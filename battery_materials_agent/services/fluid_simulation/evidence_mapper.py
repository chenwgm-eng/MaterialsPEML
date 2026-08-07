"""流体模拟证据映射 — 将计算结果转换为 EvidencePackage。"""

from __future__ import annotations

from typing import Any

from ...contracts.evidence import EvidenceLevel, EvidencePackage, build_source_fields


def map_fluid_evidence(
    run_id: str,
    task_id: str,
    name: str,
    value: Any,
    unit: str = "",
    source: str = "",
    confidence: float = 1.0,
    method: str = "",
    category: str = "",
    extra_metadata: dict[str, Any] | None = None,
) -> EvidencePackage:
    """将单条流体模拟结果映射为证据包。

    Args:
        run_id: 运行 ID
        task_id: 任务 ID
        name: 结果名称
        value: 计算值
        unit: 单位
        source: 数据来源
        confidence: 置信度 (0~1)
        method: 计算方法描述
        category: 证据类别 (run_stats, field_analysis, spectra, convergence)
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

    sf = build_source_fields("fluid_simulation", source=source)

    metadata: dict[str, Any] = {
        "result_name": name,
        "source": source,
        "category": category,
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
        method=method or "fluid_simulation",
        source_type=sf["source_type"],
        source_service=sf["source_service"],
        metadata=metadata,
    )


def batch_map_fluid_evidence(
    run_id: str,
    task_id: str,
    results: list[dict[str, Any]],
    category: str = "",
) -> list[EvidencePackage]:
    """批量将流体模拟结果映射为证据包列表。

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
            - 及其他类别专属字段
        category: 证据类别

    Returns:
        EvidencePackage 列表。
    """
    packages: list[EvidencePackage] = []
    for r in results:
        standard_keys = {"name", "value", "unit", "source", "confidence", "method"}
        extra = {k: v for k, v in r.items() if k not in standard_keys and v is not None}

        pkg = map_fluid_evidence(
            run_id=run_id,
            task_id=task_id,
            name=r.get("name", ""),
            value=r.get("value"),
            unit=r.get("unit", ""),
            source=r.get("source", ""),
            confidence=r.get("confidence", 1.0),
            method=r.get("method", "fluid_simulation"),
            category=category,
            extra_metadata=extra if extra else None,
        )
        packages.append(pkg)
    return packages


def map_run_statistics(
    run_id: str,
    task_id: str,
    stats: dict[str, Any],
) -> list[EvidencePackage]:
    """将运行统计信息映射为证据包。

    Args:
        run_id: 运行 ID
        task_id: 任务 ID
        stats: 运行统计字典，包含:
            - n_steps: 总步数
            - dt: 时间步长
            - cfl: CFL 数
            - walltime: 壁钟时间 (秒)
            - t_end: 模拟结束时间

    Returns:
        EvidencePackage 列表。
    """
    results: list[dict[str, Any]] = []

    step_map = {
        "总步数": ("n_steps", "", "int"),
        "时间步长": ("dt", "s", "float"),
        "CFL 数": ("cfl", "", "float"),
        "壁钟时间": ("walltime", "s", "float"),
        "模拟结束时间": ("t_end", "s", "float"),
    }

    for label, (key, unit, _) in step_map.items():
        if key in stats:
            results.append({
                "name": label,
                "value": stats[key],
                "unit": unit,
                "source": "fluidsim",
                "confidence": 1.0,
                "method": "运行时统计",
                "category": "run_stats",
            })

    return batch_map_fluid_evidence(run_id, task_id, results, category="run_stats")


def map_field_analysis(
    run_id: str,
    task_id: str,
    field_data: dict[str, Any],
) -> list[EvidencePackage]:
    """将物理场分析结果映射为证据包。

    Args:
        run_id: 运行 ID
        task_id: 任务 ID
        field_data: 物理场分析数据，包含:
            - max_vorticity: 最大涡量
            - min_vorticity: 最小涡量
            - mean_vorticity: 平均涡量
            - total_kinetic_energy: 总动能
            - enstrophy: 涡度拟能
            - max_velocity: 最大速度
            - mean_velocity: 平均速度

    Returns:
        EvidencePackage 列表。
    """
    results: list[dict[str, Any]] = []

    field_map = {
        "最大涡量": ("max_vorticity", "1/s"),
        "最小涡量": ("min_vorticity", "1/s"),
        "平均涡量": ("mean_vorticity", "1/s"),
        "总动能": ("total_kinetic_energy", "m²/s²"),
        "涡度拟能": ("enstrophy", "1/s²"),
        "最大速度": ("max_velocity", "m/s"),
        "平均速度": ("mean_velocity", "m/s"),
    }

    for label, (key, unit) in field_map.items():
        if key in field_data:
            results.append({
                "name": label,
                "value": field_data[key],
                "unit": unit,
                "source": "fluidsim.field_analysis",
                "confidence": 0.9,
                "method": "物理场分析",
            })

    return batch_map_fluid_evidence(run_id, task_id, results, category="field_analysis")


def map_spectra_analysis(
    run_id: str,
    task_id: str,
    spectra_data: dict[str, Any],
) -> list[EvidencePackage]:
    """将能谱分析结果映射为证据包。

    Args:
        run_id: 运行 ID
        task_id: 任务 ID
        spectra_data: 能谱分析数据，包含:
            - spectrum_1d: 1D 能谱
            - spectrum_2d: 2D 能谱
            - k_min: 最小波数
            - k_max: 最大波数
            - slope: 谱斜率 (如 -5/3)

    Returns:
        EvidencePackage 列表。
    """
    results: list[EvidencePackage] = []

    if "slope" in spectra_data:
        results.append(
            map_fluid_evidence(
                run_id=run_id,
                task_id=task_id,
                name="能谱斜率",
                value=spectra_data["slope"],
                unit="",
                source="fluidsim.spectra",
                confidence=0.85,
                method="能谱分析",
                category="spectra",
                extra_metadata={
                    "k_min": spectra_data.get("k_min"),
                    "k_max": spectra_data.get("k_max"),
                },
            )
        )

    if "spectrum_1d" in spectra_data:
        spec = spectra_data["spectrum_1d"]
        results.append(
            map_fluid_evidence(
                run_id=run_id,
                task_id=task_id,
                name="1D 能谱",
                value=spec,
                unit="",
                source="fluidsim.spectra",
                confidence=0.85,
                method="1D 傅里叶能谱",
                category="spectra",
                extra_metadata={
                    "spectrum_type": "1d",
                    "k_min": spectra_data.get("k_min"),
                    "k_max": spectra_data.get("k_max"),
                },
            )
        )

    if "spectrum_2d" in spectra_data:
        spec = spectra_data["spectrum_2d"]
        results.append(
            map_fluid_evidence(
                run_id=run_id,
                task_id=task_id,
                name="2D 能谱",
                value=spec,
                unit="",
                source="fluidsim.spectra",
                confidence=0.85,
                method="2D 傅里叶能谱",
                category="spectra",
                extra_metadata={
                    "spectrum_type": "2d",
                    "k_min": spectra_data.get("k_min"),
                    "k_max": spectra_data.get("k_max"),
                },
            )
        )

    return results


def map_convergence_analysis(
    run_id: str,
    task_id: str,
    convergence_data: dict[str, Any],
) -> list[EvidencePackage]:
    """将收敛/稳态分析结果映射为证据包。

    Args:
        run_id: 运行 ID
        task_id: 任务 ID
        convergence_data: 收敛分析数据，包含:
            - is_steady: 是否达到稳态
            - convergence_time: 收敛时间
            - energy_derivative: 能量时间导数
            - enstrophy_derivative: 涡度拟能时间导数

    Returns:
        EvidencePackage 列表。
    """
    results: list[dict[str, Any]] = []

    conv_map = {
        "是否达到稳态": ("is_steady", ""),
        "收敛时间": ("convergence_time", "s"),
        "能量时间导数": ("energy_derivative", "m²/s³"),
        "涡度拟能时间导数": ("enstrophy_derivative", "1/s³"),
    }

    for label, (key, unit) in conv_map.items():
        if key in convergence_data:
            results.append({
                "name": label,
                "value": convergence_data[key],
                "unit": unit,
                "source": "fluidsim.convergence",
                "confidence": 0.85,
                "method": "收敛/稳态分析",
            })

    return batch_map_fluid_evidence(run_id, task_id, results, category="convergence")