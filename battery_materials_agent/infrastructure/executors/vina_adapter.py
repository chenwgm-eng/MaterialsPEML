"""AutoDock Vina 分子对接适配器 — 基于 Docker 常驻容器的真实对接引擎。

使用 AutoDock Vina（Apache 2.0，CPU 推理）替代 DiffDock 占位模型。
- 受体准备：OpenBabel 将 PDB 转为 PDBQT
- 配体准备：meeko 将 SMILES 转为 PDBQT
- 对接：Vina Python 绑定（vina.Vina）
- 输出：SDF 位姿 + 亲和力（kcal/mol）

本适配器返回与 DockingAdapter 相同的输出契约，便于无缝替换。
"""
from __future__ import annotations

import json
import os
import time
from typing import Any

from .execution_adapter import ExecutionAdapter, create_engine_work_dir
from .docker_executor import run_in_persistent_container

_VINA_DOCKER_IMAGE = os.environ.get(
    "BATTERYEMCL_VINA_IMAGE", "batteryemcl/vina-engine:latest"
)


class VinaAdapter(ExecutionAdapter):
    """基于 AutoDock Vina 的分子对接适配器。

    通过 Docker 常驻容器执行真实对接计算。
    需要 batteryemcl/vina-engine:latest 镜像（见 docker/engines/docking/Dockerfile）。
    """

    def __init__(self) -> None:
        self._image = _VINA_DOCKER_IMAGE

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def execute(self, prepared_input: dict[str, Any]) -> dict[str, Any]:
        """执行 AutoDock Vina 分子对接。

        Input format 与 DockingAdapter.execute 相同::

            {
                "protein_path": "/path/to/receptor.pdb",
                "ligand": "CCO",
                "ligand_format": "smiles",
                "samples_per_complex": 10,
                "inference_steps": 20,
                "device": "cpu",
                "complex_index": 0,
                "box_center": [x, y, z],   # 可选，结合口袋中心（Å）
                "box_size": [dx, dy, dz],  # 可选，搜索盒尺寸（Å）
            }

        Output format 与 DockingAdapter.execute 相同。
        """
        t0 = time.perf_counter()
        protein_path = prepared_input.get("protein_path", "")
        ligand = prepared_input.get("ligand", "")
        ligand_format = prepared_input.get("ligand_format", "smiles")
        samples = prepared_input.get("samples_per_complex", 10)
        complex_index = prepared_input.get("complex_index", 0)
        box_center = prepared_input.get("box_center")
        box_size = prepared_input.get("box_size")

        # 默认搜索盒：若未指定，使用受体几何中心 + 30Å 立方盒
        if box_center is None or box_size is None:
            box_center, box_size = self._estimate_box_from_pdb(protein_path)

        # 1. 输入检查
        errors: list[str] = []
        if not protein_path or not os.path.isfile(protein_path):
            errors.append(f"受体文件不存在: {protein_path}")
        if not ligand:
            errors.append("配体为空")
        if ligand_format not in ("smiles", "sdf", "mol2"):
            errors.append(f"不支持的配体格式: {ligand_format}")

        # 搜索盒必须为 3 元素数值数组——既防止注入，也保证 Vina 收到合法盒参数
        box_center, box_errors = self._coerce_box(box_center, "box_center")
        box_size, box_size_errors = self._coerce_box(box_size, "box_size")
        errors += box_errors + box_size_errors

        if errors:
            return {
                "status": "failed",
                "complex_index": complex_index,
                "errors": errors,
                "poses": [],
                "warnings": [],
            }

        # 2. 创建工作目录并准备输入文件
        work_dir = create_engine_work_dir("vina")
        receptor_basename = os.path.basename(protein_path)

        # 复制受体文件到工作目录
        import shutil
        shutil.copy(protein_path, os.path.join(work_dir, receptor_basename))

        # 3. 在 Docker 容器中执行对接脚本
        # 对接脚本负责：PDB→PDBQT、SMILES→PDBQT、Vina 对接、输出 JSON
        dock_script = self._write_dock_script(
            work_dir, receptor_basename, ligand, ligand_format,
            samples, box_center, box_size,
        )

        exit_code, stdout, stderr = run_in_persistent_container(
            engine_key="docking",
            image=self._image,
            cmd_args=["python", os.path.basename(dock_script)],
            work_dir=work_dir,
            entrypoint="tail",
            timeout=600,
        )

        elapsed = time.perf_counter() - t0

        if exit_code == 1 and "镜像不可用" in stderr:
            return {
                "status": "failed",
                "complex_index": complex_index,
                "errors": [stderr],
                "poses": [],
                "warnings": ["Vina Docker 镜像不可用，请构建 batteryemcl/vina-engine:latest"],
            }

        # 4. 读取对接结果
        # 即使 exit_code != 0，脚本也可能已写入 JSON（如配体准备失败时）。
        # 优先读取 JSON 获取详细错误信息；若 JSON 不存在则用 stderr 兜底。
        result_path = os.path.join(work_dir, "vina_result.json")
        vina_result: dict[str, Any] | None = None
        if os.path.isfile(result_path):
            try:
                with open(result_path, "r", encoding="utf-8") as f:
                    vina_result = json.load(f)
            except (json.JSONDecodeError, OSError):
                vina_result = None

        if vina_result is None:
            return {
                "status": "failed",
                "complex_index": complex_index,
                "errors": [f"Vina 退出码 {exit_code}; stderr: {stderr[-500:]}"],
                "poses": [],
                "warnings": [],
            }

        # 若脚本以非零退出码结束但写了 JSON，将 stderr 追加到 warnings 便于调试
        if exit_code != 0 and stderr.strip():
            vina_result.setdefault("warnings", []).append(
                f"脚本退出码 {exit_code}; stderr: {stderr[-300:]}"
            )

        # 5. 转换为统一输出契约
        poses = []
        for i, (affinity, rmsd_lb, rmsd_ub) in enumerate(
            vina_result.get("poses", [])[:samples], start=1
        ):
            # Vina 亲和力越负越好，转换为置信度（0-1）
            # 经验映射：affinity=-12 → 0.99, affinity=0 → 0.1
            confidence = max(0.1, min(0.99, 1.0 - (affinity + 12) / 12))
            poses.append({
                "rank": i,
                "confidence": round(confidence, 3),
                "affinity_kcal_mol": round(affinity, 2),
                "rmsd_lb": round(rmsd_lb, 2),
                "rmsd_ub": round(rmsd_ub, 2),
                "sdf_path": f"poses/{i:04d}_pose.sdf",
                "metadata": {
                    "method": "autodock_vina",
                    "model": "vina_1.2",
                    "box_center": box_center,
                    "box_size": box_size,
                },
            })

        # 若无位姿（对接或配体准备失败），标记为 failed
        if not poses:
            return {
                "status": "failed",
                "complex_index": complex_index,
                "runtime_seconds": round(elapsed, 2),
                "receptor_path": protein_path,
                "ligand": ligand,
                "poses": [],
                "errors": vina_result.get("warnings", []),
                "warnings": vina_result.get("warnings", []),
            }

        return {
            "status": "completed",
            "complex_index": complex_index,
            "runtime_seconds": round(elapsed, 2),
            "receptor_path": protein_path,
            "ligand": ligand,
            "poses": poses,
            "warnings": vina_result.get("warnings", []),
        }

    def parse_output(self, raw_output: Any) -> dict[str, Any]:
        """解析原始输出为结构化 dict。"""
        if isinstance(raw_output, dict):
            return raw_output
        return {"poses": []}

    def get_resource_requirements(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """返回资源需求。"""
        samples = input_data.get("samples_per_complex", 10)
        return {
            "cpu": 2,
            "memory_mb": 512,
            "gpu": 0,  # Vina 无需 GPU
            "walltime_minutes": max(1, samples // 5),
        }

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    @staticmethod
    def _coerce_box(value: Any, name: str) -> tuple[list[float] | None, list[str]]:
        """将搜索盒参数强校验为 3 元素数值数组。

        返回 (归一化后的列表, 错误列表)。非法输入返回 (None, [错误])，
        保证后续写入生成脚本的值均为受控 float 字面量，杜绝代码注入。
        """
        if value is None:
            return None, []
        if not isinstance(value, (list, tuple)) or len(value) != 3:
            return None, [f"{name} 必须为 [x, y, z] 三元素数值数组"]
        try:
            return [float(v) for v in value], []
        except (TypeError, ValueError):
            return None, [f"{name} 必须为数值"]

    @staticmethod
    def _estimate_box_from_pdb(pdb_path: str) -> tuple[list[float], list[float]]:
        """从 PDB 受体估算结合口袋搜索盒。

        使用受体所有原子的几何中心作为盒中心，盒尺寸固定为 30Å 立方
        （Vina 推荐的盲对接默认值）。
        """
        center = [0.0, 0.0, 0.0]
        count = 0
        try:
            with open(pdb_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith(("ATOM", "HETATM")):
                        try:
                            x = float(line[30:38].strip())
                            y = float(line[38:46].strip())
                            z = float(line[46:54].strip())
                            center[0] += x
                            center[1] += y
                            center[2] += z
                            count += 1
                        except (ValueError, IndexError):
                            continue
            if count > 0:
                center = [round(c / count, 2) for c in center]
        except OSError:
            center = [0.0, 0.0, 0.0]
        return center, [30.0, 30.0, 30.0]

    @staticmethod
    def _write_dock_script(
        work_dir: str,
        receptor_basename: str,
        ligand: str,
        ligand_format: str,
        samples: int,
        box_center: list[float],
        box_size: list[float],
    ) -> str:
        """写入 Vina 对接 Python 脚本到工作目录。

        脚本在 Docker 容器内执行：
        1. OpenBabel 将受体 PDB → PDBQT
        2. meeko 将配体 SMILES → PDBQT
        3. Vina 对接
        4. 输出 JSON 结果
        """
        script_path = os.path.join(work_dir, "vina_dock.py")
        script_content = f'''"""AutoDock Vina 对接脚本 — 在 Docker 容器内执行。"""
import json
import subprocess
import sys
import os

RECEPTOR_PDB = {receptor_basename!r}
RECEPTOR_PDBQT = "receptor.pdbqt"
LIGAND_PDBQT = "ligand.pdbqt"
RESULT_JSON = "vina_result.json"
SMILES = {ligand!r}
LIGAND_FORMAT = {ligand_format!r}
NUM_MODES = {samples!r}
BOX_CENTER = {box_center!r}
BOX_SIZE = {box_size!r}

warnings = []

# 1. 受体 PDB → PDBQT（OpenBabel，rigid receptor 模式）
#    OpenBabel 默认生成带 ROOT/ENDROOT 的柔性 PDBQT（用于配体），
#    Vina 的 set_receptor 不接受 ROOT 标签。使用 -xr 选项生成刚性受体 PDBQT。
#    若 OpenBabel 不可用或转换失败，Vina 1.2+ 也可直接读取 PDB 文件。
try:
    subprocess.run(
        ["obabel", "-ipdb", RECEPTOR_PDB, "-opdbqt", "-xr", "-O", RECEPTOR_PDBQT],
        capture_output=True, check=True, timeout=60,
    )
    # 验证生成的 PDBQT 不含 ROOT 标签（避免 Vina 报错）
    with open(RECEPTOR_PDBQT) as _f:
        _content = _f.read()
    if "ROOT" in _content:
        # OpenBabel -xr 无效，回退到 PDB
        warnings.append("OpenBabel 生成的 PDBQT 含 ROOT 标签，回退到原始 PDB")
        RECEPTOR_PDBQT = RECEPTOR_PDB
except Exception as e:
    # OpenBabel 失败时直接用 PDB（Vina 1.2+ 接受 PDB）
    RECEPTOR_PDBQT = RECEPTOR_PDB
    warnings.append(f"OpenBabel 受体转换失败，使用原始 PDB: {{e}}")

# 2. 配体 SMILES → PDBQT（meeko）
if LIGAND_FORMAT == "smiles":
    try:
        # meeko 0.7 API: prepare() 返回 MoleculeSetup 列表，需用 PDBQTWriterLegacy 写字符串
        from meeko import MoleculePreparation, PDBQTWriterLegacy
        from rdkit import Chem
        from rdkit.Chem import AllChem

        mol = Chem.MolFromSmiles(SMILES)
        if mol is None:
            raise ValueError(f"无效 SMILES: {{SMILES}}")
        mol = Chem.AddHs(mol)
        AllChem.EmbedMolecule(mol)
        AllChem.MMFFOptimizeMolecule(mol)

        preparator = MoleculePreparation()
        molsetup_list = preparator.prepare(mol)
        writer = PDBQTWriterLegacy()
        pdbqt_string, is_ok, err = writer.write_string(molsetup_list[0])
        if not is_ok:
            raise RuntimeError(f"PDBQT 写入失败: {{err}}")
        with open(LIGAND_PDBQT, "w") as f:
            f.write(pdbqt_string)
    except Exception as e:
        print(json.dumps({{"poses": [], "warnings": [f"配体准备失败: {{str(e)}}"]}}))
        with open(RESULT_JSON, "w") as f:
            json.dump({{"poses": [], "warnings": [f"配体准备失败: {{str(e)}}"]}}, f)
        sys.exit(1)
elif LIGAND_FORMAT in ("sdf", "mol2"):
    # 已有文件，尝试 OpenBabel 转 PDBQT（使用相对路径，workdir 已设置）
    try:
        subprocess.run(
            ["obabel", f"-i{{LIGAND_FORMAT}}", f"ligand.{{LIGAND_FORMAT}}",
             "-opdbqt", "-O", LIGAND_PDBQT],
            capture_output=True, check=True, timeout=60,
        )
    except Exception as e:
        print(json.dumps({{"poses": [], "warnings": [f"配体文件转换失败: {{str(e)}}"]}}))
        with open(RESULT_JSON, "w") as f:
            json.dump({{"poses": [], "warnings": [f"配体文件转换失败: {{str(e)}}"]}}, f)
        sys.exit(1)

# 3. Vina 对接
try:
    from vina import Vina

    v = Vina(sf_name="vina")
    v.set_receptor(RECEPTOR_PDBQT)
    v.set_ligand_from_file(LIGAND_PDBQT)
    v.compute_vina_maps(center=BOX_CENTER, box_size=BOX_SIZE)
    v.dock(exhaustiveness=8, n_poses=NUM_MODES)
    energies = v.energies()
    # energies: [[affinity, rmsd_lb, rmsd_ub], ...]
    poses = []
    for row in energies:
        poses.append([float(row[0]), float(row[1]), float(row[2])])

    # 保存最佳位姿 PDBQT（使用相对路径）
    try:
        v.write_poses("best_pose.pdbqt", n_poses=NUM_MODES, overwrite=True)
    except Exception:
        pass

    result = {{"poses": poses, "warnings": warnings}}
except Exception as e:
    result = {{"poses": [], "warnings": warnings + [f"Vina 对接失败: {{str(e)}}"]}}

with open(RESULT_JSON, "w") as f:
    json.dump(result, f)
print(json.dumps(result))
'''
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(script_content)
        return script_path
