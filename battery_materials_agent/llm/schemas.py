"""Data models for LLM Gateway."""

from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    name: str | None = None
    tool_call_id: str | None = None


class ToolCallFunction(BaseModel):
    name: str
    arguments: str  # JSON string


class ToolCall(BaseModel):
    id: str
    type: Literal["function"] = "function"
    function: ToolCallFunction


class ChatRequest(BaseModel):
    model: str
    messages: list[ChatMessage]
    temperature: float = 0.7
    max_tokens: int = 4096
    tools: list[dict] | None = None
    tool_choice: str | dict | None = None
    response_format: dict | None = None  # for JSON mode
    # 元数据：用于 token 用量归因到项目、运行等上下文。{"project_id": "...", "run_id": "..."}
    metadata: dict | None = None


class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatResponse(BaseModel):
    content: str
    tool_calls: list[ToolCall] = []
    usage: Usage | None = None
    model: str = ""
    request_id: str | None = None
    # Audit-trace identifier emitted by the provider so callers (e.g. ECML
    # engine) can append it to ECMLState.external_invocation_ids and close
    # the audit chain. None when the provider did not write an audit record.
    invocation_id: str | None = None


class ProviderHealth(BaseModel):
    status: Literal["healthy", "degraded", "unhealthy"]
    message: str = ""
    latency_ms: int = 0