"""Búsqueda y lectura web gratuitas para el modo local (sin API key).

Con Claude se usan las herramientas web del servidor de Anthropic (mismos nombres), por eso
estas solo se activan cuando el proveedor efectivo es el modelo local.
"""

from __future__ import annotations

import ipaddress
import json
import re
import socket
from urllib.parse import urlparse

import httpx

from ..security import ExecContext, PermissionDenied, untrusted
from .base import tool

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/130.0 Safari/537.36")


def _local_mode() -> bool:
    from ..llm import is_local

    return is_local()


def _check_public(url: str) -> None:
    u = urlparse(url)
    if u.scheme not in ("http", "https") or not u.hostname:
        raise PermissionDenied("Solo se permiten URLs http(s).")
    try:
        for info in socket.getaddrinfo(u.hostname, None):
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                raise PermissionDenied("Por seguridad no se leen direcciones locales o de la red privada.")
    except socket.gaierror:
        raise PermissionDenied(f"No se puede resolver {u.hostname}")


@tool(
    name="web_search",
    description=(
        "Busca en Internet (DuckDuckGo) y devuelve títulos, URLs y fragmentos. Úsalo para cualquier "
        "información actual o que no sepas con certeza; después lee las mejores URLs con web_fetch."
    ),
    parameters={
        "query": {"type": "string", "description": "Consulta de búsqueda"},
        "max_results": {"type": "integer", "description": "Por defecto 8"},
        "news": {"type": "boolean", "description": "true para buscar noticias recientes"},
    },
    required=["query"], category="web", blocking=True, timeout_s=40, enabled_fn=_local_mode,
)
def web_search(params: dict, ctx: ExecContext) -> str:
    from ddgs import DDGS

    n = min(int(params.get("max_results") or 8), 15)
    with DDGS() as d:
        if params.get("news"):
            rows = d.news(params["query"], region="es-es", max_results=n)
            out = [{"title": r.get("title"), "url": r.get("url"), "date": r.get("date"), "snippet": r.get("body")}
                   for r in rows]
        else:
            rows = d.text(params["query"], region="es-es", max_results=n)
            out = [{"title": r.get("title"), "url": r.get("href"), "snippet": r.get("body")} for r in rows]
    if not out:
        return "Sin resultados. Prueba otra formulación."
    return untrusted("web_search", json.dumps(out, ensure_ascii=False, indent=1), 20000)


@tool(
    name="web_fetch",
    description="Descarga una página web y devuelve su texto principal (sin menús ni publicidad) para leerla o citarla.",
    parameters={"url": {"type": "string"}, "max_chars": {"type": "integer", "description": "Por defecto 12000"}},
    required=["url"], category="web", blocking=True, timeout_s=45, enabled_fn=_local_mode,
)
def web_fetch(params: dict, ctx: ExecContext) -> str:
    url = params["url"].strip()
    _check_public(url)
    r = httpx.get(url, headers={"User-Agent": UA, "Accept-Language": "es-ES,es;q=0.9,en;q=0.7"},
                  follow_redirects=True, timeout=25)
    r.raise_for_status()
    ctype = r.headers.get("content-type", "")
    if "pdf" in ctype:
        import io

        from pypdf import PdfReader

        text = "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(r.content)).pages[:30])
        title = url
    else:
        html = r.text
        import trafilatura

        text = trafilatura.extract(html, include_links=False, include_tables=True, favor_recall=True) or ""
        m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
        title = re.sub(r"\s+", " ", m.group(1)).strip() if m else url
        if len(text) < 200:  # páginas que trafilatura no reconoce: texto plano básico
            text = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"\s+", " ", text).strip()
    limit = int(params.get("max_chars") or 12000)
    return untrusted(f"web:{urlparse(str(r.url)).netloc}", f"Título: {title}\nURL: {r.url}\n\n{text}", limit)
