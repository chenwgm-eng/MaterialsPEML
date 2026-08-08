"""端到端集成测试 — 验证从 API 路由到数据库写入的完整链路。

覆盖范围：
  1. TestDatabaseSchema          — scientific_kernel.* 6 张表 / 索引 / 外键
  2. TestStateMachineTransitions — Run 状态机转换（含新修复的 QUEUED→RUNNING 路径）
  3. TestKernelLifecycle         — ScientificExecutionKernel 真实数据库生命周期
  4. TestServiceRegistry         — 11 个原生科学服务注册表与 CPU Worker 注册
  5. TestWorkflowExecutor        — 真实服务混编工作流 / $ref 解析 / 失败策略
  6. TestOutboxReliability       — 事务 Outbox 入队/领取/标记 + SKIP LOCKED + 重试
  7. TestAPIRoutes               — FastAPI TestClient 验证 HTTP→kernel→DB 链路

约定：
  - 所有测试基于 unittest 框架。
  - 涉及数据库的测试在 setUp/tearDown 中通过 TRUNCATE CASCADE 清理 6 张表。
  - 不 mock ScientificExecutionKernel —— 使用真实的内核与真实 PostgreSQL。
  - 每个测试方法可独立运行，不依赖其他测试的执行顺序。
"""

from __future__ import annotations

import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

from battery_materials_agent.contracts.artifact import Artifact, ArtifactType
from battery_materials_agent.contracts.evidence import EvidenceLevel, EvidencePackage
from battery_materials_agent.contracts.run import Run, RunStatus
from battery_materials_agent.contracts.task import Task, TaskPriority, TaskStatus
from battery_materials_agent.db import get_engine
from battery_materials_agent.domain.runtime.execution_kernel import ScientificExecutionKernel
from battery_materials_agent.domain.runtime.outbox import ScientificOutbox
from battery_materials_agent.domain.runtime.state_machine import (
    InvalidTransitionError,
    RunStateMachine,
)
from battery_materials_agent.services.base_service import NativeScientificService
from battery_materials_agent.services.registry import get_service_registry
from battery_materials_agent.workflow.executor import (
    WorkflowDefinition,
    WorkflowExecutor,
    WorkflowStep,
)
from battery_materials_agent.workers.cpu_worker import ScientificCPUWorker


# ── 辅助函数 ──────────────────────────────────────────────────

_SK_TABLES = (
    "scientific_kernel.evidence",
    "scientific_kernel.artifacts",
    "scientific_kernel.approvals",
    "scientific_kernel.outbox",
    "scientific_kernel.runs",
    "scientific_kernel.tasks",
)


def _truncate_scientific_kernel() -> None:
    """清空 scientific_kernel 下全部 6 张表（CASCADE 处理外键依赖）。"""
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE {tbls} RESTART IDENTITY CASCADE".format(
            tbls=", ".join(_SK_TABLES)
        )))


def _build_test_app() -> FastAPI:
    """构建仅挂载原生科学路由的 FastAPI 应用用于 TestClient 测试。

    生产 ``battery_materials_agent.api.app`` 注册了 ``rewrite_api_prefix_middleware``
    （将 ``/api/xxx`` 重写为 ``/xxx``）与 SPA 兜底路由；该中间件假设后端不注册
    任何 ``/api/*`` 真实路由，而科学路由恰好以 ``/api/v1/*`` 注册，二者冲突会导致
    TestClient 请求被重写后失配返回 404。此处直接挂载真实的科学路由处理器
    （路由模块内部各自实例化真实的 ScientificExecutionKernel），既验证 HTTP→kernel→DB
    完整链路，又规避了与科学内核无关的前端/重写中间件基础设施。
    """
    from battery_materials_agent.scientific_routes.artifacts import router as artifacts_router
    from battery_materials_agent.scientific_routes.evidence import router as evidence_router
    from battery_materials_agent.scientific_routes.molecular_simulation_routes import (
        router as molecular_simulation_router,
    )
    from battery_materials_agent.scientific_routes.mpa_routes import router as mpa_router
    from battery_materials_agent.scientific_routes.reaction_network_routes import (
        router as reaction_network_router,
    )
    from battery_materials_agent.scientific_routes.scientific_runs import router as scientific_runs_router

    app = FastAPI()
    app.include_router(scientific_runs_router)
    app.include_router(artifacts_router)
    app.include_router(evidence_router)
    app.include_router(mpa_router)
    app.include_router(molecular_simulation_router)
    app.include_router(reaction_network_router)
    return app


