"""化学性质证据映射 — 将查询结果转换为 EvidencePackage。"""

from __future__ import annotations

from typing import Any

from ...contracts.evidence import EvidenceLevel, EvidencePackage, build_source_fields


def map_chemical_evidence(
    run_id: str,
    task_id: str,
    property_name: str,
    value: Any,
    unit: str = "",
    source: str = "",
    confidence: float = 1.0,
    method: str = "",
) -> EvidencePackage:
    """将单条化学性质查询结果映射为证据包。

    Args:
        run_id: 运行 ID
        task_id: 任务 ID
        property_name: 性质名称
        value: 查询值
        unit: 单位
        source: 数据来源（如 DIPPR, NIST, PubChem）
        confidence: 置信度 (0~1)
        method: 计算方法描述

    Returns:
        EvidencePackage 实例。
    """
    claim = f"{property_name} = {value} {unit}".strip()
    if source:
        claim += f" (来源: {source})"

    level = EvidenceLevel.HIGH if confidence >= 0.9 else (
        EvidenceLevel.MEDIUM if confidence >= 0.7 else EvidenceLevel.LOW
    )

    # CoE 信任分级：依据 source 字符串区分真实引擎 / 内置库兜底
    sf = build_source_fields("chem_properties", source=source)

    return EvidencePackage(
        run_id=run_id,
        task_id=task_id,
        claim=claim,
        value=value,
        unit=unit,
        confidence=confidence,
        level=level,
        method=method or "chemical_property_lookup",
        source_type=sf["source_type"],
        source_service=sf["source_service"],
        metadata={
            "property_name": property_name,
            "source": source,
            **sf["metadata_patch"],
        },
    )


def batch_map_chemical_evidence(
    run_id: str,
    task_id: str,
    results: list[dict[str, Any]],
) -> list[EvidencePackage]:
    """批量将化学性质查询结果映射为证据包列表。

    Args:
        run_id: 运行 ID
        task_id: 任务 ID
        results: 查询结果列表，每个元素为 dict，包含:
            - property_name (str): 性质名称
            - value (Any): 值
            - unit (str, optional): 单位
            - source (str, optional): 数据来源
            - confidence (float, optional): 置信度 (默认 1.0)
            - method (str, optional): 计算方法

    Returns:
        EvidencePackage 列表。
    """
    packages: list[EvidencePackage] = []
    for r in results:
        pkg = map_chemical_evidence(
            run_id=run_id,
            task_id=task_id,
            property_name=r.get("property_name", ""),
            value=r.get("value"),
            unit=r.get("unit", ""),
            source=r.get("source", ""),
            confidence=r.get("confidence", 1.0),
            method=r.get("method", "chemical_property_lookup"),
        )
        packages.append(pkg)
    return packages