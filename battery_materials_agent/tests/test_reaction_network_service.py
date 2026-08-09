"""反应网络分析服务单元测试 — 完整生命周期验证。"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from battery_materials_agent.contracts.task import Task
from battery_materials_agent.contracts.run import Run
from battery_materials_agent.contracts.artifact import Artifact, ArtifactType
from battery_materials_agent.contracts.evidence import EvidencePackage, EvidenceLevel
from battery_materials_agent.services.reaction_network.application import (
    ReactionNetworkApplication,
    EnumerateReactions,
    SearchTransitionState,
    GrowNetwork,
    _PlaceholderReactionAdapter,
)
from battery_materials_agent.services.reaction_network.validators import (
    ReactionNetworkValidator,
    validate_smiles,
    validate_elements,
    validate_network_params,
    validate_enumeration_params,
    ALLOWED_ELEMENTS,
    DEFAULT_MAX_BARRIER_KCAL,
    DEFAULT_MAX_REACTION_ENERGY_KCAL,
    DEFAULT_MAX_BREAK_BONDS,
    DEFAULT_MAX_FORM_BONDS,
    DEFAULT_MAX_CANDIDATES_PER_PARENT,
    DEFAULT_MAX_LAYERS,
    DEFAULT_MAX_SPECIES,
)
from battery_materials_agent.services.reaction_network.evidence_mapper import (
    map_reaction_evidence,
    batch_map_reaction_evidence,
    _evidence_level_from_stage,
)


# =============================================================================
# TestReactionNetworkValidator
# =============================================================================


class TestReactionNetworkValidator(unittest.TestCase):
    """ReactionNetworkValidator 校验逻辑测试。"""

    def setUp(self):
        self.valid_kwargs = {
            "reactant_smiles": ["CCO"],
            "charge": 0,
            "multiplicity": 1,
            "max_break_bonds": 1,
            "max_form_bonds": 1,
            "max_candidates": 300,
            "max_layers": 3,
            "max_species": 250,
            "max_barrier": 40.0,
            "max_reaction_energy": 30.0,
        }

    def test_validate_all_valid_input(self):
        """验证有效输入应返回 valid=True 且无错误。"""
        validator = ReactionNetworkValidator(**self.valid_kwargs)
        result = validator.validate_all()
        self.assertTrue(result["valid"])
        self.assertEqual(len(result["errors"]), 0)

    def test_validate_all_empty_reactants(self):
        """验证空反应物列表应返回 valid=False。"""
        kwargs = dict(self.valid_kwargs)
        kwargs["reactant_smiles"] = []
        validator = ReactionNetworkValidator(**kwargs)
        result = validator.validate_all()
        self.assertFalse(result["valid"])
        self.assertIn("reactant_smiles", result["errors"][0])

    def test_validate_all_invalid_smiles(self):
        """验证无效 SMILES 应返回 valid=False。"""
        kwargs = dict(self.valid_kwargs)
        kwargs["reactant_smiles"] = ["invalid_smiles"]
        validator = ReactionNetworkValidator(**kwargs)
        result = validator.validate_all()
        self.assertFalse(result["valid"])
        self.assertIn("reactant[0]", str(result["errors"]))

    def test_validate_all_empty_smiles_string(self):
        """验证空 SMILES 字符串应返回 valid=False。"""
        kwargs = dict(self.valid_kwargs)
        kwargs["reactant_smiles"] = [""]
        validator = ReactionNetworkValidator(**kwargs)
        result = validator.validate_all()
        self.assertFalse(result["valid"])

    def test_validate_all_multiplicity_zero(self):
        """验证 multiplicity=0 应返回 valid=False。"""
        kwargs = dict(self.valid_kwargs)
        kwargs["multiplicity"] = 0
        validator = ReactionNetworkValidator(**kwargs)
        result = validator.validate_all()
        self.assertFalse(result["valid"])
        self.assertIn("multiplicity", str(result["errors"]))

    def test_validate_all_multiplicity_high_gets_warning(self):
        """验证高 multiplicity 应产生警告。"""
        kwargs = dict(self.valid_kwargs)
        kwargs["multiplicity"] = 3
        validator = ReactionNetworkValidator(**kwargs)
        result = validator.validate_all()
        self.assertTrue(result["valid"])
        self.assertIn("multiplicity", str(result["warnings"][0]))

    def test_validate_all_break_and_form_both_zero(self):
        """验证断键和成键同时为 0 应返回错误。"""
        kwargs = dict(self.valid_kwargs)
        kwargs["max_break_bonds"] = 0
        kwargs["max_form_bonds"] = 0
        validator = ReactionNetworkValidator(**kwargs)
        result = validator.validate_all()
        self.assertFalse(result["valid"])
        self.assertIn("不能同时为 0", str(result["errors"]))

    def test_validate_all_negative_break_bonds(self):
        """验证负数断键数应返回错误。"""
        kwargs = dict(self.valid_kwargs)
        kwargs["max_break_bonds"] = -1
        validator = ReactionNetworkValidator(**kwargs)
        result = validator.validate_all()
        self.assertFalse(result["valid"])

    def test_validate_all_invalid_max_layers(self):
        """验证无效 max_layers 应返回错误。"""
        kwargs = dict(self.valid_kwargs)
        kwargs["max_layers"] = 0
        validator = ReactionNetworkValidator(**kwargs)
        result = validator.validate_all()
        self.assertFalse(result["valid"])
        self.assertIn("max_layers", str(result["errors"]))

    def test_validate_all_max_layers_high_warning(self):
        """验证过高 max_layers 应产生警告。"""
        kwargs = dict(self.valid_kwargs)
        kwargs["max_layers"] = 5
        validator = ReactionNetworkValidator(**kwargs)
        result = validator.validate_all()
        self.assertTrue(result["valid"])
        self.assertIn("max_layers", str(result["warnings"]))

    def test_validate_all_max_barrier_zero(self):
        """验证 max_barrier=0 应返回错误。"""
        kwargs = dict(self.valid_kwargs)
        kwargs["max_barrier"] = 0
        validator = ReactionNetworkValidator(**kwargs)
        result = validator.validate_all()
        self.assertFalse(result["valid"])

    def test_validate_all_max_reaction_energy_zero(self):
        """验证 max_reaction_energy=0 应返回错误。"""
        kwargs = dict(self.valid_kwargs)
        kwargs["max_reaction_energy"] = 0
        validator = ReactionNetworkValidator(**kwargs)
        result = validator.validate_all()
        self.assertFalse(result["valid"])

    def test_validate_all_large_max_species_warning(self):
        """验证过大 max_species 应产生警告。"""
        kwargs = dict(self.valid_kwargs)
        kwargs["max_species"] = 600
        validator = ReactionNetworkValidator(**kwargs)
        result = validator.validate_all()
        self.assertTrue(result["valid"])
        self.assertIn("max_species", str(result["warnings"]))

    def test_validate_all_multiple_reactants(self):
        """验证多个反应物输入应通过校验。"""
        kwargs = dict(self.valid_kwargs)
        kwargs["reactant_smiles"] = ["CCO", "CC(=O)O", "C1=CC=CC=C1"]
        validator = ReactionNetworkValidator(**kwargs)
        result = validator.validate_all()
        self.assertTrue(result["valid"])


# =============================================================================
# TestValidateSmiles
# =============================================================================


class TestValidateSmiles(unittest.TestCase):
    """validate_smiles 函数测试。"""

    def test_valid_smiles(self):
        """验证有效 SMILES 应返回有效结果。"""
        result = validate_smiles("CCO")
        self.assertTrue(result["valid"])
        self.assertEqual(len(result["errors"]), 0)

    def test_empty_smiles(self):
        """验证空 SMILES 应返回错误。"""
        result = validate_smiles("")
        self.assertFalse(result["valid"])
        self.assertIn("SMILES 不能为空", result["errors"])

    def test_whitespace_smiles(self):
        """验证空白 SMILES 应返回错误。"""
        result = validate_smiles("   ")
        self.assertFalse(result["valid"])

    def test_invalid_smiles(self):
        """验证格式无效的 SMILES 应返回错误。"""
        result = validate_smiles("C1C2C")
        self.assertFalse(result["valid"])

    def test_complex_organic_smiles(self):
        """验证复杂有机分子 SMILES 应通过校验。"""
        result = validate_smiles("CCOCC(=O)Oc1ccccc1")
        self.assertTrue(result["valid"])


# =============================================================================
# TestValidateElements
# =============================================================================


class TestValidateElements(unittest.TestCase):
    """validate_elements 函数测试。"""

    def test_allowed_elements(self):
        """验证白名单元素应通过校验。"""
        result = validate_elements("CCO")
        self.assertTrue(result["valid"])

    def test_disallowed_element(self):
        """验证包含不允许元素应返回错误。"""
        result = validate_elements("CC[Si]")
        self.assertFalse(result["valid"])
        self.assertIn("Si", str(result["disallowed_elements"]))

    def test_multiple_disallowed_elements(self):
        """验证多个不允许元素应全部列出。"""
        result = validate_elements("[Si][Ti]")
        self.assertFalse(result["valid"])
        disallowed = result["disallowed_elements"]
        self.assertIn("Si", disallowed)
        self.assertIn("Ti", disallowed)

    def test_allowed_elements_complete(self):
        """验证所有白名单元素。"""
        expected = {"H", "C", "N", "O", "F", "Cl", "Br", "I", "S", "P"}
        self.assertEqual(ALLOWED_ELEMENTS, expected)

    def test_phosphorus_allowed(self):
        """验证磷元素在允许列表中。"""
        result = validate_elements("CP")
        self.assertTrue(result["valid"])

    def test_sulfur_allowed(self):
        """验证硫元素在允许列表中。"""
        result = validate_elements("CSC")
        self.assertTrue(result["valid"])


# =============================================================================
# TestValidateNetworkParams
# =============================================================================


class TestValidateNetworkParams(unittest.TestCase):
    """validate_network_params 函数测试。"""

    def test_valid_params(self):
        """验证有效参数应返回无错误结果。"""
        result = validate_network_params(max_layers=2, max_species=100)
        self.assertTrue(result["valid"])
        self.assertEqual(len(result["errors"]), 0)

    def test_default_params_valid(self):
        """验证默认参数应通过校验。"""
        result = validate_network_params()
        self.assertTrue(result["valid"])

    def test_max_layers_zero(self):
        """验证 max_layers=0 应返回错误。"""
        result = validate_network_params(max_layers=0)
        self.assertFalse(result["valid"])

    def test_max_layers_high_warning(self):
        """验证 max_layers 过高应产生警告。"""
        result = validate_network_params(max_layers=5)
        self.assertTrue(result["valid"])
        self.assertIn("max_layers", str(result["warnings"]))

    def test_max_species_zero(self):
        """验证 max_species=0 应返回错误。"""
        result = validate_network_params(max_species=0)
        self.assertFalse(result["valid"])

    def test_max_species_high_warning(self):
        """验证 max_species 过高应产生警告。"""
        result = validate_network_params(max_species=600)
        self.assertTrue(result["valid"])
        self.assertIn("max_species", str(result["warnings"]))

    def test_max_barrier_negative(self):
        """验证负 max_barrier 应返回错误。"""
        result = validate_network_params(max_barrier=-10.0)
        self.assertFalse(result["valid"])

    def test_max_barrier_high_warning(self):
        """验证 max_barrier 过高应产生警告。"""
        result = validate_network_params(max_barrier=200.0)
        self.assertTrue(result["valid"])
        self.assertIn("max_barrier", str(result["warnings"]))

    def test_max_reaction_energy_negative(self):
        """验证负 max_reaction_energy 应返回错误。"""
        result = validate_network_params(max_reaction_energy=-5.0)
        self.assertFalse(result["valid"])

    def test_max_reaction_energy_high_warning(self):
        """验证 max_reaction_energy 过高应产生警告。"""
        result = validate_network_params(max_reaction_energy=200.0)
        self.assertTrue(result["valid"])
        self.assertIn("max_reaction_energy", str(result["warnings"]))


# =============================================================================
# TestValidateEnumerationParams
# =============================================================================


class TestValidateEnumerationParams(unittest.TestCase):
    """validate_enumeration_params 函数测试。"""

    def test_valid_params(self):
        """验证有效参数应返回无错误结果。"""
        result = validate_enumeration_params(max_break_bonds=1, max_form_bonds=1)
        self.assertTrue(result["valid"])

    def test_default_params_valid(self):
        """验证默认参数应通过校验。"""
        result = validate_enumeration_params()
        self.assertTrue(result["valid"])

    def test_negative_break_bonds(self):
        """验证负数 max_break_bonds 应返回错误。"""
        result = validate_enumeration_params(max_break_bonds=-1)
        self.assertFalse(result["valid"])

    def test_negative_form_bonds(self):
        """验证负数 max_form_bonds 应返回错误。"""
        result = validate_enumeration_params(max_form_bonds=-1)
        self.assertFalse(result["valid"])

    def test_both_zero(self):
        """验证断键和成键同时为 0 应返回错误。"""
        result = validate_enumeration_params(max_break_bonds=0, max_form_bonds=0)
        self.assertFalse(result["valid"])
        self.assertIn("不能同时为 0", str(result["errors"]))

    def test_break_bonds_high_warning(self):
        """验证 max_break_bonds 过高应产生警告。"""
        result = validate_enumeration_params(max_break_bonds=3)
        self.assertTrue(result["valid"])
        self.assertIn("max_break_bonds", str(result["warnings"]))

    def test_form_bonds_high_warning(self):
        """验证 max_form_bonds 过高应产生警告。"""
        result = validate_enumeration_params(max_form_bonds=3)
        self.assertTrue(result["valid"])
        self.assertIn("max_form_bonds", str(result["warnings"]))

    def test_max_candidates_zero(self):
        """验证 max_candidates_per_parent=0 应返回错误。"""
        result = validate_enumeration_params(max_candidates_per_parent=0)
        self.assertFalse(result["valid"])

    def test_max_candidates_high_warning(self):
        """验证 max_candidates_per_parent 过高应产生警告。"""
        result = validate_enumeration_params(max_candidates_per_parent=2000)
        self.assertTrue(result["valid"])
        self.assertIn("max_candidates_per_parent", str(result["warnings"]))

    def test_break_only(self):
        """验证仅断键（不成键）应通过校验。"""
        result = validate_enumeration_params(max_break_bonds=1, max_form_bonds=0)
        self.assertTrue(result["valid"])

    def test_form_only(self):
        """验证仅成键（不断键）应通过校验。"""
        result = validate_enumeration_params(max_break_bonds=0, max_form_bonds=1)
        self.assertTrue(result["valid"])


# =============================================================================
# TestEnumerateReactionsModel
# =============================================================================


class TestEnumerateReactionsModel(unittest.TestCase):
    """EnumerateReactions Pydantic 模型测试。"""

    def test_model_creation(self):
        """验证模型创建应正确设置字段值。"""
        cmd = EnumerateReactions(
            project_id="proj-001",
            reactant_smiles=["CCO"],
            charge=0,
            multiplicity=1,
            max_break_bonds=1,
            max_form_bonds=1,
            max_candidates=300,
        )
        self.assertEqual(cmd.project_id, "proj-001")
        self.assertEqual(cmd.reactant_smiles, ["CCO"])
        self.assertEqual(cmd.charge, 0)
        self.assertEqual(cmd.multiplicity, 1)
        self.assertEqual(cmd.max_break_bonds, 1)
        self.assertEqual(cmd.max_form_bonds, 1)
        self.assertEqual(cmd.max_candidates, 300)

    def test_defaults(self):
        """验证默认值。"""
        cmd = EnumerateReactions(
            project_id="proj-001",
            reactant_smiles=["CCO"],
        )
        self.assertEqual(cmd.charge, 0)
        self.assertEqual(cmd.multiplicity, 1)
        self.assertEqual(cmd.max_break_bonds, 1)
        self.assertEqual(cmd.max_form_bonds, 1)
        self.assertEqual(cmd.max_candidates, 300)


class TestSearchTransitionStateModel(unittest.TestCase):
    """SearchTransitionState Pydantic 模型测试。"""

    def test_model_creation(self):
        """验证模型创建。"""
        cmd = SearchTransitionState(
            project_id="proj-001",
            reaction_smiles="CCO>>CC(=O)O",
        )
        self.assertEqual(cmd.project_id, "proj-001")
        self.assertEqual(cmd.reaction_smiles, "CCO>>CC(=O)O")
        self.assertEqual(cmd.charge, 0)
        self.assertEqual(cmd.multiplicity, 1)
        self.assertIsNone(cmd.config)

    def test_with_config(self):
        """验证可选的 config 参数。"""
        cmd = SearchTransitionState(
            project_id="proj-001",
            reaction_smiles="CCO>>C=C",
            config={"method": "pygsm", "max_iter": 100},
        )
        self.assertEqual(cmd.config, {"method": "pygsm", "max_iter": 100})


class TestGrowNetworkModel(unittest.TestCase):
    """GrowNetwork Pydantic 模型测试。"""

    def test_model_creation(self):
        """验证模型创建。"""
        cmd = GrowNetwork(
            project_id="proj-001",
            reactants=["CCO"],
            max_layers=2,
            max_species=100,
            barrier_threshold=30.0,
        )
        self.assertEqual(cmd.project_id, "proj-001")
        self.assertEqual(cmd.reactants, ["CCO"])
        self.assertEqual(cmd.max_layers, 2)
        self.assertEqual(cmd.max_species, 100)
        self.assertEqual(cmd.barrier_threshold, 30.0)

    def test_defaults(self):
        """验证默认值。"""
        cmd = GrowNetwork(
            project_id="proj-001",
            reactants=["CCO"],
        )
        self.assertEqual(cmd.max_layers, 3)
        self.assertEqual(cmd.max_species, 250)
        self.assertEqual(cmd.barrier_threshold, 40.0)


# =============================================================================
# TestReactionNetworkApplicationCapability
# =============================================================================


class TestReactionNetworkApplicationCapability(unittest.TestCase):
    """ReactionNetworkApplication 能力标识测试。"""

    def setUp(self):
        self.app = ReactionNetworkApplication(kernel=MagicMock())

    def test_capability_id(self):
        """验证 capability_id 应为 'reaction_network'。"""
        self.assertEqual(self.app.capability_id, "reaction_network")

    def test_display_name(self):
        """验证 display_name 应为中文名称。"""
        self.assertEqual(self.app.display_name, "反应网络分析")

    def test_description(self):
        """验证 description 应包含服务描述。"""
        self.assertIn("RDKit", self.app.description)
        self.assertIn("反应网络", self.app.description)


# =============================================================================
# TestReactionNetworkApplicationValidate
# =============================================================================


class TestReactionNetworkApplicationValidate(unittest.TestCase):
    """ReactionNetworkApplication.validate 方法测试。"""

    def setUp(self):
        self.app = ReactionNetworkApplication(kernel=MagicMock())

    def test_validate_enumerate_valid(self):
        """验证有效枚举命令应返回无错误结果。"""
        task = Task(
            project_id="proj-001",
            capability_id="reaction_network",
            title="test",
            metadata={
                "command": "enumerate",
                "project_id": "proj-001",
                "reactant_smiles": ["CCO"],
                "charge": 0,
                "multiplicity": 1,
            },
        )
        result = self.app.validate(task, {})
        self.assertTrue(result["valid"])

    def test_validate_enumerate_empty_reactants(self):
        """验证空反应物枚举应返回错误。"""
        task = Task(
            project_id="proj-001",
            capability_id="reaction_network",
            title="test",
            metadata={
                "command": "enumerate",
                "project_id": "proj-001",
                "reactant_smiles": [],
            },
        )
        result = self.app.validate(task, {})
        self.assertFalse(result["valid"])

    def test_validate_ts_search_valid(self):
        """验证有效 TS 搜索命令应返回无错误结果。"""
        task = Task(
            project_id="proj-001",
            capability_id="reaction_network",
            title="test",
            metadata={
                "command": "ts_search",
                "project_id": "proj-001",
                "reaction_smiles": "CCO>>CC(=O)O",
            },
        )
        result = self.app.validate(task, {})
        self.assertTrue(result["valid"])

    def test_validate_ts_search_empty_smiles(self):
        """验证空 SMILES 的 TS 搜索应返回错误。"""
        task = Task(
            project_id="proj-001",
            capability_id="reaction_network",
            title="test",
            metadata={
                "command": "ts_search",
                "project_id": "proj-001",
                "reaction_smiles": "",
            },
        )
        result = self.app.validate(task, {})
        self.assertFalse(result["valid"])

    def test_validate_grow_network_valid(self):
        """验证有效网络扩展命令应返回无错误结果。"""
        task = Task(
            project_id="proj-001",
            capability_id="reaction_network",
            title="test",
            metadata={
                "command": "grow_network",
                "project_id": "proj-001",
                "reactants": ["CCO"],
                "max_layers": 2,
                "max_species": 100,
                "barrier_threshold": 30.0,
            },
        )
        result = self.app.validate(task, {})
        self.assertTrue(result["valid"])

    def test_validate_unknown_command(self):
        """验证未知命令应返回错误。"""
        task = Task(
            project_id="proj-001",
            capability_id="reaction_network",
            title="test",
            metadata={
                "command": "unknown",
                "project_id": "proj-001",
            },
        )
        result = self.app.validate(task, {})
        self.assertFalse(result["valid"])
        self.assertIn("未知命令", str(result["errors"]))


# =============================================================================
# TestReactionNetworkApplicationPrepare
# =============================================================================


class TestReactionNetworkApplicationPrepare(unittest.TestCase):
    """ReactionNetworkApplication.prepare 方法测试。"""

    def setUp(self):
        self.app = ReactionNetworkApplication(kernel=MagicMock())

    def test_prepare_enumerate(self):
        """验证 prepare 枚举命令应创建正确的 Run 实例。"""
        task = Task(
            task_id="task-001",
            project_id="proj-001",
            capability_id="reaction_network",
            title="test",
            metadata={
                "command": "enumerate",
                "project_id": "proj-001",
                "reactant_smiles": ["CCO"],
                "charge": 0,
                "multiplicity": 1,
                "max_break_bonds": 1,
                "max_form_bonds": 1,
                "max_candidates": 300,
            },
        )
        run = self.app.prepare(task)
        self.assertIsInstance(run, Run)
        self.assertEqual(run.task_id, "task-001")
        self.assertEqual(run.service_id, "reaction_network")
        self.assertEqual(run.command, "reaction_network_enumerate")
        self.assertIn("reactant_smiles", run.input)
        self.assertEqual(run.input["reactant_smiles"], ["CCO"])

    def test_prepare_ts_search(self):
        """验证 prepare TS 搜索命令应创建正确的 Run 实例。"""
        task = Task(
            task_id="task-001",
            project_id="proj-001",
            capability_id="reaction_network",
            title="test",
            metadata={
                "command": "ts_search",
                "project_id": "proj-001",
                "reaction_smiles": "CCO>>CC(=O)O",
                "charge": 0,
                "multiplicity": 1,
            },
        )
        run = self.app.prepare(task)
        self.assertEqual(run.command, "reaction_network_ts_search")
        self.assertIn("reaction_smiles", run.input)
        self.assertEqual(run.input["reaction_smiles"], "CCO>>CC(=O)O")

    def test_prepare_grow_network(self):
        """验证 prepare 网络扩展命令应创建正确的 Run 实例。"""
        task = Task(
            task_id="task-001",
            project_id="proj-001",
            capability_id="reaction_network",
            title="test",
            metadata={
                "command": "grow_network",
                "project_id": "proj-001",
                "reactants": ["CCO"],
                "max_layers": 2,
                "max_species": 100,
                "barrier_threshold": 30.0,
            },
        )
        run = self.app.prepare(task)
        self.assertEqual(run.command, "reaction_network_grow_network")
        self.assertEqual(run.input["max_layers"], 2)
        self.assertEqual(run.input["barrier_threshold"], 30.0)


# =============================================================================
# TestReactionNetworkApplicationExecute
# =============================================================================


class TestReactionNetworkApplicationExecute(unittest.TestCase):
    """ReactionNetworkApplication.execute 方法测试。"""

    def setUp(self):
        self.app = ReactionNetworkApplication(kernel=MagicMock())

    def test_execute_enumerate_returns_artifact_list(self):
        """验证执行枚举应返回 Artifact 列表。"""
        run = Run(
            task_id="task-001",
            project_id="proj-001",
            service_id="reaction_network",
            command="reaction_network_enumerate",
            input={
                "command": "enumerate",
                "reactant_smiles": ["CCO"],
            },
        )
        artifacts = self.app.execute(run, {})
        self.assertIsInstance(artifacts, list)
        self.assertGreater(len(artifacts), 0)
        self.assertIsInstance(artifacts[0], Artifact)
        self.assertEqual(artifacts[0].type, ArtifactType.RESULT_TABLE)

    def test_execute_with_placeholder_adapter(self):
        """验证使用占位适配器应返回占位结果。"""
        app = ReactionNetworkApplication(kernel=MagicMock(), adapter=_PlaceholderReactionAdapter())
        run = Run(
            task_id="task-001",
            project_id="proj-001",
            service_id="reaction_network",
            command="reaction_network_enumerate",
            input={
                "command": "enumerate",
                "reactant_smiles": ["CCO"],
            },
        )
        artifacts = app.execute(run, {})
        self.assertIsInstance(artifacts, list)
        self.assertGreater(len(artifacts), 0)
        self.assertEqual(artifacts[0].type, ArtifactType.RESULT_TABLE)
        self.assertIn("reactions", artifacts[0].data)
        self.assertIn("warnings", artifacts[0].data)

    def test_execute_ts_search_creates_extra_artifact(self):
        """验证 TS 搜索应额外创建 PLOT 类型 Artifact。"""
        app = ReactionNetworkApplication(kernel=MagicMock(), adapter=_PlaceholderReactionAdapter())
        run = Run(
            task_id="task-001",
            project_id="proj-001",
            service_id="reaction_network",
            command="reaction_network_ts_search",
            input={
                "command": "ts_search",
                "reaction_smiles": "CCO>>CC(=O)O",
            },
        )
        artifacts = app.execute(run, {})
        artifact_types = {a.type for a in artifacts}
        self.assertIn(ArtifactType.PLOT, artifact_types)
        self.assertIn(ArtifactType.RESULT_TABLE, artifact_types)

    def test_execute_grow_network_returns_species(self):
        """验证网络扩展应返回物种信息。"""
        app = ReactionNetworkApplication(kernel=MagicMock(), adapter=_PlaceholderReactionAdapter())
        run = Run(
            task_id="task-001",
            project_id="proj-001",
            service_id="reaction_network",
            command="reaction_network_grow_network",
            input={
                "command": "grow_network",
                "reactant_smiles": ["CCO"],
                "max_layers": 2,
                "max_species": 100,
                "barrier_threshold": 30.0,
            },
        )
        artifacts = app.execute(run, {})
        self.assertIn("species", artifacts[0].data)
        self.assertIn("reactions", artifacts[0].data)


# =============================================================================
# TestReactionNetworkApplicationPostprocess
# =============================================================================


class TestReactionNetworkApplicationPostprocess(unittest.TestCase):
    """ReactionNetworkApplication.postprocess 方法测试。"""

    def setUp(self):
        self.app = ReactionNetworkApplication(kernel=MagicMock())

    def test_postprocess_returns_evidence_packages(self):
        """验证 postprocess 应返回 EvidencePackage 列表。"""
        run = Run(
            run_id="run-001",
            task_id="task-001",
            project_id="proj-001",
            service_id="reaction_network",
            command="reaction_network_enumerate",
        )
        artifacts = [
            Artifact(
                run_id="run-001",
                type=ArtifactType.RESULT_TABLE,
                name="reaction_network_results",
                data={
                    "reactions": [
                        {
                            "reaction_smiles": "CCO>>CCO_product",
                            "evidence_stage": 0,
                            "confidence": 0.5,
                            "metadata": {"method": "placeholder"},
                        },
                        {
                            "reaction_smiles": "CCO>>CCO_product2",
                            "evidence_stage": 1,
                            "confidence": 0.6,
                            "metadata": {"method": "placeholder"},
                        },
                    ],
                    "warnings": [],
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
            service_id="reaction_network",
            command="reaction_network_enumerate",
        )
        evidence = self.app.postprocess(run, [])
        self.assertEqual(len(evidence), 0)

    def test_postprocess_no_reactions_in_artifact(self):
        """验证 Artifact 无 reactions 数据时应返回空列表。"""
        run = Run(
            run_id="run-001",
            task_id="task-001",
            project_id="proj-001",
            service_id="reaction_network",
            command="reaction_network_enumerate",
        )
        artifacts = [
            Artifact(
                run_id="run-001",
                type=ArtifactType.RESULT_TABLE,
                name="reaction_network_results",
                data={"warnings": []},
            )
        ]
        evidence = self.app.postprocess(run, artifacts)
        self.assertEqual(len(evidence), 0)


# =============================================================================
# TestReactionNetworkApplicationRunFullCycle
# =============================================================================


class TestReactionNetworkApplicationRunFullCycle(unittest.TestCase):
    """ReactionNetworkApplication.run_full_cycle 完整生命周期测试。"""

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

        app = ReactionNetworkApplication(kernel=mock_kernel, adapter=_PlaceholderReactionAdapter())
        task = Task(
            project_id="proj-001",
            capability_id="reaction_network",
            title="test",
            metadata={
                "command": "enumerate",
                "project_id": "proj-001",
                "reactant_smiles": ["CCO"],
                "charge": 0,
                "multiplicity": 1,
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
        app = ReactionNetworkApplication(kernel=mock_kernel)
        task = Task(
            project_id="proj-001",
            capability_id="reaction_network",
            title="test",
            metadata={
                "command": "enumerate",
                "project_id": "proj-001",
                "reactant_smiles": [],
            },
        )
        with self.assertRaises(ValueError):
            app.run_full_cycle(task)


# =============================================================================
# TestReactionNetworkAdapter
# =============================================================================


class TestReactionNetworkAdapter(unittest.TestCase):
    """_PlaceholderReactionAdapter 占位适配器测试。"""

    def setUp(self):
        self.adapter = _PlaceholderReactionAdapter()

    def test_execute_enumerate(self):
        """验证枚举执行应返回正确结构。"""
        result = self.adapter.execute({
            "command": "enumerate",
            "reactant_smiles": ["CCO"],
        })
        self.assertIn("status", result)
        self.assertEqual(result["status"], "completed")
        self.assertIn("reactions", result)
        self.assertIn("warnings", result)
        self.assertEqual(len(result["reactions"]), 1)

    def test_execute_ts_search(self):
        """验证 TS 搜索执行应返回正确结构（占位实现需显式标记降级）。"""
        result = self.adapter.execute({
            "command": "ts_search",
            "reaction_smiles": "CCO>>CC(=O)O",
        })
        self.assertEqual(result["status"], "completed")
        # 占位实现不得伪造真实 TS 证据
        self.assertFalse(result["ts_found"])
        self.assertTrue(result.get("degraded"))
        self.assertIsNone(result["barrier_kcal"])
        self.assertIsNone(result["frequency"])

    def test_execute_grow_network(self):
        """验证网络扩展执行应返回正确结构。"""
        result = self.adapter.execute({
            "command": "grow_network",
            "reactant_smiles": ["CCO"],
            "max_layers": 2,
            "max_species": 100,
        })
        self.assertEqual(result["status"], "completed")
        self.assertIn("reactions", result)
        self.assertIn("species", result)
        self.assertIn("layers_explored", result)

    def test_execute_unknown_command(self):
        """验证未知命令应返回 unknown 状态。"""
        result = self.adapter.execute({"command": "unknown"})
        self.assertEqual(result["status"], "unknown")

    def test_parse_output_dict(self):
        """验证 parse_output 能正确处理 dict 输入。"""
        result = self.adapter.parse_output({"status": "completed", "reactions": []})
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["reactions"], [])

    def test_parse_output_non_dict(self):
        """验证 parse_output 能处理非 dict 输入。"""
        result = self.adapter.parse_output("not a dict")
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["reactions"], [])

    def test_get_resource_requirements(self):
        """验证资源需求应返回默认值。"""
        reqs = self.adapter.get_resource_requirements({})
        self.assertIn("cpu", reqs)
        self.assertIn("memory_mb", reqs)
        self.assertIn("walltime_minutes", reqs)
        self.assertEqual(reqs["cpu"], 2)
        self.assertEqual(reqs["memory_mb"], 1024)
        self.assertEqual(reqs["walltime_minutes"], 15)

    def test_validate_input(self):
        """验证 validate_input 应返回空列表。"""
        errors = self.adapter.validate_input({"command": "enumerate"})
        self.assertEqual(errors, [])

    def test_enumerate_multiple_reactants(self):
        """验证多个反应物枚举应返回对应数量的反应。"""
        result = self.adapter.execute({
            "command": "enumerate",
            "reactant_smiles": ["CCO", "CC(=O)O", "C1=CC=CC=C1"],
        })
        self.assertEqual(len(result["reactions"]), 3)

    def test_ts_search_placeholder_marks_degraded(self):
        """验证占位 TS 搜索不伪造虚频，显式标记 degraded。"""
        result = self.adapter.execute({
            "command": "ts_search",
            "reaction_smiles": "CCO>>C=C",
        })
        self.assertFalse(result["ts_found"])
        self.assertTrue(result.get("degraded"))
        self.assertIsNone(result["frequency"])


# =============================================================================
# TestReactionNetworkEvidenceMapper
# =============================================================================


class TestReactionNetworkEvidenceMapper(unittest.TestCase):
    """evidence_mapper 函数测试。"""

    def test_map_e0_template_matching(self):
        """验证 E0 证据应映射为 ASSISTIVE 级别。"""
        package = map_reaction_evidence(
            run_id="run-001",
            task_id="task-001",
            reaction_smiles="CCO>>CC(=O)O",
            evidence_stage=0,
            confidence=0.5,
        )
        self.assertEqual(package.level, EvidenceLevel.ASSISTIVE)
        self.assertEqual(package.source_service, "real_engine:reaction_network")
        self.assertEqual(package.method, "reaction_network_analysis")
        self.assertIn("模板匹配", package.claim)

    def test_map_e1_literature_similarity(self):
        """验证 E1 证据应映射为 LOW 级别。"""
        package = map_reaction_evidence(
            run_id="run-001",
            task_id="task-001",
            reaction_smiles="CCO>>C=C",
            evidence_stage=1,
            confidence=0.6,
        )
        self.assertEqual(package.level, EvidenceLevel.LOW)
        self.assertIn("文献类似", package.claim)

    def test_map_e2_literature_direct(self):
        """验证 E2 证据应映射为 MEDIUM 级别。"""
        package = map_reaction_evidence(
            run_id="run-001",
            task_id="task-001",
            reaction_smiles="CCO>>CC(=O)O",
            evidence_stage=2,
            confidence=0.85,
        )
        self.assertEqual(package.level, EvidenceLevel.MEDIUM)
        self.assertIn("文献直接引用", package.claim)

    def test_map_e3_experimental(self):
        """验证 E3 证据应映射为 MEDIUM 级别。"""
        package = map_reaction_evidence(
            run_id="run-001",
            task_id="task-001",
            reaction_smiles="CCO>>CC(=O)O",
            evidence_stage=3,
            confidence=0.9,
        )
        self.assertEqual(package.level, EvidenceLevel.MEDIUM)

    def test_map_e4_validated_process(self):
        """验证 E4 证据应映射为 HIGH 级别。"""
        package = map_reaction_evidence(
            run_id="run-001",
            task_id="task-001",
            reaction_smiles="CCO>>CC(=O)O",
            evidence_stage=4,
            confidence=0.95,
        )
        self.assertEqual(package.level, EvidenceLevel.HIGH)
        self.assertIn("已验证工艺", package.claim)

    def test_map_with_metadata(self):
        """验证附加元数据应被包含在证据包中。"""
        package = map_reaction_evidence(
            run_id="run-001",
            task_id="task-001",
            reaction_smiles="CCO>>CC(=O)O",
            evidence_stage=2,
            metadata={"doi": "10.xxx/xxxxx", "source": "literature"},
        )
        self.assertIn("doi", package.metadata)
        self.assertEqual(package.metadata["doi"], "10.xxx/xxxxx")
        self.assertEqual(package.metadata["evidence_stage"], 2)
        self.assertIn("evidence_label", package.metadata)

    def test_batch_map_multiple(self):
        """验证批量映射应返回正确数量的证据包。"""
        results = [
            {
                "reaction_smiles": "CCO>>CCO_product",
                "evidence_stage": 0,
                "confidence": 0.5,
                "metadata": {"method": "template"},
            },
            {
                "reaction_smiles": "CCO>>CCO_product2",
                "evidence_stage": 2,
                "confidence": 0.85,
                "metadata": {"doi": "10.xxx/xxxxx"},
            },
            {
                "reaction_smiles": "CCO>>CCO_product3",
                "evidence_stage": 4,
                "confidence": 0.95,
                "metadata": {"process": "validated"},
            },
        ]
        packages = batch_map_reaction_evidence(
            run_id="run-001",
            task_id="task-001",
            results=results,
        )
        self.assertEqual(len(packages), 3)
        self.assertIsInstance(packages[0], EvidencePackage)
        self.assertEqual(packages[0].level, EvidenceLevel.ASSISTIVE)
        self.assertEqual(packages[1].level, EvidenceLevel.MEDIUM)
        self.assertEqual(packages[2].level, EvidenceLevel.HIGH)

    def test_batch_map_empty(self):
        """验证空结果列表应返回空列表。"""
        packages = batch_map_reaction_evidence(
            run_id="run-001",
            task_id="task-001",
            results=[],
        )
        self.assertEqual(len(packages), 0)

    def test_evidence_level_from_stage(self):
        """验证 _evidence_level_from_stage 映射逻辑。"""
        self.assertEqual(_evidence_level_from_stage(0), EvidenceLevel.ASSISTIVE)
        self.assertEqual(_evidence_level_from_stage(1), EvidenceLevel.LOW)
        self.assertEqual(_evidence_level_from_stage(2), EvidenceLevel.MEDIUM)
        self.assertEqual(_evidence_level_from_stage(3), EvidenceLevel.MEDIUM)
        self.assertEqual(_evidence_level_from_stage(4), EvidenceLevel.HIGH)
        self.assertEqual(_evidence_level_from_stage(5), EvidenceLevel.HIGH)


# =============================================================================
# TestReactionNetworkExternalAPI
# =============================================================================


class TestReactionNetworkExternalAPI(unittest.TestCase):
    """ReactionNetworkApplication 外部调用入口测试。"""

    def setUp(self):
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
        self.app = ReactionNetworkApplication(
            kernel=mock_kernel,
            adapter=_PlaceholderReactionAdapter(),
        )

    def test_enumerate_reactions(self):
        """验证 enumerate_reactions 外部入口应返回证据包。"""
        evidence = self.app.enumerate_reactions(
            project_id="proj-001",
            reactant_smiles=["CCO"],
        )
        self.assertIsInstance(evidence, list)
        self.assertGreater(len(evidence), 0)
        self.assertIsInstance(evidence[0], EvidencePackage)

    def test_enumerate_reactions_multiple_reactants(self):
        """验证多个反应物枚举应返回对应数量的证据包。"""
        evidence = self.app.enumerate_reactions(
            project_id="proj-001",
            reactant_smiles=["CCO", "CC(=O)O"],
        )
        self.assertEqual(len(evidence), 2)

    def test_search_transition_state(self):
        """验证 search_transition_state 外部入口应返回证据包。"""
        evidence = self.app.search_transition_state(
            project_id="proj-001",
            reaction_smiles="CCO>>CC(=O)O",
        )
        self.assertIsInstance(evidence, list)
        self.assertGreater(len(evidence), 0)

    def test_grow_network(self):
        """验证 grow_network 外部入口应返回证据包。"""
        evidence = self.app.grow_network(
            project_id="proj-001",
            reactants=["CCO"],
            max_layers=2,
            max_species=50,
        )
        self.assertIsInstance(evidence, list)
        self.assertGreater(len(evidence), 0)

    def test_grow_network_max_layers(self):
        """验证网络扩展层数限制。"""
        evidence = self.app.grow_network(
            project_id="proj-001",
            reactants=["CCO"],
            max_layers=1,
            max_species=50,
        )
        # 1 layer produces 1 reaction per species
        self.assertGreater(len(evidence), 0)


# =============================================================================
# TestConstants
# =============================================================================


class TestConstants(unittest.TestCase):
    """常量定义完整性测试。"""

    def test_allowed_elements_count(self):
        """验证白名单元素数量。"""
        self.assertEqual(len(ALLOWED_ELEMENTS), 10)

    def test_allowed_elements_contains_essential(self):
        """验证核心元素都存在。"""
        essential = {"H", "C", "N", "O", "F", "Cl", "Br", "I", "S", "P"}
        for el in essential:
            with self.subTest(element=el):
                self.assertIn(el, ALLOWED_ELEMENTS)

    def test_default_max_barrier(self):
        """验证默认最大能垒。"""
        self.assertEqual(DEFAULT_MAX_BARRIER_KCAL, 40.0)

    def test_default_max_reaction_energy(self):
        """验证默认最大反应能量。"""
        self.assertEqual(DEFAULT_MAX_REACTION_ENERGY_KCAL, 30.0)

    def test_default_break_bonds(self):
        """验证默认断键数。"""
        self.assertEqual(DEFAULT_MAX_BREAK_BONDS, 1)

    def test_default_form_bonds(self):
        """验证默认成键数。"""
        self.assertEqual(DEFAULT_MAX_FORM_BONDS, 1)

    def test_default_max_candidates(self):
        """验证默认候选数。"""
        self.assertEqual(DEFAULT_MAX_CANDIDATES_PER_PARENT, 300)

    def test_default_max_layers(self):
        """验证默认最大层数。"""
        self.assertEqual(DEFAULT_MAX_LAYERS, 3)

    def test_default_max_species(self):
        """验证默认最大物种数。"""
        self.assertEqual(DEFAULT_MAX_SPECIES, 250)


if __name__ == "__main__":
    unittest.main()