"""Google Scholar 检索源单元测试。

scholarly 为 P2 补充依赖（默认关闭、异常隔离），测试通过在 sys.modules
注入假 scholarly 模块来验证检索逻辑，不依赖真实安装。

覆盖场景：
- 默认关闭时返回空结果
- 检索源列表注册 GoogleScholarRetriever 但默认关闭
- 显式开启后返回结构化文献，source=google_scholar
- 非 ASCII（中文）查询被跳过
- 检索异常静默降级为空结果
"""

from __future__ import annotations

import asyncio
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

from battery_materials_agent.agent_team.agents.literature_researcher import (
    GoogleScholarRetriever,
    LiteratureResearcherAgent,
)


def _fake_scholarly_module() -> types.ModuleType:
    """构造一个可注入 sys.modules 的假 scholarly 模块。"""
    mod = types.ModuleType("scholarly")
    mod.search_pubs = MagicMock()
    # `from scholarly import scholarly` 取子模块 scholarly，指向自身即可
    mod.scholarly = mod
    return mod


class TestGoogleScholarDefaultOff(unittest.TestCase):
    def test_retriever_disabled_by_default(self):
        """未显式开启 GOOGLE_SCHOLAR_ENABLED 时返回空结果。"""
        with patch.dict("os.environ", {}, clear=False):
            retriever = GoogleScholarRetriever()
        self.assertFalse(retriever._enabled)
        self.assertEqual(asyncio.run(retriever.search("solid electrolyte", limit=5)), [])

    def test_agent_registers_retriever_but_disabled(self):
        """Agent 注册了 GoogleScholarRetriever，但默认关闭时 search 返回空。"""
        with patch.dict("os.environ", {}, clear=False):
            agent = LiteratureResearcherAgent(enable_llm=False, enable_scp=False)
        retriever = next(
            (r for r in agent._retrievers if isinstance(r, GoogleScholarRetriever)),
            None,
        )
        self.assertIsNotNone(retriever, "GoogleScholarRetriever 应被注册到检索源")
        self.assertFalse(retriever._enabled)


class TestGoogleScholarEnabled(unittest.TestCase):
    def test_enabled_returns_papers(self):
        """显式开启后，scholarly search_pubs 返回结构化文献。"""
        fake_pubs = [
            {
                "bib": {
                    "title": "Solid-state lithium battery electrolytes",
                    "author": ["Alice", "Bob"],
                    "venue": "Nature Energy",
                    "pub_year": 2021,
                    "abstract": "A review of solid-state electrolytes.",
                },
                "pub_url": "https://scholar.google.com/citations?view_op=view_citation",
            },
        ]

        class _FakeSearchPubs:
            def __init__(self, _q):
                self._items = iter(fake_pubs)

            def __iter__(self):
                return self

            def __next__(self):
                return next(self._items)

        fake = _fake_scholarly_module()
        fake.search_pubs = _FakeSearchPubs

        retriever = GoogleScholarRetriever(enabled=True)
        with patch.dict(sys.modules, {"scholarly": fake}):
            papers = asyncio.run(retriever.search("solid electrolyte", limit=5))

        self.assertEqual(len(papers), 1)
        self.assertEqual(papers[0]["source"], "google_scholar")
        self.assertEqual(papers[0]["title"], "Solid-state lithium battery electrolytes")
        self.assertEqual(papers[0]["authors"], ["Alice", "Bob"])
        self.assertEqual(papers[0]["year"], 2021)

    def test_non_ascii_query_skipped(self):
        """中文查询被跳过，不触发 scholarly 调用。"""
        fake = _fake_scholarly_module()
        retriever = GoogleScholarRetriever(enabled=True)
        with patch.dict(sys.modules, {"scholarly": fake}):
            papers = asyncio.run(retriever.search("固态电解质", limit=5))
        self.assertEqual(papers, [])
        fake.search_pubs.assert_not_called()

    def test_exception_degrades_to_empty(self):
        """scholarly 抛异常时静默降级为空结果。"""
        fake = _fake_scholarly_module()
        fake.search_pubs.side_effect = RuntimeError("network error")
        retriever = GoogleScholarRetriever(enabled=True)
        with patch.dict(sys.modules, {"scholarly": fake}):
            papers = asyncio.run(retriever.search("solid electrolyte", limit=5))
        self.assertEqual(papers, [])


if __name__ == "__main__":
    unittest.main()