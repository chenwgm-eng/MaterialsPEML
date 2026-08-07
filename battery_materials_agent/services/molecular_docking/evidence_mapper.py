"""分子对接证据映射 — 将对接结果转换为 EvidencePackage。"""

from __future__ import annotations

from typing import Any

from ...contracts.evidence import EvidencePackage, EvidenceLevel, build_source_fields


def map_docking_evidence(
    run_id: str,
    task_id: str,
    pose_rank: int,
    pose_confidence: float,
    pose_sdf_path: str,
    complex_status: str = "success",
    runtime_seconds: float | None = None,
    metadata: dict[str, Any] | None = None,
) -> EvidencePackage:
    """将单个对接位姿结果映射为 EvidencePackage。

    Args:
        run_id: 运行 ID。
        task_id: 任务 ID。
        pose_rank: 位姿排名（1-based）。
        pose_confidence: 置信度分数 (0-1)。
        pose_sdf_path: 位姿 SDF 文件路径。
        complex_status: 复合物处理状态（success / failed）。
        runtime_seconds: 对接耗时（秒）。
        metadata: 附加元数据。

    Returns:
        EvidencePackage 实例。
    """
    level = (
        EvidenceLevel.HIGH if pose_confidence >= 0.9
        else EvidenceLevel.MEDIUM if pose_confidence >= 0.7
        else EvidenceLevel.LOW
    )

    sf = build_source_fields("molecular_docking")

    return EvidencePackage(
        run_id=run_id,
        task_id=task_id,
        claim=f"分子对接位姿 Top-{pose_rank}（置信度 {pose_confidence:.2f}）",
        value=pose_sdf_path,
        unit="sdf_path",
        confidence=pose_confidence,
        level=level,
        method="diffusion_docking",
        source_type=sf["source_type"],
        source_service=sf["source_service"],
        metadata={
            "pose_rank": pose_rank,
            "pose_confidence": pose_confidence,
            "pose_sdf_path": pose_sdf_path,
            "complex_status": complex_status,
            "runtime_seconds": runtime_seconds,
            **(metadata or {}),
            **sf["metadata_patch"],
        },
    )


def batch_map_docking_evidence(
    run_id: str,
    task_id: str,
    results: list[dict[str, Any]],
) -> list[EvidencePackage]:
    """批量将对接结果转换为 EvidencePackage 列表。

    results 格式:
        [
            {
                "complex_index": 0,
                "status": "success",
                "runtime_seconds": 45.2,
                "poses": [
                    {
                        "rank": 1,
                        "confidence": 0.95,
                        "sdf_path": "/path/to/pose_1.sdf",
                    },
                    ...
                ],
            },
            ...
        ]

    Args:
        run_id: 运行 ID。
        task_id: 任务 ID。
        results: 对接结果列表。

    Returns:
        EvidencePackage 列表。
    """
    packages: list[EvidencePackage] = []
    for entry in results:
        complex_status = entry.get("status", "success")
        runtime = entry.get("runtime_seconds")
        poses = entry.get("poses", [])
        for pose in poses:
            package = map_docking_evidence(
                run_id=run_id,
                task_id=task_id,
                pose_rank=pose.get("rank", 0),
                pose_confidence=pose.get("confidence", 0.5),
                pose_sdf_path=pose.get("sdf_path", ""),
                complex_status=complex_status,
                runtime_seconds=runtime,
                metadata=pose.get("metadata"),
            )
            packages.append(package)
    return packages


def map_screen_summary(
    run_id: str,
    task_id: str,
    best_confidence: float,
    best_rank: int,
    best_pose_path: str,
    total_complexes: int,
    total_poses: int,
    metadata: dict[str, Any] | None = None,
) -> EvidencePackage:
    """将虚拟筛选摘要映射为 EvidencePackage。

    Args:
        run_id: 运行 ID。
        task_id: 任务 ID。
        best_confidence: 最佳置信度。
        best_rank: 最佳位姿排名。
        best_pose_path: 最佳位姿文件路径。
        total_complexes: 总复合物数。
        total_poses: 总位姿数。
        metadata: 附加元数据。

    Returns:
        EvidencePackage 实例。
    """
    level = (
        EvidenceLevel.HIGH if best_confidence >= 0.9
        else EvidenceLevel.MEDIUM if best_confidence >= 0.7
        else EvidenceLevel.LOW
    )

    sf = build_source_fields("molecular_docking")

    return EvidencePackage(
        run_id=run_id,
        task_id=task_id,
        claim=f"虚拟筛选摘要: 最佳置信度 {best_confidence:.2f}, Top-{best_rank}",
        value=best_pose_path,
        unit="sdf_path",
        confidence=best_confidence,
        level=level,
        method="virtual_screening",
        source_type=sf["source_type"],
        source_service=sf["source_service"],
        metadata={
            "best_confidence": best_confidence,
            "best_rank": best_rank,
            "best_pose_path": best_pose_path,
            "total_complexes": total_complexes,
            "total_poses": total_poses,
            **(metadata or {}),
            **sf["metadata_patch"],
        },
    )