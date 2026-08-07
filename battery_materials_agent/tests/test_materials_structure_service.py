"""材料结构生成与优化服务单元测试 — 验证 generate/optimize 操作生命周期。"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from battery_materials_agent.contracts.task import Task
from battery_materials_agent.contracts.run import Run
from battery_materials_agent.contracts.artifact import Artifact, ArtifactType
from battery_materials_agent.contracts.evidence import EvidencePackage, EvidenceLevel
from battery_materials_agent.services.materials_structure.application import (
    StructureApplication,
    GenerateStructure,
    OptimizeStructure,
    _PlaceholderAdapter,
    _SUPPORTED_OPTIMIZATION_LEVELS,
    _SUPPORTED_FORCE_FIELDS,
)
from battery_materials_agent.services.materials_structure.validators import (
    StructureValidator,
    validate_input_format,
    validate_structure_data,
    SUPPORTED_FORMATS,
)
from battery_materials_agent.services.materials_structure.evidence_mapper import (
    map_structure_evidence,
    batch_map_structure_evidence,
)
from battery_materials_agent.infrastructure.executors.structure_adapter import (
    StructureAdapter,
)


class TestStructureValidator(unittest.TestCase):
    """StructureValidator 校验逻辑测试。"""

    def test_validate_valid_smiles(self):
        """验证有效 SMILES 应无错误。"""
        result = StructureValidator.validate("smiles", "CCO")
        self.assertEqual(len(result["errors"]), 0)

    def test_validate_invalid_format(self):
        """验证无效格式应返回错误。"""
        result = StructureValidator.validate("invalid_format", "CCO")
        self.assertGreater(len(result["errors"]), 0)

    def test_validate_empty_data(self):
        """验证空数据应返回错误。"""
        result = StructureValidator.validate("smiles", "")
        self.assertGreater(len(result["errors"]), 0)

    def test_validate_smiles_too_long_warning(self):
        """验证超长 SMILES 应产生警告。"""
        result = StructureValidator.validate("smiles", "C" * 201)
        self.assertGreater(len(result["warnings"]), 0)

    def test_is_valid_with_valid_input(self):
        """验证 is_valid 对有效输入应返回 True。"""
        self.assertTrue(StructureValidator.is_valid("smiles", "CCO"))

    def test_is_valid_with_invalid_input(self):
        """验证 is_valid 对无效输入应返回 False。"""
        self.assertFalse(StructureValidator.is_valid("smiles", ""))


class TestValidateInputFormat(unittest.TestCase):
    """validate_input_format 函数测试。"""

    def test_valid_formats(self):
        """验证支持的格式应返回标准化小写。"""
        self.assertEqual(validate_input_format("SMILES"), "smiles")
        self.assertEqual(validate_input_format("CIF"), "cif")
        self.assertEqual(validate_input_format("XYZ"), "xyz")

    def test_invalid_format(self):
        """验证不支持的格式应抛出 ValueError。"""
        with self.assertRaises(ValueError):
            validate_input_format("unknown_format")

    def test_supported_formats_set(self):
        """验证支持的格式集合。"""
        self.assertIn("smiles", SUPPORTED_FORMATS)
        self.assertIn("xyz", SUPPORTED_FORMATS)
        self.assertIn("cif", SUPPORTED_FORMATS)
        self.assertIn("mol", SUPPORTED_FORMATS)
        self.assertIn("pdb", SUPPORTED_FORMATS)


class TestValidateStructureData(unittest.TestCase):
    """validate_structure_data 函数测试。"""

    def test_empty_data_raises_error(self):
        """验证空数据应抛出 ValueError。"""
        with self.assertRaises(ValueError):
            validate_structure_data("", "smiles")

    def test_valid_smiles_data(self):
        """验证有效 SMILES 数据应无异常。"""
        try:
            validate_structure_data("CCO", "smiles")
        except ValueError:
            self.fail("validate_structure_data raised ValueError unexpectedly")

    def test_invalid_smiles_characters(self):
        """验证含非法字符的 SMILES 应抛出 ValueError。"""
        with self.assertRaises(ValueError):
            validate_structure_data("CCO!!!", "smiles")


class TestGenerateStructureModel(unittest.TestCase):
    """GenerateStructure Pydantic 模型测试。"""

    def test_model_creation(self):
        """验证模型创建应正确设置字段值。"""
        cmd = GenerateStructure(
            project_id="proj-001",
            input_format="smiles",
            input_data="CCO",
            output_formats=["smiles", "xyz"],
            optimization_level="basic",
            force_field="uff",
        )
        self.assertEqual(cmd.project_id, "proj-001")
        self.assertEqual(cmd.input_format, "smiles")
        self.assertEqual(cmd.input_data, "CCO")
        self.assertEqual(cmd.output_formats, ["smiles", "xyz"])
        self.assertEqual(cmd.optimization_level, "basic")
        self.assertEqual(cmd.force_field, "uff")

    def test_default_output_formats(self):
        """验证默认输出格式应包含所有标准格式。"""
        cmd = GenerateStructure(
            project_id="proj-001",
            input_format="smiles",
            input_data="CCO",
        )
        self.assertIn("smiles", cmd.output_formats)
        self.assertIn("xyz", cmd.output_formats)


class TestOptimizeStructureModel(unittest.TestCase):
    """OptimizeStructure Pydantic 模型测试。"""

    def test_model_creation(self):
        """验证模型创建应正确设置字段值。"""
        cmd = OptimizeStructure(
            project_id="proj-001",
            structure_data="CCO",
            format="smiles",
            optimization_level="full",
            max_iterations=1000,
        )
        self.assertEqual(cmd.project_id, "proj-001")
        self.assertEqual(cmd.structure_data, "CCO")
        self.assertEqual(cmd.format, "smiles")
        self.assertEqual(cmd.optimization_level, "full")
        self.assertEqual(cmd.max_iterations, 1000)


class TestStructureApplicationCapability(unittest.TestCase):
    """StructureApplication 能力标识测试。"""

    def setUp(self):
        self.app = StructureApplication(kernel=MagicMock())

    def test_capability_id(self):
        """验证 capability_id 应为 'materials_structure'。"""
        self.assertEqual(self.app.capability_id, "materials_structure")

    def test_display_name(self):
        """验证 display_name 应为中文名称。"""
        self.assertEqual(self.app.display_name, "材料结构生成与优化")

    def test_description(self):
        """验证 description 应包含服务描述。"""
        self.assertIn("结构生成", self.app.description)
        self.assertIn("优化", self.app.description)


class TestStructureApplicationValidate(unittest.TestCase):
    """StructureApplication.validate 方法测试。"""

    def setUp(self):
        self.app = StructureApplication(kernel=MagicMock())

    def test_validate_generate_valid(self):
        """验证有效的 generate 操作应无错误。"""
        task = Task(
            project_id="proj-001",
            capability_id="materials_structure",
            title="test",
            metadata={
                "operation": "generate",
                "input_format": "smiles",
                "input_data": "CCO",
                "optimization_level": "none",
            },
        )
        result = self.app.validate(task, {})
        self.assertEqual(len(result["errors"]), 0)

    def test_validate_generate_invalid_optimization_level(self):
        """验证不支持的优化级别应返回错误。"""
        task = Task(
            project_id="proj-001",
            capability_id="materials_structure",
            title="test",
            metadata={
                "operation": "generate",
                "input_format": "smiles",
                "input_data": "CCO",
                "optimization_level": "extreme",
            },
        )
        result = self.app.validate(task, {})
        self.assertGreater(len(result["errors"]), 0)

    def test_validate_generate_invalid_force_field(self):
        """验证不支持的力场应返回错误。"""
        task = Task(
            project_id="proj-001",
            capability_id="materials_structure",
            title="test",
            metadata={
                "operation": "generate",
                "input_format": "smiles",
                "input_data": "CCO",
                "optimization_level": "none",
                "force_field": "unknown_ff",
            },
        )
        result = self.app.validate(task, {})
        self.assertGreater(len(result["errors"]), 0)

    def test_validate_optimize_invalid_max_iterations(self):
        """验证 optimize 操作中无效的 max_iterations 应返回错误。"""
        task = Task(
            project_id="proj-001",
            capability_id="materials_structure",
            title="test",
            metadata={
                "operation": "optimize",
                "input_format": "smiles",
                "input_data": "CCO",
                "max_iterations": -1,
            },
        )
        result = self.app.validate(task, {})
        self.assertGreater(len(result["errors"]), 0)

    def test_validate_empty_input_data(self):
        """验证空 input_data 应返回错误。"""
        task = Task(
            project_id="proj-001",
            capability_id="materials_structure",
            title="test",
            metadata={
                "operation": "generate",
                "input_format": "smiles",
                "input_data": "",
            },
        )
        result = self.app.validate(task, {})
        self.assertGreater(len(result["errors"]), 0)

    def test_validate_empty_input_format(self):
        """验证空 input_format 应返回错误。"""
        task = Task(
            project_id="proj-001",
            capability_id="materials_structure",
            title="test",
            metadata={
                "operation": "generate",
                "input_format": "",
                "input_data": "CCO",
            },
        )
        result = self.app.validate(task, {})
        self.assertGreater(len(result["errors"]), 0)


class TestStructureApplicationPrepare(unittest.TestCase):
    """StructureApplication.prepare 方法测试。"""

    def setUp(self):
        self.app = StructureApplication(kernel=MagicMock())

    def test_prepare_creates_run(self):
        """验证 prepare 应创建正确的 Run 实例。"""
        task = Task(
            task_id="task-001",
            project_id="proj-001",
            capability_id="materials_structure",
            title="test",
            metadata={
                "operation": "generate",
                "input_format": "smiles",
                "input_data": "CCO",
            },
        )
        run = self.app.prepare(task)
        self.assertIsInstance(run, Run)
        self.assertEqual(run.task_id, "task-001")
        self.assertEqual(run.service_id, "materials_structure")
        self.assertEqual(run.command, "generate")
        self.assertIn("input_data", run.input)


class TestStructureApplicationExecute(unittest.TestCase):
    """StructureApplication.execute 方法测试。"""

    def setUp(self):
        self.app = StructureApplication(kernel=MagicMock())

    def test_execute_returns_artifacts(self):
        """验证 execute 应返回 Artifact 列表。"""
        run = Run(
            run_id="run-001",
            task_id="task-001",
            project_id="proj-001",
            service_id="materials_structure",
            command="generate",
            input={
                "input_format": "smiles",
                "input_data": "CCO",
                "output_formats": ["smiles", "xyz"],
                "optimization_level": "none",
                "force_field": None,
                "max_iterations": 500,
            },
        )
        artifacts = self.app.execute(run, {})
        self.assertIsInstance(artifacts, list)
        self.assertGreater(len(artifacts), 0)
        self.assertIsInstance(artifacts[0], Artifact)

    def test_execute_returns_structure_artifacts(self):
        """验证 execute 应返回 STRUCTURE 类型工件。"""
        run = Run(
            run_id="run-001",
            task_id="task-001",
            project_id="proj-001",
            service_id="materials_structure",
            command="generate",
            input={
                "input_format": "smiles",
                "input_data": "CCO",
                "output_formats": ["smiles", "xyz"],
                "optimization_level": "none",
                "force_field": None,
                "max_iterations": 500,
            },
        )
        artifacts = self.app.execute(run, {})
        for art in artifacts:
            self.assertIn(art.type, (ArtifactType.STRUCTURE, ArtifactType.RESULT_TABLE))


class TestStructureApplicationPostprocess(unittest.TestCase):
    """StructureApplication.postprocess 方法测试。"""

    def setUp(self):
        self.app = StructureApplication(kernel=MagicMock())

    def test_postprocess_returns_evidence_packages(self):
        """验证 postprocess 应返回 EvidencePackage 列表。"""
        run = Run(
            run_id="run-001",
            task_id="task-001",
            project_id="proj-001",
            service_id="materials_structure",
            command="generate",
        )
        artifacts = [
            Artifact(
                run_id="run-001",
                type=ArtifactType.STRUCTURE,
                name="structure_1",
                data={
                    "structure_id": "gen_smiles",
                    "format": "smiles",
                    "data": "CCO",
                },
            )
        ]
        evidence = self.app.postprocess(run, artifacts)
        self.assertIsInstance(evidence, list)
        self.assertGreater(len(evidence), 0)
        self.assertIsInstance(evidence[0], EvidencePackage)

    def test_postprocess_empty_artifacts(self):
        """验证空工件列表应返回空列表。"""
        run = Run(
            run_id="run-001",
            task_id="task-001",
            project_id="proj-001",
            service_id="materials_structure",
            command="generate",
        )
        evidence = self.app.postprocess(run, [])
        self.assertEqual(len(evidence), 0)


class TestStructureApplicationRunFullCycle(unittest.TestCase):
    """StructureApplication.run_full_cycle 完整生命周期测试。"""

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

        app = StructureApplication(kernel=mock_kernel)
        task = Task(
            project_id="proj-001",
            capability_id="materials_structure",
            title="test",
            metadata={
                "operation": "generate",
                "input_format": "smiles",
                "input_data": "CCO",
            },
        )
        evidence = app.run_full_cycle(task)
        self.assertIsInstance(evidence, list)
        mock_kernel.submit_run.assert_called_once()
        mock_kernel.store_artifact.assert_called()
        mock_kernel.store_evidence.assert_called()


class TestPlaceholderAdapter(unittest.TestCase):
    """_PlaceholderAdapter 占位适配器测试。"""

    def setUp(self):
        self.adapter = _PlaceholderAdapter()

    def test_execute_generate(self):
        """验证 generate 操作应返回结构列表。"""
        result = self.adapter.execute({
            "operation": "generate",
            "input_format": "smiles",
            "input_data": "CCO",
            "output_formats": ["smiles", "xyz"],
        })
        self.assertIn("structures", result)
        self.assertEqual(len(result["structures"]), 2)

    def test_parse_output(self):
        """验证 parse_output 应原样返回 dict 输入。"""
        output = {"structures": []}
        self.assertEqual(self.adapter.parse_output(output), output)

    def test_get_resource_requirements(self):
        """验证资源需求应包含默认值。"""
        reqs = self.adapter.get_resource_requirements({})
        self.assertEqual(reqs["cpu"], 1)
        self.assertEqual(reqs["memory_mb"], 512)


class TestStructureAdapter(unittest.TestCase):
    """StructureAdapter 执行适配器测试。"""

    def setUp(self):
        self.adapter = StructureAdapter()

    def test_execute_unsupported_operation(self):
        """验证不支持的操作应返回错误。"""
        result = self.adapter.execute({"operation": "unknown"})
        self.assertIn("error", result)

    def test_execute_generate_missing_smiles(self):
        """验证 generate 缺少 SMILES 应返回错误。"""
        result = self.adapter.execute({"operation": "generate"})
        self.assertIn("error", result)

    def test_parse_output(self):
        """验证 parse_output 应原样返回输入。"""
        output = {"structures": [{"format": "smiles", "data": "CCO"}]}
        self.assertEqual(self.adapter.parse_output(output), output)

    def test_get_resource_requirements(self):
        """验证资源需求应包含默认值。"""
        reqs = self.adapter.get_resource_requirements({})
        self.assertEqual(reqs["cpu"], 2)
        self.assertEqual(reqs["memory_mb"], 1024)


class TestEvidenceMapper(unittest.TestCase):
    """evidence_mapper 函数测试。"""

    def test_map_structure_evidence(self):
        """验证单个结构映射应返回正确证据包。"""
        package = map_structure_evidence(
            run_id="run-001",
            task_id="task-001",
            structure_id="gen_smiles",
            fmt="smiles",
            data="CCO",
            method="generate",
            confidence=0.95,
        )
        self.assertEqual(package.source_service, "real_engine:materials_structure")
        self.assertEqual(package.level, EvidenceLevel.HIGH)
        self.assertIn("gen_smiles", package.claim)

    def test_map_structure_evidence_medium_confidence(self):
        """验证中等置信度应映射为 MEDIUM 级别。"""
        package = map_structure_evidence(
            run_id="run-001",
            task_id="task-001",
            structure_id="test",
            fmt="xyz",
            data="xyz data",
            confidence=0.80,
        )
        self.assertEqual(package.level, EvidenceLevel.MEDIUM)

    def test_batch_map_structure_evidence(self):
        """验证批量映射应返回正确数量的证据包。"""
        structures = [
            {"structure_id": "s1", "format": "smiles", "data": "CCO"},
            {"structure_id": "s2", "format": "xyz", "data": "xyz data"},
        ]
        packages = batch_map_structure_evidence(
            run_id="run-001",
            task_id="task-001",
            structures=structures,
            method="generate",
        )
        self.assertEqual(len(packages), 2)

    def test_batch_map_structure_evidence_empty(self):
        """验证空结构列表应返回空列表。"""
        packages = batch_map_structure_evidence(
            run_id="run-001",
            task_id="task-001",
            structures=[],
        )
        self.assertEqual(len(packages), 0)


class TestSupportedConstants(unittest.TestCase):
    """支持常量测试。"""

    def test_supported_optimization_levels(self):
        """验证支持的优化级别。"""
        self.assertIn("none", _SUPPORTED_OPTIMIZATION_LEVELS)
        self.assertIn("basic", _SUPPORTED_OPTIMIZATION_LEVELS)
        self.assertIn("full", _SUPPORTED_OPTIMIZATION_LEVELS)

    def test_supported_force_fields(self):
        """验证支持的力场。"""
        self.assertIn("uff", _SUPPORTED_FORCE_FIELDS)
        self.assertIn("mmff94", _SUPPORTED_FORCE_FIELDS)


if __name__ == "__main__":
    unittest.main()