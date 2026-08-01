"""P5 文档版本与执行快照 Store。

承载 3 张表的 CRUD：
- mdm.documents 文档主数据
- mdm.document_versions 文档版本
- experiment.order_version_snapshots 订单版本快照

设计原则：
- 只读为主，不提供 create/update/delete
- 提供 list/get 查询接口
"""
from __future__ import annotations
import json
from pydantic import BaseModel, field_validator
from datetime import datetime
from typing import Any
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from ..db import get_engine


def _iso(value) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


# ──────────────────────────────────────────────────────────────────────────────
# 模型
# ──────────────────────────────────────────────────────────────────────────────
class Document(BaseModel):
    """文档主数据。"""
    document_id: str = ""
    title: str = ""
    document_type: str = ""
    category_code: str = ""
    status: str = "draft"
    owner: str = ""
    description: str = ""
    is_active: bool = True
    created_at: str = ""
    updated_at: str = ""

    @field_validator("category_code", mode="before")
    @classmethod
    def _coerce_none(cls, v):
        return "" if v is None else v


class DocumentVersion(BaseModel):
    """文档版本。"""
    version_id: str = ""
    document_id: str = ""
    version_number: str = ""
    content_uri: str = ""
    content_hash: str = ""
    effective_date: str | None = None
    status: str = "draft"
    change_summary: str = ""
    created_by: str = ""
    created_at: str = ""


class OrderVersionSnapshot(BaseModel):
    """订单版本快照。"""
    snapshot_id: str = ""
    order_id: str = ""
    snapshot_type: str = "order_creation"
    snapshot_data: dict = {}
    master_data_refs: dict = {}
    created_at: str = ""


