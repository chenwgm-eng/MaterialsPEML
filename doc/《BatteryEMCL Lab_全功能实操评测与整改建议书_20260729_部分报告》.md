# 《BatteryEMCL Lab 全功能实操评测与整改建议书（部分报告）》

- 评审日期：2026-07-29
- 评审环境：本地开发环境
- 前端地址：http://localhost:5173/
- 后端地址：http://localhost:8000/
- 前端版本：基于当前工作目录代码（构建通过）
- 后端版本：基于当前工作目录代码（uvicorn 启动成功）
- 评审账号/角色：本地开发模式，userRole 默认 viewer（localStorage）
- 覆盖范围：全导航可访问性普查（36 个二级菜单 URL 直接访问）+ 关键问题修复验证
- 报告版本：v0.1 部分报告

---

## 1. 执行摘要

### 1.1 当前成熟度判断

**判断：内部试用 / 受控试点**

证据：
- 36 个二级菜单页面均可直接通过 URL 访问并渲染基础结构。
- 在普查过程中发现并修复了 2 个真实前端缺陷：
  1. `/control-plane` 页面因 `ROLE_RANK` 未在路由守卫中导入而导致路由导航错误、页面无法渲染。
  2. `/value-report` 页面因 `a-select-option` 的 `:key` 可能为 `null/undefined` 而触发 "Cannot read properties of null (reading 'key')" 运行时错误。
- 未发现页面完全白屏或服务端 500 导致无法进入的情况。
- 但大量页面（如 workbench、prediction、synthesis、formula-design、ecml、experiments、samples、research、orchestration、agents、tools、topology、mappings、capability-center、eval-center 等）直接访问时仅显示默认标题 "MaterialsPEML"，业务内容区域未呈现有效数据或空态引导，无法确认其业务功能是否真正可用。

### 1.2 最重要的风险

| 优先级 | 风险 |
|---|---|
| P1 | 多个核心业务页面可能为空壳或缺乏空态引导，用户进入后不知下一步如何操作。 |
| P1 | 权限路由守卫依赖 localStorage 的 `userRole`，存在前端绕过风险，且 admin 专属页面在 viewer 角色下可能只是空白而非明确无权限提示。 |
| P2 | 页面标题不统一，部分页面标题为 "MaterialsPEML" 而非具体业务标题，影响多标签页识别与专业感。 |

### 1.3 整改策略

建议先完成“全导航可访问性 + 空态/错误态”治理，再进入核心业务链路的端到端深度测试。

---

## 2. 测试方法、环境与局限

### 2.1 证据分级规则

- **[已实操验证]**：通过真实浏览器访问页面并观察到结果。
- **[高概率推断]**：基于代码结构或页面渲染一致性推断，但未执行完整业务操作。
- **[待确认]**：受工具预算、权限或时间限制，未执行验证。

### 2.2 环境限制

- 浏览器操作子代理单次仅有 60 步预算，无法在一次会话中完成 36 个页面的每个可点击对象深度操作。
- 当前为本地开发环境，外部模型/SCP 服务可用性未知。
- 当前账号角色默认为 viewer，部分 admin 页面可能无法看到完整功能。

### 2.3 未验证清单

- 项目创建、任务拆解、候选生成、性质预测、合成路径规划、配方工艺、实验任务流转、QC 判定、Release Card、ECML 闭环等核心业务链路。
- AI/Agent/工具调用、Capability Center、Control Plane、Committee、Value Realization 等专项路径。
- 权限边界、越权访问、401/403 提示。
- 异常与韧性（校验、幂等、并发、超时、失败恢复）。

---

## 3. 实操覆盖清单

