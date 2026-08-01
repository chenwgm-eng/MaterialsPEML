"""0035: SCP 异步任务归档表（T-034 混合生命周期归档）

决策 D-09：混合保留策略
- 活跃任务（pending/submitted/running/polling）：永久保留
- 已完成（completed/cancelled）：30 天后归档
- 失败（failed/timeout）：90 天后归档

新增 integrations.scp_task_archive 表，结构与 integrations.scp_tasks 相同，
额外增加 archived_at TIMESTAMPTZ 列记录归档时间。

时间判定基于 completed_at（scp_tasks 表无 updated_at 列；所有终态任务均设置
completed_at，语义即"进入终态的时刻"）。

Revision ID: 0035_scp_task_archive
Revises: 0034_external_invocations_input_full
"""
from __future__ import annotations

from alembic import op


revision = "0035_scp_task_archive"
down_revision = "0034_external_invocations_input_full"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS integrations.scp_task_archive (
            task_id          TEXT PRIMARY KEY,
            scp_task_id      TEXT DEFAULT '',
            ecml_run_id      TEXT DEFAULT '',
            candidate_id     TEXT DEFAULT '',
            step             TEXT DEFAULT '',
            server_id        TEXT DEFAULT '',
            tool_name        TEXT DEFAULT '',
            arguments        JSONB DEFAULT '{}'::jsonb,
            status           TEXT NOT NULL DEFAULT 'pending',
            result           JSONB DEFAULT '{}'::jsonb,
            error_message    TEXT DEFAULT '',
            created_at       TIMESTAMPTZ DEFAULT NOW(),
            submitted_at     TIMESTAMPTZ,
            completed_at     TIMESTAMPTZ,
            next_poll_at     TIMESTAMPTZ DEFAULT NOW(),
            timeout_at       TIMESTAMPTZ DEFAULT NOW() + INTERVAL '30 minutes',
            retry_count      INTEGER DEFAULT 0,
            max_retries      INTEGER DEFAULT 3,
            archived_at      TIMESTAMPTZ DEFAULT NOW(),
            CONSTRAINT chk_scp_task_archive_status CHECK (
                status IN ('pending', 'submitted', 'running', 'polling',
                           'completed', 'failed', 'timeout', 'cancelled')
            )
        )
        """
    )
    # 归档表查询索引：按状态 + 完成时间（归档扫描与按状态检索）
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_scp_task_archive_status_completed "
        "ON integrations.scp_task_archive(status, completed_at)"
    )
    # 按 ECML 运行查询归档任务
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_scp_task_archive_ecml_run "
        "ON integrations.scp_task_archive(ecml_run_id, step)"
    )
    # 按归档时间排序（list_archived_tasks 分页）
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_scp_task_archive_archived_at "
        "ON integrations.scp_task_archive(archived_at)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS integrations.scp_task_archive")
