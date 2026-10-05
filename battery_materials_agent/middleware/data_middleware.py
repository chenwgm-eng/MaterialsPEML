"""Wet data middleware - unified data ingestion from LIMS, ELN, and instrument software.

改造说明（Task 9.11）：
- 已切换为 SQLAlchemy Engine（`battery_materials_agent.db.get_engine`）。
- `ingest_record` 写入入口废弃：转发到 `ExperimentDataStore.save_result_record`，
  统一写入 `experiment.experiment_result_records`，消除双源存储问题。
- `query_records` 作为兼容只读接口，内部转查 `experiment.experiment_result_records`。
- `middleware.experiment_records` 表仅作历史数据兼容只读；不再写入。
- 移除原 _init_db 中的 ALTER TABLE ... RENAME TO 临时表迁移（由 alembic 管理）。
"""

from __future__ import annotations
from pydantic import BaseModel, Field
from datetime import datetime, timezone
from typing import Any
import json
import logging
import warnings

from sqlalchemy import text

from ..db import get_engine

logger = logging.getLogger(__name__)


def _iso(v) -> str:
    """TIMESTAMPTZ 列由 psycopg3 返回 datetime 对象，需转为 ISO 字符串以匹配 Pydantic 模型。"""
    if v is None:
        return ""
    if isinstance(v, datetime):
        return v.isoformat()
    return str(v)


class ExperimentRecord(BaseModel):
    record_id: str = ""
    sample_id: str = ""
    formula: str = ""
    experiment_type: str = ""
    conditions: dict[str, Any] = Field(default_factory=dict)
    measured_values: dict[str, float] = Field(default_factory=dict)
    units: dict[str, str] = Field(default_factory=dict)
    error_ranges: dict[str, float] = Field(default_factory=dict)
    source: str = ""
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    batch_id: str = ""
    operator: str = ""
    notes: str = ""
    order_id: str = ""      # 关联实验任务单（ experiment_orders.order_id ）
    candidate_id: str = ""  # 关联候选材料标识
    # ADR-0002：数据可信度与溯源必须随记录透出（verified/simulated/estimated/literature）
    data_quality: str = ""
    provenance: list[dict] | dict | None = None  # 新写入为 list[dict]，0059 历史回填为 dict


def _parse_json_field(value, default):
    """解析 JSON 字段，兼容 psycopg3 自动反序列化或字符串两种来源。"""
    if value is None:
        return default
    if isinstance(value, str):
        if not value:
            return default
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return default
    return value


