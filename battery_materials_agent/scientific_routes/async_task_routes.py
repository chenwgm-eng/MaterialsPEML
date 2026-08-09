"""全局后台异步任务查询 API。

供前端右下角浮动指示器轮询展示当前进程内所有后台异步任务
（运行中 + 最近完成），让用户直观看到有多少计算任务在后台运行。
"""
from __future__ import annotations

from fastapi import APIRouter

from ..tasks import async_tasks

router = APIRouter(prefix="/v1/async-tasks", tags=["async-tasks"])


@router.get("")
def get_async_tasks() -> dict:
    """返回当前进程内后台异步任务（运行中 + 最近完成）。"""
    return {
        "active_count": async_tasks.active_count(),
        "tasks": async_tasks.list_tasks(),
    }