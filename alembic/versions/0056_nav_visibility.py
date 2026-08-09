"""导航可见性覆盖表 auth.nav_visibility。

仅控制「导航是否显示」，不替代任何操作权限。每个 (tenant_id, role, entry_key)
一行，visible 默认 TRUE；visible=false 表示该角色的该入口被隐藏。
权限下限由前端 requiredAnyPermission + 后端 permission 判定保证：visible=true
不能把无最小权限的入口变可见。

迁移链：0054 → 0055(ECML) → 0056(nav_visibility) → 0057(user_disciplines)。
"""
from __future__ import annotations

from alembic import op
from typing import Sequence, Union

revision: str = "0056_nav_visibility"
down_revision: Union[str, None] = "0055_ecml_runs_index_project_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE auth.nav_visibility (
            id SERIAL PRIMARY KEY,
            tenant_id TEXT NOT NULL DEFAULT current_setting('app.tenant_id', true),
            role TEXT NOT NULL,
            entry_key TEXT NOT NULL,
            visible BOOL NOT NULL DEFAULT TRUE,
            updated_by TEXT,
            updated_at TIMESTAMPTZ DEFAULT now(),
            UNIQUE (tenant_id, role, entry_key)
        )"""
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS auth.nav_visibility")