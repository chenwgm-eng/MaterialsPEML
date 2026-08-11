"""领域包（Domain Pack）通用化改造单元测试。

覆盖：
- FormulaAgent 按领域包解析配方模板（BASE_POLYMER / "*" 默认模板）
- FormulaAgent 回退到内置默认领域包（库不可用/空时）
- _assert_bom_system_consistency 从领域包 consistency 规则读取关键词
- DomainPackStore 内置默认领域包
"""

from types import SimpleNamespace

from battery_materials_agent.industrialization.formula_agent import FormulaAgent
from battery_materials_agent.industrialization.domain_pack_store import DomainPackStore


def _fake_db():
    """构造轻量物料库桩：按分类返回物料（v4.1 高分子体系分类）。"""
    db = SimpleNamespace()
    db.query_category = lambda cat: {
        "BASE_POLYMER": [SimpleNamespace(material_id="RM-P", name="PP 基材")],
        "material.reinforcement": [SimpleNamespace(material_id="RM-G", name="玻纤 GF30")],
        "ADDITIVE": [SimpleNamespace(material_id="RM-A", name="抗氧剂")],
        "FILLER": [SimpleNamespace(material_id="RM-F", name="滑石粉")],
    }.get(cat) or []
    db.get_all = lambda: []
    db.get_spec = lambda mid: None
    return db


def test_formula_agent_resolves_base_polymer_template():
    fa = FormulaAgent(raw_material_db=_fake_db(), config=None, domain_pack=DomainPackStore.builtin_fallback())
    tpl = fa._recipe_template_for("BASE_POLYMER")
    assert tpl["material_type"] == "BASE_POLYMER"
    assert tpl["equipment"] == "双螺杆挤出机"


def test_formula_agent_resolves_default_template_for_unknown_type():
    fa = FormulaAgent(raw_material_db=_fake_db(), config=None, domain_pack=DomainPackStore.builtin_fallback())
    # 未知材料类型回退到 "*" 默认模板（高分子改性通用流程）
    tpl = fa._recipe_template_for("NEW_MATERIAL_TYPE")
    assert tpl["material_type"] == "*"
    assert tpl["equipment"] == "高速混合机"


def test_formula_agent_known_target_uses_template_bom():
    fa = FormulaAgent(raw_material_db=_fake_db(), config=None, domain_pack=DomainPackStore.builtin_fallback())
    target = SimpleNamespace(material_id="RM-P", name="PP 基材", category="BASE_POLYMER")
    recipe = fa._recipe_for_known_target(target)
    # v4.1：主成分 0.7 + 增强填料 0.3（改性塑料典型配方）
    assert recipe.bom.get("RM-P") == 0.7
    assert recipe.bom.get("RM-G") == 0.3
    assert recipe.equipment == "双螺杆挤出机"


def test_formula_agent_fallback_uses_domain_pack_fallback():
    fa = FormulaAgent(raw_material_db=_fake_db(), config=None, domain_pack=DomainPackStore.builtin_fallback())
    recipe = fa._fallback_recipe({"candidate": "未知新材料XYZ"})
    # 回退配方按分类取首个物料：BASE_POLYMER 0.7 + material.reinforcement 0.3
    assert recipe.bom.get("RM-P") == 0.7
    assert recipe.bom.get("RM-G") == 0.3
    assert recipe.equipment == "双螺杆挤出机"


def test_formula_agent_uses_custom_domain_pack():
    custom = {
        "recipe_templates": [
            {
                "material_type": "FIBER",
                "main_ratio": 0.95,
                "additives": [],
                "equipment": "熔融纺丝机",
                "bop": [{"step": "熔融纺丝", "temperature": 280, "duration_min": 60, "rpm": 0}],
            }
        ],
        "fallback_recipe": {"bom": {"FIBER": 1.0}, "equipment": "熔融纺丝机", "bop": []},
        "consistency": {"polymer_kw": [], "crystal_kw": []},
    }
    db = _fake_db()
    db.query_category = lambda cat: (
        [SimpleNamespace(material_id="RM-FIB", name="PET")] if cat == "FIBER" else []
    )
    fa = FormulaAgent(raw_material_db=db, config=None, domain_pack=custom)
    tpl = fa._recipe_template_for("FIBER")
    assert tpl["equipment"] == "熔融纺丝机"
    # 无匹配模板时不再乱套默认模板
    db.query_category = lambda cat: []
    recipe = fa._fallback_recipe({"candidate": "X"})
    assert recipe.bom == {}


def test_bom_consistency_uses_domain_pack_rules():
    from battery_materials_agent.api import _assert_bom_system_consistency
    # 自定义一致性规则：仅 DMC 为聚合物关键词
    rules = {"polymer_kw": ["dmc"], "crystal_kw": ["graphite"]}
    bom = [{"material_name": "DMC"}, {"material_name": "Li2S"}]
    crossed = _assert_bom_system_consistency("crystal", "Li6PS5Cl", bom, rules)
    assert crossed == ["dmc"]
    # 默认规则下 DMC 不是聚合物关键词，不拦截（保持旧行为）
    assert _assert_bom_system_consistency("crystal", "Li6PS5Cl", bom) == []


def test_builtin_fallback_is_deep_copy():
    a = DomainPackStore.builtin_fallback()
    b = DomainPackStore.builtin_fallback()
    a["consistency"]["polymer_kw"].append("x")
    assert "x" not in b["consistency"]["polymer_kw"]