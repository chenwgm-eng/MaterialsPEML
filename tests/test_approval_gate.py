"""测试实验审批门。"""

import pytest
from battery_materials_agent.experiment.approval import ApprovalEngine
from battery_materials_agent.experiment.experiment_controller import (
    ApprovalRule,
    ApprovalDecision,
)


@pytest.fixture
def engine():
    return ApprovalEngine()


def test_low_cost_auto_approve(engine):
    """低成本、高置信度自动放行。"""
    decision = engine.judge(
        {"formula": "LiCoO2"},
        estimated_cost=100.0,
        model_confidence=0.95,
    )
    assert decision.action == "AUTO_APPROVE"
    assert len(decision.risk_factors) == 0


def test_high_cost_requires_manual(engine):
    """高成本需人工审批。"""
    decision = engine.judge(
        {"formula": "LiCoO2"},
        estimated_cost=10000.0,
        model_confidence=0.95,
    )
    assert decision.action == "REQUIRE_MANUAL"
    assert any("成本" in r for r in decision.risk_factors)


def test_hazardous_material_requires_manual(engine):
    """危险化学品需人工审批。"""
    decision = engine.judge(
        {"formula": "硝基化合物", "smiles": "[N+](=O)[O-]"},
        estimated_cost=100.0,
        model_confidence=0.95,
    )
    assert decision.action == "REQUIRE_MANUAL"
    assert decision.is_hazardous is True


def test_low_confidence_requires_manual(engine):
    """低模型置信度需人工审批。"""
    decision = engine.judge(
        {"formula": "LiCoO2"},
        estimated_cost=100.0,
        model_confidence=0.3,
    )
    assert decision.action == "REQUIRE_MANUAL"
    assert any("置信度" in r for r in decision.risk_factors)


def test_multiple_risk_factors(engine):
    """多重风险因素组合。"""
    decision = engine.judge(
        {"formula": "硝基化合物"},
        estimated_cost=10000.0,
        model_confidence=0.3,
    )
    assert decision.action == "REQUIRE_MANUAL"
    assert len(decision.risk_factors) >= 3


def test_default_rules_exist(engine):
    """默认审批规则存在。"""
    rules = engine.list_rules()
    assert len(rules) >= 4
    rule_ids = [r.rule_id for r in rules]
    assert "R001" in rule_ids
    assert "R002" in rule_ids
    assert "R003" in rule_ids
    assert "R004" in rule_ids


def test_add_custom_rule(engine):
    """添加自定义规则。"""
    rule = ApprovalRule(
        rule_id="R_CUSTOM",
        rule_name="自定义规则",
        condition_field="cost",
        operator=">",
        threshold=100000.0,
        action="BLOCK",
    )
    engine.add_rule(rule)
    rules = engine.list_rules()
    assert any(r.rule_id == "R_CUSTOM" for r in rules)