def _make_task(project_id: str = "e2e-proj", capability_id: str = "mpa", title: str = "e2e task") -> Task:
    """构造一个最小可用的 Task。"""
    return Task(
        project_id=project_id,
        capability_id=capability_id,
        title=title,
        description="e2e integration test task",
    )


def _make_run(task_id: str, project_id: str = "e2e-proj", service_id: str = "mpa") -> Run:
    """构造一个最小可用的 Run（初始状态 QUEUED）。"""
    return Run(
        task_id=task_id,
        project_id=project_id,
        service_id=service_id,
        command="e2e_command",
        input={"smiles_list": ["CCO"]},
    )


# ── 1. 数据库 Schema ─────────────────────────────────────────

class TestDatabaseSchema(unittest.TestCase):
    """验证 scientific_kernel schema 的 6 张表、关键索引与外键约束。"""

    def setUp(self):
        self.engine = get_engine()

    def test_six_core_tables_exist(self):
        """验证 tasks/runs/artifacts/evidence/approvals/outbox 6 张核心表均已创建。

        采用子集断言而非相等断言：后续迁移可能新增其它表（如 ai_sessions /
        ai_messages），核心表必须存在，但 schema 不限于这 6 张。
        """
        expected = {"tasks", "runs", "artifacts", "evidence", "approvals", "outbox"}
        with self.engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'scientific_kernel'"
                )
            ).fetchall()
        actual = {r[0] for r in rows}
        missing = expected - actual
        self.assertEqual(missing, set(), f"缺失表: {missing}")

    def test_key_indexes_exist(self):
        """验证关键索引（tasks.status / runs.task_id / artifacts.run_id / outbox.status 等）存在。"""
        with self.engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT indexname FROM pg_indexes WHERE schemaname = 'scientific_kernel'"
                )
            ).fetchall()
        index_names = {r[0] for r in rows}
        expected_indexes = {
            "idx_tasks_status",
            "idx_tasks_project",
            "idx_tasks_capability",
            "idx_runs_task_id",
            "idx_runs_status",
            "idx_runs_service",
            "idx_artifacts_run",
            "idx_evidence_run",
            "idx_evidence_task",
            "idx_outbox_status",
            "idx_outbox_created",
        }
        missing = expected_indexes - index_names
        self.assertFalse(missing, f"缺失索引: {missing}")

    def test_foreign_key_constraints_exist(self):
        """验证 runs→tasks、artifacts→runs、evidence→runs 三条外键约束存在。"""
        with self.engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT conname, conrelid::regclass AS tbl, confrelid::regclass AS ref "
                    "FROM pg_constraint "
                    "WHERE connamespace = 'scientific_kernel'::regnamespace AND contype = 'f'"
                )
            ).fetchall()
        fk_map = {r[0]: (str(r[1]), str(r[2])) for r in rows}
        self.assertIn("fk_runs_task", fk_map)
        self.assertIn("fk_artifacts_run", fk_map)
        self.assertIn("fk_evidence_run", fk_map)
        self.assertEqual(fk_map["fk_runs_task"][1], "scientific_kernel.tasks")
        self.assertEqual(fk_map["fk_artifacts_run"][1], "scientific_kernel.runs")
        self.assertEqual(fk_map["fk_evidence_run"][1], "scientific_kernel.runs")

    def test_foreign_key_cascade_blocks_orphan_run(self):
        """验证外键约束生效：不存在的 task_id 无法插入 run。"""
        _truncate_scientific_kernel()
        with self.engine.begin() as conn:
            with self.assertRaises(Exception):
                conn.execute(
                    text(
                        "INSERT INTO scientific_kernel.runs "
                        "(run_id, task_id, project_id, service_id, command) "
                        "VALUES (:rid, :tid, :pid, :sid, :cmd)"
                    ),
                    {
                        "rid": "e2e-orphan-run",
                        "tid": "nonexistent-task",
                        "pid": "e2e-proj",
                        "sid": "mpa",
                        "cmd": "x",
                    },
                )
        self.addCleanup(_truncate_scientific_kernel)


# ── 2. 状态机转换 ────────────────────────────────────────────

