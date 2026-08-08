"""GNoME 完整稳定集导入脚本（一次性运维任务，导出真实数据到统一 PostgreSQL）。

用法：
    python scripts/import_gnome.py --input path/to/gnome.csv [--limit 0]

--input 支持 CSV 或 JSON（list[dict]）。字段名兼容常见 GNoME 导出：
    material_id, formula, space_group / spacegroup, structure_type,
    energy_above_hull / e_above_hull, band_gap, formation_energy / formation_energy_per_atom,
    ionic_conductivity

--limit 0 表示全量导入（默认 0）。导入走 gnome.gnome_materials 表 + 索引。
"""
from __future__ import annotations

import argparse
import ast
import csv
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from battery_materials_agent.generation.formula_utils import (  # noqa: E402
    extract_elements,
    normalize_formula,
)
from battery_materials_agent.generation.gnome_store import GnomeMaterialStore  # noqa: E402


# 官方 GNoME stable_materials_summary.csv 表头 → 规范化键 的别名映射（大小写/空格不敏感）
_HEADER_ALIASES: dict[str, str] = {
    "materialid": "material_id",
    "id": "material_id",
    "reduced formula": "reduced_formula",
    "composition": "formula",
    "formula": "formula",
    "pretty_formula": "formula",
    "space group": "space_group",
    "spacegroup": "space_group",
    "crystal system": "structure_type",
    "structure_type": "structure_type",
    "decomposition energy per atom": "energy_above_hull",
    "energy_above_hull": "energy_above_hull",
    "e_above_hull": "energy_above_hull",
    "bandgap": "band_gap",
    "band_gap": "band_gap",
    "formation energy per atom": "formation_energy",
    "formation_energy": "formation_energy",
    "formation_energy_per_atom": "formation_energy",
    "elements": "elements",
    "ionic_conductivity": "ionic_conductivity",
}


def _normalize_row(row: dict) -> dict:
    """把任意大小写/空格风格的表头映射到规范化键（GNoME 官方 CSV 兼容）。"""
    out: dict[str, str] = {}
    for k, v in row.items():
        canon = _HEADER_ALIASES.get(str(k).strip().lower(), str(k).strip().lower())
        if canon not in out:
            out[canon] = v
    return out


def _row_to_record(row: dict) -> dict:
    row = _normalize_row(row)
    # 优先用归一化化学式（Reduced Formula），否则用完整组成（Composition）
    formula = (row.get("reduced_formula") or row.get("formula") or "").strip()
    material_id = str(row.get("material_id") or "").strip()
    space_group = str(row.get("space_group") or "").strip()
    structure_type = str(row.get("structure_type") or "").strip()

    def _f(*keys) -> float | None:
        """解析数值字段；缺失/不可解析返回 None（NULL），不伪造 0。

        0 是真实物理值（如带隙 0 = 金属），与"未测得"语义不同，必须区分。
        """
        for k in keys:
            v = row.get(k)
            if v is not None and str(v).strip() not in ("", "None", "nan"):
                try:
                    return float(v)
                except (TypeError, ValueError):
                    continue
        return None

    # 元素集合：官方 GNoME CSV 的 Elements 列是 Python 列表 repr（如 "['S','Zr','Cs']"），
    # 需用 ast.literal_eval 解析；失败时回退到按分隔符拆分，再回退到化学式解析
    elements_raw = str(row.get("elements") or "").strip()
    elements: list[str] = []
    if elements_raw and elements_raw.lower() not in ("", "none", "nan"):
        try:
            parsed = ast.literal_eval(elements_raw)
            if isinstance(parsed, (list, tuple, set)):
                elements = sorted(str(e) for e in parsed if e)
        except (ValueError, SyntaxError):
            elements = sorted(
                e.strip() for e in elements_raw.replace("/", "-").split("-") if e.strip()
            )
    if not elements:
        elements = sorted(extract_elements(formula)) if formula else []

    return {
        "formula": formula,
        "reduced_formula": normalize_formula(formula) if formula else "",
        "space_group": space_group,
        "structure_type": structure_type,
        "energy_above_hull": _f("energy_above_hull", "e_above_hull"),
        "band_gap": _f("band_gap"),
        "formation_energy": _f("formation_energy", "formation_energy_per_atom"),
        "material_id": material_id,
        "ionic_conductivity": _f("ionic_conductivity"),
        "elements": elements,
        "source": "gnome",
    }


def load_rows(path: Path, limit: int):
    rows: list[dict] = []
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        items = data if isinstance(data, list) else data.get("data", [])
    else:
        with open(path, newline="", encoding="utf-8") as f:
            items = list(csv.DictReader(f))

    for it in items:
        rows.append(_row_to_record(it))
        if limit and len(rows) >= limit:
            break
    return rows


# 官方 GNoME 公开数据（Google Cloud 公共存储桶）稳定材料摘要
GNOME_CSV_URL = (
    "https://storage.googleapis.com/gdm_materials_discovery/"
    "gnome_data/stable_materials_summary.csv"
)


def download_csv(dest: Path) -> Path:
    """从官方公共存储桶下载 stable_materials_summary.csv（约 38 万行）。"""
    import requests

    print(f"[INFO] 下载官方 GNoME 稳定材料摘要: {GNOME_CSV_URL}")
    resp = requests.get(GNOME_CSV_URL, stream=True, timeout=120)
    resp.raise_for_status()
    dest.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    with open(dest, "wb") as f:
        for chunk in resp.iter_content(chunk_size=1 << 20):
            f.write(chunk)
            total += len(chunk)
    print(f"[INFO] 已下载 {total / 1024 / 1024:.1f} MB → {dest}")
    return dest


def main() -> int:
    parser = argparse.ArgumentParser(description="导入 GNoME 稳定集到统一 PostgreSQL")
    parser.add_argument("--input", help="GNoME 导出 CSV/JSON 路径")
    parser.add_argument("--download", action="store_true",
                        help="从官方 Google Cloud 公共桶下载 stable_materials_summary.csv")
    parser.add_argument("--limit", type=int, default=0, help="最大导入条数（0=全量）")
    args = parser.parse_args()

    if args.download:
        path = download_csv(Path("data/gnome/stable_materials_summary.csv"))
    else:
        if not args.input:
            parser.error("必须提供 --input 或 --download")
        path = Path(args.input)

    if not path.exists():
        print(f"[ERROR] 输入文件不存在: {path}")
        return 2

    rows = load_rows(path, args.limit)
    if not rows:
        print("[ERROR] 未解析到任何 GNoME 记录")
        return 2

    store = GnomeMaterialStore()
    inserted = store.bulk_insert(rows)
    total = store.count()
    print(f"[INFO] 解析 {len(rows)} 条，实际插入 {inserted} 条（重复跳过），"
          f"库内现有 {total} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())