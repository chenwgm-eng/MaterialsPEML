"""GNoME 真实数据落库：gnome.gnome_materials。

将完整 GNoME 稳定集导入统一 PostgreSQL，作为离线真实数据源，
替代原先的硬编码本地回退（local_db_fallback）。元素过滤走 GIN 索引，
化学式/材料 ID 走 btree 索引。
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0052_gnome_materials"
down_revision: Union[str, None] = "0051_equipment_tenant_isolation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS gnome")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS gnome.gnome_materials (
            id BIGSERIAL PRIMARY KEY,
            formula TEXT NOT NULL DEFAULT '',
            reduced_formula TEXT NOT NULL DEFAULT '',
            space_group TEXT NOT NULL DEFAULT '',
            structure_type TEXT NOT NULL DEFAULT '',
            energy_above_hull DOUBLE PRECISION NOT NULL DEFAULT 0,
            band_gap DOUBLE PRECISION NOT NULL DEFAULT 0,
            formation_energy DOUBLE PRECISION NOT NULL DEFAULT 0,
            material_id TEXT NOT NULL DEFAULT '',
            ionic_conductivity DOUBLE PRECISION NOT NULL DEFAULT 0,
            elements TEXT[] NOT NULL DEFAULT '{}',
            source TEXT NOT NULL DEFAULT 'gnome'
        )
        """
    )
    # 元素过滤：GIN 索引（elements @> 目标元素集）
    op.execute("CREATE INDEX IF NOT EXISTS idx_gnome_elements ON gnome.gnome_materials USING GIN (elements)")
    # 化学式 / 材料 ID 查询索引
    op.execute("CREATE INDEX IF NOT EXISTS idx_gnome_formula ON gnome.gnome_materials (reduced_formula)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_gnome_material_id ON gnome.gnome_materials (material_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS gnome.gnome_materials")
    op.execute("DROP SCHEMA IF EXISTS gnome")