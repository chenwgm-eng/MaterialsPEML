"""配方优化与分子堆积适配器 — 真实接入 packmol Docker 容器。

执行策略：
- packing: 通过 Docker 容器调用 packmol 进行真实分子堆积；packmol 不可用时回退到 RDKit 体积估算。
- formulation_optimization: 基于 RDKit 分子描述符的网格搜索。

packmol 调用流程：
1. 用 RDKit 为每个 SMILES 生成 3D 构象并导出 XYZ 文件
2. 生成 packmol 输入文件（.inp）—— 包含盒子尺寸、分子数、容差
3. 通过 ``docker run --rm -v <workdir>:/work batteryemcl/packmol`` 执行
4. 解析输出的 PDB 文件，计算实际堆积密度
"""
from __future__ import annotations

import os
import shutil
import subprocess
from typing import Any

from .execution_adapter import ExecutionAdapter, create_engine_work_dir


# Docker 镜像常量
_PACKMOL_DOCKER_IMAGE = os.environ.get(
    "BATTERYEMCL_PACKMOL_IMAGE", "batteryemcl/packmol:latest"
)

# 堆积分数（packmol 失败时用于 RDKit 兜底体积估算）
_PACKING_FRACTIONS = {"crystal": 0.70, "amorphous": 0.55, "solvation": 0.45}
_AVOGADRO = 6.02214076e23


def _looks_like_path(s: str) -> bool:
    """判断字符串是否像文件路径而非 SMILES。"""
    if not s:
        return True
    if "/" in s or "\\" in s:
        return True
    lower = s.lower()
    for ext in (".xyz", ".pdb", ".mol", ".mol2", ".sdf", ".cif"):
        if lower.endswith(ext):
            return True
    return False


