"""Operations scorers for the Eval Harness.

Computes reliability and efficiency metrics. These metrics apply to any
dataset (the runner calls ``score_all`` with the active dataset name), since
operational concerns — recovery, duplicate calls, latency, cost — are
orthogonal to the science/safety dimensions scored elsewhere.
"""
from __future__ import annotations

from typing import Any

# ──────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────

def _output(result: dict) -> dict:
    """Return the ``output`` sub-dict of a result, or empty dict."""
    out = result.get("output")
    return out if isinstance(out, dict) else {}


def _as_float(value: Any) -> float | None:
    """Coerce numeric-like values to float; None otherwise."""
    if isinstance(value, bool):  # guard: bools are ints in Python
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _safe_div(num: float, den: float) -> float:
    return num / den if den else 0.0


# ──────────────────────────────────────────────────────────────────────────
# OpsScorer
# ──────────────────────────────────────────────────────────────────────────

class OpsScorer:
    """Compute reliability and efficiency metrics across eval cases."""

    def score_reliability(self, cases: list, results: list[dict]) -> dict:
        """Score reliability.

        Metrics:
          * ``recovery_success_rate`` — of cases that injected a failure
            (``expected.injected_failure`` truthy), the fraction where the
            target recovered (``output.recovered`` truthy).
          * ``duplicate_external_call_rate`` — average number of duplicate
            external calls per case (``output.duplicate_calls``); 0 is ideal.
          * ``tool_failure_degradation_correctness`` — of cases where a tool
            failure occurred, the fraction that degraded gracefully (produced
            a fallback result rather than crashing).
        """
        failure_injected_total = 0
        recovered = 0
        duplicate_calls_sum = 0.0
        tool_failure_total = 0
        degraded_correctly = 0

        for case, result in zip(cases, results):
            exp = case.expected if hasattr(case, "expected") else (case.get("expected") if isinstance(case, dict) else {})
            out = _output(result)

            # Recovery success
            if exp.get("injected_failure"):
                failure_injected_total += 1
                if out.get("recovered"):
                    recovered += 1

            # Duplicate external calls
            dup = _as_float(out.get("duplicate_calls"))
            if dup is not None:
                duplicate_calls_sum += dup

            # Tool failure degradation
            if out.get("tool_failure") or exp.get("injected_tool_failure"):
                tool_failure_total += 1
                if out.get("degraded_gracefully") or out.get("fallback_used"):
                    degraded_correctly += 1

        return {
            "recovery_success_rate": _safe_div(recovered, failure_injected_total),
            "duplicate_external_call_rate": _safe_div(duplicate_calls_sum, len(cases)),
            "tool_failure_degradation_correctness": _safe_div(degraded_correctly, tool_failure_total),
            "failure_injected_total": failure_injected_total,
            "tool_failure_total": tool_failure_total,
            "case_count": len(cases),
        }

    def score_efficiency(self, cases: list, results: list[dict]) -> dict:
        """Score efficiency.

        Metrics:
          * ``end_to_end_latency_ms`` — average latency across all cases
            (``result.latency_ms`` if present, else ``output.latency_ms``).
          * ``human_review_duration_ms`` — average time spent in human review
            across cases that were escalated (``output.human_review_duration_ms``).
          * ``cost_per_valid_candidate`` — total cost divided by the number of
            valid candidates produced.
        """
        latencies: list[float] = []
        review_durations: list[float] = []
        total_cost = 0.0
        valid_candidates = 0

        for case, result in zip(cases, results):
            out = _output(result)

            # End-to-end latency
            latency = _as_float(result.get("latency_ms")) or _as_float(out.get("latency_ms"))
            if latency is not None:
                latencies.append(latency)

            # Human review duration (only for escalated cases)
            review = _as_float(out.get("human_review_duration_ms"))
            if review is not None and out.get("escalated"):
                review_durations.append(review)

            # Cost per valid candidate
            cost = _as_float(out.get("cost_usd")) or _as_float(result.get("cost_usd"))
            if cost is not None:
                total_cost += cost
            # Count a "valid candidate" as a successful, non-rejected output.
            # For crystal cases this is out.valid == True; for ranking cases
            # out.recommended_ids non-empty; otherwise any non-error result.
            if out.get("valid") is True or (out.get("recommended_ids") and len(out["recommended_ids"]) > 0):
                valid_candidates += 1
            elif not out.get("error") and out.get("success") is True:
                valid_candidates += 1

        return {
            "end_to_end_latency_ms": sum(latencies) / len(latencies) if latencies else 0.0,
            "human_review_duration_ms": sum(review_durations) / len(review_durations) if review_durations else 0.0,
            "cost_per_valid_candidate": _safe_div(total_cost, valid_candidates),
            "total_cost_usd": total_cost,
            "valid_candidates": valid_candidates,
            "case_count": len(cases),
        }

    # ── dispatch ─────────────────────────────────────────────────────────

    def score_all(self, dataset: str, cases: list, results: list[dict]) -> dict:
        """Dispatch — ops metrics apply uniformly across datasets."""
        return {
            "reliability": self.score_reliability(cases, results),
            "efficiency": self.score_efficiency(cases, results),
            "dataset": dataset,
            "case_count": len(cases),
        }
