"""研发收益计算核心。

铁律：每个指标输出 {value, kind: verified|estimated, assumption, evidence_refs}。
- verified：直接来自系统真实数据（项目/实验任务单/样品记录）。
- estimated：基于基线或成本规则的推算，assumption 必须写明假设与公式。
- 数据不足：value=None，kind=verified，assumption 写明缺什么数据。严禁编造数字。
"""

from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path

from ..projects import ProjectStore
from ..experiment.experiment_controller import ExperimentDataStore
from ..experiment.sample_store import SampleStore
from .models import MetricValue, ProjectBaseline
from .store import ValueRealizationStore, DATA_DIR


def _parse_dt(value: str | datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


async def compute_value_report(
    project_id: str,
    data_dir: str | Path | None = None,
    vr_store: ValueRealizationStore | None = None,
) -> dict:
    """计算指定项目的研发收益账单。"""
    data_dir = Path(data_dir) if data_dir else DATA_DIR
    vr_store = vr_store or ValueRealizationStore(str(data_dir / "value_realization.db"))

    project_store = ProjectStore(str(data_dir / "projects.db"))
    project = project_store.get(project_id)
    baseline: ProjectBaseline | None = vr_store.get_baseline(project_id)

    # 使用实验任务单（experiment.experiment_orders）而非项目任务（projects.tasks），
    # 因为收益账单需要 order_id / candidate_id / created_at 字段。
    experiment_store = ExperimentDataStore(str(data_dir / "experiments.db"))
    orders = experiment_store.list_orders(project_id=project_id) if project else []
    order_ids = [o.order_id for o in orders]
    candidate_ids = list(project.candidate_ids) if project else []

    sample_store = SampleStore(str(data_dir / "samples.db"))
    cand_set = set(candidate_ids)
    order_set = set(order_ids)
    project_samples = [
        s for s in sample_store.list_all()
        if (s.source_candidate_id and s.source_candidate_id in cand_set)
        or (s.source_order_id and s.source_order_id in order_set)
    ]
    sample_ids = [s.sample_id for s in project_samples]

    metrics: dict[str, dict[str, MetricValue]] = {
        "candidate_convergence": {},
        "experiment_savings": {},
        "cycle_efficiency": {},
        "economic_value": {},
    }

    # ---------- 候选收敛（verified） ----------
    cc = metrics["candidate_convergence"]
    if project is None:
        for key, label in [
            ("total_candidates", "初始候选数"), ("entered_experiment_candidates", "进入实验数"),
            ("eliminated_candidates", "淘汰数"), ("hit_candidates", "命中数"),
        ]:
            cc[key] = MetricValue(label=label, unit="个", value=None, kind="verified",
                                  assumption=f"项目 {project_id} 不存在，无法取得{label}")
    else:
        total = len(candidate_ids)
        cc["total_candidates"] = MetricValue(
            label="初始候选数", unit="个", value=total, kind="verified",
            evidence_refs=[project_id])
        entered_ids = sorted({
            o.candidate_id for o in orders
            if o.candidate_id and (not cand_set or o.candidate_id in cand_set)
        })
        cc["entered_experiment_candidates"] = MetricValue(
            label="进入实验数", unit="个", value=len(entered_ids), kind="verified",
            evidence_refs=[o.order_id for o in orders if o.candidate_id in entered_ids])
        cc["eliminated_candidates"] = MetricValue(
            label="淘汰数", unit="个", value=total - len(entered_ids), kind="verified",
            assumption="淘汰数=初始候选数-进入实验数" if total or entered_ids else None,
            evidence_refs=[project_id])
        hit_ids = sorted({
            s.source_candidate_id for s in project_samples
            if s.source_candidate_id and (not cand_set or s.source_candidate_id in cand_set)
        })
        cc["hit_candidates"] = MetricValue(
            label="命中数", unit="个", value=len(hit_ids), kind="verified",
            assumption="命中数=已产出样品的候选数（未校验成功标准达标情况）",
            evidence_refs=[s.sample_id for s in project_samples if s.source_candidate_id in hit_ids])

    # ---------- 实验节省 ----------
    es = metrics["experiment_savings"]
    actual = len(orders)
    es["actual_experiments"] = MetricValue(
        label="实际实验数", unit="次", value=actual if project else None, kind="verified",
        assumption=None if project else f"项目 {project_id} 不存在，无法统计实验任务",
        evidence_refs=order_ids)

    baseline_expected: int | None = None
    if baseline and baseline.past_candidate_count > 0:
        baseline_expected = baseline.past_candidate_count
        es["baseline_expected_experiments"] = MetricValue(
            label="基线预期实验数", unit="次", value=baseline_expected, kind="estimated",
            assumption=f"按历史基线估算：历史流程中每个候选需一次实验，预期实验数=历史典型候选数 {baseline.past_candidate_count}",
            evidence_refs=[f"baseline:{project_id}"])
    else:
        es["baseline_expected_experiments"] = MetricValue(
            label="基线预期实验数", unit="次", value=None, kind="verified",
            assumption="缺少基线数据 past_candidate_count（历史典型候选数），无法估算基线预期实验数")

    if baseline_expected is not None and project is not None:
        avoided = baseline_expected - actual
        es["avoided_experiments"] = MetricValue(
            label="避免实验数", unit="次", value=avoided, kind="estimated",
            assumption=f"避免实验数=基线预期实验数 {baseline_expected} - 实际实验数 {actual}（负值表示超出基线）",
            evidence_refs=[f"baseline:{project_id}"] + order_ids)
        if baseline and baseline.typical_experiment_cost > 0:
            es["saved_cost"] = MetricValue(
                label="节省实验成本", unit="元", value=round(avoided * baseline.typical_experiment_cost, 2),
                kind="estimated",
                assumption=f"节省成本=避免实验数 {avoided} × 基线单次实验典型成本 {baseline.typical_experiment_cost} 元",
                evidence_refs=[f"baseline:{project_id}"])
        else:
            es["saved_cost"] = MetricValue(
                label="节省实验成本", unit="元", value=None, kind="verified",
                assumption="缺少基线数据 typical_experiment_cost（单次实验典型成本），无法估算节省成本")
    else:
        es["avoided_experiments"] = MetricValue(
            label="避免实验数", unit="次", value=None, kind="verified",
            assumption="缺少基线预期实验数，无法计算避免实验数")
        es["saved_cost"] = MetricValue(
            label="节省实验成本", unit="元", value=None, kind="verified",
            assumption="缺少避免实验数或基线单次实验典型成本，无法估算节省成本")

    # ---------- 周期效率 ----------
    ce = metrics["cycle_efficiency"]
    order_times = [t for t in (_parse_dt(o.created_at) for o in orders) if t]
    span_days: float | None = None
    if len(order_times) >= 2:
        span_days = round((max(order_times) - min(order_times)).total_seconds() / 86400.0, 2)
        ce["experiment_span_days"] = MetricValue(
            label="实验时间跨度", unit="天", value=span_days, kind="verified",
            evidence_refs=order_ids)
        ce["avg_days_per_experiment"] = MetricValue(
            label="平均每实验周期", unit="天", value=round(span_days / actual, 2), kind="verified",
            assumption="平均每实验周期=实验时间跨度/实际实验数", evidence_refs=order_ids)
    elif len(order_times) == 1:
        span_days = 0.0
        ce["experiment_span_days"] = MetricValue(
            label="实验时间跨度", unit="天", value=0.0, kind="verified",
            assumption="仅有 1 个实验任务，时间跨度按 0 计", evidence_refs=order_ids)
        ce["avg_days_per_experiment"] = MetricValue(
            label="平均每实验周期", unit="天", value=None, kind="verified",
            assumption="仅有 1 个实验任务，无法计算平均每实验周期")
    else:
        ce["experiment_span_days"] = MetricValue(
            label="实验时间跨度", unit="天", value=None, kind="verified",
            assumption="无实验任务创建时间数据，无法计算实验时间跨度")
        ce["avg_days_per_experiment"] = MetricValue(
            label="平均每实验周期", unit="天", value=None, kind="verified",
            assumption="无实验任务创建时间数据，无法计算平均每实验周期")

    project_start = _parse_dt(project.created_at) if project else None
    sample_times = [t for t in (_parse_dt(s.created_at) for s in project_samples) if t]
    if project_start and sample_times:
        ce["days_to_first_sample"] = MetricValue(
            label="首个样品时间", unit="天",
            value=round((min(sample_times) - project_start).total_seconds() / 86400.0, 2),
            kind="verified", assumption="首个样品时间=最早样品创建时间-项目创建时间",
            evidence_refs=[min(project_samples, key=lambda s: s.created_at).sample_id, project_id])
    else:
        ce["days_to_first_sample"] = MetricValue(
            label="首个样品时间", unit="天", value=None, kind="verified",
            assumption="缺少项目创建时间或项目关联样品记录，无法计算首个样品时间")

    if baseline and baseline.historical_cycle_days > 0 and span_days is not None:
        ce["cycle_saved_vs_baseline"] = MetricValue(
            label="较基线缩短周期", unit="天",
            value=round(baseline.historical_cycle_days - span_days, 2), kind="estimated",
            assumption=f"较基线缩短周期=基线历史筛选周期 {baseline.historical_cycle_days} 天 - 本项目实验时间跨度 {span_days} 天（负值表示超出基线）",
            evidence_refs=[f"baseline:{project_id}"] + order_ids)
    else:
        ce["cycle_saved_vs_baseline"] = MetricValue(
            label="较基线缩短周期", unit="天", value=None, kind="verified",
            assumption="缺少基线数据 historical_cycle_days（历史筛选周期）或实验时间跨度，无法对比基线周期")

    # ---------- 经济收益（estimated） ----------
    ev = metrics["economic_value"]
    saved_cost = es["saved_cost"].value
    ev["total_saved_cost"] = MetricValue(
        label="实验节约总成本", unit="元",
        value=saved_cost if saved_cost is not None else None,
        kind="estimated" if saved_cost is not None else "verified",
        assumption=("实验节约总成本=节省实验成本（来自实验节省分组）" if saved_cost is not None
                    else "缺少节省实验成本数据，无法汇总实验节约总成本"),
        evidence_refs=es["saved_cost"].evidence_refs)
    if baseline and baseline.typical_experiment_cost > 0 and project is not None:
        actual_cost = round(actual * baseline.typical_experiment_cost, 2)
        ev["actual_experiment_cost"] = MetricValue(
            label="实际实验投入(估算)", unit="元", value=actual_cost, kind="estimated",
            assumption=f"实际实验投入=实际实验数 {actual} × 基线单次实验典型成本 {baseline.typical_experiment_cost} 元",
            evidence_refs=[f"baseline:{project_id}"] + order_ids)
        if saved_cost is not None and actual_cost > 0:
            ev["roi_estimate"] = MetricValue(
                label="预期ROI(估算)", unit="倍", value=round(saved_cost / actual_cost, 2),
                kind="estimated",
                assumption=f"预期ROI=实验节约总成本 {saved_cost} 元 / 实际实验投入 {actual_cost} 元（基于基线成本假设，非财务审计值）",
                evidence_refs=[f"baseline:{project_id}"])
        else:
            ev["roi_estimate"] = MetricValue(
                label="预期ROI(估算)", unit="倍", value=None, kind="verified",
                assumption="缺少实验节约总成本或实际实验投入为 0，无法估算预期ROI")
    else:
        ev["actual_experiment_cost"] = MetricValue(
            label="实际实验投入(估算)", unit="元", value=None, kind="verified",
            assumption="缺少基线数据 typical_experiment_cost（单次实验典型成本），无法估算实际实验投入")
        ev["roi_estimate"] = MetricValue(
            label="预期ROI(估算)", unit="倍", value=None, kind="verified",
            assumption="缺少实际实验投入估算，无法计算预期ROI")

    # ---------- 汇总 ----------
    assumptions = []
    evidence_refs: list[str] = []
    for section in metrics.values():
        for m in section.values():
            if m.kind == "estimated" and m.assumption:
                assumptions.append({"metric": m.label, "assumption": m.assumption})
            elif m.value is None and m.assumption:
                assumptions.append({"metric": m.label, "assumption": f"【数据不足】{m.assumption}"})
            for ref in m.evidence_refs:
                if ref not in evidence_refs:
                    evidence_refs.append(ref)

    return {
        "project_id": project_id,
        "project_name": project.name if project else "",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "baseline": baseline.model_dump() if baseline else None,
        "sections": {
            "candidate_convergence": {
                "title": "候选收敛",
                "metrics": {k: m.model_dump() for k, m in metrics["candidate_convergence"].items()},
            },
            "experiment_savings": {
                "title": "实验节省",
                "metrics": {k: m.model_dump() for k, m in metrics["experiment_savings"].items()},
            },
            "cycle_efficiency": {
                "title": "周期效率",
                "metrics": {k: m.model_dump() for k, m in metrics["cycle_efficiency"].items()},
            },
            "economic_value": {
                "title": "经济收益",
                "metrics": {k: m.model_dump() for k, m in metrics["economic_value"].items()},
            },
        },
        "assumptions": assumptions,
        "evidence_refs": evidence_refs,
    }
