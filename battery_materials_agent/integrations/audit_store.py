"""Audit store for persisting external invocation records."""

from __future__ import annotations
import hashlib
import json
from datetime import datetime
from pathlib import Path

from sqlalchemy import text

from ..db import get_engine
from .models import ExternalInvocation, Provenance

# 兼容旧调用：保留 DB_PATH 常量但迁移至 PostgreSQL 后已忽略，统一使用全局 Engine。
DB_PATH = Path("data/integration_audit.db")


class AuditStore:
    """Persists external invocation audit records to PostgreSQL.

    Schema: integrations.external_invocations（由 alembic 管理）。
    Append-only 语义通过应用层 API 表面保障：仅暴露 append/query/get_by_id，
    不提供 update/delete 方法。如需数据库级保障，应在 alembic 迁移中创建
    BEFORE UPDATE/DELETE 触发器，而非在 Store 类中 ad-hoc 创建。
    """

    def __init__(self, db_path: str | Path | None = None):
        # db_path 参数保留以兼容旧调用方，迁移至 PostgreSQL 后已忽略，统一使用全局 Engine。
        self.engine = get_engine()

    @staticmethod
    def _row_to_dict(row) -> dict:
        d = dict(row._mapping)
        # JSONB 列经 psycopg3 通常已返回 Python 对象；防御性处理 str 情况。
        # input_full_json 为 TEXT 列（非 JSONB），始终返回 str，需手动解析。
        for json_field in ("input_redacted_json", "output_summary_json", "input_full_json"):
            v = d.get(json_field)
            if isinstance(v, str):
                try:
                    d[json_field] = json.loads(v)
                except (json.JSONDecodeError, TypeError):
                    pass
        # 兼容旧 API 契约：created_at 返回 ISO 字符串
        if isinstance(d.get("created_at"), datetime):
            d["created_at"] = d["created_at"].isoformat()
        return d

    def append(self, invocation: ExternalInvocation) -> str:
        """Append an audit record. Returns the invocation_id for caller-side tracking.

        Append-only semantics: rows must never be UPDATEd or DELETEd after insert.
        """
        input_redacted_json = json.dumps(invocation.input_redacted, ensure_ascii=False)
        output_summary_json = (
            json.dumps(invocation.output_summary, ensure_ascii=False)
            if invocation.output_summary else None
        )
        # input_full_json：TEXT 列（非 JSONB），存放完整输入快照。
        # 审计需求优先于存储优化，可能较大但保留完整 prompt/上下文/参数。
        input_full_json = (
            json.dumps(invocation.input_full, ensure_ascii=False)
            if invocation.input_full is not None else None
        )
        input_sha256 = hashlib.sha256(
            json.dumps(invocation.input_redacted, sort_keys=True).encode()
        ).hexdigest()

        with self.engine.begin() as conn:
            conn.execute(
                text("""INSERT INTO integrations.external_invocations
                   (invocation_id, correlation_id, project_id, run_id, actor_id,
                    provider, capability, server_id, remote_tool_name, model_name,
                    status, input_sha256, input_redacted_json, input_full_json,
                    output_summary_json, raw_output_ref, error_code, error_message,
                    latency_ms, retry_count, model_version, created_at)
                   VALUES
                   (:invocation_id, :correlation_id, :project_id, :run_id, :actor_id,
                    :provider, :capability, :server_id, :remote_tool_name, :model_name,
                    :status, :input_sha256, CAST(:input_redacted_json AS JSONB),
                    :input_full_json,
                    CAST(:output_summary_json AS JSONB), :raw_output_ref,
                    :error_code, :error_message, :latency_ms, :retry_count,
                    :model_version, :created_at)"""),
                {
                    "invocation_id": invocation.invocation_id,
                    "correlation_id": invocation.correlation_id,
                    "project_id": invocation.project_id,
                    "run_id": invocation.run_id,
                    "actor_id": invocation.actor_id,
                    "provider": invocation.provider,
                    "capability": invocation.capability,
                    "server_id": None,
                    "remote_tool_name": None,
                    "model_name": None,
                    "status": invocation.status,
                    "input_sha256": input_sha256,
                    "input_redacted_json": input_redacted_json,
                    "input_full_json": input_full_json,
                    "output_summary_json": output_summary_json,
                    "raw_output_ref": None,
                    "error_code": invocation.error_code,
                    "error_message": None,
                    "latency_ms": invocation.latency_ms,
                    "retry_count": 0,
                    "model_version": invocation.model_version,
                    "created_at": invocation.created_at,
                },
            )
        return invocation.invocation_id

    def query(
        self,
        project_id: str | None = None,
        run_id: str | None = None,
        provider: str | None = None,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        conditions = []
        params: dict = {"limit": limit, "offset": offset}
        if project_id:
            conditions.append("project_id = :project_id")
            params["project_id"] = project_id
        if run_id:
            conditions.append("run_id = :run_id")
            params["run_id"] = run_id
        if provider:
            conditions.append("provider = :provider")
            params["provider"] = provider
        if status:
            conditions.append("status = :status")
            params["status"] = status

        where = " AND ".join(conditions) if conditions else "TRUE"
        with self.engine.connect() as conn:
            rows = conn.execute(
                text(f"""SELECT * FROM integrations.external_invocations
                        WHERE {where}
                        ORDER BY created_at DESC
                        LIMIT :limit OFFSET :offset"""),
                params,
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get_by_id(self, invocation_id: str) -> dict | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM integrations.external_invocations WHERE invocation_id = :invocation_id"),
                {"invocation_id": invocation_id},
            ).fetchone()
        return self._row_to_dict(row) if row else None


class ProvenanceDecorator:
    """Attaches provenance metadata to domain results."""

    @staticmethod
    def attach(result: dict, source_type: str, provider: str, model_or_tool: str,
               duration_ms: int = 0, evidence_level: str = "auxiliary",
               warnings: list[str] | None = None) -> dict:
        provenance = Provenance(
            source_type=source_type,
            provider=provider,
            model_or_tool=model_or_tool,
            duration_ms=duration_ms,
            evidence_level=evidence_level,
            warnings=warnings or [],
        )
        if "provenance" not in result:
            result["provenance"] = [provenance.model_dump()]
        else:
            result["provenance"] = list(result["provenance"]) + [provenance.model_dump()]
        return result
