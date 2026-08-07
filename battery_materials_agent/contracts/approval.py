"""Approval 共享契约 — 审批请求。"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    SKIPPED = "skipped"


class ApprovalRequest(BaseModel):
    """审批请求 — 证据链触发。"""

    approval_id: str = Field(default_factory=lambda: str(uuid4()))
    run_id: str
    evidence_id: str
    status: ApprovalStatus = ApprovalStatus.PENDING
    requested_by: str = ""
    reviewed_by: str | None = None
    comment: str | None = None
    reviewed_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)