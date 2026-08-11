"""实验记录表增加 provenance 溯源列（ADR-0002）

Revision ID: 0059_experiment_provenance
Revises: 0058_kingfa_mdm_master
Create Date: 2026-08-11

ADR-0002（模拟数据不得冒充实测）：experiment_result_records 此前无 provenance 列，
模拟值以 VALID+learning_eligible 落库且 provenance 标 measured——无法回答
"每条数据从哪来"。本迁移：
- experiment.experiment_result_records 增加 provenance JSONB（可空）
- 历史数据按 data_quality 回填 provenance（simulated→simulation / verified→measured 等）
"""
from __future__ import annotations

import json

from alembic import op

revision = "0059_experiment_provenance"
down_revision = "0058_kingfa_mdm_master"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE experiment.experiment_result_records "
        "ADD COLUMN IF NOT EXISTS provenance JSONB"
    )
    # 历史数据回填：按 data_quality 派生溯源（模拟/实测/估算/文献）
    op.execute("""
        UPDATE experiment.experiment_result_records
        SET provenance = CASE data_quality
            WHEN 'simulated' THEN jsonb_build_object(
                'source_type', 'simulation',
                'provider', 'simulation_engine',
                'model_or_tool', 'experiment_controller_simulate',
                'evidence_level', 'simulated')
            WHEN 'verified' THEN jsonb_build_object(
                'source_type', 'measured',
                'provider', 'local_db',
                'model_or_tool', 'experiment_controller',
                'evidence_level', 'measured')
            WHEN 'literature' THEN jsonb_build_object(
                'source_type', 'literature',
                'provider', 'literature',
                'model_or_tool', 'literature',
                'evidence_level', 'literature')
            ELSE jsonb_build_object(
                'source_type', 'estimated',
                'provider', 'local_db',
                'model_or_tool', 'experiment_controller',
                'evidence_level', 'estimated')
        END
        WHERE provenance IS NULL
    """)


def downgrade() -> None:
    op.execute(
        "ALTER TABLE experiment.experiment_result_records DROP COLUMN IF EXISTS provenance"
    )
