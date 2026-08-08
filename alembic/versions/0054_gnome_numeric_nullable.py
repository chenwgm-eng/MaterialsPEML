"""gnome.gnome_materials 数值列允许 NULL。

区分"未测得"（NULL）与真实 0（如带隙 0 = 金属）。此前导入脚本把缺失伪造为 0.0，
导致语义混淆；放开 NOT NULL 使新导入可存 NULL。已有 0.0 数据无法回溯区分，保持现状。
"""
from __future__ import annotations

from alembic import op
from typing import Sequence, Union

revision: str = "0054_gnome_numeric_nullable"
down_revision: Union[str, None] = "0053_gnome_material_id_unique"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NUMERIC_COLS = (
    "energy_above_hull",
    "band_gap",
    "formation_energy",
    "ionic_conductivity",
)


def upgrade() -> None:
    for col in _NUMERIC_COLS:
        op.execute(f"ALTER TABLE gnome.gnome_materials ALTER COLUMN {col} DROP NOT NULL")


def downgrade() -> None:
    for col in _NUMERIC_COLS:
        op.execute(f"ALTER TABLE gnome.gnome_materials ALTER COLUMN {col} SET NOT NULL")