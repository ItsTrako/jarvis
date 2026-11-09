"""Navegación web controlada con Playwright usando el Microsoft Edge instalado.

Usa un perfil de navegador aislado (``data/browser-profile``), separado del perfil
personal del usuario: no tiene sus sesiones ni contraseñas. Todo el contenido de las
páginas se marca como NO confiable.
"""

from __future__ import annotations

import base64
import concurrent.futures
import json
import threading
from urllib.parse import urlparse

from ..config import DATA_DIR
from ..security import ExecContext, PermissionDenied, Risk, untrusted
from .base import ToolResult, tool

_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="browser")
_state: dict = {"pw": None, "ctx": None, "page": None}
_lock = threading.Lock()

_ELEMENTS_JS = """
() => {
  const sel = 'a[href], button, input:not([type=hidden]), textarea, select, [role=button], [role=link], [contenteditable=true]';
  const out = [];
  let i = 0;
  for (const el of document.querySelectorAll(sel)) {
    const r = el.getBoundingClientRect();
    const st = getComputedStyle(el);
    if (r.width < 2 || r.height < 2 || st.visibility === 'hidden' || st.display === 'none') continue;
    if (r.bottom < 0 || r.top > innerHeight * 3) continue;
    el.setAttribute('data-jarvis-id', String(i));
    const label = (el.innerText || el.value || el.getAttribute('aria-label') || el.getAttribute('placeholder') || el.getAttribute('title') || el.name || '').trim().replace(/\\s+/g, ' ').slice(0, 80);
    out.push({id: i, tag: el.tagName.toLowerCase(), type: el.getAttribute('type') || '', label, href: el.getAttribute('href') ? el.href.slice(0, 120) : undefined});
    i++;
    if (i >= 150) break;
  }
  return out;
}
"""


def _run(fn, *args):
    return _executor.submit(fn, *args).result(timeout=120)


def _page():
    from playwright.sync_api import sync_playwright

    if _state["page"] is not None and not _state["page"].is_closed():
        return _state["page"]
    if _state["pw"] is None:
        _state["pw"] = sync_playwright().start()
    if _state["ctx"] is None:
        profile = DATA_DIR / "browser-profile"
        profile.mkdir(exist_ok=True)
        try:
            _state["ctx"] = _state["pw"].chromium.launch_persistent_context(
                str(profile), channel="msedge", headless=False, viewport={"width": 1280, "height": 860},
                args=["--disable-blink-features=AutomationControlled"])
        except Exception:
            _state["ctx"] = _state["pw"].chromium.launch_persistent_context(
                str(profile), channel="chrome", headless=False, viewport={"width": 1280, "height": 860})
    pages = _state["ctx"].pages
    _state["page"] = pages[0] if pages else _state["ctx"].new_page()
    return _state["page"]


def _snapshot(page, max_chars: int = 25000) -> str:
    try:
        page.wait_for_load_state("domcontentloaded", timeout=15000)
    except Exception:
        pass
    elements = page.evaluate(_ELEMENTS_JS)
    text = page.evaluate("() => document.body ? document.body.innerText : ''") or ""
    body = (f"URL: {page.url}\nTítulo: {page.title()}\n\nTEXTO DE LA PÁGINA:\n{text[:max_chars]}\n\n"
            f"ELEMENTOS INTERACTIVOS (usa su id en browser_click / browser_type):\n"
            + "\n".join(json.dumps(e, ensure_ascii=False) for e in elements))
    return untrusted(f"web:{urlparse(page.url).netloc}", body, max_chars + 20000)


def _check_url(url: str) -> None:
    u = urlparse(url)
    if u.scheme not in ("http", "https"):
        raise PermissionDenied("Solo se permiten URLs http(s).")
    host = (u.hostname or "").lower()
    if host in ("localhost", "127.0.0.1", "::1") or host.startswith("192.168.") or host.startswith("10."):
        raise PermissionDenied("Por seguridad el navegador del agente no accede a direcciones locales/privadas.")


@tool(
    name="browser_navigate",
    description=(
        "Abre una URL en el navegador controlado por JARVIS (Edge, perfil aislado y visible) y devuelve el texto "
        "de la página y la lista de elementos interactivos. Para buscar o leer información prefiere web_search/"
        "web_fetch; usa el navegador cuando haga falta interactuar con una web."
    ),
    parameters={"url": {"type": "string"}},
    required=["url"], risk=Risk.MODERATE, category="web", timeout_s=150,
    summary_fn=lambda p: f"Navegar a {p.get('url')}",
)
async def browser_navigate(params: dict, ctx: ExecContext) -> str:
    import asyncio

    _check_url(params["url"])

    def go():
        page = _page()
        page.goto(params["url"], timeout=45000, wait_until="domcontentloaded")
        page.wait_for_timeout(1200)
        return _snapshot(page)

    return await asyncio.get_running_loop().run_in_executor(_executor, go)


