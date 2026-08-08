"""PolymerGNN 小型多任务模型训练脚本（Tg + 介电常数 试点）。

在 OpenPoly 公开聚合物数据库（Wang 等, Chinese J. Polym. Sci. 2025;
https://github.com/WangGroupFDU/Openpoly_benchmark）上训练 GIN 模型，
权重落盘到 ``data/models/polymer_gnn/model.pt``，供 ``polymer_gnn_adapter`` 真实推理。

用法::

    python scripts/train_polymer_gnn.py --epochs 200 --hidden 128 --layers 3

说明: 该脚本为研发工具，产出真实训练权重（非伪造）。数据缺失时打印提示后退出。
"""
from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PROJECT = _HERE.parent
sys.path.insert(0, str(_PROJECT))

import torch
from torch import nn, optim
from torch_geometric.data import Batch

from battery_materials_agent.prediction.polymer_gnn import (
    PolymerGIN,
    compute_normalization,
    load_openpoly_csv,
    normalize_openpoly_features,
    psmiles_to_graph,
)


def _require_backend() -> None:
    try:
        import torch  # noqa: F401
        import torch_geometric  # noqa: F401
    except Exception as e:  # noqa: BLE001
        raise SystemExit("缺少 torch / torch_geometric。请先安装: pip install torch torch_geometric") from e


def _collate(batch) -> tuple[Batch, torch.Tensor]:
    """合并一批 (graph, tg_z, dielectric_z) 为 batch 数据与标准化标签矩阵 [N,2]（NaN=缺失）。"""
    data_list = [g for g, _, _ in batch]
    data = Batch.from_data_list(data_list)
    y = torch.full((len(batch), 2), float("nan"))
    for i, (_, tg_z, dielec_z) in enumerate(batch):
        if tg_z is not None:
            y[i, 0] = tg_z
        if dielec_z is not None:
            y[i, 1] = dielec_z
    return data, y


def _masked_loss(pred: torch.Tensor, y: torch.Tensor, normalization: dict) -> torch.Tensor:
    """多任务 MSE，仅对存在的标签计算（标准化空间）。"""
    loss = torch.tensor(0.0)
    count = 0
    for i, key in enumerate(("tg", "dielectric")):
        mask = ~torch.isnan(y[:, i])
        if mask.any() and normalization[key]["std"] > 1e-6:
            loss = loss + ((pred[mask, i] - y[mask, i]) ** 2).mean()
            count += 1
    return loss / max(count, 1)


def _evaluate(model, graphs, normalization) -> float:
    """校验集 RMSE（标准化空间，仅有效标签）。"""
    model.eval()
    data, y = _collate(graphs)
    with torch.no_grad():
        pred = model(data)
    se = 0.0
    count = 0
    for i in range(2):
        mask = ~torch.isnan(y[:, i])
        if mask.any():
            se += ((pred[mask, i] - y[mask, i]) ** 2).sum().item()
            count += mask.sum().item()
    return (se / max(count, 1)) ** 0.5


def _save_checkpoint(model, normalization, args, n_tg, n_dielec, edge_dim, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "state_dict": model.state_dict(),
            "normalization": normalization,
            "hidden_dim": args.hidden,
            "num_layers": args.layers,
            "edge_dim": edge_dim,
            "trained_properties": ["glass_transition_temp", "dielectric_constant"],
            "dataset": "OpenPoly (Wang et al., Chinese J. Polym. Sci. 2025)",
            "n_tg": n_tg,
            "n_dielectric": n_dielec,
        },
        out,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="PolymerGNN 多任务训练（Tg + 介电常数）")
    parser.add_argument("--data", default=str(_PROJECT / "data" / "polymer_gnn" / "openpoly_properties.csv"))
    parser.add_argument("--out", default=str(_PROJECT / "data" / "models" / "polymer_gnn" / "model.pt"))
    parser.add_argument("--epochs", type=int, default=200)
    parser.add_argument("--hidden", type=int, default=128)
    parser.add_argument("--layers", type=int, default=3)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--batch", type=int, default=32)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    _require_backend()

    data_path = Path(args.data)
    if not data_path.is_file():
        print(f"[PolymerGNN] 数据不存在: {data_path}。请先下载 OpenPoly 数据（见 README）。")
        return

    records = load_openpoly_csv(data_path)
    n_tg = sum(1 for r in records if r["tg"] is not None)
    n_dielec = sum(1 for r in records if r["dielectric"] is not None)
    print(f"[PolymerGNN] OpenPoly 载入 {len(records)} 条（Tg 有效 {n_tg}，介电常数有效 {n_dielec}）")
    if n_tg < 50 or n_dielec < 50:
        print("[PolymerGNN] 标签样本过少，放弃训练。")
        return

    torch.manual_seed(args.seed)
    random.seed(args.seed)

    # 建图（跳过解析失败的 PSMILES）
    graphs = []
    for r in records:
        g = psmiles_to_graph(r["psmiles"])
        if g is not None:
            graphs.append((g, r["tg"], r["dielectric"]))
    print(f"[PolymerGNN] 成功建图 {len(graphs)} / {len(records)}")

    random.shuffle(graphs)
    n_val = max(1, int(0.15 * len(graphs)))
    train, val = graphs[n_val:], graphs[:n_val]

    # 标准化标签（仅用训练集统计，避免泄漏）
    normalization = compute_normalization(train)
    train = normalize_openpoly_features(train, normalization)
    val = normalize_openpoly_features(val, normalization)

    model = PolymerGIN(
        x_dim=train[0][0].x.shape[1],
        edge_dim=train[0][0].edge_attr.shape[1],
        hidden_dim=args.hidden,
        num_layers=args.layers,
    )
    optimizer = optim.Adam(model.parameters(), lr=args.lr)
    best_val = float("inf")

    for epoch in range(args.epochs):
        model.train()
        total_loss = 0.0
        for i in range(0, len(train), args.batch):
            batch = train[i : i + args.batch]
            data, y = _collate(batch)
            optimizer.zero_grad()
            pred = model(data)
            loss = _masked_loss(pred, y, normalization)
            loss.backward()
            optimizer.step()
            total_loss += loss.item() * data.num_graphs
        avg_loss = total_loss / max(len(train), 1)

        val_score = _evaluate(model, val, normalization)
        if val_score < best_val:
            best_val = val_score
            _save_checkpoint(model, normalization, args, n_tg, n_dielec, train[0][0].edge_attr.shape[1], Path(args.out))
        if (epoch + 1) % 20 == 0 or epoch == 0:
            print(f"[PolymerGNN] epoch {epoch + 1}/{args.epochs}  train_loss={avg_loss:.4f}  val={val_score:.4f}")

    print(f"[PolymerGNN] 训练完成，最优校验 RMSE={best_val:.4f}，权重已保存: {args.out}")


if __name__ == "__main__":
    main()