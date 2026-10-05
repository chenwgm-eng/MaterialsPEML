"""kingfa 领域包播种达标阈值（Q6 配套）

Revision ID: 0060_kingfa_target_thresholds
Revises: 0059_experiment_provenance
Create Date: 2026-08-11

Q6 决策：ECML 达标阈值内置表带来源，领域包 `target_thresholds` 可覆盖。
本迁移把内置默认阈值播种进 kingfa 领域包 data，使领域包成为"企业可改"的单一入口
（Settings 页切换领域包即切换阈值口径）。
"""
from __future__ import annotations

import json

from alembic import op

revision = "0060_kingfa_target_thresholds"
down_revision = "0059_experiment_provenance"
branch_labels = None
depends_on = None

# 与 ecml_engine._get_target_threshold 内置表一致（来源：CAMPUS / GB-T 参考区间）
_TARGET_THRESHOLDS = {
    "tensile_strength": 100.0,
    "flexural_modulus": 6000.0,
    "impact_strength": 15.0,
    "heat_deflection_temp": 130.0,
    "melt_flow_index": 15.0,
    "elongation_at_break": 50.0,
    "thermal_stability": 300.0,
    "glass_transition_temp": 120.0,
}


def upgrade() -> None:
    payload = json.dumps(_TARGET_THRESHOLDS, ensure_ascii=False)
    op.execute(
        f"""UPDATE industrialization.domain_packs
            SET data = data || jsonb_build_object('target_thresholds', CAST(:th AS JSONB)),
                updated_at = now()
            WHERE domain_key = 'kingfa'""".replace(":th", f"'{payload}'")
    )


def downgrade() -> None:
    op.execute(
        "UPDATE industrialization.domain_packs "
        "SET data = data - 'target_thresholds', updated_at = now() "
        "WHERE domain_key = 'kingfa'"
    )