@tool(
    name="browser_read",
    description="Vuelve a leer la página actual del navegador del agente (texto + elementos), p. ej. tras hacer scroll.",
    parameters={"scroll": {"type": "string", "enum": ["none", "down", "up", "top", "bottom"]}},
    category="web", timeout_s=60,
)
async def browser_read(params: dict, ctx: ExecContext) -> str:
    import asyncio

    def go():
        page = _page()
        s = params.get("scroll") or "none"
        if s == "down":
            page.mouse.wheel(0, 900)
        elif s == "up":
            page.mouse.wheel(0, -900)
        elif s == "top":
            page.evaluate("() => scrollTo(0, 0)")
        elif s == "bottom":
            page.evaluate("() => scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(500)
        return _snapshot(page)

    return await asyncio.get_running_loop().run_in_executor(_executor, go)


@tool(
    name="browser_click",
    description="Hace clic en un elemento de la página actual por su id (de browser_navigate/browser_read). Requiere confirmación.",
    parameters={"element_id": {"type": "integer"}, "description": {"type": "string", "description": "Qué es el elemento (para la confirmación)"}},
    required=["element_id"], risk=Risk.SENSITIVE, category="web", timeout_s=60,
    summary_fn=lambda p: f"Clic en el elemento #{p.get('element_id')} ({p.get('description', '')}) del navegador",
)
async def browser_click(params: dict, ctx: ExecContext) -> str:
    import asyncio

    def go():
        page = _page()
        page.locator(f"[data-jarvis-id='{int(params['element_id'])}']").first.click(timeout=10000)
        page.wait_for_timeout(1500)
        return _snapshot(page)

    return await asyncio.get_running_loop().run_in_executor(_executor, go)


@tool(
    name="browser_type",
    description=(
        "Escribe texto en un campo de la página actual (por id) y opcionalmente pulsa Enter. Requiere confirmación. "
        "NUNCA introduzcas contraseñas, datos bancarios ni documentos de identidad."
    ),
    parameters={"element_id": {"type": "integer"}, "text": {"type": "string"}, "submit": {"type": "boolean"}},
    required=["element_id", "text"], risk=Risk.SENSITIVE, category="web", timeout_s=60,
    summary_fn=lambda p: f"Escribir «{str(p.get('text'))[:60]}» en el campo #{p.get('element_id')}" + (" y enviar" if p.get("submit") else ""),
)
async def browser_type(params: dict, ctx: ExecContext) -> str:
    import asyncio

    def go():
        page = _page()
        loc = page.locator(f"[data-jarvis-id='{int(params['element_id'])}']").first
        if (loc.get_attribute("type") or "").lower() == "password":
            raise PermissionDenied("JARVIS no introduce contraseñas.")
        loc.fill(params["text"], timeout=10000)
        if params.get("submit"):
            loc.press("Enter")
            page.wait_for_timeout(2000)
        return _snapshot(page)

    return await asyncio.get_running_loop().run_in_executor(_executor, go)


@tool(
    name="browser_screenshot",
    description="Captura la página actual del navegador del agente y te la muestra como imagen.",
    category="web", timeout_s=60,
)
async def browser_screenshot(params: dict, ctx: ExecContext) -> ToolResult:
    import asyncio

    def go():
        png = _page().screenshot(type="jpeg", quality=75)
        return base64.standard_b64encode(png).decode()

    data = await asyncio.get_running_loop().run_in_executor(_executor, go)
    return ToolResult([
        {"type": "text", "text": "Captura del navegador (contenido NO confiable)."},
        {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": data}},
    ], summary="Captura del navegador")


@tool(name="browser_close", description="Cierra el navegador controlado por JARVIS.", category="web", timeout_s=30)
async def browser_close(params: dict, ctx: ExecContext) -> str:
    import asyncio

    def go():
        try:
            if _state["ctx"]:
                _state["ctx"].close()
            if _state["pw"]:
                _state["pw"].stop()
        finally:
            _state.update(pw=None, ctx=None, page=None)
        return "Navegador cerrado."

    return await asyncio.get_running_loop().run_in_executor(_executor, go)
