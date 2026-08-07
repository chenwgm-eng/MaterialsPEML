"""RDKit 分子描述符计算适配器 — 作为 MPA 远程服务的本地回退方案。"""
from __future__ import annotations

from typing import Any

from .execution_adapter import ExecutionAdapter


class RDKitAdapter(ExecutionAdapter):
    """基于 RDKit 的分子描述符计算适配器。

    作为 MPA 远程服务的本地回退方案，计算基本分子描述符。
    当 RDKit 不可用时，使用内置的简化计算作为 fallback。
    """

    _PROPERTY_FUNCTIONS: dict[str, str] = {
        "MolWt": "分子量",
        "MolLogP": "脂水分配系数",
        "NumHDonors": "氢键供体数",
        "NumHAcceptors": "氢键受体数",
        "TPSA": "拓扑极性表面积",
        "NumRotatableBonds": "可旋转键数",
        "RingCount": "环数",
        "FractionCsp3": "sp3 碳比例",
    }

    def __init__(self) -> None:
        self._rdkit_available = self._try_import_rdkit()

    # ------------------------------------------------------------------
    # Import
    # ------------------------------------------------------------------

    def _try_import_rdkit(self) -> bool:
        try:
            import rdkit  # noqa: F401
            return True
        except ImportError:
            return False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def execute(self, prepared_input: dict[str, Any]) -> dict[str, Any]:
        """Calculate molecular descriptors from SMILES.

        Input format::

            {"smiles_list": [...], "property_keys": [...]}

        Output format::

            {"results": [{"smiles": "...", "properties": {...}}, ...]}

        When *property_keys* is empty or omitted, all supported properties
        are computed.
        """
        smiles_list = prepared_input.get("smiles_list", [])
        property_keys = prepared_input.get("property_keys", [])

        if not smiles_list:
            return {"results": []}

        keys = (
            [k for k in property_keys if k in self._PROPERTY_FUNCTIONS]
            if property_keys
            else list(self._PROPERTY_FUNCTIONS)
        )

        if self._rdkit_available:
            results = self._compute_with_rdkit(smiles_list, keys)
        else:
            results = self._compute_fallback(smiles_list, keys)

        return {"results": results}

    def parse_output(self, raw_output: dict[str, Any]) -> dict[str, Any]:
        """Parse raw RDKit output into structured format."""
        return raw_output

    def get_resource_requirements(
        self, input_data: dict[str, Any]
    ) -> dict[str, Any]:
        return {"cpu": 1, "memory_mb": 512, "walltime_minutes": 5}

    # ------------------------------------------------------------------
    # RDKit implementation
    # ------------------------------------------------------------------

    def _compute_with_rdkit(
        self, smiles_list: list[str], keys: list[str]
    ) -> list[dict[str, Any]]:
        from rdkit import Chem
        from rdkit.Chem import Descriptors, rdMolDescriptors

        results: list[dict[str, Any]] = []
        for smi in smiles_list:
            mol = Chem.MolFromSmiles(smi)
            if mol is None:
                results.append(
                    {"smiles": smi, "properties": {}, "error": "Invalid SMILES"}
                )
                continue

            props: dict[str, Any] = {}
            for key in keys:
                try:
                    val = self._rdkit_func(key, mol, Descriptors, rdMolDescriptors)
                    props[key] = val
                except Exception:
                    props[key] = None
            results.append({"smiles": smi, "properties": props})
        return results

    @staticmethod
    def _rdkit_func(
        key: str,
        mol: Any,
        descriptors: Any,
        rd_mol_descriptors: Any,
    ) -> Any:
        """Dispatch to the appropriate RDKit descriptor function."""
        mapping = {
            "MolWt": lambda: descriptors.MolWt(mol),
            "MolLogP": lambda: descriptors.MolLogP(mol),
            "NumHDonors": lambda: descriptors.NumHDonors(mol),
            "NumHAcceptors": lambda: descriptors.NumHAcceptors(mol),
            "TPSA": lambda: descriptors.TPSA(mol),
            "NumRotatableBonds": lambda: descriptors.NumRotatableBonds(mol),
            "RingCount": lambda: rd_mol_descriptors.CalcNumRings(mol),
            "FractionCsp3": lambda: rd_mol_descriptors.CalcFractionCsp3(mol),
        }
        fn = mapping.get(key)
        if fn is None:
            raise ValueError(f"Unsupported property: {key}")
        return float(fn())

    # ------------------------------------------------------------------
    # Fallback (no RDKit)
    # ------------------------------------------------------------------

    def _compute_fallback(
        self, smiles_list: list[str], keys: list[str]
    ) -> list[dict[str, Any]]:
        """Simplified element-count-based fallback when RDKit is unavailable."""
        import re

        results: list[dict[str, Any]] = []
        for smi in smiles_list:
            props: dict[str, Any] = {}
            for key in keys:
                props[key] = self._fallback_property(smi, key)

            # Attempt a rough heavy-atom count
            heavy = len(
                set(re.findall(r"[A-Z][a-z]?", smi))
                - {"C", "N", "O", "S", "P", "F", "Cl", "Br", "I"}
            )

            if "MolWt" in keys and props.get("MolWt") is None:
                props["MolWt"] = 12.0 * heavy  # crude estimate
            if "MolLogP" in keys and props.get("MolLogP") is None:
                props["MolLogP"] = 0.0
            if "FractionCsp3" in keys and props.get("FractionCsp3") is None:
                props["FractionCsp3"] = 0.0

            results.append({"smiles": smi, "properties": props})
        return results

    @staticmethod
    def _fallback_property(smiles: str, key: str) -> Any:
        """Return a safe default for a property when RDKit is absent."""
        defaults: dict[str, Any] = {
            "MolWt": None,
            "MolLogP": None,
            "NumHDonors": 0,
            "NumHAcceptors": 0,
            "TPSA": 0.0,
            "NumRotatableBonds": 0,
            "RingCount": 0,
            "FractionCsp3": None,
        }
        return defaults.get(key)