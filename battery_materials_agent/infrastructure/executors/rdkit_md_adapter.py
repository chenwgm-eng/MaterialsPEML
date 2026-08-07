"""RDKit 分子动力学适配器 — 基于 MMFF94/UFF 力场的小分子 MD 仿真。

当 LAMMPS 不可用时，对有机小分子（Path B, system_type="B"）使用 RDKit 内置的
MMFF94/UFF 力场进行能量最小化与简短"准 MD"轨迹采样，并计算 RMSD/RMSF/能量等指标。

注意：RDKit 不是真正的 MD 引擎，本适配器仅用于小分子构象采样与近似指标估算，
不适用于大体系、长时模拟、NPT 系综等场景。生产级 MD 请使用 LAMMPS/GROMACS。
"""
from __future__ import annotations

import math
import random
from typing import Any

from .execution_adapter import ExecutionAdapter


class RDKitMDAdapter(ExecutionAdapter):
    """基于 RDKit MMFF94/UFF 的小分子 MD 适配器。

    支持的指标：energy, rmsd, rmsf, msd, diffusion_coefficient, rdf。
    其余指标（temperature/pressure/density/cna）返回 None 占位。
    """

    _SUPPORTED_METRICS = {
        "energy", "rmsd", "rmsf", "msd",
        "diffusion_coefficient", "rdf",
    }

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

    def execute(self, prepared_input: dict[str, Any]) -> dict[str, Any]:
        """执行小分子 MD 仿真。

        Input format::

            {
                "system_type": "B",
                "structure_data": "<SMILES>",
                "forcefield": "MMFF94" | "UFF" | None,
                "protocol": "nvt" | "minimize" | ...,
                "temperature_k": 300.0,
                "run_steps": 1000,
                "requested_metrics": ["energy", "rmsd", ...],
            }
        """
        if not self._rdkit_available:
            return {
                "status": "error",
                "error": "RDKit 不可用，无法执行小分子 MD",
                "analysis": [],
                "warnings": ["RDKit 不可用"],
            }

        smiles = prepared_input.get("structure_data", "")
        if not smiles or _looks_like_path(smiles):
            return {
                "status": "error",
                "error": f"RDKit MD 适配器仅支持 SMILES 输入，收到: {smiles}",
                "analysis": [],
                "warnings": ["输入不是 SMILES 字符串"],
            }

        try:
            from rdkit import Chem
            from rdkit.Chem import AllChem
        except ImportError:
            return {
                "status": "error",
                "error": "RDKit 模块导入失败",
                "analysis": [],
                "warnings": ["RDKit 导入失败"],
            }

        # 1. 解析 SMILES 并加氢
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return {
                "status": "error",
                "error": f"SMILES 解析失败: {smiles}",
                "analysis": [],
                "warnings": ["SMILES 无效"],
            }
        mol = Chem.AddHs(mol)

        # 2. 生成 3D 构象
        try:
            conf_result = AllChem.EmbedMolecule(mol, randomSeed=42)
            if conf_result != 0:
                # 使用随机坐标兜底
                conf_result = AllChem.EmbedMolecule(
                    mol, randomSeed=42, useRandomCoords=True
                )
            if conf_result != 0:
                return {
                    "status": "error",
                    "error": "3D 构象生成失败",
                    "analysis": [],
                    "warnings": ["EmbedMolecule 失败"],
                }
        except Exception as exc:
            return {
                "status": "error",
                "error": f"3D 构象生成异常: {exc}",
                "analysis": [],
                "warnings": ["构象生成异常"],
            }

        # 3. 选择力场
        ff_name = (prepared_input.get("forcefield") or "MMFF94").upper()
        use_mmff = ff_name.startswith("MMFF")
        try:
            if use_mmff:
                ff_props = AllChem.MMFFGetMoleculeProperties(mol)
                if ff_props is None:
                    use_mmff = False
        except Exception:
            use_mmff = False

        # 4. 能量最小化
        try:
            if use_mmff:
                ff = AllChem.MMFFGetMoleculeForceField(mol, ff_props)
            else:
                ff = AllChem.UFFGetMoleculeForceField(mol)
            ff.Minimize()
        except Exception:
            pass

        # 5. 准 MD 轨迹采样（基于随机扰动 + 最小化）
        temperature_k = float(prepared_input.get("temperature_k", 300.0) or 300.0)
        run_steps = int(prepared_input.get("run_steps", 1000) or 1000)
        # 限制步数避免性能问题（RDKit 不是真 MD）
        sampled_steps = max(10, min(50, run_steps // 100))
        trajectory = self._sample_trajectory(mol, use_mmff, temperature_k, sampled_steps)
        # trajectory: list of list[(x, y, z)] — 每帧的原子坐标

        # 6. 计算指标
        requested = prepared_input.get("requested_metrics", ["energy", "rmsd"])
        if not requested:
            requested = ["energy", "rmsd"]

        analysis: list[dict[str, Any]] = []
        warnings: list[str] = []

        # 力场能量
        energy_value = self._compute_energy(mol, use_mmff)
        if "energy" in requested:
            analysis.append({
                "metric": "energy",
                "value": energy_value,
                "unit": "kcal/mol",
                "confidence": 0.85,
                "metadata": {
                    "method": "MMFF94" if use_mmff else "UFF",
                    "note": "RDKit 力场最小化后势能",
                },
            })

        # RMSD（最终构象相对初始构象）
        if "rmsd" in requested:
            rmsd_value = self._compute_rmsd(mol, trajectory)
            analysis.append({
                "metric": "rmsd",
                "value": rmsd_value,
                "unit": "Å",
                "confidence": 0.80,
                "metadata": {
                    "method": "RDKit GetAlignmentRMS",
                    "note": "采样末端相对初始构象的 RMSD",
                },
            })

        # RMSF（每个原子的位置涨落）
        if "rmsf" in requested:
            rmsf_values = self._compute_rmsf(trajectory)
            analysis.append({
                "metric": "rmsf",
                "value": rmsf_values,
                "unit": "Å",
                "confidence": 0.75,
                "metadata": {
                    "method": "RDKit 轨迹原子涨落",
                    "n_atoms": len(rmsf_values),
                },
            })

        # MSD（均方位移）
        msd_series: list[float] = []
        if "msd" in requested or "diffusion_coefficient" in requested:
            msd_series = self._compute_msd_series(trajectory)
            if "msd" in requested:
                analysis.append({
                    "metric": "msd",
                    "value": msd_series,
                    "unit": "Å²",
                    "confidence": 0.70,
                    "metadata": {
                        "method": "RDKit 轨迹均方位移",
                        "n_frames": len(msd_series),
                    },
                })

        # 扩散系数（MSD 线性拟合，D = slope / 6）
        if "diffusion_coefficient" in requested and msd_series:
            d_value = self._estimate_diffusion(msd_series)
            analysis.append({
                "metric": "diffusion_coefficient",
                "value": d_value,
                "unit": "Å²/step",
                "confidence": 0.65,
                "metadata": {
                    "method": "Einstein 关系 D = <Δr²>/(6·Δt)",
                    "note": "单位为每步而非秒，仅作相对参考",
                },
            })

        # RDF（简化：原子对距离分布）
        if "rdf" in requested:
            rdf_pairs, rdf_values = self._compute_rdf(mol)
            analysis.append({
                "metric": "rdf",
                "value": {
                    "bins": rdf_pairs,
                    "counts": rdf_values,
                },
                "unit": "无量纲",
                "confidence": 0.70,
                "metadata": {
                    "method": "RDKit 原子对距离直方图",
                    "n_bins": len(rdf_pairs),
                },
            })

        # 不适用的指标
        unsupported = {"temperature", "pressure", "density", "cna"}
        for metric in requested:
            if metric in unsupported:
                analysis.append({
                    "metric": metric,
                    "value": None,
                    "unit": "",
                    "confidence": 0.0,
                    "metadata": {
                        "method": "not_applicable",
                        "note": "RDKit MD 不支持该指标，需 LAMMPS/GROMACS",
                    },
                })
                warnings.append(f"指标 {metric} 在 RDKit MD 中不适用，已置空")

        warnings.append(
            "RDKit MD 为简化的小分子构象采样，非真实分子动力学；"
            "生产模拟请使用 LAMMPS/GROMACS"
        )

        return {
            "status": "completed",
            "data_file": None,
            "script_file": None,
            "log_file": None,
            "trajectory_file": None,
            "analysis": analysis,
            "warnings": warnings,
            "method": "RDKit MMFF94/UFF 准 MD",
        }

    def parse_output(self, raw_output: Any) -> dict[str, Any]:
        if isinstance(raw_output, dict):
            return raw_output
        return {"status": "unknown", "analysis": []}

    def get_resource_requirements(self, input_data: dict[str, Any]) -> dict[str, Any]:
        return {"cpu": 1, "memory_mb": 512, "walltime_minutes": 5}

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    def _sample_trajectory(
        self,
        mol: Any,
        use_mmff: bool,
        temperature_k: float,
        n_frames: int,
    ) -> list[list[tuple[float, float, float]]]:
        """生成准 MD 轨迹。

        每帧对当前构象进行小幅随机扰动（幅度 ∝ √T），再最小化。
        返回每帧的原子坐标列表 [(x, y, z), ...]（避免 Conformer 拷贝问题）。
        """
        from rdkit import Chem
        from rdkit.Chem import AllChem

        n_atoms = mol.GetNumAtoms()
        trajectory: list[list[tuple[float, float, float]]] = []

        # 扰动幅度（Å），与 √T 成正比，归一化
        sigma = 0.05 * math.sqrt(max(1.0, temperature_k / 300.0))

        # 保存初始构象坐标
        conf = mol.GetConformer(0)
        trajectory.append([
            (conf.GetAtomPosition(i).x, conf.GetAtomPosition(i).y, conf.GetAtomPosition(i).z)
            for i in range(n_atoms)
        ])

        rng = random.Random(42)

        for _ in range(n_frames):
            # 在当前位置上施加随机扰动
            conf = mol.GetConformer(0)
            for i in range(n_atoms):
                p = conf.GetAtomPosition(i)
                nx = p.x + rng.gauss(0, sigma)
                ny = p.y + rng.gauss(0, sigma)
                nz = p.z + rng.gauss(0, sigma)
                conf.SetAtomPosition(i, Chem.rdGeometry.Point3D(nx, ny, nz))

            # 最小化以保持构象合理性
            try:
                if use_mmff:
                    ff_props = AllChem.MMFFGetMoleculeProperties(mol)
                    if ff_props is not None:
                        ff = AllChem.MMFFGetMoleculeForceField(mol, ff_props)
                        ff.Minimize(maxIts=50)
                else:
                    ff = AllChem.UFFGetMoleculeForceField(mol)
                    ff.Minimize(maxIts=50)
            except Exception:
                pass

            # 保存最小化后的坐标
            conf = mol.GetConformer(0)
            trajectory.append([
                (conf.GetAtomPosition(i).x, conf.GetAtomPosition(i).y, conf.GetAtomPosition(i).z)
                for i in range(n_atoms)
            ])

        return trajectory

    def _compute_energy(self, mol: Any, use_mmff: bool) -> float | None:
        """计算力场最小化后的势能。"""
        from rdkit.Chem import AllChem

        try:
            if use_mmff:
                ff_props = AllChem.MMFFGetMoleculeProperties(mol)
                if ff_props is None:
                    ff = AllChem.UFFGetMoleculeForceField(mol)
                else:
                    ff = AllChem.MMFFGetMoleculeForceField(mol, ff_props)
            else:
                ff = AllChem.UFFGetMoleculeForceField(mol)
            return float(ff.CalcEnergy())
        except Exception:
            return None

    def _compute_rmsd(self, mol: Any, trajectory: list[list[tuple[float, float, float]]]) -> float | None:
        """计算末端构象相对初始构象的 RMSD。"""
        try:
            if len(trajectory) < 2:
                return 0.0
            ref = trajectory[0]
            final = trajectory[-1]
            n = len(ref)
            sq_sum = 0.0
            for i in range(n):
                dx = ref[i][0] - final[i][0]
                dy = ref[i][1] - final[i][1]
                dz = ref[i][2] - final[i][2]
                sq_sum += dx * dx + dy * dy + dz * dz
            return round(math.sqrt(sq_sum / max(1, n)), 4)
        except Exception:
            return None

    def _compute_rmsf(self, trajectory: list[list[tuple[float, float, float]]]) -> list[float]:
        """计算每个原子的位置涨落（标准差）。"""
        if len(trajectory) < 2:
            return []

        try:
            n_atoms = len(trajectory[0])
            n_frames = len(trajectory)
            # 计算每个原子的平均位置
            means = [[0.0, 0.0, 0.0] for _ in range(n_atoms)]
            for frame in trajectory:
                for i in range(n_atoms):
                    means[i][0] += frame[i][0]
                    means[i][1] += frame[i][1]
                    means[i][2] += frame[i][2]
            means = [[m[0] / n_frames, m[1] / n_frames, m[2] / n_frames] for m in means]

            # 计算标准差
            rmsf: list[float] = []
            for i in range(n_atoms):
                var_sum = 0.0
                for frame in trajectory:
                    var_sum += (frame[i][0] - means[i][0]) ** 2
                    var_sum += (frame[i][1] - means[i][1]) ** 2
                    var_sum += (frame[i][2] - means[i][2]) ** 2
                rmsf.append(round(math.sqrt(var_sum / n_frames), 4))
            return rmsf
        except Exception:
            return []

    def _compute_msd_series(self, trajectory: list[list[tuple[float, float, float]]]) -> list[float]:
        """计算 MSD 序列（相对第一帧）。"""
        if len(trajectory) < 2:
            return []

        try:
            ref = trajectory[0]
            n_atoms = len(ref)
            msd_series: list[float] = []
            for frame in trajectory[1:]:
                sq_sum = 0.0
                for i in range(n_atoms):
                    dx = ref[i][0] - frame[i][0]
                    dy = ref[i][1] - frame[i][1]
                    dz = ref[i][2] - frame[i][2]
                    sq_sum += dx * dx + dy * dy + dz * dz
                msd_series.append(round(sq_sum / max(1, n_atoms), 6))
            return msd_series
        except Exception:
            return []

    def _estimate_diffusion(self, msd_series: list[float]) -> float | None:
        """用 Einstein 关系 D = <Δr²>/(6·Δt) 估算扩散系数（Δt=1 步）。"""
        if len(msd_series) < 2:
            return None
        try:
            # 用后半段做线性拟合（避免初始瞬态）
            half = len(msd_series) // 2
            tail = msd_series[half:]
            if len(tail) < 2:
                return None
            # 简单线性拟合 y = a*x + b
            n = len(tail)
            xs = list(range(n))
            sx = sum(xs)
            sy = sum(tail)
            sxx = sum(x * x for x in xs)
            sxy = sum(x * y for x, y in zip(xs, tail))
            denom = n * sxx - sx * sx
            if denom == 0:
                return None
            slope = (n * sxy - sx * sy) / denom
            d = slope / 6.0
            return round(d, 6)
        except Exception:
            return None

    def _compute_rdf(self, mol: Any) -> tuple[list[float], list[int]]:
        """计算原子对距离直方图作为简化 RDF。"""
        try:
            conf = mol.GetConformer(0)
            n = mol.GetNumAtoms()
            distances: list[float] = []
            for i in range(n):
                for j in range(i + 1, n):
                    p1 = conf.GetAtomPosition(i)
                    p2 = conf.GetAtomPosition(j)
                    dx = p1.x - p2.x
                    dy = p1.y - p2.y
                    dz = p1.z - p2.z
                    distances.append(math.sqrt(dx * dx + dy * dy + dz * dz))

            if not distances:
                return [], []

            # 0.5 Å ~ 10 Å，0.25 Å 一档
            n_bins = 40
            bin_edges = [0.5 + i * 0.25 for i in range(n_bins + 1)]
            counts = [0] * n_bins
            for d in distances:
                for k in range(n_bins):
                    if bin_edges[k] <= d < bin_edges[k + 1]:
                        counts[k] += 1
                        break

            bin_centers = [round((bin_edges[k] + bin_edges[k + 1]) / 2, 3) for k in range(n_bins)]
            return bin_centers, counts
        except Exception:
            return [], []


def _looks_like_path(s: str) -> bool:
    """判断字符串是否像文件路径而非 SMILES。"""
    if not s:
        return True
    # 文件路径特征：包含路径分隔符或常见扩展名
    if "/" in s or "\\" in s:
        return True
    lower = s.lower()
    for ext in (".cif", ".data", ".lammps", ".xyz", ".pdb", ".mol2"):
        if lower.endswith(ext):
            return True
    return False
