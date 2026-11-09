"""Herramientas de planificación, trabajos en segundo plano, automatizaciones y notificaciones."""

from __future__ import annotations

import json
import time
from pathlib import Path

from .. import notifier, store
from ..events import bus
from ..security import ExecContext, Risk, resolve_path
from .base import ToolResult, tool


@tool(
    name="update_plan",
    description=(
        "Publica o actualiza el plan de la tarea actual para que el usuario vea el progreso en tiempo real. "
        "Envía SIEMPRE la lista completa de pasos con su estado (pending, in_progress, done, failed). "
        "Úsalo en cualquier tarea de 3 o más pasos: al empezar, y cada vez que un paso cambie de estado."
    ),
    parameters={
        "goal": {"type": "string", "description": "Objetivo de la tarea en una frase"},
        "steps": {"type": "array", "items": {"type": "object", "properties": {
            "title": {"type": "string"}, "status": {"type": "string", "enum": ["pending", "in_progress", "done", "failed"]}}}},
    },
    required=["steps"], category="planificación",
)
async def update_plan(params: dict, ctx: ExecContext) -> str:
    steps = [{"title": str(s.get("title", ""))[:200], "status": s.get("status", "pending")}
             for s in params["steps"] if isinstance(s, dict)][:30]
    bus.publish("plan", conversation_id=ctx.conversation_id, job_id=ctx.job_id, goal=params.get("goal", ""),
                steps=steps)
    if ctx.job_id:
        await store.job_update(ctx.job_id, plan=steps)
    done = sum(1 for s in steps if s["status"] == "done")
    return f"Plan actualizado ({done}/{len(steps)} completados)."


@tool(
    name="start_background_task",
    description=(
        "Lanza un trabajo en segundo plano (investigaciones largas, informes, tareas de varios pasos) que se ejecuta "
        "de forma autónoma mientras el usuario sigue con otras cosas. Al terminar, el usuario recibe una notificación "
        "en el escritorio y en Telegram con el resumen y los archivos. Las instrucciones deben ser completas y "
        "autocontenidas (el trabajo no ve esta conversación)."
    ),
    parameters={
        "title": {"type": "string", "description": "Título corto"},
        "instructions": {"type": "string", "description": "Instrucciones completas y autocontenidas"},
    },
    required=["title", "instructions"], risk=Risk.MODERATE, category="planificación",
    summary_fn=lambda p: f"Lanzar en segundo plano: {p.get('title')}",
)
async def start_background_task(params: dict, ctx: ExecContext) -> str:
    from ..agent.jobs import jobs

    job = await jobs.start(params["title"], params["instructions"],
                           origin="telegram" if ctx.source == "telegram" else "ui", chat_id=ctx.chat_id)
    return f"Trabajo lanzado en segundo plano (id {job['id']}). Avisaré al usuario cuando termine."


@tool(
    name="check_background_tasks",
    description="Consulta el estado de los trabajos en segundo plano (todos los recientes o uno por id), incluido su resultado.",
    parameters={"job_id": {"type": "string"}, "limit": {"type": "integer"}},
    category="planificación",
)
async def check_background_tasks(params: dict, ctx: ExecContext) -> str:
    def fmt(j):
        return {"id": j["id"], "title": j["title"], "status": j["status"], "plan": j["plan"],
                "created": time.strftime("%d/%m %H:%M", time.localtime(j["created_at"])),
                "finished": time.strftime("%d/%m %H:%M", time.localtime(j["finished_at"])) if j["finished_at"] else None,
                "result": (j["result"] or "")[:4000], "error": j["error"], "files": j["files"]}

    if params.get("job_id"):
        j = await store.job_get(params["job_id"])
        return json.dumps(fmt(j), ensure_ascii=False) if j else "No existe ese trabajo."
    rows = await store.job_list(int(params.get("limit") or 10))
    return json.dumps([fmt(j) for j in rows], ensure_ascii=False)


@tool(
    name="cancel_background_task",
    description="Detiene un trabajo en segundo plano en curso.",
    parameters={"job_id": {"type": "string"}},
    required=["job_id"], risk=Risk.MODERATE, category="planificación",
    summary_fn=lambda p: f"Detener el trabajo {p.get('job_id')}",
)
async def cancel_background_task(params: dict, ctx: ExecContext) -> str:
    from ..agent.jobs import jobs

    return "Trabajo detenido." if await jobs.cancel(params["job_id"]) else "Ese trabajo no está en ejecución."


# ------------------------------------------------------------------ automatizaciones

