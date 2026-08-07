"""Artifact 管理 API 路由。"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from ..contracts.artifact import Artifact, ArtifactType
from ..domain.runtime import ScientificExecutionKernel

router = APIRouter(prefix="/v1", tags=["artifacts"])
kernel = ScientificExecutionKernel()


class StoreArtifactRequest(BaseModel):
    run_id: str
    type: ArtifactType
    name: str
    description: str = ""
    content_type: str = "application/json"
    data: dict | None = None
    file_path: str | None = None
    checksum: str | None = None


@router.post("/artifacts", response_model=Artifact)
def store_artifact(req: StoreArtifactRequest):
    artifact = Artifact(
        run_id=req.run_id,
        type=req.type,
        name=req.name,
        description=req.description,
        content_type=req.content_type,
        data=req.data,
        file_path=req.file_path,
        checksum=req.checksum,
    )
    return kernel.store_artifact(artifact)