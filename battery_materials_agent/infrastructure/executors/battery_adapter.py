"""PyBaMM 电池仿真适配器 — 封装 PyBaMM 库调用。"""

from __future__ import annotations

from typing import Any

from .execution_adapter import ExecutionAdapter

# ── PyBaMM 模型映射 ───────────────────────────────────────────────────────

_PYBAMM_MODEL_MAP: dict[str, str] = {
    "SPM": "pybamm.lithium_ion.SPM",
    "SPMe": "pybamm.lithium_ion.SPMe",
    "DFN": "pybamm.lithium_ion.DFN",
}

_ECM_MODEL_MAP: dict[str, str] = {
    "Thevenin": "pybamm.equivalent_circuit.Thevenin",
    "PNGV": "pybamm.equivalent_circuit.PNGV",
    "RC": "pybamm.equivalent_circuit.RC",
}

# 已知参数集
_KNOWN_PARAMETER_SETS: frozenset[str] = frozenset({
    "Chen2020",
    "Chen2020_composite",
    "OKane2022",
    "Prada2013",
    "OKane2022_graphite_SiOx_halfcell",
    "Marquis2019",
    "Ecker2015",
    "Ramadass2004",
})

# 默认 CCCV 协议
_DEFAULT_CCCV_STEPS: list[str] = [
    "Discharge at C/5 until 2.5 V",
    "Rest for 10 minutes",
    "Charge at C/5 until 4.2 V",
    "Hold at 4.2 V until 50 mA",
    "Rest for 10 minutes",
]