| 一级菜单 | 二级菜单 | URL | 页面标题 | 是否成功渲染 | 控制台 JS Error | 证据状态 |
|---|---|---|---|---|---|---|
| 我的研发 | 首页 | / | 总览 - BatteryPEML | 是 | 无 | 已实操验证 |
| 我的研发 | 我的待办 | /my-tasks | 我的待办 - BatteryPEML | 是 | 无 | 已实操验证 |
| 项目空间 | 项目管理 | /projects | 项目管理 - BatteryPEML | 是 | 无 | 已实操验证 |
| 项目空间 | 项目新建 | /projects/new | 项目新建 - BatteryPEML | 是 | 无 | 已实操验证 |
| 项目空间 | 候选材料设计 | /workbench | MaterialsPEML | 是 | 无 | 已实操验证 |
| 项目空间 | 性质预测 | /prediction | MaterialsPEML | 是 | 无 | 已实操验证 |
| 项目空间 | 合成路径 | /synthesis | MaterialsPEML | 是 | 无 | 已实操验证 |
| 项目空间 | 配方与工艺 | /formula-design | MaterialsPEML | 是 | 无 | 已实操验证 |
| 项目空间 | 实验闭环迭代 | /ecml | MaterialsPEML | 是 | 无 | 已实操验证 |
| 项目空间 | 迭代历史 | /ecml/runs | 迭代历史 - BatteryPEML | 是 | 无 | 已实操验证 |
| 项目空间 | 性能寿命预测 | /battery-life | 性能寿命预测 - BatteryPEML | 是 | 无 | 已实操验证 |
| 实验与数据 | 实验工作台 | /experiment-workbench | MaterialsPEML | 是 | 无 | 已实操验证 |
| 实验与数据 | 实验数据 | /experiments | MaterialsPEML | 是 | 无 | 已实操验证 |
| 实验与数据 | 样品与批次 | /samples | MaterialsPEML | 是 | 无 | 已实操验证 |
| 实验与数据 | 设备与校准 | /equipment | 设备台账 - BatteryPEML | 是 | 无 | 已实操验证 |
| 实验与数据 | 数据接入 | /data-ingest | 数据接入 - BatteryPEML | 是 | 无 | 已实操验证 |
| 实验与数据 | 数据质量 | /data-quality | MaterialsPEML | 是 | 无 | 已实操验证 |
| 知识资产 | 技术情报 | /technology-intelligence | MaterialsPEML | 是 | 无 | 已实操验证 |
| 知识资产 | 知识图谱 | /knowledge-graph | MaterialsPEML | 是 | 无 | 已实操验证 |
| 知识资产 | 物料规格库 | /materials | MaterialsPEML | 是 | 无 | 已实操验证 |
| 知识资产 | 属性字典 | /properties | 属性字典 - BatteryPEML | 是 | 无 | 已实操验证 |
| 知识资产 | 主数据治理 | /mdm | 主数据治理 - BatteryPEML | 是 | 无 | 已实操验证 |
| AI 与编排 | 研发工作台 | /research | MaterialsPEML | 是 | 无 | 已实操验证 |
| AI 与编排 | 智能编排 | /orchestration | MaterialsPEML | 是 | 无 | 已实操验证 |
| AI 与编排 | 智能体管理 | /agents | 智能体管理 - BatteryPEML | 是 | 无 | 已实操验证 |
| AI 与编排 | 工具与连接器 | /tools | 工具与连接器 - BatteryPEML | 是 | 无 | 已实操验证 |
| AI 与编排 | 调用关系 | /topology | MaterialsPEML | 是 | 无 | 已实操验证 |
| AI 与编排 | 映射控制台 | /mappings | MaterialsPEML | 是 | 无 | 已实操验证 |
| AI 与编排 | 能力契约 | /capability-center | MaterialsPEML | 是 | 无 | 已实操验证 |
| AI 与编排 | 评估中心 | /eval-center | MaterialsPEML | 是 | 无 | 已实操验证 |
| 管理 | 管理看板 | /dashboard | MaterialsPEML | 是 | 无 | 已实操验证 |
| 管理 | 控制平面 | /control-plane | 控制平面 - BatteryPEML | 是 | 无 | 已实操验证（已修复） |
| 管理 | 预算看板 | /budgets | 预算看板 - BatteryPEML | 是 | 无 | 已实操验证 |
| 管理 | 收益账单 | /value-report | 收益账单 - BatteryPEML | 是 | 无 | 已实操验证（已修复） |
| 管理 | 用户与角色 | /users | 用户管理 - BatteryPEML | 是 | 无 | 已实操验证 |
| 管理 | 系统设置 | /settings | 系统设置 - BatteryPEML | 是 | 无 | 已实操验证 |

