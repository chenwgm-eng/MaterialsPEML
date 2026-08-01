"""External evidence adapter for committee review."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone


class ExternalEvidenceAdapter:
    """Adapter for external evidence adoption committee.

    Three core checks:
    1. Hard rule conflict — SMARTS, regulations, QC rules
    2. Traceability — version, method, input hash, applicability scope
    3. Cross-validation — consistency with local models/data
    """

    def __init__(self, blacklist_smarts: list[str] | None = None):
        self.blacklist_smarts = blacklist_smarts or []

    def check_hard_rule_conflict(self, external_result: dict, local_rules: dict) -> dict:
        """Check if external result conflicts with hard rules (SMARTS, regulations, QC).

        Args:
            external_result: External evidence result dict.
            local_rules: Local hard rules dict with keys like 'smarts', 'regulations', 'qc'.

        Returns:
            {conflict: bool, conflicting_rules: list[str], recommendation: str}
        """
        conflicts: list[str] = []

        # 1. SMARTS pattern conflict check
        external_smiles = external_result.get("smiles", "")
        external_psmiles = external_result.get("psmiles", "")
        if "smarts" in local_rules:
            smarts_list = local_rules["smarts"] + self.blacklist_smarts  # Merge both lists
        else:
            smarts_list = self.blacklist_smarts

        # Check SMILES
        if external_smiles:
            for smarts in smarts_list:
                match = self._check_smarts_match(external_smiles, smarts)
                if match is None:
                    conflicts.append(f"SMARTS check unavailable (RDKit not installed): {smarts}")
                elif match is True:
                    conflicts.append(f"SMARTS conflict: {smarts}")
        # Check PSMILES independently
        if external_psmiles:
            for smarts in smarts_list:
                match = self._check_smarts_match(external_psmiles, smarts)
                if match is None:
                    conflicts.append(f"SMARTS check unavailable (RDKit not installed): {smarts}")
                elif match is True:
                    conflicts.append(f"SMARTS conflict (psmiles): {smarts}")

        # 2. Regulatory compliance check
        regulations = local_rules.get("regulations", {})
        if regulations:
            restricted = regulations.get("restricted_elements", [])
            formula = external_result.get("formula", "")
            try:
                from pymatgen.core import Composition
                comp = Composition(formula)
                formula_elements = {str(e) for e in comp.elements}
                for elem in restricted:
                    if elem in formula_elements:
                        conflicts.append(f"Regulatory restriction: element {elem} restricted")
            except Exception:
                # Fallback to word-boundary regex if pymatgen unavailable
                import re
                for elem in restricted:
                    if re.search(r'\b' + re.escape(elem) + r'\b', formula):
                        conflicts.append(f"Regulatory restriction: element {elem} restricted")

        # 3. QC threshold conflict
        qc_rules = local_rules.get("qc", {})
        if qc_rules:
            external_value = external_result.get("value", 0)
            if isinstance(external_value, (int, float)):
                min_val = qc_rules.get("min_value")
                max_val = qc_rules.get("max_value")
                if min_val is not None and external_value < min_val:
                    conflicts.append(f"QC threshold: value {external_value} below min {min_val}")
                if max_val is not None and external_value > max_val:
                    conflicts.append(f"QC threshold: value {external_value} above max {max_val}")

        has_conflict = len(conflicts) > 0
        recommendation = "reject_external" if has_conflict else "proceed_with_cross_validation"

        return {
            "conflict": has_conflict,
            "conflicting_rules": conflicts,
            "recommendation": recommendation,
        }

    def check_traceability(self, external_result: dict) -> dict:
        """Check if external evidence has version, method, input hash, applicability scope.

        Args:
            external_result: External evidence result dict.

        Returns:
            {traceable: bool, missing_fields: list[str], traceability_score: float}
        """
        required_fields = {
            "version": "evidence version/identifier",
            "method": "methodology used",
            "input_hash": "hash of input data",
            "applicability_scope": "domain of applicability",
        }

        missing: list[str] = []
        missing_fields: list[str] = []
        for field, description in required_fields.items():
            if not external_result.get(field):
                missing_fields.append(field)
                missing.append(f"{field} ({description})")

        # Also check provenance/metadata
        provenance = external_result.get("provenance", {})
        if isinstance(provenance, dict):
            if not provenance.get("source_type"):
                missing.append("provenance.source_type")
            if not provenance.get("timestamp"):
                missing.append("provenance.timestamp")

        # Auto-fill input_hash if missing
        if "input_hash" in missing_fields:
            h = hashlib.sha256(json.dumps(external_result, sort_keys=True).encode()).hexdigest()
            external_result["input_hash"] = h
            missing_fields.remove("input_hash")
            missing.remove("input_hash (hash of input data)")

        traceable = len(missing) == 0
        score = 1.0 - (len(missing) / max(len(required_fields), 1))

        return {
            "traceable": traceable,
            "missing_fields": missing,
            "traceability_score": round(score, 2),
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

    def check_cross_validation(self, external_result: dict, local_results: dict) -> dict:
        """Cross-validate external results with local models/data.

        Args:
            external_result: External evidence result dict with 'value', 'confidence', 'property_name'.
            local_results: Local results dict with same structure.

        Returns:
            {consistent: bool, discrepancies: list[dict], agreement_score: float}
        """
        discrepancies: list[dict] = []

        ext_value = external_result.get("value")
        local_value = local_results.get("value")

        if ext_value is not None and local_value is not None:
            try:
                ext_val = float(ext_value)
                local_val = float(local_value)
                if local_val != 0:
                    rel_diff = abs(ext_val - local_val) / abs(local_val)
                    if rel_diff > 0.30:
                        discrepancies.append({
                            "type": "large_value_discrepancy",
                            "external_value": ext_val,
                            "local_value": local_val,
                            "relative_difference": round(rel_diff, 4),
                            "threshold": 0.30,
                        })
                else:
                    abs_diff = abs(ext_val - local_val)
                    if abs_diff > 1.0:
                        discrepancies.append({
                            "type": "large_absolute_discrepancy",
                            "external_value": ext_val,
                            "local_value": local_val,
                            "absolute_difference": round(abs_diff, 4),
                        })
            except (ValueError, TypeError):
                discrepancies.append({
                    "type": "non_numeric_values",
                    "external_value": str(ext_value),
                    "local_value": str(local_value),
                })

        # Compare confidence
        ext_confidence = external_result.get("confidence", 0)
        local_confidence = local_results.get("confidence", 0)
        try:
            if float(ext_confidence) < 0.3 and float(local_confidence) > 0.7:
                discrepancies.append({
                    "type": "confidence_mismatch",
                    "external_confidence": ext_confidence,
                    "local_confidence": local_confidence,
                })
        except (ValueError, TypeError):
            pass

        # Compare property_name
        ext_prop = external_result.get("property_name", "")
        local_prop = local_results.get("property_name", "")
        if ext_prop and local_prop and ext_prop != local_prop:
            discrepancies.append({
                "type": "property_name_mismatch",
                "external": ext_prop,
                "local": local_prop,
            })

        consistent = len(discrepancies) == 0
        agreement_score = 1.0 - min(len(discrepancies) * 0.25, 1.0)

        return {
            "consistent": consistent,
            "discrepancies": discrepancies,
            "agreement_score": round(agreement_score, 2),
        }

    def _check_smarts_match(self, smiles: str, smarts: str) -> bool | None:
        """Check if SMILES matches a SMARTS pattern using RDKit.

        Returns True if match, False if no match, None if RDKit unavailable.
        """
        try:
            from rdkit import Chem
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                return False
            pattern = Chem.MolFromSmarts(smarts)
            if pattern is None:
                return False
            return mol.HasSubstructMatch(pattern)
        except ImportError:
            return None