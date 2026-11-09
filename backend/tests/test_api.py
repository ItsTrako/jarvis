"""Pruebas de la API HTTP/WebSocket con el proveedor simulado."""

import time

import pytest
from fastapi.testclient import TestClient

from jarvis import db
from tests.conftest import FakeProvider


@pytest.fixture(scope="module")
def client():
    db._engine = None  # el TestClient usa su propio bucle de eventos
    from jarvis.server import SESSION_TOKEN, app

    with TestClient(app) as c:
        c.token = SESSION_TOKEN
        yield c


def H(c):
    return {"X-Jarvis-Token": c.token}


def test_auth_and_host_checks(client):
    assert client.get("/api/status").status_code == 401
    assert client.get("/api/status", headers={**H(client), "Origin": "http://evil.com"}).status_code == 403
    assert client.get("/api/status", headers={**H(client), "Host": "evil.com"}).status_code == 403
    r = client.get("/api/status", headers=H(client))
    assert r.status_code == 200 and r.json()["counts"]["tools"] >= 50


def test_index_injects_token(client):
    r = client.get("/")
    assert r.status_code in (200, 503)
    if r.status_code == 200:
        assert "__JARVIS_TOKEN__" in r.text


def test_chat_flow_over_http_and_ws(client, monkeypatch):
    p = FakeProvider([
        ([{"type": "text", "text": "Consultando tareas."},
          {"type": "tool_use", "id": "t1", "name": "create_task", "input": {"title": "Llamar al banco", "priority": "high"}}],
         "tool_use"),
        ([{"type": "text", "text": "Hecho, he apuntado «Llamar al banco»."}], "end_turn"),
    ])
    import jarvis.agent.core as core
    monkeypatch.setattr(core, "get_provider", lambda: p)

    with client.websocket_connect(f"/ws?token={client.token}") as ws:
        assert ws.receive_json()["type"] == "hello"
        r = client.post("/api/chat", json={"text": "Apunta llamar al banco"}, headers=H(client))
        assert r.status_code == 200
        cid = r.json()["conversation_id"]
        seen = set()
        deadline = time.time() + 15
        while time.time() < deadline:
            ev = ws.receive_json()
            seen.add(ev["type"])
            if ev["type"] == "run_end" and ev.get("conversation_id") == cid:
                assert "apuntado" in ev["text"]
                break
        assert {"run_start", "assistant_delta", "tool_start", "tool_end", "run_end"} <= seen

    conv = client.get(f"/api/conversations/{cid}", headers=H(client)).json()
    kinds = [i["kind"] for i in conv["items"]]
    assert kinds[0] == "user" and "tool" in kinds and kinds[-1] == "assistant"
    tasks = client.get("/api/tasks?status=open", headers=H(client)).json()
    assert any(t["title"] == "Llamar al banco" for t in tasks)


def test_ws_rejects_bad_token(client):
    with pytest.raises(Exception):
        with client.websocket_connect("/ws?token=malo") as ws:
            ws.receive_json()


def test_config_patch_validation(client):
    r = client.patch("/api/config", json={"security": {"confirm_level": "nunca"}}, headers=H(client))
    assert r.status_code == 400
    r = client.patch("/api/config", json={"llm": {"effort": "high"}}, headers=H(client))
    assert r.status_code == 200 and r.json()["llm"]["effort"] == "high"


def test_emergency_endpoint(client):
    assert client.post("/api/emergency", json={"engaged": True}, headers=H(client)).json()["engaged"]
    assert client.post("/api/chat", json={"text": "hola"}, headers=H(client)).status_code == 423
    assert not client.post("/api/emergency", json={"engaged": False}, headers=H(client)).json()["engaged"]


def test_secrets_never_returned(client):
    r = client.get("/api/secrets", headers=H(client)).json()
    assert all(isinstance(v, bool) for v in r.values())
    assert client.put("/api/secrets/telegram_pin_hash", json={"value": "x"}, headers=H(client)).status_code == 400
