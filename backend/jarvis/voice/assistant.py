"""Asistente de voz permanente: «Hey JARVIS» 24/7 y conversación continua manos libres.

Funciona dentro del servicio de JARVIS (no en el navegador), así que escucha aunque la
ventana esté minimizada, en segundo plano o cerrada.

Flujo:
  reposo ──«Hey JARVIS»──► escuchando ──fin de frase──► transcribiendo ──► pensando
     ▲                         ▲                                            │
     │                         └──────── respuesta hablada (frase a frase) ◄┘
     └── silencio prolongado o «gracias, eso es todo»

Privacidad: en reposo el audio solo pasa por el detector de la palabra clave (local, en
memoria, ventanas de 80 ms). Nada se graba ni se transcribe hasta oír «Hey JARVIS».
"""

from __future__ import annotations

import asyncio
import io
import logging
import re
import threading
import time
import unicodedata
from collections import deque
from typing import Any

import numpy as np

from .. import db
from ..config import get_config
from ..events import bus
from ..security import ExecContext, kill_switch

log = logging.getLogger("jarvis.voice")

SR = 16000
EXIT_PHRASES = ("eso es todo", "nada mas", "nada más", "hasta luego", "adios", "adiós", "gracias jarvis",
                "puedes descansar", "termina la conversacion", "deja de escuchar", "ya esta", "ya está")
STOP_PHRASES = ("para", "calla", "callate", "cállate", "silencio", "stop", "basta")
# Alucinaciones típicas de Whisper con ruido de fondo
JUNK = re.compile(r"^(gracias( por ver)?[.!]*|subt[ií]tulos.*|amara\.org.*|\.+|¡?suscr[ií]bete.*|m+\.?)$", re.I)


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", t.lower())
    return re.sub(r"[^a-z0-9ñ ]", "", "".join(c for c in t if not unicodedata.combining(c))).strip()


# ------------------------------------------------------------------ dispositivos

def _pick_device(label: str, kind: str) -> int | None:
    import sounddevice as sd

    devices = sd.query_devices()
    apis = sd.query_hostapis()
    chan = "max_input_channels" if kind == "input" else "max_output_channels"
    if not label:
        return None  # predeterminado de Windows
    q = label.lower()
    ranked = []
    for i, d in enumerate(devices):
        if d[chan] <= 0 or q not in d["name"].lower():
            continue
        api = apis[d["hostapi"]]["name"]
        prio = {"Windows WASAPI": 0, "MME": 1, "Windows DirectSound": 2}.get(api, 9)
        ranked.append((prio, i))
    return min(ranked)[1] if ranked else None


def list_devices() -> dict[str, list[str]]:
    import sounddevice as sd

    ins, outs = set(), set()
    apis = sd.query_hostapis()
    for d in sd.query_devices():
        if apis[d["hostapi"]]["name"] != "Windows WASAPI":
            continue
        name = re.sub(r"^[^(]*\(|\)$", "", d["name"]).strip() or d["name"]
        if d["max_input_channels"] > 0:
            ins.add(name)
        if d["max_output_channels"] > 0:
            outs.add(name)
    return {"inputs": sorted(ins), "outputs": sorted(outs)}


class Mic:
    """Captura del micrófono en un hilo de audio → bloques de 80 ms a 16 kHz en una cola asyncio."""

    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=200)
        self.stream = None
        self.device_name = ""

    def start(self) -> None:
        import sounddevice as sd
        from scipy.signal import resample_poly

        label = get_config().voice.mic_label
        idx = _pick_device(label, "input")
        info = sd.query_devices(idx if idx is not None else sd.default.device[0])
        self.device_name = info["name"]
        sr = int(info["default_samplerate"])
        g = np.gcd(SR, sr)
        up, down = SR // g, sr // g

        def cb(indata, frames, t, status):
            x = indata[:, 0].astype(np.float32)
            y = resample_poly(x, up, down) if sr != SR else x
            block = np.clip(y, -32768, 32767).astype(np.int16)
            try:
                self.loop.call_soon_threadsafe(self._put, block)
            except RuntimeError:
                pass

        self.stream = sd.InputStream(device=idx, channels=1, samplerate=sr, dtype="int16",
                                     blocksize=int(sr * 0.08), callback=cb)
        self.stream.start()
        log.info("Micrófono abierto: %s (%d Hz)", self.device_name, sr)

    def _put(self, block) -> None:
        if self.queue.full():
            try:
                self.queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        self.queue.put_nowait(block)

    def drain(self) -> None:
        while not self.queue.empty():
            self.queue.get_nowait()

    def stop(self) -> None:
        if self.stream:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self.stream = None


