"""MPA 服务单元测试 — 分子性质预测服务的完整生命周期验证。"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from battery_materials_agent.contracts.task import Task
from battery_materials_agent.contracts.run import Run
from battery_materials_agent.contracts.artifact import Artifact, ArtifactType
from battery_materials_agent.contracts.evidence import EvidencePackage, EvidenceLevel
from battery_materials_agent.services.mpa.application import (
    MPAApplication,
    MPAAdapter,
    PredictMolecularProperties,
)
from battery_materials_agent.services.mpa.validators import (
    MPAInputValidator,
    validate_smiles,
    validate_property_keys,
    KNOWN_PROPERTY_KEYS,
    PROPERTY_CATALOG,
)
from battery_materials_agent.services.mpa.evidence_mapper import (
    map_property_to_evidence,
    batch_map_evidence,
)
from battery_materials_agent.infrastructure.executors.rdkit_adapter import RDKitAdapter


class TestMPAInputValidator(unittest.TestCase):
    """MPAInputValidator 校验逻辑测试。"""

    def setUp(self):
        self.valid_smiles = ["CCO", "CC(=O)O"]
        self.valid_property_keys = ["MW", "logP", "BP_K"]

    def test_validate_all_with_valid_input(self):
        """验证有效输入应返回 valid=True 且无错误。"""
        validator = MPAInputValidator(
            smiles_list=self.valid_smiles,
            property_keys=self.valid_property_keys,
        )
        result = validator.validate_all()
        self.assertTrue(result["valid"])
        self.assertEqual(len(result["errors"]), 0)
        self.assertIn("valid_smiles", result)
        self.assertIn("valid_property_keys", result)

    def test_validate_all_empty_smiles(self):
        """验证空 SMILES 列表应返回 valid=False。"""
        validator = MPAInputValidator(
            smiles_list=[],
            property_keys=self.valid_property_keys,
        )
        result = validator.validate_all()
        self.assertFalse(result["valid"])
        self.assertIn("SMILES 列表为空", result["errors"])

    def test_validate_all_unknown_property_keys(self):
        """验证未知属性键应产生警告。"""
        validator = MPAInputValidator(
            smiles_list=self.valid_smiles,
            property_keys=["UNKNOWN_KEY", "MW"],
        )
        result = validator.validate_all()
        self.assertTrue(result["valid"])
        self.assertIn("UNKNOWN_KEY", str(result["warnings"]))

    def test_validate_all_temperature_out_of_range(self):
        """验证超出范围的温度应产生警告。"""
        validator = MPAInputValidator(
            smiles_list=self.valid_smiles,
            property_keys=self.valid_property_keys,
            conditions={"temperature": 9999},
        )
        result = validator.validate_all()
        self.assertIn("温度", str(result["warnings"]))

    def test_validate_all_pressure_out_of_range(self):
        """验证超出范围的压力应产生警告。"""
        validator = MPAInputValidator(
            smiles_list=self.valid_smiles,
            property_keys=self.valid_property_keys,
            conditions={"pressure": 99999},
        )
        result = validator.validate_all()
        self.assertIn("压力", str(result["warnings"]))


class TestValidateSmiles(unittest.TestCase):
    """validate_smiles 函数测试。"""

    @patch("rdkit.Chem.MolFromSmiles")
    def test_validate_smiles_valid(self, mock_mol_from_smiles):
        """验证有效 SMILES 应返回正确解析结果。"""
        mock_mol = MagicMock()
        mock_mol_from_smiles.side_effect = [mock_mol, None]

        valid, invalid = validate_smiles(["CCO", "invalid_smiles"])
        self.assertEqual(len(valid), 1)
        self.assertEqual(len(invalid), 1)
        self.assertEqual(valid[0][1], "CCO")

    @patch("rdkit.Chem.MolFromSmiles")
    def test_validate_smiles_all_invalid(self, mock_mol_from_smiles):
        """验证全部无效 SMILES 应返回空 valid 列表。"""
        mock_mol_from_smiles.return_value = None

        valid, invalid = validate_smiles(["bad1", "bad2"])
        self.assertEqual(len(valid), 0)
        self.assertEqual(len(invalid), 2)


class TestValidatePropertyKeys(unittest.TestCase):
    """validate_property_keys 函数测试。"""

    def test_validate_known_keys(self):
        """验证已知属性键应返回 valid 列表。"""
        valid, unknown = validate_property_keys(["MW", "logP", "BP_K"])
        self.assertEqual(len(valid), 3)
        self.assertEqual(len(unknown), 0)

    def test_validate_mixed_keys(self):
        """验证混合已知和未知属性键应正确分离。"""
        valid, unknown = validate_property_keys(["MW", "UNKNOWN1", "logP", "UNKNOWN2"])
        self.assertEqual(len(valid), 2)
        self.assertEqual(len(unknown), 2)

    def test_validate_empty_keys(self):
        """验证空列表应返回空 valid 和 unknown。"""
        valid, unknown = validate_property_keys([])
        self.assertEqual(len(valid), 0)
        self.assertEqual(len(unknown), 0)


class TestPredictMolecularPropertiesModel(unittest.TestCase):
    """PredictMolecularProperties Pydantic 模型测试。"""

    def test_model_creation(self):
        """验证模型创建应正确设置字段值。"""
        cmd = PredictMolecularProperties(
            project_id="proj-001",
            molecule_revision_ids=["CCO"],
            property_keys=["MW", "logP"],
            conditions={"temperature": 298.15},
            model_selection_policy="accuracy",
            require_uncertainty=True,
        )
        self.assertEqual(cmd.project_id, "proj-001")
        self.assertEqual(cmd.molecule_revision_ids, ["CCO"])
        self.assertEqual(cmd.property_keys, ["MW", "logP"])
        self.assertEqual(cmd.conditions, {"temperature": 298.15})
        self.assertEqual(cmd.model_selection_policy, "accuracy")
        self.assertTrue(cmd.require_uncertainty)

    def test_default_property_keys(self):
        """验证默认 property_keys 应包含所有已知键。"""
        cmd = PredictMolecularProperties(
            project_id="proj-001",
            molecule_revision_ids=["CCO"],
        )
        self.assertEqual(set(cmd.property_keys), KNOWN_PROPERTY_KEYS)

    def test_default_conditions(self):
        """验证默认 conditions 应为空字典。"""
        cmd = PredictMolecularProperties(
            project_id="proj-001",
            molecule_revision_ids=["CCO"],
        )
        self.assertEqual(cmd.conditions, {})


class TestMPAApplicationCapability(unittest.TestCase):
    """MPAApplication 能力标识测试。"""

    def setUp(self):
        self.app = MPAApplication(kernel=MagicMock())

    def test_capability_id(self):
        """验证 capability_id 应为 'mpa'。"""
        self.assertEqual(self.app.capability_id, "mpa")

    def test_display_name(self):
        """验证 display_name 应为中文名称。"""
        self.assertEqual(self.app.display_name, "分子性质预测")

    def test_description(self):
        """验证 description 应包含服务描述。"""
        self.assertIn("SMILES", self.app.description)
        self.assertIn("42", self.app.description)


class TestMPAApplicationValidate(unittest.TestCase):
    """MPAApplication.validate 方法测试。"""

    def setUp(self):
        self.app = MPAApplication(kernel=MagicMock())

    def test_validate_valid_input(self):
        """验证有效输入应返回无错误结果。"""
        task = Task(
            project_id="proj-001",
            capability_id="mpa",
            title="test",
            metadata={
                "project_id": "proj-001",
                "molecule_revision_ids": ["CCO"],
                "property_keys": ["MW", "logP"],
            },
        )
        result = self.app.validate(task, {})
        self.assertTrue(result["valid"])

    def test_validate_empty_smiles(self):
        """验证空 SMILES 应返回错误。"""
        task = Task(
            project_id="proj-001",
            capability_id="mpa",
            title="test",
            metadata={
                "project_id": "proj-001",
                "molecule_revision_ids": [],
                "property_keys": ["MW"],
            },
        )
        result = self.app.validate(task, {})
        self.assertFalse(result["valid"])


class TestMPAApplicationPrepare(unittest.TestCase):
    """MPAApplication.prepare 方法测试。"""

    def setUp(self):
        self.app = MPAApplication(kernel=MagicMock())

    def test_prepare_creates_run(self):
        """验证 prepare 应创建正确的 Run 实例。"""
        task = Task(
            task_id="task-001",
            project_id="proj-001",
            capability_id="mpa",
            title="test",
            metadata={
                "project_id": "proj-001",
                "molecule_revision_ids": ["CCO"],
                "property_keys": ["MW"],
            },
        )
        run = self.app.prepare(task)
        self.assertIsInstance(run, Run)
        self.assertEqual(run.task_id, "task-001")
        self.assertEqual(run.service_id, "mpa")
        self.assertEqual(run.command, "predict_molecular_properties")
        self.assertIn("smiles_list", run.input)
        self.assertEqual(run.input["smiles_list"], ["CCO"])


class TestMPAApplicationExecute(unittest.TestCase):
    """MPAApplication.execute 方法测试。"""

    def setUp(self):
        self.app = MPAApplication(kernel=MagicMock())

    def test_execute_returns_artifact_list(self):
        """验证 execute 应返回 Artifact 列表。"""
        run = Run(
            task_id="task-001",
            project_id="proj-001",
            service_id="mpa",
            command="predict_molecular_properties",
            input={
                "smiles_list": ["CCO"],
                "property_keys": ["MW", "logP"],
                "conditions": {},
            },
        )
        artifacts = self.app.execute(run, {})
        self.assertIsInstance(artifacts, list)
        self.assertGreater(len(artifacts), 0)
        self.assertIsInstance(artifacts[0], Artifact)
        self.assertEqual(artifacts[0].type, ArtifactType.RESULT_TABLE)

    def test_execute_with_invalid_smiles(self):
        """验证全部 SMILES 无效时应返回 LOG 类型 Artifact。"""
        run = Run(
            task_id="task-001",
            project_id="proj-001",
            service_id="mpa",
            command="predict_molecular_properties",
            input={
                "smiles_list": ["!!!invalid!!!"],
                "property_keys": ["MW"],
                "conditions": {},
            },
        )
        artifacts = self.app.execute(run, {})
        self.assertEqual(artifacts[0].type, ArtifactType.LOG)
        self.assertIn("error", artifacts[0].data)


class TestMPAApplicationPostprocess(unittest.TestCase):
    """MPAApplication.postprocess 方法测试。"""

    def setUp(self):
        self.app = MPAApplication(kernel=MagicMock())

    def test_postprocess_returns_evidence_packages(self):
        """验证 postprocess 应返回 EvidencePackage 列表。"""
        run = Run(
            run_id="run-001",
            task_id="task-001",
            project_id="proj-001",
            service_id="mpa",
            command="predict_molecular_properties",
        )
        artifacts = [
            Artifact(
                run_id="run-001",
                type=ArtifactType.RESULT_TABLE,
                name="molecular_properties",
                data={
                    "results": [
                        {
                            "mol_id": "CCO",
                            "predictions": {
                                "MW": {"value": 46.07, "confidence": 0.95},
                            },
                        }
                    ]
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
            service_id="mpa",
            command="predict_molecular_properties",
        )
        evidence = self.app.postprocess(run, [])
        self.assertEqual(len(evidence), 0)


class TestMPAApplicationRunFullCycle(unittest.TestCase):
    """MPAApplication.run_full_cycle 完整生命周期测试。"""

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

        app = MPAApplication(kernel=mock_kernel)
        task = Task(
            project_id="proj-001",
            capability_id="mpa",
            title="test",
            metadata={
                "project_id": "proj-001",
                "molecule_revision_ids": ["CCO"],
                "property_keys": ["MW"],
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
        app = MPAApplication(kernel=mock_kernel)
        task = Task(
            project_id="proj-001",
            capability_id="mpa",
            title="test",
            metadata={
                "project_id": "proj-001",
                "molecule_revision_ids": [],
                "property_keys": ["MW"],
            },
        )
        with self.assertRaises(ValueError):
            app.run_full_cycle(task)


class TestMPAAdapter(unittest.TestCase):
    """MPAAdapter 执行适配器测试。"""

    def test_execute_local_rdkit(self):
        """验证 execute 在无远程 API 时使用本地 RDKit 回退。"""
        adapter = MPAAdapter()
        result = adapter.execute({
            "smiles_list": ["CCO"],
            "property_keys": ["MW"],
            "conditions": {},
        })
        self.assertIn("results", result)
        self.assertGreater(len(result["results"]), 0)

    def test_parse_output_dict(self):
        """验证 parse_output 能正确处理 dict 输入。"""
        adapter = MPAAdapter()
        result = adapter.parse_output({"results": [{"mol_id": "CCO"}]})
        self.assertEqual(result["results"][0]["mol_id"], "CCO")

    def test_parse_output_non_dict(self):
        """验证 parse_output 能处理非 dict 输入。"""
        adapter = MPAAdapter()
        result = adapter.parse_output("not a dict")
        self.assertEqual(result, {"results": []})

    def test_get_resource_requirements(self):
        """验证资源需求计算。"""
        adapter = MPAAdapter()
        reqs = adapter.get_resource_requirements({"smiles_list": ["CCO", "CC"]})
        self.assertIn("cpu", reqs)
        self.assertIn("memory_mb", reqs)
        self.assertIn("walltime_minutes", reqs)


class TestRDKitAdapter(unittest.TestCase):
    """RDKitAdapter 执行适配器测试。"""

    def setUp(self):
        self.adapter = RDKitAdapter()

    def test_execute_empty_smiles(self):
        """验证空 SMILES 列表应返回空结果。"""
        result = self.adapter.execute({"smiles_list": [], "property_keys": []})
        self.assertEqual(result, {"results": []})

    def test_parse_output(self):
        """验证 parse_output 应原样返回输入。"""
        output = {"results": [{"smiles": "CCO", "properties": {"MW": 46.07}}]}
        self.assertEqual(self.adapter.parse_output(output), output)

    def test_get_resource_requirements(self):
        """验证资源需求应包含默认值。"""
        reqs = self.adapter.get_resource_requirements({"smiles_list": ["CCO"]})
        self.assertEqual(reqs["cpu"], 1)
        self.assertEqual(reqs["memory_mb"], 512)


class TestEvidenceMapper(unittest.TestCase):
    """evidence_mapper 函数测试。"""

    def test_map_property_to_evidence_high_confidence(self):
        """验证高置信度应映射为 HIGH 级别。"""
        package = map_property_to_evidence(
            run_id="run-001",
            task_id="task-001",
            mol_id="CCO",
            property_name="MW",
            value=46.07,
            confidence=0.95,
        )
        self.assertEqual(package.level, EvidenceLevel.HIGH)
        self.assertEqual(package.source_service, "real_engine:mpa")

    def test_map_property_to_evidence_medium_confidence(self):
        """验证中等置信度应映射为 MEDIUM 级别。"""
        package = map_property_to_evidence(
            run_id="run-001",
            task_id="task-001",
            mol_id="CCO",
            property_name="MW",
            value=46.07,
            confidence=0.80,
        )
        self.assertEqual(package.level, EvidenceLevel.MEDIUM)

    def test_map_property_to_evidence_low_confidence(self):
        """验证低置信度应映射为 LOW 级别。"""
        package = map_property_to_evidence(
            run_id="run-001",
            task_id="task-001",
            mol_id="CCO",
            property_name="MW",
            value=None,
            confidence=0.50,
        )
        self.assertEqual(package.level, EvidenceLevel.LOW)

    def test_batch_map_evidence(self):
        """验证批量映射应返回正确数量的证据包。"""
        results_matrix = [
            {
                "mol_id": "CCO",
                "predictions": {
                    "MW": {"value": 46.07, "confidence": 0.95},
                    "logP": {"value": -0.14, "confidence": 0.90},
                },
            },
            {
                "mol_id": "CC",
                "predictions": {
                    "MW": {"value": 30.07, "confidence": 0.95},
                },
            },
        ]
        packages = batch_map_evidence(
            run_id="run-001",
            task_id="task-001",
            results_matrix=results_matrix,
        )
        self.assertEqual(len(packages), 3)

    def test_batch_map_evidence_empty(self):
        """验证空结果矩阵应返回空列表。"""
        packages = batch_map_evidence(
            run_id="run-001",
            task_id="task-001",
            results_matrix=[],
        )
        self.assertEqual(len(packages), 0)


class TestPropertyCatalog(unittest.TestCase):
    """PROPERTY_CATALOG 完整性测试。"""

    def test_catalog_has_42_properties(self):
        """验证属性目录应包含 43 种性质（42 基础 + h_bond_donors）。"""
        self.assertEqual(len(PROPERTY_CATALOG), 43)

    def test_known_property_keys_match_catalog(self):
        """验证 KNOWN_PROPERTY_KEYS 与 PROPERTY_CATALOG 的键一致。"""
        self.assertEqual(KNOWN_PROPERTY_KEYS, set(PROPERTY_CATALOG.keys()))

    def test_each_property_has_description_and_unit(self):
        """验证每种性质都包含 description 和 unit。"""
        for key, meta in PROPERTY_CATALOG.items():
            with self.subTest(key=key):
                self.assertIn("description", meta)
                self.assertIn("unit", meta)


if __name__ == "__main__":
    unittest.main()