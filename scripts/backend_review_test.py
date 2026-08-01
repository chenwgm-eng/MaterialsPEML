"""Backend endpoint census & smoke tests for BatteryEMCL Lab review.

Outputs: d:\BattleFish\BatteryEMCL Lab\doc\review_backend_api_results.json
"""
from __future__ import annotations

import json
import time
import uuid
import traceback
from dataclasses import dataclass, field, asdict
from typing import Any

import requests

BASE = "http://localhost:8000"
RESULTS_PATH = r"d:\BattleFish\BatteryEMCL Lab\doc\review_backend_api_results.json"


@dataclass
class Call:
    id: str
    module: str
    method: str
    path: str
    description: str
    status_code: int | None = None
    elapsed_ms: float | None = None
    response_summary: str = ""
    error: str = ""
    req_body: Any = field(default=None, repr=False)
    auth: bool = True


_results: list[Call] = []
_token: str | None = None
_state: dict[str, Any] = {}


def _headers(auth: bool = True) -> dict[str, str]:
    h = {"Content-Type": "application/json"}
    if auth and _token:
        h["X-Auth-Token"] = _token
    return h


def _short(text: str | None, max_len: int = 220) -> str:
    if text is None:
        return ""
    text = str(text)
    if len(text) > max_len:
        return text[:max_len] + "..."
    return text


def _summarize(resp: requests.Response) -> str:
    try:
        data = resp.json()
        if isinstance(data, dict):
            # mask token if present
            if "token" in data and isinstance(data["token"], str):
                data = {**data, "token": data["token"][:12] + "..."}
        return _short(json.dumps(data, ensure_ascii=False), 300)
    except Exception:
        return _short(resp.text, 300)


def _call(
    cid: str,
    module: str,
    method: str,
    path: str,
    body: Any = None,
    auth: bool = True,
    description: str = "",
    timeout: float = 20.0,
) -> requests.Response | None:
    call = Call(
        id=cid,
        module=module,
        method=method,
        path=path,
        description=description,
        auth=auth,
        req_body=body,
    )
    url = f"{BASE}{path}"
    try:
        kwargs: dict[str, Any] = {"headers": _headers(auth), "timeout": timeout}
        if body is not None:
            kwargs["json"] = body
        start = time.perf_counter()
        resp = requests.request(method, url, **kwargs)
        call.elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
        call.status_code = resp.status_code
        call.response_summary = _summarize(resp)
        _results.append(call)
        return resp
    except requests.exceptions.Timeout as e:
        call.status_code = None
        call.error = f"TIMEOUT after {timeout}s"
        call.response_summary = str(e)
        _results.append(call)
        return None
    except Exception as e:
        call.status_code = None
        call.error = f"ERR: {type(e).__name__}: {e}"
        _results.append(call)
        return None


def _save():
    data = {
        "base_url": BASE,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "state": {k: v for k, v in _state.items() if k not in ("token_preview",)},
        "calls": [asdict(c) for c in _results],
    }
    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def login():
    global _token
    r = _call("A1", "auth", "POST", "/auth/login", {"username": "admin", "password": "admin123"}, auth=False, description="管理员登录")
    if r and r.status_code == 200:
        _token = r.json().get("token")
        _state["user_id"] = r.json().get("user_id")


def auth_module():
    _call("A2", "auth", "GET", "/auth/me", description="获取当前登录用户")
    _call("A3", "auth", "GET", "/auth/me", auth=False, description="未登录访问 /auth/me（应 401）")
    _call("A4", "auth", "GET", "/auth/users", description="admin 列出用户")
    _call("A5", "auth", "GET", "/audit/logs", description="admin 查看审计日志")


