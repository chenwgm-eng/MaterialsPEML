"""导入审计存储：data_ingest.imports / import_rows（PostgreSQL via SQLAlchemy Engine）。

imports 表记录每次导入批次，import_rows 表记录行级明细。
幂等：idempotency_key UNIQUE，重复 create_import 返回已有记录并标 duplicated=True。
Schema 由 alembic 管理（data_ingest.imports / data_ingest.import_rows）。
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import text

from ..db import get_engine


def _parse_json_field(value, default):
    """解析 JSON 字段，兼容 psycopg3 自动反序列化或字符串两种来源。"""
    if value is None:
        return default
    if isinstance(value, str):
        if not value:
            return default
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return default
    return value


def _iso(value) -> str:
    """将 datetime 或字符串转换为 ISO 字符串；None 返回空字符串。"""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


class IngestStore:
    """导入批次与行级明细的持久化存储。"""

    def __init__(self, db_path: str = "data/ingest_imports.db"):
        # db_path 保留用于兼容旧调用方，实际连接由 get_engine() 提供
        self.db_path = db_path
        self.engine = get_engine()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def create_import(
        self,
        idempotency_key: str,
        entity_type: str,
        file_name: str = "",
        operator: str = "",
        total_rows: int = 0,
    ) -> dict:
        """创建导入批次。idempotency_key 已存在时返回已有记录并标 duplicated=True。"""
        with self.engine.begin() as conn:
            existing = conn.execute(
                text("SELECT import_id, idempotency_key, entity_type, file_name, operator, "
                     "total_rows, success_rows, failed_rows, status, quality_summary, created_at "
                     "FROM data_ingest.imports WHERE idempotency_key = :key"),
                {"key": idempotency_key},
            ).fetchone()
            if existing is not None:
                return {
                    "import_id": existing[0],
                    "idempotency_key": existing[1],
                    "entity_type": existing[2],
                    "file_name": existing[3],
                    "operator": existing[4],
                    "total_rows": existing[5],
                    "success_rows": existing[6],
                    "failed_rows": existing[7],
                    "status": existing[8],
                    "quality_summary": _parse_json_field(existing[9], default={}),
                    "created_at": _iso(existing[10]),
                    "duplicated": True,
                }
            import_id = f"IMP_{uuid.uuid4().hex[:12]}"
            created_at = self._now()
            conn.execute(
                text("""INSERT INTO data_ingest.imports
                (import_id, idempotency_key, entity_type, file_name, operator,
                 total_rows, success_rows, failed_rows, status, quality_summary, created_at)
                VALUES (:import_id, :idempotency_key, :entity_type, :file_name, :operator,
                        :total_rows, 0, 0, 'processing',
                        CAST(:quality_summary AS JSONB), :created_at)"""),
                {
                    "import_id": import_id,
                    "idempotency_key": idempotency_key,
                    "entity_type": entity_type,
                    "file_name": file_name,
                    "operator": operator,
                    "total_rows": total_rows,
                    "quality_summary": "{}",
                    "created_at": created_at,
                },
            )
        return {
            "import_id": import_id,
            "idempotency_key": idempotency_key,
            "entity_type": entity_type,
            "file_name": file_name,
            "operator": operator,
            "total_rows": total_rows,
            "success_rows": 0,
            "failed_rows": 0,
            "status": "processing",
            "quality_summary": {},
            "created_at": created_at,
            "duplicated": False,
        }

    def save_row(
        self,
        import_id: str,
        row_index: int,
        status: str,
        error: str = "",
        payload: dict | None = None,
    ):
        """记录行级导入明细。"""
        with self.engine.begin() as conn:
            conn.execute(
                text("""INSERT INTO data_ingest.import_rows
                (import_id, row_index, status, error, payload)
                VALUES (:import_id, :row_index, :status, :error, CAST(:payload AS JSONB))"""),
                {
                    "import_id": import_id,
                    "row_index": row_index,
                    "status": status,
                    "error": error,
                    "payload": json.dumps(payload or {}, ensure_ascii=False),
                },
            )

    def save_rows(self, rows: list[dict]) -> None:
        """批量记录行级明细，在单个事务中写入以减少连接开销。

        每个元素：{import_id, row_index, status, error, payload}
        """
        if not rows:
            return
        with self.engine.begin() as conn:
            for r in rows:
                conn.execute(
                    text("""INSERT INTO data_ingest.import_rows
                    (import_id, row_index, status, error, payload)
                    VALUES (:import_id, :row_index, :status, :error, CAST(:payload AS JSONB))"""),
                    {
                        "import_id": r["import_id"],
                        "row_index": r["row_index"],
                        "status": r["status"],
                        "error": r.get("error", ""),
                        "payload": json.dumps(r.get("payload") or {}, ensure_ascii=False),
                    },
                )

    def finish_import(
        self,
        import_id: str,
        success_rows: int,
        failed_rows: int,
        quality_summary: dict | None = None,
    ):
        """结束导入批次，更新统计与状态。"""
        status = "success" if failed_rows == 0 else ("partial" if success_rows > 0 else "failed")
        with self.engine.begin() as conn:
            conn.execute(
                text("""UPDATE data_ingest.imports
                       SET success_rows = :success_rows,
                           failed_rows = :failed_rows,
                           status = :status,
                           quality_summary = CAST(:quality_summary AS JSONB)
                       WHERE import_id = :import_id"""),
                {
                    "success_rows": success_rows,
                    "failed_rows": failed_rows,
                    "status": status,
                    "quality_summary": json.dumps(quality_summary or {}, ensure_ascii=False),
                    "import_id": import_id,
                },
            )

    def list_imports(self, limit: int = 100) -> list[dict]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                text("SELECT import_id, idempotency_key, entity_type, file_name, operator, "
                     "total_rows, success_rows, failed_rows, status, quality_summary, created_at "
                     "FROM data_ingest.imports ORDER BY created_at DESC LIMIT :limit"),
                {"limit": limit},
            ).fetchall()
        return [self._row_to_import(r) for r in rows]

    def get_import(self, import_id: str) -> dict | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT import_id, idempotency_key, entity_type, file_name, operator, "
                     "total_rows, success_rows, failed_rows, status, quality_summary, created_at "
                     "FROM data_ingest.imports WHERE import_id = :import_id"),
                {"import_id": import_id},
            ).fetchone()
        return self._row_to_import(row) if row else None

    def get_rows(self, import_id: str) -> list[dict]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                text("SELECT id, import_id, row_index, status, error, payload "
                     "FROM data_ingest.import_rows WHERE import_id = :import_id "
                     "ORDER BY row_index ASC"),
                {"import_id": import_id},
            ).fetchall()
        return [
            {
                "id": r[0],
                "import_id": r[1],
                "row_index": r[2],
                "status": r[3],
                "error": r[4],
                "payload": _parse_json_field(r[5], default={}),
            }
            for r in rows
        ]

    @staticmethod
    def _row_to_import(row) -> dict:
        return {
            "import_id": row[0],
            "idempotency_key": row[1],
            "entity_type": row[2],
            "file_name": row[3],
            "operator": row[4],
            "total_rows": row[5],
            "success_rows": row[6],
            "failed_rows": row[7],
            "status": row[8],
            "quality_summary": _parse_json_field(row[9], default={}),
            "created_at": _iso(row[10]),
        }
