"""反应网络分析 API 路由。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..contracts.evidence import EvidencePackage
from ..services.reaction_network.application import ReactionNetworkApplication

router = APIRouter(prefix="/v1/reaction-network", tags=["reaction-network"])
service = ReactionNetworkApplication()


class EnumerateReactionsRequest(BaseModel):
    """反应枚举请求。"""
    project_id: str = Field(..., description="项目 ID")
    reactant_smiles: list[str] = Field(..., description="反应物 SMILES 列表")
    charge: int = Field(default=0, description="总电荷")
    multiplicity: int = Field(default=1, description="自旋多重度")
    max_break_bonds: int = Field(default=1, ge=0, le=2, description="最多断键数")
    max_form_bonds: int = Field(default=1, ge=0, le=2, description="最多成键数")
    max_candidates: int = Field(default=300, ge=1, le=1000, description="最大候选反应数")


class SearchTransitionStateRequest(BaseModel):
    """过渡态搜索请求。"""
    project_id: str = Field(..., description="项目 ID")
    reaction_smiles: str = Field(..., description="反应 SMILES (Reactant>>Product)")
    charge: int = Field(default=0, description="总电荷")
    multiplicity: int = Field(default=1, description="自旋多重度")
    config: dict[str, Any] | None = Field(default=None, description="TS 搜索配置（可选）")


class GrowNetworkRequest(BaseModel):
    """网络扩展请求。"""
    project_id: str = Field(..., description="项目 ID")
    reactants: list[str] = Field(..., description="初始反应物 SMILES 列表")
    max_layers: int = Field(default=3, ge=1, le=3, description="最大扩展层数")
    max_species: int = Field(default=250, ge=1, le=500, description="最大物种数")
    barrier_threshold: float = Field(default=40.0, gt=0, le=100, description="能垒阈值 (kcal/mol)")


@router.post("/enumerate", response_model=list[EvidencePackage])
def enumerate_reactions(req: EnumerateReactionsRequest):
    """枚举给定反应物可能的化学反应，返回证据包列表。"""
    return service.enumerate_reactions(
        project_id=req.project_id,
        reactant_smiles=req.reactant_smiles,
        charge=req.charge,
        multiplicity=req.multiplicity,
        max_break_bonds=req.max_break_bonds,
        max_form_bonds=req.max_form_bonds,
        max_candidates=req.max_candidates,
    )


@router.post("/ts-search", response_model=list[EvidencePackage])
def search_transition_state(req: SearchTransitionStateRequest):
    """搜索给定反应的过渡态，返回证据包列表。"""
    return service.search_transition_state(
        project_id=req.project_id,
        reaction_smiles=req.reaction_smiles,
        charge=req.charge,
        multiplicity=req.multiplicity,
        config=req.config,
    )


@router.post("/grow", response_model=list[EvidencePackage])
def grow_network(req: GrowNetworkRequest):
    """分层扩展反应网络，返回证据包列表。"""
    return service.grow_network(
        project_id=req.project_id,
        reactants=req.reactants,
        max_layers=req.max_layers,
        max_species=req.max_species,
        barrier_threshold=req.barrier_threshold,
    )