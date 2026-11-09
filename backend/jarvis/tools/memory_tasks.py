"""Herramientas de memoria persistente y gestión de tareas/proyectos."""

from __future__ import annotations

import json
import time

from .. import store
from ..security import ExecContext, Risk
from .base import tool


def _fmt_ts(ts):
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts)) if ts else None


@tool(
    name="remember",
    description=(
        "Guarda un recuerdo persistente sobre el usuario: preferencias, datos personales que él comparte, "
        "proyectos, configuraciones o cualquier cosa que pida expresamente recordar. Escribe el recuerdo como "
        "una frase autocontenida. Antes de guardar, comprueba con recall que no exista ya (si existe, usa update_memory)."
    ),
    parameters={
        "content": {"type": "string"},
        "kind": {"type": "string", "enum": store.MEMORY_KINDS},
        "tags": {"type": "string", "description": "Palabras clave separadas por comas"},
        "importance": {"type": "integer", "description": "1-5 (5 = esencial, siempre presente)"},
    },
    required=["content"], risk=Risk.SAFE, category="memoria",
)
async def remember(params: dict, ctx: ExecContext) -> str:
    m = await store.memory_add(params["content"], params.get("kind") or "fact", params.get("tags") or "",
                               int(params.get("importance") or 3), source=ctx.source)
    return f"Recuerdo guardado (id {m['id']})."


@tool(
    name="recall",
    description="Busca en la memoria persistente recuerdos relacionados con una consulta (o lista todos si query está vacío).",
    parameters={"query": {"type": "string"}, "kind": {"type": "string", "enum": store.MEMORY_KINDS}, "limit": {"type": "integer"}},
    category="memoria",
)
async def recall(params: dict, ctx: ExecContext) -> str:
    if params.get("kind") and not params.get("query"):
        rows = await store.memory_list(params["kind"])
    else:
        rows = await store.memory_search(params.get("query") or "", int(params.get("limit") or 15))
    return json.dumps([{"id": r["id"], "kind": r["kind"], "content": r["content"], "tags": r["tags"],
                        "importance": r["importance"], "updated": _fmt_ts(r["updated_at"])} for r in rows],
                      ensure_ascii=False)


@tool(
    name="update_memory",
    description="Corrige o actualiza un recuerdo existente por su id.",
    parameters={"id": {"type": "string"}, "content": {"type": "string"}, "kind": {"type": "string", "enum": store.MEMORY_KINDS},
                "tags": {"type": "string"}, "importance": {"type": "integer"}},
    required=["id"], category="memoria",
)
async def update_memory(params: dict, ctx: ExecContext) -> str:
    m = await store.memory_update(params["id"], content=params.get("content"), kind=params.get("kind"),
                                  tags=params.get("tags"), importance=params.get("importance"))
    return "Recuerdo actualizado." if m else "No existe un recuerdo con ese id."


@tool(
    name="forget",
    description="Elimina definitivamente un recuerdo por su id. Requiere confirmación.",
    parameters={"id": {"type": "string"}, "content_preview": {"type": "string", "description": "Texto del recuerdo (para la confirmación)"}},
    required=["id"], risk=Risk.SENSITIVE, category="memoria",
    summary_fn=lambda p: f"Olvidar el recuerdo {p.get('id')}: «{p.get('content_preview', '')[:120]}»",
)
async def forget(params: dict, ctx: ExecContext) -> str:
    return "Recuerdo eliminado." if await store.memory_delete(params["id"]) else "No existía."


# ------------------------------------------------------------------ tareas

def _task_out(t: dict) -> dict:
    return {"id": t["id"], "title": t["title"], "description": t["description"], "status": t["status"],
            "priority": t["priority"], "project": t["project"], "due": t["due"],
            "created": _fmt_ts(t["created_at"]), "completed": _fmt_ts(t["completed_at"])}


@tool(
    name="create_task",
    description="Crea una tarea pendiente en la lista de tareas del usuario (opcionalmente con proyecto, prioridad y fecha).",
    parameters={"title": {"type": "string"}, "description": {"type": "string"},
                "priority": {"type": "string", "enum": ["low", "normal", "high", "urgent"]},
                "project": {"type": "string"}, "due": {"type": "string", "description": "Fecha límite ISO (YYYY-MM-DD) o texto"}},
    required=["title"], category="tareas",
)
async def create_task(params: dict, ctx: ExecContext) -> str:
    t = await store.task_create(params["title"], params.get("description") or "", params.get("priority") or "normal",
                                params.get("project") or "", params.get("due") or "")
    return json.dumps({"created": _task_out(t)}, ensure_ascii=False)


@tool(
    name="list_tasks",
    description="Lista tareas. status: 'open' (pendientes y en curso, por defecto), 'pending', 'in_progress', 'done', 'cancelled' o 'all'.",
    parameters={"status": {"type": "string", "enum": ["open", "pending", "in_progress", "done", "cancelled", "all"]},
                "project": {"type": "string"}},
    category="tareas",
)
async def list_tasks(params: dict, ctx: ExecContext) -> str:
    st = params.get("status") or "open"
    rows = await store.task_list(None if st == "all" else st, params.get("project"))
    return json.dumps([_task_out(t) for t in rows], ensure_ascii=False)


@tool(
    name="update_task",
    description="Actualiza una tarea (estado, título, prioridad, proyecto, fecha, descripción). Para completarla usa status='done'.",
    parameters={"id": {"type": "string"}, "status": {"type": "string", "enum": ["pending", "in_progress", "done", "cancelled"]},
                "title": {"type": "string"}, "description": {"type": "string"},
                "priority": {"type": "string", "enum": ["low", "normal", "high", "urgent"]},
                "project": {"type": "string"}, "due": {"type": "string"}},
    required=["id"], category="tareas",
)
async def update_task(params: dict, ctx: ExecContext) -> str:
    fields = {k: params.get(k) for k in ("status", "title", "description", "priority", "project", "due")}
    t = await store.task_update(params["id"], **fields)
    return json.dumps({"updated": _task_out(t)}, ensure_ascii=False) if t else "No existe esa tarea."


@tool(
    name="delete_task",
    description="Elimina una tarea definitivamente (para cerrarla sin borrar usa update_task con status 'cancelled'). Requiere confirmación.",
    parameters={"id": {"type": "string"}, "title": {"type": "string"}},
    required=["id"], risk=Risk.SENSITIVE, category="tareas",
    summary_fn=lambda p: f"Eliminar la tarea «{p.get('title') or p.get('id')}»",
)
async def delete_task(params: dict, ctx: ExecContext) -> str:
    return "Tarea eliminada." if await store.task_delete(params["id"]) else "No existía."
