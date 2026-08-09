"""针对企业物料库的端到端验证：
1. 直连 nginx/treebuilder API，验证一个企业特有物料（LiTFSI 锂盐）作为目标能返回路线树；
2. 验证企业特有高分子（PVDF）被 MCTS 判定为可购（不再需要平文件）；
3. 验证 ASKCOS 标准买得的常见分子仍可购（回退正常）。
"""
import json, time, urllib.parse, urllib.request

def call_treebuilder(smiles, depth=3):
    qs = urllib.parse.urlencode({
        "smiles": smiles, "max_depth": depth, "max_branching": 20,
        "expansion_time": 120, "template_count": 200, "max_cum_prob": 0.999,
        "max_ppg": 10, "filter_threshold": 0, "return_first": "True",
    })
    url = "http://localhost:5000/api/treebuilder/?" + qs
    start = time.time()
    with urllib.request.urlopen(url, timeout=400) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data, round(time.time() - start, 1)

def collect_leaves(tree):
    leaves, chems = [], []
    def walk(n):
        if n.get("is_chemical"):
            chems.append(n.get("smiles",""))
            if not n.get("children"):
                leaves.append({"smiles": n.get("smiles",""), "ppg": n.get("ppg")})
                return
        for c in (n.get("children") or []):
            walk(c)
    walk(tree)
    return leaves, chems

# Enterprise-only materials (not in standard ASKCOS flat file)
ENTERPRISE = {
    "LiTFSI": "C(F)(F)(F)S(=O)(=O)[N-]S(=O)(=O)C(F)(F)(F).[Li+]",
    "PVDF": "C(C(F)(F)C(F)(F)[*])[*]",
    "PEO": "C(COCCO[*])[*]",
}
# Standard buyable (should still resolve via flat file fallback)
STANDARD = {
    "ethanol": "CCO",
    "THF": "C1CCOC1",
}

def main():
    print("="*90)
    print("端到端：企业物料库 buyable 来源验证")
    print("="*90)
    for label, smi in {**ENTERPRISE, **STANDARD}.items():
        try:
            data, elapsed = call_treebuilder(smi)
        except Exception as e:
            print("[FAIL] {} 调用出错: {}: {}".format(label, type(e).__name__, e))
            continue
        trees = data.get("trees", [])
        print("\n### {}  SMILES={}".format(label, smi))
        print("elapsed={}s  status={}  trees={}".format(elapsed, data.get("status"), len(trees)))
        if not trees:
            print("   [--] 无路线树（可能该分子本身过小/直接可购）")
            continue
        leaves, chems = collect_leaves(trees[0])
        buyable = [l for l in leaves if l.get("ppg")]
        notbuy = [l for l in leaves if not l.get("ppg")]
        print("   叶子数={} 可购={} 不可购={}".format(len(leaves), len(buyable), len(notbuy)))
        print("   可购叶子样例:", [l["smiles"] for l in buyable[:5]])
        if notbuy:
            print("   不可购叶子样例:", [l["smiles"] for l in notbuy[:5]])

if __name__ == "__main__":
    main()