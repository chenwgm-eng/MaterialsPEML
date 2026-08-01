"""Experiment readiness committee adapter — pre-experiment validation for battery materials."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class ExperimentAdapter:
    """Adapter for experimental readiness committee evidence collection.

    Provides pre-experiment validation checks including materials availability,
    equipment availability, safety compliance, regulatory compliance,
    historical experiment lookup, and protocol-to-draft mapping.

    Follows the same pattern as CrystalAdapter — graceful handling of
    missing dependencies, structured dict returns, and httpx for HTTP calls.
    """

    def __init__(
        self,
        materials_api_url: str = "",
        equipment_api_url: str = "",
        safety_rules: dict | None = None,
        regulatory_rules: dict | None = None,
    ):
        self.materials_api_url = materials_api_url
        self.equipment_api_url = equipment_api_url
        self.safety_rules = safety_rules or {}
        self.regulatory_rules = regulatory_rules or {}

    # ── materials availability ───────────────────────────────

    def check_materials_availability(self, candidate: dict, materials_db: dict | None = None) -> dict:
        """Check if required materials are available.

        Args:
            candidate: Candidate dict with 'formula', 'required_reagents', etc.
            materials_db: Optional dict mapping material names to stock info.

        Returns:
            {available: bool, missing: list[str], alternatives: dict}
        """
        missing: list[str] = []
        alternatives: dict[str, str] = {}

        required_reagents = candidate.get("required_reagents", [])
        if not required_reagents and candidate.get("formula"):
            required_reagents = [candidate["formula"]]

        # Use local materials_db if provided
        if materials_db is not None:
            for reagent in required_reagents:
                if reagent not in materials_db or not materials_db[reagent]:
                    missing.append(reagent)
            available = len(missing) == 0
            return {"available": available, "missing": missing, "alternatives": alternatives}

        # Query external materials API if configured
        if self.materials_api_url:
            try:
                import httpx

                for reagent in required_reagents:
                    resp = httpx.get(
                        f"{self.materials_api_url}/materials/{reagent}",
                        timeout=10,
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        if not data.get("in_stock", False):
                            missing.append(reagent)
                            if data.get("alternative"):
                                alternatives[reagent] = data["alternative"]
                    else:
                        missing.append(reagent)
            except Exception as e:
                logger.warning("Materials availability query failed: %s", e)
                missing = list(required_reagents)
        else:
            # No db or API — cannot verify, mark all as missing
            missing = list(required_reagents)

        available = len(missing) == 0
        return {"available": available, "missing": missing, "alternatives": alternatives}

    # ── equipment availability ────────────────────────────────

    def check_equipment_availability(self, protocol: dict, equipment_db: dict | None = None) -> dict:
        """Check if equipment required by the protocol is available.

        Args:
            protocol: Protocol dict with 'required_equipment' list.
            equipment_db: Optional dict mapping equipment names to availability.

        Returns:
            {available: bool, missing: list[str]}
        """
        missing: list[str] = []
        required_equipment = protocol.get("required_equipment", [])

        if equipment_db is not None:
            for equip in required_equipment:
                if equip not in equipment_db or not equipment_db[equip]:
                    missing.append(equip)
            return {"available": len(missing) == 0, "missing": missing}

        if self.equipment_api_url:
            try:
                import httpx

                for equip in required_equipment:
                    resp = httpx.get(
                        f"{self.equipment_api_url}/equipment/{equip}",
                        timeout=10,
                    )
                    if resp.status_code != 200 or not resp.json().get("available", False):
                        missing.append(equip)
            except Exception as e:
                logger.warning("Equipment availability query failed: %s", e)
                missing = list(required_equipment)
        else:
            missing = list(required_equipment)

        return {"available": len(missing) == 0, "missing": missing}

    # ── safety compliance ─────────────────────────────────────

    def check_safety_compliance(self, protocol: dict, candidate: dict) -> dict:
        """Check safety constraints for the experiment.

        Args:
            protocol: Protocol dict with conditions, equipment, etc.
            candidate: Candidate dict with formula, properties, etc.

        Returns:
            {compliant: bool, issues: list[str]}
        """
        issues: list[str] = []

        # Check temperature limits
        max_temp = self.safety_rules.get("max_temperature", float("inf"))
        protocol_temp = protocol.get("temperature", 0)
        try:
            if float(protocol_temp) > float(max_temp):
                issues.append(f"Temperature {protocol_temp} exceeds safe maximum {max_temp}")
        except (ValueError, TypeError):
            pass

        # Check pressure limits
        max_pressure = self.safety_rules.get("max_pressure", float("inf"))
        protocol_pressure = protocol.get("pressure", 0)
        try:
            if float(protocol_pressure) > float(max_pressure):
                issues.append(f"Pressure {protocol_pressure} exceeds safe maximum {max_pressure}")
        except (ValueError, TypeError):
            pass

        # Check hazardous materials
        hazardous_materials = set(self.safety_rules.get("hazardous_materials", []))
        required_reagents = candidate.get("required_reagents", [])
        if candidate.get("formula"):
            required_reagents = required_reagents + [candidate["formula"]]
        for reagent in required_reagents:
            if reagent in hazardous_materials:
                issues.append(f"Hazardous material detected: {reagent}")

        # Check for required safety equipment
        required_safety_equipment = self.safety_rules.get("required_safety_equipment", [])
        protocol_equipment = protocol.get("required_equipment", [])
        for se in required_safety_equipment:
            if se not in protocol_equipment:
                issues.append(f"Missing required safety equipment: {se}")

        return {"compliant": len(issues) == 0, "issues": issues}

    # ── regulatory compliance ─────────────────────────────────

    def check_regulatory_compliance(self, protocol: dict, candidate: dict) -> dict:
        """Check regulatory constraints for the experiment.

        Args:
            protocol: Protocol dict with waste disposal, handling, etc.
            candidate: Candidate dict with formula, restricted elements, etc.

        Returns:
            {compliant: bool, issues: list[str]}
        """
        issues: list[str] = []

        # Check restricted elements
        restricted_elements = set(self.regulatory_rules.get("restricted_elements", []))
        formula = candidate.get("formula", "")
        if formula and restricted_elements:
            try:
                from pymatgen.core import Composition
                comp = Composition(formula)
                formula_elements = {str(e) for e in comp.elements}
                for elem in restricted_elements:
                    if elem in formula_elements:
                        issues.append(f"Regulatory restriction: element {elem} in formula {formula}")
            except Exception:
                # Fallback to word-boundary regex if pymatgen unavailable
                import re
                for elem in restricted_elements:
                    if re.search(r'\b' + re.escape(elem) + r'\b', formula):
                        issues.append(f"Regulatory restriction: element {elem} in formula {formula}")

        # Check waste disposal requirements
        waste_type = protocol.get("waste_type", "")
        restricted_waste = self.regulatory_rules.get("restricted_waste_types", [])
        if waste_type and waste_type in restricted_waste:
            issues.append(f"Waste type '{waste_type}' is restricted — special disposal required")

        # Check required permits
        required_permits = self.regulatory_rules.get("required_permits", [])
        candidate_permits = candidate.get("permits", [])
        for permit in required_permits:
            if permit not in candidate_permits:
                issues.append(f"Missing required permit: {permit}")

        return {"compliant": len(issues) == 0, "issues": issues}

    # ── historical experiments ────────────────────────────────

    def check_historical_experiments(self, candidate: dict, history: list[dict] | None = None) -> dict:
        """Check if similar experiments were done previously.

        Args:
            candidate: Candidate dict with formula, protocol_type, etc.
            history: Optional list of past experiment dicts.

        Returns:
            {exists: bool, reference_id: str}
        """
        formula = candidate.get("formula", "")
        protocol_type = candidate.get("protocol_type", "")

        if history is not None:
            for exp in history:
                if exp.get("formula", "") == formula and exp.get("protocol_type", "") == protocol_type:
                    return {"exists": True, "reference_id": exp.get("experiment_id", "")}
            return {"exists": False, "reference_id": ""}

        # Query external API if available
        if self.materials_api_url:
            try:
                import httpx

                params = {"formula": formula, "protocol_type": protocol_type}
                resp = httpx.get(
                    f"{self.materials_api_url}/experiments/search",
                    params=params,
                    timeout=10,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    results = data.get("results", [])
                    if results:
                        return {"exists": True, "reference_id": results[0].get("experiment_id", "")}
            except Exception as e:
                logger.warning("Historical experiment query failed: %s", e)

        return {"exists": False, "reference_id": ""}

    # ── protocol to draft mapping ─────────────────────────────

    def map_protocol_to_draft(self, protocol: dict, candidate: dict) -> dict:
        """Map a protocol to a draft experiment plan.

        Args:
            protocol: Protocol dict with steps, parameters, equipment.
            candidate: Candidate dict with formula, target properties.

        Returns:
            Draft experiment plan dict.
        """
        draft: dict[str, Any] = {
            "experiment_id": f"draft-{candidate.get('candidate_id', candidate.get('formula', 'unknown'))}",
            "formula": candidate.get("formula", ""),
            "candidate_id": candidate.get("candidate_id", ""),
            "protocol_type": protocol.get("protocol_type", ""),
            "target_properties": candidate.get("target_properties", []),
            "steps": [],
            "parameters": {},
            "required_equipment": protocol.get("required_equipment", []),
            "required_reagents": candidate.get("required_reagents", []),
            "status": "draft",
        }

        # Map protocol steps to experiment steps
        for i, step in enumerate(protocol.get("steps", [])):
            draft["steps"].append({
                "step_number": i + 1,
                "action": step.get("action", ""),
                "parameters": step.get("parameters", {}),
                "duration": step.get("duration", ""),
                "notes": step.get("notes", ""),
            })

        # Copy key parameters
        for param_key in ("temperature", "pressure", "duration", "atmosphere", "cooling_rate"):
            if param_key in protocol:
                draft["parameters"][param_key] = protocol[param_key]

        # Add safety and regulatory notes
        safety_check = self.check_safety_compliance(protocol, candidate)
        regulatory_check = self.check_regulatory_compliance(protocol, candidate)
        draft["safety_notes"] = safety_check.get("issues", [])
        draft["regulatory_notes"] = regulatory_check.get("issues", [])

        return draft
