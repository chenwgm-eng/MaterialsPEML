"""波函数分析输入验证 — 文件格式、ESP/轨道/渲染参数校验。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

# ── 支持的波函数文件格式 ─────────────────────────────────────

SUPPORTED_FILE_FORMATS: dict[str, dict[str, Any]] = {
    "molden": {
        "description": "Molden 格式 (.molden/.molden.input)",
        "extensions": {".molden", ".molden.input", ".mold"},
        "multiwfn_key": 1,
    },
    "fchk": {
        "description": "Gaussian Formatted Checkpoint (.fchk/.fch)",
        "extensions": {".fchk", ".fch"},
        "multiwfn_key": 2,
    },
    "wfn": {
        "description": "Gaussian 波函数文件 (.wfn)",
        "extensions": {".wfn"},
        "multiwfn_key": 3,
    },
    "wfx": {
        "description": "Gaussian 波函数文件 XML 格式 (.wfx)",
        "extensions": {".wfx"},
        "multiwfn_key": 4,
    },
}

# ── ESP 分析参数 ─────────────────────────────────────────────

SUPPORTED_SURFACE_TYPES: dict[str, str] = {
    "molecular": "分子表面 ESP (Multiwfn 选项 3)",
    "vdw": "范德华表面 ESP",
    "electron_density": "等电子密度面 ESP",
}

SUPPORTED_GRID_QUALITIES: dict[str, int] = {
    "low": 1,
    "medium": 2,
    "high": 3,
    "very_high": 4,
}

# ── 渲染参数 ─────────────────────────────────────────────────

SUPPORTED_RENDER_ENGINES: dict[str, str] = {
    "vmd": "VMD (Visual Molecular Dynamics) — 本地渲染",
    "multiwfn": "Multiwfn 内置渲染 — 基础场景",
}

SUPPORTED_IMAGE_FORMATS: dict[str, str] = {
    "png": "PNG 格式",
    "tiff": "TIFF 格式",
    "bmp": "BMP 格式",
    "jpg": "JPEG 格式",
    "tga": "TGA 格式",
}

# ── 参数范围 ─────────────────────────────────────────────────

BINS_RANGE: tuple[int, int] = (10, 1000)
HOMO_LUMO_RANGE: tuple[int, int] = (0, 10)
RESOLUTION_RANGE: tuple[tuple[int, int], tuple[int, int]] = ((400, 300), (3840, 2160))
WORKERS_RANGE: tuple[int, int] = (1, 128)


# ── 校验函数 ────────────────────────────────────────────────


def validate_file_format(file_format: str) -> dict[str, Any]:
    """校验波函数文件格式是否受支持。

    Returns:
        dict: 包含 valid、errors、format_info。
    """
    key = file_format.strip().lower()
    if key not in SUPPORTED_FILE_FORMATS:
        return {
            "valid": False,
            "errors": [
                f"不支持的 file_format '{file_format}'。"
                f"支持: {', '.join(sorted(SUPPORTED_FILE_FORMATS))}"
            ],
        }
    return {"valid": True, "errors": [], "format_info": SUPPORTED_FILE_FORMATS[key]}


def validate_input_file(input_file: str) -> dict[str, Any]:
    """校验输入文件路径是否存在且非空。

    Returns:
        dict: 包含 valid、errors、warnings。
    """
    errors: list[str] = []
    warnings: list[str] = []

    if not input_file or not input_file.strip():
        errors.append("input_file 不能为空")
        return {"valid": False, "errors": errors, "warnings": warnings}

    import os
    if not os.path.isfile(input_file):
        warnings.append(f"文件不存在: {input_file}，将使用占位数据")
    else:
        file_size = os.path.getsize(input_file)
        if file_size == 0:
            errors.append(f"文件为空: {input_file}")
        elif file_size < 100:
            warnings.append(f"文件过小 ({file_size} 字节)，可能不是有效的波函数文件")

    return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings}


def validate_surface_type(surface_type: str) -> dict[str, Any]:
    """校验 ESP 表面类型。

    Returns:
        dict: 包含 valid、errors、surface_info。
    """
    key = surface_type.strip().lower()
    if key not in SUPPORTED_SURFACE_TYPES:
        return {
            "valid": False,
            "errors": [
                f"不支持的 surface_type '{surface_type}'。"
                f"支持: {', '.join(sorted(SUPPORTED_SURFACE_TYPES))}"
            ],
        }
    return {"valid": True, "errors": [], "surface_info": SUPPORTED_SURFACE_TYPES[key]}


def validate_bins(bins: int) -> dict[str, Any]:
    """校验 bins 参数是否在合理范围内。

    Returns:
        dict: 包含 valid、errors、warnings。
    """
    warnings: list[str] = []
    if bins < BINS_RANGE[0] or bins > BINS_RANGE[1]:
        warnings.append(
            f"bins={bins} 超出推荐范围 ({BINS_RANGE[0]}-{BINS_RANGE[1]})"
        )
    if bins <= 0:
        return {"valid": False, "errors": ["bins 必须为正整数"], "warnings": warnings}
    return {"valid": True, "errors": [], "warnings": warnings}


def validate_cube_generation(generate_cubes: bool) -> dict[str, Any]:
    """校验 cube 生成参数（无实际校验，仅返回有效结果）。"""
    return {"valid": True, "errors": []}


def validate_orbital_range(below_homo: int, above_lumo: int) -> dict[str, Any]:
    """校验 HOMO/LUMO 轨道范围参数。

    Returns:
        dict: 包含 valid、errors、warnings。
    """
    errors: list[str] = []
    warnings: list[str] = []

    if below_homo < 0 or above_lumo < 0:
        errors.append("below_homo 和 above_lumo 必须为非负整数")
    if below_homo == 0 and above_lumo == 0:
        warnings.append("below_homo=0 且 above_lumo=0 将不产生任何轨道 Cube")
    if below_homo > HOMO_LUMO_RANGE[1] or above_lumo > HOMO_LUMO_RANGE[1]:
        warnings.append(
            f"轨道范围 ({below_homo}+{above_lumo}) 超出常用范围 "
            f"(0-{HOMO_LUMO_RANGE[1]})，可能耗时较长"
        )

    return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings}


def validate_grid_quality(grid_quality: str) -> dict[str, Any]:
    """校验网格质量参数。

    Returns:
        dict: 包含 valid、errors、quality_key。
    """
    key = grid_quality.strip().lower()
    if key not in SUPPORTED_GRID_QUALITIES:
        return {
            "valid": False,
            "errors": [
                f"不支持的 grid_quality '{grid_quality}'。"
                f"支持: {', '.join(sorted(SUPPORTED_GRID_QUALITIES))}"
            ],
        }
    return {"valid": True, "errors": [], "quality_key": SUPPORTED_GRID_QUALITIES[key]}


def validate_render_engine(engine: str) -> dict[str, Any]:
    """校验渲染引擎。

    Returns:
        dict: 包含 valid、errors、engine_info。
    """
    key = engine.strip().lower()
    if key not in SUPPORTED_RENDER_ENGINES:
        return {
            "valid": False,
            "errors": [
                f"不支持的 render_engine '{engine}'。"
                f"支持: {', '.join(sorted(SUPPORTED_RENDER_ENGINES))}"
            ],
        }
    return {"valid": True, "errors": [], "engine_info": SUPPORTED_RENDER_ENGINES[key]}


def validate_image_format(image_format: str) -> dict[str, Any]:
    """校验图片格式。

    Returns:
        dict: 包含 valid、errors、format_info。
    """
    key = image_format.strip().lower()
    if key not in SUPPORTED_IMAGE_FORMATS:
        return {
            "valid": False,
            "errors": [
                f"不支持的 image_format '{image_format}'。"
                f"支持: {', '.join(sorted(SUPPORTED_IMAGE_FORMATS))}"
            ],
        }
    return {"valid": True, "errors": [], "format_info": SUPPORTED_IMAGE_FORMATS[key]}


def validate_resolution(width: int, height: int) -> dict[str, Any]:
    """校验渲染分辨率。

    Returns:
        dict: 包含 valid、errors、warnings。
    """
    errors: list[str] = []
    warnings: list[str] = []

    (min_w, min_h), (max_w, max_h) = RESOLUTION_RANGE

    if width < min_w or height < min_h:
        errors.append(f"分辨率 ({width}x{height}) 过低，最小为 {min_w}x{min_h}")
    elif width > max_w or height > max_h:
        warnings.append(f"分辨率 ({width}x{height}) 过高，建议不超过 {max_w}x{max_h}")

    if width <= 0 or height <= 0:
        errors.append("分辨率宽高必须为正整数")

    return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings}


def validate_batch_params(workers: int, fail_fast: bool) -> dict[str, Any]:
    """校验批量分析参数。

    Returns:
        dict: 包含 valid、errors、warnings。
    """
    warnings: list[str] = []
    if workers < WORKERS_RANGE[0] or workers > WORKERS_RANGE[1]:
        warnings.append(
            f"workers={workers} 超出推荐范围 ({WORKERS_RANGE[0]}-{WORKERS_RANGE[1]})"
        )
    if workers <= 0:
        return {"valid": False, "errors": ["workers 必须为正整数"], "warnings": warnings}
    if fail_fast and workers > 1:
        warnings.append("fail_fast=True 与 workers>1 结合使用时，一个文件失败将取消所有待处理任务")
    return {"valid": True, "errors": [], "warnings": warnings}


# ── 验证器类 ────────────────────────────────────────────────


class WavefunctionValidator(BaseModel):
    """波函数分析输入验证器 — 封装完整的输入校验逻辑。"""

    # 通用参数
    input_file: str = Field(..., description="波函数文件路径")
    file_format: str = Field(..., description="文件格式: molden, fchk, wfn, wfx")

    # ESP 分析参数（可选）
    surface_type: str = Field(default="molecular", description="ESP 表面类型")
    bins: int = Field(default=100, description="ESP 区间数")
    generate_cubes: bool = Field(default=True, description="是否生成 Cube 文件")

    # 轨道分析参数（可选）
    below_homo: int = Field(default=3, description="HOMO 以下轨道数")
    above_lumo: int = Field(default=3, description="LUMO 以上轨道数")
    grid_quality: str = Field(default="high", description="网格质量: low, medium, high, very_high")

    # 渲染参数（可选）
    render_engine: str = Field(default="vmd", description="渲染引擎: vmd, multiwfn")
    image_format: str = Field(default="png", description="图片格式: png, tiff, bmp, jpg, tga")
    width: int = Field(default=1800, description="渲染宽度 (px)")
    height: int = Field(default=1200, description="渲染高度 (px)")

    # 批量分析参数（可选）
    workers: int = Field(default=1, description="批量分析并行数")
    fail_fast: bool = Field(default=False, description="失败时是否立即停止")

    def validate_all(self) -> dict[str, Any]:
        """执行完整校验，返回校验结果。"""
        result: dict[str, Any] = {"valid": True, "errors": [], "warnings": []}

        # 1. 校验文件格式
        fmt_result = validate_file_format(self.file_format)
        if not fmt_result["valid"]:
            result["errors"].extend(fmt_result["errors"])
            result["valid"] = False
            return result
        result["format_info"] = fmt_result["format_info"]

        # 2. 校验输入文件
        file_result = validate_input_file(self.input_file)
        result["errors"].extend(file_result["errors"])
        result["warnings"].extend(file_result["warnings"])

        # 3. 校验 ESP 表面类型
        surf_result = validate_surface_type(self.surface_type)
        if not surf_result["valid"]:
            result["errors"].extend(surf_result["errors"])
            result["valid"] = False
        else:
            result["surface_info"] = surf_result["surface_info"]

        # 4. 校验 bins
        bins_result = validate_bins(self.bins)
        result["errors"].extend(bins_result["errors"])
        result["warnings"].extend(bins_result["warnings"])

        # 5. 校验轨道范围
        orb_result = validate_orbital_range(self.below_homo, self.above_lumo)
        result["errors"].extend(orb_result["errors"])
        result["warnings"].extend(orb_result["warnings"])

        # 6. 校验网格质量
        grid_result = validate_grid_quality(self.grid_quality)
        if not grid_result["valid"]:
            result["errors"].extend(grid_result["errors"])
            result["valid"] = False
        else:
            result["grid_quality_key"] = grid_result["quality_key"]

        # 7. 校验渲染引擎
        engine_result = validate_render_engine(self.render_engine)
        if not engine_result["valid"]:
            result["errors"].extend(engine_result["errors"])
            result["valid"] = False
        else:
            result["engine_info"] = engine_result["engine_info"]

        # 8. 校验图片格式
        img_result = validate_image_format(self.image_format)
        if not img_result["valid"]:
            result["errors"].extend(img_result["errors"])
            result["valid"] = False
        else:
            result["image_format_info"] = img_result["format_info"]

        # 9. 校验分辨率
        res_result = validate_resolution(self.width, self.height)
        result["errors"].extend(res_result["errors"])
        result["warnings"].extend(res_result["warnings"])

        # 10. 校验批量参数
        batch_result = validate_batch_params(self.workers, self.fail_fast)
        result["errors"].extend(batch_result["errors"])
        result["warnings"].extend(batch_result["warnings"])

        if result["errors"]:
            result["valid"] = False

        return result