"""GNoME 真实数据存储：gnome.gnome_materials（统一 PostgreSQL）。

替代原 hardcoded 回退的真实数据源。由 scripts/import_gnome.py 导入完整
GNoME 稳定集，查询走元素 GIN 索引 + 化学式/材料 ID btree 索引。
"""
from __future__ import annotations

import logging
from typing import Any, Sequence

from sqlalchemy import text

from ..db import get_engine

logger = logging.getLogger(__name__)

# 支持的列，用于导入脚本与查询
GNOME_COLUMNS = (
    "formula",
    "reduced_formula",
    "space_group",
    "structure_type",
    "energy_above_hull",
    "band_gap",
    "formation_energy",
    "material_id",
    "ionic_conductivity",
    "elements",
    "source",
)


class GnomeMaterialStore:
    """GNoME 材料查询/导入存储（内存级无缓存，直接查 PG）。"""

    def __init__(self):
        self.engine = get_engine()

    def count(self) -> int:
        """返回已导入的 GNoME 记录数。"""
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT COUNT(*) FROM gnome.gnome_materials")
            ).scalar_one_or_none()
        return int(row or 0)

    def search(
        self,
        formula: str = "",
        elements: Sequence[str] | None = None,
        num_results: int = 10,
    ) -> list[dict[str, Any]]:
        """按化学式/元素查询 GNoME 材料，按能量最接近凸包（e_above_hull 最小）排序。

        Args:
            formula: 化学式子串（大小写不敏感）
            elements: 目标元素集合约束（元素为超集匹配）
            num_results: 返回数量上限

        Returns:
            命中的材料字典列表（与 CrystalCandidate 字段对应）
        """
        clauses: list[str] = []
        params: dict[str, Any] = {"limit": max(num_results, 1)}

        formula = (formula or "").strip()
        if formula:
            clauses.append("(formula ILIKE :flike OR reduced_formula ILIKE :flike)")
            params["flike"] = f"%{formula}%"

        if elements:
            # 元素名规范化：首字母大写其余小写
            norm = [e.capitalize() for e in elements if e]
            if norm:
                clauses.append("elements @> :elems")
                params["elems"] = norm

        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = text(
            "SELECT formula, reduced_formula, space_group, structure_type, "
            "energy_above_hull, band_gap, formation_energy, material_id, "
            "ionic_conductivity, elements, source "
            "FROM gnome.gnome_materials "
            f"{where} "
            "ORDER BY energy_above_hull ASC, id ASC "
            "LIMIT :limit"
        )
        with self.engine.connect() as conn:
            rows = conn.execute(sql, params).mappings().all()

        return [dict(r) for r in rows]

    def bulk_insert(self, rows: Sequence[dict[str, Any]]) -> int:
        """批量导入（供 scripts/import_gnome.py 使用）。已存在的 material_id 跳过。

        注意：Python list 由 psycopg2 原生适配为 PG TEXT[]，元素列直接传 list 即可，
        无需手写数组字面量。

        Args:
            rows: 每项含 GNOME_COLUMNS 对应字段

        Returns:
            实际插入的记录数
        """
        inserted = 0
        # 分批插入，避免单事务过大
        for i in range(0, len(rows), 2000):
            batch = rows[i : i + 2000]
            with self.engine.begin() as conn:
                for r in batch:
                    exists = conn.execute(
                        text("SELECT 1 FROM gnome.gnome_materials WHERE material_id = :mid"),
                        {"mid": r.get("material_id", "")},
                    ).scalar_one_or_none()
                    if exists:
                        continue
                    params = {
                        k: r.get(
                            k,
                            "" if k in ("formula", "reduced_formula", "space_group", "structure_type", "material_id", "source") else 0,
                        )
                        for k in GNOME_COLUMNS
                    }
                    params["elements"] = params.get("elements") or []
                    conn.execute(
                        text(
                            "INSERT INTO gnome.gnome_materials "
                            "(formula, reduced_formula, space_group, structure_type, "
                            " energy_above_hull, band_gap, formation_energy, material_id, "
                            " ionic_conductivity, elements, source) "
                            "VALUES (:formula, :reduced_formula, :space_group, :structure_type, "
                            ":energy_above_hull, :band_gap, :formation_energy, :material_id, "
                            ":ionic_conductivity, :elements, :source)"
                        ),
                        params,
                    )
                    inserted += 1
        return inserted