def projects_module():
    # anonymous access to list projects (security check)
    _call("P0-ANON", "projects", "GET", "/projects", auth=False, description="未登录访问项目列表（安全测试）")

    # create test project (unique name to avoid collisions, but keep package identity in notes)
    ts = time.strftime("%m%d%H%M%S")
    proj_name = f"ASSB-LPSCl-2026Q3-{ts}"
    body = {
        "name": proj_name,
        "target_application": "全固态电池硫化物电解质",
        "current_stage": "立项",
        "target_properties": [
            {"name": "ionic_conductivity", "direction": "maximize", "min": 1.0e-3, "unit": "S/cm", "temperature": "25C"}
        ],
        "owner": "review-agent",
        "notes": "Test package ASSB-LPSCl-2026Q3; candidates: Li6PS5Cl, Li7P3S11, Li10GeP2S12",
        "department": "BatteryEMCL",
        "start_date": "2026-07-01",
        "end_date": "2026-09-30",
        "budget": 500000,
        "iteration_progress": 10,
        "tasks": [
            {"title": "筛选硫化物固态电解质候选", "deliverable": "高离子电导率硫化物电解质", "target_properties": [{"name": "ionic_conductivity", "direction": "maximize", "min": 1.0e-3}]}
        ],
    }
    r = _call("P1", "projects", "POST", "/projects", body, description="创建 ASSB-LPSCl 测试项目")
    if r and r.status_code == 200:
        pid = r.json().get("project_id")
        _state["assb_project_id"] = pid
    else:
        pid = None

    # negative: duplicate name
    _call("P1-DUP", "projects", "POST", "/projects", body, description="重名项目创建测试（应 409）")

    # negative: missing target_application and owner
    bad_body = {"name": f"Bad-{ts}", "target_application": "   ", "owner": "????"}
    _call("P1-BAD", "projects", "POST", "/projects", bad_body, description="项目关键字段为空/占位符（应 400）")

    # negative: end_date < start_date
    bad_body2 = {
        "name": f"BadDate-{ts}",
        "target_application": "x",
        "owner": "x",
        "start_date": "2026-09-30",
        "end_date": "2026-07-01",
    }
    _call("P1-DATE", "projects", "POST", "/projects", bad_body2, description="项目结束日期早于开始日期（应 400）")

    if pid:
        _call("P2", "projects", "GET", f"/projects/{pid}", description="获取项目详情")
        _call("P3", "projects", "GET", f"/projects/{pid}/progress", description="项目进度")
        _call("P4", "projects", "GET", f"/projects/{pid}/tasks", description="项目任务列表")
        _call("P5", "projects", "GET", f"/projects/{pid}/entity-graph", description="项目实体图")
        _call("P6", "projects", "GET", f"/projects/{pid}/candidates", description="项目候选列表")
        _call("P7", "projects", "GET", f"/projects/{pid}/samples", description="项目样品列表")
        _call("P8", "projects", "GET", f"/projects/{pid}/results", description="项目结果列表")

        # decompose (AI heavy; short timeout)
        _call(
            "P9",
            "projects",
            "POST",
            "/projects/decompose",
            {"name": proj_name, "goal": "25C离子电导率>=1e-3 S/cm的硫化物固态电解质", "end_date": "2026-09-30"},
            description="AI 拆解项目目标",
            timeout=30.0,
        )

        # create project task
        task_body = {
            "title": "合成 Li6PS5Cl 并测离子电导率",
            "deliverable": "Li6PS5Cl 样品",
            "target_properties": [{"name": "ionic_conductivity", "direction": "maximize", "min": 1.0e-3}],
            "status": "draft",
            "assignee": "review-agent",
        }
        r2 = _call("P10", "projects", "POST", f"/projects/{pid}/tasks", task_body, description="创建项目任务")
        if r2 and r2.status_code == 200:
            _state["assb_task_id"] = r2.json().get("task_id")

        # stage status
        _call("P11", "projects", "GET", f"/projects/{pid}/stage-status", description="项目阶段状态")


