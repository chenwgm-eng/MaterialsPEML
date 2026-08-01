# 《BatteryEMCL Lab 全功能实操评测与整改建议书》

- 评审日期：2026-07-29
- 评审环境与版本：本地开发环境，前端 http://localhost:5173/，后端 http://localhost:8000/
- 评审账号/角色（脱敏）：U-9AF74283 / admin
- 覆盖范围：核心研发链路（项目→候选→预测→合成→配方→实验→QC→样品→PEML 闭环）、数据/知识/AI/管理模块、后端 API 与代码审查
- 实操数据集与清理状态：ASSB-LPSCl-2026Q3-V2_1 (PROJ-3DB94354)、PEO-LiTFSI-2026Q3_1 (PROJ-34890B52)
- 已完成操作数：124 次后端 API 调用、36 个前端页面/路由加载与交互、297 张 Playwright 截图证据
- 已实操验证缺陷数（P0/P1/P2/P3）：P0=3 / P1=6 / P2=6 / P3=6（去重合并后）
- 高概率推断项数：5 项（详见第 2.3 节未验证清单）
- 未验证项数及原因：5 项，主要受限于外部 LLM/SCP/ASKCOS 服务状态、并发场景构造能力及浏览器运行时内存分析工具（详见 2.3）
- 报告版本：v1.0

## 1. 执行摘要

### 1.1 当前成熟度判断（只能选一项：概念验证 / 内部试用 / 受控试点 / 可正式交付）

**受控试点**。理由如下：

- 核心端到端数据流（项目→候选发现→批量预测→合成规划→实验任务→结果录入→QC 审批→样品→PEML 闭环）已能在后端 API 层贯通，且产生可追踪的数据对象 ID。
- 但存在 3 个 P0 阻断性缺陷（性质预测页面白屏、配方与工艺核心操作 500、调用关系路由 404），直接阻碍真实材料团队的日常闭环使用。
- 另有 6 个 P1 缺陷分布在合成多路径规划、成本仪表盘、实验/样品 FK 校验、/experiments 空引用报错以及 Ant Design Vue overlay 指针拦截等关键路径。
- AI/Agent 治理链、数据质量标记、状态机并发控制、异步任务生命周期等基础设施尚未完全落地，尚不具备正式交付条件。

### 1.2 最值得保留的实现与原因

1. **Capability Registry（能力契约中心）**：已支持契约状态、风险等级、fallback 链与缓存，具备统一的工具/能力治理骨架，可作为后续所有 AI 调用的总闸门。
2. **端到端数据对象关系**：项目、候选、配方、实验任务单、结果、QC、样品之间的外键与审计轨迹（`experiment_order_status_transitions` 等）已初步建立，正查/反查可通。
3. **QC 引擎（`qc_service.py`）**：完整性、合理性、样品匹配规则统一，支持 QC 检查与审批状态流转，是数据可信的核心抓手。
4. **Alembic 迁移与 RESTRICT 外键**：0005 版本对 candidate/order/sample/result/transfers 统一加 `ON DELETE RESTRICT`，从数据库层防止误删导致的数据孤儿。
5. **数据接入（data-ingest）与导入幂等**：预览→提交→重复导入幂等（`duplicated=true`）已跑通，为数据资产沉淀提供了入口。

### 1.3 最重要的 P0/P1 风险

**P0 风险**：

- **BEMCL-PRED-P0-001**：性质预测页面渲染崩溃（`ReferenceError: energyPerAtomUnit is not defined`），核心操作返回空，候选表格无法展示。
- **BEMCL-FORMULA-P0-003**：配方与工艺页面调用 `/api/mcp/tools/design_formula/call` 返回 500，BOM 行数为 0，配方研发链路断裂。
- **BEMCL-TOPO-P0-001**：调用关系页面 `/topology` 路由直接返回 404，系统拓扑可视化不可用。

**P1 风险**：

- **BEMCL-SYN-P1-001**：`/synthesis/plan/multi` 返回 500（`KeyError: 0`），多路径合成规划失败。
- **BEMCL-DASH-P1-002**：`/dashboard/cost` 返回 500（datetime 不可下标），成本分析不可用。
- **BEMCL-EXP-P1-003 / BEMCL-SMP-P1-004**：创建实验任务单/样品时未校验 candidate_id/source_candidate_id，导致 FK 违反时直接 500。
- **BEMCL-EXP-P1-002**：实验数据页面出现 `TypeError: Cannot read properties of null (reading 'project_id' / 'emitsOptions')`。
- **BEMCL-UI-OVERLAY-P1-001**：Ant Design Vue 下拉/弹窗默认挂载到 body，导致多个页面指针事件被 overlay 拦截，影响 /experiments 编辑、/mdm 保存等关键操作。

### 1.4 整改策略与推荐整改顺序

推荐顺序：**P0 止血 → 后端 500 与 FK 校验 → 前端 overlay 与空引用 → AI 治理链补全 → LIMS/ELN 数据质量标记 → UI/UX 与视觉体系 → 试点交付**。

具体阶段：

1. **阶段 0（1–2 周）**：修复 3 个 P0、4 个后端 P1 导致的 500，恢复核心链路可用性；补齐 `/topology` 路由或隐藏入口。
2. **阶段 1（2–3 周）**：统一 `a-select` / `a-modal` 的 `getPopupContainer` 策略，修复 /experiments 空引用，恢复所有页面可交互性。
3. **阶段 2（3–4 周）**：实验/样品状态机加锁、数据质量 `verified/estimated` 标记、MDM 与属性字典校验落地。
4. **阶段 3（4–6 周）**：将 discover/orchestrate 的 LLM 调用纳入 Tool/Skill/SCP 治理链，建立 AI 委员会门禁、输入快照、版本与置信度。
5. **阶段 4（4–6 周）**：重构信息架构、工作台、向导、空态、状态色与视觉系统。
6. **阶段 5（持续）**：受控试点，收集真实新材料团队反馈，再决定商业化交付。

## 2. 测试方法、环境与局限

### 2.1 证据分级规则（[已实操验证] / [高概率推断] / [待确认]）

- **[已实操验证]**：通过 Playwright 或 Python `requests` 实际执行并记录响应/截图/控制台日志的条目。所有 P0/P1/P2/P3 缺陷均附带证据编号（EV-YYYYMMDD-NNN）或后端 API 调用记录（AG1、P1、S2 等）。
- **[高概率推断]**：基于代码审查、alembic 约束、错误堆栈或单一症状可合理外推的结论，但缺少直接边界触发证据。例如异步任务 GC 风险、状态机竞态、ON DELETE RESTRICT 的删除阻断效果。
- **[待确认]**：需要外部服务状态、高并发构造、GPU/内存分析或更多日志才能最终判定。例如 `/orchestrate/analyze` 超时根因、异步任务取消与队列积压、MoleculeView WebGL 清理等。

### 2.2 环境、权限、外部服务与数据限制

- **前端**：Vite dev server（`npm run dev`），Chromium headless / viewport 1920×1080，Node Playwright 1.62.0。
- **后端**：Python FastAPI，PostgreSQL，SQLAlchemy QueuePool（pool_pre_ping=true）。
- **认证**：`POST /auth/login` 获取 token，后续请求携带 `X-Auth-Token`；全局 `dependencies=[Depends(get_current_user)]` 对匿名用户按 VIEWER 放行。
- **外部服务**：LLM/SCP/ASKCOS 为 demo 环境，超时设置为 30–60s；未触发预算不足、权限不足、服务降级等边界。
- **账号**：仅验证 admin 角色，未覆盖 viewer/scientist/operator 等角色的页面与按钮级权限。
- **数据**：使用两个 ASSB-LPSCl 与 PEO-LiTFSI 测试项目；未进行高并发、脏数据注入、大文件导入、跨项目数据隔离测试。
- **浏览器**：Playwright Python 模块未安装，使用 Node Playwright；部分 `a-select` 通过 URL query 或浏览器注入脚本绕过 overlay 交互。

### 2.3 未验证清单及最小补测条件

| 编号 | 未验证项 | 原因 | 最小补测条件 |
| --- | --- | --- | --- |
| UV-001 | AI/预测/推荐超时、重试、降级、取消、权限不足、预算不足异常场景 | 依赖外部 LLM/SCP/ASKCOS 服务状态与预算配置，当前 demo 环境未触发相关边界 | 构造 LLM 超时/429/503、预算耗尽、角色无权限等 mock 场景 |
| UV-002 | 异步任务取消、队列积压、锁竞争场景 | 需要构造高并发或慢速 SCP 任务才能触发，当前单客户端顺序测试未覆盖 | 使用多客户端并发请求 + 慢速工具 mock，监控任务状态与数据库锁 |
| UV-003 | 已被引用主数据的编辑/删除阻断（ON DELETE RESTRICT） | 已确认 alembic 0005 设置 RESTRICT，但未进行实际删除触发测试 | 在已被引用的 candidate/order/sample 上执行 DELETE，验证返回 409/400 而非 500 |
| UV-004 | `/orchestrate/analyze` 超时原因 | 实测 OR1 30s 超时，可能是 LLM 服务响应慢或死锁；需结合后端日志与 LLM 服务状态进一步定位 | 查看后端日志、单独调用 LLMClient、增加链路追踪后复测 |
| UV-005 | MoleculeView WebGL/GPU 清理、SvgDrawer 实例级别、AgentFlowGraph 重试定时器清理 | 属于前端运行时行为，需通过浏览器 DevTools 与组件生命周期测试验证 | 使用 Chrome Performance/Memory 面板反复切换含 3D/图谱组件的页面，观察内存与定时器泄漏 |

## 3. 实操覆盖清单

本次评审覆盖 **36 个独立页面/路由**，并在其中识别了创建向导、抽屉、弹窗、批量导入、导入导出等子操作。表格中「是否真实操作」指是否执行了点击、填写、提交、搜索等交互；「是否验证联动」指操作后是否观察到列表刷新、详情更新、状态变化或跨页面数据一致。

