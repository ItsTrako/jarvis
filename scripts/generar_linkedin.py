"""Imagen para publicar en LinkedIn (formato vertical 4:5, 1080x1350 a doble resolución).

Compone el núcleo WebGL real, la captura de la conversación y la del móvil sobre el fondo de la marca.
Uso:  .venv\\Scripts\\python scripts\\generar_linkedin.py   ->  publicacion/linkedin.png
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from generar_animaciones import PORT, SITE, serve  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "publicacion"

PAGE = r"""<!doctype html><html><head><meta charset="utf-8"><style>
@font-face{font-family:SG;src:url(fonts/space-grotesk-latin-wght-normal.woff2) format('woff2');font-weight:300 700}
@font-face{font-family:IN;src:url(fonts/inter-latin-wght-normal.woff2) format('woff2');font-weight:100 900}
@font-face{font-family:JB;src:url(fonts/jetbrains-mono-latin-400-normal.woff2) format('woff2')}
html,body{margin:0;background:#000}
#s{position:relative;width:1080px;height:1350px;overflow:hidden;background:#08060d;font-family:IN,sans-serif;color:#d9d3ef}
.blob{position:absolute;border-radius:50%;filter:blur(90px)}
.grid{position:absolute;inset:0;background-image:linear-gradient(rgb(196 181 253/.055) 1px,transparent 1px),linear-gradient(90deg,rgb(196 181 253/.055) 1px,transparent 1px);
 background-size:54px 54px;-webkit-mask-image:radial-gradient(70% 55% at 70% 30%,#000,transparent)}
.noise{position:absolute;inset:0;opacity:.06;mix-blend-mode:overlay;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='200' height='200'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E")}
#orb{position:absolute;width:820px;height:820px;left:530px;top:-175px;
 -webkit-mask-image:radial-gradient(closest-side,#000 86%,transparent 100%)}
.copy{position:absolute;left:76px;top:120px;width:640px}
.eye{font:400 15px JB,monospace;letter-spacing:.24em;text-transform:uppercase;color:#a594d6;display:flex;align-items:center;gap:12px}
.eye i{width:8px;height:8px;border-radius:50%;background:#6ee7b7;box-shadow:0 0 12px #6ee7b7}
h1{margin:26px 0 0;font:600 80px/1.02 SG,sans-serif;letter-spacing:-.045em;color:#fff}
h1 span{display:block;white-space:nowrap}
.g{background:linear-gradient(100deg,#fff 0%,#e9e3ff 28%,#c4b5fd 60%,#a855f7 100%);-webkit-background-clip:text;color:transparent;padding-bottom:6px}
.sub{margin:26px 0 0;font:400 24px/1.5 IN,sans-serif;color:#b9b0d6;width:600px}
.stage{position:absolute;left:0;top:536px;width:1080px;height:700px;perspective:2200px}
.win{position:absolute;left:64px;top:70px;width:900px;border-radius:20px;overflow:hidden;background:#0e0a16;
 border:1px solid rgb(196 181 253/.22);transform:rotateX(9deg) rotateY(-7deg) rotateZ(.6deg);transform-origin:50% 0;
 box-shadow:0 0 0 1px rgb(0 0 0/.5),0 50px 140px -30px rgb(124 58 237/.75),0 40px 80px -30px rgb(0 0 0/.9)}
.bar{height:34px;display:flex;align-items:center;gap:7px;padding:0 16px;border-bottom:1px solid rgb(196 181 253/.1);background:rgb(196 181 253/.035)}
.bar span{width:10px;height:10px;border-radius:50%;background:rgb(196 181 253/.18)}
.bar em{margin:0 auto;transform:translateX(-24px);font:400 12px JB,monospace;font-style:normal;color:#6f6889}
.win img{display:block;width:100%}
.win::after{content:"";position:absolute;inset:0;background:linear-gradient(160deg,rgb(255 255 255/.06),transparent 40%)}
.phone{position:absolute;left:800px;top:190px;width:216px;border-radius:30px;overflow:hidden;
 border:1px solid rgb(196 181 253/.3);transform:rotate(3deg);
 box-shadow:0 0 0 7px #120d1c,0 0 0 8px rgb(196 181 253/.18),0 40px 90px -20px rgb(0 0 0/.9),0 0 90px -10px rgb(168 85 247/.55)}
.phone img{display:block;width:100%}
.bubble{position:absolute;display:flex;align-items:center;gap:12px;padding:14px 22px;border-radius:99px;
 font:500 19px IN,sans-serif;color:#f5f3ff;background:rgb(20 14 32/.82);border:1px solid rgb(196 181 253/.28);
 backdrop-filter:blur(14px);box-shadow:0 20px 50px -15px rgb(0 0 0/.8),0 0 40px -10px rgb(168 85 247/.5)}
.bubble b{font:500 12px JB,monospace;letter-spacing:.18em;color:#c4b5fd;text-transform:uppercase}
.bubble i{width:9px;height:9px;border-radius:50%;flex:none}
.q{left:96px;top:14px}
.a{left:330px;top:560px}
.foot{position:absolute;left:76px;right:76px;bottom:58px;display:flex;align-items:center;justify-content:space-between}
.stats{display:flex;gap:12px}
.stats span{font:400 16px JB,monospace;color:#e2dcf7;padding:10px 18px;border-radius:99px;background:rgb(196 181 253/.07);border:1px solid rgb(196 181 253/.2)}
.url{font:400 17px JB,monospace;color:#a39cbd}
</style></head><body><div id="s">
<div class="blob" style="width:900px;height:700px;left:380px;top:-260px;background:rgb(124 58 237/.55)"></div>
<div class="blob" style="width:700px;height:520px;left:-260px;top:520px;background:rgb(79 70 229/.3)"></div>
<div class="blob" style="width:700px;height:500px;left:560px;top:1000px;background:rgb(192 38 211/.24)"></div>
<div class="grid"></div>
<canvas id="orb"></canvas>
<div class="copy">
  <div class="eye"><i></i>Código abierto · Windows</div>
  <h1><span>Habla con tu PC.</span><span class="g">Él hace el resto.</span></h1>
  <p class="sub">Asistente de IA con voz siempre activa, memoria y control total del PC. En local o con Claude.</p>
</div>
<div class="stage">
  <div class="win"><div class="bar"><span></span><span></span><span></span><em>J.A.R.V.I.S.</em></div><img src="img/conversacion.webp"></div>
  <div class="phone"><img src="img/movil.webp"></div>
  <div class="bubble q"><i style="background:#a855f7;box-shadow:0 0 12px #a855f7"></i>«Hey JARVIS, compara tres alternativas a Notion y hazme un informe»</div>
  <div class="bubble a"><i style="background:#6ee7b7;box-shadow:0 0 12px #6ee7b7"></i>Informe creado y verificado</div>
</div>
<div class="foot">
  <div class="stats"><span>+50 herramientas</span><span>Voz 24/7</span><span>IA local</span></div>
  <div class="url">github.com/ItsTrako/jarvis</div>
</div>
<div class="noise"></div>
</div>
<script type="module">
import { createOrb } from "./assets/orb.js";
const orb = createOrb(document.getElementById("orb"), { manual: true, reducedMotion: false });
orb.setState("speaking");
for (let i = 0; i < 90; i++) { orb.setLevel(0.3 + 0.12 * Math.sin(i * 0.7)); orb.step(1 / 30); }
await document.fonts.ready;
await Promise.all([...document.images].map((im) => im.decode().catch(() => {})));
window.ready = true;
</script></body></html>"""


def main() -> None:
    from playwright.sync_api import sync_playwright

    OUT.mkdir(exist_ok=True)
    img = SITE / "img"
    img.mkdir(exist_ok=True)
    for n in ("conversacion.webp", "movil.webp"):
        shutil.copy(ROOT / ".github" / "assets" / n, img / n)
    page = SITE / "_linkedin.html"
    page.write_text(PAGE, encoding="utf-8")
    srv = serve()
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(channel="chrome", headless=True,
                                  args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
            pg = b.new_page(viewport={"width": 1080, "height": 1350}, device_scale_factor=2)
            pg.goto(f"http://127.0.0.1:{PORT}/_linkedin.html")
            pg.wait_for_function("window.ready === true", timeout=60000)
            pg.wait_for_timeout(300)
            pg.locator("#s").screenshot(path=str(OUT / "linkedin.png"))
            b.close()
    finally:
        page.unlink(missing_ok=True)
        srv.shutdown()
    print("  OK", OUT / "linkedin.png")


if __name__ == "__main__":
    main()
