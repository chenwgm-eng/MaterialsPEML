"""0033: 候选材料 content_hash 去重列

T-020：AI 候选基于内容哈希去重。
- experiment.candidates 新增 content_hash TEXT 列（可空）+ 索引
- content_hash = sha256(normalized_formula + "|" + target_application)
- 决策 D-08：去重粒度为"化学式 + 目标应用"

Revision ID: 0033_candidate_content_hash
Revises: 0032_experiment_result_unique_constraint
"""

from alembic import op

revision = "0033_candidate_content_hash"
down_revision = "0032_experiment_result_unique_constraint"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE experiment.candidates "
        "ADD COLUMN IF NOT EXISTS content_hash TEXT"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_candidates_content_hash "
        "ON experiment.candidates(content_hash)"
    )


def downgrade() -> None:
    op.execute(
        "DROP INDEX IF EXISTS experiment.idx_candidates_content_hash"
    )
    op.execute(
        "ALTER TABLE experiment.candidates "
        "DROP COLUMN IF EXISTS content_hash"
    )
