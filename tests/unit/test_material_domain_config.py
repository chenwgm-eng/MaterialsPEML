"""Task 4 材料体系可配置回归测试。

验证：
- MaterialDomainConfig 默认提供通用材料体系模板（非电池硬编码）
- 环境变量 MATERIAL_DOMAIN_SYSTEMS 可覆盖体系模板
- AgentConfig 挂载 material_domain 且序列化到 /config 接口
"""

from __future__ import annotations

import importlib
import json

import pytest

import battery_materials_agent.config as config_mod
from battery_materials_agent.config import MaterialDomainConfig


class TestMaterialDomainConfig:
    def test_default_material_systems_are_generic(self):
        """默认体系模板应为通用材料体系，而非电池专属硬编码。"""
        cfg = MaterialDomainConfig()
        names = [s["name"] for s in cfg.material_systems]
        assert "硫化物固态电解质" in names
        assert "钙钛矿氧化物" in names
        # 必须包含通用体系，体现"泛化为通用材料平台"决策
        assert any("氧化物" in n for n in names)
        assert cfg.default_target_properties
        assert cfg.example_formulas
        # 每个体系模板都带合法元素列表
        for s in cfg.material_systems:
            assert isinstance(s.get("elements"), list)
            assert s["elements"]

    def test_env_override_material_systems(self, monkeypatch):
        """MATERIAL_DOMAIN_SYSTEMS 环境变量可覆盖默认体系模板。"""
        systems = [
            {"name": "钢铁合金", "elements": ["Fe", "C"]},
            {"name": "陶瓷复合", "elements": ["Al", "O", "Si"]},
        ]
        monkeypatch.setenv("MATERIAL_DOMAIN_SYSTEMS", json.dumps(systems))
        importlib.reload(config_mod)
        try:
            cfg = config_mod.load_config()
            assert [s["name"] for s in cfg.material_domain.material_systems] == [
                "钢铁合金", "陶瓷复合",
            ]
        finally:
            importlib.reload(config_mod)

    def test_invalid_env_ignored(self, monkeypatch):
        """非法 JSON 的 MATERIAL_DOMAIN_SYSTEMS 应被忽略并回退默认。"""
        monkeypatch.setenv("MATERIAL_DOMAIN_SYSTEMS", "not-json{{{")
        importlib.reload(config_mod)
        try:
            cfg = config_mod.load_config()
            assert cfg.material_domain.material_systems
        finally:
            importlib.reload(config_mod)

    def test_agent_config_loads_material_domain(self):
        """load_config 构造的 AgentConfig 应挂载 material_domain。"""
        cfg = config_mod.load_config()
        assert cfg.material_domain.material_systems
        assert cfg.material_domain.default_target_properties


class TestConfigSerialization:
    def test_serialize_agent_config_contains_material_domain(self):
        """/api/config 序列化器应包含 material_domain.material_systems。"""
        from battery_materials_agent.api import _serialize_agent_config

        cfg = config_mod.load_config()
        resp = _serialize_agent_config(cfg)
        md = resp["material_domain"]
        assert md["material_systems"]
        assert md["default_target_properties"]
        assert md["example_formulas"]