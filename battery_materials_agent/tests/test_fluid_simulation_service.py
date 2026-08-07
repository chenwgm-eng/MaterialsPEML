"""流体动力学模拟服务单元测试 — FluidSimulationApplication 的完整生命周期验证。"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from battery_materials_agent.contracts.task import Task
from battery_materials_agent.contracts.run import Run
from battery_materials_agent.contracts.artifact import Artifact, ArtifactType
from battery_materials_agent.contracts.evidence import EvidencePackage, EvidenceLevel
from battery_materials_agent.services.fluid_simulation.application import (
    FluidSimulationApplication,
    RunSimulation,
    ResumeSimulation,
    AnalyzeSimulation,
    ParameterSweep,
    SOLVER_CATALOG,
)
from battery_materials_agent.services.fluid_simulation.validators import (
    FluidSimulationValidator,
    validate_solver, validate_grid_params, validate_physical_params,
    validate_time_params, validate_initial_conditions, validate_forcing_params,
    validate_stratified_params, validate_output_config,
    VALID_SOLVERS, SOLVER_NAMES, VALID_INITIAL_CONDITIONS,
)
from battery_materials_agent.services.fluid_simulation.evidence_mapper import (
    map_fluid_evidence, batch_map_fluid_evidence,
    map_run_statistics, map_field_analysis, map_spectra_analysis, map_convergence_analysis,
)
from battery_materials_agent.infrastructure.executors.fluidsim_adapter import (
    FluidSimAdapter, _PlaceholderAdapter,
)


# =============================================================================
# 校验器类
# =============================================================================


class TestFluidValidator(unittest.TestCase):
    """FluidSimulationValidator 综合校验逻辑测试。"""

    def setUp(self):
        self.valid_grid = {"nx": 64, "ny": 64, "Lx": 6.2832, "Ly": 6.2832}
        self.valid_physical = {"nu_2": 1e-4, "nu_4": 0.0}
        self.valid_time = {"t_end": 10.0, "cfl_coef": 0.5}
        self.valid_ic = {"type": "noise", "amplitude": 1.0}

    def test_validate_all_valid_ns2d(self):
        """验证有效 ns2d 输入应返回 validated=True 且无错误。"""
        result = FluidSimulationValidator.validate_all(
            solver="ns2d",
            grid_params=self.valid_grid,
            physical_params=self.valid_physical,
            time_params=self.valid_time,
            initial_conditions=self.valid_ic,
        )
        self.assertTrue(result["validated"])
        self.assertEqual(len(result["errors"]), 0)

    def test_validate_all_valid_ns3d(self):
        """验证有效 ns3d 输入（含 nz/Lz）应返回 validated=True。"""
        grid = {**self.valid_grid, "nz": 32, "Lz": 3.1416}
        result = FluidSimulationValidator.validate_all(
            solver="ns3d",
            grid_params=grid,
            physical_params=self.valid_physical,
            time_params=self.valid_time,
            initial_conditions=self.valid_ic,
        )
        self.assertTrue(result["validated"])
        self.assertEqual(len(result["errors"]), 0)

    def test_validate_all_valid_stratified(self):
        """验证有效分层流输入应返回 validated=True。"""
        physical = {**self.valid_physical, "N": 1.0, "f": 0.5}
        result = FluidSimulationValidator.validate_all(
            solver="ns2d_strat",
            grid_params=self.valid_grid,
            physical_params=physical,
            time_params=self.valid_time,
            initial_conditions=self.valid_ic,
        )
        self.assertTrue(result["validated"])
        self.assertEqual(len(result["errors"]), 0)

    def test_validate_all_valid_sw1l(self):
        """验证有效浅水方程输入应返回 validated=True。"""
        physical = {**self.valid_physical, "f": 0.5, "H": 1.0}
        result = FluidSimulationValidator.validate_all(
            solver="sw1l",
            grid_params=self.valid_grid,
            physical_params=physical,
            time_params=self.valid_time,
            initial_conditions=self.valid_ic,
        )
        self.assertTrue(result["validated"])
        self.assertEqual(len(result["errors"]), 0)

    def test_validate_all_invalid_solver(self):
        """验证无效求解器应返回 validated=False。"""
        result = FluidSimulationValidator.validate_all(
            solver="invalid_solver",
            grid_params=self.valid_grid,
            physical_params=self.valid_physical,
            time_params=self.valid_time,
            initial_conditions=self.valid_ic,
        )
        self.assertFalse(result["validated"])
        self.assertGreater(len(result["errors"]), 0)
        self.assertIn("无效求解器", str(result["errors"]))

    def test_validate_all_empty_solver(self):
        """验证空求解器应返回错误。"""
        result = FluidSimulationValidator.validate_all(
            solver="",
            grid_params=self.valid_grid,
            physical_params={},
            time_params={},
            initial_conditions={},
        )
        self.assertFalse(result["validated"])
        self.assertIn("不能为空", str(result["errors"]))

    def test_validate_all_missing_grid(self):
        """验证缺少网格参数应返回错误。"""
        result = FluidSimulationValidator.validate_all(
            solver="ns2d",
            grid_params={},
            physical_params={},
            time_params=self.valid_time,
            initial_conditions=self.valid_ic,
        )
        self.assertFalse(result["validated"])
        self.assertIn("网格参数不能为空", str(result["errors"]))

    def test_validate_all_missing_nx(self):
        """验证缺少 nx 应返回错误。"""
        result = FluidSimulationValidator.validate_all(
            solver="ns2d",
            grid_params={"ny": 64, "Lx": 6.28, "Ly": 6.28},
            physical_params={},
            time_params=self.valid_time,
            initial_conditions=self.valid_ic,
        )
        self.assertFalse(result["validated"])
        self.assertIn("nx", str(result["errors"]))

    def test_validate_all_missing_t_end(self):
        """验证缺少 t_end 应返回错误。"""
        result = FluidSimulationValidator.validate_all(
            solver="ns2d",
            grid_params=self.valid_grid,
            physical_params={},
            time_params={"cfl_coef": 0.5},
            initial_conditions=self.valid_ic,
        )
        self.assertFalse(result["validated"])
        self.assertIn("t_end", str(result["errors"]))

    def test_validate_all_empty_ic(self):
        """验证空初始条件应返回错误。"""
        result = FluidSimulationValidator.validate_all(
            solver="ns2d",
            grid_params=self.valid_grid,
            physical_params={},
            time_params=self.valid_time,
            initial_conditions={},
        )
        self.assertFalse(result["validated"])
        self.assertIn("初始条件不能为空", str(result["errors"]))

    def test_validate_all_negative_nu_2(self):
        """验证负 nu_2 应返回错误。"""
        result = FluidSimulationValidator.validate_all(
            solver="ns2d",
            grid_params=self.valid_grid,
            physical_params={"nu_2": -1e-4},
            time_params=self.valid_time,
            initial_conditions=self.valid_ic,
        )
        self.assertFalse(result["validated"])
        self.assertIn("nu_2", str(result["errors"]))

    def test_validate_all_with_forcing(self):
        """验证含 Kolmogorov 强制力的有效输入应通过。"""
        result = FluidSimulationValidator.validate_all(
            solver="ns2d",
            grid_params=self.valid_grid,
            physical_params=self.valid_physical,
            time_params=self.valid_time,
            initial_conditions=self.valid_ic,
            forcing={"type": "kolmogorov", "kf": 4, "epsilon": 0.1},
        )
        self.assertTrue(result["validated"])

    def test_validate_all_invalid_forcing_type(self):
        """验证无效强制力类型应返回错误。"""
        result = FluidSimulationValidator.validate_all(
            solver="ns2d",
            grid_params=self.valid_grid,
            physical_params=self.valid_physical,
            time_params=self.valid_time,
            initial_conditions=self.valid_ic,
            forcing={"type": "invalid_force"},
        )
        self.assertFalse(result["validated"])
        self.assertIn("强制力类型", str(result["errors"]))

    def test_validate_all_with_output_config(self):
        """验证含输出配置的有效输入应通过。"""
        result = FluidSimulationValidator.validate_all(
            solver="ns2d",
            grid_params=self.valid_grid,
            physical_params=self.valid_physical,
            time_params=self.valid_time,
            initial_conditions=self.valid_ic,
            output_config={"periods_save": 1.0, "save_spectra": True},
        )
        self.assertTrue(result["validated"])


# =============================================================================
# 校验函数
# =============================================================================


class TestValidateSolver(unittest.TestCase):
    """validate_solver 函数测试。"""

    def test_valid_solver_ns2d(self):
        """验证 ns2d 应返回 None。"""
        self.assertIsNone(validate_solver("ns2d"))

    def test_valid_solver_sw1l(self):
        """验证 sw1l 应返回 None。"""
        self.assertIsNone(validate_solver("sw1l"))

    def test_empty_solver(self):
        """验证空求解器应返回错误。"""
        self.assertIn("不能为空", validate_solver(""))

    def test_invalid_solver(self):
        """验证无效求解器应返回错误。"""
        self.assertIn("无效求解器", validate_solver("ns5d"))


class TestValidateGridParams(unittest.TestCase):
    """validate_grid_params 函数测试。"""

    def test_empty_grid(self):
        """验证空网格参数应返回错误。"""
        errors = validate_grid_params({})
        self.assertGreater(len(errors), 0)
        self.assertIn("网格参数不能为空", str(errors))

    def test_valid_grid_2d(self):
        """验证有效的 2D 网格参数应返回空列表。"""
        errors = validate_grid_params({"nx": 64, "ny": 64, "Lx": 6.28, "Ly": 6.28})
        self.assertEqual(len(errors), 0)

    def test_valid_grid_3d(self):
        """验证有效的 3D 网格参数应返回空列表。"""
        errors = validate_grid_params({"nx": 64, "ny": 64, "nz": 32, "Lx": 6.28, "Ly": 6.28, "Lz": 3.14})
        self.assertEqual(len(errors), 0)

    def test_nx_not_positive(self):
        """验证非正 nx 应返回错误。"""
        errors = validate_grid_params({"nx": 0, "ny": 64, "Lx": 6.28, "Ly": 6.28})
        self.assertGreater(len(errors), 0)
        self.assertIn("nx", str(errors))

    def test_nx_not_int(self):
        """验证非整数 nx 应返回错误。"""
        errors = validate_grid_params({"nx": 64.5, "ny": 64, "Lx": 6.28, "Ly": 6.28})
        self.assertIn("nx", str(errors))

    def test_ly_not_positive(self):
        """验证非正 Ly 应返回错误。"""
        errors = validate_grid_params({"nx": 64, "ny": 64, "Lx": 6.28, "Ly": -1})
        self.assertIn("Ly", str(errors))

    def test_nz_not_positive(self):
        """验证非正 nz 应返回错误。"""
        errors = validate_grid_params({"nx": 64, "ny": 64, "nz": 0, "Lx": 6.28, "Ly": 6.28})
        self.assertIn("nz", str(errors))


class TestValidatePhysicalParams(unittest.TestCase):
    """validate_physical_params 函数测试。"""

    def test_empty_physical(self):
        """验证空物理参数应返回空列表。"""
        self.assertEqual(len(validate_physical_params({})), 0)

    def test_valid_nu_2(self):
        """验证有效的 nu_2 应返回空列表。"""
        self.assertEqual(len(validate_physical_params({"nu_2": 1e-4})), 0)

    def test_zero_nu_2(self):
        """验证零 nu_2 应返回空列表（允许无粘模拟）。"""
        self.assertEqual(len(validate_physical_params({"nu_2": 0.0})), 0)

    def test_negative_nu_2(self):
        """验证负 nu_2 应返回错误。"""
        errors = validate_physical_params({"nu_2": -1e-4})
        self.assertGreater(len(errors), 0)
        self.assertIn("nu_2", str(errors))

    def test_valid_nu_4(self):
        """验证有效的 nu_4 应返回空列表。"""
        self.assertEqual(len(validate_physical_params({"nu_4": 1e-6})), 0)

    def test_negative_nu_4(self):
        """验证负 nu_4 应返回错误。"""
        errors = validate_physical_params({"nu_4": -1e-6})
        self.assertIn("nu_4", str(errors))


class TestValidateTimeParams(unittest.TestCase):
    """validate_time_params 函数测试。"""

    def test_empty_time(self):
        """验证空时间参数应返回错误。"""
        errors = validate_time_params({})
        self.assertGreater(len(errors), 0)
        self.assertIn("时间参数不能为空", str(errors))

    def test_valid_time(self):
        """验证有效时间参数应返回空列表。"""
        errors = validate_time_params({"t_end": 10.0, "cfl_coef": 0.5})
        self.assertEqual(len(errors), 0)

    def test_negative_t_end(self):
        """验证负 t_end 应返回错误。"""
        errors = validate_time_params({"t_end": -1, "cfl_coef": 0.5})
        self.assertIn("t_end", str(errors))

    def test_cfl_too_low(self):
        """验证过低的 cfl_coef 应返回警告。"""
        errors = validate_time_params({"t_end": 10.0, "cfl_coef": 0.001})
        self.assertGreater(len(errors), 0)
        self.assertIn("cfl_coef", str(errors))

    def test_cfl_too_high(self):
        """验证过高的 cfl_coef 应返回警告。"""
        errors = validate_time_params({"t_end": 10.0, "cfl_coef": 5.0})
        self.assertIn("cfl_coef", str(errors))

    def test_valid_t_initial(self):
        """验证有效的 t_initial 应返回空列表。"""
        errors = validate_time_params({"t_end": 10.0, "t_initial": 0.0})
        self.assertEqual(len(errors), 0)

    def test_negative_t_initial(self):
        """验证负 t_initial 应返回错误。"""
        errors = validate_time_params({"t_end": 10.0, "t_initial": -1})
        self.assertIn("t_initial", str(errors))

    def test_valid_dt_max(self):
        """验证有效的 dt_max 应返回空列表。"""
        errors = validate_time_params({"t_end": 10.0, "dt_max": 0.1})
        self.assertEqual(len(errors), 0)

    def test_negative_dt_max(self):
        """验证非正 dt_max 应返回错误。"""
        errors = validate_time_params({"t_end": 10.0, "dt_max": -0.1})
        self.assertIn("dt_max", str(errors))


class TestValidateInitialConditions(unittest.TestCase):
    """validate_initial_conditions 函数测试。"""

    def test_empty_ic(self):
        """验证空初始条件应返回错误。"""
        errors = validate_initial_conditions({})
        self.assertGreater(len(errors), 0)
        self.assertIn("不能为空", str(errors))

    def test_valid_noise(self):
        """验证 noise 类型应返回空列表。"""
        errors = validate_initial_conditions({"type": "noise", "amplitude": 1.0})
        self.assertEqual(len(errors), 0)

    def test_valid_dipole(self):
        """验证 dipole 类型应返回空列表。"""
        errors = validate_initial_conditions({"type": "dipole"})
        self.assertEqual(len(errors), 0)

    def test_valid_vortex(self):
        """验证 vortex 类型应返回空列表。"""
        errors = validate_initial_conditions({"type": "vortex"})
        self.assertEqual(len(errors), 0)

    def test_valid_from_file(self):
        """验证 from_file 类型需提供 file_path。"""
        errors = validate_initial_conditions({"type": "from_file", "file_path": "/path/to/state.h5"})
        self.assertEqual(len(errors), 0)

    def test_from_file_missing_path(self):
        """验证 from_file 缺少 file_path 应返回错误。"""
        errors = validate_initial_conditions({"type": "from_file"})
        self.assertGreater(len(errors), 0)
        self.assertIn("file_path", str(errors))

    def test_invalid_ic_type(self):
        """验证不支持的类型应返回错误。"""
        errors = validate_initial_conditions({"type": "invalid_type"})
        self.assertIn("不支持", str(errors))

    def test_negative_amplitude(self):
        """验证负振幅应返回错误。"""
        errors = validate_initial_conditions({"type": "noise", "amplitude": -1})
        self.assertIn("amplitude", str(errors))

    def test_invalid_nk_max(self):
        """验证非正 nk_max 应返回错误。"""
        errors = validate_initial_conditions({"type": "noise", "nk_max": 0})
        self.assertIn("nk_max", str(errors))


class TestValidateForcingParams(unittest.TestCase):
    """validate_forcing_params 函数测试。"""

    def test_none_forcing(self):
        """验证 None 强制力应返回空列表。"""
        self.assertEqual(len(validate_forcing_params(None)), 0)

    def test_valid_kolmogorov(self):
        """验证有效的 Kolmogorov 强制应返回空列表。"""
        errors = validate_forcing_params({"type": "kolmogorov", "kf": 4, "epsilon": 0.1})
        self.assertEqual(len(errors), 0)

    def test_kolmogorov_missing_kf(self):
        """验证 Kolmogorov 缺少 kf 应返回错误。"""
        errors = validate_forcing_params({"type": "kolmogorov"})
        self.assertIn("kf", str(errors))

    def test_invalid_forcing_type(self):
        """验证无效强制力类型应返回错误。"""
        errors = validate_forcing_params({"type": "invalid"})
        self.assertIn("不支持", str(errors))

    def test_non_dict_forcing(self):
        """验证非字典 forcing 应返回错误。"""
        errors = validate_forcing_params("not_a_dict")
        self.assertIn("必须为字典", str(errors))

    def test_valid_random(self):
        """验证 random 类型应返回空列表。"""
        errors = validate_forcing_params({"type": "random"})
        self.assertEqual(len(errors), 0)

    def test_valid_linear(self):
        """验证 linear 类型应返回空列表。"""
        errors = validate_forcing_params({"type": "linear"})
        self.assertEqual(len(errors), 0)


class TestValidateStratifiedParams(unittest.TestCase):
    """validate_stratified_params 函数测试。"""

    def test_ns2d_no_strat_check(self):
        """验证非分层求解器不应检查分层参数。"""
        errors = validate_stratified_params("ns2d", {})
        self.assertEqual(len(errors), 0)

    def test_strat_valid_N(self):
        """验证分层流有效 N 应返回空列表。"""
        errors = validate_stratified_params("ns2d_strat", {"N": 1.0})
        self.assertEqual(len(errors), 0)

    def test_strat_negative_N(self):
        """验证负 N 应返回错误。"""
        errors = validate_stratified_params("ns2d_strat", {"N": -1})
        self.assertIn("N", str(errors))

    def test_sw1l_valid_H(self):
        """验证 SW1L 有效 H 应返回空列表。"""
        errors = validate_stratified_params("sw1l", {"H": 1.0, "f": 0.5})
        self.assertEqual(len(errors), 0)

    def test_sw1l_negative_H(self):
        """验证 SW1L 负 H 应返回错误。"""
        errors = validate_stratified_params("sw1l", {"H": -1})
        self.assertIn("H", str(errors))

    def test_sw1l_valid_f(self):
        """验证 SW1L 有效 f 应返回空列表。"""
        errors = validate_stratified_params("sw1l", {"f": 0.5})
        self.assertEqual(len(errors), 0)

    def test_sw1l_valid_beta(self):
        """验证 SW1L 有效 beta 应返回空列表。"""
        errors = validate_stratified_params("sw1l", {"beta": 0.1})
        self.assertEqual(len(errors), 0)


class TestValidateOutputConfig(unittest.TestCase):
    """validate_output_config 函数测试。"""

    def test_none_output(self):
        """验证 None 输出配置应返回空列表。"""
        self.assertEqual(len(validate_output_config(None)), 0)

    def test_valid_output(self):
        """验证有效输出配置应返回空列表。"""
        errors = validate_output_config({"periods_save": 1.0, "save_spectra": True})
        self.assertEqual(len(errors), 0)

    def test_negative_periods_save(self):
        """验证负 periods_save 应返回错误。"""
        errors = validate_output_config({"periods_save": -1})
        self.assertIn("periods_save", str(errors))

    def test_non_bool_save_spectra(self):
        """验证非布尔 save_spectra 应返回错误。"""
        errors = validate_output_config({"save_spectra": "yes"})
        self.assertIn("save_spectra", str(errors))


# =============================================================================
# Pydantic 命令模型
# =============================================================================


class TestRunSimulationModel(unittest.TestCase):
    """RunSimulation Pydantic 模型测试。"""

    def test_model_creation(self):
        """验证模型创建应正确设置字段值。"""
        cmd = RunSimulation(
            project_id="proj-001",
            solver="ns2d",
            params={"grid": {"nx": 64, "ny": 64, "Lx": 6.28, "Ly": 6.28}},
            initial_conditions={"type": "noise"},
        )
        self.assertEqual(cmd.project_id, "proj-001")
        self.assertEqual(cmd.solver, "ns2d")
        self.assertIsNone(cmd.forcing)
        self.assertIsNone(cmd.output_config)

    def test_model_with_forcing(self):
        """验证模型含强制力参数。"""
        cmd = RunSimulation(
            project_id="proj-001",
            solver="ns2d",
            params={"grid": {"nx": 64, "ny": 64, "Lx": 6.28, "Ly": 6.28}},
            initial_conditions={"type": "noise"},
            forcing={"type": "kolmogorov", "kf": 4},
        )
        self.assertEqual(cmd.forcing["type"], "kolmogorov")

    def test_model_defaults(self):
        """验证默认值。"""
        cmd = RunSimulation(
            project_id="proj-001",
            solver="ns2d",
            params={"grid": {"nx": 64, "ny": 64, "Lx": 6.28, "Ly": 6.28}},
            initial_conditions={"type": "noise"},
        )
        self.assertIsNone(cmd.forcing)
        self.assertIsNone(cmd.output_config)


class TestResumeSimulationModel(unittest.TestCase):
    """ResumeSimulation Pydantic 模型测试。"""

    def test_model_creation(self):
        """验证模型创建。"""
        cmd = ResumeSimulation(
            project_id="proj-001",
            sim_dir="./sim_results",
            extend_time=5.0,
        )
        self.assertEqual(cmd.project_id, "proj-001")
        self.assertEqual(cmd.sim_dir, "./sim_results")
        self.assertEqual(cmd.extend_time, 5.0)

    def test_extend_time_positive(self):
        """验证 extend_time 必须为正数。"""
        with self.assertRaises(ValueError):
            ResumeSimulation(
                project_id="proj-001",
                sim_dir="./sim_results",
                extend_time=0,
            )


class TestAnalyzeSimulationModel(unittest.TestCase):
    """AnalyzeSimulation Pydantic 模型测试。"""

    def test_model_creation(self):
        """验证模型创建和默认字段。"""
        cmd = AnalyzeSimulation(
            project_id="proj-001",
            sim_dir="./sim_results",
        )
        self.assertEqual(cmd.project_id, "proj-001")
        self.assertEqual(cmd.fields, ["vorticity", "velocity"])
        self.assertTrue(cmd.compute_spectra)


class TestParameterSweepModel(unittest.TestCase):
    """ParameterSweep Pydantic 模型测试。"""

    def test_model_creation(self):
        """验证模型创建。"""
        cmd = ParameterSweep(
            project_id="proj-001",
            base_config={"solver": "ns2d", "params": {"grid": {"nx": 64, "ny": 64}}},
            sweep_params={"params.grid.nx": [32, 64, 128]},
            workers=2,
        )
        self.assertEqual(cmd.project_id, "proj-001")
        self.assertEqual(cmd.workers, 2)
        self.assertEqual(len(cmd.sweep_params), 1)

    def test_workers_range(self):
        """验证 workers 范围约束。"""
        with self.assertRaises(ValueError):
            ParameterSweep(
                project_id="proj-001",
                base_config={},
                sweep_params={},
                workers=0,
            )
        with self.assertRaises(ValueError):
            ParameterSweep(
                project_id="proj-001",
                base_config={},
                sweep_params={},
                workers=100,
            )


# =============================================================================
# 能力属性
# =============================================================================


class TestFluidSimulationApplicationCapability(unittest.TestCase):
    """FluidSimulationApplication 能力标识测试。"""

    def setUp(self):
        self.app = FluidSimulationApplication(kernel=MagicMock())

    def test_capability_id(self):
        """验证 capability_id 应为 'fluid_simulation'。"""
        self.assertEqual(self.app.capability_id, "fluid_simulation")

    def test_display_name(self):
        """验证 display_name 应为中文名称。"""
        self.assertEqual(self.app.display_name, "流体动力学模拟")

    def test_description(self):
        """验证 description 应包含服务描述。"""
        self.assertIn("FluidSim", self.app.description)
        self.assertIn("CFD", self.app.description)
        self.assertIn("NS2D", self.app.description)


# =============================================================================
# Validate 方法
# =============================================================================


class TestFluidSimulationApplicationValidate(unittest.TestCase):
    """FluidSimulationApplication.validate 方法测试。"""

    def setUp(self):
        self.app = FluidSimulationApplication(kernel=MagicMock())

    def test_validate_valid_input(self):
        """验证有效输入应返回无错误结果。"""
        task = Task(
            project_id="proj-001",
            capability_id="fluid_simulation",
            title="test",
            metadata={
                "solver": "ns2d",
                "params": {
                    "grid": {"nx": 64, "ny": 64, "Lx": 6.2832, "Ly": 6.2832},
                    "physical": {"nu_2": 1e-4},
                    "time": {"t_end": 10.0, "cfl_coef": 0.5},
                },
                "initial_conditions": {"type": "noise", "amplitude": 1.0},
            },
        )
        result = self.app.validate(task, {})
        self.assertTrue(result["validated"])

    def test_validate_invalid_solver(self):
        """验证无效求解器应返回错误。"""
        task = Task(
            project_id="proj-001",
            capability_id="fluid_simulation",
            title="test",
            metadata={
                "solver": "invalid",
                "params": {
                    "grid": {"nx": 64, "ny": 64, "Lx": 6.28, "Ly": 6.28},
                    "time": {"t_end": 10.0},
                },
                "initial_conditions": {"type": "noise"},
            },
        )
        result = self.app.validate(task, {})
        self.assertFalse(result["validated"])
        self.assertIn("errors", result)

    def test_validate_empty_metadata(self):
        """验证空元数据应返回错误。"""
        task = Task(
            project_id="proj-001",
            capability_id="fluid_simulation",
            title="test",
            metadata={},
        )
        result = self.app.validate(task, {})
        self.assertFalse(result["validated"])
        self.assertGreater(len(result["errors"]), 0)


# =============================================================================
# Prepare 方法
# =============================================================================


class TestFluidSimulationApplicationPrepare(unittest.TestCase):
    """FluidSimulationApplication.prepare 方法测试。"""

    def setUp(self):
        self.app = FluidSimulationApplication(kernel=MagicMock())

    def test_prepare_creates_run(self):
        """验证 prepare 应创建正确的 Run 实例。"""
        task = Task(
            task_id="task-001",
            project_id="proj-001",
            capability_id="fluid_simulation",
            title="test",
            metadata={
                "solver": "ns2d",
                "params": {"grid": {"nx": 64, "ny": 64, "Lx": 6.28, "Ly": 6.28}},
                "initial_conditions": {"type": "noise"},
            },
        )
        run = self.app.prepare(task)
        self.assertIsInstance(run, Run)
        self.assertEqual(run.task_id, "task-001")
        self.assertEqual(run.service_id, "fluid_simulation")
        self.assertIn("fluid_simulation", run.command)
        self.assertIn("solver", run.input)
        self.assertEqual(run.input["solver"], "ns2d")


# =============================================================================
# Execute 方法
# =============================================================================


class TestFluidSimulationApplicationExecute(unittest.TestCase):
    """FluidSimulationApplication.execute 方法测试。"""

    def setUp(self):
        self.app = FluidSimulationApplication(kernel=MagicMock())

    def test_execute_ns2d_returns_artifact(self):
        """验证 execute ns2d 应返回 Artifact 列表。"""
        run = Run(
            task_id="task-001",
            project_id="proj-001",
            service_id="fluid_simulation",
            command="fluid_simulation ns2d",
            input={
                "solver": "ns2d",
                "params": {
                    "grid": {"nx": 64, "ny": 64, "Lx": 6.2832, "Ly": 6.2832},
                    "physical": {"nu_2": 1e-4},
                    "time": {"t_end": 10.0, "cfl_coef": 0.5},
                },
                "initial_conditions": {"type": "noise", "amplitude": 1.0},
            },
        )
        artifacts = self.app.execute(run, {})
        self.assertIsInstance(artifacts, list)
        self.assertGreater(len(artifacts), 0)
        self.assertIsInstance(artifacts[0], Artifact)
        self.assertEqual(artifacts[0].type, ArtifactType.RESULT_TABLE)

    def test_execute_unknown_solver(self):
        """验证未知求解器仍返回结果（含错误标记）。"""
        run = Run(
            task_id="task-001",
            project_id="proj-001",
            service_id="fluid_simulation",
            command="fluid_simulation unknown",
            input={
                "solver": "unknown",
                "params": {},
                "initial_conditions": {},
            },
        )
        artifacts = self.app.execute(run, {})
        self.assertIsInstance(artifacts, list)
        self.assertEqual(artifacts[0].type, ArtifactType.RESULT_TABLE)

    def test_execute_ns3d_with_nz(self):
        """验证 ns3d 含 nz 参数应返回三维网格信息。"""
        run = Run(
            task_id="task-001",
            project_id="proj-001",
            service_id="fluid_simulation",
            command="fluid_simulation ns3d",
            input={
                "solver": "ns3d",
                "params": {
                    "grid": {"nx": 64, "ny": 64, "nz": 32, "Lx": 6.28, "Ly": 6.28, "Lz": 3.14},
                    "physical": {"nu_2": 1e-4},
                    "time": {"t_end": 10.0},
                },
                "initial_conditions": {"type": "noise"},
            },
        )
        artifacts = self.app.execute(run, {})
        data = artifacts[0].data or {}
        results = data.get("results", [])
        names = [r["name"] for r in results]
        self.assertIn("网格尺寸", names)
        grid_info = next(r["value"] for r in results if r["name"] == "网格尺寸")
        self.assertIn("32", str(grid_info))


# =============================================================================
# Postprocess 方法
# =============================================================================


class TestFluidSimulationApplicationPostprocess(unittest.TestCase):
    """FluidSimulationApplication.postprocess 方法测试。"""

    def setUp(self):
        self.app = FluidSimulationApplication(kernel=MagicMock())

    def test_postprocess_returns_evidence_packages(self):
        """验证 postprocess 应返回 EvidencePackage 列表。"""
        run = Run(
            run_id="run-001",
            task_id="task-001",
            project_id="proj-001",
            service_id="fluid_simulation",
            command="fluid_simulation ns2d",
        )
        artifacts = [
            Artifact(
                run_id="run-001",
                type=ArtifactType.RESULT_TABLE,
                name="fluid_simulation_ns2d",
                data={
                    "solver": "ns2d",
                    "results": [
                        {"name": "求解器", "value": "ns2d", "unit": "", "source": "fluidsim", "confidence": 1.0, "method": "配置"},
                        {"name": "总步数", "value": 10000, "unit": "", "source": "fluidsim.simulation", "confidence": 0.9, "method": "运行时统计"},
                    ],
                },
            )
        ]
        evidence = self.app.postprocess(run, artifacts)
        self.assertIsInstance(evidence, list)
        self.assertGreater(len(evidence), 0)
        self.assertIsInstance(evidence[0], EvidencePackage)

    def test_postprocess_empty_results(self):
        """验证无结果时应返回空列表。"""
        run = Run(
            run_id="run-001",
            task_id="task-001",
            project_id="proj-001",
            service_id="fluid_simulation",
            command="fluid_simulation ns2d",
        )
        evidence = self.app.postprocess(run, [])
        self.assertEqual(len(evidence), 0)

    def test_postprocess_empty_artifact_data(self):
        """验证工件 data 为 None 时应跳过。"""
        run = Run(
            run_id="run-001",
            task_id="task-001",
            project_id="proj-001",
            service_id="fluid_simulation",
            command="fluid_simulation ns2d",
        )
        artifacts = [
            Artifact(
                run_id="run-001",
                type=ArtifactType.RESULT_TABLE,
                name="empty",
                data=None,
            )
        ]
        evidence = self.app.postprocess(run, artifacts)
        self.assertEqual(len(evidence), 0)


# =============================================================================
# RunFullCycle
# =============================================================================


class TestFluidSimulationApplicationRunFullCycle(unittest.TestCase):
    """FluidSimulationApplication.run_full_cycle 完整生命周期测试。"""

    def test_run_full_cycle_success(self):
        """验证完整生命周期应返回 EvidencePackage 列表。"""
        mock_kernel = MagicMock()
        captured_run = {}

        def fake_submit_run(run):
            captured_run["run"] = run
            return run

        def fake_update_status(rid, status):
            r = captured_run.get("run") or MagicMock(run_id=rid)
            return r

        mock_kernel.submit_run.side_effect = fake_submit_run
        mock_kernel.update_run_status.side_effect = fake_update_status

        app = FluidSimulationApplication(kernel=mock_kernel)
        task = Task(
            project_id="proj-001",
            capability_id="fluid_simulation",
            title="test",
            metadata={
                "solver": "ns2d",
                "params": {
                    "grid": {"nx": 64, "ny": 64, "Lx": 6.2832, "Ly": 6.2832},
                    "physical": {"nu_2": 1e-4},
                    "time": {"t_end": 10.0, "cfl_coef": 0.5},
                },
                "initial_conditions": {"type": "noise", "amplitude": 1.0},
            },
        )
        evidence = app.run_full_cycle(task)
        self.assertIsInstance(evidence, list)
        mock_kernel.submit_run.assert_called_once()
        mock_kernel.store_artifact.assert_called()
        mock_kernel.store_evidence.assert_called()

    def test_run_full_cycle_validation_failure(self):
        """验证校验失败时应抛出 ValueError。"""
        mock_kernel = MagicMock()
        app = FluidSimulationApplication(kernel=mock_kernel)
        task = Task(
            project_id="proj-001",
            capability_id="fluid_simulation",
            title="test",
            metadata={
                "solver": "invalid",
                "params": {},
                "initial_conditions": {},
            },
        )
        with self.assertRaises(ValueError):
            app.run_full_cycle(task)


# =============================================================================
# 证据映射器
# =============================================================================


class TestFluidEvidenceMapper(unittest.TestCase):
    """evidence_mapper 函数测试。"""

    def test_map_fluid_evidence_high_confidence(self):
        """验证高置信度应映射为 HIGH 级别。"""
        package = map_fluid_evidence(
            run_id="run-001",
            task_id="task-001",
            name="总步数",
            value=10000,
            unit="",
            source="fluidsim.simulation",
            confidence=1.0,
            method="运行时统计",
            category="run_stats",
        )
        self.assertEqual(package.level, EvidenceLevel.HIGH)
        self.assertEqual(package.source_service, "real_engine:fluid_simulation")

    def test_map_fluid_evidence_medium_confidence(self):
        """验证中等置信度应映射为 MEDIUM 级别。"""
        package = map_fluid_evidence(
            run_id="run-001",
            task_id="task-001",
            name="能谱斜率",
            value=-1.67,
            confidence=0.80,
            method="能谱分析",
        )
        self.assertEqual(package.level, EvidenceLevel.MEDIUM)

    def test_map_fluid_evidence_low_confidence(self):
        """验证低置信度应映射为 LOW 级别。"""
        package = map_fluid_evidence(
            run_id="run-001",
            task_id="task-001",
            name="近似值",
            value=0.5,
            confidence=0.50,
        )
        self.assertEqual(package.level, EvidenceLevel.LOW)

    def test_map_fluid_evidence_with_extra_metadata(self):
        """验证额外元数据应被包含在证据包中。"""
        package = map_fluid_evidence(
            run_id="run-001",
            task_id="task-001",
            name="1D 能谱",
            value={"k": [1, 2, 3], "E(k)": [1.0, 0.5, 0.25]},
            confidence=0.85,
            method="1D 傅里叶能谱",
            category="spectra",
            extra_metadata={"spectrum_type": "1d", "k_min": 1, "k_max": 64},
        )
        self.assertIn("spectrum_type", package.metadata)
        self.assertEqual(package.metadata["k_min"], 1)

    def test_batch_map_fluid_evidence(self):
        """验证批量映射应返回正确数量的证据包。"""
        results = [
            {"name": "求解器", "value": "ns2d", "unit": "", "source": "fluidsim", "confidence": 1.0, "method": "配置"},
            {"name": "总步数", "value": 10000, "unit": "", "source": "fluidsim.simulation", "confidence": 0.9, "method": "运行时统计"},
        ]
        packages = batch_map_fluid_evidence(
            run_id="run-001",
            task_id="task-001",
            results=results,
            category="ns2d",
        )
        self.assertEqual(len(packages), 2)
        self.assertIsInstance(packages[0], EvidencePackage)

    def test_batch_map_fluid_evidence_empty(self):
        """验证空结果列表应返回空列表。"""
        packages = batch_map_fluid_evidence(
            run_id="run-001",
            task_id="task-001",
            results=[],
        )
        self.assertEqual(len(packages), 0)

    def test_map_run_statistics(self):
        """验证运行统计映射。"""
        stats = {"n_steps": 10000, "dt": 0.001, "cfl": 0.5, "walltime": 120.0, "t_end": 10.0}
        packages = map_run_statistics("run-001", "task-001", stats)
        self.assertGreater(len(packages), 0)
        names = [p.metadata["result_name"] for p in packages]
        self.assertIn("总步数", names)
        self.assertIn("CFL 数", names)

    def test_map_field_analysis(self):
        """验证物理场分析映射。"""
        field_data = {
            "max_vorticity": 5.2, "min_vorticity": -3.1, "mean_vorticity": 0.1,
            "total_kinetic_energy": 12.5, "enstrophy": 8.3,
            "max_velocity": 2.5, "mean_velocity": 0.8,
        }
        packages = map_field_analysis("run-001", "task-001", field_data)
        self.assertGreater(len(packages), 0)
        names = [p.metadata["result_name"] for p in packages]
        self.assertIn("最大涡量", names)
        self.assertIn("总动能", names)

    def test_map_spectra_analysis(self):
        """验证能谱分析映射。"""
        spectra_data = {
            "slope": -1.67,
            "k_min": 1, "k_max": 64,
            "spectrum_1d": {"k": [1, 2, 3], "E(k)": [1.0, 0.5, 0.25]},
        }
        packages = map_spectra_analysis("run-001", "task-001", spectra_data)
        self.assertGreater(len(packages), 0)
        names = [p.metadata["result_name"] for p in packages]
        self.assertIn("能谱斜率", names)
        self.assertIn("1D 能谱", names)

    def test_map_convergence_analysis(self):
        """验证收敛分析映射。"""
        convergence_data = {
            "is_steady": True,
            "convergence_time": 5.0,
            "energy_derivative": 1e-6,
            "enstrophy_derivative": 1e-5,
        }
        packages = map_convergence_analysis("run-001", "task-001", convergence_data)
        self.assertGreater(len(packages), 0)
        names = [p.metadata["result_name"] for p in packages]
        self.assertIn("是否达到稳态", names)
        self.assertIn("收敛时间", names)


# =============================================================================
# 求解器目录
# =============================================================================


class TestSolverCatalog(unittest.TestCase):
    """SOLVER_CATALOG 完整性测试。"""

    def test_catalog_has_5_solvers(self):
        """验证求解器目录应包含 5 个求解器。"""
        self.assertEqual(len(SOLVER_CATALOG), 5)

    def test_solver_keys_match_valid_solvers(self):
        """验证 SOLVER_CATALOG 的键与 VALID_SOLVERS 一致。"""
        self.assertEqual(set(SOLVER_CATALOG.keys()), VALID_SOLVERS)

    def test_each_solver_has_required_fields(self):
        """验证每个求解器都包含 name, description, dimensions。"""
        for key, meta in SOLVER_CATALOG.items():
            with self.subTest(key=key):
                self.assertIn("name", meta)
                self.assertIn("description", meta)
                self.assertIn("dimensions", meta)

    def test_solver_names_match(self):
        """验证 SOLVER_CATALOG 的 name 与 SOLVER_NAMES 一致。"""
        for key, catalog_entry in SOLVER_CATALOG.items():
            self.assertEqual(catalog_entry["name"], SOLVER_NAMES[key].split(" (")[0])


# =============================================================================
# 适配器
# =============================================================================


class TestFluidAdapter(unittest.TestCase):
    """FluidSimAdapter 功能测试（占位模式）。"""

    def setUp(self):
        self.adapter = FluidSimAdapter()

    def test_execute_placeholder_ns2d(self):
        """验证占位模式 ns2d 执行应返回结果。"""
        result = self.adapter.execute({
            "solver": "ns2d",
            "params": {
                "grid": {"nx": 64, "ny": 64, "Lx": 6.28, "Ly": 6.28},
                "physical": {"nu_2": 1e-4},
                "time": {"t_end": 10.0, "cfl_coef": 0.5},
            },
            "initial_conditions": {"type": "noise"},
        })
        self.assertEqual(result["status"], "completed")
        self.assertIn("results", result)
        self.assertIn("warnings", result)

    def test_execute_unsupported_solver(self):
        """验证不支持的求解器应返回错误。"""
        result = self.adapter.execute({
            "solver": "invalid",
            "params": {},
            "initial_conditions": {},
        })
        self.assertIn("error", result)

    def test_parse_output(self):
        """验证 parse_output 应返回原始 dict。"""
        raw = {"status": "completed", "results": []}
        self.assertEqual(self.adapter.parse_output(raw), raw)

    def test_parse_output_non_dict(self):
        """验证非 dict 输入应返回兜底结果。"""
        result = self.adapter.parse_output("not_a_dict")
        self.assertEqual(result["status"], "unknown")

    def test_get_resource_requirements_2d(self):
        """验证 2D 资源需求估算。"""
        req = self.adapter.get_resource_requirements({
            "solver": "ns2d",
            "params": {"grid": {"nx": 128, "ny": 128}},
        })
        self.assertIn("cpu", req)
        self.assertIn("memory_mb", req)
        self.assertIn("walltime_minutes", req)

    def test_get_resource_requirements_3d(self):
        """验证 3D 资源需求应高于 2D。"""
        req_2d = self.adapter.get_resource_requirements({
            "solver": "ns2d",
            "params": {"grid": {"nx": 128, "ny": 128}},
        })
        req_3d = self.adapter.get_resource_requirements({
            "solver": "ns3d",
            "params": {"grid": {"nx": 128, "ny": 128, "nz": 64}},
        })
        self.assertGreaterEqual(req_3d["memory_mb"], req_2d["memory_mb"])

    def test_resume_simulation_placeholder(self):
        """验证占位模式续跑应返回结果。"""
        result = self.adapter.resume_simulation("./sim_dir", 5.0)
        self.assertEqual(result["status"], "placeholder")
        self.assertIn("warnings", result)

    def test_run_parameter_sweep_placeholder(self):
        """验证占位模式参数扫描应返回结果。"""
        result = self.adapter.run_parameter_sweep(
            base_config={"solver": "ns2d"},
            sweep_params={"params.grid.nx": [32, 64]},
            workers=1,
        )
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["n_combinations"], 2)

    def test_set_nested_param(self):
        """验证 _set_nested_param 应正确设置嵌套参数。"""
        config = {"params": {"grid": {"nx": 64}}}
        FluidSimAdapter._set_nested_param(config, "params.grid.nx", 128)
        self.assertEqual(config["params"]["grid"]["nx"], 128)

    def test_placeholder_adapter(self):
        """验证 _PlaceholderAdapter 后备行为。"""
        adapter = _PlaceholderAdapter()
        result = adapter.execute({"solver": "ns2d"})
        self.assertEqual(result["status"], "placeholder")
        self.assertIn("results", result)

        parsed = adapter.parse_output({"a": 1})
        self.assertEqual(parsed["a"], 1)

        req = adapter.get_resource_requirements({})
        self.assertEqual(req["cpu"], 1)


# =============================================================================
# 外部 API 入口
# =============================================================================


class TestFluidExternalAPI(unittest.TestCase):
    """测试通过 API 路由对外暴露的入口。"""

    def test_solvers_list(self):
        """验证求解器列表 API 应返回 5 个求解器。"""
        from battery_materials_agent.scientific_routes.fluid_simulation_routes import list_solvers
        response = list_solvers()
        self.assertEqual(response["count"], 5)
        self.assertEqual(len(response["solvers"]), 5)

    def test_solver_keys_in_list(self):
        """验证每个求解器都有 key, name, description, dimensions。"""
        from battery_materials_agent.scientific_routes.fluid_simulation_routes import list_solvers
        response = list_solvers()
        for solver in response["solvers"]:
            self.assertIn("key", solver)
            self.assertIn("name", solver)
            self.assertIn("description", solver)
            self.assertIn("dimensions", solver)

    def test_run_simulation_via_route(self):
        """验证 run_simulation 路由应返回 Artifact 列表。"""
        from battery_materials_agent.scientific_routes.fluid_simulation_routes import run_simulation
        from battery_materials_agent.scientific_routes.fluid_simulation_routes import RunFluidSimRequest

        req = RunFluidSimRequest(
            project_id="proj-001",
            solver="ns2d",
            params={
                "grid": {"nx": 64, "ny": 64, "Lx": 6.2832, "Ly": 6.2832},
                "physical": {"nu_2": 1e-4},
                "time": {"t_end": 10.0, "cfl_coef": 0.5},
            },
            initial_conditions={"type": "noise", "amplitude": 1.0},
        )
        artifacts = run_simulation(req)
        self.assertIsInstance(artifacts, list)
        self.assertGreater(len(artifacts), 0)
        self.assertIsInstance(artifacts[0], Artifact)

    def test_run_simulation_full_via_route(self):
        """验证 run_simulation/full 路由应返回 EvidencePackage 列表。"""
        from battery_materials_agent.scientific_routes.fluid_simulation_routes import run_simulation_full
        from battery_materials_agent.scientific_routes.fluid_simulation_routes import RunFluidSimFullRequest

        req = RunFluidSimFullRequest(
            project_id="proj-001",
            solver="ns2d",
            params={
                "grid": {"nx": 64, "ny": 64, "Lx": 6.2832, "Ly": 6.2832},
                "physical": {"nu_2": 1e-4},
                "time": {"t_end": 10.0, "cfl_coef": 0.5},
            },
            initial_conditions={"type": "noise", "amplitude": 1.0},
            title="测试流体模拟",
        )
        evidence = run_simulation_full(req)
        self.assertIsInstance(evidence, list)
        self.assertGreater(len(evidence), 0)
        self.assertIsInstance(evidence[0], EvidencePackage)

    def test_resume_simulation_via_route(self):
        """验证 resume 路由应返回结果。"""
        from battery_materials_agent.scientific_routes.fluid_simulation_routes import resume_simulation
        from battery_materials_agent.scientific_routes.fluid_simulation_routes import ResumeFluidSimRequest

        req = ResumeFluidSimRequest(
            project_id="proj-001",
            sim_dir="./sim_results",
            extend_time=5.0,
        )
        result = resume_simulation(req)
        self.assertIn("status", result)

    def test_analyze_simulation_via_route(self):
        """验证 analyze 路由应返回结果。"""
        from battery_materials_agent.scientific_routes.fluid_simulation_routes import analyze_simulation
        from battery_materials_agent.scientific_routes.fluid_simulation_routes import AnalyzeFluidSimRequest

        req = AnalyzeFluidSimRequest(
            project_id="proj-001",
            sim_dir="./sim_results",
        )
        result = analyze_simulation(req)
        self.assertEqual(result["project_id"], "proj-001")
        self.assertIn("status", result)

    def test_parameter_sweep_via_route(self):
        """验证 sweep 路由应返回结果。"""
        from battery_materials_agent.scientific_routes.fluid_simulation_routes import parameter_sweep
        from battery_materials_agent.scientific_routes.fluid_simulation_routes import SweepFluidSimRequest

        req = SweepFluidSimRequest(
            project_id="proj-001",
            base_config={"solver": "ns2d"},
            sweep_params={"params.grid.nx": [32, 64]},
            workers=1,
        )
        result = parameter_sweep(req)
        self.assertIn("status", result)


if __name__ == "__main__":
    unittest.main()