def discover_module():
    pid = _state.get("assb_project_id")
    # discover generic
    body = {"target": "Li6PS5Cl-like sulfide electrolyte", "target_property": "ionic_conductivity", "max_iterations": 1, "scenario_id": "review-001"}
    r = _call("D1", "discover", "POST", "/discover", body, description="ECML 闭环发现（1轮）", timeout=60.0)
    if r and r.status_code == 200:
        _state["discover_run_id"] = r.json().get("run_id")

    # crystal
    _call("D2", "discover", "POST", "/discover/crystal", {"formula": "Li6PS5Cl", "space_group": "", "target_property": "ionic_conductivity"}, description="晶体候选发现", timeout=40.0)

    # polymer
    _call("D3", "discover", "POST", "/discover/polymer", {"smiles": "CCO", "polymer_type": "polyether", "target_properties": [{"name": "ionic_conductivity", "min": 1e-4}]}, description="聚合物候选发现", timeout=40.0)

    # batch predict
    bp_body = {
        "material_kind": "crystal",
        "candidates": [
            {"formula": "Li6PS5Cl", "name": "Li6PS5Cl"},
            {"formula": "Li7P3S11", "name": "Li7P3S11"},
            {"formula": "Li10GeP2S12", "name": "Li10GeP2S12"},
        ],
        "target_properties": [{"name": "ionic_conductivity", "min": 1.0e-3}],
        "run_synthesis_check": False,
    }
    _call("D4", "discover", "POST", "/discover/batch-predict", bp_body, description="批量预测候选", timeout=60.0)

    # agent generate async
    ag_body = {
        "task_title": "硫化物固态电解质",
        "deliverable": "Li6PS5Cl",
        "target_properties": [{"name": "ionic_conductivity", "direction": "maximize", "min": 1.0e-3}],
        "material_kind": "crystal",
        "num_candidates": 2,
        "project_id": pid or "",
        "scenario_id": "review-001",
    }
    r = _call("D5", "discover", "POST", "/discover/agent-generate/async", ag_body, description="Agent 异步生成候选", timeout=30.0)
    if r and r.status_code == 200:
        _state["agent_gen_task_id"] = r.json().get("task_id")

    if _state.get("agent_gen_task_id"):
        _call("D6", "discover", "GET", f"/discover/agent-generate/{_state['agent_gen_task_id']}/status", description="查询异步生成状态")

    # generate
    _call("D7", "discover", "POST", "/discover/generate", {"mode": "molecule", "count": 3, "constraints": {"elements": ["Li", "P", "S"]}}, description="生成候选", timeout=40.0)


def candidates_module():
    _call("C1", "candidates", "GET", "/candidates", description="候选列表")
    _call("C2", "candidates", "GET", "/candidates?page=1&size=10", description="候选列表分页")

    # try to get first candidate detail if list returned any
    r = requests.get(f"{BASE}/candidates", headers=_headers(), timeout=10)
    first_id = None
    if r.status_code == 200:
        try:
            items = r.json()
            if isinstance(items, list) and items:
                first_id = items[0].get("candidate_id")
            elif isinstance(items, dict) and items.get("items"):
                first_id = items["items"][0].get("candidate_id")
        except Exception:
            pass
    if first_id:
        _call("C3", "candidates", "GET", f"/candidates/{first_id}", description="候选详情")
        _call("C4", "candidates", "GET", f"/candidates/{first_id}/bom", description="候选 BOM")
        _call("C5", "candidates", "GET", f"/candidates/{first_id}/artifacts", description="候选产物")
        _call("C6", "candidates", "GET", f"/candidates/{first_id}/synthesis-tasks", description="候选合成任务")
    else:
        _call("C3", "candidates", "GET", "/candidates/NONEXISTENT", description="候选详情（使用占位 ID，应 404）")

    # search with special chars
    _call("C7", "candidates", "GET", "/candidates?q=Li6PS5Cl%3Cscript%3E", description="候选特殊字符搜索")


