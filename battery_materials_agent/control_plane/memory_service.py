"""Memory service for persistent, access-controlled knowledge cards.

Stores structured knowledge (run summaries, decision verdicts, experiment
results, scientific facts, feedback) as versioned cards with provenance and
role-based access control. Cards can be superseded or invalidated as
understanding evolves.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import text

from ..db import get_engine


class MemoryCardType(str, Enum):
    """Types of knowledge cards stored in the memory service."""

    RUN_SUMMARY = "run_summary"
    DECISION_VERDICT = "decision_verdict"
    HUMAN_OVERRIDE = "human_override"
    EXPERIMENT_RESULT = "experiment_result"
    DEVIATION_FINDING = "deviation_finding"
    SCIENTIFIC_FACT = "scientific_fact"
    FEEDBACK = "feedback"


AccessLevel = Literal["public", "project_internal", "sensitive", "restricted"]
ValidityStatus = Literal["active", "superseded", "invalidated"]

# Role hierarchy for access filtering (mirrors context.py ROLE_RANK).
_ROLE_RANK: dict[str, int] = {
    "admin": 4,
    "pm": 3,
    "researcher": 2,
    "viewer": 1,
}

# Minimum role rank required for each access level.
_ACCESS_LEVEL_MIN_RANK: dict[str, int] = {
    "public": 1,
    "project_internal": 2,
    "sensitive": 3,
    "restricted": 4,
}


class MemoryCard(BaseModel):
    """A persistent knowledge card with provenance and access control."""

    card_id: str
    project_id: str | None = None
    entity_type: str
    entity_id: str
    card_type: MemoryCardType
    content: dict = Field(default_factory=dict)
    provenance: dict = Field(default_factory=dict)
    access_level: AccessLevel = "project_internal"
    validity_status: ValidityStatus = "active"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


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


class MemoryService:
    """PostgreSQL-backed memory card store with access-controlled search.

    使用 SQLAlchemy Engine；schema 由 alembic 管理
    （control_plane.memory_cards）。
    """

    def __init__(self, db_path: str = "data/control_plane.db"):
        # db_path 保留用于兼容旧调用方，实际连接由 get_engine() 提供
        self.db_path = db_path
        self.engine = get_engine()

    def _init_db(self) -> None:  # pragma: no cover - 兼容旧调用
        """No-op：表结构由 alembic 管理。"""
        return

    # ── CRUD ───────────────────────────────────────────────

    def create_card(self, card: MemoryCard) -> MemoryCard:
        """Create a new memory card."""
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """INSERT INTO control_plane.memory_cards
                       (card_id, project_id, entity_type, entity_id, card_type,
                        content_json, provenance_json, access_level, validity_status,
                        created_at, updated_at)
                       VALUES (:card_id, :project_id, :entity_type, :entity_id, :card_type,
                               CAST(:content_json AS JSONB), CAST(:provenance_json AS JSONB),
                               :access_level, :validity_status, :created_at, :updated_at)"""
                ),
                {
                    "card_id": card.card_id,
                    "project_id": card.project_id,
                    "entity_type": card.entity_type,
                    "entity_id": card.entity_id,
                    "card_type": card.card_type.value,
                    "content_json": json.dumps(card.content, default=str),
                    "provenance_json": json.dumps(card.provenance, default=str),
                    "access_level": card.access_level,
                    "validity_status": card.validity_status,
                    "created_at": card.created_at.isoformat(),
                    "updated_at": card.updated_at.isoformat(),
                },
            )
        return card

    def get_card(
        self,
        card_id: str,
        user_role: str = "viewer",
        project_id: str | None = None,
    ) -> MemoryCard | None:
        """Get a card by ID, or ``None`` if not found or inaccessible.

        The result is filtered through ``_filter_by_access`` (fail-closed):
        a card the caller is not allowed to see is treated as absent.
        """
        with self.engine.connect() as conn:
            row = conn.execute(
                text(
                    """SELECT card_id, project_id, entity_type, entity_id, card_type,
                              content_json, provenance_json, access_level, validity_status,
                              created_at, updated_at
                       FROM control_plane.memory_cards WHERE card_id = :card_id"""
                ),
                {"card_id": card_id},
            ).fetchone()
        if row is None:
            return None
        card = self._row_to_card(row)
        accessible = self._filter_by_access([card], user_role, project_id)
        return accessible[0] if accessible else None

    def search(
        self,
        project_id: str | None = None,
        query: str | None = None,
        card_type: MemoryCardType | None = None,
        entity_type: str | None = None,
        access_level_filter: str | None = None,
        limit: int = 20,
        user_role: str = "viewer",
    ) -> list[MemoryCard]:
        """Search cards with optional filters, returning only active cards.

        ``query`` performs a substring search on the card's content JSON.
        Results are ordered by ``updated_at`` descending.

        Results are always filtered through ``_filter_by_access`` using
        ``user_role`` and ``project_id`` (fail-closed: defaults to the most
        restrictive role).
        """
        sql = (
            "SELECT card_id, project_id, entity_type, entity_id, card_type, "
            "content_json, provenance_json, access_level, validity_status, "
            "created_at, updated_at "
            "FROM control_plane.memory_cards WHERE validity_status = 'active'"
        )
        params: dict[str, Any] = {}
        if project_id is not None:
            sql += " AND project_id = :project_id"
            params["project_id"] = project_id
        if card_type is not None:
            sql += " AND card_type = :card_type"
            params["card_type"] = card_type.value
        if entity_type is not None:
            sql += " AND entity_type = :entity_type"
            params["entity_type"] = entity_type
        if access_level_filter is not None:
            sql += " AND access_level = :access_level"
            params["access_level"] = access_level_filter
        if query:
            sql += " AND content_json::text ILIKE :query"
            params["query"] = f"%{query}%"
        sql += " ORDER BY updated_at DESC LIMIT :limit"
        params["limit"] = limit

        with self.engine.connect() as conn:
            rows = conn.execute(text(sql), params).fetchall()
        cards = [self._row_to_card(row) for row in rows]
        return self._filter_by_access(cards, user_role, project_id)

    # ── lifecycle ──────────────────────────────────────────

    def invalidate(
        self, card_id: str, reason: str, user_role: str = "viewer"
    ) -> None:
        """Mark a card as invalidated, recording the reason in its content.

        Requires ``user_role`` in ``("admin", "pm")`` (fail-closed). Raises
        ``ValueError`` if the card is not found or the caller is not
        authorized.
        """
        if user_role not in ("admin", "pm"):
            raise ValueError(
                f"Role {user_role!r} is not authorized to invalidate cards"
            )
        now = datetime.now(timezone.utc).isoformat()
        with self.engine.begin() as conn:
            row = conn.execute(
                text(
                    "SELECT content_json FROM control_plane.memory_cards WHERE card_id = :card_id"
                ),
                {"card_id": card_id},
            ).fetchone()
            if row is None:
                raise ValueError(f"Card {card_id!r} not found")
            content = _parse_json_field(row[0], default={}) or {}
            content.setdefault("_invalidation_history", []).append(
                {"reason": reason, "invalidated_at": now}
            )
            conn.execute(
                text(
                    """UPDATE control_plane.memory_cards
                       SET validity_status = 'invalidated',
                           content_json = CAST(:content_json AS JSONB),
                           updated_at = :updated_at
                       WHERE card_id = :card_id"""
                ),
                {
                    "content_json": json.dumps(content, default=str),
                    "updated_at": now,
                    "card_id": card_id,
                },
            )

    def supersede(
        self,
        old_card_id: str,
        new_card: MemoryCard,
        user_role: str = "viewer",
    ) -> MemoryCard:
        """Replace an old card with a new one.

        The old card is marked as ``superseded`` and the new card is created
        with ``active`` status. Requires ``user_role`` in ``("admin", "pm")``
        (fail-closed).
        """
        if user_role not in ("admin", "pm"):
            raise ValueError(
                f"Role {user_role!r} is not authorized to supersede cards"
            )
        now = datetime.now(timezone.utc).isoformat()
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """UPDATE control_plane.memory_cards
                       SET validity_status = 'superseded', updated_at = :updated_at
                       WHERE card_id = :card_id"""
                ),
                {"updated_at": now, "card_id": old_card_id},
            )
            conn.execute(
                text(
                    """INSERT INTO control_plane.memory_cards
                       (card_id, project_id, entity_type, entity_id, card_type,
                        content_json, provenance_json, access_level, validity_status,
                        created_at, updated_at)
                       VALUES (:card_id, :project_id, :entity_type, :entity_id, :card_type,
                               CAST(:content_json AS JSONB), CAST(:provenance_json AS JSONB),
                               :access_level, :validity_status, :created_at, :updated_at)"""
                ),
                {
                    "card_id": new_card.card_id,
                    "project_id": new_card.project_id,
                    "entity_type": new_card.entity_type,
                    "entity_id": new_card.entity_id,
                    "card_type": new_card.card_type.value,
                    "content_json": json.dumps(new_card.content, default=str),
                    "provenance_json": json.dumps(new_card.provenance, default=str),
                    "access_level": new_card.access_level,
                    "validity_status": new_card.validity_status,
                    "created_at": new_card.created_at.isoformat(),
                    "updated_at": new_card.updated_at.isoformat(),
                },
            )
        return new_card

    # ── access control ─────────────────────────────────────

    def filter_by_access(
        self,
        cards: list[MemoryCard],
        user_role: str,
        project_id: str | None,
    ) -> list[MemoryCard]:
        """Public accessor for access-filtered memory cards.

        Delegates to ``_filter_by_access`` so callers outside the service
        no longer need to touch a private method.
        """
        return self._filter_by_access(cards, user_role, project_id)

    def _filter_by_access(
        self,
        cards: list[MemoryCard],
        user_role: str,
        project_id: str | None,
    ) -> list[MemoryCard]:
        """Filter cards by access level and project membership.

        - ``public``: visible to all roles.
        - ``project_internal``: requires role >= researcher AND project membership.
        - ``sensitive``: requires role >= pm AND project membership.
        - ``restricted``: requires role >= admin.
        """
        rank = _ROLE_RANK.get(user_role, 0)
        result: list[MemoryCard] = []
        for card in cards:
            level = card.access_level
            required = _ACCESS_LEVEL_MIN_RANK.get(level, 4)
            if rank < required:
                continue
            # Project-scoped levels require project membership. When the
            # caller supplies no project_id, fail closed (deny).
            if level in ("project_internal", "sensitive"):
                if project_id is None or card.project_id != project_id:
                    continue
            result.append(card)
        return result

    # ── helpers ────────────────────────────────────────────

    @staticmethod
    def _row_to_card(row) -> MemoryCard:
        return MemoryCard(
            card_id=row[0],
            project_id=row[1],
            entity_type=row[2],
            entity_id=row[3],
            card_type=MemoryCardType(row[4]),
            content=_parse_json_field(row[5], default={}) or {},
            provenance=_parse_json_field(row[6], default={}) or {},
            access_level=row[7],
            validity_status=row[8],
            created_at=_to_datetime(row[9]),
            updated_at=_to_datetime(row[10]),
        )
