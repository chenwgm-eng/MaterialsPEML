"""P2 物料/样品类型/设备模板/位置主数据 Store。

承载 9 张主数据表的 CRUD：
- mdm.sample_types 样品类型模板
- mdm.sample_status_transitions 样品状态迁移规则
- mdm.locations 位置层级
- mdm.containers 容器与包装
- mdm.logistics_types 物流类型
- mdm.equipment_templates 设备模板
- mdm.equipment_capabilities 设备能力
- mdm.equipment_template_capabilities 设备模板↔能力 M:N
- mdm.material_categories 物料分类治理

设计原则：
- 只读为主，初始数据由 0012 迁移脚本 seed
- 提供 list/get/查询接口
- 状态迁移提供 is_transition_allowed 工具方法
- 位置提供 get_tree 工具方法
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
class SampleType(BaseModel):
    """样品类型模板。"""
    type_code: str = ""
    name: str = ""
    description: str = ""
    default_storage_conditions: str = ""
    default_retention_days: int = 0
    is_hazardous: bool = False
    sort_order: int = 0
    is_active: bool = True
    created_at: str = ""
    updated_at: str = ""


class SampleStatusTransition(BaseModel):
    """样品状态迁移规则。"""
    id: int = 0
    from_status: str = ""
    to_status: str = ""
    is_allowed: bool = True
    requires_approval: bool = False
    description: str = ""
    created_at: str = ""
    updated_at: str = ""


class Location(BaseModel):
    """位置层级。"""
    location_id: str = ""
    parent_id: str = ""
    location_type: str = ""
    name: str = ""
    full_path: str = ""
    capacity: int = 0
    description: str = ""
    is_active: bool = True
    created_at: str = ""
    updated_at: str = ""

    @field_validator("parent_id", mode="before")
    @classmethod
    def _coerce_none(cls, v):
        return "" if v is None else v


class Container(BaseModel):
    """容器与包装主数据。"""
    container_code: str = ""
    name: str = ""
    container_type: str = ""
    material: str = ""
    capacity_value: float = 0.0
    capacity_unit: str = ""
    is_hazardous_compatible: bool = False
    description: str = ""
    is_active: bool = True
    created_at: str = ""
    updated_at: str = ""

    @field_validator("capacity_unit", mode="before")
    @classmethod
    def _coerce_none(cls, v):
        return "" if v is None else v


class LogisticsType(BaseModel):
    """物流类型。"""
    type_code: str = ""
    name: str = ""
    direction: str = ""
    requires_approval: bool = False
    description: str = ""
    sort_order: int = 0
    is_active: bool = True
    created_at: str = ""
    updated_at: str = ""


class EquipmentTemplate(BaseModel):
    """设备模板。"""
    template_code: str = ""
    name: str = ""
    category_code: str = ""
    model: str = ""
    manufacturer: str = ""
    specification: str = ""
    default_location_id: str = ""
    description: str = ""
    is_active: bool = True
    created_at: str = ""
    updated_at: str = ""

    @field_validator("category_code", "default_location_id", mode="before")
    @classmethod
    def _coerce_none(cls, v):
        return "" if v is None else v


class EquipmentCapability(BaseModel):
    """设备能力。"""
    capability_code: str = ""
    name: str = ""
    capability_type: str = ""
    unit: str = ""
    description: str = ""
    is_active: bool = True
    created_at: str = ""
    updated_at: str = ""

    @field_validator("unit", mode="before")
    @classmethod
    def _coerce_none(cls, v):
        return "" if v is None else v


class EquipmentTemplateCapability(BaseModel):
    """设备模板↔能力关联，带 min/max/nominal 值。"""
    id: int = 0
    template_code: str = ""
    capability_code: str = ""
    min_value: float | None = None
    max_value: float | None = None
    nominal_value: float | None = None
    notes: str = ""
    created_at: str = ""


class MaterialCategory(BaseModel):
    """物料分类治理（扩展 classifications）。"""
    category_code: str = ""
    default_unit: str = ""
    default_storage_conditions: str = ""
    default_retention_days: int = 0
    is_hazardous: bool = False
    description: str = ""
    created_at: str = ""
    updated_at: str = ""

    @field_validator("default_unit", mode="before")
    @classmethod
    def _coerce_none(cls, v):
        return "" if v is None else v


# ──────────────────────────────────────────────────────────────────────────────
# Store
# ──────────────────────────────────────────────────────────────────────────────
class MasterDataStore:
    """P2 主数据 Store。只读查询 + 状态迁移/位置树工具方法。"""

    def __init__(self):
        self.engine = get_engine()

    # ── 样品类型 ──────────────────────────────────────────
    def list_sample_types(self, is_active: bool | None = None) -> list[SampleType]:
        sql = ("SELECT type_code, name, description, default_storage_conditions, "
               "default_retention_days, is_hazardous, sort_order, is_active, "
               "created_at, updated_at FROM mdm.sample_types WHERE 1=1")
        params: dict[str, Any] = {}
        if is_active is not None:
            sql += " AND is_active = :is_active"
            params["is_active"] = is_active
        sql += " ORDER BY sort_order, type_code"
        with self.engine.connect() as conn:
            rows = conn.execute(text(sql), params).fetchall()
        return [self._row_to_sample_type(r) for r in rows]

    def get_sample_type(self, type_code: str) -> SampleType | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT type_code, name, description, default_storage_conditions, "
                     "default_retention_days, is_hazardous, sort_order, is_active, "
                     "created_at, updated_at FROM mdm.sample_types "
                     "WHERE type_code = :type_code"),
                {"type_code": type_code},
            ).fetchone()
        return self._row_to_sample_type(row) if row else None

    @staticmethod
    def _row_to_sample_type(r) -> SampleType:
        return SampleType(
            type_code=r[0] or "",
            name=r[1] or "",
            description=r[2] or "",
            default_storage_conditions=r[3] or "",
            default_retention_days=r[4] or 0,
            is_hazardous=bool(r[5]),
            sort_order=r[6] or 0,
            is_active=bool(r[7]),
            created_at=_iso(r[8]),
            updated_at=_iso(r[9]),
        )

    # ── 样品状态迁移 ──────────────────────────────────────
    def list_sample_status_transitions(self, from_status: str = "") -> list[SampleStatusTransition]:
        sql = ("SELECT id, from_status, to_status, is_allowed, requires_approval, "
               "description, created_at, updated_at FROM mdm.sample_status_transitions WHERE 1=1")
        params: dict[str, Any] = {}
        if from_status:
            sql += " AND from_status = :from_status"
            params["from_status"] = from_status
        sql += " ORDER BY from_status, to_status"
        with self.engine.connect() as conn:
            rows = conn.execute(text(sql), params).fetchall()
        return [self._row_to_transition(r) for r in rows]

    def is_transition_allowed(self, from_status: str, to_status: str) -> bool:
        """检查状态迁移是否允许。"""
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT is_allowed FROM mdm.sample_status_transitions "
                     "WHERE from_status = :from AND to_status = :to"),
                {"from": from_status, "to": to_status},
            ).fetchone()
        # 未定义规则默认不允许
        return bool(row[0]) if row else False

    def transition_requires_approval(self, from_status: str, to_status: str) -> bool:
        """检查状态迁移是否需要审批。"""
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT requires_approval FROM mdm.sample_status_transitions "
                     "WHERE from_status = :from AND to_status = :to AND is_allowed = TRUE"),
                {"from": from_status, "to": to_status},
            ).fetchone()
        return bool(row[0]) if row else False

    @staticmethod
    def _row_to_transition(r) -> SampleStatusTransition:
        return SampleStatusTransition(
            id=r[0] or 0,
            from_status=r[1] or "",
            to_status=r[2] or "",
            is_allowed=bool(r[3]),
            requires_approval=bool(r[4]),
            description=r[5] or "",
            created_at=_iso(r[6]),
            updated_at=_iso(r[7]),
        )

    # ── 位置 ──────────────────────────────────────────────
    def list_locations(self, parent_id: str = "", location_type: str = "") -> list[Location]:
        sql = ("SELECT location_id, parent_id, location_type, name, full_path, capacity, "
               "description, is_active, created_at, updated_at FROM mdm.locations WHERE 1=1")
        params: dict[str, Any] = {}
        if parent_id:
            sql += " AND parent_id = :parent_id"
            params["parent_id"] = parent_id
        if location_type:
            sql += " AND location_type = :location_type"
            params["location_type"] = location_type
        sql += " ORDER BY location_type, name"
        with self.engine.connect() as conn:
            rows = conn.execute(text(sql), params).fetchall()
        return [self._row_to_location(r) for r in rows]

    def get_location(self, location_id: str) -> Location | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT location_id, parent_id, location_type, name, full_path, capacity, "
                     "description, is_active, created_at, updated_at FROM mdm.locations "
                     "WHERE location_id = :location_id"),
                {"location_id": location_id},
            ).fetchone()
        return self._row_to_location(row) if row else None

    def get_location_tree(self, root_id: str = "") -> list[Location]:
        """获取位置树（递归查询子节点）。root_id 为空时返回所有根节点及其子树。"""
        if root_id:
            sql = """
                WITH RECURSIVE loc_tree AS (
                    SELECT location_id, parent_id, location_type, name, full_path,
                           capacity, description, is_active, created_at, updated_at
                    FROM mdm.locations WHERE location_id = :root_id
                    UNION ALL
                    SELECT l.location_id, l.parent_id, l.location_type, l.name, l.full_path,
                           l.capacity, l.description, l.is_active, l.created_at, l.updated_at
                    FROM mdm.locations l
                    JOIN loc_tree t ON l.parent_id = t.location_id
                )
                SELECT * FROM loc_tree ORDER BY location_type, name
            """
            params = {"root_id": root_id}
        else:
            sql = ("SELECT location_id, parent_id, location_type, name, full_path, capacity, "
                   "description, is_active, created_at, updated_at FROM mdm.locations "
                   "ORDER BY location_type, name")
            params = {}
        with self.engine.connect() as conn:
            rows = conn.execute(text(sql), params).fetchall()
        return [self._row_to_location(r) for r in rows]

    @staticmethod
    def _row_to_location(r) -> Location:
        return Location(
            location_id=r[0] or "",
            parent_id=r[1] or "",
            location_type=r[2] or "",
            name=r[3] or "",
            full_path=r[4] or "",
            capacity=r[5] or 0,
            description=r[6] or "",
            is_active=bool(r[7]),
            created_at=_iso(r[8]),
            updated_at=_iso(r[9]),
        )

    # ── 容器 ──────────────────────────────────────────────
    def list_containers(self, container_type: str = "") -> list[Container]:
        sql = ("SELECT container_code, name, container_type, material, capacity_value, "
               "capacity_unit, is_hazardous_compatible, description, is_active, "
               "created_at, updated_at FROM mdm.containers WHERE 1=1")
        params: dict[str, Any] = {}
        if container_type:
            sql += " AND container_type = :container_type"
            params["container_type"] = container_type
        sql += " ORDER BY container_type, name"
        with self.engine.connect() as conn:
            rows = conn.execute(text(sql), params).fetchall()
        return [self._row_to_container(r) for r in rows]

    def get_container(self, container_code: str) -> Container | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT container_code, name, container_type, material, capacity_value, "
                     "capacity_unit, is_hazardous_compatible, description, is_active, "
                     "created_at, updated_at FROM mdm.containers "
                     "WHERE container_code = :container_code"),
                {"container_code": container_code},
            ).fetchone()
        return self._row_to_container(row) if row else None

    @staticmethod
    def _row_to_container(r) -> Container:
        return Container(
            container_code=r[0] or "",
            name=r[1] or "",
            container_type=r[2] or "",
            material=r[3] or "",
            capacity_value=float(r[4] or 0.0),
            capacity_unit=r[5] or "",
            is_hazardous_compatible=bool(r[6]),
            description=r[7] or "",
            is_active=bool(r[8]),
            created_at=_iso(r[9]),
            updated_at=_iso(r[10]),
        )

    # ── 物流类型 ──────────────────────────────────────────
    def list_logistics_types(self, direction: str = "") -> list[LogisticsType]:
        sql = ("SELECT type_code, name, direction, requires_approval, description, "
               "sort_order, is_active, created_at, updated_at FROM mdm.logistics_types WHERE 1=1")
        params: dict[str, Any] = {}
        if direction:
            sql += " AND direction = :direction"
            params["direction"] = direction
        sql += " ORDER BY sort_order, type_code"
        with self.engine.connect() as conn:
            rows = conn.execute(text(sql), params).fetchall()
        return [self._row_to_logistics_type(r) for r in rows]

    def get_logistics_type(self, type_code: str) -> LogisticsType | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT type_code, name, direction, requires_approval, description, "
                     "sort_order, is_active, created_at, updated_at FROM mdm.logistics_types "
                     "WHERE type_code = :type_code"),
                {"type_code": type_code},
            ).fetchone()
        return self._row_to_logistics_type(row) if row else None

    @staticmethod
    def _row_to_logistics_type(r) -> LogisticsType:
        return LogisticsType(
            type_code=r[0] or "",
            name=r[1] or "",
            direction=r[2] or "",
            requires_approval=bool(r[3]),
            description=r[4] or "",
            sort_order=r[5] or 0,
            is_active=bool(r[6]),
            created_at=_iso(r[7]),
            updated_at=_iso(r[8]),
        )

    # ── 设备模板 ──────────────────────────────────────────
    def list_equipment_templates(self, category_code: str = "") -> list[EquipmentTemplate]:
        sql = ("SELECT template_code, name, category_code, model, manufacturer, specification, "
               "default_location_id, description, is_active, created_at, updated_at "
               "FROM mdm.equipment_templates WHERE 1=1")
        params: dict[str, Any] = {}
        if category_code:
            sql += " AND category_code = :category_code"
            params["category_code"] = category_code
        sql += " ORDER BY category_code, name"
        with self.engine.connect() as conn:
            rows = conn.execute(text(sql), params).fetchall()
        return [self._row_to_equipment_template(r) for r in rows]

    def get_equipment_template(self, template_code: str) -> EquipmentTemplate | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT template_code, name, category_code, model, manufacturer, specification, "
                     "default_location_id, description, is_active, created_at, updated_at "
                     "FROM mdm.equipment_templates WHERE template_code = :template_code"),
                {"template_code": template_code},
            ).fetchone()
        return self._row_to_equipment_template(row) if row else None

    @staticmethod
    def _row_to_equipment_template(r) -> EquipmentTemplate:
        return EquipmentTemplate(
            template_code=r[0] or "",
            name=r[1] or "",
            category_code=r[2] or "",
            model=r[3] or "",
            manufacturer=r[4] or "",
            specification=r[5] or "",
            default_location_id=r[6] or "",
            description=r[7] or "",
            is_active=bool(r[8]),
            created_at=_iso(r[9]),
            updated_at=_iso(r[10]),
        )

    # ── 设备能力 ──────────────────────────────────────────
    def list_equipment_capabilities(self, capability_type: str = "") -> list[EquipmentCapability]:
        sql = ("SELECT capability_code, name, capability_type, unit, description, is_active, "
               "created_at, updated_at FROM mdm.equipment_capabilities WHERE 1=1")
        params: dict[str, Any] = {}
        if capability_type:
            sql += " AND capability_type = :capability_type"
            params["capability_type"] = capability_type
        sql += " ORDER BY capability_type, name"
        with self.engine.connect() as conn:
            rows = conn.execute(text(sql), params).fetchall()
        return [self._row_to_equipment_capability(r) for r in rows]

    def get_equipment_capability(self, capability_code: str) -> EquipmentCapability | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT capability_code, name, capability_type, unit, description, is_active, "
                     "created_at, updated_at FROM mdm.equipment_capabilities "
                     "WHERE capability_code = :capability_code"),
                {"capability_code": capability_code},
            ).fetchone()
        return self._row_to_equipment_capability(row) if row else None

    @staticmethod
    def _row_to_equipment_capability(r) -> EquipmentCapability:
        return EquipmentCapability(
            capability_code=r[0] or "",
            name=r[1] or "",
            capability_type=r[2] or "",
            unit=r[3] or "",
            description=r[4] or "",
            is_active=bool(r[5]),
            created_at=_iso(r[6]),
            updated_at=_iso(r[7]),
        )

    # ── 设备模板↔能力 ────────────────────────────────────
    def list_template_capabilities(self, template_code: str = "") -> list[EquipmentTemplateCapability]:
        sql = ("SELECT id, template_code, capability_code, min_value, max_value, "
               "nominal_value, notes, created_at FROM mdm.equipment_template_capabilities WHERE 1=1")
        params: dict[str, Any] = {}
        if template_code:
            sql += " AND template_code = :template_code"
            params["template_code"] = template_code
        with self.engine.connect() as conn:
            rows = conn.execute(text(sql), params).fetchall()
        return [self._row_to_template_capability(r) for r in rows]

    @staticmethod
    def _row_to_template_capability(r) -> EquipmentTemplateCapability:
        return EquipmentTemplateCapability(
            id=r[0] or 0,
            template_code=r[1] or "",
            capability_code=r[2] or "",
            min_value=float(r[3]) if r[3] is not None else None,
            max_value=float(r[4]) if r[4] is not None else None,
            nominal_value=float(r[5]) if r[5] is not None else None,
            notes=r[6] or "",
            created_at=_iso(r[7]),
        )

    # ── 物料分类治理 ──────────────────────────────────────
    def list_material_categories(self) -> list[MaterialCategory]:
        sql = ("SELECT category_code, default_unit, default_storage_conditions, "
               "default_retention_days, is_hazardous, description, created_at, updated_at "
               "FROM mdm.material_categories ORDER BY category_code")
        with self.engine.connect() as conn:
            rows = conn.execute(text(sql)).fetchall()
        return [self._row_to_material_category(r) for r in rows]

    def get_material_category(self, category_code: str) -> MaterialCategory | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT category_code, default_unit, default_storage_conditions, "
                     "default_retention_days, is_hazardous, description, created_at, updated_at "
                     "FROM mdm.material_categories WHERE category_code = :category_code"),
                {"category_code": category_code},
            ).fetchone()
        return self._row_to_material_category(row) if row else None

    @staticmethod
    def _row_to_material_category(r) -> MaterialCategory:
        return MaterialCategory(
            category_code=r[0] or "",
            default_unit=r[1] or "",
            default_storage_conditions=r[2] or "",
            default_retention_days=r[3] or 0,
            is_hazardous=bool(r[4]),
            description=r[5] or "",
            created_at=_iso(r[6]),
            updated_at=_iso(r[7]),
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

    # ── 样品类型：create / toggle ─────────────────────────
    def create_sample_type(self, payload: dict[str, Any]) -> SampleType:
        cols = ["type_code", "name", "description", "default_storage_conditions",
                "default_retention_days", "is_hazardous", "sort_order", "is_active"]
        self._insert_row("mdm.sample_types", cols, payload)
        return self.get_sample_type(payload["type_code"])

    def set_sample_type_active(self, type_code: str, is_active: bool) -> SampleType | None:
        with self.engine.begin() as conn:
            result = conn.execute(
                text("UPDATE mdm.sample_types SET is_active = :is_active, "
                     "updated_at = CURRENT_TIMESTAMP WHERE type_code = :type_code"),
                {"is_active": is_active, "type_code": type_code},
            )
            if result.rowcount == 0:
                return None
        return self.get_sample_type(type_code)

    # ── 位置：create / toggle ─────────────────────────────
    def create_location(self, payload: dict[str, Any]) -> Location:
        cols = ["location_id", "parent_id", "location_type", "name", "full_path",
                "capacity", "description", "is_active"]
        self._insert_row("mdm.locations", cols, payload)
        return self.get_location(payload["location_id"])

    def set_location_active(self, location_id: str, is_active: bool) -> Location | None:
        with self.engine.begin() as conn:
            result = conn.execute(
                text("UPDATE mdm.locations SET is_active = :is_active, "
                     "updated_at = CURRENT_TIMESTAMP WHERE location_id = :location_id"),
                {"is_active": is_active, "location_id": location_id},
            )
            if result.rowcount == 0:
                return None
        return self.get_location(location_id)

    # ── 容器：create / toggle ─────────────────────────────
    def create_container(self, payload: dict[str, Any]) -> Container:
        cols = ["container_code", "name", "container_type", "material", "capacity_value",
                "capacity_unit", "is_hazardous_compatible", "description", "is_active"]
        self._insert_row("mdm.containers", cols, payload)
        return self.get_container(payload["container_code"])

    def set_container_active(self, container_code: str, is_active: bool) -> Container | None:
        with self.engine.begin() as conn:
            result = conn.execute(
                text("UPDATE mdm.containers SET is_active = :is_active, "
                     "updated_at = CURRENT_TIMESTAMP WHERE container_code = :container_code"),
                {"is_active": is_active, "container_code": container_code},
            )
            if result.rowcount == 0:
                return None
        return self.get_container(container_code)

    # ── 物流类型：create / toggle ─────────────────────────
    def create_logistics_type(self, payload: dict[str, Any]) -> LogisticsType:
        cols = ["type_code", "name", "direction", "requires_approval", "description",
                "sort_order", "is_active"]
        self._insert_row("mdm.logistics_types", cols, payload)
        return self.get_logistics_type(payload["type_code"])

    def set_logistics_type_active(self, type_code: str, is_active: bool) -> LogisticsType | None:
        with self.engine.begin() as conn:
            result = conn.execute(
                text("UPDATE mdm.logistics_types SET is_active = :is_active, "
                     "updated_at = CURRENT_TIMESTAMP WHERE type_code = :type_code"),
                {"is_active": is_active, "type_code": type_code},
            )
            if result.rowcount == 0:
                return None
        return self.get_logistics_type(type_code)

    # ── 设备模板：create / toggle ─────────────────────────
    def create_equipment_template(self, payload: dict[str, Any]) -> EquipmentTemplate:
        cols = ["template_code", "name", "category_code", "model", "manufacturer",
                "specification", "default_location_id", "description", "is_active"]
        self._insert_row("mdm.equipment_templates", cols, payload)
        return self.get_equipment_template(payload["template_code"])

    def set_equipment_template_active(self, template_code: str, is_active: bool) -> EquipmentTemplate | None:
        with self.engine.begin() as conn:
            result = conn.execute(
                text("UPDATE mdm.equipment_templates SET is_active = :is_active, "
                     "updated_at = CURRENT_TIMESTAMP WHERE template_code = :template_code"),
                {"is_active": is_active, "template_code": template_code},
            )
            if result.rowcount == 0:
                return None
        return self.get_equipment_template(template_code)

    # ── 设备能力：create / toggle ─────────────────────────
    def create_equipment_capability(self, payload: dict[str, Any]) -> EquipmentCapability:
        cols = ["capability_code", "name", "capability_type", "unit", "description", "is_active"]
        self._insert_row("mdm.equipment_capabilities", cols, payload)
        return self.get_equipment_capability(payload["capability_code"])

    def set_equipment_capability_active(self, capability_code: str, is_active: bool) -> EquipmentCapability | None:
        with self.engine.begin() as conn:
            result = conn.execute(
                text("UPDATE mdm.equipment_capabilities SET is_active = :is_active, "
                     "updated_at = CURRENT_TIMESTAMP WHERE capability_code = :capability_code"),
                {"is_active": is_active, "capability_code": capability_code},
            )
            if result.rowcount == 0:
                return None
        return self.get_equipment_capability(capability_code)

    # ── 物料分类：create only（无 is_active 列）──────────
    def create_material_category(self, payload: dict[str, Any]) -> MaterialCategory:
        cols = ["category_code", "default_unit", "default_storage_conditions",
                "default_retention_days", "is_hazardous", "description"]
        self._insert_row("mdm.material_categories", cols, payload)
        return self.get_material_category(payload["category_code"])
