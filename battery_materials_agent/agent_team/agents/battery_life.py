"""Battery life prediction agents: Learner / Interpreter / Oracle (template-based, no LLM)."""
from __future__ import annotations

import math

# ===========================================================================
# Task 17 过拟合核查修复：性能寿命预测原先在全部数据上拟合，
# 仅以训练集 R² 与样本量直接计算置信度，对完美符合指数衰减的样本会得到
# R²=1.0 / confidence=1.0 的不合理结果。下面新增训练/测试集分离、K-Fold
# 交叉验证、置信区间、模型版本号，并将置信度上限封顶为 0.95。
# ===========================================================================
MODEL_VERSION = "1.1.0"          # 模型版本号（前端展示用）
MIN_SAMPLES_FOR_SPLIT = 5        # 低于此值不做 train/test split
MIN_SAMPLES_FOR_CV = 10          # 低于此值不做 K-Fold CV
LOW_DATA_THRESHOLD = 30          # 低于此值标记 low_data_warning
CV_FOLDS = 5                     # K-Fold 折数
TEST_SIZE_RATIO = 0.2            # 20% 作为测试集（时序友好：取末尾段）
MAX_CONFIDENCE = 0.95            # 置信度上限：避免不合理的 100%
LOW_DATA_CONFIDENCE_CAP = 0.6    # 数据不足时置信度封顶
OVERFIT_GAP_THRESHOLD = 0.2      # 训练集-测试集 R² 差值超过此值视为过拟合
UNSTABLE_STD_THRESHOLD = 0.1     # K-Fold R² 标准差超过此值视为不稳定


def _fit_exponential_decay(xs: list[float], ys: list[float]) -> tuple[float, float, float]:
    """对 y = a * exp(-k * x) 做对数线性化最小二乘拟合。

    Returns:
        (a, k, r_squared)：a 为初始值，k 为衰减率，r_squared 为对数空间拟合优度。
        数据不足或异常时返回 (100.0, 0.0, 0.0)。

    注意：r_squared 在对数空间计算，对完美符合指数衰减的样本会得到 1.0，
    不能单独用于评估模型外推可靠性，需配合 train/test split 与 K-Fold CV。
    """
    pts = [(float(x), float(y)) for x, y in zip(xs, ys) if y > 0]
    if len(pts) < 2:
        return 100.0, 0.0, 0.0

    n = len(pts)
    s_x = sum(x for x, _ in pts)
    s_lny = sum(math.log(y) for _, y in pts)
    s_xx = sum(x * x for x, _ in pts)
    s_xlny = sum(x * math.log(y) for x, y in pts)

    denom = n * s_xx - s_x * s_x
    if denom == 0:
        return 100.0, 0.0, 0.0

    slope = (n * s_xlny - s_x * s_lny) / denom        # = -k
    intercept = (s_lny - slope * s_x) / n              # = ln(a)
    k = -slope
    a = math.exp(intercept)

    mean_lny = s_lny / n
    ss_tot = sum((math.log(y) - mean_lny) ** 2 for _, y in pts)
    ss_res = sum((math.log(y) - (intercept + slope * x)) ** 2 for x, y in pts)
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
    return a, max(k, 0.0), r2


def _r_squared_original_space(xs: list[float], ys: list[float], a: float, k: float) -> float:
    """在原始（非对数）空间计算 R²，更贴近用户视角的拟合优度。

    用于 train/test split 与 K-Fold CV 中的测试集评估，
    避免对数空间 R²=1.0 的误导。
    """
    if len(xs) < 2:
        return 0.0
    preds = [a * math.exp(-k * float(x)) for x in xs]
    mean_y = sum(float(y) for y in ys) / len(ys)
    ss_tot = sum((float(y) - mean_y) ** 2 for y in ys)
    if ss_tot == 0:
        # 所有 y 相同：仅当预测也都等于该值时 R²=1，否则 0
        return 1.0 if all(abs(p - mean_y) < 1e-9 for p in preds) else 0.0
    ss_res = sum((float(y) - p) ** 2 for y, p in zip(ys, preds))
    r2 = 1 - ss_res / ss_tot
    return max(-1.0, min(1.0, r2))  # 钳制到 [-1, 1]，外推场景可能为负


