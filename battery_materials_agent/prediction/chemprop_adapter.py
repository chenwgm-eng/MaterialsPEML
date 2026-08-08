"""Chemprop 真实权重接入适配器（可选依赖 + 权重落盘 + 优雅降级）。

- ``is_available()``：检测 chemprop / torch 是否可导入。
- ``load_model(property_name)``：从 ``data/models/polymer_chemprop/<property>.ckpt``
  加载 Chemprop 微调权重；缺失或加载失败返回 None。
- ``predict(smiles, property_name)``：返回 (value, confidence, model_label) 或 None。

policy: 任何依赖缺失 / 权重缺失 / 推理异常均返回 None，由调用方回退到描述符
线性模型并标记 degraded，绝不抛出阻断下游。
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 权重落盘目录：<项目根>/data/models/polymer_chemprop/
_MODEL_DIR = Path(__file__).resolve().parents[2] / "data" / "models" / "polymer_chemprop"

# 本适配器支持的聚合物性质（与 PolymerPropertyPredictor.PREDICTABLE_PROPERTIES 对齐）。
SUPPORTED_PROPERTIES: tuple[str, ...] = (
    "ionic_conductivity",
    "glass_transition_temp",
    "dielectric_constant",
    "elastic_modulus",
    "thermal_conductivity",
    "decomposition_temp",
    "total_energy",
    "formation_energy",
)


def _import_backend() -> tuple[bool, Any, Any]:
    """惰性导入 chemprop / torch，返回 (ok, chemprop模块或None, torch或None)。"""
    try:
        import chemprop  # noqa: F401
        import torch  # noqa: F401
        return True, chemprop, torch
    except Exception:  # noqa: BLE001
        return False, None, None


def is_available() -> bool:
    """返回 Chemprop 后端是否可导入。"""
    ok, _, _ = _import_backend()
    return ok


def _ckpt_path(property_name: str) -> Path:
    return _MODEL_DIR / f"{property_name}.ckpt"


def load_model(property_name: str) -> Any | None:
    """加载指定性质的 Chemprop 模型；不可用 / 缺失 / 加载失败返回 None。"""
    if property_name not in SUPPORTED_PROPERTIES:
        return None
    ok, _, _ = _import_backend()
    if not ok:
        return None
    ckpt = _ckpt_path(property_name)
    if not ckpt.is_file():
        return None
    try:
        from chemprop.models.model import MoleculeModel
        model = MoleculeModel.load_from_checkpoint(str(ckpt))
        model.eval()
        return model
    except Exception as e:  # noqa: BLE001
        logger.warning("加载 Chemprop 权重失败 (%s): %s", property_name, e)
        return None


def predict(smiles: str, property_name: str) -> tuple[float, float, str] | None:
    """用真实 Chemprop 权重预测单体 SMILES 的聚合物性质。

    Returns:
        (value, confidence, model_label)；任何失败返回 None。
    """
    if not smiles:
        return None
    model = load_model(property_name)
    if model is None:
        return None
    try:
        from chemprop.data import MoleculeDataLoader, MoleculeDataset, MoleculeDatapoint
        dataset = MoleculeDataset([MoleculeDatapoint(smiles=[smiles])])
        loader = MoleculeDataLoader(dataset, batch_size=1)
        outputs = []
        for batch in loader:
            outputs.extend(model.predict(batch, disable_tqdm=True))
        if not outputs:
            return None
        value = float(outputs[0])
        confidence = 0.85
        return value, confidence, "chemprop"
    except Exception as e:  # noqa: BLE001
        logger.warning("Chemprop 推理失败 (%s, %s): %s", property_name, smiles, e)
        return None