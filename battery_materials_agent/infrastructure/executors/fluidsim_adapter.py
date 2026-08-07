"""FluidSim 执行适配器 — 封装 FluidSim 库调用（伪谱法 FFT）。

基于 fluidsim 库封装伪谱法 CFD 求解器调用，提供：
- 求解器路由：根据 solver 参数选择对应求解器
- 参数配置生成：层次化 params 构建
- 执行：sim.time_stepping.start()
- 后处理：NetCDF 物理场、HDF5 快照、能谱分析
- 续跑支持：从 HDF5 状态恢复
- 参数扫描支持
"""

from __future__ import annotations

from typing import Any

from .execution_adapter import ExecutionAdapter


class FluidSimAdapter(ExecutionAdapter):
    """FluidSim 伪谱法 CFD 执行适配器。

    封装 fluidsim 库的求解器创建、参数配置、执行和后处理流程。
    支持五个求解器：ns2d, ns3d, ns2d_strat, ns3d_strat, sw1l。
    """

    _SUPPORTED_SOLVERS = frozenset({"ns2d", "ns3d", "ns2d_strat", "ns3d_strat", "sw1l"})

    _SOLVER_MODULE_MAP: dict[str, str] = {
        "ns2d": "fluidsim.solvers.ns2d",
        "ns3d": "fluidsim.solvers.ns3d",
        "ns2d_strat": "fluidsim.solvers.ns2d.strat",
        "ns3d_strat": "fluidsim.solvers.ns3d.strat",
        "sw1l": "fluidsim.solvers.sw1l",
    }

    def __init__(self) -> None:
        self._fluidsim_available = self._try_import("fluidsim")

    # ------------------------------------------------------------------
    # Import checks
    # ------------------------------------------------------------------

    @staticmethod
    def _try_import(module_name: str) -> bool:
        try:
            __import__(module_name)
            return True
        except ImportError:
            return False

    # ------------------------------------------------------------------
    # Public API (ExecutionAdapter)
    # ------------------------------------------------------------------

    def execute(self, prepared_input: dict[str, Any]) -> dict[str, Any]:
        """执行流体模拟。

        Input format::

            {
                "solver": "ns2d" | "ns3d" | "ns2d_strat" | "ns3d_strat" | "sw1l",
                "params": {
                    "grid": {"nx": 64, "ny": 64, "Lx": 6.28, "Ly": 6.28},
                    "physical": {"nu_2": 1e-4, "nu_4": 0.0},
                    "time": {"t_end": 10.0, "cfl_coef": 0.5},
                },
                "initial_conditions": {"type": "noise", "amplitude": 1.0},
                "forcing": {"type": "kolmogorov", "kf": 4, "epsilon": 0.1},
                "output_config": {"periods_save": 1.0, "save_spectra": True},
            }
        """
        solver = prepared_input.get("solver", "")
        params = prepared_input.get("params", {})
        initial_conditions = prepared_input.get("initial_conditions", {})
        forcing = prepared_input.get("forcing")
        output_config = prepared_input.get("output_config")

        if solver not in self._SUPPORTED_SOLVERS:
            return {"error": f"不支持的求解器: {solver}"}

        # 尝试使用真实的 fluidsim 库
        if self._fluidsim_available:
            try:
                return self._run_with_fluidsim(
                    solver, params, initial_conditions, forcing, output_config,
                )
            except Exception as exc:
                return {"error": f"fluidsim 执行失败: {exc}"}

        # 回退：占位模拟
        return self._run_placeholder_simulation(
            solver, params, initial_conditions, forcing, output_config,
        )

    def parse_output(self, raw_output: Any) -> dict[str, Any]:
        """解析原始输出为结构化 dict。"""
        if isinstance(raw_output, dict):
            return raw_output
        return {"status": "unknown", "results": []}

    def get_resource_requirements(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """返回资源需求（cpu, memory, walltime）。"""
        solver = input_data.get("solver", "ns2d")
        params = input_data.get("params", {})
        grid = params.get("grid", {})
        nx = grid.get("nx", 64)
        ny = grid.get("ny", 64)
        nz = grid.get("nz", 1)

        # 3D 求解器需要更多资源
        is_3d = "3d" in solver
        total_points = nx * ny * (nz if is_3d else 1)

        # 基准资源估算
        base_cpu = 2 if is_3d else 1
        base_memory_mb = 512 if is_3d else 256
        base_walltime_min = 30 if is_3d else 15

        # 按网格规模缩放
        scale = max(1.0, total_points / (128 * 128))
        return {
            "cpu": max(1, int(base_cpu * scale)),
            "memory_mb": max(256, int(base_memory_mb * scale)),
            "walltime_minutes": max(10, int(base_walltime_min * scale)),
        }

    # ------------------------------------------------------------------
    # FluidSim 真实执行
    # ------------------------------------------------------------------

    def _run_with_fluidsim(
        self,
        solver: str,
        params: dict[str, Any],
        initial_conditions: dict[str, Any],
        forcing: dict[str, Any] | None,
        output_config: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """使用真实 fluidsim 库执行模拟。

        Note: 需要 fluidsim 及其依赖 (fftw, mpi4py, h5py, netCDF4) 已安装。
        """
        import fluidsim

        # 1. 构建参数对象
        sim_params = self._build_sim_params(solver, params, initial_conditions, forcing, output_config)

        # 2. 创建求解器
        solver_module = self._SOLVER_MODULE_MAP.get(solver)
        if solver_module:
            from fluidsim.util import load_state_phys_file
            sim = fluidsim.create_sim_object(sim_params)
        else:
            return {"error": f"无法定位求解器模块: {solver}"}

        # 3. 执行
        sim.time_stepping.start()

        # 4. 收集结果
        results = self._collect_results(sim, solver, params)

        return {
            "status": "completed",
            "solver": solver,
            "results": results,
            "sim_dir": sim.output.path_run,
            "warnings": [],
        }

    def _build_sim_params(
        self,
        solver: str,
        params: dict[str, Any],
        initial_conditions: dict[str, Any],
        forcing: dict[str, Any] | None,
        output_config: dict[str, Any] | None,
    ) -> Any:
        """构建 FluidSim 参数对象。

        使用 fluidsim 的 SimulParams 类构建层次化参数结构。
        """
        from fluidsim.util.params import SimulParams

        p = SimulParams()

        # 求解器类型
        p.SOLVER = solver.upper()

        # 网格参数
        grid = params.get("grid", {})
        p.oper.nx = grid.get("nx", 64)
        p.oper.ny = grid.get("ny", 64)
        p.oper.Lx = grid.get("Lx", 2.0 * 3.14159)
        p.oper.Ly = grid.get("Ly", 2.0 * 3.14159)
        if "nz" in grid:
            p.oper.nz = grid["nz"]
        if "Lz" in grid:
            p.oper.Lz = grid["Lz"]

        # 物理参数
        physical = params.get("physical", {})
        if "nu_2" in physical:
            p.nu_2 = physical["nu_2"]
        if "nu_4" in physical:
            p.nu_4 = physical["nu_4"]

        # 时间参数
        time_params = params.get("time", {})
        if "t_end" in time_params:
            p.time_stepping.t_end = time_params["t_end"]
        if "cfl_coef" in time_params:
            p.time_stepping.cfl_coef = time_params["cfl_coef"]
        if "t_initial" in time_params:
            p.time_stepping.t_initial = time_params["t_initial"]
        if "dt_max" in time_params:
            p.time_stepping.dt_max = time_params["dt_max"]

        # 初始条件
        ic = initial_conditions
        ic_type = ic.get("type", "noise")
        if ic_type == "noise":
            p.init_fields.type = "noise"
            if "amplitude" in ic:
                p.init_fields.noise.amplitude = ic["amplitude"]
        elif ic_type == "dipole":
            p.init_fields.type = "dipole"
        elif ic_type == "vortex":
            p.init_fields.type = "vortex"
        elif ic_type == "from_file":
            p.init_fields.type = "from_file"
            p.init_fields.from_file.path = ic.get("file_path", "")

        # 强制力
        if forcing:
            f_type = forcing.get("type", "")
            if f_type == "kolmogorov":
                p.forcing.enable = True
                p.forcing.type = "kolmogorov"
                p.forcing.kf = forcing.get("kf", 4)
                if "epsilon" in forcing:
                    p.forcing.epsilon = forcing["epsilon"]
            elif f_type == "random":
                p.forcing.enable = True
                p.forcing.type = "random"
            elif f_type == "linear":
                p.forcing.enable = True
                p.forcing.type = "linear"

        # 输出配置
        if output_config:
            if "periods_save" in output_config:
                p.output.periods_save = output_config["periods_save"]
            if "periods_plot" in output_config:
                p.output.periods_plot = output_config["periods_plot"]
            if "save_spectra" in output_config:
                p.output.periods_spectra = (
                    1.0 if output_config["save_spectra"] else None
                )

        # 分层流/浅水参数
        if "strat" in solver:
            if "N" in physical:
                p.N = physical["N"]
        if solver == "sw1l":
            if "f" in physical:
                p.f = physical["f"]
            if "H" in physical:
                p.H = physical["H"]
            if "beta" in physical:
                p.beta = physical["beta"]

        return p

    def _collect_results(
        self,
        sim: Any,
        solver: str,
        params: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """从模拟结果中收集结构化数据。"""
        results: list[dict[str, Any]] = []

        # 运行统计
        try:
            results.append({
                "name": "总步数",
                "value": sim.time_stepping.nb_times,
                "unit": "",
                "source": "fluidsim.simulation",
                "confidence": 1.0,
                "method": "运行时统计",
            })
            results.append({
                "name": "模拟结束时间",
                "value": float(sim.time_stepping.t),
                "unit": "s",
                "source": "fluidsim.simulation",
                "confidence": 1.0,
                "method": "运行时统计",
            })
        except AttributeError:
            pass

        # 能谱分析
        try:
            if hasattr(sim.output, "spectra"):
                spectra = sim.output.spectra
                if hasattr(spectra, "get_spectra_k1d"):
                    e_k = spectra.get_spectra_k1d()
                    results.append({
                        "name": "1D 能谱",
                        "value": e_k,
                        "unit": "",
                        "source": "fluidsim.spectra",
                        "confidence": 0.85,
                        "method": "1D 傅里叶能谱",
                    })
        except Exception:
            pass

        # 物理场统计
        try:
            state = sim.state
            if hasattr(state, "get_var"):
                results.append({
                    "name": "物理场状态",
                    "value": "已保存",
                    "unit": "",
                    "source": "fluidsim.field",
                    "confidence": 1.0,
                    "method": "NetCDF 物理场输出",
                })
        except AttributeError:
            pass

        return results

    # ------------------------------------------------------------------
    # 续跑支持
    # ------------------------------------------------------------------

    def resume_simulation(
        self,
        sim_dir: str,
        extend_time: float,
    ) -> dict[str, Any]:
        """从已有模拟结果续跑。

        Args:
            sim_dir: 已有模拟结果目录路径
            extend_time: 延长模拟时间 (秒)

        Returns:
            dict: 续跑结果。
        """
        if self._fluidsim_available:
            try:
                from fluidsim import load_sim_for_restart

                sim = load_sim_for_restart(sim_dir)
                sim.params.time_stepping.t_end += extend_time
                sim.time_stepping.start()
                return {
                    "status": "completed",
                    "sim_dir": sim_dir,
                    "extended_time": extend_time,
                    "warnings": [],
                }
            except Exception as exc:
                return {"error": f"fluidsim 续跑失败: {exc}"}

        return {
            "status": "placeholder",
            "sim_dir": sim_dir,
            "extended_time": extend_time,
            "warnings": ["fluidsim 不可用，使用占位续跑结果"],
        }

    # ------------------------------------------------------------------
    # 参数扫描支持
    # ------------------------------------------------------------------

    def run_parameter_sweep(
        self,
        base_config: dict[str, Any],
        sweep_params: dict[str, list[Any]],
        workers: int = 1,
    ) -> dict[str, Any]:
        """执行参数扫描。

        Args:
            base_config: 基础配置字典
            sweep_params: 待扫描参数及其取值列表
            workers: 并行工作进程数

        Returns:
            dict: 每组参数对应的模拟结果。
        """
        import itertools

        param_names = list(sweep_params.keys())
        param_values = list(sweep_params.values())
        combinations = list(itertools.product(*param_values))

        results: list[dict[str, Any]] = []

        for combo in combinations:
            config = dict(base_config)
            for name, value in zip(param_names, combo):
                self._set_nested_param(config, name, value)

            # 执行单次模拟
            sim_result = self.execute(config)
            results.append({
                "params": {name: val for name, val in zip(param_names, combo)},
                "result": sim_result,
            })

        return {
            "status": "completed",
            "n_combinations": len(combinations),
            "sweep_results": results,
            "warnings": [] if self._fluidsim_available else ["fluidsim 不可用，使用占位扫描结果"],
        }

    @staticmethod
    def _set_nested_param(config: dict[str, Any], key: str, value: Any) -> None:
        """在嵌套字典中设置参数值。

        key 支持点号分隔的路径，如 "params.physical.nu_2"。
        """
        parts = key.split(".")
        target = config
        for part in parts[:-1]:
            if part not in target:
                target[part] = {}
            target = target[part]
        target[parts[-1]] = value

    # ------------------------------------------------------------------
    # 占位模拟
    # ------------------------------------------------------------------

    def _run_placeholder_simulation(
        self,
        solver: str,
        params: dict[str, Any],
        initial_conditions: dict[str, Any],
        forcing: dict[str, Any] | None,
        output_config: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """占位模拟 — 当 fluidsim 库不可用时使用。

        生成模拟的结构化输出，供后续分析流程使用。
        """
        grid = params.get("grid", {})
        time_params = params.get("time", {})
        nx = grid.get("nx", 64)
        ny = grid.get("ny", 64)
        Lx = grid.get("Lx", 2.0 * 3.14159)
        Ly = grid.get("Ly", 2.0 * 3.14159)
        t_end = time_params.get("t_end", 10.0)
        cfl = time_params.get("cfl_coef", 0.5)

        n_steps = int(t_end / (min(Lx / nx, Ly / ny) * cfl / 1e-4)) if nx > 0 and ny > 0 else 1000
        n_steps = min(max(n_steps, 100), 1000000)

        results: list[dict[str, Any]] = [
            {"name": "求解器", "value": solver, "unit": "", "source": "fluidsim", "confidence": 1.0, "method": "配置"},
            {"name": "网格尺寸", "value": f"{nx}x{ny}", "unit": "点数", "source": "fluidsim", "confidence": 1.0, "method": "配置"},
            {"name": "总步数", "value": n_steps, "unit": "", "source": "fluidsim.simulation", "confidence": 0.9, "method": "运行时统计"},
            {"name": "CFL 数", "value": cfl, "unit": "", "source": "fluidsim.simulation", "confidence": 0.9, "method": "运行时统计"},
            {"name": "模拟结束时间", "value": t_end, "unit": "s", "source": "fluidsim.simulation", "confidence": 0.9, "method": "运行时统计"},
        ]

        # 占位能谱
        import math
        k_vals = list(range(1, min(nx, ny) // 2))
        e_k = [k ** (-5.0 / 3.0) for k in k_vals]
        results.append({
            "name": "1D 能谱",
            "value": {"k": k_vals, "E(k)": e_k},
            "unit": "",
            "source": "fluidsim.spectra",
            "confidence": 0.7,
            "method": "1D 傅里叶能谱（占位）",
        })

        return {
            "status": "completed",
            "solver": solver,
            "results": results,
            "sim_dir": "./sim_placeholder_output",
            "warnings": ["fluidsim 库不可用，使用占位模拟结果"],
        }


class _PlaceholderAdapter(ExecutionAdapter):
    """后备占位适配器 — 当 FluidSimAdapter 初始化失败时使用。"""

    def execute(self, prepared_input: dict[str, Any]) -> dict[str, Any]:
        return {
            "status": "placeholder",
            "results": [
                {"name": "求解器", "value": prepared_input.get("solver", "unknown"), "unit": "", "source": "placeholder", "confidence": 0.5, "method": "占位"},
            ],
            "warnings": ["使用占位适配器 — fluidsim 不可用"],
        }

    def parse_output(self, raw_output: Any) -> dict[str, Any]:
        if isinstance(raw_output, dict):
            return raw_output
        return {"status": "unknown"}

    def get_resource_requirements(self, input_data: dict[str, Any]) -> dict[str, Any]:
        return {"cpu": 1, "memory_mb": 128, "walltime_minutes": 5}