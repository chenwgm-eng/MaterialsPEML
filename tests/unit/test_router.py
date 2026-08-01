"""Tests for the material router."""

import pytest
from battery_materials_agent.router.router import (
    MaterialRouter, MaterialInput, MaterialType, MaterialBranch, RouterResult,
)


class TestMaterialRouter:
    def setup_method(self):
        self.router = MaterialRouter()

    def test_route_psmiles(self):
        result = self.router.route(MaterialInput(psmiles="Polymer([*]CCO[*])"))
        assert result.material_type == MaterialType.POLYMER
        assert result.branch == MaterialBranch.POLYMER_BRANCH
        assert result.confidence >= 0.9

    def test_route_cif(self):
        result = self.router.route(MaterialInput(cif_path="/path/to/structure.cif"))
        assert result.material_type == MaterialType.CRYSTAL
        assert result.branch == MaterialBranch.CRYSTAL_BRANCH

    def test_route_poscar(self):
        result = self.router.route(MaterialInput(poscar="some poscar content"))
        assert result.material_type == MaterialType.CRYSTAL
        assert result.branch == MaterialBranch.CRYSTAL_BRANCH

    def test_route_smiles_small_molecule(self):
        result = self.router.route(MaterialInput(smiles="CCO"))
        assert result.material_type == MaterialType.ORGANIC
        assert result.branch == MaterialBranch.ORGANIC_BRANCH

    def test_route_hint_crystal(self):
        result = self.router.route(MaterialInput(material_type_hint=MaterialType.CRYSTAL))
        assert result.material_type == MaterialType.CRYSTAL
        assert result.branch == MaterialBranch.CRYSTAL_BRANCH
        assert result.confidence == 0.6

    def test_route_hint_polymer(self):
        result = self.router.route(MaterialInput(material_type_hint=MaterialType.POLYMER))
        assert result.material_type == MaterialType.POLYMER
        assert result.branch == MaterialBranch.POLYMER_BRANCH

    def test_route_keyword_polymer(self):
        result = self.router.route(MaterialInput(name="PEO-based electrolyte"))
        assert result.material_type == MaterialType.POLYMER
        assert result.branch == MaterialBranch.POLYMER_BRANCH

    def test_route_keyword_crystal(self):
        result = self.router.route(MaterialInput(name="spinel structure"))
        assert result.material_type == MaterialType.CRYSTAL
        assert result.branch == MaterialBranch.CRYSTAL_BRANCH

    def test_route_default_crystal(self):
        result = self.router.route(MaterialInput())
        assert result.material_type == MaterialType.CRYSTAL
        assert result.confidence == 0.5

    def test_route_empty_input(self):
        result = self.router.route(MaterialInput(name=""))
        assert result.material_type == MaterialType.CRYSTAL

    def test_route_invalid_smiles(self):
        result = self.router.route(MaterialInput(smiles="invalid_smiles_XXX"))
        assert result.material_type == MaterialType.CRYSTAL

    def test_route_result_fields(self):
        result = self.router.route(MaterialInput(smiles="CCO"))
        assert isinstance(result, RouterResult)
        assert hasattr(result, "material_type")
        assert hasattr(result, "branch")
        assert hasattr(result, "confidence")
        assert hasattr(result, "reason")
