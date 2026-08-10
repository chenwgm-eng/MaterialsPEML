"""Capability Router — 根据任务能力需求、执行策略、权限、健康、预算和风险，返回候选工具路由。

路由器组合 AliasRegistry（语义别名 → binding 映射）、EligibilityStore（agent/profile
约束）、ToolCatalog（本地工具健康与风险）、SCPCatalog（SCP binding 启用状态与风险）
与 ProviderRegistry（外部 provider 健康）来产出按 RouteScore 排序的候选列表。

评分公式：
    RouteScore = w_q*Q + w_r*R + w_h*H - w_c*C - w_l*L - w_s*S

默认权重（v1）：
    quality=0.3, relevance=0.2, health(reliability)=0.3,
    cost=0.1, latency=0.05, risk=0.05
"""
from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# SCPCatalog.RiskLevel → 风险分数：A=最低风险（可自动调用），D=最高风险（禁止）
_SCP_RISK_SCORE: dict[str, float] = {"A": 0.1, "B": 0.3, "C": 0.6, "D": 0.9}

# ToolCatalog.ToolRiskLevel → 风险分数：A=最高风险（DFT 提交），D=最低风险（本地查询）
# 注意：ToolCatalog 与 SCPCatalog 的 RiskLevel 字母含义相反。
_LOCAL_RISK_SCORE: dict[str, float] = {"A": 0.9, "B": 0.6, "C": 0.3, "D": 0.1}

# ToolEligibilityRule.max_risk_level → 允许的最大风险分数（A=最安全，D=最危险）
# 候选的 risk_score 超过此阈值的将被过滤
_MAX_RISK_SCORE: dict[str, float] = {"A": 0.1, "B": 0.3, "C": 0.6, "D": 0.9}

# ProviderHealth / ToolHealthStatus → 可靠性分数
_HEALTH_RELIABILITY: dict[str, float] = {
    "healthy": 1.0,
    "degraded": 0.4,
    "unhealthy": 0.0,
    "unknown": 0.7,
}

# SCP provider 在 ProviderRegistry 中的统一 provider_id
_SCP_PROVIDER_ID = "scp_server"


class RouteCandidate(BaseModel):
    """工具路由候选。"""

    binding_id: str                    # binding 标识，如 local:generate_polymer_candidates 或 scp:scp_scitool_chem
    source: Literal["local", "scp"]    # 来源
    alias: str                         # 语义别名
    quality_score: float = 0.0         # 质量/可信度分数 0-1
    relevance_score: float = 0.0       # 与任务的相关性 0-1
    expected_cost: float = 0.0         # 预期成本（token/调用费）
    reliability_score: float = 1.0     # 可靠性 0-1（基于健康和历史成功率）
    risk_score: float = 0.0            # 风险 0-1
    fallback_binding_id: str = ""      # 回退 binding
    reason: str = ""                   # 选择原因
    requires_human_review: bool = False  # 是否需要人工审核（来自 eligibility rule）
    capability_id: str = ""            # 关联的契约 ID（用于门禁）
    contract_status: str = ""          # 契约状态：active/pending_approval/deprecated/unknown
    degraded: bool = False             # 是否走了 fallback 链
    fallback_from: str = ""            # 降级来源：原 capability_id（仅 degraded=True 时有值）


class RouteDecision(BaseModel):
    """路由决策记录。"""

    alias: str
    profile: str
    selected_candidate: str            # 选中的 binding_id
    skipped_candidates: list[str] = Field(default_factory=list)
    reason_code: str = ""              # 原因码：local_preferred/scp_health_degraded/budget_exceeded/risk_too_high
    policy_version: str = "v1"


