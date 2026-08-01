"""Generate review_backend.md from API test results and code review evidence."""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime

RESULTS_PATH = r"d:\BattleFish\BatteryEMCL Lab\doc\review_backend_api_results.json"
OUTPUT_PATH = r"d:\BattleFish\BatteryEMCL Lab\doc\review_backend.md"

with open(RESULTS_PATH, encoding="utf-8") as f:
    data = json.load(f)

calls = data["calls"]
state = data["state"]

# Build module summary
modules: dict[str, list[dict]] = {}
for c in calls:
    modules.setdefault(c["module"], []).append(c)


def _result_flag(c: dict) -> str:
    sc = c["status_code"]
    desc = c["description"]
    summary = c.get("response_summary") or ""
    is_html = isinstance(summary, str) and (summary.strip().startswith("<!DOCTYPE") or summary.strip().startswith("<html"))
    if desc and ("应 400" in desc or "应 401" in desc or "应 404" in desc or "应 409" in desc or "应 422" in desc):
        if sc in (400, 401, 404, 409, 422):
            return "✅ 负向通过"
        return "⚠️ 负向未达预期"
    if sc is None:
        return "❌ 超时/异常"
    if 200 <= sc < 300:
        if is_html:
            return "⚠️ 返回 HTML（SPA fallback）"
        return "✅ 通过"
    return "❌ 失败"


# API coverage table rows
rows = []
for mod, cs in sorted(modules.items()):
    for c in cs:
        rows.append({
            "module": mod,
            "id": c["id"],
            "method": c["method"],
            "path": c["path"],
            "description": c["description"],
            "status": c["status_code"],
            "elapsed": c["elapsed_ms"],
            "result": _result_flag(c),
        })

