"""Interfaz común para proveedores de IA.

Para añadir otro proveedor basta con implementar ``LLMProvider.stream_turn`` devolviendo
un ``TurnResult`` con los bloques en el formato canónico (el de la Messages API de
Anthropic: text / thinking / tool_use / tool_result) y registrarlo en ``llm/__init__.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Protocol

# Callback de eventos de streaming: (tipo, datos)
#   "text"      -> {"text": str}            fragmento de respuesta visible
#   "progress"  -> {"text": str}            nota de progreso entre herramientas
#   "tool_call" -> {"name": str, "id": str} el modelo empieza a pedir una herramienta
#   "server_tool" -> {"name": str, "input": dict}  búsqueda web / fetch en servidor
StreamCallback = Callable[[str, dict[str, Any]], Awaitable[None] | None]


@dataclass
class TurnResult:
    content: list[dict[str, Any]]
    stop_reason: str
    text: str = ""
    usage: dict[str, Any] = field(default_factory=dict)
    model: str = ""
    refusal_category: str | None = None


class LLMProvider(Protocol):
    name: str

    def is_configured(self) -> bool: ...

    async def stream_turn(self, *, system: str, messages: list[dict[str, Any]],
                          tools: list[dict[str, Any]], effort: str,
                          on_event: StreamCallback | None = None) -> TurnResult: ...

    async def simple(self, *, system: str, prompt: str, max_tokens: int = 4000,
                     effort: str = "low") -> str: ...

    async def health(self) -> dict[str, Any]: ...
