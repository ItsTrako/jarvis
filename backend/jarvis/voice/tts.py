"""Síntesis de voz neural con varios motores intercambiables.

* ``edge``       — Voces neuronales de Microsoft (las mismas de Azure) vía edge-tts. Gratis,
                   sin clave, muy natural en español (es-ES-AlvaroNeural, ElviraNeural…). Por defecto.
* ``elevenlabs`` — Máximo realismo y expresividad (eleven_flash_v2_5: ~75 ms de latencia de modelo;
                   eleven_multilingual_v2: máxima calidad). Requiere API key (de pago a partir del plan gratuito).
* ``azure``      — Azure Neural TTS oficial con SSML y estilos expresivos. Requiere clave y región.

El texto se limpia (Markdown, URLs, código) y se sintetiza por frases para reducir la latencia.
"""

from __future__ import annotations

import asyncio
import html
import logging
import re
import shutil
import subprocess
from pathlib import Path

import httpx

from ..config import get_config
from ..secrets import get_secret

log = logging.getLogger("jarvis.tts")

DEFAULT_ELEVEN_VOICE = "JBFqnCBsd6RMkjVDRZzb"  # "George": voz masculina cálida, multilingüe


def clean_for_speech(text: str) -> str:
    t = re.sub(r"```.*?```", " (te dejo el código en pantalla) ", text, flags=re.S)
    t = re.sub(r"`([^`]+)`", r"\1", t)
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", t)
    t = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"https?://\S+", "el enlace", t)
    t = re.sub(r"^\s*#{1,6}\s*", "", t, flags=re.M)
    t = re.sub(r"^\s*[-*•]\s+", "", t, flags=re.M)
    t = re.sub(r"^\s*\|.*\|\s*$", "", t, flags=re.M)
    t = re.sub(r"[*_~>#]+", "", t)
    t = re.sub(r"\n{2,}", ". ", t)
    t = re.sub(r"\s+", " ", t)
    if get_config().user.language.startswith("es"):
        # Cifras, unidades y fechas a palabras: si no, las voces multilingües las leen en inglés
        from .hablar import normalizar

        t = normalizar(t)
    return t.strip()


def split_sentences(text: str, max_len: int = 280) -> list[str]:
    parts = re.split(r"(?<=[.!?…:;])\s+", text)
    out, buf = [], ""
    for p in parts:
        if len(buf) + len(p) < max_len:
            buf = f"{buf} {p}".strip()
        else:
            if buf:
                out.append(buf)
            buf = p
    if buf:
        out.append(buf)
    return [s for s in out if re.search(r"\w", s)]


async def _edge(text: str, voice: str | None = None) -> bytes:
    import edge_tts

    cfg = get_config().voice
    last: Exception | None = None
    for attempt in range(3):  # el servicio a veces falla de forma puntual: se reintenta
        try:
            com = edge_tts.Communicate(text, voice or cfg.edge_voice, rate=cfg.edge_rate, pitch=cfg.edge_pitch)
            chunks = bytearray()
            async for chunk in com.stream():
                if chunk["type"] == "audio":
                    chunks.extend(chunk["data"])
            if chunks:
                return bytes(chunks)
        except Exception as e:
            last = e
        await asyncio.sleep(0.4 * (attempt + 1))
    raise RuntimeError(f"Microsoft Neural no respondió: {last}")


async def _elevenlabs(text: str, voice: str | None = None) -> bytes:
    cfg = get_config().voice
    key = get_secret("elevenlabs_api_key")
    if not key:
        raise RuntimeError("Falta la API key de ElevenLabs")
    voice = voice or cfg.elevenlabs_voice_id or DEFAULT_ELEVEN_VOICE
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice}?output_format=mp3_44100_128",
            headers={"xi-api-key": key, "accept": "audio/mpeg"},
            json={"text": text, "model_id": cfg.elevenlabs_model, "language_code": "es",
                  "voice_settings": {"stability": 0.45, "similarity_boost": 0.8, "style": 0.15,
                                     "use_speaker_boost": True}})
        r.raise_for_status()
        return r.content


async def _azure(text: str, voice: str | None = None) -> bytes:
    cfg = get_config().voice
    key = get_secret("azure_speech_key")
    if not key:
        raise RuntimeError("Falta la clave de Azure Speech")
    body = html.escape(text)
    if cfg.azure_style:
        body = f'<mstts:express-as style="{cfg.azure_style}">{body}</mstts:express-as>'
    ssml = (f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" '
            f'xmlns:mstts="https://www.w3.org/2001/mstts" xml:lang="es-ES">'
            f'<voice name="{html.escape(voice or cfg.azure_voice)}">{body}</voice></speak>')
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post(f"https://{cfg.azure_region}.tts.speech.microsoft.com/cognitiveservices/v1",
                         headers={"Ocp-Apim-Subscription-Key": key, "Content-Type": "application/ssml+xml",
                                  "X-Microsoft-OutputFormat": "audio-24khz-96kbitrate-mono-mp3",
                                  "User-Agent": "JARVIS"}, content=ssml.encode())
        r.raise_for_status()
        return r.content


