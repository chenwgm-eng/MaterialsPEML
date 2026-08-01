"""P4 工艺路线-步骤-参数-设备能力 Store。

承载 6 张主数据表的 CRUD：
- mdm.process_routes 工艺路线模板
- mdm.process_steps 工艺步骤模板
- mdm.process_parameters 工艺参数字典
- mdm.process_route_steps 路线↔步骤有序关联
- mdm.process_step_parameters 步骤↔参数关联
- mdm.process_step_equipment_templates 步骤↔设备模板 M:N
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
class ProcessRoute(BaseModel):
    """工艺路线模板。"""
    route_id: str = ""
    name: str = ""
    route_type: str = ""
    description: str = ""
    version: str = "v1"
    is_active: bool = True
    created_at: str = ""
    updated_at: str = ""


class ProcessStep(BaseModel):
    """工艺步骤模板。"""
    step_id: str = ""
    name: str = ""
    step_type: str = ""
    description: str = ""
    sort_order: int = 0
    is_active: bool = True
    created_at: str = ""
    updated_at: str = ""


class ProcessParameter(BaseModel):
    """工艺参数字典。"""
    parameter_id: str = ""
    name: str = ""
    parameter_type: str = ""
    unit: str = ""
    description: str = ""
    sort_order: int = 0
    is_active: bool = True
    created_at: str = ""
    updated_at: str = ""

    @field_validator("unit", mode="before")
    @classmethod
    def _coerce_none(cls, v):
        return "" if v is None else v


class ProcessRouteStep(BaseModel):
    """路线↔步骤有序关联。"""
    id: int = 0
    route_id: str = ""
    step_id: str = ""
    step_order: int = 0
    notes: str = ""
    created_at: str = ""


class ProcessStepParameter(BaseModel):
    """步骤↔参数关联（默认值/区间/控制级别）。"""
    id: int = 0
    step_id: str = ""
    parameter_id: str = ""
    default_value: float | None = None
    min_value: float | None = None
    max_value: float | None = None
    control_level: str = "normal"
    notes: str = ""
    created_at: str = ""


class ProcessStepEquipmentTemplate(BaseModel):
    """步骤↔设备模板 M:N。"""
    id: int = 0
    step_id: str = ""
    template_code: str = ""
    is_preferred: bool = False
    notes: str = ""
    created_at: str = ""


# ──────────────────────────────────────────────────────────────────────────────
# Store
# ──────────────────────────────────────────────────────────────────────────────
class ProcessStore:
    """P4 工艺路线 Store。只读查询。"""

    def __init__(self):
        self.engine = get_engine()

    # ── 工艺路线 ──────────────────────────────────────────
    def list_process_routes(self, route_type: str = "") -> list[ProcessRoute]:
        sql = ("SELECT route_id, name, route_type, description, version, is_active, "
               "created_at, updated_at FROM mdm.process_routes WHERE 1=1")
        params: dict[str, Any] = {}
        if route_type:
            sql += " AND route_type = :route_type"
            params["route_type"] = route_type
        sql += " ORDER BY route_id"
        with self.engine.connect() as conn:
            rows = conn.execute(text(sql), params).fetchall()
        return [self._row_to_route(r) for r in rows]

    def get_process_route(self, route_id: str) -> ProcessRoute | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT route_id, name, route_type, description, version, is_active, "
                     "created_at, updated_at FROM mdm.process_routes WHERE route_id = :route_id"),
                {"route_id": route_id},
            ).fetchone()
        return self._row_to_route(row) if row else None

    @staticmethod
    def _row_to_route(r) -> ProcessRoute:
        return ProcessRoute(
            route_id=r[0] or "",
            name=r[1] or "",
            route_type=r[2] or "",
            description=r[3] or "",
            version=r[4] or "v1",
            is_active=bool(r[5]),
            created_at=_iso(r[6]),
            updated_at=_iso(r[7]),
        )

    # ── 工艺步骤 ──────────────────────────────────────────
    def list_process_steps(self, step_type: str = "") -> list[ProcessStep]:
        sql = ("SELECT step_id, name, step_type, description, sort_order, is_active, "
               "created_at, updated_at FROM mdm.process_steps WHERE 1=1")
        params: dict[str, Any] = {}
        if step_type:
            sql += " AND step_type = :step_type"
            params["step_type"] = step_type
        sql += " ORDER BY sort_order, step_id"
        with self.engine.connect() as conn:
            rows = conn.execute(text(sql), params).fetchall()
        return [self._row_to_step(r) for r in rows]

    def get_process_step(self, step_id: str) -> ProcessStep | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT step_id, name, step_type, description, sort_order, is_active, "
                     "created_at, updated_at FROM mdm.process_steps WHERE step_id = :step_id"),
                {"step_id": step_id},
            ).fetchone()
        return self._row_to_step(row) if row else None

    @staticmethod
    def _row_to_step(r) -> ProcessStep:
        return ProcessStep(
            step_id=r[0] or "",
            name=r[1] or "",
            step_type=r[2] or "",
            description=r[3] or "",
            sort_order=r[4] or 0,
            is_active=bool(r[5]),
            created_at=_iso(r[6]),
            updated_at=_iso(r[7]),
        )

    # ── 工艺参数 ──────────────────────────────────────────
    def list_process_parameters(self, parameter_type: str = "") -> list[ProcessParameter]:
        sql = ("SELECT parameter_id, name, parameter_type, unit, description, sort_order, "
               "is_active, created_at, updated_at FROM mdm.process_parameters WHERE 1=1")
        params: dict[str, Any] = {}
        if parameter_type:
            sql += " AND parameter_type = :parameter_type"
            params["parameter_type"] = parameter_type
        sql += " ORDER BY sort_order, parameter_id"
        with self.engine.connect() as conn:
            rows = conn.execute(text(sql), params).fetchall()
        return [self._row_to_parameter(r) for r in rows]

    def get_process_parameter(self, parameter_id: str) -> ProcessParameter | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT parameter_id, name, parameter_type, unit, description, sort_order, "
                     "is_active, created_at, updated_at FROM mdm.process_parameters "
                     "WHERE parameter_id = :parameter_id"),
                {"parameter_id": parameter_id},
            ).fetchone()
        return self._row_to_parameter(row) if row else None

    @staticmethod
    def _row_to_parameter(r) -> ProcessParameter:
        return ProcessParameter(
            parameter_id=r[0] or "",
            name=r[1] or "",
            parameter_type=r[2] or "",
            unit=r[3] or "",
            description=r[4] or "",
            sort_order=r[5] or 0,
            is_active=bool(r[6]),
            created_at=_iso(r[7]),
            updated_at=_iso(r[8]),
        )

    # ── 路线↔步骤 ────────────────────────────────────────
    def list_route_steps(self, route_id: str = "") -> list[ProcessRouteStep]:
        sql = ("SELECT id, route_id, step_id, step_order, notes, created_at "
               "FROM mdm.process_route_steps WHERE 1=1")
        params: dict[str, Any] = {}
        if route_id:
            sql += " AND route_id = :route_id"
            params["route_id"] = route_id
        sql += " ORDER BY step_order"
        with self.engine.connect() as conn:
            rows = conn.execute(text(sql), params).fetchall()
        return [self._row_to_route_step(r) for r in rows]

    @staticmethod
    def _row_to_route_step(r) -> ProcessRouteStep:
        return ProcessRouteStep(
            id=r[0] or 0,
            route_id=r[1] or "",
            step_id=r[2] or "",
            step_order=r[3] or 0,
            notes=r[4] or "",
            created_at=_iso(r[5]),
        )

    # ── 步骤↔参数 ────────────────────────────────────────
    def list_step_parameters(self, step_id: str = "") -> list[ProcessStepParameter]:
        sql = ("SELECT id, step_id, parameter_id, default_value, min_value, max_value, "
               "control_level, notes, created_at FROM mdm.process_step_parameters WHERE 1=1")
        params: dict[str, Any] = {}
        if step_id:
            sql += " AND step_id = :step_id"
            params["step_id"] = step_id
        with self.engine.connect() as conn:
            rows = conn.execute(text(sql), params).fetchall()
        return [self._row_to_step_parameter(r) for r in rows]

    @staticmethod
    def _row_to_step_parameter(r) -> ProcessStepParameter:
        return ProcessStepParameter(
            id=r[0] or 0,
            step_id=r[1] or "",
            parameter_id=r[2] or "",
            default_value=float(r[3]) if r[3] is not None else None,
            min_value=float(r[4]) if r[4] is not None else None,
            max_value=float(r[5]) if r[5] is not None else None,
            control_level=r[6] or "normal",
            notes=r[7] or "",
            created_at=_iso(r[8]),
        )

    # ── 步骤↔设备模板 ────────────────────────────────────
    def list_step_equipment_templates(self, step_id: str = "") -> list[ProcessStepEquipmentTemplate]:
        sql = ("SELECT id, step_id, template_code, is_preferred, notes, created_at "
               "FROM mdm.process_step_equipment_templates WHERE 1=1")
        params: dict[str, Any] = {}
        if step_id:
            sql += " AND step_id = :step_id"
            params["step_id"] = step_id
        with self.engine.connect() as conn:
            rows = conn.execute(text(sql), params).fetchall()
        return [self._row_to_step_equipment(r) for r in rows]

    @staticmethod
    def _row_to_step_equipment(r) -> ProcessStepEquipmentTemplate:
        return ProcessStepEquipmentTemplate(
            id=r[0] or 0,
            step_id=r[1] or "",
            template_code=r[2] or "",
            is_preferred=bool(r[3]),
            notes=r[4] or "",
            created_at=_iso(r[5]),
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

    # ── 工艺路线：create / toggle ─────────────────────────
    def create_process_route(self, payload: dict[str, Any]) -> ProcessRoute:
        cols = ["route_id", "name", "route_type", "description", "version", "is_active"]
        self._insert_row("mdm.process_routes", cols, payload)
        return self.get_process_route(payload["route_id"])

    def set_process_route_active(self, route_id: str, is_active: bool) -> ProcessRoute | None:
        with self.engine.begin() as conn:
            result = conn.execute(
                text("UPDATE mdm.process_routes SET is_active = :is_active, "
                     "updated_at = CURRENT_TIMESTAMP WHERE route_id = :route_id"),
                {"is_active": is_active, "route_id": route_id},
            )
            if result.rowcount == 0:
                return None
        return self.get_process_route(route_id)

    # ── 工艺步骤：create / toggle ─────────────────────────
    def create_process_step(self, payload: dict[str, Any]) -> ProcessStep:
        cols = ["step_id", "name", "step_type", "description", "sort_order", "is_active"]
        self._insert_row("mdm.process_steps", cols, payload)
        return self.get_process_step(payload["step_id"])

    def set_process_step_active(self, step_id: str, is_active: bool) -> ProcessStep | None:
        with self.engine.begin() as conn:
            result = conn.execute(
                text("UPDATE mdm.process_steps SET is_active = :is_active, "
                     "updated_at = CURRENT_TIMESTAMP WHERE step_id = :step_id"),
                {"is_active": is_active, "step_id": step_id},
            )
            if result.rowcount == 0:
                return None
        return self.get_process_step(step_id)

    # ── 工艺参数：create / toggle ─────────────────────────
    def create_process_parameter(self, payload: dict[str, Any]) -> ProcessParameter:
        cols = ["parameter_id", "name", "parameter_type", "unit", "description",
                "sort_order", "is_active"]
        self._insert_row("mdm.process_parameters", cols, payload)
        return self.get_process_parameter(payload["parameter_id"])

    def set_process_parameter_active(self, parameter_id: str, is_active: bool) -> ProcessParameter | None:
        with self.engine.begin() as conn:
            result = conn.execute(
                text("UPDATE mdm.process_parameters SET is_active = :is_active, "
                     "updated_at = CURRENT_TIMESTAMP WHERE parameter_id = :parameter_id"),
                {"is_active": is_active, "parameter_id": parameter_id},
            )
            if result.rowcount == 0:
                return None
        return self.get_process_parameter(parameter_id)
