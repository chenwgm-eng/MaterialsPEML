"""0032: 实验结果记录联合唯一约束

T-021：防止对同一样品同一属性同一时间点重复入库。
- experiment.experiment_result_records 增加 UNIQUE 约束
  (experiment_order_id, property_name, sample_id, uploaded_at)

注意：实际表结构使用 experiment_order_id（非 order_id）与 uploaded_at（非 created_at），
二者为本表中分别记录实验任务单 ID 与结果录入时间点的列，符合"同一样品同一属性同一时间点"的去重语义。

Revision ID: 0032_experiment_result_unique_constraint
Revises: 0031_result_data_quality
"""

from alembic import op

revision = "0032_experiment_result_unique_constraint"
down_revision = "0031_result_data_quality"
branch_labels = None
depends_on = None


_CONSTRAINT_NAME = "uq_results_order_property_sample_time"


def upgrade() -> None:
    op.execute(
        f"ALTER TABLE experiment.experiment_result_records "
        f"ADD CONSTRAINT {_CONSTRAINT_NAME} "
        f"UNIQUE (experiment_order_id, property_name, sample_id, uploaded_at)"
    )


def downgrade() -> None:
    op.execute(
        f"ALTER TABLE experiment.experiment_result_records "
        f"DROP CONSTRAINT IF EXISTS {_CONSTRAINT_NAME}"
    )
