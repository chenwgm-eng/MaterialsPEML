"""分子动力学模拟证据映射 — 将MD结果转换为 EvidencePackage。"""

from __future__ import annotations

from typing import Any

from ...contracts.evidence import EvidencePackage, EvidenceLevel, build_source_fields


def map_md_evidence(
    run_id: str,
    task_id: str,
    metric_name: str,
    value: Any,
    unit: str = "",
    confidence: float = 0.85,
    metadata: dict[str, Any] | None = None,
) -> EvidencePackage:
    """将单个MD指标结果映射为 EvidencePackage。

    Args:
        run_id: 运行 ID。
        task_id: 任务 ID。
        metric_name: 指标名称（如 rdf, msd, diffusion_coefficient）。
        value: 指标值。
        unit: 指标单位。
        confidence: 置信度 (0-1)。
        metadata: 附加元数据。

    Returns:
        EvidencePackage 实例。
    """
    level = (
        EvidenceLevel.HIGH if confidence >= 0.9
        else EvidenceLevel.MEDIUM if confidence >= 0.7
        else EvidenceLevel.LOW
    )

    description_map: dict[str, str] = {
        "rdf": "径向分布函数",
        "msd": "均方位移",
        "diffusion_coefficient": "扩散系数",
        "rmsd": "均方根偏差",
        "rmsf": "均方根涨落",
        "energy": "体系能量",
        "temperature": "温度轨迹",
        "pressure": "压力轨迹",
        "density": "密度轨迹",
        "cna": "共近邻分析",
        "angular_distribution": "角分布",
    }
    metric_desc = description_map.get(metric_name, metric_name)

    sf = build_source_fields("molecular_simulation")

    return EvidencePackage(
        run_id=run_id,
        task_id=task_id,
        claim=f"MD 模拟 {metric_desc} 分析结果",
        value=value,
        unit=unit,
        confidence=confidence,
        level=level,
        method="molecular_dynamics_simulation",
        source_type=sf["source_type"],
        source_service=sf["source_service"],
        metadata={
            "metric_name": metric_name,
            "metric_description": metric_desc,
            **(metadata or {}),
            **sf["metadata_patch"],
        },
    )


def batch_map_md_evidence(
    run_id: str,
    task_id: str,
    results: list[dict[str, Any]],
) -> list[EvidencePackage]:
    """批量将 MD 模拟结果转换为 EvidencePackage 列表。

    results 格式:
        [
            {
                "metric": "rdf",
                "value": [...],          # RDF 数据点
                "unit": "无量纲",
                "confidence": 0.9,
                "metadata": {...},
            },
            {
                "metric": "diffusion_coefficient",
                "value": 1.23e-9,
                "unit": "m²/s",
                "confidence": 0.85,
            },
            ...
        ]

    Args:
        run_id: 运行 ID。
        task_id: 任务 ID。
        results: MD 结果列表。

    Returns:
        EvidencePackage 列表。
    """
    packages: list[EvidencePackage] = []
    for entry in results:
        package = map_md_evidence(
            run_id=run_id,
            task_id=task_id,
            metric_name=entry.get("metric", "unknown"),
            value=entry.get("value"),
            unit=entry.get("unit", ""),
            confidence=entry.get("confidence", 0.85),
            metadata=entry.get("metadata"),
        )
        packages.append(package)
    return packages