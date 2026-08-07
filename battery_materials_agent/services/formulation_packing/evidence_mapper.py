"""配方与堆积证据映射 — 将计算结果转换为 EvidencePackage。"""

from __future__ import annotations

from ...contracts.evidence import EvidencePackage, EvidenceLevel, build_source_fields


def map_formulation_evidence(
    run_id: str,
    task_id: str,
    formulation_id: str,
    property: str,
    value: float,
    unit: str,
) -> EvidencePackage:
    """创建配方优化结果证据包。

    Args:
        run_id: 运行 ID。
        task_id: 任务 ID。
        formulation_id: 配方方案 ID。
        property: 优化属性名称（如 density, energy）。
        value: 属性值。
        unit: 属性单位。

    Returns:
        EvidencePackage 实例。
    """
    sf = build_source_fields("formulation_packing")

    return EvidencePackage(
        run_id=run_id,
        task_id=task_id,
        claim=f"配方 {formulation_id} 的 {property} 优化结果",
        value=value,
        unit=unit,
        confidence=0.85,
        level=EvidenceLevel.MEDIUM,
        method="formulation_optimization",
        source_type=sf["source_type"],
        source_service=sf["source_service"],
        metadata={
            "formulation_id": formulation_id,
            "property": property,
            "evidence_type": "formulation",
            **sf["metadata_patch"],
        },
    )


def map_packing_evidence(
    run_id: str,
    task_id: str,
    structure_id: str,
    density: float,
    energy: float,
) -> EvidencePackage:
    """创建堆积结构结果证据包。

    Args:
        run_id: 运行 ID。
        task_id: 任务 ID。
        structure_id: 堆积结构 ID。
        density: 堆积密度 (g/cm³)。
        energy: 体系能量 (kcal/mol)。

    Returns:
        EvidencePackage 实例。
    """
    sf = build_source_fields("formulation_packing")

    return EvidencePackage(
        run_id=run_id,
        task_id=task_id,
        claim=f"堆积结构 {structure_id} 生成结果",
        value={"density": density, "energy": energy},
        unit="",
        confidence=0.85,
        level=EvidenceLevel.MEDIUM,
        method="molecular_packing",
        source_type=sf["source_type"],
        source_service=sf["source_service"],
        metadata={
            "structure_id": structure_id,
            "density": density,
            "energy": energy,
            "evidence_type": "packing",
            **sf["metadata_patch"],
        },
    )