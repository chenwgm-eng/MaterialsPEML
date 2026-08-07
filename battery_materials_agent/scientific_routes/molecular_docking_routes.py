"""分子对接 API 路由。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..contracts.task import Task
from ..contracts.artifact import Artifact
from ..contracts.evidence import EvidencePackage
from ..services.molecular_docking.application import (
    MolecularDockingApplication,
    DockSingle,
    DockBatch,
    AnalyzeDocking,
    ExportDocking,
)

router = APIRouter(prefix="/v1/molecular-docking", tags=["molecular-docking"])
service = MolecularDockingApplication()


class DockSingleRequest(BaseModel):
    """单次分子对接请求。"""
    project_id: str = Field(..., description="项目 ID")
    protein_path: str = Field(..., description="受体蛋白文件路径 (PDB/mmCIF)")
    ligand: str = Field(..., description="配体数据（SMILES 字符串或文件路径）")
    ligand_format: str = Field(default="smiles", description="配体格式: smiles, sdf, mol2")
    samples_per_complex: int = Field(default=10, description="每个复合物采样数 (1-50)")
    inference_steps: int = Field(default=20, description="扩散模型推理步数 (10-50)")
    device: str = Field(default="cpu", description="推理设备: cpu, cuda")


class DockSingleFullRequest(DockSingleRequest):
    """单次分子对接请求（全生命周期）。"""
    title: str = Field(default="", description="任务标题")
    description: str = Field(default="", description="任务描述")


class DockBatchRequest(BaseModel):
    """批量虚拟筛选请求。"""
    project_id: str = Field(..., description="项目 ID")
    complexes: list[dict] = Field(..., description="复合物列表，每项包含 receptor_path, ligand, ligand_format 等")
    config: dict = Field(default_factory=dict, description="全局配置")
    workers: int = Field(default=1, description="并行工作进程数 (1-16)")


class AnalyzeDockingRequest(BaseModel):
    """对接结果分析请求。"""
    project_id: str = Field(..., description="项目 ID")
    workdir: str = Field(..., description="对接结果工作目录")
    top_n: int = Field(default=20, description="返回 Top-N 位姿 (1-1000)")
    confidence_threshold: float = Field(default=0.0, description="置信度过滤阈值 (0.0-1.0)")


class ExportDockingRequest(BaseModel):
    """对接结果导出请求。"""
    project_id: str = Field(..., description="项目 ID")
    workdir: str = Field(..., description="对接结果工作目录")
    format: str = Field(default="sdf", description="导出格式: sdf, csv, html")


@router.post("/dock", response_model=list[Artifact])
def dock_single(req: DockSingleRequest):
    """单次分子对接，返回 Artifact 列表。"""
    task = Task(
        project_id=req.project_id,
        capability_id=service.capability_id,
        title="分子对接（单次）",
        description=f"受体 {req.protein_path}，配体 {req.ligand[:60]}",
        metadata={
            **req.model_dump(),
            "command": "dock_single",
        },
    )
    validation = service.validate(task, {})
    if not validation.get("valid", True):
        raise HTTPException(status_code=422, detail=validation.get("errors", []))

    run = service.prepare(task)
    artifacts = service.execute(run, {})
    return artifacts


@router.post("/dock/full", response_model=list[EvidencePackage])
def dock_single_full(req: DockSingleFullRequest):
    """全生命周期单次分子对接。"""
    evidence = service.dock_single(
        project_id=req.project_id,
        protein_path=req.protein_path,
        ligand=req.ligand,
        ligand_format=req.ligand_format,
        samples_per_complex=req.samples_per_complex,
        inference_steps=req.inference_steps,
        device=req.device,
    )
    return evidence


@router.post("/batch", response_model=list[Artifact])
def dock_batch(req: DockBatchRequest):
    """批量虚拟筛选，返回 Artifact 列表。"""
    from ..services.molecular_docking.validators import validate_batch_params

    validation = validate_batch_params(req.complexes, req.workers)
    if not validation.get("valid", True):
        raise HTTPException(status_code=422, detail=validation.get("errors", []))

    task = Task(
        project_id=req.project_id,
        capability_id=service.capability_id,
        title="分子对接（批量虚拟筛选）",
        description=f"批量筛选 {len(req.complexes)} 个复合物，{req.workers} 个工作进程",
        metadata={
            **req.model_dump(),
            "command": "dock_batch",
        },
    )
    run = service.prepare(task)
    artifacts = service.execute(run, {})
    return artifacts


@router.post("/batch/full", response_model=list[EvidencePackage])
def dock_batch_full(req: DockBatchRequest):
    """全生命周期批量虚拟筛选。"""
    evidence = service.dock_batch(
        project_id=req.project_id,
        complexes=req.complexes,
        config=req.config,
        workers=req.workers,
    )
    return evidence


@router.post("/analyze", response_model=list[Artifact])
def analyze_docking(req: AnalyzeDockingRequest):
    """对接结果分析，返回 Artifact 列表。"""
    from ..services.molecular_docking.validators import validate_confidence_threshold, validate_top_n

    tn_result = validate_top_n(req.top_n)
    ct_result = validate_confidence_threshold(req.confidence_threshold)
    if tn_result.get("errors") or ct_result.get("errors"):
        errors = tn_result.get("errors", []) + ct_result.get("errors", [])
        raise HTTPException(status_code=422, detail=errors)

    task = Task(
        project_id=req.project_id,
        capability_id=service.capability_id,
        title="对接结果分析",
        description=f"分析 {req.workdir} 中的对接结果，Top-{req.top_n}",
        metadata={
            **req.model_dump(),
            "command": "analyze_docking",
        },
    )
    run = service.prepare(task)
    artifacts = service.execute(run, {})
    return artifacts


@router.post("/analyze/full", response_model=list[EvidencePackage])
def analyze_docking_full(req: AnalyzeDockingRequest):
    """全生命周期对接结果分析。"""
    evidence = service.analyze_docking(
        project_id=req.project_id,
        workdir=req.workdir,
        top_n=req.top_n,
        confidence_threshold=req.confidence_threshold,
    )
    return evidence


@router.post("/export", response_model=list[Artifact])
def export_docking(req: ExportDockingRequest):
    """对接结果导出，返回 Artifact 列表。"""
    if req.format not in ("sdf", "csv", "html"):
        raise HTTPException(
            status_code=422,
            detail=f"不支持的导出格式 '{req.format}'，支持: sdf, csv, html",
        )

    task = Task(
        project_id=req.project_id,
        capability_id=service.capability_id,
        title="对接结果导出",
        description=f"导出 {req.workdir} 中的对接结果，格式 {req.format}",
        metadata={
            **req.model_dump(),
            "command": "export_docking",
        },
    )
    run = service.prepare(task)
    artifacts = service.execute(run, {})
    return artifacts


@router.post("/export/full", response_model=list[EvidencePackage])
def export_docking_full(req: ExportDockingRequest):
    """全生命周期对接结果导出。"""
    evidence = service.export_docking(
        project_id=req.project_id,
        workdir=req.workdir,
        format=req.format,
    )
    return evidence


@router.get("/formats")
def list_formats():
    """列出支持的受体和配体格式。"""
    from ..services.molecular_docking.validators import RECEPTOR_FORMATS, LIGAND_FORMATS
    return {
        "receptor_formats": [
            {"key": k, "description": v["description"], "extensions": sorted(v["extensions"])}
            for k, v in RECEPTOR_FORMATS.items()
        ],
        "ligand_formats": [
            {"key": k, "description": v["description"]}
            for k, v in LIGAND_FORMATS.items()
        ],
    }