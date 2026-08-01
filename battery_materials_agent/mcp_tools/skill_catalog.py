"""SKILL Catalog — 声明式配置的 SKILL 注册表。

SKILL 是「组合能力」：按顺序流水线（pipeline）编排一个或多个 SCP 工具，
上一个工具的输出可映射为下一个工具的输入。配置完全声明式，无代码逻辑。
"""

from __future__ import annotations
from enum import Enum
from pydantic import BaseModel, Field, field_validator

from ..capability.models import validate_semver


class SkillRiskLevel(str, Enum):
    A = "A"  # 纯计算/查询 - 可自动调用
    B = "B"  # 辅助证据类 - 可自动调用，结果标识"辅助证据"
    C = "C"  # 默认禁用，管理员白名单启用


class SkillPipelineStep(BaseModel):
    """SKILL 流水线中的一步：调用一个 SCP 远端工具。"""

    step_id: str
    server_id: str
    tool_name: str
    # 输入映射：键=工具参数名，值=静态值 或 "${input.xxx}" 或 "${prev.output.xxx}"
    # "${input.xxx}" 从 SKILL 调用者传入的参数中取值
    # "${prev.output.xxx}" 从上一步输出的 dict 中取 xxx 字段
    # "${prev.output}" 取上一步输出的整个解析结果
    # "${prev.output_text}" 取上一步输出的原始文本
    input_mapping: dict[str, object] = Field(default_factory=dict)
    description: str = ""


class SkillBinding(BaseModel):
    """一个 SKILL 的完整声明式配置。"""

    skill_id: str
    name: str
    description: str = ""
    summary: str = ""
    introduction: str = ""
    features: list[str] = Field(default_factory=list)
    use_cases: list[str] = Field(default_factory=list)
    pipeline: list[SkillPipelineStep] = Field(default_factory=list)
    risk_level: SkillRiskLevel = SkillRiskLevel.B
    enabled: bool = True
    provider: str = ""
    # SKILL 版本号（semver，可选 "v" 前缀）
    version: str = "1.0.0"
    # 关联的能力契约 ID 列表
    capability_refs: list[str] = Field(default_factory=list)
    # 绑定的 ECML 步骤（与 ECML 7 步对齐：1=路由 2=候选生成 3=合成/工业化
    # 4=性质预测 5=DFT 验证 6=实验分析 7=反馈学习）
    # 语义：SKILL 整体可在哪些 ECML step 触发执行（语义层约束）。
    # 注意：pipeline 内单步工具的 server 级 ecml_steps 可能与 SKILL 整体不同
    # （例如 polymer_property_analysis 整体绑定 [2,4]，但其 pipeline 内调用
    # server 28 (scp_intern_agent) 该 server 自身 ecml_steps=[1,7]）。
    # SkillExecutor 在执行时会先检查 SKILL 整体门禁，再检查 pipeline 内每个工具
    # 的 server 级门禁；两者任一不通过则拒绝执行。
    # 空 list 表示该 SKILL 不受 ECML step 门禁约束。
    ecml_steps: list[int] = Field(default_factory=list)
    # 自检用的默认输入参数
    test_input: dict[str, object] = Field(default_factory=dict)
    # 涉及的 SCP server 数量（信息字段，由 pipeline 推导）
    server_count: int = 0
    # 官方认证标记
    official: bool = False

    @field_validator("version")
    @classmethod
    def _validate_version(cls, v: str) -> str:
        return validate_semver(v)


