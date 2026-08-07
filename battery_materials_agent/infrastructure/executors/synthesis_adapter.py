"""SynthesisAdapter — ReactNavi 逆合成分析执行适配器。

封装 SMILES 归一化、call_retrosynthesis API 调用、路线解析与错误诊断。
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from typing import Any

from .execution_adapter import ExecutionAdapter

# Retrosynthesis API 端点
_RETROSYNTHESIS_API_URL = "http://101.126.18.187:8100/api/v1/multi-step"

# 离子/盐 → 中性母体归一化规则
_ION_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # 季铵盐 → 叔胺（去季铵化）
    (re.compile(r"\[N\+\]\([^)]*\)\([^)]*\)\([^)]*\)"), "[N+]"),
    # 季磷盐 → 膦
    (re.compile(r"\[P\+\]\([^)]*\)\([^)]*\)\([^)]*\)"), "[P+]"),
    # 羧酸盐 → 羧酸
    (re.compile(r"\[O-\]"), "[OH]"),
    # 酚盐 → 酚
    (re.compile(r"\[O-\]"), "[OH]"),
    # 常见反离子（卤素/金属）
    (re.compile(r"\[Cl-\]"), ""),
    (re.compile(r"\[Br-\]"), ""),
    (re.compile(r"\[I-\]"), ""),
    (re.compile(r"\[F-\]"), ""),
    (re.compile(r"\[Na\+\]"), ""),
    (re.compile(r"\[K\+\]"), ""),
    (re.compile(r"\[Li\+\]"), ""),
    (re.compile(r"\[Mg\+\+\]"), ""),
    (re.compile(r"\[Ca\+\+\]"), ""),
    (re.compile(r"\[Zn\+\+\]"), ""),
    # 点号分隔的多组分（盐/溶剂化物）
    (re.compile(r"\.[A-Za-z0-9@+\-\[\](){}#%=.$\\/|~:&*!,_]+"), ""),
]


def normalize_smiles(smiles: str) -> str:
    """将离子/盐形式的 SMILES 归一化为中性母体。

    应用一系列正则替换规则，将常见离子基团、反离子和盐组分移除，
    保留中性母体分子。保留立体化学信息。

    Args:
        smiles: 原始 SMILES（可能含离子/盐）。

    Returns:
        归一化后的中性母体 SMILES。
    """
    normalized = smiles.strip()

    for pattern, replacement in _ION_PATTERNS:
        normalized = pattern.sub(replacement, normalized)

    # 清理残留的空括号、多余的点号等
    normalized = re.sub(r"\[\]", "", normalized)
    normalized = re.sub(r"^\.+|\.+$", "", normalized)
    normalized = re.sub(r"\.{2,}", ".", normalized)

    return normalized.strip() if normalized.strip() else smiles.strip()


def diagnose_search_result(stats: dict[str, Any], search_time_s: float) -> dict[str, Any] | None:
    """诊断逆合成搜索结果，返回诊断信息（如果发现问题）。

    根据 ReactNavi 架构文档定义的诊断表，识别以下场景：
    - 无模板匹配（total_reactions=0, total_templates=0, <~2s）
    - 有反应无路径（total_reactions>0, total_paths=0）
    - 搜索挂起/超时（~640s 或 expansion_timeout 接近）

    Args:
        stats: 搜索统计信息。
        search_time_s: 实际搜索耗时（秒）。

    Returns:
        诊断信息字典，无问题时返回 None。
    """
    total_reactions = stats.get("total_reactions", 0)
    total_templates = stats.get("total_templates", 0)
    total_paths = stats.get("total_paths", 0)

    # 无模板匹配
    if total_reactions == 0 and total_templates == 0 and search_time_s < 2:
        return {
            "error_type": "no_template",
            "error_message": "无模板匹配 — 目标分子超出模板覆盖范围",
            "recommendation": "回退到更简单前驱体 + 文献/专利搜索",
            "search_time_s": search_time_s,
        }

    # 有反应无路径
    if total_reactions > 0 and total_paths == 0:
        return {
            "error_type": "no_path",
            "error_message": "有反应但未形成完整路线 — 前驱体未达可购买库",
            "recommendation": "扩展搜索深度或回退到文献路线",
            "total_reactions": total_reactions,
            "search_time_s": search_time_s,
        }

    # 搜索挂起/超时（搜索时间接近或超过 expansion_timeout 的 80%）
    timeout_threshold = _get_expansion_timeout_from_stats(stats) * 0.8
    if timeout_threshold > 0 and search_time_s >= timeout_threshold:
        return {
            "error_type": "timeout",
            "error_message": "搜索时间接近超时 — 搜索树可能过度膨胀",
            "recommendation": "检查离子目标是否已归一化；或降低 template_max_count",
            "search_time_s": search_time_s,
            "expansion_timeout": timeout_threshold / 0.8,
        }

    return None


def _get_expansion_timeout_from_stats(stats: dict[str, Any]) -> float:
    """从统计信息中推断 expansion_timeout 值。"""
    # 默认 300 秒，与 PlanSynthesis 默认值一致
    return float(stats.get("expansion_timeout", 300))


def _call_retrosynthesis_api(
    target_smiles: str,
    search_depth: int,
    max_paths: int,
    expansion_timeout: int,
) -> dict[str, Any]:
    """调用 Retrosynthesis API 执行逆合成搜索。

    Args:
        target_smiles: 目标分子 SMILES（已归一化）。
        search_depth: 搜索深度。
        max_paths: 最大返回路线数。
        expansion_timeout: 搜索超时（秒）。

    Returns:
        API 响应字典。

    Raises:
        ConnectionError: API 连接失败时。
        TimeoutError: 请求超时。
        ValueError: API 返回错误响应。
    """
    payload = {
        "target_smiles": target_smiles,
        "max_paths": max_paths,
        "max_depth": search_depth,
        "max_iterations": 2000,
        "template_max_count": 80 if search_depth > 6 else 20,
        "expansion_time": expansion_timeout,
        "session_id": f"peml-{int(time.time())}",
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        _RETROSYNTHESIS_API_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    # request_timeout = expansion_timeout + 60 秒缓冲
    request_timeout = expansion_timeout + 60

    try:
        with urllib.request.urlopen(req, timeout=request_timeout) as resp:
            result: dict[str, Any] = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise ConnectionError(f"Retrosynthesis API 连接失败: {exc.reason}") from exc
    except TimeoutError as exc:
        raise TimeoutError(f"Retrosynthesis API 请求超时 ({request_timeout}s)") from exc

    return result


def parse_retrosynthesis_response(
    api_response: dict[str, Any],
) -> dict[str, Any]:
    """解析 Retrosynthesis API 响应，提取结构化结果。

    Args:
        api_response: API 返回的原始 JSON 字典。

    Returns:
        结构化解析结果，包含 stats, routes, diagnostics 等。
    """
    result: dict[str, Any] = {
        "success": api_response.get("success", False),
        "stats": {},
        "routes": [],
        "diagnostics": None,
    }

    if not result["success"]:
        result["diagnostics"] = {
            "error_type": "api_error",
            "error_message": api_response.get("error", "API 返回失败状态"),
        }
        return result

    # 提取统计信息
    stats = api_response.get("stats", {})
    result["stats"] = {
        "total_iterations": stats.get("total_iterations", 0),
        "total_chemicals": stats.get("total_chemicals", 0),
        "total_reactions": stats.get("total_reactions", 0),
        "total_templates": stats.get("total_templates", 0),
        "total_paths": stats.get("total_paths", 0),
        "search_time_s": stats.get("search_time_s", 0.0),
    }

    # 提取路线
    pathways = api_response.get("pathways", [])
    for pathway in pathways:
        route: dict[str, Any] = {
            "route_rank": pathway.get("route_rank", 0),
            "avg_ff_score": pathway.get("avg_ff_score", 0.0),
            "min_ff_score": pathway.get("min_ff_score", 0.0),
            "num_reactions": pathway.get("num_reactions", 0),
            "evidence_grade": "E0",  # 默认：模板匹配
            "image_url": pathway.get("image_file", ""),
        }
        result["routes"].append(route)

    # 按 route_rank 排序
    result["routes"].sort(key=lambda r: r["route_rank"])

    # 错误诊断
    search_time_s = result["stats"].get("search_time_s", 0.0)
    result["diagnostics"] = diagnose_search_result(result["stats"], search_time_s)

    return result


class SynthesisAdapter(ExecutionAdapter):
    """ReactNavi 逆合成分析执行适配器。

    封装：
    - SMILES 归一化（离子/盐 → 中性母体）
    - call_retrosynthesis API 调用
    - 路线解析与评分
    - 错误诊断与回退策略
    """

    def __init__(self, api_url: str = _RETROSYNTHESIS_API_URL):
        self.api_url = api_url

    def execute(self, prepared_input: dict[str, Any]) -> dict[str, Any]:
        """执行逆合成分析。

        Args:
            prepared_input: 包含 target_smiles, search_depth, max_paths,
                           normalize_ions, expansion_timeout 等参数。

        Returns:
            原始结果字典，包含归一化信息、统计、路线和诊断。
        """
        target_smiles: str = prepared_input.get("target_smiles", "")
        search_depth: int = prepared_input.get("search_depth", 3)
        max_paths: int = prepared_input.get("max_paths", 10)
        normalize_ions_flag: bool = prepared_input.get("normalize_ions", True)
        expansion_timeout: int = prepared_input.get("expansion_timeout", 300)

        # 1. 归一化
        normalized = target_smiles
        if normalize_ions_flag:
            normalized = normalize_smiles(target_smiles)

        result: dict[str, Any] = {
            "normalized_smiles": normalized,
            "stats": {},
            "routes": [],
            "diagnostics": None,
        }

        # 2. 调用 API
        try:
            api_response = _call_retrosynthesis_api(
                target_smiles=normalized,
                search_depth=search_depth,
                max_paths=max_paths,
                expansion_timeout=expansion_timeout,
            )
        except (ConnectionError, TimeoutError, ValueError) as exc:
            result["diagnostics"] = {
                "error_type": "api_error",
                "error_message": str(exc),
            }
            return result

        # 3. 解析响应
        parsed = parse_retrosynthesis_response(api_response)
        result["stats"] = parsed.get("stats", {})
        result["routes"] = parsed.get("routes", [])
        result["diagnostics"] = parsed.get("diagnostics")

        return result

    def parse_output(self, raw_output: Any) -> dict[str, Any]:
        """解析原始输出为结构化 dict。"""
        if isinstance(raw_output, dict):
            return raw_output
        return {"normalized_smiles": "", "stats": {}, "routes": [], "diagnostics": None}

    def get_resource_requirements(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """返回资源需求。"""
        return {
            "cpu": 1,
            "memory_mb": 512,
            "walltime_minutes": max(5, input_data.get("expansion_timeout", 300) // 60 + 1),
        }