def synthesis_module():
    _call("S1", "synthesis", "POST", "/synthesis/plan", {"smiles": "CCO", "max_depth": 2, "num_routes": 2}, description="合成路线规划", timeout=40.0)
    _call("S2", "synthesis", "POST", "/synthesis/plan/multi", {"smiles": "CCO", "num_routes": 2}, description="多路径合成规划", timeout=40.0)
    _call("S3", "synthesis", "GET", "/synthesis/network/CCO", description="合成网络")
    _call("S4", "synthesis", "GET", "/synthesis/tasks", description="合成任务列表")
    _call("S5", "synthesis", "GET", "/synthesis/stats", description="合成统计")
    _call("S6", "synthesis", "GET", "/synthesis/health", description="合成健康检查")

    # async synthesis
    r = _call("S7", "synthesis", "POST", "/synthesis/plan/async", {"smiles": "CCO", "num_routes": 2, "material_type": "molecule"}, description="异步合成规划", timeout=20.0)
    if r and r.status_code == 200:
        _state["synthesis_task_id"] = r.json().get("task_id")
    if _state.get("synthesis_task_id"):
        _call("S8", "synthesis", "GET", f"/synthesis/tasks/{_state['synthesis_task_id']}", description="查询异步合成任务")


def formulas_module():
    # auto draft formula
    r = _call("F1", "formulas", "POST", "/formulas", {"auto_draft": True, "target_material": {"formula": "Li6PS5Cl", "name": "Li6PS5Cl"}, "quantity": 1.0}, description="自动生成配方草案", timeout=40.0)
    if r and r.status_code == 200:
        _state["formula_id"] = r.json().get("formula_id")
    _call("F2", "formulas", "GET", "/formulas", description="配方列表")
    if _state.get("formula_id"):
        fid = _state["formula_id"]
        _call("F3", "formulas", "GET", f"/formulas/{fid}", description="配方详情")
        _call("F4", "formulas", "GET", f"/formulas/{fid}/history", description="配方历史")


def _pick_usable_candidate_id() -> str:
    """选择一个无需放行卡的真实候选 ID，避免 FK/门禁失败。"""
    r = requests.get(f"{BASE}/candidates", headers=_headers(), timeout=10)
    if r.status_code != 200:
        return ""
    try:
        data = r.json()
        items = data.get("candidates", []) if isinstance(data, dict) else data
        for item in items:
            data = item.get("data", {})
            if not data.get("release_card_required"):
                return item.get("candidate_id") or ""
        # 全部需要放行卡时退而求其次返回第一个 candidate_id
        return items[0].get("candidate_id") if items else ""
    except Exception:
        return ""


def experiments_module():
    pid = _state.get("assb_project_id")
    cand_id = _pick_usable_candidate_id()
    _state["usable_candidate_id"] = cand_id
    # create order (idempotency key)
    key = f"review-order-{uuid.uuid4().hex[:8]}"
    body = {
        "project_id": pid or "",
        "candidate_id": cand_id or "Li6PS5Cl",
        "execution_mode": "MANUAL_ENTRY",
        "priority": "P1",
        "assignee": "review-agent",
        "required_results": ["ionic_conductivity"],
        "idempotency_key": key,
        "notes": "Review test order",
    }
    r = _call("E1", "experiments", "POST", "/experiments/orders", body, description="创建实验任务单")
    if r and r.status_code == 200:
        _state["experiment_order_id"] = r.json().get("order_id")
        # double click
        _call("E1-DUP", "experiments", "POST", "/experiments/orders", body, description="重复提交实验任务单（应幂等）")

    # negative: missing project_id
    _call("E1-BAD", "experiments", "POST", "/experiments/orders", {"candidate_id": "X", "idempotency_key": f"k{uuid.uuid4().hex[:6]}"}, description="实验单缺少 project_id（应 400）")

    _call("E2", "experiments", "GET", "/experiments/orders", description="实验任务单列表")
    if _state.get("experiment_order_id"):
        oid = _state["experiment_order_id"]
        _call("E3", "experiments", "GET", f"/experiments/orders/{oid}", description="实验单详情")
        _call("E4", "experiments", "GET", f"/experiments/orders/{oid}/audit", description="实验单审计")
        _call("E5", "experiments", "GET", f"/experiments/analysis/{oid}", description="实验单分析")

    _call("E6", "experiments", "GET", "/experiments/types", description="实验类型")
    _call("E7", "experiments", "GET", "/experiments/results", description="实验结果列表")

    # manual result
    res_body = {
        "experiment_order_id": _state.get("experiment_order_id", ""),
        "sample_id": "",
        "property_name": "ionic_conductivity",
        "value": 1.2e-3,
        "unit": "S/cm",
        "test_method": "EIS",
        "uploaded_by": "review-agent",
    }
    _call("E8", "experiments", "POST", "/experiments/results/manual", res_body, description="手工录入实验结果")

    # invalid property name
    bad_res = {**res_body, "property_name": "not_a_real_property"}
    _call("E8-BAD", "experiments", "POST", "/experiments/results/manual", bad_res, description="实验结果未知属性（应 400）")

    # deviation check
    _call("E9", "experiments", "POST", "/experiments/deviation-check", {"order_id": _state.get("experiment_order_id", ""), "result": {"value": 1.2e-3, "expected": 1.0e-3}}, description="实验偏差检查")


