"""Science scorers for the Eval Harness.

Computes scientific-quality metrics across the four science golden sets:
  * crystal_golden_set       — structure validation leakage / rejection
  * candidate_ranking_set    — NDCG, Pareto coverage, budget utility, queue stability
  * experiment_deviation_set — QC misattribution, actionable coverage, model-failure ID rate
  * external_evidence_conflict_set — hard-rule conflict interception, traceability, wrong adoption

Each scorer is a *pure function* of ``(cases, results)``. ``cases`` and
``results`` are aligned by index — ``results[i]`` corresponds to ``cases[i]``.
A result dict is expected to carry an ``output`` sub-dict (the target's actual
response); scorers tolerate missing fields and return ``0.0`` rather than
raising, so a partial run still produces a report.
"""
from __future__ import annotations

import math
from typing import Any

# ──────────────────────────────────────────────────────────────────────────
# Dataset name constants
# ──────────────────────────────────────────────────────────────────────────

CRYSTAL_DATASET = "crystal_golden_set"
RANKING_DATASET = "candidate_ranking_set"
DEVIATION_DATASET = "experiment_deviation_set"
CONFLICT_DATASET = "external_evidence_conflict_set"


# ──────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────

def _output(result: dict) -> dict:
    """Return the ``output`` sub-dict of a result, or empty dict."""
    out = result.get("output")
    return out if isinstance(out, dict) else {}


def _expected(case: Any) -> dict:
    """Return the ``expected`` sub-dict of a case (EvalCase or plain dict)."""
    exp = getattr(case, "expected", None)
    if exp is None and isinstance(case, dict):
        exp = case.get("expected")
    return exp if isinstance(exp, dict) else {}


def _input(case: Any) -> dict:
    """Return the ``input`` sub-dict of a case (EvalCase or plain dict)."""
    inp = getattr(case, "input", None)
    if inp is None and isinstance(case, dict):
        inp = case.get("input")
    return inp if isinstance(inp, dict) else {}


def _safe_div(num: float, den: float) -> float:
    """Safe division returning 0.0 when denominator is 0."""
    return num / den if den else 0.0


def _as_bool(value: Any) -> bool | None:
    """Coerce a value to bool; return None if undetermined."""
    if isinstance(value, bool):
        return value
    return None


# ──────────────────────────────────────────────────────────────────────────
# ScienceScorer
# ──────────────────────────────────────────────────────────────────────────

