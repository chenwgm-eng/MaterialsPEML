"""Artifact 共享契约 — 科学服务执行产生的结构化输出。"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class ArtifactType(str, Enum):
    INPUT_TABLE = "input_table"
    RESULT_TABLE = "result_table"
    STRUCTURE = "structure"
    REPORT = "report"
    PLOT = "plot"
    LOG = "log"
    CHECKPOINT = "checkpoint"
    OTHER = "other"


class Artifact(BaseModel):
    """科学服务执行产生的工件。"""

    artifact_id: str = Field(default_factory=lambda: str(uuid4()))
    run_id: str
    type: ArtifactType
    name: str
    description: str = ""
    content_type: str = "application/json"
    data: dict[str, Any] | None = None
    file_path: str | None = None
    checksum: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))