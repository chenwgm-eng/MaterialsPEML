"""配方与堆积优化服务单元测试 — 验证 formulation_optimization 和 packing 操作生命周期。"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from battery_materials_agent.contracts.task import Task
from battery_materials_agent.contracts.run import Run
from battery_materials_agent.contracts.artifact import Artifact, ArtifactType
from battery_materials_agent.contracts.evidence import EvidencePackage, EvidenceLevel
from battery_materials_agent.services.formulation_packing.application import (
    FormulationPackingApplication,
    OptimizeFormulation,
    PackingRequest,
)
from battery_materials_agent.services.formulation_packing.validators import (
    FormulationValidator,
    validate_formulation_components,
    validate_packing_parameters,
)
from battery_materials_agent.services.formulation_packing.evidence_mapper import (
    map_formulation_evidence,
    map_packing_evidence,
)
from battery_materials_agent.infrastructure.executors.formulation_adapter import (
    FormulationAdapter,
)


class TestFormulationValidator(unittest.TestCase):
    """FormulationValidator 校验逻辑测试。"""

    def test_validate_components_valid(self):
        """验证有效组分列表应返回 valid=True。"""
        components = [
            {"name": "EC", "smiles": "C1COC(=O)O1", "ratio_range_min": 0.1, "ratio_range_max": 0.5},
            {"name": "DMC", "smiles": "COC(=O)OC", "ratio_range_min": 0.1, "ratio_range_max": 0.5},
        ]
        result = FormulationValidator.validate_components(components)
        self.assertTrue(result["valid"])

    def test_validate_components_empty(self):
        """验证空组分列表应返回 valid=False。"""
        result = FormulationValidator.validate_components([])
        self.assertFalse(result["valid"])
        self.assertIn("不能为空", str(result["errors"]))

    def test_validate_components_missing_name(self):
        """验证缺少 name 字段应返回错误。"""
        components = [
            {"smiles": "C1COC(=O)O1", "ratio_range_min": 0.1, "ratio_range_max": 0.5},
        ]
        result = FormulationValidator.validate_components(components)
        self.assertFalse(result["valid"])

    def test_validate_components_missing_smiles(self):
        """验证缺少 smiles 字段应返回错误。"""
        components = [
            {"name": "EC", "ratio_range_min": 0.1, "ratio_range_max": 0.5},
        ]
        result = FormulationValidator.validate_components(components)
        self.assertFalse(result["valid"])

    def test_validate_components_invalid_ratio_range(self):
        """验证无效 ratio_range 应返回错误。"""
        components = [
            {"name": "EC", "smiles": "C1COC(=O)O1", "ratio_range_min": 0.6, "ratio_range_max": 0.3},
        ]
        result = FormulationValidator.validate_components(components)
        self.assertFalse(result["valid"])

    def test_validate_packing_valid(self):
        """验证有效堆积参数应返回 valid=True。"""
        result = FormulationValidator.validate_packing({
            "packing_type": "crystal",
            "molecules": ["CCO"],
            "target_density": 1.2,
            "box_size_nm": 3.0,
        })
        self.assertTrue(result["valid"])

    def test_validate_packing_missing_type(self):
        """验证缺少 packing_type 应返回错误。"""
        result = FormulationValidator.validate_packing({
            "molecules": ["CCO"],
        })
        self.assertFalse(result["valid"])
        self.assertIn("packing_type", str(result["errors"]))

    def test_validate_packing_invalid_type(self):
        """验证无效 packing_type 应返回错误。"""
        result = FormulationValidator.validate_packing({
            "packing_type": "invalid_type",
            "molecules": ["CCO"],
        })
        self.assertFalse(result["valid"])

    def test_validate_packing_empty_molecules(self):
        """验证空 molecules 列表应返回错误。"""
        result = FormulationValidator.validate_packing({
            "packing_type": "crystal",
            "molecules": [],
        })
        self.assertFalse(result["valid"])

    def test_validate_packing_negative_density(self):
        """验证负密度应返回错误。"""
        result = FormulationValidator.validate_packing({
            "packing_type": "crystal",
            "molecules": ["CCO"],
            "target_density": -1.0,
        })
        self.assertFalse(result["valid"])

    def test_validate_optimization_goal_valid(self):
        """验证有效优化目标应返回 valid=True。"""
        for goal in ["maximize", "minimize", "target"]:
            with self.subTest(goal=goal):
                result = FormulationValidator.validate_optimization_goal(goal)
                self.assertTrue(result["valid"])

    def test_validate_optimization_goal_invalid(self):
        """验证无效优化目标应返回错误。"""
        result = FormulationValidator.validate_optimization_goal("unknown")
        self.assertFalse(result["valid"])


class TestValidateFormulationComponents(unittest.TestCase):
    """validate_formulation_components 函数测试。"""

    def test_valid_components(self):
        """验证有效组分应返回无错误。"""
        components = [
            {"name": "EC", "smiles": "C1COC(=O)O1", "ratio_range_min": 0.0, "ratio_range_max": 1.0},
        ]
        result = validate_formulation_components(components)
        self.assertTrue(result["valid"])

    def test_empty_components(self):
        """验证空列表应返回错误。"""
        result = validate_formulation_components([])
        self.assertFalse(result["valid"])


class TestValidatePackingParameters(unittest.TestCase):
    """validate_packing_parameters 函数测试。"""

    def test_valid_params(self):
        """验证有效参数应返回无错误。"""
        result = validate_packing_parameters({
            "packing_type": "amorphous",
            "molecules": ["CCO"],
            "target_density": 1.0,
            "box_size_nm": 5.0,
        })
        self.assertTrue(result["valid"])

    def test_solvation_type(self):
        """验证 solvation 类型应通过校验。"""
        result = validate_packing_parameters({
            "packing_type": "solvation",
            "molecules": ["CCO", "CC"],
        })
        self.assertTrue(result["valid"])


class TestOptimizeFormulationModel(unittest.TestCase):
    """OptimizeFormulation Pydantic 模型测试。"""

    def test_model_creation(self):
        """验证模型创建应正确设置字段值。"""
        cmd = OptimizeFormulation(
            project_id="proj-001",
            components=[
                {"name": "EC", "smiles": "C1COC(=O)O1", "ratio_range_min": 0.1, "ratio_range_max": 0.5},
            ],
            target_properties=["viscosity", "conductivity"],
            optimization_goal="maximize",
            constraints={"max_temperature": 350},
            max_iterations=500,
        )
        self.assertEqual(cmd.project_id, "proj-001")
        self.assertEqual(len(cmd.components), 1)
        self.assertEqual(cmd.target_properties, ["viscosity", "conductivity"])
        self.assertEqual(cmd.optimization_goal, "maximize")
        self.assertEqual(cmd.max_iterations, 500)

    def test_default_max_iterations(self):
        """验证默认 max_iterations 应为 1000。"""
        cmd = OptimizeFormulation(
            project_id="proj-001",
            components=[{"name": "EC", "smiles": "C1COC(=O)O1", "ratio_range_min": 0.0, "ratio_range_max": 1.0}],
            target_properties=["density"],
            optimization_goal="maximize",
        )
        self.assertEqual(cmd.max_iterations, 1000)


class TestPackingRequestModel(unittest.TestCase):
    """PackingRequest Pydantic 模型测试。"""

    def test_model_creation(self):
        """验证模型创建应正确设置字段值。"""
        cmd = PackingRequest(
            project_id="proj-001",
            molecules=["CCO", "CC"],
            packing_type="crystal",
            target_density=1.5,
            box_size_nm=5.0,
            force_field="uff",
        )
        self.assertEqual(cmd.project_id, "proj-001")
        self.assertEqual(cmd.molecules, ["CCO", "CC"])
        self.assertEqual(cmd.packing_type, "crystal")
        self.assertEqual(cmd.target_density, 1.5)
        self.assertEqual(cmd.force_field, "uff")

    def test_default_force_field(self):
        """验证默认力场应为 'uff'。"""
        cmd = PackingRequest(
            project_id="proj-001",
            molecules=["CCO"],
            packing_type="amorphous",
        )
        self.assertEqual(cmd.force_field, "uff")


class TestFormulationPackingApplicationCapability(unittest.TestCase):
    """FormulationPackingApplication 能力标识测试。"""

    def setUp(self):
        self.app = FormulationPackingApplication(kernel=MagicMock())

    def test_capability_id(self):
        """验证 capability_id 应为 'formulation_packing'。"""
        self.assertEqual(self.app.capability_id, "formulation_packing")

    def test_display_name(self):
        """验证 display_name 应为中文名称。"""
        self.assertEqual(self.app.display_name, "配方与堆积优化")

    def test_description(self):
        """验证 description 应包含服务描述。"""
        self.assertIn("配方优化", self.app.description)
        self.assertIn("堆积", self.app.description)


class TestFormulationPackingApplicationValidate(unittest.TestCase):
    """FormulationPackingApplication.validate 方法测试。"""

    def setUp(self):
        self.app = FormulationPackingApplication(kernel=MagicMock())

    def test_validate_formulation_valid(self):
        """验证有效的配方优化输入应返回 valid=True。"""
        task = Task(
            project_id="proj-001",
            capability_id="formulation_packing",
            title="test",
            metadata={
                "command": "formulation_optimization",
                "components": [
                    {"name": "EC", "smiles": "C1COC(=O)O1", "ratio_range_min": 0.1, "ratio_range_max": 0.5},
                ],
                "optimization_goal": "maximize",
            },
        )
        result = self.app.validate(task, {"command": "formulation_optimization"})
        self.assertTrue(result["valid"])

    def test_validate_formulation_invalid_goal(self):
        """验证无效优化目标应返回错误。"""
        task = Task(
            project_id="proj-001",
            capability_id="formulation_packing",
            title="test",
            metadata={
                "command": "formulation_optimization",
                "components": [
                    {"name": "EC", "smiles": "C1COC(=O)O1", "ratio_range_min": 0.1, "ratio_range_max": 0.5},
                ],
                "optimization_goal": "unknown",
            },
        )
        result = self.app.validate(task, {"command": "formulation_optimization"})
        self.assertFalse(result["valid"])

    def test_validate_packing_valid(self):
        """验证有效的堆积输入应返回 valid=True。"""
        task = Task(
            project_id="proj-001",
            capability_id="formulation_packing",
            title="test",
            metadata={
                "command": "packing",
                "packing_type": "crystal",
                "molecules": ["CCO"],
            },
        )
        result = self.app.validate(task, {"command": "packing"})
        self.assertTrue(result["valid"])

    def test_validate_packing_invalid_type(self):
        """验证无效堆积类型应返回错误。"""
        task = Task(
            project_id="proj-001",
            capability_id="formulation_packing",
            title="test",
            metadata={
                "command": "packing",
                "packing_type": "invalid",
                "molecules": ["CCO"],
            },
        )
        result = self.app.validate(task, {"command": "packing"})
        self.assertFalse(result["valid"])

    def test_validate_missing_command(self):
        """验证缺少 command 应返回错误。"""
        task = Task(
            project_id="proj-001",
            capability_id="formulation_packing",
            title="test",
            metadata={},
        )
        result = self.app.validate(task, {})
        self.assertFalse(result["valid"])

    def test_validate_unsupported_command(self):
        """验证不支持的 command 应返回错误。"""
        task = Task(
            project_id="proj-001",
            capability_id="formulation_packing",
            title="test",
            metadata={"command": "unknown_command"},
        )
        result = self.app.validate(task, {"command": "unknown_command"})
        self.assertFalse(result["valid"])


class TestFormulationPackingApplicationPrepare(unittest.TestCase):
    """FormulationPackingApplication.prepare 方法测试。"""

    def setUp(self):
        self.app = FormulationPackingApplication(kernel=MagicMock())

    def test_prepare_creates_formulation_run(self):
        """验证 prepare 创建配方优化 Run 实例。"""
        task = Task(
            task_id="task-001",
            project_id="proj-001",
            capability_id="formulation_packing",
            title="test",
            metadata={
                "command": "formulation_optimization",
                "input": {"components": []},
            },
        )
        run = self.app.prepare(task)
        self.assertIsInstance(run, Run)
        self.assertEqual(run.task_id, "task-001")
        self.assertEqual(run.service_id, "formulation_packing")
        self.assertEqual(run.command, "formulation_optimization")

    def test_prepare_creates_packing_run(self):
        """验证 prepare 创建堆积 Run 实例。"""
        task = Task(
            task_id="task-001",
            project_id="proj-001",
            capability_id="formulation_packing",
            title="test",
            metadata={
                "command": "packing",
                "input": {"molecules": ["CCO"]},
            },
        )
        run = self.app.prepare(task)
        self.assertEqual(run.command, "packing")


class TestFormulationPackingApplicationExecute(unittest.TestCase):
    """FormulationPackingApplication.execute 方法测试。"""

    def setUp(self):
        self.app = FormulationPackingApplication(kernel=MagicMock())

    def test_execute_formulation_returns_artifact(self):
        """验证配方优化 execute 应返回 Artifact 列表。"""
        run = Run(
            run_id="run-001",
            task_id="task-001",
            project_id="proj-001",
            service_id="formulation_packing",
            command="formulation_optimization",
            input={"components": []},
        )
        artifacts = self.app.execute(run, {})
        self.assertIsInstance(artifacts, list)
        self.assertGreater(len(artifacts), 0)
        self.assertIsInstance(artifacts[0], Artifact)
        self.assertEqual(artifacts[0].type, ArtifactType.RESULT_TABLE)

    def test_execute_packing_returns_artifact(self):
        """验证堆积 execute 应返回 Artifact 列表。"""
        run = Run(
            run_id="run-001",
            task_id="task-001",
            project_id="proj-001",
            service_id="formulation_packing",
            command="packing",
            input={"molecules": ["CCO"]},
        )
        artifacts = self.app.execute(run, {})
        self.assertIsInstance(artifacts, list)
        self.assertGreater(len(artifacts), 0)
        self.assertIsInstance(artifacts[0], Artifact)
        self.assertEqual(artifacts[0].type, ArtifactType.STRUCTURE)

    def test_execute_unsupported_command(self):
        """验证不支持的 command 应抛出 ValueError。"""
        run = Run(
            run_id="run-001",
            task_id="task-001",
            project_id="proj-001",
            service_id="formulation_packing",
            command="unknown",
            input={},
        )
        with self.assertRaises(ValueError):
            self.app.execute(run, {})


class TestFormulationPackingApplicationPostprocess(unittest.TestCase):
    """FormulationPackingApplication.postprocess 方法测试。"""

    def setUp(self):
        self.app = FormulationPackingApplication(kernel=MagicMock())

    def test_postprocess_formulation_returns_evidence(self):
        """验证配方优化 postprocess 应返回 EvidencePackage 列表。"""
        run = Run(
            run_id="run-001",
            task_id="task-001",
            project_id="proj-001",
            service_id="formulation_packing",
            command="formulation_optimization",
        )
        artifacts = [
            Artifact(
                run_id="run-001",
                type=ArtifactType.RESULT_TABLE,
                name="formulation_result",
                data={
                    "formulation_id": "f-001",
                    "properties": [
                        {"name": "density", "value": 1.2, "unit": "g/cm³"},
                        {"name": "viscosity", "value": 5.0, "unit": "mPa·s"},
                    ],
                },
            )
        ]
        evidence = self.app.postprocess(run, artifacts)
        self.assertIsInstance(evidence, list)
        self.assertGreater(len(evidence), 0)
        self.assertIsInstance(evidence[0], EvidencePackage)

    def test_postprocess_packing_returns_evidence(self):
        """验证堆积 postprocess 应返回 EvidencePackage 列表。"""
        run = Run(
            run_id="run-001",
            task_id="task-001",
            project_id="proj-001",
            service_id="formulation_packing",
            command="packing",
        )
        artifacts = [
            Artifact(
                run_id="run-001",
                type=ArtifactType.STRUCTURE,
                name="packing_structure",
                data={
                    "structure_id": "s-001",
                    "density": 1.2,
                    "energy": -150.0,
                },
            )
        ]
        evidence = self.app.postprocess(run, artifacts)
        self.assertIsInstance(evidence, list)
        self.assertGreater(len(evidence), 0)


class TestFormulationPackingApplicationRunFullCycle(unittest.TestCase):
    """FormulationPackingApplication.run_full_cycle 完整生命周期测试。"""

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

        mock_adapter = MagicMock()
        mock_adapter.optimize_formulation.return_value = {
            "formulation_id": "f-001",
            "properties": [
                {"name": "density", "value": 1.2, "unit": "g/cm³"},
            ],
        }

        app = FormulationPackingApplication(kernel=mock_kernel)
        task = Task(
            project_id="proj-001",
            capability_id="formulation_packing",
            title="test",
            metadata={
                "command": "formulation_optimization",
                "components": [
                    {"name": "EC", "smiles": "C1COC(=O)O1", "ratio_range_min": 0.1, "ratio_range_max": 0.5},
                ],
                "optimization_goal": "maximize",
            },
        )
        evidence = app.run_full_cycle(task, {"command": "formulation_optimization", "adapter": mock_adapter})
        self.assertIsInstance(evidence, list)
        self.assertGreater(len(evidence), 0)
        mock_kernel.submit_run.assert_called_once()
        mock_kernel.store_artifact.assert_called()
        mock_kernel.store_evidence.assert_called()


class TestFormulationAdapter(unittest.TestCase):
    """FormulationAdapter 执行适配器测试。"""

    def setUp(self):
        self.adapter = FormulationAdapter()

    def test_execute_formulation_optimization(self):
        """验证配方优化操作应返回结果。"""
        result = self.adapter.execute({
            "operation": "formulation_optimization",
            "components": [{"identifier": "EC", "weight_range": [0.1, 0.5]}],
            "target_properties": ["density"],
        })
        self.assertIn("method", result)
        self.assertIn("optimized_ratios", result)

    def test_execute_packing(self):
        """验证堆积操作应返回真实堆积结果（packmol Docker 或 RDKit 兜底）。"""
        result = self.adapter.execute({
            "operation": "packing",
            "molecules": [{"smiles": "CCO", "count": 10}],
            "box_size": [30.0, 30.0, 30.0],
        })
        # 新契约：返回 density/method/molecules 等真实字段
        self.assertIn("method", result)
        self.assertIn("density", result)
        self.assertIn("molecules", result)
        # engine 字段标识实际使用的引擎
        self.assertIn("engine", result)

    def test_execute_unsupported_operation(self):
        """验证不支持的操作应返回错误。"""
        result = self.adapter.execute({"operation": "unknown"})
        self.assertIn("error", result)

    def test_parse_output(self):
        """验证 parse_output 应原样返回输入。"""
        output = {"method": "grid", "optimized_ratios": []}
        self.assertEqual(self.adapter.parse_output(output), output)

    def test_get_resource_requirements(self):
        """验证资源需求应包含默认值。"""
        reqs = self.adapter.get_resource_requirements({})
        self.assertEqual(reqs["cpu"], 4)
        self.assertEqual(reqs["memory_mb"], 2048)


class TestEvidenceMapper(unittest.TestCase):
    """evidence_mapper 函数测试。"""

    def test_map_formulation_evidence(self):
        """验证配方优化证据映射。"""
        package = map_formulation_evidence(
            run_id="run-001",
            task_id="task-001",
            formulation_id="f-001",
            property="density",
            value=1.2,
            unit="g/cm³",
        )
        self.assertEqual(package.source_service, "real_engine:formulation_packing")
        self.assertEqual(package.level, EvidenceLevel.MEDIUM)
        self.assertIn("f-001", package.claim)
        self.assertIn("density", package.claim)

    def test_map_packing_evidence(self):
        """验证堆积证据映射。"""
        package = map_packing_evidence(
            run_id="run-001",
            task_id="task-001",
            structure_id="s-001",
            density=1.2,
            energy=-150.0,
        )
        self.assertEqual(package.source_service, "real_engine:formulation_packing")
        self.assertEqual(package.level, EvidenceLevel.MEDIUM)
        self.assertIn("s-001", package.claim)
        self.assertEqual(package.value, {"density": 1.2, "energy": -150.0})


if __name__ == "__main__":
    unittest.main()