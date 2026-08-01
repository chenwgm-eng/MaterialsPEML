"""Plan Validator — 校验任务图、依赖、自主等级和预算。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class ValidationResult(BaseModel):
    """校验结果。"""

    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


# 禁止字段关键词：plan 中不得出现这些字符串（防止泄露 endpoint/secret 等敏感信息）
_FORBIDDEN_KEYWORDS = [
    "endpoint",
    "secret",
    "api_key",
    "url",
    "header",
    "remote_tool_name",
]


class PlanValidator:
    """校验 ResearchPlan。

    检查：
    1. 步骤依赖无环
    2. 自主等级不超限（L0 不能调用有副作用工具）
    3. 不包含 endpoint/secret/raw tool name
    4. 必需能力有候选 binding（警告）
    5. 预算预估合理
    """

    def validate(self, plan) -> ValidationResult:
        """校验计划。"""
        errors: list[str] = []
        warnings: list[str] = []

        # 1. DAG 检查
        errors.extend(self._check_dag(plan.steps))

        # 2. 自主等级检查：L0 不能调用有副作用工具（SCP 视为潜在副作用）
        for step in plan.steps:
            if step.autonomy_level == "L0" and step.allowed_tool_aliases:
                side_effect_aliases = [
                    a for a in step.allowed_tool_aliases if a.startswith("scp:")
                ]
                if side_effect_aliases:
                    warnings.append(
                        f"Step {step.step_id} (L0) 含潜在副作用工具: {side_effect_aliases}"
                    )

        # 3. 禁止字段检查
        errors.extend(self._check_forbidden_fields(plan))

        # 4. 必需能力有候选 binding（警告）
        for step in plan.steps:
            if step.required_capabilities and not step.allowed_tool_aliases:
                warnings.append(
                    f"Step {step.step_id} 需要能力 {step.required_capabilities} 但无候选 binding"
                )

        # 5. 预算预估合理性
        budget = plan.estimated_budget or {}
        tokens = budget.get("tokens", 0)
        if isinstance(tokens, (int, float)) and tokens > 1_000_000:
            warnings.append(f"Token 预算 {tokens} 超过 1M 上限")
        dft_jobs = budget.get("dft_jobs", 0)
        if isinstance(dft_jobs, (int, float)) and dft_jobs > 10:
            warnings.append(f"DFT 任务数 {dft_jobs} 超过 10 上限")

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

    def _check_dag(self, steps) -> list[str]:
        """检查依赖图无环。"""
        errors: list[str] = []
        step_ids = {s.step_id for s in steps}

        # 检查依赖引用存在
        for step in steps:
            for dep in step.depends_on:
                if dep not in step_ids:
                    errors.append(
                        f"Step {step.step_id} 依赖未知步骤 {dep}"
                    )

        if errors:
            return errors

        # DFS 检测环
        # 0=white(未访问), 1=gray(访问中), 2=black(已完成)
        visited: dict[str, int] = {s.step_id: 0 for s in steps}
        step_map = {s.step_id: s for s in steps}

        def _dfs(sid: str) -> bool:
            """返回 True 表示检测到环。"""
            if visited[sid] == 1:
                return True
            if visited[sid] == 2:
                return False
            visited[sid] = 1
            for dep in step_map[sid].depends_on:
                if _dfs(dep):
                    return True
            visited[sid] = 2
            return False

        for step in steps:
            if visited[step.step_id] == 0:
                if _dfs(step.step_id):
                    errors.append(
                        f"检测到依赖环，涉及步骤 {step.step_id}"
                    )
                    break

        return errors

    def _check_forbidden_fields(self, plan) -> list[str]:
        """检查不含禁止字段。"""
        errors: list[str] = []

        def _check_text(text: str, context: str) -> None:
            if not text:
                return
            text_lower = text.lower()
            for kw in _FORBIDDEN_KEYWORDS:
                if kw in text_lower:
                    errors.append(f"{context} 含禁止关键词 '{kw}'")

        _check_text(plan.rationale, "Plan rationale")
        _check_text(plan.risk_summary, "Plan risk_summary")

        for step in plan.steps:
            _check_text(step.action, f"Step {step.step_id} action")
            _check_text(step.output_schema_ref, f"Step {step.step_id} output_schema_ref")
            for alias in step.allowed_tool_aliases:
                _check_text(alias, f"Step {step.step_id} allowed_tool_alias")

        return errors
