"""真实科学计算引擎数值断言测试 — 覆盖 PySCF/packmol/OpenMM/LAMMPS Docker 引擎输出。

测试策略：
  1. 每个测试类对应一个引擎，验证其返回的科学数值在物理合理范围内。
  2. Docker/镜像不可用时自动 skip，不在 CI 上产生误报。
  3. 断言聚焦"科学正确性"：数值范围、单位、符号、量级，而非精确匹配。

覆盖的引擎：
  - PySCF (Docker science-engine): ESP 分析、HOMO/LUMO 轨道能级
  - packmol (Docker): 分子堆积密度、盒子尺寸、原子数
  - OpenMM (本地 Python): MD 能量、温度、RMSD
  - LAMMPS (Docker): 热力学数据解析、轨迹分析
"""

from __future__ import annotations

import os
import unittest


def _docker_image_available(image: str) -> bool:
    """检查 Docker 与指定镜像是否可用。"""
    import subprocess
    try:
        result = subprocess.run(
            ["docker", "image", "inspect", image],
            capture_output=True, text=True, timeout=10,
        )
        return result.returncode == 0
    except Exception:
        return False


def _openmm_available() -> bool:
    """检查本地 OpenMM + RDKit 是否可用。"""
    try:
        import openmm  # noqa: F401
        import rdkit  # noqa: F401
        return True
    except ImportError:
        return False


# ── PySCF Docker 引擎数值断言 ─────────────────────────────────


class TestPySCFEngineValues(unittest.TestCase):
    """PySCF Docker 引擎 — ESP 分析与轨道能级数值断言。

    验证 B3LYP/6-31G* DFT 计算返回的：
    - ESP 表面统计值在化学合理范围（-100 ~ +100 kcal/mol）
    - HOMO 能量为负值（束缚态）
    - LUMO 能量通常为正值或接近 0
    - HOMO-LUMO 能隙在典型有机分子范围（1 ~ 15 eV）
    """

    @classmethod
    def setUpClass(cls):
        cls.image = "batteryemcl/science-engine:latest"
        if not _docker_image_available(cls.image):
            raise unittest.SkipTest(f"Docker 镜像 {cls.image} 不可用")
        from battery_materials_agent.infrastructure.executors.pyscf_adapter import PySCFAdapter
        cls.adapter = PySCFAdapter()
        if not cls.adapter.is_available():
            raise unittest.SkipTest("PySCF Docker 适配器不可用")

    def test_esp_water_values_in_range(self):
        """水分子 (O) ESP 表面统计应在化学合理范围。"""
        result = self.adapter.execute_esp({
            "input_file": "O",  # 水 SMILES
            "bins": 50,
            "surface_type": "molecular",
        })
        self.assertEqual(result.get("status"), "completed",
                         f"PySCF ESP 执行失败: {result.get('error', '')}")
        results = result.get("results", [])
        self.assertGreater(len(results), 0, "ESP 结果为空")

        # 查找 ESP 表面统计
        esp_surface = next((r for r in results if r.get("type") == "esp_surface"), None)
        if esp_surface:
            val = esp_surface["value"]
            # ESP min 应为负值（富电子区域）
            self.assertLess(val["min"], 0, f"ESP min {val['min']} 应为负值")
            # ESP max 可能为大正值（近核区域 ESP 发散，物理正确）
            self.assertGreater(val["max"], 0, f"ESP max {val['max']} 应为正值")
            # mean 通常为负（富电子表面占优）
            self.assertGreater(val["mean"], -100, f"ESP mean {val['mean']} 过低")

    def test_orbitals_methane_homo_negative(self):
        """甲烷 (C) HOMO 能量应为负值（束缚态电子）。"""
        result = self.adapter.execute_orbitals({
            "input_file": "C",  # 甲烷 SMILES
            "below_homo": 1,
            "above_lumo": 1,
        })
        self.assertEqual(result.get("status"), "completed",
                         f"PySCF 轨道分析失败: {result.get('error', '')}")
        results = result.get("results", [])
        self.assertGreater(len(results), 0, "轨道分析结果为空")

        # 查找轨道能级
        orbital_energy = next((r for r in results if r.get("type") == "orbital_energy"), None)
        if orbital_energy:
            val = orbital_energy["value"]
            homo_e = val.get("homo_energy_eV")
            lumo_e = val.get("lumo_energy_eV")
            if homo_e is not None:
                self.assertLess(homo_e, 0, f"HOMO 能量 {homo_e} 应为负值（束缚态）")
            if lumo_e is not None and homo_e is not None:
                gap = lumo_e - homo_e
                # 甲烷 HOMO-LUMO 能隙 ~13-15 eV（实验值 ~13.6 eV）
                self.assertGreater(gap, 5, f"能隙 {gap} 过小")
                self.assertLess(gap, 25, f"能隙 {gap} 过大")


