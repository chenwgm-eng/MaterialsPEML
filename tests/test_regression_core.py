"""核心链路回归测试。"""

import pytest


def test_prediction_crystal_import():
    """预测模块可正常导入。"""
    from battery_materials_agent.prediction.crystal_property_predictor import CrystalPropertyPredictor
    assert CrystalPropertyPredictor is not None


def test_prediction_polymer_import():
    """聚合物预测模块可正常导入。"""
    from battery_materials_agent.prediction.polymer_property_predictor import PolymerPropertyPredictor
    assert PolymerPropertyPredictor is not None


def test_synthesis_planner_import():
    """合成路径规划模块可正常导入。"""
    from battery_materials_agent.synthesis.synthesis_planner import SynthesisPlanner
    assert SynthesisPlanner is not None


def test_ecml_engine_import():
    """ECML 引擎可正常导入。"""
    from battery_materials_agent.ecml.ecml_engine import ECMLEngine, ECMLStep
    assert ECMLStep.WAITING_FOR_DATA is not None


def test_experiment_controller_import():
    """实验控制器可正常导入。"""
    from battery_materials_agent.experiment.experiment_controller import ExperimentController, ExperimentOrder
    assert ExperimentOrder is not None


def test_project_import():
    """项目模块可正常导入。"""
    from battery_materials_agent.projects import Project, ProjectStore
    assert Project is not None


def test_audit_import():
    """审计日志模块可正常导入。"""
    from battery_materials_agent.audit import AuditLogger, AuditEntry
    assert AuditLogger is not None


def test_config_run_mode():
    """运行模式配置正确。"""
    from battery_materials_agent.config import RunMode
    assert RunMode.DEMO.value == "demo"
    assert RunMode.PRODUCTION.value == "production"


def test_workflow_schema():
    """工作流 Schema 加载正确。"""
    from battery_materials_agent.workflow_schema import get_schema_loader
    loader = get_schema_loader()
    nodes = loader.get_nodes()
    assert len(nodes) >= 8


def test_crystal_single_objective_score_not_zero_after_backfill():
    """回归：单目标 ionic_conductivity 候选在 estimate 回填后，综合评分不应恒为 0。

    MP API 不返回 ionic_conductivity，生成时 estimate 默认为 0，导致评分阶段
    全 0；agent.discover_crystal 在回填后需用 _coerce_multi_objective_config +
    _apply_multi_objective 复评分。本测试直接验证该复评分路径。
    """
    from battery_materials_agent.generation.crystal_candidate_generator import (
        CrystalCandidate,
        _apply_multi_objective,
        _coerce_multi_objective_config,
    )

    def _make(estimate):
        return CrystalCandidate(
            formula=f"F{estimate}",
            band_gap=2.0,
            formation_energy=-2.0,
            energy_above_hull=0.0,
            ionic_conductivity_estimate=estimate,
        )

    # 前端单目标模式：target_properties 为空，target_property=ionic_conductivity
    target_property = "ionic_conductivity"
    target_properties = None

    # 回填前（生成阶段）：estimate 全 0 → 评分全 0（缺陷复现）
    before = [_make(0.0), _make(0.0), _make(0.0)]
    cfg = _coerce_multi_objective_config(target_property, target_properties)
    assert cfg == [
        {"property": "ionic_conductivity", "direction": "maximize", "weight": 1.0}
    ]
    scored_before = _apply_multi_objective(before, cfg)
    assert all(c.multi_objective_score == 0.0 for c in scored_before)

    # 回填后（agent.discover_crystal 复评分）：estimate 有区分度 → 评分有区分度且排序正确
    after = [_make(1e-3), _make(5e-2), _make(1e-1)]
    scored_after = _apply_multi_objective(after, cfg)
    scores = [c.multi_objective_score for c in scored_after]
    # 缺陷是"全 0 无区分度"；修复后评分应拉开梯度（min-max 归一化下最小项为 0）
    assert len(set(scores)) > 1
    # 评分降序：estimate 越大评分越高
    assert scores == sorted(scores, reverse=True)
    assert scored_after[0].ionic_conductivity_estimate == 1e-1
    assert scored_after[-1].ionic_conductivity_estimate == 1e-3