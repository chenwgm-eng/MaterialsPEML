"""进程内后台异步任务注册表（线程安全）。

用于跟踪通过后台线程/进程运行的耗时计算任务（如 TS 搜索），
供前端右下角浮动指示器轮询展示「当前有多少后台任务在运行、具体是哪些」。

设计说明：
- 内存存储，进程重启即清空（符合轻量后台任务跟踪，不落库）；
- 全程加锁，线程安全，可被多个后台线程并发登记/更新；
- 仅保留最近 N 条已完成任务，避免无限增长。
"""
from __future__ import annotations

import threading
import time
import uuid

_lock = threading.Lock()
_tasks: dict[str, dict] = {}
_MAX_RECENT_DONE = 50


def register(name: str, type: str = "computation", detail: str = "") -> str:
    """登记一个运行中的后台任务，返回任务 id。"""
    task_id = uuid.uuid4().hex[:12]
    with _lock:
        _tasks[task_id] = {
            "id": task_id,
            "name": name,
            "type": type,
            "status": "running",
            "progress": 0,
            "detail": detail,
            "started_at": round(time.time(), 3),
            "completed_at": None,
        }
    return task_id


def update(task_id: str, **fields) -> None:
    """更新任务字段；置为 completed/failed 时自动记录完成时间。"""
    with _lock:
        task = _tasks.get(task_id)
        if not task:
            return
        for key, value in fields.items():
            if key in ("id", "started_at"):
                continue
            task[key] = value
        if fields.get("status") in ("completed", "failed"):
            task["completed_at"] = round(time.time(), 3)


def active_count() -> int:
    """当前运行中的后台任务数。"""
    with _lock:
        return sum(1 for t in _tasks.values() if t["status"] == "running")


def list_tasks() -> list[dict]:
    """返回全部任务（运行中 + 最近完成），按开始时间倒序。"""
    with _lock:
        items = list(_tasks.values())
        # 清理超过上限的已完成任务
        done = [t for t in items if t["status"] != "running"]
        if len(done) > _MAX_RECENT_DONE:
            overflow = sorted(done, key=lambda t: t["started_at"], reverse=True)[_MAX_RECENT_DONE:]
            for t in overflow:
                _tasks.pop(t["id"], None)
        items = list(_tasks.values())
    items.sort(key=lambda t: t["started_at"], reverse=True)
    return items


__all__ = ["register", "update", "active_count", "list_tasks"]