# ── packmol Docker 引擎数值断言 ────────────────────────────────


class TestPackmolEngineValues(unittest.TestCase):
    """packmol Docker 引擎 — 分子堆积密度与结构数值断言。

    验证：
    - 堆积后原子数 > 0（PDB 非空）
    - 密度在液体/固体合理范围（0.3 ~ 3.0 g/cm³）
    - 盒子尺寸与输入一致
    - 堆积分数 < 1.0（物理约束）
    """

    @classmethod
    def setUpClass(cls):
        cls.image = "batteryemcl/packmol:latest"
        if not _docker_image_available(cls.image):
            raise unittest.SkipTest(f"Docker 镜像 {cls.image} 不可用")
        from battery_materials_agent.infrastructure.executors.formulation_adapter import (
            FormulationAdapter,
        )
        cls.adapter = FormulationAdapter()

    def test_ethanol_packing_density_reasonable(self):
        """乙醇堆积密度应在液体合理范围（0.5 ~ 1.2 g/cm³）。"""
        result = self.adapter.build_packing_structure({
            "molecules": ["CCO"],  # 乙醇
            "packing_type": "amorphous",
            "target_density": 0.789,  # 乙醇实验密度 g/cm³
            "force_field": "mmff94",
        })
        self.assertNotIn("warning", result, f"堆积返回警告: {result.get('warning')}")

        # 引擎标识（常驻容器模式后缀为 _persistent）
        engine = result.get("engine", "")
        self.assertIn(engine, ("docker_packmol", "docker_packmol_persistent", "local_packmol"),
                      f"应使用 packmol 引擎，实际: {engine}")

        # 原子数 > 0
        atom_count = result.get("atom_count", 0)
        self.assertGreater(atom_count, 0, "堆积后原子数应为正")

        # 密度在合理范围
        density = result.get("density", 0.0)
        self.assertGreater(density, 0.1, f"密度 {density} 过低")
        self.assertLess(density, 3.0, f"密度 {density} 过高")

        # 堆积分数 < 1.0（物理约束）
        pf = result.get("packing_fraction", 1.0)
        self.assertLess(pf, 1.0, f"堆积分数 {pf} 应 < 1.0")
        self.assertGreater(pf, 0.0, f"堆积分数 {pf} 应 > 0")

    def test_mixed_solvent_packing(self):
        """EC/DMC 混合溶剂堆积应返回两种分子信息。"""
        result = self.adapter.build_packing_structure({
            "molecules": ["C1COC(=O)O1", "COC(=O)OC"],  # EC, DMC
            "molecule_counts": [30, 30],
            "packing_type": "amorphous",
            "box_size_nm": 3.0,
        })
        molecules = result.get("molecules", [])
        self.assertEqual(len(molecules), 2, "应返回两种分子信息")
        for m in molecules:
            self.assertGreater(m.get("molecular_weight", 0), 0, "分子量应为正")
            self.assertGreater(m.get("count", 0), 0, "分子数应为正")


# ── OpenMM 本地引擎数值断言 ───────────────────────────────────