class FormulationAdapter(ExecutionAdapter):
    """配方优化与分子堆积适配器。

    支持的操作：
    - formulation_optimization: 基于 RDKit 描述符的网格搜索优化
    - packing: 通过 Docker packmol 容器执行真实分子堆积
    """

    _SUPPORTED_OPERATIONS = {"formulation_optimization", "packing"}

    def __init__(self) -> None:
        self._rdkit_available = self._try_import_rdkit()
        self._packmol_binary = shutil.which("packmol")
        self._docker_available: bool | None = None  # 延迟探测

    # ------------------------------------------------------------------
    # Import checks
    # ------------------------------------------------------------------

    @staticmethod
    def _try_import_rdkit() -> bool:
        try:
            import rdkit  # noqa: F401
            return True
        except ImportError:
            return False

    def _check_docker_available(self) -> bool:
        """探测 Docker + science-engine 镜像是否可用（结果缓存）。"""
        if self._docker_available is not None:
            return self._docker_available
        try:
            result = subprocess.run(
                ["docker", "images", "-q", _PACKMOL_DOCKER_IMAGE],
                capture_output=True,
                text=True,
                timeout=10,
            )
            self._docker_available = result.returncode == 0 and bool(result.stdout.strip())
        except Exception:
            self._docker_available = False
        return self._docker_available

    # ------------------------------------------------------------------
    # Public API — ExecutionAdapter 接口
    # ------------------------------------------------------------------

    def execute(self, prepared_input: dict[str, Any]) -> dict[str, Any]:
        """Handle formulation/packing operations (standard ExecutionAdapter interface)."""
        operation = prepared_input.get("operation", "")
        if operation not in self._SUPPORTED_OPERATIONS:
            return {
                "error": f"Unsupported operation: {operation}. "
                f"Supported: {', '.join(sorted(self._SUPPORTED_OPERATIONS))}",
            }
        if operation == "formulation_optimization":
            return self.optimize_formulation(prepared_input)
        return self.build_packing_structure(prepared_input)

    def parse_output(self, raw_output: dict[str, Any]) -> dict[str, Any]:
        return raw_output

    def get_resource_requirements(self, input_data: dict[str, Any]) -> dict[str, Any]:
        return {"cpu": 4, "memory_mb": 2048, "walltime_minutes": 30}

    # ------------------------------------------------------------------
    # Public API — application 期望的高级接口
    # ------------------------------------------------------------------

    def optimize_formulation(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """配方优化 — 基于 RDKit 分子描述符的网格搜索。

        Args:
            input_data: {
                "components": [{"name", "smiles", "ratio_range_min", "ratio_range_max"}, ...],
                "target_properties": ["MW", "logP", "TPSA", ...],
                "optimization_goal": "maximize" | "minimize" | "target",
                "max_iterations": 1000,
            }
        """
        components: list[dict] = input_data.get("components", [])
        target_properties: list[str] = input_data.get("target_properties", ["MW"])
        optimization_goal: str = input_data.get("optimization_goal", "maximize")

        if not components:
            return {
                "formulation_id": "f-001",
                "method": "rdkit_grid_search",
                "components": [],
                "properties": [],
                "optimized_ratios": [],
                "warning": "未提供组分",
            }

        if not self._rdkit_available:
            # 无 RDKit 时返回等比配方
            n = len(components)
            equal = [round(1.0 / n, 4)] * n
            return {
                "formulation_id": "f-001",
                "method": "equal_ratio_fallback",
                "components": [
                    {
                        "name": c.get("name", c.get("smiles", "")),
                        "smiles": c.get("smiles", ""),
                        "ratio": equal[i],
                    }
                    for i, c in enumerate(components)
                ],
                "properties": [],
                "optimized_ratios": equal,
                "optimization_goal": optimization_goal,
                "warning": "RDKit 不可用，返回等比配方",
            }

        # 计算每组分描述符
        comp_descs: list[dict[str, Any]] = []
        for comp in components:
            smiles = comp.get("smiles", "")
            name = comp.get("name", smiles)
            desc = self._compute_descriptors(smiles)
            comp_descs.append({
                "name": name,
                "smiles": smiles,
                "descriptors": desc,
                "ratio_range_min": comp.get("ratio_range_min", 0.0),
                "ratio_range_max": comp.get("ratio_range_max", 1.0),
            })

        # 网格搜索
        n = len(comp_descs)
        step = 0.1
        best_score = None
        best_ratios = [1.0 / n] * n

        if n <= 3:
            import itertools

            candidates = []
            for cd in comp_descs:
                lo = max(0.0, float(cd["ratio_range_min"]))
                hi = min(1.0, float(cd["ratio_range_max"]))
                vals = [round(lo + i * step, 2) for i in range(int((hi - lo) / step) + 1)]
                candidates.append(vals)

            for combo in itertools.product(*candidates):
                total = sum(combo)
                if total == 0 or abs(total - 1.0) > 0.05:
                    continue
                ratios = [c / total for c in combo]

                score = 0.0
                for prop in target_properties:
                    weighted = sum(
                        ratios[i] * (comp_descs[i]["descriptors"].get(prop, 0) or 0)
                        for i in range(n)
                    )
                    score += weighted

                if optimization_goal == "minimize":
                    if best_score is None or score < best_score:
                        best_score, best_ratios = score, ratios
                else:  # maximize / target
                    if best_score is None or score > best_score:
                        best_score, best_ratios = score, ratios

        # 最优配方性质
        optimized_props: list[dict[str, Any]] = []
        for prop in target_properties:
            weighted_val = sum(
                best_ratios[i] * (comp_descs[i]["descriptors"].get(prop, 0) or 0)
                for i in range(n)
            )
            optimized_props.append({"name": prop, "value": round(weighted_val, 4), "unit": ""})

        return {
            "formulation_id": "f-001",
            "method": "rdkit_grid_search",
            "components": [
                {
                    "name": cd["name"],
                    "smiles": cd["smiles"],
                    "ratio": round(best_ratios[i], 4),
                    "descriptors": cd["descriptors"],
                }
                for i, cd in enumerate(comp_descs)
            ],
            "properties": optimized_props,
            "optimized_ratios": [round(r, 4) for r in best_ratios],
            "optimization_goal": optimization_goal,
        }

    def build_packing_structure(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """分子堆积 — 优先 Docker packmol，回退 RDKit 体积估算。

        Args:
            input_data: {
                "molecules": [SMILES, ...] 或 [{"smiles": ..., "count": ...}, ...],
                "packing_type": "crystal|amorphous|solvation",
                "target_density": float|None,  # g/cm³
                "box_size_nm": float|None,  # 或旧格式 box_size: [x, y, z] (Å)
                "force_field": "uff",
                "molecule_counts": list[int]|None,  # 每种分子数量，默认各 50
                "tolerance": float|None,  # Å, 默认 2.0
            }
        """
        raw_molecules = input_data.get("molecules", [])
        packing_type: str = input_data.get("packing_type", "amorphous")
        target_density = input_data.get("target_density")
        box_size_nm = input_data.get("box_size_nm")
        force_field: str = input_data.get("force_field", "uff")
        tolerance: float = input_data.get("tolerance", 2.0)

        # 兼容旧格式 box_size: [x, y, z] (Å) → 取平均边长转 nm
        box_size_list = input_data.get("box_size")
        if box_size_nm is None and isinstance(box_size_list, list) and len(box_size_list) >= 1:
            box_size_nm = float(sum(box_size_list[:3]) / len(box_size_list[:3])) / 10.0

        # 兼容两种 molecules 格式：list[str] 或 list[dict]
        molecules: list[str] = []
        molecule_counts: list[int] = []
        for item in raw_molecules:
            if isinstance(item, dict):
                smi = item.get("smiles", item.get("identifier", ""))
                cnt = int(item.get("count", item.get("number", 50)))
                molecules.append(smi)
                molecule_counts.append(cnt)
            elif isinstance(item, str):
                molecules.append(item)
                molecule_counts.append(50)
            elif isinstance(item, (int, float)):
                # 数字不能作为 SMILES
                continue

        # 显式 molecule_counts 覆盖
        explicit_counts: list[int] | None = input_data.get("molecule_counts")
        if explicit_counts is not None:
            molecule_counts = [int(c) for c in explicit_counts]
            # 补齐
            while len(molecule_counts) < len(molecules):
                molecule_counts.append(50)

        if not molecules:
            return {
                "structure_id": "s-001",
                "density": 0.0,
                "energy": 0.0,
                "warning": "未提供分子列表",
            }

        if not self._rdkit_available:
            return {
                "structure_id": "s-001",
                "density": 0.0,
                "energy": 0.0,
                "warning": "RDKit 不可用，无法生成分子结构",
            }

        # 1. 生成 XYZ 文件并收集分子信息
        work_dir = create_engine_work_dir("packmol")
        try:
            xyz_files, mol_infos, total_mass_g = self._generate_xyz_files(
                molecules, molecule_counts, force_field, work_dir
            )
            if not xyz_files:
                return {
                    "structure_id": "s-001",
                    "density": 0.0,
                    "energy": 0.0,
                    "warning": "所有分子均无法解析",
                }

            # 2. 计算盒子尺寸 (nm → Å)
            box_size_ang = self._compute_box_size(
                box_size_nm, target_density, total_mass_g, packing_type, mol_infos
            )

            # 3. 生成 packmol 输入文件
            input_inp = self._write_packmol_input(
                xyz_files, molecule_counts, box_size_ang, tolerance, work_dir
            )

            # 4. 执行 packmol（优先本地二进制，其次 Docker，最后回退）
            packing_result = self._run_packmol(input_inp, work_dir)

            if packing_result.get("success"):
                return self._build_success_result(
                    mol_infos, packing_result, box_size_ang, packing_type,
                    target_density, force_field, molecule_counts, total_mass_g,
                    engine=packing_result.get("engine", "packmol"),
                )

            # packmol 失败 → RDKit 体积估算兜底
            return self._fallback_rdkit_packing(
                mol_infos, molecules, molecule_counts, packing_type,
                target_density, box_size_ang, force_field,
                warning=packing_result.get("error", "packmol 执行失败"),
            )
        finally:
            try:
                shutil.rmtree(work_dir, ignore_errors=True)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # 分子结构生成
    # ------------------------------------------------------------------

    def _generate_xyz_files(
        self,
        molecules: list[str],
        counts: list[int],
        force_field: str,
        work_dir: str,
    ) -> tuple[list[str], list[dict[str, Any]], float]:
        """为每个 SMILES 生成 PDB 文件（packmol 对 PDB 支持最可靠），返回 (文件列表, 分子信息, 总质量 g)。"""
        from rdkit import Chem
        from rdkit.Chem import AllChem, Descriptors

        struct_files: list[str] = []
        mol_infos: list[dict[str, Any]] = []
        total_mass_g = 0.0

        for idx, smiles in enumerate(molecules):
            if _looks_like_path(smiles):
                continue
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                continue
            mol = Chem.AddHs(mol)
            mw = Descriptors.MolWt(mol)  # g/mol

            try:
                AllChem.EmbedMolecule(mol, randomSeed=42)
                if force_field == "mmff94":
                    AllChem.MMFFOptimizeMolecule(mol, maxIters=200)
                else:
                    AllChem.UFFOptimizeMolecule(mol, maxIters=200)
            except Exception:
                pass  # 优化失败仍可使用

            # 导出 PDB（packmol 对 PDB 格式支持最可靠，强制 Unix 行尾）
            pdb_path = os.path.join(work_dir, f"mol_{idx}.pdb")
            pdb_block = Chem.MolToPDBBlock(mol)
            with open(pdb_path, "w", encoding="utf-8", newline="\n") as f:
                f.write(pdb_block)
            struct_files.append(pdb_path)

            # 估算单分子体积 (Å³)
            try:
                volume_a3 = AllChem.ComputeMolVolume(mol, gridSpacing=0.2)
            except Exception:
                volume_a3 = mw / 1.0  # 兜底：1 g/cm³ → MW cm³/mol → /Avogadro

            counts_idx = counts[idx] if idx < len(counts) else 50
            total_mass_g += (mw * counts_idx) / _AVOGADRO

            mol_infos.append({
                "smiles": smiles,
                "molecule_index": idx,
                "count": counts_idx,
                "molecular_weight": round(mw, 3),
                "volume_a3": round(volume_a3, 3),
                "structure_file": f"mol_{idx}.pdb",
            })

        return struct_files, mol_infos, total_mass_g

    # ------------------------------------------------------------------
    # packmol 输入生成与执行
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_box_size(
        box_size_nm: float | None,
        target_density: float | None,
        total_mass_g: float,
        packing_type: str,
        mol_infos: list[dict[str, Any]],
    ) -> float:
        """计算盒子边长 (Å)。"""
        if box_size_nm is not None and box_size_nm > 0:
            return float(box_size_nm) * 10.0  # nm → Å

        if target_density and target_density > 0 and total_mass_g > 0:
            # V = m / ρ; m(g), ρ(g/cm³) → V(cm³) → nm³ (×1e21) → Å³ (×1000)
            volume_cm3 = total_mass_g / target_density
            volume_nm3 = volume_cm3 * 1e21
            box_nm = volume_nm3 ** (1.0 / 3.0)
            return box_nm * 10.0

        # 兜底：根据分子总体积 + 堆积分数估算
        pf = _PACKING_FRACTIONS.get(packing_type, 0.55)
        total_vol_a3 = sum(m.get("volume_a3", 0) * m.get("count", 1) for m in mol_infos)
        if total_vol_a3 <= 0:
            return 30.0  # 默认 30 Å
        box_vol_a3 = total_vol_a3 / pf
        return box_vol_a3 ** (1.0 / 3.0)

    @staticmethod
    def _write_packmol_input(
        xyz_files: list[str],
        counts: list[int],
        box_size_ang: float,
        tolerance: float,
        work_dir: str,
    ) -> str:
        """生成 packmol 输入文件 (.inp)。"""
        inp_path = os.path.join(work_dir, "packmol.inp")
        out_pdb = "packed.pdb"

        lines = [
            f"tolerance {tolerance}",
            "filetype pdb",
            f"output {out_pdb}",
            "",
        ]

        for idx, xyz in enumerate(xyz_files):
            basename = os.path.basename(xyz)
            n = counts[idx] if idx < len(counts) else 50
            lines.extend([
                f"structure {basename}",
                f"  number {n}",
                f"  inside box 0. 0. 0. {box_size_ang:.4f} {box_size_ang:.4f} {box_size_ang:.4f}",
                "end structure",
                "",
            ])

        with open(inp_path, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(lines))
        return inp_path

    def _run_packmol(self, input_inp: str, work_dir: str) -> dict[str, Any]:
        """执行 packmol — 优先本地二进制，其次 Docker，返回结果字典。

        packmol 通过 shell 重定向读取输入文件（``packmol < input.inp``），
        而非命令行参数或 stdin 管道（packmol 需要 seek，管道不支持）。
        """
        inp_basename = os.path.basename(input_inp)

        # 1. 本地 packmol 二进制（使用 shell 重定向）
        if self._packmol_binary:
            try:
                result = subprocess.run(
                    f'"{self._packmol_binary}" < "{input_inp}"',
                    capture_output=True,
                    text=True,
                    timeout=120,
                    cwd=work_dir,
                    shell=True,
                )
                packed_path = os.path.join(work_dir, "packed.pdb")
                if result.returncode == 0 and os.path.isfile(packed_path):
                    return {
                        "success": True,
                        "engine": "local_packmol",
                        "packed_path": packed_path,
                        "stdout": result.stdout[-1000:],
                    }
            except Exception:
                pass  # 继续 Docker

        # 2. Docker 容器（覆盖 ENTRYPOINT，使用 shell 重定向）
        if self._check_docker_available():
            return self._run_docker_packmol(inp_basename, work_dir)

        return {
            "success": False,
            "error": "packmol 二进制与 Docker 容器均不可用",
        }

    def _run_docker_packmol(self, inp_basename: str, work_dir: str) -> dict[str, Any]:
        """通过常驻 Docker 容器执行 packmol — 使用 shell 重定向。"""
        from .docker_executor import run_in_persistent_container

        # packmol 需要 seekable 输入，管道 stdin 不支持，必须用文件重定向
        # 常驻容器 workdir 已设为 /work/<rel>，使用相对路径重定向
        exit_code, stdout, stderr = run_in_persistent_container(
            engine_key="packmol",
            image=_PACKMOL_DOCKER_IMAGE,
            cmd_args=["sh", "-c", f"packmol < {inp_basename}"],
            work_dir=work_dir,
            entrypoint="tail",
            timeout=180,
        )

        if exit_code == 1 and "镜像不可用" in stderr:
            return {"success": False, "error": stderr}

        packed_path = os.path.join(work_dir, "packed.pdb")
        if exit_code != 0 or not os.path.isfile(packed_path):
            return {
                "success": False,
                "error": f"packmol 退出码 {exit_code}; stdout: {stdout[-300:]}; stderr: {stderr[-300:]}",
            }

        return {
            "success": True,
            "engine": "docker_packmol_persistent",
            "packed_path": packed_path,
            "stdout": stdout[-1000:],
        }

    # ------------------------------------------------------------------
    # 结果构建
    # ------------------------------------------------------------------

    def _build_success_result(
        self,
        mol_infos: list[dict[str, Any]],
        packing_result: dict[str, Any],
        box_size_ang: float,
        packing_type: str,
        target_density: float | None,
        force_field: str,
        counts: list[int],
        total_mass_g: float,
        engine: str,
    ) -> dict[str, Any]:
        """构建 packmol 成功结果。"""
        packed_path = packing_result["packed_path"]

        # 解析 PDB 计算实际分子数与盒子尺寸
        atom_count, actual_molecules, bbox = self._parse_packed_pdb(packed_path)

        # 实际盒子尺寸（Å → nm）
        box_size_nm = round(box_size_ang / 10.0, 4)
        box_volume_nm3 = round((box_size_ang / 10.0) ** 3, 6)

        # 实际密度 = 总质量 / 盒子体积
        # box_volume_nm3 × 1e-21 = cm³
        box_volume_cm3 = box_volume_nm3 * 1e-21
        if box_volume_cm3 > 0:
            actual_density = round(total_mass_g / box_volume_cm3, 4)
        else:
            actual_density = 0.0

        # 堆积分数
        total_vol_a3 = sum(m.get("volume_a3", 0) * m.get("count", 1) for m in mol_infos)
        box_vol_a3 = box_size_ang ** 3
        pf = round(total_vol_a3 / box_vol_a3, 4) if box_vol_a3 > 0 else 0.0

        # 简化能量估算（packmol 不输出能量，用堆积分数近似）
        energy_kj_mol = round(-pf * 10.0 * len(mol_infos), 3)

        # 读取 PDB 结构（限制大小）
        structure_block = ""
        try:
            with open(packed_path, encoding="utf-8") as f:
                structure_block = f.read()[:50000]  # 限制 50KB
        except Exception:
            pass

        return {
            "structure_id": "s-001",
            "method": f"packmol_{engine}",
            "packing_type": packing_type,
            "engine": engine,
            "molecules": mol_infos,
            "box_size_nm": box_size_nm,
            "box_size_ang": round(box_size_ang, 4),
            "box_volume_nm3": box_volume_nm3,
            "packing_fraction": pf,
            "density": actual_density,
            "density_unit": "g/cm³",
            "target_density": target_density,
            "energy": energy_kj_mol,
            "energy_unit": "kJ/mol",
            "force_field": force_field,
            "atom_count": atom_count,
            "actual_molecules_packed": actual_molecules,
            "structure": structure_block,
            "structure_format": "pdb",
            "warnings": [],
        }

    @staticmethod
    def _parse_packed_pdb(packed_path: str) -> tuple[int, int, tuple[float, float, float]]:
        """解析 packmol 输出的 PDB 文件，返回 (原子数, 分子数, 包围盒)。"""
        atom_count = 0
        coords: list[tuple[float, float, float]] = []
        try:
            with open(packed_path, encoding="utf-8") as f:
                for line in f:
                    if line.startswith(("ATOM", "HETATM")):
                        atom_count += 1
                        try:
                            x = float(line[30:38])
                            y = float(line[38:46])
                            z = float(line[46:54])
                            coords.append((x, y, z))
                        except Exception:
                            pass
        except Exception:
            pass

        if coords:
            xs = [c[0] for c in coords]
            ys = [c[1] for c in coords]
            zs = [c[2] for c in coords]
            bbox = (max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))
        else:
            bbox = (0.0, 0.0, 0.0)

        # 分子数估算：原子数 / 平均每分子原子数（粗略）
        # packmol 输出不含 TER 分隔符时无法精确计数，这里返回 atom_count 作为代理
        return atom_count, atom_count, bbox

    def _fallback_rdkit_packing(
        self,
        mol_infos: list[dict[str, Any]],
        molecules: list[str],
        counts: list[int],
        packing_type: str,
        target_density: float | None,
        box_size_ang: float,
        force_field: str,
        warning: str,
    ) -> dict[str, Any]:
        """packmol 失败时回退到 RDKit 体积估算。"""
        pf = _PACKING_FRACTIONS.get(packing_type, 0.55)
        box_size_nm = round(box_size_ang / 10.0, 4)
        box_volume_nm3 = round((box_size_ang / 10.0) ** 3, 6)

        total_vol_a3 = sum(m.get("volume_a3", 0) * m.get("count", 1) for m in mol_infos)
        actual_pf = round(total_vol_a3 / (box_size_ang ** 3), 4) if box_size_ang > 0 else 0.0

        total_mass_g = sum(
            m.get("molecular_weight", 0) * m.get("count", 1) for m in mol_infos
        ) / _AVOGADRO
        box_volume_cm3 = box_volume_nm3 * 1e-21
        density = round(total_mass_g / box_volume_cm3, 4) if box_volume_cm3 > 0 else 0.0

        if target_density and target_density > 0:
            density = target_density

        return {
            "structure_id": "s-001",
            "method": "rdkit_volume_estimate",
            "packing_type": packing_type,
            "engine": "rdkit_fallback",
            "molecules": mol_infos,
            "box_size_nm": box_size_nm,
            "box_volume_nm3": box_volume_nm3,
            "packing_fraction": actual_pf if actual_pf > 0 else pf,
            "density": density,
            "density_unit": "g/cm³",
            "target_density": target_density,
            "energy": round(-pf * 10.0 * len(mol_infos), 3),
            "energy_unit": "kJ/mol",
            "force_field": force_field,
            "warnings": [f"packmol 不可用，使用 RDKit 体积估算: {warning}"],
        }

    # ------------------------------------------------------------------
    # RDKit 描述符（配方优化用）
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_descriptors(smiles: str) -> dict[str, float | None]:
        """用 RDKit 计算分子描述符。"""
        try:
            from rdkit import Chem
            from rdkit.Chem import Descriptors, Crippen

            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                return {"MW": None, "logP": None, "TPSA": None,
                        "NumHDonors": None, "NumHAcceptors": None}
            return {
                "MW": round(Descriptors.MolWt(mol), 3),
                "logP": round(Crippen.MolLogP(mol), 3),
                "TPSA": round(Descriptors.TPSA(mol), 3),
                "NumHDonors": int(Descriptors.NumHDonors(mol)),
                "NumHAcceptors": int(Descriptors.NumHAcceptors(mol)),
            }
        except Exception:
            return {"MW": None, "logP": None, "TPSA": None,
                    "NumHDonors": None, "NumHAcceptors": None}
