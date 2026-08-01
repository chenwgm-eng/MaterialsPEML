"""add inventory_unit column to raw_materials

Revision ID: 0022_add_inv_unit
Revises: 0021_cand_artifacts_proc
Create Date: 2026-07-27

为 industrialization.raw_materials 添加 inventory_unit 列，
使库存单位从主数据获取而非硬编码在字段名中。
"""
from alembic import op
import sqlalchemy as sa


revision = "0022_add_inv_unit"
down_revision = "0021_cand_artifacts_proc"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "raw_materials",
        sa.Column("inventory_unit", sa.String(20), nullable=False, server_default="kg"),
        schema="industrialization",
    )


def downgrade() -> None:
    op.drop_column("raw_materials", "inventory_unit", schema="industrialization")
