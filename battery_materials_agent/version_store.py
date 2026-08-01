"""知识资产版本追溯 - 实体快照与活跃版本管理。

为物料、工作流、知识、配方等资产提供版本快照存储：
- save: 保存新版本快照
- get: 按 version_id 获取
- list_by_entity: 列出某实体的全部历史版本
- list_latest: 列出每实体的最新活跃版本
- get_history: 同 list_by_entity，按版本号倒序
- set_active: 切换活跃版本（同实体仅一个 active）
"""

from __future__ import annotations
from pydantic import BaseModel, Field
from enum import Enum
from datetime import datetime, timezone
import json
import uuid
import logging

from sqlalchemy import text


def _iso(v) -> str:
    """TIMESTAMPTZ 列由 psycopg3 返回 datetime 对象，需转为 ISO 字符串以匹配 Pydantic 模型。"""
    if v is None:
        return ""
    if isinstance(v, datetime):
        return v.isoformat()
    return str(v)

from .db import get_engine

logger = logging.getLogger(__name__)


def _safe_enum(enum_cls, value, default):
    """安全枚举构造：非法值返回默认枚举，避免 ValueError 中断查询。"""
    try:
        return enum_cls(value) if value else default
    except (ValueError, KeyError):
        return default


class VersionType(str, Enum):
    MATERIAL = "material"
    WORKFLOW = "workflow"
    KNOWLEDGE = "knowledge"
    FORMULA = "formula"
    MDM_UNIT = "mdm_unit"
    MDM_PROPERTY = "mdm_property"
    MDM_METHOD = "mdm_method"


class Version(BaseModel):
    """单个资产版本快照。"""
    version_id: str = ""
    entity_type: VersionType
    entity_id: str = ""
    version_number: int = 1
    snapshot: dict = Field(default_factory=dict)
    change_summary: str = ""
    created_by: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    is_active: bool = True


