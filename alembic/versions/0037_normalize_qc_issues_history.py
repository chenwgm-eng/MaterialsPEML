"""0037: 清理 qc_issues 历史脏数据（dict 格式 → list[str]）

修复 ValidationError: ExperimentResultRecord qc_issues.0 Input should be a valid string

背景：
- experiment.experiment_result_records.qc_issues 契约为 list[str]
- 历史数据中存在 [{'msg': '...', 'type': 'GOVERNANCE'}] 格式的脏数据
- 模型层已在 ExperimentResultRecord.qc_issues 加 field_validator 兜底
- 本迁移一次性清理 DB 历史脏数据，使存储格式与契约一致

实现：直接复用 experiment_controller._normalize_qc_issues 函数，
通过 Python 读取脏记录 → 归一化 → 写回，避免复杂 SQL 子查询。

Revision ID: 0037_normalize_qc_issues_history
Revises: 0036_high_risk_ai_action_dimensions
Create Date: 2026-07-31
"""
from __future__ import annotations

import json
import logging

from alembic import op
from sqlalchemy import text

revision = "0037_normalize_qc_issues_history"
down_revision = "0036_high_risk_ai_action_dimensions"
branch_labels = None
depends_on = None

logger = logging.getLogger(__name__)


def upgrade() -> None:
    # 复用模型层归一化函数，确保与运行时行为一致
    from battery_materials_agent.experiment.experiment_controller import _normalize_qc_issues

    bind = op.get_bind()

    # 1. 查询所有需要清理的记录：qc_issues 为 array 且含 dict 元素，或 root 为 dict
    rows = bind.execute(
        text(
            """
            SELECT result_id, qc_issues
            FROM experiment.experiment_result_records
            WHERE qc_issues IS NOT NULL
              AND (
                (jsonb_typeof(qc_issues::jsonb) = 'array'
                 AND EXISTS (
                   SELECT 1 FROM jsonb_array_elements(qc_issues::jsonb) AS el
                   WHERE jsonb_typeof(el) = 'object'
                 ))
                OR jsonb_typeof(qc_issues::jsonb) = 'object'
                OR jsonb_typeof(qc_issues::jsonb) NOT IN ('array', 'object', 'null')
              )
            """
        )
    ).fetchall()

    if not rows:
        logger.info("0037: 无 qc_issues 脏数据需清理")
        return

    logger.info("0037: 检测到 %d 条 qc_issues 脏数据，开始归一化", len(rows))

    # 2. 逐条归一化并写回
    updated = 0
    for result_id, raw_qc_issues in rows:
        # JSONB 列已被 psycopg3 解析为 Python 对象
        normalized = _normalize_qc_issues(raw_qc_issues)
        bind.execute(
            text(
                "UPDATE experiment.experiment_result_records "
                "SET qc_issues = CAST(:qc_issues AS JSONB) "
                "WHERE result_id = :result_id"
            ),
            {
                "result_id": result_id,
                "qc_issues": json.dumps(normalized, ensure_ascii=False),
            },
        )
        updated += 1
        logger.info("0037: result_id=%s 归一化为 %s", result_id, normalized)

    logger.info("0037: 共清理 %d 条记录", updated)


def downgrade() -> None:
    # 原始 dict 数据已不可逆，downgrade 不恢复脏数据
    # 如需回滚请从备份恢复
    pass
