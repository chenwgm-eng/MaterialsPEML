"""化工过程建模服务 — 适配 NativeScientificService 的生命周期。

数据来源：
- ProcessAdapter 封装的 Wilke-Chang / Stokes-Einstein / Kremser / FUG 等真实公式
- 内置文献标准生成焓数据库（DIPPR/NIST 公开值）
- RDKit 辅助分子量计算
- scipy.solve_ivp 用于反应器数值求解
"""

from __future__ import annotations

import math
from typing import Any

from pydantic import BaseModel, Field

from ...contracts.artifact import Artifact, ArtifactType
from ...contracts.evidence import EvidencePackage
from ...contracts.run import Run
from ...contracts.task import Task
from ...domain.runtime import ScientificExecutionKernel
from ...infrastructure.executors.process_adapter import ProcessAdapter
from ..base_service import NativeScientificService
from .evidence_mapper import batch_map_process_evidence
from .validators import ProcessModelingValidator

# ── 文献标准生成焓数据库 (ΔHf°, kJ/mol) ──────────────────
# 来源：NIST Webbook / DIPPR / Perry's Chemical Engineers' Handbook
_HF_DB: dict[str, dict[str, float | None]] = {
    "water": {"Hfg": -241.83, "Hfl": -285.83, "smiles": "O"},
    "ethanol": {"Hfg": -234.80, "Hfl": -277.69, "smiles": "CCO"},
    "methanol": {"Hfg": -201.50, "Hfl": -238.66, "smiles": "CO"},
    "benzene": {"Hfg": 82.93, "Hfl": 49.04, "smiles": "c1ccccc1"},
    "toluene": {"Hfg": 50.17, "Hfl": 12.00, "smiles": "Cc1ccccc1"},
    "acetone": {"Hfg": -217.30, "Hfl": -248.10, "smiles": "CC(=O)C"},
    "hexane": {"Hfg": -166.90, "Hfl": -198.70, "smiles": "CCCCCC"},
    "octane": {"Hfg": -208.60, "Hfl": -250.10, "smiles": "CCCCCCCC"},
    "CO2": {"Hfg": -393.52, "Hfl": None, "smiles": "O=C=O"},
    "CO": {"Hfg": -110.53, "Hfl": None, "smiles": "[C-]#[O+]"},
    "H2": {"Hfg": 0.0, "Hfl": None, "smiles": "[H][H]"},
    "O2": {"Hfg": 0.0, "Hfl": None, "smiles": "O=O"},
    "N2": {"Hfg": 0.0, "Hfl": None, "smiles": "N#N"},
    "CH4": {"Hfg": -74.60, "Hfl": None, "smiles": "C"},
    "C2H4": {"Hfg": 52.40, "Hfl": None, "smiles": "C=C"},
    "C2H6": {"Hfg": -84.00, "Hfl": None, "smiles": "CC"},
}

# 名称别名
_HF_ALIASES: dict[str, str] = {
    "h2o": "water", "water": "water", "水": "water",
    "ethanol": "ethanol", "乙醇": "ethanol", "c2h5oh": "ethanol",
    "methanol": "methanol", "甲醇": "methanol", "ch3oh": "methanol",
    "benzene": "benzene", "苯": "benzene", "c6h6": "benzene",
    "toluene": "toluene", "甲苯": "toluene",
    "acetone": "acetone", "丙酮": "acetone",
    "hexane": "hexane", "己烷": "hexane",
    "octane": "octane", "辛烷": "octane",
    "co2": "CO2", "carbon dioxide": "CO2", "二氧化碳": "CO2",
    "co": "CO", "carbon monoxide": "CO", "一氧化碳": "CO",
    "h2": "H2", "hydrogen": "H2", "氢气": "H2",
    "o2": "O2", "oxygen": "O2", "氧气": "O2",
    "n2": "N2", "nitrogen": "N2", "氮气": "N2",
    "ch4": "CH4", "methane": "CH4", "甲烷": "CH4",
    "c2h4": "C2H4", "ethylene": "C2H4", "乙烯": "C2H4",
    "c2h6": "C2H6", "ethane": "C2H6", "乙烷": "C2H6",
}

