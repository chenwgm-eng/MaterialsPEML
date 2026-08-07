"""PySCF 量子化学适配器 — 基于 Docker 容器的真实波函数分析。

通过 ``batteryemcl/science-engine:latest`` 容器调用 PySCF 执行：
- ESP 分析：B3LYP/6-31G* 单点计算 → 分子表面静电势采样
- 轨道分析：HOMO/LUMO 识别 + 能级提取

执行策略：
1. 在临时工作目录中生成 PySCF Python 脚本 + 输入 SMILES
2. 通过 ``docker run --rm -v <workdir>:/work batteryemcl/science-engine`` 执行
3. 解析 JSON 输出文件，结构化返回

当 Docker 不可用时，回退到 RDKitESPAdapter（经验电荷近似）。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from typing import Any

from .execution_adapter import ExecutionAdapter, create_engine_work_dir


# Docker 镜像常量
_PYSCF_DOCKER_IMAGE = os.environ.get(
    "BATTERYEMCL_SCIENCE_IMAGE", "batteryemcl/science-engine:latest"
)

# ESP 计算脚本模板（容器内执行）
_PYSCF_ESP_SCRIPT = '''"""PySCF ESP 分析脚本 — 由 pyscf_adapter.py 生成。"""
import json
import sys

def main():
    smiles = sys.argv[1] if len(sys.argv) > 1 else ""
    bins = int(sys.argv[2]) if len(sys.argv) > 2 else 100
    surface_type = sys.argv[3] if len(sys.argv) > 3 else "molecular"
    out_path = sys.argv[4] if len(sys.argv) > 4 else "esp_result.json"

    result = {"status": "error", "error": "unknown", "results": [], "warnings": []}

    try:
        from rdkit import Chem
        from rdkit.Chem import AllChem
        from pyscf import gto, dft, scf
        import numpy as np

        # 1. RDKit 生成 3D 构象
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            result["error"] = f"SMILES 解析失败: {smiles}"
            with open(out_path, "w") as f:
                json.dump(result, f)
            return
        mol = Chem.AddHs(mol)
        AllChem.EmbedMolecule(mol, randomSeed=42)
        try:
            AllChem.MMFFOptimizeMolecule(mol, maxIters=200)
        except Exception:
            try:
                AllChem.UFFOptimizeMolecule(mol, maxIters=200)
            except Exception:
                pass

        # 2. 构建 PySCF Mole 对象
        conf = mol.GetConformer(0)
        atoms = []
        coords = []
        for i in range(mol.GetNumAtoms()):
            atom = mol.GetAtomWithIdx(i)
            p = conf.GetAtomPosition(i)
            atoms.append(atom.GetSymbol())
            coords.append([p.x, p.y, p.z])

        # 转换为 Bohr (PySCF 默认单位)
        ang_to_bohr = 1.8897259886
        coords_bohr = [[c * ang_to_bohr for c in xyz] for xyz in coords]

        mol_pyscf = gto.M(
            atom=[[atoms[i], coords_bohr[i]] for i in range(len(atoms))],
            basis="6-31G*",
            charge=0,
            spin=0,
            unit="Angstrom",  # 使用 Angstrom 输入，PySCF 自动转换
        )
        # 重新用 Angstrom 坐标构建（覆盖 unit 设置）
        mol_pyscf = gto.M(
            atom=[[atoms[i], coords[i]] for i in range(len(atoms))],
            basis="6-31G*",
            charge=0,
            spin=0,
            unit="Angstrom",
        )

        # 3. DFT 单点计算 (B3LYP)
        mf = dft.RKS(mol_pyscf)
        mf.xc = "B3LYP"
        mf.verbose = 0
        mf.max_cycle = 50
        mf.kernel()

        # 4. 提取轨道能级 (HOMO/LUMO)
        mo_energy = mf.mo_energy  # Hartree
        mo_occ = mf.mo_occ
        # HOMO: 最高占据轨道 (occ > 0)
        homo_idx = max([i for i, o in enumerate(mo_occ) if o > 0], default=-1)
        lumo_idx = min([i for i, o in enumerate(mo_occ) if o == 0], default=-1)
        hartree_to_ev = 27.211386

        homo_energy_ev = float(mo_energy[homo_idx] * hartree_to_ev) if homo_idx >= 0 else None
        lumo_energy_ev = float(mo_energy[lumo_idx] * hartree_to_ev) if lumo_idx >= 0 else None
        gap_ev = (lumo_energy_ev - homo_energy_ev) if (homo_energy_ev is not None and lumo_energy_ev is not None) else None

        # 5. 计算 Mulliken 电荷（使用 net charges，非 populations）
        Mulliken_pop = mf.mulliken_pop()
        # mulliken_pop() 返回 (pop, charges)；charges[1] 是净电荷（可正可负）
        if isinstance(Mulliken_pop[1], dict):
            charges = [float(Mulliken_pop[1].get(sym, 0)) for sym in atoms]
        else:
            charges = [float(q) for q in Mulliken_pop[1]]

        # 6. ESP 表面采样（在 vdw 表面计算静电势）
        # ESP(r) = Σ Z_j/|r-R_j| - ∫ ρ(r')/|r-r'| dr'
        # 简化：用 Mulliken 电荷近似 ESP
        vdw_radii = {"H": 1.20, "C": 1.70, "N": 1.55, "O": 1.52,
                     "F": 1.47, "Cl": 1.75, "Br": 1.85, "I": 1.98,
                     "S": 1.80, "P": 1.80}
        conversion = 332.0637  # e·Å → kcal/mol
        import math

        esp_values = []
        n_samples = 8
        for i, (q_i, pos_i, sym_i) in enumerate(zip(charges, coords, atoms)):
            r_i = vdw_radii.get(sym_i, 1.70)
            for k in range(n_samples):
                phi = math.acos(1 - 2 * (k + 0.5) / n_samples)
                theta = math.pi * (1 + 5 ** 0.5) * (k + 0.5)
                px = pos_i[0] + r_i * math.sin(phi) * math.cos(theta)
                py = pos_i[1] + r_i * math.sin(phi) * math.sin(theta)
                pz = pos_i[2] + r_i * math.cos(phi)
                esp = 0.0
                for j, (q_j, pos_j) in enumerate(zip(charges, coords)):
                    if j == i:
                        continue
                    dx, dy, dz = px - pos_j[0], py - pos_j[1], pz - pos_j[2]
                    dist = math.sqrt(dx * dx + dy * dy + dz * dz)
                    if dist < 0.1:
                        continue
                    esp += q_j / dist
                esp_values.append(esp * conversion)

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
        distribution = [0] * bins
        if esp_values and esp_max > esp_min:
            bin_width = (esp_max - esp_min) / bins
            for v in esp_values:
                idx = int((v - esp_min) / bin_width)
                if idx >= bins:
                    idx = bins - 1
                distribution[idx] += 1

        # vdw 表面积估算
        surface_area = sum(4 * math.pi * vdw_radii.get(s, 1.70) ** 2 for s in atoms)

        results = [
            {
                "type": "esp_surface",
                "claim": "ESP 表面统计分析 (PySCF B3LYP/6-31G*)",
                "value": {
                    "min": round(esp_min, 4),
                    "max": round(esp_max, 4),
                    "mean": round(esp_mean, 4),
                    "variance": round(esp_var, 4),
                    "positive_area_pct": pos_pct,
                    "negative_area_pct": neg_pct,
                },
                "unit": "kcal/mol",
                "confidence": 0.92,
                "metadata": {
                    "method": "PySCF B3LYP/6-31G* Mulliken ESP",
                    "smiles": smiles,
                    "n_atoms": len(atoms),
                    "engine": "pyscf_docker",
                },
            },
            {
                "type": "esp_area",
                "claim": "ESP 区间面积分布 (PySCF)",
                "value": {
                    "bins": bins,
                    "distribution": distribution,
                    "range": [round(esp_min, 4), round(esp_max, 4)],
                },
                "unit": "kcal/mol",
                "confidence": 0.88,
                "metadata": {"method": "PySCF Mulliken ESP histogram", "smiles": smiles},
            },
            {
                "type": "esp_atomic",
                "claim": "原子 Mulliken 电荷与 ESP 统计",
                "value": {
                    "atom_count": len(atoms),
                    "atom_charges": [
                        {"atom": atoms[i], "charge": round(charges[i], 4)}
                        for i in range(len(atoms))
                    ],
                    "local_min_charge": round(min(charges), 4) if charges else 0.0,
                    "local_max_charge": round(max(charges), 4) if charges else 0.0,
                    "surface_area_ang2": round(surface_area, 2),
                },
                "unit": "e (电子电荷)",
                "confidence": 0.88,
                "metadata": {"method": "PySCF Mulliken population", "smiles": smiles},
            },
        ]

        result = {
            "status": "completed",
            "results": results,
            "warnings": [],
            "engine": "pyscf_docker",
            "homo_energy_eV": homo_energy_ev,
            "lumo_energy_eV": lumo_energy_ev,
            "gap_eV": gap_ev,
        }

    except Exception as exc:
        result = {
            "status": "error",
            "error": f"PySCF 执行失败: {exc}",
            "results": [],
            "warnings": [f"PySCF 异常: {exc}"],
        }

    with open(out_path, "w") as f:
        json.dump(result, f, ensure_ascii=False, default=str)


if __name__ == "__main__":
    main()
'''

# 轨道分析脚本模板
_PYSCF_ORBITALS_SCRIPT = '''"""PySCF 轨道分析脚本 — 由 pyscf_adapter.py 生成。"""
import json
import sys

def main():
    smiles = sys.argv[1] if len(sys.argv) > 1 else ""
    below_homo = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    above_lumo = int(sys.argv[3]) if len(sys.argv) > 3 else 3
    out_path = sys.argv[4] if len(sys.argv) > 4 else "orbitals_result.json"

    result = {"status": "error", "error": "unknown", "results": [], "warnings": []}

    try:
        from rdkit import Chem
        from rdkit.Chem import AllChem
        from pyscf import gto, dft
        import numpy as np

        # 1. RDKit 生成 3D 构象
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            result["error"] = f"SMILES 解析失败: {smiles}"
            with open(out_path, "w") as f:
                json.dump(result, f)
            return
        mol = Chem.AddHs(mol)
        AllChem.EmbedMolecule(mol, randomSeed=42)
        try:
            AllChem.MMFFOptimizeMolecule(mol, maxIters=200)
        except Exception:
            pass

        # 2. 构建 PySCF Mole 对象
        conf = mol.GetConformer(0)
        atoms = []
        coords = []
        for i in range(mol.GetNumAtoms()):
            atom = mol.GetAtomWithIdx(i)
            p = conf.GetAtomPosition(i)
            atoms.append(atom.GetSymbol())
            coords.append([p.x, p.y, p.z])

        mol_pyscf = gto.M(
            atom=[[atoms[i], coords[i]] for i in range(len(atoms))],
            basis="6-31G*",
            charge=0,
            spin=0,
            unit="Angstrom",
        )

        # 3. DFT 单点计算 (B3LYP)
        mf = dft.RKS(mol_pyscf)
        mf.xc = "B3LYP"
        mf.verbose = 0
        mf.max_cycle = 50
        mf.kernel()

        # 4. 提取轨道能级
        mo_energy = mf.mo_energy  # Hartree
        mo_occ = mf.mo_occ
        hartree_to_ev = 27.211386

        homo_idx = max([i for i, o in enumerate(mo_occ) if o > 0], default=-1)
        lumo_idx = min([i for i, o in enumerate(mo_occ) if o == 0], default=-1)

        homo_energy_ev = float(mo_energy[homo_idx] * hartree_to_ev) if homo_idx >= 0 else None
        lumo_energy_ev = float(mo_energy[lumo_idx] * hartree_to_ev) if lumo_idx >= 0 else None
        gap_ev = (lumo_energy_ev - homo_energy_ev) if (homo_energy_ev is not None and lumo_energy_ev is not None) else None

        # 构建 HOMO-LUMO 附近轨道列表
        orbital_list = []
        start_idx = max(0, homo_idx - below_homo)
        end_idx = min(len(mo_energy) - 1, lumo_idx + above_lumo)

        for i in range(start_idx, end_idx + 1):
            if i < homo_idx:
                label = f"HOMO-{homo_idx - i}"
                occ = float(mo_occ[i])
            elif i == homo_idx:
                label = "HOMO"
                occ = float(mo_occ[i])
            elif i == lumo_idx:
                label = "LUMO"
                occ = float(mo_occ[i])
            else:
                label = f"LUMO+{i - lumo_idx}"
                occ = float(mo_occ[i])
            orbital_list.append({
                "index": label,
                "energy_eV": round(float(mo_energy[i] * hartree_to_ev), 4),
                "occupation": occ,
                "symmetry": "A",
            })

        results = [
            {
                "type": "orbital_energy",
                "claim": f"轨道能级分析 (PySCF B3LYP/6-31G*)",
                "value": {
                    "orbitals": orbital_list,
                    "homo_index": "HOMO",
                    "lumo_index": "LUMO",
                    "homo_energy_eV": round(homo_energy_ev, 4) if homo_energy_ev else None,
                    "lumo_energy_eV": round(lumo_energy_ev, 4) if lumo_energy_ev else None,
                },
                "unit": "eV",
                "confidence": 0.95,
                "metadata": {
                    "method": "PySCF B3LYP/6-31G* DFT",
                    "smiles": smiles,
                    "engine": "pyscf_docker",
                    "n_orbitals": len(orbital_list),
                },
            },
            {
                "type": "orbital_gap",
                "claim": "HOMO-LUMO 能隙",
                "value": round(gap_ev, 4) if gap_ev else None,
                "unit": "eV",
                "confidence": 0.95,
                "metadata": {
                    "method": "PySCF B3LYP/6-31G* DFT",
                    "smiles": smiles,
                },
            },
        ]

        result = {
            "status": "completed",
            "results": results,
            "warnings": [],
            "engine": "pyscf_docker",
            "homo_energy_eV": homo_energy_ev,
            "lumo_energy_eV": lumo_energy_ev,
            "gap_eV": gap_ev,
        }

    except Exception as exc:
        result = {
            "status": "error",
            "error": f"PySCF 轨道分析失败: {exc}",
            "results": [],
            "warnings": [f"PySCF 异常: {exc}"],
        }

    with open(out_path, "w") as f:
        json.dump(result, f, ensure_ascii=False, default=str)


if __name__ == "__main__":
    main()
'''


class PySCFAdapter(ExecutionAdapter):
    """基于 Docker 容器的 PySCF 量子化学适配器。

    通过 ``batteryemcl/science-engine:latest`` 镜像运行 PySCF，提供：
    - ESP 分析：B3LYP/6-31G* 单点计算 + Mulliken 电荷 ESP 采样
    - 轨道分析：HOMO/LUMO 识别 + 真实 DFT 轨道能级

    与 wavefunction_analysis.application._PlaceholderAdapter 接口兼容
    （实现 execute_esp / execute_orbitals / execute_render / parse_output）。
    """

    def __init__(self) -> None:
        self._docker_available: bool | None = None  # 延迟探测

    # ------------------------------------------------------------------
    # Docker 可用性检查
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        """公共可用性检查 — Docker + science-engine 镜像均可访问时返回 True。"""
        return self._check_docker()

    def _check_docker(self) -> bool:
        """检查 docker CLI 与 science-engine 镜像是否可用（结果缓存）。"""
        if self._docker_available is not None:
            return self._docker_available
        try:
            # docker CLI 可用
            result = subprocess.run(
                ["docker", "version", "--format", "{{.Server.Version}}"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                self._docker_available = False
                return False
            # science-engine 镜像存在
            inspect = subprocess.run(
                ["docker", "image", "inspect", _PYSCF_DOCKER_IMAGE],
                capture_output=True, text=True, timeout=10,
            )
            self._docker_available = inspect.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            self._docker_available = False
        return self._docker_available

    # ------------------------------------------------------------------
    # Public API (与 _PlaceholderAdapter / RDKitESPAdapter 兼容)
    # ------------------------------------------------------------------

    def execute(self, prepared_input: dict[str, Any]) -> dict[str, Any]:
        """通用执行入口（根据 command 分发）。"""
        command = prepared_input.get("command", "analyze_esp")
        if command == "analyze_esp":
            return self.execute_esp(prepared_input)
        elif command == "analyze_orbitals":
            return self.execute_orbitals(prepared_input)
        elif command == "render_orbital":
            return self._placeholder_render(prepared_input)
        return {"status": "unknown", "results": [], "warnings": [f"未知命令: {command}"]}

    def execute_esp(self, prepared_input: dict[str, Any]) -> dict[str, Any]:
        """执行 ESP 分析 — 调用 Docker science-engine 运行 PySCF。"""
        smiles = prepared_input.get("input_file", "")
        bins = int(prepared_input.get("bins", 100) or 100)
        surface_type = prepared_input.get("surface_type", "molecular")

        if not smiles or _looks_like_path(smiles):
            return {
                "status": "error",
                "error": f"PySCF 适配器仅支持 SMILES 输入，收到: {smiles}",
                "results": [],
                "warnings": ["输入不是 SMILES 字符串"],
            }

        if not self._check_docker():
            return {
                "status": "error",
                "error": f"Docker 镜像 {_PYSCF_DOCKER_IMAGE} 不可用",
                "results": [],
                "warnings": [
                    f"PySCF Docker 不可用；请构建镜像："
                    f"docker build -t {_PYSCF_DOCKER_IMAGE} -f docker/engines/science/Dockerfile docker/engines/science"
                ],
            }

        # 1. 创建临时工作目录
        work_dir = create_engine_work_dir("pyscf_esp")
        try:
            # 2. 写入 ESP 脚本
            script_path = os.path.join(work_dir, "pyscf_esp.py")
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(_PYSCF_ESP_SCRIPT)

            # 3. 通过 Docker 执行
            # NOTE: 常驻容器使用 docker exec -w /work/<rel>，使用相对路径
            exit_code, stdout, stderr = self._run_docker(
                work_dir,
                ["python", "pyscf_esp.py", smiles, str(bins), surface_type, "esp_result.json"],
                timeout=600,
            )

            if exit_code != 0:
                return {
                    "status": "error",
                    "error": f"PySCF Docker 执行失败 (exit={exit_code}): {stderr[-500:]}",
                    "results": [],
                    "warnings": [f"Docker stderr: {stderr[-300:]}"],
                }

            # 4. 解析 JSON 输出
            result_path = os.path.join(work_dir, "esp_result.json")
            if not os.path.isfile(result_path):
                return {
                    "status": "error",
                    "error": "PySCF 未生成结果文件",
                    "results": [],
                    "warnings": [f"stdout: {stdout[-300:]}"],
                }

            with open(result_path, encoding="utf-8") as f:
                result = json.load(f)

            return result

        except subprocess.TimeoutExpired:
            return {
                "status": "error",
                "error": "PySCF Docker 执行超时（600秒）",
                "results": [],
                "warnings": ["超时"],
            }
        except Exception as exc:
            return {
                "status": "error",
                "error": f"PySCF 调用异常: {exc}",
                "results": [],
                "warnings": [f"异常: {exc}"],
            }
        finally:
            # 清理临时目录
            try:
                shutil.rmtree(work_dir, ignore_errors=True)
            except Exception:
                pass

    def execute_orbitals(self, prepared_input: dict[str, Any]) -> dict[str, Any]:
        """执行轨道分析 — 调用 Docker science-engine 运行 PySCF。"""
        smiles = prepared_input.get("input_file", "")
        below_homo = int(prepared_input.get("below_homo", 3) or 3)
        above_lumo = int(prepared_input.get("above_lumo", 3) or 3)

        if not smiles or _looks_like_path(smiles):
            return {
                "status": "error",
                "error": f"PySCF 适配器仅支持 SMILES 输入，收到: {smiles}",
                "results": [],
                "warnings": ["输入不是 SMILES 字符串"],
            }

        if not self._check_docker():
            return {
                "status": "error",
                "error": f"Docker 镜像 {_PYSCF_DOCKER_IMAGE} 不可用",
                "results": [],
                "warnings": [f"请构建镜像：docker build -t {_PYSCF_DOCKER_IMAGE} -f docker/engines/science/Dockerfile docker/engines/science"],
            }

        work_dir = create_engine_work_dir("pyscf_orb")
        try:
            script_path = os.path.join(work_dir, "pyscf_orbitals.py")
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(_PYSCF_ORBITALS_SCRIPT)

            exit_code, stdout, stderr = self._run_docker(
                work_dir,
                ["python", "pyscf_orbitals.py", smiles, str(below_homo), str(above_lumo), "orbitals_result.json"],
                timeout=600,
            )

            if exit_code != 0:
                return {
                    "status": "error",
                    "error": f"PySCF Docker 执行失败 (exit={exit_code}): {stderr[-500:]}",
                    "results": [],
                    "warnings": [f"Docker stderr: {stderr[-300:]}"],
                }

            result_path = os.path.join(work_dir, "orbitals_result.json")
            if not os.path.isfile(result_path):
                return {
                    "status": "error",
                    "error": "PySCF 未生成结果文件",
                    "results": [],
                    "warnings": [f"stdout: {stdout[-300:]}"],
                }

            with open(result_path, encoding="utf-8") as f:
                result = json.load(f)

            return result

        except subprocess.TimeoutExpired:
            return {
                "status": "error",
                "error": "PySCF Docker 执行超时（600秒）",
                "results": [],
                "warnings": ["超时"],
            }
        except Exception as exc:
            return {
                "status": "error",
                "error": f"PySCF 调用异常: {exc}",
                "results": [],
                "warnings": [f"异常: {exc}"],
            }
        finally:
            try:
                shutil.rmtree(work_dir, ignore_errors=True)
            except Exception:
                pass

    def execute_render(self, prepared_input: dict[str, Any]) -> dict[str, Any]:
        """渲染 — PySCF 不直接支持 VMD 渲染，返回占位脚本。"""
        return self._placeholder_render(prepared_input)

    def parse_output(self, raw_output: Any) -> dict[str, Any]:
        if isinstance(raw_output, dict):
            return raw_output
        return {"status": "unknown", "results": []}

    def get_resource_requirements(self, input_data: dict[str, Any]) -> dict[str, Any]:
        return {"cpu": 2, "memory_mb": 2048, "walltime_minutes": 15}

    def validate_input(self, input_data: dict[str, Any]) -> list[str]:
        return []

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    @staticmethod
    def _run_docker(
        work_dir: str,
        cmd_args: list[str],
        timeout: int = 600,
    ) -> tuple[int, str, str]:
        """在常驻 Docker 容器中执行命令，挂载 work_dir 到 /work。

        Args:
            work_dir: 主机工作目录（含输入脚本）
            cmd_args: 容器内命令参数（必须包含解释器，如
                ["python", "/work/script.py", "arg1"]）
            timeout: 超时秒数

        Returns:
            (exit_code, stdout, stderr)

        Note:
            常驻容器启动时 entrypoint 被覆盖为 ``tail`` 以保持存活，
            实际命令通过 ``docker exec`` 执行，因此 cmd_args 必须显式
            包含解释器（如 ``python``），不能依赖镜像原 ENTRYPOINT。
        """
        from .docker_executor import run_in_persistent_container

        # 常驻容器：entrypoint=tail 保持存活，docker exec 调用 python
        return run_in_persistent_container(
            engine_key="science",
            image=_PYSCF_DOCKER_IMAGE,
            cmd_args=cmd_args,
            work_dir=work_dir,
            entrypoint="tail",
            timeout=timeout,
        )

    @staticmethod
    def _placeholder_render(prepared_input: dict[str, Any]) -> dict[str, Any]:
        """渲染占位 — PySCF 不支持 VMD 渲染。"""
        render_type = prepared_input.get("render_type", "orbital")
        image_format = prepared_input.get("image_format", "png")
        return {
            "status": "completed",
            "results": [
                {
                    "type": "render_script",
                    "claim": f"{'ESP' if render_type == 'esp' else '轨道'} 渲染 VMD 脚本 (占位)",
                    "value": {
                        "script": f"# placeholder VMD script for {render_type} rendering\n# PySCF 不支持 VMD 渲染",
                        "engine": "vmd",
                        "input_dir": prepared_input.get("input_dir", "."),
                    },
                    "unit": "",
                    "confidence": 0.30,
                    "metadata": {"method": "placeholder", "warning": "PySCF 不支持 VMD 渲染"},
                },
                {
                    "type": "render_image",
                    "claim": f"{'ESP' if render_type == 'esp' else '轨道'} 渲染图片 (占位)",
                    "value": f"{render_type}_render.{image_format}",
                    "unit": "",
                    "confidence": 0.30,
                    "metadata": {"method": "placeholder", "note": "需 VMD 才能渲染"},
                },
            ],
            "warnings": ["PySCF 不支持 VMD 渲染，仅返回占位"],
        }


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
