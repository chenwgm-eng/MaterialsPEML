"""run_id 级互斥锁 — 保护 worker 与 API 请求对同一 ECML 运行的并发访问。

决策 12a：run_id 级互斥锁（不同 run_id 互不阻塞，仅锁单个运行）。

用法：
    from .scp_task_locks import ecml_run_lock

    with ecml_run_lock(run_id):
        # 对该 run_id 的 ECML 状态读写

锁实现：进程内 threading.Lock，按 run_id 维度管理。进程重启后锁丢失，
但 ECML 状态持久化在数据库，重启后通过状态恢复机制处理。
"""
from __future__ import annotations

import threading
from contextlib import contextmanager


# 全局锁字典：run_id -> Lock
# 使用全局锁保护字典本身的并发访问
_locks_dict_guard = threading.Lock()
_locks: dict[str, threading.RLock] = {}


@contextmanager
def ecml_run_lock(run_id: str, timeout: float = 30.0):
    """获取指定 run_id 的互斥锁（可重入）。

    Args:
        run_id: ECML 运行 ID
        timeout: 获取锁的超时时间（秒），超时抛出 TimeoutError

    Raises:
        TimeoutError: 在 timeout 秒内未获取到锁
    """
    if not run_id:
        # 空 run_id 不加锁（兼容无 run_id 的场景，如单元测试）
        yield
        return

    with _locks_dict_guard:
        lock = _locks.get(run_id)
        if lock is None:
            lock = threading.RLock()
            _locks[run_id] = lock

    acquired = lock.acquire(timeout=timeout)
    if not acquired:
        raise TimeoutError(
            f"Failed to acquire ECML run lock for {run_id} within {timeout}s "
            f"(another operation is holding the lock)"
        )
    try:
        yield
    finally:
        lock.release()


def cleanup_lock(run_id: str) -> None:
    """清理已完成的 run_id 锁（防止字典无限增长）。

    仅在没有线程持有锁时清理。
    """
    if not run_id:
        return
    with _locks_dict_guard:
        lock = _locks.get(run_id)
        if lock is None:
            return
        # RLock 无法非阻塞 acquire 时表示有持有者，跳过清理
        if lock.acquire(blocking=False):
            _locks.pop(run_id, None)
            lock.release()
