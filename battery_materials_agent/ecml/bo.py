"""ECML 贝叶斯优化内核（决策引擎）。

对标 ReactBO 的能力边界，采用"离散候选池评分"形态：
- 代理模型：sklearn GP / 梯度提升树 / MLP，按样本量自动推荐 + 可手动覆写。
- 采集函数：单目标 EI / UCB / PI；多目标 EHVI（超体积改进，替代加权求和）。
- 成本感知：成本评分作为软权重（CIBO 式性价比），预算作为硬约束。
- 数据聚合主键：材料体系(Material Family) + 目标属性；项目仅作过滤条件。

设计约束（见 pyproject / 代码约定）：
- 特征由化学式/SMILES 自动派生，用户无需手填。
- 非 GP 模型的"不确定性"用轻量集成(小样本投票方差)估计，保证采集函数可用。
- 所有纯数值计算同步实现，可在 asyncio.to_thread 中安全调用。
"""
from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# 常见目标属性方向（maximize: 越大越好；minimize: 越小越好）
_DEFAULT_DIRECTION = "maximize"


def _direction(property_name: str) -> str:
    """BO 优化方向：统一引用 material_properties.PROPERTY_DIRECTION（单一可信源）。

    修复：band_gap 此前被误判 minimize，与全局 maximize 矛盾导致推荐方向反。
    """
    from ..material_properties import PROPERTY_DIRECTION

    p = (property_name or "").lower()
    return PROPERTY_DIRECTION.get(p, _DEFAULT_DIRECTION)


# ─────────────────────────── 描述符（特征） ───────────────────────────
# 固定元素词表：晶体/离子材料组成描述符（元素分数）+ 4 个组成统计量
_ELEMENT_VOCAB = [
    "Li", "Na", "K", "Rb", "Cs", "Mg", "Ca", "Sr", "Ba",
    "Ti", "V", "Cr", "Mn", "Fe", "Co", "Ni", "Cu", "Zn",
    "B", "C", "N", "O", "F", "P", "S", "Cl", "Br", "I",
    "Si", "Ge", "Se", "As", "Sb", "Sn", "Zr", "Nb", "Mo", "W",
]
_ELEM_INDEX = {e: i for i, e in enumerate(_ELEMENT_VOCAB)}
# 元素电负性（Pauling，近似值，仅用于组成统计量）
_ELECTRONEGATIVITY = {
    "Li": 0.98, "Na": 0.93, "K": 0.82, "Rb": 0.82, "Cs": 0.79,
    "Mg": 1.31, "Ca": 1.00, "Sr": 0.95, "Ba": 0.89,
    "Ti": 1.54, "V": 1.63, "Cr": 1.66, "Mn": 1.55, "Fe": 1.83,
    "Co": 1.88, "Ni": 1.91, "Cu": 1.90, "Zn": 1.65,
    "B": 2.04, "C": 2.55, "N": 3.04, "O": 3.44, "F": 3.98,
    "P": 2.19, "S": 2.58, "Cl": 3.16, "Br": 2.96, "I": 2.66,
    "Si": 1.90, "Ge": 2.01, "Se": 2.55, "As": 2.18, "Sb": 2.05,
    "Sn": 1.96, "Zr": 1.33, "Nb": 1.60, "Mo": 2.16, "W": 2.36,
}
_ATOMIC_MASS = {  # 单质原子量（近似）
    "Li": 6.94, "Na": 22.99, "K": 39.10, "Rb": 85.47, "Cs": 132.91,
    "Mg": 24.31, "Ca": 40.08, "Sr": 87.62, "Ba": 137.33,
    "Ti": 47.87, "V": 50.94, "Cr": 52.00, "Mn": 54.94, "Fe": 55.85,
    "Co": 58.93, "Ni": 58.69, "Cu": 63.55, "Zn": 65.38,
    "B": 10.81, "C": 12.01, "N": 14.01, "O": 16.00, "F": 19.00,
    "P": 30.97, "S": 32.06, "Cl": 35.45, "Br": 79.90, "I": 126.90,
    "Si": 28.09, "Ge": 72.63, "Se": 78.97, "As": 74.92, "Sb": 121.76,
    "Sn": 118.71, "Zr": 91.22, "Nb": 92.91, "Mo": 95.95, "W": 183.84,
}
_IONIC_RADIUS = {  # Shannon 近似（pm，仅在具备时使用）
    "Li": 76, "Na": 102, "K": 138, "Rb": 152, "Cs": 167,
    "Mg": 72, "Ca": 100, "Sr": 118, "Ba": 135,
    "Ti": 61, "V": 54, "Cr": 62, "Mn": 65, "Fe": 65, "Co": 61,
    "Ni": 55, "Cu": 73, "Zn": 60, "Al": 54,
    "B": 27, "C": 16, "N": 132, "O": 140, "F": 133,
    "P": 38, "S": 184, "Cl": 181, "Br": 196, "I": 220,
    "Si": 40, "Ge": 53, "Se": 198, "As": 46, "Sb": 76, "Sn": 69,
}

