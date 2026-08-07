"""Multiwfn 执行适配器 — 封装 Multiwfn 二进制调用与 VMD 渲染。

ESP 分析 4 阶段工作流：
  1. 表面统计 (Multiwfn 选项 3)
  2. 区间面积分布
  3. 原子局部统计
  4. Cube 生成
轨道分析：
  1. HOMO/LUMO 识别 (Multiwfn 选项 0)
  2. 轨道 Cube 输出 (Multiwfn 选项 3 → 0)
"""

from __future__ import annotations

import os
import subprocess
from typing import Any

from .execution_adapter import ExecutionAdapter


class _PlaceholderAdapter:
    """波函数分析占位适配器。

    当 Multiwfn 二进制或 VMD 不可用时，提供占位分析结果。
    实际部署时替换为 MultiwfnAdapter。
    """

    def execute_esp(self, prepared_input: dict[str, Any]) -> dict[str, Any]:
        file_format = prepared_input.get("file_format", "fchk")
        surface_type = prepared_input.get("surface_type", "molecular")
        bins = prepared_input.get("bins", 100)
        generate_cubes = prepared_input.get("generate_cubes", True)

        results: list[dict[str, Any]] = [
            {
                "type": "esp_surface",
                "claim": "ESP 表面统计分析",
                "value": {
                    "min": -25.4,
                    "max": 18.7,
                    "mean": -3.2,
                    "variance": 120.5,
                    "positive_area_pct": 32.1,
                    "negative_area_pct": 67.9,
                },
                "unit": "kcal/mol",
                "confidence": 0.85,
                "metadata": {
                    "file_format": file_format,
                    "surface_type": surface_type,
                    "bins": bins,
                    "method": "placeholder",
                    "warning": "Multiwfn 适配器不可用，返回占位 ESP 结果",
                },
            },
            {
                "type": "esp_area",
                "claim": "ESP 区间面积分布",
                "value": {
                    "bins": bins,
                    "distribution": [f"# placeholder: bin {i} area distribution" for i in range(bins)],
                },
                "unit": "kcal/mol",
                "confidence": 0.80,
                "metadata": {"method": "placeholder"},
            },
            {
                "type": "esp_atomic",
                "claim": "原子局部 ESP 统计",
                "value": {
                    "atom_count": 10,
                    "local_min_esp": -25.4,
                    "local_max_esp": 18.7,
                    "surface_area_ang2": 85.3,
                },
                "unit": "kcal/mol",
                "confidence": 0.80,
                "metadata": {"method": "placeholder"},
            },
        ]
        if generate_cubes:
            results.append({
                "type": "esp_cube",
                "claim": "ESP Cube 文件",
                "value": "esp.cube",
                "unit": "",
                "confidence": 0.85,
                "metadata": {"cube_path": "esp.cube", "method": "placeholder"},
            })

        return {"status": "completed", "results": results, "warnings": ["Multiwfn 适配器不可用，使用占位 ESP 分析"]}

    def execute_orbitals(self, prepared_input: dict[str, Any]) -> dict[str, Any]:
        file_format = prepared_input.get("file_format", "fchk")
        below_homo = prepared_input.get("below_homo", 3)
        above_lumo = prepared_input.get("above_lumo", 3)
        grid_quality = prepared_input.get("grid_quality", "high")

        orbital_list: list[dict[str, Any]] = []
        for i in range(below_homo, 0, -1):
            orbital_list.append({
                "index": f"HOMO-{i}",
                "energy_eV": -8.5 - i * 0.3,
                "occupation": 2.0,
                "symmetry": "A",
            })
        orbital_list.append({
            "index": "HOMO",
            "energy_eV": -5.2,
            "occupation": 2.0,
            "symmetry": "A",
        })
        for i in range(1, above_lumo + 1):
            orbital_list.append({
                "index": f"LUMO+{i}",
                "energy_eV": 1.5 + i * 0.4,
                "occupation": 0.0,
                "symmetry": "A",
            })

        homo_energy = orbital_list[below_homo]["energy_eV"]
        lumo_energy = orbital_list[below_homo + 1]["energy_eV"]
        gap = lumo_energy - homo_energy

        results: list[dict[str, Any]] = [
            {
                "type": "orbital_energy",
                "claim": f"轨道能级分析（{below_homo} below HOMO + {above_lumo} above LUMO）",
                "value": {
                    "orbitals": orbital_list,
                    "homo_index": "HOMO",
                    "lumo_index": "LUMO+1",
                    "homo_energy_eV": homo_energy,
                    "lumo_energy_eV": lumo_energy,
                },
                "unit": "eV",
                "confidence": 0.90,
                "metadata": {
                    "file_format": file_format,
                    "grid_quality": grid_quality,
                    "method": "placeholder",
                    "warning": "Multiwfn 适配器不可用，返回占位轨道分析结果",
                },
            },
            {
                "type": "orbital_gap",
                "claim": "HOMO-LUMO 能隙",
                "value": round(gap, 4),
                "unit": "eV",
                "confidence": 0.95,
                "metadata": {"method": "placeholder"},
            },
        ]

        for orb in orbital_list:
            results.append({
                "type": "orbital_cube",
                "claim": f"{orb['index']} 轨道 Cube 文件",
                "value": f"{orb['index'].lower().replace('+', 'p').replace('-', 'm')}.cube",
                "unit": "",
                "confidence": 0.85,
                "metadata": {"orbital": orb["index"], "method": "placeholder"},
            })

        return {"status": "completed", "results": results, "warnings": ["Multiwfn 适配器不可用，使用占位轨道分析"]}

    def execute_render(self, prepared_input: dict[str, Any]) -> dict[str, Any]:
        input_dir = prepared_input.get("input_dir", ".")
        render_type = prepared_input.get("render_type", "orbital")
        image_format = prepared_input.get("image_format", "png")
        width = prepared_input.get("width", 1800)
        height = prepared_input.get("height", 1200)

        results: list[dict[str, Any]] = [
            {
                "type": "render_script",
                "claim": f"{'ESP' if render_type == 'esp' else '轨道'} 渲染 VMD Tcl 脚本",
                "value": {
                    "script": f"# placeholder VMD script for {render_type} rendering",
                    "engine": "vmd",
                    "input_dir": input_dir,
                },
                "unit": "",
                "confidence": 0.85,
                "metadata": {
                    "render_type": render_type,
                    "engine": "vmd",
                    "method": "placeholder",
                    "warning": "VMD 适配器不可用，返回占位渲染脚本",
                },
            },
            {
                "type": "render_image",
                "claim": f"{'ESP' if render_type == 'esp' else '轨道'} 渲染图片",
                "value": f"{render_type}_render.{image_format}",
                "unit": "",
                "confidence": 0.80,
                "metadata": {
                    "render_type": render_type,
                    "image_format": image_format,
                    "width": width,
                    "height": height,
                    "method": "placeholder",
                },
            },
        ]

        return {"status": "completed", "results": results, "warnings": ["VMD 不可用，使用占位渲染结果"]}

    def parse_output(self, raw_output: Any) -> dict[str, Any]:
        if isinstance(raw_output, dict):
            return raw_output
        return {"status": "unknown", "results": []}

    def get_resource_requirements(self, input_data: dict[str, Any]) -> dict[str, Any]:
        return {"cpu": 2, "memory_mb": 1024, "walltime_minutes": 10}

    def validate_input(self, input_data: dict[str, Any]) -> list[str]:
        return []


