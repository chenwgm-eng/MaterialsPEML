"""Domain models for integration provenance and audit."""

from __future__ import annotations
from datetime import datetime, timezone
from pydantic import BaseModel, Field
from typing import Literal


class Provenance(BaseModel):
    """Traceable source information for a scientific result."""
    source_type: Literal["local", "internlm", "scp", "manual"] = "local"
    provider: str = ""
    model_or_tool: str = ""
    server_id: str | None = None
    version: str | None = None
    request_id: str | None = None
    input_sha256: str = ""
    invoked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    duration_ms: int = 0
    evidence_level: Literal["primary", "computed", "auxiliary", "draft"] = "primary"
    warnings: list[str] = Field(default_factory=list)


class ExternalInvocation(BaseModel):
    """Audit record for an external service call."""
    invocation_id: str
    correlation_id: str
    project_id: str | None = None
    run_id: str | None = None
    actor_id: str | None = None
    provider: Literal["internlm", "scp"]
    capability: str
    status: Literal["success", "failed", "blocked", "timeout"]
    input_redacted: dict = Field(default_factory=dict)
    # 完整输入快照（prompt + 上下文 + 全部参数），用于审计回溯。
    # 与 input_redacted（仅元数据，用于快速统计）互补。
    input_full: dict | None = None
    output_summary: dict | None = None
    error_code: str | None = None
    latency_ms: int = 0
    # 模型版本（来自 request.model 或 provider config），明确记录调用所用模型。
    model_version: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))