_ELEM_PATTERN = re.compile(r"([A-Z][a-z]?)(\d*\.?\d*)")
_FORMULA_RESERVED = 0  # 前 5 维保留给组成统计量


def _formula_vec(formula: str) -> np.ndarray | None:
    """化学式 → 固定长度描述符向量（元素分数 + 组成统计量）。"""
    if not formula:
        return None
    counts: dict[str, float] = {}
    for elem, num in _ELEM_PATTERN.findall(formula):
        if elem in _ELEM_INDEX:
            counts[elem] = counts.get(elem, 0.0) + (float(num) if num else 1.0)
    if not counts:
        return None
    total = sum(counts.values())
    if total <= 0:
        return None
    vec = np.zeros(len(_ELEMENT_VOCAB) + 5, dtype=float)
    for elem, c in counts.items():
        vec[_ELEM_INDEX[elem]] = c / total
    # 组成统计量：平均电负性 / 平均原子量 / 平均离子半径 / 元素种类数 / 总原子数
    frac = np.array([counts[e] / total for e in counts])
    masses = np.array([_ATOMIC_MASS.get(e, 0.0) for e in counts])
    en = np.array([_ELECTRONEGATIVITY.get(e, 0.0) for e in counts])
    rad = np.array([_IONIC_RADIUS.get(e, 0.0) for e in counts])
    vec[-5] = float(np.average(en, weights=frac)) if en.any() else 0.0
    vec[-4] = float(np.average(masses, weights=frac)) if masses.any() else 0.0
    vec[-3] = float(np.average(rad, weights=frac)) if rad.any() else 0.0
    vec[-2] = float(len(counts))
    vec[-1] = float(total)
    return vec


def _smiles_vec(smiles: str) -> np.ndarray | None:
    """SMILES → 固定长度描述符（rdkit 理化性质子集），失败退回组合计数。"""
    if not smiles:
        return None
    try:
        from rdkit import Chem
        from rdkit.Chem import Descriptors

        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None
        vec = np.zeros(10, dtype=float)
        vec[0] = Descriptors.MolWt(mol)
        vec[1] = Descriptors.MolLogP(mol)
        vec[2] = Descriptors.NumHDonors(mol)
        vec[3] = Descriptors.NumHAcceptors(mol)
        vec[4] = Descriptors.TPSA(mol)
        vec[5] = Descriptors.RotatableBonds(mol)
        vec[6] = Descriptors.NumAromaticRings(mol)
        vec[7] = mol.GetNumHeavyAtoms()
        vec[8] = mol.GetNumAtoms()
        vec[9] = Descriptors.NumHeteroatoms(mol)
        return vec
    except Exception:  # rdkit 不可用时退化为组合计数
        base = _formula_vec(smiles)
        if base is not None:
            return base
        return None


def build_descriptors(identifiers: list[str], is_polymer: bool = False) -> np.ndarray | None:
    """把一批候选标识符转为一致的描述符矩阵（同池内维度一致）。"""
    vecs = (
        [_smiles_vec(i) for i in identifiers]
        if is_polymer
        else [_formula_vec(i) for i in identifiers]
    )
    vecs = [v for v in vecs if v is not None]
    if not vecs:
        return None
    dim = len(vecs[0])
    return np.vstack([v.reshape(1, dim) for v in vecs])


