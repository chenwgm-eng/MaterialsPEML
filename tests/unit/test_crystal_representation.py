"""Tests for crystal structure representation."""

import pytest
from battery_materials_agent.representation.crystal import CrystalRepresentation, CrystalFeatures


class TestCrystalRepresentation:
    def setup_method(self):
        self.repr = CrystalRepresentation()

    def test_from_formula(self):
        features = self.repr.from_formula("LiCoO2")
        assert features.formula == "LiCoO2"
        assert "Li" in features.elements
        assert "Co" in features.elements
        assert "O" in features.elements

    def test_from_formula_multiple(self):
        features = self.repr.from_formula("Li7La3Zr2O12")
        assert features.formula == "Li7La3Zr2O12"
        assert len(features.elements) > 0

    def test_from_cif_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            self.repr.from_cif("nonexistent.cif")

    def test_crystal_features_fields(self):
        features = CrystalFeatures(
            formula="LiCoO2",
            space_group="R-3m",
            lattice_params={"a": 2.8, "b": 2.8, "c": 14.0},
            num_sites=4,
            density=5.0,
            elements=["Li", "Co", "O"],
        )
        assert features.formula == "LiCoO2"
        assert features.space_group == "R-3m"
        assert features.num_sites == 4
        assert len(features.elements) == 3

    def test_cache_structure(self):
        assert self.repr.get_structure("nonexistent") is None