def qc_module():
    _call("Q1", "qc", "GET", "/qc/pending", description="待 QC 列表")
    # get a result id
    r = requests.get(f"{BASE}/experiments/results", headers=_headers(), timeout=10)
    rid = None
    if r.status_code == 200:
        try:
            items = r.json()
            if isinstance(items, list) and items:
                rid = items[0].get("result_id")
        except Exception:
            pass
    if rid:
        _call("Q2", "qc", "POST", f"/qc/check/{rid}", {"rule_version": "v1"}, description="执行 QC 检查")
        _call("Q3", "qc", "POST", f"/qc/{rid}/approve", {"reviewer": "review-agent", "notes": "ok"}, description="QC 审批通过")


def samples_equipment_module():
    pid = _state.get("assb_project_id")
    cand_id = _state.get("usable_candidate_id") or _pick_usable_candidate_id()
    # sample with unique code
    code = f"S-{uuid.uuid4().hex[:6].upper()}"
    body = {
        "name": "Li6PS5Cl-样品-1",
        "source_type": "experiment",
        "source_order_id": _state.get("experiment_order_id", ""),
        "source_candidate_id": cand_id or "Li6PS5Cl",
        "batch_number": "B001",
        "quantity": 1.0,
        "unit": "g",
        "sample_code": code,
        "chemical_formula": "Li6PS5Cl",
        "scenario_id": "review-001",
    }
    r = _call("SM1", "samples", "POST", "/samples", body, description="创建样品")
    if r and r.status_code == 200:
        sid = r.json().get("sample_id")
        _state["sample_id"] = sid
        # duplicate sample code
        _call("SM1-DUP", "samples", "POST", "/samples", body, description="重复样品号（应 409）")
        _call("SM2", "samples", "GET", f"/samples/{sid}", description="样品详情")
        _call("SM3", "samples", "PUT", f"/samples/{sid}", {"name": "Li6PS5Cl-样品-1-renamed"}, description="编辑样品")
        _call("SM4", "samples", "PUT", f"/samples/{sid}/transfer", {"to_status": "in_storage", "to_location": "Lab-A", "transferred_by": "review-agent"}, description="样品状态流转")
        _call("SM5", "samples", "GET", f"/samples/{sid}/transfers", description="样品流转记录")

    _call("SM6", "samples", "GET", "/samples", description="样品列表")

    # equipment (category must exist in MDM reference dict)
    eq_body = {"name": "EIS 分析仪", "model": "Zennium", "category": "equipment.analysis", "serial_number": "SN-001", "location": "Lab-A", "status": "idle"}
    r = _call("EQ1", "equipment", "POST", "/equipment", eq_body, description="创建设备")
    if r and r.status_code == 200:
        eid = r.json().get("equipment_id")
        _state["equipment_id"] = eid
        _call("EQ2", "equipment", "GET", f"/equipment/{eid}", description="设备详情")
        _call("EQ3", "equipment", "PUT", f"/equipment/{eid}", {"status": "maintenance"}, description="更新设备状态")
    _call("EQ4", "equipment", "GET", "/equipment", description="设备列表")


