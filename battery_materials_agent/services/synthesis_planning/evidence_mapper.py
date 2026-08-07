"""合成路线证据映射 — 将逆合成分析结果转换为 EvidencePackage，支持 E0-E4 证据分级。"""

from __future__ import annotations

from typing import Any

from ...contracts.evidence import EvidencePackage, EvidenceLevel, build_source_fields


# ── 证据等级定义 ──────────────────────────────────────────────────────────
#
# E0: 模板匹配 — 仅基于逆合成模板库的模型预测，无外部验证
# E1: 文献相似 — 文献中有类似结构/反应的报道
# E2: 文献直接引用 — 文献中明确记载了该反应或路线
# E3: 内部实验验证 — 内部实验已验证该路线可行
# E4: 已验证工艺 — 经过完整工艺验证，可放大生产

EVIDENCE_GRADE_DESCRIPTIONS: dict[str, dict[str, Any]] = {
    "E0": {
        "label": "模板匹配",
        "description": "仅基于逆合成模板库的模型预测",
        "confidence": 0.4,
        "level": EvidenceLevel.LOW,
    },
    "E1": {
        "label": "文献相似",
        "description": "文献中有类似结构或反应的报道",
        "confidence": 0.6,
        "level": EvidenceLevel.MEDIUM,
    },
    "E2": {
        "label": "文献直接引用",
        "description": "文献中明确记载了该反应或合成路线",
        "confidence": 0.8,
        "level": EvidenceLevel.MEDIUM,
    },
    "E3": {
        "label": "内部实验验证",
        "description": "内部实验已验证该路线可行",
        "confidence": 0.9,
        "level": EvidenceLevel.HIGH,
    },
    "E4": {
        "label": "已验证工艺",
        "description": "经过完整工艺验证，可放大生产",
        "confidence": 1.0,
        "level": EvidenceLevel.HIGH,
    },
}


def map_route_evidence(
    run_id: str,
    task_id: str,
    route: dict[str, Any],
) -> EvidencePackage:
    """将单条合成路线映射为 EvidencePackage。

    Args:
        run_id: 运行 ID。
        task_id: 任务 ID。
        route: 路线数据，包含 route_rank, avg_ff_score, reaction_smiles,
               num_reactions, evidence_grade 等字段。

    Returns:
        EvidencePackage 实例。
    """
    route_rank = route.get("route_rank", 0)
    avg_ff_score = route.get("avg_ff_score", 0.0)
    num_reactions = route.get("num_reactions", 0)
    evidence_grade = route.get("evidence_grade", "E0")
    reaction_smiles = route.get("reaction_smiles", "")

    grade_info = EVIDENCE_GRADE_DESCRIPTIONS.get(evidence_grade, EVIDENCE_GRADE_DESCRIPTIONS["E0"])

    sf = build_source_fields("synthesis_planning")

    return EvidencePackage(
        run_id=run_id,
        task_id=task_id,
        claim=f"合成路线 #{route_rank} — {num_reactions} 步反应，证据等级 {evidence_grade}",
        value={
            "route_rank": route_rank,
            "avg_ff_score": avg_ff_score,
            "num_reactions": num_reactions,
            "reaction_smiles": reaction_smiles,
            "evidence_grade": evidence_grade,
        },
        unit="",
        confidence=grade_info["confidence"],
        level=grade_info["level"],
        method="ReactNavi retrosynthesis",
        source_type=sf["source_type"],
        source_service=sf["source_service"],
        metadata={
            "route_rank": route_rank,
            "evidence_grade": evidence_grade,
            "evidence_label": grade_info["label"],
            "avg_ff_score": avg_ff_score,
            "num_reactions": num_reactions,
            **sf["metadata_patch"],
        },
    )