class CapabilityRouter:
    """能力路由器 — 为每个能力需求返回候选工具列表。

    路由逻辑：
    1. 从 AliasRegistry 获取别名对应的 binding 列表
    2. 从 EligibilityStore 获取该能力的资格规则（agent/profile 约束）
    3. 从 ToolCatalog/SCPCatalog 检查工具健康状态和风险等级
    4. 按 standard/internlm_assisted/committee_governed 策略过滤
    5. 评分排序：RouteScore = w_q*Q + w_r*R + w_h*H - w_c*C - w_l*L - w_s*S

    契约门禁（当 capability_registry 注入时生效）：
    6. 根据 alias 查对应契约的 status；deprecated/pending_high_risk 的候选被过滤
    7. 主能力不可调用时，自动解析 fallback_chain 找可调用的替代契约
    """

    # alias → 主契约 capability_id 映射（用于运行时门禁）
    # 未列出的 alias 视为"无契约约束"，向后兼容不强制门禁
    _ALIAS_TO_CAPABILITY_ID: dict[str, str] = {
        "property_prediction": "crystal_property_prediction_v1",
        "dft_verification": "dft_verification_v1",
        "chemical_descriptors": "polymer_candidate_generation_v1",
    }

    def __init__(
        self,
        alias_registry,
        eligibility_store,
        tool_catalog=None,
        scp_catalog=None,
        provider_registry=None,
        capability_registry=None,
    ):
        self._alias_registry = alias_registry
        self._eligibility_store = eligibility_store
        self._tool_catalog = tool_catalog
        self._scp_catalog = scp_catalog
        self._provider_registry = provider_registry
        # 契约注册表（可选）：注入后启用运行时门禁与自动 fallback
        self._capability_registry = capability_registry
        # 路由权重（可由版本化 routing_policy 配置）
        self._weights: dict[str, float] = {
            "quality": 0.3,
            "relevance": 0.2,
            "health": 0.3,
            "cost": 0.1,
            "latency": 0.05,
            "risk": 0.05,
        }
        self._policy_version = "v1"

    def tool_to_alias(self, tool_name: str) -> str:
        """本地 MCP 工具名 → 语义别名（反向映射）。

        编排执行器以 MCP 工具名调用路由门禁，而 Router 按语义别名解析；
        未出现在任何别名 local_binding 中的工具视为无契约约束（放行）。
        """
        for alias in self._alias_registry.list_all():
            if alias.local_binding == tool_name:
                return alias.alias
        return ""

    async def resolve(
        self,
        capability: str,
        profile: str,
        context=None,
        agent_id: str = "*",
    ) -> list[RouteCandidate]:
        """解析能力到候选 binding 列表。

        Args:
            capability: 能力名，如 chemical_descriptors
            profile: ExecutionProfile 值
            context: ExecutionContext（可选，用于权限和预算检查）
            agent_id: 请求 Agent 的 ID（默认通配符）

        Returns:
            按 RouteScore 降序排列的候选列表，已过滤超风险候选并按 preferred_binding_order 重排。
            若主能力契约不可调用且 fallback 链可用，返回的候选会标记 degraded=True。
            若主能力与整条 fallback 链都不可调用，返回空列表（调用方应拒绝）。
        """
        alias = self._alias_registry.get(capability)
        if alias is None:
            return []

        # ── 契约门禁：检查主能力契约状态，必要时走 fallback 链 ──
        primary_capability_id = self._ALIAS_TO_CAPABILITY_ID.get(capability, "")
        degraded_from = ""
        if self._capability_registry is not None and primary_capability_id:
            ok, reason = self._capability_registry.is_callable(primary_capability_id)
            if not ok:
                # 主能力不可调用，尝试 fallback 链
                fallback_id, fb_reason = self._capability_registry.find_callable_fallback(
                    primary_capability_id
                )
                if fallback_id is None:
                    logger.warning(
                        "CapabilityRouter.resolve(%s) blocked: contract %s is %s, "
                        "no callable fallback in chain",
                        capability, primary_capability_id, reason,
                    )
                    return []
                # 找到可调用 fallback：标记降级
                degraded_from = primary_capability_id
                # 如果 fallback 契约对应另一个 alias，递归 resolve 该 alias
                fallback_alias = self._capability_id_to_alias(fallback_id)
                if fallback_alias and fallback_alias != capability:
                    logger.info(
                        "CapabilityRouter.resolve(%s) degraded: fallback to alias %s "
                        "(contract %s)",
                        capability, fallback_alias, fallback_id,
                    )
                    fb_candidates = await self._resolve_alias(
                        fallback_alias, profile, context, agent_id,
                        capability_id=fallback_id,
                        degraded_from=degraded_from,
                    )
                    return fb_candidates
                # fallback 契约没有对应 alias：用原 alias 的 binding，但标记降级
                logger.info(
                    "CapabilityRouter.resolve(%s) degraded: contract %s -> %s (no alias switch)",
                    capability, primary_capability_id, fallback_id,
                )

        # ── 正常解析主 alias 的 binding ──
        return await self._resolve_alias(
            capability, profile, context, agent_id,
            capability_id=primary_capability_id,
            degraded_from=degraded_from,
        )

    async def _resolve_alias(
        self,
        capability: str,
        profile: str,
        context,
        agent_id: str,
        capability_id: str = "",
        degraded_from: str = "",
    ) -> list[RouteCandidate]:
        """解析单个 alias 到候选 binding 列表（内部方法）。

        Args:
            capability: alias 名称
            capability_id: 关联的契约 ID（用于填充候选的 capability_id 字段）
            degraded_from: 若为降级执行，原 capability_id；否则空字符串
        """
        alias = self._alias_registry.get(capability)
        if alias is None:
            return []

        # 检查 profile 是否在该 alias 允许的 profile 列表中
        profile_allowed = profile in alias.allowed_profiles
        # standard 策略：只返回 local binding（不返回 SCP）
        scp_allowed = profile != "standard" and profile_allowed

        # 从 EligibilityStore 获取该 capability 的规则（按 agent_id 过滤）
        all_rules = self._eligibility_store.list_by_capability(capability, profile)
        # 优先取 agent 专属规则，没有则用通配规则
        rules = [r for r in all_rules if r.agent_id == agent_id]
        if not rules:
            rules = [r for r in all_rules if r.agent_id == "*"]
        rule = rules[0] if rules else None

        # 契约状态（若注入了 capability_registry）
        contract_status = "unknown"
        if self._capability_registry is not None and capability_id:
            status_risk = self._capability_registry.get_status(capability_id)
            if status_risk is not None:
                contract_status = status_risk[0]

        candidates: list[RouteCandidate] = []
        skipped: list[str] = []

        # 1. 本地 binding —— standard 与 assisted/committee 均可使用
        if alias.local_binding:
            candidates.append(
                RouteCandidate(
                    binding_id=f"local:{alias.local_binding}",
                    source="local",
                    alias=capability,
                    quality_score=0.9,
                    relevance_score=1.0,
                    expected_cost=0.0,
                    reliability_score=self._local_reliability(alias.local_binding),
                    risk_score=self._local_risk_score(alias.local_binding),
                    fallback_binding_id=alias.fallback_binding,
                    reason="local_binding_preferred",
                    capability_id=capability_id,
                    contract_status=contract_status,
                    degraded=bool(degraded_from),
                    fallback_from=degraded_from,
                )
            )

        # 2. SCP binding —— 仅当 profile 允许且非 standard
        if scp_allowed and alias.scp_binding:
            scp_binding_id = f"scp:{alias.scp_binding}"
            if not self._scp_binding_enabled(alias.scp_binding):
                skipped.append(scp_binding_id)
                logger.debug("SCP binding %s disabled, skipped", scp_binding_id)
            elif not self._scp_provider_healthy():
                skipped.append(scp_binding_id)
                logger.debug(
                    "SCP provider unhealthy, skipped %s", scp_binding_id
                )
            else:
                scp_candidate = self._build_scp_candidate(
                    capability, alias.scp_binding, scp_binding_id, alias.fallback_binding,
                    capability_id=capability_id,
                    contract_status=contract_status,
                    degraded_from=degraded_from,
                )
                if scp_candidate is not None:
                    candidates.append(scp_candidate)

        # 3. 应用 eligibility 规则：过滤超风险候选
        if rule is not None:
            max_risk_score = _MAX_RISK_SCORE.get(rule.max_risk_level, 0.6)
            before = len(candidates)
            candidates = [c for c in candidates if c.risk_score <= max_risk_score]
            if len(candidates) < before:
                logger.info(
                    "CapabilityRouter.resolve(%s, %s) filtered %d candidates by max_risk_level=%s",
                    capability, profile, before - len(candidates), rule.max_risk_level,
                )
            # 标记 requires_human_review
            if rule.requires_human_review:
                for c in candidates:
                    c.requires_human_review = True

        # 4. 按 preferred_binding_order 重排（优先级 > 评分）
        if rule is not None and rule.preferred_binding_order:
            candidates = self._reorder_by_preferred(candidates, rule.preferred_binding_order)
        else:
            candidates.sort(key=self._score_candidate, reverse=True)

        if skipped:
            logger.info(
                "CapabilityRouter.resolve(%s, %s) skipped: %s",
                capability,
                profile,
                skipped,
            )
        return candidates

    @classmethod
    def _capability_id_to_alias(cls, capability_id: str) -> str:
        """反向映射：capability_id → alias（若存在）。"""
        for alias, cid in cls._ALIAS_TO_CAPABILITY_ID.items():
            if cid == capability_id:
                return alias
        return ""

    def _reorder_by_preferred(
        self, candidates: list[RouteCandidate], preferred_order: list[str]
    ) -> list[RouteCandidate]:
        """按 preferred_binding_order 重排候选。

        在 preferred_order 中的候选按其顺序排前，不在的按评分降序排后。
        """
        order_map = {bid: idx for idx, bid in enumerate(preferred_order)}
        in_order = [c for c in candidates if c.binding_id in order_map]
        out_order = [c for c in candidates if c.binding_id not in order_map]
        in_order.sort(key=lambda c: order_map[c.binding_id])
        out_order.sort(key=self._score_candidate, reverse=True)
        return in_order + out_order

    # ── 评分 ──────────────────────────────────────────────

    def _score_candidate(self, candidate: RouteCandidate) -> float:
        """计算候选的路由评分。"""
        w = self._weights
        return (
            w["quality"] * candidate.quality_score
            + w["relevance"] * candidate.relevance_score
            + w["health"] * candidate.reliability_score
            - w["cost"] * candidate.expected_cost
            - w["latency"] * 0.0  # 简化：暂不计算延迟
            - w["risk"] * candidate.risk_score
        )

    # ── 配置 ──────────────────────────────────────────────

    def set_weights(self, weights: dict) -> None:
        """更新路由权重（部分更新，仅覆盖传入的键）。"""
        for key, value in weights.items():
            if key in self._weights:
                self._weights[key] = value

    def set_policy_version(self, version: str) -> None:
        """设置策略版本标识。"""
        self._policy_version = version

    @property
    def policy_version(self) -> str:
        return self._policy_version

    @property
    def weights(self) -> dict[str, float]:
        return dict(self._weights)

    # ── 帮助方法 ──────────────────────────────────────────

    def _local_reliability(self, tool_name: str) -> float:
        """从 ToolCatalog 获取本地工具可靠性分数。

        未注入 ToolCatalog 或工具未注册时返回本地默认 0.95（本地工具可靠）。
        """
        if self._tool_catalog is None:
            return 0.95
        desc = self._tool_catalog.get(tool_name)
        if desc is None:
            return 0.95
        return _HEALTH_RELIABILITY.get(desc.health_status.value, 0.95)

    def _local_risk_score(self, tool_name: str) -> float:
        """从 ToolCatalog 获取本地工具风险分数。

        ToolCatalog.ToolRiskLevel: A=最高风险，D=最低风险。
        """
        if self._tool_catalog is None:
            return 0.1
        desc = self._tool_catalog.get(tool_name)
        if desc is None:
            return 0.1
        return _LOCAL_RISK_SCORE.get(desc.risk_level.value, 0.1)

    def _scp_binding_enabled(self, scp_binding_name: str) -> bool:
        """检查 SCPCatalog 中 binding 是否启用。

        未注入 SCPCatalog 时乐观允许（外部组件应保证已启用）；
        binding 未注册时返回 False（避免路由到未知 SCP）。
        """
        if self._scp_catalog is None:
            return True
        binding = self._scp_catalog.get(scp_binding_name)
        if binding is None:
            return False
        return binding.enabled

    def _scp_provider_healthy(self) -> bool:
        """检查 SCP provider 是否健康。

        所有 SCP binding 走统一的 'scp_server' provider。
        未注入 ProviderRegistry 或 provider 不存在时乐观允许；
        health_status 为 DEGRADED/UNHEALTHY 时视为不健康。
        """
        if self._provider_registry is None:
            return True
        provider = self._provider_registry.get(_SCP_PROVIDER_ID)
        if provider is None:
            return True
        return provider.health_status.value not in ("degraded", "unhealthy")

    def _build_scp_candidate(
        self,
        capability: str,
        scp_binding_name: str,
        scp_binding_id: str,
        fallback_binding: str,
        capability_id: str = "",
        contract_status: str = "",
        degraded_from: str = "",
    ) -> RouteCandidate | None:
        """构造 SCP 路由候选。"""
        risk_score = 0.3
        reliability = 0.8  # SCP 默认中等可靠性
        reason = "scp_supplementary"

        # 从 SCPCatalog 获取风险等级
        if self._scp_catalog is not None:
            binding = self._scp_catalog.get(scp_binding_name)
            if binding is not None:
                risk_score = _SCP_RISK_SCORE.get(binding.risk_level.value, 0.3)
                reason = f"scp_binding_risk_{binding.risk_level.value}"

        # 从 ProviderRegistry 获取健康状态影响可靠性
        if self._provider_registry is not None:
            provider = self._provider_registry.get(_SCP_PROVIDER_ID)
            if provider is not None:
                reliability = _HEALTH_RELIABILITY.get(
                    provider.health_status.value, 0.8
                )

        return RouteCandidate(
            binding_id=scp_binding_id,
            source="scp",
            alias=capability,
            quality_score=0.7,
            relevance_score=0.8,
            expected_cost=0.1,
            reliability_score=reliability,
            risk_score=risk_score,
            fallback_binding_id=fallback_binding,
            reason=reason,
            capability_id=capability_id,
            contract_status=contract_status,
            degraded=bool(degraded_from),
            fallback_from=degraded_from,
        )
