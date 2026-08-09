"""E2E 验收测试：金发科技 / 华峰新材料 核心研发业务分子逆合成覆盖度测试。

针对两家的主营研发场景选取代表性单体/中间体，调用本地 USPTO 模板 ASKCOS
treebuilder API，验证是否都能给出可用的多步逆合成路线。

- 金发科技：改性塑料、聚酯(PBT)、聚碳酸酯(PC)、可降解塑料(PBAT/PLA)、PA
- 华峰新材料：聚氨酯(异氰酸酯/多元醇)、PA66(己二酸/己二胺)、己内酰胺

template_count 按搜索深度动态调大（深度<=3 取 200，深度>3 取 500），以覆盖
电池/高分子材料相关的低频模板（全局频率排序会把低频模板挤出 top-50）。
"""

from __future__ import annotations

import json
import time
import urllib.request

# 本地 USPTO ASKCOS treebuilder 端点（nginx: 5000 -> app）
_API = "http://localhost:5000/api/treebuilder/"

# 目标用户研发场景清单：(企业, 业务背景, 分子名, SMILES, 期望深度)
CASES = [
    # ---- 金发科技 ----
    ("金发", "聚酯/PBT 单体", "对苯二甲酸二甲酯 DMT",
     "COC(=O)c1ccc(cc1)C(=O)OC", 4),
    ("金发", "聚酯/PBT 单体", "1,4-丁二醇 BDO", "OCCCCO", 3),
    ("金发", "聚碳酸酯单体", "双酚A", "CC(C)(C1=CC=C(O)C=C1)C2=CC=C(O)C=C2", 4),
    ("金发", "聚碳酸酯单体", "碳酸二苯酯", "O=C(Oc1ccccc1)Oc1ccccc1", 4),
    ("金发", "可降解塑料 PLA", "乳酸", "CC(O)C(=O)O", 3),
    ("金发", "可降解塑料 PBAT", "丁二酸", "OC(=O)CCC(=O)O", 3),
    ("金发", "改性 PA", "己内酰胺", "O=C1CCCCCN1", 4),
    # ---- 华峰新材料 ----
    ("华峰", "聚氨酯原料", "MDI(二苯甲烷二异氰酸酯)",
     "O=C=NC1=CC=C(C=C1)CC2=CC=C(C=C2)N=C=O", 4),
    ("华峰", "聚氨酯原料", "HDI(己二异氰酸酯)", "O=C=NCCCCCCN=C=O", 4),
    ("华峰", "PA66 单体", "己二酸", "OC(=O)CCCCC(=O)O", 3),
    ("华峰", "PA66 单体", "己二胺", "NCCCCCCN", 3),
    ("华峰", "聚氨酯/PTMG 中间体", "四氢呋喃 THF", "C1CCOC1", 3),
    ("华峰", "聚氨酯/聚己内酯", "ε-己内酯", "O=C1CCCCCO1", 4),
    ("华峰", "聚氨酯多元醇单体", "乙二醇", "OCCO", 3),
]


def get_templates(search_depth: int) -> int:
    """按搜索深度动态调大 template_count，保证低频业务模板不被挤出。"""
    return 500 if search_depth > 3 else 200


def call_treebuilder(smiles: str, depth: int) -> dict:
    tcount = get_templates(depth)
    url = (
        f"{_API}?smiles={urllib.parse.quote(smiles)}"
        f"&max_depth={depth}&max_branching=20&expansion_time=150"
        f"&template_count={tcount}&max_cum_prob=0.999"
        f"&max_ppg=10&filter_threshold=0&return_first=True"
    )
    start = time.time()
    with urllib.request.urlopen(url, timeout=400) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    data["_elapsed"] = round(time.time() - start, 1)
    data["_tcount"] = tcount
    return data


def summarize(data: dict) -> dict:
    trees = data.get("trees", [])
    if not trees:
        return {"ok": False, "reason": "no_tree", "paths": 0, "elapsed": data.get("_elapsed")}
    # 递归收集叶子（前体）与路径
    leaves: list[str] = []
    paths = 0

    def walk(n, prefix):
        nonlocal paths
        if n.get("is_chemical"):
            leaves.append(n["smiles"])
        if not n.get("children"):
            if len(prefix) >= 1:
                paths += 1
            return
        for c in n.get("children", []):
            walk(c, prefix + [n["smiles"]])

    walk(trees[0], [])
    return {
        "ok": True,
        "reason": "tree",
        "root_children": sum(len(t.get("children", [])) for t in trees),
        "leaves": leaves[:8],
        "paths": paths,
        "elapsed": data.get("_elapsed"),
    }


def main() -> None:
    print("{:<4} {:<14} {:<28} {:<8} {:<6} {:<8} {}".format(
        "企业", "业务", "分子", "深度", "Tcount", "结果", "说明"))
    print("-" * 100)
    results = []
    for company, biz, name, smi, depth in CASES:
        tcount = get_templates(depth)
        try:
            data = call_treebuilder(smi, depth)
            s = summarize(data)
        except Exception as exc:  # 网络/超时
            s = {"ok": False, "reason": f"error:{type(exc).__name__}", "elapsed": "-", "tcount": tcount}
        note = ""
        if s["ok"]:
            note = "前体: " + ", ".join(s["leaves"]) if s["leaves"] else "树已生成(产物可购买/无叶子)"
        else:
            note = s.get("reason", "")
        print("{:<4} {:<14} {:<28} {:<8} {:<6} {:<8} {}".format(
            company, biz, name, depth, s.get("tcount", tcount),
            "OK" if s["ok"] else "--", note))
        results.append({"company": company, "biz": biz, "mol": name, "smiles": smi,
                        "ok": s["ok"], "note": note, "elapsed": s.get("elapsed")})
    # 汇总
    ok = sum(1 for r in results if r["ok"])
    print("-" * 100)
    print(f"通过 {ok}/{len(results)}  未通过: "
          + ", ".join(f"{r['mol']}({r['note']})" for r in results if not r["ok"]) or "无")


if __name__ == "__main__":
    import urllib.parse
    main()