"""ecml.ecml_runs_index 回填 project_id。

ecml.ecml_runs_index.project_id 列在 0009 已存在（默认 ''），但 ECMLRunStore.save()
从未写入该列，导致按项目过滤 ECML 运行记录无法生效。本迁移做三分类回填：

1. 可唯一关联 → 通过 task_id JOIN projects.tasks 回填 project_id；
2. 无法关联（task_id 为空 / 不在 projects.tasks）→ 保持 NULL，全局历史可查；
3. 冲突或项目不存在 → 不写入，记原因交管理员处置。

回填来源(projectId via task_id)/时间/脚本版本/三分类数量写入 audit.audit_log。

迁移链：0054 → 0055(ECML) → 0056 → 0057。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from alembic import op
from typing import Sequence, Union

revision: str = "0055_ecml_runs_index_project_id"
down_revision: Union[str, None] = "0054_gnome_numeric_nullable"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SCRIPT_VERSION = "0055.1"


def upgrade() -> None:
    conn = op.get_bind()

    # 列已存在（0009 添加），此处幂等兜底，并补索引
    conn.execute(
        "ALTER TABLE ecml.ecml_runs_index ADD COLUMN IF NOT EXISTS project_id TEXT DEFAULT ''"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ecml_runs_index_project_id "
        "ON ecml.ecml_runs_index(project_id)"
    )

    # 类别1：可唯一关联回填（task_id 非空且在 projects.tasks 中）
    linked = conn.execute(
        """UPDATE ecml.ecml_runs_index i
           SET project_id = t.project_id
           FROM projects.tasks t
           WHERE i.task_id = t.task_id
             AND i.task_id <> ''
             AND i.task_id IS NOT NULL
             AND (i.project_id IS NULL OR i.project_id = '')"""
    ).rowcount

    # 类别3：task_id 非空但对应项目不存在（task_id 在 index 中但 projects.tasks 无此任务）
    # 说明：task_id 指向失效任务，视为"项目不存在"，不写入、交管理员。仅统计数量。
    orphaned_task_ids = conn.execute(
        """SELECT DISTINCT i.task_id
           FROM ecml.ecml_runs_index i
           WHERE i.task_id <> ''
             AND i.task_id IS NOT NULL
             AND NOT EXISTS (SELECT 1 FROM projects.tasks t WHERE t.task_id = i.task_id)"""
    ).scalars().all()

    # 类别2：无法关联（task_id 为空）= 剩余保持 NULL 的记录数
    remaining = conn.execute(
        """SELECT COUNT(*) FROM ecml.ecml_runs_index
           WHERE project_id IS NULL OR project_id = ''"""
    ).scalar() or 0

    # 审计：回填来源/时间/脚本版本/三分类数量
    conn.execute(
        """INSERT INTO audit.audit_log
           (entry_id, event_type, module, action, detail, operator, created_at)
           VALUES (:entry_id, 'system', 'ecml', 'backfill_project_id',
                   :detail, 'migration:0055', :created_at)""",
        {
            "entry_id": str(uuid.uuid4()),
            "detail": {
                "source": "projects.tasks.task_id",
                "script_version": _SCRIPT_VERSION,
                "linked": linked,
                "unlinkable_null": remaining,
                "conflict_orphan_task_ids": list(orphaned_task_ids)[:100],
                "conflict_orphan_count": len(orphaned_task_ids),
            },
            "created_at": datetime.now(timezone.utc),
        },
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute("DROP INDEX IF EXISTS ecml.idx_ecml_runs_index_project_id")
    # 回填不可逆且不删列（0009 已有该列），仅将 project_id 置空还原
    conn.execute("UPDATE ecml.ecml_runs_index SET project_id = ''")