class Player:
    """Reproduce audio (MP3 de la voz o tonos) por los altavoces/cascos, interrumpible."""

    def __init__(self, on_level) -> None:
        self.stop_event = threading.Event()
        self.on_level = on_level

    @staticmethod
    def decode(mp3: bytes) -> tuple[np.ndarray, int]:
        import av

        container = av.open(io.BytesIO(mp3))
        res = av.AudioResampler(format="flt", layout="mono", rate=48000)
        parts = [f.to_ndarray().reshape(-1) for frame in container.decode(container.streams.audio[0])
                 for f in res.resample(frame)]
        parts += [f.to_ndarray().reshape(-1) for f in res.resample(None)]
        return (np.concatenate(parts) if parts else np.zeros(0, np.float32)), 48000

    def play(self, samples: np.ndarray, sr: int) -> bool:
        """Bloqueante (ejecutar en un hilo). Devuelve False si se interrumpió."""
        import sounddevice as sd

        self.stop_event.clear()
        idx = _pick_device(get_config().voice.output_device, "output")
        block = sr // 20
        with sd.OutputStream(device=idx, samplerate=sr, channels=1, dtype="float32") as out:
            for i in range(0, len(samples), block):
                if self.stop_event.is_set():
                    return False
                chunk = samples[i:i + block]
                out.write(chunk.reshape(-1, 1))
                self.on_level(float(min(1.0, np.sqrt(np.mean(chunk ** 2)) * 6)) if len(chunk) else 0.0)
        self.on_level(0.0)
        return True

    def stop(self) -> None:
        self.stop_event.set()

    # ---------------------------------------------------------- streaming
    def open(self) -> None:
        """Abre la salida de audio una vez para toda la respuesta (abrirla por frase añade retardo)."""
        import sounddevice as sd

        self.stop_event.clear()
        idx = _pick_device(get_config().voice.output_device, "output")
        self._out = sd.OutputStream(device=idx, samplerate=48000, channels=1, dtype="float32", latency="low")
        self._out.start()

    def close(self) -> None:
        out = getattr(self, "_out", None)
        if out is not None:
            try:
                out.stop()
                out.close()
            except Exception:
                pass
            self._out = None
        self.on_level(0.0)

    def play_stream(self, reader: "StreamReader") -> bool:
        """Decodifica el MP3 según llega y lo reproduce sin esperar al final (ejecutar en un hilo)."""
        import av

        out = getattr(self, "_out", None)
        if out is None:
            return False
        try:
            container = av.open(reader, format="mp3")
        except Exception as e:
            log.warning("No se pudo abrir el audio: %s", e)
            return True
        res = av.AudioResampler(format="flt", layout="mono", rate=48000)
        try:
            for frame in container.decode(container.streams.audio[0]):
                for f in res.resample(frame):
                    if self.stop_event.is_set():
                        return False
                    chunk = f.to_ndarray().reshape(-1).astype(np.float32)
                    out.write(chunk.reshape(-1, 1))
                    self.on_level(float(min(1.0, np.sqrt(np.mean(chunk ** 2)) * 6)) if len(chunk) else 0.0)
        except Exception as e:
            log.debug("Fin de audio: %s", e)
        finally:
            container.close()
        return not self.stop_event.is_set()


class StreamReader(io.RawIOBase):
    """Archivo «en vivo»: se le van añadiendo fragmentos MP3 y el decodificador los lee según llegan."""

    def __init__(self) -> None:
        import queue

        self.q: "queue.Queue[bytes | None]" = queue.Queue()
        self.buf = b""
        self.eof = False

    def feed(self, b: bytes | None) -> None:
        self.q.put(b)

    def readable(self) -> bool:
        return True

    def readinto(self, b) -> int:
        while not self.buf and not self.eof:
            item = self.q.get()
            if item is None:
                self.eof = True
            else:
                self.buf += item
        n = min(len(b), len(self.buf))
        b[:n] = self.buf[:n]
        self.buf = self.buf[n:]
        return n


def tone(kind: str) -> np.ndarray:
    notes = {"wake": [523.25, 783.99, 1046.5], "listen": [880.0], "sleep": [783.99, 523.25]}[kind]
    out = []
    for f in notes:
        t = np.arange(int(48000 * 0.11)) / 48000
        env = np.minimum(1, t * 120) * np.exp(-t * 18)
        out.append(0.12 * np.sin(2 * np.pi * f * t) * env)
    return np.concatenate(out).astype(np.float32)


