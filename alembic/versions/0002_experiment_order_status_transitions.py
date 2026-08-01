"""新增 experiment_order_status_transitions 事件日志表

记录实验任务单状态迁移历史：(order_id, from_status, to_status, triggered_by, reason, timestamp)。
每次 ExperimentDataStore.update_order_status 成功迁移后写入一条记录。

Revision ID: 0002_order_status_transitions
Revises: 0001_initial_schema
Create Date: 2026-07-26
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_order_status_transitions"
down_revision: Union[str, None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS experiment.experiment_order_status_transitions (
            transition_id    BIGSERIAL PRIMARY KEY,
            order_id         TEXT NOT NULL,
            from_status      TEXT NOT NULL,
            to_status        TEXT NOT NULL,
            triggered_by     TEXT NOT NULL DEFAULT 'system',
            reason           TEXT DEFAULT '',
            timestamp        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT fk_transitions_order
                FOREIGN KEY (order_id)
                REFERENCES experiment.experiment_orders(order_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_transitions_order "
        "ON experiment.experiment_order_status_transitions(order_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_transitions_timestamp "
        "ON experiment.experiment_order_status_transitions(timestamp DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS experiment.experiment_order_status_transitions")
