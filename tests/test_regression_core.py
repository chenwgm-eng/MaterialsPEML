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