class SentenceSplitter:
    def __init__(self) -> None:
        self.buf = ""
        self.in_code = False
        self.started = False

    def feed(self, delta: str) -> list[str]:
        self.buf += delta
        out = []
        while True:
            # La primera frase sale en cuanto hay una coma (voz casi instantánea); el resto, por frases.
            first = not self.started
            m = (re.match(r"^([\s\S]{12,}?[.!?…:;,])(\s)", self.buf) if first else None) \
                or re.match(r"^([\s\S]{20,}?[.!?…:;])(\s)", self.buf) or re.match(r"^([\s\S]+?)\n\n", self.buf) \
                or re.match(r"^([\s\S]{160,}?[,;])(\s)", self.buf)
            if m:
                self.started = True
            if not m:
                break
            s = m.group(1)
            self.buf = self.buf[m.end():]
            if s.count("```") % 2:
                self.in_code = not self.in_code
                continue
            if not self.in_code:
                out.append(s)
        return out

    def flush(self) -> list[str]:
        s, self.buf = self.buf, ""
        return [s] if s.strip() and not self.in_code else []

    def force(self, min_chars: int = 28) -> list[str]:
        """Si el texto llega lento, adelanta la voz cortando en el último espacio (no espera al punto)."""
        if self.in_code or len(self.buf) < min_chars:
            return []
        cut = self.buf.rfind(" ")
        if cut < min_chars // 2:
            return []
        s, self.buf = self.buf[:cut], self.buf[cut + 1:]
        self.started = True
        return [s]


# ------------------------------------------------------------------ asistente

