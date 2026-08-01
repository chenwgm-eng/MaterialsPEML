# BatteryEMCL Lab 后端质量评审报告

- 生成时间：2026-07-29 16:56:26
- 后端地址：http://localhost:8000
- API 实测调用数：124
- 测试数据包：ASSB-LPSCl-2026Q3 / PEO-LiTFSI-2026Q3

## 1. 环境基线与测试方法

- 使用 Python `requests` 顺序执行端到端调用，记录状态码、响应摘要、耗时。
- 认证方式：POST /auth/login 获取 token，后续请求携带 `X-Auth-Token`。
- 部分 AI 密集型端点设置 30-60s 超时。
- 代码审查基于 `battery_materials_agent/` 与 `alembic/versions/` 当前磁盘版本。

## 2. API 覆盖清单与实测结果

### 2.1 状态码统计

| 状态码 | 次数 |
| --- | --- |
| 200 | 113 |
| 400 | 4 |
| 401 | 1 |
| 404 | 1 |
| 409 | 2 |
| 500 | 2 |
| None | 1 |

### 2.2 按模块实测清单

| 模块 | 端点 ID | 方法 | 路径 | 描述 | 状态码 | 耗时(ms) | 结果 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| agents | AG1 | GET | `/agents` | Agent 列表 | 200 | 2055.6 | ✅ 通过 |
| agents | AG2 | GET | `/agents/llm-options` | LLM 选项 | 200 | 2064.7 | ✅ 通过 |
| agents | AG3 | GET | `/agents/health` | Agent 健康 | 200 | 2048.6 | ✅ 通过 |
| auth | A1 | POST | `/auth/login` | 管理员登录 | 200 | 2103.0 | ✅ 通过 |
| auth | A2 | GET | `/auth/me` | 获取当前登录用户 | 200 | 2046.5 | ✅ 通过 |
| auth | A3 | GET | `/auth/me` | 未登录访问 /auth/me（应 401） | 401 | 2050.4 | ✅ 负向通过 |
| auth | A4 | GET | `/auth/users` | admin 列出用户 | 200 | 2045.9 | ✅ 通过 |
| auth | A5 | GET | `/audit/logs` | admin 查看审计日志 | 200 | 2058.9 | ✅ 通过 |
| budgets | BG1 | GET | `/budgets/token-usage` | Token 使用 | 200 | 2054.3 | ✅ 通过 |
| candidates | C1 | GET | `/candidates` | 候选列表 | 200 | 2208.1 | ✅ 通过 |
| candidates | C2 | GET | `/candidates?page=1&size=10` | 候选列表分页 | 200 | 2278.1 | ✅ 通过 |
| candidates | C3 | GET | `/candidates/NONEXISTENT` | 候选详情（使用占位 ID，应 404） | 404 | 2052.1 | ✅ 负向通过 |
| candidates | C7 | GET | `/candidates?q=Li6PS5Cl%3Cscript%3E` | 候选特殊字符搜索 | 200 | 2178.9 | ✅ 通过 |
| capability-center | CAP1 | GET | `/capabilities` | 能力契约列表 | 200 | 2074.6 | ✅ 通过 |
| capability-center | CAP2 | GET | `/capabilities/synthesis_planning_askcos_v1/fallback-chain` | 能力契约回退链 | 200 | 2046.5 | ✅ 通过 |
| config | CF1 | GET | `/config` | 系统配置 | 200 | 2216.6 | ✅ 通过 |
| control-plane | CP1 | GET | `/control-plane/runs` | 控制面运行列表 | 200 | 2040.9 | ✅ 通过 |
| control-plane | CP2 | GET | `/control-plane/budgets` | 预算列表 | 200 | 2058.8 | ✅ 通过 |
| control-plane | CP3 | GET | `/control-plane/tools` | 控制面工具列表 | 200 | 2038.1 | ✅ 通过 |
| control-plane | CP4 | GET | `/control-plane/providers` | Provider 列表 | 200 | 2045.7 | ✅ 通过 |
| control-plane | CP5 | GET | `/control-plane/policies` | 策略列表 | 200 | 2048.4 | ✅ 通过 |
| dashboard | DB1 | GET | `/dashboard/overview` | 概览仪表盘 | 200 | 2170.4 | ✅ 通过 |
| dashboard | DB2 | GET | `/dashboard/cost` | 成本仪表盘 | 500 | 2086.4 | ❌ 失败 |
| dashboard | DB3 | GET | `/dashboard/resources` | 资源仪表盘 | 200 | 2041.2 | ✅ 通过 |
| data-ingest | DI1 | GET | `/ingest/field-dict/project` | 导入字段字典 | 200 | 2043.3 | ✅ 通过 |
| data-ingest | DI2 | POST | `/ingest/preview` | 导入预览 | 200 | 2159.6 | ✅ 通过 |
| data-ingest | DI3 | POST | `/ingest/commit` | 导入提交 | 200 | 2086.0 | ✅ 通过 |
| data-ingest | DI3-DUP | POST | `/ingest/commit` | 重复导入幂等（应 duplicated=true） | 200 | 2048.8 | ✅ 通过 |
| data-ingest | DI4 | GET | `/ingest/imports` | 导入历史 | 200 | 2085.9 | ✅ 通过 |
| data-ingest | DI5 | GET | `/ingest/imports/IMP_588086c58feb` | 导入详情 | 200 | 2036.5 | ✅ 通过 |
| discover | D1 | POST | `/discover` | ECML 闭环发现（1轮） | 200 | 15767.9 | ✅ 通过 |
| discover | D2 | POST | `/discover/crystal` | 晶体候选发现 | 200 | 3652.0 | ✅ 通过 |
| discover | D3 | POST | `/discover/polymer` | 聚合物候选发现 | 200 | 12222.3 | ✅ 通过 |
| discover | D4 | POST | `/discover/batch-predict` | 批量预测候选 | 200 | 2043.6 | ✅ 通过 |
| discover | D5 | POST | `/discover/agent-generate/async` | Agent 异步生成候选 | 200 | 2070.1 | ✅ 通过 |
| discover | D6 | GET | `/discover/agent-generate/aggen-7271c945649e/status` | 查询异步生成状态 | 200 | 2026.4 | ✅ 通过 |
| discover | D7 | POST | `/discover/generate` | 生成候选 | 200 | 2061.7 | ✅ 通过 |
| equipment | EQ1 | POST | `/equipment` | 创建设备 | 200 | 2061.2 | ✅ 通过 |
| equipment | EQ2 | GET | `/equipment/EQUIP-F83DF7` | 设备详情 | 200 | 2043.5 | ✅ 通过 |
| equipment | EQ3 | PUT | `/equipment/EQUIP-F83DF7` | 更新设备状态 | 200 | 2038.2 | ✅ 通过 |
| equipment | EQ4 | GET | `/equipment` | 设备列表 | 200 | 2038.9 | ✅ 通过 |
| eval-center | EV1 | GET | `/evals/runs` | 评测运行列表 | 200 | 2029.7 | ✅ 通过 |
| experiments | E1 | POST | `/experiments/orders` | 创建实验任务单 | 200 | 2166.6 | ✅ 通过 |
| experiments | E1-DUP | POST | `/experiments/orders` | 重复提交实验任务单（应幂等） | 200 | 2047.2 | ✅ 通过 |
| experiments | E1-BAD | POST | `/experiments/orders` | 实验单缺少 project_id（应 400） | 400 | 2067.2 | ✅ 负向通过 |
| experiments | E2 | GET | `/experiments/orders` | 实验任务单列表 | 200 | 2166.2 | ✅ 通过 |
| experiments | E3 | GET | `/experiments/orders/EXP_be45d2cd` | 实验单详情 | 200 | 2064.2 | ✅ 通过 |
| experiments | E4 | GET | `/experiments/orders/EXP_be45d2cd/audit` | 实验单审计 | 200 | 2037.0 | ✅ 通过 |
| experiments | E5 | GET | `/experiments/analysis/EXP_be45d2cd` | 实验单分析 | 200 | 2028.1 | ✅ 通过 |
| experiments | E6 | GET | `/experiments/types` | 实验类型 | 200 | 2060.7 | ✅ 通过 |
| experiments | E7 | GET | `/experiments/results` | 实验结果列表 | 200 | 2065.3 | ✅ 通过 |
| experiments | E8 | POST | `/experiments/results/manual` | 手工录入实验结果 | 200 | 2095.5 | ✅ 通过 |
| experiments | E8-BAD | POST | `/experiments/results/manual` | 实验结果未知属性（应 400） | 400 | 2034.4 | ✅ 负向通过 |
| experiments | E9 | POST | `/experiments/deviation-check` | 实验偏差检查 | 200 | 2055.8 | ✅ 通过 |
| formulas | F1 | POST | `/formulas` | 自动生成配方草案 | 200 | 14110.3 | ✅ 通过 |
| formulas | F2 | GET | `/formulas` | 配方列表 | 200 | 2083.7 | ✅ 通过 |
| formulas | F3 | GET | `/formulas/FORM-736FC7C5` | 配方详情 | 200 | 2041.8 | ✅ 通过 |
| formulas | F4 | GET | `/formulas/FORM-736FC7C5/history` | 配方历史 | 200 | 2049.0 | ✅ 通过 |
| knowledge | K1 | POST | `/knowledge/search` | 知识搜索 | 200 | 14040.0 | ✅ 通过 |
| knowledge | K2 | POST | `/knowledge/graph` | 知识图谱查询 | 200 | 2053.3 | ✅ 通过 |
| knowledge | K3 | GET | `/knowledge/graphs` | 图谱列表 | 200 | 2067.7 | ✅ 通过 |
| knowledge | K4 | GET | `/knowledge/papers` | 论文列表 | 200 | 2061.1 | ✅ 通过 |
| knowledge | K5 | GET | `/knowledge/materials` | 知识材料列表 | 200 | 2057.0 | ✅ 通过 |
| knowledge | K6 | POST | `/knowledge/search` | 知识搜索特殊字符 | 200 | 4760.2 | ✅ 通过 |
| mdm | MDM1 | GET | `/mdm/status-codes?domain=sample` | 状态码列表 | 200 | 2061.1 | ✅ 通过 |
| mdm | MDM2 | GET | `/mdm/units` | 单位列表 | 200 | 2062.9 | ✅ 通过 |
| mdm | MDM3 | GET | `/mdm/units/S/cm` | 单位详情 | 200 | 2049.4 | ⚠️ 返回 HTML（SPA fallback） |
| mdm | MDM4 | GET | `/mdm/test-methods` | 检测方法列表 | 200 | 2078.0 | ✅ 通过 |
| mdm | MDM5 | GET | `/mdm/properties` | 属性列表 | 200 | 2059.5 | ✅ 通过 |
| mdm | MDM6 | GET | `/mdm/material-categories` | 物料分类 | 200 | 2047.7 | ✅ 通过 |
| mdm | MDM7 | GET | `/mdm/process-routes` | 工艺路线 | 200 | 2060.0 | ✅ 通过 |
| mdm | MDM8 | GET | `/mdm/sample-types` | 样品类型 | 200 | 2057.0 | ✅ 通过 |
| mdm | MDM9 | GET | `/mdm/equipment-templates` | 设备模板 | 200 | 2067.2 | ✅ 通过 |
| mdm | MDM10 | POST | `/mdm/units/convert` | 单位换算 | 200 | 2041.7 | ✅ 通过 |
| orchestration | OR1 | POST | `/orchestrate/analyze` | 编排分析 | None | None | ❌ 超时/异常 |
| orchestration | OR2 | GET | `/orchestrate/history` | 编排历史 | 200 | 2075.5 | ✅ 通过 |
| projects | P0-ANON | GET | `/projects` | 未登录访问项目列表（安全测试） | 200 | 2030.2 | ✅ 通过 |
| projects | P1 | POST | `/projects` | 创建 ASSB-LPSCl 测试项目 | 200 | 2076.5 | ✅ 通过 |
| projects | P1-DUP | POST | `/projects` | 重名项目创建测试（应 409） | 409 | 2052.7 | ✅ 负向通过 |
| projects | P1-BAD | POST | `/projects` | 项目关键字段为空/占位符（应 400） | 400 | 2021.5 | ✅ 负向通过 |
| projects | P1-DATE | POST | `/projects` | 项目结束日期早于开始日期（应 400） | 400 | 2036.5 | ✅ 负向通过 |
| projects | P2 | GET | `/projects/PROJ-8207C2DD` | 获取项目详情 | 200 | 2047.7 | ✅ 通过 |
| projects | P3 | GET | `/projects/PROJ-8207C2DD/progress` | 项目进度 | 200 | 2055.1 | ✅ 通过 |
| projects | P4 | GET | `/projects/PROJ-8207C2DD/tasks` | 项目任务列表 | 200 | 2059.4 | ✅ 通过 |
| projects | P5 | GET | `/projects/PROJ-8207C2DD/entity-graph` | 项目实体图 | 200 | 2085.9 | ✅ 通过 |
| projects | P6 | GET | `/projects/PROJ-8207C2DD/candidates` | 项目候选列表 | 200 | 2053.3 | ⚠️ 返回 HTML（SPA fallback） |
| projects | P7 | GET | `/projects/PROJ-8207C2DD/samples` | 项目样品列表 | 200 | 2038.7 | ⚠️ 返回 HTML（SPA fallback） |
| projects | P8 | GET | `/projects/PROJ-8207C2DD/results` | 项目结果列表 | 200 | 2056.4 | ⚠️ 返回 HTML（SPA fallback） |
| projects | P9 | POST | `/projects/decompose` | AI 拆解项目目标 | 200 | 9433.9 | ✅ 通过 |
| projects | P10 | POST | `/projects/PROJ-8207C2DD/tasks` | 创建项目任务 | 200 | 2064.6 | ✅ 通过 |
| projects | P11 | GET | `/projects/PROJ-8207C2DD/stage-status` | 项目阶段状态 | 200 | 2074.0 | ✅ 通过 |
| properties | PR1 | GET | `/properties/categories` | 属性分类 | 200 | 2052.5 | ✅ 通过 |
| properties | PR2 | GET | `/properties/fields` | 属性字段 | 200 | 2035.4 | ✅ 通过 |
| properties | PR3 | GET | `/properties/options` | 属性选项 | 200 | 2033.3 | ✅ 通过 |
| properties | PR4 | GET | `/properties/templates` | 属性模板 | 200 | 2036.7 | ✅ 通过 |
| qc | Q1 | GET | `/qc/pending` | 待 QC 列表 | 200 | 2066.2 | ✅ 通过 |
| qc | Q2 | POST | `/qc/check/RES_8e2c05f7` | 执行 QC 检查 | 200 | 2080.8 | ✅ 通过 |
| qc | Q3 | POST | `/qc/RES_8e2c05f7/approve` | QC 审批通过 | 200 | 2057.4 | ✅ 通过 |
| release-cards | RC1 | GET | `/release-cards/metrics/summary` | 放行卡指标 | 200 | 2129.8 | ✅ 通过 |
| release-cards | RC2 | GET | `/release-cards` | 放行卡列表 | 200 | 2045.7 | ✅ 通过 |
| release-cards | RC3 | POST | `/release-cards` | 创建放行卡 | 200 | 2069.1 | ✅ 通过 |
| release-cards | RC4 | GET | `/release-cards/rc-794ce49a` | 放行卡详情 | 200 | 2084.4 | ✅ 通过 |
| samples | SM1 | POST | `/samples` | 创建样品 | 200 | 2068.1 | ✅ 通过 |
| samples | SM1-DUP | POST | `/samples` | 重复样品号（应 409） | 409 | 2054.0 | ✅ 负向通过 |
| samples | SM2 | GET | `/samples/SMP_6629ba72` | 样品详情 | 200 | 2059.9 | ✅ 通过 |
| samples | SM3 | PUT | `/samples/SMP_6629ba72` | 编辑样品 | 200 | 2048.3 | ✅ 通过 |
| samples | SM4 | PUT | `/samples/SMP_6629ba72/transfer` | 样品状态流转 | 200 | 2054.1 | ✅ 通过 |
| samples | SM5 | GET | `/samples/SMP_6629ba72/transfers` | 样品流转记录 | 200 | 2054.4 | ✅ 通过 |
| samples | SM6 | GET | `/samples` | 样品列表 | 200 | 2049.3 | ✅ 通过 |
| settings | ST1 | GET | `/settings/model_catalog` | 模型目录 | 200 | 2052.1 | ✅ 通过 |
| synthesis | S1 | POST | `/synthesis/plan` | 合成路线规划 | 200 | 2383.2 | ✅ 通过 |
| synthesis | S2 | POST | `/synthesis/plan/multi` | 多路径合成规划 | 500 | 3022.4 | ❌ 失败 |
| synthesis | S3 | GET | `/synthesis/network/CCO` | 合成网络 | 200 | 2373.3 | ✅ 通过 |
| synthesis | S4 | GET | `/synthesis/tasks` | 合成任务列表 | 200 | 2126.0 | ✅ 通过 |
| synthesis | S5 | GET | `/synthesis/stats` | 合成统计 | 200 | 2076.3 | ✅ 通过 |
| synthesis | S6 | GET | `/synthesis/health` | 合成健康检查 | 200 | 2068.1 | ✅ 通过 |
| synthesis | S7 | POST | `/synthesis/plan/async` | 异步合成规划 | 200 | 2058.6 | ✅ 通过 |
| synthesis | S8 | GET | `/synthesis/tasks/b728b25faf71` | 查询异步合成任务 | 200 | 2052.1 | ✅ 通过 |
| tools | TL1 | GET | `/tools` | 工具列表 | 200 | 2040.8 | ✅ 通过 |
| tools | TL2 | GET | `/tools/scp-bindings` | SCP 绑定（admin） | 200 | 2047.0 | ✅ 通过 |
| tools | TL3 | GET | `/tools/skills` | Skills（admin） | 200 | 2054.2 | ✅ 通过 |
| value-report | VR1 | GET | `/value-reports/PROJ-8207C2DD` | 项目收益报告 | 200 | 2054.6 | ✅ 通过 |
| workflow | WF1 | GET | `/workflow/schema` | 工作流 schema | 200 | 2062.0 | ✅ 通过 |
| workflow | WF2 | GET | `/workflow/nodes` | 工作流节点 | 200 | 2043.2 | ✅ 通过 |

