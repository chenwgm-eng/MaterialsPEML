"""研发流水线（Pipeline）—— 领域包流水线解析与阶段模型。

设计目标：把研发工作流步骤（原先硬编码在 orchestrator._action_sequence）
从代码中抽离，改为由领域包 data["pipeline"] 段声明。新增一个新材料领域时，
只需在该领域的领域包里声明各研发阶段（action / agent_role / autonomy /
executor_kind），整套编排骨架即可复用，无需改动核心协作代码。

领域包 pipeline 段结构（JSONB）：
{
  "pipeline": {
    "crystal": [
      {"action": "route_material", "agent_role": "planner", "autonomy_level": "L1"},
      {"action": "generate_crystal_candidates", "agent_role": "thinker", "autonomy_level": "L0"},
      {"action": "verify_dft", "agent_role": "doer", "autonomy_level": "L1",
       "executor_kind": "scp", "when": "requires_dft"},
      ...
    ],
    "polymer": [ ... ],
    "*": [ ... ]   # 未匹配具体类型的默认流水线
  }
}

- executor_kind：native / scp / skill / agent，交由 StageExecutor 分派。
- when：条件键，如 "requires_dft"，仅当上下文命中时才保留该阶段。
"""
from __future__ import annotations

from pydantic import BaseModel, Field

# action → capability 别名映射（默认能力解析；PipelineStage 可逐阶段覆盖）
ACTION_CAPABILITY_MAP: dict[str, str] = {
    "route_material": "material_reference_lookup",
    "generate_crystal_candidates": "chemical_descriptors",
    "generate_polymer_candidates": "chemical_descriptors",
    "predict_crystal_properties": "property_prediction",
    "predict_polymer_properties": "property_prediction",
    "check_synthesis_feasibility": "compliance_screening",
    "verify_dft": "dft_verification",
    "design_formula": "reaction_engineering_check",
    "compliance_check": "compliance_screening",
}


class PipelineStage(BaseModel):
    """研发流水线中的一个阶段（领域包声明的可变部分）。"""

    action: str
    agent_role: str = "doer"
    autonomy_level: str = "L1"
    capability: str = ""            # 默认由 action 映射；可逐阶段覆盖
    executor_kind: str = "native"   # native/scp/skill/agent
    when: str = ""                  # 条件键（如 requires_dft），满足才保留

    @property
    def resolved_capability(self) -> str:
        return self.capability or ACTION_CAPABILITY_MAP.get(self.action, "")


# 内置默认流水线（镜像旧 orchestrator._action_sequence 三分支），供无领域包
# 或领域包未声明 pipeline 时回退，保证仅回退路径下行为不回归。
BUILTIN_PIPELINES: dict[str, list[dict]] = {
    "crystal": [
        {"action": "route_material", "agent_role": "planner", "autonomy_level": "L1"},
        {"action": "generate_crystal_candidates", "agent_role": "thinker", "autonomy_level": "L0"},
        {"action": "predict_crystal_properties", "agent_role": "doer", "autonomy_level": "L1"},
        {"action": "verify_dft", "agent_role": "doer", "autonomy_level": "L1", "when": "requires_dft"},
        {"action": "compliance_check", "agent_role": "verifier", "autonomy_level": "L2"},
    ],
    "polymer": [
        {"action": "route_material", "agent_role": "planner", "autonomy_level": "L1"},
        {"action": "generate_polymer_candidates", "agent_role": "thinker", "autonomy_level": "L0"},
        {"action": "predict_polymer_properties", "agent_role": "doer", "autonomy_level": "L1"},
        {"action": "design_formula", "agent_role": "doer", "autonomy_level": "L1"},
        {"action": "compliance_check", "agent_role": "verifier", "autonomy_level": "L2"},
    ],
    "molecule": [
        {"action": "route_material", "agent_role": "planner", "autonomy_level": "L1"},
        {"action": "generate_polymer_candidates", "agent_role": "thinker", "autonomy_level": "L0"},
        {"action": "check_synthesis_feasibility", "agent_role": "doer", "autonomy_level": "L1"},
        {"action": "predict_crystal_properties", "agent_role": "doer", "autonomy_level": "L1"},
        {"action": "compliance_check", "agent_role": "verifier", "autonomy_level": "L2"},
    ],
}


class PipelineResolver:
    """从领域包解析研发流水线；无配置时回退内置默认。

    domain_pack 为领域包 data 字典。真实场景下由 DomainPackStore 解析活跃包
    后传入；测试或无关库场景可传 None 直接使用内置兜底。
    """

    def __init__(self, domain_pack: dict | None = None):
        self._domain_pack = domain_pack or {}

    def resolve(self, material_type: str, context: dict | None = None) -> list[PipelineStage]:
        """返回该材料类型的研发流水线阶段列表。

        context 用于计算 when 条件（如 {"requires_dft": True}）。
        解析优先级：领域包具体类型 > 领域包 "*" 默认 > 内置具体类型 > 内置 molecule。
        """
        context = context or {}
        pipeline_conf = self._domain_pack.get("pipeline") or {}
        stages_conf = pipeline_conf.get(material_type) or pipeline_conf.get("*")
        if not stages_conf:
            stages_conf = BUILTIN_PIPELINES.get(material_type) or BUILTIN_PIPELINES["molecule"]
        return self._build_stages(stages_conf, context)

    @staticmethod
    def _build_stages(stages_conf: list, context: dict) -> list[PipelineStage]:
        stages: list[PipelineStage] = []
        for conf in stages_conf:
            stage = PipelineStage(**conf)
            if stage.when and not context.get(stage.when):
                continue
            stages.append(stage)
        return stages