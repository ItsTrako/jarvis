"""Trabajos en segundo plano y automatizaciones programadas.

Un trabajo es una ejecución completa del agente en su propia conversación, sin bloquear la
conversación principal. Al terminar se notifica al usuario (escritorio + Telegram) con el
resumen y los archivos generados.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging

from .. import db, notifier, store
from ..config import get_config
from ..events import bus
from ..security import ExecContext, kill_switch
from .core import agent

log = logging.getLogger("jarvis.jobs")


class JobManager:
    def __init__(self, max_concurrent: int = 2) -> None:
        self._sem = asyncio.Semaphore(max_concurrent)
        self._tasks: dict[str, tuple[asyncio.Task, ExecContext]] = {}

    async def start(self, title: str, prompt: str, origin: str = "ui", chat_id: int | None = None,
                    notify: str = "all") -> dict:
        job = await store.job_create(title, prompt, origin, str(chat_id or ""))
        conv = await db.create_conversation(f"⚙ {title}"[:70], source="job")
        await store.job_update(job["id"], conversation_id=conv["id"])
        ctx = ExecContext(source="job" if origin != "automation" else "automation", chat_id=chat_id,
                          job_id=job["id"], interactive=False)
        task = asyncio.create_task(self._run(job["id"], conv["id"], title, prompt, ctx, notify))
        kill_switch.track(task)
        self._tasks[job["id"]] = (task, ctx)
        return await store.job_get(job["id"])

    async def _run(self, jid: str, cid: str, title: str, prompt: str, ctx: ExecContext, notify: str) -> None:
        async with self._sem:
            await store.job_update(jid, status="running", started_at=db.now())
            instructions = (
                f"[TRABAJO EN SEGUNDO PLANO: «{title}»]\n{prompt}\n\n"
                "Trabajas de forma autónoma: el usuario no está mirando. Usa update_plan para mostrar el progreso. "
                "Si necesitas una acción que requiera confirmación, el sistema se la pedirá al usuario. Al terminar, "
                "da un resumen final claro y conciso (qué has hecho, conclusiones y rutas de archivos generados).")
            try:
                res = await agent.run(cid, instructions, ctx, interface="pc", effort=get_config().llm.background_effort)
                status = "cancelled" if res.stopped else ("failed" if res.error else "done")
                await store.job_update(jid, status=status, result=res.text[:20000], error=res.error or "",
                                       files=res.files, finished_at=db.now())
                if notify != "none":
                    head = {"done": "✅ Tarea completada", "failed": "⚠️ La tarea ha fallado",
                            "cancelled": "⏹ Tarea detenida"}[status]
                    await notifier.notify(f"{head}: {title}", res.text[:3500], res.files, notify,
                                          int(ctx.chat_id) if ctx.chat_id else None)
            except asyncio.CancelledError:
                await store.job_update(jid, status="cancelled", finished_at=db.now())
                raise
            except Exception as e:
                log.exception("Trabajo %s falló", jid)
                await store.job_update(jid, status="failed", error=str(e), finished_at=db.now())
            finally:
                self._tasks.pop(jid, None)

    async def cancel(self, jid: str) -> bool:
        entry = self._tasks.get(jid)
        if not entry:
            return False
        task, ctx = entry
        ctx.cancel_event.set()
        task.cancel()
        return True

    def ctx_for(self, jid: str) -> ExecContext | None:
        e = self._tasks.get(jid)
        return e[1] if e else None


jobs = JobManager()


# ------------------------------------------------------------------ automatizaciones

DAYS = {"lun": 0, "mon": 0, "mar": 1, "tue": 1, "mie": 2, "mié": 2, "wed": 2, "jue": 3, "thu": 3,
        "vie": 4, "fri": 4, "sab": 5, "sáb": 5, "sat": 5, "dom": 6, "sun": 6}


def compute_next_run(schedule_type: str, value: str, after: dt.datetime | None = None) -> float:
    """daily: 'HH:MM' · weekly: 'lun,mie HH:MM' · interval: minutos (>=5)."""
    now = after or dt.datetime.now()
    if schedule_type == "interval":
        minutes = max(5, int(value))
        return (now + dt.timedelta(minutes=minutes)).timestamp()
    if schedule_type == "daily":
        h, m = (int(x) for x in value.strip().split(":"))
        cand = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if cand <= now:
            cand += dt.timedelta(days=1)
        return cand.timestamp()
    if schedule_type == "weekly":
        days_part, time_part = value.strip().rsplit(" ", 1)
        days = sorted({DAYS[d.strip().lower()[:3]] for d in days_part.split(",") if d.strip()})
        h, m = (int(x) for x in time_part.split(":"))
        for add in range(0, 8):
            day = now + dt.timedelta(days=add)
            cand = day.replace(hour=h, minute=m, second=0, microsecond=0)
            if cand.weekday() in days and cand > now:
                return cand.timestamp()
    raise ValueError("Programación no válida")


def describe_schedule(schedule_type: str, value: str) -> str:
    if schedule_type == "interval":
        return f"cada {value} minutos"
    if schedule_type == "daily":
        return f"cada día a las {value}"
    return f"semanal ({value})"


class Scheduler:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            self._task = None

    async def _loop(self) -> None:
        while True:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Error en el programador")
            await asyncio.sleep(20)

    async def tick(self) -> None:
        if kill_switch.engaged:
            return
        now = db.now()
        for a in await store.automation_list():
            if not a["enabled"]:
                continue
            if a["next_run"] is None:
                await store.automation_update(a["id"], next_run=compute_next_run(a["schedule_type"], a["schedule_value"]))
                continue
            if a["next_run"] <= now:
                nxt = compute_next_run(a["schedule_type"], a["schedule_value"])
                await store.automation_update(a["id"], last_run=now, next_run=nxt, last_status="lanzada")
                await jobs.start(f"Automatización: {a['name']}", a["prompt"], origin="automation", notify=a["notify"])
                bus.publish("automation_fired", automation_id=a["id"], name=a["name"])


scheduler = Scheduler()
