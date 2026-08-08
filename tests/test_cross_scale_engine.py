"""CrossScaleEngine 真实求解器耦合测试。

覆盖：
- LAMMPS 适配器：可用性探测、热力学输出解析（热导率 / MSD 离子扩散）
- FEniCSx 适配器：真实求解不可用时优雅降级（返回 None）
- CrossScaleEngine：求解器状态上报、真实抓手切入点、模板降级标记 estimate

真实求解器（Docker LAMMPS / dolfinx）通常不在 CI 环境安装，
因此对真实执行路径做 mock，聚焦"耦合 + 解析 + 降级"逻辑。
"""

import asyncio
import unittest
from unittest import mock


# ── LAMMPS 适配器单元测试 ─────────────────────────────────────


class TestLAMMPSAdapter(unittest.TestCase):
    """LAMMPS 适配器 — 热力学输出解析与可用性探测。"""

    def setUp(self):
        from battery_materials_agent.cross_scale.solvers.lammps_adapter import LAMMPSAdapter
        self.adapter = LAMMPSAdapter.__new__(LAMMPSAdapter)  # 绕过 __init__ 探测

    def test_parse_thermo_tail_thermal_conductivity(self):
        """应能从输出尾部解析最近温度值（热导率路径）。"""
        stdout = """LAMMPS (29 Aug 2024)
Step Temp E_pair E_mol TotEng Press
        0          300         -100          0         -80         -50
      100    302.1234         -98          0         -78    -48.5
      200    298.5678         -99          0         -79    -51.2
Loop time of 1.5 on 1 procs
"""
        val = self.adapter._parse_thermo_tail(stdout, "Temp")
        self.assertIsNotNone(val)
        self.assertAlmostEqual(val, 298.5678, places=3)

    def test_parse_thermo_tail_msd_ion_diffusion(self):
        """应能从含 c_msd1[4] 列的输出解析 MSD 值（离子扩散路径）。"""
        stdout = """LAMMPS (29 Aug 2024)
Step Temp c_msd1[4]
        0    300      0.0
      100    302      12.5
      200    298      25.1
Loop time of 1.5 on 1 procs
"""
        val = self.adapter._parse_thermo_tail(stdout, "c_msd1[4]")
        self.assertIsNotNone(val)
        self.assertAlmostEqual(val, 25.1, places=3)

    def test_parse_thermo_tail_missing_key(self):
        """key 不在输出中时应返回 None（不抛异常）。"""
        stdout = "Step Temp\n0 300\n100 301\n"
        self.assertIsNone(self.adapter._parse_thermo_tail(stdout, "c_msd1[4]"))

    def test_parse_thermo_tail_no_rows(self):
        """无数据行时应返回 None。"""
        self.assertIsNone(self.adapter._parse_thermo_tail("no data here\n", "Temp"))

    @mock.patch("battery_materials_agent.cross_scale.solvers.lammps_adapter.shutil.which", return_value=None)
    @mock.patch("battery_materials_agent.cross_scale.solvers.lammps_adapter._docker_lammps_available", return_value=False)
    def test_available_false_when_no_backend(self, _docker, _which):
        """无本地二进制、无 Python 模块、无 Docker 时不可用。"""
        import battery_materials_agent.cross_scale.solvers.lammps_adapter as mod
        mod._available = None
        try:
            self.assertFalse(mod.lammps_available())
        finally:
            mod._available = None

    @mock.patch("battery_materials_agent.cross_scale.solvers.lammps_adapter.shutil.which", return_value="/usr/bin/lmp")
    def test_available_true_when_local_binary(self, _which):
        """存在本地 lmp 可执行文件时可用。"""
        import battery_materials_agent.cross_scale.solvers.lammps_adapter as mod
        mod._available = None
        try:
            self.assertTrue(mod.lammps_available())
        finally:
            mod._available = None

    def test_ion_diffusion_einstein_relation(self):
        """离子扩散路径：MSD → 爱因斯坦关系 D = MSD/(6·t)。"""
        import numpy as np
        n_steps = 2000
        dt = 0.005
        msd = 25.1
        D = msd / (6.0 * n_steps * dt)
        self.assertAlmostEqual(D, msd / 60.0, places=6)


# ── FEniCSx 适配器降级测试 ────────────────────────────────────


@mock.patch("battery_materials_agent.cross_scale.solvers.fenicsx_adapter.fenicsx_available", return_value=False)
class TestFEniCSxAdapter(unittest.TestCase):
    """FEniCSx 不可用时优雅降级到模板近似。"""

    def test_run_returns_none_when_unavailable(self, _avail):
        from battery_materials_agent.cross_scale.solvers.fenicsx_adapter import FEniCSxAdapter
        adapter = FEniCSxAdapter()
        self.assertFalse(adapter.available)
        self.assertIsNone(adapter.run({"formula": "LiCoO2"}, thermal_k=1.0))


# ── CrossScaleEngine 耦合测试 ──────────────────────────────────