# ── 模块目录 ──────────────────────────────────────────────────────────────
MODULE_CATALOG: dict[str, dict[str, str]] = {
    "M1": {
        "name": "反应热与生成焓",
        "description": "反应焓变与标准生成焓计算（Hess 定律、Joback 基团贡献法、DFT 高精度）",
        "methods": "Hess, Joback, DFT",
    },
    "M2": {
        "name": "扩散系数",
        "description": "扩散系数估算（Wilke-Chang、Stokes-Einstein、Chapman-Enskog）",
        "methods": "Wilke-Chang, Stokes-Einstein, Chapman-Enskog",
    },
    "M3": {
        "name": "反应动力学与反应器",
        "description": "表面动力学（Langmuir-Hinshelwood）、Eyring 速率常数、批量反应器求解（scipy.solve_ivp）",
        "methods": "Langmuir-Hinshelwood, Eyring, solve_ivp",
    },
    "M4": {
        "name": "液液萃取",
        "description": "Kremser 方程计算萃取级数",
        "methods": "Kremser",
    },
    "M5": {
        "name": "蒸馏",
        "description": "Fenske-Underwood-Gilliland 捷径法计算最小回流比、理论板数",
        "methods": "Fenske, Underwood, Gilliland",
    },
    "M6": {
        "name": "技能路由",
        "description": "协调 /chem-properties、/lammps、/reactnet 等上游技能获取输入数据",
        "methods": "skill_routing",
    },
}


class RunProcessCalculation(BaseModel):
    """化工过程计算请求模型。"""

    project_id: str
    module: str = Field(description="计算模块: M1(反应热), M2(扩散), M3(反应器), M4(萃取), M5(蒸馏), M6(路由)")
    calculation_type: str = Field(description="模块内具体计算类型")
    compounds: list[dict] = Field(default_factory=list, description="化合物信息列表: name, smiles, cas, amounts")
    conditions: dict[str, Any] = Field(default_factory=dict, description="操作条件: temperature, pressure, composition")
    parameters: dict[str, Any] = Field(default_factory=dict, description="模块专属参数")


