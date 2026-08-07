"""波函数分析 API 路由。"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..contracts.task import Task
from ..contracts.artifact import Artifact
from ..contracts.evidence import EvidencePackage
from ..services.wavefunction_analysis.application import WavefunctionAnalysisApplication

router = APIRouter(prefix="/v1/wavefunction-analysis", tags=["wavefunction-analysis"])
service = WavefunctionAnalysisApplication()


class AnalyzeESPRequest(BaseModel):
    """ESP 分析请求。"""
    project_id: str = Field(..., description="项目 ID")
    input_file: str = Field(..., description="波函数文件路径")
    file_format: str = Field(..., description="文件格式: molden, fchk, wfn, wfx")
    surface_type: str = Field(default="molecular", description="ESP 表面类型: molecular, vdw, electron_density")
    bins: int = Field(default=100, description="ESP 区间数")
    generate_cubes: bool = Field(default=True, description="是否生成 Cube 文件")


class AnalyzeESPFullRequest(AnalyzeESPRequest):
    """ESP 分析请求（全生命周期）。"""
    title: str = Field(default="", description="任务标题")
    description: str = Field(default="", description="任务描述")


class AnalyzeOrbitalsRequest(BaseModel):
    """轨道分析请求。"""
    project_id: str = Field(..., description="项目 ID")
    input_file: str = Field(..., description="波函数文件路径")
    file_format: str = Field(..., description="文件格式: molden, fchk, wfn, wfx")
    below_homo: int = Field(default=3, description="HOMO 以下轨道数")
    above_lumo: int = Field(default=3, description="LUMO 以上轨道数")
    grid_quality: str = Field(default="high", description="网格质量: low, medium, high, very_high")


class AnalyzeOrbitalsFullRequest(AnalyzeOrbitalsRequest):
    """轨道分析请求（全生命周期）。"""
    title: str = Field(default="", description="任务标题")
    description: str = Field(default="", description="任务描述")


class RenderOrbitalRequest(BaseModel):
    """渲染请求。"""
    project_id: str = Field(..., description="项目 ID")
    input_dir: str = Field(..., description="含有 Cube 文件的目录路径")
    render_type: str = Field(..., description="渲染类型: esp, orbital")
    image_format: str = Field(default="png", description="图片格式: png, tiff, bmp, jpg, tga")
    width: int = Field(default=1800, description="渲染宽度 (px)")
    height: int = Field(default=1200, description="渲染高度 (px)")


class RenderOrbitalFullRequest(RenderOrbitalRequest):
    """渲染请求（全生命周期）。"""
    title: str = Field(default="", description="任务标题")
    description: str = Field(default="", description="任务描述")


class BatchAnalysisRequest(BaseModel):
    """批量分析请求。"""
    project_id: str = Field(..., description="项目 ID")
    files: list[str] = Field(..., description="波函数文件路径列表")
    mode: str = Field(..., description="分析模式: esp, orbital")
    workers: int = Field(default=1, description="并行 worker 数")
    fail_fast: bool = Field(default=False, description="失败时是否立即停止")


@router.post("/esp", response_model=list[Artifact])
def analyze_esp(req: AnalyzeESPRequest):
    """执行 ESP 分析，返回 Artifact 列表。"""
    task = Task(
        project_id=req.project_id,
        capability_id=service.capability_id,
        title="ESP 分析",
        description=f"文件格式 {req.file_format}，表面类型 {req.surface_type}",
        metadata={"command": "analyze_esp", **req.model_dump()},
    )
    run = service.prepare(task)
    artifacts = service.execute(run, {})
    return artifacts


@router.post("/esp/full", response_model=list[EvidencePackage])
def analyze_esp_full(req: AnalyzeESPFullRequest):
    """全生命周期 ESP 分析。"""
    evidence = service.analyze_esp(
        project_id=req.project_id,
        input_file=req.input_file,
        file_format=req.file_format,
        surface_type=req.surface_type,
        bins=req.bins,
        generate_cubes=req.generate_cubes,
    )
    return evidence


@router.post("/orbitals", response_model=list[Artifact])
def analyze_orbitals(req: AnalyzeOrbitalsRequest):
    """执行轨道分析，返回 Artifact 列表。"""
    task = Task(
        project_id=req.project_id,
        capability_id=service.capability_id,
        title="轨道分析",
        description=f"文件格式 {req.file_format}，{req.below_homo} below HOMO + {req.above_lumo} above LUMO",
        metadata={"command": "analyze_orbitals", **req.model_dump()},
    )
    run = service.prepare(task)
    artifacts = service.execute(run, {})
    return artifacts


@router.post("/orbitals/full", response_model=list[EvidencePackage])
def analyze_orbitals_full(req: AnalyzeOrbitalsFullRequest):
    """全生命周期轨道分析。"""
    evidence = service.analyze_orbitals(
        project_id=req.project_id,
        input_file=req.input_file,
        file_format=req.file_format,
        below_homo=req.below_homo,
        above_lumo=req.above_lumo,
        grid_quality=req.grid_quality,
    )
    return evidence


@router.post("/render", response_model=list[Artifact])
def render_orbital(req: RenderOrbitalRequest):
    """执行渲染，返回 Artifact 列表。"""
    task = Task(
        project_id=req.project_id,
        capability_id=service.capability_id,
        title="波函数渲染",
        description=f"渲染类型 {req.render_type}，格式 {req.image_format}，{req.width}x{req.height}",
        metadata={"command": "render_orbital", **req.model_dump()},
    )
    run = service.prepare(task)
    artifacts = service.execute(run, {})
    return artifacts


@router.post("/render/full", response_model=list[EvidencePackage])
def render_orbital_full(req: RenderOrbitalFullRequest):
    """全生命周期渲染。"""
    evidence = service.render_orbital(
        project_id=req.project_id,
        input_dir=req.input_dir,
        render_type=req.render_type,
        image_format=req.image_format,
        width=req.width,
        height=req.height,
    )
    return evidence


@router.post("/batch", response_model=list[list[EvidencePackage]])
def batch_analysis(req: BatchAnalysisRequest):
    """批量分析。"""
    all_evidence = service.batch_analysis(
        project_id=req.project_id,
        files=req.files,
        mode=req.mode,
        workers=req.workers,
        fail_fast=req.fail_fast,
    )
    return all_evidence


@router.get("/formats")
def list_formats():
    """列出所有支持的波函数文件格式。"""
    from ..services.wavefunction_analysis.validators import SUPPORTED_FILE_FORMATS
    return {
        "count": len(SUPPORTED_FILE_FORMATS),
        "formats": [
            {"key": k, "description": v["description"], "extensions": list(v["extensions"])}
            for k, v in SUPPORTED_FILE_FORMATS.items()
        ],
    }


@router.get("/surface-types")
def list_surface_types():
    """列出所有支持的 ESP 表面类型。"""
    from ..services.wavefunction_analysis.validators import SUPPORTED_SURFACE_TYPES
    return {
        "count": len(SUPPORTED_SURFACE_TYPES),
        "surface_types": [
            {"key": k, "description": v}
            for k, v in SUPPORTED_SURFACE_TYPES.items()
        ],
    }