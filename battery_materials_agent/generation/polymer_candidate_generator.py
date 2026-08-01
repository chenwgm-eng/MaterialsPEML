"""Polymer candidate generation using LLM APIs and rule-based molecular design."""

from __future__ import annotations
from pydantic import BaseModel, Field
import asyncio
import json
import hashlib
import uuid
import logging

import httpx

from ..config import AgentConfig, EngineMode, LLMConfig, InternLMConfig
from ..llm.schemas import ChatMessage, ChatRequest, ChatResponse

logger = logging.getLogger(__name__)

# 聚合物 LLM 生成调用整体超时（秒），需小于前端 axios 默认 15s
POLYMER_LLM_TIMEOUT = 10.0


class PolymerCandidate(BaseModel):
    candidate_id: str = Field(default_factory=lambda: f"CAND-{uuid.uuid4().hex[:8].upper()}")
    name: str
    psmiles: str = ""
    smiles: str = ""
    monomer_smiles: list[str] = Field(default_factory=list)
    source: str = ""
    description: str = ""
    predicted_ionic_conductivity: float = 0.0
    molecular_weight: float = 0.0
    multi_objective_score: float = 0.0  # 多目标加权综合评分（0-1）
    provenance: list[dict] = Field(default_factory=list)


# 聚合物属性提取器与方向（与晶体保持一致语义，仅支持可计算字段）
_POLY_PROPERTY_GETTERS = {
    "ionic_conductivity": lambda c: c.predicted_ionic_conductivity,
    "molecular_weight": lambda c: c.molecular_weight,
}
_POLY_PROPERTY_DIRECTION = {
    "ionic_conductivity": "maximize",
    "molecular_weight": "minimize",  # 通常希望分子量适中偏小以利加工
}


def _apply_polymer_multi_objective(
    candidates: list[PolymerCandidate],
    target_properties: list[dict],
) -> list[PolymerCandidate]:
    """聚合物多目标加权评分（与晶体 _apply_multi_objective 同算法）。"""
    if not candidates:
        return candidates

    configs = []
    for tp in target_properties:
        prop = tp.get("property") or tp.get("target_property") or ""
        if not prop or prop not in _POLY_PROPERTY_GETTERS:
            continue
        weight = float(tp.get("weight", 1.0))
        direction = tp.get("direction") or _POLY_PROPERTY_DIRECTION.get(prop, "maximize")
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
            val = _POLY_PROPERTY_GETTERS[cfg["property"]](c)
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

    # 2. min-max 归一化 + 加权求和
    total_weight = sum(cfg["weight"] for cfg in configs) or 1.0
    for cfg in configs:
        vals = [_POLY_PROPERTY_GETTERS[cfg["property"]](c) for c in filtered]
        v_min, v_max = min(vals), max(vals)
        rng = v_max - v_min if v_max > v_min else 1.0
        for c, v in zip(filtered, vals):
            normalized = (v - v_min) / rng
            if cfg["direction"] == "minimize":
                normalized = 1.0 - normalized
            c.multi_objective_score += (cfg["weight"] / total_weight) * normalized

    filtered.sort(key=lambda c: c.multi_objective_score, reverse=True)
    return filtered


