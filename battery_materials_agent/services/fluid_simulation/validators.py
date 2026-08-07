"""流体模拟输入校验 — 基于 OpenFluidSimFlow 设计文档。"""

from __future__ import annotations

from typing import Any

# 支持的求解器
VALID_SOLVERS = frozenset({"ns2d", "ns3d", "ns2d_strat", "ns3d_strat", "sw1l"})

# 求解器名称映射
SOLVER_NAMES: dict[str, str] = {
    "ns2d": "二维 Navier-Stokes (NS2D)",
    "ns3d": "三维 Navier-Stokes (NS3D)",
    "ns2d_strat": "二维分层流 (NS2D Stratified)",
    "ns3d_strat": "三维分层流 (NS3D Stratified)",
    "sw1l": "单层浅水方程 (SW1L)",
}

# 支持的初始条件类型
VALID_INITIAL_CONDITIONS = frozenset({"noise", "dipole", "vortex", "from_file", "in_script"})


def validate_solver(solver: str) -> str | None:
    """验证求解器标识。

    Returns:
        错误信息字符串，校验通过返回 None。
    """
    if not solver:
        return "求解器标识不能为空"
    if solver not in VALID_SOLVERS:
        return (
            f"无效求解器 '{solver}'，"
            f"可选: {', '.join(sorted(VALID_SOLVERS))}"
        )
    return None


def validate_grid_params(params: dict[str, Any]) -> list[str]:
    """验证网格参数。

    Args:
        params: 网格参数字典，包含 nx, ny, Lx, Ly 等。

    Returns:
        错误信息列表，空列表表示无错误。
    """
    errors: list[str] = []

    if not params:
        errors.append("网格参数不能为空")
        return errors

    nx = params.get("nx")
    if nx is not None:
        if not isinstance(nx, int) or nx <= 0:
            errors.append(f"nx 必须为正整数，当前: {nx}")
    else:
        errors.append("nx (网格点数) 为必填参数")

    ny = params.get("ny")
    if ny is not None:
        if not isinstance(ny, int) or ny <= 0:
            errors.append(f"ny 必须为正整数，当前: {ny}")
    else:
        errors.append("ny (网格点数) 为必填参数")

    # 三维求解器需要 nz
    nz = params.get("nz")
    if nz is not None:
        if not isinstance(nz, int) or nz <= 0:
            errors.append(f"nz 必须为正整数，当前: {nz}")

    Lx = params.get("Lx")
    if Lx is not None:
        if not isinstance(Lx, (int, float)) or Lx <= 0:
            errors.append(f"Lx 必须为正数，当前: {Lx}")
    else:
        errors.append("Lx (域长度) 为必填参数")

    Ly = params.get("Ly")
    if Ly is not None:
        if not isinstance(Ly, (int, float)) or Ly <= 0:
            errors.append(f"Ly 必须为正数，当前: {Ly}")
    else:
        errors.append("Ly (域长度) 为必填参数")

    Lz = params.get("Lz")
    if Lz is not None:
        if not isinstance(Lz, (int, float)) or Lz <= 0:
            errors.append(f"Lz 必须为正数，当前: {Lz}")

    return errors


def validate_physical_params(params: dict[str, Any]) -> list[str]:
    """验证物理参数。

    Args:
        params: 物理参数字典，包含 nu_2, nu_4 等。

    Returns:
        错误信息列表，空列表表示无错误。
    """
    errors: list[str] = []

    if not params:
        return errors

    nu_2 = params.get("nu_2")
    if nu_2 is not None:
        if not isinstance(nu_2, (int, float)) or nu_2 < 0:
            errors.append(f"nu_2 (二阶粘性) 必须为非负数，当前: {nu_2}")

    nu_4 = params.get("nu_4")
    if nu_4 is not None:
        if not isinstance(nu_4, (int, float)) or nu_4 < 0:
            errors.append(f"nu_4 (四阶粘性) 必须为非负数，当前: {nu_4}")

    return errors


