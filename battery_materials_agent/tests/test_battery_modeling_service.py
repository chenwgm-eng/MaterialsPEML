"""电池建模与仿真服务单元测试 — BatteryModelingService 完整生命周期验证。"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from battery_materials_agent.contracts.task import Task
from battery_materials_agent.contracts.run import Run
from battery_materials_agent.contracts.artifact import Artifact, ArtifactType
from battery_materials_agent.contracts.evidence import EvidencePackage, EvidenceLevel
from battery_materials_agent.services.battery_modeling.application import (
    BatteryModelingApplication,
    RunBatterySimulation,
)
from battery_materials_agent.services.battery_modeling.validators import (
    BatteryModelingValidator,
    validate_track, validate_model_type, validate_parameter_set,
    validate_experiment_protocol, validate_thermal_option, validate_requested_variables,
    VALID_TRACKS, VALID_MODEL_TYPES, VALID_PARAMETER_SETS, VALID_THERMAL_OPTIONS,
)
from battery_materials_agent.services.battery_modeling.evidence_mapper import (
    map_simulation_evidence, batch_map_evidence,
)
from battery_materials_agent.infrastructure.executors.battery_adapter import BatteryAdapter


# ============================================================================
# BatteryModelingValidator 类测试
# ============================================================================

class TestBatteryModelingValidator(unittest.TestCase):
    """BatteryModelingValidator 完整校验逻辑测试。"""

    def setUp(self):
        self.valid_kwargs = {
            "track": "p2d",
            "model_type": "DFN",
            "parameter_set": "Chen2020",
            "experiment_protocol": [],
            "thermal_option": "isothermal",
            "requested_variables": ["Terminal voltage [V]", "Current [A]"],
        }

    def test_validate_all_valid_input(self):
        """验证有效输入应返回 valid=True 且无错误。"""
        validator = BatteryModelingValidator(**self.valid_kwargs)
        result = validator.validate_all()
        self.assertTrue(result["valid"])
        self.assertEqual(len(result["errors"]), 0)
        self.assertEqual(len(result["warnings"]), 0)

    def test_validate_all_invalid_track(self):
        """验证无效轨道应返回 valid=False 并立即返回。"""
        validator = BatteryModelingValidator(track="invalid_track", model_type="DFN")
        result = validator.validate_all()
        self.assertFalse(result["valid"])
        self.assertIn("无效轨道", result["errors"][0])

    def test_validate_all_invalid_model_type(self):
        """验证轨道不匹配的模型类型应返回错误。"""
        validator = BatteryModelingValidator(track="p2d", model_type="Thevenin")
        result = validator.validate_all()
        self.assertFalse(result["valid"])
        self.assertIn("不支持的模型类型", result["errors"][0])

    def test_validate_all_unknown_parameter_set(self):
        """验证未知参数集应产生警告而不是错误。"""
        validator = BatteryModelingValidator(
            track="p2d", model_type="DFN", parameter_set="UnknownParam"
        )
        result = validator.validate_all()
        self.assertTrue(result["valid"])
        self.assertIn("未知参数集", str(result["warnings"]))

    def test_validate_all_protocol_errors(self):
        """验证实验协议错误应使校验失败。"""
        validator = BatteryModelingValidator(
            track="p2d", model_type="DFN",
            experiment_protocol=[{"type": "invalid_step"}],
        )
        result = validator.validate_all()
        self.assertFalse(result["valid"])
        self.assertIn("无效步骤类型", result["errors"][0])

    def test_validate_all_unknown_thermal_option(self):
        """验证无效热选项应产生警告。"""
        validator = BatteryModelingValidator(
            track="p2d", model_type="DFN", thermal_option="super_hot"
        )
        result = validator.validate_all()
        self.assertTrue(result["valid"])
        self.assertIn("无效热选项", str(result["warnings"]))

    def test_validate_all_unknown_variables(self):
        """验证未知请求变量应产生警告。"""
        validator = BatteryModelingValidator(
            track="p2d", model_type="DFN",
            requested_variables=["Unknown var", "Terminal voltage [V]"],
        )
        result = validator.validate_all()
        self.assertTrue(result["valid"])
        self.assertIn("未知变量", str(result["warnings"]))

    def test_validate_all_multiple_errors(self):
        """验证多个错误时应全部返回。"""
        validator = BatteryModelingValidator(
            track="p2d", model_type="InvalidModel",
            experiment_protocol=[{"type": "bad_step"}],
        )
        result = validator.validate_all()
        self.assertFalse(result["valid"])
        self.assertGreaterEqual(len(result["errors"]), 2)


# ============================================================================
# validate_track 函数测试
# ============================================================================

class TestValidateTrack(unittest.TestCase):
    """validate_track 函数测试。"""

    def test_valid_track_p2d(self):
        """验证 p2d 轨道应返回 None。"""
        self.assertIsNone(validate_track("p2d"))

    def test_valid_track_ecm(self):
        """验证 ecm 轨道应返回 None。"""
        self.assertIsNone(validate_track("ecm"))

    def test_valid_track_pybop(self):
        """验证 pybop 轨道应返回 None。"""
        self.assertIsNone(validate_track("pybop"))

    def test_invalid_track(self):
        """验证无效轨道应返回错误信息。"""
        error = validate_track("unknown_track")
        self.assertIn("无效轨道", error)

    def test_empty_track(self):
        """验证空轨道应返回错误信息。"""
        error = validate_track("")
        self.assertIn("不能为空", error)


# ============================================================================
# validate_model_type 函数测试
# ============================================================================

class TestValidateModelType(unittest.TestCase):
    """validate_model_type 函数测试。"""

    def test_valid_model_type_p2d(self):
        """验证 p2d 轨道支持 DFN/SPM/SPMe。"""
        for mt in ["SPM", "SPMe", "DFN"]:
            with self.subTest(model_type=mt):
                self.assertIsNone(validate_model_type("p2d", mt))

    def test_valid_model_type_ecm(self):
        """验证 ecm 轨道支持 Thevenin/PNGV/RC。"""
        for mt in ["Thevenin", "PNGV", "RC"]:
            with self.subTest(model_type=mt):
                self.assertIsNone(validate_model_type("ecm", mt))

    def test_valid_model_type_pybop(self):
        """验证 pybop 轨道支持 parameter_identification。"""
        self.assertIsNone(validate_model_type("pybop", "parameter_identification"))

    def test_invalid_model_type_for_track(self):
        """验证 p2d 轨道不支持 Thevenin 应返回错误。"""
        error = validate_model_type("p2d", "Thevenin")
        self.assertIn("不支持的模型类型", error)

    def test_empty_model_type(self):
        """验证空模型类型应返回错误。"""
        error = validate_model_type("p2d", "")
        self.assertIn("不能为空", error)

    def test_unknown_track(self):
        """验证未知轨道应返回错误。"""
        error = validate_model_type("unknown", "DFN")
        self.assertIn("不支持", error)


# ============================================================================
# validate_parameter_set 函数测试
# ============================================================================

class TestValidateParameterSet(unittest.TestCase):
    """validate_parameter_set 函数测试。"""

    def test_valid_parameter_set(self):
        """验证已知参数集应返回 None。"""
        for name in VALID_PARAMETER_SETS:
            with self.subTest(parameter_set=name):
                self.assertIsNone(validate_parameter_set(name))

    def test_invalid_parameter_set(self):
        """验证未知参数集应返回错误。"""
        error = validate_parameter_set("UnknownSet")
        self.assertIn("未知参数集", error)

    def test_empty_parameter_set(self):
        """验证空参数集名称应返回错误。"""
        error = validate_parameter_set("")
        self.assertIn("不能为空", error)


# ============================================================================
# validate_experiment_protocol 函数测试
# ============================================================================

class TestValidateExperimentProtocol(unittest.TestCase):
    """validate_experiment_protocol 函数测试。"""

    def test_empty_protocol(self):
        """验证空协议应返回空错误列表（允许默认协议）。"""
        errors = validate_experiment_protocol([])
        self.assertEqual(len(errors), 0)

    def test_valid_step_types(self):
        """验证所有有效步骤类型。"""
        protocol = [
            {"type": "charge", "current": "C/5", "until": "4.2 V"},
            {"type": "discharge", "current": "C/5", "until": "2.5 V"},
            {"type": "rest", "duration": "10 minutes"},
            {"type": "hold", "voltage": "4.2 V", "until": "50 mA"},
            {"type": "cccv_cycle", "cycles": 3},
        ]
        errors = validate_experiment_protocol(protocol)
        self.assertEqual(len(errors), 0)

    def test_invalid_step_type(self):
        """验证无效步骤类型应返回错误。"""
        errors = validate_experiment_protocol([{"type": "unknown_step"}])
        self.assertGreater(len(errors), 0)
        self.assertIn("无效步骤类型", errors[0])

    def test_missing_type_field(self):
        """验证缺少 type 字段应返回错误。"""
        errors = validate_experiment_protocol([{"current": "C/5"}])
        self.assertGreater(len(errors), 0)
        self.assertIn("缺少", errors[0])

    def test_non_dict_step(self):
        """验证非 dict 步骤应返回错误。"""
        errors = validate_experiment_protocol(["not a dict"])
        self.assertGreater(len(errors), 0)
        self.assertIn("dict 类型", errors[0])

    def test_mixed_valid_and_invalid(self):
        """验证混合有效和无效步骤应返回对应错误。"""
        protocol = [
            {"type": "charge", "current": "C/5"},
            {"type": "bad_type"},
        ]
        errors = validate_experiment_protocol(protocol)
        self.assertEqual(len(errors), 1)
        self.assertIn("无效步骤类型", errors[0])


# ============================================================================
# validate_thermal_option 函数测试
# ============================================================================

class TestValidateThermalOption(unittest.TestCase):
    """validate_thermal_option 函数测试。"""

    def test_valid_thermal_options(self):
        """验证所有有效热选项应返回 None。"""
        for opt in VALID_THERMAL_OPTIONS:
            with self.subTest(thermal_option=opt):
                self.assertIsNone(validate_thermal_option(opt))

    def test_invalid_thermal_option(self):
        """验证无效热选项应返回错误。"""
        error = validate_thermal_option("unknown_thermal")
        self.assertIn("无效热选项", error)


# ============================================================================
# validate_requested_variables 函数测试
# ============================================================================

class TestValidateRequestedVariables(unittest.TestCase):
    """validate_requested_variables 函数测试。"""

    def test_all_known_variables(self):
        """验证全部已知变量应返回空列表。"""
        unknown = validate_requested_variables(
            ["Terminal voltage [V]", "Current [A]", "Discharge capacity [A.h]"]
        )
        self.assertEqual(len(unknown), 0)

    def test_mixed_known_and_unknown(self):
        """验证混合已知和未知变量应返回未知列表。"""
        unknown = validate_requested_variables(
            ["Terminal voltage [V]", "UnknownVar", "Current [A]", "AnotherUnknown"]
        )
        self.assertEqual(len(unknown), 2)
        self.assertIn("UnknownVar", unknown)
        self.assertIn("AnotherUnknown", unknown)

    def test_empty_list(self):
        """验证空列表应返回空列表。"""
        unknown = validate_requested_variables([])
        self.assertEqual(len(unknown), 0)


# ============================================================================
# RunBatterySimulation Pydantic 模型测试
# ============================================================================

class TestRunBatterySimulationModel(unittest.TestCase):
    """RunBatterySimulation Pydantic 模型测试。"""

    def test_model_creation(self):
        """验证模型创建应正确设置字段值。"""
        cmd = RunBatterySimulation(
            project_id="proj-001",
            track="p2d",
            model_type="SPMe",
            parameter_set="OKane2022",
            experiment_protocol=[{"type": "cccv_cycle", "cycles": 2}],
            thermal_option="lumped",
            requested_variables=["Terminal voltage [V]", "Current [A]", "Cell temperature [K]"],
        )
        self.assertEqual(cmd.project_id, "proj-001")
        self.assertEqual(cmd.track, "p2d")
        self.assertEqual(cmd.model_type, "SPMe")
        self.assertEqual(cmd.parameter_set, "OKane2022")
        self.assertEqual(len(cmd.experiment_protocol), 1)
        self.assertEqual(cmd.thermal_option, "lumped")
        self.assertEqual(len(cmd.requested_variables), 3)

    def test_default_model_type(self):
        """验证默认 model_type 应为 DFN。"""
        cmd = RunBatterySimulation(project_id="proj-001", track="p2d")
        self.assertEqual(cmd.model_type, "DFN")

    def test_default_parameter_set(self):
        """验证默认 parameter_set 应为 Chen2020。"""
        cmd = RunBatterySimulation(project_id="proj-001", track="p2d")
        self.assertEqual(cmd.parameter_set, "Chen2020")

    def test_default_experiment_protocol(self):
        """验证默认 experiment_protocol 应为空列表。"""
        cmd = RunBatterySimulation(project_id="proj-001", track="p2d")
        self.assertEqual(cmd.experiment_protocol, [])

    def test_default_thermal_option(self):
        """验证默认 thermal_option 应为 isothermal。"""
        cmd = RunBatterySimulation(project_id="proj-001", track="p2d")
        self.assertEqual(cmd.thermal_option, "isothermal")

    def test_default_requested_variables(self):
        """验证默认 requested_variables 应包含端电压和电流。"""
        cmd = RunBatterySimulation(project_id="proj-001", track="p2d")
        self.assertIn("Terminal voltage [V]", cmd.requested_variables)
        self.assertIn("Current [A]", cmd.requested_variables)

    def test_ecm_track_defaults(self):
        """验证 ecm 轨道使用默认值。"""
        cmd = RunBatterySimulation(project_id="proj-001", track="ecm")
        self.assertEqual(cmd.model_type, "DFN")  # 默认值，用户需自行覆盖
        self.assertEqual(cmd.track, "ecm")


# ============================================================================
# BatteryModelingApplication 能力标识测试
# ============================================================================

class TestBatteryModelingApplicationCapability(unittest.TestCase):
    """BatteryModelingApplication 能力标识测试。"""

    def setUp(self):
        self.app = BatteryModelingApplication(kernel=MagicMock())

    def test_capability_id(self):
        """验证 capability_id 应为 'battery_modeling'。"""
        self.assertEqual(self.app.capability_id, "battery_modeling")

    def test_display_name(self):
        """验证 display_name 应为中文名称。"""
        self.assertEqual(self.app.display_name, "电池建模与仿真")

    def test_description(self):
        """验证 description 应包含服务描述。"""
        self.assertIn("PyBaMM", self.app.description)
        self.assertIn("P2D", self.app.description)


# ============================================================================
# BatteryModelingApplication.validate 测试
# ============================================================================

class TestBatteryModelingApplicationValidate(unittest.TestCase):
    """BatteryModelingApplication.validate 方法测试。"""

    def setUp(self):
        self.app = BatteryModelingApplication(kernel=MagicMock())

    def test_validate_valid_input(self):
        """验证有效输入应返回无错误结果。"""
        task = Task(
            project_id="proj-001",
            capability_id="battery_modeling",
            title="test",
            metadata={
                "project_id": "proj-001",
                "track": "p2d",
                "model_type": "DFN",
                "parameter_set": "Chen2020",
                "experiment_protocol": [],
                "thermal_option": "isothermal",
                "requested_variables": ["Terminal voltage [V]", "Current [A]"],
            },
        )
        result = self.app.validate(task, {})
        self.assertTrue(result["valid"])

    def test_validate_invalid_track(self):
        """验证无效轨道应返回错误。"""
        task = Task(
            project_id="proj-001",
            capability_id="battery_modeling",
            title="test",
            metadata={
                "project_id": "proj-001",
                "track": "invalid_track",
                "model_type": "DFN",
            },
        )
        result = self.app.validate(task, {})
        self.assertFalse(result["valid"])

    def test_validate_protocol_errors(self):
        """验证实验协议错误应返回错误。"""
        task = Task(
            project_id="proj-001",
            capability_id="battery_modeling",
            title="test",
            metadata={
                "project_id": "proj-001",
                "track": "p2d",
                "model_type": "DFN",
                "experiment_protocol": [{"type": "invalid_step"}],
            },
        )
        result = self.app.validate(task, {})
        self.assertFalse(result["valid"])


# ============================================================================
# BatteryModelingApplication.prepare 测试
# ============================================================================

class TestBatteryModelingApplicationPrepare(unittest.TestCase):
    """BatteryModelingApplication.prepare 方法测试。"""

    def setUp(self):
        self.app = BatteryModelingApplication(kernel=MagicMock())

    def test_prepare_creates_run(self):
        """验证 prepare 应创建正确的 Run 实例。"""
        task = Task(
            task_id="task-001",
            project_id="proj-001",
            capability_id="battery_modeling",
            title="test",
            metadata={
                "project_id": "proj-001",
                "track": "p2d",
                "model_type": "DFN",
                "parameter_set": "Chen2020",
                "experiment_protocol": [],
                "thermal_option": "isothermal",
                "requested_variables": ["Terminal voltage [V]", "Current [A]"],
            },
        )
        run = self.app.prepare(task)
        self.assertIsInstance(run, Run)
        self.assertEqual(run.task_id, "task-001")
        self.assertEqual(run.service_id, "battery_modeling")
        self.assertEqual(run.command, "run_battery_simulation p2d DFN")
        self.assertIn("track", run.input)
        self.assertEqual(run.input["track"], "p2d")
        self.assertEqual(run.input["model_type"], "DFN")

    def test_prepare_with_ecm_track(self):
        """验证 prepare 在 ecm 轨道下 command 正确。"""
        task = Task(
            task_id="task-002",
            project_id="proj-001",
            capability_id="battery_modeling",
            title="test",
            metadata={
                "project_id": "proj-001",
                "track": "ecm",
                "model_type": "Thevenin",
            },
        )
        run = self.app.prepare(task)
        self.assertEqual(run.command, "run_battery_simulation ecm Thevenin")


# ============================================================================
# BatteryModelingApplication.execute 测试
# ============================================================================

class TestBatteryModelingApplicationExecute(unittest.TestCase):
    """BatteryModelingApplication.execute 方法测试。"""

    def setUp(self):
        self.app = BatteryModelingApplication(kernel=MagicMock())

    def test_execute_returns_artifact_list(self):
        """验证 execute 应返回 Artifact 列表。"""
        run = Run(
            task_id="task-001",
            project_id="proj-001",
            service_id="battery_modeling",
            command="run_battery_simulation p2d DFN",
            input={
                "track": "p2d",
                "model_type": "DFN",
                "parameter_set": "Chen2020",
                "experiment_protocol": [],
                "thermal_option": "isothermal",
                "requested_variables": ["Terminal voltage [V]", "Current [A]"],
            },
        )
        artifacts = self.app.execute(run, {})
        self.assertIsInstance(artifacts, list)
        self.assertGreater(len(artifacts), 0)
        self.assertIsInstance(artifacts[0], Artifact)
        self.assertEqual(artifacts[0].type, ArtifactType.RESULT_TABLE)
        self.assertEqual(artifacts[0].name, "battery_simulation_results")

    def test_execute_contains_track_info(self):
        """验证 execute 返回的 Artifact 包含轨道信息。"""
        run = Run(
            task_id="task-001",
            project_id="proj-001",
            service_id="battery_modeling",
            command="run_battery_simulation p2d DFN",
            input={
                "track": "p2d",
                "model_type": "DFN",
                "parameter_set": "Chen2020",
            },
        )
        artifacts = self.app.execute(run, {})
        self.assertIn("p2d", artifacts[0].description)
        self.assertIn("DFN", artifacts[0].description)

    @patch.object(BatteryAdapter, "execute")
    def test_execute_with_mock_adapter(self, mock_execute):
        """验证 execute 使用 adapter 的输出。"""
        mock_execute.return_value = {
            "track": "p2d",
            "model_type": "DFN",
            "parameter_set": "Chen2020",
            "results": {"Terminal voltage [V]": [4.2, 4.1, 4.0]},
            "summary": {"final_voltage": 4.0},
        }
        app = BatteryModelingApplication(kernel=MagicMock(), adapter=BatteryAdapter())
        run = Run(
            task_id="task-001",
            project_id="proj-001",
            service_id="battery_modeling",
            command="run_battery_simulation p2d DFN",
            input={
                "track": "p2d",
                "model_type": "DFN",
                "parameter_set": "Chen2020",
            },
        )
        artifacts = app.execute(run, {})
        self.assertEqual(len(artifacts), 1)
        self.assertIn("results", artifacts[0].data)
        mock_execute.assert_called_once()


# ============================================================================
# BatteryModelingApplication.postprocess 测试
# ============================================================================

class TestBatteryModelingApplicationPostprocess(unittest.TestCase):
    """BatteryModelingApplication.postprocess 方法测试。"""

    def setUp(self):
        self.app = BatteryModelingApplication(kernel=MagicMock())

    def test_postprocess_returns_evidence_packages(self):
        """验证 postprocess 应返回 EvidencePackage 列表。"""
        run = Run(
            run_id="run-001",
            task_id="task-001",
            project_id="proj-001",
            service_id="battery_modeling",
            command="run_battery_simulation p2d DFN",
        )
        artifacts = [
            Artifact(
                run_id="run-001",
                type=ArtifactType.RESULT_TABLE,
                name="battery_simulation_results",
                data={
                    "track": "p2d",
                    "model_type": "DFN",
                    "parameter_set": "Chen2020",
                    "results": {
                        "Terminal voltage [V]": [4.2, 4.1, 4.0],
                    },
                    "summary": {
                        "final_voltage": 4.0,
                        "total_capacity": 5.0,
                    },
                },
            )
        ]
        evidence = self.app.postprocess(run, artifacts)
        self.assertIsInstance(evidence, list)
        self.assertGreater(len(evidence), 0)
        self.assertIsInstance(evidence[0], EvidencePackage)

    def test_postprocess_empty_artifacts(self):
        """验证无 Artifact 时应返回空列表。"""
        run = Run(
            run_id="run-001",
            task_id="task-001",
            project_id="proj-001",
            service_id="battery_modeling",
            command="run_battery_simulation p2d DFN",
        )
        evidence = self.app.postprocess(run, [])
        self.assertEqual(len(evidence), 0)

    def test_postprocess_artifact_without_data(self):
        """验证 Artifact 无 data 时应返回空列表。"""
        run = Run(
            run_id="run-001",
            task_id="task-001",
            project_id="proj-001",
            service_id="battery_modeling",
            command="run_battery_simulation p2d DFN",
        )
        artifacts = [
            Artifact(
                run_id="run-001",
                type=ArtifactType.LOG,
                name="log",
                data=None,
            )
        ]
        evidence = self.app.postprocess(run, artifacts)
        self.assertEqual(len(evidence), 0)

    def test_postprocess_includes_summary_evidence(self):
        """验证 postprocess 结果包含摘要证据。"""
        run = Run(
            run_id="run-001",
            task_id="task-001",
            project_id="proj-001",
            service_id="battery_modeling",
            command="run_battery_simulation p2d DFN",
        )
        artifacts = [
            Artifact(
                run_id="run-001",
                type=ArtifactType.RESULT_TABLE,
                name="battery_simulation_results",
                data={
                    "track": "p2d",
                    "model_type": "DFN",
                    "parameter_set": "Chen2020",
                    "results": {},
                    "summary": {"final_voltage": 4.0, "total_capacity": 5.0},
                },
            )
        ]
        evidence = self.app.postprocess(run, artifacts)
        # 1 个概要证据 + 2 个摘要统计证据
        self.assertGreaterEqual(len(evidence), 3)


# ============================================================================
# BatteryModelingApplication.run_full_cycle 测试
# ============================================================================

class TestBatteryModelingApplicationRunFullCycle(unittest.TestCase):
    """BatteryModelingApplication.run_full_cycle 完整生命周期测试。"""

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

        app = BatteryModelingApplication(kernel=mock_kernel)
        task = Task(
            project_id="proj-001",
            capability_id="battery_modeling",
            title="test",
            metadata={
                "project_id": "proj-001",
                "track": "p2d",
                "model_type": "DFN",
                "parameter_set": "Chen2020",
                "experiment_protocol": [],
                "thermal_option": "isothermal",
                "requested_variables": ["Terminal voltage [V]", "Current [A]"],
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
        app = BatteryModelingApplication(kernel=mock_kernel)
        task = Task(
            project_id="proj-001",
            capability_id="battery_modeling",
            title="test",
            metadata={
                "project_id": "proj-001",
                "track": "invalid_track",
                "model_type": "DFN",
            },
        )
        with self.assertRaises(ValueError):
            app.run_full_cycle(task)

    def test_run_full_cycle_execution_failure(self):
        """验证执行失败时状态应更新为 FAILED。"""
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

        app = BatteryModelingApplication(kernel=mock_kernel)
        app.execute = MagicMock(side_effect=RuntimeError("Simulation crashed"))

        task = Task(
            project_id="proj-001",
            capability_id="battery_modeling",
            title="test",
            metadata={
                "project_id": "proj-001",
                "track": "p2d",
                "model_type": "DFN",
                "parameter_set": "Chen2020",
            },
        )
        with self.assertRaises(RuntimeError):
            app.run_full_cycle(task)
        mock_kernel.update_run_status.assert_any_call(
            mock_kernel.update_run_status.call_args[0][0], "failed"
        )


# ============================================================================
# BatteryAdapter 测试
# ============================================================================

class TestBatteryAdapter(unittest.TestCase):
    """BatteryAdapter 执行适配器测试。"""

    def setUp(self):
        self.adapter = BatteryAdapter()

    def test_execute_p2d_fallback(self):
        """验证 execute 在 PyBaMM 不可用时使用回退数据。"""
        self.adapter.pybamm_available = False
        result = self.adapter.execute({
            "track": "p2d",
            "model_type": "DFN",
            "parameter_set": "Chen2020",
            "requested_variables": ["Terminal voltage [V]", "Current [A]"],
        })
        self.assertIn("results", result)
        self.assertIn("Terminal voltage [V]", result["results"])
        self.assertIn("summary", result)

    def test_execute_ecm_fallback(self):
        """验证 ECM 回退应返回占位结果。"""
        self.adapter.pybamm_available = False
        result = self.adapter.execute({
            "track": "ecm",
            "model_type": "Thevenin",
            "requested_variables": ["Terminal voltage [V]"],
        })
        self.assertEqual(result["track"], "ecm")
        self.assertIn("Terminal voltage [V]", result["results"])

    def test_execute_pybop_fallback(self):
        """验证 PyBOP 回退应返回占位参数辨识结果。"""
        self.adapter.pybop_available = False
        result = self.adapter.execute({
            "track": "pybop",
            "parameter_set": "Chen2020",
        })
        self.assertEqual(result["track"], "pybop")
        self.assertIn("optimized_params", result["results"])

    def test_execute_unknown_track(self):
        """验证未知轨道应返回错误。"""
        result = self.adapter.execute({
            "track": "unknown",
        })
        self.assertIn("error", result)
        self.assertIn("Unknown track", result["error"])

    def test_parse_output_dict(self):
        """验证 parse_output 能正确处理 dict 输入。"""
        result = self.adapter.parse_output({"track": "p2d", "results": {}})
        self.assertEqual(result["track"], "p2d")

    def test_parse_output_non_dict(self):
        """验证 parse_output 能处理非 dict 输入。"""
        result = self.adapter.parse_output("not a dict")
        self.assertEqual(result, "not a dict")

    def test_get_resource_requirements_p2d_dfn(self):
        """验证 P2D/DFN 资源需求。"""
        reqs = self.adapter.get_resource_requirements({"track": "p2d", "model_type": "DFN"})
        self.assertEqual(reqs["cpu"], 2)
        self.assertEqual(reqs["memory_mb"], 2048)

    def test_get_resource_requirements_p2d_spm(self):
        """验证 P2D/SPM 资源需求。"""
        reqs = self.adapter.get_resource_requirements({"track": "p2d", "model_type": "SPM"})
        self.assertEqual(reqs["cpu"], 1)
        self.assertEqual(reqs["memory_mb"], 1024)

    def test_get_resource_requirements_pybop(self):
        """验证 PyBOP 资源需求。"""
        reqs = self.adapter.get_resource_requirements({"track": "pybop"})
        self.assertEqual(reqs["cpu"], 4)
        self.assertEqual(reqs["memory_mb"], 4096)

    def test_fallback_p2d_voltage_shape(self):
        """验证回退 P2D 仿真电压数据格式。"""
        self.adapter.pybamm_available = False
        result = self.adapter.execute({
            "track": "p2d",
            "model_type": "DFN",
            "requested_variables": ["Terminal voltage [V]"],
        })
        voltage = result["results"]["Terminal voltage [V]"]
        self.assertGreater(len(voltage), 0)
        self.assertAlmostEqual(voltage[0], 4.2, places=1)

    def test_fallback_ecm_voltage_shape(self):
        """验证回退 ECM 仿真电压数据格式。"""
        self.adapter.pybamm_available = False
        result = self.adapter.execute({
            "track": "ecm",
            "model_type": "Thevenin",
            "requested_variables": ["Terminal voltage [V]"],
        })
        voltage = result["results"]["Terminal voltage [V]"]
        self.assertGreater(len(voltage), 0)
        self.assertAlmostEqual(voltage[0], 3.8, places=1)


# ============================================================================
# EvidenceMapper 测试
# ============================================================================

class TestEvidenceMapper(unittest.TestCase):
    """evidence_mapper 函数测试。"""

    def test_map_simulation_evidence_high_confidence(self):
        """验证高置信度应映射为 HIGH 级别。"""
        package = map_simulation_evidence(
            run_id="run-001",
            task_id="task-001",
            claim="最终电压 = 4.0 V",
            value=4.0,
            unit="V",
            confidence=0.95,
            method="pybamm_p2d_DFN",
        )
        self.assertEqual(package.level, EvidenceLevel.HIGH)
        self.assertEqual(package.source_service, "real_engine:battery_modeling")

    def test_map_simulation_evidence_medium_confidence(self):
        """验证中等置信度应映射为 MEDIUM 级别。"""
        package = map_simulation_evidence(
            run_id="run-001",
            task_id="task-001",
            claim="最终电压 = 4.0 V",
            value=4.0,
            unit="V",
            confidence=0.80,
        )
        self.assertEqual(package.level, EvidenceLevel.MEDIUM)

    def test_map_simulation_evidence_low_confidence(self):
        """验证低置信度应映射为 LOW 级别。"""
        package = map_simulation_evidence(
            run_id="run-001",
            task_id="task-001",
            claim="估算值",
            value=None,
            confidence=0.50,
        )
        self.assertEqual(package.level, EvidenceLevel.LOW)

    def test_map_simulation_evidence_default_method(self):
        """验证默认 method 应为 pybamm_simulation。"""
        package = map_simulation_evidence(
            run_id="run-001",
            task_id="task-001",
            claim="测试",
            value=1.0,
        )
        self.assertEqual(package.method, "pybamm_simulation")

    def test_map_simulation_evidence_metadata(self):
        """验证元数据应正确传递。"""
        meta = {"track": "p2d", "model_type": "DFN"}
        package = map_simulation_evidence(
            run_id="run-001",
            task_id="task-001",
            claim="测试",
            value=1.0,
            metadata=meta,
        )
        self.assertEqual(package.metadata["track"], meta["track"])
        self.assertEqual(package.metadata["model_type"], meta["model_type"])

    def test_batch_map_evidence(self):
        """验证批量映射应返回正确数量的证据包。"""
        packages = batch_map_evidence(
            run_id="run-001",
            task_id="task-001",
            track="p2d",
            model_type="DFN",
            parameter_set="Chen2020",
            results={
                "Terminal voltage [V]": [4.2, 4.1, 4.0],
                "Current [A]": [1.0, 1.0, 1.0],
            },
            summary={
                "final_voltage": 4.0,
                "total_capacity": 5.0,
            },
        )
        # 1 个概要 + 2 个摘要 + 2 个变量 = 5
        self.assertEqual(len(packages), 5)

    def test_batch_map_evidence_empty_results(self):
        """验证空结果和摘要应返回 1 个概要包。"""
        packages = batch_map_evidence(
            run_id="run-001",
            task_id="task-001",
            track="p2d",
            model_type="DFN",
            parameter_set="Chen2020",
            results={},
            summary={},
        )
        self.assertEqual(len(packages), 1)

    def test_batch_map_evidence_summary_keys(self):
        """验证摘要统计键名映射到中文描述。"""
        packages = batch_map_evidence(
            run_id="run-001",
            task_id="task-001",
            track="p2d",
            model_type="DFN",
            parameter_set="Chen2020",
            results={},
            summary={
                "final_voltage": 4.0,
                "total_capacity": 5.0,
                "max_temperature": 303.15,
                "min_voltage": 3.5,
                "max_voltage": 4.2,
                "cycle_count": 3,
            },
        )
        # 1 个概要 + 6 个摘要 = 7
        self.assertEqual(len(packages), 7)
        # 验证包中包含中文描述
        claims = [p.claim for p in packages]
        self.assertTrue(any("最终端电压" in c for c in claims))
        self.assertTrue(any("总容量" in c for c in claims))
        self.assertTrue(any("最高温度" in c for c in claims))
        self.assertTrue(any("循环次数" in c for c in claims))

    def test_batch_map_evidence_variable_claims(self):
        """验证变量证据包含首值/末值/点数。"""
        packages = batch_map_evidence(
            run_id="run-001",
            task_id="task-001",
            track="p2d",
            model_type="DFN",
            parameter_set="Chen2020",
            results={
                "Terminal voltage [V]": [4.2, 4.1, 4.0, 3.9],
            },
            summary={},
        )
        # 1 个概要 + 1 个变量 = 2
        self.assertEqual(len(packages), 2)
        var_pkg = packages[1]
        self.assertIn("首值", var_pkg.claim)
        self.assertIn("末值", var_pkg.claim)
        self.assertIn("点数", var_pkg.claim)
        self.assertEqual(var_pkg.value["first"], 4.2)
        self.assertEqual(var_pkg.value["last"], 3.9)
        self.assertEqual(var_pkg.value["count"], 4)

    def test_batch_map_evidence_skips_non_list_data(self):
        """验证非列表变量数据应被跳过。"""
        packages = batch_map_evidence(
            run_id="run-001",
            task_id="task-001",
            track="p2d",
            model_type="DFN",
            parameter_set="Chen2020",
            results={
                "Terminal voltage [V]": "not a list",
            },
            summary={},
        )
        # 只有 1 个概要包
        self.assertEqual(len(packages), 1)

    def test_batch_map_evidence_skips_none_summary_values(self):
        """验证 None 摘要值应被跳过。"""
        packages = batch_map_evidence(
            run_id="run-001",
            task_id="task-001",
            track="p2d",
            model_type="DFN",
            parameter_set="Chen2020",
            results={},
            summary={
                "final_voltage": None,
                "total_capacity": 5.0,
            },
        )
        # 只有 1 个概要 + 1 个有效摘要
        self.assertEqual(len(packages), 2)


# ============================================================================
# VALID_TRACKS / VALID_MODEL_TYPES / VALID_PARAMETER_SETS / VALID_THERMAL_OPTIONS 常量测试
# ============================================================================

class TestBatteryModelingConstants(unittest.TestCase):
    """电池建模常量完整性测试。"""

    def test_valid_tracks(self):
        """验证轨道常量应包含 p2d/ecm/pybop。"""
        self.assertEqual(VALID_TRACKS, frozenset({"p2d", "ecm", "pybop"}))

    def test_valid_model_types_keys(self):
        """验证模型类型字典包含所有轨道。"""
        self.assertIn("p2d", VALID_MODEL_TYPES)
        self.assertIn("ecm", VALID_MODEL_TYPES)
        self.assertIn("pybop", VALID_MODEL_TYPES)

    def test_valid_model_types_p2d(self):
        """验证 p2d 轨道模型类型。"""
        self.assertEqual(set(VALID_MODEL_TYPES["p2d"]), {"SPM", "SPMe", "DFN"})

    def test_valid_model_types_ecm(self):
        """验证 ecm 轨道模型类型。"""
        self.assertEqual(set(VALID_MODEL_TYPES["ecm"]), {"Thevenin", "PNGV", "RC"})

    def test_valid_parameter_sets_has_known_sets(self):
        """验证参数集包含已知关键集。"""
        self.assertIn("Chen2020", VALID_PARAMETER_SETS)
        self.assertIn("OKane2022", VALID_PARAMETER_SETS)
        self.assertIn("Prada2013", VALID_PARAMETER_SETS)

    def test_valid_parameter_sets_has_description(self):
        """验证每个参数集包含 description 字段。"""
        for name, meta in VALID_PARAMETER_SETS.items():
            with self.subTest(parameter_set=name):
                self.assertIn("description", meta)
                self.assertIn("chemistry", meta)
                self.assertIn("use_case", meta)

    def test_valid_thermal_options(self):
        """验证热选项常量。"""
        self.assertEqual(VALID_THERMAL_OPTIONS, frozenset({"isothermal", "lumped", "x-full"}))


if __name__ == "__main__":
    unittest.main()