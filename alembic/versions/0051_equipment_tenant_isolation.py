"""设备台账租户隔离：experiment.equipment 补 tenant_id。

0050 迁移对核心业务表加了 tenant_id，但遗漏了 experiment.equipment，
导致设备台账无法按租户过滤。本迁移补齐该列并回填默认租户。
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0051_equipment_tenant_isolation"
down_revision: Union[str, None] = "0050_add_tenant_isolation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE experiment.equipment "
        "ADD COLUMN IF NOT EXISTS tenant_id TEXT NOT NULL DEFAULT 'default'"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_equipment_tenant "
        "ON experiment.equipment(tenant_id)"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE experiment.equipment DROP COLUMN IF EXISTS tenant_id")