"""候选材料产出物存储（性质预测、合规检查等结果的持久化）。

0021 迁移新增：将候选详情各 Tab 的产出物（除合成路径已有独立表外）持久化到统一表，
按 candidate_id + artifact_type 唯一约束保留最新一条。

支持的 artifact_type：
- prediction：性质预测（含跨尺度预测）结果
- compliance：工业化合规检查结果
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


# 已支持的产出物类型
ARTIFACT_TYPE_PREDICTION = "prediction"
ARTIFACT_TYPE_COMPLIANCE = "compliance"
VALID_ARTIFACT_TYPES = {ARTIFACT_TYPE_PREDICTION, ARTIFACT_TYPE_COMPLIANCE}


class CandidateArtifact(BaseModel):
    """候选材料产出物（按 candidate_id + artifact_type 唯一，只保留最新一条）。"""
    artifact_id: str = ""
    candidate_id: str = ""
    artifact_type: str = ""  # prediction / compliance
    artifact_data: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = ""

    @field_validator('candidate_id', 'artifact_type', 'artifact_id', mode='before')
    @classmethod
    def _coerce_none_to_empty(cls, v):
        return "" if v is None else v


class CandidateArtifactStore:
    """候选材料产出物存储。"""

    def __init__(self, db_path: str = ""):
        self.engine = get_engine()
        self._init_db()

    def _init_db(self):
        # 表由 0021 alembic 迁移创建，这里仅 IF NOT EXISTS 兜底
        with self.engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS experiment.candidate_artifacts (
                    artifact_id TEXT PRIMARY KEY,
                    candidate_id TEXT NOT NULL,
                    artifact_type TEXT NOT NULL,
                    artifact_data JSONB DEFAULT '{}'::jsonb,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW(),
                    CONSTRAINT uq_artifact_candidate_type UNIQUE (candidate_id, artifact_type)
                )
            """))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_artifact_candidate_id "
                "ON experiment.candidate_artifacts(candidate_id)"
            ))

    _SELECT_COLS = (
        "artifact_id, candidate_id, artifact_type, artifact_data, "
        "created_at, updated_at"
    )

    @staticmethod
    def _row_to_artifact(r) -> CandidateArtifact:
        return CandidateArtifact(
            artifact_id=r[0] or "",
            candidate_id=r[1] or "",
            artifact_type=r[2] or "",
            artifact_data=r[3] if r[3] is not None else {},
            created_at=_iso(r[4]),
            updated_at=_iso(r[5]),
        )

    def upsert(self, artifact: CandidateArtifact) -> CandidateArtifact:
        """按 candidate_id + artifact_type 插入或更新（保留最新一条）。

        Raises:
            ValueError: 若 candidate_id 或 artifact_type 为空，或 artifact_type 不在白名单中。
        """
        if not artifact.candidate_id:
            raise ValueError("candidate_id 不能为空")
        if not artifact.artifact_type:
            raise ValueError("artifact_type 不能为空")
        if artifact.artifact_type not in VALID_ARTIFACT_TYPES:
            raise ValueError(
                f"不支持的 artifact_type {artifact.artifact_type!r}，"
                f"必须是 {VALID_ARTIFACT_TYPES} 之一"
            )

        if not artifact.artifact_id:
            artifact.artifact_id = f"ART-{uuid.uuid4().hex[:10].upper()}"
        now = datetime.now(timezone.utc).isoformat()
        if not artifact.created_at:
            artifact.created_at = now
        artifact.updated_at = now

        with self.engine.begin() as conn:
            # ON CONFLICT (candidate_id, artifact_type) DO UPDATE
            conn.execute(
                text("""INSERT INTO experiment.candidate_artifacts
                (artifact_id, candidate_id, artifact_type, artifact_data,
                 created_at, updated_at)
                VALUES (:artifact_id, :candidate_id, :artifact_type,
                 CAST(:artifact_data AS JSONB), :created_at, :updated_at)
                ON CONFLICT (candidate_id, artifact_type) DO UPDATE SET
                    artifact_data = EXCLUDED.artifact_data,
                    updated_at = EXCLUDED.updated_at
                """),
                {
                    "artifact_id": artifact.artifact_id,
                    "candidate_id": artifact.candidate_id,
                    "artifact_type": artifact.artifact_type,
                    "artifact_data": json.dumps(artifact.artifact_data, ensure_ascii=False),
                    "created_at": artifact.created_at,
                    "updated_at": artifact.updated_at,
                },
            )
        return artifact

    def get(self, candidate_id: str, artifact_type: str) -> CandidateArtifact | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                text(f"SELECT {self._SELECT_COLS} "
                     "FROM experiment.candidate_artifacts "
                     "WHERE candidate_id = :candidate_id AND artifact_type = :artifact_type"),
                {"candidate_id": candidate_id, "artifact_type": artifact_type},
            ).fetchone()
        return self._row_to_artifact(row) if row else None

    def list_by_candidate(self, candidate_id: str) -> list[CandidateArtifact]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                text(f"SELECT {self._SELECT_COLS} "
                     "FROM experiment.candidate_artifacts "
                     "WHERE candidate_id = :candidate_id "
                     "ORDER BY artifact_type"),
                {"candidate_id": candidate_id},
            ).fetchall()
        return [self._row_to_artifact(r) for r in rows]

    def delete(self, candidate_id: str, artifact_type: str) -> bool:
        with self.engine.begin() as conn:
            cur = conn.execute(
                text("DELETE FROM experiment.candidate_artifacts "
                     "WHERE candidate_id = :candidate_id AND artifact_type = :artifact_type"),
                {"candidate_id": candidate_id, "artifact_type": artifact_type},
            )
        return cur.rowcount > 0
