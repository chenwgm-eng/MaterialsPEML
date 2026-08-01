"""SCP Catalog — registry of approved SCP tool bindings."""

from __future__ import annotations
from enum import Enum
from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    A = "A"  # 化学结构转换、描述符 - 可自动调用
    B = "B"  # 毒理、ADMET、文献 - 可自动调用，结果标识"辅助证据"
    C = "C"  # 分子对接、蛋白 - 默认禁用，管理员白名单启用
    D = "D"  # 实验、采购、设备操作 - 禁止


class ToolBinding(BaseModel):
    internal_name: str
    enabled: bool = False
    risk_level: RiskLevel = RiskLevel.B
    server_id: str = ""
    remote_tool_name: str = ""
    server_url: str = ""
    description: str = ""
    # 中文一句话描述（卡片/表格用）
    summary: str = ""
    # 简介：能力概述与背景（多行文本）
    introduction: str = ""
    # 特点：核心能力清单
    features: list[str] = Field(default_factory=list)
    # 用途：典型应用场景
    use_cases: list[str] = Field(default_factory=list)
    # 关联的能力契约 ID 列表（显式建立工具 ↔ 能力契约关系，供前端调用关系视图使用）
    capability_refs: list[str] = Field(default_factory=list)
    provider: str = ""
    tool_count: int | None = None
    allowed_roles: list[str] = Field(default_factory=lambda: ["admin", "pm", "researcher"])
    ecml_steps: list[int] = Field(default_factory=list)
    timeout_seconds: int = 60
    input_mapping: str = ""
    output_mapping: str = ""


