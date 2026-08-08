"""Equipment ledger storage for lab equipment management."""

from __future__ import annotations
from pydantic import BaseModel, field_validator
from enum import Enum
from sqlalchemy import text
import logging

from ..db import get_engine
from ..mdm.reference_dict import ReferenceDictStore

logger = logging.getLogger(__name__)


class EquipmentStatus(str, Enum):
    IDLE = "idle"
    IN_USE = "in_use"
    MAINTENANCE = "maintenance"
    CALIBRATION = "calibration"
    RETIRED = "retired"


class Equipment(BaseModel):
    equipment_id: str = ""
    name: str = ""
    model: str = ""
    category: str = ""
    serial_number: str = ""
    location: str = ""
    status: EquipmentStatus = EquipmentStatus.IDLE
    last_calibration: str = ""
    next_calibration: str = ""
    responsible_person: str = ""
    purchase_date: str = ""
    notes: str = ""

    @field_validator('equipment_id', 'name', 'model', 'category', 'serial_number',
                     'location', 'last_calibration', 'next_calibration',
                     'responsible_person', 'purchase_date', 'notes', mode='before')
    @classmethod
    def _coerce_none_to_empty(cls, v):
        return "" if v is None else v


class EquipmentStore:
    """PostgreSQL-backed persistent storage for equipment ledger."""

    def __init__(self, db_path: str = "data/equipment.db"):
        # db_path 保留用于兼容旧调用方，实际连接由 get_engine() 提供
        self.engine = get_engine()
        self._mdm = ReferenceDictStore()
        self._init_db()

    def _init_db(self):
        # 表已由 alembic 迁移创建，这里仅保留 IF NOT EXISTS 兜底
        with self.engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS experiment.equipment (
                    equipment_id TEXT PRIMARY KEY,
                    name TEXT,
                    model TEXT,
                    category TEXT,
                    serial_number TEXT,
                    location TEXT,
                    status TEXT,
                    last_calibration TEXT,
                    next_calibration TEXT,
                    responsible_person TEXT,
                    purchase_date TEXT,
                    notes TEXT
                )
            """))

    def _validate_status(self, status: str):
        if self._mdm.get_status_code("equipment", status) is None:
            raise ValueError(f"Invalid equipment status: {status}")

    def _validate_category(self, category: str) -> None:
        """校验设备分类是否在 MDM classifications 中存在。空值允许。"""
        if not category:
            return
        if self._mdm.get_classification(category) is None:
            raise ValueError(
                f"设备分类 '{category}' 不存在于主数据分类表中，请先在 MDM 中创建"
            )

    def save(self, equipment: Equipment):
        self._validate_status(equipment.status.value)
        self._validate_category(equipment.category)
        with self.engine.begin() as conn:
            conn.execute(
                text("""INSERT INTO experiment.equipment
                (equipment_id, name, model, category, serial_number, location,
                 status, last_calibration, next_calibration, responsible_person,
                 purchase_date, notes)
                VALUES (:equipment_id, :name, :model, :category, :serial_number, :location,
                 :status, :last_calibration, :next_calibration, :responsible_person,
                 :purchase_date, :notes)
                ON CONFLICT (equipment_id) DO UPDATE SET
                    name = EXCLUDED.name,
                    model = EXCLUDED.model,
                    category = EXCLUDED.category,
                    serial_number = EXCLUDED.serial_number,
                    location = EXCLUDED.location,
                    status = EXCLUDED.status,
                    last_calibration = EXCLUDED.last_calibration,
                    next_calibration = EXCLUDED.next_calibration,
                    responsible_person = EXCLUDED.responsible_person,
                    purchase_date = EXCLUDED.purchase_date,
                    notes = EXCLUDED.notes
                """),
                {
                    "equipment_id": equipment.equipment_id,
                    "name": equipment.name,
                    "model": equipment.model,
                    "category": equipment.category,
                    "serial_number": equipment.serial_number,
                    "location": equipment.location,
                    "status": equipment.status.value,
                    "last_calibration": equipment.last_calibration,
                    "next_calibration": equipment.next_calibration,
                    "responsible_person": equipment.responsible_person,
                    "purchase_date": equipment.purchase_date,
                    "notes": equipment.notes,
                },
            )

    def get(self, equipment_id: str) -> Equipment | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM experiment.equipment WHERE equipment_id = :equipment_id"),
                {"equipment_id": equipment_id},
            ).fetchone()
        if row is None:
            return None
        return self._row_to_equipment(row)

    def find_by_serial(self, serial_number: str, exclude_id: str = "") -> Equipment | None:
        """按序列号查找设备（用于唯一性校验），可排除指定设备。"""
        if not serial_number:
            return None
        with self.engine.connect() as conn:
            if exclude_id:
                row = conn.execute(
                    text(
                        "SELECT * FROM experiment.equipment "
                        "WHERE serial_number = :serial_number AND equipment_id != :exclude_id "
                        "ORDER BY equipment_id ASC LIMIT 1"
                    ),
                    {"serial_number": serial_number, "exclude_id": exclude_id},
                ).fetchone()
            else:
                row = conn.execute(
                    text(
                        "SELECT * FROM experiment.equipment "
                        "WHERE serial_number = :serial_number ORDER BY equipment_id ASC LIMIT 1"
                    ),
                    {"serial_number": serial_number},
                ).fetchone()
        if row is None:
            return None
        return self._row_to_equipment(row)

    def list_all(self, category: str = "", status: str = "") -> list[Equipment]:
        with self.engine.connect() as conn:
            query = "SELECT * FROM experiment.equipment"
            conditions = []
            params: dict[str, str] = {}
            if category:
                conditions.append("category = :category")
                params["category"] = category
            if status:
                conditions.append("status = :status")
                params["status"] = status
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            query += " ORDER BY equipment_id ASC"
            rows = conn.execute(text(query), params).fetchall()
        return [self._row_to_equipment(r) for r in rows]

    def update_status(self, equipment_id: str, status: str, notes: str = ""):
        self._validate_status(status)
        with self.engine.begin() as conn:
            if notes:
                conn.execute(
                    text("UPDATE experiment.equipment SET status = :status, notes = :notes "
                         "WHERE equipment_id = :equipment_id"),
                    {"status": status, "notes": notes, "equipment_id": equipment_id},
                )
            else:
                conn.execute(
                    text("UPDATE experiment.equipment SET status = :status "
                         "WHERE equipment_id = :equipment_id"),
                    {"status": status, "equipment_id": equipment_id},
                )

    def _row_to_equipment(self, row) -> Equipment:
        return Equipment(
            equipment_id=row[0] or "",
            name=row[1] or "",
            model=row[2] or "",
            category=row[3] or "",
            serial_number=row[4] or "",
            location=row[5] or "",
            status=EquipmentStatus(row[6]) if row[6] else EquipmentStatus.IDLE,
            last_calibration=row[7] or "",
            next_calibration=row[8] or "",
            responsible_person=row[9] or "",
            purchase_date=row[10] or "",
            notes=row[11] or "",
        )
