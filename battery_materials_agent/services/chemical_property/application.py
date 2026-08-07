"""化学性质查询服务 — 适配 NativeScientificService 的生命周期。

数据来源（单一事实源）：
- ChemicalsAdapter（thermo/chemicals 库）：DIPPR/Perry's/NIST 标准物性常数（数千种化合物）
  — VLE/闪蒸使用 PR 状态方程计算 K 值（非理想溶液）
  — 蒸气压使用 chemicals 库 Antoine 关联式
- 内置文献物性库：8 种常见化合物的兜底数据（当 chemicals 库未命中时）
- RDKit 实时计算（分子量、logP）作为最终兜底
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
from ...infrastructure.executors.chemicals_adapter import ChemicalsAdapter
from ..base_service import NativeScientificService
from .evidence_mapper import batch_map_chemical_evidence
from .validators import ChemicalPropertyValidator

# ── 文献物性库 ─────────────────────────────────────────────
# 数值来源：DIPPR 801 / Perry's Chemical Engineers' Handbook / NIST Webbook
# Antoine 系数：log10(P_mmHg) = A - B / (C + T_Celsius)
_COMPOUND_DB: dict[str, dict[str, Any]] = {
    "water": {
        "smiles": "O", "cas": "7732-18-5",
        "MW": 18.015, "Tb": 373.15, "Tm": 273.15,
        "Tc": 647.10, "Pc": 22.064e6, "Vc": 5.594e-5, "omega": 0.344,
        "antoine": {"A": 8.07131, "B": 1730.63, "C": 233.426, "Tmin": 1.0, "Tmax": 100.0},
        "logP": -0.65, "solubility_water": float("inf"),
    },
    "ethanol": {
        "smiles": "CCO", "cas": "64-17-5",
        "MW": 46.069, "Tb": 351.44, "Tm": 159.05,
        "Tc": 514.0, "Pc": 6.137e6, "Vc": 1.671e-4, "omega": 0.644,
        "antoine": {"A": 8.20417, "B": 1642.89, "C": 230.300, "Tmin": -57.0, "Tmax": 80.0},
        "logP": -0.14, "solubility_water": float("inf"),
    },
    "methanol": {
        "smiles": "CO", "cas": "67-56-1",
        "MW": 32.042, "Tb": 337.70, "Tm": 175.50,
        "Tc": 512.60, "Pc": 8.095e6, "Vc": 1.180e-4, "omega": 0.565,
        "antoine": {"A": 8.08097, "B": 1582.271, "C": 239.726, "Tmin": -14.0, "Tmax": 65.0},
        "logP": -0.74, "solubility_water": float("inf"),
    },
    "benzene": {
        "smiles": "c1ccccc1", "cas": "71-43-2",
        "MW": 78.114, "Tb": 353.25, "Tm": 278.65,
        "Tc": 562.20, "Pc": 4.898e6, "Vc": 2.560e-4, "omega": 0.212,
        "antoine": {"A": 6.90565, "B": 1211.033, "C": 220.790, "Tmin": 8.0, "Tmax": 80.0},
        "logP": 2.03, "solubility_water": 1.79,
    },
    "toluene": {
        "smiles": "Cc1ccccc1", "cas": "108-88-3",
        "MW": 92.140, "Tb": 383.78, "Tm": 178.00,
        "Tc": 591.80, "Pc": 4.106e6, "Vc": 3.160e-4, "omega": 0.257,
        "antoine": {"A": 6.95464, "B": 1344.800, "C": 219.482, "Tmin": 6.0, "Tmax": 137.0},
        "logP": 2.73, "solubility_water": 0.53,
    },
    "acetone": {
        "smiles": "CC(=O)C", "cas": "67-64-1",
        "MW": 58.080, "Tb": 329.24, "Tm": 178.50,
        "Tc": 508.10, "Pc": 4.700e6, "Vc": 3.070e-4, "omega": 0.307,
        "antoine": {"A": 7.13224, "B": 1219.970, "C": 230.653, "Tmin": -13.0, "Tmax": 55.0},
        "logP": -0.04, "solubility_water": float("inf"),
    },
    "hexane": {
        "smiles": "CCCCCC", "cas": "110-54-3",
        "MW": 86.177, "Tb": 341.88, "Tm": 177.80,
        "Tc": 507.60, "Pc": 3.025e6, "Vc": 3.710e-4, "omega": 0.301,
        "antoine": {"A": 6.87787, "B": 1171.530, "C": 224.366, "Tmin": -2.0, "Tmax": 69.0},
        "logP": 3.90, "solubility_water": 0.0095,
    },
    "octane": {
        "smiles": "CCCCCCCC", "cas": "111-65-9",
        "MW": 114.232, "Tb": 398.83, "Tm": 216.35,
        "Tc": 568.70, "Pc": 2.490e6, "Vc": 4.920e-4, "omega": 0.399,
        "antoine": {"A": 6.91868, "B": 1351.990, "C": 209.155, "Tmin": 19.0, "Tmax": 152.0},
        "logP": 5.18, "solubility_water": 0.00066,
    },
}

# 名称别名 → 规范名
_NAME_ALIASES: dict[str, str] = {
    "h2o": "water", "water": "water", "水": "water",
    "ethanol": "ethanol", "ethyl alcohol": "ethanol", "乙醇": "ethanol", "c2h5oh": "ethanol",
    "methanol": "methanol", "methyl alcohol": "methanol", "甲醇": "methanol", "ch3oh": "methanol",
    "benzene": "benzene", "c6h6": "benzene", "苯": "benzene",
    "toluene": "toluene", "methylbenzene": "toluene", "甲苯": "toluene",
    "acetone": "acetone", "propanone": "acetone", "丙酮": "acetone",
    "hexane": "hexane", "n-hexane": "hexane", "己烷": "hexane",
    "octane": "octane", "n-octane": "octane", "辛烷": "octane",
}

# ── 模块目录 ──────────────────────────────────────────────────────────────
MODULE_CATALOG: dict[str, dict[str, str]] = {
    "M1": {
        "name": "标准常数",
        "description": "查询化合物的标准物性常数，如分子量、沸点、熔点、临界参数等",
        "sources": "DIPPR, Perry's, PubChem",
    },
    "M2": {
        "name": "T/P 依赖性质",
        "description": "查询随温度/压力变化的性质，如蒸气压、密度、粘度、热容等",
        "sources": "DIPPR, NIST, thermo 模型",
        "params": "temperature_k, pressure_pa",
    },
    "M3": {
        "name": "气液平衡 (VLE)",
        "description": "查询二元/多元体系的气液平衡数据，含活度系数、相组成等",
        "sources": "DIPPR, NIST TDE, thermo 模型",
        "params": "composition, temperature_k",
    },
    "M4": {
        "name": "闪蒸计算",
        "description": "对给定组成、温度和压力进行闪蒸计算，输出汽化分率、相组成",
        "sources": "thermo 模型, SRK/PR 状态方程",
        "params": "composition, temperature_k, pressure_pa",
    },
    "M5": {
        "name": "溶解度",
        "description": "查询化合物在指定溶剂中的溶解度数据",
        "sources": "PubChem, Stenutz, Perry's",
    },
}


class QueryChemicalProperty(BaseModel):
    """化学性质查询请求模型。"""

    project_id: str
    compound_name: str = Field(description="化合物名称、SMILES 或 CAS 号")
    module: str = Field(description="查询模块: M1(标准常数), M2(T/P依赖), M3(VLE), M4(闪蒸), M5(溶解度)")
    temperature_k: float | None = Field(default=None, description="温度 (K)，M2/M4 需要")
    pressure_pa: float | None = Field(default=None, description="压力 (Pa)，M2/M4 需要")
    composition: list[float] | None = Field(default=None, description="摩尔分数列表，M3/M4 需要")
    property_keys: list[str] | None = Field(default=None, description="要查询的特定性质列表，为空时查询全部")


class ChemicalPropertyApplication(NativeScientificService):
    """化学性质查询服务。

    覆盖 5 个模块：M1（标准常数）、M2（T/P 依赖性质）、M3（VLE）、
    M4（闪蒸）、M5（溶解度）。
    单一事实源为 ChemicalsAdapter（thermo/chemicals 库），
    内置文献库仅在库未命中时兜底。
    """

    def __init__(self, kernel: ScientificExecutionKernel | None = None) -> None:
        super().__init__(kernel)
        self._adapter = ChemicalsAdapter()

    # ── 模块目录 ──────────────────────────────────────────────────────────

    @property
    def capability_id(self) -> str:
        return "chem_properties"

    @property
    def display_name(self) -> str:
        return "化学性质查询"

    @property
    def description(self) -> str:
        return "查询化合物标准常数、T/P 依赖性质、VLE、闪蒸和溶解度"

    # ── 生命周期 ──────────────────────────────────────────────────────────

    def validate(self, task: Task, context: dict[str, Any]) -> dict[str, Any]:
        """校验任务输入。

        从 task.metadata 中提取查询参数并进行校验。
        """
        params = task.metadata
        query = QueryChemicalProperty(
            project_id=task.project_id,
            compound_name=params.get("compound_name", ""),
            module=params.get("module", ""),
            temperature_k=params.get("temperature_k"),
            pressure_pa=params.get("pressure_pa"),
            composition=params.get("composition"),
            property_keys=params.get("property_keys"),
        )

        result = ChemicalPropertyValidator.validate_all(
            compound_name=query.compound_name,
            module=query.module,
            temperature_k=query.temperature_k,
            pressure_pa=query.pressure_pa,
            composition=query.composition,
        )

        return {
            "validated": result["validated"],
            "errors": result["errors"],
            "parsed_query": query.model_dump(),
        }

    def prepare(self, task: Task) -> Run:
        """根据任务创建 Run 实例。"""
        params = task.metadata
        query = QueryChemicalProperty(
            project_id=task.project_id,
            compound_name=params.get("compound_name", ""),
            module=params.get("module", ""),
            temperature_k=params.get("temperature_k"),
            pressure_pa=params.get("pressure_pa"),
            composition=params.get("composition"),
            property_keys=params.get("property_keys"),
        )

        return Run(
            task_id=task.task_id,
            project_id=task.project_id,
            service_id=self.capability_id,
            command=f"query_chemical_property {query.module} {query.compound_name}",
            input=query.model_dump(),
        )

    def execute(self, run: Run, context: dict[str, Any]) -> list[Artifact]:
        """执行化学性质查询。

        根据模块选择调用对应的适配器逻辑。
        当前实现为模拟查询，后续可对接 DIPPR/thermo/chemicals 等实际数据源。
        """
        input_data = run.input
        module = input_data.get("module", "")
        compound_name = input_data.get("compound_name", "")

        # 根据模块分发查询
        if module == "M1":
            results = self._query_m1(compound_name, input_data.get("property_keys"))
        elif module == "M2":
            results = self._query_m2(
                compound_name,
                temperature_k=input_data.get("temperature_k"),
                pressure_pa=input_data.get("pressure_pa"),
                property_keys=input_data.get("property_keys"),
            )
        elif module == "M3":
            results = self._query_m3(
                compound_name,
                composition=input_data.get("composition"),
                temperature_k=input_data.get("temperature_k"),
                property_keys=input_data.get("property_keys"),
            )
        elif module == "M4":
            results = self._query_m4(
                compound_name,
                composition=input_data.get("composition"),
                temperature_k=input_data.get("temperature_k"),
                pressure_pa=input_data.get("pressure_pa"),
                property_keys=input_data.get("property_keys"),
            )
        elif module == "M5":
            results = self._query_m5(compound_name, input_data.get("property_keys"))
        else:
            results = [{"property_name": "error", "value": f"未知模块: {module}"}]

        # 封装为工件
        artifact = Artifact(
            run_id=run.run_id,
            type=ArtifactType.RESULT_TABLE,
            name=f"chemical_properties_{module}",
            description=f"{compound_name} {MODULE_CATALOG.get(module, {}).get('name', module)} 查询结果",
            data={
                "module": module,
                "compound_name": compound_name,
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
            ev_list = batch_map_chemical_evidence(
                run_id=run.run_id,
                task_id=run.task_id,
                results=results,
            )
            packages.extend(ev_list)
        return packages

    # ── 模块查询方法 ─────────────────────────────────────────────────────

    def _query_m1(
        self,
        compound_name: str,
        property_keys: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """M1: 查询标准常数。

        优先委托 ChemicalsAdapter（thermo/chemicals 库，覆盖数千种化合物）；
        库未命中时回退到内置文献库；最终用 RDKit 计算分子量。
        """
        # 第一优先：ChemicalsAdapter（真实库查询）
        constants = property_keys or ["分子量", "沸点", "熔点", "临界温度", "临界压力", "临界体积", "偏心因子"]
        adapter_result = self._adapter.execute({
            "module": "M1",
            "identifier": compound_name,
            "constants": constants,
        })
        results = adapter_result.get("results", {})

        all_props: list[dict[str, Any]] = []
        if results and "error" not in results:
            # chemicals 库命中
            prop_units = {
                "分子量": "g/mol", "沸点": "K", "熔点": "K",
                "临界温度": "K", "临界压力": "Pa", "临界体积": "m³/mol", "偏心因子": "",
            }
            for const_name in constants:
                val = results.get(const_name)
                if val is not None:
                    all_props.append({
                        "property_name": const_name,
                        "value": val,
                        "unit": prop_units.get(const_name, ""),
                        "source": "chemicals/DIPPR",
                        "confidence": 0.99,
                    })

        # 第二优先：内置文献库兜底（库未命中或部分缺失）
        if not all_props:
            record = self._resolve_compound(compound_name)
            if record is not None:
                all_props = [
                    {"property_name": "分子量", "value": record["MW"], "unit": "g/mol", "source": "DIPPR(内置)", "confidence": 0.95},
                    {"property_name": "沸点", "value": record["Tb"], "unit": "K", "source": "DIPPR(内置)", "confidence": 0.90},
                    {"property_name": "熔点", "value": record["Tm"], "unit": "K", "source": "DIPPR(内置)", "confidence": 0.85},
                    {"property_name": "临界温度", "value": record["Tc"], "unit": "K", "source": "DIPPR(内置)", "confidence": 0.85},
                    {"property_name": "临界压力", "value": record["Pc"], "unit": "Pa", "source": "DIPPR(内置)", "confidence": 0.85},
                    {"property_name": "临界体积", "value": record["Vc"], "unit": "m³/mol", "source": "DIPPR(内置)", "confidence": 0.80},
                    {"property_name": "偏心因子", "value": record["omega"], "unit": "", "source": "DIPPR(内置)", "confidence": 0.85},
                ]
            else:
                # 最终兜底：RDKit 分子量
                mw = self._rdkit_mw(compound_name)
                all_props = [
                    {"property_name": "分子量", "value": mw, "unit": "g/mol",
                     "source": "RDKit" if mw is not None else "N/A",
                     "confidence": 0.95 if mw is not None else 0.0},
                ]
        return self._filter_properties(all_props, property_keys)

    def _query_m2(
        self,
        compound_name: str,
        temperature_k: float | None = None,
        pressure_pa: float | None = None,
        property_keys: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """M2: 查询 T/P 依赖性质。

        优先委托 ChemicalsAdapter 使用 chemicals 库 Antoine 关联式计算蒸气压；
        库未命中时回退到内置 Antoine 系数。
        """
        T = temperature_k or 298.15

        # 第一优先：ChemicalsAdapter（chemicals 库 Antoine 关联式）
        adapter_result = self._adapter.execute({
            "module": "M2",
            "identifier": compound_name,
            "temperature": T,
            "pressure": pressure_pa or 101325.0,
            "properties": ["蒸气压"],
        })
        results = adapter_result.get("results", {})
        psat = results.get("蒸气压") if results and "error" not in results else None

        source = "chemicals/Antoine"
        confidence = 0.95

        # 第二优先：内置文献库 Antoine 兜底
        if psat is None:
            record = self._resolve_compound(compound_name)
            if record is not None and "antoine" in record:
                ant = record["antoine"]
                T_celsius = T - 273.15
                if ant["Tmin"] <= T_celsius <= ant["Tmax"]:
                    log_p_mmhg = ant["A"] - ant["B"] / (ant["C"] + T_celsius)
                    psat = (10 ** log_p_mmhg) * 133.322  # mmHg → Pa
                    source = "Antoine/NIST(内置)"
                    confidence = 0.90

        all_props: list[dict[str, Any]] = [
            {"property_name": "蒸气压", "value": psat, "unit": "Pa",
             "source": source if psat is not None else "N/A",
             "confidence": confidence if psat is not None else 0.0},
            {"property_name": "温度", "value": T, "unit": "K", "source": "input", "confidence": 1.0},
            {"property_name": "压力", "value": pressure_pa or 101325.0, "unit": "Pa", "source": "input", "confidence": 1.0},
        ]
        return self._filter_properties(all_props, property_keys)

    def _query_m3(
        self,
        compound_name: str,
        composition: list[float] | None = None,
        temperature_k: float | None = None,
        property_keys: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """M3: 气液平衡 (VLE) 计算。

        优先委托 ChemicalsAdapter 使用 PR 状态方程计算 K 值（非理想溶液）；
        库未命中时回退到内置文献库 + Raoult 定律（理想溶液）。
        compound_name 格式："A/B" 表示二元混合物。
        """
        parts = [p.strip() for p in compound_name.split("/") if p.strip()]
        if len(parts) < 2 or not composition or temperature_k is None:
            missing = []
            if len(parts) < 2:
                missing.append(
                    f'compound_name 需为 "A/B" 格式（如 "ethanol/water"），当前为 "{compound_name}"'
                )
            if not composition:
                missing.append("composition（摩尔分数列表）")
            if temperature_k is None:
                missing.append("temperature_k（温度）")
            return [{
                "property_name": "error",
                "value": "M3 VLE 缺少必要输入: " + "；".join(missing),
                "unit": "",
                "source": "validator",
                "confidence": 1.0,
                "expected_format": 'compound_name="ethanol/water", composition=[0.5,0.5], temperature_k=351',
            }]

        T = float(temperature_k)
        P_total = 101325.0  # 默认 1 atm

        # 第一优先：ChemicalsAdapter（PR-EOS K 值）
        adapter_result = self._adapter.execute({
            "module": "M3",
            "mixture": parts,
            "composition": list(composition),
            "temperature": T,
            "pressure": P_total,
        })
        results = adapter_result.get("results", {})

        if results and "error" not in results and "K_values" in results:
            K_values = results.get("K_values", [])
            y_comp = results.get("气相组成")
            alpha = results.get("相对挥发度")
            all_props = [
                {"property_name": "活度系数", "value": 1.0, "unit": "", "source": "PR-EOS(ideal γ)", "confidence": 0.85},
                {"property_name": "气相组成", "value": y_comp, "unit": "mol/mol", "source": "PR-EOS", "confidence": 0.90},
                {"property_name": "液相组成", "value": list(composition), "unit": "mol/mol", "source": "input", "confidence": 1.0},
                {"property_name": "相对挥发度", "value": alpha, "unit": "", "source": "PR-EOS", "confidence": 0.88},
                {"property_name": "K值", "value": K_values, "unit": "", "source": "PR-EOS", "confidence": 0.88},
            ]
            # 补充蒸气压（若适配器内部计算了）
            return self._filter_properties(all_props, property_keys)

        # 第二优先：内置文献库 + Raoult 定律兜底
        rec_a = self._resolve_compound(parts[0])
        rec_b = self._resolve_compound(parts[1])
        if rec_a is None or rec_b is None:
            missing = parts[0] if rec_a is None else parts[1]
            return [{"property_name": "error", "value": f"化合物 '{missing}' 不在物性库中", "unit": "", "source": "db", "confidence": 1.0}]

        psat_a = self._antoine_psat(rec_a, T)
        psat_b = self._antoine_psat(rec_b, T)

        if psat_a is None or psat_b is None:
            return [{"property_name": "error", "value": "温度超出 Antoine 适用范围", "unit": "", "source": "Antoine", "confidence": 1.0}]

        x_a, x_b = composition[0], composition[1]
        # Raoult 定律（理想溶液，活度系数 = 1）
        y_a = x_a * psat_a / P_total
        y_b = x_b * psat_b / P_total
        # 相对挥发度 α_AB = (y_A/x_A) / (y_B/x_B) = P_sat_A / P_sat_B
        alpha = psat_a / psat_b if psat_b > 0 else None

        all_props = [
            {"property_name": "活度系数", "value": 1.0, "unit": "", "source": "Raoult(ideal)", "confidence": 0.80},
            {"property_name": "气相组成", "value": [y_a, y_b], "unit": "mol/mol", "source": "Raoult", "confidence": 0.85},
            {"property_name": "液相组成", "value": [x_a, x_b], "unit": "mol/mol", "source": "input", "confidence": 1.0},
            {"property_name": "相对挥发度", "value": alpha, "unit": "", "source": "Raoult", "confidence": 0.85},
            {"property_name": "蒸气压_A", "value": psat_a, "unit": "Pa", "source": "Antoine", "confidence": 0.92},
            {"property_name": "蒸气压_B", "value": psat_b, "unit": "Pa", "source": "Antoine", "confidence": 0.92},
        ]
        return self._filter_properties(all_props, property_keys)

    def _query_m4(
        self,
        compound_name: str,
        composition: list[float] | None = None,
        temperature_k: float | None = None,
        pressure_pa: float | None = None,
        property_keys: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """M4: 等温闪蒸计算。

        优先委托 ChemicalsAdapter 使用 Rachford-Rice + PR-EOS K 值求解；
        库未命中时回退到内置文献库 + Antoine/Raoult K 值。
        """
        parts = [p.strip() for p in compound_name.split("/") if p.strip()]
        if len(parts) < 2 or not composition or temperature_k is None or pressure_pa is None:
            return [{"property_name": "error", "value": "M4 需要混合物名称、组成、温度和压力", "unit": "", "source": "validator", "confidence": 1.0}]

        T = float(temperature_k)
        P = float(pressure_pa)

        # 第一优先：ChemicalsAdapter（Rachford-Rice + PR-EOS K 值）
        adapter_result = self._adapter.execute({
            "module": "M4",
            "mixture": parts,
            "composition": list(composition),
            "temperature": T,
            "pressure": P,
        })
        results = adapter_result.get("results", {})

        if results and "error" not in results and "汽化分率" in results:
            V = results.get("汽化分率")
            y_comp = results.get("气相组成")
            x_comp = results.get("液相组成")
            K_values = results.get("K值")
            all_props = [
                {"property_name": "汽化分率", "value": V, "unit": "", "source": "Rachford-Rice + PR-EOS", "confidence": 0.90},
                {"property_name": "气相组成", "value": y_comp, "unit": "mol/mol", "source": "PR-EOS", "confidence": 0.88},
                {"property_name": "液相组成", "value": x_comp, "unit": "mol/mol", "source": "PR-EOS", "confidence": 0.88},
                {"property_name": "K值", "value": K_values, "unit": "", "source": "PR-EOS", "confidence": 0.88},
            ]
            return self._filter_properties(all_props, property_keys)

        # 第二优先：内置文献库 + Antoine/Raoult 兜底
        records = []
        for p in parts:
            rec = self._resolve_compound(p)
            if rec is None:
                return [{"property_name": "error", "value": f"化合物 '{p}' 不在物性库中", "unit": "", "source": "db", "confidence": 1.0}]
            records.append(rec)

        z = composition
        n = len(records)

        # 计算 K 值
        psats = [self._antoine_psat(r, T) for r in records]
        if any(p is None for p in psats):
            return [{"property_name": "error", "value": "温度超出 Antoine 适用范围", "unit": "", "source": "Antoine", "confidence": 1.0}]

        K = [ps / P for ps in psats]  # K_i = P_sat_i / P

        # Rachford-Rice 方程：sum( z_i * (K_i - 1) / (1 + V*(K_i - 1)) ) = 0
        # 用二分法求解 V ∈ [0, 1]
        def rr(V):
            return sum(z[i] * (K[i] - 1) / (1 + V * (K[i] - 1)) for i in range(n))

        # 检查是否有解
        if all(k <= 1 for k in K) or all(k >= 1 for k in K):
            vapor_fraction = 0.0 if all(k <= 1 for k in K) else 1.0
        else:
            lo, hi = 0.0, 1.0
            for _ in range(100):
                mid = (lo + hi) / 2
                val = rr(mid)
                if abs(val) < 1e-10:
                    lo = hi = mid
                    break
                if val > 0:
                    lo = mid
                else:
                    hi = mid
            vapor_fraction = (lo + hi) / 2

        V = vapor_fraction
        # 液相组成 x_i = z_i / (1 + V*(K_i - 1))
        x = [z[i] / (1 + V * (K[i] - 1)) for i in range(n)]
        # 气相组成 y_i = K_i * x_i
        y = [K[i] * x[i] for i in range(n)]

        all_props = [
            {"property_name": "汽化分率", "value": V, "unit": "", "source": "Rachford-Rice", "confidence": 0.85},
            {"property_name": "气相组成", "value": y, "unit": "mol/mol", "source": "Raoult", "confidence": 0.80},
            {"property_name": "液相组成", "value": x, "unit": "mol/mol", "source": "Raoult", "confidence": 0.80},
            {"property_name": "K值", "value": K, "unit": "", "source": "Antoine/Raoult", "confidence": 0.82},
        ]
        return self._filter_properties(all_props, property_keys)

    def _query_m5(
        self,
        compound_name: str,
        property_keys: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """M5: 查询溶解度数据。

        优先委托 ChemicalsAdapter 使用 GSE (Yalkowsky) 估算水中溶解度；
        库未命中时回退到内置文献库；最终用 RDKit 兜底计算 logP。
        compound_name 格式："solute/solvent" 或单化合物（默认水溶剂）。
        """
        # 解析 "solute/solvent" 格式
        parts = [p.strip() for p in compound_name.split("/") if p.strip()]
        solute = parts[0] if parts else compound_name
        solvent = parts[1] if len(parts) > 1 else "water"

        # 第一优先：ChemicalsAdapter（GSE/Yalkowsky）
        adapter_result = self._adapter.execute({
            "module": "M5",
            "solute": solute,
            "solvent": solvent,
            "temperature": 298.15,
        })
        results = adapter_result.get("results", {})

        if results and "error" not in results and ("水中溶解度" in results or "logS" in results):
            sol = results.get("水中溶解度")
            logp = results.get("logP")
            log_s = results.get("logS")
            mw = results.get("MW")
            method = results.get("method", "GSE(Yalkowsky)")
            all_props = [
                {"property_name": "水中溶解度", "value": sol, "unit": "g/L", "source": method, "confidence": 0.88},
                {"property_name": "logP", "value": logp, "unit": "", "source": "RDKit/Crippen", "confidence": 0.88},
                {"property_name": "logS", "value": log_s, "unit": "", "source": method, "confidence": 0.85},
                {"property_name": "分子量", "value": mw, "unit": "g/mol", "source": "RDKit", "confidence": 0.95},
            ]
            return self._filter_properties(all_props, property_keys)

        # 第二优先：内置文献库
        record = self._resolve_compound(solute)
        if record is not None:
            logp = record.get("logP")
            sol = record.get("solubility_water")
            all_props = [
                {"property_name": "水中溶解度", "value": sol, "unit": "g/L", "source": "PubChem/Perry's", "confidence": 0.90},
                {"property_name": "logP", "value": logp, "unit": "", "source": "PubChem", "confidence": 0.88},
            ]
            return self._filter_properties(all_props, property_keys)

        # 第三优先：RDKit 兜底
        logp = self._rdkit_logp(solute)
        all_props = [
            {"property_name": "水中溶解度", "value": None, "unit": "g/L", "source": "N/A", "confidence": 0.0},
            {"property_name": "logP", "value": logp, "unit": "",
             "source": "RDKit/Crippen" if logp is not None else "N/A",
             "confidence": 0.80 if logp is not None else 0.0},
        ]
        return self._filter_properties(all_props, property_keys)

    # ── 工具方法 ──────────────────────────────────────────────────────────

    @staticmethod
    def _resolve_compound(identifier: str) -> dict[str, Any] | None:
        """根据名称/SMILES/CAS 查找文献库记录。"""
        key = identifier.strip().lower()
        # 先查别名
        canonical = _NAME_ALIASES.get(key)
        if canonical and canonical in _COMPOUND_DB:
            return _COMPOUND_DB[canonical]
        # 再查 SMILES
        for rec in _COMPOUND_DB.values():
            if rec.get("smiles", "").lower() == key:
                return rec
        # 再查 CAS
        for rec in _COMPOUND_DB.values():
            if rec.get("cas", "").lower() == key:
                return rec
        # 最后查规范名
        if key in _COMPOUND_DB:
            return _COMPOUND_DB[key]
        return None

    @staticmethod
    def _antoine_psat(record: dict[str, Any], T_k: float) -> float | None:
        """用 Antoine 方程计算温度 T_k (K) 下的饱和蒸气压 (Pa)。"""
        ant = record.get("antoine")
        if not ant:
            return None
        T_c = T_k - 273.15
        if T_c < ant["Tmin"] or T_c > ant["Tmax"]:
            return None
        log_p_mmhg = ant["A"] - ant["B"] / (ant["C"] + T_c)
        return (10 ** log_p_mmhg) * 133.322  # mmHg → Pa

    @staticmethod
    def _rdkit_mw(smiles_or_name: str) -> float | None:
        """用 RDKit 计算分子量。"""
        try:
            from rdkit import Chem
            from rdkit.Chem import Descriptors
            mol = Chem.MolFromSmiles(smiles_or_name)
            if mol is None:
                return None
            return round(Descriptors.MolWt(mol), 3)
        except Exception:
            return None

    @staticmethod
    def _rdkit_logp(smiles_or_name: str) -> float | None:
        """用 RDKit Crippen 方法计算 logP。"""
        try:
            from rdkit import Chem
            from rdkit.Chem import Crippen
            mol = Chem.MolFromSmiles(smiles_or_name)
            if mol is None:
                return None
            return round(Crippen.MolLogP(mol), 2)
        except Exception:
            return None

    @staticmethod
    def _filter_properties(
        all_props: list[dict[str, Any]],
        property_keys: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """按 property_keys 过滤性质列表。"""
        if not property_keys:
            return all_props
        key_set = set(property_keys)
        return [p for p in all_props if p["property_name"] in key_set]