import os
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))

from helpers.cluster import ClickHouseCluster

cluster = ClickHouseCluster(__file__)
node = cluster.add_instance(
    'node', 
    stay_alive=True,
    # main_configs=['config/foundationdb.xml'],
    with_foundationdb=True
 )



def skip_test_msan(instance):
    if instance.is_built_with_memory_sanitizer():
        pytest.skip("Memory Sanitizer cannot work with vfork")

def copy_file_to_container(local_path, dist_path, container_id):
    os.system("docker cp {local} {cont_id}:{dist}".format(local=local_path, cont_id=container_id, dist=dist_path))


func_xml = "/etc/clickhouse-server/config.d/executable_user_defined_functions_config.xml"
config = '''<clickhouse>
    <user_defined_executable_functions_config>/etc/clickhouse-server/functions/test_function_config.xml</user_defined_executable_functions_config>
</clickhouse>'''

@pytest.fixture(scope="module")
def started_cluster():
    try:
        cluster.start()
        node = cluster.instances['node']
        node.replace_config(func_xml, config)
        with open(os.path.dirname(__file__) + "/config/foundationdb.xml", "r") as f:
            node.replace_config("/etc/clickhouse-server/config.d/foundationdb.xml", f.read())
        copy_file_to_container(os.path.join(SCRIPT_DIR, 'functions/.'), '/etc/clickhouse-server/functions', node.docker_id)
        copy_file_to_container(os.path.join(SCRIPT_DIR, 'user_scripts/.'), '/var/lib/clickhouse/user_scripts', node.docker_id)

        node.restart_clickhouse()

        yield cluster

    finally:
        cluster.shutdown()

def test_executable_function_python(started_cluster):
    node = cluster.instances['node']
    node.start_clickhouse()
    assert node.query("SELECT test_function_python(toUInt64(1))") == 'Key 1\n'
    assert node.query("SELECT test_function_python(1)") == 'Key 1\n'
    node.stop_clickhouse()

def test_executable_function_python_fdb_down(started_cluster):
    node = cluster.instances['node']
    node.start_clickhouse()
    assert node.query("SELECT test_function_python(toUInt64(1))") == 'Key 1\n'
    assert node.query("SELECT test_function_python(1)") == 'Key 1\n'
    cluster.stop_fdb()
    time.sleep(50)
    # Can not find function without fdb
    assert node.contains_in_log("Operation aborted because the transaction timed out")
    assert "Unknown function test_function_python" in node.query_and_get_error("SELECT test_function_python(1)")

    cluster.start_fdb()
    time.sleep(50)
    assert node.query("SELECT test_function_python(toUInt64(1))") == 'Key 1\n'
    assert node.query("SELECT test_function_python(1)") == 'Key 1\n'
    node.stop_clickhouse()

