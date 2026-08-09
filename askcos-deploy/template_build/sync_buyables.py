"""buyables 双来源管理：ASKCOS 标准平文件 + 企业物料库运行时实时查询。

背景与来源划分：
  * **ASKCOS 标准平文件**（/usr/local/ASKCOS/makeit/data/buyables/buyables.json.gz）
    是 ASKCOS 自带的商业可购集合，本脚本将其视为“标准 buyables”，不再写入企业物料。
  * **企业物料库**（PostgreSQL industrialization.raw_materials）是运行时来源，
    Pricer 在查询时**先查企业物料库（实时读 PG，TTL 缓存），未命中再回退 ASKCOS 标准平文件**。
    由于是运行时实时查询，企业物料库的**动态更新无需重建平文件或重启容器**即自动生效。

本脚本职责（不再把企业物料合并进平文件）：
  1. 校验企业物料库连通，并报告可获取物料数（带 SMILES 的物料即视为可购买）；
  2. 清理平文件中历史遗留的 enterprise-material-library 残留条目，确保平文件保持纯 ASKCOS 标准；
  3. 可选重启 TB 协调器/工作进程，使改动生效。

用法：
    python sync_buyables.py [--container tb_coordinator_mcts] [--ppg 1.0]

说明：
  * 企业物料 ppg 默认取 1.0（仅用于 buyable 判定，保证“库中有即可得”）。
    细粒度成本由应用层 estimate_cost 负责，不在 Pricer 中建模。
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import subprocess
import sys

# 允许从仓库根目录导入 battery_materials_agent
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# 单一事实来源：EXCLUDE_SMILES 与 SMILES 规范化（与容器内 Pricer 共用）
_BUYABLE_PATCH_DIR = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "custom", "patches", "makeit", "utilities", "buyable"))
if _BUYABLE_PATCH_DIR not in sys.path:
    sys.path.insert(0, _BUYABLE_PATCH_DIR)

from sqlalchemy import text  # noqa: E402

from battery_materials_agent.db import get_engine  # noqa: E402
from buyables_exclusions import EXCLUDE_SMILES, canonical_smiles  # noqa: E402

# 容器内 buyables 平文件路径
CONTAINER_BUYABLES = "/usr/local/ASKCOS/makeit/data/buyables/buyables.json.gz"


def _find_container(name_part: str) -> str | None:
    """按名字片段定位运行中的容器。"""
    out = subprocess.run(
        ["docker", "ps", "--format", "{{.Names}}"],
        check=True, capture_output=True, text=True,
    ).stdout.splitlines()
    for name in out:
        if name_part in name:
            return name
    return None


def _read_container_buyables(container: str) -> list[dict]:
    """从容器拉取 buyables 平文件内容。"""
    tmp = os.path.join(os.path.dirname(__file__), "_buyables.sync.json.gz")
    subprocess.run(
        ["docker", "cp", f"{container}:{CONTAINER_BUYABLES}", tmp],
        check=True,
    )
    try:
        with gzip.open(tmp, "rb") as f:
            return json.loads(f.read().decode("utf-8"))
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def _write_container_buyables(container: str, prices: list[dict]) -> None:
    tmp = os.path.join(os.path.dirname(__file__), "_buyables.sync.json.gz")
    with gzip.open(tmp, "wb") as f:
        f.write(json.dumps(prices).encode("utf-8"))
    try:
        subprocess.run(
            ["docker", "cp", tmp, f"{container}:{CONTAINER_BUYABLES}"],
            check=True,
        )
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def enterprise_material_count() -> int:
    """返回企业物料库中带合法 SMILES 的物料数（即运行时视为可购买的物料数）。"""
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT material_id, name, smiles FROM industrialization.raw_materials "
                "WHERE smiles IS NOT NULL AND length(trim(smiles)) > 0"
            )
        ).fetchall()
    count = 0
    for mid, name, smiles in rows:
        smi = canonical_smiles(str(smiles).strip())
        if smi and smi not in EXCLUDE_SMILES:
            count += 1
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--container", default="tb_coordinator_mcts",
                        help="承载 buyables 平文件的容器名片段（默认 tb_coordinator_mcts）")
    parser.add_argument("--ppg", type=float, default=1.0,
                        help="企业物料的 buyable 价格（默认 1.0，仅用于 buyable 判定）")
    parser.add_argument("--restart", action="store_true", default=True,
                        help="清理后重启 TB 协调器/工作进程使生效（默认开启）")
    args = parser.parse_args()

    # 1. 校验企业物料库连通（运行时来源，动态更新自动生效）
    try:
        n = enterprise_material_count()
        print("[OK] 企业物料库可获取物料数: {}（运行时 Pricer 实时查询，动态更新自动生效）".format(n))
        print("[OK] 企业物料 ppg: {}（仅用于 buyable 判定）".format(args.ppg))
    except Exception as e:
        print("[FAIL] 无法连接企业物料库: {}".format(e))
        print("[WARN] 运行时将仅使用 ASKCOS 标准平文件（企业库不可达时自动回退）")
        return 1

    container = _find_container(args.container)
    if container is None:
        print("[FAIL] 未找到容器（片段 {}）。请确认 ASKCOS 已启动。".format(args.container))
        return 1

    # 2. 清理平文件中的企业物料残留，恢复纯 ASKCOS 标准
    current = _read_container_buyables(container)
    kept = []
    removed = 0
    for p in current:
        if p.get("source") == "enterprise-material-library":
            removed += 1
            continue
        p.pop("source", None)
        # 剔除历史注入的人工单-NCO 中间体
        if p.get("smiles", "") in EXCLUDE_SMILES:
            removed += 1
            continue
        kept.append(p)
    print("[OK] 平文件条目: {} → {}（移除企业物料残留/人工单-NCO {} 条）".format(
        len(current), len(kept), removed))

    if removed:
        _write_container_buyables(container, kept)
        print("[OK] 已写回 {}:{}{}".format(container, CONTAINER_BUYABLES,
                                            "（纯 ASKCOS 标准，企业物料由运行时实时提供）"))

    if args.restart:
        targets = []
        for part in ("tb_coordinator_mcts", "tb_c_worker_preload", "tb_c_worker"):
            c = _find_container(part)
            if c:
                targets.append(c)
        if targets:
            subprocess.run(["docker", "restart"] + targets, check=True)
            print("[OK] 已重启: {}".format(", ".join(targets)))
        else:
            print("[WARN] 未找到 TB 容器，跳过重启（改动需手动重启生效）")
    return 0


if __name__ == "__main__":
    sys.exit(main())