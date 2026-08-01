"""SCP 异步任务后台 worker 线程。

决策 10a-2=A：独立后台线程（FastAPI 进程内）。
决策 11=C：自动重试 3 次 + 用户取消。

设计原则：
- worker 与具体工具解耦：通过 handler 注册机制分派
- handler 是同步函数：handler(task: SCPTaskRecord) -> tuple[str, dict]
  返回 (new_status, result_dict)
  - new_status ∈ {"completed", "submitted", "running", "failed"}
  - result_dict: 任务结果或中间状态信息
- 未注册 handler 的工具：worker 仅做超时清理，不触发执行
- worker 启动时若发现已有未完成任务（进程重启），自动接管

线程安全：worker 线程与 API 请求并发访问 store，store 本身使用 SQLAlchemy
事务保证原子性。worker 触发 ECML 恢复时使用 run_id 级互斥锁（scp_task_locks）。
"""
from __future__ import annotations

import logging
import threading
from typing import Callable

from .scp_task_store import SCPTaskRecord, SCPTaskStore

logger = logging.getLogger(__name__)


# Handler 类型：接收任务记录，返回 (new_status, result_dict)
# - new_status: "completed" | "submitted" | "running" | "failed"
# - result_dict: 任务结果或中间状态信息
TaskHandler = Callable[[SCPTaskRecord], "tuple[str, dict]"]


