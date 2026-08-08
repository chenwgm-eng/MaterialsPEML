"""统一知识采集管道。

将多源检索结果统一处理为知识资产：
1. 多源并行检索（LLM / Crossref / Semantic Scholar / 本地知识库）
2. 按 DOI 和标题模糊匹配去重
3. 写入 knowledge.papers 资产表
4. 抽取材料实体，自动建立/更新材料卡片
5. 关联 paper_materials
6. LLM 驱动的自动主张抽取（从 abstract 提取结构化数据点）

设计原则：
- 复用 LiteratureResearcherAgent 的检索器，但把结果落到资产库而非仅返回列表
- 与现有 build_knowledge_graph 解耦：采集管道产出资产，图谱是资产的视图
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from .asset_store import (
    ClaimStore,
    MaterialStore,
    PaperStore,
    get_claim_store,
    get_material_store,
    get_paper_store,
)
from .credibility import (
    compute_confidence,
    infer_evidence_level,
    infer_source_tier,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# 实体抽取（复用并精简 LiteratureResearcherAgent 的关键词表）
# ─────────────────────────────────────────────────────────────────────────────

# 常见材料类别 → 关键词集合（含电解质/电极/隔膜等电化学储能领域）
MATERIAL_PATTERNS: dict[str, list[str]] = {
    "固态电解质": [
        "LLZO", "LLZTO", "LLTO", "LATP", "LAGP", "LPSC", "LGPS",
        "Li7La3Zr2O12", "Li6PS5Cl", "Li10GeP2S12", "garnet",
        "sulfide electrolyte", "oxide electrolyte", "polymer electrolyte",
    ],
    "正极材料": [
        "NCM", "NCA", "LFP", "LiFePO4", "LiCoO2", "LCO", "NCM811", "NCM622",
        "NCM523", "LiNi0.8Co0.1Mn0.1O2", "Li-rich", "LNMO",
    ],
    "负极材料": [
        "graphite", "silicon", "Si/C", "lithium metal", "Li metal",
        "hard carbon", "soft carbon", "LTO", "Li4Ti5O12",
    ],
    "隔膜": [
        "PP", "PE", "polypropylene", "polyethylene", "ceramic separator",
    ],
    "电解液": [
        "LiPF6", "LiFSI", "LiTFSI", "EC", "DEC", "DMC", "EMC", "FEC", "VC",
    ],
}

PROPERTY_KEYWORDS: list[str] = [
    "ionic conductivity", "ion conductivity", "电导率", "离子电导率",
    "cycle life", "cycling stability", "循环", "循环寿命",
    "capacity", "容量", "比容量",
    "coulombic efficiency", "库伦效率", "CE",
    "rate capability", "倍率",
    "energy density", "能量密度",
    "thermal stability", "热稳定性",
    "dendrite", "枝晶",
    "interfacial resistance", "界面阻抗",
    "electrochemical window", "电化学窗口",
]

METHOD_KEYWORDS: list[str] = [
    "solid-state reaction", "sol-gel", "co-precipitation", "hydrothermal",
    "sputtering", "ALD", "CVD", "electrospinning", "hot pressing",
    "spark plasma sintering", "SPS", "tape casting", "in-situ polymerization",
]


def _match_keywords(text: str, keywords: list[str]) -> list[str]:
    """在文本中匹配关键词（大小写不敏感，整词匹配）。"""
    if not text:
        return []
    text_lower = text.lower()
    found = []
    for kw in keywords:
        pattern = r"\b" + re.escape(kw.lower()) + r"\b"
        if re.search(pattern, text_lower):
            found.append(kw)
    return found


def _classify_material_category(name: str) -> str:
    """根据材料名称推断所属类别。"""
    name_lower = name.lower()
    for category, keywords in MATERIAL_PATTERNS.items():
        for kw in keywords:
            if kw.lower() in name_lower or name_lower in kw.lower():
                return category
    return "其他"


def extract_materials_from_paper(paper: dict) -> list[dict]:
    """从单篇文献中提取材料实体。

    Returns:
        [{canonical_name, category, context}] 列表
    """
    text = " ".join([
        paper.get("title", ""),
        paper.get("abstract", ""),
        " ".join(paper.get("keywords", [])),
    ])
    materials = []
    seen: set[str] = set()
    for category, keywords in MATERIAL_PATTERNS.items():
        for kw in keywords:
            pattern = r"\b" + re.escape(kw.lower()) + r"\b"
            if re.search(pattern, text.lower()) and kw.lower() not in seen:
                seen.add(kw.lower())
                # 找上下文（首个匹配位置前后 100 字符）
                match = re.search(pattern, text.lower())
                context = ""
                if match:
                    start = max(0, match.start() - 50)
                    end = min(len(text), match.end() + 100)
                    context = text[start:end].strip()
                materials.append({
                    "canonical_name": kw,
                    "category": category,
                    "context": context,
                })
    return materials


# ─────────────────────────────────────────────────────────────────────────────
# 采集管道
# ─────────────────────────────────────────────────────────────────────────────

class KnowledgeIngestionPipeline:
    """统一知识采集管道。"""

    def __init__(
        self,
        paper_store: PaperStore | None = None,
        material_store: MaterialStore | None = None,
        claim_store: ClaimStore | None = None,
    ):
        self.papers = paper_store or get_paper_store()
        self.materials = material_store or get_material_store()
        self.claims = claim_store or get_claim_store()

    def ingest_papers(
        self,
        raw_papers: list[dict],
        default_source: str = "unknown",
        auto_create_materials: bool = True,
    ) -> dict:
        """把一组检索结果入库为知识资产。

        Args:
            raw_papers: 检索器返回的原始文献列表（字段不一定齐全）
            default_source: 缺失 source 字段时的默认值
            auto_create_materials: 是否自动建立材料卡片

        Returns:
            处理结果统计 {papers_added, papers_updated, materials_touched, claims_added}
        """
        stats = {
            "papers_added": 0,
            "papers_skipped": 0,
            "materials_touched": 0,
            "claims_added": 0,
            "paper_ids": [],
        }
        touched_materials: set[str] = set()

        for raw in raw_papers:
            title = (raw.get("title") or "").strip()
            if not title:
                stats["papers_skipped"] += 1
                continue

            # 推断可信度双维度
            source = raw.get("source") or default_source
            journal = raw.get("journal", "")
            source_tier = infer_source_tier(source, journal)
            evidence_level = infer_evidence_level(
                abstract=raw.get("abstract", ""),
                keywords=raw.get("keywords", []),
            )
            confidence = compute_confidence(source_tier, evidence_level)

            # 构建入库记录
            paper_record = {
                "doi": (raw.get("doi") or "").strip() or None,
                "title": title,
                "authors": raw.get("authors", []),
                "journal": journal,
                "year": raw.get("year"),
                "abstract": raw.get("abstract", ""),
                "keywords": raw.get("keywords", []),
                "source": source,
                "source_tier": source_tier,
                "url": raw.get("url", ""),
                "citation_count": raw.get("citation_count", 0),
                "extra": {
                    "evidence_level": evidence_level,
                    "confidence": confidence,
                    **(raw.get("extra", {}) if isinstance(raw.get("extra"), dict) else {}),
                },
            }

            # 写入 papers 表（按 DOI 去重）
            saved = self.papers.upsert(paper_record)
            stats["papers_added"] += 1
            stats["paper_ids"].append(saved["paper_id"])

            # 自动建立材料卡片
            if auto_create_materials:
                materials_found = extract_materials_from_paper(saved)
                for m in materials_found:
                    material_record = {
                        "canonical_name": m["canonical_name"],
                        "category": m["category"],
                        "source_tier": source_tier,
                        "evidence_level": evidence_level,
                    }
                    saved_material = self.materials.upsert(material_record)
                    self.materials.link_paper(
                        saved_material["material_id"],
                        saved["paper_id"],
                        context=m.get("context", ""),
                    )
                    touched_materials.add(saved_material["material_id"])

        stats["materials_touched"] = len(touched_materials)
        return stats

    def ingest_papers_for_query(
        self,
        query: str,
        raw_papers: list[dict],
        default_source: str = "unknown",
    ) -> dict:
        """针对一次查询的批量入库（含按查询关联到通用材料卡片）。"""
        stats = self.ingest_papers(
            raw_papers,
            default_source=default_source,
            auto_create_materials=True,
        )
        stats["query"] = query
        return stats

    def add_claim(
        self,
        material_name: str,
        claim_text: str,
        claim_type: str = "general",
        subject: str = "",
        predicate: str = "",
        value: str = "",
        unit: str = "",
        numeric_value: float | None = None,
        source_paper_id: str = "",
        source_tier: str = "journal",
        evidence_level: str = "literature",
    ) -> dict:
        """手动添加一条主张（供内部资料录入/用户标注使用）。"""
        material = self.materials.get_by_name(material_name)
        if material is None:
            material = self.materials.upsert({
                "canonical_name": material_name,
                "category": _classify_material_category(material_name),
                "source_tier": source_tier,
                "evidence_level": evidence_level,
            })

        confidence = compute_confidence(source_tier, evidence_level)
        claim_record = {
            "material_id": material["material_id"],
            "claim_type": claim_type,
            "subject": subject or material_name,
            "predicate": predicate,
            "value": value,
            "unit": unit,
            "numeric_value": numeric_value,
            "claim_text": claim_text,
            "source_paper_id": source_paper_id or None,
            "source_tier": source_tier,
            "evidence_level": evidence_level,
            "confidence": confidence,
        }
        return self.claims.upsert(claim_record)

    # ───────────────────────────────────────────────────────────────────────
    # LLM 驱动的自动主张抽取
    # ───────────────────────────────────────────────────────────────────────

    async def extract_claims_from_paper(
        self,
        paper: dict,
        material_name: str = "",
    ) -> list[dict]:
        """调用 LLM 从文献摘要中自动抽取结构化主张。

        提取的主张格式：
        {
            "claim_type": "property|synthesis|application|comparison|mechanism|general",
            "subject": "LLZO",
            "predicate": "ionic_conductivity",
            "value": "1.5e-4",
            "unit": "S/cm",
            "claim_text": "LLZO 在 25°C 下离子电导率达到 1.5×10⁻⁴ S/cm"
        }

        Args:
            paper: 文献记录（需含 title, abstract, keywords）
            material_name: 可选，限定抽取与此材料相关的主张

        Returns:
            已入库的主张列表
        """
        from ..config import EngineMode, get_config
        from ..llm.factory import ProviderFactory
        from ..llm.schemas import ChatRequest, ChatMessage

        abstract = paper.get("abstract", "").strip()
        title = paper.get("title", "").strip()
        if not abstract or len(abstract) < 30:
            return []

        prompt = self._build_claim_extraction_prompt(title, abstract, material_name)

        config = get_config()
        provider = ProviderFactory.create(config)
        model = config.internlm.model if config.engine_mode == EngineMode.INTERNLM else config.llm.model
        try:
            chat_req = ChatRequest(
                model=model,
                messages=[ChatMessage(role="user", content=prompt)],
                temperature=0.1,
                max_tokens=2048,
                response_format={"type": "json_object"},
            )
            chat_resp = await provider.complete(chat_req)
            response = chat_resp.content
        except Exception as e:
            logger.warning("LLM 主张抽取失败: %s", e)
            return []
        finally:
            close_fn = getattr(provider, "close", None)
            if close_fn is not None:
                try:
                    await close_fn()
                except Exception as close_err:
                    logger.warning("Failed to close temporary LLM provider: %s", close_err)

        # 解析 LLM 返回的 JSON
        claims_raw = self._parse_claims_response(response)
        if not claims_raw:
            return []

        # 推断可信度
        source = paper.get("source", "unknown")
        journal = paper.get("journal", "")
        source_tier = infer_source_tier(source, journal)
        evidence_level = infer_evidence_level(
            abstract=abstract,
            keywords=paper.get("keywords", []),
        )

        # 入库
        saved_claims = []
        for c in claims_raw:
            material_name_resolved = c.get("subject", "") or material_name
            if not material_name_resolved:
                continue
            try:
                saved = self.add_claim(
                    material_name=material_name_resolved,
                    claim_text=c.get("claim_text", ""),
                    claim_type=c.get("claim_type", "general"),
                    subject=c.get("subject", material_name_resolved),
                    predicate=c.get("predicate", ""),
                    value=c.get("value", ""),
                    unit=c.get("unit", ""),
                    numeric_value=self._try_parse_float(c.get("value", "")),
                    source_paper_id=paper.get("paper_id", ""),
                    source_tier=source_tier,
                    evidence_level=evidence_level,
                )
                saved_claims.append(saved)
            except Exception as e:
                logger.warning("主张入库失败: %s", e)
        return saved_claims

    async def extract_claims_batch(
        self,
        papers: list[dict],
        material_name: str = "",
    ) -> dict:
        """批量抽取多篇文献的主张。"""
        all_claims = []
        for paper in papers:
            claims = await self.extract_claims_from_paper(paper, material_name)
            all_claims.extend(claims)
        return {
            "papers_processed": len(papers),
            "claims_extracted": len(all_claims),
            "claims": all_claims,
        }

    @staticmethod
    def _build_claim_extraction_prompt(
        title: str, abstract: str, material_name: str
    ) -> str:
        target = f'重点关注与"{material_name}"相关的主张。' if material_name else ""
        return f"""请从以下文献摘要中提取结构化的知识主张（claims）。