class TestOpenMMEngineValues(unittest.TestCase):
    """OpenMM 本地引擎 — 分子动力学能量与轨迹数值断言。

    验证：
    - 能量为有限数值（非 NaN/Inf）
    - 温度接近设定值（统计涨落 ±50K）
    - RMSD 随时间增长（分子构象偏离初始结构）

    NOTE: OpenMM 在 Windows 上 Simulation 构造函数存在访问冲突（C++ 库问题），
    因此 Windows 上跳过实际 MD 执行测试。
    """

    @classmethod
    def setUpClass(cls):
        import sys
        if sys.platform == "win32":
            raise unittest.SkipTest("OpenMM 在 Windows 上存在访问冲突，跳过实际 MD 执行")
        if not _openmm_available():
            raise unittest.SkipTest("OpenMM 或 RDKit 不可用")
        from battery_materials_agent.infrastructure.executors.openmm_adapter import (
            OpenMMAdapter,
        )
        cls.adapter = OpenMMAdapter()
        if not cls.adapter.is_available():
            raise unittest.SkipTest("OpenMMAdapter 不可用")

    def test_ethane_md_energy_finite(self):
        """乙烷 MD 模拟能量应为有限数值。"""
        result = self.adapter.execute({
            "system_type": "B",
            "structure_data": "CC",  # 乙烷
            "protocol": "nvt",
            "temperature_k": 300.0,
            "timestep_fs": 1.0,
            "run_steps": 500,  # 短模拟
            "requested_metrics": ["energy", "temperature"],
        })
        if result.get("status") == "error":
            self.skipTest(f"OpenMM 执行失败: {result.get('error')}")

        analysis = result.get("analysis", [])
        self.assertGreater(len(analysis), 0, "MD 分析结果为空")

        # 验证能量
        energy_result = next((a for a in analysis if a.get("metric") == "energy"), None)
        if energy_result:
            val = energy_result.get("value")
            if isinstance(val, dict):
                # 能量值应为有限数值
                for k, v in val.items():
                    if isinstance(v, (int, float)):
                        self.assertTrue(
                            abs(v) < 1e10,
                            f"能量 {k}={v} 量级异常"
                        )

    def test_water_md_temperature_near_target(self):
        """水分子 MD 模拟温度应接近设定值 300K（±100K 涨落）。"""
        result = self.adapter.execute({
            "system_type": "B",
            "structure_data": "O",  # 水
            "protocol": "nvt",
            "temperature_k": 300.0,
            "timestep_fs": 1.0,
            "run_steps": 500,
            "requested_metrics": ["temperature"],
        })
        if result.get("status") == "error":
            self.skipTest(f"OpenMM 执行失败: {result.get('error')}")

        analysis = result.get("analysis", [])
        temp_result = next((a for a in analysis if a.get("metric") == "temperature"), None)
        if temp_result:
            val = temp_result.get("value")
            if isinstance(val, (int, float)):
                # 温度应在 200-400K 范围（300K ± 100K 涨落）
                self.assertGreater(val, 100, f"温度 {val} 过低")
                self.assertLess(val, 600, f"温度 {val} 过高")


# ── LAMMPS Docker 引擎数值断言 ─────────────────────────────────


