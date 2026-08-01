"""Eval Harness runner — fixed-input replay framework for the Agent Control Plane.

Replays golden-set cases against a target (model / agent / committee / tool /
policy), scores the results with science / safety / ops scorers, compares
against a baseline, and writes a JSON report. Used as a publication gate:
a target version may not be promoted while safety zero-tolerance metrics are
non-zero or business metrics regress against the baseline.

The runner is self-contained: by default it invokes mock fixtures
(:mod:`evals.fixtures.mock_providers`) so golden sets can be replayed without
any real infrastructure. Real targets are wired in by overriding
``_invoke_target``.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from .fixtures.mock_providers import (
    MockCommitteeCoordinator,
    MockLLMProvider,
    MockToolHandler,
)
from .scorers.ops_scorers import OpsScorer
from .scorers.safety_scorers import SafetyScorer
from .scorers.science_scorers import ScienceScorer

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────

# All known golden sets. ``run_eval(datasets=None)`` replays every set.
KNOWN_DATASETS: tuple[str, ...] = (
    "crystal_golden_set",
    "candidate_ranking_set",
    "experiment_deviation_set",
    "external_evidence_conflict_set",
    "security_policy_set",
)

# Package root: battery_materials_agent/. Relative defaults like
# ``evals/datasets`` resolve under here.
_PACKAGE_ROOT = Path(__file__).resolve().parents[1]

# Metrics where lower is better. Everything else is treated as higher-is-better.
# Zero-tolerance counts (key_exposure_count, invalid_structure_leak_count,
# policy_regression_failures, unauthorized_access_leak_count) are also lower-
# is-better AND must equal zero for the gate to pass.
_LOWER_IS_BETTER: frozenset[str] = frozenset({
    "invalid_structure_leak_rate",
    "invalid_structure_leak_count",
    "valid_candidate_rejection_rate",
    "qc_misattribution_rate",
    "wrong_adoption_rate",
    "key_exposure_count",
    "policy_regression_failures",
    "duplicate_external_call_rate",
    "end_to_end_latency_ms",
    "human_review_duration_ms",
    "cost_per_valid_candidate",
    "unauthorized_access_leak_count",
})

# Zero-tolerance metric names — must be 0 for the gate to pass.
_ZERO_TOLERANCE_METRICS: frozenset[str] = frozenset({
    "key_exposure_count",
    "invalid_structure_leak_count",
    "policy_regression_failures",
    "unauthorized_access_leak_count",
})


# ──────────────────────────────────────────────────────────────────────────
# Models
# ──────────────────────────────────────────────────────────────────────────

DatasetName = Literal[
    "crystal_golden_set",
    "candidate_ranking_set",
    "experiment_deviation_set",
    "external_evidence_conflict_set",
    "security_policy_set",
]

TargetType = Literal["model", "agent", "committee", "tool", "policy"]

RunStatus = Literal["pending", "running", "completed", "failed"]


class EvalCase(BaseModel):
    """A single golden-set case.

    Fields:
      * ``case_id`` — stable identifier within the dataset.
      * ``dataset`` — the golden set this case belongs to.
      * ``input`` — the fixed input replayed against the target.
      * ``expected`` — the ground-truth output the target should produce.
      * ``metadata`` — free-form description / provenance.
    """

    case_id: str
    dataset: DatasetName
    input: dict = Field(default_factory=dict)
    expected: dict = Field(default_factory=dict)
    metadata: dict = Field(default_factory=dict)


class EvalRun(BaseModel):
    """A single evaluation run over one or more datasets.

    ``cases`` and ``results`` are aligned by index — ``results[i]`` is the
    outcome of replaying ``cases[i]``.
    """

    eval_run_id: str
    target_type: TargetType
    target_id: str
    target_version: str
    dataset: str  # single name, or comma-joined when multiple datasets run
    status: RunStatus = "pending"
    cases: list[EvalCase] = Field(default_factory=list)
    results: list[dict] = Field(default_factory=list)
    metrics: dict = Field(default_factory=dict)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    baseline_version: str | None = None


# ──────────────────────────────────────────────────────────────────────────
# EvalRunner
# ──────────────────────────────────────────────────────────────────────────

class EvalRunner:
    """Replay golden sets against a target, score, and report.

    Lifecycle:
      1. ``load_dataset(name)`` reads ``{golden_set_dir}/{name}.json``.
      2. ``run_eval(...)`` replays every case via ``_invoke_target``,
         computes metrics with the three scorers, optionally compares
         against a baseline, and writes a JSON report to ``report_dir``.
      3. ``get_result`` / ``list_runs`` retrieve past runs from the
         in-memory store.
    """

    def __init__(
        self,
        golden_set_dir: str = "evals/datasets",
        report_dir: str = "evals/reports",
    ):
        # Resolve relative paths under the battery_materials_agent package
        # root so the harness works regardless of the process CWD.
        gd = Path(golden_set_dir)
        self.golden_set_dir: Path = gd if gd.is_absolute() else (_PACKAGE_ROOT / gd)
        rd = Path(report_dir)
        self.report_dir: Path = rd if rd.is_absolute() else (_PACKAGE_ROOT / rd)
        self.report_dir.mkdir(parents=True, exist_ok=True)

        # In-memory store of completed / in-flight runs.
        self._runs: dict[str, EvalRun] = {}

        # Scorers — stateless, safe to share across runs.
        self._science_scorer = ScienceScorer()
        self._safety_scorer = SafetyScorer()
        self._ops_scorer = OpsScorer()

        # Default mock fixtures used by ``_invoke_target``.
        self._mock_llm = MockLLMProvider()
        self._mock_tools = MockToolHandler()
        self._mock_committee = MockCommitteeCoordinator()

        logger.info(
            "EvalRunner initialized (golden_set_dir=%s, report_dir=%s)",
            self.golden_set_dir,
            self.report_dir,
        )

    # ── dataset loading ──────────────────────────────────────────────────

    def load_dataset(self, dataset_name: str) -> list[EvalCase]:
        """Load a golden set from ``{golden_set_dir}/{dataset_name}.json``.

        Each JSON entry is expected to carry ``case_id``, ``input``,
        ``expected`` and ``metadata``. The ``dataset`` field is stamped
        automatically from ``dataset_name``.
        """
        path = self.golden_set_dir / f"{dataset_name}.json"
        if not path.exists():
            raise FileNotFoundError(f"dataset not found: {path}")
        with path.open("r", encoding="utf-8") as fh:
            raw = json.load(fh)
        if not isinstance(raw, list):
            raise ValueError(f"dataset {dataset_name}: expected a JSON list, got {type(raw).__name__}")

        cases: list[EvalCase] = []
        for entry in raw:
            if not isinstance(entry, dict):
                raise ValueError(f"dataset {dataset_name}: entry is not a dict: {entry!r}")
            cases.append(
                EvalCase(
                    case_id=entry.get("case_id", ""),
                    dataset=dataset_name,  # type: ignore[arg-type]
                    input=entry.get("input", {}) or {},
                    expected=entry.get("expected", {}) or {},
                    metadata=entry.get("metadata", {}) or {},
                )
            )
        logger.info("Loaded %d cases from %s", len(cases), dataset_name)
        return cases

    # ── run evaluation ───────────────────────────────────────────────────

    async def run_eval(
        self,
        target_type: TargetType,
        target_id: str,
        target_version: str,
        datasets: list[str] | None = None,
        timeout_seconds: float = 600.0,
        baseline_version: str | None = None,
    ) -> EvalRun:
        """Run an evaluation across one or more datasets.

        For each dataset: load cases, invoke the target per case, collect
        results, and compute metrics via the three scorers. Then optionally
        compare against ``baseline_version`` and write a JSON report.

        The whole run is bounded by ``timeout_seconds``; on timeout or any
        other failure the run is marked ``failed`` and the partial state is
        still persisted to a report.
        """
        dataset_names = list(datasets) if datasets else list(KNOWN_DATASETS)
        eval_run_id = f"eval-{uuid4().hex[:12]}"
        dataset_label = ",".join(dataset_names)

        run = EvalRun(
            eval_run_id=eval_run_id,
            target_type=target_type,
            target_id=target_id,
            target_version=target_version,
            dataset=dataset_label,
            status="running",
            started_at=datetime.now(timezone.utc),
            baseline_version=baseline_version,
        )
        self._runs[eval_run_id] = run

        try:
            await asyncio.wait_for(
                self._execute_run(run, dataset_names),
                timeout=timeout_seconds,
            )
            run.status = "completed"
        except asyncio.TimeoutError:
            logger.warning("EvalRun %s timed out after %ss", eval_run_id, timeout_seconds)
            run.status = "failed"
            run.metrics.setdefault("error", f"timeout after {timeout_seconds}s")
            run.metrics["gate"] = {
                "passed": False,
                "violations": ["run_timeout"],
                "zero_tolerance_passed": False,
                "baseline_passed": False,
            }
        except Exception as exc:
            logger.exception("EvalRun %s failed", eval_run_id)
            run.status = "failed"
            run.metrics.setdefault("error", str(exc)[:200])
            run.metrics["gate"] = {
                "passed": False,
                "violations": ["run_failed"],
                "zero_tolerance_passed": False,
                "baseline_passed": False,
            }
        finally:
            run.completed_at = datetime.now(timezone.utc)
            self._write_report(run)

        return run

    async def _execute_run(self, run: EvalRun, dataset_names: list[str]) -> None:
        """Inner execution: load cases, invoke target, score, compare."""
        all_cases: list[EvalCase] = []
        all_results: list[dict] = []
        per_dataset_metrics: dict[str, dict] = {}

        for name in dataset_names:
            try:
                cases = self.load_dataset(name)
            except FileNotFoundError as exc:
                logger.warning("Skipping missing dataset %s: %s", name, exc)
                per_dataset_metrics[name] = {"error": "dataset_not_found"}
                continue

            results: list[dict] = []
            for case in cases:
                result = await self._invoke_target_safely(case, run.target_type, run.target_id)
                results.append(result)

            all_cases.extend(cases)
            all_results.extend(results)

            # Score this dataset with every applicable scorer.
            ds_metrics: dict[str, dict] = {}
            ds_metrics["science"] = self._science_scorer.score_all(name, cases, results)
            ds_metrics["safety"] = self._safety_scorer.score_all(name, cases, results)
            ds_metrics["ops"] = self._ops_scorer.score_all(name, cases, results)
            per_dataset_metrics[name] = ds_metrics

        run.cases = all_cases
        run.results = all_results
        run.metrics = {
            "per_dataset": per_dataset_metrics,
            "total_cases": len(all_cases),
        }

        # Baseline comparison (if a baseline version was supplied).
        if run.baseline_version:
            run.metrics["baseline_comparison"] = self.compare_with_baseline(run, run.baseline_version)

        # Publication gate: zero-tolerance + baseline non-regression.
        run.metrics["gate"] = self._evaluate_gate(run.metrics)

    async def _invoke_target_safely(
        self,
        case: EvalCase,
        target_type: TargetType,
        target_id: str,
    ) -> dict:
        """Wrap ``_invoke_target`` with timing and error capture."""
        start = time.perf_counter()
        try:
            output = await self._invoke_target(case, target_type, target_id)
            latency_ms = (time.perf_counter() - start) * 1000.0
            return {
                "case_id": case.case_id,
                "dataset": case.dataset,
                "output": output,
                "passed": self._check_passed(case, output),
                "error": None,
                "latency_ms": latency_ms,
            }
        except Exception as exc:
            latency_ms = (time.perf_counter() - start) * 1000.0
            logger.exception("Target invocation failed for case %s", case.case_id)
            return {
                "case_id": case.case_id,
                "dataset": case.dataset,
                "output": {},
                "passed": False,
                "error": str(exc),
                "latency_ms": latency_ms,
            }

    # ── target invocation (mock by default) ──────────────────────────────

    async def _invoke_target(
        self,
        case: EvalCase,
        target_type: TargetType,
        target_id: str,
    ) -> dict:
        """Invoke the target for a single case.

        This is a **placeholder** that dispatches to the mock fixtures. Real
        deployments override this to call the actual model / agent /
        committee / tool / policy under test. The output dict shape is
        scorer-dependent; see :mod:`evals.scorers` for the fields each
        scorer reads.
        """
        if target_type == "model":
            response = await self._mock_llm.complete({
                "messages": [{"role": "user", "content": json.dumps(case.input)}],
            })
            return self._shape_model_output(case, response)

        if target_type == "tool":
            # ``target_id`` carries the tool name for tool targets.
            return await self._mock_tools.invoke(target_id, case.input)

        if target_type == "committee":
            return await self._mock_committee.assess(case.input)

        if target_type == "agent":
            # Agents typically produce a candidate structure or recommendation.
            response = await self._mock_llm.complete({
                "messages": [{"role": "user", "content": json.dumps(case.input)}],
            })
            return self._shape_model_output(case, response)

        if target_type == "policy":
            # Policy target: mirror the expected decision so the security
            # golden set passes by default. Real policy engines override
            # ``_invoke_target`` to call ``PolicyEngine.authorize``.
            return self._shape_policy_output(case)

        return {"error": f"unknown target_type: {target_type}"}

    @staticmethod
    def _shape_model_output(case: EvalCase, response: dict) -> dict:
        """Shape a mock LLM response into the scorer-expected output.

        For crystal cases the model is expected to return a candidate
        structure; we re-run the mock validator so the result carries the
        ``valid`` / ``spacegroup`` fields the science scorer reads.
        """
        content = response.get("content", "")
        try:
            parsed = json.loads(content) if isinstance(content, str) else content
        except json.JSONDecodeError:
            parsed = {}

        if case.dataset == "crystal_golden_set":
            structure = (parsed.get("candidate") if isinstance(parsed, dict) else None) or case.input.get("structure", {})
            # Re-use the mock validator for a deterministic validity verdict.
            handler = MockToolHandler()
            validation = handler._tool_pymatgen_validate({"structure": structure})
            return {
                "valid": validation.get("valid"),
                "reason": validation.get("reason"),
                "spacegroup": validation.get("spacegroup"),
                "candidate": structure,
                "model": response.get("model", ""),
            }

        # Default: surface the parsed payload (or raw content) as output.
        return parsed if isinstance(parsed, dict) else {"content": content}

    @staticmethod
    def _shape_policy_output(case: EvalCase) -> dict:
        """Shape a mock policy decision based on input role/action/resource.

        Implements a minimal real policy logic rather than mirroring
        ``expected``, so the security gate is meaningful by default. Real
        deployments override ``_invoke_target`` for ``target_type="policy"``
        to call the real :class:`PolicyEngine`.
        """
        inp = case.input
        role = inp.get("role", "viewer")
        action = inp.get("action", "")
        resource = inp.get("resource", "")

        # Expired delegation context always denied.
        if inp.get("context_expired"):
            return {"allowed": False, "reason_code": "expired_delegation"}

        # Admin allows all actions.
        if role == "admin":
            return {"allowed": True, "reason_code": "admin_allowed"}

        # Viewer and researcher cannot perform write/submit operations.
        if role in ("viewer", "researcher") and action.startswith(
            ("create", "update", "delete", "submit", "start", "invoke")
        ):
            return {"allowed": False, "reason_code": "role_not_permitted"}

        # Unknown tool/resources are rejected.
        if resource.startswith("unknown_"):
            return {"allowed": False, "reason_code": "unknown_tool"}

        # Default allow for non-write actions from non-admin roles.
        return {"allowed": True, "reason_code": "default_allow"}

    # ── pass / fail check ────────────────────────────────────────────────

    @staticmethod
    def _check_passed(case: EvalCase, output: dict) -> bool:
        """Compare a target's output to the case's expected values.

        Conservative structural equality on the keys present in ``expected``.
        Returns False if any expected key disagrees or if the target errored.
        """
        if not isinstance(output, dict) or output.get("error"):
            return False
        expected = case.expected
        for key, exp_val in expected.items():
            if key not in output:
                return False
            if output[key] != exp_val:
                return False
        return True

    # ── gate evaluation ──────────────────────────────────────────────────

    def _evaluate_gate(self, metrics: dict) -> dict:
        """Evaluate the publication gate.

        Gate passes iff:
          1. Every zero-tolerance metric (across all datasets) is 0.
          2. No business metric regressed against the baseline (when a
             baseline comparison is present).
          3. No required dataset is missing (errored during load).
        """
        zt_violations: list[str] = []
        regression_violations: list[str] = []

        # 1. Zero-tolerance scan across per-dataset metrics.
        per_dataset = metrics.get("per_dataset", {})

        # 0. Missing dataset check — a required dataset that failed to load
        #    is a hard gate failure (blocks publication).
        for ds_name, ds_metrics in per_dataset.items():
            if isinstance(ds_metrics, dict) and "error" in ds_metrics:
                zt_violations.append(f"missing_dataset:{ds_name}:{ds_metrics['error']}")

        for ds_name, ds_metrics in per_dataset.items():
            if not isinstance(ds_metrics, dict):
                continue
            for scorer_name, scorer_metrics in ds_metrics.items():
                if not isinstance(scorer_metrics, dict):
                    continue
                # The safety scorer nests zero-tolerance under
                # ``zero_tolerance.metrics``.
                zero_tol = scorer_metrics.get("zero_tolerance")
                if isinstance(zero_tol, dict):
                    zt_metrics = zero_tol.get("metrics", {})
                    for metric_name, count in zt_metrics.items():
                        if isinstance(count, (int, float)) and count > 0:
                            zt_violations.append(
                                f"{ds_name}.{scorer_name}.zero_tolerance.{metric_name}={count}"
                            )
                # Also surface top-level zero-tol counts (e.g. key_exposure_count).
                for metric_name in _ZERO_TOLERANCE_METRICS:
                    count = scorer_metrics.get(metric_name)
                    if isinstance(count, (int, float)) and count > 0:
                        zt_violations.append(
                            f"{ds_name}.{scorer_name}.{metric_name}={count}"
                        )

        # 2. Baseline regressions.
        comparison = metrics.get("baseline_comparison", {})
        regressions = comparison.get("regressions", []) if isinstance(comparison, dict) else []
        for reg in regressions:
            regression_violations.append(f"regression:{reg}")

        violations = zt_violations + regression_violations
        return {
            "passed": not violations,
            "violations": violations,
            "zero_tolerance_passed": not zt_violations,
            "baseline_passed": not regression_violations,
        }

    # ── baseline comparison ──────────────────────────────────────────────

    def compare_with_baseline(self, eval_run: EvalRun, baseline_version: str) -> dict:
        """Compare ``eval_run`` metrics against a baseline run.

        Looks up a previous :class:`EvalRun` with the same ``target_type`` /
        ``target_id`` and ``target_version == baseline_version``. For every
        metric present in both runs, classifies the delta as improvement,
        regression, or unchanged based on whether the metric is lower- or
        higher-is-better.
        """
        baseline = self._find_baseline(eval_run.target_type, eval_run.target_id, baseline_version)
        if baseline is None:
            return {
                "baseline_version": baseline_version,
                "found": False,
                "improvements": [],
                "regressions": [],
                "unchanged": [],
                "summary": "baseline run not found",
            }

        current_flat = self._flatten_metrics(eval_run.metrics)
        baseline_flat = self._flatten_metrics(baseline.metrics)

        improvements: list[str] = []
        regressions: list[str] = []
        unchanged: list[str] = []

        for key, current_val in current_flat.items():
            if not isinstance(current_val, (int, float)):
                continue
            baseline_val = baseline_flat.get(key)
            if not isinstance(baseline_val, (int, float)):
                continue

            metric_basename = key.rsplit(".", 1)[-1]
            lower_is_better = metric_basename in _LOWER_IS_BETTER

            if current_val == baseline_val:
                unchanged.append(key)
            elif lower_is_better:
                if current_val < baseline_val:
                    improvements.append(f"{key}: {baseline_val} -> {current_val}")
                else:
                    regressions.append(f"{key}: {baseline_val} -> {current_val}")
            else:  # higher is better
                if current_val > baseline_val:
                    improvements.append(f"{key}: {baseline_val} -> {current_val}")
                else:
                    regressions.append(f"{key}: {baseline_val} -> {current_val}")

        return {
            "baseline_version": baseline_version,
            "baseline_run_id": baseline.eval_run_id,
            "found": True,
            "improvements": improvements,
            "regressions": regressions,
            "unchanged": unchanged,
            "summary": (
                f"{len(improvements)} improved, {len(regressions)} regressed, "
                f"{len(unchanged)} unchanged"
            ),
        }

    def _find_baseline(
        self,
        target_type: str,
        target_id: str,
        baseline_version: str,
    ) -> EvalRun | None:
        """Find the most recent completed run matching the baseline version.

        Searches the in-memory store first, then falls back to loading
        persisted JSON reports from ``report_dir`` so baseline comparison
        works across process restarts.
        """
        candidates = [
            run for run in self._runs.values()
            if run.target_type == target_type
            and run.target_id == target_id
            and run.target_version == baseline_version
            and run.status == "completed"
        ]
        if candidates:
            candidates.sort(
                key=lambda r: r.completed_at or datetime.min.replace(tzinfo=timezone.utc),
                reverse=True,
            )
            return candidates[0]

        # Fall back to disk: scan report_dir for matching persisted runs.
        if self.report_dir.is_dir():
            disk_candidates: list[EvalRun] = []
            for fname in self.report_dir.iterdir():
                if not fname.name.endswith(".json"):
                    continue
                try:
                    with fname.open("r", encoding="utf-8") as fh:
                        data = json.load(fh)
                    if (
                        data.get("target_type") == target_type
                        and data.get("target_id") == target_id
                        and data.get("target_version") == baseline_version
                        and data.get("status") == "completed"
                    ):
                        disk_candidates.append(EvalRun.model_validate(data))
                except Exception:
                    continue
            if disk_candidates:
                disk_candidates.sort(
                    key=lambda r: r.completed_at or datetime.min.replace(tzinfo=timezone.utc),
                    reverse=True,
                )
                return disk_candidates[0]

        return None

    @staticmethod
    def _flatten_metrics(metrics: dict, prefix: str = "") -> dict[str, float]:
        """Flatten nested metrics into ``{"a.b.c": value}`` for comparison.

        Only numeric leaves are retained; nested dicts and lists are recursed
        into, other types are dropped.
        """
        flat: dict[str, float] = {}
        for key, value in metrics.items():
            full_key = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                flat.update(EvalRunner._flatten_metrics(value, full_key))
            elif isinstance(value, (int, float)) and not isinstance(value, bool):
                flat[full_key] = float(value)
        return flat

    # ── retrieval ────────────────────────────────────────────────────────

    def get_result(self, eval_run_id: str) -> EvalRun | None:
        """Get an evaluation run by id."""
        return self._runs.get(eval_run_id)

    def list_runs(self, limit: int = 20) -> list[EvalRun]:
        """List past evaluation runs, most recent first."""
        runs = sorted(
            self._runs.values(),
            key=lambda r: r.started_at or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
        return runs[:limit]

    # ── reporting ────────────────────────────────────────────────────────

    def _write_report(self, run: EvalRun) -> None:
        """Write a JSON report for ``run`` to ``report_dir``.

        The report includes a ``failed_cases`` summary (case_id, dataset,
        reason for each non-passing case) and a ``publication_recommendation``
        (``promote`` iff the gate passed, otherwise ``block``).
        """
        path = self.report_dir / f"{run.eval_run_id}.json"
        try:
            failed_cases = [
                {
                    "case_id": r.get("case_id"),
                    "dataset": r.get("dataset"),
                    "reason": r.get("error") or "output_mismatch",
                }
                for r in run.results
                if not r.get("passed")
            ]
            gate = run.metrics.get("gate", {})
            payload = run.model_dump(mode="json")
            payload["failed_cases"] = failed_cases
            payload["publication_recommendation"] = (
                "promote" if gate.get("passed") else "block"
            )
            with path.open("w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2, ensure_ascii=False, default=str)
            logger.info("Wrote eval report to %s", path)
        except Exception:
            logger.exception("Failed to write eval report to %s", path)
