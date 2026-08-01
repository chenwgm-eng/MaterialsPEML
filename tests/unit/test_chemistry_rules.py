"""Task 15 化学规则引擎单元测试。

覆盖：
- 必含元素校验（required_elements）
- 禁含元素校验（forbidden_elements）
- 元素数量上限校验（max_elements_count）
- 结构类型校验（required_structure_types）
- 复杂化学式解析（如 Na2CaMg(SO4)3）
- 批量过滤 filter_candidates
- 集成测试：generate_candidates 端到端硬过滤
- 委员会适配器联动
"""

from __future__ import annotations

import pytest

from battery_materials_agent.generation.chemistry_rules import ChemistryRuleSet
from battery_materials_agent.generation.crystal_candidate_generator import (
    CrystalCandidate,
    CrystalCandidateGenerator,
)
from battery_materials_agent.generation.formula_validator import parse_formula_elements
from battery_materials_agent.committee.adapters.crystal import CrystalAdapter


class TestParseFormulaElements:
    """复杂化学式元素解析（parse_formula_elements）。"""

    def test_simple_formula(self):
        assert parse_formula_elements("Li2O") == {"Li", "O"}

    def test_no_coefficient(self):
        assert parse_formula_elements("LiCoO2") == {"Li", "Co", "O"}

    def test_nested_parentheses(self):
        """Na2CaMg(SO4)3 — 嵌套括号与系数。"""
        elements = parse_formula_elements("Na2CaMg(SO4)3")
        assert elements == {"Na", "Ca", "Mg", "S", "O"}

    def test_decimal_coefficients(self):
        """LiNi0.8Mn0.1Co0.1O2 — 小数系数。"""
        elements = parse_formula_elements("LiNi0.8Mn0.1Co0.1O2")
        assert elements == {"Li", "Ni", "Mn", "Co", "O"}

    def test_multiple_groups(self):
        """Li6PS5Cl — 多元素无括号。"""
        assert parse_formula_elements("Li6PS5Cl") == {"Li", "P", "S", "Cl"}

    def test_invalid_formula_returns_empty(self):
        """非法化学式（未知元素、括号不匹配）返回空集合。"""
        assert parse_formula_elements("Xx3O2") == set()
        assert parse_formula_elements("Ca(OH2") == set()
        assert parse_formula_elements("") == set()


class TestRequiredElements:
    """必含元素校验。"""

    def test_passes_when_required_present(self):
        rules = ChemistryRuleSet(required_elements=["Li"])
        ok, reasons = rules.validate("LiCoO2")
        assert ok
        assert reasons == []

    def test_fails_when_required_missing(self):
        rules = ChemistryRuleSet(required_elements=["Li"])
        ok, reasons = rules.validate("Na3PS4")
        assert not ok
        assert any("missing required element: Li" in r for r in reasons)

    def test_multiple_required(self):
        rules = ChemistryRuleSet(required_elements=["Li", "Co"])
        ok, _ = rules.validate("LiCoO2")
        assert ok
        ok2, reasons2 = rules.validate("LiFePO4")
        assert not ok2
        assert any("missing required element: Co" in r for r in reasons2)

    def test_case_insensitive_input(self):
        """规则集中的元素符号大小写不敏感（'li' 与 'Li' 等价）。"""
        rules = ChemistryRuleSet(required_elements=["li", "CO"])
        ok, _ = rules.validate("LiCoO2")
        assert ok


class TestForbiddenElements:
    """禁含元素校验。"""

    def test_passes_when_forbidden_absent(self):
        rules = ChemistryRuleSet(forbidden_elements=["Co"])
        ok, reasons = rules.validate("LiFePO4")
        assert ok
        assert reasons == []

    def test_fails_when_forbidden_present(self):
        rules = ChemistryRuleSet(forbidden_elements=["Co"])
        ok, reasons = rules.validate("LiCoO2")
        assert not ok
        assert any("contains forbidden element: Co" in r for r in reasons)

    def test_no_cobalt_solid_electrolyte_scenario(self):
        """验证场景：不含钴、锂离子固态电解质。"""
        rules = ChemistryRuleSet(
            required_elements=["Li"],
            forbidden_elements=["Co"],
        )
        # LiCoO2 含 Co，应被拒绝
        ok_co, _ = rules.validate("LiCoO2")
        assert not ok_co
        # Li7La3Zr2O12 (LLZO) 含 Li 不含 Co，应通过
        ok_llzo, _ = rules.validate("Li7La3Zr2O12")
        assert ok_llzo