def validate_time_params(params: dict[str, Any]) -> list[str]:
    """验证时间参数。

    Args:
        params: 时间参数字典，包含 t_end, cfl_coef 等。

    Returns:
        错误信息列表，空列表表示无错误。
    """
    errors: list[str] = []

    if not params:
        errors.append("时间参数不能为空")
        return errors

    t_end = params.get("t_end")
    if t_end is not None:
        if not isinstance(t_end, (int, float)) or t_end <= 0:
            errors.append(f"t_end (模拟总时长) 必须为正数，当前: {t_end}")
    else:
        errors.append("t_end (模拟总时长) 为必填参数")

    cfl_coef = params.get("cfl_coef")
    if cfl_coef is not None:
        if not isinstance(cfl_coef, (int, float)):
            errors.append(f"cfl_coef 必须为数值，当前: {cfl_coef}")
        elif cfl_coef < 0.01 or cfl_coef > 2.0:
            errors.append(f"cfl_coef 建议在 [0.01, 2.0] 范围内，当前: {cfl_coef}")
        elif cfl_coef < 0.1 or cfl_coef > 1.0:
            errors.append(f"cfl_coef 典型范围 [0.1, 1.0]，当前: {cfl_coef}，请确认")

    t_initial = params.get("t_initial")
    if t_initial is not None:
        if not isinstance(t_initial, (int, float)) or t_initial < 0:
            errors.append(f"t_initial 必须为非负数，当前: {t_initial}")

    dt_max = params.get("dt_max")
    if dt_max is not None:
        if not isinstance(dt_max, (int, float)) or dt_max <= 0:
            errors.append(f"dt_max 必须为正数，当前: {dt_max}")

    return errors


def validate_initial_conditions(ic: dict[str, Any]) -> list[str]:
    """验证初始条件参数。

    Args:
        ic: 初始条件字典，包含 type 及其他参数。

    Returns:
        错误信息列表，空列表表示无错误。
    """
    errors: list[str] = []

    if not ic:
        errors.append("初始条件不能为空")
        return errors

    ic_type = ic.get("type", "")
    if not ic_type:
        errors.append("初始条件 type 不能为空")
        return errors
    if ic_type not in VALID_INITIAL_CONDITIONS:
        errors.append(
            f"初始条件类型 '{ic_type}' 不支持，"
            f"可选: {', '.join(sorted(VALID_INITIAL_CONDITIONS))}"
        )

    if ic_type == "from_file":
        file_path = ic.get("file_path")
        if not file_path:
            errors.append("from_file 类型需要提供 file_path")
        elif not isinstance(file_path, str):
            errors.append("file_path 必须为字符串")

    if ic_type == "in_script":
        script = ic.get("script")
        if not script:
            errors.append("in_script 类型需要提供 script")
        elif not isinstance(script, str):
            errors.append("script 必须为字符串")

    # 振幅参数
    amplitude = ic.get("amplitude")
    if amplitude is not None:
        if not isinstance(amplitude, (int, float)) or amplitude <= 0:
            errors.append(f"amplitude 必须为正数，当前: {amplitude}")

    # 噪声参数
    nk_max = ic.get("nk_max")
    if nk_max is not None:
        if not isinstance(nk_max, int) or nk_max <= 0:
            errors.append(f"nk_max (最大波数) 必须为正整数，当前: {nk_max}")

    return errors


def validate_forcing_params(forcing: dict[str, Any] | None) -> list[str]:
    """验证强制力参数。

    Args:
        forcing: 强制力配置字典，可以为 None（表示无力）。

    Returns:
        错误信息列表，空列表表示无错误。
    """
    errors: list[str] = []

    if forcing is None:
        return errors
    if not isinstance(forcing, dict):
        errors.append("forcing 必须为字典或 None")
        return errors

    forcing_type = forcing.get("type", "")
    if not forcing_type:
        errors.append("forcing.type 不能为空")
        return errors

    valid_types = {"kolmogorov", "random", "linear", "custom"}
    if forcing_type not in valid_types:
        errors.append(
            f"强制力类型 '{forcing_type}' 不支持，"
            f"可选: {', '.join(sorted(valid_types))}"
        )

    if forcing_type == "kolmogorov":
        kf = forcing.get("kf")
        if kf is not None:
            if not isinstance(kf, (int, float)) or kf <= 0:
                errors.append(f"kf (强制波数) 必须为正数，当前: {kf}")
        else:
            errors.append("Kolmogorov 强制需要 kf 参数")

        epsilon = forcing.get("epsilon")
        if epsilon is not None:
            if not isinstance(epsilon, (int, float)) or epsilon <= 0:
                errors.append(f"epsilon (能量注入率) 必须为正数，当前: {epsilon}")

    return errors


