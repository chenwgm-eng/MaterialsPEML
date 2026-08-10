"""实验放行卡 API 路由。"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException

from ..auth import UserRole, require_role
from pydantic import BaseModel

from ..committee.repository import CommitteeRepository
from .generator import generate_and_save
from .metrics import compute_metrics_summary
from .models import EVIDENCE_CATEGORIES, ReleaseCard
from .store import ReleaseCardStore

router = APIRouter()

PROJECT_ROOT = Path(__file__).resolve().parents[2]

_store: ReleaseCardStore | None = None
_committee_repo: CommitteeRepository | None = None


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
async def review_release_card(card_id: str, req: ReleaseCardReviewRequest):
    """人工复核：写入复核人/意见/最终裁决，并将状态置为 decided。"""
    store = _get_store()
    card = store.get(card_id)
    if card is None:
        raise HTTPException(status_code=404, detail=f"放行卡 {card_id} 不存在")

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

    # 放行门禁闭环：agree 时回写候选 release_card_approved=True，
    # 解除实验任务创建阻断；reject/modify 不解除
    if req.final_decision == "agree" and card.candidate_id:
        try:
            # 通过 candidate_store 回写审批状态。
            # 注意：save 默认按 content_hash 去重，可能短路丢弃 data 更新（返回已存在候选），
            # 必须 dedup=False 走完整 upsert 才能把 release_card_approved 落库。
            from .. import api as _api_module
            candidate_store = _api_module.app.state.candidate_store
            record = candidate_store.get(card.candidate_id)
            if record is not None:
                cand_data = dict(record.data or {})
                cand_data["release_card_approved"] = True
                cand_data["release_card_decision"] = "agree"
                cand_data["release_card_decided_at"] = now.isoformat()
                record.data = cand_data
                candidate_store.save(record, dedup=False)
        except Exception:
            # 回写失败不影响审批结果，仅记录日志
            import logging
            logging.getLogger(__name__).warning(
                "放行卡 %s 审批通过后回写候选 %s 失败",
                card_id, card.candidate_id, exc_info=True,
            )

    return card.model_dump(mode="json")
