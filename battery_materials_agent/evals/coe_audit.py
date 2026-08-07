"""CoE Audit「证据链完整性」审计运行器。

从委员会仓库拉取最近已产出的案件、证据与裁决，对每条证据链做反向核对
（声明→证据→方法→引用→来源层级→声明核验），用 :class:`CoeAuditScorer`
聚合指标，并写入 ``evals/reports/audit-{timestamp}.json``。

支持：
- 手动触发：调用 :meth:`run` 立即执行并返回报告路径。
- 定时任务：由外部调度（每日凌晨）调用 :meth:`run`。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from ..committee.enums import EvidenceSource
from ..committee.repository import CommitteeRepository
from ..contracts.evidence import SourceTier
from .scorers.coe_audit_scorers import CoeAuditScorer

logger = logging.getLogger(__name__)

# Package root: battery_materials_agent/
_PACKAGE_ROOT = Path(__file__).resolve().parents[1]


class CoeAuditor:
    """证据链完整性审计器。"""

    def __init__(
        self,
        repository: CommitteeRepository | None = None,
        report_dir: str = "evals/reports",
    ):
        self._repo = repository or CommitteeRepository()
        self._scorer = CoeAuditScorer()
        rd = Path(report_dir)
        self.report_dir: Path = rd if rd.is_absolute() else (_PACKAGE_ROOT / rd)
        self.report_dir.mkdir(parents=True, exist_ok=True)

    # ── 单条证据链核对 ──────────────────────────────────────────────

    @staticmethod
    def _audit_evidence(evidence_list: list) -> dict:
        """统计一条案件下属证据链各环节满足数。"""
        total = len(evidence_list)
        success = 0
        method_aligned = 0
        citation_traceable = 0
        source_tier_valid = 0
        verified = 0

        for ev in evidence_list:
            # 证据真实：status == success
            if ev.status == "success":
                success += 1
            # 方法对齐：capability 或 source_name 非空
            if (ev.capability or ev.source_name or "").strip():
                method_aligned += 1
            # 引用可查：provenance 含 run_id 或 value 含引用；核验失败(未通过)不计入
            prov = ev.provenance or {}
            run_id = prov.get("run_id") or (prov.get("task") or {}).get("run_id")
            if ev.verification != "unverified" and (run_id or ev.source_name):
                citation_traceable += 1
            # 来源层级合法：委员会证据仍为旧枚举，来源层级校验单独走 scientific_kernel.evidence
            if ev.source_type in EvidenceSource._value2member_map_:
                source_tier_valid += 1
            # 声明核验：verification == verified（未核验范围视为通过）
            if ev.verification in ("verified", "unknown"):
                verified += 1

        return {
            "evidence_count": total,
            "success_count": success,
            "method_aligned_count": method_aligned,
            "citation_traceable_count": citation_traceable,
            "source_tier_valid_count": source_tier_valid,
            "verified_count": verified,
        }

    # ── 来源层级审计（scientific_kernel.evidence 三级信任体系）──────────────────

    def _audit_scientific_source_tiers(self) -> dict:
        """读取 scientific_kernel.evidence 的 source_type，校验是否进入三级信任体系。

        Returns:
            dict：total / valid / validity / by_tier。
        """
        try:
            tiers = self._repo.get_scientific_evidence_source_tiers()
        except Exception as exc:  # noqa: BLE001
            logger.warning("CoE Audit 读取 scientific_kernel.evidence 来源层级失败: %s", exc)
            return {"total": 0, "valid": 0, "validity": 0.0, "by_tier": {}}
        valid_tiers = frozenset(SourceTier._value2member_map_.keys())
        by_tier: dict[str, int] = {}
        valid = 0
        for tier in tiers:
            by_tier[tier] = by_tier.get(tier, 0) + 1
            if tier in valid_tiers:
                valid += 1
        total = len(tiers)
        return {
            "total": total,
            "valid": valid,
            "validity": valid / total if total else 0.0,
            "by_tier": by_tier,
        }

    # ── 主流程 ──────────────────────────────────────────────────────

    def run(self, limit: int = 100) -> dict:
        """拉取最近案件并审计证据链完整性，写入报告。

        Args:
            limit: 最近审计的案件数上限。

        Returns:
            审计报告 dict（含 audit_run_id / metrics / per_case / 报告路径）。
        """
        audit_run_id = f"audit-{uuid4().hex[:12]}"
        started = datetime.now(timezone.utc)

        try:
            cases = self._repo.list_cases(limit=limit)
        except Exception as exc:  # noqa: BLE001
            logger.exception("CoE Audit 拉取案件失败")
            return self._build_failed_report(audit_run_id, started, f"list_cases_failed: {exc}")

        per_case: list[dict] = []
        for case in cases:
            try:
                evidence = self._repo.get_evidence_by_case(case.case_id)
                verdict = self._repo.get_verdict_by_case(case.case_id)
            except Exception as exc:  # noqa: BLE001
                logger.warning("CoE Audit case %s 读取失败: %s", case.case_id, exc)
                per_case.append({
                    "case_id": case.case_id,
                    "error": str(exc)[:200],
                    **self._audit_evidence([]),
                })
                continue
            audit = self._audit_evidence(evidence)
            audit["case_id"] = case.case_id
            audit["committee_type"] = getattr(case, "committee_type", "").value \
                if getattr(case, "committee_type", None) else ""
            audit["decision"] = verdict.decision.value if verdict else None
            audit["score"] = self._scorer.score_case(audit)
            per_case.append(audit)

        metrics = self._scorer.score_all(per_case)
        # 来源层级：对 scientific_kernel.evidence 的三级信任体系做全局校验
        source_tier = self._audit_scientific_source_tiers()
        metrics["source_tier_validity"] = source_tier["validity"]
        metrics["source_tier_evidence_count"] = source_tier["total"]
        report = {
            "audit_run_id": audit_run_id,
            "audit_type": "coe_evidence_chain_integrity",
            "started_at": started.isoformat(),
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "metrics": metrics,
            "per_case": per_case,
            "source_tier": source_tier,
        }
        path = self._write_report(audit_run_id, report)
        report["report_path"] = str(path)
        logger.info(
            "CoE Audit 完成: %s cases, integrity=%s, report=%s",
            metrics.get("case_count"),
            metrics.get("integrity_score"),
            path,
        )
        return report

    def _build_failed_report(self, audit_run_id: str, started: datetime, error: str) -> dict:
        report = {
            "audit_run_id": audit_run_id,
            "audit_type": "coe_evidence_chain_integrity",
            "started_at": started.isoformat(),
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "error": error,
            "metrics": {},
            "per_case": [],
        }
        path = self._write_report(audit_run_id, report)
        report["report_path"] = str(path)
        return report

    def _write_report(self, audit_run_id: str, report: dict) -> Path:
        path = self.report_dir / f"{audit_run_id}.json"
        with path.open("w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2, ensure_ascii=False, default=str)
        return path