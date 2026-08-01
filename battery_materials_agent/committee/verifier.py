"""Committee verifier — evaluates evidence with scorecards and produces verdicts."""

from __future__ import annotations

from datetime import datetime, timezone

from .enums import CommitteeType, Decision
from .models import CommitteeCase, CommitteeVerdict, EvidenceItem, Proposal
from .scorecards import SCORECARD_REGISTRY


class CommitteeVerifier:
    """Evaluates committee cases using scorecards and produces verdicts."""

    def __init__(self, scorecards: dict | None = None):
        self.scorecards = scorecards or {
            key: cls()
            for key, cls in SCORECARD_REGISTRY.items()
        }

    def evaluate(
        self,
        case: CommitteeCase,
        proposal: Proposal,
        evidence: list[EvidenceItem],
    ) -> CommitteeVerdict:
        """Run the appropriate scorecard and return a verdict."""
        try:
            scorecard = self.scorecards.get(case.committee_type.value)
            if scorecard is None:
                return self.escalate(case, f"No scorecard for committee type: {case.committee_type.value}")

            # Check for infrastructure failures
            failed_evidence = [e for e in evidence if e.status in ("failed", "unknown")]
            if failed_evidence and not all(e.status == "success" for e in evidence):
                # If any required evidence failed, mark as FAILED (infrastructure issue)
                has_success = any(e.status == "success" for e in evidence)
                if not has_success:
                    return self._build_failed_verdict(case, "infrastructure_failure", failed_evidence)

            # Check evidence coverage
            present_capabilities = {e.capability for e in evidence if e.status == "success"}
            required_capabilities = set(proposal.requested_evidence) if proposal and proposal.requested_evidence else set()
            missing = required_capabilities - present_capabilities

            result = scorecard.evaluate(evidence)

            if result.get("blocking_reasons"):
                decision = Decision.REJECT
            elif missing:
                decision = Decision.REQUEST_EVIDENCE
            elif result["passed"]:
                decision = Decision.PASS
            else:
                decision = Decision.REQUEST_EVIDENCE

            # Apply score threshold
            threshold = None
            if case.committee_type.value == "crystal_construction":
                threshold = 0.70  # crystal_min_score_for_dft
            elif case.committee_type.value == "experimental_readiness":
                threshold = 0.75  # experiment_min_score_for_submit
            if threshold and result.get("score", 0) < threshold and decision == Decision.PASS:
                decision = Decision.REQUEST_EVIDENCE
                result["blocking_reasons"] = result.get("blocking_reasons", []) + [f"score_below_threshold: {result['score']:.2f} < {threshold}"]

            return CommitteeVerdict(
                verdict_id=f"verdict-{case.case_id}",
                case_id=case.case_id,
                decision=decision,
                scorecard={
                    "score": result["score"],
                    "passed": result["passed"],
                },
                blocking_reasons=result.get("blocking_reasons", []),
                warnings=result.get("warnings", []),
                required_actions=[],
                verifier_provenance={"method": "scorecard", "committee_type": case.committee_type.value},
                created_at=datetime.now(timezone.utc),
            )
        except Exception as exc:
            return self.escalate(case, f"verifier_error: {exc}")

    def _build_failed_verdict(
        self,
        case: CommitteeCase,
        reason: str,
        failed_evidence: list[EvidenceItem],
    ) -> CommitteeVerdict:
        """Build a FAILED verdict for infrastructure issues."""
        return CommitteeVerdict(
            verdict_id=f"verdict-{case.case_id}",
            case_id=case.case_id,
            decision=Decision.FAILED,
            scorecard={"score": 0.0, "passed": False},
            blocking_reasons=[f"{reason}: {len(failed_evidence)} failed/unknown evidence items"],
            warnings=[],
            required_actions=["infrastructure_review"],
            verifier_provenance={"method": "failed", "committee_type": case.committee_type.value},
            created_at=datetime.now(timezone.utc),
        )

    def escalate(self, case: CommitteeCase, reason: str) -> CommitteeVerdict:
        """Escalate to human review."""
        return CommitteeVerdict(
            verdict_id=f"verdict-{case.case_id}",
            case_id=case.case_id,
            decision=Decision.HUMAN_REVIEW,
            scorecard={"score": 0.0, "passed": False},
            blocking_reasons=[reason],
            warnings=[],
            required_actions=["human_review"],
            verifier_provenance={"method": "escalation"},
            created_at=datetime.now(timezone.utc),
        )