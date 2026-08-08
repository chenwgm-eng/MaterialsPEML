"""Tests for candidate generation modules."""

from unittest import mock

import pytest
from battery_materials_agent.generation.crystal_candidate_generator import (
    CrystalCandidateGenerator, CrystalCandidate,
    _extract_elements,
)
from battery_materials_agent.generation.polymer_candidate_generator import (
    PolymerCandidateGenerator, PolymerCandidate,
)


class TestCrystalCandidateGenerator:
    def setup_method(self):
        self.generator = CrystalCandidateGenerator(api_key="")

    def test_search_materials_project_no_api(self):
        candidates = self.generator.search_materials_project(elements=["Li", "Co"])
        assert len(candidates) > 0
        assert all(isinstance(c, CrystalCandidate) for c in candidates)

    def test_search_materials_project_formula(self):
        candidates = self.generator.search_materials_project(formula="LiCoO2")
        assert len(candidates) > 0
        assert any("LiCoO2" in c.formula for c in candidates)

    def test_generate_candidates(self):
        # elements 采用严格子集语义：仅返回由这些元素组成的材料。
        # 使用 Li-Co-O 体系可覆盖 LiCoO2、Li2CoO3、Co3O4、CoO、Li2O 等候选。
        candidates = self.generator.generate_candidates(elements=["Li", "Co", "O"], num_candidates=10)
        assert len(candidates) > 0
        assert len(candidates) <= 10

    def test_generate_candidates_strict_element_subset(self):
        # 严格子集：即使 LLM 元素解析未覆盖某个化学式，该候选也必须被过滤，
        # 不得因空集合（空集 ⊂ 任意 allowed）而绕过过滤泄漏进结果。
        allowed = {"Li", "Co", "O"}
        # 构造 LLM 返回 dict，故意缺失含 F 的候选公式，验证回退 pymatgen 过滤生效
        llm_result = {"LiCoO2": {"Li", "Co", "O"}, "Li2O": {"Li", "O"}}
        with mock.patch(
            "battery_materials_agent.generation.crystal_candidate_generator._extract_elements_with_llm",
            return_value=llm_result,
        ):
            candidates = self.generator.generate_candidates(elements=list(allowed), num_candidates=10)
        assert len(candidates) > 0
        for c in candidates:
            # 任何候选元素必须是 allowed 的子集（无额外元素）
            assert _extract_elements(c.formula).issubset(allowed), \
                f"候选 {c.formula} 含目标元素集之外的元素"

    def test_crystal_candidate_fields(self):
        candidate = CrystalCandidate(
            formula="LiCoO2",
            structure_type="Trigonal",
            space_group="R-3m",
            energy_above_hull=0.0,
            band_gap=2.1,
            source="materials_project",
        )
        assert candidate.formula == "LiCoO2"
        assert candidate.source == "materials_project"

    def test_search_gnome(self):
        # 无真实数据源命中（PG 查询返回空、无本地文件、无 API key）时返回空，
        # 不做硬编码伪数据回退。真实 GNoME 已导入统一 PG，故 mock 查询返回空来模拟。
        with mock.patch.object(self.generator._gnome_db, "search", return_value=[]):
            candidates = self.generator.search_gnome(num_results=5)
        assert candidates == []

    def test_search_gnome_from_pg(self):
        # 统一 PostgreSQL 真实数据源命中时返回候选
        row = {
            "formula": "LiCoO2", "reduced_formula": "LiCoO2",
            "space_group": "R-3m", "structure_type": "Trigonal",
            "energy_above_hull": 0.0, "band_gap": 2.1,
            "formation_energy": -2.5, "material_id": "mp-1",
            "ionic_conductivity": 0.0, "elements": ["Co", "Li", "O"],
            "source": "gnome_pg",
        }
        with mock.patch.object(self.generator._gnome_db, "search", return_value=[row]):
            candidates = self.generator.search_gnome(num_results=5)
        assert len(candidates) == 1
        assert candidates[0].source == "gnome_pg"


class TestPolymerCandidateGenerator:
    def setup_method(self):
        self.generator = PolymerCandidateGenerator(llm_api_key="")

    def test_generate_default(self):
        candidates = self.generator.generate(num_candidates=10)
        assert len(candidates) > 0
        assert all(isinstance(c, PolymerCandidate) for c in candidates)

    def test_known_polymers(self):
        assert len(self.generator.KNOWN_POLYMERS) >= 5
        names = [p.name for p in self.generator.KNOWN_POLYMERS]
        assert "Poly(ethylene oxide)" in names
        assert "Poly(vinylidene fluoride)" in names

    def test_generate_derivatives(self):
        base = self.generator.KNOWN_POLYMERS[0]
        variants = self.generator.generate_derivatives(base, num_variants=3)
        assert len(variants) == 3
        for v in variants:
            assert "Poly(ethylene oxide)" in v.name

    def test_filter_by_rules(self):
        candidates = self.generator.KNOWN_POLYMERS
        rules = {"required_groups": ["ester"], "require_all": False}
        filtered = self.generator.filter_by_rules(candidates, rules)
        assert isinstance(filtered, list)

    def test_polymer_candidate_fields(self):
        candidate = PolymerCandidate(
            name="Test Polymer",
            psmiles="Polymer([*]CCO[*])",
            smiles="CCO",
            source="known",
        )
        assert candidate.name == "Test Polymer"
        assert candidate.psmiles == "Polymer([*]CCO[*])"
