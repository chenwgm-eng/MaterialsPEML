"""Task 12：QC 可解释化单元测试。

不依赖 DB（避开 Task 14 引入的 fk_results_order 外键约束），
仅验证：
- QCResult 新增 7 个可解释字段
- QCRuleResult 数据类
- 每个 Checker 输出 List[QCRuleResult]
- config/qc_rules.yaml 加载
- qc_service 统一入口
- alembic 迁移文件存在且版本号正确
"""
from __future__ import annotations

import inspect
import os
from dataclasses import fields as dataclass_fields
from pathlib import Path

import pytest

from battery_materials_agent.experiment.experiment_controller import (
    ExperimentResultRecord,
)
from battery_materials_agent.middleware.wet_data.quality import (
    CompletenessChecker,
    PlausibilityChecker,
    QCResult,
    QCRuleResult,
    QCEngine,
    SampleMatcher,
    load_qc_config,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


# ───────────────────────── Task 12.1: QCResult 新增字段 ─────────────────────────


def test_qc_result_new_fields_exist():
    """QCResult 必须包含 7 个新增可解释字段。"""
    new_fields = {
        "rule_id", "rule_version", "rule_category",
        "severity", "suggested_action", "decision_path", "confidence",
    }
    model_fields = set(QCResult.model_fields.keys())
    missing = new_fields - model_fields
    assert not missing, f"QCResult 缺少新增字段: {missing}"


def test_qc_result_preserves_existing_fields():
    """QCResult 必须保留所有原字段（向后兼容）。"""
    existing_fields = {
        "qc_status", "issues", "learning_eligible", "completeness_score",
    }
    model_fields = set(QCResult.model_fields.keys())
    missing = existing_fields - model_fields
    assert not missing, f"QCResult 缺少原字段: {missing}"


def test_qc_result_default_values():
    """QCResult 新增字段默认值应当合理。"""
    r = QCResult()
    assert r.rule_id == ""
    assert r.rule_version == ""
    assert r.rule_category == ""
    assert r.severity == "info"
    assert r.suggested_action == ""
    assert r.decision_path == ""
    assert r.confidence == 1.0
    assert r.rule_results == []


# ───────────────────────── Task 12.2: QCRuleResult 数据类 ─────────────────────────


def test_qc_rule_result_is_dataclass():
    """QCRuleResult 必须是 dataclass。"""
    import dataclasses
    assert dataclasses.is_dataclass(QCRuleResult)


def test_qc_rule_result_fields():
    """QCRuleResult 必须包含 spec 要求的所有字段。"""
    expected_fields = {
        "rule_id", "rule_version", "rule_category", "severity",
        "passed", "message", "suggested_action", "decision_path",
        "confidence", "field_name", "expected_value", "actual_value",
    }
    actual_fields = {f.name for f in dataclass_fields(QCRuleResult)}
    assert expected_fields == actual_fields, f"字段不匹配: 缺少 {expected_fields - actual_fields}"


def test_qc_rule_result_to_dict():
    """QCRuleResult.to_dict() 应当返回完整 dict。"""
    r = QCRuleResult(
        rule_id="test.rule",
        rule_version="1.0.0",
        rule_category="completeness",
        severity="error",
        passed=False,
        message="测试消息",
        suggested_action="测试动作",
        decision_path="test.path",
        confidence=0.5,
        field_name="sample_id",
    )
    d = r.to_dict()
    assert d["rule_id"] == "test.rule"
    assert d["passed"] is False
    assert d["field_name"] == "sample_id"
    assert d["expected_value"] is None


# ───────────────────────── Task 12.2: Checker 输出 List[QCRuleResult] ─────────────────────────


def _valid_record() -> ExperimentResultRecord:
    return ExperimentResultRecord(
        result_id="R_VALID",
        experiment_order_id="EO_001",
        sample_id="SMP_001",
        property_name="ionic_conductivity",
        value=0.005,
        unit="S/cm",
    )


def _invalid_record() -> ExperimentResultRecord:
    return ExperimentResultRecord(
        result_id="R_INVALID",
        sample_id="",
        property_name="ionic_conductivity",
        value=999999.0,
        unit="S/cm",
    )


def test_completeness_checker_outputs_rule_results():
    """CompletenessChecker.check_rules() 必须返回 List[QCRuleResult]。"""
    checker = CompletenessChecker()
    results = checker.check_rules(_valid_record())
    assert isinstance(results, list)
    assert all(isinstance(r, QCRuleResult) for r in results)
    assert len(results) == 4  # property_name / value / unit / sample_id
    assert all(r.passed for r in results)  # 全部通过


def test_completeness_checker_detects_missing():
    """CompletenessChecker 检测到缺失字段时应有未通过规则。"""
    checker = CompletenessChecker()
    record = ExperimentResultRecord(
        result_id="R_MISS",
        sample_id="",
        property_name="ionic_conductivity",
        value=0.005,
        unit="S/cm",
    )
    results = checker.check_rules(record)
    failed = [r for r in results if not r.passed]
    assert len(failed) == 1
    assert failed[0].field_name == "sample_id"
    assert failed[0].severity == "critical"
    assert "sample_id" in failed[0].message


def test_completeness_checker_backward_compat():
    """原 check() 方法仍返回 list[str]（向后兼容）。"""
    checker = CompletenessChecker()
    issues = checker.check(_valid_record())
    assert isinstance(issues, list)
    assert all(isinstance(i, str) for i in issues)
    assert issues == []  # 有效记录无 issue


def test_plausibility_checker_outputs_rule_results():
    """PlausibilityChecker.check_rules() 必须返回 List[QCRuleResult]。"""
    checker = PlausibilityChecker()
    results = checker.check_rules(_valid_record())
    assert isinstance(results, list)
    assert all(isinstance(r, QCRuleResult) for r in results)
    assert len(results) == 1
    assert results[0].passed
    assert results[0].rule_id == "plausibility.range.ionic_conductivity"
    assert results[0].expected_value == "[1e-10, 100.0]"


def test_plausibility_checker_detects_out_of_range():
    """PlausibilityChecker 检测到超出范围时有未通过规则。"""
    checker = PlausibilityChecker()
    results = checker.check_rules(_invalid_record())
    failed = [r for r in results if not r.passed]
    assert len(failed) == 1
    assert "超出" in failed[0].message
    assert failed[0].severity == "error"


def test_plausibility_checker_generic_range():
    """未在 RANGES 中的属性使用 generic 范围。"""
    checker = PlausibilityChecker()
    record = ExperimentResultRecord(
        result_id="R_GEN",
        sample_id="S1",
        property_name="unknown_property",
        value=42.0,
        unit="x",
    )
    results = checker.check_rules(record)
    assert len(results) == 1
    assert results[0].rule_id == "plausibility.range.generic"
    assert results[0].severity == "warning"


def test_plausibility_checker_backward_compat():
    """原 check() 方法仍返回 list[str]（向后兼容）。"""
    checker = PlausibilityChecker()
    issues = checker.check(_valid_record())
    assert isinstance(issues, list)
    assert all(isinstance(i, str) for i in issues)
    assert issues == []


def test_sample_matcher_outputs_rule_results():
    """SampleMatcher.check_rules() 必须返回 List[QCRuleResult]。"""
    checker = SampleMatcher()
    results = checker.check_rules(_valid_record(), valid_sample_ids=["SMP_001"])
    assert isinstance(results, list)
    assert all(isinstance(r, QCRuleResult) for r in results)
    # 两条规则：not_empty + in_valid_list
    assert len(results) == 2
    assert all(r.passed for r in results)


def test_sample_matcher_detects_empty():
    """SampleMatcher 检测到空 sample_id 时有未通过规则。"""
    checker = SampleMatcher()
    record = ExperimentResultRecord(
        result_id="R_EMPTY",
        sample_id="",
        property_name="ionic_conductivity",
        value=0.005,
        unit="S/cm",
    )
    results = checker.check_rules(record)
    failed = [r for r in results if not r.passed]
    assert len(failed) == 1
    assert failed[0].rule_id == "sample_match.not_empty"
    assert failed[0].severity == "critical"


def test_sample_matcher_detects_not_in_list():
    """SampleMatcher 检测到不在有效列表时有未通过规则。"""
    checker = SampleMatcher()
    record = ExperimentResultRecord(
        result_id="R_NOT_IN_LIST",
        sample_id="UNKNOWN_ID",
        property_name="ionic_conductivity",
        value=0.005,
        unit="S/cm",
    )
    results = checker.check_rules(record, valid_sample_ids=["SMP_001"])
    failed = [r for r in results if not r.passed]
    assert len(failed) == 1
    assert failed[0].rule_id == "sample_match.in_valid_list"


def test_sample_matcher_backward_compat():
    """原 check() 方法仍返回 list[str]（向后兼容）。"""
    checker = SampleMatcher()
    issues = checker.check(_valid_record(), valid_sample_ids=["SMP_001"])
    assert isinstance(issues, list)
    assert all(isinstance(i, str) for i in issues)
    assert issues == []


# ───────────────────────── Task 12.2: QCEngine 聚合 ─────────────────────────


def test_qc_engine_valid_record():
    """QCEngine 对有效记录返回 VALID 状态。"""
    engine = QCEngine()
    result = engine.check(_valid_record())
    assert result.qc_status == "VALID"
    assert result.learning_eligible is True
    assert len(result.rule_results) == 6  # 4 完整性 + 1 合理性 + 1 样品
    assert all(r.passed for r in result.rule_results)
    assert result.decision_path == "all_passed"
    assert result.severity == "info"


def test_qc_engine_invalid_record():
    """QCEngine 对无效记录返回 INVALID 状态及结构化规则结果。"""
    engine = QCEngine()
    result = engine.check(_invalid_record())
    assert result.qc_status == "INVALID"
    assert len(result.rule_results) == 6
    failed = [r for r in result.rule_results if not r.passed]
    assert len(failed) == 3  # 缺 sample_id / 超范围 / sample_id 为空
    # 主规则是首个失败规则
    assert result.rule_id == failed[0].rule_id
    assert result.severity == "critical"
    assert "completeness" in result.decision_path
    assert "plausibility" in result.decision_path
    assert "sample_match" in result.decision_path


def test_qc_engine_rule_version_from_yaml():
    """QCEngine.rule_version 应当从 config/qc_rules.yaml 加载。"""
    engine = QCEngine()
    assert engine.rule_version == "1.0.0"
    result = engine.check(_valid_record())
    assert result.rule_version == "1.0.0"
    # 每条 rule_result 也带版本
    assert all(r.rule_version == "1.0.0" for r in result.rule_results)


def test_qc_engine_confidence():
    """QCEngine.confidence 是所有规则的最小值。"""
    engine = QCEngine()
    valid_result = engine.check(_valid_record())
    # 全部通过：confidence = min(1.0, 1.0, 1.0, 1.0, 1.0, 1.0) = 1.0
    assert valid_result.confidence == 1.0


def test_qc_engine_backward_compat():
    """QCEngine.check() 返回的 QCResult.issues 仍是 list[str]。"""
    engine = QCEngine()
    result = engine.check(_valid_record())
    assert isinstance(result.issues, list)
    assert all(isinstance(i, str) for i in result.issues)


# ───────────────────────── Task 12.3: config/qc_rules.yaml ─────────────────────────


def test_qc_rules_yaml_exists():
    """config/qc_rules.yaml 必须存在。"""
    yaml_path = PROJECT_ROOT / "config" / "qc_rules.yaml"
    assert yaml_path.exists(), f"qc_rules.yaml 不存在: {yaml_path}"


def test_load_qc_config_structure():
    """load_qc_config() 返回的结构正确。"""
    config = load_qc_config()
    assert "version" in config
    assert "rules" in config
    rules = config["rules"]
    assert "completeness" in rules
    assert "plausibility" in rules
    assert "sample_match" in rules


def test_load_qc_config_ranges():
    """config/qc_rules.yaml 中的 plausibility.ranges 与默认值一致。"""
    config = load_qc_config()
    ranges = config["rules"]["plausibility"]["ranges"]
    # ionic_conductivity 在 yaml 中应有配置
    assert "ionic_conductivity" in ranges
    ic = ranges["ionic_conductivity"]
    assert float(ic["min"]) == 1e-10
    assert float(ic["max"]) == 1e2
    assert ic["severity"] == "error"
    assert ic["suggested_action"]


def test_load_qc_config_completeness():
    """config/qc_rules.yaml 中的 completeness.required_fields 配置。"""
    config = load_qc_config()
    required = config["rules"]["completeness"]["required_fields"]
    field_names = [c["field"] for c in required]
    assert "property_name" in field_names
    assert "value" in field_names
    assert "unit" in field_names
    assert "sample_id" in field_names
    # 每个字段都有 severity
    for c in required:
        assert c["severity"]


def test_load_qc_config_fallback():
    """load_qc_config 在文件不存在时回退到内置默认值。"""
    config = load_qc_config("/nonexistent/path/qc_rules.yaml")
    assert "version" in config
    assert "rules" in config


# ───────────────────────── Task 12.4: alembic 迁移 ─────────────────────────


def test_alembic_migration_0003_exists():
    """alembic 迁移 0003_qc_decisions.py 必须存在。"""
    migration_path = PROJECT_ROOT / "alembic" / "versions" / "0003_qc_decisions.py"
    assert migration_path.exists(), f"迁移文件不存在: {migration_path}"


def test_alembic_migration_0003_revision():
    """迁移文件 revision 必须为 0003_qc_decisions。"""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "migration_0003",
        PROJECT_ROOT / "alembic" / "versions" / "0003_qc_decisions.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.revision == "0003_qc_decisions"
    assert module.down_revision == "0002_order_status_transitions"


def test_alembic_migration_0003_has_upgrade_downgrade():
    """迁移文件必须定义 upgrade 和 downgrade 函数。"""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "migration_0003",
        PROJECT_ROOT / "alembic" / "versions" / "0003_qc_decisions.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert callable(module.upgrade)
    assert callable(module.downgrade)


# ───────────────────────── Task 12.5: qc_service 统一入口 ─────────────────────────


def test_qc_service_module_exists():
    """battery_materials_agent/qc_service.py 必须存在。"""
    from battery_materials_agent import qc_service
    assert hasattr(qc_service, "check_record")
    assert hasattr(qc_service, "get_qc_engine")
    assert hasattr(qc_service, "write_audit_log")
    assert hasattr(qc_service, "check_and_audit")


def test_qc_service_check_record():
    """qc_service.check_record() 是统一入口，返回 QCResult。"""
    from battery_materials_agent import qc_service
    result = qc_service.check_record(_valid_record())
    assert isinstance(result, QCResult)
    assert result.qc_status == "VALID"
    assert len(result.rule_results) == 6


def test_qc_service_get_qc_engine_singleton():
    """qc_service.get_qc_engine() 返回单例。"""
    from battery_materials_agent import qc_service
    qc_service.reset_qc_engine()
    engine1 = qc_service.get_qc_engine()
    engine2 = qc_service.get_qc_engine()
    assert engine1 is engine2


def test_qc_service_write_audit_log_signature():
    """write_audit_log 函数签名应包含 result_id 与 qc_result 参数。"""
    from battery_materials_agent import qc_service
    sig = inspect.signature(qc_service.write_audit_log)
    params = set(sig.parameters.keys())
    assert "result_id" in params
    assert "qc_result" in params


def test_qc_service_exports():
    """qc_service 应导出 QCEngine / QCResult / QCRuleResult / Checkers。"""
    from battery_materials_agent import qc_service
    assert qc_service.QCEngine is QCEngine
    assert qc_service.QCResult is QCResult
    assert qc_service.QCRuleResult is QCRuleResult
    assert qc_service.CompletenessChecker is CompletenessChecker
    assert qc_service.PlausibilityChecker is PlausibilityChecker
    assert qc_service.SampleMatcher is SampleMatcher


def test_data_ingest_quality_deprecated():
    """data_ingest/quality.py 必须标记为 deprecated。"""
    import warnings
    src_path = PROJECT_ROOT / "battery_materials_agent" / "data_ingest" / "quality.py"
    src = src_path.read_text(encoding="utf-8")
    assert "deprecated" in src.lower()
    # 调用 check_quality 时应发出 DeprecationWarning
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        from battery_materials_agent.data_ingest.quality import check_quality
        try:
            check_quality([], {}, "sample")
        except Exception:
            pass
        deprecation_warnings = [w for w in caught if issubclass(w.category, DeprecationWarning)]
        assert deprecation_warnings, "check_quality 应发出 DeprecationWarning"


# ───────────────────────── 集成：端到端可解释性 ─────────────────────────


def test_qc_explainability_end_to_end():
    """端到端：QC 判定无效时返回完整可解释字段。"""
    engine = QCEngine()
    record = ExperimentResultRecord(
        result_id="R_EXPLAIN",
        sample_id="",
        property_name="ionic_conductivity",
        value=999999.0,
        unit="S/cm",
    )
    result = engine.check(record)

    # 用户能从结果中知道"为什么 QC 判定无效"
    assert result.qc_status == "INVALID"
    assert result.rule_id  # 主规则 ID 非空
    assert result.rule_version  # 规则版本非空
    assert result.rule_category  # 规则类别非空
    assert result.severity in ("info", "warning", "error", "critical")
    assert result.suggested_action  # 建议动作非空
    assert result.decision_path  # 决策路径非空
    assert 0.0 <= result.confidence <= 1.0
    assert len(result.rule_results) > 0
    # 至少有一条未通过规则
    failed_rules = [r for r in result.rule_results if not r.passed]
    assert failed_rules
    # 每条规则都有 rule_id / severity / message / suggested_action
    for rule in failed_rules:
        assert rule.rule_id
        assert rule.severity in ("info", "warning", "error", "critical")
        assert rule.message
        assert rule.decision_path


def test_qc_explainability_serializable():
    """QCResult 必须可被 model_dump() 序列化为 JSON 兼容 dict。"""
    import json
    engine = QCEngine()
    result = engine.check(_invalid_record())
    dumped = result.model_dump()
    # 必须可 JSON 序列化（前端 API 传输）
    json_str = json.dumps(dumped, ensure_ascii=False, default=str)
    assert "rule_results" in json_str
    assert "rule_id" in json_str
    assert "decision_path" in json_str
    assert "rule_version" in json_str
