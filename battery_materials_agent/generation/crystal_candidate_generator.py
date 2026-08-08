"""Crystal candidate generation using Materials Project API and GNoME data with real queries."""

from __future__ import annotations
from pydantic import BaseModel, Field
import httpx
import json
import logging
import uuid
from pathlib import Path
import hashlib

from .chemistry_rules import ChemistryRuleSet

logger = logging.getLogger(__name__)


class CrystalCandidate(BaseModel):
    candidate_id: str = Field(default_factory=lambda: f"CAND-{uuid.uuid4().hex[:8].upper()}")
    formula: str
    structure_type: str = ""
    space_group: str = ""
    energy_above_hull: float = 0.0
    band_gap: float = 0.0
    formation_energy: float = 0.0
    source: str = ""
    material_id: str = ""
    ionic_conductivity_estimate: float = 0.0
    stability_score: float = 0.0
    multi_objective_score: float = 0.0  # 多目标加权综合评分（0-1）
    provenance: list[dict] = Field(default_factory=list)


# 属性提取器：从 CrystalCandidate 中读取各属性值
_PROPERTY_GETTERS = {
    "ionic_conductivity": lambda c: c.ionic_conductivity_estimate,
    "band_gap": lambda c: c.band_gap,
    "formation_energy": lambda c: c.formation_energy,
    "stability": lambda c: c.stability_score,
    "energy_above_hull": lambda c: c.energy_above_hull,
}

# 属性默认方向：maximize（越大越好）或 minimize（越小越好）
_PROPERTY_DIRECTION = {
    "ionic_conductivity": "maximize",
    "band_gap": "maximize",
    "formation_energy": "minimize",  # 越负越稳定
    "stability": "maximize",
    "energy_above_hull": "minimize",  # 越接近凸包越稳定
}


import re as _re


def _normalize_formula(formula: str) -> str:
    """归一化化学式用于去重：使用 pymatgen 的 reduced_formula 保留化学计量比。

    这样 LiCoO2 与 Li2CoO3 不会被误判为同一材料（仅按元素集合去重会导致此问题）。
    """
    if not formula:
        return ""
    try:
        from pymatgen.core import Composition
        return Composition(formula).reduced_formula
    except Exception:
        # 回退：元素符号排序拼接（不精确，但好过无去重）
        elems = _extract_elements(formula)
        return "".join(sorted(elems))


def _extract_elements(formula: str) -> set[str]:
    """从化学式中提取元素符号集合（保留原大小写：Co、Li、O、C）。

    使用 pymatgen.core.Composition 精确解析，正确区分 Co（钴）与 C+O（碳+氧）。
    """
    if not formula:
        return set()
    try:
        from pymatgen.core import Composition
        comp = Composition(formula)
        return {str(e) for e in comp.elements}
    except Exception:
        # 回退到正则（不精确，但好过无过滤）
        matches = _re.findall(r"[A-Z][a-z]?", formula)
        return {m for m in matches if m}


# 支持 thinking_mode 的模型列表（根据 InternLM 官方文档）
# 文档地址：https://internlm.intern-ai.org.cn/api/document
# thinking_mode 仅对以下模型生效，对其他模型发送该参数会返回 400 Bad Request
_THINKING_MODE_SUPPORTED_MODELS = {
    "intern-s2-preview-397b",
    "intern-s2-preview-35b",
    "intern-s2-preview",
    "intern-s1-pro",
    "intern-s1",
    "intern-s1-mini",
}


