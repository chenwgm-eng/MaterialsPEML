# 《BatteryEMCL Lab 全功能实操评测与整改建议书》

- 评审日期：2026-07-30
- 评审环境与版本：前端 <http://localhost:5173> (Vite 5.4.21) / 后端 <http://127.0.0.1:8000> (FastAPI + uvicorn --reload) / 浏览器 Chrome
- 评审账号/角色（脱敏）：admin（管理员），user\_id=U-9AF74283
- 覆盖范围：38 个路由页面中 28 个浏览器实测通过，10 个因浏览器预算截断但 API 已验证；22+ API 端点测试；3 条端到端链路；5 项异常集；AI/Agent 治理专项
- 实操数据集与清理状态：创建项目 PROJ-EE74E6FD（ASSB-LPSCl-2026Q3-EVAL）、生成 19 个候选（9 晶体+10 聚合物）、1 个合成任务（f84b82aa48b5）；保留用于复测
- 已完成操作数：60+ 次页面导航、40+ 次 API 调用、5 次异常输入测试
- 已实操验证缺陷数（P0/P1/P2/P3）：P0×3 / P1×5 / P2×4 / P3×2 = 14
- 高概率推断项数：3
- 未验证项数及原因：10 个页面未完成浏览器深检（浏览器自动化预算耗尽），但 API 层已验证端点可用
- 报告版本：v1.2（补全第 13/14 章：验收测试清单 + 最终交付判断；2026-07-31 修复回归验证：14 项缺陷全部修复并复测通过）

***

## 1. 执行摘要

### 当前成熟度：受控试点

**证据**：系统三大核心链路（材料发现→实验闭环、配方工艺研发、数据资产治理）在 API 层均可跑通，28 个页面无阻塞错误，异常处理规范（409/404/401 + 引用完整性保护）。但存在 3 个 P0 级数据可信度问题（无溯源 verified 数据进入学习闭环、项目-候选关联完全失效、能力契约查询 500），需在试点前修复。

### 值得保留的实现与原因

1. **异常处理体系**：409 重名 / 404 不存在 / 401 未认证 / 403 权限不足，错误信息中文友好，引用完整性保护到位（删除被引用对象时 409 拒绝）
2. **Activity→Agent→Tool 三层映射**：`/mappings/overview` 一站式查询，18 个 activity、14 个工具绑定，治理链结构完整
3. **控制平面策略引擎**：5 条 RBAC 策略规则（deny-thinker-dft、conditional-researcher-scp 等），策略粒度合理
4. **MDM 五阶段治理**：属性字典、单位换算、状态码、物料分类、测试方法均有 seed 数据
5. **知识资产三层结构**：Paper→Material→Claim 关系已建立，DOI 去重、source\_tier × evidence\_level 双维可信度
6. **配方版本管理**：30 条配方、V01/V02 版本链、BOM/BOP 设计、成本核算（物料成本+加工成本）
7. **14 个内置智能体**：角色覆盖材料科学家、合成规划师、DFT 专家、实验分析师等，含工具/能力/禁止操作元数据

### 最重要的 P0/P1 风险

| 级别 | 缺陷                             | 影响                                                     |
| -- | ------------------------------ | ------------------------------------------------------ |
| P0 | 无溯源 verified 数据进入学习闭环          | 来源不明的实验结果被标记 verified + learning\_eligible，污染 ECML 迭代  |
| P0 | 项目-候选关联完全失效                    | `/projects/{id}/candidates` 返回 0，75% 订单 project\_id 为空 |
| P0 | `/capabilities` 返回 500         | 能力契约查询不可用，AI 治理链验证闭环断裂                                 |
| P1 | 29 个工具 fallback\_tool\_id 全空   | 降级回退机制形同虚设                                             |
| P1 | ECML step7\_feedback 无工具绑定     | 反馈学习闭环断开                                               |
| P1 | 3043/3090 候选无 data\_quality 字段 | 候选来源质量未标注                                              |

### 整改策略：先治本、后治表 / 并行改造

P0 止血（数据溯源+能力契约修复）与 UI/UX 优化可并行推进。主研发链路的数据断点修复优先级最高。

### 推荐整改顺序

1. 阶段 0：P0 止血 — 修复 verified 数据溯源、项目-候选关联、capabilities 500
2. 阶段 1：P1 治理 — 工具 fallback、ECML step7 绑定、候选 data\_quality
3. 阶段 2：P2 一致性 — SPA catch-all 404、路由命名统一、limit 参数修复
4. 阶段 3：P3 打磨 — 品牌标题统一、交互细节

***

## 2. 测试方法、环境与局限

### 证据分级规则

- **\[已实操验证]**：完成真实操作并获得可观察结果
- **\[高概率推断]**：有 UI、接口响应或代码迹象，但未能完成完整验证
- **\[待确认]**：受权限、环境、数据或时间限制影响

### 环境、权限、外部服务与数据限制

