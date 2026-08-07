"""ECML 贝叶斯优化 Round 级记录 + 材料体系标签

Revision ID: 0041_ecml_rounds
Revises: 0040_two_layer_formulation_process
Create Date: 2026-08-06

背景：把"实验闭环迭代"从一次性表单升级为决策引擎。
1. 新增 ecml.ecml_rounds 表：每一轮迭代的结构化可追溯记录（训练池快照、
   代理模型元数据、采集策略元数据、推荐候选+预测、实测回填、模型指标、状态）。
2. experiment.experiment_result_records 增加 material_family 列：
   数据聚合主键（材料体系/化学空间标签），独立于项目 ID，AI 自动归类 + 人工可改。
"""
from alembic import op

revision = "0042_ecml_rounds"
down_revision = "0041_committee_evidence_verification"


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE ecml.ecml_rounds (
            round_id            TEXT PRIMARY KEY,
            run_id              TEXT NOT NULL,
            round_no            BIGINT NOT NULL,
            status              TEXT NOT NULL DEFAULT 'pending_review',
            target              TEXT,
            target_property     TEXT,
            material_family     TEXT,
            train_pool_snapshot JSONB,
            model_meta          JSONB,
            acquisition_meta    JSONB,
            recommended         JSONB,
            actual_results      JSONB,
            model_metrics       JSONB,
            review_actions      JSONB,
            created_at          TIMESTAMPTZ,
            updated_at          TIMESTAMPTZ
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_ecml_rounds_run_id ON ecml.ecml_rounds(run_id)"
    )
    op.execute(
        "CREATE INDEX idx_ecml_rounds_family_property "
        "ON ecml.ecml_rounds(material_family, target_property)"
    )
    op.execute(
        "ALTER TABLE experiment.experiment_result_records "
        "ADD COLUMN IF NOT EXISTS material_family TEXT"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_result_records_material_family "
        "ON experiment.experiment_result_records(material_family)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ecml.idx_ecml_rounds_run_id")
    op.execute("DROP INDEX IF EXISTS ecml.idx_ecml_rounds_family_property")
    op.execute("DROP TABLE IF EXISTS ecml.ecml_rounds")
    op.execute("DROP INDEX IF EXISTS experiment.idx_result_records_material_family")
    op.execute(
        "ALTER TABLE experiment.experiment_result_records "
        "DROP COLUMN IF EXISTS material_family"
    )