"""Scorecard implementations for each committee type."""

from .enums import Decision
from .models import EvidenceItem


class CrystalConstructionScorecard:
    """Hard constraints: structure validity. Weighted: chemical_reasonability(25%), symmetry(10%),
    relaxation_stability(35%), novelty(15%), target_match(15%)."""

    def __init__(self, min_score_threshold: float | None = None):
        self.weights = {
            "chemical_reasonability": 0.25,
            "symmetry": 0.10,
            "relaxation_stability": 0.35,
            "novelty": 0.15,
            "target_match": 0.15,
        }
        self.min_score_threshold = min_score_threshold

    def evaluate(self, evidence: list[EvidenceItem]) -> dict:
        blocking_reasons: list[str] = []
        warnings: list[str] = []
        score = 0.0

        if not evidence:
            blocking_reasons.append("No evidence provided for crystal construction")
            return {"score": 0.0, "blocking_reasons": blocking_reasons, "warnings": warnings, "passed": False}

        # Hard constraints: structure validity
        struct_evidence = [e for e in evidence if e.capability == "structure_validity"]
        if not struct_evidence or any(e.value.get("valid") is False for e in struct_evidence):
            blocking_reasons.append("Structure validity check failed")
            return {"score": 0.0, "blocking_reasons": blocking_reasons, "warnings": warnings, "passed": False}

        # Evidence-coverage check
        present_capabilities = {e.capability for e in evidence if e.status == "success"}
        required_capabilities = set(self.weights.keys())
        missing = required_capabilities - present_capabilities
        if missing:
            blocking_reasons.append(f"missing_evidence: {', '.join(sorted(missing))}")
            return {"passed": False, "score": 0.0, "blocking_reasons": blocking_reasons, "warnings": [], "scorecard": {}}

        # Weighted scoring
        for item in evidence:
            cap = item.capability
            if cap in self.weights:
                val = float(item.value.get("score", 0))
                if val < 0.5:
                    warnings.append(f"Low {cap}: {val:.2f}")
                if val < 0.3:
                    blocking_reasons.append(f"{cap} below threshold: {val:.2f}")
                score += val * self.weights[cap]

        # Check against config threshold if available
        threshold = getattr(self, 'min_score_threshold', None)
        if threshold is not None and score < threshold and not blocking_reasons:
            blocking_reasons.append(f"score_below_threshold: {score:.2f} < {threshold:.2f}")

        passed = len(blocking_reasons) == 0
        return {"score": round(score, 4), "blocking_reasons": blocking_reasons, "warnings": warnings, "passed": passed}


class ExperimentalReadinessScorecard:
    """Hard constraints: safety/compliance. Weighted scoring."""

    def __init__(self, min_score_threshold: float | None = None):
        self.weights = {
            "safety": 0.30,
            "compliance": 0.20,
            "feasibility": 0.25,
            "resource_availability": 0.15,
            "scheduling": 0.10,
        }
        self.min_score_threshold = min_score_threshold

    def evaluate(self, evidence: list[EvidenceItem]) -> dict:
        blocking_reasons: list[str] = []
        warnings: list[str] = []
        score = 0.0

        if not evidence:
            blocking_reasons.append("No evidence for experimental readiness")
            return {"score": 0.0, "blocking_reasons": blocking_reasons, "warnings": warnings, "passed": False}

        # Hard constraints: safety/compliance
        safety = [e for e in evidence if e.capability == "safety"]
        compliance = [e for e in evidence if e.capability == "compliance"]

        if safety and any(e.value.get("safe") is False for e in safety):
            blocking_reasons.append("Safety check failed")
            return {"score": 0.0, "blocking_reasons": blocking_reasons, "warnings": warnings, "passed": False}
        if compliance and any(e.value.get("compliant") is False for e in compliance):
            blocking_reasons.append("Compliance check failed")
            return {"score": 0.0, "blocking_reasons": blocking_reasons, "warnings": warnings, "passed": False}

        # Evidence-coverage check
        present_capabilities = {e.capability for e in evidence if e.status == "success"}
        required_capabilities = set(self.weights.keys())
        missing = required_capabilities - present_capabilities
        if missing:
            blocking_reasons.append(f"missing_evidence: {', '.join(sorted(missing))}")
            return {"passed": False, "score": 0.0, "blocking_reasons": blocking_reasons, "warnings": [], "scorecard": {}}

        for item in evidence:
            cap = item.capability
            if cap in self.weights:
                val = float(item.value.get("score", 0))
                if val < 0.5:
                    warnings.append(f"Low {cap}: {val:.2f}")
                score += val * self.weights[cap]

        # Check against config threshold if available
        threshold = getattr(self, 'min_score_threshold', None)
        if threshold is not None and score < threshold and not blocking_reasons:
            blocking_reasons.append(f"score_below_threshold: {score:.2f} < {threshold:.2f}")

        passed = len(blocking_reasons) == 0
        return {"score": round(score, 4), "blocking_reasons": blocking_reasons, "warnings": warnings, "passed": passed}


