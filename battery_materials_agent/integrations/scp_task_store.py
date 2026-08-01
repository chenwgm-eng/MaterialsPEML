"""SCP 异步任务持久化 Store — CRUD + 状态流转 + 重试/取消 + 归档。

Schema:
- integrations.scp_tasks（由 alembic 0026 管理）
- integrations.scp_task_archive（由 alembic 0035 管理，T-034 混合生命周期归档）

状态机：
    pending → submitted → running → polling → completed
                                           ↘ failed
                                           ↘ timeout
                                           ↘ cancelled

容错策略：
- 失败自动重试：retry_count < max_retries 时重置为 pending，指数退避
- 用户取消：pending/submitted/running/polling 均可取消
- 超时清理：超过 timeout_at 仍非终态，标记 timeout
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text

from ..db import get_engine


# 任务终态（worker 不再处理）
TERMINAL_STATUSES = {"completed", "failed", "timeout", "cancelled"}

# 可取消的状态（用户主动取消时只针对这些状态）
CANCELLABLE_STATUSES = {"pending", "submitted", "running", "polling"}

# 默认超时 30 分钟
DEFAULT_TIMEOUT_MINUTES = 30

# 默认最大重试次数
DEFAULT_MAX_RETRIES = 3

# T-034 归档保留期默认值（与 AgentConfig 默认值一致；可由调用方覆盖）
DEFAULT_COMPLETED_RETENTION_DAYS = 30  # completed/cancelled 归档阈值
DEFAULT_FAILED_RETENTION_DAYS = 90     # failed/timeout 归档阈值

# 归档目标状态分组
COMPLETED_ARCHIVE_STATUSES = ("completed", "cancelled")
FAILED_ARCHIVE_STATUSES = ("failed", "timeout")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _to_iso(dt: Any) -> str | None:
    if dt is None:
        return None
    if isinstance(dt, datetime):
        return dt.isoformat() if dt.tzinfo else dt.replace(tzinfo=timezone.utc).isoformat()
    return str(dt)


class SCPTaskRecord:
    """SCP 任务记录 DTO（便于上层使用，不依赖 SQLAlchemy Row）。"""

    def __init__(self, **kwargs: Any):
        self.task_id: str = kwargs.get("task_id", "")
        self.scp_task_id: str = kwargs.get("scp_task_id", "")
        self.ecml_run_id: str = kwargs.get("ecml_run_id", "")
        self.candidate_id: str = kwargs.get("candidate_id", "")
        self.step: str = kwargs.get("step", "")
        self.server_id: str = kwargs.get("server_id", "")
        self.tool_name: str = kwargs.get("tool_name", "")
        self.arguments: dict = kwargs.get("arguments", {}) or {}
        self.status: str = kwargs.get("status", "pending")
        self.result: dict = kwargs.get("result", {}) or {}
        self.error_message: str = kwargs.get("error_message", "")
        self.created_at = kwargs.get("created_at")
        self.submitted_at = kwargs.get("submitted_at")
        self.completed_at = kwargs.get("completed_at")
        self.next_poll_at = kwargs.get("next_poll_at")
        self.timeout_at = kwargs.get("timeout_at")
        self.retry_count: int = kwargs.get("retry_count", 0)
        self.max_retries: int = kwargs.get("max_retries", DEFAULT_MAX_RETRIES)
        # 归档表专用字段（活跃表无此列；from_row 容忍多余键）
        self.archived_at = kwargs.get("archived_at")

    @classmethod
    def from_row(cls, row) -> "SCPTaskRecord":
        d = dict(row._mapping)
        # JSONB 列防御性解析
        for k in ("arguments", "result"):
            v = d.get(k)
            if isinstance(v, str):
                try:
                    d[k] = json.loads(v)
                except (json.JSONDecodeError, TypeError):
                    d[k] = {}
        return cls(**d)

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "scp_task_id": self.scp_task_id,
            "ecml_run_id": self.ecml_run_id,
            "candidate_id": self.candidate_id,
            "step": self.step,
            "server_id": self.server_id,
            "tool_name": self.tool_name,
            "arguments": self.arguments,
            "status": self.status,
            "result": self.result,
            "error_message": self.error_message,
            "created_at": _to_iso(self.created_at),
            "submitted_at": _to_iso(self.submitted_at),
            "completed_at": _to_iso(self.completed_at),
            "next_poll_at": _to_iso(self.next_poll_at),
            "timeout_at": _to_iso(self.timeout_at),
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "archived_at": _to_iso(self.archived_at),
        }


class SCPTaskStore:
    """SCP 异步任务的持久化 CRUD。

    所有写入操作使用事务（engine.begin），保证状态流转原子性。
    读取操作使用只读连接（engine.connect）。
    """

    def __init__(self):
        self.engine = get_engine()

    # ── 创建 ────────────────────────────────────────────────────────────

    def create(
        self,
        *,
        ecml_run_id: str = "",
        candidate_id: str = "",
        step: str = "",
        server_id: str = "",
        tool_name: str = "",
        arguments: dict | None = None,
        timeout_minutes: int = DEFAULT_TIMEOUT_MINUTES,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ) -> SCPTaskRecord:
        """创建一个新的 SCP 异步任务记录，返回完整 DTO。"""
        task_id = f"scptask-{uuid.uuid4().hex[:12]}"
        now = _now()
        timeout_at = now + timedelta(minutes=timeout_minutes)
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """INSERT INTO integrations.scp_tasks
                    (task_id, ecml_run_id, candidate_id, step, server_id, tool_name,
                     arguments, status, created_at, next_poll_at, timeout_at, max_retries)
                    VALUES
                    (:task_id, :ecml_run_id, :candidate_id, :step, :server_id, :tool_name,
                     CAST(:arguments AS JSONB), 'pending', :now, :now, :timeout_at, :max_retries)"""
                ),
                {
                    "task_id": task_id,
                    "ecml_run_id": ecml_run_id,
                    "candidate_id": candidate_id,
                    "step": step,
                    "server_id": server_id,
                    "tool_name": tool_name,
                    "arguments": json.dumps(arguments or {}),
                    "now": now,
                    "timeout_at": timeout_at,
                    "max_retries": max_retries,
                },
            )
        return self.get(task_id)

    # ── 读取 ────────────────────────────────────────────────────────────

    def get(self, task_id: str) -> SCPTaskRecord | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM integrations.scp_tasks WHERE task_id=:tid"),
                {"tid": task_id},
            ).first()
        return SCPTaskRecord.from_row(row) if row else None

    def list_by_ecml_run(self, ecml_run_id: str, step: str = "") -> list[SCPTaskRecord]:
        """按 ECML run_id 查询任务（step5 恢复时使用）。"""
        sql = "SELECT * FROM integrations.scp_tasks WHERE ecml_run_id=:rid"
        params: dict = {"rid": ecml_run_id}
        if step:
            sql += " AND step=:step"
            params["step"] = step
        sql += " ORDER BY created_at ASC"
        with self.engine.connect() as conn:
            rows = conn.execute(text(sql), params).all()
        return [SCPTaskRecord.from_row(r) for r in rows]

    def list_by_candidate(self, candidate_id: str) -> list[SCPTaskRecord]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT * FROM integrations.scp_tasks WHERE candidate_id=:cid "
                    "ORDER BY created_at ASC"
                ),
                {"cid": candidate_id},
            ).all()
        return [SCPTaskRecord.from_row(r) for r in rows]

    def list_pending(self, limit: int = 10) -> list[SCPTaskRecord]:
        """worker 调度：扫描待处理任务（非终态 + 到轮询时间 + 未超时）。"""
        now = _now()
        with self.engine.connect() as conn:
            rows = conn.execute(
                text(
                    """SELECT * FROM integrations.scp_tasks
                    WHERE status = ANY(:active_statuses)
                      AND next_poll_at <= :now
                      AND timeout_at > :now
                    ORDER BY next_poll_at ASC
                    LIMIT :limit"""
                ),
                {
                    "active_statuses": list({"pending", "submitted", "running", "polling"}),
                    "now": now,
                    "limit": limit,
                },
            ).all()
        return [SCPTaskRecord.from_row(r) for r in rows]

    def list_timed_out(self, limit: int = 20) -> list[SCPTaskRecord]:
        """扫描超时任务（非终态 + 已过 timeout_at）。"""
        now = _now()
        with self.engine.connect() as conn:
            rows = conn.execute(
                text(
                    """SELECT * FROM integrations.scp_tasks
                    WHERE status = ANY(:active_statuses)
                      AND timeout_at <= :now
                    LIMIT :limit"""
                ),
                {
                    "active_statuses": list({"pending", "submitted", "running", "polling"}),
                    "now": now,
                    "limit": limit,
                },
            ).all()
        return [SCPTaskRecord.from_row(r) for r in rows]

    # ── 状态流转 ────────────────────────────────────────────────────────

    def mark_submitted(self, task_id: str, scp_task_id: str) -> None:
        """任务已提交到 SCP 服务端，记录服务端返回的 task_id。"""
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """UPDATE integrations.scp_tasks SET
                        scp_task_id=:scp_task_id, status='submitted',
                        submitted_at=COALESCE(submitted_at, NOW()),
                        next_poll_at=NOW()
                    WHERE task_id=:tid AND status='pending'"""
                ),
                {"tid": task_id, "scp_task_id": scp_task_id},
            )

    def mark_running(self, task_id: str) -> None:
        """SCP 服务端返回 running 状态。"""
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """UPDATE integrations.scp_tasks SET status='running', next_poll_at=NOW()
                    WHERE task_id=:tid AND status IN ('submitted','polling')"""
                ),
                {"tid": task_id},
            )

    def schedule_next_poll(self, task_id: str, interval_seconds: int = 30) -> None:
        """更新下次轮询时间（控制 30s 间隔，避免压垮 SCP hub）。"""
        next_at = _now() + timedelta(seconds=interval_seconds)
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """UPDATE integrations.scp_tasks SET next_poll_at=:next_at
                    WHERE task_id=:tid AND status IN ('submitted','running','polling')"""
                ),
                {"tid": task_id, "next_at": next_at},
            )

    def mark_completed(self, task_id: str, result: dict) -> None:
        """任务成功完成。"""
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """UPDATE integrations.scp_tasks SET
                        status='completed', result=CAST(:result AS JSONB),
                        completed_at=NOW(), error_message=''
                    WHERE task_id=:tid"""
                ),
                {"tid": task_id, "result": json.dumps(result)},
            )

    def mark_failed(self, task_id: str, error: str) -> None:
        """任务失败。若 retry_count < max_retries，重置为 pending 触发重试。"""
        with self.engine.begin() as conn:
            # 先读当前重试次数
            row = conn.execute(
                text("SELECT retry_count, max_retries FROM integrations.scp_tasks WHERE task_id=:tid"),
                {"tid": task_id},
            ).first()
            if row is None:
                return
            retry_count, max_retries = row[0], row[1]
            if retry_count < max_retries:
                # 指数退避：2^retry_count 秒后重试
                backoff_seconds = 2 ** retry_count
                next_at = _now() + timedelta(seconds=backoff_seconds)
                conn.execute(
                    text(
                        """UPDATE integrations.scp_tasks SET
                            status='pending', error_message=:err,
                            retry_count=retry_count+1, next_poll_at=:next_at
                        WHERE task_id=:tid"""
                    ),
                    {"tid": task_id, "err": error[:500], "next_at": next_at},
                )
            else:
                # 重试耗尽，标 failed
                conn.execute(
                    text(
                        """UPDATE integrations.scp_tasks SET
                            status='failed', error_message=:err, completed_at=NOW()
                        WHERE task_id=:tid"""
                    ),
                    {"tid": task_id, "err": error[:500]},
                )

    def mark_timeout(self, task_id: str) -> None:
        """任务超过 timeout_at 仍未完成。"""
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """UPDATE integrations.scp_tasks SET
                        status='timeout', completed_at=NOW(),
                        error_message='Task exceeded timeout_at'
                    WHERE task_id=:tid AND status = ANY(:active)"""
                ),
                {"tid": task_id, "active": list({"pending", "submitted", "running", "polling"})},
            )

    def cancel(self, task_id: str) -> bool:
        """用户主动取消。仅对非终态任务有效。

        Returns:
            True 若取消成功，False 若任务已是终态不可取消
        """
        with self.engine.begin() as conn:
            result = conn.execute(
                text(
                    """UPDATE integrations.scp_tasks SET
                        status='cancelled', completed_at=NOW(),
                        error_message='Cancelled by user'
                    WHERE task_id=:tid AND status = ANY(:cancellable)"""
                ),
                {"tid": task_id, "cancellable": list(CANCELLABLE_STATUSES)},
            )
            return result.rowcount > 0

    # ── ECML step5 恢复辅助 ────────────────────────────────────────────

    def all_completed_for_run(self, ecml_run_id: str, step: str = "step5_verify") -> bool:
        """检查某个 ECML run + step 的所有任务是否都已进入终态。

        step5 恢复时调用：若所有任务终态，则可恢复 ECML；否则继续等待。
        """
        with self.engine.connect() as conn:
            row = conn.execute(
                text(
                    """SELECT COUNT(*) AS total,
                        COUNT(*) FILTER (WHERE status = ANY(:terminal)) AS done
                    FROM integrations.scp_tasks
                    WHERE ecml_run_id=:rid AND step=:step"""
                ),
                {
                    "rid": ecml_run_id,
                    "step": step,
                    "terminal": list(TERMINAL_STATUSES),
                },
            ).first()
        if row is None or row[0] == 0:
            return False
        return row[0] == row[1]

    # ── 归档（T-034 混合生命周期）──────────────────────────────────────

    def archive_old_tasks(
        self,
        completed_retention_days: int = DEFAULT_COMPLETED_RETENTION_DAYS,
        failed_retention_days: int = DEFAULT_FAILED_RETENTION_DAYS,
    ) -> dict:
        """按混合保留策略归档终态任务（决策 D-09）。

        - completed/cancelled 且 completed_at < now() - completed_retention_days → 归档
        - failed/timeout 且 completed_at < now() - failed_retention_days → 归档
        - 活跃任务（pending/submitted/running/polling）：永久保留，不归档

        迁移在单事务内完成（INSERT + DELETE 原子操作）。

        Returns:
            dict: {
                "archived_completed": int,  # completed/cancelled 归档数
                "archived_failed": int,     # failed/timeout 归档数
                "total": int,               # 合计
            }
        """
        now = _now()
        completed_cutoff = now - timedelta(days=completed_retention_days)
        failed_cutoff = now - timedelta(days=failed_retention_days)

        # 归档表列与活跃表一致（外加 archived_at）。INSERT ... SELECT 一次性迁移，
        # 避免在 Python 层搬运数据；DELETE WHERE task_id IN (...) 复用同一子查询。
        completed_insert = text(
            """
            INSERT INTO integrations.scp_task_archive
                (task_id, scp_task_id, ecml_run_id, candidate_id, step, server_id,
                 tool_name, arguments, status, result, error_message,
                 created_at, submitted_at, completed_at, next_poll_at, timeout_at,
                 retry_count, max_retries, archived_at)
            SELECT task_id, scp_task_id, ecml_run_id, candidate_id, step, server_id,
                   tool_name, arguments, status, result, error_message,
                   created_at, submitted_at, completed_at, next_poll_at, timeout_at,
                   retry_count, max_retries, :now
            FROM integrations.scp_tasks
            WHERE status = ANY(:completed_statuses)
              AND completed_at IS NOT NULL
              AND completed_at < :cutoff
            """
        )
        completed_delete = text(
            """
            DELETE FROM integrations.scp_tasks
            WHERE status = ANY(:completed_statuses)
              AND completed_at IS NOT NULL
              AND completed_at < :cutoff
            """
        )
        failed_insert = text(
            """
            INSERT INTO integrations.scp_task_archive
                (task_id, scp_task_id, ecml_run_id, candidate_id, step, server_id,
                 tool_name, arguments, status, result, error_message,
                 created_at, submitted_at, completed_at, next_poll_at, timeout_at,
                 retry_count, max_retries, archived_at)
            SELECT task_id, scp_task_id, ecml_run_id, candidate_id, step, server_id,
                   tool_name, arguments, status, result, error_message,
                   created_at, submitted_at, completed_at, next_poll_at, timeout_at,
                   retry_count, max_retries, :now
            FROM integrations.scp_tasks
            WHERE status = ANY(:failed_statuses)
              AND completed_at IS NOT NULL
              AND completed_at < :cutoff
            """
        )
        failed_delete = text(
            """
            DELETE FROM integrations.scp_tasks
            WHERE status = ANY(:failed_statuses)
              AND completed_at IS NOT NULL
              AND completed_at < :cutoff
            """
        )

        archived_completed = 0
        archived_failed = 0
        with self.engine.begin() as conn:
            # 先归档已完成组（INSERT + DELETE），再归档失败组。
            # 单事务保证原子性：任一步失败则整体回滚，活跃表与归档表始终保持一致。
            r = conn.execute(
                completed_insert,
                {
                    "completed_statuses": list(COMPLETED_ARCHIVE_STATUSES),
                    "cutoff": completed_cutoff,
                    "now": now,
                },
            )
            archived_completed = r.rowcount or 0
            conn.execute(
                completed_delete,
                {
                    "completed_statuses": list(COMPLETED_ARCHIVE_STATUSES),
                    "cutoff": completed_cutoff,
                },
            )
            r = conn.execute(
                failed_insert,
                {
                    "failed_statuses": list(FAILED_ARCHIVE_STATUSES),
                    "cutoff": failed_cutoff,
                    "now": now,
                },
            )
            archived_failed = r.rowcount or 0
            conn.execute(
                failed_delete,
                {
                    "failed_statuses": list(FAILED_ARCHIVE_STATUSES),
                    "cutoff": failed_cutoff,
                },
            )

        return {
            "archived_completed": archived_completed,
            "archived_failed": archived_failed,
            "total": archived_completed + archived_failed,
        }

    def list_archived_tasks(self, limit: int = 50, offset: int = 0) -> list[SCPTaskRecord]:
        """分页查询归档任务（按归档时间倒序）。"""
        with self.engine.connect() as conn:
            rows = conn.execute(
                text(
                    """SELECT * FROM integrations.scp_task_archive
                    ORDER BY archived_at DESC
                    LIMIT :limit OFFSET :offset"""
                ),
                {"limit": limit, "offset": offset},
            ).all()
        return [SCPTaskRecord.from_row(r) for r in rows]