class BatteryAdapter(ExecutionAdapter):
    """PyBaMM 电池仿真适配器。

    支持三条轨道：
    - p2d: P2D/DFN 机理模型 (SPM/SPMe/DFN)
    - ecm: 等效电路模型 (Thevenin/PNGV/RC)
    - pybop: PyBOP 参数辨识

    当 PyBaMM 不可用时，回退到占位仿真结果。
    """

    def __init__(self) -> None:
        self.pybamm_available = self._check_pybamm()
        self.pybop_available = self._check_pybop()

    # ------------------------------------------------------------------
    # Import checks
    # ------------------------------------------------------------------

    @staticmethod
    def _check_pybamm() -> bool:
        try:
            import pybamm  # noqa: F401
            return True
        except ImportError:
            return False

    @staticmethod
    def _check_pybop() -> bool:
        try:
            import pybop  # noqa: F401
            return True
        except ImportError:
            return False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def execute(self, prepared_input: dict[str, Any]) -> dict[str, Any]:
        """执行电池仿真。

        Input format::

            {
                "track": "p2d" | "ecm" | "pybop",
                "model_type": "DFN" | "SPM" | "SPMe" | ...,
                "parameter_set": "Chen2020",
                "experiment_protocol": [{"type": "cccv_cycle", ...}],
                "thermal_option": "isothermal" | "lumped" | "x-full",
                "requested_variables": ["Terminal voltage [V]", "Current [A]"]
            }
        """
        track = prepared_input.get("track", "p2d")
        model_type = prepared_input.get("model_type", "DFN")
        parameter_set = prepared_input.get("parameter_set", "Chen2020")
        experiment_protocol = prepared_input.get("experiment_protocol", [])
        thermal_option = prepared_input.get("thermal_option", "isothermal")
        requested_variables = prepared_input.get(
            "requested_variables",
            ["Terminal voltage [V]", "Current [A]"],
        )

        if track == "p2d":
            return self._run_p2d(
                model_type=model_type,
                parameter_set=parameter_set,
                experiment_protocol=experiment_protocol,
                thermal_option=thermal_option,
                requested_variables=requested_variables,
            )
        elif track == "ecm":
            return self._run_ecm(
                model_type=model_type,
                parameter_set=parameter_set,
                experiment_protocol=experiment_protocol,
                requested_variables=requested_variables,
            )
        elif track == "pybop":
            return self._run_pybop(
                parameter_set=parameter_set,
                requested_variables=requested_variables,
            )
        else:
            return {
                "track": track,
                "model_type": model_type,
                "parameter_set": parameter_set,
                "results": {},
                "summary": {},
                "error": f"Unknown track: {track}",
            }

    def parse_output(self, raw_output: dict[str, Any]) -> dict[str, Any]:
        """解析原始输出为结构化 dict。"""
        return raw_output

    def get_resource_requirements(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """返回资源需求。"""
        track = input_data.get("track", "p2d")
        model_type = input_data.get("model_type", "DFN")
        if track == "pybop":
            return {"cpu": 4, "memory_mb": 4096, "walltime_minutes": 60}
        if model_type == "DFN":
            return {"cpu": 2, "memory_mb": 2048, "walltime_minutes": 30}
        return {"cpu": 1, "memory_mb": 1024, "walltime_minutes": 15}

    # ------------------------------------------------------------------
    # P2D 轨道
    # ------------------------------------------------------------------

    def _run_p2d(
        self,
        model_type: str,
        parameter_set: str,
        experiment_protocol: list[dict],
        thermal_option: str,
        requested_variables: list[str],
    ) -> dict[str, Any]:
        """运行 P2D/DFN 机理模型仿真。"""
        if not self.pybamm_available:
            return self._fallback_p2d(
                model_type, parameter_set, requested_variables
            )

        try:
            import pybamm  # type: ignore[import-untyped]

            # 模型选择
            model_class = _PYBAMM_MODEL_MAP.get(model_type)
            if model_class is None:
                return {"error": f"Unknown P2D model type: {model_type}"}

            # 热选项
            options = {"thermal": thermal_option}
            model = pybamm.lithium_ion.DFN(options=options)
            if model_type == "SPM":
                model = pybamm.lithium_ion.SPM(options=options)
            elif model_type == "SPMe":
                model = pybamm.lithium_ion.SPMe(options=options)

            # 参数集加载
            param = pybamm.ParameterValues(parameter_set)

            # 构建实验协议
            sim: Any
            if experiment_protocol:
                experiment = self._build_experiment(experiment_protocol)
                sim = pybamm.Simulation(
                    model, parameter_values=param, experiment=experiment
                )
            else:
                sim = pybamm.Simulation(model, parameter_values=param)

            # 求解
            sol = sim.solve()

            # 提取结果
            results: dict[str, list[float]] = {}
            for var in requested_variables:
                try:
                    data = sol[var].entries.tolist()
                    results[var] = data
                except (KeyError, AttributeError):
                    results[var] = []

            # 摘要
            summary = self._extract_summary(sol, requested_variables)

            return {
                "track": "p2d",
                "model_type": model_type,
                "parameter_set": parameter_set,
                "thermal_option": thermal_option,
                "results": results,
                "summary": summary,
            }

        except Exception as exc:
            return {
                "track": "p2d",
                "model_type": model_type,
                "parameter_set": parameter_set,
                "results": {},
                "summary": {},
                "error": str(exc),
            }

    # ------------------------------------------------------------------
    # ECM 轨道
    # ------------------------------------------------------------------

    def _run_ecm(
        self,
        model_type: str,
        parameter_set: str,
        experiment_protocol: list[dict],
        requested_variables: list[str],
    ) -> dict[str, Any]:
        """运行等效电路模型仿真。"""
        if not self.pybamm_available:
            return self._fallback_ecm(model_type, requested_variables)

        try:
            import pybamm  # type: ignore[import-untyped]

            # 构建等效电路模型
            model = pybamm.equivalent_circuit.Thevenin()

            # 使用默认参数
            param = pybamm.ParameterValues("ECM_Example")

            sim: Any
            if experiment_protocol:
                experiment = self._build_experiment(experiment_protocol)
                sim = pybamm.Simulation(
                    model, parameter_values=param, experiment=experiment
                )
            else:
                sim = pybamm.Simulation(model, parameter_values=param)

            sol = sim.solve()

            results: dict[str, list[float]] = {}
            for var in requested_variables:
                try:
                    data = sol[var].entries.tolist()
                    results[var] = data
                except (KeyError, AttributeError):
                    results[var] = []

            summary = self._extract_summary(sol, requested_variables)

            return {
                "track": "ecm",
                "model_type": model_type,
                "parameter_set": parameter_set,
                "results": results,
                "summary": summary,
            }

        except Exception as exc:
            return {
                "track": "ecm",
                "model_type": model_type,
                "parameter_set": parameter_set,
                "results": {},
                "summary": {},
                "error": str(exc),
            }

    # ------------------------------------------------------------------
    # PyBOP 轨道
    # ------------------------------------------------------------------

    def _run_pybop(
        self,
        parameter_set: str,
        requested_variables: list[str],
    ) -> dict[str, Any]:
        """运行 PyBOP 参数辨识。"""
        if not self.pybop_available:
            return self._fallback_pybop(parameter_set)

        try:
            import pybop  # type: ignore[import-untyped]

            # 构建参数辨识问题
            model = pybop.lithium_ion.SPM()
            params = pybop.ParameterSet.pybamm(parameter_set)
            problem = pybop.FittingProblem(model, params)

            # 使用简单优化器
            optim = pybop.CMAES(problem)
            results = optim.run()

            return {
                "track": "pybop",
                "parameter_set": parameter_set,
                "results": {
                    "optimized_params": results.xopt.tolist()
                    if hasattr(results, "xopt")
                    else [],
                    "cost": float(results.fopt) if hasattr(results, "fopt") else None,
                },
                "summary": {
                    "optimizer": "CMAES",
                    "iterations": len(results.xlog) if hasattr(results, "xlog") else 0,
                    "final_cost": float(results.fopt) if hasattr(results, "fopt") else None,
                },
            }

        except Exception as exc:
            return {
                "track": "pybop",
                "parameter_set": parameter_set,
                "results": {},
                "summary": {},
                "error": str(exc),
            }

    # ------------------------------------------------------------------
    # Fallbacks (当 PyBaMM/PyBOP 不可用时)
    # ------------------------------------------------------------------

    def _fallback_p2d(
        self,
        model_type: str,
        parameter_set: str,
        requested_variables: list[str],
    ) -> dict[str, Any]:
        """PyBaMM 不可用时的回退：返回占位仿真结果。"""
        import math

        n_points = 100
        t = [i * 36.0 for i in range(n_points)]  # 0-3600s

        results: dict[str, list[float]] = {}
        for var in requested_variables:
            if "voltage" in var.lower():
                results[var] = [4.2 - 0.3 * math.sin(math.pi * i / n_points) for i in range(n_points)]
            elif "current" in var.lower():
                results[var] = [1.0] * n_points
            elif "capacity" in var.lower():
                results[var] = [5.0 * i / n_points for i in range(n_points)]
            elif "temperature" in var.lower():
                results[var] = [298.15 + 5.0 * math.sin(math.pi * i / n_points) for i in range(n_points)]
            else:
                results[var] = [0.0] * n_points

        results["Time [s]"] = t

        return {
            "track": "p2d",
            "model_type": model_type,
            "parameter_set": parameter_set,
            "results": results,
            "summary": {
                "final_voltage": 3.0,
                "total_capacity": 5.0,
                "max_temperature": 303.15,
            },
            "warning": "PyBaMM not available; using placeholder simulation data",
        }

    def _fallback_ecm(
        self,
        model_type: str,
        requested_variables: list[str],
    ) -> dict[str, Any]:
        """ECM 回退：返回占位仿真结果。"""
        import math

        n_points = 100
        t = [i * 10.0 for i in range(n_points)]

        results: dict[str, list[float]] = {}
        for var in requested_variables:
            if "voltage" in var.lower():
                results[var] = [3.8 - 0.2 * math.sin(math.pi * i / n_points) for i in range(n_points)]
            elif "current" in var.lower():
                results[var] = [1.0] * n_points
            else:
                results[var] = [0.0] * n_points

        results["Time [s]"] = t

        return {
            "track": "ecm",
            "model_type": model_type,
            "results": results,
            "summary": {"final_voltage": 3.6},
            "warning": "PyBaMM not available; using placeholder ECM data",
        }

    def _fallback_pybop(self, parameter_set: str) -> dict[str, Any]:
        """PyBOP 回退：返回占位辨识结果。"""
        return {
            "track": "pybop",
            "parameter_set": parameter_set,
            "results": {
                "optimized_params": [1.0, 0.5, 0.1],
                "cost": 0.05,
            },
            "summary": {
                "optimizer": "CMAES (placeholder)",
                "iterations": 50,
                "final_cost": 0.05,
            },
            "warning": "PyBOP not available; using placeholder identification data",
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_experiment(protocol: list[dict]) -> Any:
        """将协议步骤列表转换为 PyBaMM Experiment 对象。

        每个步骤 dict 支持格式:
            {"type": "cccv_cycle", "cycles": 3}
            {"type": "discharge", "current": "C/5", "until": "2.5 V"}
            {"type": "charge", "current": "C/5", "until": "4.2 V"}
            {"type": "rest", "duration": "10 minutes"}
            {"type": "hold", "voltage": "4.2 V", "until": "50 mA"}
        """
        import pybamm  # type: ignore[import-untyped]

        step_strings: list[str] = []
        for step in protocol:
            step_type = step.get("type", "")
            if step_type == "cccv_cycle":
                cycles = step.get("cycles", 1)
                for _ in range(cycles):
                    step_strings.extend(_DEFAULT_CCCV_STEPS)
            elif step_type == "discharge":
                current = step.get("current", "C/5")
                until = step.get("until", "2.5 V")
                step_strings.append(f"Discharge at {current} until {until}")
            elif step_type == "charge":
                current = step.get("current", "C/5")
                until = step.get("until", "4.2 V")
                step_strings.append(f"Charge at {current} until {until}")
            elif step_type == "rest":
                duration = step.get("duration", "10 minutes")
                step_strings.append(f"Rest for {duration}")
            elif step_type == "hold":
                voltage = step.get("voltage", "4.2 V")
                until = step.get("until", "50 mA")
                step_strings.append(f"Hold at {voltage} until {until}")
            else:
                step_strings.append(f"Rest for 10 minutes")

        return pybamm.Experiment(step_strings)

    @staticmethod
    def _extract_summary(
        sol: Any,
        requested_variables: list[str],
    ) -> dict[str, Any]:
        """从 PyBaMM 求解结果中提取摘要统计。"""
        summary: dict[str, Any] = {}

        try:
            v = sol["Terminal voltage [V]"].entries
            summary["min_voltage"] = float(v.min())
            summary["max_voltage"] = float(v.max())
            summary["final_voltage"] = float(v[-1])
        except (KeyError, AttributeError):
            pass

        try:
            cap = sol["Discharge capacity [A.h]"].entries
            summary["total_capacity"] = float(cap[-1])
        except (KeyError, AttributeError):
            pass

        try:
            temp = sol["Cell temperature [K]"].entries
            summary["max_temperature"] = float(temp.max())
        except (KeyError, AttributeError):
            try:
                temp = sol["X-averaged cell temperature [K]"].entries
                summary["max_temperature"] = float(temp.max())
            except (KeyError, AttributeError):
                pass

        return summary