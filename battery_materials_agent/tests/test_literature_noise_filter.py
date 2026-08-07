"""文献检索质量过滤单元测试。

覆盖场景：
- 非正式条目前缀（Review for / Comment on / Erratum / Corrigendum / Retraction）被过滤
- 前缀匹配不区分大小写
- 含 "Review" 的正式综述不被误伤
- Crossref / SemanticScholar 检索器实际应用过滤
"""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from battery_materials_agent.agent_team.agents.literature_researcher import (
    CrossrefRetriever,
    SemanticScholarRetriever,
    _is_non_peer_review_title,
)


class TestNoiseFilter(unittest.TestCase):
    def test_common_prefixes_flagged(self):
        """常见非正式条目前缀应被识别为应过滤条目。"""
        cases = [
            "Review for: A new battery",
            "Comment on 'Lithium anodes'",
            "Erratum to the paper",
            "Corrigendum: methods section",
            "Retraction notice",
        ]
        for t in cases:
            self.assertTrue(_is_non_peer_review_title(t), f"expected flagged: {t!r}")

    def test_case_insensitive(self):
        """前缀匹配不区分大小写。"""
        self.assertTrue(_is_non_peer_review_title("REVIEW FOR: X"))
        self.assertTrue(_is_non_peer_review_title("eRrAtUm: X"))
        self.assertTrue(_is_non_peer_review_title("Comment On: X"))

    def test_formal_review_not_flagged(self):
        """正式综述（标题含 Review 但非前缀匹配）不应被误伤。"""
        cases = [
            "A review of solid-state electrolytes for lithium batteries",
            "Review: advances in NMC cathode materials",
            "The lithium-ion battery: a comprehensive review",
            "Review article on sulfide solid electrolytes",
        ]
        for t in cases:
            self.assertFalse(_is_non_peer_review_title(t), f"expected kept: {t!r}")

    def test_normal_papers_not_flagged(self):
        """普通论文标题不应被过滤。"""
        for t in [
            "High-ionic-conductivity garnet-type Li7La3Zr2O12",
            "Machine learning accelerated discovery of solid electrolytes",
            "Commentary on electrolyte additives",  # 含 comment 但非前缀
        ]:
            self.assertFalse(_is_non_peer_review_title(t))

    def test_empty_title(self):
        """空标题返回 False（不触发过滤）。"""
        self.assertFalse(_is_non_peer_review_title(""))
        self.assertFalse(_is_non_peer_review_title(None))  # type: ignore


def _mock_httpx(json_data: dict):
    """构造一个返回固定 JSON 的 httpx.AsyncClient mock。

    用法：
        with patch("...httpx.AsyncClient", return_value=ctx):
            ...
    其中 ctx 需为 AsyncContextManager，__aenter__ 返回 fake client。
    """
    fake_response = MagicMock()
    fake_response.raise_for_status = MagicMock()
    fake_response.json = MagicMock(return_value=json_data)

    fake_client = MagicMock()
    fake_client.get = AsyncMock(return_value=fake_response)

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=fake_client)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


class TestCrossrefNoiseFilter(unittest.TestCase):
    def test_crossref_filters_noise(self):
        """Crossref 结果中的审稿评论 / 勘误条目被过滤，正式论文保留。"""
        items = [
            {"title": ["Review for: lithium plating"], "author": [], "container-title": ["J."],
             "published": {"date-parts": [[2020]]}, "DOI": "10.1/rev"},
            {"title": ["Erratum: thermal runaway"], "author": [], "container-title": ["J."],
             "published": {"date-parts": [[2021]]}, "DOI": "10.1/err"},
            {"title": ["A review of solid-state electrolytes"], "author": [], "container-title": ["J."],
             "published": {"date-parts": [[2022]]}, "DOI": "10.1/review"},
            {"title": ["High-ionic-conductivity garnet electrolyte"], "author": [], "container-title": ["J."],
             "published": {"date-parts": [[2023]]}, "DOI": "10.1/garnet"},
        ]
        ctx = _mock_httpx({"message": {"items": items}})
        retriever = CrossrefRetriever()

        with patch(
            "battery_materials_agent.agent_team.agents.literature_researcher.httpx.AsyncClient",
            return_value=ctx,
        ):
            papers = asyncio.run(retriever.search("solid electrolyte", limit=10))

        titles = [p["title"] for p in papers]
        self.assertNotIn("Review for: lithium plating", titles)
        self.assertNotIn("Erratum: thermal runaway", titles)
        self.assertIn("A review of solid-state electrolytes", titles)  # 正式综述保留
        self.assertIn("High-ionic-conductivity garnet electrolyte", titles)


class TestSemanticScholarNoiseFilter(unittest.TestCase):
    def test_s2_filters_noise(self):
        """Semantic Scholar 结果中的非正式条目被过滤，正式论文保留。"""
        data = [
            {"title": "Comment on 'fast charging'", "authors": [], "year": 2020,
             "venue": "J.", "externalIds": {"DOI": "10.1/c"}, "abstract": ""},
            {"title": "Retraction notice", "authors": [], "year": 2021,
             "venue": "J.", "externalIds": {"DOI": "10.1/r"}, "abstract": ""},
            {"title": "A review of sulfide solid electrolytes", "authors": [], "year": 2022,
             "venue": "J.", "externalIds": {"DOI": "10.1/rev"}, "abstract": ""},
            {"title": "Silicon anode with high capacity", "authors": [], "year": 2023,
             "venue": "J.", "externalIds": {"DOI": "10.1/si"}, "abstract": ""},
        ]
        ctx = _mock_httpx({"data": data})
        retriever = SemanticScholarRetriever()

        with patch(
            "battery_materials_agent.agent_team.agents.literature_researcher.httpx.AsyncClient",
            return_value=ctx,
        ):
            papers = asyncio.run(retriever.search("solid electrolyte", limit=10))

        titles = [p["title"] for p in papers]
        self.assertNotIn("Comment on 'fast charging'", titles)
        self.assertNotIn("Retraction notice", titles)
        self.assertIn("A review of sulfide solid electrolytes", titles)
        self.assertIn("Silicon anode with high capacity", titles)


if __name__ == "__main__":
    unittest.main()