"""为金发科技领域包补充 material_systems 体系模板。

背景：material_domain 双源统一后，/config 与 /api/config 改由领域包 Store 提供
权威值（AgentConfig 仅作回退）。0046 落库的金发（kingfa）领域包 data 缺少
"material_systems"，导致其体系模板仍回退到 AgentConfig 默认（电池体系），
无法体现改性塑料领域的推荐体系。本迁移为库中 kingfa 记录补充 material_systems，
仅当缺失时写入（幂等，不覆盖用户后续定制）。

Revision ID: 0047_kingfa_material_systems
Revises: 0046_domain_pack_pipeline_kingfa
Create Date: 2026-08-07
"""
from __future__ import annotations

import json

from alembic import op


revision = "0047_kingfa_material_systems"
down_revision = "0046_domain_pack_pipeline_kingfa"
branch_labels = None
depends_on = None


# 金发科技（改性塑料/聚合物复合材料）的推荐体系模板
_KINGFA_MATERIAL_SYSTEMS = [
    {"name": "聚丙烯改性体系", "elements": ["C", "H"]},
    {"name": "尼龙增强体系", "elements": ["C", "H", "O", "N"]},
    {"name": "汽车用工程塑料", "elements": ["C", "H", "O", "N", "Cl"]},
    {"name": "阻燃聚合物体系", "elements": ["C", "H", "O", "N", "P", "Cl", "Br"]},
    {"name": "生物降解材料体系", "elements": ["C", "H", "O", "N"]},
]


def _js(data: list) -> str:
    return json.dumps(data, ensure_ascii=False).replace("'", "''")


def upgrade() -> None:
    op.execute(
        f"""
        UPDATE industrialization.domain_packs
        SET data = data || '{{"material_systems": {_js(_KINGFA_MATERIAL_SYSTEMS)}}}'::jsonb,
            updated_at = NOW()
        WHERE domain_key = 'kingfa'
          AND NOT (data ? 'material_systems')
        """
    )


def downgrade() -> None:
    # 移除 kingfa 领域包的 material_systems（不破坏其他字段）
    op.execute(
        """
        UPDATE industrialization.domain_packs
        SET data = data - 'material_systems',
            updated_at = NOW()
        WHERE domain_key = 'kingfa'
        """
    )