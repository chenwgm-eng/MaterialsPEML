"""LLM Provider Protocol."""

from __future__ import annotations
from typing import Protocol, runtime_checkable
from .schemas import ChatRequest, ChatResponse, ProviderHealth


@runtime_checkable
class LLMProvider(Protocol):
    async def complete(self, request: ChatRequest) -> ChatResponse: ...
    async def healthcheck(self) -> ProviderHealth: ...