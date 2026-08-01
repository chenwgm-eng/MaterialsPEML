"""Provider factory for creating LLM providers based on engine mode."""

from __future__ import annotations
from ..config import AgentConfig, EngineMode
from .base import LLMProvider


class ProviderFactory:
    @staticmethod
    def create(config: AgentConfig) -> LLMProvider:
        mode = config.engine_mode
        if mode == EngineMode.INTERNLM:
            from .internlm_provider import InternLMProvider
            return InternLMProvider(config.internlm)
        # Legacy mode: return a provider that wraps config.llm
        from .legacy_provider import LegacyProvider
        return LegacyProvider(config.llm)