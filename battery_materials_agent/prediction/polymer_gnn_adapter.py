"""PolymerGNN 真实权重接入适配器（可选依赖 + 权重落盘 + 优雅降级）。

- ``is_available()``：检测 torch / torch_geometric / 共享模型模块是否可导入。
- ``load_model()``：从 ``data/models/polymer_gnn/model.pt`` 加载训练产出权重，
  不可用 / 缺失 / 加载失败返回 None。
- ``predict(psmiles, property_name)``：返回 (value, confidence, model_label) 或 None。

仅支持训练覆盖的两个试点性质：``glass_transition_temp`` / ``dielectric_constant``。

policy: 任何依赖缺失 / 权重缺失 / 推理异常均返回 None，由调用方回退到描述符
线性模型并标记 degraded，绝不抛出阻断下游。
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 权重落盘目录：<项目根>/data/models/polymer_gnn/
_MODEL_DIR = Path(__file__).resolve().parents[2] / "data" / "models" / "polymer_gnn"
_CKPT = _MODEL_DIR / "model.pt"

# 本适配器支持的性质（对齐训练任务）。property_name → 模型输出列索引。
SUPPORTED_PROPERTIES: dict[str, int] = {
    "glass_transition_temp": 0,
    "dielectric_constant": 1,
}

_model_cache: dict[str, Any] = {}


def is_available() -> bool:
    """返回 PolymerGNN 后端（torch + torch_geometric + 共享模块）是否可导入。"""
    try:
        import torch  # noqa: F401
        import torch_geometric  # noqa: F401
        import battery_materials_agent.prediction.polymer_gnn as _  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


def load_model() -> Any | None:
    """加载聚合物 GNN checkpoint（带缓存）；不可用 / 缺失 / 加载失败返回 None。"""
    if not is_available():
        return None
    if "model" in _model_cache:
        return _model_cache["model"]
    if not _CKPT.is_file():
        return None
    try:
        import torch
        from battery_materials_agent.prediction.polymer_gnn import PolymerGIN

        ckpt = torch.load(_CKPT, map_location="cpu", weights_only=False)
        # edge_dim 优先从 checkpoint 读取；旧权重缺失时从首个 GINEConv 的 lin 权重形状推断
        edge_dim = ckpt.get("edge_dim") or int(ckpt["state_dict"]["convs.0.lin.weight"].shape[1])
        model = PolymerGIN(
            x_dim=25,
            edge_dim=edge_dim,
            hidden_dim=ckpt["hidden_dim"],
            num_layers=ckpt["num_layers"],
        )
        model.load_state_dict(ckpt["state_dict"])
        model.eval()
        _model_cache.update({"model": model, "normalization": ckpt["normalization"], "ckpt": ckpt})
        return model
    except Exception as e:  # noqa: BLE001
        logger.warning("加载 PolymerGNN 权重失败: %s", e)
        return None


def predict(psmiles: str, property_name: str) -> tuple[float, float, str] | None:
    """用训练好的 PolymerGNN 权重预测单体 PSMILES 的聚合物性质。

    Returns:
        (value, confidence, model_label)；任何失败返回 None。
    """
    if property_name not in SUPPORTED_PROPERTIES:
        return None
    if not psmiles:
        return None
    model = load_model()
    if model is None:
        return None
    try:
        import torch
        from torch_geometric.data import Batch
        from battery_materials_agent.prediction.polymer_gnn import denormalize, psmiles_to_graph

        graph = psmiles_to_graph(psmiles)
        if graph is None:
            return None
        batch = Batch.from_data_list([graph])
        with torch.no_grad():
            out = model(batch)  # [1, 2] 标准化空间
        col = SUPPORTED_PROPERTIES[property_name]
        value = denormalize(out[0, col], property_name, _model_cache["normalization"])
        confidence = 0.85
        return value, confidence, "polymer_gnn"
    except Exception as e:  # noqa: BLE001
        logger.warning("PolymerGNN 推理失败 (%s, %s): %s", property_name, psmiles, e)
        return None