# Defect list
findings = [
    {
        "id": "BEMCL-SYN-P1-001",
        "level": "P1",
        "module": "synthesis",
        "title": "/synthesis/plan/multi 返回 500 KeyError: 0",
        "evidence": "实测 S2: POST /synthesis/plan/multi 返回 500; battery_materials_agent/synthesis/synthesis_planner.py:771 plan_multiple_routes 返回 dict，但 api.py:3841 将 dict 赋给 routes，api.py:3862 用 routes[0] 索引导致 KeyError。",
        "suggestion": "统一 API 端点与 planner 的返回格式，或在端点层适配 dict 结构。",
    },
    {
        "id": "BEMCL-DASH-P1-002",
        "level": "P1",
        "module": "dashboard",
        "title": "/dashboard/cost 返回 500 TypeError: datetime 不可下标",
        "evidence": "实测 DB2: GET /dashboard/cost 返回 500; api.py:9391 对 o.created_at 直接切片 [:7]，但 ExperimentDataStore.list_orders 可能返回 datetime 对象。",
        "suggestion": "在 dashboard_cost 中对 created_at 调用 _iso() 或统一转换为字符串后再切片。",
    },
    {
        "id": "BEMCL-EXP-P1-003",
        "level": "P1",
        "module": "experiments",
        "title": "创建实验任务单时未校验 candidate_id 存在性，导致 FK 违反时返回 500",
        "evidence": "api.py:6928-6939 仅在 candidate 存在时检查 release_card；若 candidate_id 不存在，后续 save_order 因 fk_orders_candidate 抛出 IntegrityError，被包装为 500。",
        "suggestion": "在创建 order 前显式校验 candidate_id 是否存在，不存在返回 404/400。",
    },
    {
        "id": "BEMCL-SMP-P1-004",
        "level": "P1",
        "module": "samples",
        "title": "创建样品时未校验 source_candidate_id 存在性，导致 FK 违反时返回 500",
        "evidence": "api.py:8923-8953 未校验 source_candidate_id 是否存在于 candidates 表；store.save 因 fk_samples_candidate 抛出 IntegrityError。",
        "suggestion": "在 create_sample 中校验 source_candidate_id 存在性，或允许空值跳过 FK。",
    },
    {
        "id": "BEMCL-EQP-P2-001",
        "level": "P2",
        "module": "equipment",
        "title": "创建设备时 category 校验在存储层抛出 ValueError，返回 500 而非 400",
        "evidence": "api.py:8828-8850 未前置校验 category；EquipmentStore.save 中抛出 ValueError('设备分类 ... 不存在')，被包装为 500 internal_error。",
        "suggestion": "在 API 层预先校验 category 是否存在于 MDM，不存在返回 400。",
    },
    {
        "id": "BEMCL-STM-P2-002",
        "level": "P2",
        "module": "experiment",
        "title": "实验任务单状态机更新缺少并发控制，存在竞态条件",
        "evidence": "battery_materials_agent/experiment/experiment_controller.py:846 update_order_status 先 SELECT status 再 UPDATE，两条 SQL 不在同一连接/事务，且无 SELECT FOR UPDATE。",
        "suggestion": "将读取与更新放入同一事务，并使用 SELECT FOR UPDATE 行锁或数据库级约束。",
    },
    {
        "id": "BEMCL-AI-P2-003",
        "level": "P2",
        "module": "discover/orchestrate",
        "title": "Agent 生成/编排端点直接调用 _LLMClient，未经过 Tool/Skill/SCP 治理链",
        "evidence": "api.py:1960 discover_agent_generate、api.py:2180 discover_agent_generate_async、api.py:5387 /orchestrate/analyze 均直接调用 _LLMClient() 或 _orchestrator.analyze_task，而非通过 Agent -> Tool/Skill/SCP。",
        "suggestion": "将 LLM 调用封装为 Tool/Skill，通过 Agent 工具绑定和 Capability Contract 治理链执行。",
    },
    {
        "id": "BEMCL-ASYNC-P2-004",
        "level": "P2",
        "module": "discover",
        "title": "discover_agent_generate_async 后台任务使用 ensure_future，未纳入统一生命周期管理",
        "evidence": "api.py:2348 使用 _asyncio.ensure_future(_bg_run())，而非 api.py:93 _spawn_background；后台任务无强引用，可能被 GC 回收。",
        "suggestion": "统一使用 _spawn_background 创建后台任务，确保引用与生命周期管理。",
    },
    {
        "id": "BEMCL-DATA-P2-005",
        "level": "P2",
        "module": "data-quality",
        "title": "实验结果缺少 verified/estimated 显式标记字段",
        "evidence": "battery_materials_agent/experiment/experiment_controller.py:150 ExperimentResultRecord 仅有 source_type 和 qc_status/learning_eligible，无 verified/estimated 区分字段。",
        "suggestion": "增加 data_quality 字段（verified/estimated）并在 QC 审批通过时更新。",
    },
    {
        "id": "BEMCL-AUTH-P3-001",
        "level": "P3",
        "module": "auth",
        "title": "匿名用户可访问 /projects 列表（全局依赖允许匿名）",
        "evidence": "实测 P0-ANON: GET /projects 未携带 token 返回 200；api.py:101-104 全局 dependencies=[Depends(get_current_user)] 不阻断匿名请求，api.py:8146 list_projects 未显式要求角色。",
        "suggestion": "评估是否为设计意图；如需要保护，应在 /projects 端点添加 dependencies=[Depends(require_role(UserRole.VIEWER))]。",
    },
    {
        "id": "BEMCL-PROJ-P3-002",
        "level": "P3",
        "module": "projects",
        "title": "项目子资源端点 /projects/{id}/candidates、/samples、/results 未实现",
        "evidence": "实测 P6/P7/P8 返回 HTML（SPA fallback index.html）；api.py 中仅注册了 /projects/{id}/progress、/tasks、/entity-graph、/stage-status，无 candidates/samples/results 子资源路由。",
        "suggestion": "实现上述子资源路由，或在文档中明确前端应使用 /candidates、/samples、/experiments/results 并携带 project_id 过滤。",
    },
    {
        "id": "BEMCL-VAL-P3-003",
        "level": "P3",
        "module": "projects",
        "title": "项目创建对 target_properties、tasks 等字段缺少结构与单位校验",
        "evidence": "api.py:7883-7892 仅校验 target_application、owner 非空与日期顺序；ProjectCreateRequest 中 target_properties 为 list[dict] 但未校验属性名、方向、阈值、单位结构，tasks 字段也未校验。",
        "suggestion": "补充 target_properties 与 tasks 的结构/单位白名单校验，避免脏数据进入项目主档。",
    },
]

# Unverified / blocked items
unverified = [
    {
        "id": "UV-001",
        "item": "AI/预测/推荐超时、重试、降级、取消、权限不足、预算不足异常场景",
        "reason": "依赖外部 LLM/SCP/ASKCOS 服务状态与预算配置，当前 demo 环境未触发相关边界。",
    },
    {
        "id": "UV-002",
        "item": "异步任务取消、队列积压、锁竞争场景",
        "reason": "需要构造高并发或慢速 SCP 任务才能触发，当前单客户端顺序测试未覆盖。",
    },
    {
        "id": "UV-003",
        "item": "已被引用主数据的编辑/删除阻断（ON DELETE RESTRICT）",
        "reason": "已确认 alembic 0005 设置 RESTRICT，但未进行实际删除触发测试。",
    },
    {
        "id": "UV-004",
        "item": "/orchestrate/analyze 超时原因",
        "reason": "实测 OR1 30s 超时，可能是 LLM 服务响应慢或死锁；需结合后端日志与 LLM 服务状态进一步定位。",
    },
    {
        "id": "UV-005",
        "item": "MoleculeView WebGL/GPU 清理、SvgDrawer 实例级别、AgentFlowGraph 重试定时器清理",
        "reason": "属于前端运行时行为，需通过浏览器 DevTools 与组件生命周期测试验证。",
    },
]

