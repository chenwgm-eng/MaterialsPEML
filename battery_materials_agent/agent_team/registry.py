"""Agent registry with PostgreSQL persistence for custom agents."""
from __future__ import annotations
import json
import uuid

from sqlalchemy import text

from ..db import get_engine
from ..mdm.reference_dict import ReferenceDictStore
from .models import AgentDefinition, AgentDefinitionV2, AgentRole


# V1 → V2 迁移映射表（参考 V1.2.2 第 5 节）
_V2_MIGRATION_MAP: dict[str, dict] = {
    "builtin_material_discovery": {
        "agent_id": "molecule_polymer_design",
        "role": "thinker",
        "max_autonomy_level": "L1",
        "capabilities": ["molecule_polymer_design", "structure_validation", "property_prediction"],
        "required_capabilities": ["structure_validation"],
        "optional_capabilities": ["material_reference_lookup"],
        "prohibited_actions": ["experiment.start", "dft.submit", "synthesis.execute", "formula.design"],
    },
    "builtin_synthesis_planner": {
        "agent_id": "synthesis_evidence",
        "role": "doer",
        "max_autonomy_level": "L1",
        "capabilities": ["synthesis_evidence", "reaction_engineering_check"],
        "required_capabilities": ["synthesis_evidence"],
        "optional_capabilities": ["chemical_descriptors"],
        "prohibited_actions": ["dft.submit", "compliance.verdict"],
    },
    "builtin_dft_verifier": {
        "agent_id": "dft_execution",
        "role": "doer",
        "max_autonomy_level": "L1",
        "capabilities": ["dft_verification"],
        "required_capabilities": ["dft_verification"],
        "optional_capabilities": [],
        "prohibited_actions": ["compliance.verdict"],
    },
    "builtin_experiment_analyst": {
        "agent_id": "experiment_analyst",
        "role": "analyst",
        "max_autonomy_level": "L1",
        "capabilities": ["experiment_qc_lookup"],
        "required_capabilities": ["experiment_qc_lookup"],
        "optional_capabilities": [],
        "prohibited_actions": ["experiment.start", "dft.submit", "synthesis.execute"],
    },
    "builtin_project_manager": {
        "agent_id": "material_planner",
        "role": "planner",
        "max_autonomy_level": "L1",
        "capabilities": ["material_planning"],
        "required_capabilities": [],
        "optional_capabilities": [],
        "prohibited_actions": ["experiment.start", "dft.submit", "synthesis.execute"],
    },
    "builtin_literature_researcher": {
        "agent_id": "evidence_research",
        "role": "analyst",
        "max_autonomy_level": "L1",
        "capabilities": ["evidence_research", "material_knowledge_query"],
        "required_capabilities": [],
        "optional_capabilities": ["material_reference_lookup", "material_knowledge_query"],
        "prohibited_actions": ["experiment.start", "dft.submit", "synthesis.execute"],
    },
    "builtin_quality_reviewer": {
        "agent_id": "compliance_verifier",
        "role": "verifier",
        "max_autonomy_level": "L2",
        "capabilities": ["compliance_screening", "structure_validation"],
        "required_capabilities": ["structure_validation", "compliance_screening"],
        "optional_capabilities": [],
        "prohibited_actions": ["experiment.start", "dft.submit", "synthesis.execute"],
    },
    "builtin_material_router": {
        "agent_id": "material_planner",
        "role": "planner",
        "max_autonomy_level": "L1",
        "capabilities": ["material_planning"],
        "required_capabilities": [],
        "optional_capabilities": [],
        "prohibited_actions": ["experiment.start", "dft.submit", "synthesis.execute"],
    },
    "builtin_industrialization": {
        "agent_id": "industrialization",
        "role": "doer",
        "max_autonomy_level": "L1",
        "capabilities": ["industrialization", "compliance_screening"],
        "required_capabilities": ["compliance_screening"],
        "optional_capabilities": [],
        "prohibited_actions": ["dft.submit", "compliance.verdict"],
    },
    "builtin_cross_validator": {
        "agent_id": "compliance_verifier",
        "role": "verifier",
        "max_autonomy_level": "L2",
        "capabilities": ["compliance_screening"],
        "required_capabilities": ["compliance_screening"],
        "optional_capabilities": [],
        "prohibited_actions": ["experiment.start", "dft.submit", "synthesis.execute"],
    },
    "builtin_battery_learner": {
        "agent_id": "experiment_analyst",
        "role": "analyst",
        "max_autonomy_level": "L1",
        "capabilities": ["experiment_qc_lookup"],
        "required_capabilities": [],
        "optional_capabilities": [],
        "prohibited_actions": ["experiment.start", "dft.submit", "synthesis.execute"],
    },
    "builtin_battery_interpreter": {
        "agent_id": "evidence_research",
        "role": "analyst",
        "max_autonomy_level": "L0",
        "capabilities": ["evidence_research"],
        "required_capabilities": [],
        "optional_capabilities": [],
        "prohibited_actions": ["experiment.start", "dft.submit", "synthesis.execute"],
    },
    "builtin_battery_oracle": {
        "agent_id": "property_prediction",
        "role": "doer",
        "max_autonomy_level": "L1",
        "capabilities": ["property_prediction"],
        "required_capabilities": ["property_prediction"],
        "optional_capabilities": ["material_reference_lookup"],
        "prohibited_actions": ["dft.submit", "compliance.verdict"],
    },
}


