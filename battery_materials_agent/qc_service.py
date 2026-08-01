"""统一 QC 服务入口（Task 12.5）。

合并 `data_ingest/quality.py` 与 `middleware/wet_data/quality.py` 两套独立 QC 实现：
- 对外暴露 `check_record()` / `get_qc_engine()` / `write_audit_log()` 统一 API。
- 内部委托给 `middleware/wet_data/quality.py` 的 QCEngine / Checker 实现。
- `data_ingest/quality.py` 标记为 deprecated，新代码统一走本模块。

审计日志（Task 12.4）：
- `write_audit_log(result_id, qc_result)` 把完整规则快照写入 audit.qc_decisions 表。
- 调用方应在 QCEngine.check() 之后调用本函数；DB 不可用时静默失败不阻塞 QC 主流程。
"""
from __future__ import annotations

import json
import logging
from typing import Any

from .experiment.experiment_controller import ExperimentResultRecord
from .middleware.wet_data.quality import (
    CompletenessChecker,
    PlausibilityChecker,
    QCEngine,
    QCRuleResult,
    QCResult,
    SampleMatcher,
    load_qc_config,
)

logger = logging.getLogger(__name__)

# 单例 QCEngine（首次访问时加载 config/qc_rules.yaml）
_default_engine: QCEngine | None = None


def get_qc_engine() -> QCEngine:
    """获取统一 QC 引擎单例。"""
    global _default_engine
    if _default_engine is None:
        _default_engine = QCEngine()
    return _default_engine


def reset_qc_engine() -> None:
    """重置单例（测试用）。"""
    global _default_engine
    _default_engine = None


def check_record(record: ExperimentResultRecord,
                 valid_sample_ids: list[str] | None = None) -> QCResult:
    """统一 QC 检查入口。

    委托给 middleware/wet_data/quality.py 的 QCEngine，返回包含
    rule_results / decision_path / rule_version 等可解释字段的 QCResult。
    """
    return get_qc_engine().check(record, valid_sample_ids=valid_sample_ids)


def write_audit_log(result_id: str, qc_result: QCResult) -> bool:
    """把 QC 决策快照写入 audit.qc_decisions 审计表。

    Args:
        result_id: 关联的实验结果记录 ID（可能为空字符串）。
        qc_result: QCEngine.check() 返回的 QCResult。

    Returns:
        True 表示写入成功；False 表示写入失败（已静默捕获异常）。
    """
    snapshot: dict[str, Any] = {
        "qc_status": qc_result.qc_status,
        "issues": qc_result.issues,
        "decision_path": qc_result.decision_path,
        "severity": qc_result.severity,
        "confidence": qc_result.confidence,
        "completeness_score": qc_result.completeness_score,
        "learning_eligible": qc_result.learning_eligible,
        "rule_results": [r.to_dict() for r in qc_result.rule_results],
    }
    try:
        from sqlalchemy import text

        from .db import get_engine

        engine = get_engine()
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO audit.qc_decisions
                        (result_id, rule_version, decision_snapshot)
                    VALUES
                        (:result_id, :rule_version, CAST(:snapshot AS JSONB))
                    """
                ),
                {
                    "result_id": result_id or None,
                    "rule_version": qc_result.rule_version,
                    "snapshot": json.dumps(snapshot, ensure_ascii=False),
                },
            )
        return True
    except Exception as e:  # pragma: no cover - 审计日志失败不阻塞 QC
        logger.warning("QC 审计日志写入失败 (result_id=%s): %s", result_id, e)
        return False


def check_and_audit(record: ExperimentResultRecord,
                    valid_sample_ids: list[str] | None = None,
                    result_id: str | None = None) -> QCResult:
    """一站式：执行 QC 检查并写入审计日志。

    result_id 不传时使用 record.result_id。
    """
    qc_result = check_record(record, valid_sample_ids=valid_sample_ids)
    rid = result_id or record.result_id
    write_audit_log(rid, qc_result)
    return qc_result


__all__ = [
    "CompletenessChecker",
    "PlausibilityChecker",
    "QCEngine",
    "QCRuleResult",
    "QCResult",
    "SampleMatcher",
    "check_and_audit",
    "check_record",
    "get_qc_engine",
    "load_qc_config",
    "reset_qc_engine",
    "write_audit_log",
]