class CandidatePriorityScorecard:
    """Hard constraints: no blocks. Weighted: target_match(30%), confidence(25%), stability(20%),
    dft_info_value(15%), cost(10%)."""

    def __init__(self, min_score_threshold: float | None = None):
        self.weights = {
            "target_match": 0.30,
            "confidence": 0.25,
            "stability": 0.20,
            "dft_info_value": 0.15,
            "cost": 0.10,
        }
        self.min_score_threshold = min_score_threshold

    def evaluate(self, evidence: list[EvidenceItem]) -> dict:
        blocking_reasons: list[str] = []
        warnings: list[str] = []
        score = 0.0

        if not evidence:
            blocking_reasons.append("No evidence for candidate priority")
            return {"score": 0.0, "blocking_reasons": blocking_reasons, "warnings": warnings, "passed": False}

        # Evidence-coverage check
        present_capabilities = {e.capability for e in evidence if e.status == "success"}
        required_capabilities = set(self.weights.keys())
        missing = required_capabilities - present_capabilities
        if missing:
            blocking_reasons.append(f"missing_evidence: {', '.join(sorted(missing))}")
            return {"passed": False, "score": 0.0, "blocking_reasons": blocking_reasons, "warnings": [], "scorecard": {}}

        for item in evidence:
            cap = item.capability
            if cap in self.weights:
                val = float(item.value.get("score", 0))
                if val < 0.5:
                    warnings.append(f"Low {cap}: {val:.2f}")
                if val < 0.2:
                    blocking_reasons.append(f"{cap} critically low: {val:.2f}")
                score += val * self.weights[cap]

        # Check against config threshold if available
        threshold = getattr(self, 'min_score_threshold', None)
        if threshold is not None and score < threshold and not blocking_reasons:
            blocking_reasons.append(f"score_below_threshold: {score:.2f} < {threshold:.2f}")

        passed = len(blocking_reasons) == 0
        return {"score": round(score, 4), "blocking_reasons": blocking_reasons, "warnings": warnings, "passed": passed}


class DeviationReviewScorecard:
    """Hard constraints: data QC. Weighted scoring."""

    def __init__(self, min_score_threshold: float | None = None):
        self.weights = {
            "data_qc": 0.25,
            "deviation_magnitude": 0.30,
            "methodology_review": 0.20,
            "reproducibility": 0.15,
            "context_alignment": 0.10,
        }
        self.min_score_threshold = min_score_threshold

    def evaluate(self, evidence: list[EvidenceItem]) -> dict:
        blocking_reasons: list[str] = []
        warnings: list[str] = []
        score = 0.0

        if not evidence:
            blocking_reasons.append("No evidence for deviation review")
            return {"score": 0.0, "blocking_reasons": blocking_reasons, "warnings": warnings, "passed": False}

        # Hard constraints: data QC
        data_qc = [e for e in evidence if e.capability == "data_qc"]
        if data_qc and any(e.value.get("passed") is False for e in data_qc):
            blocking_reasons.append("Data QC check failed")
            return {"score": 0.0, "blocking_reasons": blocking_reasons, "warnings": warnings, "passed": False}

        # Evidence-coverage check
        present_capabilities = {e.capability for e in evidence if e.status == "success"}
        required_capabilities = set(self.weights.keys())
        missing = required_capabilities - present_capabilities
        if missing:
            blocking_reasons.append(f"missing_evidence: {', '.join(sorted(missing))}")
            return {"passed": False, "score": 0.0, "blocking_reasons": blocking_reasons, "warnings": [], "scorecard": {}}

        for item in evidence:
            cap = item.capability
            if cap in self.weights:
                val = float(item.value.get("score", 0))
                if val < 0.5:
                    warnings.append(f"Low {cap}: {val:.2f}")
                score += val * self.weights[cap]

        # Check against config threshold if available
        threshold = getattr(self, 'min_score_threshold', None)
        if threshold is not None and score < threshold and not blocking_reasons:
            blocking_reasons.append(f"score_below_threshold: {score:.2f} < {threshold:.2f}")

        passed = len(blocking_reasons) == 0
        return {"score": round(score, 4), "blocking_reasons": blocking_reasons, "warnings": warnings, "passed": passed}


