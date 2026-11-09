"""Apertura y cierre de aplicaciones, URLs y carpetas."""

from __future__ import annotations

import difflib
import json
import logging
import os
import shutil
import subprocess
import time
import webbrowser
from urllib.parse import urlparse

import psutil

from ..config import get_config
from ..security import ExecContext, PermissionDenied, Risk, resolve_path
from .base import tool

log = logging.getLogger("jarvis.apps")
_NO_WINDOW = 0x08000000
_cache: tuple[float, dict[str, str]] = (0.0, {})


def start_menu_apps(refresh: bool = False) -> dict[str, str]:
    """Nombre visible -> AppID (incluye apps de escritorio y de la Microsoft Store)."""
    global _cache
    if not refresh and time.time() - _cache[0] < 600 and _cache[1]:
        return _cache[1]
    apps: dict[str, str] = {}
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "[Console]::OutputEncoding=[Text.Encoding]::UTF8; "
             "Get-StartApps | Select-Object Name,AppID | ConvertTo-Json -Compress"],
            capture_output=True, timeout=25, creationflags=_NO_WINDOW)
        raw = r.stdout or b"[]"
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("cp850", errors="replace")
        data = json.loads(text.strip().lstrip("﻿") or "[]")
        if isinstance(data, dict):
            data = [data]
        for item in data:
            if item.get("Name") and item.get("AppID"):
                apps[item["Name"]] = item["AppID"]
    except Exception as e:
        log.warning("No se pudo leer el menú Inicio: %s", e)
    _cache = (time.time(), apps)
    return apps


def _match(query: str, names: list[str]) -> str | None:
    q = query.lower().strip()
    lower = {n.lower(): n for n in names}
    if q in lower:
        return lower[q]
    starts = [n for n in names if n.lower().startswith(q)]
    if starts:
        return min(starts, key=len)
    contains = [n for n in names if q in n.lower()]
    if contains:
        return min(contains, key=len)
    close = difflib.get_close_matches(q, list(lower), n=1, cutoff=0.6)
    return lower[close[0]] if close else None


@tool(
    name="list_applications",
    description="Lista las aplicaciones que JARVIS puede abrir (lista autorizada y, si está permitido, el menú Inicio).",
    parameters={"filter": {"type": "string"}},
    category="aplicaciones", blocking=True,
)
def list_applications(params: dict, ctx: ExecContext) -> str:
    cfg = get_config().security
    names = list(cfg.app_allowlist)
    if cfg.app_mode == "start_menu":
        names += list(start_menu_apps())
    flt = (params.get("filter") or "").lower()
    names = sorted({n for n in names if flt in n.lower()})
    return json.dumps({"mode": cfg.app_mode, "count": len(names), "apps": names[:400]}, ensure_ascii=False)


@tool(
    name="open_application",
    description=(
        "Abre una aplicación por su nombre (p. ej. 'Spotify', 'Visual Studio Code', 'calculadora'). "
        "Solo aplicaciones autorizadas: la lista blanca de la configuración o, según el modo, las del menú Inicio. "
        "Opcionalmente abre un archivo/carpeta autorizado con ella (argumento 'target')."
    ),
    parameters={"name": {"type": "string"}, "target": {"type": "string", "description": "Archivo o carpeta a abrir con la app (opcional)"}},
    required=["name"], risk=Risk.MODERATE, category="aplicaciones", blocking=True,
    summary_fn=lambda p: f"Abrir {p.get('name')}" + (f" con {p.get('target')}" if p.get("target") else ""),
)
def open_application(params: dict, ctx: ExecContext) -> str:
    cfg = get_config().security
    name = params["name"]
    target = str(resolve_path(params["target"], must_exist=True)) if params.get("target") else None

    allow = {k.lower(): v for k, v in cfg.app_allowlist.items()}
    key = _match(name, list(cfg.app_allowlist))
    if key:
        cmd = allow[key.lower()]
        # Varias vías, de la más directa a la más tolerante (alias de Windows, App Paths, menú Inicio)
        exe = shutil.which(cmd)
        try:
            if exe:
                subprocess.Popen([exe] + ([target] if target else []), close_fds=True)
            else:
                os.startfile(cmd)  # type: ignore[attr-defined]
            return f"Abierto '{key}' ({exe or cmd}). Verifícalo con list_windows si vas a interactuar con él."
        except OSError:
            name = key  # se intenta por el menú Inicio con su nombre visible

    if cfg.app_mode != "start_menu" and not cfg.full_access:
        raise PermissionDenied(f"'{name}' no está en la lista de aplicaciones autorizadas.")
    apps = start_menu_apps()
    found = _match(name, list(apps))
    if not found:
        apps = start_menu_apps(refresh=True)
        found = _match(name, list(apps))
    if not found:
        return f"No encuentro ninguna aplicación llamada '{name}' en el menú Inicio."
    app_id = apps[found]
    if target and os.path.exists(app_id):
        subprocess.Popen([app_id, target], close_fds=True)
    else:
        subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{app_id}"], close_fds=True)
    return f"Abriendo '{found}'." + (" (El archivo indicado no se pudo pasar a esta app; ábrelo con open_path.)" if target and not os.path.exists(app_id) else "")


