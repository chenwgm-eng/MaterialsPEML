"""P7 MDM 缺失主数据补充：为业务代码中硬编码但 MDM 未维护的枚举补充 seed。

补充内容：
- mdm.status_codes (domain='synthesis_task'): pending / running / success / failed
- mdm.status_codes (domain='release_card'): draft / pending_review / decided
- mdm.status_codes (domain='material_request'): submitted / approved / rejected / written
- mdm.dimensions (domain='recommendation'): recommend / conditional / need_evidence / human_review / reject
- mdm.dimensions (domain='committee_decision'): pass / reject / request_evidence / human_review / failed
- mdm.dimensions (domain='evidence_category'): prediction / experiment_history / literature / cost / ehs / synthesis_feasibility
- mdm.dimensions (domain='risk_level'): low / medium / high / critical

所有 INSERT 使用 ON CONFLICT (...) DO NOTHING 保证幂等。

Revision ID: 0018_mdm_missing_seed
Revises: 0017_mdm_fill_empty_tables
Create Date: 2026-07-27
"""
from __future__ import annotations

from alembic import op

revision = "0018_mdm_missing_seed"
down_revision = "0017_mdm_fill_empty_tables"
branch_labels = None
depends_on = None


# ──────────────────────────────────────────────────────────────────────────────
# upgrade
# ──────────────────────────────────────────────────────────────────────────────
def upgrade() -> None:
    _seed_status_codes()
    _seed_dimensions()


def _seed_status_codes() -> None:
    """补充缺失的 status_codes domain。"""
    rows = [
        # ── synthesis_task：合成任务生命周期 ──────────────────────────────
        ("synthesis_task.pending", "synthesis_task", "pending", "待执行", 10),
        ("synthesis_task.running", "synthesis_task", "running", "执行中", 20),
        ("synthesis_task.success", "synthesis_task", "success", "成功", 30),
        ("synthesis_task.failed", "synthesis_task", "failed", "失败", 40),
        # ── release_card：实验放行卡状态 ──────────────────────────────
        ("release_card.draft", "release_card", "draft", "草稿", 10),
        ("release_card.pending_review", "release_card", "pending_review", "待复核", 20),
        ("release_card.decided", "release_card", "decided", "已裁决", 30),
        # ── material_request：物料申请审批状态 ──────────────────────────────
        ("material_request.submitted", "material_request", "submitted", "已提交", 10),
        ("material_request.approved", "material_request", "approved", "已批准", 20),
        ("material_request.rejected", "material_request", "rejected", "已拒绝", 30),
        ("material_request.written", "material_request", "written", "已写入", 40),
    ]
    values = ",".join(
        f"('{r[0]}','{r[1]}','{r[2]}','{r[3]}',{r[4]},TRUE,'')" for r in rows
    )
    op.execute(
        f"INSERT INTO mdm.status_codes (code_id, domain, code, label, sort_order, is_active, description) "
        f"VALUES {values} ON CONFLICT (code_id) DO NOTHING"
    )


def _seed_dimensions() -> None:
    """补充缺失的 dimensions domain。"""
    rows = [
        # ── recommendation：放行卡推荐结论 ──────────────────────────────
        ("recommendation.recommend", "recommendation", "recommend", "推荐放行", 10),
        ("recommendation.conditional", "recommendation", "conditional", "条件放行", 20),
        ("recommendation.need_evidence", "recommendation", "need_evidence", "需要补充证据", 30),
        ("recommendation.human_review", "recommendation", "human_review", "建议人工复核", 40),
        ("recommendation.reject", "recommendation", "reject", "拒绝放行", 50),
        # ── committee_decision：委员会裁决结论 ──────────────────────────────
        ("committee_decision.pass", "committee_decision", "pass", "通过", 10),
        ("committee_decision.reject", "committee_decision", "reject", "拒绝", 20),
        ("committee_decision.request_evidence", "committee_decision", "request_evidence", "需要补充证据", 30),
        ("committee_decision.human_review", "committee_decision", "human_review", "建议人工复核", 40),
        ("committee_decision.failed", "committee_decision", "failed", "失败", 50),
        # ── evidence_category：证据摘要类别 ──────────────────────────────
        ("evidence_category.prediction", "evidence_category", "prediction", "预测", 10),
        ("evidence_category.experiment_history", "evidence_category", "experiment_history", "实验历史", 20),
        ("evidence_category.literature", "evidence_category", "literature", "文献", 30),
        ("evidence_category.cost", "evidence_category", "cost", "成本", 40),
        ("evidence_category.ehs", "evidence_category", "ehs", "EHS", 50),
        ("evidence_category.synthesis_feasibility", "evidence_category", "synthesis_feasibility", "合成可行性", 60),
        # ── risk_level：风险等级 ──────────────────────────────
        ("risk_level.low", "risk_level", "low", "低", 10),
        ("risk_level.medium", "risk_level", "medium", "中", 20),
        ("risk_level.high", "risk_level", "high", "高", 30),
        ("risk_level.critical", "risk_level", "critical", "严重", 40),
    ]
    values = ",".join(
        f"('{r[0]}','{r[1]}','{r[2]}','{r[3]}',{r[4]},TRUE,'')" for r in rows
    )
    op.execute(
        f"INSERT INTO mdm.dimensions (dim_code, domain, code, label, sort_order, is_active, description) "
        f"VALUES {values} ON CONFLICT (dim_code) DO NOTHING"
    )


# ──────────────────────────────────────────────────────────────────────────────
# downgrade：seed 数据不可逆，仅占位
# ──────────────────────────────────────────────────────────────────────────────
def downgrade() -> None:
    pass
