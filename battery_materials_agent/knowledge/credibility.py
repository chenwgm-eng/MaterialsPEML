"""知识可信度双维度模型。

source_tier（来源等级）：
    database        权威数据库（Materials Project / PubChem / NIST 等）
    top_journal     顶级期刊（Nature/Science/JACS/Adv. Mater. 等）
    journal         普通同行评议期刊
    preprint        预印本（arXiv/ChemRxiv 等）
    internal        内部资料（实验记录/技术报告）
    llm_generated   LLM 参数化生成（最低可信度，需人工核实）

evidence_level（证据强度）：
    computation     计算预测（DFT/MD 等）
    literature      文献报道（他人实验结果）
    lab_validated   实验室验证（内部小试）
    pilot           中试验证
    production      量产验证

最终置信度 confidence = source_tier_score × evidence_level_score
"""
from __future__ import annotations

# 来源等级 → 基础分（0.0 ~ 1.0）
SOURCE_TIER_SCORES: dict[str, float] = {
    "database": 0.95,
    "top_journal": 0.90,
    "journal": 0.75,
    "preprint": 0.55,
    "internal": 0.70,  # 内部资料来源可信，但需结合证据强度
    "llm_generated": 0.30,
}

# 证据强度 → 权重（0.0 ~ 1.0）
EVIDENCE_LEVEL_SCORES: dict[str, float] = {
    "production": 1.00,
    "pilot": 0.90,
    "lab_validated": 0.80,
    "literature": 0.65,
    "computation": 0.55,
}

# 已知顶级期刊关键词（用于自动判定 source_tier）
TOP_JOURNAL_KEYWORDS: set[str] = {
    "nature", "science", "cell",
    "jacs", "journal of the american chemical society",
    "advanced materials", "adv. mater", "adv mater",
    "energy & environmental science", "energy environ. sci",
    "nature energy", "nature materials", "nature communications",
    "angewandte chemie",
    "physical review letters",
    "chemical reviews", "chemical society reviews",
    "advanced energy materials", "advanced functional materials",
    "nano letters", "acs nano",
    "joule",
}

# 权威数据库来源标识
DATABASE_SOURCES: set[str] = {
    "materials_project", "pubchem", "nist", "crossref", "semantic_scholar",
}


def infer_source_tier(source: str, journal: str = "") -> str:
    """根据来源标识和期刊名推断 source_tier。

    Args:
        source: 来源标识（crossref / semantic_scholar / llm_generated / ...）
        journal: 期刊名（可选，用于判定 top_journal）

    Returns:
        source_tier 字符串
    """
    source_lower = (source or "").lower().strip()
    if source_lower == "llm_generated":
        return "llm_generated"
    if source_lower in DATABASE_SOURCES:
        # Crossref/S2 是聚合器，仍按期刊分级；只有专用物性库才算 database
        if source_lower in {"materials_project", "pubchem", "nist"}:
            return "database"
        # 聚合器需看期刊
        if journal:
            journal_lower = journal.lower()
            if any(kw in journal_lower for kw in TOP_JOURNAL_KEYWORDS):
                return "top_journal"
        return "journal"
    if source_lower in {"internal", "upload", "user_upload"}:
        return "internal"
    if source_lower in {"arxiv", "chemrxiv", "preprint"}:
        return "preprint"
    # 默认
    if journal:
        journal_lower = journal.lower()
        if any(kw in journal_lower for kw in TOP_JOURNAL_KEYWORDS):
            return "top_journal"
    return "journal"


def infer_evidence_level(
    abstract: str = "",
    keywords: list[str] | None = None,
    claim_text: str = "",
) -> str:
    """根据摘要/关键词推断 evidence_level。

    简单规则：
    - 含 "DFT" / "first-principles" / "molecular dynamics" / "simulation" → computation
    - 含 "pilot" / "scale-up" / "中试" → pilot
    - 含 "production" / "manufacturing" / "量产" → production
    - 含 "we demonstrate" / "experimentally" / "successfully synthesized" → lab_validated
    - 其他 → literature

    Args:
        abstract: 摘要文本
        keywords: 关键词列表
        claim_text: 主张文本

    Returns:
        evidence_level 字符串
    """
    text = " ".join([abstract or "", " ".join(keywords or []), claim_text or ""]).lower()

    if any(kw in text for kw in ("production", "manufacturing", "industrial-scale", "量产")):
        return "production"
    if any(kw in text for kw in ("pilot", "scale-up", "scaleup", "中试")):
        return "pilot"
    if any(kw in text for kw in (
        "dft", "first-principles", "first principles", "ab initio",
        "molecular dynamics", "md simulation", "monte carlo",
        "computational screening", "machine learning prediction",
    )):
        return "computation"
    if any(kw in text for kw in (
        "we demonstrate", "experimentally", "successfully synthesized",
        "we report", "we fabricated", "we prepared",
    )):
        return "lab_validated"
    return "literature"


def compute_confidence(source_tier: str, evidence_level: str) -> float:
    """计算组合置信度（0.0 ~ 1.0）。

    Args:
        source_tier: 来源等级
        evidence_level: 证据强度

    Returns:
        0.0~1.0 的置信度分数
    """
    s = SOURCE_TIER_SCORES.get(source_tier, 0.5)
    e = EVIDENCE_LEVEL_SCORES.get(evidence_level, 0.5)
    return round(s * e, 3)


def confidence_label(confidence: float) -> str:
    """将数值置信度转为人类可读标签。"""
    if confidence >= 0.75:
        return "high"
    if confidence >= 0.45:
        return "medium"
    return "low"
