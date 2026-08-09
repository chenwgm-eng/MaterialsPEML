"""auth.users 增加专业画像字段 disciplines / primary_discipline。

专业画像（discipline）只影响默认体验，不影响权限。P0 不变量由 DB CHECK 强制：
- primary_discipline IS NULL 时 disciplines 可空/非空；
- 非 NULL 必 ∈ disciplines（杜绝 disciplines=['material_research'] 而 primary='experiment_analysis'）；
- 枚举值变更只走 migration；前端自由字符串在 API 层 400。

迁移链：0054 → 0056(nav_visibility) → 0057(user_disciplines)。
Step C 的 0055(ECML) 落地后，将 0056 的 down_revision 改为 0055 以插入链中
（最终 0054 → 0055 → 0056 → 0057）。
"""
from __future__ import annotations

from alembic import op
from typing import Sequence, Union

revision: str = "0057_user_disciplines"
down_revision: Union[str, None] = "0056_nav_visibility"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE auth.users ADD COLUMN disciplines JSONB NOT NULL DEFAULT '[]'::jsonb"
    )
    op.execute("ALTER TABLE auth.users ADD COLUMN primary_discipline TEXT")
    op.execute(
        "ALTER TABLE auth.users ADD CONSTRAINT disciplines_is_array "
        "CHECK (jsonb_typeof(disciplines)='array')"
    )
    op.execute(
        "ALTER TABLE auth.users ADD CONSTRAINT disciplines_values_valid "
        "CHECK (disciplines <@ '[\"material_research\",\"process_design\",\"experiment_analysis\"]'::jsonb)"
    )
    op.execute(
        "ALTER TABLE auth.users ADD CONSTRAINT primary_discipline_in_disciplines "
        "CHECK (primary_discipline IS NULL OR disciplines ? primary_discipline)"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE auth.users DROP CONSTRAINT IF EXISTS primary_discipline_in_disciplines"
    )
    op.execute(
        "ALTER TABLE auth.users DROP CONSTRAINT IF EXISTS disciplines_values_valid"
    )
    op.execute("ALTER TABLE auth.users DROP CONSTRAINT IF EXISTS disciplines_is_array")
    op.execute("ALTER TABLE auth.users DROP COLUMN IF EXISTS primary_discipline")
    op.execute("ALTER TABLE auth.users DROP COLUMN IF EXISTS disciplines")