"""化学性质查询 API 路由。"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..contracts.task import Task
from ..contracts.artifact import Artifact
from ..contracts.evidence import EvidencePackage
from ..services.chemical_property.application import ChemicalPropertyApplication, MODULE_CATALOG

router = APIRouter(prefix="/v1/chemical", tags=["chemical"])
service = ChemicalPropertyApplication()


# ── Request/Response Schemas ───────────────────────────────

class QueryRequest(BaseModel):
    """化学性质查询请求（直接执行）。"""
    project_id: str
    compound_name: str = Field(
        description='化合物名称、SMILES 或 CAS 号；M3(VLE)/M4(闪蒸) 需二元混合物，格式为 "A/B"（如 "ethanol/water"）'
    )
    module: str = Field(description="查询模块: M1(标准常数), M2(T/P依赖), M3(VLE), M4(闪蒸), M5(溶解度)")
    temperature_k: float | None = Field(default=None, description="温度 (K)")
    pressure_pa: float | None = Field(default=None, description="压力 (Pa)")
    composition: list[float] | None = Field(default=None, description="摩尔分数列表（M3/M4 必填）")
    property_keys: list[str] | None = Field(default=None, description="要查询的特定性质")


class QueryFullRequest(BaseModel):
    """化学性质查询请求（全生命周期）。"""
    project_id: str
    compound_name: str = Field(
        description='化合物名称、SMILES 或 CAS 号；M3(VLE)/M4(闪蒸) 需二元混合物，格式为 "A/B"（如 "ethanol/water"）'
    )
    module: str = Field(description="查询模块: M1(标准常数), M2(T/P依赖), M3(VLE), M4(闪蒸), M5(溶解度)")
    temperature_k: float | None = Field(default=None, description="温度 (K)")
    pressure_pa: float | None = Field(default=None, description="压力 (Pa)")
    composition: list[float] | None = Field(default=None, description="摩尔分数列表（M3/M4 必填）")
    property_keys: list[str] | None = Field(default=None, description="要查询的特定性质")
    title: str = Field(default="", description="任务标题")
    description: str = Field(default="", description="任务描述")


# ── Routes ─────────────────────────────────────────────────

@router.post("/query", response_model=list[Artifact])
def query(req: QueryRequest):
    """直接执行化学性质查询，返回 Artifact 列表。

    创建 Task 和 Run，执行查询，返回结果工件。
    """
    module_name = MODULE_CATALOG.get(req.module, {}).get("name", req.module)
    task = Task(
        project_id=req.project_id,
        capability_id=service.capability_id,
        title="化学性质查询",
        description=f"{req.compound_name} - {module_name}",
        metadata={
            "compound_name": req.compound_name,
            "module": req.module,
            "temperature_k": req.temperature_k,
            "pressure_pa": req.pressure_pa,
            "composition": req.composition,
            "property_keys": req.property_keys,
        },
    )
    run = service.prepare(task)
    artifacts = service.execute(run, {})
    return artifacts


@router.post("/query/full", response_model=list[EvidencePackage])
def query_full(req: QueryFullRequest):
    """全生命周期化学性质查询。

    创建 Task → 创建 Run → 执行 → 后处理 → 返回 EvidencePackage。
    """
    module_name = MODULE_CATALOG.get(req.module, {}).get("name", req.module)
    title = req.title or "化学性质查询"
    desc = req.description or f"{req.compound_name} - {module_name}"

    task = Task(
        project_id=req.project_id,
        capability_id=service.capability_id,
        title=title,
        description=desc,
        metadata={
            "compound_name": req.compound_name,
            "module": req.module,
            "temperature_k": req.temperature_k,
            "pressure_pa": req.pressure_pa,
            "composition": req.composition,
            "property_keys": req.property_keys,
        },
    )
    return service.run_full_cycle(task)


@router.get("/modules")
def list_modules():
    """列出所有可用的化学查询模块（M1-M5）。"""
    return {
        "count": len(MODULE_CATALOG),
        "modules": [
            {
                "key": key,
                "name": meta["name"],
                "description": meta["description"],
                "sources": meta.get("sources", ""),
                "params": meta.get("params", ""),
            }
            for key, meta in MODULE_CATALOG.items()
        ],
    }