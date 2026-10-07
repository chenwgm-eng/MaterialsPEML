"""实验放行卡 API 路由。"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Literal

from fastapi import APIRouter, Depends, HTTPException

from ..audit import AuditEntry, get_audit_logger
from ..auth import User, UserRole, get_current_user, require_role
from pydantic import BaseModel

from ..committee.repository import CommitteeRepository
from .generator import generate_and_save
from .metrics import compute_metrics_summary
from .models import EVIDENCE_CATEGORIES, ReleaseCard
from .store import ReleaseCardStore

logger = logging.getLogger(__name__)

router = APIRouter()

PROJECT_ROOT = Path(__file__).resolve().parents[2]

_store: ReleaseCardStore | None = None
_committee_repo: CommitteeRepository | None = None
# 候选存储注入点：由应用启动时注入（api.py startup），
# 替代反向 `from .. import api` 取 app.state（领域路由不得依赖 API 单体）
_candidate_store_provider = None

# T11：补偿通知注入点（由应用启动时注入，向 notifications 表写补偿任务）
_notification_sink: Callable[[str, str, str], None] | None = None


def set_candidate_store(store) -> None:
    global _candidate_store_provider
    _candidate_store_provider = store


def set_notification_sink(sink: Callable[[str, str, str], None] | None) -> None:
    global _notification_sink
    _notification_sink = sink


def _get_store() -> ReleaseCardStore:
    global _store
    if _store is None:
        _store = ReleaseCardStore()
    return _store


def _get_committee_repo() -> CommitteeRepository:
    global _committee_repo
    if _committee_repo is None:
        _committee_repo = CommitteeRepository(
            db_path=str(PROJECT_ROOT / "data" / "committee.db")
        )
    return _committee_repo


class ReleaseCardCreateRequest(BaseModel):
    """创建放行卡：传 case_id 则从委员会 case 生成，否则按手工字段创建。"""

    case_id: str | None = None
    project_id: str | None = None
    candidate_id: str | None = None
    title: str | None = None
    recommendation: str | None = None
    target_window: dict | None = None
    evidence_summary: dict | None = None
    uncertainty: dict | None = None
    suggested_experiments: list[dict] | None = None
    stop_conditions: list[str] | None = None
    provenance: dict | None = None
    status: str | None = None


class ReleaseCardReviewRequest(BaseModel):
    """人工复核：写入人工责任并置为已裁决。"""

    reviewer: str
    review_opinion: str = ""
    final_decision: Literal["agree", "modify", "reject"]


# ── POST /release-cards ──

@router.post("/release-cards", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def create_release_card(req: ReleaseCardCreateRequest):
    """创建放行卡（可传 case_id 从委员会生成，或手工字段创建）。"""
    store = _get_store()

    if req.case_id:
        card = generate_and_save(req.case_id, store=store, repository=_get_committee_repo())
        if card is None:
            raise HTTPException(status_code=404, detail=f"委员会 Case {req.case_id} 不存在")
        return card.model_dump(mode="json")

    card = ReleaseCard(
        card_id=f"rc-{uuid.uuid4().hex[:8]}",
        case_id=None,
        project_id=req.project_id,
        candidate_id=req.candidate_id,
        title=req.title or "手工创建的实验放行卡",
        recommendation=req.recommendation or "need_evidence",
        target_window=req.target_window or {},
        evidence_summary=req.evidence_summary or {k: None for k in EVIDENCE_CATEGORIES},
        uncertainty=req.uncertainty or {},
        suggested_experiments=req.suggested_experiments or [],
        stop_conditions=req.stop_conditions or [],
        provenance=req.provenance or {},
        status=req.status or "draft",
    )
    try:
        store.create(card)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return card.model_dump(mode="json")


# ── GET /release-cards/metrics/summary ──
# 注意：必须注册在 /release-cards/{card_id} 之前，避免被路径参数捕获

@router.get("/release-cards/metrics/summary")
async def release_card_metrics_summary():
    """放行卡治理指标汇总。"""
    try:
        repository = _get_committee_repo()
    except Exception:
        repository = None
    return compute_metrics_summary(_get_store(), repository)


# ── GET /release-cards ──

@router.get("/release-cards")
async def list_release_cards(
    status: str | None = None,
    recommendation: str | None = None,
    project_id: str | None = None,
    case_id: str | None = None,
    limit: int = 200,
    offset: int = 0,
):
    """列出放行卡，可按 status / recommendation / project_id / case_id 过滤。"""
    cards = _get_store().list(
        status=status,
        recommendation=recommendation,
        project_id=project_id,
        case_id=case_id,
        limit=limit,
        offset=offset,
    )
    return {"items": [c.model_dump(mode="json") for c in cards], "count": len(cards)}


# ── GET /release-cards/{card_id} ──

@router.get("/release-cards/{card_id}")
async def get_release_card(card_id: str):
    """获取放行卡详情。"""
    card = _get_store().get(card_id)
    if card is None:
        raise HTTPException(status_code=404, detail=f"放行卡 {card_id} 不存在")
    return card.model_dump(mode="json")


# ── POST /release-cards/{card_id}/review ──

@router.post("/release-cards/{card_id}/review", dependencies=[Depends(require_role(UserRole.RESEARCHER))])
async def review_release_card(
    card_id: str,
    req: ReleaseCardReviewRequest,
    current: User | None = Depends(get_current_user),
):
    """人工复核：写入复核人/意见/最终裁决，并将状态置为 decided。"""
    store = _get_store()
    card = store.get(card_id)
    if card is None:
        raise HTTPException(status_code=404, detail=f"放行卡 {card_id} 不存在")
    # 审计操作者绑定登录身份，请求体 reviewer 仅作展示用途（防伪造审计主体）
    operator = (current.username if current else "") or req.reviewer or "unknown"

    now = datetime.now(timezone.utc)
    card.human_responsibility = {
        "reviewer": req.reviewer,
        "review_opinion": req.review_opinion,
        "final_decision": req.final_decision,
        "decided_at": now.isoformat(),
    }
    card.status = "decided"
    card.updated_at = now
    try:
        store.update(card)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # 裁决即审计：放行/否决是解除或维持实验阻断的核心合规动作，
    # 无论后续候选回写成败都必须留痕
    try:
        get_audit_logger().log(AuditEntry(
            event_type="decision",
            module="release_card",
            action=f"review_{req.final_decision}",
            detail={
                "card_id": card_id,
                "candidate_id": card.candidate_id,
                "final_decision": req.final_decision,
                "reviewer_declared": req.reviewer,
                "review_opinion": req.review_opinion,
            },
            operator=operator,
            confirmed=True,
            resource_type="release_card",
            resource_id=card_id,
        ))
    except Exception:
        logger.warning("放行卡 %s 裁决审计写入失败", card_id, exc_info=True)

    # 放行门禁闭环：agree 时回写候选 release_card_approved=True，
    # 解除实验任务创建阻断；reject/modify 不解除
    if req.final_decision == "agree" and card.candidate_id:
        try:
            # 通过 candidate_store 回写审批状态。
            # 注意：save 默认按 content_hash 去重，可能短路丢弃 data 更新（返回已存在候选），
            # 必须 dedup=False 走完整 upsert 才能把 release_card_approved 落库。
            candidate_store = _candidate_store_provider
            if candidate_store is None:
                raise RuntimeError("candidate_store 未注入（应用启动配置错误）")
            record = candidate_store.get(card.candidate_id)
            if record is not None:
                cand_data = dict(record.data or {})
                cand_data["release_card_approved"] = True
                cand_data["release_card_decision"] = "agree"
                cand_data["release_card_decided_at"] = now.isoformat()
                record.data = cand_data
                candidate_store.save(record, dedup=False)
        except Exception:
            # Q10 补偿：候选回写失败时经专用通道回退卡状态（decided 是终态，
            # 必须走 store.rollback_decided 补偿通道，普通 update 会因状态机拒绝而失效）
            logger.error(
                "放行卡 %s 审批通过后回写候选 %s 失败，尝试补偿回退卡状态", card_id, card.candidate_id, exc_info=True,
            )
            # T11：补偿任务入库。失败后卡状态可回滚，但运维必须能看到需要人工对账的补偿任务。
            if _notification_sink is not None:
                try:
                    _notification_sink(
                        f"RC-FAIL-{card_id}",
                        "admin",
                        f"放行卡审批回写候选失败需补偿：card={card_id}, candidate={card.candidate_id}, decision={req.final_decision}",
                    )
                except Exception:
                    logger.error("放行卡 %s 补偿通知写入失败", card_id, exc_info=True)
            rollback_reason = f"候选 {card.candidate_id} 回写失败，自动补偿回退"
            try:
                store.rollback_decided(card_id, reason=rollback_reason)
                rolled_back = True
            except Exception:
                logger.critical(
                    "放行卡 %s 补偿回退失败，卡保持 decided 但候选未解锁，需人工处理",
                    card_id,
                    exc_info=True,
                )
                rolled_back = False
            if rolled_back:
                raise HTTPException(
                    status_code=500,
                    detail="放行卡审批通过但候选回写失败，卡状态已回滚为待审批，可重试复核",
                )
            raise HTTPException(
                status_code=500,
                detail=(
                    f"放行卡 {card_id} 审批通过但候选回写失败，且补偿回退失败："
                    "卡保持已裁决状态、候选未解锁，请联系管理员人工处理该候选的放行标记"
                ),
            )

    return card.model_dump(mode="json")