class PolymerDesignRules:
    """Rule-based polymer electrolyte design knowledge base."""

    BACKBONE_MOTIFS = [
        ("Poly(ethylene oxide)", "[*]CCO[*]", "CCO", "PEO", "High Li+ solvation via ether oxygen"),
        ("Poly(propylene oxide)", "[*]CC(C)O[*]", "CC(C)O", "PPO", "Methyl side chain reduces crystallinity"),
        ("Poly(vinyl alcohol)", "[*]CC(O)[*]", "CC(O)", "PVA", "Hydroxyl groups for H-bonding"),
        ("Poly(acrylonitrile)", "[*]CCC#N[*]", "C=CC#N", "PAN", "Nitrile group for high dielectric constant"),
        ("Poly(methyl methacrylate)", "[*]CC(C)(C(=O)OC)[*]", "CC(C)(C(=O)OC)", "PMMA", "Good mechanical stability"),
        ("Poly(vinylidene fluoride)", "[*]CC(F)(F)[*]", "C=C(F)F", "PVDF", "High dielectric constant, piezoelectric"),
        ("Poly(vinyl fluoride)", "[*]CCF[*]", "C=CF", "PVF", "Fluorinated backbone"),
        ("Poly(ethylene carbonate)", "[*]CCOC(=O)O[*]", "CCOC(=O)O", "PEC", "Cyclic carbonate for high conductivity"),
        ("Poly(propylene carbonate)", "[*]CC(C)OC(=O)O[*]", "CC(C)OC(=O)O", "PPC", "Biodegradable, good ion transport"),
        ("Poly(trimethylene carbonate)", "[*]CCCOC(=O)O[*]", "CCCOC(=O)O", "PTMC", "Flexible carbonate backbone"),
    ]

    SALT_ADDITIVES = [
        ("LiTFSI", "LiN(S(=O)(=O)C(F)(F)F)S(=O)(=O)C(F)(F)F", "Lithium bis(trifluoromethanesulfonyl)imide"),
        ("LiFSI", "LiN(S(=O)(=O)C(F)F)S(=O)(=O)C(F)F", "Lithium bis(fluorosulfonyl)imide"),
        ("LiClO4", "[Li+].[O-]Cl(=O)(=O)=O", "Lithium perchlorate"),
        ("LiBF4", "[Li+].[F-]B(F)(F)F", "Lithium tetrafluoroborate"),
        ("LiPF6", "[Li+].[F-]P(F)(F)(F)(F)F", "Lithium hexafluorophosphate"),
        ("LiBOB", "[Li+].[O-]C(=O)C1([O-])CCC1", "Lithium bis(oxalate)borate"),
    ]

    FILLER_MOTIFS = [
        ("LLZO", "Li7La3Zr2O12", "Garnet-type ceramic filler"),
        ("LATP", "Li1.3Al0.3Ti1.7(PO4)3", "NASICON-type filler"),
        ("LLTO", "La0.5Li0.5TiO3", "Perovskite-type filler"),
        ("SiO2", "O=[Si]=O", "Silica nanoparticle"),
        ("Al2O3", "O=[Al]O[Al]=O", "Alumina nanoparticle"),
    ]


