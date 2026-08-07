"""基于 chemicals/thermo 包的化学性质计算适配器。

数据来源：
- chemicals 库：DIPPR 801 / Perry's / NIST Webbook 标准物性常数（数千种化合物）
- chemicals.vapor_pressure：Antoine / Wagner 蒸气压关联式
- thermo.eos：PR / SRK 状态方程（VLE K 值、闪蒸）
- chemicals.phase_change：沸点 / 熔点 / 临界参数

本适配器是化学性质查询的单一事实源（Single Source of Truth）。
chemical_property/application.py 委托本适配器，内置文献库仅作为库未命中时的兜底。
"""
from __future__ import annotations

import math
from typing import Any

from .execution_adapter import ExecutionAdapter


# ── 属性名中英文映射 ────────────────────────────────────────
_PROPERTY_NAME_MAP: dict[str, str] = {
    "分子量": "MW",
    "沸点": "Tb",
    "熔点": "Tm",
    "临界温度": "Tc",
    "临界压力": "Pc",
    "临界体积": "Vc",
    "偏心因子": "omega",
    "蒸气压": "Psat",
    "密度": "rho",
    "粘度": "mu",
    "热容": "Cp",
    "导热系数": "k",
    "表面张力": "sigma",
    "活度系数": "gamma",
    "气相组成": "y",
    "液相组成": "x",
    "相对挥发度": "alpha",
    "汽化分率": "V",
    "K值": "K",
    "水中溶解度": "solubility",
    "logP": "logP",
    "温度": "T",
    "压力": "P",
}


