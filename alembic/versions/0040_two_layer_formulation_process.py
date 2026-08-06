"""0040: 两层流程打通 — 候选材料状态机 / 工艺方案结构化 / 实验单双来源引用

对应需求要点：
1. 候选材料（配方设计阶段）：
   - candidates 新增 status（两层状态机：screening → feasible → process_planning
     → process_confirmed → ready_for_experiment / rejected）
   - 新增 owner（责任人）与 assigned_role（当前环节角色）字段
2. 工艺深化（工艺人员阶段）：
   - process_schemes 新增 routes（多路径比选）、evidence_refs（能力来源记录）、
     status（draft → reviewing → confirmed）
3. 实验单双来源：
   - experiment_orders 新增 process_id（关联 ProcessScheme），与 candidate_id 并列，
     形成"配方来源 + 工艺来源"双引用

Revision ID: 0040_two_layer_formulation_process
Revises: 0039_ai_assistant_sessions
Create Date: 2026-08-01
"""
from __future__ import annotations

import logging

from alembic import op

revision = "0040_two_layer_formulation_process"
down_revision = "0039_ai_assistant_sessions"
branch_labels = None
depends_on = None

logger = logging.getLogger(__name__)


def upgrade() -> None:
    # ── 1. 候选材料状态机 ─────────────────────────────────
    op.execute(
        "ALTER TABLE experiment.candidates "
        "ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'screening'"
    )
    op.execute(
        "ALTER TABLE experiment.candidates "
        "ADD COLUMN IF NOT EXISTS owner TEXT DEFAULT ''"
    )
    op.execute(
        "ALTER TABLE experiment.candidates "
        "ADD COLUMN IF NOT EXISTS assigned_role TEXT DEFAULT ''"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_candidates_status "
        "ON experiment.candidates(status)"
    )

    # ── 2. 工艺方案结构化 ─────────────────────────────────
    op.execute(
        "ALTER TABLE experiment.process_schemes "
        "ADD COLUMN IF NOT EXISTS routes JSONB DEFAULT '[]'::jsonb"
    )
    op.execute(
        "ALTER TABLE experiment.process_schemes "
        "ADD COLUMN IF NOT EXISTS evidence_refs JSONB DEFAULT '[]'::jsonb"
    )
    op.execute(
        "ALTER TABLE experiment.process_schemes "
        "ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'draft'"
    )

    # ── 3. 实验单双来源引用 ───────────────────────────────
    op.execute(
        "ALTER TABLE experiment.experiment_orders "
        "ADD COLUMN IF NOT EXISTS process_id TEXT DEFAULT ''"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_experiment_orders_process_id "
        "ON experiment.experiment_orders(process_id)"
    )

    logger.info("0040: 已打通两层流程（候选状态机 / 工艺方案结构化 / 实验单双来源）")


def downgrade() -> None:
    op.execute("ALTER TABLE experiment.candidates DROP COLUMN IF EXISTS status")
    op.execute("ALTER TABLE experiment.candidates DROP COLUMN IF EXISTS owner")
    op.execute("ALTER TABLE experiment.candidates DROP COLUMN IF EXISTS assigned_role")
    op.execute("ALTER TABLE experiment.process_schemes DROP COLUMN IF EXISTS routes")
    op.execute("ALTER TABLE experiment.process_schemes DROP COLUMN IF EXISTS evidence_refs")
    op.execute("ALTER TABLE experiment.process_schemes DROP COLUMN IF EXISTS status")
    op.execute("ALTER TABLE experiment.experiment_orders DROP COLUMN IF EXISTS process_id")
    logger.info("0040: 已回滚两层流程相关字段")