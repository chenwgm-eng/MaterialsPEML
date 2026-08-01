"""Tests for experiment controller module."""

import pytest
import tempfile
import os
import shutil
from sqlalchemy import text
from battery_materials_agent.experiment.experiment_controller import (
    ExperimentController, ExperimentTask, ExperimentResult,
    ExperimentStatus, ExperimentType,
)


@pytest.fixture(autouse=True)
def _cleanup_experiment_tasks():
    """每个测试前后清理 experiment_tasks，避免跨测试数据污染。"""
    from battery_materials_agent.db import get_engine
    with get_engine().begin() as conn:
        conn.execute(text("DELETE FROM experiment.experiment_tasks"))
    yield
    with get_engine().begin() as conn:
        conn.execute(text("DELETE FROM experiment.experiment_tasks"))


class TestExperimentController:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "experiments.db")
        self.controller = ExperimentController(db_path=self.db_path)

    def teardown_method(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_submit_task(self):
        task = ExperimentTask(
            task_id="test-001",
            experiment_type=ExperimentType.IONIC_CONDUCTIVITY,
        )
        task_id = self.controller.submit_task(task)
        assert task_id == "test-001"

    def test_start_task(self):
        task = ExperimentTask(task_id="t1", experiment_type=ExperimentType.ELECTROCHEMICAL)
        self.controller.submit_task(task)
        assert self.controller.start_task("t1") is True
        assert self.controller.get_task("t1").status == ExperimentStatus.RUNNING

    def test_complete_task(self):
        task = ExperimentTask(task_id="t2", experiment_type=ExperimentType.XRD)
        self.controller.submit_task(task)
        self.controller.start_task("t2")
        result = ExperimentResult(
            task_id="t2",
            experiment_type=ExperimentType.XRD,
            status=ExperimentStatus.COMPLETED,
            measured_values={"peak_position": 25.3},
        )
        assert self.controller.complete_task("t2", result) is True
        assert self.controller.get_result("t2").measured_values["peak_position"] == 25.3

    def test_fail_task(self):
        task = ExperimentTask(task_id="t3", experiment_type=ExperimentType.SEM)
        self.controller.submit_task(task)
        self.controller.start_task("t3")
        assert self.controller.fail_task("t3", "Hardware error") is True
        assert self.controller.get_task("t3").status == ExperimentStatus.FAILED

    def test_cancel_task(self):
        task = ExperimentTask(task_id="t4", experiment_type=ExperimentType.DSC)
        self.controller.submit_task(task)
        assert self.controller.cancel_task("t4") is True
        assert self.controller.get_task("t4").status == ExperimentStatus.CANCELLED

    def test_list_tasks(self):
        self.controller.submit_task(ExperimentTask(task_id="a", experiment_type=ExperimentType.TGA))
        self.controller.submit_task(ExperimentTask(task_id="b", experiment_type=ExperimentType.XRD))
        all_tasks = self.controller.list_tasks()
        assert len(all_tasks) == 2

    def test_list_tasks_by_status(self):
        self.controller.submit_task(ExperimentTask(task_id="c", experiment_type=ExperimentType.XRD))
        self.controller.start_task("c")
        running = self.controller.list_tasks(status=ExperimentStatus.RUNNING)
        assert len(running) == 1

    def test_get_nonexistent_task(self):
        assert self.controller.get_task("nonexistent") is None

    def test_complete_nonexistent(self):
        assert self.controller.complete_task("nonexistent", ExperimentResult(
            task_id="x", experiment_type=ExperimentType.XRD, status=ExperimentStatus.COMPLETED,
        )) is False

    def test_execute_experiment(self):
        result = self.controller.execute_experiment(
            {"formula": "LiCoO2", "concentration": 0.1},
            ExperimentType.IONIC_CONDUCTIVITY,
        )
        assert result.status == ExperimentStatus.COMPLETED
        assert result.task_id != ""

    def test_experiment_types(self):
        for et in ExperimentType:
            assert isinstance(et.value, str)
