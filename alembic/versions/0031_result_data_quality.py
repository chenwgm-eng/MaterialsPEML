"""0031: 实验结果记录增加 data_quality 数据质量分层字段

评测修复 P2-5（BEMCL-DATA-P2-005）：
- experiment.experiment_result_records 新增 data_quality TEXT 列
- 取值：verified（实测已审）/ estimated（估算，默认）/ simulated（模拟）/ literature（文献）
- 回填规则：qc_status 已为 VALID/VALID_WITH_WARNING 的历史记录置 verified，其余置 estimated
- QC 审批通过时由 API 层自动升级为 verified

Revision ID: 0031_result_data_quality
Revises: 0030_fix_category_fk_schema
"""

from alembic import op

revision = "0031_result_data_quality"
down_revision = "0030_fix_category_fk_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE experiment.experiment_result_records "
        "ADD COLUMN IF NOT EXISTS data_quality TEXT"
    )
    # 历史数据回填：已通过 QC 的标记 verified，其余默认 estimated
    op.execute(
        "UPDATE experiment.experiment_result_records "
        "SET data_quality = CASE "
        "  WHEN qc_status IN ('VALID', 'VALID_WITH_WARNING') THEN 'verified' "
        "  ELSE 'estimated' END "
        "WHERE data_quality IS NULL"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE experiment.experiment_result_records "
        "DROP COLUMN IF EXISTS data_quality"
    )
