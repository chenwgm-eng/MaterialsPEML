"""输入校验 — 材料结构格式与数据合法性检查。"""

from __future__ import annotations

import re

# 支持的分子/晶体结构格式
SUPPORTED_FORMATS: frozenset[str] = frozenset({
    "smiles",
    "xyz",
    "cif",
    "mol",
    "mol2",
    "pdb",
    "sdf",
})


def validate_input_format(fmt: str) -> str:
    """校验结构格式名称，标准化为小写后返回。

    Raises:
        ValueError: 格式不受支持时抛出。

    Examples:
        >>> validate_input_format("SMILES")
        'smiles'
        >>> validate_input_format("cif")
        'cif'
    """
    normalized = fmt.strip().lower()
    if normalized not in SUPPORTED_FORMATS:
        raise ValueError(
            f"不支持的格式 '{fmt}'。支持: {', '.join(sorted(SUPPORTED_FORMATS))}"
        )
    return normalized


def validate_structure_data(data: str, fmt: str) -> None:
    """对结构数据进行基本的合法性检查。

    Args:
        data: 原始结构数据字符串。
        fmt: 格式名称（已标准化）。

    Raises:
        ValueError: 数据为空或不符合基本格式要求时抛出。
    """
    if not data or not data.strip():
        raise ValueError("结构数据不能为空")

    fmt = fmt.lower()
    if fmt == "smiles":
        # SMILES 基本检查：非空且不含非法字符
        if not re.match(r"^[A-Za-z0-9@+\-\[\](){}#%=\\./\\:^~]+$", data.strip()):
            raise ValueError("SMILES 字符串包含非法字符")
    elif fmt in ("xyz", "cif", "mol", "mol2", "pdb", "sdf"):
        # 文件格式至少应包含换行符
        if "\n" not in data and len(data) < 20:
            raise ValueError(f"{fmt.upper()} 格式数据过短，可能不完整")
    # 其他格式不做深层校验


class StructureValidator:
    """结构输入校验器 — 组合格式和内容校验。"""

    @staticmethod
    def validate(fmt: str, data: str) -> dict[str, list[str]]:
        """执行完整校验，返回校验结果字典。

        Returns:
            dict: 包含 ``errors`` 和 ``warnings`` 两个列表。
        """
        errors: list[str] = []
        warnings: list[str] = []

        try:
            validate_input_format(fmt)
        except ValueError as exc:
            errors.append(str(exc))
            return {"errors": errors, "warnings": warnings}

        try:
            validate_structure_data(data, fmt)
        except ValueError as exc:
            errors.append(str(exc))

        if fmt == "smiles" and len(data.strip()) > 200:
            warnings.append("SMILES 字符串长度超过 200，可能为复杂分子")

        return {"errors": errors, "warnings": warnings}

    @staticmethod
    def is_valid(fmt: str, data: str) -> bool:
        """快速判断输入是否合法。"""
        result = StructureValidator.validate(fmt, data)
        return len(result["errors"]) == 0