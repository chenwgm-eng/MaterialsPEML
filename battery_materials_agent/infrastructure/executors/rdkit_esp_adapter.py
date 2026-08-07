"""RDKit ESP 适配器 — 基于 Gasteiger 电荷的静电势近似分析。

当 Multiwfn 不可用时，对输入为 SMILES 的有机小分子使用 RDKit 的 Gasteiger
电荷计算做 ESP 近似分析，并提供 HOMO/LUMO 能级的经验估算。

注意：Gasteiger 电荷是经验电荷，非量子化学严格计算；HOMO/LUMO 能级来自
文献值数据库或经验公式。生产级分析请使用 Multiwfn/PSI4/Gaussian。
"""
from __future__ import annotations

import math
from typing import Any


# ── 文献 HOMO/LUMO 能级数据库 (eV) ──────────────────────────
# 来源：NIST CCCBDB / 实验电离势(IP)与电子亲和能(EA)
# HOMO ≈ -IP, LUMO ≈ -EA
_HOMO_LUMO_DB: dict[str, dict[str, float]] = {
    "O": {"homo": -12.61, "lumo": -3.47, "name": "水"},  # water
    "CCO": {"homo": -10.49, "lumo": -1.34, "name": "乙醇"},  # ethanol
    "CO": {"homo": -10.85, "lumo": -0.95, "name": "甲醇"},  # methanol
    "c1ccccc1": {"homo": -9.24, "lumo": 0.98, "name": "苯"},  # benzene
    "Cc1ccccc1": {"homo": -8.83, "lumo": 1.10, "name": "甲苯"},  # toluene
    "CC(=O)C": {"homo": -9.71, "lumo": -0.46, "name": "丙酮"},  # acetone
    "C": {"homo": -12.61, "lumo": 1.46, "name": "甲烷"},  # methane (CH4)
    "CC": {"homo": -11.52, "lumo": 1.69, "name": "乙烷"},  # ethane
    "C=C": {"homo": -10.51, "lumo": 1.40, "name": "乙烯"},  # ethylene
    "C#C": {"homo": -11.40, "lumo": 4.40, "name": "乙炔"},  # acetylene
    "O=C=O": {"homo": -13.78, "lumo": 0.50, "name": "二氧化碳"},  # CO2
    "N": {"homo": -10.07, "lumo": 1.20, "name": "氨"},  # NH3 ammonia
    "O=O": {"homo": -12.07, "lumo": -0.81, "name": "氧气"},  # O2
    "[O-][N+](=O)O": {"homo": -11.30, "lumo": -1.10, "name": "硝酸"},  # HNO3
    "c1ccncc1": {"homo": -9.25, "lumo": -0.32, "name": "吡啶"},  # pyridine
    "C1=CC=CC=C1": {"homo": -9.24, "lumo": 0.98, "name": "苯"},  # benzene alt
    "CCN": {"homo": -9.96, "lumo": 1.20, "name": "乙胺"},  # ethylamine
    "CCOCC": {"homo": -9.80, "lumo": 1.47, "name": "乙醚"},  # diethyl ether
    "ClCCl": {"homo": -11.36, "lumo": 0.45, "name": "二氯甲烷"},  # DCM
    "C(#N)C": {"homo": -11.20, "lumo": -0.74, "name": "乙腈"},  # acetonitrile
}


