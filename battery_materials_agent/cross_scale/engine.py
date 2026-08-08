"""跨尺度建模引擎：分子性质 → 反应过程 → 多物理场串联。

分层执行：
- molecular 层：调用现有性质预测（crystal/polymer predictor）
- reaction 层：调用合成路径规划（synthesis_planner），简化为反应动力学模板
- continuum 层：优先使用真实求解器（LAMMPS 分子/介观、FEniCSx 连续介质），
  求解器不可用时回退到多物理场模板近似（标记 estimate/degraded）
- coupled：汇总各尺度结果，分析耦合关系
"""

from __future__ import annotations

import asyncio
import math

from .solvers import FEniCSxAdapter, LAMMPSAdapter, fenicsx_available, lammps_available


class CrossScaleEngine:
    """跨尺度建模引擎：分子性质 → 反应过程 → 多物理场串联。"""

    # 反应类型 → 模板动力学参数
    REACTION_KINETICS: dict[str, dict] = {
        "esterification": {"Ea": 50.0, "A": 1.0e10, "yield": 0.85, "temperature": 80},
        "grignard": {"Ea": 45.0, "A": 1.0e9, "yield": 0.70, "temperature": 0},
        "suzuki": {"Ea": 60.0, "A": 1.0e11, "yield": 0.90, "temperature": 80},
        "wittig": {"Ea": 55.0, "A": 1.0e10, "yield": 0.75, "temperature": 25},
        "reduction": {"Ea": 40.0, "A": 1.0e9, "yield": 0.90, "temperature": 25},
        "oxidation": {"Ea": 50.0, "A": 1.0e10, "yield": 0.85, "temperature": 50},
        "nucleophilic_sub": {"Ea": 55.0, "A": 1.0e10, "yield": 0.80, "temperature": 50},
        "amide_formation": {"Ea": 45.0, "A": 1.0e10, "yield": 0.88, "temperature": 25},
        "sulfonation": {"Ea": 60.0, "A": 1.0e10, "yield": 0.70, "temperature": 60},
        "phosphorylation": {"Ea": 55.0, "A": 1.0e9, "yield": 0.65, "temperature": 50},
        "retrosynthesis": {"Ea": 50.0, "A": 1.0e10, "yield": 0.75, "temperature": 50},
    }
    DEFAULT_KINETICS = {"Ea": 55.0, "A": 1.0e10, "yield": 0.75, "temperature": 50}

    def __init__(self, agent=None):
        self.agent = agent
        # 真实求解器适配器（惰性创建，探测可用性）
        self._lammps = LAMMPSAdapter()
        self._fenicsx = FEniCSxAdapter()

    def solver_status(self) -> dict:
        """返回各级求解器可用性（供前端展示真实求解 vs 模板降级）。"""
        return {
            "lammps": {"available": self._lammps.available, "engine": "LAMMPS"},
            "fenicsx": {"available": self._fenicsx.available, "engine": "FEniCSx"},
        }

    async def run_cross_scale(self, material: dict, scales: list[str], agent_id: str | None = None) -> dict:
        """跨尺度建模主入口。

        Args:
            material: {type: 'molecule'/'crystal', smiles/formula, ...}
            scales: ['molecular', 'reaction', 'continuum'] 或子集
            agent_id: 指定执行此任务的智能体（须具备 property_prediction 能力）

        Returns:
            {
                molecular: {properties, confidence},
                reaction: {pathway, kinetics, yield},
                continuum: {electrochemical, thermal, mechanical},
                coupled: {summary, correlations}
            }
        """
        result: dict = {}
        if "molecular" in scales:
            result["molecular"] = await self._run_molecular(material)
            # 分子尺度可补充 LAMMPS 热导率/RDF/离子扩散（真实 MD，可用时）
            if lammps_available():
                result["molecular"]["md"] = await asyncio.to_thread(self._run_lammps_tasks, material)
        if "reaction" in scales:
            result["reaction"] = await self._run_reaction(material)
        if "continuum" in scales:
            result["continuum"] = self._run_continuum(material, result.get("molecular"))
            # 连续介质尺度优先 FEniCSx 真实 PDE（可用时）
            if fenicsx_available():
                result["continuum"]["pde"] = await asyncio.to_thread(
                    self._run_fenicsx, material, result.get("molecular")
                )
        result["coupled"] = self._analyze_coupling(result, material, scales)
        result["solvers"] = self.solver_status()
        # 标注执行 agent（若指定）
        if agent_id:
            result["executed_by"] = agent_id
        return result

    # ------------------------------------------------------------------
    # 分子尺度
    # ------------------------------------------------------------------

    async def _run_molecular(self, material: dict) -> dict:
        mat_type = material.get("type", "crystal")
        formula = material.get("formula", "")
        smiles = material.get("smiles", "")
        features = {"formula": formula, "smiles": smiles}

        if mat_type == "crystal":
            predictor = self.agent.crystal_predictor if self.agent else None
            prop_names = list(predictor.PREDICTABLE_PROPERTIES) if predictor else [
                "band_gap", "formation_energy", "ionic_conductivity",
                "bulk_modulus", "shear_modulus", "e_above_hull",
            ]
        else:
            predictor = self.agent.polymer_predictor if self.agent else None
            prop_names = list(predictor.PREDICTABLE_PROPERTIES) if predictor else [
                "ionic_conductivity", "glass_transition_temp", "dielectric_constant",
                "elastic_modulus", "thermal_conductivity", "decomposition_temp",
                "total_energy", "formation_energy",
            ]

        if predictor is None:
            return {"estimate": True, "properties": [], "properties_by_name": {}, "confidence": 0.0,
                    "material_type": mat_type, "error": "predictor unavailable"}

        properties: list[dict] = []
        props_by_name: dict = {}
        for name in prop_names:
            try:
                r = await asyncio.to_thread(predictor.predict, features, name)
                entry = {
                    "name": name,
                    "value": float(r.value),
                    "unit": r.unit,
                    "confidence": float(r.confidence),
                    "model": r.model,
                }
            except Exception as e:
                entry = {"name": name, "value": None, "unit": "", "confidence": 0.0,
                         "model": "", "error": str(e)}
            properties.append(entry)
            props_by_name[name] = entry

        confidences = [p["confidence"] for p in properties if p.get("confidence", 0) > 0]
        avg_conf = round(sum(confidences) / len(confidences), 4) if confidences else 0.0
        return {
            "estimate": False,
            "properties": properties,
            "properties_by_name": props_by_name,
            "confidence": avg_conf,
            "material_type": mat_type,
        }

    def _run_lammps_tasks(self, material: dict) -> dict:
        """运行 LAMMPS 分子动力学任务（热导率/RDF/离子扩散），真实可用时执行。"""
        # 这些任务较重（MD 仿真），放线程池避免阻塞事件循环
        results = {}
        for task in ("thermal_conductivity", "rdf", "ion_diffusion"):
            try:
                r = self._lammps.run(task, material)
                if r is not None:
                    results[task] = r
            except Exception:  # noqa: BLE001
                continue
        return results

    def _run_fenicsx(self, material: dict, molecular: dict | None) -> dict:
        """运行 FEniCSx 薄片热-电化学耦合 PDE，真实可用时执行。"""
        props = (molecular or {}).get("properties_by_name", {}) if molecular else {}

        def _val(name):
            p = props.get(name)
            if p is None:
                return None
            v = p.get("value")
            return float(v) if v is not None else None

        thermal_cond = _val("thermal_conductivity") or 1.0
        ionic_cond = _val("ionic_conductivity") or 1.0e-4
        formation_e = _val("formation_energy")
        heat_q = max(0.1, abs(formation_e or -2.0) * 0.5)
        r = self._fenicsx.run(
            material,
            thermal_k=thermal_cond,
            ec_conductivity=ionic_cond,
            heat_generation=heat_q,
        )
        return {"estimate": False, "result": r} if r else {"estimate": True, "result": None}

    # ------------------------------------------------------------------
    # 反应尺度
    # ------------------------------------------------------------------

    async def _run_reaction(self, material: dict) -> dict:
        smiles = material.get("smiles", "")
        formula = material.get("formula", "")

        if not smiles or self.agent is None:
            return self._template_reaction(formula or smiles, estimate=True)

        try:
            routes = await asyncio.to_thread(
                self.agent.synthesis_planner.plan_synthesis, smiles, 2, 3,
            )
        except Exception:
            try:
                routes = await asyncio.to_thread(
                    self.agent.synthesis_planner._build_local_tree, smiles, 2, 3,
                )
            except Exception:
                routes = []

        if not routes:
            return self._template_reaction(formula or smiles, estimate=True)

        route = routes[0]
        # 本地树返回空步骤时，模板化回退（标记为估算，仅用于展示，不参与评分）
        if not route.steps:
            pathway = {
                "target": smiles,
                "num_steps": 1,
                "steps": [{
                    "description": "标准合成路径",
                    "reactants": [material.get("formula", "")],
                }],
                "feasibility_score": 0.5,
                "confidence": 0.5,
            }
            return {
                "estimate": True,
                "pathway": pathway,
                "kinetics": [self._step_kinetics(0, "retrosynthesis")],
                "yield": 0.5,
            }

        pathway = {
            "target": smiles,
            "num_steps": route.num_steps,
            "steps": [s.model_dump() for s in route.steps],
            "feasibility_score": round(route.feasibility_score, 4),
            "confidence": round(route.confidence, 4),
        }
        kinetics = self._derive_kinetics(route.steps)
        overall_yield = self._compute_yield(route.steps)
        return {
            "estimate": False,
            "pathway": pathway,
            "kinetics": kinetics,
            "yield": overall_yield,
        }

    def _template_reaction(self, identifier: str, estimate: bool = False) -> dict:
        return {
            "estimate": estimate,
            "pathway": {
                "target": identifier,
                "num_steps": 1,
                "steps": [{
                    "reaction_smiles": f"{identifier}>>product",
                    "reactants": [identifier],
                    "products": ["product"],
                    "conditions": "standard conditions",
                    "score": 0.7,
                    "reaction_type": "retrosynthesis",
                }],
                "feasibility_score": 0.7,
                "confidence": 0.6,
            },
            "kinetics": [self._step_kinetics(0, "retrosynthesis")],
            "yield": 0.75,
        }

    def _derive_kinetics(self, steps) -> list[dict]:
        return [self._step_kinetics(i, s.reaction_type) for i, s in enumerate(steps)]

    def _step_kinetics(self, idx: int, rtype: str) -> dict:
        params = self.REACTION_KINETICS.get(rtype, self.DEFAULT_KINETICS)
        R = 8.314  # J/(mol·K)
        T = params["temperature"] + 273.15
        Ea_J = params["Ea"] * 1000.0
        k = params["A"] * math.exp(-Ea_J / (R * T))
        return {
            "step": idx + 1,
            "reaction_type": rtype,
            "activation_energy": params["Ea"],
            "pre_exponential_factor": params["A"],
            "rate_constant": k,
            "temperature_kelvin": round(T, 2),
            "step_yield": params["yield"],
        }

    def _compute_yield(self, steps) -> float:
        if not steps:
            return 0.0
        overall = 1.0
        for step in steps:
            params = self.REACTION_KINETICS.get(step.reaction_type, self.DEFAULT_KINETICS)
            overall *= params["yield"]
        return round(overall, 4)

    # ------------------------------------------------------------------
    # 连续介质尺度（多物理场模板）
    # ------------------------------------------------------------------

    def _run_continuum(self, material: dict, molecular: dict | None) -> dict:
        """连续介质尺度（模板化多物理场近似）。

        ⚠️ 物理近似：以下公式均为工程简化模板，仅用于横向对比与展示，
        不可用于定量决策（勿作为设计依据或上报结论）。
        """
        props = (molecular or {}).get("properties_by_name", {}) if molecular else {}

        def _val(name):
            p = props.get(name)
            if p is None:
                return None
            v = p.get("value")
            return float(v) if v is not None else None

        # 电化学（模板化，从分子尺度属性推导；近似 - 勿用于定量决策）
        band_gap = _val("band_gap")
        ionic_cond = _val("ionic_conductivity")
        formation_e = _val("formation_energy")

        # 近似：电压 ≈ 带隙/2（物理量级估算，非真实电化学窗口）
        voltage = min(5.0, max(1.0, (band_gap or 3.0) / 2.0))
        # 近似：容量经验式（150 + |形成能|*10，单位 mAh/g）
        capacity = 150.0 + abs(formation_e or -2.0) * 10.0
        energy_density = voltage * capacity
        power_density = min(1000.0, max(10.0, (ionic_cond or 1.0e-4) * 1.0e5))

        # 热学（近似 - 勿用于定量决策）
        thermal_cond = _val("thermal_conductivity") or 1.0
        heat_gen = max(0.1, abs(formation_e or -2.0) * 0.5)
        temp_rise = heat_gen / max(0.1, thermal_cond) * 10.0

        # 力学（近似 - 勿用于定量决策）
        bulk_mod = _val("bulk_modulus") or 100.0
        shear_mod = _val("shear_modulus") or 40.0
        elastic_mod = _val("elastic_modulus") or bulk_mod
        formula = material.get("formula", "")
        # 近似：密度由化学式长度启发式估算
        density = 2.0 + (len(formula) % 5) * 0.3

        return {
            "estimate": True,
            "electrochemical": {
                "operating_voltage": round(voltage, 3),
                "theoretical_capacity": round(capacity, 2),
                "energy_density": round(energy_density, 2),
                "power_density": round(power_density, 2),
            },
            "thermal": {
                "thermal_conductivity": round(thermal_cond, 4),
                "heat_generation": round(heat_gen, 4),
                "max_temperature_rise": round(temp_rise, 2),
            },
            "mechanical": {
                "elastic_modulus": round(elastic_mod, 2),
                "bulk_modulus": round(bulk_mod, 2),
                "shear_modulus": round(shear_mod, 2),
                "density": round(density, 2),
            },
        }

    # ------------------------------------------------------------------
    # 耦合分析
    # ------------------------------------------------------------------

    def _analyze_coupling(self, result: dict, material: dict, scales: list[str]) -> dict:
        correlations: list[dict] = []
        mol = result.get("molecular")
        cont = result.get("continuum")
        rxn = result.get("reaction")

        if mol and cont:
            props = mol.get("properties_by_name", {})
            if "ionic_conductivity" in props and props["ionic_conductivity"].get("value") is not None:
                correlations.append({
                    "from_scale": "molecular",
                    "to_scale": "continuum",
                    "property": "ionic_conductivity → power_density",
                    "correlation": "positive",
                    "description": "分子尺度离子电导率提升 → 连续介质尺度功率密度增大",
                })
            if "band_gap" in props and props["band_gap"].get("value") is not None:
                correlations.append({
                    "from_scale": "molecular",
                    "to_scale": "continuum",
                    "property": "band_gap → operating_voltage",
                    "correlation": "positive",
                    "description": "带隙越大 → 工作电压窗口越宽",
                })
            if "formation_energy" in props and props["formation_energy"].get("value") is not None:
                correlations.append({
                    "from_scale": "molecular",
                    "to_scale": "continuum",
                    "property": "formation_energy → thermal_stability",
                    "correlation": "negative",
                    "description": "形成能越负（越稳定）→ 热产率越低、温升越小",
                })

        if rxn and cont:
            correlations.append({
                "from_scale": "reaction",
                "to_scale": "continuum",
                "property": "reaction_yield → manufacturing_feasibility",
                "correlation": "positive",
                "description": f"反应路径产率 {rxn.get('yield', 0)} → 影响连续化制造的可行性",
            })

        if mol and rxn:
            correlations.append({
                "from_scale": "molecular",
                "to_scale": "reaction",
                "property": "molecular_stability → reaction_feasibility",
                "correlation": "positive",
                "description": "分子尺度稳定性影响反应路径评分",
            })

        active = [s for s in scales if s in result]
        summary = (
            f"跨尺度建模完成，串联尺度：{', '.join(active)}。"
            f"共识别 {len(correlations)} 条跨尺度关联。"
        )
        return {"summary": summary, "correlations": correlations}