class TestStateMachineTransitions(unittest.TestCase):
    """验证 Run 状态机的合法/非法转换（纯逻辑，不触碰数据库）。"""

    def setUp(self):
        self.sm = RunStateMachine()

    def test_queued_to_running_direct(self):
        """验证新修复的直通路径：QUEUED → RUNNING 应被允许。"""
        result = self.sm.transition(RunStatus.QUEUED, RunStatus.RUNNING)
        self.assertEqual(result, RunStatus.RUNNING)

    def test_queued_preparing_running_normal_path(self):
        """验证正常路径：QUEUED → PREPARING → RUNNING 均合法。"""
        step1 = self.sm.transition(RunStatus.QUEUED, RunStatus.PREPARING)
        self.assertEqual(step1, RunStatus.PREPARING)
        step2 = self.sm.transition(RunStatus.PREPARING, RunStatus.RUNNING)
        self.assertEqual(step2, RunStatus.RUNNING)

    def test_running_to_succeeded(self):
        """验证 RUNNING → SUCCEEDED 合法。"""
        self.assertEqual(
            self.sm.transition(RunStatus.RUNNING, RunStatus.SUCCEEDED),
            RunStatus.SUCCEEDED,
        )

    def test_running_to_failed(self):
        """验证 RUNNING → FAILED 合法。"""
        self.assertEqual(
            self.sm.transition(RunStatus.RUNNING, RunStatus.FAILED),
            RunStatus.FAILED,
        )

    def test_invalid_transition_raises(self):
        """验证非法转换（SUCCEEDED → RUNNING）应抛出 InvalidTransitionError。"""
        with self.assertRaises(InvalidTransitionError):
            self.sm.transition(RunStatus.SUCCEEDED, RunStatus.RUNNING)

    def test_terminal_states_have_no_outgoing(self):
        """验证终态（SUCCEEDED/FAILED/CANCELLED）不允许任何出边。"""
        for terminal in (RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED):
            with self.subTest(terminal=terminal):
                with self.assertRaises(InvalidTransitionError):
                    self.sm.transition(terminal, RunStatus.RUNNING)

    def test_same_state_transition_allowed(self):
        """验证相同状态转换（幂等）应被允许。"""
        self.assertEqual(
            self.sm.transition(RunStatus.RUNNING, RunStatus.RUNNING),
            RunStatus.RUNNING,
        )


# ── 3. Kernel 生命周期（真实数据库） ─────────────────────────

class TestKernelLifecycle(unittest.TestCase):
    """验证 ScientificExecutionKernel 在真实数据库上的完整生命周期。"""

    def setUp(self):
        _truncate_scientific_kernel()
        self.kernel = ScientificExecutionKernel()

    def tearDown(self):
        _truncate_scientific_kernel()

    def test_create_task_and_query(self):
        """create_task 写入后，get_task 应能查回并还原全部字段。"""
        task = _make_task()
        self.kernel.create_task(task)
        got = self.kernel.get_task(task.task_id)
        self.assertIsNotNone(got)
        self.assertEqual(got.task_id, task.task_id)
        self.assertEqual(got.project_id, task.project_id)
        self.assertEqual(got.capability_id, task.capability_id)
        self.assertEqual(got.title, task.title)
        self.assertEqual(got.status, TaskStatus.PENDING)
        self.assertEqual(got.priority, TaskPriority.NORMAL)

    def test_submit_run_and_query(self):
        """submit_run 写入后，get_run 应能查回且初始状态为 QUEUED。"""
        task = _make_task()
        self.kernel.create_task(task)
        run = _make_run(task.task_id)
        self.kernel.submit_run(run)
        got = self.kernel.get_run(run.run_id)
        self.assertIsNotNone(got)
        self.assertEqual(got.run_id, run.run_id)
        self.assertEqual(got.task_id, task.task_id)
        self.assertEqual(got.service_id, "mpa")
        self.assertEqual(got.status, RunStatus.QUEUED)
        self.assertEqual(got.input, {"smiles_list": ["CCO"]})

    def test_update_run_status_queued_running_succeeded(self):
        """update_run_status 应驱动 QUEUED→RUNNING→SUCCEEDED 并写入时间戳。"""
        task = _make_task()
        self.kernel.create_task(task)
        run = _make_run(task.task_id)
        self.kernel.submit_run(run)

        running = self.kernel.update_run_status(run.run_id, RunStatus.RUNNING)
        self.assertEqual(running.status, RunStatus.RUNNING)
        self.assertIsNotNone(running.started_at)
        self.assertIsNone(running.completed_at)

        succeeded = self.kernel.update_run_status(run.run_id, RunStatus.SUCCEEDED)
        self.assertEqual(succeeded.status, RunStatus.SUCCEEDED)
        self.assertIsNotNone(succeeded.completed_at)

    def test_update_run_status_running_failed(self):
        """update_run_status 应支持 RUNNING→FAILED 终态转换。"""
        task = _make_task()
        self.kernel.create_task(task)
        run = _make_run(task.task_id)
        self.kernel.submit_run(run)
        self.kernel.update_run_status(run.run_id, RunStatus.RUNNING)
        failed = self.kernel.update_run_status(run.run_id, RunStatus.FAILED)
        self.assertEqual(failed.status, RunStatus.FAILED)
        self.assertIsNotNone(failed.completed_at)

    def test_store_artifact_and_get_artifacts(self):
        """store_artifact 写入后，get_artifacts 应能按 run_id 查回。"""
        task = _make_task()
        self.kernel.create_task(task)
        run = _make_run(task.task_id)
        self.kernel.submit_run(run)

        artifact = Artifact(
            run_id=run.run_id,
            type=ArtifactType.RESULT_TABLE,
            name="e2e_result",
            description="e2e artifact",
            data={"value": 42},
        )
        self.kernel.store_artifact(artifact)
        got = self.kernel.get_artifacts(run.run_id)
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0].artifact_id, artifact.artifact_id)
        self.assertEqual(got[0].run_id, run.run_id)
        self.assertEqual(got[0].type, ArtifactType.RESULT_TABLE)
        self.assertEqual(got[0].data, {"value": 42})

    def test_store_evidence_and_get_evidence(self):
        """store_evidence 写入后，get_evidence 应能按 run_id 查回。"""
        task = _make_task()
        self.kernel.create_task(task)
        run = _make_run(task.task_id)
        self.kernel.submit_run(run)

        evidence = EvidencePackage(
            run_id=run.run_id,
            task_id=task.task_id,
            claim="e2e claim",
            value=3.14,
            unit="eV",
            confidence=0.95,
            level=EvidenceLevel.HIGH,
            method="e2e_method",
            source_service="real_engine:mpa",
        )
        self.kernel.store_evidence(evidence)
        got = self.kernel.get_evidence(run.run_id)
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0].evidence_id, evidence.evidence_id)
        self.assertEqual(got[0].claim, "e2e claim")
        self.assertEqual(got[0].source_service, "real_engine:mpa")
        self.assertEqual(got[0].level, EvidenceLevel.HIGH)

    def test_invalid_status_transition_blocked_by_kernel(self):
        """kernel.update_run_status 应拒绝非法转换（SUCCEEDED→RUNNING）。"""
        task = _make_task()
        self.kernel.create_task(task)
        run = _make_run(task.task_id)
        self.kernel.submit_run(run)
        self.kernel.update_run_status(run.run_id, RunStatus.RUNNING)
        self.kernel.update_run_status(run.run_id, RunStatus.SUCCEEDED)
        with self.assertRaises(InvalidTransitionError):
            self.kernel.update_run_status(run.run_id, RunStatus.RUNNING)


