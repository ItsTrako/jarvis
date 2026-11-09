"""Proveedor Claude (API oficial de Anthropic, SDK ``anthropic``).

* Streaming con ``client.beta.messages.stream`` y ``get_final_message()``.
* Pensamiento adaptativo (siempre activo en Claude Opus 5.5) con notas de progreso
  entre herramientas (``display: "updates"``).
* Herramientas del servidor: ``web_search`` y ``web_fetch`` (búsqueda y lectura web reales).
* ``fallbacks: "default"``: si un clasificador de seguridad rechaza por error una petición
  legítima, la API la reintenta en el modelo de respaldo recomendado.
* Historial solo-anexado (append-only) + ``prefix_mismatch_behavior: drop_block`` para que
  el pensamiento preservado nunca rompa una conversación.
* Modo compatible automático: si la cuenta no admite alguna beta, se reintenta sin ella.
"""

from __future__ import annotations

import inspect
import logging
from typing import Any

import anthropic

from ..config import get_config
from ..secrets import get_secret
from .base import StreamCallback, TurnResult

log = logging.getLogger("jarvis.llm")

BETA_FALLBACK = "server-side-fallback-2026-07-01"
BETA_UPDATES = "thinking-display-updates-2026-08-18"
BETA_BINDING = "thinking-binding-controls-2026-08-01"


class ProviderNotConfigured(Exception):
    pass


