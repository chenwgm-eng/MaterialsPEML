"""Thin repository for budget envelopes and ledger entries.

PostgreSQL via SQLAlchemy Engine；schema 由 alembic 管理
（control_plane.budget_envelopes / control_plane.budget_ledger）。

Follows the same pattern as ``committee/repository.py``: Pydantic models in,
Pydantic models out. 使用 self.engine.begin()/connect() 管理连接生命周期。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import text

from ...db import get_engine
from ..budget import (
    BudgetCategory,
    BudgetEnvelope,
    BudgetLedgerEntry,
    BudgetScope,
    LedgerStatus,
)


def _to_datetime(value):
    """兼容 psycopg3 返回的 datetime 对象或 ISO 字符串。"""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)


class BudgetRepository:
    """PostgreSQL CRUD for budget envelopes and ledger entries.

    使用 SQLAlchemy Engine；schema 由 alembic 管理。
    """

    def __init__(self, db_path: str = "data/control_plane.db"):
        # db_path 保留用于兼容旧调用方，实际连接由 get_engine() 提供
        self.db_path = db_path
        self.engine = get_engine()

    def _init_db(self) -> None:  # pragma: no cover - 兼容旧调用
        """No-op：表结构由 alembic 管理。"""
        return

    # ── envelopes ──────────────────────────────────────────

    def get_envelope(self, scope: BudgetScope, scope_id: str) -> BudgetEnvelope | None:
        """Get a budget envelope by scope, or ``None`` if not found."""
        with self.engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT scope, scope_id, token_limit, external_call_limit, "
                    "dft_cpu_hour_limit, cost_limit, concurrency_limit, "
                    "action_on_exhaustion FROM control_plane.budget_envelopes "
                    "WHERE scope = :scope AND scope_id = :scope_id"
                ),
                {"scope": scope.value, "scope_id": scope_id},
            ).fetchone()
        if row is None:
            return None
        return self._row_to_envelope(row)

    def upsert_envelope(self, envelope: BudgetEnvelope) -> None:
        """Insert or update a budget envelope."""
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """INSERT INTO control_plane.budget_envelopes
                       (scope, scope_id, token_limit, external_call_limit,
                        dft_cpu_hour_limit, cost_limit, concurrency_limit,
                        action_on_exhaustion)
                       VALUES (:scope, :scope_id, :token_limit, :external_call_limit,
                                :dft_cpu_hour_limit, :cost_limit, :concurrency_limit,
                                :action_on_exhaustion)
                       ON CONFLICT (scope, scope_id) DO UPDATE SET
                         token_limit = EXCLUDED.token_limit,
                         external_call_limit = EXCLUDED.external_call_limit,
                         dft_cpu_hour_limit = EXCLUDED.dft_cpu_hour_limit,
                         cost_limit = EXCLUDED.cost_limit,
                         concurrency_limit = EXCLUDED.concurrency_limit,
                         action_on_exhaustion = EXCLUDED.action_on_exhaustion"""
                ),
                {
                    "scope": envelope.scope.value,
                    "scope_id": envelope.scope_id,
                    "token_limit": envelope.token_limit,
                    "external_call_limit": envelope.external_call_limit,
                    "dft_cpu_hour_limit": envelope.dft_cpu_hour_limit,
                    "cost_limit": envelope.cost_limit,
                    "concurrency_limit": envelope.concurrency_limit,
                    "action_on_exhaustion": envelope.action_on_exhaustion,
                },
            )

    def delete_envelope(self, scope: BudgetScope, scope_id: str) -> None:
        """Delete a budget envelope."""
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    "DELETE FROM control_plane.budget_envelopes "
                    "WHERE scope = :scope AND scope_id = :scope_id"
                ),
                {"scope": scope.value, "scope_id": scope_id},
            )

    def list_envelopes(
        self, scope: BudgetScope | None = None
    ) -> list[BudgetEnvelope]:
        """List budget envelopes, optionally filtered by scope."""
        with self.engine.connect() as conn:
            if scope is not None:
                rows = conn.execute(
                    text(
                        "SELECT scope, scope_id, token_limit, external_call_limit, "
                        "dft_cpu_hour_limit, cost_limit, concurrency_limit, "
                        "action_on_exhaustion FROM control_plane.budget_envelopes "
                        "WHERE scope = :scope ORDER BY scope_id"
                    ),
                    {"scope": scope.value},
                ).fetchall()
            else:
                rows = conn.execute(
                    text(
                        "SELECT scope, scope_id, token_limit, external_call_limit, "
                        "dft_cpu_hour_limit, cost_limit, concurrency_limit, "
                        "action_on_exhaustion FROM control_plane.budget_envelopes "
                        "ORDER BY scope, scope_id"
                    )
                ).fetchall()
        return [self._row_to_envelope(row) for row in rows]

    # ── ledger ─────────────────────────────────────────────

    def create_ledger_entry(self, entry: BudgetLedgerEntry) -> BudgetLedgerEntry:
        """Insert a new ledger entry."""
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """INSERT INTO control_plane.budget_ledger
                       (ledger_id, scope_type, scope_id, run_id, category,
                        reserved_amount, settled_amount, status, created_at)
                       VALUES (:ledger_id, :scope_type, :scope_id, :run_id, :category,
                                :reserved_amount, :settled_amount, :status, :created_at)"""
                ),
                {
                    "ledger_id": entry.ledger_id,
                    "scope_type": entry.scope_type.value,
                    "scope_id": entry.scope_id,
                    "run_id": entry.run_id,
                    "category": entry.category.value,
                    "reserved_amount": entry.reserved_amount,
                    "settled_amount": entry.settled_amount,
                    "status": entry.status,
                    "created_at": entry.created_at.isoformat(),
                },
            )
        return entry

    def get_ledger_entry(self, ledger_id: str) -> BudgetLedgerEntry | None:
        """Get a ledger entry by ID, or ``None`` if not found."""
        with self.engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT ledger_id, scope_type, scope_id, run_id, category, "
                    "reserved_amount, settled_amount, status, created_at "
                    "FROM control_plane.budget_ledger WHERE ledger_id = :ledger_id"
                ),
                {"ledger_id": ledger_id},
            ).fetchone()
        if row is None:
            return None
        return self._row_to_entry(row)

    def update_ledger_entry(self, entry: BudgetLedgerEntry) -> None:
        """Update a ledger entry's settled_amount and status."""
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """UPDATE control_plane.budget_ledger
                       SET settled_amount = :settled_amount, status = :status
                       WHERE ledger_id = :ledger_id"""
                ),
                {
                    "settled_amount": entry.settled_amount,
                    "status": entry.status,
                    "ledger_id": entry.ledger_id,
                },
            )

    def list_ledger_entries(
        self,
        scope_type: BudgetScope,
        scope_id: str,
        status: LedgerStatus | None = None,
        category: BudgetCategory | None = None,
    ) -> list[BudgetLedgerEntry]:
        """List ledger entries for a scope, with optional filters."""
        query = (
            "SELECT ledger_id, scope_type, scope_id, run_id, category, "
            "reserved_amount, settled_amount, status, created_at "
            "FROM control_plane.budget_ledger "
            "WHERE scope_type = :scope_type AND scope_id = :scope_id"
        )
        params: dict[str, Any] = {"scope_type": scope_type.value, "scope_id": scope_id}
        if status is not None:
            query += " AND status = :status"
            params["status"] = status
        if category is not None:
            query += " AND category = :category"
            params["category"] = category.value
        query += " ORDER BY created_at ASC"

        with self.engine.connect() as conn:
            rows = conn.execute(text(query), params).fetchall()
        return [self._row_to_entry(row) for row in rows]

    def list_ledger_entries_by_run(
        self, run_id: str, status: LedgerStatus | None = None
    ) -> list[BudgetLedgerEntry]:
        """List ledger entries for a run, with optional status filter."""
        with self.engine.connect() as conn:
            if status is not None:
                rows = conn.execute(
                    text(
                        """SELECT ledger_id, scope_type, scope_id, run_id, category,
                                  reserved_amount, settled_amount, status, created_at
                           FROM control_plane.budget_ledger
                           WHERE run_id = :run_id AND status = :status
                           ORDER BY created_at ASC"""
                    ),
                    {"run_id": run_id, "status": status},
                ).fetchall()
            else:
                rows = conn.execute(
                    text(
                        """SELECT ledger_id, scope_type, scope_id, run_id, category,
                                  reserved_amount, settled_amount, status, created_at
                           FROM control_plane.budget_ledger
                           WHERE run_id = :run_id
                           ORDER BY created_at ASC"""
                    ),
                    {"run_id": run_id},
                ).fetchall()
        return [self._row_to_entry(row) for row in rows]

    # ── helpers ────────────────────────────────────────────

    @staticmethod
    def _row_to_envelope(row) -> BudgetEnvelope:
        return BudgetEnvelope(
            scope=BudgetScope(row[0]),
            scope_id=row[1],
            token_limit=row[2],
            external_call_limit=row[3],
            dft_cpu_hour_limit=row[4],
            cost_limit=row[5],
            concurrency_limit=row[6],
            action_on_exhaustion=row[7],
        )

    @staticmethod
    def _row_to_entry(row) -> BudgetLedgerEntry:
        return BudgetLedgerEntry(
            ledger_id=row[0],
            scope_type=BudgetScope(row[1]),
            scope_id=row[2],
            run_id=row[3],
            category=BudgetCategory(row[4]),
            reserved_amount=float(row[5]),
            settled_amount=float(row[6]) if row[6] is not None else None,
            status=row[7],
            created_at=_to_datetime(row[8]),
        )
