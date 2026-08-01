"""为 industrialization.raw_materials 表新增合规证据字段

Revision ID: 0004_compliance_evidence
Revises: 0003_qc_decisions
Create Date: 2026-07-26

Task 13 强制合规关联：REACH/SDS/毒性合规声明必须关联具体检测报告凭证。
coa_uri 在 0001_initial_schema 中已存在，本次新增 sds_uri / test_report_uri /
test_institution / test_date 四列。reach_compliant 字段语义改变：现在表示
"声明值"，需有 evidence 支撑才可视为合规（由 RawMaterialDB.compute_compliance_status
判定 compliant / pending_evidence / non_compliant）。
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004_compliance_evidence"
down_revision: Union[str, None] = "0003_qc_decisions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE industrialization.raw_materials
            ADD COLUMN IF NOT EXISTS sds_uri TEXT DEFAULT '',
            ADD COLUMN IF NOT EXISTS test_report_uri TEXT DEFAULT '',
            ADD COLUMN IF NOT EXISTS test_institution TEXT DEFAULT '',
            ADD COLUMN IF NOT EXISTS test_date TEXT DEFAULT ''
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE industrialization.raw_materials
            DROP COLUMN IF EXISTS sds_uri,
            DROP COLUMN IF EXISTS test_report_uri,
            DROP COLUMN IF EXISTS test_institution,
            DROP COLUMN IF EXISTS test_date
        """
    )
