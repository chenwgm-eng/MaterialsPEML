"""Tests for DFT verification module."""

import pytest
from battery_materials_agent.verification.dft_verifier import DFTVerifier, VerificationResult


class TestDFTVerifier:
    def setup_method(self):
        self.verifier = DFTVerifier(method="b3lyp", basis="6-31g*")

    def test_verify_single_point(self):
        result = self.verifier.verify_single_point("CCO", "total_energy")
        assert isinstance(result, VerificationResult)
        assert result.molecule_name == "CCO"
        assert result.property_name == "total_energy"
        # v4.0: method 反映实际使用的计算方法（PySCF→ASE-EMT→RDKit 回退链）
        assert result.method in ("b3lyp/6-31g*", "ASE-EMT", "RDKit-MMFF94")

    def test_verify_single_point_invalid_smiles(self):
        result = self.verifier.verify_single_point("invalid", "total_energy")
        assert result.convergence is False

    def test_verify_unsupported_property(self):
        with pytest.raises(ValueError):
            self.verifier.verify_single_point("CCO", "unsupported")

    def test_verify_geometry_optimization(self):
        result = self.verifier.verify_geometry_optimization("c1ccccc1")
        assert result.property_name == "optimized_geometry"
        assert isinstance(result, VerificationResult)

    def test_verify_batch(self):
        results = self.verifier.verify_batch(["CCO", "CC(=O)O"], "total_energy")
        assert len(results) == 2

    def test_rank_by_energy(self):
        results = [
            VerificationResult(molecule_name="A", energy=-10.0),
            VerificationResult(molecule_name="B", energy=-5.0),
            VerificationResult(molecule_name="C", energy=-15.0),
        ]
        ranked = self.verifier.rank_by_energy(results)
        assert ranked[0].molecule_name == "C"
        assert ranked[-1].molecule_name == "B"

    def test_filter_converged(self):
        results = [
            VerificationResult(molecule_name="A", convergence=True),
            VerificationResult(molecule_name="B", convergence=False),
        ]
        converged = self.verifier.filter_converged(results)
        assert len(converged) == 1
        assert converged[0].molecule_name == "A"

    def test_verification_result_fields(self):
        result = VerificationResult(
            molecule_name="CCO",
            property_name="total_energy",
            value=-154.0,
            unit="Ha",
            method="b3lyp/6-31g*",
            convergence=True,
            energy=-154.0,
        )
        assert result.value == -154.0
        assert result.convergence is True