| 导航层级 | 页面/入口 | 是否进入 | 是否真实操作 | 是否保存/提交 | 是否验证联动 | 证据 | 结果 | 未覆盖原因 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 工作台 | 首页 / | 是 | 是（遍历点击） | 否 | 否 | frontend/screenshots/pw_core/EV-20260729-100_home_initial.png | ⚠️ 部分点击被 overlay 拦截 | - |
| 工作台 | 我的待办 /my-tasks | 是 | 是（遍历点击） | 否 | 否 | frontend/screenshots/pw_core/EV-20260729-102_my-tasks_initial.png | ⚠️ 17 处点击异常 | - |
| 研发 | 项目管理 /projects | 是 | 是（遍历点击） | 否 | 否 | frontend/screenshots/pw_core/EV-20260729-104_projects_initial.png | ⚠️ 1 处点击异常 | - |
| 研发 | 项目新建 /projects/new | 是 | 是 | 是 | 是 | frontend/screenshots/pw_core/EV-20260729-107_projects_new_core.png | ✅ 创建成功 PROJ-* | - |
| 研发 | 候选材料设计 /workbench | 是 | 是 | 是 | 是 | frontend/screenshots/pw_core/EV-20260729-110_workbench_core.png | ✅ 生成 2 个候选 | - |
| 研发 | 性质预测 /prediction | 是 | 是 | 否 | 否 | frontend/screenshots/pw_core/EV-20260729-113_prediction_core.png | ❌ 渲染崩溃 | - |
| 研发 | 合成路径 /synthesis | 是 | 是 | 是 | 是 | frontend/screenshots/pw_core/EV-20260729-116_synthesis_core.png | ✅ 返回 1 条路线 | - |
| 研发 | 配方与工艺 /formula-design | 是 | 是 | 否 | 否 | frontend/screenshots/pw_core/EV-20260729-119_formula-design_core.png | ❌ MCP 工具 500 | - |
| 研发 | 实验闭环迭代 /ecml | 是 | 是 | 是 | 是 | frontend/screenshots/pw_core/EV-20260729-122_ecml_core.png | ✅ 闭环完成 | - |
| 研发 | 迭代历史 /ecml/runs | 是 | 是（遍历点击） | 否 | 否 | frontend/screenshots/pw_core/EV-20260729-124_ecml_runs_initial.png | ✅ 正常加载 | - |
| 研发 | 性能寿命预测 /battery-life | 是 | 是（遍历点击） | 否 | 否 | frontend/screenshots/pw_core/EV-20260729-126_battery-life_initial.png | ✅ 正常加载 | - |
| 实验 | 实验工作台 /experiment-workbench | 是 | 是 | 否 | 否 | frontend/screenshots/pw_data_ai/EXPW_full.png | ⚠️ 30 处点击异常 | overlay 拦截 |
| 实验 | 实验数据 /experiments | 是 | 是 | 否 | 否 | frontend/screenshots/pw_data_ai/EXP_full.png | ❌ 编辑被拦截 + 控制台报错 | overlay + null project_id |
| 实验 | 样品管理 /samples | 是 | 是 | 否 | 否 | frontend/screenshots/pw_data_ai/SAM_full.png | ✅ 正常加载 | - |
| 资产 | 设备台账 /equipment | 是 | 是 | 否 | 否 | frontend/screenshots/pw_data_ai/EQP_full.png | ✅ 正常加载 | - |
| 数据 | 数据接入 /data-ingest | 是 | 是 | 是（导入提交） | 是 | frontend/screenshots/pw_data_ai/ING_full.png | ✅ 导入预览/提交/幂等 | - |
| 数据 | 数据质量 /data-quality | 是 | 是（刷新/筛选） | 否 | 否 | frontend/screenshots/pw_data_ai/DQ_full.png | ✅ 正常加载 | - |
| 知识 | 技术情报 /technology-intelligence | 是 | 是（搜索/Tab 切换） | 否 | 否 | frontend/screenshots/pw_data_ai/TI_full.png | ✅ 正常加载 | - |
| 知识 | 知识图谱 /knowledge-graph | 是 | 是 | 否 | 否 | frontend/screenshots/pw_data_ai/KG_full.png | ✅ 图谱可视化 | - |
| 资产 | 物料规格库 /materials | 是 | 是 | 否 | 否 | frontend/screenshots/pw_data_ai/MAT_full.png | ✅ 正常加载 | - |
| 数据 | 属性字典 /properties | 是 | 是 | 否 | 否 | frontend/screenshots/pw_data_ai/PROP_full.png | ✅ 正常加载 | - |
| 数据 | 主数据治理 /mdm | 是 | 是 | 是 | 否 | frontend/screenshots/pw_data_ai/MDM_full.png | ❌ 保存弹窗不稳定 | overlay 抖动 |
| 研发 | 研发工作台 /research | 是 | 是 | 否 | 否 | frontend/screenshots/pw_data_ai/RES_full.png | ⚠️ Descriptions span 警告 | - |
| 研发 | 智能编排 /orchestration | 是 | 是 | 否 | 否 | frontend/screenshots/pw_data_ai/ORCH_full.png | ⚠️ Descriptions span 警告 | - |
| AI | 智能体管理 /agents | 是 | 是 | 否 | 否 | frontend/screenshots/pw_data_ai/AGT_full.png | ⚠️ SCP 风险策略未呈现 | - |
| AI | 工具与连接器 /tools | 是 | 是 | 否 | 否 | frontend/screenshots/pw_data_ai/TOOL_full.png | ✅ 正常加载 | - |
| AI | 调用关系 /topology | 是 | 是 | 否 | 否 | frontend/screenshots/pw_data_ai/TOPO_full.png | ❌ 404 | 路由未注册 |
| AI | 映射控制台 /mappings | 是 | 是 | 否 | 否 | frontend/screenshots/pw_data_ai/MAP_full.png | ⚠️ expandedRowRender 警告 | - |
| AI | 能力契约 /capability-center | 是 | 是 | 是 | 是 | frontend/screenshots/pw_data_ai/CAP_form_submit_1785321831687.png | ✅ 登记契约提交 | - |
| AI | 评估中心 /eval-center | 是 | 是 | 否 | 否 | frontend/screenshots/pw_data_ai/EVAL_full.png | ✅ 正常加载 | - |
| 管理 | 管理看板 /dashboard | 是 | 是 | 否 | 否 | frontend/screenshots/pw_data_ai/DASH_full.png | ⚠️ 成本接口 500（后端） | - |
| 管理 | 控制平面 /control-plane | 是 | 是 | 否 | 否 | frontend/screenshots/pw_data_ai/CTRL_full.png | ✅ 正常加载 | - |
| 管理 | 预算看板 /budgets | 是 | 是 | 否 | 否 | frontend/screenshots/pw_data_ai/BUD_full.png | ✅ 正常加载 | - |
| 管理 | 收益账单 /value-report | 是 | 是 | 否 | 否 | frontend/screenshots/pw_data_ai/VAL_full.png | ✅ 正常加载 | - |
| 管理 | 用户管理 /users | 是 | 是 | 否（弹窗未提交） | 否 | frontend/screenshots/pw_data_ai/USR_add_modal.png | ✅ 弹窗可打开 | - |
| 管理 | 系统设置 /settings | 是 | 是 | 否 | 否 | frontend/screenshots/pw_data_ai/SET_full.png | ✅ 只读验证 | - |

**弹窗/抽屉/创建向导/批量操作/导入导出补充覆盖**：

| 导航层级 | 子操作 | 所属页面 | 是否触发 | 是否提交 | 证据 | 结果 |
| --- | --- | --- | --- | --- | --- | --- |
| 研发 | 项目新建向导 | /projects/new | 是 | 是 | EV-20260729-107_projects_new_core.png | ✅ |
| 实验 | 实验工作台批量导入 | /experiment-workbench | 是 | 否 | EV-20260729-211 EXPW_btn_0.png | ⚠️ 按钮可点，未验证文件上传 |
| 实验 | 实验工作台新建任务 | /experiment-workbench | 是 | 否 | EV-20260729-212 EXPW_btn_1.png | ⚠️ 弹窗/抽屉未完整提交 |
| 数据 | 数据接入导入预览 | /data-ingest | 是 | 是 | ING_full.png / 后端 DI2/DI3 | ✅ |
| 数据 | 数据接入导入提交 | /data-ingest | 是 | 是 | 后端 DI3/DI3-DUP | ✅ 幂等 |
| 数据 | MDM 新增弹窗 | /mdm | 是 | 是 | EV-20260729-327 MDM_custom_error.png | ❌ 保存抖动 |
| 用户 | 用户新增弹窗 | /users | 是 | 否 | EV-20260729-473 USR_add_modal.png | ✅ 弹窗可打开 |
| AI | 能力契约登记抽屉 | /capability-center | 是 | 是 | CAP_form_submit_1785321831687.png | ✅ |

## 4. 端到端研发闭环验证

### 4.1 材料发现到实验闭环

**操作步骤**：

1. `POST /auth/login` 获取 token，角色 admin。
2. `POST /projects` 创建 ASSB-LPSCl-2026Q3 项目，返回 `PROJ-8207C2DD`。
3. `POST /projects/decompose` AI 拆解项目目标。
4. `POST /discover/crystal` 与 `POST /discover/agent-generate/async` 发现候选，正查 `/candidates` 得到 `CAND-*`。
5. `POST /discover/batch-predict` 批量预测，观察 `prediction_status` / `synthesis_status`。
6. `POST /synthesis/plan` 合成路线规划，`GET /synthesis/tasks/{id}` 返回 route。
7. `POST /experiments/orders` 创建实验任务单，返回 `EXP_be45d2cd`。
8. `POST /experiments/results/manual` 手工录入实验结果。
9. `POST /qc/check/RES_8e2c05f7` + `POST /qc/RES_8e2c05f7/approve`，QC 状态变为 VALID。
10. `POST /samples` 创建样品，返回 `SMP_6629ba72`。
11. ECML 运行 ID `ecml_20260729085056_38d231`，运行状态 `is_complete`。

**数据对象/ID**：

- 项目：`PROJ-8207C2DD`
- 候选：`CAND-*`
- 实验任务单：`EXP_be45d2cd`
- 结果：`RES_8e2c05f7`
- 样品：`SMP_6629ba72`
- ECML 运行：`ecml_20260729085056_38d231`

**成功节点**：项目创建、任务拆解、候选发现、批量预测状态返回、单路径合成规划、实验单创建与详情查询、结果录入、QC 审批通过、样品创建与流转、ECML 闭环完成。

**失败节点/断点**：

- `/synthesis/plan/multi` 返回 500（BEMCL-SYN-P1-001），多路径规划不可用。
- 前端 `/prediction` 页面渲染崩溃（BEMCL-PRED-P0-001），用户无法在前端查看预测结果。
- 前端 `/formula-design` 页面 MCP 工具 500（BEMCL-FORMULA-P0-003），配方研发链路在前端断裂。
- `/dashboard/cost` 返回 500（BEMCL-DASH-P1-002），成本分析不可用。

**逆向追溯结果**：

- 从 `SMP_6629ba72` 可反查样品详情、流转记录。
- 从 `EXP_be45d2cd` 可反查审计日志、分析结果。
- 从 `RES_8e2c05f7` 可反查 QC 检查与审批记录。
- 项目实体图 `/projects/{id}/entity-graph` 可返回关联关系。

**成熟度**：API 层基本可用（7/10），前端呈现层在关键节点存在 P0/P1 缺陷（4/10），综合 **受控试点**。

**整改建议**：

- 修复 `/prediction` 渲染错误与 `/formula-design` MCP 500，确保用户能从前端闭环。
- 修复 `/synthesis/plan/multi` 与 `/dashboard/cost` 的 500。
- 在前端增加「结果→实验单→候选→项目」一键追溯入口，而非仅依赖 API。

### 4.2 配方与工艺研发闭环

**操作步骤**：

1. 后端 `POST /formulas` 自动生成配方草案，返回 `FORM-736FC7C5`。
2. `GET /formulas/FORM-736FC7C5` 查看详情，`GET /formulas/{id}/history` 查看历史。
3. 前端进入 `/formula-design`，尝试通过 MCP 工具 `design_formula/call` 生成配方。

**数据对象/ID**：

- 配方：`FORM-736FC7C5`
- MCP 调用：`POST /api/mcp/tools/design_formula/call`

**成功节点**：后端 `/formulas` 接口 200，配方主档可创建与查询。

**失败节点/断点**：

- 前端 `/formula-design` 调用 MCP 工具返回 500，BOM 行数为 0，用户无法在前端完成配方设计。
- 配方与候选、实验单之间的联动在前端未验证（因页面已失败）。

**逆向追溯结果**：后端可通过配方 ID 正查，但前端无法展示。

**成熟度**：3/10。后端有接口，前端主链路断裂。

**整改建议**：

- 优先定位 MCP `design_formula/call` 500 根因（可能是工具未注册、后端 `/formulas` 与 MCP 返回格式不一致、或缺少项目/候选上下文）。
- 统一配方数据模型：明确 `/formulas` 与 MCP 工具的关系，避免两套接口。
- 增加配方→候选、配方→实验任务的联动入口。

### 4.3 数据资产治理闭环

**操作步骤**：

1. `POST /ingest/preview` 预览导入数据。
2. `POST /ingest/commit` 提交导入，重复提交验证幂等（`duplicated=true`）。
3. `GET /ingest/imports` 与 `GET /ingest/imports/IMP_588086c58feb` 查看导入历史与详情。
4. 进入 `/mdm`、`/materials`、`/properties`、`/knowledge-graph`、`/technology-intelligence` 查看主数据、物料、属性、知识图谱。
5. `POST /knowledge/search` 与 `POST /knowledge/graph` 验证知识搜索与图谱查询。

**数据对象/ID**：

- 导入记录：`IMP_588086c58feb`
- 主数据：单位、测试方法、属性、物料分类、工艺路线、样品类型、设备模板等。

**成功节点**：导入预览/提交/幂等、MDM 列表、物料库、属性字典、知识图谱可视化均正常加载。

**失败节点/断点**：

- `/mdm` 新增/编辑保存弹窗不稳定（BEMCL-UI-OVERLAY-P1-001 子症状），主数据维护操作可能失败。
- `/topology` 404（BEMCL-TOPO-P0-001），系统调用关系不可见。
- 实验结果缺少 `verified/estimated` 显式标记（BEMCL-DATA-P2-005），数据可信度分层不足。