class PolymerCandidateGenerator:
    """Generate polymer electrolyte candidates using LLM + rule-based design."""

    KNOWN_POLYMERS = [
        PolymerCandidate(
            name="Poly(ethylene oxide)", psmiles="Polymer([*]CCO[*])", smiles="CCO",
            monomer_smiles=["C(CO)O"], source="known",
            description="PEO-based SPE, widely studied for Li+ conduction",
            predicted_ionic_conductivity=1e-5,
        ),
        PolymerCandidate(
            name="Poly(vinylidene fluoride)", psmiles="Polymer([*]CC(F)(F)[*])", smiles="C=C(F)F",
            monomer_smiles=["C=C(F)F"], source="known",
            description="PVDF, high dielectric constant",
            predicted_ionic_conductivity=1e-7,
        ),
        PolymerCandidate(
            name="Poly(methyl methacrylate)", psmiles="Polymer([*]CC(C)(C(=O)OC)[*])", smiles="CC(C)(C(=O)OC)",
            monomer_smiles=["CC(C)(C(=O)OC)"], source="known",
            description="PMMA, good mechanical properties",
            predicted_ionic_conductivity=1e-8,
        ),
        PolymerCandidate(
            name="Polyacrylonitrile", psmiles="Polymer([*]CCC#N[*])", smiles="CC(C#N)",
            monomer_smiles=["C=CC#N"], source="known",
            description="PAN, good thermal stability",
            predicted_ionic_conductivity=1e-6,
        ),
        PolymerCandidate(
            name="Poly(propylene carbonate)", psmiles="Polymer([*]CC(C)OC(=O)O[*])", smiles="CC(C)OC(=O)O",
            monomer_smiles=["CC(C)OC(=O)O"], source="known",
            description="PPC, biodegradable SPE candidate",
            predicted_ionic_conductivity=5e-6,
        ),
    ]

    def __init__(
        self,
        config: AgentConfig | None = None,
        llm_api_key: str = "",
        llm_model: str = "LongCat-2.0",
        llm_base_url: str = "https://api.longcat.chat/openai",
        llm_max_tokens: int = 128000,
        llm_provider = None,
    ):
        # 保持旧的位置参数向后兼容：若第一个参数不是 AgentConfig 而是字符串 api_key
        if config is not None and not isinstance(config, AgentConfig):
            llm_api_key = config if isinstance(config, str) else llm_api_key
            config = None

        if config is None:
            config = AgentConfig(
                llm=LLMConfig(
                    api_key=llm_api_key,
                    model=llm_model,
                    base_url=llm_base_url,
                    max_tokens=llm_max_tokens,
                ),
                engine_mode=EngineMode.LEGACY,
            )

        self.config = config
        self._llm_provider = llm_provider
        # 为旧代码保留的属性（初始化后不再随热更新变化）
        self.llm_api_key = config.llm.api_key
        self.llm_model = config.llm.model
        self.llm_base_url = config.llm.base_url.rstrip("/")
        self.llm_max_tokens = config.llm.max_tokens
        self._rules = PolymerDesignRules()

    def generate(self, target_properties: dict | list | None = None,
                 num_candidates: int = 10) -> list[PolymerCandidate]:
        # 多目标列表形式：先生成候选，再应用加权评分
        multi_obj_list: list[dict] | None = None
        dict_props: dict | None = None
        if isinstance(target_properties, list):
            multi_obj_list = target_properties if target_properties else None
            # 同时构造一个 dict 形式传给 LLM 作上下文
            dict_props = {"properties": target_properties} if target_properties else None
        else:
            dict_props = target_properties

        if self.config.engine_mode == EngineMode.INTERNLM:
            try:
                candidates = self._run_llm_sync(self._generate_with_internlm_async, dict_props, num_candidates)
            except Exception as e:
                logger.warning("InternLM polymer generation failed: %s", e)
                candidates = []
        else:
            candidates = []

        if not candidates:
            candidates = list(self.KNOWN_POLYMERS)
            rule_based = self._generate_rule_based(num_candidates)
            candidates.extend(rule_based)
            if self.config.llm.api_key:
                try:
                    llm_generated = self._run_llm_sync(self._generate_with_llm_async, dict_props, num_candidates)
                    candidates.extend(llm_generated)
                except Exception as e:
                    logger.warning("LLM polymer generation failed: %s", e)

        seen = set()
        unique = []
        for c in candidates:
            key = c.psmiles or c.smiles
            if key not in seen:
                seen.add(key)
                unique.append(c)

        # 多目标加权评分（若启用）
        if multi_obj_list:
            unique = _apply_polymer_multi_objective(unique, multi_obj_list)

        return unique[:num_candidates]

    def _run_llm_sync(self, async_fn, *args):
        """在同步上下文中执行异步 LLM 调用，并强制整体超时。

        若当前已有运行中的事件循环（罕见），直接抛出异常交由上层回退。
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop is not None:
            raise RuntimeError("cannot run LLM call from a running event loop")
        return asyncio.run(asyncio.wait_for(async_fn(*args), timeout=POLYMER_LLM_TIMEOUT))

    def generate_derivatives(self, base_polymer: PolymerCandidate, num_variants: int = 5) -> list[PolymerCandidate]:
        variants = []
        modifications = [
            ("with LiTFSI salt", "LiTFSI"),
            ("with LLZO ceramic filler", "LLZO"),
            ("with LATP filler", "LATP"),
            ("with crosslinker", "crosslinked"),
            ("blended with PEO", "PEO blend"),
        ]
        for suffix, desc in modifications[:num_variants]:
            variants.append(PolymerCandidate(
                name=f"{base_polymer.name} {suffix}",
                psmiles=base_polymer.psmiles,
                smiles=base_polymer.smiles,
                monomer_smiles=list(base_polymer.monomer_smiles),
                source="derivative",
                description=f"{base_polymer.description} - {desc}",
                predicted_ionic_conductivity=base_polymer.predicted_ionic_conductivity * 2,
            ))
        return variants

    def filter_by_rules(self, candidates: list[PolymerCandidate], rules: dict) -> list[PolymerCandidate]:
        filtered = []
        for c in candidates:
            if rules.get("max_molecular_weight") and c.molecular_weight > rules["max_molecular_weight"]:
                continue
            if rules.get("required_groups"):
                has_group = any(g.lower() in c.smiles.lower() for g in rules["required_groups"])
                if not has_group and rules.get("require_all", False):
                    continue
            filtered.append(c)
        return filtered

    def _generate_rule_based(self, num_candidates: int) -> list[PolymerCandidate]:
        candidates = []
        h = int(hashlib.sha256(b"rule_based").hexdigest()[:8], 16)

        for i, (name, psmiles, smiles, abbr, desc) in enumerate(self._rules.BACKBONE_MOTIFS):
            if len(candidates) >= num_candidates:
                break
            conductivity = 1e-6 * (((h >> (i * 2)) & 3) + 1)
            candidates.append(PolymerCandidate(
                name=name, psmiles=f"Polymer({psmiles})", smiles=smiles,
                monomer_smiles=[smiles], source="rule_based", description=desc,
                predicted_ionic_conductivity=conductivity,
            ))

        return candidates

    async def _generate_with_llm_async(self, target_properties: dict | None, num_candidates: int) -> list[PolymerCandidate]:
        if not self.config.llm.api_key:
            return []

        prompt = self._build_generation_prompt(target_properties)
        try:
            import httpx
            # base_url may or may not include /v1; build the chat completions endpoint
            base_url = self.config.llm.base_url.rstrip("/")
            if "/v1" not in base_url:
                endpoint = f"{base_url}/v1/chat/completions"
            else:
                endpoint = f"{base_url}/chat/completions"
            # Cap response tokens to keep prompt responses small
            response_max_tokens = min(2000, self.config.llm.max_tokens)
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.post(
                    endpoint,
                    headers={"Authorization": f"Bearer {self.config.llm.api_key}"},
                    json={
                        "model": self.config.llm.model,
                        "messages": [
                            {"role": "system", "content": "You are a polymer chemist specializing in battery electrolyte materials."},
                            {"role": "user", "content": prompt},
                        ],
                        "temperature": self.config.llm.temperature,
                        "max_tokens": response_max_tokens,
                    },
                )

            if response.status_code == 200:
                content = response.json()["choices"][0]["message"]["content"]
                return self._parse_llm_response(content, num_candidates)
        except Exception:
            pass

        return []

    async def _generate_with_internlm_async(self, target_properties: dict | None, num_candidates: int) -> list[PolymerCandidate]:
        """Use the InternLM provider to generate polymer candidates."""
        provider = self._llm_provider
        provider_created_locally = False
        if provider is None:
            from ..llm.factory import ProviderFactory
            provider = ProviderFactory.create(self.config)
            provider_created_locally = True

        try:
            prompt = f"""Generate {num_candidates} polymer candidates for battery electrolyte with target properties: {target_properties}
