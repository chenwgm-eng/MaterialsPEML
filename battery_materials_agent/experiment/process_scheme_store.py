"""工艺方案存储（独立于 BOM 的工艺路线信息）。

0021 迁移新增：将工艺方案从 BomScheme.process_route JSONB 嵌入字段独立成表，
便于记录从合成路径生成的工艺路线详情，并与 BOM 1:1 关联。

业务链路：
    合成路径（SynthesisRoute）→ 选中某条路径 → 生成 BOM + 工艺方案
    BOM 方案 1 ↔ 1 工艺方案（process_schemes）
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
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


class ProcessScheme(BaseModel):
    """工艺方案（与 BomScheme 1:1 关联）。

    source_route_id / source_synthesis_task_id 用于追溯 BOM+工艺方案
    是从哪条合成路径生成的。
    """
    process_id: str = ""
    candidate_id: str = ""
    bom_id: str = ""  # 关联 BomScheme（1:1）
    source_route_id: str = ""  # 如 "R1"，标识合成路径任务结果中的某条路径
    source_synthesis_task_id: str = ""  # 关联 synthesis.synthesis_tasks
    steps: list[dict[str, Any]] = Field(default_factory=list)  # 工艺步骤
    raw_materials: list[dict[str, Any]] = Field(default_factory=list)  # 原料清单
    metadata: dict[str, Any] = Field(default_factory=dict)  # 其他元数据（如 feasibility_score）
    created_by: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = ""

    @field_validator('candidate_id', 'bom_id', 'source_route_id',
                     'source_synthesis_task_id', 'created_by',
                     mode='before')
    @classmethod
    def _coerce_none_to_empty(cls, v):
        return "" if v is None else v


class ProcessSchemeStore:
    """工艺方案存储。"""

    def __init__(self, db_path: str = ""):
        self.engine = get_engine()
        self._init_db()

    def _init_db(self):
        # 表由 0021 alembic 迁移创建，这里仅 IF NOT EXISTS 兜底
        with self.engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS experiment.process_schemes (
                    process_id TEXT PRIMARY KEY,
                    candidate_id TEXT NOT NULL,
                    bom_id TEXT,
                    source_route_id TEXT,
                    source_synthesis_task_id TEXT,
                    steps JSONB DEFAULT '[]'::jsonb,
                    raw_materials JSONB DEFAULT '[]'::jsonb,
                    metadata JSONB DEFAULT '{}'::jsonb,
                    created_by TEXT DEFAULT '',
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            """))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_process_candidate_id "
                "ON experiment.process_schemes(candidate_id)"
            ))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_process_bom_id "
                "ON experiment.process_schemes(bom_id)"
            ))

    _SELECT_COLS = (
        "process_id, candidate_id, bom_id, source_route_id, "
        "source_synthesis_task_id, steps, raw_materials, metadata, "
        "created_by, created_at, updated_at"
    )

    @staticmethod
    def _row_to_scheme(r) -> ProcessScheme:
        return ProcessScheme(
            process_id=r[0] or "",
            candidate_id=r[1] or "",
            bom_id=r[2] or "",
            source_route_id=r[3] or "",
            source_synthesis_task_id=r[4] or "",
            steps=r[5] if r[5] is not None else [],
            raw_materials=r[6] if r[6] is not None else [],
            metadata=r[7] if r[7] is not None else {},
            created_by=r[8] or "",
            created_at=_iso(r[9]),
            updated_at=_iso(r[10]),
        )

    def create(self, scheme: ProcessScheme) -> ProcessScheme:
        if not scheme.candidate_id:
            raise ValueError("candidate_id 不能为空")
        if not scheme.process_id:
            scheme.process_id = f"PROC-{uuid.uuid4().hex[:10].upper()}"
        now = datetime.now(timezone.utc).isoformat()
        if not scheme.created_at:
            scheme.created_at = now
        scheme.updated_at = now

        with self.engine.begin() as conn:
            conn.execute(
                text("""INSERT INTO experiment.process_schemes
                (process_id, candidate_id, bom_id, source_route_id,
                 source_synthesis_task_id, steps, raw_materials, metadata,
                 created_by, created_at, updated_at)
                VALUES (:process_id, :candidate_id, :bom_id, :source_route_id,
                 :source_synthesis_task_id,
                 CAST(:steps AS JSONB), CAST(:raw_materials AS JSONB),
                 CAST(:metadata AS JSONB),
                 :created_by, :created_at, :updated_at)
                """),
                {
                    "process_id": scheme.process_id,
                    "candidate_id": scheme.candidate_id,
                    "bom_id": scheme.bom_id or None,
                    "source_route_id": scheme.source_route_id,
                    "source_synthesis_task_id": scheme.source_synthesis_task_id,
                    "steps": json.dumps(scheme.steps, ensure_ascii=False),
                    "raw_materials": json.dumps(scheme.raw_materials, ensure_ascii=False),
                    "metadata": json.dumps(scheme.metadata, ensure_ascii=False),
                    "created_by": scheme.created_by,
                    "created_at": scheme.created_at,
                    "updated_at": scheme.updated_at,
                },
            )
        return scheme

    def get(self, process_id: str) -> ProcessScheme | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                text(f"SELECT {self._SELECT_COLS} "
                     "FROM experiment.process_schemes WHERE process_id = :process_id"),
                {"process_id": process_id},
            ).fetchone()
        return self._row_to_scheme(row) if row else None

    def get_by_bom(self, bom_id: str) -> ProcessScheme | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                text(f"SELECT {self._SELECT_COLS} "
                     "FROM experiment.process_schemes WHERE bom_id = :bom_id LIMIT 1"),
                {"bom_id": bom_id},
            ).fetchone()
        return self._row_to_scheme(row) if row else None

    def list_by_candidate(self, candidate_id: str) -> list[ProcessScheme]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                text(f"SELECT {self._SELECT_COLS} "
                     "FROM experiment.process_schemes WHERE candidate_id = :candidate_id "
                     "ORDER BY created_at DESC"),
                {"candidate_id": candidate_id},
            ).fetchall()
        return [self._row_to_scheme(r) for r in rows]

    def update(self, scheme: ProcessScheme) -> ProcessScheme:
        scheme.updated_at = datetime.now(timezone.utc).isoformat()
        with self.engine.begin() as conn:
            conn.execute(
                text("""UPDATE experiment.process_schemes SET
                bom_id = :bom_id,
                source_route_id = :source_route_id,
                source_synthesis_task_id = :source_synthesis_task_id,
                steps = CAST(:steps AS JSONB),
                raw_materials = CAST(:raw_materials AS JSONB),
                metadata = CAST(:metadata AS JSONB),
                created_by = :created_by,
                updated_at = :updated_at
                WHERE process_id = :process_id"""),
                {
                    "bom_id": scheme.bom_id or None,
                    "source_route_id": scheme.source_route_id,
                    "source_synthesis_task_id": scheme.source_synthesis_task_id,
                    "steps": json.dumps(scheme.steps, ensure_ascii=False),
                    "raw_materials": json.dumps(scheme.raw_materials, ensure_ascii=False),
                    "metadata": json.dumps(scheme.metadata, ensure_ascii=False),
                    "created_by": scheme.created_by,
                    "updated_at": scheme.updated_at,
                    "process_id": scheme.process_id,
                },
            )
        return scheme

    def delete(self, process_id: str) -> bool:
        with self.engine.begin() as conn:
            cur = conn.execute(
                text("DELETE FROM experiment.process_schemes WHERE process_id = :process_id"),
                {"process_id": process_id},
            )
        return cur.rowcount > 0
