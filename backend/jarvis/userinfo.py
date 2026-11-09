"""Datos del usuario que JARVIS conoce sin tener que preguntar.

Se detectan solos y se refrescan cada pocas horas:
* Ubicación aproximada (ciudad, región, país, coordenadas y zona horaria) a partir de la IP pública.
  Se puede fijar a mano con ``user.city`` y desactivar con ``user.auto_location``.
* Cuenta de Windows, idioma del sistema y nombre del equipo.

El resultado se guarda en la tabla kv (``user_profile``) y se inyecta en el bloque <contexto> de cada turno.
"""

from __future__ import annotations

import asyncio
import ctypes
import datetime as dt
import getpass
import logging
import platform
import time
from typing import Any

import httpx

from . import db
from .config import get_config

log = logging.getLogger("jarvis.userinfo")

KEY = "user_profile"
REFRESH_S = 6 * 3600
_lock = asyncio.Lock()


def _windows_info() -> dict[str, str]:
    info: dict[str, str] = {"equipo": platform.node(), "sistema": f"{platform.system()} {platform.release()}"}
    try:
        info["cuenta"] = getpass.getuser()
    except Exception:
        pass
    try:  # nombre completo de la cuenta (vacío en cuentas locales sin nombre)
        size = ctypes.c_ulong(256)
        buf = ctypes.create_unicode_buffer(256)
        if ctypes.windll.secur32.GetUserNameExW(3, buf, ctypes.byref(size)) and buf.value.strip():
            info["nombre_cuenta"] = buf.value.strip()
    except Exception:
        pass
    try:
        buf = ctypes.create_unicode_buffer(85)
        if ctypes.windll.kernel32.GetUserDefaultLocaleName(buf, 85):
            info["idioma_sistema"] = buf.value
    except Exception:
        pass
    return info


async def _ip_location() -> dict[str, Any] | None:
    """Ubicación aproximada por IP. Dos servicios gratuitos sin clave (el primero responde en español)."""
    async with httpx.AsyncClient(timeout=6, headers={"User-Agent": "JARVIS-asistente"}) as c:
        try:
            r = (await c.get("https://ipwho.is/", params={"lang": "es"})).json()
            if r.get("success") and r.get("city"):
                return {"ciudad": r["city"], "region": r.get("region", ""), "pais": r.get("country", ""),
                        "lat": r.get("latitude"), "lon": r.get("longitude"),
                        "zona_horaria": (r.get("timezone") or {}).get("id", "")}
        except Exception as e:
            log.debug("ipwho.is: %s", e)
        try:
            r = (await c.get("https://ipapi.co/json/")).json()
            if r.get("city") and not r.get("error"):
                return {"ciudad": r["city"], "region": r.get("region", ""), "pais": r.get("country_name", ""),
                        "lat": r.get("latitude"), "lon": r.get("longitude"), "zona_horaria": r.get("timezone", "")}
        except Exception as e:
            log.debug("ipapi.co: %s", e)
    return None


async def refresh(force: bool = False) -> dict[str, Any]:
    async with _lock:
        cached = await db.kv_get(KEY) or {}
        if not force and cached and time.time() - cached.get("ts", 0) < REFRESH_S:
            return cached
        data: dict[str, Any] = {"ts": time.time(), **await asyncio.to_thread(_windows_info)}
        if get_config().user.auto_location:
            loc = await _ip_location()
            if loc:
                data["ubicacion"] = loc
            elif cached.get("ubicacion"):  # sin conexión: se conserva la última conocida
                data["ubicacion"] = cached["ubicacion"]
        await db.kv_set(KEY, data)
        if data.get("ubicacion"):
            u = data["ubicacion"]
            log.info("Ubicación detectada: %s, %s, %s", u["ciudad"], u["region"], u["pais"])
        return data


async def get(max_wait: float = 2.5) -> dict[str, Any]:
    """Perfil en caché; si caducó, se refresca en segundo plano sin hacer esperar al usuario."""
    cached = await db.kv_get(KEY) or {}
    if not cached:
        try:
            return await asyncio.wait_for(refresh(), max_wait)
        except Exception:
            return {}
    if time.time() - cached.get("ts", 0) > REFRESH_S:
        asyncio.create_task(refresh())
    return cached


async def location() -> dict[str, Any] | None:
    """Ubicación efectiva: la fijada a mano en la configuración o la detectada."""
    city = get_config().user.city.strip()
    detected = (await get()).get("ubicacion")
    if city:
        if detected and detected.get("ciudad", "").casefold() == city.casefold():
            return {**detected, "manual": True}  # misma ciudad: se aprovechan región, país y coordenadas
        return {"ciudad": city, "manual": True}
    return detected


async def context_lines() -> list[str]:
    p = await get()
    lines: list[str] = []
    loc = await location()
    if loc:
        lugar = ", ".join(x for x in (loc.get("ciudad"), loc.get("region"), loc.get("pais")) if x)
        origen = "indicada por el usuario" if loc.get("manual") else "detectada automáticamente por la conexión, aproximada"
        lines.append(f"Ubicación del usuario: {lugar} ({origen}). Úsala por defecto sin preguntar: tiempo, "
                     "horarios, comercios o sitios cercanos, noticias locales.")
    tz = (loc or {}).get("zona_horaria") or get_config().user.timezone
    hora = dt.datetime.now().astimezone()
    lines.append(f"Zona horaria: {tz} (UTC{hora:%z}). Idioma: responde siempre en español"
                 + (f"; idioma del sistema {p['idioma_sistema']}" if p.get("idioma_sistema") else "") + ".")
    cuenta = p.get("nombre_cuenta") or p.get("cuenta")
    if cuenta or p.get("equipo"):
        lines.append(f"Equipo: {p.get('equipo', '')} ({p.get('sistema', 'Windows')}), cuenta de Windows: {cuenta}")
    return lines