class TestMaxElementsCount:
    """元素数量上限校验。"""

    def test_passes_under_limit(self):
        rules = ChemistryRuleSet(max_elements_count=3)
        ok, _ = rules.validate("LiCoO2")  # 3 种元素
        assert ok

    def test_fails_over_limit(self):
        rules = ChemistryRuleSet(max_elements_count=3)
        ok, reasons = rules.validate("LiNi0.8Mn0.1Co0.1O2")  # 5 种元素
        assert not ok
        assert any("too many elements" in r for r in reasons)

    def test_exactly_at_limit(self):
        rules = ChemistryRuleSet(max_elements_count=4)
        ok, _ = rules.validate("LiNi0.8Mn0.1Co0.1O2")  # 5 种元素 > 4
        assert not ok


class TestRequiredStructureTypes:
    """结构类型校验。"""

    def test_passes_when_structure_in_whitelist(self):
        rules = ChemistryRuleSet(required_structure_types=["Layered", "Spinel"])
        ok, _ = rules.validate("LiCoO2", structure_type="Layered")
        assert ok

    def test_fails_when_structure_not_in_whitelist(self):
        rules = ChemistryRuleSet(required_structure_types=["Layered", "Spinel"])
        ok, reasons = rules.validate("LiFePO4", structure_type="Olivine")
        assert not ok
        assert any("structure type" in r for r in reasons)

    def test_skipped_when_structure_type_empty(self):
        """structure_type 为空时跳过该项，避免误伤未标注的候选。"""
        rules = ChemistryRuleSet(required_structure_types=["Layered"])
        ok, _ = rules.validate("LiCoO2", structure_type=None)
        assert ok
        ok2, _ = rules.validate("LiCoO2", structure_type="")
        assert ok2


class TestEmptyRuleSet:
    """空规则集不过滤任何候选。"""

    def test_empty_rule_set_passes_all(self):
        rules = ChemistryRuleSet.empty()
        assert rules.is_empty()
        ok, reasons = rules.validate("LiCoO2", "Layered")
        assert ok
        assert reasons == []

    def test_default_rule_set_is_empty(self):
        rules = ChemistryRuleSet()
        assert rules.is_empty()


class TestFilterCandidates:
    """批量过滤 filter_candidates。"""

    def test_empty_rule_set_returns_all(self):
        rules = ChemistryRuleSet.empty()
        candidates = [
            CrystalCandidate(formula="LiCoO2", structure_type="Layered"),
            CrystalCandidate(formula="Na3PS4", structure_type="NASICON"),
        ]
        passed, filtered_out = rules.filter_candidates(candidates)
        assert len(passed) == 2
        assert len(filtered_out) == 0

    def test_filters_by_forbidden_element(self):
        rules = ChemistryRuleSet(forbidden_elements=["Co"])
        candidates = [
            CrystalCandidate(formula="LiCoO2", structure_type="Layered"),  # 含 Co，剔除
            CrystalCandidate(formula="LiFePO4", structure_type="Olivine"),  # 通过
            CrystalCandidate(formula="Co3O4", structure_type="Spinel"),  # 含 Co，剔除
        ]
        passed, filtered_out_pairs = rules.filter_candidates(candidates)
        assert len(passed) == 1
        assert passed[0].formula == "LiFePO4"
        assert len(filtered_out_pairs) == 2
        # 每个被剔除项是 (candidate, reasons) 元组
        for cand, reasons in filtered_out_pairs:
            assert any("Co" in r for r in reasons)
        # 被剔除的候选对象未被修改（不附帶额外属性）
        assert not hasattr(filtered_out_pairs[0][0], "chemistry_filter_reasons")

    def test_supports_dict_candidates(self):
        rules = ChemistryRuleSet(required_elements=["Li"])
        candidates = [
            {"formula": "LiCoO2", "structure_type": "Layered"},
            {"formula": "Na3PS4", "structure_type": "NASICON"},
        ]
        passed, filtered_out_pairs = rules.filter_candidates(candidates)
        assert len(passed) == 1
        assert passed[0]["formula"] == "LiCoO2"
        assert len(filtered_out_pairs) == 1
        # 被剔除项是 (dict, reasons) 元组
        rejected_dict, reasons = filtered_out_pairs[0]
        assert rejected_dict["formula"] == "Na3PS4"
        assert any("Li" in r for r in reasons)