# 角色默认禁止动作（用于未知 agent 兜底）
_DEFAULT_PROHIBITED_BY_ROLE: dict[str, list[str]] = {
    "thinker": ["experiment.start", "dft.submit", "synthesis.execute", "formula.design"],
    "doer": ["dft.submit", "compliance.verdict"],
    "analyst": ["experiment.start", "dft.submit", "synthesis.execute"],
    "planner": ["experiment.start", "dft.submit", "synthesis.execute"],
    "verifier": ["experiment.start", "dft.submit", "synthesis.execute"],
    "reviewer": ["experiment.start", "dft.submit", "synthesis.execute"],
}


class AgentRegistry:
    """Agent 注册表：管理内置 agent 和用户自定义 agent（PostgreSQL 持久化）。"""

    def __init__(self, db_path: str = "data/agent_team.db"):
        # db_path 参数保留以兼容旧调用方，迁移至 PostgreSQL 后已忽略，统一使用全局 Engine。
        self.engine = get_engine()
        self._ref_dict = ReferenceDictStore()
        self._ensure_overrides_table()
        self._builtin_agents = self._apply_builtin_overrides(self._init_builtin_agents())

    def _validate_role(self, role: AgentRole) -> None:
        """校验 agent_role 是否存在于 MDM dimensions (domain='agent_role')。"""
        dim = self._ref_dict.get_dimension(domain="agent_role", code=role.value)
        if dim is None:
            raise ValueError(
                f"Invalid agent_role: {role!r}. "
                "Must exist in mdm.dimensions (domain='agent_role')."
            )

    def _ensure_overrides_table(self) -> None:
        """启动时确保覆盖表存在（未执行 alembic 迁移的环境也能工作）。"""
        try:
            with self.engine.begin() as conn:
                conn.execute(
                    text(
                        """
                        CREATE TABLE IF NOT EXISTS agent_team.builtin_agent_overrides (
                            id           TEXT PRIMARY KEY,
                            data         JSONB NOT NULL,
                            updated_at   TIMESTAMPTZ DEFAULT NOW()
                        )
                        """
                    )
                )
        except Exception:
            # 表已存在或权限不足时忽略，后续读写会再次抛错并被调用方捕获
            pass

    def _load_builtin_overrides(self) -> dict[str, dict]:
        """从 PostgreSQL 加载所有内置 agent 覆盖。"""
        overrides: dict[str, dict] = {}
        try:
            with self.engine.connect() as conn:
                cur = conn.execute(
                    text("SELECT id, data FROM agent_team.builtin_agent_overrides")
                )
                for row in cur.fetchall():
                    data = row[1]
                    if isinstance(data, str):
                        import json as _json
                        try:
                            data = _json.loads(data)
                        except Exception:
                            continue
                    if isinstance(data, dict):
                        overrides[row[0]] = data
        except Exception:
            pass
        return overrides

    def _apply_builtin_overrides(self, agents: list[AgentDefinition]) -> list[AgentDefinition]:
        """将数据库中的覆盖字段合并到内置 agent 上。"""
        overrides = self._load_builtin_overrides()
        if not overrides:
            return agents
        result: list[AgentDefinition] = []
        for a in agents:
            ov = overrides.get(a.id)
            if not ov:
                result.append(a)
                continue
            merged = a.model_dump()
            for key, value in ov.items():
                if key in ("id", "is_builtin"):
                    continue
                merged[key] = value
            result.append(AgentDefinition(**merged))
        return result

    def _init_builtin_agents(self) -> list[AgentDefinition]:
        """返回 8 个内置 agent 定义。"""
        return [
            AgentDefinition(
                id="builtin_material_discovery",
                name="首席材料学家",
                role=AgentRole.MATERIAL_DISCOVERY,
                description="晶体/聚合物材料发现专家，擅长从元素组合与结构空间中筛选高潜力候选材料",
                expertise=["晶体结构预测", "聚合物电解质设计", "材料空间探索", "元素组合优化"],
                tools=["generate_crystal_candidates", "generate_polymer_candidates",
                       "predict_crystal_properties", "predict_polymer_properties"],
                avatar="🔬",
                is_builtin=True,
            ),
            AgentDefinition(
                id="builtin_synthesis_planner",
                name="合成路线规划师",
                role=AgentRole.SYNTHESIS_PLANNING,
                description="合成路径与可行性专家，基于逆合成分析评估候选材料的合成难度与路径",
                expertise=["逆合成分析", "反应路径规划", "合成可行性评估", "ASKCOS 引擎"],
                tools=["check_synthesis_feasibility", "generate_crystal_candidates"],
                avatar="⚗️",
                is_builtin=True,
                llm_model="",
            ),
            AgentDefinition(
                id="builtin_dft_verifier",
                name="DFT 计算专家",
                role=AgentRole.DFT_VERIFICATION,
                description="量子化学验证专家，使用 DFT 方法对候选材料进行高精度性质验证",
                expertise=["密度泛函理论", "量子化学计算", "PySCF/ASE", "能带结构分析"],
                tools=["verify_dft"],
                avatar="🧮",
                is_builtin=True,
                llm_model="",
            ),
            AgentDefinition(
                id="builtin_experiment_analyst",
                name="实验数据分析员",
                role=AgentRole.EXPERIMENT_ANALYSIS,
                description="实验数据查询与统计分析，从湿实验结果中提取关键性能指标",
                expertise=["实验数据统计", "电化学性能分析", "数据可视化", "实验趋势识别"],
                tools=["get_experiment_results", "subscribe_experiment_updates"],
                avatar="📊",
                is_builtin=True,
            ),
            AgentDefinition(
                id="builtin_project_manager",
                name="项目经理",
                role=AgentRole.PROJECT_MANAGER,
                description="任务分解与协调，负责整体研发流程规划与进度跟踪",
                expertise=["项目管理", "任务分解", "风险评估", "资源调度"],
                tools=[],
                avatar="📋",
                is_builtin=True,
                status="active",
            ),
            AgentDefinition(
                id="builtin_literature_researcher",
                name="文献调研员",
                role=AgentRole.LITERATURE_RESEARCH,
                description="基于 LLM 的知识检索与文献综述，提供材料研发的理论依据",
                expertise=["文献检索", "知识图谱", "研发趋势分析", "理论依据梳理"],
                tools=["search_literature", "build_knowledge_graph"],
                avatar="📚",
                is_builtin=True,
                status="active",
                llm_model="",
            ),
            AgentDefinition(
                id="builtin_quality_reviewer",
                name="质量审核员",
                role=AgentRole.QUALITY_REVIEW,
                description="结果合理性检查，对预测与实验结果进行交叉验证与质量把关",
                expertise=["结果验证", "异常检测", "交叉验证", "质量控制"],
                tools=["get_experiment_results", "predict_crystal_properties"],
                avatar="✅",
                is_builtin=True,
            ),
            AgentDefinition(
                id="builtin_material_router",
                name="材料路由调度员",
                role=AgentRole.MATERIAL_DISCOVERY,
                description="晶体/聚合物路由分发，根据输入材料类型自动选择最优处理分支",
                expertise=["材料分类", "路由调度", "流程编排", "输入解析"],
                tools=["route_material"],
                avatar="🧭",
                is_builtin=True,
            ),
            AgentDefinition(
                id="builtin_industrialization",
                name="配方工艺师",
                role=AgentRole.INDUSTRIALIZATION,
                description="工业化落地验证专家，基于企业物料库生成 BOM/BOP 配方，评估合规性与量产成本",
                expertise=["配方设计", "BOM/BOP 工艺规划", "EHS 合规审查", "成本熔断评估"],
                tools=["design_formula"],
                avatar="🏭",
                is_builtin=True,
            ),
            AgentDefinition(
                id="builtin_cross_validator",
                name="交叉验证分析员",
                role=AgentRole.QUALITY_REVIEW,
                description="过程反思机制：对预测与实测偏差异常样本进行模板化原因分析，输出测量误差、模型外推、材料降解等可能原因",
                expertise=["偏差检测", "交叉验证", "异常归因", "过程反思"],
                tools=["detect_prediction_deviation", "mark_anomaly_samples"],
                avatar="🔍",
                is_builtin=True,
                status="active",
            ),
            AgentDefinition(
                id="builtin_battery_learner",
                name="材料数据学习者",
                role=AgentRole.EXPERIMENT_ANALYSIS,
                description="材料数据学习者：从实验/测量数据中拟合性能演变模型，提取起始值与变化率等性能演变模式",
                expertise=["数据演变学习", "性能拟合", "趋势分析", "模式识别"],
                tools=[],
                avatar="🎓",
                is_builtin=True,
                status="active",
            ),
            AgentDefinition(
                id="builtin_battery_interpreter",
                name="材料机理解释者",
                role=AgentRole.CUSTOM,
                description="材料机理解释者：基于数据学习结果分析性能变化的潜在机理，输出主导与次要机理",
                expertise=["机理分析", "结构演变", "活性物质损失", "相变分解"],
                tools=[],
                avatar="🧠",
                is_builtin=True,
                status="active",
            ),
            AgentDefinition(
                id="builtin_battery_oracle",
                name="材料性质预言者",
                role=AgentRole.CUSTOM,
                description="材料性质预言者：基于学习结果外推性能演变，预测未来性能值及置信度",
                expertise=["性质外推预测", "趋势外推", "置信度评估", "性能预测"],
                tools=[],
                avatar="🔮",
                is_builtin=True,
                status="active",
            ),
        ]

    def _migrate_to_v2(self, agent: AgentDefinition) -> AgentDefinitionV2:
        """将旧 AgentDefinition 迁移为 V2。

        按 V1.2.2 第 5 节映射表将 V1 agent 转换为 V2 能力驱动定义。
        capabilities 从原 expertise/tools 推断为标准化能力名；
        legacy_agent_id 与 legacy_tools_json 保留原始信息用于历史关联。
        """
        spec = _V2_MIGRATION_MAP.get(agent.id)
        legacy_tools_json = json.dumps(agent.tools, ensure_ascii=False)
        if spec is None:
            # 未知 agent：使用通用兜底映射（analyst, L0）
            role = "analyst"
            return AgentDefinitionV2(
                agent_id=agent.id,
                name=agent.name,
                role=role,
                description=agent.description,
                capabilities=list(agent.expertise),
                required_capabilities=[],
                optional_capabilities=[],
                prohibited_actions=_DEFAULT_PROHIBITED_BY_ROLE.get(role, []),
                max_autonomy_level="L0",
                legacy_agent_id=agent.id,
                legacy_tools_json=legacy_tools_json,
                status=agent.status,
            )
        return AgentDefinitionV2(
            agent_id=spec["agent_id"],
            name=agent.name,
            role=spec["role"],
            description=agent.description,
            capabilities=list(spec["capabilities"]),
            required_capabilities=list(spec["required_capabilities"]),
            optional_capabilities=list(spec["optional_capabilities"]),
            prohibited_actions=list(spec["prohibited_actions"]),
            max_autonomy_level=spec["max_autonomy_level"],
            legacy_agent_id=agent.id,
            legacy_tools_json=legacy_tools_json,
            status=agent.status,
        )

    def list_agents(self) -> list[AgentDefinition]:
        """返回所有 agent（内置 + 自定义），内置 agent 填充 V2 字段。"""
        agents = list(self._builtin_agents)
        agents.extend(self._load_custom_agents())
        # 为内置 agent 填充 V2 字段（capabilities/allowed_profiles/max_autonomy_level/prohibited_actions）
        result: list[AgentDefinition] = []
        for a in agents:
            if a.is_builtin:
                v2 = self._migrate_to_v2(a)
                result.append(a.model_copy(update={
                    "capabilities": v2.capabilities,
                    "allowed_profiles": v2.allowed_profiles,
                    "max_autonomy_level": v2.max_autonomy_level,
                    "prohibited_actions": v2.prohibited_actions,
                }))
            else:
                result.append(a)
        return result

    def get_agent(self, agent_id: str) -> AgentDefinition | None:
        """获取单个 agent，先查内置再查自定义。内置 agent 填充 V2 字段。"""
        for a in self._builtin_agents:
            if a.id == agent_id:
                v2 = self._migrate_to_v2(a)
                return a.model_copy(update={
                    "capabilities": v2.capabilities,
                    "allowed_profiles": v2.allowed_profiles,
                    "max_autonomy_level": v2.max_autonomy_level,
                    "prohibited_actions": v2.prohibited_actions,
                })
        for a in self._load_custom_agents():
            if a.id == agent_id:
                return a
        return None

    def create_custom_agent(self, agent: AgentDefinition) -> AgentDefinition:
        """保存自定义 agent 到 PostgreSQL。"""
        if agent.is_builtin:
            agent.is_builtin = False
        if not agent.id or agent.id.startswith("builtin_"):
            agent.id = str(uuid.uuid4())
        self._validate_role(agent.role)
        with self.engine.begin() as conn:
            conn.execute(
                text("INSERT INTO agent_team.custom_agents (id, data) VALUES (:id, CAST(:data AS JSONB))"),
                {"id": agent.id, "data": agent.model_dump_json()},
            )
        return agent

    def update_agent(self, agent_id: str, updates: dict) -> AgentDefinition | None:
        """更新 agent。

        - 自定义 agent：直接更新 custom_agents 表。
        - 内置 agent：将更新字段写入 builtin_agent_overrides 表，启动时合并回内置定义。
        """
        existing = self.get_agent(agent_id)
        if not existing:
            return None
        # 合并更新字段
        updated_data = existing.model_dump()
        for key, value in updates.items():
            if key in updated_data and value is not None:
                updated_data[key] = value
        # id 与 is_builtin 不允许通过 updates 修改
        updated_data["id"] = agent_id
        updated_data["is_builtin"] = existing.is_builtin
        updated_agent = AgentDefinition(**updated_data)
        self._validate_role(updated_agent.role)

        if existing.is_builtin:
            # 内置 agent：只保存被覆盖的字段（非默认值），便于「重置」语义
            override_payload = {k: v for k, v in updated_data.items() if k not in ("id", "is_builtin")}
            with self.engine.begin() as conn:
                conn.execute(
                    text(
                        """
                        INSERT INTO agent_team.builtin_agent_overrides (id, data, updated_at)
                        VALUES (:id, CAST(:data AS JSONB), NOW())
                        ON CONFLICT (id) DO UPDATE
                            SET data = CAST(:data AS JSONB),
                                updated_at = NOW()
                        """
                    ),
                    {"id": agent_id, "data": json.dumps(override_payload, ensure_ascii=False)},
                )
            # 同步刷新内存中的内置 agent 列表，避免重启前显示陈旧数据
            for idx, a in enumerate(self._builtin_agents):
                if a.id == agent_id:
                    self._builtin_agents[idx] = updated_agent
                    break
            return updated_agent

        with self.engine.begin() as conn:
            conn.execute(
                text("UPDATE agent_team.custom_agents SET data = CAST(:data AS JSONB) WHERE id = :id"),
                {"data": updated_agent.model_dump_json(), "id": agent_id},
            )
        return updated_agent

    def reset_builtin_agent(self, agent_id: str) -> bool:
        """重置内置 agent 到默认定义（清除覆盖）。"""
        existing = self.get_agent(agent_id)
        if not existing or not existing.is_builtin:
            return False
        with self.engine.begin() as conn:
            cur = conn.execute(
                text("DELETE FROM agent_team.builtin_agent_overrides WHERE id = :id"),
                {"id": agent_id},
            )
        # 重新从默认定义加载
        defaults = self._init_builtin_agents()
        for a in defaults:
            if a.id == agent_id:
                for idx, builtin in enumerate(self._builtin_agents):
                    if builtin.id == agent_id:
                        self._builtin_agents[idx] = a
                        break
                break
        return cur.rowcount > 0

    def delete_agent(self, agent_id: str) -> bool:
        """删除自定义 agent（内置 agent 不可删除）。"""
        existing = self.get_agent(agent_id)
        if not existing or existing.is_builtin:
            return False
        with self.engine.begin() as conn:
            cur = conn.execute(
                text("DELETE FROM agent_team.custom_agents WHERE id = :id"),
                {"id": agent_id},
            )
        return cur.rowcount > 0

    def _load_custom_agents(self) -> list[AgentDefinition]:
        """从 PostgreSQL 加载所有自定义 agent。"""
        agents: list[AgentDefinition] = []
        with self.engine.connect() as conn:
            cur = conn.execute(
                text("SELECT data FROM agent_team.custom_agents ORDER BY created_at DESC")
            )
            for row in cur.fetchall():
                try:
                    data = row[0]
                    if isinstance(data, str):
                        agents.append(AgentDefinition.model_validate_json(data))
                    else:
                        agents.append(AgentDefinition.model_validate(data))
                except Exception:
                    # 跳过损坏的记录
                    continue
        return agents
