"""0036: T-031 高风险 AI 操作人工确认 — 注册新 committee_type / trigger_code 维度

新增 MDM 维度行（ON CONFLICT DO NOTHING，不影响既有数据）：
- committee_type.high_risk_ai_action：高风险 AI 操作委员会
- trigger_code.high_risk_ai_action：高风险 AI 操作触发码

CommitteeRepository.create_case 会校验 committee_type / trigger_code 是否在
mdm.dimensions 中注册，故新增枚举值必须同步 seed。

Revision ID: 0036_high_risk_ai_action_dimensions
Revises: 0035_scp_task_archive
Create Date: 2026-07-30
"""
from __future__ import annotations

from alembic import op

revision = "0036_high_risk_ai_action_dimensions"
down_revision = "0035_scp_task_archive"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "INSERT INTO mdm.dimensions (dim_code, domain, code, label, sort_order, is_active, description) "
        "VALUES ('committee_type.high_risk_ai_action', 'committee_type', 'high_risk_ai_action', "
        "'高风险AI操作', 80, TRUE, 'T-031 高风险 AI 操作人工确认') "
        "ON CONFLICT (dim_code) DO NOTHING"
    )
    op.execute(
        "INSERT INTO mdm.dimensions (dim_code, domain, code, label, sort_order, is_active, description) "
        "VALUES ('trigger_code.high_risk_ai_action', 'trigger_code', 'high_risk_ai_action', "
        "'高风险AI操作', 100, TRUE, 'T-031 高风险 AI 操作人工确认') "
        "ON CONFLICT (dim_code) DO NOTHING"
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM mdm.dimensions "
        "WHERE dim_code IN ('committee_type.high_risk_ai_action', "
        "'trigger_code.high_risk_ai_action')"
    )
