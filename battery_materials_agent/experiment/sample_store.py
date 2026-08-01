"""Sample management store for tracking samples through the lab workflow."""

from __future__ import annotations
from pydantic import BaseModel, Field
from enum import Enum
from datetime import datetime, timezone
from sqlalchemy import text
import uuid
import logging

from ..db import get_engine

logger = logging.getLogger(__name__)


def _iso(v) -> str:
    """TIMESTAMPTZ 列由 psycopg3 返回 datetime 对象，需转为 ISO 字符串以匹配 Pydantic 模型。"""
    if v is None:
        return ""
    if isinstance(v, datetime):
        return v.isoformat()
    return str(v)


class SampleStatus(str, Enum):
    CREATED = "created"
    IN_STORAGE = "in_storage"
    IN_USE = "in_use"
    CONSUMED = "consumed"
    DISCARDED = "discarded"
    PROPOSED = "proposed"  # Task 14.5：配方发布后自动创建的样品提案状态


class Sample(BaseModel):
    sample_id: str = ""
    name: str = ""
    source_type: str = ""  # synthesis / purchase / candidate
    source_order_id: str = ""  # 关联实验任务
    source_candidate_id: str = ""  # 关联候选材料
    batch_number: str = ""
    quantity: float = 0.0
    unit: str = "g"
    status: SampleStatus = SampleStatus.CREATED
    storage_location: str = ""
    storage_condition: str = ""  # 常温/冷藏/冷冻/惰性气氛
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    notes: str = ""
    sample_code: str = ""  # 业务编号（客户自定义，唯一）
    chemical_formula: str = ""  # 化学式，如 Li6PS5Cl
    scenario_id: str = ""  # P0-001：关联研发场景 ID
    test_task_id: str = ""  # 业务链路：关联 experiment.test_tasks(test_task_id)


class SampleTransfer(BaseModel):
    transfer_id: str = ""
    sample_id: str = ""
    from_status: str = ""
    to_status: str = ""
    from_location: str = ""
    to_location: str = ""
    transferred_by: str = ""
    transferred_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    notes: str = ""


