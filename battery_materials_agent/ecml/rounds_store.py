"""ECML Round 级记录持久化（ecml.ecml_rounds）。

让"迭代"成为可追溯实体：每轮的训练池快照、模型/采集元数据、推荐结果、
实测回填、状态流转都独立落库，供趋势曲线与复核确认使用。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text

from ..db import get_engine


class RoundStore:
    def __init__(self, engine=None):
        self.engine = engine or get_engine()

    def create_round(
        self,
        run_id: str,
        round_no: int,
        target: str,
        target_property: str,
        material_family: str,
        status: str = "pending_review",
        train_pool_snapshot: dict | None = None,
        model_meta: dict | None = None,
        acquisition_meta: dict | None = None,
        recommended: list | None = None,
        model_metrics: dict | None = None,
    ) -> str:
        import uuid

        round_id = uuid.uuid4().hex[:12]
        now = datetime.now(timezone.utc).isoformat()
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """INSERT INTO ecml.ecml_rounds
                    (round_id, run_id, round_no, status, target, target_property,
                     material_family, train_pool_snapshot, model_meta, acquisition_meta,
                     recommended, model_metrics, created_at, updated_at)
                    VALUES (:round_id, :run_id, :round_no, :status, :target, :target_property,
                            :material_family, :pool, :model, :acq,
                            :recommended, :metrics, :now, :now)
                    """
                ),
                {
                    "round_id": round_id,
                    "run_id": run_id,
                    "round_no": round_no,
                    "status": status,
                    "target": target,
                    "target_property": target_property,
                    "material_family": material_family,
                    "pool": _json(train_pool_snapshot),
                    "model": _json(model_meta),
                    "acq": _json(acquisition_meta),
                    "recommended": _json_list(recommended),
                    "metrics": _json(model_metrics),
                    "now": now,
                },
            )
        return round_id

    def update_status(
        self,
        round_id: str,
        status: str,
        review_actions: dict | None = None,
        actual_results: list | None = None,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """UPDATE ecml.ecml_rounds SET status=:status, updated_at=:now,
                       review_actions=COALESCE(:review_actions, review_actions),
                       actual_results=COALESCE(:actual_results, actual_results)
                       WHERE round_id=:round_id"""
                ),
                {
                    "round_id": round_id,
                    "status": status,
                    "review_actions": _json(review_actions) if review_actions is not None else None,
                    "actual_results": _json_list(actual_results) if actual_results is not None else None,
                    "now": now,
                },
            )

    def list_rounds(self, run_id: str) -> list[dict[str, Any]]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                text(
                    """SELECT round_id, run_id, round_no, status, target, target_property,
                              material_family, created_at, updated_at
                       FROM ecml.ecml_rounds WHERE run_id=:run_id
                       ORDER BY round_no ASC"""
                ),
                {"run_id": run_id},
            ).mappings().all()
        return [dict(r) for r in rows]

    def get_round(self, round_id: str) -> dict[str, Any] | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                text(
                    """SELECT round_id, run_id, round_no, status, target, target_property,
                              material_family, train_pool_snapshot, model_meta, acquisition_meta,
                              recommended, model_metrics, review_actions, actual_results,
                              created_at, updated_at
                       FROM ecml.ecml_rounds WHERE round_id=:round_id"""
                ),
                {"round_id": round_id},
            ).mappings().first()
        if row is None:
            return None
        d = dict(row)
        for k in ("train_pool_snapshot", "model_meta", "acquisition_meta", "model_metrics", "review_actions"):
            d[k] = _load(d[k])
        d["recommended"] = _load_list(d.get("recommended"))
        d["actual_results"] = _load_list(d.get("actual_results"))
        return d


def _json(obj: dict | None) -> str | None:
    return json.dumps(obj, ensure_ascii=False) if obj is not None else None


def _json_list(obj: list | None) -> str | None:
    return json.dumps(obj, ensure_ascii=False) if obj is not None else None


def _load(raw) -> Any:
    if raw is None:
        return None
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except Exception:
            return raw
    return raw


def _load_list(raw) -> list:
    v = _load(raw)
    return v if isinstance(v, list) else []