@tool(
    name="create_automation",
    description=(
        "Crea una automatización periódica: JARVIS ejecutará las instrucciones según la programación y notificará "
        "el resultado. schedule_type: 'daily' (value 'HH:MM'), 'weekly' (value 'lun,mie,vie HH:MM') o 'interval' "
        "(value = minutos, mínimo 5). Requiere confirmación."
    ),
    parameters={
        "name": {"type": "string"},
        "instructions": {"type": "string", "description": "Qué debe hacer en cada ejecución (autocontenido)"},
        "schedule_type": {"type": "string", "enum": ["daily", "weekly", "interval"]},
        "schedule_value": {"type": "string"},
        "notify": {"type": "string", "enum": ["all", "desktop", "telegram", "none"]},
    },
    required=["name", "instructions", "schedule_type", "schedule_value"], risk=Risk.SENSITIVE,
    category="automatización",
    summary_fn=lambda p: f"Crear automatización «{p.get('name')}» ({p.get('schedule_type')} {p.get('schedule_value')}): {str(p.get('instructions'))[:200]}",
)
async def create_automation(params: dict, ctx: ExecContext) -> str:
    from ..agent.jobs import compute_next_run, describe_schedule

    nxt = compute_next_run(params["schedule_type"], params["schedule_value"])
    a = await store.automation_create(params["name"], params["instructions"], params["schedule_type"],
                                      params["schedule_value"], params.get("notify") or "all", nxt)
    return (f"Automatización creada (id {a['id']}), {describe_schedule(a['schedule_type'], a['schedule_value'])}. "
            f"Próxima ejecución: {time.strftime('%d/%m/%Y %H:%M', time.localtime(nxt))}.")


@tool(
    name="list_automations",
    description="Lista las automatizaciones programadas con su estado y próxima ejecución.",
    category="automatización",
)
async def list_automations(params: dict, ctx: ExecContext) -> str:
    rows = await store.automation_list()
    return json.dumps([{**{k: r[k] for k in ("id", "name", "prompt", "schedule_type", "schedule_value", "enabled", "notify")},
                        "next_run": time.strftime("%d/%m %H:%M", time.localtime(r["next_run"])) if r["next_run"] else None}
                       for r in rows], ensure_ascii=False)


@tool(
    name="delete_automation",
    description="Elimina una automatización programada. Requiere confirmación.",
    parameters={"id": {"type": "string"}, "name": {"type": "string"}},
    required=["id"], risk=Risk.SENSITIVE, category="automatización",
    summary_fn=lambda p: f"Eliminar la automatización «{p.get('name') or p.get('id')}»",
)
async def delete_automation(params: dict, ctx: ExecContext) -> str:
    return "Automatización eliminada." if await store.automation_delete(params["id"]) else "No existía."


# ------------------------------------------------------------------ notificaciones

@tool(
    name="send_notification",
    description="Envía una notificación al usuario: 'desktop' (Windows), 'telegram' (móvil) o 'all'.",
    parameters={"title": {"type": "string"}, "message": {"type": "string"},
                "channel": {"type": "string", "enum": ["all", "desktop", "telegram"]}},
    required=["message"], risk=Risk.MODERATE, category="notificaciones",
    summary_fn=lambda p: f"Notificar ({p.get('channel', 'all')}): {str(p.get('message'))[:120]}",
)
async def send_notification(params: dict, ctx: ExecContext) -> str:
    sent = await notifier.notify(params.get("title") or "J.A.R.V.I.S.", params["message"], None,
                                 params.get("channel") or "all", ctx.chat_id)
    return f"Notificación enviada: {sent}"


@tool(
    name="send_file_to_user",
    description=(
        "Entrega un archivo autorizado al usuario. Si la conversación viene de Telegram se adjunta en la respuesta; "
        "con deliver_to='telegram' se envía al móvil del usuario aunque estés en el PC."
    ),
    parameters={"path": {"type": "string"}, "deliver_to": {"type": "string", "enum": ["reply", "telegram"]},
                "caption": {"type": "string"}},
    required=["path"], risk=Risk.MODERATE, category="notificaciones",
    summary_fn=lambda p: f"Enviar archivo {p.get('path')} al usuario" + (" por Telegram" if p.get("deliver_to") == "telegram" else ""),
)
async def send_file_to_user(params: dict, ctx: ExecContext) -> ToolResult:
    p = resolve_path(params["path"], must_exist=True)
    if p.is_dir():
        return ToolResult("No se pueden enviar carpetas; comprímela primero.", is_error=True)
    if p.stat().st_size > 48 * 1024 * 1024:
        return ToolResult("El archivo supera los 48 MB (límite de Telegram para bots).", is_error=True)
    if params.get("deliver_to") == "telegram":
        if not notifier.telegram_available():
            return ToolResult("Telegram no está conectado.", is_error=True)
        await notifier.notify("Archivo de JARVIS", params.get("caption") or p.name, [str(p)], "telegram", ctx.chat_id)
        return ToolResult(f"Enviado por Telegram: {p.name}", summary=f"Enviado {p.name}")
    return ToolResult(f"Archivo adjuntado a la respuesta: {p}", files=[str(p)], summary=f"Adjunto {p.name}")