## 3. 端到端数据流验证

以项目 `ASSB-LPSCl-2026Q3` 为主线，正查与反查如下：

| 步骤 | 动作 | 正向调用 | 反查/验证 | 结果 |
| --- | --- | --- | --- | --- |
| 1 | 创建项目 | POST /projects -> PROJ-8207C2DD | GET /projects/{id} 返回项目详情 | ✅ |
| 2 | 拆解任务 | POST /projects/decompose | GET /projects/{id}/tasks 列出任务 | ✅ |
| 3 | 发现候选 | POST /discover/crystal /discover/agent-generate/async | GET /candidates 含 CAND-* | ✅ |
| 4 | 批量预测 | POST /discover/batch-predict | 返回 prediction_status / synthesis_status | ✅ |
| 5 | 合成规划 | POST /synthesis/plan | GET /synthesis/tasks/{id} 返回 route | ✅ |
| 6 | 创建实验单 | POST /experiments/orders -> EXP_be45d2cd | GET /experiments/orders/{id} | ✅ |
| 7 | 录入结果 | POST /experiments/results/manual | GET /experiments/results 含结果 | ✅ |
| 8 | QC 审批 | POST /qc/check/{rid} + /qc/{rid}/approve | QC 状态 VALID | ✅ |
| 9 | 创建样品 | POST /samples -> SMP_6629ba72 | GET /samples/{id} 溯源 | ✅ |
| 10 | PEML 闭环 | ECML 运行 ID ecml_20260729085056_38d231 | 运行状态 is_complete | ✅ |

