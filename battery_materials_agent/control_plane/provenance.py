"""Provenance graph for tracing entity lineage across the Agent Control Plane.

Records the origin and relationships of entities (candidates, structures,
experiments, verdicts, tool calls, policy decisions) so that any result can
be traced back to its sources and forward to its consumers.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field
from sqlalchemy import text

from ..db import get_engine


EntityType = Literal[
    "candidate", "structure", "experiment", "verdict", "tool_call", "policy_decision"
]
Source = Literal["tool", "model", "human", "committee"]
RelationType = Literal[
    "contains", "generated", "verified_by", "derived_from", "overturned_by"
]


class ProvenanceRecord(BaseModel):
    """A single node in the provenance graph representing one entity's origin."""

    record_id: str
    run_id: str | None = None
    correlation_id: str
    entity_type: EntityType
    entity_id: str
    source: Source
    source_version: str | None = None
    input_hash: str | None = None
    output_artifact_path: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict = Field(default_factory=dict)


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


def _to_datetime(value):
    """兼容 psycopg3 返回的 datetime 对象或 ISO 字符串。"""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)


class ProvenanceGraph:
    """PostgreSQL-backed provenance graph with node/edge storage and lineage queries.

    使用 SQLAlchemy Engine；schema 由 alembic 管理
    （control_plane.provenance_nodes / control_plane.provenance_edges）。
    """

    def __init__(self, db_path: str = "data/control_plane.db"):
        # db_path 保留用于兼容旧调用方，实际连接由 get_engine() 提供
        self.db_path = db_path
        self.engine = get_engine()
        self._artifacts_dir = Path(db_path).parent / "artifacts"
        self._artifacts_dir.mkdir(parents=True, exist_ok=True)

    def _init_db(self) -> None:  # pragma: no cover - 兼容旧调用
        """No-op：表结构由 alembic 管理。"""
        return

    # ── nodes ──────────────────────────────────────────────

    def add_node(self, record: ProvenanceRecord) -> ProvenanceRecord:
        """Add a provenance node (upsert by record_id)."""
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """INSERT INTO control_plane.provenance_nodes
                       (record_id, run_id, correlation_id, entity_type, entity_id,
                        source, source_version, input_hash, output_artifact_path,
                        metadata_json, created_at)
                       VALUES (:record_id, :run_id, :correlation_id, :entity_type, :entity_id,
                               :source, :source_version, :input_hash, :output_artifact_path,
                               CAST(:metadata_json AS JSONB), :created_at)
                       ON CONFLICT (record_id) DO UPDATE SET
                         run_id = EXCLUDED.run_id,
                         correlation_id = EXCLUDED.correlation_id,
                         entity_type = EXCLUDED.entity_type,
                         entity_id = EXCLUDED.entity_id,
                         source = EXCLUDED.source,
                         source_version = EXCLUDED.source_version,
                         input_hash = EXCLUDED.input_hash,
                         output_artifact_path = EXCLUDED.output_artifact_path,
                         metadata_json = EXCLUDED.metadata_json,
                         created_at = EXCLUDED.created_at"""
                ),
                {
                    "record_id": record.record_id,
                    "run_id": record.run_id,
                    "correlation_id": record.correlation_id,
                    "entity_type": record.entity_type,
                    "entity_id": record.entity_id,
                    "source": record.source,
                    "source_version": record.source_version,
                    "input_hash": record.input_hash,
                    "output_artifact_path": record.output_artifact_path,
                    "metadata_json": json.dumps(record.metadata, default=str),
                    "created_at": record.created_at.isoformat(),
                },
            )
        return record

    def get_node(
        self, entity_type: EntityType, entity_id: str
    ) -> ProvenanceRecord | None:
        """Look up the most recent node for an entity, or ``None`` if not found."""
        with self.engine.connect() as conn:
            row = conn.execute(
                text(
                    """SELECT record_id, run_id, correlation_id, entity_type, entity_id,
                              source, source_version, input_hash, output_artifact_path,
                              metadata_json, created_at
                       FROM control_plane.provenance_nodes
                       WHERE entity_type = :entity_type AND entity_id = :entity_id
                       ORDER BY created_at DESC LIMIT 1"""
                ),
                {"entity_type": entity_type, "entity_id": entity_id},
            ).fetchone()
        if row is None:
            return None
        return self._row_to_record(row)

    # ── edges ──────────────────────────────────────────────

    def add_edge(
        self, from_id: str, to_id: str, relation_type: RelationType
    ) -> None:
        """Add a directed relationship between two nodes (idempotent)."""
        now = datetime.now(timezone.utc).isoformat()
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """INSERT INTO control_plane.provenance_edges
                       (from_id, to_id, relation_type, created_at)
                       VALUES (:from_id, :to_id, :relation_type, :created_at)
                       ON CONFLICT (from_id, to_id, relation_type) DO NOTHING"""
                ),
                {
                    "from_id": from_id,
                    "to_id": to_id,
                    "relation_type": relation_type,
                    "created_at": now,
                },
            )

    # ── lineage ────────────────────────────────────────────

    def get_lineage(
        self, entity_type: EntityType, entity_id: str
    ) -> list[ProvenanceRecord]:
        """Get full lineage (parents + children) for an entity.

        Parents are nodes with an edge pointing TO this node; children are
        nodes this node points TO. The node itself is included as the first
        element.
        """
        node = self.get_node(entity_type, entity_id)
        if node is None:
            return []
        record_id = node.record_id
        with self.engine.connect() as conn:
            parent_rows = conn.execute(
                text(
                    """SELECT n.record_id, n.run_id, n.correlation_id, n.entity_type,
                              n.entity_id, n.source, n.source_version, n.input_hash,
                              n.output_artifact_path, n.metadata_json, n.created_at
                       FROM control_plane.provenance_nodes n
                       JOIN control_plane.provenance_edges e ON e.from_id = n.record_id
                       WHERE e.to_id = :record_id"""
                ),
                {"record_id": record_id},
            ).fetchall()
            child_rows = conn.execute(
                text(
                    """SELECT n.record_id, n.run_id, n.correlation_id, n.entity_type,
                              n.entity_id, n.source, n.source_version, n.input_hash,
                              n.output_artifact_path, n.metadata_json, n.created_at
                       FROM control_plane.provenance_nodes n
                       JOIN control_plane.provenance_edges e ON e.to_id = n.record_id
                       WHERE e.from_id = :record_id"""
                ),
                {"record_id": record_id},
            ).fetchall()
        seen: set[str] = {record_id}
        result: list[ProvenanceRecord] = [node]
        for row in parent_rows + child_rows:
            if row[0] not in seen:
                seen.add(row[0])
                result.append(self._row_to_record(row))
        return result

    def get_trace(self, correlation_id: str) -> list[ProvenanceRecord]:
        """Get all provenance records for a correlation_id, oldest first."""
        with self.engine.connect() as conn:
            rows = conn.execute(
                text(
                    """SELECT record_id, run_id, correlation_id, entity_type, entity_id,
                              source, source_version, input_hash, output_artifact_path,
                              metadata_json, created_at
                       FROM control_plane.provenance_nodes
                       WHERE correlation_id = :correlation_id
                       ORDER BY created_at ASC"""
                ),
                {"correlation_id": correlation_id},
            ).fetchall()
        return [self._row_to_record(row) for row in rows]

    # ── artifacts ──────────────────────────────────────────

    @staticmethod
    def _validate_path_component(name: str) -> str:
        """Validate that ``name`` is a safe single path component.

        Only alphanumerics, underscore, and hyphen are allowed, which
        prevents ``..``, separators, and other traversal vectors.
        """
        if not re.match(r"^[A-Za-z0-9_\-]+$", name):
            raise ValueError(f"Invalid path component: {name!r}")
        return name

    def save_artifact(
        self, data: Any, artifact_type: str, run_id: str | None = None
    ) -> str:
        """Save raw artifact data to a JSON file and return the file path.

        Artifacts are stored under ``<db_dir>/artifacts/<run_id>/<type>_<id>.json``.
        All path components are validated to prevent path traversal.
        """
        safe_run_id = self._validate_path_component(run_id or "no_run")
        safe_artifact_type = self._validate_path_component(artifact_type)
        run_dir = self._artifacts_dir / safe_run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        artifact_id = uuid4().hex[:12]
        filename = f"{safe_artifact_type}_{artifact_id}.json"
        path = (run_dir / filename).resolve()
        # Defense in depth: ensure the resolved path stays within artifacts.
        artifacts_root = self._artifacts_dir.resolve()
        try:
            path.relative_to(artifacts_root)
        except ValueError:
            raise ValueError("Path traversal detected")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, default=str, indent=2)
        return str(path)

    # ── helpers ────────────────────────────────────────────

    @staticmethod
    def _row_to_record(row) -> ProvenanceRecord:
        return ProvenanceRecord(
            record_id=row[0],
            run_id=row[1],
            correlation_id=row[2],
            entity_type=row[3],
            entity_id=row[4],
            source=row[5],
            source_version=row[6],
            input_hash=row[7],
            output_artifact_path=row[8],
            metadata=_parse_json_field(row[9], default={}) or {},
            created_at=_to_datetime(row[10]),
        )