**逆向追溯结果**：导入记录可反查，但数据血缘、来源、版本快照尚未可视化。

**成熟度**：6/10。数据入口与主数据查看可用，但维护操作与血缘可视化存在缺陷。

**整改建议**：

- 修复 MDM 弹窗 overlay 挂载问题，确保新增/编辑/保存可用。
- 补齐 `/topology` 路由或暂时隐藏菜单入口。
- 为实验结果、预测值、导入数据增加 `verified/estimated/simulated` 数据质量标记与来源字段。

## 5. 总体产品诊断

| 维度 | 评分（1-10） | 证据与理由 | 优先整改方向 |
| --- | --- | --- | --- |
| 业务适配 | 6 | 覆盖固态/聚合物电解质研发主流程，但配方与工艺前端断裂，多路径合成、成本分析不可用。 | 修复配方前端与合成/成本 500，补全业务闭环。 |
| 数据可信 | 5 | QC 引擎已存在，但实验结果缺少 verified/estimated 标记，数据质量分层不足；导入幂等已验证。 | 增加数据质量标记、来源、版本快照。 |
| MDM | 6 | 单位、测试方法、属性、物料分类等主数据接口可用；但 MDM 弹窗保存不稳定，target_properties 结构校验缺失。 | 修复 overlay、补齐 MDM 校验与版本控制。 |
| 端到端闭环 | 5 | 后端 API 层项目→候选→预测→合成→实验→QC→样品→PEML 已贯通；前端关键页面（prediction/formula-design/topology）断裂。 | 前端修复 P0，统一前后端数据接口。 |
| AI 可信 | 4 | Capability Registry 骨架好，但 discover/orchestrate 直接调用 LLMClient，未走 Tool/Skill/SCP 治理链；缺少输入快照、置信度、人工审核。 | 全部 LLM 调用纳入治理链，建立 AI 委员会门禁。 |
| LIMS/ELN | 5 | 实验任务单、结果录入、QC、样品流转已存在；状态机缺并发控制，结果缺数据质量标记。 | 状态机加锁、数据标记、审计日志可视化。 |
| 信息架构 | 5 | 36 个页面已覆盖，但导航层级与角色工作台不清晰，部分页面（topology）为死链。 | 重构左侧导航与角色首页，隐藏未实现页面。 |
| 表单 | 5 | 项目新建、能力契约登记可提交；但项目 target_properties 缺校验，MDM/实验表单存在 overlay 问题。 | 补齐校验、统一表单组件与挂载策略。 |
| UI | 5 | Ant Design Vue 基础组件使用规范，但存在大量 overlay 拦截、Descriptions span 警告、expandedRowRender 警告。 | 统一 getPopupContainer、修复组件告警。 |
| UX | 4 | 核心操作失败时无友好降级，空态/失败态未统一，部分页面点击无反馈。 | 建立空态、失败态、异步任务状态设计规范。 |
| 视觉 | 4 | 未形成统一视觉系统，化学式上下标、科学计数法、单位精度展示不一致。 | 制定视觉设计系统与科学数据展示规范。 |
| 异常恢复 | 5 | 后端部分 500 直接暴露内部错误；前端缺少错误边界与重试引导。 | 统一 400/500 错误处理、前端错误边界。 |
| 权限版本审计 | 5 | token 与角色中间件存在，但 /projects 匿名可访问；审计日志存在但前端未充分利用。 | 明确端点权限、前端展示审计轨迹与版本对比。 |
| 交付成熟度 | 4 | 存在 P0 阻断缺陷与多个 500，AI 治理链未完全落地，不可直接交付。 | 按路线图分阶段整改后进入受控试点。 |

## 6. 页面级深度问题清单

### [BEMCL-PRED-P0-001] 性质预测页面 - 候选表格渲染崩溃导致核心操作无结果
- 证据状态：[已实操验证]
- 优先级：P0
- 问题类型：功能
- 证据编号：EV-20260729-113_prediction_core.png；后端未观测到对应 500
- 位置：菜单「研发」> 性质预测 /prediction > CandidateTable 组件
- 触发前提：admin 角色，已存在候选数据，页面加载后触发渲染
- 复现步骤：1. 登录并进入 /prediction；2. 页面加载 CandidateTable；3. 控制台报错 `ReferenceError: energyPerAtomUnit is not defined`；4. 表格区域空白，操作状态 `failed_or_empty`
- 输入与对象：无特殊输入；候选类型 crystal
- 预期表现：页面正常渲染候选列表与预测结果，无控制台错误
- 实际表现：页面报错，候选数量为 0，核心操作未返回有效结果
- 用户影响：无法查看任何候选材料的性质预测结果，材料筛选与研发决策被阻断
- 研发/合规影响：性质预测是研发闭环核心环节，持续不可使用将导致实验优先级失去数据依据
- 根因假设：`CandidateTable` 渲染函数中引用了未定义的 `energyPerAtomUnit` 变量，或该常量/计算属性未在组件作用域内导入
- 整改方案：在 `CandidateTable` 组件中定义 `energyPerAtomUnit`，或从常量文件导入；增加单元测试覆盖该渲染路径
- 前端修改点：`frontend/src/components/prediction/CandidateTable.vue`（或等效文件）
- 后端/数据修改点：无
- 算法/AI/工具治理修改点：无
- 验收标准：/prediction 页面在存在候选时正常渲染表格，console 无 ReferenceError，操作状态为 success
- 回归范围：/prediction、/workbench、任何引用 CandidateTable 的页面
- 建议责任角色：前端工程师
- 预计工作量：S
- 依赖、风险与数据迁移：无

### [BEMCL-FORMULA-P0-003] 配方与工艺页面 - MCP 配方设计工具 500 导致 BOM 为空
- 证据状态：[已实操验证]
- 优先级：P0
- 问题类型：功能
- 证据编号：EV-20260729-119_formula-design_core.png；控制台 error Failed to load resource: 500 Internal Server Error
- 位置：菜单「研发」> 配方与工艺 /formula-design > 配方生成区域
- 触发前提：admin 角色，已进入 /formula-design 页面
- 复现步骤：1. 登录并进入 /formula-design；2. 触发配方设计操作；3. 请求 `POST http://localhost:5173/api/mcp/tools/design_formula/call` 返回 500；4. BOM 行数为 0
- 输入与对象：MCP 工具 `design_formula/call`
- 预期表现：接口返回 200 并展示配方 BOM 与工艺参数
- 实际表现：接口 500，页面无配方数据
- 用户影响：配方与工艺研发链路完全不可用，无法生成或优化配方
- 研发/合规影响：配方设计是连接候选材料与实验验证的关键节点，缺失将导致后续实验失去工艺依据
- 根因假设：MCP 工具未正确注册、工具内部调用后端 `/formulas` 时参数缺失/格式不匹配、或工具后端未处理异常
- 整改方案：检查 MCP 工具注册表与 `design_formula` 实现；统一 `/formulas` 与 MCP 工具的入参/出参；增加工具级错误处理与降级
- 前端修改点：增加错误边界与重试UI；验证请求参数
- 后端/数据修改点：MCP 工具层、`battery_materials_agent/api.py` 配方相关端点
- 算法/AI/工具治理修改点：将配方设计纳入 Tool/Skill/SCP 治理链，记录调用日志与版本
- 验收标准：/formula-design 能稳定生成配方 BOM，接口 200，无 500，支持结果导出到实验单
- 回归范围：/formula-design、/formulas、MCP 工具列表
- 建议责任角色：后端工程师 + 工具链工程师
- 预计工作量：M
- 依赖、风险与数据迁移：需确认 MCP 工具注册状态与依赖服务可用性

### [BEMCL-TOPO-P0-001] 调用关系页面 - /topology 路由返回 404
- 证据状态：[已实操验证]
- 优先级：P0
- 问题类型：功能
- 证据编号：EV-20260729-388 TOPO_full.png
- 位置：菜单「AI」> 调用关系 /topology
- 触发前提：admin 角色，点击左侧导航进入
- 复现步骤：1. 登录并点击「调用关系」；2. 页面内容包含 404 或无权限提示
- 输入与对象：路由 /topology
- 预期表现：展示系统内部/外部工具、服务、Agent 之间的调用拓扑图
- 实际表现：路由返回 404，页面无有效内容
- 用户影响：无法查看系统调用关系与依赖健康度
- 研发/合规影响：可观测性缺失，问题排查困难；如对外宣称 AI 驱动闭环，调用关系是重要证据入口
- 根因假设：前端路由存在但后端未注册 `/topology` 或对应数据接口；或该功能尚未实现
- 整改方案：补齐后端 `/topology` 接口并返回节点/边数据；或暂时在前端菜单中隐藏该入口
- 前端修改点：/topology 页面数据获取逻辑；菜单可见性控制
- 后端/数据修改点：新增 `/topology` 端点，聚合工具、Agent、SCP、LLM 调用关系
- 算法/AI/工具治理修改点：从 Capability Registry 与 ActivityMappingStore 自动生成拓扑数据
- 验收标准：/topology 正常加载并展示调用关系图，无 404；或菜单中不可见该入口
- 回归范围：/topology、左侧导航、能力契约/工具/Agent 相关页面
- 建议责任角色：后端工程师 + 前端工程师
- 预计工作量：M（实现）/ S（隐藏入口）
- 依赖、风险与数据迁移：依赖 Agent/工具/SCP 元数据完整性

### [BEMCL-SYN-P1-001] 合成路径 - /synthesis/plan/multi 返回 500 KeyError: 0
- 证据状态：[已实操验证]
- 优先级：P1
- 问题类型：功能
- 证据编号：后端实测 S2；`battery_materials_agent/synthesis/synthesis_planner.py:771`；`api.py:3841/3862`
- 位置：API `POST /synthesis/plan/multi`
- 触发前提：admin 角色，调用多路径合成规划
- 复现步骤：1. POST /synthesis/plan/multi；2. 后端返回 500；3. 日志显示 `KeyError: 0`
- 输入与对象：合成请求参数
- 预期表现：返回多条合成路线或空结果 200
- 实际表现：500 Internal Server Error
- 用户影响：无法同时比较多条合成路径，影响路线选择效率
- 研发/合规影响：合成规划是实验前的关键决策步骤，500 会导致实验任务创建受阻
- 根因假设：`plan_multiple_routes` 返回 dict，但 API 端点按 list 处理并使用 `routes[0]` 索引
- 整改方案：统一 API 端点与 planner 的返回格式，或在端点层适配 dict 结构
- 前端修改点：无
- 后端/数据修改点：`battery_materials_agent/api.py` 多路径规划端点与 `synthesis_planner.py`
- 算法/AI/工具治理修改点：无
- 验收标准：/synthesis/plan/multi 返回 200，数据结构稳定，前端可正确展示多条路线
- 回归范围：/synthesis/plan、/synthesis/plan/multi、/synthesis/tasks
- 建议责任角色：后端工程师
- 预计工作量：S
- 依赖、风险与数据迁移：无

### [BEMCL-DASH-P1-002] 管理看板 - /dashboard/cost 返回 500 TypeError
- 证据状态：[已实操验证]
- 优先级：P1
- 问题类型：功能
- 证据编号：后端实测 DB2；`api.py:9391`
- 位置：API `GET /dashboard/cost`
- 触发前提：admin 角色，存在实验单数据
- 复现步骤：1. GET /dashboard/cost；2. 后端返回 500 TypeError：datetime 不可下标
- 输入与对象：无特殊输入
- 预期表现：返回成本统计 JSON
- 实际表现：500
- 用户影响：成本分析看板不可用
- 研发/合规影响：项目预算与资源优化缺乏数据支撑
- 根因假设：`api.py:9391` 对 `o.created_at` 直接切片 `[:7]`，但 `ExperimentDataStore.list_orders` 返回 datetime 对象
- 整改方案：在 `dashboard_cost` 中对 `created_at` 调用 `_iso()` 或统一转换为字符串后再切片
- 前端修改点：无
- 后端/数据修改点：`battery_materials_agent/api.py`
- 算法/AI/工具治理修改点：无
- 验收标准：/dashboard/cost 返回 200，前端成本卡片正常展示
- 回归范围：/dashboard、/dashboard/cost、管理看板页面
- 建议责任角色：后端工程师
- 预计工作量：S
- 依赖、风险与数据迁移：无