## 4. 代码审查发现（按分类）

### 4.1 认证与权限
- token 使用 HMAC-SHA256 签名，含过期时间，支持 user_id 含点号（`rsplit('.', 2)`）。
- `require_role` 对匿名用户按 VIEWER 放行，其他角色要求登录。
- `/projects` 列表端点未显式要求角色，匿名可访问（见缺陷 BEMCL-AUTH-P3-001）。

### 4.2 状态机与事务
- 实验任务单状态迁移图完整，终态 COMPLETED/CANCELLED 不可迁出。
- 迁移事件写入 `experiment_order_status_transitions` 表。
- 读取当前状态与更新状态非同一事务，缺少行锁（见缺陷 BEMCL-STM-P2-002）。

### 4.3 数据模型与外键
- alembic 0005 将 candidate/order/sample/result/transfers 间 FK 统一加 `ON DELETE RESTRICT`。
- 但 API 层未在写入前校验引用存在性，导致 500（见 BEMCL-EXP-P1-003 / BEMCL-SMP-P1-004）。

### 4.4 输入校验与异常处理
- 项目创建校验了空值、占位符、日期顺序、重名。
- 缺少数值范围、单位白名单、target_properties 结构校验（见 BEMCL-VAL-P3-003）。
- 部分校验下沉到存储层，导致 500 而非 400（见 BEMCL-EQP-P2-001）。

