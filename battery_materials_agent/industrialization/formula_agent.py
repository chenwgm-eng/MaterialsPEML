"""Formula and process design agent for polymer electrolyte industrialization."""

from __future__ import annotations

from pydantic import BaseModel, Field
import asyncio
import json
import logging

import httpx

from ..config import AgentConfig, EngineMode
from ..llm.schemas import ChatMessage, ChatRequest, ChatResponse
from .raw_material_db import RawMaterialDB

logger = logging.getLogger(__name__)

# 配方 LLM 调用整体超时（秒），需小于前端 axios 默认超时 15s，避免浏览器先取消请求
FORMULA_LLM_TIMEOUT = 12.0


class RecipeProcess(BaseModel):
    bom: dict = Field(default_factory=dict)       # 物料清单：{物料名: 质量比}
    bop: list[dict] = Field(default_factory=list)  # 工艺路线：[{"step": "混料", "temperature": 25, "duration_min": 60, "rpm": 1500}]
    equipment: str = ""                            # 所需设备
    provenance: list[dict] = Field(default_factory=list)


class FormulaAgent:
    """Design battery electrolyte recipe (BOM) and process (BOP) via LLM with rule-based fallback."""

    def __init__(self, raw_material_db: RawMaterialDB, config: AgentConfig | None = None, llm_provider = None):
        self.db = raw_material_db
        self.config = config  # AgentConfig 或 None
        self._llm_provider = llm_provider

    async def design_recipe(self, target_material: dict) -> RecipeProcess:
        if self.config is None:
            return self._fallback_recipe(target_material)

        # 查找目标材料是否已在物料库中
        candidate_name = target_material.get("candidate", "")
        target_spec = self._find_target_in_db(candidate_name)

        available_polymers = self.db.query_category("BASE_POLYMER")
        available_salts = self.db.query_category("LITHIUM_SALT")

        polymers_str = ", ".join(f"{p.name}({p.material_id})" for p in available_polymers) or "无"
        salts_str = ", ".join(f"{s.name}({s.material_id})" for s in available_salts) or "无"
        target_str = target_spec.name if target_spec else candidate_name or "未指定"

        prompt = f"""你是一个资深的电池材料配方与工艺架构师。
当前需要制备目标材料：{target_str}。

请严格从以下企业现有物料库中选择原材料（不允许编造物料）：
- 基材：{polymers_str}
- 锂盐：{salts_str}
{f"- 目标材料本身：{target_spec.name}({target_spec.material_id})" if target_spec else ""}

请输出工业级试产指导书，必须包含：
1. BOM (物料清单及质量占比%)
2. BOP (工艺参数：混料温度、搅拌转速RPM、涂布厚度、烘烤真空度与时间)

以 JSON 格式返回，格式：{{"bom": {{"物料名": 比例}}, "bop": [{{"step": "...", "temperature": 25, "duration_min": 60, "rpm": 1500}}], "equipment": "..."}}"""

        try:
            content = await self._call_llm(prompt)
            json_str = self._extract_json(content)
            data = json.loads(json_str)
            return RecipeProcess(
                bom=data.get("bom", {}),
                bop=data.get("bop", []),
                equipment=data.get("equipment", ""),
            )
        except Exception as e:
            logger.warning("LLM recipe design failed, falling back: %s", e)
            return self._fallback_recipe(target_material)

    async def _call_llm(self, prompt: str) -> str:
        """调用配方 LLM，带整体超时和响应结构容错。"""
        if self.config.engine_mode == EngineMode.INTERNLM:
            provider = self._llm_provider
            provider_created_locally = False
            if provider is None:
                from ..llm.factory import ProviderFactory
                provider = ProviderFactory.create(self.config)
                provider_created_locally = True
            try:
                request = ChatRequest(
                    model=self.config.internlm.model,
                    messages=[
                        ChatMessage(role="user", content=prompt),
                    ],
                    temperature=0.7,
                    max_tokens=4096,
                )
                response = await asyncio.wait_for(
                    provider.complete(request),
                    timeout=FORMULA_LLM_TIMEOUT,
                )
                return response.content
            finally:
                if provider_created_locally:
                    close_fn = getattr(provider, "close", None)
                    if close_fn is not None:
                        try:
                            await close_fn()
                        except Exception as close_err:
                            logger.warning("Failed to close temporary LLM provider: %s", close_err)
        else:
            llm = self.config.llm
            base_url = llm.base_url.rstrip("/")
            if "/v1" not in base_url:
                endpoint = f"{base_url}/v1/chat/completions"
            else:
                endpoint = f"{base_url}/chat/completions"
            response_max_tokens = min(2000, llm.max_tokens)
            async with httpx.AsyncClient(timeout=60) as client:
                response = await asyncio.wait_for(
                    client.post(
                        endpoint,
                        headers={"Authorization": f"Bearer {llm.api_key}"},
                        json={
                            "model": llm.model,
                            "messages": [
                                {"role": "system", "content": "You are a battery materials formulation and process architect."},
                                {"role": "user", "content": prompt},
                            ],
                            "temperature": llm.temperature,
                            "max_tokens": response_max_tokens,
                        },
                    ),
                    timeout=FORMULA_LLM_TIMEOUT,
                )
                response.raise_for_status()
        return self._extract_message_content(response.json())

    def _extract_message_content(self, data: dict) -> str:
        """从容错的 OpenAI 风格响应中提取 content，结构异常时抛出。"""
        choices = data.get("choices") if isinstance(data, dict) else None
        if not choices:
            raise ValueError("LLM response missing choices")
        message = choices[0].get("message") if choices else None
        content = message.get("content") if isinstance(message, dict) else None
        if not content or not isinstance(content, str):
            raise ValueError("LLM response missing content")
        return content

    def _extract_json(self, text: str) -> str:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end < start:
            return ""
        return text[start:end + 1]

    def _find_target_in_db(self, candidate: str):
        """在物料库中查找目标材料：按 material_id → 名称精确 → 名称模糊。"""
        if not candidate:
            return None
        # 按 material_id 查找
        spec = self.db.get_spec(candidate)
        if spec:
            return spec
        # 按名称查找
        for s in self.db.get_all():
            if s.name.lower() == candidate.lower():
                return s
        # 模糊匹配
        for s in self.db.get_all():
            if candidate.lower() in s.name.lower() or s.name.lower() in candidate.lower():
                return s
        return None

    def _fallback_recipe(self, target_material: dict) -> RecipeProcess:
        candidate_name = target_material.get("candidate", "")
        target_spec = self._find_target_in_db(candidate_name)

        # 目标材料在物料库中 → 以目标材料为主体生成配方
        if target_spec:
            return self._recipe_for_known_target(target_spec)

        # 目标不在物料库 → 按聚合物电解质模板生成
        available_polymers = self.db.query_category("BASE_POLYMER")
        available_salts = self.db.query_category("LITHIUM_SALT")

        if not available_polymers or not available_salts:
            return RecipeProcess()

        polymer = available_polymers[0]
        salt = available_salts[0]

        return RecipeProcess(
            bom={polymer.material_id: 0.8, salt.material_id: 0.2},
            bop=[
                {"step": "混料", "temperature": 25, "duration_min": 60, "rpm": 1500, "equipment": "双行星搅拌机"},
                {"step": "涂布", "temperature": 25, "duration_min": 30, "rpm": 0, "equipment": "涂布机"},
                {"step": "烘烤", "temperature": 80, "duration_min": 720, "rpm": 0, "equipment": "真空烘箱"},
            ],
            equipment="双行星搅拌机",
        )

    def _recipe_for_known_target(self, target_spec) -> RecipeProcess:
        """目标材料在物料库中：以目标材料为主成分，辅以适量添加剂/粘结剂。"""
        bom = {target_spec.material_id: 0.9}

        # 根据目标材料类别选择辅料
        fillers = self.db.query_category("FILLER")
        binders = self.db.query_category("BINDER")
        polymers = self.db.query_category("BASE_POLYMER")

        # 聚合物基电解质：补加锂盐
        if target_spec.category == "BASE_POLYMER":
            salts = self.db.query_category("LITHIUM_SALT")
            if salts:
                bom[salts[0].material_id] = 0.1
            bop = [
                {"step": "混料", "temperature": 25, "duration_min": 60, "rpm": 1500, "equipment": "双行星搅拌机"},
                {"step": "涂布", "temperature": 25, "duration_min": 30, "rpm": 0, "equipment": "涂布机"},
                {"step": "烘烤", "temperature": 80, "duration_min": 720, "rpm": 0, "equipment": "真空烘箱"},
            ]
            equipment = "双行星搅拌机"
        else:
            # 无机/硫化物电解质：补加粘结剂，采用粉末冶金工艺
            if binders:
                bom[binders[0].material_id] = 0.05
            if fillers:
                bom[fillers[0].material_id] = 0.05
            bop = [
                {"step": "球磨混料", "temperature": 25, "duration_min": 120, "rpm": 300, "equipment": "球磨机"},
                {"step": "冷压成型", "temperature": 25, "duration_min": 30, "rpm": 0, "equipment": "粉末压片机"},
                {"step": "烧结", "temperature": 500, "duration_min": 600, "rpm": 0, "equipment": "管式炉"},
            ]
            equipment = "球磨机"

        return RecipeProcess(bom=bom, bop=bop, equipment=equipment)
