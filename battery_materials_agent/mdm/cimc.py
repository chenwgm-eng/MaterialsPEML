"""P3 CIMC（特性-指标-方法-能力）Store。

承载 5 张主数据表的 CRUD：
- mdm.properties 特性
- mdm.test_items 指标项目
- mdm.test_methods 检测方法
- mdm.specifications 规格与判定
- mdm.inspection_capabilities 检查能力

关系：property 1→N test_items N→1 test_method 1→N inspection_capabilities。
"""
from __future__ import annotations
from pydantic import BaseModel, field_validator
from datetime import datetime
from typing import Any
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from ..db import get_engine


def _iso(value) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


# ──────────────────────────────────────────────────────────────────────────────
# 模型
# ──────────────────────────────────────────────────────────────────────────────
class Property(BaseModel):
    """特性主数据。"""
    property_id: str = ""
    name: str = ""
    property_type: str = ""
    default_unit: str = ""
    description: str = ""
    sort_order: int = 0
    is_active: bool = True
    created_at: str = ""
    updated_at: str = ""

    @field_validator("default_unit", mode="before")
    @classmethod
    def _coerce_none(cls, v):
        return "" if v is None else v


class TestMethod(BaseModel):
    """检测方法主数据。"""
    method_id: str = ""
    name: str = ""
    standard_code: str = ""
    sop_version: str = ""
    preparation_req: str = ""
    calculation_formula: str = ""
    description: str = ""
    is_active: bool = True
    created_at: str = ""
    updated_at: str = ""

    @field_validator("standard_code", mode="before")
    @classmethod
    def _coerce_none(cls, v):
        return "" if v is None else v


class TestItem(BaseModel):
    """指标项目。"""
    item_id: str = ""
    property_id: str = ""
    name: str = ""
    test_method_id: str = ""
    condition_text: str = ""
    default_unit: str = ""
    sort_order: int = 0
    is_active: bool = True
    created_at: str = ""
    updated_at: str = ""

    @field_validator("test_method_id", "default_unit", mode="before")
    @classmethod
    def _coerce_none(cls, v):
        return "" if v is None else v


class Specification(BaseModel):
    """规格与判定。"""
    spec_id: str = ""
    item_id: str = ""
    target_value: float | None = None
    min_value: float | None = None
    max_value: float | None = None
    unit: str = ""
    judgment_logic: str = ""
    description: str = ""
    is_active: bool = True
    created_at: str = ""
    updated_at: str = ""

    @field_validator("unit", mode="before")
    @classmethod
    def _coerce_none(cls, v):
        return "" if v is None else v


class InspectionCapability(BaseModel):
    """检查能力。"""
    capability_id: str = ""
    name: str = ""
    method_id: str = ""
    location_id: str = ""
    template_code: str = ""
    range_min: float | None = None
    range_max: float | None = None
    accuracy: str = ""
    detection_limit: float | None = None
    unit: str = ""
    description: str = ""
    is_active: bool = True
    created_at: str = ""
    updated_at: str = ""

    @field_validator("location_id", "template_code", "unit", mode="before")
    @classmethod
    def _coerce_none(cls, v):
        return "" if v is None else v


