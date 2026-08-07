"""CoE Audit「证据链完整性」评分器。

依据 Science One「可验证性作为一等架构约束」方法论，对委员会已产出的声明做
**事后反向审计**，核对证据链各环节是否完整：

- 声明→证据：案件是否至少关联一条证据（证据落库）。
- 证据真实：success 证据占比（非 success 证据不支撑决策）。
- 方法对齐：证据是否记录 capability / source_name（方法可追溯）。
- 引用可查：证据是否携带 provenance / run_id（底层运行可核验）。
- 来源层级：证据 source_type 是否合法（trust tier 可区分）。
- 声明核验：证据 verification 状态（ClaimVerifier 是否放行）。

评分器为纯函数：输入一批「已审计案件」dict，输出聚合指标。每个案件 dict 建议形如：

    {
        "case_id": str,
        "evidence_count": int,
        "success_count": int,
        "method_aligned_count": int,
        "citation_traceable_count": int,
        "source_tier_valid_count": int,
        "verified_count": int,
    }
"""

from __future__ import annotations

from typing import Any


def _safe_div(num: float, den: float) -> float:
    return num / den if den else 0.0


class CoeAuditScorer:
    """计算证据链完整性聚合指标。"""

    def score_case(self, case: dict) -> dict:
        """对单个案件的证据链各维度打分（0.0-1.0），容忍缺失字段。"""
        evidence_count = int(case.get("evidence_count", 0) or 0)
        return {
            "case_id": case.get("case_id", ""),
            "evidence_recorded": evidence_count > 0,
            "evidence_success_rate": _safe_div(
                int(case.get("success_count", 0) or 0), evidence_count
            ),
            "method_alignment_rate": _safe_div(
                int(case.get("method_aligned_count", 0) or 0), evidence_count
            ),
            "citation_traceability": _safe_div(
                int(case.get("citation_traceable_count", 0) or 0), evidence_count
            ),
            "source_tier_validity": _safe_div(
                int(case.get("source_tier_valid_count", 0) or 0), evidence_count
            ),
            "claim_verification_rate": _safe_div(
                int(case.get("verified_count", 0) or 0), evidence_count
            ),
        }

    def score_all(self, cases: list[dict]) -> dict:
        """聚合多案件的证据链完整性指标。"""
        if not cases:
            return {
                "case_count": 0,
                "evidence_coverage": 0.0,
                "evidence_success_rate": 0.0,
                "method_alignment_rate": 0.0,
                "citation_traceability": 0.0,
                "source_tier_validity": 0.0,
                "claim_verification_rate": 0.0,
                "integrity_score": 0.0,
            }

        scored = [self.score_case(c) for c in cases]
        total_evidence = sum(int(c.get("evidence_count", 0) or 0) for c in cases)

        def _avg(key: str) -> float:
            return sum(s[key] for s in scored) / len(scored)

        covered = sum(1 for s in scored if s["evidence_recorded"])
        success_den = sum(1 for c, s in zip(cases, scored) if int(c.get("evidence_count", 0) or 0) > 0)
        verified_evidence = sum(int(c.get("verified_count", 0) or 0) for c in cases)

        evidence_coverage = _safe_div(covered, len(cases))
        evidence_success_rate = _safe_div(
            sum(s["evidence_success_rate"] for c, s in zip(cases, scored) if int(c.get("evidence_count", 0) or 0) > 0),
            success_den,
        )

        # 完整性总分：evidence_coverage 0.3 + 其余五维均值 0.7
        chain_avg = (
            _avg("evidence_success_rate")
            + _avg("method_alignment_rate")
            + _avg("citation_traceability")
            + _avg("source_tier_validity")
            + _avg("claim_verification_rate")
        ) / 5
        integrity_score = evidence_coverage * 0.3 + chain_avg * 0.7

        return {
            "case_count": len(cases),
            "evidence_count": total_evidence,
            "evidence_coverage": evidence_coverage,
            "evidence_success_rate": evidence_success_rate,
            "method_alignment_rate": _avg("method_alignment_rate"),
            "citation_traceability": _avg("citation_traceability"),
            "source_tier_validity": _avg("source_tier_validity"),
            "claim_verification_rate": _safe_div(verified_evidence, total_evidence),
            "integrity_score": integrity_score,
        }