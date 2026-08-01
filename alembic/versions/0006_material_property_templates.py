"""物料类型属性模板与物料属性值闭环

Revision ID: 0006_material_property_templates
Revises: 0005_strong_fk_constraints
Create Date: 2026-07-26

为 industrialization.raw_materials 新增 properties JSONB 列，
用于存储按属性字典模板录入的物料示例属性值。
同时新增 industrialization.material_type_templates 表，
建立「物料类型 -> 属性字段模板」的关联配置。
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006_material_property_templates"
down_revision: Union[str, None] = "0005_strong_fk_constraints"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. 物料示例新增动态属性值字段
    op.execute(
        """
        ALTER TABLE industrialization.raw_materials
            ADD COLUMN IF NOT EXISTS properties JSONB DEFAULT '{}'
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_raw_materials_properties "
        "ON industrialization.raw_materials USING GIN (properties)"
    )

    # 2. 物料类型 -> 属性字段模板配置表
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS industrialization.material_type_templates (
            material_type    TEXT PRIMARY KEY,
            field_keys       JSONB DEFAULT '[]',
            created_at       TIMESTAMPTZ DEFAULT NOW(),
            updated_at       TIMESTAMPTZ DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_mtt_field_keys "
        "ON industrialization.material_type_templates USING GIN (field_keys)"
    )


def downgrade() -> None:
    op.execute(
        "DROP INDEX IF EXISTS industrialization.idx_raw_materials_properties"
    )
    op.execute(
        "ALTER TABLE industrialization.raw_materials "
        "DROP COLUMN IF EXISTS properties"
    )
    op.execute(
        "DROP INDEX IF EXISTS industrialization.idx_mtt_field_keys"
    )
    op.execute(
        "DROP TABLE IF EXISTS industrialization.material_type_templates"
    )
