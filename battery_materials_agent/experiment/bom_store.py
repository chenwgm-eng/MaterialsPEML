"""BOM 方案存储。

业务链路层级：
    项目 1 → N 任务
    任务 1 → N 候选材料
    候选材料 1 → N BOM 方案  ← 本模块（0021 迁移放宽为 1:N）
    BOM 方案 1 ↔ 1 工艺方案（process_schemes，0021 迁移新增）
    BOM 方案 1 → N 实验任务（experiment_orders）
    实验任务 1 → N 测试任务（test_tasks）
    测试任务 1 → N 样品
    样品 1 → N 实验数据（experiment_result_records）

表：experiment.bom_schemes（由 0009 迁移创建，0021 迁移放宽 UNIQUE 约束并新增字段）。
"""
from __future__ import annotations
from pydantic import BaseModel, Field, field_validator
from datetime import datetime, timezone
from typing import Any
import uuid
import json
from sqlalchemy import text

from ..db import get_engine


def _iso(value) -> str:
    """将 datetime 或字符串转换为 ISO 字符串；None 返回空字符串。"""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


class BomScheme(BaseModel):
    """候选材料的 BOM 方案（0021 迁移后候选 1:N BOM）。

    formulation / process_route / test_protocol 为 JSONB 字段，分别存储
    配方（原料配比）、工艺路线、测试协议。version 字段当前默认 v1，
    status='draft'/'active'/'archived' 用于区分多 BOM 中的当前方案。

    0021 新增字段：
    - source_route_id：来源合成路径 ID（如 "R1"），用于追溯 BOM 由哪条合成路径生成
    - source_synthesis_task_id：来源合成任务 ID
    - process_id：关联 process_schemes 表的工艺方案 ID（1:1）
    - name：BOM 名称，便于多方案时区分（如 "BOM - 路径1"）
    """
    bom_id: str = ""
    candidate_id: str = ""  # 1:N 关联候选材料（0021 迁移放宽 UNIQUE）
    task_id: str = ""  # 可选，关联 projects.tasks
    formulation: dict[str, Any] = Field(default_factory=dict)
    process_route: dict[str, Any] = Field(default_factory=dict)
    test_protocol: dict[str, Any] = Field(default_factory=dict)
    version: str = "v1"
    status: str = "draft"  # draft / active / archived
    created_by: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = ""
    # 0021 新增字段
    source_route_id: str = ""
    source_synthesis_task_id: str = ""
    process_id: str = ""
    name: str = ""

    @field_validator('candidate_id', 'task_id', 'version', 'status', 'created_by',
                     'source_route_id', 'source_synthesis_task_id', 'process_id', 'name',
                     mode='before')
    @classmethod
    def _coerce_none_to_empty(cls, v):
        """前端或上游可能传入 None，统一转为空字符串。"""
        return "" if v is None else v