class SkillCatalog:
    """声明式 SKILL 注册表。"""

    def __init__(self):
        self._skills: dict[str, SkillBinding] = {}
        self._init_standard_skills()

    def _init_standard_skills(self):
        """初始化 8 个官方认证 SKILL。

        配置来源：https://discovery.intern-ai.org.cn/scp/material
        每个 SKILL 按网页描述的「组合工具」编排为顺序流水线。

        适配说明：
        - 官方 SKILL 中 NameToSMILES (server 31) 实测对所有输入返回 "Could not find"
          （远端工具故障），统一替换为功能等价的 ChemicalStructureAnalyzer (server 28)
          （按化合物名返回 SMILES、分子式、分子量等完整结构信息）。
        - 官方 polymer_property_analysis 中 CalculateSymmetry / CalculateDensity / MofLattice
          (server 30) 实测仅接受 SCP 服务器本地 CIF 文件路径（不接受 URL/SMILES/formula），
          在我们环境中无法直接调用。为保留 SKILL 的 4 步组合能力，替换为同样来自官方
          SCP 工具集的 ChemicalStructureAnalyzer / SMILESToWeight / MolecularDescriptorCalculator，
          覆盖成分→结构→分子量→描述符的材料特性分析全链路。
        """
        skills = [
            # 1. polymer_property_analysis
            # 官方组合：MaterialCompositionAnalyzer + CalculateSymmetry + CalculateDensity + MofLattice
            # 适配后：MaterialCompositionAnalyzer + ChemicalStructureAnalyzer + SMILESToWeight + MolecularDescriptorCalculator
            # 原因：CalculateSymmetry/CalculateDensity/MofLattice 仅接受 SCP 服务器本地 CIF 文件路径
            SkillBinding(
                skill_id="polymer_property_analysis",
                name="聚合物和材料特性分析",
                description="分析聚合物特性：材料设计的成分、结构、分子量和描述符",
                summary="组合 4 个工具完成聚合物全链路特性分析",
                introduction=(
                    "该 SKILL 依次调用 MaterialCompositionAnalyzer（成分分析）、"
                    "ChemicalStructureAnalyzer（结构解析）、SMILESToWeight（分子量计算）"
                    "和 MolecularDescriptorCalculator（高级描述符），覆盖从成分到描述符"
                    "的完整材料特性分析流程，为材料设计提供系统化数据支持。"
                    "（官方原版含 CalculateSymmetry/CalculateDensity/MofLattice，因这些工具"
                    "仅接受 SCP 服务器本地 CIF 文件路径，已适配为可在线调用的等价工具组合。）"
                ),
                features=[
                    "材料成分分析（元素组成、比例、氧化态）",
                    "化学结构解析（SMILES、分子式、原子数）",
                    "分子量计算",
                    "高级分子描述符（logP、TPSA、拓扑指数等）",
                ],
                use_cases=[
                    "聚合物材料的综合特性评估",
                    "新材料设计前的数据收集",
                    "候选材料的成分-结构-性质关联分析",
                ],
                pipeline=[
                    SkillPipelineStep(
                        step_id="step1_composition",
                        server_id="28",
                        tool_name="MaterialCompositionAnalyzer",
                        input_mapping={"formula": "${input.formula}"},
                        description="分析材料成分",
                    ),
                    SkillPipelineStep(
                        step_id="step2_structure",
                        server_id="28",
                        tool_name="ChemicalStructureAnalyzer",
                        input_mapping={"compound_name": "${input.compound_name}"},
                        description="解析化学结构",
                    ),
                    SkillPipelineStep(
                        step_id="step3_weight",
                        server_id="31",
                        tool_name="SMILESToWeight",
                        input_mapping={"smiles": "${input.smiles}"},
                        description="计算分子量",
                    ),
                    SkillPipelineStep(
                        step_id="step4_descriptors",
                        server_id="28",
                        tool_name="MolecularDescriptorCalculator",
                        input_mapping={"smiles": "${input.smiles}"},
                        description="计算高级分子描述符",
                    ),
                ],
                risk_level=SkillRiskLevel.A,
                provider="上海人工智能实验室",
                capability_refs=["polymer_property_prediction_v1", "crystal_property_prediction_v1"],
                ecml_steps=[2, 4],
                test_input={"formula": "LiCoO2", "compound_name": "ethanol", "smiles": "CCO"},
                official=True,
            ),
            # 2. material-density-volume-calculation
            SkillBinding(
                skill_id="material_density_volume_calculation",
                name="材料密度与体积计算",
                description="根据质量和几何尺寸计算材料密度和体积以进行材料力学分析",
                summary="调用材料力学工具计算密度和体积",
                introduction=(
                    "该 SKILL 调用材料力学与断裂分析工具集中的 calculate_material_density "
                    "工具，根据质量参数和几何尺寸计算材料密度，为材料力学分析提供基础数据。"
                ),
                features=[
                    "材料密度自动计算",
                    "支持比重的输入方式",
                    "输出标准化密度值",
                ],
                use_cases=[
                    "工程材料建模前的密度估算",
                    "材料性能评估的基础数据获取",
                ],
                pipeline=[
                    SkillPipelineStep(
                        step_id="step1_density",
                        server_id="20",
                        tool_name="calculate_material_density",
                        input_mapping={
                            "specific_gravity": "${input.specific_gravity}",
                            "water_density_kg_m3": "${input.water_density_kg_m3}",
                        },
                        description="计算材料密度",
                    ),
                ],
                risk_level=SkillRiskLevel.A,
                provider="上海人工智能实验室",
                capability_refs=["crystal_property_prediction_v1", "polymer_property_prediction_v1"],
                ecml_steps=[4, 5],
                test_input={"specific_gravity": 0.2, "water_density_kg_m3": 1000},
                official=True,
            ),
            # 3. unit-conversion-nanoscale
            SkillBinding(
                skill_id="unit_conversion_nanoscale",
                name="纳米尺度单位转换",
                description="在纳米尺度上转换物理量和单位，以用于材料科学和纳米技术应用",
                summary="调用物理量与单位换算工具进行纳米尺度转换",
                introduction=(
                    "该 SKILL 调用物理量与单位换算工具集中的 convert_length_to_meters "
                    "工具，将纳米尺度的长度值转换为米，为纳米技术应用的单位标准化提供支持。"
                ),
                features=[
                    "纳米尺度长度单位转换",
                    "支持千米到米的精确换算",
                ],
                use_cases=[
                    "纳米材料的尺寸单位标准化",
                    "跨尺度分析中的单位对齐",
                ],
                pipeline=[
                    SkillPipelineStep(
                        step_id="step1_convert",
                        server_id="27",
                        tool_name="convert_length_to_meters",
                        input_mapping={"length_km": "${input.length_km}"},
                        description="长度单位转换",
                    ),
                ],
                risk_level=SkillRiskLevel.A,
                provider="上海人工智能实验室",
                capability_refs=["crystal_property_prediction_v1", "experiment_analyst_v1"],
                ecml_steps=[4, 6],
                test_input={"length_km": 1},
                official=True,
            ),
            # 4. molecular-descriptors-calculation
            # 官方组合：SMILESToWeight + MolecularDescriptorCalculator
            # 适配：MolecularDescriptorCalculator 真实 schema 要求 smiles（非 compound_name）
            SkillBinding(
                skill_id="molecular_descriptors_calculation",
                name="高级分子描述符计算",
                description="计算高级分子描述符，包括 QSAR 和药物发现的形状指数、连接指数和结构特征",
                summary="组合 2 个工具计算分子描述符",
                introduction=(
                    "该 SKILL 先通过 SMILESToWeight 获取分子量基础信息，再调用 "
                    "MolecularDescriptorCalculator 计算形状指数、连接指数等高级描述符，"
                    "为 QSAR 建模和药物发现提供完整的分子特征输入。"
                ),
                features=[
                    "分子量基础信息获取",
                    "高级分子描述符计算（形状指数、连接指数、结构特征）",
                    "QSAR 建模的标准化特征输入",
                ],
                use_cases=[
                    "药物发现中的分子特征提取",
                    "QSAR 建模的输入特征生成",
                    "候选分子的高通量筛选",
                ],
                pipeline=[
                    SkillPipelineStep(
                        step_id="step1_weight",
                        server_id="31",
                        tool_name="SMILESToWeight",
                        input_mapping={"smiles": "${input.smiles}"},
                        description="获取分子量",
                    ),
                    SkillPipelineStep(
                        step_id="step2_descriptors",
                        server_id="28",
                        tool_name="MolecularDescriptorCalculator",
                        input_mapping={"smiles": "${input.smiles}"},
                        description="计算高级分子描述符",
                    ),
                ],
                risk_level=SkillRiskLevel.A,
                provider="上海人工智能实验室",
                capability_refs=["polymer_property_prediction_v1", "crystal_candidate_generation_v1"],
                ecml_steps=[2, 4],
                test_input={"smiles": "CCO"},
                official=True,
            ),
            # 5. molecular-property-profiling
            # 官方组合：ChemicalStructureAnalyzer + LipinskiRuleChecker + MolecularDescriptorCalculator
            # 适配：LipinskiRuleChecker / MolecularDescriptorCalculator 真实 schema 要求 smiles；
            #      用 ${prev.output.smiles} 从 step1 输出中提取 SMILES，形成真正的流水线
            SkillBinding(
                skill_id="molecular_property_profiling",
                name="分子特性全面分析",
                description="全面的分子特性分析，涵盖基本信息、疏水性、氢键、结构复杂性、拓扑、药物相似性等",
                summary="组合 3 个工具完成分子特性全面分析",
                introduction=(
                    "该 SKILL 依次调用 ChemicalStructureAnalyzer（结构分析）、LipinskiRuleChecker"
                    "（Lipinski 规则检查）和 MolecularDescriptorCalculator（描述符计算），"
                    "step1 解析出的 SMILES 自动作为 step2/step3 的输入，"
                    "输出涵盖结构、成药性、描述符等多维度的分子特性画像。"
                ),
                features=[
                    "化学结构分析（SMILES、分子式、分子量、原子数）",
                    "Lipinski 规则检查（成药性评估）",
                    "高级分子描述符计算",
                    "多维度的分子特性画像",
                ],
                use_cases=[
                    "候选分子的综合特性评估",
                    "药物发现中的成药性筛选",
                    "分子性质预测的特征输入",
                ],
                pipeline=[
                    SkillPipelineStep(
                        step_id="step1_structure",
                        server_id="28",
                        tool_name="ChemicalStructureAnalyzer",
                        input_mapping={"compound_name": "${input.compound_name}"},
                        description="分析化学结构",
                    ),
                    SkillPipelineStep(
                        step_id="step2_lipinski",
                        server_id="28",
                        tool_name="LipinskiRuleChecker",
                        input_mapping={"smiles": "${prev.output.smiles}"},
                        description="检查 Lipinski 规则",
                    ),
                    SkillPipelineStep(
                        step_id="step3_descriptors",
                        server_id="28",
                        tool_name="MolecularDescriptorCalculator",
                        input_mapping={"smiles": "${prev.output.smiles}"},
                        description="计算分子描述符",
                    ),
                ],
                risk_level=SkillRiskLevel.A,
                provider="上海人工智能实验室",
                capability_refs=["polymer_property_prediction_v1", "crystal_candidate_generation_v1"],
                ecml_steps=[2, 4],
                test_input={"compound_name": "ethanol"},
                official=True,
            ),
            # 6. chemical-structure-analysis
            # 官方组合：NameToSMILES + SMILESToWeight
            # 适配：NameToSMILES (server 31) 实测对所有输入返回 "Could not find"（远端故障），
            #      替换为功能等价的 ChemicalStructureAnalyzer (server 28)（按化合物名返回
            #      SMILES、分子式、分子量等完整结构信息），并将 step1 输出的 SMILES
            #      自动传递给 step2 的 SMILESToWeight，形成真正的流水线
            SkillBinding(
                skill_id="chemical_structure_analysis",
                name="化学结构分析",
                description="从化合物名称分析化学结构以检索 SMILES、分子式、分子量和 LogP 值",
                summary="组合 2 个工具从名称解析化学结构",
                introduction=(
                    "该 SKILL 先通过 ChemicalStructureAnalyzer 将化合物名称解析为 SMILES、"
                    "分子式等结构信息，再将解析出的 SMILES 自动传递给 SMILESToWeight 计算分子量，"
                    "为后续分析提供基础结构信息。"
                    "（官方原版使用 NameToSMILES，因远端工具故障已适配为 ChemicalStructureAnalyzer。）"
                ),
                features=[
                    "化合物名称到 SMILES 的转换",
                    "分子量计算",
                    "基础结构信息获取",
                ],
                use_cases=[
                    "化合物结构信息的快速查询",
                    "实验设计前的结构确认",
                    "候选分子的标识对齐",
                ],
                pipeline=[
                    SkillPipelineStep(
                        step_id="step1_name_to_smiles",
                        server_id="28",
                        tool_name="ChemicalStructureAnalyzer",
                        input_mapping={"compound_name": "${input.compound_name}"},
                        description="解析化合物结构（含 SMILES）",
                    ),
                    SkillPipelineStep(
                        step_id="step2_weight",
                        server_id="31",
                        tool_name="SMILESToWeight",
                        input_mapping={"smiles": "${prev.output.smiles}"},
                        description="计算分子量",
                    ),
                ],
                risk_level=SkillRiskLevel.A,
                provider="上海人工智能实验室",
                capability_refs=["literature_researcher_v1", "crystal_candidate_generation_v1"],
                ecml_steps=[1, 2],
                test_input={"compound_name": "ethanol"},
                official=True,
            ),
            # 7. chemical_structure_comparison
            # 官方组合：NameToSMILES + MolSimilarity + search_pubchem_by_name
            # 适配：
            # - NameToSMILES (server 31) 远端故障，替换为 ChemicalStructureAnalyzer (server 28)
            # - MolSimilarity 真实 schema 要求 smiles_pair（点分隔字符串 "SMILES1.SMILES2"），
            #   非 smiles1/smiles2 两个参数
            SkillBinding(
                skill_id="chemical_structure_comparison",
                name="化学结构比较",
                description="比较化学结构：获取 SMILES、分析结构、计算相似性并检查 PubChem 记录",
                summary="组合 3 个工具完成化学结构比较",
                introduction=(
                    "该 SKILL 组合了 ChemicalStructureAnalyzer、MolSimilarity 和 "
                    "search_pubchem_by_name 三个工具，完成化学结构的解析、相似度计算和 "
                    "PubChem 记录查询，为化学信息学研究提供完整的比较流程。"
                    "（官方原版使用 NameToSMILES，因远端故障已适配为 ChemicalStructureAnalyzer；"
                    "MolSimilarity 的 smiles1/smiles2 已修正为 schema 要求的 smiles_pair。）"
                ),
                features=[
                    "化合物名称到 SMILES 的转换",
                    "分子相似度计算（Tanimoto 系数）",
                    "PubChem 记录查询",
                ],
                use_cases=[
                    "候选分子的相似性筛选",
                    "化学信息学中的结构比较",
                    "化合物新颖性评估",
                ],
                pipeline=[
                    SkillPipelineStep(
                        step_id="step1_name_to_smiles",
                        server_id="28",
                        tool_name="ChemicalStructureAnalyzer",
                        input_mapping={"compound_name": "${input.compound_name}"},
                        description="解析化合物结构（含 SMILES）",
                    ),
                    SkillPipelineStep(
                        step_id="step2_similarity",
                        server_id="31",
                        tool_name="MolSimilarity",
                        input_mapping={"smiles_pair": "${input.smiles_pair}"},
                        description="计算分子相似度",
                    ),
                    SkillPipelineStep(
                        step_id="step3_pubchem",
                        server_id="8",
                        tool_name="search_pubchem_by_name",
                        input_mapping={"name": "${input.compound_name}"},
                        description="查询 PubChem 记录",
                    ),
                ],
                risk_level=SkillRiskLevel.A,
                provider="上海人工智能实验室",
                capability_refs=["literature_researcher_v1", "crystal_candidate_generation_v1"],
                ecml_steps=[1, 2],
                test_input={"compound_name": "ethanol", "smiles_pair": "CCO.CC"},
                official=True,
            ),
            # 8. smiles-to-cas-conversion
            SkillBinding(
                skill_id="smiles_to_cas_conversion",
                name="SMILES 转 CAS 号",
                description="使用材料信息学工具将 SMILES 字符串转换为 CAS 登记号，以识别化学物质",
                summary="调用 SciToolAgent-Mat 将 SMILES 转为 CAS 号",
                introduction=(
                    "该 SKILL 调用 SciToolAgent-Mat 工具集中的 SMILESToCAS 工具，"
                    "将 SMILES 字符串转换为 CAS 登记号，为化学物质的标识对齐提供支持。"
                ),
                features=[
                    "SMILES 到 CAS 号的精确转换",
                    "化学物质标识统一",
                ],
                use_cases=[
                    "候选材料标识的统一对齐与登记",
                    "化学物质的身份确认",
                    "实验记录的标准化",
                ],
                pipeline=[
                    SkillPipelineStep(
                        step_id="step1_smiles_to_cas",
                        server_id="30",
                        tool_name="SMILESToCAS",
                        input_mapping={"smiles": "${input.smiles}"},
                        description="SMILES 转 CAS 号",
                    ),
                ],
                risk_level=SkillRiskLevel.A,
                provider="上海人工智能实验室",
                capability_refs=["crystal_candidate_generation_v1", "polymer_candidate_generation_v1"],
                ecml_steps=[2, 6],
                test_input={"smiles": "CCO"},
                official=True,
            ),
        ]
        for skill in skills:
            # 计算 server_count
            unique_servers = {step.server_id for step in skill.pipeline}
            skill.server_count = len(unique_servers)
            self._skills[skill.skill_id] = skill

    def get(self, skill_id: str) -> SkillBinding | None:
        return self._skills.get(skill_id)

    def list_all(self) -> list[SkillBinding]:
        return list(self._skills.values())

    def list_enabled(self) -> list[SkillBinding]:
        return [s for s in self._skills.values() if s.enabled]

    def set_enabled(self, skill_id: str, enabled: bool) -> SkillBinding:
        skill = self._skills.get(skill_id)
        if skill is None:
            raise KeyError(f"SKILL '{skill_id}' not found")
        skill.enabled = enabled
        return skill
