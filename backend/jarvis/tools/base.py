"""Sistema de herramientas: definición, registro, validación, permisos y ejecución.

Cada herramienta declara: nombre, descripción, parámetros (JSON Schema), nivel de riesgo,
categoría y su función. Añadir una herramienta = crear una función decorada con
``@tool(...)`` en cualquier módulo de ``jarvis/tools`` o en la carpeta ``plugins/`` del
proyecto. No hace falta tocar nada más.
"""

from __future__ import annotations

import asyncio
import importlib
import importlib.util
import inspect
import json
import logging
import pkgutil
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from .. import db
from ..config import PROJECT_ROOT
from ..events import bus
from ..security import (
    EmergencyStop, ExecContext, PermissionDenied, Risk, approvals, confirm_threshold, kill_switch,
)

log = logging.getLogger("jarvis.tools")


@dataclass
class ToolResult:
    content: Any                      # str o lista de bloques (texto/imagen) de la API
    is_error: bool = False
    files: list[str] = field(default_factory=list)
    summary: str = ""


Handler = Callable[[dict[str, Any], ExecContext], Awaitable[Any] | Any]


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    required: list[str]
    handler: Handler
    risk: Risk = Risk.SAFE
    category: str = "general"
    risk_fn: Callable[[dict[str, Any]], Risk] | None = None
    summary_fn: Callable[[dict[str, Any]], str] | None = None
    timeout_s: float = 120.0
    blocking: bool = False            # True -> se ejecuta en un hilo (APIs síncronas)
    enabled_fn: Callable[[], bool] | None = None

    def schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": self.parameters,
                "required": self.required,
                "additionalProperties": False,
            },
            "eager_input_streaming": True,
        }

    def risk_for(self, params: dict[str, Any]) -> Risk:
        if self.risk_fn:
            try:
                return max(self.risk, self.risk_fn(params))
            except Exception:
                return Risk.DANGEROUS
        return self.risk

    def describe(self, params: dict[str, Any]) -> str:
        if self.summary_fn:
            try:
                return self.summary_fn(params)
            except Exception:
                pass
        return f"{self.name}({json.dumps(params, ensure_ascii=False)[:300]})"

    def public(self) -> dict[str, Any]:
        return {
            "name": self.name, "description": self.description, "category": self.category,
            "risk": self.risk.label, "risk_level": int(self.risk), "parameters": self.parameters,
            "required": self.required, "enabled": self.is_enabled(),
        }

    def is_enabled(self) -> bool:
        return self.enabled_fn() if self.enabled_fn else True


class ToolRegistry:
    def __init__(self) -> None:
        self.tools: dict[str, Tool] = {}

    def register(self, t: Tool) -> None:
        if t.name in self.tools:
            log.warning("Herramienta duplicada %s: se sobrescribe", t.name)
        self.tools[t.name] = t

    def get(self, name: str) -> Tool | None:
        return self.tools.get(name)

    def schemas(self) -> list[dict[str, Any]]:
        # Orden determinista: mantiene estable el prefijo (caché y thinking preservado)
        return [t.schema() for t in sorted(self.tools.values(), key=lambda t: t.name) if t.is_enabled()]

    def public(self) -> list[dict[str, Any]]:
        return [t.public() for t in sorted(self.tools.values(), key=lambda t: (t.category, t.name))]

    # -------------------------------------------------------------- ejecución

    async def execute(self, name: str, params: Any, ctx: ExecContext, call_id: str = "") -> ToolResult:
        t = self.tools.get(name)
        started = time.time()
        if t is None:
            return ToolResult(f"Herramienta desconocida: {name}", is_error=True)
        if not t.is_enabled():
            return ToolResult(f"La herramienta {name} está desactivada en la configuración.", is_error=True)
        if not isinstance(params, dict):
            return ToolResult("INVALID_JSON: los parámetros deben ser un objeto JSON.", is_error=True)
        err = validate(params, t.parameters, t.required)
        if err:
            return ToolResult(f"Parámetros inválidos para {name}: {err}", is_error=True)

        risk = t.risk_for(params)
        summary = t.describe(params)
        bus.publish("tool_start", call_id=call_id, tool=name, risk=risk.label, summary=summary,
                    conversation_id=ctx.conversation_id, job_id=ctx.job_id, source=ctx.source)
        try:
            ctx.check_cancelled()
            from ..config import get_config

            need = risk >= confirm_threshold() or risk >= Risk.DANGEROUS
            if get_config().security.full_access:
                # Acceso total: lo que pides en el PC (texto o voz) se ejecuta sin preguntar. Lo que llega
                # por Telegram o de trabajos automáticos sigue confirmándose si es peligroso.
                need = ctx.source in ("telegram", "job", "automation") and risk >= Risk.DANGEROUS
            if need:
                approved = await approvals.request(ctx, name, risk, summary, _safe_params(params))
                if not approved:
                    await db.audit(ctx.source, "tool_denied", name, risk.label, "denied", summary)
                    res = ToolResult(
                        "El usuario NO ha autorizado esta acción (denegada o sin respuesta). "
                        "No la ejecutes por otra vía; informa al usuario y pregunta cómo seguir.",
                        is_error=True, summary="Denegado")
                    self._publish_end(call_id, name, ctx, res, started)
                    return res
                ctx.check_cancelled()

            if t.blocking:
                coro = asyncio.to_thread(t.handler, params, ctx)
            else:
                out = t.handler(params, ctx)
                coro = out if inspect.isawaitable(out) else _wrap(out)
            raw = await asyncio.wait_for(coro, timeout=t.timeout_s)
            res = raw if isinstance(raw, ToolResult) else ToolResult(raw)
            if res.files:
                ctx.files_out.extend(f for f in res.files if f not in ctx.files_out)
            await db.audit(ctx.source, "tool_executed", name, risk.label,
                           "error" if res.is_error else "ok", summary)
        except PermissionDenied as e:
            res = ToolResult(f"Permiso denegado: {e}", is_error=True, summary="Permiso denegado")
            await db.audit(ctx.source, "tool_blocked", name, risk.label, "blocked", f"{summary} :: {e}")
        except FileNotFoundError as e:
            res = ToolResult(f"No encontrado: {e}", is_error=True)
        except asyncio.TimeoutError:
            res = ToolResult(f"La herramienta superó el tiempo límite de {t.timeout_s:.0f}s.", is_error=True)
        except (EmergencyStop, asyncio.CancelledError):
            raise
        except Exception as e:  # la herramienta falló: se informa al modelo para que se recupere
            log.exception("Error en herramienta %s", name)
            res = ToolResult(f"Error ejecutando {name}: {type(e).__name__}: {e}", is_error=True)
            await db.audit(ctx.source, "tool_error", name, risk.label, "error", f"{summary} :: {e}")
        if res.is_error and "NO ha autorizado" not in str(res.content):
            res.content = (f"{res.content}\n\n[JARVIS] Este paso ha FALLADO. No digas al usuario que se ha hecho. "
                           "Resuélvelo tú: prueba otra vía (otra herramienta, otro nombre, list_applications, "
                           "run_command, write_file + open_path…), verifica el resultado y solo entonces responde. "
                           "Si de verdad es imposible, explica qué falló.")
        self._publish_end(call_id, name, ctx, res, started)
        return res

    @staticmethod
    def _publish_end(call_id: str, name: str, ctx: ExecContext, res: ToolResult, started: float) -> None:
        preview = res.summary or (res.content if isinstance(res.content, str) else "[contenido multimedia]")
        preview = str(preview).split("\n\n[JARVIS] Este paso ha FALLADO")[0]
        bus.publish("tool_end", call_id=call_id, tool=name, ok=not res.is_error,
                    preview=str(preview)[:400], duration=round(time.time() - started, 2),
                    conversation_id=ctx.conversation_id, job_id=ctx.job_id, files=res.files)


