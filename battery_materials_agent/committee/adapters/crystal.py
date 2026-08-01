"""Crystal construction committee adapter — evidence collection for crystal candidates."""

from __future__ import annotations

import math
import logging

logger = logging.getLogger(__name__)


class CrystalAdapter:
    """Adapter for crystal construction committee evidence collection.

    Provides evidence items for the crystal construction committee by
    running structure validation, symmetry checks, pre-relaxation,
    and novelty checks. Gracefully handles missing dependencies
    (pymatgen, spglib, M3GNet).
    """

    def __init__(self, min_distance_threshold: float = 0.5):
        self.min_distance_threshold = min_distance_threshold
        # Task 15：规则引擎硬过滤剔除的候选列表（由候选生成阶段填充），
        # 委员会评估时作为决策参考——委员会做软评分，规则引擎已做硬过滤。
        self.chemistry_filtered_candidates: list[dict] = []

    def set_chemistry_filtered_candidates(self, candidates: list[dict]) -> None:
        """Task 15：注入被化学规则引擎硬过滤剔除的候选列表。

        在候选生成阶段调用 ``CrystalCandidateGenerator.generate_candidates()`` 后，
        将 ``get_last_chemistry_filtered_out()`` 返回的候选（序列化为 dict）传入此处，
        委员会评估时可读取 ``self.chemistry_filtered_candidates`` 作为决策参考：
        了解哪些候选因化学约束被排除，避免在软评分中重复争议。
        """
        self.chemistry_filtered_candidates = list(candidates) if candidates else []

    # ── structure_validity ────────────────────────────────────

    def validate_structure(self, structure_data: dict) -> dict:
        """Validate crystal structure using pymatgen.

        Hard constraints:
        - Positive cell volume
        - Coordinates are finite and can be normalized to [0,1)
        - Stoichiometry matches
        - Minimum periodic interatomic distance > threshold (default 0.5Å)
        - Lattice is non-singular

        Returns: {passed, blocking_reasons, warnings, details}
        """
        try:
            import pymatgen  # noqa: F401
            return self._validate_with_pymatgen(structure_data)
        except ImportError:
            logger.debug("pymatgen not available, using basic structure checks")
            return self._validate_basic(structure_data)

    def _validate_with_pymatgen(self, data: dict) -> dict:
        from pymatgen.core import Structure, Lattice, Composition

        blocking_reasons: list[str] = []
        warnings: list[str] = []
        details: dict = {}

        try:
            lattice = data.get("lattice")
            species = data.get("species", [])
            coords = data.get("coords", [])
            coords_are_cartesian = data.get("coords_are_cartesian", False)
            formula = data.get("formula", "")

            if lattice is None:
                blocking_reasons.append("No lattice matrix provided")
                return {"passed": False, "blocking_reasons": blocking_reasons, "warnings": warnings, "details": details}

            pymat_lattice = Lattice(lattice)

            # Check volume > 0
            volume = pymat_lattice.volume
            details["volume"] = volume
            if volume <= 0:
                blocking_reasons.append(f"Non-positive cell volume: {volume:.4f} Å³")
            elif volume < 1.0:
                warnings.append(f"Very small cell volume: {volume:.4f} Å³")

            # Check lattice is non-singular
            import numpy as np
            if abs(np.linalg.det(pymat_lattice.matrix)) < 1e-8:
                blocking_reasons.append("Singular lattice matrix (determinant near zero)")

            if not species or not coords or len(species) != len(coords):
                blocking_reasons.append("Species and coordinates length mismatch")
                return {"passed": False, "blocking_reasons": blocking_reasons, "warnings": warnings, "details": details}

            # Don't attempt structure construction if lattice is already invalid
            if blocking_reasons:
                return {"passed": False, "blocking_reasons": blocking_reasons, "warnings": warnings, "details": details}

            # Build structure
            try:
                struct = Structure(
                    pymat_lattice, species, coords,
                    coords_are_cartesian=coords_are_cartesian,
                )
            except Exception as e:
                blocking_reasons.append(f"Failed to build pymatgen Structure: {e}")
                return {"passed": False, "blocking_reasons": blocking_reasons, "warnings": warnings, "details": details}

            # Check coordinates are finite
            for site in struct:
                if not all(math.isfinite(v) for v in site.frac_coords):
                    blocking_reasons.append(f"Non-finite coordinates for {site.species_string}")
                    break

            # Check stoichiometry
            if formula:
                try:
                    struct_formula = struct.composition.reduced_formula
                    expected_formula = Composition(formula).reduced_formula
                    if struct_formula != expected_formula:
                        warnings.append(
                            f"Stoichiometry mismatch: structure={struct_formula}, expected={expected_formula}"
                        )
                    details["formula"] = struct_formula
                except Exception:
                    details["formula"] = struct.composition.reduced_formula

            # Check minimum distance
            try:
                if len(struct) < 2:
                    details["min_distance"] = None
                else:
                    min_dist = min(
                        struct.get_distance(i, j)
                        for i in range(len(struct))
                        for j in range(i + 1, len(struct))
                    )
                    details["min_distance"] = round(min_dist, 4)
                    if min_dist < self.min_distance_threshold:
                        blocking_reasons.append(
                            f"Minimum interatomic distance {min_dist:.4f}Å below threshold {self.min_distance_threshold}Å"
                        )
            except Exception:
                warnings.append("Could not compute minimum interatomic distance")

            details["num_sites"] = len(struct)
            details["space_group"] = struct.get_space_group_info()[0] if len(struct) > 0 else ""

        except Exception as e:
            blocking_reasons.append(f"Structure validation error: {e}")

        passed = len(blocking_reasons) == 0
        return {
            "passed": passed,
            "blocking_reasons": blocking_reasons,
            "warnings": warnings,
            "details": details,
        }

    def _validate_basic(self, data: dict) -> dict:
        """Basic structure validation without pymatgen."""
        blocking_reasons: list[str] = []
        warnings: list[str] = []
        details: dict = {}

        lattice = data.get("lattice")
        species = data.get("species", [])
        coords = data.get("coords", [])
        formula = data.get("formula", "")

        if lattice is None:
            blocking_reasons.append("No lattice matrix provided")
        else:
            # Basic lattice checks
            try:
                if len(lattice) != 3 or any(len(row) != 3 for row in lattice):
                    blocking_reasons.append("Lattice must be a 3x3 matrix")
                else:
                    # Compute volume via determinant
                    a, b, c = lattice
                    det = (
                        a[0] * (b[1] * c[2] - b[2] * c[1])
                        - a[1] * (b[0] * c[2] - b[2] * c[0])
                        + a[2] * (b[0] * c[1] - b[1] * c[0])
                    )
                    details["volume"] = abs(det)
                    if abs(det) <= 0:
                        blocking_reasons.append("Non-positive cell volume")
                    elif abs(det) < 1e-8:
                        blocking_reasons.append("Singular lattice matrix")
            except Exception:
                blocking_reasons.append("Invalid lattice matrix format")

        # Check species and coordinates
        if not species:
            blocking_reasons.append("No species provided")
        if not coords:
            blocking_reasons.append("No coordinates provided")
        if species and coords and len(species) != len(coords):
            blocking_reasons.append("Species and coordinates length mismatch")

        # Check coordinates are finite
        try:
            for i, coord in enumerate(coords):
                if len(coord) != 3:
                    warnings.append(f"Coordinate {i} is not 3D")
                elif not all(math.isfinite(v) for v in coord):
                    blocking_reasons.append(f"Non-finite coordinates at position {i}")
        except Exception:
            warnings.append("Could not validate coordinate values")

        # Check minimum interatomic distance (periodic)
        if species and coords and len(species) >= 2 and lattice is not None:
            try:
                import numpy as np
                lattice_arr = np.array(lattice, dtype=float)
                coords_arr = np.array(coords, dtype=float)
                coords_are_cartesian = data.get("coords_are_cartesian", False)
                if coords_are_cartesian:
                    inv_lattice = np.linalg.inv(lattice_arr)
                    frac_coords = np.dot(coords_arr, inv_lattice.T)
                else:
                    frac_coords = coords_arr
                min_dist = float("inf")
                for i in range(len(frac_coords)):
                    for j in range(i + 1, len(frac_coords)):
                        frac_diff = frac_coords[j] - frac_coords[i]
                        frac_diff = frac_diff - np.round(frac_diff)
                        cart_diff = np.dot(frac_diff, lattice_arr)
                        dist = float(np.linalg.norm(cart_diff))
                        if dist < min_dist:
                            min_dist = dist
                details["min_distance"] = round(min_dist, 4)
                if min_dist < self.min_distance_threshold:
                    blocking_reasons.append(
                        f"Minimum interatomic distance {min_dist:.4f}Å below threshold {self.min_distance_threshold}Å"
                    )
            except Exception:
                warnings.append("Could not compute minimum interatomic distance")

        details["num_sites"] = len(species) if species else 0
        details["formula"] = formula

        passed = len(blocking_reasons) == 0
        return {
            "passed": passed,
            "blocking_reasons": blocking_reasons,
            "warnings": warnings,
            "details": details,
        }

    # ── symmetry ──────────────────────────────────────────────

    def check_symmetry(self, structure_data: dict) -> dict:
        """Check space group symmetry using spglib if available.

        Space group mismatch → warning, not rejection.
        Returns: {space_group, matches_model, warnings}
        """
        try:
            import spglib
            return self._check_symmetry_with_spglib(structure_data)
        except ImportError:
            logger.debug("spglib not available, symmetry check skipped")
            return {"space_group": "", "matches_model": False, "warnings": ["spglib not available"]}

    def _check_symmetry_with_spglib(self, data: dict) -> dict:
        warnings: list[str] = []
        space_group = ""
        matches_model = False

        try:
            lattice = data.get("lattice")
            species = data.get("species", [])
            coords = data.get("coords", [])
            coords_are_cartesian = data.get("coords_are_cartesian", False)
            expected_sg = data.get("space_group", "")

            if lattice is None or not species or not coords:
                warnings.append("Insufficient data for symmetry analysis")
                return {"space_group": "", "matches_model": False, "warnings": warnings}

            # Map species to atomic numbers
            from spglib import get_symmetry_dataset

            atomic_numbers = self._species_to_atomic_numbers(species)
            # Convert cartesian to fractional coordinates for spglib
            if coords_are_cartesian and lattice is not None:
                import numpy as np
                inv_lattice = np.linalg.inv(lattice)
                frac_coords = np.dot(coords, inv_lattice.T)
                cell = (lattice, frac_coords, atomic_numbers)
            else:
                cell = (lattice, coords, atomic_numbers)

            dataset = get_symmetry_dataset(cell, symprec=1e-5)
            if dataset is not None:
                space_group = dataset.get("international", "")
                sg_number = dataset.get("number", 0)
                if expected_sg and str(space_group) != str(expected_sg):
                    warnings.append(
                        f"Space group mismatch: computed={space_group}(#{sg_number}), expected={expected_sg}"
                    )
                else:
                    matches_model = True
            else:
                warnings.append("spglib could not determine space group")

        except Exception as e:
            warnings.append(f"Symmetry analysis error: {e}")

        return {"space_group": str(space_group), "matches_model": matches_model, "warnings": warnings}

    # ── pre_relax ─────────────────────────────────────────────

    def pre_relax(self, structure_data: dict) -> dict:
        """Run M3GNet pre-relaxation if available.

        Returns: {completed, energy, forces, structure_changes, error}
        """
        try:
            from matgl.ext.ase import M3GNetCalculator
            from ase import Atoms
            from ase.optimize import BFGS

            return self._relax_with_m3gnet(structure_data)
        except ImportError:
            logger.debug("M3GNet or ASE not available, pre-relaxation skipped")
            return {
                "completed": False,
                "energy": None,
                "forces": [],
                "structure_changes": {},
                "error": "M3GNet/ASE not available",
            }

    def _relax_with_m3gnet(self, data: dict) -> dict:
        try:
            from matgl.ext.ase import M3GNetCalculator
            from ase import Atoms
            from ase.optimize import BFGS

            species = data.get("species", [])
            coords = data.get("coords", [])
            lattice = data.get("lattice")
            coords_are_cartesian = data.get("coords_are_cartesian", False)

            if not species or not coords or lattice is None:
                return {
                    "completed": False,
                    "energy": None,
                    "forces": [],
                    "structure_changes": {},
                    "error": "Insufficient structure data for relaxation",
                }

            if not coords_are_cartesian and lattice is not None:
                import numpy as np
                cart_coords = np.dot(coords, lattice)
            else:
                cart_coords = coords
            atoms = Atoms(symbols=species, positions=cart_coords, cell=lattice, pbc=True)

            calc = M3GNetCalculator()
            atoms.calc = calc

            initial_energy = atoms.get_potential_energy()
            optimizer = BFGS(atoms)
            optimizer.run(fmax=0.05, steps=50)

            final_energy = atoms.get_potential_energy()
            final_forces = atoms.get_forces()

            structure_changes = {
                "volume_change": abs(atoms.get_volume() - abs(float(
                    lattice[0][0] * (lattice[1][1] * lattice[2][2] - lattice[1][2] * lattice[2][1])
                    - lattice[0][1] * (lattice[1][0] * lattice[2][2] - lattice[1][2] * lattice[2][0])
                    + lattice[0][2] * (lattice[1][0] * lattice[2][1] - lattice[1][1] * lattice[2][0])
                ))),
                "energy_change": abs(final_energy - initial_energy),
                "max_force": float(max(abs(f) for f in final_forces.flatten())),
            }

            return {
                "completed": True,
                "energy": float(final_energy),
                "forces": final_forces.tolist(),
                "structure_changes": structure_changes,
                "error": None,
            }

        except Exception as e:
            return {
                "completed": False,
                "energy": None,
                "forces": [],
                "structure_changes": {},
                "error": str(e),
            }

    # ── novelty ───────────────────────────────────────────────

    def check_novelty(self, structure_data: dict) -> dict:
        """Check against Materials Project and known structures.

        Returns: {is_novel, similar_structures, similarity_score}
        """
        try:
            import pymatgen  # noqa: F401
            return self._check_novelty_with_pymatgen(structure_data)
        except ImportError:
            logger.debug("pymatgen not available, novelty check skipped")
            return {
                "is_novel": None,
                "similar_structures": [],
                "similarity_score": None,
                "warning": "pymatgen not available for novelty check",
            }

    def _check_novelty_with_pymatgen(self, data: dict) -> dict:
        from pymatgen.core import Structure, Lattice

        similar_structures: list[dict] = []
        similarity_score: float | None = None

        try:
            lattice = data.get("lattice")
            species = data.get("species", [])
            coords = data.get("coords", [])
            formula = data.get("formula", "")

            if not species or not coords or lattice is None:
                return {
                    "is_novel": None,
                    "similar_structures": [],
                    "similarity_score": None,
                    "warning": "Insufficient data for novelty check",
                }

            # Try Materials Project query
            mp_matches = self._query_materials_project(formula)
            for match in mp_matches:
                similar_structures.append({
                    "material_id": match.get("material_id", ""),
                    "formula": match.get("formula", ""),
                    "source": "Materials Project",
                    "similarity": match.get("similarity", 0.0),
                })
                if match.get("similarity", 0) > (similarity_score or 0):
                    similarity_score = match["similarity"]

            is_novel = similarity_score is None or similarity_score < 0.5

        except Exception as e:
            return {
                "is_novel": None,
                "similar_structures": [],
                "similarity_score": None,
                "warning": str(e),
            }

        return {
            "is_novel": is_novel,
            "similar_structures": similar_structures[:5],
            "similarity_score": similarity_score,
        }

    def _query_materials_project(self, formula: str) -> list[dict]:
        """Query Materials Project for similar structures."""
        try:
            import httpx

            resp = httpx.get(
                f"https://api.materialsproject.org/materials/summary/?formula={formula}&_limit=5",
                headers={"X-API-KEY": ""},
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                results = []
                for entry in data.get("data", []):
                    results.append({
                        "material_id": entry.get("material_id", ""),
                        "formula": entry.get("formula_pretty", formula),
                        "similarity": 0.3,  # placeholder
                    })
                return results
        except Exception as e:
            logger.warning("Materials Project query failed: %s", e)
            return []

    # ── helpers ───────────────────────────────────────────────

    @staticmethod
    def _species_to_atomic_numbers(species: list[str]) -> list[int]:
        """Map element symbols to atomic numbers."""
        _ATOMIC_NUMBERS = {
            "H": 1, "He": 2, "Li": 3, "Be": 4, "B": 5, "C": 6, "N": 7, "O": 8, "F": 9, "Ne": 10,
            "Na": 11, "Mg": 12, "Al": 13, "Si": 14, "P": 15, "S": 16, "Cl": 17, "Ar": 18,
            "K": 19, "Ca": 20, "Sc": 21, "Ti": 22, "V": 23, "Cr": 24, "Mn": 25, "Fe": 26,
            "Co": 27, "Ni": 28, "Cu": 29, "Zn": 30, "Ga": 31, "Ge": 32, "As": 33, "Se": 34,
            "Br": 35, "Kr": 36, "Rb": 37, "Sr": 38, "Y": 39, "Zr": 40, "Nb": 41, "Mo": 42,
            "Tc": 43, "Ru": 44, "Rh": 45, "Pd": 46, "Ag": 47, "Cd": 48, "In": 49, "Sn": 50,
            "Sb": 51, "Te": 52, "I": 53, "Xe": 54, "Cs": 55, "Ba": 56, "La": 57, "Ce": 58,
            "Pr": 59, "Nd": 60, "Pm": 61, "Sm": 62, "Eu": 63, "Gd": 64, "Tb": 65, "Dy": 66,
            "Ho": 67, "Er": 68, "Tm": 69, "Yb": 70, "Lu": 71, "Hf": 72, "Ta": 73, "W": 74,
            "Re": 75, "Os": 76, "Ir": 77, "Pt": 78, "Au": 79, "Hg": 80, "Tl": 81, "Pb": 82,
            "Bi": 83, "Po": 84, "At": 85, "Rn": 86, "Fr": 87, "Ra": 88, "Ac": 89, "Th": 90,
            "Pa": 91, "U": 92, "Np": 93, "Pu": 94, "Am": 95, "Cm": 96, "Bk": 97, "Cf": 98,
            "Es": 99, "Fm": 100, "Md": 101, "No": 102, "Lr": 103,
        }
        numbers = []
        for s in species:
            num = _ATOMIC_NUMBERS.get(s)
            if num is None:
                raise ValueError(f"Unknown element: {s}")
            numbers.append(num)
        return numbers