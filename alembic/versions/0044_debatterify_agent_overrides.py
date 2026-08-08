"""去电池化：修正内置智能体覆盖表中的电池专属表述。

背景：agent_team.builtin_agent_overrides 表中存在 3 条早前写入的
覆盖记录，其 name/description/expertise 仍为电池专属文案
（电池衰减学习者/电池机理解释者/电池寿命预言者），在启动时被
AgentRegistry 合并到内置定义上，覆盖了 registry.py 中已去电池化的
默认名称，导致 /agents、/topology 页面仍展示电池专属智能体名。

本迁移仅更新 name/description/expertise 三个字段（与 registry.py 默认完全一致），
保留其余配置（provider / llm_model / capabilities 等）不变。

Revision ID: 0044_debatterify_agent_overrides
Revises: 0043_committee_case_candidate_data
Create Date: 2026-08-07
"""
from __future__ import annotations

import json

from alembic import op

revision = "0044_debatterify_agent_overrides"
down_revision = "0043_committee_case_candidate_data"
branch_labels = None
depends_on = None


# 与 agent_team/registry.py 中对应内置 agent 的默认字段完全一致
_DEBATTERIFIED = {
    "builtin_battery_learner": {
        "name": "材料数据学习者",
        "description": "材料数据学习者：从实验/测量数据中拟合性能演变模型，提取起始值与变化率等性能演变模式",
        "expertise": ["数据演变学习", "性能拟合", "趋势分析", "模式识别"],
    },
    "builtin_battery_interpreter": {
        "name": "材料机理解释者",
        "description": "材料机理解释者：基于数据学习结果分析性能变化的潜在机理，输出主导与次要机理",
        "expertise": ["机理分析", "结构演变", "活性物质损失", "相变分解"],
    },
    "builtin_battery_oracle": {
        "name": "材料性质预言者",
        "description": "材料性质预言者：基于学习结果外推性能演变，预测未来性能值及置信度",
        "expertise": ["性质外推预测", "趋势外推", "置信度评估", "性能预测"],
    },
}


def upgrade() -> None:
    for agent_id, fields in _DEBATTERIFIED.items():
        # data 为 JSONB：仅合并写回 name/description/expertise，保留其余用户配置
        payload = json.dumps(fields, ensure_ascii=False).replace("'", "''")
        op.execute(
            "UPDATE agent_team.builtin_agent_overrides "
            f"SET data = data || '{payload}'::jsonb, updated_at = NOW() "
            f"WHERE id = '{agent_id}'"
        )


def downgrade() -> None:
    """数据修正不可逆，不恢复旧电池文案。"""
    pass