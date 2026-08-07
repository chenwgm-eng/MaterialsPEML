"""Workflow Executor — 支持原生服务、SCP 工具和 Skill 的混编执行。

允许定义可执行的工作流步骤序列，每步可调用：
- type: native → NativeScientificService 实现
- type: scp → SCP 工具
- type: skill → Skill 能力
"""
from __future__ import annotations

import logging
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from ..contracts.task import Task
from ..contracts.run import Run
from ..contracts.artifact import Artifact
from ..contracts.evidence import EvidencePackage
from ..services.base_service import NativeScientificService

logger = logging.getLogger(__name__)


class WorkflowStep(BaseModel):
    """工作流步骤定义。"""

    step_id: str = Field(default="", description="步骤 ID")
    type: Literal["native", "scp", "skill"] = Field(..., description="步骤类型")
    service_id: str = Field(..., description="原生服务 ID / SCP 工具 ID / Skill 名称")
    command: str = Field(default="", description="执行命令（仅 native 类型）")
    input: dict[str, Any] = Field(default_factory=dict, description="步骤输入参数")
    depends_on: list[str] = Field(default_factory=list, description="依赖的步骤 ID 列表")
    on_failure: Literal["stop", "skip", "fallback"] = Field(default="stop", description="失败处理策略")
    fallback_input: dict[str, Any] = Field(default_factory=dict, description="回退输入参数")
    description: str = Field(default="", description="步骤描述")


class WorkflowDefinition(BaseModel):
    """工作流定义。"""

    workflow_id: str = Field(default="", description="工作流 ID")
    name: str = Field(default="", description="工作流名称")
    steps: list[WorkflowStep] = Field(..., description="步骤列表")
    project_id: str = Field(default="", description="项目 ID")
    context: dict[str, Any] = Field(default_factory=dict, description="全局上下文")


