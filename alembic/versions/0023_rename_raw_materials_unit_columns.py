"""rename raw_materials unit-embedded columns

Revision ID: 0023_rename_rm_cols
Revises: 0022_add_inv_unit
Create Date: 2026-07-27

彻底重构第一步：去除 industrialization.raw_materials 表中字段名硬编码的单位后缀。
原 inventory_kg / cost_per_kg 字段名含单位（kg / per_kg），
但 0022 迁移已新增 inventory_unit 列引入"值 + 单位"模式，
新旧两种模式并存会导致 schema 自相矛盾。

本次重命名：
  - inventory_kg  → inventory_quantity  （库存数量，单位由 inventory_unit 决定）
  - cost_per_kg   → unit_cost           （单位成本，货币+单位由 inventory_unit 决定）

注：其他业务/运维字段（historical_cycle_days、duration_ms、latency_ms 等）
虽字段名也含单位后缀，但属于纯业务/运维指标，与"物性单位主数据联动"主旨无关，
为避免触及无关运维代码，本次不重命名。
"""
from alembic import op
import sqlalchemy as sa


revision = "0023_rename_rm_cols"
down_revision = "0022_add_inv_unit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PostgreSQL 支持批量 RENAME COLUMN
    op.alter_column(
        "raw_materials",
        "inventory_kg",
        new_column_name="inventory_quantity",
        schema="industrialization",
        existing_type=sa.Float(),
    )
    op.alter_column(
        "raw_materials",
        "cost_per_kg",
        new_column_name="unit_cost",
        schema="industrialization",
        existing_type=sa.Float(),
    )


def downgrade() -> None:
    op.alter_column(
        "raw_materials",
        "unit_cost",
        new_column_name="cost_per_kg",
        schema="industrialization",
        existing_type=sa.Float(),
    )
    op.alter_column(
        "raw_materials",
        "inventory_quantity",
        new_column_name="inventory_kg",
        schema="industrialization",
        existing_type=sa.Float(),
    )
