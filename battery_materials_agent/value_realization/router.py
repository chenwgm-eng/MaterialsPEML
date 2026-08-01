"""研发收益证明层 API 路由。"""

from __future__ import annotations
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from .models import ProjectBaseline, CostRule
from .store import ValueRealizationStore
from .calculator import compute_value_report
from .report import render_markdown

router = APIRouter()

_store: ValueRealizationStore | None = None


def _get_store() -> ValueRealizationStore:
    global _store
    if _store is None:
        _store = ValueRealizationStore()
    return _store


# ---------- 基线 ----------

@router.put("/value-baselines/{project_id}")
async def upsert_baseline(project_id: str, baseline: ProjectBaseline):
    """创建或更新项目历史基线。"""
    baseline.project_id = project_id
    return _get_store().upsert_baseline(baseline)


@router.get("/value-baselines/{project_id}")
async def get_baseline(project_id: str):
    """获取项目历史基线。"""
    baseline = _get_store().get_baseline(project_id)
    if baseline is None:
        raise HTTPException(status_code=404, detail="该项目尚未录入历史基线")
    return baseline


# ---------- 成本规则 ----------

@router.get("/cost-rules")
async def list_cost_rules(enabled_only: bool = False):
    """列出成本规则。"""
    return _get_store().list_cost_rules(enabled_only=enabled_only)


@router.post("/cost-rules")
async def create_cost_rule(rule: CostRule):
    """新增成本规则。"""
    return _get_store().create_cost_rule(rule)


@router.put("/cost-rules/{rule_id}")
async def update_cost_rule(rule_id: str, rule: CostRule):
    """更新成本规则。"""
    updated = _get_store().update_cost_rule(rule_id, rule)
    if updated is None:
        raise HTTPException(status_code=404, detail="成本规则不存在")
    return updated


@router.delete("/cost-rules/{rule_id}")
async def delete_cost_rule(rule_id: str):
    """删除成本规则。"""
    if not _get_store().delete_cost_rule(rule_id):
        raise HTTPException(status_code=404, detail="成本规则不存在")
    return {"deleted": True, "rule_id": rule_id}


# ---------- 收益报告 ----------

@router.get("/value-reports/{project_id}")
async def get_value_report(project_id: str):
    """获取项目研发收益账单（JSON 完整报告）。"""
    return await compute_value_report(project_id, vr_store=_get_store())


@router.get("/value-reports/{project_id}/markdown")
async def get_value_report_markdown(project_id: str):
    """导出项目研发收益账单 Markdown。"""
    report = await compute_value_report(project_id, vr_store=_get_store())
    md = render_markdown(report)
    filename = f"value-report-{project_id}.md"
    return Response(
        content=md,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
