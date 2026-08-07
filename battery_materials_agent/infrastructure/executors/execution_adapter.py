"""ExecutionAdapter 接口 — 封装第三方库/二进制调用。"""
from __future__ import annotations

import os
import tempfile
from abc import ABC, abstractmethod
from typing import Any


# 引擎临时工作目录根 — 默认项目目录下 .cache/engine-tmp/，避免占用系统盘 (C:)
# 可通过环境变量 BATTERYEMCL_ENGINE_TMP 覆盖
_PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)
_ENGINE_TMP_ROOT = os.environ.get(
    "BATTERYEMCL_ENGINE_TMP",
    os.path.join(_PROJECT_ROOT, ".cache", "engine-tmp"),
)


def create_engine_work_dir(prefix: str) -> str:
    """在项目目录下创建引擎临时工作目录。

    所有适配器应使用此函数替代 ``tempfile.mkdtemp``，确保临时文件落到
    项目所在盘（D:），而非系统 temp 目录（C:）。

    Args:
        prefix: 目录前缀（不含尾随下划线）。

    Returns:
        临时工作目录绝对路径。
    """
    os.makedirs(_ENGINE_TMP_ROOT, exist_ok=True)
    return tempfile.mkdtemp(prefix=prefix + "_", dir=_ENGINE_TMP_ROOT)


def engine_tmp_path(filename: str) -> str:
    """返回项目目录下引擎临时文件的完整路径。

    用于替代 ``tempfile.mktemp``（已废弃且落在系统 temp）。

    Args:
        filename: 文件名（如 "structure.pdb"）。

    Returns:
        临时文件绝对路径（目录已确保存在，文件本身不创建）。
    """
    os.makedirs(_ENGINE_TMP_ROOT, exist_ok=True)
    return os.path.join(_ENGINE_TMP_ROOT, filename)


class ExecutionAdapter(ABC):
    """执行适配器接口。

    每种第三方库（RDKit, Packmol, LAMMPS, PyBaMM, xTB, DiffDock 等）
    实现一个 Adapter，封装 CLI 调用或库 API 调用。
    """

    @abstractmethod
    def execute(self, prepared_input: dict[str, Any]) -> dict[str, Any]:
        """执行计算，返回原始输出。"""
        ...

    @abstractmethod
    def parse_output(self, raw_output: Any) -> dict[str, Any]:
        """解析原始输出为结构化 dict。"""
        ...

    @abstractmethod
    def get_resource_requirements(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """返回资源需求（cpu, memory, gpu, walltime 等）。"""
        ...

    def validate_input(self, input_data: dict[str, Any]) -> list[str]:
        """可选：校验输入，返回错误列表。"""
        return []