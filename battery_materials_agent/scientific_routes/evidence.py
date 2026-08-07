"""Evidence 管理 API 路由。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..contracts.evidence import EvidencePackage, EvidenceLevel
from ..domain.runtime import ScientificExecutionKernel

router = APIRouter(prefix="/v1", tags=["evidence"])
kernel = ScientificExecutionKernel()


class StoreEvidenceRequest(BaseModel):
    run_id: str
    task_id: str
    claim: str
    value: str | dict | list | None = None
    unit: str = ""
    confidence: float = 1.0
    level: EvidenceLevel = EvidenceLevel.MEDIUM
    method: str = ""
    source_type: str = "real_engine"
    source_service: str = ""
    metadata: dict = {}


@router.post("/evidence", response_model=EvidencePackage)
def store_evidence(req: StoreEvidenceRequest):
    evidence = EvidencePackage(
        run_id=req.run_id,
        task_id=req.task_id,
        claim=req.claim,
        value=req.value,
        unit=req.unit,
        confidence=req.confidence,
        level=req.level,
        method=req.method,
        source_type=req.source_type,
        source_service=req.source_service,
        metadata=req.metadata,
    )
    return kernel.store_evidence(evidence)


@router.get("/evidence/{evidence_id}", response_model=EvidencePackage)
def get_evidence(evidence_id: str):
    """通过 evidence_id 直接查询单个证据包。"""
    ev = kernel.get_evidence_by_id(evidence_id)
    if ev is None:
        raise HTTPException(status_code=404, detail="Evidence not found")
    return ev