class ExternalEvidenceScorecard:
    """Hard constraints: hard rule consistency. Weighted scoring."""

    def __init__(self, min_score_threshold: float | None = None):
        self.weights = {
            "rule_consistency": 0.30,
            "source_reliability": 0.25,
            "cross_reference": 0.20,
            "temporal_validity": 0.15,
            "domain_relevance": 0.10,
        }
        self.min_score_threshold = min_score_threshold

    def evaluate(self, evidence: list[EvidenceItem]) -> dict:
        blocking_reasons: list[str] = []
        warnings: list[str] = []
        score = 0.0

        if not evidence:
            blocking_reasons.append("No evidence for external evidence review")
            return {"score": 0.0, "blocking_reasons": blocking_reasons, "warnings": warnings, "passed": False}

        # Hard constraints: hard rule consistency
        rule_consistency = [e for e in evidence if e.capability == "rule_consistency"]
        if rule_consistency and any(e.value.get("consistent") is False for e in rule_consistency):
            blocking_reasons.append("Hard rule consistency check failed")
            return {"score": 0.0, "blocking_reasons": blocking_reasons, "warnings": warnings, "passed": False}

        # Evidence-coverage check
        present_capabilities = {e.capability for e in evidence if e.status == "success"}
        required_capabilities = set(self.weights.keys())
        missing = required_capabilities - present_capabilities
        if missing:
            blocking_reasons.append(f"missing_evidence: {', '.join(sorted(missing))}")
            return {"passed": False, "score": 0.0, "blocking_reasons": blocking_reasons, "warnings": [], "scorecard": {}}

        for item in evidence:
            cap = item.capability
            if cap in self.weights:
                val = float(item.value.get("score", 0))
                if val < 0.5:
                    warnings.append(f"Low {cap}: {val:.2f}")
                score += val * self.weights[cap]

        # Check against config threshold if available
        threshold = getattr(self, 'min_score_threshold', None)
        if threshold is not None and score < threshold and not blocking_reasons:
            blocking_reasons.append(f"score_below_threshold: {score:.2f} < {threshold:.2f}")

        passed = len(blocking_reasons) == 0
        return {"score": round(score, 4), "blocking_reasons": blocking_reasons, "warnings": warnings, "passed": passed}


