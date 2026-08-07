"""科学任务/Run 管理 API 路由。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..contracts.task import Task, TaskStatus, TaskPriority
from ..contracts.run import Run, RunStatus
from ..domain.runtime import ScientificExecutionKernel

router = APIRouter(prefix="/v1", tags=["scientific-runs"])
kernel = ScientificExecutionKernel()


# ── Request/Response Schemas ───────────────────────────────

class CreateTaskRequest(BaseModel):
    project_id: str
    capability_id: str
    title: str
    description: str = ""
    priority: TaskPriority = TaskPriority.NORMAL
    input_schema_version: str = "1.0.0"
    metadata: dict = {}


class SubmitRunRequest(BaseModel):
    task_id: str
    project_id: str
    service_id: str
    command: str
    input: dict = {}
    metadata: dict = {}


class UpdateRunStatusRequest(BaseModel):
    status: RunStatus


# ── Tasks ──────────────────────────────────────────────────

@router.post("/tasks", response_model=Task)
def create_task(req: CreateTaskRequest):
    task = Task(
        project_id=req.project_id,
        capability_id=req.capability_id,
        title=req.title,
        description=req.description,
        priority=req.priority,
        input_schema_version=req.input_schema_version,
        metadata=req.metadata,
    )
    return kernel.create_task(task)


@router.get("/tasks/{task_id}", response_model=Task)
def get_task(task_id: str):
    task = kernel.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.get("/tasks", response_model=list[Task])
def list_tasks(project_id: str | None = None, limit: int = 50, offset: int = 0):
    return kernel.list_tasks(project_id=project_id, limit=limit, offset=offset)


# ── Runs ───────────────────────────────────────────────────

@router.post("/runs", response_model=Run)
def submit_run(req: SubmitRunRequest):
    run = Run(
        task_id=req.task_id,
        project_id=req.project_id,
        service_id=req.service_id,
        command=req.command,
        input=req.input,
        metadata=req.metadata,
    )
    return kernel.submit_run(run)


@router.get("/runs/{run_id}", response_model=Run)
def get_run(run_id: str):
    run = kernel.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.post("/runs/{run_id}/cancel", response_model=Run)
def cancel_run(run_id: str):
    try:
        return kernel.cancel_run(run_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/runs/{run_id}/resume", response_model=Run)
def resume_run(run_id: str):
    try:
        return kernel.resume_run(run_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/runs", response_model=list[Run])
def list_runs(
    task_id: str | None = None,
    project_id: str | None = None,
    status: RunStatus | None = None,
    limit: int = 50,
    offset: int = 0,
):
    return kernel.list_runs(
        task_id=task_id,
        project_id=project_id,
        status=status,
        limit=limit,
        offset=offset,
    )


# ── Artifacts ──────────────────────────────────────────────

@router.get("/runs/{run_id}/artifacts", response_model=list)
def get_artifacts(run_id: str):
    return kernel.get_artifacts(run_id)


# ── Evidence ───────────────────────────────────────────────

@router.get("/runs/{run_id}/evidence", response_model=list)
def get_evidence(run_id: str):
    return kernel.get_evidence(run_id)