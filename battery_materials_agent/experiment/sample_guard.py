"""样品存在性守护：写入实验结果前确保样品记录已存在（fk_results_sample）。

从 api.py 抽出（T12 模块拆分），通过注册式依赖注入替代对 api.py 的反向 import。
"""
from __future__ import annotations

import logging
from typing import Callable

logger = logging.getLogger(__name__)

from .sample_store import Sample

_sample_store_getter: Callable[[], object | None] | None = None
_order_lookup: Callable[[str], object | None] | None = None


def register_sample_store_getter(fn: Callable[[], object | None]) -> None:
    global _sample_store_getter
    _sample_store_getter = fn


def register_order_lookup(fn: Callable[[str], object | None]) -> None:
    global _order_lookup
    _order_lookup = fn


def ensure_sample_for_result(sample_id: str, source_type: str = "experiment",
                             order_id: str = "", candidate_id: str = "") -> None:
    """写入实验结果时联动创建样品记录，打通 samples.db 与 experiments.db。"""
    if not sample_id:
        return
    sample_store = _sample_store_getter() if _sample_store_getter else None
    if sample_store is None:
        return
    try:
        if sample_store.get(sample_id) is not None:
            return
        if not candidate_id and order_id and _order_lookup is not None:
            try:
                order = _order_lookup(order_id)
                if order is not None:
                    candidate_id = getattr(order, "candidate_id", "") or ""
            except Exception:
                pass
        sample_store.save(Sample(
            sample_id=sample_id,
            name=sample_id,
            source_type=source_type,
            source_order_id=order_id,
            source_candidate_id=candidate_id,
        ))
    except Exception as e:
        logger.debug("联动创建样品失败 sample_id=%s: %s", sample_id, e)