# ──────────────────────────────────────────────────────────────────────────────
# Store
# ──────────────────────────────────────────────────────────────────────────────
class DocumentStore:
    """P5 文档版本 Store。只读查询。"""

    def __init__(self):
        self.engine = get_engine()

    # ── 文档 ──────────────────────────────────────────────
    def list_documents(self, document_type: str = "") -> list[Document]:
        sql = ("SELECT document_id, title, document_type, category_code, status, owner, "
               "description, is_active, created_at, updated_at FROM mdm.documents WHERE 1=1")
        params: dict[str, Any] = {}
        if document_type:
            sql += " AND document_type = :document_type"
            params["document_type"] = document_type
        sql += " ORDER BY document_type, title"
        with self.engine.connect() as conn:
            rows = conn.execute(text(sql), params).fetchall()
        return [self._row_to_document(r) for r in rows]

    def get_document(self, document_id: str) -> Document | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT document_id, title, document_type, category_code, status, owner, "
                     "description, is_active, created_at, updated_at FROM mdm.documents "
                     "WHERE document_id = :document_id"),
                {"document_id": document_id},
            ).fetchone()
        return self._row_to_document(row) if row else None

    @staticmethod
    def _row_to_document(r) -> Document:
        return Document(
            document_id=r[0] or "",
            title=r[1] or "",
            document_type=r[2] or "",
            category_code=r[3] or "",
            status=r[4] or "draft",
            owner=r[5] or "",
            description=r[6] or "",
            is_active=bool(r[7]),
            created_at=_iso(r[8]),
            updated_at=_iso(r[9]),
        )

    # ── 文档版本 ──────────────────────────────────────────
    def list_document_versions(self, document_id: str = "") -> list[DocumentVersion]:
        sql = ("SELECT version_id, document_id, version_number, content_uri, content_hash, "
               "effective_date, status, change_summary, created_by, created_at "
               "FROM mdm.document_versions WHERE 1=1")
        params: dict[str, Any] = {}
        if document_id:
            sql += " AND document_id = :document_id"
            params["document_id"] = document_id
        sql += " ORDER BY created_at DESC"
        with self.engine.connect() as conn:
            rows = conn.execute(text(sql), params).fetchall()
        return [self._row_to_document_version(r) for r in rows]

    def get_document_version(self, version_id: str) -> DocumentVersion | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT version_id, document_id, version_number, content_uri, content_hash, "
                     "effective_date, status, change_summary, created_by, created_at "
                     "FROM mdm.document_versions WHERE version_id = :version_id"),
                {"version_id": version_id},
            ).fetchone()
        return self._row_to_document_version(row) if row else None

    @staticmethod
    def _row_to_document_version(r) -> DocumentVersion:
        return DocumentVersion(
            version_id=r[0] or "",
            document_id=r[1] or "",
            version_number=r[2] or "",
            content_uri=r[3] or "",
            content_hash=r[4] or "",
            effective_date=_iso(r[5]) or None,
            status=r[6] or "draft",
            change_summary=r[7] or "",
            created_by=r[8] or "",
            created_at=_iso(r[9]),
        )

    # ── 订单版本快照 ──────────────────────────────────────
    def list_order_snapshots(self, order_id: str = "") -> list[OrderVersionSnapshot]:
        sql = ("SELECT snapshot_id, order_id, snapshot_type, snapshot_data, master_data_refs, "
               "created_at FROM experiment.order_version_snapshots WHERE 1=1")
        params: dict[str, Any] = {}
        if order_id:
            sql += " AND order_id = :order_id"
            params["order_id"] = order_id
        sql += " ORDER BY created_at DESC"
        with self.engine.connect() as conn:
            rows = conn.execute(text(sql), params).fetchall()
        return [self._row_to_snapshot(r) for r in rows]

    def get_order_snapshot(self, snapshot_id: str) -> OrderVersionSnapshot | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT snapshot_id, order_id, snapshot_type, snapshot_data, master_data_refs, "
                     "created_at FROM experiment.order_version_snapshots "
                     "WHERE snapshot_id = :snapshot_id"),
                {"snapshot_id": snapshot_id},
            ).fetchone()
        return self._row_to_snapshot(row) if row else None

    @staticmethod
    def _row_to_snapshot(r) -> OrderVersionSnapshot:
        snapshot_data = r[3] if r[3] else {}
        if isinstance(snapshot_data, str):
            snapshot_data = json.loads(snapshot_data)
        master_data_refs = r[4] if r[4] else {}
        if isinstance(master_data_refs, str):
            master_data_refs = json.loads(master_data_refs)
        return OrderVersionSnapshot(
            snapshot_id=r[0] or "",
            order_id=r[1] or "",
            snapshot_type=r[2] or "order_creation",
            snapshot_data=snapshot_data,
            master_data_refs=master_data_refs,
            created_at=_iso(r[5]),
        )

    # ── 写入：通用 INSERT 助手 ────────────────────────────
    def _insert_row(self, table: str, cols: list[str], payload: dict[str, Any]) -> None:
        """按允许列过滤 payload 后执行 INSERT。唯一键冲突抛 ValueError。"""
        cols_clean = [c for c in cols if c in payload]
        if not cols_clean:
            raise ValueError("payload 不包含任何可插入列")
        placeholders = {c: payload.get(c) for c in cols_clean}
        col_list = ",".join(cols_clean)
        param_list = ":" + ",:".join(cols_clean)
        sql = f"INSERT INTO {table} ({col_list}) VALUES ({param_list})"
        try:
            with self.engine.begin() as conn:
                conn.execute(text(sql), placeholders)
        except IntegrityError as e:
            raise ValueError(f"唯一键冲突: {e.orig}") from e

    # ── 文档：create / toggle ─────────────────────────────
    def create_document(self, payload: dict[str, Any]) -> Document:
        cols = ["document_id", "title", "document_type", "category_code", "status",
                "owner", "description", "is_active"]
        self._insert_row("mdm.documents", cols, payload)
        return self.get_document(payload["document_id"])

    def set_document_active(self, document_id: str, is_active: bool) -> Document | None:
        with self.engine.begin() as conn:
            result = conn.execute(
                text("UPDATE mdm.documents SET is_active = :is_active, "
                     "updated_at = CURRENT_TIMESTAMP WHERE document_id = :document_id"),
                {"is_active": is_active, "document_id": document_id},
            )
            if result.rowcount == 0:
                return None
        return self.get_document(document_id)