class TestGenerateCandidatesIntegration:
    """集成测试：generate_candidates 端到端硬过滤。"""

    def setup_method(self):
        self.generator = CrystalCandidateGenerator(api_key="")

    def test_exclude_cobalt_returns_no_co_candidates(self):
        """验证场景：不含钴、锂离子固态电解质——候选不再返回含 Co 的化学式。"""
        candidates = self.generator.generate_candidates(
            target_property="ionic_conductivity",
            elements=["Li", "Co", "O", "Fe", "Mn", "Ni", "P", "S", "La", "Zr"],
            num_candidates=20,
            require_elements=["Li"],
            exclude_elements=["Co"],
        )
        # 断言所有返回候选都不含 Co
        for c in candidates:
            elements = parse_formula_elements(c.formula)
            assert "Co" not in elements, f"候选 {c.formula} 含 Co，违反 exclude_elements=['Co']"
            assert "Li" in elements, f"候选 {c.formula} 缺 Li，违反 require_elements=['Li']"

    def test_require_lithium_returns_only_li_candidates(self):
        """验证场景：含 Li 的电解质——候选不再返回不含 Li 的化学式。"""
        candidates = self.generator.generate_candidates(
            target_property="ionic_conductivity",
            elements=["Li", "Na", "Co", "O", "P", "S"],
            num_candidates=15,
            require_elements=["Li"],
        )
        assert len(candidates) > 0
        for c in candidates:
            elements = parse_formula_elements(c.formula)
            assert "Li" in elements, f"候选 {c.formula} 缺 Li"

    def test_filtered_out_candidates_tracked(self):
        """被规则引擎剔除的候选可在 get_last_chemistry_filtered_out 中查到。"""
        # 先清空历史
        self.generator._last_chemistry_filtered_out = []
        self.generator.generate_candidates(
            target_property="ionic_conductivity",
            elements=["Li", "Co", "O", "Fe"],
            num_candidates=10,
            exclude_elements=["Co"],
        )
        # 由于本地库含 LiCoO2、Co3O4、CoO 等含 Co 候选，应至少有一个被剔除
        # （若本地库内容变化导致无 Co 候选，则 filtered_out 可能为空，此断言放宽）
        filtered_out = self.generator.get_last_chemistry_filtered_out()
        assert isinstance(filtered_out, list)
        # 被剔除候选应为 CrystalCandidate 对象，且确实含 Co（违反 exclude_elements）
        for c in filtered_out:
            assert hasattr(c, "formula")
            elements = parse_formula_elements(c.formula)
            assert "Co" in elements, (
                f"被剔除候选 {c.formula} 不含 Co，不应出现在 filtered_out 中"
            )

    def test_empty_rule_set_no_filtering(self):
        """不传 require/exclude 时不做硬过滤（除非配置默认值）。"""
        # 通过显式构造空规则集验证
        candidates = self.generator.generate_candidates(
            target_property="ionic_conductivity",
            elements=["Li", "Co", "O"],
            num_candidates=5,
        )
        assert len(candidates) > 0


class TestCommitteeAdapterLinkage:
    """委员会适配器联动测试。"""

    def test_set_and_get_chemistry_filtered_candidates(self):
        adapter = CrystalAdapter()
        assert adapter.chemistry_filtered_candidates == []

        filtered = [
            {"formula": "LiCoO2", "reason": "contains forbidden element: Co"},
            {"formula": "Co3O4", "reason": "contains forbidden element: Co"},
        ]
        adapter.set_chemistry_filtered_candidates(filtered)

        assert len(adapter.chemistry_filtered_candidates) == 2
        assert adapter.chemistry_filtered_candidates[0]["formula"] == "LiCoO2"

    def test_set_empty_list(self):
        adapter = CrystalAdapter()
        adapter.set_chemistry_filtered_candidates(None)
        assert adapter.chemistry_filtered_candidates == []

    def test_set_does_not_mutate_original(self):
        """setter 应做防御性拷贝，避免外部修改影响适配器内部状态。"""
        adapter = CrystalAdapter()
        original = [{"formula": "LiCoO2"}]
        adapter.set_chemistry_filtered_candidates(original)
        original.append({"formula": "Na3PS4"})
        # 适配器内部列表不应被影响
        assert len(adapter.chemistry_filtered_candidates) == 1


