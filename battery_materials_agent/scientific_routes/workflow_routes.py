"""工作流混编执行 API 路由。"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from typing import Any

from ..contracts.evidence import EvidencePackage
from ..workflow import WorkflowStep, WorkflowDefinition, WorkflowExecutor
from ..services.registry import get_service_registry

router = APIRouter(prefix="/v1/workflow", tags=["workflow"])

# 从服务注册中心获取全部 12 个原生科学服务（单一事实来源）
_service_registry = get_service_registry()
_executor = WorkflowExecutor(service_registry=_service_registry)


class WorkflowStepRequest(BaseModel):
    """工作流步骤请求。"""
    step_id: str = Field(default="", description="步骤 ID")
    type: str = Field(..., description="步骤类型: native, scp, skill")
    service_id: str = Field(..., description="服务 ID")
    command: str = Field(default="", description="执行命令")
    input: dict[str, Any] = Field(default_factory=dict, description="输入参数")
    depends_on: list[str] = Field(default_factory=list, description="依赖步骤")
    on_failure: str = Field(default="stop", description="失败处理策略")
    fallback_input: dict[str, Any] = Field(default_factory=dict, description="回退参数")
    description: str = Field(default="", description="步骤描述")


class WorkflowExecuteRequest(BaseModel):
    """工作流执行请求。"""
    workflow_id: str = Field(default="", description="工作流 ID")
    name: str = Field(default="", description="工作流名称")
    steps: list[WorkflowStepRequest] = Field(..., description="步骤列表")
    project_id: str = Field(default="", description="项目 ID")
    context: dict[str, Any] = Field(default_factory=dict, description="全局上下文")


@router.post("/execute")
def execute_workflow(req: WorkflowExecuteRequest):
    """执行混编工作流。"""
    wf_steps = [
        WorkflowStep(
            step_id=s.step_id or f"step_{i}",
            type=s.type,
            service_id=s.service_id,
            command=s.command,
            input=s.input,
            depends_on=s.depends_on,
            on_failure=s.on_failure,
            fallback_input=s.fallback_input,
            description=s.description,
        )
        for i, s in enumerate(req.steps)
    ]

    definition = WorkflowDefinition(
        workflow_id=req.workflow_id,
        name=req.name,
        steps=wf_steps,
        project_id=req.project_id,
        context=req.context,
    )

    result = _executor.execute(definition)
    return result


@router.get("/services")
def list_workflow_services():
    """列出所有可用的工作流服务。"""
    return {
        "native_services": list(_service_registry.keys()),
        "supported_types": ["native", "scp", "skill"],
    }