### [BEMCL-EXP-P1-003] 实验任务单 - 未校验 candidate_id 存在性导致 FK 违反 500
- 证据状态：[已实操验证]
- 优先级：P1
- 问题类型：功能 / 数据
- 证据编号：`api.py:6928-6939`；alembic 0005 FK 约束
- 位置：API `POST /experiments/orders`
- 触发前提：admin 角色，提交含不存在 candidate_id 的实验任务单
- 复现步骤：1. POST /experiments/orders，payload 中 candidate_id 不存在；2. 后端返回 500（IntegrityError）
- 输入与对象：不存在的 candidate_id
- 预期表现：返回 400/404，提示候选不存在
- 实际表现：500 Internal Server Error
- 用户影响：前端用户收到不可理解的内部错误，无法正确修正输入
- 研发/合规影响：FK 违反暴露为 500，破坏 API 契约与审计日志可读性
- 根因假设：`api.py` 仅在 candidate 存在时检查 release_card，未在创建 order 前显式校验 candidate_id
- 整改方案：在创建 order 前显式校验 candidate_id 是否存在，不存在返回 404/400
- 前端修改点：无
- 后端/数据修改点：`battery_materials_agent/api.py:6928-6939`
- 算法/AI/工具治理修改点：无
- 验收标准：使用不存在 candidate_id 创建实验单返回 400 或 404，且错误信息明确
- 回归范围：/experiments/orders、实验任务单创建
- 建议责任角色：后端工程师
- 预计工作量：S
- 依赖、风险与数据迁移：无

### [BEMCL-SMP-P1-004] 样品管理 - 未校验 source_candidate_id 存在性导致 FK 违反 500
- 证据状态：[已实操验证]
- 优先级：P1
- 问题类型：功能 / 数据
- 证据编号：`api.py:8923-8953`；alembic 0005 FK 约束
- 位置：API `POST /samples`
- 触发前提：admin 角色，提交含不存在 source_candidate_id 的样品
- 复现步骤：1. POST /samples，payload 中 source_candidate_id 不存在；2. 后端返回 500（IntegrityError）
- 输入与对象：不存在的 source_candidate_id
- 预期表现：返回 400/404，提示候选不存在
- 实际表现：500 Internal Server Error
- 用户影响：样品创建失败，错误信息不可理解
- 研发/合规影响：样品溯源链建立失败，可能影响实验可重复性
- 根因假设：`create_sample` 未校验 source_candidate_id 是否存在于 candidates 表
- 整改方案：在 create_sample 中校验 source_candidate_id 存在性，或允许空值跳过 FK
- 前端修改点：无
- 后端/数据修改点：`battery_materials_agent/api.py:8923-8953`
- 算法/AI/工具治理修改点：无
- 验收标准：使用不存在 source_candidate_id 创建样品返回 400 或 404，且错误信息明确
- 回归范围：/samples、样品创建
- 建议责任角色：后端工程师
- 预计工作量：S
- 依赖、风险与数据迁移：无

### [BEMCL-EXP-P1-002] 实验数据页面 - 控制台空引用错误
- 证据状态：[已实操验证]
- 优先级：P1
- 问题类型：功能
- 证据编号：EV-20260729-226 EXP_console_error.png
- 位置：菜单「实验」> 实验数据 /experiments
- 触发前提：admin 角色，页面加载并交互
- 复现步骤：1. 进入 /experiments；2. 控制台出现 `[pageerror] TypeError: Cannot read properties of null (reading 'project_id')` 与 `[pageerror] TypeError: Cannot read properties of null (reading 'emitsOptions')`
- 输入与对象：无特殊输入
- 预期表现：页面加载无未处理异常
- 实际表现：出现空引用报错
- 用户影响：可能导致某些组件渲染异常或事件响应失败
- 研发/合规影响：未处理异常是稳定性隐患，可能掩盖更严重问题
- 根因假设：组件在异步数据返回前访问 `project_id`，或父组件未正确传递 `emitsOptions`
- 整改方案：增加空值保护（optional chaining / v-if）；检查组件 props/emits 定义
- 前端修改点：`frontend/src/views/Experiments.vue` 及相关子组件
- 后端/数据修改点：无
- 算法/AI/工具治理修改点：无
- 验收标准：/experiments 页面加载与交互过程中无 console pageerror
- 回归范围：/experiments、实验数据详情
- 建议责任角色：前端工程师
- 预计工作量：S
- 依赖、风险与数据迁移：无

### [BEMCL-UI-OVERLAY-P1-001] 全局 UI - Ant Design Vue overlay/portal 挂载导致多页面指针事件被拦截
- 证据状态：[已实操验证]
- 优先级：P1
- 问题类型：UI / UX
- 证据编号：EV-20260729-219 EXP_custom_error.png（/experiments 编辑按钮被 `<td class="ant-descriptions-item-content">` 拦截）；EV-20260729-327 MDM_custom_error.png（/mdm 保存弹窗不稳定）；EV-20260729-101/103/105/111/114/117/120/123/130 home/my-tasks/projects/workbench/prediction/synthesis/formula-design/ecml/experiment-workbench 点击异常截图
- 位置：多处页面，集中在 `a-select`、`a-modal`、`a-drawer`、`a-descriptions` 等使用 body 级 portal 的组件
- 触发前提：admin 角色，页面存在下拉/弹窗/抽屉，且自动化或用户点击触发元素
- 复现步骤：
  1. /experiments：点击「编辑」按钮，提示 `<td class="ant-descriptions-item-content">` 拦截 pointer events。
  2. /mdm：在弹窗中点击「保存/提交/确认/确定」，元素不稳定/不可见导致超时。
  3. 首页、我的待办、项目管理、候选材料设计、性质预测、合成路径、配方与工艺、实验闭环迭代、实验工作台：遍历点击时出现 1–44 处点击异常。
- 输入与对象：无特殊输入
- 预期表现：所有可见且可点击的元素正常响应
- 实际表现：大量点击被 overlay/portal 子树拦截，关键操作（编辑、保存）无法完成
- 用户影响：日常操作频繁被阻断，用户信任度下降；自动化测试难以稳定执行
- 研发/合规影响：自动化覆盖率低，回归成本高；关键业务操作可能失败
- 根因假设：Ant Design Vue 默认将 `a-select` 下拉、`a-modal` 弹窗渲染到 body 级独立容器（teleport），与触发元素不在同一 DOM 子树；当父级存在 `z-index`、动画、overflow 或布局抖动时，pointer events 被中间层拦截
- 整改方案：
  1. 全局配置 `ConfigProvider` 的 `getPopupContainer`，使弹窗/下拉挂载到 trigger 父级。
  2. 对确实需要 body 挂载的场景，确保 overlay 关闭后 DOM 清理，避免残留拦截层。
  3. 为自动化测试提供稳定的 `data-testid` 与 URL query 预填能力。
- 前端修改点：`frontend/src/main.js` 或 `App.vue` 配置 ConfigProvider；各页面 `a-select`/`a-modal`/`a-drawer` 的 `getPopupContainer`
- 后端/数据修改点：无
- 算法/AI/工具治理修改点：无
- 验收标准：
  1. Playwright 遍历点击所有页面，点击异常数为 0。
  2. /experiments 编辑按钮可正常点击。
  3. /mdm 弹窗保存/提交稳定成功。
- 回归范围：所有使用 Ant Design Vue overlay 组件的页面
- 建议责任角色：前端工程师
- 预计工作量：M
- 依赖、风险与数据迁移：无

### [BEMCL-EQP-P2-001] 设备台账 - category 校验在存储层抛出 500
- 证据状态：[已实操验证]
- 优先级：P2
- 问题类型：功能
- 证据编号：`api.py:8828-8850`；`EquipmentStore.save`
- 位置：API `POST /equipment`
- 触发前提：admin 角色，提交不存在的设备分类
- 复现步骤：1. POST /equipment，category 不存在于 MDM；2. 后端返回 500
- 输入与对象：不存在的 category
- 预期表现：返回 400，提示分类不存在
- 实际表现：500 Internal Server Error
- 用户影响：错误信息不友好
- 研发/合规影响：违反 RESTful 错误码约定
- 根因假设：API 层未前置校验 category；存储层抛出 ValueError 后被包装为 internal_error
- 整改方案：在 API 层预先校验 category 是否存在于 MDM，不存在返回 400
- 前端修改点：无
- 后端/数据修改点：`battery_materials_agent/api.py:8828-8850`
- 算法/AI/工具治理修改点：无
- 验收标准：使用不存在 category 创建设备返回 400
- 回归范围：/equipment、设备创建
- 建议责任角色：后端工程师
- 预计工作量：S
- 依赖、风险与数据迁移：无

### [BEMCL-STM-P2-002] 实验任务单 - 状态机更新缺少并发控制
- 证据状态：[高概率推断]
- 优先级：P2
- 问题类型：流程 / 数据
- 证据编号：`battery_materials_agent/experiment/experiment_controller.py:846`
- 位置：实验任务单状态机更新逻辑
- 触发前提：并发更新同一实验单状态
- 复现步骤：两个并发请求同时读取状态并更新，可能产生非预期迁移或覆盖
- 输入与对象：同一 experiment_order_id
- 预期表现：状态迁移原子性、一致性
- 实际表现：读取与更新非同一事务，缺少行锁
- 用户影响：高并发下状态可能不一致
- 研发/合规影响：影响实验流程合规性与审计准确性
- 根因假设：`update_order_status` 先 SELECT status 再 UPDATE，两条 SQL 不在同一连接/事务，且无 SELECT FOR UPDATE
- 整改方案：将读取与更新放入同一事务，并使用 SELECT FOR UPDATE 行锁或数据库级约束
- 前端修改点：无
- 后端/数据修改点：`battery_materials_agent/experiment/experiment_controller.py:846`
- 算法/AI/工具治理修改点：无
- 验收标准：并发状态更新测试通过，无状态覆盖
- 回归范围：实验任务单状态迁移
- 建议责任角色：后端工程师
- 预计工作量：M
- 依赖、风险与数据迁移：无

### [BEMCL-AI-P2-003] AI/Agent 治理链 - discover/orchestrate 端点直接调用 LLMClient 未走 Tool/Skill/SCP
- 证据状态：[已实操验证] + [高概率推断]
- 优先级：P2
- 问题类型：AI / 工具治理
- 证据编号：`api.py:1960` discover_agent_generate；`api.py:2180` discover_agent_generate_async；`api.py:5387` /orchestrate/analyze
- 位置：候选发现、智能编排相关 API 端点
- 触发前提：admin 角色，调用 AI 生成或编排分析
- 复现步骤：1. 调用 /discover/agent-generate、/discover/agent-generate/async、/orchestrate/analyze；2. 代码中直接实例化 `_LLMClient()` 或调用 `_orchestrator.analyze_task`
- 输入与对象：项目/任务/候选上下文
- 预期表现：所有 LLM 调用通过 Agent -> Tool/Skill -> SCP 治理链执行，受 Capability Contract 约束
- 实际表现：直接调用 LLMClient，绕过 Tool/Skill/SCP 治理链
- 用户影响：AI 输出不可追溯、无法审计、缺少降级与预算控制
- 研发/合规影响：无法满足 AI 委员会门禁、输入快照、版本与置信度要求
- 根因假设：早期实现为快速验证，直接将 LLM 调用写在 API 层
- 整改方案：将 LLM 调用封装为 Tool/Skill，通过 Agent 工具绑定和 Capability Contract 治理链执行
- 前端修改点：无
- 后端/数据修改点：`battery_materials_agent/api.py` 相关端点；新增 Tool/Skill 定义
- 算法/AI/工具治理修改点：Capability Registry、ActivityMappingStore、SCP 绑定
- 验收标准：discover/orchestrate 的 LLM 调用全部走 Tool/Skill/SCP；Capability Contract 记录风险等级与 fallback
- 回归范围：/discover、/orchestrate、/agents、/tools、/capability-center
- 建议责任角色：AI 平台工程师 + 后端工程师
- 预计工作量：L
- 依赖、风险与数据迁移：依赖 Capability Registry 与 SCP 已注册能力；需迁移现有 prompt 版本

