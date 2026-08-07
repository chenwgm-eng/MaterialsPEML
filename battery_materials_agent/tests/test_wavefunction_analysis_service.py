"""波函数分析服务单元测试 — 完整生命周期验证。"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from battery_materials_agent.contracts.task import Task
from battery_materials_agent.contracts.run import Run
from battery_materials_agent.contracts.artifact import Artifact, ArtifactType
from battery_materials_agent.contracts.evidence import EvidencePackage, EvidenceLevel
from battery_materials_agent.services.wavefunction_analysis.application import (
    WavefunctionAnalysisApplication,
    AnalyzeESP,
    AnalyzeOrbitals,
    RenderOrbital,
    BatchAnalysis,
    _PlaceholderAdapter,
)
from battery_materials_agent.services.wavefunction_analysis.validators import (
    WavefunctionValidator,
    validate_file_format,
    validate_input_file,
    validate_surface_type,
    validate_bins,
    validate_orbital_range,
    validate_grid_quality,
    validate_render_engine,
    validate_image_format,
    validate_resolution,
    validate_batch_params,
    SUPPORTED_FILE_FORMATS,
    SUPPORTED_SURFACE_TYPES,
    SUPPORTED_GRID_QUALITIES,
    SUPPORTED_RENDER_ENGINES,
    SUPPORTED_IMAGE_FORMATS,
)
from battery_materials_agent.services.wavefunction_analysis.evidence_mapper import (
    map_wavefunction_evidence,
    batch_map_wavefunction_evidence,
)


# ====================================================================
# TestWavefunctionValidator
# ====================================================================


class TestWavefunctionValidator(unittest.TestCase):
    """WavefunctionValidator 校验逻辑测试。"""

    def setUp(self):
        self.valid_kwargs = {
            "input_file": "/path/to/structure.fchk",
            "file_format": "fchk",
            "surface_type": "molecular",
            "bins": 100,
            "generate_cubes": True,
            "below_homo": 3,
            "above_lumo": 3,
            "grid_quality": "high",
            "render_engine": "vmd",
            "image_format": "png",
            "width": 1800,
            "height": 1200,
            "workers": 1,
            "fail_fast": False,
        }

    def test_validate_all_valid_input(self):
        """验证有效输入应返回 valid=True 且无错误。"""
        validator = WavefunctionValidator(**self.valid_kwargs)
        result = validator.validate_all()
        self.assertTrue(result["valid"])
        self.assertEqual(len(result["errors"]), 0)
        self.assertIn("format_info", result)
        self.assertIn("surface_info", result)
        self.assertIn("engine_info", result)

    def test_validate_all_valid_molden(self):
        """验证 molden 格式应通过校验。"""
        kwargs = dict(self.valid_kwargs)
        kwargs["file_format"] = "molden"
        validator = WavefunctionValidator(**kwargs)
        result = validator.validate_all()
        self.assertTrue(result["valid"])

    def test_validate_all_valid_wfn(self):
        """验证 wfn 格式应通过校验。"""
        kwargs = dict(self.valid_kwargs)
        kwargs["file_format"] = "wfn"
        validator = WavefunctionValidator(**kwargs)
        result = validator.validate_all()
        self.assertTrue(result["valid"])

    def test_validate_all_valid_wfx(self):
        """验证 wfx 格式应通过校验。"""
        kwargs = dict(self.valid_kwargs)
        kwargs["file_format"] = "wfx"
        validator = WavefunctionValidator(**kwargs)
        result = validator.validate_all()
        self.assertTrue(result["valid"])

    def test_validate_all_invalid_file_format(self):
        """验证无效文件格式应返回 valid=False。"""
        kwargs = dict(self.valid_kwargs)
        kwargs["file_format"] = "xyz"
        validator = WavefunctionValidator(**kwargs)
        result = validator.validate_all()
        self.assertFalse(result["valid"])
        self.assertIn("file_format", result["errors"][0])

    def test_validate_all_empty_input_file(self):
        """验证空 input_file 应返回错误。"""
        kwargs = dict(self.valid_kwargs)
        kwargs["input_file"] = ""
        validator = WavefunctionValidator(**kwargs)
        result = validator.validate_all()
        self.assertFalse(result["valid"])
        self.assertIn("input_file", result["errors"][0])

    def test_validate_all_invalid_surface_type(self):
        """验证无效表面类型应返回错误。"""
        kwargs = dict(self.valid_kwargs)
        kwargs["surface_type"] = "invalid_surface"
        validator = WavefunctionValidator(**kwargs)
        result = validator.validate_all()
        self.assertFalse(result["valid"])
        self.assertIn("surface_type", result["errors"][0])

    def test_validate_all_bins_out_of_range_low(self):
        """验证 bins 过小应产生警告。"""
        kwargs = dict(self.valid_kwargs)
        kwargs["bins"] = 5
        validator = WavefunctionValidator(**kwargs)
        result = validator.validate_all()
        self.assertTrue(result["valid"])
        self.assertIn("bins", str(result["warnings"]))

    def test_validate_all_bins_out_of_range_high(self):
        """验证 bins 过大应产生警告。"""
        kwargs = dict(self.valid_kwargs)
        kwargs["bins"] = 2000
        validator = WavefunctionValidator(**kwargs)
        result = validator.validate_all()
        self.assertTrue(result["valid"])
        self.assertIn("bins", str(result["warnings"]))

    def test_validate_all_bins_negative(self):
        """验证负数 bins 应返回错误。"""
        kwargs = dict(self.valid_kwargs)
        kwargs["bins"] = -10
        validator = WavefunctionValidator(**kwargs)
        result = validator.validate_all()
        self.assertFalse(result["valid"])

    def test_validate_all_below_homo_negative(self):
        """验证负数 below_homo 应返回错误。"""
        kwargs = dict(self.valid_kwargs)
        kwargs["below_homo"] = -1
        validator = WavefunctionValidator(**kwargs)
        result = validator.validate_all()
        self.assertFalse(result["valid"])
        self.assertIn("below_homo", str(result["errors"]))

    def test_validate_all_below_homo_zero_above_lumo_zero(self):
        """验证 below_homo=0 且 above_lumo=0 应产生警告。"""
        kwargs = dict(self.valid_kwargs)
        kwargs["below_homo"] = 0
        kwargs["above_lumo"] = 0
        validator = WavefunctionValidator(**kwargs)
        result = validator.validate_all()
        self.assertTrue(result["valid"])
        self.assertIn("不产生任何轨道", str(result["warnings"]))

    def test_validate_all_grid_quality_invalid(self):
        """验证无效网格质量应返回错误。"""
        kwargs = dict(self.valid_kwargs)
        kwargs["grid_quality"] = "ultra"
        validator = WavefunctionValidator(**kwargs)
        result = validator.validate_all()
        self.assertFalse(result["valid"])
        self.assertIn("grid_quality", result["errors"][0])

    def test_validate_all_grid_quality_low(self):
        """验证 low 网格质量应通过校验。"""
        kwargs = dict(self.valid_kwargs)
        kwargs["grid_quality"] = "low"
        validator = WavefunctionValidator(**kwargs)
        result = validator.validate_all()
        self.assertTrue(result["valid"])

    def test_validate_all_grid_quality_very_high(self):
        """验证 very_high 网格质量应通过校验。"""
        kwargs = dict(self.valid_kwargs)
        kwargs["grid_quality"] = "very_high"
        validator = WavefunctionValidator(**kwargs)
        result = validator.validate_all()
        self.assertTrue(result["valid"])

    def test_validate_all_render_engine_invalid(self):
        """验证无效渲染引擎应返回错误。"""
        kwargs = dict(self.valid_kwargs)
        kwargs["render_engine"] = "blender"
        validator = WavefunctionValidator(**kwargs)
        result = validator.validate_all()
        self.assertFalse(result["valid"])
        self.assertIn("render_engine", result["errors"][0])

    def test_validate_all_render_engine_multiwfn(self):
        """验证 multiwfn 渲染引擎应通过校验。"""
        kwargs = dict(self.valid_kwargs)
        kwargs["render_engine"] = "multiwfn"
        validator = WavefunctionValidator(**kwargs)
        result = validator.validate_all()
        self.assertTrue(result["valid"])

    def test_validate_all_image_format_invalid(self):
        """验证无效图片格式应返回错误。"""
        kwargs = dict(self.valid_kwargs)
        kwargs["image_format"] = "gif"
        validator = WavefunctionValidator(**kwargs)
        result = validator.validate_all()
        self.assertFalse(result["valid"])
        self.assertIn("image_format", result["errors"][0])

    def test_validate_all_image_format_tiff(self):
        """验证 tiff 图片格式应通过校验。"""
        kwargs = dict(self.valid_kwargs)
        kwargs["image_format"] = "tiff"
        validator = WavefunctionValidator(**kwargs)
        result = validator.validate_all()
        self.assertTrue(result["valid"])

    def test_validate_all_resolution_too_low(self):
        """验证分辨率过低应返回错误。"""
        kwargs = dict(self.valid_kwargs)
        kwargs["width"] = 100
        kwargs["height"] = 100
        validator = WavefunctionValidator(**kwargs)
        result = validator.validate_all()
        self.assertFalse(result["valid"])
        self.assertIn("分辨率", str(result["errors"]))

    def test_validate_all_workers_negative(self):
        """验证负数 workers 应返回错误。"""
        kwargs = dict(self.valid_kwargs)
        kwargs["workers"] = -1
        validator = WavefunctionValidator(**kwargs)
        result = validator.validate_all()
        self.assertFalse(result["valid"])

    def test_validate_all_workers_out_of_range_high(self):
        """验证 workers 过大应产生警告。"""
        kwargs = dict(self.valid_kwargs)
        kwargs["workers"] = 200
        validator = WavefunctionValidator(**kwargs)
        result = validator.validate_all()
        self.assertTrue(result["valid"])
        self.assertIn("workers", str(result["warnings"]))

    def test_validate_all_fail_fast_with_workers(self):
        """验证 fail_fast=True 与 workers>1 结合应产生警告。"""
        kwargs = dict(self.valid_kwargs)
        kwargs["workers"] = 4
        kwargs["fail_fast"] = True
        validator = WavefunctionValidator(**kwargs)
        result = validator.validate_all()
        self.assertTrue(result["valid"])
        self.assertIn("fail_fast", str(result["warnings"]))


# ====================================================================
# TestValidateFileFormat
# ====================================================================


class TestValidateFileFormat(unittest.TestCase):
    """validate_file_format 函数测试。"""

    def test_valid_molden(self):
        """验证 molden 格式应返回有效结果。"""
        result = validate_file_format("molden")
        self.assertTrue(result["valid"])
        self.assertIn("format_info", result)

    def test_valid_fchk(self):
        """验证 fchk 格式应返回有效结果。"""
        result = validate_file_format("fchk")
        self.assertTrue(result["valid"])
        self.assertEqual(result["format_info"]["multiwfn_key"], 2)

    def test_valid_wfn(self):
        """验证 wfn 格式应返回有效结果。"""
        result = validate_file_format("wfn")
        self.assertTrue(result["valid"])
        self.assertEqual(result["format_info"]["multiwfn_key"], 3)

    def test_valid_wfx(self):
        """验证 wfx 格式应返回有效结果。"""
        result = validate_file_format("wfx")
        self.assertTrue(result["valid"])
        self.assertEqual(result["format_info"]["multiwfn_key"], 4)

    def test_invalid_format(self):
        """验证无效格式应返回错误。"""
        result = validate_file_format("cif")
        self.assertFalse(result["valid"])
        self.assertIn("file_format", result["errors"][0])

    def test_case_insensitive(self):
        """验证格式名称应大小写不敏感。"""
        result = validate_file_format("FCHK")
        self.assertTrue(result["valid"])

    def test_whitespace_handling(self):
        """验证格式名称中的空白应被去除。"""
        result = validate_file_format("  molden  ")
        self.assertTrue(result["valid"])


# ====================================================================
# TestValidateInputFile
# ====================================================================


class TestValidateInputFile(unittest.TestCase):
    """validate_input_file 函数测试。"""

    def test_empty_input_file(self):
        """验证空输入文件应返回错误。"""
        result = validate_input_file("")
        self.assertFalse(result["valid"])
        self.assertIn("input_file", result["errors"][0])

    def test_non_existent_file(self):
        """验证不存在的文件应产生警告。"""
        result = validate_input_file("/nonexistent/path.fchk")
        self.assertTrue(result["valid"])
        self.assertIn("文件不存在", str(result["warnings"]))


# ====================================================================
# TestValidateSurfaceType
# ====================================================================


class TestValidateSurfaceType(unittest.TestCase):
    """validate_surface_type 函数测试。"""

    def test_valid_molecular(self):
        """验证 molecular 表面类型应返回有效结果。"""
        result = validate_surface_type("molecular")
        self.assertTrue(result["valid"])
        self.assertIn("surface_info", result)

    def test_valid_vdw(self):
        """验证 vdw 表面类型应返回有效结果。"""
        result = validate_surface_type("vdw")
        self.assertTrue(result["valid"])

    def test_valid_electron_density(self):
        """验证 electron_density 表面类型应返回有效结果。"""
        result = validate_surface_type("electron_density")
        self.assertTrue(result["valid"])

    def test_invalid_surface_type(self):
        """验证无效表面类型应返回错误。"""
        result = validate_surface_type("solvent")
        self.assertFalse(result["valid"])
        self.assertIn("surface_type", result["errors"][0])

    def test_case_insensitive(self):
        """验证表面类型名称应大小写不敏感。"""
        result = validate_surface_type("MOLECULAR")
        self.assertTrue(result["valid"])


# ====================================================================
# TestValidateBins
# ====================================================================


class TestValidateBins(unittest.TestCase):
    """validate_bins 函数测试。"""

    def test_valid_bins(self):
        """验证有效 bins 应返回无错误结果。"""
        result = validate_bins(100)
        self.assertTrue(result["valid"])
        self.assertEqual(len(result["errors"]), 0)

    def test_bins_negative(self):
        """验证负数 bins 应返回错误。"""
        result = validate_bins(-1)
        self.assertFalse(result["valid"])
        self.assertIn("bins", result["errors"][0])

    def test_bins_zero(self):
        """验证 bins=0 应返回错误。"""
        result = validate_bins(0)
        self.assertFalse(result["valid"])

    def test_bins_out_of_range_low(self):
        """验证 bins 过小应产生警告。"""
        result = validate_bins(5)
        self.assertTrue(result["valid"])
        self.assertIn("bins", str(result["warnings"]))

    def test_bins_out_of_range_high(self):
        """验证 bins 过大应产生警告。"""
        result = validate_bins(2000)
        self.assertTrue(result["valid"])
        self.assertIn("bins", str(result["warnings"]))


# ====================================================================
# TestValidateGridQuality
# ====================================================================


class TestValidateGridQuality(unittest.TestCase):
    """validate_grid_quality 函数测试。"""

    def test_valid_low(self):
        """验证 low 网格质量应返回有效结果。"""
        result = validate_grid_quality("low")
        self.assertTrue(result["valid"])
        self.assertEqual(result["quality_key"], 1)

    def test_valid_medium(self):
        """验证 medium 网格质量应返回有效结果。"""
        result = validate_grid_quality("medium")
        self.assertTrue(result["valid"])
        self.assertEqual(result["quality_key"], 2)

    def test_valid_high(self):
        """验证 high 网格质量应返回有效结果。"""
        result = validate_grid_quality("high")
        self.assertTrue(result["valid"])
        self.assertEqual(result["quality_key"], 3)

    def test_valid_very_high(self):
        """验证 very_high 网格质量应返回有效结果。"""
        result = validate_grid_quality("very_high")
        self.assertTrue(result["valid"])
        self.assertEqual(result["quality_key"], 4)

    def test_invalid_quality(self):
        """验证无效网格质量应返回错误。"""
        result = validate_grid_quality("ultra")
        self.assertFalse(result["valid"])
        self.assertIn("grid_quality", result["errors"][0])


# ====================================================================
# TestValidateRenderEngine
# ====================================================================


class TestValidateRenderEngine(unittest.TestCase):
    """validate_render_engine 函数测试。"""

    def test_valid_vmd(self):
        """验证 vmd 渲染引擎应返回有效结果。"""
        result = validate_render_engine("vmd")
        self.assertTrue(result["valid"])
        self.assertIn("engine_info", result)

    def test_valid_multiwfn(self):
        """验证 multiwfn 渲染引擎应返回有效结果。"""
        result = validate_render_engine("multiwfn")
        self.assertTrue(result["valid"])

    def test_invalid_engine(self):
        """验证无效渲染引擎应返回错误。"""
        result = validate_render_engine("blender")
        self.assertFalse(result["valid"])
        self.assertIn("render_engine", result["errors"][0])


# ====================================================================
# TestValidateImageFormat
# ====================================================================


class TestValidateImageFormat(unittest.TestCase):
    """validate_image_format 函数测试。"""

    def test_valid_png(self):
        """验证 png 格式应返回有效结果。"""
        result = validate_image_format("png")
        self.assertTrue(result["valid"])
        self.assertIn("format_info", result)

    def test_valid_tiff(self):
        """验证 tiff 格式应返回有效结果。"""
        result = validate_image_format("tiff")
        self.assertTrue(result["valid"])

    def test_valid_bmp(self):
        """验证 bmp 格式应返回有效结果。"""
        result = validate_image_format("bmp")
        self.assertTrue(result["valid"])

    def test_valid_jpg(self):
        """验证 jpg 格式应返回有效结果。"""
        result = validate_image_format("jpg")
        self.assertTrue(result["valid"])

    def test_valid_tga(self):
        """验证 tga 格式应返回有效结果。"""
        result = validate_image_format("tga")
        self.assertTrue(result["valid"])

    def test_invalid_format(self):
        """验证无效图片格式应返回错误。"""
        result = validate_image_format("gif")
        self.assertFalse(result["valid"])
        self.assertIn("image_format", result["errors"][0])


# ====================================================================
# TestValidateResolution
# ====================================================================


class TestValidateResolution(unittest.TestCase):
    """validate_resolution 函数测试。"""

    def test_valid_resolution(self):
        """验证有效分辨率应返回无错误结果。"""
        result = validate_resolution(1800, 1200)
        self.assertTrue(result["valid"])
        self.assertEqual(len(result["errors"]), 0)

    def test_resolution_too_low(self):
        """验证分辨率过低应返回错误。"""
        result = validate_resolution(100, 100)
        self.assertFalse(result["valid"])
        self.assertIn("分辨率", str(result["errors"]))

    def test_resolution_too_high(self):
        """验证分辨率过高应产生警告。"""
        result = validate_resolution(5000, 4000)
        self.assertTrue(result["valid"])
        self.assertIn("分辨率", str(result["warnings"]))

    def test_resolution_negative_width(self):
        """验证负数宽度应返回错误。"""
        result = validate_resolution(-100, 1200)
        self.assertFalse(result["valid"])
        self.assertIn("正整数", str(result["errors"]))

    def test_resolution_zero_height(self):
        """验证零高度应返回错误。"""
        result = validate_resolution(1800, 0)
        self.assertFalse(result["valid"])
        self.assertIn("正整数", str(result["errors"]))


# ====================================================================
# TestValidateBatchParams
# ====================================================================


class TestValidateBatchParams(unittest.TestCase):
    """validate_batch_params 函数测试。"""

    def test_valid_params(self):
        """验证有效批量参数应返回无错误结果。"""
        result = validate_batch_params(1, False)
        self.assertTrue(result["valid"])
        self.assertEqual(len(result["errors"]), 0)

    def test_workers_negative(self):
        """验证负数 workers 应返回错误。"""
        result = validate_batch_params(-1, False)
        self.assertFalse(result["valid"])
        self.assertIn("workers", result["errors"][0])

    def test_workers_zero(self):
        """验证 workers=0 应返回错误。"""
        result = validate_batch_params(0, False)
        self.assertFalse(result["valid"])

    def test_workers_too_many(self):
        """验证 workers 过多应产生警告。"""
        result = validate_batch_params(200, False)
        self.assertTrue(result["valid"])
        self.assertIn("workers", str(result["warnings"]))

    def test_fail_fast_with_parallel(self):
        """验证 fail_fast 与并行结合应产生警告。"""
        result = validate_batch_params(4, True)
        self.assertTrue(result["valid"])
        self.assertIn("fail_fast", str(result["warnings"]))


# ====================================================================
# TestValidateOrbitalRange
# ====================================================================


class TestValidateOrbitalRange(unittest.TestCase):
    """validate_orbital_range 函数测试。"""

    def test_valid_range(self):
        """验证有效轨道范围应返回无错误结果。"""
        result = validate_orbital_range(3, 3)
        self.assertTrue(result["valid"])
        self.assertEqual(len(result["errors"]), 0)

    def test_negative_below_homo(self):
        """验证负数 below_homo 应返回错误。"""
        result = validate_orbital_range(-1, 3)
        self.assertFalse(result["valid"])
        self.assertIn("below_homo", str(result["errors"]))

    def test_negative_above_lumo(self):
        """验证负数 above_lumo 应返回错误。"""
        result = validate_orbital_range(3, -1)
        self.assertFalse(result["valid"])
        self.assertIn("above_lumo", str(result["errors"]))

    def test_both_zero(self):
        """验证两者均为零应产生警告。"""
        result = validate_orbital_range(0, 0)
        self.assertTrue(result["valid"])
        self.assertIn("不产生任何轨道", str(result["warnings"]))

    def test_range_too_large(self):
        """验证范围过大应产生警告。"""
        result = validate_orbital_range(15, 15)
        self.assertTrue(result["valid"])
        self.assertIn("超出常用范围", str(result["warnings"]))


# ====================================================================
# TestCommandModels
# ====================================================================


class TestAnalyzeESPModel(unittest.TestCase):
    """AnalyzeESP Pydantic 模型测试。"""

    def test_model_creation(self):
        """验证模型创建应正确设置字段值。"""
        cmd = AnalyzeESP(
            project_id="proj-001",
            input_file="/path/to/structure.fchk",
            file_format="fchk",
            surface_type="molecular",
            bins=100,
            generate_cubes=True,
        )
        self.assertEqual(cmd.project_id, "proj-001")
        self.assertEqual(cmd.input_file, "/path/to/structure.fchk")
        self.assertEqual(cmd.file_format, "fchk")
        self.assertEqual(cmd.surface_type, "molecular")
        self.assertEqual(cmd.bins, 100)
        self.assertTrue(cmd.generate_cubes)

    def test_default_surface_type(self):
        """验证默认 surface_type 应为 molecular。"""
        cmd = AnalyzeESP(
            project_id="proj-001",
            input_file="/path/to/structure.fchk",
            file_format="fchk",
        )
        self.assertEqual(cmd.surface_type, "molecular")

    def test_default_bins(self):
        """验证默认 bins 应为 100。"""
        cmd = AnalyzeESP(
            project_id="proj-001",
            input_file="/path/to/structure.fchk",
            file_format="fchk",
        )
        self.assertEqual(cmd.bins, 100)

    def test_default_generate_cubes(self):
        """验证默认 generate_cubes 应为 True。"""
        cmd = AnalyzeESP(
            project_id="proj-001",
            input_file="/path/to/structure.fchk",
            file_format="fchk",
        )
        self.assertTrue(cmd.generate_cubes)


class TestAnalyzeOrbitalsModel(unittest.TestCase):
    """AnalyzeOrbitals Pydantic 模型测试。"""

    def test_model_creation(self):
        """验证模型创建应正确设置字段值。"""
        cmd = AnalyzeOrbitals(
            project_id="proj-001",
            input_file="/path/to/structure.fchk",
            file_format="fchk",
            below_homo=3,
            above_lumo=3,
            grid_quality="high",
        )
        self.assertEqual(cmd.project_id, "proj-001")
        self.assertEqual(cmd.below_homo, 3)
        self.assertEqual(cmd.above_lumo, 3)
        self.assertEqual(cmd.grid_quality, "high")

    def test_default_below_homo(self):
        """验证默认 below_homo 应为 3。"""
        cmd = AnalyzeOrbitals(
            project_id="proj-001",
            input_file="/path/to/structure.fchk",
            file_format="fchk",
        )
        self.assertEqual(cmd.below_homo, 3)

    def test_default_above_lumo(self):
        """验证默认 above_lumo 应为 3。"""
        cmd = AnalyzeOrbitals(
            project_id="proj-001",
            input_file="/path/to/structure.fchk",
            file_format="fchk",
        )
        self.assertEqual(cmd.above_lumo, 3)

    def test_default_grid_quality(self):
        """验证默认 grid_quality 应为 high。"""
        cmd = AnalyzeOrbitals(
            project_id="proj-001",
            input_file="/path/to/structure.fchk",
            file_format="fchk",
        )
        self.assertEqual(cmd.grid_quality, "high")


class TestRenderOrbitalModel(unittest.TestCase):
    """RenderOrbital Pydantic 模型测试。"""

    def test_model_creation(self):
        """验证模型创建应正确设置字段值。"""
        cmd = RenderOrbital(
            project_id="proj-001",
            input_dir="/path/to/cubes",
            render_type="orbital",
            image_format="png",
            width=1800,
            height=1200,
        )
        self.assertEqual(cmd.project_id, "proj-001")
        self.assertEqual(cmd.input_dir, "/path/to/cubes")
        self.assertEqual(cmd.render_type, "orbital")
        self.assertEqual(cmd.image_format, "png")
        self.assertEqual(cmd.width, 1800)
        self.assertEqual(cmd.height, 1200)

    def test_default_image_format(self):
        """验证默认 image_format 应为 png。"""
        cmd = RenderOrbital(
            project_id="proj-001",
            input_dir="/path/to/cubes",
            render_type="esp",
        )
        self.assertEqual(cmd.image_format, "png")

    def test_default_width_height(self):
        """验证默认分辨率应为 1800x1200。"""
        cmd = RenderOrbital(
            project_id="proj-001",
            input_dir="/path/to/cubes",
            render_type="esp",
        )
        self.assertEqual(cmd.width, 1800)
        self.assertEqual(cmd.height, 1200)


class TestBatchAnalysisModel(unittest.TestCase):
    """BatchAnalysis Pydantic 模型测试。"""

    def test_model_creation(self):
        """验证模型创建应正确设置字段值。"""
        cmd = BatchAnalysis(
            project_id="proj-001",
            files=["/path/to/file1.fchk", "/path/to/file2.fchk"],
            mode="esp",
            workers=2,
            fail_fast=True,
        )
        self.assertEqual(cmd.project_id, "proj-001")
        self.assertEqual(len(cmd.files), 2)
        self.assertEqual(cmd.mode, "esp")
        self.assertEqual(cmd.workers, 2)
        self.assertTrue(cmd.fail_fast)

    def test_default_workers(self):
        """验证默认 workers 应为 1。"""
        cmd = BatchAnalysis(
            project_id="proj-001",
            files=["/path/to/file.fchk"],
            mode="esp",
        )
        self.assertEqual(cmd.workers, 1)

    def test_default_fail_fast(self):
        """验证默认 fail_fast 应为 False。"""
        cmd = BatchAnalysis(
            project_id="proj-001",
            files=["/path/to/file.fchk"],
            mode="esp",
        )
        self.assertFalse(cmd.fail_fast)


# ====================================================================
# TestWavefunctionApplicationCapability
# ====================================================================


class TestWavefunctionApplicationCapability(unittest.TestCase):
    """WavefunctionAnalysisApplication 能力标识测试。"""

    def setUp(self):
        self.app = WavefunctionAnalysisApplication(kernel=MagicMock())

    def test_capability_id(self):
        """验证 capability_id 应为 'wavefunction_analysis'。"""
        self.assertEqual(self.app.capability_id, "wavefunction_analysis")

    def test_display_name(self):
        """验证 display_name 应为中文名称。"""
        self.assertEqual(self.app.display_name, "波函数分析")

    def test_description(self):
        """验证 description 应包含服务描述。"""
        self.assertIn("Multiwfn", self.app.description)
        self.assertIn("波函数", self.app.description)


# ====================================================================
# TestWavefunctionApplicationValidate
# ====================================================================


class TestWavefunctionApplicationValidate(unittest.TestCase):
    """WavefunctionAnalysisApplication.validate 方法测试。"""

    def setUp(self):
        self.app = WavefunctionAnalysisApplication(kernel=MagicMock())

    def test_validate_valid_esp_input(self):
        """验证有效 ESP 输入应返回无错误结果。"""
        task = Task(
            project_id="proj-001",
            capability_id="wavefunction_analysis",
            title="test",
            metadata={
                "command": "analyze_esp",
                "input_file": "/path/to/structure.fchk",
                "file_format": "fchk",
                "surface_type": "molecular",
                "bins": 100,
            },
        )
        result = self.app.validate(task, {})
        self.assertTrue(result["valid"])

    def test_validate_invalid_file_format(self):
        """验证无效文件格式应返回错误。"""
        task = Task(
            project_id="proj-001",
            capability_id="wavefunction_analysis",
            title="test",
            metadata={
                "command": "analyze_esp",
                "input_file": "/path/to/structure.xyz",
                "file_format": "xyz",
                "surface_type": "molecular",
                "bins": 100,
            },
        )
        result = self.app.validate(task, {})
        self.assertFalse(result["valid"])

    def test_validate_empty_input_file(self):
        """验证空 input_file 应返回错误。"""
        task = Task(
            project_id="proj-001",
            capability_id="wavefunction_analysis",
            title="test",
            metadata={
                "command": "analyze_esp",
                "input_file": "",
                "file_format": "fchk",
            },
        )
        result = self.app.validate(task, {})
        self.assertFalse(result["valid"])


# ====================================================================
# TestWavefunctionApplicationPrepare
# ====================================================================


class TestWavefunctionApplicationPrepare(unittest.TestCase):
    """WavefunctionAnalysisApplication.prepare 方法测试。"""

    def setUp(self):
        self.app = WavefunctionAnalysisApplication(kernel=MagicMock())

    def test_prepare_creates_run(self):
        """验证 prepare 应创建正确的 Run 实例。"""
        task = Task(
            task_id="task-001",
            project_id="proj-001",
            capability_id="wavefunction_analysis",
            title="test",
            metadata={
                "command": "analyze_esp",
                "input_file": "/path/to/structure.fchk",
                "file_format": "fchk",
                "surface_type": "molecular",
                "bins": 100,
            },
        )
        run = self.app.prepare(task)
        self.assertIsInstance(run, Run)
        self.assertEqual(run.task_id, "task-001")
        self.assertEqual(run.service_id, "wavefunction_analysis")
        self.assertEqual(run.command, "analyze_esp")
        self.assertIn("input_file", run.input)
        self.assertEqual(run.input["file_format"], "fchk")


# ====================================================================
# TestWavefunctionApplicationExecute
# ====================================================================


class TestWavefunctionApplicationExecute(unittest.TestCase):
    """WavefunctionAnalysisApplication.execute 方法测试。"""

    def setUp(self):
        self.app = WavefunctionAnalysisApplication(kernel=MagicMock())

    def test_execute_esp_returns_artifact_list(self):
        """验证 execute ESP 应返回 Artifact 列表。"""
        run = Run(
            task_id="task-001",
            project_id="proj-001",
            service_id="wavefunction_analysis",
            command="analyze_esp",
            input={
                "input_file": "/path/to/structure.fchk",
                "file_format": "fchk",
                "surface_type": "molecular",
                "bins": 100,
                "generate_cubes": True,
            },
        )
        artifacts = self.app.execute(run, {})
        self.assertIsInstance(artifacts, list)
        self.assertGreater(len(artifacts), 0)
        self.assertIsInstance(artifacts[0], Artifact)
        self.assertEqual(artifacts[0].type, ArtifactType.RESULT_TABLE)

    def test_execute_orbitals_returns_artifact_list(self):
        """验证 execute 轨道分析应返回 Artifact 列表。"""
        run = Run(
            task_id="task-001",
            project_id="proj-001",
            service_id="wavefunction_analysis",
            command="analyze_orbitals",
            input={
                "input_file": "/path/to/structure.fchk",
                "file_format": "fchk",
                "below_homo": 3,
                "above_lumo": 3,
                "grid_quality": "high",
            },
        )
        artifacts = self.app.execute(run, {})
        self.assertIsInstance(artifacts, list)
        self.assertGreater(len(artifacts), 0)
        self.assertIsInstance(artifacts[0], Artifact)

    def test_execute_render_returns_artifact_list(self):
        """验证 execute 渲染应返回 Artifact 列表。"""
        run = Run(
            task_id="task-001",
            project_id="proj-001",
            service_id="wavefunction_analysis",
            command="render_orbital",
            input={
                "input_dir": "/path/to/cubes",
                "render_type": "orbital",
                "image_format": "png",
                "width": 1800,
                "height": 1200,
            },
        )
        artifacts = self.app.execute(run, {})
        self.assertIsInstance(artifacts, list)
        self.assertGreater(len(artifacts), 0)
        self.assertIsInstance(artifacts[0], Artifact)

    def test_execute_unknown_command(self):
        """验证未知命令应返回空结果。"""
        run = Run(
            task_id="task-001",
            project_id="proj-001",
            service_id="wavefunction_analysis",
            command="unknown_command",
            input={},
        )
        artifacts = self.app.execute(run, {})
        self.assertIsInstance(artifacts, list)
        self.assertEqual(len(artifacts), 1)
        self.assertIn("warnings", artifacts[0].data)
        self.assertIn("未知命令", str(artifacts[0].data["warnings"]))

    def test_execute_with_placeholder_adapter(self):
        """验证 execute 使用占位适配器应返回占位结果。"""
        app = WavefunctionAnalysisApplication(kernel=MagicMock(), adapter=_PlaceholderAdapter())
        run = Run(
            task_id="task-001",
            project_id="proj-001",
            service_id="wavefunction_analysis",
            command="analyze_esp",
            input={
                "input_file": "/path/to/structure.fchk",
                "file_format": "fchk",
                "surface_type": "molecular",
                "bins": 100,
            },
        )
        artifacts = app.execute(run, {})
        self.assertIsInstance(artifacts, list)
        self.assertGreater(len(artifacts), 0)
        self.assertEqual(artifacts[0].type, ArtifactType.RESULT_TABLE)
        self.assertIn("results", artifacts[0].data)
        self.assertIn("warnings", artifacts[0].data)

    def test_execute_with_cube_creates_extra_artifacts(self):
        """验证包含 Cube 结果时应额外创建 OTHER 类型 Artifact。"""
        app = WavefunctionAnalysisApplication(kernel=MagicMock(), adapter=_PlaceholderAdapter())
        run = Run(
            task_id="task-001",
            project_id="proj-001",
            service_id="wavefunction_analysis",
            command="analyze_esp",
            input={
                "input_file": "/path/to/structure.fchk",
                "file_format": "fchk",
                "surface_type": "molecular",
                "bins": 100,
                "generate_cubes": True,
            },
        )
        artifacts = app.execute(run, {})
        artifact_types = [a.type for a in artifacts]
        self.assertIn(ArtifactType.OTHER, artifact_types)
        self.assertIn(ArtifactType.RESULT_TABLE, artifact_types)


# ====================================================================
# TestWavefunctionApplicationPostprocess
# ====================================================================


class TestWavefunctionApplicationPostprocess(unittest.TestCase):
    """WavefunctionAnalysisApplication.postprocess 方法测试。"""

    def setUp(self):
        self.app = WavefunctionAnalysisApplication(kernel=MagicMock())

    def test_postprocess_returns_evidence_packages(self):
        """验证 postprocess 应返回 EvidencePackage 列表。"""
        run = Run(
            run_id="run-001",
            task_id="task-001",
            project_id="proj-001",
            service_id="wavefunction_analysis",
            command="analyze_esp",
        )
        artifacts = [
            Artifact(
                run_id="run-001",
                type=ArtifactType.RESULT_TABLE,
                name="analyze_esp_results",
                data={
                    "results": [
                        {
                            "type": "esp_surface",
                            "claim": "ESP 表面统计",
                            "value": {"min": -25.4, "max": 18.7},
                            "unit": "kcal/mol",
                            "confidence": 0.85,
                        },
                        {
                            "type": "orbital_gap",
                            "claim": "HOMO-LUMO 能隙",
                            "value": 4.5,
                            "unit": "eV",
                            "confidence": 0.95,
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
            service_id="wavefunction_analysis",
            command="analyze_esp",
        )
        evidence = self.app.postprocess(run, [])
        self.assertEqual(len(evidence), 0)

    def test_postprocess_no_results_in_artifact(self):
        """验证 Artifact 无 results 数据时应返回空列表。"""
        run = Run(
            run_id="run-001",
            task_id="task-001",
            project_id="proj-001",
            service_id="wavefunction_analysis",
            command="analyze_esp",
        )
        artifacts = [
            Artifact(
                run_id="run-001",
                type=ArtifactType.RESULT_TABLE,
                name="analyze_esp_results",
                data={"warnings": []},
            )
        ]
        evidence = self.app.postprocess(run, artifacts)
        self.assertEqual(len(evidence), 0)


# ====================================================================
# TestWavefunctionApplicationRunFullCycle
# ====================================================================


class TestWavefunctionApplicationRunFullCycle(unittest.TestCase):
    """WavefunctionAnalysisApplication.run_full_cycle 完整生命周期测试。"""

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

        app = WavefunctionAnalysisApplication(kernel=mock_kernel, adapter=_PlaceholderAdapter())
        task = Task(
            project_id="proj-001",
            capability_id="wavefunction_analysis",
            title="test",
            metadata={
                "command": "analyze_esp",
                "input_file": "/path/to/structure.fchk",
                "file_format": "fchk",
                "surface_type": "molecular",
                "bins": 100,
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
        app = WavefunctionAnalysisApplication(kernel=mock_kernel)
        task = Task(
            project_id="proj-001",
            capability_id="wavefunction_analysis",
            title="test",
            metadata={
                "command": "analyze_esp",
                "input_file": "",
                "file_format": "fchk",
            },
        )
        with self.assertRaises(ValueError):
            app.run_full_cycle(task)


# ====================================================================
# TestPlaceholderAdapter
# ====================================================================


class TestPlaceholderAdapter(unittest.TestCase):
    """_PlaceholderAdapter 占位适配器测试。"""

    def setUp(self):
        self.adapter = _PlaceholderAdapter()

    def test_execute_esp_returns_expected_structure(self):
        """验证 execute_esp 应返回正确的结构。"""
        result = self.adapter.execute_esp({
            "file_format": "fchk",
            "surface_type": "molecular",
            "bins": 100,
            "generate_cubes": True,
        })
        self.assertIn("status", result)
        self.assertEqual(result["status"], "completed")
        self.assertIn("results", result)
        self.assertIn("warnings", result)
        self.assertGreater(len(result["results"]), 0)

    def test_execute_esp_includes_cube_when_requested(self):
        """验证 generate_cubes=True 时应包含 Cube 结果。"""
        result = self.adapter.execute_esp({
            "file_format": "fchk",
            "surface_type": "molecular",
            "bins": 100,
            "generate_cubes": True,
        })
        types = [r["type"] for r in result["results"]]
        self.assertIn("esp_cube", types)

    def test_execute_esp_no_cube_when_not_requested(self):
        """验证 generate_cubes=False 时应不包含 Cube 结果。"""
        result = self.adapter.execute_esp({
            "file_format": "fchk",
            "surface_type": "molecular",
            "bins": 100,
            "generate_cubes": False,
        })
        types = [r["type"] for r in result["results"]]
        self.assertNotIn("esp_cube", types)

    def test_execute_orbitals_returns_expected_structure(self):
        """验证 execute_orbitals 应返回正确的结构。"""
        result = self.adapter.execute_orbitals({
            "file_format": "fchk",
            "below_homo": 3,
            "above_lumo": 3,
            "grid_quality": "high",
        })
        self.assertIn("status", result)
        self.assertEqual(result["status"], "completed")
        self.assertIn("results", result)
        self.assertGreater(len(result["results"]), 0)

    def test_execute_orbitals_includes_gap(self):
        """验证轨道分析结果应包含 HOMO-LUMO 能隙。"""
        result = self.adapter.execute_orbitals({
            "file_format": "fchk",
            "below_homo": 3,
            "above_lumo": 3,
        })
        types = [r["type"] for r in result["results"]]
        self.assertIn("orbital_gap", types)

    def test_execute_orbitals_includes_cubes(self):
        """验证轨道分析结果应包含轨道 Cube 文件。"""
        result = self.adapter.execute_orbitals({
            "file_format": "fchk",
            "below_homo": 2,
            "above_lumo": 2,
        })
        types = [r["type"] for r in result["results"]]
        self.assertIn("orbital_cube", types)

    def test_execute_render_returns_expected_structure(self):
        """验证 execute_render 应返回正确的结构。"""
        result = self.adapter.execute_render({
            "input_dir": "/path/to/cubes",
            "render_type": "orbital",
            "image_format": "png",
            "width": 1800,
            "height": 1200,
        })
        self.assertIn("status", result)
        self.assertEqual(result["status"], "completed")
        self.assertIn("results", result)
        self.assertGreater(len(result["results"]), 0)

    def test_execute_render_includes_script_and_image(self):
        """验证渲染结果应包含脚本和图片。"""
        result = self.adapter.execute_render({
            "input_dir": "/path/to/cubes",
            "render_type": "esp",
            "image_format": "png",
        })
        types = [r["type"] for r in result["results"]]
        self.assertIn("render_script", types)
        self.assertIn("render_image", types)

    def test_parse_output_dict(self):
        """验证 parse_output 能正确处理 dict 输入。"""
        result = self.adapter.parse_output({"status": "completed", "results": []})
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["results"], [])

    def test_parse_output_non_dict(self):
        """验证 parse_output 能处理非 dict 输入。"""
        result = self.adapter.parse_output("not a dict")
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["results"], [])

    def test_get_resource_requirements(self):
        """验证资源需求应返回默认值。"""
        reqs = self.adapter.get_resource_requirements({})
        self.assertIn("cpu", reqs)
        self.assertIn("memory_mb", reqs)
        self.assertIn("walltime_minutes", reqs)
        self.assertEqual(reqs["cpu"], 2)
        self.assertEqual(reqs["memory_mb"], 1024)

    def test_validate_input(self):
        """验证 validate_input 应返回空列表。"""
        errors = self.adapter.validate_input({"file_format": "fchk"})
        self.assertEqual(errors, [])


# ====================================================================
# TestEvidenceMapper
# ====================================================================


class TestEvidenceMapper(unittest.TestCase):
    """evidence_mapper 函数测试。"""

    def test_map_wavefunction_evidence_high_confidence(self):
        """验证高置信度应映射为 HIGH 级别。"""
        package = map_wavefunction_evidence(
            run_id="run-001",
            task_id="task-001",
            evidence_type="esp_surface",
            claim="ESP 表面统计",
            value={"min": -25.4},
            unit="kcal/mol",
            confidence=0.95,
        )
        self.assertEqual(package.level, EvidenceLevel.HIGH)
        self.assertEqual(package.source_service, "real_engine:wavefunction_analysis")
        self.assertEqual(package.method, "multiwfn_esp_surface_analysis")

    def test_map_wavefunction_evidence_medium_confidence(self):
        """验证中等置信度应映射为 MEDIUM 级别。"""
        package = map_wavefunction_evidence(
            run_id="run-001",
            task_id="task-001",
            evidence_type="esp_area",
            claim="ESP 区间面积分布",
            value={},
            confidence=0.80,
        )
        self.assertEqual(package.level, EvidenceLevel.MEDIUM)

    def test_map_wavefunction_evidence_low_confidence(self):
        """验证低置信度应映射为 LOW 级别。"""
        package = map_wavefunction_evidence(
            run_id="run-001",
            task_id="task-001",
            evidence_type="orbital_energy",
            claim="轨道能级",
            value={},
            confidence=0.50,
        )
        self.assertEqual(package.level, EvidenceLevel.LOW)

    def test_map_wavefunction_evidence_boundary_high(self):
        """验证边界置信度 0.9 应映射为 HIGH 级别。"""
        package = map_wavefunction_evidence(
            run_id="run-001",
            task_id="task-001",
            evidence_type="orbital_gap",
            claim="HOMO-LUMO 能隙",
            value=4.5,
            unit="eV",
            confidence=0.9,
        )
        self.assertEqual(package.level, EvidenceLevel.HIGH)

    def test_map_wavefunction_evidence_boundary_medium(self):
        """验证边界置信度 0.7 应映射为 MEDIUM 级别。"""
        package = map_wavefunction_evidence(
            run_id="run-001",
            task_id="task-001",
            evidence_type="render_image",
            claim="渲染图片",
            value="image.png",
            confidence=0.7,
        )
        self.assertEqual(package.level, EvidenceLevel.MEDIUM)

    def test_map_wavefunction_evidence_render_script_method(self):
        """验证渲染脚本类型应映射正确的方法名。"""
        package = map_wavefunction_evidence(
            run_id="run-001",
            task_id="task-001",
            evidence_type="render_script",
            claim="VMD 脚本",
            value={},
        )
        self.assertEqual(package.method, "vmd_render_script")

    def test_map_wavefunction_evidence_with_metadata(self):
        """验证附加元数据应被包含在证据包中。"""
        package = map_wavefunction_evidence(
            run_id="run-001",
            task_id="task-001",
            evidence_type="esp_surface",
            claim="ESP 表面统计",
            value={},
            metadata={"source": "test", "method": "placeholder"},
        )
        self.assertIn("source", package.metadata)
        self.assertEqual(package.metadata["source"], "test")
        self.assertIn("evidence_type", package.metadata)

    def test_batch_map_wavefunction_evidence(self):
        """验证批量映射应返回正确数量的证据包。"""
        results = [
            {
                "type": "esp_surface",
                "claim": "ESP 表面统计",
                "value": {"min": -25.4},
                "unit": "kcal/mol",
                "confidence": 0.9,
                "metadata": {"method": "placeholder"},
            },
            {
                "type": "orbital_gap",
                "claim": "HOMO-LUMO 能隙",
                "value": 4.5,
                "unit": "eV",
                "confidence": 0.95,
            },
            {
                "type": "render_image",
                "claim": "渲染图片",
                "value": "image.png",
                "confidence": 0.80,
            },
        ]
        packages = batch_map_wavefunction_evidence(
            run_id="run-001",
            task_id="task-001",
            results=results,
        )
        self.assertEqual(len(packages), 3)
        self.assertIsInstance(packages[0], EvidencePackage)

    def test_batch_map_wavefunction_evidence_empty(self):
        """验证空结果列表应返回空列表。"""
        packages = batch_map_wavefunction_evidence(
            run_id="run-001",
            task_id="task-001",
            results=[],
        )
        self.assertEqual(len(packages), 0)


# ====================================================================
# TestConstants
# ====================================================================


class TestConstants(unittest.TestCase):
    """常量定义完整性测试。"""

    def test_supported_file_formats_count(self):
        """验证支持的文件格式数量。"""
        self.assertEqual(len(SUPPORTED_FILE_FORMATS), 4)

    def test_supported_file_formats_keys(self):
        """验证支持的文件格式键名。"""
        expected = {"molden", "fchk", "wfn", "wfx"}
        self.assertEqual(set(SUPPORTED_FILE_FORMATS.keys()), expected)

    def test_supported_surface_types_count(self):
        """验证支持的表面类型数量。"""
        self.assertEqual(len(SUPPORTED_SURFACE_TYPES), 3)

    def test_supported_grid_qualities_count(self):
        """验证支持的网格质量数量。"""
        self.assertEqual(len(SUPPORTED_GRID_QUALITIES), 4)

    def test_supported_render_engines_count(self):
        """验证支持的渲染引擎数量。"""
        self.assertEqual(len(SUPPORTED_RENDER_ENGINES), 2)

    def test_supported_image_formats_count(self):
        """验证支持的图片格式数量。"""
        self.assertEqual(len(SUPPORTED_IMAGE_FORMATS), 5)

    def test_supported_image_formats_keys(self):
        """验证支持的图片格式键名。"""
        expected = {"png", "tiff", "bmp", "jpg", "tga"}
        self.assertEqual(set(SUPPORTED_IMAGE_FORMATS.keys()), expected)

    def test_fchk_multiwfn_key(self):
        """验证 fchk 格式的 multiwfn_key 应为 2。"""
        self.assertEqual(SUPPORTED_FILE_FORMATS["fchk"]["multiwfn_key"], 2)

    def test_molden_extensions(self):
        """验证 molden 格式的扩展名集合。"""
        exts = SUPPORTED_FILE_FORMATS["molden"]["extensions"]
        self.assertIn(".molden", exts)
        self.assertIn(".molden.input", exts)


# ====================================================================
# TestExternalEntryPoints
# ====================================================================


class _FakeKernel:
    """模拟内核，保持 Run 对象引用完整。"""

    @staticmethod
    def create_task(task):
        return task

    def submit_run(self, run):
        self._last_run = run
        return run

    def update_run_status(self, run_id, status):
        return self._last_run

    @staticmethod
    def store_artifact(artifact):
        pass

    @staticmethod
    def store_evidence(evidence):
        pass


class TestExternalEntryPoints(unittest.TestCase):
    """外部调用入口测试。"""

    def setUp(self):
        self.app = WavefunctionAnalysisApplication(kernel=_FakeKernel(), adapter=_PlaceholderAdapter())

    def test_analyze_esp_returns_evidence(self):
        """验证 analyze_esp 外部入口应返回证据包。"""
        evidence = self.app.analyze_esp(
            project_id="proj-001",
            input_file="/path/to/structure.fchk",
            file_format="fchk",
        )
        self.assertIsInstance(evidence, list)
        for ev in evidence:
            self.assertIsInstance(ev, EvidencePackage)

    def test_analyze_orbitals_returns_evidence(self):
        """验证 analyze_orbitals 外部入口应返回证据包。"""
        evidence = self.app.analyze_orbitals(
            project_id="proj-001",
            input_file="/path/to/structure.fchk",
            file_format="fchk",
        )
        self.assertIsInstance(evidence, list)
        for ev in evidence:
            self.assertIsInstance(ev, EvidencePackage)

    def test_render_orbital_returns_evidence(self):
        """验证 render_orbital 外部入口应返回证据包。"""
        evidence = self.app.render_orbital(
            project_id="proj-001",
            input_dir="/path/to/cubes",
            render_type="orbital",
        )
        self.assertIsInstance(evidence, list)
        for ev in evidence:
            self.assertIsInstance(ev, EvidencePackage)

    def test_batch_analysis_esp_returns_list_of_evidence(self):
        """验证 batch_analysis ESP 模式应返回证据包列表的列表。"""
        all_evidence = self.app.batch_analysis(
            project_id="proj-001",
            files=["/path/to/file1.fchk", "/path/to/file2.fchk"],
            mode="esp",
        )
        self.assertIsInstance(all_evidence, list)
        self.assertEqual(len(all_evidence), 2)
        for evidence_list in all_evidence:
            self.assertIsInstance(evidence_list, list)
            for ev in evidence_list:
                self.assertIsInstance(ev, EvidencePackage)

    def test_batch_analysis_orbital_returns_list_of_evidence(self):
        """验证 batch_analysis orbital 模式应返回证据包列表的列表。"""
        all_evidence = self.app.batch_analysis(
            project_id="proj-001",
            files=["/path/to/file1.fchk"],
            mode="orbital",
        )
        self.assertIsInstance(all_evidence, list)
        self.assertEqual(len(all_evidence), 1)


if __name__ == "__main__":
    unittest.main()