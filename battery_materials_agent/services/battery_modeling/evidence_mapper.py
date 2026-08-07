"""电池建模证据映射 — 将仿真结果转换为 EvidencePackage。"""

from __future__ import annotations

from typing import Any

from ...contracts.evidence import EvidenceLevel, EvidencePackage, build_source_fields


def map_simulation_evidence(
    run_id: str,
    task_id: str,
    claim: str,
    value: Any,
    unit: str = "",
    confidence: float = 1.0,
    method: str = "",
    metadata: dict[str, Any] | None = None,
) -> EvidencePackage:
    """将单条电池仿真结果映射为证据包。

    Args:
        run_id: 运行 ID
        task_id: 任务 ID
        claim: 证据声明
        value: 值
        unit: 单位
        confidence: 置信度 (0~1)
        method: 计算方法描述
        metadata: 额外元数据

    Returns:
        EvidencePackage 实例。
    """
    level = (
        EvidenceLevel.HIGH
        if confidence >= 0.9
        else (EvidenceLevel.MEDIUM if confidence >= 0.7 else EvidenceLevel.LOW)
    )

    sf = build_source_fields("battery_modeling")

    return EvidencePackage(
        run_id=run_id,
        task_id=task_id,
        claim=claim,
        value=value,
        unit=unit,
        confidence=confidence,
        level=level,
        method=method or "pybamm_simulation",
        source_type=sf["source_type"],
        source_service=sf["source_service"],
        metadata={**(metadata or {}), **sf["metadata_patch"]},
    )


def batch_map_evidence(
    run_id: str,
    task_id: str,
    track: str,
    model_type: str,
    parameter_set: str,
    results: dict[str, Any],
    summary: dict[str, Any],
) -> list[EvidencePackage]:
    """批量将电池仿真结果映射为证据包列表。

    Args:
        run_id: 运行 ID
        task_id: 任务 ID
        track: 仿真轨道 (p2d/ecm/pybop)
        model_type: 模型类型 (SPM/SPMe/DFN)
        parameter_set: 参数集名称
        results: 仿真结果 dict，key 为变量名，value 为数组
        summary: 摘要信息（如最终电压、总容量等）

    Returns:
        EvidencePackage 列表。
    """
    packages: list[EvidencePackage] = []

    # 1. 仿真概要证据
    summary_metadata = {
        "track": track,
        "model_type": model_type,
        "parameter_set": parameter_set,
    }
    packages.append(
        map_simulation_evidence(
            run_id=run_id,
            task_id=task_id,
            claim=f"电池仿真完成: {track}/{model_type} ({parameter_set})",
            value=f"{track}/{model_type}",
            unit="",
            confidence=1.0,
            method=f"pybamm_{track}_{model_type}",
            metadata=summary_metadata,
        )
    )

    # 2. 摘要统计证据
    for key, val in summary.items():
        if val is None:
            continue
        unit_map = {
            "final_voltage": "V",
            "total_capacity": "A.h",
            "max_temperature": "K",
            "min_voltage": "V",
            "max_voltage": "V",
            "cycle_count": "",
        }
        unit = unit_map.get(key, "")
        desc_map = {
            "final_voltage": "最终端电压",
            "total_capacity": "总容量",
            "max_temperature": "最高温度",
            "min_voltage": "最低电压",
            "max_voltage": "最高电压",
            "cycle_count": "循环次数",
        }
        claim = f"{desc_map.get(key, key)} = {val} {unit}".strip()

        packages.append(
            map_simulation_evidence(
                run_id=run_id,
                task_id=task_id,
                claim=claim,
                value=val,
                unit=unit,
                confidence=0.95,
                method=f"pybamm_{track}_{model_type}",
                metadata={**summary_metadata, "stat_key": key},
            )
        )

    # 3. 关键变量曲线证据（给每个变量生成一个证据包）
    for var_name, var_data in results.items():
        if not isinstance(var_data, (list, tuple)):
            continue
        if len(var_data) == 0:
            continue

        # 仅记录变量存在性及特征值（首尾值），避免数据量过大
        first_val = var_data[0] if var_data else None
        last_val = var_data[-1] if var_data else None
        var_desc_map = {
            "Terminal voltage [V]": "端电压",
            "Current [A]": "电流",
            "Discharge capacity [A.h]": "放电容量",
            "Charge capacity [A.h]": "充电容量",
            "Cell temperature [K]": "电池温度",
            "X-averaged cell temperature [K]": "X-平均电池温度",
        }
        desc = var_desc_map.get(var_name, var_name)
        claim = f"{desc}: 首值={first_val}, 末值={last_val}, 点数={len(var_data)}"

        packages.append(
            map_simulation_evidence(
                run_id=run_id,
                task_id=task_id,
                claim=claim,
                value={"first": first_val, "last": last_val, "count": len(var_data)},
                unit="",
                confidence=0.95,
                method=f"pybamm_{track}_{model_type}",
                metadata={**summary_metadata, "variable": var_name},
            )
        )

    return packages