"""Tool Gateway — single chokepoint for tool invocation with auth, budget, idempotency, and provenance."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from .tool_catalog import ToolCatalog, ToolHealthStatus

logger = logging.getLogger(__name__)


class ToolInvocationResult(BaseModel):
    invocation_id: str
    tool_id: str
    status: Literal["success", "failed", "timeout", "rejected"]
    output: dict = Field(default_factory=dict)
    error: str | None = None
    latency_ms: int = 0
    provenance: dict = Field(default_factory=dict)
    idempotency_key: str | None = None
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ToolGateway:
    """Central gateway for invoking tools with policy, budget, idempotency, and provenance."""

    def __init__(
        self,
        catalog: ToolCatalog,
        policy_engine: PolicyEngine = None,
        budget=None,
        provider_registry=None,
        audit_logger=None,
    ):
        self.catalog = catalog
        self.policy_engine = policy_engine
        self.budget = budget
        self.provider_registry = provider_registry
        self.audit_logger = audit_logger
        # In-memory idempotency cache; can be replaced with Redis later.
        self._idempotency_cache: dict[str, ToolInvocationResult] = {}

    async def invoke(
        self,
        context: ExecutionContext,
        tool_id: str,
        input_data: dict,
        idempotency_key: str | None = None,
    ) -> ToolInvocationResult:
        invocation_id = uuid4().hex
        start = time.perf_counter()
        ts = datetime.now(timezone.utc).isoformat()

        # 1. Registration check
        descriptor = self.catalog.get(tool_id)
        if descriptor is None:
            return self._reject(invocation_id, tool_id, f"Tool '{tool_id}' not registered", start, ts, idempotency_key)

        # 2. Health check
        if descriptor.health_status == ToolHealthStatus.UNHEALTHY:
            return self._reject(invocation_id, tool_id, f"Tool '{tool_id}' is UNHEALTHY", start, ts, idempotency_key)
        if descriptor.health_status == ToolHealthStatus.DEGRADED:
            logger.warning("Tool '%s' is DEGRADED; proceeding with caution", tool_id)

        # 3. Authorization via PolicyEngine (fail-closed when not configured)
        if self.policy_engine is None:
            return self._reject(
                invocation_id, tool_id, "Policy engine not configured", start, ts, idempotency_key
            )
        try:
            decision = self.policy_engine.authorize(context, "tool.invoke", f"tool:{tool_id}")
            if not decision.allowed:
                return self._reject(
                    invocation_id, tool_id, "Authorization denied by policy engine", start, ts, idempotency_key
                )
        except Exception as e:
            return self._reject(invocation_id, tool_id, f"Authorization denied: {e}", start, ts, idempotency_key)

        # 4. Idempotency — derive a key if required but not supplied, then check cache.
        eff_key = idempotency_key
        if eff_key is None and descriptor.idempotency_required:
            eff_key = self._derive_idempotency_key(context, tool_id, input_data)
        if eff_key is not None:
            cached = self._check_idempotency(eff_key)
            if cached is not None:
                logger.info("Idempotent cache hit for tool '%s' key=%s", tool_id, eff_key)
                return cached

        # 5. Input validation (schema resolver not wired yet; structural check only).
        ok, err = self._validate_input(descriptor, input_data)
        if not ok:
            return self._reject(invocation_id, tool_id, f"Input validation failed: {err}", start, ts, eff_key)

        # 6. Budget reservation（签名对齐 BudgetManager.reserve(scope, scope_id, category, amount)）
        if self.budget is not None:
            try:
                from .budget import BudgetScope, BudgetCategory
                # 预算域：优先项目/用户，兜底 ORGANIZATION
                scope_id = context.project_id or context.user_id or tool_id
                scope = BudgetScope.PROJECT if context.project_id else (
                    BudgetScope.USER if context.user_id else BudgetScope.ORGANIZATION
                )
                # 风险等级 → 预算类别（A/B 高风险走 EXTERNAL_CALL，C/D 走 COST）
                risk = str(getattr(descriptor, "risk_level", "") or "")
                category = BudgetCategory.EXTERNAL_CALL if risk in ("A", "B") else BudgetCategory.COST
                amount = float(getattr(descriptor, "budget_amount", 0.0) or 0.0)
                self.budget.reserve(scope, scope_id, category, amount)
            except Exception as e:
                return self._reject(invocation_id, tool_id, f"Budget reservation failed: {e}", start, ts, eff_key)

        # 7. Execute with timeout
        try:
            handler = self._get_tool_handler(tool_id)
            output = await self._execute_with_timeout(handler, descriptor.timeout_seconds, input_data=input_data)
            status = "success"
            error = None
        except asyncio.TimeoutError:
            status = "timeout"
            output = {}
            error = f"Timeout after {descriptor.timeout_seconds}s"
        except Exception as e:
            status = "failed"
            output = {}
            error = f"{type(e).__name__}: {e}"

        latency_ms = int((time.perf_counter() - start) * 1000)

        # 8. Record provenance
        result = ToolInvocationResult(
            invocation_id=invocation_id,
            tool_id=tool_id,
            status=status,
            output=output if isinstance(output, dict) else {"value": output},
            error=error,
            latency_ms=latency_ms,
            provenance={},
            idempotency_key=eff_key,
            timestamp=ts,
        )
        result.provenance = self._record_provenance(context, tool_id, input_data, result)

        # 9. Settle budget
        if self.budget is not None:
            try:
                self.budget.settle(tool_id, status, latency_ms)
            except Exception as e:
                logger.warning("Budget settle failed for '%s': %s", tool_id, e)

        # Cache idempotent successes only (transient failures should not be cached).
        if eff_key is not None and status == "success":
            self._idempotency_cache[eff_key] = result

        # 10. Log invocation
        logger.info("Invocation %s tool=%s status=%s latency=%dms", invocation_id, tool_id, status, latency_ms)
        if self.audit_logger is not None:
            try:
                self.audit_logger.log(result)
            except Exception as e:
                logger.warning("Audit log failed for '%s': %s", tool_id, e)

        return result

    def _reject(
        self,
        invocation_id: str,
        tool_id: str,
        reason: str,
        start: float,
        ts: str,
        idempotency_key: str | None = None,
    ) -> ToolInvocationResult:
        latency_ms = int((time.perf_counter() - start) * 1000)
        result = ToolInvocationResult(
            invocation_id=invocation_id,
            tool_id=tool_id,
            status="rejected",
            error=reason,
            latency_ms=latency_ms,
            idempotency_key=idempotency_key,
            timestamp=ts,
        )
        logger.info("Invocation %s tool=%s rejected: %s", invocation_id, tool_id, reason)
        return result

    def _check_idempotency(self, key: str) -> ToolInvocationResult | None:
        return self._idempotency_cache.get(key)

    def _derive_key(self, tool_id: str, input_data: dict) -> str:
        payload = json.dumps({"tool": tool_id, "input": input_data}, sort_keys=True, default=str)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _derive_idempotency_key(self, context, tool_id: str, input_data: dict) -> str:
        """Derive an idempotency key scoped to the caller's project and user.

        Including ``project_id`` and ``user_id`` prevents the same tool input
        from being deduplicated across different users or projects.
        """
        payload = json.dumps(
            {
                "tool": tool_id,
                "input": input_data,
                "project_id": context.project_id,
                "user_id": context.user_id,
            },
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _validate_input(self, descriptor, input_data: dict) -> tuple[bool, str | None]:
        if not isinstance(input_data, dict):
            return False, "input_data must be a dict"
        # Schema-based validation is a hook; a schema resolver is not wired yet.
        return True, None

    def _get_tool_handler(self, tool_id: str):
        # Prefer a real handler from the provider registry if available.
        if self.provider_registry is not None:
            getter = getattr(self.provider_registry, "get_handler", None)
            if getter is not None:
                handler = getter(tool_id)
                if handler is not None:
                    return handler

        descriptor = self.catalog.get(tool_id)
        if descriptor is None:
            raise KeyError(f"Tool '{tool_id}' not registered")

        # Placeholder mock handler for registered tools.
        async def _mock_handler(input_data: dict, **kwargs):
            return {"mock": True, "tool_id": tool_id, "input": input_data}

        return _mock_handler

    async def _execute_with_timeout(self, func, timeout_seconds: int, **kwargs):
        if asyncio.iscoroutinefunction(func):
            return await asyncio.wait_for(func(**kwargs), timeout=timeout_seconds)
        # Sync handler — run in a worker thread.
        return await asyncio.wait_for(asyncio.to_thread(func, **kwargs), timeout=timeout_seconds)

    def _record_provenance(self, context, tool_id: str, input_data: dict, result: ToolInvocationResult) -> dict:
        descriptor = self.catalog.get(tool_id)
        return {
            "invocation_id": result.invocation_id,
            "tool_id": tool_id,
            "source": descriptor.source if descriptor else None,
            "risk_level": descriptor.risk_level.value if descriptor else None,
            "version": descriptor.version if descriptor else None,
            "status": result.status,
            "latency_ms": result.latency_ms,
            "timestamp": result.timestamp,
            "input_hash": self._derive_key(tool_id, input_data),
            "role": context.user_role,
            "agent_id": context.agent_id,
            "ecml_run_id": context.ecml_run_id,
        }
