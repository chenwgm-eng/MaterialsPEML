"""CPU Worker 单元测试 — 验证 ScientificCPUWorker 生命周期和任务分发。"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from battery_materials_agent.contracts.run import Run, RunStatus
from battery_materials_agent.workers.cpu_worker import (
    ScientificCPUWorker,
    get_worker,
    start_worker,
    stop_worker,
)


class TestScientificCPUWorkerCreation(unittest.TestCase):
    """ScientificCPUWorker 创建与单例测试。"""

    def tearDown(self):
        # 清理全局单例状态
        import battery_materials_agent.workers.cpu_worker as w
        w._worker_instance = None

    def test_worker_creation(self):
        """验证创建 worker 实例应正确初始化。"""
        worker = ScientificCPUWorker()
        self.assertIsNotNone(worker._kernel)
        self.assertEqual(worker._services, {})
        self.assertIsNone(worker._thread)

    def test_get_worker_singleton(self):
        """验证 get_worker 应返回同一实例。"""
        worker1 = get_worker()
        worker2 = get_worker()
        self.assertIs(worker1, worker2)

    def test_get_worker_creates_new_instance(self):
        """验证首次调用 get_worker 应创建新实例。"""
        import battery_materials_agent.workers.cpu_worker as w
        w._worker_instance = None
        worker = get_worker()
        self.assertIsInstance(worker, ScientificCPUWorker)


class TestScientificCPUWorkerRegisterService(unittest.TestCase):
    """ScientificCPUWorker.register_service 方法测试。"""

    def setUp(self):
        self.worker = ScientificCPUWorker()

    def test_register_service(self):
        """验证注册服务应添加到 services 字典。"""
        mock_service = MagicMock()
        mock_service.capability_id = "mpa"
        self.worker.register_service("mpa", mock_service)
        self.assertIn("mpa", self.worker._services)
        self.assertIs(self.worker._services["mpa"], mock_service)

    def test_register_multiple_services(self):
        """验证可注册多个服务。"""
        mpa = MagicMock()
        chem = MagicMock()
        self.worker.register_service("mpa", mpa)
        self.worker.register_service("chem_properties", chem)
        self.assertEqual(len(self.worker._services), 2)


class TestScientificCPUWorkerStartStop(unittest.TestCase):
    """ScientificCPUWorker.start/stop 方法测试。"""

    def setUp(self):
        self.worker = ScientificCPUWorker(kernel=MagicMock())

    def test_start_creates_thread(self):
        """验证 start 应创建并启动后台线程。"""
        self.worker.start()
        self.assertIsNotNone(self.worker._thread)
        self.assertTrue(self.worker._thread.is_alive())
        self.worker.stop()

    def test_start_when_already_running(self):
        """验证重复调用 start 应不创建新线程。"""
        self.worker.start()
        thread_id = id(self.worker._thread)
        self.worker.start()
        self.assertEqual(id(self.worker._thread), thread_id)
        self.worker.stop()

    def test_stop_joins_thread(self):
        """验证 stop 应停止后台线程。"""
        self.worker.start()
        self.worker.stop()
        self.assertFalse(self.worker._thread.is_alive())

    def test_stop_without_start(self):
        """验证未启动时调用 stop 不应报错。"""
        try:
            self.worker.stop()
        except Exception:
            self.fail("stop() raised unexpectedly when worker not started")


class TestScientificCPUWorkerProcessRuns(unittest.TestCase):
    """ScientificCPUWorker 任务执行逻辑测试。"""

    def setUp(self):
        self.worker = ScientificCPUWorker()
        self.mock_kernel = MagicMock()
        self.worker._kernel = self.mock_kernel

    def test_process_queued_runs_empty(self):
        """验证无队列任务时应不执行任何操作。"""
        self.mock_kernel.list_runs.return_value = []
        self.worker._process_queued_runs()
        self.mock_kernel.list_runs.assert_called_once()

    def test_process_queued_runs_no_service(self):
        """验证未注册服务时应标记为 FAILED。"""
        run = MagicMock(run_id="run-001", service_id="unknown_service")
        self.mock_kernel.list_runs.return_value = [run]
        self.worker._process_queued_runs()
        self.mock_kernel.update_run_status.assert_called_with("run-001", RunStatus.FAILED)

    def test_execute_run_success(self):
        """验证成功执行应标记为 SUCCEEDED。"""
        mock_service = MagicMock()
        mock_service.execute.return_value = []
        mock_service.postprocess.return_value = []
        self.worker._services["test_service"] = mock_service

        run = Run(
            run_id="run-001",
            task_id="task-001",
            project_id="proj-001",
            service_id="test_service",
            command="test_command",
            metadata={},
        )
        self.worker._execute_run(run)
        mock_service.execute.assert_called_once()
        mock_service.postprocess.assert_called_once()
        self.mock_kernel.update_run_status.assert_called_with("run-001", RunStatus.SUCCEEDED)

    def test_execute_run_retry_then_fail(self):
        """验证执行失败重试后应标记为 FAILED。"""
        mock_service = MagicMock()
        mock_service.execute.side_effect = Exception("execution error")
        self.worker._services["test_service"] = mock_service

        # 减少重试次数以加速测试
        original_max_retries = self.worker.MAX_RETRIES
        self.worker.MAX_RETRIES = 2

        run = Run(
            run_id="run-001",
            task_id="task-001",
            project_id="proj-001",
            service_id="test_service",
            command="test_command",
            metadata={},
        )
        self.worker._execute_run(run)
        self.assertEqual(mock_service.execute.call_count, 2)
        # 最后应调用 FAILED（在重试耗尽后）
        self.mock_kernel.update_run_status.assert_called_with("run-001", RunStatus.FAILED)

        self.worker.MAX_RETRIES = original_max_retries


class TestStartStopWorkerFunctions(unittest.TestCase):
    """start_worker / stop_worker 模块级函数测试。"""

    def setUp(self):
        self._kernel_patcher = patch(
            "battery_materials_agent.workers.cpu_worker.ScientificExecutionKernel"
        )
        self._kernel_patcher.start()

    def tearDown(self):
        self._kernel_patcher.stop()
        import battery_materials_agent.workers.cpu_worker as w
        if w._worker_instance is not None:
            w._worker_instance.stop()
            w._worker_instance = None

    def test_start_worker(self):
        """验证 start_worker 应启动全局 worker。"""
        start_worker()
        import battery_materials_agent.workers.cpu_worker as w
        self.assertIsNotNone(w._worker_instance)
        self.assertTrue(w._worker_instance._thread.is_alive())
        stop_worker()

    def test_stop_worker(self):
        """验证 stop_worker 应停止全局 worker。"""
        start_worker()
        stop_worker()
        import battery_materials_agent.workers.cpu_worker as w
        self.assertFalse(w._worker_instance._thread.is_alive())


class TestScientificCPUWorkerConstants(unittest.TestCase):
    """ScientificCPUWorker 常量测试。"""

    def test_default_constants(self):
        """验证默认常量值。"""
        self.assertEqual(ScientificCPUWorker.IDLE_INTERVAL_SECONDS, 5.0)
        self.assertEqual(ScientificCPUWorker.BUSY_INTERVAL_SECONDS, 1.0)
        self.assertEqual(ScientificCPUWorker.BATCH_SIZE, 10)
        self.assertEqual(ScientificCPUWorker.MAX_RETRIES, 3)


if __name__ == "__main__":
    unittest.main()