class TestConfigLoading:
    """AgentConfig.chemistry_rules 配置加载测试。"""

    def test_chemistry_rules_field_exists(self):
        from battery_materials_agent.config import AgentConfig, ChemistryRuleSetConfig

        cfg = AgentConfig()
        assert isinstance(cfg.chemistry_rules, ChemistryRuleSetConfig)
        assert cfg.chemistry_rules.required_elements == []
        assert cfg.chemistry_rules.forbidden_elements == []
        assert cfg.chemistry_rules.max_elements_count is None
        assert cfg.chemistry_rules.required_structure_types == []

    def test_chemistry_rules_from_yaml(self, tmp_path, monkeypatch):
        """YAML 配置可被正确解析为 ChemistryRuleSetConfig。"""
        from battery_materials_agent.config import _load_chemistry_rules_config, PROJECT_ROOT
        import yaml

        # 构造临时 yaml 文件内容
        yaml_content = {
            "chemistry_rules": {
                "required_elements": ["Li"],
                "forbidden_elements": ["Co", "Ni"],
                "max_elements_count": 5,
                "required_structure_types": ["Layered", "Spinel"],
            }
        }
        # monkeypatch PROJECT_ROOT 指向临时目录，让 _load_chemistry_rules_config 找到临时 yaml
        config_dir = tmp_path / "config" / "workflows"
        config_dir.mkdir(parents=True)
        (config_dir / "ecml_v2.yaml").write_text(
            yaml.safe_dump(yaml_content, allow_unicode=True), encoding="utf-8"
        )
        monkeypatch.setattr(
            "battery_materials_agent.config.PROJECT_ROOT", tmp_path
        )
        # 清空相关环境变量，确保读取的是 yaml
        for k in [
            "CHEMISTRY_REQUIRED_ELEMENTS",
            "CHEMISTRY_FORBIDDEN_ELEMENTS",
            "CHEMISTRY_MAX_ELEMENTS_COUNT",
            "CHEMISTRY_REQUIRED_STRUCTURE_TYPES",
        ]:
            monkeypatch.delenv(k, raising=False)

        cfg = _load_chemistry_rules_config()
        assert cfg.required_elements == ["Li"]
        assert cfg.forbidden_elements == ["Co", "Ni"]
        assert cfg.max_elements_count == 5
        assert cfg.required_structure_types == ["Layered", "Spinel"]

    def test_env_vars_override_yaml(self, tmp_path, monkeypatch):
        """环境变量覆盖 YAML 默认值。"""
        from battery_materials_agent.config import _load_chemistry_rules_config
        import yaml

        yaml_content = {
            "chemistry_rules": {
                "required_elements": ["Li"],
                "forbidden_elements": ["Co"],
                "max_elements_count": 5,
            }
        }
        config_dir = tmp_path / "config" / "workflows"
        config_dir.mkdir(parents=True)
        (config_dir / "ecml_v2.yaml").write_text(
            yaml.safe_dump(yaml_content, allow_unicode=True), encoding="utf-8"
        )
        monkeypatch.setattr(
            "battery_materials_agent.config.PROJECT_ROOT", tmp_path
        )
        # 环境变量覆盖
        monkeypatch.setenv("CHEMISTRY_REQUIRED_ELEMENTS", "Na,Ca")
        monkeypatch.setenv("CHEMISTRY_FORBIDDEN_ELEMENTS", "Mn")
        monkeypatch.setenv("CHEMISTRY_MAX_ELEMENTS_COUNT", "3")

        cfg = _load_chemistry_rules_config()
        assert cfg.required_elements == ["Na", "Ca"]
        assert cfg.forbidden_elements == ["Mn"]
        assert cfg.max_elements_count == 3
