"""Run 共享契约 — 单次执行记录。"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class RunStatus(str, Enum):
    QUEUED = "queued"
    PREPARING = "preparing"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    CANCELLING = "cancelling"


_TERMINAL_STATUSES = frozenset({
    RunStatus.SUCCEEDED.value,
    RunStatus.FAILED.value,
    RunStatus.CANCELLED.value,
})


def is_terminal(status: RunStatus | str) -> bool:
    val = status.value if isinstance(status, RunStatus) else status
    return val in _TERMINAL_STATUSES


class Run(BaseModel):
    """科学服务的一次执行记录。"""

    run_id: str = Field(default_factory=lambda: str(uuid4()))
    task_id: str
    project_id: str
    service_id: str
    command: str
    status: RunStatus = RunStatus.QUEUED
    input: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)