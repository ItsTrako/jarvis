"""Reconocimiento de voz local con faster-whisper (Whisper large-v3-turbo en la GPU).

Funciona 100 % en local: el audio no sale del ordenador. En la RTX 3060 transcribe una
frase en ~0,3-0,8 s. Si no hay CUDA disponible, cae automáticamente a CPU (int8) con un
modelo más ligero.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import threading
import time
from pathlib import Path

from ..config import DATA_DIR, get_config

log = logging.getLogger("jarvis.stt")

_model = None
_model_info: dict = {"loaded": False, "device": None, "model": None, "error": None, "load_s": None}
_lock = threading.Lock()


def _add_cuda_dll_dirs() -> None:
    """Las DLL de cuBLAS/cuDNN instaladas por pip no están en el PATH: se registran aquí."""
    if sys.platform != "win32":
        return
    base = Path(sys.prefix) / "Lib" / "site-packages" / "nvidia"
    for sub in ("cublas", "cudnn", "cuda_nvrtc"):
        d = base / sub / "bin"
        if d.exists():
            os.add_dll_directory(str(d))
            os.environ["PATH"] = str(d) + os.pathsep + os.environ.get("PATH", "")


def load_model():
    global _model
    with _lock:
        if _model is not None:
            return _model
        cfg = get_config().voice
        _add_cuda_dll_dirs()
        from faster_whisper import WhisperModel

        t0 = time.time()
        attempts = []
        if cfg.stt_device in ("auto", "cuda"):
            attempts.append(("cuda", "float16", cfg.stt_model))
        attempts.append(("cpu", "int8", cfg.stt_model if cfg.stt_device == "cpu" else "small"))
        last_err = None
        for device, compute, model_name in attempts:
            try:
                _model = WhisperModel(model_name, device=device, compute_type=compute,
                                      download_root=str(DATA_DIR / "models" / "whisper"))
                _model_info.update(loaded=True, device=device, model=model_name, error=None,
                                   load_s=round(time.time() - t0, 1))
                log.info("Whisper '%s' cargado en %s (%.1fs)", model_name, device, time.time() - t0)
                return _model
            except Exception as e:
                last_err = e
                log.warning("No se pudo cargar Whisper en %s: %s", device, e)
        _model_info.update(loaded=False, error=str(last_err))
        raise RuntimeError(f"No se pudo cargar el reconocimiento de voz: {last_err}")


def info() -> dict:
    return dict(_model_info)


PROMPT = ("Conversación en español con JARVIS, el asistente personal del ordenador. Hola, JARVIS. "
          "¿Qué tal? Abre Spotify, busca en Internet, ¿cuánta RAM tengo libre?, organiza mis archivos.")


def _transcribe_sync(path, language: str | None) -> dict:
    import numpy as np

    model = load_model()
    t0 = time.time()
    in_memory = not isinstance(path, str)
    if in_memory:
        peak = float(np.max(np.abs(path))) if len(path) else 0
        if 0 < peak < 0.5:  # micrófonos con poco volumen (DGM20): se normaliza sin saturar
            path = path * min(0.9 / peak, 20.0)
    segments, inf = model.transcribe(
        path, language=language or get_config().voice.stt_language or None, beam_size=5,
        # El audio del servicio ya viene recortado por su detector de voz: no se recorta dos veces
        vad_filter=not in_memory, vad_parameters={"min_silence_duration_ms": 500, "speech_pad_ms": 400},
        condition_on_previous_text=False, initial_prompt=PROMPT, hotwords="JARVIS")
    text = " ".join(s.text.strip() for s in segments).strip()
    return {"text": text, "language": inf.language, "duration": round(inf.duration, 2),
            "elapsed": round(time.time() - t0, 2)}


async def transcribe(path: str | Path, language: str | None = None) -> dict:
    return await asyncio.to_thread(_transcribe_sync, str(path), language)


async def transcribe_pcm(pcm16k, language: str | None = None) -> dict:
    """Transcribe audio en memoria (numpy int16 o float32, 16 kHz mono). No se guarda en disco."""
    import numpy as np

    audio = pcm16k.astype(np.float32) / (32768.0 if pcm16k.dtype == np.int16 else 1.0)
    return await asyncio.to_thread(_transcribe_sync, audio, language)


async def warmup() -> None:
    try:
        await asyncio.to_thread(load_model)
    except Exception as e:
        log.warning("Precarga de Whisper fallida: %s", e)
