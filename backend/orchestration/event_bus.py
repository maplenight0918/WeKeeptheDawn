"""Independent async subscriber queues; disconnect explicitly unsubscribes."""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from copy import deepcopy
from typing import Any

from pydantic import BaseModel


class EventBus:
    def __init__(self, record: Callable[[str, Any], None] | None = None):
        self._subscribers: set[asyncio.Queue] = set()
        self._record = record

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers.discard(queue)

    async def publish(self, message_type: str, payload: Any) -> None:
        if isinstance(payload, BaseModel):
            payload = payload.model_dump(mode="json")
        if self._record is not None:
            self._record(message_type, deepcopy(payload))
        envelope = {"type": message_type, "payload": payload}
        # Nonblocking enqueue preserves ordering without one client holding up
        # others. Each connection owns only its own message copy.
        for queue in tuple(self._subscribers):
            queue.put_nowait(deepcopy(envelope))