class ScienceScorer:
    """Compute scientific-quality metrics across the four science golden sets."""

    # ── crystal validation ───────────────────────────────────────────────

    def score_crystal_validation(self, cases: list, results: list[dict]) -> dict:
        """Score the crystal_golden_set.

        Metrics:
          * ``invalid_structure_leak_rate`` — of cases expected to be invalid,
            the fraction the target marked valid (lower is better; zero-tolerance).
          * ``valid_candidate_rejection_rate`` — of cases expected to be valid,
            the fraction the target rejected (lower is better).
          * ``invalid_structure_leak_count`` — absolute count of leaks (zero-tol).
          * ``spacegroup_accuracy`` — fraction of valid cases with correct spacegroup.
        """
        invalid_total = 0
        invalid_leaked = 0
        valid_total = 0
        valid_rejected = 0
        sg_correct = 0
        sg_total = 0

        for case, result in zip(cases, results):
            exp = _expected(case)
            out = _output(result)
            exp_valid = exp.get("valid")
            out_valid = out.get("valid")

            if exp_valid is False:
                invalid_total += 1
                if out_valid is True:
                    invalid_leaked += 1
            elif exp_valid is True:
                valid_total += 1
                if out_valid is False:
                    valid_rejected += 1
                # Spacegroup accuracy (only for valid cases with expected sg)
                exp_sg = exp.get("spacegroup")
                if exp_sg is not None:
                    sg_total += 1
                    if out.get("spacegroup") == exp_sg:
                        sg_correct += 1

        return {
            "invalid_structure_leak_rate": _safe_div(invalid_leaked, invalid_total),
            "invalid_structure_leak_count": invalid_leaked,
            "valid_candidate_rejection_rate": _safe_div(valid_rejected, valid_total),
            "spacegroup_accuracy": _safe_div(sg_correct, sg_total),
            "invalid_total": invalid_total,
            "valid_total": valid_total,
        }

    # ── candidate ranking ────────────────────────────────────────────────

    def score_candidate_ranking(self, cases: list, results: list[dict]) -> dict:
        """Score the candidate_ranking_set.

        Metrics:
          * ``ndcg`` — average Normalized Discounted Cumulative Gain @k.
          * ``pareto_coverage`` — fraction of Pareto-optimal candidates
            recovered in the target's recommended set.
          * ``budget_utility`` — achieved utility / max possible utility
            within budget (averaged).
          * ``queue_stability`` — Spearman-style rank agreement between the
            target's ranking and the expected ranking (averaged).
        """
        ndcg_scores: list[float] = []
        pareto_scores: list[float] = []
        budget_scores: list[float] = []
        stability_scores: list[float] = []

        for case, result in zip(cases, results):
            exp = _expected(case)
            out = _output(result)

            # NDCG
            relevance = exp.get("relevance_scores") or exp.get("relevance")
            predicted_order = out.get("ranking") or out.get("predicted_order")
            if isinstance(relevance, list) and isinstance(predicted_order, list):
                ndcg_scores.append(self._ndcg(relevance, predicted_order))

            # Pareto coverage
            pareto_ids = exp.get("pareto_optimal_ids") or exp.get("pareto_ids")
            recommended_ids = out.get("recommended_ids")
            if isinstance(pareto_ids, list) and isinstance(recommended_ids, list):
                pareto_set = set(map(str, pareto_ids))
                rec_set = set(map(str, recommended_ids))
                if pareto_set:
                    pareto_scores.append(
                        len(pareto_set & rec_set) / len(pareto_set)
                    )

            # Budget utility
            max_utility = exp.get("max_utility")
            achieved = out.get("achieved_utility")
            if isinstance(max_utility, (int, float)) and isinstance(achieved, (int, float)):
                budget_scores.append(_safe_div(achieved, max_utility))

            # Queue stability — rank correlation with expected order
            expected_order = exp.get("expected_order") or exp.get("ideal_order")
            if isinstance(expected_order, list) and isinstance(predicted_order, list):
                stability_scores.append(self._rank_agreement(expected_order, predicted_order))

        return {
            "ndcg": sum(ndcg_scores) / len(ndcg_scores) if ndcg_scores else 0.0,
            "pareto_coverage": sum(pareto_scores) / len(pareto_scores) if pareto_scores else 0.0,
            "budget_utility": sum(budget_scores) / len(budget_scores) if budget_scores else 0.0,
            "queue_stability": sum(stability_scores) / len(stability_scores) if stability_scores else 0.0,
            "case_count": len(cases),
        }

    @staticmethod
    def _ndcg(relevance: list, predicted_order: list) -> float:
        """Compute NDCG given per-candidate relevance (indexed by candidate id)
        and a predicted ordering (list of candidate indices/ids)."""
        # Map candidate id -> relevance score
        rel_map: dict[str, float] = {}
        for i, score in enumerate(relevance):
            rel_map[str(i)] = float(score) if isinstance(score, (int, float)) else 0.0

        def dcg(order: list) -> float:
            total = 0.0
            for pos, cand in enumerate(order, start=1):
                rel = rel_map.get(str(cand), 0.0)
                total += rel / math.log2(pos + 1)
            return total

        actual_dcg = dcg(predicted_order)
        ideal_order = sorted(
            range(len(relevance)),
            key=lambda i: float(relevance[i]) if isinstance(relevance[i], (int, float)) else 0.0,
            reverse=True,
        )
        ideal_dcg = dcg(ideal_order)
        return _safe_div(actual_dcg, ideal_dcg)

    @staticmethod
    def _rank_agreement(expected_order: list, predicted_order: list) -> float:
        """Spearman-style rank agreement in [0, 1].

        Computed as 1 - normalized pairwise disagreement.
        """
        try:
            exp_ranks = {str(c): i for i, c in enumerate(expected_order)}
            pred_ranks = {str(c): i for i, c in enumerate(predicted_order)}
            common = [str(c) for c in expected_order if str(c) in pred_ranks]
            n = len(common)
            if n < 2:
                return 1.0 if n == 1 else 0.0
            d_sq = sum(
                (exp_ranks[c] - pred_ranks[c]) ** 2 for c in common
            )
            max_d_sq = n * (n * n - 1) / 3.0  # maximum sum of squared rank diffs
            return 1.0 - _safe_div(d_sq, max_d_sq)
        except Exception:
            return 0.0

    # ── deviation attribution ────────────────────────────────────────────

    def score_deviation_attribution(self, cases: list, results: list[dict]) -> dict:
        """Score the experiment_deviation_set.

        Metrics:
          * ``qc_misattribution_rate`` — of cases whose true cause is NOT QC,
            the fraction wrongly attributed to QC (lower is better).
          * ``actionable_coverage`` — fraction of cases that received an
            actionable (non-unknown, non-empty) attribution.
          * ``model_failure_identification_rate`` — of cases whose true cause
            is a model failure, the fraction correctly identified.
          * ``exact_match_rate`` — fraction attributed to the exact true cause.
        """
        non_qc_total = 0
        qc_misattributed = 0
        actionable_total = 0
        model_failure_total = 0
        model_failure_identified = 0
        exact_match = 0

        for case, result in zip(cases, results):
            exp = _expected(case)
            out = _output(result)
            true_cause = exp.get("true_cause") or exp.get("cause")
            attributed = out.get("attributed_cause") or out.get("cause")

            # QC misattribution
            if true_cause and true_cause != "qc":
                non_qc_total += 1
                if attributed == "qc":
                    qc_misattributed += 1

            # Actionable coverage
            if attributed and attributed not in ("unknown", "none", ""):
                actionable_total += 1

            # Model failure identification
            if true_cause == "model_failure" or true_cause == "model":
                model_failure_total += 1
                if attributed == true_cause:
                    model_failure_identified += 1

            # Exact match
            if true_cause and attributed == true_cause:
                exact_match += 1

        return {
            "qc_misattribution_rate": _safe_div(qc_misattributed, non_qc_total),
            "actionable_coverage": _safe_div(actionable_total, len(cases)),
            "model_failure_identification_rate": _safe_div(model_failure_identified, model_failure_total),
            "exact_match_rate": _safe_div(exact_match, len(cases)),
            "case_count": len(cases),
        }

    # ── external evidence conflict ───────────────────────────────────────

    def score_external_evidence(self, cases: list, results: list[dict]) -> dict:
        """Score the external_evidence_conflict_set.

        Metrics:
          * ``hard_rule_conflict_interception_rate`` — of cases that contain a
            hard-rule conflict, the fraction the target intercepted/blocked.
          * ``traceability`` — fraction of cases with a recorded provenance/
            source trail (``output.trace`` or ``output.sources`` non-empty).
          * ``wrong_adoption_rate`` — of cases with a known correct evidence
            item, the fraction where the target adopted a conflicting item.
        """
        conflict_total = 0
        conflict_intercepted = 0
        traceable = 0
        adoption_total = 0
        wrong_adopted = 0

        for case, result in zip(cases, results):
            exp = _expected(case)
            out = _output(result)

            # Hard rule conflict interception
            has_conflict = exp.get("has_hard_conflict")
            should_intercept = exp.get("should_intercept", has_conflict is True)
            if should_intercept:
                conflict_total += 1
                if out.get("intercepted") is True or out.get("blocked") is True:
                    conflict_intercepted += 1

            # Traceability
            trace = out.get("trace") or out.get("sources") or out.get("provenance")
            if trace:
                traceable += 1

            # Wrong adoption
            correct_id = exp.get("correct_evidence_id")
            adopted_id = out.get("adopted_evidence_id")
            if correct_id is not None:
                adoption_total += 1
                if adopted_id is not None and str(adopted_id) != str(correct_id):
                    wrong_adopted += 1

        return {
            "hard_rule_conflict_interception_rate": _safe_div(conflict_intercepted, conflict_total),
            "traceability": _safe_div(traceable, len(cases)),
            "wrong_adoption_rate": _safe_div(wrong_adopted, adoption_total),
            "conflict_total": conflict_total,
            "case_count": len(cases),
        }

    # ── dispatch ─────────────────────────────────────────────────────────

    def score_all(self, dataset: str, cases: list, results: list[dict]) -> dict:
        """Dispatch to the correct scorer based on dataset name."""
        if dataset == CRYSTAL_DATASET:
            return self.score_crystal_validation(cases, results)
        if dataset == RANKING_DATASET:
            return self.score_candidate_ranking(cases, results)
        if dataset == DEVIATION_DATASET:
            return self.score_deviation_attribution(cases, results)
        if dataset == CONFLICT_DATASET:
            return self.score_external_evidence(cases, results)
        return {"error": f"unknown_dataset: {dataset}", "case_count": len(cases)}
