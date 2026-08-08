"""Integration tests for the main Battery Materials Agent."""

import pytest
import tempfile
import os
from battery_materials_agent.agent import BatteryMaterialsAgent
from battery_materials_agent.config import AgentConfig
from battery_materials_agent.router.router import MaterialInput, MaterialType


@pytest.fixture
def agent():
    with tempfile.TemporaryDirectory() as tmpdir:
        config = AgentConfig(
            data_dir=os.path.join(tmpdir, "data"),
        )
        os.makedirs(config.data_dir, exist_ok=True)
        a = BatteryMaterialsAgent(config)
        yield a


class TestBatteryMaterialsAgent:
    def test_route_material_crystal(self, agent):
        result = agent.route(MaterialInput(name="spinel structure"))
        assert result.material_type == MaterialType.CRYSTAL

    def test_route_material_polymer(self, agent):
        result = agent.route(MaterialInput(psmiles="Polymer([*]CCO[*])"))
        assert result.material_type == MaterialType.POLYMER

    def test_discover_crystal(self, agent):
        # 严格子集过滤要求候选元素 ⊆ 目标元素集。真实 GNoME 稳定集中不存在
        # 纯 Li-Co 二元化合物（Li-Co 合金不稳定），故用真实正极体系 Li-Co-O。
        result = agent.discover_crystal(elements=["Li", "Co", "O"], num_candidates=5)
        assert result["count"] > 0
        assert len(result["candidates"]) > 0

    def test_discover_polymer(self, agent):
        result = agent.discover_polymer(num_candidates=5)
        assert result["count"] > 0

    def test_check_synthesis(self, agent):
        score = agent.check_synthesis("CCO")
        assert 0.0 <= score <= 1.0

    def test_verify(self, agent):
        result = agent.verify("CCO", "total_energy")
        assert result.molecule_name == "CCO"

    def test_query_experiments_empty(self, agent):
        records = agent.query_experiments()
        assert isinstance(records, list)

    def test_get_mcp_manifest(self, agent):
        manifest = agent.get_mcp_manifest()
        assert "tools" in manifest
        assert len(manifest["tools"]) >= 8

    def test_discover_full_loop(self, agent):
        state = agent.discover("test", max_iterations=1)
        assert state.is_complete is True
        assert state.iteration == 1

    def test_discover_multiple_iterations(self, agent):
        state = agent.discover("test", max_iterations=2)
        assert state.iteration == 2

    def test_tool_registration(self, agent):
        tools = agent.tools.list_tools()
        assert len(tools) >= 9

    def test_tool_handler_exists(self, agent):
        assert agent.tools._handlers.get("route_material") is not None
        assert agent.tools._handlers.get("generate_crystal_candidates") is not None

    def test_ecml_summary(self, agent):
        state = agent.discover("test", max_iterations=1)
        summary = agent.ecml.get_summary(state)
        assert summary["iterations"] == 1
        assert summary["branch"] == "crystal_branch"
