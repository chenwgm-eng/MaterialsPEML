"""research_requests 增加 material_system 列

Revision ID: 0048_add_material_system
Revises: 0047_kingfa_material_systems
Create Date: 2026-08-07

背景：material_scope 与 material_system 语义解耦。material_system 保存领域包
material_systems.name 的体系名（如"改性塑料"），material_scope 保留下游路由所需的
材料类型枚举（crystal/polymer/molecule）。research_store.create_request。
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0048_add_material_system"
down_revision: Union[str, None] = "0047_kingfa_material_systems"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE hybrid.research_requests
            ADD COLUMN IF NOT EXISTS material_system TEXT DEFAULT ''
        """
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE hybrid.research_requests DROP COLUMN IF EXISTS material_system"
    )