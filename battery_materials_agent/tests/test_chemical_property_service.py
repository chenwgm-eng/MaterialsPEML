"""化学性质查询服务单元测试 — 验证 5 个模块的完整生命周期。"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from battery_materials_agent.contracts.task import Task
from battery_materials_agent.contracts.run import Run
from battery_materials_agent.contracts.artifact import Artifact, ArtifactType
from battery_materials_agent.contracts.evidence import EvidencePackage, EvidenceLevel
from battery_materials_agent.services.chemical_property.application import (
    ChemicalPropertyApplication,
    QueryChemicalProperty,
    MODULE_CATALOG,
)
from battery_materials_agent.services.chemical_property.validators import (
    ChemicalPropertyValidator,
    validate_compound_name,
    validate_module_parameters,
    VALID_MODULES,
    MODULE_NAMES,
)
from battery_materials_agent.services.chemical_property.evidence_mapper import (
    map_chemical_evidence,
    batch_map_chemical_evidence,
)
from battery_materials_agent.infrastructure.executors.chemicals_adapter import (
    ChemicalsAdapter,
)


class TestChemicalPropertyValidator(unittest.TestCase):
    """ChemicalPropertyValidator 校验逻辑测试。"""

    def test_validate_all_valid_m1(self):
        """验证有效的 M1 模块输入应返回 validated=True。"""
        result = ChemicalPropertyValidator.validate_all(
            compound_name="ethanol",
            module="M1",
        )
        self.assertTrue(result["validated"])
        self.assertEqual(len(result["errors"]), 0)

    def test_validate_all_valid_m2_with_temperature(self):
        """验证 M2 模块提供温度应通过校验。"""
        result = ChemicalPropertyValidator.validate_all(
            compound_name="ethanol",
            module="M2",
            temperature_k=298.15,
        )
        self.assertTrue(result["validated"])

    def test_validate_all_m2_missing_params(self):
        """验证 M2 模块缺少温度/压力应返回错误。"""
        result = ChemicalPropertyValidator.validate_all(
            compound_name="ethanol",
            module="M2",
        )
        self.assertFalse(result["validated"])
        self.assertTrue(any("temperature_k" in e or "pressure_pa" in e for e in result["errors"]))

    def test_validate_all_m3_missing_composition(self):
        """验证 M3 模块缺少 composition 应返回错误。"""
        result = ChemicalPropertyValidator.validate_all(
            compound_name="ethanol/water",
            module="M3",
        )
        self.assertFalse(result["validated"])
        self.assertTrue(any("composition" in e for e in result["errors"]))

    def test_validate_all_m3_invalid_composition_sum(self):
        """验证 M3 模块 composition 之和不等于 1 应返回错误。"""
        result = ChemicalPropertyValidator.validate_all(
            compound_name="ethanol/water",
            module="M3",
            composition=[0.5, 0.3],
        )
        self.assertFalse(result["validated"])

    def test_validate_all_m4_missing_params(self):
        """验证 M4 模块缺少温度、压力、composition 应返回错误。"""
        result = ChemicalPropertyValidator.validate_all(
            compound_name="ethanol/water",
            module="M4",
        )
        self.assertFalse(result["validated"])
        self.assertGreaterEqual(len(result["errors"]), 2)

    def test_validate_all_invalid_module(self):
        """验证无效模块标识应返回错误。"""
        result = ChemicalPropertyValidator.validate_all(
            compound_name="ethanol",
            module="M6",
        )
        self.assertFalse(result["validated"])

    def test_validate_all_empty_compound_name(self):
        """验证空化合物名称应返回错误。"""
        result = ChemicalPropertyValidator.validate_all(
            compound_name="",
            module="M1",
        )
        self.assertFalse(result["validated"])
        self.assertTrue(any("不能为空" in e for e in result["errors"]))

    def test_validate_all_long_compound_name(self):
        """验证过长的化合物名称应返回错误。"""
        result = ChemicalPropertyValidator.validate_all(
            compound_name="A" * 201,
            module="M1",
        )
        self.assertFalse(result["validated"])
        self.assertTrue(any("过长" in e for e in result["errors"]))


class TestValidateCompoundName(unittest.TestCase):
    """validate_compound_name 函数测试。"""

    def test_valid_name(self):
        """验证有效化合物名称应返回 None。"""
        self.assertIsNone(validate_compound_name("ethanol"))
        self.assertIsNone(validate_compound_name("C2H5OH"))
        self.assertIsNone(validate_compound_name("Sodium Chloride"))

    def test_empty_name(self):
        """验证空名称应返回错误信息。"""
        self.assertIsNotNone(validate_compound_name(""))
        self.assertIsNotNone(validate_compound_name("   "))

    def test_too_long_name(self):
        """验证超长名称应返回错误信息。"""
        self.assertIsNotNone(validate_compound_name("A" * 201))


class TestValidateModuleParameters(unittest.TestCase):
    """validate_module_parameters 函数测试。"""

    def test_invalid_module(self):
        """验证无效模块应返回错误。"""
        errors = validate_module_parameters("M6")
        self.assertGreater(len(errors), 0)

    def test_m1_no_params_needed(self):
        """验证 M1 模块不需要额外参数。"""
        errors = validate_module_parameters("M1")
        self.assertEqual(len(errors), 0)

    def test_m5_no_params_needed(self):
        """验证 M5 模块不需要额外参数。"""
        errors = validate_module_parameters("M5")
        self.assertEqual(len(errors), 0)

    def test_m2_valid_temperature(self):
        """验证 M2 模块有效温度应无错误。"""
        errors = validate_module_parameters("M2", temperature_k=298.15)
        self.assertEqual(len(errors), 0)

    def test_m2_invalid_temperature_range(self):
        """验证 M2 模块温度超出范围应返回错误。"""
        errors = validate_module_parameters("M2", temperature_k=-10)
        self.assertGreater(len(errors), 0)

    def test_m3_valid_composition(self):
        """验证 M3 模块有效 composition 应无错误。"""
        errors = validate_module_parameters("M3", composition=[0.4, 0.6])
        self.assertEqual(len(errors), 0)


class TestQueryChemicalPropertyModel(unittest.TestCase):
    """QueryChemicalProperty Pydantic 模型测试。"""

    def test_model_creation_m1(self):
        """验证 M1 查询模型创建。"""
        query = QueryChemicalProperty(
            project_id="proj-001",
            compound_name="ethanol",
            module="M1",
        )
        self.assertEqual(query.project_id, "proj-001")
        self.assertEqual(query.compound_name, "ethanol")
        self.assertEqual(query.module, "M1")

    def test_model_creation_m4(self):
        """验证 M4 闪蒸查询模型创建。"""
        query = QueryChemicalProperty(
            project_id="proj-001",
            compound_name="ethanol/water",
            module="M4",
            temperature_k=373.15,
            pressure_pa=101325.0,
            composition=[0.5, 0.5],
        )
        self.assertEqual(query.module, "M4")
        self.assertEqual(query.temperature_k, 373.15)
        self.assertEqual(query.composition, [0.5, 0.5])


class TestChemicalPropertyApplicationCapability(unittest.TestCase):
    """ChemicalPropertyApplication 能力标识测试。"""

    def setUp(self):
        self.app = ChemicalPropertyApplication(kernel=MagicMock())

    def test_capability_id(self):
        """验证 capability_id 应为 'chem_properties'。"""
        self.assertEqual(self.app.capability_id, "chem_properties")

    def test_display_name(self):
        """验证 display_name 应为中文名称。"""
        self.assertEqual(self.app.display_name, "化学性质查询")

    def test_description(self):
        """验证 description 应包含模块描述。"""
        self.assertIn("标准常数", self.app.description)
        self.assertIn("溶解度", self.app.description)


class TestChemicalPropertyApplicationValidate(unittest.TestCase):
    """ChemicalPropertyApplication.validate 方法测试。"""

    def setUp(self):
        self.app = ChemicalPropertyApplication(kernel=MagicMock())

    def test_validate_m1_valid(self):
        """验证 M1 模块有效输入应返回 validated=True。"""
        task = Task(
            project_id="proj-001",
            capability_id="chem_properties",
            title="test",
            metadata={
                "compound_name": "ethanol",
                "module": "M1",
            },
        )
        result = self.app.validate(task, {})
        self.assertTrue(result["validated"])

    def test_validate_m2_missing_params(self):
        """验证 M2 模块缺少参数应返回错误。"""
        task = Task(
            project_id="proj-001",
            capability_id="chem_properties",
            title="test",
            metadata={
                "compound_name": "ethanol",
                "module": "M2",
            },
        )
        result = self.app.validate(task, {})
        self.assertFalse(result["validated"])

    def test_validate_m4_valid(self):
        """验证 M4 模块有效输入应返回 validated=True。"""
        task = Task(
            project_id="proj-001",
            capability_id="chem_properties",
            title="test",
            metadata={
                "compound_name": "ethanol/water",
                "module": "M4",
                "temperature_k": 373.15,
                "pressure_pa": 101325.0,
                "composition": [0.5, 0.5],
            },
        )
        result = self.app.validate(task, {})
        self.assertTrue(result["validated"])

    def test_validate_invalid_module(self):
        """验证无效模块应返回错误。"""
        task = Task(
            project_id="proj-001",
            capability_id="chem_properties",
            title="test",
            metadata={
                "compound_name": "ethanol",
                "module": "M99",
            },
        )
        result = self.app.validate(task, {})
        self.assertFalse(result["validated"])


class TestChemicalPropertyApplicationPrepare(unittest.TestCase):
    """ChemicalPropertyApplication.prepare 方法测试。"""

    def setUp(self):
        self.app = ChemicalPropertyApplication(kernel=MagicMock())

    def test_prepare_creates_run(self):
        """验证 prepare 应创建正确的 Run 实例。"""
        task = Task(
            task_id="task-001",
            project_id="proj-001",
            capability_id="chem_properties",
            title="test",
            metadata={
                "compound_name": "ethanol",
                "module": "M1",
            },
        )
        run = self.app.prepare(task)
        self.assertIsInstance(run, Run)
        self.assertEqual(run.task_id, "task-001")
        self.assertEqual(run.service_id, "chem_properties")
        self.assertIn("M1", run.command)


class TestChemicalPropertyApplicationExecute(unittest.TestCase):
    """ChemicalPropertyApplication.execute 方法测试。"""

    def setUp(self):
        self.app = ChemicalPropertyApplication(kernel=MagicMock())

    def test_execute_m1_returns_artifact(self):
        """验证 M1 模块 execute 应返回 Artifact 列表。"""
        run = Run(
            run_id="run-001",
            task_id="task-001",
            project_id="proj-001",
            service_id="chem_properties",
            command="query_chemical_property M1 ethanol",
            input={
                "module": "M1",
                "compound_name": "ethanol",
            },
        )
        artifacts = self.app.execute(run, {})
        self.assertIsInstance(artifacts, list)
        self.assertGreater(len(artifacts), 0)
        self.assertIsInstance(artifacts[0], Artifact)
        self.assertEqual(artifacts[0].type, ArtifactType.RESULT_TABLE)

    def test_execute_m2_returns_artifact(self):
        """验证 M2 模块 execute 应返回包含 T/P 依赖性质的结果。"""
        run = Run(
            run_id="run-001",
            task_id="task-001",
            project_id="proj-001",
            service_id="chem_properties",
            command="query_chemical_property M2 ethanol",
            input={
                "module": "M2",
                "compound_name": "ethanol",
                "temperature_k": 298.15,
                "pressure_pa": 101325.0,
            },
        )
        artifacts = self.app.execute(run, {})
        data = artifacts[0].data
        self.assertIn("results", data)
        self.assertGreater(len(data["results"]), 0)

    def test_execute_m3_returns_artifact(self):
        """验证 M3 模块 execute 应返回 VLE 结果。"""
        run = Run(
            run_id="run-001",
            task_id="task-001",
            project_id="proj-001",
            service_id="chem_properties",
            command="query_chemical_property M3 ethanol/water",
            input={
                "module": "M3",
                "compound_name": "ethanol/water",
                "composition": [0.4, 0.6],
                "temperature_k": 353.15,
            },
        )
        artifacts = self.app.execute(run, {})
        data = artifacts[0].data
        self.assertIn("results", data)

    def test_execute_m4_returns_artifact(self):
        """验证 M4 模块 execute 应返回闪蒸结果。"""
        run = Run(
            run_id="run-001",
            task_id="task-001",
            project_id="proj-001",
            service_id="chem_properties",
            command="query_chemical_property M4 ethanol/water",
            input={
                "module": "M4",
                "compound_name": "ethanol/water",
                "composition": [0.5, 0.5],
                "temperature_k": 373.15,
                "pressure_pa": 101325.0,
            },
        )
        artifacts = self.app.execute(run, {})
        data = artifacts[0].data
        self.assertIn("results", data)

    def test_execute_m5_returns_artifact(self):
        """验证 M5 模块 execute 应返回溶解度结果。"""
        run = Run(
            run_id="run-001",
            task_id="task-001",
            project_id="proj-001",
            service_id="chem_properties",
            command="query_chemical_property M5 ethanol",
            input={
                "module": "M5",
                "compound_name": "ethanol",
            },
        )
        artifacts = self.app.execute(run, {})
        data = artifacts[0].data
        self.assertIn("results", data)

    def test_execute_unknown_module(self):
        """验证未知模块应返回错误信息。"""
        run = Run(
            run_id="run-001",
            task_id="task-001",
            project_id="proj-001",
            service_id="chem_properties",
            command="query_chemical_property M99 unknown",
            input={
                "module": "M99",
                "compound_name": "unknown",
            },
        )
        artifacts = self.app.execute(run, {})
        self.assertIn("error", str(artifacts[0].data))


class TestChemicalPropertyApplicationPostprocess(unittest.TestCase):
    """ChemicalPropertyApplication.postprocess 方法测试。"""

    def setUp(self):
        self.app = ChemicalPropertyApplication(kernel=MagicMock())

    def test_postprocess_returns_evidence_packages(self):
        """验证 postprocess 应返回 EvidencePackage 列表。"""
        run = Run(
            run_id="run-001",
            task_id="task-001",
            project_id="proj-001",
            service_id="chem_properties",
            command="query_chemical_property M1 ethanol",
        )
        artifacts = [
            Artifact(
                run_id="run-001",
                type=ArtifactType.RESULT_TABLE,
                name="chemical_properties_M1",
                data={
                    "results": [
                        {"property_name": "分子量", "value": 46.07, "unit": "g/mol", "confidence": 0.95},
                        {"property_name": "沸点", "value": 351.15, "unit": "K", "confidence": 0.90},
                    ],
                },
            )
        ]
        evidence = self.app.postprocess(run, artifacts)
        self.assertIsInstance(evidence, list)
        self.assertGreater(len(evidence), 0)
        self.assertIsInstance(evidence[0], EvidencePackage)

    def test_postprocess_artifact_without_data(self):
        """验证 data 为 None 的 Artifact 应被跳过。"""
        run = Run(
            run_id="run-001",
            task_id="task-001",
            project_id="proj-001",
            service_id="chem_properties",
            command="query_chemical_property M1 ethanol",
        )
        artifacts = [Artifact(run_id="run-001", type=ArtifactType.RESULT_TABLE, name="empty", data=None)]
        evidence = self.app.postprocess(run, artifacts)
        self.assertEqual(len(evidence), 0)


class TestChemicalPropertyApplicationRunFullCycle(unittest.TestCase):
    """ChemicalPropertyApplication.run_full_cycle 完整生命周期测试。"""

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

        app = ChemicalPropertyApplication(kernel=mock_kernel)
        task = Task(
            project_id="proj-001",
            capability_id="chem_properties",
            title="test",
            metadata={
                "compound_name": "ethanol",
                "module": "M1",
            },
        )
        evidence = app.run_full_cycle(task)
        self.assertIsInstance(evidence, list)
        mock_kernel.submit_run.assert_called_once()
        mock_kernel.store_artifact.assert_called()
        mock_kernel.store_evidence.assert_called()


class TestChemicalsAdapter(unittest.TestCase):
    """ChemicalsAdapter 执行适配器测试。"""

    def setUp(self):
        self.adapter = ChemicalsAdapter()

    def test_execute_m1_missing_identifier(self):
        """验证缺少标识符应返回错误。"""
        result = self.adapter.execute({"module": "M1", "identifier": ""})
        # error 可能位于顶层或嵌套在 results 中
        if "error" in result:
            pass
        elif "results" in result and isinstance(result["results"], dict):
            self.assertIn("error", result["results"])
        else:
            self.fail("应返回 error 字段")

    def test_execute_m1_with_identifier(self):
        """验证 M1 模块执行应返回结果。"""
        result = self.adapter.execute({"module": "M1", "identifier": "ethanol", "constants": ["MW", "Tb"]})
        self.assertEqual(result["module"], "M1")
        self.assertIn("results", result)

    def test_execute_unknown_module(self):
        """验证未知模块应返回错误。"""
        result = self.adapter.execute({"module": "M99", "identifier": "ethanol"})
        self.assertIn("error", result)

    def test_parse_output(self):
        """验证 parse_output 应原样返回输入。"""
        output = {"module": "M1", "results": {}}
        self.assertEqual(self.adapter.parse_output(output), output)

    def test_get_resource_requirements(self):
        """验证资源需求应包含默认值。"""
        reqs = self.adapter.get_resource_requirements({})
        self.assertEqual(reqs["cpu"], 1)
        self.assertEqual(reqs["memory_mb"], 256)


class TestEvidenceMapper(unittest.TestCase):
    """evidence_mapper 函数测试。"""

    def test_map_chemical_evidence_high_confidence(self):
        """验证高置信度应映射为 HIGH 级别。"""
        package = map_chemical_evidence(
            run_id="run-001",
            task_id="task-001",
            property_name="分子量",
            value=46.07,
            unit="g/mol",
            source="DIPPR",
            confidence=0.95,
        )
        self.assertEqual(package.level, EvidenceLevel.HIGH)
        self.assertEqual(package.source_service, "real_engine:chem_properties")

    def test_map_chemical_evidence_medium_confidence(self):
        """验证中等置信度应映射为 MEDIUM 级别。"""
        package = map_chemical_evidence(
            run_id="run-001",
            task_id="task-001",
            property_name="密度",
            value=789.0,
            unit="kg/m³",
            confidence=0.80,
        )
        self.assertEqual(package.level, EvidenceLevel.MEDIUM)

    def test_batch_map_chemical_evidence(self):
        """验证批量映射应返回正确数量的证据包。"""
        results = [
            {"property_name": "分子量", "value": 46.07, "unit": "g/mol", "confidence": 0.95},
            {"property_name": "沸点", "value": 351.15, "unit": "K", "confidence": 0.90},
        ]
        packages = batch_map_chemical_evidence(
            run_id="run-001",
            task_id="task-001",
            results=results,
        )
        self.assertEqual(len(packages), 2)

    def test_batch_map_chemical_evidence_empty(self):
        """验证空结果列表应返回空列表。"""
        packages = batch_map_chemical_evidence(
            run_id="run-001",
            task_id="task-001",
            results=[],
        )
        self.assertEqual(len(packages), 0)


class TestModuleCatalog(unittest.TestCase):
    """MODULE_CATALOG 完整性测试。"""

    def test_catalog_has_five_modules(self):
        """验证模块目录应包含 5 个模块。"""
        self.assertEqual(len(MODULE_CATALOG), 5)

    def test_each_module_has_name_and_description(self):
        """验证每个模块都包含 name 和 description。"""
        for key, meta in MODULE_CATALOG.items():
            with self.subTest(key=key):
                self.assertIn("name", meta)
                self.assertIn("description", meta)

    def test_valid_modules_set(self):
        """验证 VALID_MODULES 包含 M1-M5。"""
        self.assertEqual(VALID_MODULES, frozenset({"M1", "M2", "M3", "M4", "M5"}))

    def test_module_names_mapping(self):
        """验证 MODULE_NAMES 映射的正确性。"""
        self.assertEqual(MODULE_NAMES["M1"], "标准常数")
        self.assertEqual(MODULE_NAMES["M5"], "溶解度")


if __name__ == "__main__":
    unittest.main()