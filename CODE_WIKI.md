# BatteryEMCL Lab — Code Wiki

> AI 驱动的电池材料研发闭环系统（基于 OpenScience Agent 架构）
>
> 版本：v2.1.0 ｜ 文档更新日期：2026-07-28
>
> 对标产品：[Deep Principle](https://www.deepprinciple.com/) 的 Agent Mira 六大模块能力
>
> **v2.0 重大变更**：全库迁移至 PostgreSQL（SQLAlchemy 2.0 + psycopg3 + Alembic），新增 MDM 主数据治理、Capability 能力契约、Release Card 放行卡、Value Realization 收益证明、Data Ingest 数据接入五大战略模块，统一 QC 服务入口。
>
> **v2.1 增量变更**：
> - 数据库启用 pgvector 扩展（docker-compose 切换至 `pgvector/pgvector:pg16` 镜像，迁移 0028/0029 将知识资产 embedding 列升级为 `vector(1024)`）
> - 新增 **知识资产层**（`knowledge/asset_store.py` + `credibility.py` + `ingestion.py`）：Paper/Material/Claim 三层资产 + 双维度可信度模型（source_tier × evidence_level）+ 多源采集管道
> - 新增 **业务活动↔Agent↔工具三层映射**（`agent_team/activity_mapping.py` + `mapping_router.py`，迁移 0027）：业务活动必须通过 Agent 调用工具，禁止直接调用大模型
> - 新增 **SKILL 声明式流水线层**（`mcp_tools/skill_catalog.py` + `skill_executor.py`）：组合多个 SCP 工具为顺序 pipeline
> - 新增 **SCP 异步任务系统**（`integrations/scp_task_store.py` + `scp_task_worker.py` + `scp_task_locks.py`，迁移 0026）：长时 SCP 调用走异步 worker + 状态机 + 重试/取消
> - Alembic 迁移由 23 个增至 **29 个**（新增 0024~0029）

---

## 目录

- [1. 项目概述](#1-项目概述)
- [2. 项目整体架构](#2-项目整体架构)
- [3. 目录结构](#3-目录结构)
- [4. 后端模块详解](#4-后端模块详解)
- [5. 前端模块详解](#5-前端模块详解)
- [6. API 端点总览](#6-api-端点总览)
- [7. 数据库与数据存储](#7-数据库与数据存储)
- [8. 依赖关系](#8-依赖关系)
- [9. 项目运行方式](#9-项目运行方式)
- [10. 测试体系](#10-测试体系)
- [11. 关键实现说明与已知限制](#11-关键实现说明与已知限制)
- [附录：关键数据模型速查表](#附录关键数据模型速查表)

---

## 1. 项目概述

### 1.1 项目定位

BatteryEMCL Lab 是一套面向锂电池材料（固态聚合物电解质 + 无机晶体正负极材料）的 AI 驱动研发闭环系统。它以 OpenScience Agent 架构为底座，通过封装整合各领域最成熟的开源模型/工具，构建出对标 Deep Principle Agent Mira 的完整材料研发能力。

系统核心自研部分收敛于 **ECML 八步调度编排逻辑**、**工业化验证层**、**实验全链路管理**、**Agent Team 多智能体协作框架**、**Committee 委员会机制**、**Control Plane 控制平面**、**Hybrid Orchestrator 混合编排**、**湿数据中间件业务规则设计**，以及 v2.0 新增的 **MDM 主数据治理**、**能力契约注册中心**、**实验放行卡** 与 **研发收益证明层**，其余能力均采用开源方案整合落地。

### 1.2 材料体系分类

| 电池组件 | 材料类型 | 表示方法 | 建模引擎 |
|---|---|---|---|
| 正极材料 | 无机晶体 | CIF/POSCAR | CGCNN / M3GNet |
| 负极材料 | 无机晶体 / 碳基 | CIF/POSCAR | CGCNN / M3GNet |
| 固态聚合物电解质 (SPE) | 高分子 | PSMILES | PolymerGNN + polyBERT 指纹 |
| 无机固态电解质 | 无机晶体 | CIF/POSCAR | CGCNN / M3GNet |
| 液态电解质 | 有机小分子 | SMILES | RDKit 描述符 |

### 1.3 能力对标一览

| Deep Principle 能力 | 本系统整合实现 |
|---|---|
| ReactGen (生成) | 多 LLM API 生成 + Materials Project/GNoME 候选库检索 |
| MPA (性质预测) | PolymerGNN（高分子）/ CGCNN + M3GNet（晶体） |
| Reactify (精密计算) | RDKit + PySCF + ASE 三级降级链 |
| ReactControl / ReactBO (筛选优化) | ECML 调度 Agent 内置 Top-K 评分与筛选 + Committee 多委员会评审 |
| ReactNet (合成路径导航) | ASKCOS 开源逆合成规划套件 |
| ReactHTE (实验闭环) | FINDUS / RoboChem-Flex + 湿数据中间件层 |
| ECML 统一范式 | OpenScience Agent runtime + 自定义八步循环编排 |
| 工业化验证 | SMARTS 合规检查 + 物料库匹配 + 成本估算 + BOM/BOP 配方设计 |
| 多智能体协作 | Agent Team 编排框架 + Hybrid Orchestrator + Committee 委员会 |
| 实验室管理 | 任务单创建/审批/数据录入/QC 审核 + 样品/设备/物料全链路 |
| 管控治理 | Control Plane 控制平面（策略引擎/工具网关/预算/可观测性） |
| 能力路由 | CapabilityRouter + ModelRouter + Capability 能力契约注册中心 |
| 研发工作台 | 统一意图入口 + 智能推导子任务 + 计划校验与执行 |
| 主数据治理 | MDM 五阶段（参考字典/主数据/CIMC/工艺/血缘快照） |
| 决策放行 | Release Card 放行卡（六类证据摘要 + 人工责任闭环） |
| 收益证明 | Value Realization（项目基线 + 成本规则 + verified/estimated 收益账单） |

---

## 2. 项目整体架构

### 2.1 架构总览

```text
battery-materials-agent (OpenScience Agent 架构直接扩展)
│
├── 统一研发入口层 = HybridOrchestrator + IntentInterpreter
│   └── 意图解析 → 能力路由 → 模型路由 → 计划校验 → 执行
│
├── Router 层：判断材料类型，路由到高分子分支或晶体分支
│
├── 高分子分支 = PSMILES 工具链 + PolymerGNN + LLM 生成
│   ├── 表示: PSMILES + canonicalize_psmiles + RDKit
│   ├── 生成: 多 LLM API 规则重组 + 分子扩散模型
│   └── 预测: PolymerGNN(微调) + MatterSim-MT
│
├── 晶体分支 = CIF 工具链 + CGCNN/M3GNet + 候选库检索
│   ├── 表示: pymatgen Structure + CIF 解析
│   ├── 生成: Materials Project / GNoME 检索 + 元素替换
│   └── 预测: CGCNN + M3GNet (MatterSim)
│
├── 工业化验证层 = 合规检查 + 成本估算 + 配方设计
│   ├── SMARTS 毒性/合规规则库 + REACH 受限物质核查
│   ├── 物料规格库 (RawMaterialDB) + 供应商匹配
│   ├── 成本模型（原料+设备折旧+人工+能耗+三废）
│   └── BOM/BOP 配方与工艺设计
│
├── 实验全链路 = 任务单 → 审批 → 执行 → 数据录入 → QC 审核
│   ├── ExperimentController（状态机 + 审批引擎）
│   ├── DataMiddleware（湿数据归一化/QC/追溯）
│   └── qc_service（统一 QC 入口 + 决策审计快照）
│
├── ECML 调度引擎 = 八步闭环（设计→预测→合成→验证→实验→分析→学习→决策）
│
├── 治理与决策层
│   ├── Committee 委员会（多角色评审/证据治理/裁决）
│   ├── Release Card 放行卡（委员会结论 → 可执行决策载体）
│   ├── Capability 能力契约（模型版本/适用域/回退链）
│   └── Control Plane 控制平面（策略/预算/可观测性/溯源）
│
├── 数据治理层
│   ├── MDM 主数据治理（P1 参考字典 → P5 血缘快照）
│   ├── Data Ingest 数据接入（Excel/CSV 导入 + 字段映射 + 质量报告）
│   ├── Knowledge 知识资产层（Paper/Material/Claim 三层 + 双维度可信度 + pgvector 向量检索）
│   └── Value Realization 收益证明（基线对照 + 成本核算）
│
├── Agent 工具治理层（v2.1 新增）
│   ├── ActivityMapping 业务活动↔Agent↔工具三层映射（静态绑定 + 能力回退）
│   ├── SKILL 声明式流水线（多 SCP 工具顺序编排，纯配置无代码）
│   └── SCP 异步任务系统（长时调用 worker + 状态机 + 重试/取消）
│
└── 基础设施
    ├── PostgreSQL 统一数据库（SQLAlchemy 2.0 + psycopg3 + Alembic + pgvector）
    ├── LLM Provider 层（legacy / InternLM 双引擎 + token 追踪）
    └── MCP/SCP 工具集成（内部工具 + 外部科学工具发现 + SKILL pipeline）
```

### 2.2 分层职责

| 层 | 核心模块 | 职责 |
|---|---|---|
| 入口层 | `api.py`、`cli.py` | REST API（337+ 直接端点 + 5 子路由）、CLI 命令 |
| 编排层 | `agent.py`、`hybrid/`、`agent_team/` | 单一 Agent 编排、混合研发工作台、多智能体协作 |
| 材料流水线 | `router/`、`representation/`、`generation/`、`prediction/`、`synthesis/`、`verification/` | 材料类型路由 → 表示 → 生成 → 预测 → 合成 → 验证 |
| 工业化层 | `industrialization/` | 合规检查、成本估算、配方设计、物料请求 |
| 实验层 | `experiment/`、`middleware/`、`qc_service.py` | 任务单状态机、审批、样品/设备/物料、湿数据 QC |
| 闭环层 | `ecml/` | 八步迭代闭环调度与状态持久化 |
| 治理层 | `committee/`、`release_card/`、`capability/`、`control_plane/` | 委员会评审、放行卡、能力契约、策略/预算/观测 |
| 数据治理层 | `mdm/`、`data_ingest/`、`knowledge/`、`value_realization/` | 主数据、数据接入、知识资产、收益证明 |
| Agent 工具治理层 | `agent_team/activity_mapping.py`、`mcp_tools/skill_catalog.py`、`integrations/scp_task_*` | 活动↔Agent↔工具映射、SKILL 流水线、SCP 异步任务 |
| 基础设施 | `db.py`、`llm/`、`mcp_tools/`、`auth/`、`audit.py` | 数据库引擎（pgvector）、LLM 提供者、工具集成、认证、审计 |

### 2.3 核心数据流

```text
用户意图 (ResearchWorkbench)
    ↓
IntentInterpreter 意图解析 → CapabilityRouter 能力路由 → ModelRouter 模型选择
    ↓
PlanValidator 计划校验 → HybridOrchestrator 执行计划
    ↓
┌─────────────────────────────────────────────────┐
│ 材料流水线：Router → Representation → Generation │
│   → Prediction → Industrialization → Synthesis   │
└─────────────────────────────────────────────────┘
    ↓
候选材料 (CandidateStore) → Committee 委员会评审
    ↓
Release Card 放行卡（六类证据 + 推荐结论 + 人工责任）
    ↓
实验任务单 (ExperimentController) → 审批 → 湿实验执行
    ↓
DataMiddleware 数据归一化 → qc_service QC 检查 + 审计快照
    ↓
ECML 八步闭环迭代（反馈学习）
    ↓
Value Realization 收益账单（verified/estimated 指标）
```

---

## 3. 目录结构

```text
BatteryEMCL Lab/
├── battery_materials_agent/          # 后端 Python 包
│   ├── api.py                        # FastAPI 应用（337 直接端点 + 4 子路由挂载）
│   ├── agent.py                      # BatteryMaterialsAgent 核心编排类
│   ├── cli.py                        # CLI 入口（serve/route/discover/verify 等）
│   ├── config.py                     # Pydantic 配置模型（EngineMode/RUN_MODE 等）
│   ├── db.py                         # 统一数据库引擎工厂（SQLAlchemy 2.0 + psycopg3）
│   ├── qc_service.py                 # 统一 QC 服务入口（合并两套 QC 实现 + 审计快照）
│   ├── projects.py                   # 项目实体管理（Project/ProjectStore/ProjectTask）
│   ├── audit.py                      # 审计日志（AuditEntry/AuditLogger）
│   ├── version_store.py              # 版本追溯（Version/VersionStore）
│   ├── material_properties.py        # 材料属性注册（5 大类 54 字段）
│   ├── workflow_schema.py            # 工作流 Schema 加载
│   │
│   ├── router/                       # 材料类型路由
│   │   └── router.py                 # MaterialRouter/MaterialInput/RouterResult
│   ├── representation/               # 表示层
│   │   ├── crystal.py                # CrystalRepresentation（CIF/pymatgen）
│   │   └── polymer.py                # PolymerRepresentation（PSMILES/RDKit）
│   ├── generation/                   # 生成层
│   │   ├── crystal_candidate_generator.py   # 晶体候选（MP/GNoME 检索 + 元素替换）
│   │   ├── polymer_candidate_generator.py   # 高分子候选（LLM 规则重组）
│   │   ├── chemistry_rules.py        # 化学规则校验
│   │   ├── formula_validator.py      # 化学式校验
│   │   └── gen_model.py              # 生成模型封装
│   ├── prediction/                   # 预测层
│   │   ├── crystal_property_predictor.py    # CGCNN/M3GNet 晶体预测
│   │   └── polymer_property_predictor.py    # PolymerGNN 高分子预测
│   ├── industrialization/            # 工业化验证层
│   │   ├── compliance_checker.py     # SMARTS 合规 + REACH 核查
│   │   ├── raw_material_db.py        # 物料规格库（PostgreSQL）
│   │   ├── formula_agent.py          # BOM/BOP 配方设计 Agent
│   │   ├── formula_store.py          # 配方版本存储
│   │   ├── feasibility.py            # 工业化可行性筛选
│   │   └── material_request.py       # 物料请求
│   ├── synthesis/                    # 合成层
│   │   ├── synthesis_planner.py      # ASKCOS 逆合成规划
│   │   └── task_store.py             # 合成任务存储
│   ├── verification/                 # 验证层
│   │   └── dft_verifier.py           # DFT 验证（RDKit→PySCF→ASE 降级链）
│   │
│   ├── experiment/                   # 实验全链路
│   │   ├── experiment_controller.py  # 任务单状态机 + 结果记录
│   │   ├── approval.py               # 审批引擎（ApprovalEngine）
│   │   ├── sample_store.py           # 样品管理（含 SampleTransfer 转移记录）
│   │   ├── equipment_store.py        # 设备台账
│   │   ├── candidate_store.py        # 候选材料持久化
│   │   ├── idea_store.py             # 实验假设
│   │   ├── bom_store.py              # BOM 物料清单存储
│   │   ├── candidate_artifact_store.py    # 候选产物（结构文件等）
│   │   ├── process_scheme_store.py   # 工艺方案存储
│   │   └── test_task_store.py        # 测试任务存储
│   ├── middleware/                   # 湿数据中间件
│   │   ├── data_middleware.py        # DataMiddleware 主入口
│   │   ├── adapters.py               # 设备/格式适配器
│   │   └── wet_data/                 # 湿数据子模块
│   │       ├── normalization.py      # 数据归一化
│   │       ├── quality.py            # QCEngine（Completeness/Plausibility/SampleMatcher）
│   │       └── adapters.py           # 湿数据适配
│   ├── ecml/                         # ECML 闭环引擎
│   │   └── ecml_engine.py            # ECMLEngine/ECMLState（八步循环）
│   │
│   ├── agent_team/                   # 多智能体协作框架
│   │   ├── models.py                 # AgentDefinition/TaskStep/OrchestrationPlan/ExecutionEvent
│   │   ├── registry.py               # AgentRegistry（注册/发现）
│   │   ├── orchestrator.py           # TaskOrchestrator（任务编排）
│   │   ├── executor.py               # AgenticExecutor（执行器）
│   │   ├── agent_proxy.py            # AgentProxy（业务活动调用工具的统一入口，v2.1）
│   │   ├── activity_mapping.py       # ActivityMappingStore（活动↔Agent↔工具三层映射，v2.1 新增）
│   │   ├── mapping_router.py         # 映射控制台 REST 路由（/mappings/*，v2.1 新增）
│   │   ├── event_log.py              # AgentEventLog（调用事件日志）
│   │   ├── research_event_stream.py  # ResearchEventStream（统一研发事件流水）
│   │   ├── eligibility_store.py      # Agent 资格存储
│   │   └── agents/                   # 内置专业 Agent
│   │       ├── experiment_analyst.py # 实验分析 Agent
│   │       ├── battery_life.py       # 电池寿命（Learner/Interpreter/Oracle 三体）
│   │       ├── literature_researcher.py  # 文献调研 Agent
│   │       └── cross_validator.py    # 交叉验证 Agent
│   ├── hybrid/                       # 混合编排（研发工作台后端）
│   │   ├── orchestrator.py           # HybridOrchestrator
│   │   ├── intent_interpreter.py     # IntentInterpreter 意图解析
│   │   ├── plan_validator.py         # PlanValidator 计划校验
│   │   ├── research_store.py         # ResearchStore（研发请求持久化）
│   │   └── committee_trigger.py      # 委员会触发器
│   ├── committee/                    # 委员会机制
│   │   ├── models.py                 # CommitteeCase/Proposal/EvidenceItem/CommitteeVerdict
│   │   ├── enums.py                  # CaseStatus/EvidenceSource 等枚举
│   │   ├── coordinator.py            # 委员会协调器
│   │   ├── thinker.py / doer.py / verifier.py   # 三种角色 Agent
│   │   ├── executor.py               # 案例执行器
│   │   ├── policy.py                 # 评审策略
│   │   ├── scorecards.py             # 评分卡
│   │   ├── triggers.py               # 触发规则
│   │   ├── repository.py             # 案例存储（PostgreSQL）
│   │   ├── event_store.py            # 事件存储
│   │   └── adapters/                 # 证据适配器（crystal/experiment/external_evidence）
│   ├── control_plane/                # 控制平面
│   │   ├── context.py                # ExecutionContext 执行上下文
│   │   ├── identity.py               # IdentityManager 身份管理
│   │   ├── policy_engine.py          # PolicyEngine 策略引擎
│   │   ├── policy_store.py           # 策略存储
│   │   ├── tool_catalog.py           # 工具目录
│   │   ├── tool_gateway.py           # 工具网关（调用拦截）
│   │   ├── run_manager.py            # Run/Checkpoint 运行管理
│   │   ├── budget.py                 # BudgetManager 预算管理
│   │   ├── observability.py          # 可观测性服务
│   │   ├── memory_service.py         # MemoryService 记忆卡片
│   │   ├── provider_registry.py      # Provider 注册
│   │   ├── capability_router.py      # CapabilityRouter 能力→工具路由
│   │   ├── model_router.py           # ModelRouter 模型选择路由
│   │   ├── provenance.py             # 溯源记录
│   │   ├── outbox.py                 # Outbox 事件外发模式
│   │   └── repositories/             # 仓储层（run_repo/budget_repo/control_plane_repo）
│   │
│   ├── capability/                   # 能力契约注册中心（v2.0 新增）
│   │   ├── models.py                 # CapabilityContract（适用域/回退链/风险等级）
│   │   ├── registry.py               # CapabilityRegistry（含 seed_builtin）
│   │   └── router.py                 # REST 路由（8 端点）
│   ├── release_card/                 # 实验放行卡（v2.0 新增）
│   │   ├── models.py                 # ReleaseCard（六类证据/五种推荐结论）
│   │   ├── generator.py              # 从委员会 case 生成放行卡
│   │   ├── store.py                  # PostgreSQL 存储（MDM 字典校验）
│   │   ├── metrics.py                # 放行卡指标汇总
│   │   └── router.py                 # REST 路由（5 端点）
│   ├── value_realization/            # 研发收益证明层（v2.0 新增）
│   │   ├── models.py                 # ProjectBaseline/CostRule/MetricValue
│   │   ├── calculator.py             # compute_value_report 收益计算核心
│   │   ├── report.py                 # Markdown 账单渲染
│   │   ├── store.py                  # 基线与成本规则存储
│   │   └── router.py                 # REST 路由（8 端点）
│   ├── mdm/                          # 主数据治理（v2.0 新增，五阶段）
│   │   ├── reference_dict.py         # P1 参考字典（7 表：状态码/分类码/单位/换算/标准/GHS/维度）
│   │   ├── master_data.py            # P2 主数据（9 表：样品类型/位置/容器/设备模板等）
│   │   ├── cimc.py                   # P3 CIMC（5 表：特性/指标/方法/规格/检查能力）
│   │   ├── process.py                # P4 工艺（6 表：路线/步骤/参数/关联）
│   │   └── documents.py              # P5 文档版本 + 执行快照 + 血缘
│   ├── data_ingest/                  # 客户数据接入（v2.0 新增）
│   │   ├── field_dict.py             # 四实体字段字典（sample/equipment/raw_material/experiment_result）
│   │   ├── mapping.py                # auto_map 自动字段映射
│   │   ├── quality.py                # check_quality 数据质量报告（已标记 deprecated，委托 qc_service）
│   │   ├── store.py                  # IngestStore（imports/import_rows，幂等键）
│   │   └── router.py                 # REST 路由（5 端点）
│   │
│   ├── mcp_tools/                    # MCP/SCP 工具集成
│   │   ├── tools.py                  # MCPToolRegistry 内部工具注册
│   │   ├── alias_registry.py         # 工具别名
│   │   ├── scp_catalog.py            # SCPCatalog/ToolBinding/RiskLevel（含 ecml_steps 绑定）
│   │   ├── scp_client.py             # SCPClientPool 连接池
│   │   ├── scp_policy.py             # SCPPolicy 策略（PolicyDeniedError）
│   │   ├── scp_adapters.py           # 5 个内置 SCP 适配器
│   │   ├── skill_catalog.py          # SkillCatalog（声明式 SKILL 流水线注册，v2.1 新增）
│   │   └── skill_executor.py         # SkillExecutor（SKILL pipeline 顺序执行 + 门禁，v2.1 新增）
│   ├── llm/                          # LLM 提供者层
│   │   ├── base.py                   # Provider 基类协议
│   │   ├── factory.py                # Provider 工厂（按 ENGINE_MODE 创建）
│   │   ├── legacy_provider.py        # 传统 OpenAI 兼容 API
│   │   ├── internlm_provider.py      # InternLM 统一科学模型
│   │   ├── schemas.py                # ChatRequest/ChatResponse/ProviderHealth
│   │   └── token_tracker.py          # Token 用量追踪
│   ├── auth/                         # 认证与授权
│   │   ├── middleware.py             # get_current_user/require_role/check_project_access
│   │   ├── tokens.py                 # HMAC-SHA256 签名 token（issue/verify）
│   │   └── user_store.py             # UserStore（用户 CRUD + 密码哈希升级）
│   ├── knowledge/                    # 知识资产层（v2.1 重构）
│   │   ├── asset_store.py            # PaperStore/MaterialStore/ClaimStore（三层资产 + DOI 去重）
│   │   ├── credibility.py            # 双维度可信度模型（source_tier × evidence_level）
│   │   ├── graph_store.py            # KnowledgeGraphStore（图谱持久化）
│   │   └── ingestion.py              # 多源采集管道（LLM/Crossref/Semantic Scholar/本地）
│   ├── battery/                      # 电池循环数据库
│   │   └── cycle_database.py         # BatteryCycleDatabase
│   ├── cross_scale/                  # 跨尺度计算
│   │   └── engine.py                 # CrossScaleEngine（占位实现）
│   ├── evals/                        # 评估系统
│   │   ├── runner.py                 # EvalRunner
│   │   ├── datasets/                 # 5 个黄金数据集
│   │   ├── fixtures/mock_providers.py    # Mock Provider
│   │   ├── scorers/                  # 评分器（science/safety/ops 三类）
│   │   └── reports/                  # 评估报告输出
│   └── integrations/                 # 外部集成审计与 SCP 异步任务
│       ├── models.py                 # ExternalInvocation
│       ├── audit_store.py            # AuditStore/ProvenanceDecorator
│       ├── material_info_client.py   # 材料信息查询客户端
│       ├── scp_task_store.py         # SCP 异步任务持久化（状态机 + 重试/取消，v2.1 新增）
│       ├── scp_task_worker.py        # SCP 异步任务 Worker（后台轮询执行，v2.1 新增）
│       └── scp_task_locks.py         # SCP 任务分布式锁（防并发重复，v2.1 新增）
│
├── frontend/                         # Vue 3 前端
│   ├── src/
│   │   ├── api/                      # 32 个 API 模块（axios 封装）
│   │   ├── components/               # 32 个公共组件
│   │   ├── views/                    # 40 个页面视图
│   │   ├── stores/                   # 7 个 Pinia store
│   │   ├── router/index.js           # 路由（40+ 路径 + 角色守卫）
│   │   ├── layouts/MainLayout.vue    # 主布局
│   │   ├── constants/                # 常量（materialTypes/toolMeta）
│   │   ├── utils/                    # 工具函数
│   │   └── styles/                   # design-tokens.css 设计令牌
│   ├── vite.config.js                # Vite 配置（端口 5173，代理 /api → 127.0.0.1:8000）
│   └── package.json
│
├── alembic/                          # 数据库迁移
│   ├── env.py                        # Alembic 环境（读 DATABASE_URL）
│   └── versions/                     # 29 个迁移脚本（0001~0029，含 pgvector）
├── config/
│   ├── workflows/ecml_v2.yaml        # ECML 工作流配置
│   └── qc_rules.yaml                 # QC 规则配置
├── scripts/                          # 运维脚本
│   ├── migrate_sqlite_to_postgres.py # SQLite → PostgreSQL 迁移脚本
│   ├── verify_migration_row_counts.py    # 迁移行数核验
│   ├── verify_business_chain_e2e.py  # 业务链 E2E 验证
│   ├── verify_mdm_api_regression.py  # MDM API 回归
│   ├── verify_mdm_fk_integrity.py    # MDM 外键完整性
│   ├── verify_regression_smoke.py    # 回归冒烟
│   ├── seed_raw_materials.py         # 物料库种子数据
│   ├── reset_stuck_committee_cases.py    # 卡死委员会案例重置
│   ├── cleanup_ecml_runs.py          # ECML 运行清理
│   └── scan_db_corruption.py         # 数据库腐坏扫描
├── tests/                            # 测试（unit/ + integration/ + 根级回归）
├── doc/                              # 设计文档与评测报告
├── docker-compose.yml                # pgvector/pgvector:pg16 容器定义（v2.1 升级）
├── alembic.ini                       # Alembic 配置
├── pyproject.toml                    # Python 依赖与构建配置
├── .env.example                      # 环境变量模板
└── askcos-data/ + askcos-deploy/     # ASKCOS 逆合成套件（数据 + 部署）
```

---

## 4. 后端模块详解

### 4.1 入口与编排层

#### 4.1.1 `api.py` — FastAPI 应用

- **应用定义**：`app = FastAPI(title="Battery Materials Agent API", version="0.1.0")`，全局依赖 `get_current_user` 解析 `X-Auth-Token` 写入 `request.state.current_user`（匿名不阻断）。
- **启动守卫**：`ensure_project_root()` 强制 CWD 切到项目根，保证 `.env`/`data/` 相对路径正确。
- **子路由挂载**（无 `/api` 前缀，Vite 代理已剥离）：
  - `capability.router`（8 端点）、`release_card.router`（5 端点）
  - `value_realization.router`（8 端点）、`data_ingest.router`（5 端点）
  - `agent_team.mapping_router`（/mappings/* 活动↔Agent↔工具三层映射，v2.1 新增）
- **直接端点**：337 个，覆盖项目/候选/预测/合成/实验/QC/ECML/委员会/控制平面/MDM/知识图谱/用户/系统配置等全域。
- **CORS**：默认同源不开；跨域通过 `CORS_ALLOWED_ORIGINS` 环境变量配置白名单。
- **后台任务**：`_spawn_background()` 持有强引用防 GC，集中管理 asyncio 任务生命周期。
- **能力门禁**：模块级 `CapabilityRegistry` 单例装饰器，为直接 API 端点提供能力契约门禁。

#### 4.1.2 `agent.py` — BatteryMaterialsAgent

核心编排类，依赖注入所有流水线组件：

```python
class BatteryMaterialsAgent:
    def __init__(self, config: AgentConfig | None = None):
        # 注入 Router/Representation/Prediction/Generation/Synthesis/
        # Verification/ExperimentController/ApprovalEngine/DataMiddleware/
        # ECMLEngine/RawMaterialDB/FormulaAgent/ComplianceAndCostNode/
        # IndustrialFeasibilityScreening/MCPToolRegistry/CandidateStore
```

关键方法：`route_material()`、`generate_candidates()`、`predict_properties()`、`check_compliance()`、`design_formula()`、`plan_synthesis()`、`verify()`、`run_ecml()`。

模块内还包含工业化成本/EHS 细化逻辑：`_depreciation_rate_for()`（设备台时费关键词匹配）、`_estimate_step_power_kw()`（按工艺温度估功率）、`_build_hazard_profile()`（EHS 危险特性档案：REACH/GHS/闪点/SDS）。

#### 4.1.3 `config.py` — 配置体系

- `AgentConfig`（Pydantic）：引擎模式、LLM、InternLM、SCP、ASKCOS、工业化阈值等。
- `EngineMode` 枚举：`legacy` / `internlm`（`logos` 已弃用，自动映射至 internlm）。
- `load_config()` / `get_config()` / `save_config_to_env()` / `ensure_project_root()`。

#### 4.1.4 `cli.py` — CLI 入口

子命令：`serve`（启动 API）、`route`（材料路由）、`discover`（ECML 发现）、`discover-crystal`、`discover-polymer`、`synthesis`、`verify`、`mcp-manifest`、`tools`。

### 4.2 Router 路由模块

**文件**：`router/router.py`

- `MaterialInput`：name/smiles/psmiles/formula/cif_content 五选一输入。
- `MaterialRouter.route(input) -> RouterResult`：优先级 PSMILES > CIF/Formula > SMILES > Name，判定材料类型（polymer/crystal/molecule）并归一化表示。
- `RouterResult`：material_type、normalized、confidence、metadata。

### 4.3 Representation 表示层

| 文件 | 关键类 | 职责 |
|---|---|---|
| `representation/crystal.py` | `CrystalRepresentation` | CIF/POSCAR 解析（pymatgen Structure），结构归一化、对称性分析 |
| `representation/polymer.py` | `PolymerRepresentation` | PSMILES canonicalize（RDKit），重复单元识别、聚合度估算 |

### 4.4 Generation 生成层

| 文件 | 关键类 | 职责 |
|---|---|---|
| `generation/crystal_candidate_generator.py` | `CrystalCandidateGenerator` | MP/GNoME 候选库检索 + 元素替换 + 结构扰动 |
| `generation/polymer_candidate_generator.py` | `PolymerCandidateGenerator` | 多 LLM API 规则重组生成 PSMILES 候选 |
| `generation/chemistry_rules.py` | 化学规则函数集 | 价态/电荷/配位合理性校验 |
| `generation/formula_validator.py` | 校验函数 | 化学式合法性 |
| `generation/gen_model.py` | 生成模型封装 | 分子扩散模型接口 |

### 4.5 Industrialization 工业化验证层

| 文件 | 关键类 | 职责 |
|---|---|---|
| `industrialization/compliance_checker.py` | `ComplianceAndCostNode` | SMARTS 毒性/合规规则 + REACH 受限物质核查 + 成本估算节点 |
| `industrialization/raw_material_db.py` | `RawMaterialDB` | 物料规格库（PostgreSQL）：供应商/库存/单价/COA/SDS/检测凭证 |
| `industrialization/formula_agent.py` | `FormulaAgent` | BOM/BOP 配方与工艺设计（LLM 驱动） |
| `industrialization/formula_store.py` | `FormulaStore`/`FormulaVersion` | 配方版本管理 |
| `industrialization/feasibility.py` | `IndustrialFeasibilityScreening` | 工业化可行性筛选 |
| `industrialization/material_request.py` | `MaterialRequestStore` | 物料请求流转 |

### 4.6 Prediction 预测层

| 文件 | 关键类 | 职责 |
|---|---|---|
| `prediction/crystal_property_predictor.py` | `CrystalPropertyPredictor` | CGCNN + M3GNet 晶体性质预测（带 ASE-EMT 回退） |
| `prediction/polymer_property_predictor.py` | `PolymerPropertyPredictor` | PolymerGNN 高分子预测（RDKit 描述子回退） |

### 4.7 Synthesis 合成层

- `synthesis/synthesis_planner.py` — `SynthesisPlanner`：ASKCOS 逆合成规划（retro 模板 + buyables 可购库 + scscore 复杂度）。
- `synthesis/task_store.py` — 合成任务持久化（PostgreSQL）。

### 4.8 Verification 验证层

- `verification/dft_verifier.py` — `DFTVerifier`：三级降级链 RDKit（快速描述符）→ PySCF（DFT 精算，需 Python 3.11+）→ ASE（经验势 EMT）。输出 `VerificationResult`（能量/带隙/稳定性等）。

### 4.9 Experiment 实验全链路

#### 4.9.1 `experiment_controller.py` — 核心状态机

- `ExperimentOrder`：任务单（类型/样品/参数/状态/审批）。
- `ExperimentResultRecord`：结果记录（属性名/数值/单位/测试方法/条件/设备）。
- `ExperimentType` 枚举：覆盖电化学/结构/热学/力学等测试类型。
- `ExperimentController`：任务单创建 → 审批 → 执行 → 数据录入 → QC → 归档全生命周期；非法状态迁移抛 `IllegalStateTransitionError`。
- `ApprovalRule` / `ApprovalDecision`：审批规则与决策模型。

#### 4.9.2 支撑 Store（全部 PostgreSQL）

| Store | 模型 | 职责 |
|---|---|---|
| `SampleStore` | `Sample`/`SampleTransfer` | 样品台账与转移记录 |
| `EquipmentStore` | `Equipment`/`EquipmentStatus` | 设备台账（校准日期/负责人） |
| `CandidateStore` | `CandidateRecord` | 候选材料持久化 |
| `IdeaStore` | `Idea`/`IdeaStatus` | 实验假设管理 |
| `ApprovalEngine` (`approval.py`) | — | 审批规则引擎 |
| `BomStore` (`bom_store.py`) | — | BOM 物料清单 |
| `CandidateArtifactStore` | — | 候选产物（CIF/JSON 结构文件） |
| `ProcessSchemeStore` | — | 工艺方案 |
| `TestTaskStore` | — | 测试任务 |

### 4.10 Middleware 湿数据中间件

- `middleware/data_middleware.py` — `DataMiddleware`：湿实验数据统一入口，归一化 → QC → 追溯（关联 order_id/candidate_id）。
- `middleware/wet_data/quality.py` — **QCEngine 核心实现**：
  - `CompletenessChecker`（完整性）、`PlausibilityChecker`（合理性）、`SampleMatcher`（样品匹配）。
  - `QCResult`：qc_status/issues/decision_path/severity/confidence/completeness_score/learning_eligible/rule_results/rule_version（全部可解释字段）。
  - `load_qc_config()`：加载 `config/qc_rules.yaml`。
- `middleware/wet_data/normalization.py` — 单位/格式归一化。

### 4.11 统一 QC 服务（`qc_service.py`，v2.0 新增）

合并原 `data_ingest/quality.py` 与 `middleware/wet_data/quality.py` 两套独立 QC 实现：

- `get_qc_engine()` — QCEngine 单例（首次访问加载 qc_rules.yaml）。
- `check_record(record, valid_sample_ids)` — 统一 QC 检查入口，委托 QCEngine。
- `write_audit_log(result_id, qc_result)` — 把完整规则快照写入 `audit.qc_decisions` 表（JSONB），DB 不可用静默失败不阻塞主流程。
- `check_and_audit()` — 一站式：检查 + 审计。
- `reset_qc_engine()` — 测试用单例重置。

### 4.12 ECML 调度引擎

**文件**：`ecml/ecml_engine.py`

- `ECMLEngine`：八步闭环 — ①设计 → ②预测 → ③合成 → ④验证 → ⑤实验 → ⑥分析 → ⑦学习 → ⑧决策。
- `ECMLState`：闭环运行状态（迭代轮次/当前步/历史/反馈）。
- 关键设计：后端 run steps 用 `asyncio.to_thread` 防事件循环阻塞；引擎反馈考虑属性方向（maximize/minimize）而非统一 max 比较。
- 工作流配置：`config/workflows/ecml_v2.yaml`（`workflow_schema.py` 的 `SchemaLoader` 加载）。

### 4.13 Agent Team 多智能体协作

| 文件 | 关键类 | 职责 |
|---|---|---|
| `agent_team/models.py` | `AgentDefinition`/`TaskStep`/`OrchestrationPlan`/`ExecutionEvent`/`AgentRole`/`AgentDefinitionV2` | 协作编排数据模型（V1→V2 capability-driven 迁移） |
| `agent_team/registry.py` | `AgentRegistry` | Agent 注册/发现/能力声明（含 V1→V2 迁移映射表） |
| `agent_team/orchestrator.py` | `TaskOrchestrator` | 计划拆解与任务编排 |
| `agent_team/executor.py` | `AgenticExecutor` | 执行器（工具选择不做关键词不匹配时回退唯一工具） |
| `agent_team/agent_proxy.py` | `AgentProxy`/`AgentInvocationResult` | 业务活动调用工具的统一入口（v2.1，决策 7-A/9-C/2-C/10-B） |
| `agent_team/activity_mapping.py` | `ActivityAgentBinding`/`AgentToolBinding`/`ToolRegistration`/`ActivityMappingStore` | 活动↔Agent↔工具三层映射配置（v2.1 新增，决策 13） |
| `agent_team/mapping_router.py` | — | 映射控制台 REST 路由（/mappings/*，v2.1 新增） |
| `agent_team/event_log.py` | `AgentEventLog` | Agent 调用事件日志 |
| `agent_team/research_event_stream.py` | `ResearchEventStream` | 统一研发事件流水 |
| `agent_team/eligibility_store.py` | — | Agent 资格存储 |

**三层映射模型**（v2.1 决策 13）：
- `ActivityAgentBinding`：业务活动→智能体（静态绑定 `agent_id` + 能力需求 `capability_need` 用于回退）
- `AgentToolBinding`：智能体→主工具（`primary_tool_id` 显式绑定 + `CapabilityRouter` 评分回退 + `tools_whitelist/blacklist`）
- `ToolRegistration`：新工具注册元数据（source: local/scp/internlm，availability: always/conditional/disabled）

**铁律**：业务活动必须通过 Agent 调用工具，禁止直接调用大模型。

内置专业 Agent（`agent_team/agents/`）：

| Agent | 文件 | 职责 |
|---|---|---|
| ExperimentAnalystAgent | `experiment_analyst.py` | 实验数据分析与偏差解读 |
| LearnerAgent/InterpreterAgent/OracleAgent | `battery_life.py` | 电池寿命预测三体协作 |
| LiteratureResearcherAgent | `literature_researcher.py` | 文献调研与情报 |
| CrossValidatorAgent | `cross_validator.py` | 跨源证据交叉验证 |

### 4.14 Hybrid Orchestrator 混合编排

**统一研发入口（研发工作台后端）**：

- `hybrid/intent_interpreter.py` — `IntentInterpreter`：自然语言意图 → 结构化研发请求（`ResearchRequest`）。
- `hybrid/orchestrator.py` — `HybridOrchestrator`：意图解析 → 能力路由 → 模型路由 → 计划校验 → 执行，产出 `ResearchPlan`/`TaskStepV3`/`EvidenceSummary`。
- `hybrid/plan_validator.py` — `PlanValidator`：计划可行性校验（能力覆盖/依赖环/预算）。
- `hybrid/research_store.py` — `ResearchStore`：研发请求持久化（PostgreSQL）。
- `hybrid/committee_trigger.py` — 满足条件时自动触发委员会评审。

### 4.15 Committee 委员会机制

| 文件 | 关键类 | 职责 |
|---|---|---|
| `committee/models.py` | `CommitteeCase`/`Proposal`/`EvidenceItem`/`CommitteeVerdict` | 决策案例数据模型 |
| `committee/enums.py` | `CaseStatus`/`EvidenceSource` | 状态与来源枚举（PASS/REQUEST_EVIDENCE/HUMAN_REVIEW/REJECT/FAILED） |
| `committee/coordinator.py` | Coordinator | 多角色协调 |
| `committee/thinker.py` | Thinker | 提案生成角色 |
| `committee/doer.py` | Doer | 证据收集角色 |
| `committee/verifier.py` | Verifier | 证据核验角色 |
| `committee/executor.py` | Executor | 案例执行流 |
| `committee/policy.py` | 策略 | 评审策略（通过阈值/证据要求） |
| `committee/scorecards.py` | 评分卡 | 多维评分 |
| `committee/triggers.py` | 触发器 | 自动立案规则 |
| `committee/repository.py` | `CommitteeRepository` | 案例存储（PostgreSQL） |
| `committee/event_store.py` | `CommitteeEventStore` | 事件存储 |
| `committee/adapters/` | crystal/experiment/external_evidence | 三类证据适配器 |

### 4.16 Control Plane 控制平面

| 文件 | 关键类 | 职责 |
|---|---|---|
| `control_plane/context.py` | `ExecutionContext` | 执行上下文（身份/预算/追踪） |
| `control_plane/identity.py` | `IdentityManager` | 身份与凭证 |
| `control_plane/policy_engine.py` | `PolicyEngine` | OPA 风格策略评估 |
| `control_plane/policy_store.py` | `PolicyStore` | 策略持久化 |
| `control_plane/tool_catalog.py` | `ToolCatalog` | 工具元数据目录 |
| `control_plane/tool_gateway.py` | `ToolGateway` | 工具调用拦截（策略+预算+审计） |
| `control_plane/run_manager.py` | `RunManager`/`Run`/`RunStatus`/`Checkpoint` | 运行与检查点 |
| `control_plane/budget.py` | `BudgetManager`/`BudgetScope`/`BudgetEnvelope` | 预算域与信封 |
| `control_plane/observability.py` | `ObservabilityService` | 指标/追踪/日志 |
| `control_plane/memory_service.py` | `MemoryService`/`MemoryCardType` | 记忆卡片服务 |
| `control_plane/provider_registry.py` | `ProviderRegistry` | Provider 注册与健康 |
| `control_plane/capability_router.py` | `CapabilityRouter` | `resolve(capability, profile) -> list[CapabilityBinding]` |
| `control_plane/model_router.py` | `ModelRouter` | `route(capability, profile) -> ModelRoute` |
| `control_plane/provenance.py` | — | 数据/决策溯源 |
| `control_plane/outbox.py` | — | Outbox 事件外发（可靠投递模式） |
| `control_plane/repositories/` | run_repo/budget_repo/control_plane_repo | 仓储层（PostgreSQL） |

### 4.17 Capability 能力契约注册中心（v2.0 新增）

**目的**：任何 AI 输出都可回溯到对应契约 — 模型版本、适用域、回退路径。

- `capability/models.py` — `CapabilityContract`：
  - 标识：capability_id/name/provider/version
  - 契约：input_schema/output_schema/supported_domains/limitations
  - 质量：uncertainty_method/ood_method/validation_dataset
  - 治理：risk_level（low/medium/high）/status（active/pending_approval/deprecated）/fallback_chain（其他 capability_id 链）/cost_model/latency_sla/owner/license
- `capability/registry.py` — `CapabilityRegistry`：CRUD + `seed_builtin()` 内置契约种子 + `list_all(domain, risk_level, status, q)` 过滤 + 回退链解析。
- `capability/router.py` — 8 端点：列表/详情（RESEARCHER）、创建/更新/审批/弃用/删除（ADMIN）、回退链查询。写操作记录审计日志（`module="capability"`，失败不阻断）。

### 4.18 Release Card 实验放行卡（v2.0 新增）

**定位**：研发人员可直接执行的决策载体，承接委员会评审结论。

- `release_card/models.py` — `ReleaseCard`：
  - `recommendation`：recommend / conditional / need_evidence / human_review / reject
  - `target_window`：metrics/success_range/min_viable_outcome
  - `evidence_summary`：**六类证据** — prediction/experiment_history/literature/cost/ehs/synthesis_feasibility（每类可空，None=未提供，绝不编造）
  - `uncertainty`：applicability_domain/data_gaps/key_assumptions/failure_modes
  - `suggested_experiments`：recipe/conditions/sample_count/priority/equipment/estimated_cost
  - `stop_conditions`、`human_responsibility`（reviewer/opinion/final_decision/decided_at）
  - `provenance`：run_id/model_versions/data_versions/rule_versions/audit_refs
  - `status`：draft → pending_review → decided
- `release_card/generator.py` — 从委员会 case 生成：委员会终态映射推荐结论（PASS→recommend、REQUEST_EVIDENCE→need_evidence 等，非终态保守转人工）；证据 capability → 六类映射 + 来源兜底。
- `release_card/store.py` — `ReleaseCardStore`：PostgreSQL CRUD；**写前 MDM 校验**（status 走 `mdm.status_codes`、recommendation 与 evidence_category 走 `mdm.dimensions`）；构造参数 `db_path` 仅为兼容保留，实际用全局 Engine。
- `release_card/metrics.py` — 放行卡汇总指标。
- `release_card/router.py` — 5 端点：创建/列表/详情/评审（review）/指标汇总。

### 4.19 Value Realization 研发收益证明层（v2.0 新增）

**铁律**：每个指标输出 `{value, kind: verified|estimated, assumption, evidence_refs}` —
- `verified`：直接来自系统真实数据（项目/任务单/样品记录）
- `estimated`：基于基线或成本规则推算，assumption 必须写明假设与公式
- 数据不足：`value=None, kind=verified`，assumption 写明缺什么数据。**严禁编造数字**。

- `value_realization/models.py`：
  - `ProjectBaseline`：历史周期（天）/单次实验典型成本/历史命中率/成功标准/历史候选数
  - `CostRule`：六类成本（material/equipment/labor/outsourced/energy/waste）+ 单价 + 单位 + 启停
  - `MetricValue`：label/value/unit/kind/assumption/evidence_refs
- `value_realization/calculator.py` — `compute_value_report(project_id)`：聚合项目任务单、候选、样品，对照基线计算周期缩短/成本节约/命中率提升等账单指标。
- `value_realization/report.py` — Markdown 账单渲染。
- `value_realization/store.py` — 基线与成本规则存储（PostgreSQL）。
- `value_realization/router.py` — 8 端点：基线 upsert/查询、成本规则 CRUD、收益报告（JSON + Markdown）。

### 4.20 MDM 主数据治理（v2.0 新增）

按 `.trae/specs/mdm-governance/spec.md` 规划，分 5 个 Phase（对应迁移 0011~0015+）：

| Phase | 文件 | 表（PostgreSQL schema：`mdm`） | 职责 |
|---|---|---|---|
| P1 | `mdm/reference_dict.py` | status_codes / classifications / units / unit_conversions / standards / ghs_classes / dimensions（7 表） | 参考字典中心：状态码/分类码/标准单位/单位换算/方法标准/GHS 危害/通用维度。`convert(value, from_unit, to_unit)` 换算工具 |
| P2 | `mdm/master_data.py` | sample_types / sample_status_transitions / locations / containers / logistics_types / equipment_templates / equipment_capabilities / equipment_template_capabilities / material_categories（9 表） | 样品类型模板、状态迁移规则（`is_transition_allowed`）、位置树（`get_tree`）、容器/物流/设备模板与能力 M:N |
| P3 | `mdm/cimc.py` | properties / test_items / test_methods / specifications / inspection_capabilities（5 表） | CIMC：特性 1→N 指标 N→1 方法 1→N 检查能力 + 规格判定 |
| P4 | `mdm/process.py` | process_routes / process_steps / process_parameters / process_route_steps / process_step_parameters / process_step_equipment_templates（6 表） | 工艺路线-步骤-参数-设备能力模板 |
| P5 | `mdm/documents.py` | documents / document_versions / order_snapshots 等 | 文档版本、任务单执行快照、全链血缘 + 业务表 FK 加固 |

设计原则：初始数据由迁移脚本 seed；业务侧以 list/get 只读为主，治理写操作集中在受控端点。所有 Store 走 `db.get_engine()`。

### 4.21 Data Ingest 客户数据接入（v2.0 新增）

**流程**：前端解析 Excel/CSV 为 rows JSON → 后端映射、校验、质量报告、幂等写入与审计。

- `data_ingest/field_dict.py` — `ENTITY_FIELD_DICT`：四实体 canonical 字段定义
  - `sample`（10 字段）、`equipment`（11 字段）、`raw_material`（15 字段，含 COA/SDS/检测报告合规凭证）、`experiment_result`（核心：property_name + value 必填）
  - 每字段：key/label/required/type(string/number/date)/aliases（中英文别名）/unit_hints
- `data_ingest/mapping.py` — `auto_map`：用户列名 → canonical 字段自动映射。
- `data_ingest/quality.py` — `check_quality`：导入质量报告（**已标记 deprecated**，新代码统一走 `qc_service`）。
- `data_ingest/store.py` — `IngestStore`：`data_ingest.imports`（批次）+ `import_rows`（行级明细）；**幂等**：`idempotency_key` UNIQUE，重复提交返回已有记录并标 `duplicated=True`。
- `data_ingest/router.py` — 5 端点：字段字典查询 / preview（映射+质量预览）/ commit（幂等写入）/ 批次列表 / 批次详情。

### 4.22 MCP / SCP 工具集成

| 文件 | 关键类 | 职责 |
|---|---|---|
| `mcp_tools/tools.py` | `MCPToolRegistry`/`SCPToolProxy` | 内部 MCP 工具注册（manifest 输出）+ SCP 完整调用链（authorize→validate→call→normalize→provenance→audit） |
| `mcp_tools/alias_registry.py` | — | 工具别名解析 |
| `mcp_tools/scp_catalog.py` | `SCPCatalog`/`ToolBinding`/`RiskLevel` | SCP 外部工具目录与绑定（含 `ecml_steps` 步骤绑定） |
| `mcp_tools/scp_client.py` | `SCPClientPool` | SCP 连接池（JSON-RPC 2.0 over HTTP，超时/重试/并发信号量） |
| `mcp_tools/scp_policy.py` | `SCPPolicy`/`PolicyDeniedError` | 服务器/工具白名单策略（5 项检查：enabled/risk_level/allowed_roles/ecml_steps） |
| `mcp_tools/scp_adapters.py` | 5 个适配器 | MoleculeDescriptor/ToxicityAssessment/LiteratureSearch/ProtocolDraft/MaterialTransform |
| `mcp_tools/skill_catalog.py` | `SkillCatalog`/`SkillBinding`/`SkillPipelineStep`/`SkillRiskLevel` | 声明式 SKILL 流水线注册（v2.1 新增） |
| `mcp_tools/skill_executor.py` | `SkillExecutor` | SKILL pipeline 顺序执行 + 双层门禁（SKILL 整体 + pipeline 内单工具 server 级，v2.1 新增） |

**RiskLevel 四级**：A（结构转换/描述符，自动）/ B（毒理/ADMET/文献，辅助证据）/ C（分子对接/蛋白，需 admin）/ D（实验/采购，禁止）。

**SKILL 层**（v2.1 新增）：SKILL 是「组合能力」，按顺序流水线（pipeline）编排一个或多个 SCP 工具，上一个工具的输出可映射为下一个工具的输入（`${input.xxx}` / `${prev.output.xxx}`）。配置完全声明式，无代码逻辑。`SkillExecutor` 执行时先检查 SKILL 整体 `ecml_steps` 门禁，再检查 pipeline 内每个工具的 server 级门禁；两者任一不通过则拒绝执行。

默认关闭（`SCP_ENABLED=false`），依赖外部 API 可用性。

### 4.23 LLM 提供者层

| 文件 | 关键类 | 职责 |
|---|---|---|
| `llm/base.py` | Provider 协议 | 统一 chat/health 接口 |
| `llm/factory.py` | 工厂 | 按 `ENGINE_MODE` 创建 provider |
| `llm/legacy_provider.py` | LegacyProvider | OpenAI 兼容 API（LongCat 等） |
| `llm/internlm_provider.py` | InternLMProvider | InternLM 统一科学模型（thinking 模式/并发控制/JSON 修复重试） |
| `llm/schemas.py` | `ChatRequest`/`ChatResponse`/`ProviderHealth` | 协议模型 |
| `llm/token_tracker.py` | TokenTracker | Token 用量追踪（成本归集） |

LLM 响应解析包含非 JSON 格式错误处理，并隔离单候选失败。

### 4.24 认证与授权（`auth/`）

- `auth/tokens.py` — HMAC-SHA256 签名 token：`issue_token(user_id)` / `verify_token(token)`；密钥 `AUTH_TOKEN_SECRET`（production 必填）。
- `auth/user_store.py` — `UserStore`：用户 CRUD；`User`（role/project_ids/is_active）；`UserRole` 枚举（viewer/researcher/pm/admin，`ROLE_RANK` 排序）；`hash_password`/`verify_password`/`is_legacy_hash`（旧哈希自动升级）。
- `auth/middleware.py`：
  - `get_current_user(request)` — 从 `X-Auth-Token` 解析用户，永不抛异常（匿名返回 None），结果缓存到 `request.state.current_user`。
  - `require_role(min_role)` — FastAPI 依赖工厂：未登录访问高角色资源返回 401，角色不足返回 403；匿名仅允许 VIEWER 级。
  - `check_project_access(user_id, project_id, store)` — project_ids 为空表示全部可访问。

### 4.25 项目管理（`projects.py`）

- `Project`：目标应用（动力/储能/消费）、阶段（立项/筛选/中试/验证/定型）、目标属性、预算、迭代进度、candidate_ids/experiment_order_ids、tasks（含交付物与目标属性）。
- `ProjectStore`：PostgreSQL CRUD + `get_project_tasks(project_id)`。
- `ProjectTask`：立项拆解任务。

### 4.26 评估系统（`evals/`）

- `evals/runner.py` — `EvalRunner`：加载数据集 → 跑 pipeline → 评分 → 输出报告（`evals/reports/`）。
- 数据集（5 个）：candidate_ranking / crystal_golden / experiment_deviation / external_evidence_conflict / security_policy。
- 评分器三类：`science_scorers.py` / `safety_scorers.py` / `ops_scorers.py`。
- `fixtures/mock_providers.py`：离线 Mock Provider。

### 4.27 外部集成审计（`integrations/`）

- `integrations/models.py` — `ExternalInvocation`：外部调用记录（服务/入参/出参/时延/状态）。
- `integrations/audit_store.py` — `AuditStore` + `ProvenanceDecorator`（调用自动埋点）+ `init_audit_db()`。

### 4.28 辅助模块

| 模块 | 文件 | 关键类 | 职责 |
|---|---|---|---|
| 版本管理 | `version_store.py` | `Version`/`VersionType`/`VersionStore` | 材料/实验版本追溯与激活 |
| 审计日志 | `audit.py` | `AuditEntry`/`AuditLogger` | 关键操作审计（PostgreSQL） |
| 工作流 | `workflow_schema.py` | `SchemaLoader` | 工作流 Schema 加载 |
| 知识图谱 | `knowledge/graph_store.py` | `KnowledgeGraphStore` | 实体/关系存储查询 |
| 知识资产 | `knowledge/asset_store.py` | `PaperStore`/`MaterialStore`/`ClaimStore` | 三层知识资产（v2.1 新增） |
| 可信度模型 | `knowledge/credibility.py` | `SOURCE_TIER_SCORES`/`EVIDENCE_LEVEL_SCORES` | 双维度可信度评分（v2.1 新增） |
| 知识采集 | `knowledge/ingestion.py` | — | 多源采集管道（v2.1 新增） |
| 电池循环 | `battery/cycle_database.py` | `BatteryCycleDatabase` | 循环基准数据（占位） |
| 跨尺度 | `cross_scale/engine.py` | `CrossScaleEngine` | 分子→介观→宏观（占位） |
| 材料属性 | `material_properties.py` | `PropertyRegistry`/`PropertyField`/`PropertyCategory` | 5 大类 54 字段属性注册 |
| SCP 异步任务 | `integrations/scp_task_store.py` | `ScpTaskStore` | SCP 长时调用持久化 + 状态机（v2.1 新增） |
| SCP 任务 Worker | `integrations/scp_task_worker.py` | — | 后台轮询执行 + 重试/取消（v2.1 新增） |
| SCP 任务锁 | `integrations/scp_task_locks.py` | — | 分布式锁防并发重复（v2.1 新增） |

---

## 5. 前端模块详解

### 5.1 技术栈

| 类别 | 依赖 | 版本 |
|---|---|---|
| 核心框架 | vue | ^3.5.13 |
| 路由 | vue-router | ^4.4.5 |
| 状态管理 | pinia | ^2.2.4 |
| UI 组件库 | ant-design-vue | ^4.2.3 |
| HTTP 客户端 | axios | ^1.7.7 |
| 图表库 | echarts | ^5.5.1 |
| Excel 解析/导出 | xlsx | ^0.18.5 |
| E2E 测试 | playwright | ^1.62.0 |
| 分子 2D/3D | smiles-drawer / 3Dmol.js | CDN |
| 构建工具 | vite | ^5.4.11 |

### 5.2 路由与页面（`router/index.js`）

40+ 路径，全局导航守卫：未登录访问非公开页重定向首页；`meta.requiredRole` 按角色等级（viewer=0/researcher=1/pm=2/admin=3）拦截。

**核心工作区**：

| 路径 | 视图 | 标题 | 权限 |
|---|---|---|---|
| `/` | Dashboard | 总览 | 公开 |
| `/dashboard` | ManagementDashboard | 管理看板 | — |
| `/my-tasks` | MyTasks | 我的待办（合并审批/委员会/放行卡三个 tab） | — |
| `/projects` `/projects/new` | Projects / ProjectNew | 项目管理/新建 | — |
| `/workbench` | CandidateWorkbench | 候选材料设计（/discovery 已合并重定向） | — |
| `/prediction` | Prediction | 性质预测 | — |
| `/battery-life` | BatteryLifeWorkflow | 性能寿命预测 | — |
| `/ecml` `/ecml/runs` | ECMLMonitor / ECMLRuns | 实验闭环迭代/迭代历史 | — |
| `/experiments` | Experiments | 实验数据 | — |
| `/experiment-workbench` | ExperimentWorkbench | 实验工作台 | — |
| `/research` | ResearchWorkbench | 研发工作台 | — |
| `/synthesis` | Synthesis | 合成路径 | — |
| `/formula-design` | FormulaDesign | 配方与工艺 | — |

**治理与数据（v2.0 新增页面加粗）**：

| 路径 | 视图 | 标题 | 权限 |
|---|---|---|---|
| `/value-report` | **ValueReport** | 收益账单 | admin |
| `/data-ingest` | **DataIngest** | 数据接入 | — |
| `/capability-center` | **CapabilityCenter** | 能力契约 | admin |
| `/mdm` | **MdmCenter** | 主数据治理 | — |
| `/data-quality` | **DataQualityWorkbench** | 数据质量 | — |
| `/control-plane` | ControlPlaneDashboard | 控制平面 | admin |
| `/budgets` | BudgetBoard | 预算看板 | admin |
| `/eval-center` | EvalCenter | 评估中心 | admin |
| `/tools` | ToolsHub | 工具与连接器（/tool-catalog 已合并） | — |
| `/topology` | TopologyView | 调用关系 | — |
| `/orchestration` | Orchestration | 智能编排（已并入研发工作台菜单） | — |
| `/agents` | AgentManager | 智能体管理 | — |
| `/technology-intelligence` | TechnologyIntelligence | 技术情报 | — |
| `/knowledge-graph` | KnowledgeGraph | 知识图谱 | — |
| `/properties` | MaterialProperties | 属性字典 | — |
| `/materials` | RawMaterials | 物料规格库 | — |
| `/samples` | SampleManager | 样品管理 | — |
| `/equipment` | EquipmentLedger | 设备台账 | — |
| `/users` | UserManagement | 用户管理 | — |
| `/settings` | Settings | 系统设置 | — |

**菜单合并重定向**：`/approvals → /my-tasks?tab=approval`、`/committees → /my-tasks?tab=committee`、`/release-cards → /my-tasks?tab=release`、`/discovery → /workbench`、`/tool-catalog → /tools`。另有 9 条常见错误路径 301 重定向 + 404 通配页（NotFound）。

### 5.3 API 层（35 个模块）

`agentEvents`、`agents`、`approvals`、`auth`、`battery`、`candidates`、`capabilities`、`client`（axios 实例，baseURL=`/api`，X-Auth-Token 注入 + 错误转译）、`committees`、`controlPlane`、`dashboard`、`discovery`、`ecml`、`equipment`、`experiments`、`formula`、`ideas`、`ingest`、`knowledge`、`mappings`（v2.1 新增，活动↔Agent↔工具映射）、`materialRequests`、`mdm`、`orchestration`、`properties`、`rawMaterials`、`releaseCards`、`research`、`researchEvents`、`samples`、`synthesis`、`system`、`valueReports`、`versions`。

**关键工具函数**（`utils/`）：
- `errorHandler.js` — 全局错误转译（P0），生成工单编号 `ERR-<ts>-<seq>`，幂等 GET 提供重试按钮
- `format.js` — 数值格式化（`formatNumber`/`formatSci`/`formatPropValue`，属性感知：电导率等小量级走科学计数法）
- `candidateSource.js` — 候选材料来源标签统一映射（6 类规范 source_type + 颜色徽章）
- `crystal.js` — 晶体结构工具（元素 CPK 配色、化学式解析、空间群→晶系推断）
- `mdmDict.js` — MDM 字典 composable（14 类选项加载器 + 10s 缓存 + 单位符号工具）
- `researchContext.js` — 研发工作台→派生子任务视图的上下文映射（`buildDerivedQuery`/`parseResearchContext`）

### 5.4 状态管理（7 个 Pinia store）

`system`（配置/会话）、`projectContext`（当前项目上下文）、`researchContext`（研发请求上下文）、`discovery`（候选发现）、`ecml`（闭环状态）、`experiments`（实验数据）、`orchestration`（编排）、`tasks`（待办）。

### 5.5 关键组件（32 个）

| 组件 | 职责 |
|---|---|
| `AgentChip.vue` | Agent 显性表达（所有 AI 环节展示执行 Agent 及介绍，防黑箱） |
| `AgentFlowGraph.vue` | Agent 流程图（CSS absolute+visibility 隐藏保持尺寸；节点初始圆环坐标防重叠；重试定时器卸载清理） |
| `MoleculeView.vue` | 分子 2D/3D 视图（textContent 防 XSS；WebGL 关闭显式清理；SvgDrawer 实例级防串扰） |
| `CandidateTable.vue`/`CandidateDetail.vue`/`CandidateList.vue` | 候选材料列表/详情 |
| `ECMLStepFlow.vue` | ECML 八步流程可视化 |
| `GanttChart.vue` | 项目甘特图 |
| `KnowledgeGraph.vue`/`EntityGraph.vue` | 图谱可视化 |
| `RadarChart.vue`/`ParetoChart.vue`/`ResultChart.vue` | 雷达/帕累托/结果图表 |
| `ApprovalCard.vue`/`ActionCard.vue`/`MetricCard.vue`/`StatCard.vue` | 卡片族 |
| `OnboardingTooltip.vue` | 新手引导（禁用按钮用 a-tooltip + .tt-btn-wrap 包裹层显示原因） |
| `TaskNotifier.vue` | 任务通知 |
| `RunDetailDrawer.vue` | 运行详情抽屉 |
| `StructureView.vue`/`CrystalCellSvg.vue` | 晶体结构视图 |

---

## 6. API 端点总览

后端共 **370+ 个 REST 端点**：`api.py` 直接定义 337+ 个 + 5 个子路由 30+ 个。按域分组：

### 6.1 战略工作包子路由（无 `/api` 前缀）

**Activity Mapping 活动↔Agent↔工具映射**（`agent_team/mapping_router.py`，v2.1 新增，prefix=`/mappings`）：

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/mappings/activities` | — | 业务活动→智能体绑定列表 |
| POST | `/mappings/activities` | admin | upsert 绑定 |
| DELETE | `/mappings/activities/{binding_id}` | admin | 删除绑定 |
| GET | `/mappings/tools` | — | 智能体→工具绑定列表 |
| POST | `/mappings/tools` | admin | upsert 工具绑定 |
| DELETE | `/mappings/tools/{binding_id}` | admin | 删除工具绑定 |
| GET | `/mappings/registrations` | — | 工具注册列表 |
| POST | `/mappings/registrations` | admin | 注册新工具 |
| PUT | `/mappings/registrations/{tool_id}` | admin | 更新工具 |
| DELETE | `/mappings/registrations/{tool_id}` | admin | 删除工具 |
| GET | `/mappings/agents/{agent_id}/available-tools` | — | Agent 可用工具 |
| GET | `/mappings/overview` | — | 映射概览（决策 13-B 主从详情） |

**Capability 能力契约**（`capability/router.py`，8 端点）：

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/capabilities` | RESEARCHER | 列表（domain/risk_level/status/q 过滤） |
| GET | `/capabilities/{id}` | RESEARCHER | 详情 |
| POST | `/capabilities` | ADMIN | 创建 |
| PUT | `/capabilities/{id}` | ADMIN | 更新 |
| POST | `/capabilities/{id}/approve` | ADMIN | 审批生效 |
| POST | `/capabilities/{id}/deprecate` | ADMIN | 弃用 |
| DELETE | `/capabilities/{id}` | ADMIN | 删除 |
| GET | `/capabilities/{id}/fallback-chain` | RESEARCHER | 回退链 |

**Release Card 放行卡**（`release_card/router.py`，5 端点）：

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/release-cards` | 创建（可从委员会 case 生成） |
| GET | `/release-cards` | 列表 |
| GET | `/release-cards/metrics/summary` | 指标汇总 |
| GET | `/release-cards/{card_id}` | 详情 |
| POST | `/release-cards/{card_id}/review` | 人工评审（决策闭环） |

**Value Realization 收益**（`value_realization/router.py`，8 端点）：

| 方法 | 路径 | 说明 |
|---|---|---|
| PUT | `/value-baselines/{project_id}` | 基线 upsert |
| GET | `/value-baselines/{project_id}` | 基线查询 |
| GET | `/cost-rules` | 成本规则列表 |
| POST | `/cost-rules` | 新建规则 |
| PUT | `/cost-rules/{rule_id}` | 更新规则 |
| DELETE | `/cost-rules/{rule_id}` | 删除规则 |
| GET | `/value-reports/{project_id}` | 收益账单（JSON） |
| GET | `/value-reports/{project_id}/markdown` | 收益账单（Markdown） |

**Data Ingest 数据接入**（`data_ingest/router.py`，5 端点）：

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/ingest/field-dict/{entity_type}` | 字段字典 |
| POST | `/ingest/preview` | 映射 + 质量预览 |
| POST | `/ingest/commit` | 幂等提交写入 |
| GET | `/ingest/imports` | 导入批次列表 |
| GET | `/ingest/imports/{import_id}` | 批次详情（行级） |

### 6.2 `api.py` 直接端点分组（337 个）

| 域 | 代表路径 | 数量级 |
|---|---|---|
| 认证/用户 | `/auth/login`、`/auth/logout`、`/users/*` | ~15 |
| 项目 | `/projects/*`、`/projects/{id}/tasks` | ~20 |
| 候选材料 | `/candidates/*`、发现/对比/采纳 | ~25 |
| 性质预测 | `/predict/*` | ~10 |
| 合成 | `/synthesis/*`、任务管理 | ~12 |
| 工业化/配方 | `/formula/*`、合规/成本/BOM | ~18 |
| 物料/样品/设备 | `/raw-materials/*`、`/samples/*`、`/equipment/*` | ~35 |
| 实验 | `/experiments/*`、任务单/审批/数据录入 | ~30 |
| QC | `/qc/check/{id}`、`/qc/pending`、`/qc/{id}/approve`、`/qc/{id}/reject` | 4 |
| ECML | `/ecml/*`、运行控制/历史 | ~18 |
| Agent Team | `/agents/*`、编排/事件流 | ~20 |
| Hybrid | `/research/*`、意图/计划/执行 | ~15 |
| 委员会 | `/committees/*`、案例/证据/裁决 | ~20 |
| 控制平面 | `/control-plane/*`、策略/预算/运行/观测 | ~30 |
| MCP/SCP | `/tools/*`、SCP 目录/调用 | ~15 |
| MDM | `/mdm/*`（P1~P5 全域，见 6.3） | ~78 |
| 知识图谱 | `/knowledge/*` | ~8 |
| 评估 | `/evals/*` | ~8 |
| 版本/审计 | `/versions/*`、审计查询 | ~10 |
| 系统 | `/config`、`/health`、静态资源 | ~10 |

### 6.3 MDM 端点（~78 个，`/mdm/*`）

- **P1 参考字典**（GET+POST）：`/mdm/status-codes`、`/mdm/classifications`、`/mdm/units`、`/mdm/unit-conversions`（含 `POST /mdm/units/convert` 换算）、`/mdm/standards`、`/mdm/ghs-classes`、`/mdm/dimensions`
- **P2 主数据**（GET+POST）：`/mdm/sample-types`、`/mdm/sample-status-transitions`（含 `/check` 迁移校验）、`/mdm/locations`（含 `/{id}/tree` 位置树）、`/mdm/containers`、`/mdm/logistics-types`、`/mdm/equipment-templates`（含 `/{code}/capabilities`）、`/mdm/equipment-capabilities`、`/mdm/material-categories`
- **P3 CIMC**（GET+POST）：`/mdm/properties`、`/mdm/test-items`、`/mdm/test-methods`、`/mdm/specifications`、`/mdm/inspection-capabilities`
- **P4 工艺**（GET+POST）：`/mdm/process-routes`（含 `/{id}/steps`）、`/mdm/process-steps`（含 `/{id}/parameters`、`/{id}/equipment-templates`）、`/mdm/process-parameters`
- **P5 文档/快照**（GET+POST）：`/mdm/documents`、`/mdm/documents/{id}/versions`、`/mdm/document-versions/{id}`、`/mdm/order-snapshots/{id}`

---

## 7. 数据库与数据存储

### 7.1 统一 PostgreSQL 架构（v2.0 核心变更，v2.1 增 pgvector）

**引擎工厂**（`db.py`）：

```python
# 默认连接串（开发）
DATABASE_URL = postgresql+psycopg://batteryemcl:batteryemcl_dev@localhost:5433/batteryemcl

get_engine()   # SQLAlchemy Engine 单例（lru_cache）
               # QueuePool: pool_size=5, max_overflow=20, pool_pre_ping=True
reset_engine() # 清缓存（测试/热更新）
test_connection()  # SELECT 1 探活
get_session()  # 兼容性别名（需事务场景）
```

- **生产守卫**：`RUN_MODE=production` 且未显式配置 `DATABASE_URL` 时直接抛错，禁止静默回退开发连接串。
- **pgvector 扩展**（v2.1 新增）：docker-compose 使用 `pgvector/pgvector:pg16` 镜像；迁移 0028 检测并启用 `CREATE EXTENSION IF NOT EXISTS vector`，迁移 0029 将知识资产 embedding TEXT 占位列升级为 `vector(1024)`，支持语义相似度检索。
- **迁移完成度**：49+ 个 Store 文件全部走 `get_engine()`；全代码库 **零 `import sqlite3`**。Store 构造器的 `db_path` 参数仅为兼容旧调用方保留，实际已忽略。
- **Schema 划分**：按域分 schema — `mdm.*`（主数据 27+ 表）、`data_ingest.*`（imports/import_rows）、`audit.*`（含 `qc_decisions` JSONB 快照表）、`knowledge.*`（papers/materials/claims/graphs，含 vector(1024) embedding 列）、`agent_team.*`（activity_bindings/tool_registrations，v2.1 新增）、`integrations.*`（scp_tasks，v2.1 新增）及公共业务表。

### 7.2 Alembic 迁移（29 个版本）

| 版本 | 内容 |
|---|---|
| 0001 | 初始 schema |
| 0002 | 实验任务单状态迁移 |
| 0003 | QC 决策（audit.qc_decisions） |
| 0004 | 合规证据字段 |
| 0005 | 强外键约束 |
| 0006 | 材料属性模板 |
| 0007 | research_requests.scenario_id |
| 0008 | 项目任务 |
| 0009 | 业务链 MDM 基础 |
| 0010 | 内置 Agent 覆写 |
| 0011 | MDM P1 参考字典（7 表 seed） |
| 0012 | MDM P2 主数据（9 表） |
| 0013 | MDM P3 CIMC（5 表） |
| 0014 | MDM P4 工艺（6 表） |
| 0015 | MDM P5 FK 加固 + 血缘 |
| 0016~0019 | MDM 种子数据修复/填充/easpring 种子 |
| 0020 | 电池角色材料类型 |
| 0021 | 候选产物与工艺方案 |
| 0022 | 库存单位字段 |
| 0023 | 物料单位列改名 |
| 0024 | MDM 测试方法填充 + 订单幂等键 |
| 0025 | MDM 模板属性填充 |
| 0026 | SCP 异步任务表（integrations.scp_tasks） |
| 0027 | 活动↔Agent↔工具映射表（agent_team.activity_bindings/tool_registrations） |
| 0028 | 知识资产基础表（knowledge.papers/materials/claims）+ pgvector 扩展检测 |
| 0029 | pgvector embedding 列升级（TEXT → vector(1024)） |

### 7.3 遗留 SQLite 文件

`data/` 目录下 `*.db` 与 `*.db.bak.20260726` 为迁移前遗留备份（迁移脚本：`scripts/migrate_sqlite_to_postgres.py`，行数核验：`verify_migration_row_counts.py`）。运行期不再读写，可安全归档。

---

## 8. 依赖关系

### 8.1 Python 主依赖（`pyproject.toml`）

| 依赖 | 版本 | 用途 |
|---|---|---|
| fastapi / uvicorn | >=0.100 / >=0.23 | REST API 服务 |
| pydantic | >=2.0 | 数据模型与校验 |
| SQLAlchemy | >=2.0 | 统一 ORM/Engine |
| psycopg[binary] | >=3.1 | PostgreSQL 驱动（psycopg3） |
| alembic | >=1.13 | 数据库迁移 |
| httpx / requests | >=0.24 / >=2.31 | HTTP 客户端 |
| numpy / pandas | >=1.24 / >=2.0 | 数值计算 |
| rdkit | >=2023.3 | 分子/聚合物表示 |
| pymatgen | >=2023.10 | 晶体结构 |
| ase | >=3.22 | 原子模拟（EMT 回退） |
| pyscf | >=2.4 | DFT 计算（需 Python 3.11+） |
| python-dotenv | >=1.0 | 环境变量 |
| watchdog | >=3.0 | 文件监控 |
| openpyxl | >=3.1 | Excel 读写 |

可选：`ml = [torch>=2.0, scikit-learn>=1.3]`；`dev = [pytest, pytest-cov, pytest-asyncio, ruff]`。Python >= 3.10。

### 8.2 前端依赖

见 5.1。核心：vue 3.5 / vue-router 4.4 / pinia 2.2 / ant-design-vue 4.2 / axios / echarts 5.5 / xlsx / vite 5.4。

### 8.3 外部服务依赖

| 服务 | 配置 | 默认状态 |
|---|---|---|
| PostgreSQL 16 + pgvector | `DATABASE_URL`（docker-compose 使用 `pgvector/pgvector:pg16` 镜像，端口 5433→5432） | **必需** |
| LLM API（legacy） | `LLM_API_KEY`/`LLM_BASE_URL`（默认 LongCat） | 必需（AI 功能） |
| InternLM | `INTERNLM_API_KEY`/`INTERNLM_BASE_URL` | ENGINE_MODE=internlm 时必需 |
| SCP 工具平台 | `SCP_ENABLED=false` 默认关闭；`SCP_HUB_API_KEY`/`SCP_BASE_URL` | 可选（v2.1 增 SKILL 流水线 + 异步任务） |
| Materials Project | `MP_API_KEY` | 可选（晶体检索） |
| ASKCOS | `ASKCOS_BASE_URL=http://localhost:5000` | 可选（需独立部署 Docker） |

### 8.4 模块依赖关系（后端内部）

```text
api.py ──depends──> agent.py ──depends──> router/representation/generation/
│                                          prediction/industrialization/
│                                          synthesis/verification/experiment/
│                                          middleware/ecml
├──> capability.router ──> capability.registry ──> db.get_engine
├──> release_card.router ──> release_card.store ──> mdm.reference_dict（字典校验）
│                        └─> release_card.generator ──> committee.repository
├──> value_realization.router ──> calculator ──> projects / experiment.sample_store
├──> data_ingest.router ──> field_dict/mapping/store ──> db.get_engine
├──> agent_team.mapping_router ──> activity_mapping ──> db.get_engine（v2.1）
│                               └─> agent_proxy ──> control_plane.capability_router
├──> qc_service ──> middleware.wet_data.quality + db.get_engine（audit.qc_decisions）
├──> hybrid.* ──> control_plane.capability_router/model_router
├──> committee.* ──> control_plane（策略/预算）+ agent_team.executor
├──> mcp_tools.skill_executor ──> scp_catalog/scp_client/scp_policy（v2.1）
├──> integrations.scp_task_worker ──> scp_task_store/scp_task_locks ──> scp_client（v2.1）
├──> knowledge.ingestion ──> asset_store/credibility ──> db.get_engine（v2.1）
└──> 所有 Store ──> db.get_engine() ──> PostgreSQL + pgvector
```

---

## 9. 项目运行方式

### 9.1 环境准备

```bash
# 1. Python 环境（>=3.10；DFT 功能需 3.11+）
pip install -e .            # 安装主依赖
pip install -e .[ml,dev]    # 可选：ML 与开发依赖

# 2. 启动 PostgreSQL + pgvector（Docker）
docker compose up -d postgres
# 容器 batteryemcl-postgres，镜像 pgvector/pgvector:pg16
# 宿主机端口 5433 → 容器 5432
# 用户/库：batteryemcl / batteryemcl（密码 batteryemcl_dev，仅开发用）

# 3. 配置环境变量
cp .env.example .env        # 按需填写 LLM_API_KEY / INTERNLM_API_KEY 等

# 4. 执行数据库迁移
alembic upgrade head        # 29 个迁移，含 MDM 种子数据 + pgvector 扩展 + 知识资产表
```

### 9.2 启动服务

```bash
# 后端（端口 8000）
uvicorn battery_materials_agent.api:app --host 0.0.0.0 --port 8000 --reload

# 或使用 CLI
python -m battery_materials_agent.cli serve

# 前端（端口 5173，代理 /api → 127.0.0.1:8000）
cd frontend
npm install
npm run dev
```

访问：`http://localhost:5173`（开发）或后端静态托管 `frontend/dist`（生产，`npm run build` 后由 FastAPI StaticFiles 服务）。

### 9.3 生产部署要点

- `RUN_MODE=production` 时必须显式配置 `DATABASE_URL` 与 `AUTH_TOKEN_SECRET`（HMAC 密钥，`python -c "import secrets; print(secrets.token_hex(32))"` 生成）。
- `ADMIN_DEFAULT_PASSWORD`：首次创建 admin 时读取。
- 跨域部署前端时配置 `CORS_ALLOWED_ORIGINS` 白名单（禁 `*`）。

### 9.4 数据迁移（旧 SQLite 部署升级）

```bash
python scripts/migrate_sqlite_to_postgres.py    # SQLite → PostgreSQL
python scripts/verify_migration_row_counts.py   # 行数核验
python scripts/verify_business_chain_e2e.py     # 业务链 E2E 验证
```

### 9.5 常用运维脚本

| 脚本 | 用途 |
|---|---|
| `scripts/seed_raw_materials.py` | 物料库种子数据 |
| `scripts/verify_mdm_api_regression.py` | MDM API 回归 |
| `scripts/verify_mdm_fk_integrity.py` | MDM 外键完整性 |
| `scripts/verify_regression_smoke.py` | 回归冒烟 |
| `scripts/reset_stuck_committee_cases.py` | 卡死委员会案例重置 |
| `scripts/cleanup_ecml_runs.py` | ECML 运行清理 |
| `scripts/scan_db_corruption.py` | 数据腐坏扫描 |

---

## 10. 测试体系

### 10.1 测试结构（`tests/`，pytest，`asyncio_mode=auto`）

| 层级 | 文件 | 覆盖 |
|---|---|---|
| 根级回归 | `test_regression_core.py`、`test_approval_gate.py`、`test_qc_explainability.py`、`test_wet_data_pipeline.py`、`test_experiment_mode_isolation.py`、`test_workflow_schema.py` | 核心链路回归、审批门禁、QC 可解释性、湿数据管道 |
| `tests/unit/`（24 个） | `test_router`、`test_generation`、`test_prediction`、`test_verification`、`test_synthesis`、`test_ecml`、`test_experiment`、`test_experiment_order_state_machine`、`test_middleware`、`test_mcp_tools`、`test_auth_tokens`、`test_agent_events`、`test_research_event_stream`、`test_chemistry_rules`、`test_formula_validator`、`test_formula_cost_ehs`、`test_compliance_evidence`、`test_strong_fk_associations`、`test_crystal_representation`、`test_polymer_representation`、`test_synthesis_tasks`、`test_ecml_run_source` 等 | 单元级 |
| `tests/integration/` | `test_agent.py`、`test_api.py`、`test_api_fallback.py` | API/Agent 集成 |

### 10.2 运行测试

```bash
pytest                          # 全部
pytest tests/unit -v            # 单元
pytest tests/integration -v     # 集成
pytest --cov=battery_materials_agent   # 覆盖率
```

前端 E2E：Playwright（`frontend/` 内 `*.mjs` 调试/测试脚本 + `screenshots/` 截图报告）。

---

## 11. 关键实现说明与已知限制

### 11.1 关键实现约束（硬性）

- **数据库**：所有 Store 必须走 `db.get_engine()`（SQLAlchemy 2.0 + psycopg3）；禁止新增 `import sqlite3`；Store 构造器 `db_path` 参数仅兼容保留，实际忽略。
- **生产守卫**：`RUN_MODE=production` 未配置 `DATABASE_URL` 直接抛错。
- **迁移**：schema 变更必须走 Alembic 迁移脚本，禁止手工改库。
- **QC 统一入口**：新代码一律用 `qc_service.check_record()`；`data_ingest/quality.py` 已 deprecated。
- **放行卡校验**：ReleaseCard 写入前必须过 MDM 字典校验（status/recommendation/evidence_category）。
- **收益铁律**：指标必须标 verified/estimated，estimated 必须写 assumption；数据不足 `value=None`，严禁编造。
- **证据原则**：放行卡六类证据"有什么填什么"，缺失保持 None，绝不编造证据内容。
- **幂等**：data_ingest 提交用 `idempotency_key` 防重复写入。
- **异步**：后端 ECML run steps 用 `asyncio.to_thread` 防事件循环阻塞；所有中间件 async/await。
- **审计**：QC 决策快照（JSONB）写 `audit.qc_decisions`；能力契约写操作记审计，失败不阻断主流程。
- **LLM 解析**：响应解析含非 JSON 容错，单候选失败隔离。
- **前端硬约束**：AgentFlowGraph 用 `position:absolute+visibility:hidden` 隐藏（非 v-show）保持容器尺寸；ECharts 初始化带重试（100ms×10~20 次）；节点初始圆环坐标防力导重叠；重试定时器卸载清理；Pinia 状态只能经 action 修改；MoleculeView 用 textContent 防 XSS、WebGL 关闭显式清理、SvgDrawer 实例级。

### 11.2 前端 UX 规范

- **Agent 显性表达**：所有真实调用 Agent 的业务环节（新建项目、候选材料、性质预测、合成路径、ECML 闭环、配方生成）通过 `AgentChip` 显性展示执行 Agent 及介绍。
- **禁用按钮原因**：禁用操作按钮经 `a-tooltip` 显示禁用原因，全局 `.tt-btn-wrap` 包裹层保证禁用态 tooltip 触发。

### 11.3 已知限制

1. DFT 验证受 Python 版本限制（PySCF 需 3.11+）。
2. GNoME 数据集未真实接入（本地硬编码，仅标记 source="gnome"）。
3. ECML start_time 时区不一致（UTC vs 本地时间混用）。
4. 前端 ECharts chunk 过大（500KB+ gzip，待按需加载拆分）。
5. 聚合物预测模型（PolymerGNN）未接入真实预训练权重，使用 ASE-EMT/RDKit 描述子回退。
6. 跨尺度计算引擎（CrossScaleEngine）为占位实现。
7. 电池循环数据库（BatteryCycleDatabase）为占位实现。
8. ASKCOS 服务需独立部署 Docker 容器，本地开发可能不可用。
9. Committee 与 Control Plane 默认关闭，需显式配置环境变量启用。
10. SCP 外部工具依赖外部 API 可用性，默认关闭；SKILL 流水线与 SCP 异步任务系统（v2.1 新增）依赖 SCP 启用。
11. 认证为 HMAC 签名 token 方案（`X-Auth-Token`），非标准 JWT/OAuth2。
12. `value_realization/calculator.py` 中部分 Store 调用仍传旧 `db_path` 参数（兼容残留，实际已走全局 Engine）。
13. `data/` 目录遗留 SQLite `.db`/`.bak` 文件未清理（运行期不再读写）。
14. 知识资产层（v2.1 新增）的 embedding 向量检索需 pgvector 扩展；未启用 pgvector 时退化为空检索。
15. 业务活动↔Agent↔工具三层映射（v2.1 新增）的绑定关系需在映射控制台手工配置或由 seed 数据初始化。

---

## 附录：关键数据模型速查表

| 模型 | 所在模块 | 用途 |
|---|---|---|
| `MaterialInput` / `RouterResult` | router | 路由输入/输出 |
| `CrystalCandidate` / `PolymerCandidate` | generation | 候选材料 |
| `ComplianceReport` / `Recipe` | industrialization | 合规/配方 |
| `PredictionResult` | prediction | 预测结果 |
| `SynthesisRoute` | synthesis | 合成路径 |
| `VerificationResult` | verification | 验证结果 |
| `ExperimentOrder` / `ExperimentResultRecord` | experiment | 任务单/结果 |
| `ApprovalRule` / `ApprovalDecision` | experiment（approval） | 审批规则/决策 |
| `Sample` / `SampleTransfer` / `Equipment` / `Idea` | experiment | 样品/转移/设备/假设 |
| `ExperimentRecord` | middleware | 湿实验记录 |
| `QCResult` / `QCRuleResult` | middleware.wet_data.quality | QC 可解释结果 |
| `ECMLState` | ecml | 闭环状态 |
| `AgentDefinition` / `TaskStep` / `OrchestrationPlan` / `ExecutionEvent` | agent_team | 协作编排 |
| `ResearchRequest` / `ResearchPlan` / `TaskStepV3` / `EvidenceSummary` | hybrid | 混合编排 |
| `CommitteeCase` / `Proposal` / `EvidenceItem` / `CommitteeVerdict` | committee | 委员会决策 |
| `Run` / `Checkpoint` | control_plane.run_manager | 运行管理 |
| `BudgetScope` / `BudgetEnvelope` | control_plane.budget | 预算管理 |
| `ExecutionContext` | control_plane.context | 执行上下文 |
| `ToolBinding` / `RiskLevel` | mcp_tools.scp_catalog | SCP 工具绑定 |
| `CapabilityContract` | capability.models | 能力契约（适用域/回退链/风险） |
| `ReleaseCard` | release_card.models | 放行卡（六类证据/五结论） |
| `ProjectBaseline` / `CostRule` / `MetricValue` | value_realization.models | 收益证明 |
| `StatusCode` / `Unit` / `Standard` / `Dimension` | mdm.reference_dict | P1 参考字典 |
| `SampleType` / `Location` / `EquipmentTemplate` | mdm.master_data | P2 主数据 |
| `Property` / `TestItem` / `TestMethod` / `Specification` | mdm.cimc | P3 CIMC |
| `ProcessRoute` / `ProcessStep` / `ProcessParameter` | mdm.process | P4 工艺 |
| `ENTITY_FIELD_DICT` | data_ingest.field_dict | 四实体字段字典 |
| `PropertyField` / `PropertyCategory` | material_properties | 属性注册 |
| `User` / `UserRole` | auth | 用户/角色 |
| `Project` / `ProjectTask` | projects | 项目/任务 |
| `Version` | version_store | 版本记录 |
| `AuditEntry` | audit | 审计日志 |
| `ExternalInvocation` | integrations | 外部调用 |
| `ChatRequest` / `ChatResponse` / `ProviderHealth` | llm | LLM 协议 |
| `CandidateRecord` | experiment.candidate_store | 候选持久化 |
| `ActivityAgentBinding` / `AgentToolBinding` / `ToolRegistration` | agent_team.activity_mapping | 活动↔Agent↔工具映射（v2.1） |
| `SkillBinding` / `SkillPipelineStep` / `SkillRiskLevel` | mcp_tools.skill_catalog | SKILL 声明式流水线（v2.1） |
| `Paper` / `Material` / `Claim`（通过 Store 暴露） | knowledge.asset_store | 三层知识资产（v2.1） |
| `SOURCE_TIER_SCORES` / `EVIDENCE_LEVEL_SCORES` | knowledge.credibility | 双维度可信度评分（v2.1） |

---

*本文档基于源代码分析生成，所有信息均直接来源于代码事实。*
*文档版本 v2.0.0，更新日期 2026-07-27（PostgreSQL 统一架构 + MDM/能力契约/放行卡/收益证明/数据接入五大新模块）。*
