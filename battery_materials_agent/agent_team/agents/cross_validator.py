"""Cross-validation agent for anomaly analysis (template-based, no LLM)."""
from __future__ import annotations


class CrossValidationAgent:
    """交叉验证 Agent：对预测偏差异常样本进行模板化原因分析。

    分析逻辑基于偏差幅度、属性类型等规则生成可能原因，
    不调用真实 LLM，返回结构化原因列表供前端展示。
    """

    AGENT_ID = "builtin_cross_validator"
    AGENT_NAME = "交叉验证分析员"

    # 属性 → 典型原因映射（模板化）
    _PROPERTY_HINTS = {
        "ionic_conductivity": "离子电导率对温度、界面阻抗敏感",
        "discharge_capacity": "放电容量受活性物质利用率与循环衰减影响",
        "coulombic_efficiency": "库仑效率受副反应与 SEI 成膜影响",
        "capacity_retention": "容量保持率反映循环稳定性与材料降解",
        "internal_resistance": "内阻受界面接触与电解质浸润影响",
        "open_circuit_voltage": "开路电压反映热力学平衡状态",
    }

    def analyze(self, anomalies: list[dict]) -> dict:
        """分析异常样本，返回结构化原因列表。

        Args:
            anomalies: 异常样本列表，每项含 result_id / property_name /
                       predicted / measured / deviation_pct 等字段

        Returns:
            {
                "summary": str,
                "anomaly_count": int,
                "max_deviation_pct": float,
                "avg_deviation_pct": float,
                "causes": [{"cause", "description", "confidence"}],
                "recommendations": [str],
            }
        """
        if not anomalies:
            return {
                "summary": "无异常样本需要分析",
                "anomaly_count": 0,
                "max_deviation_pct": 0.0,
                "avg_deviation_pct": 0.0,
                "causes": [],
                "recommendations": [],
            }

        deviations = [float(a.get("deviation_pct", 0.0)) for a in anomalies]
        max_dev = max(deviations)
        avg_dev = sum(deviations) / len(deviations)
        property_names = {a.get("property_name", "") for a in anomalies}

        causes: list[dict] = []
        recommendations: list[str] = []

        # 规则 1：极大偏差 → 测量误差
        if max_dev > 50.0:
            causes.append({
                "cause": "测量误差",
                "description": f"最大偏差达 {max_dev:.1f}%，疑似仪器校准异常或操作失误",
                "confidence": 0.8,
            })
            recommendations.append("复核仪器校准状态与原始测试数据")

        # 规则 2：中等偏差 → 模型外推
        if avg_dev > 20.0:
            causes.append({
                "cause": "模型外推",
                "description": f"平均偏差 {avg_dev:.1f}%，预测模型可能处于训练数据分布之外",
                "confidence": 0.6,
            })
            recommendations.append("补充该区间的训练样本以提升模型适用性")

        # 规则 3：多属性同时偏差 → 材料降解
        if len(property_names) > 1:
            causes.append({
                "cause": "材料降解",
                "description": f"多个属性（{', '.join(sorted(p for p in property_names if p))}）同时偏离，可能与材料降解或副反应有关",
                "confidence": 0.5,
            })
            recommendations.append("检查样品存储条件与测试前预处理流程")

        # 规则 4：属性相关提示
        for prop in property_names:
            hint = self._PROPERTY_HINTS.get(prop)
            if hint:
                causes.append({
                    "cause": "属性特性",
                    "description": f"{prop}：{hint}",
                    "confidence": 0.4,
                })
                break  # 只取一条属性提示，避免冗余

        # 规则 5：默认兜底
        if not causes:
            causes.append({
                "cause": "未知因素",
                "description": f"偏差 {avg_dev:.1f}% 超过阈值，原因待进一步排查",
                "confidence": 0.3,
            })

        if not recommendations:
            recommendations.append("结合实验条件与历史数据进一步排查偏差来源")

        return {
            "summary": f"共分析 {len(anomalies)} 个异常样本，最大偏差 {max_dev:.1f}%，平均偏差 {avg_dev:.1f}%",
            "anomaly_count": len(anomalies),
            "max_deviation_pct": round(max_dev, 2),
            "avg_deviation_pct": round(avg_dev, 2),
            "causes": causes,
            "recommendations": recommendations,
        }

    def format_analysis(self, analysis: dict) -> str:
        """将结构化分析结果格式化为可存储的简短文本。"""
        if not analysis.get("causes"):
            return ""
        parts = [analysis.get("summary", "")]
        for c in analysis["causes"]:
            parts.append(f"{c['cause']}({c['confidence']:.0%}): {c['description']}")
        return " | ".join(parts)