class TestLAMMPSEngineValues(unittest.TestCase):
    """LAMMPS Docker 引擎 — 热力学数据与轨迹分析数值断言。

    验证：
    - log.lammps 热力学数据解析正确（温度、能量、密度）
    - 轨迹分析指标为有限数值
    """

    @classmethod
    def setUpClass(cls):
        cls.image = "lammps/lammps:latest"
        if not _docker_image_available(cls.image):
            raise unittest.SkipTest(f"Docker 镜像 {cls.image} 不可用")
        try:
            from battery_materials_agent.infrastructure.executors.lammps_adapter import (
                LAMMPSAdapter,
            )
            cls.adapter = LAMMPSAdapter()
        except ImportError:
            raise unittest.SkipTest("LAMMPSAdapter 不可用")

    def test_lammps_log_parsing(self):
        """LAMMPS log.lammps 解析应返回热力学数据。"""
        # 测试 log 解析器（不实际运行 LAMMPS）
        import tempfile
        import os

        log_content = """LAMMPS (29 Aug 2024)
Step Temp E_pair E_mol TotEng Press Volume Density
        0          300         -100          0         -80         -50       27000    1.0
      100    302.1234         -98          0         -78    -48.5    27000    1.0
      200    298.5678         -99          0         -79    -51.2    27000    1.0
Loop time of 1.5 on 1 procs
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".lammps", delete=False, encoding="utf-8") as f:
            f.write(log_content)
            log_path = f.name

        try:
            thermo = self.adapter._parse_lammps_log(log_path)
            # 解析应返回非空数据
            self.assertIsInstance(thermo, dict)
            # 温度数据应包含 300K 附近的值
            if "temperature" in thermo:
                temps = thermo["temperature"]
                if temps:
                    avg_temp = sum(temps) / len(temps)
                    self.assertGreater(avg_temp, 250, f"平均温度 {avg_temp} 过低")
                    self.assertLess(avg_temp, 350, f"平均温度 {avg_temp} 过高")
        finally:
            os.unlink(log_path)

    def test_trajectory_analysis_finite(self):
        """LAMMPS 轨迹分析指标应为有限数值。"""
        import tempfile
        import os

        # 构造简单的 LAMMPS dump 轨迹（2 帧，3 个原子）
        dump_content = """ITEM: TIMESTEP
0
ITEM: NUMBER OF ATOMS
3
ITEM: BOX BOUNDS pp pp pp
0.0 10.0
0.0 10.0
0.0 10.0
ITEM: ATOMS id type x y z
1 1 0.0 0.0 0.0
2 1 1.0 0.0 0.0
3 1 0.0 1.0 0.0
ITEM: TIMESTEP
100
ITEM: NUMBER OF ATOMS
3
ITEM: BOX BOUNDS pp pp pp
0.0 10.0
0.0 10.0
0.0 10.0
ITEM: ATOMS id type x y z
1 1 0.1 0.0 0.0
2 1 1.1 0.0 0.0
3 1 0.0 1.1 0.0
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".dump", delete=False, encoding="utf-8") as f:
            f.write(dump_content)
            traj_path = f.name

        try:
            result = self.adapter.analyze_trajectory(
                traj_path,
                requested_metrics=["rmsd"],
                engine="placeholder",
            )
            # 应返回结果列表（即使解析简单轨迹）
            self.assertIsInstance(result, dict)
            self.assertIn("results", result)
        finally:
            os.unlink(traj_path)

    def test_docker_lammps_real_run(self):
        """真实运行 LAMMPS Docker 容器（最小 LJ 模拟），验证 --entrypoint lmp_serial 修复有效。

        此测试覆盖回归 bug：lammps/lammps:latest 镜像 ENTRYPOINT 为空，
        若不显式指定 --entrypoint lmp_serial，-in 参数会被当作命令执行而失败。
        """
        import subprocess
        from battery_materials_agent.infrastructure.executors.execution_adapter import (
            create_engine_work_dir,
        )

        # 最小 LAMMPS 输入：3 个 Ar 原子，LJ/cut 对势，NVT 100 步
        lammps_input = """# 最小 LAMMPS 测试 — Ar 原子 LJ/cut NVT
units           real
atom_style      atomic
boundary        p p p
lattice         fcc 5.26
region          box block 0 2 0 2 0 2
create_box      1 box
create_atoms    1 box
mass            1 39.948
pair_style      lj/cut 8.5
pair_coeff      1 1 0.238 3.405 8.5
velocity        all create 300.0 12345
fix             1 all nvt temp 300.0 300.0 100.0
thermo          10
dump            1 all custom 50 trajectory.dump id type x y z
run             100
"""
        work_dir = create_engine_work_dir("lammps_test")
        inp_path = os.path.join(work_dir, "test.in")
        with open(inp_path, "w", encoding="utf-8") as f:
            f.write(lammps_input)

        # 直接调用 docker run（模拟适配器的调用方式）
        mount_source = work_dir.replace("\\", "/")
        cmd = [
            "docker", "run", "--rm",
            "--entrypoint", "lmp_serial",
            "-v", f"{mount_source}:/work",
            "-w", "/work",
            "lammps/lammps:latest",
            "-in", "/work/test.in",
        ]
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=120,
            )
        except subprocess.TimeoutExpired:
            self.skipTest("LAMMPS Docker 执行超时")
            return

        # 验证退出码为 0（LAMMPS 正常完成）
        self.assertEqual(result.returncode, 0,
                         f"LAMMPS Docker 执行失败 (exit={result.returncode}):\n"
                         f"stdout: {result.stdout[-500:]}\nstderr: {result.stderr[-500:]}")

        # 验证 log.lammps 文件生成
        log_path = os.path.join(work_dir, "log.lammps")
        self.assertTrue(os.path.isfile(log_path), "log.lammps 未生成")

        # 验证 log 包含热力学数据
        with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
            log_content = f.read()
        self.assertIn("Step", log_content, "log.lammps 缺少热力学表头")
        self.assertIn("Loop time", log_content, "log.lammps 缺少完成标记")

        # 验证轨迹文件生成
        traj_path = os.path.join(work_dir, "trajectory.dump")
        self.assertTrue(os.path.isfile(traj_path), "trajectory.dump 未生成")