class SCPTaskWorker:
    """SCP 异步任务后台 worker。

    生命周期：
    - start()：启动后台线程（守护线程，进程退出时自动结束）
    - stop()：通知线程退出（设置 stop event，等待最多 5s）
    - register_handler(tool_name, handler)：注册工具处理器

    工作循环：
    1. 扫描超时任务 → mark_timeout
    2. 扫描待处理任务 → 按 tool_name 分派到 handler
    3. 无任务时 sleep 5s（worker 调度间隔）
    4. 处理任务时 sleep 1s（避免压垮 store）
    """

    # worker 调度间隔（无任务时）
    IDLE_INTERVAL_SECONDS = 5.0

    # 处理任务后的短暂休止（避免压垮 store/SCP）
    BUSY_INTERVAL_SECONDS = 1.0

    # 单轮最多处理的任务数
    BATCH_SIZE = 10

    def __init__(
        self,
        store: SCPTaskStore | None = None,
        on_task_completed: Callable[[SCPTaskRecord], None] | None = None,
    ):
        self.store = store or SCPTaskStore()
        # 任务完成后的回调（ECML step5 恢复钩子，由阶段 3 注入）
        self._on_task_completed = on_task_completed
        # 工具处理器注册表：tool_name -> handler
        self._handlers: dict[str, TaskHandler] = {}
        # 后台线程
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._started = False

    # ── 生命周期 ────────────────────────────────────────────────────────

    def start(self) -> None:
        """启动 worker 线程（幂等，重复调用无副作用）。"""
        if self._started:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="scp-task-worker",
            daemon=True,
        )
        self._thread.start()
        self._started = True
        logger.info("SCPTaskWorker started (daemon thread)")

    def stop(self, timeout: float = 5.0) -> None:
        """通知 worker 退出并等待最多 timeout 秒。"""
        if not self._started:
            return
        self._stop_event.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=timeout)
        self._started = False
        logger.info("SCPTaskWorker stopped")

    # ── Handler 注册 ────────────────────────────────────────────────────

    def register_handler(self, tool_name: str, handler: TaskHandler) -> None:
        """注册工具处理器。

        Args:
            tool_name: SCP 工具名（如 "VASP_calculate"）
            handler: 同步函数，接收 SCPTaskRecord，返回 (new_status, result_dict)
        """
        self._handlers[tool_name] = handler
        logger.info("SCPTaskWorker registered handler for tool=%s", tool_name)

    def unregister_handler(self, tool_name: str) -> None:
        self._handlers.pop(tool_name, None)

    # ── 工作循环 ────────────────────────────────────────────────────────

    def _run_loop(self) -> None:
        """worker 主循环。"""
        logger.info("SCPTaskWorker loop started")
        while not self._stop_event.is_set():
            try:
                processed = self._tick()
                # 休止
                sleep_seconds = (
                    self.BUSY_INTERVAL_SECONDS if processed > 0
                    else self.IDLE_INTERVAL_SECONDS
                )
                self._stop_event.wait(sleep_seconds)
            except Exception as e:
                # 任何异常都不能让 worker 退出
                logger.exception("SCPTaskWorker tick failed: %s", e)
                self._stop_event.wait(self.IDLE_INTERVAL_SECONDS)
        logger.info("SCPTaskWorker loop exited")

    def _tick(self) -> int:
        """单轮调度：超时清理 + 任务处理。返回处理的任务数。"""
        # 1. 清理超时任务
        try:
            timed_out = self.store.list_timed_out(limit=self.BATCH_SIZE)
            for t in timed_out:
                self.store.mark_timeout(t.task_id)
                logger.warning(
                    "SCPTaskWorker: task %s (tool=%s) timed out after retry_count=%d",
                    t.task_id, t.tool_name, t.retry_count,
                )
                # 超时也触发回调（让 ECML step5 知道任务终态）
                self._fire_completion_callback(t.task_id)
        except Exception as e:
            logger.warning("SCPTaskWorker: timeout cleanup failed: %s", e)

        # 2. 处理待执行任务
        processed = 0
        try:
            pending = self.store.list_pending(limit=self.BATCH_SIZE)
            for task in pending:
                self._process_task(task)
                processed += 1
        except Exception as e:
            logger.warning("SCPTaskWorker: pending scan failed: %s", e)

        return processed + (len(timed_out) if 'timed_out' in locals() else 0)

    def _process_task(self, task: SCPTaskRecord) -> None:
        """处理单个任务：按 tool_name 分派到 handler。"""
        handler = self._handlers.get(task.tool_name)
        if handler is None:
            # 未注册 handler：跳过（保持原状态，等待 handler 注册）
            # 但仍要触发轮询间隔，避免 worker 反复扫描这个任务
            self.store.schedule_next_poll(task.task_id, interval_seconds=60)
            logger.debug(
                "SCPTaskWorker: no handler for tool=%s (task=%s), deferred 60s",
                task.tool_name, task.task_id,
            )
            return

        try:
            new_status, result = handler(task)
        except Exception as e:
            logger.exception(
                "SCPTaskWorker: handler failed for task=%s tool=%s: %s",
                task.task_id, task.tool_name, e,
            )
            self.store.mark_failed(task.task_id, f"handler exception: {e}")
            self._fire_completion_callback(task.task_id)
            return

        # 根据 handler 返回的状态更新 store
        if new_status == "completed":
            self.store.mark_completed(task.task_id, result)
            self._fire_completion_callback(task.task_id)
        elif new_status == "submitted":
            scp_task_id = str(result.get("scp_task_id", ""))
            if scp_task_id:
                self.store.mark_submitted(task.task_id, scp_task_id)
            else:
                # handler 声明 submitted 但没给 scp_task_id，视为失败
                self.store.mark_failed(task.task_id, "handler returned submitted without scp_task_id")
            self.store.schedule_next_poll(task.task_id)
        elif new_status == "running":
            self.store.mark_running(task.task_id)
            self.store.schedule_next_poll(task.task_id)
        elif new_status == "failed":
            err = str(result.get("error", "handler returned failed"))
            self.store.mark_failed(task.task_id, err)
            self._fire_completion_callback(task.task_id)
        else:
            logger.warning(
                "SCPTaskWorker: handler returned unknown status=%s for task=%s",
                new_status, task.task_id,
            )
            self.store.schedule_next_poll(task.task_id)

    # ── ECML 恢复回调 ──────────────────────────────────────────────────

    def _fire_completion_callback(self, task_id: str) -> None:
        """任务进入终态后触发回调（ECML step5 恢复钩子）。

        回调内由上层（阶段 3 的 ECML 引擎改造）负责：
        1. 检查同 run_id 所有任务是否终态
        2. 若全部终态，获取 run_id 锁，恢复 ECML
        """
        if self._on_task_completed is None:
            return
        try:
            self._on_task_completed(task_id)
        except Exception as e:
            logger.exception(
                "SCPTaskWorker: on_task_completed callback failed for task=%s: %s",
                task_id, e,
            )


# ── 全局单例 ──────────────────────────────────────────────────────────

_global_worker: SCPTaskWorker | None = None
_global_lock = threading.Lock()


def get_worker() -> SCPTaskWorker:
    """获取全局 SCPTaskWorker 单例。

    首次调用时创建并启动 worker。FastAPI startup 时应调用此函数。
    """
    global _global_worker
    if _global_worker is not None:
        return _global_worker
    with _global_lock:
        if _global_worker is None:
            _global_worker = SCPTaskWorker()
            _global_worker.start()
    return _global_worker


def set_worker(worker: SCPTaskWorker | None) -> None:
    """替换全局 worker（测试用）。"""
    global _global_worker
    with _global_lock:
        if _global_worker is not None and _global_worker is not worker:
            _global_worker.stop()
        _global_worker = worker
