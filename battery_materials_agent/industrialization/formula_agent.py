"""Formula and process design agent for material industrialization.

基于领域包（Domain Pack）生成配方（BOM）与工艺（BOP）。配方模板、工艺步骤、
回退配方均从领域包读取，不再硬编码聚合物/粉末冶金分支，从而支持未来各类
新材料场景（生物材料/纤维/涂层等）通过新增领域包即可接入。
"""

from __future__ import annotations

from pydantic import BaseModel, Field
import asyncio
import json
import logging

import httpx

from ..config import AgentConfig, EngineMode
from ..llm.schemas import ChatMessage, ChatRequest
from .raw_material_db import RawMaterialDB
from .domain_pack_store import DomainPackStore

logger = logging.getLogger(__name__)

# 配方 LLM 调用整体超时（秒），需小于前端 axios 默认超时 15s，避免浏览器先取消请求
FORMULA_LLM_TIMEOUT = 12.0


class RecipeProcess(BaseModel):
    bom: dict = Field(default_factory=dict)       # 物料清单：{物料名: 质量比}
    bop: list[dict] = Field(default_factory=list)  # 工艺路线：[{"step": "混料", "temperature": 25, "duration_min": 60, "rpm": 1500}]
    equipment: str = ""                            # 所需设备
    provenance: list[dict] = Field(default_factory=list)


class FormulaAgent:
    """按领域包生成配方（BOM）与工艺（BOP），LLM 生成 + 规则模板回退。"""

    def __init__(
        self,
        raw_material_db: RawMaterialDB,
        config: AgentConfig | None = None,
        llm_provider=None,
        domain_pack: dict | None = None,
    ):
        self.db = raw_material_db
        self.config = config  # AgentConfig 或 None
        self._llm_provider = llm_provider
        # 领域包数据（配方模板/回退配方/一致性规则）。未显式传入时，从库解析活跃领域包；
        # 库不可用或为空时回退到内置默认电池领域包，保证旧行为不回归。
        if domain_pack is None:
            try:
                store = DomainPackStore()
                active = store.resolve_active_pack()
                domain_pack = active.data if active else None
            except Exception as exc:
                logger.warning("解析活跃领域包失败，回退内置默认: %s", exc)
                domain_pack = None
        self.domain_pack = domain_pack or DomainPackStore.builtin_fallback()

    # ---- 领域包工具 ----
    def _recipe_template_for(self, material_type: str) -> dict | None:
        """按材料类型选取配方模板；未命中时回退到 "*" 默认模板。"""
        templates = self.domain_pack.get("recipe_templates") or []
        for tpl in templates:
            if tpl.get("material_type") == material_type:
                return tpl
        for tpl in templates:
            if tpl.get("material_type") == "*":
                return tpl
        return None

    def _all_categories(self) -> list[str]:
        """收集领域包中引用的全部物料分类（用于 LLM 提示词枚举可选原料）。"""
        cats: list[str] = []
        for tpl in self.domain_pack.get("recipe_templates") or []:
            if tpl.get("material_type") and tpl.get("material_type") != "*":
                cats.append(tpl["material_type"])
            for add in tpl.get("additives") or []:
                if add.get("category"):
                    cats.append(add["category"])
        return list(dict.fromkeys(cats))

    async def design_recipe(self, target_material: dict) -> RecipeProcess:
        if self.config is None:
            return self._fallback_recipe(target_material)

        # 查找目标材料是否已在物料库中
        candidate_name = target_material.get("candidate", "")
        target_spec = self._find_target_in_db(candidate_name)

        category_lines = []
        for category in self._all_categories():
            specs = self.db.query_category(category)
            if specs:
                item_str = ", ".join(f"{s.name}({s.material_id})" for s in specs)
                category_lines.append(f"- {category}：{item_str}")
        material_pool_str = "\n".join(category_lines) or "（物料库为空）"
        target_str = target_spec.name if target_spec else candidate_name or "未指定"

        prompt = f"""你是一名材料配方与工艺架构师。
当前需要制备目标材料：{target_str}。

请严格从以下企业现有物料库中选择原材料（不允许编造物料）：
{material_pool_str}
{f"- 目标材料本身：{target_spec.name}({target_spec.material_id})" if target_spec else ""}

请输出工业级试产指导书，必须包含：
1. BOM (物料清单及质量占比%)
2. BOP (工艺参数：温度、时间、转速RPM 等)

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

        # 目标材料在物料库中 → 以目标材料为主成分生成配方
        if target_spec:
            return self._recipe_for_known_target(target_spec)

        # 目标不在物料库 → 按领域包回退配方生成（按分类取首个物料填充）
        fb = self.domain_pack.get("fallback_recipe") or {}
        bom: dict = {}
        for category, ratio in (fb.get("bom") or {}).items():
            specs = self.db.query_category(category)
            if specs:
                bom[specs[0].material_id] = float(ratio)
        if not bom:
            return RecipeProcess()
        return RecipeProcess(
            bom=bom,
            bop=fb.get("bop") or [],
            equipment=fb.get("equipment") or "",
        )

    def _recipe_for_known_target(self, target_spec) -> RecipeProcess:
        """目标材料在物料库中：按领域包内对应材料类型的配方模板生成 BOM/BOP。"""
        tpl = self._recipe_template_for(target_spec.category)
        if not tpl:
            return RecipeProcess()

        bom = {target_spec.material_id: float(tpl.get("main_ratio", 0.9))}
        for add in tpl.get("additives") or []:
            category = add.get("category")
            ratio = add.get("ratio", 0.0)
            if not category:
                continue
            specs = self.db.query_category(category)
            if specs:
                bom[specs[0].material_id] = float(ratio)

        return RecipeProcess(
            bom=bom,
            bop=tpl.get("bop") or [],
            equipment=tpl.get("equipment") or "",
        )
