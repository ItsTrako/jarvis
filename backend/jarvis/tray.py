"""Icono de JARVIS en la bandeja del sistema: abrir, parada de emergencia y salir."""

from __future__ import annotations

import asyncio
import json
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from .config import DATA_DIR, PROJECT_ROOT, get_config


def _icon_image() -> Image.Image:
    png = PROJECT_ROOT / "frontend" / "public" / "jarvis-icon.png"
    if png.exists():
        return Image.open(png).convert("RGBA").resize((64, 64))
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((6, 6, 58, 58), outline=(168, 85, 247, 255), width=4)
    d.ellipse((22, 22, 42, 42), fill=(196, 181, 253, 255))
    return img.filter(ImageFilter.SMOOTH)


def _api(path: str, body: dict) -> None:
    token = (DATA_DIR / ".session_token").read_text(encoding="utf-8").strip()
    port = get_config().server.port
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "X-Jarvis-Token": token})
    urllib.request.urlopen(req, timeout=10).read()


def run_tray(server, open_ui, server_thread=None) -> None:
    import threading

    import pystray

    def emergency(icon, item):
        _api("/api/emergency", {"engaged": True})
        icon.notify("Parada de emergencia activada. JARVIS no ejecutará acciones.", "J.A.R.V.I.S.")

    def resume(icon, item):
        _api("/api/emergency", {"engaged": False})

    def quit_(icon, item):
        icon.stop()

    icon = pystray.Icon("jarvis", _icon_image(), "J.A.R.V.I.S.", menu=pystray.Menu(
        pystray.MenuItem("Abrir J.A.R.V.I.S.", lambda i, it: open_ui(), default=True),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("🛑 Parada de emergencia", emergency),
        pystray.MenuItem("Reanudar", resume),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Salir", quit_),
    ))

    def watch_server():
        # Si el servicio se detiene por otra vía (Detener-Jarvis, /api/shutdown), se cierra el icono.
        if server_thread is not None:
            server_thread.join()
            icon.stop()

    threading.Thread(target=watch_server, daemon=True).start()
    icon.run()
