"""反应网络分析证据映射 — 将反应枚举/TS搜索/网络生长结果映射为 EvidencePackage。

基于 OpenReactNet 的 E0-E4 证据分级体系：
    E0: 模板匹配
    E1: 文献类似
    E2: 文献直接引用
    E3: 内部实验验证
    E4: 已验证工艺
"""

from __future__ import annotations

from typing import Any

from ...contracts.evidence import EvidencePackage, EvidenceLevel, build_source_fields


def _evidence_level_from_stage(stage: int) -> EvidenceLevel:
    """将 E0-E4 证据等级映射为 EvidenceLevel。

    Args:
        stage: 证据等级 (0-4)。

    Returns:
        EvidenceLevel 枚举值。
    """
    if stage >= 4:
        return EvidenceLevel.HIGH
    elif stage >= 2:
        return EvidenceLevel.MEDIUM
    elif stage >= 1:
        return EvidenceLevel.LOW
    return EvidenceLevel.ASSISTIVE


def map_reaction_evidence(
    run_id: str,
    task_id: str,
    reaction_smiles: str,
    evidence_stage: int = 0,
    confidence: float = 0.5,
    metadata: dict[str, Any] | None = None,
) -> EvidencePackage:
    """将单个反应结果映射为 EvidencePackage。

    E0-E4 证据等级说明：
        E0: 模板匹配 — 基于已知反应模板的自动匹配，置信度最低。
        E1: 文献类似 — 与文献报道的反应类型相似。
        E2: 文献直接引用 — 该反应在文献中直接报道。
        E3: 内部实验验证 — 内部实验已验证。
        E4: 已验证工艺 — 经过工艺验证的成熟反应。

    Args:
        run_id: 运行 ID。
        task_id: 任务 ID。
        reaction_smiles: 反应 SMILES。
        evidence_stage: 证据等级 (0-4)。
        confidence: 置信度 (0-1)。
        metadata: 附加元数据。

    Returns:
        EvidencePackage 实例。
    """
    stage_labels = {
        0: "模板匹配",
        1: "文献类似",
        2: "文献直接引用",
        3: "内部实验验证",
        4: "已验证工艺",
    }
    stage_label = stage_labels.get(evidence_stage, f"E{evidence_stage}")

    sf = build_source_fields("reaction_network")

    return EvidencePackage(
        run_id=run_id,
        task_id=task_id,
        claim=f"反应网络 {stage_label} 证据: {reaction_smiles}",
        value=reaction_smiles,
        unit="",
        confidence=confidence,
        level=_evidence_level_from_stage(evidence_stage),
        method="reaction_network_analysis",
        source_type=sf["source_type"],
        source_service=sf["source_service"],
        metadata={
            "reaction_smiles": reaction_smiles,
            "evidence_stage": evidence_stage,
            "evidence_label": stage_label,
            **(metadata or {}),
            **sf["metadata_patch"],
        },
    )


def batch_map_reaction_evidence(
    run_id: str,
    task_id: str,
    results: list[dict[str, Any]],
) -> list[EvidencePackage]:
    """批量将反应网络分析结果转换为 EvidencePackage 列表。

    results 格式:
        [
            {
                "reaction_smiles": "CCO>>CC(=O)O",
                "evidence_stage": 0,       # E0 模板匹配
                "confidence": 0.6,
                "metadata": {...},
            },
            {
                "reaction_smiles": "CCO>>C=C",
                "evidence_stage": 2,       # E2 文献直接引用
                "confidence": 0.85,
                "metadata": {"doi": "10.xxx/xxxxx"},
            },
            ...
        ]

    Args:
        run_id: 运行 ID。
        task_id: 任务 ID。
        results: 反应网络分析结果列表。

    Returns:
        EvidencePackage 列表。
    """
    packages: list[EvidencePackage] = []
    for entry in results:
        package = map_reaction_evidence(
            run_id=run_id,
            task_id=task_id,
            reaction_smiles=entry.get("reaction_smiles", ""),
            evidence_stage=entry.get("evidence_stage", 0),
            confidence=entry.get("confidence", 0.5),
            metadata=entry.get("metadata"),
        )
        packages.append(package)
    return packages