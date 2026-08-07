"""化工过程建模服务单元测试 — ProcessModelingApplication 的完整生命周期验证。"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from battery_materials_agent.contracts.task import Task
from battery_materials_agent.contracts.run import Run
from battery_materials_agent.contracts.artifact import Artifact, ArtifactType
from battery_materials_agent.contracts.evidence import EvidencePackage, EvidenceLevel
from battery_materials_agent.services.process_modeling.application import (
    ProcessModelingApplication,
    RunProcessCalculation,
    MODULE_CATALOG,
)
from battery_materials_agent.services.process_modeling.validators import (
    ProcessModelingValidator,
    validate_module, validate_calculation_type, validate_compounds,
    validate_conditions, validate_module_parameters,
    VALID_MODULES, CALCULATION_TYPES, MODULE_NAMES,
)
from battery_materials_agent.services.process_modeling.evidence_mapper import (
    map_process_evidence, batch_map_process_evidence,
)


# =============================================================================
# 校验器类
# =============================================================================


class TestProcessModelingValidator(unittest.TestCase):
    """ProcessModelingValidator 综合校验逻辑测试。"""

    def setUp(self):
        self.valid_compounds = [{"name": "乙醇", "smiles": "CCO"}]
        self.valid_conditions = {"temperature_k": 298.15, "pressure_pa": 101325}
        self.valid_params = {"method": "hess"}

    def test_validate_all_valid_input(self):
        """验证有效输入应返回 validated=True 且无错误。"""
        result = ProcessModelingValidator.validate_all(
            module="M1",
            calculation_type="hess",
            compounds=self.valid_compounds,
            conditions=self.valid_conditions,
            parameters=self.valid_params,
        )
        self.assertTrue(result["validated"])
        self.assertEqual(len(result["errors"]), 0)

    def test_validate_all_invalid_module(self):
        """验证无效模块应返回 validated=False。"""
        result = ProcessModelingValidator.validate_all(
            module="M7",
            calculation_type="hess",
            compounds=self.valid_compounds,
            conditions={},
            parameters={},
        )
        self.assertFalse(result["validated"])
        self.assertGreater(len(result["errors"]), 0)

    def test_validate_all_invalid_calculation_type(self):
        """验证模块不支持的计算类型应返回错误。"""
        result = ProcessModelingValidator.validate_all(
            module="M1",
            calculation_type="kremser",
            compounds=self.valid_compounds,
            conditions={},
            parameters={},
        )
        self.assertFalse(result["validated"])
        self.assertIn("不支持", str(result["errors"]))

    def test_validate_all_missing_compounds_m1(self):
        """验证 M1 缺少化合物应返回错误。"""
        result = ProcessModelingValidator.validate_all(
            module="M1",
            calculation_type="hess",
            compounds=[],
            conditions={},
            parameters={},
        )
        self.assertFalse(result["validated"])
        self.assertIn("需要至少一个化合物", str(result["errors"]))

    def test_validate_all_invalid_conditions(self):
        """验证异常条件应返回错误。"""
        result = ProcessModelingValidator.validate_all(
            module="M1",
            calculation_type="hess",
            compounds=self.valid_compounds,
            conditions={"temperature_k": -1},
            parameters={},
        )
        self.assertFalse(result["validated"])
        self.assertIn("温度", str(result["errors"]))

    def test_validate_all_invalid_module_parameters(self):
        """验证无效模块参数应返回错误。"""
        result = ProcessModelingValidator.validate_all(
            module="M1",
            calculation_type="hess",
            compounds=self.valid_compounds,
            conditions={},
            parameters={"method": "invalid_method"},
        )
        self.assertFalse(result["validated"])
        self.assertIn("method", str(result["errors"]))


# =============================================================================
# 校验函数
# =============================================================================


class TestValidateModule(unittest.TestCase):
    """validate_module 函数测试。"""

    def test_valid_module_m1(self):
        """验证 M1 应返回 None。"""
        self.assertIsNone(validate_module("M1"))

    def test_valid_module_m6(self):
        """验证 M6 应返回 None。"""
        self.assertIsNone(validate_module("M6"))

    def test_empty_module(self):
        """验证空模块应返回错误。"""
        self.assertIn("不能为空", validate_module(""))

    def test_invalid_module(self):
        """验证无效模块应返回错误。"""
        self.assertIn("无效模块", validate_module("M7"))


class TestValidateCalculationType(unittest.TestCase):
    """validate_calculation_type 函数测试。"""

    def test_valid_type_for_m1(self):
        """验证 M1 允许的计算类型应返回 None。"""
        self.assertIsNone(validate_calculation_type("M1", "hess"))
        self.assertIsNone(validate_calculation_type("M1", "joback"))
        self.assertIsNone(validate_calculation_type("M1", "dft"))

    def test_valid_type_for_m4(self):
        """验证 M4 允许的计算类型应返回 None。"""
        self.assertIsNone(validate_calculation_type("M4", "kremser"))

    def test_empty_type(self):
        """验证空计算类型应返回错误。"""
        self.assertIn("不能为空", validate_calculation_type("M1", ""))

    def test_incompatible_type(self):
        """验证不兼容的计算类型应返回错误。"""
        self.assertIn("不支持", validate_calculation_type("M1", "kremser"))


class TestValidateCompounds(unittest.TestCase):
    """validate_compounds 函数测试。"""

    def test_empty_compounds_m1(self):
        """验证 M1 空化合物列表应返回错误。"""
        errors = validate_compounds([], "M1")
        self.assertGreater(len(errors), 0)
        self.assertIn("需要至少一个化合物", str(errors))

    def test_empty_compounds_m4(self):
        """验证 M4 空化合物列表应返回空错误（非必需）。"""
        errors = validate_compounds([], "M4")
        self.assertEqual(len(errors), 0)

    def test_valid_compounds(self):
        """验证有效化合物应返回空错误列表。"""
        errors = validate_compounds([{"name": "乙醇", "smiles": "CCO"}], "M1")
        self.assertEqual(len(errors), 0)

    def test_missing_identifiers(self):
        """验证缺少名称/SMILES/CAS 的化合物应返回错误。"""
        errors = validate_compounds([{"some_key": "value"}], "M1")
        self.assertGreater(len(errors), 0)
        self.assertIn("缺少", str(errors[0]))

    def test_non_dict_compound(self):
        """验证非字典格式的化合物应返回错误。"""
        errors = validate_compounds(["not_a_dict"], "M1")
        self.assertIn("格式错误", str(errors[0]))


class TestValidateConditions(unittest.TestCase):
    """validate_conditions 函数测试。"""

    def test_empty_conditions(self):
        """验证空条件应返回空错误列表。"""
        self.assertEqual(len(validate_conditions({})), 0)

    def test_valid_temperature(self):
        """验证有效温度应返回空错误列表。"""
        self.assertEqual(len(validate_conditions({"temperature_k": 298.15})), 0)

    def test_invalid_temperature_type(self):
        """验证非数值温度应返回错误。"""
        errors = validate_conditions({"temperature_k": "hot"})
        self.assertGreater(len(errors), 0)

    def test_temperature_out_of_range(self):
        """验证超出范围的温度应返回错误。"""
        errors = validate_conditions({"temperature_k": 99999})
        self.assertIn("温度范围异常", str(errors))

    def test_valid_pressure(self):
        """验证有效压力应返回空错误列表。"""
        self.assertEqual(len(validate_conditions({"pressure_pa": 101325})), 0)

    def test_pressure_out_of_range(self):
        """验证超出范围的压力应返回错误。"""
        errors = validate_conditions({"pressure_pa": 1e12})
        self.assertIn("压力范围异常", str(errors))

    def test_valid_composition(self):
        """验证有效组成应返回空错误列表。"""
        self.assertEqual(len(validate_conditions({"composition": [0.5, 0.5]})), 0)

    def test_invalid_composition_sum(self):
        """验证组成之和不为 1 应返回错误。"""
        errors = validate_conditions({"composition": [0.8, 0.8]})
        self.assertIn("摩尔分数之和", str(errors))

    def test_composition_too_short(self):
        """验证组成元素少于 2 应返回错误。"""
        errors = validate_conditions({"composition": [1.0]})
        self.assertIn("至少两个元素", str(errors))


class TestValidateModuleParameters(unittest.TestCase):
    """validate_module_parameters 函数测试。"""

    def test_empty_parameters(self):
        """验证空参数应返回空错误列表。"""
        self.assertEqual(len(validate_module_parameters("M1", {})), 0)

    def test_m1_method_hess(self):
        """验证 M1 hess 方法应返回空错误列表。"""
        self.assertEqual(len(validate_module_parameters("M1", {"method": "hess"})), 0)

    def test_m1_method_invalid(self):
        """验证 M1 无效方法应返回错误。"""
        errors = validate_module_parameters("M1", {"method": "invalid"})
        self.assertIn("不支持", str(errors))

    def test_m2_method_wilke_chang(self):
        """验证 M2 wilke_chang 方法应返回空错误列表。"""
        self.assertEqual(len(validate_module_parameters("M2", {"method": "wilke_chang"})), 0)

    def test_m2_method_invalid(self):
        """验证 M2 无效方法应返回错误。"""
        errors = validate_module_parameters("M2", {"method": "invalid"})
        self.assertIn("不支持", str(errors))

    def test_m4_k_value_positive(self):
        """验证 M4 正 k_value 应返回空错误列表。"""
        self.assertEqual(len(validate_module_parameters("M4", {"k_value": 1.5})), 0)

    def test_m4_k_value_non_positive(self):
        """验证 M4 非正 k_value 应返回错误。"""
        errors = validate_module_parameters("M4", {"k_value": -1})
        self.assertIn("必须为正数", str(errors))

    def test_m5_relative_volatility_valid(self):
        """验证 M5 大于 1 的相对挥发度应返回空错误列表。"""
        self.assertEqual(len(validate_module_parameters("M5", {"relative_volatility": 2.5})), 0)

    def test_m5_relative_volatility_invalid(self):
        """验证 M5 小于等于 1 的相对挥发度应返回错误。"""
        errors = validate_module_parameters("M5", {"relative_volatility": 1.0})
        self.assertIn("必须大于 1", str(errors))


# =============================================================================
# Pydantic 命令模型
# =============================================================================


class TestRunProcessCalculationModel(unittest.TestCase):
    """RunProcessCalculation Pydantic 模型测试。"""

    def test_model_creation(self):
        """验证模型创建应正确设置字段值。"""
        cmd = RunProcessCalculation(
            project_id="proj-001",
            module="M1",
            calculation_type="hess",
            compounds=[{"name": "乙醇", "smiles": "CCO"}],
            conditions={"temperature_k": 298.15},
            parameters={"method": "hess"},
        )
        self.assertEqual(cmd.project_id, "proj-001")
        self.assertEqual(cmd.module, "M1")
        self.assertEqual(cmd.calculation_type, "hess")
        self.assertEqual(len(cmd.compounds), 1)
        self.assertEqual(cmd.conditions, {"temperature_k": 298.15})
        self.assertEqual(cmd.parameters, {"method": "hess"})

    def test_default_compounds(self):
        """验证默认 compounds 应为空列表。"""
        cmd = RunProcessCalculation(
            project_id="proj-001",
            module="M1",
            calculation_type="hess",
        )
        self.assertEqual(cmd.compounds, [])

    def test_default_conditions(self):
        """验证默认 conditions 应为空字典。"""
        cmd = RunProcessCalculation(
            project_id="proj-001",
            module="M1",
            calculation_type="hess",
        )
        self.assertEqual(cmd.conditions, {})

    def test_default_parameters(self):
        """验证默认 parameters 应为空字典。"""
        cmd = RunProcessCalculation(
            project_id="proj-001",
            module="M1",
            calculation_type="hess",
        )
        self.assertEqual(cmd.parameters, {})


# =============================================================================
# 能力属性
# =============================================================================


class TestProcessModelingApplicationCapability(unittest.TestCase):
    """ProcessModelingApplication 能力标识测试。"""

    def setUp(self):
        self.app = ProcessModelingApplication(kernel=MagicMock())

    def test_capability_id(self):
        """验证 capability_id 应为 'process_modeling'。"""
        self.assertEqual(self.app.capability_id, "process_modeling")

    def test_display_name(self):
        """验证 display_name 应为中文名称。"""
        self.assertEqual(self.app.display_name, "化工过程建模")

    def test_description(self):
        """验证 description 应包含服务描述。"""
        self.assertIn("反应热", self.app.description)
        self.assertIn("扩散", self.app.description)
        self.assertIn("蒸馏", self.app.description)


# =============================================================================
# Validate 方法
# =============================================================================


class TestProcessModelingApplicationValidate(unittest.TestCase):
    """ProcessModelingApplication.validate 方法测试。"""

    def setUp(self):
        self.app = ProcessModelingApplication(kernel=MagicMock())

    def test_validate_valid_input(self):
        """验证有效输入应返回无错误结果。"""
        task = Task(
            project_id="proj-001",
            capability_id="process_modeling",
            title="test",
            metadata={
                "module": "M1",
                "calculation_type": "hess",
                "compounds": [{"name": "乙醇", "smiles": "CCO"}],
                "conditions": {"temperature_k": 298.15},
                "parameters": {"method": "hess"},
            },
        )
        result = self.app.validate(task, {})
        self.assertTrue(result["validated"])

    def test_validate_invalid_module(self):
        """验证无效模块应返回错误。"""
        task = Task(
            project_id="proj-001",
            capability_id="process_modeling",
            title="test",
            metadata={
                "module": "M7",
                "calculation_type": "hess",
                "compounds": [{"name": "乙醇", "smiles": "CCO"}],
            },
        )
        result = self.app.validate(task, {})
        self.assertFalse(result["validated"])
        self.assertIn("errors", result)

    def test_validate_empty_compounds_m1(self):
        """验证 M1 空化合物应返回错误。"""
        task = Task(
            project_id="proj-001",
            capability_id="process_modeling",
            title="test",
            metadata={
                "module": "M1",
                "calculation_type": "hess",
                "compounds": [],
            },
        )
        result = self.app.validate(task, {})
        self.assertFalse(result["validated"])


# =============================================================================
# Prepare 方法
# =============================================================================


class TestProcessModelingApplicationPrepare(unittest.TestCase):
    """ProcessModelingApplication.prepare 方法测试。"""

    def setUp(self):
        self.app = ProcessModelingApplication(kernel=MagicMock())

    def test_prepare_creates_run(self):
        """验证 prepare 应创建正确的 Run 实例。"""
        task = Task(
            task_id="task-001",
            project_id="proj-001",
            capability_id="process_modeling",
            title="test",
            metadata={
                "module": "M1",
                "calculation_type": "hess",
                "compounds": [{"name": "乙醇", "smiles": "CCO"}],
                "conditions": {"temperature_k": 298.15},
                "parameters": {"method": "hess"},
            },
        )
        run = self.app.prepare(task)
        self.assertIsInstance(run, Run)
        self.assertEqual(run.task_id, "task-001")
        self.assertEqual(run.service_id, "process_modeling")
        self.assertIn("process_calculation M1", run.command)
        self.assertIn("module", run.input)
        self.assertEqual(run.input["module"], "M1")
        self.assertEqual(run.input["calculation_type"], "hess")


# =============================================================================
# Execute 方法
# =============================================================================


class TestProcessModelingApplicationExecute(unittest.TestCase):
    """ProcessModelingApplication.execute 方法测试。"""

    def setUp(self):
        self.app = ProcessModelingApplication(kernel=MagicMock())

    def test_execute_m1_returns_artifact(self):
        """验证 execute M1 应返回 Artifact 列表。"""
        run = Run(
            task_id="task-001",
            project_id="proj-001",
            service_id="process_modeling",
            command="process_calculation M1 hess",
            input={
                "module": "M1",
                "calculation_type": "hess",
                "compounds": [{"name": "乙醇", "smiles": "CCO"}],
                "conditions": {"temperature_k": 298.15},
                "parameters": {"method": "hess"},
            },
        )
        artifacts = self.app.execute(run, {})
        self.assertIsInstance(artifacts, list)
        self.assertGreater(len(artifacts), 0)
        self.assertIsInstance(artifacts[0], Artifact)
        self.assertEqual(artifacts[0].type, ArtifactType.RESULT_TABLE)

    def test_execute_unknown_module(self):
        """验证未知模块应返回错误结果。"""
        run = Run(
            task_id="task-001",
            project_id="proj-001",
            service_id="process_modeling",
            command="process_calculation M99 unknown",
            input={
                "module": "M99",
                "calculation_type": "unknown",
                "compounds": [],
                "conditions": {},
                "parameters": {},
            },
        )
        artifacts = self.app.execute(run, {})
        self.assertEqual(artifacts[0].type, ArtifactType.RESULT_TABLE)
        self.assertIn("error", str(artifacts[0].data))


# =============================================================================
# Postprocess 方法
# =============================================================================


class TestProcessModelingApplicationPostprocess(unittest.TestCase):
    """ProcessModelingApplication.postprocess 方法测试。"""

    def setUp(self):
        self.app = ProcessModelingApplication(kernel=MagicMock())

    def test_postprocess_returns_evidence_packages(self):
        """验证 postprocess 应返回 EvidencePackage 列表。"""
        run = Run(
            run_id="run-001",
            task_id="task-001",
            project_id="proj-001",
            service_id="process_modeling",
            command="process_calculation M1 hess",
        )
        artifacts = [
            Artifact(
                run_id="run-001",
                type=ArtifactType.RESULT_TABLE,
                name="process_calculation_M1",
                data={
                    "module": "M1",
                    "results": [
                        {
                            "name": "标准生成焓",
                            "value": None,
                            "unit": "kJ/mol",
                            "source": "chemicals.Hfg / Hfl",
                            "confidence": 0.95,
                            "method": "Hess 定律",
                        }
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
            service_id="process_modeling",
            command="process_calculation M1 hess",
        )
        evidence = self.app.postprocess(run, [])
        self.assertEqual(len(evidence), 0)

    def test_postprocess_empty_artifact_data(self):
        """验证工件 data 为 None 时应跳过。"""
        run = Run(
            run_id="run-001",
            task_id="task-001",
            project_id="proj-001",
            service_id="process_modeling",
            command="process_calculation M1 hess",
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


class TestProcessModelingApplicationRunFullCycle(unittest.TestCase):
    """ProcessModelingApplication.run_full_cycle 完整生命周期测试。"""

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

        app = ProcessModelingApplication(kernel=mock_kernel)
        task = Task(
            project_id="proj-001",
            capability_id="process_modeling",
            title="test",
            metadata={
                "module": "M1",
                "calculation_type": "hess",
                "compounds": [{"name": "乙醇", "smiles": "CCO"}],
                "conditions": {"temperature_k": 298.15},
                "parameters": {"method": "hess"},
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
        app = ProcessModelingApplication(kernel=mock_kernel)
        task = Task(
            project_id="proj-001",
            capability_id="process_modeling",
            title="test",
            metadata={
                "module": "M7",
                "calculation_type": "hess",
                "compounds": [],
            },
        )
        with self.assertRaises(ValueError):
            app.run_full_cycle(task)


# =============================================================================
# 模块计算方法 M1-M6
# =============================================================================


class TestProcessModelingComputeM1(unittest.TestCase):
    """_compute_m1 模块计算方法测试。"""

    def setUp(self):
        self.app = ProcessModelingApplication(kernel=MagicMock())
        self.compounds = [{"name": "乙醇", "smiles": "CCO"}]

    def test_m1_hess_method(self):
        """验证 M1 Hess 方法应返回标准生成焓结果。"""
        results = self.app._compute_m1(
            self.compounds,
            {"temperature_k": 298.15},
            {"method": "hess"},
        )
        self.assertGreater(len(results), 0)
        self.assertIn("标准生成焓", results[0]["name"])
        self.assertEqual(results[0]["method"], "Hess 定律")
        self.assertEqual(results[0]["confidence"], 0.95)

    def test_m1_joback_method(self):
        """验证 M1 Joback 方法应返回 Joback 生成焓结果。"""
        results = self.app._compute_m1(
            self.compounds,
            {"temperature_k": 298.15},
            {"method": "joback"},
        )
        self.assertGreater(len(results), 0)
        self.assertIn("Joback 生成焓", results[0]["name"])
        self.assertEqual(results[0]["method"], "Joback 基团贡献法")
        self.assertEqual(results[0]["confidence"], 0.80)

    def test_m1_dft_method(self):
        """验证 M1 DFT 方法应返回 DFT 生成焓结果。"""
        results = self.app._compute_m1(
            self.compounds,
            {"temperature_k": 298.15},
            {"method": "dft"},
        )
        self.assertGreater(len(results), 0)
        self.assertIn("DFT 生成焓", results[0]["name"])
        self.assertEqual(results[0]["confidence"], 0.95)

    def test_m1_with_reaction(self):
        """验证 M1 包含反应方程时应返回反应焓变。"""
        results = self.app._compute_m1(
            self.compounds,
            {"temperature_k": 298.15},
            {"method": "hess", "reaction": {"reactants": ["CCO"], "products": ["CC"]}},
        )
        names = [r["name"] for r in results]
        self.assertIn("反应焓变 ΔH_rxn", names)


class TestProcessModelingComputeM2(unittest.TestCase):
    """_compute_m2 模块计算方法测试。"""

    def setUp(self):
        self.app = ProcessModelingApplication(kernel=MagicMock())
        self.compounds = [{"name": "乙醇", "smiles": "CCO"}]

    def test_m2_wilke_chang_method(self):
        """验证 M2 Wilke-Chang 方法应返回扩散系数结果。"""
        results = self.app._compute_m2(
            self.compounds,
            {"temperature_k": 298.15},
            {"method": "wilke_chang", "solvent": {"name": "水"}},
        )
        self.assertGreater(len(results), 0)
        self.assertIn("Wilke-Chang", results[0]["name"])
        self.assertEqual(results[0]["confidence"], 0.80)

    def test_m2_stokes_einstein_method(self):
        """验证 M2 Stokes-Einstein 方法应返回扩散系数结果。"""
        results = self.app._compute_m2(
            self.compounds,
            {"temperature_k": 298.15},
            {"method": "stokes_einstein", "particle_radius_m": 1e-9},
        )
        self.assertGreater(len(results), 0)
        self.assertIn("Stokes-Einstein", results[0]["name"])
        self.assertEqual(results[0]["confidence"], 0.85)

    def test_m2_chapman_enskoq_method(self):
        """验证 M2 Chapman-Enskog 方法应返回扩散系数结果。"""
        results = self.app._compute_m2(
            self.compounds,
            {"temperature_k": 298.15},
            {"method": "chapman_enskoq"},
        )
        self.assertGreater(len(results), 0)
        self.assertIn("Chapman-Enskog", results[0]["name"])
        self.assertEqual(results[0]["confidence"], 0.85)


class TestProcessModelingComputeM3(unittest.TestCase):
    """_compute_m3 模块计算方法测试。"""

    def setUp(self):
        self.app = ProcessModelingApplication(kernel=MagicMock())
        self.compounds = [{"name": "A"}]

    def test_m3_batch_reactor(self):
        """验证 M3 批量反应器应返回模拟结果。"""
        results = self.app._compute_m3(
            self.compounds,
            {"temperature_k": 298.15},
            {"calculation_type": "batch_reactor", "t_span": [0, 3600]},
        )
        self.assertGreater(len(results), 0)
        self.assertIn("批量反应器", results[0]["name"])
        self.assertEqual(results[0]["confidence"], 0.85)

    def test_m3_langmuir_hinshelwood(self):
        """验证 M3 Langmuir-Hinshelwood 应返回动力学结果。"""
        results = self.app._compute_m3(
            self.compounds,
            {"temperature_k": 298.15},
            {"calculation_type": "langmuir_hinshelwood"},
        )
        self.assertGreater(len(results), 0)
        self.assertIn("Langmuir-Hinshelwood", results[0]["name"])
        self.assertEqual(results[0]["confidence"], 0.80)

    def test_m3_eyring(self):
        """验证 M3 Eyring 应返回速率常数结果。"""
        results = self.app._compute_m3(
            self.compounds,
            {"temperature_k": 298.15},
            {"calculation_type": "eyring", "dg_dagger_kjmol": 50.0},
        )
        self.assertGreater(len(results), 0)
        self.assertIn("Eyring", results[0]["name"])
        self.assertEqual(results[0]["confidence"], 0.85)

    def test_m3_pfo_pso(self):
        """验证 M3 PFO/PSO 应返回吸附动力学拟合结果。"""
        results = self.app._compute_m3(
            self.compounds,
            {"temperature_k": 298.15},
            {"calculation_type": "pfo_pso"},
        )
        self.assertGreater(len(results), 0)
        self.assertIn("吸附动力学", results[0]["name"])
        self.assertEqual(results[0]["confidence"], 0.80)


class TestProcessModelingComputeM4(unittest.TestCase):
    """_compute_m4 模块计算方法测试。"""

    def setUp(self):
        self.app = ProcessModelingApplication(kernel=MagicMock())
        self.compounds = [{"name": "溶质"}]

    def test_m4_kremser_with_all_params(self):
        """验证 M4 Kremser 完整参数应返回萃取因子、可行性、理论级数。"""
        results = self.app._compute_m4(
            self.compounds,
            {"temperature_k": 298.15},
            {"k_value": 2.0, "v_org": 1.0, "v_aq": 1.0, "x_in": 0.1, "x_out": 0.01},
        )
        names = [r["name"] for r in results]
        self.assertIn("萃取因子 E", names)
        self.assertIn("萃取可行性", names)
        self.assertIn("理论级数 N", names)

    def test_m4_kremser_e_less_than_1(self):
        """验证 E<1 时应返回最大回收率上限。"""
        results = self.app._compute_m4(
            self.compounds,
            {"temperature_k": 298.15},
            {"k_value": 0.5, "v_org": 1.0, "v_aq": 1.0, "x_in": 0.1, "x_out": 0.01},
        )
        names = [r["name"] for r in results]
        self.assertIn("最大回收率上限", names)
        self.assertIn("不可行", results[-1]["value"])

    def test_m4_missing_k_value(self):
        """验证缺少 k_value 应返回空结果。"""
        results = self.app._compute_m4(
            self.compounds,
            {"temperature_k": 298.15},
            {},
        )
        self.assertEqual(len(results), 0)


class TestProcessModelingComputeM5(unittest.TestCase):
    """_compute_m5 模块计算方法测试。"""

    def setUp(self):
        self.app = ProcessModelingApplication(kernel=MagicMock())

    def test_m5_fenske_minimum_stages(self):
        """验证 M5 Fenske 应返回最小理论板数。"""
        results = self.app._compute_m5(
            [],
            {"temperature_k": 298.15},
            {
                "relative_volatility": 2.5,
                "x_d": 0.95,
                "x_b": 0.05,
                "x_f": 0.5,
                "q": 1.0,
            },
        )
        names = [r["name"] for r in results]
        self.assertIn("最小理论板数 N_min", names)

    def test_m5_underwood_gilliland(self):
        """验证 M5 Underwood+Gilliland 应返回回流比和实际板数。"""
        results = self.app._compute_m5(
            [],
            {"temperature_k": 298.15},
            {
                "relative_volatility": 2.5,
                "x_d": 0.95,
                "x_b": 0.05,
                "x_f": 0.5,
                "q": 1.0,
                "hetp": 0.6,
            },
        )
        names = [r["name"] for r in results]
        self.assertIn("最小回流比 R_min", names)
        self.assertIn("实际理论板数 N", names)
        self.assertIn("估算塔高", names)

    def test_m5_missing_alpha(self):
        """验证缺少相对挥发度应返回空结果。"""
        results = self.app._compute_m5(
            [],
            {"temperature_k": 298.15},
            {"x_d": 0.95, "x_b": 0.05},
        )
        self.assertEqual(len(results), 0)


class TestProcessModelingComputeM6(unittest.TestCase):
    """_compute_m6 模块计算方法测试。"""

    def setUp(self):
        self.app = ProcessModelingApplication(kernel=MagicMock())

    def test_m6_known_routing_target(self):
        """验证已知路由目标应返回对应信息。"""
        results = self.app._compute_m6(
            [],
            {},
            {"routing_target": "chem_properties"},
        )
        self.assertGreater(len(results), 0)
        self.assertIn("chem_properties", results[0]["name"])

    def test_m6_unknown_routing_target(self):
        """验证未知路由目标应返回所有可用路由。"""
        results = self.app._compute_m6(
            [],
            {},
            {"routing_target": "unknown_target"},
        )
        self.assertEqual(len(results), 4)  # 应返回所有可用路由
        names = [r["name"] for r in results]
        self.assertTrue(any("chem_properties" in n for n in names))
        self.assertTrue(any("lammps" in n for n in names))


# =============================================================================
# 证据映射器
# =============================================================================


class TestEvidenceMapper(unittest.TestCase):
    """evidence_mapper 函数测试。"""

    def test_map_process_evidence_high_confidence(self):
        """验证高置信度应映射为 HIGH 级别。"""
        package = map_process_evidence(
            run_id="run-001",
            task_id="task-001",
            name="标准生成焓",
            value=46.07,
            unit="kJ/mol",
            source="chemicals.Hfg / Hfl",
            confidence=0.95,
            method="Hess 定律",
            module="M1",
        )
        self.assertEqual(package.level, EvidenceLevel.HIGH)
        self.assertEqual(package.source_service, "real_engine:process_modeling")
        self.assertEqual(package.claim, "标准生成焓 = 46.07 kJ/mol (来源: chemicals.Hfg / Hfl)")

    def test_map_process_evidence_medium_confidence(self):
        """验证中等置信度应映射为 MEDIUM 级别。"""
        package = map_process_evidence(
            run_id="run-001",
            task_id="task-001",
            name="扩散系数",
            value=2.5e-9,
            unit="m²/s",
            confidence=0.80,
            module="M2",
        )
        self.assertEqual(package.level, EvidenceLevel.MEDIUM)

    def test_map_process_evidence_low_confidence(self):
        """验证低置信度应映射为 LOW 级别。"""
        package = map_process_evidence(
            run_id="run-001",
            task_id="task-001",
            name="估算塔高",
            value=12.5,
            unit="m",
            confidence=0.60,
            module="M5",
        )
        self.assertEqual(package.level, EvidenceLevel.LOW)

    def test_map_process_evidence_with_extra_metadata(self):
        """验证额外元数据应被包含在证据包中。"""
        package = map_process_evidence(
            run_id="run-001",
            task_id="task-001",
            name="理论级数",
            value=5.2,
            unit="级",
            confidence=0.85,
            module="M4",
            extra_metadata={"compound": "溶质", "method_detail": "Kremser"},
        )
        self.assertIn("compound", package.metadata)
        self.assertEqual(package.metadata["compound"], "溶质")

    def test_batch_map_process_evidence(self):
        """验证批量映射应返回正确数量的证据包。"""
        results = [
            {
                "name": "标准生成焓",
                "value": -277.6,
                "unit": "kJ/mol",
                "source": "chemicals.Hfg / Hfl",
                "confidence": 0.95,
                "method": "Hess 定律",
                "compound": "乙醇",
            },
            {
                "name": "反应焓变 ΔH_rxn",
                "value": -50.0,
                "unit": "kJ/mol",
                "confidence": 0.90,
                "method": "Hess 定律",
            },
        ]
        packages = batch_map_process_evidence(
            run_id="run-001",
            task_id="task-001",
            results=results,
            module="M1",
        )
        self.assertEqual(len(packages), 2)
        self.assertIsInstance(packages[0], EvidencePackage)
        self.assertIn("compound", packages[0].metadata)

    def test_batch_map_process_evidence_empty(self):
        """验证空结果列表应返回空列表。"""
        packages = batch_map_process_evidence(
            run_id="run-001",
            task_id="task-001",
            results=[],
            module="M1",
        )
        self.assertEqual(len(packages), 0)


# =============================================================================
# 模块目录
# =============================================================================


class TestModuleCatalog(unittest.TestCase):
    """MODULE_CATALOG 完整性测试。"""

    def test_catalog_has_6_modules(self):
        """验证模块目录应包含 6 个模块。"""
        self.assertEqual(len(MODULE_CATALOG), 6)

    def test_module_keys_match_valid_modules(self):
        """验证 MODULE_CATALOG 的键与 VALID_MODULES 一致。"""
        self.assertEqual(set(MODULE_CATALOG.keys()), VALID_MODULES)

    def test_module_names_match(self):
        """验证 MODULE_CATALOG 的 name 与 MODULE_NAMES 一致。"""
        for key, catalog_entry in MODULE_CATALOG.items():
            self.assertEqual(catalog_entry["name"], MODULE_NAMES[key])

    def test_each_module_has_required_fields(self):
        """验证每个模块都包含 name, description, methods。"""
        for key, meta in MODULE_CATALOG.items():
            with self.subTest(key=key):
                self.assertIn("name", meta)
                self.assertIn("description", meta)
                self.assertIn("methods", meta)

    def test_calculation_types_match_catalog(self):
        """验证 CALCULATION_TYPES 的键与 MODULE_CATALOG 一致。"""
        self.assertEqual(set(CALCULATION_TYPES.keys()), set(MODULE_CATALOG.keys()))


if __name__ == "__main__":
    unittest.main()