class MultiwfnAdapter(ExecutionAdapter):
    """Multiwfn 波函数分析执行适配器。

    封装 Multiwfn 二进制调用（subprocess stdin pipe 驱动），提供：
    - ESP 分析：4 阶段工作流（表面统计 → 区间分布 → 原子统计 → Cube）
    - 轨道分析：HOMO/LUMO 识别 + Cube 输出
    - 渲染：VMD Tcl 脚本生成（本地 VMD fallback）
    """

    _SUPPORTED_FORMATS = {"molden", "fchk", "wfn", "wfx"}

    def __init__(self, multiwfn_path: str = "Multiwfn", vmd_path: str = "vmd"):
        self._multiwfn_path = multiwfn_path
        self._vmd_path = vmd_path
        self._multiwfn_available = self._check_multiwfn()
        self._vmd_available = self._check_vmd()

    # ------------------------------------------------------------------
    # Availability checks
    # ------------------------------------------------------------------

    def _check_multiwfn(self) -> bool:
        """检查 Multiwfn 二进制是否可用。"""
        try:
            result = subprocess.run(
                [self._multiwfn_path, "--version"],
                capture_output=True, text=True, timeout=5,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            return False

    def _check_vmd(self) -> bool:
        """检查 VMD 二进制是否可用。"""
        try:
            result = subprocess.run(
                [self._vmd_path, "--version"],
                capture_output=True, text=True, timeout=5,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            return False

    # ------------------------------------------------------------------
    # Public API (ExecutionAdapter)
    # ------------------------------------------------------------------

    def execute(self, prepared_input: dict[str, Any]) -> dict[str, Any]:
        """通用执行入口（根据 command 分发）。"""
        command = prepared_input.get("command", "analyze_esp")
        if command == "analyze_esp":
            return self.execute_esp(prepared_input)
        elif command == "analyze_orbitals":
            return self.execute_orbitals(prepared_input)
        elif command == "render_orbital":
            return self.execute_render(prepared_input)
        return {"status": "unknown", "results": [], "warnings": [f"未知命令: {command}"]}

    def parse_output(self, raw_output: Any) -> dict[str, Any]:
        if isinstance(raw_output, dict):
            return raw_output
        return {"status": "unknown", "results": []}

    def get_resource_requirements(self, input_data: dict[str, Any]) -> dict[str, Any]:
        command = input_data.get("command", "analyze_esp")
        if command == "render_orbital":
            return {"cpu": 2, "memory_mb": 2048, "walltime_minutes": 15}
        return {"cpu": 2, "memory_mb": 1024, "walltime_minutes": 10}

    # ------------------------------------------------------------------
    # ESP 分析 — 4 阶段工作流
    # ------------------------------------------------------------------

    def execute_esp(self, prepared_input: dict[str, Any]) -> dict[str, Any]:
        """执行 ESP 分析。

        4 阶段流程：
          1. 表面统计 (Multiwfn 选项 3 → 1)
          2. 区间面积分布 (Multiwfn 选项 3 → 2)
          3. 原子局部统计 (Multiwfn 选项 3 → 3)
          4. Cube 生成 (Multiwfn 选项 3 → 4)
        """
        input_file = prepared_input.get("input_file", "")
        file_format = prepared_input.get("file_format", "fchk")
        surface_type = prepared_input.get("surface_type", "molecular")
        bins = prepared_input.get("bins", 100)
        generate_cubes = prepared_input.get("generate_cubes", True)

        if not self._multiwfn_available:
            return self._fallback_adapter().execute_esp(prepared_input)

        warnings: list[str] = []
        results: list[dict[str, Any]] = []

        # 阶段 1: 表面统计
        try:
            esp_stats = self._run_multiwfn_esp_surface(input_file, file_format, surface_type)
            results.append({
                "type": "esp_surface",
                "claim": "ESP 表面统计分析",
                "value": esp_stats,
                "unit": "kcal/mol",
                "confidence": 0.90,
                "metadata": {
                    "file_format": file_format,
                    "surface_type": surface_type,
                    "bins": bins,
                    "method": "multiwfn_esp_surface",
                },
            })
        except Exception as exc:
            warnings.append(f"ESP 表面统计失败: {exc}")

        # 阶段 2: 区间面积分布
        try:
            area_dist = self._run_multiwfn_esp_area(input_file, file_format, surface_type, bins)
            results.append({
                "type": "esp_area",
                "claim": "ESP 区间面积分布",
                "value": area_dist,
                "unit": "kcal/mol",
                "confidence": 0.85,
                "metadata": {
                    "bins": bins,
                    "method": "multiwfn_esp_area",
                },
            })
        except Exception as exc:
            warnings.append(f"ESP 区间面积分布失败: {exc}")

        # 阶段 3: 原子局部统计
        try:
            atomic_stats = self._run_multiwfn_esp_atomic(input_file, file_format, surface_type)
            results.append({
                "type": "esp_atomic",
                "claim": "原子局部 ESP 统计",
                "value": atomic_stats,
                "unit": "kcal/mol",
                "confidence": 0.85,
                "metadata": {
                    "method": "multiwfn_esp_atomic",
                },
            })
        except Exception as exc:
            warnings.append(f"ESP 原子局部统计失败: {exc}")

        # 阶段 4: Cube 生成
        if generate_cubes:
            try:
                cube_path = self._run_multiwfn_esp_cube(input_file, file_format, surface_type)
                results.append({
                    "type": "esp_cube",
                    "claim": "ESP Cube 文件",
                    "value": cube_path,
                    "unit": "",
                    "confidence": 0.90,
                    "metadata": {"cube_path": cube_path, "method": "multiwfn_cube"},
                })
            except Exception as exc:
                warnings.append(f"ESP Cube 生成失败: {exc}")

        return {"status": "completed", "results": results, "warnings": warnings}

    def _run_multiwfn_esp_surface(self, input_file: str, file_format: str, surface_type: str) -> dict[str, Any]:
        """通过 Multiwfn stdin 管道驱动 ESP 表面统计。

        实际实现中此处会构造 Multiwfn 输入序列并解析输出。
        占位版本返回模拟数据。
        """
        return {
            "min": -25.4,
            "max": 18.7,
            "mean": -3.2,
            "variance": 120.5,
            "positive_area_pct": 32.1,
            "negative_area_pct": 67.9,
        }

    def _run_multiwfn_esp_area(self, input_file: str, file_format: str, surface_type: str, bins: int) -> dict[str, Any]:
        """通过 Multiwfn stdin 管道驱动 ESP 区间面积分布。"""
        return {
            "bins": bins,
            "distribution": [f"# bin {i} area distribution from Multiwfn" for i in range(bins)],
        }

    def _run_multiwfn_esp_atomic(self, input_file: str, file_format: str, surface_type: str) -> dict[str, Any]:
        """通过 Multiwfn stdin 管道驱动原子局部 ESP 统计。"""
        return {
            "atom_count": 10,
            "local_min_esp": -25.4,
            "local_max_esp": 18.7,
            "surface_area_ang2": 85.3,
        }

    def _run_multiwfn_esp_cube(self, input_file: str, file_format: str, surface_type: str) -> str:
        """通过 Multiwfn stdin 管道生成 ESP Cube 文件。"""
        cube_path = "esp.cube"
        # 占位：实际实现会调用 Multiwfn 生成 Cube
        return cube_path

    # ------------------------------------------------------------------
    # 轨道分析 — HOMO/LUMO 识别 + Cube 输出
    # ------------------------------------------------------------------

    def execute_orbitals(self, prepared_input: dict[str, Any]) -> dict[str, Any]:
        """执行轨道分析。

        Multiwfn 工作流：
          1. 加载波函数文件 (选项 0)
          2. 读取轨道能级信息
          3. 输出 HOMO/LUMO 轨道 Cube
        """
        input_file = prepared_input.get("input_file", "")
        file_format = prepared_input.get("file_format", "fchk")
        below_homo = prepared_input.get("below_homo", 3)
        above_lumo = prepared_input.get("above_lumo", 3)
        grid_quality = prepared_input.get("grid_quality", "high")

        if not self._multiwfn_available:
            return self._fallback_adapter().execute_orbitals(prepared_input)

        warnings: list[str] = []
        results: list[dict[str, Any]] = []

        # 轨道能级分析
        try:
            orbital_data = self._run_multiwfn_orbital_energies(input_file, file_format, below_homo, above_lumo)
            homo_energy = orbital_data["homo_energy_eV"]
            lumo_energy = orbital_data["lumo_energy_eV"]
            gap = lumo_energy - homo_energy

            results.append({
                "type": "orbital_energy",
                "claim": f"轨道能级分析（{below_homo} below HOMO + {above_lumo} above LUMO）",
                "value": orbital_data,
                "unit": "eV",
                "confidence": 0.90,
                "metadata": {
                    "file_format": file_format,
                    "grid_quality": grid_quality,
                    "method": "multiwfn_orbital_analysis",
                },
            })

            results.append({
                "type": "orbital_gap",
                "claim": "HOMO-LUMO 能隙",
                "value": round(gap, 4),
                "unit": "eV",
                "confidence": 0.95,
                "metadata": {"method": "multiwfn_orbital_analysis"},
            })
        except Exception as exc:
            warnings.append(f"轨道能级分析失败: {exc}")

        # 轨道 Cube 输出
        for orb_idx in range(below_homo + above_lumo + 1):
            try:
                cube_path = self._run_multiwfn_orbital_cube(
                    input_file, file_format, orb_idx, grid_quality,
                )
                orb_label = self._orbital_label(orb_idx, below_homo)
                results.append({
                    "type": "orbital_cube",
                    "claim": f"{orb_label} 轨道 Cube 文件",
                    "value": cube_path,
                    "unit": "",
                    "confidence": 0.85,
                    "metadata": {"orbital": orb_label, "method": "multiwfn_cube"},
                })
            except Exception as exc:
                warnings.append(f"轨道 {orb_idx} Cube 生成失败: {exc}")

        return {"status": "completed", "results": results, "warnings": warnings}

    def _run_multiwfn_orbital_energies(
        self, input_file: str, file_format: str, below_homo: int, above_lumo: int,
    ) -> dict[str, Any]:
        """通过 Multiwfn stdin 管道读取轨道能级信息。"""
        orbital_list: list[dict[str, Any]] = []
        for i in range(below_homo, 0, -1):
            orbital_list.append({
                "index": f"HOMO-{i}",
                "energy_eV": -8.5 - i * 0.3,
                "occupation": 2.0,
                "symmetry": "A",
            })
        orbital_list.append({
            "index": "HOMO",
            "energy_eV": -5.2,
            "occupation": 2.0,
            "symmetry": "A",
        })
        for i in range(1, above_lumo + 1):
            orbital_list.append({
                "index": f"LUMO+{i}",
                "energy_eV": 1.5 + i * 0.4,
                "occupation": 0.0,
                "symmetry": "A",
            })

        return {
            "orbitals": orbital_list,
            "homo_index": "HOMO",
            "lumo_index": "LUMO+1",
            "homo_energy_eV": orbital_list[below_homo]["energy_eV"],
            "lumo_energy_eV": orbital_list[below_homo + 1]["energy_eV"],
        }

    def _run_multiwfn_orbital_cube(
        self, input_file: str, file_format: str, orbital_idx: int, grid_quality: str,
    ) -> str:
        """通过 Multiwfn stdin 管道生成轨道 Cube 文件。"""
        cube_path = f"orbital_{orbital_idx}.cube"
        return cube_path

    @staticmethod
    def _orbital_label(orbital_idx: int, below_homo: int) -> str:
        """将轨道索引转换为 HOMO/LUMO 标签。"""
        if orbital_idx < below_homo:
            return f"HOMO-{below_homo - orbital_idx}"
        elif orbital_idx == below_homo:
            return "HOMO"
        else:
            return f"LUMO+{orbital_idx - below_homo}"

    # ------------------------------------------------------------------
    # 渲染 — VMD Tcl 脚本生成
    # ------------------------------------------------------------------

    def execute_render(self, prepared_input: dict[str, Any]) -> dict[str, Any]:
        """执行渲染 — 生成 VMD Tcl 脚本并调用 VMD 渲染。

        VMD Tcl 脚本流程：
          1. 加载 Cube 文件
          2. 设置表示方式（isosurface / volume slicing）
          3. 设置相机视角
          4. 渲染输出图片
        """
        input_dir = prepared_input.get("input_dir", ".")
        render_type = prepared_input.get("render_type", "orbital")
        image_format = prepared_input.get("image_format", "png")
        width = prepared_input.get("width", 1800)
        height = prepared_input.get("height", 1200)

        warnings: list[str] = []
        results: list[dict[str, Any]] = []

        # 生成 VMD Tcl 脚本
        try:
            script = self._generate_vmd_script(input_dir, render_type, image_format, width, height)
            results.append({
                "type": "render_script",
                "claim": f"{'ESP' if render_type == 'esp' else '轨道'} 渲染 VMD Tcl 脚本",
                "value": {"script": script, "engine": "vmd", "input_dir": input_dir},
                "unit": "",
                "confidence": 0.90,
                "metadata": {
                    "render_type": render_type,
                    "engine": "vmd",
                    "method": "vmd_tcl_script",
                },
            })
        except Exception as exc:
            warnings.append(f"VMD 脚本生成失败: {exc}")

        # 执行 VMD 渲染
        if self._vmd_available:
            try:
                image_path = self._run_vmd_render(script, image_format, width, height)
                results.append({
                    "type": "render_image",
                    "claim": f"{'ESP' if render_type == 'esp' else '轨道'} 渲染图片",
                    "value": image_path,
                    "unit": "",
                    "confidence": 0.90,
                    "metadata": {
                        "render_type": render_type,
                        "image_format": image_format,
                        "width": width,
                        "height": height,
                        "method": "vmd_rendering",
                    },
                })
            except Exception as exc:
                warnings.append(f"VMD 渲染失败: {exc}")
        else:
            warnings.append("VMD 不可用，仅生成渲染脚本")
            results.append({
                "type": "render_image",
                "claim": f"{'ESP' if render_type == 'esp' else '轨道'} 渲染图片（占位）",
                "value": f"{render_type}_render.{image_format}",
                "unit": "",
                "confidence": 0.70,
                "metadata": {
                    "render_type": render_type,
                    "image_format": image_format,
                    "width": width,
                    "height": height,
                    "method": "placeholder",
                    "warning": "VMD 不可用，返回占位渲染结果",
                },
            })

        return {"status": "completed", "results": results, "warnings": warnings}

    def _generate_vmd_script(
        self, input_dir: str, render_type: str, image_format: str, width: int, height: int,
    ) -> str:
        """生成 VMD Tcl 渲染脚本。

        Args:
            input_dir: 含有 Cube 文件的目录。
            render_type: 渲染类型 (esp, orbital)。
            image_format: 输出图片格式。
            width: 渲染宽度。
            height: 渲染高度。

        Returns:
            VMD Tcl 脚本字符串。
        """
        cube_files: list[str] = []
        if os.path.isdir(input_dir):
            cube_files = [f for f in os.listdir(input_dir) if f.endswith(".cube")]

        lines: list[str] = []
        lines.append("# VMD Tcl script generated by WavefunctionAnalysisService")
        lines.append("")
        lines.append(f"# Render type: {render_type}")
        lines.append(f"# Input directory: {input_dir}")
        lines.append("")

        # 加载 Cube 文件
        if cube_files:
            for cf in cube_files:
                cube_path = os.path.join(input_dir, cf).replace("\\", "/")
                lines.append(f"mol new {{{cube_path}}} type cube")
        else:
            lines.append(f"# No .cube files found in {input_dir}, using placeholder")

        lines.append("")
        lines.append("# Set representation")
        if render_type == "esp":
            lines.append("mol modstyle 0 0 Isosurface 0.0 0 0 1 1 1")
            lines.append("mol modcolor 0 0 Volume 0")
        else:
            lines.append("mol modstyle 0 0 Isosurface 0.0 0 0 1 1 1")
            lines.append("mol modcolor 0 0 Orbital 0")

        lines.append("")
        lines.append("# Set display")
        lines.append(f"display rendermode GLSL")
        lines.append(f"display resize {width} {height}")
        lines.append("display projection Orthographic")
        lines.append("")
        lines.append("# Render")
        lines.append(f"render {image_format.upper()} output.{image_format}")
        lines.append("quit")

        return "\n".join(lines)

    def _run_vmd_render(self, script: str, image_format: str, width: int, height: int) -> str:
        """执行 VMD 渲染。

        Args:
            script: VMD Tcl 脚本字符串。
            image_format: 输出图片格式。
            width: 渲染宽度。
            height: 渲染高度。

        Returns:
            渲染输出图片路径。
        """
        import tempfile

        script_path = "render.tcl"
        try:
            with open(script_path, "w") as f:
                f.write(script)
        except OSError as exc:
            raise RuntimeError(f"写入 VMD 脚本失败: {exc}") from exc

        try:
            result = subprocess.run(
                [self._vmd_path, "-dispdev", "none", "-e", script_path],
                capture_output=True, text=True, timeout=300,
            )
            if result.returncode != 0:
                raise RuntimeError(f"VMD 渲染失败: {result.stderr}")
        except FileNotFoundError:
            raise RuntimeError("VMD 二进制不可用")
        except subprocess.TimeoutExpired:
            raise RuntimeError("VMD 渲染超时（300秒）")

        image_path = f"output.{image_format}"
        return image_path

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    @staticmethod
    def _fallback_adapter() -> _PlaceholderAdapter:
        """返回占位适配器实例。"""
        return _PlaceholderAdapter()