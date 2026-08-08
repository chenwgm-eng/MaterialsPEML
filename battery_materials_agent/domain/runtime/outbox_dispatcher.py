"""Outbox 派发器 — 消费 ScientificOutbox 中待发送的事件消息。

原理：`ScientificOutbox` 仅负责"可靠入队"（enqueue），若没有消费者持续
`claim_pending` → 派发 → `mark_sent/failed`，消息会永久滞留在 pending 状态。
本派发器补齐这一消费链路：

- `claim_pending` 原子领取一批消息（同一事务将状态置为 sending，避免并发重复领取）；
- 按 ``event_type`` 派发到已注册处理器；未注册类型的消息走默认日志处理器，保证队列被耗尽；
- 处理成功 `mark_sent`，失败 `mark_failed`（内部按 max_retries 递增重试计数并终态化）。

调用方可在应用启动时 `register` 具体事件的业务处理器，并以后台任务运行 `run_forever`。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable

from .outbox import ScientificOutbox

logger = logging.getLogger(__name__)

# 事件处理器签名：(event_type, subject_id, payload) -> None 或协程
EventHandler = Callable[[str, str, dict[str, Any]], "None | Awaitable[None]"]


class OutboxDispatcher:
    """按事件类型派发 outbox 消息的消费者。"""

    def __init__(self, outbox: ScientificOutbox | None = None, poll_interval: float = 2.0):
        self.outbox = outbox or ScientificOutbox()
        self.poll_interval = poll_interval
        self._handlers: dict[str, EventHandler] = {}

    def register(self, event_type: str, handler: EventHandler) -> None:
        """注册某类事件的处理器（同步或异步均可）。"""
        self._handlers[event_type] = handler

    async def process_once(self, limit: int = 10) -> int:
        """领取并处理一批消息，返回成功派发条数。"""
        processed = 0
        for msg in self.outbox.claim_pending(limit=limit):
            handler = self._handlers.get(msg.event_type, self._default_handler)
            try:
                result = handler(msg.event_type, msg.subject_id, msg.payload)
                if asyncio.iscoroutine(result):
                    await result
                self.outbox.mark_sent(msg.message_id)
                processed += 1
                logger.info(
                    "Outbox 消息已派发 event=%s subject=%s",
                    msg.event_type, msg.subject_id,
                )
            except Exception as e:  # noqa: BLE001 - 单条失败不阻断批次
                logger.warning(
                    "Outbox 消息派发失败 event=%s subject=%s err=%s (retry=%d/%d)",
                    msg.event_type, msg.subject_id, e, msg.retry_count, msg.max_retries,
                )
                self.outbox.mark_failed(msg.message_id, str(e))
        return processed

    async def run_forever(self) -> None:
        """周期性消费循环（作为后台任务运行，直至被取消）。"""
        logger.info("OutboxDispatcher 已启动 poll_interval=%ss", self.poll_interval)
        while True:
            try:
                await self.process_once()
            except Exception as e:  # noqa: BLE001 - 消费批次异常不中断循环
                logger.warning("Outbox 消费批次异常: %s", e)
            await asyncio.sleep(self.poll_interval)

    @staticmethod
    def _default_handler(event_type: str, subject_id: str, payload: dict[str, Any]) -> None:
        """默认处理器：仅记录日志，确保消息被耗尽、不永久滞留。"""
        logger.info(
            "Outbox 默认处理器 event=%s subject=%s payload=%s",
            event_type, subject_id, payload,
        )