"""Committee thinker — generates structured proposals using Intern-S2 or rule templates."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from .enums import CommitteeType
from .models import CommitteeCase, Proposal


class CommitteeThinker:
    """Generates structured proposals for committee cases."""

    def __init__(self, llm_provider=None):
        self.llm_provider = llm_provider

    async def propose(self, case: CommitteeCase, context: dict) -> Proposal:
        """Use Intern-S2 to generate a structured proposal."""
        if self.llm_provider:
            return await self._llm_propose(case, context)
        return self._template_propose(case, context)

    async def _llm_propose(self, case: CommitteeCase, context: dict) -> Proposal:
        try:
            prompt = self._build_prompt(case, context)
            response = await asyncio.wait_for(
                self.llm_provider.generate(prompt),
                timeout=90.0,
            )
            content = self._parse_response(response)
            if not isinstance(content, dict):
                return self._template_propose(case, context)
            model_name = getattr(self.llm_provider, 'model_name', None) or getattr(self.llm_provider, 'model', 'unknown')
            return Proposal(
                proposal_id=f"prop-{case.case_id}",
                case_id=case.case_id,
                content=content,
                assumptions=content.get("assumptions", []),
                requested_evidence=content.get("requested_evidence", []),
                model_provenance={"model": model_name, "prompt": prompt},
                created_at=datetime.now(timezone.utc),
            )
        except Exception:
            # Fallback to template on any error
            return self._template_propose(case, context)

    def _template_propose(self, case: CommitteeCase, context: dict) -> Proposal:
        templates = {
            CommitteeType.CRYSTAL_CONSTRUCTION: {
                "content": {
                    "goal": "Validate crystal structure candidates",
                    "approach": "Check structure validity, chemical reasonability, and stability",
                },
                "assumptions": [
                    "Structure generation is valid",
                    "Composition constraints are correct",
                ],
                "requested_evidence": [
                    "structure_validity",
                    "chemical_reasonability",
                    "symmetry",
                    "relaxation_stability",
                    "novelty",
                    "target_match",
                ],
            },
            CommitteeType.EXPERIMENTAL_READINESS: {
                "content": {
                    "goal": "Assess experimental readiness",
                    "approach": "Check safety, compliance, and feasibility",
                },
                "assumptions": [
                    "Materials are synthesizable",
                    "Equipment is available",
                ],
                "requested_evidence": [
                    "safety",
                    "compliance",
                    "feasibility",
                    "resource_availability",
                    "scheduling",
                ],
            },
            CommitteeType.CANDIDATE_PRIORITY: {
                "content": {
                    "goal": "Prioritize material candidates",
                    "approach": "Compare candidates by target match, confidence, stability, cost",
                },
                "assumptions": [
                    "All candidates are valid",
                    "Properties are comparable",
                ],
                "requested_evidence": [
                    "target_match",
                    "confidence",
                    "stability",
                    "dft_info_value",
                    "cost",
                ],
            },
            CommitteeType.DEVIATION_REVIEW: {
                "content": {
                    "goal": "Review experimental deviations",
                    "approach": "Check data quality, methodology, reproducibility",
                },
                "assumptions": [
                    "Deviation is significant",
                    "Root cause is identifiable",
                ],
                "requested_evidence": [
                    "data_qc",
                    "deviation_magnitude",
                    "methodology_review",
                    "reproducibility",
                    "context_alignment",
                ],
            },
            CommitteeType.EXTERNAL_EVIDENCE: {
                "content": {
                    "goal": "Integrate external evidence",
                    "approach": "Check rule consistency, source reliability, cross-reference",
                },
                "assumptions": [
                    "External sources are accessible",
                    "Data is comparable",
                ],
                "requested_evidence": [
                    "rule_consistency",
                    "source_reliability",
                    "cross_reference",
                    "temporal_validity",
                    "domain_relevance",
                ],
            },
            CommitteeType.CANDIDATE_QUALITY: {
                "content": {
                    "goal": "Validate candidate material quality",
                    "approach": "Check formula validity, data quality, and synthesizability",
                },
                "assumptions": [
                    "Candidate formulas are parseable",
                    "Input data matches target constraints",
                ],
                "requested_evidence": [
                    "formula_validity",
                    "composition_check",
                    "data_quality",
                    "synthesizability",
                    "target_match",
                ],
            },
            CommitteeType.SYSTEM_HEALTH: {
                "content": {
                    "goal": "Assess system health and service availability",
                    "approach": "Check critical service status, error rates, and resource utilization",
                },
                "assumptions": [
                    "Service health endpoints are reachable",
                    "Recent error logs are available",
                ],
                "requested_evidence": [
                    "service_status",
                    "error_rate",
                    "resource_utilization",
                    "dependency_health",
                    "recent_failures",
                ],
            },
        }

        template = templates.get(
            case.committee_type,
            {
                "content": {"goal": "General review", "approach": "Standard evaluation"},
                "assumptions": [],
                "requested_evidence": [],
            },
        )

        return Proposal(
            proposal_id=f"prop-{case.case_id}",
            case_id=case.case_id,
            content=template["content"],
            assumptions=template["assumptions"],
            requested_evidence=template["requested_evidence"],
            model_provenance={"method": "template"},
            created_at=datetime.now(timezone.utc),
        )

    def _build_prompt(self, case: CommitteeCase, context: dict) -> str:
        return f"""You are a committee thinker for battery materials research.
Committee type: {case.committee_type.value}
Trigger code: {case.trigger_code}
Risk level: {case.risk_level.value}
Context: {context}

Generate a structured proposal with:
- goal: what to assess
- approach: how to assess it
- assumptions: key assumptions
- requested_evidence: list of evidence capabilities needed

Respond in JSON format."""

    def _parse_response(self, response: str) -> dict:
        import json

        try:
            content = json.loads(response)
        except json.JSONDecodeError:
            return {"goal": "parse_failed", "assumptions": [], "requested_evidence": []}
        if not isinstance(content, dict):
            return {"goal": "parse_failed", "assumptions": [], "requested_evidence": []}
        return content