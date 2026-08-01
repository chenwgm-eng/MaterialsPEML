"""0026_scp_async_tasks

新增 SCP 异步任务持久化表：integrations.scp_tasks

背景：SCP 材料专题接入后，VASP/PySCF/LAMMPS 等远程计算耗时较长（5-30 分钟），
同步阻塞会导致 ECML 引擎线程被占用。改为异步任务模式：
- ECML step5 提交任务后暂停，释放引擎
- 后台 worker 线程轮询任务状态
- 任务完成后 worker 触发 ECML 恢复

表结构：
- task_id: 本地任务 ID（uuid）
- scp_task_id: SCP 服务端返回的任务 ID
- ecml_run_id / candidate_id: 关联上下文
- status: pending/submitted/running/polling/completed/failed/timeout/cancelled
- result: 完成后的结果数据（JSONB）
- next_poll_at: 下次轮询时间（控制 30s 间隔）
- timeout_at: 超时截止时间（created_at + 30min）
- retry_count / max_retries: 自动重试机制
"""
from __future__ import annotations

from alembic import op


revision = "0026_scp_async_tasks"
down_revision = "0025_mdm_props_units_fill"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS integrations.scp_tasks (
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
            CONSTRAINT chk_scp_task_status CHECK (
                status IN ('pending', 'submitted', 'running', 'polling',
                           'completed', 'failed', 'timeout', 'cancelled')
            )
        )
        """
    )
    # worker 调度索引：扫描待处理任务（status + next_poll_at + 未超时）
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_scp_tasks_poll "
        "ON integrations.scp_tasks(status, next_poll_at, timeout_at)"
    )
    # 按 ECML 运行查询任务（恢复 step5 时使用）
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_scp_tasks_ecml_run "
        "ON integrations.scp_tasks(ecml_run_id, step)"
    )
    # 按候选查询任务（前端展示）
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_scp_tasks_candidate "
        "ON integrations.scp_tasks(candidate_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS integrations.scp_tasks")
