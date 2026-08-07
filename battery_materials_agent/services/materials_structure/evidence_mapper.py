"""证据映射 — 将结构结果转换为 EvidencePackage。"""

from __future__ import annotations

from typing import Any

from ...contracts.evidence import EvidencePackage, EvidenceLevel, build_source_fields


def map_structure_evidence(
    run_id: str,
    task_id: str,
    structure_id: str,
    fmt: str,
    data: str,
    method: str = "structure_generation",
    confidence: float = 1.0,
) -> EvidencePackage:
    """将单个结构结果映射为证据包。

    Args:
        run_id: 所属运行 ID。
        task_id: 所属任务 ID。
        structure_id: 结构标识符。
        fmt: 结构格式（smiles / xyz / cif / mol 等）。
        data: 结构数据字符串。
        method: 生成方法说明。
        confidence: 置信度（0-1）。

    Returns:
        EvidencePackage: 结构证据包。
    """
    sf = build_source_fields("materials_structure")

    return EvidencePackage(
        run_id=run_id,
        task_id=task_id,
        claim=f"生成/优化了结构 {structure_id}（格式: {fmt}）",
        value={
            "structure_id": structure_id,
            "format": fmt,
            "data": data,
        },
        confidence=confidence,
        level=EvidenceLevel.HIGH if confidence >= 0.9 else EvidenceLevel.MEDIUM,
        method=method,
        source_type=sf["source_type"],
        source_service=sf["source_service"],
        metadata={
            "structure_id": structure_id,
            "format": fmt,
            **sf["metadata_patch"],
        },
    )


def batch_map_structure_evidence(
    run_id: str,
    task_id: str,
    structures: list[dict[str, Any]],
    method: str = "structure_generation",
) -> list[EvidencePackage]:
    """批量将多个结构结果映射为证据包列表。

    Args:
        run_id: 所属运行 ID。
        task_id: 所属任务 ID。
        structures: 结构字典列表，每个字典应包含
            ``structure_id``, ``format``, ``data`` 三个键。
        method: 生成方法说明。

    Returns:
        list[EvidencePackage]: 证据包列表。
    """
    packages: list[EvidencePackage] = []
    for struct in structures:
        package = map_structure_evidence(
            run_id=run_id,
            task_id=task_id,
            structure_id=struct["structure_id"],
            fmt=struct["format"],
            data=struct["data"],
            method=method,
        )
        packages.append(package)
    return packages