class DataMiddleware:
    """Unified data middleware for wet experiment data integration.

    写入入口已废弃，统一通过 ExperimentDataStore.save_result_record 写入
    experiment.experiment_result_records；本类仅保留兼容只读查询接口。
    """

    def __init__(self, db_path: str = "data/experiment_data.db"):
        # db_path 保留用于兼容旧调用方，实际连接由 get_engine() 提供
        self.db_path = db_path
        self.engine = get_engine()
        self._subscribers: list[callable] = []

    def _init_db(self):  # pragma: no cover - 保留空方法以兼容旧调用
        """No-op：表结构由 alembic 管理，运行时无需 _init_db。"""
        return

    def ingest_record(self, record: ExperimentRecord) -> str:
        """[DEPRECATED] 写入入口已废弃。

        原实现写入 `middleware.experiment_records` 表，造成双源存储问题。
        现统一转发到 `ExperimentDataStore.save_result_record` 写入
        `experiment.experiment_result_records`。

        Returns:
            record_id: 与 ExperimentDataStore 一致的结果 ID
        """
        warnings.warn(
            "ingest_record is deprecated, use ExperimentDataStore.save_result_record instead",
            DeprecationWarning,
            stacklevel=2,
        )

        # 惰性导入避免循环依赖
        from ..experiment.experiment_controller import (
            ExperimentDataStore,
            ExperimentResultRecord,
        )

        store = ExperimentDataStore()
        if not record.record_id:
            import uuid
            record.record_id = str(uuid.uuid4())[:12]

        # 把兼容 ExperimentRecord 映射为统一 ExperimentResultRecord
        result_record = ExperimentResultRecord(
            result_id=record.record_id,
            experiment_order_id=record.order_id or "",
            sample_id=record.sample_id or "",
            sample_batch_id=record.batch_id or "",
            source_type=record.source or "MANUAL_ENTRY",
            source_system="",
            uploaded_by=record.operator or "",
            uploaded_at=record.timestamp or datetime.now(timezone.utc).isoformat(),
            property_name=record.experiment_type or "",
            value=float(next(iter(record.measured_values.values()), 0.0)),
            unit=next(iter(record.units.values()), "") if record.units else "",
            test_method="",
            test_conditions=record.conditions or {},
            instrument_id="",
            raw_file_uri="",
            qc_status="PENDING",
            qc_issues=[],
            reviewed_by="",
            reviewed_at=None,
            learning_eligible=False,
            scenario_id="",
        )
        store.save_result_record(result_record)

        for subscriber in self._subscribers:
            try:
                subscriber(record)
            except Exception as e:
                logger.warning(f"Subscriber callback failed: {e}")

        return record.record_id

    def query_records(
        self,
        formula: str | None = None,
        experiment_type: str | None = None,
        sample_id: str | None = None,
        batch_id: str | None = None,
        limit: int = 100,
    ) -> list[ExperimentRecord]:
        """兼容只读查询接口：转查 experiment.experiment_result_records。

        说明：experiment_result_records 表的 property_name 与 experiment_type 大致对应，
        sample_batch_id 与 batch_id 对应，统一映射回 ExperimentRecord。
        """
        query = (
            "SELECT result_id, sample_id, sample_batch_id, source_type, uploaded_by, "
            "uploaded_at, property_name, value, unit, test_conditions, "
                "experiment_order_id, instrument_id, data_quality, provenance "
                "FROM experiment.experiment_result_records WHERE 1=1"
        )
        params: dict[str, Any] = {}
        # experiment_result_records 无 formula 列；通过 sample_id / property_name 过滤
        if sample_id:
            query += " AND sample_id = :sample_id"
            params["sample_id"] = sample_id
        if experiment_type:
            query += " AND property_name = :property_name"
            params["property_name"] = experiment_type
        if batch_id:
            query += " AND sample_batch_id = :sample_batch_id"
            params["sample_batch_id"] = batch_id
        query += " ORDER BY uploaded_at DESC NULLS LAST LIMIT :limit"
        params["limit"] = limit

        with self.engine.connect() as conn:
            rows = conn.execute(text(query), params).fetchall()

        records: list[ExperimentRecord] = []
        for r in rows:
            conditions = _parse_json_field(r[9], default={}) or {}
            records.append(ExperimentRecord(
                record_id=r[0] or "",
                sample_id=r[1] or "",
                formula="",
                experiment_type=r[6] or "",
                conditions=conditions,
                measured_values={r[6] or "value": float(r[7] or 0.0)} if r[7] is not None else {},
                units={r[6] or "value": r[8] or ""} if r[8] else {},
                source=r[3] or "",
                timestamp=_iso(r[5]),
                batch_id=r[2] or "",
                operator=r[4] or "",
                order_id=r[10] or "",
                candidate_id="",
                data_quality=r[12] or "",
                provenance=_parse_json_field(r[13], default=None),
            ))
        return records

    def update_record(self, record_id: str, updates: dict) -> bool:
        """[DEPRECATED] 更新 experiment_records 的入口已废弃。

        统一通过 ExperimentDataStore 更新 experiment.experiment_result_records。
        """
        warnings.warn(
            "update_record is deprecated, use ExperimentDataStore instead",
            DeprecationWarning,
            stacklevel=2,
        )
        # 兼容：直接在 experiment.experiment_result_records 上更新可映射字段
        set_clauses = []
        params: dict[str, Any] = {"record_id": record_id}
        # 字段映射：兼容 ExperimentRecord -> experiment_result_records
        if "sample_id" in updates:
            set_clauses.append("sample_id = :sample_id")
            params["sample_id"] = updates["sample_id"]
        if "batch_id" in updates:
            set_clauses.append("sample_batch_id = :sample_batch_id")
            params["sample_batch_id"] = updates["batch_id"]
        if "operator" in updates:
            set_clauses.append("uploaded_by = :uploaded_by")
            params["uploaded_by"] = updates["operator"]
        if "source" in updates:
            set_clauses.append("source_type = :source_type")
            params["source_type"] = updates["source"]
        if "experiment_type" in updates:
            set_clauses.append("property_name = :property_name")
            params["property_name"] = updates["experiment_type"]
        if "order_id" in updates:
            set_clauses.append("experiment_order_id = :experiment_order_id")
            params["experiment_order_id"] = updates["order_id"]
        if not set_clauses:
            return False
        with self.engine.begin() as conn:
            result = conn.execute(
                text(
                    f"UPDATE experiment.experiment_result_records "
                    f"SET {', '.join(set_clauses)} WHERE result_id = :record_id"
                ),
                params,
            )
        return result.rowcount > 0

    def delete_record(self, record_id: str) -> bool:
        """[DEPRECATED] 删除入口已废弃；为兼容直接删除 experiment.experiment_result_records。"""
        warnings.warn(
            "delete_record is deprecated, use ExperimentDataStore instead",
            DeprecationWarning,
            stacklevel=2,
        )
        with self.engine.begin() as conn:
            result = conn.execute(
                text("DELETE FROM experiment.experiment_result_records WHERE result_id = :record_id"),
                {"record_id": record_id},
            )
        return result.rowcount > 0

    def subscribe(self, callback: callable):
        self._subscribers.append(callback)

    def unsubscribe(self, callback: callable):
        self._subscribers = [s for s in self._subscribers if s is not callback]

    def get_latest_for_formula(self, formula: str, experiment_type: str) -> ExperimentRecord | None:
        # experiment_result_records 无 formula 列；改按 experiment_type 查
        records = self.query_records(experiment_type=experiment_type, limit=1)
        return records[0] if records else None

    def export_to_parquet(self, output_path: str, formula: str | None = None):
        try:
            import pandas as pd
        except ImportError:
            raise ImportError(
                "pandas is required for parquet export. Install with: pip install pandas pyarrow"
            )
        records = self.query_records(formula=formula, limit=10000)
        if not records:
            return
        data = [r.model_dump() for r in records]
        df = pd.DataFrame(data)
        df.to_parquet(output_path, index=False)

    def get_statistics(self, formula: str, experiment_type: str) -> dict:
        records = self.query_records(experiment_type=experiment_type)
        if not records:
            return {"count": 0}

        all_values = {}
        for r in records:
            for k, v in r.measured_values.items():
                if k not in all_values:
                    all_values[k] = []
                all_values[k].append(v)

        import numpy as np
        stats = {"count": len(records)}
        for k, values in all_values.items():
            arr = np.array(values)
            stats[k] = {
                "mean": float(np.mean(arr)),
                "std": float(np.std(arr)),
                "min": float(np.min(arr)),
                "max": float(np.max(arr)),
            }
        return stats