class BomStore:
    """BOM 方案存储。"""

    def __init__(self, db_path: str = ""):
        # db_path 保留用于兼容旧调用方，实际连接由 get_engine() 提供
        self.engine = get_engine()
        self._init_db()

    def _init_db(self):
        # 表已由 alembic 迁移创建，这里仅保留 IF NOT EXISTS 兜底（不含 0021 新增字段）
        with self.engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS experiment.bom_schemes (
                    bom_id TEXT PRIMARY KEY,
                    candidate_id TEXT NOT NULL,
                    task_id TEXT,
                    formulation JSONB DEFAULT '{}'::jsonb,
                    process_route JSONB DEFAULT '{}'::jsonb,
                    test_protocol JSONB DEFAULT '{}'::jsonb,
                    version TEXT DEFAULT 'v1',
                    status TEXT DEFAULT 'draft',
                    created_by TEXT DEFAULT '',
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            """))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_bom_task_id "
                "ON experiment.bom_schemes(task_id)"
            ))

    # 列顺序（与 0021 迁移后表结构一致）：
    # bom_id, candidate_id, task_id, formulation, process_route, test_protocol,
    # version, status, created_by, created_at, updated_at,
    # source_route_id, source_synthesis_task_id, process_id, name
    _SELECT_COLS = (
        "bom_id, candidate_id, task_id, formulation, process_route, test_protocol, "
        "version, status, created_by, created_at, updated_at, "
        "source_route_id, source_synthesis_task_id, process_id, name"
    )

    @staticmethod
    def _row_to_bom(r) -> BomScheme:
        # 兼容旧表（无 0021 新增字段）的查询结果
        return BomScheme(
            bom_id=r[0] or "",
            candidate_id=r[1] or "",
            task_id=r[2] or "",
            formulation=r[3] if r[3] is not None else {},
            process_route=r[4] if r[4] is not None else {},
            test_protocol=r[5] if r[5] is not None else {},
            version=r[6] or "v1",
            status=r[7] or "draft",
            created_by=r[8] or "",
            created_at=_iso(r[9]),
            updated_at=_iso(r[10]),
            # 0021 新增字段（旧表查询可能不存在这些列，使用安全取值）
            source_route_id=(r[11] or "") if len(r) > 11 else "",
            source_synthesis_task_id=(r[12] or "") if len(r) > 12 else "",
            process_id=(r[13] or "") if len(r) > 13 else "",
            name=(r[14] or "") if len(r) > 14 else "",
        )

    def create(self, bom: BomScheme) -> BomScheme:
        """创建 BOM 方案（0021 后允许候选 1:N BOM，不再检查重复）。

        Raises:
            ValueError: 若 candidate_id 为空。
        """
        if not bom.candidate_id:
            raise ValueError("candidate_id 不能为空")

        if not bom.bom_id:
            bom.bom_id = f"BOM-{uuid.uuid4().hex[:10].upper()}"
        now = datetime.now(timezone.utc).isoformat()
        if not bom.created_at:
            bom.created_at = now
        bom.updated_at = now

        with self.engine.begin() as conn:
            conn.execute(
                text("""INSERT INTO experiment.bom_schemes
                (bom_id, candidate_id, task_id, formulation, process_route, test_protocol,
                 version, status, created_by, created_at, updated_at,
                 source_route_id, source_synthesis_task_id, process_id, name)
                VALUES (:bom_id, :candidate_id, :task_id,
                 CAST(:formulation AS JSONB), CAST(:process_route AS JSONB),
                 CAST(:test_protocol AS JSONB),
                 :version, :status, :created_by, :created_at, :updated_at,
                 :source_route_id, :source_synthesis_task_id, :process_id, :name)
                """),
                {
                    "bom_id": bom.bom_id,
                    "candidate_id": bom.candidate_id,
                    # FK 约束：空字符串需转为 NULL
                    "task_id": bom.task_id or None,
                    "formulation": json.dumps(bom.formulation, ensure_ascii=False),
                    "process_route": json.dumps(bom.process_route, ensure_ascii=False),
                    "test_protocol": json.dumps(bom.test_protocol, ensure_ascii=False),
                    "version": bom.version,
                    "status": bom.status,
                    "created_by": bom.created_by,
                    "created_at": bom.created_at,
                    "updated_at": bom.updated_at,
                    "source_route_id": bom.source_route_id,
                    "source_synthesis_task_id": bom.source_synthesis_task_id,
                    "process_id": bom.process_id,
                    "name": bom.name,
                },
            )
        return bom

    def get(self, bom_id: str) -> BomScheme | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                text(f"SELECT {self._SELECT_COLS} "
                     "FROM experiment.bom_schemes WHERE bom_id = :bom_id"),
                {"bom_id": bom_id},
            ).fetchone()
        return self._row_to_bom(row) if row else None

    def get_by_candidate(self, candidate_id: str) -> BomScheme | None:
        """按 candidate_id 查询最新一条 BOM（1:N 后取 created_at DESC 第一条）。

        保留单条返回语义以兼容旧 API（GET /candidates/{id}/bom）。
        如需获取全部 BOM，请使用 list_by_candidate。
        """
        with self.engine.connect() as conn:
            row = conn.execute(
                text(f"SELECT {self._SELECT_COLS} "
                     "FROM experiment.bom_schemes WHERE candidate_id = :candidate_id "
                     "ORDER BY created_at DESC LIMIT 1"),
                {"candidate_id": candidate_id},
            ).fetchone()
        return self._row_to_bom(row) if row else None

    def list_by_candidate(self, candidate_id: str) -> list[BomScheme]:
        """按 candidate_id 查询全部 BOM（1:N，按 created_at DESC 排序）。"""
        with self.engine.connect() as conn:
            rows = conn.execute(
                text(f"SELECT {self._SELECT_COLS} "
                     "FROM experiment.bom_schemes WHERE candidate_id = :candidate_id "
                     "ORDER BY created_at DESC"),
                {"candidate_id": candidate_id},
            ).fetchall()
        return [self._row_to_bom(r) for r in rows]

    def update(self, bom: BomScheme) -> BomScheme:
        """更新 BOM 方案（不允许修改 candidate_id）。"""
        bom.updated_at = datetime.now(timezone.utc).isoformat()
        with self.engine.begin() as conn:
            conn.execute(
                text("""UPDATE experiment.bom_schemes SET
                task_id = :task_id,
                formulation = CAST(:formulation AS JSONB),
                process_route = CAST(:process_route AS JSONB),
                test_protocol = CAST(:test_protocol AS JSONB),
                version = :version,
                status = :status,
                created_by = :created_by,
                updated_at = :updated_at,
                source_route_id = :source_route_id,
                source_synthesis_task_id = :source_synthesis_task_id,
                process_id = :process_id,
                name = :name
                WHERE bom_id = :bom_id"""),
                {
                    "task_id": bom.task_id or None,
                    "formulation": json.dumps(bom.formulation, ensure_ascii=False),
                    "process_route": json.dumps(bom.process_route, ensure_ascii=False),
                    "test_protocol": json.dumps(bom.test_protocol, ensure_ascii=False),
                    "version": bom.version,
                    "status": bom.status,
                    "created_by": bom.created_by,
                    "updated_at": bom.updated_at,
                    "source_route_id": bom.source_route_id,
                    "source_synthesis_task_id": bom.source_synthesis_task_id,
                    "process_id": bom.process_id,
                    "name": bom.name,
                    "bom_id": bom.bom_id,
                },
            )
        return bom

    def delete(self, bom_id: str) -> bool:
        with self.engine.begin() as conn:
            cur = conn.execute(
                text("DELETE FROM experiment.bom_schemes WHERE bom_id = :bom_id"),
                {"bom_id": bom_id},
            )
        return cur.rowcount > 0

    def list_by_task(self, task_id: str) -> list[BomScheme]:
        """按 task_id 查询 BOM 列表。"""
        with self.engine.connect() as conn:
            rows = conn.execute(
                text(f"SELECT {self._SELECT_COLS} "
                     "FROM experiment.bom_schemes WHERE task_id = :task_id "
                     "ORDER BY created_at DESC"),
                {"task_id": task_id},
            ).fetchall()
        return [self._row_to_bom(r) for r in rows]

    def list_all(self) -> list[BomScheme]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                text(f"SELECT {self._SELECT_COLS} "
                     "FROM experiment.bom_schemes ORDER BY created_at DESC")
            ).fetchall()
        return [self._row_to_bom(r) for r in rows]
