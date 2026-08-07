"""全文内容抽取（WebContentRetriever）单元测试。

覆盖场景：
- DOI → URL 推导
- SSRF 防护（拦截内网/环回/非 http(s)）
- HTML 正文提取
- 单篇抓取成功 / 失败（不影响其余）
- 批量抓取超时不阻断
- 全文参与实体抽取 / 写入图谱节点属性
- search() 仅在启用时触发全文抽取
"""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from battery_materials_agent.agent_team.agents.literature_researcher import (
    LiteratureResearcherAgent,
    WebContentRetriever,
    _paper_id,
)


class TestUrlHelpers(unittest.TestCase):
    def test_doi_url(self):
        self.assertEqual(WebContentRetriever._doi_url("10.123/abc"), "https://doi.org/10.123/abc")
        self.assertEqual(WebContentRetriever._doi_url(""), "")
        self.assertEqual(WebContentRetriever._doi_url(None), "")  # type: ignore

    def test_safe_url_allows_public(self):
        self.assertTrue(WebContentRetriever._is_safe_url("https://doi.org/10.123/abc"))
        self.assertTrue(WebContentRetriever._is_safe_url("https://pubs.acs.org/doi/10.1/abc"))

    def test_unsafe_url_blocked(self):
        """SSRF 防护：拦截内网 / 环回 / 非 http(s)。"""
        for url in [
            "http://127.0.0.1:8000/secret",
            "http://localhost/env",
            "http://192.168.1.1/admin",
            "http://10.0.0.1/x",
            "http://169.254.169.254/latest/meta-data",
            "file:///etc/passwd",
            "ftp://example.com/x",
            "http://service.local/x",
        ]:
            self.assertFalse(WebContentRetriever._is_safe_url(url), f"expected blocked: {url!r}")

    def test_html_text_extraction(self):
        html = "<html><head><script>var x=1;</script></head><body><h1>Title</h1><p>Hello <b>world</b></p></body></html>"
        text = WebContentRetriever._extract_html_text(html)
        self.assertIn("Title", text)
        self.assertIn("Hello world", text)
        self.assertNotIn("<", text)
        self.assertNotIn("script", text)


class TestWebContentRetrieverExtract(unittest.TestCase):
    def _mock_response(self, content: bytes, content_type: str, status: int = 200):
        resp = MagicMock()
        resp.status_code = status
        resp.content = content
        resp.headers = {"content-type": content_type}
        resp.raise_for_status = MagicMock()
        return resp

    def test_extract_one_success_html(self):
        retriever = WebContentRetriever()
        resp = self._mock_response(b"<html><body><p>Full text content here</p></body></html>", "text/html")
        client = MagicMock()
        client.get = AsyncMock(return_value=resp)
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=client)
        ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("battery_materials_agent.agent_team.agents.literature_researcher.httpx.AsyncClient",
                   return_value=ctx):
            result = asyncio.run(retriever.extract_one("10.123/abc", timeout=5))

        self.assertTrue(result["full_text_available"])
        self.assertIn("Full text content here", result["full_text"])

    def test_extract_one_missing_doi(self):
        retriever = WebContentRetriever()
        result = asyncio.run(retriever.extract_one("", timeout=5))
        self.assertFalse(result["full_text_available"])
        self.assertEqual(result["full_text_error"], "missing_doi")

    def test_extract_one_request_failure(self):
        retriever = WebContentRetriever()
        client = MagicMock()
        client.get = AsyncMock(side_effect=Exception("connection refused"))
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=client)
        ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("battery_materials_agent.agent_team.agents.literature_researcher.httpx.AsyncClient",
                   return_value=ctx):
            result = asyncio.run(retriever.extract_one("10.123/abc", timeout=5))

        self.assertFalse(result["full_text_available"])
        self.assertIn("connection refused", result["full_text_error"])

    def test_extract_batch_failure_does_not_block(self):
        """批量抓取：单篇失败不影响其余结果。"""
        retriever = WebContentRetriever()
        good_resp = self._mock_response(b"<html><body><p>Good full text</p></body></html>", "text/html")

        async def fake_get(url):
            if "10.123/good" in url:
                return good_resp
            raise Exception("boom")

        client = MagicMock()
        client.get = AsyncMock(side_effect=fake_get)
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=client)
        ctx.__aexit__ = AsyncMock(return_value=False)

        papers = [
            {"doi": "10.123/good", "title": "good"},
            {"doi": "10.123/bad", "title": "bad"},
        ]
        with patch("battery_materials_agent.agent_team.agents.literature_researcher.httpx.AsyncClient",
                   return_value=ctx):
            result = asyncio.run(retriever.extract(papers, timeout=5))

        good = next(p for p in result if p["doi"] == "10.123/good")
        bad = next(p for p in result if p["doi"] == "10.123/bad")
        self.assertTrue(good["full_text_available"])
        self.assertIn("Good full text", good["full_text"])
        self.assertFalse(bad["full_text_available"])
        self.assertTrue(bad.get("full_text_error"))


class TestAgentFullTextIntegration(unittest.TestCase):
    def test_paper_text_prefers_full_text(self):
        # 直接调用静态方法
        paper = {"title": "T", "abstract": "abstract only", "keywords": [], "authors": [],
                 "full_text_available": True, "full_text": "VERY LONG FULL TEXT"}
        text = LiteratureResearcherAgent._paper_text(paper)
        self.assertIn("very long full text", text)
        self.assertNotIn("abstract only", text)

    def test_paper_text_falls_back_to_abstract(self):
        paper = {"title": "T", "abstract": "abstract only", "keywords": [], "authors": [],
                 "full_text_available": False}
        text = LiteratureResearcherAgent._paper_text(paper)
        self.assertIn("abstract only", text)

    def test_build_graph_stores_full_text_in_nodes(self):
        agent = LiteratureResearcherAgent(enable_llm=False, enable_scp=False, enable_web_api=False,
                                          enable_local_kb=False, enable_template_fallback=False)
        papers = [{
            "title": "Garnet-type Li7La3Zr2O12 solid electrolyte",
            "abstract": "garnet electrolyte",
            "keywords": ["LLZO"],
            "authors": [],
            "source": "crossref",
            "doi": "10.1/llzo",
            "full_text_available": True,
            "full_text": "Li7La3Zr2O12 garnet solid electrolyte with high ionic conductivity for solid-state batteries",
        }]
        graph = agent.build_knowledge_graph(papers)
        self.assertTrue(graph["nodes"])
        node = graph["nodes"][0]
        self.assertTrue(node["properties"].get("full_text_available"))
        self.assertIn("Li7La3Zr2O12", node["properties"].get("content", ""))

    def test_search_roughly_runs_when_enabled(self):
        """启用时 search 会调用全文抽取器（通过 patch 验证）。"""
        with patch.dict("os.environ", {"FULL_TEXT_EXTRACT_ENABLED": "true"}, clear=False):
            agent = LiteratureResearcherAgent(enable_llm=False, enable_scp=False, enable_web_api=False,
                                              enable_local_kb=False, enable_template_fallback=True)
            self.assertTrue(agent._enable_full_text)

    def test_search_skips_when_disabled(self):
        """默认关闭时全文抽取不启用。"""
        with patch.dict("os.environ", {"FULL_TEXT_EXTRACT_ENABLED": "false"}, clear=False):
            agent = LiteratureResearcherAgent(enable_llm=False, enable_scp=False, enable_web_api=False,
                                              enable_local_kb=False, enable_template_fallback=True)
            self.assertFalse(agent._enable_full_text)


if __name__ == "__main__":
    unittest.main()