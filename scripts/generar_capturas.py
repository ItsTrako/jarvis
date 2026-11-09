"""Genera las capturas de la documentación con una instancia de DEMOSTRACIÓN aislada.

Crea una carpeta de datos temporal con datos ficticios (nunca los tuyos), arranca JARVIS en el
puerto 8766 sin voz, Telegram ni esfera de escritorio, y captura las pantallas con Chrome.

Uso:  cd backend && ..\\.venv\\Scripts\\python ..\\scripts\\generar_capturas.py
Salida: .github/assets/*.webp
"""

from __future__ import annotations

import asyncio
import os
import platform
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / ".github" / "assets"
DEMO = Path(tempfile.mkdtemp(prefix="jarvis-demo-"))
PORT = 8766


def seed() -> None:
    os.environ["JARVIS_DATA_DIR"] = str(DEMO)
    sys.path.insert(0, str(ROOT / "backend"))
    from jarvis import db, store
    from jarvis.config import load_config, update_config

    load_config()
    update_config({
        "server": {"port": PORT, "open_browser_on_start": False},
        "user": {"name": "Tony"},
        "llm": {"provider": "ollama", "local_model": "gemma4:12b", "local_light_model": "qwen3:8b"},
        "voice": {"wake_word_enabled": False, "stt_device": "cpu"},
        "telegram": {"enabled": False},
        "desktop": {"overlay": False},
    })

    async def go():
        await db.init_db()
        c = await db.create_conversation("Comparativa de alternativas a Notion")
        cid, seg = c["id"], 0
        ctx = "<contexto>\nFecha y hora local: lunes 09/11/2026 10:12\nInterfaz: pc\n</contexto>"
        await db.add_message(cid, seg, "user", [{"type": "text", "text": ctx}, {"type": "text", "text":
            "Investiga tres alternativas a Notion para un equipo pequeño, compáralas y prepárame un informe en Word."}])
        plan = [{"title": "Buscar alternativas actuales", "status": "done"},
                {"title": "Comparar precio, colaboración y privacidad", "status": "done"},
                {"title": "Redactar el informe", "status": "done"},
                {"title": "Verificar el documento", "status": "done"}]
        await db.add_message(cid, seg, "assistant", [
            {"type": "text", "text": "Perfecto. Preparo un plan y me pongo con ello."},
            {"type": "tool_use", "id": "t1", "name": "update_plan", "input": {"goal": "Informe comparativo", "steps": plan}},
            {"type": "tool_use", "id": "t2", "name": "web_search", "input": {"query": "alternativas a Notion 2026 equipos pequeños"}},
        ])
        await db.add_message(cid, seg, "user", [
            {"type": "tool_result", "tool_use_id": "t1", "content": "Plan actualizado (4/4 completados)."},
            {"type": "tool_result", "tool_use_id": "t2", "content": "8 resultados: Obsidian, AFFiNE, Anytype, Coda, ClickUp…"},
        ])
        await db.add_message(cid, seg, "assistant", [
            {"type": "tool_use", "id": "t3", "name": "web_fetch", "input": {"url": "https://affine.pro/pricing"}},
            {"type": "tool_use", "id": "t4", "name": "create_document",
             "input": {"path": "informes/alternativas-notion.docx", "title": "Alternativas a Notion"}},
            {"type": "tool_use", "id": "t5", "name": "file_info", "input": {"path": "informes/alternativas-notion.docx"}},
        ])
        await db.add_message(cid, seg, "user", [
            {"type": "tool_result", "tool_use_id": "t3", "content": "Leído: affine.pro/pricing"},
            {"type": "tool_result", "tool_use_id": "t4", "content": "Documento creado y verificado: informes/alternativas-notion.docx (38 KB)."},
            {"type": "tool_result", "tool_use_id": "t5", "content": '{"exists": true, "size": "38.2 KB"}'},
        ])
        await db.add_message(cid, seg, "assistant", [{"type": "text", "text": (
            "Listo, Tony. He comparado las tres opciones más sólidas para un equipo pequeño:\n\n"
            "| | **AFFiNE** | **Anytype** | **Obsidian** |\n|---|---|---|---|\n"
            "| Colaboración en tiempo real | Sí | Sí | Con plugins |\n"
            "| Funciona sin conexión | Sí | Sí | Sí |\n"
            "| Datos en tu equipo | Opcional | Sí, cifrados | Sí |\n"
            "| Ideal para | Docs y pizarras | Privacidad | Notas personales |\n\n"
            "**Mi recomendación:** AFFiNE si colaboráis a diario; Anytype si la privacidad es prioritaria.\n\n"
            "El informe completo está en `informes/alternativas-notion.docx` y he comprobado que se ha generado bien.")}])
        for t, p, pr in [("Revisar el informe con el equipo", "Producto", "high"),
                         ("Renovar el dominio", "", "urgent"), ("Preparar la demo del viernes", "Producto", "normal")]:
            await store.task_create(t, priority=pr, project=p)
        await store.memory_add("Prefiere los informes en Word con la recomendación al principio", "preference", "informes", 4)
        await store.memory_add("Trabaja en un equipo de cinco personas", "personal", "equipo", 3)
        await db.kv_set("demo_conv", cid)
        return cid

    return asyncio.run(go())


def webp(png: bytes, name: str) -> None:
    import io

    from PIL import Image

    Image.open(io.BytesIO(png)).convert("RGB").save(OUT / f"{name}.webp", "WEBP", quality=86, method=6)


