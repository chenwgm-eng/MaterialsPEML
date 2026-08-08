"""为 gnome.gnome_materials.material_id 增加唯一索引。

去重逻辑（import_gnome / GnomeMaterialStore.bulk_insert）是应用层 EXISTS 检查，
非原子；加唯一索引把去重交给 DB，杜绝并发导入竞态。已有数据已确认无重复
（count == count(distinct material_id)），可安全加唯一索引。
"""
from __future__ import annotations

from alembic import op
from typing import Sequence, Union

revision: str = "0053_gnome_material_id_unique"
down_revision: Union[str, None] = "0052_gnome_materials"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_gnome_material_id_unique "
        "ON gnome.gnome_materials (material_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_gnome_material_id_unique")