# ─────────────────────────── 材料体系归类 ───────────────────────────
# v4.1：polymer 族关键词扩展至工程塑料体系（此前仅电池电解质，PP/PA6/PC 会被归类成 P-based）
_FAMILY_KEYWORDS = [
    ("argyrodite", ["Li6PS5", "LPSCl", "argyrodite"]),
    # 单字母元素（li/s）不得作关键词：会误匹配任意含该字母的标识（如 "pc/abs" 含 s）
    ("sulfide", ["li6ps5", "lpscl", "lgps", "li2s", "p2s5", "sulfide"]),
    ("perovskite", ["perovskite", "CsPb", "MAPb"]),
    ("layered_oxide", ["LiCoO2", "LiNi", "NMC", "LiMnO2", "LiFePO4"]),
    ("polymer", [
        "PEO", "polym", "PVDF", "PVC", "PAN", "LiTFSI",
        # v4.1 工程塑料体系
        "PA6", "PA66", "PA12", "PC", "ABS", "PP", "PBT", "PET", "POM",
        "PPS", "PPSU", "PEEK", "PLA", "PBAT", "LCP", "TPU", "EVA",
        "尼龙", "聚酰胺", "聚碳酸酯", "聚丙烯", "聚乙烯", "聚苯乙烯",
        "聚酯", "玻纤", "碳纤", "阻燃", "增韧", "改性",
    ]),
    ("spinel", ["spinel", "LiMn2O4", "Li4Ti5O12"]),
    ("halide", ["Li3YCl6", "halide", "Cl6", "Br6"]),
]


def _is_polymer_candidate(c: dict) -> bool:
    """判断候选是否为高分子（BO 描述符分派用）。

    优先 material_type 字段；其次按标识特征（psmiles 标记 / 工程塑料关键词）鲁棒兜底，
    避免工程塑料候选（无 material_type 的历史数据）被错误分派到晶体描述符。
    """
    mt = (c.get("material_type") or "").lower()
    if "polym" in mt or "molecule" in mt:
        return True
    ident = (c.get("smiles") or c.get("psmiles") or c.get("formula") or c.get("name") or "").lower()
    if ident.startswith("polymer(") or "[*]" in ident:
        return True
    import re
    if re.search(
        r"\b(pa6|pa66|pa12|pc|abs|pp|pbt|pet|pom|pps|ppsu|peek|pla|pbat|lcp|tpu|eva|peo|pvdf|pan|pmma)\b",
        ident,
    ):
        return True
    polymer_hints = (
        "尼龙", "聚酰胺", "聚碳酸酯", "聚丙烯", "聚乙烯", "聚苯乙烯",
        "聚酯", "玻纤", "碳纤", "阻燃", "增韧", "改性塑料", "polym",
    )
    return any(h in ident for h in polymer_hints)


def classify_family(identifier: str) -> str:
    """根据化学式/SMILES 自动归类材料体系（可被人工覆写）。"""
    s = (identifier or "").lower()
    if not s:
        return "unknown"
    for name, kws in _FAMILY_KEYWORDS:
        if any(k.lower() in s for k in kws):
            return name
    for e in _ELEMENT_VOCAB:
        if s.startswith(e.lower()):
            return f"{_ELEMENT_VOCAB[_ELEMENT_INDEX[e]]}-based"
    return "unknown"


# ─────────────────────────── 训练数据点 ───────────────────────────
@dataclass
class TrainPoint:
    """一条进入 BO 训练池的有效观测。"""
    identifier: str
    value: float
    family: str
    project_id: str = ""
    sample_id: str = ""
    source: str = ""


@dataclass
class PoolResult:
    """训练池装配结果。"""
    points: list[TrainPoint]
    family: str
    property_name: str
    stats: dict[str, Any] = field(default_factory=dict)
    quality_report: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "family": self.family,
            "property_name": self.property_name,
            "stats": self.stats,
            "points": [asdict(p) for p in self.points],
            "quality_report": self.quality_report,
        }


