"""Interfaz de Telegram: TELÉFONO → TELEGRAM → JARVIS → PC → RESPUESTA.

Seguridad:
* Long polling saliente (HTTPS a api.telegram.org): no se abre NINGÚN puerto en el PC.
* Token en el Administrador de credenciales de Windows.
* Lista blanca de user_id y chat_id; emparejamiento con código de un solo uso mostrado
  únicamente en la interfaz local del PC.
* Límite de peticiones por usuario y registro de toda la actividad.
* Las acciones peligrosas requieren aprobación con botón + PIN. Telegram es solo otra
  interfaz: usa el mismo agente, las mismas herramientas y las mismas confirmaciones.
"""

from __future__ import annotations

import asyncio
import base64
import html
import logging
import re
import secrets as pysecrets
import time
from pathlib import Path
from typing import Any

from telegram import (
    BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, InputFile, Update,
)
from telegram.constants import ChatAction, ChatType, ParseMode
from telegram.error import TelegramError
from telegram.ext import (
    Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters,
)

from . import db, notifier, store
from .config import DATA_DIR, get_config, update_config
from .events import bus
from .secrets import get_secret, verify_pin
from .security import ExecContext, approvals, kill_switch, rate_limiter

log = logging.getLogger("jarvis.telegram")

MAX_LEN = 3900


