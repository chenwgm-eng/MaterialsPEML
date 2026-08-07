"""审批管理 API 路由。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..contracts.approval import ApprovalRequest
from ..domain.runtime import ScientificExecutionKernel

router = APIRouter(prefix="/v1", tags=["approvals"])
kernel = ScientificExecutionKernel()


class ReviewRequest(BaseModel):
    reviewer: str
    comment: str = ""


@router.post("/approvals/request/{evidence_id}", response_model=ApprovalRequest)
def request_approval(evidence_id: str):
    return kernel.request_approval(evidence_id)


@router.post("/approvals/{approval_id}/approve", response_model=ApprovalRequest)
def approve(approval_id: str, req: ReviewRequest):
    return kernel.approve(approval_id, req.reviewer, req.comment)


@router.post("/approvals/{approval_id}/reject", response_model=ApprovalRequest)
def reject(approval_id: str, req: ReviewRequest):
    return kernel.reject(approval_id, req.reviewer, req.comment)


@router.get("/approvals/{approval_id}", response_model=ApprovalRequest)
def get_approval(approval_id: str):
    approval = kernel.get_approval(approval_id)
    if approval is None:
        raise HTTPException(status_code=404, detail="Approval not found")
    return approval


@router.get("/approvals", response_model=list[ApprovalRequest])
def list_approvals(run_id: str | None = None, limit: int = 50):
    return kernel.list_approvals(run_id=run_id, limit=limit)