"""Phase 1 CPU Worker — 科学任务后台执行器。

设计原则：
- 独立后台线程（FastAPI 进程内），与 SCPTaskWorker 类似
- 轮询 scientific_kernel.runs 表中的 QUEUED 状态 Run
- 根据 service_id 分派到对应的 NativeScientificService 实现
- 自动重试 3 次，失败后标记 FAILED
"""
from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING

from ..contracts.run import Run, RunStatus
from ..domain.runtime import ScientificExecutionKernel

if TYPE_CHECKING:
    from ..services.base_service import NativeScientificService

logger = logging.getLogger(__name__)


class ScientificCPUWorker:
    """科学任务 CPU Worker。

    生命周期：
    - start()：启动后台线程（守护线程，进程退出时自动结束）
    - stop()：通知线程退出
    - register_service(capability_id, service)：注册科学服务处理器
    """

    IDLE_INTERVAL_SECONDS = 5.0
    BUSY_INTERVAL_SECONDS = 1.0
    BATCH_SIZE = 10
    MAX_RETRIES = 3

    def __init__(self, kernel: ScientificExecutionKernel | None = None):
        self._kernel = kernel or ScientificExecutionKernel()
        self._services: dict[str, NativeScientificService] = {}
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def register_service(self, capability_id: str, service: NativeScientificService) -> None:
        """注册科学服务处理器。"""
        self._services[capability_id] = service
        logger.info("Worker registered service: %s", capability_id)

    def start(self) -> None:
        """启动后台 worker 线程。"""
        if self._thread and self._thread.is_alive():
            logger.warning("Worker already running")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="cpu-worker")
        self._thread.start()
        logger.info("CPU Worker started")

    def stop(self) -> None:
        """停止 worker 线程。"""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
            logger.info("CPU Worker stopped")

    def _run_loop(self) -> None:
        """主工作循环。"""
        while not self._stop_event.is_set():
            try:
                self._process_queued_runs()
            except Exception:
                logger.exception("CPU Worker iteration error")
            # 使用 Event.wait 实现可中断睡眠，stop() 设置事件后可立即唤醒
            self._stop_event.wait(self.IDLE_INTERVAL_SECONDS)

    def _process_queued_runs(self) -> None:
        """处理队列中的 Run。"""
        runs = self._kernel.list_runs(status=RunStatus.QUEUED, limit=self.BATCH_SIZE)
        if not runs:
            return

        for run in runs:
            if self._stop_event.is_set():
                break
            self._execute_run(run)
            time.sleep(self.BUSY_INTERVAL_SECONDS)

    def _execute_run(self, run: Run) -> None:
        """执行单个 Run。"""
        service = self._services.get(run.service_id)
        if service is None:
            logger.warning("No service registered for %s (run=%s)", run.service_id, run.run_id)
            self._kernel.update_run_status(run.run_id, RunStatus.FAILED)
            return

        # 将 Run 状态更新为 RUNNING
        self._kernel.update_run_status(run.run_id, RunStatus.RUNNING)

        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                # 执行服务（run.input 包含完整命令参数）
                context = {"input": run.input, "command": run.command}
                artifacts = service.execute(run, context)
                for art in artifacts:
                    self._kernel.store_artifact(art)
                evidence = service.postprocess(run, artifacts)
                for ev in evidence:
                    self._kernel.store_evidence(ev)

                self._kernel.update_run_status(run.run_id, RunStatus.SUCCEEDED)
                logger.info("Run %s completed successfully", run.run_id)
                return

            except Exception as exc:
                logger.warning(
                    "Run %s attempt %d/%d failed: %s",
                    run.run_id, attempt, self.MAX_RETRIES, exc,
                )
                if attempt < self.MAX_RETRIES:
                    time.sleep(1.0)
                else:
                    self._kernel.update_run_status(run.run_id, RunStatus.FAILED)
                    logger.error("Run %s failed after %d attempts", run.run_id, self.MAX_RETRIES)


# 模块级单例
_worker_instance: ScientificCPUWorker | None = None


def get_worker() -> ScientificCPUWorker:
    """获取全局 CPU Worker 单例。"""
    global _worker_instance
    if _worker_instance is None:
        _worker_instance = ScientificCPUWorker()
    return _worker_instance


def start_worker() -> None:
    """启动全局 CPU Worker。"""
    worker = get_worker()
    worker.start()


def stop_worker() -> None:
    """停止全局 CPU Worker。"""
    worker = get_worker()
    worker.stop()