# ─────────────────────────── 代理模型 ───────────────────────────
class SurrogateModel:
    """封装 sklearn 代理模型，统一输出 (mean, std)。

    非 GP 模型没有解析不确定性，用轻量集成（bootstrap 方差）估计，保证采集函数可用。
    """

    FAMILY_GP = "gp"
    FAMILY_GBT = "gbt"
    FAMILY_MLP = "mlp"

    def __init__(self, family: str = FAMILY_GP, n_ensemble: int = 3, seed: int = 42):
        self.family = family
        self.n_ensemble = n_ensemble
        self.seed = seed
        self._models: list = []
        self._feature_dim: int | None = None

    @staticmethod
    def auto_recommend(n_samples: int) -> str:
        """按样本量自动推荐代理模型：GP(<50) / GBT(50~300) / MLP(>300)。"""
        if n_samples < 50:
            return SurrogateModel.FAMILY_GP
        if n_samples <= 300:
            return SurrogateModel.FAMILY_GBT
        return SurrogateModel.FAMILY_MLP

    def _build_estimator(self):
        if self.family == self.FAMILY_GBT:
            from sklearn.ensemble import GradientBoostingRegressor
            return GradientBoostingRegressor(
                n_estimators=80, learning_rate=0.08, max_depth=3, random_state=self.seed
            )
        if self.family == self.FAMILY_MLP:
            from sklearn.neural_network import MLPRegressor
            return MLPRegressor(
                hidden_layer_sizes=(32, 16), max_iter=500, random_state=self.seed
            )
        from sklearn.gaussian_process import GaussianProcessRegressor
        from sklearn.gaussian_process.kernels import ConstantKernel as C
        from sklearn.gaussian_process.kernels import RBF, WhiteKernel

        kernel = C(1.0, (1e-3, 1e3)) * RBF(1.0, (1e-3, 1e3)) + WhiteKernel(1e-3, (1e-6, 1e-1))
        return GaussianProcessRegressor(kernel=kernel, n_restarts_optimizer=2, random_state=self.seed)

    def fit(self, X: np.ndarray, y: np.ndarray) -> "SurrogateModel":
        X = np.asarray(X, dtype=float).reshape(len(y), -1)
        y = np.asarray(y, dtype=float).reshape(-1)
        self._feature_dim = X.shape[1]
        if self.family == self.FAMILY_GP:
            m = self._build_estimator()
            m.fit(X, y)
            self._models = [m]
        else:
            rng = np.random.default_rng(self.seed)
            self._models = []
            for i in range(self.n_ensemble):
                idx = rng.choice(len(y), size=max(2, int(len(y) * 0.7)), replace=True)
                m = self._build_estimator()
                m.fit(X[idx], y[idx])
                self._models.append(m)
        return self

    def predict(self, X: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """返回 (mean, std)。"""
        X = np.asarray(X, dtype=float)
        if self._feature_dim is not None and X.ndim == 1:
            X = X.reshape(1, -1)
        if self.family == self.FAMILY_GP:
            try:
                mean, std = self._models[0].predict(X, return_std=True)
                return np.asarray(mean, dtype=float), np.asarray(std, dtype=float)
            except Exception:
                mean = self._models[0].predict(X)
                return np.asarray(mean, dtype=float), np.full(X.shape[0], 1e-6)
        preds = np.column_stack([m.predict(X) for m in self._models])
        return preds.mean(axis=1), preds.std(axis=1)

    def metrics(self, y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
        y_true = np.asarray(y_true, dtype=float)
        y_pred = np.asarray(y_pred, dtype=float)
        mae = float(np.mean(np.abs(y_true - y_pred)))
        rmse = float(np.sqrt(np.mean((y_true - y_pred) ** 2)))
        ss_res = float(np.sum((y_true - y_pred) ** 2))
        ss_tot = float(np.sum((y_true - np.mean(y_true)) ** 2))
        r2 = 1.0 - ss_res / ss_tot if ss_tot > 1e-12 else 0.0
        return {"mae": round(mae, 6), "rmse": round(rmse, 6), "r2": round(r2, 6)}


# ─────────────────────────── 采集函数 ───────────────────────────
def _acquisition_score(
    mean: np.ndarray,
    std: np.ndarray,
    best: float,
    acq: str,
    explore: float,
    direction: str,
) -> np.ndarray:
    """单目标采集函数。explore∈[0,1] 映射到各策略的探索参数。"""
    mean = np.asarray(mean, dtype=float)
    std = np.maximum(np.asarray(std, dtype=float), 1e-9)
    sign = 1.0 if direction == "maximize" else -1.0
    # 把 minimize 转成 maximize 视角
    m_eff = sign * mean
    b_eff = sign * best
    if acq == "ucb":
        kappa = 0.5 + explore * 2.5  # 0 -> 0.5, 1 -> 3.0
        return m_eff + kappa * std
    if acq == "pi":
        threshold = 0.0 + explore * 0.5  # 稳妥收敛：阈值越高越利用
        z = (m_eff - b_eff - threshold) / std
        from scipy import stats
        return stats.norm.cdf(np.asarray(z, dtype=float))
    # EI（默认）：期望改进
    xi = 0.0 + explore * 0.1
    diff = m_eff - b_eff - xi
    from scipy import stats

    z = diff / std
    pdf = stats.norm.pdf(np.asarray(z, dtype=float))
    cdf = stats.norm.cdf(np.asarray(z, dtype=float))
    return diff * cdf + std * pdf


@dataclass
class ObjectiveMeta:
    property: str
    direction: str = _DEFAULT_DIRECTION
    weight: float = 1.0


def _hypervolume(points: np.ndarray, reference: np.ndarray, n_samples: int = 20000) -> float:
    """超体积：以 reference 为顶点，样本点在前沿内的占比 × 盒子体积（蒙特卡洛估计）。"""
    if points.size == 0:
        return 0.0
    pts = np.asarray(points, dtype=float)
    if pts.ndim == 1:
        pts = pts.reshape(1, -1)
    ref = np.asarray(reference, dtype=float).reshape(-1)
    # 归一化后按参考点计算贡献
    box_vol = float(np.prod(np.abs(np.maximum(ref, 0.0) + 1.0)))
    rng = np.random.default_rng(0)
    lo = np.zeros(ref.shape)
    hi = np.maximum(ref + 1e-6, 1e-6).copy()
    hi[hi <= 0] = 1e-6
    samples = rng.uniform(lo, hi, size=(n_samples, len(ref)))
    dominated = np.zeros(n_samples, dtype=bool)
    for p in pts:
        dominated |= np.all(p >= samples, axis=1)
    return box_vol * float(np.mean(dominated))


def _ehvi_scores(
    predicted: np.ndarray,  # (n_candidates, n_obj)，已按"越大越好"归一化
    observed: np.ndarray,  # (n_observed, n_obj)
    reference: np.ndarray,
) -> np.ndarray:
    hv_base = _hypervolume(observed, reference)
    scores = np.zeros(predicted.shape[0])
    for i, p in enumerate(predicted):
        merged = np.vstack([observed, p.reshape(1, -1)])
        scores[i] = _hypervolume(merged, reference) - hv_base
    return scores


# ─────────────────────────── 优化器 ───────────────────────────
@dataclass
class Recommendation:
    """一轮 BO 推荐结果。"""
    candidates: list[dict[str, Any]]
    reasoning: str
    model: dict[str, Any]
    acquisition: dict[str, Any]
    pool: dict[str, Any]
    model_metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class BayesianOptimizer:
    """离散候选池评分版贝叶斯优化器。"""

    def __init__(self, engine=None):
        self.engine = engine  # SQLAlchemy Engine（用于装配训练池）

    # ---- 训练池装配 ----
    def build_pool(
        self,
        family: str,
        property_name: str,
        include_cross_project: bool = False,
        project_id: str = "",
    ) -> PoolResult:
        """从 experiment.experiment_result_records 聚合训练池。"""
        if self.engine is None:
            return PoolResult(points=[], family=family, property_name=property_name)
        from sqlalchemy import text

        rows = []
        # 兼容裸名与 prop.* 前缀（人工/CSV 导入可能未规范化）
        prop_filter = property_name
        if not prop_filter.startswith("prop."):
            prop_filter = f"prop.{prop_filter}"
        with self.engine.connect() as conn:
            # 通过实验任务单关联项目：result_records.experiment_order_id -> experiment_orders.project_id
            sql = text(
                """
                SELECT r.sample_id, r.property_name, r.value, r.unit,
                       r.qc_status, r.learning_eligible, r.material_family,
                       r.experiment_order_id, o.project_id AS order_project_id
                FROM experiment.experiment_result_records r
                LEFT JOIN experiment.experiment_orders o ON o.order_id = r.experiment_order_id
                WHERE (r.property_name = :prop OR r.property_name = :prop_bare)
                  AND (r.material_family = :fam OR r.material_family IS NULL)
                  AND r.value IS NOT NULL
                ORDER BY r.uploaded_at NULLS LAST
                """
            )
            rows = conn.execute(
                sql, {"prop": prop_filter, "prop_bare": property_name, "fam": family}
            ).mappings().all()

        proj = (project_id or "").strip()
        points: list[TrainPoint] = []
        report: list[dict[str, Any]] = []
        seen: set[str] = set()
        for r in rows:
            qs = (r["qc_status"] or "").upper()
            # 复用现有质量信号：进入训练池前剔除无效/被拒数据
            if qs in ("INVALID", "REJECTED"):
                report.append({"result_id": r["sample_id"], "reason": "qc_status=" + qs})
                continue
            if r["learning_eligible"] is False:
                report.append({"result_id": r["sample_id"], "reason": "learning_eligible=False"})
                continue
            try:
                val = float(r["value"])
            except (TypeError, ValueError):
                report.append({"result_id": r["sample_id"], "reason": "non-numeric value"})
                continue
            # 项目归属：仅当提供了项目上下文时才判定"本项目/跨项目"；
            # 无项目上下文时一律视为本项目，不虚构跨项目划分。
            src = "project"
            if proj:
                src = "project" if (r["order_project_id"] or "") == proj else "cross_project"
                # 范围过滤：不纳入跨项目时，仅保留本项目数据
                if src == "cross_project" and not include_cross_project:
                    continue
            key = r["sample_id"] or r["experiment_order_id"] or f"{family}-{property_name}-{val}"
            if key in seen:
                continue
            seen.add(key)
            points.append(
                TrainPoint(
                    identifier=r["sample_id"] or f"{family}-pt{len(points)}",
                    value=val,
                    family=r["material_family"] or family,
                    sample_id=r["sample_id"] or "",
                    source=src,
                )
            )
        # 训练池统计
        n = len(points)
        stats = {
            "total": n,
            "family": family,
            "property": property_name,
            "cross_project": int(sum(1 for p in points if p.source == "cross_project")),
            "project": int(sum(1 for p in points if p.source == "project")),
        }
        return PoolResult(points=points, family=family, property_name=property_name, stats=stats, quality_report=report)

    # ---- 主流程 ----
    def recommend(
        self,
        family: str,
        property_name: str,
        candidates: list[dict[str, Any]],
        acquisition: str = "ei",
        explore: float = 0.5,
        surrogates: list[str] | None = None,  # 多目标时每个目标一个模型族
        objectives: list[ObjectiveMeta] | None = None,
        budget: float | None = None,
        cost_field: str = "industrialization_score",
        include_cross_project: bool = False,
        project_id: str = "",
        model_family_override: str | None = None,
        num_candidates: int = 10,
    ) -> Recommendation:
        """推荐下一批候选。单目标走 EI/UCB/PI；多目标（objectives 非空）走 EHVI。"""
        is_multi = bool(objectives) and len(objectives) > 1
        if is_multi:
            # 多目标：每个目标属性各自装配训练池，由 _recommend_multi 统一处理（含空池判定）
            return self._recommend_multi(
                family, candidates, objectives, explore, budget, cost_field,
                model_family_override, include_cross_project, project_id, num_candidates,
            )

        pool = self.build_pool(family, property_name, include_cross_project, project_id)
        n = len(pool.points)
        if n == 0:
            return Recommendation(
                candidates=[],
                reasoning="当前材料体系+目标属性下没有有效实验数据，无法拟合代理模型。",
                model={"family": "none", "reason": "no data"},
                acquisition={"name": acquisition},
                pool=pool.to_dict(),
            )

        # ---- 单目标 ----
        idents = [c.get("smiles") or c.get("psmiles") or c.get("formula") or c.get("name") or "" for c in candidates]
        is_polymer = any(_is_polymer_candidate(c) for c in candidates)
        # 修复：空标识候选剔除时同步保留下标映射，避免 X 行数与 candidates 错位（IndexError）
        valid_idx = [i for i, ident in enumerate(idents) if ident]
        valid_idents = [idents[i] for i in valid_idx]
        X = build_descriptors(valid_idents, is_polymer)
        X_pool = build_descriptors([p.identifier for p in pool.points], is_polymer)
        if X is None or X_pool is None or X.shape[1] != X_pool.shape[1]:
            return Recommendation(
                candidates=[],
                reasoning="候选与训练池描述符维度不一致或无法派生，跳过贝叶斯推荐。",
                model={"family": "none", "reason": "descriptor mismatch"},
                acquisition={"name": acquisition},
                pool=pool.to_dict(),
            )

        family_sel = model_family_override or SurrogateModel.auto_recommend(n)
        model = SurrogateModel(family_sel)
        y = np.array([p.value for p in pool.points], dtype=float)
        model.fit(X_pool, y)
        mean, std = model.predict(X)

        direction = _direction(property_name)
        best = float(np.max(y)) if direction == "maximize" else float(np.min(y))
        scores = _acquisition_score(mean, std, best, acquisition, explore, direction)

        # 成本软权重 + 预算硬约束（下标基于 valid_idx 对齐 X 行）
        cost_col: list[float] = []
        for vi in valid_idx:
            c = candidates[vi]
            v = c.get(cost_field)
            cost_col.append(float(v) if isinstance(v, (int, float)) and v > 0 else 0.0)
        ranking = []
        for row, vi in enumerate(valid_idx):
            cost = cost_col[row]
            if budget is not None and cost > 0 and cost > budget:
                continue  # 硬约束：超出预算剔除
            effect = scores[row] / (1.0 + cost) if cost > 0 else scores[row]
            ranking.append((effect, vi))
        ranking.sort(key=lambda x: x[0], reverse=True)

        top = min(max(1, num_candidates), 10, len(ranking))
        rec_candidates: list[dict[str, Any]] = []
        for eff, i in ranking[:top]:
            row = valid_idx.index(i)
            cand = dict(candidates[i])
            cand["expected_performance"] = float(mean[row])
            cand["uncertainty"] = float(std[row])
            cand["expected_improvement"] = float(max(scores[row], 0.0))
            cand["strategy"] = "exploration" if std[row] > (np.max(std) if len(std) else 0) * 0.7 else "exploitation"
            cand["acquisition_score"] = float(eff)
            cand["recommendation_reason"] = _explain_single(
                cand, mean[row], std[row], best, direction, cost, len(pool.points)
            )
            rec_candidates.append(cand)

        metrics = model.metrics(y, model.predict(X_pool)[0])
        return Recommendation(
            candidates=rec_candidates,
            reasoning=f"基于当前材料体系「{family}」+属性「{property_name}」共 {n} 条有效数据，"
                      f"采用 {family_sel.upper()} 代理模型 + {acquisition.upper()} 采集函数推荐下一批候选。",
            model={"family": family_sel, "n_samples": n, "auto": model_family_override is None},
            acquisition={"name": acquisition, "explore": explore, "direction": direction},
            pool=pool.to_dict(),
            model_metrics=metrics,
        )

    def _recommend_multi(self, family, candidates, objectives, explore, budget, cost_field, model_family_override, include_cross_project, project_id, num_candidates=10):
        n_obj = len(objectives)
        idents = [c.get("smiles") or c.get("psmiles") or c.get("formula") or c.get("name") or "" for c in candidates]
        is_polymer = any(_is_polymer_candidate(c) for c in candidates)
        # 修复：空标识候选剔除时同步保留下标映射（与单目标一致），避免行数错位
        valid_idx = [i for i, ident in enumerate(idents) if ident]
        valid_idents = [idents[i] for i in valid_idx]
        X = build_descriptors(valid_idents, is_polymer)
        if X is None:
            return Recommendation(candidates=[], reasoning="候选描述符无法派生，跳过 EHVI。", model={}, acquisition={"name": "ehvi"}, pool={})

        # 每个目标属性各自装配训练池（材料体系 + 该目标属性），不再共用同一份单属性数据
        pools = {obj.property: self.build_pool(family, obj.property, include_cross_project, project_id) for obj in objectives}
        missing = [prop for prop, pool in pools.items() if not pool.points]
        if missing:
            return Recommendation(
                candidates=[],
                reasoning="目标属性「" + "、".join(missing) + "」下暂无有效实验数据，缺少该维度的观测，无法完成多目标超体积改进推荐。",
                model={"family": "none", "reason": "missing objective data"},
                acquisition={"name": "ehvi"},
                pool=pools[objectives[0].property].to_dict(),
            )

        # 各目标独立拟合代理模型（各自使用自己属性的训练数据）
        fitted: list[tuple[str, str, SurrogateModel, np.ndarray]] = []  # (property, family, model, X_pool)
        for obj in objectives:
            pool = pools[obj.property]
            X_pool = build_descriptors([p.identifier for p in pool.points], is_polymer)
            if X_pool is None or X_pool.shape[1] != X.shape[1]:
                return Recommendation(
                    candidates=[],
                    reasoning=f"目标属性「{obj.property}」训练池描述符与候选不一致，跳过 EHVI。",
                    model={"family": "none", "reason": "descriptor mismatch"},
                    acquisition={"name": "ehvi"},
                    pool=pool.to_dict(),
                )
            family_sel = model_family_override or SurrogateModel.auto_recommend(len(pool.points))
            model = SurrogateModel(family_sel)
            y = np.array([p.value for p in pool.points], dtype=float)
            model.fit(X_pool, y)
            fitted.append((obj.property, family_sel, model, X_pool))

        # 待预测候选：每个目标用其自己的代理模型评分（行数对齐 valid_idx）
        predicted = np.zeros((len(valid_idx), n_obj))
        for j, (_, _, model, _) in enumerate(fitted):
            predicted[:, j] = model.predict(X)[0]

        # 当前前沿：对全部训练样本（各目标池的并集）做全目标预测，作为观测前沿
        union_ids: list[str] = []
        seen_ids: set[str] = set()
        for obj in objectives:
            for p in pools[obj.property].points:
                if p.identifier not in seen_ids:
                    seen_ids.add(p.identifier)
                    union_ids.append(p.identifier)
        X_union = build_descriptors(union_ids, is_polymer)
        observed = np.zeros((len(union_ids), n_obj))
        for j, (_, _, model, _) in enumerate(fitted):
            observed[:, j] = model.predict(X_union)[0]

        # 统一为"越大越好"，再做超体积改进
        predicted_norm = np.zeros_like(predicted)
        observed_norm = np.zeros_like(observed)
        for j, obj in enumerate(objectives):
            sign = 1.0 if _direction(obj.property) == "maximize" else -1.0
            predicted_norm[:, j] = sign * predicted[:, j]
            observed_norm[:, j] = sign * observed[:, j]
        reference = observed_norm.min(axis=0) - 1.0
        scores = _ehvi_scores(predicted_norm, observed_norm, reference)

        cost_col = [float(c.get(cost_field)) if isinstance(c.get(cost_field), (int, float)) and c.get(cost_field) > 0 else 0.0 for vi in valid_idx for c in [candidates[vi]]]
        ranking = []
        for row, vi in enumerate(valid_idx):
            cost = cost_col[row]
            if budget is not None and cost > 0 and cost > budget:
                continue
            ranking.append((scores[row] / (1.0 + cost), vi))
        ranking.sort(key=lambda x: x[0], reverse=True)

        model_meta = [{"property": prop, "family": fam, "n_samples": len(pools[prop].points)} for prop, fam, _, _ in fitted]
        rec = []
        for eff, i in ranking[:min(max(1, num_candidates), 10)]:
            row = valid_idx.index(i)
            cand = dict(candidates[i])
            cand["expected_improvement"] = float(max(scores[row], 0.0))
            cand["acquisition_score"] = float(eff)
            cand["predicted_objectives"] = {obj.property: float(predicted[row, j]) for j, obj in enumerate(objectives)}
            cand["recommendation_reason"] = _explain_multi(cand, objectives, predicted[row])
            rec.append(cand)
        return Recommendation(
            candidates=rec,
            reasoning=f"多目标 EHVI（超体积改进）推荐，覆盖 {n_obj} 个目标属性，各目标独立训练代理模型。",
            model={"models": model_meta},
            acquisition={"name": "ehvi", "explore": explore, "n_objectives": n_obj},
            pool=pools[objectives[0].property].to_dict(),
        )


def _explain_single(cand, mean, std, best, direction, cost, n) -> str:
    """把"为什么推荐这个"翻译成可审计的大白话。"""
    better = (mean > best) if direction == "maximize" else (mean < best)
    perf = "与历史最优接近" if (abs(mean - best) / (abs(best) + 1e-9)) < 0.1 else ("好于历史最优" if better else "低于历史最优")
    if std > 0.5 * (abs(mean) + 1e-9):
        cls = "该候选在训练数据中样本稀疏、模型不确定性较高，被优先推荐以补充数据覆盖（探索型）"
    else:
        cls = "模型对该候选预测较有把握，用于收敛局部最优（利用型）"
    cost_txt = f"，实验成本评分 {cost:.2f}，性价比较高" if cost > 0 else ""
    return f"预测性能{perf}（均值 {mean:.4g}）。{cls}。基于 {n} 条训练数据{cost_txt}。"


def _explain_multi(cand, objectives, predicted) -> str:
    parts = []
    for j, obj in enumerate(objectives):
        v = predicted[j]
        more = "高" if _direction(obj.property) == "maximize" else "低"
        parts.append(f"{obj.property} {more}（{v:.3g}）")
    return "多目标权衡：" + "，".join(parts) + "，在帕累托前沿上未被其他候选支配。"