def data_ingest_module():
    _call("DI1", "data-ingest", "GET", "/ingest/field-dict/project", description="导入字段字典")
    preview_body = {
        "entity_type": "project",
        "rows": [{"项目名称": f"Ingest-{uuid.uuid4().hex[:6]}", "目标应用": "固态电解质", "负责人": "review-agent"}],
    }
    _call("DI2", "data-ingest", "POST", "/ingest/preview", preview_body, description="导入预览")
    key = f"ingest-review-{uuid.uuid4().hex[:8]}"
    commit_body = {
        "entity_type": "project",
        "rows": [{"项目名称": f"IngestCommit-{uuid.uuid4().hex[:6]}", "目标应用": "固态电解质", "负责人": "review-agent"}],
        "mapping": {},
        "idempotency_key": key,
        "file_name": "review.csv",
        "operator": "review-agent",
    }
    r = _call("DI3", "data-ingest", "POST", "/ingest/commit", commit_body, description="导入提交")
    if r and r.status_code == 200:
        _state["import_id"] = r.json().get("import_id")
        # duplicate key
        _call("DI3-DUP", "data-ingest", "POST", "/ingest/commit", commit_body, description="重复导入幂等（应 duplicated=true）")
    _call("DI4", "data-ingest", "GET", "/ingest/imports", description="导入历史")
    if _state.get("import_id"):
        _call("DI5", "data-ingest", "GET", f"/ingest/imports/{_state['import_id']}", description="导入详情")


def mdm_module():
    endpoints = [
        ("MDM1", "GET", "/mdm/status-codes?domain=sample", None, "状态码列表"),
        ("MDM2", "GET", "/mdm/units", None, "单位列表"),
        ("MDM3", "GET", "/mdm/units/S/cm", None, "单位详情"),
        ("MDM4", "GET", "/mdm/test-methods", None, "检测方法列表"),
        ("MDM5", "GET", "/mdm/properties", None, "属性列表"),
        ("MDM6", "GET", "/mdm/material-categories", None, "物料分类"),
        ("MDM7", "GET", "/mdm/process-routes", None, "工艺路线"),
        ("MDM8", "GET", "/mdm/sample-types", None, "样品类型"),
        ("MDM9", "GET", "/mdm/equipment-templates", None, "设备模板"),
        ("MDM10", "POST", "/mdm/units/convert", {"from_unit": "S/cm", "to_unit": "mS/cm", "value": 1.0}, "单位换算"),
    ]
    for cid, method, path, body, desc in endpoints:
        _call(cid, "mdm", method, path, body, description=desc)


def knowledge_module():
    _call("K1", "knowledge", "POST", "/knowledge/search", {"query": "ionic conductivity sulfide electrolyte", "limit": 5}, description="知识搜索")
    _call("K2", "knowledge", "POST", "/knowledge/graph", {"query": "Li6PS5Cl", "depth": 1}, description="知识图谱查询")
    _call("K3", "knowledge", "GET", "/knowledge/graphs", description="图谱列表")
    _call("K4", "knowledge", "GET", "/knowledge/papers", description="论文列表")
    _call("K5", "knowledge", "GET", "/knowledge/materials", description="知识材料列表")
    # special char search
    _call("K6", "knowledge", "POST", "/knowledge/search", {"query": "<script>alert(1)</script>", "limit": 5}, description="知识搜索特殊字符")


