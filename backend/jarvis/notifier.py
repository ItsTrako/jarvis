"""Notificaciones: escritorio de Windows (toast) y Telegram."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Awaitable, Callable

from .config import PROJECT_ROOT
from .events import bus

log = logging.getLogger("jarvis.notify")

# Lo registra el bot de Telegram al arrancar: (texto, archivos, chat_id|None) -> None
TelegramSender = Callable[[str, list[str], int | None], Awaitable[None]]
_telegram_sender: TelegramSender | None = None


def register_telegram_sender(fn: TelegramSender | None) -> None:
    global _telegram_sender
    _telegram_sender = fn


def telegram_available() -> bool:
    return _telegram_sender is not None


def _toast(title: str, message: str) -> None:
    try:
        from winotify import Notification, audio

        icon = PROJECT_ROOT / "frontend" / "public" / "jarvis-icon.png"
        n = Notification(app_id="J.A.R.V.I.S.", title=title[:60], msg=message[:250],
                         icon=str(icon) if icon.exists() else "")
        n.set_audio(audio.Default, loop=False)
        n.show()
    except Exception as e:
        log.debug("Toast no disponible: %s", e)


async def notify(title: str, message: str, files: list[str] | None = None, channels: str = "all",
                 chat_id: int | None = None) -> dict[str, bool]:
    """channels: 'all' | 'desktop' | 'telegram' | 'none'."""
    sent = {"desktop": False, "telegram": False}
    bus.publish("notification", title=title, message=message[:1000], files=files or [])
    if channels in ("all", "desktop"):
        await asyncio.to_thread(_toast, title, message)
        sent["desktop"] = True
    if channels in ("all", "telegram") and _telegram_sender is not None:
        try:
            await _telegram_sender(f"*{title}*\n\n{message}", [f for f in (files or []) if Path(f).exists()], chat_id)
            sent["telegram"] = True
        except Exception as e:
            log.warning("No se pudo notificar por Telegram: %s", e)
    return sent
