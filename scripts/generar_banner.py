"""Genera el banner animado del README (.github/assets/banner.svg) y la imagen del núcleo.

El núcleo se renderiza con el shader WebGL real (site/assets/orb.js) sobre el fondo del banner y se
funde por los bordes con una máscara radial, así se integra sin cortes en cualquier fondo oscuro.
El SVG lleva las fuentes y la imagen incrustadas (GitHub no carga recursos externos desde un SVG).

Uso:  .venv\\Scripts\\python scripts\\generar_banner.py
"""

from __future__ import annotations

import base64
import io
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parent))
from generar_animaciones import OUT, PAGE, PORT, SITE, serve  # noqa: E402

BG = "#0a0710"
ORB = 600  # px del render del núcleo


def render_orb() -> Image.Image:
    from playwright.sync_api import sync_playwright

    cap = SITE / "_captura.html"
    srv = serve()
    try:
        cap.write_text(PAGE % {"w": ORB, "h": ORB, "orb": ORB, "top": 0, "lb": 0, "bg": BG}, encoding="utf-8")
        with sync_playwright() as p:
            b = p.chromium.launch(channel="chrome", headless=True,
                                  args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
            pg = b.new_page(viewport={"width": ORB, "height": ORB}, device_scale_factor=1)
            pg.goto(f"http://127.0.0.1:{PORT}/_captura.html")
            pg.wait_for_function("window.ready === true")
            pg.evaluate("orb.setState('speaking'); setLabel('', '')")
            for i in range(80):
                pg.evaluate(f"orb.setLevel({0.22 + 0.1 * ((i % 7) / 7):.3f}); orb.step(1/30)")
            img = Image.open(io.BytesIO(pg.locator("#stage").screenshot())).convert("RGB")
            b.close()
    finally:
        cap.unlink(missing_ok=True)
        srv.shutdown()
    # Máscara radial suave: opaco en el centro, transparente en el borde
    m = Image.new("L", (ORB, ORB), 0)
    d = ImageDraw.Draw(m)
    steps = 60
    for i in range(steps):
        t = i / (steps - 1)
        r = ORB * (0.5 - 0.16 * t)
        d.ellipse([ORB / 2 - r, ORB / 2 - r, ORB / 2 + r, ORB / 2 + r], fill=int(255 * (t ** 1.6)))
    m = m.filter(ImageFilter.GaussianBlur(6))
    out = img.convert("RGBA")
    out.putalpha(ImageChops.multiply(m, Image.new("L", m.size, 255)))
    return out


def b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode()


def build_svg(orb_webp: bytes) -> str:
    sg = b64(SITE / "fonts" / "space-grotesk-latin-wght-normal.woff2")
    jb = b64(SITE / "fonts" / "jetbrains-mono-latin-400-normal.woff2")
    orb = base64.b64encode(orb_webp).decode()
    cx, cy = 968, 220
    chips = ["Claude Opus", "IA local con Ollama", "Voz 24/7", "Telegram"]
    x, chip_svg = 0, []
    for i, c in enumerate(chips):
        w = 24 + len(c) * 8.4
        chip_svg.append(
            f'<g class="up" style="animation-delay:{0.55 + i * 0.07:.2f}s">'
            f'<rect x="{x:.1f}" y="0" width="{w:.1f}" height="32" rx="16" fill="#c4b5fd" fill-opacity=".06" '
            f'stroke="#c4b5fd" stroke-opacity=".18"/>'
            f'<text x="{x + w / 2:.1f}" y="21" text-anchor="middle" class="m" font-size="13" fill="#d8cffa">{c}</text></g>')
        x += w + 10
    bars = "".join(
        f'<rect x="{i * 6}" y="-9" width="3" height="18" rx="1.5" fill="#a855f7" class="bar" '
        f'style="animation-delay:{(i * 0.13) % 0.9:.2f}s;animation-duration:{0.8 + (i % 3) * 0.17:.2f}s"/>'
        for i in range(9))
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 440" width="1280" height="440" role="img" aria-label="J.A.R.V.I.S. Asistente personal de IA para Windows">
<defs>
<style>
@font-face{{font-family:SG;src:url(data:font/woff2;base64,{sg}) format("woff2");font-weight:300 700}}
@font-face{{font-family:JBM;src:url(data:font/woff2;base64,{jb}) format("woff2")}}
.t{{font-family:SG,"Segoe UI",system-ui,sans-serif}}
.m{{font-family:JBM,Consolas,monospace}}
@keyframes spin{{to{{transform:rotate(360deg)}}}}
@keyframes spinr{{to{{transform:rotate(-360deg)}}}}
@keyframes breathe{{0%,100%{{transform:scale(1)}}50%{{transform:scale(1.035)}}}}
@keyframes drift{{0%,100%{{transform:translate(0,0);opacity:.75}}50%{{transform:translate(-40px,18px);opacity:1}}}}
@keyframes drift2{{0%,100%{{transform:translate(0,0);opacity:.6}}50%{{transform:translate(50px,-14px);opacity:.95}}}}
@keyframes up{{from{{opacity:0;transform:translateY(12px)}}to{{opacity:1;transform:none}}}}
@keyframes bar{{0%,100%{{transform:scaleY(.25)}}50%{{transform:scaleY(1)}}}}
@keyframes ping{{0%{{transform:scale(1);opacity:.7}}100%{{transform:scale(2.6);opacity:0}}}}
@keyframes sweep{{0%{{transform:translateX(-420px)}}100%{{transform:translateX(1400px)}}}}
.spin,.spinr,.breathe,.bar,.ping{{transform-box:fill-box;transform-origin:center}}
.spin{{animation:spin 48s linear infinite}}
.spinr{{animation:spinr 70s linear infinite}}
.fast{{animation-duration:22s}}
.breathe{{animation:breathe 6s ease-in-out infinite}}
.a1{{animation:drift 14s ease-in-out infinite}}
.a2{{animation:drift2 18s ease-in-out infinite}}
.up{{animation:up .9s cubic-bezier(.22,1,.36,1) both}}
.bar{{animation:bar 1s ease-in-out infinite}}
.ping{{animation:ping 2.4s cubic-bezier(0,0,.2,1) infinite}}
.sweep{{animation:sweep 9s cubic-bezier(.6,0,.4,1) infinite}}
@media (prefers-reduced-motion:reduce){{.sweep,.a1,.a2{{animation:none}}.up{{animation-name:fade}}}}
@keyframes fade{{from{{opacity:0}}to{{opacity:1}}}}
</style>
<clipPath id="card"><rect width="1280" height="440" rx="28"/></clipPath>
<radialGradient id="g1" cx="50%" cy="50%" r="50%"><stop offset="0" stop-color="#7c3aed" stop-opacity=".55"/><stop offset="1" stop-color="#7c3aed" stop-opacity="0"/></radialGradient>
<radialGradient id="g2" cx="50%" cy="50%" r="50%"><stop offset="0" stop-color="#c026d3" stop-opacity=".28"/><stop offset="1" stop-color="#c026d3" stop-opacity="0"/></radialGradient>
<radialGradient id="g3" cx="50%" cy="50%" r="50%"><stop offset="0" stop-color="#4f46e5" stop-opacity=".3"/><stop offset="1" stop-color="#4f46e5" stop-opacity="0"/></radialGradient>
<linearGradient id="title" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#ffffff"/><stop offset=".55" stop-color="#ede9fe"/><stop offset="1" stop-color="#c4b5fd"/></linearGradient>
<linearGradient id="edge" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#c4b5fd" stop-opacity=".35"/><stop offset=".5" stop-color="#c4b5fd" stop-opacity=".08"/><stop offset="1" stop-color="#c4b5fd" stop-opacity=".18"/></linearGradient>
<linearGradient id="beam" x1="0" x2="1"><stop offset="0" stop-color="#c4b5fd" stop-opacity="0"/><stop offset=".5" stop-color="#c4b5fd" stop-opacity=".07"/><stop offset="1" stop-color="#c4b5fd" stop-opacity="0"/></linearGradient>
<linearGradient id="ring" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#c4b5fd" stop-opacity=".55"/><stop offset=".5" stop-color="#a855f7" stop-opacity=".05"/><stop offset="1" stop-color="#c4b5fd" stop-opacity=".4"/></linearGradient>
<pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse"><path d="M40 0H0V40" fill="none" stroke="#c4b5fd" stroke-opacity=".07"/></pattern>
<radialGradient id="gridfade" cx="72%" cy="50%" r="62%"><stop offset="0" stop-color="#fff"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></radialGradient>
<mask id="gm"><rect width="1280" height="440" fill="url(#gridfade)"/></mask>
</defs>
<g clip-path="url(#card)">
<rect width="1280" height="440" fill="{BG}"/>
<ellipse class="a1" cx="980" cy="120" rx="520" ry="300" fill="url(#g1)"/>
<ellipse class="a2" cx="1180" cy="420" rx="420" ry="240" fill="url(#g2)"/>
<ellipse class="a2" cx="180" cy="-40" rx="520" ry="260" fill="url(#g3)"/>
<rect width="1280" height="440" fill="url(#grid)" mask="url(#gm)"/>
<rect class="sweep" x="0" y="0" width="420" height="440" fill="url(#beam)"/>
<g>
<circle class="spin" cx="{cx}" cy="{cy}" r="236" fill="none" stroke="url(#ring)" stroke-width="1.2" stroke-dasharray="2 9"/>
<circle class="spinr" cx="{cx}" cy="{cy}" r="268" fill="none" stroke="#c4b5fd" stroke-opacity=".12" stroke-width="1"/>
<circle class="spin fast" cx="{cx}" cy="{cy}" r="268" fill="none" stroke="#c4b5fd" stroke-opacity=".7" stroke-width="2" stroke-linecap="round" stroke-dasharray="60 1624"/>
<circle class="spinr" cx="{cx}" cy="{cy}" r="300" fill="none" stroke="#c4b5fd" stroke-opacity=".08" stroke-width="1" stroke-dasharray="1 5"/>
<g class="breathe"><image x="{cx - 260}" y="{cy - 260}" width="520" height="520" href="data:image/webp;base64,{orb}"/></g>
</g>
<g transform="translate(88 0)">
<g class="up" style="animation-delay:.05s"><text x="0" y="124" class="m" font-size="13" letter-spacing="3.2" fill="#a594d6">ASISTENTE PERSONAL DE IA PARA WINDOWS</text></g>
<g class="up" style="animation-delay:.15s"><text x="-4" y="214" class="t" font-size="96" font-weight="600" letter-spacing="-3" fill="url(#title)">J.A.R.V.I.S.</text></g>
<g class="up" style="animation-delay:.3s">
<text x="0" y="262" class="t" font-size="23" font-weight="400" fill="#cbc2e6">Habla con tu PC. Voz siempre activa, memoria</text>
<text x="0" y="294" class="t" font-size="23" font-weight="400" fill="#cbc2e6">y control total, con Claude o con IA local.</text>
</g>
<g transform="translate(0 330)">{"".join(chip_svg)}</g>
<g transform="translate(0 398)"><g class="up" style="animation-delay:.9s">
<circle class="ping" cx="5" cy="0" r="4.5" fill="#6ee7b7"/><circle cx="5" cy="0" r="4.5" fill="#6ee7b7"/>
<text x="20" y="5" class="m" font-size="13" fill="#8f84b0">en línea</text>
<g transform="translate(96 0)">{bars}</g>
</g></g>
</g>
</g>
<rect x=".75" y=".75" width="1278.5" height="438.5" rx="27.5" fill="none" stroke="url(#edge)" stroke-width="1.5"/>
</svg>'''


SOCIAL = """<!doctype html><html><head><meta charset="utf-8"><style>
@font-face{font-family:SG;src:url(fonts/space-grotesk-latin-wght-normal.woff2) format('woff2');font-weight:300 700}
@font-face{font-family:IN;src:url(fonts/inter-latin-wght-normal.woff2) format('woff2');font-weight:100 900}
@font-face{font-family:JB;src:url(fonts/jetbrains-mono-latin-400-normal.woff2) format('woff2')}
html,body{margin:0}
#s{position:relative;width:1280px;height:640px;overflow:hidden;background:%(bg)s;font-family:IN,sans-serif}
.a{position:absolute;border-radius:50%%;filter:blur(70px)}
.g{position:absolute;inset:0;background-image:linear-gradient(rgb(196 181 253/.06) 1px,transparent 1px),linear-gradient(90deg,rgb(196 181 253/.06) 1px,transparent 1px);
 background-size:44px 44px;-webkit-mask-image:radial-gradient(60%% 70%% at 74%% 50%%,#000,transparent)}
img{position:absolute;width:700px;height:700px;left:640px;top:-30px}
.ring{position:absolute;border-radius:50%%;border:1px solid rgb(196 181 253/.14)}
.t{position:absolute;left:84px;top:150px;width:640px}
.e{font:400 15px JB,monospace;letter-spacing:.26em;text-transform:uppercase;color:#a594d6}
h1{margin:22px 0 0;font:600 118px/1 SG,sans-serif;letter-spacing:-.045em;
 background:linear-gradient(110deg,#fff,#ede9fe 50%%,#c4b5fd);-webkit-background-clip:text;color:transparent}
p{margin:26px 0 0;font:400 27px/1.45 IN,sans-serif;color:#cbc2e6;letter-spacing:-.01em}
.c{display:flex;gap:10px;margin-top:34px}
.c span{font:400 15px JB,monospace;color:#d8cffa;padding:9px 16px;border-radius:99px;background:rgb(196 181 253/.06);border:1px solid rgb(196 181 253/.18)}
.u{position:absolute;left:84px;bottom:52px;font:400 16px JB,monospace;color:#8f84b0}
</style></head><body><div id="s">
<div class="a" style="width:760px;height:520px;left:600px;top:-160px;background:rgb(124 58 237/.5)"></div>
<div class="a" style="width:520px;height:360px;left:980px;top:420px;background:rgb(192 38 211/.22)"></div>
<div class="a" style="width:620px;height:320px;left:-160px;top:-120px;background:rgb(79 70 229/.26)"></div>
<div class="g"></div>
<div class="ring" style="width:600px;height:600px;left:690px;top:20px"></div>
<div class="ring" style="width:680px;height:680px;left:650px;top:-20px;border-style:dashed;opacity:.6"></div>
<img src="%(orb)s">
<div class="t"><div class="e">Asistente personal de IA para Windows</div><h1>J.A.R.V.I.S.</h1>
<p>Habla con tu PC. Voz siempre activa, memoria y control total, con Claude o con IA local.</p>
<div class="c"><span>Claude Opus</span><span>Ollama local</span><span>Voz 24/7</span><span>Telegram</span></div></div>
<div class="u">github.com/ItsTrako/jarvis</div>
</div></body></html>"""


def render_social(orb: Image.Image) -> None:
    from playwright.sync_api import sync_playwright

    buf = io.BytesIO()
    orb.save(buf, "PNG")
    page = SITE / "_social.html"
    page.write_text(SOCIAL % {"bg": BG, "orb": "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()},
                    encoding="utf-8")
    srv = serve()
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(channel="chrome", headless=True)
            pg = b.new_page(viewport={"width": 1280, "height": 640}, device_scale_factor=1)
            pg.goto(f"http://127.0.0.1:{PORT}/_social.html")
            pg.evaluate("document.fonts.ready")
            pg.wait_for_timeout(400)
            png = pg.locator("#s").screenshot()
            b.close()
    finally:
        page.unlink(missing_ok=True)
        srv.shutdown()
    Image.open(io.BytesIO(png)).convert("RGB").save(OUT / "social.png", optimize=True)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    orb = render_orb()
    orb.save(OUT / "nucleo.png", optimize=True)
    # Favicon de la web: el centro del núcleo
    w = orb.size[0]
    orb.crop((int(w * .22), int(w * .22), int(w * .78), int(w * .78))).resize((128, 128), Image.LANCZOS).save(OUT / "icono.png")
    small = orb.resize((520, 520), Image.LANCZOS)
    buf = io.BytesIO()
    small.save(buf, "WEBP", quality=86, method=6)
    svg = build_svg(buf.getvalue())
    assert "—" not in svg and "–" not in svg
    (OUT / "banner.svg").write_text(svg, encoding="utf-8")
    render_social(orb)
    print(f"  OK nucleo.png, icono.png, banner.svg ({len(svg.encode()) / 1024:.0f} KB), social.png")


if __name__ == "__main__":
    main()
