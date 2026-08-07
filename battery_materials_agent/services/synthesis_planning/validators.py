"""合成路线规划输入验证 — SMILES 合法性检查与参数范围校验。"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field

# 简易 SMILES 正则（非 RDKit 时的兜底检查）
_SMILES_PATTERN = re.compile(r"^[A-Za-z0-9@+\-\[\](){}#%=.$\\/|~:&*!,_]+$")

# 参数范围约束
_SEARCH_DEPTH_RANGE = (1, 10)
_MAX_PATHS_RANGE = (1, 100)
_EXPANSION_TIMEOUT_RANGE = (30, 1800)


def validate_target_smiles(smiles: str) -> tuple[bool, str | None]:
    """验证目标 SMILES 字符串。

    Args:
        smiles: 目标分子 SMILES。

    Returns:
        (is_valid, error_message) 元组。
    """
    if not smiles or not smiles.strip():
        return False, "目标 SMILES 不能为空"

    smi = smiles.strip()

    try:
        from rdkit import Chem  # type: ignore[import-untyped]

        mol = Chem.MolFromSmiles(smi)
        if mol is None:
            return False, f"无效的 SMILES: {smi}"
        return True, None
    except ImportError:
        # RDKit 不可用，使用正则兜底
        if _SMILES_PATTERN.match(smi):
            return True, None
        return False, f"SMILES 格式不合法: {smi}"


def validate_search_depth(depth: int) -> tuple[bool, str | None]:
    """验证搜索深度。

    Args:
        depth: 搜索深度。

    Returns:
        (is_valid, error_message) 元组。
    """
    min_d, max_d = _SEARCH_DEPTH_RANGE
    if not isinstance(depth, int) or depth < min_d or depth > max_d:
        return False, f"搜索深度必须在 {min_d}-{max_d} 之间，收到: {depth}"
    return True, None


def validate_max_paths(max_paths: int) -> tuple[bool, str | None]:
    """验证最大返回路线数。

    Args:
        max_paths: 最大路线数。

    Returns:
        (is_valid, error_message) 元组。
    """
    min_p, max_p = _MAX_PATHS_RANGE
    if not isinstance(max_paths, int) or max_paths < min_p or max_paths > max_p:
        return False, f"最大路线数必须在 {min_p}-{max_p} 之间，收到: {max_paths}"
    return True, None


def validate_expansion_timeout(timeout: int) -> tuple[bool, str | None]:
    """验证搜索超时时间。

    Args:
        timeout: 超时时间（秒）。

    Returns:
        (is_valid, error_message) 元组。
    """
    min_t, max_t = _EXPANSION_TIMEOUT_RANGE
    if not isinstance(timeout, int) or timeout < min_t or timeout > max_t:
        return False, f"扩展超时必须在 {min_t}-{max_t} 秒之间，收到: {timeout}"
    return True, None


class SynthesisInputValidator(BaseModel):
    """合成路线规划输入验证器 — 封装完整输入校验逻辑。"""

    target_smiles: str = Field(..., description="目标分子 SMILES")
    search_depth: int = Field(default=3, description="搜索深度")
    max_paths: int = Field(default=10, description="最大返回路线数")
    expansion_timeout: int = Field(default=300, description="搜索超时（秒）")
    normalize_ions: bool = Field(default=True, description="是否归一化离子/盐")
    include_literature: bool = Field(default=True, description="是否包含文献验证")

    def validate_all(self) -> dict[str, Any]:
        """执行完整校验，返回校验结果。"""
        result: dict[str, Any] = {"valid": True, "errors": [], "warnings": []}

        # 1. 验证 SMILES
        valid_smi, smi_err = validate_target_smiles(self.target_smiles)
        if not valid_smi:
            result["valid"] = False
            result["errors"].append(smi_err or "SMILES 验证失败")
        else:
            result["normalized_smiles"] = self.target_smiles.strip()

        # 2. 验证搜索深度
        valid_depth, depth_err = validate_search_depth(self.search_depth)
        if not valid_depth:
            result["errors"].append(depth_err or "搜索深度无效")

        # 3. 验证最大路线数
        valid_paths, paths_err = validate_max_paths(self.max_paths)
        if not valid_paths:
            result["errors"].append(paths_err or "最大路线数无效")

        # 4. 验证超时时间
        valid_timeout, timeout_err = validate_expansion_timeout(self.expansion_timeout)
        if not valid_timeout:
            result["errors"].append(timeout_err or "扩展超时无效")

        # 5. 搜索深度与超时关联检查
        if self.search_depth > 6 and self.expansion_timeout < 300:
            result["warnings"].append(
                f"搜索深度 {self.search_depth} 较大，建议 expansion_timeout >= 300 秒"
            )

        if result["errors"]:
            result["valid"] = False

        return result