"""波函数分析证据映射 — 将 ESP/轨道/渲染结果转换为 EvidencePackage。"""

from __future__ import annotations

from typing import Any

from ...contracts.evidence import EvidencePackage, EvidenceLevel, build_source_fields


def map_wavefunction_evidence(
    run_id: str,
    task_id: str,
    evidence_type: str,
    claim: str,
    value: Any,
    unit: str = "",
    confidence: float = 0.85,
    metadata: dict[str, Any] | None = None,
) -> EvidencePackage:
    """将单个波函数分析结果映射为 EvidencePackage。

    Args:
        run_id: 运行 ID。
        task_id: 任务 ID。
        evidence_type: 证据类型（esp_surface, esp_area, esp_atomic,
                        orbital_energy, orbital_gap, render_script, render_image）。
        claim: 证据声明。
        value: 证据值。
        unit: 单位。
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

    method_map: dict[str, str] = {
        "esp_surface": "multiwfn_esp_surface_analysis",
        "esp_area": "multiwfn_esp_area_distribution",
        "esp_atomic": "multiwfn_esp_atomic_statistics",
        "orbital_energy": "multiwfn_orbital_energy_analysis",
        "orbital_gap": "multiwfn_homo_lumo_gap",
        "render_script": "vmd_render_script",
        "render_image": "vmd_rendering",
    }
    method = method_map.get(evidence_type, "wavefunction_analysis")

    sf = build_source_fields("wavefunction_analysis")

    return EvidencePackage(
        run_id=run_id,
        task_id=task_id,
        claim=claim,
        value=value,
        unit=unit,
        confidence=confidence,
        level=level,
        method=method,
        source_type=sf["source_type"],
        source_service=sf["source_service"],
        metadata={
            "evidence_type": evidence_type,
            **(metadata or {}),
            **sf["metadata_patch"],
        },
    )


def batch_map_wavefunction_evidence(
    run_id: str,
    task_id: str,
    results: list[dict[str, Any]],
) -> list[EvidencePackage]:
    """批量将波函数分析结果转换为 EvidencePackage 列表。

    results 格式:
        [
            {
                "type": "esp_surface",
                "claim": "ESP 表面统计",
                "value": {...},
                "unit": "kcal/mol",
                "confidence": 0.9,
                "metadata": {...},
            },
            {
                "type": "orbital_gap",
                "claim": "HOMO-LUMO 能隙",
                "value": 4.5,
                "unit": "eV",
                "confidence": 0.95,
            },
            ...
        ]

    Args:
        run_id: 运行 ID。
        task_id: 任务 ID。
        results: 波函数分析结果列表。

    Returns:
        EvidencePackage 列表。
    """
    packages: list[EvidencePackage] = []
    for entry in results:
        package = map_wavefunction_evidence(
            run_id=run_id,
            task_id=task_id,
            evidence_type=entry.get("type", "unknown"),
            claim=entry.get("claim", "波函数分析结果"),
            value=entry.get("value"),
            unit=entry.get("unit", ""),
            confidence=entry.get("confidence", 0.85),
            metadata=entry.get("metadata"),
        )
        packages.append(package)
    return packages