"""AI 助手（Copilot）纯函数单元测试。

覆盖两个修复回归点：
1. _build_conv_messages — 当前用户消息不得在 prompt 中重复出现
2. _resolve_attempts — 通用分支回退链必须 ("llm", None) 在前，且聚焦 agent 双模型正确
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from battery_materials_agent import api


def _mk_msg(message_id: str, role: str, content: str) -> dict:
    return {
        "message_id": message_id,
        "role": role,
        "content": content,
        "provider": "",
        "model": "",
        "status": "done",
        "meta": {},
        "created_at": "",
    }


def _mk_session(**overrides) -> dict:
    base = {
        "session_id": "s1",
        "user_id": "u1",
        "project_id": "",
        "title": "新会话",
        "mode": "global",
        "focus": {},
        "status": "active",
        "context": {},
        "metadata": {},
        "created_at": "",
        "updated_at": "",
    }
    base.update(overrides)
    return base


class TestBuildConvMessages(unittest.TestCase):
    """验证对话消息构造不会重复当前用户消息。"""

    def test_current_message_not_duplicated(self):
        session = _mk_session()
        history = [
            _mk_msg("m1", "user", "前一问题"),
            _mk_msg("m2", "assistant", "前一回答"),
            _mk_msg("m3", "user", "当前问题"),  # 已写入存储的当前消息
        ]
        messages = api._build_conv_messages(session, history, "m3", "当前问题")
        user_msgs = [m for m in messages if m["role"] == "user"]
        # 历史去掉 m3 后剩 m1，再追加一次当前问题 → 共 2 条 user
        self.assertEqual(len(user_msgs), 2)
        # "当前问题"只出现一次（回归点）
        cur = [m for m in user_msgs if m["content"] == "当前问题"]
        self.assertEqual(len(cur), 1)

    def test_empty_content_skipped(self):
        session = _mk_session()
        history = [
            _mk_msg("m1", "user", "a"),
            _mk_msg("m2", "assistant", ""),  # streaming 空内容应跳过
            _mk_msg("m3", "user", "当前问题"),
        ]
        messages = api._build_conv_messages(session, history, "m3", "当前问题")
        contents = [m["content"] for m in messages]
        self.assertNotIn("", contents)
        self.assertIn("a", contents)

    def test_history_limited_to_20(self):
        session = _mk_session()
        history = [_mk_msg(f"m{i}", "user", f"问题{i}") for i in range(1, 29)]  # m1..m28
        current_id = "m29"  # 不在 history 中
        messages = api._build_conv_messages(session, history, current_id, "当前问题")
        # history[-20:] 只保留最近 20 条历史 + 1 条当前 = 21 条 user 消息
        user_msgs = [m for m in messages if m["role"] == "user"]
        self.assertEqual(len(user_msgs), 21)


class TestResolveAttempts(unittest.TestCase):
    """验证调用链尝试序列。"""

    def test_generic_fallback_chain_uses_llm_first(self):
        attempts = api._resolve_attempts(_mk_session())
        # 回归点：必须 ("llm", None) 在前，否则空 provider 会被解析为 internlm
        self.assertEqual(attempts[0][0], "llm")
        self.assertEqual(attempts[1][0], "internlm")

    @patch("battery_materials_agent.api._registry")
    def test_focused_agent_dual_model(self, mock_registry):
        agent = MagicMock()
        agent.provider = "llm"
        agent.llm_model = "gpt-x"
        agent.provider_secondary = "internlm"
        agent.llm_model_secondary = "s2"
        agent.name = "研究员"
        mock_registry.get_agent.return_value = agent
        attempts = api._resolve_attempts(_mk_session(focus={"agent_id": "a1"}))
        self.assertEqual(len(attempts), 2)
        self.assertEqual(attempts[0], ("llm", "gpt-x", "研究员"))
        self.assertEqual(attempts[1], ("internlm", "s2", "研究员"))


if __name__ == "__main__":
    unittest.main()