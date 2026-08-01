"""SKILL Executor — 按声明式 pipeline 顺序调用 SCP 工具。

解析 input_mapping 中的表达式，按 pipeline 顺序调用 SCPClientPool.call_tool，
将上一步输出传递给下一步，返回完整的 pipeline 执行结果。

门禁策略：
- 通过注入的 SCPCatalog 查找 binding 的 server_url（避免与 catalog 重复定义）
- 通过 SCPCatalog 检查 SKILL 整体的 ecml_steps 与 pipeline 内每个工具的
  ecml_steps 是否允许当前 ecml_step；任一不通过则整体拒绝执行
- 注：SCPToolProxy.invoke() 内的 SCPPolicy.authorize 不适用于此处，
  因 SKILL pipeline step 使用 server_id 而非 internal_name
"""

from __future__ import annotations
import json
import logging
import re
import time
from typing import Any

from .skill_catalog import SkillBinding, SkillPipelineStep
from .scp_catalog import SCPCatalog

logger = logging.getLogger(__name__)


# 匹配 ${input.xxx} 或 ${prev.output.xxx} 或 ${prev.output_text} 或 ${prev.output}
_EXPR_RE = re.compile(r"^\$\{(.+)\}$")


def _resolve_value(expr: Any, user_input: dict, prev_output: dict | None) -> Any:
    """解析 input_mapping 中的值表达式。

    - 非 str 值直接返回（静态数值/布尔）
    - "${input.xxx}" → user_input["xxx"]
    - "${prev.output.xxx}" → prev_output["xxx"]
    - "${prev.output}" → prev_output 整体
    - "${prev.output_text}" → prev_output 的原始文本
    - 不匹配表达式的 str 直接返回（静态字符串）
    """
    if not isinstance(expr, str):
        return expr
    m = _EXPR_RE.match(expr)
    if not m:
        return expr
    path = m.group(1)
    parts = path.split(".")
    if parts[0] == "input":
        if len(parts) < 2:
            return user_input
        return user_input.get(parts[1], "")
    if parts[0] == "prev":
        if prev_output is None:
            return ""
        if len(parts) < 2:
            return prev_output
        if parts[1] == "output_text":
            return prev_output.get("_raw_text", "")
        if parts[1] == "output":
            if len(parts) == 2:
                return prev_output.get("_parsed", prev_output)
            parsed = prev_output.get("_parsed")
            if isinstance(parsed, dict):
                return parsed.get(parts[2], "")
            return ""
    return expr


def _parse_scp_result(result: dict) -> dict:
    """从 MCP tools/call 的 result 中提取文本并尝试解析为 dict。

    返回的 dict 包含：
    - _raw_text: 原始文本内容
    - _parsed: 解析后的 dict（如果文本是 JSON），否则 None
    - _content: 原始 content 列表
    """
    content = result.get("content") or []
    text_parts: list[str] = []
    for item in content:
        if isinstance(item, dict) and item.get("type") == "text":
            text_parts.append(item.get("text", ""))
    raw_text = "\n".join(text_parts)
    parsed: dict | None = None
    if raw_text:
        try:
            parsed = json.loads(raw_text)
        except (json.JSONDecodeError, TypeError):
            parsed = None
    return {"_raw_text": raw_text, "_parsed": parsed, "_content": content}


# 反向映射：server_id → 该 server 上任一 binding 的 internal_name
# 用于通过 SCPCatalog 查找 server_url（避免与 catalog 重复定义 URL）
_SERVER_ID_TO_BINDING: dict[str, str] = {
    "31": "scp_scitool_chem",
    "40": "scp_scigraph_material",
    "30": "scp_scitool_mat",
    "24": "scp_chem_reaction",
    "8":  "scp_origene_pubchem",
    "4":  "scp_origene_chembl",
    "20": "scp_materials_mechanics",
    "27": "scp_unit_conversion",
    "26": "scp_data_analysis",
    "28": "scp_intern_agent",
    "37": "scp_scigraph",
}