# ── 4. 服务注册表 ────────────────────────────────────────────

class TestServiceRegistry(unittest.TestCase):
    """验证 get_service_registry() 与 setup_cpu_worker() 的注册行为。"""

    EXPECTED_COUNT = 11

    def setUp(self):
        # 清除 lru_cache，确保每个测试拿到全新注册表（独立性）
        import battery_materials_agent.services.registry as reg_mod
        reg_mod.get_service_registry.cache_clear()
        _truncate_scientific_kernel()

    def tearDown(self):
        import battery_materials_agent.services.registry as reg_mod
        reg_mod.get_service_registry.cache_clear()
        _truncate_scientific_kernel()

    def test_registry_returns_twelve_services(self):
        """get_service_registry() 应返回 11 个原生科学服务。"""
        registry = get_service_registry()
        self.assertEqual(len(registry), self.EXPECTED_COUNT)

    def test_unique_capability_ids(self):
        """每个服务的 capability_id 应唯一且非空。"""
        registry = get_service_registry()
        cap_ids = list(registry.keys())
        self.assertEqual(len(cap_ids), len(set(cap_ids)), "存在重复的 capability_id")
        for cap_id in cap_ids:
            self.assertTrue(cap_id, "capability_id 不应为空")

    def test_all_services_inherit_native_base(self):
        """每个服务实例都应继承 NativeScientificService。"""
        registry = get_service_registry()
        for cap_id, svc in registry.items():
            with self.subTest(capability_id=cap_id):
                self.assertIsInstance(svc, NativeScientificService)

    def test_expected_capability_ids_present(self):
        """验证 11 个已知 capability_id 均已注册。"""
        expected = {
            "mpa", "chem_properties", "materials_structure", "formulation_packing",
            "molecular_simulation", "synthesis_planning",
            "process_modeling", "reaction_network", "wavefunction_analysis",
            "fluid_simulation", "molecular_docking",
        }
        registry = get_service_registry()
        self.assertEqual(set(registry.keys()), expected)

    def test_setup_cpu_worker_registers_all_services(self):
        """setup_cpu_worker() 应将全部 11 个服务注册到 CPU Worker。"""
        from battery_materials_agent.services.registry import setup_cpu_worker
        # 传入全新 worker 实例，避免污染全局单例
        worker = ScientificCPUWorker()
        result = setup_cpu_worker(worker=worker)
        self.assertIs(result, worker)
        self.assertEqual(len(worker._services), self.EXPECTED_COUNT)
        # 验证注册的 capability_id 与注册表一致
        registry = get_service_registry()
        self.assertEqual(set(worker._services.keys()), set(registry.keys()))