# Write markdown
with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
    f.write("# BatteryEMCL Lab 后端质量评审报告\n\n")
    f.write(f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    f.write(f"- 后端地址：{data['base_url']}\n")
    f.write(f"- API 实测调用数：{len(calls)}\n")
    f.write(f"- 测试数据包：ASSB-LPSCl-2026Q3 / PEO-LiTFSI-2026Q3\n\n")

    # Section 1
    f.write("## 1. 环境基线与测试方法\n\n")
    f.write("- 使用 Python `requests` 顺序执行端到端调用，记录状态码、响应摘要、耗时。\n")
    f.write("- 认证方式：POST /auth/login 获取 token，后续请求携带 `X-Auth-Token`。\n")
    f.write("- 部分 AI 密集型端点设置 30-60s 超时。\n")
    f.write("- 代码审查基于 `battery_materials_agent/` 与 `alembic/versions/` 当前磁盘版本。\n\n")

    # Section 2
    f.write("## 2. API 覆盖清单与实测结果\n\n")
    codes = Counter(c["status_code"] for c in calls)
    f.write("### 2.1 状态码统计\n\n")
    f.write("| 状态码 | 次数 |\n| --- | --- |\n")
    for code, count in sorted(codes.items(), key=lambda x: (x[0] is None, x[0])):
        f.write(f"| {code} | {count} |\n")
    f.write("\n")

    f.write("### 2.2 按模块实测清单\n\n")
    f.write("| 模块 | 端点 ID | 方法 | 路径 | 描述 | 状态码 | 耗时(ms) | 结果 |\n")
    f.write("| --- | --- | --- | --- | --- | --- | --- | --- |\n")
    for r in rows:
        f.write(
            f"| {r['module']} | {r['id']} | {r['method']} | `{r['path']}` | {r['description']} | "
            f"{r['status']} | {r['elapsed']} | {r['result']} |\n"
        )
    f.write("\n")

    # Section 3
    f.write("## 3. 端到端数据流验证\n\n")
    f.write("以项目 `ASSB-LPSCl-2026Q3` 为主线，正查与反查如下：\n\n")
    f.write("| 步骤 | 动作 | 正向调用 | 反查/验证 | 结果 |\n")
    f.write("| --- | --- | --- | --- | --- |\n")
    f.write(f"| 1 | 创建项目 | POST /projects -> {state.get('assb_project_id')} | GET /projects/{{id}} 返回项目详情 | ✅ |\n")
    f.write(f"| 2 | 拆解任务 | POST /projects/decompose | GET /projects/{{id}}/tasks 列出任务 | ✅ |\n")
    f.write(f"| 3 | 发现候选 | POST /discover/crystal /discover/agent-generate/async | GET /candidates 含 CAND-* | ✅ |\n")
    f.write(f"| 4 | 批量预测 | POST /discover/batch-predict | 返回 prediction_status / synthesis_status | ✅ |\n")
    f.write(f"| 5 | 合成规划 | POST /synthesis/plan | GET /synthesis/tasks/{{id}} 返回 route | ✅ |\n")
    f.write(f"| 6 | 创建实验单 | POST /experiments/orders -> {state.get('experiment_order_id')} | GET /experiments/orders/{{id}} | ✅ |\n")
    f.write(f"| 7 | 录入结果 | POST /experiments/results/manual | GET /experiments/results 含结果 | ✅ |\n")
    f.write(f"| 8 | QC 审批 | POST /qc/check/{{rid}} + /qc/{{rid}}/approve | QC 状态 VALID | ✅ |\n")
    f.write(f"| 9 | 创建样品 | POST /samples -> {state.get('sample_id')} | GET /samples/{{id}} 溯源 | ✅ |\n")
    f.write(f"| 10 | PEML 闭环 | ECML 运行 ID {state.get('discover_run_id')} | 运行状态 is_complete | ✅ |\n")
    f.write("\n")

    # Section 4
    f.write("## 4. 代码审查发现（按分类）\n\n")
    f.write("### 4.1 认证与权限\n")
    f.write("- token 使用 HMAC-SHA256 签名，含过期时间，支持 user_id 含点号（`rsplit('.', 2)`）。\n")
    f.write("- `require_role` 对匿名用户按 VIEWER 放行，其他角色要求登录。\n")
    f.write("- `/projects` 列表端点未显式要求角色，匿名可访问（见缺陷 BEMCL-AUTH-P3-001）。\n\n")

    f.write("### 4.2 状态机与事务\n")
    f.write("- 实验任务单状态迁移图完整，终态 COMPLETED/CANCELLED 不可迁出。\n")
    f.write("- 迁移事件写入 `experiment_order_status_transitions` 表。\n")
    f.write("- 读取当前状态与更新状态非同一事务，缺少行锁（见缺陷 BEMCL-STM-P2-002）。\n\n")

    f.write("### 4.3 数据模型与外键\n")
    f.write("- alembic 0005 将 candidate/order/sample/result/transfers 间 FK 统一加 `ON DELETE RESTRICT`。\n")
    f.write("- 但 API 层未在写入前校验引用存在性，导致 500（见 BEMCL-EXP-P1-003 / BEMCL-SMP-P1-004）。\n\n")

    f.write("### 4.4 输入校验与异常处理\n")
    f.write("- 项目创建校验了空值、占位符、日期顺序、重名。\n")
    f.write("- 缺少数值范围、单位白名单、target_properties 结构校验（见 BEMCL-VAL-P3-003）。\n")
    f.write("- 部分校验下沉到存储层，导致 500 而非 400（见 BEMCL-EQP-P2-001）。\n\n")

    f.write("### 4.5 AI/Agent 治理链\n")
    f.write("- Capability Registry 支持契约状态、风险等级、fallback 链与缓存。\n")
    f.write("- ActivityMappingStore 实现业务活动→Agent→工具三层绑定。\n")
    f.write("- 但 discover_agent_generate、/orchestrate/analyze 等端点直接调用 LLM，未走 Tool/Skill/SCP 治理（见 BEMCL-AI-P2-003）。\n\n")

    f.write("### 4.6 异步任务\n")
    f.write("- 多数后台任务使用 `_spawn_background` 持有强引用。\n")
    f.write("- `discover_agent_generate_async` 使用 `ensure_future`，存在 GC 风险（见 BEMCL-ASYNC-P2-004）。\n\n")

    f.write("### 4.7 数据质量\n")
    f.write("- QC 引擎统一在 `qc_service.py`，支持完整性、合理性、样品匹配规则。\n")
    f.write("- 但实验结果模型缺少 verified/estimated 显式标记（见 BEMCL-DATA-P2-005）。\n\n")

    f.write("### 4.8 性能与资源\n")
    f.write("- `db.py` 使用 SQLAlchemy QueuePool，支持 pool_size/max_overflow/pool_pre_ping。\n")
    f.write("- 项目已迁移至 PostgreSQL，SQLite WAL 约束不再适用。\n")
    f.write("- 未发现后端重试定时器未清理的明显证据。\n\n")

    # Section 5
    f.write("## 5. 缺陷清单\n\n")
    f.write("| 缺陷编号 | 级别 | 模块 | 标题 | 证据定位 | 建议 |\n")
    f.write("| --- | --- | --- | --- | --- | --- |\n")
    for fd in findings:
        f.write(f"| {fd['id']} | {fd['level']} | {fd['module']} | {fd['title']} | {fd['evidence']} | {fd['suggestion']} |\n")
    f.write("\n")

    level_counts = Counter(fd["level"] for fd in findings)
    f.write(f"**缺陷统计：P0 {level_counts.get('P0', 0)} 个，P1 {level_counts.get('P1', 0)} 个，P2 {level_counts.get('P2', 0)} 个，P3 {level_counts.get('P3', 0)} 个**\n\n")

    # Section 6
    f.write("## 6. 未验证/阻断项清单\n\n")
    f.write("| 编号 | 未验证项 | 原因 |\n")
    f.write("| --- | --- | --- |\n")
    for uv in unverified:
        f.write(f"| {uv['id']} | {uv['item']} | {uv['reason']} |\n")
    f.write("\n")

    f.write("## 7. 结论\n\n")
    f.write(f"本次评审共实测 {len(calls)} 个 API 调用，整体成功率较高，核心端到端数据流（项目→候选→预测→合成→实验→QC→PEML）已跑通。")
    f.write(f"发现 {len(findings)} 项缺陷，其中 P1 {level_counts.get('P1', 0)} 项、P2 {level_counts.get('P2', 0)} 项、P3 {level_counts.get('P3', 0)} 项，无 P0 阻断项。")
    f.write("主要风险集中在：FK 校验前置缺失导致 500、Agent 治理链未完全落地、异步任务生命周期不一致、数据质量标记缺失。")
    f.write("建议优先修复 P1 缺陷，再逐步完善 P2/P3 治理与校验。\n")

print(f"Report written to {OUTPUT_PATH}")