class VoiceAssistant:
    def __init__(self) -> None:
        self.state = "off"
        self.error = ""
        self.device = ""
        self.conversation_id: str | None = None
        self._task: asyncio.Task | None = None
        self._mic: Mic | None = None
        self._player: Player | None = None
        self._speaking = False
        self._interrupt = asyncio.Event()
        self._last_level = 0.0
        self._level_ts = 0.0

    # -------------------------------------------------------------- control

    def info(self) -> dict[str, Any]:
        return {"state": self.state, "error": self.error, "device": self.device,
                "enabled": get_config().voice.wake_word_enabled, "conversation_id": self.conversation_id}

    def _set(self, state: str) -> None:
        if state != self.state:
            self.state = state
            bus.publish("voice_state", state=state, conversation_id=self.conversation_id, device=self.device)

    def _level(self, v: float) -> None:
        now = time.time()
        if now - self._level_ts > 0.06 or (v == 0 and self._last_level > 0):
            self._level_ts, self._last_level = now, v
            bus.publish("voice_level", level=round(v, 3))

    def _level_threadsafe(self, loop, v: float) -> None:
        loop.call_soon_threadsafe(self._level, v)

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self.error = ""
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._player:
            self._player.stop()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
        self._task = None
        if self._mic:
            self._mic.stop()
        self._set("off")

    async def apply_config(self) -> None:
        if get_config().voice.wake_word_enabled:
            await self.stop()
            await self.start()
        else:
            await self.stop()

    def interrupt(self) -> None:
        """Corta la voz (botón «detener» o «Hey JARVIS» mientras habla)."""
        self._interrupt.set()
        if self._player:
            self._player.stop()

    # -------------------------------------------------------------- bucle principal

    async def _run(self) -> None:
        loop = asyncio.get_running_loop()
        from .wakeword import WakeWordDetector

        while True:
            try:
                self._mic = Mic(loop)
                await asyncio.to_thread(self._mic.start)
                self.device = self._mic.device_name
                self._player = Player(lambda v: self._level_threadsafe(loop, v))
                cfg = get_config().voice
                self._det = await asyncio.to_thread(WakeWordDetector, cfg.wake_word_model, cfg.wake_word_threshold)
                from openwakeword.vad import VAD

                self._vad = VAD()
                while True:
                    await self._standby()
                    await self._conversation()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.error = str(e)
                log.exception("Asistente de voz: error; reintento en 10 s")
                self._set("error")
                if self._mic:
                    self._mic.stop()
                await asyncio.sleep(10)

    async def _standby(self) -> None:
        self._set("standby")
        self._det.model.reset()
        self._mic.drain()
        while True:
            block = await self._mic.queue.get()
            if kill_switch.engaged:
                continue
            if await asyncio.to_thread(self._det.feed, block.tobytes()):
                log.info("Palabra de activación detectada")
                return

    async def _listen(self, timeout: float, keep_buffer: bool = False) -> np.ndarray | None:
        """Graba una frase: empieza al detectar voz y termina tras un silencio. None si no hablas.

        keep_buffer: conserva lo dicho justo tras «Hey JARVIS» («Hey JARVIS, ¿qué hora es?» de un tirón).
        """
        cfg = get_config().voice
        self._set("listening")
        if not keep_buffer:
            self._mic.drain()  # descarta el final de la propia voz de JARVIS
        self._vad.reset_states() if hasattr(self._vad, "reset_states") else None
        pre: deque = deque(maxlen=7)  # ~0,55 s antes de empezar a hablar (no se corta la primera sílaba)
        frames: list[np.ndarray] = []
        pending = np.zeros(0, np.int16)
        speech_ms = silence_ms = 0.0
        started = False
        t0 = time.time()
        while True:
            try:
                block = await asyncio.wait_for(self._mic.queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                block = None
            if block is not None:
                self._level(float(min(1.0, np.sqrt(np.mean((block / 32768.0) ** 2)) * 9)))
                (frames if started else pre).append(block)
                pending = np.concatenate([pending, block])
                while len(pending) >= 1536:
                    chunk, pending = pending[:1536], pending[1536:]
                    p = float(self._vad.predict(chunk, frame_size=512))
                    if p > 0.5:
                        speech_ms += 96
                        silence_ms = 0
                        if not started and speech_ms >= 192:
                            started = True
                            frames = list(pre)
                    else:
                        silence_ms += 96
                        if not started:
                            speech_ms = max(0, speech_ms - 96)
            elapsed = time.time() - t0
            if started and silence_ms >= cfg.end_silence_s * 1000:
                break
            if not started and elapsed > timeout:
                self._level(0)
                return None
            if elapsed > 40:
                break
        self._level(0)
        return np.concatenate(frames) if frames else None

    async def _say(self, text: str) -> bool:
        from . import tts

        try:
            audio, _ = await tts.synthesize(text)
        except Exception as e:
            log.warning("TTS: %s", e)
            return True
        samples, sr = await asyncio.to_thread(Player.decode, audio)
        return await self._play(samples, sr)

    async def _play(self, samples: np.ndarray, sr: int) -> bool:
        self._speaking = True
        try:
            return await asyncio.to_thread(self._player.play, samples, sr)
        finally:
            self._speaking = False

    async def _earcon(self, kind: str) -> None:
        await self._play(tone(kind), 48000)

    async def _watch_barge_in(self) -> None:
        """Mientras JARVIS habla, «Hey JARVIS» le interrumpe."""
        self._det.model.reset()
        while True:
            block = await self._mic.queue.get()
            if self._speaking and await asyncio.to_thread(self._det.feed, block.tobytes()):
                log.info("Interrupción por voz")
                self.interrupt()

    _FILLERS = ("Un segundo.", "Déjame ver.", "Ahora mismo.", "Dame un momento.", "Vamos a ver.")

    async def _warm_fillers(self) -> None:
        for t in self._FILLERS:
            await self._filler(t)

    async def _filler(self, text: str | None = None) -> bytes | None:
        """Frase corta de espera, sintetizada una vez y guardada en memoria (latencia cero)."""
        import random

        from . import tts

        if not hasattr(self, "_filler_cache") or self._filler_voice != get_config().voice.edge_voice:
            self._filler_cache: dict[str, bytes] = {}
            self._filler_voice = get_config().voice.edge_voice
        text = text or random.choice(self._FILLERS)
        if text not in self._filler_cache:
            try:
                self._filler_cache[text], _ = await tts.synthesize(text)
            except Exception:
                return None
        return self._filler_cache[text]

    async def _voice_conversation(self) -> str:
        cid = await db.kv_get("voice_conv")
        conv = await db.get_conversation(cid) if cid else None
        if not conv or time.time() - conv["updated_at"] > 3 * 3600:
            conv = await db.create_conversation("Conversación por voz", source="voice")
            await db.kv_set("voice_conv", conv["id"])
        return conv["id"]

    async def _conversation(self) -> None:
        from ..agent.core import agent
        from . import stt

        cfg = get_config().voice
        self._set("listening")  # feedback inmediato en la interfaz
        self.conversation_id = await self._voice_conversation()
        asyncio.create_task(self._warm_fillers())
        asyncio.create_task(self._earcon("wake"))  # el tono suena mientras ya se graba
        first = True
        while True:
            audio = await self._listen(timeout=7.0 if first else cfg.follow_up_s, keep_buffer=first)
            if audio is None:
                await self._earcon("sleep")
                return
            first = False
            self._set("transcribing")
            r = await stt.transcribe_pcm(audio)
            text = (r.get("text") or "").strip()
            if len(text) < 2 or JUNK.match(text):
                continue
            n = _norm(text)
            bus.publish("voice_transcript", text=text, conversation_id=self.conversation_id)
            if any(p in n for p in EXIT_PHRASES) and len(n) < 40:
                await self._say("De acuerdo. Aquí estaré.")
                return
            if n in STOP_PHRASES:
                continue
            if kill_switch.engaged:
                await self._say("La parada de emergencia está activa. No puedo ejecutar nada.")
                return
            await self._respond(text)

    async def _respond(self, text: str) -> None:
        """Ejecuta el agente y va hablando la respuesta frase a frase mientras se genera."""
        from ..agent.core import agent
        from . import tts

        cid = self.conversation_id
        self._set("thinking")
        self._interrupt.clear()
        sentences: asyncio.Queue = asyncio.Queue()
        splitter = SentenceSplitter()
        q = bus.subscribe()
        ctx = ExecContext(source="wake")
        run = asyncio.create_task(agent.run(cid, text, ctx, interface="voz"))

        def synth(s: str) -> StreamReader:
            # Cada frase se pide al motor de voz en cuanto existe y su audio se va acumulando en un
            # lector «en vivo»; la reproducción empieza con los primeros milisegundos, en orden.
            reader = StreamReader()

            async def fill():
                try:
                    async for b in tts.stream_audio(s):
                        if self._interrupt.is_set():
                            break
                        reader.feed(b)
                except Exception as e:
                    log.warning("TTS: %s", e)
                finally:
                    reader.feed(None)

            asyncio.create_task(fill())
            return reader

        started = time.time()
        any_speech = False

        async def collect():
            nonlocal any_speech
            asked = False
            filler_done = False
            while True:
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=0.7)
                except asyncio.TimeoutError:
                    # El texto llega lento (modelo local ocupado): se adelanta la voz sin esperar al punto
                    for s in splitter.force():
                        any_speech = True
                        await sentences.put(synth(s))
                    # Si la respuesta tarda, una frase corta precargada evita el silencio incómodo
                    if not any_speech and not filler_done and time.time() - started > 2.2:
                        filler_done = True
                        cached = await self._filler()
                        if cached:
                            r = StreamReader()
                            r.feed(cached)
                            r.feed(None)
                            await sentences.put(r)
                    continue
                if ev["type"] == "assistant_delta" and ev.get("conversation_id") == cid:
                    any_speech = True
                if ev.get("conversation_id") != cid and ev["type"] != "approval_request":
                    continue
                if ev["type"] == "assistant_delta":
                    for s in splitter.feed(ev["text"]):
                        await sentences.put(synth(s))
                elif ev["type"] == "approval_request" and ev["approval"].get("source") == "wake" and not asked:
                    asked = True
                    await sentences.put(synth("Necesito que confirmes esa acción en la pantalla."))
                elif ev["type"] == "run_end":
                    for s in splitter.flush():
                        await sentences.put(synth(s))
                    if ev.get("error") and not ev.get("text"):
                        await sentences.put(synth("Ha ocurrido un error."))
                    await sentences.put(None)
                    return

        async def speak():
            opened = False
            try:
                while True:
                    reader = await sentences.get()
                    if reader is None:
                        return
                    if self._interrupt.is_set():
                        continue
                    if not opened:
                        await asyncio.to_thread(self._player.open)
                        opened = True
                    self._set("speaking")
                    self._speaking = True
                    try:
                        await asyncio.to_thread(self._player.play_stream, reader)
                    finally:
                        self._speaking = False
            finally:
                if opened:
                    await asyncio.to_thread(self._player.close)

        barge = asyncio.create_task(self._watch_barge_in())
        collector = asyncio.create_task(collect())
        try:
            await speak()
            await collector
            await run
        finally:
            barge.cancel()
            collector.cancel()
            bus.unsubscribe(q)
            self._mic.drain()


voice_assistant = VoiceAssistant()
