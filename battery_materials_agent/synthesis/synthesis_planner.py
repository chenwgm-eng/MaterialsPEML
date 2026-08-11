"""Synthesis pathway planning using ASKCOS retro-synthesis + local heuristic scoring."""

from __future__ import annotations
from pydantic import BaseModel, Field
import httpx
import numpy as np
import asyncio
import json
import logging
from typing import Optional

from ..config import AgentConfig, EngineMode, ASKCOSConfig, get_config
from ..generation.formula_validator import parse_formula_elements

logger = logging.getLogger(__name__)


# 支持 thinking_mode 的模型列表（根据 InternLM 官方文档）
# thinking_mode 仅对以下模型生效，对其他模型发送该参数会返回 400 Bad Request
_THINKING_MODE_SUPPORTED_MODELS = {
    "intern-s2-preview-397b",
    "intern-s2-preview-35b",
    "intern-s2-preview",
    "intern-s1-pro",
    "intern-s1",
    "intern-s1-mini",
}


class SynthesisServiceError(Exception):
    """逆合成服务调用失败的异常。携带服务名称和原始异常，便于上层精细化提示。"""

    def __init__(self, message: str, service: str = "", cause: Exception | None = None):
        super().__init__(message)
        self.service = service
        self.cause = cause


class RouteStep(BaseModel):
    reaction_smiles: str = ""
    reactants: list[str] = Field(default_factory=list)
    products: list[str] = Field(default_factory=list)
    conditions: str = ""
    score: float = 0.0
    template_score: float = 0.0
    difficulty: str = "medium"
    reaction_type: str = ""
    # Task 18：工艺标签与温度一致性校验。process_label 为按步骤温度推断的工艺标签，
    # label_conflict 标记该步骤的路线级工艺标签与温度不符（已按温度自动校准）。
    process_label: str = ""
    label_conflict: bool = False
    process_label_note: str = ""


class SynthesisRoute(BaseModel):
    target_smiles: str
    steps: list[RouteStep] = Field(default_factory=list)
    overall_score: float = 0.0
    num_steps: int = 0
    feasibility_score: float = 0.0
    is_feasible: bool = False
    confidence: float = 0.0
    provenance: list[dict] = Field(default_factory=list)
    # 路线来源（AI 透明性）：askcos / internlm / local_template / scp
    source: str = ""