def _train_test_split_sorted(
    xs: list[float], ys: list[float], test_ratio: float = TEST_SIZE_RATIO
) -> tuple[list[float], list[float], list[float], list[float]] | None:
    """时序友好的 train/test 切分：按 cycle 排序后取末尾 test_ratio 作为测试集。

    循环数据天然按时间顺序排列，随机打乱会造成时间泄露，
    因此采用 forward-chaining 风格：训练集为前 80% 循环，测试集为后 20%。
    """
    pts = sorted(zip([float(x) for x in xs], [float(y) for y in ys]))
    n = len(pts)
    if n < MIN_SAMPLES_FOR_SPLIT:
        return None
    n_test = max(1, int(round(n * test_ratio)))
    if n - n_test < 2:
        n_test = max(0, n - 2)
    if n_test == 0:
        return None
    train = pts[: n - n_test]
    test = pts[n - n_test :]
    tx, ty = zip(*train)
    ex, ey = zip(*test)
    return list(tx), list(ty), list(ex), list(ey)


def _kfold_cv(xs: list[float], ys: list[float], k: int = CV_FOLDS) -> list[float] | None:
    """K-Fold 交叉验证（时序友好：连续分块），返回各 fold 的测试集 R² 列表。

    返回 None 表示样本量不足以做 K-Fold。
    """
    n = len(xs)
    if n < MIN_SAMPLES_FOR_CV or k < 2:
        return None
    pts = sorted(zip([float(x) for x in xs], [float(y) for y in ys]))
    fold_size = n // k
    if fold_size < 1:
        return None
    folds: list[list[tuple[float, float]]] = [
        pts[i * fold_size : (i + 1) * fold_size] for i in range(k - 1)
    ]
    folds.append(pts[(k - 1) * fold_size :])  # 最后一个 fold 收尾
    r2_list: list[float] = []
    for i in range(k):
        test = folds[i]
        train = [p for j, f in enumerate(folds) if j != i for p in f]
        if len(train) < 2 or len(test) == 0:
            continue
        tx, ty = zip(*train)
        a, k_fit, _ = _fit_exponential_decay(list(tx), list(ty))
        ex, ey = zip(*test)
        r2 = _r_squared_original_space(list(ex), list(ey), a, k_fit)
        r2_list.append(r2)
    return r2_list if r2_list else None


