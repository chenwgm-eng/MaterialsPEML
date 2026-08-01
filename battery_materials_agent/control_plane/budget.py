"""Budget management for the Agent Control Plane.

Multi-scope budget envelopes with reserve/settle/release ledger semantics.
Supports token, external-call, DFT CPU-hour, cost, concurrency, storage, and
human-review categories across organization, project, ECML-run, committee-case,
and user scopes.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field
from sqlalchemy import text

from ..db import get_engine


class BudgetCategory(str, Enum):
    """Categories of resource consumption tracked by the budget system."""

    TOKEN = "token"
    EXTERNAL_CALL = "external_call"
    DFT_CPU_HOUR = "dft_cpu_hour"
    COST = "cost"
    CONCURRENCY = "concurrency"
    STORAGE = "storage"
    HUMAN_REVIEW = "human_review"


def _to_datetime(value):
    """兼容 psycopg3 返回的 datetime 对象或 ISO 字符串。"""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)


class BudgetScope(str, Enum):
    """Scopes at which budget envelopes can be defined."""

    ORGANIZATION = "organization"
    PROJECT = "project"
    ECML_RUN = "ecml_run"
    COMMITTEE_CASE = "committee_case"
    USER = "user"


ActionOnExhaustion = Literal["pause", "fallback", "human_review", "reject"]
LedgerStatus = Literal["reserved", "settled", "released"]

# Maps a category to the corresponding limit field on BudgetEnvelope.
# Categories absent from this mapping (STORAGE, HUMAN_REVIEW) have no
# dedicated limit and are treated as unlimited.
_CATEGORY_LIMIT_FIELD: dict[BudgetCategory, str] = {
    BudgetCategory.TOKEN: "token_limit",
    BudgetCategory.EXTERNAL_CALL: "external_call_limit",
    BudgetCategory.DFT_CPU_HOUR: "dft_cpu_hour_limit",
    BudgetCategory.COST: "cost_limit",
    BudgetCategory.CONCURRENCY: "concurrency_limit",
}


class BudgetEnvelope(BaseModel):
    """A budget envelope defining limits for a scope.

    Fields set to ``None`` mean "unlimited" for that category.
    """

    scope: BudgetScope
    scope_id: str
    token_limit: int | None = None
    external_call_limit: int | None = None
    dft_cpu_hour_limit: float | None = None
    cost_limit: float | None = None
    concurrency_limit: int | None = None
    action_on_exhaustion: ActionOnExhaustion = "pause"


class BudgetLedgerEntry(BaseModel):
    """A single reservation/settlement record in the budget ledger."""

    ledger_id: str
    scope_type: BudgetScope
    scope_id: str
    run_id: str | None = None
    category: BudgetCategory
    reserved_amount: float
    settled_amount: float | None = None
    status: LedgerStatus = "reserved"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class BudgetManager:
    """Reserve/settle/release budget ledger with envelope-based limits.

    PostgreSQL via SQLAlchemy Engine；schema 由 alembic 管理
    （control_plane.budget_envelopes / control_plane.budget_ledger）。
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
        """Get the budget envelope for a scope, or ``None`` if not set."""
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

    def set_envelope(self, scope: BudgetScope, scope_id: str, envelope: BudgetEnvelope) -> None:
        """Create or update the budget envelope for a scope."""
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
                    "scope": scope.value,
                    "scope_id": scope_id,
                    "token_limit": envelope.token_limit,
                    "external_call_limit": envelope.external_call_limit,
                    "dft_cpu_hour_limit": envelope.dft_cpu_hour_limit,
                    "cost_limit": envelope.cost_limit,
                    "concurrency_limit": envelope.concurrency_limit,
                    "action_on_exhaustion": envelope.action_on_exhaustion,
                },
            )

    # ── ledger ─────────────────────────────────────────────

    def reserve(
        self,
        scope: BudgetScope,
        scope_id: str,
        category: BudgetCategory,
        amount: float,
        run_id: str | None = None,
    ) -> BudgetLedgerEntry:
        """Reserve budget for a category.

        Checks availability against the envelope limit and creates a ledger
        entry with status ``reserved``. The check and insert are performed in
        a single transaction to prevent TOCTOU races under concurrency.
        Raises ``ValueError`` if insufficient budget is available.
        """
        if amount < 0:
            raise ValueError("reserve amount must be non-negative")
        entry = BudgetLedgerEntry(
            ledger_id=str(uuid4()),
            scope_type=scope,
            scope_id=scope_id,
            run_id=run_id,
            category=category,
            reserved_amount=amount,
            status="reserved",
        )
        with self.engine.begin() as conn:
            # Re-query usage and limit inside the transaction so the
            # check is atomic with the INSERT below.
            usage = self._query_usage_in_conn(
                conn, scope, scope_id
            ).get(category.value, 0.0)
            limit = self._query_limit_in_conn(conn, scope, scope_id, category)
            if limit is not None and usage + amount > limit:
                raise ValueError(
                    f"Insufficient budget for {category.value} at "
                    f"{scope.value}:{scope_id}"
                )
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

    def settle(self, ledger_id: str, actual_amount: float) -> None:
        """Settle a reservation with the actual usage amount.

        The state check and update are performed atomically via a single
        UPDATE with a status precondition. Raises ``ValueError`` if the
        ledger entry is not found or is not in ``reserved`` status.
        """
        with self.engine.begin() as conn:
            cursor = conn.execute(
                text(
                    """UPDATE control_plane.budget_ledger
                       SET settled_amount = :amount, status = 'settled'
                       WHERE ledger_id = :ledger_id AND status = 'reserved'"""
                ),
                {"amount": actual_amount, "ledger_id": ledger_id},
            )
            if cursor.rowcount == 0:
                row = conn.execute(
                    text(
                        "SELECT status FROM control_plane.budget_ledger WHERE ledger_id = :ledger_id"
                    ),
                    {"ledger_id": ledger_id},
                ).fetchone()
                if row is None:
                    raise ValueError(f"Ledger entry {ledger_id!r} not found")
                raise ValueError(
                    f"Ledger entry {ledger_id!r} is in status {row[0]!r}; "
                    f"can only settle 'reserved' entries"
                )

    def release(self, ledger_id: str) -> None:
        """Release a reservation without settling.

        The reservation no longer counts against the budget. The state check
        and update are performed atomically via a single UPDATE with a status
        precondition. Raises ``ValueError`` if the entry is not found or is
        not in ``reserved`` status.
        """
        with self.engine.begin() as conn:
            cursor = conn.execute(
                text(
                    """UPDATE control_plane.budget_ledger
                       SET status = 'released'
                       WHERE ledger_id = :ledger_id AND status = 'reserved'"""
                ),
                {"ledger_id": ledger_id},
            )
            if cursor.rowcount == 0:
                row = conn.execute(
                    text(
                        "SELECT status FROM control_plane.budget_ledger WHERE ledger_id = :ledger_id"
                    ),
                    {"ledger_id": ledger_id},
                ).fetchone()
                if row is None:
                    raise ValueError(f"Ledger entry {ledger_id!r} not found")
                raise ValueError(
                    f"Ledger entry {ledger_id!r} is in status {row[0]!r}; "
                    f"can only release 'reserved' entries"
                )

    # ── queries ────────────────────────────────────────────

    def get_usage(self, scope: BudgetScope, scope_id: str) -> dict[str, float]:
        """Get current usage by category for a scope.

        Reserved entries contribute their ``reserved_amount``; settled entries
        contribute their ``settled_amount``; released entries contribute
        nothing. Categories with no usage are omitted.
        """
        with self.engine.connect() as conn:
            rows = conn.execute(
                text(
                    """SELECT category,
                              SUM(CASE WHEN status = 'reserved' THEN reserved_amount
                                       WHEN status = 'settled' THEN COALESCE(settled_amount, 0)
                                       ELSE 0 END) AS usage
                       FROM control_plane.budget_ledger
                       WHERE scope_type = :scope_type AND scope_id = :scope_id
                       GROUP BY category"""
                ),
                {"scope_type": scope.value, "scope_id": scope_id},
            ).fetchall()
        return {row[0]: float(row[1]) for row in rows}

    def check_available(
        self,
        scope: BudgetScope,
        scope_id: str,
        category: BudgetCategory,
        amount: float,
    ) -> bool:
        """Check if ``amount`` is available for ``category`` within the envelope.

        Returns ``True`` if there is no envelope, no limit for the category,
        or the current usage plus ``amount`` does not exceed the limit.
        """
        limit = self._get_limit(scope, scope_id, category)
        if limit is None:
            return True
        usage = self.get_usage(scope, scope_id).get(category.value, 0.0)
        return usage + amount <= limit

    def is_exhausted(
        self,
        scope: BudgetScope,
        scope_id: str,
        category: BudgetCategory | None = None,
    ) -> bool:
        """Check if budget is exhausted.

        If ``category`` is specified, checks only that category. If
        ``category`` is ``None``, checks all categories that have limits and
        returns ``True`` if any is exhausted.
        """
        if category is not None:
            limit = self._get_limit(scope, scope_id, category)
            if limit is None:
                return False
            usage = self.get_usage(scope, scope_id).get(category.value, 0.0)
            return usage >= limit

        usage = self.get_usage(scope, scope_id)
        for cat, limit_field in _CATEGORY_LIMIT_FIELD.items():
            limit = self._get_limit_by_field(scope, scope_id, limit_field)
            if limit is not None and usage.get(cat.value, 0.0) >= limit:
                return True
        return False

    # ── internals ──────────────────────────────────────────

    def _query_usage_in_conn(
        self, conn, scope: BudgetScope, scope_id: str
    ) -> dict[str, float]:
        """Query current usage by category using an existing connection."""
        rows = conn.execute(
            text(
                """SELECT category,
                          SUM(CASE WHEN status = 'reserved' THEN reserved_amount
                                   WHEN status = 'settled' THEN COALESCE(settled_amount, 0)
                                   ELSE 0 END) AS usage
                   FROM control_plane.budget_ledger
                   WHERE scope_type = :scope_type AND scope_id = :scope_id
                   GROUP BY category"""
            ),
            {"scope_type": scope.value, "scope_id": scope_id},
        ).fetchall()
        return {row[0]: float(row[1]) for row in rows}

    def _query_limit_in_conn(
        self,
        conn,
        scope: BudgetScope,
        scope_id: str,
        category: BudgetCategory,
    ) -> float | None:
        """Query the numeric limit for a category using an existing connection."""
        limit_field = _CATEGORY_LIMIT_FIELD.get(category)
        if limit_field is None:
            return None
        row = conn.execute(
            text(
                f"SELECT {limit_field} AS lim FROM control_plane.budget_envelopes "
                "WHERE scope = :scope AND scope_id = :scope_id"
            ),
            {"scope": scope.value, "scope_id": scope_id},
        ).fetchone()
        if row is None or row[0] is None:
            return None
        return float(row[0])

    def _get_limit(
        self, scope: BudgetScope, scope_id: str, category: BudgetCategory
    ) -> float | None:
        """Get the numeric limit for a category, or ``None`` if unlimited."""
        limit_field = _CATEGORY_LIMIT_FIELD.get(category)
        if limit_field is None:
            return None
        return self._get_limit_by_field(scope, scope_id, limit_field)

    def _get_limit_by_field(
        self, scope: BudgetScope, scope_id: str, field: str
    ) -> float | None:
        envelope = self.get_envelope(scope, scope_id)
        if envelope is None:
            return None
        return getattr(envelope, field)

    @staticmethod
    def _row_to_envelope(row) -> BudgetEnvelope:
        try:
            scope = BudgetScope(row[0]) if row[0] else BudgetScope.ORGANIZATION
        except (ValueError, KeyError):
            scope = BudgetScope.ORGANIZATION
        valid_actions = ("pause", "fallback", "human_review", "reject")
        action = row[7] if row[7] in valid_actions else "pause"
        return BudgetEnvelope(
            scope=scope,
            scope_id=row[1] or "",
            token_limit=row[2],
            external_call_limit=row[3],
            dft_cpu_hour_limit=row[4],
            cost_limit=row[5],
            concurrency_limit=row[6],
            action_on_exhaustion=action,
        )

    @staticmethod
    def _row_to_entry(row) -> BudgetLedgerEntry:
        try:
            scope_type = BudgetScope(row[1]) if row[1] else BudgetScope.ORGANIZATION
        except (ValueError, KeyError):
            scope_type = BudgetScope.ORGANIZATION
        try:
            category = BudgetCategory(row[4]) if row[4] else BudgetCategory.TOKEN
        except (ValueError, KeyError):
            category = BudgetCategory.TOKEN
        valid_statuses = ("reserved", "settled", "released")
        status = row[7] if row[7] in valid_statuses else "reserved"
        return BudgetLedgerEntry(
            ledger_id=row[0] or "",
            scope_type=scope_type,
            scope_id=row[2] or "",
            run_id=row[3],
            category=category,
            reserved_amount=float(row[5]) if row[5] is not None else 0.0,
            settled_amount=float(row[6]) if row[6] is not None else None,
            status=status,
            created_at=_to_datetime(row[8]),
        )