### 4.5 AI/Agent 治理链
- Capability Registry 支持契约状态、风险等级、fallback 链与缓存。
- ActivityMappingStore 实现业务活动→Agent→工具三层绑定。
- 但 discover_agent_generate、/orchestrate/analyze 等端点直接调用 LLM，未走 Tool/Skill/SCP 治理（见 BEMCL-AI-P2-003）。

### 4.6 异步任务
- 多数后台任务使用 `_spawn_background` 持有强引用。
- `discover_agent_generate_async` 使用 `ensure_future`，存在 GC 风险（见 BEMCL-ASYNC-P2-004）。

### 4.7 数据质量
- QC 引擎统一在 `qc_service.py`，支持完整性、合理性、样品匹配规则。
- 但实验结果模型缺少 verified/estimated 显式标记（见 BEMCL-DATA-P2-005）。

### 4.8 性能与资源
- `db.py` 使用 SQLAlchemy QueuePool，支持 pool_size/max_overflow/pool_pre_ping。
- 项目已迁移至 PostgreSQL，SQLite WAL 约束不再适用。
- 未发现后端重试定时器未清理的明显证据。

## 5. 缺陷清单

| 缺陷编号 | 级别 | 模块 | 标题 | 证据定位 | 建议 |
| --- | --- | --- | --- | --- | --- |
| BEMCL-SYN-P1-001 | P1 | synthesis | /synthesis/plan/multi 返回 500 KeyError: 0 | 实测 S2: POST /synthesis/plan/multi 返回 500; battery_materials_agent/synthesis/synthesis_planner.py:771 plan_multiple_routes 返回 dict，但 api.py:3841 将 dict 赋给 routes，api.py:3862 用 routes[0] 索引导致 KeyError。 | 统一 API 端点与 planner 的返回格式，或在端点层适配 dict 结构。 |
| BEMCL-DASH-P1-002 | P1 | dashboard | /dashboard/cost 返回 500 TypeError: datetime 不可下标 | 实测 DB2: GET /dashboard/cost 返回 500; api.py:9391 对 o.created_at 直接切片 [:7]，但 ExperimentDataStore.list_orders 可能返回 datetime 对象。 | 在 dashboard_cost 中对 created_at 调用 _iso() 或统一转换为字符串后再切片。 |
| BEMCL-EXP-P1-003 | P1 | experiments | 创建实验任务单时未校验 candidate_id 存在性，导致 FK 违反时返回 500 | api.py:6928-6939 仅在 candidate 存在时检查 release_card；若 candidate_id 不存在，后续 save_order 因 fk_orders_candidate 抛出 IntegrityError，被包装为 500。 | 在创建 order 前显式校验 candidate_id 是否存在，不存在返回 404/400。 |
| BEMCL-SMP-P1-004 | P1 | samples | 创建样品时未校验 source_candidate_id 存在性，导致 FK 违反时返回 500 | api.py:8923-8953 未校验 source_candidate_id 是否存在于 candidates 表；store.save 因 fk_samples_candidate 抛出 IntegrityError。 | 在 create_sample 中校验 source_candidate_id 存在性，或允许空值跳过 FK。 |
| BEMCL-EQP-P2-001 | P2 | equipment | 创建设备时 category 校验在存储层抛出 ValueError，返回 500 而非 400 | api.py:8828-8850 未前置校验 category；EquipmentStore.save 中抛出 ValueError('设备分类 ... 不存在')，被包装为 500 internal_error。 | 在 API 层预先校验 category 是否存在于 MDM，不存在返回 400。 |
| BEMCL-STM-P2-002 | P2 | experiment | 实验任务单状态机更新缺少并发控制，存在竞态条件 | battery_materials_agent/experiment/experiment_controller.py:846 update_order_status 先 SELECT status 再 UPDATE，两条 SQL 不在同一连接/事务，且无 SELECT FOR UPDATE。 | 将读取与更新放入同一事务，并使用 SELECT FOR UPDATE 行锁或数据库级约束。 |
| BEMCL-AI-P2-003 | P2 | discover/orchestrate | Agent 生成/编排端点直接调用 _LLMClient，未经过 Tool/Skill/SCP 治理链 | api.py:1960 discover_agent_generate、api.py:2180 discover_agent_generate_async、api.py:5387 /orchestrate/analyze 均直接调用 _LLMClient() 或 _orchestrator.analyze_task，而非通过 Agent -> Tool/Skill/SCP。 | 将 LLM 调用封装为 Tool/Skill，通过 Agent 工具绑定和 Capability Contract 治理链执行。 |
| BEMCL-ASYNC-P2-004 | P2 | discover | discover_agent_generate_async 后台任务使用 ensure_future，未纳入统一生命周期管理 | api.py:2348 使用 _asyncio.ensure_future(_bg_run())，而非 api.py:93 _spawn_background；后台任务无强引用，可能被 GC 回收。 | 统一使用 _spawn_background 创建后台任务，确保引用与生命周期管理。 |
| BEMCL-DATA-P2-005 | P2 | data-quality | 实验结果缺少 verified/estimated 显式标记字段 | battery_materials_agent/experiment/experiment_controller.py:150 ExperimentResultRecord 仅有 source_type 和 qc_status/learning_eligible，无 verified/estimated 区分字段。 | 增加 data_quality 字段（verified/estimated）并在 QC 审批通过时更新。 |
| BEMCL-AUTH-P3-001 | P3 | auth | 匿名用户可访问 /projects 列表（全局依赖允许匿名） | 实测 P0-ANON: GET /projects 未携带 token 返回 200；api.py:101-104 全局 dependencies=[Depends(get_current_user)] 不阻断匿名请求，api.py:8146 list_projects 未显式要求角色。 | 评估是否为设计意图；如需要保护，应在 /projects 端点添加 dependencies=[Depends(require_role(UserRole.VIEWER))]。 |
| BEMCL-PROJ-P3-002 | P3 | projects | 项目子资源端点 /projects/{id}/candidates、/samples、/results 未实现 | 实测 P6/P7/P8 返回 HTML（SPA fallback index.html）；api.py 中仅注册了 /projects/{id}/progress、/tasks、/entity-graph、/stage-status，无 candidates/samples/results 子资源路由。 | 实现上述子资源路由，或在文档中明确前端应使用 /candidates、/samples、/experiments/results 并携带 project_id 过滤。 |
| BEMCL-VAL-P3-003 | P3 | projects | 项目创建对 target_properties、tasks 等字段缺少结构与单位校验 | api.py:7883-7892 仅校验 target_application、owner 非空与日期顺序；ProjectCreateRequest 中 target_properties 为 list[dict] 但未校验属性名、方向、阈值、单位结构，tasks 字段也未校验。 | 补充 target_properties 与 tasks 的结构/单位白名单校验，避免脏数据进入项目主档。 |