class LearnerAgent:
    """学习者 Agent：从电池循环数据库中学习材料性能衰减模式。

    基于循环数据拟合指数衰减模型 C(n) = a * exp(-k * n)，
    不调用真实 LLM，返回结构化学习结果供下游 Agent 使用。
    """

    AGENT_ID = "builtin_battery_learner"
    AGENT_NAME = "电池衰减学习者"

    def learn(self, material_formula: str, cycle_data: list) -> dict:
        """学习材料性能衰减模式，返回衰减曲线拟合参数。

        Args:
            material_formula: 材料化学式（仅用于标注，可为空）
            cycle_data: 循环数据列表，每项含 cycle 与 capacity（容量保持率，%），
                        兼容 capacity_retention 字段

        Returns:
            {
                "formula": str,
                "model_type": "exponential_decay",
                "params": {"a": float, "k": float},
                "initial_capacity": float,
                "decay_rate_per_cycle": float,
                "fit_r_squared": float,           # 对数空间 R²（全量），保留以兼容旧前端
                "sample_count": int,
                "cycle_range": [min, max],
                "fitted_curve": [{cycle, capacity}],
                "summary": str,
                # Task 17 新增字段：
                "model_version": str,             # 模型版本号
                "low_data_warning": bool,         # 训练样本 < 30
                "train_r_squared": float | None,  # 训练集 R²（原始空间，80% 数据）
                "test_r_squared": float | None,   # 测试集 R²（原始空间，20% 数据）
                "cv_r_squared_mean": float | None, # K-Fold CV R² 均值
                "cv_r_squared_std": float | None,  # K-Fold CV R² 标准差
                "cv_folds": int | None,            # CV 折数
                "overfit_warning": bool,           # 训练集-测试集 R² 差值 > 0.2
            }
        """
        formula = (material_formula or "").strip()
        points = self._extract_points(cycle_data)

        if len(points) < 2:
            return self._empty_result(formula, len(points))

        # 过滤掉容量 <= 0 的数据点（对数线性化要求 C(n) > 0）
        valid_points = [(n, c) for n, c in points if c > 0]
        if len(valid_points) < 2:
            return {"error": "有效数据点不足", "fitted": False}

        xs = [p[0] for p in valid_points]
        ys = [p[1] for p in valid_points]
        a, k, r2 = _fit_exponential_decay(xs, ys)

        # ---- Task 17 过拟合核查：训练/测试集分离 + K-Fold CV ----
        sample_count = len(points)
        low_data_warning = sample_count < LOW_DATA_THRESHOLD

        train_r2: float | None = None
        test_r2: float | None = None
        cv_mean: float | None = None
        cv_std: float | None = None
        cv_folds: int | None = None
        overfit_warning = False

        # 时序友好的 train/test split（80/20，末尾 20% 作为测试集）
        split = _train_test_split_sorted(xs, ys)
        if split is not None:
            tx, ty, ex, ey = split
            a_tr, k_tr, _ = _fit_exponential_decay(tx, ty)
            train_r2 = round(_r_squared_original_space(tx, ty, a_tr, k_tr), 4)
            test_r2 = round(_r_squared_original_space(ex, ey, a_tr, k_tr), 4)
            if train_r2 is not None and test_r2 is not None:
                gap = train_r2 - test_r2
                overfit_warning = gap > OVERFIT_GAP_THRESHOLD

        # K-Fold CV（样本量足够时）
        cv_results = _kfold_cv(xs, ys, k=CV_FOLDS)
        if cv_results is not None and len(cv_results) > 0:
            cv_mean = round(sum(cv_results) / len(cv_results), 4)
            if len(cv_results) > 1:
                mean_val = sum(cv_results) / len(cv_results)
                variance = sum((r - mean_val) ** 2 for r in cv_results) / len(cv_results)
                cv_std = round(math.sqrt(variance), 4)
            else:
                cv_std = 0.0
            cv_folds = len(cv_results)

        # 拟合曲线（在实测循环范围内均匀采样 20 点用于展示）
        cmin, cmax = min(xs), max(xs)
        fitted_curve = []
        if cmax > cmin:
            step = (cmax - cmin) / 19
            for i in range(20):
                cyc = cmin + step * i
                fitted_curve.append({
                    "cycle": round(cyc, 1),
                    "capacity": round(a * math.exp(-k * cyc), 2),
                })
        else:
            fitted_curve.append({"cycle": cmin, "capacity": round(a * math.exp(-k * cmin), 2)})

        # summary：附训练/测试 R² 与警告
        r2_summary = f"R²={r2:.4f}"
        if test_r2 is not None:
            r2_summary += f"，训练 R²={train_r2:.4f}，测试 R²={test_r2:.4f}"
        if overfit_warning:
            r2_summary += "（⚠ 训练-测试 R² 差值过大，疑似过拟合）"
        if low_data_warning:
            r2_summary += "（⚠ 样本量 < 30，预测可靠性受限）"
        if cv_std is not None and cv_std > UNSTABLE_STD_THRESHOLD:
            r2_summary += f"（⚠ CV 标准差 {cv_std:.4f} 偏大，模型不稳定）"

        return {
            "formula": formula,
            "model_type": "exponential_decay",
            "params": {"a": round(a, 4), "k": round(k, 6)},
            "initial_capacity": round(a, 2),
            "decay_rate_per_cycle": round(k, 6),
            "fit_r_squared": round(r2, 4),
            "sample_count": sample_count,
            "cycle_range": [cmin, cmax],
            "fitted_curve": fitted_curve,
            "summary": (
                f"材料 {formula or '未命名'} 拟合指数衰减模型："
                f"初始容量 {a:.2f}%，衰减率 {k:.6f}/循环，"
                f"拟合优度 {r2_summary}（样本 {sample_count}）"
            ),
            # Task 17 新增字段
            "model_version": MODEL_VERSION,
            "low_data_warning": low_data_warning,
            "train_r_squared": train_r2,
            "test_r_squared": test_r2,
            "cv_r_squared_mean": cv_mean,
            "cv_r_squared_std": cv_std,
            "cv_folds": cv_folds,
            "overfit_warning": overfit_warning,
        }

    @staticmethod
    def _extract_points(cycle_data: list) -> list[tuple[float, float]]:
        """从循环数据中提取 (cycle, capacity) 点，兼容 capacity / capacity_retention 字段。"""
        points: list[tuple[float, float]] = []
        if not cycle_data:
            return points
        for item in cycle_data:
            if not isinstance(item, dict):
                continue
            cycle = item.get("cycle")
            cap = item.get("capacity")
            if cap is None:
                cap = item.get("capacity_retention")
            if cycle is None or cap is None:
                continue
            try:
                c = float(cycle)
                v = float(cap)
            except (TypeError, ValueError):
                continue
            if c < 0:
                continue
            points.append((c, v))
        # 按循环数排序
        points.sort(key=lambda p: p[0])
        return points

    @staticmethod
    def _empty_result(formula: str, sample_count: int) -> dict:
        return {
            "formula": formula,
            "model_type": "exponential_decay",
            "params": {"a": 100.0, "k": 0.0},
            "initial_capacity": 100.0,
            "decay_rate_per_cycle": 0.0,
            "fit_r_squared": 0.0,
            "sample_count": sample_count,
            "cycle_range": [0, 0],
            "fitted_curve": [],
            "summary": f"材料 {formula or '未命名'} 循环数据不足（{sample_count} 点），无法拟合衰减模型",
            # Task 17 新增字段（数据不足时的默认值）
            "model_version": MODEL_VERSION,
            "low_data_warning": True,
            "train_r_squared": None,
            "test_r_squared": None,
            "cv_r_squared_mean": None,
            "cv_r_squared_std": None,
            "cv_folds": None,
            "overfit_warning": False,
        }