class SampleStore:
    """PostgreSQL-backed persistent storage for samples and transfer records."""

    def __init__(self, db_path: str = "data/samples.db"):
        # db_path 保留用于兼容旧调用方，实际连接由 get_engine() 提供
        self.engine = get_engine()
        self._init_db()

    def _init_db(self):
        # 表已由 alembic 迁移创建，这里仅保留 IF NOT EXISTS 兜底
        with self.engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS experiment.samples (
                    sample_id TEXT PRIMARY KEY,
                    name TEXT,
                    source_type TEXT,
                    source_order_id TEXT,
                    source_candidate_id TEXT,
                    batch_number TEXT,
                    quantity DOUBLE PRECISION,
                    unit TEXT,
                    status TEXT,
                    storage_location TEXT,
                    storage_condition TEXT,
                    created_at TIMESTAMPTZ,
                    updated_at TIMESTAMPTZ,
                    notes TEXT,
                    sample_code TEXT,
                    chemical_formula TEXT,
                    scenario_id TEXT,
                    test_task_id TEXT
                )
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS experiment.sample_transfers (
                    transfer_id TEXT PRIMARY KEY,
                    sample_id TEXT,
                    from_status TEXT,
                    to_status TEXT,
                    from_location TEXT,
                    to_location TEXT,
                    transferred_by TEXT,
                    transferred_at TIMESTAMPTZ,
                    notes TEXT
                )
            """))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_samples_test_task_id "
                "ON experiment.samples(test_task_id)"
            ))

    def save(self, sample: Sample) -> Sample:
        # Task 14.3：实验任务 → 样品自动关联
        # 若 source_order_id 存在但 source_candidate_id 缺失，从 order.candidate_id 推导填充
        if sample.source_order_id and not sample.source_candidate_id:
            try:
                with self.engine.connect() as conn:
                    row = conn.execute(
                        text("SELECT candidate_id FROM experiment.experiment_orders "
                             "WHERE order_id = :oid"),
                        {"oid": sample.source_order_id},
                    ).fetchone()
                if row is not None and row[0]:
                    sample.source_candidate_id = row[0]
            except Exception as e:
                logger.debug("自动填充 source_candidate_id 失败: %s", e)

        sample.updated_at = datetime.now(timezone.utc).isoformat()
        # Task 14.1：FK 约束不允许空字符串，需转为 NULL（PostgreSQL FK 仅对 NULL 跳过校验）
        with self.engine.begin() as conn:
            conn.execute(
                text("""INSERT INTO experiment.samples
                (sample_id, name, source_type, source_order_id, source_candidate_id,
                 batch_number, quantity, unit, status, storage_location, storage_condition,
                 created_at, updated_at, notes, sample_code, chemical_formula, scenario_id,
                 test_task_id)
                VALUES (:sample_id, :name, :source_type, :source_order_id, :source_candidate_id,
                 :batch_number, :quantity, :unit, :status, :storage_location, :storage_condition,
                 :created_at, :updated_at, :notes, :sample_code, :chemical_formula, :scenario_id,
                 :test_task_id)
                ON CONFLICT (sample_id) DO UPDATE SET
                    name = EXCLUDED.name,
                    source_type = EXCLUDED.source_type,
                    source_order_id = EXCLUDED.source_order_id,
                    source_candidate_id = EXCLUDED.source_candidate_id,
                    batch_number = EXCLUDED.batch_number,
                    quantity = EXCLUDED.quantity,
                    unit = EXCLUDED.unit,
                    status = EXCLUDED.status,
                    storage_location = EXCLUDED.storage_location,
                    storage_condition = EXCLUDED.storage_condition,
                    updated_at = EXCLUDED.updated_at,
                    notes = EXCLUDED.notes,
                    sample_code = EXCLUDED.sample_code,
                    chemical_formula = EXCLUDED.chemical_formula,
                    scenario_id = EXCLUDED.scenario_id,
                    test_task_id = EXCLUDED.test_task_id
                """),
                {
                    "sample_id": sample.sample_id,
                    "name": sample.name,
                    "source_type": sample.source_type,
                    "source_order_id": sample.source_order_id or None,
                    "source_candidate_id": sample.source_candidate_id or None,
                    "batch_number": sample.batch_number,
                    "quantity": sample.quantity,
                    "unit": sample.unit,
                    "status": sample.status.value,
                    "storage_location": sample.storage_location,
                    "storage_condition": sample.storage_condition,
                    "created_at": sample.created_at,
                    "updated_at": sample.updated_at,
                    "notes": sample.notes,
                    "sample_code": sample.sample_code,
                    "chemical_formula": sample.chemical_formula,
                    "scenario_id": sample.scenario_id,
                    "test_task_id": sample.test_task_id or None,
                },
            )
        return sample

    @staticmethod
    def _row_to_sample(row) -> Sample:
        try:
            status = SampleStatus(row[8]) if row[8] else SampleStatus.CREATED
        except (ValueError, KeyError):
            status = SampleStatus.CREATED
        return Sample(
            sample_id=row[0] or "", name=row[1] or "", source_type=row[2] or "",
            source_order_id=row[3] or "",
            source_candidate_id=row[4] or "",
            batch_number=row[5] or "", quantity=row[6] if row[6] is not None else 0.0,
            unit=row[7] or "g",
            status=status,
            storage_location=row[9] or "",
            storage_condition=row[10] or "",
            created_at=_iso(row[11]), updated_at=_iso(row[12]),
            notes=row[13] or "",
            sample_code=row[14] if len(row) > 14 and row[14] else "",
            chemical_formula=row[15] if len(row) > 15 and row[15] else "",
            scenario_id=row[16] if len(row) > 16 and row[16] else "",
            test_task_id=row[17] if len(row) > 17 and row[17] else "",
        )

    def get(self, sample_id: str) -> Sample | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM experiment.samples WHERE sample_id = :sample_id"),
                {"sample_id": sample_id},
            ).fetchone()
        if row is None:
            return None
        return self._row_to_sample(row)

    def get_by_code(self, sample_code: str) -> Sample | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM experiment.samples "
                     "WHERE sample_code = :sample_code AND sample_code != ''"),
                {"sample_code": sample_code},
            ).fetchone()
        if row is None:
            return None
        return self._row_to_sample(row)

    def list_all(self, test_task_id: str = "") -> list[Sample]:
        """查询样品列表，支持按 test_task_id 过滤。"""
        with self.engine.connect() as conn:
            if test_task_id:
                rows = conn.execute(
                    text("SELECT * FROM experiment.samples "
                         "WHERE test_task_id = :test_task_id "
                         "ORDER BY created_at DESC"),
                    {"test_task_id": test_task_id},
                ).fetchall()
            else:
                rows = conn.execute(
                    text("SELECT * FROM experiment.samples ORDER BY created_at DESC")
                ).fetchall()
        return [self._row_to_sample(r) for r in rows]

    def has_transfers(self, sample_id: str) -> bool:
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT COUNT(*) FROM experiment.sample_transfers WHERE sample_id = :sample_id"),
                {"sample_id": sample_id},
            ).fetchone()
        return bool(row and row[0] > 0)

    def delete(self, sample_id: str) -> bool:
        with self.engine.begin() as conn:
            cur = conn.execute(
                text("DELETE FROM experiment.samples WHERE sample_id = :sample_id"),
                {"sample_id": sample_id},
            )
            return cur.rowcount > 0

    def update_status(self, sample_id: str, status: SampleStatus, notes: str = "") -> bool:
        # T-024：状态迁移加锁。在同一事务内 SELECT ... FOR UPDATE 行锁，
        # 防止并发请求读到相同旧状态后分别更新造成覆盖
        with self.engine.begin() as conn:
            row = conn.execute(
                text("SELECT * FROM experiment.samples WHERE sample_id = :sample_id FOR UPDATE"),
                {"sample_id": sample_id},
            ).fetchone()
            if row is None:
                return False
            sample = self._row_to_sample(row)
            sample.status = status
            if notes:
                sample.notes = notes
            sample.updated_at = datetime.now(timezone.utc).isoformat()
            conn.execute(
                text("""UPDATE experiment.samples SET
                    status = :status,
                    notes = :notes,
                    updated_at = :updated_at
                    WHERE sample_id = :sample_id"""),
                {
                    "status": sample.status.value,
                    "notes": sample.notes,
                    "updated_at": sample.updated_at,
                    "sample_id": sample.sample_id,
                },
            )
        return True

    def transfer(self, sample_id: str, to_status: SampleStatus, to_location: str = "",
                 transferred_by: str = "", notes: str = "") -> SampleTransfer | None:
        # MDM 状态迁移校验：从主数据治理表查询是否允许该迁移
        from ..mdm.master_data import MasterDataStore
        mdm = MasterDataStore()
        # T-024：状态迁移加锁。在同一事务内 SELECT ... FOR UPDATE 行锁，
        # 确保读取-校验-写入原子化，避免并发迁移覆盖
        with self.engine.begin() as conn:
            row = conn.execute(
                text("SELECT * FROM experiment.samples WHERE sample_id = :sample_id FOR UPDATE"),
                {"sample_id": sample_id},
            ).fetchone()
            if row is None:
                return None
            sample = self._row_to_sample(row)
            from_status = sample.status.value
            to_status_code = to_status.value
            if not mdm.is_transition_allowed(from_status, to_status_code):
                logger.warning("样品状态迁移被 MDM 拒绝: %s → %s (sample_id=%s)",
                               from_status, to_status_code, sample_id)
                return None
            transfer = SampleTransfer(
                transfer_id=f"TRF_{uuid.uuid4().hex[:8]}",
                sample_id=sample_id,
                from_status=sample.status.value,
                to_status=to_status.value,
                from_location=sample.storage_location,
                to_location=to_location or sample.storage_location,
                transferred_by=transferred_by,
                notes=notes,
            )
            # 记录流转
            conn.execute(
                text("""INSERT INTO experiment.sample_transfers
                (transfer_id, sample_id, from_status, to_status, from_location, to_location,
                 transferred_by, transferred_at, notes)
                VALUES (:transfer_id, :sample_id, :from_status, :to_status, :from_location,
                 :to_location, :transferred_by, :transferred_at, :notes)
                """),
                {
                    "transfer_id": transfer.transfer_id,
                    "sample_id": transfer.sample_id,
                    "from_status": transfer.from_status,
                    "to_status": transfer.to_status,
                    "from_location": transfer.from_location,
                    "to_location": transfer.to_location,
                    "transferred_by": transfer.transferred_by,
                    "transferred_at": transfer.transferred_at,
                    "notes": transfer.notes,
                },
            )
            # 更新样品状态和位置（同一事务内，避免 save() 独立事务）
            sample.status = to_status
            if to_location:
                sample.storage_location = to_location
            if notes:
                sample.notes = notes
            sample.updated_at = datetime.now(timezone.utc).isoformat()
            conn.execute(
                text("""UPDATE experiment.samples SET
                    status = :status,
                    storage_location = :storage_location,
                    notes = :notes,
                    updated_at = :updated_at
                    WHERE sample_id = :sample_id"""),
                {
                    "status": sample.status.value,
                    "storage_location": sample.storage_location,
                    "notes": sample.notes,
                    "updated_at": sample.updated_at,
                    "sample_id": sample_id,
                },
            )
        return transfer

    def list_transfers(self, sample_id: str) -> list[SampleTransfer]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                text("SELECT * FROM experiment.sample_transfers "
                     "WHERE sample_id = :sample_id ORDER BY transferred_at ASC"),
                {"sample_id": sample_id},
            ).fetchall()
        return [SampleTransfer(
            transfer_id=r[0], sample_id=r[1], from_status=r[2], to_status=r[3],
            from_location=r[4], to_location=r[5], transferred_by=r[6],
            transferred_at=_iso(r[7]), notes=r[8],
        ) for r in rows]
