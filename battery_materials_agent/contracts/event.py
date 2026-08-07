"""DomainEvent 共享契约 — 领域事件。"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class DomainEvent(BaseModel):
    """领域事件 — 用于科学执行内核的事件总线。"""

    event_id: str = Field(default_factory=lambda: str(uuid4()))
    event_type: str
    source: str  # 服务标识
    subject_id: str  # 关联的 task_id 或 run_id
    project_id: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))