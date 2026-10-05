"""属性名规范化与别名映射（T12 模块拆分：从 api.py 抽出，消除跨模块反向依赖）。"""
from __future__ import annotations

from fastapi import HTTPException

_PROPERTY_ALIASES = {
    "ionic_conductivity": "prop.ionic_conductivity",
    "operating_voltage": "prop.operating_voltage",
    "bulk_resistance": "prop.bulk_resistance",
    "oxidation_potential": "prop.oxidation_potential",
    "crystallinity": "prop.crystallinity",
    "particle_size": "prop.particle_size",
    "glass_transition_temp": "prop.glass_transition_temp",
    "decomposition_temp": "prop.decomposition_temp",
    # v4.1 改性塑料：高分子模板主字段（0058 迁移已播种 prop.*）
    "tensile_strength": "prop.tensile_strength",
    "elongation_at_break": "prop.elongation_at_break",
    "tensile_modulus": "prop.tensile_modulus",
    "impact_strength": "prop.impact_strength",
    "flexural_modulus": "prop.flexural_modulus",
    "flexural_strength": "prop.flexural_strength",
    "heat_deflection_temp": "prop.heat_deflection_temp",
    "melt_flow_index": "prop.melt_flow_index",
    "melting_point": "prop.melting_point",
    "thermal_stability": "prop.thermal_stability",
    "weight_loss": "prop.weight_loss",
    "residual_mass": "prop.residual_mass",
    "flame_retardancy": "prop.flame_retardancy",
}


def normalize_property_name(raw: str) -> str:
    """规范化 property_name 为 mdm.properties 的合法 property_id。规则同 _normalize_test_method。"""
    v = (raw or "").strip()
    if not v or v.startswith("prop."):
        return v
    mapped = _PROPERTY_ALIASES.get(v)
    if mapped:
        return mapped
    raise HTTPException(
        status_code=400,
        detail=f"未知特性「{raw}」。可选值：{', '.join(sorted(_PROPERTY_ALIASES))}，或 mdm.properties 中的 property_id",
    )
