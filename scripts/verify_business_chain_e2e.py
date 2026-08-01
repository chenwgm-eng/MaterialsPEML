"""业务链路主数据端到端验证脚本。

验证目标链路：
    项目 1 → N 任务
    任务 1 → N 候选材料
    候选材料 1 ↔ 1 BOM 方案
    BOM 方案 1 → N 实验任务（experiment_orders）
    实验任务 1 → N 测试任务（test_tasks）
    测试任务 1 → N 样品
    样品 1 → N 实验数据（experiment_result_records）

同时验证：
    GET /projects/{id}/stage-status 在不同阶段返回正确的任务级标签

用法：
    python scripts/verify_business_chain_e2e.py
    python scripts/verify_business_chain_e2e.py --base-url http://localhost:8000
    python scripts/verify_business_chain_e2e.py --keep   # 保留测试数据，便于排查

注：
- 候选材料目前无直接 POST /candidates 接口（POST /discover/crystal 走 LLM，
  速度慢且不稳定），本脚本通过 SQLAlchemy 直接写入 experiment.candidates 表，
  其余环节全部走 HTTP API。
- 测试数据使用唯一前缀 `E2E-{timestamp}-`，结束时默认清理，避免污染数据库。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from datetime import datetime, timezone

import requests
from sqlalchemy import text

# 让 battery_materials_agent 包可被导入（用于 get_engine）
sys.path.insert(0, ".")
from battery_materials_agent.db import get_engine  # noqa: E402


# ──────────────────────────────────────────────────────────────────────────
# 工具函数
# ──────────────────────────────────────────────────────────────────────────

class Step:
    """单步验证结果。"""

    def __init__(self, name: str):
        self.name = name
        self.ok = False
        self.detail: str = ""
        self.payload: dict | list | None = None

    def pass_(self, detail: str = "", payload=None) -> "Step":
        self.ok = True
        self.detail = detail
        self.payload = payload
        return self

    def fail(self, detail: str, payload=None) -> "Step":
        self.ok = False
        self.detail = detail
        self.payload = payload
        return self


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _short_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8].upper()}"


# ──────────────────────────────────────────────────────────────────────────
# 验证步骤
# ──────────────────────────────────────────────────────────────────────────

def step_01_create_project_with_tasks(base: str, run_id: str) -> Step:
    """01. 创建项目（携带任务列表）→ POST /projects。"""
    step = Step("01 创建项目（含任务）")
    project_name = f"E2E项目-{run_id}"
    payload = {
        "name": project_name,
        "target_application": "固态电池电解质",
        "current_stage": "立项",
        "target_properties": [
            {"name": "ionic_conductivity", "direction": "maximize", "min": 1e-4, "max": None},
        ],
        "owner": "e2e-verifier",
        "department": "验证组",
        "start_date": "2026-07-01",
        "end_date": "2026-12-31",
        "budget": 100000.0,
        "iteration_progress": 0,
        "tasks": [
            {
                "title": "筛选高电导率固态电解质候选",
                "deliverable": "Li7La3Zr2O12 (LLZO) 改性候选材料",
                "target_properties": [
                    {"name": "ionic_conductivity", "direction": "maximize", "min": 1e-4, "max": None},
                    {"name": "band_gap", "direction": "maximize", "min": 3.0, "max": None},
                ],
            },
            {
                "title": "可制造性论证",
                "deliverable": "LLZO 烧结工艺路线",
                "target_properties": [
                    {"name": "formation_energy", "direction": "minimize", "min": None, "max": 0.05},
                ],
            },
        ],
    }
    try:
        r = requests.post(f"{base}/projects", json=payload, timeout=15)
        if r.status_code != 200:
            return step.fail(f"HTTP {r.status_code}: {r.text[:200]}")
        body = r.json()
        pid = body.get("project_id")
        if not pid:
            return step.fail("返回缺少 project_id", body)
        tasks = body.get("tasks") or []
        if len(tasks) != 2:
            return step.fail(f"返回任务数 {len(tasks)} != 2", body)
        return step.pass_(
            f"project_id={pid}, 任务数={len(tasks)}",
            {"project_id": pid, "tasks": tasks, "project_name": project_name},
        )
    except Exception as e:
        return step.fail(f"异常: {e}")


def step_02_get_project_tasks(base: str, project_id: str) -> Step:
    """02. 查询项目任务 → GET /projects/{id}/tasks（应来自 projects.tasks 关系表）。"""
    step = Step("02 查询项目任务（关系表）")
    try:
        r = requests.get(f"{base}/projects/{project_id}/tasks", timeout=10)
        if r.status_code != 200:
            return step.fail(f"HTTP {r.status_code}: {r.text[:200]}")
        tasks = r.json()
        if not isinstance(tasks, list) or len(tasks) != 2:
            return step.fail(f"任务数={len(tasks) if isinstance(tasks, list) else 'N/A'} != 2", tasks)
        # 校验字段
        for t in tasks:
            if not t.get("task_id"):
                return step.fail("任务缺少 task_id", tasks)
            if not t.get("title"):
                return step.fail("任务缺少 title", tasks)
        return step.pass_(
            f"任务数={len(tasks)}, task_ids={[t['task_id'][:8] for t in tasks]}",
            tasks,
        )
    except Exception as e:
        return step.fail(f"异常: {e}")


def step_03_create_candidate_via_db(project_id: str, task_id: str) -> Step:
    """03. 直接写 DB 创建候选材料（携带 task_id / project_id）。"""
    step = Step("03 创建候选材料（DB 直写，含 task_id）")
    candidate_id = _short_id("CAND")
    engine = get_engine()
    try:
        with engine.begin() as conn:
            conn.execute(
                text("""INSERT INTO experiment.candidates
                    (candidate_id, candidate_type, name, smiles, source, scenario_id,
                     task_id, project_id, multi_objective_score, created_at, data)
                    VALUES (:cid, :ctype, :name, :smiles, :source, :scenario,
                            :tid, :pid, :score, :ts, CAST(:data AS JSONB))
                    """),
                {
                    "cid": candidate_id,
                    "ctype": "crystal",
                    "name": "Li7La3Zr2O12",
                    "smiles": "",
                    "source": "e2e_verify",
                    "scenario": "",
                    "tid": task_id,
                    "pid": project_id,
                    "score": 0.85,
                    "ts": _now_iso(),
                    "data": json.dumps({
                        "formula": "Li7La3Zr2O12",
                        "space_group": "Ia-3d",
                        "band_gap": 5.2,
                        "ionic_conductivity_estimate": 1.5e-4,
                        "source_type": "algorithm_generated",
                    }, ensure_ascii=False),
                },
            )
        return step.pass_(
            f"candidate_id={candidate_id}, task_id={task_id[:8]}, project_id={project_id}",
            {"candidate_id": candidate_id, "task_id": task_id, "project_id": project_id},
        )
    except Exception as e:
        return step.fail(f"DB 异常: {e}")


def step_04_get_task_candidates(base: str, task_id: str, expected_cid: str) -> Step:
    """04. 查询任务下候选 → GET /tasks/{task_id}/candidates。"""
    step = Step("04 查询任务下候选材料")
    try:
        r = requests.get(f"{base}/tasks/{task_id}/candidates", timeout=10)
        if r.status_code != 200:
            return step.fail(f"HTTP {r.status_code}: {r.text[:200]}")
        body = r.json()
        candidates = body.get("candidates") or []
        if len(candidates) == 0:
            return step.fail("候选列表为空", body)
        cids = [c.get("candidate_id") for c in candidates]
        if expected_cid not in cids:
            return step.fail(f"未找到预期候选 {expected_cid}, 实际={cids}", body)
        # 校验 task_id 字段已回填
        target = next((c for c in candidates if c.get("candidate_id") == expected_cid), None)
        if not target or target.get("task_id") != task_id:
            return step.fail(
                f"候选 task_id 不匹配: 期望={task_id}, 实际={target.get('task_id') if target else 'N/A'}",
                body,
            )
        return step.pass_(f"候选数={len(candidates)}, 命中={expected_cid}", body)
    except Exception as e:
        return step.fail(f"异常: {e}")


def step_05_create_bom(base: str, candidate_id: str, task_id: str) -> Step:
    """05. 创建 BOM 方案 → POST /candidates/{cid}/bom。"""
    step = Step("05 创建 BOM 方案")
    payload = {
        "task_id": task_id,
        "formulation": {
            "Li2CO3": "0.05 mol",
            "La2O3": "0.03 mol",
            "ZrO2": "0.02 mol",
        },
        "process_route": {
            "step1": "球磨混料 4h",
            "step2": "焙烧 900°C 6h",
            "step3": "等静压成型",
            "step4": "烧结 1100°C 12h",
        },
        "test_protocol": {
            "eis": "电化学阻抗谱 25-80°C",
            "xrd": "XRD 物相分析",
        },
        "version": "v1",
        "status": "draft",
        "created_by": "e2e-verifier",
    }
    try:
        r = requests.post(f"{base}/candidates/{candidate_id}/bom", json=payload, timeout=10)
        if r.status_code not in (200, 201):
            return step.fail(f"HTTP {r.status_code}: {r.text[:200]}")
        bom = r.json()
        bom_id = bom.get("bom_id")
        if not bom_id:
            return step.fail("返回缺少 bom_id", bom)
        if bom.get("candidate_id") != candidate_id:
            return step.fail(f"candidate_id 不匹配: 期望={candidate_id}, 实际={bom.get('candidate_id')}", bom)
        return step.pass_(f"bom_id={bom_id}", bom)
    except Exception as e:
        return step.fail(f"异常: {e}")


def step_06_get_candidate_bom(base: str, candidate_id: str, expected_bom_id: str) -> Step:
    """06. 查询候选 BOM → GET /candidates/{cid}/bom。"""
    step = Step("06 查询候选 BOM 方案")
    try:
        r = requests.get(f"{base}/candidates/{candidate_id}/bom", timeout=10)
        if r.status_code != 200:
            return step.fail(f"HTTP {r.status_code}: {r.text[:200]}")
        body = r.json()
        bom = body.get("bom")
        if not bom:
            return step.fail("返回缺少 bom", body)
        if bom.get("bom_id") != expected_bom_id:
            return step.fail(f"bom_id 不匹配: 期望={expected_bom_id}, 实际={bom.get('bom_id')}", bom)
        if not bom.get("formulation"):
            return step.fail("formulation 为空", bom)
        return step.pass_(f"bom_id={bom['bom_id']}, formulation keys={list(bom.get('formulation', {}).keys())}", bom)
    except Exception as e:
        return step.fail(f"异常: {e}")


def step_07_create_experiment_order(base: str, project_id: str, candidate_id: str,
                                    task_id: str, bom_id: str) -> Step:
    """07. 创建实验任务单 → POST /experiments/orders（携带 task_id 与 bom_id）。"""
    step = Step("07 创建实验任务单（含 task_id / bom_id）")
    payload = {
        "project_id": project_id,
        "candidate_id": candidate_id,
        "execution_mode": "MANUAL_ENTRY",
        "priority": "P2",
        "assignee": "e2e-verifier",
        "material_requirements": [],
        "procedure": [{"step": 1, "action": "球磨混料"}],
        "required_results": ["ionic_conductivity"],
        "acceptance_criteria": {"ionic_conductivity_min": 1e-4},
        "notes": "E2E 验证自动创建",
        "scenario_id": "",
        "bom_id": bom_id,
        "task_id": task_id,
    }
    try:
        r = requests.post(f"{base}/experiments/orders", json=payload, timeout=15)
        if r.status_code not in (200, 201):
            return step.fail(f"HTTP {r.status_code}: {r.text[:300]}")
        order = r.json()
        oid = order.get("order_id")
        if not oid:
            return step.fail("返回缺少 order_id", order)
        # 校验 task_id / bom_id 已透传
        if order.get("task_id") != task_id:
            return step.fail(f"task_id 未透传: 期望={task_id}, 实际={order.get('task_id')}", order)
        if order.get("bom_id") != bom_id:
            return step.fail(f"bom_id 未透传: 期望={bom_id}, 实际={order.get('bom_id')}", order)
        return step.pass_(f"order_id={oid}, task_id={task_id[:8]}, bom_id={bom_id[:8]}", order)
    except Exception as e:
        return step.fail(f"异常: {e}")


def step_08_create_test_task(base: str, order_id: str, bom_id: str) -> Step:
    """08. 创建测试任务 → POST /orders/{oid}/test-tasks。"""
    step = Step("08 创建测试任务")
    payload = {
        "bom_id": bom_id,
        "test_type": "eis",
        "test_method": "method.eis",
        "priority": "P2",
        "assignee": "e2e-verifier",
        "notes": "E2E 验证测试任务",
    }
    try:
        r = requests.post(f"{base}/orders/{order_id}/test-tasks", json=payload, timeout=10)
        if r.status_code not in (200, 201):
            return step.fail(f"HTTP {r.status_code}: {r.text[:200]}")
        tt = r.json()
        ttid = tt.get("test_task_id")
        if not ttid:
            return step.fail("返回缺少 test_task_id", tt)
        if tt.get("order_id") != order_id:
            return step.fail(f"order_id 不匹配: 期望={order_id}, 实际={tt.get('order_id')}", tt)
        if tt.get("bom_id") != bom_id:
            return step.fail(f"bom_id 不匹配: 期望={bom_id}, 实际={tt.get('bom_id')}", tt)
        return step.pass_(f"test_task_id={ttid}, order_id={order_id}, bom_id={bom_id[:8]}", tt)
    except Exception as e:
        return step.fail(f"异常: {e}")


def step_09_get_bom_test_tasks(base: str, bom_id: str, expected_ttid: str) -> Step:
    """09. 查询 BOM 下测试任务 → GET /bom/{bom_id}/test-tasks。"""
    step = Step("09 查询 BOM 下测试任务")
    try:
        r = requests.get(f"{base}/bom/{bom_id}/test-tasks", timeout=10)
        if r.status_code != 200:
            return step.fail(f"HTTP {r.status_code}: {r.text[:200]}")
        body = r.json()
        tasks = body.get("test_tasks") or body.get("tasks") or []
        if not isinstance(tasks, list):
            tasks = []
        ttids = [t.get("test_task_id") for t in tasks]
        if expected_ttid not in ttids:
            return step.fail(f"未找到预期测试任务 {expected_ttid}, 实际={ttids}", body)
        return step.pass_(f"测试任务数={len(tasks)}, 命中={expected_ttid}", body)
    except Exception as e:
        return step.fail(f"异常: {e}")


def step_10_get_order_test_tasks(base: str, order_id: str, expected_ttid: str) -> Step:
    """10. 查询订单下测试任务 → GET /orders/{oid}/test-tasks。"""
    step = Step("10 查询订单下测试任务")
    try:
        r = requests.get(f"{base}/orders/{order_id}/test-tasks", timeout=10)
        if r.status_code != 200:
            return step.fail(f"HTTP {r.status_code}: {r.text[:200]}")
        body = r.json()
        tasks = body.get("test_tasks") or body.get("tasks") or []
        if not isinstance(tasks, list):
            tasks = []
        ttids = [t.get("test_task_id") for t in tasks]
        if expected_ttid not in ttids:
            return step.fail(f"未找到预期测试任务 {expected_ttid}, 实际={ttids}", body)
        return step.pass_(f"测试任务数={len(tasks)}, 命中={expected_ttid}", body)
    except Exception as e:
        return step.fail(f"异常: {e}")


def step_11_create_sample(base: str, test_task_id: str, candidate_id: str,
                          order_id: str) -> Step:
    """11. 创建样品 → POST /samples（携带 test_task_id）。

    test_task_id 透传为软断言：失败时 step.ok=False 但仍返回 sample_id，
    便于后续步骤 12-14 继续验证（API 修复需重启后端才生效）。
    """
    step = Step("11 创建样品（含 test_task_id）")
    payload = {
        "name": f"E2E样品-{test_task_id[:8]}",
        "source_type": "experiment",
        "source_order_id": order_id,
        "source_candidate_id": candidate_id,
        "batch_number": f"BATCH-{test_task_id[:6]}",
        "quantity": 5.0,
        "unit": "g",
        "status": "created",
        "storage_location": "实验室-A-1",
        "storage_condition": "干燥器",
        "notes": "E2E 验证样品",
        "chemical_formula": "Li7La3Zr2O12",
        "scenario_id": "",
        "test_task_id": test_task_id,
    }
    try:
        r = requests.post(f"{base}/samples", json=payload, timeout=10)
        if r.status_code not in (200, 201):
            return step.fail(f"HTTP {r.status_code}: {r.text[:300]}")
        sample = r.json()
        sid = sample.get("sample_id")
        if not sid:
            return step.fail("返回缺少 sample_id", sample)
        # 软断言：test_task_id 未透传时仍返回 sample_id，便于后续步骤继续
        if sample.get("test_task_id") != test_task_id:
            return Step("11 创建样品（含 test_task_id）").fail(
                f"test_task_id 未透传: 期望={test_task_id}, 实际={sample.get('test_task_id')}"
                "（API 修复需重启后端生效；sample_id 已返回，继续后续验证）",
                {"sample_id": sid, "sample": sample},
            )
        return step.pass_(f"sample_id={sid}, test_task_id={test_task_id[:8]}", sample)
    except Exception as e:
        return step.fail(f"异常: {e}")


def step_12_create_experiment_result(base: str, sample_id: str, order_id: str) -> Step:
    """12. 上传实验数据 → POST /experiments/results。"""
    step = Step("12 上传实验数据")
    payload = [
        {
            "experiment_order_id": order_id,
            "sample_id": sample_id,
            "sample_batch_id": "",
            "property_name": "prop.ionic_conductivity",
            "value": 2.3e-4,
            "unit": "S/cm",
            "test_method": "method.eis",
            "test_conditions": {"temperature": 25, "frequency_range": "1Hz-1MHz"},
            "instrument_id": "",
            "uploaded_by": "e2e-verifier",
            "raw_file_uri": "",
            "scenario_id": "",
        }
    ]
    try:
        r = requests.post(f"{base}/experiments/results", json=payload, timeout=10)
        if r.status_code not in (200, 201):
            return step.fail(f"HTTP {r.status_code}: {r.text[:300]}")
        body = r.json()
        imported = body.get("imported", 0)
        if imported != 1:
            return step.fail(f"imported={imported} != 1", body)
        records = body.get("records") or []
        if not records:
            return step.fail("records 为空", body)
        rec = records[0]
        if rec.get("sample_id") != sample_id:
            return step.fail(f"sample_id 不匹配: 期望={sample_id}, 实际={rec.get('sample_id')}", body)
        return step.pass_(f"result_id={rec.get('result_id')}, sample_id={sample_id[:8]}", body)
    except Exception as e:
        return step.fail(f"异常: {e}")


def step_13_stage_status_with_experiment_order(base: str, project_id: str,
                                               task_with_order_id: str,
                                               task_without_anything_id: str) -> Step:
    """13. 验证 stage-status：有实验订单无 ECML → 「实验阶段」；无任何 → 「未启动」。"""
    step = Step("13 stage-status 任务级标签（实验阶段 / 未启动）")
    try:
        r = requests.get(f"{base}/projects/{project_id}/stage-status", timeout=10)
        if r.status_code != 200:
            return step.fail(f"HTTP {r.status_code}: {r.text[:200]}")
        body = r.json()
        tasks = body.get("tasks") or []
        if not isinstance(tasks, list) or len(tasks) < 2:
            return step.fail(f"tasks 数={len(tasks) if isinstance(tasks, list) else 'N/A'} < 2", body)
        # 找到带实验订单的 task
        t1 = next((t for t in tasks if t.get("task_id") == task_with_order_id), None)
        t2 = next((t for t in tasks if t.get("task_id") == task_without_anything_id), None)
        if not t1:
            return step.fail(f"未找到带订单任务 {task_with_order_id}", body)
        if not t2:
            return step.fail(f"未找到无订单任务 {task_without_anything_id}", body)
        # 校验：有订单无 ECML → stage_label == "实验阶段"
        if t1.get("stage_label") != "实验阶段":
            return step.fail(
                f"有订单任务 stage_label={t1.get('stage_label')} != '实验阶段'", body
            )
        # 校验：有订单任务 experiment_orders_summary.total >= 1
        eos = t1.get("experiment_orders_summary") or {}
        if (eos.get("total") or 0) < 1:
            return step.fail(f"有订单任务 experiment_orders_summary.total={eos.get('total')} < 1", body)
        # 校验：无任何 → stage_label == "未启动"
        if t2.get("stage_label") != "未启动":
            return step.fail(
                f"无订单任务 stage_label={t2.get('stage_label')} != '未启动'", body
            )
        return step.pass_(
            f"有订单任务→实验阶段(订单数={eos.get('total')}), 无任何任务→未启动",
            body,
        )
    except Exception as e:
        return step.fail(f"异常: {e}")


def step_14_stage_status_with_ecml_run(project_id: str, task_id: str) -> Step:
    """14. 注入 ECML run 后，验证 stage-status 返回 ECML 细粒度 step 标签。

    通过直接写 ecml.ecml_runs_index 表模拟一个 ECML run（避免调用真实 LLM）。
    注意：ecml_runs_index 表的列为 run_id / status / iteration / is_complete /
    created_at / run_status / iteration_id / parent_run_id / scenario_id /
    task_id / project_id（无 target / target_property，那些在 ecml.ecml_runs 表）。
    """
    step = Step("14 stage-status 任务级标签（ECML 细粒度 step）")
    engine = get_engine()
    run_id = _short_id("ECML")
    scenario_id = _short_id("SCEN")
    iteration_id = 2
    ecml_step = "step4_predict"
    expected_label = "性能预测"
    try:
        # 写入 ecml_runs_index（含 task_id / project_id / iteration_id / status）
        with engine.begin() as conn:
            conn.execute(
                text("""INSERT INTO ecml.ecml_runs_index
                    (run_id, status, iteration, is_complete, created_at,
                     run_status, iteration_id, parent_run_id, scenario_id,
                     task_id, project_id)
                    VALUES (:run_id, :status, :iteration, :complete, :ts,
                            :run_status, :iter_id, :parent, :scenario,
                            :tid, :pid)
                    """),
                {
                    "run_id": run_id,
                    "status": ecml_step,
                    "iteration": iteration_id,
                    "complete": False,
                    "ts": _now_iso(),
                    "run_status": "running",
                    "iter_id": iteration_id,
                    "parent": "",
                    "scenario": scenario_id,
                    "tid": task_id,
                    "pid": project_id,
                },
            )
        # 调用 stage-status
        r = requests.get(f"http://localhost:8000/projects/{project_id}/stage-status", timeout=10)
        if r.status_code != 200:
            return step.fail(f"HTTP {r.status_code}: {r.text[:200]}")
        body = r.json()
        tasks = body.get("tasks") or []
        t = next((x for x in tasks if x.get("task_id") == task_id), None)
        if not t:
            return step.fail(f"未找到任务 {task_id}", body)
        ecml_info = t.get("ecml") or {}
        if ecml_info.get("step_label") != expected_label:
            return step.fail(
                f"step_label={ecml_info.get('step_label')} != {expected_label}",
                body,
            )
        if ecml_info.get("iteration_id") != iteration_id:
            return step.fail(
                f"iteration_id={ecml_info.get('iteration_id')} != {iteration_id}",
                body,
            )
        return step.pass_(
            f"step_label={expected_label}, iter={iteration_id}, run_id={run_id}",
            {"run_id": run_id, "ecml_info": ecml_info, "stage_status": body},
        )
    except Exception as e:
        return step.fail(f"异常: {e}")


# ──────────────────────────────────────────────────────────────────────────
# 清理
# ──────────────────────────────────────────────────────────────────────────

def cleanup(project_id: str, candidate_id: str, bom_id: str, order_id: str,
            test_task_id: str, sample_id: str, ecml_run_id: str) -> None:
    """按依赖关系反向清理测试数据。失败不抛异常，仅打印。"""
    engine = get_engine()
    stmts = [
        # 实验结果 → 样品
        ("DELETE FROM experiment.experiment_result_records WHERE sample_id = :id", sample_id),
        # 样品
        ("DELETE FROM experiment.samples WHERE sample_id = :id", sample_id),
        # 测试任务
        ("DELETE FROM experiment.test_tasks WHERE test_task_id = :id", test_task_id),
        # 实验任务单
        ("DELETE FROM experiment.experiment_orders WHERE order_id = :id", order_id),
        # ECML run
        ("DELETE FROM ecml.ecml_runs_index WHERE run_id = :id", ecml_run_id),
        # BOM 方案
        ("DELETE FROM experiment.bom_schemes WHERE bom_id = :id", bom_id),
        # 候选材料
        ("DELETE FROM experiment.candidates WHERE candidate_id = :id", candidate_id),
        # 项目任务（关系表）
        ("DELETE FROM projects.tasks WHERE project_id = :id", project_id),
        # 项目
        ("DELETE FROM projects.projects WHERE project_id = :id", project_id),
    ]
    for sql, eid in stmts:
        if not eid:
            continue
        try:
            with engine.begin() as conn:
                conn.execute(text(sql), {"id": eid})
        except Exception as e:
            print(f"  [cleanup] 跳过: {sql.split('WHERE')[0].strip()} id={eid[:16]}... : {e}")


# ──────────────────────────────────────────────────────────────────────────
# 主流程
# ──────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="业务链路主数据端到端验证")
    parser.add_argument("--base-url", default="http://localhost:8000",
                        help="后端 API 基址（默认 http://localhost:8000）")
    parser.add_argument("--keep", action="store_true",
                        help="保留测试数据（便于排查），默认清理")
    args = parser.parse_args()

    base = args.base_url.rstrip("/")

    # 健康检查
    try:
        r = requests.get(f"{base}/health", timeout=5)
        if r.status_code != 200:
            print(f"[FATAL] 后端健康检查失败: HTTP {r.status_code}")
            return 2
    except Exception as e:
        print(f"[FATAL] 无法连接后端 {base}: {e}")
        return 2

    run_id = datetime.now().strftime("%Y%m%d%H%M%S")
    print(f"=== 业务链路端到端验证 ===")
    print(f"后端: {base}")
    print(f"运行 ID: {run_id}")
    print()

    # 依次执行 14 个验证步骤
    steps: list[Step] = []

    s1 = step_01_create_project_with_tasks(base, run_id)
    steps.append(s1)
    print(_format_step(s1))
    if not s1.ok:
        return _summarize(steps)
    project_id = s1.payload["project_id"]
    # task_id 在 POST /projects 响应中尚未生成，需要从 GET /projects/{id}/tasks 获取

    s2 = step_02_get_project_tasks(base, project_id)
    steps.append(s2)
    print(_format_step(s2))
    if not s2.ok:
        return _summarize(steps)
    tasks = s2.payload  # list[dict]，含 task_id
    # 选取两个 task：第一个用于候选/BOM/订单/ECML，第二个保持空用于「未启动」验证
    task_a_id = tasks[0]["task_id"]
    task_b_id = tasks[1]["task_id"]

    s3 = step_03_create_candidate_via_db(project_id, task_a_id)
    steps.append(s3)
    print(_format_step(s3))
    if not s3.ok:
        return _summarize(steps, project_id=project_id, task_a_id=task_a_id, task_b_id=task_b_id)
    candidate_id = s3.payload["candidate_id"]

    s4 = step_04_get_task_candidates(base, task_a_id, candidate_id)
    steps.append(s4)
    print(_format_step(s4))

    s5 = step_05_create_bom(base, candidate_id, task_a_id)
    steps.append(s5)
    print(_format_step(s5))
    if not s5.ok:
        return _summarize(steps, project_id=project_id, candidate_id=candidate_id,
                          task_a_id=task_a_id, task_b_id=task_b_id)
    bom_id = s5.payload["bom_id"]

    s6 = step_06_get_candidate_bom(base, candidate_id, bom_id)
    steps.append(s6)
    print(_format_step(s6))

    s7 = step_07_create_experiment_order(base, project_id, candidate_id, task_a_id, bom_id)
    steps.append(s7)
    print(_format_step(s7))
    if not s7.ok:
        return _summarize(steps, project_id=project_id, candidate_id=candidate_id,
                          bom_id=bom_id, task_a_id=task_a_id, task_b_id=task_b_id)
    order_id = s7.payload["order_id"]

    s8 = step_08_create_test_task(base, order_id, bom_id)
    steps.append(s8)
    print(_format_step(s8))
    if not s8.ok:
        return _summarize(steps, project_id=project_id, candidate_id=candidate_id,
                          bom_id=bom_id, order_id=order_id,
                          task_a_id=task_a_id, task_b_id=task_b_id)
    test_task_id = s8.payload["test_task_id"]

    s9 = step_09_get_bom_test_tasks(base, bom_id, test_task_id)
    steps.append(s9)
    print(_format_step(s9))

    s10 = step_10_get_order_test_tasks(base, order_id, test_task_id)
    steps.append(s10)
    print(_format_step(s10))

    s11 = step_11_create_sample(base, test_task_id, candidate_id, order_id)
    steps.append(s11)
    print(_format_step(s11))
    # 步骤 11 为软断言：test_task_id 透传失败时仍返回 sample_id
    payload11 = s11.payload if isinstance(s11.payload, dict) else {}
    sample_id = payload11.get("sample_id", "")
    if not sample_id:
        # 步骤 11 完全通过时 payload 是 sample dict 自身，sample_id 也在其中
        sample_id = payload11.get("sample_id", "")
    if not sample_id:
        return _summarize(steps, project_id=project_id, candidate_id=candidate_id,
                          bom_id=bom_id, order_id=order_id, test_task_id=test_task_id,
                          task_a_id=task_a_id, task_b_id=task_b_id)

    s12 = step_12_create_experiment_result(base, sample_id, order_id)
    steps.append(s12)
    print(_format_step(s12))

    s13 = step_13_stage_status_with_experiment_order(base, project_id, task_a_id, task_b_id)
    steps.append(s13)
    print(_format_step(s13))

    s14 = step_14_stage_status_with_ecml_run(project_id, task_a_id)
    steps.append(s14)
    print(_format_step(s14))
    ecml_run_id = s14.payload.get("run_id", "") if s14.ok else ""

    return _summarize(
        steps,
        cleanup=not args.keep,
        project_id=project_id, candidate_id=candidate_id, bom_id=bom_id,
        order_id=order_id, test_task_id=test_task_id, sample_id=sample_id,
        ecml_run_id=ecml_run_id,
    )


def _format_step(s: Step) -> str:
    mark = "[OK]  " if s.ok else "[FAIL]"
    return f"{mark} {s.name} — {s.detail}"


def _summarize(steps: list[Step], cleanup: bool = False, **ids) -> int:
    print()
    print("=== 验证汇总 ===")
    passed = sum(1 for s in steps if s.ok)
    total = len(steps)
    for s in steps:
        print(_format_step(s))
    print(f"\n通过: {passed}/{total}")
    if cleanup and ids:
        print("\n=== 清理测试数据 ===")
        cleanup_fn(**ids)
        print("清理完成。")
    return 0 if passed == total else 1


def cleanup_fn(project_id: str = "", candidate_id: str = "", bom_id: str = "",
               order_id: str = "", test_task_id: str = "", sample_id: str = "",
               ecml_run_id: str = "", task_a_id: str = "", task_b_id: str = ""):
    """清理函数包装。"""
    cleanup(
        project_id=project_id, candidate_id=candidate_id, bom_id=bom_id,
        order_id=order_id, test_task_id=test_task_id, sample_id=sample_id,
        ecml_run_id=ecml_run_id,
    )


if __name__ == "__main__":
    sys.exit(main())
