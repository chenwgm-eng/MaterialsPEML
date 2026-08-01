"""研发收益账单 Markdown 报告生成。"""

from __future__ import annotations


def _fmt_value(metric: dict) -> str:
    if metric.get("value") is None:
        return "—（数据不足）"
    unit = metric.get("unit") or ""
    return f"{metric['value']} {unit}".strip()


def _fmt_kind(metric: dict) -> str:
    return "已验证" if metric.get("kind") == "verified" else "预估"


def render_markdown(report: dict) -> str:
    """将 compute_value_report 的输出渲染为中文 Markdown 报告。"""
    lines: list[str] = []
    lines.append(f"# 研发收益账单（Value Realization Report）")
    lines.append("")

    # 项目概览
    lines.append("## 一、项目概览")
    lines.append("")
    lines.append(f"- 项目 ID：{report.get('project_id', '')}")
    lines.append(f"- 项目名称：{report.get('project_name') or '—'}")
    lines.append(f"- 报告生成时间：{report.get('generated_at', '')}")
    lines.append("")
    lines.append("> 本报告严格区分「已验证收益（verified，来自系统真实数据）」与"
                 "「预估收益（estimated，基于假设推算）」，两者不可混用。")
    lines.append("")

    # 历史基线
    lines.append("## 二、历史基线")
    lines.append("")
    baseline = report.get("baseline")
    if baseline:
        lines.append(f"- 历史筛选周期：{baseline.get('historical_cycle_days', 0)} 天")
        lines.append(f"- 单次实验典型成本：{baseline.get('typical_experiment_cost', 0)} 元")
        lines.append(f"- 历史命中率：{round(baseline.get('historical_hit_rate', 0) * 100, 1)}%")
        lines.append(f"- 历史典型候选数：{baseline.get('past_candidate_count', 0)} 个")
        lines.append(f"- 成功标准：{baseline.get('success_criteria') or '—'}")
        if baseline.get("notes"):
            lines.append(f"- 备注：{baseline['notes']}")
        lines.append(f"- 基线更新时间：{baseline.get('updated_at', '')}")
    else:
        lines.append("未录入历史基线。预估类指标将标记为数据不足。")
    lines.append("")

    # 指标分组
    section_order = [
        ("candidate_convergence", "三"),
        ("experiment_savings", "四"),
        ("cycle_efficiency", "五"),
        ("economic_value", "六"),
    ]
    for section_key, num in section_order:
        section = report.get("sections", {}).get(section_key, {})
        lines.append(f"## {num}、{section.get('title', section_key)}")
        lines.append("")
        lines.append("| 指标 | 数值 | 性质 |")
        lines.append("| --- | --- | --- |")
        for metric in section.get("metrics", {}).values():
            lines.append(f"| {metric.get('label', '')} | {_fmt_value(metric)} | {_fmt_kind(metric)} |")
        lines.append("")

    # 假设与不确定性
    lines.append("## 七、假设与不确定性")
    lines.append("")
    assumptions = report.get("assumptions", [])
    if assumptions:
        for item in assumptions:
            lines.append(f"- **{item.get('metric', '')}**：{item.get('assumption', '')}")
    else:
        lines.append("无预估类指标，全部数值均为已验证数据。")
    lines.append("")

    # 证据溯源
    lines.append("## 八、证据溯源清单")
    lines.append("")
    refs = report.get("evidence_refs", [])
    if refs:
        for ref in refs:
            lines.append(f"- `{ref}`")
    else:
        lines.append("无证据引用。")
    lines.append("")

    return "\n".join(lines)
