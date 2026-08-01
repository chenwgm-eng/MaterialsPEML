"""research_requests 增加 scenario_id 列

Revision ID: 0007_add_scenario_id
Revises: 0006_material_property_templates
Create Date: 2026-07-26

为 hybrid.research_requests 新增 scenario_id 列，用于关联研发场景。
research_store.create_request 已使用该字段，但初始 schema 遗漏，导致写入失败。
同时为 experiment.experiment_orders 补充 scenario_id 索引（列已存在，仅补索引）。
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007_add_scenario_id"
down_revision: Union[str, None] = "0006_material_property_templates"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. research_requests 增加 scenario_id 列
    op.execute(
        """
        ALTER TABLE hybrid.research_requests
            ADD COLUMN IF NOT EXISTS scenario_id TEXT
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_research_requests_scenario_id "
        "ON hybrid.research_requests(scenario_id)"
    )

    # 2. 为已存在 scenario_id 列的 experiment_orders 补充索引（若已存在则跳过）
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_experiment_orders_scenario_id "
        "ON experiment.experiment_orders(scenario_id)"
    )


def downgrade() -> None:
    op.execute(
        "DROP INDEX IF EXISTS hybrid.idx_research_requests_scenario_id"
    )
    op.execute(
        "ALTER TABLE hybrid.research_requests DROP COLUMN IF EXISTS scenario_id"
    )
    op.execute(
        "DROP INDEX IF EXISTS experiment.idx_experiment_orders_scenario_id"
    )
