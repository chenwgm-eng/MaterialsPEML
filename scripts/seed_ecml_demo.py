"""Seed end-to-end demo data to unblock the ECML closed-loop and the process-deepening pipeline.

背景：`experiment_result_records` 无数据时，ECML 闭环迭代的启动前置条件
（"至少需要 1 条实验数据"）不满足，核心闭环无法演示；同时工艺深化流水线
只展示状态为 feasible 及以上的候选，而候选不会自动流转，导致流水线为空。

本脚本插入 2 条端到端示例链路（候选材料 → 样品 → 实验任务单 → 实验结果）：
- 候选材料以 ready_for_experiment 状态写入，可直接出现在工艺深化流水线中；
- 实验结果写入 experiment_result_records，满足 ECML 启动前置条件。

链路可完整溯源：样品经由实验单反查 candidate_id。

⚠️ 演示专用：脚本会向当前数据库直写 SEED_ 前缀候选与 SEED_FORMULA_* 假化学式
（而非真实分子式），这些假数据会进入化学合理性/委员会评估链路。仅可在演示/开发库执行，
禁止在生产库运行。默认拒绝执行，需设置环境变量 SEED_CONFIRM=1 显式确认。

用法（在仓库根目录运行）：
    SEED_CONFIRM=1 python scripts/seed_ecml_demo.py

脚本幂等：候选/实验单/结果均带固定 ID，已存在则跳过，可重复运行。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# 允许直接以 python scripts/seed_ecml_demo.py 运行
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from battery_materials_agent import api as api_module  # noqa: E402
from battery_materials_agent.api import app, _save_single_result_record  # noqa: E402
from battery_materials_agent.api import ExperimentResultManualRequest  # noqa: E402
from battery_materials_agent.db import get_engine  # noqa: E402
from battery_materials_agent.experiment.candidate_store import CandidateRecord, CandidateStatus  # noqa: E402
from battery_materials_agent.experiment.experiment_controller import ExperimentOrder  # noqa: E402
from battery_materials_agent.experiment.process_scheme_store import ProcessScheme, ProcessSchemeStore  # noqa: E402
from battery_materials_agent.experiment.sample_store import SampleStore  # noqa: E402
from battery_materials_agent.config import get_config  # noqa: E402
from battery_materials_agent.agent import BatteryMaterialsAgent  # noqa: E402
from sqlalchemy import text  # noqa: E402

# 2 条端到端示例链路（电池材料场景）
# 注意：candidate data.formula 使用唯一种子值，避免与现有真实候选触发
# candidate_store 的 content_hash 去重（否则按候选名/Li 式命中已有候选会跳过插入）。
DEMO_CANDIDATES = [
    {
        "candidate_id": "SEED_CAND_LLZO",
        "candidate_type": "crystal",
        "name": "Li7La3Zr2O12",
        "formula": "SEED_FORMULA_LLZO",
        "smiles": "",
        "source": "seed_demo",
        "status": CandidateStatus.READY_FOR_EXPERIMENT.value,
    },
    {
        "candidate_id": "SEED_CAND_PEO",
        "candidate_type": "polymer",
        "name": "PEO-LiTFSI",
        "formula": "SEED_FORMULA_PEO",
        "smiles": "C(COCCO[*])[*]",
        "source": "seed_demo",
        "status": CandidateStatus.READY_FOR_EXPERIMENT.value,
    },
]

# 每个候选的实验结果（property_name / unit / test_method 均为 MDM 合法 ID）
DEMO_RESULTS = {
    "SEED_CAND_LLZO": [
        {"property_name": "ionic_conductivity", "value": 0.0004, "unit": "S/cm", "test_method": "EIS"},
        {"property_name": "crystallinity", "value": 96.0, "unit": "%", "test_method": "XRD"},
    ],
    "SEED_CAND_PEO": [
        {"property_name": "ionic_conductivity", "value": 0.0001, "unit": "S/cm", "test_method": "EIS"},
        {"property_name": "operating_voltage", "value": 4.2, "unit": "V", "test_method": "CV"},
    ],
}


def _count_results() -> int:
    with get_engine().connect() as conn:
        row = conn.execute(
            text("SELECT COUNT(*) FROM experiment.experiment_result_records")
        ).fetchone()
        return int(row[0]) if row else 0


def _candidate_exists(candidate_id: str) -> bool:
    with get_engine().connect() as conn:
        row = conn.execute(
            text("SELECT 1 FROM experiment.candidates WHERE candidate_id = :id"),
            {"id": candidate_id},
        ).fetchone()
        return row is not None


def main() -> None:
    # 演示专用护栏：防止误在生产库写入假化学式数据
    if os.environ.get("SEED_CONFIRM") != "1":
        print("[seed] 这是演示专用脚本，会写入 SEED_FORMULA_* 假化学式数据。")
        print("[seed] 请确认在演示/开发库执行，并通过 SEED_CONFIRM=1 显式确认。")
        sys.exit(1)

    # 复现 api 的 startup 最小初始化：agent + 关键 store 挂到 api 模块全局，
    # 使 _save_single_result_record 能通过 agent / app.state 正常写入。
    config = get_config()
    agent = BatteryMaterialsAgent(config)
    # _save_single_result_record 依赖 api 模块全局 agent / app，需显式注入
    api_module.agent = agent
    app.state.agent = agent
    app.state.candidate_store = agent.candidate_store
    app.state.sample_store = SampleStore()
    app.state.process_scheme_store = ProcessSchemeStore()

    before = _count_results()
    print(f"[seed] 当前 experiment_result_records 记录数：{before}")

    created_candidates = 0
    created_orders = 0
    created_results = 0

    for meta in DEMO_CANDIDATES:
        cid = meta["candidate_id"]
        if _candidate_exists(cid):
            print(f"[seed] 候选 {cid} 已存在，跳过创建")
        else:
            agent.candidate_store.save(CandidateRecord(
                candidate_id=cid,
                candidate_type=meta["candidate_type"],
                name=meta["name"],
                smiles=meta["smiles"],
                source=meta["source"],
                data={"formula": meta["formula"]},
                status=meta["status"],
            ))
            created_candidates += 1
            print(f"[seed] 已创建候选 {cid}（{meta['name']}，状态 {meta['status']}）")

        # 关联一份工艺方案（使深化流水线展示 route / status）
        process_id = f"SEED_PROC_{cid.split('_')[-1]}"
        existing = app.state.process_scheme_store.list_by_candidate(cid)
        if existing:
            print(f"[seed] 候选 {cid} 已有工艺方案，跳过")
        else:
            app.state.process_scheme_store.create(ProcessScheme(
                process_id=process_id,
                candidate_id=cid,
                status="confirmed",
                owner="seed_demo",
                routes=[{
                    "route_id": "R1",
                    "name": f"{meta['name']} 直接合成路线",
                    "steps": ["原料混合", "高温烧结", "退火"],
                    "score": 0.85,
                }],
                evidence_refs=[{
                    "capability": "process_deepening",
                    "source": "seed_demo",
                    "detail": "示例工艺方案（种子数据）",
                }],
            ))
            print(f"[seed] 已为候选 {cid} 创建工艺方案 {process_id}")

        # 创建实验任务单（关联候选）
        order = agent.experiment_controller.create_order(
            ExperimentOrder(
                candidate_id=cid,
                project_id="",
                scenario_id="",
                assignee="seed_demo",
                notes="种子数据：端到端闭环演示实验单",
            )
        )
        created_orders += 1
        print(f"[seed] 已创建实验单 {order.order_id}（候选 {cid}）")

        # 写入实验结果（自动联动创建样品，样品经实验单反查候选）
        for r in DEMO_RESULTS[cid]:
            req = ExperimentResultManualRequest(
                experiment_order_id=order.order_id,
                sample_id=f"SEED_SMP_{cid.split('_')[-1]}",
                property_name=r["property_name"],
                value=r["value"],
                unit=r["unit"],
                test_method=r["test_method"],
                uploaded_by="seed_demo",
                data_quality="literature",
            )
            record = _save_single_result_record(req)
            created_results += 1
            print(f"[seed] 已写入结果 {record.result_id}：{r['property_name']}={r['value']}{r['unit']}")

    after = _count_results()
    print("\n[seed] 完成汇总：")
    print(f"[seed]   新增候选：{created_candidates}")
    print(f"[seed]   新增实验单：{created_orders}")
    print(f"[seed]   新增实验结果：{created_results}")
    print(f"[seed]   experiment_result_records 记录数：{before} -> {after}")
    if after >= 1:
        print("[seed] ✅ ECML 闭环前置条件已满足（至少 1 条实验数据）。")
    else:
        print("[seed] ⚠️ 实验结果写入失败，请检查上方日志。")
        sys.exit(1)


if __name__ == "__main__":
    main()