def validate_stratified_params(solver: str, params: dict[str, Any]) -> list[str]:
    """验证分层流/浅水参数。

    Args:
        solver: 求解器标识
        params: 参数字典

    Returns:
        错误信息列表，空列表表示无错误。
    """
    errors: list[str] = []

    if "strat" in solver or solver == "sw1l":
        N = params.get("N")
        if N is not None:
            if not isinstance(N, (int, float)) or N <= 0:
                errors.append(f"N (Brunt-Väisälä 频率) 必须为正数，当前: {N}")

        f = params.get("f")
        if f is not None:
            if not isinstance(f, (int, float)):
                errors.append(f"f (Coriolis 参数) 必须为数值，当前: {f}")

        if solver == "sw1l":
            H = params.get("H")
            if H is not None:
                if not isinstance(H, (int, float)) or H <= 0:
                    errors.append(f"H (流体深度) 必须为正数，当前: {H}")

        beta = params.get("beta")
        if beta is not None:
            if not isinstance(beta, (int, float)):
                errors.append(f"beta (beta 平面参数) 必须为数值，当前: {beta}")

    return errors


def validate_output_config(output_config: dict[str, Any] | None) -> list[str]:
    """验证输出配置参数。

    Args:
        output_config: 输出配置字典

    Returns:
        错误信息列表，空列表表示无错误。
    """
    errors: list[str] = []

    if output_config is None:
        return errors
    if not isinstance(output_config, dict):
        errors.append("output_config 必须为字典或 None")
        return errors

    periods_save = output_config.get("periods_save")
    if periods_save is not None:
        if not isinstance(periods_save, (int, float)) or periods_save <= 0:
            errors.append(f"periods_save 必须为正数，当前: {periods_save}")

    periods_plot = output_config.get("periods_plot")
    if periods_plot is not None:
        if not isinstance(periods_plot, (int, float)) or periods_plot <= 0:
            errors.append(f"periods_plot 必须为正数，当前: {periods_plot}")

    save_spectra = output_config.get("save_spectra")
    if save_spectra is not None and not isinstance(save_spectra, bool):
        errors.append("save_spectra 必须为布尔值")

    save_fields = output_config.get("save_fields")
    if save_fields is not None and not isinstance(save_fields, bool):
        errors.append("save_fields 必须为布尔值")

    return errors


class FluidSimulationValidator:
    """流体模拟综合校验器。"""

    @staticmethod
    def validate_all(
        solver: str,
        grid_params: dict[str, Any],
        physical_params: dict[str, Any],
        time_params: dict[str, Any],
        initial_conditions: dict[str, Any],
        forcing: dict[str, Any] | None = None,
        output_config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """全量校验，返回结构化结果。

        Returns:
            dict 包含 validated (bool) 和 errors (list[str])。
        """
        errors: list[str] = []

        # 验证求解器
        solver_err = validate_solver(solver)
        if solver_err:
            errors.append(solver_err)
            return {"validated": False, "errors": errors}

        # 验证网格参数
        grid_errors = validate_grid_params(grid_params)
        errors.extend(grid_errors)

        # 验证物理参数
        phys_errors = validate_physical_params(physical_params)
        errors.extend(phys_errors)

        # 验证时间参数
        time_errors = validate_time_params(time_params)
        errors.extend(time_errors)

        # 验证初始条件
        ic_errors = validate_initial_conditions(initial_conditions)
        errors.extend(ic_errors)

        # 验证强制力参数
        forcing_errors = validate_forcing_params(forcing)
        errors.extend(forcing_errors)

        # 验证分层流/浅水参数
        strat_errors = validate_stratified_params(solver, {**physical_params, **time_params})
        errors.extend(strat_errors)

        # 验证输出配置
        output_errors = validate_output_config(output_config)
        errors.extend(output_errors)

        return {"validated": len(errors) == 0, "errors": errors}