### [BEMCL-ASYNC-P2-004] 候选发现异步任务 - ensure_future 存在 GC 风险
- 证据状态：[高概率推断]
- 优先级：P2
- 问题类型：性能 / 稳定性
- 证据编号：`api.py:2348`
- 位置：`discover_agent_generate_async` 后台任务创建逻辑
- 触发前提：admin 角色，触发异步候选生成
- 复现步骤：调用 /discover/agent-generate/async 后，任务对象无强引用
- 输入与对象：async task id aggen-*
- 预期表现：后台任务纳入统一生命周期管理，可被查询、取消、重启
- 实际表现：使用 `_asyncio.ensure_future(_bg_run())`，无强引用，可能被 GC 回收
- 用户影响：异步任务可能丢失，用户无法追踪生成进度
- 研发/合规影响：异步实验/AI 任务不可审计
- 根因假设：未使用统一的 `_spawn_background` 工具函数
- 整改方案：统一使用 `_spawn_background` 创建后台任务，确保引用与生命周期管理
- 前端修改点：无
- 后端/数据修改点：`battery_materials_agent/api.py:2348`
- 算法/AI/工具治理修改点：异步任务注册到控制平面 /control-plane/runs
- 验收标准：异步任务可被稳定查询状态，不会被 GC 回收
- 回归范围：/discover/agent-generate/async、/control-plane/runs
- 建议责任角色：后端工程师
- 预计工作量：S
- 依赖、风险与数据迁移：无

### [BEMCL-DATA-P2-005] 数据质量 - 实验结果缺少 verified/estimated 显式标记
- 证据状态：[高概率推断]
- 优先级：P2
- 问题类型：数据
- 证据编号：`battery_materials_agent/experiment/experiment_controller.py:150` ExperimentResultRecord
- 位置：实验结果数据模型
- 触发前提：任何产生实验结果的场景
- 复现步骤：查看 ExperimentResultRecord 字段，仅有 source_type 和 qc_status/learning_eligible，无 verified/estimated 区分
- 输入与对象：实验结果记录
- 预期表现：每条结果明确标记数据来源与可信度（实测/估算/模拟/文献）
- 实际表现：缺少显式标记
- 用户影响：无法区分实测数据与 AI 估算数据，影响研发决策
- 研发/合规影响：数据可信度与可追溯性不足，可能影响论文/专利/审计
- 根因假设：数据模型设计阶段未纳入数据质量分层
- 整改方案：增加 `data_quality` 字段（verified/estimated/simulated/literature）并在 QC 审批通过时更新
- 前端修改点：实验结果列表/详情展示 data_quality 标记
- 后端/数据修改点：`ExperimentResultRecord` 模型、实验结果录入/更新接口、QC 审批逻辑
- 算法/AI/工具治理修改点：预测/估算结果统一标记为 estimated
- 验收标准：所有实验结果携带 data_quality 字段，QC 通过后 verified 状态正确更新
- 回归范围：/experiments/results、/qc、/data-quality
- 建议责任角色：后端工程师 + 数据工程师
- 预计工作量：M
- 依赖、风险与数据迁移：需对历史数据回填默认值

### [BEMCL-AGT-P2-001] 智能体管理 - 工具路由策略 / SCP 风险策略未呈现
- 证据状态：[已实操验证]
- 优先级：P2
- 问题类型：AI / 功能
- 证据编号：EV-20260729-358 AGT_full.png
- 位置：菜单「AI」> 智能体管理 /agents
- 触发前提：admin 角色，进入 /agents 页面
- 复现步骤：1. 进入 /agents；2. 查看内置智能体/自定义智能体/模型路由；3. 未检测到「工具路由策略」「SCP 风险」等关键内容
- 输入与对象：无特殊输入
- 预期表现：智能体详情或模型路由页展示工具路由策略、SCP 风险等级、fallback 链
- 实际表现：未呈现上述关键内容
- 用户影响：无法直观理解 Agent 如何选工具、如何降级、风险如何控制
- 研发/合规影响：AI 治理透明度不足
- 根因假设：前端未读取 Capability Registry 与 SCP 绑定数据，或后端未暴露相关字段
- 整改方案：前端从 `/capabilities` 与 `/tools/scp-bindings` 获取策略并展示；后端补充 Agent 与 Capability 的关联接口
- 前端修改点：`frontend/src/views/Agents.vue` 及子组件
- 后端/数据修改点：`/agents` 相关接口补充工具路由与风险字段
- 算法/AI/工具治理修改点：Capability Registry 数据完整呈现
- 验收标准：/agents 页面可查看每个智能体的工具路由策略与 SCP 风险等级
- 回归范围：/agents、/capability-center、/tools
- 建议责任角色：前端工程师 + AI 平台工程师
- 预计工作量：M
- 依赖、风险与数据迁移：依赖 BEMCL-AI-P2-003 治理链落地

### [BEMCL-AUTH-P3-001] 认证权限 - 匿名用户可访问 /projects 列表
- 证据状态：[已实操验证]
- 优先级：P3
- 问题类型：权限 / 安全
- 证据编号：后端实测 P0-ANON；`api.py:101-104`；`api.py:8146`
- 位置：API `GET /projects`
- 触发前提：未登录或携带无效 token
- 复现步骤：1. GET /projects 不携带 token；2. 返回 200
- 输入与对象：无 token
- 预期表现：返回 401 或 403
- 实际表现：返回 200
- 用户影响：未认证用户可查看项目列表
- 研发/合规影响：数据访问合规性风险
- 根因假设：全局 dependencies 对匿名用户按 VIEWER 放行；list_projects 未显式要求角色
- 整改方案：评估是否为设计意图；如需要保护，在 /projects 端点添加 `dependencies=[Depends(require_role(UserRole.VIEWER))]`
- 前端修改点：无
- 后端/数据修改点：`battery_materials_agent/api.py:8146`
- 算法/AI/工具治理修改点：无
- 验收标准：未登录访问 /projects 返回 401/403，或明确文档化为公开端点
- 回归范围：/projects、认证中间件
- 建议责任角色：后端工程师
- 预计工作量：S
- 依赖、风险与数据迁移：需确认产品设计意图

### [BEMCL-PROJ-P3-002] 项目管理 - 项目子资源 /candidates/samples/results 未实现
- 证据状态：[已实操验证]
- 优先级：P3
- 问题类型：功能
- 证据编号：后端实测 P6/P7/P8；返回 HTML（SPA fallback index.html）
- 位置：API `GET /projects/{id}/candidates`、`/projects/{id}/samples`、`/projects/{id}/results`
- 触发前提：admin 角色，访问项目子资源
- 复现步骤：1. GET /projects/{id}/candidates；2. 返回 index.html
- 输入与对象：项目 ID PROJ-8207C2DD
- 预期表现：返回 JSON 列表
- 实际表现：返回 HTML（SPA fallback）
- 用户影响：前端若按该路由请求数据会失败
- 研发/合规影响：项目聚合视图不可用
- 根因假设：`api.py` 中仅注册了 /progress、/tasks、/entity-graph、/stage-status，无 candidates/samples/results 子资源路由
- 整改方案：实现上述子资源路由，或在文档中明确前端应使用 /candidates、/samples、/experiments/results 并携带 project_id 过滤
- 前端修改点：调整项目详情页的数据请求路由
- 后端/数据修改点：`battery_materials_agent/api.py` 新增子资源路由
- 算法/AI/工具治理修改点：无
- 验收标准：项目子资源返回正确 JSON，或前端不再调用这些路由
- 回归范围：/projects、/candidates、/samples、/experiments/results
- 建议责任角色：后端工程师 + 前端工程师
- 预计工作量：M
- 依赖、风险与数据迁移：无

### [BEMCL-VAL-P3-003] 项目创建 - target_properties/tasks 等字段缺少结构与单位校验
- 证据状态：[已实操验证]
- 优先级：P3
- 问题类型：数据 / 校验
- 证据编号：`api.py:7883-7892`
- 位置：API `POST /projects`
- 触发前提：admin 角色，创建项目
- 复现步骤：1. POST /projects，target_properties 结构任意或单位非法；2. 后端仅校验 target_application、owner、日期顺序、重名
- 输入与对象：非法 target_properties / tasks
- 预期表现：返回 400，提示属性名/方向/阈值/单位结构错误
- 实际表现：可能存入脏数据
- 用户影响：项目目标不规范，下游预测/实验难以解析
- 研发/合规影响：数据质量与可重复性风险
- 根因假设：ProjectCreateRequest 中 target_properties 为 list[dict]，未校验内部结构与单位白名单
- 整改方案：补充 target_properties 与 tasks 的结构/单位白名单校验
- 前端修改点：项目新建表单增加结构化输入与单位选择
- 后端/数据修改点：`battery_materials_agent/api.py:7883-7892`
- 算法/AI/工具治理修改点：无
- 验收标准：非法 target_properties 返回 400；合法结构正常创建
- 回归范围：/projects/new、/projects
- 建议责任角色：后端工程师 + 前端工程师
- 预计工作量：M
- 依赖、风险与数据迁移：需梳理 properties / units / mdm 数据作为白名单来源

### [BEMCL-UI-WARN-P3-001] 控制台警告聚合 - Descriptions span 不匹配与 expandedRowRender 未定义
- 证据状态：[已实操验证]
- 优先级：P3
- 问题类型：UI
- 证据编号：EV-20260729-347 RES_console_warn.png；EV-20260729-357 ORCH_console_warn.png；EV-20260729-403 MAP_console_warn.png
- 位置：/research、/orchestration、/mappings
- 触发前提：admin 角色，页面加载
- 复现步骤：1. 进入 /research 或 /orchestration，控制台报 `[ant-design-vue: Descriptions] Sum of column span in a line not match column of Descriptions`；2. 进入 /mappings，控制台报 `[Vue warn]: Property "expandedRowRender" was accessed during render but is not defined on instance`
- 输入与对象：无特殊输入
- 预期表现：无控制台警告
- 实际表现：存在组件使用警告
- 用户影响：可能影响布局或表格展开功能
- 研发/合规影响：警告积累会掩盖更严重问题
- 根因假设：`a-descriptions` 的 `:span` 总和与 `column` 不匹配；`mappings` 页面引用了未定义的 `expandedRowRender`
- 整改方案：修正 Descriptions 的 span 配置；为 mappings 表格定义 expandedRowRender 或移除引用
- 前端修改点：`frontend/src/views/Research.vue`、`Orchestration.vue`、`MappingConsole.vue`
- 后端/数据修改点：无
- 算法/AI/工具治理修改点：无
- 验收标准：上述页面控制台无相关 warning
- 回归范围：/research、/orchestration、/mappings
- 建议责任角色：前端工程师
- 预计工作量：S
- 依赖、风险与数据迁移：无

## 7. 表单与字段级整改规格

### 7.1 项目新建 /projects/new

| 字段分组 | 中文名 | 英文键 | 类型 | 必填 | 数据来源 | 自动带出/默认 | 单位/格式 | 校验 | 联动 | 提示 | 可编辑 | 版本控制 | 修改方案 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 基础信息 | 项目名称 | name | string | 是 | 用户输入 | - | 长度 2–100 | 非空、唯一、去重 | - | 示例：ASSB-LPSCl-2026Q3 | 是 | 创建后不可改 | 增加唯一校验与自动后缀提示 |
| 基础信息 | 项目代号 | code | string | 否 | 用户输入/系统自动 | 按规则生成 | 大写下划线 | 唯一 | - | 示例：PROJ-XXXXXX | 否 | 创建时生成 | 后端生成并返回 |
| 基础信息 | 负责人 | owner | string | 是 | 用户列表 | 当前用户默认 | 用户 ID | 必须存在于用户表 | 负责人变更写入审计日志 | 请选择负责人 | 是 | 每次变更记录 | 修复 overlay 导致的选择失败 |
| 基础信息 | 开始日期 | start_date | date | 是 | 用户选择 | 当天 | YYYY-MM-DD | 不能晚于 end_date | - | - | 是 | 记录变更 | 已校验，保持 |
| 基础信息 | 结束日期 | end_date | date | 是 | 用户选择 | start_date+90 天 | YYYY-MM-DD | 不能早于 start_date | - | - | 是 | 记录变更 | 已校验，保持 |
| 目标 | 目标应用 | target_application | string | 是 | 枚举 | - | - | 白名单 | - | 如：固态电池 | 是 | 记录变更 | 已校验，保持 |
| 目标 | 目标属性 | target_properties | array[object] | 是 | 属性字典 | - | {property, direction, threshold, unit} | 属性名/方向/单位白名单 | 选择 property 自动带出可选 unit | 至少填写一项 | 是 | 记录变更 | 新增结构化校验与单位联动 |
| 目标 | 任务列表 | tasks | array[object] | 否 | 用户输入/AI 拆解 | AI 拆解可填充 | {name, milestone, owner} | 结构校验 | AI 拆解后回填 | - | 是 | 记录变更 | 新增结构校验 |
| 扩展 | 描述 | description | text | 否 | 用户输入 | - | 长度 ≤2000 | - | - | - | 是 | 记录变更 | - |