{target}

文献标题：{title}
摘要：{abstract}

提取要求：
1. 每条主张应是一个可验证的、独立的科学陈述
2. 优先提取包含具体数值的性能数据（如电导率、容量、循环寿命等）
3. 提取合成方法、应用场景、机制解释等主张
4. 不要编造摘要中没有的信息

输出 JSON 格式：
{{
  "claims": [
    {{
      "claim_type": "property|synthesis|application|comparison|mechanism|general",
      "subject": "材料名称（如 LLZO、NCM811）",
      "predicate": "属性名（如 ionic_conductivity、cycle_life、capacity）",
      "value": "数值或描述",
      "unit": "单位（如 S/cm、mAh/g、cycles）",
      "claim_text": "完整的中文陈述句"
    }}
  ]
}}

如果摘要中没有可提取的主张，返回 {{"claims": []}}。"""

    @staticmethod
    def _parse_claims_response(response: str) -> list[dict]:
        """解析 LLM 返回的 JSON，容错处理。"""
        if not response:
            return []
        # 尝试直接解析
        try:
            data = json.loads(response)
            if isinstance(data, dict) and "claims" in data:
                return data["claims"]
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            pass
        # 尝试提取 JSON 块
        match = re.search(r'\{[\s\S]*\}', response)
        if match:
            try:
                data = json.loads(match.group())
                if isinstance(data, dict) and "claims" in data:
                    return data["claims"]
            except json.JSONDecodeError:
                pass
        return []

    @staticmethod
    def _try_parse_float(value: str) -> float | None:
        """尝试从字符串中解析数值。"""
        if not value:
            return None
        # 提取科学计数法或普通数字
        match = re.search(r'[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?', value)
        if match:
            try:
                return float(match.group())
            except ValueError:
                return None
        return None


# ─────────────────────────────────────────────────────────────────────────────
# 单例
# ─────────────────────────────────────────────────────────────────────────────

_pipeline: KnowledgeIngestionPipeline | None = None


def get_ingestion_pipeline() -> KnowledgeIngestionPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = KnowledgeIngestionPipeline()
    return _pipeline