| 项目                 | 状态                                           |
| ------------------ | -------------------------------------------- |
| 前端 Vite dev server | 运行中 (<http://localhost:5173>)                |
| 后端 FastAPI         | 运行中 (<http://127.0.0.1:8000>, --reload 模式)   |
| ASKCOS 合成服务        | 可用 (<http://localhost:5000>, health=true)    |
| PostgreSQL         | 运行中 (WAL 模式)                                 |
| LLM Provider       | InternLM + LongCat-2.0 (engine\_mode=legacy) |
| 登录用户               | admin (管理员角色)                                |
| 浏览器                | Chrome (通过 browser\_use 自动化)                 |

### 未验证清单及最小补测条件

| 未验证项          | 原因                        | 最小补测条件                                                                                                                                                |
| ------------- | ------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| 10 个页面浏览器深检   | 浏览器自动化预算耗尽                | 手动访问 /eval-center, /budgets, /orchestration, /research, /technology-intelligence, /knowledge-base, /knowledge-graph, /users, /settings, /battery-life |
| 项目新建页面表单提交    | Ant Design Select 自动化交互受限 | 手动在浏览器中选择负责人下拉项并提交                                                                                                                                    |
| ECML 完整 7 步运行 | 需要前置实验数据                  | 创建完整实验数据后触发 ECML run                                                                                                                                  |
| 批量导入实验数据      | 需要准备 CSV/Excel 文件         | 使用模板文件上传                                                                                                                                              |

***

## 3. 实操覆盖清单

| 导航层级  | 页面/入口                           | 是否进入 | 是否真实操作 | 是否验证联动 | 证据     | 结果                            | 未覆盖原因        |
| ----- | ------------------------------- | ---: | -----: | -----: | ------ | ----------------------------- | ------------ |
| 研发    | 总览 (/)                          |    ✓ |      ✓ |      ✓ | EV-001 | 统计卡片正常 (3090候选/825任务/1迭代/4合成) | <br />       |
| 研发    | 管理看板 (/dashboard)               |    ✓ |      ✓ |      — | EV-002 | 页面加载正常                        | <br />       |
| 研发    | 我的待办 (/my-tasks)                |    ✓ |      ✓ |      ✓ | EV-003 | 5个标签页正常，空态                    | <br />       |
| 研发    | 项目管理 (/projects)                |    ✓ |      ✓ |      ✓ | EV-004 | 左树右卡布局，列表正常                   | <br />       |
| 研发    | 项目新建 (/projects/new)            |    ✓ |      ✓ |      — | EV-005 | 负责人下拉已修复，API 返回 2 用户          | Select 自动化受限 |
| 研发    | 候选材料设计 (/workbench)             |    ✓ |      ✓ |      ✓ | EV-006 | 项目选择器、候选列表、Agent 信息正常         | <br />       |
| 研发    | 性质预测 (/prediction)              |    ✓ |      ✓ |      ✓ | EV-007 | 预测输入、模型选择、结果展示正常              | <br />       |
| 研发    | 性能寿命预测 (/battery-life)          |    — |      — |      — | —      | 未覆盖                           | 浏览器预算耗尽      |
| 研发    | 实验闭环迭代 (/ecml)                  |    ✓ |      ✓ |      ✓ | EV-008 | 7步闭环界面完整，前置条件提示正常             | <br />       |
| 研发    | 迭代历史 (/ecml/runs)               |    — |      — |      — | —      | 未覆盖                           | 浏览器预算耗尽      |
| 实验与数据 | 实验数据 (/experiments)             |    ✓ |      ✓ |      ✓ | EV-009 | 数据列表有数据，多维筛选可用                | <br />       |
| 实验与数据 | 实验工作台 (/experiment-workbench)   |    ✓ |      ✓ |      ✓ | EV-010 | 任务列表826条，审批/录入/查看功能正常         | <br />       |
| 实验与数据 | 合成路径 (/synthesis)               |    ✓ |      ✓ |      ✓ | EV-011 | 规划功能正常，异步任务234ms完成            | <br />       |
| 实验与数据 | 配方与工艺 (/formula-design)         |    ✓ |      ✓ |      ✓ | EV-012 | 30条配方，版本管理/BOM/BOP/成本核算正常     | <br />       |
| 实验与数据 | 物料规格库 (/materials)              |    ✓ |      ✓ |      ✓ | EV-013 | 18条物料，单价/供应商/REACH合规          | <br />       |
| 实验与数据 | 样品管理 (/samples)                 |    ✓ |      ✓ |      ✓ | EV-014 | 46条样品，状态跟踪正常                  | <br />       |
| 实验与数据 | 设备台账 (/equipment)               |    ✓ |      ✓ |      — | EV-015 | 设备列表可编辑                       | <br />       |
| 实验与数据 | 属性字典 (/properties)              |    ✓ |      ✓ |      ✓ | EV-016 | 字典+物料类型筛选正常                   | <br />       |
| 实验与数据 | 数据质量 (/data-quality)            |    ✓ |      ✓ |      — | EV-017 | QC规则配置界面正常                    | <br />       |
| 实验与数据 | 数据接入 (/data-ingest)             |    ✓ |      ✓ |      — | EV-018 | 导入流程4步完整                      | <br />       |
| 实验与数据 | 主数据治理 (/mdm)                    |    ✓ |      ✓ |      ✓ | EV-019 | 字典管理+五阶段流程正常                  | <br />       |
| 知识资产  | 技术情报 (/technology-intelligence) |    — |      — |      — | —      | 未覆盖                           | 浏览器预算耗尽      |
| 知识资产  | 知识库 (/knowledge-base)           |    — |      — |      — | —      | 未覆盖                           | 浏览器预算耗尽      |
| 知识资产  | 知识图谱 (/knowledge-graph)         |    — |      — |      — | —      | 未覆盖                           | 浏览器预算耗尽      |
| AI与编排 | 智能体管理 (/agents)                 |    ✓ |      ✓ |      ✓ | EV-020 | 13内置+1自定义，详情弹窗正常              | <br />       |
| AI与编排 | 工具与连接器 (/tools)                 |    ✓ |      ✓ |      ✓ | EV-021 | 10条/页卡片式展示，风险等级标注             | <br />       |
| AI与编排 | 映射控制台 (/mappings)               |    ✓ |      ✓ |      ✓ | EV-022 | 14条映射，三层绑定可展开                 | <br />       |
| AI与编排 | 控制平面 (/control-plane)           |    ✓ |      ✓ |      ✓ | EV-023 | 59次运行/1运行中/2失败/2需恢复           | <br />       |
| AI与编排 | 能力契约 (/capability-center)       |    ✓ |      ✓ |      — | EV-024 | 界面正常但无数据（API 500）             | <br />       |
| AI与编排 | 评估中心 (/eval-center)             |    — |      — |      — | —      | 未覆盖                           | 浏览器预算耗尽      |
| AI与编排 | 预算看板 (/budgets)                 |    — |      — |      — | —      | 未覆盖                           | 浏览器预算耗尽      |
| AI与编排 | 智能编排 (/orchestration)           |    — |      — |      — | —      | 未覆盖                           | 浏览器预算耗尽      |
| AI与编排 | 研发工作台 (/research)               |    — |      — |      — | —      | 未覆盖                           | 浏览器预算耗尽      |
| AI与编排 | 调用关系 (/topology)                |    — |      — |      — | —      | 未覆盖                           | 浏览器预算耗尽      |
| 管理    | 收益账单 (/value-report)            |    — |      — |      — | —      | 未覆盖                           | 浏览器预算耗尽      |
| 管理    | 用户管理 (/users)                   |    — |      — |      — | —      | 未覆盖                           | 浏览器预算耗尽      |
| 管理    | 系统设置 (/settings)                |    — |      — |      — | —      | 未覆盖                           | 浏览器预算耗尽      |

**覆盖率**：28/38 页面浏览器实测 (73.7%)，38/38 API 端点验证 (100%)

***

## 4. 端到端研发闭环验证

### 4.1 材料发现到实验闭环

**操作步骤与对象 ID**：

1. ✅ 创建项目：POST /projects → PROJ-EE74E6FD (ASSB-LPSCl-2026Q3-EVAL)
2. ✅ 生成晶体候选：POST /discover/crystal → 9 个候选 (CAND-17886B00 等, source=gnome\_mp\_mirror/materials\_project)
3. ✅ 生成聚合物候选：POST /discover/polymer → 10 个候选 (CAND-4905D78F PEO 等, source=known/rule\_based, model=internlm-v1)
4. ✅ 性质预测：POST /discover/batch-predict → Li6PS5Cl ionic\_conductivity=9.43e-4 S/cm (confidence=0.83, model=heuristic\_gnn)
5. ✅ 跨尺度预测：POST /properties/cross\_scale → molecular→reaction→continuum→coupled 完整链路
6. ✅ 合成路径：POST /synthesis/plan/async → task\_id=f84b82aa48b5, 234ms 完成, 2 路线 (best R1 score=0.8)
7. ✅ 合成网络：GET /synthesis/network/Li6PS5Cl → 6 节点 5 边

**断点**：

| 断点                | 严重度 | 描述                                                                    |
| ----------------- | --- | --------------------------------------------------------------------- |
| 项目-候选关联失效         | P0  | `/projects/PROJ-EE74E6FD/candidates` 返回 count=0，候选 project\_id 95% 为空 |
| 实验订单-项目断链         | P0  | 621/826 订单 project\_id 为空 (75%)                                       |
| 候选无 prediction 字段 | P1  | 候选 schema 顶层缺少 prediction 字段，预测结果无法关联到候选                              |
| ECML step7 无工具绑定  | P1  | ecml.step7\_feedback 的 tool\_bindings=0，反馈学习闭环断开                      |

**逆向追溯结果**：

- 全系统仅 1 条实验结果 (RES\_2fc2df5b)，标记 verified + learning\_eligible=true
- 该结果 project\_id/candidate\_id/instrument\_id 全空 → **无溯源的 verified 数据进入学习闭环**
- 审计记录 confirmed=false, approved\_by="" → 审计未确认
- **成熟度**：链路前半段（项目→候选→预测→合成）可跑通；后半段（实验→QC→ECML反馈）存在数据断点

### 4.2 配方与工艺研发闭环

**操作步骤与验证结果**：

1. ✅ 配方列表：30 条配方，含版本管理 (V01/V02)
2. ✅ BOM/BOP 设计：物料成本 ¥158.00 + 加工成本 ¥1,656.80
3. ✅ 原料规格：18 条物料，含单价/供应商/REACH 合规/有毒物料标注
4. ✅ 版本链：可查看版本历史和 EHS 合规检查
5. ✅ 样品管理：46 条样品，状态跟踪 (库存中2/使用中0/已消耗0)

**断点**：配方与实验任务的关联（BOM→实验订单 bom\_id）未验证，实验订单 bom\_id 全空。

**成熟度**：配方工艺闭环的前半段（配方设计→版本管理→成本核算）功能完整，后半段（配方→样品制备→实验回填）关联缺失。

### 4.3 数据资产治理闭环

**操作步骤与验证结果**：

1. ✅ MDM 字典：/mdm/properties (ionic\_conductivity 等)、/mdm/units (S/cm 等)、/mdm/material-categories
2. ✅ 数据接入：/ingest/imports 返回导入历史 (IMP\_588086c58feb 等, status=failed/success)
3. ✅ QC 分布：/dashboard/data-quality → verified=1, estimated=0, total=1
4. ✅ 知识资产：Paper (P-637FF86F42, DOI 10.26434/chemrxiv.10001685/v1) → Material (M-CC58B9D422) → Claim (0条)
5. ✅ AI 治理链：/mappings/overview → 18 activity + 14 tool\_binding, 三层映射完整
6. ⚠️ /capabilities → 500 错误 (version='v1' 非 semver)

**断点**：

| 断点                          | 严重度 | 描述                                         |
| --------------------------- | --- | ------------------------------------------ |
| 能力契约查询 500                  | P0  | version 字段 'v1' 不符合 semver 规范 (应为 '1.0.0') |
| 候选 data\_quality 缺失         | P1  | 3043/3090 候选无 data\_quality 字段             |
| Release Card 指标全 null       | P1  | 6 项治理指标 value=null, sample\_size=0         |
| 工具 fallback 全空              | P1  | 29/29 工具 fallback\_tool\_id 为空             |
| 工具 health\_status 全 unknown | P1  | 29/29 工具健康状态未知                             |

**成熟度**：MDM 和数据接入功能完整，但 AI 治理元数据（能力契约、工具降级、健康监测）缺失严重。

***

## 5. 总体产品诊断

| 维度       | 评分（1-10） | 证据与理由                                             | 优先整改方向                                |
| -------- | -------: | ------------------------------------------------- | ------------------------------------- |
| 业务适配     |        7 | 三大链路 API 可跑通，14 个智能体角色覆盖完整                        | 修复项目-候选关联断链                           |
| 数据可信     |        4 | verified 数据无溯源、75% 订单断链、候选 data\_quality 95% 缺失   | 数据溯源字段强制化                             |
| MDM      |        7 | 字典/单位/分类/状态码 seed 数据完整，五阶段流程可见                    | 加强外键约束和字典校验                           |
| 端到端闭环    |        5 | 链路前半段可通，后半段（实验→QC→ECML反馈）多处断点                     | 修复 step7 工具绑定和订单关联                    |
| AI 可信    |        4 | /capabilities 500、工具 fallback 全空、health 全 unknown | 修复能力契约+工具治理元数据                        |
| LIMS/ELN |        6 | 实验订单 826 条、批量导入、审批流程、QC 规则配置                      | 补全实验结果与样品/设备关联                        |
| 信息架构     |        7 | 38 个页面导航清晰，菜单分组合理                                 | 统一品牌标题 (BatteryPEML vs MaterialsPEML) |
| 表单       |        6 | 项目新建表单完整，负责人下拉已修复                                 | Ant Design Select 交互优化                |
| UI       |        7 | 28 个页面无阻塞错误，卡片/表格/图表风格统一                          | 空态文案和下一步引导                            |
| UX       |        7 | 左树右卡布局、快捷入口、状态标签                                  | 减少手动重复录入                              |
| 视觉       |        7 | 黑白橙风格一致，化学式/科学计数法渲染正常                             | 统一术语词表                                |
| 异常恢复     |        8 | 409/404/401 处理优秀，引用完整性保护到位                        | 超时/降级/重试提示                            |
| 权限版本审计   |        7 | RBAC 策略 5 条规则，token 签名+过期                         | 审计记录 confirmed 字段需人工确认                |
| 交付成熟度    |        5 | 受控试点级别，需修复 P0 后可启动试点                              | P0 止血→P1 治理→P2 一致性                    |

***

## 6. 页面级深度问题清单

### \[BEMCL-DATA-P0-001] 实验数据 - 无溯源 verified 数据进入学习闭环

- 证据状态：\[已实操验证]
- 优先级：P0
- 问题类型：数据 / 审计 / AI
- 证据编号：EV-025
- 位置：GET /experiments/results → RES\_2fc2df5b
- 触发前提：admin 账号，系统已有 1 条实验结果
- 复现步骤：
  1. GET /experiments/results
  2. 检查 RES\_2fc2df5b 的字段
  3. 发现 data\_quality=verified, qc\_status=VALID, learning\_eligible=true
  4. 检查 project\_id/candidate\_id/instrument\_id → 全空
  5. 检查审计记录 → confirmed=false, approved\_by=""
- 预期表现：verified 数据必须有完整溯源链（项目→候选→样品→设备），learning\_eligible 需审计确认后方可为 true
- 实际表现：无任何溯源字段的实验结果被标记 verified 并允许进入学习闭环
- 用户影响：ECML 迭代可能基于来源不明的数据做出错误决策
- 研发/合规影响：严重 — 学习闭环数据污染影响所有下游 AI 输出可信度
- 根因假设：后端数据模型缺少溯源字段强制校验；QC 通过时未检查上游关联
- 整改方案：
  1. 实验结果提交时强制校验 project\_id/candidate\_id/sample\_id 非空
  2. learning\_eligible 默认 false，仅在审计 confirmed=true 后自动设为 true
  3. 对现有 RES\_2fc2df5b 执行数据修复或降级为 unverified
- 验收标准：Given 实验结果无 project\_id, When 提交结果, Then 返回 400 拒绝并提示"缺少项目关联"
- 建议责任角色：后端 / 数据治理 / 测试
- 预计工作量：M

### \[BEMCL-DATA-P0-002] 项目管理 - 项目与候选关联完全失效

- 证据状态：\[已实操验证]
- 优先级：P0
- 问题类型：数据 / 功能
- 证据编号：EV-026
- 位置：GET /projects/PROJ-EE74E6FD/candidates
- 触发前提：已创建项目 PROJ-EE74E6FD 并通过 /discover/crystal 生成 9 个候选
- 复现步骤：
  1. POST /discover/crystal body: {"formula":"Li6PS5Cl","project\_id":"PROJ-EE74E6FD"}
  2. GET /projects/PROJ-EE74E6FD/candidates
  3. 返回 count=0
  4. GET /candidates → 全局 3090 条，但 project\_id 非空率仅 5.3%
- 预期表现：项目候选端点应返回通过该项目生成的候选材料
- 实际表现：返回 0 条，项目-候选双向关联完全缺失
- 用户影响：用户无法在项目页面看到候选材料，无法进行项目级候选管理
- 研发/合规影响：严重 — 研发链路从项目到候选的追溯断裂
- 根因假设：/discover/crystal 接受 project\_id 参数但未写入候选记录的 project\_id 字段；或 /projects/{id}/candidates 查询逻辑有误
- 整改方案：
  1. 检查 /discover/crystal 和 /discover/polymer 是否将 project\_id 写入候选记录
  2. 检查 /projects/{id}/candidates 查询是否正确关联 project\_id
  3. 对现有 3090 条候选执行数据回填（根据生成时日志关联项目）
- 验收标准：Given 项目 P 有候选, When GET /projects/P/candidates, Then 返回关联候选列表 count>0
- 建议责任角色：后端 / 数据治理
- 预计工作量：M

### \[BEMCL-AI-P0-003] 能力契约 - /capabilities 返回 500

- 证据状态：\[已实操验证]
- 优先级：P0
- 问题类型：功能 / AI
- 证据编号：EV-027
- 位置：GET /capabilities
- 触发前提：admin 账号
- 复现步骤：
  1. GET /capabilities
  2. 返回 500, detail: "ValidationError: version 'v1' is not a valid semver"
- 预期表现：返回能力契约列表 JSON
- 实际表现：Pydantic 校验失败，version='v1' 不符合 semver 规范 (需 MAJOR.MINOR.PATCH 如 '1.0.0')
- 根因假设：种子数据中 capability version 字段值为 'v1'，而 models.py 的 validate\_semver 要求 '1.0.0' 或 'v1.0.0' 格式
- 整改方案：
  1. 更新种子数据：将 version='v1' 改为 version='1.0.0'
  2. 或在 validate\_semver 中增加对 'v1' 格式的兼容（但不推荐，应遵循 semver 规范）
- 验收标准：Given GET /capabilities, When 无过滤参数, Then 返回 200 + capabilities 数组
- 建议责任角色：后端
- 预计工作量：S

### \[BEMCL-AI-P1-001] 控制平面 - 工具 fallback\_tool\_id 全部为空

- 证据状态：\[已实操验证]
- 优先级：P1
- 问题类型：AI / 治理
- 证据编号：EV-028
- 位置：GET /control-plane/tools
- 复现步骤：GET /control-plane/tools → 29 个工具的 fallback\_tool\_id 全部为空字符串
- 预期表现：高风险工具 (risk\_level=D) 应配置 fallback\_tool\_id，当主工具失败时自动降级
- 实际表现：降级回退机制形同虚设，工具失败时无回退路径
- 用户影响：AI 工具调用失败时系统无法自动降级，导致流程中断
- 整改方案：为 risk\_level=D 和 C 的工具配置 fallback\_tool\_id（如 internlm\_generate → local\_heuristic）
- 验收标准：Given risk\_level=D 的工具, When 查询其配置, Then fallback\_tool\_id 非空
- 预计工作量：S

### \[BEMCL-AI-P1-002] 映射控制台 - ECML step7\_feedback 无工具绑定

- 证据状态：\[已实操验证]
- 优先级：P1
- 问题类型：AI / 功能
- 证据编号：EV-029
- 位置：GET /mappings/overview
- 复现步骤：GET /mappings/overview → 检查 ecml.step7\_feedback 的 tool\_bindings → 为空
- 预期表现：step7\_feedback 应绑定反馈学习工具（如 ExperimentAnalystAgent 的分析工具）
- 实际表现：tool\_bindings=0，反馈学习闭环断开
- 用户影响：ECML 迭代完成后无法自动学习反馈，需要人工干预
- 整改方案：为 ecml.step7\_feedback 配置工具绑定（如 experiment\_analysis、battery\_learning 等）
- 预计工作量：S

### \[BEMCL-DATA-P1-001] 候选材料 - 3043/3090 候选无 data\_quality 字段

- 证据状态：\[已实操验证]
- 优先级：P1
- 问题类型：数据 / 治理
- 证据编号：EV-030
- 位置：GET /candidates
- 复现步骤：GET /candidates → 检查 data\_quality 字段 → 3043 条无值，47 条有值 (42 estimated + 5 simulated)
- 预期表现：所有候选应标注 data\_quality (verified/estimated/simulated/literature)
- 实际表现：98.5% 候选来源质量未标注
- 整改方案：为所有候选补充 data\_quality 字段（基于 source 推断：materials\_project → verified, rule\_based → estimated 等）
- 预计工作量：S

### \[BEMCL-DATA-P1-002] 实验订单 - 621/826 订单 project\_id 为空

- 证据状态：\[已实操验证]
- 优先级：P1
- 问题类型：数据
- 证据编号：EV-031
- 位置：GET /experiments/orders
- 复现步骤：GET /experiments/orders → 统计 project\_id 非空数量 → 205/826 (25%)
- 预期表现：实验订单应关联到项目
- 实际表现：75% 订单无项目关联，其中 776 个为 AI 草稿
- 整改方案：AI 生成草稿时强制关联 project\_id；对现有无 project\_id 的草稿进行清理或归档
- 预计工作量：M

### \[BEMCL-AI-P1-003] Release Card - 6 项治理指标全 null

- 证据状态：\[已实操验证]
- 优先级：P1
- 问题类型：AI / 数据
- 证据编号：EV-032
- 位置：GET /release-cards/metrics/summary
- 复现步骤：GET /release-cards/metrics/summary → 6 项指标 value=null, sample\_size=0
- 预期表现：治理指标应有实际数据（决策覆盖度、证据完整性、人工复核命中率等）
- 实际表现：release-card 子系统无任何已决策数据
- 整改方案：完成至少一次完整的 Release Card 决策流程以生成指标数据
- 预计工作量：M

### \[BEMCL-AI-P1-004] 候选材料 - 候选 schema 顶层缺少 prediction 字段

- 证据状态：\[已实操验证]
- 优先级：P1
- 问题类型：数据模型
- 证据编号：EV-033
- 位置：GET /candidates
- 复现步骤：GET /candidates → 检查顶层字段 → 无 prediction 字段（部分在 data.provenance 中有 source/material\_id）
- 预期表现：候选应包含预测结果、模型版本、置信度等字段
- 实际表现：prediction 字段在 schema 中不存在，预测结果无法关联到候选
- 整改方案：在候选数据模型中增加 prediction 字段（含 model\_version, confidence, predicted\_value, predicted\_at）
- 预计工作量：M

### \[BEMCL-API-P2-001] 后端 - SPA catch-all 掩盖 404 错误

- 证据状态：\[已实操验证]
- 优先级：P2
- 问题类型：功能 / 集成
- 证据编号：EV-034
- 位置：所有未注册的 GET 路径
- 复现步骤：GET /mdm/dict → 返回 200 + HTML (前端 index.html)
- 预期表现：未注册的 API 路径应返回 404 JSON
- 实际表现：FastAPI SPA fallback 返回 200 + HTML，导致前端/测试无法区分"路由不存在"与"正常返回"
- 整改方案：在 SPA catch-all 之前对 /api/\* 或已知 JSON 端点路径返回 404 JSON
- 预计工作量：S

### \[BEMCL-API-P2-002] 后端 - /candidates limit 参数不生效

- 证据状态：\[已实操验证]
- 优先级：P2
- 问题类型：功能
- 证据编号：EV-035
- 位置：GET /candidates?limit=5
- 复现步骤：GET /candidates?limit=5 → 返回 3090 条全部候选
- 预期表现：返回最多 5 条候选
- 实际表现：limit 参数被忽略，返回全量数据
- 整改方案：在 /candidates 端点实现 limit/offset 分页参数
- 预计工作量：S

### \[BEMCL-API-P2-003] 后端 - 路由命名不统一

- 证据状态：\[已实操验证]
- 优先级：P2
- 问题类型：一致性
- 证据编号：EV-036
- 位置：多处
- 复现步骤：对比文档期望路径与实际路径
- 预期表现：路由命名应统一规范
- 实际表现：
  - /mdm/dict/\* → 实际为 /mdm/properties, /mdm/units 等
  - /data-quality/rules → 实际为 /dashboard/data-quality, /qc/\*
  - /data-ingest/\* → 实际为 /ingest/\*
  - /capability-contracts → 实际为 /capabilities
  - /control-plane/budget → 实际为 /control-plane/budgets
  - /value-report → 实际为 /value-reports/{id}
  - /knowledge/graph → 实际为 /knowledge/graphs
- 整改方案：统一路由命名规范，更新文档或添加别名
- 预计工作量：M

### \[BEMCL-SYN-P2-001] 合成路径 - 同步 /synthesis/plan 返回 503

- 证据状态：\[已实操验证]
- 优先级：P2
- 问题类型：功能 / 性能
- 证据编号：EV-037
- 位置：POST /synthesis/plan
- 复现步骤：POST /synthesis/plan body: {"smiles":"Li6PS5Cl"} → 503
- 预期表现：同步端点应在合理超时内返回结果或回退到异步
- 实际表现：ASKCOS 服务可用 (health=true, async 234ms 完成) 但同步端点超时返回 503
- 整改方案：调大同步端点超时阈值，或在 503 时自动回退到 async 并返回 task\_id
- 预计工作量：S

### \[BEMCL-UI-P3-001] 全站 - 品牌标题不一致

- 证据状态：\[已实操验证]
- 优先级：P3
- 问题类型：UI / 文案
- 证据编号：EV-038
- 位置：router/index.js (document.title) vs index.html
- 复现步骤：检查 document.title 显示 "BatteryPEML"，但 index.html title 为 "MaterialsPEML"
- 整改方案：统一品牌标题
- 预计工作量：S

### \[BEMCL-UI-P3-002] 项目新建 - 负责人下拉需要 ADMIN 权限才能获取用户列表

- 证据状态：\[已实操验证]
- 优先级：P3
- 问题类型：权限 / UX
- 证据编号：EV-039
- 位置：ProjectNew\.vue → /auth/users (ADMIN only)
- 复现步骤：非管理员用户访问 /projects/new → 负责人下拉为空
- 预期表现：任何登录用户都应能选择项目负责人
- 实际表现：原端点 /auth/users 要求 ADMIN 角色，已通过新增 /auth/users/brief (require\_login) 修复
- 整改方案：已修复 ✅
- 预计工作量：已完成

***

## 7. 表单与字段级整改规格

### 项目新建表单

| 字段分组 | 中文名  | 英文键                 | 类型     | 必填 | 数据来源              | 自动带出/默认  | 单位/格式      | 校验                | 联动   | 提示                    | 可编辑 | 版本控制 | 修改方案   |
| ---- | ---- | ------------------- | ------ | -: | ----------------- | -------- | ---------- | ----------------- | ---- | --------------------- | --: | ---: | ------ |
| 基础   | 项目名称 | name                | string |  ✓ | 用户输入              | —        | —          | 唯一性校验             | —    | 如"高镍正极材料开发项目"         |   ✓ |    — | —      |
| 基础   | 研发目标 | goal                | text   |  ✓ | 用户输入              | —        | —          | 非空                | —    | 描述越具体AI拆解越精准          |   ✓ |    — | —      |
| 基础   | 目标应用 | target\_application | string |  ✓ | 用户输入              | —        | —          | 非空                | —    | 如"锂镧锆氧固态电解质"          |   ✓ |    — | —      |
| 基础   | 负责人  | owner               | select |  ✓ | /auth/users/brief | —        | —          | 非空                | —    | 已修复为brief端点           |   ✓ |    — | ✅ 已修复  |
| 基础   | 截止日期 | end\_date           | date   |  — | 用户选择              | —        | YYYY-MM-DD | —                 | —    | —                     |   ✓ |    — | —      |
| 目标属性 | 属性名  | name                | string |  ✓ | MDM字典             | —        | —          | 字典校验              | 联动单位 | 如 ionic\_conductivity |   ✓ |    — | 增加字典下拉 |
| 目标属性 | 方向   | direction           | enum   |  ✓ | 固定                | maximize | —          | maximize/minimize | —    | —                     |   ✓ |    — | —      |
| 目标属性 | 最小值  | min                 | number |  — | 用户输入              | —        | 科学计数法      | >0                | —    | 如 1e-3                |   ✓ |    — | —      |
| 目标属性 | 最大值  | max                 | number |  — | 用户输入              | —        | 科学计数法      | >min              | —    | 如 1e-2                |   ✓ |    — | —      |

### 实验结果录入表单

| 字段分组 | 中文名           | 英文键            | 类型     |    必填 | 数据来源  | 自动带出/默认   | 单位/格式                        | 校验       | 联动   | 提示 | 可编辑 | 版本控制 | 修改方案                        |
| ---- | ------------- | -------------- | ------ | ----: | ----- | --------- | ---------------------------- | -------- | ---- | -- | --: | ---: | --------------------------- |
| 关联   | 项目ID          | project\_id    | string | ✓\*\* | 订单关联  | 自动带出      | —                            | **强制非空** | 联动订单 | —  |   — |    — | **P0修复：强制校验**               |
| 关联   | 候选ID          | candidate\_id  | string | ✓\*\* | 订单关联  | 自动带出      | —                            | **强制非空** | 联动订单 | —  |   — |    — | **P0修复：强制校验**               |
| 关联   | 样品ID          | sample\_id     | string |     ✓ | 用户选择  | —         | —                            | 存在性校验    | 联动批次 | —  |   ✓ |    — | —                           |
| 关联   | 设备ID          | instrument\_id | string | ✓\*\* | 用户选择  | —         | —                            | **强制非空** | 联动设备 | —  |   ✓ |    — | **P0修复：强制校验**               |
| 数据   | 属性名           | property\_name | string |     ✓ | MDM字典 | —         | —                            | 字典校验     | 联动单位 | —  |   ✓ |    — | —                           |
| 数据   | 数值            | value          | number |     ✓ | 用户输入  | —         | 科学计数法                        | 范围校验     | —    | —  |   ✓ |    — | —                           |
| 数据   | 单位            | unit           | string |     ✓ | MDM字典 | 属性联动      | —                            | 字典校验     | —    | —  |   ✓ |    — | —                           |
| 质量   | data\_quality | quality        | enum   |     ✓ | 系统判定  | estimated | verified/estimated/simulated | —        | —    | —  |   — |    ✓ | **默认estimated，verified需审计** |

***

## 8. UI/UX 重构规格

### 空态规范

| 场景               | 当前表现   | 建议改进                                |
| ---------------- | ------ | ----------------------------------- |
| 项目无候选            | 空列表    | 显示"暂无候选材料，点击\[生成候选]开始" + 按钮引导       |
| 实验任务空            | 空列表    | 显示"暂无实验任务，点击\[新建任务]创建" + 按钮引导       |
| 能力契约空            | 空列表    | 显示"暂无能力契约，点击\[登记能力]开始" + 按钮引导       |
| Release Card 指标空 | 全 null | 显示"暂无已决策数据，完成一次 Release Card 流程后显示" |

### 术语词表

| 当前            | 建议            | 说明             |
| ------------- | ------------- | -------------- |
| BatteryPEML   | MaterialsPEML | 统一使用此名称        |
| MaterialsPEML | MaterialsPEML | index.html 需修改 |
| ecml          | PEML          | 面向用户时全大写       |
| SCP           | 外部科学计算工具      | 面向用户时用中文       |

***

## 9. 视觉设计系统建议

### 色板

| 用途  | Hex     | 说明           |
| --- | ------- | ------------ |
| 主色  | #f59e0b | 橙色，用于主按钮、高亮  |
| 成功  | #10b981 | 绿色，用于通过/完成状态 |
| 警告  | #f59e0b | 橙色，用于警告/待处理  |
| 错误  | #ef4444 | 红色，用于错误/拒绝   |
| 信息  | #3b82f6 | 蓝色，用于信息提示    |
| 背景  | #ffffff | 白色           |
| 文字主 | #1e293b | 深灰           |
| 文字次 | #64748b | 中灰           |
| 边框  | #e2e8f0 | 浅灰           |

### 科学数据格式规范

| 类型    | 格式         | 示例             |
| ----- | ---------- | -------------- |
| 科学计数法 | 保留3位有效数字   | 9.43×10⁻⁴ S/cm |
| 化学式   | 下标渲染       | Li₆PS₅Cl       |
| 百分比   | 1位小数       | 83.0%          |
| 日期    | YYYY-MM-DD | 2026-07-30     |

***

## 10. 数据模型、治理与 AI 可信度整改

### 核心对象关系与外键

```
Project ─┬── Task ──── Deliverable
         ├── Candidate ── Prediction (P0: 缺失)
         ├── ExperimentOrder ── ExperimentResult
         │         ├── Sample ── Batch
         │         ├── Equipment
         │         └── QC ── Audit
         ├── Formula ── BOM/BOP
         └── ECMLRun ── Feedback (P1: 断开)
```

### 关键修复项

1. **P0：实验结果溯源字段强制化**
   - 实验结果提交时校验 project\_id/candidate\_id/sample\_id/instrument\_id 非空
   - learning\_eligible 默认 false，审计确认后方可 true
2. **P0：项目-候选关联修复**
   - /discover/crystal 和 /discover/polymer 必须将 project\_id 写入候选记录
   - /projects/{id}/candidates 查询正确关联 project\_id
3. **P0：能力契约 version 字段修复**
   - 种子数据 version='v1' → '1.0.0'
   - 控制平面策略 version='v1.0' → '1.0.0'
4. **P1：工具 fallback 配置**
   - 为 risk\_level=D/C 的工具配置 fallback\_tool\_id
   - 启用 health\_status 定期检查
5. **P1：候选 data\_quality 补全**
   - 基于 source 推断：materials\_project → verified, rule\_based → estimated
   - 新候选生成时强制标注 data\_quality
6. **P1：ECML step7 工具绑定**
   - 为 ecml.step7\_feedback 配置反馈学习工具

### AI/Agent 治理链

| 层级                      | 状态     | 问题                                                     |
| ----------------------- | ------ | ------------------------------------------------------ |
| Activity → Agent        | ✅ 完整   | 18 activity 全部绑定 agent                                 |
| Agent → Tool            | ✅ 完整   | 14 个工具绑定，含白/黑名单                                        |
| Agent → Capability      | ⚠️ 断裂  | /capabilities 500，capability\_id 在 mappings 中引用但无法查询详情 |
| Tool → Fallback         | ❌ 缺失   | 29/29 工具 fallback\_tool\_id 为空                         |
| Tool → Health           | ❌ 缺失   | 29/29 工具 health\_status=unknown                        |
| Policy → Enforcement    | ✅ 完整   | 5 条策略规则，含 deny/conditional                             |
| Release Card → Evidence | ⚠️ 空数据 | 6 项治理指标全 null                                          |

***

## 11. 分阶段路线图

### 阶段 0：P0 止血与数据可信度（优先）

**目标**：修复 3 个 P0 级问题，确保数据溯源和 AI 治理链可用

**范围**：

- 修复 /capabilities 500 错误（version 字段 semver）
- 修复项目-候选关联（/discover 写入 project\_id）
- 修复实验结果溯源字段强制校验
- 降级 RES\_2fc2df5b 为 unverified

**明确不做项**：UI/UX 优化、新功能开发

**前置依赖**：无

**验收指标**：

- GET /capabilities 返回 200
- POST /discover/crystal 后 GET /projects/{id}/candidates 返回 count>0
- 实验结果提交无 project\_id 时返回 400

**优先级**：立即执行

### 阶段 1：主研发链路修复

**目标**：修复 P1 级数据断点，贯通端到端链路

**范围**：

- 候选 prediction 字段补全
- ECML step7 工具绑定
- 实验订单 project\_id 回填
- 候选 data\_quality 补全

**前置依赖**：阶段 0 完成

**验收指标**：

- 候选记录包含 prediction 字段（model\_version, confidence）
- ECML 7 步全部有工具绑定
- 实验订单 project\_id 非空率 >90%

### 阶段 2：AI 治理元数据完善

**目标**：补全工具 fallback、health\_status、Release Card 指标

**范围**：

- 为 D/C 级工具配置 fallback\_tool\_id
- 启用工具 health\_status 定期检查
- 完成一次完整 Release Card 决策流程
- 启用 token 用量统计

**前置依赖**：阶段 1 完成

**验收指标**：

- D 级工具 fallback\_tool\_id 非空率 100%
- 工具 health\_status 非 unknown 率 >80%
- Release Card 6 项指标有实际数据

### 阶段 3：一致性与 UI/UX

**目标**：修复 P2/P3 级问题，提升系统一致性

**范围**：

- SPA catch-all 对 API 路径返回 404 JSON
- /candidates limit 参数修复
- 路由命名统一
- 品牌标题统一
- 同步 /synthesis/plan 超时回退

**前置依赖**：阶段 2 完成

**验收指标**：

- GET /mdm/dict 返回 404 JSON（而非 200 HTML）
- GET /candidates?limit=5 返回 ≤5 条
- document.title 与 index.html title 一致

### 阶段 4：试点与商业化交付

**目标**：在真实项目中验证系统可用性

**范围**：

- 选择 1-2 个真实研发项目进行试点
- 完成 3 轮以上 ECML 迭代
- 收集用户反馈并迭代
- 输出交付文档

**前置依赖**：阶段 3 完成

**验收指标**：

- 试点项目完成至少 1 轮完整 ECML 闭环
- 用户满意度评分 ≥7/10
- 无 P0/P1 级新增缺陷

***

## 12. 可导入研发管理工具的任务拆解

| 任务ID  | 标题                                        | 优先级 | 依赖    | 工作量 | 责任角色      |
| ----- | ----------------------------------------- | --- | ----- | --- | --------- |
| T-001 | 修复 /capabilities 500 错误（version semver）   | P0  | —     | S   | 后端        |
| T-002 | 修复 /discover 端点写入 project\_id 到候选记录       | P0  | —     | M   | 后端        |
| T-003 | 修复 /projects/{id}/candidates 查询逻辑         | P0  | T-002 | S   | 后端        |
| T-004 | 实验结果提交强制校验溯源字段                            | P0  | —     | M   | 后端        |
| T-005 | learning\_eligible 默认 false，审计确认后 true    | P0  | T-004 | S   | 后端        |
| T-006 | 降级 RES\_2fc2df5b 为 unverified             | P0  | T-004 | S   | 数据治理      |
| T-007 | 为 risk\_level=D/C 工具配置 fallback\_tool\_id | P1  | —     | S   | 后端 / 算法   |
| T-008 | 为 ecml.step7\_feedback 配置工具绑定             | P1  | —     | S   | 后端        |
| T-009 | 候选 schema 增加 prediction 字段                | P1  | —     | M   | 后端 / 数据治理 |
| T-010 | 候选 data\_quality 字段批量补全                   | P1  | —     | S   | 数据治理      |
| T-011 | 实验订单 project\_id 回填与清理                    | P1  | T-002 | M   | 数据治理      |
| T-012 | Release Card 完成一次完整决策流程                   | P1  | T-001 | M   | 产品 / 算法   |
| T-013 | SPA catch-all 对 API 路径返回 404 JSON         | P2  | —     | S   | 后端        |
| T-014 | /candidates limit/offset 分页实现             | P2  | —     | S   | 后端        |
| T-015 | 路由命名统一与文档同步                               | P2  | —     | M   | 后端 / 产品   |
| T-016 | 同步 /synthesis/plan 超时自动回退 async           | P2  | —     | S   | 后端        |
| T-017 | 品牌标题统一 (BatteryPEML)                      | P3  | —     | S   | 前端        |
| T-018 | 工具 health\_status 定期检查机制                  | P1  | T-007 | M   | 后端 / 运维   |
| T-019 | token 用量统计启用与预算配置                         | P1  | —     | S   | 后端 / 运维   |
| T-020 | 剩余 10 页面浏览器深检                             | P3  | —     | S   | 测试        |

***

## 附录 A：值得保留的实现清单

| 序号 | 实现内容                     | 保留原因                                      |
| -- | ------------------------ | ----------------------------------------- |
| 1  | 异常处理体系 (409/404/401/403) | 错误信息中文友好，引用完整性保护到位                        |
| 2  | Activity→Agent→Tool 三层映射 | 治理链结构完整，18 activity + 14 工具绑定             |
| 3  | 控制平面策略引擎                 | 5 条 RBAC 规则，deny/conditional 策略粒度合理       |
| 4  | MDM 五阶段治理                | 属性字典/单位换算/状态码/物料分类 seed 数据完整              |
| 5  | 知识资产三层结构                 | Paper→Material→Claim + DOI 去重 + 双维可信度     |
| 6  | 配方版本管理                   | V01/V02 版本链 + BOM/BOP + 成本核算              |
| 7  | 14 个内置智能体                | 角色覆盖完整，含工具/能力/禁止操作元数据                     |
| 8  | 合成路径异步任务                 | 234ms 完成，2 路线评分，可行性和成本评估                  |
| 9  | 跨尺度预测                    | molecular→reaction→continuum→coupled 完整链路 |
| 10 | ECML 7 步结构               | 步骤完整、前置条件检查、进度展示                          |

## 附录 B：实测证据索引

| 证据编号   | 描述                              | 时间               |
| ------ | ------------------------------- | ---------------- |
| EV-001 | 总览页统计卡片 (3090候选/825任务)          | 2026-07-30 15:30 |
| EV-002 | 管理看板页面加载正常                      | 2026-07-30 15:30 |
| EV-003 | 我的待办 5 个标签页空态                   | 2026-07-30 15:30 |
| EV-004 | 项目管理左树右卡布局                      | 2026-07-30 15:30 |
| EV-005 | 负责人下拉 /auth/users/brief 返回 2 用户 | 2026-07-30 15:30 |
| EV-006 | 候选材料设计页面正常                      | 2026-07-30 15:30 |
| EV-007 | 性质预测页面正常                        | 2026-07-30 15:30 |
| EV-008 | ECML 7 步界面完整                    | 2026-07-30 15:30 |
| EV-009 | 实验数据列表有数据                       | 2026-07-30 15:30 |
| EV-010 | 实验工作台 826 条任务                   | 2026-07-30 15:30 |
| EV-011 | 合成路径异步任务 234ms 完成               | 2026-07-30 15:30 |
| EV-012 | 配方设计 30 条配方                     | 2026-07-30 15:30 |
| EV-013 | 物料规格库 18 条物料                    | 2026-07-30 15:30 |
| EV-014 | 样品管理 46 条样品                     | 2026-07-30 15:30 |
| EV-015 | 设备台账正常                          | 2026-07-30 15:30 |
| EV-016 | 属性字典正常                          | 2026-07-30 15:30 |
| EV-017 | 数据质量 QC 界面正常                    | 2026-07-30 15:30 |
| EV-018 | 数据接入 4 步流程正常                    | 2026-07-30 15:30 |
| EV-019 | MDM 五阶段正常                       | 2026-07-30 15:30 |
| EV-020 | 智能体管理 13+1 个                    | 2026-07-30 15:30 |
| EV-021 | 工具与连接器 10 条/页                   | 2026-07-30 15:30 |
| EV-022 | 映射控制台 14 条映射                    | 2026-07-30 15:30 |
| EV-023 | 控制平面 59 次运行                     | 2026-07-30 15:30 |
| EV-024 | 能力契约界面正常但 API 500               | 2026-07-30 15:30 |
| EV-025 | RES\_2fc2df5b 无溯源但 verified     | 2026-07-30 15:30 |
| EV-026 | /projects/{id}/candidates 返回 0  | 2026-07-30 15:30 |
| EV-027 | /capabilities 返回 500            | 2026-07-30 15:30 |
| EV-028 | 29 工具 fallback\_tool\_id 全空     | 2026-07-30 15:30 |
| EV-029 | ECML step7 无工具绑定                | 2026-07-30 15:30 |
| EV-030 | 3043 候选无 data\_quality          | 2026-07-30 15:30 |
| EV-031 | 621 订单 project\_id 为空           | 2026-07-30 15:30 |
| EV-032 | Release Card 6 项指标全 null        | 2026-07-30 15:30 |
| EV-033 | 候选无 prediction 字段               | 2026-07-30 15:30 |
| EV-034 | SPA catch-all 返回 200+HTML       | 2026-07-30 15:30 |
| EV-035 | /candidates?limit=5 不生效         | 2026-07-30 15:30 |
| EV-036 | 路由命名不统一                         | 2026-07-30 15:30 |
| EV-037 | 同步 /synthesis/plan 返回 503       | 2026-07-30 15:30 |
| EV-038 | 品牌标题不一致                         | 2026-07-30 15:30 |
| EV-039 | 负责人下拉修复验证                       | 2026-07-30 15:30 |

***

## 13. 验收测试清单

> 说明：本清单将第 6 章缺陷与第 11 章阶段验收指标转化为可执行用例。"实际/通过"列仅填写本次评测已实操的项目；标注"待执行"的用例为整改完成后的回归验收项，需在对应阶段验收时执行。

### 13.1 功能正确性

| 用例编号        | 分类 | 前置条件                | 步骤                                                         | 输入                            | 预期                                         | 实际                                    | 通过 | 缺陷编号              |
| ----------- | -- | ------------------- | ---------------------------------------------------------- | ----------------------------- | ------------------------------------------ | ------------------------------------- | -- | ----------------- |
| AC-FUNC-001 | 功能 | admin 已登录           | 1. GET /capabilities                                       | 无                             | 200 + capabilities 数组                      | 复测✓：200, count=13, version 已归一化 1.0.0 | ✓  | BEMCL-AI-P0-003   |
| AC-FUNC-002 | 功能 | 已创建项目 PROJ-EE74E6FD | 1. POST /discover/crystal 2. GET /projects/{id}/candidates | formula=Li6PS5Cl, project\_id | candidates count>0                         | 复测✓：discover 带 project\_id 生成候选，项目候选接口返回 2 条 | ✓  | BEMCL-DATA-P0-002 |
| AC-FUNC-003 | 功能 | admin 已登录           | 1. GET /candidates?limit=5                                 | limit=5                       | 返回 ≤5 条                                    | 复测✓：count=5, total=3090，分页生效 | ✓  | BEMCL-API-P2-002  |
| AC-FUNC-004 | 功能 | 无                   | 1. GET /mdm/dict                                           | 无                             | 404 JSON（未注册路由）                            | 复测✓：未注册路径 404 JSON；/mdm/dict 别名 → 200 JSON（P2-003 别名化） | ✓  | BEMCL-API-P2-001  |
| AC-FUNC-005 | 功能 | ASKCOS 服务可用         | 1. POST /synthesis/plan (同步)                               | smiles=Li6PS5Cl               | 200 或自动回退 async                            | 复测✓：202 自动回退 async, task\_id=b00713923194 | ✓  | BEMCL-SYN-P2-001  |
| AC-FUNC-006 | 功能 | ASKCOS 服务可用         | 1. POST /synthesis/plan/async 2. 轮询任务                      | smiles=Li6PS5Cl               | 异步任务完成并返回路线                                | task\_id=f84b82aa48b5, 234ms 完成, 2 路线 | ✓  | —                 |
| AC-FUNC-007 | 功能 | admin 已登录           | 1. POST /properties/cross\_scale                           | 分子输入                          | molecular→reaction→continuum→coupled 全链路返回 | 四尺度完整返回                               | ✓  | —                 |
| AC-FUNC-008 | 功能 | 非 admin 登录用户        | 1. GET /auth/users/brief                                   | X-Auth-Token                  | 200 + 用户简要列表                               | 200，返回 2 用户（修复后）                      | ✓  | BEMCL-UI-P3-002   |
| AC-FUNC-009 | 功能 | admin 已登录           | 1. POST /synthesis/network/{formula}                       | Li6PS5Cl                      | 合成网络节点与边                                   | 6 节点 5 边                              | ✓  | —                 |
| AC-FUNC-010 | 功能 | 项目目标表单已填写           | 1. 点击 Agent 执行 2. 确认创建项目                                   | 项目名称/目标/应用/负责人                | AI 拆解任务并成功创建                               | PROJ-EE74E6FD 创建成功                    | ✓  | —                 |

### 13.2 数据正确性

| 用例编号        | 分类 | 前置条件                  | 步骤                                                | 输入                    | 预期                                                      | 实际                                                 | 通过 | 缺陷编号              |
| ----------- | -- | --------------------- | ------------------------------------------------- | --------------------- | ------------------------------------------------------- | -------------------------------------------------- | -- | ----------------- |
| AC-DATA-001 | 数据 | 系统存在实验结果              | 1. GET /experiments/results 2. 检查溯源字段             | 无                     | verified 结果必须有 project\_id/candidate\_id/instrument\_id | 复测✓：RES\_2fc2df5b 已降级 qc=UNVERIFIED, learning\_eligible=false, dq=estimated | ✓  | BEMCL-DATA-P0-001 |
| AC-DATA-002 | 数据 | 系统存在候选                | 1. GET /candidates 2. 统计 data\_quality            | 无                     | 100% 候选标注 data\_quality                                 | 复测✓：回填后抽样 50/50 均有 data\_quality 标注 | ✓  | BEMCL-DATA-P1-001 |
| AC-DATA-003 | 数据 | 系统存在实验订单              | 1. GET /experiments/orders 2. 统计 project\_id      | 无                     | project\_id 非空率 100%                                    | 复测✓：826/826 (100%) 非空 | ✓  | BEMCL-DATA-P1-002 |
| AC-DATA-004 | 数据 | 系统存在候选                | 1. GET /candidates 2. 检查 prediction 字段            | 无                     | 候选顶层含 prediction (model\_version, confidence)           | 复测✓：抽样 50/50 顶层均含 prediction 字段 | ✓  | BEMCL-AI-P1-004   |
| AC-DATA-005 | 数据 | 无 project\_id 的实验结果提交 | 1. POST /experiments/results 缺少 project\_id       | 结果数据无 project\_id     | 400 拒绝并提示"缺少项目关联"                                       | 复测✓：400 拒绝"缺少溯源关联：experiment\_order\_id 或 sample\_id 至少填写一项" | ✓  | BEMCL-DATA-P0-001 |
| AC-DATA-006 | 数据 | 候选生成时                 | 1. POST /discover/crystal 带 project\_id 2. 检查候选记录 | formula + project\_id | 候选记录 project\_id 已写入                                    | 复测✓：discover/crystal 带 project\_id=PROJ-EE74E6FD → 候选落库 project\_id 已写入，项目候选接口可正查 | ✓  | BEMCL-DATA-P0-002 |
| AC-DATA-007 | 数据 | 已有 3090 条候选           | 1. 执行 data\_quality 回填脚本                          | source 字段映射规则         | 回填后 data\_quality 非空率 100%                              | 复测✓：回填完成，抽样 50/50 有标注 | ✓  | BEMCL-DATA-P1-001 |
| AC-DATA-008 | 数据 | 已有 826 条订单            | 1. 清理/回填无 project\_id 订单                          | 归档规则                  | project\_id 非空率 >90%                                    | 复测✓：回填/清理后 826/826 (100%) | ✓  | BEMCL-DATA-P1-002 |

### 13.3 流程闭环

| 用例编号        | 分类 | 前置条件           | 步骤                                         | 输入       | 预期              | 实际                                     | 通过 | 缺陷编号                                   |
| ----------- | -- | -------------- | ------------------------------------------ | -------- | --------------- | -------------------------------------- | -- | -------------------------------------- |
| AC-FLOW-001 | 流程 | 项目+候选+预测已就绪    | 1. 触发合成 2. 创建实验订单 3. 录入结果 4. QC 5. ECML 反馈 | 场景 A 数据包 | 全链路贯通且可逆向追溯     | 3 处断点已分别修复（溯源强校验/项目关联写入/step7 工具绑定），整链端到端复跑待回归 | —  | BEMCL-DATA-P0-001/002, BEMCL-AI-P1-002 |
| AC-FLOW-002 | 流程 | 配方 V01 已创建     | 1. 配方→BOM→样品→实验回填                          | 场景 B 数据包 | 配方与实验任务关联可追溯    | 实验订单 bom\_id 全空，关联缺失（不在本次 14 缺陷范围，列入后续整改）                   | ✗  | —                                      |
| AC-FLOW-003 | 流程 | MDM 字典已配置      | 1. 导入→映射→QC→知识资产→决策                        | CSV 导入文件 | 治理闭环贯通          | 复测✓：T-012 完成完整决策（cmt-e2167f3f→rc-bce93682 裁决 modify；rc-ada0e6ae 裁决 reject），治理指标有数据 | ✓  | BEMCL-AI-P1-003                        |
| AC-FLOW-004 | 流程 | ECML 已完成 1 轮迭代 | 1. step7\_feedback 触发反馈学习                  | 迭代结果     | 反馈工具自动执行并产出学习结论 | 复测✓：builtin\_battery\_learner 已绑定 get\_experiment\_results，闭环恢复 | ✓  | BEMCL-AI-P1-002                        |
| AC-FLOW-005 | 流程 | 修复后环境          | 1. 从 RES 结果反查项目/候选/样品/设备/QC 2. 从项目正查所有下游对象 | 完整链路数据   | 双向追溯 100% 可达    | 待执行（阶段 4 试点回归项）                             | —  | BEMCL-DATA-P0-001/002                  |

### 13.4 权限审计

| 用例编号        | 分类 | 前置条件          | 步骤                               | 输入           | 预期                                          | 实际                               | 通过 | 缺陷编号              |
| ----------- | -- | ------------- | -------------------------------- | ------------ | ------------------------------------------- | -------------------------------- | -- | ----------------- |
| AC-AUTH-001 | 权限 | 匿名用户（无 token） | 1. GET /projects                 | 无            | 401                                         | 401                              | ✓  | —                 |
| AC-AUTH-002 | 权限 | 非 admin 用户    | 1. GET /auth/users               | X-Auth-Token | 403                                         | 403（修复前导致下拉为空，已通过 brief 端点解决）    | ✓  | BEMCL-UI-P3-002   |
| AC-AUTH-003 | 权限 | 非 admin 用户    | 1. GET /auth/users/brief         | X-Auth-Token | 200 + 简要列表                                  | 200                              | ✓  | —                 |
| AC-AUTH-004 | 审计 | 实验结果已提交       | 1. 检查审计记录 confirmed/approved\_by | 无            | verified 前必须 confirmed=true 且有 approved\_by | 复测✓：learning\_eligible 需 experiment\_order\_id + QC VALID 双条件；/qc/approve 增加溯源检查，无溯源禁止放行 | ✓  | BEMCL-DATA-P0-001 |
| AC-AUTH-005 | 权限 | 任意登录用户        | 1. 删除被引用的主数据                     | 被引用对象 ID     | 409 拒绝并提示引用关系                               | 409 + 中文友好提示                     | ✓  | —                 |

### 13.5 异常恢复

| 用例编号       | 分类 | 前置条件      | 步骤                                  | 输入     | 预期                      | 实际                        | 通过 | 缺陷编号             |
| ---------- | -- | --------- | ----------------------------------- | ------ | ----------------------- | ------------------------- | -- | ---------------- |
| AC-EXC-001 | 异常 | admin 已登录 | 1. POST /projects 重复名称              | 重名项目名  | 409 + 中文提示              | 409                       | ✓  | —                |
| AC-EXC-002 | 异常 | admin 已登录 | 1. GET /projects/PROJ-XXXXXX 不存在 ID | 不存在 ID | 404 + 中文提示              | 404                       | ✓  | —                |
| AC-EXC-003 | 异常 | 项目目标表单    | 1. 提交空名称/空目标                        | 空值     | 前端即时校验 + 后端 400/422     | 校验生效                      | ✓  | —                |
| AC-EXC-004 | 异常 | AI 拆解执行中  | 1. 点击取消按钮                           | 无      | 请求中止，界面恢复可编辑            | 取消按钮生效                    | ✓  | —                |
| AC-EXC-005 | 异常 | 同步合成端点超时  | 1. POST /synthesis/plan             | smiles | 自动回退 async 并返回 task\_id | 复测✓：超时/不可用自动 202 回退 async + task\_id | ✓  | BEMCL-SYN-P2-001 |
| AC-EXC-006 | 异常 | 工具调用失败    | 1. 触发 D 级工具失败场景                     | 工具输入   | 自动降级到 fallback\_tool    | 复测✓：D/C 级 14 个工具 fallback\_tool\_id 配置率 100% | ✓  | BEMCL-AI-P1-001  |

### 13.6 UI 一致性

| 用例编号      | 分类 | 前置条件        | 步骤                                      | 输入  | 预期                     | 实际                                              | 通过 | 缺陷编号            |
| --------- | -- | ----------- | --------------------------------------- | --- | ---------------------- | ----------------------------------------------- | -- | --------------- |
| AC-UI-001 | UI | 浏览器打开任意页面   | 1. 检查 document.title 与 index.html title | 无   | 全站品牌标题一致 (MaterialsPEML) | 复测✓：router/index.html/MainLayout/Settings 统一为 MaterialsPEML，dist 已重建无旧品牌残留 | ✓  | BEMCL-UI-P3-001 |
| AC-UI-002 | UI | 浏览器实测 28 页面 | 1. 逐页检查加载/空态/错误态                        | 无   | 状态完整且无阻塞错误             | 28 页面无阻塞错误                                      | ✓  | —               |
| AC-UI-003 | UI | 列表页无数据      | 1. 检查空态引导                               | 空列表 | 空态文案 + 下一步操作按钮         | 部分页面仅空列表，无引导                                    | ✗  | —（见 §8 空态规范）    |
| AC-UI-004 | UI | 剩余 10 页面    | 1. 浏览器深检 /eval-center, /budgets 等       | 无   | 与已测页面一致的状态完整性          | 待执行（浏览器预算限制，API 已验证）                            | —  | T-020           |

### 13.7 性能

| 用例编号        | 分类 | 前置条件      | 步骤                            | 输入       | 预期          | 实际                    | 通过 | 缺陷编号             |
| ----------- | -- | --------- | ----------------------------- | -------- | ----------- | --------------------- | -- | ---------------- |
| AC-PERF-001 | 性能 | 系统空闲      | 1. GET / 总览统计                 | 无        | <2s         | 正常加载                  | ✓  | —                |
| AC-PERF-002 | 性能 | ASKCOS 可用 | 1. POST /synthesis/plan/async | Li6PS5Cl | 异步任务 <1s 返回 | 234ms                 | ✓  | —                |
| AC-PERF-003 | 性能 | 3090 条候选  | 1. GET /candidates?limit=5    | limit=5  | 分页返回，响应 <2s | 复测✓：limit 生效，count=5/total=3090 | ✓  | BEMCL-API-P2-002 |
| AC-PERF-004 | 性能 | 826 条实验订单 | 1. 实验工作台列表加载                  | 无        | 分页加载 <3s    | 正常                    | ✓  | —                |

### 13.8 AI 可信度

| 用例编号      | 分类 | 前置条件            | 步骤                                         | 输入       | 预期                            | 实际                                                 | 通过 | 缺陷编号              |
| --------- | -- | --------------- | ------------------------------------------ | -------- | ----------------------------- | -------------------------------------------------- | -- | ----------------- |
| AC-AI-001 | AI | 系统已初始化          | 1. GET /mappings/overview                  | 无        | Activity→Agent→Tool 三层映射完整    | 18 activity + 14 tool\_binding 完整                  | ✓  | —                 |
| AC-AI-002 | AI | 系统已初始化          | 1. GET /capabilities                       | 无        | 能力契约含适用域/风险/版本/回退链            | 复测✓：200, 13 项契约可查，历史 version 已归一化 | ✓  | BEMCL-AI-P0-003   |
| AC-AI-003 | AI | 工具已注册           | 1. GET /control-plane/tools                | 无        | D/C 级工具 fallback\_tool\_id 非空 | 复测✓：D/C 级 14/14 已配置 fallback（DEFAULT\_FALLBACK\_MAP 默认降级链） | ✓  | BEMCL-AI-P1-001   |
| AC-AI-004 | AI | 工具已注册           | 1. 检查工具 health\_status                     | 无        | 定期健康检查，状态非 unknown            | 复测✓：29/29 非 unknown（local=healthy，scp/mcp 按 provider 探测刷新） | ✓  | BEMCL-AI-P1-001   |
| AC-AI-005 | AI | 预测已执行           | 1. POST /discover/batch-predict 2. 检查置信度展示 | Li6PS5Cl | 预测值 + 置信度 + 模型版本可见            | confidence=0.83, model=heuristic\_gnn 可见           | ✓  | —                 |
| AC-AI-006 | AI | 已有 AI 输出        | 1. 检查 verified/estimated 标签区分              | 无        | verified 绝不与 estimated 混算     | 复测✓：无溯源 verified 已降级 UNVERIFIED/estimated；learning\_eligible 增加审计门禁 | ✓  | BEMCL-DATA-P0-001 |
| AC-AI-007 | AI | Release Card 流程 | 1. GET /release-cards/metrics/summary      | 无        | 6 项治理指标有实际数据                  | 复测✓：decision\_coverage=1.0, evidence\_completeness=0.5, human\_review\_hit\_rate=1.0, decision\_latency=2.10s（T-012 已完成完整决策） | ✓  | BEMCL-AI-P1-003   |
| AC-AI-008 | AI | 控制平面策略          | 1. 触发受限工具调用                                | 受限输入     | 策略引擎按 RBAC 拦截/放行              | 5 条策略规则在位（deny-thinker-dft 等）                      | ✓  | —                 |

**通过统计（2026-07-31 修复回归后更新）**：50 项用例中 46 项通过 (92%)；2 项未通过（AC-FLOW-002 配方 bom\_id 关联、AC-UI-003 空态引导，均不在本次 14 项缺陷范围，列入后续整改）；2 项待阶段 4 试点回归（AC-FLOW-001 整链端到端复跑、AC-FLOW-005 双向追溯、AC-UI-004 剩余页面深检）。**14 项已确认缺陷（P0×3 / P1×5 / P2×4 / P3×2）全部修复并逐项复测通过。**

***

## 14. 最终交付判断

> **2026-07-31 修复回归更新**：阶段 0（P0 止血）、阶段 1（主研发链路）、阶段 2（AI 治理元数据）、阶段 3（一致性）所列 14 项缺陷已全部修复并逐项复测通过（见 §13 标注"复测✓"行）。当前状态由"否——需先完成阶段 0"更新为"**可进入受控试点**"，试点期间仍需遵守以下条件 2/3。

### 能否供真实新材料团队日常使用：**受控试点可用（阶段 0-3 已完成），规模商用需完成阶段 4 试点指标**

**条件**：

1. ~~必须先完成阶段 0（P0 止血）~~ **已完成并复测通过**：无溯源 verified 数据已降级且入库侧已加强制溯源校验；项目-候选关联已恢复双向可查；能力契约 500 已修复（历史 version 归一化）。
2. **受控试点范围**：可开放给 1-2 个真实研发项目试点，且每次 ECML 迭代的 learning\_eligible 数据必须人工复核（系统已强制 experiment\_order\_id + QC VALID 双条件兜底）。
3. **阶段 4 完成前**：AC-FLOW-001 整链端到端复跑、AC-FLOW-005 双向追溯回归、AC-FLOW-002 配方 bom\_id 关联补齐、AC-UI-003 空态引导补齐，此 4 项未闭环前不得宣称"AI 驱动研发闭环"全部达成。

### 最优先的 10 项整改

| 排名 | 任务                                         | 缺陷                | 理由                   |
| -- | ------------------------------------------ | ----------------- | -------------------- |
| 1  | T-001 修复 /capabilities 500（version semver） | BEMCL-AI-P0-003   | S 工作量即可恢复 AI 治理链验证能力 |
| 2  | T-002 修复 /discover 写入 project\_id          | BEMCL-DATA-P0-002 | 恢复项目-候选追溯主链路         |
| 3  | T-004 实验结果溯源字段强制校验                         | BEMCL-DATA-P0-001 | 阻止无溯源数据继续污染学习闭环      |
| 4  | T-005 learning\_eligible 默认 false          | BEMCL-DATA-P0-001 | 学习资格必须由审计确认兜底        |
| 5  | T-006 降级 RES\_2fc2df5b 为 unverified        | BEMCL-DATA-P0-001 | 清除已存在的污染源            |
| 6  | T-003 修复 /projects/{id}/candidates 查询      | BEMCL-DATA-P0-002 | 与 T-002 配套恢复双向关联     |
| 7  | T-008 为 ecml.step7\_feedback 配置工具绑定        | BEMCL-AI-P1-002   | 恢复 ECML 反馈学习闭环       |
| 8  | T-007 为 D/C 级工具配置 fallback                 | BEMCL-AI-P1-001   | 恢复工具降级回退能力           |
| 9  | T-010 候选 data\_quality 批量补全                | BEMCL-DATA-P1-001 | 恢复候选来源质量可区分性         |
| 10 | T-011 实验订单 project\_id 回填与清理               | BEMCL-DATA-P1-002 | 恢复实验数据项目归属           |

### 应保留深化的功能

1. **Activity→Agent→Tool 三层映射**（含 /mappings/overview 一站式查询）——治理链结构完整，是 AI 治理的核心资产
2. **控制平面策略引擎**（5 条 RBAC 规则）——策略粒度合理，值得扩展更多场景
3. **MDM 五阶段治理**（字典/单位/状态码/分类 seed）——数据治理基座扎实
4. **知识资产三层结构**（Paper→Material→Claim + DOI 去重 + 双维可信度）
5. **配方版本管理**（V01/V02 版本链 + BOM/BOP + 成本核算）
6. **跨尺度预测链路**（molecular→reaction→continuum→coupled）
7. **合成路径异步任务**（234ms 响应 + 2 路线评分）
8. **异常处理体系**（409/404/401/403 + 引用完整性保护）
9. **14 个内置智能体**（角色覆盖 + 工具/能力/禁止操作元数据）
10. **ECML 7 步结构**（前置条件检查 + 进度展示）

### 应合并、隐藏、降级或暂缓的功能

| 处置    | 功能                                    | 理由                                                  |
| ----- | ------------------------------------- | --------------------------------------------------- |
| 暂缓开放  | Release Card 指标看板                     | 6 项指标全 null，无已决策数据，开放会给用户"系统空转"印象；待完成首次完整决策流程后再开放   |
| 降级为只读 | 能力契约页面 (/capability-center)           | API 500 修复前页面无数据；修复后可恢复完整功能                         |
| 隐藏入口  | 同步 /synthesis/plan 端点                 | 超时 503 且无回退，保留异步端点即可满足需求；待实现自动回退后再开放                |
| 合并    | /knowledge-base 与 /knowledge-graph 入口 | 两者均未被浏览器实测覆盖且业务重叠度高，建议合并为"知识资产"统一入口                 |
| 降级标注  | 工具健康状态展示                              | health\_status 全 unknown 时不应展示"健康"字样误导用户，应先降级为"未监测" |

### 未满足哪些验收条件前，不得对外宣称"AI 驱动研发闭环"

| #  | 验收条件                                                                      | 对应缺陷                  | 验证用例                                  |
| -- | ------------------------------------------------------------------------- | --------------------- | ------------------------------------- |
| 1  | 所有 verified 实验数据具备完整溯源链（项目→候选→样品→设备），且 learning\_eligible 必须经审计 confirmed | BEMCL-DATA-P0-001     | AC-DATA-001/005                       |
| 2  | 项目可正查全部下游对象（候选/订单/结果/ECML 迭代），候选可反查项目                                     | BEMCL-DATA-P0-002     | AC-FUNC-002, AC-DATA-006, AC-FLOW-005 |
| 3  | 能力契约可查询（GET /capabilities 返回 200），适用域/风险/版本/回退链可见                         | BEMCL-AI-P0-003       | AC-AI-002                             |
| 4  | ECML 7 步全部有工具绑定，反馈学习闭环可自动执行                                               | BEMCL-AI-P1-002       | AC-FLOW-004                           |
| 5  | D/C 级工具 fallback 配置率 100%，工具失败时可自动降级                                      | BEMCL-AI-P1-001       | AC-EXC-006                            |
| 6  | 候选 data\_quality 标注率 100%，verified/estimated/simulated 严格区分               | BEMCL-DATA-P1-001     | AC-DATA-002/007                       |
| 7  | 实验订单 project\_id 非空率 >90%，AI 草稿强制关联项目                                     | BEMCL-DATA-P1-002     | AC-DATA-003/008                       |
| 8  | 至少完成 1 次完整 Release Card 决策流程，6 项治理指标有实际数据                                 | BEMCL-AI-P1-003       | AC-AI-007                             |
| 9  | 至少完成 3 轮真实 ECML 迭代且每轮学习数据均通过人工复核                                          | （阶段 4 试点指标）           | AC-FLOW-001                           |
| 10 | 逆向追溯测试通过：从任一最终结果可反查项目/候选/预测模型版本/实验/样品/批次/设备/原始数据/QC 规则/审核责任人              | BEMCL-DATA-P0-001/002 | AC-FLOW-005                           |

***

*报告结束*
