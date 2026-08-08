"""Main Battery Materials Agent - entry point for the ECML closed-loop system."""

from __future__ import annotations
import logging
from .config import AgentConfig, get_config
from .router.router import MaterialRouter, MaterialInput, RouterResult
from .representation.crystal import CrystalRepresentation
from .representation.polymer import PolymerRepresentation
from .prediction.crystal_property_predictor import CrystalPropertyPredictor
from .prediction.polymer_property_predictor import PolymerPropertyPredictor
from .generation.crystal_candidate_generator import CrystalCandidateGenerator
from .generation.polymer_candidate_generator import PolymerCandidateGenerator
from .synthesis.synthesis_planner import SynthesisPlanner
from .verification.dft_verifier import DFTVerifier
from .experiment.experiment_controller import ExperimentController
from .experiment.approval import ApprovalEngine
from .middleware.data_middleware import DataMiddleware
from .ecml.ecml_engine import ECMLEngine, ECMLState
from .industrialization.raw_material_db import RawMaterialDB
from .industrialization.formula_agent import FormulaAgent
from .industrialization.compliance_checker import ComplianceAndCostNode
from .industrialization.feasibility import IndustrialFeasibilityScreening
from .mcp_tools.tools import MCPToolRegistry
from .experiment.candidate_store import CandidateStore
from sqlalchemy import text

logger = logging.getLogger(__name__)


# ============================================================
# P2-4：加工成本明细 + EHS 合规字段细化
# ============================================================

# 设备折旧费率（元/h，按设备名称关键词匹配，取行业典型台时费）
_DEPRECIATION_RATE_PER_H = {
    "搅拌": 80.0,
    "混料": 80.0,
    "涂布": 120.0,
    "烘": 50.0,
    "干燥": 50.0,
    "烧结": 150.0,
    "辊压": 90.0,
}
_DEFAULT_DEPRECIATION_RATE = 100.0  # 未识别设备的默认台时费（元/h）
_ELECTRICITY_PRICE_PER_KWH = 0.8    # 工业电价（元/kWh）
_LABOR_RATE_PER_H = 60.0            # 单操作员人工费率（元/h）


def _depreciation_rate_for(equipment: str) -> float:
    """按设备名称关键词匹配折旧台时费，未命中返回默认值。"""
    for kw, rate in _DEPRECIATION_RATE_PER_H.items():
        if kw in (equipment or ""):
            return rate
    return _DEFAULT_DEPRECIATION_RATE


def _estimate_step_power_kw(temp_c) -> float:
    """按工艺温度估算设备功率：室温基准 5kW，每升高 1°C 增加 0.1kW。"""
    try:
        t = float(temp_c)
    except (TypeError, ValueError):
        t = 25.0
    return 5.0 + max(0.0, t - 25.0) * 0.1


# 常见电池溶剂闪点（°C，文献典型值，用于 EHS 危险特性展示）
_SOLVENT_FLASH_POINTS = {
    "DMC": "18", "DEC": "25", "EMC": "23", "EC": "143", "PC": "132",
    "碳酸二甲酯": "18", "碳酸二乙酯": "25", "碳酸甲乙酯": "23",
}


def _build_hazard_profile(spec) -> dict:
    """基于物料规格库字段生成 EHS 危险特性档案（P2-4）。

    数据来源说明：
    - reach_status / ghs_classification：来自物料库 reach_compliant / is_toxic 字段
    - flash_point：仅对已知溶剂给出文献典型值，其余如实标注"未测定"
    - sds_link：物料库暂无 SDS 字段，前置兼容 sds_uri 属性，无则留空
    """
    is_toxic = bool(getattr(spec, "is_toxic", False))
    reach_ok = bool(getattr(spec, "reach_compliant", False))
    ghs = "急性毒性 类别3 (H301)" if is_toxic else "未分类为危险品"
    name = f"{getattr(spec, 'name', '')} {getattr(spec, 'material_id', '')}"
    flash = "未测定"
    for key, fp in _SOLVENT_FLASH_POINTS.items():
        if key in name:
            flash = f"{fp} °C（{key} 典型值）"
            break
    return {
        "material_name": getattr(spec, "name", "") or getattr(spec, "material_id", ""),
        "reach_status": "通过" if reach_ok else "未通过",
        "reach_clause": "REACH (EC) No 1907/2006 Annex XVII 受限物质核查",
        "ghs_classification": ghs,
        "flash_point": flash,
        "reactivity_hazard": "需评估氧化性/水解反应活性" if is_toxic else "无已知反应性危害",
        "sds_link": getattr(spec, "sds_uri", "") or "",
    }


