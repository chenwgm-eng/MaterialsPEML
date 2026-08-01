"""测试实验模式隔离（demo/production）。"""

import pytest
from battery_materials_agent.config import RunMode, AgentConfig
from battery_materials_agent.experiment.experiment_controller import (
    ExperimentController,
    ExperimentType,
    ExperimentStatus,
)


def test_run_mode_enum():
    """RunMode 枚举包含 demo 和 production。"""
    assert RunMode.DEMO.value == "demo"
    assert RunMode.PRODUCTION.value == "production"


def test_default_config_is_demo():
    """默认配置应为 demo 模式。"""
    config = AgentConfig()
    assert config.run_mode == RunMode.DEMO


def test_demo_mode_generates_simulated_data():
    """demo 模式下应生成模拟数据。"""
    controller = ExperimentController(run_mode="demo")
    result = controller.execute_experiment(
        {"formula": "LiCoO2"},
        ExperimentType.IONIC_CONDUCTIVITY,
    )
    assert result.status == ExperimentStatus.COMPLETED
    assert len(result.measured_values) > 0
    assert "ionic_conductivity_S_cm" in result.measured_values


def test_production_mode_does_not_simulate():
    """production 模式下不应生成模拟数据。"""
    controller = ExperimentController(run_mode="production")
    result = controller.execute_experiment(
        {"formula": "LiCoO2"},
        ExperimentType.IONIC_CONDUCTIVITY,
    )
    assert result.status == ExperimentStatus.PENDING
    assert len(result.measured_values) == 0
    assert result.metadata.get("mode") == "production_waiting"


def test_production_mode_task_is_pending():
    """production 模式下任务应处于 PENDING 状态。"""
    controller = ExperimentController(run_mode="production")
    result = controller.execute_experiment(
        {"formula": "LiCoO2"},
        ExperimentType.IONIC_CONDUCTIVITY,
    )
    task = controller.get_task(result.task_id)
    assert task is not None
    assert task.status == ExperimentStatus.PENDING