# ── 5. 工作流执行器（真实服务） ──────────────────────────────

class TestWorkflowExecutor(unittest.TestCase):
    """验证 WorkflowExecutor 驱动真实原生服务的多步骤工作流。"""

    def setUp(self):
        import battery_materials_agent.services.registry as reg_mod
        reg_mod.get_service_registry.cache_clear()
        _truncate_scientific_kernel()
        self.registry = get_service_registry()
        self.executor = WorkflowExecutor(service_registry=self.registry)

    def tearDown(self):
        import battery_materials_agent.services.registry as reg_mod
        reg_mod.get_service_registry.cache_clear()
        _truncate_scientific_kernel()

    def _mpa_step(self, step_id: str, smiles: list[str], **kwargs) -> WorkflowStep:
        """构造一个 MPA 原生服务步骤。"""
        params = {
            "project_id": "e2e-wf",
            "molecule_revision_ids": smiles,
            "property_keys": ["MW"],
        }
        params.update(kwargs)
        return WorkflowStep(
            step_id=step_id,
            type="native",
            service_id="mpa",
            input=params,
            description=step_id,
        )

    def test_two_native_steps_both_succeed(self):
        """包含 2 个 native 步骤的工作流应全部成功完成。"""
        wf = WorkflowDefinition(
            workflow_id="wf-e2e-two",
            name="e2e two-step",
            steps=[
                self._mpa_step("s1", ["CCO"]),
                self._mpa_step("s2", ["CC"], depends_on=["s1"]),
            ],
            project_id="e2e-wf",
        )
        result = self.executor.execute(wf)
        self.assertEqual(result.status, "completed")
        self.assertEqual(len(result.steps), 2)
        for step_result in result.steps:
            self.assertEqual(step_result.status, "success")
            self.assertIn("evidence_count", step_result.output)

    def test_ref_resolution_between_steps(self):
        """$ref 引用应能解析前置步骤的 output 字段并在后续步骤中使用。"""
        # step2 通过 $ref 引用 step1 的 evidence_count；MPA 命令模型会忽略额外字段
        step1 = self._mpa_step("step1", ["CCO"])
        step2 = WorkflowStep(
            step_id="step2",
            type="native",
            service_id="mpa",
            input={
                "project_id": "e2e-wf",
                "molecule_revision_ids": ["CC"],
                "property_keys": ["MW"],
                "prev_evidence_count": {"$ref": "step1.evidence_count"},
            },
            depends_on=["step1"],
            description="step2",
        )
        wf = WorkflowDefinition(steps=[step1, step2], project_id="e2e-wf")
        result = self.executor.execute(wf)
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.steps[0].status, "success")
        self.assertEqual(result.steps[1].status, "success")
        # step1 应产生证据，evidence_count > 0
        self.assertGreater(result.steps[0].output["evidence_count"], 0)

    def test_ref_to_full_output(self):
        """$ref 引用整个 output（不含子键）应返回完整 output dict。"""
        step1 = self._mpa_step("first", ["CCO"])
        step2 = WorkflowStep(
            step_id="second",
            type="native",
            service_id="mpa",
            input={
                "project_id": "e2e-wf",
                "molecule_revision_ids": ["CC"],
                "property_keys": ["MW"],
                "previous_output": {"$ref": "first"},
            },
            depends_on=["first"],
            description="second",
        )
        wf = WorkflowDefinition(steps=[step1, step2], project_id="e2e-wf")
        result = self.executor.execute(wf)
        self.assertEqual(result.status, "completed")
        # 验证 $ref 解析逻辑本身（直接调用静态方法）
        resolved = WorkflowExecutor._resolve_input(
            {"x": {"$ref": "first.evidence_count"}},
            {"first": result.steps[0]},
        )
        self.assertEqual(resolved["x"], result.steps[0].output["evidence_count"])

    def test_failure_strategy_stop(self):
        """on_failure='stop' 时首步失败应阻止后续步骤执行。"""
        # 空 SMILES 列表触发 MPA 校验失败 → run_full_cycle 抛 ValueError
        step1 = WorkflowStep(
            step_id="bad",
            type="native",
            service_id="mpa",
            input={"project_id": "e2e-wf", "molecule_revision_ids": [], "property_keys": ["MW"]},
            on_failure="stop",
            description="bad",
        )
        step2 = self._mpa_step("good", ["CCO"])
        wf = WorkflowDefinition(steps=[step1, step2], project_id="e2e-wf")
        result = self.executor.execute(wf)
        self.assertEqual(result.status, "partially_completed")
        self.assertEqual(result.steps[0].status, "failed")
        # stop 策略：后续步骤未执行，结果中仅含失败步骤
        self.assertEqual(len(result.steps), 1)

    def test_failure_strategy_skip(self):
        """on_failure='skip' 时首步失败后后续步骤应继续执行。"""
        step1 = WorkflowStep(
            step_id="bad",
            type="native",
            service_id="mpa",
            input={"project_id": "e2e-wf", "molecule_revision_ids": [], "property_keys": ["MW"]},
            on_failure="skip",
            description="bad",
        )
        step2 = self._mpa_step("good", ["CCO"])
        wf = WorkflowDefinition(steps=[step1, step2], project_id="e2e-wf")
        result = self.executor.execute(wf)
        self.assertEqual(result.status, "partially_completed")
        self.assertEqual(result.steps[0].status, "failed")
        self.assertEqual(result.steps[1].status, "success")


