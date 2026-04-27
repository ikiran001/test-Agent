from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from graphic_studio.agents.messages import AgentEnvelope

Subscriber = Callable[[AgentEnvelope], None]


class InMemoryBus:
    """Tiny pub/sub for local dev and tests."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subs: list[Subscriber] = []

    def subscribe(self, fn: Subscriber) -> None:
        with self._lock:
            self._subs.append(fn)

    def publish(self, envelope: AgentEnvelope) -> None:
        with self._lock:
            subs = list(self._subs)
        for fn in subs:
            fn(envelope)

    def clear(self) -> None:
        with self._lock:
            self._subs.clear()


# Module-level default bus (tests may replace).
default_bus = InMemoryBus()
