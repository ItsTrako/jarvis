"""Aprendizaje automático sobre el usuario.

Tras cada turno en el que el usuario cuenta algo de sí mismo («trabajo en…», «me encanta…», «mi hermana…»),
un paso en segundo plano extrae los datos duraderos y los guarda en la memoria persistente. Así JARVIS no
vuelve a preguntar lo que ya sabe. Se puede desactivar con ``user.auto_learn`` y todo se revisa y borra en
la página Memoria (los recuerdos aprendidos llevan la etiqueta «auto»).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re

from .. import store
from ..config import get_config
from ..events import bus
from ..llm import get_provider

log = logging.getLogger("jarvis.learn")

# Solo se gasta una llamada al modelo cuando el mensaje parece contar algo personal
PISTAS = re.compile(
    r"\b(soy|me llamo|llámame|mi nombre|tengo \d+ años|cumplo|nací|vivo|trabajo|curro|estudio|me gusta|me gustan|"
    r"me encanta|me encantan|odio|no me gusta|prefiero|suelo|uso|juego|mi|mis|me dedico|estoy (casado|soltero|"
    r"aprendiendo|trabajando|estudiando)|tengo (un|una|dos|tres) |recuerda que|para que lo sepas|ten en cuenta)\b",
    re.I)
SENSIBLE = re.compile(r"contraseña|password|clave|pin\b|iban|tarjeta|cvv|dni|nie\b|pasaporte|\b\d{8,}\b", re.I)

SYSTEM = """Extraes datos DURADEROS sobre el usuario a partir de su mensaje, para la memoria de su asistente \
personal. Devuelve SOLO JSON válido: una lista de objetos {"dato": str, "tipo": "personal" | "preference" | \
"project", "importancia": 1-5}. Sin texto adicional.

Incluye solo lo que seguirá siendo cierto dentro de semanas y sea útil para ayudarle sin preguntar: nombre o cómo \
quiere que le llamen, edad, dónde vive, trabajo o estudios, familia, pareja, amigos y mascotas (con nombres), \
gustos, aficiones, comidas, música, equipos, herramientas y programas que usa, proyectos, horarios y rutinas, y \
cómo quiere que se le responda.
Redacta cada dato en tercera persona, breve, en español y con los nombres propios exactos \
(p. ej. "Trabaja como diseñador gráfico", "Su perra se llama Luna", "Prefiere respuestas cortas").
NO incluyas: lo que pide hacer ahora mismo, datos ya guardados, suposiciones, contraseñas, claves, datos \
bancarios, documentos de identidad ni datos de salud. Si no hay nada que guardar, devuelve []."""

_sem = asyncio.Semaphore(1)


def _tokens(t: str) -> set[str]:
    return set(store._norm(t))


def _parecido(a: str, b: str) -> float:
    x, y = _tokens(a), _tokens(b)
    return len(x & y) / max(1, len(x | y))


def _parse(raw: str) -> list[dict]:
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.S)
    i, j = raw.find("["), raw.rfind("]")
    if i < 0 or j <= i:
        return []
    try:
        data = json.loads(raw[i:j + 1])
    except json.JSONDecodeError:
        return []
    return [d for d in data if isinstance(d, dict) and isinstance(d.get("dato"), str) and d["dato"].strip()]


def should_learn(user_text: str, source: str) -> bool:
    cfg = get_config().user
    if not cfg.auto_learn or source in ("job", "automation", "scheduler"):
        return False
    t = user_text.strip()
    return 8 <= len(t) <= 4000 and bool(PISTAS.search(t))


async def learn(user_text: str, answer: str) -> list[str]:
    """Extrae y guarda datos nuevos. Devuelve los datos guardados."""
    async with _sem:
        existing = await store.memory_list()
        relacionados = await store.memory_search(user_text, limit=12)
        ya = "\n".join(f"- {m['content']}" for m in relacionados) or "(ninguno)"
        prompt = (f"Datos ya guardados (no los repitas):\n{ya}\n\n"
                  f"Mensaje del usuario:\n«{user_text.strip()[:2000]}»\n\n"
                  f"Respuesta del asistente (solo como contexto):\n«{answer.strip()[:600]}»")
        try:
            raw = await asyncio.wait_for(get_provider().simple(system=SYSTEM, prompt=prompt, max_tokens=600,
                                                               effort="low"), 90)
        except Exception as e:
            log.debug("Aprendizaje omitido: %s", e)
            return []
        saved: list[str] = []
        for d in _parse(raw)[:5]:
            dato = d["dato"].strip().rstrip(".")
            if len(dato) < 6 or SENSIBLE.search(dato):
                continue
            if any(_parecido(dato, m["content"]) >= 0.6 for m in existing):
                continue
            kind = d.get("tipo") if d.get("tipo") in ("personal", "preference", "project") else "personal"
            try:
                imp = int(d.get("importancia", 3))
            except (TypeError, ValueError):
                imp = 3
            m = await store.memory_add(dato, kind=kind, tags="auto", importance=imp, source="auto")
            existing.append(m)
            saved.append(dato)
        if saved:
            log.info("Aprendido sobre el usuario: %s", " | ".join(saved))
            bus.publish("memory_learned", facts=saved)
        return saved


def schedule(user_text: str, answer: str, source: str) -> None:
    if should_learn(user_text, source):
        asyncio.create_task(learn(user_text, answer))