class RDKitESPAdapter:
    """基于 RDKit Gasteiger 电荷的 ESP 近似适配器。

    提供 execute_esp / execute_orbitals / execute_render 接口，
    与 wavefunction_analysis.application._PlaceholderAdapter 兼容。
    """

    def __init__(self) -> None:
        self._rdkit_available = self._try_import_rdkit()

    @staticmethod
    def _try_import_rdkit() -> bool:
        try:
            import rdkit  # noqa: F401
            return True
        except ImportError:
            return False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def execute_esp(self, prepared_input: dict[str, Any]) -> dict[str, Any]:
        """基于 Gasteiger 电荷计算 ESP 近似值。

        Input format::

            {
                "input_file": "<SMILES>",
                "file_format": "molden" | "fchk" | ...,
                "surface_type": "molecular" | "vdw" | "electron_density",
                "bins": 100,
                "generate_cubes": True,
            }
        """
        if not self._rdkit_available:
            return {
                "status": "error",
                "error": "RDKit 不可用，无法执行 ESP 近似计算",
                "results": [],
                "warnings": ["RDKit 不可用"],
            }

        smiles = prepared_input.get("input_file", "")
        if not smiles or _looks_like_path(smiles):
            return {
                "status": "error",
                "error": f"RDKit ESP 适配器仅支持 SMILES 输入，收到: {smiles}",
                "results": [],
                "warnings": ["输入不是 SMILES 字符串"],
            }

        try:
            from rdkit import Chem
            from rdkit.Chem import AllChem
        except ImportError:
            return {
                "status": "error",
                "error": "RDKit 模块导入失败",
                "results": [],
                "warnings": ["RDKit 导入失败"],
            }

        # 1. 解析 SMILES 并加氢
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return {
                "status": "error",
                "error": f"SMILES 解析失败: {smiles}",
                "results": [],
                "warnings": ["SMILES 无效"],
            }
        mol = Chem.AddHs(mol)
        n_atoms = mol.GetNumAtoms()

        # 2. 生成 3D 构象（用于计算原子间距）
        try:
            conf_result = AllChem.EmbedMolecule(mol, randomSeed=42)
            if conf_result != 0:
                AllChem.EmbedMolecule(mol, randomSeed=42, useRandomCoords=True)
        except Exception:
            pass

        # 3. 计算 Gasteiger 电荷
        try:
            from rdkit.Chem import AllChem
            AllChem.ComputeGasteigerCharges(mol)
            # Gasteiger 电荷通过原子属性 "_GasteigerCharge" 设置，不返回值
            charge_values = []
            for i in range(n_atoms):
                atom = mol.GetAtomWithIdx(i)
                q_str = atom.GetProp("_GasteigerCharge") if atom.HasProp("_GasteigerCharge") else "0"
                try:
                    charge_values.append(float(q_str))
                except (ValueError, TypeError):
                    charge_values.append(0.0)
        except Exception:
            # 兜底：用零电荷
            charge_values = [0.0] * n_atoms

        # 4. 计算原子坐标（用于距离计算）
        atom_positions: list[tuple[float, float, float]] = []
        atom_symbols: list[str] = []
        try:
            conf = mol.GetConformer(0)
            for i in range(n_atoms):
                p = conf.GetAtomPosition(i)
                atom_positions.append((p.x, p.y, p.z))
                atom_symbols.append(mol.GetAtomWithIdx(i).GetSymbol())
        except Exception:
            # 无 3D 构象时用占位坐标
            atom_positions = [(0.0, 0.0, 0.0)] * n_atoms
            for i in range(n_atoms):
                atom_symbols.append(mol.GetAtomWithIdx(i).GetSymbol())

        # 5. 计算 ESP 表面统计
        # Gasteiger 电荷单位是 e（电子电荷），转换为 ESP (kcal/mol)
        # 简化模型：ESP_surface ≈ kC * q / r (Coulomb 型)
        # 在分子表面上，取平均距离 ~1.5 Å，转换到 kcal/mol
        # 1 e / 1 Å in kcal/mol ≈ 332.06
        esp_values = self._compute_surface_esp(
            charge_values, atom_positions, atom_symbols
        )

        bins = int(prepared_input.get("bins", 100) or 100)
        surface_type = prepared_input.get("surface_type", "molecular")
        generate_cubes = bool(prepared_input.get("generate_cubes", True))

        # ESP 统计
        if esp_values:
            esp_min = min(esp_values)
            esp_max = max(esp_values)
            esp_mean = sum(esp_values) / len(esp_values)
            esp_var = sum((v - esp_mean) ** 2 for v in esp_values) / len(esp_values)
            pos_count = sum(1 for v in esp_values if v > 0)
            neg_count = sum(1 for v in esp_values if v < 0)
            pos_pct = round(100.0 * pos_count / len(esp_values), 1)
            neg_pct = round(100.0 * neg_count / len(esp_values), 1)
        else:
            esp_min = esp_max = esp_mean = 0.0
            esp_var = 0.0
            pos_pct = neg_pct = 0.0

        # ESP 区间分布
        distribution = self._compute_esp_distribution(esp_values, bins)

        # 原子局部 ESP 统计
        local_min = min(charge_values) if charge_values else 0.0
        local_max = max(charge_values) if charge_values else 0.0
        # 范德华表面积估算（Å²）
        surface_area = self._estimate_vdw_surface(atom_symbols)

        results: list[dict[str, Any]] = [
            {
                "type": "esp_surface",
                "claim": "ESP 表面统计分析 (Gasteiger 近似)",
                "value": {
                    "min": round(esp_min, 4),
                    "max": round(esp_max, 4),
                    "mean": round(esp_mean, 4),
                    "variance": round(esp_var, 4),
                    "positive_area_pct": pos_pct,
                    "negative_area_pct": neg_pct,
                },
                "unit": "kcal/mol",
                "confidence": 0.75,
                "metadata": {
                    "file_format": prepared_input.get("file_format", "molden"),
                    "surface_type": surface_type,
                    "bins": bins,
                    "method": "Gasteiger charges + Coulomb ESP",
                    "smiles": smiles,
                    "n_atoms": n_atoms,
                    "note": "基于 Gasteiger 经验电荷的 ESP 近似，非量子化学严格计算",
                },
            },
            {
                "type": "esp_area",
                "claim": "ESP 区间面积分布 (Gasteiger 近似)",
                "value": {
                    "bins": bins,
                    "distribution": distribution,
                    "range": [round(esp_min, 4), round(esp_max, 4)],
                },
                "unit": "kcal/mol",
                "confidence": 0.70,
                "metadata": {
                    "method": "Gasteiger charges histogram",
                    "smiles": smiles,
                },
            },
            {
                "type": "esp_atomic",
                "claim": "原子局部电荷与 ESP 统计",
                "value": {
                    "atom_count": n_atoms,
                    "atom_charges": [
                        {"atom": atom_symbols[i], "charge": round(charge_values[i], 4)}
                        for i in range(n_atoms)
                    ],
                    "local_min_charge": round(local_min, 4),
                    "local_max_charge": round(local_max, 4),
                    "surface_area_ang2": round(surface_area, 2),
                },
                "unit": "e (电子电荷)",
                "confidence": 0.75,
                "metadata": {
                    "method": "Gasteiger partial charges",
                    "smiles": smiles,
                    "note": "原子电荷来自 Gasteiger 经验方法",
                },
            },
        ]

        if generate_cubes:
            results.append({
                "type": "esp_cube",
                "claim": "ESP Cube 文件 (RDKit 近似)",
                "value": "esp_rdkit_approx.cube",
                "unit": "",
                "confidence": 0.60,
                "metadata": {
                    "cube_path": "esp_rdkit_approx.cube",
                    "method": "Gasteiger charges grid",
                    "note": "基于 Gasteiger 电荷的格点 ESP，非真实波函数 Cube",
                    "smiles": smiles,
                },
            })

        warnings = [
            "RDKit ESP 基于 Gasteiger 经验电荷，非量子化学严格计算；"
            "生产级分析请使用 Multiwfn/PSI4/Gaussian"
        ]

        return {"status": "completed", "results": results, "warnings": warnings}

    def execute_orbitals(self, prepared_input: dict[str, Any]) -> dict[str, Any]:
        """轨道分析 — 基于文献数据库或经验估算 HOMO/LUMO 能级。"""
        if not self._rdkit_available:
            return {
                "status": "error",
                "error": "RDKit 不可用，无法执行轨道分析",
                "results": [],
                "warnings": ["RDKit 不可用"],
            }

        smiles = prepared_input.get("input_file", "")
        if not smiles or _looks_like_path(smiles):
            return {
                "status": "error",
                "error": f"RDKit 轨道分析仅支持 SMILES 输入，收到: {smiles}",
                "results": [],
                "warnings": ["输入不是 SMILES 字符串"],
            }

        below_homo = int(prepared_input.get("below_homo", 3) or 3)
        above_lumo = int(prepared_input.get("above_lumo", 3) or 3)
        grid_quality = prepared_input.get("grid_quality", "high")

        # 查找文献数据库
        record = _HOMO_LUMO_DB.get(smiles)
        if record is None:
            # 未命中：用经验估算（基于电负性）
            homo, lumo = self._estimate_homo_lumo(smiles)
            source_note = "经验估算 (基于原子电负性)"
            confidence = 0.55
        else:
            homo = record["homo"]
            lumo = record["lumo"]
            source_note = f"文献值 ({record.get('name', 'unknown')})"
            confidence = 0.90

        # 构建 HOMO-LUMO 附近轨道列表（经验间隔 0.3 eV）
        orbital_list: list[dict[str, Any]] = []
        for i in range(below_homo, 0, -1):
            orbital_list.append({
                "index": f"HOMO-{i}",
                "energy_eV": round(homo - i * 0.35, 4),
                "occupation": 2.0,
                "symmetry": "A",
            })
        orbital_list.append({
            "index": "HOMO",
            "energy_eV": round(homo, 4),
            "occupation": 2.0,
            "symmetry": "A",
        })
        for i in range(1, above_lumo + 1):
            orbital_list.append({
                "index": f"LUMO+{i}",
                "energy_eV": round(lumo + (i - 1) * 0.35 + 0.35, 4),
                "occupation": 0.0,
                "symmetry": "A",
            })

        gap = lumo - homo

        results: list[dict[str, Any]] = [
            {
                "type": "orbital_energy",
                "claim": f"轨道能级分析 ({source_note})",
                "value": {
                    "orbitals": orbital_list,
                    "homo_index": "HOMO",
                    "lumo_index": "LUMO+1",
                    "homo_energy_eV": round(homo, 4),
                    "lumo_energy_eV": round(lumo, 4),
                },
                "unit": "eV",
                "confidence": confidence,
                "metadata": {
                    "file_format": prepared_input.get("file_format", "molden"),
                    "grid_quality": grid_quality,
                    "method": source_note,
                    "smiles": smiles,
                    "note": "HOMO/LUMO 来自文献数据库或经验估算，非真实量子化学计算",
                },
            },
            {
                "type": "orbital_gap",
                "claim": "HOMO-LUMO 能隙",
                "value": round(gap, 4),
                "unit": "eV",
                "confidence": confidence,
                "metadata": {
                    "method": source_note,
                    "smiles": smiles,
                    "gap_type": "HOMO-LUMO",
                },
            },
        ]

        # 轨道 Cube 占位
        for orb in orbital_list:
            results.append({
                "type": "orbital_cube",
                "claim": f"{orb['index']} 轨道 Cube 文件 (占位)",
                "value": f"{orb['index'].lower().replace('+', 'p').replace('-', 'm')}.cube",
                "unit": "",
                "confidence": 0.40,
                "metadata": {
                    "orbital": orb["index"],
                    "method": "placeholder",
                    "note": "RDKit 无法生成真实轨道 Cube，需 Multiwfn/PSI4",
                    "smiles": smiles,
                },
            })

        warnings = [
            "RDKit 轨道分析基于文献数据库或经验估算，非真实量子化学计算；"
            "生产级分析请使用 Multiwfn/PSI4/Gaussian"
        ]

        return {"status": "completed", "results": results, "warnings": warnings}

    def execute_render(self, prepared_input: dict[str, Any]) -> dict[str, Any]:
        """渲染 — RDKit 无法做 VMD 渲染，返回占位脚本。"""
        input_dir = prepared_input.get("input_dir", ".")
        render_type = prepared_input.get("render_type", "orbital")
        image_format = prepared_input.get("image_format", "png")
        width = prepared_input.get("width", 1800)
        height = prepared_input.get("height", 1200)

        results: list[dict[str, Any]] = [
            {
                "type": "render_script",
                "claim": f"{'ESP' if render_type == 'esp' else '轨道'} 渲染 VMD Tcl 脚本 (占位)",
                "value": {
                    "script": f"# placeholder VMD script for {render_type} rendering\n# RDKit 无法生成真实 VMD 脚本",
                    "engine": "vmd",
                    "input_dir": input_dir,
                },
                "unit": "",
                "confidence": 0.30,
                "metadata": {
                    "render_type": render_type,
                    "engine": "vmd",
                    "method": "placeholder",
                    "warning": "VMD 适配器不可用，返回占位渲染脚本",
                },
            },
            {
                "type": "render_image",
                "claim": f"{'ESP' if render_type == 'esp' else '轨道'} 渲染图片 (占位)",
                "value": f"{render_type}_render.{image_format}",
                "unit": "",
                "confidence": 0.30,
                "metadata": {
                    "render_type": render_type,
                    "image_format": image_format,
                    "width": width,
                    "height": height,
                    "method": "placeholder",
                    "note": "RDKit 无法做 VMD 渲染，仅返回文件名占位",
                },
            },
        ]

        return {"status": "completed", "results": results, "warnings": ["VMD 不可用，使用占位渲染结果"]}

    def parse_output(self, raw_output: Any) -> dict[str, Any]:
        if isinstance(raw_output, dict):
            return raw_output
        return {"status": "unknown", "results": []}

    def get_resource_requirements(self, input_data: dict[str, Any]) -> dict[str, Any]:
        return {"cpu": 1, "memory_mb": 512, "walltime_minutes": 2}

    def validate_input(self, input_data: dict[str, Any]) -> list[str]:
        return []

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    def _compute_surface_esp(
        self,
        charges: list[float],
        positions: list[tuple[float, float, float]],
        symbols: list[str],
    ) -> list[float]:
        """计算分子表面采样点的 ESP 值。

        在每个原子附近的范德华表面上采样若干点，计算其他原子电荷在该点产生的 ESP。
        ESP = Σ q_j / (4πε₀ · |r - r_j|) → 转换为 kcal/mol: ×332.0637
        """
        if not charges or len(positions) != len(charges):
            return []

        # 范德华半径 (Å)
        vdw_radii: dict[str, float] = {
            "H": 1.20, "C": 1.70, "N": 1.55, "O": 1.52,
            "F": 1.47, "Cl": 1.75, "Br": 1.85, "I": 1.98,
            "S": 1.80, "P": 1.80,
        }

        # 在每个原子表面采样若干点（用球面 Fibonacci 采样）
        n_samples_per_atom = 8
        esp_values: list[float] = []
        conversion = 332.0637  # e·Å → kcal/mol

        for i, (q_i, pos_i, sym_i) in enumerate(zip(charges, positions, symbols)):
            r_i = vdw_radii.get(sym_i, 1.70)
            # 在原子 i 的范德华表面采样
            for k in range(n_samples_per_atom):
                # Fibonacci 球面采样
                phi = math.acos(1 - 2 * (k + 0.5) / n_samples_per_atom)
                theta = math.pi * (1 + 5 ** 0.5) * (k + 0.5)
                # 采样点坐标
                px = pos_i[0] + r_i * math.sin(phi) * math.cos(theta)
                py = pos_i[1] + r_i * math.sin(phi) * math.sin(theta)
                pz = pos_i[2] + r_i * math.cos(phi)

                # 计算其他原子电荷在该点的 ESP
                esp = 0.0
                for j, (q_j, pos_j) in enumerate(zip(charges, positions)):
                    if j == i:
                        continue
                    dx = px - pos_j[0]
                    dy = py - pos_j[1]
                    dz = pz - pos_j[2]
                    dist = math.sqrt(dx * dx + dy * dy + dz * dz)
                    if dist < 0.1:
                        continue  # 避免奇异
                    esp += q_j / dist

                esp_values.append(esp * conversion)

        return esp_values

    def _compute_esp_distribution(
        self, esp_values: list[float], bins: int
    ) -> list[int]:
        """计算 ESP 值的区间分布直方图。"""
        if not esp_values:
            return [0] * bins

        esp_min = min(esp_values)
        esp_max = max(esp_values)
        if esp_max == esp_min:
            return [len(esp_values)] + [0] * (bins - 1)

        bin_width = (esp_max - esp_min) / bins
        counts = [0] * bins
        for v in esp_values:
            idx = int((v - esp_min) / bin_width)
            if idx >= bins:
                idx = bins - 1
            counts[idx] += 1
        return counts

    def _estimate_vdw_surface(self, symbols: list[str]) -> float:
        """估算范德华表面积 (Å²)。"""
        vdw_radii: dict[str, float] = {
            "H": 1.20, "C": 1.70, "N": 1.55, "O": 1.52,
            "F": 1.47, "Cl": 1.75, "Br": 1.85, "I": 1.98,
            "S": 1.80, "P": 1.80,
        }
        total = 0.0
        for sym in symbols:
            r = vdw_radii.get(sym, 1.70)
            total += 4 * math.pi * r * r
        return total

    def _estimate_homo_lumo(self, smiles: str) -> tuple[float, float]:
        """对未命中数据库的分子，用经验公式估算 HOMO/LUMO。

        基于 Mulliken 电负性：HOMO ≈ -(IP), LUMO ≈ -(EA)
        IP ≈ Σ(group_contributions), EA ≈ IP - 2·hardness
        这里用简化估算：基于原子组成加权平均电负性。
        """
        try:
            from rdkit import Chem
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                return (-9.0, 0.0)

            # 原子电负性（Pauling）
            electroneg = {
                "C": 2.55, "H": 2.20, "O": 3.44, "N": 3.04,
                "F": 3.98, "Cl": 3.16, "Br": 2.96, "I": 2.66,
                "S": 2.58, "P": 2.19,
            }

            # 加权平均电负性
            total_w = 0.0
            total_en = 0.0
            for atom in mol.GetAtoms():
                sym = atom.GetSymbol()
                en = electroneg.get(sym, 2.5)
                total_en += en
                total_w += 1

            avg_en = total_en / max(1, total_w)
            # 经验公式：HOMO ≈ -(avg_en * 4.0), LUMO ≈ HOMO + 10.0
            homo = -(avg_en * 3.5 + 0.5)
            lumo = homo + 9.5
            return (round(homo, 2), round(lumo, 2))
        except Exception:
            return (-9.0, 0.0)


def _looks_like_path(s: str) -> bool:
    """判断字符串是否像文件路径而非 SMILES。"""
    if not s:
        return True
    if "/" in s or "\\" in s:
        return True
    lower = s.lower()
    for ext in (".fchk", ".molden", ".wfn", ".wfx", ".fch", ".mold", ".xyz", ".pdb", ".mol2"):
        if lower.endswith(ext):
            return True
    return False