# ── 6. Outbox 可靠性 ─────────────────────────────────────────

class TestOutboxReliability(unittest.TestCase):
    """验证事务 Outbox 的入队/领取/标记与 SKIP LOCKED / 重试逻辑。"""

    def setUp(self):
        _truncate_scientific_kernel()
        self.outbox = ScientificOutbox()

    def tearDown(self):
        _truncate_scientific_kernel()

    def test_enqueue_claim_mark_sent_flow(self):
        """enqueue → claim_pending → mark_sent 完整流程应正确推进状态。"""
        engine = get_engine()
        msg = self.outbox.enqueue("e2e.event", "e2e-subject", {"k": "v"})
        self.assertEqual(msg.status, "pending")

        claimed = self.outbox.claim_pending(limit=10)
        self.assertEqual(len(claimed), 1)
        self.assertEqual(claimed[0].message_id, msg.message_id)
        # claim_pending 在同一事务内将 DB 状态推进为 'sending'（返回对象反映
        # SELECT 时刻的 'pending'，故以 DB 实际状态为准）
        with engine.connect() as conn:
            after_claim = conn.execute(
                text("SELECT status FROM scientific_kernel.outbox WHERE message_id = :mid"),
                {"mid": msg.message_id},
            ).fetchone()
        self.assertEqual(after_claim[0], "sending")

        # claim_pending 再次调用应无消息可领
        self.assertEqual(len(self.outbox.claim_pending(limit=10)), 0)

        self.outbox.mark_sent(msg.message_id)
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT status, sent_at FROM scientific_kernel.outbox "
                    "WHERE message_id = :mid"
                ),
                {"mid": msg.message_id},
            ).fetchone()
        self.assertEqual(row[0], "sent")
        self.assertIsNotNone(row[1])

    def test_claim_pending_disjoint_sets(self):
        """多次 claim_pending 应返回互不相交的消息集（已领取的不会被重复领取）。"""
        ids = []
        for i in range(3):
            m = self.outbox.enqueue("e2e.event", f"sub-{i}", {"i": i})
            ids.append(m.message_id)

        first_batch = self.outbox.claim_pending(limit=2)
        second_batch = self.outbox.claim_pending(limit=2)
        first_ids = {m.message_id for m in first_batch}
        second_ids = {m.message_id for m in second_batch}

        self.assertEqual(len(first_batch), 2)
        self.assertEqual(len(second_batch), 1)
        self.assertEqual(first_ids & second_ids, set(), "两批领取出现重叠")
        self.assertEqual(first_ids | second_ids, set(ids))

    def test_for_update_skip_locked_concurrent(self):
        """两个并发事务同时 SELECT ... FOR UPDATE SKIP LOCKED 应领取不相交的行。

        直接通过两个独立连接的显式事务验证 SKIP LOCKED 语义：连接 A 锁定部分行后，
        连接 B 的 SKIP LOCKED 查询应跳过被锁行，仅返回未被锁定的行。
        """
        for i in range(4):
            self.outbox.enqueue("e2e.concurrent", f"sub-{i}", {"i": i})

        engine = get_engine()
        conn_a = engine.connect()
        conn_b = engine.connect()
        tx_a = conn_a.begin()
        try:
            rows_a = conn_a.execute(
                text(
                    "SELECT message_id FROM scientific_kernel.outbox "
                    "WHERE status = 'pending' ORDER BY created_at ASC LIMIT 2 "
                    "FOR UPDATE SKIP LOCKED"
                )
            ).fetchall()
            ids_a = {r[0] for r in rows_a}
            self.assertEqual(len(ids_a), 2)

            # 连接 B 在 A 未提交时领取，应跳过 A 锁定的行
            tx_b = conn_b.begin()
            rows_b = conn_b.execute(
                text(
                    "SELECT message_id FROM scientific_kernel.outbox "
                    "WHERE status = 'pending' ORDER BY created_at ASC LIMIT 2 "
                    "FOR UPDATE SKIP LOCKED"
                )
            ).fetchall()
            ids_b = {r[0] for r in rows_b}
            tx_b.rollback()

            self.assertEqual(len(ids_b), 2, "连接 B 应领取剩余 2 行")
            self.assertEqual(ids_a & ids_b, set(), "SKIP LOCKED 下两连接不应领取相同行")
        finally:
            tx_a.rollback()
            conn_a.close()
            conn_b.close()

    def test_retry_logic_marks_failed_after_max_retries(self):
        """mark_failed 在未达 max_retries 时重置回 pending 以便重试，达到后终态化为 'failed'。"""
        msg = self.outbox.enqueue("e2e.retry", "e2e-subject", {}, max_retries=2)

        # 先领取（状态 → sending），模拟 worker 处理失败后的真实路径
        claimed = self.outbox.claim_pending(limit=10)
        self.assertEqual(len(claimed), 1)

        # 第一次失败：retry_count=1 < max_retries=2，状态应重置回 pending 以允许重试
        self.outbox.mark_failed(msg.message_id, "error-1")
        engine = get_engine()
        with engine.connect() as conn:
            r1 = conn.execute(
                text("SELECT status, retry_count FROM scientific_kernel.outbox WHERE message_id = :mid"),
                {"mid": msg.message_id},
            ).fetchone()
        self.assertEqual(r1[0], "pending")
        self.assertEqual(r1[1], 1)

        # 重置回 pending 后应能被再次领取（重试生效）
        reclaim = self.outbox.claim_pending(limit=10)
        self.assertEqual(len(reclaim), 1)
        self.assertEqual(reclaim[0].message_id, msg.message_id)

        # 第二次失败：retry_count=2 >= max_retries=2，终态化为 failed
        self.outbox.mark_failed(msg.message_id, "error-2")
        with engine.connect() as conn:
            r2 = conn.execute(
                text("SELECT status, retry_count, last_error FROM scientific_kernel.outbox WHERE message_id = :mid"),
                {"mid": msg.message_id},
            ).fetchone()
        self.assertEqual(r2[0], "failed")
        self.assertEqual(r2[1], 2)
        self.assertEqual(r2[2], "error-2")