class _MockPredictor:
    """模拟 predictor.predict(features, name) → 带 value/unit/confidence/model 的对象。"""

    PREDICTABLE_PROPERTIES = ("band_gap", "formation_energy", "ionic_conductivity")

    def __init__(self, values=None):
        self._values = values or {
            "band_gap": 3.0,
            "formation_energy": -2.0,
            "ionic_conductivity": 1.0e-3,
        }

    def predict(self, features, name):
        from types import SimpleNamespace
        v = self._values.get(name)
        return SimpleNamespace(
            value=v, unit="", confidence=0.9, model="mock",
        )


class _MockPlanner:
    """模拟合成规划器：返回空路由，触发模板化回退。"""

    def __init__(self):
        self._routes = []

    def plan_synthesis(self, smiles, *args, **kwargs):
        return self._routes

    def _build_local_tree(self, smiles, *args, **kwargs):
        return []


class _MockAgent:
    def __init__(self):
        self.crystal_predictor = _MockPredictor()
        self.polymer_predictor = _MockPredictor()
        self.synthesis_planner = _MockPlanner()


class TestCrossScaleEngine(unittest.TestCase):
    """CrossScaleEngine — 真实求解器耦合与模板降级。"""

    @classmethod
    def setUpClass(cls):
        from battery_materials_agent.cross_scale.engine import CrossScaleEngine
        cls.engine = CrossScaleEngine(agent=_MockAgent())

    def test_solver_status_reports_both_solvers(self):
        """solver_status 应报告 lammps 与 fenicsx 可用性。"""
        status = self.engine.solver_status()
        self.assertIn("lammps", status)
        self.assertIn("fenicsx", status)
        self.assertIn("available", status["lammps"])
        self.assertIn("engine", status["lammps"])

    @mock.patch("battery_materials_agent.cross_scale.engine.lammps_available", return_value=False)
    @mock.patch("battery_materials_agent.cross_scale.engine.fenicsx_available", return_value=False)
    def test_run_cross_scale_falls_back_to_templates(self, _fen, _lam):
        """求解器不可用时，各尺度应标记 estimate 且流程不中断。"""
        result = asyncio.run(self.engine.run_cross_scale(
            {"type": "crystal", "formula": "LiCoO2"},
            scales=["molecular", "reaction", "continuum"],
        ))
        self.assertIn("molecular", result)
        self.assertIn("reaction", result)
        self.assertIn("continuum", result)
        self.assertIn("coupled", result)
        # 连续介质尺度无真实求解器 → estimate=True
        self.assertTrue(result["continuum"]["estimate"])
        # 分子尺度有 predictor → estimate=False
        self.assertFalse(result["molecular"]["estimate"])
        # 耦合分析产出
        self.assertIn("correlations", result["coupled"])
        self.assertIn("summary", result["coupled"])

    @mock.patch("battery_materials_agent.cross_scale.engine.lammps_available", return_value=False)
    @mock.patch("battery_materials_agent.cross_scale.engine.fenicsx_available", return_value=False)
    def test_run_cross_scale_subset_scales(self, _fen, _lam):
        """只请求部分尺度时，仅执行对应尺度。"""
        result = asyncio.run(self.engine.run_cross_scale(
            {"type": "crystal", "formula": "LiCoO2"},
            scales=["molecular"],
        ))
        self.assertIn("molecular", result)
        self.assertNotIn("reaction", result)
        self.assertNotIn("continuum", result)

    @mock.patch("battery_materials_agent.cross_scale.engine.lammps_available", return_value=True)
    def test_molecular_scale_includes_lammps_when_available(self, _avail):
        """LAMMPS 可用时分子尺度应补充 md 真实结果。"""
        with mock.patch.object(
            self.engine, "_run_lammps_tasks",
            return_value={"thermal_conductivity": {"task": "thermal_conductivity", "engine": "real"}},
        ):
            result = asyncio.run(self.engine.run_cross_scale(
                {"type": "crystal", "formula": "LiCoO2"},
                scales=["molecular"],
            ))
        self.assertIn("md", result["molecular"])
        self.assertEqual(result["molecular"]["md"]["thermal_conductivity"]["engine"], "real")

    @mock.patch("battery_materials_agent.cross_scale.engine.lammps_available", return_value=False)
    @mock.patch("battery_materials_agent.cross_scale.engine.fenicsx_available", return_value=True)
    def test_continuum_scale_includes_pde_when_fenicsx_available(self, _fen_avail, _lam):
        """FEniCSx 可用时连续介质尺度应补充 pde 真实结果。"""
        with mock.patch.object(
            self.engine, "_run_fenicsx",
            return_value={"estimate": False, "result": {"task": "thermo_electrochemical_coupling"}},
        ):
            result = asyncio.run(self.engine.run_cross_scale(
                {"type": "crystal", "formula": "LiCoO2"},
                scales=["continuum"],
            ))
        self.assertIn("pde", result["continuum"])
        self.assertEqual(result["continuum"]["pde"]["result"]["task"], "thermo_electrochemical_coupling")

    def test_kinetics_derivation(self):
        """反应尺度动力学参数（Arrhenius）应合理。"""
        k = self.engine._step_kinetics(0, "esterification")
        self.assertEqual(k["step"], 1)
        self.assertGreater(k["rate_constant"], 0)
        self.assertGreater(k["temperature_kelvin"], 273.15)


if __name__ == "__main__":
    unittest.main()