### 7.2 实验数据录入 /experiments/results/manual

| 字段分组 | 中文名 | 英文键 | 类型 | 必填 | 数据来源 | 自动带出/默认 | 单位/格式 | 校验 | 联动 | 提示 | 可编辑 | 版本控制 | 修改方案 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 基础 | 实验任务单 | order_id | string | 是 | 实验单列表 | 上下文带入 | EXP-* | 必须存在且状态允许录入 | 选择后自动带出 candidate/project | - | 否 | 固定 | 已校验，保持 |
| 基础 | 测试方法 | test_method | string | 是 | MDM 测试方法 | - | - | 白名单 | - | 请选择已注册测试方法 | 是 | 记录变更 | 联动 MDM |
| 基础 | 样品 | sample_id | string | 否 | 样品列表 | - | SMP-* | 必须存在 | 选择后自动带出批次 | - | 是 | 记录变更 | 增加可选校验 |
| 测量值 | 属性名 | property_name | string | 是 | 属性字典 | - | - | 白名单 | 带出单位 | - | 是 | 记录变更 | 联动属性字典 |
| 测量值 | 数值 | value | number | 是 | 用户输入/仪器解析 | - | 科学计数法/小数 | 数值范围、精度 | 根据 property_name 校验 | 支持科学计数法 | 是 | 记录变更 | 增加数值范围校验 |
| 测量值 | 单位 | unit | string | 是 | 单位列表 | property_name 自动带出 | - | 单位白名单/可换算 | 与属性联动 | - | 是 | 记录变更 | 联动单位字典 |
| 可信度 | 数据质量 | data_quality | enum | 是 | 系统判定+人工确认 | 默认值 estimated | verified/estimated/simulated/literature | - | QC 通过后自动更新为 verified | 实测数据请选 verified | 是 | 记录变更 | 新增字段 |
| 可信度 | 来源类型 | source_type | enum | 是 | 系统记录 | manual | manual/import/instrument/ai | - | - | - | 否 | 固定 | 已存在，保持 |
| 附件 | 原始数据文件 | raw_files | array[file] | 否 | 用户上传 | - | - | 大小/格式限制 | - | 支持 csv/txt/xlsx | 是 | 记录变更 | 增加文件校验 |

### 7.3 主数据治理 /mdm（以标准单位为例）

| 字段分组 | 中文名 | 英文键 | 类型 | 必填 | 数据来源 | 自动带出/默认 | 单位/格式 | 校验 | 联动 | 提示 | 可编辑 | 版本控制 | 修改方案 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 基础 | 单位符号 | symbol | string | 是 | 用户输入 | - | 如 S/cm | 唯一、非空 | - | 区分大小写 | 创建后不可改 | 创建时固定 | 增加唯一校验 |
| 基础 | 单位名称 | name | string | 是 | 用户输入 | - | 如 西门子每厘米 | 非空 | - | - | 是 | 记录变更 | - |
| 基础 | 量纲 | dimension | string | 是 | 量纲字典 | - | 如 conductivity | 白名单 | - | - | 是 | 记录变更 | 联动量纲字典 |
| 换算 | 基准单位 | base_unit | string | 否 | 单位字典 | - | - | 必须与 symbol 可换算 | 选择后自动填充换算系数 | - | 是 | 记录变更 | 增加换算校验 |
| 换算 | 换算系数 | conversion_factor | number | 否 | 用户输入/自动计算 | 1.0 | 浮点数 | >0 | base_unit 联动 | - | 是 | 记录变更 | 自动计算并允许人工修正 |
| 元数据 | 适用域 | applicable_domain | array[string] | 否 | 枚举 | 全局 | - | 白名单 | - | - | 是 | 记录变更 | 新增字段 |
| 审计 | 生效版本 | version | string | 是 | 系统生成 | 1.0.0 | semver | - | - | - | 否 | 每次编辑+1 | 新增版本控制 |

## 8. UI/UX 重构规格

### 8.1 推荐左侧信息架构

建议按「角色+任务」而非「功能模块」组织一级导航，减少认知负荷：

```
工作台
  ├─ 我的待办（按角色聚合审批/任务/异常）
  ├─ 我的项目
  └─ 最近访问
研发闭环
  ├─ 项目管理
  ├─ 候选材料设计
  ├─ 性质预测
  ├─ 合成路径
  ├─ 配方与工艺
  └─ 实验闭环迭代
实验与样品
  ├─ 实验工作台
  ├─ 实验数据
  └─ 样品管理
数据资产
  ├─ 数据接入
  ├─ 数据质量
  ├─ 物料规格库
  ├─ 属性字典
  └─ 主数据治理
知识情报
  ├─ 技术情报
  ├─ 知识图谱
  └─ 论文/文献
AI 与工具
  ├─ 智能编排
  ├─ 智能体管理
  ├─ 工具与连接器
  ├─ 能力契约
  ├─ 映射控制台
  └─ 调用关系
管理
  ├─ 管理看板
  ├─ 控制平面
  ├─ 预算看板
  ├─ 收益账单
  ├─ 用户管理
  └─ 系统设置
```

### 8.2 不同角色首页/工作台

- **管理员**：系统健康度、预算消耗、用户活跃度、待审批事项、异常链路（P0/P1 告警）。
- **科学家/PI**：我的项目进展、待办实验、候选预测结果、QC 待审、最新知识推送。
- **实验员**：实验任务单列表、待录入结果、样品流转、设备预约/状态。
- **数据工程师**：数据接入队列、数据质量报告、MDM 变更审批、血缘异常。
- **Viewer/访客**：只读项目看板、公开报告（如配置开放）。

### 8.3 关键首屏、向导与渐进披露

- **项目新建**：改为分步向导（基础信息→目标属性→任务拆解→确认），每步实时校验；目标属性使用「属性选择器 + 方向 + 阈值 + 单位」组合输入，避免自由文本。
- **候选材料设计**：首屏展示项目/任务选择器 + 候选列表 + 「调用智能体生成」主按钮；高级参数（温度、模型、约束）折叠在「高级设置」抽屉中。
- **性质预测**：结果页首屏展示关键指标卡（最高离子电导率、平均带隙等）+ 候选表格；详情通过抽屉展开，避免页面跳转。
- **实验闭环迭代**：以时间轴/状态机展示项目→候选→预测→合成→实验→QC→样品的完整链路，当前节点高亮，断点标红并附一键修复入口。

### 8.4 空态、加载、失败、无权限、异步任务状态

- **空态**：统一使用插画 + 标题 + 操作建议，例如「暂无候选，点击「调用智能体生成」开始」。
- **加载**：骨架屏优先于 spinner；超过 2s 显示进度说明与取消按钮。
- **失败**：错误卡片包含错误码、友好说明、重试按钮、联系支持入口；禁止直接暴露堆栈。
- **无权限**：展示「无权限访问」插图 + 当前角色说明 + 申请权限入口。
- **异步任务**：任务卡片展示状态（排队中/运行中/成功/失败/已取消）、进度条、预计剩余时间、取消按钮、日志入口；失败时展示失败原因与重试。

### 8.5 状态色、按钮层级、表格/筛选/批量/详情/版本对比规范

- **状态色**：
  - 成功/通过：#52C41A
  - 运行中/待处理：#1890FF
  - 警告/待审：#FAAD14
  - 失败/拒绝：#F5222D
  - 默认/草稿：#8C8C8C
- **按钮层级**：每页仅保留一个主按钮（primary），次要操作为 default/text，危险操作为 danger；批量操作统一放在表格上方 toolbar。
- **表格**：固定表头、分页、行操作收纳在「更多」下拉中；筛选与搜索放在表格上方；可配置列。
- **详情**：默认抽屉展示，复杂详情使用新页面；详情页顶部展示面包屑、对象 ID、状态徽标、操作按钮。
- **版本对比**：对配方、属性、MDM 等支持版本的对象，提供「对比」按钮，展示字段级 diff（增/删/改）。

### 8.6 术语词表与必须替换文案

| 当前可能存在的问题文案 | 推荐替换 | 原因 |
| --- | --- | --- |
| 内部错误 / Internal Error | 操作失败，请重试或联系管理员（错误码：XXX） | 避免暴露内部信息 |
| 加载中... | 正在加载 xxx，预计还需 N 秒 | 提供上下文与预期 |
| 暂无数据 | 还没有 xxx，点击「新建」开始 | 提供行动指引 |
| 保存 | 保存草稿 / 提交 | 区分状态 |
| 生成 | 智能生成 / AI 生成 | 明确来源 |
| 结果 | 实测结果 / 预测结果 / 模拟结果 | 区分数据质量 |

## 9. 视觉设计系统建议

### 9.1 产品视觉定位、色板 Hex、浅/深色策略

- **视觉定位**：专业、冷静、可信的科学研究平台，强调数据精度与 AI 可信度。
- **主色**：#096DD9（科技蓝）
- **辅助色**：#13C2C2（青绿，用于成功/通过）、#722ED1（紫，用于 AI/智能体）
- **功能色**：#52C41A（成功）、#FAAD14（警告）、#F5222D（失败）
- **中性色**：#262626（主文本）、#595959（次级文本）、#8C8C8C（占位）、#D9D9D9（边框）、#F5F5F5（背景）
- **浅色模式**：默认；深色模式可作为实验室低光环境的可选项，但首阶段建议仅维护浅色，避免资源分散。

### 9.2 字体、字号、行高、间距、圆角、边框、阴影、图标

- **字体**：系统字体栈优先，英文 `Inter / SF Pro Display`，中文 `PingFang SC / Microsoft YaHei / Noto Sans SC`。
- **字号**：
  - 页面标题：24px / 600
  - 卡片标题：16px / 600
  - 正文：14px / 400
  - 辅助文本：12px / 400
- **行高**：标题 1.4，正文 1.6，表格 1.5。
- **间距**：基础单位 8px；卡片内边距 24px；模块间距 24px；表单字段间距 16px。
- **圆角**：卡片 8px，按钮 4px，标签/徽标 2px。
- **边框**：1px #D9D9D9，hover 时变为 #BFBFBF。
- **阴影**：卡片 `0 2px 8px rgba(0,0,0,0.08)`，抽屉/弹窗 `0 6px 16px rgba(0,0,0,0.12)`。
- **图标**：使用 Ant Design 图标库；化学/实验相关图标需保持一致风格（线框，1.5px stroke）。

### 9.3 卡片/表格/图表/状态徽标

- **卡片**：统一使用 8px 圆角、白色背景、 subtle shadow；标题左对齐，操作按钮右对齐。
- **表格**：斑马纹行、hover 高亮、操作列固定右对齐；状态列使用徽标 + 文字。
- **图表**：统一使用 ECharts/AntV 主题色；坐标轴标签使用 12px 灰色；图例位于顶部或右侧；科学数据支持对数坐标。
- **状态徽标**：使用 `a-tag` 圆角标签，颜色与状态色一致；文字使用动词/状态名（如「待 QC」「已通过」）。

### 9.4 化学式上下标、科学计数法、单位、精度规范