def capture(cid: str) -> None:
    from playwright.sync_api import sync_playwright

    OUT.mkdir(parents=True, exist_ok=True)
    url = f"http://127.0.0.1:{PORT}/"
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome", headless=True, args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        ctx = b.new_context(viewport={"width": 1600, "height": 1000}, device_scale_factor=1.25)
        pg = ctx.new_page()

        def demo_system(route):
            # Ventanas y procesos ficticios: las capturas son públicas
            import json

            r = route.fetch()
            data = r.json()
            data["windows"] = [
                {"process": "Code.exe", "pid": 8124, "windows": ["informe.py - jarvis - Visual Studio Code"]},
                {"process": "chrome.exe", "pid": 5520, "windows": ["Documentación de FastAPI - Google Chrome"]},
                {"process": "WINWORD.EXE", "pid": 9310, "windows": ["alternativas-notion.docx - Word"]},
                {"process": "Spotify.exe", "pid": 7741, "windows": ["Spotify Premium"]},
                {"process": "explorer.exe", "pid": 4012, "windows": ["Informes"]},
            ]
            data["processes"] = [{"name": n, "pid": pid, "mem_mb": m} for n, pid, m in [
                ("ollama.exe", 6120, 6412.4), ("chrome.exe", 5520, 1210.8), ("Code.exe", 8124, 842.1),
                ("python.exe", 3384, 611.5), ("WINWORD.EXE", 9310, 402.9), ("Spotify.exe", 7741, 318.2),
                ("explorer.exe", 4012, 166.0)]]
            route.fulfill(response=r, body=json.dumps(data), headers={**r.headers, "content-type": "application/json"})

        ctx.route("**/api/system", demo_system)

        def ready(page, stats: bool = False):
            # Espera a que la interfaz esté conectada y con datos reales del sistema
            page.wait_for_function("document.body.innerText.includes('En línea') && !document.body.innerText.includes('Sin conexión')", timeout=40000)
            if stats:
                page.wait_for_function("[...document.querySelectorAll('aside .font-mono')].some(e => /[1-9]/.test(e.textContent))", timeout=20000)

        host = platform.node()

        def shot(name: str, wait: float = 2.5, title: str = "", **kw):
            ready(pg, stats=name in ("inicio", "conversacion"))
            if title:  # la transición de página puede tardar con renderizado por software
                try:
                    pg.wait_for_function(f"[...document.querySelectorAll('main h1')].some(e => e.textContent === {title!r})", timeout=30000)
                except Exception:
                    print("  h1 visibles:", pg.evaluate("[...document.querySelectorAll('h1')].map(e => e.textContent)"), pg.url)
                    raise
            pg.wait_for_timeout(int(wait * 1000))
            # Las capturas son públicas: nunca mostrar el nombre real del equipo
            pg.evaluate("""h => { const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
                for (let n; (n = w.nextNode());) if (n.nodeValue.includes(h)) n.nodeValue = n.nodeValue.replaceAll(h, 'TONY-PC'); }""", host)
            webp(pg.screenshot(**kw), name)
            print("  OK", name)

        # Inicio vacío (núcleo + saludo)
        pg.goto(url)
        pg.evaluate("localStorage.removeItem('jarvis.conversation')")
        pg.reload()
        shot("inicio", 4)
        # Conversación con plan y herramientas
        pg.evaluate(f"localStorage.setItem('jarvis.conversation', '{cid}')")
        pg.reload()
        shot("conversacion", 4)

        def settings(tab: str, scroll: int = 0, name: str = ""):
            pg.evaluate(f"sessionStorage.setItem('jarvis.settingsTab', '{tab}')")
            pg.get_by_role("button", name="Configuración").click()
            pg.wait_for_timeout(2500)
            if scroll:
                pg.evaluate(f"document.querySelector('main .overflow-y-auto').scrollTop = {scroll}")
            shot(name or f"ajustes-{tab}", 1.5)
            pg.get_by_role("button", name="Inicio").first.click()
            pg.wait_for_timeout(800)

        settings("model", 0, "motor-ia")
        settings("voice", 640, "voces")
        for page, name in [("Sistema", "sistema"), ("Herramientas", "herramientas")]:
            pg.get_by_role("button", name=page).first.click()
            shot(name, 3, title=page)
        # Móvil
        m = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True)
        mp = m.new_page()
        mp.goto(url)
        mp.evaluate("localStorage.removeItem('jarvis.conversation')")
        mp.reload()
        mp.wait_for_function("document.body.innerText.includes('Buenos') && !document.body.innerText.includes('Sin conexión')", timeout=40000)
        mp.wait_for_timeout(3500)
        webp(mp.screenshot(), "movil")
        print("  OK movil")
        b.close()


def main() -> None:
    print(f"Datos de demostración en {DEMO}")
    cid = seed()
    env = {**os.environ, "JARVIS_DATA_DIR": str(DEMO)}
    srv = subprocess.Popen([sys.executable, "-m", "jarvis", "run", "--no-browser"], cwd=str(ROOT / "backend"), env=env,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=0x08000000)
    try:
        import urllib.request

        for _ in range(60):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{PORT}/api/session", timeout=1)
                break
            except Exception:
                time.sleep(0.5)
        capture(cid)
    finally:
        srv.terminate()


if __name__ == "__main__":
    main()
