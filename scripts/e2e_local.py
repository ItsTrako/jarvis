"""Prueba de extremo a extremo contra el JARVIS en ejecución (HTTP + WebSocket).

Uso:  ..\\.venv\\Scripts\\python ..\\scripts\\e2e_local.py "pregunta 1" "pregunta 2" ...
Muestra, para cada pregunta, las herramientas usadas, el tiempo y la respuesta final.
"""

import asyncio
import json
import sys
import time
from pathlib import Path

import httpx
import websockets

ROOT = Path(__file__).resolve().parents[1]
TOKEN = (ROOT / "data" / ".session_token").read_text().strip()
BASE = "http://127.0.0.1:8765"
H = {"X-Jarvis-Token": TOKEN}


async def ask(text: str, conv: str | None) -> str:
    async with websockets.connect(f"ws://127.0.0.1:8765/ws?token={TOKEN}", max_size=None) as ws:
        r = httpx.post(f"{BASE}/api/chat", headers=H, json={"text": text, "conversation_id": conv}, timeout=30)
        r.raise_for_status()
        cid = r.json()["conversation_id"]
        t0 = time.time()
        tools = []
        while True:
            ev = json.loads(await asyncio.wait_for(ws.recv(), timeout=900))
            if ev.get("conversation_id") != cid:
                continue
            if ev["type"] == "tool_start":
                tools.append(ev["tool"])
            elif ev["type"] == "tool_end" and not ev["ok"]:
                tools.append(f"(error: {ev['preview'][:80]})")
            elif ev["type"] == "approval_request":
                pass
            elif ev["type"] == "run_end":
                print(f"\n>>> {text}\n    herramientas: {tools or '—'} · {time.time() - t0:.0f} s")
                print("    " + ev["text"].replace("\n", "\n    ")[:1500])
                return cid


async def main():
    conv = None
    for q in sys.argv[1:]:
        conv = await ask(q, conv)


asyncio.run(main())
