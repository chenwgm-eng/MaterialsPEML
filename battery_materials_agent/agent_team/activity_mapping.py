"""业务活动—智能体—工具 三层映射配置。

决策 1-13 的核心数据结构：
- ActivityAgentBinding: 业务活动→智能体（静态绑定 + 能力需求声明用于回退）
- AgentToolBinding: 智能体→主工具（显式绑定 + CapabilityRouter 评分回退）
- ToolOverride: 工具级 LLM 模型覆盖（决策 6）
- ToolRegistration: 新工具注册元数据（决策 11）

持久化：PostgreSQL（agent_team schema），启动时全量缓存（决策 12）。
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import text

from ..db import get_engine


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ===========================================================================
# 1. 业务活动 → 智能体绑定（决策 1：静态绑定 + 能力回退）
# ===========================================================================

class ActivityAgentBinding(BaseModel):
    """业务活动与智能体的绑定关系。

    决策 1-C：默认走 agent_id 静态绑定，agent 不可用时按 capability_need 动态回退。
    """
    binding_id: str = Field(default_factory=lambda: f"ab_{uuid.uuid4().hex[:12]}")
    activity_id: str  # 业务活动 ID，如 "ecml.step2_generate" / "project.decompose"
    activity_name: str = ""  # 人类可读名称，如"候选材料生成"
    activity_category: str = "ecml"  # ecml / project / experiment / discovery / synthesis
    agent_id: str  # 默认绑定的智能体 ID，如 "builtin_material_discovery"
    capability_need: str = ""  # 能力需求 ID，用于智能体不可用时回退，如 "molecule_polymer_design"
    enabled: bool = True
    notes: str = ""
    created_at: str = Field(default_factory=_utc_now)
    updated_at: str = Field(default_factory=_utc_now)


# ===========================================================================
# 2. 智能体 → 主工具绑定（决策 2：主工具显式 + 评分回退）
# ===========================================================================

class AgentToolBinding(BaseModel):
    """智能体在某能力下的主工具绑定。

    决策 2-C：primary_tool_id 显式绑定，不可用时按 CapabilityRouter 评分回退到候选池。
    决策 9-C：tools_whitelist/tools_blacklist 对能力标签关联的工具做增删。
    """
    binding_id: str = Field(default_factory=lambda: f"tb_{uuid.uuid4().hex[:12]}")
    agent_id: str
    capability: str  # 能力标签，如 "property_prediction"
    primary_tool_id: str  # 主工具，如 "ase_emt" 或 "scp_scitool_mat"
    # 决策 9-C：能力关联工具之外的额外白名单/黑名单
    tools_whitelist: list[str] = Field(default_factory=list)  # 追加到候选池
    tools_blacklist: list[str] = Field(default_factory=list)  # 从候选池排除
    # 决策 6-C：工具内 LLM 模型覆盖（空则跟随智能体模型）
    tool_model_override: dict[str, str] = Field(default_factory=dict)
    # 形如 {"internlm": "intern-s2-preview-397b"}，key 为工具 id
    enabled: bool = True
    created_at: str = Field(default_factory=_utc_now)
    updated_at: str = Field(default_factory=_utc_now)


# ===========================================================================
# 3. 工具注册元数据（决策 11：新工具可被智能体感知）
# ===========================================================================

class ToolRegistration(BaseModel):
    """工具注册元数据，决定工具如何被智能体感知和调用。

    决策 11-C：基础向导 + 高级声明。
    决策 8-C：execution_mode 标识 sync/async，智能体自动适配。
    """
    tool_id: str = Field(default_factory=lambda: f"tool_{uuid.uuid4().hex[:10]}")
    name: str  # 显示名
    source: str  # local / scp / skill / mcp
    # 关联能力标签（决策 9-C：能力标签关联的工具自动进入智能体候选池）
    capability_refs: list[str] = Field(default_factory=list)
    # 决策 8-C：执行模式
    execution_mode: str = "sync"  # sync / async
    # SCP/SKILL 关联字段
    scp_internal_name: str = ""  # 对应 ToolBinding.internal_name
    skill_id: str = ""  # 对应 SkillBinding.skill_id
    mcp_tool_name: str = ""  # 对应 MCPToolRegistry 中的工具名
    # 默认参数模板（可选）
    default_params: dict = Field(default_factory=dict)
    # 风险等级（A/B/C/D）
    risk_level: str = "B"
    enabled: bool = True
    description: str = ""
    # 是否为用户自定义注册（决策 11）
    user_registered: bool = False
    created_at: str = Field(default_factory=_utc_now)
    updated_at: str = Field(default_factory=_utc_now)


# ===========================================================================
# 4. 持久化 + 启动时全量缓存（决策 12-C）
# ===========================================================================

class ActivityMappingStore:
    """业务活动—智能体—工具 映射的持久化存储与缓存。

    决策 12-C：PostgreSQL 为 source of truth，启动时全量加载到内存，
    配置变更时双写（DB + 缓存刷新）。
    """

    def __init__(self):
        self.engine = get_engine()
        self._ensure_tables()
        # 全量缓存
        self._activity_bindings: dict[str, ActivityAgentBinding] = {}
        self._agent_tool_bindings: dict[str, AgentToolBinding] = {}
        self._tool_registrations: dict[str, ToolRegistration] = {}
        self._loaded = False

    def _ensure_tables(self):
        """幂等创建三张映射表。"""
        with self.engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS agent_team.activity_agent_bindings (
                    binding_id TEXT PRIMARY KEY,
                    activity_id TEXT NOT NULL,
                    data JSONB NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_activity_bindings_activity
                ON agent_team.activity_agent_bindings(activity_id)
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_activity_bindings_agent
                ON agent_team.activity_agent_bindings((data->>'agent_id'))
            """))

            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS agent_team.agent_tool_bindings (
                    binding_id TEXT PRIMARY KEY,
                    agent_id TEXT NOT NULL,
                    capability TEXT NOT NULL,
                    data JSONB NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_agent_tool_bindings_agent
                ON agent_team.agent_tool_bindings(agent_id)
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_agent_tool_bindings_cap
                ON agent_team.agent_tool_bindings(capability)
            """))

            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS agent_team.tool_registrations (
                    tool_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    source TEXT NOT NULL,
                    data JSONB NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_tool_registrations_source
                ON agent_team.tool_registrations(source)
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_tool_registrations_cap_gin
                ON agent_team.tool_registrations USING GIN ((data->'capability_refs'))
            """))

    def load_all(self):
        """全量加载到内存缓存。"""
        if self._loaded:
            return
        with self.engine.connect() as conn:
            # 加载业务活动绑定
            rows = conn.execute(text(
                "SELECT data FROM agent_team.activity_agent_bindings ORDER BY created_at ASC"
            )).fetchall()
            for (data,) in rows:
                try:
                    b = ActivityAgentBinding.model_validate(json.loads(data))
                    self._activity_bindings[b.activity_id] = b
                except Exception:
                    continue

            # 加载智能体工具绑定
            rows = conn.execute(text(
                "SELECT data FROM agent_team.agent_tool_bindings ORDER BY created_at ASC"
            )).fetchall()
            for (data,) in rows:
                try:
                    b = AgentToolBinding.model_validate(json.loads(data))
                    self._agent_tool_bindings[f"{b.agent_id}:{b.capability}"] = b
                except Exception:
                    continue

            # 加载工具注册
            rows = conn.execute(text(
                "SELECT data FROM agent_team.tool_registrations ORDER BY created_at ASC"
            )).fetchall()
            for (data,) in rows:
                try:
                    t = ToolRegistration.model_validate(json.loads(data))
                    self._tool_registrations[t.tool_id] = t
                except Exception:
                    continue

        self._loaded = True

    # ----- 业务活动 → 智能体 -----

    def get_agent_for_activity(self, activity_id: str) -> Optional[ActivityAgentBinding]:
        self.load_all()
        return self._activity_bindings.get(activity_id)

    def list_activity_bindings(self, category: str = "") -> list[ActivityAgentBinding]:
        self.load_all()
        items = list(self._activity_bindings.values())
        if category:
            items = [b for b in items if b.activity_category == category]
        return items

    def upsert_activity_binding(self, binding: ActivityAgentBinding) -> ActivityAgentBinding:
        binding.updated_at = _utc_now()
        with self.engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO agent_team.activity_agent_bindings
                    (binding_id, activity_id, data, created_at, updated_at)
                VALUES (:bid, :aid, :data, NOW(), NOW())
                ON CONFLICT (binding_id) DO UPDATE SET
                    activity_id = EXCLUDED.activity_id,
                    data = EXCLUDED.data,
                    updated_at = NOW()
            """), {
                "bid": binding.binding_id,
                "aid": binding.activity_id,
                "data": json.dumps(binding.model_dump(), ensure_ascii=False),
            })
        # 刷新缓存
        self._activity_bindings[binding.activity_id] = binding
        return binding

    def delete_activity_binding(self, binding_id: str) -> bool:
        with self.engine.begin() as conn:
            cur = conn.execute(text(
                "DELETE FROM agent_team.activity_agent_bindings WHERE binding_id = :bid"
            ), {"bid": binding_id})
            if cur.rowcount == 0:
                return False
        # 刷新缓存
        self._activity_bindings = {
            aid: b for aid, b in self._activity_bindings.items() if b.binding_id != binding_id
        }
        return True

    # ----- 智能体 → 工具 -----

    def get_tool_binding(self, agent_id: str, capability: str) -> Optional[AgentToolBinding]:
        self.load_all()
        return self._agent_tool_bindings.get(f"{agent_id}:{capability}")

    def list_tool_bindings(self, agent_id: str = "") -> list[AgentToolBinding]:
        self.load_all()
        items = list(self._agent_tool_bindings.values())
        if agent_id:
            items = [b for b in items if b.agent_id == agent_id]
        return items

    def upsert_tool_binding(self, binding: AgentToolBinding) -> AgentToolBinding:
        binding.updated_at = _utc_now()
        with self.engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO agent_team.agent_tool_bindings
                    (binding_id, agent_id, capability, data, created_at, updated_at)
                VALUES (:bid, :aid, :cap, :data, NOW(), NOW())
                ON CONFLICT (binding_id) DO UPDATE SET
                    agent_id = EXCLUDED.agent_id,
                    capability = EXCLUDED.capability,
                    data = EXCLUDED.data,
                    updated_at = NOW()
            """), {
                "bid": binding.binding_id,
                "aid": binding.agent_id,
                "cap": binding.capability,
                "data": json.dumps(binding.model_dump(), ensure_ascii=False),
            })
        self._agent_tool_bindings[f"{binding.agent_id}:{binding.capability}"] = binding
        return binding

    def delete_tool_binding(self, binding_id: str) -> bool:
        with self.engine.begin() as conn:
            cur = conn.execute(text(
                "DELETE FROM agent_team.agent_tool_bindings WHERE binding_id = :bid"
            ), {"bid": binding_id})
            if cur.rowcount == 0:
                return False
        self._agent_tool_bindings = {
            k: b for k, b in self._agent_tool_bindings.items() if b.binding_id != binding_id
        }
        return True

    # ----- 工具注册 -----

    def get_tool_registration(self, tool_id: str) -> Optional[ToolRegistration]:
        self.load_all()
        return self._tool_registrations.get(tool_id)

    def list_tool_registrations(self, source: str = "") -> list[ToolRegistration]:
        self.load_all()
        items = list(self._tool_registrations.values())
        if source:
            items = [t for t in items if t.source == source]
        return items

    def find_tools_by_capability(self, capability: str) -> list[ToolRegistration]:
        """按能力标签查找工具（决策 9-C：能力标签关联工具进入智能体候选池）。"""
        self.load_all()
        return [t for t in self._tool_registrations.values()
                if t.enabled and capability in t.capability_refs]

    def upsert_tool_registration(self, reg: ToolRegistration) -> ToolRegistration:
        reg.updated_at = _utc_now()
        with self.engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO agent_team.tool_registrations
                    (tool_id, name, source, data, created_at, updated_at)
                VALUES (:tid, :name, :source, :data, NOW(), NOW())
                ON CONFLICT (tool_id) DO UPDATE SET
                    name = EXCLUDED.name,
                    source = EXCLUDED.source,
                    data = EXCLUDED.data,
                    updated_at = NOW()
            """), {
                "tid": reg.tool_id,
                "name": reg.name,
                "source": reg.source,
                "data": json.dumps(reg.model_dump(), ensure_ascii=False),
            })
        self._tool_registrations[reg.tool_id] = reg
        return reg

    def delete_tool_registration(self, tool_id: str) -> bool:
        with self.engine.begin() as conn:
            cur = conn.execute(text(
                "DELETE FROM agent_team.tool_registrations WHERE tool_id = :tid"
            ), {"tid": tool_id})
            if cur.rowcount == 0:
                return False
        self._tool_registrations.pop(tool_id, None)
        return True

    def invalidate(self):
        """手动失效缓存（管理员变更后可调用）。"""
        self._loaded = False
        self._activity_bindings.clear()
        self._agent_tool_bindings.clear()
        self._tool_registrations.clear()


# ===========================================================================
# 5. 默认业务活动 → 智能体绑定种子（决策 5-D：全量覆盖）
# ===========================================================================

def _default_activity_bindings() -> list[ActivityAgentBinding]:
    """全量业务活动的默认智能体绑定。

    覆盖 ECML 7 步 + 项目/实验/发现/合成等所有业务活动。
    """
    return [
        # --- ECML 7 步 ---
        ActivityAgentBinding(
            activity_id="ecml.step1_route",
            activity_name="材料路由",
            activity_category="ecml",
            agent_id="builtin_material_router",
            capability_need="material_planning",
        ),
        ActivityAgentBinding(
            activity_id="ecml.step2_generate",
            activity_name="候选材料生成",
            activity_category="ecml",
            agent_id="builtin_material_discovery",
            capability_need="molecule_polymer_design",
        ),
        ActivityAgentBinding(
            activity_id="ecml.step3_synthesis_check",
            activity_name="合成可行性检查",
            activity_category="ecml",
            agent_id="builtin_synthesis_planner",
            capability_need="synthesis_evidence",
        ),
        ActivityAgentBinding(
            activity_id="ecml.step3_industrialization",
            activity_name="工业化配方与合规",
            activity_category="ecml",
            agent_id="builtin_industrialization",
            capability_need="industrialization",
        ),
        ActivityAgentBinding(
            activity_id="ecml.step4_predict",
            activity_name="性质预测",
            activity_category="ecml",
            agent_id="builtin_battery_oracle",
            capability_need="property_prediction",
        ),
        ActivityAgentBinding(
            activity_id="ecml.step5_verify",
            activity_name="DFT 验证",
            activity_category="ecml",
            agent_id="builtin_dft_verifier",
            capability_need="dft_verification",
        ),
        ActivityAgentBinding(
            activity_id="ecml.step6_experiment",
            activity_name="实验执行",
            activity_category="ecml",
            agent_id="builtin_experiment_analyst",
            capability_need="experiment_qc_lookup",
        ),
        ActivityAgentBinding(
            activity_id="ecml.step7_feedback",
            activity_name="反馈学习",
            activity_category="ecml",
            agent_id="builtin_battery_learner",
            capability_need="experiment_qc_lookup",
        ),
        # --- 项目管理 ---
        ActivityAgentBinding(
            activity_id="project.decompose",
            activity_name="项目目标 AI 拆解",
            activity_category="project",
            agent_id="builtin_project_manager",
            capability_need="material_planning",
        ),
        ActivityAgentBinding(
            activity_id="project.literature_research",
            activity_name="项目文献调研",
            activity_category="project",
            agent_id="builtin_literature_researcher",
            capability_need="evidence_research",
        ),
        # --- 实验管理 ---
        ActivityAgentBinding(
            activity_id="experiment.design",
            activity_name="实验任务设计",
            activity_category="experiment",
            agent_id="builtin_experiment_analyst",
            capability_need="experiment_qc_lookup",
        ),
        ActivityAgentBinding(
            activity_id="experiment.analyze",
            activity_name="实验数据分析",
            activity_category="experiment",
            agent_id="builtin_experiment_analyst",
            capability_need="experiment_qc_lookup",
        ),
        # --- 材料发现 ---
        ActivityAgentBinding(
            activity_id="discovery.crystal",
            activity_name="晶体材料发现",
            activity_category="discovery",
            agent_id="builtin_material_discovery",
            capability_need="molecule_polymer_design",
        ),
        ActivityAgentBinding(
            activity_id="discovery.polymer",
            activity_name="聚合物材料发现",
            activity_category="discovery",
            agent_id="builtin_material_discovery",
            capability_need="molecule_polymer_design",
        ),
        # --- 合成规划 ---
        ActivityAgentBinding(
            activity_id="synthesis.planning",
            activity_name="逆合成路线规划",
            activity_category="synthesis",
            agent_id="builtin_synthesis_planner",
            capability_need="synthesis_evidence",
        ),
        # --- 电池机理解释 ---
        ActivityAgentBinding(
            activity_id="battery.interpret",
            activity_name="电池机理解释",
            activity_category="battery",
            agent_id="builtin_battery_interpreter",
            capability_need="evidence_research",
        ),
        # --- 质量审核 ---
        ActivityAgentBinding(
            activity_id="quality.review",
            activity_name="质量审核",
            activity_category="quality",
            agent_id="builtin_quality_reviewer",
            capability_need="compliance_screening",
        ),
        ActivityAgentBinding(
            activity_id="quality.cross_validate",
            activity_name="交叉验证",
            activity_category="quality",
            agent_id="builtin_cross_validator",
            capability_need="compliance_screening",
        ),
    ]


def _default_tool_bindings() -> list[AgentToolBinding]:
    """智能体→主工具的默认绑定。"""
    return [
        # 材料路由 → 本地 route_material
        AgentToolBinding(
            agent_id="builtin_material_router",
            capability="material_planning",
            primary_tool_id="route_material",
        ),
        # 候选生成（晶体）→ 本地 generate_crystal_candidates
        AgentToolBinding(
            agent_id="builtin_material_discovery",
            capability="molecule_polymer_design",
            primary_tool_id="generate_crystal_candidates",
        ),
        # 候选生成（聚合物）→ 本地 generate_polymer_candidates
        AgentToolBinding(
            agent_id="builtin_material_discovery",
            capability="polymer_candidate_generation",
            primary_tool_id="generate_polymer_candidates",
        ),
        # 合成可行性 → check_synthesis_feasibility
        AgentToolBinding(
            agent_id="builtin_synthesis_planner",
            capability="synthesis_evidence",
            primary_tool_id="check_synthesis_feasibility",
        ),
        # 工业化配方 → design_formula
        AgentToolBinding(
            agent_id="builtin_industrialization",
            capability="industrialization",
            primary_tool_id="design_formula",
        ),
        # 性质预测（晶体）→ predict_crystal_properties
        AgentToolBinding(
            agent_id="builtin_battery_oracle",
            capability="property_prediction",
            primary_tool_id="predict_crystal_properties",
            tool_model_override={"predict_crystal_properties": "intern-s2-preview-397b"},
        ),
        # 性质预测（聚合物）→ predict_polymer_properties
        AgentToolBinding(
            agent_id="builtin_battery_oracle",
            capability="polymer_property_prediction",
            primary_tool_id="predict_polymer_properties",
            tool_model_override={"predict_polymer_properties": "intern-s2-preview-397b"},
        ),
        # DFT 验证 → verify_dft
        AgentToolBinding(
            agent_id="builtin_dft_verifier",
            capability="dft_verification",
            primary_tool_id="verify_dft",
        ),
        # 实验执行 → get_experiment_results
        AgentToolBinding(
            agent_id="builtin_experiment_analyst",
            capability="experiment_qc_lookup",
            primary_tool_id="get_experiment_results",
        ),
        # 评测修复 P1-002：ECML step7 反馈学习 → 复用实验数据查询工具，
        # 恢复"实验数据 → 反馈学习"闭环（此前无绑定导致 step7 无工具可用）
        AgentToolBinding(
            agent_id="builtin_battery_learner",
            capability="experiment_qc_lookup",
            primary_tool_id="get_experiment_results",
        ),
        # 文献调研 → SCP 文献检索
        AgentToolBinding(
            agent_id="builtin_literature_researcher",
            capability="evidence_research",
            primary_tool_id="scp_literature_search",
        ),
        # 质量审核 → compliance_screening
        AgentToolBinding(
            agent_id="builtin_quality_reviewer",
            capability="compliance_screening",
            primary_tool_id="check_synthesis_feasibility",
        ),
    ]


def _default_tool_registrations() -> list[ToolRegistration]:
    """默认工具注册（覆盖本地 MCP 工具 + 主要 SCP/SKILL）。"""
    tools = [
        # --- 本地 MCP 工具 ---
        ToolRegistration(
            tool_id="route_material",
            name="材料路由",
            source="local",
            capability_refs=["material_planning", "material_reference_lookup"],
            execution_mode="sync",
            mcp_tool_name="route_material",
            risk_level="A",
            description="判断材料类型（晶体/聚合物）并解析元素约束",
        ),
        ToolRegistration(
            tool_id="generate_crystal_candidates",
            name="晶体候选生成",
            source="local",
            capability_refs=["molecule_polymer_design", "crystal_candidate_generation"],
            execution_mode="sync",
            mcp_tool_name="generate_crystal_candidates",
            risk_level="B",
            description="基于约束生成晶体候选材料",
        ),
        ToolRegistration(
            tool_id="generate_polymer_candidates",
            name="聚合物候选生成",
            source="local",
            capability_refs=["molecule_polymer_design", "polymer_candidate_generation"],
            execution_mode="sync",
            mcp_tool_name="generate_polymer_candidates",
            risk_level="B",
            description="基于约束生成聚合物候选材料",
        ),
        ToolRegistration(
            tool_id="predict_crystal_properties",
            name="晶体性质预测",
            source="local",
            capability_refs=["property_prediction", "crystal_property_prediction"],
            execution_mode="sync",
            mcp_tool_name="predict_crystal_properties",
            risk_level="B",
            description="预测晶体材料的 band_gap/formation_energy 等性质",
        ),
        ToolRegistration(
            tool_id="predict_polymer_properties",
            name="聚合物性质预测",
            source="local",
            capability_refs=["property_prediction", "polymer_property_prediction"],
            execution_mode="sync",
            mcp_tool_name="predict_polymer_properties",
            risk_level="B",
            description="预测聚合物材料的 ionic_conductivity/band_gap 等性质",
        ),
        ToolRegistration(
            tool_id="check_synthesis_feasibility",
            name="合成可行性检查",
            source="local",
            capability_refs=["synthesis_evidence", "compliance_screening"],
            execution_mode="sync",
            mcp_tool_name="check_synthesis_feasibility",
            risk_level="B",
            description="评估候选材料的逆合成可行性",
        ),
        ToolRegistration(
            tool_id="verify_dft",
            name="DFT 验证",
            source="local",
            capability_refs=["dft_verification"],
            execution_mode="sync",
            mcp_tool_name="verify_dft",
            risk_level="C",
            description="DFT 单点能验证（需 PySCF/VASP）",
        ),
        ToolRegistration(
            tool_id="get_experiment_results",
            name="实验结果查询",
            source="local",
            capability_refs=["experiment_qc_lookup"],
            execution_mode="sync",
            mcp_tool_name="get_experiment_results",
            risk_level="B",
            description="查询实验记录与 QC 数据",
        ),
        ToolRegistration(
            tool_id="design_formula",
            name="配方设计",
            source="local",
            capability_refs=["industrialization", "reaction_engineering_check"],
            execution_mode="sync",
            mcp_tool_name="design_formula",
            risk_level="B",
            description="生成 BOM/BOP 配方",
        ),
        # --- 主要 SCP 工具（能力级绑定）---
        ToolRegistration(
            tool_id="scp_molecule_descriptors",
            name="分子描述符计算（SCP）",
            source="scp",
            capability_refs=["property_prediction", "chemical_descriptors"],
            execution_mode="async",
            scp_internal_name="scp_molecule_descriptors",
            risk_level="B",
            description="SCP 远程分子描述符计算",
        ),
        ToolRegistration(
            tool_id="scp_toxicity_assessment",
            name="毒理评估（SCP）",
            source="scp",
            capability_refs=["compliance_screening", "bioactivity_risk_lookup"],
            execution_mode="async",
            scp_internal_name="scp_toxicity_assessment",
            risk_level="B",
            description="SCP 远程毒理与生物活性评估",
        ),
        ToolRegistration(
            tool_id="scp_literature_search",
            name="文献检索（SCP）",
            source="scp",
            capability_refs=["evidence_research", "material_knowledge_query"],
            execution_mode="async",
            scp_internal_name="scp_literature_search",
            risk_level="B",
            description="SCP 远程文献检索",
        ),
        ToolRegistration(
            tool_id="scp_protocol_draft",
            name="实验协议草案（SCP）",
            source="scp",
            capability_refs=["experiment_qc_lookup"],
            execution_mode="async",
            scp_internal_name="scp_protocol_draft",
            risk_level="B",
            description="SCP 远程实验协议草案生成",
        ),
        ToolRegistration(
            tool_id="scp_material_transform",
            name="材料结构转换（SCP）",
            source="scp",
            capability_refs=["molecule_polymer_design", "structure_validation"],
            execution_mode="async",
            scp_internal_name="scp_material_transform",
            risk_level="B",
            description="SCP 远程材料结构转换",
        ),
    ]
    return tools


def seed_default_mappings(store: ActivityMappingStore):
    """幂等种子默认映射关系。"""
    store.load_all()

    # 种子业务活动绑定
    existing_activities = {b.activity_id for b in store.list_activity_bindings()}
    for binding in _default_activity_bindings():
        if binding.activity_id not in existing_activities:
            store.upsert_activity_binding(binding)

    # 种子智能体工具绑定
    existing_tool_bindings = {
        (b.agent_id, b.capability) for b in store.list_tool_bindings()
    }
    for binding in _default_tool_bindings():
        if (binding.agent_id, binding.capability) not in existing_tool_bindings:
            store.upsert_tool_binding(binding)

    # 种子工具注册
    existing_tools = {t.tool_id for t in store.list_tool_registrations()}
    for reg in _default_tool_registrations():
        if reg.tool_id not in existing_tools:
            store.upsert_tool_registration(reg)
