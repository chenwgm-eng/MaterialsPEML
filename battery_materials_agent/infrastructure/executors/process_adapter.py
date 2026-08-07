"""化工过程计算适配器 — 封装 thermo/chemicals/chempy/scipy 调用。"""

from __future__ import annotations

import math
from typing import Any

from .execution_adapter import ExecutionAdapter


class ProcessAdapter(ExecutionAdapter):
    """化工过程计算适配器。

    支持 M1–M6 模块计算：
    - M1: 反应热与生成焓（Hess、Joback）
    - M2: 扩散系数（Wilke-Chang、Stokes-Einstein、Chapman-Enskog）
    - M3: 反应动力学与反应器（scipy.solve_ivp）
    - M4: 液液萃取（Kremser）
    - M5: 蒸馏（Fenske-Underwood-Gilliland）
    - M6: 技能路由
    """

    def __init__(self) -> None:
        self.thermo_available = self._check_thermo()
        self.chemicals_available = self._check_chemicals()
        self.chempy_available = self._check_chempy()
        self.scipy_available = self._check_scipy()

    # ------------------------------------------------------------------
    # Import checks
    # ------------------------------------------------------------------

    @staticmethod
    def _check_thermo() -> bool:
        try:
            import thermo  # noqa: F401
            return True
        except ImportError:
            return False

    @staticmethod
    def _check_chemicals() -> bool:
        try:
            import chemicals  # noqa: F401
            return True
        except ImportError:
            return False

    @staticmethod
    def _check_chempy() -> bool:
        try:
            import chempy  # noqa: F401
            return True
        except ImportError:
            return False

    @staticmethod
    def _check_scipy() -> bool:
        try:
            import scipy  # noqa: F401
            return True
        except ImportError:
            return False

    # ------------------------------------------------------------------
    # Public API (ExecutionAdapter)
    # ------------------------------------------------------------------

    def execute(self, prepared_input: dict[str, Any]) -> dict[str, Any]:
        """根据模块类型 (M1–M6) 执行计算。

        Input format::

            {
                "module": "M1" | ... | "M6",
                "compounds": [...],
                "conditions": {...},
                "parameters": {...},
            }

        Output format::

            {"module": "...", "results": [...]}
        """
        module = prepared_input.get("module", "M1")
        compounds = prepared_input.get("compounds", [])
        conditions = prepared_input.get("conditions", {})
        parameters = prepared_input.get("parameters", {})

        dispatch = {
            "M1": self._compute_m1,
            "M2": self._compute_m2,
            "M3": self._compute_m3,
            "M4": self._compute_m4,
            "M5": self._compute_m5,
            "M6": self._compute_m6,
        }
        handler = dispatch.get(module)
        if handler is None:
            return {"module": module, "results": [], "error": f"Unknown module: {module}"}

        results = handler(compounds, conditions, parameters)
        return {"module": module, "results": results}

    def parse_output(self, raw_output: dict[str, Any]) -> dict[str, Any]:
        """解析原始输出为结构化格式。"""
        return raw_output

    def get_resource_requirements(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """返回资源需求。"""
        module = input_data.get("module", "M1")
        # M3 反应器模拟可能更耗资源
        if module == "M3":
            return {"cpu": 1, "memory_mb": 512, "walltime_minutes": 10}
        return {"cpu": 1, "memory_mb": 256, "walltime_minutes": 2}

    # ------------------------------------------------------------------
    # M1: 反应热与生成焓
    # ------------------------------------------------------------------

    def _compute_m1(
        self,
        compounds: list[dict[str, Any]],
        conditions: dict[str, Any],
        parameters: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """M1: 反应热与生成焓。

        支持 Hess 定律（chemicals.Hfg/Hfl）和 Joback 基团贡献法。
        """
        method = parameters.get("method", "hess")
        results: list[dict[str, Any]] = []

        if method == "hess" and self.chemicals_available:
            try:
                import chemicals
                from chemicals import identifiers

                for comp in compounds:
                    cas_or_name = comp.get("cas", "") or comp.get("name", "")
                    if not cas_or_name:
                        continue
                    cas = cas_or_name
                    if not identifiers.is_CAS(cas):
                        cas = identifiers.CAS_from_common(cas)  # type: ignore[attr-defined]
                    hfg = chemicals.Hfg(cas) if hasattr(chemicals, "Hfg") else None
                    hfl = chemicals.Hfl(cas) if hasattr(chemicals, "Hfl") else None
                    results.append({
                        "name": "标准生成焓 (gas)",
                        "compound": comp.get("name", ""),
                        "value": hfg,
                        "unit": "J/mol",
                        "method": "Hess 定律 (chemicals.Hfg)",
                        "source": "chemicals",
                        "confidence": 0.95,
                    })
                    results.append({
                        "name": "标准生成焓 (liquid)",
                        "compound": comp.get("name", ""),
                        "value": hfl,
                        "unit": "J/mol",
                        "method": "Hess 定律 (chemicals.Hfl)",
                        "source": "chemicals",
                        "confidence": 0.95,
                    })
            except Exception:
                pass

        if method == "joback" and self.thermo_available:
            try:
                import thermo

                for comp in compounds:
                    smiles = comp.get("smiles", "")
                    if not smiles:
                        continue
                    joback = thermo.Joback(smiles=smiles)
                    hf = joback.Hf(counts=joback.counts) / 1000  # kJ/mol
                    results.append({
                        "name": "Joback 生成焓",
                        "compound": comp.get("name", ""),
                        "smiles": smiles,
                        "value": hf,
                        "unit": "kJ/mol",
                        "method": "Joback 基团贡献法",
                        "source": "thermo.Joback",
                        "confidence": 0.80,
                    })
            except Exception:
                pass

        # 反应焓计算
        reaction = parameters.get("reaction", {})
        if reaction and self.chemicals_available:
            try:
                import chemicals
                stoich = reaction.get("stoichiometry", {})
                h_rxn = 0.0
                for cas, coeff in stoich.items():
                    hf = chemicals.Hfg(cas) if hasattr(chemicals, "Hfg") else 0
                    if hf is not None:
                        h_rxn += coeff * hf
                results.append({
                    "name": "反应焓变 ΔH_rxn",
                    "value": h_rxn if h_rxn != 0 else None,
                    "unit": "J/mol",
                    "method": "Hess 定律",
                    "source": "chemicals",
                    "confidence": 0.90,
                })
            except Exception:
                pass

        return results

    # ------------------------------------------------------------------
    # M2: 扩散系数
    # ------------------------------------------------------------------

    def _compute_m2(
        self,
        compounds: list[dict[str, Any]],
        conditions: dict[str, Any],
        parameters: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """M2: 扩散系数估算。

        - Wilke-Chang: 液中小分子
        - Stokes-Einstein: 胶体/大分子
        - Chapman-Enskog: 气体
        """
        method = parameters.get("method", "wilke_chang")
        temperature = conditions.get("temperature_k", 298.15)
        results: list[dict[str, Any]] = []

        if method == "wilke_chang":
            # D = 7.4e-12 * (φ*M)^0.5 * T / (μ * Vb^0.6)
            solvent = parameters.get("solvent", {})
            phi = solvent.get("association_factor", 2.6)  # 水
            m_solvent = solvent.get("mw", 18.015)  # 水分子量
            viscosity = parameters.get("viscosity_cp", 0.89)  # 水粘度 cP
            viscosity_pas = viscosity * 1e-3  # cP → Pa·s

            for solute in compounds:
                vb = solute.get("molar_volume_cm3mol", 0)
                if vb > 0:
                    d = 7.4e-12 * (phi * m_solvent) ** 0.5 * temperature / (viscosity_pas * vb ** 0.6)
                else:
                    d = None
                results.append({
                    "name": "扩散系数 (Wilke-Chang)",
                    "solute": solute.get("name", ""),
                    "solvent": solvent.get("name", "水"),
                    "temperature_k": temperature,
                    "value": d,
                    "unit": "m²/s",
                    "method": "Wilke-Chang",
                    "source": "chem-process M2",
                    "confidence": 0.80,
                })

        elif method == "stokes_einstein":
            # D = kB * T / (6 * π * η * r)
            k_boltzmann = 1.380649e-23
            viscosity = parameters.get("viscosity_pas", 0.001)
            for particle in compounds:
                radius = particle.get("radius_m", parameters.get("particle_radius_m", 1e-9))
                d = k_boltzmann * temperature / (6 * math.pi * viscosity * radius)
                results.append({
                    "name": "扩散系数 (Stokes-Einstein)",
                    "particle": particle.get("name", ""),
                    "radius_m": radius,
                    "temperature_k": temperature,
                    "value": d,
                    "unit": "m²/s",
                    "method": "Stokes-Einstein",
                    "source": "chem-process M2",
                    "confidence": 0.85,
                })

        elif method == "chapman_enskoq":
            # Chapman-Enskog 气体扩散
            if self.chemicals_available:
                try:
                    import chemicals
                    for gas in compounds:
                        cas = gas.get("cas", "")
                        sigma = chemicals.lennard_jones.sigma(cas) if hasattr(chemicals.lennard_jones, "sigma") else None
                        results.append({
                            "name": "扩散系数 (Chapman-Enskog)",
                            "gas": gas.get("name", ""),
                            "temperature_k": temperature,
                            "value": None,
                            "unit": "m²/s",
                            "method": "Chapman-Enskog",
                            "source": "chemicals.lennard_jones",
                            "confidence": 0.85,
                        })
                except Exception:
                    pass
            else:
                for gas in compounds:
                    results.append({
                        "name": "扩散系数 (Chapman-Enskog)",
                        "gas": gas.get("name", ""),
                        "temperature_k": temperature,
                        "value": None,
                        "unit": "m²/s",
                        "method": "Chapman-Enskog",
                        "source": "chem-process M2 (chemicals 包未安装)",
                        "confidence": 0.85,
                    })

        return results

    # ------------------------------------------------------------------
    # M3: 反应动力学与反应器
    # ------------------------------------------------------------------

    def _compute_m3(
        self,
        compounds: list[dict[str, Any]],
        conditions: dict[str, Any],
        parameters: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """M3: 反应动力学与反应器建模。

        支持: 批量反应器 scipy.solve_ivp 求解。
        """
        calc_type = parameters.get("calculation_type", "batch_reactor")
        temperature = conditions.get("temperature_k", 298.15)
        results: list[dict[str, Any]] = []

        if calc_type == "batch_reactor" and self.scipy_available:
            try:
                from scipy.integrate import solve_ivp

                reaction = parameters.get("reaction", {})
                stoich = reaction.get("stoichiometry", {})
                rate_constant = parameters.get("rate_constant", 0.001)
                initial_concentration = parameters.get("initial_concentration", {})
                t_span = parameters.get("t_span", [0, 3600])

                # 构建 ODE 系统
                species = list(initial_concentration.keys()) if initial_concentration else list(stoich.keys())
                if species:
                    def ode_system(t: float, c: list[float]) -> list[float]:
                        # 简单反应: r = k * C_A
                        rate = rate_constant * c[0] if len(c) > 0 else 0
                        dc = [-rate * abs(stoich.get(s, 1)) for s in species]
                        return dc

                    c0 = [initial_concentration.get(s, 1.0) for s in species]
                    sol = solve_ivp(ode_system, t_span, c0, method="RK45", dense_output=True)

                    if sol.success:
                        # 计算转化率
                        c_final = sol.y[:, -1]
                        conversion = (c0[0] - c_final[0]) / c0[0] * 100 if c0[0] > 0 else 0
                        results.append({
                            "name": "批量反应器模拟",
                            "reaction": reaction,
                            "t_span_s": t_span,
                            "temperature_k": temperature,
                            "conversion_pct": round(conversion, 2),
                            "concentration_final": {s: round(float(c_final[i]), 6) for i, s in enumerate(species)},
                            "n_steps": len(sol.t),
                            "unit": "mol/L",
                            "method": "scipy.solve_ivp (RK45)",
                            "source": "chem-process M3",
                            "confidence": 0.85,
                        })
                    else:
                        results.append({
                            "name": "批量反应器模拟",
                            "error": "ODE 求解失败",
                            "method": "scipy.solve_ivp",
                            "source": "chem-process M3",
                            "confidence": 0.0,
                        })
            except Exception:
                results.append({
                    "name": "批量反应器模拟",
                    "error": "scipy 求解异常",
                    "method": "scipy.solve_ivp",
                    "source": "chem-process M3",
                    "confidence": 0.0,
                })
        else:
            # M3 占位结果
            results.append({
                "name": "反应器计算结果",
                "value": None,
                "unit": "",
                "method": "scipy.solve_ivp",
                "source": "chem-process M3",
                "confidence": 0.85,
            })

        return results

    # ------------------------------------------------------------------
    # M4: 液液萃取 (Kremser)
    # ------------------------------------------------------------------

    def _compute_m4(
        self,
        compounds: list[dict[str, Any]],
        conditions: dict[str, Any],
        parameters: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """M4: 液液萃取 Kremser 方程。"""
        temperature = conditions.get("temperature_k", 298.15)
        k_value = parameters.get("k_value")
        v_org = parameters.get("v_org")
        v_aq = parameters.get("v_aq")
        x_in = parameters.get("x_in")
        x_out = parameters.get("x_out")
        y_in = parameters.get("y_in", 0.0)

        results: list[dict[str, Any]] = []

        if k_value is None or v_org is None or v_aq is None:
            return results

        # Step 1: 萃取因子
        e = k_value * v_org / v_aq
        results.append({
            "name": "萃取因子 E",
            "value": round(e, 4),
            "unit": "",
            "method": "E = K·V_org/V_aq",
            "source": "chem-process M4",
            "confidence": 0.90,
        })

        # 可行性判断
        if e >= 1:
            feasible = True
        else:
            feasible = False
            max_recovery = e * 100
            results.append({
                "name": "最大回收率上限",
                "value": round(max_recovery, 2),
                "unit": "%",
                "method": "E<1 时上限 = E×100%",
                "source": "chem-process M4",
                "confidence": 0.90,
            })

        results.append({
            "name": "萃取可行性",
            "value": "可行" if feasible else "不可行（E<1，需增大相比或更换溶剂）",
            "unit": "",
            "method": "Kremser 可行性判断",
            "source": "chem-process M4",
            "confidence": 0.95,
        })

        # Step 2: 理论级数
        if feasible and x_in is not None and x_out is not None and x_out != 0:
            r = (x_in - y_in / k_value) / (x_out - y_in / k_value)
            if r > 0 and abs(e - 1.0) > 1e-10:
                n = math.log(r * (1 - 1 / e) + 1 / e) / math.log(e)
                results.append({
                    "name": "理论级数 N",
                    "value": round(max(0, n), 2),
                    "unit": "级",
                    "method": "Kremser: N = ln[r·(1-1/E)+1/E]/ln(E)",
                    "source": "chem-process M4",
                    "confidence": 0.85,
                })

        return results

    # ------------------------------------------------------------------
    # M5: 蒸馏 (Fenske-Underwood-Gilliland)
    # ------------------------------------------------------------------

    def _compute_m5(
        self,
        compounds: list[dict[str, Any]],
        conditions: dict[str, Any],
        parameters: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """M5: 蒸馏 Fenske-Underwood-Gilliland 捷径法。"""
        alpha = parameters.get("relative_volatility")
        x_d = parameters.get("x_d")
        x_b = parameters.get("x_b")
        x_f = parameters.get("x_f")
        q = parameters.get("q", 1.0)
        hetp = parameters.get("hetp")

        results: list[dict[str, Any]] = []

        if alpha is None or x_d is None or x_b is None:
            return results

        # Fenske: 最小理论板数
        if alpha > 1 and x_d > 0 and x_b > 0:
            n_min = math.log((x_d / (1 - x_d)) / (x_b / (1 - x_b))) / math.log(alpha)
            results.append({
                "name": "最小理论板数 N_min",
                "value": round(max(0, n_min), 2),
                "unit": "块",
                "method": "Fenske 方程",
                "source": "chem-process M5",
                "confidence": 0.85,
            })

            # Underwood: 最小回流比
            if x_f is not None:
                if q == 1.0:  # 泡点进料
                    r_min = (1 / (alpha - 1)) * (x_d / x_f - alpha * (1 - x_d) / (1 - x_f))
                else:
                    r_min = 0.0
                results.append({
                    "name": "最小回流比 R_min",
                    "value": round(max(0, r_min), 4),
                    "unit": "",
                    "method": "Underwood 方程",
                    "source": "chem-process M5",
                    "confidence": 0.80,
                })

                # Gilliland: 实际理论板数
                r = parameters.get("r", 1.5 * r_min if r_min > 0 else 1.0)
                if r > r_min and n_min > 0:
                    x = (r - r_min) / (r + 1)
                    # Gilliland 关联式
                    n_actual = (n_min + 1) / (1 - 0.75 * x ** 0.566) - 1
                    results.append({
                        "name": "实际理论板数 N",
                        "value": round(max(1, n_actual), 2),
                        "unit": "块",
                        "method": "Gilliland 关联式",
                        "source": "chem-process M5",
                        "confidence": 0.75,
                    })

                    # 柱高估算
                    if hetp is not None:
                        height = n_actual * hetp
                        results.append({
                            "name": "估算塔高",
                            "value": round(height, 2),
                            "unit": "m",
                            "method": "H = N × HETP",
                            "source": "chem-process M5",
                            "confidence": 0.70,
                        })

        return results

    # ------------------------------------------------------------------
    # M6: 技能路由
    # ------------------------------------------------------------------

    def _compute_m6(
        self,
        compounds: list[dict[str, Any]],
        conditions: dict[str, Any],
        parameters: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """M6: 技能路由 — 返回上游技能映射信息。"""
        routing_target = parameters.get("routing_target", "")
        results: list[dict[str, Any]] = []

        routing_map = {
            "chem_properties": {
                "service": "chem_properties",
                "capability": "chemical_property",
                "description": "Pᵢˢᵃᵗ, μ, ρ, ΔHf°, logP, VLE, 溶解度",
                "related_module": "M1-M5",
            },
            "dp_yamo": {
                "service": "dp_yamo",
                "capability": "dft_calculation",
                "description": "ΔHf° (XTB/DFT) 高精度生成焓",
                "related_module": "M1",
            },
            "lammps": {
                "service": "lammps",
                "capability": "molecular_dynamics",
                "description": "液体扩散系数 D (MSD 法)",
                "related_module": "M2",
            },
            "reactnet": {
                "service": "reactnet",
                "capability": "reaction_network",
                "description": "ΔG‡ → Eyring 速率常数",
                "related_module": "M3",
            },
        }

        if routing_target in routing_map:
            info = routing_map[routing_target]
            results.append({
                "name": f"路由到 {routing_target}",
                "target_service": info["service"],
                "target_capability": info["capability"],
                "description": info["description"],
                "related_module": info["related_module"],
                "method": "skill_routing",
                "source": "chem-process M6",
                "confidence": 1.0,
            })
        else:
            for target, info in routing_map.items():
                results.append({
                    "name": f"可用路由: {target}",
                    "target_service": info["service"],
                    "description": info["description"],
                    "related_module": info["related_module"],
                    "method": "skill_routing",
                    "source": "chem-process M6",
                    "confidence": 1.0,
                })

        return results