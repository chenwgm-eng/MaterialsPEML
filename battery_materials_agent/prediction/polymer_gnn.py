"""PolymerGNN 小型图神经网络：聚合度单体 PSMILES → 分子图 → Tg/介电常数 多任务回归。

本模块被两处共用：
- ``scripts/train_polymer_gnn.py``：在 OpenPoly 公开数据上训练真实权重。
- ``polymer_gnn_adapter.py``：加载训练产出权重做推理。

为保持"训练与推理使用同一 PSMILES→图 函数"，避免结构漂移，图构建与模型定义都放这里。

依赖 torch / torch_geometric，属可选重量依赖；由调用方（adapter）惰性导入本模块，
因此其他无关代码不受影响。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import torch
import torch.nn.functional as F
from torch import nn
from torch_geometric.data import Data
from torch_geometric.nn import BatchNorm, GINEConv, global_add_pool

# 本项目训练的两个试点性质 → OpenPoly 数据列名（预测结果 property_name 用左侧值）
PROPERTY_TARGETS: dict[str, str] = {
    "glass_transition_temp": "Tg (K)",
    "dielectric_constant": "Dielectric Constant Total",
}

# 图节点特征里预留的常见元素（含占位 other 与聚合点 dummy *）。
_ELEMENTS = ["C", "H", "O", "N", "S", "F", "Cl", "Br", "Si", "P"]
_MAX_DEGREE = 6
_HYBRIDIZATIONS = ["SP", "SP2", "SP3", "UNSPECIFIED"]


def atom_features(atom) -> list[float]:
    """计算单个 RDKit 原子的特征向量（25 维）。

    布局: 元素 one-hot(10) + other(1) + dummy[*](1) + degree one-hot(7)
          + hybridization one-hot(4) + aromatic(1) + in_ring(1) = 25。
    """
    sym = atom.GetSymbol()
    if sym == "*":
        feats = [0.0] * len(_ELEMENTS) + [0.0, 1.0]  # other=0, dummy=1
    else:
        feats = [1.0 if sym == e else 0.0 for e in _ELEMENTS]
        n_known = any(feats)
        feats += [0.0, 0.0]  # other、dummy 两个槽位
        if not n_known:
            feats[len(_ELEMENTS)] = 1.0  # 未知元素 → other 位

    degree = atom.GetDegree()
    feats += [1.0 if degree == d else 0.0 for d in range(_MAX_DEGREE + 1)]
    if degree > _MAX_DEGREE:
        feats[-1] = 1.0

    hib = str(atom.GetHybridization())
    feats += [1.0 if hib == h else 0.0 for h in _HYBRIDIZATIONS]
    if not any(feats[-len(_HYBRIDIZATIONS):]):
        feats[-1] = 1.0

    feats.append(1.0 if atom.GetIsAromatic() else 0.0)
    feats.append(1.0 if atom.IsInRing() else 0.0)
    return feats


def bond_features(bond) -> list[float]:
    """计算单条键的特征向量（7 维）。"""
    btype = bond.GetBondTypeAsDouble()
    feats = [1.0 if btype == t else 0.0 for t in (1.0, 2.0, 3.0, 1.5)]
    feats.append(1.0 if bond.GetIsConjugated() else 0.0)
    feats.append(1.0 if bond.IsInRing() else 0.0)
    stereo = str(bond.GetStereo())
    feats.append(1.0 if stereo == "STEREONONE" else 0.0)
    feats.append(1.0 if stereo == "STEREOZ" else 0.0)
    feats.append(1.0 if stereo == "STEREOE" else 0.0)
    return feats


def psmiles_to_graph(psmiles: str) -> Data | None:
    """把聚合度单体 PSMILES（含 [*]）转成 torch_geometric 图；解析失败返回 None。

    与训练、推理共用，保证输入编码一致。``[*]`` 作为 dummy 节点保留，保证
    训练数据的连接拓扑在推理时也能正确重建。
    """
    from rdkit import Chem

    if not psmiles:
        return None
    mol = Chem.MolFromSmiles(psmiles)
    if mol is None:
        return None

    x = [atom_features(a) for a in mol.GetAtoms()]
    if not x:
        return None

    edge_index: list[list[int]] = [[], []]
    edge_attr: list[list[float]] = []
    for bond in mol.GetBonds():
        i = bond.GetBeginAtomIdx()
        j = bond.GetEndAtomIdx()
        edge_index[0] += [i, j]
        edge_index[1] += [j, i]
        e = bond_features(bond)
        edge_attr += [e, e]

    return Data(
        x=torch.tensor(x, dtype=torch.float),
        edge_index=torch.tensor(edge_index, dtype=torch.long),
        edge_attr=torch.tensor(edge_attr, dtype=torch.float),
    )


class PolymerGIN(nn.Module):
    """小型 GIN 多任务模型：分子图 → 图嵌入 → Tg 与介电常数两个回归头。"""

    def __init__(self, x_dim: int, edge_dim: int, hidden_dim: int = 128, num_layers: int = 3):
        super().__init__()
        self.num_tasks = 2  # glass_transition_temp, dielectric_constant
        self.node_enc = nn.Linear(x_dim, hidden_dim)

        self.convs = nn.ModuleList()
        self.norms = nn.ModuleList()
        for _ in range(num_layers):
            self.convs.append(
                GINEConv(
                    nn.Sequential(
                        nn.Linear(hidden_dim, hidden_dim),
                        nn.ReLU(),
                        nn.Linear(hidden_dim, hidden_dim),
                    ),
                    edge_dim=edge_dim,
                )
            )
            self.norms.append(BatchNorm(hidden_dim))

        self.head_tg = nn.Sequential(nn.Linear(hidden_dim, hidden_dim), nn.ReLU(), nn.Linear(hidden_dim, 1))
        self.head_dielectric = nn.Sequential(nn.Linear(hidden_dim, hidden_dim), nn.ReLU(), nn.Linear(hidden_dim, 1))

    def forward(self, data: Data) -> torch.Tensor:
        x = F.relu(self.node_enc(data.x))
        for conv, norm in zip(self.convs, self.norms):
            x = x + F.relu(norm(conv(x, data.edge_index, edge_attr=data.edge_attr)))
        graph_emb = global_add_pool(x, data.batch)
        tg = self.head_tg(graph_emb)
        dielec = self.head_dielectric(graph_emb)
        return torch.cat([tg, dielec], dim=1)


def load_openpoly_csv(path: str | Path) -> list[dict]:
    """读取 OpenPoly 数据，返回 [{psmiles, tg, dielectric}]，仅保留至少一个标签有效的样本。"""
    import pandas as pd

    df = pd.read_csv(path)
    records: list[dict] = []
    for _, row in df.iterrows():
        psmiles = str(row.get("PSMILES", "")).strip()
        if not psmiles or psmiles == "nan":
            continue
        tg = _to_float(row.get("Tg (K)"))
        dielectric = _to_float(row.get("Dielectric Constant Total"))
        if tg is None and dielectric is None:
            continue
        records.append({"psmiles": psmiles, "tg": tg, "dielectric": dielectric})
    return records


def _to_float(value: Any) -> float | None:
    try:
        f = float(value)
        return f if f == f else None  # NaN → None
    except (TypeError, ValueError):
        return None


def compute_normalization(graphs: list) -> dict:
    """基于样本（仅有效标签）计算训练集均值/标准差，用于标签标准化与推理还原。"""
    tg_vals = [g[1] for g in graphs if g[1] is not None]
    dielec_vals = [g[2] for g in graphs if g[2] is not None]
    return {
        "tg": {"mean": float(torch.mean(torch.tensor(tg_vals))), "std": float(torch.std(torch.tensor(tg_vals)))},
        "dielectric": {
            "mean": float(torch.mean(torch.tensor(dielec_vals))),
            "std": float(torch.std(torch.tensor(dielec_vals))),
        },
    }


def normalize_openpoly_features(graphs: list, normalization: dict) -> list:
    """把样本标签标准化，返回 [(graph, tg_z, dielectric_z)]，缺失标签为 None。

    训练/校验共用，保证标签编码一致。
    """
    out = []
    for g, tg, dielec in graphs:
        tg_z = None if tg is None else (tg - normalization["tg"]["mean"]) / normalization["tg"]["std"]
        dielec_z = (
            None
            if dielec is None
            else (dielec - normalization["dielectric"]["mean"]) / normalization["dielectric"]["std"]
        )
        out.append((g, tg_z, dielec_z))
    return out


def denormalize(pred: torch.Tensor, property_name: str, normalization: dict) -> float:
    """把标准化后的预测还原为物理量。pred 为模型输出（batch 单样本）。"""
    key = "tg" if property_name == "glass_transition_temp" else "dielectric"
    stats = normalization[key]
    return float(pred.item() * stats["std"] + stats["mean"])