def agents_tools_orchestration_module():
    _call("AG1", "agents", "GET", "/agents", description="Agent 列表")
    _call("AG2", "agents", "GET", "/agents/llm-options", description="LLM 选项")
    _call("AG3", "agents", "GET", "/agents/health", description="Agent 健康")
    _call("TL1", "tools", "GET", "/tools", description="工具列表")
    _call("TL2", "tools", "GET", "/tools/scp-bindings", description="SCP 绑定（admin）")
    _call("TL3", "tools", "GET", "/tools/skills", description="Skills（admin）")
    _call("OR1", "orchestration", "POST", "/orchestrate/analyze", {"target": "plan synthesis for Li6PS5Cl"}, description="编排分析", timeout=30.0)
    _call("OR2", "orchestration", "GET", "/orchestrate/history", description="编排历史")


def control_plane_module():
    _call("CP1", "control-plane", "GET", "/control-plane/runs", description="控制面运行列表")
    _call("CP2", "control-plane", "GET", "/control-plane/budgets", description="预算列表")
    _call("CP3", "control-plane", "GET", "/control-plane/tools", description="控制面工具列表")
    _call("CP4", "control-plane", "GET", "/control-plane/providers", description="Provider 列表")
    _call("CP5", "control-plane", "GET", "/control-plane/policies", description="策略列表")
    _call("BG1", "budgets", "GET", "/budgets/token-usage", description="Token 使用")


def capability_release_value_module():
    _call("CAP1", "capability-center", "GET", "/capabilities", description="能力契约列表")
    _call("CAP2", "capability-center", "GET", "/capabilities/synthesis_planning_askcos_v1/fallback-chain", description="能力契约回退链")
    _call("RC1", "release-cards", "GET", "/release-cards/metrics/summary", description="放行卡指标")
    _call("RC2", "release-cards", "GET", "/release-cards", description="放行卡列表")
    rc_body = {"project_id": _state.get("assb_project_id", ""), "title": "Review release card", "status": "draft"}
    r = _call("RC3", "release-cards", "POST", "/release-cards", rc_body, description="创建放行卡")
    if r and r.status_code == 200:
        cid = r.json().get("card_id")
        _state["release_card_id"] = cid
        _call("RC4", "release-cards", "GET", f"/release-cards/{cid}", description="放行卡详情")

    if _state.get("assb_project_id"):
        _call("VR1", "value-report", "GET", f"/value-reports/{_state['assb_project_id']}", description="项目收益报告")


def dashboard_settings_module():
    _call("DB1", "dashboard", "GET", "/dashboard/overview", description="概览仪表盘")
    _call("DB2", "dashboard", "GET", "/dashboard/cost", description="成本仪表盘")
    _call("DB3", "dashboard", "GET", "/dashboard/resources", description="资源仪表盘")
    _call("ST1", "settings", "GET", "/settings/model_catalog", description="模型目录")
    _call("CF1", "config", "GET", "/config", description="系统配置")


def eval_center_module():
    _call("EV1", "eval-center", "GET", "/evals/runs", description="评测运行列表")


def workflow_properties_module():
    _call("WF1", "workflow", "GET", "/workflow/schema", description="工作流 schema")
    _call("WF2", "workflow", "GET", "/workflow/nodes", description="工作流节点")
    _call("PR1", "properties", "GET", "/properties/categories", description="属性分类")
    _call("PR2", "properties", "GET", "/properties/fields", description="属性字段")
    _call("PR3", "properties", "GET", "/properties/options", description="属性选项")
    _call("PR4", "properties", "GET", "/properties/templates", description="属性模板")


def main():
    login()
    if not _token:
        print("Login failed; aborting authenticated tests.")
        _save()
        return

    auth_module()
    projects_module()
    discover_module()
    candidates_module()
    synthesis_module()
    formulas_module()
    experiments_module()
    qc_module()
    samples_equipment_module()
    data_ingest_module()
    mdm_module()
    knowledge_module()
    agents_tools_orchestration_module()
    control_plane_module()
    capability_release_value_module()
    dashboard_settings_module()
    eval_center_module()
    workflow_properties_module()

    _save()
    print(f"Done. {len(_results)} calls recorded -> {RESULTS_PATH}")


if __name__ == "__main__":
    main()