class InterpreterAgent:
    """解释者 Agent：解释学习结果，分析衰减机理。

    基于衰减率、拟合优度等规则判断主导机理
    （SEI 增长、活性物质损失、电解液分解等），
    不调用真实 LLM，返回结构化机理分析。
    """

    AGENT_ID = "builtin_battery_interpreter"
    AGENT_NAME = "电池机理解释者"

    def interpret(self, learning_result: dict) -> dict:
        """解释学习结果，返回机理分析。

        Args:
            learning_result: LearnerAgent.learn() 的返回值

        Returns:
            {
                "summary": str,
                "dominant_mechanism": str,
                "secondary_mechanisms": [str],
                "mechanisms": [{"name", "description", "confidence", "evidence"}],
                "severity": str,
                "recommendations": [str],
            }
        """
        k = float(learning_result.get("decay_rate_per_cycle", 0.0) or 0.0)
        r2 = float(learning_result.get("fit_r_squared", 0.0) or 0.0)
        sample_count = int(learning_result.get("sample_count", 0) or 0)
        formula = learning_result.get("formula", "")

        mechanisms: list[dict] = []
        secondary: list[str] = []

        # 规则 1：基于衰减率判断主导机理
        if k > 0.005:
            dominant = "活性物质损失"
            severity = "严重"
            mechanisms.append({
                "name": "活性物质损失",
                "description": (
                    f"衰减率 {k:.6f}/循环偏高，疑似活性物质结构坍塌或颗粒粉化，"
                    f"导致有效容量快速下降"
                ),
                "confidence": 0.85,
                "evidence": f"decay_rate={k:.6f} > 0.005",
            })
            secondary.extend(["SEI 增长", "电解液分解"])
        elif k > 0.001:
            dominant = "SEI 增长"
            severity = "中等"
            mechanisms.append({
                "name": "SEI 增长",
                "description": (
                    f"衰减率 {k:.6f}/循环处于中等区间，符合 SEI 膜持续生长消耗活性锂的"
                    f"典型特征"
                ),
                "confidence": 0.75,
                "evidence": f"0.001 < decay_rate={k:.6f} <= 0.005",
            })
            secondary.extend(["活性物质损失", "电解液分解"])
        else:
            dominant = "电解液分解"
            severity = "轻微"
            mechanisms.append({
                "name": "电解液分解",
                "description": (
                    f"衰减率 {k:.6f}/循环较低，衰减平缓，主要为电解液缓慢分解或"
                    f"正常老化"
                ),
                "confidence": 0.65,
                "evidence": f"decay_rate={k:.6f} <= 0.001",
            })
            secondary.extend(["SEI 增长"])

        # 规则 2：拟合优度低 → 锂枝晶/界面不稳定等非平稳因素
        if r2 < 0.85 and sample_count >= 3:
            mechanisms.append({
                "name": "界面不稳定/锂枝晶",
                "description": (
                    f"拟合优度 R²={r2:.4f} 偏低，数据偏离指数衰减，"
                    f"可能存在锂枝晶生长或界面阻抗突变等非平稳因素"
                ),
                "confidence": 0.5,
                "evidence": f"r_squared={r2:.4f} < 0.85",
            })
            if "界面不稳定/锂枝晶" not in secondary:
                secondary.append("界面不稳定/锂枝晶")

        # 规则 3：样本量提示
        recommendations: list[str] = []
        if sample_count < 5:
            recommendations.append("循环数据点较少，建议补充更多循环测试以提升机理判断可靠性")
        if severity == "严重":
            recommendations.append("衰减过快，建议检查材料结构稳定性与循环窗口设置")
        elif severity == "中等":
            recommendations.append("关注 SEI 膜稳定性，可优化电解液配方或成膜工艺")
        else:
            recommendations.append("衰减平缓，材料循环稳定性良好")
        if r2 < 0.85:
            recommendations.append("数据离散度较高，建议复核测试条件一致性与数据采集质量")
        if not recommendations:
            recommendations.append("衰减机理明确，可继续寿命预测")

        summary = (
            f"材料 {formula or '未命名'} 主导衰减机理为 {dominant}（{severity}），"
            f"衰减率 {k:.6f}/循环，拟合优度 R²={r2:.4f}"
        )

        return {
            "summary": summary,
            "dominant_mechanism": dominant,
            "secondary_mechanisms": secondary,
            "mechanisms": mechanisms,
            "severity": severity,
            "recommendations": recommendations,
        }


