"""合成路线规划服务单元测试 — 完整生命周期验证。"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from battery_materials_agent.contracts.task import Task
from battery_materials_agent.contracts.run import Run
from battery_materials_agent.contracts.artifact import Artifact, ArtifactType
from battery_materials_agent.contracts.evidence import EvidencePackage, EvidenceLevel
from battery_materials_agent.services.synthesis_planning.application import (
    SynthesisPlanningApplication,
    PlanSynthesis,
)
from battery_materials_agent.services.synthesis_planning.validators import (
    SynthesisInputValidator,
    validate_target_smiles,
    validate_search_depth,
    validate_max_paths,
    validate_expansion_timeout,
)
from battery_materials_agent.services.synthesis_planning.evidence_mapper import (
    map_route_evidence,
    map_stats_evidence,
    map_normalization_evidence,
    map_error_evidence,
    batch_map_routes,
    EVIDENCE_GRADE_DESCRIPTIONS,
)


class TestSynthesisInputValidator(unittest.TestCase):
    """SynthesisInputValidator 校验逻辑测试。"""

    def setUp(self):
        self.valid_smiles = "CCO"
        self.valid_depth = 3
        self.valid_max_paths = 10
        self.valid_timeout = 300

    @patch("rdkit.Chem.MolFromSmiles")
    def test_validate_all_with_valid_input(self, mock_mol_from_smiles):
        """验证有效输入应返回 valid=True 且无错误。"""
        mock_mol = MagicMock()
        mock_mol_from_smiles.return_value = mock_mol

        validator = SynthesisInputValidator(
            target_smiles=self.valid_smiles,
            search_depth=self.valid_depth,
            max_paths=self.valid_max_paths,
            expansion_timeout=self.valid_timeout,
        )
        result = validator.validate_all()
        self.assertTrue(result["valid"])
        self.assertEqual(len(result["errors"]), 0)
        self.assertIn("normalized_smiles", result)

    @patch("rdkit.Chem.MolFromSmiles")
    def test_validate_all_invalid_smiles(self, mock_mol_from_smiles):
        """验证无效 SMILES 应返回 valid=False。"""
        mock_mol_from_smiles.return_value = None

        validator = SynthesisInputValidator(
            target_smiles="!!!invalid!!!",
            search_depth=self.valid_depth,
            max_paths=self.valid_max_paths,
            expansion_timeout=self.valid_timeout,
        )
        result = validator.validate_all()
        self.assertFalse(result["valid"])
        self.assertIn("无效的 SMILES", str(result["errors"]))

    def test_validate_all_search_depth_out_of_range(self):
        """验证超出范围的搜索深度应返回错误。"""
        validator = SynthesisInputValidator(
            target_smiles=self.valid_smiles,
            search_depth=99,
            max_paths=self.valid_max_paths,
            expansion_timeout=self.valid_timeout,
        )
        result = validator.validate_all()
        self.assertFalse(result["valid"])
        self.assertIn("搜索深度", str(result["errors"]))

    def test_validate_all_max_paths_out_of_range(self):
        """验证超出范围的最大路线数应返回错误。"""
        validator = SynthesisInputValidator(
            target_smiles=self.valid_smiles,
            search_depth=self.valid_depth,
            max_paths=999,
            expansion_timeout=self.valid_timeout,
        )
        result = validator.validate_all()
        self.assertFalse(result["valid"])
        self.assertIn("最大路线数", str(result["errors"]))

    def test_validate_all_expansion_timeout_out_of_range(self):
        """验证超出范围的超时时间应返回错误。"""
        validator = SynthesisInputValidator(
            target_smiles=self.valid_smiles,
            search_depth=self.valid_depth,
            max_paths=self.valid_max_paths,
            expansion_timeout=5,
        )
        result = validator.validate_all()
        self.assertFalse(result["valid"])
        self.assertIn("扩展超时", str(result["errors"]))

    def test_validate_all_depth_timeout_warning(self):
        """验证深度大且超时短时应产生警告。"""
        validator = SynthesisInputValidator(
            target_smiles=self.valid_smiles,
            search_depth=8,
            max_paths=self.valid_max_paths,
            expansion_timeout=60,
        )
        result = validator.validate_all()
        self.assertGreater(len(result["warnings"]), 0)
        self.assertIn("搜索深度", str(result["warnings"]))

    def test_validate_all_empty_smiles(self):
        """验证空 SMILES 应返回错误。"""
        validator = SynthesisInputValidator(
            target_smiles="",
            search_depth=self.valid_depth,
            max_paths=self.valid_max_paths,
            expansion_timeout=self.valid_timeout,
        )
        result = validator.validate_all()
        self.assertFalse(result["valid"])
        self.assertIn("不能为空", str(result["errors"]))


class TestValidateTargetSmiles(unittest.TestCase):
    """validate_target_smiles 函数测试。"""

    @patch("rdkit.Chem.MolFromSmiles")
    def test_validate_valid_smiles(self, mock_mol_from_smiles):
        """验证有效 SMILES 应返回 (True, None)。"""
        mock_mol = MagicMock()
        mock_mol_from_smiles.return_value = mock_mol

        valid, err = validate_target_smiles("CCO")
        self.assertTrue(valid)
        self.assertIsNone(err)

    @patch("rdkit.Chem.MolFromSmiles")
    def test_validate_invalid_smiles(self, mock_mol_from_smiles):
        """验证无效 SMILES 应返回错误信息。"""
        mock_mol_from_smiles.return_value = None

        valid, err = validate_target_smiles("!!!invalid!!!")
        self.assertFalse(valid)
        self.assertIsNotNone(err)
        self.assertIn("无效的 SMILES", err)

    def test_validate_empty_smiles(self):
        """验证空 SMILES 应返回错误。"""
        valid, err = validate_target_smiles("")
        self.assertFalse(valid)
        self.assertIn("不能为空", err)

    def test_validate_rdkit_import_error(self):
        """验证 RDKit 不可用时使用正则兜底。"""
        import builtins

        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "rdkit":
                raise ImportError(f"No module named {name}")
            return real_import(name, *args, **kwargs)

        with patch.object(builtins, "__import__", side_effect=mock_import):
            valid, err = validate_target_smiles("CCO")
            self.assertTrue(valid)
            self.assertIsNone(err)


class TestValidateSearchDepth(unittest.TestCase):
    """validate_search_depth 函数测试。"""

    def test_valid_depth(self):
        """验证有效深度应返回 (True, None)。"""
        valid, err = validate_search_depth(3)
        self.assertTrue(valid)
        self.assertIsNone(err)

    def test_depth_too_low(self):
        """验证深度过低应返回错误。"""
        valid, err = validate_search_depth(0)
        self.assertFalse(valid)
        self.assertIn("搜索深度", err)

    def test_depth_too_high(self):
        """验证深度过高应返回错误。"""
        valid, err = validate_search_depth(11)
        self.assertFalse(valid)
        self.assertIn("搜索深度", err)

    def test_depth_non_integer(self):
        """验证非整数深度应返回错误。"""
        valid, err = validate_search_depth(3.5)
        self.assertFalse(valid)
        self.assertIn("搜索深度", err)

    def test_depth_boundary_low(self):
        """验证边界深度 1 应通过。"""
        valid, err = validate_search_depth(1)
        self.assertTrue(valid)
        self.assertIsNone(err)

    def test_depth_boundary_high(self):
        """验证边界深度 10 应通过。"""
        valid, err = validate_search_depth(10)
        self.assertTrue(valid)
        self.assertIsNone(err)


class TestValidateMaxPaths(unittest.TestCase):
    """validate_max_paths 函数测试。"""

    def test_valid_max_paths(self):
        """验证有效路线数应返回 (True, None)。"""
        valid, err = validate_max_paths(10)
        self.assertTrue(valid)
        self.assertIsNone(err)

    def test_max_paths_too_low(self):
        """验证路线数过低应返回错误。"""
        valid, err = validate_max_paths(0)
        self.assertFalse(valid)
        self.assertIn("最大路线数", err)

    def test_max_paths_too_high(self):
        """验证路线数过高应返回错误。"""
        valid, err = validate_max_paths(101)
        self.assertFalse(valid)
        self.assertIn("最大路线数", err)

    def test_max_paths_non_integer(self):
        """验证非整数路线数应返回错误。"""
        valid, err = validate_max_paths(10.5)
        self.assertFalse(valid)
        self.assertIn("最大路线数", err)

    def test_max_paths_boundary_low(self):
        """验证边界路线数 1 应通过。"""
        valid, err = validate_max_paths(1)
        self.assertTrue(valid)
        self.assertIsNone(err)

    def test_max_paths_boundary_high(self):
        """验证边界路线数 100 应通过。"""
        valid, err = validate_max_paths(100)
        self.assertTrue(valid)
        self.assertIsNone(err)


class TestValidateExpansionTimeout(unittest.TestCase):
    """validate_expansion_timeout 函数测试。"""

    def test_valid_timeout(self):
        """验证有效超时应返回 (True, None)。"""
        valid, err = validate_expansion_timeout(300)
        self.assertTrue(valid)
        self.assertIsNone(err)

    def test_timeout_too_low(self):
        """验证超时过低应返回错误。"""
        valid, err = validate_expansion_timeout(29)
        self.assertFalse(valid)
        self.assertIn("扩展超时", err)

    def test_timeout_too_high(self):
        """验证超时过高应返回错误。"""
        valid, err = validate_expansion_timeout(1801)
        self.assertFalse(valid)
        self.assertIn("扩展超时", err)

    def test_timeout_non_integer(self):
        """验证非整数超时应返回错误。"""
        valid, err = validate_expansion_timeout(300.5)
        self.assertFalse(valid)
        self.assertIn("扩展超时", err)

    def test_timeout_boundary_low(self):
        """验证边界超时 30 应通过。"""
        valid, err = validate_expansion_timeout(30)
        self.assertTrue(valid)
        self.assertIsNone(err)

    def test_timeout_boundary_high(self):
        """验证边界超时 1800 应通过。"""
        valid, err = validate_expansion_timeout(1800)
        self.assertTrue(valid)
        self.assertIsNone(err)


class TestPlanSynthesisModel(unittest.TestCase):
    """PlanSynthesis Pydantic 模型测试。"""

    def test_model_creation(self):
        """验证模型创建应正确设置字段值。"""
        cmd = PlanSynthesis(
            project_id="proj-001",
            target_smiles="CCO",
            search_depth=5,
            max_paths=20,
            normalize_ions=False,
            include_literature=False,
            expansion_timeout=600,
        )
        self.assertEqual(cmd.project_id, "proj-001")
        self.assertEqual(cmd.target_smiles, "CCO")
        self.assertEqual(cmd.search_depth, 5)
        self.assertEqual(cmd.max_paths, 20)
        self.assertFalse(cmd.normalize_ions)
        self.assertFalse(cmd.include_literature)
        self.assertEqual(cmd.expansion_timeout, 600)

    def test_default_values(self):
        """验证默认值应正确设置。"""
        cmd = PlanSynthesis(
            project_id="proj-001",
            target_smiles="CCO",
        )
        self.assertEqual(cmd.search_depth, 3)
        self.assertEqual(cmd.max_paths, 10)
        self.assertTrue(cmd.normalize_ions)
        self.assertTrue(cmd.include_literature)
        self.assertEqual(cmd.expansion_timeout, 300)


class TestSynthesisPlanningApplicationCapability(unittest.TestCase):
    """SynthesisPlanningApplication 能力标识测试。"""

    def setUp(self):
        self.app = SynthesisPlanningApplication(kernel=MagicMock())

    def test_capability_id(self):
        """验证 capability_id 应为 'synthesis_planning'。"""
        self.assertEqual(self.app.capability_id, "synthesis_planning")

    def test_display_name(self):
        """验证 display_name 应为中文名称。"""
        self.assertEqual(self.app.display_name, "合成路线规划")

    def test_description(self):
        """验证 description 应包含服务描述。"""
        self.assertIn("ReactNavi", self.app.description)
        self.assertIn("逆合成", self.app.description)


class TestSynthesisPlanningApplicationValidate(unittest.TestCase):
    """SynthesisPlanningApplication.validate 方法测试。"""

    def setUp(self):
        self.app = SynthesisPlanningApplication(kernel=MagicMock())

    @patch("rdkit.Chem.MolFromSmiles")
    def test_validate_valid_input(self, mock_mol_from_smiles):
        """验证有效输入应返回无错误结果。"""
        mock_mol = MagicMock()
        mock_mol_from_smiles.return_value = mock_mol

        task = Task(
            project_id="proj-001",
            capability_id="synthesis_planning",
            title="test",
            metadata={
                "project_id": "proj-001",
                "target_smiles": "CCO",
                "search_depth": 3,
                "max_paths": 10,
                "normalize_ions": True,
                "include_literature": True,
                "expansion_timeout": 300,
            },
        )
        result = self.app.validate(task, {})
        self.assertTrue(result["valid"])

    @patch("rdkit.Chem.MolFromSmiles")
    def test_validate_invalid_smiles(self, mock_mol_from_smiles):
        """验证无效 SMILES 应返回错误。"""
        mock_mol_from_smiles.return_value = None

        task = Task(
            project_id="proj-001",
            capability_id="synthesis_planning",
            title="test",
            metadata={
                "project_id": "proj-001",
                "target_smiles": "!!!invalid!!!",
                "search_depth": 3,
                "max_paths": 10,
                "normalize_ions": True,
                "include_literature": True,
                "expansion_timeout": 300,
            },
        )
        result = self.app.validate(task, {})
        self.assertFalse(result["valid"])

    @patch("rdkit.Chem.MolFromSmiles")
    def test_validate_depth_out_of_range(self, mock_mol_from_smiles):
        """验证超出范围的搜索深度应返回错误。"""
        mock_mol = MagicMock()
        mock_mol_from_smiles.return_value = mock_mol

        task = Task(
            project_id="proj-001",
            capability_id="synthesis_planning",
            title="test",
            metadata={
                "project_id": "proj-001",
                "target_smiles": "CCO",
                "search_depth": 99,
                "max_paths": 10,
                "normalize_ions": True,
                "include_literature": True,
                "expansion_timeout": 300,
            },
        )
        result = self.app.validate(task, {})
        self.assertFalse(result["valid"])


class TestSynthesisPlanningApplicationPrepare(unittest.TestCase):
    """SynthesisPlanningApplication.prepare 方法测试。"""

    def setUp(self):
        self.app = SynthesisPlanningApplication(kernel=MagicMock())

    def test_prepare_creates_run(self):
        """验证 prepare 应创建正确的 Run 实例。"""
        task = Task(
            task_id="task-001",
            project_id="proj-001",
            capability_id="synthesis_planning",
            title="test",
            metadata={
                "project_id": "proj-001",
                "target_smiles": "CCO",
                "search_depth": 5,
                "max_paths": 20,
                "normalize_ions": False,
                "include_literature": True,
                "expansion_timeout": 600,
            },
        )
        run = self.app.prepare(task)
        self.assertIsInstance(run, Run)
        self.assertEqual(run.task_id, "task-001")
        self.assertEqual(run.service_id, "synthesis_planning")
        self.assertEqual(run.command, "plan_synthesis")
        self.assertIn("target_smiles", run.input)
        self.assertEqual(run.input["target_smiles"], "CCO")
        self.assertEqual(run.input["search_depth"], 5)
        self.assertEqual(run.input["max_paths"], 20)
        self.assertFalse(run.input["normalize_ions"])
        self.assertTrue(run.input["include_literature"])
        self.assertEqual(run.input["expansion_timeout"], 600)


class TestSynthesisPlanningApplicationExecute(unittest.TestCase):
    """SynthesisPlanningApplication.execute 方法测试。"""

    def setUp(self):
        self.app = SynthesisPlanningApplication(kernel=MagicMock())

    def test_execute_returns_artifact_list(self):
        """验证 execute 应返回 Artifact 列表，包含 stats 和 routes。"""
        run = Run(
            run_id="run-001",
            task_id="task-001",
            project_id="proj-001",
            service_id="synthesis_planning",
            command="plan_synthesis",
            input={
                "target_smiles": "CCO",
                "search_depth": 3,
                "max_paths": 10,
                "normalize_ions": True,
                "include_literature": True,
                "expansion_timeout": 300,
            },
        )
        artifacts = self.app.execute(run, {})
        self.assertIsInstance(artifacts, list)
        self.assertGreater(len(artifacts), 0)
        self.assertIsInstance(artifacts[0], Artifact)
        # 默认 adapter 没有归一化，也没有 routes，所以至少有一个 stats artifact
        self.assertEqual(artifacts[0].name, "search_stats")
        self.assertEqual(artifacts[0].type, ArtifactType.RESULT_TABLE)

    def test_execute_with_normalization(self):
        """验证归一化发生时应产生 normalization Artifact。"""
        mock_adapter = MagicMock()
        mock_adapter.execute.return_value = {
            "normalized_smiles": "CCO",
            "stats": {"total_iterations": 10, "total_reactions": 5, "total_paths": 2, "search_time_s": 1.5},
            "routes": [
                {"route_rank": 1, "avg_ff_score": 0.85, "num_reactions": 3, "reaction_smiles": "A>>B>>C", "evidence_grade": "E1"},
            ],
            "diagnostics": None,
        }
        mock_adapter.parse_output.return_value = {
            "normalized_smiles": "CCO",
            "stats": {"total_iterations": 10, "total_reactions": 5, "total_paths": 2, "search_time_s": 1.5},
            "routes": [
                {"route_rank": 1, "avg_ff_score": 0.85, "num_reactions": 3, "reaction_smiles": "A>>B>>C", "evidence_grade": "E1"},
            ],
            "diagnostics": None,
        }
        app = SynthesisPlanningApplication(kernel=MagicMock(), adapter=mock_adapter)
        run = Run(
            run_id="run-001",
            task_id="task-001",
            project_id="proj-001",
            service_id="synthesis_planning",
            command="plan_synthesis",
            input={
                "target_smiles": "CCO.NaCl",
                "search_depth": 3,
                "max_paths": 10,
                "normalize_ions": True,
                "include_literature": True,
                "expansion_timeout": 300,
            },
        )
        artifacts = app.execute(run, {})
        names = [a.name for a in artifacts]
        self.assertIn("normalization", names)
        self.assertIn("search_stats", names)
        self.assertIn("synthesis_routes", names)

    def test_execute_with_normalization_no_change(self):
        """验证归一化后 SMILES 不变时不应产生 normalization Artifact。"""
        mock_adapter = MagicMock()
        mock_adapter.execute.return_value = {
            "normalized_smiles": "CCO",
            "stats": {"total_iterations": 5, "total_reactions": 3, "total_paths": 1, "search_time_s": 0.5},
            "routes": [],
            "diagnostics": None,
        }
        mock_adapter.parse_output.return_value = {
            "normalized_smiles": "CCO",
            "stats": {"total_iterations": 5, "total_reactions": 3, "total_paths": 1, "search_time_s": 0.5},
            "routes": [],
            "diagnostics": None,
        }
        app = SynthesisPlanningApplication(kernel=MagicMock(), adapter=mock_adapter)
        run = Run(
            run_id="run-001",
            task_id="task-001",
            project_id="proj-001",
            service_id="synthesis_planning",
            command="plan_synthesis",
            input={
                "target_smiles": "CCO",
                "search_depth": 3,
                "max_paths": 10,
                "normalize_ions": True,
                "include_literature": True,
                "expansion_timeout": 300,
            },
        )
        artifacts = app.execute(run, {})
        names = [a.name for a in artifacts]
        self.assertNotIn("normalization", names)

    def test_execute_with_diagnostics(self):
        """验证存在诊断信息时应产生 diagnostics Artifact。"""
        mock_adapter = MagicMock()
        mock_adapter.execute.return_value = {
            "normalized_smiles": "CCO",
            "stats": {"total_iterations": 0, "total_reactions": 0, "total_paths": 0, "search_time_s": 0.3},
            "routes": [],
            "diagnostics": {
                "error_type": "no_template",
                "error_message": "无模板匹配",
                "recommendation": "回退到文献搜索",
            },
        }
        mock_adapter.parse_output.return_value = {
            "normalized_smiles": "CCO",
            "stats": {"total_iterations": 0, "total_reactions": 0, "total_paths": 0, "search_time_s": 0.3},
            "routes": [],
            "diagnostics": {
                "error_type": "no_template",
                "error_message": "无模板匹配",
                "recommendation": "回退到文献搜索",
            },
        }
        app = SynthesisPlanningApplication(kernel=MagicMock(), adapter=mock_adapter)
        run = Run(
            run_id="run-001",
            task_id="task-001",
            project_id="proj-001",
            service_id="synthesis_planning",
            command="plan_synthesis",
            input={
                "target_smiles": "CCO",
                "search_depth": 3,
                "max_paths": 10,
                "normalize_ions": True,
                "include_literature": True,
                "expansion_timeout": 300,
            },
        )
        artifacts = app.execute(run, {})
        names = [a.name for a in artifacts]
        self.assertIn("diagnostics", names)

    def test_execute_with_no_routes(self):
        """验证无路线时不应产生 synthesis_routes Artifact。"""
        mock_adapter = MagicMock()
        mock_adapter.execute.return_value = {
            "normalized_smiles": "CCO",
            "stats": {"total_iterations": 5, "total_reactions": 0, "total_paths": 0, "search_time_s": 0.5},
            "routes": [],
            "diagnostics": None,
        }
        mock_adapter.parse_output.return_value = {
            "normalized_smiles": "CCO",
            "stats": {"total_iterations": 5, "total_reactions": 0, "total_paths": 0, "search_time_s": 0.5},
            "routes": [],
            "diagnostics": None,
        }
        app = SynthesisPlanningApplication(kernel=MagicMock(), adapter=mock_adapter)
        run = Run(
            run_id="run-001",
            task_id="task-001",
            project_id="proj-001",
            service_id="synthesis_planning",
            command="plan_synthesis",
            input={
                "target_smiles": "CCO",
                "search_depth": 3,
                "max_paths": 10,
                "normalize_ions": True,
                "include_literature": True,
                "expansion_timeout": 300,
            },
        )
        artifacts = app.execute(run, {})
        names = [a.name for a in artifacts]
        self.assertIn("search_stats", names)
        self.assertNotIn("synthesis_routes", names)


class TestSynthesisPlanningApplicationPostprocess(unittest.TestCase):
    """SynthesisPlanningApplication.postprocess 方法测试。"""

    def setUp(self):
        self.app = SynthesisPlanningApplication(kernel=MagicMock())

    def test_postprocess_returns_evidence_packages(self):
        """验证 postprocess 应返回 EvidencePackage 列表。"""
        run = Run(
            run_id="run-001",
            task_id="task-001",
            project_id="proj-001",
            service_id="synthesis_planning",
            command="plan_synthesis",
        )
        artifacts = [
            Artifact(
                run_id="run-001",
                type=ArtifactType.RESULT_TABLE,
                name="search_stats",
                description="逆合成搜索统计",
                data={
                    "total_iterations": 100,
                    "total_chemicals": 50,
                    "total_reactions": 30,
                    "total_templates": 20,
                    "total_paths": 5,
                    "search_time_s": 2.5,
                },
            ),
            Artifact(
                run_id="run-001",
                type=ArtifactType.RESULT_TABLE,
                name="synthesis_routes",
                description="逆合成路线结果",
                data={
                    "routes": [
                        {"route_rank": 1, "avg_ff_score": 0.85, "num_reactions": 3, "reaction_smiles": "A>>B>>C", "evidence_grade": "E1"},
                    ]
                },
            ),
        ]
        evidence = self.app.postprocess(run, artifacts)
        self.assertIsInstance(evidence, list)
        self.assertGreater(len(evidence), 0)
        self.assertIsInstance(evidence[0], EvidencePackage)

    def test_postprocess_with_normalization(self):
        """验证包含归一化信息时应产生 normalization 证据。"""
        run = Run(
            run_id="run-001",
            task_id="task-001",
            project_id="proj-001",
            service_id="synthesis_planning",
            command="plan_synthesis",
        )
        artifacts = [
            Artifact(
                run_id="run-001",
                type=ArtifactType.LOG,
                name="normalization",
                description="目标分子归一化信息",
                data={
                    "original_smiles": "CCO.[Na+]",
                    "normalized_smiles": "CCO",
                },
            ),
            Artifact(
                run_id="run-001",
                type=ArtifactType.RESULT_TABLE,
                name="search_stats",
                data={
                    "total_iterations": 10,
                    "total_reactions": 5,
                    "total_paths": 2,
                    "search_time_s": 1.0,
                },
            ),
        ]
        evidence = self.app.postprocess(run, artifacts)
        types = [e.metadata.get("evidence_type") for e in evidence]
        self.assertIn("normalization", types)
        self.assertIn("search_stats", types)

    def test_postprocess_with_diagnostics(self):
        """验证包含诊断信息时应产生 error 证据。"""
        run = Run(
            run_id="run-001",
            task_id="task-001",
            project_id="proj-001",
            service_id="synthesis_planning",
            command="plan_synthesis",
        )
        artifacts = [
            Artifact(
                run_id="run-001",
                type=ArtifactType.RESULT_TABLE,
                name="search_stats",
                data={
                    "total_iterations": 0,
                    "total_reactions": 0,
                    "total_paths": 0,
                    "search_time_s": 0.3,
                },
            ),
            Artifact(
                run_id="run-001",
                type=ArtifactType.LOG,
                name="diagnostics",
                data={
                    "error_type": "no_template",
                    "error_message": "无模板匹配",
                    "recommendation": "回退到文献搜索",
                },
            ),
        ]
        evidence = self.app.postprocess(run, artifacts)
        types = [e.metadata.get("evidence_type") for e in evidence]
        self.assertIn("error_diagnosis", types)

    def test_postprocess_empty_artifacts(self):
        """验证无工件时应返回空列表。"""
        run = Run(
            run_id="run-001",
            task_id="task-001",
            project_id="proj-001",
            service_id="synthesis_planning",
            command="plan_synthesis",
        )
        evidence = self.app.postprocess(run, [])
        self.assertEqual(len(evidence), 0)


class TestSynthesisPlanningApplicationRunFullCycle(unittest.TestCase):
    """SynthesisPlanningApplication.run_full_cycle 完整生命周期测试。"""

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

        app = SynthesisPlanningApplication(kernel=mock_kernel)
        task = Task(
            project_id="proj-001",
            capability_id="synthesis_planning",
            title="test",
            metadata={
                "project_id": "proj-001",
                "target_smiles": "CCO",
                "search_depth": 3,
                "max_paths": 10,
                "normalize_ions": True,
                "include_literature": True,
                "expansion_timeout": 300,
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
        app = SynthesisPlanningApplication(kernel=mock_kernel)
        task = Task(
            project_id="proj-001",
            capability_id="synthesis_planning",
            title="test",
            metadata={
                "project_id": "proj-001",
                "target_smiles": "",
                "search_depth": 3,
                "max_paths": 10,
                "normalize_ions": True,
                "include_literature": True,
                "expansion_timeout": 300,
            },
        )
        with self.assertRaises(ValueError):
            app.run_full_cycle(task)


class TestEvidenceMapper(unittest.TestCase):
    """evidence_mapper 函数测试。"""

    def test_map_route_evidence_e0(self):
        """验证 E0 等级应映射为 LOW 级别。"""
        package = map_route_evidence(
            run_id="run-001",
            task_id="task-001",
            route={
                "route_rank": 1,
                "avg_ff_score": 0.5,
                "num_reactions": 2,
                "reaction_smiles": "A>>B>>C",
                "evidence_grade": "E0",
            },
        )
        self.assertEqual(package.level, EvidenceLevel.LOW)
        self.assertEqual(package.source_service, "real_engine:synthesis_planning")
        self.assertEqual(package.metadata["evidence_grade"], "E0")
        self.assertEqual(package.metadata["evidence_label"], "模板匹配")

    def test_map_route_evidence_e1(self):
        """验证 E1 等级应映射为 MEDIUM 级别。"""
        package = map_route_evidence(
            run_id="run-001",
            task_id="task-001",
            route={
                "route_rank": 1,
                "avg_ff_score": 0.6,
                "num_reactions": 3,
                "reaction_smiles": "A>>B>>C>>D",
                "evidence_grade": "E1",
            },
        )
        self.assertEqual(package.level, EvidenceLevel.MEDIUM)
        self.assertEqual(package.metadata["evidence_grade"], "E1")
        self.assertEqual(package.metadata["evidence_label"], "文献相似")

    def test_map_route_evidence_e2(self):
        """验证 E2 等级应映射为 MEDIUM 级别。"""
        package = map_route_evidence(
            run_id="run-001",
            task_id="task-001",
            route={
                "route_rank": 2,
                "avg_ff_score": 0.8,
                "num_reactions": 4,
                "reaction_smiles": "A>>B>>C>>D>>E",
                "evidence_grade": "E2",
            },
        )
        self.assertEqual(package.level, EvidenceLevel.MEDIUM)
        self.assertEqual(package.metadata["evidence_grade"], "E2")
        self.assertEqual(package.metadata["evidence_label"], "文献直接引用")

    def test_map_route_evidence_e3(self):
        """验证 E3 等级应映射为 HIGH 级别。"""
        package = map_route_evidence(
            run_id="run-001",
            task_id="task-001",
            route={
                "route_rank": 1,
                "avg_ff_score": 0.9,
                "num_reactions": 2,
                "reaction_smiles": "A>>B>>C",
                "evidence_grade": "E3",
            },
        )
        self.assertEqual(package.level, EvidenceLevel.HIGH)
        self.assertEqual(package.metadata["evidence_grade"], "E3")
        self.assertEqual(package.metadata["evidence_label"], "内部实验验证")

    def test_map_route_evidence_e4(self):
        """验证 E4 等级应映射为 HIGH 级别。"""
        package = map_route_evidence(
            run_id="run-001",
            task_id="task-001",
            route={
                "route_rank": 1,
                "avg_ff_score": 1.0,
                "num_reactions": 5,
                "reaction_smiles": "A>>B>>C>>D>>E>>F",
                "evidence_grade": "E4",
            },
        )
        self.assertEqual(package.level, EvidenceLevel.HIGH)
        self.assertEqual(package.metadata["evidence_grade"], "E4")
        self.assertEqual(package.metadata["evidence_label"], "已验证工艺")

    def test_map_route_evidence_default_grade(self):
        """验证未指定 evidence_grade 时应默认为 E0。"""
        package = map_route_evidence(
            run_id="run-001",
            task_id="task-001",
            route={
                "route_rank": 1,
                "avg_ff_score": 0.0,
                "num_reactions": 0,
                "reaction_smiles": "",
            },
        )
        self.assertEqual(package.metadata["evidence_grade"], "E0")
        self.assertEqual(package.level, EvidenceLevel.LOW)

    def test_map_stats_evidence_with_paths(self):
        """验证有路线时的统计证据。"""
        package = map_stats_evidence(
            run_id="run-001",
            task_id="task-001",
            stats={
                "total_iterations": 100,
                "total_chemicals": 50,
                "total_reactions": 30,
                "total_templates": 20,
                "total_paths": 5,
                "search_time_s": 2.5,
            },
        )
        self.assertEqual(package.source_service, "real_engine:synthesis_planning")
        self.assertEqual(package.metadata["evidence_type"], "search_stats")
        self.assertIn("找到", package.claim)
        self.assertIn("5 条路线", package.claim)
        self.assertIn("30 个反应", package.claim)

    def test_map_stats_evidence_reactions_no_paths(self):
        """验证有反应但无路线时的统计证据。"""
        package = map_stats_evidence(
            run_id="run-001",
            task_id="task-001",
            stats={
                "total_iterations": 50,
                "total_chemicals": 20,
                "total_reactions": 10,
                "total_templates": 5,
                "total_paths": 0,
                "search_time_s": 1.0,
            },
        )
        self.assertEqual(package.metadata["evidence_grade"], "E0")
        self.assertIn("部分完成", package.claim)

    def test_map_stats_evidence_no_results(self):
        """验证无任何结果时的统计证据。"""
        package = map_stats_evidence(
            run_id="run-001",
            task_id="task-001",
            stats={
                "total_iterations": 0,
                "total_chemicals": 0,
                "total_reactions": 0,
                "total_templates": 0,
                "total_paths": 0,
                "search_time_s": 0.0,
            },
        )
        self.assertIn("未找到", package.claim)

    def test_map_normalization_evidence(self):
        """验证归一化证据应返回 HIGH 级别。"""
        package = map_normalization_evidence(
            run_id="run-001",
            task_id="task-001",
            original_smiles="CCO.[Na+]",
            normalized_smiles="CCO",
        )
        self.assertEqual(package.level, EvidenceLevel.HIGH)
        self.assertEqual(package.confidence, 1.0)
        self.assertEqual(package.metadata["evidence_type"], "normalization")
        self.assertIn("CCO.[Na+]", package.claim)
        self.assertIn("CCO", package.claim)
        self.assertEqual(package.value["original_smiles"], "CCO.[Na+]")
        self.assertEqual(package.value["normalized_smiles"], "CCO")

    def test_map_error_evidence(self):
        """验证错误诊断证据应返回 ASSISTIVE 级别。"""
        package = map_error_evidence(
            run_id="run-001",
            task_id="task-001",
            error_type="no_template",
            error_message="无模板匹配 — 目标分子超出模板覆盖范围",
            diagnostics={
                "error_type": "no_template",
                "error_message": "无模板匹配",
                "recommendation": "回退到文献搜索",
            },
        )
        self.assertEqual(package.level, EvidenceLevel.ASSISTIVE)
        self.assertEqual(package.confidence, 0.0)
        self.assertEqual(package.metadata["evidence_type"], "error_diagnosis")
        self.assertEqual(package.metadata["error_type"], "no_template")
        self.assertIn("no_template", package.claim)

    def test_map_error_evidence_without_diagnostics(self):
        """验证错误诊断证据不传 diagnostics 时使用空字典。"""
        package = map_error_evidence(
            run_id="run-001",
            task_id="task-001",
            error_type="timeout",
            error_message="搜索超时",
        )
        self.assertEqual(package.value["diagnostics"], {})
        self.assertEqual(package.metadata["error_type"], "timeout")

    def test_batch_map_routes(self):
        """验证批量映射应返回正确数量的证据包。"""
        routes = [
            {"route_rank": 1, "avg_ff_score": 0.85, "num_reactions": 3, "reaction_smiles": "A>>B>>C", "evidence_grade": "E1"},
            {"route_rank": 2, "avg_ff_score": 0.70, "num_reactions": 4, "reaction_smiles": "D>>E>>F>>G", "evidence_grade": "E2"},
        ]
        packages = batch_map_routes(
            run_id="run-001",
            task_id="task-001",
            routes=routes,
        )
        self.assertEqual(len(packages), 2)
        self.assertEqual(packages[0].metadata["route_rank"], 1)
        self.assertEqual(packages[1].metadata["route_rank"], 2)

    def test_batch_map_routes_empty(self):
        """验证空路线列表应返回空列表。"""
        packages = batch_map_routes(
            run_id="run-001",
            task_id="task-001",
            routes=[],
        )
        self.assertEqual(len(packages), 0)


class TestEvidenceGradeDescriptions(unittest.TestCase):
    """EVIDENCE_GRADE_DESCRIPTIONS 完整性测试。"""

    def test_has_five_grades(self):
        """验证证据等级表应包含 5 个等级。"""
        self.assertEqual(len(EVIDENCE_GRADE_DESCRIPTIONS), 5)

    def test_each_grade_has_required_fields(self):
        """验证每个等级都包含 label, description, confidence, level。"""
        for grade, meta in EVIDENCE_GRADE_DESCRIPTIONS.items():
            with self.subTest(grade=grade):
                self.assertIn("label", meta)
                self.assertIn("description", meta)
                self.assertIn("confidence", meta)
                self.assertIn("level", meta)

    def test_confidence_monotonic(self):
        """验证置信度应随等级递增。"""
        confidences = [EVIDENCE_GRADE_DESCRIPTIONS[f"E{i}"]["confidence"] for i in range(5)]
        for i in range(len(confidences) - 1):
            with self.subTest(i=i):
                self.assertLessEqual(confidences[i], confidences[i + 1])


if __name__ == "__main__":
    unittest.main()