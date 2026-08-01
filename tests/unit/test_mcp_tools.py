"""Tests for MCP tools module."""

import pytest
from battery_materials_agent.mcp_tools.tools import MCPToolRegistry, MCPTool, MCPToolParameter


class TestMCPToolRegistry:
    def setup_method(self):
        self.registry = MCPToolRegistry()

    def test_list_tools(self):
        tools = self.registry.list_tools()
        assert len(tools) >= 8

    def test_get_tool(self):
        tool = self.registry.get_tool("route_material")
        assert tool is not None
        assert tool.name == "route_material"

    def test_get_nonexistent_tool(self):
        assert self.registry.get_tool("nonexistent") is None

    def test_register_custom_tool(self):
        tool = MCPTool(
            name="custom_tool",
            description="A custom tool",
            parameters=[MCPToolParameter(name="input", type="string", description="Input")],
        )
        self.registry.register(tool)
        assert self.registry.get_tool("custom_tool") is not None

    def test_unregister_tool(self):
        tool = MCPTool(name="to_remove", description="Remove me")
        self.registry.register(tool)
        self.registry.unregister("to_remove")
        assert self.registry.get_tool("to_remove") is None

    def test_execute_tool(self):
        def handler(x=0):
            return {"result": x + 1}
        tool = MCPTool(name="add_one", description="Add one")
        self.registry.register(tool, handler=handler)
        result = self.registry.execute("add_one", x=5)
        assert result["result"] == 6

    def test_execute_no_handler(self):
        with pytest.raises(ValueError):
            self.registry.execute("route_material")

    def test_to_mcp_manifest(self):
        manifest = self.registry.to_mcp_manifest()
        assert "tools" in manifest
        assert len(manifest["tools"]) >= 8
        for tool in manifest["tools"]:
            assert "name" in tool
            assert "description" in tool
            assert "parameters" in tool

    def test_tool_parameters(self):
        tool = self.registry.get_tool("generate_crystal_candidates")
        assert len(tool.parameters) >= 1
        assert tool.parameters[0].name == "elements"

    def test_builtin_tools_complete(self):
        expected_tools = [
            "route_material",
            "generate_crystal_candidates",
            "generate_polymer_candidates",
            "predict_crystal_properties",
            "predict_polymer_properties",
            "check_synthesis_feasibility",
            "verify_dft",
            "get_experiment_results",
            "subscribe_experiment_updates",
        ]
        for name in expected_tools:
            assert self.registry.get_tool(name) is not None, f"Missing tool: {name}"
