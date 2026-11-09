"""Repositorios de memoria persistente, tareas, trabajos en segundo plano y automatizaciones."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from sqlalchemy import delete, insert, or_, select, update

from . import db
from .events import bus

MEMORY_KINDS = ["preference", "personal", "project", "fact", "note", "config"]

_STOP = set("""a al algo como con de del el ella ellos en es esa ese eso esta este esto estoy hay la las le lo los
mas me mi mis muy no nos o para pero por que se si sin sobre su sus te tu un una uno y ya yo the of and to in is
for on my it you""".split())


def _norm(text: str) -> list[str]:
    t = unicodedata.normalize("NFKD", text.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return [w for w in re.findall(r"[a-z0-9ñ]{3,}", t) if w not in _STOP]


# ------------------------------------------------------------------ memoria

async def memory_add(content: str, kind: str = "fact", tags: str = "", importance: int = 3,
                     source: str = "user") -> dict:
    mid = db.new_id("m_")
    t = db.now()
    await db.execute(insert(db.memories).values(
        id=mid, kind=kind if kind in MEMORY_KINDS else "fact", content=content.strip(), tags=tags,
        importance=max(1, min(5, importance)), source=source, created_at=t, updated_at=t))
    bus.publish("memory_changed")
    return await db.fetch_one(select(db.memories).where(db.memories.c.id == mid))


async def memory_list(kind: str | None = None) -> list[dict]:
    stmt = select(db.memories).order_by(db.memories.c.importance.desc(), db.memories.c.updated_at.desc())
    if kind:
        stmt = stmt.where(db.memories.c.kind == kind)
    return await db.fetch_all(stmt)


async def memory_update(mid: str, **values) -> dict | None:
    values = {k: v for k, v in values.items() if v is not None and k in ("content", "kind", "tags", "importance")}
    if not values:
        return await db.fetch_one(select(db.memories).where(db.memories.c.id == mid))
    values["updated_at"] = db.now()
    await db.execute(update(db.memories).where(db.memories.c.id == mid).values(**values))
    bus.publish("memory_changed")
    return await db.fetch_one(select(db.memories).where(db.memories.c.id == mid))


async def memory_delete(mid: str) -> bool:
    res = await db.execute(delete(db.memories).where(db.memories.c.id == mid))
    bus.publish("memory_changed")
    return res.rowcount > 0


async def memory_search(query: str, limit: int = 10) -> list[dict]:
    q = set(_norm(query))
    rows = await memory_list()
    scored = []
    for r in rows:
        words = set(_norm(r["content"] + " " + r["tags"] + " " + r["kind"]))
        overlap = len(q & words)
        partial = sum(1 for a in q for b in words if len(a) > 4 and (a in b or b in a)) * 0.5
        score = overlap + partial
        if score > 0 or not q:
            scored.append((score + r["importance"] * 0.15, r))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [r for _, r in scored[:limit]]


async def memory_context(user_text: str, max_items: int = 14) -> str:
    """Recuerdos para inyectar en el turno: los esenciales + los relevantes para el mensaje."""
    rows = await memory_list()
    if not rows:
        return ""
    core = [r for r in rows if r["importance"] >= 4 or r["kind"] in ("preference", "personal")][:8]
    relevant = await memory_search(user_text, limit=max_items)
    chosen, seen = [], set()
    for r in core + relevant:
        if r["id"] not in seen:
            chosen.append(r)
            seen.add(r["id"])
        if len(chosen) >= max_items:
            break
    return "\n".join(f"- [{r['kind']}] {r['content']} (id {r['id']})" for r in chosen)


# ------------------------------------------------------------------ tareas

async def task_create(title: str, description: str = "", priority: str = "normal", project: str = "",
                      due: str = "") -> dict:
    tid = db.new_id("t_")
    t = db.now()
    await db.execute(insert(db.tasks).values(
        id=tid, title=title, description=description, status="pending", priority=priority,
        project=project, due=due, created_at=t, updated_at=t))
    bus.publish("tasks_changed")
    return await task_get(tid)


async def task_get(tid: str) -> dict | None:
    return await db.fetch_one(select(db.tasks).where(db.tasks.c.id == tid))


async def task_list(status: str | None = None, project: str | None = None) -> list[dict]:
    stmt = select(db.tasks).order_by(db.tasks.c.status, db.tasks.c.created_at.desc())
    if status == "open":
        stmt = stmt.where(db.tasks.c.status.in_(["pending", "in_progress"]))
    elif status:
        stmt = stmt.where(db.tasks.c.status == status)
    if project:
        stmt = stmt.where(db.tasks.c.project == project)
    return await db.fetch_all(stmt)


async def task_update(tid: str, **values) -> dict | None:
    values = {k: v for k, v in values.items() if v is not None}
    if values.get("status") == "done":
        values["completed_at"] = db.now()
    values["updated_at"] = db.now()
    await db.execute(update(db.tasks).where(db.tasks.c.id == tid).values(**values))
    bus.publish("tasks_changed")
    return await task_get(tid)


async def task_delete(tid: str) -> bool:
    res = await db.execute(delete(db.tasks).where(db.tasks.c.id == tid))
    bus.publish("tasks_changed")
    return res.rowcount > 0


# ------------------------------------------------------------------ trabajos (jobs)

async def job_create(title: str, prompt: str, origin: str, origin_chat_id: str = "") -> dict:
    jid = db.new_id("j_")
    await db.execute(insert(db.jobs).values(
        id=jid, title=title, prompt=prompt, status="queued", origin=origin,
        origin_chat_id=origin_chat_id, plan=[], files=[], created_at=db.now()))
    job = await job_get(jid)
    bus.publish("job_update", job=job)
    return job


async def job_get(jid: str) -> dict | None:
    return await db.fetch_one(select(db.jobs).where(db.jobs.c.id == jid))


async def job_update(jid: str, **values) -> dict | None:
    await db.execute(update(db.jobs).where(db.jobs.c.id == jid).values(**values))
    job = await job_get(jid)
    bus.publish("job_update", job=job)
    return job


async def job_list(limit: int = 50, active_only: bool = False) -> list[dict]:
    stmt = select(db.jobs).order_by(db.jobs.c.created_at.desc()).limit(limit)
    if active_only:
        stmt = stmt.where(db.jobs.c.status.in_(["queued", "running"]))
    return await db.fetch_all(stmt)


# ------------------------------------------------------------------ automatizaciones

async def automation_list() -> list[dict]:
    return await db.fetch_all(select(db.automations).order_by(db.automations.c.created_at))


async def automation_get(aid: str) -> dict | None:
    return await db.fetch_one(select(db.automations).where(db.automations.c.id == aid))


async def automation_create(name: str, prompt: str, schedule_type: str, schedule_value: str,
                            notify: str = "all", next_run: float | None = None) -> dict:
    aid = db.new_id("au_")
    await db.execute(insert(db.automations).values(
        id=aid, name=name, prompt=prompt, schedule_type=schedule_type, schedule_value=schedule_value,
        enabled=True, notify=notify, next_run=next_run, created_at=db.now()))
    bus.publish("automations_changed")
    return await automation_get(aid)


async def automation_update(aid: str, **values: Any) -> dict | None:
    await db.execute(update(db.automations).where(db.automations.c.id == aid).values(**values))
    bus.publish("automations_changed")
    return await automation_get(aid)


async def automation_delete(aid: str) -> bool:
    res = await db.execute(delete(db.automations).where(db.automations.c.id == aid))
    bus.publish("automations_changed")
    return res.rowcount > 0
