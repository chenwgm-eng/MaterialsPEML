"""报表导出：Excel / PDF 生成、报表数据查询、定时报表调度。

- export_excel / export_pdf：生成二进制字节。
- build_report：按报表类型查询数据，返回 {columns, rows, title}。
- schedule_report / start_report_scheduler：APScheduler + PostgreSQL 持久化调度。
  任务持久化于 ``apscheduler_jobs`` 表（SQLAlchemyJobStore 自动建表），
  全量 cron（5/6 段，仅支持标准 cron 语法）驱动，进程重启后自动恢复。
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import text

from ..db import get_engine, get_tenant, set_tenant, tenant_filter

logger = logging.getLogger(__name__)

# 支持的报表类型与来源表/列定义。
# 注：0051 迁移后 experiment.equipment 已含 tenant_id，全部报表类型均参与租户过滤。
REPORT_TYPES: dict[str, dict[str, Any]] = {
    "candidate": {
        "table": "experiment.candidates",
        "title": "候选材料报表",
        "tenant_scoped": True,
        "columns": [
            {"key": "candidate_id", "title": "候选ID"},
            {"key": "name", "title": "化学式/名称"},
            {"key": "candidate_type", "title": "类型"},
            {"key": "status", "title": "状态"},
            {"key": "multi_objective_score", "title": "综合得分"},
            {"key": "created_at", "title": "创建时间"},
        ],
    },
    "experiment": {
        "table": "experiment.experiment_result_records",
        "title": "实验结果报表",
        "tenant_scoped": True,
        "columns": [
            {"key": "result_id", "title": "结果ID"},
            {"key": "experiment_order_id", "title": "实验单ID"},
            {"key": "sample_id", "title": "样品ID"},
            {"key": "property_name", "title": "测试属性"},
            {"key": "value", "title": "数值"},
            {"key": "unit", "title": "单位"},
            {"key": "test_method", "title": "测试方法"},
            {"key": "qc_status", "title": "质检状态"},
            {"key": "data_quality", "title": "数据质量"},
            {"key": "uploaded_at", "title": "上传时间"},
        ],
    },
    "equipment": {
        "table": "experiment.equipment",
        "title": "设备台账报表",
        "tenant_scoped": True,
        "columns": [
            {"key": "equipment_id", "title": "设备ID"},
            {"key": "name", "title": "名称"},
            {"key": "model", "title": "型号"},
            {"key": "category", "title": "分类"},
            {"key": "serial_number", "title": "序列号"},
            {"key": "location", "title": "位置"},
            {"key": "status", "title": "状态"},
            {"key": "responsible_person", "title": "负责人"},
            {"key": "next_calibration", "title": "下次校准"},
        ],
    },
    "sample": {
        "table": "experiment.samples",
        "title": "样品报表",
        "tenant_scoped": True,
        "columns": [
            {"key": "sample_id", "title": "样品ID"},
            {"key": "name", "title": "名称"},
            {"key": "source_type", "title": "来源类型"},
            {"key": "batch_number", "title": "批次号"},
            {"key": "quantity", "title": "数量"},
            {"key": "unit", "title": "单位"},
            {"key": "status", "title": "状态"},
            {"key": "storage_location", "title": "存储位置"},
            {"key": "chemical_formula", "title": "化学式"},
            {"key": "created_at", "title": "创建时间"},
        ],
    },
}

VALID_FORMATS = ("excel", "pdf")


def _normalize(value: Any) -> Any:
    """将 DB 取值规范化为可序列化/可写入单元格的值。"""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return value


def build_report(payload: dict) -> dict:
    """根据报表类型查询数据，返回 {columns, rows, title}。

    payload.report_type 取值：candidate / experiment / equipment / sample。
    按当前租户过滤（equipment 表无 tenant_id 列除外）。
    """
    report_type = payload.get("report_type")
    if report_type not in REPORT_TYPES:
        raise ValueError(f"不支持的报表类型: {report_type}")
    spec = REPORT_TYPES[report_type]
    keys = [c["key"] for c in spec["columns"]]
    select = ", ".join(keys)
    sql = f"SELECT {select} FROM {spec['table']}"
    params: dict[str, Any] = {}
    if spec.get("tenant_scoped"):
        sql += f" WHERE {tenant_filter()}"
        params["tenant_id"] = get_tenant()
    with get_engine().connect() as conn:
        fetched = conn.execute(text(sql), params).fetchall()
    rows = [
        {key: _normalize(value) for key, value in zip(keys, row)}
        for row in fetched
    ]
    return {"columns": spec["columns"], "rows": rows, "title": spec["title"]}


def export_excel(rows: list[dict], columns: list[dict]) -> bytes:
    """用 openpyxl 生成 .xlsx，columns 为 [{key, title}]。返回字节。"""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    wb = Workbook()
    ws = wb.active
    ws.title = "report"
    ws.append([c["title"] for c in columns])
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="D9E1F2")
    for row in rows:
        ws.append([_normalize(row.get(c["key"])) for c in columns])
    bio = BytesIO()
    wb.save(bio)
    bio.seek(0)
    return bio.getvalue()


def _pdf_cell(value: Any) -> str:
    """将单元格值转为 PDF 可显示的字符串。"""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def export_pdf(rows: list[dict], columns: list[dict], title: str) -> bytes:
    """用 reportlab Platypus SimpleDocTemplate + Table 生成 PDF。返回字节。"""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    bio = BytesIO()
    doc = SimpleDocTemplate(bio, pagesize=landscape(A4), title=title)
    styles = getSampleStyleSheet()
    story = [Paragraph(title, styles["Title"]), Spacer(1, 8)]

    header = [c["title"] for c in columns]
    data = [header] + [
        [_pdf_cell(row.get(c["key"])) for c in columns] for row in rows
    ]
    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#D9E1F2")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F2F2")]),
    ]))
    story.append(table)
    doc.build(story)
    bio.seek(0)
    return bio.getvalue()


# 定时报表导出产物落盘目录（相对包根目录，含租户子目录）。
_EXPORT_ROOT = Path(__file__).resolve().parents[1] / "evals" / "reports" / "scheduled"

# 调度时区（业务统一使用本地时区）。
_TZ = "Asia/Shanghai"

# 全局 APScheduler 调度器：任务持久化于 PostgreSQL（apscheduler_jobs 表），
# 进程重启后由 SQLAlchemyJobStore 自动恢复并继续调度。
_scheduler: BackgroundScheduler | None = None


def _get_scheduler() -> BackgroundScheduler:
    """惰性创建全局 APScheduler 实例（复用项目统一数据库引擎）。"""
    global _scheduler
    if _scheduler is None:
        _scheduler = BackgroundScheduler(
            timezone=_TZ,
            jobstores={"default": SQLAlchemyJobStore(engine=get_engine())},
            job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 3600},
        )
    return _scheduler


def start_report_scheduler() -> None:
    """启动全局调度器（幂等）。SQLAlchemyJobStore 首次启动自动建表。"""
    sched = _get_scheduler()
    if not sched.running:
        sched.start()
        logger.info("报表定时调度器已启动（APScheduler + PostgreSQL 持久化）")


def _build_trigger(cron_expr: str) -> CronTrigger:
    """将完整 cron 表达式（5/6 段标准语法）解析为 APScheduler 触发器。

    仅支持标准 cron，非法表达式抛 ValueError。
    """
    expr = (cron_expr or "").strip()
    if not expr:
        raise ValueError("cron 表达式不能为空")
    try:
        return CronTrigger.from_crontab(expr, timezone=_TZ)
    except ValueError as e:
        raise ValueError(f"无效的 cron 表达式: {cron_expr}") from e


def _export_dir(tenant_id: str) -> Path:
    """返回指定租户的报表导出目录，并确保存在。"""
    # 租户 ID 作为目录名，需净化，防止路径注入
    safe = "".join(c for c in (tenant_id or "default") if c.isalnum() or c in "-_")
    d = _EXPORT_ROOT / (safe or "default")
    d.mkdir(parents=True, exist_ok=True)
    return d


def _persist_export(
    tenant_id: str, report_type: str, content: bytes, ext: str
) -> str:
    """将导出字节写入磁盘，返回相对可读路径。"""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"{report_type}_{ts}.{ext}"
    full = _export_dir(tenant_id) / filename
    with open(full, "wb") as f:
        f.write(content)
    return full.name


def schedule_report(payload: dict) -> dict:
    """注册一个持久化定时报表，返回调度结果（含 next_run）。"""
    report_type = payload.get("report_type")
    fmt = payload.get("format")
    if report_type not in REPORT_TYPES:
        raise ValueError(f"不支持的报表类型: {report_type}")
    if fmt not in VALID_FORMATS:
        raise ValueError(f"不支持的导出格式: {fmt}")
    cron = payload.get("cron_expr", "0 8 * * *")
    owner = payload.get("owner", "system")
    tenant_id = payload.get("tenant_id") or get_tenant()
    trigger = _build_trigger(cron)

    report_id = uuid.uuid4().hex[:12]
    sched = _get_scheduler()
    sched.add_job(
        _execute_scheduled,
        trigger=trigger,
        args=[report_type, fmt, owner, tenant_id, report_id],
        id=report_id,
        replace_existing=True,
    )
    job = sched.get_job(report_id)
    return {
        "report_id": report_id,
        "report_type": report_type,
        "format": fmt,
        "cron_expr": cron,
        "next_run": job.next_run_time.isoformat() if job.next_run_time else "",
        "last_run": "",
        "enabled": True,
        "owner": owner,
        "tenant_id": tenant_id,
    }


def _execute_scheduled(
    report_type: str, fmt: str, owner: str, tenant_id: str, report_id: str
) -> None:
    """执行一次报表：生成数据 → 落盘 → 写审计。

    由 APScheduler 在独立线程中调用，须显式 set_tenant() 以复现注册时的租户隔离。
    该函数必须保持模块级顶层可 pickle，供 SQLAlchemyJobStore 持久化。
    """
    from ..audit import AuditEntry, get_audit_logger

    set_tenant(tenant_id)
    data = build_report({"report_type": report_type})
    if fmt == "excel":
        content = export_excel(data["rows"], data["columns"])
        ext = "xlsx"
    else:
        content = export_pdf(data["rows"], data["columns"], data["title"])
        ext = "pdf"
    filename = _persist_export(tenant_id, report_type, content, ext)
    get_audit_logger().log(AuditEntry(
        event_type="data_change",
        module="report",
        action="scheduled_export",
        operator=owner,
        user_id=owner,
        resource_type="report",
        resource_id=f"{report_type}:{fmt}",
        detail={
            "report_id": report_id,
            "tenant_id": tenant_id,
            "file": filename,
            "rows": len(data["rows"]),
        },
    ))