def _extract_json_from_text(text: str) -> dict | None:
    """从 LLM 返回的文本中提取 JSON 对象。

    LLM 经常用 markdown 代码块（```json ... ```）包裹 JSON，或包含额外说明文字。
    此函数尝试多种方式提取纯 JSON。

    Args:
        text: LLM 返回的原始文本

    Returns:
        解析后的 dict；失败时返回 None
    """
    if not text:
        return None
    text = text.strip()

    # 1. 直接尝试解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 2. 尝试从 markdown 代码块中提取（```json ... ``` 或 ``` ... ```）
    block_match = _re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, _re.DOTALL)
    if block_match:
        try:
            return json.loads(block_match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # 3. 尝试截取第一个 { 到最后一个 } 之间的内容
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        try:
            return json.loads(text[first_brace : last_brace + 1])
        except json.JSONDecodeError:
            pass

    return None


def _extract_elements_with_llm(formulas: list[str]) -> dict[str, set[str]] | None:
    """使用 InternLM 批量解析化学式中的元素符号集合。

    优先调用 LLM 以获得更准确的解析（正确区分 Co 与 C+O 等）。
    如果 LLM 不可用或调用失败（额度限制、认证失败、参数错误等），返回 None，
    调用方应回退到 _extract_elements（pymatgen）。

    根据 InternLM 官方文档（https://internlm.intern-ai.org.cn/api/document）：
    - API URL: {base_url}/chat/completions
    - 支持参数: model, messages, n, temperature, top_p, stream, max_tokens, tools
    - thinking_mode 仅对特定模型（intern-s2-preview-*/intern-s1-*）生效，
      对其他模型发送会导致 400 Bad Request
    - 限流: 默认 30 次/分钟，超限返回 429

    Args:
        formulas: 待解析的化学式列表（去重后更佳）

    Returns:
        {formula: {element1, element2, ...}} 字典；失败时返回 None
    """
    if not formulas:
        return {}
    try:
        from ..config import get_config
        cfg = get_config()
        internlm = cfg.internlm
        if not internlm.enabled or not internlm.api_key:
            return None

        api_key = internlm.api_key.get_secret_value() if internlm.api_key else ""
        if not api_key:
            return None

        # 构造 prompt，要求返回 JSON
        prompt = (
            "你是化学专家。请解析以下化学式，提取每种化学式包含的全部元素符号。\n"
            "要求：\n"
            "1. 元素符号首字母大写，其余小写（如 Li、Co、O、C）\n"
            "2. 注意区分 Co（钴，单一元素）与 C+O（碳+氧，两个元素）\n"
            "3. 仅返回 JSON 对象，不要包含任何其他文字或解释\n"
            f"化学式列表：{json.dumps(formulas, ensure_ascii=False)}\n"
            '示例输出：{"LiCoO2": ["Li", "Co", "O"], "Li2S": ["Li", "S"]}'
        )

        # 构造请求参数：仅当模型支持 thinking_mode 时才发送该参数
        # 官方文档明确 thinking_mode 仅支持特定模型，其他模型发送会报 400
        request_body: dict = {
            "model": internlm.model,
            "messages": [{"role": "user", "content": prompt}],
            # 元素解析是确定性任务，低温度提高一致性
            "temperature": 0.1,
            "top_p": 0.9,
            "n": 1,
            # 限制响应长度，避免大模型发散过多文字（元素列表很短）
            "max_tokens": 1024,
        }
        if internlm.model in _THINKING_MODE_SUPPORTED_MODELS:
            # 元素解析是简单任务，禁用深度思考以加速响应
            request_body["thinking_mode"] = False

        import time

        # 容量限制（-20014 "书生体验过于火爆"）是临时性错误，短暂重试有助于成功
        # 认证失败/参数错误等永久性错误不重试，直接回退
        max_capacity_retries = 2
        retry_delay = 2.0  # 秒

        with httpx.Client(timeout=internlm.timeout_seconds) as client:
            for attempt in range(max_capacity_retries + 1):
                resp = client.post(
                    f"{internlm.base_url.rstrip('/')}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json=request_body,
                )

                # 细化错误处理：区分认证失败、限流、参数错误、容量限制等
                if resp.status_code == 401:
                    logger.warning("InternLM 认证失败（API Key 无效或已过期），回退到 pymatgen")
                    return None
                if resp.status_code == 429:
                    logger.warning("InternLM 限流（429 Too Many Requests，默认 30 次/分钟），回退到 pymatgen")
                    return None
                if resp.status_code == 400:
                    # 区分容量限制（可重试）与真正的参数错误（不可重试）
                    body_text = resp.text[:500]
                    is_capacity = False
                    try:
                        err_body = resp.json()
                        err_code = str(err_body.get("error", {}).get("code", ""))
                        err_msg = err_body.get("error", {}).get("message", "")
                        # -20014: "书生体验过于火爆，请稍后再试" —— 容量限制，可重试
                        if err_code == "-20014" or "火爆" in err_msg or "稍后再试" in err_msg:
                            is_capacity = True
                    except Exception:
                        pass

                    if is_capacity and attempt < max_capacity_retries:
                        logger.info(
                            "InternLM 容量限制（-20014），第 %d/%d 次重试（等待 %.1fs）...",
                            attempt + 1, max_capacity_retries, retry_delay,
                        )
                        time.sleep(retry_delay)
                        continue
                    logger.warning(
                        "InternLM 请求参数错误（400 Bad Request），模型 %r，回退到 pymatgen。响应: %s",
                        internlm.model,
                        body_text,
                    )
                    return None
                if resp.status_code >= 500 and attempt < max_capacity_retries:
                    logger.info(
                        "InternLM 服务端错误（HTTP %d），第 %d/%d 次重试...",
                        resp.status_code, attempt + 1, max_capacity_retries,
                    )
                    time.sleep(retry_delay)
                    continue
                if resp.status_code >= 400:
                    logger.warning(
                        "InternLM 请求失败（HTTP %d）: %s，回退到 pymatgen",
                        resp.status_code,
                        resp.text[:500],
                    )
                    return None

                # 成功，跳出重试循环
                break

            data = resp.json()
            choices = data.get("choices") or []
            if not choices:
                logger.warning("InternLM 返回空 choices，回退到 pymatgen。响应: %s", str(data)[:300])
                return None
            content = choices[0].get("message", {}).get("content", "")
            if not content:
                logger.warning("InternLM 返回空 content，回退到 pymatgen。响应: %s", str(choices[0])[:300])
                return None

            # LLM 可能用 markdown 代码块包裹 JSON，或包含额外说明文字，需要提取
            parsed = _extract_json_from_text(content)
            if parsed is None:
                logger.warning("InternLM 返回内容无法解析为 JSON: %s，回退到 pymatgen", content[:200])
                return None

        result: dict[str, set[str]] = {}
        for f in formulas:
            elems = parsed.get(f, [])
            if isinstance(elems, list):
                result[f] = {str(e).strip().capitalize() for e in elems if e}
            else:
                # LLM 返回格式不对，整体回退
                logger.warning("InternLM 元素解析返回格式异常（%s），回退到 pymatgen", f)
                return None
        logger.info("InternLM 元素解析成功，共解析 %d 个化学式", len(result))
        return result
    except httpx.TimeoutException:
        logger.warning("InternLM 请求超时，回退到 pymatgen")
        return None
    except Exception as e:
        logger.warning("InternLM 元素解析失败，将回退到 pymatgen: %s", e)
        return None


def _apply_multi_objective(
    candidates: list[CrystalCandidate],
    target_properties: list[dict],
) -> list[CrystalCandidate]:
    """多目标加权评分：对每个候选材料计算综合得分并排序。

    target_properties: [{property, weight, direction, min, max}, ...]
    - property: 属性 key（ionic_conductivity/band_gap/formation_energy/stability/energy_above_hull）
    - weight: 权重（0-1，所有权重会归一化）
    - direction: maximize / minimize（覆盖默认方向）
    - min/max: 约束条件（可选，超出范围的候选被过滤）

    评分步骤：
    1. 按约束过滤候选
    2. 对每个属性做 min-max 归一化到 [0, 1]
    3. minimize 方向取 1 - normalized
    4. 加权求和得到综合评分
    5. P0-4：排序时全 0 候选移到末尾，并增加次级排序键
    """
    if not candidates:
        return candidates

    # 规范化配置
    configs = []
    for tp in target_properties:
        prop = tp.get("property") or tp.get("target_property") or ""
        if not prop or prop not in _PROPERTY_GETTERS:
            continue
        weight = float(tp.get("weight", 1.0))
        direction = tp.get("direction") or _PROPERTY_DIRECTION.get(prop, "maximize")
        min_val = tp.get("min")
        max_val = tp.get("max")
        configs.append({
            "property": prop,
            "weight": max(weight, 0.0),
            "direction": direction,
            "min": float(min_val) if min_val is not None else None,
            "max": float(max_val) if max_val is not None else None,
        })

    if not configs:
        return candidates

    # 1. 约束过滤
    filtered = []
    for c in candidates:
        passed = True
        for cfg in configs:
            val = _PROPERTY_GETTERS[cfg["property"]](c)
            if cfg["min"] is not None and val < cfg["min"]:
                passed = False
                break
            if cfg["max"] is not None and val > cfg["max"]:
                passed = False
                break
        if passed:
            filtered.append(c)

    if not filtered:
        return filtered

    # 2. min-max 归一化
    # 先重置评分：本函数可能被多次调用（generate_candidates 生成阶段 + agent 回填后复评分），
    # 若不清零会因 `+=` 累加导致评分 >1 且排序错乱。重置后函数幂等，多次调用等价一次。
    for c in filtered:
        c.multi_objective_score = 0.0
    total_weight = sum(cfg["weight"] for cfg in configs) or 1.0
    for cfg in configs:
        vals = [_PROPERTY_GETTERS[cfg["property"]](c) for c in filtered]
        v_min, v_max = min(vals), max(vals)
        rng = v_max - v_min if v_max > v_min else 1.0
        for c, v in zip(filtered, vals):
            normalized = (v - v_min) / rng
            if cfg["direction"] == "minimize":
                normalized = 1.0 - normalized
            c.multi_objective_score += (cfg["weight"] / total_weight) * normalized

    # 3. P0-4：识别全 0 候选（multi_objective_score == 0 且所有属性值都为默认 0），移到列表末尾
    config_props = [cfg["property"] for cfg in configs]
    def _is_all_zero(c: CrystalCandidate) -> bool:
        if c.multi_objective_score != 0.0:
            return False
        return all(_PROPERTY_GETTERS[p](c) == 0.0 for p in config_props)

    nonzero = [c for c in filtered if not _is_all_zero(c)]
    zero_candidates = [c for c in filtered if _is_all_zero(c)]
    if zero_candidates:
        logger.info(
            "P0-4 排序修正：%d 个全 0 候选将移到列表末尾（避免占首位）",
            len(zero_candidates),
        )

    # 4. P0-4：排序——主键 multi_objective_score 降序，次级键 stability_score 降序 + formation_energy 升序
    #    这样在主分数相同时，更稳定/形成能更负的候选优先
    nonzero.sort(
        key=lambda c: (
            -c.multi_objective_score,
            -c.stability_score,
            c.formation_energy,
        )
    )
    # 全 0 候选内部也按次级键排序，保持稳定展示
    zero_candidates.sort(
        key=lambda c: (
            -c.stability_score,
            c.formation_energy,
        )
    )
    return nonzero + zero_candidates


def _coerce_multi_objective_config(
    target_property: str,
    target_properties: list[dict] | None,
) -> list[dict] | None:
    """P0-4：target_properties 为空但 target_property 已知时，自动构造默认单属性配置，
    强制触发 _apply_multi_objective，避免单目标回退导致 0.0% 评分排首位。

    作为评分配置构造的单一事实来源，供 generate_candidates 与
    agent.discover_crystal 回填后复评分共享，避免两处各自拼装规则。
    """
    if target_properties:
        return target_properties
    if target_property in _PROPERTY_GETTERS:
        default_direction = _PROPERTY_DIRECTION.get(target_property, "maximize")
        return [
            {"property": target_property, "direction": default_direction, "weight": 1.0}
        ]
    return target_properties


class MaterialsProjectDatabase:
    """Curated database of known battery materials from Materials Project literature."""

    KNOWN_BATTERY_MATERIALS = [
        {"formula": "LiCoO2", "space_group": "R-3m", "structure_type": "Layered",
         "band_gap": 2.1, "formation_energy": -2.48, "e_above_hull": 0.0,
         "ionic_conductivity": 1e-4, "material_id": "mp-1962"},
        {"formula": "LiFePO4", "space_group": "Pnma", "structure_type": "Olivine",
         "band_gap": 3.8, "formation_energy": -3.02, "e_above_hull": 0.01,
         "ionic_conductivity": 1e-9, "material_id": "mp-1901"},
        {"formula": "LiMn2O4", "space_group": "Fd-3m", "structure_type": "Spinel",
         "band_gap": 1.5, "formation_energy": -2.35, "e_above_hull": 0.0,
         "ionic_conductivity": 1e-5, "material_id": "mp-2576"},
        {"formula": "LiNiO2", "space_group": "R-3m", "structure_type": "Layered",
         "band_gap": 1.8, "formation_energy": -2.31, "e_above_hull": 0.02,
         "ionic_conductivity": 5e-5, "material_id": "mp-1978"},
        {"formula": "Li2MnO3", "space_group": "C2/m", "structure_type": "Layered",
         "band_gap": 2.5, "formation_energy": -2.65, "e_above_hull": 0.0,
         "ionic_conductivity": 1e-7, "material_id": "mp-756"},
        {"formula": "Li7La3Zr2O12", "space_group": "Ia-3d", "structure_type": "Garnet",
         "band_gap": 5.0, "formation_energy": -4.52, "e_above_hull": 0.0,
         "ionic_conductivity": 1e-3, "material_id": "mp-8435"},
        {"formula": "Na3PS4", "space_group": "P213", "structure_type": "NASICON",
         "band_gap": 3.5, "formation_energy": -1.95, "e_above_hull": 0.02,
         "ionic_conductivity": 2e-4, "material_id": "mp-10170"},
        {"formula": "Li3PS4", "space_group": "Pnma", "structure_type": "Thio-LISICON",
         "band_gap": 3.8, "formation_energy": -1.78, "e_above_hull": 0.05,
         "ionic_conductivity": 1.5e-4, "material_id": "mp-10174"},
        {"formula": "Li6PS5Cl", "space_group": "F-43m", "structure_type": "Argyrodite",
         "band_gap": 3.2, "formation_energy": -2.10, "e_above_hull": 0.01,
         "ionic_conductivity": 3e-3, "material_id": "mp-10256"},
        {"formula": "Li10GeP2S12", "space_group": "P42/nmc", "structure_type": "LGPS",
         "band_gap": 2.8, "formation_energy": -1.65, "e_above_hull": 0.03,
         "ionic_conductivity": 1.2e-2, "material_id": "mp-10408"},
        {"formula": "Li3InCl6", "space_group": "C2/m", "structure_type": "Halide",
         "band_gap": 4.2, "formation_energy": -2.85, "e_above_hull": 0.0,
         "ionic_conductivity": 5e-4, "material_id": "mp-10654"},
        {"formula": "Na3Zr2Si2PO12", "space_group": "R-3c", "structure_type": "NASICON",
         "band_gap": 4.5, "formation_energy": -5.20, "e_above_hull": 0.0,
         "ionic_conductivity": 1e-3, "material_id": "mp-10826"},
        {"formula": "Li2S", "space_group": "Fm-3m", "structure_type": "Antifluorite",
         "band_gap": 3.5, "formation_energy": -1.95, "e_above_hull": 0.0,
         "ionic_conductivity": 1e-8, "material_id": "mp-1037"},
        {"formula": "MoS2", "space_group": "P63/mmc", "structure_type": "Layered",
         "band_gap": 1.2, "formation_energy": -0.85, "e_above_hull": 0.0,
         "ionic_conductivity": 1e-10, "material_id": "mp-2815"},
        {"formula": "TiS2", "space_group": "P-3m1", "structure_type": "Layered",
         "band_gap": 0.5, "formation_energy": -0.95, "e_above_hull": 0.0,
         "ionic_conductivity": 1e-7, "material_id": "mp-1620"},
        {"formula": "WS2", "space_group": "P63/mmc", "structure_type": "Layered",
         "band_gap": 1.3, "formation_energy": -0.78, "e_above_hull": 0.0,
         "ionic_conductivity": 1e-10, "material_id": "mp-2242"},
        {"formula": "V2O5", "space_group": "Pmmn", "structure_type": "Layered",
         "band_gap": 2.2, "formation_energy": -1.55, "e_above_hull": 0.0,
         "ionic_conductivity": 1e-6, "material_id": "mp-1017"},
        {"formula": "Nb2O5", "space_group": "P2", "structure_type": "T-Nb2O5",
         "band_gap": 3.4, "formation_energy": -1.90, "e_above_hull": 0.0,
         "ionic_conductivity": 1e-4, "material_id": "mp-1076"},
        {"formula": "TiO2", "space_group": "P42/mnm", "structure_type": "Rutile",
         "band_gap": 3.0, "formation_energy": -2.40, "e_above_hull": 0.0,
         "ionic_conductivity": 1e-8, "material_id": "mp-2657"},
        {"formula": "SnO2", "space_group": "P42/mnm", "structure_type": "Rutile",
         "band_gap": 3.6, "formation_energy": -2.60, "e_above_hull": 0.0,
         "ionic_conductivity": 1e-7, "material_id": "mp-856"},
        # 扩展：纯 Li-Co-O 体系
        {"formula": "Li2CoO3", "space_group": "C2/m", "structure_type": "Layered",
         "band_gap": 2.8, "formation_energy": -2.55, "e_above_hull": 0.03,
         "ionic_conductivity": 5e-5, "material_id": "mp-759618"},
        {"formula": "Co3O4", "space_group": "Fd-3m", "structure_type": "Spinel",
         "band_gap": 2.0, "formation_energy": -2.10, "e_above_hull": 0.0,
         "ionic_conductivity": 1e-8, "material_id": "mp-795822"},
        {"formula": "CoO", "space_group": "Fm-3m", "structure_type": "Rock Salt",
         "band_gap": 2.4, "formation_energy": -1.85, "e_above_hull": 0.0,
         "ionic_conductivity": 1e-9, "material_id": "mp-1278444"},
        # 扩展：纯 Li-Fe-O 体系
        {"formula": "LiFeO2", "space_group": "R-3m", "structure_type": "Layered",
         "band_gap": 2.5, "formation_energy": -2.40, "e_above_hull": 0.02,
         "ionic_conductivity": 1e-6, "material_id": "mp-753666"},
        {"formula": "Fe2O3", "space_group": "R-3c", "structure_type": "Corundum",
         "band_gap": 2.1, "formation_energy": -1.90, "e_above_hull": 0.0,
         "ionic_conductivity": 1e-9, "material_id": "mp-19770"},
        {"formula": "Fe3O4", "space_group": "Fd-3m", "structure_type": "Inverse Spinel",
         "band_gap": 0.1, "formation_energy": -1.80, "e_above_hull": 0.0,
         "ionic_conductivity": 1e-7, "material_id": "mp-19306"},
        {"formula": "Li5FeO4", "space_group": "Pnn2", "structure_type": "Antifluorite",
         "band_gap": 3.2, "formation_energy": -2.70, "e_above_hull": 0.01,
         "ionic_conductivity": 1e-6, "material_id": "mp-753723"},
        # 扩展：纯 Li-Mn-O 体系
        {"formula": "MnO2", "space_group": "P42/mnm", "structure_type": "Rutile",
         "band_gap": 1.8, "formation_energy": -1.65, "e_above_hull": 0.0,
         "ionic_conductivity": 1e-6, "material_id": "mp-18905"},
        {"formula": "Mn2O3", "space_group": "Ia-3", "structure_type": "Bixbyite",
         "band_gap": 1.9, "formation_energy": -1.75, "e_above_hull": 0.0,
         "ionic_conductivity": 1e-8, "material_id": "mp-18909"},
        {"formula": "LiMnO2", "space_group": "Pmnm", "structure_type": "Layered",
         "band_gap": 2.0, "formation_energy": -2.30, "e_above_hull": 0.01,
         "ionic_conductivity": 1e-6, "material_id": "mp-753647"},
        # 扩展：纯 Li-Ni-O 体系
        {"formula": "NiO", "space_group": "Fm-3m", "structure_type": "Rock Salt",
         "band_gap": 3.5, "formation_energy": -1.90, "e_above_hull": 0.0,
         "ionic_conductivity": 1e-9, "material_id": "mp-19009"},
        {"formula": "Li2NiO3", "space_group": "C2/m", "structure_type": "Layered",
         "band_gap": 2.6, "formation_energy": -2.50, "e_above_hull": 0.02,
         "ionic_conductivity": 3e-5, "material_id": "mp-753651"},
        # 扩展：其他常见电极材料
        {"formula": "Li4Ti5O12", "space_group": "Fd-3m", "structure_type": "Spinel",
         "band_gap": 2.0, "formation_energy": -2.85, "e_above_hull": 0.0,
         "ionic_conductivity": 1e-7, "material_id": "mp-755886"},
        {"formula": "LiV3O8", "space_group": "P21/m", "structure_type": "Layered",
         "band_gap": 1.2, "formation_energy": -2.10, "e_above_hull": 0.0,
         "ionic_conductivity": 1e-5, "material_id": "mp-755886"},
        {"formula": "Li2O", "space_group": "Fm-3m", "structure_type": "Antifluorite",
         "band_gap": 5.5, "formation_energy": -3.20, "e_above_hull": 0.0,
         "ionic_conductivity": 1e-8, "material_id": "mp-1278444"},
    ]

    @classmethod
    def get_materials(cls, elements: list[str] | None = None, formula: str = "") -> list[dict]:
        materials = cls.KNOWN_BATTERY_MATERIALS
        if elements:
            materials = [m for m in materials
                         if any(e in m["formula"] for e in elements)]
        if formula:
            materials = [m for m in materials
                         if formula.lower() in m["formula"].lower()]
        return materials


class CrystalCandidateGenerator:
    """Generate crystal candidates from Materials Project and GNoME datasets."""

    def __init__(self, api_key: str = "", cache_dir: str = "data/mp_cache",
                 gnome_use_mp_mirror: bool = True, gnome_data_dir: str = "data/gnome"):
        self.api_key = api_key
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._client = httpx.Client(timeout=30)
        self._db = MaterialsProjectDatabase()
        self.gnome_use_mp_mirror = gnome_use_mp_mirror
        self.gnome_data_dir = Path(gnome_data_dir)
        # Task 15：最近一次规则引擎硬过滤剔除的候选列表，供委员会决策参考
        self._last_chemistry_filtered_out: list[CrystalCandidate] = []

    def search_materials_project(
        self,
        elements: list[str] | None = None,
        formula: str = "",
        band_gap_range: tuple[float, float] = (0, 10),
        num_results: int = 10,
    ) -> list[CrystalCandidate]:
        cache_key = self._cache_key(elements, formula)
        cached = self._load_cache(cache_key)
        if cached:
            return cached[:num_results]

        if self.api_key:
            try:
                candidates = self._query_mp_api(elements, formula, band_gap_range, num_results)
                self._save_cache(cache_key, candidates)
                return candidates
            except Exception as e:
                logger.warning("MP API query failed: %s", e)

        return self._search_local_db(elements, formula, band_gap_range, num_results)

    def search_gnome(self, formula: str = "", num_results: int = 10,
                     elements: list[str] | None = None) -> list[CrystalCandidate]:
        """
        查询 GNoME 稳定晶体结构数据。

        优先级：
        1. mp-api 客户端查询 Materials Project 镜像（GNoME 数据已同步至 MP）
        2. 本地静态数据集（data/gnome/ 目录下的 CSV/JSON 文件）
        3. 硬编码本地数据库回退
        """
        # 方案 A：通过 mp-api 查询 Materials Project 镜像
        if self.gnome_use_mp_mirror and self.api_key:
            candidates = self._search_gnome_via_mp(formula, elements, num_results)
            if candidates:
                return candidates

        # 方案 B：本地静态数据集
        candidates = self._load_gnome_local(formula, num_results)
        if candidates:
            return candidates

        # 回退：硬编码本地数据库
        return self._search_gnome_fallback(formula, num_results)

    def _search_gnome_via_mp(self, formula: str, elements: list[str] | None,
                             num_results: int) -> list[CrystalCandidate]:
        """通过 REST API 查询 Materials Project 中的 GNoME 理论预测结构。

        使用 GET /materials/summary/ 端点 + theoretical=True 过滤条件，
        无需 mp-api 客户端包，直接 httpx 调用。
        """
        try:
            params: dict = {
                "_limit": num_results,
                "theoretical": "true",
                "_fields": "formula_pretty,symmetry,energy_above_hull,band_gap,formation_energy_per_atom,material_id",
            }
            if formula:
                params["formula"] = formula
            if elements and not formula:
                params["elements"] = ",".join(elements)

            headers = {"X-API-KEY": self.api_key}
            resp = self._client.get(
                "https://api.materialsproject.org/materials/summary/",
                headers=headers,
                params=params,
            )
            resp.raise_for_status()
            data = resp.json()

            candidates = []
            for doc in data.get("data", [])[:num_results]:
                sym = doc.get("symmetry", {})
                candidates.append(CrystalCandidate(
                    formula=doc.get("formula_pretty", ""),
                    space_group=sym.get("symbol", ""),
                    structure_type=sym.get("crystal_system", ""),
                    energy_above_hull=doc.get("energy_above_hull", 0) or 0.0,
                    band_gap=doc.get("band_gap", 0) or 0.0,
                    formation_energy=doc.get("formation_energy_per_atom", 0) or 0.0,
                    material_id=doc.get("material_id", ""),
                    source="gnome_mp_mirror",
                    stability_score=1.0 - (doc.get("energy_above_hull", 0) or 0.0),
                ))
            print(f"[INFO] GNoME MP mirror query: {len(candidates)} results for formula='{formula}'")
            return candidates
        except Exception as e:
            print(f"[WARN] GNoME MP mirror query failed: {e}, falling back to local data")
            return []

    def _load_gnome_local(self, formula: str, num_results: int) -> list[CrystalCandidate]:
        """从本地 data/gnome/ 目录加载 GNoME 静态数据集。"""
        if not self.gnome_data_dir.exists():
            return []

        candidates = []

        # 尝试加载 CSV 文件
        csv_file = self.gnome_data_dir / "gnome_compounds.csv"
        if csv_file.exists():
            try:
                import csv
                with open(csv_file, newline="", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        row_formula = row.get("formula", "")
                        if formula and formula.lower() not in row_formula.lower():
                            continue
                        candidates.append(CrystalCandidate(
                            formula=row_formula,
                            structure_type=row.get("structure_type", ""),
                            space_group=row.get("space_group", ""),
                            energy_above_hull=float(row.get("e_above_hull", 0)),
                            band_gap=float(row.get("band_gap", 0)),
                            formation_energy=float(row.get("formation_energy", 0)),
                            source="gnome_local",
                            material_id=row.get("material_id", ""),
                            ionic_conductivity_estimate=float(row.get("ionic_conductivity", 0)),
                            stability_score=1.0 - float(row.get("e_above_hull", 0)),
                        ))
                        if len(candidates) >= num_results:
                            break
            except Exception as e:
                logger.warning("GNoME CSV load failed: %s", e)

        if candidates:
            return candidates[:num_results]

        # 尝试加载 JSON 文件
        json_file = self.gnome_data_dir / "gnome.json"
        if json_file.exists():
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    for item in data:
                        row_formula = item.get("formula", "")
                        if formula and formula.lower() not in row_formula.lower():
                            continue
                        candidates.append(CrystalCandidate(
                            formula=row_formula,
                            structure_type=item.get("structure_type", ""),
                            space_group=item.get("space_group", ""),
                            energy_above_hull=float(item.get("e_above_hull", 0)),
                            band_gap=float(item.get("band_gap", 0)),
                            formation_energy=float(item.get("formation_energy", 0)),
                            source="gnome_local",
                            material_id=item.get("material_id", ""),
                            ionic_conductivity_estimate=float(item.get("ionic_conductivity", 0)),
                            stability_score=1.0 - float(item.get("e_above_hull", 0)),
                        ))
                        if len(candidates) >= num_results:
                            break
            except Exception as e:
                logger.warning("GNoME JSON load failed: %s", e)

        return candidates[:num_results]

    def _search_gnome_fallback(self, formula: str, num_results: int) -> list[CrystalCandidate]:
        """硬编码本地数据库回退（无 API key 且无本地数据集时使用）。"""
        candidates = []
        for mat in self._db.KNOWN_BATTERY_MATERIALS:
            if formula and formula.lower() not in mat["formula"].lower():
                continue
            candidates.append(CrystalCandidate(
                formula=mat["formula"],
                structure_type=mat["structure_type"],
                space_group=mat["space_group"],
                energy_above_hull=mat["e_above_hull"],
                band_gap=mat["band_gap"],
                formation_energy=mat["formation_energy"],
                source="local_db_fallback",
                material_id=mat["material_id"],
                ionic_conductivity_estimate=mat["ionic_conductivity"],
                stability_score=1.0 - mat["e_above_hull"],
            ))
        return candidates[:num_results]

    def generate_candidates(
        self,
        target_property: str = "ionic_conductivity",
        elements: list[str] | None = None,
        num_candidates: int = 20,
        target_properties: list[dict] | None = None,
        require_elements: list[str] | None = None,
        exclude_elements: list[str] | None = None,
    ) -> list[CrystalCandidate]:
        # P0-4：候选数不足标记——调用方依据返回列表长度自行判断 degraded
        # 多取一些以便去重后仍有足够候选覆盖不同化学式
        fetch_n = max(num_candidates * 2, 20)
        mp_candidates = self.search_materials_project(
            elements=elements, num_results=fetch_n)
        gnome_candidates = self.search_gnome(num_results=fetch_n, elements=elements)
        all_candidates = mp_candidates + gnome_candidates

        # 元素严格过滤：剔除包含目标元素集之外元素的候选
        # （MP 的 elements 参数语义是"包含"，会返回含额外元素如 F/P/B 的材料）
        if elements:
            # 规范化元素符号：首字母大写，其余小写（如 "LI"→"Li", "co"→"Co"）
            allowed = {e.capitalize() for e in elements}

            # 优先使用 InternLM 批量解析化学式元素，失败时回退到 pymatgen
            unique_formulas = list({c.formula for c in all_candidates if c.formula})
            llm_elements = _extract_elements_with_llm(unique_formulas)

            # 元素解析函数：LLM 优先，未覆盖的化学式回退 pymatgen
            # 注意：不能对 LLM 未覆盖的公式返回空集合——空集是任意 allowed 的子集，
            # 会让含目标元素集之外元素的无关候选绕过严格过滤（BLOCKER 回归）。
            def _get_elements(formula: str) -> set[str]:
                if llm_elements is not None:
                    llm_parsed = llm_elements.get(formula)
                    if llm_parsed is not None:
                        return llm_parsed
                return _extract_elements(formula)

            filtered = [
                c for c in all_candidates
                if _get_elements(c.formula).issubset(allowed)
            ]
            logger.info("使用 InternLM 解析元素（未覆盖公式回退 pymatgen），过滤后候选数: %d/%d", len(filtered), len(all_candidates))

            # 候选不足或为空时，补充本地已知电池材料库（严格过滤后去重合并）
            # 使用较大 num_results 确保扩展材料不被截断
            if len(filtered) < num_candidates:
                local = self._search_local_db(elements, formula="", band_gap_range=(0, 10), num_results=200)
                local_filtered = [
                    c for c in local
                    if _get_elements(c.formula).issubset(allowed)
                ]
                # 合并去重：避免与已有 filtered 重复
                existing_keys = {_normalize_formula(c.formula) for c in filtered}
                for c in local_filtered:
                    key = _normalize_formula(c.formula)
                    if key not in existing_keys:
                        filtered.append(c)
                        existing_keys.add(key)
                logger.info("补充本地数据库后候选数: %d", len(filtered))
            all_candidates = filtered

        # 跨源去重：按归一化 formula 去重（同一化学式只保留首个材料），
        # 同时合并来源信息到 provenance 字段
        seen: dict[str, CrystalCandidate] = {}
        for c in all_candidates:
            key = _normalize_formula(c.formula)
            if key not in seen:
                seen[key] = c
            else:
                # 合并 provenance，保留首次记录但标注多来源
                if c.source and c.source not in [p.get("source", "") for p in seen[key].provenance]:
                    seen[key].provenance.append({"source": c.source, "material_id": c.material_id})
        all_candidates = list(seen.values())

        # Task 15：化学规则引擎硬过滤——在 _apply_multi_objective 之前剔除违反
        # 化学约束的候选。规则集优先从用户传入的 require_elements / exclude_elements
        # 构造，否则回退到 AgentConfig.chemistry_rules 默认配置。
        rule_set = self._build_chemistry_rule_set(require_elements, exclude_elements)
        passed_candidates, filtered_out_pairs = rule_set.filter_candidates(all_candidates)
        if filtered_out_pairs:
            logger.info(
                "Task 15 化学规则引擎：%d 个候选被硬过滤剔除（规则：%s）",
                len(filtered_out_pairs),
                {
                    "required": rule_set.required_elements,
                    "forbidden": rule_set.forbidden_elements,
                    "max_elements": rule_set.max_elements_count,
                    "structures": rule_set.required_structure_types,
                },
            )
            # 逐条记录被剔除候选的违反原因，便于审计
            for c, reasons in filtered_out_pairs:
                logger.info(
                    "Task 15 化学规则剔除：%s — %s",
                    getattr(c, "formula", c.get("formula", "") if isinstance(c, dict) else ""),
                    reasons,
                )
        # 缓存被剔除候选（仅候选对象，不含原因元组），供委员会决策参考
        self._last_chemistry_filtered_out = [c for c, _ in filtered_out_pairs]
        all_candidates = passed_candidates

        # P0-4：target_properties 为空但 target_property 已知时，自动构造默认多目标配置
        # 强制触发 _apply_multi_objective，避免单目标回退导致 0.0% 评分排首位
        coerced = _coerce_multi_objective_config(target_property, target_properties)
        if coerced is not target_properties:
            logger.info(
                "P0-4 自动构造默认多目标配置：target_property=%s → %s",
                target_property, coerced,
            )
        target_properties = coerced

        # 多目标优化：target_properties 为 [{property, weight, direction, min, max}, ...]
        if target_properties:
            all_candidates = _apply_multi_objective(all_candidates, target_properties)
            return all_candidates[:num_candidates]

        # 单目标回退（保持向后兼容）
        if target_property == "ionic_conductivity":
            all_candidates.sort(key=lambda c: c.ionic_conductivity_estimate, reverse=True)
        elif target_property == "band_gap":
            all_candidates.sort(key=lambda c: c.band_gap)
        elif target_property == "formation_energy":
            all_candidates.sort(key=lambda c: c.formation_energy, reverse=True)

        return all_candidates[:num_candidates]

    def _filter_by_element_constraints(
        self,
        candidates: list[CrystalCandidate],
        require_elements: list[str] | None,
        exclude_elements: list[str] | None,
    ) -> list[CrystalCandidate]:
        """P0-4：强制元素包含/排除校验——剔除不满足约束的候选。

        .. deprecated:: Task 15
            候选生成主路径已改用 :class:`ChemistryRuleSet` 做硬过滤（见
            :meth:`_build_chemistry_rule_set`），本方法保留供旧调用方兼容。
        """
        if not candidates:
            return candidates
        if not require_elements and not exclude_elements:
            return candidates
        from .formula_validator import _check_element_constraints
        filtered: list[CrystalCandidate] = []
        rejected = 0
        for c in candidates:
            ok, _reason = _check_element_constraints(
                c.formula, require_elements, exclude_elements
            )
            if ok:
                filtered.append(c)
            else:
                rejected += 1
        if rejected:
            logger.info(
                "P0-4 元素约束过滤：%d 个候选被剔除（require=%s, exclude=%s）",
                rejected, require_elements, exclude_elements,
            )
        return filtered

    def _build_chemistry_rule_set(
        self,
        require_elements: list[str] | None,
        exclude_elements: list[str] | None,
    ) -> ChemistryRuleSet:
        """Task 15：构造化学规则集。

        优先级：
        1. 用户传入的 ``require_elements`` / ``exclude_elements`` 覆盖配置默认值
           （显式传参胜出，未传时回退到配置）。
        2. ``max_elements_count`` / ``required_structure_types`` 仅从
           ``AgentConfig.chemistry_rules`` 读取（无对应函数参数）。
        3. 配置缺失时返回空规则集（不做硬过滤），保持向后兼容。
        """
        # 从 AgentConfig.chemistry_rules 读取默认值（若配置可用）
        cfg_required: list[str] = []
        cfg_forbidden: list[str] = []
        cfg_max_elements: int | None = None
        cfg_structures: list[str] = []
        try:
            from ..config import get_config
            cfg = get_config()
            rules_cfg = getattr(cfg, "chemistry_rules", None)
            if rules_cfg is not None:
                cfg_required = list(rules_cfg.required_elements or [])
                cfg_forbidden = list(rules_cfg.forbidden_elements or [])
                cfg_max_elements = rules_cfg.max_elements_count
                cfg_structures = list(rules_cfg.required_structure_types or [])
        except Exception as e:
            logger.debug("读取 AgentConfig.chemistry_rules 失败，使用空默认值: %s", e)

        # 用户传参覆盖配置默认值
        required = list(require_elements) if require_elements else cfg_required
        forbidden = list(exclude_elements) if exclude_elements else cfg_forbidden

        return ChemistryRuleSet(
            required_elements=required,
            forbidden_elements=forbidden,
            max_elements_count=cfg_max_elements,
            required_structure_types=cfg_structures,
        )

    def get_last_chemistry_filtered_out(self) -> list[CrystalCandidate]:
        """Task 15：返回最近一次规则引擎硬过滤剔除的候选列表。

        供晶体委员会适配器（``committee/adapters/crystal.py``）在评估阶段
        作为决策参考——委员会可感知哪些候选因化学约束被排除。
        """
        return list(self._last_chemistry_filtered_out)

    def _query_mp_api(self, elements, formula, band_gap_range, num_results) -> list[CrystalCandidate]:
        # Materials Project REST API: GET /materials/summary/
        # 用 elements 参数查询包含指定元素的材料，客户端再做元素子集过滤
        params: dict = {
            "_limit": num_results * 3,  # 多取一些以便过滤后仍够数
            "_fields": "formula_pretty,symmetry,energy_above_hull,band_gap,formation_energy_per_atom,material_id",
        }
        if elements and not formula:
            params["elements"] = ",".join(elements)
        if formula:
            params["formula"] = formula

        headers = {"X-API-KEY": self.api_key}
        resp = self._client.get(
            "https://api.materialsproject.org/materials/summary/",
            headers=headers,
            params=params,
        )
        resp.raise_for_status()
        data = resp.json()

        candidates = []
        for doc in data.get("data", []):
            bg = doc.get("band_gap", 0) or 0
            # 客户端 band_gap 范围过滤
            if band_gap_range and not (band_gap_range[0] <= bg <= band_gap_range[1]):
                continue
            candidates.append(CrystalCandidate(
                formula=doc.get("formula_pretty", ""),
                structure_type=doc.get("symmetry", {}).get("crystal_system", ""),
                space_group=doc.get("symmetry", {}).get("symbol", ""),
                energy_above_hull=doc.get("energy_above_hull", 0),
                band_gap=bg,
                formation_energy=doc.get("formation_energy_per_atom", 0),
                source="materials_project",
                material_id=doc.get("material_id", ""),
                stability_score=1.0 - doc.get("energy_above_hull", 0),
            ))
            if len(candidates) >= num_results:
                break
        return candidates

    def _search_local_db(self, elements, formula, band_gap_range, num_results) -> list[CrystalCandidate]:
        materials = self._db.get_materials(elements, formula)
        candidates = []
        for mat in materials:
            if not (band_gap_range[0] <= mat["band_gap"] <= band_gap_range[1]):
                continue
            candidates.append(CrystalCandidate(
                formula=mat["formula"],
                structure_type=mat["structure_type"],
                space_group=mat["space_group"],
                energy_above_hull=mat["e_above_hull"],
                band_gap=mat["band_gap"],
                formation_energy=mat["formation_energy"],
                source="local_database",
                material_id=mat["material_id"],
                ionic_conductivity_estimate=mat["ionic_conductivity"],
                stability_score=1.0 - mat["e_above_hull"],
            ))
        return candidates[:num_results]

    def _cache_key(self, elements, formula) -> str:
        key_str = json.dumps({"elements": elements, "formula": formula}, sort_keys=True)
        return hashlib.md5(key_str.encode()).hexdigest()

    def _load_cache(self, key: str) -> list[CrystalCandidate] | None:
        cache_file = self.cache_dir / f"{key}.json"
        if cache_file.exists():
            try:
                data = json.loads(cache_file.read_text())
                return [CrystalCandidate(**item) for item in data]
            except Exception as e:
                logger.warning("Cache load failed for %s: %s", key, e)
        return None

    def _save_cache(self, key: str, candidates: list[CrystalCandidate]):
        cache_file = self.cache_dir / f"{key}.json"
        try:
            cache_file.write_text(json.dumps([c.model_dump() for c in candidates], indent=2))
        except Exception as e:
            logger.warning("Cache save failed for %s: %s", key, e)

    def close(self):
        self._client.close()