def map_stats_evidence(
    run_id: str,
    task_id: str,
    stats: dict[str, Any],
) -> EvidencePackage:
    """将搜索统计信息映射为 EvidencePackage。

    Args:
        run_id: 运行 ID。
        task_id: 任务 ID。
        stats: 搜索统计，包含 total_iterations, total_chemicals,
               total_reactions, total_templates, total_paths, search_time_s。

    Returns:
        EvidencePackage 实例。
    """
    total_reactions = stats.get("total_reactions", 0)
    total_paths = stats.get("total_paths", 0)
    search_time_s = stats.get("search_time_s", 0.0)

    # 根据统计信息推断证据等级
    if total_paths > 0 and total_reactions > 0:
        evidence_grade = "E1"
        claim = f"逆合成搜索完成：找到 {total_paths} 条路线，{total_reactions} 个反应"
    elif total_reactions > 0 and total_paths == 0:
        evidence_grade = "E0"
        claim = f"逆合成搜索部分完成：找到 {total_reactions} 个反应但未形成完整路线"
    else:
        evidence_grade = "E0"
        claim = "逆合成搜索未找到匹配模板或路线"

    grade_info = EVIDENCE_GRADE_DESCRIPTIONS.get(evidence_grade, EVIDENCE_GRADE_DESCRIPTIONS["E0"])

    sf = build_source_fields("synthesis_planning")

    return EvidencePackage(
        run_id=run_id,
        task_id=task_id,
        claim=claim,
        value=stats,
        unit="",
        confidence=grade_info["confidence"],
        level=grade_info["level"],
        method="ReactNavi retrosynthesis",
        source_type=sf["source_type"],
        source_service=sf["source_service"],
        metadata={
            "evidence_type": "search_stats",
            "evidence_grade": evidence_grade,
            "total_reactions": total_reactions,
            "total_paths": total_paths,
            "search_time_s": search_time_s,
            **sf["metadata_patch"],
        },
    )


def map_normalization_evidence(
    run_id: str,
    task_id: str,
    original_smiles: str,
    normalized_smiles: str,
) -> EvidencePackage:
    """将目标分子归一化操作映射为 EvidencePackage。

    Args:
        run_id: 运行 ID。
        task_id: 任务 ID。
        original_smiles: 原始 SMILES（可能含离子/盐）。
        normalized_smiles: 归一化后的中性母体 SMILES。

    Returns:
        EvidencePackage 实例。
    """
    sf = build_source_fields("synthesis_planning")

    return EvidencePackage(
        run_id=run_id,
        task_id=task_id,
        claim=f"目标分子归一化: {original_smiles} → {normalized_smiles}",
        value={
            "original_smiles": original_smiles,
            "normalized_smiles": normalized_smiles,
        },
        unit="",
        confidence=1.0,
        level=EvidenceLevel.HIGH,
        method="ReactNavi normalization",
        source_type=sf["source_type"],
        source_service=sf["source_service"],
        metadata={
            "evidence_type": "normalization",
            "original_smiles": original_smiles,
            "normalized_smiles": normalized_smiles,
            **sf["metadata_patch"],
        },
    )


def map_error_evidence(
    run_id: str,
    task_id: str,
    error_type: str,
    error_message: str,
    diagnostics: dict[str, Any] | None = None,
) -> EvidencePackage:
    """将错误诊断信息映射为 EvidencePackage。

    Args:
        run_id: 运行 ID。
        task_id: 任务 ID。
        error_type: 错误类型（no_template, no_path, timeout, api_error）。
        error_message: 错误描述。
        diagnostics: 诊断详情。

    Returns:
        EvidencePackage 实例。
    """
    sf = build_source_fields("synthesis_planning")

    return EvidencePackage(
        run_id=run_id,
        task_id=task_id,
        claim=f"逆合成诊断 [{error_type}]: {error_message}",
        value={
            "error_type": error_type,
            "error_message": error_message,
            "diagnostics": diagnostics or {},
        },
        unit="",
        confidence=0.0,
        level=EvidenceLevel.ASSISTIVE,
        method="ReactNavi error diagnosis",
        source_type=sf["source_type"],
        source_service=sf["source_service"],
        metadata={
            "evidence_type": "error_diagnosis",
            "error_type": error_type,
            "error_message": error_message,
            **sf["metadata_patch"],
        },
    )


def batch_map_routes(
    run_id: str,
    task_id: str,
    routes: list[dict[str, Any]],
) -> list[EvidencePackage]:
    """批量将路线列表转换为 EvidencePackage 列表。

    Args:
        run_id: 运行 ID。
        task_id: 任务 ID。
        routes: 路线列表，每项包含 route_rank, avg_ff_score, reaction_smiles 等。

    Returns:
        EvidencePackage 列表。
    """
    return [map_route_evidence(run_id=run_id, task_id=task_id, route=r) for r in routes]