# ──────────────────────────────────────────────────────────────────────────────
# Store
# ──────────────────────────────────────────────────────────────────────────────
class CimcStore:
    """P3 CIMC Store。只读查询。"""

    def __init__(self):
        self.engine = get_engine()

    # ── 特性 ──────────────────────────────────────────────
    def list_properties(self, property_type: str = "") -> list[Property]:
        sql = ("SELECT property_id, name, property_type, default_unit, description, "
               "sort_order, is_active, created_at, updated_at FROM mdm.properties WHERE 1=1")
        params: dict[str, Any] = {}
        if property_type:
            sql += " AND property_type = :property_type"
            params["property_type"] = property_type
        sql += " ORDER BY sort_order, property_id"
        with self.engine.connect() as conn:
            rows = conn.execute(text(sql), params).fetchall()
        return [self._row_to_property(r) for r in rows]

    def get_property(self, property_id: str) -> Property | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT property_id, name, property_type, default_unit, description, "
                     "sort_order, is_active, created_at, updated_at FROM mdm.properties "
                     "WHERE property_id = :property_id"),
                {"property_id": property_id},
            ).fetchone()
        return self._row_to_property(row) if row else None

    @staticmethod
    def _row_to_property(r) -> Property:
        return Property(
            property_id=r[0] or "",
            name=r[1] or "",
            property_type=r[2] or "",
            default_unit=r[3] or "",
            description=r[4] or "",
            sort_order=r[5] or 0,
            is_active=bool(r[6]),
            created_at=_iso(r[7]),
            updated_at=_iso(r[8]),
        )

    # ── 检测方法 ──────────────────────────────────────────
    def list_test_methods(self, standard_code: str = "") -> list[TestMethod]:
        sql = ("SELECT method_id, name, standard_code, sop_version, preparation_req, "
               "calculation_formula, description, is_active, created_at, updated_at "
               "FROM mdm.test_methods WHERE 1=1")
        params: dict[str, Any] = {}
        if standard_code:
            sql += " AND standard_code = :standard_code"
            params["standard_code"] = standard_code
        sql += " ORDER BY method_id"
        with self.engine.connect() as conn:
            rows = conn.execute(text(sql), params).fetchall()
        return [self._row_to_test_method(r) for r in rows]

    def get_test_method(self, method_id: str) -> TestMethod | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT method_id, name, standard_code, sop_version, preparation_req, "
                     "calculation_formula, description, is_active, created_at, updated_at "
                     "FROM mdm.test_methods WHERE method_id = :method_id"),
                {"method_id": method_id},
            ).fetchone()
        return self._row_to_test_method(row) if row else None

    @staticmethod
    def _row_to_test_method(r) -> TestMethod:
        return TestMethod(
            method_id=r[0] or "",
            name=r[1] or "",
            standard_code=r[2] or "",
            sop_version=r[3] or "",
            preparation_req=r[4] or "",
            calculation_formula=r[5] or "",
            description=r[6] or "",
            is_active=bool(r[7]),
            created_at=_iso(r[8]),
            updated_at=_iso(r[9]),
        )

    # ── 指标项目 ──────────────────────────────────────────
    def list_test_items(self, property_id: str = "", test_method_id: str = "") -> list[TestItem]:
        sql = ("SELECT item_id, property_id, name, test_method_id, condition_text, "
               "default_unit, sort_order, is_active, created_at, updated_at "
               "FROM mdm.test_items WHERE 1=1")
        params: dict[str, Any] = {}
        if property_id:
            sql += " AND property_id = :property_id"
            params["property_id"] = property_id
        if test_method_id:
            sql += " AND test_method_id = :test_method_id"
            params["test_method_id"] = test_method_id
        sql += " ORDER BY sort_order, item_id"
        with self.engine.connect() as conn:
            rows = conn.execute(text(sql), params).fetchall()
        return [self._row_to_test_item(r) for r in rows]

    def get_test_item(self, item_id: str) -> TestItem | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT item_id, property_id, name, test_method_id, condition_text, "
                     "default_unit, sort_order, is_active, created_at, updated_at "
                     "FROM mdm.test_items WHERE item_id = :item_id"),
                {"item_id": item_id},
            ).fetchone()
        return self._row_to_test_item(row) if row else None

    @staticmethod
    def _row_to_test_item(r) -> TestItem:
        return TestItem(
            item_id=r[0] or "",
            property_id=r[1] or "",
            name=r[2] or "",
            test_method_id=r[3] or "",
            condition_text=r[4] or "",
            default_unit=r[5] or "",
            sort_order=r[6] or 0,
            is_active=bool(r[7]),
            created_at=_iso(r[8]),
            updated_at=_iso(r[9]),
        )

    # ── 规格 ──────────────────────────────────────────────
    def list_specifications(self, item_id: str = "") -> list[Specification]:
        sql = ("SELECT spec_id, item_id, target_value, min_value, max_value, unit, "
               "judgment_logic, description, is_active, created_at, updated_at "
               "FROM mdm.specifications WHERE 1=1")
        params: dict[str, Any] = {}
        if item_id:
            sql += " AND item_id = :item_id"
            params["item_id"] = item_id
        sql += " ORDER BY spec_id"
        with self.engine.connect() as conn:
            rows = conn.execute(text(sql), params).fetchall()
        return [self._row_to_specification(r) for r in rows]

    def get_specification(self, spec_id: str) -> Specification | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT spec_id, item_id, target_value, min_value, max_value, unit, "
                     "judgment_logic, description, is_active, created_at, updated_at "
                     "FROM mdm.specifications WHERE spec_id = :spec_id"),
                {"spec_id": spec_id},
            ).fetchone()
        return self._row_to_specification(row) if row else None

    @staticmethod
    def _row_to_specification(r) -> Specification:
        return Specification(
            spec_id=r[0] or "",
            item_id=r[1] or "",
            target_value=float(r[2]) if r[2] is not None else None,
            min_value=float(r[3]) if r[3] is not None else None,
            max_value=float(r[4]) if r[4] is not None else None,
            unit=r[5] or "",
            judgment_logic=r[6] or "",
            description=r[7] or "",
            is_active=bool(r[8]),
            created_at=_iso(r[9]),
            updated_at=_iso(r[10]),
        )

    # ── 检查能力 ──────────────────────────────────────────
    def list_inspection_capabilities(self, method_id: str = "") -> list[InspectionCapability]:
        sql = ("SELECT capability_id, name, method_id, location_id, template_code, "
               "range_min, range_max, accuracy, detection_limit, unit, description, "
               "is_active, created_at, updated_at FROM mdm.inspection_capabilities WHERE 1=1")
        params: dict[str, Any] = {}
        if method_id:
            sql += " AND method_id = :method_id"
            params["method_id"] = method_id
        sql += " ORDER BY method_id, name"
        with self.engine.connect() as conn:
            rows = conn.execute(text(sql), params).fetchall()
        return [self._row_to_inspection_capability(r) for r in rows]

    def get_inspection_capability(self, capability_id: str) -> InspectionCapability | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT capability_id, name, method_id, location_id, template_code, "
                     "range_min, range_max, accuracy, detection_limit, unit, description, "
                     "is_active, created_at, updated_at FROM mdm.inspection_capabilities "
                     "WHERE capability_id = :capability_id"),
                {"capability_id": capability_id},
            ).fetchone()
        return self._row_to_inspection_capability(row) if row else None

    @staticmethod
    def _row_to_inspection_capability(r) -> InspectionCapability:
        return InspectionCapability(
            capability_id=r[0] or "",
            name=r[1] or "",
            method_id=r[2] or "",
            location_id=r[3] or "",
            template_code=r[4] or "",
            range_min=float(r[5]) if r[5] is not None else None,
            range_max=float(r[6]) if r[6] is not None else None,
            accuracy=r[7] or "",
            detection_limit=float(r[8]) if r[8] is not None else None,
            unit=r[9] or "",
            description=r[10] or "",
            is_active=bool(r[11]),
            created_at=_iso(r[12]),
            updated_at=_iso(r[13]),
        )

    # ── 写入：通用 INSERT 助手 ────────────────────────────
    def _insert_row(self, table: str, cols: list[str], payload: dict[str, Any]) -> None:
        """按允许列过滤 payload 后执行 INSERT。唯一键冲突抛 ValueError。"""
        cols_clean = [c for c in cols if c in payload]
        if not cols_clean:
            raise ValueError("payload 不包含任何可插入列")
        placeholders = {c: payload.get(c) for c in cols_clean}
        col_list = ",".join(cols_clean)
        param_list = ":" + ",:".join(cols_clean)
        sql = f"INSERT INTO {table} ({col_list}) VALUES ({param_list})"
        try:
            with self.engine.begin() as conn:
                conn.execute(text(sql), placeholders)
        except IntegrityError as e:
            raise ValueError(f"唯一键冲突: {e.orig}") from e

    # ── 特性：create / toggle ─────────────────────────────
    def create_property(self, payload: dict[str, Any]) -> Property:
        cols = ["property_id", "name", "property_type", "default_unit", "description",
                "sort_order", "is_active"]
        self._insert_row("mdm.properties", cols, payload)
        return self.get_property(payload["property_id"])

    def set_property_active(self, property_id: str, is_active: bool) -> Property | None:
        with self.engine.begin() as conn:
            result = conn.execute(
                text("UPDATE mdm.properties SET is_active = :is_active, "
                     "updated_at = CURRENT_TIMESTAMP WHERE property_id = :property_id"),
                {"is_active": is_active, "property_id": property_id},
            )
            if result.rowcount == 0:
                return None
        return self.get_property(property_id)

    # ── 检测方法：create / toggle ─────────────────────────
    def create_test_method(self, payload: dict[str, Any]) -> TestMethod:
        cols = ["method_id", "name", "standard_code", "sop_version", "preparation_req",
                "calculation_formula", "description", "is_active"]
        self._insert_row("mdm.test_methods", cols, payload)
        return self.get_test_method(payload["method_id"])

    def set_test_method_active(self, method_id: str, is_active: bool) -> TestMethod | None:
        with self.engine.begin() as conn:
            result = conn.execute(
                text("UPDATE mdm.test_methods SET is_active = :is_active, "
                     "updated_at = CURRENT_TIMESTAMP WHERE method_id = :method_id"),
                {"is_active": is_active, "method_id": method_id},
            )
            if result.rowcount == 0:
                return None
        return self.get_test_method(method_id)

    # ── 指标项目：create / toggle ─────────────────────────
    def create_test_item(self, payload: dict[str, Any]) -> TestItem:
        cols = ["item_id", "property_id", "name", "test_method_id", "condition_text",
                "default_unit", "sort_order", "is_active"]
        self._insert_row("mdm.test_items", cols, payload)
        return self.get_test_item(payload["item_id"])

    def set_test_item_active(self, item_id: str, is_active: bool) -> TestItem | None:
        with self.engine.begin() as conn:
            result = conn.execute(
                text("UPDATE mdm.test_items SET is_active = :is_active, "
                     "updated_at = CURRENT_TIMESTAMP WHERE item_id = :item_id"),
                {"is_active": is_active, "item_id": item_id},
            )
            if result.rowcount == 0:
                return None
        return self.get_test_item(item_id)

    # ── 规格：create / toggle ─────────────────────────────
    def create_specification(self, payload: dict[str, Any]) -> Specification:
        cols = ["spec_id", "item_id", "target_value", "min_value", "max_value", "unit",
                "judgment_logic", "description", "is_active"]
        self._insert_row("mdm.specifications", cols, payload)
        return self.get_specification(payload["spec_id"])

    def set_specification_active(self, spec_id: str, is_active: bool) -> Specification | None:
        with self.engine.begin() as conn:
            result = conn.execute(
                text("UPDATE mdm.specifications SET is_active = :is_active, "
                     "updated_at = CURRENT_TIMESTAMP WHERE spec_id = :spec_id"),
                {"is_active": is_active, "spec_id": spec_id},
            )
            if result.rowcount == 0:
                return None
        return self.get_specification(spec_id)

    # ── 检查能力：create / toggle ─────────────────────────
    def create_inspection_capability(self, payload: dict[str, Any]) -> InspectionCapability:
        cols = ["capability_id", "name", "method_id", "location_id", "template_code",
                "range_min", "range_max", "accuracy", "detection_limit", "unit",
                "description", "is_active"]
        self._insert_row("mdm.inspection_capabilities", cols, payload)
        return self.get_inspection_capability(payload["capability_id"])

    def set_inspection_capability_active(self, capability_id: str, is_active: bool) -> InspectionCapability | None:
        with self.engine.begin() as conn:
            result = conn.execute(
                text("UPDATE mdm.inspection_capabilities SET is_active = :is_active, "
                     "updated_at = CURRENT_TIMESTAMP WHERE capability_id = :capability_id"),
                {"is_active": is_active, "capability_id": capability_id},
            )
            if result.rowcount == 0:
                return None
        return self.get_inspection_capability(capability_id)
