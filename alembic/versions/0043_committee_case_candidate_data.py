"""committee_cases 增加 candidate_data 列

Revision ID: 0043_committee_case_candidate_data
Revises: 0042_ecml_rounds
Create Date: 2026-08-07

背景：ECML 闭环触发晶体构建委员会时，候选数据随案件内联传入
（方案 1，修复 chemical_reasonability 空 formula 误判 0 分）。
为保证案件持久化、跨进程重跑/反查时仍能还原候选数据，为
committee.committee_cases 增加 candidate_data JSONB 列。
"""
from alembic import op

revision = "0043_committee_case_candidate_data"
down_revision = "0042_ecml_rounds"


def upgrade() -> None:
    op.execute(
        "ALTER TABLE committee.committee_cases "
        "ADD COLUMN IF NOT EXISTS candidate_data JSONB"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE committee.committee_cases "
        "DROP COLUMN IF EXISTS candidate_data"
    )