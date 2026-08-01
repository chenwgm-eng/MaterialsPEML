"""现有功能回归冒烟测试。

验证业务链路 MDM 改造未破坏现有功能：
- 项目列表/详情查询
- 候选材料列表查询
- 实验任务单列表查询
- 样品列表查询
- ECML runs 列表查询
- 健康检查、工具列表等基础接口

只读操作，不创建任何数据，安全可重复执行。
"""

from __future__ import annotations

import argparse
import sys
import requests


def _check(name: str, ok: bool, detail: str = "") -> bool:
    mark = "[OK]  " if ok else "[FAIL]"
    print(f"{mark} {name} — {detail}")
    return ok


def main():
    parser = argparse.ArgumentParser(description="现有功能回归冒烟测试")
    parser.add_argument("--base-url", default="http://localhost:8000")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    print("=== 现有功能回归冒烟测试 ===")
    print(f"后端: {base}\n")

    results: list[bool] = []

    # 1. 基础接口
    try:
        r = requests.get(f"{base}/health", timeout=5)
        results.append(_check("GET /health", r.status_code == 200, f"HTTP {r.status_code}"))
    except Exception as e:
        results.append(_check("GET /health", False, f"异常: {e}"))

    try:
        r = requests.get(f"{base}/tools", timeout=5)
        ok = r.status_code == 200 and "tools" in r.json()
        results.append(_check("GET /tools", ok, f"HTTP {r.status_code}"))
    except Exception as e:
        results.append(_check("GET /tools", False, f"异常: {e}"))

    # 2. 项目相关（含改造后的 stage-status）
    try:
        r = requests.get(f"{base}/projects", timeout=10)
        ok = r.status_code == 200 and isinstance(r.json(), list)
        n = len(r.json()) if ok else 0
        results.append(_check("GET /projects", ok, f"HTTP {r.status_code}, 项目数={n}"))
        projects = r.json() if ok else []
    except Exception as e:
        results.append(_check("GET /projects", False, f"异常: {e}"))
        projects = []

    if projects:
        pid = projects[0].get("project_id")
        # GET /projects/{id}/tasks（改造后查关系表）
        try:
            r = requests.get(f"{base}/projects/{pid}/tasks", timeout=10)
            ok = r.status_code == 200 and isinstance(r.json(), list)
            n = len(r.json()) if ok else 0
            results.append(_check(
                "GET /projects/{id}/tasks", ok,
                f"HTTP {r.status_code}, 任务数={n}",
            ))
        except Exception as e:
            results.append(_check("GET /projects/{id}/tasks", False, f"异常: {e}"))

        # GET /projects/{id}/stage-status（改造后按 task 维度返回）
        try:
            r = requests.get(f"{base}/projects/{pid}/stage-status", timeout=10)
            ok = r.status_code == 200 and "tasks" in r.json()
            body = r.json() if ok else {}
            n = len(body.get("tasks") or [])
            results.append(_check(
                "GET /projects/{id}/stage-status", ok,
                f"HTTP {r.status_code}, tasks 数={n}",
            ))
        except Exception as e:
            results.append(_check("GET /projects/{id}/stage-status", False, f"异常: {e}"))

        # GET /projects/{id}/progress
        try:
            r = requests.get(f"{base}/projects/{pid}/progress", timeout=10)
            ok = r.status_code == 200
            results.append(_check(
                "GET /projects/{id}/progress", ok, f"HTTP {r.status_code}",
            ))
        except Exception as e:
            results.append(_check("GET /projects/{id}/progress", False, f"异常: {e}"))

    # 3. 候选材料列表（返回 dict: {"candidates": [...], "count": N}）
    try:
        r = requests.get(f"{base}/candidates", timeout=10)
        if r.status_code != 200:
            results.append(_check("GET /candidates", False, f"HTTP {r.status_code}"))
        else:
            body = r.json()
            cands = body.get("candidates") if isinstance(body, dict) else body
            ok = isinstance(cands, list)
            n = len(cands) if ok else 0
            results.append(_check("GET /candidates", ok, f"HTTP {r.status_code}, 候选数={n}"))
    except Exception as e:
        results.append(_check("GET /candidates", False, f"异常: {e}"))

    # 4. 实验任务单列表
    try:
        r = requests.get(f"{base}/experiments/orders", timeout=10)
        ok = r.status_code == 200 and isinstance(r.json(), list)
        n = len(r.json()) if ok else 0
        results.append(_check(
            "GET /experiments/orders", ok, f"HTTP {r.status_code}, 订单数={n}",
        ))
    except Exception as e:
        results.append(_check("GET /experiments/orders", False, f"异常: {e}"))

    # 5. 样品列表
    try:
        r = requests.get(f"{base}/samples", timeout=10)
        ok = r.status_code == 200 and isinstance(r.json(), list)
        n = len(r.json()) if ok else 0
        results.append(_check("GET /samples", ok, f"HTTP {r.status_code}, 样品数={n}"))
    except Exception as e:
        results.append(_check("GET /samples", False, f"异常: {e}"))

    # 6. BOM 列表（无项目 ID 也能调，返回空或全量）
    try:
        r = requests.get(f"{base}/projects/nonexistent-id/tasks", timeout=10)
        # 404 是预期（项目不存在），200 也是预期（空列表）
        ok = r.status_code in (200, 404)
        results.append(_check(
            "GET /projects/{不存在}/tasks (404预期)", ok, f"HTTP {r.status_code}",
        ))
    except Exception as e:
        results.append(_check("GET /projects/{不存在}/tasks", False, f"异常: {e}"))

    # 7. ECML runs 列表
    try:
        r = requests.get(f"{base}/ecml/runs?limit=5", timeout=10)
        ok = r.status_code == 200
        results.append(_check("GET /ecml/runs", ok, f"HTTP {r.status_code}"))
    except Exception as e:
        results.append(_check("GET /ecml/runs", False, f"异常: {e}"))

    # 汇总
    print(f"\n=== 回归汇总 ===")
    passed = sum(1 for r in results if r)
    total = len(results)
    print(f"通过: {passed}/{total}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
