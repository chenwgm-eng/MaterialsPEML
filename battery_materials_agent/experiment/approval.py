"""实验审批门 - 基于成本/EHS/合规的自动/人工审批决策。"""

from __future__ import annotations
import logging
from .experiment_controller import ApprovalRule, ApprovalDecision

logger = logging.getLogger(__name__)


class ApprovalEngine:
    """实验审批引擎。"""

    def __init__(self, config=None):
        self.cost_threshold = 5000.0  # 单次实验成本阈值（元）
        self.confidence_threshold = 0.7  # 模型置信度阈值
        self.hazardous_keywords = ["硝基", "硝酸", "叠氮", "过氧", "高氯", "氟化", "氰化", "放射性"]
        self._rules: list[ApprovalRule] = []
        self._init_default_rules()

    def _init_default_rules(self):
        """初始化默认审批规则。"""
        self._rules = [
            ApprovalRule(
                rule_id="R001",
                rule_name="高成本实验需人工审批",
                condition_field="cost",
                operator=">",
                threshold=self.cost_threshold,
                action="REQUIRE_MANUAL",
                description=f"单次实验成本超过 {self.cost_threshold} 元需人工审批",
            ),
            ApprovalRule(
                rule_id="R002",
                rule_name="危险化学品需人工审批",
                condition_field="is_hazardous",
                operator="==",
                threshold=1.0,
                action="REQUIRE_MANUAL",
                description="涉及危险化学品/工艺的实验需人工审批",
            ),
            ApprovalRule(
                rule_id="R003",
                rule_name="低模型置信度需人工审批",
                condition_field="model_confidence",
                operator="<",
                threshold=self.confidence_threshold,
                action="REQUIRE_MANUAL",
                description=f"模型置信度低于 {self.confidence_threshold} 需人工审批",
            ),
            ApprovalRule(
                rule_id="R004",
                rule_name="低成本低风险自动放行",
                condition_field="cost",
                operator="<",
                threshold=self.cost_threshold,
                action="AUTO_APPROVE",
                description="低成本、低风险实验自动放行",
            ),
        ]

    def judge(self, candidate: dict, estimated_cost: float = 0.0,
              model_confidence: float = 1.0) -> ApprovalDecision:
        """判断实验是否需要人工审批。"""
        matched_rules: list[str] = []
        risk_factors: list[str] = []

        # 检查候选是否涉及危险化学品
        is_hazardous = False
        candidate_str = str(candidate).lower()
        for keyword in self.hazardous_keywords:
            if keyword in candidate_str:
                is_hazardous = True
                risk_factors.append(f"涉及危险关键词：{keyword}")
                break

        # 检查成本
        if estimated_cost > self.cost_threshold:
            matched_rules.append("R001")
            risk_factors.append(f"实验成本 {estimated_cost:.2f} 元超过阈值 {self.cost_threshold} 元")

        # 检查危险品
        if is_hazardous:
            matched_rules.append("R002")

        # 检查模型置信度
        if model_confidence < self.confidence_threshold:
            matched_rules.append("R003")
            risk_factors.append(f"模型置信度 {model_confidence:.2f} 低于阈值 {self.confidence_threshold}")

        # 确定审批动作
        if any(rule_id in matched_rules for rule_id in ["R001", "R002", "R003"]):
            action = "REQUIRE_MANUAL"
        else:
            action = "AUTO_APPROVE"
            matched_rules.append("R004")

        return ApprovalDecision(
            action=action,
            matched_rules=matched_rules,
            risk_factors=risk_factors,
            estimated_cost=estimated_cost,
            is_hazardous=is_hazardous,
            model_confidence=model_confidence,
            notes="自动审批" if action == "AUTO_APPROVE" else "需人工审批",
        )

    def add_rule(self, rule: ApprovalRule):
        """添加自定义审批规则。"""
        self._rules.append(rule)

    def list_rules(self) -> list[ApprovalRule]:
        """列出所有审批规则。"""
        return self._rules