def md_to_html(text: str) -> str:
    """Markdown básico → HTML de Telegram (seguro: todo se escapa antes)."""
    blocks: list[str] = []

    def keep(m):
        blocks.append(f"<pre>{html.escape(m.group(2))}</pre>")
        return f"\x00{len(blocks) - 1}\x00"

    t = re.sub(r"```(\w+)?\n?(.*?)```", keep, text, flags=re.S)
    t = html.escape(t)
    t = re.sub(r"`([^`\n]+)`", r"<code>\1</code>", t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<i>\1</i>", t)
    t = re.sub(r"(?<!\w)_(?!\s)(.+?)(?<!\s)_(?!\w)", r"<i>\1</i>", t)
    t = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2">\1</a>', t)
    t = re.sub(r"^#{1,6}\s*(.+)$", r"<b>\1</b>", t, flags=re.M)
    t = re.sub(r"^\s*[-*]\s+", "• ", t, flags=re.M)
    t = re.sub(r"\x00(\d+)\x00", lambda m: blocks[int(m.group(1))], t)
    return t


def split_message(text: str, limit: int = MAX_LEN) -> list[str]:
    parts, buf = [], ""
    for para in text.split("\n"):
        if len(buf) + len(para) + 1 > limit:
            if buf:
                parts.append(buf)
            while len(para) > limit:
                parts.append(para[:limit])
                para = para[limit:]
            buf = para
        else:
            buf = f"{buf}\n{para}" if buf else para
    if buf:
        parts.append(buf)
    return parts or [""]


class TelegramService:
    def __init__(self) -> None:
        self.app: Application | None = None
        self.status: str = "detenido"
        self.error: str = ""
        self.bot_username: str = ""
        self.pairing_code: str = ""
        self.pairing_expires: float = 0
        self._pin_wait: dict[int, tuple[str, int]] = {}  # user_id -> (approval_id, intentos)
        self._approval_msgs: dict[str, list[tuple[int, int]]] = {}
        self._bus_task: asyncio.Task | None = None
        self._runs: dict[int, asyncio.Task] = {}
        self.last_activity: float | None = None

    # ------------------------------------------------------------------ ciclo de vida

    async def start(self) -> None:
        cfg = get_config().telegram
        token = get_secret("telegram_bot_token")
        if not cfg.enabled:
            self.status = "desactivado"
            return
        if not token:
            self.status = "sin_token"
            return
        try:
            self.app = Application.builder().token(token).concurrent_updates(True).build()
            a = self.app
            for cmd, fn in [("start", self.cmd_start), ("help", self.cmd_help), ("ayuda", self.cmd_help),
                            ("status", self.cmd_status), ("estado", self.cmd_status), ("stop", self.cmd_stop),
                            ("new", self.cmd_new), ("nueva", self.cmd_new), ("tasks", self.cmd_tasks),
                            ("tareas", self.cmd_tasks), ("jobs", self.cmd_jobs), ("memory", self.cmd_memory),
                            ("emergency", self.cmd_emergency), ("resume", self.cmd_resume),
                            ("pair", self.cmd_pair), ("brief", self.cmd_brief), ("detailed", self.cmd_detailed),
                            ("voice", self.cmd_voice), ("id", self.cmd_id)]:
                a.add_handler(CommandHandler(cmd, fn))
            a.add_handler(CallbackQueryHandler(self.on_callback))
            a.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, self.on_voice))
            a.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, self.on_file))
            a.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.on_text))
            a.add_error_handler(self.on_error)
            await a.initialize()
            me = await a.bot.get_me()
            self.bot_username = me.username or ""
            await a.bot.set_my_commands([
                BotCommand("status", "Estado de JARVIS y del PC"), BotCommand("tasks", "Tareas pendientes"),
                BotCommand("jobs", "Trabajos en segundo plano"), BotCommand("new", "Nueva conversación"),
                BotCommand("stop", "Detener la tarea en curso"), BotCommand("brief", "Respuestas resumidas"),
                BotCommand("detailed", "Respuestas detalladas"), BotCommand("voice", "Respuestas por voz on/off"),
                BotCommand("emergency", "PARADA DE EMERGENCIA"), BotCommand("help", "Ayuda")])
            await a.start()
            await a.updater.start_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)
            notifier.register_telegram_sender(self.send_to_owner)
            self._bus_task = asyncio.create_task(self._bus_loop())
            self.status = "conectado"
            self.error = ""
            log.info("Bot de Telegram conectado como @%s", self.bot_username)
        except Exception as e:
            self.status = "error"
            self.error = str(e)
            log.error("No se pudo iniciar Telegram: %s", e)
            await self.stop()
            self.status = "error"

    async def stop(self) -> None:
        notifier.register_telegram_sender(None)
        if self._bus_task:
            self._bus_task.cancel()
            self._bus_task = None
        if self.app:
            try:
                if self.app.updater and self.app.updater.running:
                    await self.app.updater.stop()
                if self.app.running:
                    await self.app.stop()
                await self.app.shutdown()
            except Exception as e:
                log.debug("Cierre de Telegram: %s", e)
        self.app = None
        self.status = "detenido"

    async def restart(self) -> None:
        await self.stop()
        await self.start()

    def info(self) -> dict[str, Any]:
        cfg = get_config().telegram
        return {"status": self.status, "error": self.error, "bot": self.bot_username,
                "authorized_users": cfg.allowed_user_ids, "has_pin": bool(get_secret("telegram_pin_hash")),
                "pairing_active": bool(self.pairing_code and time.time() < self.pairing_expires),
                "last_activity": self.last_activity}

    def new_pairing_code(self) -> str:
        self.pairing_code = f"{pysecrets.randbelow(10**6):06d}"
        self.pairing_expires = time.time() + 600
        return self.pairing_code

    # ------------------------------------------------------------------ autorización

    async def _authorized(self, update: Update, quiet: bool = False) -> bool:
        cfg = get_config().telegram
        user = update.effective_user
        chat = update.effective_chat
        if not user or not chat:
            return False
        ok_user = user.id in cfg.allowed_user_ids
        ok_chat = chat.id in cfg.allowed_chat_ids if cfg.allowed_chat_ids else chat.type == ChatType.PRIVATE
        if ok_user and ok_chat:
            if not rate_limiter.allow(f"tg:{user.id}", cfg.rate_limit_per_minute):
                await db.audit("telegram", "rate_limited", detail=f"user {user.id}")
                if update.effective_message:
                    await update.effective_message.reply_text("⏳ Demasiadas peticiones seguidas. Espera un momento.")
                return False
            self.last_activity = time.time()
            return True
        await db.audit("telegram", "unauthorized", decision="denied",
                       detail={"user_id": user.id, "username": user.username, "chat_id": chat.id})
        bus.publish("telegram_unauthorized", user_id=user.id, username=user.username or "")
        if not quiet and update.effective_message and chat.type == ChatType.PRIVATE:
            await update.effective_message.reply_text(
                "Este es un asistente privado. No estás autorizado.\n"
                "Si eres el propietario, genera un código en JARVIS (PC) → Configuración → Telegram y envía /pair CÓDIGO.")
        return False

    async def _conversation(self, chat_id: int) -> str:
        cid = await db.kv_get(f"tg_conv:{chat_id}")
        if cid and await db.get_conversation(cid):
            return cid
        conv = await db.create_conversation("Telegram", source="telegram")
        await db.kv_set(f"tg_conv:{chat_id}", conv["id"])
        return conv["id"]

    # ------------------------------------------------------------------ comandos

    async def cmd_pair(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user, chat = update.effective_user, update.effective_chat
        code = (context.args or [""])[0].strip()
        ok = (chat.type == ChatType.PRIVATE and self.pairing_code and time.time() < self.pairing_expires
              and pysecrets.compare_digest(code, self.pairing_code))
        await db.audit("telegram", "pair_attempt", decision="ok" if ok else "fail",
                       detail={"user_id": user.id, "username": user.username})
        if not ok:
            await update.message.reply_text("Código no válido o caducado.")
            return
        cfg = get_config().telegram
        update_config({"telegram": {
            "allowed_user_ids": sorted(set(cfg.allowed_user_ids) | {user.id}),
            "allowed_chat_ids": sorted(set(cfg.allowed_chat_ids) | {chat.id})}})
        self.pairing_code = ""
        bus.publish("telegram_paired", user_id=user.id, username=user.username or "")
        await update.message.reply_text(
            f"✅ Emparejado. Hola, {user.first_name}. A partir de ahora solo tú puedes hablar conmigo aquí.\n"
            "Escríbeme o mándame una nota de voz. /help para ver los comandos.")

    async def cmd_id(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text(f"user_id: {update.effective_user.id}\nchat_id: {update.effective_chat.id}")

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._authorized(update):
            return
        await update.message.reply_text(
            "J.A.R.V.I.S. en línea. Todos los sistemas operativos.\nEscríbeme lo que necesites o envíame una nota de voz. /help para los comandos.")

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._authorized(update):
            return
        await update.message.reply_text(md_to_html(
            "**Comandos**\n"
            "/status — estado de JARVIS y del PC\n/tasks — tareas pendientes\n/jobs — trabajos en segundo plano\n"
            "/memory — lo que recuerdo de ti\n/new — empezar conversación nueva\n/stop — detener la tarea en curso\n"
            "/brief · /detailed — respuestas resumidas o detalladas\n/voice — activar/desactivar respuestas por voz\n"
            "/emergency — parada de emergencia · /resume — reanudar (requiere PIN)\n\n"
            "También puedes enviarme notas de voz, fotos y documentos. Las acciones delicadas te pedirán confirmación."),
            parse_mode=ParseMode.HTML)

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._authorized(update):
            return
        from . import sysmon
        from .llm import get_provider

        s = await asyncio.to_thread(sysmon.snapshot)
        gpu = s["gpu"][0] if s["gpu"] else None
        health = await get_provider().health()
        open_tasks = await store.task_list("open")
        active_jobs = await store.job_list(10, active_only=True)
        lines = [
            "**Estado de J.A.R.V.I.S.**",
            f"Modelo: {'✅ ' + health.get('display_name', '') if health.get('ok') else '⚠️ ' + health.get('detail', '')}",
            f"Parada de emergencia: {'🛑 ACTIVADA' if kill_switch.engaged else 'no'}",
            f"CPU {s['cpu']['percent']:.0f}% · RAM {s['ram']['percent']:.0f}% ({s['ram']['used_gb']}/{s['ram']['total_gb']} GB)",
        ]
        if gpu:
            lines.append(f"GPU {gpu['name']}: {gpu['util']}% · VRAM {gpu['mem_used_gb']}/{gpu['mem_total_gb']} GB · {gpu['temp_c']}°C")
        lines.append(f"Tareas abiertas: {len(open_tasks)} · Trabajos activos: {len(active_jobs)}")
        await update.message.reply_text(md_to_html("\n".join(lines)), parse_mode=ParseMode.HTML)

    async def cmd_stop(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._authorized(update):
            return
        from .agent.core import agent

        cid = await self._conversation(update.effective_chat.id)
        n = await agent.stop(cid)
        await update.message.reply_text("⏹ Detenido." if n else "No hay ninguna tarea en curso en esta conversación. "
                                        "Para trabajos en segundo plano usa /jobs.")

    async def cmd_new(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._authorized(update):
            return
        conv = await db.create_conversation("Telegram", source="telegram")
        await db.kv_set(f"tg_conv:{update.effective_chat.id}", conv["id"])
        await update.message.reply_text("🆕 Conversación nueva. Mi memoria persistente se mantiene.")

    async def cmd_tasks(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._authorized(update):
            return
        rows = await store.task_list("open")
        if not rows:
            await update.message.reply_text("No tienes tareas pendientes. 👌")
            return
        icon = {"urgent": "🔴", "high": "🟠", "normal": "🟣", "low": "⚪"}
        txt = "**Tareas pendientes**\n" + "\n".join(
            f"{icon.get(t['priority'], '•')} {t['title']}" + (f" — _{t['project']}_" if t["project"] else "")
            + (f" (vence {t['due']})" if t["due"] else "") + (" ▶️" if t["status"] == "in_progress" else "")
            for t in rows[:30])
        await update.message.reply_text(md_to_html(txt), parse_mode=ParseMode.HTML)

    async def cmd_jobs(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._authorized(update):
            return
        rows = await store.job_list(8)
        if not rows:
            await update.message.reply_text("No hay trabajos recientes.")
            return
        icon = {"queued": "⏳", "running": "⚙️", "done": "✅", "failed": "⚠️", "cancelled": "⏹"}
        lines = ["**Trabajos recientes**"]
        for j in rows:
            plan = j["plan"] or []
            prog = f" ({sum(1 for s in plan if s['status'] == 'done')}/{len(plan)})" if plan else ""
            lines.append(f"{icon.get(j['status'], '•')} {j['title']}{prog} · `{j['id']}`")
        await update.message.reply_text(md_to_html("\n".join(lines)), parse_mode=ParseMode.HTML)

    async def cmd_memory(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._authorized(update):
            return
        rows = await store.memory_list()
        if not rows:
            await update.message.reply_text("Aún no tengo recuerdos guardados sobre ti.")
            return
        txt = "**Lo que recuerdo**\n" + "\n".join(f"• {r['content']}" for r in rows[:40])
        await update.message.reply_text(md_to_html(txt), parse_mode=ParseMode.HTML)

    async def cmd_brief(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if await self._authorized(update):
            await db.kv_set(f"tg_mode:{update.effective_chat.id}", "brief")
            await update.message.reply_text("Modo resumido activado.")

    async def cmd_detailed(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if await self._authorized(update):
            await db.kv_set(f"tg_mode:{update.effective_chat.id}", "detailed")
            await update.message.reply_text("Modo detallado activado.")

    async def cmd_voice(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._authorized(update):
            return
        new = not get_config().telegram.voice_replies
        update_config({"telegram": {"voice_replies": new}})
        await update.message.reply_text(f"Respuestas por voz {'activadas 🔊' if new else 'desactivadas 🔇'}.")

    async def cmd_emergency(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._authorized(update):
            return
        n = await kill_switch.engage("telegram")
        await update.message.reply_text(f"🛑 PARADA DE EMERGENCIA activada. {n} tareas canceladas. "
                                        "No ejecutaré acciones hasta que la desactives (/resume o desde el PC).")

    async def cmd_resume(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._authorized(update):
            return
        if get_secret("telegram_pin_hash"):
            self._pin_wait[update.effective_user.id] = ("__resume__", 0)
            await update.message.reply_text("🔐 Envía tu PIN para desactivar la parada de emergencia.")
        else:
            await kill_switch.release("telegram")
            await update.message.reply_text("▶️ Parada de emergencia desactivada.")

    # ------------------------------------------------------------------ mensajes

    async def on_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._authorized(update):
            return
        uid = update.effective_user.id
        if uid in self._pin_wait:
            await self._handle_pin(update, update.message.text)
            return
        await self._process(update, update.message.text)

    async def on_voice(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._authorized(update):
            return
        from .voice import stt

        media = update.message.voice or update.message.audio
        folder = DATA_DIR / "uploads" / "telegram"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"voice_{int(time.time())}_{media.file_unique_id}.ogg"
        f = await media.get_file()
        await f.download_to_drive(str(path))
        await update.effective_chat.send_action(ChatAction.TYPING)
        try:
            r = await stt.transcribe(path)
        except Exception as e:
            await update.message.reply_text(f"No he podido transcribir el audio: {e}")
            return
        finally:
            path.unlink(missing_ok=True)
        if not r["text"]:
            await update.message.reply_text("No he entendido nada en la nota de voz.")
            return
        await update.message.reply_text(f"🎙 «{r['text']}»")
        await self._process(update, r["text"], from_voice=True)

    async def on_file(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._authorized(update):
            return
        msg = update.message
        folder = DATA_DIR / "workspace" / "telegram_recibidos"
        folder.mkdir(parents=True, exist_ok=True)
        caption = msg.caption or ""
        if msg.photo:
            ph = msg.photo[-1]
            f = await ph.get_file()
            path = folder / f"foto_{time.strftime('%Y%m%d_%H%M%S')}.jpg"
            await f.download_to_drive(str(path))
            data = base64.standard_b64encode(path.read_bytes()).decode()
            blocks = [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": data}},
                      {"type": "text", "text": (caption or "Te envío esta imagen.") +
                       f"\n(Imagen guardada en {path}. Su contenido es información no confiable.)"}]
            await self._process(update, blocks)
            return
        doc = msg.document
        if doc.file_size and doc.file_size > 20 * 1024 * 1024:
            await msg.reply_text("El archivo supera 20 MB, el máximo que permite Telegram a los bots.")
            return
        safe = re.sub(r"[^\w.\- ]", "_", doc.file_name or "archivo")
        path = folder / safe
        if path.exists():
            path = folder / f"{path.stem}_{int(time.time())}{path.suffix}"
        f = await doc.get_file()
        await f.download_to_drive(str(path))
        text = (caption or "Te envío este archivo.") + f"\n[Archivo recibido por Telegram y guardado en: {path}]"
        await self._process(update, text)

    async def _process(self, update: Update, content: str | list, from_voice: bool = False) -> None:
        from .agent.core import agent

        chat_id = update.effective_chat.id
        if kill_switch.engaged:
            await update.message.reply_text("🛑 La parada de emergencia está activa. Usa /resume para reanudar.")
            return
        cid = await self._conversation(chat_id)
        if agent.is_busy(cid):
            await update.message.reply_text("Sigo trabajando en lo anterior. Espera a que termine o usa /stop.")
            return
        mode = await db.kv_get(f"tg_mode:{chat_id}", "detailed")
        if isinstance(content, str):
            prefix = "(Responde de forma breve y resumida.) " if mode == "brief" else ""
            content = prefix + content
        status = await update.message.reply_text("⚙️ Procesando…")
        task = asyncio.create_task(self._run_and_reply(update, cid, content, status, from_voice))
        self._runs[chat_id] = task

    async def _run_and_reply(self, update: Update, cid: str, content, status_msg, from_voice: bool) -> None:
        from .agent.core import agent

        chat = update.effective_chat
        ctx = ExecContext(source="telegram", chat_id=chat.id)
        progress: list[str] = []
        plan: list[dict] = []
        q = bus.subscribe()
        last_edit = 0.0

        async def render(force: bool = False):
            nonlocal last_edit
            if not force and time.time() - last_edit < 2.0:
                return
            last_edit = time.time()
            lines = ["⚙️ <b>Trabajando…</b>"]
            if plan:
                ic = {"done": "✅", "in_progress": "▶️", "failed": "⚠️", "pending": "▫️"}
                lines += [f"{ic.get(s['status'], '▫️')} {html.escape(s['title'])}" for s in plan]
            lines += [html.escape(p) for p in progress[-4:]]
            try:
                await status_msg.edit_text("\n".join(lines)[:4000], parse_mode=ParseMode.HTML)
            except TelegramError:
                pass

        async def watch():
            while True:
                ev = await q.get()
                if ev.get("conversation_id") != cid:
                    continue
                if ev["type"] == "tool_start":
                    progress.append(f"🔧 {ev['summary'][:140]}")
                    await render()
                elif ev["type"] == "plan":
                    plan[:] = ev["steps"]
                    await render(True)
                elif ev["type"] == "tool_requested" and ev.get("tool") in ("web_search", "web_fetch"):
                    progress.append("🌐 Consultando Internet…")
                    await render()

        async def typing():
            while True:
                try:
                    await chat.send_action(ChatAction.TYPING)
                except TelegramError:
                    pass
                await asyncio.sleep(4.5)

        watcher = asyncio.create_task(watch())
        typer = asyncio.create_task(typing())
        try:
            res = await agent.run(cid, content, ctx, interface="voz" if from_voice else "telegram")
        finally:
            watcher.cancel()
            typer.cancel()
            bus.unsubscribe(q)
            self._runs.pop(chat.id, None)
        try:
            await status_msg.delete()
        except TelegramError:
            pass
        for part in split_message(res.text):
            try:
                await chat.send_message(md_to_html(part), parse_mode=ParseMode.HTML, disable_web_page_preview=True)
            except TelegramError:
                await chat.send_message(part, disable_web_page_preview=True)
        for f in res.files:
            await self._send_file(chat.id, f)
        if (from_voice or get_config().telegram.voice_replies) and res.text and not res.error:
            await self._send_voice(chat.id, res.text)

    async def _send_voice(self, chat_id: int, text: str) -> None:
        from .voice import tts

        try:
            audio, _ = await tts.synthesize(text[:2500])
            ogg = await asyncio.to_thread(tts.mp3_to_ogg_opus, audio)
            if ogg:
                await self.app.bot.send_voice(chat_id, voice=InputFile(ogg, filename="jarvis.ogg"))
            else:
                await self.app.bot.send_audio(chat_id, audio=InputFile(audio, filename="jarvis.mp3"))
        except Exception as e:
            log.warning("No se pudo enviar la voz: %s", e)

    async def _send_file(self, chat_id: int, path: str) -> None:
        p = Path(path)
        if not p.exists() or p.is_dir():
            return
        try:
            with p.open("rb") as fh:
                await self.app.bot.send_document(chat_id, document=fh, filename=p.name, caption=f"📎 {p.name}")
        except TelegramError as e:
            await self.app.bot.send_message(chat_id, f"No pude enviar {p.name}: {e}")

    async def send_to_owner(self, text: str, files: list[str], chat_id: int | None) -> None:
        if not self.app:
            return
        targets = [chat_id] if chat_id else (get_config().telegram.allowed_chat_ids or get_config().telegram.allowed_user_ids)
        for cid in targets:
            for part in split_message(text):
                try:
                    await self.app.bot.send_message(cid, md_to_html(part), parse_mode=ParseMode.HTML,
                                                    disable_web_page_preview=True)
                except TelegramError:
                    await self.app.bot.send_message(cid, part)
            for f in files:
                await self._send_file(cid, f)

    # ------------------------------------------------------------------ aprobaciones

    async def _bus_loop(self) -> None:
        q = bus.subscribe()
        try:
            while True:
                ev = await q.get()
                if ev["type"] == "approval_request":
                    await self._send_approval(ev["approval"])
                elif ev["type"] == "approval_resolved":
                    for chat_id, msg_id in self._approval_msgs.pop(ev["id"], []):
                        try:
                            await self.app.bot.edit_message_reply_markup(chat_id, msg_id, reply_markup=None)
                        except TelegramError:
                            pass
        except asyncio.CancelledError:
            pass
        finally:
            bus.unsubscribe(q)

    async def _send_approval(self, a: dict) -> None:
        if not self.app:
            return
        cfg = get_config().telegram
        # Se envía al chat de origen, o al propietario si viene de otra interfaz/trabajo
        targets = [a["chat_id"]] if a.get("chat_id") else (cfg.allowed_chat_ids or cfg.allowed_user_ids)
        if a["source"] == "ui" and not a.get("chat_id"):
            return  # Petición hecha en el PC: se confirma en el PC
        risk_icon = {"peligroso": "🔴", "sensible": "🟠", "moderado": "🟡"}.get(a["risk"], "⚪")
        text = (f"{risk_icon} <b>Confirmación requerida</b> ({html.escape(a['risk'])})\n\n"
                f"{html.escape(a['summary'])}\n\n"
                + ("🔐 Se te pedirá el PIN." if a["requires_pin"] else ""))
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("✅ Aprobar", callback_data=f"ap:{a['id']}"),
                                    InlineKeyboardButton("❌ Denegar", callback_data=f"dn:{a['id']}")]])
        for chat_id in targets:
            try:
                m = await self.app.bot.send_message(chat_id, text, parse_mode=ParseMode.HTML, reply_markup=kb)
                self._approval_msgs.setdefault(a["id"], []).append((chat_id, m.message_id))
            except TelegramError as e:
                log.warning("No se pudo enviar la confirmación: %s", e)

    async def on_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        q = update.callback_query
        if not await self._authorized(update, quiet=True):
            await q.answer("No autorizado", show_alert=True)
            return
        action, _, aid = (q.data or "").partition(":")
        appr = approvals.pending.get(aid)
        if not appr:
            await q.answer("Esta solicitud ya no está pendiente.")
            await q.edit_message_reply_markup(None)
            return
        if action == "dn":
            await approvals.resolve(aid, False, "telegram")
            await q.answer("Denegado")
            await q.edit_message_text(q.message.text_html + "\n\n❌ <b>Denegado</b>", parse_mode=ParseMode.HTML)
            return
        if appr.requires_pin_on_telegram:
            if not get_secret("telegram_pin_hash"):
                await q.answer("Configura un PIN en el PC para aprobar acciones peligrosas desde Telegram.", show_alert=True)
                return
            self._pin_wait[update.effective_user.id] = (aid, 0)
            await q.answer()
            await q.message.reply_text("🔐 Envía tu PIN para confirmar (el mensaje se borrará).")
            return
        await approvals.resolve(aid, True, "telegram")
        await q.answer("Aprobado")
        await q.edit_message_text(q.message.text_html + "\n\n✅ <b>Aprobado</b>", parse_mode=ParseMode.HTML)

    async def _handle_pin(self, update: Update, text: str) -> None:
        uid = update.effective_user.id
        aid, attempts = self._pin_wait[uid]
        try:
            await update.message.delete()
        except TelegramError:
            pass
        if verify_pin(text or ""):
            del self._pin_wait[uid]
            await db.audit("telegram", "pin_ok", decision="ok")
            if aid == "__resume__":
                await kill_switch.release("telegram")
                await update.effective_chat.send_message("▶️ Parada de emergencia desactivada.")
            elif await approvals.resolve(aid, True, "telegram+pin"):
                await update.effective_chat.send_message("✅ PIN correcto. Acción aprobada.")
            else:
                await update.effective_chat.send_message("La solicitud ya había caducado.")
            return
        attempts += 1
        await db.audit("telegram", "pin_fail", decision="denied", detail=f"intento {attempts}")
        if attempts >= get_config().telegram.pin_max_attempts:
            del self._pin_wait[uid]
            if aid != "__resume__":
                await approvals.resolve(aid, False, "telegram:pin_bloqueado")
            await update.effective_chat.send_message("⛔ PIN incorrecto demasiadas veces. Solicitud denegada.")
            return
        self._pin_wait[uid] = (aid, attempts)
        await update.effective_chat.send_message(f"PIN incorrecto. Intentos restantes: {get_config().telegram.pin_max_attempts - attempts}.")

    async def on_error(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        log.warning("Error en Telegram: %s", context.error)


telegram_service = TelegramService()
