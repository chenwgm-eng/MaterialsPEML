# MaterialsPEML Lab · Code Wiki

> 高分子改性塑料 AI 研发平台（kingfa 领域）· 开发者维基
>
> 版本：v4.1.0 · 文档更新：2026-08-11
>
> 配套文档：`CONTEXT.md`（领域术语）、`docs/adr/`（架构决策）、`docs/产品说明书.md`（产品）、`docs/用户使用手册.md`（操作）、`系统架构说明书.md`（架构）

---

## 目录

- [1. 项目概览](#1-项目概览)
- [2. 技术栈](#2-技术栈)
- [3. 目录结构与架构地图](#3-目录结构与架构地图)
- [4. 核心概念与领域模型](#4-核心概念与领域模型)
- [5. 数据可信度体系（四档）](#5-数据可信度体系四档)
- [6. 关键链路](#6-关键链路)
- [7. 数据库](#7-数据库)
- [8. 前端架构](#8-前端架构)
- [9. 开发陷阱（血泪清单）](#9-开发陷阱血泪清单)
- [10. 测试策略](#10-测试策略)
- [11. 常用命令](#11-常用命令)
- [12. 迁移历史与版本演进](#12-迁移历史与版本演进)

---

## 1. 项目概览

MaterialsPEML Lab 是面向**高分子改性塑料（金发科技 kingfa 领域）**研发场景的 AI 辅助平台：从"一句话研发目标"出发，完成材料体系识别 → 候选配方生成 → 性能估算 → 工业化验证 → 实验闭环 → 反馈迭代的完整研发链路。

**核心定位**：
- 数据可信度四档审计链（实测/模拟/模型预测/工程估算），每一数值可回答"从哪来、可信度几何"
- 实验闭环（ECML）带验证精度指标（估算 vs 实测 MAPE）
- 新人零门槛：智能目标框输入一句话即可开始
- 多租户 + 细粒度权限 + 审计日志（企业级）

**版本历史**：v3.0（电池时代）→ v4.1（全面切换改性塑料，见 [12](#12-迁移历史与版本演进)）。

---

## 2. 技术栈

| 层 | 技术 |
|---|---|
| 前端 | Vue 3 + Vite + Pinia + ant-design-vue 4 + ECharts + Playwright（E2E） |
| 后端 | Python 3.10 + FastAPI + SQLAlchemy 2.0 + Pydantic v2 |
| 数据库 | PostgreSQL 16（+ pgvector，知识资产 embedding） |
| 迁移 | Alembic（当前 head：0060_kingfa_target_thresholds） |
| LLM | InternLM（LongCat）/ 本地 LLM，ProviderFactory 统一 |
| 计算 | RDKit / pymatgen / ASE / Multiwfn（适配器隔离，占位路径显式标注） |
| 集成 | SCP（远程科学服务，异步任务）/ ASKCOS（逆合成）/ GNoME（材料库） |

**Python 环境**：必须用 `C:\Users\chenw\AppData\Local\Programs\Python\Python310\python.exe`（系统默认是 Miniconda，无项目依赖）。

---

## 3. 目录结构与架构地图

```
BatteryEMCL Lab/
├── battery_materials_agent/
│   ├── api.py                  # 单体 FastAPI（~1.7 万行，全部路由，SPA fallback + 中间件）
│   ├── agent.py                # BatteryMaterialsAgent 门面（MCP 工具 handler 注册）
│   ├── config.py               # AgentConfig / EngineMode / RunMode
│   ├── db.py                   # 引擎 + ContextVar 租户（set_tenant/get_tenant/tenant_filter）
│   ├── material_properties.py  # 属性注册表 + REFERENCE_RANGES（绝对评分基准，ADR-0003）
│   ├── experiment/             # candidate/process_scheme/equipment/experiment_controller 存储层
│   ├── generation/             # crystal/polymer 候选生成（polymer 查表法）
│   ├── ecml/                   # 闭环引擎（validation_metrics/阈值/模拟分派）+ BO（贝叶斯优化）
│   ├── hybrid/                 # 研发流水线（orchestrator/pipeline/intent_interpreter）
│   ├── prediction/             # polymer/crystal 预测器（descriptor_heuristic 分层）
│   ├── industrialisation/      # 领域包 / FormulaAgent / 物料库 / 工艺深化
│   ├── knowledge/              # 知识资产（paper/material/claim + 可信度双维）
│   ├── agent_team/             # 多智能体（executor/agents/*）
│   ├── mcp_tools/              # 工具注册（local/SCP/SKILL）
│   ├── release_card/           # 放行卡（状态机 + 审批）
│   ├── committee/              # 委员会（外部证据/偏差复盘）
│   ├── auth/                   # 认证（HMAC token/SSO/LDAP）+ 权限点
│   ├── control_plane/          # 预算/工具网关/策略/审计（可选启用）
│   ├── middleware/             # 数据中间件（湿数据 QC/归一化）
│   ├── data_ingest/            # CSV/Excel 导入（实体映射 + 质量检查）
│   └── router/                 # 材料类型路由（高分子/晶体）
├── frontend/src/
│   ├── views/                  # 44 个页面
│   ├── components/             # 全局组件（GoalIntentInput/EvidenceBadge/EmptyState…）
│   ├── stores/                 # Pinia（discovery/ecml/projects/projectContext…）
│   ├── api/                    # axios client（统一鉴权/错误转译）
│   ├── layouts/                # IconRail 导航壳 + menuConfig（角色菜单）
│   └── tests/                  # Playwright E2E（deep/modal/danger/…audit）
├── alembic/versions/           # 0060 个迁移
├── tests/unit/                 # pytest（574 个，连真实 PostgreSQL）
├── docs/                       # 文档（本维基/ADR/产品/用户手册）
├── CONTEXT.md                  # 领域术语表（权威）
└── AGENTS.md                   # AI 协作指令（开发陷阱）
```

**模块职责速查**：
- `api.py`：所有 HTTP 端点 + 中间件（`rewrite_api_prefix_middleware` 处理 /api 前缀）
- `agent.py`：业务门面，聚合所有 store/predictor/generator，MCP 工具 handler
- `ecml/ecml_engine.py`：7 步闭环（route→generate→industrialization→predict→verify→experiment→feedback）
- `ecml/bo.py`：贝叶斯优化推荐（高斯过程等代理模型 + 采集函数）
- `generation/polymer_candidate_generator.py`：工程塑料候选（查表法 + 增强加成，无派生系数）
- `industrialisation/domain_pack_store.py`：领域包（kingfa 默认，DB 持久化，Settings 页切换）

---

## 4. 核心概念与领域模型

领域术语权威定义见 `CONTEXT.md`。开发者必读：

| 概念 | 定义 | 关键代码 |
|---|---|---|
| 候选材料 | 研发流水线产出的待评估提案（高分子=PSMILES 标识；工程塑料=基材×增强组合） | `generation/` |
| 材料体系 | 树脂体系（PA6/PC/ABS/PP…），决定骨架库与参考性能 | `REFERENCE_PROPERTIES` |
| 领域包 | 企业研发领域默认配置（默认目标/配方模板/阈值），默认 kingfa | `domain_pack_store.py` |
| 候选状态机 | screening→feasible→process_planning→process_confirmed→ready_for_experiment，可拒绝 | `candidate_store.CANDIDATE_ALLOWED_TRANSITIONS` |
| 放行卡 | 候选下单审批门（draft→pending_review→decided，decided 终态） | `release_card/store.py` |
| 实验闭环 ECML | 7 步闭环迭代，目标达标判定用参考阈值 | `ecml/ecml_engine.py` |
| 综合评分 | 绝对规格基准归一化加权得分（跨 run 可比） | `material_properties.REFERENCE_RANGES` |
| 智能目标框 | 一句话目标→体系/属性自动回填 | `GoalIntentInput.vue` + `/parse-goal` |

**术语红线（ADR-0001）**：只有带真实权重的模型（Tg/介电常数 PolymerGNN）能称"预测"；描述符启发式产出一律标"工程估算"（`descriptor_heuristic` 标签 + confidence≤0.5 + evidence_level="estimated"）。**禁止**给启发式结果标 predicted/simulated。

---

## 5. 数据可信度体系（四档）

每个数值必须回答"从哪来、可信度几何"：

| 档位 | 来源 | 落库标记 | 前端徽标 |
|---|---|---|---|
| 实测 measured | 实验设备/人工录入，QC 审批通过 | `data_quality="verified"` + provenance | EvidenceBadge 绿 |
| 模拟 simulated | demo 模式确定性伪随机（围绕估算值±10%） | `data_quality="simulated"` + `learning_eligible=False` | EvidenceBadge 橙 |
| 模型预测 predicted | 真实权重模型（Tg/介电常数） | `data_quality="predicted"` | EvidenceBadge 蓝 |
| 工程估算 estimated | 查表法/描述符启发式 | `data_quality="estimated"` + confidence≤0.5 | EvidenceBadge 灰 |

**审计规则**：
- 模拟值**永不进学习池**（ECML feedback 按 data_quality 过滤），但 `validation_metrics` 含模拟（审计展示语义，二者分离，ADR-0002）
- 所有实验记录写 `provenance JSONB`（人工/导入/ECML/模拟各有 source_type）
- 候选属性查表带 `property_source`（CAMPUS/GB-T 来源标注）

---

## 6. 关键链路

### 6.1 研发闭环（hybrid）
```
用户一句话目标 → /parse-goal（意图解析+体系推断）→ ResearchWorkbench 表单回填
→ /research/requests 创建 → 流水线执行（route→generate_polymer_candidates
→design_formula→predict_polymer_properties→compliance_check）
→ 事件流驱动前端进度 → 候选落库
```

### 6.2 ECML 闭环（7 步）
```
step1 route（材料路由）→ step2 generate（候选生成，material_system 透传工程塑料模式）
→ step3 industrialization（配方合规+成本）→ step4 predict（描述符估算）
→ step5 verify（DFT 仅有机分子；高分子/晶体 predicted_only）
→ step6 experiment（demo 模拟围绕估算±10%；production 建单等待数据）
→ step7 feedback（阈值判定 + validation_metrics 估算vs实测 MAPE）→ 下一轮
```

### 6.3 实验数据链路
```
录入（人工/CSV/ECML 模拟）→ 规范化（prop.*/method.*/unit FK）→ QC（规则+learning_eligible）
→ 审批 → 学习池 / 偏差分析（detect_prediction_deviation，预期值来自候选估算）
```

---

## 7. 数据库

- PostgreSQL `batteryemcl`，schema 按域划分：`experiment.*`、`ecml.*`、`mdm.*`（主数据）、`knowledge.*`、`industrialisation.*`、`release_card.*`、`committee.*`、`control_plane.*`、`gnome.*`、`audit.*`
- **FK 空串陷阱**：所有外键列写入必须 `value or None`（空串触发 ForeignKeyViolation）
- **MDM 主数据有 FK**：`property_name→mdm.properties`、`unit→mdm.units`、`test_method→mdm.test_methods`、物料 `category→mdm.classifications`——新增须先入表（迁移 0058 已播种高分子属性/单位/GB-T 方法）
- 关键迁移：0058（高分子 MDM）、0059（provenance 列）、0060（kingfa 阈值）

---

## 8. 前端架构

- 导航壳：IconRail（4 入口：工作台/项目/能力库/管理）+ 二级菜单（`menuConfig.js`，角色过滤 + researchHidden）
- 全局组件：`GoalIntentInput`（智能目标框）、`EvidenceBadge`（可信度徽标）、`EmptyState`（空态引导）
- 状态：Pinia（discovery/ecml/projects/projectContext/system…），localStorage 无 key 冲突
- E2E：`frontend/tests/*.mjs`（Playwright，需 5173+8200 双活，admin/admin123）

---

## 9. 开发陷阱（血泪清单）

1. **ant-design-vue 4**：`@row-click` 已移除（用 `:custom-row`）；折叠面板默认收起用 `default-active-key`（`:active-key` 受控锁死）；图标名必须是真实导出
2. **vite proxy 不 rewrite**：`/api` 原样转发，由后端 `rewrite_api_prefix_middleware` 处理；剥掉 `/api` 会让 `/ecml/runs` 等命中 SPA fallback
3. **FK 空串**：外键列必须 `value or None`
4. **candidate_store.save()** 默认 content_hash 去重短路——回写字段必须 `dedup=False`
5. **工具名 ≠ 语义别名**：`CapabilityRouter.resolve()` 按 alias，编排 executor 持有 MCP 工具名——须 `tool_to_alias()` 反向映射
6. **SCP 健康探测**：MCP 端点只收 POST；SCP 用 `list_tools` 探测，LLM 用 `GET /models`
7. **回退必须透明**：合成路线带 `source`，深化来源记 `evidence_refs`，UI 展示徽标
8. **MDM 分类短码陷阱**：设备/物料分类必须用 DB 全码（`equipment.test` 而非 `test`）
9. **ECML feedback 数据源**：用 `experiment_controller._store.list_result_records()`（带 data_quality/provenance），**不要**用 `middleware.query_records`（忽略 formula 参数、无 data_quality）
10. **run_mode 切换**：`/config` 同步 `experiment_controller.run_mode`（无需重启）；demo 模拟落库必须标 simulated
11. **评分口径**：生成器 `_apply_polymer_multi_objective` 与后端 `_backfill_multi_objective_scores` 必须同用 `REFERENCE_RANGES`（绝对基准），前端 objectiveConfig 与 `_SCORE_PROPS` 对齐
12. **编辑文件注意**：局部变量不得命名 `props`（遮蔽 defineProps）；computed 不得嵌在 onMounted 内（模板不可见）
13. **放行卡状态**：MDM 合法值为 draft/pending_review/decided（无 pending）

---

## 10. 测试策略

- 后端：`python -m pytest tests/unit/ -q`（574 个，连真实 PostgreSQL；Fake 夹具需实现 `plan_multiple_routes`）
- 重点文件：`test_grilling_features.py`（v4.1 新能力：parse-goal/查表法/validation_metrics/放行卡迁移/模拟联动/术语分层）
- 前端 E2E：`deep-audit.mjs`（全页按钮）、`modal-audit.mjs`（弹窗）、`danger-audit.mjs`（危险按钮）——改菜单/页面后必须跑
- 巡检脚本会断言菜单项，删菜单需同步更新脚本

---

## 11. 常用命令

```bash
# 后端（工作目录 D:\BattleFish\BatteryEMCL Lab）
"C:\Users\chenw\AppData\Local\Programs\Python\Python310\python.exe" -m uvicorn battery_materials_agent.api:app --host 0.0.0.0 --port 8200
# 改后端代码必须重启 8200

# 前端
npm run dev     # :5173（HMR 自动生效）
npm run build   # frontend 目录

# 迁移
"C:\Users\chenw\AppData\Local\Programs\Python\Python310\python.exe" -m alembic upgrade head

# 测试
"C:\Users\chenw\AppData\Local\Programs\Python\Python310\python.exe" -m pytest tests/unit/ -q

# E2E（需 5173+8200 双活）
node frontend/tests/deep-audit.mjs
```

---

## 12. 迁移历史与版本演进

- **v3.0（电池时代）**：PostgreSQL 化、MDM 主数据、Capability 契约、Release Card、Data Ingest、多租户（0050）、SSO/LDAP（A2）、细粒度权限（A3）、审计（A4）、报表（A5）、GNoME 库（0052-0054）
- **v4.1（改性塑料全面切换）**：
  - 界面/默认值/术语全面高分子化（实验模板 GB-T 体系、知识库关键词、生成器查表法）
  - ADR-0001 术语分层（估算 vs 预测）、ADR-0002 模拟审计（provenance 列）、ADR-0003 绝对评分基准
  - 智能目标框（`/parse-goal` + `GoalIntentInput`，集成研发工作台/项目创建/编排）
  - ECML 闭环验证精度（`validation_metrics` MAPE）、模拟实验围绕估算值±10%
  - MDM 高分子主数据（迁移 0058）、provenance 列（0059）、kingfa 阈值（0060）
  - 放行卡迁移图、BO 方向统一、多轮穷举审查修复 75+ 缺陷