# ── 7. API 路由（FastAPI TestClient） ────────────────────────

class TestAPIRoutes(unittest.TestCase):
    """使用 FastAPI TestClient 验证 HTTP 路由 → kernel → 数据库的完整链路。

    说明：任务描述中提到的 ``POST /v1/scientific-runs``（创建任务+运行）在当前
    实现中由两个独立端点承担 —— ``POST /v1/tasks`` 创建任务、``POST /v1/runs``
    提交运行；本测试通过连续调用这两个端点并回查 ``GET /v1/runs/{run_id}`` 来
    覆盖该意图。``GET /v1/artifacts/{run_id}`` / ``GET /v1/evidence/{run_id}``
    对应实际注册的 ``GET /v1/runs/{run_id}/artifacts`` 与
    ``GET /v1/runs/{run_id}/evidence``。
    """

    @classmethod
    def setUpClass(cls):
        cls.app = _build_test_app()
        cls.client = TestClient(cls.app)

    def setUp(self):
        _truncate_scientific_kernel()

    def tearDown(self):
        _truncate_scientific_kernel()

    def _create_task_and_run(self) -> tuple[str, str]:
        """通过 API 创建任务并提交运行，返回 (task_id, run_id)。"""
        task_resp = self.client.post(
            "/v1/tasks",
            json={"project_id": "e2e-api", "capability_id": "mpa", "title": "e2e api task"},
        )
        self.assertEqual(task_resp.status_code, 200)
        task_id = task_resp.json()["task_id"]

        run_resp = self.client.post(
            "/v1/runs",
            json={
                "task_id": task_id,
                "project_id": "e2e-api",
                "service_id": "mpa",
                "command": "predict_molecular_properties",
                "input": {"smiles_list": ["CCO"]},
            },
        )
        self.assertEqual(run_resp.status_code, 200)
        run_id = run_resp.json()["run_id"]
        return task_id, run_id

    def test_create_task_and_run_via_api(self):
        """POST /v1/tasks + POST /v1/runs 应写入数据库并可回查。"""
        task_id, run_id = self._create_task_and_run()

        # 回查 task
        task_get = self.client.get(f"/v1/tasks/{task_id}")
        self.assertEqual(task_get.status_code, 200)
        self.assertEqual(task_get.json()["task_id"], task_id)

        # 回查 run（初始状态 queued）
        run_get = self.client.get(f"/v1/runs/{run_id}")
        self.assertEqual(run_get.status_code, 200)
        run_body = run_get.json()
        self.assertEqual(run_body["run_id"], run_id)
        self.assertEqual(run_body["task_id"], task_id)
        self.assertEqual(run_body["status"], "queued")

    def test_get_run_not_found(self):
        """GET /v1/runs/{run_id} 对不存在的 run 应返回 404。"""
        resp = self.client.get("/v1/runs/nonexistent-run")
        self.assertEqual(resp.status_code, 404)

    def test_get_artifacts_for_run(self):
        """GET /v1/runs/{run_id}/artifacts 应返回该 run 的工件列表。"""
        _, run_id = self._create_task_and_run()
        # 通过 API 写入一个工件
        store_resp = self.client.post(
            "/v1/artifacts",
            json={
                "run_id": run_id,
                "type": "result_table",
                "name": "api_artifact",
                "data": {"v": 1},
            },
        )
        self.assertEqual(store_resp.status_code, 200)

        get_resp = self.client.get(f"/v1/runs/{run_id}/artifacts")
        self.assertEqual(get_resp.status_code, 200)
        artifacts = get_resp.json()
        self.assertEqual(len(artifacts), 1)
        self.assertEqual(artifacts[0]["name"], "api_artifact")
        self.assertEqual(artifacts[0]["run_id"], run_id)

    def test_get_evidence_for_run(self):
        """GET /v1/runs/{run_id}/evidence 应返回该 run 的证据包列表。"""
        _, run_id = self._create_task_and_run()
        # StoreEvidenceRequest.value 仅接受 str|dict|list|None，故用 dict 提交
        store_resp = self.client.post(
            "/v1/evidence",
            json={
                "run_id": run_id,
                "task_id": self.client.get(f"/v1/runs/{run_id}").json()["task_id"],
                "claim": "api evidence claim",
                "value": {"amount": 2.71},
                "unit": "eV",
                "source_service": "mpa",
            },
        )
        self.assertEqual(store_resp.status_code, 200)

        get_resp = self.client.get(f"/v1/runs/{run_id}/evidence")
        self.assertEqual(get_resp.status_code, 200)
        evidence = get_resp.json()
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0]["claim"], "api evidence claim")
        self.assertEqual(evidence[0]["run_id"], run_id)

    def test_mpa_predict_full_endpoint(self):
        """POST /v1/mpa/predict/full 应完成全生命周期并返回证据包（写入数据库）。"""
        resp = self.client.post(
            "/v1/mpa/predict/full",
            json={
                "project_id": "e2e-mpa",
                "molecule_revision_ids": ["CCO"],
                "property_keys": ["MW"],
            },
        )
        self.assertEqual(resp.status_code, 200)
        evidence = resp.json()
        self.assertGreater(len(evidence), 0)
        self.assertIn("evidence_id", evidence[0])
        self.assertEqual(evidence[0]["source_service"], "real_engine:mpa")

        # 验证数据库确有对应 run（状态应为 succeeded）
        run_id = evidence[0]["run_id"]
        run_resp = self.client.get(f"/v1/runs/{run_id}")
        self.assertEqual(run_resp.status_code, 200)
        self.assertEqual(run_resp.json()["status"], "succeeded")

    def test_molecular_simulation_run_endpoint(self):
        """POST /v1/molecular-simulation/run 应返回工件列表。"""
        resp = self.client.post(
            "/v1/molecular-simulation/run",
            json={
                "project_id": "e2e-ms",
                "system_type": "A",
                "structure_data": "CCO",
            },
        )
        self.assertEqual(resp.status_code, 200)
        artifacts = resp.json()
        self.assertIsInstance(artifacts, list)
        self.assertGreater(len(artifacts), 0)

    def test_reaction_network_enumerate_endpoint(self):
        """POST /v1/reaction-network/enumerate 应完成全生命周期并返回证据包。"""
        resp = self.client.post(
            "/v1/reaction-network/enumerate",
            json={"project_id": "e2e-rn", "reactant_smiles": ["CCO"]},
        )
        self.assertEqual(resp.status_code, 200)
        evidence = resp.json()
        self.assertGreater(len(evidence), 0)
        self.assertIn("evidence_id", evidence[0])


if __name__ == "__main__":
    unittest.main()
