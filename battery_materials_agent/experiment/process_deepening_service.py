"""工艺深化编排服务（Phase B 第二层：工艺深化阶段）。

针对初筛通过（feasible → process_planning）的候选配方，由工艺人员主导做详细的
合成路径规划，产出可执行的工艺方案（ProcessScheme）。

高级能力（合成路径规划、DFT 可行性验证、反应机理）接入策略：**SCP 优先 + 本地回退**。
- 优先调用对应能力的 SCP（远端科学服务，如 SciToolAgent-Chem / SciToolAgent-Mat）；
- SCP 不可用 / 未启用 / 调用失败时，回退到本地科学服务（SynthesisPlanner / DFTVerifier）。

每次能力调用都会写入 ProcessScheme.evidence_refs（能力来源可追溯），
满足"所有业务环节使用 Agent/能力须显式展示来源"的透明性要求。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from ..synthesis.synthesis_planner import SynthesisPlanner
from .candidate_store import CandidateStore, CandidateRecord
from .process_scheme_store import ProcessScheme, ProcessSchemeStore, ProcessSchemeStatus

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ProcessDeepeningService:
    """工艺深化编排服务。

    Args:
        process_scheme_store: 工艺方案存储（读写 ProcessScheme）。
        candidate_store: 候选材料存储（读取候选配方）。
        synthesis_planner: 本地逆合成规划器（SCP 回退目标）。
        scp_client_pool: SCP 客户端池（可选，未启用时自动走本地）。
        scp_catalog: SCP 工具绑定目录（可选，用于解析 SCP 能力绑定）。
        dft_verifier: 本地 DFT 验证器（可选，SCP 回退目标）。
    """

    def __init__(
        self,
        process_scheme_store: ProcessSchemeStore,
        candidate_store: CandidateStore,
        synthesis_planner: SynthesisPlanner | None = None,
        scp_client_pool: Any | None = None,
        scp_catalog: Any | None = None,
        dft_verifier: Any | None = None,
    ):
        self.process_scheme_store = process_scheme_store
        self.candidate_store = candidate_store
        self.synthesis_planner = synthesis_planner or SynthesisPlanner()
        self.scp_client_pool = scp_client_pool
        self.scp_catalog = scp_catalog
        self.dft_verifier = dft_verifier

    # ── 对外入口 ───────────────────────────────────────────

    async def deepen(
        self,
        candidate_id: str,
        owner: str = "",
        triggered_by: str = "user",
        max_routes: int = 5,
        max_depth: int = 3,
        process_id: str = "",
    ) -> ProcessScheme:
        """对候选配方执行工艺深化，产出/更新工艺方案。

        Args:
            candidate_id: 候选材料 ID。
            owner: 工艺人员用户名（写入 scheme.owner）。
            triggered_by: 触发主体标识。
            max_routes: 规划的最大候选路线数。
            max_depth: 逆合成搜索深度。
            process_id: 若提供，在既有工艺方案上深化；否则新建。

        Returns:
            更新后的工艺方案（含 routes / evidence_refs）。
        """
        record = self.candidate_store.get(candidate_id)
        if record is None:
            raise ValueError(f"候选材料 {candidate_id} 不存在")
        smiles = (record.smiles or "").strip()
        if not smiles:
            raise ValueError(f"候选材料 {candidate_id} 缺少 SMILES，无法进行合成路径深化")

        # 1) 取出既有方案（或准备新建）
        scheme = self._load_or_create_scheme(record, process_id)

        # 2) 合成路径规划（SCP 优先 + 本地回退）
        routes_bundle = await self._plan_routes(smiles, max_routes, max_depth)
        scheme.routes = routes_bundle["routes"]
        scheme.evidence_refs.extend(routes_bundle["evidence_refs"])

        # 3) 对每条路线做 DFT 可行性校验（SCP 优先 + 本地回退）
        dft_bundle = await self._verify_dft_batch(routes_bundle["routes"])
        scheme.evidence_refs.extend(dft_bundle)

        # 4) 落库：状态保持 draft（工艺人员在深化中），记录责任人
        scheme.owner = owner or scheme.owner or record.assigned_role
        scheme.updated_at = _now()
        if scheme.process_id:
            self.process_scheme_store.update(scheme)
        else:
            self.process_scheme_store.create(scheme)
        return scheme

    # ── 内部：方案装载 ─────────────────────────────────────

    def _load_or_create_scheme(self, record: CandidateRecord, process_id: str) -> ProcessScheme:
        if process_id:
            existing = self.process_scheme_store.get(process_id)
            if existing is None:
                raise ValueError(f"工艺方案 {process_id} 不存在")
            return existing
        # 已有该候选方案则复用，否则新建
        existing_list = self.process_scheme_store.list_by_candidate(record.candidate_id)
        active = [s for s in existing_list if s.status == ProcessSchemeStatus.DRAFT.value]
        if active:
            return active[0]
        return ProcessScheme(
            candidate_id=record.candidate_id,
            status=ProcessSchemeStatus.DRAFT.value,
            created_by=record.owner or "",
            steps=[],
        )

    # ── 内部：能力编排（SCP 优先 + 本地回退） ───────────────

    async def _plan_routes(self, smiles: str, max_routes: int, max_depth: int) -> dict[str, Any]:
        """合成路径规划：SCP 优先，失败回退本地 SynthesisPlanner。"""
        evidence_refs: list[dict[str, Any]] = []

        scp_result = await self._call_scp_capability(
            capability="synthesis_planning",
            preferred_binding="scp_scitool_chem",
            fallback_bindings=("scp_chem_reaction",),
            arguments={"smiles": smiles, "max_routes": max_routes, "max_depth": max_depth},
            evidence_refs=evidence_refs,
        )
        if scp_result is not None:
            routes = self._normalize_scp_routes(scp_result, smiles)
            if routes:
                return {"routes": routes, "evidence_refs": evidence_refs}

        # 本地回退
        logger.info("工艺深化：合成路径规划回退本地 SynthesisPlanner smiles=%s", smiles)
        try:
            local_routes = await self.synthesis_planner.plan_synthesis_async(
                smiles, max_depth=max_depth, num_routes=max_routes,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("工艺深化：本地逆合成失败 %s", e)
            evidence_refs.append({
                "capability": "synthesis_planning",
                "source": "local",
                "status": "failed",
                "detail": f"本地逆合成失败: {e}",
                "at": _now(),
            })
            return {"routes": [], "evidence_refs": evidence_refs}

        routes = [r.model_dump() for r in local_routes]
        evidence_refs.append({
            "capability": "synthesis_planning",
            "source": "local",
            "provider": "SynthesisPlanner",
            "tool": "askcos/internlm",
            "status": "success",
            "detail": f"本地逆合成生成 {len(routes)} 条路线",
            "at": _now(),
        })
        return {"routes": routes, "evidence_refs": evidence_refs}

    async def _verify_dft_batch(self, routes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """对每条路线做 DFT 可行性校验并回写 confidence。"""
        evidence_refs: list[dict[str, Any]] = []
        for route in routes:
            dft = await self._verify_dft_single(route)
            if dft is not None:
                route["dft"] = dft
                evidence_refs.append({
                    "capability": "dft_verification",
                    "source": dft.get("source", "local"),
                    "provider": dft.get("provider", ""),
                    "tool": dft.get("method", ""),
                    "status": "success",
                    "route_id": route.get("route_id", ""),
                    "overall_status": dft.get("overall_status", ""),
                    "detail": f"置信度 {dft.get('original_confidence')} → {dft.get('adjusted_confidence')}",
                    "at": _now(),
                })
        return evidence_refs

    async def _verify_dft_single(self, route: dict[str, Any]) -> dict[str, Any] | None:
        """单条路线 DFT 校验：SCP 优先，失败回退本地。"""
        temp_refs: list[dict[str, Any]] = []
        scp_result = await self._call_scp_capability(
            capability="dft_verification",
            preferred_binding="scp_scitool_mat",
            fallback_bindings=(),
            arguments={"route": route},
            evidence_refs=temp_refs,
        )
        if scp_result is not None and scp_result.get("overall_status"):
            scp_result["source"] = "scp"
            return scp_result

        # 本地回退
        try:
            result = await self.synthesis_planner.verify_with_dft(route)
            result["source"] = "local"
            result["provider"] = "SynthesisPlanner"
            result["method"] = result.get("method", "template-based DFT estimate")
            return result
        except Exception as e:  # noqa: BLE001
            logger.warning("工艺深化：本地 DFT 校验失败 %s", e)
            return None

    # ── 内部：SCP 能力调用 ─────────────────────────────────

    async def _call_scp_capability(
        self,
        capability: str,
        preferred_binding: str,
        fallback_bindings: tuple[str, ...],
        arguments: dict[str, Any],
        evidence_refs: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        """尝试通过 SCP 调用能力；成功返回结果 dict，失败返回 None 并记录来源。"""
        if self.scp_client_pool is None or self.scp_catalog is None:
            return None
        for binding_name in (preferred_binding,) + fallback_bindings:
            binding = self.scp_catalog.get(binding_name)
            if binding is None or not binding.enabled or not binding.server_id:
                continue
            try:
                raw = await self.scp_client_pool.call_tool(
                    binding.server_id,
                    binding.remote_tool_name or "",
                    arguments,
                    server_url=binding.server_url or None,
                )
            except Exception as e:  # noqa: BLE001
                logger.warning("工艺深化：SCP %s/%s 调用异常 %s", binding_name, capability, e)
                evidence_refs.append({
                    "capability": capability,
                    "source": "scp",
                    "provider": binding.provider or "",
                    "tool": binding_name,
                    "status": "failed",
                    "detail": f"SCP 调用异常: {e}",
                    "at": _now(),
                })
                continue
            if raw.get("status") == "success" and raw.get("data"):
                evidence_refs.append({
                    "capability": capability,
                    "source": "scp",
                    "provider": binding.provider or "",
                    "tool": binding_name,
                    "status": "success",
                    "detail": f"SCP {binding_name} 调用成功",
                    "at": _now(),
                })
                return raw.get("data")
            evidence_refs.append({
                "capability": capability,
                "source": "scp",
                "provider": binding.provider or "",
                "tool": binding_name,
                "status": "failed",
                "detail": raw.get("error") or raw.get("message") or "SCP 调用失败",
                "at": _now(),
            })
        return None

    @staticmethod
    def _normalize_scp_routes(scp_data: Any, target_smiles: str) -> list[dict[str, Any]]:
        """将 SCP 返回的路线结果归一化为统一 routes 结构。

        兼容多种返回形态：{routes:[...]} / {result:{routes:[...]}} / [{steps:...}]。
        无法解析时返回空列表（由调用方决定是否回退）。
        """
        if isinstance(scp_data, dict):
            inner = (
                scp_data.get("routes")
                or (scp_data.get("result") or {}).get("routes")
                or scp_data.get("data", {}).get("routes")
                or []
            )
        elif isinstance(scp_data, list):
            inner = scp_data
        else:
            inner = []
        routes: list[dict[str, Any]] = []
        for idx, r in enumerate(inner[:10]):
            if not isinstance(r, dict):
                continue
            routes.append({
                "route_id": r.get("route_id") or f"R{idx + 1}",
                "target_smiles": r.get("target_smiles") or target_smiles,
                "steps": r.get("steps") or [],
                "confidence": float(r.get("confidence") or r.get("score") or 0.5),
                "feasibility_score": float(r.get("feasibility_score") or 0.5),
                "is_feasible": bool(r.get("is_feasible", True)),
                "step_count": len(r.get("steps") or []),
                "estimated_cost": r.get("estimated_cost") or 0,
            })
        return routes