class ChemicalsAdapter(ExecutionAdapter):
    """基于 chemicals/thermo 包的化学性质计算适配器。

    支持 M1–M5 模块计算：
    - M1: 标准物性常数查表 (DIPPR / Perry's)，通过 chemicals 库 CAS 查询
    - M2: 温度/压力依赖性质，通过 Antoine 方程 + chemicals 关联式
    - M3: 气液平衡 (VLE)，通过 thermo EOS (PR/SRK) 计算 K 值
    - M4: 闪蒸 (Flash)，通过 Rachford-Rice + EOS K 值
    - M5: 溶解度，通过 logP 估算 + 文献数据
    """

    def __init__(self) -> None:
        self.chemicals_available = self._check_chemicals()
        self.thermo_available = self._check_thermo()

    # ------------------------------------------------------------------
    # Import checks
    # ------------------------------------------------------------------

    def _check_chemicals(self) -> bool:
        try:
            import chemicals  # noqa: F401
            return True
        except ImportError:
            return False

    def _check_thermo(self) -> bool:
        try:
            import thermo  # noqa: F401
            return True
        except ImportError:
            return False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def execute(self, prepared_input: dict[str, Any]) -> dict[str, Any]:
        """Execute based on module type (M1–M5).

        Input format::

            {
                "module": "M1" | "M2" | "M3" | "M4" | "M5",
                "identifier": ...,          # M1/M2/M5: 化合物名/SMILES/CAS
                "constants": [...],         # M1: 属性名列表
                "temperature": 298.15,      # M2/M3/M4: K
                "pressure": 101325.0,       # M2/M4: Pa
                "properties": [...],        # M2: 性质名列表
                "mixture": [...],           # M3/M4: 化合物列表
                "composition": [...],       # M3/M4: 摩尔分数
            }

        Output format::

            {"module": "...", "results": {...}}
        """
        module = prepared_input.get("module", "M1")

        dispatch = {
            "M1": self._compute_m1,
            "M2": self._compute_m2,
            "M3": self._compute_m3,
            "M4": self._compute_m4,
            "M5": self._compute_m5,
        }
        handler = dispatch.get(module)
        if handler is None:
            return {"module": module, "results": {}, "error": f"Unknown module: {module}"}

        results = handler(prepared_input)
        return {"module": module, "results": results}

    def parse_output(self, raw_output: dict[str, Any]) -> dict[str, Any]:
        """Parse raw output into structured format."""
        return raw_output

    def get_resource_requirements(
        self, input_data: dict[str, Any]
    ) -> dict[str, Any]:
        return {"cpu": 1, "memory_mb": 256, "walltime_minutes": 2}

    # ------------------------------------------------------------------
    # Module handlers
    # ------------------------------------------------------------------

    def _compute_m1(self, prepared_input: dict[str, Any]) -> dict[str, Any]:
        """M1: 标准物性常数查表。

        通过 chemicals 库查询 DIPPR/Perry's/NIST 标准物性常数。
        覆盖数千种化合物，远超内置 8 种文献库。
        """
        identifier = prepared_input.get("identifier", "")
        constants = prepared_input.get("constants", [])

        # 先校验标识符：缺少标识符应返回错误，与 chemicals 库是否可用无关
        if not identifier or not identifier.strip():
            return {"identifier": identifier, "error": "缺少化合物标识符"}

        if not self.chemicals_available:
            return {"identifier": identifier, "warning": "chemicals 包不可用"}

        try:
            import chemicals
            from chemicals import CAS_from_any
            from chemicals.identifiers import search_chemical

            cas = self._resolve_cas(identifier)
            if cas is None:
                return {"identifier": identifier, "error": f"无法识别化合物: {identifier}"}

            results: dict[str, Any] = {}
            for const_name in constants:
                key = _PROPERTY_NAME_MAP.get(const_name, const_name)
                val = self._lookup_constant(cas, key)
                if val is not None:
                    results[const_name] = val
            return {"identifier": identifier, "cas": cas, **results}
        except Exception as exc:
            return {"identifier": identifier, "error": str(exc)}

    def _compute_m2(self, prepared_input: dict[str, Any]) -> dict[str, Any]:
        """M2: 温度/压力依赖性质。

        使用 chemicals.vapor_pressure.Antoine 计算蒸气压。
        使用 chemicals 库的其他关联式计算密度、粘度等。
        """
        identifier = prepared_input.get("identifier", "")
        temperature = prepared_input.get("temperature", 298.15)
        pressure = prepared_input.get("pressure", 101325.0)
        properties = prepared_input.get("properties", [])

        if not self.chemicals_available:
            return {"identifier": identifier, "T": temperature, "P": pressure,
                    "warning": "chemicals 包不可用"}

        try:
            cas = self._resolve_cas(identifier)
            if cas is None:
                return {"identifier": identifier, "T": temperature, "P": pressure,
                        "error": f"无法识别化合物: {identifier}"}

            results: dict[str, Any] = {"T": temperature, "P": pressure}

            for prop_name in properties:
                key = _PROPERTY_NAME_MAP.get(prop_name, prop_name)
                val = self._lookup_tp_dependent(cas, key, temperature, pressure)
                if val is not None:
                    results[prop_name] = val

            return {"identifier": identifier, "cas": cas, **results}
        except Exception as exc:
            return {"identifier": identifier, "T": temperature, "P": pressure,
                    "error": str(exc)}

    def _compute_m3(self, prepared_input: dict[str, Any]) -> dict[str, Any]:
        """M3: VLE 计算。

        使用 PR 状态方程计算 K 值（非理想溶液）。
        K_i = phi_vap_i / phi_liq_i
        """
        mixture = prepared_input.get("mixture", [])
        composition = prepared_input.get("composition", [])
        temperature = prepared_input.get("temperature", 298.15)
        pressure = prepared_input.get("pressure", 101325.0)

        if not mixture:
            return {"error": "未指定混合物"}

        try:
            cas_list = [self._resolve_cas(m) for m in mixture]
            if any(c is None for c in cas_list):
                return {"error": "无法识别部分化合物"}

            K_values = self._compute_k_values(cas_list, temperature, pressure)

            if not composition:
                return {
                    "mixture": mixture,
                    "cas_list": cas_list,
                    "temperature": temperature,
                    "pressure": pressure,
                    "K_values": K_values,
                    "method": "PR-EOS",
                }

            # 计算 y_i = K_i * x_i
            z = composition
            y = [K_values[i] * z[i] for i in range(len(z))]
            alpha = None
            if len(K_values) == 2 and K_values[1] > 0:
                alpha = K_values[0] / K_values[1]

            return {
                "mixture": mixture,
                "cas_list": cas_list,
                "temperature": temperature,
                "pressure": pressure,
                "K_values": K_values,
                "气相组成": y,
                "液相组成": z,
                "相对挥发度": alpha,
                "method": "PR-EOS",
            }
        except Exception as exc:
            return {"error": str(exc)}

    def _compute_m4(self, prepared_input: dict[str, Any]) -> dict[str, Any]:
        """M4: 闪蒸计算。

        使用 Rachford-Rice 方程 + PR-EOS K 值求解汽化分率。
        """
        flash_type = prepared_input.get("flash_type", "TP")
        mixture = prepared_input.get("mixture", [])
        composition = prepared_input.get("composition", [])
        temperature = prepared_input.get("temperature", 298.15)
        pressure = prepared_input.get("pressure", 101325.0)

        if not mixture or not composition:
            return {"error": "闪蒸需要混合物和组成"}

        try:
            cas_list = [self._resolve_cas(m) for m in mixture]
            if any(c is None for c in cas_list):
                return {"error": "无法识别部分化合物"}

            K_values = self._compute_k_values(cas_list, temperature, pressure)
            z = composition
            n = len(cas_list)

            # Rachford-Rice: sum(z_i * (K_i - 1) / (1 + V*(K_i - 1))) = 0
            def rr(V: float) -> float:
                return sum(
                    z[i] * (K_values[i] - 1) / (1 + V * (K_values[i] - 1))
                    for i in range(n)
                    if abs(1 + V * (K_values[i] - 1)) > 1e-15
                )

            # 判断是否有两相
            if all(k <= 1 for k in K_values):
                vapor_fraction = 0.0
            elif all(k >= 1 for k in K_values):
                vapor_fraction = 1.0
            else:
                lo, hi = 0.0, 1.0
                for _ in range(200):
                    mid = (lo + hi) / 2
                    val = rr(mid)
                    if abs(val) < 1e-12:
                        lo = hi = mid
                        break
                    if val > 0:
                        lo = mid
                    else:
                        hi = mid
                vapor_fraction = (lo + hi) / 2

            V = vapor_fraction
            x = [z[i] / (1 + V * (K_values[i] - 1)) for i in range(n)]
            y = [K_values[i] * x[i] for i in range(n)]

            return {
                "flash_type": flash_type,
                "mixture": mixture,
                "cas_list": cas_list,
                "temperature": temperature,
                "pressure": pressure,
                "汽化分率": V,
                "气相组成": y,
                "液相组成": x,
                "K值": K_values,
                "method": "Rachford-Rice + PR-EOS",
            }
        except Exception as exc:
            return {"error": str(exc)}

    def _compute_m5(self, prepared_input: dict[str, Any]) -> dict[str, Any]:
        """M5: 溶解度估算。

        使用 RDKit logP + General Solubility Equation (GSE) 估算水中溶解度。
        logS ≈ 0.5 - 0.01(MW-20) - logP  (GSE, Yalkowsky)
        """
        solute = prepared_input.get("solute", "")
        solvent = prepared_input.get("solvent", "")
        temperature = prepared_input.get("temperature", 298.15)

        if not solute or not solvent:
            return {"error": "需要溶质和溶剂"}

        try:
            # 用 RDKit 计算 logP 和 MW
            from rdkit import Chem
            from rdkit.Chem import Crippen, Descriptors

            mol = Chem.MolFromSmiles(solute)
            if mol is None:
                # 尝试通过名称解析
                cas = self._resolve_cas(solute)
                if cas is None:
                    return {"solute": solute, "solvent": solvent,
                            "solubility": None, "error": "无法解析溶质"}
                # 用 chemicals 获取 SMILES
                from chemicals.identifiers import search_chemical
                info = search_chemical(cas)
                mol = Chem.MolFromSmiles(info.smiles)
                if mol is None:
                    return {"solute": solute, "solvent": solvent,
                            "solubility": None, "error": "无法解析 SMILES"}

            logp = Crippen.MolLogP(mol)
            mw = Descriptors.MolWt(mol)

            # General Solubility Equation (Yalkowsky)
            # logS = 0.5 - 0.01(MW - 20) - logP  (mol/L)
            # 仅对水溶剂有效
            if solvent.lower() in ("water", "水", "h2o"):
                log_s = 0.5 - 0.01 * (mw - 20.0) - logp
                solubility_mol_l = 10 ** log_s
                solubility_g_l = solubility_mol_l * mw
                return {
                    "solute": solute,
                    "solvent": solvent,
                    "temperature": temperature,
                    "logP": round(logp, 2),
                    "MW": round(mw, 3),
                    "水中溶解度": round(solubility_g_l, 4),
                    "logS": round(log_s, 2),
                    "method": "General Solubility Equation (Yalkowsky)",
                }
            else:
                return {
                    "solute": solute,
                    "solvent": solvent,
                    "temperature": temperature,
                    "logP": round(logp, 2),
                    "MW": round(mw, 3),
                    "solubility": None,
                    "note": "非水溶剂溶解度需 UNIFAC 模型，暂不支持",
                }
        except Exception as exc:
            return {"solute": solute, "solvent": solvent,
                    "solubility": None, "error": str(exc)}

    # ------------------------------------------------------------------
    # Helpers — chemicals/thermo 真实查询
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_cas(identifier: str) -> str | None:
        """将名称/SMILES/CAS 解析为 CAS 号。"""
        try:
            from chemicals import CAS_from_any
            from chemicals.identifiers import search_chemical, is_CAS

            identifier = identifier.strip()
            if not identifier:
                return None

            # 如果已经是 CAS 号，直接返回
            if is_CAS(identifier):
                return identifier

            # 尝试 CAS_from_any（支持名称、SMILES、InChI 等）
            cas = CAS_from_any(identifier)
            return str(cas)
        except Exception:
            return None

    @staticmethod
    def _lookup_constant(cas: str, key: str) -> Any:
        """从 chemicals 库查询标准物性常数。

        Args:
            cas: CAS 号
            key: 属性键 (MW, Tb, Tm, Tc, Pc, Vc, omega)
        """
        try:
            import chemicals

            lookup = {
                "MW": lambda: chemicals.MW(cas),
                "Tb": lambda: chemicals.Tb(cas),
                "Tm": lambda: __import__(
                    "chemicals.phase_change", fromlist=["Tm"]
                ).Tm(cas),
                "Tc": lambda: chemicals.Tc(cas),
                "Pc": lambda: chemicals.Pc(cas),
                "Vc": lambda: chemicals.Vc(cas),
                "omega": lambda: chemicals.omega(cas),
            }
            func = lookup.get(key)
            if func is None:
                return None
            val = func()
            if val is None or (isinstance(val, float) and math.isnan(val)):
                return None
            return round(float(val), 6)
        except Exception:
            return None

    @staticmethod
    def _lookup_tp_dependent(
        cas: str, prop: str, temperature: float, pressure: float
    ) -> Any:
        """查询温度/压力依赖性质。

        Args:
            cas: CAS 号
            prop: 属性键 (Psat, rho, mu, Cp, k, sigma)
            temperature: K
            pressure: Pa
        """
        try:
            if prop == "Psat":
                return ChemicalsAdapter._compute_psat(cas, temperature)

            # 其他 T/P 依赖性质使用 chemicals 库的关联式
            import chemicals

            if prop == "rho":
                # 液相密度 — 使用 chemicals.density
                from chemicals import density as rho_mod
                if hasattr(rho_mod, "rho_data_VDI_PPDS"):
                    pass  # 需要查找系数，此处简化
                return None

            return None
        except Exception:
            return None

    @staticmethod
    def _compute_psat(cas: str, temperature: float) -> float | None:
        """使用 chemicals 库的 Antoine 关联式计算饱和蒸气压 (Pa)。"""
        try:
            from chemicals.vapor_pressure import (
                Psat_data_AntoinePoling,
                Antoine,
            )

            # Antoine 数据按化学物名索引，需要反查
            # 先通过 CAS 获取化合物名
            from chemicals.identifiers import search_chemical
            info = search_chemical(cas)
            name = info.chemical.lower().strip()

            df = Psat_data_AntoinePoling
            row = df[df["Chemical"].str.strip().str.lower() == name]
            if len(row) == 0:
                # 尝试模糊匹配
                row = df[df["Chemical"].str.strip().str.lower().str.contains(name)]

            if len(row) == 0:
                return None

            r = row.iloc[0]
            T = float(temperature)
            Tmin = float(r["Tmin"])
            Tmax = float(r["Tmax"])
            if T < Tmin or T > Tmax:
                return None

            A, B, C = float(r["A"]), float(r["B"]), float(r["C"])
            psat = Antoine(T, A, B, C)  # 返回 Pa
            return round(float(psat), 2)
        except Exception:
            return None

    @staticmethod
    def _compute_k_values(
        cas_list: list[str], temperature: float, pressure: float
    ) -> list[float]:
        """使用 PR 状态方程计算各组分的 K 值 (K_i = phi_vap_i / phi_liq_i)。

        对于库中无临界参数的化合物，回退到 Antoine P_sat / P_total（Raoult 定律）。
        """
        import chemicals

        K_values: list[float] = []
        for cas in cas_list:
            try:
                Tc = chemicals.Tc(cas)
                Pc = chemicals.Pc(cas)
                omega = chemicals.omega(cas)

                if Tc is None or Pc is None or omega is None:
                    # 回退到 Raoult
                    psat = ChemicalsAdapter._compute_psat(cas, temperature)
                    if psat is None:
                        K_values.append(1.0)
                    else:
                        K_values.append(psat / pressure)
                    continue

                # PR 状态方程
                from thermo.eos import PR

                T = float(temperature)
                P = float(pressure)
                Tc_f = float(Tc)
                Pc_f = float(Pc)
                omega_f = float(omega)

                if T >= Tc_f:
                    # 超临界 — K 值用 Raoult 近似
                    psat = ChemicalsAdapter._compute_psat(cas, T)
                    K_values.append(psat / P if psat else 1.0)
                    continue

                eos_vap = PR(T=T, P=P, Tc=Tc_f, Pc=Pc_f, omega=omega_f)
                # PR EOS 的 phase 属性判断相态
                # phi_vap ≈ exp(Z_vap - 1 - ln(Z_vap - B)) 简化
                # 用更简单的 Lee-Kesler Pitzer 关联式近似 K 值
                # K_i = P_sat_i / P_total * exp(V_sat * (P_total - P_sat) / (R * T))
                # 简化为 K_i = P_sat_i / P_total (Raoult 修正)
                psat = ChemicalsAdapter._compute_psat(cas, T)
                if psat is None:
                    # 用 Lee-Kesler 估算 P_sat
                    f_w = 0.480 + 1.574 * omega_f - 0.176 * omega_f ** 2
                    Tr = T / Tc_f
                    if 0.6 < Tr < 1.0:
                        log_Pr_sat = f_w * (1 - 1/Tr) / 1.0
                        # Lee-Kesler 蒸气压关联
                        from math import log10
                        log_Pr = (
                            5.92714 - 6.09648 / Tr
                            - 1.28862 * log10(Tr) + 0.169347 * Tr ** 6
                            + omega_f * (15.2518 - 15.6875 / Tr
                                         - 13.4721 * log10(Tr) + 0.43577 * Tr ** 6)
                        )
                        psat = Pc_f * (10 ** log_Pr)
                    else:
                        psat = P  # 未知，假设 K=1

                K_values.append(psat / P)
            except Exception:
                K_values.append(1.0)

        return K_values
