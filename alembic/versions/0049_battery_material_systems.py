"""为 battery 领域包补充 material_systems 体系模板。

背景：_resolve_material_domain 修正为"领域包激活则未声明字段为空，不再回退
AgentConfig"，杜绝跨域串数据。但默认 battery 领域包（0045 播种）未声明
material_systems，会导致其体系模板变为空。本迁移为库中 battery 记录补充
material_systems（与 AgentConfig 默认电池体系一致），仅当缺失时写入（幂等）。
"""
from __future__ import annotations

import json

from alembic import op


revision = "0049_battery_material_systems"
down_revision = "0048_add_material_system"
branch_labels = None
depends_on = None


# 默认电池领域体系模板（与 AgentConfig.material_domain.material_systems 默认一致）
_BATTERY_MATERIAL_SYSTEMS = [
    {"name": "硫化物固态电解质", "elements": ["Li", "P", "S"]},
    {"name": "氧化物固态电解质", "elements": ["La", "Zr", "O"]},
    {"name": "卤化物电解质", "elements": ["Li", "Y", "Cl", "Br", "I"]},
    {"name": "钙钛矿氧化物", "elements": ["La", "Sr", "Ti", "O"]},
    {"name": "尖晶石氧化物", "elements": ["Li", "Mn", "O"]},
    {"name": "层状氧化物", "elements": ["Li", "Co", "Ni", "Mn", "O"]},
]


def _js(data: list) -> str:
    return json.dumps(data, ensure_ascii=False).replace("'", "''")


def upgrade() -> None:
    op.execute(
        f"""
        UPDATE industrialization.domain_packs
        SET data = data || '{{"material_systems": {_js(_BATTERY_MATERIAL_SYSTEMS)}}}'::jsonb,
            updated_at = NOW()
        WHERE domain_key = 'battery'
          AND NOT (data ? 'material_systems')
        """
    )


def downgrade() -> None:
    # 移除 battery 领域包的 material_systems（不破坏其他字段）
    op.execute(
        """
        UPDATE industrialization.domain_packs
        SET data = data - 'material_systems',
            updated_at = NOW()
        WHERE domain_key = 'battery'
        """
    )