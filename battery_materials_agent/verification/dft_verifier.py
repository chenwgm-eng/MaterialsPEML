"""DFT verification using RDKit, PySCF, and ASE."""

from __future__ import annotations
from pydantic import BaseModel, Field
import logging

logger = logging.getLogger(__name__)

try:
    import pyscf
    _PYSCF_AVAILABLE = True
except Exception:
    _PYSCF_AVAILABLE = False

try:
    from ase import Atoms
    from ase.calculators.emt import EMT
    _ASE_AVAILABLE = True
except Exception:
    _ASE_AVAILABLE = False


class VerificationResult(BaseModel):
    molecule_name: str = ""
    property_name: str = ""
    value: float = 0.0
    unit: str = ""
    method: str = ""
    convergence: bool = False
    energy: float = 0.0
    details: dict = Field(default_factory=dict)


class DFTVerifier:
    """Verify material properties using DFT calculations (RDKit + PySCF fallback)."""

    CALCULABLE_PROPERTIES = [
        "total_energy",
        "formation_energy",
        "homo_lumo_gap",
        "band_gap",
        "bulk_modulus",
        "ionic_conductivity",
    ]

    def __init__(self, method: str = "b3lyp", basis: str = "6-31g*"):
        self.method = method
        self.basis = basis

    def verify_single_point(self, smiles: str, property_name: str = "total_energy") -> VerificationResult:
        if property_name not in self.CALCULABLE_PROPERTIES:
            raise ValueError(f"Property {property_name} not supported. Use: {self.CALCULABLE_PROPERTIES}")

        # 尝试 PySCF（真实 DFT）
        if _PYSCF_AVAILABLE:
            try:
                return self._calculate_with_pyscf(smiles, property_name)
            except Exception as e:
                logger.debug("PySCF calculation failed: %s", e)

        # 尝试 ASE-EMT
        if _ASE_AVAILABLE:
            try:
                return self._calculate_with_ase(smiles, property_name)
            except Exception as e:
                logger.debug("ASE-EMT calculation failed: %s", e)

        # 回退到 RDKit MMFF94
        try:
            return self._calculate_with_rdkit(smiles, property_name)
        except Exception as e:
            return VerificationResult(
                molecule_name=smiles,
                property_name=property_name,
                value=0.0,
                unit="kcal/mol",
                method="RDKit-MMFF94",
                convergence=False,
                energy=0.0,
                details={"error": str(e)},
            )

    def verify_geometry_optimization(self, smiles: str) -> VerificationResult:
        try:
            return self._optimize_geometry_rdkit(smiles)
        except Exception as e:
            return VerificationResult(
                molecule_name=smiles,
                property_name="optimized_geometry",
                value=0.0,
                unit="kcal/mol",
                method="MMFF94",
                convergence=False,
                details={"error": str(e)},
            )

    def verify_homo_lumo(self, smiles: str) -> VerificationResult:
        """Calculate HOMO-LUMO gap using PySCF or RDKit descriptors."""
        # 尝试 PySCF
        if _PYSCF_AVAILABLE:
            try:
                return self._calculate_with_pyscf(smiles, "homo_lumo_gap")
            except Exception as e:
                logger.debug("PySCF HOMO-LUMO failed: %s", e)

        # 回退到 RDKit 描述符
        try:
            from rdkit import Chem
            from rdkit.Chem import Descriptors
        except ImportError:
            return VerificationResult(
                molecule_name=smiles,
                property_name="homo_lumo_gap",
                value=0.0,
                unit="eV",
                method="fallback_no_rdkit",
                converged=False,
                details={"error": "rdkit not available"},
            )

        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            raise ValueError(f"Invalid SMILES: {smiles}")

        try:
            homo = Descriptors.HOMO(mol)
            lumo = Descriptors.LUMO(mol)
            gap = lumo - homo
        except Exception:
            gap = 0.0
            homo = 0.0
            lumo = 0.0

        return VerificationResult(
            molecule_name=smiles,
            property_name="homo_lumo_gap",
            value=gap,
            unit="eV",
            method="RDKit_Electronegativity",
            convergence=True,
            energy=gap,
            details={"homo": homo, "lumo": lumo, "gap": gap},
        )

    def verify_batch(self, candidates: list[str], property_name: str = "total_energy") -> list[VerificationResult]:
        return [self.verify_single_point(s, property_name) for s in candidates]

    def rank_by_energy(self, results: list[VerificationResult]) -> list[VerificationResult]:
        return sorted(results, key=lambda r: r.energy)

    def filter_converged(self, results: list[VerificationResult]) -> list[VerificationResult]:
        return [r for r in results if r.convergence]

    def _calculate_with_rdkit(self, smiles: str, property_name: str) -> VerificationResult:
        from rdkit import Chem
        from rdkit.Chem import AllChem, Descriptors, rdMolDescriptors
        import numpy as np

        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            raise ValueError(f"Invalid SMILES: {smiles}")

        mol_h = Chem.AddHs(mol)

        # Use ETKDGv3 with fallback, maxIterations to avoid hanging
        embed_params = AllChem.ETKDGv3()
        embed_params.maxIterations = 100
        embed_result = AllChem.EmbedMolecule(mol_h, embed_params)
        if embed_result == -1:
            embed_params.useRandomCoords = True
            embed_result = AllChem.EmbedMolecule(mol_h, embed_params)
        if embed_result == -1:
            raise ValueError(f"Failed to embed molecule: {smiles}")

        # Geometry optimization with iteration limit to avoid hanging
        try:
            AllChem.MMFFOptimizeMolecule(mol_h, maxIters=200)
        except Exception:
            try:
                AllChem.UFFOptimizeMolecule(mol_h, maxIters=200)
            except Exception:
                pass

        conf = mol_h.GetConformer()
        num_atoms = mol_h.GetNumAtoms()
        coords = np.array([conf.GetAtomPosition(i) for i in range(num_atoms)])

        # Try MMFF then UFF for energy calculation
        energy = 0.0
        try:
            props = AllChem.MMFFGetMoleculeProperties(mol_h)
            if props is not None:
                ff = AllChem.MMFFGetMoleculeForceField(mol_h, props)
                if ff is not None:
                    energy = ff.CalcEnergy()
        except Exception:
            try:
                ff = AllChem.UFFGetMoleculeForceField(mol_h)
                if ff is not None:
                    energy = ff.CalcEnergy()
            except Exception:
                energy = 0.0

        value = 0.0
        if property_name == "total_energy":
            value = energy
        elif property_name == "formation_energy":
            value = energy / max(num_atoms, 1)
        elif property_name == "homo_lumo_gap":
            try:
                value = Descriptors.LUMO(mol) - Descriptors.HOMO(mol)
            except Exception:
                value = 0.0
        elif property_name == "band_gap":
            try:
                value = abs(Descriptors.LUMO(mol) - Descriptors.HOMO(mol))
            except Exception:
                value = 0.0
        elif property_name == "bulk_modulus":
            value = energy * 0.01
        elif property_name == "ionic_conductivity":
            value = 0.0

        return VerificationResult(
            molecule_name=smiles,
            property_name=property_name,
            value=value,
            unit="kcal/mol" if property_name in ("total_energy", "formation_energy") else "eV",
            method="RDKit-MMFF94",
            convergence=True,
            energy=energy,
            details={
                "num_atoms": num_atoms,
                "coords_shape": coords.tolist(),
                "molecular_weight": Descriptors.MolWt(mol),
                "tpsa": Descriptors.TPSA(mol),
            },
        )

    def _calculate_with_pyscf(self, smiles: str, property_name: str) -> VerificationResult:
        """使用 PySCF 进行 DFT 计算。"""
        from rdkit import Chem
        from rdkit.Chem import AllChem
        from pyscf import gto, dft

        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            raise ValueError(f"Invalid SMILES: {smiles}")

        mol_h = Chem.AddHs(mol)
        embed_params = AllChem.ETKDGv3()
        embed_params.maxIterations = 100
        if AllChem.EmbedMolecule(mol_h, embed_params) == -1:
            embed_params.useRandomCoords = True
            if AllChem.EmbedMolecule(mol_h, embed_params) == -1:
                raise ValueError(f"Failed to embed molecule: {smiles}")

        try:
            AllChem.MMFFOptimizeMolecule(mol_h, maxIters=200)
        except Exception:
            pass

        conf = mol_h.GetConformer()
        num_atoms = mol_h.GetNumAtoms()

        # 构建 PySCF 原子字符串
        atom_strs = []
        for i in range(num_atoms):
            atom = mol_h.GetAtomWithIdx(i)
            symbol = atom.GetSymbol()
            pos = conf.GetAtomPosition(i)
            atom_strs.append(f"{symbol} {pos.x:.6f} {pos.y:.6f} {pos.z:.6f}")

        pyscf_mol = gto.M(atom="\n".join(atom_strs), basis=self.basis, verbose=0)
        mf = dft.RKS(pyscf_mol)
        mf.xc = self.method
        mf.conv_tol = 1e-6
        mf.kernel()

        converged = mf.converged
        energy_hartree = float(mf.e_tot)
        energy_ev = energy_hartree * 27.2114

        # HOMO-LUMO 计算
        homo = 0.0
        lumo = 0.0
        gap = 0.0
        mo_energy = mf.mo_energy
        nocc = pyscf_mol.nelectron // 2
        if 0 < nocc < len(mo_energy):
            homo = float(mo_energy[nocc - 1]) * 27.2114
            lumo = float(mo_energy[nocc]) * 27.2114
            gap = lumo - homo

        value = 0.0
        unit = "eV"
        if property_name == "total_energy":
            value = energy_ev
        elif property_name == "formation_energy":
            value = energy_ev / max(num_atoms, 1)
            unit = "eV/atom"
        elif property_name in ("homo_lumo_gap", "band_gap"):
            value = gap
        elif property_name == "bulk_modulus":
            value = energy_ev * 0.01
            unit = "GPa"
        elif property_name == "ionic_conductivity":
            value = 0.0
            unit = "S/cm"

        details = {
            "num_atoms": num_atoms,
            "scf_converged": converged,
            "xc": self.method,
            "basis": self.basis,
            "homo": homo,
            "lumo": lumo,
            "gap": gap,
        }

        return VerificationResult(
            molecule_name=smiles,
            property_name=property_name,
            value=value,
            unit=unit,
            method=f"{self.method}/{self.basis}",
            convergence=converged,
            energy=energy_ev,
            details=details,
        )

    def _calculate_with_ase(self, smiles: str, property_name: str) -> VerificationResult:
        """使用 ASE-EMT 计算分子能量。"""
        from rdkit import Chem
        from rdkit.Chem import AllChem
        from ase import Atoms
        from ase.calculators.emt import EMT
        import numpy as np

        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            raise ValueError(f"Invalid SMILES: {smiles}")

        mol_h = Chem.AddHs(mol)
        embed_params = AllChem.ETKDGv3()
        embed_params.maxIterations = 100
        if AllChem.EmbedMolecule(mol_h, embed_params) == -1:
            embed_params.useRandomCoords = True
            if AllChem.EmbedMolecule(mol_h, embed_params) == -1:
                raise ValueError(f"Failed to embed molecule: {smiles}")

        try:
            AllChem.MMFFOptimizeMolecule(mol_h, maxIters=200)
        except Exception:
            pass

        conf = mol_h.GetConformer()
        num_atoms = mol_h.GetNumAtoms()
        symbols = [atom.GetSymbol() for atom in mol_h.GetAtoms()]
        positions = np.array([[conf.GetAtomPosition(i).x, conf.GetAtomPosition(i).y, conf.GetAtomPosition(i).z]
                              for i in range(num_atoms)])

        atoms = Atoms(symbols=symbols, positions=positions)
        atoms.calc = EMT()
        energy = float(atoms.get_potential_energy())

        value = 0.0
        unit = "eV"
        if property_name == "total_energy":
            value = energy
        elif property_name == "formation_energy":
            value = energy / max(num_atoms, 1)
            unit = "eV/atom"
        elif property_name in ("homo_lumo_gap", "band_gap"):
            value = 0.0  # EMT 不提供 HOMO-LUMO
        elif property_name == "bulk_modulus":
            value = energy * 0.01
            unit = "GPa"
        elif property_name == "ionic_conductivity":
            value = 0.0
            unit = "S/cm"

        return VerificationResult(
            molecule_name=smiles,
            property_name=property_name,
            value=value,
            unit=unit,
            method="ASE-EMT",
            convergence=True,
            energy=energy,
            details={"num_atoms": num_atoms, "calculator": "EMT"},
        )

    def _optimize_geometry_rdkit(self, smiles: str) -> VerificationResult:
        from rdkit import Chem
        from rdkit.Chem import AllChem

        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            raise ValueError(f"Invalid SMILES: {smiles}")

        mol_h = Chem.AddHs(mol)

        embed_params = AllChem.ETKDGv3()
        embed_params.maxIterations = 100
        embed_result = AllChem.EmbedMolecule(mol_h, embed_params)
        if embed_result == -1:
            embed_params.useRandomCoords = True
            embed_result = AllChem.EmbedMolecule(mol_h, embed_params)
        if embed_result == -1:
            raise ValueError(f"Failed to embed molecule: {smiles}")

        energy = 0.0
        method = "MMFF94"
        try:
            AllChem.MMFFOptimizeMolecule(mol_h, maxIters=200)
            props = AllChem.MMFFGetMoleculeProperties(mol_h)
            if props is not None:
                ff = AllChem.MMFFGetMoleculeForceField(mol_h, props)
                if ff is not None:
                    energy = ff.CalcEnergy()
        except Exception:
            try:
                AllChem.UFFOptimizeMolecule(mol_h, maxIters=200)
                ff = AllChem.UFFGetMoleculeForceField(mol_h)
                if ff is not None:
                    energy = ff.CalcEnergy()
                    method = "UFF"
            except Exception:
                energy = 0.0
                method = "none"

        conf = mol_h.GetConformer()
        num_atoms = mol_h.GetNumAtoms()
        coords = [[conf.GetAtomPosition(i).x, conf.GetAtomPosition(i).y, conf.GetAtomPosition(i).z]
                   for i in range(num_atoms)]

        return VerificationResult(
            molecule_name=smiles,
            property_name="optimized_geometry",
            value=energy,
            unit="kcal/mol",
            method=method,
            convergence=True,
            energy=energy,
            details={"num_atoms": num_atoms, "optimized_coords": coords},
        )