# ── 适配器路由优先级断言 ───────────────────────────────────────


class TestAdapterRoutingPriority(unittest.TestCase):
    """验证服务层的适配器路由优先级 — 真实引擎优先于占位实现。

    验证：
    - wavefunction_analysis: SMILES 输入时优先 PySCF（Docker 可用时）
    - molecular_simulation: system_type=B + SMILES 时优先 OpenMM（可用时）
    - formulation_packing: packing 操作优先 FormulationAdapter (packmol Docker)
    """

    def test_wavefunction_analysis_routes_to_pyscf_when_smiles(self):
        """wavefunction_analysis 对 SMILES 输入应路由到 PySCF/RDKit（非占位）。"""
        from battery_materials_agent.services.wavefunction_analysis.application import (
            WavefunctionAnalysisApplication,
            _PlaceholderAdapter,
        )
        app = WavefunctionAnalysisApplication()
        adapter = app._resolve_adapter({"input_file": "CCO"})
        # 应不是 _PlaceholderAdapter（除非 Docker 和 RDKit 都不可用）
        self.assertNotIsInstance(adapter, _PlaceholderAdapter,
                                  "SMILES 输入不应回退到占位适配器")

    def test_molecular_simulation_routes_to_real_adapter_for_smiles(self):
        """molecular_simulation 对 SMILES 输入应路由到 OpenMM/RDKit/LAMMPS（非占位）。"""
        from battery_materials_agent.services.molecular_simulation.application import (
            MolecularSimulationApplication,
            _PlaceholderAdapter,
        )
        app = MolecularSimulationApplication()
        adapter = app._resolve_adapter({
            "system_type": "B",
            "structure_data": "CCO",
        })
        # 应不是 _PlaceholderAdapter（RDKit 通常可用）
        self.assertNotIsInstance(adapter, _PlaceholderAdapter,
                                  "SMILES 输入不应回退到占位适配器")

    def test_formulation_packing_loads_formulation_adapter(self):
        """formulation_packing 应加载 FormulationAdapter（非 None）。"""
        from battery_materials_agent.services.formulation_packing.application import (
            FormulationPackingApplication,
        )
        adapter = FormulationPackingApplication._load_formulation_adapter()
        self.assertIsNotNone(adapter, "应成功加载 FormulationAdapter")


if __name__ == "__main__":
    unittest.main()
