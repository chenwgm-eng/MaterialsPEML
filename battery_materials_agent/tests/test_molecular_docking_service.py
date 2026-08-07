"""分子对接服务单元测试 — 完整生命周期验证。"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from battery_materials_agent.contracts.task import Task
from battery_materials_agent.contracts.run import Run
from battery_materials_agent.contracts.artifact import Artifact, ArtifactType
from battery_materials_agent.contracts.evidence import EvidencePackage, EvidenceLevel
from battery_materials_agent.services.molecular_docking.application import (
    MolecularDockingApplication,
    DockSingle,
    DockBatch,
    AnalyzeDocking,
    ExportDocking,
    _PlaceholderAdapter,
)
from battery_materials_agent.services.molecular_docking.validators import (
    MolecularDockingValidator,
    validate_receptor_format,
    validate_ligand_format,
    validate_ligand_molecular_weight,
    validate_sampling_params,
    validate_confidence_threshold,
    validate_batch_params,
    validate_docking_scope,
    validate_top_n,
    RECEPTOR_FORMATS,
    LIGAND_FORMATS,
    LIGAND_MW_RANGE,
    SAMPLES_PER_COMPLEX_RANGE,
    INFERENCE_STEPS_RANGE,
    REJECTED_DOCKING_TYPES,
)
from battery_materials_agent.services.molecular_docking.evidence_mapper import (
    map_docking_evidence,
    batch_map_docking_evidence,
    map_screen_summary,
)


# ====================================================================
# TestDockingValidator — 验证器测试
# ====================================================================


class TestDockingValidator(unittest.TestCase):
    """MolecularDockingValidator 校验逻辑测试。"""

    def setUp(self):
        self.valid_kwargs = {
            "receptor_path": "/path/to/receptor.pdb",
            "ligand": "CCO",
            "ligand_format": "smiles",
            "ligand_mw": 150.0,
            "samples_per_complex": 10,
            "inference_steps": 20,
            "docking_type": "small_molecule",
        }

    def test_validate_all_valid_input(self):
        """验证有效输入应返回 valid=True 且无错误。"""
        validator = MolecularDockingValidator(**self.valid_kwargs)
        result = validator.validate_all()
        self.assertTrue(result["valid"])
        self.assertEqual(len(result["errors"]), 0)
        self.assertIn("receptor_format", result)

    def test_validate_all_empty_ligand(self):
        """验证空配体应返回 valid=False。"""
        kwargs = dict(self.valid_kwargs)
        kwargs["ligand"] = ""
        validator = MolecularDockingValidator(**kwargs)
        result = validator.validate_all()
        self.assertFalse(result["valid"])
        self.assertIn("ligand", result["errors"][0])

    def test_validate_all_whitespace_ligand(self):
        """验证空白配体应返回 valid=False。"""
        kwargs = dict(self.valid_kwargs)
        kwargs["ligand"] = "   "
        validator = MolecularDockingValidator(**kwargs)
        result = validator.validate_all()
        self.assertFalse(result["valid"])

    def test_validate_all_invalid_receptor_format(self):
        """验证不支持的受体格式应返回 valid=False。"""
        kwargs = dict(self.valid_kwargs)
        kwargs["receptor_path"] = "/path/to/receptor.xyz"
        validator = MolecularDockingValidator(**kwargs)
        result = validator.validate_all()
        self.assertFalse(result["valid"])
        self.assertIn("受体文件格式", result["errors"][0])

    def test_validate_all_invalid_ligand_format(self):
        """验证不支持的配体格式应返回 valid=False。"""
        kwargs = dict(self.valid_kwargs)
        kwargs["ligand_format"] = "invalid"
        validator = MolecularDockingValidator(**kwargs)
        result = validator.validate_all()
        self.assertFalse(result["valid"])
        self.assertIn("配体格式", result["errors"][0])

    def test_validate_all_sampling_out_of_range(self):
        """验证超范围的采样参数应返回错误。"""
        kwargs = dict(self.valid_kwargs)
        kwargs["samples_per_complex"] = 100
        validator = MolecularDockingValidator(**kwargs)
        result = validator.validate_all()
        self.assertFalse(result["valid"])
        self.assertIn("samples_per_complex", str(result["errors"]))

    def test_validate_all_inference_steps_out_of_range(self):
        """验证超范围的推理步数应返回错误。"""
        kwargs = dict(self.valid_kwargs)
        kwargs["inference_steps"] = 5
        validator = MolecularDockingValidator(**kwargs)
        result = validator.validate_all()
        self.assertFalse(result["valid"])
        self.assertIn("inference_steps", str(result["errors"]))

    def test_validate_all_rejected_docking_type(self):
        """验证被拒绝的对接类型应返回错误。"""
        kwargs = dict(self.valid_kwargs)
        kwargs["docking_type"] = "protein_protein"
        validator = MolecularDockingValidator(**kwargs)
        result = validator.validate_all()
        self.assertFalse(result["valid"])
        self.assertIn("蛋白-蛋白对接", result["errors"][0])

    def test_validate_all_covalent_rejected(self):
        """验证共价对接应被拒绝。"""
        kwargs = dict(self.valid_kwargs)
        kwargs["docking_type"] = "covalent"
        validator = MolecularDockingValidator(**kwargs)
        result = validator.validate_all()
        self.assertFalse(result["valid"])
        self.assertIn("共价对接", result["errors"][0])

    def test_validate_all_large_peptide_rejected(self):
        """验证大肽对接应被拒绝。"""
        kwargs = dict(self.valid_kwargs)
        kwargs["docking_type"] = "large_peptide"
        validator = MolecularDockingValidator(**kwargs)
        result = validator.validate_all()
        self.assertFalse(result["valid"])
        self.assertIn("大肽", result["errors"][0])

    def test_validate_all_mw_warning(self):
        """验证超出范围的分子量应产生警告。"""
        kwargs = dict(self.valid_kwargs)
        kwargs["ligand_mw"] = 50.0
        validator = MolecularDockingValidator(**kwargs)
        result = validator.validate_all()
        self.assertTrue(result["valid"])
        self.assertIn("分子量", str(result["warnings"]))

    def test_validate_all_mw_negative(self):
        """验证负数分子量应返回错误。"""
        kwargs = dict(self.valid_kwargs)
        kwargs["ligand_mw"] = -10.0
        validator = MolecularDockingValidator(**kwargs)
        result = validator.validate_all()
        self.assertFalse(result["valid"])

    def test_validate_all_mmcif_receptor(self):
        """验证 mmCIF 格式受体应通过校验。"""
        kwargs = dict(self.valid_kwargs)
        kwargs["receptor_path"] = "/path/to/receptor.cif"
        validator = MolecularDockingValidator(**kwargs)
        result = validator.validate_all()
        self.assertTrue(result["valid"])
        self.assertEqual(result["receptor_format"], "mmcif")


# ====================================================================
# TestValidateReceptorFormat — 受体格式校验测试
# ====================================================================


class TestValidateReceptorFormat(unittest.TestCase):
    """validate_receptor_format 函数测试。"""

    def test_valid_pdb(self):
        """验证 .pdb 格式应返回有效结果。"""
        result = validate_receptor_format("/path/to/protein.pdb")
        self.assertTrue(result["valid"])
        self.assertEqual(result["receptor_format"], "pdb")

    def test_valid_pdb_ent(self):
        """验证 .ent 格式应返回有效结果。"""
        result = validate_receptor_format("/path/to/protein.ent")
        self.assertTrue(result["valid"])
        self.assertEqual(result["receptor_format"], "pdb")

    def test_valid_mmcif(self):
        """验证 .cif 格式应返回有效结果。"""
        result = validate_receptor_format("/path/to/protein.cif")
        self.assertTrue(result["valid"])
        self.assertEqual(result["receptor_format"], "mmcif")

    def test_valid_mmcif_double_ext(self):
        """验证 .mmcif 格式应返回有效结果。"""
        result = validate_receptor_format("/path/to/protein.mmcif")
        self.assertTrue(result["valid"])
        self.assertEqual(result["receptor_format"], "mmcif")

    def test_invalid_extension(self):
        """验证不支持的扩展名应返回错误。"""
        result = validate_receptor_format("/path/to/protein.xyz")
        self.assertFalse(result["valid"])
        self.assertIn("受体文件格式", result["errors"][0])

    def test_no_extension(self):
        """验证无扩展名的文件应返回错误。"""
        result = validate_receptor_format("/path/to/protein")
        self.assertFalse(result["valid"])


# ====================================================================
# TestValidateLigandFormat — 配体格式校验测试
# ====================================================================


class TestValidateLigandFormat(unittest.TestCase):
    """validate_ligand_format 函数测试。"""

    def test_valid_smiles(self):
        """验证 smiles 格式应返回有效结果。"""
        result = validate_ligand_format("smiles")
        self.assertTrue(result["valid"])
        self.assertIn("ligand_format_info", result)

    def test_valid_sdf(self):
        """验证 sdf 格式应返回有效结果。"""
        result = validate_ligand_format("sdf")
        self.assertTrue(result["valid"])

    def test_valid_mol2(self):
        """验证 mol2 格式应返回有效结果。"""
        result = validate_ligand_format("mol2")
        self.assertTrue(result["valid"])

    def test_invalid_format(self):
        """验证无效格式应返回错误。"""
        result = validate_ligand_format("xyz")
        self.assertFalse(result["valid"])
        self.assertIn("配体格式", result["errors"][0])

    def test_case_insensitive(self):
        """验证格式名称应大小写不敏感。"""
        result = validate_ligand_format("SMILES")
        self.assertTrue(result["valid"])


# ====================================================================
# TestValidateLigandMolecularWeight — 分子量校验测试
# ====================================================================


class TestValidateLigandMolecularWeight(unittest.TestCase):
    """validate_ligand_molecular_weight 函数测试。"""

    def test_valid_mw(self):
        """验证有效分子量应返回无错误结果。"""
        result = validate_ligand_molecular_weight(300.0)
        self.assertTrue(result["valid"])
        self.assertEqual(len(result["errors"]), 0)

    def test_none_mw(self):
        """验证 None 分子量应返回有效。"""
        result = validate_ligand_molecular_weight(None)
        self.assertTrue(result["valid"])

    def test_negative_mw(self):
        """验证负数分子量应返回错误。"""
        result = validate_ligand_molecular_weight(-10.0)
        self.assertFalse(result["valid"])

    def test_mw_below_range(self):
        """验证低于范围分子量应产生警告。"""
        result = validate_ligand_molecular_weight(50.0)
        self.assertTrue(result["valid"])
        self.assertIn("分子量", str(result["warnings"]))

    def test_mw_above_range(self):
        """验证高于范围分子量应产生警告。"""
        result = validate_ligand_molecular_weight(2000.0)
        self.assertTrue(result["valid"])
        self.assertIn("分子量", str(result["warnings"]))

    def test_mw_at_lower_boundary(self):
        """验证边界分子量 100.0 不应产生警告。"""
        result = validate_ligand_molecular_weight(100.0)
        self.assertTrue(result["valid"])
        self.assertEqual(len(result["warnings"]), 0)

    def test_mw_at_upper_boundary(self):
        """验证边界分子量 1000.0 不应产生警告。"""
        result = validate_ligand_molecular_weight(1000.0)
        self.assertTrue(result["valid"])
        self.assertEqual(len(result["warnings"]), 0)


# ====================================================================
# TestValidateSamplingParams — 采样参数校验测试
# ====================================================================


class TestValidateSamplingParams(unittest.TestCase):
    """validate_sampling_params 函数测试。"""

    def test_valid_params(self):
        """验证有效参数应返回无错误结果。"""
        result = validate_sampling_params(10, 20)
        self.assertTrue(result["valid"])
        self.assertEqual(len(result["errors"]), 0)

    def test_samples_too_low(self):
        """验证过低的 samples_per_complex 应返回错误。"""
        result = validate_sampling_params(samples_per_complex=0)
        self.assertFalse(result["valid"])
        self.assertIn("samples_per_complex", str(result["errors"]))

    def test_samples_too_high(self):
        """验证过高的 samples_per_complex 应返回错误。"""
        result = validate_sampling_params(samples_per_complex=100)
        self.assertFalse(result["valid"])

    def test_steps_too_low(self):
        """验证过低的 inference_steps 应返回错误。"""
        result = validate_sampling_params(inference_steps=5)
        self.assertFalse(result["valid"])
        self.assertIn("inference_steps", str(result["errors"]))

    def test_steps_too_high(self):
        """验证过高的 inference_steps 应返回错误。"""
        result = validate_sampling_params(inference_steps=100)
        self.assertFalse(result["valid"])

    def test_steps_high_warning(self):
        """验证较高的 inference_steps 应产生警告。"""
        result = validate_sampling_params(inference_steps=40)
        self.assertTrue(result["valid"])
        self.assertIn("推理时间较长", str(result["warnings"]))

    def test_samples_at_lower_boundary(self):
        """验证边界 samples_per_complex=1 应有效。"""
        result = validate_sampling_params(samples_per_complex=1)
        self.assertTrue(result["valid"])

    def test_samples_at_upper_boundary(self):
        """验证边界 samples_per_complex=50 应有效。"""
        result = validate_sampling_params(samples_per_complex=50)
        self.assertTrue(result["valid"])


# ====================================================================
# TestValidateConfidenceThreshold — 置信度阈值校验测试
# ====================================================================


class TestValidateConfidenceThreshold(unittest.TestCase):
    """validate_confidence_threshold 函数测试。"""

    def test_valid_threshold(self):
        """验证有效阈值应返回无错误。"""
        result = validate_confidence_threshold(0.5)
        self.assertTrue(result["valid"])

    def test_threshold_too_low(self):
        """验证过低阈值应返回错误。"""
        result = validate_confidence_threshold(-0.1)
        self.assertFalse(result["valid"])

    def test_threshold_too_high(self):
        """验证过高阈值应返回错误。"""
        result = validate_confidence_threshold(1.5)
        self.assertFalse(result["valid"])

    def test_threshold_at_lower_boundary(self):
        """验证边界阈值 0.0 应有效。"""
        result = validate_confidence_threshold(0.0)
        self.assertTrue(result["valid"])

    def test_threshold_at_upper_boundary(self):
        """验证边界阈值 1.0 应有效。"""
        result = validate_confidence_threshold(1.0)
        self.assertTrue(result["valid"])


# ====================================================================
# TestValidateBatchParams — 批处理参数校验测试
# ====================================================================


class TestValidateBatchParams(unittest.TestCase):
    """validate_batch_params 函数测试。"""

    def test_valid_batch(self):
        """验证有效批处理参数应返回无错误。"""
        result = validate_batch_params(
            complexes=[{"receptor_path": "a.pdb", "ligand": "CCO"}],
            workers=1,
        )
        self.assertTrue(result["valid"])

    def test_empty_complexes(self):
        """验证空复合物列表应返回错误。"""
        result = validate_batch_params(complexes=[], workers=1)
        self.assertFalse(result["valid"])
        self.assertIn("不能为空", result["errors"][0])

    def test_missing_receptor_path(self):
        """验证缺少 receptor_path 应返回错误。"""
        result = validate_batch_params(
            complexes=[{"ligand": "CCO"}],
            workers=1,
        )
        self.assertFalse(result["valid"])
        self.assertIn("receptor_path", result["errors"][0])

    def test_missing_ligand(self):
        """验证缺少 ligand 应返回错误。"""
        result = validate_batch_params(
            complexes=[{"receptor_path": "a.pdb"}],
            workers=1,
        )
        self.assertFalse(result["valid"])
        self.assertIn("ligand", result["errors"][0])

    def test_workers_too_high(self):
        """验证过高的 workers 应返回错误。"""
        result = validate_batch_params(
            complexes=[{"receptor_path": "a.pdb", "ligand": "CCO"}],
            workers=100,
        )
        self.assertFalse(result["valid"])
        self.assertIn("workers", str(result["errors"]))

    def test_large_batch_warning(self):
        """验证大批量任务应产生警告。"""
        complexes = [{"receptor_path": f"{i}.pdb", "ligand": "CCO"} for i in range(1001)]
        result = validate_batch_params(complexes=complexes, workers=1)
        self.assertTrue(result["valid"])
        self.assertIn("建议分批处理", str(result["warnings"]))


# ====================================================================
# TestValidateDockingScope — 适用范围校验测试
# ====================================================================


class TestValidateDockingScope(unittest.TestCase):
    """validate_docking_scope 函数测试。"""

    def test_valid_scope(self):
        """验证小分子对接应有效。"""
        result = validate_docking_scope("small_molecule")
        self.assertTrue(result["valid"])

    def test_protein_protein_rejected(self):
        """验证蛋白-蛋白对接应被拒绝。"""
        result = validate_docking_scope("protein_protein")
        self.assertFalse(result["valid"])
        self.assertIn("蛋白-蛋白", result["errors"][0])

    def test_covalent_rejected(self):
        """验证共价对接应被拒绝。"""
        result = validate_docking_scope("covalent")
        self.assertFalse(result["valid"])
        self.assertIn("共价", result["errors"][0])

    def test_large_peptide_rejected(self):
        """验证大肽对接应被拒绝。"""
        result = validate_docking_scope("large_peptide")
        self.assertFalse(result["valid"])
        self.assertIn("大肽", result["errors"][0])

    def test_case_insensitive(self):
        """验证对接类型应大小写不敏感。"""
        result = validate_docking_scope("PROTEIN_PROTEIN")
        self.assertFalse(result["valid"])


# ====================================================================
# TestValidateTopN — Top-N 参数校验测试
# ====================================================================


class TestValidateTopN(unittest.TestCase):
    """validate_top_n 函数测试。"""

    def test_valid_top_n(self):
        """验证有效 top_n 应返回无错误。"""
        result = validate_top_n(20)
        self.assertTrue(result["valid"])

    def test_top_n_too_high(self):
        """验证过高的 top_n 应返回错误。"""
        result = validate_top_n(2000)
        self.assertFalse(result["valid"])

    def test_top_n_exceeds_total(self):
        """验证 top_n 超过总位姿数应返回错误。"""
        result = validate_top_n(50, total_poses=10)
        self.assertFalse(result["valid"])
        self.assertIn("已有位姿总数", result["errors"][0])


# ====================================================================
# TestDockingModels — 命令模型测试
# ====================================================================


class TestDockingModels(unittest.TestCase):
    """DockSingle / DockBatch / AnalyzeDocking / ExportDocking 模型测试。"""

    def test_dock_single_creation(self):
        """验证 DockSingle 模型创建应正确设置字段值。"""
        cmd = DockSingle(
            project_id="proj-001",
            protein_path="/path/to/receptor.pdb",
            ligand="CCO",
            ligand_format="smiles",
            samples_per_complex=10,
            inference_steps=20,
            device="cpu",
        )
        self.assertEqual(cmd.project_id, "proj-001")
        self.assertEqual(cmd.protein_path, "/path/to/receptor.pdb")
        self.assertEqual(cmd.ligand, "CCO")
        self.assertEqual(cmd.ligand_format, "smiles")
        self.assertEqual(cmd.samples_per_complex, 10)
        self.assertEqual(cmd.inference_steps, 20)
        self.assertEqual(cmd.device, "cpu")

    def test_dock_single_defaults(self):
        """验证 DockSingle 默认值。"""
        cmd = DockSingle(
            project_id="proj-001",
            protein_path="/path/to/receptor.pdb",
            ligand="CCO",
        )
        self.assertEqual(cmd.ligand_format, "smiles")
        self.assertEqual(cmd.samples_per_complex, 10)
        self.assertEqual(cmd.inference_steps, 20)
        self.assertEqual(cmd.device, "cpu")

    def test_dock_batch_creation(self):
        """验证 DockBatch 模型创建。"""
        cmd = DockBatch(
            project_id="proj-001",
            complexes=[{"receptor_path": "a.pdb", "ligand": "CCO"}],
            config={"samples_per_complex": 10},
            workers=2,
        )
        self.assertEqual(cmd.project_id, "proj-001")
        self.assertEqual(len(cmd.complexes), 1)
        self.assertEqual(cmd.workers, 2)

    def test_analyze_docking_creation(self):
        """验证 AnalyzeDocking 模型创建。"""
        cmd = AnalyzeDocking(
            project_id="proj-001",
            workdir="/path/to/docking_results",
            top_n=20,
            confidence_threshold=0.5,
        )
        self.assertEqual(cmd.top_n, 20)
        self.assertEqual(cmd.confidence_threshold, 0.5)

    def test_export_docking_creation(self):
        """验证 ExportDocking 模型创建。"""
        cmd = ExportDocking(
            project_id="proj-001",
            workdir="/path/to/docking_results",
            format="sdf",
        )
        self.assertEqual(cmd.format, "sdf")


# ====================================================================
# TestDockingApplicationCapability — 能力标识测试
# ====================================================================


class TestDockingApplicationCapability(unittest.TestCase):
    """MolecularDockingApplication 能力标识测试。"""

    def setUp(self):
        self.app = MolecularDockingApplication(kernel=MagicMock())

    def test_capability_id(self):
        """验证 capability_id 应为 'molecular_docking'。"""
        self.assertEqual(self.app.capability_id, "molecular_docking")

    def test_display_name(self):
        """验证 display_name 应为中文名称。"""
        self.assertEqual(self.app.display_name, "分子对接")

    def test_description(self):
        """验证 description 应包含服务描述。"""
        self.assertIn("扩散模型", self.app.description)
        self.assertIn("分子对接", self.app.description)


# ====================================================================
# TestDockingApplicationValidate — validate 方法测试
# ====================================================================


class TestDockingApplicationValidate(unittest.TestCase):
    """MolecularDockingApplication.validate 方法测试。"""

    def setUp(self):
        self.app = MolecularDockingApplication(kernel=MagicMock())

    def test_validate_dock_single_valid(self):
        """验证有效单次对接输入应返回无错误结果。"""
        task = Task(
            project_id="proj-001",
            capability_id="molecular_docking",
            title="test",
            metadata={
                "command": "dock_single",
                "project_id": "proj-001",
                "protein_path": "/path/to/receptor.pdb",
                "ligand": "CCO",
                "ligand_format": "smiles",
                "samples_per_complex": 10,
                "inference_steps": 20,
            },
        )
        result = self.app.validate(task, {})
        self.assertTrue(result["valid"])

    def test_validate_dock_single_invalid_receptor(self):
        """验证无效受体格式应返回错误。"""
        task = Task(
            project_id="proj-001",
            capability_id="molecular_docking",
            title="test",
            metadata={
                "command": "dock_single",
                "project_id": "proj-001",
                "protein_path": "/path/to/receptor.xyz",
                "ligand": "CCO",
            },
        )
        result = self.app.validate(task, {})
        self.assertFalse(result["valid"])

    def test_validate_dock_single_empty_ligand(self):
        """验证空配体应返回错误。"""
        task = Task(
            project_id="proj-001",
            capability_id="molecular_docking",
            title="test",
            metadata={
                "command": "dock_single",
                "project_id": "proj-001",
                "protein_path": "/path/to/receptor.pdb",
                "ligand": "",
            },
        )
        result = self.app.validate(task, {})
        self.assertFalse(result["valid"])

    def test_validate_analyze_valid(self):
        """验证有效分析参数应返回无错误。"""
        task = Task(
            project_id="proj-001",
            capability_id="molecular_docking",
            title="test",
            metadata={
                "command": "analyze_docking",
                "project_id": "proj-001",
                "workdir": "/path/to/results",
                "top_n": 20,
                "confidence_threshold": 0.3,
            },
        )
        result = self.app.validate(task, {})
        self.assertTrue(result["valid"])

    def test_validate_export_valid(self):
        """验证有效导出参数应返回无错误。"""
        task = Task(
            project_id="proj-001",
            capability_id="molecular_docking",
            title="test",
            metadata={
                "command": "export_docking",
                "project_id": "proj-001",
                "workdir": "/path/to/results",
                "format": "csv",
            },
        )
        result = self.app.validate(task, {})
        self.assertTrue(result["valid"])

    def test_validate_export_invalid_format(self):
        """验证无效导出格式应返回错误。"""
        task = Task(
            project_id="proj-001",
            capability_id="molecular_docking",
            title="test",
            metadata={
                "command": "export_docking",
                "project_id": "proj-001",
                "workdir": "/path/to/results",
                "format": "pdf",
            },
        )
        result = self.app.validate(task, {})
        self.assertFalse(result["valid"])

    def test_validate_unknown_command(self):
        """验证未知命令应返回错误。"""
        task = Task(
            project_id="proj-001",
            capability_id="molecular_docking",
            title="test",
            metadata={"command": "unknown"},
        )
        result = self.app.validate(task, {})
        self.assertFalse(result["valid"])


# ====================================================================
# TestDockingApplicationPrepare — prepare 方法测试
# ====================================================================


class TestDockingApplicationPrepare(unittest.TestCase):
    """MolecularDockingApplication.prepare 方法测试。"""

    def setUp(self):
        self.app = MolecularDockingApplication(kernel=MagicMock())

    def test_prepare_dock_single(self):
        """验证 dock_single 应创建正确的 Run 实例。"""
        task = Task(
            task_id="task-001",
            project_id="proj-001",
            capability_id="molecular_docking",
            title="test",
            metadata={
                "command": "dock_single",
                "project_id": "proj-001",
                "protein_path": "/path/to/receptor.pdb",
                "ligand": "CCO",
                "ligand_format": "smiles",
                "samples_per_complex": 10,
                "inference_steps": 20,
                "device": "cpu",
            },
        )
        run = self.app.prepare(task)
        self.assertIsInstance(run, Run)
        self.assertEqual(run.task_id, "task-001")
        self.assertEqual(run.service_id, "molecular_docking")
        self.assertEqual(run.command, "dock_single")
        self.assertIn("protein_path", run.input)
        self.assertEqual(run.input["protein_path"], "/path/to/receptor.pdb")

    def test_prepare_dock_batch(self):
        """验证 dock_batch 应创建正确的 Run 实例。"""
        task = Task(
            task_id="task-002",
            project_id="proj-001",
            capability_id="molecular_docking",
            title="test",
            metadata={
                "command": "dock_batch",
                "project_id": "proj-001",
                "complexes": [{"receptor_path": "a.pdb", "ligand": "CCO"}],
                "config": {},
                "workers": 2,
            },
        )
        run = self.app.prepare(task)
        self.assertEqual(run.command, "dock_batch")
        self.assertEqual(len(run.input["complexes"]), 1)

    def test_prepare_analyze(self):
        """验证 analyze_docking 应创建正确的 Run 实例。"""
        task = Task(
            task_id="task-003",
            project_id="proj-001",
            capability_id="molecular_docking",
            title="test",
            metadata={
                "command": "analyze_docking",
                "project_id": "proj-001",
                "workdir": "/path/to/results",
                "top_n": 20,
                "confidence_threshold": 0.3,
            },
        )
        run = self.app.prepare(task)
        self.assertEqual(run.command, "analyze_docking")
        self.assertEqual(run.input["top_n"], 20)

    def test_prepare_export(self):
        """验证 export_docking 应创建正确的 Run 实例。"""
        task = Task(
            task_id="task-004",
            project_id="proj-001",
            capability_id="molecular_docking",
            title="test",
            metadata={
                "command": "export_docking",
                "project_id": "proj-001",
                "workdir": "/path/to/results",
                "format": "sdf",
            },
        )
        run = self.app.prepare(task)
        self.assertEqual(run.command, "export_docking")
        self.assertEqual(run.input["format"], "sdf")


# ====================================================================
# TestDockingApplicationExecute — execute 方法测试
# ====================================================================


class TestDockingApplicationExecute(unittest.TestCase):
    """MolecularDockingApplication.execute 方法测试。"""

    def setUp(self):
        self.app = MolecularDockingApplication(kernel=MagicMock())

    def test_execute_dock_single_returns_artifact_list(self):
        """验证 execute 应返回 Artifact 列表。"""
        run = Run(
            task_id="task-001",
            project_id="proj-001",
            service_id="molecular_docking",
            command="dock_single",
            input={
                "command": "dock_single",
                "project_id": "proj-001",
                "protein_path": "/path/to/receptor.pdb",
                "ligand": "CCO",
                "ligand_format": "smiles",
                "samples_per_complex": 10,
                "inference_steps": 20,
                "device": "cpu",
            },
        )
        artifacts = self.app.execute(run, {})
        self.assertIsInstance(artifacts, list)
        self.assertGreater(len(artifacts), 0)
        self.assertIsInstance(artifacts[0], Artifact)
        self.assertEqual(artifacts[0].type, ArtifactType.RESULT_TABLE)

    def test_execute_dock_single_with_placeholder(self):
        """验证 execute 使用占位适配器应返回占位结果。"""
        app = MolecularDockingApplication(kernel=MagicMock(), adapter=_PlaceholderAdapter())
        run = Run(
            task_id="task-001",
            project_id="proj-001",
            service_id="molecular_docking",
            command="dock_single",
            input={
                "command": "dock_single",
                "project_id": "proj-001",
                "protein_path": "/path/to/receptor.pdb",
                "ligand": "CCO",
                "samples_per_complex": 5,
                "inference_steps": 20,
                "device": "cpu",
            },
        )
        artifacts = app.execute(run, {})
        self.assertIn("results", artifacts[0].data)
        self.assertIn("poses", artifacts[0].data["results"][0])
        self.assertIn("warnings", artifacts[0].data)

    def test_execute_dock_single_high_confidence_creates_structure(self):
        """验证高置信度位姿应额外创建 STRUCTURE 类型 Artifact。"""
        app = MolecularDockingApplication(kernel=MagicMock(), adapter=_PlaceholderAdapter())
        run = Run(
            task_id="task-001",
            project_id="proj-001",
            service_id="molecular_docking",
            command="dock_single",
            input={
                "command": "dock_single",
                "project_id": "proj-001",
                "protein_path": "/path/to/receptor.pdb",
                "ligand": "CCO",
                "samples_per_complex": 10,
                "inference_steps": 20,
                "device": "cpu",
            },
        )
        artifacts = app.execute(run, {})
        artifact_types = [a.type for a in artifacts]
        self.assertIn(ArtifactType.STRUCTURE, artifact_types)
        self.assertIn(ArtifactType.RESULT_TABLE, artifact_types)

    def test_execute_dock_batch(self):
        """验证批量对接应返回摘要结果。"""
        app = MolecularDockingApplication(kernel=MagicMock(), adapter=_PlaceholderAdapter())
        run = Run(
            task_id="task-001",
            project_id="proj-001",
            service_id="molecular_docking",
            command="dock_batch",
            input={
                "command": "dock_batch",
                "project_id": "proj-001",
                "complexes": [
                    {"receptor_path": "a.pdb", "ligand": "CCO"},
                    {"receptor_path": "b.pdb", "ligand": "CCO"},
                ],
                "config": {"samples_per_complex": 5},
                "workers": 1,
            },
        )
        artifacts = app.execute(run, {})
        self.assertEqual(len(artifacts), 1)
        self.assertIn("summary", artifacts[0].data)
        self.assertIn("results", artifacts[0].data)

    def test_execute_analyze(self):
        """验证 analyze 应返回 REPORT 类型 Artifact。"""
        run = Run(
            task_id="task-001",
            project_id="proj-001",
            service_id="molecular_docking",
            command="analyze_docking",
            input={
                "command": "analyze_docking",
                "project_id": "proj-001",
                "workdir": "/path/to/results",
                "top_n": 20,
                "confidence_threshold": 0.3,
            },
        )
        artifacts = self.app.execute(run, {})
        self.assertEqual(len(artifacts), 1)
        self.assertEqual(artifacts[0].type, ArtifactType.REPORT)

    def test_execute_export(self):
        """验证 export 应返回 REPORT 类型 Artifact。"""
        run = Run(
            task_id="task-001",
            project_id="proj-001",
            service_id="molecular_docking",
            command="export_docking",
            input={
                "command": "export_docking",
                "project_id": "proj-001",
                "workdir": "/path/to/results",
                "format": "sdf",
            },
        )
        artifacts = self.app.execute(run, {})
        self.assertEqual(len(artifacts), 1)
        self.assertEqual(artifacts[0].type, ArtifactType.REPORT)

    def test_execute_unknown_command(self):
        """验证未知命令应返回空列表。"""
        run = Run(
            task_id="task-001",
            project_id="proj-001",
            service_id="molecular_docking",
            command="unknown",
            input={"command": "unknown"},
        )
        artifacts = self.app.execute(run, {})
        self.assertEqual(len(artifacts), 0)


# ====================================================================
# TestDockingApplicationPostprocess — postprocess 方法测试
# ====================================================================


class TestDockingApplicationPostprocess(unittest.TestCase):
    """MolecularDockingApplication.postprocess 方法测试。"""

    def setUp(self):
        self.app = MolecularDockingApplication(kernel=MagicMock())

    def test_postprocess_dock_single(self):
        """验证单次对接后处理应返回 EvidencePackage 列表。"""
        run = Run(
            run_id="run-001",
            task_id="task-001",
            project_id="proj-001",
            service_id="molecular_docking",
            command="dock_single",
            input={"command": "dock_single"},
        )
        artifacts = [
            Artifact(
                run_id="run-001",
                type=ArtifactType.RESULT_TABLE,
                name="docking_results",
                data={
                    "results": [
                        {
                            "status": "success",
                            "runtime_seconds": 45.0,
                            "poses": [
                                {"rank": 1, "confidence": 0.95, "sdf_path": "pose.sdf"},
                            ],
                        }
                    ],
                },
            )
        ]
        evidence = self.app.postprocess(run, artifacts)
        self.assertIsInstance(evidence, list)
        self.assertGreater(len(evidence), 0)
        self.assertIsInstance(evidence[0], EvidencePackage)

    def test_postprocess_dock_batch(self):
        """验证批量对接后处理应返回 EvidencePackage 列表。"""
        run = Run(
            run_id="run-001",
            task_id="task-001",
            project_id="proj-001",
            service_id="molecular_docking",
            command="dock_batch",
            input={"command": "dock_batch"},
        )
        artifacts = [
            Artifact(
                run_id="run-001",
                type=ArtifactType.RESULT_TABLE,
                name="batch_docking_results",
                data={
                    "results": [
                        {
                            "complex_index": 0,
                            "status": "success",
                            "runtime_seconds": 45.0,
                            "poses": [
                                {"rank": 1, "confidence": 0.95, "sdf_path": "pose.sdf"},
                            ],
                        }
                    ],
                    "summary": {
                        "best_confidence": 0.95,
                        "best_rank": 1,
                        "best_pose_path": "pose.sdf",
                        "total_complexes": 1,
                        "total_poses": 1,
                    },
                },
            )
        ]
        evidence = self.app.postprocess(run, artifacts)
        self.assertIsInstance(evidence, list)
        self.assertGreater(len(evidence), 0)

    def test_postprocess_empty_results(self):
        """验证无结果时应返回空列表。"""
        run = Run(
            run_id="run-001",
            task_id="task-001",
            project_id="proj-001",
            service_id="molecular_docking",
            command="dock_single",
            input={"command": "dock_single"},
        )
        evidence = self.app.postprocess(run, [])
        self.assertEqual(len(evidence), 0)

    def test_postprocess_no_results_in_artifact(self):
        """验证 Artifact 无 results 数据时应返回空列表。"""
        run = Run(
            run_id="run-001",
            task_id="task-001",
            project_id="proj-001",
            service_id="molecular_docking",
            command="dock_single",
            input={"command": "dock_single"},
        )
        artifacts = [
            Artifact(
                run_id="run-001",
                type=ArtifactType.RESULT_TABLE,
                name="docking_results",
                data={"warnings": []},
            )
        ]
        evidence = self.app.postprocess(run, artifacts)
        self.assertEqual(len(evidence), 0)


# ====================================================================
# TestDockingApplicationRunFullCycle — 完整生命周期测试
# ====================================================================


class TestDockingApplicationRunFullCycle(unittest.TestCase):
    """MolecularDockingApplication.run_full_cycle 完整生命周期测试。"""

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

        app = MolecularDockingApplication(kernel=mock_kernel, adapter=_PlaceholderAdapter())
        task = Task(
            project_id="proj-001",
            capability_id="molecular_docking",
            title="test",
            metadata={
                "command": "dock_single",
                "project_id": "proj-001",
                "protein_path": "/path/to/receptor.pdb",
                "ligand": "CCO",
                "samples_per_complex": 5,
                "inference_steps": 20,
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
        app = MolecularDockingApplication(kernel=mock_kernel)
        task = Task(
            project_id="proj-001",
            capability_id="molecular_docking",
            title="test",
            metadata={
                "command": "dock_single",
                "project_id": "proj-001",
                "protein_path": "/path/to/receptor.xyz",
                "ligand": "CCO",
            },
        )
        with self.assertRaises(ValueError):
            app.run_full_cycle(task)


# ====================================================================
# TestPlaceholderAdapter — 占位适配器测试
# ====================================================================


class TestPlaceholderAdapter(unittest.TestCase):
    """_PlaceholderAdapter 占位适配器测试。"""

    def setUp(self):
        self.adapter = _PlaceholderAdapter()

    def test_execute_returns_expected_structure(self):
        """验证 execute 应返回正确的结构。"""
        result = self.adapter.execute({
            "protein_path": "/path/to/receptor.pdb",
            "ligand": "CCO",
            "samples_per_complex": 10,
        })
        self.assertIn("status", result)
        self.assertEqual(result["status"], "completed")
        self.assertIn("poses", result)
        self.assertIn("warnings", result)
        self.assertIn("runtime_seconds", result)
        self.assertIn("receptor_path", result)
        self.assertIn("ligand", result)

    def test_execute_poses_count(self):
        """验证返回的位姿数量应不超过 5。"""
        result = self.adapter.execute({
            "protein_path": "a.pdb",
            "ligand": "CCO",
            "samples_per_complex": 100,
        })
        self.assertLessEqual(len(result["poses"]), 5)

    def test_parse_output_dict(self):
        """验证 parse_output 能正确处理 dict 输入。"""
        result = self.adapter.parse_output({"status": "completed", "poses": []})
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["poses"], [])

    def test_parse_output_non_dict(self):
        """验证 parse_output 能处理非 dict 输入。"""
        result = self.adapter.parse_output("not a dict")
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["poses"], [])

    def test_get_resource_requirements(self):
        """验证资源需求应返回默认值。"""
        reqs = self.adapter.get_resource_requirements({})
        self.assertIn("cpu", reqs)
        self.assertIn("memory_mb", reqs)
        self.assertIn("walltime_minutes", reqs)
        self.assertIn("gpu", reqs)

    def test_validate_input(self):
        """验证 validate_input 应返回空列表。"""
        errors = self.adapter.validate_input({"protein_path": "a.pdb"})
        self.assertEqual(errors, [])


# ====================================================================
# TestDockingEvidenceMapper — 证据映射测试
# ====================================================================


class TestDockingEvidenceMapper(unittest.TestCase):
    """evidence_mapper 函数测试。"""

    def test_map_docking_evidence_high_confidence(self):
        """验证高置信度应映射为 HIGH 级别。"""
        package = map_docking_evidence(
            run_id="run-001",
            task_id="task-001",
            pose_rank=1,
            pose_confidence=0.95,
            pose_sdf_path="/path/to/pose.sdf",
        )
        self.assertEqual(package.level, EvidenceLevel.HIGH)
        self.assertEqual(package.source_service, "real_engine:molecular_docking")
        self.assertEqual(package.method, "diffusion_docking")
        self.assertIn("Top-1", package.claim)

    def test_map_docking_evidence_medium_confidence(self):
        """验证中等置信度应映射为 MEDIUM 级别。"""
        package = map_docking_evidence(
            run_id="run-001",
            task_id="task-001",
            pose_rank=2,
            pose_confidence=0.80,
            pose_sdf_path="/path/to/pose.sdf",
        )
        self.assertEqual(package.level, EvidenceLevel.MEDIUM)

    def test_map_docking_evidence_low_confidence(self):
        """验证低置信度应映射为 LOW 级别。"""
        package = map_docking_evidence(
            run_id="run-001",
            task_id="task-001",
            pose_rank=3,
            pose_confidence=0.50,
            pose_sdf_path="/path/to/pose.sdf",
        )
        self.assertEqual(package.level, EvidenceLevel.LOW)

    def test_map_docking_evidence_boundary_high(self):
        """验证边界置信度 0.9 应映射为 HIGH 级别。"""
        package = map_docking_evidence(
            run_id="run-001", task_id="task-001",
            pose_rank=1, pose_confidence=0.9, pose_sdf_path="pose.sdf",
        )
        self.assertEqual(package.level, EvidenceLevel.HIGH)

    def test_map_docking_evidence_boundary_medium(self):
        """验证边界置信度 0.7 应映射为 MEDIUM 级别。"""
        package = map_docking_evidence(
            run_id="run-001", task_id="task-001",
            pose_rank=2, pose_confidence=0.7, pose_sdf_path="pose.sdf",
        )
        self.assertEqual(package.level, EvidenceLevel.MEDIUM)

    def test_map_docking_evidence_with_metadata(self):
        """验证附加元数据应被包含。"""
        package = map_docking_evidence(
            run_id="run-001", task_id="task-001",
            pose_rank=1, pose_confidence=0.95, pose_sdf_path="pose.sdf",
            metadata={"source": "test"},
        )
        self.assertIn("source", package.metadata)

    def test_map_docking_evidence_with_runtime(self):
        """验证运行时信息应被包含。"""
        package = map_docking_evidence(
            run_id="run-001", task_id="task-001",
            pose_rank=1, pose_confidence=0.95, pose_sdf_path="pose.sdf",
            runtime_seconds=45.2,
        )
        self.assertEqual(package.metadata["runtime_seconds"], 45.2)

    def test_batch_map_docking_evidence(self):
        """验证批量映射应返回正确数量的证据包。"""
        results = [
            {
                "complex_index": 0,
                "status": "success",
                "runtime_seconds": 45.0,
                "poses": [
                    {"rank": 1, "confidence": 0.95, "sdf_path": "pose_1.sdf"},
                    {"rank": 2, "confidence": 0.85, "sdf_path": "pose_2.sdf"},
                ],
            }
        ]
        packages = batch_map_docking_evidence(
            run_id="run-001", task_id="task-001", results=results,
        )
        self.assertEqual(len(packages), 2)
        self.assertIsInstance(packages[0], EvidencePackage)

    def test_batch_map_docking_evidence_empty(self):
        """验证空结果列表应返回空列表。"""
        packages = batch_map_docking_evidence(
            run_id="run-001", task_id="task-001", results=[],
        )
        self.assertEqual(len(packages), 0)

    def test_batch_map_docking_evidence_multiple_complexes(self):
        """验证多个复合物应正确映射。"""
        results = [
            {
                "complex_index": 0,
                "status": "success",
                "poses": [{"rank": 1, "confidence": 0.9, "sdf_path": "pose_1.sdf"}],
            },
            {
                "complex_index": 1,
                "status": "success",
                "poses": [{"rank": 1, "confidence": 0.8, "sdf_path": "pose_2.sdf"}],
            },
        ]
        packages = batch_map_docking_evidence(
            run_id="run-001", task_id="task-001", results=results,
        )
        self.assertEqual(len(packages), 2)

    def test_map_screen_summary(self):
        """验证筛选摘要映射应返回正确的 EvidencePackage。"""
        package = map_screen_summary(
            run_id="run-001",
            task_id="task-001",
            best_confidence=0.95,
            best_rank=1,
            best_pose_path="best_pose.sdf",
            total_complexes=100,
            total_poses=500,
        )
        self.assertEqual(package.level, EvidenceLevel.HIGH)
        self.assertEqual(package.method, "virtual_screening")
        self.assertIn("虚拟筛选", package.claim)
        self.assertEqual(package.metadata["total_complexes"], 100)
        self.assertEqual(package.metadata["total_poses"], 500)


# ====================================================================
# TestConstants — 常量定义完整性测试
# ====================================================================


class TestConstants(unittest.TestCase):
    """常量定义完整性测试。"""

    def test_receptor_formats_has_two_types(self):
        """验证受体格式应包含 PDB 和 mmCIF。"""
        self.assertIn("pdb", RECEPTOR_FORMATS)
        self.assertIn("mmcif", RECEPTOR_FORMATS)

    def test_ligand_formats_has_three_types(self):
        """验证配体格式应包含 SMILES/SDF/MOL2。"""
        self.assertIn("smiles", LIGAND_FORMATS)
        self.assertIn("sdf", LIGAND_FORMATS)
        self.assertIn("mol2", LIGAND_FORMATS)

    def test_ligand_mw_range(self):
        """验证分子量范围应为 100-1000。"""
        self.assertEqual(LIGAND_MW_RANGE, (100.0, 1000.0))

    def test_samples_range(self):
        """验证采样范围应为 1-50。"""
        self.assertEqual(SAMPLES_PER_COMPLEX_RANGE, (1, 50))

    def test_inference_steps_range(self):
        """验证推理步数范围应为 10-50。"""
        self.assertEqual(INFERENCE_STEPS_RANGE, (10, 50))

    def test_rejected_docking_types(self):
        """验证被拒绝的对接类型数量。"""
        self.assertEqual(len(REJECTED_DOCKING_TYPES), 3)


if __name__ == "__main__":
    unittest.main()