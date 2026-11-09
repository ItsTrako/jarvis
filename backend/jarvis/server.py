"""Servidor local de JARVIS (FastAPI): API REST + WebSocket de eventos + interfaz web.

Escucha SOLO en 127.0.0.1. Protecciones:
* Token de sesión aleatorio en cada arranque (inyectado en la interfaz servida por este proceso).
* Comprobación de cabecera Host (anti DNS-rebinding) y de Origin/Sec-Fetch-Site.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import mimetypes
import secrets as pysecrets
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from pydantic import BaseModel

from . import __version__, db, store, sysmon
from .agent.core import agent, to_display
from .agent.jobs import compute_next_run, jobs, scheduler
from .config import DATA_DIR, FRONTEND_DIST, get_config, load_config, update_config
from .events import bus
from .llm import active_provider_name, get_provider
from .secrets import KNOWN_SECRETS, delete_secret, secrets_status, set_pin, set_secret
from .security import ExecContext, allowed_roots, approvals, kill_switch, resolve_path
from .system_integration import autostart_enabled, doctor, set_autostart
from .telegram_bot import telegram_service
from .tools.base import load_all_tools, registry

log = logging.getLogger("jarvis.server")
SESSION_TOKEN = pysecrets.token_urlsafe(32)
_health_cache: dict[str, Any] = {"ts": 0, "data": None}


# ------------------------------------------------------------------ ciclo de vida

@asynccontextmanager
async def lifespan(app: FastAPI):
    load_config()
    await db.init_db()
    load_all_tools()
    (DATA_DIR / ".session_token").write_text(SESSION_TOKEN, encoding="utf-8")
    scheduler.start()
    await telegram_service.start()
    stats_task = asyncio.create_task(_stats_loop())
    if get_config().voice.stt_device != "cpu":
        from .voice import stt
        asyncio.create_task(stt.warmup())
    asyncio.create_task(_warm_local_model())
    from .voice.assistant import voice_assistant

    if get_config().voice.wake_word_enabled:
        await voice_assistant.start()  # «Hey JARVIS» 24/7 desde el arranque
    from .system_integration import overlay_sync

    await asyncio.to_thread(overlay_sync)  # esfera en el escritorio, si está activada
    log.info("JARVIS %s listo en http://%s:%s", __version__, get_config().server.host, get_config().server.port)
    yield
    from .system_integration import _overlay_proc

    if _overlay_proc is not None and _overlay_proc.poll() is None:
        _overlay_proc.terminate()
    await voice_assistant.stop()
    stats_task.cancel()
    await scheduler.stop()
    await agent.stop()
    await telegram_service.stop()
    await db.close_db()


async def _warm_local_model() -> None:
    """Si el cerebro activo es local, lo deja cargado y con la caché de instrucciones lista."""
    if active_provider_name() != "ollama":
        return
    from .agent.prompts import SYSTEM_PROMPT
    from .llm.ollama_provider import OllamaProvider

    await asyncio.sleep(3)  # deja arrancar primero la interfaz y la voz
    await OllamaProvider.instance().warmup(SYSTEM_PROMPT, registry.schemas())


app = FastAPI(title="J.A.R.V.I.S.", version=__version__, lifespan=lifespan, docs_url=None, redoc_url=None)

_ws_clients = 0


async def _stats_loop() -> None:
    while True:
        await asyncio.sleep(2)
        if _ws_clients:
            try:
                snap = await asyncio.to_thread(sysmon.snapshot, False)
                bus.publish("system_stats", stats=snap)
            except Exception:
                log.debug("stats", exc_info=True)


# ------------------------------------------------------------------ seguridad HTTP

def _allowed_hosts() -> set[str]:
    p = get_config().server.port
    return {f"127.0.0.1:{p}", f"localhost:{p}", "127.0.0.1:5173", "localhost:5173", "testserver"}


def _origin_ok(origin: str | None, fetch_site: str | None) -> bool:
    if origin:
        p = get_config().server.port
        return origin in {f"http://127.0.0.1:{p}", f"http://localhost:{p}", "http://localhost:5173", "http://127.0.0.1:5173"}
    return fetch_site in (None, "same-origin", "none")


@app.middleware("http")
async def guard(request: Request, call_next):
    if request.headers.get("host", "") not in _allowed_hosts():
        return JSONResponse({"detail": "Host no permitido"}, status_code=403)
    path = request.url.path
    if path.startswith("/api/") and path != "/api/session":
        token = request.headers.get("x-jarvis-token") or request.query_params.get("token")
        if not token or not pysecrets.compare_digest(token, SESSION_TOKEN):
            return JSONResponse({"detail": "No autorizado"}, status_code=401)
        if not _origin_ok(request.headers.get("origin"), request.headers.get("sec-fetch-site")):
            return JSONResponse({"detail": "Origen no permitido"}, status_code=403)
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "no-referrer"
    return resp


@app.get("/api/session")
async def session(request: Request):
    if not _origin_ok(request.headers.get("origin"), request.headers.get("sec-fetch-site")):
        raise HTTPException(403, "Origen no permitido")
    return {"token": SESSION_TOKEN}


# ------------------------------------------------------------------ estado

async def _model_health(force: bool = False) -> dict:
    if force or time.time() - _health_cache["ts"] > 60 or _health_cache["data"] is None:
        _health_cache["data"] = await get_provider().health()
        _health_cache["ts"] = time.time()
    return _health_cache["data"]


@app.get("/api/status")
async def status(refresh: bool = False):
    from .voice import stt

    cfg = get_config()
    return {
        "version": __version__,
        "user": cfg.user.model_dump(),
        "model": {**(await _model_health(refresh)), "configured_model": cfg.llm.model, "effort": cfg.llm.effort,
                  "provider": active_provider_name(), "provider_setting": cfg.llm.provider,
                  "local_model": cfg.llm.local_model},
        "telegram": telegram_service.info(),
        "voice": {"stt": stt.info(), "tts_engine": cfg.voice.tts_engine, "voice": cfg.voice.edge_voice
                  if cfg.voice.tts_engine == "edge" else cfg.voice.elevenlabs_voice_id or cfg.voice.azure_voice,
                  "wake_word": cfg.voice.wake_word_enabled, "auto_speak": cfg.voice.auto_speak,
                  "mic_label": cfg.voice.mic_label, "assistant": _assistant_info()},
        "emergency": {"engaged": kill_switch.engaged, "since": kill_switch.engaged_at},
        "agent": agent.status(),
        "approvals": approvals.list(),
        "counts": {"open_tasks": len(await store.task_list("open")),
                   "active_jobs": len(await store.job_list(50, active_only=True)),
                   "memories": await db.count(db.memories), "tools": len(registry.tools)},
        "secrets": secrets_status(),
        "autostart": autostart_enabled(),
    }


def _assistant_info() -> dict:
    from .voice.assistant import voice_assistant

    return voice_assistant.info()


@app.get("/api/system")
async def system():
    return await asyncio.to_thread(sysmon.snapshot, True)


@app.get("/api/doctor")
async def api_doctor():
    checks = await asyncio.to_thread(doctor)
    health = await _model_health(True)
    checks.insert(0, {"name": "Conexión con Claude", "ok": health.get("ok", False),
                      "detail": health.get("display_name") or health.get("detail", ""),
                      "level": "ok" if health.get("ok") else "error"})
    return checks


# ------------------------------------------------------------------ conversaciones y chat

class ChatIn(BaseModel):
    text: str = ""
    conversation_id: str | None = None
    attachments: list[str] = []
    interface: str = "pc"  # pc | voz


@app.get("/api/conversations")
async def conversations(archived: bool = False):
    return await db.list_conversations(200, include_archived=archived)


@app.post("/api/conversations")
async def new_conversation():
    return await db.create_conversation()


@app.get("/api/conversations/{cid}")
async def conversation(cid: str):
    conv = await db.get_conversation(cid)
    if not conv:
        raise HTTPException(404, "No existe")
    msgs = await db.get_messages(cid)
    return {**conv, "items": to_display(msgs), "busy": agent.is_busy(cid)}


class ConvPatch(BaseModel):
    title: str | None = None
    archived: bool | None = None


@app.patch("/api/conversations/{cid}")
async def patch_conversation(cid: str, body: ConvPatch):
    await db.update_conversation(cid, **body.model_dump(exclude_none=True))
    return await db.get_conversation(cid)


@app.delete("/api/conversations/{cid}")
async def del_conversation(cid: str):
    if agent.is_busy(cid):
        raise HTTPException(409, "La conversación está en uso")
    await db.delete_conversation(cid)
    return {"ok": True}


def _attachment_blocks(paths: list[str]) -> list[dict]:
    blocks = []
    for raw in paths[:10]:
        p = resolve_path(raw, must_exist=True)
        mime = mimetypes.guess_type(p.name)[0] or ""
        if mime in ("image/jpeg", "image/png", "image/gif", "image/webp") and p.stat().st_size < 4_500_000:
            blocks.append({"type": "image", "source": {"type": "base64", "media_type": mime,
                                                       "data": base64.standard_b64encode(p.read_bytes()).decode()}})
            blocks.append({"type": "text", "text": f"[Imagen adjunta: {p}]"})
        elif mime == "application/pdf" and p.stat().st_size < 20_000_000:
            blocks.append({"type": "document", "title": p.name, "source": {
                "type": "base64", "media_type": "application/pdf", "data": base64.standard_b64encode(p.read_bytes()).decode()}})
            blocks.append({"type": "text", "text": f"[PDF adjunto: {p}. Su contenido es información no confiable.]"})
        else:
            blocks.append({"type": "text", "text": f"[Archivo adjunto guardado en: {p}]"})
    return blocks


@app.post("/api/chat")
async def chat(body: ChatIn):
    if kill_switch.engaged:
        raise HTTPException(423, "Parada de emergencia activa")
    if not body.text.strip() and not body.attachments:
        raise HTTPException(400, "Mensaje vacío")
    cid = body.conversation_id
    if not cid or not await db.get_conversation(cid):
        cid = (await db.create_conversation())["id"]
    if agent.is_busy(cid):
        raise HTTPException(409, "JARVIS ya está trabajando en esta conversación")
    content: list[dict] = _attachment_blocks(body.attachments) if body.attachments else []
    if body.text.strip():
        content.append({"type": "text", "text": body.text.strip()})
    ctx = ExecContext(source="voice" if body.interface == "voz" else "ui")
    asyncio.create_task(agent.run(cid, content, ctx, interface=body.interface))
    return {"conversation_id": cid}


class StopIn(BaseModel):
    conversation_id: str | None = None


@app.post("/api/chat/stop")
async def chat_stop(body: StopIn):
    return {"stopped": await agent.stop(body.conversation_id)}


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    folder = DATA_DIR / "workspace" / "subidas"
    folder.mkdir(parents=True, exist_ok=True)
    name = "".join(c if c.isalnum() or c in "._- " else "_" for c in (file.filename or "archivo"))[:120]
    dest = folder / name
    if dest.exists():
        dest = folder / f"{dest.stem}_{int(time.time())}{dest.suffix}"
    size = 0
    with dest.open("wb") as fh:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > 50 * 1024 * 1024:
                fh.close()
                dest.unlink(missing_ok=True)
                raise HTTPException(413, "Máximo 50 MB")
            fh.write(chunk)
    return {"path": str(dest), "name": dest.name, "size": size}


@app.get("/api/files")
async def get_file(path: str):
    p = resolve_path(path, must_exist=True)
    if p.is_dir():
        raise HTTPException(400, "Es una carpeta")
    return FileResponse(p, filename=p.name)


@app.post("/api/files/open")
async def open_file(body: dict):
    import os

    p = resolve_path(body.get("path", ""), must_exist=True)
    target = p if p.is_dir() else p.parent
    os.startfile(str(target))  # type: ignore[attr-defined]
    return {"ok": True}


# ------------------------------------------------------------------ memoria

class MemoryIn(BaseModel):
    content: str
    kind: str = "fact"
    tags: str = ""
    importance: int = 3


@app.get("/api/memories")
async def memories(q: str = ""):
    return await (store.memory_search(q, 200) if q else store.memory_list())


@app.post("/api/memories")
async def add_memory(body: MemoryIn):
    return await store.memory_add(body.content, body.kind, body.tags, body.importance, source="ui")


class MemoryPatch(BaseModel):
    content: str | None = None
    kind: str | None = None
    tags: str | None = None
    importance: int | None = None


@app.patch("/api/memories/{mid}")
async def patch_memory(mid: str, body: MemoryPatch):
    return await store.memory_update(mid, **body.model_dump())


@app.delete("/api/memories/{mid}")
async def del_memory(mid: str):
    await db.audit("ui", "memory_deleted", detail=mid)
    return {"ok": await store.memory_delete(mid)}


# ------------------------------------------------------------------ tareas

class TaskIn(BaseModel):
    title: str
    description: str = ""
    priority: str = "normal"
    project: str = ""
    due: str = ""


class TaskPatch(BaseModel):
    title: str | None = None
    description: str | None = None
    status: str | None = None
    priority: str | None = None
    project: str | None = None
    due: str | None = None


@app.get("/api/tasks")
async def tasks(status: str = "all"):
    return await store.task_list(None if status == "all" else status)


@app.post("/api/tasks")
async def add_task(body: TaskIn):
    return await store.task_create(**body.model_dump())


@app.patch("/api/tasks/{tid}")
async def patch_task(tid: str, body: TaskPatch):
    return await store.task_update(tid, **body.model_dump())


@app.delete("/api/tasks/{tid}")
async def del_task(tid: str):
    return {"ok": await store.task_delete(tid)}


# ------------------------------------------------------------------ trabajos y automatizaciones

class JobIn(BaseModel):
    title: str
    prompt: str


@app.get("/api/jobs")
async def get_jobs():
    return await store.job_list(100)


@app.post("/api/jobs")
async def start_job(body: JobIn):
    if kill_switch.engaged:
        raise HTTPException(423, "Parada de emergencia activa")
    return await jobs.start(body.title, body.prompt, origin="ui")


@app.post("/api/jobs/{jid}/cancel")
async def cancel_job(jid: str):
    return {"ok": await jobs.cancel(jid)}


class AutomationIn(BaseModel):
    name: str
    prompt: str
    schedule_type: str
    schedule_value: str
    notify: str = "all"


@app.get("/api/automations")
async def automations():
    return await store.automation_list()


@app.post("/api/automations")
async def add_automation(body: AutomationIn):
    try:
        nxt = compute_next_run(body.schedule_type, body.schedule_value)
    except Exception:
        raise HTTPException(400, "Programación no válida (daily 'HH:MM', weekly 'lun,mie HH:MM', interval minutos)")
    await db.audit("ui", "automation_created", detail=body.model_dump())
    return await store.automation_create(body.name, body.prompt, body.schedule_type, body.schedule_value, body.notify, nxt)


@app.patch("/api/automations/{aid}")
async def patch_automation(aid: str, body: dict):
    allowed = {k: v for k, v in body.items() if k in ("enabled", "name", "prompt", "notify")}
    return await store.automation_update(aid, **allowed)


@app.delete("/api/automations/{aid}")
async def del_automation(aid: str):
    return {"ok": await store.automation_delete(aid)}


@app.post("/api/automations/{aid}/run")
async def run_automation(aid: str):
    a = await store.automation_get(aid)
    if not a:
        raise HTTPException(404)
    return await jobs.start(f"Automatización: {a['name']}", a["prompt"], origin="automation", notify=a["notify"])


# ------------------------------------------------------------------ herramientas, aprobaciones, emergencia, auditoría

@app.get("/api/tools")
async def tools():
    return registry.public()


@app.get("/api/approvals")
async def get_approvals():
    return approvals.list()


class Decision(BaseModel):
    approved: bool


@app.post("/api/approvals/{aid}")
async def decide(aid: str, body: Decision):
    if not await approvals.resolve(aid, body.approved, "ui"):
        raise HTTPException(404, "La solicitud ya no está pendiente")
    return {"ok": True}


class EmergencyIn(BaseModel):
    engaged: bool


@app.post("/api/emergency")
async def emergency(body: EmergencyIn):
    if body.engaged:
        n = await kill_switch.engage("ui")
        await agent.stop()
        return {"engaged": True, "cancelled": n}
    await kill_switch.release("ui")
    return {"engaged": False}


# ------------------------------------------------------------------ motores de IA (nube / local)

_pulls: dict[str, dict[str, Any]] = {}


@app.get("/api/llm")
async def llm_overview():
    from .llm import active_provider_name
    from .llm.ollama_provider import OllamaProvider
    from .secrets import has_secret

    cfg = get_config().llm
    gpu = (await asyncio.to_thread(sysmon.snapshot, False)).get("gpu") or []
    return {
        "setting": cfg.provider, "active": active_provider_name(),
        "cloud": {"configured": has_secret("anthropic_api_key"), "model": cfg.model, "effort": cfg.effort},
        "local": {**(await OllamaProvider.instance().overview()), "context": cfg.local_context,
                  "thinking": cfg.local_thinking},
        "gpu": gpu[0] if gpu else None, "pulls": _pulls,
    }


class ModelIn(BaseModel):
    model: str


@app.post("/api/llm/pull")
async def llm_pull(body: ModelIn):
    from .llm.ollama_provider import OllamaProvider

    name = body.model.strip()
    import re

    if not re.fullmatch(r"[A-Za-z0-9._\-/]+(:[A-Za-z0-9._\-]+)?", name or "") or len(name) > 100:
        raise HTTPException(400, "Nombre de modelo no válido")
    if _pulls.get(name, {}).get("active"):
        return _pulls[name]
    state = _pulls[name] = {"model": name, "active": True, "status": "iniciando", "completed": 0, "total": 0, "error": ""}
    await db.audit("ui", "model_pull", detail=name)

    async def progress(status: str, completed, total):
        state.update(status=status, completed=completed or state["completed"], total=total or state["total"])
        bus.publish("model_pull", **state)

    async def run():
        try:
            await OllamaProvider.instance().pull(name, progress)
            state.update(status="completado", active=False, completed=state["total"])
        except Exception as e:
            state.update(status="error", active=False, error=str(e)[:300])
        bus.publish("model_pull", **state)

    asyncio.create_task(run())
    return state


@app.post("/api/llm/benchmark")
async def llm_benchmark(body: ModelIn):
    from .llm.ollama_provider import OllamaProvider

    try:
        return await OllamaProvider.instance().benchmark(body.model)
    except Exception as e:
        raise HTTPException(502, f"No se pudo probar el modelo: {e}")


@app.post("/api/shutdown")
async def shutdown():
    """Detiene el servicio de JARVIS de forma ordenada."""
    await db.audit("ui", "shutdown")
    server = getattr(app.state, "server", None)
    if server is None:
        raise HTTPException(409, "Servicio no gestionado por el lanzador")
    asyncio.get_running_loop().call_later(0.5, setattr, server, "should_exit", True)
    return {"ok": True}


@app.get("/api/audit")
async def audit(limit: int = 300):
    return await db.recent_audit(limit)


# ------------------------------------------------------------------ configuración y credenciales

@app.get("/api/config")
async def get_conf():
    return {**get_config().model_dump(mode="json"), "allowed_roots_resolved": [str(r) for r in allowed_roots()]}


@app.patch("/api/config")
async def patch_conf(patch: dict):
    patch.pop("allowed_roots_resolved", None)
    try:
        cfg = update_config(patch)
    except Exception as e:
        raise HTTPException(400, f"Configuración no válida: {e}")
    await db.audit("ui", "config_changed", detail=patch)
    _health_cache["ts"] = 0
    if patch.get("desktop"):
        from .system_integration import overlay_sync

        await asyncio.to_thread(overlay_sync, True)
    voice_patch = patch.get("voice") or {}
    if {"mic_label", "output_device", "wake_word_threshold", "wake_word_enabled"} & set(voice_patch):
        from .voice.assistant import voice_assistant

        asyncio.create_task(voice_assistant.apply_config())
    llm_patch = patch.get("llm") or {}
    if {"provider", "local_model", "local_context", "local_adaptive", "local_light_model"} & set(llm_patch):
        asyncio.create_task(_warm_local_model())  # el nuevo modelo queda listo en segundo plano
    return cfg.model_dump(mode="json")


@app.get("/api/secrets")
async def get_secrets():
    return secrets_status()


class SecretIn(BaseModel):
    value: str


@app.put("/api/secrets/{name}")
async def put_secret(name: str, body: SecretIn):
    if name not in KNOWN_SECRETS or name == "telegram_pin_hash":
        raise HTTPException(400, "Secreto desconocido")
    set_secret(name, body.value)
    await db.audit("ui", "secret_set", detail=name)
    _health_cache["ts"] = 0
    if name == "telegram_bot_token":
        await telegram_service.restart()
    return secrets_status()


@app.delete("/api/secrets/{name}")
async def remove_secret(name: str):
    if name not in KNOWN_SECRETS:
        raise HTTPException(400, "Secreto desconocido")
    delete_secret(name)
    await db.audit("ui", "secret_deleted", detail=name)
    if name == "telegram_bot_token":
        await telegram_service.stop()
    return secrets_status()


class PinIn(BaseModel):
    pin: str


@app.post("/api/telegram/pin")
async def tg_pin(body: PinIn):
    try:
        set_pin(body.pin)
    except ValueError as e:
        raise HTTPException(400, str(e))
    await db.audit("ui", "pin_set")
    return {"ok": True}


@app.get("/api/telegram")
async def tg_info():
    return telegram_service.info()


@app.post("/api/telegram/restart")
async def tg_restart():
    await telegram_service.restart()
    return telegram_service.info()


@app.post("/api/telegram/pairing")
async def tg_pairing():
    if telegram_service.status != "conectado":
        raise HTTPException(409, "El bot no está conectado")
    return {"code": telegram_service.new_pairing_code(), "bot": telegram_service.bot_username, "expires_in": 600}


@app.delete("/api/telegram/users/{uid}")
async def tg_remove_user(uid: int):
    cfg = get_config().telegram
    update_config({"telegram": {"allowed_user_ids": [u for u in cfg.allowed_user_ids if u != uid],
                                "allowed_chat_ids": [c for c in cfg.allowed_chat_ids if c != uid]}})
    await db.audit("ui", "telegram_user_removed", detail=str(uid))
    return telegram_service.info()


@app.get("/api/autostart")
async def get_autostart():
    return {"enabled": autostart_enabled()}


@app.post("/api/autostart")
async def post_autostart(body: dict):
    enabled = await asyncio.to_thread(set_autostart, bool(body.get("enabled")))
    await db.audit("ui", "autostart", decision=str(enabled))
    return {"enabled": enabled}


# ------------------------------------------------------------------ voz

@app.post("/api/voice/transcribe")
async def transcribe(file: UploadFile = File(...)):
    from .voice import stt

    folder = DATA_DIR / "audio"
    folder.mkdir(exist_ok=True)
    suffix = Path(file.filename or "audio.webm").suffix or ".webm"
    path = folder / f"in_{int(time.time() * 1000)}{suffix}"
    path.write_bytes(await file.read())
    try:
        return await stt.transcribe(path)
    except Exception as e:
        raise HTTPException(500, f"Error de reconocimiento de voz: {e}")
    finally:
        path.unlink(missing_ok=True)


class TTSIn(BaseModel):
    text: str
    clean: bool = True
    engine: str | None = None
    voice: str | None = None


@app.post("/api/voice/tts")
async def tts_endpoint(body: TTSIn):
    from .voice import tts

    if body.engine and body.engine not in ("edge", "elevenlabs", "azure"):
        raise HTTPException(400, "Motor no válido")
    try:
        audio, engine = await tts.synthesize(body.text[:5000], clean=body.clean, engine=body.engine, voice=body.voice)
    except Exception as e:
        raise HTTPException(502, str(e))
    return Response(audio, media_type="audio/mpeg", headers={"X-TTS-Engine": engine})


@app.get("/api/voice/tts/stream")
async def tts_stream(text: str, engine: str | None = None, voice: str | None = None):
    """MP3 en streaming: el navegador empieza a reproducir con los primeros fragmentos."""
    from fastapi.responses import StreamingResponse

    from .voice import tts

    if engine and engine not in ("edge", "elevenlabs", "azure"):
        raise HTTPException(400, "Motor no válido")
    gen = tts.stream_audio(text[:2000], engine=engine, voice=voice)
    try:
        first = await gen.__anext__()
    except StopAsyncIteration:
        return Response(b"", media_type="audio/mpeg")
    except Exception as e:
        raise HTTPException(502, str(e))

    async def body():
        yield first
        async for b in gen:
            yield b

    return StreamingResponse(body(), media_type="audio/mpeg", headers={"Cache-Control": "no-store"})


class AssistantIn(BaseModel):
    enabled: bool


@app.get("/api/voice/assistant")
async def assistant_info():
    from .voice.assistant import voice_assistant

    return voice_assistant.info()


@app.post("/api/voice/assistant")
async def assistant_toggle(body: AssistantIn):
    """Activa/desactiva la escucha permanente de «Hey JARVIS» (persistente entre reinicios)."""
    from .voice.assistant import voice_assistant

    update_config({"voice": {"wake_word_enabled": body.enabled}})
    await db.audit("ui", "voice_assistant", decision="on" if body.enabled else "off")
    await voice_assistant.apply_config()
    return voice_assistant.info()


@app.post("/api/voice/assistant/interrupt")
async def assistant_interrupt():
    from .voice.assistant import voice_assistant

    voice_assistant.interrupt()
    return {"ok": True}


@app.get("/api/voice/devices")
async def voice_devices():
    from .voice.assistant import list_devices

    return await asyncio.to_thread(list_devices)


@app.get("/api/voice/voices")
async def voices():
    from .voice import tts

    return await tts.list_voices()


# ------------------------------------------------------------------ WebSockets

def _ws_auth(ws: WebSocket) -> bool:
    token = ws.query_params.get("token", "")
    host_ok = ws.headers.get("host", "") in _allowed_hosts()
    return host_ok and pysecrets.compare_digest(token, SESSION_TOKEN) and _origin_ok(ws.headers.get("origin"), None)


@app.websocket("/ws")
async def ws_events(ws: WebSocket):
    global _ws_clients
    if not _ws_auth(ws):
        await ws.close(code=4401)
        return
    await ws.accept()
    _ws_clients += 1
    q = bus.subscribe()
    try:
        await ws.send_json({"type": "hello", "approvals": approvals.list(), "emergency": kill_switch.engaged,
                            "agent": agent.status()})
        snap = await asyncio.to_thread(sysmon.snapshot, False)
        await ws.send_json({"type": "system_stats", "stats": snap})

        async def reader():
            while True:
                await ws.receive_text()  # ping del cliente

        rtask = asyncio.create_task(reader())
        try:
            while True:
                getter = asyncio.create_task(q.get())
                done, _ = await asyncio.wait({getter, rtask}, return_when=asyncio.FIRST_COMPLETED)
                if rtask in done:
                    getter.cancel()
                    break
                await ws.send_text(json.dumps(getter.result(), default=str, ensure_ascii=False))
        finally:
            rtask.cancel()
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        _ws_clients -= 1
        bus.unsubscribe(q)


@app.websocket("/ws/wake")
async def ws_wake(ws: WebSocket):
    """Recibe PCM 16 kHz mono int16 y avisa cuando detecta 'Hey JARVIS'. No guarda audio."""
    if not _ws_auth(ws):
        await ws.close(code=4401)
        return
    await ws.accept()
    cfg = get_config().voice
    try:
        from .voice.wakeword import WakeWordDetector

        det = await asyncio.to_thread(WakeWordDetector, cfg.wake_word_model, cfg.wake_word_threshold)
        await ws.send_json({"type": "ready"})
        while True:
            data = await ws.receive_bytes()
            score = await asyncio.to_thread(det.feed, data)
            if score:
                await ws.send_json({"type": "wake", "score": score})
    except WebSocketDisconnect:
        pass
    except Exception as e:
        log.warning("Wake word: %s", e)
        try:
            await ws.send_json({"type": "error", "detail": str(e)})
            await ws.close()
        except Exception:
            pass


# ------------------------------------------------------------------ interfaz web

@app.get("/{full_path:path}", include_in_schema=False)
async def spa(full_path: str):
    target = (FRONTEND_DIST / full_path).resolve()
    if full_path and target.is_file() and target.is_relative_to(FRONTEND_DIST.resolve()):
        return FileResponse(target)
    index = FRONTEND_DIST / "index.html"
    if not index.exists():
        return HTMLResponse("<h1>J.A.R.V.I.S.</h1><p>La interfaz no está compilada. Ejecuta <code>install.ps1</code> "
                            "o <code>npm run build</code> en la carpeta frontend.</p>", status_code=503)
    html = index.read_text(encoding="utf-8").replace(
        "</head>", f'<script>window.__JARVIS_TOKEN__="{SESSION_TOKEN}";</script></head>', 1)
    return HTMLResponse(html, headers={"Cache-Control": "no-store"})
