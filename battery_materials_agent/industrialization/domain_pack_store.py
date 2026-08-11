"""领域包（Domain Pack）Store：存储与管理各材料领域的声明式配置。

设计目标：把可变的领域知识（配方模板 / 一致性规则 / 目标属性 / 材料表示法）
从硬编码中抽离出来，按领域关键字存取。新增一个新材料领域（如生物材料、纤维、
涂层）时，只需写入一条领域包记录，无需修改核心代码。

每条领域包 data 结构（JSONB）：
{
  "material_representation": "formula" | "smiles" | "sequence" | ...,
  "recipe_templates": [
      {"material_type": "BASE_POLYMER", "main_ratio": 0.9,
       "additives": [{"category": "...", "ratio": 0.1}],
       "equipment": "...", "bop": [ {...} ]},
      {"material_type": "*", ...}   # "*" 为默认模板
  ],
  "fallback_recipe": {"bom": {...}, "equipment": "...", "bop": [...]},
  "consistency": {"polymer_kw": [...], "crystal_kw": [...]},
  "default_target_properties": [...],
  "example_formulas": [...]
}
"""
from __future__ import annotations

import json
import logging
from datetime import datetime

from pydantic import BaseModel, Field
from sqlalchemy import text

from ..db import get_engine

logger = logging.getLogger(__name__)


def _iso(value) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


# 内置默认领域包：当库中无任何活跃领域包时回退使用。
# v4.1：默认领域为改性塑料（kingfa），与迁移 0046/0047 播种的领域包保持一致，
# 保证仅回退路径下行为不回归。
_BUILTIN_FALLBACK = {
    "material_representation": "formula",
    "recipe_templates": [
        {
            "material_type": "BASE_POLYMER",
            "main_ratio": 0.7,
            "additives": [{"category": "material.reinforcement", "ratio": 0.3}],
            "equipment": "双螺杆挤出机",
            "bop": [
                {"step": "预混", "temperature": 25, "duration_min": 30, "rpm": 800, "equipment": "高速混合机"},
                {"step": "挤出造粒", "temperature": 230, "duration_min": 60, "rpm": 300, "equipment": "双螺杆挤出机"},
                {"step": "注塑成型", "temperature": 240, "duration_min": 30, "rpm": 0, "equipment": "注塑机"},
            ],
        },
        {
            "material_type": "*",
            "main_ratio": 0.9,
            "additives": [
                {"category": "ADDITIVE", "ratio": 0.05},
                {"category": "FILLER", "ratio": 0.05},
            ],
            "equipment": "高速混合机",
            "bop": [
                {"step": "预混", "temperature": 25, "duration_min": 30, "rpm": 800, "equipment": "高速混合机"},
                {"step": "挤出造粒", "temperature": 230, "duration_min": 60, "rpm": 300, "equipment": "双螺杆挤出机"},
                {"step": "注塑成型", "temperature": 240, "duration_min": 30, "rpm": 0, "equipment": "注塑机"},
            ],
        },
    ],
    "fallback_recipe": {
        "bom": {"BASE_POLYMER": 0.7, "material.reinforcement": 0.3},
        "equipment": "双螺杆挤出机",
        "bop": [
            {"step": "预混", "temperature": 25, "duration_min": 30, "rpm": 800, "equipment": "高速混合机"},
            {"step": "挤出造粒", "temperature": 230, "duration_min": 60, "rpm": 300, "equipment": "双螺杆挤出机"},
            {"step": "注塑成型", "temperature": 240, "duration_min": 30, "rpm": 0, "equipment": "注塑机"},
        ],
    },
    "consistency": {
        "polymer_kw": ["pp", "pa6", "pa66", "pc", "abs", "pbt", "pet", "pom", "polymer", "尼龙", "聚丙烯", "玻纤", "阻燃", "psmiles", "[*]"],
        "crystal_kw": ["lpscl", "lgps", "li6ps5cl", "lifepo4", "ncm", "sulfide", "li2s", "p2s5"],
    },
    "default_target_properties": ["tensile_strength", "flexural_modulus", "impact_strength", "heat_deflection_temp"],
    "example_formulas": ["PA6/GF30", "PC/ABS", "PP/Talc20", "PBAT"],
}


class DomainPack(BaseModel):
    """领域包记录。"""

    domain_key: str = ""
    name: str = ""
    description: str = ""
    material_representation: str = "formula"
    data: dict = Field(default_factory=dict)
    is_active: bool = True
    created_at: str = ""
    updated_at: str = ""


