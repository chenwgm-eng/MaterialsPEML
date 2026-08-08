"""新增领域包表：将可变的领域知识（配方模板/一致性规则/目标属性）从硬编码抽离为可配置数据。

背景：新材料研发场景多样，未来可能接入生物材料/纤维/涂层等非电池、非粉末冶金领域。
本迁移新增 industrialization.domain_packs 表，存储每个材料领域的声明式配置，
并预置默认电池/粉末冶金领域包，保证现有流程不回归。

Revision ID: 0045_domain_packs
Revises: 0044_debatterify_agent_overrides
Create Date: 2026-08-07
"""
from __future__ import annotations

import json

from alembic import op


revision = "0045_domain_packs"
down_revision = "0044_debatterify_agent_overrides"
branch_labels = None
depends_on = None


# 默认电池/粉末冶金领域包：与 formula_agent.py 原硬编码逻辑保持一致
def _default_battery_domain() -> dict:
    current = {
        "material_representation": "formula",
        "recipe_templates": [
            {
                "material_type": "BASE_POLYMER",
                "main_ratio": 0.9,
                "additives": [{"category": "LITHIUM_SALT", "ratio": 0.1}],
                "equipment": "双行星搅拌机",
                "bop": [
                    {"step": "混料", "temperature": 25, "duration_min": 60, "rpm": 1500, "equipment": "双行星搅拌机"},
                    {"step": "涂布", "temperature": 25, "duration_min": 30, "rpm": 0, "equipment": "涂布机"},
                    {"step": "烘烤", "temperature": 80, "duration_min": 720, "rpm": 0, "equipment": "真空烘箱"},
                ],
            },
            {
                "material_type": "*",  # 其余材料类型（无机/粉末冶金）默认模板
                "main_ratio": 0.9,
                "additives": [
                    {"category": "BINDER", "ratio": 0.05},
                    {"category": "FILLER", "ratio": 0.05},
                ],
                "equipment": "球磨机",
                "bop": [
                    {"step": "球磨混料", "temperature": 25, "duration_min": 120, "rpm": 300, "equipment": "球磨机"},
                    {"step": "冷压成型", "temperature": 25, "duration_min": 30, "rpm": 0, "equipment": "粉末压片机"},
                    {"step": "烧结", "temperature": 500, "duration_min": 600, "rpm": 0, "equipment": "管式炉"},
                ],
            },
        ],
        "fallback_recipe": {
            "bom": {"BASE_POLYMER": 0.8, "LITHIUM_SALT": 0.2},
            "equipment": "双行星搅拌机",
            "bop": [
                {"step": "混料", "temperature": 25, "duration_min": 60, "rpm": 1500, "equipment": "双行星搅拌机"},
                {"step": "涂布", "temperature": 25, "duration_min": 30, "rpm": 0, "equipment": "涂布机"},
                {"step": "烘烤", "temperature": 80, "duration_min": 720, "rpm": 0, "equipment": "真空烘箱"},
            ],
        },
        "consistency": {
            "polymer_kw": ["peo", "polymer", "pvdf", "pan ", "pan-", "pmma", "psmiles", "[*]"],
            "crystal_kw": ["lpscl", "lgps", "li6ps5cl", "lifepo4", "ncm", "sulfide", "li2s", "p2s5"],
        },
        "default_target_properties": ["ionic_conductivity", "band_gap", "formation_energy"],
        "example_formulas": ["Li6PS5Cl", "Li3YCl6", "LaTiO3", "LiMn2O4"],
    }
    return current


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS industrialization.domain_packs (
            domain_key       VARCHAR(64) PRIMARY KEY,
            name             VARCHAR(128) NOT NULL,
            description      TEXT NOT NULL DEFAULT '',
            material_representation VARCHAR(32) NOT NULL DEFAULT 'formula',
            data             JSONB NOT NULL DEFAULT '{}',
            is_active        BOOLEAN NOT NULL DEFAULT TRUE,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    payload = json.dumps(_default_battery_domain(), ensure_ascii=False).replace("'", "''")
    op.execute(
        "INSERT INTO industrialization.domain_packs "
        "(domain_key, name, description, material_representation, data) VALUES "
        "('battery', '电池/粉末冶金', '默认电池与粉末冶金材料领域包', 'formula', "
        f"'{payload}'::jsonb) "
        "ON CONFLICT (domain_key) DO NOTHING"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS industrialization.domain_packs")