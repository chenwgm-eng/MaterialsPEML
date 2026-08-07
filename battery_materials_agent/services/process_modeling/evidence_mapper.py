"""化工过程证据映射 — 将计算结果转换为 EvidencePackage。"""

from __future__ import annotations

from typing import Any

from ...contracts.evidence import EvidenceLevel, EvidencePackage, build_source_fields


def map_process_evidence(
    run_id: str,
    task_id: str,
    name: str,
    value: Any,
    unit: str = "",
    source: str = "",
    confidence: float = 1.0,
    method: str = "",
    module: str = "",
    extra_metadata: dict[str, Any] | None = None,
) -> EvidencePackage:
    """将单条化工过程计算结果映射为证据包。

    Args:
        run_id: 运行 ID
        task_id: 任务 ID
        name: 计算结果名称
        value: 计算值
        unit: 单位
        source: 数据来源
        confidence: 置信度 (0~1)
        method: 计算方法描述
        module: 模块标识 (M1-M6)
        extra_metadata: 额外元数据

    Returns:
        EvidencePackage 实例。
    """
    claim = f"{name} = {value} {unit}".strip()
    if source:
        claim += f" (来源: {source})"

    level = EvidenceLevel.HIGH if confidence >= 0.9 else (
        EvidenceLevel.MEDIUM if confidence >= 0.7 else EvidenceLevel.LOW
    )

    sf = build_source_fields("process_modeling", source=source)

    metadata: dict[str, Any] = {
        "result_name": name,
        "source": source,
        "module": module,
        **sf["metadata_patch"],
    }
    if extra_metadata:
        metadata.update(extra_metadata)

    return EvidencePackage(
        run_id=run_id,
        task_id=task_id,
        claim=claim,
        value=value,
        unit=unit,
        confidence=confidence,
        level=level,
        method=method or "process_calculation",
        source_type=sf["source_type"],
        source_service=sf["source_service"],
        metadata=metadata,
    )


def batch_map_process_evidence(
    run_id: str,
    task_id: str,
    results: list[dict[str, Any]],
    module: str = "",
) -> list[EvidencePackage]:
    """批量将化工过程计算结果映射为证据包列表。

    Args:
        run_id: 运行 ID
        task_id: 任务 ID
        results: 计算结果列表，每个元素为 dict，包含:
            - name (str): 结果名称
            - value (Any): 值
            - unit (str, optional): 单位
            - source (str, optional): 数据来源
            - confidence (float, optional): 置信度 (默认 1.0)
            - method (str, optional): 计算方法
            - 及其他模块专属字段
        module: 模块标识 (M1-M6)

    Returns:
        EvidencePackage 列表。
    """
    packages: list[EvidencePackage] = []
    for r in results:
        # 提取额外元数据（排除标准字段）
        standard_keys = {"name", "value", "unit", "source", "confidence", "method"}
        extra = {k: v for k, v in r.items() if k not in standard_keys and v is not None}

        pkg = map_process_evidence(
            run_id=run_id,
            task_id=task_id,
            name=r.get("name", ""),
            value=r.get("value"),
            unit=r.get("unit", ""),
            source=r.get("source", ""),
            confidence=r.get("confidence", 1.0),
            method=r.get("method", "process_calculation"),
            module=module,
            extra_metadata=extra if extra else None,
        )
        packages.append(pkg)
    return packages