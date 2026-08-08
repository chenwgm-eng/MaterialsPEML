"""科学服务接入 CapabilityRouter —— 能力目录集成回归测试。

锁定：
  1. 全部 11 个科学服务能力从服务注册表派生为可路由别名（单一数据源）；
  2. 别名结构符合约定（sci_<capability_id> / local binding sci:<capability_id>）；
  3. CapabilityRouter 能把这些别名解析为 local 候选，实现"科学服务可路由"。

约定：基于 unittest + 真实 PostgreSQL（与 test_e2e_integration 一致）。
"""

from __future__ import annotations

import asyncio
import unittest

from battery_materials_agent.agent_team.eligibility_store import EligibilityStore
from battery_materials_agent.control_plane.capability_router import CapabilityRouter
from battery_materials_agent.mcp_tools.alias_registry import AliasRegistry
from battery_materials_agent.services.capability_catalog import (
    build_scientific_aliases,
    register_scientific_capabilities,
    scientific_alias,
    scientific_binding,
)


class ScientificCapabilityCatalogTest(unittest.TestCase):
    def test_aliases_derived_from_all_services(self):
        """所有科学服务都应派生为可路由别名。"""
        aliases = build_scientific_aliases()
        self.assertEqual(len(aliases), 11)
        by_alias = {a.alias: a for a in aliases}
        self.assertIn("sci_mpa", by_alias)
        self.assertEqual(by_alias["sci_mpa"].local_binding, "sci:mpa")
        self.assertEqual(by_alias["sci_mpa"].category, "scientific")
        # 每个别名走 local 绑定，且默认全 profile 可用
        for a in aliases:
            self.assertTrue(a.local_binding.startswith("sci:"))
            self.assertIn("standard", a.allowed_profiles)

    def test_enabled_filter_limits_aliases(self):
        """SCIENTIFIC_CAPABILITIES_ENABLED 开关仅暴露指定服务。"""
        aliases = build_scientific_aliases(enabled={"mpa", "chem_properties"})
        self.assertEqual({a.alias for a in aliases}, {"sci_mpa", "sci_chem_properties"})

    def test_capability_router_resolves_scientific_capability(self):
        """注册后 CapabilityRouter 应能把科学服务解析为 local 候选。"""
        alias_registry = AliasRegistry()
        eligibility_store = EligibilityStore()
        register_scientific_capabilities(alias_registry, eligibility_store)

        router = CapabilityRouter(alias_registry, eligibility_store)
        candidates = asyncio.run(router.resolve("sci_mpa", "standard"))
        self.assertTrue(candidates, "sci_mpa 应解析出候选")
        local = [c for c in candidates if c.source == "local" and c.binding_id == "local:sci:mpa"]
        self.assertEqual(len(local), 1)

    def test_unknown_scientific_capability_returns_empty(self):
        """未注册的科学服务别名应返回空候选（而非误路由）。"""
        alias_registry = AliasRegistry()
        eligibility_store = EligibilityStore()
        router = CapabilityRouter(alias_registry, eligibility_store)
        candidates = asyncio.run(router.resolve("sci_not_a_service", "standard"))
        self.assertEqual(candidates, [])


class NamingConventionTest(unittest.TestCase):
    def test_alias_binding_convention(self):
        self.assertEqual(scientific_alias("mpa"), "sci_mpa")
        self.assertEqual(scientific_binding("mpa"), "sci:mpa")


if __name__ == "__main__":
    unittest.main()