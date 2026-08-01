"""委员会触发规则引擎（P1-2）。

将产品评审要求的自动触发条件落地为可配置规则：
- 触发条件A：实验-预测偏差超过阈值 → "实验偏差审核"案件
  （已在 ecml_engine._maybe_trigger_deviation_review_committee 实现）
- 触发条件B：AI 生成候选化学式未通过合法性校验 → "候选质量审核"案件
- 触发条件C：合成路径规划服务连续失败超过阈值 → "系统健康度"告警案件
- 触发条件D：高风险 AI 操作（物理执行/资源消耗类）→ "高风险AI操作"案件
  （T-031：决策 D-04，AI 自动创建实验任务单/放行样品/发布配方/下单采购
  需人工确认后再放行）

所有触发均带去重保护：同一来源（run_id / 服务 / 操作类型）已存在未结案案件时
不重复创建，避免异常风暴刷爆委员会列表。
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

from .enums import CaseStatus, CommitteeType, RiskLevel, TriggerCode
from .models import CommitteeCase

if TYPE_CHECKING:
    from .coordinator import CommitteeCoordinator

logger = logging.getLogger(__name__)

# 触发条件C：连续失败次数阈值
SYNTHESIS_FAILURE_STREAK_THRESHOLD = 3

# 触发条件D（T-031）：高风险 AI 操作类型清单
# 决策 D-04：物理执行/资源消耗类操作需人工确认，纯建议类仅标记置信度（不在此清单）
HIGH_RISK_AI_ACTION_TYPES = frozenset({
    "auto_create_experiment_order",  # AI 自动创建实验任务单
    "auto_release_sample",           # AI 自动放行样品
    "auto_publish_formula",          # AI 自动发布配方
    "auto_order_materials",          # AI 自动下单采购材料
})

# 未结案状态集合（用于触发去重）
_OPEN_STATUSES = {
    CaseStatus.PENDING,
    CaseStatus.THINKING,
    CaseStatus.EXECUTING_EVIDENCE,
    CaseStatus.VERIFYING,
    CaseStatus.REQUEST_EVIDENCE,
    CaseStatus.HUMAN_REVIEW,
}


def _has_open_case(
    coordinator: "CommitteeCoordinator",
    trigger_code: TriggerCode,
    ecml_run_id: str | None = None,
) -> bool:
    """检查是否已存在同触发码的未结案案件（可选限定到某个 ECML 运行）。"""
    open_cases = coordinator.repository.list_cases(limit=1000)
    for c in open_cases:
        if c.trigger_code != trigger_code.value:
            continue
        if c.status not in _OPEN_STATUSES:
            continue
        if ecml_run_id is not None and c.ecml_run_id != ecml_run_id:
            continue
        return True
    return False


def trigger_candidate_quality_case(
    coordinator: "CommitteeCoordinator",
    run_id: str,
    blocked_candidates: list[dict],
) -> str | None:
    """触发条件B：候选质量审核案件。

    非法候选已被 P1-1 质量门禁拦截（不会进入推荐池），本规则负责创建
    治理案件，让"AI 生成质量"问题在委员会中心可追踪、可复核。
    返回 case_id；去重命中或创建失败时返回 None。
    """
    if not blocked_candidates:
        return None
    try:
        if _has_open_case(coordinator, TriggerCode.CANDIDATE_QUALITY_INVALID, run_id):
            return None
        case = CommitteeCase(
            case_id=f"cmt-cq-{run_id}-{uuid.uuid4().hex[:6]}",
            committee_type=CommitteeType.CANDIDATE_QUALITY,
            ecml_run_id=run_id,
            candidate_id=blocked_candidates[0].get("name", ""),
            trigger_code=TriggerCode.CANDIDATE_QUALITY_INVALID.value,
            risk_level=RiskLevel.HIGH,
        )
        coordinator.repository.create_case(case)
        coordinator.event_store.append(
            case.case_id,
            "auto_triggered",
            {
                "trigger": TriggerCode.CANDIDATE_QUALITY_INVALID.value,
                "run_id": run_id,
                "blocked_count": len(blocked_candidates),
                "blocked": [
                    {"name": c.get("name", ""), "issues": c.get("quality_issues", [])}
                    for c in blocked_candidates[:10]
                ],
            },
        )
        logger.info(
            "Candidate quality case %s created: %d blocked candidates (run %s)",
            case.case_id, len(blocked_candidates), run_id,
        )
        return case.case_id
    except Exception as e:  # noqa: BLE001 - 触发失败不得阻断主流程
        logger.warning("Failed to trigger candidate quality case: %s", e)
        return None


def trigger_synthesis_health_case(
    coordinator: "CommitteeCoordinator",
    failure_streak: int,
    latest_error: str = "",
) -> str | None:
    """触发条件C：合成服务连续失败 → 系统健康度告警案件。

    同一服务告警只需一个未结案案件；去重命中或创建失败时返回 None。
    """
    if failure_streak < SYNTHESIS_FAILURE_STREAK_THRESHOLD:
        return None
    try:
        if _has_open_case(coordinator, TriggerCode.SYNTHESIS_SERVICE_FAILURE):
            return None
        case = CommitteeCase(
            case_id=f"cmt-health-{uuid.uuid4().hex[:8]}",
            committee_type=CommitteeType.SYSTEM_HEALTH,
            trigger_code=TriggerCode.SYNTHESIS_SERVICE_FAILURE.value,
            risk_level=RiskLevel.CRITICAL,
        )
        coordinator.repository.create_case(case)
        coordinator.event_store.append(
            case.case_id,
            "auto_triggered",
            {
                "trigger": TriggerCode.SYNTHESIS_SERVICE_FAILURE.value,
                "service": "ASKCOS",
                "failure_streak": failure_streak,
                "latest_error": latest_error[:500],
            },
        )
        logger.warning(
            "System health case %s created: ASKCOS failure streak = %d",
            case.case_id, failure_streak,
        )
        return case.case_id
    except Exception as e:  # noqa: BLE001 - 触发失败不得阻断主流程
        logger.warning("Failed to trigger synthesis health case: %s", e)
        return None


def _has_open_high_risk_case(
    coordinator: "CommitteeCoordinator",
    action_type: str,
) -> bool:
    """检查是否已存在同一高风险操作类型的未结案案件。

    高风险操作的 action_type 存储在 case 的 auto_triggered 事件 data 中，
    故需扫描同 trigger_code 的未结案案件事件流匹配 action_type。
    """
    open_cases = coordinator.repository.list_cases(limit=1000)
    for c in open_cases:
        if c.trigger_code != TriggerCode.HIGH_RISK_AI_ACTION.value:
            continue
        if c.status not in _OPEN_STATUSES:
            continue
        for ev in coordinator.event_store.get_events(c.case_id):
            if ev.get("event_type") != "auto_triggered":
                continue
            if ev.get("data", {}).get("action_type") == action_type:
                return True
            break  # 只需检查首个 auto_triggered 事件
    return False


def trigger_high_risk_ai_action(
    coordinator: "CommitteeCoordinator",
    action_type: str,
    action_payload: dict,
    initiator: str = "ai",
) -> str | None:
    """触发条件D（T-031）：高风险 AI 操作 → 人工确认案件。

    决策 D-04：物理执行/资源消耗类 AI 操作（自动创建实验任务单/放行样品/
    发布配方/下单采购）需人工确认后再放行；纯建议类操作不触发本规则。

    创建 case_type="high_risk_ai_action" 案件并立即置为 HUMAN_REVIEW，
    返回 case_id 供调用方阻塞等待人工审批。去重命中或创建失败时返回 None。
    """
    if action_type not in HIGH_RISK_AI_ACTION_TYPES:
        logger.warning(
            "Unknown high-risk AI action type: %s (allowed: %s)",
            action_type, sorted(HIGH_RISK_AI_ACTION_TYPES),
        )
        return None
    try:
        if _has_open_high_risk_case(coordinator, action_type):
            return None
        case = CommitteeCase(
            case_id=f"cmt-hra-{uuid.uuid4().hex[:8]}",
            committee_type=CommitteeType.HIGH_RISK_AI_ACTION,
            trigger_code=TriggerCode.HIGH_RISK_AI_ACTION.value,
            risk_level=RiskLevel.CRITICAL,
            created_by=initiator,
        )
        coordinator.repository.create_case(case)
        # 立即进入人工复审：高风险操作不走自动评估流程，等待人工 approve/reject
        coordinator.repository.update_case_status(case.case_id, CaseStatus.HUMAN_REVIEW)
        coordinator.event_store.append(
            case.case_id,
            "auto_triggered",
            {
                "trigger": TriggerCode.HIGH_RISK_AI_ACTION.value,
                "action_type": action_type,
                "initiator": initiator,
                "action_payload": action_payload,
            },
        )
        coordinator.event_store.append(
            case.case_id,
            "human_review_requested",
            {"reason": "high_risk_ai_action", "action_type": action_type},
        )
        logger.warning(
            "High-risk AI action case %s created: action=%s initiator=%s",
            case.case_id, action_type, initiator,
        )
        return case.case_id
    except Exception as e:  # noqa: BLE001 - 触发失败不得阻断主流程
        logger.warning("Failed to trigger high-risk AI action case: %s", e)
        return None

