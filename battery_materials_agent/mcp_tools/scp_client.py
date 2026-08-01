"""SCP Client Pool — manages Streamable HTTP MCP connections to SCP servers.

Each SCP provider has its own ``server_url`` (e.g.
``https://scp.intern-ai.org.cn/api/v1/mcp/31/SciToolAgent-Chem``).
All providers share the same ``SCP_HUB_API_KEY`` — passed via the
``SCP-HUB-API-KEY`` request header.

Protocol: standard MCP **JSON-RPC 2.0** over Streamable HTTP — a single
POST to the provider endpoint with
``{"jsonrpc": "2.0", "id": n, "method": "tools/call"|"tools/list", "params": {...}}``
and an ``Accept: application/json, text/event-stream`` header. The server
may answer with plain JSON or an SSE frame; both are parsed. Reference:
https://discovery-usercenter.intern-ai.org.cn/doc

Error handling policy: **never silent**. Every failure path logs a
``WARNING``/``ERROR`` and returns a structured error dict so upstream
callers can surface the message to the user.
"""

from __future__ import annotations
import asyncio
import itertools
import json
import logging
import time
from ..config import SCPConfig

logger = logging.getLogger(__name__)


class SCPClientPool:
    """Manages Streamable HTTP MCP connections to SCP servers.

    Enforces two layers of defense at the transport boundary:
      1. allowlist checks against SCPConfig.allowed_servers / allowed_tools
         (prevents invoking unintended remote capabilities even if a caller
         crafts an arbitrary server_id/tool_name).
      2. a global concurrency semaphore (SCPConfig.max_concurrency) to keep
         the downstream SCP hub from being flooded by parallel calls.

    Note: SCPPolicy is the higher-level role/ecml-step/risk gate; this class
    only enforces transport-level allowlists. Callers should still route
    through SCPToolProxy when policy enforcement is required.
    """

    def __init__(self, config: SCPConfig):
        self.config = config
        self._sessions: dict[str, dict] = {}  # server_id -> session info
        self._rpc_ids = itertools.count(1)  # JSON-RPC request id sequence
        # Concurrency cap. A value <= 0 disables the semaphore (unbounded).
        if config.max_concurrency and config.max_concurrency > 0:
            self._semaphore: asyncio.Semaphore | None = asyncio.Semaphore(config.max_concurrency)
        else:
            self._semaphore = None

    def _check_allowlist(self, server_id: str, tool_name: str) -> str | None:
        """Return an error message if the server/tool is not allowlisted, else None.

        Empty allowlists are treated as "no transport-level filter": the
        SCPCatalog (which only enables explicitly approved bindings) remains
        the source of truth for which tools may be invoked. When an operator
        populates either allowlist, that list becomes an additional
        deny-by-default filter.
        """
        allowed_servers = self.config.allowed_servers or []
        allowed_tools = self.config.allowed_tools or []
        if allowed_servers and server_id not in allowed_servers:
            return f"server_id '{server_id}' is not in SCP_ALLOWED_SERVERS allowlist"
        if allowed_tools and tool_name not in allowed_tools:
            return f"tool_name '{tool_name}' is not in SCP_ALLOWED_TOOLS allowlist"
        return None

    def _resolve_api_key(self) -> str | None:
        """Return the SCP Hub API key, or ``None`` if not configured."""
        if self.config.api_key is not None:
            val = self.config.api_key.get_secret_value()
            if val:
                return val
        return None

    def _build_headers(self, api_key: str | None) -> dict[str, str]:
        """Build request headers with the SCP-HUB-API-KEY auth header."""
        headers = {
            "Content-Type": "application/json",
            # MCP Streamable HTTP: server may answer with JSON or SSE
            "Accept": "application/json, text/event-stream",
        }
        if api_key:
            headers["SCP-HUB-API-KEY"] = api_key
        else:
            logger.warning("SCP call attempted without SCP_HUB_API_KEY configured")
        return headers

    def _resolve_url(self, server_url: str | None) -> str:
        """Resolve the MCP endpoint for a provider.

        ``server_url`` is the per-provider endpoint (from ToolBinding.server_url).
        When provided, it takes precedence over the global ``config.base_url``.
        JSON-RPC messages are POSTed to this endpoint as-is (no path suffix).
        """
        base = server_url or self.config.base_url
        return base.rstrip("/")

    @staticmethod
    def _parse_rpc_message(resp) -> dict:
        """Parse a Streamable HTTP MCP response body into a JSON-RPC message.

        Handles both ``application/json`` and ``text/event-stream`` (SSE)
        framings; for SSE the last ``data:`` frame carries the message.
        """
        ctype = resp.headers.get("content-type", "")
        if "text/event-stream" in ctype:
            last_data = None
            for line in resp.text.splitlines():
                if line.startswith("data:"):
                    last_data = line[len("data:"):].strip()
            if not last_data:
                raise ValueError("SSE response contained no data frame")
            return json.loads(last_data)
        return resp.json()

    @staticmethod
    def _mcp_error_text(result: dict) -> str:
        """Extract a human-readable error message from an MCP result with isError=true."""
        for item in result.get("content") or []:
            if isinstance(item, dict) and item.get("type") == "text":
                return item.get("text", "")[:500]
        return "MCP tool returned isError=true"

    async def call_tool(
        self,
        server_id: str,
        tool_name: str,
        arguments: dict,
        server_url: str | None = None,
    ) -> dict:
        """调用 SCP 工具，并记录审计日志。

        审计日志以 ``SCP_AUDIT`` 前缀统一输出，包含 request_id /
        server_id / tool_name / status / elapsed，便于后续查询与分析。
        实际工具调用逻辑委托给 :meth:`_call_tool_impl`。
        """
        request_id = f"scp_{int(time.time() * 1000)}_{tool_name}"
        start_time = time.time()
        response_status = "unknown"

        try:
            result = await self._call_tool_impl(server_id, tool_name, arguments, server_url)
            if isinstance(result, dict):
                response_status = result.get("status", "unknown")
            return result
        except Exception as e:
            response_status = "failed"
            logger.error("SCP tool call failed: %s/%s - %s", server_id, tool_name, e)
            raise
        finally:
            elapsed = time.time() - start_time
            logger.info(
                "SCP_AUDIT | request_id=%s | server_id=%s | tool_name=%s | status=%s | elapsed=%.2fs",
                request_id, server_id, tool_name, response_status, elapsed,
            )
            # TODO: 持久化到 audit 表（可后续迭代）

    async def _call_tool_impl(
        self,
        server_id: str,
        tool_name: str,
        arguments: dict,
        server_url: str | None = None,
    ) -> dict:
        """Call a tool on a specific SCP server via MCP JSON-RPC.

        ``server_url`` is the per-provider endpoint from ``ToolBinding.server_url``.
        When omitted, falls back to the global ``SCPConfig.base_url``.
        """
        # Transport-level allowlist gate.
        allowlist_error = self._check_allowlist(server_id, tool_name)
        if allowlist_error:
            logger.warning("SCP allowlist denied: %s", allowlist_error)
            return {
                "status": "error",
                "error": allowlist_error,
                "server_id": server_id,
                "tool_name": tool_name,
            }

        import httpx

        api_key = self._resolve_api_key()
        if api_key is None:
            msg = "SCP_HUB_API_KEY is not configured; cannot authenticate SCP call"
            logger.error(msg)
            return {
                "status": "error",
                "error": msg,
                "server_id": server_id,
                "tool_name": tool_name,
            }

        headers = self._build_headers(api_key)

        payload = {
            "jsonrpc": "2.0",
            "id": next(self._rpc_ids),
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        }

        url = self._resolve_url(server_url)
        # httpx.Timeout 要求默认值或四项全设：以 read 为默认，connect 单独覆盖
        timeout = httpx.Timeout(
            self.config.read_timeout_seconds,
            connect=self.config.connect_timeout_seconds,
        )

        async def _do_call() -> dict:
            async with httpx.AsyncClient(timeout=timeout) as client:
                for attempt in range(self.config.max_retries + 1):
                    try:
                        start = time.monotonic()
                        resp = await client.post(url, json=payload, headers=headers)
                        elapsed_ms = int((time.monotonic() - start) * 1000)

                        if resp.status_code == 200:
                            try:
                                msg = self._parse_rpc_message(resp)
                            except Exception as exc:
                                logger.error(
                                    "SCP response parse failed: server=%s tool=%s error=%s body=%s",
                                    server_id, tool_name, exc, resp.text[:300],
                                )
                                return {
                                    "status": "error",
                                    "error": f"Invalid MCP response: {exc}",
                                    "server_id": server_id,
                                    "tool_name": tool_name,
                                    "latency_ms": elapsed_ms,
                                }
                            rpc_error = msg.get("error")
                            if rpc_error:
                                err_msg = rpc_error.get("message", str(rpc_error)) if isinstance(rpc_error, dict) else str(rpc_error)
                                logger.error(
                                    "SCP JSON-RPC error: server=%s tool=%s error=%s",
                                    server_id, tool_name, err_msg,
                                )
                                return {
                                    "status": "error",
                                    "error": f"JSON-RPC error: {err_msg}",
                                    "server_id": server_id,
                                    "tool_name": tool_name,
                                    "latency_ms": elapsed_ms,
                                }
                            result = msg.get("result") or {}
                            if result.get("isError"):
                                err_text = self._mcp_error_text(result)
                                logger.error(
                                    "SCP tool isError: server=%s tool=%s error=%s",
                                    server_id, tool_name, err_text,
                                )
                                return {
                                    "status": "error",
                                    "error": err_text,
                                    "server_id": server_id,
                                    "tool_name": tool_name,
                                    "latency_ms": elapsed_ms,
                                }
                            logger.info(
                                "SCP call success: server=%s tool=%s latency=%dms",
                                server_id, tool_name, elapsed_ms,
                            )
                            return {
                                "status": "success",
                                "data": result,
                                "server_id": server_id,
                                "tool_name": tool_name,
                                "latency_ms": elapsed_ms,
                            }
                        elif resp.status_code == 401 or resp.status_code == 403:
                            logger.error(
                                "SCP auth failed (%d) for server=%s tool=%s",
                                resp.status_code, server_id, tool_name,
                            )
                            return {
                                "status": "error",
                                "error": f"Authentication failed: {resp.status_code}",
                                "server_id": server_id,
                                "tool_name": tool_name,
                                "latency_ms": elapsed_ms,
                            }
                        elif resp.status_code >= 500 and attempt < self.config.max_retries:
                            logger.warning(
                                "SCP server %d error (attempt %d/%d): server=%s tool=%s",
                                resp.status_code, attempt + 1,
                                self.config.max_retries + 1, server_id, tool_name,
                            )
                            await asyncio.sleep(2 ** attempt)
                            continue
                        else:
                            logger.error(
                                "SCP call failed: HTTP %d, server=%s tool=%s body=%s",
                                resp.status_code, server_id, tool_name,
                                resp.text[:500],
                            )
                            return {
                                "status": "error",
                                "error": f"SCP server returned {resp.status_code}: {resp.text[:500]}",
                                "server_id": server_id,
                                "tool_name": tool_name,
                                "latency_ms": elapsed_ms,
                            }
                    except httpx.ConnectError:
                        logger.warning(
                            "SCP connection error (attempt %d/%d): url=%s",
                            attempt + 1, self.config.max_retries + 1, url,
                        )
                        if attempt < self.config.max_retries:
                            await asyncio.sleep(2 ** attempt)
                            continue
                        logger.error(
                            "SCP connection refused after %d attempts: url=%s",
                            self.config.max_retries + 1, url,
                        )
                        return {
                            "status": "error",
                            "error": f"Connection refused: {url}",
                            "server_id": server_id,
                            "tool_name": tool_name,
                        }
                    except httpx.TimeoutException:
                        logger.warning(
                            "SCP timeout (attempt %d/%d): url=%s timeout=%ds",
                            attempt + 1, self.config.max_retries + 1,
                            url, self.config.read_timeout_seconds,
                        )
                        if attempt < self.config.max_retries:
                            await asyncio.sleep(2 ** attempt)
                            continue
                        logger.error(
                            "SCP timed out after %ds: url=%s",
                            self.config.read_timeout_seconds, url,
                        )
                        return {
                            "status": "error",
                            "error": f"Request timed out after {self.config.read_timeout_seconds}s",
                            "server_id": server_id,
                            "tool_name": tool_name,
                        }
            logger.error("SCP call exhausted all retries: server=%s tool=%s", server_id, tool_name)
            return {
                "status": "error",
                "error": "Max retries exceeded",
                "server_id": server_id,
                "tool_name": tool_name,
            }

        # Enforce global concurrency cap when configured.
        if self._semaphore is not None:
            async with self._semaphore:
                return await _do_call()
        return await _do_call()

    async def list_tools(self, server_id: str, server_url: str | None = None) -> list[dict]:
        """List available tools on a server via MCP JSON-RPC ``tools/list``.

        Returns an empty list **only** on success with no tools. On failure,
        logs the error and returns an empty list with a ``_error`` entry so
        callers can distinguish "no tools" from "call failed".
        """
        import httpx

        api_key = self._resolve_api_key()
        if api_key is None:
            logger.error("SCP_HUB_API_KEY is not configured; cannot list tools for server=%s", server_id)
            return [{"_error": "SCP_HUB_API_KEY is not configured"}]

        headers = self._build_headers(api_key)

        payload = {
            "jsonrpc": "2.0",
            "id": next(self._rpc_ids),
            "method": "tools/list",
            "params": {},
        }

        url = self._resolve_url(server_url)
        # httpx.Timeout 要求默认值或四项全设：以 read 为默认，connect 单独覆盖
        timeout = httpx.Timeout(
            self.config.read_timeout_seconds,
            connect=self.config.connect_timeout_seconds,
        )

        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                resp = await client.post(url, json=payload, headers=headers)
                if resp.status_code == 200:
                    msg = self._parse_rpc_message(resp)
                    rpc_error = msg.get("error")
                    if rpc_error:
                        err_msg = rpc_error.get("message", str(rpc_error)) if isinstance(rpc_error, dict) else str(rpc_error)
                        logger.error(
                            "SCP list_tools JSON-RPC error: server=%s error=%s", server_id, err_msg,
                        )
                        return [{"_error": f"JSON-RPC error: {err_msg}"}]
                    tools = (msg.get("result") or {}).get("tools", [])
                    logger.info(
                        "SCP list_tools success: server=%s tools=%d", server_id, len(tools),
                    )
                    return tools
                logger.error(
                    "SCP list_tools failed: HTTP %d, server=%s body=%s",
                    resp.status_code, server_id, resp.text[:500],
                )
                return [{"_error": f"SCP server returned {resp.status_code}: {resp.text[:200]}"}]
            except httpx.ConnectError:
                logger.error("SCP list_tools connection error: url=%s", url)
                return [{"_error": f"Connection refused: {url}"}]
            except httpx.TimeoutException:
                logger.error(
                    "SCP list_tools timed out: url=%s timeout=%ds",
                    url, self.config.read_timeout_seconds,
                )
                return [{"_error": f"Request timed out after {self.config.read_timeout_seconds}s"}]
            except Exception as exc:
                logger.error(
                    "SCP list_tools unexpected error: server=%s error=%s",
                    server_id, exc, exc_info=True,
                )
                return [{"_error": f"Unexpected error: {exc}"}]

    async def close(self):
        """Close all sessions."""
        self._sessions.clear()
