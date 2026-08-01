"""P1 参考字典中心 Store。

承载 7 张主数据表的 CRUD：
- mdm.status_codes 状态码
- mdm.classifications 分类码
- mdm.units 标准单位
- mdm.unit_conversions 单位换算
- mdm.standards 方法标准
- mdm.ghs_classes GHS 危害分类
- mdm.dimensions 通用维度

设计原则：
- 只读为主，初始数据由 0011 迁移脚本 seed
- 提供 list/get/查询接口
- 不提供 create/update/delete（治理操作走 DBA 或专用治理 UI，本 spec 范围外）
- 单位换算提供 convert(value, from_unit, to_unit) 工具方法
"""
from __future__ import annotations
from pydantic import BaseModel, Field, field_validator
from datetime import datetime, timezone
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
class StatusCode(BaseModel):
    """状态码主数据。"""
    code_id: str = ""
    domain: str = ""
    code: str = ""
    label: str = ""
    sort_order: int = 0
    is_active: bool = True
    description: str = ""
    created_at: str = ""
    updated_at: str = ""


class Classification(BaseModel):
    """分类码主数据（树形）。"""
    code: str = ""
    domain: str = ""
    parent_code: str = ""
    label: str = ""
    sort_order: int = 0
    is_active: bool = True
    description: str = ""
    created_at: str = ""
    updated_at: str = ""

    @field_validator("parent_code", mode="before")
    @classmethod
    def _coerce_none(cls, v):
        return "" if v is None else v


class Unit(BaseModel):
    """标准单位主数据。"""
    unit_code: str = ""
    name: str = ""
    symbol: str = ""
    dimension: str = ""
    is_base: bool = False
    is_active: bool = True
    created_at: str = ""
    updated_at: str = ""


class UnitConversion(BaseModel):
    """单位换算：value_in_to = value_in_from * factor + offset_value。"""
    id: int = 0
    from_unit: str = ""
    to_unit: str = ""
    factor: float = 1.0
    offset_value: float = 0.0


class Standard(BaseModel):
    """方法标准主数据。"""
    standard_code: str = ""
    name: str = ""
    issuer: str = ""
    version: str = ""
    effective_date: str | None = None
    is_active: bool = True
    description: str = ""
    created_at: str = ""
    updated_at: str = ""


class GhsClass(BaseModel):
    """GHS 危害分类主数据。"""
    ghs_code: str = ""
    label: str = ""
    hazard_level: str = ""
    pictogram: str = ""
    is_active: bool = True
    created_at: str = ""
    updated_at: str = ""


class Dimension(BaseModel):
    """通用维度主数据。"""
    dim_code: str = ""
    domain: str = ""
    code: str = ""
    label: str = ""
    sort_order: int = 0
    is_active: bool = True
    description: str = ""
    created_at: str = ""
    updated_at: str = ""