- **化学式**：使用 HTML `<sub>` / `<sup>` 或 Unicode 下标；提供 `ChemicalFormula` 组件统一渲染（如 Li₆PS₅Cl）。
- **科学计数法**：统一格式 `a × 10ⁿ` 或 `aE+n`，避免混用；表格中按列对齐。
- **单位**：使用 `/` 表示「每」（如 S/cm），避免使用非标准缩写；温度统一为 °C。
- **精度**：
  - 离子电导率：根据数量级动态展示 2–4 位有效数字。
  - 能量/电压：保留 3 位小数。
  - 百分比：保留 1 位小数。
  - 所有数值展示需在后端/前端统一格式化函数处理，避免各组件自行截断。

### 9.5 禁止视觉模式

- 禁止使用纯红色/绿色作为唯一信息区分（考虑色盲用户，需配合图标/文字）。
- 禁止在表格中直接展示长 ID，使用短 ID + 复制按钮 + hover 提示。
- 禁止使用超过 3 种主色在同一页面，避免视觉混乱。
- 禁止在科学数据展示中使用无单位的裸数值。
- 禁止弹窗/抽屉内再嵌套多层弹窗，复杂操作使用分步向导或新页面。

## 10. 数据模型、治理与 AI 可信度整改

### 10.1 核心对象关系与外键

核心对象链：`project → task → candidate → formula → experiment_order → experiment_result → qc_record → sample → ecml_run`。

- 已建立外键：`candidate/order/sample/result/transfers` 间使用 `ON DELETE RESTRICT`。
- 待完善：
  - `formula` 与 `candidate`、`experiment_order` 的外键与级联策略。
  - `knowledge_graph` 节点/边与 `candidate/material/paper` 的关联。
  - `capability` 与 `tool/skill/agent` 的多对多关系。

### 10.2 唯一标识、状态、版本、来源、审计字段

- **唯一标识**：项目 `PROJ-*`、候选 `CAND-*`、实验单 `EXP-*`、结果 `RES-*`、样品 `SMP-*`、导入 `IMP_*`、ECML `ecml_YYYYMMDD...`、能力契约 `能力名_v版本`。
- **状态**：所有状态机字段使用 MDM 状态码，禁止硬编码；实验任务单终态（COMPLETED/CANCELLED）不可迁出。
- **版本**：配方、MDM 主数据、属性模板、能力契约必须支持版本号；每次编辑生成新版本，旧版本只读。
- **来源**：实验结果增加 `source_type`（manual/import/instrument/ai）与 `data_quality`（verified/estimated/simulated/literature）。
- **审计**：每条核心记录包含 `created_at`、`created_by`、`updated_at`、`updated_by`、`version`、`deleted_at`（逻辑删除）；状态迁移写入专门的事件表。

### 10.3 删除/修改保护、幂等与去重、统计口径、数据质量、血缘

- **删除保护**：通过 `ON DELETE RESTRICT` 防止误删；删除前前端提示所有引用对象；管理员删除需二次确认并记录审计。
- **修改保护**：已被引用的主数据编辑后生成新版本，旧版本保留；关联对象可选择是否跟随升级。
- **幂等与去重**：数据导入已验证幂等（`duplicated=true`）；AI 生成候选需基于内容哈希去重；实验结果录入需基于（order_id, property_name, sample_id, timestamp）联合唯一。
- **统计口径**：成本、性能、进度看板需文档化统计口径（如是否包含已取消实验、是否区分 verified/estimated）。
- **数据质量**：建立 data_quality 字段与 QC 规则联动；数据质量看板展示 verified/estimated/simulated/literature 分布。
- **血缘**：构建 project→candidate→formula→experiment→result→sample 的血缘图；导入数据记录原始文件 ID 与映射关系。

### 10.4 AI/Agent 的输入快照、版本、证据、适用域、置信度、人工审核与放行机制

- **输入快照**：每次 LLM/Agent 调用前记录完整输入（prompt、上下文、参数、模型版本），保存为不可变快照。
- **版本**：Agent、Tool、Skill、Capability 均使用 semver；调用记录引用具体版本。
- **证据**：AI 输出必须附带引用来源（文献 ID、实验 ID、知识图谱节点）；可点击追溯。
- **适用域**：每个 AI 模型/工具声明适用域（材料体系、任务类型、数据规模），越界调用需人工确认。
- **置信度**：预测/推荐结果必须展示置信度分数与置信区间；低置信度结果标记为 estimated 并需实验验证。
- **人工审核与放行**：
  - 高风险操作（如自动创建实验单、自动放行样品）必须经过委员会/PI 审核。
  - 建立「AI 建议 → 人工确认 → 系统执行」的三段式工作流。
  - 所有 AI 驱动的状态变更写入审计日志，支持回滚。

## 11. 分阶段路线图

### 阶段 0：P0 止血与数据可信度

- **目标**：修复阻断性缺陷，恢复核心链路可用性，建立数据质量基础。
- **范围**：
  - 修复 BEMCL-PRED-P0-001、BEMCL-FORMULA-P0-003、BEMCL-TOPO-P0-001。
  - 修复 BEMCL-SYN-P1-001、BEMCL-DASH-P1-002、BEMCL-EXP-P1-003、BEMCL-SMP-P1-004。
  - 增加 `data_quality` 字段（BEMCL-DATA-P2-005）。
- **明确不做项**：不重构 UI/UX，不新增 AI 治理功能，不优化视觉系统。
- **前置依赖**：开发环境可稳定复现上述缺陷；MCP 工具源码可访问。
- **验收指标**：核心 7 个页面 100% 可用；/prediction、/formula-design、/topology 无阻断错误；后端 500 数量归零（除外部服务异常）。
- **风险**：MCP 工具根因定位耗时可能超过预期。
- **优先级**：最高（P0/P1）。

### 阶段 1：主研发链路

- **目标**：确保材料发现→预测→合成→配方→实验→QC→样品闭环在前端可完整执行。
- **范围**：
  - 修复 BEMCL-UI-OVERLAY-P1-001（全局 overlay 问题）。
  - 修复 BEMCL-EXP-P1-002（空引用报错）。
  - 修复 BEMCL-EQP-P2-001（设备 category 校验）。
  - 统一前后端数据接口（如 `/projects/{id}/candidates` 等子资源，BEMCL-PROJ-P3-002）。
- **明确不做项**：不引入新的 AI 能力，不做深色模式。
- **前置依赖**：阶段 0 完成；前端可稳定构建。
- **验收指标**：Playwright 遍历 36 个页面点击异常数为 0；主研发链路自动化脚本通过。
- **风险**：Ant Design Vue 全局 ConfigProvider 调整可能影响现有页面布局。
- **优先级**：高。

### 阶段 2：LIMS/ELN 数据闭环与治理

- **目标**：建立实验与样品的 LIMS/ELN 级数据可信与治理。
- **范围**：
  - 实验任务单状态机加锁（BEMCL-STM-P2-002）。
  - 数据质量标记落地与展示（BEMCL-DATA-P2-005）。
  - MDM 校验与版本控制（BEMCL-VAL-P3-003、MDM 弹窗修复）。
  - 导入数据血缘与来源记录。
  - 属性字典、单位、测试方法白名单联动。
- **明确不做项**：不重构知识图谱算法，不做外部仪器直连。
- **前置依赖**：阶段 1 完成；MDM 数据模型确定。
- **验收指标**：并发状态更新测试通过；所有实验结果携带 data_quality；MDM 编辑稳定且带版本。
- **风险**：历史数据回填规则需业务确认。
- **优先级**：高。

### 阶段 3：AI 可信度、委员会门禁与可观测性

- **目标**：所有 AI/Agent 调用纳入治理链，建立可信度与人工审核机制。
- **范围**：
  - 将 discover/orchestrate 直接 LLM 调用改造为 Tool/Skill/SCP 治理链（BEMCL-AI-P2-003）。
  - 修复异步任务 GC 风险（BEMCL-ASYNC-P2-004）。
  - 实现输入快照、版本、证据、适用域、置信度。
  - 建立 AI 委员会门禁与人工审核工作流。
  - 智能体管理页展示工具路由策略与 SCP 风险（BEMCL-AGT-P2-001）。
  - 调用关系图可用（BEMCL-TOPO-P0-001 如阶段 0 未完全实现则在此补齐）。
- **明确不做项**：不自研 LLM，不扩展多模态大模型。
- **前置依赖**：阶段 2 完成；Capability Registry 数据完整。
- **验收指标**：所有 LLM 调用可追踪到 Capability Contract；低置信度预测必须人工确认；/topology 正常展示。
- **风险**：SCP/ASKCOS 外部服务稳定性影响治理链效果。
- **优先级**：中-高。

### 阶段 4：UI/UX 与视觉体系

- **目标**：重构信息架构、工作台、向导、视觉系统，提升专业感与可用性。
- **范围**：
  - 重构左侧导航与角色工作台。
  - 统一空态、加载、失败、异步任务状态。
  - 实施视觉设计系统（色板、字体、间距、圆角、阴影、图标）。
  - 化学式上下标、科学计数法、单位、精度组件化。
  - 修复控制台警告（BEMCL-UI-WARN-P3-001）。
- **明确不做项**：不改业务逻辑，不新增页面功能。
- **前置依赖**：阶段 1/2 完成，业务流程稳定。
- **验收指标**：设计系统文档化；36 个页面视觉一致；无障碍基础检查通过。
- **风险**：视觉改版可能影响用户既有习惯，需试点反馈。
- **优先级**：中。

### 阶段 5：试点与商业化交付

- **目标**：在真实新材料团队中受控试点，收集反馈，决定是否正式交付。
- **范围**：
  - 选择 1–2 个真实项目运行完整闭环。
  - 监控 P0/P1 复发率、用户操作成功率、AI 输出采纳率。
  - 完善权限版本审计（BEMCL-AUTH-P3-001 等）。
  - 编写用户手册、培训材料、运维 SOP。
- **明确不做项**：不扩大销售范围，不做大规模市场推广。
- **前置依赖**：阶段 0–4 完成；至少连续 2 周无 P0/P1。
- **验收指标**：真实项目闭环成功率 ≥90%；用户满意度 ≥4/5；P0/P1 零复发。
- **风险**：真实数据与测试数据差异可能暴露新的边界问题。
- **优先级**：中。

## 12. 可导入研发管理工具的任务拆解

