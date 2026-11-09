"""Pruebas del proveedor local (Ollama) sin necesidad de tener Ollama en marcha."""

import os

from jarvis.config import update_config
from jarvis.llm import active_provider_name
from jarvis.llm.ollama_provider import OllamaProvider, ThinkFilter
from jarvis.tools.base import registry


def stream(chunks):
    f = ThinkFilter()
    vis, hid = [], []
    for i, c in enumerate(chunks):
        v, h = f.feed(c, final=i == len(chunks) - 1)
        vis.append(v)
        hid.append(h)
    return "".join(vis), "".join(hid)


def test_think_filter_split_tags():
    v, h = stream(["<thi", "nk>pienso en ", "algo</th", "ink>\n\nHola, ", "soy JARVIS."])
    assert v == "Hola, soy JARVIS." and h == "pienso en algo"


def test_think_filter_stray_close_and_plain():
    assert stream(["</think>\n\nBuenas", " tardes"]) == ("Buenas tardes", "")
    assert stream(["a < b y c > d"]) == ("a < b y c > d", "")


def stream_impl(chunks):
    f = ThinkFilter(implicit_open=True)
    out = [f.feed(c, final=i == len(chunks) - 1) for i, c in enumerate(chunks)]
    return "".join(v for v, _ in out), "".join(h for _, h in out)


def test_think_filter_implicit_reasoning_is_hidden():
    # Caso real (Qwen3): razona sin «<think>» y cierra con «</think>»
    v, h = stream_impl(["Okay, the user asked \"2+2\". ", "It's simple.\n</th", "ink>\n\n4"])
    assert v == "4" and "Okay" in h
    # Con /no_think funcionando: solo llega el cierre vacío
    assert stream_impl(["</think>\n\nHola, ", "soy JARVIS."]) == ("Hola, soy JARVIS.", "")
    # Sin ninguna etiqueta: todo es respuesta (se entrega al final)
    assert stream_impl(["Buenas ", "noches."]) == ("Buenas noches.", "")


def test_convert_history_with_tools_and_images():
    p = OllamaProvider()
    msgs = [
        {"role": "user", "content": [{"type": "text", "text": "<contexto>x</contexto>"},
                                     {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "AAA"}},
                                     {"type": "text", "text": "¿Qué ves?"}]},
        {"role": "assistant", "content": [{"type": "text", "text": "Miro."},
                                          {"type": "tool_use", "id": "t1", "name": "system_info", "input": {}}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "fallo", "is_error": True}]},
    ]
    out = p._convert("SYS", msgs, vision=True)
    assert out[0]["role"] == "system" and "Modo local" in out[0]["content"]
    assert out[1]["images"] == ["AAA"] and "¿Qué ves?" in out[1]["content"]
    assert out[2]["tool_calls"][0]["function"]["name"] == "system_info"
    assert out[3] == {"role": "tool", "content": "ERROR: fallo", "tool_name": "system_info"}
    no_vision = p._convert("SYS", msgs, vision=False)
    assert "images" not in no_vision[1] and "no tiene visión" in no_vision[1]["content"]


def test_fit_drops_old_turns():
    update_config({"llm": {"local_context": 4096}})
    p = OllamaProvider()
    msgs = [{"role": "system", "content": "s"}]
    for i in range(40):
        msgs += [{"role": "user", "content": f"pregunta {i} " + "x" * 400}, {"role": "assistant", "content": "ok " * 50}]
    fitted = p._fit(msgs, [], 1024)
    assert len(fitted) < len(msgs) and fitted[0]["role"] == "system"
    assert fitted[1]["content"].startswith("[Nota del sistema")
    assert fitted[2]["role"] == "user" and "pregunta 39" in fitted[-2]["content"]
    update_config({"llm": {"local_context": 16384}})


def test_auto_provider_and_local_web_tools(monkeypatch):
    update_config({"llm": {"provider": "auto"}})
    assert active_provider_name() == "anthropic"  # hay clave (de prueba) en el entorno
    names = {t["name"] for t in registry.schemas()}
    assert "web_search" not in names  # con Claude se usan las herramientas web del servidor
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    monkeypatch.setattr("jarvis.secrets.keyring.get_password", lambda *a: None)
    assert active_provider_name() == "ollama"
    names = {t["name"] for t in registry.schemas()}
    assert {"web_search", "web_fetch"} <= names
    tools = OllamaProvider()._tools(registry.schemas())
    assert all(t["type"] == "function" and len(t["function"]["description"]) <= 421 for t in tools)
    update_config({"llm": {"provider": "auto"}})