# ──────────────────────────────────────────────────────────────────────────────
# Store
# ──────────────────────────────────────────────────────────────────────────────
class ReferenceDictStore:
    """参考字典中心 Store。只读查询 + 单位换算工具。"""

    def __init__(self):
        self.engine = get_engine()

    # ── 状态码 ──────────────────────────────────────────────
    def list_status_codes(self, domain: str = "") -> list[StatusCode]:
        """按 domain 列出状态码；domain 为空时返回全部。"""
        sql = ("SELECT code_id, domain, code, label, sort_order, is_active, description, "
               "created_at, updated_at FROM mdm.status_codes")
        params: dict[str, Any] = {}
        if domain:
            sql += " WHERE domain = :domain"
            params["domain"] = domain
        sql += " ORDER BY domain, sort_order, code"
        with self.engine.connect() as conn:
            rows = conn.execute(text(sql), params).fetchall()
        return [self._row_to_status_code(r) for r in rows]

    def get_status_code(self, domain: str, code: str) -> StatusCode | None:
        """按 domain + code 查询单条状态码。"""
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT code_id, domain, code, label, sort_order, is_active, description, "
                     "created_at, updated_at FROM mdm.status_codes "
                     "WHERE domain = :domain AND code = :code"),
                {"domain": domain, "code": code},
            ).fetchone()
        return self._row_to_status_code(row) if row else None

    @staticmethod
    def _row_to_status_code(r) -> StatusCode:
        return StatusCode(
            code_id=r[0] or "",
            domain=r[1] or "",
            code=r[2] or "",
            label=r[3] or "",
            sort_order=r[4] or 0,
            is_active=bool(r[5]),
            description=r[6] or "",
            created_at=_iso(r[7]),
            updated_at=_iso(r[8]),
        )

    # ── 分类码 ──────────────────────────────────────────────
    def list_classifications(self, domain: str = "", parent_code: str = "") -> list[Classification]:
        """按 domain / parent_code 列出分类码。"""
        sql = ("SELECT code, domain, parent_code, label, sort_order, is_active, description, "
               "created_at, updated_at FROM mdm.classifications WHERE 1=1")
        params: dict[str, Any] = {}
        if domain:
            sql += " AND domain = :domain"
            params["domain"] = domain
        if parent_code:
            sql += " AND parent_code = :parent_code"
            params["parent_code"] = parent_code
        sql += " ORDER BY domain, sort_order, code"
        with self.engine.connect() as conn:
            rows = conn.execute(text(sql), params).fetchall()
        return [self._row_to_classification(r) for r in rows]

    def get_classification(self, code: str) -> Classification | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT code, domain, parent_code, label, sort_order, is_active, description, "
                     "created_at, updated_at FROM mdm.classifications WHERE code = :code"),
                {"code": code},
            ).fetchone()
        return self._row_to_classification(row) if row else None

    @staticmethod
    def _row_to_classification(r) -> Classification:
        return Classification(
            code=r[0] or "",
            domain=r[1] or "",
            parent_code=r[2] or "",
            label=r[3] or "",
            sort_order=r[4] or 0,
            is_active=bool(r[5]),
            description=r[6] or "",
            created_at=_iso(r[7]),
            updated_at=_iso(r[8]),
        )

    # ── 单位 ──────────────────────────────────────────────
    def list_units(self, dimension: str = "") -> list[Unit]:
        sql = ("SELECT unit_code, name, symbol, dimension, is_base, is_active, "
               "created_at, updated_at FROM mdm.units")
        params: dict[str, Any] = {}
        if dimension:
            sql += " WHERE dimension = :dimension"
            params["dimension"] = dimension
        sql += " ORDER BY dimension, is_base DESC, unit_code"
        with self.engine.connect() as conn:
            rows = conn.execute(text(sql), params).fetchall()
        return [self._row_to_unit(r) for r in rows]

    def get_unit(self, unit_code: str) -> Unit | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT unit_code, name, symbol, dimension, is_base, is_active, "
                     "created_at, updated_at FROM mdm.units WHERE unit_code = :unit_code"),
                {"unit_code": unit_code},
            ).fetchone()
        return self._row_to_unit(row) if row else None

    @staticmethod
    def _row_to_unit(r) -> Unit:
        return Unit(
            unit_code=r[0] or "",
            name=r[1] or "",
            symbol=r[2] or "",
            dimension=r[3] or "",
            is_base=bool(r[4]),
            is_active=bool(r[5]),
            created_at=_iso(r[6]),
            updated_at=_iso(r[7]),
        )

    # ── 单位换算 ──────────────────────────────────────────
    def list_conversions(self, from_unit: str = "") -> list[UnitConversion]:
        sql = "SELECT id, from_unit, to_unit, factor, offset_value FROM mdm.unit_conversions"
        params: dict[str, Any] = {}
        if from_unit:
            sql += " WHERE from_unit = :from_unit"
            params["from_unit"] = from_unit
        with self.engine.connect() as conn:
            rows = conn.execute(text(sql), params).fetchall()
        return [UnitConversion(id=r[0], from_unit=r[1] or "", to_unit=r[2] or "",
                               factor=float(r[3] or 1.0), offset_value=float(r[4] or 0.0))
                for r in rows]

    def convert(self, value: float, from_unit: str, to_unit: str) -> float | None:
        """单位换算。返回换算后的值；若无直接换算路径返回 None。

        支持链式换算（最多 2 跳）以处理 from→base→to 的间接路径。
        """
        if from_unit == to_unit:
            return value
        # 直接换算
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT factor, offset_value FROM mdm.unit_conversions "
                     "WHERE from_unit = :from AND to_unit = :to"),
                {"from": from_unit, "to": to_unit},
            ).fetchone()
        if row:
            return value * float(row[0] or 1.0) + float(row[1] or 0.0)
        # 反向换算
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT factor, offset_value FROM mdm.unit_conversions "
                     "WHERE from_unit = :to AND to_unit = :from"),
                {"to": to_unit, "from": from_unit},
            ).fetchone()
        if row:
            factor = float(row[0] or 1.0)
            offset_value = float(row[1] or 0.0)
            if factor == 0:
                return None
            return (value - offset_value) / factor
        # 链式换算：from → base → to（2 跳）
        with self.engine.connect() as conn:
            mid_row = conn.execute(
                text("SELECT to_unit, factor, offset_value FROM mdm.unit_conversions "
                     "WHERE from_unit = :from UNION "
                     "SELECT from_unit, factor, offset_value FROM mdm.unit_conversions "
                     "WHERE to_unit = :from LIMIT 1"),
                {"from": from_unit},
            ).fetchone()
        if mid_row:
            mid_unit = mid_row[0]
            if not mid_unit or mid_unit == to_unit:
                return None
            # 递归：from → mid → to
            mid_value = self.convert(value, from_unit, mid_unit)
            if mid_value is None:
                return None
            return self.convert(mid_value, mid_unit, to_unit)
        return None

    # ── 方法标准 ──────────────────────────────────────────
    def list_standards(self, issuer: str = "") -> list[Standard]:
        sql = ("SELECT standard_code, name, issuer, version, effective_date, is_active, "
               "description, created_at, updated_at FROM mdm.standards")
        params: dict[str, Any] = {}
        if issuer:
            sql += " WHERE issuer = :issuer"
            params["issuer"] = issuer
        sql += " ORDER BY issuer, standard_code"
        with self.engine.connect() as conn:
            rows = conn.execute(text(sql), params).fetchall()
        return [self._row_to_standard(r) for r in rows]

    def get_standard(self, standard_code: str) -> Standard | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT standard_code, name, issuer, version, effective_date, is_active, "
                     "description, created_at, updated_at FROM mdm.standards "
                     "WHERE standard_code = :code"),
                {"code": standard_code},
            ).fetchone()
        return self._row_to_standard(row) if row else None

    @staticmethod
    def _row_to_standard(r) -> Standard:
        return Standard(
            standard_code=r[0] or "",
            name=r[1] or "",
            issuer=r[2] or "",
            version=r[3] or "",
            effective_date=_iso(r[4]) or None,
            is_active=bool(r[5]),
            description=r[6] or "",
            created_at=_iso(r[7]),
            updated_at=_iso(r[8]),
        )

    # ── GHS ──────────────────────────────────────────────
    def list_ghs_classes(self) -> list[GhsClass]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                text("SELECT ghs_code, label, hazard_level, pictogram, is_active, "
                     "created_at, updated_at FROM mdm.ghs_classes "
                     "ORDER BY hazard_level, ghs_code")
            ).fetchall()
        return [self._row_to_ghs(r) for r in rows]

    @staticmethod
    def _row_to_ghs(r) -> GhsClass:
        return GhsClass(
            ghs_code=r[0] or "",
            label=r[1] or "",
            hazard_level=r[2] or "",
            pictogram=r[3] or "",
            is_active=bool(r[4]),
            created_at=_iso(r[5]),
            updated_at=_iso(r[6]),
        )

    # ── 通用维度 ──────────────────────────────────────────
    def list_dimensions(self, domain: str = "") -> list[Dimension]:
        sql = ("SELECT dim_code, domain, code, label, sort_order, is_active, description, "
               "created_at, updated_at FROM mdm.dimensions")
        params: dict[str, Any] = {}
        if domain:
            sql += " WHERE domain = :domain"
            params["domain"] = domain
        sql += " ORDER BY domain, sort_order, code"
        with self.engine.connect() as conn:
            rows = conn.execute(text(sql), params).fetchall()
        return [self._row_to_dimension(r) for r in rows]

    def get_dimension(self, domain: str, code: str) -> Dimension | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT dim_code, domain, code, label, sort_order, is_active, description, "
                     "created_at, updated_at FROM mdm.dimensions "
                     "WHERE domain = :domain AND code = :code"),
                {"domain": domain, "code": code},
            ).fetchone()
        return self._row_to_dimension(row) if row else None

    @staticmethod
    def _row_to_dimension(r) -> Dimension:
        return Dimension(
            dim_code=r[0] or "",
            domain=r[1] or "",
            code=r[2] or "",
            label=r[3] or "",
            sort_order=r[4] or 0,
            is_active=bool(r[5]),
            description=r[6] or "",
            created_at=_iso(r[7]),
            updated_at=_iso(r[8]),
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

    # ── 状态码：create / toggle ───────────────────────────
    def create_status_code(self, payload: dict[str, Any]) -> StatusCode:
        """插入状态码。payload 仅含 updatable 列。返回新建实例。"""
        cols = ["domain", "code", "label", "sort_order", "is_active", "description"]
        self._insert_row("mdm.status_codes", cols, payload)
        return self.get_status_code(payload["domain"], payload["code"])

    def set_status_code_active(self, domain: str, code: str, is_active: bool) -> StatusCode | None:
        """切换状态码 is_active。未命中返回 None。"""
        with self.engine.begin() as conn:
            result = conn.execute(
                text("UPDATE mdm.status_codes SET is_active = :is_active, "
                     "updated_at = CURRENT_TIMESTAMP "
                     "WHERE domain = :domain AND code = :code"),
                {"is_active": is_active, "domain": domain, "code": code},
            )
            if result.rowcount == 0:
                return None
        return self.get_status_code(domain, code)

    # ── 分类码：create / toggle ───────────────────────────
    def create_classification(self, payload: dict[str, Any]) -> Classification:
        cols = ["code", "domain", "parent_code", "label", "sort_order", "is_active", "description"]
        self._insert_row("mdm.classifications", cols, payload)
        return self.get_classification(payload["code"])

    def set_classification_active(self, code: str, is_active: bool) -> Classification | None:
        with self.engine.begin() as conn:
            result = conn.execute(
                text("UPDATE mdm.classifications SET is_active = :is_active, "
                     "updated_at = CURRENT_TIMESTAMP WHERE code = :code"),
                {"is_active": is_active, "code": code},
            )
            if result.rowcount == 0:
                return None
        return self.get_classification(code)

    # ── 单位：create / toggle ─────────────────────────────
    def create_unit(self, payload: dict[str, Any]) -> Unit:
        symbol = payload.get("symbol")
        if symbol:
            with self.engine.connect() as conn:
                existing = conn.execute(
                    text("SELECT 1 FROM mdm.units WHERE symbol = :symbol LIMIT 1"),
                    {"symbol": symbol},
                ).fetchone()
            if existing:
                raise ValueError(f"单位符号已存在: {symbol}")
        cols = ["unit_code", "name", "symbol", "dimension", "is_base", "is_active"]
        self._insert_row("mdm.units", cols, payload)
        return self.get_unit(payload["unit_code"])

    def set_unit_active(self, unit_code: str, is_active: bool) -> Unit | None:
        with self.engine.begin() as conn:
            result = conn.execute(
                text("UPDATE mdm.units SET is_active = :is_active, "
                     "updated_at = CURRENT_TIMESTAMP WHERE unit_code = :unit_code"),
                {"is_active": is_active, "unit_code": unit_code},
            )
            if result.rowcount == 0:
                return None
        return self.get_unit(unit_code)

    # ── 单位：版本管理（T-018）────────────────────────────
    _UNIT_UPDATABLE_COLS = ["name", "symbol", "dimension", "is_base", "is_active"]

    def update_unit(self, unit_code: str, payload: dict[str, Any]) -> Unit | None:
        """更新单位主数据。更新前先保存版本快照（保存合并后的新状态作为活跃版本）。

        若 unit_code 不存在返回 None。
        """
        existing = self.get_unit(unit_code)
        if existing is None:
            return None

        # 合并出新状态
        new_state = existing.model_dump()
        for k in self._UNIT_UPDATABLE_COLS:
            if k in payload:
                new_state[k] = payload[k]

        # 更新前先保存版本快照
        from ..version_store import Version, VersionType, get_version_store
        try:
            vs = get_version_store()
            vs.save(Version(
                entity_type=VersionType.MDM_UNIT,
                entity_id=unit_code,
                version_number=0,  # 自动递增
                snapshot=new_state,
                change_summary=f"更新单位 {unit_code}",
                is_active=True,
            ))
        except Exception:
            import logging
            logging.getLogger(__name__).warning(
                "保存单位版本快照失败: %s", unit_code, exc_info=True,
            )

        # 执行 DB UPDATE
        cols_clean = [c for c in self._UNIT_UPDATABLE_COLS if c in payload]
        if cols_clean:
            set_clause = ", ".join(f"{c} = :{c}" for c in cols_clean)
            set_clause += ", updated_at = CURRENT_TIMESTAMP"
            placeholders = {c: payload[c] for c in cols_clean}
            placeholders["unit_code"] = unit_code
            with self.engine.begin() as conn:
                conn.execute(
                    text(f"UPDATE mdm.units SET {set_clause} WHERE unit_code = :unit_code"),
                    placeholders,
                )

        return self.get_unit(unit_code)

    def list_unit_versions(self, unit_code: str) -> list[dict[str, Any]]:
        """返回指定单位的历史版本列表（按版本号倒序）。"""
        from ..version_store import VersionType, get_version_store
        vs = get_version_store()
        versions = vs.list_by_entity(VersionType.MDM_UNIT.value, unit_code)
        return [v.model_dump() for v in versions]

    def get_unit_version(self, version_id: str) -> dict[str, Any] | None:
        """返回指定版本的快照数据；非 MDM_UNIT 类型或不存在返回 None。"""
        from ..version_store import VersionType, get_version_store
        vs = get_version_store()
        version = vs.get(version_id)
        if version is None or version.entity_type != VersionType.MDM_UNIT:
            return None
        return version.model_dump()

    def activate_unit_version(self, unit_code: str, version_id: str) -> Unit | None:
        """激活旧版本：用旧版本快照数据覆盖当前 mdm.units 记录。

        - 校验 version_id 属于该 unit_code 且类型为 MDM_UNIT
        - 用快照中可更新字段覆盖 mdm.units
        - 调用 version_store.set_active 将该版本设为活跃（同实体其他自动失活）
        """
        from ..version_store import VersionType, get_version_store
        vs = get_version_store()
        version = vs.get(version_id)
        if (version is None
                or version.entity_type != VersionType.MDM_UNIT
                or version.entity_id != unit_code):
            return None

        snapshot = version.snapshot or {}
        cols_clean = [c for c in self._UNIT_UPDATABLE_COLS if c in snapshot]
        if cols_clean:
            set_clause = ", ".join(f"{c} = :{c}" for c in cols_clean)
            set_clause += ", updated_at = CURRENT_TIMESTAMP"
            placeholders = {c: snapshot[c] for c in cols_clean}
            placeholders["unit_code"] = unit_code
            with self.engine.begin() as conn:
                result = conn.execute(
                    text(f"UPDATE mdm.units SET {set_clause} WHERE unit_code = :unit_code"),
                    placeholders,
                )
                if result.rowcount == 0:
                    return None

        vs.set_active(version_id)
        return self.get_unit(unit_code)

    # ── 方法标准：create / toggle ─────────────────────────
    def create_standard(self, payload: dict[str, Any]) -> Standard:
        cols = ["standard_code", "name", "issuer", "version", "effective_date",
                "is_active", "description"]
        self._insert_row("mdm.standards", cols, payload)
        return self.get_standard(payload["standard_code"])

    def set_standard_active(self, standard_code: str, is_active: bool) -> Standard | None:
        with self.engine.begin() as conn:
            result = conn.execute(
                text("UPDATE mdm.standards SET is_active = :is_active, "
                     "updated_at = CURRENT_TIMESTAMP WHERE standard_code = :standard_code"),
                {"is_active": is_active, "standard_code": standard_code},
            )
            if result.rowcount == 0:
                return None
        return self.get_standard(standard_code)

    # ── GHS：get / create / toggle ────────────────────────
    def get_ghs_class(self, ghs_code: str) -> GhsClass | None:
        """按 ghs_code 查询单条 GHS 危害分类。"""
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT ghs_code, label, hazard_level, pictogram, is_active, "
                     "created_at, updated_at FROM mdm.ghs_classes WHERE ghs_code = :ghs_code"),
                {"ghs_code": ghs_code},
            ).fetchone()
        return self._row_to_ghs(row) if row else None

    def create_ghs_class(self, payload: dict[str, Any]) -> GhsClass:
        cols = ["ghs_code", "label", "hazard_level", "pictogram", "is_active"]
        self._insert_row("mdm.ghs_classes", cols, payload)
        return self.get_ghs_class(payload["ghs_code"])

    def set_ghs_class_active(self, ghs_code: str, is_active: bool) -> GhsClass | None:
        with self.engine.begin() as conn:
            result = conn.execute(
                text("UPDATE mdm.ghs_classes SET is_active = :is_active, "
                     "updated_at = CURRENT_TIMESTAMP WHERE ghs_code = :ghs_code"),
                {"is_active": is_active, "ghs_code": ghs_code},
            )
            if result.rowcount == 0:
                return None
        return self.get_ghs_class(ghs_code)

    # ── 通用维度：create / toggle ─────────────────────────
    def create_dimension(self, payload: dict[str, Any]) -> Dimension:
        # dim_code 由 DB 自动生成，不写入
        cols = ["domain", "code", "label", "sort_order", "is_active", "description"]
        self._insert_row("mdm.dimensions", cols, payload)
        return self.get_dimension(payload["domain"], payload["code"])

    def set_dimension_active(self, domain: str, code: str, is_active: bool) -> Dimension | None:
        with self.engine.begin() as conn:
            result = conn.execute(
                text("UPDATE mdm.dimensions SET is_active = :is_active, "
                     "updated_at = CURRENT_TIMESTAMP "
                     "WHERE domain = :domain AND code = :code"),
                {"is_active": is_active, "domain": domain, "code": code},
            )
            if result.rowcount == 0:
                return None
        return self.get_dimension(domain, code)

    # ── 单位换算：create only（无 is_active 列）──────────
    def create_unit_conversion(self, payload: dict[str, Any]) -> UnitConversion:
        """插入单位换算规则。无 is_active 列，故不提供 toggle。"""
        cols = ["from_unit", "to_unit", "factor", "offset_value"]
        cols_clean = [c for c in cols if c in payload]
        if not cols_clean:
            raise ValueError("payload 不包含任何可插入列")
        placeholders = {c: payload.get(c) for c in cols_clean}
        col_list = ",".join(cols_clean)
        param_list = ":" + ",:".join(cols_clean)
        sql = f"INSERT INTO mdm.unit_conversions ({col_list}) VALUES ({param_list})"
        try:
            with self.engine.begin() as conn:
                conn.execute(text(sql), placeholders)
        except IntegrityError as e:
            raise ValueError(f"唯一键冲突: {e.orig}") from e
        # 无 get-by-id，按 from_unit + to_unit 回查
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT id, from_unit, to_unit, factor, offset_value "
                     "FROM mdm.unit_conversions "
                     "WHERE from_unit = :from_unit AND to_unit = :to_unit"),
                {"from_unit": payload["from_unit"], "to_unit": payload["to_unit"]},
            ).fetchone()
        return UnitConversion(
            id=row[0] or 0,
            from_unit=row[1] or "",
            to_unit=row[2] or "",
            factor=float(row[3] or 1.0),
            offset_value=float(row[4] or 0.0),
        )
