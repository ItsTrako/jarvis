"""Entorno de pruebas aislado: carpeta de datos temporal y proveedor de IA simulado."""

import asyncio
import os
import sys
import tempfile
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-test-"))
os.environ["JARVIS_DATA_DIR"] = str(_TMP)
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-no-real")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jarvis import db  # noqa: E402
from jarvis.config import load_config, update_config  # noqa: E402
from jarvis.llm.base import TurnResult  # noqa: E402
from jarvis.tools.base import load_all_tools  # noqa: E402

load_config()
update_config({"telegram": {"enabled": False}, "voice": {"stt_device": "cpu", "wake_word_enabled": False},
               "security": {"allowed_roots": [str(_TMP / "workspace")], "confirmation_timeout_s": 5}})
load_all_tools()


class FakeProvider:
    """Devuelve turnos guionizados en formato de la Messages API."""

    name = "fake"

    def __init__(self, script):
        self.script = list(script)
        self.calls: list[list[dict]] = []

    def is_configured(self):
        return True

    async def stream_turn(self, *, system, messages, tools, effort, on_event=None, max_tokens=None):
        self.calls.append([dict(m) for m in messages])
        step = self.script.pop(0)
        if callable(step):
            step = await step(messages)
        content, stop = step
        for b in content:
            if b["type"] == "text" and on_event:
                await on_event("text", {"text": b["text"]})
        text = "".join(b.get("text", "") for b in content if b["type"] == "text")
        return TurnResult(content=content, stop_reason=stop, text=text, usage={"input_tokens": 100})

    async def simple(self, **kw):
        return "resumen"

    async def health(self):
        return {"ok": True, "status": "operativo", "display_name": "Fake"}


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session", autouse=True)
def _db(event_loop):
    event_loop.run_until_complete(db.init_db())
    yield


@pytest.fixture
def fake(monkeypatch):
    def install(script):
        p = FakeProvider(script)
        import jarvis.agent.core as core
        monkeypatch.setattr(core, "get_provider", lambda: p)
        return p
    return install


@pytest.fixture
def tmp_root():
    return _TMP