class SCPCatalog:
    """Registry of approved SCP tool bindings."""

    def __init__(self):
        self._bindings: dict[str, ToolBinding] = {}
        self._init_standard_bindings()

    def _init_standard_bindings(self):
        # 5 个能力级 SCP 绑定：映射到具体 Intern Discovery SCP server
        # 按 BatteryPEML_Lab_V1.2 设计文档第 3 节能力-服务器映射
        capability_bindings = [
            # (internal_name, risk, ecml_steps, input_mapping, server_id, remote_tool_name, server_url, provider, description)
            # remote_tool_name 必须是远端 server 上真实存在的工具名（而非 server 级 internal_name），
            # 否则生产路径（不经 _remote_tool_name 覆盖）会调用失败。
            ("scp_molecule_descriptors", RiskLevel.A, [2, 4], "molecule_descriptor_v1",
             "31", "SMILESToWeight",
             "https://scp.intern-ai.org.cn/api/v1/mcp/31/SciToolAgent-Chem",
             "浙江大学", "分子描述符计算（SMILES 转换、分子量、描述符）"),
            ("scp_toxicity_assessment", RiskLevel.B, [3], "toxicity_v1",
             "", "", "",
             "内部 LLM", "毒性 / ADMET / 安全性评估（远端 SCP server 31 暂无专用 ADMET 工具，调用 LLM 内部能力）"),
            ("scp_literature_search", RiskLevel.B, [1, 2, 6], "literature_search_v1",
             "8", "search_pubchem_by_name",
             "https://scp.intern-ai.org.cn/api/v1/mcp/8/Origene-PubChem",
             "临港实验室", "化合物 / 文献检索"),
            ("scp_protocol_draft", RiskLevel.B, [6], "protocol_draft_v1",
             "", "", "",
             "内部 LLM", "实验协议草案生成（LLM 内部能力，无 SCP 远端）"),
            ("scp_material_transform", RiskLevel.C, [2, 6], "material_transform_v1",
             "30", "SMILESToCAS",
             "https://scp.intern-ai.org.cn/api/v1/mcp/30/SciToolAgent-Mat",
             "浙江大学", "材料信息 / MOF 结构 / 电池材料评估"),
        ]
        # 能力绑定 → 能力契约的显式映射（前端调用关系视图使用）
        # TODO: 后续根据实际业务契约归属细化调整
        capability_refs_map: dict[str, list[str]] = {
            "scp_molecule_descriptors": ["crystal_property_prediction_v1", "polymer_property_prediction_v1"],
            "scp_toxicity_assessment": ["polymer_property_prediction_v1"],
            "scp_literature_search": ["literature_researcher_v1"],
            "scp_protocol_draft": ["experiment_analyst_v1"],
            "scp_material_transform": ["crystal_candidate_generation_v1", "polymer_candidate_generation_v1"],
        }
        # 能力级绑定的中文详情（ToolsHub 卡片/详情抽屉使用）
        capability_detail_map: dict[str, dict] = {
            "scp_molecule_descriptors": {
                "summary": "分子描述符计算",
                "description": (
                    "解决候选分子从结构表示到可计算特征的转换问题：将 SMILES 等结构输入解析后，"
                    "计算分子量与常用理化描述符，为性质预测与高通量筛选提供标准化特征输入。"
                ),
                "features": [
                    "SMILES 等化学结构表示的解析与格式互转",
                    "分子量及基础理化描述符计算",
                    "输出结构化特征，可直接接入性质预测流程",
                    "仅限结构转换与描述符计算，不含量子化学级精度计算",
                ],
                "use_cases": [
                    "固态电解质候选分子的批量描述符计算",
                    "聚合物单体与添加剂的结构特征提取",
                    "性质预测模型的输入特征生成",
                    "候选分子库的高通量初筛",
                ],
            },
            "scp_toxicity_assessment": {
                "summary": "毒性与安全性评估",
                "description": (
                    "在候选材料进入实验阶段前评估其潜在毒性、安全风险与环境影响，辅助研发决策与合规预审。"
                    "当前远端 SCP 暂无专用评估工具，调用 LLM 内部知识能力给出参考性结论。"
                ),
                "features": [
                    "基于 LLM 内部知识的毒性 / ADMET 类安全性分析",
                    "输出结果仅作辅助证据，需在结论中明确标识",
                    "不构成合规或安全认证结论",
                    "无远端专用工具，覆盖范围受模型知识限制",
                ],
                "use_cases": [
                    "电解液与添加剂候选的安全风险初筛",
                    "固态电解质前驱体的毒性评估",
                    "实验方案的安全合规预审",
                ],
            },
            "scp_literature_search": {
                "summary": "化合物与文献检索",
                "description": (
                    "解决研发过程中的化合物信息与公开文献证据检索问题：按名称或结构查询 PubChem 等"
                    "公开数据库，为候选材料调研提供背景资料与物性参考。"
                ),
                "features": [
                    "按化合物名称检索 PubChem 公开数据库",
                    "返回化合物基础信息与公开物性数据",
                    "仅覆盖公开数据源，不含付费文献全文",
                    "检索结果需人工研判后方可引用",
                ],
                "use_cases": [
                    "候选电解质材料的背景调研",
                    "前驱体与试剂的物性数据查证",
                    "文献调研阶段的证据收集",
                ],
            },
            "scp_protocol_draft": {
                "summary": "实验协议草案生成",
                "description": (
                    "根据实验目标与约束条件自动生成实验协议（SOP）草案，覆盖材料配比、工艺步骤与表征安排，"
                    "减少人工起草工作量。基于 LLM 内部能力生成，无 SCP 远端服务。"
                ),
                "features": [
                    "按实验目标生成结构化 SOP 草案",
                    "覆盖配料、合成、表征等常规湿实验环节",
                    "草案须由实验人员审核后方可执行",
                    "不直接对接设备控制系统",
                ],
                "use_cases": [
                    "固态电解质合成实验方案起草",
                    "电化学测试流程模板生成",
                    "批次实验操作步骤的标准化",
                ],
            },
            "scp_material_transform": {
                "summary": "材料信息与结构转换",
                "description": (
                    "解决材料标识与结构数据的互查互转问题：支持 SMILES 到 CAS 号等标识转换，"
                    "并可查询 MOF 结构解析与电池材料评估等材料信息，辅助候选材料的数据对齐与查证。"
                ),
                "features": [
                    "SMILES 与 CAS 号等材料标识互转",
                    "MOF 结构解析与材料信息查询",
                    "电池材料相关评估数据查询",
                    "C 级风险：默认禁用，需管理员显式启用",
                ],
                "use_cases": [
                    "候选材料标识的统一对齐与登记",
                    "MOF / 晶体材料的结构信息查询",
                    "电池材料公开评估数据查证",
                ],
            },
        }
        for name, risk, steps, mapping, srv_id, remote_name, srv_url, provider, desc in capability_bindings:
            # C/D 级默认禁用，需管理员显式启用；B/A 级且有 server 映射的才默认启用
            default_enabled = (
                risk not in (RiskLevel.C, RiskLevel.D)
                and bool(srv_id)
            )
            detail = capability_detail_map.get(name, {})
            self._bindings[name] = ToolBinding(
                internal_name=name,
                enabled=default_enabled,
                risk_level=risk,
                ecml_steps=steps,
                input_mapping=mapping,
                output_mapping=mapping,
                server_id=srv_id,
                remote_tool_name=remote_name,
                server_url=srv_url,
                provider=provider,
                description=detail.get("description", desc),
                summary=detail.get("summary", ""),
                features=detail.get("features", []),
                use_cases=detail.get("use_cases", []),
                capability_refs=capability_refs_map.get(name, []),
            )

        # 7 个默认 Intern Discovery SCP server 绑定，默认启用
        # 风险等级按设计文档 BatteryEMCL_Lab_V1.2_统一菜单与MCP_SCP可维护平台详细设计方案.md 第3节
        # server 级绑定默认启用的远端工具（已探测验证可用）。
        # 这些绑定代表整台 SCP server 的入口；生产调用时应由调用方通过
        # _remote_tool_name 指定具体远端工具，此处仅作为未指定时的兜底。
        server_default_remote_tools: dict[str, str] = {
            "scp_scitool_chem": "SMILESToWeight",
            "scp_scigraph_material": "query_cypher",
            "scp_scitool_mat": "SMILESToCAS",
            "scp_chem_reaction": "calculate_pH_from_pOH",
            "scp_origene_pubchem": "search_pubchem_by_name",
            "scp_origene_chembl": "search_assay",
            "scp_materials_mechanics": "calculate_material_density",
            "scp_unit_conversion": "convert_length_to_meters",
            "scp_data_analysis": "calculate_absolute_error",
            "scp_intern_agent": "ChemicalStructureAnalyzer",
            "scp_scigraph": "query_cypher",
        }
        # server 级绑定 → ECML 步骤映射（与 ECML 7 步对齐：1=路由 2=候选生成
        # 3=合成/工业化 4=性质预测 5=DFT 验证 6=实验分析 7=反馈学习）
        # 用于 ToolCatalog.allowed_ecml_steps 门禁与前端调用关系展示。
        server_ecml_steps: dict[str, list[int]] = {
            "scp_scitool_chem": [2, 4],         # 候选生成、性质预测的化学计算
            "scp_scigraph_material": [1, 2, 4], # 知识检索、候选生成、性质预测
            "scp_scitool_mat": [2, 4, 5],       # 候选生成、性质预测、DFT 验证
            "scp_chem_reaction": [3, 6],        # 合成反应计算、实验分析
            "scp_origene_pubchem": [1, 2],      # 化合物检索、候选生成
            "scp_origene_chembl": [1, 2],       # 药物检索、候选生成
            "scp_materials_mechanics": [4, 5],  # 力学性质预测、DFT 验证
            "scp_unit_conversion": [3, 4, 6],   # 合成、预测、实验数据单位换算
            "scp_data_analysis": [4, 6, 7],     # 预测数据处理、实验分析、反馈决策
            "scp_intern_agent": [1, 7],         # 路由调研、反馈综述
            "scp_scigraph": [1, 2, 4],          # 跨学科知识检索、候选生成、性质预测
        }
        # server 级绑定 → 能力契约的语义兜底映射（供调用关系视图使用）
        # TODO: 随着能力契约细化，建议按 server 内真实工具拆分映射
        server_capability_refs: dict[str, list[str]] = {
            "scp_scitool_chem": [
                "crystal_property_prediction_v1",
                "polymer_property_prediction_v1",
                "synthesis_planning_askcos_v1",
            ],
            "scp_scigraph_material": [
                "literature_researcher_v1",
                "cross_scale_prediction_v1",
            ],
            "scp_scitool_mat": [
                "crystal_property_prediction_v1",
                "polymer_property_prediction_v1",
                "dft_verification_v1",
                "crystal_candidate_generation_v1",
                "polymer_candidate_generation_v1",
            ],
            "scp_chem_reaction": [
                "synthesis_planning_askcos_v1",
                "ecml_closed_loop_v1",
            ],
            "scp_origene_pubchem": [
                "literature_researcher_v1",
                "crystal_property_prediction_v1",
                "polymer_property_prediction_v1",
            ],
            "scp_origene_chembl": [
                "literature_researcher_v1",
                "polymer_property_prediction_v1",
            ],
            "scp_materials_mechanics": [
                "dft_verification_v1",
                "crystal_property_prediction_v1",
                "polymer_property_prediction_v1",
            ],
            "scp_unit_conversion": [
                "crystal_property_prediction_v1",
                "polymer_property_prediction_v1",
                "experiment_analyst_v1",
            ],
            "scp_data_analysis": [
                "experiment_analyst_v1",
                "cross_scale_prediction_v1",
            ],
            "scp_intern_agent": [
                "deep_research_v1",
                "literature_researcher_v1",
                "cross_scale_prediction_v1",
            ],
            "scp_scigraph": [
                "literature_researcher_v1",
                "cross_scale_prediction_v1",
            ],
        }
        default_servers = [
            {
                "internal_name": "scp_scitool_chem",
                "server_id": "31",
                "remote_tool_name": server_default_remote_tools["scp_scitool_chem"],
                "risk_level": RiskLevel.B,
                "provider": "浙江大学",
                "server_url": "https://scp.intern-ai.org.cn/api/v1/mcp/31/SciToolAgent-Chem",
                "ecml_steps": server_ecml_steps["scp_scitool_chem"],
                "description": "化学计算与分子模拟工具集 — 结构转换/反应预测/分子描述符/ML 建模",
                "summary": "面向化学信息学、药物设计、反应工程及计算化学领域的综合性工具库",
                "introduction": (
                    "SciToolAgent-Chem 由浙江大学开发，整合分子结构分析、化学反应预测、分子描述符计算、"
                    "指纹生成、机器学习建模等多种功能，为化学研究与药物发现提供全流程计算支持。"
                    "工具集涵盖 169 个原子级工具，覆盖化学结构格式互转、分子性质与描述符计算、"
                    "化学反应预测与逆合成路径规划、分子相似度与子结构匹配、官能团识别与立体化学分配、"
                    "安全性与爆炸性评估、分子聚类与机器学习分类等核心能力。"
                ),
                "features": [
                    "化学结构格式互转（SMILES / InChI / CAS / SELFIES）",
                    "分子性质与描述符计算（分子量、拓扑指纹、电子描述符、TPSA）",
                    "化学反应预测与逆合成路径规划",
                    "分子相似度与子结构匹配",
                    "官能团识别与立体化学分配",
                    "安全性与爆炸性评估",
                    "分子聚类与机器学习分类（MLP / AdaBoost / 随机森林）",
                ],
                "use_cases": [
                    "药物发现（虚拟筛选、先导化合物优化、成药性评估）",
                    "化学信息学（SAR 研究、QSAR 建模）",
                    "反应工程（反应预测、路径规划、产率优化）",
                    "材料化学（聚合物设计、催化剂筛选）",
                    "计算化学（分子描述符计算、量子化学预处理）",
                    "专利分析（化合物检索、新颖性评估）",
                ],
                "tool_count": 169,
                "capability_refs": server_capability_refs["scp_scitool_chem"],
            },
            {
                "internal_name": "scp_scigraph_material",
                "server_id": "40",
                "remote_tool_name": server_default_remote_tools["scp_scigraph_material"],
                "risk_level": RiskLevel.B,
                "provider": "浙江大学",
                "server_url": "https://scp.intern-ai.org.cn/api/v1/mcp/40/SciGraph-Material",
                "ecml_steps": server_ecml_steps["scp_scigraph_material"],
                "description": "物质科学统一知识查询服务 — 跨图谱知识检索与实体关系查询",
                "summary": "面向物质科学研究的统一知识查询服务，集成材料、化学、功能材料等多个领域知识图谱",
                "introduction": (
                    "SciGraph-Material 由浙江大学牵头，联合上海人工智能实验室共同打造，"
                    "整合了多个物质科学领域知识图谱，通过统一的 MCP 协议提供访问接口。"
                    "研究人员无需分别对接不同数据源，即可一站式获取跨学科知识。"
                    "以 ElementKG（化学知识图谱）为例：包含约 2309 万个节点、7400 余万条关系，"
                    "涵盖分子、化学反应、实验流程、实验试剂、实验装置、元素等 13 种实体类型，"
                    "通过 97 种关系类型相互连接，形成完整的化学实验与元素知识网络。"
                ),
                "features": [
                    "多图谱覆盖、统一访问接口",
                    "数据规模庞大、知识体系完整（ElementKG 含 2309 万节点、7400 余万条关系）",
                    "跨图谱联合查询，自动聚合并标注来源",
                    "支持 Cypher 查询、节点/关系统计、关系类型查询",
                    "灵活查询、开箱即用，无需本地部署图数据库",
                ],
                "use_cases": [
                    "跨学科知识检索与实体关系查询",
                    "领域知识问答",
                    "AI 辅助科学研究",
                    "实验设计到结果分析的全流程知识查询",
                ],
                "tool_count": 4,
                "capability_refs": server_capability_refs["scp_scigraph_material"],
            },
            {
                "internal_name": "scp_scitool_mat",
                "server_id": "30",
                "remote_tool_name": server_default_remote_tools["scp_scitool_mat"],
                "risk_level": RiskLevel.B,
                "provider": "浙江大学",
                "server_url": "https://scp.intern-ai.org.cn/api/v1/mcp/30/SciToolAgent-Mat",
                "ecml_steps": server_ecml_steps["scp_scitool_mat"],
                "description": "材料信息与计算化学工具集 — MOF/MP/电池材料评估/晶体学计算",
                "summary": "面向材料科学、固体物理、电化学及计算材料学领域的专业化工具库",
                "introduction": (
                    "SciToolAgent-Mat 由浙江大学开发，深度集成 Materials Project 数据库、MOF 结构分析、"
                    "电池材料评估、晶体学计算等功能，为材料设计、性能预测与数据挖掘提供系统化解决方案。"
                    "工具集涵盖 MOF 框架结构解析（晶格参数、分数坐标、拓扑特征）、Materials Project 数据库深度对接"
                    "（材料搜索、带隙/能量/密度查询、电子结构分析、磁性与介电性质获取）、电池材料性能评估"
                    "（工作电压、容量、循环稳定性）、分子热力学与振动性质计算、材料吸附与稳定性预测、"
                    "晶体对称性与键合信息分析等多种核心功能。"
                ),
                "features": [
                    "MOF 框架结构解析（晶格参数、分数坐标、拓扑特征）",
                    "Materials Project 数据库深度对接（材料搜索、带隙/能量/密度查询、电子结构分析、磁性/介电性质）",
                    "电池材料性能评估（工作电压、容量、循环稳定性）",
                    "分子热力学与振动性质计算",
                    "材料吸附与稳定性预测",
                    "晶体对称性与键合信息分析",
                ],
                "use_cases": [
                    "新材料发现（高通量筛选、材料基因组、逆向设计）",
                    "能源材料（电池材料、太阳能材料、储氢材料）",
                    "催化材料（MOF 催化剂、光催化、电催化）",
                    "电子材料（半导体、拓扑绝缘体、超导材料）",
                    "磁性材料（铁磁体、反铁磁体、自旋电子学）",
                    "材料数据挖掘（结构-性质关系、机器学习建模）",
                ],
                "tool_count": 8,
                "capability_refs": server_capability_refs["scp_scitool_mat"],
            },
            {
                "internal_name": "scp_chem_reaction",
                "server_id": "24",
                "remote_tool_name": server_default_remote_tools["scp_chem_reaction"],
                "risk_level": RiskLevel.B,
                "provider": "上海人工智能实验室",
                "server_url": "https://scp.intern-ai.org.cn/api/v1/mcp/24/Chemistry_and_Reaction_Calculations",
                "ecml_steps": server_ecml_steps["scp_chem_reaction"],
                "description": "化学反应计算工具 — 反应参数/动力学/平衡/产率估算",
                "summary": "面向化学实验、反应工程与材料科学领域的一站式综合计算平台 ChemReaction-Tool",
                "introduction": (
                    "化学与反应计算-Tool 由上海人工智能实验室推出，集成化学反应参数计算、溶液分析、"
                    "反应动力学、质量能量平衡核查等功能，支持自动化反应参数求解与智能报告输出，"
                    "极大提升实验设计、反应模拟和工艺优化的效率。工具集包含 105 个工具，覆盖从基础数据计算"
                    "到复杂反应分析的广泛应用，是科研和工程工作者进行化学反应建模与数据处理的理想助手。"
                ),
                "features": [
                    "化学反应参数自动计算（配平、可逆/不可逆过程定量分析）",
                    "物质量与溶液浓度分析（标准溶液配置、稀释倍数、定容）",
                    "反应速率与化学平衡常数求解（零级/一二级及复杂反应动力学）",
                    "质量守恒与能量平衡核查",
                    "反应配比与产率估算（过量/限量试剂、副反应产物）",
                    "环境和溶剂影响分析（温度、压强、溶剂类型）",
                    "工艺放大与实验方案规划",
                    "实验与模拟数据一体化处理（CSV / Excel 兼容）",
                ],
                "use_cases": [
                    "实验设计与反应模拟",
                    "工艺优化与放大",
                    "化学反应建模与数据处理",
                    "能效评估与反应路线优化",
                ],
                "tool_count": 105,
                "capability_refs": server_capability_refs["scp_chem_reaction"],
            },
            {
                "internal_name": "scp_origene_pubchem",
                "server_id": "8",
                "remote_tool_name": server_default_remote_tools["scp_origene_pubchem"],
                "risk_level": RiskLevel.A,
                "provider": "临港实验室",
                "server_url": "https://scp.intern-ai.org.cn/api/v1/mcp/8/Origene-PubChem",
                "ecml_steps": server_ecml_steps["scp_origene_pubchem"],
                "description": "PubChem 化合物检索 — 即查即用、随取随用",
                "summary": "元生 OriGene 深度集成全球最大、开放的化学信息数据库 PubChem 核心检索引擎",
                "introduction": (
                    "Origene-PubChem 由临港实验室牵头，联合上海人工智能实验室、上海交通大学、复旦大学"
                    "及 MIT 等顶尖科研机构共同发布的“元生”（OriGene）系统组件之一，全面嵌入全球最大、"
                    "开放的化学信息数据库 PubChem 核心检索引擎，实现“即查即用、随取随用”的高效科研支持能力。"
                    "在团队构建的首个靶标发现问答基准测试集 TRQA 上的表现显著优于 DeepSeek-R1、OpenAI o3-mini "
                    "等主流基座大模型，靶标发现能力已通过前瞻性实验验证。"
                ),
                "features": [
                    "深度集成 PubChem 核心检索引擎",
                    "支持 SMILES / 化合物名称多维度查询",
                    "即查即用、随取随用",
                    "39 个专用检索工具",
                ],
                "use_cases": [
                    "化合物信息检索",
                    "靶标发现与临床转化价值评估",
                    "化学信息查询",
                    "AI 辅助药物研发",
                ],
                "tool_count": 39,
                "capability_refs": server_capability_refs["scp_origene_pubchem"],
            },
            {
                "internal_name": "scp_origene_chembl",
                "server_id": "4",
                "remote_tool_name": server_default_remote_tools["scp_origene_chembl"],
                "risk_level": RiskLevel.C,
                "provider": "临港实验室",
                "server_url": "https://scp.intern-ai.org.cn/api/v1/mcp/4/Origene-ChEMBL",
                "ecml_steps": server_ecml_steps["scp_origene_chembl"],
                "description": "ChEMBL 小分子药物与生物活性检索 — 即查即用、随取随用",
                "summary": "元生 OriGene 深度集成大型、开放的小分子药物与生物活性数据库 ChEMBL 核心检索引擎",
                "introduction": (
                    "Origene-ChEMBL 由临港实验室牵头发布，作为“元生”（OriGene）系统组件之一，"
                    "深度集成大型、开放的小分子药物与生物活性数据库 ChEMBL 核心检索引擎，"
                    "实现“即查即用、随取随用”的高效检索能力，为药物发现与靶标研究提供专业数据支撑。"
                ),
                "features": [
                    "深度集成 ChEMBL 核心检索引擎",
                    "支持小分子药物与生物活性数据多维查询",
                    "即查即用、随取随用",
                    "58 个专用检索工具",
                ],
                "use_cases": [
                    "小分子药物检索",
                    "生物活性数据查询",
                    "药物发现与靶标研究",
                    "成药性评估",
                ],
                "tool_count": 58,
                "capability_refs": server_capability_refs["scp_origene_chembl"],
            },
            {
                "internal_name": "scp_materials_mechanics",
                "server_id": "20",
                "remote_tool_name": server_default_remote_tools["scp_materials_mechanics"],
                "risk_level": RiskLevel.B,
                "provider": "上海人工智能实验室",
                "server_url": "https://scp.intern-ai.org.cn/api/v1/mcp/20/Materials_Mechanics_and_Fracture_Analysis",
                "ecml_steps": server_ecml_steps["scp_materials_mechanics"],
                "description": "材料力学与断裂分析工具集 — 应力应变/断裂判据/残余应力",
                "summary": "面向工程结构分析、材料性能评估与失效预测的一站式工具集 MaterialStrength-Tool",
                "introduction": (
                    "材料力学与断裂分析-Tool 由上海人工智能实验室推出，坚持“开箱即用”的设计理念，"
                    "深度集成应力应变分析、力学性能参数计算、断裂判据评估、界面强度分析、"
                    "残余应力与长度收缩模拟等核心功能。平台支持自动化任务调度、批量数据分析与智能报告生成，"
                    "极大提升工程材料建模、结构优化与物理量精准计算的效率，为科研人员与工程师在材料设计、"
                    "结构安全评估及复杂工况下的失效预警等领域提供强大且便捷的技术支撑。"
                ),
                "features": [
                    "应力与应变自动计算（多场景结构件分布与集中效应评估）",
                    "结构安全性与断裂判据分析（临界应力强度、断裂韧性）",
                    "弹性与塑性参数求解（弹性模量、屈服强度、残余应力）",
                    "界面强度与微观损伤评估（粘结界面/复合材料细观结构）",
                    "过程变形与残余应力估算（冷却、成型、焊接等制造过程）",
                ],
                "use_cases": [
                    "工程材料建模与结构优化",
                    "零部件设计与极限承载力分析",
                    "材料失效预测与结构安全评估",
                    "复杂工况下的失效预警",
                ],
                "tool_count": 107,
                "capability_refs": server_capability_refs["scp_materials_mechanics"],
            },
            {
                "internal_name": "scp_unit_conversion",
                "server_id": "27",
                "remote_tool_name": server_default_remote_tools["scp_unit_conversion"],
                "risk_level": RiskLevel.A,
                "provider": "上海人工智能实验室",
                "server_url": "https://scp.intern-ai.org.cn/api/v1/mcp/27/Physical_Quantities_Conversion",
                "ecml_steps": server_ecml_steps["scp_unit_conversion"],
                "description": "物理量与单位换算工具 — 单位转换/物理常数/维度校验",
                "summary": "面向科学计算、工程分析与实验研究的一体化单位处理工具库",
                "introduction": (
                    "物理量与单位换算-Tool 由上海人工智能实验室推出，集成常见及特殊物理量的单位转换、"
                    "国际与英制单位互换、物理常数查找、数量级换算、物理维度校验等功能。"
                    "工具集包含 81 个工具，覆盖长度、质量、压力、电流、电容、体积等多类物理量的"
                    "精确换算，为跨学科数据对齐与单位标准化提供基础支持。"
                ),
                "features": [
                    "常见及特殊物理量的单位转换（长度、质量、压力、电流、电容、体积等）",
                    "国际单位制与英制单位互转",
                    "物理常数查找与数量级换算",
                    "物理维度校验",
                ],
                "use_cases": [
                    "实验数据单位标准化与对齐",
                    "跨学科数据换算与统一",
                    "工程分析中的单位转换",
                    "实验报告中的单位规范化",
                ],
                "tool_count": 81,
                "capability_refs": server_capability_refs["scp_unit_conversion"],
            },
            {
                "internal_name": "scp_data_analysis",
                "server_id": "26",
                "remote_tool_name": server_default_remote_tools["scp_data_analysis"],
                "risk_level": RiskLevel.A,
                "provider": "上海人工智能实验室",
                "server_url": "https://scp.intern-ai.org.cn/api/v1/mcp/26/Data_processing_and_statistical_analysis",
                "ecml_steps": server_ecml_steps["scp_data_analysis"],
                "description": "数据处理与统计分析工具 — 数据清洗/拟合/误差评估/分布分析",
                "summary": "面向科学研究、工程实践与数据驱动决策的统计分析工具库",
                "introduction": (
                    "数据处理与统计分析-Tool 由上海人工智能实验室推出，集成数据清洗、筛选、归一化、"
                    "异常值检测、数据拟合与插值、误差评估、分布分析、相关性计算等核心统计与数据分析函数。"
                    "工具集包含 41 个工具，为实验数据处理、结果分析与决策支持提供系统化方案。"
                ),
                "features": [
                    "数据清洗、筛选与归一化",
                    "异常值检测与处理",
                    "数据拟合与插值",
                    "误差评估（绝对误差、相对误差、百分比误差）",
                    "分布分析与相关性计算",
                    "科学计数法格式化",
                ],
                "use_cases": [
                    "实验数据的统计分析与误差评估",
                    "ECML 闭环中的数据处理与归一化",
                    "跨尺度分析中的数据拟合与插值",
                    "实验报告中的统计指标计算",
                ],
                "tool_count": 41,
                "capability_refs": server_capability_refs["scp_data_analysis"],
            },
            {
                "internal_name": "scp_intern_agent",
                "server_id": "28",
                "remote_tool_name": server_default_remote_tools["scp_intern_agent"],
                "risk_level": RiskLevel.B,
                "provider": "上海人工智能实验室",
                "server_url": "https://scp.intern-ai.org.cn/api/v1/mcp/28/InternAgent",
                "ecml_steps": server_ecml_steps["scp_intern_agent"],
                "description": "InternAgent 通用科研智能体 — 深度研究/结构化知识流/科研报告生成",
                "summary": "覆盖化学、生物、材料、药物等多领域的百余个科学计算工具体系",
                "introduction": (
                    "InternAgent 由上海人工智能实验室自建，覆盖化学、生物学、材料科学、药物发现以及"
                    "多领域交叉应用的百余个科学计算工具体系。核心工具 InternAgent-DeepResearch 面向"
                    "复杂科研任务，通过动态结构化知识流实现智能搜索与规划，将研究问题拆解为具备依赖"
                    "关系的子任务，执行并行探索、层级分解与自适应优化，最终生成结构严谨、内容翔实、"
                    "逻辑自洽的科研报告。"
                ),
                "features": [
                    "化学结构分析（SMILES 解析、分子量、官能团、立体化学）",
                    "分子描述符计算与 Lipinski 规则检查",
                    "分子相似度比较与指纹生成",
                    "环系统分析与构象分析",
                    "InternAgent-DeepResearch：复杂科研任务的智能拆解与报告生成",
                ],
                "use_cases": [
                    "复杂科研问题的深度研究与综述生成",
                    "候选材料的综合分析与评估",
                    "跨学科知识检索与关联分析",
                    "科研报告的结构化生成",
                ],
                "tool_count": 115,
                "capability_refs": server_capability_refs["scp_intern_agent"],
            },
            {
                "internal_name": "scp_scigraph",
                "server_id": "37",
                "remote_tool_name": server_default_remote_tools["scp_scigraph"],
                "risk_level": RiskLevel.B,
                "provider": "浙江大学",
                "server_url": "https://scp.intern-ai.org.cn/api/v1/mcp/37/SciGraph",
                "ecml_steps": server_ecml_steps["scp_scigraph"],
                "description": "通用科学知识图谱 — 多学科知识检索/实体关系查询/领域问答",
                "summary": "面向科学研究的统一知识查询服务，集成生命科学、地球科学、材料科学、数学物理等多学科知识图谱",
                "introduction": (
                    "SciGraph 由浙江大学开发，集成生命科学、地球科学、材料科学、数学物理等多个学科领域的"
                    "知识图谱数据，通过统一的 MCP 协议提供访问接口。支持跨学科知识检索、实体关系查询、"
                    "领域知识问答等操作，为 AI 辅助科学研究提供强大的知识支撑。"
                    "与 SciGraph-Material（物质科学专用）互补，SciGraph 覆盖更广泛的学科领域。"
                ),
                "features": [
                    "多学科知识图谱覆盖（生命科学、地球科学、材料科学、数学物理）",
                    "Cypher 查询与节点/关系统计",
                    "跨图谱联合查询，自动聚合并标注来源",
                    "实体关系查询与领域知识问答",
                ],
                "use_cases": [
                    "跨学科知识检索与实体关系查询",
                    "领域知识问答与辅助决策",
                    "AI 辅助科研与证据收集",
                    "与 SciGraph-Material 互补的通用知识查询",
                ],
                "tool_count": 4,
                "capability_refs": server_capability_refs["scp_scigraph"],
            },
        ]
        for server in default_servers:
            # C/D 级 server 绑定默认禁用
            default_enabled = server.get("risk_level") not in (RiskLevel.C, RiskLevel.D)
            self._bindings[server["internal_name"]] = ToolBinding(
                enabled=default_enabled,
                **server,
            )

    def get(self, internal_name: str) -> ToolBinding | None:
        return self._bindings.get(internal_name)

    def list_all(self) -> list[ToolBinding]:
        return list(self._bindings.values())

    def list_enabled(self) -> list[ToolBinding]:
        return [b for b in self._bindings.values() if b.enabled]

    def enable(self, internal_name: str, server_id: str, remote_tool_name: str):
        binding = self._bindings.get(internal_name)
        if binding is None:
            raise KeyError(f"Tool binding '{internal_name}' not found")
        binding.enabled = True
        binding.server_id = server_id
        binding.remote_tool_name = remote_tool_name

    def disable(self, internal_name: str):
        binding = self._bindings.get(internal_name)
        if binding is None:
            raise KeyError(f"Tool binding '{internal_name}' not found")
        binding.enabled = False

    def set_enabled(self, internal_name: str, enabled: bool) -> ToolBinding:
        """启用或禁用指定绑定，返回更新后的绑定。"""
        binding = self._bindings.get(internal_name)
        if binding is None:
            raise KeyError(f"Tool binding '{internal_name}' not found")
        binding.enabled = enabled
        return binding

    def update(self, internal_name: str, **kwargs):
        binding = self._bindings.get(internal_name)
        if binding is None:
            raise KeyError(f"Tool binding '{internal_name}' not found")
        allowed = set(binding.model_fields.keys())
        for key, value in kwargs.items():
            if key not in allowed:
                raise ValueError(
                    f"字段 '{key}' 不在 ToolBinding 可更新字段列表中，"
                    f"允许更新的字段：{', '.join(sorted(allowed))}"
                )
            setattr(binding, key, value)