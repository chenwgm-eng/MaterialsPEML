"""新增 qc_decisions 审计日志表

Revision ID: 0003_qc_decisions
Revises: 0002_order_status_transitions
Create Date: 2026-07-26

每次 QC 检查写入此表，包含完整规则结果快照（rule_version +
decision_snapshot JSONB + result_id 关联实验结果 + timestamp）。
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003_qc_decisions"
down_revision: Union[str, None] = "0002_order_status_transitions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE audit.qc_decisions (
            decision_id        BIGSERIAL PRIMARY KEY,
            result_id          TEXT,
            rule_version       TEXT NOT NULL,
            decision_snapshot  JSONB NOT NULL,
            timestamp          TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_qc_decisions_result ON audit.qc_decisions(result_id)"
    )
    op.execute(
        "CREATE INDEX idx_qc_decisions_timestamp ON audit.qc_decisions(timestamp DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS audit.qc_decisions")
