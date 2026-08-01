"""能力契约注册中心 — PostgreSQL 持久化（capability.capability_contracts，SQLAlchemy Engine）。"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone

from sqlalchemy import text

from ..db import get_engine
from .models import CapabilityContract


def _normalize_legacy_version(payload: dict) -> dict:
    """评测修复 P0-003：兼容历史数据中的非 semver 版本号。

    旧种子数据写入过 version='v1' / 'v1.0' 等格式，反序列化时
    CapabilityContract 的 semver 校验会抛 ValidationError 导致
    /capabilities 500。读取路径统一归一化为 semver：
    - 'v1'     → '1.0.0'
    - 'v1.0'   → '1.0.0'
    - 'v1.2.3' → '1.2.3'
    - 其他无法识别的值 → '1.0.0'（兜底，避免读路径崩溃）
    """
    version = payload.get("version")
    if not isinstance(version, str):
        payload["version"] = "1.0.0"
        return payload
    v = version.strip()
    if v.startswith(("v", "V")):
        v = v[1:]
    parts = v.split(".")
    if parts and all(p.isdigit() for p in parts):
        while len(parts) < 3:
            parts.append("0")
        payload["version"] = ".".join(parts[:3])
    else:
        payload["version"] = "1.0.0"
    return payload


class CapabilityRegistry:
    """能力契约注册中心，PostgreSQL 持久化。

    Schema 由 alembic 管理（capability.capability_contracts）。
    """

    # 契约状态缓存 TTL（秒）：状态变更后最多需等待此时间生效
    _CACHE_TTL = 60.0

    def __init__(self, db_path: str | None = None):
        # db_path 保留用于兼容旧调用方，实际连接由 get_engine() 提供
        self.db_path = db_path or ""
        self.engine = get_engine()
        # 状态缓存：capability_id -> (status, risk_level, expires_at)
        self._status_cache: dict[str, tuple[str, str, float]] = {}

    def _init_db(self):  # pragma: no cover - 兼容旧调用
        return

    def save(self, contract: CapabilityContract) -> CapabilityContract:
        """登记或更新契约（upsert）。"""
        existing = self.get(contract.capability_id)
        if existing is not None:
            contract.created_at = existing.created_at
        contract.updated_at = datetime.now(timezone.utc).isoformat()
        with self.engine.begin() as conn:
            conn.execute(
                text("""INSERT INTO capability.capability_contracts
                (capability_id, name, provider, risk_level, status, payload, created_at, updated_at)
                VALUES (:capability_id, :name, :provider, :risk_level, :status,
                        CAST(:payload AS JSONB), :created_at, :updated_at)
                ON CONFLICT (capability_id) DO UPDATE SET
                    name = EXCLUDED.name,
                    provider = EXCLUDED.provider,
                    risk_level = EXCLUDED.risk_level,
                    status = EXCLUDED.status,
                    payload = EXCLUDED.payload,
                    created_at = EXCLUDED.created_at,
                    updated_at = EXCLUDED.updated_at"""),
                {
                    "capability_id": contract.capability_id,
                    "name": contract.name,
                    "provider": contract.provider,
                    "risk_level": contract.risk_level,
                    "status": contract.status,
                    "payload": json.dumps(contract.model_dump(), ensure_ascii=False),
                    "created_at": contract.created_at,
                    "updated_at": contract.updated_at,
                },
            )
        # 失效状态缓存，确保变更立即对运行时门禁生效
        self._status_cache.pop(contract.capability_id, None)
        return contract

    def get(self, capability_id: str) -> CapabilityContract | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT payload FROM capability.capability_contracts WHERE capability_id = :capability_id"),
                {"capability_id": capability_id},
            ).fetchone()
        if not row:
            return None
        payload = row[0]
        if isinstance(payload, str):
            payload = json.loads(payload) if payload else {}
        return CapabilityContract(**_normalize_legacy_version(payload))

    def list_all(
        self,
        domain: str | None = None,
        risk_level: str | None = None,
        status: str | None = None,
        q: str | None = None,
    ) -> list[CapabilityContract]:
        # 将过滤条件下推到 SQL，减少 Python 侧全量加载
        clauses = []
        params: dict[str, str] = {}
        if risk_level:
            clauses.append("risk_level = :risk_level")
            params["risk_level"] = risk_level
        if status:
            clauses.append("status = :status")
            params["status"] = status
        if q:
            clauses.append("(LOWER(capability_id) LIKE LOWER(:q) OR LOWER(name) LIKE LOWER(:q) OR LOWER(provider) LIKE LOWER(:q) OR LOWER(payload->>'owner') LIKE LOWER(:q))")
            params["q"] = f"%{q}%"
        where_sql = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = f"SELECT payload FROM capability.capability_contracts{where_sql} ORDER BY created_at DESC"
        with self.engine.connect() as conn:
            rows = conn.execute(text(sql), params).fetchall()
        contracts = []
        for r in rows:
            payload = r[0]
            if isinstance(payload, str):
                payload = json.loads(payload) if payload else {}
            contracts.append(CapabilityContract(**_normalize_legacy_version(payload)))
        # domain 过滤需要检查 JSON 数组，仍在 Python 侧处理
        if domain:
            contracts = [c for c in contracts if domain in c.supported_domains]
        return contracts

    def delete(self, capability_id: str) -> bool:
        with self.engine.begin() as conn:
            cur = conn.execute(
                text("DELETE FROM capability.capability_contracts WHERE capability_id = :capability_id"),
                {"capability_id": capability_id},
            )
        self._status_cache.pop(capability_id, None)
        return cur.rowcount > 0

    def get_status(self, capability_id: str) -> tuple[str, str] | None:
        """获取契约状态与风险等级（带 TTL 缓存）。

        返回 (status, risk_level) 或 None（契约不存在）。
        """
        now = time.monotonic()
        cached = self._status_cache.get(capability_id)
        if cached is not None:
            status, risk_level, expires_at = cached
            if now < expires_at:
                return status, risk_level
        # 缓存未命中或过期：从 DB 查询（仅读 payload 中的 status/risk_level，避免反序列化全量）
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT status, risk_level FROM capability.capability_contracts WHERE capability_id = :capability_id"),
                {"capability_id": capability_id},
            ).fetchone()
        if row is None:
            self._status_cache.pop(capability_id, None)
            return None
        status, risk_level = row[0], row[1]
        self._status_cache[capability_id] = (status, risk_level, now + self._CACHE_TTL)
        return status, risk_level

    def is_callable(self, capability_id: str) -> tuple[bool, str]:
        """判断契约是否可被运行时调用（门禁核心）。

        返回 (callable, reason)：
        - 契约不存在 → (True, "no_contract")：未登记契约不强制门禁，向后兼容
        - status=deprecated → (False, "deprecated")
        - status=pending_approval 且 risk_level=high → (False, "pending_high_risk")
        - 其他 → (True, "active"/"pending_low_risk")
        """
        status_risk = self.get_status(capability_id)
        if status_risk is None:
            return True, "no_contract"
        status, risk_level = status_risk
        if status == "deprecated":
            return False, "deprecated"
        if status == "pending_approval" and risk_level == "high":
            return False, "pending_high_risk"
        return True, status

    def invalidate_cache(self, capability_id: str | None = None) -> None:
        """手动失效缓存。capability_id 为 None 时清空全部。"""
        if capability_id is None:
            self._status_cache.clear()
        else:
            self._status_cache.pop(capability_id, None)

    def get_fallback_chain(self, capability_id: str) -> list[CapabilityContract]:
        """解析回退链（含起点契约），防循环，忽略未登记的引用。

        注意：回退链中已 deprecated 的契约仍会被返回（用于展示）；
        运行时调用方应自行用 is_callable() 过滤。
        """
        chain: list[CapabilityContract] = []
        visited: set[str] = set()
        queue = [capability_id]
        while queue:
            cid = queue.pop(0)
            if cid in visited:
                continue
            visited.add(cid)
            contract = self.get(cid)
            if contract is None:
                continue
            chain.append(contract)
            queue.extend(contract.fallback_chain)
        return chain

    def find_callable_fallback(self, capability_id: str) -> tuple[str | None, str]:
        """从 capability_id 的回退链中找到第一个可调用的契约。

        返回 (fallback_capability_id, reason)：
        - 起点契约本身可调用 → (capability_id, "primary_callable")
        - 起点不可调用，找到可调用 fallback → (fallback_id, "fallback:<原 capability_id>")
        - 整条链都不可调用 → (None, "no_callable_fallback")
        """
        callable_flag, _ = self.is_callable(capability_id)
        if callable_flag:
            return capability_id, "primary_callable"
        for contract in self.get_fallback_chain(capability_id):
            if contract.capability_id == capability_id:
                continue
            ok, _ = self.is_callable(contract.capability_id)
            if ok:
                return contract.capability_id, f"fallback:{capability_id}"
        return None, "no_callable_fallback"

    def seed_builtin(self) -> None:
        """预置系统内建能力契约，幂等（ON CONFLICT DO NOTHING）。"""
        with self.engine.begin() as conn:
            for contract in _builtin_contracts():
                conn.execute(
                    text("""INSERT INTO capability.capability_contracts
                    (capability_id, name, provider, risk_level, status, payload, created_at, updated_at)
                    VALUES (:capability_id, :name, :provider, :risk_level, :status,
                            CAST(:payload AS JSONB), :created_at, :updated_at)
                    ON CONFLICT (capability_id) DO NOTHING"""),
                    {
                        "capability_id": contract.capability_id,
                        "name": contract.name,
                        "provider": contract.provider,
                        "risk_level": contract.risk_level,
                        "status": contract.status,
                        "payload": json.dumps(contract.model_dump(), ensure_ascii=False),
                        "created_at": contract.created_at,
                        "updated_at": contract.updated_at,
                    },
                )


def _builtin_contracts() -> list[CapabilityContract]:
    """系统已有能力的内建契约清单。"""
    return [
        CapabilityContract(
            capability_id="crystal_property_prediction_v1",
            name="晶体性质预测",
            provider="local/m3gnet",
            version="1.0.0",
            input_schema={"structure": "CIF/POSCAR 晶体结构", "properties": "目标性质列表"},
            output_schema={"predictions": "性质名到数值/区间的映射", "uncertainty": "逐性质不确定度"},
            supported_domains=["无机晶体", "正极材料", "固态电解质"],
            limitations=["不支持缺陷态精确预测", "对强关联电子体系（如含 3d 过渡金属）误差偏大", "温度依赖性质仅供趋势参考"],
            uncertainty_method="集成方差 + 校准曲线缩放",
            ood_method="基于描述子距离检测，OOD 时仅供初筛并提示降级",
            cost_model={"unit": "次", "compute_seconds": 30},
            latency_sla="P95 < 60s",
            risk_level="medium",
            fallback_chain=["heuristic_baseline_v1"],
            validation_dataset="crystal_golden_set",
            owner="材料预测组",
            license="内部",
            status="active",
            source="auto",
        ),
        CapabilityContract(
            capability_id="polymer_property_prediction_v1",
            name="聚合物性质预测",
            provider="local/polymer-gnn",
            version="1.0.0",
            input_schema={"polymer_smiles": "重复单元 SMILES", "properties": "目标性质列表"},
            output_schema={"predictions": "性质名到数值的映射", "uncertainty": "逐性质不确定度"},
            supported_domains=["聚合物电解质", "粘结剂", "隔膜涂层"],
            limitations=["共聚物序列信息不参与建模", "不预测长期老化行为", "交联体系精度有限"],
            uncertainty_method="深度集成标准差",
            ood_method="指纹相似度阈值，OOD 时仅供初筛",
            cost_model={"unit": "次", "compute_seconds": 20},
            latency_sla="P95 < 45s",
            risk_level="medium",
            fallback_chain=["heuristic_baseline_v1"],
            validation_dataset="polymer_holdout_v1",
            owner="材料预测组",
            license="内部",
            status="active",
            source="auto",
        ),
        CapabilityContract(
            capability_id="crystal_candidate_generation_v1",
            name="晶体候选生成",
            provider="local/gen-model",
            version="1.0.0",
            input_schema={"constraints": "元素/化学计量/对称性约束", "n_candidates": "生成数量"},
            output_schema={"candidates": "候选结构列表（CIF）", "scores": "生成置信度"},
            supported_domains=["无机晶体", "正极材料"],
            limitations=["不保证热力学稳定性，须经性质预测与 DFT 复核", "对罕见氧化态组合覆盖不足"],
            uncertainty_method="生成置信度打分，不做严格校准",
            ood_method="约束外的化学空间直接拒绝生成",
            cost_model={"unit": "次", "compute_seconds": 120},
            latency_sla="P95 < 300s",
            risk_level="medium",
            fallback_chain=["heuristic_baseline_v1"],
            validation_dataset="candidate_ranking_set",
            owner="材料生成组",
            license="内部",
            status="active",
            source="auto",
        ),
        CapabilityContract(
            capability_id="polymer_candidate_generation_v1",
            name="聚合物候选生成",
            provider="local/gen-model",
            version="1.0.0",
            input_schema={"constraints": "官能团/分子量/性能目标约束", "n_candidates": "生成数量"},
            output_schema={"candidates": "重复单元 SMILES 列表", "scores": "生成置信度"},
            supported_domains=["聚合物电解质", "粘结剂"],
            limitations=["不评估可合成性，须经逆合成或人工复核", "嵌段/接枝拓扑表达有限"],
            uncertainty_method="生成置信度打分，不做严格校准",
            ood_method="约束外的化学空间直接拒绝生成",
            cost_model={"unit": "次", "compute_seconds": 90},
            latency_sla="P95 < 240s",
            risk_level="medium",
            fallback_chain=["heuristic_baseline_v1"],
            validation_dataset="candidate_ranking_set",
            owner="材料生成组",
            license="内部",
            status="active",
            source="auto",
        ),
        CapabilityContract(
            capability_id="synthesis_planning_askcos_v1",
            name="逆合成规划",
            provider="askcos",
            version="1.0.0",
            input_schema={"target": "目标分子/材料标识", "max_depth": "逆合成深度"},
            output_schema={"routes": "合成路线列表", "scores": "路线评分"},
            supported_domains=["有机小分子", "聚合物单体"],
            limitations=["无机固态合成路径覆盖弱", "路线可行性依赖文献命中率", "外部服务，结果须人工审核后方可下单"],
            uncertainty_method="路线评分排序，不提供统计校准",
            ood_method="无可行路线时返回空并标记未覆盖",
            cost_model={"unit": "次", "external_api": True},
            latency_sla="P95 < 120s（依赖外部服务）",
            risk_level="high",
            fallback_chain=["literature_researcher_v1", "heuristic_baseline_v1"],
            validation_dataset="synthesis_route_review_v1",
            owner="合成规划组",
            license="外部服务协议",
            status="active",
            source="auto",
        ),
        CapabilityContract(
            capability_id="dft_verification_v1",
            name="DFT 验证",
            provider="scp/vasp",
            version="1.0.0",
            input_schema={"structure": "晶体结构", "calc_type": "计算类型（relax/static）"},
            output_schema={"energy": "总能量", "forces": "原子力", "converged": "收敛标记"},
            supported_domains=["无机晶体"],
            limitations=["结果依赖泛函选择，不自动校正带隙低估", "不自动校验赝势合理性的极端情形", "计算资源受限，需审批后提交"],
            uncertainty_method="收敛判据检查 + 与同族体系交叉比对",
            ood_method="超出现有验证集覆盖的体系需人工确认参数",
            cost_model={"unit": "核时", "cluster": "scp"},
            latency_sla="单任务排队 + 计算通常 < 24h",
            risk_level="high",
            fallback_chain=["crystal_property_prediction_v1"],
            validation_dataset="dft_benchmark_set_v1",
            owner="计算验证组",
            license="VASP 商业许可",
            status="active",
            source="auto",
        ),
        CapabilityContract(
            capability_id="ecml_closed_loop_v1",
            name="ECML 闭环引擎",
            provider="local/ecml",
            version="1.0.0",
            input_schema={"objective": "优化目标", "budget": "迭代预算"},
            output_schema={"next_experiments": "推荐实验列表", "loop_state": "闭环状态"},
            supported_domains=["实验闭环优化", "候选筛选"],
            limitations=["推荐质量依赖上游预测模型的适用域", "不自动执行高危实验，需审批"],
            uncertainty_method="采集函数显式权衡探索/利用",
            ood_method="上游模型标记 OOD 时降级为随机/基线采样",
            cost_model={"unit": "迭代轮次"},
            latency_sla="单轮决策 P95 < 5min",
            risk_level="high",
            fallback_chain=["committee_assessment_v1"],
            validation_dataset="ecml_replay_set_v1",
            owner="闭环研发组",
            license="内部",
            status="active",
            source="auto",
        ),
        CapabilityContract(
            capability_id="literature_researcher_v1",
            name="文献调研智能体",
            provider="local/llm",
            version="1.0.0",
            input_schema={"query": "调研问题", "filters": "时间/期刊过滤"},
            output_schema={"summary": "调研综述", "references": "文献引用列表"},
            supported_domains=["电池材料文献", "专利情报"],
            limitations=["可能产生幻觉引用，引用须人工核验", "付费墙文献仅基于摘要"],
            uncertainty_method="多源交叉验证，标注置信等级",
            ood_method="检索命中不足时明确声明证据缺口",
            cost_model={"unit": "token", "llm": "internlm"},
            latency_sla="P95 < 180s",
            risk_level="medium",
            fallback_chain=["heuristic_baseline_v1"],
            validation_dataset="literature_qa_set_v1",
            owner="智能体组",
            license="内部",
            status="active",
            source="auto",
        ),
        CapabilityContract(
            capability_id="experiment_analyst_v1",
            name="实验分析智能体",
            provider="local/llm",
            version="1.0.0",
            input_schema={"experiment_data": "结构化实验数据", "context": "实验目的"},
            output_schema={"analysis": "偏差与归因分析", "suggestions": "后续建议"},
            supported_domains=["电化学测试", "材料表征数据"],
            limitations=["不替代统计显著性检验", "对仪器故障类异常需人工确认"],
            uncertainty_method="结论附带证据强度标注",
            ood_method="数据模式偏离已知分布时降级为描述性统计",
            cost_model={"unit": "token", "llm": "internlm"},
            latency_sla="P95 < 120s",
            risk_level="medium",
            fallback_chain=["heuristic_baseline_v1"],
            validation_dataset="experiment_deviation_set",
            owner="智能体组",
            license="内部",
            status="active",
            source="auto",
        ),
        CapabilityContract(
            capability_id="committee_assessment_v1",
            name="委员会评估",
            provider="local/committee",
            version="1.0.0",
            input_schema={"candidate": "候选材料/方案", "evidence": "上下游证据包"},
            output_schema={"scorecard": "多维评分卡", "verdict": "评估结论"},
            supported_domains=["候选评审", "立项决策"],
            limitations=["评分依赖输入证据完整性", "结论为辅助意见，最终决策权在人工"],
            uncertainty_method="多角色评分分歧显式呈现",
            ood_method="证据不足时输出无法评估而非强行打分",
            cost_model={"unit": "次", "llm": "internlm"},
            latency_sla="P95 < 300s",
            risk_level="medium",
            fallback_chain=["heuristic_baseline_v1"],
            validation_dataset="committee_review_set_v1",
            owner="智能体组",
            license="内部",
            status="active",
            source="auto",
        ),
        CapabilityContract(
            capability_id="cross_scale_prediction_v1",
            name="跨尺度预测",
            provider="local/cross-scale",
            version="1.0.0",
            input_schema={"material": "材料标识", "scale_path": "原子到电芯的尺度链"},
            output_schema={"cell_metrics": "电芯级指标预测", "propagation": "尺度传递明细"},
            supported_domains=["原子-材料-电芯跨尺度"],
            limitations=["误差随尺度传递累积", "界面副反应建模简化", "仅供趋势比较，不作绝对值承诺"],
            uncertainty_method="逐尺度不确定度传播",
            ood_method="任一尺度输入 OOD 时整条链降级并提示",
            cost_model={"unit": "次", "compute_seconds": 300},
            latency_sla="P95 < 600s",
            risk_level="high",
            fallback_chain=["crystal_property_prediction_v1", "heuristic_baseline_v1"],
            validation_dataset="cross_scale_benchmark_v1",
            owner="材料预测组",
            license="内部",
            status="active",
            source="auto",
        ),
        CapabilityContract(
            capability_id="heuristic_baseline_v1",
            name="启发式基线",
            provider="local/rules",
            version="1.0.0",
            input_schema={"query": "材料/性质查询"},
            output_schema={"estimate": "经验规则估计值", "note": "规则说明"},
            supported_domains=["无机晶体", "聚合物", "通用初筛"],
            limitations=["仅基于经验规则与查表，精度有限", "不提供不确定度量化", "仅作降级兜底与初筛参考"],
            uncertainty_method="无，结果标注为基线参考",
            ood_method="不适用，规则命中即返回，未命中返回空",
            cost_model={"unit": "次", "compute_seconds": 1},
            latency_sla="P95 < 2s",
            risk_level="low",
            fallback_chain=[],
            validation_dataset="heuristic_smoke_set_v1",
            owner="平台组",
            license="内部",
            status="active",
            source="auto",
        ),
        CapabilityContract(
            capability_id="deep_research_v1",
            name="深度科研智能体",
            provider="scp/intern-agent",
            version="1.0.0",
            input_schema={"query": "复杂科研问题", "context": "研究背景与约束"},
            output_schema={"report": "结构化科研报告", "subtasks": "拆解的子任务列表", "references": "引用来源"},
            supported_domains=["跨学科科研", "综述生成", "候选材料深度评估"],
            limitations=[
                "依赖远端 InternAgent 服务可用性，存在网络抖动风险",
                "生成内容可能产生幻觉引用，关键结论须人工核验",
                "单次调用耗时较长，不适合同步阻塞场景",
            ],
            uncertainty_method="结构化知识流交叉验证，标注证据强度",
            ood_method="研究问题超出工具覆盖范围时降级为文献检索",
            cost_model={"unit": "次", "external_api": True, "compute_seconds": 180},
            latency_sla="P95 < 300s（依赖外部服务）",
            risk_level="medium",
            fallback_chain=["literature_researcher_v1", "heuristic_baseline_v1"],
            validation_dataset="deep_research_review_v1",
            owner="智能体组",
            license="外部服务协议",
            status="active",
            source="auto",
        ),
    ]
