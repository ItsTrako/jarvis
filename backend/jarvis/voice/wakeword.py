"""Palabra de activación "Hey JARVIS" con openWakeWord (local, ONNX, CPU).

Privacidad: solo se activa si el usuario lo habilita en la interfaz. El navegador envía
audio PCM 16 kHz por WebSocket local; aquí solo se calcula la probabilidad de la palabra
clave en ventanas de 80 ms. El audio NO se guarda, NO se transcribe y NO sale del PC.
"""

from __future__ import annotations

import logging
import threading

import numpy as np

log = logging.getLogger("jarvis.wakeword")
_lock = threading.Lock()
_ready = False


def ensure_models(name: str = "hey_jarvis") -> None:
    global _ready
    with _lock:
        if _ready:
            return
        import openwakeword
        from openwakeword.utils import download_models

        download_models([name])
        _ready = True


class WakeWordDetector:
    FRAME = 1280  # 80 ms a 16 kHz

    def __init__(self, model_name: str = "hey_jarvis", threshold: float = 0.5) -> None:
        ensure_models(model_name)
        from openwakeword.model import Model

        self.model = Model(wakeword_models=[model_name], inference_framework="onnx")
        self.name = model_name
        self.threshold = threshold
        self._buf = np.zeros(0, dtype=np.int16)
        self._cooldown = 0

    def feed(self, pcm16: bytes) -> float | None:
        """Añade audio; devuelve la puntuación si se detecta la palabra clave."""
        self._buf = np.concatenate([self._buf, np.frombuffer(pcm16, dtype=np.int16)])
        hit = None
        while len(self._buf) >= self.FRAME:
            frame, self._buf = self._buf[: self.FRAME], self._buf[self.FRAME:]
            scores = self.model.predict(frame)
            score = max(scores.values()) if scores else 0.0
            if self._cooldown > 0:
                self._cooldown -= 1
                continue
            if score >= self.threshold:
                hit = float(score)
                self._cooldown = 25  # ~2 s sin nuevas detecciones
                self.model.reset()
        return hit