async def _wrap(value: Any) -> Any:
    return value


def _safe_params(params: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for k, v in params.items():
        s = v if isinstance(v, (int, float, bool)) or v is None else str(v)
        if isinstance(s, str) and len(s) > 1500:
            s = s[:1500] + f"… (+{len(s) - 1500} caracteres)"
        out[k] = s
    return out


_TYPES = {"string": str, "integer": int, "number": (int, float), "boolean": bool,
          "array": list, "object": dict}


def validate(params: dict[str, Any], props: dict[str, Any], required: list[str]) -> str | None:
    for r in required:
        if r not in params or params[r] is None:
            return f"falta el parámetro obligatorio '{r}'"
    for k, v in params.items():
        spec = props.get(k)
        if spec is None:
            return f"parámetro no reconocido '{k}'"
        typ = spec.get("type")
        if typ and v is not None:
            py = _TYPES.get(typ)
            if py and not isinstance(v, py) or (typ in ("integer", "number") and isinstance(v, bool)):
                return f"'{k}' debe ser de tipo {typ}"
        if "enum" in spec and v not in spec["enum"]:
            return f"'{k}' debe ser uno de {spec['enum']}"
    return None


registry = ToolRegistry()


def tool(name: str, description: str, parameters: dict[str, Any] | None = None,
         required: list[str] | None = None, risk: Risk = Risk.SAFE, category: str = "general",
         risk_fn=None, summary_fn=None, timeout_s: float = 120.0, blocking: bool = False,
         enabled_fn=None):
    """Decorador para registrar una herramienta."""

    def deco(fn: Handler) -> Handler:
        registry.register(Tool(
            name=name, description=description.strip(), parameters=parameters or {},
            required=required or [], handler=fn, risk=risk, category=category, risk_fn=risk_fn,
            summary_fn=summary_fn, timeout_s=timeout_s, blocking=blocking, enabled_fn=enabled_fn))
        return fn

    return deco


def load_all_tools() -> None:
    """Importa todos los módulos de herramientas internos y los plugins del usuario."""
    from .. import tools as pkg

    for mod in pkgutil.iter_modules(pkg.__path__):
        if mod.name != "base":
            importlib.import_module(f"{pkg.__name__}.{mod.name}")

    plugins_dir = PROJECT_ROOT / "plugins"
    if plugins_dir.exists():
        for f in sorted(plugins_dir.glob("*.py")):
            if f.name.startswith("_"):
                continue
            try:
                spec = importlib.util.spec_from_file_location(f"jarvis_plugin_{f.stem}", f)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)  # type: ignore[union-attr]
                log.info("Plugin cargado: %s", f.name)
            except Exception:
                log.exception("No se pudo cargar el plugin %s", f.name)
