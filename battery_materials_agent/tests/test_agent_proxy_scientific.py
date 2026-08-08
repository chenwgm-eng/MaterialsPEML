"""AgentProxy 科学服务能力（sci_*）经 CapabilityRouter 路由执行的端到端测试。

锁定（方案 a —— 真实调用经过 CapabilityRouter）：
  1. sci_* 能力调用真实经过 CapabilityRouter.resolve（不绕过路由）；
  2. 解析出的 local:sci:<id> 绑定被映射到对应科学服务并执行 run_full_cycle；
  3. 未注册 / 无法路由的能力返回明确失败，而非误执行；
  4. 未注入 CapabilityRouter 时返回明确失败。
"""

from __future__ import annotations

import asyncio
import unittest
from unittest import mock

from battery_materials_agent.agent_team.agent_proxy import AgentProxy
from battery_materials_agent.control_plane.capability_router import CapabilityRouter
from battery_materials_agent.control_plane.tool_catalog import ToolCatalog
from battery_materials_agent.mcp_tools.alias_registry import AliasRegistry
from battery_materials_agent.services.capability_catalog import (
    register_scientific_capabilities,
    register_scientific_tools,
)


class FakeEligibilityStore:
    """内存版资格规则存储（避免单测依赖 PostgreSQL），接口对齐真实 Store。"""

    def __init__(self):
        self._rules = []

    def list_by_capability(self, capability, profile):
        return [r for r in self._rules
                if r.capability == capability and profile in r.profiles]

    def list_all(self):
        return list(self._rules)

    def create(self, rule):
        self._rules.append(rule)
        return rule.rule_id


class FakeScientificService:
    """模拟 NativeScientificService，仅记录 run_full_cycle 调用。"""

    def __init__(self, capability_id: str):
        self.capability_id = capability_id
        self.calls = []

    def run_full_cycle(self, task, context=None):
        self.calls.append((task, context))
        return [{"capability_id": self.capability_id, "task_id": task.task_id}]


def _build_proxy(with_router: bool = True):
    alias_registry = AliasRegistry()
    eligibility_store = FakeEligibilityStore()
    register_scientific_capabilities(alias_registry, eligibility_store)
    router = CapabilityRouter(alias_registry, eligibility_store)
    svc = FakeScientificService("mpa")
    proxy = AgentProxy(
        agent_registry=None,
        mapping_store=None,
        mcp_tool_registry=None,
        capability_router=router if with_router else None,
        scientific_registry={"mpa": svc},
    )
    return proxy, svc


class AgentProxyScientificRoutingTest(unittest.TestCase):
    def test_sci_capability_routed_through_router_and_executed(self):
        """sci_mpa 应经 CapabilityRouter 解析并执行对应科学服务。"""
        proxy, svc = _build_proxy()
        params = {"project_id": "p1", "formula": "LiFePO4"}
        result = proxy.invoke_tool("any_agent", "sci_mpa", params)

        self.assertTrue(result.success, result.error)
        self.assertEqual(result.tool_id, "local:sci:mpa")
        self.assertFalse(result.used_fallback)
        self.assertEqual(len(svc.calls), 1)
        task, ctx = svc.calls[0]
        self.assertEqual(task.capability_id, "mpa")
        self.assertEqual(task.project_id, "p1")
        self.assertEqual(task.metadata, params)

    def test_router_resolve_is_consulted(self):
        """必须真实调用 CapabilityRouter.resolve（证明未绕过路由层）。"""
        alias_registry = AliasRegistry()
        eligibility_store = FakeEligibilityStore()
        register_scientific_capabilities(alias_registry, eligibility_store)
        router = CapabilityRouter(alias_registry, eligibility_store)
        svc = FakeScientificService("mpa")
        proxy = AgentProxy(
            agent_registry=None, mapping_store=None, mcp_tool_registry=None,
            capability_router=router, scientific_registry={"mpa": svc},
        )
        with mock.patch.object(router, "resolve", wraps=router.resolve) as spy:
            result = proxy.invoke_tool("any", "sci_mpa", {"project_id": "p1"})
        self.assertTrue(result.success, result.error)
        spy.assert_called_once_with("sci_mpa", "standard")

    def test_unknown_sci_capability_fails(self):
        """未注册的 sci_* 能力应失败，而非误执行。"""
        proxy, svc = _build_proxy()
        result = proxy.invoke_tool("any", "sci_not_a_service", {})

        self.assertFalse(result.success)
        self.assertIn("No routable", result.error)
        self.assertEqual(len(svc.calls), 0)

    def test_sci_without_router_fails(self):
        """未注入 CapabilityRouter 时返回明确失败。"""
        proxy, svc = _build_proxy(with_router=False)
        result = proxy.invoke_tool("any", "sci_mpa", {})

        self.assertFalse(result.success)
        self.assertIn("CapabilityRouter 未配置", result.error)
        self.assertEqual(len(svc.calls), 0)

    def test_sci_capability_async_path(self):
        """异步入口 invoke_tool_async 同样经路由执行。"""
        proxy, svc = _build_proxy()
        result = asyncio.run(proxy.invoke_tool_async("any", "sci_mpa", {"project_id": "p1"}))

        self.assertTrue(result.success, result.error)
        self.assertEqual(result.tool_id, "local:sci:mpa")
        self.assertEqual(len(svc.calls), 1)
        self.assertEqual(svc.calls[0][0].capability_id, "mpa")