class OracleAgent:
    """预言者 Agent：基于学习结果预测未来循环性能。

    外推衰减曲线，预测未来循环容量保持率与循环寿命
    （容量保持率降至 80% 时的循环数，即 EOL），
    不调用真实 LLM。
    """

    AGENT_ID = "builtin_battery_oracle"
    AGENT_NAME = "电池寿命预言者"
    EOL_THRESHOLD = 80.0  # 容量保持率 80% 视为寿命终点

    def predict(self, learning_result: dict, future_cycles: int) -> dict:
        """基于学习结果预测未来循环性能。

        Args:
            learning_result: LearnerAgent.learn() 的返回值
            future_cycles: 预测到的目标循环数

        Returns:
            {
                "summary": str,
                "predicted_cycle_life": int,
                "capacity_at_future_cycles": float,
                "eol_threshold": float,
                "reaches_eol": bool,
                "prediction_curve": [{cycle, capacity}],
                "confidence": float,
                # Task 17 新增字段：
                "model_version": str,
                "confidence_interval": str,           # "0.85 ± 0.03"
                "confidence_interval_struct": {lower, upper, margin},
                "train_r_squared": float | None,
                "test_r_squared": float | None,
                "sample_count": int,
                "low_data_warning": bool,
                "overfit_warning": bool,
            }
        """
        params = learning_result.get("params", {}) or {}
        a = float(params.get("a", 100.0) or 100.0)
        k = float(params.get("k", 0.0) or 0.0)
        r2 = float(learning_result.get("fit_r_squared", 0.0) or 0.0)
        sample_count = int(learning_result.get("sample_count", 0) or 0)
        cycle_range = learning_result.get("cycle_range", [0, 0]) or [0, 0]
        formula = learning_result.get("formula", "")

        # Task 17：透传 Learner 评估指标
        train_r2 = learning_result.get("train_r_squared")
        test_r2 = learning_result.get("test_r_squared")
        cv_mean = learning_result.get("cv_r_squared_mean")
        cv_std = learning_result.get("cv_r_squared_std")
        low_data_warning = bool(learning_result.get("low_data_warning", False))
        overfit_warning = bool(learning_result.get("overfit_warning", False))

        try:
            target = max(int(future_cycles), 0)
        except (TypeError, ValueError):
            target = 0

        # 预测曲线：从实测最大循环数外推到目标循环数（采样 30 点）
        start_cycle = int(cycle_range[1]) if len(cycle_range) >= 2 else 0
        end_cycle = max(target, start_cycle)
        prediction_curve: list[dict] = []
        if end_cycle > start_cycle:
            steps = 30
            step = (end_cycle - start_cycle) / steps
            for i in range(1, steps + 1):
                cyc = start_cycle + step * i
                cap = a * math.exp(-k * cyc)
                prediction_curve.append({
                    "cycle": round(cyc, 1),
                    "capacity": round(cap, 2),
                })
        elif end_cycle == start_cycle and end_cycle > 0:
            cap = a * math.exp(-k * end_cycle)
            prediction_curve.append({
                "cycle": end_cycle,
                "capacity": round(cap, 2),
            })

        # 目标循环数处的容量保持率
        capacity_at_target = round(a * math.exp(-k * target), 2) if target > 0 else round(a, 2)

        # 循环寿命：容量保持率降至 EOL 阈值时的循环数
        # a * exp(-k * n) = threshold  =>  n = -ln(threshold / a) / k
        reaches_eol = False
        predicted_life = 0
        if k > 0 and a > self.EOL_THRESHOLD:
            n_eol = -math.log(self.EOL_THRESHOLD / a) / k
            predicted_life = int(round(n_eol))
            reaches_eol = n_eol <= target if target > 0 else True
        elif a <= self.EOL_THRESHOLD:
            # 初始容量已低于阈值
            predicted_life = 0
            reaches_eol = True
        else:
            # k == 0：无衰减，永不达到 EOL
            predicted_life = -1  # 表示在预测范围内未达到 EOL
            reaches_eol = False

        # ---- Task 17：置信度计算（封顶 0.95，不再出现 100%） ----
        # 基础 R² 优先级：测试集 R² > CV 均值 > 训练集 R²（带惩罚）
        if test_r2 is not None:
            base_r2 = float(test_r2)
        elif cv_mean is not None:
            base_r2 = float(cv_mean)
        else:
            base_r2 = r2 * 0.85  # 仅训练集 R²，惩罚 15%

        # 样本量加权
        sample_factor = min(sample_count, 30) / 30 * 0.3
        confidence = base_r2 * 0.7 + sample_factor

        # CV 标准差惩罚（不稳定时下调置信度）
        if cv_std is not None:
            confidence -= float(cv_std) * 0.5

        # 过拟合惩罚
        if overfit_warning:
            confidence -= 0.1

        # 数据不足时大幅降级
        if low_data_warning:
            confidence = min(confidence, LOW_DATA_CONFIDENCE_CAP)

        # 钳制到 [0, MAX_CONFIDENCE]，永不超过 0.95
        confidence = max(0.0, min(MAX_CONFIDENCE, confidence))

        # 置信区间：基于 CV 标准差或样本量启发式估计
        if cv_std is not None:
            margin = float(cv_std) + 0.02
        else:
            # 启发式：样本量越少，区间越宽
            margin = max(0.05, 0.15 - min(sample_count, 30) / 30 * 0.10)
        # 数据不足时进一步扩大区间
        if low_data_warning:
            margin = max(margin, 0.15)
        # 过拟合时也扩大区间
        if overfit_warning:
            margin = max(margin, 0.12)
        ci_lower = max(0.0, confidence - margin)
        ci_upper = min(MAX_CONFIDENCE, confidence + margin)
        confidence_interval_str = f"{confidence:.3f} ± {margin:.3f}"

        life_text = (
            f"约 {predicted_life} 循环" if predicted_life > 0
            else ("已达寿命终点" if reaches_eol else "预测范围内未达到寿命终点")
        )
        summary = (
            f"材料 {formula or '未命名'} 预测 {target} 循环时容量保持率 {capacity_at_target}%，"
            f"循环寿命（80% 阈值）{life_text}，"
            f"预测置信度 {confidence:.0%}（区间 {ci_lower:.0%}~{ci_upper:.0%}，"
            f"模型 v{MODEL_VERSION}）"
        )

        return {
            "summary": summary,
            "predicted_cycle_life": predicted_life,
            "capacity_at_future_cycles": capacity_at_target,
            "eol_threshold": self.EOL_THRESHOLD,
            "reaches_eol": reaches_eol,
            "prediction_curve": prediction_curve,
            "confidence": round(confidence, 3),
            # Task 17 新增字段
            "model_version": MODEL_VERSION,
            "confidence_interval": confidence_interval_str,
            "confidence_interval_struct": {
                "lower": round(ci_lower, 3),
                "upper": round(ci_upper, 3),
                "margin": round(margin, 3),
            },
            "train_r_squared": train_r2,
            "test_r_squared": test_r2,
            "sample_count": sample_count,
            "low_data_warning": low_data_warning,
            "overfit_warning": overfit_warning,
        }
