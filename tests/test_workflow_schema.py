"""测试统一工作流 Schema。"""

import pytest
from pathlib import Path
from battery_materials_agent.workflow_schema import WorkflowSchemaLoader, get_schema_loader


@pytest.fixture
def loader():
    return WorkflowSchemaLoader()


def test_schema_loads(loader):
    """Schema 能正确加载。"""
    schema = loader.load()
    assert "workflow" in schema
    assert schema["workflow"]["id"] == "ecml_v2"


def test_nodes_exist(loader):
    """节点列表非空。"""
    nodes = loader.get_nodes()
    assert len(nodes) >= 8


def test_node_has_required_fields(loader):
    """每个节点有 id 和 name。"""
    nodes = loader.get_nodes()
    for node in nodes:
        assert "id" in node
        assert "name" in node


def test_states_exist(loader):
    """状态列表存在。"""
    candidate_states = loader.get_states("candidate")
    assert len(candidate_states) > 0
    assert "GENERATED" in candidate_states


def test_experiment_states(loader):
    """实验状态包含 WAITING_FOR_DATA。"""
    exp_states = loader.get_states("experiment")
    assert "WAITING_FOR_DATA" in exp_states


def test_events_exist(loader):
    """事件列表存在。"""
    events = loader.get_events()
    assert "wet_data.qc_passed" in events


def test_timeout_policy(loader):
    """超时策略存在。"""
    policy = loader.get_timeout_policy()
    assert "experiment_scheduling_timeout_hours" in policy


def test_schema_singleton():
    """全局单例正常工作。"""
    l1 = get_schema_loader()
    l2 = get_schema_loader()
    assert l1 is l2
