"""Enrich the USPTO-derived retro template collection with hand-curated public-domain
templates for functional groups that USPTO/RDChiral under-represents.

Targeted gaps (confirmed by E2E for 金发/华峰 R&D scenarios):
  * isocyanate synthesis (phosgenation: amine + phosgene -> isocyanate)  -> MDI/HDI
  * tetrahydrofuran (THF) from 1,4-butanediol dehydration                  -> PTMG unit

These are industrial-process reactions that are rare / hard to atom-map in patent
data, so generic templates are missing from the extracted set. The curated rules
below are textbook public-domain organic chemistry, tagged with the same
template_set label the treebuilder queries, and injected with a high `count` so the
local reaction-frequency ranking surfaces them.

Usage:
    python enrich_templates.py [--collection retro_templates_commercial] [--apply-existing]

    --apply-existing  只用代码中的定义对 mongo 中已存在的 curated 模板做对账
                      （更新 count/necessary_reagent），不插入重复文档。
                      默认（无该参数）行为保持不变：校验后追加导入新文档。

说明：count 与 necessary_reagent 以本文件为唯一事实来源（single source of truth），
不再通过临时 mongo 脚本（_set_reagent.js / _bump_count*.js）手工修改。
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

from rdkit import Chem
from rdkit.Chem import AllChem

DEFAULT_COLLECTION = "retro_templates_commercial"
DEFAULT_CONTAINER = "askcos-deploy-mongo-1"
MONGO_HOST = "mongo"
MONGO_USER = "askcos"
MONGO_PW = "askcos"
MONGO_DB = "askcos"

# 高频计数：本地 heuristic 按 count 降序取模板，高 count 保证这些规则被选中。
# 取 100000000 远高于绝大多数 USPTO 模板，稳定进入 top-N（与线上库中 curated 值一致）。
CURATED_COUNT = 100000000

# (业务说明, retro_rule, 验证目标 SMILES, necessary_reagent)
# necessary_reagent 是必要共反应物（无机副产物），用于解释模板两侧原子数差异：
#   * 光气化：R-NCO -> R-NH2 + COCl2，正向反应 RNH2 + COCl2 -> RNCO + 2 HCl，
#     共反应物为 2 分子 HCl（提供产物侧 2 Cl + 2 H），故记 'HCl.HCl'。
#   * THF 脱水：BDO -> THF + H2O，共反应物为 1 分子 H2O，故记 'O'。
CURATED_TEMPLATES = [
    (
        "光气化：异氰酸酯 -> 胺 + 光气(COCl2)  [MDI/HDI 原料路线]",
        "[#6:1][N;H0;D2:2]=[C;H0;D2:3]=[O;H0;D1:4]"
        ">>[#6:1][NH2;D1:2].O=[C;H0;D3:3](Cl)Cl",
        "O=C=NC1=CC=C(C=C1)CC2=CC=C(C=C2)N=C=O",  # MDI
        "HCl.HCl",
    ),
    (
        "THF -> 1,4-丁二醇(脱水逆反应)  [PTMG 单元路线]",
        # 产物侧 O 原子是丁二醇的羟基氧（H1/D1），而非环醚氧（H0/D2）。
        # 与线上库中已 seed 的正确模板保持一致，避免 --apply-existing 因 SMARTS
        # 不一致而新建缺 index 的孤儿文档。
        "[O;H0;D2:1]1[CH2:2][CH2:3][CH2:4][CH2:5]1"
        ">>[O;H1;D1:1][CH2:2][CH2:3][CH2:4][CH2:5][OH]",
        "C1CCOC1",  # THF
        "O",
    ),
]


def _validate_rule(rule: str, verify_smiles: str) -> list[str]:
    """Return a list of error strings; empty means the rule is usable."""
    errors = []
    if ">>" not in rule:
        errors.append("missing '>>' separator")
    try:
        rxn = AllChem.ReactionFromSmarts(rule)
    except Exception as exc:
        return [f"parse error: {exc}"]
    if rxn is None:
        return ["unparseable reaction SMARTS"]
    if rxn.GetNumReactantTemplates() == 0 or rxn.GetNumProductTemplates() == 0:
        errors.append("must have both reactant and product side")
    mol = Chem.MolFromSmiles(verify_smiles)
    if mol is None:
        errors.append(f"verify target unparseable: {verify_smiles}")
    else:
        products = rxn.RunReactants((mol,))
        if not products:
            errors.append(f"rule does not match verify target {verify_smiles}")
    return errors


def _max_index(container: str, collection: str) -> int:
    cmd = [
        "docker", "exec", container, "mongo",
        "--host", MONGO_HOST, "--username", MONGO_USER, "--password", MONGO_PW,
        "--authenticationDatabase", "admin", "--quiet", MONGO_DB,
        "--eval",
        f"const r=db.{collection}.aggregate([{{$group:{{_id:null,m:{{$max:'$index'}}}}}}]).toArray();"
        f"print(r.length?r[0].m:-1)",
    ]
    out = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return int(out.stdout.strip())


def _import_docs(container: str, collection: str, docs_path: str) -> None:
    name = docs_path.split("\\")[-1].split("/")[-1]
    dst = f"/tmp/{name}"
    subprocess.run(["docker", "cp", docs_path, f"{container}:{dst}"], check=True)
    cmd = [
        "docker", "exec", container, "bash", "-c",
        "mongoimport --host {} --username {} --password {} "
        "--authenticationDatabase admin --db {} --collection {} "
        "--type json --jsonArray --file {}".format(
            MONGO_HOST, MONGO_USER, MONGO_PW, MONGO_DB, collection, dst),
    ]
    subprocess.run(cmd, check=True)


def _apply_existing(container: str, collection: str) -> None:
    """用代码中的定义对 mongo 中已有的 curated 模板做对账（更新而非重复插入）。

    以 reaction_smarts 精确匹配：命中的更新 count / necessary_reagent / note（保留原 index）；
    未命中的（如全新添加的规则）则插入，并补齐 index / template_set 等字段，避免产生
    缺 index 的孤儿文档（缺 index 会导致 tb_c_worker 的按频率排序崩溃）。
    幂等，可重复执行。

    实现说明：把 JS 写入临时文件再 docker cp 进容器，用 `mongo <file>` 执行，
    避免 `bash -c "--eval"` 对 `$set` 等 shell 元字符的展开导致语法错误。
    """
    rules = []
    for note, rule, verify, reagent in CURATED_TEMPLATES:
        rules.append({
            "note": note,
            "reaction_smarts": rule,
            "verify_smiles": verify,
            "count": CURATED_COUNT,
            "necessary_reagent": reagent,
        })
    js_lines = [
        # 先取当前集合最大 index，命中时不覆盖、仅插入未命中规则时递增分配。
        "const r = db.{c}.aggregate([{{$group:{{_id:null, m:{{$max:'$index'}}}}}}]).toArray();".format(c=collection),
        "let nextIndex = (r.length ? r[0].m : -1) + 1;",
    ]
    for r in rules:
        js_lines.append(
            "db.{c}.updateOne(\n"
            "  {{ reaction_smarts: {rule!r} }},\n"
            "  {{ $set: {{ count: {count}, necessary_reagent: {reagent!r}, note: {note!r} }},\n"
            "     $setOnInsert: {{ index: nextIndex++, template_set: 'reaxys', smiles: {verify!r},\n"
            "       retro_rule: {rule!r}, selector_id: 0, template_relevance_id: 0,\n"
            "       provenance: 'curated-public-domain' }} }},\n"
            "  {{ upsert: true }}\n"
            ");".format(
                c=collection,
                rule=r["reaction_smarts"],
                count=r["count"],
                reagent=r["necessary_reagent"],
                note=r["note"],
                verify=r["verify_smiles"],
            )
        )
    js = "\n".join(js_lines)
    local = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_apply_existing.js")
    with open(local, "w", encoding="utf-8") as fh:
        fh.write(js)
    try:
        dst = "/tmp/_apply_existing.js"
        subprocess.run(["docker", "cp", local, f"{container}:{dst}"], check=True)
        cmd = [
            "docker", "exec", container, "bash", "-c",
            "mongo --host {} --username {} --password {} --authenticationDatabase admin --quiet {} {}".format(
                MONGO_HOST, MONGO_USER, MONGO_PW, MONGO_DB, dst),
        ]
        subprocess.run(cmd, check=True)
    finally:
        if os.path.exists(local):
            os.remove(local)
    print("Reconciled {} curated template(s) into {}.{}".format(len(rules), MONGO_DB, collection))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collection", default=DEFAULT_COLLECTION)
    parser.add_argument("--container", default=DEFAULT_CONTAINER)
    parser.add_argument("--out", default="curated_templates.json")
    parser.add_argument("--import-only", action="store_true",
                        help="skip RDKit validation, only import the JSON")
    parser.add_argument("--apply-existing", action="store_true",
                        help="reconcile count/necessary_reagent on existing curated docs instead of importing")
    args = parser.parse_args()

    if args.apply_existing:
        _apply_existing(args.container, args.collection)
        return 0

    start_index = _max_index(args.container, args.collection) + 1
    docs = []
    for i, (note, rule, verify, reagent) in enumerate(CURATED_TEMPLATES):
        if not args.import_only:
            errs = _validate_rule(rule, verify)
            if errs:
                print(f"[FAIL] {note}: {'; '.join(errs)}")
                return 1
            print(f"[OK]   {note}")
        docs.append({
            "index": start_index + i,
            "smiles": verify,
            "reaction_smarts": rule,
            "retro_rule": rule,
            "count": CURATED_COUNT,
            "necessary_reagent": reagent,
            "selector_id": 0,
            "template_relevance_id": 0,
            "template_set": "reaxys",
            "provenance": "curated-public-domain",
            "note": note,
        })

    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(docs, fh)
    print(f"Wrote {len(docs)} curated template(s) -> {args.out} (indices {start_index}..{start_index + len(docs) - 1})")

    _import_docs(args.container, args.collection, args.out)
    print(f"Imported into {MONGO_DB}.{args.collection}")
    return 0


if __name__ == "__main__":
    sys.exit(main())