Return only a JSON list of objects with keys: name, smiles, psmiles, properties (dict).
Example: [{{"name": "PEO", "smiles": "CCO", "psmiles": "[*]CCO[*]", "properties": {{"ionic_conductivity": 1e-5}}}}]"""

            request = ChatRequest(
                model=self.config.internlm.model,
                messages=[
                    ChatMessage(role="user", content=prompt),
                ],
                temperature=0.7,
                max_tokens=4096,
            )
            response = await provider.complete(request)
            content = response.content
            items = self._extract_json_list(content)
            if not items:
                raise ValueError("InternLM returned empty candidate list")

            candidates = []
            for item in items[:num_candidates]:
                props = item.get("properties", {}) or {}
                candidates.append(PolymerCandidate(
                    name=item.get("name", "Unknown"),
                    psmiles=item.get("psmiles", ""),
                    smiles=item.get("smiles", ""),
                    source="internlm_generated",
                    description=item.get("description", ""),
                    predicted_ionic_conductivity=props.get("ionic_conductivity", 0.0),
                ))

            if len(candidates) < num_candidates:
                remaining = num_candidates - len(candidates)
                candidates.extend(await self._generate_with_llm_async(target_properties, remaining))

            return candidates
        finally:
            if provider_created_locally:
                close_fn = getattr(provider, "close", None)
                if close_fn is not None:
                    try:
                        await close_fn()
                    except Exception as close_err:
                        logger.warning("Failed to close temporary LLM provider: %s", close_err)

    def _build_generation_prompt(self, target_properties: dict | None) -> str:
        props_str = json.dumps(target_properties or {"ionic_conductivity": "high"}, indent=2)
        return f"""Generate {5} novel polymer electrolyte candidates for lithium batteries.

Target properties:
{props_str}

For each polymer, provide:
1. Name
2. PSMILES notation
3. SMILES of monomer
4. Brief description of design rationale

Focus on polymers with:
- High dielectric constant for salt dissociation
- Flexible backbone for ion transport
- Good mechanical stability
- Thermal stability up to 200°C

Return as JSON array with fields: name, psmiles, smiles, description"""

    def _parse_llm_response(self, content: str, num_candidates: int) -> list[PolymerCandidate]:
        try:
            json_match = content[content.index("["):content.rindex("]")+1]
            data = json.loads(json_match)
            candidates = []
            for item in data[:num_candidates]:
                candidates.append(PolymerCandidate(
                    name=item.get("name", "Unknown"),
                    psmiles=item.get("psmiles", ""),
                    smiles=item.get("smiles", ""),
                    source="llm_generated",
                    description=item.get("description", ""),
                ))
            return candidates
        except Exception as e:
            logger.warning("LLM response parse failed: %s", e)
            return []

    def _extract_json_list(self, text: str) -> list[dict]:
        try:
            data = json.loads(text)
            if isinstance(data, list):
                return data
        except Exception:
            pass

        try:
            start = text.index("[")
            end = text.rindex("]") + 1
            data = json.loads(text[start:end])
            if isinstance(data, list):
                return data
        except Exception:
            pass

        return []
