"""Compliance and cost checker for industrialization formulation BOMs."""

from __future__ import annotations
from pydantic import BaseModel, Field
import asyncio
import logging
from typing import TYPE_CHECKING

from .raw_material_db import RawMaterialDB

if TYPE_CHECKING:
    from ..llm.base import LLMProvider
    from ..mcp_tools.scp_client import SCPClientPool
    from ..mcp_tools.tools import MCPToolRegistry

logger = logging.getLogger(__name__)


class ComplianceReport(BaseModel):
    is_passed: bool = True
    estimated_unit_cost: float = 0.0  # 0727b：估算单位成本（货币+单位由上下文决定）
    warnings: list[str] = Field(default_factory=list)
    fatal_errors: list[str] = Field(default_factory=list)
    external_assessments: list[dict] = Field(default_factory=list)
    evidence_conflicts: list[dict] = Field(default_factory=list)
    review_required: bool = False
    # Audit invocation_ids emitted by SCP/InternLM calls during this report's
    # construction. Callers (e.g. ECML engine) append these to
    # ECMLState.external_invocation_ids to close the audit chain.
    external_invocation_ids: list[str] = Field(default_factory=list)


class ComplianceAndCostNode:
    def __init__(self, raw_material_db: RawMaterialDB, config=None,
                 llm_provider: "LLMProvider | None" = None,
                 scp_client_pool: "SCPClientPool | None" = None,
                 mcp_tool_registry: "MCPToolRegistry | None" = None):
        self.db = raw_material_db
        self._llm_provider = llm_provider
        self._scp_client_pool = scp_client_pool
        # Prefer the MCP tool registry as the entry point for SCP calls so that
        # SCPToolProxy → SCPPolicy.authorize → SCPAdapter → SCPClientPool →
        # ProvenanceDecorator → AuditStore chain is enforced. Direct
        # scp_client_pool.call_tool() bypasses policy and must only be used as
        # a legacy fallback when no registry is wired.
        self._mcp_tool_registry = mcp_tool_registry
        # 从 config 读取，如果 config 为 None 使用默认值
        self.cost_threshold = 500.0
        self.blacklist_smarts = ["[N+](=O)[O-]", "P(=S)(F)(F)F"]
        self._scp_enabled = False
        if config is not None:
            self.cost_threshold = config.cost_threshold
            self.blacklist_smarts = config.blacklist_smarts
            self._scp_enabled = getattr(config, "scp", None) is not None and getattr(config.scp, "enabled", False)

    def evaluate(self, formula_bom: dict) -> ComplianceReport:
        """Synchronous wrapper: runs the async evaluate_async in a safe manner."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.evaluate_async(formula_bom))
        # Running in an event loop, use a fallback that skips SCP
        return self._evaluate_sync(formula_bom)

    async def evaluate_async(self, formula_bom: dict) -> ComplianceReport:
        """Fixed-order compliance check:
        1. SMARTS hard block
        2. REACH/regulations
        3. SCP toxicity (if enabled)
        4. Cost estimation
        5. Evidence summary
        """
        warnings: list[str] = []
        fatal_errors: list[str] = []
        external_assessments: list[dict] = []
        evidence_conflicts: list[dict] = []
        total_cost = 0.0

        # RDKit 可用性检测（一次性，避免循环内重复导入）
        rdkit_available = False
        try:
            from rdkit import Chem  # noqa: F811
            rdkit_available = True
        except ImportError:
            pass

        # 容错：如果 BOM 值 > 1，视为百分比，自动归一化为比率
        bom_items = list(formula_bom.items())
        values = [v for _, v in bom_items if isinstance(v, (int, float))]
        if values and max(values) > 1.0:
            total_pct = sum(values)
            bom_items = [(k, v / total_pct if total_pct > 0 else 0) for k, v in bom_items]

        # Phase 1: SMARTS hard block (must NOT be overridden by SCP)
        smart_blocks: list[str] = []
        for mat_id, weight_ratio in bom_items:
            spec = self._lookup_material(mat_id)
            if spec is None:
                fatal_errors.append(f"物料 {mat_id} 不存在于物料库中")
                continue
            if rdkit_available and spec.smiles:
                mol = Chem.MolFromSmiles(spec.smiles)
                if mol is not None:
                    for smarts_pattern in self.blacklist_smarts:
                        pattern = Chem.MolFromSmarts(smarts_pattern)
                        if pattern and mol.HasSubstructMatch(pattern):
                            block_msg = f"物料 {spec.name} 含有禁用结构：{smarts_pattern}"
                            fatal_errors.append(block_msg)
                            smart_blocks.append(block_msg)

        # Phase 2: REACH/regulations
        # Task 13：声明 reach_compliant 的物料必须关联检测报告凭证（COA/SDS/第三方报告），
        # 否则视为"待补充证据"，不可作为合规依据。
        for mat_id, weight_ratio in bom_items:
            spec = self._lookup_material(mat_id)
            if spec is None:
                continue
            if not spec.reach_compliant:
                fatal_errors.append(f"物料 {spec.name} 不符合 REACH 标准。")
            elif not RawMaterialDB._has_evidence(spec):
                warnings.append(
                    f"物料 {spec.name} 声明 REACH 合规但未关联检测报告凭证（COA/SDS/第三方报告），"
                    f"状态为'待补充证据'，需上传报告后方可作为合规依据。"
                )

        # Phase 3: SCP toxicity (if enabled) — must NOT override SMARTS hard blocks
        scp_toxicity_results = await self._check_scp_toxicity(bom_items, smart_blocks)
        scp_invocation_ids: list[str] = []
        for item in scp_toxicity_results:
            material_name = item.get("material_name", "")
            risk_level = item.get("risk_level", "unknown")
            # Collect audit invocation_id from the SCP result (if the proxy
            # surfaced one) so the caller can close the audit chain in ECMLState.
            inv_id = item.get("invocation_id")
            if inv_id:
                scp_invocation_ids.append(inv_id)
            if risk_level == "high":
                conflict = {
                    "material": material_name,
                    "source": "scp_toxicity",
                    "finding": item.get("findings", {}),
                    "note": "SCP 毒性评估为高风险，但 SMARTS 硬阻断优先",
                }
                evidence_conflicts.append(conflict)
                # SCP result must NOT override SMARTS hard blocks
                if not any(material_name in block for block in smart_blocks):
                    fatal_errors.append(f"物料 {material_name} SCP 毒性评估为高风险。")
            elif risk_level == "medium":
                warnings.append(f"物料 {material_name} SCP 毒性评估为中风险，建议额外审查。")
            elif risk_level == "unknown":
                # SCP timeout/unavailable → mark as unknown, NOT as safe
                warnings.append(f"物料 {material_name} SCP 毒性评估不可用（未知风险），需人工复核。")
                external_assessments.append({
                    "material": material_name,
                    "source": "scp_toxicity",
                    "status": "unknown",
                    "reason": item.get("reason", "SCP 服务不可用或超时"),
                })
            external_assessments.append({
                "material": material_name,
                "source": "scp_toxicity",
                "risk_level": risk_level,
                "provenance": item.get("provenance"),
            })

        # Phase 4: Local toxicity (EHS) and cost estimation
        # Task 19：有毒物料（is_toxic）强制触发人工审批标记 review_required，
        # 阻断自动上量/投产，需人工复核 EHS 防护后方可放行。
        has_toxic = False
        for mat_id, weight_ratio in bom_items:
            spec = self._lookup_material(mat_id)
            if spec is None:
                continue
            total_cost += spec.unit_cost * weight_ratio
            if spec.is_toxic:
                has_toxic = True
                warnings.append(f"物料 {spec.name} 具有毒性，需升级 EHS 防护等级，且必须人工审批。")

        if total_cost > self.cost_threshold:
            fatal_errors.append(f"配方成本熔断：估算成本 {total_cost:.2f} 元/kg，远超商业警戒线。")

        # Phase 5: Evidence summary
        # Task 19：含毒性物料同样强制进入人工审批（review_required=True）
        review_required = (
            has_toxic
            or bool(evidence_conflicts)
            or any(a.get("status") == "unknown" for a in external_assessments)
        )

        return ComplianceReport(
            is_passed=len(fatal_errors) == 0,
            estimated_unit_cost=total_cost,
            warnings=warnings,
            fatal_errors=fatal_errors,
            external_assessments=external_assessments,
            evidence_conflicts=evidence_conflicts,
            review_required=review_required,
            external_invocation_ids=scp_invocation_ids,
        )

    def _evaluate_sync(self, formula_bom: dict) -> ComplianceReport:
        """Synchronous fallback that skips SCP async calls."""
        import asyncio
        warnings: list[str] = []
        fatal_errors: list[str] = []
        total_cost = 0.0

        rdkit_available = False
        try:
            from rdkit import Chem
            rdkit_available = True
        except ImportError:
            pass

        bom_items = list(formula_bom.items())
        values = [v for _, v in bom_items if isinstance(v, (int, float))]
        if values and max(values) > 1.0:
            total_pct = sum(values)
            bom_items = [(k, v / total_pct if total_pct > 0 else 0) for k, v in bom_items]

        # Task 19：含毒性物料强制进入人工审批（review_required=True）
        has_toxic = False
        for mat_id, weight_ratio in bom_items:
            spec = self._lookup_material(mat_id)
            if spec is None:
                fatal_errors.append(f"物料 {mat_id} 不存在于物料库中")
                continue
            total_cost += spec.unit_cost * weight_ratio
            if not spec.reach_compliant:
                fatal_errors.append(f"物料 {spec.name} 不符合 REACH 标准。")
            elif not RawMaterialDB._has_evidence(spec):
                warnings.append(
                    f"物料 {spec.name} 声明 REACH 合规但未关联检测报告凭证，"
                    f"状态为'待补充证据'，需上传报告后方可作为合规依据。"
                )
            if spec.is_toxic:
                has_toxic = True
                warnings.append(f"物料 {spec.name} 具有毒性，需升级 EHS 防护等级，且必须人工审批。")
            if rdkit_available and spec.smiles:
                mol = Chem.MolFromSmiles(spec.smiles)
                if mol is not None:
                    for smarts_pattern in self.blacklist_smarts:
                        pattern = Chem.MolFromSmarts(smarts_pattern)
                        if pattern and mol.HasSubstructMatch(pattern):
                            fatal_errors.append(f"物料 {spec.name} 含有禁用结构：{smarts_pattern}")

        if total_cost > self.cost_threshold:
            fatal_errors.append(f"配方成本熔断：估算成本 {total_cost:.2f} 元/kg，远超商业警戒线。")

        return ComplianceReport(
            is_passed=len(fatal_errors) == 0,
            estimated_unit_cost=total_cost,
            warnings=warnings,
            fatal_errors=fatal_errors,
            review_required=has_toxic,
        )

    async def _check_scp_toxicity(self, bom_items: list, smart_blocks: list[str]) -> list[dict]:
        """Query SCP toxicity assessment for materials in BOM.

        Routes through MCPToolRegistry so that SCPToolProxy enforces
        SCPPolicy.authorize → SCPAdapter.validate_and_map_input →
        SCPClientPool.call_tool → normalize_output → provenance → audit.
        Falls back to direct scp_client_pool.call_tool() only when no registry
        is wired (legacy path; emits a warning).
        """
        if not self._scp_enabled:
            return []
        if self._mcp_tool_registry is None and self._scp_client_pool is None:
            return []

        if self._mcp_tool_registry is not None:
            return await self._check_scp_toxicity_via_registry(bom_items)
        # Legacy fallback (no policy enforcement)
        logger.warning(
            "ComplianceAndCostNode calling SCP without MCPToolRegistry — "
            "SCPPolicy/SCPAdapter chain is bypassed. Wire mcp_tool_registry "
            "to enable the full security chain."
        )
        return await self._check_scp_toxicity_via_client_pool(bom_items)

    async def _check_scp_toxicity_via_registry(self, bom_items: list) -> list[dict]:
        """Invoke scp_toxicity_assessment through MCPToolRegistry (secure path)."""
        results = []
        for mat_id, weight_ratio in bom_items:
            spec = self._lookup_material(mat_id)
            if spec is None or not spec.smiles:
                continue
            try:
                # Arguments include both tool input and policy metadata (underscore-prefixed).
                # SCPToolProxy pops the metadata before delegating to the adapter.
                args = {
                    "smiles": spec.smiles,
                    "endpoints": ["all"],
                    "_user_role": "researcher",
                    "_ecml_step": "compliance_check",
                }
                scp_result = await self._mcp_tool_registry.execute_async(
                    "scp_toxicity_assessment", args
                )
                if not isinstance(scp_result, dict):
                    scp_result = {"status": "error", "message": f"unexpected return type: {type(scp_result)}"}

                status = scp_result.get("status", "unknown")
                provenance_list = scp_result.get("provenance") or []
                provenance = provenance_list[0] if provenance_list else {
                    "source_type": "scp",
                    "provider": "scp",
                    "model_or_tool": "toxicity_v1",
                    "evidence_level": "auxiliary",
                }

                if status == "success":
                    risk_level = scp_result.get("risk_level", "unknown")
                    findings = {k: v for k, v in scp_result.items()
                                if k not in {"status", "provenance", "risk_level", "invocation_id"}}
                    results.append({
                        "material_name": spec.name,
                        "risk_level": risk_level,
                        "findings": findings,
                        "provenance": provenance,
                        "invocation_id": scp_result.get("invocation_id"),
                    })
                elif status == "blocked":
                    # Policy denied the call; surface as unknown (do NOT treat as safe).
                    results.append({
                        "material_name": spec.name,
                        "risk_level": "unknown",
                        "reason": scp_result.get("message", "SCP 调用被策略拒绝"),
                        "provenance": provenance,
                        "invocation_id": scp_result.get("invocation_id"),
                    })
                else:
                    results.append({
                        "material_name": spec.name,
                        "risk_level": "unknown",
                        "reason": scp_result.get("message") or scp_result.get("error", "SCP 服务不可用"),
                        "provenance": provenance,
                        "invocation_id": scp_result.get("invocation_id"),
                    })
            except Exception as e:
                logger.warning("SCP toxicity check failed for %s: %s", spec.name, e)
                results.append({
                    "material_name": spec.name,
                    "risk_level": "unknown",
                    "reason": f"SCP 调用异常: {e}",
                })
        return results

    async def _check_scp_toxicity_via_client_pool(self, bom_items: list) -> list[dict]:
        """Legacy direct-call path. Retained for callers that have not migrated
        to MCPToolRegistry. Bypasses SCPPolicy and SCPAdapter.

        注意：直接调用 client_pool 需要使用 catalog 中配置的真实 server_id 和
        remote_tool_name。scp_toxicity_assessment 绑定到 server_id=31、
        remote_tool_name=SMILESToWeight（参见 scp_catalog.py）。
        """
        results = []
        for mat_id, weight_ratio in bom_items:
            spec = self._lookup_material(mat_id)
            if spec is None or not spec.smiles:
                continue
            try:
                # 使用 catalog 中 scp_toxicity_assessment 绑定的真实 server_id 与远端工具名
                scp_result = await self._scp_client_pool.call_tool(
                    server_id="31",
                    tool_name="SMILESToWeight",
                    arguments={"smiles": spec.smiles},
                    server_url="https://scp.intern-ai.org.cn/api/v1/mcp/31/SciToolAgent-Chem",
                )
                provenance = {
                    "source_type": "scp",
                    "provider": "scp",
                    "model_or_tool": "SMILESToWeight",
                    "evidence_level": "auxiliary",
                    "duration_ms": scp_result.get("latency_ms", 0),
                }
                if scp_result.get("status") == "success":
                    data = scp_result.get("data", {})
                    results.append({
                        "material_name": spec.name,
                        "risk_level": data.get("risk_level", "unknown"),
                        "findings": data,
                        "provenance": provenance,
                    })
                else:
                    results.append({
                        "material_name": spec.name,
                        "risk_level": "unknown",
                        "reason": scp_result.get("error", "SCP 服务不可用"),
                        "provenance": provenance,
                    })
            except Exception as e:
                logger.warning("SCP toxicity check failed for %s: %s", spec.name, e)
                results.append({
                    "material_name": spec.name,
                    "risk_level": "unknown",
                    "reason": f"SCP 调用异常: {e}",
                })
        return results

    def _lookup_material(self, mat_id: str):
        """容错查找：先按 material_id 查，再从 key 中提取 RM-xxx 模式，最后按名称查。"""
        import re
        spec = self.db.get_spec(mat_id)
        if spec is not None:
            return spec
        # 尝试从 key 中提取 RM-xxx 格式的物料编码
        m = re.search(r'(RM-\w+)', mat_id)
        if m:
            spec = self.db.get_spec(m.group(1))
            if spec is not None:
                return spec
        # 尝试按名称匹配
        for s in self.db.get_all():
            if s.name in mat_id or mat_id in s.name:
                return s
        return None