class SynthesisPlanner:
    """Plan synthesis routes using ASKCOS retro-synthesis + local heuristic scoring."""

    KNOWN_REACTIONS = {
        "esterification": {"pattern": "C(=O)O", "reagents": "acid + alcohol", "score": 0.85},
        "grignard": {"pattern": "C-C(=O)", "reagents": "R-MgBr + carbonyl", "score": 0.7},
        "suzuki": {"pattern": "c1ccccc1-c1ccccc1", "reagents": "aryl halide + boronic acid", "score": 0.9},
        "wittig": {"pattern": "C=C", "reagents": "ylide + aldehyde", "score": 0.75},
        "reduction": {"pattern": "C-O", "reagents": "LiAlH4 or NaBH4", "score": 0.9},
        "oxidation": {"pattern": "C=O", "reagents": "PCC or Jones", "score": 0.85},
        "nucleophilic_sub": {"pattern": "C-X", "reagents": "nucleophile + alkyl halide", "score": 0.8},
        "amide_formation": {"pattern": "C(=O)N", "reagents": "acid + amine", "score": 0.88},
        "sulfonation": {"pattern": "S(=O)(=O)", "reagents": "SO3 or SOCl2", "score": 0.7},
        "phosphorylation": {"pattern": "P(=O)", "reagents": "POCl3 or P2O5", "score": 0.65},
    }

    def __init__(
        self,
        config: AgentConfig | None = None,
        askcos_url: str = "http://localhost:5000",
        timeout: int = 5,
    ):
        # 保持旧的位置参数向后兼容：若第一个参数不是 AgentConfig 而是字符串 URL
        if config is not None and not isinstance(config, AgentConfig):
            askcos_url = config if isinstance(config, str) else askcos_url
            config = None

        if config is None:
            # 默认复用应用级全局配置（含 InternLM/ASKCOS/EngineMode 等），
            # 避免无参构造时空 AgentConfig 导致 InternLM 凭据缺失。
            try:
                from ..config import get_config
                config = get_config()
            except Exception:
                config = AgentConfig(
                    askcos=ASKCOSConfig(base_url=askcos_url, timeout=timeout),
                    engine_mode=EngineMode.LEGACY,
                )

        self.config = config
        self.askcos_url = config.askcos.base_url.rstrip("/")
        self.timeout = config.askcos.timeout
        self._async_client: Optional[httpx.AsyncClient] = None

    def _get_async_client(self) -> httpx.AsyncClient:
        if self._async_client is None or self._async_client.is_closed:
            # 不在客户端级别锁定 timeout，让每个请求按自身需要传入 httpx.Timeout
            self._async_client = httpx.AsyncClient(
                timeout=httpx.Timeout(connect=10.0, read=None, write=None, pool=None),
            )
        return self._async_client

    async def aclose(self) -> None:
        """关闭内部 httpx.AsyncClient 连接池，应在 FastAPI shutdown 时调用。"""
        if self._async_client is not None and not self._async_client.is_closed:
            await self._async_client.aclose()
            self._async_client = None

    async def plan_synthesis_async(
        self,
        smiles: str,
        max_depth: int = 3,
        num_routes: int = 5,
        engine_type: str | None = None,
    ) -> list[SynthesisRoute]:
        """规划逆合成路径。ASKCOS/InternLM 失败时直接抛错，由调用方决定如何向用户反馈。

        参数 engine_type 优先于 config.engine_mode；"logos" 为兼容别名，统一映射到 InternLM。

        异常类型：
        - SynthesisServiceError：服务连接/响应失败（建议提示用户检查 ASKCOS 服务）
        - ValueError：输入参数无效（如空 SMILES）
        """
        if not smiles:
            raise ValueError("SMILES string is required")

        # engine_type 优先于 config.engine_mode；LOGOS 已统一到 InternLM
        effective = (engine_type or self.config.engine_mode.value).lower()
        use_internlm = effective in ("logos", "internlm")

        if use_internlm:
            try:
                return await self._plan_with_internlm(smiles, max_depth, num_routes)
            except SynthesisServiceError:
                raise  # 直接抛出，由调用方处理
            except Exception as e:
                raise SynthesisServiceError(
                    f"InternLM 逆合成服务调用失败: {e}",
                    service="InternLM",
                    cause=e,
                ) from e

        try:
            return await self._plan_with_askcos(smiles, max_depth, num_routes)
        except SynthesisServiceError:
            raise
        except Exception as e:
            raise SynthesisServiceError(
                f"ASKCOS 逆合成服务调用失败: {e}。请检查 ASKCOS 服务是否在 {self.askcos_url} 正常运行，"
                f"且 MongoDB 中的反应模板数据已正确导入。",
                service="ASKCOS",
                cause=e,
            ) from e

    async def _plan_with_askcos(self, smiles: str, max_depth: int, num_routes: int) -> list[SynthesisRoute]:
        askcos_url = self.config.askcos.base_url.rstrip("/")
        client = self._get_async_client()
        # ASKCOS treebuilder 仅支持 GET，通过 query params 传参（URL 需带尾部斜杠避免 301）
        resp = await client.get(
            f"{askcos_url}/api/treebuilder/",
            params={
                "smiles": smiles,
                "max_depth": max_depth,
                "n_cards": min(num_routes, 5),
                "return_first": "true",
            },
            follow_redirects=True,
        )
        if resp.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"ASKCOS 返回 HTTP {resp.status_code}, 响应内容: {resp.text[:500]}",
                request=resp.request, response=resp,
            )
        data = resp.json()
        routes = []
        for tree in data.get("trees", [])[:num_routes]:
            steps = self._parse_tree(tree)
            # ASKCOS 树中 plausibility 在子反应节点上，取最大值作为路径评分
            score = self._extract_tree_score(tree)
            # 空树（仅有目标根节点、无任何反应）视为未找到合成路线，
            # 跳过以触发调用方本地树兜底，避免生成"0 步"空路线误导用户
            if not steps:
                continue
            routes.append(SynthesisRoute(
                target_smiles=smiles,
                steps=steps,
                num_steps=len(steps),
                overall_score=score,
                feasibility_score=score,
                is_feasible=score > 0.3,
                confidence=score,
                source="askcos",
            ))
        return routes

    def _resolve_internlm_creds(self) -> tuple[str, str, str, httpx.Timeout]:
        """解析 InternLM 调用凭证与超时配置。

        LOGOS 已统一到 InternLM，统一使用 config.internlm 配置。
        返回 (base_url, api_key, model_name, httpx.Timeout)。
        读超时不限制（InternLM 推理可能较慢），仅保留 connect 超时。
        """
        internlm = getattr(self.config, "internlm", None)
        if not internlm or not internlm.api_key:
            raise SynthesisServiceError(
                "InternLM 配置缺失：请在 .env 中设置 INTERNLM_API_KEY。",
                service="InternLM",
            )
        key = internlm.api_key.get_secret_value() if hasattr(internlm.api_key, "get_secret_value") else str(internlm.api_key)
        connect_timeout = float(getattr(internlm, "connect_timeout_seconds", 10.0))
        timeout = httpx.Timeout(connect=connect_timeout, read=None, write=None, pool=None)
        return (
            internlm.base_url.rstrip("/"),
            key,
            internlm.model,
            timeout,
        )

    async def _internlm_stream_chat(
        self,
        endpoint: str,
        api_key: str,
        model_name: str,
        prompt: str,
        timeout: httpx.Timeout,
        temperature: float = 0.4,
        max_tokens: int = 2048,
    ) -> str:
        """流式调用 InternLM chat/completions，边接收边拼接，避免单次读超时。

        InternLM 推理模型响应较慢（首 token 可能 60s+），用 stream=True 让服务端
        持续吐 token，每个 chunk 都会重置 httpx 的 read 计时。

        关键：对支持 thinking_mode 的模型（intern-s2-preview-*/intern-s1-*），
        必须显式传 thinking_mode=False 才能关闭深度思考模式。否则 397B 模型
        默认启用深度思考，单次响应 5-10 分钟，会触发 600s 超时。
        """
        client = self._get_async_client()
        # 构造请求体：仅当模型支持 thinking_mode 时才发送该参数
        # 官方文档明确 thinking_mode 仅支持特定模型，其他模型发送会报 400
        request_body: dict = {
            "model": model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        if model_name in _THINKING_MODE_SUPPORTED_MODELS:
            # 合成规划是结构化 JSON 生成任务，不需要深度推理
            # 读取配置（.env 中 INTERNLM_THINKING_MODE 默认 false）
            try:
                cfg = get_config()
                thinking_mode = cfg.internlm.thinking_mode
            except Exception:
                thinking_mode = False  # 安全兜底：关闭深度思考以加速响应
            request_body["thinking_mode"] = thinking_mode

        async with client.stream(
            "POST",
            endpoint,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Accept": "text/event-stream",
            },
            json=request_body,
            timeout=timeout,
        ) as resp:
            if resp.status_code >= 400:
                body = await resp.aread()
                raise httpx.HTTPStatusError(
                    f"InternLM 返回 HTTP {resp.status_code}, 响应内容: {body.decode('utf-8', errors='replace')[:500]}",
                    request=resp.request, response=resp,
                )
            content_parts: list[str] = []
            reasoning_parts: list[str] = []
            async for line in resp.aiter_lines():
                # SSE 格式：每行以 "data: " 开头，结束标记 "data: [DONE]"
                if not line or not line.startswith("data:"):
                    continue
                payload = line[len("data:"):].strip()
                if payload == "[DONE]":
                    break
                try:
                    chunk = json.loads(payload)
                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    # Intern-S2 推理模型：thinking_mode 启用时，内容在 reasoning_content
                    # 非 thinking 模型或思考结束后，内容在 content
                    piece = delta.get("content", "")
                    if piece:
                        content_parts.append(piece)
                    reasoning = delta.get("reasoning_content", "")
                    if reasoning:
                        reasoning_parts.append(reasoning)
                except Exception:
                    continue
            # 优先返回 content；若 content 为空（纯思考模式），回退到 reasoning_content
            final_content = "".join(content_parts)
            if not final_content and reasoning_parts:
                final_content = "".join(reasoning_parts)
            return final_content

    async def _plan_with_internlm(self, smiles: str, max_depth: int, num_routes: int) -> list[SynthesisRoute]:
        base_url, api_key, model_name, timeout = self._resolve_internlm_creds()
        endpoint = f"{base_url}/chat/completions"
        prompt = (
            f"Perform retrosynthesis for target SMILES: {smiles}\n"
            "Return a JSON list of reaction routes. Each route is {\"reactants\": [\"SMILES1\", \"SMILES2\"], \"score\": 0.85}\n"
            f"重要约束：所有反应物的元素组成必须与目标分子 {smiles} 的元素组成完全一致，不得引入目标分子中不存在的元素（如 S、F、Cl、Br 等）。"
        )

        # 流式调用：InternLM 推理模型首 token 可能 60s+，stream=True 让每个 chunk 重置 read 计时
        content = await self._internlm_stream_chat(
            endpoint=endpoint,
            api_key=api_key,
            model_name=model_name,
            prompt=prompt,
            timeout=timeout,
            temperature=0.3,
            max_tokens=1024,
        )

        routes: list[SynthesisRoute] = []
        try:
            json_match = content[content.index("["):content.rindex("]") + 1]
            data = json.loads(json_match)
        except Exception as exc:
            raise ValueError(f"Could not parse InternLM response: {exc}\n原始内容: {content[:300]}")

        if not isinstance(data, list):
            raise ValueError("InternLM response is not a JSON list")

        for item in data:
            reactants = item.get("reactants", [])
            if isinstance(reactants, str):
                reactants = [reactants]
            score = float(item.get("score", 0.5))
            steps = [
                RouteStep(
                    reaction_smiles=f"{reactant}>>{smiles}",
                    reactants=[reactant],
                    products=[smiles],
                    conditions="",
                    score=score,
                    reaction_type="retrosynthesis",
                )
                for reactant in reactants
            ]
            routes.append(SynthesisRoute(
                target_smiles=smiles,
                steps=steps,
                num_steps=len(steps),
                overall_score=score,
                feasibility_score=score,
                is_feasible=score > 0.3,
                confidence=score,
                source="internlm",
            ))

        if not routes:
            raise ValueError("InternLM returned no routes")
        return routes[:num_routes]

    async def _plan_crystal_with_internlm(
        self,
        formula: str,
        space_group: str,
        num_routes: int,
    ) -> tuple[list[SynthesisRoute], dict]:
        """为晶体材料生成固相合成路线（LLM 推理）。

        返回 (routes, meta)，meta 包含 agent_info 与 reasoning，供前端展示。
        元素校验：前驱体元素组成必须 ⊇ 目标晶体元素组成。
        """
        base_url, api_key, model_name, timeout = self._resolve_internlm_creds()
        endpoint = f"{base_url}/chat/completions"

        # 解析目标晶体的元素组成
        target_elements = self._parse_formula_elements(formula)

        prompt = (
            f"为晶体材料 {formula}（空间群 {space_group or '未知'}）设计 {num_routes} 条合成路线。\n"
            "请基于高温固相法 / 溶胶凝胶法 / 水热法 / 共沉淀法等常用无机合成工艺。\n"
            "返回严格 JSON（不要 markdown 代码块）：\n"
            "{\n"
            '  "routes": [\n'
            '    {\n'
            '      "method": "高温固相法",\n'
            '      "precursors": ["Li2CO3", "Co3O4"],\n'
            '      "steps": [\n'
            '        {"action": "球磨混合", "temperature": 25, "duration": 2, "atmosphere": "air"},\n'
            '        {"action": "煅烧", "temperature": 800, "duration": 12, "atmosphere": "air"}\n'
            '      ],\n'
            '      "score": 0.85,\n'
            '      "key_notes": "注意 Li 挥发补偿"\n'
            '    }\n'
            "  ],\n"
            '  "reasoning": "简要说明为何选择这些前驱体与工艺（包含热力学与动力学考虑）"\n'
            "}\n"
            f"重要约束：所有前驱体的元素并集必须包含目标晶体 {formula} 的所有元素 {sorted(target_elements)}，"
            "不得缺失任何元素，但可以包含额外的 O/N/H 等辅助元素（来自空气/溶剂）。\n"
            "score 取 0.0-1.0，反映工艺成熟度与产率预期。"
        )

        # 流式调用：InternLM 推理模型首 token 可能 60s+，stream=True 让每个 chunk 重置 read 计时
        content = await self._internlm_stream_chat(
            endpoint=endpoint,
            api_key=api_key,
            model_name=model_name,
            prompt=prompt,
            timeout=timeout,
            temperature=0.4,
            max_tokens=2048,
        )

        # 提取 JSON（兼容 markdown 代码块包裹）
        try:
            json_start = content.find("{")
            json_end = content.rfind("}") + 1
            if json_start < 0 or json_end <= 0:
                raise ValueError("响应中未找到 JSON 对象")
            parsed = json.loads(content[json_start:json_end])
        except Exception as exc:
            raise ValueError(f"无法解析 InternLM 晶体合成响应: {exc}\n原始内容: {content[:300]}")

        raw_routes = parsed.get("routes", [])
        reasoning = parsed.get("reasoning", "")

        routes: list[SynthesisRoute] = []
        rejected = 0
        for idx, item in enumerate(raw_routes[:num_routes]):
            precursors = item.get("precursors", [])
            if isinstance(precursors, str):
                precursors = [precursors]
            precursors = [p.strip() for p in precursors if p and p.strip()]
            if not precursors:
                continue

            # 元素校验：前驱体元素并集必须 ⊇ 目标晶体元素
            if not self._validate_crystal_elements(formula, precursors):
                rejected += 1
                continue

            method = item.get("method", "固相合成")
            steps_data = item.get("steps", [])
            score = float(item.get("score", 0.6))
            key_notes = item.get("key_notes", "")

            steps: list[RouteStep] = []
            # Task 18：工艺标签与温度一致性校验。逐步骤按温度推断工艺标签，
            # 避免低温步骤被笼统标注为路线级“高温固相法”。
            calibration_notes: list[str] = []
            for s_idx, s in enumerate(steps_data):
                action = s.get("action", f"步骤{s_idx + 1}")
                temp = s.get("temperature")
                dur = s.get("duration")
                atm = s.get("atmosphere", "")

                # 按步骤温度自动校准工艺标签（None/非法温度时回退到路线 method）
                auto_label = self._classify_process_by_temperature(temp, fallback=method)
                label_conflict = temp is not None and auto_label != method
                process_label_note = ""
                if label_conflict:
                    process_label_note = (
                        f"工艺标签与温度不符，已按温度自动校准：{temp}°C 归为{auto_label}"
                        f"（原路线标注：{method}）"
                    )
                    calibration_notes.append(process_label_note)

                cond_parts = [auto_label]
                if temp is not None:
                    cond_parts.append(f"{temp}°C")
                if dur is not None:
                    cond_parts.append(f"{dur}h")
                if atm:
                    cond_parts.append(f"{atm} atmosphere")
                conditions = " / ".join(cond_parts)
                steps.append(RouteStep(
                    reaction_smiles=f"{'+'.join(precursors)}>>{formula}",
                    reactants=precursors,
                    products=[formula],
                    conditions=conditions,
                    score=score,
                    reaction_type=auto_label,
                    process_label=auto_label,
                    label_conflict=label_conflict,
                    process_label_note=process_label_note,
                    difficulty="medium",
                ))

            if not steps:
                steps.append(RouteStep(
                    reaction_smiles=f"{'+'.join(precursors)}>>{formula}",
                    reactants=precursors,
                    products=[formula],
                    conditions=method,
                    score=score,
                    reaction_type=method,
                ))

            routes.append(SynthesisRoute(
                target_smiles=formula,
                steps=steps,
                num_steps=len(steps),
                overall_score=score,
                feasibility_score=score,
                is_feasible=score > 0.3,
                confidence=score * 0.85,
                source="internlm",
                provenance=[
                    {"method": method, "key_notes": key_notes, "precursors": precursors},
                    *([{
                        "calibration": "工艺标签与温度不符，已按温度自动校准",
                        "details": calibration_notes,
                    }] if calibration_notes else []),
                ],
            ))

        if not routes:
            raise ValueError(
                f"InternLM 晶体合成路线未通过元素校验或为空（拒绝 {rejected} 条；目标元素 {sorted(target_elements)}）"
            )

        meta = {
            "agent_info": {
                "agent_id": "internlm_crystal_synth",
                "name": "AI4S大模型·晶体合成规划",
                "role": "thinker",
                "model": model_name,
                "capabilities": ["synthesis_evidence", "crystal_synthesis"],
            },
            "reasoning": reasoning,
            "engine": "internlm",
            "material_type": "crystal",
            "rejected_count": rejected,
        }
        return routes, meta

    @staticmethod
    def _classify_process_by_temperature(temp, fallback: str = "固相合成") -> str:
        """根据步骤温度(°C)推断工艺标签。

        Task 18：工艺标签与温度一致性校验。避免低温步骤被笼统标注为“高温固相法”。
        - temp >= 600        -> 高温固相法
        - 300 <= temp < 600  -> 中温煅烧
        - 100 < temp < 300   -> 低温/球磨法
        - temp <= 100        -> 室温球磨法
        - temp 为 None/非法  -> 返回 fallback（默认“固相合成”）
        """
        if temp is None:
            return fallback
        try:
            temp = float(temp)
        except (TypeError, ValueError):
            return fallback
        if temp >= 600:
            return "高温固相法"
        if temp >= 300:
            return "中温煅烧"
        if temp > 100:
            return "低温/球磨法"
        return "室温球磨法"

    @staticmethod
    def _parse_formula_elements(formula: str) -> set[str]:
        """解析化学式中的元素集合（如 'LiCoO2' -> {'Li', 'Co', 'O'}）。

        复用 formula_validator.parse_formula_elements，支持嵌套括号、
        小数系数，并验证每个元素符号是否在周期表中。
        """
        if not formula:
            return set()
        return parse_formula_elements(formula)

    def _validate_crystal_elements(self, formula: str, precursors: list[str]) -> bool:
        """校验前驱体元素并集是否 ⊇ 目标晶体元素（允许额外 O/N/H 等辅助元素）。"""
        target = self._parse_formula_elements(formula)
        if not target:
            return True
        precursor_elements: set[str] = set()
        for p in precursors:
            precursor_elements |= self._parse_formula_elements(p)
        # 目标元素必须全部被前驱体覆盖
        return target.issubset(precursor_elements)

    async def check_feasibility_async(self, smiles: str) -> float:
        routes = await self.plan_synthesis_async(smiles, max_depth=2, num_routes=3)
        if not routes:
            return 0.0
        return max(r.feasibility_score for r in routes)

    def plan_synthesis(self, smiles: str, max_depth: int = 3, num_routes: int = 5) -> list[SynthesisRoute]:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            # 无事件循环，可安全使用 asyncio.run
            try:
                routes = asyncio.run(self.plan_synthesis_async(smiles, max_depth, num_routes))
                if routes:
                    return routes
                # ASKCOS 可达但无可用树（空 trees）：与异常同样回退本地合成树（回退必须透明）
                return self._build_local_tree(smiles, max_depth, num_routes)
            except SynthesisServiceError:
                # ASKCOS/InternLM 不可用时回退到本地合成树（v4.0 回退链要求）
                return self._build_local_tree(smiles, max_depth, num_routes)
        # 已在事件循环中（如 FastAPI async 端点），使用同步本地回退
        return self._build_local_tree(smiles, max_depth, num_routes)

    def check_feasibility(self, smiles: str) -> float:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop is not None:
            # 同步调用方无法 await，直接用本地回退
            return self._check_feasibility_sync(smiles)
        try:
            return asyncio.run(self.check_feasibility_async(smiles))
        except SynthesisServiceError:
            # ASKCOS 不可用时回退到本地评估
            return self._check_feasibility_sync(smiles)

    def _check_feasibility_sync(self, smiles: str) -> float:
        """同步回退：使用本地合成树评估"""
        routes = self._build_local_tree(smiles, max_depth=2, num_routes=3)
        if not routes:
            return 0.0
        return max(r.feasibility_score for r in routes)

    def filter_synthesizable(self, candidates: list[str], threshold: float = 0.3) -> list[str]:
        return [s for s in candidates if self.check_feasibility(s) >= threshold]

    def score_candidates(self, candidates: list[str]) -> list[tuple[str, float]]:
        scored = [(s, self.check_feasibility(s)) for s in candidates]
        return sorted(scored, key=lambda x: x[1], reverse=True)

    def _parse_tree(self, tree: dict, depth: int = 0) -> list[RouteStep]:
        steps = []
        # ASKCOS 格式：is_reaction 标记反应节点，smiles 为 "reactant>>product"
        if tree.get("is_reaction"):
            rxn_smiles = tree.get("smiles", "")
            reactants_str, _, products_str = rxn_smiles.partition(">>")
            steps.append(RouteStep(
                reaction_smiles=rxn_smiles,
                reactants=[reactants_str] if reactants_str else [],
                products=[products_str] if products_str else [],
                conditions=tree.get("necessary_reagent", ""),
                score=tree.get("plausibility", tree.get("template_score", 0)),
                template_score=tree.get("template_score", 0),
                reaction_type="retrosynthesis",
            ))
        # 兼容旧格式：reaction 子键
        elif "reaction" in tree:
            rxn = tree["reaction"]
            steps.append(RouteStep(
                reaction_smiles=rxn.get("smiles", ""),
                reactants=rxn.get("reactants", []),
                products=rxn.get("products", []),
                conditions=rxn.get("conditions", ""),
                score=rxn.get("score", 0),
            ))
        for child in tree.get("children", []):
            steps.extend(self._parse_tree(child, depth + 1))
        return steps

    def _extract_tree_score(self, tree: dict) -> float:
        """从 ASKCOS 树中提取最大 plausibility 作为路径评分。"""
        best = 0.0
        if tree.get("is_reaction"):
            best = max(best, float(tree.get("plausibility", 0)))
        for child in tree.get("children", []):
            best = max(best, self._extract_tree_score(child))
        return best

    def _build_local_tree(self, smiles: str, max_depth: int, num_routes: int) -> list[SynthesisRoute]:
        routes = []
        fragments = self._fragment_molecule(smiles)

        for frag_set in fragments[:num_routes]:
            # 过滤无效片段并去重
            reactants = []
            seen = set()
            for frag in frag_set:
                if frag and frag not in seen:
                    reactants.append(frag)
                    seen.add(frag)
            if not reactants:
                continue

            # 元素组成校验：反应物不能包含目标分子中没有的元素
            if not self._validate_elements(smiles, reactants):
                continue

            reaction_type = self._classify_reaction(reactants[0])
            known = self.KNOWN_REACTIONS.get(reaction_type, {})
            rxn_smiles = f"{'.'.join(reactants)}>>{smiles}"
            score = known.get("score", 0.5)
            routes.append(SynthesisRoute(
                target_smiles=smiles,
                steps=[RouteStep(
                    reaction_smiles=rxn_smiles,
                    reactants=reactants,
                    products=[smiles],
                    conditions=known.get("reagents", "standard conditions"),
                    score=score,
                    reaction_type=reaction_type,
                )],
                num_steps=1,
                overall_score=score,
                feasibility_score=score,
                is_feasible=score > 0.3,
                confidence=score * 0.8,
                source="local_template",
            ))

        return routes

    def _fragment_molecule(self, smiles: str) -> list[list[str]]:
        """生成目标分子的候选片段集合，优先使用 RDKit 进行化学上合理的键断裂。

        返回多个片段集合，每个集合可作为一条本地回退合成路线的反应物。
        """
        fragments = []

        # 1. 尝试使用 RDKit 断裂非环单键生成真实 SMILES 片段
        try:
            from rdkit import Chem
            from rdkit.Chem import BRICS

            mol = Chem.MolFromSmiles(smiles)
            if mol is not None:
                # BRICS 分解可得到合成上合理的片段
                brics = list(BRICS.BRICSDecompose(mol))
                if len(brics) >= 2:
                    fragments.append(sorted(brics))

                # 额外尝试断裂 C-C / C-O / C-N 单键
                bond_break_fragments = self._break_single_bonds(mol, smiles)
                if bond_break_fragments:
                    fragments.extend(bond_break_fragments)
        except Exception:
            pass

        # 2. RDKit 不可用或无法分解时，回退到字符串分段
        if not fragments:
            n = len(smiles)
            fragments.append([smiles[:max(1, n // 2)], smiles[max(1, n // 2):]])
            fragments.append([
                smiles[:max(1, n // 3)],
                smiles[max(1, n // 3):max(1, 2 * n // 3)],
                smiles[max(1, 2 * n // 3):],
            ])

        return fragments

    def _break_single_bonds(self, mol, parent_smiles: str) -> list[list[str]]:
        """使用 RDKit 断裂非环 C-C / C-O / C-N 单键，返回若干片段集合。"""
        from rdkit import Chem

        results = []
        bonds_to_break = []
        for bond in mol.GetBonds():
            if bond.IsInRing():
                continue
            if bond.GetBondType() != Chem.BondType.SINGLE:
                continue
            a1, a2 = bond.GetBeginAtom(), bond.GetEndAtom()
            # 只考虑重原子之间的键，避免断裂 C-H
            if a1.GetAtomicNum() <= 1 or a2.GetAtomicNum() <= 1:
                continue
            # 优先断裂 C-C / C-O / C-N
            pair = tuple(sorted([a1.GetAtomicNum(), a2.GetAtomicNum()]))
            if pair in {(6, 6), (6, 7), (6, 8)}:
                bonds_to_break.append(bond.GetIdx())

        # 为避免组合爆炸，最多断裂前 3 条候选键
        for bond_idx in bonds_to_break[:3]:
            try:
                fragmented = Chem.FragmentOnBonds(mol, [bond_idx], addDummies=False)
                frags = Chem.GetMolFrags(fragmented, asMols=True, sanitizeFrags=True)
                frag_smiles = [Chem.MolToSmiles(f) for f in frags]
                if len(frag_smiles) >= 2:
                    results.append(sorted(frag_smiles))
            except Exception:
                continue

        return results

    def _classify_reaction(self, fragment: str) -> str:
        if "=" in fragment and "O" in fragment:
            return "esterification"
        if "c1" in fragment:
            return "suzuki"
        if "N" in fragment and "C" in fragment:
            return "amide_formation"
        if "S" in fragment:
            return "sulfonation"
        if "P" in fragment:
            return "phosphorylation"
        if "O" in fragment:
            return "oxidation"
        return "nucleophilic_sub"

    @staticmethod
    def _validate_elements(target_smiles: str, reactants: list[str]) -> bool:
        """验证反应物元素组成与目标分子一致。"""
        try:
            from rdkit import Chem
            target_mol = Chem.MolFromSmiles(target_smiles)
            if target_mol is None:
                return True
            target_elements = set(atom.GetSymbol() for atom in target_mol.GetAtoms())

            for reactant in reactants:
                reactant_mol = Chem.MolFromSmiles(reactant)
                if reactant_mol is None:
                    continue
                reactant_elements = set(atom.GetSymbol() for atom in reactant_mol.GetAtoms())
                extra = reactant_elements - target_elements
                if extra:
                    return False
            return True
        except ImportError:
            return True

    # ===================================================================
    # E1: 多路径并行探索
    # ===================================================================

    async def plan_multiple_routes(
        self,
        smiles: str,
        num_routes: int = 3,
        engine_type: str | None = None,
        material_type: str = "molecule",
        formula: str = "",
        space_group: str = "",
    ) -> dict:
        """规划合成路线，按 material_type 路由到不同引擎。

        - molecule：并行调用 ASKCOS/InternLM 多次（不同搜索深度），返回去重后的多条候选路线
        - crystal：调用 InternLM 生成固相合成路线（高温固相/溶胶凝胶/水热等）

        返回 dict：
        - molecule: {routes: [...], count, best_route}
        - crystal:  {routes: [...], count, best_route, agent_info, reasoning, engine, material_type}
        """
        if material_type == "crystal":
            if not formula or not formula.strip():
                raise ValueError("晶体合成路线规划需要化学式 formula")
            routes, meta = await self._plan_crystal_with_internlm(
                formula=formula.strip(),
                space_group=space_group or "",
                num_routes=num_routes,
            )
            deduped = sorted(routes, key=lambda r: r.feasibility_score, reverse=True)[:num_routes]
            route_dicts = [self._route_to_dict(r, idx) for idx, r in enumerate(deduped)]
            return {
                "routes": route_dicts,
                "count": len(route_dicts),
                "best_route": route_dicts[0] if route_dicts else None,
                "engine": "internlm",
                "used_local_fallback": False,
                **meta,
            }

        # 分子路径：保留原多深度并行逻辑
        if not smiles:
            raise ValueError("SMILES string is required")

        # 不同搜索深度并行探索，获得结构多样化的路径
        depths = [2, 3, 4]
        results = await asyncio.gather(
            *[self.plan_synthesis_async(smiles, max_depth=d, num_routes=num_routes, engine_type=engine_type) for d in depths],
            return_exceptions=True,
        )

        all_routes: list[SynthesisRoute] = []
        last_error: Exception | None = None
        used_local_fallback = False
        for r in results:
            if isinstance(r, Exception):
                last_error = r
                continue
            all_routes.extend(r)

        # 全部失败时回退到本地合成树（保证功能可用性）——必须显式标记来源
        if not all_routes:
            for d in depths:
                all_routes.extend(self._build_local_tree(smiles, max_depth=d, num_routes=num_routes))
            used_local_fallback = True

        # 去重：以反应物集合为指纹，相似路径只保留评分最高的一条
        seen: dict[frozenset, SynthesisRoute] = {}
        for route in all_routes:
            key = frozenset(r for s in route.steps for r in s.reactants) or frozenset({route.target_smiles})
            existing = seen.get(key)
            if existing is None or route.feasibility_score > existing.feasibility_score:
                seen[key] = route

        deduped = sorted(seen.values(), key=lambda r: r.feasibility_score, reverse=True)[:num_routes]
        route_dicts = [self._route_to_dict(r, idx) for idx, r in enumerate(deduped)]
        # AI 透明性：标记实际使用的引擎与是否发生本地模板回退
        engines = sorted({r.source for r in deduped if r.source})
        return {
            "routes": route_dicts,
            "count": len(route_dicts),
            "best_route": route_dicts[0] if route_dicts else None,
            "engine": ",".join(engines) if engines else (engine_type or "askcos"),
            "used_local_fallback": used_local_fallback,
            "last_error": str(last_error)[:200] if last_error else "",
        }

    def _route_to_dict(self, route: SynthesisRoute, idx: int) -> dict:
        """将 SynthesisRoute 序列化为带额外聚合字段的 dict。"""
        reactants = sorted({r for s in route.steps for r in s.reactants})
        conditions = [s.conditions for s in route.steps if s.conditions]
        return {
            "route_id": f"R{idx + 1}",
            "target_smiles": route.target_smiles,
            "steps": [s.model_dump() for s in route.steps],
            "feasibility_score": route.feasibility_score,
            "step_count": route.num_steps or len(route.steps),
            "confidence": route.confidence,
            "reactants": reactants,
            "conditions": conditions,
            "is_feasible": route.is_feasible,
            "overall_score": route.overall_score,
            "estimated_cost": self._estimate_cost(route),
            "source": route.source,
        }

    def _estimate_cost(self, route: SynthesisRoute) -> float:
        """基于步骤数与反应难度估算综合成本（相对值）。"""
        if not route.steps:
            return 0.0
        difficulty_weight = {"easy": 1.0, "medium": 1.5, "hard": 2.5}
        cost = sum(difficulty_weight.get(s.difficulty, 1.5) for s in route.steps)
        return round(cost, 2)

    # ===================================================================
    # E2: 反应机理网络解析
    # ===================================================================

    MECHANISM_MAP = {
        "esterification": "substitution",
        "grignard": "addition",
        "suzuki": "other",
        "wittig": "addition",
        "reduction": "reduction",
        "oxidation": "oxidation",
        "nucleophilic_sub": "substitution",
        "amide_formation": "substitution",
        "sulfonation": "substitution",
        "phosphorylation": "substitution",
        "retrosynthesis": "other",
    }

    def _infer_mechanism(self, reaction_type: str) -> str:
        return self.MECHANISM_MAP.get(reaction_type, "other")

    async def build_reaction_network(self, smiles: str) -> dict:
        """基于 ASKCOS 合成树提取中间体与反应节点，构建反应机理网络。

        返回 {nodes: [{id, label, type, mechanism}], edges: [{source, target, label, mechanism, is_byproduct}], target}。
        type: starting_material / intermediate / product / byproduct
        mechanism: substitution / elimination / addition / oxidation / reduction / other
        """
        if not smiles:
            raise ValueError("SMILES string is required")

        routes: list[SynthesisRoute] = []
        try:
            routes = await self.plan_synthesis_async(smiles, max_depth=3, num_routes=3)
        except Exception:
            logger.warning("ASKCOS 网络解析失败，切换到本地回退")

        # ASKCOS 返回空结果时，使用本地合成树兜底
        if not routes:
            routes = self._build_local_tree(smiles, max_depth=3, num_routes=3)

        # 本地树也为空时，至少展示目标分子节点
        if not routes:
            return {
                "nodes": [{
                    "id": smiles,
                    "label": smiles if len(smiles) <= 24 else smiles[:21] + "...",
                    "type": "product",
                    "mechanism": "other",
                }],
                "edges": [],
                "target": smiles,
            }

        nodes_map: dict[str, dict] = {}
        edges: list[dict] = []
        all_reactants: set[str] = set()
        all_products: set[str] = set()

        for route in routes:
            for step in route.steps:
                all_reactants.update(step.reactants)
                all_products.update(step.products)

        target = smiles

        def get_or_create(smiles_str: str, default_type: str) -> dict:
            if smiles_str not in nodes_map:
                label = smiles_str if len(smiles_str) <= 24 else smiles_str[:21] + "..."
                nodes_map[smiles_str] = {
                    "id": smiles_str,
                    "label": label,
                    "type": default_type,
                    "mechanism": "other",
                }
            return nodes_map[smiles_str]

        for route in routes:
            for step in route.steps:
                mechanism = self._infer_mechanism(step.reaction_type)
                for product in step.products:
                    node = get_or_create(product, "intermediate")
                    if product == target:
                        node["type"] = "product"
                    elif product in all_reactants:
                        node["type"] = "intermediate"
                    else:
                        node["type"] = "byproduct"
                    if product != target:
                        node["mechanism"] = mechanism
                for reactant in step.reactants:
                    node = get_or_create(reactant, "starting_material")
                    if reactant in all_products and reactant != target:
                        node["type"] = "intermediate"
                # 构建边
                for reactant in step.reactants:
                    for product in step.products:
                        edge = {
                            "source": reactant,
                            "target": product,
                            "label": step.reaction_type or "reaction",
                            "mechanism": mechanism,
                            "is_byproduct": product != target and product not in all_reactants,
                        }
                        if edge not in edges:
                            edges.append(edge)

        return {
            "nodes": list(nodes_map.values()),
            "edges": edges,
            "target": target,
        }

    # ===================================================================
    # E3: DFT 可行性校验联动
    # ===================================================================

    # 反应类型 → 典型能量变化（kcal/mol，负值表示放热）
    REACTION_ENERGY = {
        "esterification": -5.0,
        "grignard": -25.0,
        "suzuki": -15.0,
        "wittig": -10.0,
        "reduction": -20.0,
        "oxidation": -15.0,
        "nucleophilic_sub": -12.0,
        "amide_formation": -8.0,
        "sulfonation": -18.0,
        "phosphorylation": -10.0,
        "retrosynthesis": -5.0,
    }

    def _estimate_energy_change(self, reaction_type: str, step: dict) -> float:
        """基于反应类型模板化估算能量变化（简化 DFT 替代）。"""
        import hashlib
        base = self.REACTION_ENERGY.get(reaction_type, -5.0)
        # 基于 SMILES 哈希添加确定性扰动，模拟分子结构差异对能量的影响
        rxn_key = step.get("reaction_smiles", "") or str(step.get("reactants", []))
        h = int(hashlib.md5(rxn_key.encode()).hexdigest()[:4], 16)
        perturbation = (h % 100 - 50) / 10.0  # -5.0 ~ +5.0
        return base + perturbation

    async def verify_with_dft(self, route: dict) -> dict:
        """对合成路线关键步骤进行 DFT 校验（模板化简化逻辑）。

        返回 {route_id, step_results, overall_status, original_confidence, adjusted_confidence, method}。
        能量变化不合理（吸热过大）的步骤会降低路线置信度。
        """
        steps = route.get("steps", [])
        step_results = []
        all_pass = True

        for idx, step in enumerate(steps):
            reaction_type = step.get("reaction_type", "other")
            energy_change = self._estimate_energy_change(reaction_type, step)
            # 吸热超过 10 kcal/mol 判定为不合理
            passed = energy_change < 10.0
            if not passed:
                all_pass = False
            step_results.append({
                "step_idx": idx,
                "reaction_type": reaction_type,
                "status": "passed" if passed else "failed",
                "energy_change": round(energy_change, 2),
                "unit": "kcal/mol",
                "reactants": step.get("reactants", []),
                "products": step.get("products", []),
            })

        # E3.2: DFT 结果回写至置信度评分
        original_confidence = float(route.get("confidence", 0.5))
        if all_pass:
            adjusted_confidence = min(1.0, original_confidence * 1.05)
        else:
            failed_ratio = sum(1 for r in step_results if r["status"] == "failed") / max(len(step_results), 1)
            adjusted_confidence = original_confidence * (1.0 - 0.4 * failed_ratio)

        return {
            "route_id": route.get("route_id", ""),
            "step_results": step_results,
            "overall_status": "passed" if all_pass else "failed",
            "original_confidence": round(original_confidence, 4),
            "adjusted_confidence": round(adjusted_confidence, 4),
            "method": "template-based DFT estimate",
        }

    def close(self):
        """同步关闭：仅标记客户端为关闭，异步资源需通过 close_async 释放。"""
        if self._async_client is not None and not self._async_client.is_closed:
            # httpx.AsyncClient 没有同步 close，只能触发底层 transport 关闭
            try:
                # 在事件循环外调用 sync close 会抛错，此处仅做最佳努力
                self._async_client.close()
            except Exception:
                pass

    async def close_async(self):
        """异步关闭连接池"""
        if self._async_client is not None and not self._async_client.is_closed:
            await self._async_client.aclose()
            self._async_client = None
