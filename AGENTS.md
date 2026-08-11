# AGENTS.md

MaterialsPEML Lab — 电池材料 AI 研发平台（前端 Vue3 + 后端 FastAPI + PostgreSQL）。中文 UI 与注释。

## 快速开始

- **Python 必须用 `C:\Users\chenw\AppData\Local\Programs\Python\Python310\python.exe`**（系统默认 python 是 Miniconda 3.14，无项目依赖）。
- 后端：`python -m uvicorn battery_materials_agent.api:app --host 0.0.0.0 --port 8200`（工作目录 `D:\BattleFish\BatteryEMCL Lab`）。
- 前端：`npm run dev`（vite, :5173）；构建 `npm run build`（frontend 目录）。
- **改后端代码必须重启 8200 进程**（无 --reload）。前端改动 vite HMR 自动生效。
- 数据库：`postgresql+psycopg://batteryemcl:batteryemcl_dev@localhost:5433/batteryemcl`（psql 不在 PATH，用 Python/SQLAlchemy 脚本查库；PowerShell 内联 Python 引号易坏，写临时脚本到 `C:\Users\chenw\AppData\Local\Temp\opencode\` 执行）。

## 架构地图

- `battery_materials_agent/api.py`：单体 FastAPI（1.6 万行，全部路由在此，含 SPA fallback 与中间件）。
- `battery_materials_agent/agent.py`：`BatteryMaterialsAgent` 门面（MCP 工具 handler 注册处，`_register_tool_handlers`）。
- `battery_materials_agent/experiment/`：candidate / process_scheme / equipment / experiment_controller 存储层（SQLAlchemy + JSONB）。
- `battery_materials_agent/generation/`：crystal/polymer 候选生成器（polymer 含 `_generate_engineering_plastics` 工程塑料模式）。
- `battery_materials_agent/hybrid/`：研发流水线（orchestrator/stage_executor/pipeline）。
- `frontend/src/views/`、`frontend/src/components/`：页面与组件；`src/styles/global.css` 为全局设计 token（v4.0 深蓝 2B：primary `#1d4ed8`，sidebar `#0f172a`）。
- `alembic/versions/`：数据库迁移；`tests/unit/`：pytest。

## 开发陷阱（容易踩）

- **ant-design-vue 4**：`@row-click` 已移除，行点击必须用 `:custom-row` 返回 `{ onClick }`；折叠面板默认收起用 `default-active-key`（`:active-key` 受控会锁死）；图标名必须是 `@ant-design/icons-vue` 真实导出（如 `CpuOutlined` 不存在）。
- **vite proxy 不能 rewrite**：`/api` 原样转发到 8200，由后端 `rewrite_api_prefix_middleware` 标记 `is_api_request` 并重写；若 proxy 剥掉 `/api`，`/ecml/runs` 等与 SPA 路由同名的 API 会返回 index.html。
- **PostgreSQL FK 空串**：外键列空字符串报 `ForeignKeyViolation`，必须 `value or None` 转 NULL（candidate.task_id、equipment.category、order.project_id、user.last_login 均如此）。
- **`candidate_store.save()` 默认 content_hash 去重会短路丢弃 data 更新**——回写候选字段必须 `save(record, dedup=False)`（放行卡审批回写曾因此失效）。
- **候选状态机**（candidate_store.py `CANDIDATE_ALLOWED_TRANSITIONS`）：`screening→feasible→process_planning→process_confirmed→ready_for_experiment`（终态，无后继）；`rejected` 为终态；`feasible/process_planning/process_confirmed` 可→`rejected`。前端按钮必须按候选状态门控，否则触发 409。
- **工具名 ≠ 语义别名**：`CapabilityRouter.resolve()` 按 alias（如 `dft_verification`），编排 executor 持有 MCP 工具名（`verify_dft`）——必须经 `tool_to_alias()` 反向映射，否则契约门禁误拒绝。
- **SCP 健康探测**：MCP 端点只收 POST，GET 探测必然 4xx 误判 degraded；SCP 类用 `list_tools`（POST tools/list）探测，LLM 类用 `GET /models`，REST 类才用 GET endpoint。
- **回退必须透明**：合成路线带 `source`（askcos/internlm/local_template），深化能力来源记录 `evidence_refs`（SCP failed→local success 明细），UI 展示来源徽标；每次深化重置 evidence_refs。
- **领域包**：`industrialization.domain_packs`（battery 默认 / kingfa 改性塑料）DB 持久化，系统设置页切换，`/config?domain_key=` 读取；材料体系/属性随领域包变化。
- **放行卡门禁**：候选 `data.release_card_required` 且未 `release_card_approved` 时阻断下单；无卡时自动补建待审批卡（防死锁），审批 agree 回写候选（dedup=False）。
- **综合评分补算**：历史候选 `multi_objective_score=0` 但属性齐全时，`/candidates`、`/tasks/{id}/candidates`、`/process-engineer/workbench` 用 `_backfill_multi_objective_scores` 按生成器方法补算。
- **领域包（v4.1 起全系统严格对照改性塑料）**：当前默认领域 = 改性塑料（kingfa）。领域相关默认值已从电池切换为高分子：实验模板（`_EXPERIMENT_TYPE_TEMPLATES`：tensile/impact/flexural/hdt/mfi/flame_retardancy/density…）、`ECML_TARGET_KEYS` 与 `EXPERIMENTAL_KEYS`（拉伸/弯曲/冲击/HDT/MFI/热稳定/断裂伸长/Tg）、评分补算 `_SCORE_PROPS`（4 个 maximize 力学属性）、知识库关键词（`knowledge/ingestion.py` MATERIAL_PATTERNS/PROPERTY_KEYWORDS）、生成器与 FormulaAgent 的 LLM 提示词。MDM 属性/样品类型/物料/设备已含塑料体系（PP/PA6/PC/ABS/PLA/PBAT + 玻纤/碳纤/阻燃剂 + 万能试验机/挤出机等）。`MDM 属性与物料分类有 FK（mdm.units/classifications）`——新增属性单位或物料分类须先入表；电池历史数据保留未删（防 FK 断裂）。

## 测试

- 后端：`python -m pytest tests/unit/test_two_layer_workflow.py tests/unit/test_process_deepening_service.py -q`（连真实 PostgreSQL）。Fake 测试夹具需实现 `plan_multiple_routes`（晶体走化学式分支）。
- 前端 E2E：`frontend/tests/*.mjs`（Playwright，需要 5173+8200 双活）。登录 admin/admin123（登录页为 `/login` 独立路由，非 modal）。`deep-audit.mjs` 逐页按钮巡检、`modal-audit.mjs` 弹窗巡检、`danger-audit.mjs` 危险按钮——改菜单/页面后跑这些回归。
- 巡检脚本会断言菜单项，删除菜单需同步更新脚本或接受失败。

## 约定

- 中文 UI 文案与代码注释；空态文案用 `MESSAGES`（glossary.js），不要硬编码。
- 变更遵循根目录 `CLAUDE.md`（Think Before Coding / Simplicity First / Surgical Changes / Goal-Driven Execution）。
- 已删除：研发 Copilot（AiAssistantDrawer/stores/ai.js/api/ai.js）、二级菜单「迭代历史」(/ecml/runs，路由保留可直达)。
