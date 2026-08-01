"""Model Router — 根据能力与策略选择 LLM 路由。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class ModelRoute(BaseModel):
    """模型路由定义。"""

    route_id: str
    capability: str                    # 能力名，如 molecule_design
    profile: str                       # ExecutionProfile 值
    provider_id: str                   # ProviderRegistry 中的 provider_id，如 internlm
    model_id: str                      # 模型标识，如 intern-s2-preview-397b
    prompt_template_version: str = "v1"
    max_tokens: int = 4096
    temperature: float = 0.7
    requires_structured_output: bool = True
    fallback_route_id: str | None = None
    allowed_data_classification: list[str] = Field(
        default_factory=lambda: ["internal", "public"]
    )


class ModelRouter:
    """根据能力与执行策略选择 LLM 路由。

    standard 策略不调用 LLM；
    internlm_assisted 使用 Intern-S2；
    committee_governed 使用 Intern-S2 + 可选独立 verifier。
    """

    def __init__(self):
        self._routes: dict[str, ModelRoute] = {}
        self._init_default_routes()

    def _init_default_routes(self) -> None:
        """初始化默认路由表。

        standard 策略默认不调用 LLM（确定性计算 / 规则模板）；
        仅 molecule_design、polymer_design、evidence_synthesis、literature_analysis
        在 internlm_assisted 下使用 Intern-S2；committee_governed 在此基础上为
        candidate_prioritization、committee_coordination、deviation_analysis 增加
        独立 verifier 路由。
        """
        provider_id = "internlm"
        model_id = "intern-s2-preview-397b"

        routes: list[ModelRoute] = [
            # molecule_design
            ModelRoute(
                route_id="molecule_design_internlm_assisted",
                capability="molecule_design",
                profile="internlm_assisted",
                provider_id=provider_id,
                model_id=model_id,
                requires_structured_output=True,
            ),
            ModelRoute(
                route_id="molecule_design_committee_governed",
                capability="molecule_design",
                profile="committee_governed",
                provider_id=provider_id,
                model_id=model_id,
                temperature=0.8,
                requires_structured_output=False,
            ),
            # polymer_design
            ModelRoute(
                route_id="polymer_design_internlm_assisted",
                capability="polymer_design",
                profile="internlm_assisted",
                provider_id=provider_id,
                model_id=model_id,
                requires_structured_output=True,
            ),
            ModelRoute(
                route_id="polymer_design_committee_governed",
                capability="polymer_design",
                profile="committee_governed",
                provider_id=provider_id,
                model_id=model_id,
                temperature=0.8,
                requires_structured_output=False,
            ),
            # evidence_synthesis
            ModelRoute(
                route_id="evidence_synthesis_internlm_assisted",
                capability="evidence_synthesis",
                profile="internlm_assisted",
                provider_id=provider_id,
                model_id=model_id,
                temperature=0.3,
                requires_structured_output=False,
            ),
            ModelRoute(
                route_id="evidence_synthesis_committee_governed",
                capability="evidence_synthesis",
                profile="committee_governed",
                provider_id=provider_id,
                model_id=model_id,
                temperature=0.3,
                requires_structured_output=False,
            ),
            # literature_analysis
            ModelRoute(
                route_id="literature_analysis_internlm_assisted",
                capability="literature_analysis",
                profile="internlm_assisted",
                provider_id=provider_id,
                model_id=model_id,
                temperature=0.3,
                requires_structured_output=False,
            ),
            ModelRoute(
                route_id="literature_analysis_committee_governed",
                capability="literature_analysis",
                profile="committee_governed",
                provider_id=provider_id,
                model_id=model_id,
                temperature=0.3,
                requires_structured_output=False,
            ),
            # candidate_prioritization — committee_governed 主路由 + verifier
            ModelRoute(
                route_id="candidate_prioritization_committee_governed",
                capability="candidate_prioritization",
                profile="committee_governed",
                provider_id=provider_id,
                model_id=model_id,
                temperature=0.6,
                requires_structured_output=True,
            ),
            ModelRoute(
                route_id="candidate_prioritization_committee_governed_verifier",
                capability="candidate_prioritization",
                profile="committee_governed",
                provider_id=provider_id,
                model_id=model_id,
                temperature=0.2,
                requires_structured_output=True,
                fallback_route_id="candidate_prioritization_committee_governed",
            ),
            # committee_coordination — committee_governed 主路由 + verifier
            ModelRoute(
                route_id="committee_coordination_committee_governed",
                capability="committee_coordination",
                profile="committee_governed",
                provider_id=provider_id,
                model_id=model_id,
                temperature=0.5,
                requires_structured_output=True,
            ),
            ModelRoute(
                route_id="committee_coordination_committee_governed_verifier",
                capability="committee_coordination",
                profile="committee_governed",
                provider_id=provider_id,
                model_id=model_id,
                temperature=0.2,
                requires_structured_output=True,
                fallback_route_id="committee_coordination_committee_governed",
            ),
            # deviation_analysis — committee_governed 主路由 + verifier
            ModelRoute(
                route_id="deviation_analysis_committee_governed",
                capability="deviation_analysis",
                profile="committee_governed",
                provider_id=provider_id,
                model_id=model_id,
                temperature=0.4,
                requires_structured_output=True,
            ),
            ModelRoute(
                route_id="deviation_analysis_committee_governed_verifier",
                capability="deviation_analysis",
                profile="committee_governed",
                provider_id=provider_id,
                model_id=model_id,
                temperature=0.2,
                requires_structured_output=True,
                fallback_route_id="deviation_analysis_committee_governed",
            ),
        ]

        for route in routes:
            key = f"{route.capability}:{route.profile}"
            if route.route_id.endswith("_verifier"):
                key = f"{key}:verifier"
            self._routes[key] = route

    def route(self, capability: str, profile: str, context=None) -> ModelRoute | None:
        """根据能力与策略返回模型路由。

        Returns:
            ModelRoute 如果需要 LLM；None 如果不需要（确定性计算）。
        """
        # 构建查找键
        key = f"{capability}:{profile}"
        route = self._routes.get(key)
        if route:
            return route
        # standard 策略默认不调 LLM
        if profile == "standard":
            return None
        # 尝试回退到 internlm_assisted
        if profile == "committee_governed":
            fallback_key = f"{capability}:internlm_assisted"
            return self._routes.get(fallback_key)
        return None

    def get(self, route_id: str) -> ModelRoute | None:
        """按 route_id 查询路由，找不到返回 None。"""
        for route in self._routes.values():
            if route.route_id == route_id:
                return route
        return None

    def list_all(self) -> list[ModelRoute]:
        """返回所有已注册路由。"""
        return list(self._routes.values())

    def register(self, route: ModelRoute) -> None:
        """注册或替换一条路由，键为 ``{capability}:{profile}``。"""
        self._routes[f"{route.capability}:{route.profile}"] = route

    def update(self, route_id: str, route: ModelRoute) -> bool:
        """按 route_id 替换已有路由。成功返回 True，未找到返回 False。"""
        for key, existing in self._routes.items():
            if existing.route_id == route_id:
                self._routes[key] = route
                return True
        return False
