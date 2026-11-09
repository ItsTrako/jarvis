"""Bus de eventos en memoria (pub/sub asíncrono).

Todas las interfaces (UI web, Telegram, bandeja) se suscriben aquí: así comparten el
mismo estado en tiempo real (progreso de tareas, confirmaciones, estado del sistema).
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

log = logging.getLogger("jarvis.events")


class EventBus:
    def __init__(self) -> None:
        self._subs: set[asyncio.Queue] = set()

    def subscribe(self, maxsize: int = 1000) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
        self._subs.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subs.discard(q)

    def publish(self, type_: str, **payload: Any) -> None:
        event = {"type": type_, "ts": time.time(), **payload}
        for q in list(self._subs):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                # Cliente lento: se descarta el evento más antiguo para no bloquear
                try:
                    q.get_nowait()
                    q.put_nowait(event)
                except Exception:  # pragma: no cover
                    pass


bus = EventBus()
