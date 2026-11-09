"""Genera los recursos animados de la documentación a partir del núcleo WebGL real (site/assets/orb.js).

    nucleo-estados.webp WebP animado con los cuatro estados (en espera, escuchando, pensando, hablando)

Uso:  ..\\.venv\\Scripts\\python ..\\scripts\\generar_animaciones.py   (desde backend/)
"""

from __future__ import annotations

import functools
import http.server
import io
import math
import threading
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
OUT = ROOT / ".github" / "assets"
PORT = 8790

PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
@font-face{font-family:SG;src:url(fonts/space-grotesk-latin-wght-normal.woff2) format('woff2');font-weight:300 700}
html,body{margin:0;background:transparent}
#stage{width:%(w)dpx;height:%(h)dpx;position:relative;overflow:hidden;
 background:%(bg)s}
canvas{position:absolute;left:50%%;top:%(top)dpx;transform:translateX(-50%%);width:%(orb)dpx;height:%(orb)dpx}
#label{position:absolute;left:0;right:0;bottom:%(lb)dpx;text-align:center;font:500 15px SG,sans-serif;
 letter-spacing:.32em;text-transform:uppercase;color:#c4b5fd}
#label b{display:inline-block;width:7px;height:7px;border-radius:9px;background:#6ee7b7;margin-right:12px;vertical-align:2px}
</style></head><body><div id="stage"><canvas id="c"></canvas><div id="label"></div></div>
<script type="module">
import { createOrb } from "./assets/orb.js";
const orb = createOrb(document.getElementById("c"), { manual: true, reducedMotion: false });
window.orb = orb;
window.setLabel = (t, dot) => { document.getElementById("label").innerHTML = t ? `<b style="background:${dot}"></b>${t}` : ""; };
window.ready = true;
</script></body></html>"""

STATES = [("idle", "En espera", "#6ee7b7"), ("listening", "Escuchando", "#a855f7"),
          ("thinking", "Pensando", "#c4b5fd"), ("speaking", "Hablando", "#a855f7")]


def serve():
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(SITE))
    handler.log_message = lambda *a: None
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def level_for(state: str, t: float) -> float:
    if state == "speaking":  # sílabas: envolvente rápida modulada
        return max(0.0, 0.35 + 0.35 * math.sin(t * 13) * math.sin(t * 3.1) + 0.2 * math.sin(t * 29))
    if state == "listening":
        return max(0.0, 0.18 + 0.16 * math.sin(t * 9) * math.sin(t * 2.3))
    return 0.0


def main() -> None:
    from playwright.sync_api import sync_playwright

    OUT.mkdir(parents=True, exist_ok=True)
    srv = serve()
    cap = SITE / "_captura.html"
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(channel="chrome", headless=True, args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"])

            # WebP animado de estados
            W, H = 560, 430
            cap.write_text(PAGE % {"w": W, "h": H, "orb": W, "top": -86, "lb": 34,
                                   "bg": "radial-gradient(60% 60% at 50% 42%, #1a1030 0%, #0b0812 70%, #08060d 100%)"},
                           encoding="utf-8")
            pg = b.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)
            pg.goto(f"http://127.0.0.1:{PORT}/_captura.html")
            pg.wait_for_function("window.ready === true")
            fps, per_state = 15, 2.4
            frames, t = [], 0.0
            for state, label, dot in STATES:
                pg.evaluate(f"orb.setState('{state}'); setLabel('{label}', '{dot}')")
                for i in range(int(per_state * fps)):
                    t += 1 / fps
                    pg.evaluate(f"orb.setLevel({level_for(state, t):.3f}); orb.step({1 / fps})")
                    png = pg.locator("#stage").screenshot()
                    frames.append(Image.open(io.BytesIO(png)).convert("RGB"))
            # WebP animado: mucha más calidad y menos peso que GIF con el plasma en movimiento
            dst = OUT / "nucleo-estados.webp"
            frames[0].save(dst, save_all=True, append_images=frames[1:], duration=int(1000 / fps), loop=0,
                           quality=78, method=6)
            (OUT / "nucleo-estados.gif").unlink(missing_ok=True)
            print(f"  OK {dst.name} ({len(frames)} fotogramas, {dst.stat().st_size / 1e6:.1f} MB)")

            b.close()
    finally:
        cap.unlink(missing_ok=True)
        srv.shutdown()


if __name__ == "__main__":
    main()
