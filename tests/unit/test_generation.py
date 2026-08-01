"""Tests for candidate generation modules."""

import pytest
from battery_materials_agent.generation.crystal_candidate_generator import (
    CrystalCandidateGenerator, CrystalCandidate,
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
        candidates = self.generator.search_gnome(num_results=5)
        assert len(candidates) > 0


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
