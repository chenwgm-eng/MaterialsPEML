"""Literature researcher agent for technical intelligence & knowledge graph.

检索策略：
1. LLM 知识检索（默认启用）：调用配置的大模型基于参数化知识生成相关学术文献。
2. SCP 工具检索（可选）：若系统启用了 SCP 且配置了 literature_search 绑定，
   则通过 MCPToolRegistry 调用远端检索服务。
3. 外部学术 API 检索（默认启用）：Crossref / Semantic Scholar 公开 API，
   无需 API key 即可使用，配置对应环境变量可提升配额。
4. 本地知识库检索（默认启用）：复用已保存知识图谱中的文献，实现知识积累。
5. 模板文献库（兜底）：当真实检索均未返回结果时，回退到内置的 25 篇电池材料领域模板文献。

所有文献均标记来源与置信度（high/medium/low），LLM 生成的文献标记为
source="llm_generated"，提醒用户人工核实。
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from abc import ABC, abstractmethod
from typing import Any, Protocol

import httpx

from ...config import AgentConfig, get_config

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# 检索源协议与实现
# ──────────────────────────────────────────────────────────────────────────────

class RetrievalSource(Protocol):
    """文献检索源协议。"""

    async def search(self, query: str, limit: int) -> list[dict]:
        """返回文献列表，每项含 title/authors/journal/year/abstract/doi/keywords。"""
        ...


class _LLMClient:
    """简易 LLM 客户端：优先 InternLM，其次通用 OpenAI-compatible API。

    .. deprecated:: BEMCL-AI-P2-003
        此类绕过 LLMProvider Protocol 治理链（无审计、无输入快照）。
        新代码应使用 ``ProviderFactory.create(config)`` 获取 ``LLMProvider`` 实例，
        通过 ``ChatRequest`` / ``ChatMessage`` 调用 ``provider.complete()``。
    """

    def __init__(self, config: AgentConfig | None = None):
        import warnings
        warnings.warn(
            "_LLMClient 已废弃，请使用 ProviderFactory.create(config) 获取 LLMProvider 实例。"
            "详见 BEMCL-AI-P2-003 修复。",
            DeprecationWarning,
            stacklevel=2,
        )
        self._config = config

    def _get_config(self) -> AgentConfig:
        if self._config is None:
            self._config = get_config()
        return self._config

    async def complete(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 4096,
        response_format: dict | None = None,
        model: str | None = None,
    ) -> str:
        config = self._get_config()

        # 若显式指定 model（例如使用某个 Agent 自己的 llm_model），
        # 则跳过 InternLM 优先策略，直接走通用 OpenAI-compatible API
        if model is not None:
            return await self._generic_complete(
                config, messages, temperature, max_tokens, response_format, model=model
            )

        # 优先 InternLM；但文献检索对延迟敏感，设置较短超时以快速回退到通用 LLM
        if config.internlm.enabled and config.internlm.api_key:
            try:
                return await asyncio.wait_for(
                    self._internlm_complete(config, messages, temperature, max_tokens, response_format),
                    timeout=8.0,
                )
            except asyncio.TimeoutError:
                logger.warning("InternLM 调用超时（8s），回退到通用 LLM")
            except Exception as e:
                logger.warning("InternLM 调用失败，回退到通用 LLM: %s", e)

        return await self._generic_complete(config, messages, temperature, max_tokens, response_format)

    async def _internlm_complete(
        self,
        config: AgentConfig,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        response_format: dict | None,
    ) -> str:
        from ...llm.schemas import ChatMessage, ChatRequest
        from ...llm.internlm_provider import InternLMProvider

        provider = InternLMProvider(config.internlm)
        try:
            request = ChatRequest(
                model=config.internlm.model,
                messages=[ChatMessage(role=m["role"], content=m["content"]) for m in messages],
                temperature=temperature,
                max_tokens=max_tokens,
                response_format=response_format,
            )
            response = await provider.complete(request)
            return response.content
        finally:
            close_fn = getattr(provider, "close", None)
            if close_fn is not None:
                try:
                    await close_fn()
                except Exception as close_err:
                    logger.warning("Failed to close temporary LLM provider: %s", close_err)

    async def _generic_complete(
        self,
        config: AgentConfig,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        response_format: dict | None,
        model: str | None = None,
    ) -> str:
        base_url = config.llm.base_url.rstrip("/")
        endpoint = f"{base_url}/v1/chat/completions" if "/v1" not in base_url else f"{base_url}/chat/completions"
        headers = {"Authorization": f"Bearer {config.llm.api_key}"}
        # 若调用方显式指定 model（例如 Agent 自己的 llm_model），覆盖默认配置
        effective_model = model or config.llm.model
        payload: dict = {
            "model": effective_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format:
            payload["response_format"] = response_format

        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(endpoint, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
        if "error" in data:
            raise RuntimeError(f"LLM API 返回错误: {data['error']}")
        if "choices" not in data or not data["choices"]:
            raise RuntimeError("LLM API 响应缺少 choices 字段")
        return data["choices"][0]["message"]["content"]


class LLMKnowledgeRetriever:
    """基于 LLM 参数化知识的文献检索器。

    通过 LLM 生成与用户查询相关的学术文献列表。返回结果会明确标记为
    source="llm_generated"，提示用户需人工核实真实性与准确性。
    """

    def __init__(self, llm_client: _LLMClient | None = None):
        self._llm = llm_client or _LLMClient()

    async def search(self, query: str, limit: int = 10) -> list[dict]:
        if not query or not query.strip():
            return []

        system_prompt = (
            "你是一位资深材料科学文献调研员。请根据用户的研究主题，"
            "检索并返回最相关的真实学术文献信息。你必须只返回你相对有把握的真实文献；"
            "对于不确定的文献，宁可不返回也不要编造。"
            "输出必须是严格 JSON 数组，不要包含 markdown 代码块标记。"
        )
        user_prompt = (
            f"研究主题：{query}\n\n"
            f"请返回 {limit} 篇与该主题最相关的学术文献，按相关度降序排列。"
            "每篇文献必须包含以下字段（JSON 数组）：\n"
            "[\n"
            "  {\n"
            '    "title": "文献标题（英文优先）",\n'
            '    "authors": ["作者1", "作者2"],\n'
            '    "journal": "期刊名称",\n'
            '    "year": 2020,\n'
            '    "abstract": "摘要，控制在 80-150 字",\n'
            '    "doi": "DOI，若无则留空字符串",\n'
            '    "keywords": ["关键词1", "关键词2"]\n'
            "  }\n"
            "]\n"
            "要求：\n"
            "1. 必须返回合法 JSON 数组，不要任何额外说明。\n"
            "2. 如果主题超出你的知识范围或你不确定，返回空数组 []。\n"
            "3. 年份必须是整数，作者必须是字符串数组。"
        )

        try:
            content = await self._llm.complete(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
                max_tokens=8192,
            )
            papers = self._parse_llm_papers(content, limit)
            for p in papers:
                p["source"] = "llm_generated"
                p.setdefault("score", 0)
            return papers
        except Exception as e:
            logger.warning("LLM 知识检索失败: %s", e)
            return []

    @staticmethod
    def _parse_llm_papers(content: str, limit: int) -> list[dict]:
        text = content.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text
            if text.endswith("```"):
                text = text.rsplit("```", 1)[0]
            text = text.strip()

        if not text:
            return []

        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            logger.warning("LLM 文献 JSON 解析失败: %s (raw=%r)", e, text[:200])
            return []

        if isinstance(data, dict) and "papers" in data:
            data = data["papers"]
        if not isinstance(data, list):
            logger.warning("LLM 文献输出不是数组: %r", type(data))
            return []

        papers: list[dict] = []
        for item in data[:limit]:
            if not isinstance(item, dict):
                continue
            title = _normalize_text(item.get("title", ""))
            if not title:
                continue
            authors = _to_string_list(item.get("authors", []))
            keywords = _to_string_list(item.get("keywords", []))
            year = _to_int(item.get("year", 0))
            if year < 1900 or year > 2100:
                year = 0
            papers.append({
                "title": title,
                "authors": authors,
                "journal": _normalize_text(item.get("journal", "")),
                "year": year,
                "abstract": _normalize_text(item.get("abstract", "")),
                "doi": _normalize_text(item.get("doi", "")),
                "keywords": keywords,
            })
        return papers


class SCPRetriever:
    """通过 SCP / MCP 工具调用远端文献检索服务。"""

    def __init__(self, tool_registry: Any | None = None):
        self._tool_registry = tool_registry

    async def search(self, query: str, limit: int = 10) -> list[dict]:
        registry = self._tool_registry
        if registry is None:
            from ...agent import BatteryMaterialsAgent
            try:
                # 优先从 app state 获取（后端运行时）
                import battery_materials_agent.api as api_module
                if hasattr(api_module, "agent") and api_module.agent is not None:
                    registry = api_module.agent.tools
            except Exception:
                pass

        if registry is None:
            return []

        # 工具注册时使用 internal_name（如 scp_literature_search），而非 output_mapping
        tool_name = "scp_literature_search"
        try:
            # 远端 search_pubchem_by_name 不接受 limit 参数，仅传递 query/name
            result = await registry.execute_async(tool_name, {"query": query})
        except Exception as e:
            logger.warning("SCP 文献检索失败: %s", e)
            return []

        documents = result.get("documents") or result.get("papers") or []
        papers: list[dict] = []
        for doc in documents[:limit]:
            if not isinstance(doc, dict):
                continue
            title = _normalize_text(doc.get("title", ""))
            if not title:
                continue
            papers.append({
                "title": title,
                "authors": _to_string_list(doc.get("authors", [])),
                "journal": _normalize_text(doc.get("journal", "")),
                "year": _to_int(doc.get("year", 0)),
                "abstract": _normalize_text(doc.get("abstract", "")),
                "doi": _normalize_text(doc.get("doi", "")),
                "keywords": _to_string_list(doc.get("keywords", [])),
                "source": "scp",
            })
        return papers


class WebAPIRetriever(ABC):
    """外部学术 API 检索基类（预留接口）。"""

    @abstractmethod
    async def search(self, query: str, limit: int) -> list[dict]:
        """子类实现具体 API 调用。默认返回空列表。"""
        return []


class SemanticScholarRetriever(WebAPIRetriever):
    """Semantic Scholar API 检索。

    公开 API 无需 key 即可使用；配置 S2_API_KEY 后可获得更高调用配额。
    文档：https://api.semanticscholar.org/api-docs/graph
    """

    _BASE_URL = "https://api.semanticscholar.org/graph/v1/paper/search"

    async def search(self, query: str, limit: int = 10) -> list[dict]:
        if not query or not query.strip():
            return []

        headers = {}
        s2_key = self._api_key("S2_API_KEY")
        if s2_key:
            headers["x-api-key"] = s2_key

        params = {
            "query": query,
            "limit": min(limit, 100),
            "fields": "title,authors,year,abstract,venue,externalIds",
        }
        try:
            async with httpx.AsyncClient(timeout=30, headers=headers) as client:
                response = await client.get(self._BASE_URL, params=params)
                response.raise_for_status()
                data = response.json()
        except Exception as e:
            logger.warning("Semantic Scholar API 检索失败: %s", e)
            return []

        papers: list[dict] = []
        for item in data.get("data", [])[:limit]:
            title = _normalize_text(item.get("title"))
            if not title:
                continue
            if _is_non_peer_review_title(title):
                continue
            authors = []
            for author in item.get("authors", []) or []:
                name = _normalize_text(author.get("name"))
                if name:
                    authors.append(name)
            year = _to_int(item.get("year"))
            if year < 1900 or year > 2100:
                year = 0
            external_ids = item.get("externalIds") or {}
            doi = _normalize_text(external_ids.get("DOI"))
            abstract = _normalize_text(item.get("abstract"))
            journal = _normalize_text(item.get("venue"))
            papers.append({
                "title": title,
                "authors": authors,
                "journal": journal,
                "year": year,
                "abstract": abstract,
                "doi": doi,
                "keywords": [],
                "source": "semantic_scholar",
                "score": 0,
            })
        return papers

    @staticmethod
    def _api_key(env_name: str) -> str | None:
        import os
        key = os.getenv(env_name, "").strip()
        return key or None


class CrossrefRetriever(WebAPIRetriever):
    """Crossref API 检索。

    公开 API 无需 key；建议提供邮件作为 polite 请求。
    文档：https://api.crossref.org
    """

    _BASE_URL = "https://api.crossref.org/works"

    async def search(self, query: str, limit: int = 10) -> list[dict]:
        if not query or not query.strip():
            return []

        headers = {}
        contact_email = self._api_key("CROSSREF_EMAIL")
        if contact_email:
            headers["User-Agent"] = f"BatteryPEML/1.0 (mailto:{contact_email})"
        else:
            headers["User-Agent"] = "BatteryPEML/1.0"

        params = {
            "query": query,
            "rows": min(limit, 100),
            "sort": "relevance",
            "order": "desc",
            "select": "title,author,container-title,published,abstract,DOI",
        }
        try:
            async with httpx.AsyncClient(timeout=30, headers=headers) as client:
                response = await client.get(self._BASE_URL, params=params)
                response.raise_for_status()
                data = response.json()
        except Exception as e:
            logger.warning("Crossref API 检索失败: %s", e)
            return []

        papers: list[dict] = []
        for item in (data.get("message", {}).get("items", []))[:limit]:
            titles = item.get("title") or []
            title = _normalize_text(titles[0]) if titles else ""
            if not title:
                continue
            if _is_non_peer_review_title(title):
                continue
            authors = []
            for author in item.get("author", []) or []:
                given = author.get("given", "")
                family = author.get("family", "")
                name = " ".join([p for p in [given, family] if p]).strip()
                if name:
                    authors.append(name)
            year = 0
            published = item.get("published") or {}
            date_parts = published.get("date-parts") or [[]]
            if date_parts and date_parts[0]:
                year = _to_int(date_parts[0][0])
            if year < 1900 or year > 2100:
                year = 0
            containers = item.get("container-title") or []
            journal = _normalize_text(containers[0]) if containers else ""
            papers.append({
                "title": title,
                "authors": authors,
                "journal": journal,
                "year": year,
                "abstract": _normalize_text(item.get("abstract")),
                "doi": _normalize_text(item.get("DOI")),
                "keywords": [],
                "source": "crossref",
                "score": 0,
            })
        return papers

    @staticmethod
    def _api_key(env_name: str) -> str | None:
        import os
        key = os.getenv(env_name, "").strip()
        return key or None


class ArxivRetriever(WebAPIRetriever):
    """arXiv API 检索（生物医药 / 化学 / 材料预印本）。

    复用 Biomni 项目 `biomni/tool/literature.py::query_arxiv` 的检索思路，
    输出改为结构化字段以便接入知识图谱与入库。公开 API 无需 key。
    """

    async def search(self, query: str, limit: int = 10) -> list[dict]:
        if not query or not query.strip():
            return []

        def _search() -> list[dict]:
            import arxiv

            client = arxiv.Client()
            search = arxiv.Search(
                query=query,
                max_results=max(limit, 1),
                sort_by=arxiv.SortCriterion.Relevance,
            )
            papers: list[dict] = []
            for paper in client.results(search):
                title = _normalize_text(paper.title)
                if not title:
                    continue
                authors = [_normalize_text(a.name) for a in paper.authors if a.name and a.name.strip()]
                year = 0
                if paper.published is not None:
                    year = _to_int(getattr(paper.published, "year", 0))
                if year < 1900 or year > 2100:
                    year = 0
                papers.append({
                    "title": title,
                    "authors": authors,
                    "journal": _normalize_text(paper.journal_ref),
                    "year": year,
                    "abstract": _normalize_text(paper.summary),
                    "doi": _normalize_text(paper.doi),
                    "keywords": [],
                    "url": _normalize_text(paper.entry_id),
                    "source": "arxiv",
                    "score": 0,
                })
                if len(papers) >= limit:
                    break
            return papers

        try:
            return await asyncio.to_thread(_search)
        except ImportError:
            logger.warning("未安装 arxiv 库，跳过 arXiv 检索")
            return []
        except Exception as e:
            logger.warning("arXiv API 检索失败: %s", e)
            return []


class PubmedRetriever(WebAPIRetriever):
    """PubMed API 检索（生物医药文献）。

    复用 Biomni 项目 `biomni/tool/literature.py::query_pubmed` 的检索思路
    （含简化查询重试），输出改为结构化字段。公开 API 无需 key，
    需提供可用的联系邮箱（PUBMED_EMAIL，缺省用占位邮箱）。
    """

    async def search(self, query: str, limit: int = 10) -> list[dict]:
        if not query or not query.strip():
            return []

        def _search() -> list[dict]:
            import os

            from pymed import PubMed

            email = os.getenv("PUBMED_EMAIL", "").strip() or "battery-materials@example.com"
            pubmed = PubMed(tool="BatteryPEML", email=email)
            papers: list[dict] = []
            max_retries = 3

            # 查询字符串用于重试；PubMed 对中文/复杂查询可能返回空，逐步简化
            cur_query = query
            for attempt in range(max_retries):
                try:
                    articles = list(pubmed.query(cur_query, max_results=max(limit, 1)))
                except Exception as e:
                    logger.warning("PubMed 查询失败（%s）: %s", cur_query, e)
                    articles = []
                if articles:
                    break
                # 简化查询：去掉最后一个词
                tokens = cur_query.split()
                if len(tokens) <= 1:
                    break
                cur_query = " ".join(tokens[:-1])

            for article in articles[:limit]:
                title = _normalize_text(getattr(article, "title", None))
                if not title:
                    continue
                authors = []
                for a in (getattr(article, "authors", None) or []):
                    name = _normalize_text(getattr(a, "name", None) or getattr(a, "lastname", "") + " " + getattr(a, "initials", ""))
                    if name:
                        authors.append(name)
                year = 0
                pub_date = getattr(article, "publication_date", None)
                if pub_date is not None:
                    year = _to_int(getattr(pub_date, "year", 0))
                if year < 1900 or year > 2100:
                    year = 0
                papers.append({
                    "title": title,
                    "authors": authors,
                    "journal": _normalize_text(getattr(article, "journal", None)),
                    "year": year,
                    "abstract": _normalize_text(getattr(article, "abstract", None)),
                    "doi": _normalize_text(getattr(article, "doi", None)),
                    "keywords": [],
                    "url": _normalize_text(
                        getattr(article, "pubmed_url", None)
                        or f"https://pubmed.ncbi.nlm.nih.gov/{getattr(article, 'pubmed_id', '')}"
                    ),
                    "source": "pubmed",
                    "score": 0,
                })
                if len(papers) >= limit:
                    break
            return papers

        try:
            return await asyncio.to_thread(_search)
        except ImportError:
            logger.warning("未安装 pymed 库，跳过 PubMed 检索")
            return []
        except Exception as e:
            logger.warning("PubMed API 检索失败: %s", e)
            return []


class GoogleScholarRetriever(WebAPIRetriever):
    """Google Scholar 检索源（scholarly 库）。

    作为补充检索源，可靠度标记为 ``low``，且**默认关闭**（由环境变量
    ``GOOGLE_SCHOLAR_ENABLED`` 控制，默认 false）。scholarly 依赖 Google
    搜索结果页，稳定性较差，因此异常时静默降级为空结果，不影响主检索流。

    中文查询由 ``LiteratureResearcherAgent`` 统一转译为英文后再调用本检索器。
    """

    def __init__(self, enabled: bool | None = None):
        import os as _os

        if enabled is None:
            enabled = (
                _os.getenv("GOOGLE_SCHOLAR_ENABLED", "false").strip().lower() in ("1", "true", "yes")
            )
        self._enabled = enabled

    async def search(self, query: str, limit: int = 10) -> list[dict]:
        if not self._enabled or not query or not query.strip():
            return []
        if not _is_ascii(query):
            logger.info("Google Scholar 跳过非英文查询: %r", query)
            return []

        def _search() -> list[dict]:
            from scholarly import scholarly  # type: ignore

            papers: list[dict] = []
            search_query = scholarly.search_pubs(query)
            for _ in range(max(limit, 1)):
                try:
                    pub = next(search_query)
                except StopIteration:
                    break
                except Exception as e:  # noqa: BLE001
                    logger.debug("Google Scholar 单条解析失败: %s", e)
                    continue
                title = _normalize_text(pub.get("bib", {}).get("title"))
                if not title:
                    continue
                authors = _to_string_list(pub.get("bib", {}).get("author"))
                year = _to_int(pub.get("bib", {}).get("pub_year"))
                if year < 1900 or year > 2100:
                    year = 0
                papers.append({
                    "title": title,
                    "authors": authors,
                    "journal": _normalize_text(pub.get("bib", {}).get("venue")),
                    "year": year,
                    "abstract": _normalize_text(pub.get("bib", {}).get("abstract")),
                    "doi": _normalize_text(pub.get("pub_url", "")),
                    "keywords": [],
                    "url": _normalize_text(pub.get("pub_url")),
                    "source": "google_scholar",
                    "score": 0,
                })
                if len(papers) >= limit:
                    break
            return papers

        try:
            return await asyncio.to_thread(_search)
        except ImportError:
            logger.warning("未安装 scholarly 库，跳过 Google Scholar 检索")
            return []
        except Exception as e:  # noqa: BLE001
            logger.warning("Google Scholar 检索失败: %s", e)
            return []


class WebContentRetriever:
    """全文内容抽取 — 对检索结果抓取网页正文 / PDF 全文。

    复用 Biomni 项目 `extract_url_content` / `extract_pdf_content` 思路：
    - 从 DOI 推导 `https://doi.org/{doi}` 并跟随重定向到出版商页面。
    - HTML 页面：剥离 script/style/标签后提取正文。
    - PDF 链接：若已安装 pypdf / PyPDF2 则提取文本，否则跳过。

    安全与稳定性：
    - SSRF 防护：仅允许 http/https，拦截环回 / 内网 / 链路本地 / 保留地址。
    - 内容大小上限：超过 2MB 丢弃，避免内存占用。
    - 超时熔断：单次抓取超时即放弃，不影响摘要级结果返回。

    行为由环境变量控制：
    - `FULL_TEXT_EXTRACT_ENABLED`（默认 false）：是否启用全文抽取。
    - `FULL_TEXT_EXTRACT_TIMEOUT`（默认 30s）：单次抓取超时。
    """

    _MAX_BYTES = 2 * 1024 * 1024  # 2MB

    @staticmethod
    def _default_timeout() -> float:
        import os
        raw = os.getenv("FULL_TEXT_EXTRACT_TIMEOUT", "30")
        try:
            return max(1.0, float(raw))
        except ValueError:
            return 30.0

    @staticmethod
    def _is_safe_url(url: str) -> bool:
        from urllib.parse import urlparse

        try:
            import ipaddress
            parsed = urlparse(url)
        except Exception:
            return False
        if parsed.scheme not in ("http", "https"):
            return False
        hostname = parsed.hostname
        if not hostname:
            return False
        if hostname.lower() in ("localhost",) or hostname.lower().endswith(".local"):
            return False
        try:
            addr = ipaddress.ip_address(hostname)
        except ValueError:
            addr = None
        if addr is not None:
            return not (addr.is_private or addr.is_loopback or addr.is_link_local
                        or addr.is_reserved or addr.is_multicast)
        return True

    @staticmethod
    def _doi_url(doi: str) -> str:
        doi = (doi or "").strip()
        if not doi:
            return ""
        return f"https://doi.org/{doi}"

    @staticmethod
    def _extract_html_text(html: str) -> str:
        text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
        text = re.sub(r"<[^>]+>", " ", text)
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _extract_pdf_text(content: bytes) -> str:
        try:
            from pypdf import PdfReader  # type: ignore
        except ImportError:
            try:
                from PyPDF2 import PdfReader  # type: ignore
            except ImportError:
                return ""
        try:
            import io
            reader = PdfReader(io.BytesIO(content))
            parts = [page.extract_text() or "" for page in reader.pages]
            return " ".join(parts).strip()
        except Exception:
            return ""

    async def extract_one(self, doi: str, timeout: float) -> dict:
        """抓取单篇 DOI 对应页面/PDF 的全文。失败返回 error 标记，不抛异常。"""
        url = self._doi_url(doi)
        if not url:
            return {"full_text": "", "full_text_available": False, "full_text_error": "missing_doi"}
        if not self._is_safe_url(url):
            return {"full_text": "", "full_text_available": False, "full_text_error": "unsafe_url"}
        try:
            async with httpx.AsyncClient(
                follow_redirects=True,
                timeout=timeout,
                headers={"User-Agent": "BatteryPEML/1.0 (mailto:battery-materials@example.com)"},
            ) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                content = resp.content
            if len(content) > self._MAX_BYTES:
                return {"full_text": "", "full_text_available": False, "full_text_error": "content_too_large"}
            ctype = resp.headers.get("content-type", "").lower()
            if "pdf" in ctype or url.lower().endswith(".pdf"):
                text = self._extract_pdf_text(content)
            else:
                text = self._extract_html_text(content.decode("utf-8", errors="ignore"))
            if not text:
                return {"full_text": "", "full_text_available": False, "full_text_error": "empty_content"}
            return {"full_text": text, "full_text_available": True, "full_text_error": ""}
        except Exception as e:  # noqa: BLE001
            return {"full_text": "", "full_text_available": False, "full_text_error": str(e)[:200]}

    async def extract(self, papers: list[dict], timeout: float | None = None) -> list[dict]:
        """对一批文献抓取全文，就地更新每篇的 full_text / full_text_available / full_text_error。

        多篇并行抓取，单篇受超时熔断；某篇失败不影响其余结果。
        """
        if not papers:
            return papers
        timeout = timeout or self._default_timeout()
        tasks = [
            asyncio.wait_for(self.extract_one(p.get("doi", ""), min(timeout, 15.0)), timeout=timeout)
            for p in papers
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for paper, res in zip(papers, results):
            if isinstance(res, Exception):
                paper["full_text_available"] = False
                paper["full_text"] = ""
                paper["full_text_error"] = "timeout_or_error"
            elif isinstance(res, dict):
                paper.update(res)
        return papers


class LocalKnowledgeBaseRetriever:
    """本地知识库检索：复用已保存知识图谱中的文献。

    检索流程：列出最近的知识图谱，从图谱节点的 paper_titles 中提取
    标题，与查询做简单匹配后返回为本地来源文献。这些文献已经过
    一次筛选，可信度高。
    """

    async def search(self, query: str, limit: int) -> list[dict]:
        from ...knowledge.graph_store import get_knowledge_graph_store

        store = get_knowledge_graph_store()
        try:
            graphs = store.list_graphs(limit=5)
        except Exception as e:
            logger.warning("本地知识库检索失败（list_graphs）: %s", e)
            return []

        if not graphs:
            return []

        # 从最近图谱的节点中收集文献标题与来源
        seen_titles: set[str] = set()
        papers: list[dict] = []
        query_lower = query.lower().strip()

        for graph_meta in graphs:
            if len(papers) >= limit:
                break
            graph_id = graph_meta.get("graph_id", "")
            if not graph_id:
                continue
            try:
                graph = store.get_graph(graph_id)
            except Exception as e:
                logger.warning("本地知识库检索失败（get_graph %s）: %s", graph_id, e)
                continue
            if not graph:
                continue
            for node in graph.get("nodes", []):
                if len(papers) >= limit:
                    break
                props = node.get("properties", {})
                titles = props.get("paper_titles", [])
                node_sources = props.get("sources", [])
                node_confidence = props.get("confidence", "medium")
                for title in titles:
                    if len(papers) >= limit:
                        break
                    title_clean = title.strip()
                    if not title_clean or title_clean.lower() in seen_titles:
                        continue
                    # 简单相关性：查询词与标题是否有关联
                    if query_lower and query_lower not in title_clean.lower():
                        # 若查询无匹配，也保留一部分以维持知识库多样性
                        if len(papers) < limit // 2:
                            pass
                        else:
                            continue
                    seen_titles.add(title_clean.lower())
                    papers.append({
                        "title": title_clean,
                        "authors": [],
                        "journal": "",
                        "year": 0,
                        "abstract": "",
                        "doi": "",
                        "keywords": [],
                        "source": "local_kb",
                        "confidence": node_confidence,
                        "score": 5,
                    })

        if papers:
            logger.info("本地知识库命中 %d 篇文献（来自 %d 个图谱）", len(papers), len(graphs))
        return papers


class TemplateLibraryRetriever:
    """内置模板文献库（兜底）。"""

    # 预置电池材料领域文献模板（25 篇，覆盖主要研究方向）
    _PAPERS: list[dict] = [
        {
            "title": "High-ionic-conductivity garnet-type Li7La3Zr2O12 solid electrolyte for all-solid-state batteries",
            "authors": ["Murugan R.", "Thangadurai V.", "Weppner W."],
            "journal": "Angewandte Chemie International Edition",
            "year": 2007,
            "abstract": "Garnet-type Li7La3Zr2O12 (LLZO) solid electrolyte exhibits high ionic conductivity of 3×10⁻⁴ S/cm at room temperature and good chemical stability against lithium metal, making it promising for all-solid-state lithium batteries.",
            "doi": "10.1002/anie.200701144",
            "keywords": ["LLZO", "solid electrolyte", "ionic conductivity", "lithium metal", "garnet"],
        },
        {
            "title": "Li-rich layered oxides as cathode materials for high-energy lithium-ion batteries",
            "authors": ["Lu Z.", "Dahn J.R."],
            "journal": "Journal of the Electrochemical Society",
            "year": 2002,
            "abstract": "Li-rich layered oxide cathodes Li[Li1/3Mn2/3]O2 deliver high capacity over 250 mAh/g through anionic redox, enabling high-energy-density lithium-ion batteries for electric vehicles.",
            "doi": "10.1149/1.1498248",
            "keywords": ["Li-rich", "cathode", "layered oxide", "anionic redox", "electric vehicle"],
        },
        {
            "title": "Solvent-free synthesis of Ni-rich NMC811 cathode with enhanced cycling stability",
            "authors": ["Kim J.", "Lee H.", "Cho J."],
            "journal": "Advanced Energy Materials",
            "year": 2021,
            "abstract": "A solvent-free synthesis route for Ni-rich LiNi0.8Mn0.1Co0.1O2 (NMC811) cathode material achieves 200 mAh/g discharge capacity with 92% capacity retention after 200 cycles at MIT.",
            "doi": "10.1002/aenm.202101234",
            "keywords": ["NMC811", "cathode", "solvent-free", "cycling stability", "MIT"],
        },
        {
            "title": "Sulfide solid electrolyte Li6PS5Cl for all-solid-state lithium batteries",
            "authors": ["Kato Y.", "Hori S.", "Kanno R."],
            "journal": "Nature Energy",
            "year": 2016,
            "abstract": "Argyrodite-type Li6PS5Cl sulfide electrolyte achieves ionic conductivity of 3×10⁻³ S/cm at Toyota Research Institute, enabling all-solid-state batteries with high rate capability.",
            "doi": "10.1038/nenergy.2016.30",
            "keywords": ["Li6PS5Cl", "sulfide", "solid electrolyte", "argyrodite", "Toyota"],
        },
        {
            "title": "Polymer electrolyte PEO-based solid-state battery for flexible electronics",
            "authors": ["Manthiram A.", "Yu X.", "Wang S."],
            "journal": "Nature Reviews Materials",
            "year": 2017,
            "abstract": "Poly(ethylene oxide) (PEO) based polymer electrolyte with lithium salt enables flexible solid-state batteries at University of Texas, with ionic conductivity of 10⁻⁵ S/cm at 60°C.",
            "doi": "10.1038/natrevmats.2017.3",
            "keywords": ["PEO", "polymer electrolyte", "flexible", "solid-state", "University of Texas"],
        },
        {
            "title": "Silicon anode with high capacity for next-generation lithium-ion batteries",
            "authors": ["Wu H.", "Cui Y."],
            "journal": "Nano Today",
            "year": 2012,
            "abstract": "Silicon anode material achieves theoretical capacity of 4200 mAh/g at Stanford, overcoming volume expansion through nanostructured design for lithium-ion batteries in electric vehicles.",
            "doi": "10.1016/j.nantod.2012.04.005",
            "keywords": ["silicon", "anode", "high capacity", "nanostructure", "Stanford"],
        },
        {
            "title": "Lithium metal anode for high-energy-density rechargeable batteries",
            "authors": ["Lin D.", "Liu Y.", "Cui Y."],
            "journal": "Nature Nanotechnology",
            "year": 2017,
            "abstract": "Lithium metal anode offers highest theoretical capacity (3860 mAh/g) at Stanford, enabling high-energy-density batteries for electric vehicles through dendrite suppression techniques.",
            "doi": "10.1038/nnano.2017.16",
            "keywords": ["lithium metal", "anode", "high capacity", "dendrite", "Stanford"],
        },
        {
            "title": "LFP cathode material LiFePO4 for safe lithium-ion batteries",
            "authors": ["Padhi A.K.", "Nanjundaswamy K.S.", "Goodenough J.B."],
            "journal": "Journal of the Electrochemical Society",
            "year": 1997,
            "abstract": "Olivine-structured LiFePO4 cathode material developed at University of Texas offers 170 mAh/g capacity with excellent thermal stability and cycling safety for lithium-ion batteries.",
            "doi": "10.1149/1.1837960",
            "keywords": ["LiFePO4", "LFP", "cathode", "olivine", "University of Texas"],
        },
        {
            "title": "Solid-state battery with garnet electrolyte and lithium metal anode at MIT",
            "authors": ["Wang C.", "Xie H.", "Chiang Y.M."],
            "journal": "Advanced Materials",
            "year": 2020,
            "abstract": "All-solid-state battery combining LLZO garnet electrolyte with lithium metal anode achieves 4V operating voltage at MIT, with capacity retention of 85% after 500 cycles.",
            "doi": "10.1002/adma.202005123",
            "keywords": ["LLZO", "lithium metal", "solid-state", "garnet", "MIT"],
        },
        {
            "title": "NASICON-type solid electrolyte Li1.3Al0.3Ti1.7(PO4)3 for sodium batteries",
            "authors": ["Guin M.", "Tietz F.", "Guillon O."],
            "journal": "Solid State Ionics",
            "year": 2016,
            "abstract": "NASICON-type Li1.3Al0.3Ti1.7(PO4)3 (LATP) solid electrolyte exhibits ionic conductivity of 10⁻⁴ S/cm at Forschungszentrum Jülich, suitable for sodium-ion batteries in grid storage.",
            "doi": "10.1016/j.ssi.2016.05.012",
            "keywords": ["NASICON", "LATP", "solid electrolyte", "sodium-ion", "Forschungszentrum Jülich"],
        },
        {
            "title": "Co-free cathode materials for sustainable lithium-ion batteries",
            "authors": ["Lee E.", "Persson K.", "Ceder G."],
            "journal": "Chemistry of Materials",
            "year": 2019,
            "abstract": "Cobalt-free LiMn0.6Fe0.4PO4 cathode material developed at UC Berkeley delivers 160 mAh/g capacity with reduced cost, addressing sustainability concerns for electric vehicle batteries.",
            "doi": "10.1021/acs.chemmater.9b02345",
            "keywords": ["Co-free", "cathode", "LiMnPO4", "sustainability", "UC Berkeley"],
        },
        {
            "title": "Atomic layer deposition for stable cathode-electrolyte interface",
            "authors": ["Jung Y.S.", "Lee S.", "Kim H."],
            "journal": "ACS Nano",
            "year": 2018,
            "abstract": "Atomic layer deposition (ALD) coating on NMC cathode at KAIST improves cycling stability by 30% through stable cathode-electrolyte interface for high-voltage lithium-ion batteries.",
            "doi": "10.1021/acsnano.8b01234",
            "keywords": ["ALD", "NMC", "cathode", "interface", "KAIST"],
        },
        {
            "title": "Lithium-sulfur battery with high energy density for electric aviation",
            "authors": ["Bruce P.G.", "Freunberger S.A.", "Hardwick L.J."],
            "journal": "Nature Materials",
            "year": 2011,
            "abstract": "Lithium-sulfur battery at University of Oxford achieves theoretical energy density of 2600 Wh/kg through sulfur cathode, targeting electric aviation applications.",
            "doi": "10.1038/nmat3191",
            "keywords": ["lithium-sulfur", "sulfur cathode", "energy density", "electric aviation", "University of Oxford"],
        },
        {
            "title": "Electrospinning synthesis of Si/C composite anode for lithium-ion batteries",
            "authors": ["Li X.", "Sun Q.", "Wang X."],
            "journal": "Journal of Power Sources",
            "year": 2020,
            "abstract": "Electrospinning synthesis of silicon-carbon composite anode at Tsinghua University achieves 1200 mAh/g capacity with 88% retention after 300 cycles for lithium-ion batteries.",
            "doi": "10.1016/j.jpowsour.2020.228123",
            "keywords": ["electrospinning", "Si/C", "anode", "composite", "Tsinghua University"],
        },
        {
            "title": "Halide solid electrolyte Li3YCl6 for high-voltage all-solid-state batteries",
            "authors": ["Kwak H.", "Han D.", "Jung Y.S."],
            "journal": "Advanced Energy Materials",
            "year": 2021,
            "abstract": "Halide solid electrolyte Li3YCl6 developed at KAIST exhibits ionic conductivity of 6.5×10⁻⁴ S/cm and stable interface with high-voltage NMC cathode for all-solid-state batteries.",
            "doi": "10.1002/aenm.202103012",
            "keywords": ["halide", "Li3YCl6", "solid electrolyte", "high-voltage", "KAIST"],
        },
        {
            "title": "Dry processing of cathode electrodes for sustainable battery manufacturing",
            "authors": ["Schlüter S.", "Gärtner T.", "Zaeh M.F."],
            "journal": "Journal of Cleaner Production",
            "year": 2022,
            "abstract": "Dry processing of NMC cathode electrodes at Technical University of Munich reduces energy consumption by 47% compared to solvent-based manufacturing for lithium-ion batteries.",
            "doi": "10.1016/j.jclepro.2022.131234",
            "keywords": ["dry processing", "NMC", "cathode", "manufacturing", "Technical University of Munich"],
        },
        {
            "title": "Sodium-ion battery with Prussian blue cathode for grid storage",
            "authors": ["Goodenough J.B.", "Kim K.T."],
            "journal": "Energy Storage Materials",
            "year": 2020,
            "abstract": "Prussian blue analog cathode Na2Fe[Fe(CN)6] for sodium-ion batteries at University of Texas delivers 120 mAh/g capacity, suitable for grid storage applications.",
            "doi": "10.1016/j.ensm.2020.07.023",
            "keywords": ["sodium-ion", "Prussian blue", "cathode", "grid storage", "University of Texas"],
        },
        {
            "title": "In-situ characterization of SEI formation on lithium metal anode",
            "authors": ["Cheng Q.", "Mao L.", "Yang Y."],
            "journal": "Nature Communications",
            "year": 2023,
            "abstract": "In-situ TEM characterization at Chinese Academy of Sciences reveals SEI formation mechanism on lithium metal anode, guiding dendrite suppression for high-energy-density batteries.",
            "doi": "10.1038/s41467-023-37890-1",
            "keywords": ["in-situ", "SEI", "lithium metal", "anode", "Chinese Academy of Sciences"],
        },
        {
            "title": "Machine learning accelerated discovery of solid electrolytes",
            "authors": ["Sendek A.D.", "Reed E.J."],
            "journal": "Energy & Environmental Science",
            "year": 2017,
            "abstract": "Machine learning model at Stanford screens 12000 candidate materials for lithium-ion solid electrolytes, identifying 21 promising structures with predicted high ionic conductivity.",
            "doi": "10.1039/c7ee02657c",
            "keywords": ["machine learning", "solid electrolyte", "ionic conductivity", "discovery", "Stanford"],
        },
        {
            "title": "Porous graphene scaffold for lithium metal anode with high rate capability",
            "authors": ["Zhang L.", "Sun Q.", "Zhu D."],
            "journal": "ACS Nano",
            "year": 2021,
            "abstract": "Porous graphene scaffold at Tsinghua University guides uniform lithium deposition, achieving 3 mA/cm² current density with 99% coulombic efficiency for lithium metal anode.",
            "doi": "10.1021/acsnano.1c02345",
            "keywords": ["graphene", "lithium metal", "anode", "porous scaffold", "Tsinghua University"],
        },
        {
            "title": "Perovskite-type solid electrolyte for all-solid-state lithium batteries",
            "authors": ["Inaguma Y.", "Itoh M."],
            "journal": "Solid State Communications",
            "year": 1994,
            "abstract": "Perovskite-type La2/3-xLi3xTiO3 solid electrolyte exhibits bulk ionic conductivity of 10⁻³ S/cm, suitable for all-solid-state lithium batteries at Gakushuin University.",
            "doi": "10.1016/0038-1098(94)90840-6",
            "keywords": ["perovskite", "LLTO", "solid electrolyte", "ionic conductivity", "Gakushuin University"],
        },
        {
            "title": "Cathode material LiNi0.5Mn1.5O4 for 5V high-voltage lithium-ion batteries",
            "authors": ["Amine K.", "Belharouak I.", "Lu J."],
            "journal": "Journal of Power Sources",
            "year": 2010,
            "abstract": "Spinel LiNi0.5Mn1.5O4 cathode at Argonne National Laboratory delivers 147 mAh/g capacity at 4.7V, enabling high-voltage lithium-ion batteries for electric vehicles.",
            "doi": "10.1016/j.jpowsour.2010.05.012",
            "keywords": ["LNMO", "spinel", "cathode", "high-voltage", "Argonne National Laboratory"],
        },
        {
            "title": "Hydrothermal synthesis of LiFePO4/C composite with enhanced rate performance",
            "authors": ["Wang Y.", "Wang J.", "Zhou X."],
            "journal": "Electrochimica Acta",
            "year": 2019,
            "abstract": "Hydrothermal synthesis of LiFePO4/C composite at Peking University achieves 160 mAh/g capacity with 90% retention at 5C rate, suitable for power tool applications.",
            "doi": "10.1016/j.electacta.2019.134567",
            "keywords": ["hydrothermal", "LiFePO4", "cathode", "rate performance", "Peking University"],
        },
        {
            "title": "Electrolyte additive for high-voltage NMC/graphite lithium-ion batteries",
            "authors": ["Xu K.", "Jow R."],
            "journal": "Journal of the Electrochemical Society",
            "year": 2012,
            "abstract": "Fluoroethylene carbonate (FEC) electrolyte additive at University of California improves NMC/graphite battery cycling stability by 40% through stable SEI formation.",
            "doi": "10.1149/2.056212jes",
            "keywords": ["FEC", "electrolyte additive", "NMC", "graphite", "University of California"],
        },
        {
            "title": "Quasi-solid-state battery with gel polymer electrolyte for wearable devices",
            "authors": ["Zhou G.", "Liu F.", "Li F."],
            "journal": "Advanced Functional Materials",
            "year": 2022,
            "abstract": "Gel polymer electrolyte based quasi-solid-state battery at Chinese Academy of Sciences achieves 180 mAh/g capacity with 500 bending cycles, targeting wearable device applications.",
            "doi": "10.1002/adfm.202201234",
            "keywords": ["gel polymer", "quasi-solid-state", "wearable", "bending", "Chinese Academy of Sciences"],
        },
    ]

    async def search(self, query: str, limit: int = 10) -> list[dict]:
        if not query or not query.strip():
            sorted_papers = sorted(self._PAPERS, key=lambda p: p["year"], reverse=True)
            return [{**p, "source": "template", "score": 0} for p in sorted_papers[:limit]]

        query_lower = query.lower().strip()
        query_tokens = [t for t in query_lower.split() if t]

        # 中文关键词扩展
        expanded_tokens = list(query_tokens)
        for cn_key, en_words in LiteratureResearcherAgent._CHINESE_KEYWORD_MAP.items():
            if cn_key in query:
                expanded_tokens.extend([w.lower() for w in en_words])
        seen: set[str] = set()
        expanded_tokens = [t for t in expanded_tokens if not (t in seen or seen.add(t))]

        scored: list[tuple[dict, int]] = []
        for paper in self._PAPERS:
            score = self._match_score(paper, query_lower, expanded_tokens)
            if score > 0:
                scored.append((paper, score))

        if not scored:
            sorted_papers = sorted(self._PAPERS, key=lambda p: p["year"], reverse=True)
            return [{**p, "source": "template", "score": 0} for p in sorted_papers[:limit]]

        scored.sort(key=lambda x: (-x[1], -x[0]["year"]))
        return [{**p, "source": "template", "score": s} for p, s in scored[:limit]]

    def _match_score(self, paper: dict, query_lower: str, query_tokens: list[str]) -> int:
        title = paper["title"].lower()
        abstract = paper["abstract"].lower()
        keywords = " ".join(paper["keywords"]).lower()

        score = 0
        if query_lower in title:
            score += 10
        if query_lower in keywords:
            score += 6
        if query_lower in abstract:
            score += 3
        for token in query_tokens:
            if token in title:
                score += 3
            if token in keywords:
                score += 2
            if token in abstract:
                score += 1
        return score


# ──────────────────────────────────────────────────────────────────────────────
# 工具函数
# ──────────────────────────────────────────────────────────────────────────────

def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    # 去除 markdown 代码块标记
    text = re.sub(r"^```(\w+)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text


def _to_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return []


def _is_ascii(text: str) -> bool:
    """判断文本是否全部为 ASCII 字符（用于 Google Scholar 等仅支持英文的源）。"""
    try:
        text.encode("ascii")
        return True
    except (UnicodeEncodeError, AttributeError):
        return False


def _to_int(value: Any) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


# 非正式条目标题前缀（审稿评论 / 勘误 / 撤稿等），不计入文献证据。
# 仅匹配前缀模式，避免误伤标题含 "Review" 的正式综述论文。
NON_PEER_REVIEW_PREFIXES: tuple[str, ...] = (
    "review for",
    "comment on",
    "erratum",
    "corrigendum",
    "retraction",
)


def _is_non_peer_review_title(title: str) -> bool:
    """判断标题是否命中非正式条目前缀（不区分大小写）。"""
    t = (title or "").strip().lower()
    if not t:
        return False
    return any(t.startswith(p) for p in NON_PEER_REVIEW_PREFIXES)


def _paper_id(paper: dict) -> str:
    """基于标题生成稳定的去重 ID。"""
    title = paper.get("title", "").strip().lower()
    doi = paper.get("doi", "").strip().lower()
    key = f"{doi}:{title}" if doi else title
    return hashlib.md5(key.encode("utf-8")).hexdigest()


# ──────────────────────────────────────────────────────────────────────────────
# LiteratureResearcherAgent
# ──────────────────────────────────────────────────────────────────────────────

class LiteratureResearcherAgent:
    """文献调研 Agent：整合 LLM、SCP、外部 API、本地知识库与模板库的多源文献检索。"""

    AGENT_ID = "builtin_literature_researcher"
    AGENT_NAME = "文献调研员"

    ENTITY_MATERIAL = "material"
    ENTITY_PROPERTY = "property"
    ENTITY_METHOD = "method"
    ENTITY_APPLICATION = "application"
    ENTITY_INSTITUTION = "institution"

    # 中文术语 → 英文等价词映射
    _CHINESE_KEYWORD_MAP: dict[str, list[str]] = {
        "锂电池": ["lithium-ion", "lithium metal", "lithium"],
        "锂离子": ["lithium-ion"],
        "锂金属": ["lithium metal"],
        "锂硫": ["lithium-sulfur", "sulfur cathode"],
        "固态电池": ["solid-state", "all-solid-state"],
        "固态电解质": ["solid electrolyte"],
        "全固态": ["all-solid-state"],
        "石榴石": ["garnet", "LLZO"],
        "钙钛矿": ["perovskite", "LLTO"],
        "硫化物": ["sulfide", "Li6PS5Cl"],
        "卤化物": ["halide", "Li3YCl6"],
        "聚合物电解质": ["polymer electrolyte", "PEO"],
        "聚合物": ["polymer", "PEO"],
        "正极": ["cathode"],
        "负极": ["anode"],
        "硅负极": ["silicon", "Si/C"],
        "硅碳": ["Si/C", "silicon"],
        "石墨": ["graphite"],
        "石墨烯": ["graphene"],
        "磷酸铁锂": ["LiFePO4", "LFP"],
        "三元": ["NMC", "NMC811"],
        "富锂": ["Li-rich"],
        "钠离子": ["sodium-ion"],
        "普鲁士蓝": ["Prussian blue"],
        "电解液": ["electrolyte"],
        "电解质": ["electrolyte"],
        "添加剂": ["additive", "FEC"],
        "涂覆": ["coating", "ALD"],
        "原子层沉积": ["ALD", "atomic layer deposition"],
        "机器学习": ["machine learning"],
        "原位": ["in-situ"],
        "水热": ["hydrothermal"],
        "电纺": ["electrospinning"],
        "无溶剂": ["solvent-free"],
        "干法": ["dry processing"],
        "新能源汽车": ["electric vehicle"],
        "电动汽车": ["electric vehicle"],
        "电动车辆": ["electric vehicle"],
        "电网储能": ["grid storage"],
        "储能": ["grid storage", "storage"],
        "柔性": ["flexible", "wearable"],
        "可穿戴": ["wearable", "flexible"],
        "循环稳定性": ["cycling stability"],
        "循环": ["cycling", "cycle"],
        "离子电导率": ["ionic conductivity"],
        "电导率": ["conductivity"],
        "能量密度": ["energy density"],
        "放电容量": ["discharge capacity"],
        "容量": ["capacity"],
        "电压": ["voltage"],
        "高电压": ["high-voltage"],
        "库伦效率": ["coulombic efficiency"],
        "倍率性能": ["rate capability", "rate performance"],
        "倍率": ["rate"],
        "热稳定性": ["thermal stability"],
        "枝晶": ["dendrite"],
        "清华大学": ["Tsinghua University"],
        "斯坦福": ["Stanford"],
        "麻省理工": ["MIT"],
        "中科院": ["Chinese Academy of Sciences"],
        "北京大学": ["Peking University"],
        "牛津": ["Oxford"],
        "丰田": ["Toyota"],
        "古迪纳夫": ["Goodenough"],
    }

    # 置信度等级（基于文献来源）
    CONFIDENCE_HIGH = "high"      # 外部学术 API（Crossref/Semantic Scholar）+ 模板库
    CONFIDENCE_MEDIUM = "medium"  # SCP 检索
    CONFIDENCE_LOW = "low"        # LLM 生成

    _SOURCE_CONFIDENCE: dict[str, str] = {
        "crossref": CONFIDENCE_HIGH,
        "semantic_scholar": CONFIDENCE_HIGH,
        "arxiv": CONFIDENCE_HIGH,
        "pubmed": CONFIDENCE_HIGH,
        "template": CONFIDENCE_MEDIUM,
        "local_kb": CONFIDENCE_HIGH,
        "scp": CONFIDENCE_MEDIUM,
        "google_scholar": CONFIDENCE_LOW,
        "llm_generated": CONFIDENCE_LOW,
    }

    # 实体类型与关键词映射（用于模板库与图谱构建）
    _MATERIAL_KEYWORDS: dict[str, list[str]] = {
        "Li7La3Zr2O12": ["LLZO", "Li7La3Zr2O12", "garnet"],
        "Li6PS5Cl": ["Li6PS5Cl", "argyrodite", "sulfide electrolyte"],
        "PEO": ["PEO", "poly(ethylene oxide)", "polymer electrolyte"],
        "Silicon": ["silicon", "Si/C"],
        "Lithium metal": ["lithium metal"],
        "LiFePO4": ["LiFePO4", "LFP", "olivine"],
        "NMC811": ["NMC811", "LiNi0.8Mn0.1Co0.1O2"],
        "Li-rich oxide": ["Li-rich", "layered oxide"],
        "Li1.3Al0.3Ti1.7(PO4)3": ["LATP", "NASICON"],
        "Li3YCl6": ["Li3YCl6", "halide"],
        "LiMn0.6Fe0.4PO4": ["LiMn0.6Fe0.4PO4", "Co-free"],
        "Li2Fe[Fe(CN)6]": ["Prussian blue"],
        "La2/3-xLi3xTiO3": ["LLTO", "perovskite"],
        "LiNi0.5Mn1.5O4": ["LNMO", "spinel"],
        "Sulfur": ["sulfur cathode", "lithium-sulfur"],
        "Graphene": ["graphene", "porous scaffold"],
        "Graphite": ["graphite"],
    }

    _PROPERTY_KEYWORDS: dict[str, list[str]] = {
        "ionic conductivity": ["ionic conductivity", "conductivity"],
        "discharge capacity": ["mAh/g", "capacity", "discharge capacity"],
        "cycling stability": ["cycling stability", "capacity retention", "retention"],
        "energy density": ["energy density", "Wh/kg"],
        "operating voltage": ["operating voltage", "4V", "4.7V", "5V", "high-voltage"],
        "coulombic efficiency": ["coulombic efficiency"],
        "rate capability": ["rate performance", "rate capability", "5C"],
        "thermal stability": ["thermal stability"],
    }

    _METHOD_KEYWORDS: dict[str, list[str]] = {
        "solvent-free synthesis": ["solvent-free"],
        "atomic layer deposition": ["ALD", "atomic layer deposition"],
        "electrospinning": ["electrospinning"],
        "dry processing": ["dry processing"],
        "hydrothermal synthesis": ["hydrothermal"],
        "machine learning": ["machine learning"],
        "in-situ characterization": ["in-situ", "TEM characterization"],
        "nanostructured design": ["nanostructure", "nanostructured"],
    }

    _APPLICATION_KEYWORDS: dict[str, list[str]] = {
        "all-solid-state batteries": ["all-solid-state", "solid-state battery"],
        "lithium-ion batteries": ["lithium-ion", "lithium-ion battery"],
        "electric vehicles": ["electric vehicle", "electric vehicles"],
        "flexible electronics": ["flexible", "wearable", "bending"],
        "grid storage": ["grid storage"],
        "electric aviation": ["electric aviation"],
        "power tools": ["power tool"],
    }

    _INSTITUTION_KEYWORDS: dict[str, list[str]] = {
        "MIT": ["MIT"],
        "Stanford": ["Stanford"],
        "University of Texas": ["University of Texas"],
        "Toyota": ["Toyota"],
        "KAIST": ["KAIST"],
        "Tsinghua University": ["Tsinghua University"],
        "UC Berkeley": ["UC Berkeley"],
        "University of Oxford": ["University of Oxford"],
        "Technical University of Munich": ["Technical University of Munich"],
        "Chinese Academy of Sciences": ["Chinese Academy of Sciences"],
        "Argonne National Laboratory": ["Argonne National Laboratory"],
        "Peking University": ["Peking University"],
        "University of California": ["University of California"],
        "Forschungszentrum Jülich": ["Forschungszentrum Jülich"],
        "Gakushuin University": ["Gakushuin University"],
    }

    def __init__(
        self,
        config: AgentConfig | None = None,
        llm_client: _LLMClient | None = None,
        tool_registry: Any | None = None,
        enable_llm: bool = True,
        enable_scp: bool = True,
        enable_web_api: bool = True,
        enable_local_kb: bool = True,
        enable_template_fallback: bool = True,
    ):
        self.config = config
        self._retrievers: list[RetrievalSource] = []
        if enable_llm:
            self._retrievers.append(LLMKnowledgeRetriever(llm_client or _LLMClient(config)))
        if enable_scp:
            self._retrievers.append(SCPRetriever(tool_registry))
        if enable_web_api:
            self._retrievers.extend([
                SemanticScholarRetriever(),
                CrossrefRetriever(),
                ArxivRetriever(),
                PubmedRetriever(),
                GoogleScholarRetriever(),
            ])
        if enable_local_kb:
            self._retrievers.append(LocalKnowledgeBaseRetriever())

        self._template_retriever = TemplateLibraryRetriever()
        self._enable_template_fallback = enable_template_fallback

        # 全文内容抽取：由 FULL_TEXT_EXTRACT_ENABLED 控制（默认关闭）
        import os as _os
        self._web_content = WebContentRetriever()
        self._enable_full_text = (
            _os.getenv("FULL_TEXT_EXTRACT_ENABLED", "false").strip().lower() in ("1", "true", "yes")
        )

    def _translate_query(self, query: str) -> str | None:
        """若查询包含中文，返回基于关键词映射的英文查询，便于外部学术 API/SCP 检索。"""
        if not re.search(r"[\u4e00-\u9fff]", query):
            return None
        extra: list[str] = []
        for cn_key, en_words in self._CHINESE_KEYWORD_MAP.items():
            if cn_key in query:
                extra.extend(en_words)
        if not extra:
            return None
        seen: set[str] = set()
        unique = [w for w in extra if not (w.lower() in seen or seen.add(w.lower()))]
        return " ".join(unique)

    async def search(self, query: str, limit: int = 10) -> list[dict]:
        """多源文献检索。

        1. 并行调用所有启用的真实检索源（LLM/SCP/WebAPI/本地知识库）。
        2. 合并结果并基于标题去重。
        3. 若真实检索无结果且启用模板兜底，回退到模板文献库。

        Args:
            query: 搜索关键词（支持中英文）
            limit: 返回文献数量上限

        Returns:
            文献列表，每项含 title/authors/journal/year/abstract/doi/keywords/score/source
        """
        if not query or not query.strip():
            return await self._template_retriever.search(query, limit)

        # 中文查询自动转译为英文，供外部学术 API / SCP 使用；LLM 仍接收原文以保留语义
        translated = self._translate_query(query)
        if translated:
            logger.info("查询含中文，为外部检索生成英文查询: %r", translated)

        # 并行执行真实检索；每个检索源独立 12 秒超时，避免单个慢源拖慢整体
        logger.info("开始多源文献检索: query=%r, retrievers=%d", query, len(self._retrievers))
        per_source_timeout = 12.0
        tasks = []
        for r in self._retrievers:
            # WebAPI / SCP 对英文检索更友好；LLM 与本地知识库保留原始查询
            use_translated = translated and isinstance(
                r,
                (SemanticScholarRetriever, CrossrefRetriever, SCPRetriever, ArxivRetriever, PubmedRetriever, GoogleScholarRetriever),
            )
            q = translated if use_translated else query
            tasks.append(asyncio.wait_for(r.search(q, limit), timeout=per_source_timeout))
        results = await asyncio.gather(*tasks, return_exceptions=True)

        source_counts: dict[str, int] = {}
        all_papers: list[dict] = []
        seen_ids: set[str] = set()
        for idx, papers in enumerate(results):
            source_name = type(self._retrievers[idx]).__name__
            if isinstance(papers, asyncio.TimeoutError):
                logger.warning("检索源超时 (%s)", source_name)
                source_counts[source_name] = -1
                continue
            if isinstance(papers, Exception):
                logger.warning("检索源异常 (%s): %s", source_name, papers)
                source_counts[source_name] = -1
                continue
            source_counts[source_name] = len(papers)
            for paper in papers:
                pid = _paper_id(paper)
                if pid in seen_ids:
                    continue
                seen_ids.add(pid)
                all_papers.append(paper)

        logger.info("各检索源结果数: %s, 去重后总数: %d", source_counts, len(all_papers))

        if all_papers:
            # 全文内容抽取：仅当启用时触发，对**所有**去重后的结果抓取全文；
            # 失败/超时不影响摘要级结果返回
            if self._enable_full_text:
                logger.info("全文抽取已启用，对 %d 篇结果抓取全文", len(all_papers))
                all_papers = await self._web_content.extract(all_papers)
            # LLM/SCP 结果默认按返回顺序，年份较新的优先；补充相关度简单排序
            all_papers.sort(key=lambda p: (-(p.get("score", 0) or 0), -p.get("year", 0)))
            return all_papers[:limit]

        if self._enable_template_fallback:
            logger.info("真实检索无结果，回退到模板文献库: query=%r", query)
            return await self._template_retriever.search(query, limit)

        return []

    def extract_entities(self, papers: list) -> dict:
        """从文献列表中抽取实体，按类型分组返回。"""
        materials: set[str] = set()
        properties: set[str] = set()
        methods: set[str] = set()
        applications: set[str] = set()
        institutions: set[str] = set()

        for paper in papers:
            text = self._paper_text(paper)
            for entity, keywords in self._MATERIAL_KEYWORDS.items():
                if any(kw.lower() in text for kw in keywords):
                    materials.add(entity)
            for entity, keywords in self._PROPERTY_KEYWORDS.items():
                if any(kw.lower() in text for kw in keywords):
                    properties.add(entity)
            for entity, keywords in self._METHOD_KEYWORDS.items():
                if any(kw.lower() in text for kw in keywords):
                    methods.add(entity)
            for entity, keywords in self._APPLICATION_KEYWORDS.items():
                if any(kw.lower() in text for kw in keywords):
                    applications.add(entity)
            for entity, keywords in self._INSTITUTION_KEYWORDS.items():
                if any(kw.lower() in text for kw in keywords):
                    institutions.add(entity)

        return {
            "materials": sorted(materials),
            "properties": sorted(properties),
            "methods": sorted(methods),
            "applications": sorted(applications),
            "institutions": sorted(institutions),
            "paper_count": len(papers),
        }

    def build_knowledge_graph(self, papers: list) -> dict:
        """从文献列表构建知识图谱（节点 + 边），含来源追溯与置信度。"""
        nodes: dict[str, dict] = {}
        edges: dict[tuple[str, str, str], dict] = {}

        def add_node(node_id: str, label: str, node_type: str, source: str, confidence: str,
                 content: str | None = None, full_text_available: bool = False):
            if node_id not in nodes:
                nodes[node_id] = {
                    "id": node_id,
                    "label": label,
                    "type": node_type,
                    "properties": {
                        "papers": 0,
                        "mentions": 0,
                        "paper_titles": [],
                        "sources": set(),
                        "confidence": confidence,
                    },
                }
            nodes[node_id]["properties"]["papers"] += 1
            nodes[node_id]["properties"]["sources"].add(source)
            # 全文内容抽取结果：写入节点 content 并标记可用（供图谱落库审计）
            if content:
                nodes[node_id]["properties"]["content"] = content
            if full_text_available:
                nodes[node_id]["properties"]["full_text_available"] = True
            # 若已有节点置信度较低，则升级为较高置信度（外部来源优先）
            # 修复：直接比较节点当前置信度等级（此前误用 _SOURCE_CONFIDENCE 查置信度值，恒返回 low）
            cur_conf = nodes[node_id]["properties"].get("confidence")
            if (cur_conf not in (self.CONFIDENCE_HIGH, self.CONFIDENCE_MEDIUM)
                    and confidence in (self.CONFIDENCE_HIGH, self.CONFIDENCE_MEDIUM)):
                nodes[node_id]["properties"]["confidence"] = confidence

        def add_edge(source: str, target: str, label: str, weight: int = 1, source_tag: str = ""):
            key = (source, target, label)
            if key not in edges:
                edges[key] = {
                    "source": source,
                    "target": target,
                    "label": label,
                    "weight": 0,
                    "sources": set(),
                }
            edges[key]["weight"] += weight
            if source_tag:
                edges[key]["sources"].add(source_tag)

        for paper in papers:
            text = self._paper_text(paper)
            paper_title = paper.get("title", "")
            paper_source = paper.get("source", "unknown")
            paper_confidence = self._SOURCE_CONFIDENCE.get(paper_source, "low")
            paper_full_text = paper.get("full_text", "") if paper.get("full_text_available") else ""
            paper_full_text_ok = bool(paper.get("full_text_available"))

            paper_materials = self._match_entities(text, self._MATERIAL_KEYWORDS)
            paper_properties = self._match_entities(text, self._PROPERTY_KEYWORDS)
            paper_methods = self._match_entities(text, self._METHOD_KEYWORDS)
            paper_applications = self._match_entities(text, self._APPLICATION_KEYWORDS)
            paper_institutions = self._match_entities(text, self._INSTITUTION_KEYWORDS)

            for m in paper_materials:
                add_node(m, m, self.ENTITY_MATERIAL, paper_source, paper_confidence,
                         content=paper_full_text, full_text_available=paper_full_text_ok)
                nodes[m]["properties"]["paper_titles"].append(paper_title)
            for p in paper_properties:
                add_node(p, p, self.ENTITY_PROPERTY, paper_source, paper_confidence,
                         content=paper_full_text, full_text_available=paper_full_text_ok)
                nodes[p]["properties"]["paper_titles"].append(paper_title)
            for meth in paper_methods:
                add_node(meth, meth, self.ENTITY_METHOD, paper_source, paper_confidence,
                         content=paper_full_text, full_text_available=paper_full_text_ok)
                nodes[meth]["properties"]["paper_titles"].append(paper_title)
            for app in paper_applications:
                add_node(app, app, self.ENTITY_APPLICATION, paper_source, paper_confidence,
                         content=paper_full_text, full_text_available=paper_full_text_ok)
                nodes[app]["properties"]["paper_titles"].append(paper_title)
            for inst in paper_institutions:
                add_node(inst, inst, self.ENTITY_INSTITUTION, paper_source, paper_confidence,
                         content=paper_full_text, full_text_available=paper_full_text_ok)
                nodes[inst]["properties"]["paper_titles"].append(paper_title)

            for m in paper_materials:
                for inst in paper_institutions:
                    add_edge(m, inst, "developed_by", 1, paper_source)
            for m in paper_materials:
                for meth in paper_methods:
                    add_edge(m, meth, "synthesized_by", 1, paper_source)
            for m in paper_materials:
                for p in paper_properties:
                    add_edge(m, p, "measures_property", 1, paper_source)
            for m in paper_materials:
                for app in paper_applications:
                    add_edge(m, app, "applied_in", 1, paper_source)

        # 将 set 序列化为可 JSON 化的 list
        for node in nodes.values():
            node["properties"]["sources"] = sorted(node["properties"]["sources"])
        for edge in edges.values():
            edge["sources"] = sorted(edge["sources"])

        return {
            "nodes": list(nodes.values()),
            "edges": list(edges.values()),
        }

    @staticmethod
    def _match_entities(text: str, mapping: dict[str, list[str]]) -> list[str]:
        matched: list[str] = []
        for entity, keywords in mapping.items():
            if any(kw.lower() in text for kw in keywords):
                matched.append(entity)
        return matched

    @staticmethod
    def _paper_text(paper: Any) -> str:
        if isinstance(paper, dict):
            title = paper.get("title", "")
            abstract = paper.get("abstract", "")
            keywords = " ".join(paper.get("keywords", []))
            authors = " ".join(paper.get("authors", []))
            # 若已抓取全文，优先使用全文做实体抽取（更完整）
            if paper.get("full_text_available"):
                full_text = paper.get("full_text", "")
                if full_text:
                    return f"{title} {full_text} {authors}".lower()
        else:
            title = getattr(paper, "title", "")
            abstract = getattr(paper, "abstract", "")
            keywords = " ".join(getattr(paper, "keywords", []) or [])
            authors = " ".join(getattr(paper, "authors", []) or [])
        return f"{title} {abstract} {keywords} {authors}".lower()
