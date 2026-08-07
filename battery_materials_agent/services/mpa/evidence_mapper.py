"""MPA 证据映射 — 将预测结果转换为 EvidencePackage。"""

from __future__ import annotations

from typing import Any

from ...contracts.evidence import EvidencePackage, EvidenceLevel, build_source_fields
from .validators import PROPERTY_CATALOG


def map_property_to_evidence(
    run_id: str,
    task_id: str,
    mol_id: str,
    property_name: str,
    value: Any,
    unit: str | None = None,
    confidence: float = 1.0,
    note: str | None = None,
    degraded: bool = False,
) -> EvidencePackage:
    """将单个分子属性预测结果映射为 EvidencePackage。

    Args:
        run_id: 运行 ID
        task_id: 任务 ID
        mol_id: 分子标识符（SMILES 或索引）
        property_name: 属性键名
        value: 属性值
        unit: 单位；若为 None 则从属性目录自动查找
        confidence: 置信度 (0-1)
        note: 降级原因说明（如 "需 DFT 计算补充"）
        degraded: 是否为降级结果（RDKit 无法计算）

    Returns:
        EvidencePackage 实例
    """
    meta = PROPERTY_CATALOG.get(property_name, {})
    resolved_unit = unit or meta.get("unit", "")

    level = EvidenceLevel.HIGH if confidence >= 0.9 else (
        EvidenceLevel.MEDIUM if confidence >= 0.7 else EvidenceLevel.LOW
    )

    claim = f"{meta.get('description', property_name)} of molecule {mol_id}"

    metadata: dict[str, Any] = {
        "mol_id": mol_id,
        "property_name": property_name,
        "property_description": meta.get("description", ""),
    }
    if note:
        metadata["note"] = note
    if degraded:
        metadata["degraded"] = True

    sf = build_source_fields("mpa", degraded=degraded)

    return EvidencePackage(
        run_id=run_id,
        task_id=task_id,
        claim=claim,
        value=value,
        unit=resolved_unit,
        confidence=confidence,
        level=level,
        method="MPA (Molecular Property Analysis)",
        source_type=sf["source_type"],
        source_service=sf["source_service"],
        metadata={**metadata, **sf["metadata_patch"]},
    )


def batch_map_evidence(
    run_id: str,
    task_id: str,
    results_matrix: list[dict[str, Any]],
) -> list[EvidencePackage]:
    """批量将预测结果矩阵转换为 EvidencePackage 列表。

    results_matrix 格式:
        [
            {
                "mol_id": str,          # SMILES 或索引
                "predictions": {
                    "BP_K": {"value": 373.15, "confidence": 0.95},
                    "MW":   {"value": 18.015, "confidence": 1.0},
                    ...
                }
            },
            ...
        ]

    Returns:
        EvidencePackage 列表
    """
    packages: list[EvidencePackage] = []
    for entry in results_matrix:
        mol_id = entry.get("mol_id", "?")
        predictions = entry.get("predictions", {})
        for prop_name, prop_data in predictions.items():
            if isinstance(prop_data, dict):
                value = prop_data.get("value")
                confidence = prop_data.get("confidence", 1.0)
                unit = prop_data.get("unit")
                note = prop_data.get("note")
                degraded = prop_data.get("degraded", False)
            else:
                value = prop_data
                confidence = 1.0
                unit = None
                note = None
                degraded = False

            package = map_property_to_evidence(
                run_id=run_id,
                task_id=task_id,
                mol_id=mol_id,
                property_name=prop_name,
                value=value,
                unit=unit,
                confidence=confidence,
                note=note,
                degraded=degraded,
            )
            packages.append(package)

    return packages