class BatteryMaterialsAgent:
    """Main agent orchestrating the ECML closed-loop battery materials discovery."""

    def __init__(self, config: AgentConfig | None = None):
        self.config = config or get_config()

        self.router = MaterialRouter()
        self.crystal_repr = CrystalRepresentation()
        self.polymer_repr = PolymerRepresentation()
        self.crystal_predictor = CrystalPropertyPredictor()
        self.polymer_predictor = PolymerPropertyPredictor()
        self.crystal_generator = CrystalCandidateGenerator(
            api_key=self.config.materials_project.api_key,
            cache_dir=str(self.config.materials_project.cache_dir),
            gnome_use_mp_mirror=self.config.materials_project.gnome_use_mp_mirror,
            gnome_data_dir=str(self.config.materials_project.gnome_data_dir),
        )
        self.polymer_generator = PolymerCandidateGenerator(config=self.config)
        self.synthesis_planner = SynthesisPlanner(config=self.config)
        self.verifier = DFTVerifier()
        self.experiment_controller = ExperimentController(run_mode=self.config.run_mode.value)
        self.middleware = DataMiddleware(db_path=str(self.config.data_dir / "experiment_data.db"))
        # 候选材料持久化存储：Discovery 和 ECML 两条路径统一写入此 store，
        # 下游 Sample/ExperimentOrder 可通过 candidate_id 反查
        self.candidate_store = CandidateStore()
        self.raw_material_db = RawMaterialDB(db_path=str(self.config.industrialization.db_path))
        self.formula_agent = FormulaAgent(raw_material_db=self.raw_material_db, config=self.config)
        self.compliance_node = ComplianceAndCostNode(raw_material_db=self.raw_material_db, config=self.config.industrialization)
        self.feasibility_screener = IndustrialFeasibilityScreening(
            raw_material_db=self.raw_material_db,
            compliance_node=self.compliance_node,
            config=self.config.industrialization,
        )
        self.approval_engine = ApprovalEngine()
        self.ecml = ECMLEngine(
            router=self.router,
            generator=self.crystal_generator,
            polymer_generator=self.polymer_generator,
            synthesis_planner=self.synthesis_planner,
            predictor=self.crystal_predictor,
            polymer_predictor=self.polymer_predictor,
            verifier=self.verifier,
            experiment_controller=self.experiment_controller,
            middleware=self.middleware,
            candidate_store=self.candidate_store,
            state_store=None,  # 使用默认 SQLite 持久化（见下）
            config=self.config,
            formula_agent=self.formula_agent,
            compliance_node=self.compliance_node,
            feasibility_screener=self.feasibility_screener,
            approval_engine=self.approval_engine,
        )
        self.tools = MCPToolRegistry()
        self._register_tool_handlers()
        # Wire the MCP tool registry into the compliance node so that SCP
        # toxicity calls go through SCPToolProxy → SCPPolicy → SCPAdapter
        # → SCPClientPool → ProvenanceDecorator → AuditStore. Without this,
        # the compliance checker would bypass the security chain.
        self.compliance_node._mcp_tool_registry = self.tools

    def _register_tool_handlers(self):
        self.tools.register(self.tools.get_tool("route_material"), handler=self._handle_route)
        self.tools.register(self.tools.get_tool("generate_crystal_candidates"), handler=self._handle_crystal_gen)
        self.tools.register(self.tools.get_tool("generate_polymer_candidates"), handler=self._handle_polymer_gen)
        self.tools.register(self.tools.get_tool("predict_crystal_properties"), handler=self._handle_crystal_pred)
        self.tools.register(self.tools.get_tool("predict_polymer_properties"), handler=self._handle_polymer_pred)
        self.tools.register(self.tools.get_tool("check_synthesis_feasibility"), handler=self._handle_synthesis)
        self.tools.register(self.tools.get_tool("verify_dft"), handler=self._handle_verify)
        self.tools.register(self.tools.get_tool("get_experiment_results"), handler=self._handle_get_results)
        self.tools.register(self.tools.get_tool("subscribe_experiment_updates"), handler=self._handle_subscribe)
        self.tools.register(self.tools.get_tool("design_formula"), handler=self._handle_design_formula)

    def discover(self, target: str, target_property: str = "ionic_conductivity",
                 max_iterations: int = 3) -> ECMLState:
        return self.ecml.run(target, target_property, max_iterations)

    def discover_crystal(self, elements: list[str], target_property: str = "ionic_conductivity",
                         num_candidates: int = 10, target_properties: list[dict] | None = None,
                         require_elements: list[str] | None = None,
                         exclude_elements: list[str] | None = None) -> dict:
        candidates = self.crystal_generator.generate_candidates(
            target_property=target_property,
            elements=elements,
            num_candidates=num_candidates,
            target_properties=target_properties,
            require_elements=require_elements,
            exclude_elements=exclude_elements,
        )
        # 回填离子电导率预测值：MP API 不返回该字段，默认值为 0，
        # 用启发式预测器为每个候选估算一次，避免前端展示全 0
        if target_property == "ionic_conductivity":
            for c in candidates:
                if c.ionic_conductivity_estimate == 0.0:
                    try:
                        result = self.crystal_predictor.predict(
                            {"formula": c.formula}, "ionic_conductivity",
                        )
                        c.ionic_conductivity_estimate = result.value
                    except Exception as e:
                        logger.debug("ionic_conductivity prediction failed formula=%s: %s", c.formula, e)
        # P0-4：把 formula_validator.assess_candidate_quality 提前到 discover_crystal 入口
        # 对每个候选做化学式/SMILES 合法性 + 元素约束校验，剔除 invalid 候选
        from .generation.formula_validator import assess_candidate_quality
        valid_candidates: list = []
        blocked_count = 0
        for c in candidates:
            quality = assess_candidate_quality(
                c.model_dump(),
                require_elements=require_elements,
                exclude_elements=exclude_elements,
            )
            if quality["flag"] == "invalid":
                blocked_count += 1
            else:
                valid_candidates.append(c)
        if blocked_count:
            candidates = valid_candidates
        # P0-4：候选数不足 num_candidates 时加 degraded 标记
        degraded = len(candidates) < num_candidates
        return {
            "candidates": [c.model_dump() for c in candidates],
            "count": len(candidates),
            "degraded": degraded,
            "blocked_count": blocked_count,
        }

    def discover_polymer(self, target_properties: dict | list | None = None,
                         num_candidates: int = 10) -> dict:
        candidates = self.polymer_generator.generate(
            target_properties=target_properties,
            num_candidates=num_candidates,
        )
        return {
            "candidates": [c.model_dump() for c in candidates],
            "count": len(candidates),
        }

    def route(self, material_input: MaterialInput) -> RouterResult:
        return self.router.route(material_input)

    def check_synthesis(self, smiles: str) -> float:
        return self.synthesis_planner.check_feasibility(smiles)

    def verify(self, smiles: str, property_name: str = "total_energy"):
        return self.verifier.verify_single_point(smiles, property_name)

    def query_experiments(
        self,
        formula: str = "",
        experiment_type: str = "",
        project_id: str = "",
        sample_id: str = "",
        batch_id: str = "",
        source_type: str = "",
        operator: str = "",
        order_id: str = "",
        date_from: str = "",
        date_to: str = "",
    ):
        """查询实验数据。

        统一查询 experiment.experiment_result_records 表（关联 experiment_orders 获取
        project_id/candidate_id），支持按样品/批次/类型/来源/操作员/任务单/时间范围等过滤。
        """
        from .middleware.data_middleware import ExperimentRecord
        engine = self.experiment_controller._store.engine
        clauses = [
            "(:formula = '' OR o.candidate_id = :formula)",
            "(:sample_id = '' OR r.sample_id ILIKE :sample_id_like)",
            "(:experiment_type = '' OR r.test_method = :experiment_type)",
            "(:project_id = '' OR o.project_id = :project_id)",
            "(:batch_id = '' OR r.sample_batch_id ILIKE :batch_id_like)",
            "(:source_type = '' OR r.source_type = :source_type)",
            "(:operator = '' OR r.uploaded_by ILIKE :operator_like)",
            "(:order_id = '' OR r.experiment_order_id ILIKE :order_id_like)",
            "(:date_from = '' OR r.uploaded_at >= CAST(:date_from AS timestamptz))",
            "(:date_to = '' OR r.uploaded_at <= CAST(:date_to AS timestamptz))",
        ]
        query = (
            "SELECT r.result_id, r.sample_id, r.sample_batch_id, r.source_type, "
            "r.uploaded_by, r.uploaded_at, r.property_name, r.value, r.unit, "
            "r.test_method, o.order_id, o.project_id, o.candidate_id "
            "FROM experiment.experiment_result_records r "
            "LEFT JOIN experiment.experiment_orders o ON r.experiment_order_id = o.order_id "
            "WHERE " + " AND ".join(clauses) + " ORDER BY r.uploaded_at DESC"
        )
        with engine.connect() as conn:
            rows = conn.execute(
                text(query),
                {
                    "formula": formula or "",
                    "sample_id": sample_id or "",
                    "sample_id_like": f"%{sample_id}%" if sample_id else "",
                    "experiment_type": experiment_type or "",
                    "project_id": project_id or "",
                    "batch_id": batch_id or "",
                    "batch_id_like": f"%{batch_id}%" if batch_id else "",
                    "source_type": source_type or "",
                    "operator": operator or "",
                    "operator_like": f"%{operator}%" if operator else "",
                    "order_id": order_id or "",
                    "order_id_like": f"%{order_id}%" if order_id else "",
                    "date_from": date_from or "",
                    "date_to": date_to or "",
                },
            ).fetchall()
        records = []
        for r in rows:
            ts = r[5]
            if ts is not None and not isinstance(ts, str):
                ts = ts.isoformat()
            records.append(ExperimentRecord(
                record_id=str(r[0]),
                sample_id=r[1] or "",
                formula=r[12] or "",
                experiment_type=r[9] or r[6] or "",
                measured_values={r[6]: r[7]} if r[6] else {},
                units={r[6]: r[8]} if r[6] else {},
                source=r[3] or "unknown",
                timestamp=ts or "",
                batch_id=r[2] or "",
                operator=r[4] or "",
                notes=f"任务单: {r[10]}" if r[10] else "",
                order_id=r[10] or "",
                candidate_id=r[12] or "",
            ))
        return records

    def get_mcp_manifest(self) -> dict:
        return self.tools.to_mcp_manifest()

    def _handle_route(self, material_input):
        if isinstance(material_input, dict):
            material_input = MaterialInput(**material_input)
        return self.route(material_input).model_dump()

    def _handle_crystal_gen(self, elements=None, num_candidates=10):
        return self.discover_crystal(elements or [], num_candidates=num_candidates)

    def _handle_polymer_gen(self, target_properties=None, num_candidates=10):
        return self.discover_polymer(target_properties, num_candidates)

    def _handle_crystal_pred(self, features=None, property_name="band_gap"):
        return self.crystal_predictor.predict(features or {}, property_name).model_dump()

    def _handle_polymer_pred(self, features=None, property_name="ionic_conductivity"):
        return self.polymer_predictor.predict(features or {}, property_name).model_dump()

    def _handle_synthesis(self, smiles=""):
        return {"feasibility_score": self.check_synthesis(smiles)}

    def _handle_verify(self, smiles="", property_name="total_energy"):
        return self.verify(smiles, property_name).model_dump()

    def _handle_get_results(self, formula="", experiment_type=""):
        records = self.query_experiments(formula, experiment_type)
        return {"records": [r.model_dump() for r in records], "count": len(records)}

    def _handle_subscribe(self, callback_url=""):
        # Register a webhook-style subscriber that forwards new experiment records
        # to the provided callback URL via HTTP POST
        import urllib.request
        import json
        def _forwarder(record):
            try:
                data = json.dumps(record.model_dump() if hasattr(record, 'model_dump') else record).encode()
                req = urllib.request.Request(callback_url, data=data, headers={'Content-Type': 'application/json'})
                with urllib.request.urlopen(req, timeout=5) as resp:
                    resp.read()
            except Exception as e:
                logger.warning("Forward to %s failed: %s", callback_url, e)
        if callback_url and self.middleware is not None:
            self.middleware.subscribe(_forwarder)
        return {"subscribed": True, "callback_url": callback_url}

    def _handle_design_formula(self, target_material=None, quantity: float = 1.0,
                               quantity_kg: float | None = None):
        """调用工业化配方智能体生成 BOM/BOP 并评估合规性与成本。

        返回结构对齐前端 FormulaDesign.vue 期望：
        - bom: [{material_id, material_name, cas_number, amount, unit_price, cost, supplier, in_stock}]
        - bop: [{step, equipment, temperature, duration, key_params}]
        - material_cost / process_cost / total_unit_cost
        - ehs: {reach, hazard_class, storage, disposal}
        - is_passed / warnings / fatal_errors
        """
        import asyncio
        # 兼容 MCP 工具调用方传入 quantity_kg（前端 FormulaDesign.vue 与测试用例使用该名称）
        if quantity_kg is not None:
            quantity = quantity_kg
        if target_material is None:
            target_material = {"target_property": "ionic_conductivity"}
        # 兼容字符串形式
        if isinstance(target_material, str):
            target_material = {"candidate": target_material, "target_property": "ionic_conductivity"}

        try:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            if loop is not None:
                # 已在事件循环中（如 FastAPI async 端点调用），不能使用 asyncio.run()
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    recipe = pool.submit(
                        asyncio.run, self.formula_agent.design_recipe(target_material)
                    ).result(timeout=35)
            else:
                recipe = asyncio.run(self.formula_agent.design_recipe(target_material))
            report = self.compliance_node.evaluate(recipe.bom)

            # 转换 BOM dict -> list（对齐前端表格）
            bom_list = []
            material_cost = 0.0
            hazard_profiles = []  # P2-4：逐物料 EHS 危险特性档案
            # BOM 归一化
            bom_items = list(recipe.bom.items())
            values = [v for _, v in bom_items if isinstance(v, (int, float))]
            if values and max(values) > 1.0:
                total_pct = sum(values) or 1.0
                bom_items = [(k, v / total_pct) for k, v in bom_items]

            for mat_id, weight_ratio in bom_items:
                spec = self.raw_material_db.get_spec(mat_id) or self._lookup_material_fuzzy(mat_id)
                amount = weight_ratio * quantity
                if spec:
                    unit_price = spec.unit_cost
                    cost = unit_price * amount
                    material_cost += cost
                    bom_list.append({
                        "material_id": spec.material_id,
                        "material_name": spec.name,
                        "cas_number": "",  # 物料库暂无 CAS 字段，留空
                        "amount": round(amount, 4),
                        "unit_price": unit_price,
                        "cost": round(cost, 2),
                        "supplier": spec.supplier,
                        "in_stock": spec.inventory_quantity >= amount,
                    })
                    hazard_profiles.append(_build_hazard_profile(spec))
                else:
                    bom_list.append({
                        "material_id": mat_id,
                        "material_name": mat_id,
                        "cas_number": "",
                        "amount": round(amount, 4),
                        "unit_price": 0.0,
                        "cost": 0.0,
                        "supplier": "",
                        "in_stock": False,
                    })
                    hazard_profiles.append({
                        "material_name": mat_id,
                        "reach_status": "未知",
                        "reach_clause": "REACH (EC) No 1907/2006 Annex XVII 受限物质核查",
                        "ghs_classification": "未评估（物料不在台账）",
                        "flash_point": "未测定",
                        "reactivity_hazard": "未知",
                        "sds_link": "",
                    })

            # 转换 BOP 字段名（对齐前端）
            bop_list = []
            for step in recipe.bop:
                temp_c = step.get("temperature", 25)
                time_min = step.get("duration_min", 0)
                bop_list.append({
                    "step": step.get("step", ""),
                    "equipment": step.get("equipment", recipe.equipment or ""),
                    "temperature": temp_c,
                    "duration": round(time_min / 60.0, 2) if time_min else 0.0,
                    "key_params": ", ".join(f"{k}={v}" for k, v in step.items()
                                             if k not in ("step", "temperature", "duration_min", "equipment")),
                })

            # 加工成本明细（P2-4）：按工艺步骤拆解设备折旧 / 能耗 / 人工
            process_cost_breakdown = []
            process_cost = 0.0
            for s in bop_list:
                hours = s["duration"] or 0.0
                depreciation = hours * _depreciation_rate_for(s["equipment"])
                energy = hours * _estimate_step_power_kw(s["temperature"]) * _ELECTRICITY_PRICE_PER_KWH
                labor = hours * _LABOR_RATE_PER_H
                subtotal = depreciation + energy + labor
                process_cost += subtotal
                process_cost_breakdown.append({
                    "step": s["step"],
                    "equipment": s["equipment"],
                    "duration_h": round(hours, 2),
                    "duration": round(hours, 2),
                    "depreciation_cost": round(depreciation, 2),
                    "energy_cost": round(energy, 2),
                    "labor_cost": round(labor, 2),
                    "subtotal": round(subtotal, 2),
                })
            total_unit_cost = (material_cost + process_cost) / quantity if quantity > 0 else 0.0

            # EHS 合规
            reach_status = "通过" if report.is_passed else "未通过"
            if any("REACH" in err for err in report.fatal_errors):
                reach_status = "未通过"
            elif any("REACH" in w for w in report.warnings):
                reach_status = "待复核"

            has_toxic = any("毒性" in w for w in report.warnings)
            ehs = {
                "reach": reach_status,
                "hazard_class": "有毒" if has_toxic else "常规",
                "storage": "阴凉干燥处" if has_toxic else "常温存储",
                "disposal": "危废处理" if has_toxic else "通用工业废弃物",
                # P2-4 细化字段：整体 GHS 分类 + 逐物料危险特性档案
                "ghs_classification": "急性毒性 类别3 (H301)" if has_toxic else "未分类为危险品",
                "hazard_profiles": hazard_profiles,
            }

            # P1-2：AI 可信度元信息——置信度由真实信号计算（物料主数据命中率 + 合规通过），
            # 不做无依据的乐观估计；存在警告/未命中物料时必须人工复核
            _matched = sum(
                1 for item in bom_list
                if (item.get("unit_price") or 0) > 0 or item.get("supplier")
            )
            _total = len(bom_list) or 1
            _match_rate = _matched / _total
            _confidence = round(
                min(0.95, 0.4 + 0.4 * _match_rate + (0.15 if report.is_passed else 0.0)), 3
            )
            _human_review = bool(
                (not report.is_passed) or report.warnings or _match_rate < 1.0
            )
            ai_meta = {
                "agent_name": "工业化配方智能体",
                "strategy": "FormulaAgent 配方生成 + 合规检查 + 成本模型",
                "confidence": _confidence,
                "key_assumptions": [
                    "加工成本模型：设备台时费（"
                    + "/".join(f"{k} {v:g}" for k, v in _DEPRECIATION_RATE_PER_H.items())
                    + f" 元/h，未识别设备 {_DEFAULT_DEPRECIATION_RATE:g} 元/h）",
                    f"工业电价 {_ELECTRICITY_PRICE_PER_KWH:g} 元/kWh，单操作员人工费率 {_LABOR_RATE_PER_H:g} 元/h",
                    "BOM 配比已按质量分数归一化",
                ],
                "evidence_sources": [
                    f"原料主数据库（{_matched}/{_total} 种物料命中价格/供应商/库存）",
                    "REACH 合规规则库",
                ],
                "human_review_required": _human_review,
            }

            return {
                "bom": bom_list,
                "bop": bop_list,
                "equipment": recipe.equipment,
                "material_cost": round(material_cost, 2),
                "process_cost": round(process_cost, 2),
                "process_cost_breakdown": process_cost_breakdown,
                "total_unit_cost": round(total_unit_cost, 2),
                "total_cost_per_kg": round(total_unit_cost, 2),
                "ehs": ehs,
                "is_passed": report.is_passed,
                "warnings": report.warnings,
                "fatal_errors": report.fatal_errors,
                "review_required": report.review_required,
                "estimated_unit_cost": report.estimated_unit_cost,
                "ai_meta": ai_meta,
            }
        except Exception as e:
            logger.warning("design_formula failed: %s", e)
            return {"error": str(e)}

    def _lookup_material_fuzzy(self, mat_id: str):
        """容错查找物料：按 material_id → RM-xxx 正则 → 名称模糊匹配。"""
        import re
        spec = self.raw_material_db.get_spec(mat_id)
        if spec is not None:
            return spec
        m = re.search(r"(RM-\w+)", mat_id)
        if m:
            spec = self.raw_material_db.get_spec(m.group(1))
            if spec is not None:
                return spec
        for s in self.raw_material_db.get_all():
            if s.name in mat_id or mat_id in s.name:
                return s
        return None