class DomainPackStore:
    """领域包 Store：List / Get / Upsert / 活跃包解析。"""

    def __init__(self):
        self.engine = get_engine()

    # ── 查询 ──────────────────────────────────────────────
    def list_packs(self, active_only: bool = False) -> list[DomainPack]:
        sql = ("SELECT domain_key, name, description, material_representation, data, "
               "is_active, created_at, updated_at FROM industrialization.domain_packs")
        params = {}
        if active_only:
            sql += " WHERE is_active = TRUE"
        sql += " ORDER BY domain_key"
        with self.engine.connect() as conn:
            rows = conn.execute(text(sql), params).fetchall()
        return [self._row_to_pack(r) for r in rows]

    def get_pack(self, domain_key: str) -> DomainPack | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT domain_key, name, description, material_representation, data, "
                     "is_active, created_at, updated_at FROM industrialization.domain_packs "
                     "WHERE domain_key = :domain_key"),
                {"domain_key": domain_key},
            ).fetchone()
        return self._row_to_pack(row) if row else None

    @staticmethod
    def _row_to_pack(r) -> DomainPack:
        return DomainPack(
            domain_key=r[0] or "",
            name=r[1] or "",
            description=r[2] or "",
            material_representation=r[3] or "formula",
            data=r[4] or {},
            is_active=bool(r[5]),
            created_at=_iso(r[6]),
            updated_at=_iso(r[7]),
        )

    # ── 写入 ──────────────────────────────────────────────
    def upsert_pack(self, pack: DomainPack) -> DomainPack:
        with self.engine.begin() as conn:
            conn.execute(
                text("""INSERT INTO industrialization.domain_packs
                (domain_key, name, description, material_representation, data, is_active)
                VALUES (:domain_key, :name, :description, :material_representation,
                        CAST(:data AS JSONB), :is_active)
                ON CONFLICT (domain_key) DO UPDATE SET
                    name=EXCLUDED.name,
                    description=EXCLUDED.description,
                    material_representation=EXCLUDED.material_representation,
                    data=EXCLUDED.data,
                    is_active=EXCLUDED.is_active,
                    updated_at=NOW()"""),
                {
                    "domain_key": pack.domain_key,
                    "name": pack.name,
                    "description": pack.description,
                    "material_representation": pack.material_representation,
                    "data": json.dumps(pack.data, ensure_ascii=False),
                    "is_active": pack.is_active,
                },
            )
        return self.get_pack(pack.domain_key)

    def set_active(self, domain_key: str, is_active: bool) -> DomainPack | None:
        with self.engine.begin() as conn:
            result = conn.execute(
                text("UPDATE industrialization.domain_packs SET is_active = :is_active, "
                     "updated_at = NOW() WHERE domain_key = :domain_key"),
                {"is_active": is_active, "domain_key": domain_key},
            )
            if result.rowcount == 0:
                return None
        return self.get_pack(domain_key)

    def delete_pack(self, domain_key: str) -> bool:
        with self.engine.begin() as conn:
            result = conn.execute(
                text("DELETE FROM industrialization.domain_packs WHERE domain_key = :domain_key"),
                {"domain_key": domain_key},
            )
            return result.rowcount > 0

    # ── 解析：选择活跃领域包 ──────────────────────────────
    def resolve_active_pack(self, domain_key: str = "") -> DomainPack | None:
        """按 domain_key 解析目标领域包；未指定时返回默认活跃包。

        多领域包场景下不再"取第一个活跃包"（存在歧义），而是：
        - 显式传入 domain_key：精确返回该领域包（须为活跃包，否则视为不存在）。
        - 未指定 domain_key：返回唯一的活跃包；若活跃包不止一个，则返回
          优先级最低的默认包（v4.1 默认领域 kingfa 优先），调用方仍可显式指定 domain_key。
        """
        if domain_key:
            pack = self.get_pack(domain_key)
            return pack if pack and pack.is_active else None
        packs = self.list_packs(active_only=True)
        if not packs:
            return None
        if len(packs) == 1:
            return packs[0]
        # 多个活跃包：kingfa（改性塑料）作为 v4.1 默认领域，排在前面
        return next((p for p in packs if p.domain_key in ("kingfa", "battery")), packs[0])

    @staticmethod
    def builtin_fallback() -> dict:
        """返回内置默认领域包数据（深拷贝），供无库回退路径使用。"""
        import copy

        data = copy.deepcopy(_BUILTIN_FALLBACK)
        # 注入流水线段：直接引用 hybrid.pipeline 的内置默认，保证单一数据源。
        from ..hybrid.pipeline import BUILTIN_PIPELINES

        data["pipeline"] = copy.deepcopy(BUILTIN_PIPELINES)
        return data