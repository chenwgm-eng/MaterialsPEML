"""Committee doer — builds evidence collection plans for committee cases."""

from __future__ import annotations

from .enums import CommitteeType
from .models import CommitteeCase, CommitteeVerdict, EvidenceItem, Proposal


class CommitteeDoer:
    """Builds evidence collection plans based on committee type and proposals."""

    def __init__(self, tool_registry=None, scp_client_pool=None):
        self.tool_registry = tool_registry
        self.scp_client_pool = scp_client_pool

    def build_evidence_plan(self, case: CommitteeCase, proposal: Proposal) -> list[dict]:
        """Build a list of evidence tasks based on committee type and proposal."""
        tasks = []
        capabilities = proposal.requested_evidence

        for i, cap in enumerate(capabilities):
            tool_name = self._map_capability_to_tool(cap, case.committee_type)
            if tool_name is None:
                continue  # Skip unknown capabilities
            task = {
                "tool_name": tool_name,
                "args": {
                    "capability": cap,
                    "case_id": case.case_id,
                    "candidate_id": case.candidate_id,
                    "project_id": case.project_id,
                },
                "timeout": 60,
                "retry": 2,
                "idempotency_key": f"{case.case_id}-{cap}-{i}",
                "input_snapshot_hash": case.input_snapshot_hash,
            }
            tasks.append(task)

        return tasks

    def build_followup_plan(
        self,
        case: CommitteeCase,
        verdict: CommitteeVerdict,
        evidence: list[EvidenceItem],
    ) -> list[dict]:
        """Build follow-up evidence tasks for request_evidence verdicts."""
        tasks = []

        for action in verdict.required_actions:
            tool_name = self._map_action_to_tool(action)
            if tool_name is None:
                continue  # Skip unmapped actions
            task = {
                "tool_name": tool_name,
                "args": {
                    "action": action,
                    "case_id": case.case_id,
                    "candidate_id": case.candidate_id,
                    "project_id": case.project_id,
                },
                "timeout": 60,
                "retry": 1,
                "idempotency_key": f"{case.case_id}-followup-{action}",
                "input_snapshot_hash": case.input_snapshot_hash,
            }
            tasks.append(task)

        return tasks

    def _map_capability_to_tool(self, capability: str, committee_type: CommitteeType) -> str | None:
        capability_tool_map = {
            "structure_validity": "structure_validation",
            "chemical_reasonability": "chemical_reasonability_check",
            "symmetry": "symmetry_analysis",
            "relaxation_stability": "relaxation_stability_calc",
            "novelty": "novelty_check",
            "target_match": "target_match_eval",
            "safety": "safety_check",
            "compliance": "compliance_check",
            "feasibility": "feasibility_check",
            "resource_availability": "resource_check",
            "scheduling": "scheduling_check",
            "confidence": "confidence_eval",
            "stability": "stability_eval",
            "dft_info_value": "dft_info_eval",
            "cost": "cost_eval",
            "data_qc": "data_quality_check",
            "deviation_magnitude": "deviation_analysis",
            "methodology_review": "methodology_review",
            "reproducibility": "reproducibility_check",
            "context_alignment": "context_alignment_check",
            "rule_consistency": "rule_consistency_check",
            "source_reliability": "source_reliability_check",
            "cross_reference": "cross_reference_check",
            "temporal_validity": "temporal_validity_check",
            "domain_relevance": "domain_relevance_check",
        }
        return capability_tool_map.get(capability, None)

    def _map_action_to_tool(self, action: str) -> str | None:
        known_actions = {
            "human_review",
            "infrastructure_review",
            "request_more_evidence",
            "re_run_analysis",
            "escalate",
        }
        if action not in known_actions:
            return None
        return f"action_{action}"