class VersionStore:
    """版本快照的 PostgreSQL 持久化存储（control_plane.versions 表）。"""

    def __init__(self, db_path: str | None = None):
        # db_path 参数保留以兼容旧调用方，迁移至 PostgreSQL 后已忽略，统一使用全局 Engine。
        self.engine = get_engine()

    def _row_to_version(self, row) -> Version:
        snapshot = row[4]
        if not isinstance(snapshot, dict):
            try:
                snapshot = json.loads(snapshot or "{}")
            except (json.JSONDecodeError, TypeError):
                snapshot = {}
        return Version(
            version_id=row[0],
            entity_type=_safe_enum(VersionType, row[1], VersionType.MATERIAL),
            entity_id=row[2],
            version_number=row[3] or 1,
            snapshot=snapshot,
            change_summary=row[5] or "",
            created_by=row[6] or "",
            created_at=_iso(row[7]),
            is_active=bool(row[8]),
        )

    def save(self, version: Version) -> Version:
        """保存新版本。

        - 自动生成 version_id（若为空）
        - 自动递增 version_number（若调用方未指定，取该实体当前最大版本号 + 1）
        - 若 is_active=True，先将同实体的其他版本置为非活跃
        """
        if not version.version_id:
            version.version_id = f"VER-{uuid.uuid4().hex[:10].upper()}"
        if not version.created_at:
            version.created_at = datetime.now(timezone.utc).isoformat()

        with self.engine.begin() as conn:
            # 未指定版本号 → 自动递增
            if version.version_number <= 0:
                row = conn.execute(
                    text("SELECT MAX(version_number) FROM control_plane.versions "
                         "WHERE entity_type=:entity_type AND entity_id=:entity_id"),
                    {"entity_type": version.entity_type.value, "entity_id": version.entity_id},
                ).fetchone()
                version.version_number = (row[0] or 0) + 1

            if version.is_active:
                conn.execute(
                    text("UPDATE control_plane.versions SET is_active=FALSE "
                         "WHERE entity_type=:entity_type AND entity_id=:entity_id"),
                    {"entity_type": version.entity_type.value, "entity_id": version.entity_id},
                )

            conn.execute(
                text("""INSERT INTO control_plane.versions
                (version_id, entity_type, entity_id, version_number,
                 snapshot, change_summary, created_by, created_at, is_active)
                VALUES (:version_id, :entity_type, :entity_id, :version_number,
                        CAST(:snapshot AS JSONB), :change_summary, :created_by, :created_at, :is_active)"""),
                {
                    "version_id": version.version_id,
                    "entity_type": version.entity_type.value,
                    "entity_id": version.entity_id,
                    "version_number": version.version_number,
                    "snapshot": json.dumps(version.snapshot, ensure_ascii=False),
                    "change_summary": version.change_summary,
                    "created_by": version.created_by,
                    "created_at": version.created_at,
                    "is_active": version.is_active,
                },
            )
        return version

    def get(self, version_id: str) -> Version | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM control_plane.versions WHERE version_id=:version_id"),
                {"version_id": version_id},
            ).fetchone()
        return self._row_to_version(row) if row else None

    def list_by_entity(self, entity_type: str, entity_id: str) -> list[Version]:
        """列出某实体的全部版本，按版本号倒序。"""
        with self.engine.connect() as conn:
            rows = conn.execute(
                text("SELECT * FROM control_plane.versions WHERE entity_type=:entity_type AND entity_id=:entity_id "
                     "ORDER BY version_number DESC"),
                {"entity_type": entity_type, "entity_id": entity_id},
            ).fetchall()
        return [self._row_to_version(r) for r in rows]

    def get_history(self, entity_type: str, entity_id: str) -> list[Version]:
        """get_history 与 list_by_entity 同义，保留以匹配 spec 命名。"""
        return self.list_by_entity(entity_type, entity_id)

    def list_latest(self, entity_type: str = "") -> list[Version]:
        """列出每实体的最新活跃版本（is_active=TRUE）。

        可选 entity_type 过滤；为空则返回全部类型的活跃版本。
        """
        with self.engine.connect() as conn:
            if entity_type:
                rows = conn.execute(
                    text("SELECT * FROM control_plane.versions WHERE entity_type=:entity_type AND is_active=TRUE "
                         "ORDER BY created_at DESC"),
                    {"entity_type": entity_type},
                ).fetchall()
            else:
                rows = conn.execute(
                    text("SELECT * FROM control_plane.versions WHERE is_active=TRUE ORDER BY created_at DESC")
                ).fetchall()
        return [self._row_to_version(r) for r in rows]

    def get_latest(self, entity_type: str, entity_id: str) -> Version | None:
        """获取指定实体的最新版本（优先返回活跃版本，无则取最大版本号）。"""
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM control_plane.versions WHERE entity_type=:entity_type AND entity_id=:entity_id AND is_active=TRUE "
                     "ORDER BY version_number DESC LIMIT 1"),
                {"entity_type": entity_type, "entity_id": entity_id},
            ).fetchone()
            if row is None:
                row = conn.execute(
                    text("SELECT * FROM control_plane.versions WHERE entity_type=:entity_type AND entity_id=:entity_id "
                         "ORDER BY version_number DESC LIMIT 1"),
                    {"entity_type": entity_type, "entity_id": entity_id},
                ).fetchone()
        return self._row_to_version(row) if row else None

    def set_active(self, version_id: str) -> Version | None:
        """将指定版本设为活跃，同实体的其他版本自动置为非活跃。"""
        with self.engine.begin() as conn:
            row = conn.execute(
                text("SELECT entity_type, entity_id FROM control_plane.versions WHERE version_id=:version_id"),
                {"version_id": version_id},
            ).fetchone()
            if row is None:
                return None
            entity_type, entity_id = row[0], row[1]
            conn.execute(
                text("UPDATE control_plane.versions SET is_active=FALSE "
                     "WHERE entity_type=:entity_type AND entity_id=:entity_id"),
                {"entity_type": entity_type, "entity_id": entity_id},
            )
            conn.execute(
                text("UPDATE control_plane.versions SET is_active=TRUE WHERE version_id=:version_id"),
                {"version_id": version_id},
            )
        return self.get(version_id)


# 全局单例
_version_store: VersionStore | None = None


def get_version_store() -> VersionStore:
    global _version_store
    if _version_store is None:
        _version_store = VersionStore()
    return _version_store
