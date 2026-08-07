"""分子动力学模拟服务单元测试 — 完整生命周期验证。"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from battery_materials_agent.contracts.task import Task
from battery_materials_agent.contracts.run import Run
from battery_materials_agent.contracts.artifact import Artifact, ArtifactType
from battery_materials_agent.contracts.evidence import EvidencePackage, EvidenceLevel
from battery_materials_agent.services.molecular_simulation.application import (
    MolecularSimulationApplication,
    RunMolecularDynamics,
    _PlaceholderAdapter,
)
from battery_materials_agent.services.molecular_simulation.validators import (
    MolecularSimulationValidator,
    validate_system_type,
    validate_forcefield,
    validate_protocol,
    validate_temperature,
    validate_pressure,
    validate_metrics,
    SUPPORTED_METRICS,
    SYSTEM_TYPES,
    SUPPORTED_PROTOCOLS,
)
from battery_materials_agent.services.molecular_simulation.evidence_mapper import (
    map_md_evidence,
    batch_map_md_evidence,
)


class TestMolecularSimulationValidator(unittest.TestCase):
    """MolecularSimulationValidator 校验逻辑测试。"""

    def setUp(self):
        self.valid_kwargs = {
            "system_type": "A",
            "structure_data": "/path/to/structure.cif",
            "forcefield": "EAM",
            "protocol": "nvt",
            "temperature_k": 300.0,
            "pressure_atm": None,
            "timestep_fs": 1.0,
            "run_steps": 100000,
            "requested_metrics": ["rdf", "msd", "energy"],
        }

    def test_validate_all_valid_input(self):
        """验证有效输入应返回 valid=True 且无错误。"""
        validator = MolecularSimulationValidator(**self.valid_kwargs)
        result = validator.validate_all()
        self.assertTrue(result["valid"])
        self.assertEqual(len(result["errors"]), 0)
        self.assertIn("system_info", result)
        self.assertIn("resolved_forcefield", result)

    def test_validate_all_system_type_a(self):
        """验证系统类型 A 应通过校验。"""
        kwargs = dict(self.valid_kwargs)
        kwargs["system_type"] = "A"
        validator = MolecularSimulationValidator(**kwargs)
        result = validator.validate_all()
        self.assertTrue(result["valid"])

    def test_validate_all_system_type_b(self):
        """验证系统类型 B 应通过校验。"""
        kwargs = dict(self.valid_kwargs)
        kwargs["system_type"] = "B"
        kwargs["forcefield"] = "OPLS-AA"
        validator = MolecularSimulationValidator(**kwargs)
        result = validator.validate_all()
        self.assertTrue(result["valid"])

    def test_validate_all_system_type_c(self):
        """验证系统类型 C 应通过校验。"""
        kwargs = dict(self.valid_kwargs)
        kwargs["system_type"] = "C"
        kwargs["forcefield"] = "CHARMM"
        validator = MolecularSimulationValidator(**kwargs)
        result = validator.validate_all()
        self.assertTrue(result["valid"])

    def test_validate_all_empty_structure_data(self):
        """验证空 structure_data 应返回 valid=False。"""
        kwargs = dict(self.valid_kwargs)
        kwargs["structure_data"] = ""
        validator = MolecularSimulationValidator(**kwargs)
        result = validator.validate_all()
        self.assertFalse(result["valid"])
        self.assertIn("structure_data", result["errors"][0])

    def test_validate_all_invalid_system_type(self):
        """验证无效系统类型应返回 valid=False。"""
        kwargs = dict(self.valid_kwargs)
        kwargs["system_type"] = "X"
        validator = MolecularSimulationValidator(**kwargs)
        result = validator.validate_all()
        self.assertFalse(result["valid"])
        self.assertIn("system_type", result["errors"][0])

    def test_validate_all_incompatible_forcefield(self):
        """验证不兼容的力场应返回 valid=False。"""
        kwargs = dict(self.valid_kwargs)
        kwargs["system_type"] = "A"
        kwargs["forcefield"] = "CHARMM"
        validator = MolecularSimulationValidator(**kwargs)
        result = validator.validate_all()
        self.assertFalse(result["valid"])
        self.assertIn("CHARMM", str(result["errors"]))

    def test_validate_all_protocol_npt_requires_pressure(self):
        """验证 npt 协议缺少压力时应返回错误。"""
        kwargs = dict(self.valid_kwargs)
        kwargs["protocol"] = "npt"
        kwargs["pressure_atm"] = None
        validator = MolecularSimulationValidator(**kwargs)
        result = validator.validate_all()
        self.assertIn("pressure_atm", str(result["errors"]))

    def test_validate_all_protocol_npt_nvt_requires_pressure(self):
        """验证 npt_nvt 协议缺少压力时应返回错误。"""
        kwargs = dict(self.valid_kwargs)
        kwargs["protocol"] = "npt_nvt"
        kwargs["pressure_atm"] = None
        validator = MolecularSimulationValidator(**kwargs)
        result = validator.validate_all()
        self.assertIn("pressure_atm", str(result["errors"]))

    def test_validate_all_protocol_nve_no_temperature_required(self):
        """验证 nve 协议不要求温度时不应报错。"""
        kwargs = dict(self.valid_kwargs)
        kwargs["protocol"] = "nve"
        kwargs["temperature_k"] = None
        validator = MolecularSimulationValidator(**kwargs)
        result = validator.validate_all()
        self.assertTrue(result["valid"])

    def test_validate_all_protocol_minimize_no_temperature_required(self):
        """验证 minimize 协议不要求温度时不应报错。"""
        kwargs = dict(self.valid_kwargs)
        kwargs["protocol"] = "minimize"
        kwargs["temperature_k"] = None
        validator = MolecularSimulationValidator(**kwargs)
        result = validator.validate_all()
        self.assertTrue(result["valid"])

    def test_validate_all_timestep_negative(self):
        """验证负数时间步长应返回错误。"""
        kwargs = dict(self.valid_kwargs)
        kwargs["timestep_fs"] = -1.0
        validator = MolecularSimulationValidator(**kwargs)
        result = validator.validate_all()
        self.assertFalse(result["valid"])
        self.assertIn("timestep_fs", str(result["errors"]))

    def test_validate_all_timestep_large_warning(self):
        """验证过大时间步长应产生警告。"""
        kwargs = dict(self.valid_kwargs)
        kwargs["timestep_fs"] = 6.0
        validator = MolecularSimulationValidator(**kwargs)
        result = validator.validate_all()
        self.assertTrue(result["valid"])
        self.assertIn("时间步长", str(result["warnings"]))

    def test_validate_all_run_steps_negative(self):
        """验证负数运行步数应返回错误。"""
        kwargs = dict(self.valid_kwargs)
        kwargs["run_steps"] = -100
        validator = MolecularSimulationValidator(**kwargs)
        result = validator.validate_all()
        self.assertFalse(result["valid"])
        self.assertIn("run_steps", str(result["errors"]))

    def test_validate_all_run_steps_zero(self):
        """验证零运行步数应返回错误。"""
        kwargs = dict(self.valid_kwargs)
        kwargs["run_steps"] = 0
        validator = MolecularSimulationValidator(**kwargs)
        result = validator.validate_all()
        self.assertFalse(result["valid"])
        self.assertIn("run_steps", str(result["errors"]))

    def test_validate_all_unknown_metrics(self):
        """验证未知指标应产生警告。"""
        kwargs = dict(self.valid_kwargs)
        kwargs["requested_metrics"] = ["rdf", "unknown_metric"]
        validator = MolecularSimulationValidator(**kwargs)
        result = validator.validate_all()
        self.assertTrue(result["valid"])
        self.assertIn("unknown_metric", str(result["warnings"]))

    def test_validate_all_empty_metrics(self):
        """验证空指标列表不应产生警告。"""
        kwargs = dict(self.valid_kwargs)
        kwargs["requested_metrics"] = []
        validator = MolecularSimulationValidator(**kwargs)
        result = validator.validate_all()
        self.assertTrue(result["valid"])
        self.assertNotIn("valid_metrics", result)


class TestValidateSystemType(unittest.TestCase):
    """validate_system_type 函数测试。"""

    def test_valid_a(self):
        """验证系统类型 A 应返回有效结果。"""
        result = validate_system_type("A")
        self.assertTrue(result["valid"])
        self.assertIn("system_info", result)
        self.assertEqual(result["system_info"]["description"], "晶体/无机材料")

    def test_valid_b(self):
        """验证系统类型 B 应返回有效结果。"""
        result = validate_system_type("B")
        self.assertTrue(result["valid"])
        self.assertEqual(result["system_info"]["default_forcefield"], "OPLS-AA")

    def test_valid_c(self):
        """验证系统类型 C 应返回有效结果。"""
        result = validate_system_type("C")
        self.assertTrue(result["valid"])
        self.assertEqual(result["system_info"]["default_forcefield"], "CHARMM")

    def test_invalid_system_type(self):
        """验证无效系统类型应返回错误。"""
        result = validate_system_type("X")
        self.assertFalse(result["valid"])
        self.assertIn("system_type", result["errors"][0])

    def test_case_insensitive(self):
        """验证系统类型应大小写不敏感。"""
        result = validate_system_type("a")
        self.assertTrue(result["valid"])


class TestValidateForcefield(unittest.TestCase):
    """validate_forcefield 函数测试。"""

    def test_valid_compatible(self):
        """验证兼容力场应返回有效结果。"""
        result = validate_forcefield("EAM", "A")
        self.assertTrue(result["valid"])
        self.assertEqual(result["resolved_forcefield"], "EAM")

    def test_incompatible_forcefield(self):
        """验证不兼容力场应返回错误。"""
        result = validate_forcefield("CHARMM", "A")
        self.assertFalse(result["valid"])
        self.assertIn("CHARMM", str(result["errors"]))

    def test_none_forcefield_uses_default(self):
        """验证力场为 None 时应使用默认力场。"""
        result = validate_forcefield(None, "A")
        self.assertTrue(result["valid"])
        self.assertEqual(result["resolved_forcefield"], "EAM")

    def test_none_forcefield_system_b(self):
        """验证系统 B 默认力场为 OPLS-AA。"""
        result = validate_forcefield(None, "B")
        self.assertTrue(result["valid"])
        self.assertEqual(result["resolved_forcefield"], "OPLS-AA")

    def test_unknown_system_type(self):
        """验证未知系统类型应返回错误。"""
        result = validate_forcefield("EAM", "X")
        self.assertFalse(result["valid"])
        self.assertIn("未知系统类型", result["errors"][0])

    def test_forcefield_with_whitespace(self):
        """验证力场名称中的空白应被去除。"""
        result = validate_forcefield("  EAM  ", "A")
        self.assertTrue(result["valid"])
        self.assertEqual(result["resolved_forcefield"], "EAM")


class TestValidateProtocol(unittest.TestCase):
    """validate_protocol 函数测试。"""

    def test_valid_nvt(self):
        """验证 nvt 协议应返回有效结果。"""
        result = validate_protocol("nvt")
        self.assertTrue(result["valid"])
        self.assertTrue(result["protocol_info"]["requires_temperature"])
        self.assertFalse(result["protocol_info"]["requires_pressure"])

    def test_valid_npt(self):
        """验证 npt 协议应返回有效结果。"""
        result = validate_protocol("npt")
        self.assertTrue(result["valid"])
        self.assertTrue(result["protocol_info"]["requires_pressure"])

    def test_valid_nve(self):
        """验证 nve 协议应返回有效结果。"""
        result = validate_protocol("nve")
        self.assertTrue(result["valid"])
        self.assertFalse(result["protocol_info"]["requires_temperature"])

    def test_valid_minimize(self):
        """验证 minimize 协议应返回有效结果。"""
        result = validate_protocol("minimize")
        self.assertTrue(result["valid"])

    def test_valid_npt_nvt(self):
        """验证 npt_nvt 协议应返回有效结果。"""
        result = validate_protocol("npt_nvt")
        self.assertTrue(result["valid"])

    def test_invalid_protocol(self):
        """验证无效协议应返回错误。"""
        result = validate_protocol("invalid_protocol")
        self.assertFalse(result["valid"])
        self.assertIn("protocol", result["errors"][0])


class TestValidateTemperature(unittest.TestCase):
    """validate_temperature 函数测试。"""

    def test_valid_temperature(self):
        """验证有效温度应返回无错误结果。"""
        result = validate_temperature(300.0)
        self.assertTrue(result["valid"])
        self.assertEqual(len(result["errors"]), 0)

    def test_none_temperature_not_required(self):
        """验证 None 温度且非必需时不应报错。"""
        result = validate_temperature(None, required=False)
        self.assertTrue(result["valid"])

    def test_none_temperature_required(self):
        """验证 None 温度且必需时应返回错误。"""
        result = validate_temperature(None, required=True)
        self.assertFalse(result["valid"])
        self.assertIn("temperature_k", result["errors"][0])

    def test_negative_temperature(self):
        """验证负数温度应返回错误。"""
        result = validate_temperature(-10.0)
        self.assertFalse(result["valid"])
        self.assertIn("正数", result["errors"][0])

    def test_temperature_out_of_range_low(self):
        """验证过低温度应产生警告。"""
        result = validate_temperature(0.001)
        self.assertTrue(result["valid"])
        self.assertIn("温度", str(result["warnings"]))

    def test_temperature_out_of_range_high(self):
        """验证过高温度应产生警告。"""
        result = validate_temperature(50000.0)
        self.assertTrue(result["valid"])
        self.assertIn("温度", str(result["warnings"]))


class TestValidatePressure(unittest.TestCase):
    """validate_pressure 函数测试。"""

    def test_valid_pressure(self):
        """验证有效压力应返回无错误结果。"""
        result = validate_pressure(1.0)
        self.assertTrue(result["valid"])
        self.assertEqual(len(result["errors"]), 0)

    def test_none_pressure_not_required(self):
        """验证 None 压力且非必需时不应报错。"""
        result = validate_pressure(None, required=False)
        self.assertTrue(result["valid"])

    def test_none_pressure_required(self):
        """验证 None 压力且必需时应返回错误。"""
        result = validate_pressure(None, required=True)
        self.assertFalse(result["valid"])
        self.assertIn("pressure_atm", result["errors"][0])

    def test_negative_pressure(self):
        """验证负数压力应返回错误。"""
        result = validate_pressure(-1.0)
        self.assertFalse(result["valid"])
        self.assertIn("负数", result["errors"][0])

    def test_pressure_out_of_range_high(self):
        """验证过高压力应产生警告。"""
        result = validate_pressure(200000.0)
        self.assertTrue(result["valid"])
        self.assertIn("压力", str(result["warnings"]))


class TestValidateMetrics(unittest.TestCase):
    """validate_metrics 函数测试。"""

    def test_valid_metrics(self):
        """验证已知指标应返回有效结果。"""
        result = validate_metrics(["rdf", "msd", "energy"])
        self.assertTrue(result["valid"])
        self.assertEqual(len(result["valid_metrics"]), 3)
        self.assertEqual(len(result["unknown_metrics"]), 0)

    def test_mixed_metrics(self):
        """验证混合已知和未知指标应正确分离。"""
        result = validate_metrics(["rdf", "unknown_metric", "msd", "bad_metric"])
        self.assertFalse(result["valid"])
        self.assertEqual(len(result["valid_metrics"]), 2)
        self.assertEqual(len(result["unknown_metrics"]), 2)

    def test_empty_metrics(self):
        """验证空列表应返回空有效和未知指标。"""
        result = validate_metrics([])
        self.assertTrue(result["valid"])
        self.assertEqual(len(result["valid_metrics"]), 0)
        self.assertEqual(len(result["unknown_metrics"]), 0)

    def test_unknown_metrics_warning(self):
        """验证未知指标应产生警告。"""
        result = validate_metrics(["unknown_metric"])
        self.assertIn("未知指标", str(result["warnings"]))

    def test_case_insensitive(self):
        """验证指标名称应大小写不敏感。"""
        result = validate_metrics(["RDF", "MSD"])
        self.assertTrue(result["valid"])
        self.assertIn("rdf", result["valid_metrics"])
        self.assertIn("msd", result["valid_metrics"])


class TestRunMolecularDynamicsModel(unittest.TestCase):
    """RunMolecularDynamics Pydantic 模型测试。"""

    def test_model_creation(self):
        """验证模型创建应正确设置字段值。"""
        cmd = RunMolecularDynamics(
            project_id="proj-001",
            system_type="A",
            structure_data="/path/to/structure.cif",
            forcefield="EAM",
            protocol="nvt",
            temperature_k=300.0,
            pressure_atm=None,
            timestep_fs=1.0,
            run_steps=100000,
            requested_metrics=["rdf", "msd", "energy"],
        )
        self.assertEqual(cmd.project_id, "proj-001")
        self.assertEqual(cmd.system_type, "A")
        self.assertEqual(cmd.structure_data, "/path/to/structure.cif")
        self.assertEqual(cmd.forcefield, "EAM")
        self.assertEqual(cmd.protocol, "nvt")
        self.assertEqual(cmd.temperature_k, 300.0)
        self.assertIsNone(cmd.pressure_atm)
        self.assertEqual(cmd.timestep_fs, 1.0)
        self.assertEqual(cmd.run_steps, 100000)
        self.assertEqual(cmd.requested_metrics, ["rdf", "msd", "energy"])

    def test_default_forcefield(self):
        """验证默认 forcefield 应为 None。"""
        cmd = RunMolecularDynamics(
            project_id="proj-001",
            system_type="A",
            structure_data="/path/to/structure.cif",
        )
        self.assertIsNone(cmd.forcefield)

    def test_default_protocol(self):
        """验证默认 protocol 应为 nvt。"""
        cmd = RunMolecularDynamics(
            project_id="proj-001",
            system_type="A",
            structure_data="/path/to/structure.cif",
        )
        self.assertEqual(cmd.protocol, "nvt")

    def test_default_temperature(self):
        """验证默认 temperature_k 应为 300.0。"""
        cmd = RunMolecularDynamics(
            project_id="proj-001",
            system_type="A",
            structure_data="/path/to/structure.cif",
        )
        self.assertEqual(cmd.temperature_k, 300.0)

    def test_default_timestep(self):
        """验证默认 timestep_fs 应为 1.0。"""
        cmd = RunMolecularDynamics(
            project_id="proj-001",
            system_type="A",
            structure_data="/path/to/structure.cif",
        )
        self.assertEqual(cmd.timestep_fs, 1.0)

    def test_default_run_steps(self):
        """验证默认 run_steps 应为 100000。"""
        cmd = RunMolecularDynamics(
            project_id="proj-001",
            system_type="A",
            structure_data="/path/to/structure.cif",
        )
        self.assertEqual(cmd.run_steps, 100000)

    def test_default_requested_metrics(self):
        """验证默认 requested_metrics 应包含 rdf/msd/energy。"""
        cmd = RunMolecularDynamics(
            project_id="proj-001",
            system_type="A",
            structure_data="/path/to/structure.cif",
        )
        self.assertEqual(cmd.requested_metrics, ["rdf", "msd", "energy"])

    def test_npt_with_pressure(self):
        """验证 npt 协议可设置压力。"""
        cmd = RunMolecularDynamics(
            project_id="proj-001",
            system_type="A",
            structure_data="/path/to/structure.cif",
            protocol="npt",
            pressure_atm=1.0,
        )
        self.assertEqual(cmd.protocol, "npt")
        self.assertEqual(cmd.pressure_atm, 1.0)


class TestMolecularSimulationApplicationCapability(unittest.TestCase):
    """MolecularSimulationApplication 能力标识测试。"""

    def setUp(self):
        self.app = MolecularSimulationApplication(kernel=MagicMock())

    def test_capability_id(self):
        """验证 capability_id 应为 'molecular_simulation'。"""
        self.assertEqual(self.app.capability_id, "molecular_simulation")

    def test_display_name(self):
        """验证 display_name 应为中文名称。"""
        self.assertEqual(self.app.display_name, "分子动力学模拟")

    def test_description(self):
        """验证 description 应包含服务描述。"""
        self.assertIn("LAMMPS", self.app.description)
        self.assertIn("分子动力学", self.app.description)


class TestMolecularSimulationApplicationValidate(unittest.TestCase):
    """MolecularSimulationApplication.validate 方法测试。"""

    def setUp(self):
        self.app = MolecularSimulationApplication(kernel=MagicMock())

    def test_validate_valid_input(self):
        """验证有效输入应返回无错误结果。"""
        task = Task(
            project_id="proj-001",
            capability_id="molecular_simulation",
            title="test",
            metadata={
                "project_id": "proj-001",
                "system_type": "A",
                "structure_data": "/path/to/structure.cif",
                "forcefield": "EAM",
                "protocol": "nvt",
                "temperature_k": 300.0,
                "run_steps": 100000,
                "requested_metrics": ["rdf", "msd"],
            },
        )
        result = self.app.validate(task, {})
        self.assertTrue(result["valid"])

    def test_validate_empty_structure_data(self):
        """验证空 structure_data 应返回错误。"""
        task = Task(
            project_id="proj-001",
            capability_id="molecular_simulation",
            title="test",
            metadata={
                "project_id": "proj-001",
                "system_type": "A",
                "structure_data": "",
                "forcefield": "EAM",
                "protocol": "nvt",
            },
        )
        result = self.app.validate(task, {})
        self.assertFalse(result["valid"])

    def test_validate_invalid_system_type(self):
        """验证无效系统类型应返回错误。"""
        task = Task(
            project_id="proj-001",
            capability_id="molecular_simulation",
            title="test",
            metadata={
                "project_id": "proj-001",
                "system_type": "X",
                "structure_data": "/path/to/structure.cif",
                "forcefield": "EAM",
                "protocol": "nvt",
            },
        )
        result = self.app.validate(task, {})
        self.assertFalse(result["valid"])


class TestMolecularSimulationApplicationPrepare(unittest.TestCase):
    """MolecularSimulationApplication.prepare 方法测试。"""

    def setUp(self):
        self.app = MolecularSimulationApplication(kernel=MagicMock())

    def test_prepare_creates_run(self):
        """验证 prepare 应创建正确的 Run 实例。"""
        task = Task(
            task_id="task-001",
            project_id="proj-001",
            capability_id="molecular_simulation",
            title="test",
            metadata={
                "project_id": "proj-001",
                "system_type": "A",
                "structure_data": "/path/to/structure.cif",
                "forcefield": "EAM",
                "protocol": "nvt",
                "temperature_k": 300.0,
                "pressure_atm": None,
                "timestep_fs": 1.0,
                "run_steps": 100000,
                "requested_metrics": ["rdf", "msd"],
            },
        )
        run = self.app.prepare(task)
        self.assertIsInstance(run, Run)
        self.assertEqual(run.task_id, "task-001")
        self.assertEqual(run.service_id, "molecular_simulation")
        self.assertEqual(run.command, "run_molecular_dynamics")
        self.assertIn("system_type", run.input)
        self.assertEqual(run.input["system_type"], "A")
        self.assertEqual(run.input["structure_data"], "/path/to/structure.cif")
        self.assertIn("requested_metrics", run.input)


class TestMolecularSimulationApplicationExecute(unittest.TestCase):
    """MolecularSimulationApplication.execute 方法测试。"""

    def setUp(self):
        self.app = MolecularSimulationApplication(kernel=MagicMock())

    def test_execute_returns_artifact_list(self):
        """验证 execute 应返回 Artifact 列表。"""
        run = Run(
            task_id="task-001",
            project_id="proj-001",
            service_id="molecular_simulation",
            command="run_molecular_dynamics",
            input={
                "system_type": "A",
                "structure_data": "/path/to/structure.cif",
                "forcefield": "EAM",
                "protocol": "nvt",
                "temperature_k": 300.0,
                "pressure_atm": None,
                "timestep_fs": 1.0,
                "run_steps": 100000,
                "requested_metrics": ["rdf", "msd", "energy"],
            },
        )
        artifacts = self.app.execute(run, {})
        self.assertIsInstance(artifacts, list)
        self.assertGreater(len(artifacts), 0)
        self.assertIsInstance(artifacts[0], Artifact)
        self.assertEqual(artifacts[0].type, ArtifactType.RESULT_TABLE)

    def test_execute_with_placeholder_adapter(self):
        """验证 execute 使用占位适配器应返回占位结果。"""
        run = Run(
            task_id="task-001",
            project_id="proj-001",
            service_id="molecular_simulation",
            command="run_molecular_dynamics",
            input={
                "system_type": "B",
                "structure_data": "CCO",
                "forcefield": "OPLS-AA",
                "protocol": "nvt",
                "temperature_k": 300.0,
                "pressure_atm": None,
                "timestep_fs": 1.0,
                "run_steps": 100000,
                "requested_metrics": ["rdf"],
            },
        )
        artifacts = self.app.execute(run, {})
        self.assertIsInstance(artifacts, list)
        self.assertGreater(len(artifacts), 0)
        self.assertEqual(artifacts[0].type, ArtifactType.RESULT_TABLE)
        self.assertIn("analysis", artifacts[0].data)
        self.assertIn("warnings", artifacts[0].data)

    def test_execute_with_rdf_creates_plot_artifact(self):
        """验证包含 RDF 指标时应额外创建 PLOT 类型 Artifact。"""
        app = MolecularSimulationApplication(kernel=MagicMock(), adapter=_PlaceholderAdapter())
        run = Run(
            task_id="task-001",
            project_id="proj-001",
            service_id="molecular_simulation",
            command="run_molecular_dynamics",
            input={
                "system_type": "A",
                "structure_data": "/path/to/structure.cif",
                "forcefield": "EAM",
                "protocol": "nvt",
                "temperature_k": 300.0,
                "pressure_atm": None,
                "timestep_fs": 1.0,
                "run_steps": 100000,
                "requested_metrics": ["rdf", "msd"],
            },
        )
        artifacts = app.execute(run, {})
        artifact_types = [a.type for a in artifacts]
        self.assertIn(ArtifactType.PLOT, artifact_types)
        self.assertIn(ArtifactType.RESULT_TABLE, artifact_types)


class TestMolecularSimulationApplicationPostprocess(unittest.TestCase):
    """MolecularSimulationApplication.postprocess 方法测试。"""

    def setUp(self):
        self.app = MolecularSimulationApplication(kernel=MagicMock())

    def test_postprocess_returns_evidence_packages(self):
        """验证 postprocess 应返回 EvidencePackage 列表。"""
        run = Run(
            run_id="run-001",
            task_id="task-001",
            project_id="proj-001",
            service_id="molecular_simulation",
            command="run_molecular_dynamics",
        )
        artifacts = [
            Artifact(
                run_id="run-001",
                type=ArtifactType.RESULT_TABLE,
                name="md_analysis_results",
                data={
                    "analysis": [
                        {
                            "metric": "rdf",
                            "value": "# placeholder: rdf 分析结果",
                            "unit": "",
                            "confidence": 0.7,
                            "metadata": {"method": "placeholder"},
                        },
                        {
                            "metric": "msd",
                            "value": "# placeholder: msd 分析结果",
                            "unit": "",
                            "confidence": 0.7,
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
            service_id="molecular_simulation",
            command="run_molecular_dynamics",
        )
        evidence = self.app.postprocess(run, [])
        self.assertEqual(len(evidence), 0)

    def test_postprocess_no_analysis_in_artifact(self):
        """验证 Artifact 无 analysis 数据时应返回空列表。"""
        run = Run(
            run_id="run-001",
            task_id="task-001",
            project_id="proj-001",
            service_id="molecular_simulation",
            command="run_molecular_dynamics",
        )
        artifacts = [
            Artifact(
                run_id="run-001",
                type=ArtifactType.RESULT_TABLE,
                name="md_analysis_results",
                data={"warnings": [], "data_file": "data.lammps"},
            )
        ]
        evidence = self.app.postprocess(run, artifacts)
        self.assertEqual(len(evidence), 0)


class TestMolecularSimulationApplicationRunFullCycle(unittest.TestCase):
    """MolecularSimulationApplication.run_full_cycle 完整生命周期测试。"""

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

        app = MolecularSimulationApplication(kernel=mock_kernel, adapter=_PlaceholderAdapter())
        task = Task(
            project_id="proj-001",
            capability_id="molecular_simulation",
            title="test",
            metadata={
                "project_id": "proj-001",
                "system_type": "A",
                "structure_data": "/path/to/structure.cif",
                "forcefield": "EAM",
                "protocol": "nvt",
                "temperature_k": 300.0,
                "run_steps": 100000,
                "requested_metrics": ["rdf", "msd"],
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
        app = MolecularSimulationApplication(kernel=mock_kernel)
        task = Task(
            project_id="proj-001",
            capability_id="molecular_simulation",
            title="test",
            metadata={
                "project_id": "proj-001",
                "system_type": "A",
                "structure_data": "",
                "forcefield": "EAM",
                "protocol": "nvt",
            },
        )
        with self.assertRaises(ValueError):
            app.run_full_cycle(task)


class TestPlaceholderAdapter(unittest.TestCase):
    """_PlaceholderAdapter 占位适配器测试。"""

    def setUp(self):
        self.adapter = _PlaceholderAdapter()

    def test_execute_returns_expected_structure(self):
        """验证 execute 应返回正确的结构。"""
        result = self.adapter.execute({
            "system_type": "A",
            "protocol": "nvt",
            "temperature_k": 300.0,
            "run_steps": 100000,
            "requested_metrics": ["rdf", "msd"],
        })
        self.assertIn("status", result)
        self.assertEqual(result["status"], "completed")
        self.assertIn("analysis", result)
        self.assertIn("warnings", result)
        self.assertIn("data_file", result)
        self.assertIn("script_file", result)
        self.assertIn("log_file", result)
        self.assertIn("trajectory_file", result)
        self.assertEqual(len(result["analysis"]), 2)

    def test_execute_metrics_reflect_requested(self):
        """验证 execute 返回的指标应与请求一致。"""
        result = self.adapter.execute({
            "system_type": "B",
            "protocol": "npt",
            "temperature_k": 300.0,
            "run_steps": 100000,
            "requested_metrics": ["rdf", "msd", "energy"],
        })
        metrics = [a["metric"] for a in result["analysis"]]
        self.assertIn("rdf", metrics)
        self.assertIn("msd", metrics)
        self.assertIn("energy", metrics)

    def test_parse_output_dict(self):
        """验证 parse_output 能正确处理 dict 输入。"""
        result = self.adapter.parse_output({"status": "completed", "analysis": []})
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["analysis"], [])

    def test_parse_output_non_dict(self):
        """验证 parse_output 能处理非 dict 输入。"""
        result = self.adapter.parse_output("not a dict")
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["analysis"], [])

    def test_get_resource_requirements(self):
        """验证资源需求应返回默认值。"""
        reqs = self.adapter.get_resource_requirements({})
        self.assertIn("cpu", reqs)
        self.assertIn("memory_mb", reqs)
        self.assertIn("walltime_minutes", reqs)
        self.assertEqual(reqs["cpu"], 4)
        self.assertEqual(reqs["memory_mb"], 2048)
        self.assertEqual(reqs["walltime_minutes"], 30)

    def test_validate_input(self):
        """验证 validate_input 应返回空列表。"""
        errors = self.adapter.validate_input({"system_type": "A"})
        self.assertEqual(errors, [])


class TestEvidenceMapper(unittest.TestCase):
    """evidence_mapper 函数测试。"""

    def test_map_md_evidence_high_confidence(self):
        """验证高置信度应映射为 HIGH 级别。"""
        package = map_md_evidence(
            run_id="run-001",
            task_id="task-001",
            metric_name="rdf",
            value="rdf_data",
            unit="无量纲",
            confidence=0.95,
        )
        self.assertEqual(package.level, EvidenceLevel.HIGH)
        self.assertEqual(package.source_service, "real_engine:molecular_simulation")
        self.assertEqual(package.method, "molecular_dynamics_simulation")
        self.assertIn("径向分布函数", package.claim)

    def test_map_md_evidence_medium_confidence(self):
        """验证中等置信度应映射为 MEDIUM 级别。"""
        package = map_md_evidence(
            run_id="run-001",
            task_id="task-001",
            metric_name="msd",
            value="msd_data",
            confidence=0.80,
        )
        self.assertEqual(package.level, EvidenceLevel.MEDIUM)

    def test_map_md_evidence_low_confidence(self):
        """验证低置信度应映射为 LOW 级别。"""
        package = map_md_evidence(
            run_id="run-001",
            task_id="task-001",
            metric_name="diffusion_coefficient",
            value=1.23e-9,
            unit="m²/s",
            confidence=0.50,
        )
        self.assertEqual(package.level, EvidenceLevel.LOW)

    def test_map_md_evidence_boundary_high(self):
        """验证边界置信度 0.9 应映射为 HIGH 级别。"""
        package = map_md_evidence(
            run_id="run-001",
            task_id="task-001",
            metric_name="energy",
            value=-2.5,
            confidence=0.9,
        )
        self.assertEqual(package.level, EvidenceLevel.HIGH)

    def test_map_md_evidence_boundary_medium(self):
        """验证边界置信度 0.7 应映射为 MEDIUM 级别。"""
        package = map_md_evidence(
            run_id="run-001",
            task_id="task-001",
            metric_name="temperature",
            value=300.0,
            confidence=0.7,
        )
        self.assertEqual(package.level, EvidenceLevel.MEDIUM)

    def test_map_md_evidence_with_metadata(self):
        """验证附加元数据应被包含在证据包中。"""
        package = map_md_evidence(
            run_id="run-001",
            task_id="task-001",
            metric_name="rdf",
            value="data",
            metadata={"source": "test", "method": "placeholder"},
        )
        self.assertIn("source", package.metadata)
        self.assertEqual(package.metadata["source"], "test")

    def test_batch_map_md_evidence(self):
        """验证批量映射应返回正确数量的证据包。"""
        results = [
            {
                "metric": "rdf",
                "value": "rdf_data",
                "unit": "无量纲",
                "confidence": 0.9,
                "metadata": {"method": "placeholder"},
            },
            {
                "metric": "msd",
                "value": "msd_data",
                "unit": "Å²",
                "confidence": 0.85,
            },
            {
                "metric": "diffusion_coefficient",
                "value": 1.23e-9,
                "unit": "m²/s",
                "confidence": 0.75,
            },
        ]
        packages = batch_map_md_evidence(
            run_id="run-001",
            task_id="task-001",
            results=results,
        )
        self.assertEqual(len(packages), 3)
        self.assertIsInstance(packages[0], EvidencePackage)

    def test_batch_map_md_evidence_empty(self):
        """验证空结果列表应返回空列表。"""
        packages = batch_map_md_evidence(
            run_id="run-001",
            task_id="task-001",
            results=[],
        )
        self.assertEqual(len(packages), 0)


class TestConstants(unittest.TestCase):
    """常量定义完整性测试。"""

    def test_system_types_has_three_paths(self):
        """验证系统类型应包含 A/B/C 三条路径。"""
        self.assertIn("A", SYSTEM_TYPES)
        self.assertIn("B", SYSTEM_TYPES)
        self.assertIn("C", SYSTEM_TYPES)
        self.assertEqual(len(SYSTEM_TYPES), 3)

    def test_system_type_a_has_compatible_forcefields(self):
        """验证系统类型 A 的兼容力场集合。"""
        ff = SYSTEM_TYPES["A"]["compatible_forcefields"]
        self.assertIn("EAM", ff)
        self.assertIn("Buckingham", ff)
        self.assertIn("Tersoff", ff)
        self.assertIn("SW", ff)
        self.assertIn("ReaxFF", ff)

    def test_system_type_b_has_compatible_forcefields(self):
        """验证系统类型 B 的兼容力场集合。"""
        ff = SYSTEM_TYPES["B"]["compatible_forcefields"]
        self.assertIn("OPLS-AA", ff)
        self.assertIn("ReaxFF", ff)

    def test_system_type_c_has_compatible_forcefields(self):
        """验证系统类型 C 的兼容力场集合。"""
        ff = SYSTEM_TYPES["C"]["compatible_forcefields"]
        self.assertIn("CHARMM", ff)
        self.assertIn("AMBER", ff)
        self.assertIn("OPLS-AA", ff)

    def test_supported_protocols_count(self):
        """验证支持的协议数量。"""
        self.assertEqual(len(SUPPORTED_PROTOCOLS), 5)

    def test_npt_and_npt_nvt_require_pressure(self):
        """验证 npt 和 npt_nvt 协议需要压力。"""
        self.assertTrue(SUPPORTED_PROTOCOLS["npt"]["requires_pressure"])
        self.assertTrue(SUPPORTED_PROTOCOLS["npt_nvt"]["requires_pressure"])

    def test_nve_and_minimize_no_temperature_required(self):
        """验证 nve 和 minimize 协议不需要温度。"""
        self.assertFalse(SUPPORTED_PROTOCOLS["nve"]["requires_temperature"])
        self.assertFalse(SUPPORTED_PROTOCOLS["minimize"]["requires_temperature"])

    def test_supported_metrics_count(self):
        """验证支持的指标数量。"""
        self.assertEqual(len(SUPPORTED_METRICS), 11)

    def test_essential_metrics_present(self):
        """验证核心指标都存在。"""
        essential = ["rdf", "msd", "diffusion_coefficient", "rmsd", "rmsf", "energy"]
        for metric in essential:
            with self.subTest(metric=metric):
                self.assertIn(metric, SUPPORTED_METRICS)


if __name__ == "__main__":
    unittest.main()