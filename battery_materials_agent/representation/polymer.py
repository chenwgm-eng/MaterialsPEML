"""Polymer structure representation using PSMILES and RDKit."""

from pydantic import BaseModel, Field
import numpy as np

try:
    from rdkit import Chem
    from rdkit.Chem import Descriptors, AllChem
    _RDKIT_AVAILABLE = True
except ImportError:
    _RDKIT_AVAILABLE = False
    Chem = None  # type: ignore
    Descriptors = None  # type: ignore
    AllChem = None  # type: ignore


class PolymerFeatures(BaseModel):
    psmiles: str = ""
    smiles: str = ""
    num_heavy_atoms: int = 0
    molecular_weight: float = 0.0
    tpsa: float = 0.0
    num_rotatable_bonds: int = 0
    num_hbd: int = 0
    num_hba: int = 0
    fingerprint: list[int] = Field(default_factory=list)


class PolymerRepresentation:
    """Parse and encode polymer structures from PSMILES/SMILES."""

    def from_psmiles(self, psmiles: str) -> PolymerFeatures:
        if not psmiles or not psmiles.startswith("Polymer"):
            raise ValueError(f"Invalid PSMILES: {psmiles}")

        canonical = self._canonicalize_psmiles(psmiles)
        return PolymerFeatures(psmiles=canonical)

    def from_smiles(self, smiles: str) -> PolymerFeatures:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            raise ValueError(f"Invalid SMILES: {smiles}")

        fp = AllChem.GetMorganFingerprintAsBitVect(mol, 2, nBits=1024)
        fp_list = [int(x) for x in fp.ToBitString()]

        return PolymerFeatures(
            smiles=smiles,
            num_heavy_atoms=mol.GetNumHeavyAtoms(),
            molecular_weight=Descriptors.MolWt(mol),
            tpsa=Descriptors.TPSA(mol),
            num_rotatable_bonds=Descriptors.NumRotatableBonds(mol),
            num_hbd=Descriptors.NumHDonors(mol),
            num_hba=Descriptors.NumHAcceptors(mol),
            fingerprint=fp_list,
        )

    def _canonicalize_psmiles(self, psmiles: str) -> str:
        """规范化 PSMILES，使用 RDKit 规范化主链后还原占位符"""
        import re
        psmiles = psmiles.replace(" ", "").strip()
        try:
            # 将所有聚合物占位符 [*]、[*:1]、[*:2]... 统一替换为虚拟原子 [Xe]
            temp_smiles = re.sub(r'\[\*(:\d+)?\]', '[Xe]', psmiles)
            mol = Chem.MolFromSmiles(temp_smiles)
            if mol is not None:
                canonical = Chem.MolToSmiles(mol)
                # 还原占位符（使用 [*] 作为统一占位符）
                canonical = canonical.replace("[Xe]", "[*]")
                return canonical
        except Exception:
            pass
        return psmiles

    def get_fingerprint_array(self, features: PolymerFeatures) -> np.ndarray:
        if features.fingerprint:
            return np.array(features.fingerprint, dtype=np.float32)
        if features.smiles:
            mol = Chem.MolFromSmiles(features.smiles)
            if mol is not None:
                fp = AllChem.GetMorganFingerprintAsBitVect(mol, 2, nBits=1024)
                return np.array([int(x) for x in fp.ToBitString()], dtype=np.float32)
        return np.zeros(1024, dtype=np.float32)

    def batch_fingerprints(self, features_list: list[PolymerFeatures]) -> np.ndarray:
        return np.array([self.get_fingerprint_array(f) for f in features_list])