---

## 4. 已发现并修复的问题

### BEMCL-ROUTER-P1-001：/control-plane 页面因 ROLE_RANK 未定义崩溃

- **证据状态**：已实操验证
- **优先级**：P1
- **问题类型**：功能
- **位置**：路由守卫 /control-plane、/capability-center、/mappings 等 requiredRole 页面
- **复现步骤**：
  1. 访问 http://localhost:5173/control-plane
  2. 页面标题异常，控制台报 `ReferenceError: ROLE_RANK is not defined`
- **根因**：`frontend/src/router/index.js` 路由守卫使用 `ROLE_RANK` 但未从 `@/constants/roles` 导入。
- **已修复**：在 `router/index.js` 顶部添加 `import { ROLE_RANK } from '@/constants/roles'`。
- **验证**：强制刷新后 `/control-plane` 页面正常渲染，无 ROLE_RANK 错误。

### BEMCL-UIREPORT-P1-002：/value-report 页面 key 为 null 运行时错误

- **证据状态**：已实操验证
- **优先级**：P1
- **问题类型**：功能
- **位置**：收益账单页面项目选择下拉
- **复现步骤**：
  1. 访问 http://localhost:5173/value-report
  2. 控制台报 `Cannot read properties of null (reading 'key')`，来源 DisabledButton.vue
- **根因**：`ValueReport.vue` 中 `a-select-option` 的 `:key="p.project_id"` 在 projects 列表存在 project_id 为空的项时 key 为 null/undefined。
- **已修复**：
  1. `ValueReport.vue` 中 key 改为 `:key="p.project_id || \`proj-${idx}\`"`。
  2. `DisabledButton.vue` 中对 slotData 增加 null 保护：`v-bind="slotData || {}"`。
- **验证**：强制刷新后无 JavaScript 运行时错误。

---

## 5. 后续必须执行的深度测试（待完成）

### 5.1 核心业务链路

1. **材料发现到实验闭环**：项目创建 -> 候选生成 -> 性质预测 -> 合成路径 -> 实验任务 -> 样品/批次/设备 -> 数据录入 -> QC -> ECML 迭代。
2. **配方与工艺研发闭环**：配方创建 -> BOM/BOP -> 工艺版本 -> 样品制备 -> 实验数据回填 -> 版本迭代。
3. **数据资产治理闭环**：MDM 字典 -> Data Ingest 导入 -> 统一 QC -> 知识图谱 -> Value Report。

### 5.2 专项测试

- AI/Agent 工具调用链路与可解释性
- Capability Center / Control Plane 策略与权限
- Committee / Release Card 决策流程
- 权限边界与越权访问
- 异常与韧性（超时、失败、重试、取消）

### 5.3 页面级深检

- 对每个页面的表单字段、空态、加载态、错误态、按钮状态、数据一致性进行逐页检查。

---

## 6. 当前结论与建议

### 6.1 交付判断

**当前不能对外宣称“AI 驱动研发闭环”已可日常使用。**

虽然基础页面框架可访问，但大量核心业务页面内容为空或仅显示默认标题，缺乏业务数据与空态引导。必须完成端到端链路验证后，才能评估真实可用性。

### 6.2 最优先的整改项

1. 为所有显示默认标题 "MaterialsPEML" 的页面补充业务标题、空态引导和加载态。
2. 完成核心业务链路（项目 -> 候选 -> 预测 -> 合成 -> 实验 -> QC -> ECML）的端到端验证。
3. 验证权限路由守卫在所有角色场景下行为正确（viewer/researcher/pm/admin）。
4. 补充 AI/Agent 调用链路的可观测性与失败降级验证。

---

*本报告为部分报告，完整深度测评需分多轮执行。建议下一轮从“项目创建 -> 候选生成 -> 性质预测”核心链路开始。*
