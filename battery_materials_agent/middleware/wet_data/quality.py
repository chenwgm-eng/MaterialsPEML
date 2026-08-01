"""数据质量控制引擎。

Task 12：QC 可解释化重构
- QCResult 新增 7 个可解释字段（rule_id / rule_version / rule_category /
  severity / suggested_action / decision_path / confidence）并保留 rule_results
  规则结果列表，向后兼容 qc_status / issues / learning_eligible /
  completeness_score 字段。
- 每个 Checker 新增 check_rules() 方法输出 List[QCRuleResult]，原子规则可追溯；
  原 check() 保留向后兼容（内部转调 check_rules() 并取 message）。
- 规则配置从 config/qc_rules.yaml 加载，每次配置变更递增 version 号。
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ...experiment.experiment_controller import ExperimentResultRecord

logger = logging.getLogger(__name__)


# ───────────────────────── 默认配置（向后兼容兜底） ─────────────────────────
_DEFAULT_RANGES: dict[str, tuple[float, float]] = {
    "ionic_conductivity": (1e-10, 1e2),
    "band_gap": (0, 20),
    "formation_energy": (-10, 10),
    "electrochemical_window": (0, 10),
    "operating_voltage": (0, 10),
    "density": (0, 50),
    "melting_point": (-273, 5000),
    "boiling_point": (-273, 10000),
}

_DEFAULT_GENERIC_RANGE: tuple[float, float] = (-1e6, 1e6)

_DEFAULT_REQUIRED_FIELDS: list[str] = ["property_name", "value", "unit", "sample_id"]

_DEFAULT_RULE_VERSION = "1.0.0"


def _project_root() -> Path:
    """返回项目根目录（包含 config/qc_rules.yaml 的目录）。"""
    here = Path(__file__).resolve()
    # battery_materials_agent/middleware/wet_data/quality.py → 上 4 级
    return here.parents[3]


def _qc_config_path() -> Path:
    """返回 config/qc_rules.yaml 的路径。"""
    env_path = os.environ.get("QC_RULES_CONFIG", "")
    if env_path:
        return Path(env_path)
    return _project_root() / "config" / "qc_rules.yaml"


def load_qc_config(config_path: str | os.PathLike | None = None) -> dict[str, Any]:
    """加载 config/qc_rules.yaml。失败时回退到内置默认值。

    返回结构：
        {
            "version": "1.0.0",
            "rules": {
                "completeness": {"required_fields": [...]},
                "plausibility": {"ranges": {...}, "generic": {...}},
                "sample_match": {...},
            },
        }
    """
    path = Path(config_path) if config_path else _qc_config_path()
    try:
        import yaml  # type: ignore[import-untyped]

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        if not isinstance(data, dict) or "version" not in data:
            logger.warning("QC 规则配置 %s 结构异常，回退默认值", path)
            return _fallback_config()
        return data
    except FileNotFoundError:
        logger.info("QC 规则配置 %s 不存在，使用内置默认值", path)
    except Exception as e:  # pragma: no cover - 配置加载异常不应阻塞 QC
        logger.warning("QC 规则配置 %s 加载失败：%s，使用内置默认值", path, e)
    return _fallback_config()


def _fallback_config() -> dict[str, Any]:
    """内置默认配置（与原硬编码常量一致）。"""
    ranges_yaml: dict[str, dict[str, Any]] = {}
    for name, (lo, hi) in _DEFAULT_RANGES.items():
        ranges_yaml[name] = {
            "min": lo,
            "max": hi,
            "severity": "error",
            "suggested_action": "检查测量单位或重新测量",
        }
    return {
        "version": _DEFAULT_RULE_VERSION,
        "rules": {
            "completeness": {
                "required_fields": [
                    {"field": f, "severity": "critical", "suggested_action": f"请填写字段 {f}"}
                    for f in _DEFAULT_REQUIRED_FIELDS
                ],
            },
            "plausibility": {
                "ranges": ranges_yaml,
                "generic": {
                    "min": _DEFAULT_GENERIC_RANGE[0],
                    "max": _DEFAULT_GENERIC_RANGE[1],
                    "severity": "warning",
                    "suggested_action": "确认数值是否在合理范围",
                },
            },
            "sample_match": {
                "empty_severity": "critical",
                "empty_suggested_action": "请填写样品 ID",
                "missing_severity": "error",
                "missing_suggested_action": "请确认样品 ID 是否已登记",
            },
        },
    }


# ───────────────────────── QCRuleResult ─────────────────────────


@dataclass
class QCRuleResult:
    """原子 QC 规则结果。

    每个 Checker 把判定逻辑拆分为多条原子规则，每条规则输出一个 QCRuleResult。
    """

    rule_id: str
    rule_version: str
    rule_category: str  # completeness / plausibility / sample_match / consistency
    severity: str  # info / warning / error / critical
    passed: bool
    message: str
    suggested_action: str
    decision_path: str
    confidence: float
    field_name: str | None = None
    expected_value: str | None = None
    actual_value: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ───────────────────────── QCResult ─────────────────────────


class QCResult(BaseModel):
    """QC 检查结果。

    Task 12.1 新增字段（保留所有原字段不变）：
        rule_id / rule_version / rule_category / severity /
        suggested_action / decision_path / confidence
    Task 12.2 新增字段：rule_results（每条原子规则结果）
    """

    # ─────── 现有字段（保留不变，向后兼容） ───────
    qc_status: str = "PENDING"  # VALID / INVALID / REQUIRES_REVIEW
    issues: list[str] = Field(default_factory=list)
    learning_eligible: bool = False
    completeness_score: float = 1.0

    # ─────── Task 12.1 新增：可解释字段 ───────
    rule_id: str = ""  # 主规则 ID（首个失败规则，或全部通过时取首条规则 ID）
    rule_version: str = ""  # 规则版本号（来自 config/qc_rules.yaml）
    rule_category: str = ""  # 主规则类别（与 rule_id 对应）
    severity: str = "info"  # 主规则严重度：info / warning / error / critical
    suggested_action: str = ""  # 主规则建议动作
    decision_path: str = ""  # 决策路径（如 "completeness.check_required_fields -> plausibility.check_range"）
    confidence: float = 1.0  # 置信度 0.0-1.0

    # ─────── Task 12.2 新增：规则结果列表 ───────
    rule_results: list[QCRuleResult] = Field(default_factory=list)

    model_config = ConfigDict(arbitrary_types_allowed=True)


# ───────────────────────── Checkers ─────────────────────────


class CompletenessChecker:
    """必填字段完整性检查。

    Task 12.2：新增 check_rules() 输出 List[QCRuleResult]，原 check() 保留向后兼容。
    """

    DECISION_PATH = "completeness.check_required_fields"

    def __init__(self, required_fields: list[dict] | None = None,
                 rule_version: str = _DEFAULT_RULE_VERSION):
        if required_fields:
            self._fields_cfg = required_fields
            self.REQUIRED_FIELDS = [c["field"] for c in required_fields]
        else:
            self._fields_cfg = [
                {"field": f, "severity": "critical", "suggested_action": f"请填写字段 {f}"}
                for f in _DEFAULT_REQUIRED_FIELDS
            ]
            self.REQUIRED_FIELDS = list(_DEFAULT_REQUIRED_FIELDS)
        self._rule_version = rule_version

    def check_rules(self, record: ExperimentResultRecord) -> list[QCRuleResult]:
        results: list[QCRuleResult] = []
        for cfg in self._fields_cfg:
            field_name = cfg["field"]
            severity = cfg.get("severity", "critical")
            suggested = cfg.get("suggested_action", f"请填写字段 {field_name}")
            value = getattr(record, field_name, None)
            # P1-002 修复：value==0 是合法数值（如 0℃、0 V），不应判为缺失
            passed = value is not None and value != ""
            results.append(QCRuleResult(
                rule_id=f"completeness.required.{field_name}",
                rule_version=self._rule_version,
                rule_category="completeness",
                severity=severity,
                passed=passed,
                message="" if passed else f"缺失必填字段：{field_name}",
                suggested_action="" if passed else suggested,
                decision_path=self.DECISION_PATH,
                confidence=1.0 if passed else 0.0,
                field_name=field_name,
                actual_value=str(value) if value is not None else None,
            ))
        return results

    def check(self, record: ExperimentResultRecord) -> list[str]:
        """向后兼容：返回 issue 字符串列表。"""
        return [r.message for r in self.check_rules(record) if not r.passed]


class PlausibilityChecker:
    """数值范围合理性检查。

    Task 12.2：新增 check_rules() 输出 List[QCRuleResult]，原 check() 保留向后兼容。
    Task 12.3：RANGES 配置从 config/qc_rules.yaml 加载。
    """

    DECISION_PATH_KNOWN = "plausibility.check_range"
    DECISION_PATH_GENERIC = "plausibility.check_generic_range"

    def __init__(self, ranges_cfg: dict[str, dict] | None = None,
                 generic_cfg: dict[str, Any] | None = None,
                 rule_version: str = _DEFAULT_RULE_VERSION):
        # 兼容旧 API：允许直接传 (min, max) tuple dict
        if ranges_cfg is None:
            self.RANGES = dict(_DEFAULT_RANGES)
            self._ranges_cfg = {
                name: {"min": lo, "max": hi, "severity": "error",
                       "suggested_action": "检查测量单位或重新测量"}
                for name, (lo, hi) in _DEFAULT_RANGES.items()
            }
        else:
            self._ranges_cfg = ranges_cfg
            self.RANGES = {
                name: (float(c["min"]), float(c["max"]))
                for name, c in ranges_cfg.items()
            }
        self._generic_cfg = generic_cfg or {
            "min": _DEFAULT_GENERIC_RANGE[0],
            "max": _DEFAULT_GENERIC_RANGE[1],
            "severity": "warning",
            "suggested_action": "确认数值是否在合理范围",
        }
        self._rule_version = rule_version

    def check_rules(self, record: ExperimentResultRecord) -> list[QCRuleResult]:
        results: list[QCRuleResult] = []
        prop = record.property_name
        value = record.value

        if prop in self._ranges_cfg:
            cfg = self._ranges_cfg[prop]
            lo = float(cfg["min"])
            hi = float(cfg["max"])
            severity = cfg.get("severity", "error")
            suggested = cfg.get("suggested_action", "检查测量单位或重新测量")
            passed = lo <= value <= hi
            results.append(QCRuleResult(
                rule_id=f"plausibility.range.{prop}",
                rule_version=self._rule_version,
                rule_category="plausibility",
                severity=severity,
                passed=passed,
                message="" if passed else f"数值 {value} 超出 {prop} 合理范围 [{lo}, {hi}]",
                suggested_action="" if passed else suggested,
                decision_path=self.DECISION_PATH_KNOWN,
                confidence=1.0 if passed else 0.9,
                field_name=prop,
                expected_value=f"[{lo}, {hi}]",
                actual_value=str(value),
            ))
        else:
            cfg = self._generic_cfg
            lo = float(cfg["min"])
            hi = float(cfg["max"])
            severity = cfg.get("severity", "warning")
            suggested = cfg.get("suggested_action", "确认数值是否在合理范围")
            passed = lo <= value <= hi
            results.append(QCRuleResult(
                rule_id="plausibility.range.generic",
                rule_version=self._rule_version,
                rule_category="plausibility",
                severity=severity,
                passed=passed,
                message="" if passed else f"数值 {value} 超出通用合理范围",
                suggested_action="" if passed else suggested,
                decision_path=self.DECISION_PATH_GENERIC,
                confidence=0.8 if passed else 0.7,
                field_name=prop or "value",
                expected_value=f"[{lo}, {hi}]",
                actual_value=str(value),
            ))
        return results

    def check(self, record: ExperimentResultRecord) -> list[str]:
        """向后兼容：返回 issue 字符串列表。"""
        return [r.message for r in self.check_rules(record) if not r.passed]


class SampleMatcher:
    """样品 ID 关联校验。

    Task 12.2：新增 check_rules() 输出 List[QCRuleResult]，原 check() 保留向后兼容。
    """

    DECISION_PATH = "sample_match.check_id"

    def __init__(self,
                 empty_severity: str = "critical",
                 empty_suggested: str = "请填写样品 ID",
                 missing_severity: str = "error",
                 missing_suggested: str = "请确认样品 ID 是否已登记",
                 rule_version: str = _DEFAULT_RULE_VERSION):
        self._empty_severity = empty_severity
        self._empty_suggested = empty_suggested
        self._missing_severity = missing_severity
        self._missing_suggested = missing_suggested
        self._rule_version = rule_version

    def check_rules(self, record: ExperimentResultRecord,
                    valid_sample_ids: list[str] | None = None) -> list[QCRuleResult]:
        results: list[QCRuleResult] = []

        # 规则 1：样品 ID 非空
        empty_passed = bool(record.sample_id)
        results.append(QCRuleResult(
            rule_id="sample_match.not_empty",
            rule_version=self._rule_version,
            rule_category="sample_match",
            severity=self._empty_severity,
            passed=empty_passed,
            message="" if empty_passed else "样品 ID 为空",
            suggested_action="" if empty_passed else self._empty_suggested,
            decision_path=self.DECISION_PATH,
            confidence=1.0 if empty_passed else 0.0,
            field_name="sample_id",
            actual_value=record.sample_id or None,
        ))

        # 规则 2：样品 ID 在有效列表中（仅当传入 valid_sample_ids 时检查）
        if valid_sample_ids is not None:
            in_list = record.sample_id in valid_sample_ids
            missing_passed = bool(record.sample_id) and in_list
            results.append(QCRuleResult(
                rule_id="sample_match.in_valid_list",
                rule_version=self._rule_version,
                rule_category="sample_match",
                severity=self._missing_severity,
                passed=missing_passed,
                message="" if missing_passed else f"样品 ID {record.sample_id} 不在有效列表中",
                suggested_action="" if missing_passed else self._missing_suggested,
                decision_path=self.DECISION_PATH,
                confidence=0.9 if missing_passed else 0.5,
                field_name="sample_id",
                actual_value=record.sample_id or None,
            ))
        return results

    def check(self, record: ExperimentResultRecord,
              valid_sample_ids: list[str] | None = None) -> list[str]:
        """向后兼容：返回 issue 字符串列表。"""
        return [r.message for r in self.check_rules(record, valid_sample_ids) if not r.passed]


# ───────────────────────── QCEngine ─────────────────────────


class QCEngine:
    """QC 规则引擎。

    Task 12.2：内部委托各 Checker.check_rules()，聚合成 rule_results 列表，
    保留对外 QCResult 的 qc_status / issues 等字段语义不变。
    """

    def __init__(self, config: dict[str, Any] | None = None):
        if config is None:
            config = load_qc_config()
        self._config = config
        self.rule_version: str = str(config.get("version", _DEFAULT_RULE_VERSION))

        rules = config.get("rules", {}) if isinstance(config, dict) else {}

        # 完整性
        completeness_cfg = rules.get("completeness", {}) or {}
        required_fields = completeness_cfg.get("required_fields") or []

        # 合理性
        plaus_cfg = rules.get("plausibility", {}) or {}
        ranges_cfg = plaus_cfg.get("ranges") or {}
        generic_cfg = plaus_cfg.get("generic") or {}

        # 样品关联
        sample_cfg = rules.get("sample_match", {}) or {}

        self.completeness_checker = CompletenessChecker(
            required_fields=required_fields or None,
            rule_version=self.rule_version,
        )
        self.plausibility_checker = PlausibilityChecker(
            ranges_cfg=ranges_cfg or None,
            generic_cfg=generic_cfg or None,
            rule_version=self.rule_version,
        )
        self.sample_matcher = SampleMatcher(
            empty_severity=sample_cfg.get("empty_severity", "critical"),
            empty_suggested=sample_cfg.get("empty_suggested_action", "请填写样品 ID"),
            missing_severity=sample_cfg.get("missing_severity", "error"),
            missing_suggested=sample_cfg.get("missing_suggested_action",
                                             "请确认样品 ID 是否已登记"),
            rule_version=self.rule_version,
        )

    def check(self, record: ExperimentResultRecord,
              valid_sample_ids: list[str] | None = None) -> QCResult:
        rule_results: list[QCRuleResult] = []
        decision_steps: list[str] = []

        # 1. 完整性检查
        completeness_results = self.completeness_checker.check_rules(record)
        rule_results.extend(completeness_results)
        if any(not r.passed for r in completeness_results):
            decision_steps.append(self.completeness_checker.DECISION_PATH)

        # 2. 合理性检查
        plaus_results = self.plausibility_checker.check_rules(record)
        rule_results.extend(plaus_results)
        if any(not r.passed for r in plaus_results):
            decision_steps.append(plaus_results[0].decision_path)

        # 3. 样品关联检查
        sample_results = self.sample_matcher.check_rules(record, valid_sample_ids)
        rule_results.extend(sample_results)
        if any(not r.passed for r in sample_results):
            decision_steps.append(self.sample_matcher.DECISION_PATH)

        # 构建 issues 列表（向后兼容：取所有失败规则的 message）
        issues: list[str] = [r.message for r in rule_results if not r.passed]

        # 确定状态（保留原有判定语义）
        if not record.property_name or not record.sample_id:
            qc_status = "INVALID"
        elif issues:
            has_critical = any("缺失" in i or "超出" in i for i in issues)
            qc_status = "INVALID" if has_critical else "REQUIRES_REVIEW"
        else:
            qc_status = "VALID"

        # 评测修复 P0-001：learning_eligible 不能只由 qc_status 决定。
        # 进入学习闭环的数据必须具备完整溯源链：experiment_order_id 提供
        # 项目→任务单→候选关联，sample_id 提供样品关联（VALID 已隐含 sample_id 非空）。
        # 无任务单关联的数据即使 QC 通过也不允许直接进入学习闭环，
        # 需经人工审批（/qc/{id}/approve）确认溯源后放行。
        learning_eligible = (
            qc_status == "VALID"
            and bool((record.experiment_order_id or "").strip())
        )

        completeness = 1.0 - len(issues) * 0.1
        completeness = max(0.0, min(1.0, completeness))

        # 选取主规则（首个失败规则；全部通过时取首条规则）
        primary_rule = next((r for r in rule_results if not r.passed), None)
        if primary_rule is None and rule_results:
            primary_rule = rule_results[0]

        if primary_rule is not None:
            rule_id = primary_rule.rule_id
            rule_category = primary_rule.rule_category
            severity = primary_rule.severity if not primary_rule.passed else "info"
            suggested_action = primary_rule.suggested_action
        else:
            rule_id = ""
            rule_category = ""
            severity = "info"
            suggested_action = ""

        decision_path = " -> ".join(decision_steps) if decision_steps else "all_passed"

        # 置信度：所有规则置信度的最小值（最弱环节）
        confidence = min((r.confidence for r in rule_results), default=1.0)

        return QCResult(
            qc_status=qc_status,
            issues=issues,
            learning_eligible=learning_eligible,
            completeness_score=completeness,
            rule_id=rule_id,
            rule_version=self.rule_version,
            rule_category=rule_category,
            severity=severity,
            suggested_action=suggested_action,
            decision_path=decision_path,
            confidence=confidence,
            rule_results=rule_results,
        )
