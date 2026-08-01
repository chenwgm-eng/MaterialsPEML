"""LLM Token 用量追踪器 —— 将 token 消耗回写到预算系统。"""
import threading
from collections import defaultdict
from typing import Callable

_lock = threading.Lock()
_usage_store: dict[str, list[dict]] = defaultdict(list)  # project_id -> [{tokens, model, timestamp}]

# 评测修复 P1-019：用量下沉钩子，由 api.py 启动时注入（写预算台账）。
# sink(project_id, total_tokens)；异常由 record_token_usage 内部吞掉，避免影响 LLM 主流程。
_usage_sink: Callable[[str, int], None] | None = None


def set_usage_sink(sink: Callable[[str, int], None] | None) -> None:
    """注册用量下沉钩子（None 表示注销）。"""
    global _usage_sink
    _usage_sink = sink


def record_token_usage(project_id: str, model: str, prompt_tokens: int, completion_tokens: int, total_tokens: int):
    """记录一次 LLM 调用的 token 用量。"""
    if total_tokens <= 0:
        return
    import time
    with _lock:
        _usage_store[project_id].append({
            "model": model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "timestamp": time.time(),
        })
        # 只保留最近 1000 条
        if len(_usage_store[project_id]) > 1000:
            _usage_store[project_id] = _usage_store[project_id][-1000:]
    # P1-019：同步下沉到预算系统（在锁外执行，避免 sink 阻塞/死锁）
    sink = _usage_sink
    if sink is not None:
        try:
            sink(project_id, total_tokens)
        except Exception:
            pass


def get_token_usage(project_id: str = "") -> dict:
    """获取 token 用量统计。"""
    with _lock:
        if project_id and project_id in _usage_store:
            records = _usage_store[project_id]
        else:
            records = []
            for v in _usage_store.values():
                records.extend(v)
        total = sum(r["total_tokens"] for r in records)
        by_model = defaultdict(int)
        for r in records:
            by_model[r["model"]] += r["total_tokens"]
        return {
            "total_tokens": total,
            "call_count": len(records),
            "by_model": dict(by_model),
            "estimated_cost_cny": total * 0.0001,  # 粗略估算：每 token 约 0.0001 元
        }


def reset_token_usage(project_id: str = ""):
    """重置 token 用量统计。"""
    with _lock:
        if project_id:
            _usage_store.pop(project_id, None)
        else:
            _usage_store.clear()
