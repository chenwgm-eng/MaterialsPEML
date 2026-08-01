"""Legacy provider wrapping the existing LLMConfig for OpenAI-compatible API."""

from __future__ import annotations
import asyncio
import json
import logging
import time
import uuid
from typing import Any

import httpx

from ..config import LLMConfig
from ..integrations.audit_store import AuditStore
from ..integrations.models import ExternalInvocation
from .schemas import ChatMessage, ChatRequest, ChatResponse, ProviderHealth, Usage

logger = logging.getLogger(__name__)

_RETRYABLE_STATUSES = {429, 500, 502, 503, 504}
_MAX_RETRIES = 2
_RETRY_BACKOFF_BASE = 2.0
_MAX_RECORDS = 200


class LegacyProvider:
    """Wraps the existing LLMConfig to call OpenAI-compatible API.

    使用单例 httpx.AsyncClient 复用连接池，并对可重试错误（429/5xx、网络错误）
    进行有限次数指数退避重试。
    """

    def __init__(self, llm_config: LLMConfig):
        self._config = llm_config
        self._client: httpx.AsyncClient | None = None
        self._semaphore = asyncio.Semaphore(4)
        self._audit_store = AuditStore()

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            base_url = self._config.base_url.rstrip("/")
            # 与 internlm_provider 保持一致：base_url 以 / 结尾，请求路径使用相对路径
            if "/v1" in base_url:
                base_url = base_url + "/"
            else:
                base_url = base_url + "/v1/"
            self._client = httpx.AsyncClient(
                base_url=base_url,
                timeout=httpx.Timeout(connect=10.0, read=90.0, write=90.0, pool=10.0),
                headers={
                    "Authorization": f"Bearer {self._config.api_key}",
                    "Content-Type": "application/json",
                },
            )
        return self._client

    async def complete(self, request: ChatRequest) -> ChatResponse:
        start = time.monotonic()
        correlation_id = uuid.uuid4().hex
        invocation_id = uuid.uuid4().hex

        async with self._semaphore:
            response = await self._send_with_retry(request, correlation_id, invocation_id, start)

        # 审计记录
        latency_ms = int((time.monotonic() - start) * 1000)
        self._write_audit(
            invocation_id=invocation_id,
            correlation_id=correlation_id,
            status="success",
            input_redacted=self._redact_input(request),
            input_full=self._build_input_full(request),
            model_version=self._config.model,
            output_summary={
                "content_len": len(response.content),
                "tool_calls_count": len(response.tool_calls),
            },
            latency_ms=latency_ms,
        )
        response.invocation_id = invocation_id
        return response

    async def _send_with_retry(
        self, request: ChatRequest, correlation_id: str, invocation_id: str, start: float
    ) -> ChatResponse:
        last_error: Exception | None = None
        for attempt in range(_MAX_RETRIES + 1):
            try:
                return await self._send_once(request, correlation_id, invocation_id, start)
            except Exception as e:
                last_error = e
                if not self._is_retryable(e):
                    raise
                if attempt < _MAX_RETRIES:
                    delay = min(_RETRY_BACKOFF_BASE ** attempt, 30.0)
                    logger.warning(
                        "Legacy provider retry %d/%d after %.1fs: %s",
                        attempt + 1, _MAX_RETRIES, delay, e,
                    )
                    await asyncio.sleep(delay)

        raise last_error  # type: ignore[misc]

    async def _send_once(
        self, request: ChatRequest, correlation_id: str, invocation_id: str, start: float
    ) -> ChatResponse:
        client = self._get_client()
        endpoint = "chat/completions"

        messages = []
        for msg in request.messages:
            m: dict = {"role": msg.role, "content": msg.content}
            if msg.name:
                m["name"] = msg.name
            if msg.tool_call_id:
                m["tool_call_id"] = msg.tool_call_id
            messages.append(m)

        payload: dict = {
            "model": self._config.model,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": min(request.max_tokens, self._config.max_tokens),
        }
        if request.tools:
            payload["tools"] = request.tools
        if request.tool_choice:
            payload["tool_choice"] = request.tool_choice
        if request.response_format:
            payload["response_format"] = request.response_format

        response = await client.post(endpoint, json=payload)

        if response.status_code != 200:
            error_text = response.text[:500]
            if response.status_code in _RETRYABLE_STATUSES:
                raise httpx.HTTPStatusError(
                    f"Legacy provider HTTP {response.status_code}: {error_text}",
                    request=response.request,
                    response=response,
                )
            # 不可重试的 4xx，写审计后抛出
            latency_ms = int((time.monotonic() - start) * 1000)
            self._write_audit(
                invocation_id=invocation_id,
                correlation_id=correlation_id,
                status="failed",
                input_redacted=self._redact_input(request),
                input_full=self._build_input_full(request),
                model_version=self._config.model,
                error_code=f"HTTP_{response.status_code}",
                latency_ms=latency_ms,
            )
            raise httpx.HTTPStatusError(
                f"Legacy provider HTTP {response.status_code}: {error_text}",
                request=response.request,
                response=response,
            )

        return self._parse_response(response, request, correlation_id, invocation_id, start)

    def _parse_response(
        self,
        response: httpx.Response,
        request: ChatRequest,
        correlation_id: str,
        invocation_id: str,
        start: float,
    ) -> ChatResponse:
        # 兼容 LLM 返回非 JSON 响应（HTML 错误页、纯文本、截断 JSON 等）
        try:
            data = response.json()
        except Exception:
            raw_text = response.text or ""
            try:
                start_idx = raw_text.find("{")
                end_idx = raw_text.rfind("}") + 1
                if start_idx >= 0 and end_idx > start_idx:
                    data = json.loads(raw_text[start_idx:end_idx])
                else:
                    raise ValueError("Legacy provider response is not valid JSON")
            except Exception as parse_err:
                logger.error("Legacy provider response parse failed: %s", parse_err)
                latency_ms = int((time.monotonic() - start) * 1000)
                self._write_audit(
                    invocation_id=invocation_id,
                    correlation_id=correlation_id,
                    status="failed",
                    input_redacted=self._redact_input(request),
                    input_full=self._build_input_full(request),
                    model_version=self._config.model,
                    error_code="JSON_PARSE_ERROR",
                    latency_ms=latency_ms,
                )
                raise ValueError(
                    f"Legacy provider response is not valid JSON: {parse_err}"
                ) from parse_err

        # 兼容缺少 choices 字段的错误响应
        if "choices" not in data or not data["choices"]:
            raise ValueError(f"Legacy provider response missing 'choices' field: {data}")
        choice = data["choices"][0]
        message = choice.get("message") or {}
        content = message.get("content") or ""

        tool_calls = []
        if "tool_calls" in message:
            from .schemas import ToolCall, ToolCallFunction
            for tc in message["tool_calls"]:
                func = tc.get("function") or {}
                name = func.get("name")
                if not name:
                    logger.warning("Skipping malformed tool_call without name: %s", tc)
                    continue
                func_args = func.get("arguments", "")
                if isinstance(func_args, dict):
                    func_args = json.dumps(func_args)
                tool_calls.append(ToolCall(
                    id=tc.get("id", ""),
                    type="function",
                    function=ToolCallFunction(
                        name=name,
                        arguments=func_args,
                    ),
                ))

        usage = None
        if "usage" in data:
            u = data["usage"]
            usage = Usage(
                prompt_tokens=u.get("prompt_tokens", 0),
                completion_tokens=u.get("completion_tokens", 0),
                total_tokens=u.get("total_tokens", 0),
            )

        # 将 token 用量回写到预算系统
        if usage is not None:
            from .token_tracker import record_token_usage
            project_id = getattr(request, "metadata", {}) or {}
            if isinstance(project_id, dict):
                project_id = project_id.get("project_id", "")
            else:
                project_id = ""
            record_token_usage(
                project_id=project_id,
                model=data.get("model", self._config.model),
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
                total_tokens=usage.total_tokens,
            )

        return ChatResponse(
            content=content,
            tool_calls=tool_calls,
            usage=usage,
            model=data.get("model", self._config.model),
            request_id=data.get("id"),
        )

    async def healthcheck(self) -> ProviderHealth:
        start = time.monotonic()
        try:
            client = self._get_client()
            response = await client.get("models")
            latency_ms = int((time.monotonic() - start) * 1000)
            if response.status_code == 200:
                return ProviderHealth(status="healthy", latency_ms=latency_ms)
            return ProviderHealth(status="degraded", message=f"HTTP {response.status_code}", latency_ms=latency_ms)
        except Exception as e:
            latency_ms = int((time.monotonic() - start) * 1000)
            return ProviderHealth(status="unhealthy", message=str(e), latency_ms=latency_ms)

    def _is_retryable(self, error: Exception) -> bool:
        if isinstance(error, httpx.HTTPStatusError):
            return error.response.status_code in _RETRYABLE_STATUSES
        if isinstance(error, (httpx.ConnectError, httpx.ReadError, httpx.WriteError, httpx.PoolTimeout)):
            return True
        if isinstance(error, (httpx.RemoteProtocolError, httpx.TimeoutException)):
            return True
        return False

    def _redact_input(self, request: ChatRequest) -> dict:
        return {
            "model": request.model,
            "messages_count": len(request.messages),
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "has_tools": request.tools is not None,
            "has_response_format": request.response_format is not None,
        }

    def _build_input_full(self, request: ChatRequest) -> dict:
        """构建完整输入快照（prompt + 上下文 + 全部参数），用于审计回溯。

        包含完整 messages 数组、temperature、max_tokens、model、response_format、tools 等。
        敏感信息（API key）位于 Authorization header，不在 request 对象中，因此不会泄露。
        model 取 self._config.model（实际发送给 API 的模型，而非 request.model）。
        """
        return {
            "model": self._config.model,
            "messages": [m.model_dump(exclude_none=True) for m in request.messages],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "tools": request.tools,
            "tool_choice": request.tool_choice,
            "response_format": request.response_format,
        }

    def _write_audit(
        self,
        invocation_id: str,
        correlation_id: str,
        status: str,
        input_redacted: dict,
        input_full: dict | None = None,
        model_version: str | None = None,
        output_summary: dict | None = None,
        error_code: str | None = None,
        latency_ms: int = 0,
    ) -> None:
        try:
            record = ExternalInvocation(
                invocation_id=invocation_id,
                correlation_id=correlation_id,
                provider="legacy",
                capability="chat_completion",
                status=status,  # type: ignore[arg-type]
                input_redacted=input_redacted,
                input_full=input_full,
                model_version=model_version,
                output_summary=output_summary,
                error_code=error_code,
                latency_ms=latency_ms,
            )
            self._audit_store.append(record)
        except Exception as e:
            logger.warning("Failed to write audit record: %s", e)

    async def close(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
        self._client = None
