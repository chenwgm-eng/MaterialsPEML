"""添加强外键约束：candidate -> order -> sample -> result，附 ON DELETE RESTRICT。

Revision ID: 0005_strong_fk_constraints
Revises: 0004_compliance_evidence
Create Date: 2026-07-26

Task 14：利用 PostgreSQL 外键约束建立强关联对象模型。

替换 0001_initial_schema 中已存在的 FK 约束，统一加上 ON DELETE RESTRICT，
使得「删除有下游数据的候选材料 / 实验任务 / 样品」被数据库直接阻止。

涉及的 FK 约束：
1. experiment.experiment_orders.candidate_id       -> experiment.candidates(candidate_id)         [fk_orders_candidate]
2. experiment.samples.source_order_id              -> experiment.experiment_orders(order_id)       [fk_samples_order]
3. experiment.samples.source_candidate_id          -> experiment.candidates(candidate_id)          [fk_samples_candidate]
4. experiment.experiment_result_records.experiment_order_id
                                                   -> experiment.experiment_orders(order_id)       [fk_results_order]
5. experiment.sample_transfers.sample_id           -> experiment.samples(sample_id)               [fk_transfers_sample]

迁移策略：先 DROP 旧 FK，再 ADD 新 FK with ON DELETE RESTRICT。
- upgrade(): 替换为 ON DELETE RESTRICT
- downgrade(): 恢复为无 ON DELETE 行为的 FK（与 0001 保持一致）

数据完整性前提：迁移前需要确保无 dangling 引用（candidate_id / source_order_id /
source_candidate_id / experiment_order_id / sample_id 引用不存在的父记录）。
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005_strong_fk_constraints"
down_revision: Union[str, None] = "0004_compliance_evidence"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (table, constraint_name, column, ref_table, ref_column)
_FK_DEFS: list[tuple[str, str, str, str, str]] = [
    (
        "experiment.experiment_orders",
        "fk_orders_candidate",
        "candidate_id",
        "experiment.candidates",
        "candidate_id",
    ),
    (
        "experiment.samples",
        "fk_samples_order",
        "source_order_id",
        "experiment.experiment_orders",
        "order_id",
    ),
    (
        "experiment.samples",
        "fk_samples_candidate",
        "source_candidate_id",
        "experiment.candidates",
        "candidate_id",
    ),
    (
        "experiment.experiment_result_records",
        "fk_results_order",
        "experiment_order_id",
        "experiment.experiment_orders",
        "order_id",
    ),
    (
        "experiment.sample_transfers",
        "fk_transfers_sample",
        "sample_id",
        "experiment.samples",
        "sample_id",
    ),
]


def upgrade() -> None:
    """替换现有 FK 为带 ON DELETE RESTRICT 的版本。"""
    for table, constraint, column, ref_table, ref_column in _FK_DEFS:
        op.execute(
            f"ALTER TABLE {table} "
            f"DROP CONSTRAINT IF EXISTS {constraint}"
        )
        op.execute(
            f"ALTER TABLE {table} "
            f"ADD CONSTRAINT {constraint} "
            f"FOREIGN KEY ({column}) "
            f"REFERENCES {ref_table}({ref_column}) "
            f"ON DELETE RESTRICT"
        )


def downgrade() -> None:
    """恢复为无 ON DELETE 行为的 FK（与 0001 保持一致）。"""
    for table, constraint, column, ref_table, ref_column in _FK_DEFS:
        op.execute(
            f"ALTER TABLE {table} "
            f"DROP CONSTRAINT IF EXISTS {constraint}"
        )
        op.execute(
            f"ALTER TABLE {table} "
            f"ADD CONSTRAINT {constraint} "
            f"FOREIGN KEY ({column}) "
            f"REFERENCES {ref_table}({ref_column})"
        )
