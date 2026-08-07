"""Committee coordinator — orchestrates the full committee lifecycle."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from .enums import CaseStatus, CommitteeType, Decision, TriggerCode
from .models import CommitteeCase, CommitteeVerdict, EvidenceItem, Proposal
from .policy import CommitteePolicy, PolicyDeniedError
from .repository import CommitteeRepository
from .thinker import CommitteeThinker
from .doer import CommitteeDoer
from .verifier import CommitteeVerifier
from .event_store import CommitteeEventStore


class CommitteeCoordinator:
    """Orchestrates the full committee lifecycle: propose -> evidence -> verify -> verdict."""

    def __init__(
        self,
        config,
        policy: CommitteePolicy,
        thinker: CommitteeThinker,
        doer: CommitteeDoer,
        verifier: CommitteeVerifier,
        repository: CommitteeRepository,
        event_store: CommitteeEventStore,
        executor=None,
        identity_manager=None,
        tool_gateway=None,
        policy_engine=None,
    ):
        self.config = config
        self.policy = policy
        self.thinker = thinker
        self.doer = doer
        self.verifier = verifier
        self.repository = repository
        self.event_store = event_store
        self.executor = executor
        # Control Plane integration (optional, lazy-wired by api startup).
        self.identity_manager = identity_manager
        self.tool_gateway = tool_gateway
        self.policy_engine = policy_engine

    async def assess_candidate_priority(
        self,
        case: CommitteeCase,
        candidates: list[dict],
        top_k_scores: list[float] | None = None,
        user_role: str = "viewer",
    ) -> dict:
        """Dedicated workflow for Candidate Priority Committee.

        Triggered when Top-K scores differ by <=5% or multi-objective conflicts exist.

        Outputs:
            - dft_queue: ordered list of candidates for DFT calculation
            - retention_pool: candidates kept for future rounds
            - pareto_relations: Pareto-dominance relationships
            - resource_constraints: resource limits and allocations
            - per-candidate rationale: performance, confidence, cost, information_value
        """
        self.policy.assert_authorized(case, user_role=user_role)
        await asyncio.to_thread(self.event_store.append, case.case_id, "candidate_priority_started", {"case_id": case.case_id})
        await asyncio.to_thread(self.repository.update_case_status, case.case_id, CaseStatus.THINKING)

        # 1. Verify trigger conditions
        trigger_reason = self._verify_candidate_priority_trigger(case, top_k_scores)
        await asyncio.to_thread(self.event_store.append, case.case_id, "trigger_verified", {"reason": trigger_reason})

        # 2. Propose via thinker
        context = {
            "trigger_code": case.trigger_code,
            "committee_type": case.committee_type.value,
            "risk_level": case.risk_level.value,
            "candidate_count": len(candidates),
        }
        try:
            proposal = await asyncio.wait_for(self.thinker.propose(case, context), timeout=300.0)
        except Exception as e:
            await asyncio.to_thread(self.repository.update_case_status, case.case_id, CaseStatus.FAILED)
            await asyncio.to_thread(self.event_store.append, case.case_id, "case_failed", {"reason": str(e)})
            raise
        await asyncio.to_thread(self.repository.save_proposal, proposal)
        await asyncio.to_thread(
            self.event_store.append,
            case.case_id, "proposal_generated",
            {"proposal_id": proposal.proposal_id, "requested_evidence": proposal.requested_evidence},
        )

        # 3. Build evidence plan targeting priority-specific evidence
        evidence_plan = self.doer.build_evidence_plan(case, proposal)
        await asyncio.to_thread(self.repository.update_case_status, case.case_id, CaseStatus.EXECUTING_EVIDENCE)
        evidence = await self._execute_evidence(case, evidence_plan)

        for e in evidence:
            await asyncio.to_thread(self.repository.save_evidence, e)
            await asyncio.to_thread(
                self.event_store.append,
                case.case_id, "evidence_collected",
                {"evidence_id": e.evidence_id, "source_type": e.source_type.value},
            )

        # 4. Verify
        await asyncio.to_thread(self.repository.update_case_status, case.case_id, CaseStatus.VERIFYING)
        try:
            verdict = self.verifier.evaluate(case, proposal, evidence)
        except Exception as e:
            await asyncio.to_thread(self.repository.update_case_status, case.case_id, CaseStatus.FAILED)
            await asyncio.to_thread(self.event_store.append, case.case_id, "case_failed", {"reason": str(e)})
            raise
        await asyncio.to_thread(self.repository.save_verdict, verdict)
        await asyncio.to_thread(
            self.event_store.append,
            case.case_id, "verdict_reached",
            {"verdict_id": verdict.verdict_id, "decision": verdict.decision.value},
        )

        # 5. Build priority outputs
        dft_queue, retention_pool = self._build_priority_queues(candidates, evidence, verdict)
        pareto_relations = self._compute_pareto_relations(candidates)
        resource_constraints = self._compute_resource_constraints(len(dft_queue))

        # Per-candidate rationale
        candidate_rationale = []
        for cand in candidates[: len(dft_queue) + len(retention_pool)]:
            candidate_rationale.append({
                "candidate_id": cand.get("candidate_id", cand.get("formula", "")),
                "performance": cand.get("score", 0.0),
                "confidence": self._extract_confidence(cand, evidence),
                "cost": cand.get("estimated_cost", 0.0),
                "information_value": self._compute_info_value(cand, evidence),
            })

        final_status = self._decision_to_status(verdict.decision)
        await asyncio.to_thread(self.repository.update_case_status, case.case_id, final_status)
        await asyncio.to_thread(
            self.event_store.append,
            case.case_id, "candidate_priority_completed",
            {"dft_queue_size": len(dft_queue), "retention_pool_size": len(retention_pool), "final_decision": verdict.decision.value},
        )

        return {
            "verdict": verdict,
            "dft_queue": dft_queue,
            "retention_pool": retention_pool,
            "pareto_relations": pareto_relations,
            "resource_constraints": resource_constraints,
            "candidate_rationale": candidate_rationale,
            "trigger_reason": trigger_reason,
        }

    def _verify_candidate_priority_trigger(
        self, case: CommitteeCase, top_k_scores: list[float] | None
    ) -> str:
        """Verify that candidate priority committee should be triggered."""
        reasons = []
        if top_k_scores and len(top_k_scores) >= 2:
            best = max(top_k_scores)
            second = sorted(top_k_scores, reverse=True)[1]
            if best > 0 and (best - second) / best <= self.config.top_k_score_proximity_ratio:
                reasons.append(f"Top scores within {self.config.top_k_score_proximity_ratio:.0%}: {best:.4f} vs {second:.4f}")
        if case.trigger_code == TriggerCode.PREDICTION_CONFLICT:
            reasons.append("Multi-objective or multi-predictor conflict detected")
        if not reasons:
            reasons.append("Manual trigger")
        return "; ".join(reasons)

    def _build_priority_queues(
        self, candidates: list[dict], evidence: list[EvidenceItem], verdict: CommitteeVerdict
    ) -> tuple[list[dict], list[dict]]:
        """Build DFT queue and retention pool from candidates and evidence."""
        scored = []
        for i, cand in enumerate(candidates):
            score = 0.0
            for e in evidence:
                if e.capability == "dft_info_value":
                    score += float(e.value.get("score", 0)) * 0.15
                elif e.capability == "cost":
                    score += float(e.value.get("score", 0)) * 0.10
            score += cand.get("score", 0.0) * 0.75
            scored.append((score, cand))

        scored.sort(key=lambda x: x[0], reverse=True)
        dft_cut = max(3, len(scored) // 2)
        dft_queue = [c for _, c in scored[:dft_cut]]
        retention_pool = [c for _, c in scored[dft_cut:]]
        return dft_queue, retention_pool

    def _compute_pareto_relations(self, candidates: list[dict]) -> list[dict]:
        """Compute Pareto dominance relations among candidates."""
        if len(candidates) < 2:
            return []
        relations = []
        for i, a in enumerate(candidates):
            for j, b in enumerate(candidates):
                if i >= j:
                    continue
                a_score = a.get("score", 0.0)
                b_score = b.get("score", 0.0)
                a_cost = a.get("estimated_cost", 0.0)
                b_cost = b.get("estimated_cost", 0.0)
                if a_score >= b_score and a_cost <= b_cost and (a_score > b_score or a_cost < b_cost):
                    relations.append({"dominant": a.get("formula", a.get("candidate_id", "")),
                                      "dominated": b.get("formula", b.get("candidate_id", "")),
                                      "type": "pareto_dominates"})
                elif b_score >= a_score and b_cost <= a_cost and (b_score > a_score or b_cost < a_cost):
                    relations.append({"dominant": b.get("formula", b.get("candidate_id", "")),
                                      "dominated": a.get("formula", a.get("candidate_id", "")),
                                      "type": "pareto_dominates"})
        return relations

    def _compute_resource_constraints(self, dft_queue_size: int) -> dict:
        """Compute resource constraints for DFT queue."""
        return {
            "max_dft_slots": self.config.max_parallel_evidence_tasks,
            "queued": dft_queue_size,
            "available": max(0, self.config.max_parallel_evidence_tasks - dft_queue_size),
            "estimated_cost": dft_queue_size * 100.0,
        }

    def _extract_confidence(self, candidate: dict, evidence: list[EvidenceItem]) -> float:
        for e in evidence:
            if e.capability == "confidence":
                return float(e.value.get("score", 0.0))
        return candidate.get("confidence", 0.0)

    def _compute_info_value(self, candidate: dict, evidence: list[EvidenceItem]) -> float:
        for e in evidence:
            if e.capability == "dft_info_value":
                return float(e.value.get("score", 0.0))
        return 0.5

    async def assess_deviation_review(
        self,
        case: CommitteeCase,
        predicted_values: dict,
        experimental_values: dict,
        deviation_context: dict | None = None,
        user_role: str = "viewer",
    ) -> dict:
        """Dedicated workflow for Deviation Review Committee.

        Triggered when experiment-prediction deviation exceeds threshold.

        Decomposes deviation into five categories:
            1. Data quality (QC check)
            2. Model applicability domain
            3. Structure/recipe representation
            4. Experimental process
            5. Real material mechanism

        CRITICAL: If QC fails, must classify as DATA QUALITY issue first, not model failure.
        """
        self.policy.assert_authorized(case, user_role=user_role)
        await asyncio.to_thread(self.event_store.append, case.case_id, "deviation_review_started", {"case_id": case.case_id})
        await asyncio.to_thread(self.repository.update_case_status, case.case_id, CaseStatus.THINKING)

        # 1. Compute deviation magnitude
        deviation_report = self._compute_deviation(predicted_values, experimental_values)
        await asyncio.to_thread(self.event_store.append, case.case_id, "deviation_computed", deviation_report)

        # 2. Propose with deviation context
        context = {
            "trigger_code": case.trigger_code,
            "committee_type": case.committee_type.value,
            "risk_level": case.risk_level.value,
            "deviation": deviation_report,
        }
        try:
            proposal = await asyncio.wait_for(self.thinker.propose(case, context), timeout=300.0)
        except Exception as e:
            await asyncio.to_thread(self.repository.update_case_status, case.case_id, CaseStatus.FAILED)
            await asyncio.to_thread(self.event_store.append, case.case_id, "case_failed", {"reason": str(e)})
            raise
        await asyncio.to_thread(self.repository.save_proposal, proposal)
        await asyncio.to_thread(
            self.event_store.append,
            case.case_id, "proposal_generated",
            {"proposal_id": proposal.proposal_id},
        )

        # 3. Collect evidence with deviation-specific decomposition
        evidence_plan = self.doer.build_evidence_plan(case, proposal)

        # Ensure data_qc is always first in the plan
        qc_tasks = [t for t in evidence_plan if t["args"].get("capability") == "data_qc"]
        other_tasks = [t for t in evidence_plan if t["args"].get("capability") != "data_qc"]
        evidence_plan = qc_tasks + other_tasks

        await asyncio.to_thread(self.repository.update_case_status, case.case_id, CaseStatus.EXECUTING_EVIDENCE)
        evidence = await self._execute_evidence(case, evidence_plan)

        for e in evidence:
            await asyncio.to_thread(self.repository.save_evidence, e)
            await asyncio.to_thread(
                self.event_store.append,
                case.case_id, "evidence_collected",
                {"evidence_id": e.evidence_id, "capability": e.capability},
            )

        # 4. Decompose deviation into five categories
        decomposition = self._decompose_deviation(predicted_values, experimental_values, evidence, deviation_context)

        # Mandatory: if QC failed, root cause must be data_quality
        qc_evidence = [e for e in evidence if e.capability == "data_qc"]
        if qc_evidence and any(e.value.get("passed") is False for e in qc_evidence):
            # Reset previously chosen primary category
            prev_primary = decomposition.get("primary_cause")
            if prev_primary and prev_primary in decomposition and prev_primary != "data_quality":
                decomposition[prev_primary]["is_primary"] = False
            decomposition["primary_cause"] = "data_quality"
            decomposition["data_quality"]["is_primary"] = True
            decomposition["classification_note"] = "QC check failed — deviation classified as data quality issue, not model failure"

        await asyncio.to_thread(self.event_store.append, case.case_id, "deviation_decomposed", decomposition)

        # 5. Verify
        await asyncio.to_thread(self.repository.update_case_status, case.case_id, CaseStatus.VERIFYING)
        try:
            verdict = self.verifier.evaluate(case, proposal, evidence)
        except Exception as e:
            await asyncio.to_thread(self.repository.update_case_status, case.case_id, CaseStatus.FAILED)
            await asyncio.to_thread(self.event_store.append, case.case_id, "case_failed", {"reason": str(e)})
            raise
        await asyncio.to_thread(self.repository.save_verdict, verdict)
        await asyncio.to_thread(
            self.event_store.append,
            case.case_id, "verdict_reached",
            {"verdict_id": verdict.verdict_id, "decision": verdict.decision.value},
        )

        # 6. Build feedback actions
        feedback_actions = self._build_feedback_actions(decomposition, verdict)

        final_status = self._decision_to_status(verdict.decision)
        await asyncio.to_thread(self.repository.update_case_status, case.case_id, final_status)
        await asyncio.to_thread(
            self.event_store.append,
            case.case_id, "deviation_review_completed",
            {"primary_cause": decomposition.get("primary_cause", "unknown"), "final_decision": verdict.decision.value},
        )

        return {
            "verdict": verdict,
            "deviation_report": deviation_report,
            "decomposition": decomposition,
            "feedback_actions": feedback_actions,
        }

    def _compute_deviation(self, predicted: dict, experimental: dict) -> dict:
        """Compute deviation magnitude for each property."""
        deviations = {}
        for prop, pred_val in predicted.items():
            exp_val = experimental.get(prop)
            if exp_val is not None and exp_val != 0:
                rel_dev = abs(pred_val - exp_val) / abs(exp_val)
                exceeded = rel_dev > self.config.experiment_relative_deviation_trigger
                deviations[prop] = {
                    "predicted": pred_val,
                    "experimental": exp_val,
                    "relative_deviation": round(rel_dev, 4),
                    "threshold": self.config.experiment_relative_deviation_trigger,
                    "exceeded": exceeded,
                }
        return {"properties": deviations, "any_exceeded": any(d["exceeded"] for d in deviations.values())}

    def _decompose_deviation(
        self,
        predicted: dict,
        experimental: dict,
        evidence: list[EvidenceItem],
        context: dict | None,
    ) -> dict:
        """Decompose deviation into five categories."""
        decomposition = {
            "data_quality": {"score": 0.0, "issues": [], "is_primary": False},
            "model_applicability": {"score": 0.0, "issues": [], "is_primary": False},
            "structure_representation": {"score": 0.0, "issues": [], "is_primary": False},
            "experimental_process": {"score": 0.0, "issues": [], "is_primary": False},
            "real_mechanism": {"score": 0.0, "issues": [], "is_primary": False},
        }

        for e in evidence:
            cap = e.capability
            if cap == "data_qc":
                decomposition["data_quality"]["score"] = float(e.value.get("score", 0))
                if not e.value.get("passed", True):
                    decomposition["data_quality"]["issues"].append("QC check failed")
            elif cap == "deviation_magnitude":
                decomposition["model_applicability"]["score"] = float(e.value.get("score", 0))
            elif cap == "methodology_review":
                decomposition["experimental_process"]["score"] = float(e.value.get("score", 0))
                decomposition["structure_representation"]["score"] = float(e.value.get("score", 0)) * 0.5
            elif cap == "reproducibility":
                decomposition["experimental_process"]["score"] += float(e.value.get("score", 0)) * 0.5
            elif cap == "context_alignment":
                decomposition["model_applicability"]["score"] += float(e.value.get("score", 0)) * 0.5
                decomposition["real_mechanism"]["score"] = float(e.value.get("score", 0)) * 0.5

        # Determine primary cause: lowest-scoring non-QC category
        candidate_causes = [
            k for k in ["model_applicability", "structure_representation", "experimental_process", "real_mechanism"]
        ]
        if candidate_causes:
            primary = min(candidate_causes, key=lambda k: decomposition[k]["score"])
            decomposition[primary]["is_primary"] = True
            decomposition["primary_cause"] = primary

        return decomposition

    def _build_feedback_actions(self, decomposition: dict, verdict: CommitteeVerdict) -> list[dict]:
        """Build actionable feedback from deviation decomposition."""
        actions = []
        primary = decomposition.get("primary_cause", "")
        if primary == "data_quality":
            actions.append({"action": "requeue_experiment", "reason": "QC failed — re-run experiment with improved protocol"})
        elif primary == "model_applicability":
            actions.append({"action": "retrain_model", "reason": "Model outside applicability domain — expand training data"})
        elif primary == "structure_representation":
            actions.append({"action": "improve_representation", "reason": "Structure/recipe representation may be inaccurate"})
        elif primary == "experimental_process":
            actions.append({"action": "review_protocol", "reason": "Experimental process may have issues — review protocol"})
        elif primary == "real_mechanism":
            actions.append({"action": "investigate_mechanism", "reason": "Real material mechanism differs from model assumptions"})
        if verdict.decision == Decision.HUMAN_REVIEW:
            actions.append({"action": "escalate_human", "reason": "Requires human expert review"})
        return actions

    async def assess(self, case: CommitteeCase, user_role: str = "viewer") -> CommitteeVerdict:
        """Full lifecycle: propose -> collect evidence -> verify -> verdict."""
        # 1. Authorization
        self.policy.assert_authorized(case, user_role=user_role)
        await asyncio.to_thread(self.event_store.append, case.case_id, "assessment_started", {"case_id": case.case_id})
        await asyncio.to_thread(self.repository.update_case_status, case.case_id, CaseStatus.THINKING)

        # 2. Propose
        context = {
            "trigger_code": case.trigger_code,
            "committee_type": case.committee_type.value,
            "risk_level": case.risk_level.value,
        }
        try:
            proposal = await asyncio.wait_for(self.thinker.propose(case, context), timeout=300.0)
        except Exception as e:
            await asyncio.to_thread(self.repository.update_case_status, case.case_id, CaseStatus.FAILED)
            await asyncio.to_thread(self.event_store.append, case.case_id, "case_failed", {"reason": str(e)})
            raise
        await asyncio.to_thread(self.repository.save_proposal, proposal)
        await asyncio.to_thread(
            self.event_store.append,
            case.case_id, "proposal_generated",
            {"proposal_id": proposal.proposal_id, "requested_evidence": proposal.requested_evidence},
        )

        # 3. Evidence collection rounds
        all_evidence: list[EvidenceItem] = []
        verdict = None

        for round_num in range(self.config.max_evidence_rounds):
            await asyncio.to_thread(self.repository.update_case_status, case.case_id, CaseStatus.EXECUTING_EVIDENCE)
            await asyncio.to_thread(self.event_store.append, case.case_id, "evidence_round_start", {"round": round_num + 1})

            # Build plan
            if round_num == 0:
                evidence_plan = self.doer.build_evidence_plan(case, proposal)
            else:
                evidence_plan = self.doer.build_followup_plan(case, verdict, all_evidence)

            if not evidence_plan:
                break

            # Execute evidence tasks
            evidence = await self._execute_evidence(case, evidence_plan)
            all_evidence.extend(evidence)

            for e in evidence:
                await asyncio.to_thread(
                    self.event_store.append,
                    case.case_id, "evidence_collected",
                    {"evidence_id": e.evidence_id, "source_type": e.source_type.value},
                )

            # 4. Verify
            await asyncio.to_thread(self.repository.update_case_status, case.case_id, CaseStatus.VERIFYING)
            try:
                verdict = self.verifier.evaluate(case, proposal, all_evidence)
            except Exception as e:
                await asyncio.to_thread(self.repository.update_case_status, case.case_id, CaseStatus.FAILED)
                await asyncio.to_thread(self.event_store.append, case.case_id, "case_failed", {"reason": str(e)})
                raise

            # 核验后再持久化：确保 ClaimVerifier 就地标记的 verification/confidence 落库
            for e in evidence:
                await asyncio.to_thread(self.repository.save_evidence, e)

            await asyncio.to_thread(self.repository.save_verdict, verdict)
            await asyncio.to_thread(
                self.event_store.append,
                case.case_id, "verdict_reached",
                {"verdict_id": verdict.verdict_id, "decision": verdict.decision.value},
            )

            if verdict.decision != Decision.REQUEST_EVIDENCE:
                break

        # 5. Final verdict
        if verdict is None:
            verdict = self.verifier.escalate(case, "No evidence rounds completed")

        if verdict.decision == Decision.REQUEST_EVIDENCE:
            verdict = self.verifier.escalate(case, "evidence_round_limit")

        final_status = self._decision_to_status(verdict.decision)
        await asyncio.to_thread(self.repository.update_case_status, case.case_id, final_status)
        await asyncio.to_thread(
            self.event_store.append,
            case.case_id, "assessment_completed",
            {"final_decision": verdict.decision.value},
        )

        return verdict

    async def _execute_evidence(self, case: CommitteeCase, plan: list[dict]) -> list[EvidenceItem]:
        """Execute evidence tasks. Uses executor if available, otherwise simulates."""
        items: list[EvidenceItem] = []

        if self.executor:
            try:
                results = await self.executor.run_dag(plan)
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning("Committee executor failed: %s", e)
                results = []
            for i, task in enumerate(plan):
                result = results[i] if i < len(results) else {}
                item = EvidenceItem(
                    evidence_id=f"ev-{case.case_id}-{i}",
                    case_id=case.case_id,
                    source_type="local_tool",
                    source_name=task.get("tool_name", "unknown"),
                    capability=task["args"].get("capability", ""),
                    status="success" if result else "unknown",
                    value=result if isinstance(result, dict) else {},
                    provenance={"task": task},
                    created_at=datetime.now(timezone.utc),
                )
                items.append(item)
        else:
            for i, task in enumerate(plan):
                item = EvidenceItem(
                    evidence_id=f"ev-{case.case_id}-{i}",
                    case_id=case.case_id,
                    source_type="local_tool",
                    source_name=task.get("tool_name", "unknown"),
                    capability=task["args"].get("capability", ""),
                    status="unknown",
                    value={"score": 0.5},
                    provenance={"task": task, "note": "simulated"},
                    created_at=datetime.now(timezone.utc),
                )
                items.append(item)

        return items

    def _decision_to_status(self, decision: Decision) -> CaseStatus:
        mapping = {
            Decision.PASS: CaseStatus.PASS,
            Decision.REJECT: CaseStatus.REJECT,
            Decision.REQUEST_EVIDENCE: CaseStatus.REQUEST_EVIDENCE,
            Decision.HUMAN_REVIEW: CaseStatus.HUMAN_REVIEW,
            Decision.FAILED: CaseStatus.FAILED,
        }
        return mapping.get(decision, CaseStatus.FAILED)