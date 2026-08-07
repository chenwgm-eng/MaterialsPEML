"""材料结构生成与优化 API 路由。"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..contracts.task import Task
from ..contracts.artifact import Artifact
from ..services.materials_structure.application import StructureApplication
from ..services.materials_structure.validators import SUPPORTED_FORMATS

router = APIRouter(prefix="/v1/structure", tags=["structure"])
service = StructureApplication()


# ── Request/Response Schemas ───────────────────────────────

class GenerateRequest(BaseModel):
    """结构生成请求。"""
    project_id: str
    input_format: str = Field(description="输入格式: smiles, formula, cif, xyz")
    input_data: str = Field(description="输入数据字符串")
    output_formats: list[str] = Field(
        default=["smiles", "xyz", "cif", "mol"],
        description="请求的输出格式列表",
    )
    optimization_level: str = Field(default="none", description="优化级别: none, basic, full")
    force_field: str | None = Field(default=None, description="力场类型: uff, mmff94")


class OptimizeRequest(BaseModel):
    """结构优化请求。"""
    project_id: str
    structure_data: str = Field(description="待优化的结构数据")
    format: str = Field(description="输入格式")
    optimization_level: str = Field(description="优化级别: basic, full")
    max_iterations: int = Field(default=500, description="最大迭代次数")


class ConvertRequest(BaseModel):
    """结构格式转换请求。"""
    project_id: str
    input_format: str = Field(description="输入格式: smiles, cif, xyz, mol, pdb, sdf, mol2")
    input_data: str = Field(description="输入数据字符串")
    output_format: str = Field(description="目标输出格式")


# ── Routes ─────────────────────────────────────────────────

@router.post("/generate", response_model=list[Artifact])
def generate(req: GenerateRequest):
    """从 SMILES 或其他格式生成分子/晶体结构。"""
    task = Task(
        project_id=req.project_id,
        capability_id=service.capability_id,
        title="结构生成",
        description=f"从 {req.input_format} 生成结构，输出 {req.output_formats}",
        metadata={
            "operation": "generate",
            "input_format": req.input_format,
            "input_data": req.input_data,
            "output_formats": req.output_formats,
            "optimization_level": req.optimization_level,
            "force_field": req.force_field,
        },
    )
    run = service.prepare(task)
    artifacts = service.execute(run, {})
    return artifacts


@router.post("/optimize", response_model=list[Artifact])
def optimize(req: OptimizeRequest):
    """优化分子/晶体结构几何构型。"""
    task = Task(
        project_id=req.project_id,
        capability_id=service.capability_id,
        title="结构优化",
        description=f"优化 {req.format} 结构，级别: {req.optimization_level}",
        metadata={
            "operation": "optimize",
            "input_format": req.format,
            "input_data": req.structure_data,
            "output_formats": [req.format],
            "optimization_level": req.optimization_level,
            "max_iterations": req.max_iterations,
        },
    )
    run = service.prepare(task)
    artifacts = service.execute(run, {})
    return artifacts


@router.post("/convert", response_model=list[Artifact])
def convert(req: ConvertRequest):
    """转换结构格式。

    将输入格式的结构数据转换为目标格式。
    """
    task = Task(
        project_id=req.project_id,
        capability_id=service.capability_id,
        title="结构格式转换",
        description=f"{req.input_format} → {req.output_format}",
        metadata={
            "operation": "convert",
            "input_format": req.input_format,
            "input_data": req.input_data,
            "output_formats": [req.output_format],
            "optimization_level": "none",
        },
    )
    run = service.prepare(task)
    artifacts = service.execute(run, {})
    return artifacts


@router.get("/formats")
def list_formats():
    """列出所有支持的结构格式。"""
    return {
        "count": len(SUPPORTED_FORMATS),
        "formats": sorted(SUPPORTED_FORMATS),
    }