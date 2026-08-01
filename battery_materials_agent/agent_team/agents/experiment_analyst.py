"""Experiment analyst agent for statistical analysis of QC-passed results (template-based, no LLM)."""
from __future__ import annotations

import statistics
from typing import Any


class ExperimentAnalystAgent:
    """实验数据分析 Agent：对 QC 通过的实验结果进行模板化统计分析。

    分析逻辑基于均值、标准差、趋势比较等统计规则，
    不调用真实 LLM，返回结构化分析结果供前端展示。
    """

    AGENT_ID = "builtin_experiment_analyst"
    AGENT_NAME = "实验数据分析员"

    def analyze(self, records: list[Any]) -> dict:
        """分析 QC 通过的实验结果记录列表，返回结构化统计简报。

        Args:
            records: ExperimentResultRecord 列表（或 dict），
                     应包含 property_name / value / unit / uploaded_at / qc_status 等字段

        Returns:
            {
                "summary": str,
                "statistics": {mean, std, min, max, sample_count, trend, property_name},
                "anomalies": [{result_id, property_name, value, deviation, reason}],
                "recommendations": [str],
            }
        """
        # 仅保留 QC 通过的记录
        valid = [r for r in records if self._get(r, "qc_status") in ("VALID", "VALID_WITH_WARNING")]
        if not valid:
            return self._empty_result("无 QC 通过的实验结果，暂无法分析")

        # 按 property_name 分组
        groups: dict[str, list] = {}
        for r in valid:
            prop = self._get(r, "property_name") or "unknown"
            groups.setdefault(prop, []).append(r)

        # 取样本数最多的属性作为主分析对象
        main_prop = max(groups.keys(), key=lambda p: len(groups[p]))
        main_records = groups[main_prop]

        values = [float(self._get(r, "value")) for r in main_records if self._get(r, "value") is not None]
        if not values:
            return self._empty_result(f"属性 {main_prop} 无有效数值")

        stats = self._compute_statistics(values, main_records, main_prop)
        anomalies = self._detect_anomalies(main_records, values, stats)
        recommendations = self._generate_recommendations(stats, anomalies)
        summary = self._build_summary(stats, anomalies, main_prop, len(valid), len(groups))

        # 次要属性摘要（非主分析对象的其他属性样本数）
        secondary_properties = {p: len(recs) for p, recs in groups.items() if p != main_prop}

        return {
            "summary": summary,
            "statistics": stats,
            "anomalies": anomalies,
            "recommendations": recommendations,
            "secondary_properties": secondary_properties,
        }

    def _compute_statistics(self, values: list[float], records: list, prop: str) -> dict:
        mean = statistics.mean(values)
        std = statistics.pstdev(values) if len(values) > 1 else 0.0
        trend = self._determine_trend(records, mean)
        return {
            "mean": round(mean, 4),
            "std": round(std, 4),
            "min": round(min(values), 4),
            "max": round(max(values), 4),
            "sample_count": len(values),
            "trend": trend,
            "property_name": prop,
        }

    def _determine_trend(self, records: list, mean: float) -> str:
        """比较最近一条记录与整体均值，判断趋势。"""
        sorted_recs = sorted(records, key=lambda r: self._get(r, "uploaded_at") or "")
        if len(sorted_recs) < 2 or mean == 0:
            return "稳定"
        latest_val = float(self._get(sorted_recs[-1], "value"))
        deviation = (latest_val - mean) / abs(mean)
        if deviation > 0.05:
            return "上升"
        if deviation < -0.05:
            return "下降"
        return "稳定"

    def _detect_anomalies(self, records: list, values: list[float], stats: dict) -> list[dict]:
        """识别偏离 2 倍标准差的异常点。"""
        mean = stats["mean"]
        std = stats["std"]
        if std == 0:
            return []
        threshold = 2 * std
        anomalies: list[dict] = []
        for r, v in zip(records, values):
            deviation = abs(v - mean)
            if deviation > threshold:
                anomalies.append({
                    "result_id": self._get(r, "result_id"),
                    "property_name": stats["property_name"],
                    "value": round(v, 4),
                    "deviation": round(deviation, 4),
                    "reason": f"偏离均值 {deviation:.4f}（超过 2 倍标准差 {threshold:.4f}）",
                })
        return anomalies

    def _generate_recommendations(self, stats: dict, anomalies: list) -> list[str]:
        recs: list[str] = []
        if stats["sample_count"] < 3:
            recs.append("样本量较少，建议增加实验次数以提升统计可靠性")
        if anomalies:
            recs.append(f"检测到 {len(anomalies)} 个异常点，建议复核实验条件与仪器状态")
        cv = stats["std"] / stats["mean"] if stats["mean"] != 0 else 0
        if cv > 0.2:
            recs.append("数据离散度较高（变异系数 > 20%），建议检查实验一致性")
        if not recs:
            recs.append("数据一致性良好，可继续后续分析")
        return recs

    def _build_summary(self, stats: dict, anomalies: list, prop: str,
                       total_count: int, group_count: int) -> str:
        parts = [
            f"共分析 {total_count} 条 QC 通过记录",
            f"主属性 {prop}：均值 {stats['mean']}，标准差 {stats['std']}，样本数 {stats['sample_count']}",
            f"趋势：{stats['trend']}",
        ]
        if group_count > 1:
            parts.append(f"共 {group_count} 个属性，主分析对象为 {prop}")
        if anomalies:
            parts.append(f"检测到 {len(anomalies)} 个异常点")
        return "；".join(parts)

    def _empty_result(self, summary: str) -> dict:
        return {
            "summary": summary,
            "statistics": {
                "mean": 0.0, "std": 0.0, "min": 0.0, "max": 0.0,
                "sample_count": 0, "trend": "稳定", "property_name": "",
            },
            "anomalies": [],
            "recommendations": [],
        }

    @staticmethod
    def _get(obj: Any, field: str):
        """从 model 对象或 dict 中取字段，兼容 ExperimentResultRecord 与 dict。"""
        if hasattr(obj, field):
            return getattr(obj, field)
        if isinstance(obj, dict):
            return obj.get(field)
        return None

    def format_analysis(self, analysis: dict) -> str:
        """将结构化分析结果格式化为可存储的简短文本。"""
        stats = analysis.get("statistics") or {}
        if stats.get("sample_count", 0) == 0:
            return analysis.get("summary", "")
        parts = [
            analysis.get("summary", ""),
            f"均值 {stats['mean']}，标准差 {stats['std']}",
        ]
        return " | ".join(p for p in parts if p)