class CandidateQualityScorecard:
    """Hard constraints: formula validity and composition. Weighted scoring."""

    def __init__(self, min_score_threshold: float | None = None):
        self.weights = {
            "formula_validity": 0.30,
            "composition_check": 0.25,
            "data_quality": 0.20,
            "synthesizability": 0.15,
            "target_match": 0.10,
        }
        self.min_score_threshold = min_score_threshold

    def evaluate(self, evidence: list[EvidenceItem]) -> dict:
        blocking_reasons: list[str] = []
        warnings: list[str] = []
        score = 0.0

        if not evidence:
            blocking_reasons.append("No evidence for candidate quality review")
            return {"score": 0.0, "blocking_reasons": blocking_reasons, "warnings": warnings, "passed": False}

        formula_validity = [e for e in evidence if e.capability == "formula_validity"]
        if formula_validity and any(e.value.get("valid") is False for e in formula_validity):
            blocking_reasons.append("Formula validity check failed")
            return {"score": 0.0, "blocking_reasons": blocking_reasons, "warnings": warnings, "passed": False}

        composition = [e for e in evidence if e.capability == "composition_check"]
        if composition and any(e.value.get("passed") is False for e in composition):
            blocking_reasons.append("Composition check failed")
            return {"score": 0.0, "blocking_reasons": blocking_reasons, "warnings": warnings, "passed": False}

        present_capabilities = {e.capability for e in evidence if e.status == "success"}
        required_capabilities = set(self.weights.keys())
        missing = required_capabilities - present_capabilities
        if missing:
            blocking_reasons.append(f"missing_evidence: {', '.join(sorted(missing))}")
            return {"passed": False, "score": 0.0, "blocking_reasons": blocking_reasons, "warnings": [], "scorecard": {}}

        for item in evidence:
            cap = item.capability
            if cap in self.weights:
                val = float(item.value.get("score", 0))
                if val < 0.5:
                    warnings.append(f"Low {cap}: {val:.2f}")
                if val < 0.3:
                    blocking_reasons.append(f"{cap} below threshold: {val:.2f}")
                score += val * self.weights[cap]

        threshold = getattr(self, 'min_score_threshold', None)
        if threshold is not None and score < threshold and not blocking_reasons:
            blocking_reasons.append(f"score_below_threshold: {score:.2f} < {threshold:.2f}")

        passed = len(blocking_reasons) == 0
        return {"score": round(score, 4), "blocking_reasons": blocking_reasons, "warnings": warnings, "passed": passed}


class SystemHealthScorecard:
    """Hard constraints: critical service availability. Weighted scoring."""

    def __init__(self, min_score_threshold: float | None = None):
        self.weights = {
            "service_status": 0.30,
            "error_rate": 0.25,
            "resource_utilization": 0.20,
            "dependency_health": 0.15,
            "recent_failures": 0.10,
        }
        self.min_score_threshold = min_score_threshold

    def evaluate(self, evidence: list[EvidenceItem]) -> dict:
        blocking_reasons: list[str] = []
        warnings: list[str] = []
        score = 0.0

        if not evidence:
            blocking_reasons.append("No evidence for system health review")
            return {"score": 0.0, "blocking_reasons": blocking_reasons, "warnings": warnings, "passed": False}

        service_status = [e for e in evidence if e.capability == "service_status"]
        if service_status and any(e.value.get("healthy") is False for e in service_status):
            blocking_reasons.append("Critical service unhealthy")
            return {"score": 0.0, "blocking_reasons": blocking_reasons, "warnings": warnings, "passed": False}

        present_capabilities = {e.capability for e in evidence if e.status == "success"}
        required_capabilities = set(self.weights.keys())
        missing = required_capabilities - present_capabilities
        if missing:
            blocking_reasons.append(f"missing_evidence: {', '.join(sorted(missing))}")
            return {"passed": False, "score": 0.0, "blocking_reasons": blocking_reasons, "warnings": [], "scorecard": {}}

        for item in evidence:
            cap = item.capability
            if cap in self.weights:
                val = float(item.value.get("score", 0))
                if val < 0.5:
                    warnings.append(f"Low {cap}: {val:.2f}")
                if val < 0.3:
                    blocking_reasons.append(f"{cap} below threshold: {val:.2f}")
                score += val * self.weights[cap]

        threshold = getattr(self, 'min_score_threshold', None)
        if threshold is not None and score < threshold and not blocking_reasons:
            blocking_reasons.append(f"score_below_threshold: {score:.2f} < {threshold:.2f}")

        passed = len(blocking_reasons) == 0
        return {"score": round(score, 4), "blocking_reasons": blocking_reasons, "warnings": warnings, "passed": passed}


SCORECARD_REGISTRY = {
    "crystal_construction": CrystalConstructionScorecard,
    "experimental_readiness": ExperimentalReadinessScorecard,
    "candidate_priority": CandidatePriorityScorecard,
    "deviation_review": DeviationReviewScorecard,
    "external_evidence": ExternalEvidenceScorecard,
    "candidate_quality": CandidateQualityScorecard,
    "system_health": SystemHealthScorecard,
}