@tool(
    name="open_path",
    description="Abre un archivo o carpeta autorizado con su programa predeterminado (como hacer doble clic).",
    parameters={"path": {"type": "string"}},
    required=["path"], risk=Risk.MODERATE, category="aplicaciones", blocking=True,
    summary_fn=lambda p: f"Abrir {p.get('path')}",
)
def open_path(params: dict, ctx: ExecContext) -> str:
    p = resolve_path(params["path"], must_exist=True)
    if not get_config().security.full_access and p.suffix.lower() in {
            ".exe", ".bat", ".cmd", ".ps1", ".vbs", ".js", ".msi", ".scr", ".lnk", ".hta"}:
        raise PermissionDenied("Por seguridad, open_path no ejecuta programas ni scripts. Usa run_script.")
    os.startfile(str(p))  # type: ignore[attr-defined]
    return f"Abierto: {p}"


@tool(
    name="open_url",
    description="Abre una URL http/https en el navegador predeterminado del usuario.",
    parameters={"url": {"type": "string"}},
    required=["url"], risk=Risk.MODERATE, category="aplicaciones",
    summary_fn=lambda p: f"Abrir en el navegador: {p.get('url')}",
)
def open_url(params: dict, ctx: ExecContext) -> str:
    u = urlparse(params["url"])
    if u.scheme not in ("http", "https") or not u.netloc:
        raise PermissionDenied("Solo se permiten URLs http(s).")
    webbrowser.open(params["url"])
    return f"Abierto en el navegador: {params['url']}"


@tool(
    name="close_application",
    description=(
        "Cierra de forma ordenada (como pulsar la X) las ventanas de una aplicación por nombre de proceso "
        "(p. ej. 'notepad.exe') o por parte del título de la ventana. Requiere confirmación."
    ),
    parameters={"process_name": {"type": "string"}, "window_title": {"type": "string"}},
    risk=Risk.SENSITIVE, category="aplicaciones", blocking=True,
    summary_fn=lambda p: f"Cerrar {p.get('process_name') or p.get('window_title')}",
)
def close_application(params: dict, ctx: ExecContext) -> str:
    import win32con
    import win32gui
    import win32process

    pname = (params.get("process_name") or "").lower()
    title_q = (params.get("window_title") or "").lower()
    if not pname and not title_q:
        return "Indica process_name o window_title."
    protected = {n.lower() for n in get_config().security.protected_processes}
    closed: list[str] = []

    def cb(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        title = win32gui.GetWindowText(hwnd)
        if not title:
            return
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            name = psutil.Process(pid).name().lower()
        except Exception:
            return
        if name in protected:
            return
        if (pname and name == pname) or (title_q and title_q in title.lower()):
            win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
            closed.append(f"{title} [{name}]")

    win32gui.EnumWindows(cb, None)
    if not closed:
        return "No encontré ventanas que coincidan (o pertenecen a procesos protegidos)."
    return "Solicitud de cierre enviada a: " + "; ".join(closed[:10]) + ". Si había cambios sin guardar, la aplicación lo preguntará."
