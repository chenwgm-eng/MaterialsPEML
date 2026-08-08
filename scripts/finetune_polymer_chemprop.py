"""Chemprop 聚合物性质微调脚本。

从公开聚合物数据集（CSV，含 smiles 与目标列）微调 Chemprop 模型，
将权重落盘到 ``data/models/polymer_chemprop/<property>.ckpt``，
供 ``chemprop_adapter`` 真实推理使用。

用法::

    python scripts/finetune_polymer_chemprop.py \\
        --property glass_transition_temp \\
        --data path/to/polymer_tg.csv \\
        --smiles-col smiles --target-col tg --epochs 50

公开数据建议（有数据才真，缺数据则提示后退出，不做伪造）:
- 玻璃化转变温度: PolyInfo (polymer.nims.go.jp) 或 PolymerGNN 公开 Tg 数据集
- 离子电导率 / 带隙 / 弹性模量等: 对应领域公开 CSV

该脚本为研发工具，产出的权重文件用于真实 ML 预测路径。
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PROJECT = _HERE.parent
_OUTPUT_DIR = _PROJECT / "data" / "models" / "polymer_chemprop"

# 支持的性质与落盘名称（与 chemprop_adapter.SUPPORTED_PROPERTIES 对齐）。
SUPPORTED_PROPERTIES = (
    "ionic_conductivity",
    "glass_transition_temp",
    "dielectric_constant",
    "elastic_modulus",
    "thermal_conductivity",
    "decomposition_temp",
    "total_energy",
    "formation_energy",
)


def _require_backend() -> None:
    try:
        import chemprop  # noqa: F401
        import torch  # noqa: F401
        import lightning.pytorch  # noqa: F401
    except Exception as e:  # noqa: BLE001
        raise SystemExit(
            "缺少 chemprop / torch / lightning。请先安装可选依赖: pip install -e '.[ml]'"
        ) from e


def main() -> None:
    parser = argparse.ArgumentParser(description="Chemprop 聚合物性质微调")
    parser.add_argument("--property", required=True, help="目标性质名")
    parser.add_argument("--data", required=True, help="训练数据 CSV 路径")
    parser.add_argument("--smiles-col", default="smiles")
    parser.add_argument("--target-col", required=True)
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    if args.property not in SUPPORTED_PROPERTIES:
        raise SystemExit(f"不支持的性质: {args.property}，可选 {SUPPORTED_PROPERTIES}")

    _require_backend()

    import pandas as pd

    data_path = Path(args.data)
    if not data_path.is_file():
        raise SystemExit(
            f"未找到训练数据 {data_path}。请先下载/准备公开聚合物数据集（有数据才真，不做伪造）。"
        )

    df = pd.read_csv(data_path)
    if args.smiles_col not in df.columns or args.target_col not in df.columns:
        raise SystemExit(f"CSV 缺少列 {args.smiles_col} 或 {args.target_col}")
    df = df.dropna(subset=[args.smiles_col, args.target_col])
    df = df[[args.smiles_col, args.target_col]]
    smiles = df[args.smiles_col].astype(str).tolist()
    targets = df[args.target_col].astype(float).tolist()
    if not smiles:
        raise SystemExit("清洗后无有效样本，请检查数据列含义。")
    print(f"加载 {len(smiles)} 条样本，开始微调 Chemprop（{args.property}）...")

    # 延迟导入，避免无后端时脚本报错
    from chemprop import models
    from chemprop.data import (
        MoleculeDataLoader,
        MoleculeDatapoint,
        MoleculeDataset,
        split_data_by_ratio,
    )
    from chemprop.nn import Aggregation, RBFReadout
    from chemprop.nn.criterion import MSELoss
    from chemprop.nn.metrics import RMSE
    from chemprop.train import Trainer, make_dataloaders
    from lightning.pytorch.callbacks import ModelCheckpoint

    datapoints = [
        MoleculeDatapoint(smiles=[s], y=[[float(t)]]) for s, t in zip(smiles, targets)
    ]
    dataset = MoleculeDataset(datapoints)
    train_dset, val_dset, test_dset = split_data_by_ratio(dataset, (0.8, 0.1, 0.1), seed=args.seed)

    mpnn = models.MPNN(
        message_passing=models.MPNN.MessagePassing(d_model=300, depth=4),
        agg=Aggregation(blocks=[models.MPNN.AggregationBlock()]),
        predictor=RBFReadout(),
    )

    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ckpt_path = _OUTPUT_DIR / f"{args.property}.ckpt"
    checkpoint_cb = ModelCheckpoint(
        monitor="val_loss",
        filename=f"{args.property}_{{epoch}}",
        dirpath=str(_OUTPUT_DIR),
    )

    train_loader, val_loader, test_loader = make_dataloaders(
        train_dset, val_dset, test_dset, batch_size=args.batch_size, num_workers=0
    )
    trainer = Trainer(
        model=mpnn,
        loss_func=MSELoss(),
        metric=RMSE(),
        epochs=args.epochs,
        batch_size=args.batch_size,
        seed=args.seed,
        accelerator="auto",
    )
    trainer.train(train_loader, val_loader, test_loader, callbacks=[checkpoint_cb])

    best = checkpoint_cb.best_model_path
    if best and Path(best).is_file():
        shutil.copyfile(best, ckpt_path)
        print(f"权重已落盘: {ckpt_path}")
    else:
        print("未生成 checkpoint，请检查训练过程。")


if __name__ == "__main__":
    main()