"""buyables 共享常量与规范化 — 单一事实来源。

Pricer（容器内运行时，makeit 包）与 sync_buyables（宿主构建期）共用本模块，
避免 EXCLUDE_SMILES 与 SMILES 规范化在两处各自维护导致语义漂移。

注意：本模块运行于 ASKCOS 容器（Python 3.5），禁止使用 f-string、
``str | None`` 注解、``from __future__ import annotations`` 等 3.6+ 语法；
仅依赖 rdkit（容器与本机测试环境均可用）。
"""
import time

import rdkit.Chem as Chem

# 人工单-NCO 中间体永不视为可购买：否则 MCTS 会在单-NCO 处停机，
# 无法展开到真二胺原料（MDA/HMD）。此处 SMILES 须为 RDKit 规范形式
# （canonical_smiles 输出）。
EXCLUDE_SMILES = {
    'Nc1ccc(Cc2ccc(N=C=O)cc2)cc1',  # MDA-NCO
    'NCCCCCCN=C=O',                  # HMD-NCO
}


def canonical_smiles(smiles):
    """规范 SMILES 用于去重；解析失败返回 None（与可购判定一致）。"""
    try:
        mol = Chem.MolFromSmiles(smiles)
        return Chem.MolToSmiles(mol, isomericSmiles=True) if mol is not None else None
    except Exception:
        return None


def enterprise_refresh_due(last_loaded_at, ttl, now=None):
    """判断企业物料库缓存是否已过期、需要刷新。

    失败时上层也应更新 last_loaded_at（进入冷却期），
    避免每次 lookup 都触发 3s 连接超时阻塞。
    """
    if now is None:
        now = time.time()
    return (now - last_loaded_at) > ttl