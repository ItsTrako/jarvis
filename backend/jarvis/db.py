"""Persistencia (SQLAlchemy 2 async).

SQLite por defecto (``data/jarvis.db``). Cambiando ``database_url`` en config.yaml a
``postgresql+asyncpg://...`` (e instalando asyncpg) el mismo código funciona sobre PostgreSQL.
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

from sqlalchemy import (
    JSON, Boolean, Column, Float, Integer, MetaData, String, Table, Text, delete, func, insert,
    select, update,
)
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from .config import DATA_DIR, get_config

metadata = MetaData()


def now() -> float:
    return time.time()


def new_id(prefix: str = "") -> str:
    return prefix + uuid.uuid4().hex[:12]


conversations = Table(
    "conversations", metadata,
    Column("id", String(32), primary_key=True),
    Column("title", String(200), nullable=False, default="Nueva conversación"),
    Column("source", String(20), nullable=False, default="ui"),
    Column("segment", Integer, nullable=False, default=0),
    Column("archived", Boolean, nullable=False, default=False),
    Column("input_tokens", Integer, nullable=False, default=0),
    Column("created_at", Float, nullable=False),
    Column("updated_at", Float, nullable=False),
)

messages = Table(
    "messages", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("conversation_id", String(32), nullable=False, index=True),
    Column("segment", Integer, nullable=False, default=0),
    Column("role", String(12), nullable=False),
    Column("content", JSON, nullable=False),  # bloques en formato de la API
    Column("source", String(20), nullable=False, default="ui"),
    Column("created_at", Float, nullable=False),
)

memories = Table(
    "memories", metadata,
    Column("id", String(32), primary_key=True),
    Column("kind", String(20), nullable=False, default="fact"),
    Column("content", Text, nullable=False),
    Column("tags", String(300), nullable=False, default=""),
    Column("importance", Integer, nullable=False, default=3),
    Column("source", String(20), nullable=False, default="user"),
    Column("created_at", Float, nullable=False),
    Column("updated_at", Float, nullable=False),
)

tasks = Table(
    "tasks", metadata,
    Column("id", String(32), primary_key=True),
    Column("title", String(300), nullable=False),
    Column("description", Text, nullable=False, default=""),
    Column("status", String(20), nullable=False, default="pending"),
    Column("priority", String(10), nullable=False, default="normal"),
    Column("project", String(100), nullable=False, default=""),
    Column("due", String(40), nullable=False, default=""),
    Column("created_at", Float, nullable=False),
    Column("updated_at", Float, nullable=False),
    Column("completed_at", Float),
)

jobs = Table(
    "jobs", metadata,
    Column("id", String(32), primary_key=True),
    Column("title", String(300), nullable=False),
    Column("prompt", Text, nullable=False),
    Column("status", String(20), nullable=False, default="queued"),
    Column("result", Text, nullable=False, default=""),
    Column("error", Text, nullable=False, default=""),
    Column("conversation_id", String(32), nullable=False, default=""),
    Column("origin", String(20), nullable=False, default="ui"),
    Column("origin_chat_id", String(40), nullable=False, default=""),
    Column("plan", JSON, nullable=False, default=list),
    Column("files", JSON, nullable=False, default=list),
    Column("created_at", Float, nullable=False),
    Column("started_at", Float),
    Column("finished_at", Float),
)

automations = Table(
    "automations", metadata,
    Column("id", String(32), primary_key=True),
    Column("name", String(200), nullable=False),
    Column("prompt", Text, nullable=False),
    Column("schedule_type", String(20), nullable=False),  # daily | weekly | interval
    Column("schedule_value", String(60), nullable=False),
    Column("enabled", Boolean, nullable=False, default=True),
    Column("notify", String(20), nullable=False, default="all"),
    Column("last_run", Float),
    Column("next_run", Float),
    Column("last_status", String(20), nullable=False, default=""),
    Column("created_at", Float, nullable=False),
)

audit_log = Table(
    "audit_log", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("ts", Float, nullable=False, index=True),
    Column("source", String(20), nullable=False),
    Column("event", String(40), nullable=False),
    Column("tool", String(60), nullable=False, default=""),
    Column("risk", String(12), nullable=False, default=""),
    Column("decision", String(20), nullable=False, default=""),
    Column("detail", Text, nullable=False, default=""),
)

kv = Table(
    "kv", metadata,
    Column("key", String(100), primary_key=True),
    Column("value", JSON),
)

_engine: AsyncEngine | None = None


def engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        url = get_config().database_url or f"sqlite+aiosqlite:///{(DATA_DIR / 'jarvis.db').as_posix()}"
        _engine = create_async_engine(url, future=True)
    return _engine


async def init_db() -> None:
    async with engine().begin() as conn:
        await conn.run_sync(metadata.create_all)
        if engine().dialect.name == "sqlite":
            await conn.exec_driver_sql("PRAGMA journal_mode=WAL")


async def close_db() -> None:
    if _engine is not None:
        await _engine.dispose()


def _row(r) -> dict[str, Any]:
    return dict(r._mapping) if r is not None else None


async def fetch_all(stmt) -> list[dict[str, Any]]:
    async with engine().connect() as conn:
        res = await conn.execute(stmt)
        return [dict(r._mapping) for r in res]


async def fetch_one(stmt) -> dict[str, Any] | None:
    async with engine().connect() as conn:
        res = await conn.execute(stmt)
        return _row(res.first())


async def execute(stmt) -> Any:
    async with engine().begin() as conn:
        return await conn.execute(stmt)


# ------------------------------------------------------------------ conversaciones

async def create_conversation(title: str = "Nueva conversación", source: str = "ui") -> dict:
    cid = new_id("c_")
    t = now()
    await execute(insert(conversations).values(
        id=cid, title=title, source=source, segment=0, archived=False, input_tokens=0,
        created_at=t, updated_at=t))
    return await get_conversation(cid)


async def get_conversation(cid: str) -> dict | None:
    return await fetch_one(select(conversations).where(conversations.c.id == cid))


async def list_conversations(limit: int = 100, include_archived: bool = False) -> list[dict]:
    stmt = select(conversations).order_by(conversations.c.updated_at.desc()).limit(limit)
    if not include_archived:
        stmt = stmt.where(conversations.c.archived == False)  # noqa: E712
    return await fetch_all(stmt)


async def update_conversation(cid: str, **values) -> None:
    values.setdefault("updated_at", now())
    await execute(update(conversations).where(conversations.c.id == cid).values(**values))


async def delete_conversation(cid: str) -> None:
    await execute(delete(messages).where(messages.c.conversation_id == cid))
    await execute(delete(conversations).where(conversations.c.id == cid))


async def add_message(cid: str, segment: int, role: str, content: Any, source: str = "ui") -> int:
    res = await execute(insert(messages).values(
        conversation_id=cid, segment=segment, role=role, content=content, source=source,
        created_at=now()))
    await update_conversation(cid)
    return res.inserted_primary_key[0]


async def get_messages(cid: str, segment: int | None = None) -> list[dict]:
    stmt = select(messages).where(messages.c.conversation_id == cid).order_by(messages.c.id)
    if segment is not None:
        stmt = stmt.where(messages.c.segment == segment)
    return await fetch_all(stmt)


# ------------------------------------------------------------------ kv

async def kv_get(key: str, default: Any = None) -> Any:
    row = await fetch_one(select(kv).where(kv.c.key == key))
    return row["value"] if row else default


async def kv_set(key: str, value: Any) -> None:
    async with engine().begin() as conn:
        res = await conn.execute(update(kv).where(kv.c.key == key).values(value=value))
        if res.rowcount == 0:
            await conn.execute(insert(kv).values(key=key, value=value))


# ------------------------------------------------------------------ auditoría

async def audit(source: str, event: str, tool: str = "", risk: str = "", decision: str = "",
                detail: Any = "") -> None:
    if not isinstance(detail, str):
        detail = json.dumps(detail, ensure_ascii=False, default=str)
    try:
        await execute(insert(audit_log).values(
            ts=now(), source=source, event=event, tool=tool, risk=risk, decision=decision,
            detail=detail[:4000]))
    except Exception:  # el registro nunca debe romper la acción, pero sí dejar rastro en el log
        import logging

        logging.getLogger("jarvis.audit").exception("No se pudo registrar en auditoría: %s %s", event, tool)


async def recent_audit(limit: int = 200) -> list[dict]:
    return await fetch_all(select(audit_log).order_by(audit_log.c.id.desc()).limit(limit))


async def count(table: Table, *where) -> int:
    stmt = select(func.count()).select_from(table)
    for w in where:
        stmt = stmt.where(w)
    async with engine().connect() as conn:
        return (await conn.execute(stmt)).scalar_one()