**缺陷统计：P0 0 个，P1 4 个，P2 5 个，P3 3 个**

## 6. 未验证/阻断项清单

| 编号 | 未验证项 | 原因 |
| --- | --- | --- |
| UV-001 | AI/预测/推荐超时、重试、降级、取消、权限不足、预算不足异常场景 | 依赖外部 LLM/SCP/ASKCOS 服务状态与预算配置，当前 demo 环境未触发相关边界。 |
| UV-002 | 异步任务取消、队列积压、锁竞争场景 | 需要构造高并发或慢速 SCP 任务才能触发，当前单客户端顺序测试未覆盖。 |
| UV-003 | 已被引用主数据的编辑/删除阻断（ON DELETE RESTRICT） | 已确认 alembic 0005 设置 RESTRICT，但未进行实际删除触发测试。 |
| UV-004 | /orchestrate/analyze 超时原因 | 实测 OR1 30s 超时，可能是 LLM 服务响应慢或死锁；需结合后端日志与 LLM 服务状态进一步定位。 |
| UV-005 | MoleculeView WebGL/GPU 清理、SvgDrawer 实例级别、AgentFlowGraph 重试定时器清理 | 属于前端运行时行为，需通过浏览器 DevTools 与组件生命周期测试验证。 |

## 7. 结论

本次评审共实测 124 个 API 调用，整体成功率较高，核心端到端数据流（项目→候选→预测→合成→实验→QC→PEML）已跑通。发现 12 项缺陷，其中 P1 4 项、P2 5 项、P3 3 项，无 P0 阻断项。主要风险集中在：FK 校验前置缺失导致 500、Agent 治理链未完全落地、异步任务生命周期不一致、数据质量标记缺失。建议优先修复 P1 缺陷，再逐步完善 P2/P3 治理与校验。
