"""Cerebro de JARVIS: bucle agéntico con herramientas, plan, memoria y recuperación de errores.

Todas las interfaces (UI web, voz, Telegram, trabajos en segundo plano, automatizaciones)
llaman a ``Agent.run``. Una conversación solo ejecuta un turno a la vez (lock por conversación).
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
from dataclasses import dataclass, field
from typing import Any

import anthropic

from .. import db, store, userinfo
from ..config import get_config
from ..events import bus
from ..llm import get_provider
from ..llm.anthropic_provider import ProviderNotConfigured
from ..security import EmergencyStop, ExecContext, kill_switch
from ..tools.base import registry
from .prompts import COMPACTION_PROMPT, SYSTEM_PROMPT

log = logging.getLogger("jarvis.agent")

WEEKDAYS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


async def _engine_description() -> str:
    from ..llm import active_provider_name

    cfg = get_config().llm
    if active_provider_name() == "anthropic":
        return f"Claude ({cfg.model}) de Anthropic, en la nube, vía su API oficial"
    from ..llm.ollama_provider import CATALOG, OllamaProvider

    try:
        model = await OllamaProvider.instance().pick_model()
    except Exception:
        model = cfg.local_model
    cat = next((c for c in CATALOG if c["id"] == model), None)
    name = f"{cat['name']} de {cat['vendor']}" if cat else model
    return f"{name}, modelo abierto ejecutado en local en la GPU del usuario mediante Ollama (gratuito y privado)"


@dataclass
class AgentResult:
    text: str
    files: list[str] = field(default_factory=list)
    error: str | None = None
    stopped: bool = False
    iterations: int = 0


@dataclass
class _Run:
    task: asyncio.Task
    ctx: ExecContext
    source: str


class Agent:
    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}
        self.active: dict[str, _Run] = {}  # conversation_id -> ejecución en curso

    # ------------------------------------------------------------------ API pública

    def is_busy(self, conversation_id: str) -> bool:
        r = self.active.get(conversation_id)
        return bool(r and not r.task.done())

    def status(self) -> dict[str, Any]:
        return {"running": [{"conversation_id": cid, "source": r.source} for cid, r in self.active.items()
                            if not r.task.done()]}

    async def stop(self, conversation_id: str | None = None) -> int:
        """Detiene la ejecución de una conversación (o todas si no se indica)."""
        n = 0
        for cid, r in list(self.active.items()):
            if conversation_id and cid != conversation_id:
                continue
            if not r.task.done():
                r.ctx.cancel_event.set()
                r.task.cancel()
                n += 1
        return n

    async def run(self, conversation_id: str, user_content: str | list[dict[str, Any]], ctx: ExecContext,
                  interface: str = "pc", effort: str | None = None) -> AgentResult:
        """Ejecuta un turno completo. Se puede cancelar con ``stop``."""
        ctx.conversation_id = conversation_id
        task = asyncio.current_task()
        lock = self._locks.setdefault(conversation_id, asyncio.Lock())
        async with lock:
            if task is not None:
                self.active[conversation_id] = _Run(task, ctx, ctx.source)
                kill_switch.track(task)
            try:
                return await self._run(conversation_id, user_content, ctx, interface, effort)
            finally:
                self.active.pop(conversation_id, None)

    # ------------------------------------------------------------------ implementación

    async def _context_block(self, text: str, interface: str, ctx: ExecContext) -> str:
        cfg = get_config()
        now = dt.datetime.now()
        lines = [
            f"Fecha y hora local: {WEEKDAYS[now.weekday()]} {now:%d/%m/%Y %H:%M}",
            f"Interfaz: {interface} (origen: {ctx.source})",
            f"Motor de IA que te hace razonar ahora: {await _engine_description()}",
        ]
        if cfg.user.name:
            lines.append(f"Nombre del usuario: {cfg.user.name}")
        try:
            lines += await userinfo.context_lines()
        except Exception:
            log.debug("Perfil del usuario no disponible", exc_info=True)
        mem = await store.memory_context(text)
        if mem:
            lines.append("Recuerdos relevantes (memoria persistente):\n" + mem)
        open_tasks = await store.task_list("open")
        if open_tasks:
            lines.append(f"Tareas abiertas del usuario: {len(open_tasks)} (usa list_tasks para el detalle)")
        jobs = await store.job_list(10, active_only=True)
        if jobs:
            lines.append("Trabajos en segundo plano activos: " + "; ".join(f"{j['title']} ({j['status']}, id {j['id']})" for j in jobs))
        return "<contexto>\n" + "\n".join(lines) + "\n</contexto>"

    async def _run(self, cid: str, user_content: str | list[dict[str, Any]], ctx: ExecContext,
                   interface: str, effort: str | None) -> AgentResult:
        cfg = get_config()
        provider = get_provider()
        conv = await db.get_conversation(cid)
        if conv is None:
            raise ValueError(f"Conversación inexistente: {cid}")
        segment = conv["segment"]

        blocks = [{"type": "text", "text": user_content}] if isinstance(user_content, str) else list(user_content)
        plain = " ".join(b.get("text", "") for b in blocks if b.get("type") == "text")
        context = await self._context_block(plain, interface, ctx)
        user_msg = [{"type": "text", "text": context}] + blocks
        await db.add_message(cid, segment, "user", user_msg, ctx.source)
        if conv["title"] in ("Nueva conversación", "") and plain.strip():
            title = plain.strip().replace("\n", " ")
            await db.update_conversation(cid, title=title[:70] + ("…" if len(title) > 70 else ""))

        bus.publish("run_start", conversation_id=cid, source=ctx.source, job_id=ctx.job_id)
        result = AgentResult(text="")
        pending_tool_ids: list[str] = []
        texts: list[str] = []

        async def on_event(kind: str, data: dict[str, Any]) -> None:
            if kind == "text":
                bus.publish("assistant_delta", conversation_id=cid, text=data["text"], job_id=ctx.job_id)
            elif kind == "progress":
                bus.publish("progress", conversation_id=cid, text=data["text"], job_id=ctx.job_id)
            elif kind in ("tool_call", "server_tool"):
                bus.publish("tool_requested", conversation_id=cid, tool=data["name"], job_id=ctx.job_id)

        try:
            if not provider.is_configured():
                raise ProviderNotConfigured(
                    "Todavía no tengo acceso al modelo de IA: falta la API key de Anthropic. "
                    "Configúrala en Configuración → Credenciales (o ejecuta `Jarvis setup`).")
            tools = registry.schemas()
            for iteration in range(cfg.llm.max_tool_iterations):
                ctx.check_cancelled()
                result.iterations = iteration + 1
                history = [{"role": m["role"], "content": m["content"]} for m in await db.get_messages(cid, segment)]
                turn = await provider.stream_turn(system=SYSTEM_PROMPT, messages=history, tools=tools,
                                                  effort=effort or cfg.llm.effort, on_event=on_event)
                await db.add_message(cid, segment, "assistant", turn.content, ctx.source)
                if turn.usage.get("input_tokens") is not None:
                    total_in = (turn.usage.get("input_tokens", 0) + turn.usage.get("cache_read_input_tokens", 0)
                                + turn.usage.get("cache_creation_input_tokens", 0))
                    await db.update_conversation(cid, input_tokens=total_in)
                if turn.text:
                    texts.append(turn.text)

                if turn.stop_reason == "refusal":
                    texts.append("\n\n_(El sistema de seguridad del modelo ha declinado esta petición"
                                 + (f" — categoría: {turn.refusal_category}" if turn.refusal_category else "")
                                 + ". Si crees que es un error, reformúlala.)_")
                    break
                if turn.stop_reason == "pause_turn":
                    continue  # herramienta del servidor en curso: se reanuda con el mismo historial

                tool_uses = [b for b in turn.content if b.get("type") == "tool_use"]
                if not tool_uses:
                    if turn.stop_reason == "max_tokens":
                        texts.append("\n\n_(Respuesta truncada por longitud. Pídeme que continúe.)_")
                    break
                if turn.stop_reason == "max_tokens":
                    # Entrada de herramienta posiblemente truncada: no se ejecuta
                    pending_tool_ids = [b["id"] for b in tool_uses]
                    await self._close_pending(cid, segment, pending_tool_ids, ctx,
                                              "Entrada truncada por límite de tokens; no ejecutada. Divide la tarea.")
                    pending_tool_ids = []
                    continue

                pending_tool_ids = [b["id"] for b in tool_uses]
                results = []
                for b in tool_uses:
                    ctx.check_cancelled()
                    res = await registry.execute(b["name"], b.get("input"), ctx, call_id=b["id"])
                    content = res.content if isinstance(res.content, list) else str(res.content)
                    results.append({"type": "tool_result", "tool_use_id": b["id"], "content": content,
                                    **({"is_error": True} if res.is_error else {})})
                    pending_tool_ids.remove(b["id"])
                await db.add_message(cid, segment, "user", results, ctx.source)
            else:
                texts.append("\n\n_(He alcanzado el límite de pasos para esta petición. Dime si continúo.)_")

            result.text = "\n\n".join(t.strip() for t in texts if t.strip()) or "(Sin respuesta de texto.)"
        except (asyncio.CancelledError, EmergencyStop) as e:
            result.stopped = True
            result.text = ("Parada de emergencia: he detenido la tarea." if isinstance(e, EmergencyStop) or kill_switch.engaged
                           else "Tarea detenida a petición tuya.")
            if texts:
                result.text = "\n\n".join(texts) + "\n\n" + result.text
            await self._close_pending(cid, segment, pending_tool_ids, ctx, "Cancelado por el usuario antes de completarse.")
            await db.add_message(cid, segment, "assistant", [{"type": "text", "text": f"[{result.text}]"}], ctx.source)
        except ProviderNotConfigured as e:
            result.error = str(e)
            result.text = str(e)
        except anthropic.AuthenticationError:
            result.error = result.text = "La API key de Anthropic no es válida. Revísala en Configuración → Credenciales."
        except anthropic.RateLimitError:
            result.error = result.text = "La API de Claude está limitando las peticiones (rate limit). Inténtalo en un momento."
        except anthropic.APIConnectionError:
            result.error = result.text = "No puedo conectar con la API de Claude. Comprueba la conexión a Internet."
        except anthropic.APIStatusError as e:
            log.exception("Error de API")
            result.error = f"Error de la API de Claude ({e.status_code}): {getattr(e, 'message', e)}"
            result.text = result.error
            await self._close_pending(cid, segment, pending_tool_ids, ctx, "Interrumpido por un error.")
        except Exception as e:
            log.exception("Fallo en el agente")
            result.error = f"{type(e).__name__}: {e}"
            result.text = f"Ha ocurrido un error interno: {result.error}"
            await self._close_pending(cid, segment, pending_tool_ids, ctx, "Interrumpido por un error interno.")

        result.files = list(dict.fromkeys(ctx.files_out))
        if not (result.error or result.stopped):
            from . import learn  # aprende datos duraderos del usuario en segundo plano

            learn.schedule(plain, result.text, ctx.source)
        bus.publish("run_end", conversation_id=cid, text=result.text, files=result.files, error=result.error,
                    stopped=result.stopped, job_id=ctx.job_id, source=ctx.source)
        await self._maybe_compact(cid)
        return result

    async def _close_pending(self, cid: str, segment: int, ids: list[str], ctx: ExecContext, reason: str) -> None:
        """Mantiene el historial válido: todo tool_use necesita su tool_result."""
        if not ids:
            return
        msgs = await db.get_messages(cid, segment)
        if not msgs or msgs[-1]["role"] != "assistant":
            return
        last_ids = {b.get("id") for b in msgs[-1]["content"] if b.get("type") == "tool_use"}
        ids = [i for i in ids if i in last_ids]
        if ids:
            await db.add_message(cid, segment, "user", [
                {"type": "tool_result", "tool_use_id": i, "content": reason, "is_error": True} for i in ids
            ], ctx.source)

    async def _maybe_compact(self, cid: str) -> None:
        """Compactación simple: al superar el umbral, resume y abre un segmento nuevo."""
        conv = await db.get_conversation(cid)
        if not conv or conv["input_tokens"] < get_config().llm.compact_after_tokens:
            return
        try:
            msgs = await db.get_messages(cid, conv["segment"])
            transcript = []
            for m in msgs:
                for b in m["content"] if isinstance(m["content"], list) else [{"type": "text", "text": m["content"]}]:
                    if b.get("type") == "text":
                        transcript.append(f"{m['role'].upper()}: {b['text'][:4000]}")
                    elif b.get("type") == "tool_use":
                        transcript.append(f"HERRAMIENTA {b['name']}: {str(b.get('input'))[:500]}")
            summary = await get_provider().simple(system=COMPACTION_PROMPT, prompt="\n".join(transcript)[-400_000:],
                                                  max_tokens=6000, effort="low")
            seg = conv["segment"] + 1
            await db.update_conversation(cid, segment=seg, input_tokens=0)
            await db.add_message(cid, seg, "user", [{"type": "text", "text":
                "<resumen_conversacion_anterior>\n" + summary + "\n</resumen_conversacion_anterior>"}], "system")
            bus.publish("conversation_compacted", conversation_id=cid)
            log.info("Conversación %s compactada (segmento %d)", cid, seg)
        except Exception:
            log.exception("No se pudo compactar la conversación %s", cid)


agent = Agent()


# ------------------------------------------------------------------ vista para la UI

def to_display(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convierte el historial en formato API a elementos legibles para la interfaz."""
    items: list[dict[str, Any]] = []
    tool_index: dict[str, dict[str, Any]] = {}
    for m in messages:
        content = m["content"] if isinstance(m["content"], list) else [{"type": "text", "text": str(m["content"])}]
        if m["role"] == "user":
            texts, attachments = [], []
            for b in content:
                t = b.get("type")
                if t == "text":
                    txt = b["text"]
                    if txt.startswith("<contexto>"):
                        continue
                    if txt.startswith("<resumen_conversacion_anterior>"):
                        items.append({"kind": "note", "text": "Conversación compactada: el historial anterior se ha resumido.",
                                      "ts": m["created_at"]})
                        continue
                    texts.append(txt)
                elif t == "tool_result":
                    item = tool_index.get(b.get("tool_use_id"))
                    if item is not None:
                        c = b.get("content")
                        if isinstance(c, list):
                            c = " ".join(x.get("text", "[imagen]") if x.get("type") == "text" else "[imagen]" for x in c)
                        item["result"] = str(c).split("\n\n[JARVIS] Este paso ha FALLADO")[0][:3000]
                        item["is_error"] = bool(b.get("is_error"))
                elif t in ("image", "document"):
                    attachments.append(t)
            if texts or attachments:
                items.append({"kind": "user", "text": "\n".join(texts), "attachments": attachments,
                              "source": m["source"], "ts": m["created_at"], "id": m["id"]})
        else:
            for b in content:
                t = b.get("type")
                if t == "text" and b.get("text", "").strip():
                    items.append({"kind": "assistant", "text": b["text"], "ts": m["created_at"], "id": m["id"],
                                  "source": m["source"]})
                elif t == "thinking" and b.get("thinking", "").strip():
                    items.append({"kind": "progress", "text": b["thinking"], "ts": m["created_at"]})
                elif t in ("tool_use", "server_tool_use"):
                    item = {"kind": "tool", "id": b["id"], "name": b["name"], "input": b.get("input"),
                            "result": None, "is_error": False, "ts": m["created_at"], "server": t == "server_tool_use"}
                    tool_index[b["id"]] = item
                    items.append(item)
                elif t.endswith("_tool_result"):
                    item = tool_index.get(b.get("tool_use_id"))
                    if item is not None:
                        c = b.get("content")
                        if isinstance(c, list):
                            item["result"] = f"{len(c)} resultados: " + "; ".join(
                                f"{x.get('title', '')} ({x.get('url', '')})" for x in c[:6] if isinstance(x, dict))
                        elif isinstance(c, dict):
                            if c.get("error_code"):
                                item["result"], item["is_error"] = f"Error: {c['error_code']}", True
                            else:
                                item["result"] = f"Leído: {c.get('url', '')}"
    # Unir textos consecutivos del asistente
    merged: list[dict[str, Any]] = []
    for it in items:
        if merged and it["kind"] == "assistant" and merged[-1]["kind"] == "assistant":
            merged[-1]["text"] += "\n\n" + it["text"]
        else:
            merged.append(it)
    return merged
