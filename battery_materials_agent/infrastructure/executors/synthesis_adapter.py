"""SynthesisAdapter — ReactNavi 逆合成分析执行适配器。

封装 SMILES 归一化、call_retrosynthesis API 调用、路线解析与错误诊断。
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .execution_adapter import ExecutionAdapter

# 远程 Retrosynthesis API 端点（FastAPI 网关）
_RETROSYNTHESIS_API_URL = "http://101.126.18.187:8100/api/v1/multi-step"

# 本地 USPTO 模板 ASKCOS treebuilder 端点（nginx -> app）
_LOCAL_TREEBUILDER_API_URL = "http://localhost:5000/api/treebuilder/"


class _NoRouteError(Exception):
    """远程服务可用但未返回可用路线，触发回退本地。"""

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


def _template_count_for_depth(search_depth: int) -> int:
    """按搜索深度动态调大候选模板数。

    本地 ASKCOS 使用全局反应频率对模板排序，电池/高分子材料相关的低频模板
    （如碳酸酯、异氰酸酯、环醚）会被高频通用模板挤出前几十名。深度越深越需要
    更多候选模板，否则会漏掉这些低频业务模板。深度<=3 取 200，更深取 500。
    """
    return 500 if search_depth > 3 else 200


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
        "template_max_count": _template_count_for_depth(search_depth),
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


def _call_local_treebuilder(
    target_smiles: str,
    search_depth: int,
    max_paths: int,
    expansion_timeout: int,
) -> dict[str, Any]:
    """调用本地 USPTO 模板 ASKCOS treebuilder 执行逆合成搜索。

    本地端点为 GET /api/treebuilder/，返回 ASKCOS 的 trees 结构（与远程
    ReactNavi FastAPI 的 pathways 结构不同），由
    parse_local_treebuilder_response() 统一转换为上层期望的路由格式。

    Args:
        target_smiles: 目标分子 SMILES（已归一化）。
        search_depth: 搜索深度。
        max_paths: 最大返回路线数。
        expansion_timeout: 搜索超时（秒）。

    Returns:
        treebuilder 原始响应字典。

    Raises:
        ConnectionError: 连接失败时。
        TimeoutError: 请求超时。
        ValueError: 响应不可解析或缺少 trees 时。
    """
    query = urllib.parse.urlencode({
        "smiles": target_smiles,
        "max_depth": search_depth,
        "max_branching": 20,
        "expansion_time": expansion_timeout,
        "template_count": _template_count_for_depth(search_depth),
        "max_cum_prob": 0.999,
        "max_ppg": 10,
        "filter_threshold": 0,  # 关闭 fast-filter，避免误过滤业务分子
        "return_first": "True",
    })
    url = f"{_LOCAL_TREEBUILDER_API_URL}?{query}"
    request_timeout = expansion_timeout + 60

    try:
        with urllib.request.urlopen(url, timeout=request_timeout) as resp:
            result: dict[str, Any] = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise ConnectionError(f"本地 ASKCOS 连接失败: {exc.reason}") from exc
    except TimeoutError as exc:
        raise TimeoutError(f"本地 ASKCOS 请求超时 ({request_timeout}s)") from exc

    if "trees" not in result:
        raise ValueError(f"本地 ASKCOS 响应缺少 trees 字段: {result}")
    return result


def _collect_tree_leaves(
    node: dict[str, Any],
    depth: int,
    leaves: list[tuple[int, list[str]]],
) -> tuple[int, int]:
    """递归收集树节点，返回 (反应节点数, 分子节点数)。

    leaves 追加 (深度, 自根到该叶子的前体 SMILES 链)。
    """
    children: list[dict[str, Any]] = node.get("children", []) or []
    reactions = 1 if children else 0
    chemicals = 1
    if not children:
        leaves.append((depth, []))
        return reactions, chemicals
    for child in children:
        cr, cc = _collect_tree_leaves(child, depth + 1, leaves)
        reactions += cr
        chemicals += cc
    return reactions, chemicals


def parse_local_treebuilder_response(
    api_response: dict[str, Any],
    search_time_s: float = 0.0,
) -> dict[str, Any]:
    """解析本地 treebuilder 响应（trees 结构）为统一 result 格式。

    Args:
        api_response: treebuilder 原始响应。
        search_time_s: 实际搜索耗时（秒）。

    Returns:
        与 parse_retrosynthesis_response 相同结构的 result 字典。
    """
    result: dict[str, Any] = {
        "success": True,
        "stats": {},
        "routes": [],
        "diagnostics": None,
    }

    trees: list[dict[str, Any]] = (api_response.get("trees") or []) if api_response.get(
        "success", True) else []
    # treebuilder 无显式 error 时 success 恒真；若响应含 error 字段则视为失败
    if api_response.get("error"):
        result["success"] = False
        result["diagnostics"] = {
            "error_type": "api_error",
            "error_message": str(api_response.get("error")),
        }
        return result

    total_reactions = 0
    total_chemicals = 0
    leaves: list[tuple[int, list[str]]] = []
    for tree in trees:
        cr, cc = _collect_tree_leaves(tree, 0, leaves)
        total_reactions += cr
        total_chemicals += cc

    result["stats"] = {
        "total_iterations": total_reactions,
        "total_chemicals": total_chemicals,
        "total_reactions": total_reactions,
        "total_templates": total_reactions,
        "total_paths": len(leaves),
        "search_time_s": search_time_s,
    }

    # 将每条叶子路径整理为一条路线（本地无 ff_score，统一给 0 + E0 模板匹配）
    for rank, (_depth, _chain) in enumerate(leaves):
        result["routes"].append({
            "route_rank": rank,
            "avg_ff_score": 0.0,
            "min_ff_score": 0.0,
            "num_reactions": _depth,
            "evidence_grade": "E0",
            "image_url": "",
        })

    return result


class SynthesisAdapter(ExecutionAdapter):
    """ReactNavi 逆合成分析执行适配器。

    封装：
    - SMILES 归一化（离子/盐 → 中性母体）
    - call_retrosynthesis API 调用（远程优先，失败回退本地 USPTO ASKCOS）
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

        # 2. 调用远程 API（优先）
        #    远程失败（连接/超时/无路线/返回失败）时，回退到本地 USPTO 模板 ASKCOS，
        #    保证目标企业（金发/华峰）的低频业务分子也能出路线。
        result["fallback"] = False
        try:
            api_response = _call_retrosynthesis_api(
                target_smiles=normalized,
                search_depth=search_depth,
                max_paths=max_paths,
                expansion_timeout=expansion_timeout,
            )
            parsed = parse_retrosynthesis_response(api_response)
            if not parsed.get("success") or not parsed.get("routes"):
                raise _NoRouteError("远程未返回可用路线")
        except (ConnectionError, TimeoutError, ValueError, _NoRouteError) as exc:
            result["fallback"] = True
            remote_error = str(exc)
            try:
                start = time.time()
                local_response = _call_local_treebuilder(
                    target_smiles=normalized,
                    search_depth=search_depth,
                    max_paths=max_paths,
                    expansion_timeout=expansion_timeout,
                )
                parsed = parse_local_treebuilder_response(
                    local_response, search_time_s=round(time.time() - start, 1))
            except (ConnectionError, TimeoutError, ValueError) as fb_exc:
                result["fallback"] = True
                result["diagnostics"] = {
                    "error_type": "api_error",
                    "error_message": f"远程及本地均失败: {fb_exc}",
                    "remote_error": remote_error,
                }
                return result

        # 3. 组装结果
        result["stats"] = parsed.get("stats", {})
        result["routes"] = parsed.get("routes", [])
        result["diagnostics"] = parsed.get("diagnostics")
        if result["fallback"]:
            result["diagnostics"] = {
                **(result["diagnostics"] or {}),
                "fallback": True,
                "fallback_source": "local_uspto_askcos",
                "remote_error": remote_error,
            }

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