class StepResult(BaseModel):
    """步骤执行结果。"""

    step_id: str
    status: Literal["success", "failed", "skipped"]
    artifacts: list[Artifact] = Field(default_factory=list)
    evidence: list[EvidencePackage] = Field(default_factory=list)
    output: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class WorkflowResult(BaseModel):
    """工作流执行结果。"""

    workflow_id: str
    status: Literal["completed", "failed", "partially_completed"]
    steps: list[StepResult] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class WorkflowExecutor:
    """工作流执行器 — 混编原生服务、SCP 工具和 Skill 的步骤执行。

    用法:
        executor = WorkflowExecutor(service_registry, scp_executor, skill_executor)
        result = executor.execute(workflow_def)
    """

    def __init__(
        self,
        service_registry: dict[str, NativeScientificService] | None = None,
        scp_executor: object | None = None,
        skill_executor: object | None = None,
    ):
        self._service_registry = service_registry or {}
        self._scp_executor = scp_executor
        self._skill_executor = skill_executor

    def register_service(self, service_id: str, service: NativeScientificService) -> None:
        """注册原生服务。"""
        self._service_registry[service_id] = service

    def execute(self, workflow: WorkflowDefinition) -> WorkflowResult:
        """按拓扑顺序执行工作流步骤。"""
        workflow.workflow_id = workflow.workflow_id or f"wf-{uuid4().hex[:12]}"
        step_results: dict[str, StepResult] = {}
        errors: list[str] = []

        # 拓扑排序
        ordered = self._topological_sort(workflow.steps)

        for step in ordered:
            # 检查依赖是否全部成功
            deps_success = all(
                step_results.get(dep) and step_results[dep].status == "success"
                for dep in step.depends_on
            )
            if not deps_success:
                logger.warning("跳过步骤 %s: 依赖未就绪", step.step_id)
                result = StepResult(step_id=step.step_id, status="skipped")
                step_results[step.step_id] = result
                continue

            try:
                result = self._execute_step(step, step_results, workflow)
                step_results[step.step_id] = result
            except Exception as exc:
                logger.error("步骤 %s 执行失败: %s", step.step_id, exc)
                result = StepResult(
                    step_id=step.step_id,
                    status="failed",
                    error=str(exc),
                )
                step_results[step.step_id] = result
                errors.append(f"步骤 {step.step_id} 失败: {exc}")

                if step.on_failure == "stop":
                    break
                elif step.on_failure == "fallback":
                    try:
                        fallback_step = step.model_copy(update={"input": step.fallback_input})
                        fb_result = self._execute_step(fallback_step, step_results, workflow)
                        step_results[step.step_id] = fb_result
                    except Exception as fb_exc:
                        errors.append(f"步骤 {step.step_id} 回退也失败: {fb_exc}")
                        if step.on_failure == "stop":
                            break

        # 汇总结果
        all_results = list(step_results.values())
        has_failed = any(r.status == "failed" for r in all_results)
        all_success = all(r.status == "success" for r in all_results)

        return WorkflowResult(
            workflow_id=workflow.workflow_id,
            status="completed" if all_success else ("partially_completed" if has_failed else "completed"),
            steps=all_results,
            errors=errors,
        )

    def _execute_step(
        self,
        step: WorkflowStep,
        step_results: dict[str, StepResult],
        workflow: WorkflowDefinition,
    ) -> StepResult:
        """执行单个步骤。"""
        resolved_input = self._resolve_input(step.input, step_results)
        context = {**workflow.context, "project_id": workflow.project_id}

        if step.type == "native":
            return self._execute_native(step, resolved_input, context)
        elif step.type == "scp":
            return self._execute_scp(step, resolved_input, context)
        elif step.type == "skill":
            return self._execute_skill(step, resolved_input, context)
        else:
            raise ValueError(f"不支持的步骤类型: {step.type}")

    def _execute_native(
        self,
        step: WorkflowStep,
        resolved_input: dict[str, Any],
        context: dict[str, Any],
    ) -> StepResult:
        """执行原生服务步骤。"""
        service = self._service_registry.get(step.service_id)
        if service is None:
            raise ValueError(f"未注册的原生服务: {step.service_id}")

        task = Task(
            project_id=context.get("project_id", ""),
            capability_id=service.capability_id,
            title=step.description or step.service_id,
            metadata=resolved_input,
        )

        try:
            evidence = service.run_full_cycle(task, context)
            return StepResult(
                step_id=step.step_id,
                status="success",
                evidence=evidence,
                output={"evidence_count": len(evidence)},
            )
        except Exception as exc:
            raise RuntimeError(f"原生服务 {step.service_id} 执行失败: {exc}") from exc

    def _execute_scp(
        self,
        step: WorkflowStep,
        resolved_input: dict[str, Any],
        context: dict[str, Any],
    ) -> StepResult:
        """执行 SCP 工具步骤。"""
        if self._scp_executor is None:
            raise RuntimeError("SCP 执行器未配置")

        # 通过 SCP 执行器调用
        if hasattr(self._scp_executor, "execute"):
            result = self._scp_executor.execute(step.service_id, resolved_input)
        else:
            # 兼容 ToolGateway 模式
            result = self._scp_executor.invoke(context, step.service_id, resolved_input)

        return StepResult(
            step_id=step.step_id,
            status="success",
            output={"result": result} if not isinstance(result, dict) else result,
        )

    def _execute_skill(
        self,
        step: WorkflowStep,
        resolved_input: dict[str, Any],
        context: dict[str, Any],
    ) -> StepResult:
        """执行 Skill 步骤。"""
        if self._skill_executor is None:
            raise RuntimeError("Skill 执行器未配置")

        # 通过 Skill 执行器调用
        if hasattr(self._skill_executor, "execute"):
            result = self._skill_executor.execute(step.service_id, resolved_input)
        elif hasattr(self._skill_executor, "run"):
            result = self._skill_executor.run(step.service_id, resolved_input)
        else:
            result = self._skill_executor(step.service_id, resolved_input)

        return StepResult(
            step_id=step.step_id,
            status="success",
            output={"result": result} if not isinstance(result, dict) else result,
        )

    @staticmethod
    def _resolve_input(
        raw_input: dict[str, Any],
        step_results: dict[str, StepResult],
    ) -> dict[str, Any]:
        """解析输入中的 $ref 引用。

        $ref 语法: {"$ref": "step_id.output_key"} 或 {"$ref": "step_id"}
        """
        resolved: dict[str, Any] = {}
        for key, value in raw_input.items():
            if isinstance(value, dict) and "$ref" in value:
                ref_path = value["$ref"]
                parts = ref_path.split(".", 1)
                ref_step_id = parts[0]
                ref_key = parts[1] if len(parts) > 1 else "output"

                prev = step_results.get(ref_step_id)
                if prev is None:
                    raise ValueError(f"引用不存在的步骤: {ref_step_id}")

                if ref_key == "output":
                    resolved[key] = prev.output
                else:
                    resolved[key] = prev.output.get(ref_key)
            else:
                resolved[key] = value
        return resolved

    @staticmethod
    def _topological_sort(steps: list[WorkflowStep]) -> list[WorkflowStep]:
        """拓扑排序（Kahn 算法）。"""
        step_map = {s.step_id: s for s in steps}
        in_degree: dict[str, int] = {s.step_id: 0 for s in steps}
        adjacency: dict[str, list[str]] = {s.step_id: [] for s in steps}

        for s in steps:
            for dep in s.depends_on:
                if dep in step_map:
                    adjacency[dep].append(s.step_id)
                    in_degree[s.step_id] = in_degree.get(s.step_id, 0) + 1

        queue = [sid for sid, deg in in_degree.items() if deg == 0]
        ordered: list[WorkflowStep] = []

        while queue:
            sid = queue.pop(0)
            ordered.append(step_map[sid])
            for neighbor in adjacency.get(sid, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        # 检查是否有环
        if len(ordered) != len(steps):
            raise ValueError("工作流步骤中存在循环依赖")

        return ordered