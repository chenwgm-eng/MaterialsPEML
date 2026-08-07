"""WorkflowExecutor 单元测试 — 验证工作流定义、拓扑排序、$ref 解析、混编执行和失败策略。"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch, call

from battery_materials_agent.contracts.task import Task
from battery_materials_agent.contracts.run import Run
from battery_materials_agent.contracts.artifact import Artifact, ArtifactType
from battery_materials_agent.contracts.evidence import EvidencePackage, EvidenceLevel
from battery_materials_agent.services.base_service import NativeScientificService
from battery_materials_agent.workflow.executor import (
    WorkflowExecutor,
    WorkflowDefinition,
    WorkflowStep,
    WorkflowResult,
    StepResult,
)


class TestWorkflowStepModel(unittest.TestCase):
    """WorkflowStep Pydantic 模型默认值测试。"""

    def test_required_fields(self):
        """验证 type 和 service_id 为必填字段。"""
        with self.assertRaises(ValueError):
            WorkflowStep()

    def test_minimal_step(self):
        """验证仅提供必填字段可创建步骤。"""
        step = WorkflowStep(type="native", service_id="mpa")
        self.assertEqual(step.step_id, "")
        self.assertEqual(step.type, "native")
        self.assertEqual(step.service_id, "mpa")
        self.assertEqual(step.command, "")
        self.assertEqual(step.input, {})
        self.assertEqual(step.depends_on, [])
        self.assertEqual(step.on_failure, "stop")
        self.assertEqual(step.fallback_input, {})
        self.assertEqual(step.description, "")

    def test_full_step(self):
        """验证提供所有字段可创建完整步骤。"""
        step = WorkflowStep(
            step_id="step-1",
            type="scp",
            service_id="some_tool",
            command="run",
            input={"key": "value"},
            depends_on=["step-0"],
            on_failure="skip",
            fallback_input={"alt": "val"},
            description="测试步骤",
        )
        self.assertEqual(step.step_id, "step-1")
        self.assertEqual(step.type, "scp")
        self.assertEqual(step.service_id, "some_tool")
        self.assertEqual(step.command, "run")
        self.assertEqual(step.input, {"key": "value"})
        self.assertEqual(step.depends_on, ["step-0"])
        self.assertEqual(step.on_failure, "skip")
        self.assertEqual(step.fallback_input, {"alt": "val"})
        self.assertEqual(step.description, "测试步骤")

    def test_invalid_type_rejected(self):
        """验证不支持的 type 应被拒绝。"""
        with self.assertRaises(ValueError):
            WorkflowStep(type="invalid", service_id="x")

    def test_invalid_on_failure_rejected(self):
        """验证不支持的 on_failure 策略应被拒绝。"""
        with self.assertRaises(ValueError):
            WorkflowStep(type="native", service_id="x", on_failure="invalid")

    def test_type_literals_accepted(self):
        """验证所有三种 type 字面量均可接受。"""
        native = WorkflowStep(type="native", service_id="a")
        scp = WorkflowStep(type="scp", service_id="b")
        skill = WorkflowStep(type="skill", service_id="c")
        self.assertEqual(native.type, "native")
        self.assertEqual(scp.type, "scp")
        self.assertEqual(skill.type, "skill")


class TestWorkflowDefinitionModel(unittest.TestCase):
    """WorkflowDefinition 创建与默认值测试。"""

    def test_minimal_definition(self):
        """验证仅提供必填字段可创建工作流定义。"""
        step = WorkflowStep(type="native", service_id="mpa")
        wf = WorkflowDefinition(steps=[step])
        self.assertEqual(wf.workflow_id, "")
        self.assertEqual(wf.name, "")
        self.assertEqual(len(wf.steps), 1)
        self.assertEqual(wf.project_id, "")
        self.assertEqual(wf.context, {})

    def test_full_definition(self):
        """验证提供所有字段可创建完整工作流定义。"""
        steps = [
            WorkflowStep(step_id="s1", type="native", service_id="mpa"),
            WorkflowStep(step_id="s2", type="scp", service_id="tool"),
        ]
        wf = WorkflowDefinition(
            workflow_id="wf-test",
            name="测试工作流",
            steps=steps,
            project_id="proj-001",
            context={"global_param": 42},
        )
        self.assertEqual(wf.workflow_id, "wf-test")
        self.assertEqual(wf.name, "测试工作流")
        self.assertEqual(len(wf.steps), 2)
        self.assertEqual(wf.project_id, "proj-001")
        self.assertEqual(wf.context, {"global_param": 42})


class TestWorkflowExecutorInit(unittest.TestCase):
    """WorkflowExecutor 创建与服务注册测试。"""

    def test_empty_registry(self):
        """验证默认初始化应创建空注册表。"""
        executor = WorkflowExecutor()
        self.assertEqual(executor._service_registry, {})
        self.assertIsNone(executor._scp_executor)
        self.assertIsNone(executor._skill_executor)

    def test_init_with_registry(self):
        """验证提供注册表可初始化。"""
        reg = {"mpa": MagicMock()}
        executor = WorkflowExecutor(service_registry=reg)
        self.assertIs(executor._service_registry, reg)

    def test_init_with_executors(self):
        """验证提供 SCP 和 Skill 执行器可初始化。"""
        scp = MagicMock()
        skill = MagicMock()
        executor = WorkflowExecutor(scp_executor=scp, skill_executor=skill)
        self.assertIs(executor._scp_executor, scp)
        self.assertIs(executor._skill_executor, skill)

    def test_register_service(self):
        """验证 register_service 应添加服务到注册表。"""
        executor = WorkflowExecutor()
        service = MagicMock(spec=NativeScientificService)
        executor.register_service("mpa", service)
        self.assertIn("mpa", executor._service_registry)
        self.assertIs(executor._service_registry["mpa"], service)

    def test_register_service_overwrite(self):
        """验证重复注册同一 ID 应覆盖。"""
        executor = WorkflowExecutor()
        s1 = MagicMock()
        s2 = MagicMock()
        executor.register_service("svc", s1)
        executor.register_service("svc", s2)
        self.assertIs(executor._service_registry["svc"], s2)

    def test_register_multiple_services(self):
        """验证可注册多个不同服务。"""
        executor = WorkflowExecutor()
        mpa = MagicMock()
        chem = MagicMock()
        executor.register_service("mpa", mpa)
        executor.register_service("chem_properties", chem)
        self.assertEqual(len(executor._service_registry), 2)


class TestWorkflowExecutorTopologicalSort(unittest.TestCase):
    """WorkflowExecutor._topological_sort 拓扑排序测试。"""

    def setUp(self):
        self.executor = WorkflowExecutor()

    def test_no_dependencies(self):
        """验证无依赖步骤应按原序返回。"""
        steps = [
            WorkflowStep(step_id="a", type="native", service_id="s1"),
            WorkflowStep(step_id="b", type="native", service_id="s2"),
        ]
        ordered = self.executor._topological_sort(steps)
        self.assertEqual([s.step_id for s in ordered], ["a", "b"])

    def test_simple_dependency(self):
        """验证简单依赖关系应正确排序。"""
        steps = [
            WorkflowStep(step_id="b", type="native", service_id="s2", depends_on=["a"]),
            WorkflowStep(step_id="a", type="native", service_id="s1"),
        ]
        ordered = self.executor._topological_sort(steps)
        self.assertEqual([s.step_id for s in ordered], ["a", "b"])

    def test_chain_dependency(self):
        """验证链式依赖 (a → b → c) 应正确排序。"""
        steps = [
            WorkflowStep(step_id="c", type="native", service_id="s3", depends_on=["b"]),
            WorkflowStep(step_id="a", type="native", service_id="s1"),
            WorkflowStep(step_id="b", type="native", service_id="s2", depends_on=["a"]),
        ]
        ordered = self.executor._topological_sort(steps)
        self.assertEqual([s.step_id for s in ordered], ["a", "b", "c"])

    def test_diamond_dependency(self):
        """验证菱形依赖应正确排序（a 依赖无，b/c 依赖 a，d 依赖 b/c）。"""
        steps = [
            WorkflowStep(step_id="d", type="native", service_id="s4", depends_on=["b", "c"]),
            WorkflowStep(step_id="b", type="native", service_id="s2", depends_on=["a"]),
            WorkflowStep(step_id="a", type="native", service_id="s1"),
            WorkflowStep(step_id="c", type="native", service_id="s3", depends_on=["a"]),
        ]
        ordered = self.executor._topological_sort(steps)
        ordered_ids = [s.step_id for s in ordered]
        # a 必须在 b 和 c 之前
        self.assertLess(ordered_ids.index("a"), ordered_ids.index("b"))
        self.assertLess(ordered_ids.index("a"), ordered_ids.index("c"))
        # b 和 c 必须在 d 之前
        self.assertLess(ordered_ids.index("b"), ordered_ids.index("d"))
        self.assertLess(ordered_ids.index("c"), ordered_ids.index("d"))

    def test_preserves_all_steps(self):
        """验证拓扑排序应保留所有步骤。"""
        steps = [
            WorkflowStep(step_id="c", type="native", service_id="s3", depends_on=["b"]),
            WorkflowStep(step_id="a", type="native", service_id="s1"),
            WorkflowStep(step_id="b", type="native", service_id="s2", depends_on=["a"]),
        ]
        ordered = self.executor._topological_sort(steps)
        self.assertEqual(len(ordered), 3)
        self.assertEqual({s.step_id for s in ordered}, {"a", "b", "c"})

    def test_dependency_on_nonexistent_step(self):
        """验证依赖不存在的步骤不会影响排序。"""
        steps = [
            WorkflowStep(step_id="a", type="native", service_id="s1"),
            WorkflowStep(step_id="b", type="native", service_id="s2", depends_on=["nonexistent"]),
        ]
        ordered = self.executor._topological_sort(steps)
        self.assertEqual(len(ordered), 2)
        self.assertIn("b", [s.step_id for s in ordered])


class TestWorkflowExecutorCyclicDependency(unittest.TestCase):
    """WorkflowExecutor 循环依赖检测测试。"""

    def setUp(self):
        self.executor = WorkflowExecutor()

    def test_direct_cycle(self):
        """验证直接循环依赖 (a → b → a) 应抛出异常。"""
        steps = [
            WorkflowStep(step_id="a", type="native", service_id="s1", depends_on=["b"]),
            WorkflowStep(step_id="b", type="native", service_id="s2", depends_on=["a"]),
        ]
        with self.assertRaises(ValueError) as ctx:
            self.executor._topological_sort(steps)
        self.assertIn("循环依赖", str(ctx.exception))

    def test_self_cycle(self):
        """验证自循环依赖 (a → a) 应抛出异常。"""
        steps = [
            WorkflowStep(step_id="a", type="native", service_id="s1", depends_on=["a"]),
        ]
        with self.assertRaises(ValueError) as ctx:
            self.executor._topological_sort(steps)
        self.assertIn("循环依赖", str(ctx.exception))

    def test_execute_cyclic_workflow(self):
        """验证 execute 对循环依赖应抛出异常。"""
        steps = [
            WorkflowStep(step_id="a", type="native", service_id="s1", depends_on=["b"]),
            WorkflowStep(step_id="b", type="native", service_id="s2", depends_on=["a"]),
        ]
        wf = WorkflowDefinition(steps=steps, project_id="proj-001")
        with self.assertRaises(ValueError) as ctx:
            self.executor.execute(wf)
        self.assertIn("循环依赖", str(ctx.exception))


class TestWorkflowExecutorResolveInput(unittest.TestCase):
    """WorkflowExecutor._resolve_input $ref 解析测试。"""

    def setUp(self):
        self.executor = WorkflowExecutor()

    def test_no_ref(self):
        """验证无 $ref 的输入应原样返回。"""
        raw = {"key1": "value1", "key2": 42}
        result = self.executor._resolve_input(raw, {})
        self.assertEqual(result, raw)

    def test_ref_full_output(self):
        """验证 $ref 引用整个 output 应正确解析。"""
        step_results = {
            "prev": StepResult(step_id="prev", status="success", output={"data": "result"}),
        }
        raw = {"my_input": {"$ref": "prev"}}
        result = self.executor._resolve_input(raw, step_results)
        self.assertEqual(result, {"my_input": {"data": "result"}})

    def test_ref_specific_key(self):
        """验证 $ref 引用 output 中特定键应正确解析。"""
        step_results = {
            "prev": StepResult(step_id="prev", status="success", output={"data": "result"}),
        }
        raw = {"my_input": {"$ref": "prev.data"}}
        result = self.executor._resolve_input(raw, step_results)
        self.assertEqual(result, {"my_input": "result"})

    def test_mixed_ref_and_literal(self):
        """验证混合 $ref 和字面值应正确解析。"""
        step_results = {
            "prev": StepResult(step_id="prev", status="success", output={"value": 99}),
        }
        raw = {"literal": "hello", "ref_val": {"$ref": "prev.value"}}
        result = self.executor._resolve_input(raw, step_results)
        self.assertEqual(result, {"literal": "hello", "ref_val": 99})

    def test_ref_nonexistent_step(self):
        """验证引用不存在的步骤应抛出异常。"""
        raw = {"x": {"$ref": "missing.data"}}
        with self.assertRaises(ValueError) as ctx:
            self.executor._resolve_input(raw, {})
        self.assertIn("引用不存在的步骤", str(ctx.exception))

    def test_ref_to_nonexistent_key_returns_none(self):
        """验证引用 output 中不存在的键应返回 None。"""
        step_results = {
            "prev": StepResult(step_id="prev", status="success", output={"a": 1}),
        }
        raw = {"x": {"$ref": "prev.b"}}
        result = self.executor._resolve_input(raw, step_results)
        self.assertEqual(result, {"x": None})

    def test_nested_dict_without_ref(self):
        """验证嵌套字典（非 $ref 对象）应原样保留。"""
        raw = {"config": {"nested": "value", "deep": {"key": 1}}}
        result = self.executor._resolve_input(raw, {})
        self.assertEqual(result, raw)

    def test_multiple_refs(self):
        """验证多个 $ref 引用应正确解析。"""
        step_results = {
            "s1": StepResult(step_id="s1", status="success", output={"x": 10}),
            "s2": StepResult(step_id="s2", status="success", output={"y": 20}),
        }
        raw = {"a": {"$ref": "s1.x"}, "b": {"$ref": "s2.y"}}
        result = self.executor._resolve_input(raw, step_results)
        self.assertEqual(result, {"a": 10, "b": 20})


class TestWorkflowExecutorExecuteNative(unittest.TestCase):
    """WorkflowExecutor 原生服务执行测试。"""

    def setUp(self):
        self.mock_service = MagicMock(spec=NativeScientificService)
        self.mock_service.capability_id = "mpa"
        self.mock_evidence = [
            EvidencePackage(
                run_id="run-1", task_id="task-1", claim="test", source_service="mpa"
            ),
        ]
        self.mock_service.run_full_cycle.return_value = self.mock_evidence

        self.executor = WorkflowExecutor(service_registry={"mpa": self.mock_service})

    def test_execute_native_success(self):
        """验证原生服务步骤成功执行应返回正确结果。"""
        step = WorkflowStep(step_id="s1", type="native", service_id="mpa", description="测试")
        wf = WorkflowDefinition(steps=[step], project_id="proj-001")
        result = self.executor.execute(wf)

        self.assertEqual(result.status, "completed")
        self.assertEqual(len(result.steps), 1)
        step_result = result.steps[0]
        self.assertEqual(step_result.step_id, "s1")
        self.assertEqual(step_result.status, "success")
        self.assertEqual(step_result.evidence, self.mock_evidence)
        self.assertEqual(step_result.output, {"evidence_count": 1})

    def test_execute_native_with_input(self):
        """验证原生服务执行应传递正确输入。"""
        step = WorkflowStep(
            step_id="s1", type="native", service_id="mpa",
            input={"material": "LiCoO2"},
        )
        wf = WorkflowDefinition(steps=[step], project_id="proj-001")

        self.executor.execute(wf)
        # 验证 run_full_cycle 被调用，且 task 包含正确的 metadata
        call_args = self.mock_service.run_full_cycle.call_args
        task = call_args[0][0]
        self.assertIsInstance(task, Task)
        self.assertEqual(task.metadata, {"material": "LiCoO2"})
        self.assertEqual(task.project_id, "proj-001")
        self.assertEqual(task.capability_id, "mpa")

    def test_execute_native_unregistered_service(self):
        """验证未注册的原生服务应失败。"""
        step = WorkflowStep(step_id="s1", type="native", service_id="unknown")
        wf = WorkflowDefinition(steps=[step], project_id="proj-001")
        result = self.executor.execute(wf)

        self.assertEqual(result.status, "partially_completed")
        self.assertEqual(len(result.steps), 1)
        self.assertEqual(result.steps[0].status, "failed")
        self.assertIn("未注册的原生服务", result.steps[0].error)

    def test_execute_native_service_raises(self):
        """验证原生服务抛出异常应记录失败。"""
        self.mock_service.run_full_cycle.side_effect = RuntimeError("计算失败")
        step = WorkflowStep(step_id="s1", type="native", service_id="mpa")
        wf = WorkflowDefinition(steps=[step], project_id="proj-001")
        result = self.executor.execute(wf)

        self.assertEqual(result.status, "partially_completed")
        self.assertEqual(result.steps[0].status, "failed")
        self.assertIn("计算失败", result.steps[0].error)

    def test_execute_native_with_context(self):
        """验证全局上下文应传递给服务。"""
        step = WorkflowStep(step_id="s1", type="native", service_id="mpa")
        wf = WorkflowDefinition(
            steps=[step], project_id="proj-001", context={"temperature": 300},
        )
        self.executor.execute(wf)

        call_args = self.mock_service.run_full_cycle.call_args
        context = call_args[0][1]
        self.assertEqual(context["temperature"], 300)
        self.assertEqual(context["project_id"], "proj-001")


class TestWorkflowExecutorExecuteMixed(unittest.TestCase):
    """WorkflowExecutor 混编执行（native + scp + skill）测试。"""

    def setUp(self):
        self.mock_service = MagicMock(spec=NativeScientificService)
        self.mock_service.capability_id = "mpa"
        self.mock_service.run_full_cycle.return_value = []

        self.mock_scp = MagicMock()
        self.mock_scp.execute.return_value = {"scp_result": "ok"}

        self.mock_skill = MagicMock()
        self.mock_skill.execute.return_value = {"skill_result": "done"}

        self.executor = WorkflowExecutor(
            service_registry={"mpa": self.mock_service},
            scp_executor=self.mock_scp,
            skill_executor=self.mock_skill,
        )

    def test_native_step_only(self):
        """验证仅原生步骤的工作流应正常执行。"""
        step = WorkflowStep(step_id="s1", type="native", service_id="mpa")
        wf = WorkflowDefinition(steps=[step], project_id="proj-001")
        result = self.executor.execute(wf)
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.steps[0].status, "success")

    def test_scp_step_only(self):
        """验证仅 SCP 步骤的工作流应正常执行。"""
        step = WorkflowStep(step_id="s1", type="scp", service_id="some_tool")
        wf = WorkflowDefinition(steps=[step], project_id="proj-001")
        result = self.executor.execute(wf)
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.steps[0].status, "success")
        self.mock_scp.execute.assert_called_once_with("some_tool", {})

    def test_scp_step_with_invoke(self):
        """验证 SCP 执行器仅有 invoke 方法时应正确调用。"""
        scp_invoke = MagicMock()
        scp_invoke.invoke.return_value = {"result": "via_invoke"}
        del scp_invoke.execute
        executor = WorkflowExecutor(scp_executor=scp_invoke)

        step = WorkflowStep(step_id="s1", type="scp", service_id="tool_a", input={"x": 1})
        wf = WorkflowDefinition(steps=[step], project_id="proj-001")
        result = executor.execute(wf)
        self.assertEqual(result.status, "completed")
        scp_invoke.invoke.assert_called_once()

    def test_scp_step_no_executor(self):
        """验证未配置 SCP 执行器应失败。"""
        executor = WorkflowExecutor()
        step = WorkflowStep(step_id="s1", type="scp", service_id="tool")
        wf = WorkflowDefinition(steps=[step], project_id="proj-001")
        result = executor.execute(wf)
        self.assertEqual(result.status, "partially_completed")
        self.assertIn("SCP 执行器未配置", result.steps[0].error)

    def test_skill_step_only(self):
        """验证仅 Skill 步骤的工作流应正常执行。"""
        step = WorkflowStep(step_id="s1", type="skill", service_id="my_skill")
        wf = WorkflowDefinition(steps=[step], project_id="proj-001")
        result = self.executor.execute(wf)
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.steps[0].status, "success")
        self.mock_skill.execute.assert_called_once_with("my_skill", {})

    def test_skill_step_with_run_method(self):
        """验证 Skill 执行器仅有 run 方法时应正确调用。"""
        skill_run = MagicMock()
        skill_run.run.return_value = {"result": "via_run"}
        del skill_run.execute
        executor = WorkflowExecutor(skill_executor=skill_run)

        step = WorkflowStep(step_id="s1", type="skill", service_id="skill_a")
        wf = WorkflowDefinition(steps=[step], project_id="proj-001")
        result = executor.execute(wf)
        self.assertEqual(result.status, "completed")
        skill_run.run.assert_called_once_with("skill_a", {})

    def test_skill_step_callable(self):
        """验证 Skill 执行器为可调用对象时应直接调用。"""
        skill_callable = MagicMock(return_value={"result": "direct"})
        del skill_callable.execute
        del skill_callable.run
        executor = WorkflowExecutor(skill_executor=skill_callable)

        step = WorkflowStep(step_id="s1", type="skill", service_id="skill_a")
        wf = WorkflowDefinition(steps=[step], project_id="proj-001")
        result = executor.execute(wf)
        self.assertEqual(result.status, "completed")
        skill_callable.assert_called_once_with("skill_a", {})

    def test_skill_step_no_executor(self):
        """验证未配置 Skill 执行器应失败。"""
        executor = WorkflowExecutor()
        step = WorkflowStep(step_id="s1", type="skill", service_id="skill")
        wf = WorkflowDefinition(steps=[step], project_id="proj-001")
        result = executor.execute(wf)
        self.assertEqual(result.status, "partially_completed")
        self.assertIn("Skill 执行器未配置", result.steps[0].error)

    def test_mixed_workflow_all_success(self):
        """验证混编工作流全部成功应返回 completed。"""
        steps = [
            WorkflowStep(step_id="s1", type="native", service_id="mpa"),
            WorkflowStep(step_id="s2", type="scp", service_id="tool", depends_on=["s1"]),
            WorkflowStep(step_id="s3", type="skill", service_id="skill", depends_on=["s2"]),
        ]
        wf = WorkflowDefinition(steps=steps, project_id="proj-001")
        result = self.executor.execute(wf)
        self.assertEqual(result.status, "completed")
        self.assertEqual(len(result.steps), 3)
        for s in result.steps:
            self.assertEqual(s.status, "success")

    def test_data_passing_between_steps_via_ref(self):
        """验证步骤间通过 $ref 传递数据。"""
        self.mock_service.run_full_cycle.return_value = [
            EvidencePackage(
                run_id="r1", task_id="t1", claim="density", value=2.5,
                source_service="mpa",
            ),
        ]

        # 模拟 output 包含计算结果
        original_execute = self.executor._execute_native

        def patched_execute(step, resolved_input, context):
            result = original_execute(step, resolved_input, context)
            # 注入模拟 output 以便后续步骤引用
            result.output = {"density": 2.5, "evidence_count": 1}
            return result

        self.executor._execute_native = patched_execute

        steps = [
            WorkflowStep(step_id="calc", type="native", service_id="mpa", input={"formula": "LiCoO2"}),
            WorkflowStep(
                step_id="report", type="scp", service_id="reporter",
                depends_on=["calc"],
                input={"density_val": {"$ref": "calc.density"}},
            ),
        ]
        wf = WorkflowDefinition(steps=steps, project_id="proj-001")
        result = self.executor.execute(wf)
        self.assertEqual(result.status, "completed")
        self.assertEqual(len(result.steps), 2)
        # 验证 SCP 步骤收到了解析后的输入
        call_args = self.mock_scp.execute.call_args
        scp_input = call_args[0][1]
        self.assertEqual(scp_input, {"density_val": 2.5})

    def test_workflow_id_generated(self):
        """验证未指定 workflow_id 时应自动生成。"""
        step = WorkflowStep(step_id="s1", type="native", service_id="mpa")
        wf = WorkflowDefinition(steps=[step], project_id="proj-001")
        self.assertEqual(wf.workflow_id, "")
        result = self.executor.execute(wf)
        self.assertTrue(result.workflow_id.startswith("wf-"))
        self.assertEqual(len(result.workflow_id), 15)  # "wf-" + 12 hex chars

    def test_workflow_id_preserved(self):
        """验证已指定 workflow_id 应保持不变。"""
        step = WorkflowStep(step_id="s1", type="native", service_id="mpa")
        wf = WorkflowDefinition(workflow_id="my-wf", steps=[step], project_id="proj-001")
        result = self.executor.execute(wf)
        self.assertEqual(result.workflow_id, "my-wf")

    def test_unsupported_step_type(self):
        """验证不支持的步骤类型应失败。"""
        step = WorkflowStep(step_id="s1", type="native", service_id="mpa")
        # 在 _execute_step 中手动触发不支持的 type
        executor = self.executor
        with patch.object(executor, "_execute_step") as mock_exec:
            mock_exec.side_effect = ValueError("不支持的步骤类型: unknown")
            wf = WorkflowDefinition(steps=[step], project_id="proj-001")
            result = executor.execute(wf)
            self.assertEqual(result.steps[0].status, "failed")


class TestWorkflowExecutorOnFailure(unittest.TestCase):
    """WorkflowExecutor on_failure 策略测试。"""

    def setUp(self):
        self.mock_service = MagicMock(spec=NativeScientificService)
        self.mock_service.capability_id = "mpa"
        self.executor = WorkflowExecutor(service_registry={"mpa": self.mock_service})

    def test_stop_strategy(self):
        """验证 on_failure='stop' 应在失败时停止后续步骤。"""
        self.mock_service.run_full_cycle.side_effect = RuntimeError("失败")
        steps = [
            WorkflowStep(step_id="s1", type="native", service_id="mpa", on_failure="stop"),
            WorkflowStep(step_id="s2", type="native", service_id="mpa"),
        ]
        wf = WorkflowDefinition(steps=steps, project_id="proj-001")
        result = self.executor.execute(wf)
        self.assertEqual(result.status, "partially_completed")
        self.assertEqual(result.steps[0].status, "failed")
        # s2 不应被执行
        self.assertEqual(len(result.steps), 1)

    def test_skip_strategy(self):
        """验证 on_failure='skip' 应在失败时继续后续步骤。"""
        self.mock_service.run_full_cycle.side_effect = [
            RuntimeError("失败"),  # s1 失败
            [],                    # s2 成功
        ]
        steps = [
            WorkflowStep(step_id="s1", type="native", service_id="mpa", on_failure="skip"),
            WorkflowStep(step_id="s2", type="native", service_id="mpa"),
        ]
        wf = WorkflowDefinition(steps=steps, project_id="proj-001")
        result = self.executor.execute(wf)
        self.assertEqual(result.status, "partially_completed")
        self.assertEqual(result.steps[0].status, "failed")
        self.assertEqual(result.steps[1].status, "success")
        self.assertEqual(len(result.steps), 2)

    def test_fallback_strategy_success(self):
        """验证 fallback 成功时应使用回退结果。"""
        def side_effect(task, context):
            if task.metadata.get("material") == "original":
                raise RuntimeError("原始失败")
            return []

        self.mock_service.run_full_cycle.side_effect = side_effect

        step = WorkflowStep(
            step_id="s1", type="native", service_id="mpa",
            input={"material": "original"},
            on_failure="fallback",
            fallback_input={"material": "backup"},
        )
        wf = WorkflowDefinition(steps=[step], project_id="proj-001")
        result = self.executor.execute(wf)
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.steps[0].status, "success")
        # 验证回退输入被使用
        self.assertEqual(self.mock_service.run_full_cycle.call_count, 2)

    def test_fallback_strategy_fails(self):
        """验证 fallback 也失败时应继续执行（不停止）。"""
        self.mock_service.run_full_cycle.side_effect = RuntimeError("全部失败")

        steps = [
            WorkflowStep(
                step_id="s1", type="native", service_id="mpa",
                on_failure="fallback", fallback_input={"alt": True},
            ),
            WorkflowStep(step_id="s2", type="native", service_id="mpa"),
        ]
        # 让 s2 成功
        real_side_effect = self.mock_service.run_full_cycle.side_effect
        call_count = 0

        def side_effect_with_s2(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count >= 3:  # s2 的调用
                return []
            raise RuntimeError("全部失败")

        self.mock_service.run_full_cycle.side_effect = side_effect_with_s2

        wf = WorkflowDefinition(steps=steps, project_id="proj-001")
        result = self.executor.execute(wf)
        # s1 失败（含 fallback），s2 成功
        self.assertEqual(result.status, "partially_completed")
        self.assertEqual(result.steps[0].status, "failed")
        self.assertEqual(result.steps[1].status, "success")
        self.assertIn("回退也失败", result.errors[1])

    def test_stop_with_dependencies(self):
        """验证 stop 策略应阻止依赖步骤执行。"""
        self.mock_service.run_full_cycle.side_effect = RuntimeError("失败")
        steps = [
            WorkflowStep(step_id="s1", type="native", service_id="mpa", on_failure="stop"),
            WorkflowStep(step_id="s2", type="native", service_id="mpa", depends_on=["s1"]),
        ]
        wf = WorkflowDefinition(steps=steps, project_id="proj-001")
        result = self.executor.execute(wf)
        self.assertEqual(result.status, "partially_completed")
        self.assertEqual(len(result.steps), 1)

    def test_skip_with_dependencies(self):
        """验证 skip 策略但依赖失败时步骤仍被跳过。"""
        self.mock_service.run_full_cycle.side_effect = RuntimeError("失败")

        steps = [
            WorkflowStep(step_id="s1", type="native", service_id="mpa", on_failure="skip"),
            WorkflowStep(step_id="s2", type="native", service_id="mpa", depends_on=["s1"]),
        ]
        wf = WorkflowDefinition(steps=steps, project_id="proj-001")
        result = self.executor.execute(wf)
        # s1 失败，s2 因为依赖失败被跳过
        self.assertEqual(result.status, "partially_completed")
        self.assertEqual(result.steps[0].status, "failed")
        self.assertEqual(result.steps[1].status, "skipped")
        self.assertEqual(len(result.steps), 2)


class TestWorkflowExecutorStepDependency(unittest.TestCase):
    """WorkflowExecutor 步骤依赖跳过测试。"""

    def setUp(self):
        self.mock_service = MagicMock(spec=NativeScientificService)
        self.mock_service.capability_id = "mpa"
        self.mock_service.run_full_cycle.return_value = []
        self.executor = WorkflowExecutor(service_registry={"mpa": self.mock_service})

    def test_skip_when_dependency_failed(self):
        """验证依赖失败时应跳过后续步骤。"""
        # s1 成功，s2 依赖 s1 但失败，s3 依赖 s2 应被跳过
        call_log = []

        def side_effect(task, context):
            call_log.append(task.title)
            if task.title == "s2":
                raise RuntimeError("s2 失败")
            return []

        self.mock_service.run_full_cycle.side_effect = side_effect

        steps = [
            WorkflowStep(step_id="s1", type="native", service_id="mpa", description="s1", on_failure="skip"),
            WorkflowStep(step_id="s2", type="native", service_id="mpa", depends_on=["s1"], description="s2", on_failure="skip"),
            WorkflowStep(step_id="s3", type="native", service_id="mpa", depends_on=["s2"], description="s3"),
        ]
        wf = WorkflowDefinition(steps=steps, project_id="proj-001")
        result = self.executor.execute(wf)
        self.assertIn("s1", call_log)
        self.assertIn("s2", call_log)
        self.assertNotIn("s3", call_log)  # s3 因 s2 失败被跳过
        self.assertEqual(result.steps[0].status, "success")
        self.assertEqual(result.steps[1].status, "failed")
        self.assertEqual(result.steps[2].status, "skipped")

    def test_all_dependencies_satisfied(self):
        """验证所有依赖成功时应正常执行。"""
        steps = [
            WorkflowStep(step_id="s1", type="native", service_id="mpa"),
            WorkflowStep(step_id="s2", type="native", service_id="mpa", depends_on=["s1"]),
            WorkflowStep(step_id="s3", type="native", service_id="mpa", depends_on=["s1", "s2"]),
        ]
        wf = WorkflowDefinition(steps=steps, project_id="proj-001")
        result = self.executor.execute(wf)
        self.assertEqual(result.status, "completed")
        for s in result.steps:
            self.assertEqual(s.status, "success")

    def test_skip_when_missing_dependency_result(self):
        """验证依赖未执行（结果不存在）时应跳过。"""
        # 直接从 _execute_step 调用，模拟依赖没有结果
        # 在 execute 中，依赖检查发生在执行前
        # 如果我们让 s1 被跳过（没有结果），s2 依赖 s1 应被跳过
        # 但正常情况下 s1 被跳过只发生在 s1 的依赖失败时
        # 我们模拟一个场景：s1 的依赖失败，s1 被跳过，s2 依赖 s1 应被跳过
        steps = [
            # 无依赖步骤，但让它失败
            WorkflowStep(step_id="s0", type="native", service_id="mpa", on_failure="skip"),
            WorkflowStep(step_id="s1", type="native", service_id="mpa", depends_on=["s0"], on_failure="skip"),
            WorkflowStep(step_id="s2", type="native", service_id="mpa", depends_on=["s1"]),
        ]
        # s0 失败 → s1 跳过（依赖失败）→ s2 跳过（s1 被跳过，status 不是 success）
        self.mock_service.run_full_cycle.side_effect = RuntimeError("s0 失败")

        wf = WorkflowDefinition(steps=steps, project_id="proj-001")
        result = self.executor.execute(wf)
        self.assertEqual(result.steps[0].status, "failed")
        self.assertEqual(result.steps[1].status, "skipped")
        self.assertEqual(result.steps[2].status, "skipped")

    def test_no_dependency_chain(self):
        """验证无依赖步骤应全部并行执行（按拓扑序）。"""
        steps = [
            WorkflowStep(step_id="s1", type="native", service_id="mpa"),
            WorkflowStep(step_id="s2", type="native", service_id="mpa"),
            WorkflowStep(step_id="s3", type="native", service_id="mpa"),
        ]
        wf = WorkflowDefinition(steps=steps, project_id="proj-001")
        result = self.executor.execute(wf)
        self.assertEqual(result.status, "completed")
        self.assertEqual(len(result.steps), 3)
        self.assertEqual(self.mock_service.run_full_cycle.call_count, 3)


class TestWorkflowResult(unittest.TestCase):
    """WorkflowResult 模型测试。"""

    def test_minimal_result(self):
        """验证仅提供必填字段可创建结果。"""
        result = WorkflowResult(workflow_id="wf-1", status="completed")
        self.assertEqual(result.workflow_id, "wf-1")
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.steps, [])
        self.assertEqual(result.errors, [])

    def test_full_result(self):
        """验证提供所有字段可创建完整结果。"""
        steps = [
            StepResult(step_id="s1", status="success"),
            StepResult(step_id="s2", status="failed"),
        ]
        result = WorkflowResult(
            workflow_id="wf-1",
            status="partially_completed",
            steps=steps,
            errors=["s2 失败"],
        )
        self.assertEqual(result.workflow_id, "wf-1")
        self.assertEqual(result.status, "partially_completed")
        self.assertEqual(len(result.steps), 2)
        self.assertEqual(result.errors, ["s2 失败"])

    def test_status_literals(self):
        """验证 status 字面量约束。"""
        WorkflowResult(workflow_id="a", status="completed")
        WorkflowResult(workflow_id="a", status="failed")
        WorkflowResult(workflow_id="a", status="partially_completed")
        with self.assertRaises(ValueError):
            WorkflowResult(workflow_id="a", status="unknown")

    def test_step_result_defaults(self):
        """验证 StepResult 默认值。"""
        sr = StepResult(step_id="s1", status="success")
        self.assertEqual(sr.step_id, "s1")
        self.assertEqual(sr.status, "success")
        self.assertEqual(sr.artifacts, [])
        self.assertEqual(sr.evidence, [])
        self.assertEqual(sr.output, {})
        self.assertIsNone(sr.error)

    def test_step_result_with_artifacts_and_evidence(self):
        """验证 StepResult 包含工件和证据。"""
        art = Artifact(run_id="r1", type=ArtifactType.REPORT, name="report")
        ev = EvidencePackage(run_id="r1", task_id="t1", claim="claim", source_service="svc")
        sr = StepResult(
            step_id="s1", status="success",
            artifacts=[art],
            evidence=[ev],
            output={"key": "val"},
            error=None,
        )
        self.assertEqual(len(sr.artifacts), 1)
        self.assertEqual(sr.artifacts[0].name, "report")
        self.assertEqual(len(sr.evidence), 1)
        self.assertEqual(sr.evidence[0].claim, "claim")
        self.assertEqual(sr.output, {"key": "val"})

    def test_workflow_result_all_success(self):
        """验证 execute 在全部成功时返回 completed 状态。"""
        # 通过 execute 测试状态推断
        mock_svc = MagicMock(spec=NativeScientificService)
        mock_svc.capability_id = "mpa"
        mock_svc.run_full_cycle.return_value = []
        executor = WorkflowExecutor(service_registry={"mpa": mock_svc})

        steps = [
            WorkflowStep(step_id="s1", type="native", service_id="mpa"),
            WorkflowStep(step_id="s2", type="native", service_id="mpa"),
        ]
        wf = WorkflowDefinition(workflow_id="wf-001", steps=steps, project_id="proj-001")
        result = executor.execute(wf)

        self.assertEqual(result.workflow_id, "wf-001")
        self.assertEqual(result.status, "completed")
        self.assertEqual(len(result.steps), 2)
        self.assertEqual(result.errors, [])

    def test_workflow_result_partial_with_skip(self):
        """验证有步骤被跳过时仍为 partially_completed。"""
        mock_svc = MagicMock(spec=NativeScientificService)
        mock_svc.capability_id = "mpa"
        mock_svc.run_full_cycle.side_effect = RuntimeError("fail")
        executor = WorkflowExecutor(service_registry={"mpa": mock_svc})

        steps = [
            WorkflowStep(step_id="s1", type="native", service_id="mpa", on_failure="skip"),
            WorkflowStep(step_id="s2", type="native", service_id="mpa", depends_on=["s1"]),
        ]
        wf = WorkflowDefinition(steps=steps, project_id="proj-001")
        result = executor.execute(wf)

        # s1 失败，s2 跳过
        self.assertEqual(result.status, "partially_completed")
        self.assertEqual(result.steps[0].status, "failed")
        self.assertEqual(result.steps[1].status, "skipped")


if __name__ == "__main__":
    unittest.main()