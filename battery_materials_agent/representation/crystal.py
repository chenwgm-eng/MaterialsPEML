"""Crystal structure representation using pymatgen."""

from __future__ import annotations
from pathlib import Path
from pydantic import BaseModel, Field

try:
    from pymatgen.core import Structure
    from pymatgen.io.cif import CifParser
    _PYMATGEN_AVAILABLE = True
except ImportError:
    _PYMATGEN_AVAILABLE = False
    Structure = None  # type: ignore
    CifParser = None  # type: ignore


class CrystalFeatures(BaseModel):
    formula: str = ""
    space_group: str = ""
    lattice_params: dict[str, float] = Field(default_factory=dict)
    num_sites: int = 0
    density: float = 0.0
    elements: list[str] = Field(default_factory=list)
    coordination_numbers: dict[str, float] = Field(default_factory=dict)
    structure_index: int = 0


class CrystalRepresentation:
    """Parse and encode crystal structures from CIF/POSCAR."""

    def __init__(self):
        self._cache: dict[str, Structure] = {}

    def from_cif(self, cif_path: str) -> CrystalFeatures:
        path = Path(cif_path)
        if not path.exists():
            raise FileNotFoundError(f"CIF file not found: {cif_path}")

        parser = CifParser(str(path))
        structures = parser.get_structures()
        if not structures:
            raise ValueError(f"No structures found in CIF file: {cif_path}")

        structure = structures[0]
        self._cache[str(path)] = structure
        return self._extract_features(structure)

    def from_poscar(self, poscar_content: str) -> CrystalFeatures:
        from pymatgen.io.vasp import Poscar
        structure = Poscar.from_str(poscar_content).structure
        return self._extract_features(structure)

    def from_formula(self, formula: str) -> CrystalFeatures:
        from pymatgen.core import Composition
        comp = Composition(formula)
        elements = [str(e) for e in comp.elements]
        return CrystalFeatures(
            formula=formula,
            elements=elements,
            num_sites=sum(comp.values()),
        )

    def from_structure(self, structure: Structure) -> CrystalFeatures:
        return self._extract_features(structure)

    def _extract_features(self, structure: Structure) -> CrystalFeatures:
        lattice = structure.lattice
        lattice_params = {
            "a": lattice.a,
            "b": lattice.b,
            "c": lattice.c,
            "alpha": lattice.alpha,
            "beta": lattice.beta,
            "gamma": lattice.gamma,
        }
        elements = list({str(site.specie) for site in structure})
        formula = structure.composition.reduced_formula

        try:
            sg = structure.get_space_group_info()[1]
        except Exception:
            sg = "Unknown"

        coord_numbers = self._calc_coordination_numbers(structure)

        return CrystalFeatures(
            formula=formula,
            space_group=sg,
            lattice_params=lattice_params,
            num_sites=len(structure),
            density=structure.density,
            elements=elements,
            coordination_numbers=coord_numbers,
        )

    def _calc_coordination_numbers(self, structure: Structure) -> dict[str, float]:
        """使用 CrystalNN 计算各元素平均配位数"""
        try:
            from pymatgen.analysis.local_env import CrystalNN
            cnn = CrystalNN()
            element_cn: dict[str, list[float]] = {}
            for i, site in enumerate(structure):
                element = site.specie.symbol
                try:
                    cn = cnn.get_cn(structure, i)
                    element_cn.setdefault(element, []).append(float(cn))
                except Exception:
                    continue
            return {
                elem: round(sum(cns) / len(cns), 2)
                for elem, cns in element_cn.items()
                if cns
            }
        except Exception:
            return {}

    def to_poscar(self, structure: Structure) -> str:
        from pymatgen.io.vasp import Poscar
        return Poscar(structure).__str__()

    def get_structure(self, key: str) -> Structure | None:
        return self._cache.get(key)
