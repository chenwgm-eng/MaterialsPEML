"""实验放行卡（Release Card）数据模型。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

Recommendation = Literal["recommend", "conditional", "need_evidence", "human_review", "reject"]
CardStatus = Literal["draft", "pending_review", "decided"]

# 证据摘要的六个类别
EVIDENCE_CATEGORIES = (
    "prediction",           # 预测
    "experiment_history",   # 实验历史
    "literature",           # 文献
    "cost",                 # 成本
    "ehs",                  # EHS
    "synthesis_feasibility",  # 合成可行性
)


def _default_evidence_summary() -> dict:
    return {k: None for k in EVIDENCE_CATEGORIES}


def _default_human_responsibility() -> dict:
    return {"reviewer": None, "review_opinion": None, "final_decision": None, "decided_at": None}


class ReleaseCard(BaseModel):
    """实验放行卡：研发人员可直接执行的决策载体。"""

    card_id: str
    case_id: str | None = None        # 关联的委员会 case，可空
    project_id: str | None = None
    candidate_id: str | None = None
    title: str = ""
    recommendation: Recommendation = "need_evidence"
    # 目标与成功窗口：metrics / success_range / min_viable_outcome
    target_window: dict = Field(default_factory=dict)
    # 证据摘要：六类，每类可空（None 表示未提供）
    evidence_summary: dict = Field(default_factory=_default_evidence_summary)
    # 不确定性：applicability_domain / data_gaps / key_assumptions / failure_modes
    uncertainty: dict = Field(default_factory=dict)
    # 推荐实验：recipe / conditions / sample_count / priority / equipment / estimated_cost
    suggested_experiments: list[dict] = Field(default_factory=list)
    stop_conditions: list[str] = Field(default_factory=list)
    # 人工责任：reviewer / review_opinion / final_decision / decided_at
    human_responsibility: dict = Field(default_factory=_default_human_responsibility)
    # 溯源：run_id / model_versions / data_versions / rule_versions / audit_refs
    provenance: dict = Field(default_factory=dict)
    status: CardStatus = "draft"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
