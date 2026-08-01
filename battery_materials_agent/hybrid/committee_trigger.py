"""Committee Trigger Engine — 统一的委员会触发服务。

将 ECML 中已有的 4 个触发器提取为独立服务，并新增外部证据冲突触发条件。
"""
from __future__ import annotations

import logging

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class TriggerCondition(BaseModel):
    """触发条件。"""

    trigger_type: str  # external_evidence/candidate_priority/crystal_review/deviation_review/evidence_conflict
    description: str = ""
    threshold: dict = Field(default_factory=dict)
    enabled: bool = True


class TriggerResult(BaseModel):
    """触发结果。"""

    triggered: bool
    trigger_type: str = ""
    case_id: str = ""
    reason: str = ""
    severity: str = "low"  # low/medium/high


class CommitteeTriggerEngine:
    """委员会触发引擎。

    在运行中依据结构化事实自动创建委员会 case，而非要求用户手动选择。
    """

    def __init__(self, committee_coordinator=None):
        self._coordinator = committee_coordinator
        self._conditions: dict[str, TriggerCondition] = {}
        self._init_default_conditions()

    def _init_default_conditions(self):
        """初始化默认触发条件。"""
        defaults = [
            TriggerCondition(
                trigger_type="external_evidence",
                description="Step3 外部证据辅助委员会",
                threshold={"min_evidence_count": 1},
            ),
            TriggerCondition(
                trigger_type="candidate_priority",
                description="Step4 候选优先级委员会（DFT 资源稀缺）",
                threshold={"min_candidates": 3, "dft_budget_limit": 5},
            ),
            TriggerCondition(
                trigger_type="crystal_review",
                description="Step5 晶体结构审查委员会",
                threshold={"min_controversial": 1},
            ),
            TriggerCondition(
                trigger_type="deviation_review",
                description="Step7 实验偏差复盘委员会",
                threshold={"max_deviation_pct": 15.0},
            ),
            TriggerCondition(
                trigger_type="evidence_conflict",
                description="外部证据冲突委员会（新增）",
                threshold={"min_conflicting_sources": 2},
            ),
        ]
        for cond in defaults:
            self._conditions[cond.trigger_type] = cond

    def check_external_evidence(self, state) -> TriggerResult:
        """检查是否需要触发外部证据委员会。"""
        cond = self._conditions.get("external_evidence")
        if not cond or not cond.enabled:
            return TriggerResult(triggered=False)

        external_ids = getattr(state, "external_invocation_ids", None) or []
        min_count = cond.threshold.get("min_evidence_count", 1)

        if len(external_ids) >= min_count:
            return TriggerResult(
                triggered=True,
                trigger_type="external_evidence",
                case_id=getattr(state, "run_id", "") or "",
                reason=f"检测到 {len(external_ids)} 个外部证据调用（阈值 {min_count}）",
                severity="medium",
            )
        return TriggerResult(triggered=False)

    def check_candidate_priority(
        self, state, dft_budget_remaining: int = 0
    ) -> TriggerResult:
        """检查是否需要触发候选优先级委员会。"""
        cond = self._conditions.get("candidate_priority")
        if not cond or not cond.enabled:
            return TriggerResult(triggered=False)

        candidates = getattr(state, "candidates", None) or []
        min_candidates = cond.threshold.get("min_candidates", 3)
        dft_limit = cond.threshold.get("dft_budget_limit", 5)

        if len(candidates) >= min_candidates and dft_budget_remaining < dft_limit:
            return TriggerResult(
                triggered=True,
                trigger_type="candidate_priority",
                case_id=getattr(state, "run_id", "") or "",
                reason=(
                    f"候选数量 {len(candidates)} ≥ {min_candidates}，"
                    f"DFT 预算剩余 {dft_budget_remaining} < {dft_limit}（资源稀缺）"
                ),
                severity="medium",
            )
        return TriggerResult(triggered=False)

    def check_crystal_review(self, state) -> TriggerResult:
        """检查是否需要触发晶体审查委员会。"""
        cond = self._conditions.get("crystal_review")
        if not cond or not cond.enabled:
            return TriggerResult(triggered=False)

        verified = getattr(state, "verified", None) or []
        candidates = getattr(state, "candidates", None) or []
        min_controversial = cond.threshold.get("min_controversial", 1)

        # 简化：候选数量 > 5 视为存在结构争议
        has_controversy = len(candidates) > 5 or len(verified) >= min_controversial

        if has_controversy:
            return TriggerResult(
                triggered=True,
                trigger_type="crystal_review",
                case_id=getattr(state, "run_id", "") or "",
                reason=f"晶体结构存在争议（候选 {len(candidates)}，已验证 {len(verified)}）",
                severity="medium",
            )
        return TriggerResult(triggered=False)

    def check_deviation_review(self, state) -> TriggerResult:
        """检查是否需要触发偏差复盘委员会。"""
        cond = self._conditions.get("deviation_review")
        if not cond or not cond.enabled:
            return TriggerResult(triggered=False)

        predictions = getattr(state, "predictions", None) or []
        experiment_results = getattr(state, "experiment_results", None) or []
        max_dev_pct = cond.threshold.get("max_deviation_pct", 15.0)

        max_rel_dev = 0.0
        for pred in predictions:
            pred_val = pred.get("value", 0) if isinstance(pred, dict) else 0
            for exp in experiment_results:
                measured = (
                    exp.get("measured_values", {}) if isinstance(exp, dict) else {}
                )
                for _prop, exp_val in measured.items():
                    try:
                        exp_f = float(exp_val)
                        pred_f = float(pred_val)
                        if exp_f != 0:
                            rel_dev = abs(pred_f - exp_f) / abs(exp_f) * 100
                            if rel_dev > max_rel_dev:
                                max_rel_dev = rel_dev
                    except (ValueError, TypeError):
                        continue

        if max_rel_dev > max_dev_pct:
            return TriggerResult(
                triggered=True,
                trigger_type="deviation_review",
                case_id=getattr(state, "run_id", "") or "",
                reason=f"实验偏差 {max_rel_dev:.1f}% 超过阈值 {max_dev_pct}%",
                severity="high" if max_rel_dev > max_dev_pct * 2 else "medium",
            )
        return TriggerResult(triggered=False)

    def check_evidence_conflict(self, state) -> TriggerResult:
        """检查是否需要触发外部证据冲突委员会（新增）。

        当多个外部证据来源（SCP/文献/实验）的结论存在冲突时触发。
        简化实现：检查 external_invocation_ids 中是否有多个不同 provider 的调用，
        且 predictions 中存在相反方向的结论。
        """
        cond = self._conditions.get("evidence_conflict")
        if not cond or not cond.enabled:
            return TriggerResult(triggered=False)

        external_ids = getattr(state, "external_invocation_ids", None) or []
        predictions = getattr(state, "predictions", None) or []
        min_conflicting = cond.threshold.get("min_conflicting_sources", 2)

        has_multiple_sources = len(external_ids) >= min_conflicting

        # 检查 predictions 是否存在相反方向（正值与负值共存）
        values: list[float] = []
        for pred in predictions:
            if isinstance(pred, dict):
                v = pred.get("value")
                if v is not None:
                    try:
                        values.append(float(v))
                    except (ValueError, TypeError):
                        continue

        has_conflicting_directions = False
        if len(values) >= 2:
            has_positive = any(v > 0 for v in values)
            has_negative = any(v < 0 for v in values)
            has_conflicting_directions = has_positive and has_negative

        if has_multiple_sources and has_conflicting_directions:
            return TriggerResult(
                triggered=True,
                trigger_type="evidence_conflict",
                case_id=getattr(state, "run_id", "") or "",
                reason=(
                    f"检测到 {len(external_ids)} 个外部证据来源，"
                    f"且 predictions 中存在相反方向结论"
                ),
                severity="high",
            )
        return TriggerResult(triggered=False)

    def check_all(self, state, step: str = "", **kwargs) -> list[TriggerResult]:
        """检查所有触发条件。"""
        results = []
        if not self._conditions.get(
            "external_evidence",
            TriggerCondition(trigger_type="external_evidence", enabled=False),
        ).enabled:
            return results

        # 按步骤检查
        if step in ("step3", "step3_synthesis_check", "step3_industrialization"):
            r = self.check_external_evidence(state)
            if r.triggered:
                results.append(r)

        if step in ("step4", "step4_predict"):
            r = self.check_candidate_priority(
                state, kwargs.get("dft_budget_remaining", 0)
            )
            if r.triggered:
                results.append(r)

        if step in ("step5", "step5_verify"):
            r = self.check_crystal_review(state)
            if r.triggered:
                results.append(r)

        if step in ("step7", "step7_feedback"):
            r = self.check_deviation_review(state)
            if r.triggered:
                results.append(r)

        # 证据冲突在所有步骤都检查
        r = self.check_evidence_conflict(state)
        if r.triggered:
            results.append(r)

        return results

    def update_condition(self, trigger_type: str, condition: TriggerCondition):
        """更新触发条件。"""
        self._conditions[trigger_type] = condition