class RiskFilteringTest(unittest.TestCase):
    """CA3 回归：注入 ToolCatalog 后，科学服务候选携带真实风险分，路由真正做风险过滤。"""

    def _router(self, max_risk_level: str | None = None):
        alias_registry = AliasRegistry()
        eligibility_store = FakeEligibilityStore()
        register_scientific_capabilities(alias_registry, eligibility_store)
        tool_catalog = ToolCatalog()
        register_scientific_tools(tool_catalog)
        if max_risk_level is not None:
            for rule in eligibility_store.list_all():
                rule.max_risk_level = max_risk_level
        return CapabilityRouter(alias_registry, eligibility_store, tool_catalog=tool_catalog)

    def test_scientific_candidate_carries_real_risk_score(self):
        """科学服务注册进 ToolCatalog 后，候选风险分应为 0.3（默认 C），而非最低 0.1。"""
        router = self._router()
        candidates = asyncio.run(router.resolve("sci_mpa", "standard"))
        local = [c for c in candidates if c.binding_id == "local:sci:mpa"]
        self.assertEqual(len(local), 1)
        self.assertEqual(local[0].risk_score, 0.3)

    def test_default_gate_admits_own_risk(self):
        """默认门禁（C 风险 → max_risk_level=B，放行 ≤0.3）应放行自身 C 风险候选。"""
        router = self._router()
        candidates = asyncio.run(router.resolve("sci_mpa", "standard"))
        self.assertTrue(any(c.binding_id == "local:sci:mpa" for c in candidates))

    def test_tightened_gate_filters_scientific_candidate(self):
        """收紧门禁到 A（放行 ≤0.1）后，C 风险科学候选应被真正过滤（而非恒放行）。"""
        router = self._router(max_risk_level="A")
        candidates = asyncio.run(router.resolve("sci_mpa", "standard"))
        self.assertEqual(candidates, [])

    def test_without_tool_catalog_risk_is_minimum(self):
        """未注入 ToolCatalog 时风险回落 0.1 —— 复现 CA3 根因，证明注册是必要前提。"""
        alias_registry = AliasRegistry()
        eligibility_store = FakeEligibilityStore()
        register_scientific_capabilities(alias_registry, eligibility_store)
        router = CapabilityRouter(alias_registry, eligibility_store)
        candidates = asyncio.run(router.resolve("sci_mpa", "standard"))
        local = [c for c in candidates if c.binding_id == "local:sci:mpa"]
        self.assertEqual(local[0].risk_score, 0.1)


if __name__ == "__main__":
    unittest.main()