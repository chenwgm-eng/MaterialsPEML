"""LAMMPS 执行适配器 — 数据文件准备、输入脚本生成、验证、执行、轨迹分析。

基于 lammps_architecture.md 的三条路径（A: 晶体/无机, B: 有机/聚合物, C: 生物分子）
和五步工作流（数据准备 → 输入生成 → 三级验证 → 执行 → 轨迹分析）。

执行后端优先级：
1. 本地 ``lmp`` 二进制（若可用）
2. Docker 容器 ``lammps/lammps:latest``（推荐生产部署方式）
3. 占位仿真（仅当上述两者都不可用时）
"""

from __future__ import annotations

import os
import shutil
from typing import Any

from .execution_adapter import ExecutionAdapter, create_engine_work_dir


# Docker 镜像常量
_LAMMPS_DOCKER_IMAGE = os.environ.get("BATTERYEMCL_LAMMPS_IMAGE", "lammps/lammps:latest")


class LAMMPSAdapter(ExecutionAdapter):
    """LAMMPS 分子动力学仿真执行适配器。

    封装 LAMMPS 二进制调用和 Python 生态工具（pymatgen, mbuild, foyer,
    OVITO, MDAnalysis），提供完整的 MD 模拟工作流。
    """

    _SUPPORTED_SYSTEM_TYPES = {"A", "B", "C"}

    def __init__(self) -> None:
        self._pymatgen_available = self._try_import("pymatgen")
        self._mbuild_available = self._try_import("mbuild")
        self._foyer_available = self._try_import("foyer")
        self._ovito_available = self._try_import("ovito")
        self._mdanalysis_available = self._try_import("MDAnalysis")
        # 缓存本地 lmp / docker 可用性探测结果
        self._lmp_path: str | None = self._find_local_lmp()
        self._docker_available: bool | None = None  # 延迟探测

    # ------------------------------------------------------------------
    # Import checks
    # ------------------------------------------------------------------

    @staticmethod
    def _try_import(module_name: str) -> bool:
        try:
            __import__(module_name)
            return True
        except ImportError:
            return False

    @staticmethod
    def _find_local_lmp() -> str | None:
        """查找本地 lmp 二进制路径；不可用返回 None。"""
        return shutil.which("lmp") or shutil.which("lmp_serial") or shutil.which("lammps")

    def _check_docker_available(self) -> bool:
        """检查 docker CLI 是否可用且能访问 lammps 镜像（结果缓存）。"""
        if self._docker_available is not None:
            return self._docker_available
        import subprocess

        try:
            # 检查 docker CLI 可用性
            result = subprocess.run(
                ["docker", "version", "--format", "{{.Server.Version}}"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                self._docker_available = False
                return False
            # 检查 lammps 镜像是否存在（本地或可拉取）
            inspect = subprocess.run(
                ["docker", "image", "inspect", _LAMMPS_DOCKER_IMAGE],
                capture_output=True, text=True, timeout=10,
            )
            self._docker_available = inspect.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            self._docker_available = False
        return self._docker_available

    # ------------------------------------------------------------------
    # Public API (ExecutionAdapter)
    # ------------------------------------------------------------------

    def execute(self, prepared_input: dict[str, Any]) -> dict[str, Any]:
        """执行完整的 MD 模拟工作流。

        Input format::

            {
                "system_type": "A" | "B" | "C",
                "structure_data": "...",          # SMILES / CIF / data 路径
                "forcefield": "EAM" | "OPLS-AA" | ...,
                "protocol": "nvt" | "npt" | "nve" | "minimize" | "npt_nvt",
                "temperature_k": 300.0,
                "pressure_atm": 1.0,
                "timestep_fs": 1.0,
                "run_steps": 100000,
                "requested_metrics": ["rdf", "msd", "diffusion_coefficient"],
            }

        执行后端优先使用本地 ``lmp`` 二进制；不可用时自动切换到 Docker 容器
        ``lammps/lammps:latest``；两者都不可用才回退到占位仿真。
        """
        # 在隔离的临时工作目录中执行，便于 Docker 卷挂载与清理
        original_cwd = os.getcwd()
        work_dir = create_engine_work_dir("lammps_run")
        try:
            os.chdir(work_dir)

            # 1. 数据文件准备
            data_result = self.prepare_data_file(prepared_input)
            if "error" in data_result:
                return data_result

            # 2. 输入脚本生成
            script_result = self.generate_input_script(prepared_input, data_result)
            if "error" in script_result:
                return script_result

            # 3. 三级验证
            validation_result = self.validate_simulation(
                script_result.get("script_path", "input.in"),
                data_result.get("data_path", "data.lammps"),
            )
            if "error" in validation_result:
                return validation_result

            # 4. 执行仿真（本地 lmp → Docker → 占位）
            execution_result = self.run_simulation(
                script_result.get("script_path", "input.in"),
                prepared_input,
                work_dir=work_dir,
            )
            if "error" in execution_result:
                return execution_result

            # 5. 轨迹分析
            analysis_result = self.analyze_trajectory(
                execution_result.get("trajectory_path", "trajectory.dump"),
                prepared_input.get("requested_metrics", []),
                thermo_data=execution_result.get("thermo_data", {}),
                engine=execution_result.get("engine", "unknown"),
            )

            return {
                "status": "completed",
                "data_file": data_result.get("data_path"),
                "script_file": script_result.get("script_path"),
                "log_file": execution_result.get("log_path"),
                "trajectory_file": execution_result.get("trajectory_path"),
                "analysis": analysis_result.get("results", []),
                "warnings": (
                    validation_result.get("warnings", [])
                    + execution_result.get("warnings", [])
                    + analysis_result.get("warnings", [])
                ),
                "engine": execution_result.get("engine", "unknown"),
            }
        finally:
            # 恢复原工作目录；work_dir 保留供后续轨迹分析读取，由系统清理
            os.chdir(original_cwd)

    def parse_output(self, raw_output: Any) -> dict[str, Any]:
        """解析原始输出为结构化 dict。"""
        if isinstance(raw_output, dict):
            return raw_output
        return {"status": "unknown", "analysis": []}

    def get_resource_requirements(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """返回资源需求。"""
        system_type = input_data.get("system_type", "A")
        run_steps = input_data.get("run_steps", 100000)

        # 不同系统类型的资源需求估算
        base_resources: dict[str, Any] = {
            "A": {"cpu": 4, "memory_mb": 2048, "walltime_minutes": 30},
            "B": {"cpu": 4, "memory_mb": 4096, "walltime_minutes": 60},
            "C": {"cpu": 8, "memory_mb": 8192, "walltime_minutes": 120},
        }
        resources = base_resources.get(system_type, base_resources["A"])

        # 按步数缩放
        scale = max(1.0, run_steps / 100000)
        resources["walltime_minutes"] = int(resources["walltime_minutes"] * scale)
        return resources

    # ------------------------------------------------------------------
    # Step 1: 数据文件准备
    # ------------------------------------------------------------------

    def prepare_data_file(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """根据系统类型准备 LAMMPS data 文件。

        - Path A: pymatgen LammpsData.from_structure()
        - Path B: mbuild + foyer → write_lammps_data()
        - Path C: 拓扑文件转换（占位）
        """
        system_type = input_data.get("system_type", "A")
        structure_data = input_data.get("structure_data", "")

        if not structure_data:
            return {"error": "structure_data 不能为空"}

        if system_type == "A":
            return self._prepare_path_a(structure_data, input_data)
        elif system_type == "B":
            return self._prepare_path_b(structure_data, input_data)
        elif system_type == "C":
            return self._prepare_path_c(structure_data, input_data)
        else:
            return {"error": f"不支持的系统类型: {system_type}"}

    def _prepare_path_a(self, structure_data: str, input_data: dict[str, Any]) -> dict[str, Any]:
        """Path A: 使用 pymatgen 从 CIF/结构文件生成 data 文件。"""
        atom_style = "charge" if input_data.get("forcefield") in ("Buckingham",) else "atomic"

        if self._pymatgen_available:
            try:
                from pymatgen.core import Structure
                from pymatgen.io.lammps.data import LammpsData

                struct = Structure.from_file(structure_data)
                lammps_data = LammpsData.from_structure(struct, atom_style=atom_style)
                data_path = "data.lammps"
                lammps_data.write_file(data_path)
                return {"data_path": data_path, "atom_style": atom_style}
            except Exception as exc:
                return {"error": f"pymatgen data 准备失败: {exc}"}

        # 回退：占位 data 文件
        return {"data_path": "data.lammps", "atom_style": atom_style, "warning": "pymatgen 不可用，使用占位 data 文件"}

    def _prepare_path_b(self, structure_data: str, input_data: dict[str, Any]) -> dict[str, Any]:
        """Path B: 使用 mbuild + foyer 从 SMILES 生成 data 文件。"""
        if self._mbuild_available and self._foyer_available:
            try:
                import mbuild as mb
                from foyer import Forcefield

                # 从 SMILES 构建分子
                compound = mb.load(structure_data, smiles=True)
                # 应用力场
                forcefield_name = input_data.get("forcefield", "OPLS-AA")
                ff = Forcefield(forcefield_name)
                compound = ff.apply(compound)
                # 写入 data 文件
                data_path = "data.lammps"
                compound.save(data_path, forcefield_name=forcefield_name)
                return {"data_path": data_path, "atom_style": "full"}
            except Exception as exc:
                return {"error": f"mbuild/foyer data 准备失败: {exc}"}

        return {"data_path": "data.lammps", "atom_style": "full", "warning": "mbuild 或 foyer 不可用，使用占位 data 文件"}

    def _prepare_path_c(self, structure_data: str, input_data: dict[str, Any]) -> dict[str, Any]:
        """Path C: 生物分子拓扑文件转换（占位实现）。"""
        return {
            "data_path": structure_data,
            "atom_style": "full",
            "warning": "Path C 生物分子拓扑转换目前为占位实现",
        }

    # ------------------------------------------------------------------
    # Step 2: 输入脚本生成
    # ------------------------------------------------------------------

    def generate_input_script(self, input_data: dict[str, Any], data_result: dict[str, Any]) -> dict[str, Any]:
        """生成 LAMMPS 输入脚本。"""
        system_type = input_data.get("system_type", "A")
        system_info = self._get_system_info(system_type)

        protocol = input_data.get("protocol", "nvt")
        temperature_k = input_data.get("temperature_k", 300.0)
        pressure_atm = input_data.get("pressure_atm", 1.0)
        timestep_fs = input_data.get("timestep_fs", 1.0)
        run_steps = input_data.get("run_steps", 100000)

        lines: list[str] = []
        lines.append("# LAMMPS input script generated by MolecularSimulationService")
        lines.append("")
        lines.append(f"units          {system_info['units']}")
        lines.append(f"atom_style     {data_result.get('atom_style', 'atomic')}")
        lines.append("")
        lines.append(f"read_data      {data_result.get('data_path', 'data.lammps')}")
        lines.append("")
        lines.append(f"timestep       {timestep_fs}")

        # 力场设置（根据系统类型）
        ff_lines = self._generate_forcefield_section(
            input_data.get("forcefield", ""),
            system_type,
        )
        lines.extend(ff_lines)
        lines.append("")

        # 输出设置
        lines.append("thermo         1000")
        lines.append("thermo_style   custom step temp pe ke etotal press density")
        lines.append("")
        lines.append("dump           traj all custom 10000 trajectory.dump id type x y z vx vy vz")
        lines.append("dump_modify    traj sort id")
        lines.append("")

        # 协议相关设置
        protocol_lines = self._generate_protocol_section(
            protocol, temperature_k, pressure_atm, run_steps,
        )
        lines.extend(protocol_lines)

        script_path = "input.in"
        try:
            with open(script_path, "w") as f:
                f.write("\n".join(lines))
        except OSError as exc:
            return {"error": f"写入输入脚本失败: {exc}"}

        return {"script_path": script_path, "lines": lines}

    @staticmethod
    def _get_system_info(system_type: str) -> dict[str, str]:
        info: dict[str, dict[str, str]] = {
            "A": {"units": "metal", "atom_style": "atomic"},
            "B": {"units": "real", "atom_style": "full"},
            "C": {"units": "real", "atom_style": "full"},
        }
        return info.get(system_type, info["A"])

    def _generate_forcefield_section(self, forcefield: str, system_type: str) -> list[str]:
        """生成力场相关的 LAMMPS 命令段。"""
        lines: list[str] = []
        ff = forcefield.upper() if forcefield else ""

        if system_type == "A":
            if ff in ("EAM", "") or not ff:
                lines.append("pair_style     eam/alloy")
                lines.append("pair_coeff     * * potentials/NiCu.eam.alloy Ni Cu")
            elif ff == "BUCKINGHAM":
                lines.append("pair_style     buck/coul/long 12.0")
                lines.append("pair_coeff     * * potentials/buckingham.param Mg O")
                lines.append("kspace_style   pppm 1.0e-5")
            elif ff == "TERSOFF":
                lines.append("pair_style     tersoff")
                lines.append("pair_coeff     * * potentials/Si.tersoff Si")
            elif ff == "SW":
                lines.append("pair_style     sw")
                lines.append("pair_coeff     * * potentials/Si.sw Si")
            elif ff == "REAXFF":
                lines.append("pair_style     reaxff NULL")
                lines.append("pair_coeff     * * potentials/ffield.reaxff C H O")
            else:
                lines.append(f"# pair_style for {ff} — 待补充")

        elif system_type == "B":
            lines.append("pair_style     lj/cut/coul/long 12.0")
            lines.append("pair_modify    mix geometric")
            lines.append("kspace_style   pppm 1.0e-5")
            lines.append("bond_style     harmonic")
            lines.append("angle_style    harmonic")
            lines.append("dihedral_style opls")
            lines.append("improper_style cvff")
            lines.append("special_bonds  lj/coul 0.0 0.0 0.5")

        else:  # C
            lines.append("pair_style     lj/cut/coul/long 12.0")
            lines.append("kspace_style   pppm 1.0e-5")
            lines.append("# 生物分子力场需要从拓扑文件导入")

        return lines

    def _generate_protocol_section(
        self,
        protocol: str,
        temperature_k: float,
        pressure_atm: float,
        run_steps: int,
    ) -> list[str]:
        """生成系综协议相关的 LAMMPS 命令段。"""
        lines: list[str] = []
        proto = protocol.lower()

        if proto == "minimize":
            lines.append("# 能量最小化")
            lines.append("min_style      cg")
            lines.append("minimize       1.0e-4 1.0e-6 1000 10000")
            lines.append("write_data     minimized.data")

        elif proto == "nvt":
            lines.append(f"# NVT 系综 — T = {temperature_k} K")
            lines.append(f"fix            1 all nvt temp {temperature_k} {temperature_k} 100.0")
            lines.append(f"run            {run_steps}")
            lines.append(f"write_data     nvt.data")

        elif proto == "npt":
            lines.append(f"# NPT 系综 — T = {temperature_k} K, P = {pressure_atm} atm")
            lines.append(f"fix            1 all npt temp {temperature_k} {temperature_k} 100.0 iso {pressure_atm} {pressure_atm} 1000.0")
            lines.append(f"run            {run_steps}")
            lines.append(f"write_data     npt.data")

        elif proto == "nve":
            lines.append("# NVE 系综 — 微正则")
            lines.append("fix            1 all nve")
            lines.append(f"run            {run_steps}")

        elif proto == "npt_nvt":
            lines.append(f"# 两步流程: NPT 平衡 → NVT 产出")
            npt_steps = run_steps // 2
            nvt_steps = run_steps - npt_steps
            lines.append(f"# 阶段一: NPT 平衡 (T = {temperature_k} K, P = {pressure_atm} atm)")
            lines.append(f"fix            1 all npt temp {temperature_k} {temperature_k} 100.0 iso {pressure_atm} {pressure_atm} 1000.0")
            lines.append(f"run            {npt_steps}")
            lines.append("unfix          1")
            lines.append(f"write_data     npt_equilibrated.data")
            lines.append("")
            lines.append(f"# 阶段二: NVT 产出 (T = {temperature_k} K)")
            lines.append(f"fix            1 all nvt temp {temperature_k} {temperature_k} 100.0")
            lines.append(f"run            {nvt_steps}")
            lines.append(f"write_data     nvt_production.data")

        else:
            lines.append(f"# 未知协议: {protocol}")

        return lines

    # ------------------------------------------------------------------
    # Step 3: 三级验证
    # ------------------------------------------------------------------

    def validate_simulation(self, script_path: str, data_path: str) -> dict[str, Any]:
        """三级验证：语法 → 物理 → 协议。

        Returns:
            dict: 包含 valid、errors、warnings。
        """
        errors: list[str] = []
        warnings: list[str] = []

        # 1. 语法验证：检查脚本文件是否存在且非空
        syntax_result = self._validate_syntax(script_path)
        if "error" in syntax_result:
            return syntax_result
        errors.extend(syntax_result.get("errors", []))
        warnings.extend(syntax_result.get("warnings", []))

        # 2. 物理验证：检查参数合理性
        physics_result = self._validate_physics(script_path)
        errors.extend(physics_result.get("errors", []))
        warnings.extend(physics_result.get("warnings", []))

        # 3. 协议验证
        protocol_result = self._validate_protocol_order(script_path)
        warnings.extend(protocol_result.get("warnings", []))

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
        }

    @staticmethod
    def _validate_syntax(script_path: str) -> dict[str, Any]:
        """语法验证 — 检查文件是否存在且包含必要命令。"""
        errors: list[str] = []
        warnings: list[str] = []

        try:
            with open(script_path) as f:
                content = f.read()
        except FileNotFoundError:
            return {"error": f"脚本文件不存在: {script_path}"}
        except OSError as exc:
            return {"error": f"读取脚本文件失败: {exc}"}

        if not content.strip():
            errors.append("脚本文件为空")

        # 检查必要命令（简化版）
        required_commands = ["units", "atom_style", "read_data", "pair_style"]
        for cmd in required_commands:
            if cmd not in content:
                warnings.append(f"脚本中缺少 {cmd} 命令")

        # 检查是否有 run 命令
        if "run" not in content:
            errors.append("脚本中没有 run 命令")

        return {"errors": errors, "warnings": warnings}

    @staticmethod
    def _validate_physics(script_path: str) -> dict[str, Any]:
        """物理验证 — 检查参数合理性。"""
        errors: list[str] = []
        warnings: list[str] = []

        try:
            with open(script_path) as f:
                content = f.read()
        except (FileNotFoundError, OSError):
            return {"errors": [], "warnings": ["无法读取脚本进行物理验证"]}

        # 检查时间步长
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("timestep"):
                parts = stripped.split()
                if len(parts) >= 2:
                    try:
                        dt = float(parts[1])
                        if dt <= 0:
                            errors.append("时间步长必须为正数")
                        elif dt > 5.0:
                            warnings.append(f"时间步长 {dt} fs 偏大，可能影响数值稳定性")
                    except ValueError:
                        warnings.append("无法解析时间步长")

        # 检查温度范围
        for line in content.splitlines():
            if "temp" in line.lower() and any(x in line for x in ("fix", "nvt", "npt")):
                parts = line.split()
                for p in parts:
                    try:
                        t = float(p)
                        if t > 10000:
                            warnings.append(f"温度 {t} K 异常偏高")
                        elif t <= 0:
                            errors.append("温度必须为正数")
                    except ValueError:
                        pass

        return {"errors": errors, "warnings": warnings}

    @staticmethod
    def _validate_protocol_order(script_path: str) -> dict[str, Any]:
        """协议验证 — 检查阶段顺序是否正确。"""
        warnings: list[str] = []

        try:
            with open(script_path) as f:
                content = f.read()
        except (FileNotFoundError, OSError):
            return {"warnings": ["无法读取脚本进行协议验证"]}

        lines = content.splitlines()
        has_minimize = any("minimize" in line for line in lines)
        has_fix = any(line.strip().startswith("fix") for line in lines)
        has_run = any(line.strip().startswith("run") for line in lines)

        if has_run and not has_fix:
            warnings.append("run 前没有 active fix（应含 nve/nvt/npt 系综）")
        if has_run and not has_minimize:
            warnings.append("动力学前建议先进行能量最小化")

        return {"warnings": warnings}

    # ------------------------------------------------------------------
    # Step 4: 仿真执行
    # ------------------------------------------------------------------

    def run_simulation(
        self,
        script_path: str,
        input_data: dict[str, Any],
        work_dir: str | None = None,
    ) -> dict[str, Any]:
        """执行 LAMMPS 仿真。

        优先级：
        1. 本地 ``lmp`` 二进制（subprocess）
        2. Docker 容器 ``lammps/lammps:latest``（mount work_dir → /work）
        3. 占位仿真（两者都不可用时）

        Args:
            script_path: LAMMPS 输入脚本路径（相对 work_dir 或绝对路径）。
            input_data: 仿真输入参数（temperature_k, protocol 等）。
            work_dir: 工作目录（用于 Docker 卷挂载）；为 None 时使用当前目录。
        """
        import subprocess

        work_dir = work_dir or os.getcwd()
        # script_path 在容器内对应 /work/<basename>
        script_basename = os.path.basename(script_path) if os.path.isabs(script_path) else script_path

        # 1. 优先本地 lmp 二进制
        if self._lmp_path:
            try:
                env = {**os.environ, "OMP_NUM_THREADS": "4"}
                result = subprocess.run(
                    [self._lmp_path, "-sf", "omp", "-in", script_path],
                    capture_output=True,
                    text=True,
                    timeout=300,
                    env=env,
                    cwd=work_dir,
                )
                log_path = os.path.join(work_dir, "log.lammps")
                return {
                    "log_path": log_path,
                    "trajectory_path": os.path.join(work_dir, "trajectory.dump"),
                    "exit_code": result.returncode,
                    "stdout": result.stdout[-2000:],
                    "stderr": result.stderr[-2000:],
                    "engine": "local_lmp",
                }
            except subprocess.TimeoutExpired:
                return {"error": "LAMMPS 执行超时（300秒）"}
            except Exception as exc:
                # 本地 lmp 失败，继续尝试 Docker
                pass

        # 2. Docker 容器后端
        if self._check_docker_available():
            return self._run_docker_simulation(script_basename, input_data, work_dir)

        # 3. 占位仿真
        return self._run_placeholder_simulation(script_basename, input_data, work_dir)

    def _run_docker_simulation(
        self,
        script_basename: str,
        input_data: dict[str, Any],
        work_dir: str,
    ) -> dict[str, Any]:
        """通过常驻 Docker 容器执行 LAMMPS 仿真。

        将 work_dir 挂载为容器内 /work，复用 lammps/lammps:latest 常驻容器。
        """
        from .docker_executor import run_in_persistent_container

        # lammps/lammps:latest 镜像 ENTRYPOINT 为空，CMD=lmp_mpi；
        # 实际可执行文件为 /usr/bin/lmp_serial 或 /usr/bin/lmp_mpi，
        # 必须显式指定 entrypoint，否则 -in 参数被当作命令执行而失败
        # 使用相对路径 script_basename（workdir 已设为 /work/<rel>）
        exit_code, stdout, stderr = run_in_persistent_container(
            engine_key="lammps",
            image=_LAMMPS_DOCKER_IMAGE,
            cmd_args=["lmp_serial", "-in", script_basename],
            work_dir=work_dir,
            entrypoint="tail",  # 常驻容器启动时用 tail 保持存活
            timeout=600,
        )

        if exit_code == 1 and "镜像不可用" in stderr:
            return {"error": stderr}

        log_path = os.path.join(work_dir, "log.lammps")
        traj_path = os.path.join(work_dir, "trajectory.dump")

        warnings: list[str] = []
        if exit_code != 0:
            warnings.append(
                f"LAMMPS Docker 退出码非零 ({exit_code})；"
                f"stderr: {stderr[-500:]}"
            )

        # 解析 log.lammps 提取热力学数据（温度、能量、密度等）
        thermo_data = self._parse_lammps_log(log_path)

        return {
            "log_path": log_path,
            "trajectory_path": traj_path,
            "exit_code": exit_code,
            "stdout": stdout[-2000:],
            "stderr": stderr[-2000:],
            "engine": "docker_lammps_persistent",
            "thermo_data": thermo_data,
            "warnings": warnings,
        }

    @staticmethod
    def _parse_lammps_log(log_path: str) -> dict[str, Any]:
        """解析 LAMMPS log.lammps 文件提取热力学数据。

        返回 dict 包含 steps/temperature/energy/pressure/density 等列表，
        供 analyze_trajectory 使用。文件不存在或解析失败返回空 dict。
        """
        if not os.path.isfile(log_path):
            return {}

        try:
            with open(log_path) as f:
                content = f.read()
        except OSError:
            return {}

        # LAMMPS thermo 输出格式：列名行 + 数据行
        # 例如：Step Temp PotEng KinEng TotEng Press Density
        lines = content.splitlines()
        columns: list[str] = []
        data_rows: list[list[float]] = []
        in_thermo = False

        for line in lines:
            stripped = line.strip()
            if not stripped:
                in_thermo = False
                continue
            # thermo 头部行：纯字母单词
            tokens = stripped.split()
            if (
                not in_thermo
                and len(tokens) >= 2
                and all(t.isalpha() or t.replace("_", "").isalpha() for t in tokens)
                and any(k in tokens for k in ("Step", "Temp", "Press", "Density", "Eng"))
            ):
                columns = tokens
                in_thermo = True
                continue
            if in_thermo:
                try:
                    row = [float(t) for t in tokens]
                    data_rows.append(row)
                except ValueError:
                    in_thermo = False
                    columns = []

        if not columns or not data_rows:
            return {}

        result: dict[str, Any] = {}
        for i, col in enumerate(columns):
            if i >= len(data_rows[0]):
                continue
            result[col] = [row[i] for row in data_rows]
        return result

    def _run_placeholder_simulation(
        self,
        script_basename: str,
        input_data: dict[str, Any],
        work_dir: str,
    ) -> dict[str, Any]:
        """占位仿真 — 当 LAMMPS 本地二进制与 Docker 都不可用时使用。

        生成模拟的 log 和 trajectory 文件，供后续分析流程使用。
        """
        protocol = input_data.get("protocol", "nvt")
        temperature_k = input_data.get("temperature_k", 300.0)
        run_steps = input_data.get("run_steps", 100000)

        # 创建占位 log 文件
        log_path = os.path.join(work_dir, "log.lammps")
        with open(log_path, "w") as f:
            f.write(f"LAMMPS placeholder simulation: {protocol} at {temperature_k}K for {run_steps} steps\n")
            f.write(f"System type: {input_data.get('system_type', 'A')}\n")
            f.write("WARNING: This is a placeholder — LAMMPS binary & Docker both unavailable\n")

        # 创建占位 trajectory 文件
        traj_path = os.path.join(work_dir, "trajectory.dump")
        with open(traj_path, "w") as f:
            f.write("ITEM: TIMESTEP\n0\nITEM: NUMBER OF ATOMS\n0\nITEM: BOX BOUNDS\n0 10\n0 10\n0 10\nITEM: ATOMS\n")

        return {
            "log_path": log_path,
            "trajectory_path": traj_path,
            "exit_code": 0,
            "engine": "placeholder",
            "warnings": ["LAMMPS 本地二进制与 Docker 均不可用，使用占位仿真结果"],
        }

    # ------------------------------------------------------------------
    # Step 5: 轨迹分析
    # ------------------------------------------------------------------

    def analyze_trajectory(
        self,
        trajectory_path: str,
        requested_metrics: list[str],
        thermo_data: dict[str, Any] | None = None,
        engine: str = "unknown",
    ) -> dict[str, Any]:
        """使用 OVITO / MDAnalysis / 纯 Python 解析器进行轨迹分析。

        Args:
            trajectory_path: 轨迹文件路径（.dump 或 .lammpstrj）。
            requested_metrics: 请求分析的指标列表。
            thermo_data: 从 log.lammps 解析得到的热力学数据（温度/能量/密度等）。
            engine: 仿真引擎标识（local_lmp / docker_lammps / placeholder）。

        Returns:
            dict: 包含 results（每个指标的分析结果）和 warnings。
        """
        results: list[dict[str, Any]] = []
        warnings: list[str] = []
        thermo_data = thermo_data or {}

        if not requested_metrics:
            return {"results": [], "warnings": ["未指定分析指标"]}

        # 解析 LAMMPS dump 轨迹（纯 Python，避免 OVITO/MDAnalysis 依赖）
        trajectory_frames = self._parse_lammps_dump(trajectory_path)
        if not trajectory_frames and engine in ("local_lmp", "docker_lammps"):
            warnings.append(
                f"轨迹文件 {trajectory_path} 解析为空（可能 LAMMPS 输出失败）"
            )

        for metric in requested_metrics:
            result = self._analyze_single_metric(
                metric,
                trajectory_frames=trajectory_frames,
                thermo_data=thermo_data,
                engine=engine,
            )
            if "error" in result:
                warnings.append(result["error"])
            else:
                results.append(result)

        return {"results": results, "warnings": warnings}

    def _analyze_single_metric(
        self,
        metric: str,
        trajectory_frames: list[dict[str, Any]] | None = None,
        thermo_data: dict[str, Any] | None = None,
        engine: str = "unknown",
    ) -> dict[str, Any]:
        """分析单个指标。

        优先使用 thermo_data（来自 log.lammps）和纯 Python 轨迹解析，
        无需 OVITO/MDAnalysis 依赖。
        """
        metric_lower = metric.lower().strip()
        thermo_data = thermo_data or {}
        trajectory_frames = trajectory_frames or []

        # 1. 优先从 thermo_data 提取标量指标（能量/温度/压力/密度）
        if metric_lower == "energy":
            return self._extract_thermo_metric(
                thermo_data, ["TotEng", "TotalEng", "E_pair", "PotEng", "Pe"],
                "energy", "eV", engine,
            )
        if metric_lower == "temperature":
            return self._extract_thermo_metric(
                thermo_data, ["Temp"], "temperature", "K", engine,
            )
        if metric_lower == "pressure":
            return self._extract_thermo_metric(
                thermo_data, ["Press"], "pressure", "bar", engine,
            )
        if metric_lower == "density":
            return self._extract_thermo_metric(
                thermo_data, ["Density"], "density", "g/cm³", engine,
            )

        # 2. 轨迹相关指标：优先 OVITO/MDAnalysis，回退到纯 Python 解析
        if metric_lower in ("rdf", "cna", "angular_distribution"):
            if self._ovito_available:
                try:
                    # OVITO 需要文件路径，但当前接口改为传入 frames；
                    # 此处简化：OVITO 不可用时直接走纯 Python
                    pass
                except Exception:
                    pass

        if metric_lower in ("rdf", "msd", "rmsd", "rmsf", "diffusion_coefficient"):
            if self._mdanalysis_available:
                # MDAnalysis 同样需要文件路径，简化：走纯 Python
                pass

            # 纯 Python 轨迹分析
            if trajectory_frames:
                return self._analyze_with_pure_python(
                    metric_lower, trajectory_frames, engine
                )

        # 3. 回退：占位分析结果
        return self._placeholder_analysis(metric_lower, engine)

    def _extract_thermo_metric(
        self,
        thermo_data: dict[str, Any],
        keys: list[str],
        metric_name: str,
        unit: str,
        engine: str,
    ) -> dict[str, Any]:
        """从 LAMMPS thermo 数据中提取标量指标。"""
        for key in keys:
            if key in thermo_data and thermo_data[key]:
                values = thermo_data[key]
                avg = sum(values) / len(values)
                return {
                    "metric": metric_name,
                    "value": round(avg, 6),
                    "unit": unit,
                    "confidence": 0.95 if engine in ("local_lmp", "docker_lammps") else 0.7,
                    "metadata": {
                        "method": f"LAMMPS thermo ({engine})",
                        "n_samples": len(values),
                        "min": round(min(values), 6),
                        "max": round(max(values), 6),
                    },
                }
        # thermo 中无此指标
        return self._placeholder_analysis(metric_name, engine)

    @staticmethod
    def _parse_lammps_dump(dump_path: str) -> list[dict[str, Any]]:
        """纯 Python 解析 LAMMPS dump 轨迹文件。

        支持常见的 LAMMPS dump custom 格式：
            ITEM: TIMESTEP
            <step>
            ITEM: NUMBER OF ATOMS
            <n>
            ITEM: BOX BOUNDS ...
            <xlo xhi> <ylo yhi> <zlo zhi>
            ITEM: ATOMS id type x y z ...
            <atom lines>

        返回 [{timestep, n_atoms, box, atoms: [(id, type, x, y, z), ...]}, ...]
        """
        if not dump_path or not os.path.isfile(dump_path):
            return []

        frames: list[dict[str, Any]] = []
        try:
            with open(dump_path) as f:
                content = f.read()
        except OSError:
            return []

        lines = content.splitlines()
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if line.startswith("ITEM: TIMESTEP"):
                try:
                    timestep = int(lines[i + 1].strip())
                    i += 2
                except (ValueError, IndexError):
                    break

                # NUMBER OF ATOMS
                if i < len(lines) and lines[i].startswith("ITEM: NUMBER OF ATOMS"):
                    n_atoms = int(lines[i + 1].strip())
                    i += 2
                else:
                    break

                # BOX BOUNDS
                box: list[tuple[float, float]] = []
                if i < len(lines) and lines[i].startswith("ITEM: BOX BOUNDS"):
                    for k in range(3):
                        parts = lines[i + 1 + k].split()
                        if len(parts) >= 2:
                            box.append((float(parts[0]), float(parts[1])))
                    i += 4
                else:
                    i += 0

                # ATOMS
                atoms: list[tuple] = []
                if i < len(lines) and lines[i].startswith("ITEM: ATOMS"):
                    # 解析列名
                    header = lines[i].replace("ITEM: ATOMS", "").strip().split()
                    i += 1
                    for k in range(n_atoms):
                        if i + k >= len(lines):
                            break
                        parts = lines[i + k].split()
                        if not parts:
                            continue
                        # 默认列：id type x y z（支持子集）
                        atom: dict[str, float | int] = {}
                        for col_idx, col_name in enumerate(header):
                            if col_idx >= len(parts):
                                break
                            try:
                                atom[col_name] = float(parts[col_idx])
                            except ValueError:
                                atom[col_name] = parts[col_idx]
                        atoms.append((
                            atom.get("id", k),
                            atom.get("type", 1),
                            atom.get("x", 0.0),
                            atom.get("y", 0.0),
                            atom.get("z", 0.0),
                        ))
                    i += n_atoms
                else:
                    # 无 ATOMS 段，跳过
                    pass

                frames.append({
                    "timestep": timestep,
                    "n_atoms": n_atoms,
                    "box": box,
                    "atoms": atoms,
                })
            else:
                i += 1

        return frames

    def _analyze_with_pure_python(
        self,
        metric: str,
        frames: list[dict[str, Any]],
        engine: str,
    ) -> dict[str, Any]:
        """纯 Python 实现的轨迹分析（无 OVITO/MDAnalysis 依赖）。"""
        import math

        confidence = 0.90 if engine in ("local_lmp", "docker_lammps") else 0.75
        method = f"pure_python ({engine})"

        if not frames:
            return self._placeholder_analysis(metric, engine)

        # 提取所有帧的原子坐标（按 id 排序以对齐）
        # frames[i]["atoms"] = [(id, type, x, y, z), ...]
        # 排序
        sorted_frames = []
        for frame in frames:
            atoms_sorted = sorted(frame["atoms"], key=lambda a: a[0])
            sorted_frames.append([(a[2], a[3], a[4]) for a in atoms_sorted])

        n_frames = len(sorted_frames)
        n_atoms = len(sorted_frames[0]) if sorted_frames else 0

        if metric == "rmsd" and n_frames >= 2:
            ref = sorted_frames[0]
            rmsd_series: list[float] = []
            for frame in sorted_frames[1:]:
                if len(frame) != len(ref):
                    continue
                sq_sum = 0.0
                for i in range(len(ref)):
                    dx = ref[i][0] - frame[i][0]
                    dy = ref[i][1] - frame[i][1]
                    dz = ref[i][2] - frame[i][2]
                    sq_sum += dx * dx + dy * dy + dz * dz
                rmsd_series.append(round(math.sqrt(sq_sum / max(1, len(ref))), 6))
            return {
                "metric": "rmsd",
                "value": rmsd_series,
                "unit": "Å",
                "confidence": confidence,
                "metadata": {
                    "method": method,
                    "n_frames": len(rmsd_series),
                    "final_rmsd": rmsd_series[-1] if rmsd_series else None,
                },
            }

        if metric == "rmsf" and n_frames >= 2:
            # 每个原子的位置涨落
            rmsf: list[float] = []
            for atom_idx in range(min(n_atoms, len(sorted_frames[0]))):
                coords = [f[atom_idx] for f in sorted_frames if len(f) > atom_idx]
                if len(coords) < 2:
                    rmsf.append(0.0)
                    continue
                mean_x = sum(c[0] for c in coords) / len(coords)
                mean_y = sum(c[1] for c in coords) / len(coords)
                mean_z = sum(c[2] for c in coords) / len(coords)
                var_sum = sum(
                    (c[0] - mean_x) ** 2 + (c[1] - mean_y) ** 2 + (c[2] - mean_z) ** 2
                    for c in coords
                )
                rmsf.append(round(math.sqrt(var_sum / len(coords)), 6))
            return {
                "metric": "rmsf",
                "value": rmsf,
                "unit": "Å",
                "confidence": confidence,
                "metadata": {"method": method, "n_atoms": len(rmsf)},
            }

        if metric == "msd" and n_frames >= 2:
            ref = sorted_frames[0]
            msd_series: list[float] = []
            for frame in sorted_frames[1:]:
                if len(frame) != len(ref):
                    continue
                sq_sum = 0.0
                for i in range(len(ref)):
                    dx = ref[i][0] - frame[i][0]
                    dy = ref[i][1] - frame[i][1]
                    dz = ref[i][2] - frame[i][2]
                    sq_sum += dx * dx + dy * dy + dz * dz
                msd_series.append(round(sq_sum / max(1, len(ref)), 6))
            return {
                "metric": "msd",
                "value": msd_series,
                "unit": "Å²",
                "confidence": confidence,
                "metadata": {"method": method, "n_frames": len(msd_series)},
            }

        if metric == "diffusion_coefficient" and n_frames >= 2:
            ref = sorted_frames[0]
            msd_series: list[float] = []
            for frame in sorted_frames[1:]:
                if len(frame) != len(ref):
                    continue
                sq_sum = 0.0
                for i in range(len(ref)):
                    dx = ref[i][0] - frame[i][0]
                    dy = ref[i][1] - frame[i][1]
                    dz = ref[i][2] - frame[i][2]
                    sq_sum += dx * dx + dy * dy + dz * dz
                msd_series.append(sq_sum / max(1, len(ref)))
            # Einstein 关系 D = <Δr²>/(6·Δt)；这里用 MSD 末端线性拟合
            d_value = None
            if len(msd_series) >= 2:
                half = len(msd_series) // 2
                tail = msd_series[half:]
                if len(tail) >= 2:
                    n = len(tail)
                    xs = list(range(n))
                    sx = sum(xs)
                    sy = sum(tail)
                    sxx = sum(x * x for x in xs)
                    sxy = sum(x * y for x, y in zip(xs, tail))
                    denom = n * sxx - sx * sx
                    if denom != 0:
                        slope = (n * sxy - sx * sy) / denom
                        d_value = round(slope / 6.0, 8)
            return {
                "metric": "diffusion_coefficient",
                "value": d_value,
                "unit": "Å²/step",
                "confidence": confidence - 0.1,
                "metadata": {
                    "method": method + " Einstein",
                    "note": "单位 Å²/step，需乘以 timestep 转换为 Å²/ps 或 m²/s",
                },
            }

        if metric == "rdf" and n_frames >= 1:
            # 用首帧计算原子对距离分布
            atoms = sorted_frames[0]
            distances: list[float] = []
            for i in range(len(atoms)):
                for j in range(i + 1, len(atoms)):
                    dx = atoms[i][0] - atoms[j][0]
                    dy = atoms[i][1] - atoms[j][1]
                    dz = atoms[i][2] - atoms[j][2]
                    distances.append(math.sqrt(dx * dx + dy * dy + dz * dz))
            if not distances:
                return self._placeholder_analysis(metric, engine)
            n_bins = 40
            d_max = max(distances) if distances else 10.0
            d_min = 0.0
            bin_width = (d_max - d_min) / n_bins if d_max > d_min else 1.0
            counts = [0] * n_bins
            for d in distances:
                idx = int((d - d_min) / bin_width) if bin_width > 0 else 0
                if idx >= n_bins:
                    idx = n_bins - 1
                counts[idx] += 1
            bin_centers = [
                round(d_min + (i + 0.5) * bin_width, 4) for i in range(n_bins)
            ]
            return {
                "metric": "rdf",
                "value": {"bins": bin_centers, "counts": counts},
                "unit": "无量纲",
                "confidence": confidence - 0.05,
                "metadata": {
                    "method": method,
                    "n_bins": n_bins,
                    "n_pairs": len(distances),
                    "frame": 0,
                },
            }

        # 未覆盖的指标
        return self._placeholder_analysis(metric, engine)

    @staticmethod
    def _placeholder_analysis(metric: str, engine: str = "placeholder") -> dict[str, Any]:
        """占位分析结果 — 当分析工具不可用时使用。"""
        metric_units: dict[str, str] = {
            "rdf": "无量纲",
            "msd": "Å²",
            "diffusion_coefficient": "m²/s",
            "rmsd": "Å",
            "rmsf": "Å",
            "energy": "eV",
            "temperature": "K",
            "pressure": "bar",
            "density": "g/cm³",
            "cna": "计数",
            "angular_distribution": "无量纲",
        }
        is_real_engine = engine in ("local_lmp", "docker_lammps")
        return {
            "metric": metric,
            "value": None if is_real_engine else f"# placeholder: {metric} 分析结果",
            "unit": metric_units.get(metric, ""),
            "confidence": 0.0 if is_real_engine else 0.7,
            "metadata": {
                "method": "not_applicable" if is_real_engine else "placeholder",
                "engine": engine,
                "warning": (
                    f"指标 {metric} 在 LAMMPS 输出中不可用（engine={engine}）"
                    if is_real_engine
                    else "LAMMPS 引擎不可用，返回占位结果"
                ),
            },
        }

    def _analyze_with_ovito(self, trajectory_path: str, metric: str) -> dict[str, Any]:
        """使用 OVITO Python API 进行分析。"""
        from ovito.io import import_file
        from ovito.modifiers import CoordinationNumberModifier, CommonNeighborAnalysisModifier

        pipeline = import_file(trajectory_path)

        if metric == "rdf":
            modifier = CoordinationNumberModifier()
            pipeline.modifiers.append(modifier)
            data = pipeline.compute()
            return {
                "metric": "rdf",
                "value": data.tables["coordination-rdf"].xy,
                "unit": "无量纲",
                "confidence": 0.9,
                "metadata": {"method": "OVITO CoordinationNumberModifier"},
            }
        elif metric == "cna":
            modifier = CommonNeighborAnalysisModifier()
            pipeline.modifiers.append(modifier)
            data = pipeline.compute()
            return {
                "metric": "cna",
                "value": data.attributes["CommonNeighborAnalysis.counts"],
                "unit": "计数",
                "confidence": 0.9,
                "metadata": {"method": "OVITO CommonNeighborAnalysis"},
            }
        else:
            return {"error": f"OVITO 不支持指标: {metric}"}

    def _analyze_with_mdanalysis(self, trajectory_path: str, metric: str) -> dict[str, Any]:
        """使用 MDAnalysis 进行分析。"""
        import MDAnalysis as mda
        from MDAnalysis.analysis import rdf, diffusion, rms

        universe = mda.Universe(trajectory_path)

        if metric == "rdf":
            g = rdf.InterRDF(universe.atoms, universe.atoms)
            g.run()
            return {
                "metric": "rdf",
                "value": {"r": g.results.bins.tolist(), "g(r)": g.results.rdf.tolist()},
                "unit": "无量纲",
                "confidence": 0.9,
                "metadata": {"method": "MDAnalysis.InterRDF"},
            }
        elif metric == "msd":
            msd_analysis = diffusion.EinsteinMSD(universe, select="all", msd_type="xyz")
            msd_analysis.run()
            return {
                "metric": "msd",
                "value": {
                    "lagtimes": msd_analysis.results.timeseries.tolist(),
                    "msd": msd_analysis.results.msd.tolist(),
                },
                "unit": "Å²",
                "confidence": 0.85,
                "metadata": {"method": "MDAnalysis.EinsteinMSD"},
            }
        elif metric == "diffusion_coefficient":
            msd_analysis = diffusion.EinsteinMSD(universe, select="all", msd_type="xyz")
            msd_analysis.run()
            D = msd_analysis.results.msd[-1] / (6 * msd_analysis.results.timeseries[-1])
            return {
                "metric": "diffusion_coefficient",
                "value": D,
                "unit": "Å²/步",
                "confidence": 0.75,
                "metadata": {"method": "MDAnalysis.EinsteinMSD (slope approximation)"},
            }
        elif metric == "rmsd":
            rmsd_analysis = rms.RMSD(universe, universe, select="all")
            rmsd_analysis.run()
            return {
                "metric": "rmsd",
                "value": {
                    "time": rmsd_analysis.results.rmsd[:, 0].tolist(),
                    "rmsd": rmsd_analysis.results.rmsd[:, 2].tolist(),
                },
                "unit": "Å",
                "confidence": 0.85,
                "metadata": {"method": "MDAnalysis.RMSD"},
            }
        elif metric == "rmsf":
            rmsf_analysis = rms.RMSF(universe.select_atoms("all"))
            rmsf_analysis.run()
            return {
                "metric": "rmsf",
                "value": rmsf_analysis.results.rmsf.tolist(),
                "unit": "Å",
                "confidence": 0.85,
                "metadata": {"method": "MDAnalysis.RMSF"},
            }
        else:
            return {"error": f"MDAnalysis 不支持指标: {metric}"}

    @staticmethod
    def _placeholder_analysis(metric: str) -> dict[str, Any]:
        """占位分析结果 — 当分析工具不可用时使用。"""
        metric_units: dict[str, str] = {
            "rdf": "无量纲",
            "msd": "Å²",
            "diffusion_coefficient": "m²/s",
            "rmsd": "Å",
            "rmsf": "Å",
            "energy": "eV",
            "temperature": "K",
            "pressure": "bar",
            "density": "g/cm³",
            "cna": "计数",
            "angular_distribution": "无量纲",
        }
        return {
            "metric": metric,
            "value": f"# placeholder: {metric} 分析结果",
            "unit": metric_units.get(metric, ""),
            "confidence": 0.7,
            "metadata": {
                "method": "placeholder",
                "warning": "分析工具不可用，返回占位结果",
            },
        }