| 任务编号 | 优先级 | 模块 | 用户故事 | 修改内容 | 前端 | 后端 | 数据迁移 | AI/算法 | 测试要点 | 验收标准 | 工作量 | 依赖 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| T-001 | P0 | 性质预测 | 作为科学家，我希望性质预测页面正常展示候选与结果 | 修复 CandidateTable 中 energyPerAtomUnit 未定义错误 | ✅ | - | - | - | 页面加载、候选渲染、console 报错 | /prediction 正常展示，无 pageerror | S | - |
| T-002 | P0 | 配方与工艺 | 作为科学家，我希望配方页面能生成 BOM | 定位并修复 MCP design_formula/call 500 | ✅（错误处理） | ✅（工具层） | - | ✅（配方工具） | 触发配方生成、BOM 展示、导出 | /formula-design 生成配方，接口 200 | M | MCP 工具源码 |
| T-003 | P0 | 调用关系 | 作为管理员，我希望查看系统调用拓扑 | 补齐 /topology 路由或隐藏菜单 | ✅ | ✅ | - | - | 路由加载、节点/边展示 | /topology 无 404 或有意义内容 | M/S | Capability Registry |
| T-004 | P1 | 合成路径 | 作为科学家，我希望比较多条合成路线 | 修复 /synthesis/plan/multi 返回格式 | - | ✅ | - | - | 多路径规划、数据结构 | /synthesis/plan/multi 返回 200 | S | - |
| T-005 | P1 | 管理看板 | 作为 PI，我希望查看项目成本 | 修复 /dashboard/cost datetime 切片错误 | - | ✅ | - | - | 成本接口、前端展示 | /dashboard/cost 返回 200 | S | - |
| T-006 | P1 | 实验任务单 | 作为实验员，我希望创建实验单时获得明确错误提示 | 前置校验 candidate_id 存在性 | - | ✅ | - | - | 非法 candidate_id、错误码 | 不存在 candidate_id 返回 400/404 | S | - |
| T-007 | P1 | 样品管理 | 作为实验员，我希望创建样品时获得明确错误提示 | 前置校验 source_candidate_id 存在性 | - | ✅ | - | - | 非法 source_candidate_id | 不存在 source_candidate_id 返回 400/404 | S | - |
| T-008 | P1 | 全局 UI | 作为用户，我希望所有按钮和下拉可正常点击 | 统一 ConfigProvider getPopupContainer，修复 overlay 拦截 | ✅ | - | - | - | 遍历点击 36 页、MDM 保存、实验编辑 | 点击异常数为 0 | M | - |
| T-009 | P1 | 实验数据 | 作为实验员，我希望实验数据页面无异常 | 修复 project_id/emitsOptions 空引用 | ✅ | - | - | - | 页面加载、详情展开 | /experiments 无 pageerror | S | - |
| T-010 | P2 | 设备台账 | 作为资产管理员，我希望设备分类错误有明确提示 | 前置校验 equipment category | - | ✅ | - | - | 非法 category | 返回 400 | S | - |
| T-011 | P2 | 实验任务单 | 作为系统，我希望状态迁移原子化 | 状态机加 SELECT FOR UPDATE 行锁 | - | ✅ | - | - | 并发状态更新 | 无状态覆盖 | M | - |
| T-012 | P2 | AI 治理 | 作为平台工程师，我希望所有 LLM 调用可治理 | discover/orchestrate 改造为 Tool/Skill/SCP | - | ✅ | - | ✅ | LLM 调用追踪、Capability Contract | 所有调用走治理链 | L | Capability Registry |
| T-013 | P2 | 异步任务 | 作为用户，我希望异步任务不丢失 | 统一使用 _spawn_background | - | ✅ | - | - | 异步候选生成、任务查询 | 任务状态稳定可查询 | S | - |
| T-014 | P2 | 数据质量 | 作为科学家，我希望区分实测与估算数据 | 增加 data_quality 字段与 QC 联动 | ✅ | ✅ | ✅（回填） | - | 结果录入、QC 审批、展示 | 所有结果携带 data_quality | M | - |
| T-015 | P2 | 智能体管理 | 作为管理员，我希望查看 Agent 路由策略 | 前端展示工具路由与 SCP 风险 | ✅ | ✅ | - | ✅ | /agents 页面 | 策略可见 | M | T-012 |
| T-016 | P3 | 权限 | 作为安全负责人，我希望未登录不可访问项目 | 修复 /projects 匿名访问 | - | ✅ | - | - | 未登录访问 | 返回 401/403 | S | 产品确认 |
| T-017 | P3 | 项目管理 | 作为用户，我希望项目详情能查看候选/样品/结果 | 实现项目子资源路由 | ✅ | ✅ | - | - | 子资源请求 | 返回正确 JSON | M | - |
| T-018 | P3 | 项目创建 | 作为科学家，我希望项目目标规范 | target_properties/tasks 结构校验 | ✅ | ✅ | - | - | 非法结构、单位 | 返回 400 | M | MDM 数据 |
| T-019 | P3 | 控制台警告 | 作为开发者，我希望减少警告噪音 | 修复 Descriptions span 与 expandedRowRender | ✅ | - | - | - | 控制台 | 无相关 warning | S | - |
| T-020 | P4 | UI/UX | 作为用户，我希望界面更专业易用 | 信息架构、工作台、视觉系统重构 | ✅ | - | - | - | 设计走查、可用性测试 | 设计系统落地 | L | T-008 |

## 13. 验收测试清单

| 用例编号 | 分类 | 前置条件 | 步骤 | 输入 | 预期 | 实际 | 通过 | 缺陷编号 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TC-001 | 核心链路 | admin 登录，存在项目 | 进入 /prediction | - | 候选表格正常渲染 | 渲染崩溃 | 否 | BEMCL-PRED-P0-001 |
| TC-002 | 核心链路 | admin 登录 | 进入 /formula-design 触发配方生成 | - | 返回 200 并展示 BOM | 500 | 否 | BEMCL-FORMULA-P0-003 |
| TC-003 | 核心链路 | admin 登录 | 进入 /topology | - | 展示调用关系 | 404 | 否 | BEMCL-TOPO-P0-001 |
| TC-004 | 后端 API | admin token | POST /synthesis/plan/multi | 合法参数 | 200 并返回路线列表 | 500 | 否 | BEMCL-SYN-P1-001 |
| TC-005 | 后端 API | admin token | GET /dashboard/cost | - | 200 并返回成本 JSON | 500 | 否 | BEMCL-DASH-P1-002 |
| TC-006 | 后端 API | admin token | POST /experiments/orders 含不存在 candidate_id | 不存在 candidate_id | 400/404 | 500 | 否 | BEMCL-EXP-P1-003 |
| TC-007 | 后端 API | admin token | POST /samples 含不存在 source_candidate_id | 不存在 source_candidate_id | 400/404 | 500 | 否 | BEMCL-SMP-P1-004 |
| TC-008 | UI 交互 | admin 登录 | Playwright 遍历 /experiments 编辑按钮 | - | 编辑按钮可点击 | 被拦截 | 否 | BEMCL-UI-OVERLAY-P1-001 |
| TC-009 | UI 交互 | admin 登录 | Playwright 遍历 36 页面所有可点击元素 | - | 点击异常数为 0 | >0 | 否 | BEMCL-UI-OVERLAY-P1-001 |
| TC-010 | UI 交互 | admin 登录 | 进入 /mdm 并保存新增条目 | - | 保存成功 | 弹窗不稳定 | 否 | BEMCL-UI-OVERLAY-P1-001 |
| TC-011 | 数据质量 | admin 登录 | 查看实验结果详情 | - | 展示 data_quality 字段 | 未展示 | 否 | BEMCL-DATA-P2-005 |
| TC-012 | AI 治理 | admin 登录 | 查看 /agents 工具路由策略 | - | 策略可见 | 未呈现 | 否 | BEMCL-AGT-P2-001 |
| TC-013 | 权限 | 未登录 | GET /projects | - | 401/403 | 200 | 否 | BEMCL-AUTH-P3-001 |
| TC-014 | 数据接入 | admin token | 重复导入同一文件 | 同一文件 | duplicated=true | duplicated=true | 是 | - |
| TC-015 | 核心链路 | admin token | 完整闭环：项目→候选→合成→实验→QC→样品→PEML | 测试项目数据 | 所有步骤 200，状态正确 | 主路径通过 | 是 | - |
| TC-016 | UI 警告 | admin 登录 | 进入 /research /orchestration /mappings | - | 控制台无相关 warning | 存在 warning | 否 | BEMCL-UI-WARN-P3-001 |
| TC-017 | 项目子资源 | admin token | GET /projects/{id}/candidates | 项目 ID | JSON 列表 | HTML fallback | 否 | BEMCL-PROJ-P3-002 |
| TC-018 | 项目校验 | admin token | POST /projects 含非法 target_properties | 非法结构 | 400 | 可能 200 | 否 | BEMCL-VAL-P3-003 |
| TC-019 | 状态机 | admin token | 并发更新同一实验单状态 | 同一 order_id | 状态一致 | 可能存在竞态 | 否 | BEMCL-STM-P2-002 |
| TC-020 | 异步任务 | admin token | 触发 /discover/agent-generate/async 并查询状态 | - | 状态稳定可查询 | 可能丢失 | 否 | BEMCL-ASYNC-P2-004 |

## 14. 最终交付判断

### 14.1 能否供真实新材料团队日常使用：是/否/仅受控试点，并给出条件

**仅受控试点**。必须同时满足以下条件方可进入真实团队试点：

1. 修复全部 3 个 P0 缺陷（BEMCL-PRED-P0-001、BEMCL-FORMULA-P0-003、BEMCL-TOPO-P0-001）。
2. 修复全部 6 个 P1 缺陷，确保核心链路前后端可完整执行。
3. 完成阶段 0 与阶段 1 的关键任务（T-001 至 T-009）。
4. 建立基础 AI 调用审计与数据质量标记机制（至少完成 T-014）。
5. 连续 1 周自动化测试（含 36 页面点击遍历与核心闭环脚本）无 P0/P1 复发。

### 14.2 最优先的 10 项整改

1. 修复 /prediction 渲染崩溃（BEMCL-PRED-P0-001）。
2. 修复 /formula-design MCP 500（BEMCL-FORMULA-P0-003）。
3. 修复 /topology 404（BEMCL-TOPO-P0-001）。
4. 修复 /synthesis/plan/multi 500（BEMCL-SYN-P1-001）。
5. 修复 /dashboard/cost 500（BEMCL-DASH-P1-002）。
6. 修复实验/样品 FK 校验前置缺失（BEMCL-EXP-P1-003、BEMCL-SMP-P1-004）。
7. 统一修复全局 overlay 指针拦截（BEMCL-UI-OVERLAY-P1-001）。
8. 修复 /experiments 空引用报错（BEMCL-EXP-P1-002）。
9. 增加实验结果 data_quality 字段（BEMCL-DATA-P2-005）。
10. 将 discover/orchestrate LLM 调用纳入 Tool/Skill/SCP 治理链（BEMCL-AI-P2-003）。

### 14.3 应保留深化的功能

- **Capability Registry 与能力契约中心**：作为 AI 治理的总闸门，应深化风险等级、fallback 链、版本管理。
- **端到端数据对象关系**：项目→候选→实验→QC→样品的血缘与审计是核心竞争力，应继续深化。
- **QC 引擎**：统一的数据质量规则引擎是 LIMS/ELN 可信基础，应扩展更多规则类型。
- **数据接入与导入幂等**：数据资产沉淀的入口，应支持更多格式与来源。
- **控制平面与预算看板**：AI/工具运行的可观测性与成本控制是商业化关键。

### 14.4 应合并、隐藏、降级或暂缓的功能

- **调用关系 /topology**：当前为 404，应暂时隐藏菜单入口，待后端接口补齐后再开放。
- **多路径合成规划 /synthesis/plan/multi**：当前 500，修复前可降级为仅展示单路径结果，并提示多路径暂时不可用。
- **配方与工艺 MCP 工具与 /formulas 端点**：存在两套接口，应合并为统一服务，避免前端调用混乱。
- **性能寿命预测 /battery-life**：本次仅做了加载验证，尚未纳入核心闭环，可待真实数据积累后再深化。
- **深色模式**：视觉重构阶段 4 中明确不做，待浅色模式稳定后再评估。

### 14.5 未满足哪些验收条件前，不得对外宣称“AI 驱动研发闭环”

在以下条件未满足前，不得对外宣称“AI 驱动研发闭环”：

1. **核心链路可完整执行**：从项目创建、候选发现、性质预测、合成规划、配方设计、实验任务、结果录入、QC 审批、样品管理到 PEML 闭环，全部可在前端无 P0/P1 缺陷完成。
2. **AI 调用可审计**：所有 LLM/Agent/Tool 调用必须记录输入快照、模型版本、输出结果、置信度与人工审核状态。
3. **数据可信度分层**：实验结果、预测结果、模拟结果必须明确区分 verified/estimated/simulated，并在关键决策节点提示用户。
4. **AI 委员会门禁**：高风险 AI 输出（如自动创建实验单、自动放行）必须经过人工确认，不可直接执行。
5. **调用关系与血缘可观测**：用户可查看 project→candidate→formula→experiment→result→sample 的完整血缘，以及系统内部 AI/工具调用拓扑。
6. **权限与审计合规**：匿名不可访问敏感数据；所有状态变更写入审计日志并支持追溯。
7. **连续稳定运行**：在受控试点中连续 1 个月无 P0/P1 复发，用户闭环成功率 ≥90%。

---

**报告附件**：

- 后端 API 实测原始记录：`doc/review_backend.md`
- 前端核心研发链路 Playwright 报告：`doc/review_core_playwright.md`
- 前端数据/知识/AI/管理模块 Playwright 报告：`doc/review_data_ai_playwright.md`
- 前端 overlay 排查与测试数据准备报告：`doc/review_frontend_investigation.md`
- 截图目录：`frontend/screenshots/pw_core/`、`frontend/screenshots/pw_data_ai/`
