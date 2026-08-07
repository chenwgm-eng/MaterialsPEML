"""P2-4：加工成本明细 + EHS 合规字段细化单元测试。

覆盖：
- _depreciation_rate_for：设备关键词费率匹配与默认值
- _estimate_step_power_kw：温度功率估算与非法输入容错
- _build_hazard_profile：毒性/REACH/闪点/SDS 字段生成
- _handle_design_formula：成本明细合计与 EHS 档案完整性（mock 配方智能体与合规节点）
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

from battery_materials_agent.agent import (
    BatteryMaterialsAgent,
    _build_hazard_profile,
    _depreciation_rate_for,
    _estimate_step_power_kw,
)


# ── 折旧费率 ──────────────────────────────────────────────

def test_depreciation_rate_keyword_match():
    assert _depreciation_rate_for("双行星搅拌机") == 80.0
    assert _depreciation_rate_for("高速混料机") == 80.0
    assert _depreciation_rate_for("涂布机") == 120.0
    assert _depreciation_rate_for("真空烘箱") == 50.0
    assert _depreciation_rate_for("高温烧结炉") == 150.0


def test_depreciation_rate_default():
    assert _depreciation_rate_for("未知设备X") == 100.0
    assert _depreciation_rate_for("") == 100.0
    assert _depreciation_rate_for(None) == 100.0


# ── 功率估算 ──────────────────────────────────────────────

def test_estimate_power_room_temperature():
    assert _estimate_step_power_kw(25) == 5.0
    assert _estimate_step_power_kw(20) == 5.0  # 低于室温不增加


def test_estimate_power_heated():
    assert _estimate_step_power_kw(125) == 15.0  # 5 + 100 * 0.1
    assert abs(_estimate_step_power_kw(80) - 10.5) < 1e-9


def test_estimate_power_invalid_input():
    # 非法温度回退为室温基准功率，不抛异常
    assert _estimate_step_power_kw("abc") == 5.0
    assert _estimate_step_power_kw(None) == 5.0


# ── EHS 危险特性档案 ──────────────────────────────────────

def _make_spec(**kw):
    defaults = dict(
        material_id="RM-001",
        name="PEO",
        is_toxic=False,
        reach_compliant=True,
    )
    defaults.update(kw)
    return SimpleNamespace(**defaults)


def test_hazard_profile_non_toxic():
    p = _build_hazard_profile(_make_spec())
    assert p["reach_status"] == "通过"
    assert p["ghs_classification"] == "未分类为危险品"
    assert p["flash_point"] == "未测定"
    assert p["reactivity_hazard"] == "无已知反应性危害"
    assert p["sds_link"] == ""
    assert "REACH" in p["reach_clause"]


def test_hazard_profile_toxic():
    p = _build_hazard_profile(_make_spec(is_toxic=True, reach_compliant=False))
    assert p["reach_status"] == "未通过"
    assert "H301" in p["ghs_classification"]
    assert "反应活性" in p["reactivity_hazard"]


def test_hazard_profile_solvent_flash_point():
    p = _build_hazard_profile(_make_spec(name="碳酸二甲酯 DMC", material_id="RM-DMC"))
    assert "18" in p["flash_point"]
    # 非溶剂不误标闪点
    p2 = _build_hazard_profile(_make_spec(name="LiTFSI", material_id="RM-002"))
    assert p2["flash_point"] == "未测定"


# ── 完整配方生成（mock 依赖） ─────────────────────────────

def _make_agent_stub():
    """构造不触发真实初始化的 agent 实例（仅挂载设计配方所需依赖）。"""
    agent = BatteryMaterialsAgent.__new__(BatteryMaterialsAgent)

    recipe = SimpleNamespace(
        bom={"RM-001": 0.8, "RM-002": 0.2},
        bop=[
            {"step": "混料", "equipment": "双行星搅拌机", "temperature": 60, "duration_min": 120, "rpm": 300},
            {"step": "烘烤", "equipment": "真空烘箱", "temperature": 80, "duration_min": 240},
        ],
        equipment="双行星搅拌机",
    )
    agent.formula_agent = MagicMock()
    agent.formula_agent.design_recipe = MagicMock(return_value=_async_return(recipe))

    agent.compliance_node = MagicMock()
    agent.compliance_node.evaluate = MagicMock(return_value=SimpleNamespace(
        is_passed=True, warnings=[], fatal_errors=[], estimated_unit_cost=100.0,
    ))

    specs = {
        "RM-001": _make_spec(material_id="RM-001", name="PEO", unit_cost=85.0,
                             inventory_quantity=500.0, supplier="国泰华荣"),
        "RM-002": _make_spec(material_id="RM-002", name="LiTFSI", unit_cost=450.0,
                             inventory_quantity=100.0, supplier="国泰华荣"),
    }
    agent.raw_material_db = MagicMock()
    agent.raw_material_db.get_spec = MagicMock(side_effect=lambda mid: specs.get(mid))
    return agent


async def _async_return(value):
    return value


def test_design_formula_cost_breakdown():
    agent = _make_agent_stub()
    result = agent._handle_design_formula({"candidate": "PEO"}, quantity_kg=1.0)

    assert "error" not in result
    breakdown = result["process_cost_breakdown"]
    assert len(breakdown) == 2

    # 混料：2h × (80 折旧 + 8.5kW×0.8 能耗 + 60 人工)
    mix = breakdown[0]
    assert mix["duration_h"] == 2.0
    assert mix["depreciation_cost"] == 160.0
    # 60°C → 功率 5 + 35*0.1 = 8.5kW → 2h × 8.5 × 0.8 = 13.6
    assert mix["energy_cost"] == 13.6
    assert mix["labor_cost"] == 120.0
    assert abs(mix["subtotal"] - (160.0 + 13.6 + 120.0)) < 1e-6

    # 明细小计之和必须等于 process_cost（消除黑盒数字）
    assert abs(sum(b["subtotal"] for b in breakdown) - result["process_cost"]) < 1e-6
    # 总成本口径保持一致
    assert abs(result["material_cost"] + result["process_cost"]
               - result["total_unit_cost"]) < 1e-6


def test_design_formula_ehs_profiles():
    agent = _make_agent_stub()
    result = agent._handle_design_formula({"candidate": "PEO"}, quantity_kg=1.0)

    ehs = result["ehs"]
    # 兼容旧字段
    assert ehs["reach"] == "通过"
    # P2-4 新字段
    assert ehs["ghs_classification"] == "未分类为危险品"
    profiles = ehs["hazard_profiles"]
    assert len(profiles) == 2
    names = {p["material_name"] for p in profiles}
    assert names == {"PEO", "LiTFSI"}
    for p in profiles:
        assert set(p.keys()) >= {
            "material_name", "reach_status", "reach_clause",
            "ghs_classification", "flash_point", "reactivity_hazard", "sds_link",
        }