async def synthesize(text: str, clean: bool = True, engine: str | None = None,
                     voice: str | None = None) -> tuple[bytes, str]:
    """Devuelve (audio mp3, motor usado). Si el motor configurado falla, cae a edge.

    ``engine``/``voice`` permiten escuchar una voz concreta (galería de voces) sin cambiar la configuración.
    """
    text = clean_for_speech(text) if clean else text
    if not text:
        return b"", "none"
    engine = engine or get_config().voice.tts_engine
    order = [engine] + (["edge"] if engine != "edge" else [])
    last = None
    for eng in order:
        try:
            fn = {"edge": _edge, "elevenlabs": _elevenlabs, "azure": _azure}[eng]
            audio = await fn(text, voice if eng == engine else None)
            if audio:
                return audio, eng
        except Exception as e:
            last = e
            log.warning("TTS %s falló: %s", eng, e)
    raise RuntimeError(f"No se pudo sintetizar la voz: {last}")


async def _edge_stream(text: str, voice: str | None):
    import edge_tts

    cfg = get_config().voice
    com = edge_tts.Communicate(text, voice or cfg.edge_voice, rate=cfg.edge_rate, pitch=cfg.edge_pitch)
    async for chunk in com.stream():
        if chunk["type"] == "audio" and chunk["data"]:
            yield chunk["data"]


async def _elevenlabs_stream(text: str, voice: str | None):
    cfg = get_config().voice
    key = get_secret("elevenlabs_api_key")
    if not key:
        raise RuntimeError("Falta la API key de ElevenLabs")
    voice = voice or cfg.elevenlabs_voice_id or DEFAULT_ELEVEN_VOICE
    async with httpx.AsyncClient(timeout=60) as c:
        async with c.stream(
                "POST", f"https://api.elevenlabs.io/v1/text-to-speech/{voice}/stream?output_format=mp3_44100_128"
                        "&optimize_streaming_latency=3",
                headers={"xi-api-key": key, "accept": "audio/mpeg"},
                json={"text": text, "model_id": cfg.elevenlabs_model, "language_code": "es",
                      "voice_settings": {"stability": 0.45, "similarity_boost": 0.8, "style": 0.15,
                                         "use_speaker_boost": True}}) as r:
            r.raise_for_status()
            async for b in r.aiter_bytes():
                if b:
                    yield b


async def stream_audio(text: str, clean: bool = True, engine: str | None = None, voice: str | None = None):
    """Voz en streaming: devuelve fragmentos MP3 según se generan, para empezar a sonar al instante.

    Si el motor falla antes del primer fragmento se reintenta y, si hace falta, se cae a Microsoft Neural.
    """
    text = clean_for_speech(text) if clean else text
    if not text:
        return
    engine = engine or get_config().voice.tts_engine
    attempts = [(engine, voice)] + [("edge", None)] * (2 if engine == "edge" else 1)
    last = None
    for i, (eng, v) in enumerate(attempts):
        sent = False
        try:
            if eng == "edge":
                gen = _edge_stream(text, v)
            elif eng == "elevenlabs":
                gen = _elevenlabs_stream(text, v)
            else:  # Azure: sin streaming, se entrega completo
                async def _one():
                    yield await _azure(text, v)
                gen = _one()
            async for b in gen:
                sent = True
                yield b
            if sent:
                return
        except Exception as e:
            last = e
            if sent:  # ya sonaba: no se repite la frase
                log.warning("TTS cortado a mitad: %s", e)
                return
            log.warning("TTS %s falló (intento %d): %s", eng, i + 1, e)
            await asyncio.sleep(0.3)
    raise RuntimeError(f"No se pudo sintetizar la voz: {last}")


async def list_voices() -> dict:
    out: dict = {"edge": [], "elevenlabs": []}
    try:
        import edge_tts

        voices = await edge_tts.list_voices()
        out["edge"] = sorted(
            [{"id": v["ShortName"], "name": v["ShortName"].split("-")[-1].replace("Neural", ""),
              "locale": v["Locale"], "gender": v["Gender"]}
             for v in voices if v["Locale"].startswith("es-") or "Multilingual" in v["ShortName"]],
            key=lambda v: (not v["locale"].startswith("es-ES"), v["locale"], v["id"]))
    except Exception as e:
        log.warning("No se pudieron listar voces edge: %s", e)
    key = get_secret("elevenlabs_api_key")
    if key:
        try:
            async with httpx.AsyncClient(timeout=20) as c:
                r = await c.get("https://api.elevenlabs.io/v1/voices", headers={"xi-api-key": key})
                r.raise_for_status()
                out["elevenlabs"] = [{"id": v["voice_id"], "name": v["name"],
                                      "labels": v.get("labels", {})} for v in r.json().get("voices", [])]
        except Exception as e:
            log.warning("No se pudieron listar voces ElevenLabs: %s", e)
    return out


def mp3_to_ogg_opus(mp3: bytes) -> bytes | None:
    """Para notas de voz de Telegram (OGG/Opus)."""
    ff = shutil.which("ffmpeg")
    if not ff:
        return None
    r = subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-i", "pipe:0", "-c:a", "libopus",
                        "-b:a", "48k", "-f", "ogg", "pipe:1"], input=mp3, capture_output=True,
                       creationflags=0x08000000, timeout=60)
    return r.stdout if r.returncode == 0 else None