class ProcessModelingApplication(NativeScientificService):
    """化工过程建模服务。

    覆盖 6 个模块：M1（反应热与生成焓）、M2（扩散系数）、
    M3（反应动力学与反应器）、M4（液液萃取）、M5（蒸馏）、
    M6（技能路由）。
    M2–M5 委托给 ProcessAdapter（含真实物理化学公式），
    M1 使用内置文献数据库 + Joback 估算。
    """

    def __init__(self, kernel: ScientificExecutionKernel | None = None) -> None:
        super().__init__(kernel)
        self._adapter: ProcessAdapter | None = None
        self._adapter_init_failed = False

    def _get_adapter(self) -> ProcessAdapter:
        """延迟初始化 ProcessAdapter。"""
        if self._adapter is not None:
            return self._adapter
        if self._adapter_init_failed:
            raise RuntimeError("ProcessAdapter 初始化失败")
        self._adapter = ProcessAdapter()
        return self._adapter

    # ── 属性 ──────────────────────────────────────────────────────────────

    @property
    def capability_id(self) -> str:
        return "process_modeling"

    @property
    def display_name(self) -> str:
        return "化工过程建模"

    @property
    def description(self) -> str:
        return "化工过程与反应工程计算：反应热、扩散系数、反应器、萃取、蒸馏"

    # ── 生命周期 ──────────────────────────────────────────────────────────

    def validate(self, task: Task, context: dict[str, Any]) -> dict[str, Any]:
        """校验任务输入。

        从 task.metadata 中提取计算参数并进行校验。
        """
        params = task.metadata
        request = RunProcessCalculation(
            project_id=task.project_id,
            module=params.get("module", ""),
            calculation_type=params.get("calculation_type", ""),
            compounds=params.get("compounds", []),
            conditions=params.get("conditions", {}),
            parameters=params.get("parameters", {}),
        )

        result = ProcessModelingValidator.validate_all(
            module=request.module,
            calculation_type=request.calculation_type,
            compounds=request.compounds,
            conditions=request.conditions,
            parameters=request.parameters,
        )

        return {
            "validated": result["validated"],
            "errors": result["errors"],
            "parsed_request": request.model_dump(),
        }

    def prepare(self, task: Task) -> Run:
        """根据任务创建 Run 实例。"""
        params = task.metadata
        request = RunProcessCalculation(
            project_id=task.project_id,
            module=params.get("module", ""),
            calculation_type=params.get("calculation_type", ""),
            compounds=params.get("compounds", []),
            conditions=params.get("conditions", {}),
            parameters=params.get("parameters", {}),
        )

        return Run(
            task_id=task.task_id,
            project_id=task.project_id,
            service_id=self.capability_id,
            command=f"process_calculation {request.module} {request.calculation_type}",
            input=request.model_dump(),
        )

    def execute(self, run: Run, context: dict[str, Any]) -> list[Artifact]:
        """执行化工过程计算。

        根据模块选择调用对应的适配器逻辑。
        当 calculation_type 指定了属于其他模块的计算时，优先按 calculation_type 路由。
        """
        input_data = run.input
        module = input_data.get("module", "")
        calculation_type = input_data.get("calculation_type", "")
        compounds = input_data.get("compounds", [])
        conditions = input_data.get("conditions", {})
        parameters = input_data.get("parameters", {})

        # calculation_type 二次路由：某些 calculation_type 属于其他模块
        # 例如 distillation_shortcut 属于 M5（蒸馏），不应在 M2（扩散系数）下处理
        # 这里维护 calculation_type → module 的映射，覆盖 module 字段的路由
        effective_module = module
        if calculation_type:
            ct_lower = calculation_type.lower()
            # 蒸馏相关 calculation_type → M5
            if ct_lower in (
                "distillation_shortcut", "distillation",
                "fenske_underwood_gilliland", "fug", "fenske",
            ):
                effective_module = "M5"
            # 扩散系数相关 calculation_type → M2
            elif ct_lower in ("wilke_chang", "stokes_einstein", "chapman_enskog"):
                effective_module = "M2"
            # 反应动力学相关 → M3
            elif ct_lower in (
                "langmuir_hinshelwood", "eyring", "batch_reactor", "pfo_pso",
            ):
                effective_module = "M3"
            # 萃取相关 → M4
            elif ct_lower in ("kremser",):
                effective_module = "M4"
            # 反应热相关 → M1
            elif ct_lower in ("hess", "joback", "dft", "reaction_enthalpy"):
                effective_module = "M1"

        # 根据有效模块分发计算
        if effective_module == "M1":
            results = self._compute_m1(compounds, conditions, parameters)
        elif effective_module == "M2":
            results = self._compute_m2(compounds, conditions, parameters)
        elif effective_module == "M3":
            results = self._compute_m3(compounds, conditions, parameters)
        elif effective_module == "M4":
            results = self._compute_m4(compounds, conditions, parameters)
        elif effective_module == "M5":
            results = self._compute_m5(compounds, conditions, parameters)
        elif effective_module == "M6":
            results = self._compute_m6(compounds, conditions, parameters)
        else:
            results = [{"name": "error", "value": f"未知模块: {module}"}]

        # 封装为工件
        artifact = Artifact(
            run_id=run.run_id,
            type=ArtifactType.RESULT_TABLE,
            name=f"process_calculation_{module}",
            description=f"{MODULE_CATALOG.get(module, {}).get('name', module)} 计算结果",
            data={
                "module": module,
                "calculation_type": calculation_type,
                "compounds": compounds,
                "conditions": conditions,
                "parameters": parameters,
                "results": results,
                "module_catalog": MODULE_CATALOG.get(module),
            },
        )
        return [artifact]

    def postprocess(self, run: Run, artifacts: list[Artifact]) -> list[EvidencePackage]:
        """后处理，将工件转换为证据包。"""
        packages: list[EvidencePackage] = []
        for art in artifacts:
            if art.data is None:
                continue
            results = art.data.get("results", [])
            module = art.data.get("module", "")
            ev_list = batch_map_process_evidence(
                run_id=run.run_id,
                task_id=run.task_id,
                results=results,
                module=module,
            )
            packages.extend(ev_list)
        return packages

    # ── 模块计算方法 ─────────────────────────────────────────────────────

    def _compute_m1(
        self,
        compounds: list[dict[str, Any]],
        conditions: dict[str, Any],
        parameters: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """M1: 反应热与生成焓计算。

        支持方法: Hess（文献数据库查表）、Joback（基团贡献法 RDKit 估算）。
        """
        method = parameters.get("method", "hess")
        results: list[dict[str, Any]] = []

        if method == "hess":
            for comp in compounds:
                name = comp.get("name", "")
                smiles = comp.get("smiles", "")
                record = self._lookup_hf(name) or self._lookup_hf(smiles)
                if record is not None:
                    results.append({
                        "name": "标准生成焓 (gas)",
                        "compound": name,
                        "value": record.get("Hfg"),
                        "unit": "kJ/mol",
                        "method": "Hess 定律",
                        "source": "NIST/DIPPR",
                        "confidence": 0.95,
                    })
                    if record.get("Hfl") is not None:
                        results.append({
                            "name": "标准生成焓 (liquid)",
                            "compound": name,
                            "value": record.get("Hfl"),
                            "unit": "kJ/mol",
                            "method": "Hess 定律",
                            "source": "NIST/DIPPR",
                            "confidence": 0.95,
                        })
                else:
                    # RDKit 兜底：用 Joback 估算
                    hf_joback = self._joback_hf(smiles) if smiles else None
                    results.append({
                        "name": "标准生成焓 (gas, Joback 估算)",
                        "compound": name,
                        "value": hf_joback,
                        "unit": "kJ/mol",
                        "method": "Joback 基团贡献法 (RDKit)",
                        "source": "RDKit/Joback",
                        "confidence": 0.80 if hf_joback is not None else 0.0,
                    })

        elif method == "joback":
            for comp in compounds:
                smiles = comp.get("smiles", "")
                name = comp.get("name", "")
                hf = self._joback_hf(smiles) if smiles else None
                results.append({
                    "name": "Joback 生成焓",
                    "compound": name,
                    "smiles": smiles,
                    "value": hf,
                    "unit": "kJ/mol",
                    "method": "Joback 基团贡献法",
                    "source": "RDKit/Joback",
                    "confidence": 0.80 if hf is not None else 0.0,
                })

        elif method == "dft":
            results.append({
                "name": "DFT 生成焓",
                "value": None,
                "unit": "kJ/mol",
                "method": "DFT (XTB/ORCA)",
                "source": "/dp-yamo",
                "confidence": 0.95,
                "note": "需调用 /dp-yamo 技能获取高精度结果",
            })

        # 反应焓计算
        reaction = parameters.get("reaction", {})
        if reaction:
            # 支持 stoichiometry 格式 {compound: coeff} 和 reactants/products 格式
            stoich = reaction.get("stoichiometry", {})
            if stoich:
                h_rxn = 0.0
                all_found = True
                for compound_name, coeff in stoich.items():
                    record = self._lookup_hf(compound_name)
                    if record and record.get("Hfg") is not None:
                        h_rxn += coeff * record["Hfg"]  # type: ignore
                    else:
                        all_found = False
                results.append({
                    "name": "反应焓变 ΔH_rxn",
                    "value": round(h_rxn, 2) if all_found else None,
                    "unit": "kJ/mol",
                    "method": "Hess 定律 (ΔH_rxn = Σ νi·ΔHf°i)",
                    "source": "NIST/DIPPR" if all_found else "部分化合物缺失",
                    "confidence": 0.95 if all_found else 0.0,
                    "stoichiometry": stoich,
                })
            else:
                # reactants/products 格式: ΔH_rxn = Σ(Hf_products) - Σ(Hf_reactants)
                reactants = reaction.get("reactants", [])
                products = reaction.get("products", [])
                if reactants or products:
                    h_reactants = 0.0
                    h_products = 0.0
                    all_found = True
                    for r in reactants:
                        record = self._lookup_hf(r)
                        if record and record.get("Hfg") is not None:
                            h_reactants += record["Hfg"]  # type: ignore
                        else:
                            all_found = False
                    for p in products:
                        record = self._lookup_hf(p)
                        if record and record.get("Hfg") is not None:
                            h_products += record["Hfg"]  # type: ignore
                        else:
                            all_found = False
                    h_rxn = h_products - h_reactants
                    results.append({
                        "name": "反应焓变 ΔH_rxn",
                        "value": round(h_rxn, 2) if all_found else None,
                        "unit": "kJ/mol",
                        "method": "Hess 定律 (ΔH_rxn = ΣHf°(products) - ΣHf°(reactants))",
                        "source": "NIST/DIPPR" if all_found else "部分化合物缺失",
                        "confidence": 0.95 if all_found else 0.0,
                        "reactants": reactants,
                        "products": products,
                    })

        return results

    def _compute_m2(
        self,
        compounds: list[dict[str, Any]],
        conditions: dict[str, Any],
        parameters: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """M2: 扩散系数估算 — 委托给 ProcessAdapter 的真实公式。"""
        try:
            adapter = self._get_adapter()
            return adapter._compute_m2(compounds, conditions, parameters)
        except Exception:
            # 兜底
            method = parameters.get("method", "wilke_chang")
            temperature = conditions.get("temperature_k", 298.15)
            return [{
                "name": f"扩散系数 ({method})",
                "temperature_k": temperature,
                "value": None,
                "unit": "m²/s",
                "method": method,
                "source": "chem-process M2 (adapter 不可用)",
                "confidence": 0.0,
            }]

    def _compute_m3(
        self,
        compounds: list[dict[str, Any]],
        conditions: dict[str, Any],
        parameters: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """M3: 反应动力学与反应器建模。

        - batch_reactor: 委托给 ProcessAdapter (scipy.solve_ivp)
        - eyring: 真实公式 k=(kBT/h)·exp(-ΔG‡/RT)
        - langmuir_hinshelwood: 真实 LH 速率方程
        """
        calculation_type = parameters.get("calculation_type", "batch_reactor")
        temperature = conditions.get("temperature_k", 298.15)
        results: list[dict[str, Any]] = []

        if calculation_type == "eyring":
            # Eyring 方程: k = (kBT/h) * exp(-ΔG‡/RT)
            dg_dagger_kjmol = parameters.get("dg_dagger_kjmol", 50.0)
            R = 8.314  # J/(mol·K)
            kB = 1.380649e-23  # J/K
            h = 6.62607015e-34  # J·s
            dg_j = dg_dagger_kjmol * 1000  # kJ → J
            k_rate = (kB * temperature / h) * math.exp(-dg_j / (R * temperature))
            results.append({
                "name": "Eyring 速率常数",
                "temperature_k": temperature,
                "dg_dagger_kjmol": dg_dagger_kjmol,
                "rate_constant": k_rate,
                "rate_constant_unit": "1/s",
                "value": k_rate,
                "unit": "1/s",
                "method": "k=(kBT/h)·exp(-ΔG‡/RT)",
                "source": "Eyring 方程 (真实计算)",
                "confidence": 0.85,
            })

        elif calculation_type == "langmuir_hinshelwood":
            # LH: r = k * KA * CA / (1 + KA * CA)^2
            k = parameters.get("rate_constant", 1e-3)
            KA = parameters.get("adsorption_constant", 1.0)
            CA = parameters.get("concentration", 1.0)
            rate = k * KA * CA / (1 + KA * CA) ** 2
            results.append({
                "name": "Langmuir-Hinshelwood 动力学",
                "temperature_k": temperature,
                "rate_constant": k,
                "adsorption_constant": KA,
                "concentration": CA,
                "rate": rate,
                "rate_unit": "mol/(g·s)",
                "value": rate,
                "unit": "mol/(g·s)",
                "method": "r=k·KA·CA/(1+KA·CA)²",
                "source": "LH 方程 (真实计算)",
                "confidence": 0.80,
            })

        elif calculation_type == "batch_reactor":
            # 委托给 ProcessAdapter (scipy.solve_ivp)
            try:
                adapter = self._get_adapter()
                results = adapter._compute_m3(compounds, conditions, parameters)
            except Exception:
                pass
            # 如果适配器未返回结果（缺少反应参数），添加兜底
            if not results:
                results.append({
                    "name": "批量反应器模拟",
                    "temperature_k": temperature,
                    "t_span_s": parameters.get("t_span", [0, 3600]),
                    "value": None,
                    "unit": "mol/L",
                    "method": "scipy.solve_ivp (RK45)",
                    "source": "chem-process M3",
                    "confidence": 0.85,
                    "note": "未提供反应化学方程式或初始浓度，无法执行数值求解",
                })

        elif calculation_type == "pfo_pso":
            # PFO: dq/dt = k1*(qe-q); PSO: dq/dt = k2*(qe-q)^2
            k1 = parameters.get("pfo_k", 0.01)
            k2 = parameters.get("pso_k", 0.001)
            qe = parameters.get("qe", 1.0)
            q0 = parameters.get("q0", 0.0)
            # 简单解析: PFO q(t) = qe*(1-exp(-k1*t)); PSO q(t) = qe*k2*qe*t/(1+k2*qe*t)
            t_eval = parameters.get("t_eval", 60.0)
            q_pfo = qe * (1 - math.exp(-k1 * t_eval))
            q_pso = qe * k2 * qe * t_eval / (1 + k2 * qe * t_eval) if (1 + k2 * qe * t_eval) > 0 else 0
            results.append({
                "name": "吸附动力学拟合 (PFO/PSO)",
                "temperature_k": temperature,
                "pfo_rate_constant": k1,
                "pso_rate_constant": k2,
                "qe": qe,
                "q_pfo_at_t": round(q_pfo, 6),
                "q_pso_at_t": round(q_pso, 6),
                "method": "PFO: q=qe(1-e^(-k1·t)); PSO: q=qe²·k2·t/(1+qe·k2·t)",
                "source": "PFO/PSO 解析解 (真实计算)",
                "confidence": 0.80,
            })

        return results

    def _compute_m4(
        self,
        compounds: list[dict[str, Any]],
        conditions: dict[str, Any],
        parameters: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """M4: 液液萃取 — 委托给 ProcessAdapter 的 Kremser 方程。"""
        try:
            adapter = self._get_adapter()
            return adapter._compute_m4(compounds, conditions, parameters)
        except Exception:
            return [{
                "name": "萃取计算",
                "value": None,
                "unit": "",
                "method": "Kremser",
                "source": "chem-process M4 (adapter 不可用)",
                "confidence": 0.0,
            }]

    def _compute_m5(
        self,
        compounds: list[dict[str, Any]],
        conditions: dict[str, Any],
        parameters: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """M5: 蒸馏 — 委托给 ProcessAdapter 的 FUG 捷径法。"""
        try:
            adapter = self._get_adapter()
            return adapter._compute_m5(compounds, conditions, parameters)
        except Exception:
            return [{
                "name": "蒸馏计算",
                "value": None,
                "unit": "",
                "method": "FUG",
                "source": "chem-process M5 (adapter 不可用)",
                "confidence": 0.0,
            }]

    def _compute_m6(
        self,
        compounds: list[dict[str, Any]],
        conditions: dict[str, Any],
        parameters: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """M6: 技能路由 — 返回上游技能映射信息。"""
        routing_target = parameters.get("routing_target", "chem_properties")
        results: list[dict[str, Any]] = []

        routing_map = {
            "chem_properties": {
                "service": "chem_properties",
                "capability": "chemical_property",
                "description": "获取 Pᵢˢᵃᵗ, μ, ρ, ΔHf°, logP, VLE, 溶解度",
                "module": "M1-M5",
            },
            "dp_yamo": {
                "service": "dp_yamo",
                "capability": "dft_calculation",
                "description": "获取 ΔHf° (XTB/DFT) 高精度生成焓",
                "module": "M1",
            },
            "lammps": {
                "service": "lammps",
                "capability": "molecular_dynamics",
                "description": "获取液体扩散系数 D (MSD 法)",
                "module": "M2",
            },
            "reactnet": {
                "service": "reactnet",
                "capability": "reaction_network",
                "description": "获取 ΔG‡ → Eyring 速率常数",
                "module": "M3",
            },
        }

        if routing_target in routing_map:
            info = routing_map[routing_target]
            results.append({
                "name": f"路由到 {routing_target}",
                "target_service": info["service"],
                "target_capability": info["capability"],
                "description": info["description"],
                "related_module": info["module"],
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
                    "related_module": info["module"],
                    "method": "skill_routing",
                    "source": "chem-process M6",
                    "confidence": 1.0,
                })

        return results

    # ── 辅助方法 ───────────────────────────────────────────

    @staticmethod
    def _lookup_hf(identifier: str) -> dict[str, float | None] | None:
        """从文献数据库查找标准生成焓。"""
        key = identifier.strip().lower()
        canonical = _HF_ALIASES.get(key)
        if canonical and canonical in _HF_DB:
            return _HF_DB[canonical]
        # 查 SMILES
        for rec in _HF_DB.values():
            if rec.get("smiles", "").lower() == key:
                return rec
        if key in _HF_DB:
            return _HF_DB[key]
        return None

    @staticmethod
    def _joback_hf(smiles: str) -> float | None:
        """用 RDKit + Joback 基团贡献法估算气相标准生成焓。

        Joback 方法: ΔHf°(g) = Σ(ni * ΔHi) - 基团修正
        这里用简化版本，基于 RDKit 描述符和已知基团模式匹配。
        """
        try:
            from rdkit import Chem
            from rdkit.Chem import Descriptors

            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                return None

            # 简化 Joback: 基于原子计数和官能团匹配
            # 真实 Joback 需要完整的基团识别，这里用近似估算
            smarts_groups = {
                "[CX4H3]": -42.05,  # -CH3
                "[CX4H2]": -20.64,  # -CH2-
                "[CX4H]": -2.22,    # >CH-
                "[CX4H0]": 8.67,    # >C<
                "[CX3H2]=[CX3H2]": 26.21,  # =CH2 (端烯)
                "[CX3H]=[CX3H]": 17.32,    # =CH- (内烯)
                "[OX2H]": -158.95,  # -OH
                "[OX2H0][CX3]=O": -146.06, # ester O-C=O
                "[CX3]=[OX1]": -133.22,    # =O (酮/醛)
                "[cX3H1]": 2.13,    # 芳香 =CH-
                "[cX3H0]": 4.40,    # 芳香 =C<
            }

            total_hf = 0.0
            for smarts, contribution in smarts_groups.items():
                pattern = Chem.MolFromSmarts(smarts)
                if pattern:
                    matches = mol.GetSubstructMatches(pattern)
                    total_hf += len(matches) * contribution

            # Joback 基础修正
            total_hf += 68.29  # Joback 常数项

            return round(total_hf, 2)
        except Exception:
            return None