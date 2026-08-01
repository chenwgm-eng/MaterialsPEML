"""Tests for polymer structure representation."""

import pytest
import numpy as np
from battery_materials_agent.representation.polymer import PolymerRepresentation, PolymerFeatures


class TestPolymerRepresentation:
    def setup_method(self):
        self.repr = PolymerRepresentation()

    def test_from_smiles_ethanol(self):
        features = self.repr.from_smiles("CCO")
        assert features.smiles == "CCO"
        assert features.num_heavy_atoms == 3
        assert features.molecular_weight > 0
        assert len(features.fingerprint) == 1024

    def test_from_smiles_invalid(self):
        with pytest.raises(ValueError):
            self.repr.from_smiles("invalid_smiles")

    def test_from_psmiles(self):
        features = self.repr.from_psmiles("Polymer([*]CCO[*])")
        assert features.psmiles == "Polymer([*]CCO[*])"

    def test_from_psmiles_invalid(self):
        with pytest.raises(ValueError):
            self.repr.from_psmiles("not_polymer")

    def test_get_fingerprint_array(self):
        features = self.repr.from_smiles("CCO")
        fp = self.repr.get_fingerprint_array(features)
        assert isinstance(fp, np.ndarray)
        assert fp.shape == (1024,)

    def test_batch_fingerprints(self):
        features_list = [
            self.repr.from_smiles("CCO"),
            self.repr.from_smiles("CC(=O)O"),
        ]
        batch = self.repr.batch_fingerprints(features_list)
        assert batch.shape == (2, 1024)

    def test_polymer_features_fields(self):
        features = PolymerFeatures(
            psmiles="Polymer([*]CCO[*])",
            smiles="CCO",
            num_heavy_atoms=3,
            molecular_weight=46.07,
            tpsa=20.23,
        )
        assert features.psmiles == "Polymer([*]CCO[*])"
        assert features.molecular_weight == 46.07
