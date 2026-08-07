"""配方与堆积优化 API 路由。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..contracts.task import Task
from ..contracts.artifact import Artifact
from ..services.formulation_packing.application import FormulationPackingApplication

router = APIRouter(prefix="/v1/formulation", tags=["formulation"])
service = FormulationPackingApplication()


# ── Request/Response Schemas ───────────────────────────────

class OptimizeRequest(BaseModel):
    """配方优化请求。"""
    project_id: str
    components: list[dict] = Field(
        ..., description="组分列表，每项包含 {name, smiles, ratio_range_min, ratio_range_max, constraints}"
    )
    target_properties: list[str] = Field(
        ..., description="目标优化属性列表"
    )
    optimization_goal: str = Field(
        ..., description="优化目标: maximize / minimize / target"
    )
    constraints: dict = Field(default_factory=dict, description="附加约束条件")
    max_iterations: int = Field(default=1000, ge=1, description="最大迭代次数")


class PackRequest(BaseModel):
    """分子堆积请求。"""
    project_id: str
    molecules: list[str] = Field(..., description="待堆积分子的 SMILES 列表")
    packing_type: str = Field(..., description="堆积类型: crystal / amorphous / solvation")
    target_density: float | None = Field(default=None, description="目标密度 (g/cm³)")
    box_size_nm: float | None = Field(default=None, description="盒子边长 (nm)")
    force_field: str = Field(default="uff", description="力场名称")


# ── 能力目录 ────────────────────────────────────────────────

_CAPABILITIES: dict[str, dict[str, str]] = {
    "formulation_optimization": {
        "name": "配方优化",
        "description": "组分比例搜索与性能优化，支持多目标优化和约束条件",
    },
    "packing": {
        "name": "分子堆积",
        "description": "分子堆积结构生成，支持晶体/无定形/溶剂化三种堆积类型",
    },
}


# ── Routes ─────────────────────────────────────────────────

@router.post("/optimize", response_model=list[Artifact])
def optimize(req: OptimizeRequest):
    """优化配方组分比例。

    创建 Task 和 Run，执行配方优化，返回结果工件。
    """
    task = Task(
        project_id=req.project_id,
        capability_id=service.capability_id,
        title="配方优化",
        description=f"优化 {len(req.components)} 种组分的配比，目标: {req.optimization_goal}",
        metadata={
            "command": "formulation_optimization",
            "input": {
                "components": req.components,
                "target_properties": req.target_properties,
                "optimization_goal": req.optimization_goal,
                "constraints": req.constraints,
                "max_iterations": req.max_iterations,
            },
        },
    )
    run = service.prepare(task)
    artifacts = service.execute(run, {})
    return artifacts


@router.post("/pack", response_model=list[Artifact])
def pack(req: PackRequest):
    """生成分子堆积结构。

    创建 Task 和 Run，执行分子堆积，返回结构工件。
    """
    task = Task(
        project_id=req.project_id,
        capability_id=service.capability_id,
        title="分子堆积",
        description=f"{req.packing_type} 堆积，{len(req.molecules)} 个分子",
        metadata={
            "command": "packing",
            "input": {
                "molecules": req.molecules,
                "packing_type": req.packing_type,
                "target_density": req.target_density,
                "box_size_nm": req.box_size_nm,
                "force_field": req.force_field,
            },
        },
    )
    run = service.prepare(task)
    artifacts = service.execute(run, {})
    return artifacts


@router.get("/capabilities")
def list_capabilities():
    """列出所有配方与堆积能力。"""
    return {
        "count": len(_CAPABILITIES),
        "capabilities": [
            {
                "key": key,
                "name": meta["name"],
                "description": meta["description"],
            }
            for key, meta in _CAPABILITIES.items()
        ],
    }


@router.get("/candidate-components")
def candidate_components(candidate_id: str, request: Request):
    """从候选材料的配方成分信息生成配方优化所需的 components 列表。

    数据来源（按优先级合并去重）：
    1. 候选 BOM 方案中的 formulation.materials（原料配比）
    2. 候选材料自身的 data.components（复合体系）
    3. 企业物料库反查（find_raw_materials_for_candidate）

    Returns:
        {"candidate_id", "candidate_name", "components", "count"}，
        components 每项为 {name, smiles, ratio_range_min, ratio_range_max, source}。
    """
    candidate_store = getattr(request.app.state, "candidate_store", None)
    if candidate_store is None:
        raise HTTPException(status_code=503, detail="候选存储不可用")
    cand = candidate_store.get(candidate_id)
    if cand is None:
        raise HTTPException(status_code=404, detail=f"候选材料 {candidate_id} 不存在")

    # 物料库（可选，缺省时仅用候选自身信息）
    agent = getattr(request.app.state, "agent", None)
    raw_db = getattr(agent, "raw_material_db", None) if agent is not None else None

    def _lookup_smiles(name: str) -> str:
        """从物料库按名称精确匹配 SMILES。"""
        if raw_db is None or not name:
            return ""
        try:
            target = name.strip().lower()
            for spec in raw_db.get_all():
                if spec.name and spec.name.strip().lower() == target:
                    return spec.smiles or ""
        except Exception:
            pass
        return ""

    components: list[dict] = []
    seen: set[str] = set()

    def _add(name: str, smiles: str, source: str) -> None:
        name = (name or "").strip()
        if not name or name in seen:
            return
        seen.add(name)
        components.append({
            "name": name,
            "smiles": smiles or _lookup_smiles(name),
            "ratio_range_min": 0.0,
            "ratio_range_max": 1.0,
            "source": source,
        })

    # 1. 候选 BOM formulation.materials（最新一条）
    bom_store = getattr(request.app.state, "bom_store", None)
    if bom_store is not None:
        try:
            boms = bom_store.list_by_candidate(candidate_id)
            if boms:
                formulation = boms[0].formulation if isinstance(boms[0].formulation, dict) else {}
                for m in formulation.get("materials") or []:
                    name = m.get("material_name") or m.get("name") or ""
                    if name:
                        _add(name, "", "bom")
        except Exception:
            pass

    # 2. 候选自身 data.components（复合体系）
    cand_data = cand.data if isinstance(cand.data, dict) else {}
    for c in cand_data.get("components") or []:
        if not isinstance(c, dict):
            continue
        name = c.get("formula") or c.get("name") or ""
        smiles = c.get("smiles") or ""
        if name:
            _add(name, smiles, "candidate_components")

    # 3. 物料库反查可用原料
    if raw_db is not None:
        try:
            matched = raw_db.find_raw_materials_for_candidate(
                formula=cand.name or "", smiles=cand.smiles or "",
            )
            for spec in matched:
                _add(spec.name or spec.material_id, spec.smiles or "", "material_db")
        except Exception:
            pass

    # 兜底：候选自身作为单一组分
    if not components:
        _add(cand.name or cand.candidate_id, cand.smiles or "", "candidate_self")

    return {
        "candidate_id": candidate_id,
        "candidate_name": cand.name or cand.candidate_id,
        "components": components,
        "count": len(components),
    }