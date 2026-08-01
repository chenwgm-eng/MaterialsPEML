"""放行卡治理指标计算。

严禁编造：任何指标在数据不足或无法从现有数据证实是，
返回 value=null 并附 reason 说明。
每个指标返回 {value, sample_size, explanation}（value 为 None 时附 reason）。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ..committee.enums import RiskLevel
from ..committee.repository import CommitteeRepository
from .models import EVIDENCE_CATEGORIES, ReleaseCard
from .store import ReleaseCardStore

# 高风险 case 的风险等级
_HIGH_RISK_LEVELS = {RiskLevel.HIGH.value, RiskLevel.CRITICAL.value}


def _metric(
    value: float | None,
    sample_size: int,
    explanation: str,
    reason: str | None = None,
) -> dict:
    m = {"value": value, "sample_size": sample_size, "explanation": explanation}
    if reason:
        m["reason"] = reason
    return m


def decision_coverage(
    store: ReleaseCardStore,
    repository: CommitteeRepository | None,
) -> dict:
    """决策覆盖率：高风险委员会 case 中已生成放行卡的比例。"""
    explanation = "高风险（high/critical）委员会 case 中，存在关联放行卡（case_id 匹配）的比例"
    if repository is None:
        return _metric(None, 0, explanation, "委员会数据不可用，无法统计高风险 case")

    cases = repository.list_cases(limit=100000)
    high_risk = [c for c in cases if c.risk_level.value in _HIGH_RISK_LEVELS]
    if not high_risk:
        return _metric(None, 0, explanation, "当前无高风险（high/critical）委员会 case")

    covered_case_ids = {c.case_id for c in store.list() if c.case_id}
    covered = sum(1 for c in high_risk if c.case_id in covered_case_ids)
    return _metric(covered / len(high_risk), len(high_risk), explanation)


def evidence_completeness(store: ReleaseCardStore) -> dict:
    """证据完备率：六类证据中至少 4 类非空的放行卡比例。"""
    explanation = "放行卡证据摘要六类（预测/实验历史/文献/成本/EHS/合成可行性）中 >=4 类非空的卡占比"
    cards = store.list()
    if not cards:
        return _metric(None, 0, explanation, "暂无放行卡数据")

    def _complete(card: ReleaseCard) -> bool:
        filled = sum(
            1 for k in EVIDENCE_CATEGORIES if card.evidence_summary.get(k)
        )
        return filled >= 4

    complete = sum(1 for c in cards if _complete(c))
    return _metric(complete / len(cards), len(cards), explanation)


def human_review_hit_rate(store: ReleaseCardStore) -> dict:
    """人工复核命中率：已裁决卡中人工最终裁决与系统推荐不一致的比例。

    final_decision=agree 视为与系统一致；modify/reject 视为不一致。
    """
    explanation = "status=decided 的放行卡中，人工 final_decision 非 agree（即 modify/reject）的比例"
    decided = [c for c in store.list(status="decided")]
    if not decided:
        return _metric(None, 0, explanation, "暂无已裁决（decided）的放行卡")

    def _mismatch(card: ReleaseCard) -> bool:
        final = (card.human_responsibility or {}).get("final_decision")
        return final is not None and final != "agree"

    mismatched = sum(1 for c in decided if _mismatch(c))
    return _metric(mismatched / len(decided), len(decided), explanation)


def rejection_accuracy(store: ReleaseCardStore) -> dict:
    """拒绝正确率：被拒绝的候选最终被证实确实不应放行的比例。

    现有数据不含拒绝后的实验验证结果（ground truth），无法证实，返回 null。
    """
    explanation = "系统 recommendation=reject 或人工 final_decision=reject 的卡中，被后续实验结果证实拒绝正确的比例"
    cards = store.list()
    rejected = sum(
        1
        for c in cards
        if c.recommendation == "reject"
        or (c.human_responsibility or {}).get("final_decision") == "reject"
    )
    return _metric(
        None,
        rejected,
        explanation,
        "现有数据未记录拒绝后的实验验证结果（ground truth），无法证实拒绝是否正确",
    )


def confidence_calibration_error(store: ReleaseCardStore) -> dict:
    """置信度校准误差：预测置信度与实际结果的一致性误差。

    现有数据缺少置信度-结果成对样本，无法计算，返回 null。
    """
    explanation = "证据置信度与实验实际结果之间的校准误差（ECE）"
    return _metric(
        None,
        0,
        explanation,
        "缺少预测置信度与实际实验结果的成对数据，无法计算校准误差",
    )


def _parse_dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def decision_latency(store: ReleaseCardStore) -> dict:
    """裁决时效：放行卡创建到人工裁决的平均秒数（仅统计 decided 卡）。"""
    explanation = "放行卡 created_at 到人工裁决 decided_at 的平均耗时（秒），仅统计 status=decided 的卡"
    decided = [c for c in store.list(status="decided")]
    durations: list[float] = []
    for card in decided:
        decided_at = _parse_dt((card.human_responsibility or {}).get("decided_at"))
        created_at = card.created_at
        if decided_at is None or created_at is None:
            continue
        durations.append((decided_at - created_at).total_seconds())

    if not durations:
        return _metric(None, 0, explanation, "暂无含裁决时间的已裁决放行卡")
    return _metric(sum(durations) / len(durations), len(durations), explanation)


def compute_metrics_summary(
    store: ReleaseCardStore,
    repository: CommitteeRepository | None = None,
) -> dict:
    """汇总全部治理指标。"""
    return {
        "decision_coverage": decision_coverage(store, repository),
        "evidence_completeness": evidence_completeness(store),
        "human_review_hit_rate": human_review_hit_rate(store),
        "rejection_accuracy": rejection_accuracy(store),
        "confidence_calibration_error": confidence_calibration_error(store),
        "decision_latency": decision_latency(store),
    }