class SkillExecutor:
    """声明式 SKILL pipeline 执行器。

    依赖 SCPClientPool 进行远端调用，按 pipeline 顺序执行，
    每步的输出可被下一步通过 input_mapping 引用。

    通过注入 SCPCatalog 实现：
    - 从 catalog 读取 server_url（避免 URL 重复定义）
    - 检查 SKILL 与每个 pipeline 工具的 ecml_step 门禁
    """

    def __init__(self, scp_client_pool, scp_catalog: SCPCatalog | None = None):
        """注入 SCPClientPool 与 SCPCatalog 实例。

        catalog 可选，未注入时退化为不做 URL 查找和门禁检查
        （保持向后兼容，但生产环境应注入）。
        """
        self.pool = scp_client_pool
        self._catalog = scp_catalog

    def _resolve_server_url(self, server_id: str) -> str:
        """通过 SCPCatalog 查找 server_url，避免与 catalog 重复定义。"""
        if self._catalog is None:
            return ""
        binding_name = _SERVER_ID_TO_BINDING.get(server_id)
        if not binding_name:
            return ""
        binding = self._catalog.get(binding_name)
        return binding.server_url if binding else ""

    def _check_step_gate(self, skill: SkillBinding, step: SkillPipelineStep,
                         ecml_step: int | None) -> tuple[bool, str]:
        """检查 SKILL 整体与 pipeline 单步工具的 ecml_step 门禁。

        返回 (allowed, reason)。allowed=False 时 reason 描述拒绝原因。
        """
        if ecml_step is None:
            return True, ""

        # 1) SKILL 整体 ecml_steps 门禁
        if skill.ecml_steps and ecml_step not in skill.ecml_steps:
            return False, (
                f"SKILL '{skill.skill_id}' 不允许在 ECML step {ecml_step} 执行"
                f"（允许: {skill.ecml_steps}）"
            )

        # 2) pipeline 内单步工具的 server 级 ecml_steps 门禁
        if self._catalog is not None:
            binding_name = _SERVER_ID_TO_BINDING.get(step.server_id)
            if binding_name:
                binding = self._catalog.get(binding_name)
                if binding and binding.ecml_steps and ecml_step not in binding.ecml_steps:
                    return False, (
                        f"SKILL '{skill.skill_id}' 步骤 {step.step_id} 调用的"
                        f"工具 server {step.server_id} ({binding_name})"
                        f"不允许在 ECML step {ecml_step} 执行"
                        f"（允许: {binding.ecml_steps}）"
                    )

        return True, ""

    async def execute(self, skill: SkillBinding, user_input: dict,
                      ecml_step: int | None = None) -> dict:
        """执行一个 SKILL 的完整 pipeline。

        参数 ecml_step：当前 ECML 步骤编号，用于门禁检查；None 表示跳过门禁
        （如管理员自检场景）。

        返回格式：
        {
            "skill_id": "...",
            "status": "success" | "error",
            "steps": [{step_id, tool_name, status, latency_ms, output_preview, ...}],
            "final_output": 最后一步的解析结果,
            "error": 失败时的错误信息,
        }
        """
        # 入口门禁：先检查所有步骤，任一不通过则整体拒绝（fail-fast）
        if ecml_step is not None:
            for step in skill.pipeline:
                allowed, reason = self._check_step_gate(skill, step, ecml_step)
                if not allowed:
                    logger.warning("SKILL %s 门禁拒绝: %s", skill.skill_id, reason)
                    return {
                        "skill_id": skill.skill_id,
                        "status": "error",
                        "steps": [],
                        "final_output": None,
                        "error": f"门禁拒绝: {reason}",
                    }

        steps_result: list[dict] = []
        prev_output: dict | None = None
        final_output: Any = None

        for step in skill.pipeline:
            args = self._build_args(step, user_input, prev_output)
            server_url = self._resolve_server_url(step.server_id)

            step_start = time.monotonic()
            try:
                result = await self.pool.call_tool(
                    step.server_id,
                    step.tool_name,
                    args,
                    server_url=server_url or None,
                )
                latency_ms = int((time.monotonic() - step_start) * 1000)

                if result.get("status") == "error":
                    error_msg = result.get("error", "未知错误")
                    logger.warning(
                        "SKILL %s step %s failed: %s",
                        skill.skill_id, step.step_id, error_msg,
                    )
                    steps_result.append({
                        "step_id": step.step_id,
                        "tool_name": step.tool_name,
                        "server_id": step.server_id,
                        "status": "error",
                        "error": error_msg,
                        "latency_ms": latency_ms,
                    })
                    return {
                        "skill_id": skill.skill_id,
                        "status": "error",
                        "steps": steps_result,
                        "final_output": None,
                        "error": f"步骤 {step.step_id} ({step.tool_name}) 失败: {error_msg}",
                    }

                # 解析输出
                scp_result = result.get("data", {})
                parsed = _parse_scp_result(scp_result)
                prev_output = parsed
                final_output = parsed.get("_parsed") or parsed.get("_raw_text", "")

                steps_result.append({
                    "step_id": step.step_id,
                    "tool_name": step.tool_name,
                    "server_id": step.server_id,
                    "status": "success",
                    "latency_ms": latency_ms,
                    "output_preview": (parsed.get("_raw_text") or "")[:200],
                })
                logger.info(
                    "SKILL %s step %s success: tool=%s latency=%dms",
                    skill.skill_id, step.step_id, step.tool_name, latency_ms,
                )

            except Exception as exc:
                latency_ms = int((time.monotonic() - step_start) * 1000)
                logger.error(
                    "SKILL %s step %s exception: %s",
                    skill.skill_id, step.step_id, exc, exc_info=True,
                )
                steps_result.append({
                    "step_id": step.step_id,
                    "tool_name": step.tool_name,
                    "server_id": step.server_id,
                    "status": "error",
                    "error": str(exc),
                    "latency_ms": latency_ms,
                })
                return {
                    "skill_id": skill.skill_id,
                    "status": "error",
                    "steps": steps_result,
                    "final_output": None,
                    "error": f"步骤 {step.step_id} ({step.tool_name}) 异常: {exc}",
                }

        return {
            "skill_id": skill.skill_id,
            "status": "success",
            "steps": steps_result,
            "final_output": final_output,
            "error": None,
        }

    def _build_args(
        self,
        step: SkillPipelineStep,
        user_input: dict,
        prev_output: dict | None,
    ) -> dict:
        """按 input_mapping 构造工具参数。"""
        args: dict = {}
        for param_name, expr in step.input_mapping.items():
            args[param_name] = _resolve_value(expr, user_input, prev_output)
        return args
