"""Prueba del asistente de voz permanente con audio sintético inyectado como micrófono.

Simula: silencio → «Hey Jarvis» → pregunta → silencio. Verifica detección, grabación,
transcripción, respuesta del agente, voz por los altavoces y vuelta al reposo.
Uso (con el servicio detenido):  cd backend && ..\\.venv\\Scripts\\python ..\\scripts\\test_voice_pipeline.py
"""

import asyncio
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from jarvis import db  # noqa: E402
from jarvis.config import load_config  # noqa: E402
from jarvis.events import bus  # noqa: E402
from jarvis.tools.base import load_all_tools  # noqa: E402
from jarvis.voice import tts  # noqa: E402
from jarvis.voice.assistant import Player, VoiceAssistant  # noqa: E402


async def pcm16k(text: str, voice: str) -> np.ndarray:
    audio, _ = await tts.synthesize(text, engine="edge", voice=voice)
    samples, sr = Player.decode(audio)  # 48 kHz float
    from scipy.signal import resample_poly

    return (resample_poly(samples, 1, 3) * 32767 * 0.8).astype(np.int16)


class FakeMic:
    def __init__(self, stream: np.ndarray):
        self.queue: asyncio.Queue = asyncio.Queue()
        self.stream = stream
        self.device_name = "micrófono simulado"

    async def feed(self):
        for i in range(0, len(self.stream), 1280):
            await self.queue.put(self.stream[i:i + 1280])
            await asyncio.sleep(0.08)
        while True:  # después, silencio
            await self.queue.put(np.zeros(1280, np.int16))
            await asyncio.sleep(0.08)

    def drain(self):
        pass  # el audio simulado no se descarta

    def stop(self):
        pass


async def main():
    load_config()
    await db.init_db()
    load_all_tools()
    hey = await pcm16k("Hey Jarvis!", "en-US-AndrewMultilingualNeural")
    q = await pcm16k("¿Qué hora es? Responde en una frase muy corta.", "es-ES-ElviraNeural")
    sil = lambda s: np.zeros(int(16000 * s), np.int16)  # noqa: E731
    stream = np.concatenate([sil(1.0), hey, sil(0.6), q, sil(0.2)])

    va = VoiceAssistant()
    loop = asyncio.get_running_loop()
    va._mic = FakeMic(stream)
    va._player = Player(lambda v: None)
    from openwakeword.vad import VAD
    from jarvis.voice.wakeword import WakeWordDetector

    va._det = WakeWordDetector("hey_jarvis", 0.5)
    va._vad = VAD()
    states, transcripts, t0 = [], [], time.time()
    sub = bus.subscribe()

    async def watch():
        while True:
            ev = await sub.get()
            if ev["type"] == "voice_state":
                states.append((round(time.time() - t0, 1), ev["state"]))
            elif ev["type"] == "voice_transcript":
                transcripts.append(ev["text"])
            elif ev["type"] == "run_end":
                print("RESPUESTA:", ev["text"])

    w = asyncio.create_task(watch())
    feeder = asyncio.create_task(va._mic.feed())
    await asyncio.wait_for(va._standby(), timeout=20)
    print(f"Palabra detectada a los {time.time() - t0:.1f} s")
    await asyncio.wait_for(va._conversation(), timeout=600)
    await asyncio.sleep(0.3)
    feeder.cancel()
    w.cancel()
    print("TRANSCRIPCIÓN:", transcripts)
    print("ESTADOS:", states)


asyncio.run(main())