class AnthropicProvider:
    name = "anthropic"
    _instance: "AnthropicProvider | None" = None

    def __init__(self) -> None:
        self._client: anthropic.AsyncAnthropic | None = None
        self._key_used: str | None = None
        # Capacidades desactivadas tras un 400 de la API (modo compatible)
        self.disabled: set[str] = set()
        self.last_error: str = ""
        self.last_usage: dict[str, Any] = {}

    @classmethod
    def instance(cls) -> "AnthropicProvider":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ------------------------------------------------------------------ cliente

    def is_configured(self) -> bool:
        return bool(get_secret("anthropic_api_key"))

    def client(self) -> anthropic.AsyncAnthropic:
        key = get_secret("anthropic_api_key")
        if not key:
            raise ProviderNotConfigured(
                "No hay API key de Anthropic configurada. Añádela en Configuración → Credenciales "
                "o ejecuta 'Jarvis setup'.")
        if self._client is None or key != self._key_used:
            self._client = anthropic.AsyncAnthropic(api_key=key, max_retries=3, timeout=600.0)
            self._key_used = key
        return self._client

    # ------------------------------------------------------------------ petición

    def _server_tools(self) -> list[dict[str, Any]]:
        cfg = get_config().llm
        tools = []
        if cfg.web_search and "web_search" not in self.disabled:
            tools.append({"type": "web_search_20260209", "name": "web_search", "max_uses": 8})
        if cfg.web_fetch and "web_fetch" not in self.disabled:
            tools.append({"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": 8})
        return tools

    def _build(self, system: str, messages: list[dict], tools: list[dict], effort: str,
               max_tokens: int) -> dict[str, Any]:
        cfg = get_config().llm
        betas: list[str] = []
        thinking: dict[str, Any] = {"type": "adaptive"}
        kwargs: dict[str, Any] = {
            "model": cfg.model,
            "max_tokens": max_tokens,
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "messages": messages,
            "output_config": {"effort": effort},
            "cache_control": {"type": "ephemeral"},
        }
        all_tools = list(tools) + self._server_tools()
        if all_tools:
            kwargs["tools"] = all_tools
        if cfg.progress_updates and "updates" not in self.disabled:
            thinking["display"] = "updates"
            betas.append(BETA_UPDATES)
        if "binding" not in self.disabled:
            thinking["block_binding"] = {"prefix_mismatch_behavior": "drop_block"}
            betas.append(BETA_BINDING)
        if cfg.server_fallbacks and "fallbacks" not in self.disabled:
            kwargs["fallbacks"] = "default"
            betas.append(BETA_FALLBACK)
        if "eager" in self.disabled and kwargs.get("tools"):
            kwargs["tools"] = [{k: v for k, v in t.items() if k != "eager_input_streaming"} for t in kwargs["tools"]]
        kwargs["thinking"] = thinking
        if betas:
            kwargs["betas"] = betas
        return kwargs

    def _degrade(self, err: anthropic.BadRequestError) -> bool:
        """Ante un 400 por una función no disponible, la desactiva y devuelve True para reintentar."""
        msg = str(getattr(err, "message", err)).lower()
        rules = [
            ("fallbacks", ("fallback",)),
            ("updates", ("display", BETA_UPDATES)),
            ("binding", ("block_binding", BETA_BINDING, "prefix_mismatch")),
            ("web_fetch", ("web_fetch",)),
            ("web_search", ("web_search",)),
            ("eager", ("eager_input_streaming",)),
        ]
        for feature, needles in rules:
            if feature not in self.disabled and any(n.lower() in msg for n in needles):
                log.warning("La API rechazó '%s'; se desactiva (modo compatible). Detalle: %s", feature, msg[:300])
                self.disabled.add(feature)
                return True
        if "beta" in msg and not {"fallbacks", "updates", "binding"} <= self.disabled:
            log.warning("Beta no admitida; se desactivan todas las betas. Detalle: %s", msg[:300])
            self.disabled |= {"fallbacks", "updates", "binding"}
            return True
        return False

    # ------------------------------------------------------------------ turno con streaming

    async def stream_turn(self, *, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]],
                          effort: str, on_event: StreamCallback | None = None,
                          max_tokens: int | None = None) -> TurnResult:
        cfg = get_config().llm
        client = self.client()

        async def emit(kind: str, data: dict[str, Any]) -> None:
            if on_event is None:
                return
            r = on_event(kind, data)
            if inspect.isawaitable(r):
                await r

        for attempt in range(6):
            kwargs = self._build(system, messages, tools, effort, max_tokens or cfg.max_tokens)
            block_types: dict[int, str] = {}
            try:
                async with client.beta.messages.stream(**kwargs) as stream:
                    async for event in stream:
                        et = getattr(event, "type", "")
                        if et == "content_block_start":
                            cb = event.content_block
                            block_types[event.index] = cb.type
                            if cb.type == "tool_use":
                                await emit("tool_call", {"name": cb.name, "id": cb.id})
                            elif cb.type == "server_tool_use":
                                await emit("server_tool", {"name": cb.name, "id": cb.id})
                        elif et == "content_block_delta":
                            d = event.delta
                            if d.type == "text_delta":
                                await emit("text", {"text": d.text})
                            elif d.type == "thinking_delta" and d.thinking:
                                await emit("progress", {"text": d.thinking})
                    final = await stream.get_final_message()
                break
            except anthropic.BadRequestError as e:
                self.last_error = str(e)
                if attempt < 5 and self._degrade(e):
                    continue
                raise
            except ValueError as e:
                # JSON de herramienta imposible de parsear (eager streaming): se reintenta el turno
                log.warning("Entrada de herramienta inválida en streaming: %s", e)
                if attempt < 2:
                    continue
                raise

        content = [b.model_dump(mode="json", exclude_none=True) for b in final.content]
        # La API no acepta de vuelta campos internos de solo-respuesta en algunos bloques
        for b in content:
            b.pop("parsed_output", None)
        text = "".join(b.get("text", "") for b in content if b.get("type") == "text")
        usage = final.usage.model_dump(mode="json", exclude_none=True) if final.usage else {}
        self.last_usage = usage
        refusal = None
        if final.stop_reason == "refusal":
            sd = getattr(final, "stop_details", None)
            refusal = getattr(sd, "category", None) if sd else None
        self.last_error = ""
        return TurnResult(content=content, stop_reason=final.stop_reason or "end_turn", text=text,
                          usage=usage, model=final.model, refusal_category=refusal)

    async def simple(self, *, system: str, prompt: str, max_tokens: int = 4000, effort: str = "low") -> str:
        res = await self.stream_turn(system=system, messages=[{"role": "user", "content": prompt}],
                                     tools=[], effort=effort, max_tokens=max_tokens)
        return res.text

    async def health(self) -> dict[str, Any]:
        if not self.is_configured():
            return {"ok": False, "status": "sin_api_key", "detail": "Falta la API key de Anthropic"}
        try:
            m = await self.client().models.retrieve(get_config().llm.model)
            return {"ok": True, "status": "operativo", "model": m.id, "display_name": getattr(m, "display_name", m.id),
                    "compat_disabled": sorted(self.disabled)}
        except anthropic.AuthenticationError:
            return {"ok": False, "status": "api_key_invalida", "detail": "La API key no es válida"}
        except anthropic.NotFoundError:
            return {"ok": False, "status": "modelo_no_disponible", "detail": f"Modelo {get_config().llm.model} no disponible"}
        except anthropic.APIConnectionError:
            return {"ok": False, "status": "sin_conexion", "detail": "No hay conexión con la API"}
        except Exception as e:
            return {"ok": False, "status": "error", "detail": str(e)[:200]}
