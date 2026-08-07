"""声明核验器（ClaimVerifier）— 在 CommitteeVerifier 评分前对 success 证据做真实性核验。

依据 Science One「可验证性作为一等架构约束」方法论：委员会打分卡此前完整采信
EvidenceItem.score，无独立核验。本模块在评分前核验携带 run_id 的证据其底层运行记录
是否真实存在并按预期完成。

判定规则：
- 证据 status != "success"：不适用核验（applicable=False）。
- 证据未携带 run_id（本地工具 / LLM 生成 / 无运行记录）：不适用核验，原样保留。
- 证据携带 run_id：
  - run 记录存在 且 status=succeeded 且 有 artifact 落库 → verified=True
  - 否则 → verified=False，reason 记录具体失败原因（run 不存在 / 未完成 / 无 artifact）
"""

from __future__ import annotations

from dataclasses import dataclass

from ..contracts.run import RunStatus
from ..domain.runtime.execution_kernel import ScientificExecutionKernel
from .models import EvidenceItem

# 未通过核验时证据可信度降级值（low）
UNVERIFIED_CONFIDENCE = 0.3


@dataclass
class ClaimVerification:
    """单条证据的核验结果。"""

    evidence_id: str
    verified: bool
    reason: str = ""
    # applicable=False 表示该证据不属于核验范围（非 success 或无 run_id），不降级
    applicable: bool = True


class ClaimVerifier:
    """核验 success 证据的 run 记录真实性。"""

    def __init__(self, kernel: ScientificExecutionKernel | None = None):
        self.kernel = kernel

    def extract_run_id(self, item: EvidenceItem) -> str:
        """从证据 provenance 中提取 run_id（支持直接字段或 task 内嵌）。"""
        provenance = item.provenance or {}
        run_id = provenance.get("run_id") or ""
        if not run_id:
            task = provenance.get("task") or {}
            run_id = task.get("run_id") or ""
        return run_id

    def verify_item(self, item: EvidenceItem) -> ClaimVerification:
        """核验单条证据，返回核验结果（不修改证据本体）。"""
        if item.status != "success":
            return ClaimVerification(item.evidence_id, verified=True, applicable=False, reason="not_success")

        run_id = self.extract_run_id(item)
        if not run_id:
            # 无 run_id 即无底层运行记录可核验，视为不适用而非失败
            return ClaimVerification(item.evidence_id, verified=True, applicable=False, reason="missing_run_id")

        if self.kernel is None:
            return ClaimVerification(item.evidence_id, verified=False, reason="no_verifier_kernel")

        run = self.kernel.get_run(run_id)
        if run is None:
            return ClaimVerification(item.evidence_id, verified=False, reason=f"run_not_found:{run_id}")

        if run.status != RunStatus.SUCCEEDED:
            return ClaimVerification(
                item.evidence_id,
                verified=False,
                reason=f"run_not_completed:{run.status.value}",
            )

        artifacts = self.kernel.get_artifacts(run_id)
        if not artifacts:
            return ClaimVerification(item.evidence_id, verified=False, reason="artifact_missing")

        return ClaimVerification(item.evidence_id, verified=True, reason="ok")

    def verify(self, evidence: list[EvidenceItem]) -> list[ClaimVerification]:
        """批量核验，返回与输入等长的核验结果列表。"""
        return [self.verify_item(item) for item in evidence]

    def apply(self, evidence: list[EvidenceItem]) -> list[ClaimVerification]:
        """核验并就地标记证据：不通过者置 verification='unverified'、降级可信度，
        并将核验详情写入 provenance。返回核验结果列表。"""
        checks = self.verify(evidence)
        for item, check in zip(evidence, checks):
            if not check.applicable:
                continue
            if check.verified:
                continue
            item.verification = "unverified"
            item.confidence = UNVERIFIED_CONFIDENCE
            prov = dict(item.provenance or {})
            prov["claim_verifier"] = {"verified": False, "reason": check.reason}
            item.provenance = prov
        return checks