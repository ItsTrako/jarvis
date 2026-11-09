"""Proveedor local y gratuito: modelos abiertos ejecutados en tu GPU con Ollama.

* Sin API key, sin coste por uso y sin que tus conversaciones salgan del PC.
* Habla con el servidor HTTP local de Ollama (``/api/chat``) en streaming, con herramientas.
* Traduce el historial canónico (formato de la Messages API: text / tool_use / tool_result)
  al formato de Ollama y viceversa, de modo que una conversación puede pasar de Claude a local
  y de local a Claude sin perder el hilo.
* Recorta el historial antiguo para respetar la ventana de contexto del modelo local.
* Si Ollama no está en marcha, intenta arrancarlo.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import shutil
import subprocess
import time
import uuid
from typing import Any

import httpx
from pathlib import Path

from ..config import get_config
from .base import StreamCallback, TurnResult

log = logging.getLogger("jarvis.ollama")

# Catálogo curado para una GPU de 12 GB (tamaños de descarga de ollama.com/library)
CATALOG: list[dict[str, Any]] = [
    {"id": "gemma4:12b", "name": "Gemma 4 12B", "vendor": "Google", "size_gb": 7.1,
     "hf": "hf.co/unsloth/gemma-4-12b-it-GGUF:Q4_K_M",
     "caps": ["herramientas", "visión", "razonamiento"], "context": "256K",
     "blurb": "El más capaz que cabe en tu GPU. Ve imágenes y capturas de pantalla.", "tier": "Máxima calidad"},
    {"id": "qwen3:8b", "name": "Qwen3 8B", "vendor": "Alibaba", "size_gb": 5.0,
     "hf": "hf.co/Qwen/Qwen3-8B-GGUF:Q4_K_M",
     "caps": ["herramientas", "razonamiento"], "context": "40K",
     "blurb": "Rápido y muy fiable usando herramientas. Deja más memoria libre.", "tier": "Equilibrado"},
    {"id": "qwen3:14b", "name": "Qwen3 14B", "vendor": "Alibaba", "size_gb": 9.3,
     "caps": ["herramientas", "razonamiento"], "context": "40K",
     "blurb": "Más razonamiento, pero justo de memoria junto a la voz.", "tier": "Razonamiento"},
    {"id": "qwen3:4b", "name": "Qwen3 4B", "vendor": "Alibaba", "size_gb": 2.5,
     "hf": "hf.co/Qwen/Qwen3-4B-GGUF:Q4_K_M",
     "caps": ["herramientas", "razonamiento"], "context": "256K",
     "blurb": "Ultraligero. Para equipos modestos o respuestas instantáneas.", "tier": "Ligero"},
]

LOCAL_ADDENDUM = """

# Modo local
Funcionas con un modelo abierto en el propio PC del usuario (gratis y privado). Reglas adicionales:
- Para información actual usa web_search y después web_fetch sobre las mejores URLs. No inventes datos.
- Usa exactamente los nombres de herramienta y parámetros definidos. Una herramienta por paso si dudas.
- Cuando una herramienta devuelva el resultado, responde en lenguaje natural; no repitas el JSON.
- Responde siempre en español salvo que el usuario use otro idioma."""


class OllamaUnavailable(Exception):
    pass


def ollama_exe() -> str | None:
    """Ruta de ollama.exe (también recién instalado, aunque el PATH de la sesión no esté actualizado)."""
    import os

    exe = shutil.which("ollama")
    if exe:
        return exe
    for base in (os.environ.get("LOCALAPPDATA", ""), os.environ.get("ProgramFiles", "")):
        cand = Path(base) / ("Programs/Ollama/ollama.exe" if "Local" in base else "Ollama/ollama.exe")
        if cand.exists():
            return str(cand)
    return None


class ThinkFilter:
    """Separa en streaming los bloques <think>…</think> que algunos modelos escriben en el texto.

    Devuelve (texto_visible, texto_de_razonamiento) por cada fragmento, aunque las etiquetas
    lleguen partidas entre fragmentos. También elimina un «</think>» suelto (Qwen3 con /no_think).
    """

    OPEN, CLOSE = "<think>", "</think>"

    def __init__(self, implicit_open: bool = False) -> None:
        # implicit_open: el modelo puede empezar razonando SIN «<think>» (la plantilla ya lo abrió).
        # Entonces se retiene el texto hasta ver «</think>»; si nunca aparece, todo era respuesta.
        self.buf = ""
        self.in_think = False
        self.started = False
        self.pending_implicit = implicit_open

    def _partial(self, s: str) -> int:
        for tag in (self.OPEN, self.CLOSE):
            for k in range(min(len(tag) - 1, len(s)), 0, -1):
                if s.endswith(tag[:k]):
                    return k
        return 0

    def feed(self, chunk: str, final: bool = False) -> tuple[str, str]:
        self.buf += chunk
        visible, thinking = [], []
        if self.pending_implicit:
            i_open, i_close = self.buf.find(self.OPEN), self.buf.find(self.CLOSE)
            if i_close >= 0 and (i_open < 0 or i_close < i_open):
                thinking.append(self.buf[:i_close])  # todo lo anterior al cierre era razonamiento
                self.buf = self.buf[i_close + len(self.CLOSE):]
                self.pending_implicit = False
            elif i_open >= 0 or final:
                self.pending_implicit = False  # razonamiento explícito o respuesta sin razonar
            else:
                return "", ""  # aún no se sabe: se retiene
        while self.buf:
            if self.in_think:
                i = self.buf.find(self.CLOSE)
                if i >= 0:
                    thinking.append(self.buf[:i])
                    self.buf = self.buf[i + len(self.CLOSE):]
                    self.in_think = False
                    continue
                keep = 0 if final else self._partial(self.buf)
                thinking.append(self.buf[: len(self.buf) - keep])
                self.buf = self.buf[len(self.buf) - keep:]
                break
            i_open, i_close = self.buf.find(self.OPEN), self.buf.find(self.CLOSE)
            if i_close >= 0 and (i_open < 0 or i_close < i_open):  # cierre suelto: se descarta
                visible.append(self.buf[:i_close])
                self.buf = self.buf[i_close + len(self.CLOSE):]
                continue
            if i_open >= 0:
                visible.append(self.buf[:i_open])
                self.buf = self.buf[i_open + len(self.OPEN):]
                self.in_think = True
                continue
            keep = 0 if final else self._partial(self.buf)
            visible.append(self.buf[: len(self.buf) - keep])
            self.buf = self.buf[len(self.buf) - keep:]
            break
        text = "".join(visible)
        if not self.started:
            text = text.lstrip()
            self.started = bool(text)
        return text, "".join(thinking)


def _tid() -> str:
    return "toolu_local_" + uuid.uuid4().hex[:16]


def _est_tokens(obj: Any) -> int:
    s = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False)
    return int(len(s) / 3.3) + 4


class OllamaProvider:
    name = "ollama"
    _instance: "OllamaProvider | None" = None

    def __init__(self) -> None:
        self._caps: dict[str, list[str]] = {}
        self._started_at = 0.0
        self.last_error = ""
        self.last_stats: dict[str, Any] = {}
        self._routed: str | None = None
        self._route_until = 0.0
        self.route_reason = ""

    @classmethod
    def instance(cls) -> "OllamaProvider":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ------------------------------------------------------------------ servidor Ollama

    @property
    def url(self) -> str:
        return get_config().llm.ollama_url.rstrip("/")

    @property
    def model(self) -> str:
        return get_config().llm.local_model

    def is_configured(self) -> bool:
        return bool(self.model)

    async def _get(self, path: str, timeout: float = 5) -> Any:
        async with httpx.AsyncClient(timeout=timeout) as c:
            r = await c.get(self.url + path)
            r.raise_for_status()
            return r.json()

    async def _post(self, path: str, body: dict, timeout: float = 30) -> Any:
        async with httpx.AsyncClient(timeout=timeout) as c:
            r = await c.post(self.url + path, json=body)
            r.raise_for_status()
            return r.json()

    async def running(self) -> bool:
        try:
            await self._get("/api/version", timeout=2)
            return True
        except Exception:
            return False

    async def ensure_running(self) -> None:
        if await self.running():
            return
        exe = ollama_exe()
        if not exe:
            raise OllamaUnavailable(
                "Ollama no está instalado. Descárgalo gratis en https://ollama.com/download e instálalo; "
                "después elige un modelo en Configuración → Inteligencia.")
        if time.time() - self._started_at > 30:
            log.info("Arrancando Ollama…")
            self._started_at = time.time()
            subprocess.Popen([exe, "serve"], creationflags=0x08000000 | 0x00000008, close_fds=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(40):
            await asyncio.sleep(0.5)
            if await self.running():
                return
        raise OllamaUnavailable("No he podido arrancar Ollama. Ábrelo manualmente y vuelve a intentarlo.")

    async def installed(self) -> list[dict[str, Any]]:
        data = await self._get("/api/tags")
        return data.get("models", [])

    async def pick_model(self, force: bool = False) -> str:
        """Modo adaptativo: el modelo principal si cabe holgadamente en la VRAM libre; si no, el ligero.

        La elección se mantiene 5 minutos para no cambiar de modelo a mitad de una tarea.
        """
        cfg = get_config().llm
        main, light = cfg.local_model, cfg.local_light_model
        if not cfg.local_adaptive or not light or light == main:
            self.route_reason = ""
            return main
        if not force and self._routed and time.time() < self._route_until:
            return self._routed
        try:
            from .. import sysmon

            installed = {m["name"]: m.get("size", 0) / 1024**3 for m in await self.installed()}
            if light not in installed:
                return main
            gpu = await asyncio.to_thread(sysmon._gpu)
            if not gpu:
                return main
            loaded = {m["name"]: m.get("size_vram", 0) / 1024**3 for m in (await self._get("/api/ps")).get("models", [])}
            g = gpu[0]
            others = g["mem_used_gb"] - sum(loaded.values())  # escritorio, juegos, voz…
            free_for_models = g["mem_total_gb"] - others
            need = installed.get(main, 8.0) + 1.5  # pesos + contexto
            choice = main if free_for_models >= need else light
            self.route_reason = ("" if choice == main else
                                 f"GPU ocupada ({others:.1f} GB en uso por otras apps): modelo ligero {light}")
        except Exception as e:
            log.debug("pick_model: %s", e)
            choice = main
        if choice != self._routed:
            log.info("Modelo local elegido: %s %s", choice, f"({self.route_reason})" if self.route_reason else "")
        self._routed, self._route_until = choice, time.time() + 300
        return choice

    async def capabilities(self, model: str | None = None) -> list[str]:
        model = model or self.model
        if model not in self._caps:
            try:
                info = await self._post("/api/show", {"model": model}, timeout=15)
                self._caps[model] = info.get("capabilities") or []
            except Exception:
                return []
        return self._caps[model]

    # ------------------------------------------------------------------ conversión de formato

    def _tools(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out = []
        for t in tools:
            if "input_schema" not in t:  # herramientas de servidor de Claude: no aplican en local
                continue
            desc = t["description"]
            if len(desc) > 420:  # descripciones más compactas: ahorran contexto al modelo local
                desc = desc[:420].rsplit(" ", 1)[0] + "…"
            out.append({"type": "function", "function": {
                "name": t["name"], "description": desc, "parameters": t["input_schema"]}})
        return out

    def _convert(self, system: str, messages: list[dict[str, Any]], vision: bool) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = [{"role": "system", "content": system + LOCAL_ADDENDUM}]
        names: dict[str, str] = {}
        for m in messages:
            content = m["content"]
            if isinstance(content, str):
                content = [{"type": "text", "text": content}]
            if m["role"] == "assistant":
                text, calls = [], []
                for b in content:
                    t = b.get("type")
                    if t == "text":
                        text.append(b["text"])
                    elif t == "tool_use":
                        names[b["id"]] = b["name"]
                        calls.append({"function": {"name": b["name"], "arguments": b.get("input") or {}}})
                    elif t == "server_tool_use":
                        text.append(f"[Búsqueda web realizada: {json.dumps(b.get('input'), ensure_ascii=False)[:200]}]")
                msg: dict[str, Any] = {"role": "assistant", "content": "\n".join(text)}
                if calls:
                    msg["tool_calls"] = calls
                if msg["content"] or calls:
                    out.append(msg)
                continue
            # usuario: puede mezclar texto, imágenes, documentos y resultados de herramientas
            texts, images = [], []
            for b in content:
                t = b.get("type")
                if t == "text":
                    texts.append(b["text"])
                elif t == "image" and b.get("source", {}).get("type") == "base64":
                    if vision:
                        images.append(b["source"]["data"])
                    else:
                        texts.append("[Imagen adjunta: este modelo local no tiene visión; usa un modelo con visión como Gemma 4.]")
                elif t == "document":
                    texts.append(f"[Documento adjunto «{b.get('title', 'PDF')}»: léelo con read_document usando la ruta indicada.]")
                elif t == "tool_result":
                    c = b.get("content")
                    tool_images = []
                    if isinstance(c, list):
                        parts = []
                        for x in c:
                            if x.get("type") == "text":
                                parts.append(x["text"])
                            elif x.get("type") == "image" and x.get("source", {}).get("type") == "base64":
                                tool_images.append(x["source"]["data"])
                        c = "\n".join(parts)
                    if b.get("is_error"):
                        c = f"ERROR: {c}"
                    out.append({"role": "tool", "content": str(c), "tool_name": names.get(b.get("tool_use_id"), "")})
                    if tool_images:
                        if vision:
                            out.append({"role": "user", "content": "Imagen devuelta por la herramienta:", "images": tool_images})
                        else:
                            out.append({"role": "user", "content": "[La herramienta devolvió una imagen, pero este modelo no tiene visión.]"})
            if texts or images:
                msg = {"role": "user", "content": "\n\n".join(texts)}
                if images:
                    msg["images"] = images
                out.append(msg)
        return out

    def _fit(self, msgs: list[dict[str, Any]], tools: list[dict[str, Any]], max_out: int) -> list[dict[str, Any]]:
        """Descarta los turnos más antiguos hasta que el historial cabe en el contexto local."""
        budget = get_config().llm.local_context - max_out - _est_tokens(tools)
        system, rest = msgs[0], msgs[1:]
        budget -= _est_tokens(system["content"])

        def size(m):
            return _est_tokens(m.get("content", "")) + _est_tokens(m.get("tool_calls", "")) + 1500 * len(m.get("images", []))

        total = sum(size(m) for m in rest)
        dropped = 0
        while total > budget and len(rest) > 1:
            total -= size(rest.pop(0))
            dropped += 1
            # el historial debe empezar en un mensaje de usuario normal (no en un resultado de herramienta)
            while rest and (rest[0]["role"] != "user"):
                total -= size(rest.pop(0))
                dropped += 1
        if dropped:
            rest.insert(0, {"role": "user", "content": "[Nota del sistema: se han omitido mensajes antiguos de esta "
                                                       "conversación para ajustarse a la memoria del modelo local.]"})
            log.info("Contexto local: %d mensajes antiguos omitidos", dropped)
        if total > budget and rest:  # un único mensaje enorme: se trunca su contenido
            last = rest[-1]
            keep = max(2000, int(budget * 3.3))
            if isinstance(last.get("content"), str) and len(last["content"]) > keep:
                last["content"] = last["content"][:keep] + "\n[… truncado para caber en el contexto local]"
        return [system] + rest

    # ------------------------------------------------------------------ turno

    async def stream_turn(self, *, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]],
                          effort: str, on_event: StreamCallback | None = None,
                          max_tokens: int | None = None) -> TurnResult:
        from .anthropic_provider import ProviderNotConfigured

        cfg = get_config().llm
        try:
            await self.ensure_running()
        except OllamaUnavailable as e:
            raise ProviderNotConfigured(str(e)) from e
        names = {m["name"] for m in await self.installed()}
        model = await self.pick_model()
        if model not in names and f"{model}:latest" not in names:
            raise ProviderNotConfigured(
                f"El modelo local «{model}» no está descargado. Descárgalo en Configuración → Inteligencia "
                "(un clic) o elige otro de los instalados.")

        caps = await self.capabilities(model)
        vision = "vision" in caps
        mode = cfg.local_thinking
        think = mode == "on" or (mode == "auto" and effort in ("high", "xhigh", "max"))
        max_out = min(max_tokens or 4096, 8192)
        if think:
            max_out = min(max_out * 2, 12288)  # el razonamiento también consume tokens de salida
        otools = self._tools(tools) if "tools" in caps or not caps else []
        qwen = model.startswith("qwen3")
        if qwen and not think:
            system = system + "\n/no_think"  # interruptor oficial de Qwen3
        omsgs = self._fit(self._convert(system, messages, vision), otools, max_out)
        if qwen and not think:
            # Qwen3 obedece la instrucción más reciente: también al final del último mensaje del usuario
            last_user = next((m for m in reversed(omsgs) if m["role"] == "user"), None)
            if last_user is not None:
                last_user["content"] = f"{last_user['content']} /no_think"

        async def emit(kind: str, data: dict[str, Any]) -> None:
            if on_event:
                r = on_event(kind, data)
                if inspect.isawaitable(r):
                    await r

        body: dict[str, Any] = {
            "model": model, "messages": omsgs, "stream": True, "keep_alive": cfg.local_keep_alive,
            "options": {"num_ctx": cfg.local_context, "num_predict": max_out, "temperature": 0.6, "top_p": 0.95},
        }
        if otools:
            body["tools"] = otools
        # Se envía siempre: algunos modelos (Gemma 4) razonan por defecto aunque no lo anuncien
        body["think"] = think

        text_parts: list[str] = []
        calls: list[dict[str, Any]] = []
        thinking_chars = 0
        stats: dict[str, Any] = {}
        filt = ThinkFilter(implicit_open=qwen)
        t0 = time.time()

        async def on_thinking(n: int) -> None:
            nonlocal thinking_chars
            if n and thinking_chars == 0:
                await emit("progress", {"text": "Razonando… "})
            thinking_chars += n

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(600, connect=10)) as c:
                for attempt in range(2):
                    async with c.stream("POST", self.url + "/api/chat", json=body) as r:
                        if r.status_code >= 400:
                            detail = (await r.aread()).decode("utf-8", "replace")[:400]
                            if attempt == 0 and "think" in detail.lower():
                                body.pop("think", None)  # modelo sin interruptor de razonamiento
                                continue
                            raise RuntimeError(f"Ollama respondió {r.status_code}: {detail}")
                        async for line in r.aiter_lines():
                            if not line.strip():
                                continue
                            chunk = json.loads(line)
                            if chunk.get("error"):
                                raise RuntimeError(f"Ollama: {chunk['error']}")
                            msg = chunk.get("message") or {}
                            await on_thinking(len(msg.get("thinking") or ""))
                            if msg.get("content") or chunk.get("done"):
                                visible, hidden = filt.feed(msg.get("content") or "", final=bool(chunk.get("done")))
                                await on_thinking(len(hidden))
                                if visible:
                                    text_parts.append(visible)
                                    await emit("text", {"text": visible})
                            for tc in msg.get("tool_calls") or []:
                                fn = tc.get("function", {})
                                args = fn.get("arguments")
                                if isinstance(args, str):
                                    try:
                                        args = json.loads(args)
                                    except json.JSONDecodeError:
                                        args = {"_raw": args}
                                call = {"type": "tool_use", "id": _tid(), "name": fn.get("name", ""), "input": args or {}}
                                calls.append(call)
                                await emit("tool_call", {"name": call["name"], "id": call["id"]})
                            if chunk.get("done"):
                                stats = chunk
                    break
        except httpx.ConnectError as e:
            raise ProviderNotConfigured("Se ha perdido la conexión con Ollama.") from e

        text = "".join(text_parts).strip()
        content: list[dict[str, Any]] = []
        if text:
            content.append({"type": "text", "text": text})
        content.extend(calls)
        if not content:
            content = [{"type": "text", "text": "(El modelo local no ha generado respuesta.)"}]
        eval_s = (stats.get("eval_duration") or 0) / 1e9
        self.last_stats = {
            "model": model, "prompt_tokens": stats.get("prompt_eval_count"), "output_tokens": stats.get("eval_count"),
            "tokens_per_s": round(stats.get("eval_count", 0) / eval_s, 1) if eval_s else None,
            "seconds": round(time.time() - t0, 1), "thinking": think,
        }
        log.info("Turno local %s: %s", model, self.last_stats)
        stop = "tool_use" if calls else ("max_tokens" if stats.get("done_reason") == "length" else "end_turn")
        return TurnResult(content=content, stop_reason=stop, text=text, model=model,
                          usage={"input_tokens": stats.get("prompt_eval_count") or 0,
                                 "output_tokens": stats.get("eval_count") or 0})

    async def warmup(self, system: str, tools: list[dict[str, Any]]) -> None:
        """Carga el modelo y precalcula el prefijo (instrucciones + herramientas) en la caché de Ollama.

        Las peticiones reales comparten ese prefijo exacto, así que la primera respuesta ya no
        tiene que procesar miles de tokens en frío.
        """
        try:
            await self.ensure_running()
            model = await self.pick_model(force=True)
            caps = await self.capabilities(model)
            sys_text = system + ("\n/no_think" if model.startswith("qwen3") else "")
            msgs = self._convert(sys_text, [{"role": "user", "content": "Hola"}], "vision" in caps)
            body = {"model": model, "messages": msgs, "stream": False, "think": False,
                    "keep_alive": get_config().llm.local_keep_alive,
                    "options": {"num_ctx": get_config().llm.local_context, "num_predict": 1}}
            otools = self._tools(tools) if "tools" in caps or not caps else []
            if otools:
                body["tools"] = otools
            t0 = time.time()
            await self._post("/api/chat", body, timeout=900)
            log.info("Modelo local %s precalentado en %.1fs", model, time.time() - t0)
        except Exception as e:
            log.warning("No se pudo precalentar el modelo local: %s", e)

    async def simple(self, *, system: str, prompt: str, max_tokens: int = 4000, effort: str = "low") -> str:
        res = await self.stream_turn(system=system, messages=[{"role": "user", "content": prompt}], tools=[],
                                     effort=effort, max_tokens=max_tokens)
        return res.text

    async def health(self) -> dict[str, Any]:
        if not await self.running():
            if ollama_exe():
                return {"ok": False, "status": "ollama_detenido", "detail": "Ollama no está en marcha (se arrancará al usarlo)",
                        "local": True}
            return {"ok": False, "status": "sin_ollama", "detail": "Ollama no está instalado", "local": True}
        try:
            names = {m["name"] for m in await self.installed()}
        except Exception as e:
            return {"ok": False, "status": "error", "detail": str(e)[:200], "local": True}
        model = self.model
        if model not in names and f"{model}:latest" not in names:
            return {"ok": False, "status": "modelo_no_descargado", "detail": f"Falta descargar {model}", "local": True}
        active = await self.pick_model()
        cat = next((m for m in CATALOG if m["id"] == active), None)
        return {"ok": True, "status": "operativo", "local": True, "model": active,
                "display_name": f"{cat['name'] if cat else active} · local", "route_reason": self.route_reason,
                "capabilities": await self.capabilities(active)}

    # ------------------------------------------------------------------ gestión de modelos

    async def overview(self) -> dict[str, Any]:
        running = await self.running()
        version = None
        installed: list[dict[str, Any]] = []
        loaded: list[str] = []
        loaded_vram: dict[str, float] = {}
        if running:
            try:
                version = (await self._get("/api/version")).get("version")
                for m in await self.installed():
                    installed.append({"name": m["name"], "size_gb": round(m.get("size", 0) / 1024**3, 1),
                                      "family": (m.get("details") or {}).get("family", ""),
                                      "params": (m.get("details") or {}).get("parameter_size", ""),
                                      "quant": (m.get("details") or {}).get("quantization_level", "")})
                ps = (await self._get("/api/ps")).get("models", [])
                loaded = [m["name"] for m in ps]
                loaded_vram = {m["name"]: round(m.get("size_vram", 0) / 1024**3, 2) for m in ps}
            except Exception as e:
                log.warning("Ollama overview: %s", e)
        names = {m["name"] for m in installed}
        catalog = [{**c, "installed": c["id"] in names} for c in CATALOG]
        cfg = get_config().llm
        active = (await self.pick_model()) if running else self.model
        return {"installed_app": bool(ollama_exe()), "running": running, "version": version,
                "models": installed, "loaded": loaded, "loaded_vram": loaded_vram, "catalog": catalog,
                "selected": self.model,
                "adaptive": cfg.local_adaptive, "light": cfg.local_light_model, "active_model": active,
                "route_reason": self.route_reason, "last_stats": self.last_stats}

    async def _pull_one(self, source: str, progress, stall_s: float | None) -> None:
        last_change, last_completed = time.time(), -1
        async with httpx.AsyncClient(timeout=httpx.Timeout(None, connect=10)) as c:
            async with c.stream("POST", self.url + "/api/pull", json={"model": source, "stream": True}) as r:
                if r.status_code >= 400:
                    raise RuntimeError((await r.aread()).decode("utf-8", "replace")[:300])
                lines = r.aiter_lines()
                while True:
                    try:
                        line = await asyncio.wait_for(lines.__anext__(), timeout=stall_s or 3600)
                    except StopAsyncIteration:
                        break
                    except asyncio.TimeoutError:
                        raise TimeoutError("descarga atascada")
                    if not line.strip():
                        continue
                    ev = json.loads(line)
                    if ev.get("error"):
                        raise RuntimeError(ev["error"])
                    completed = ev.get("completed")
                    if completed is not None and completed != last_completed:
                        last_completed, last_change = completed, time.time()
                    elif stall_s and time.time() - last_change > stall_s:
                        raise TimeoutError("descarga atascada")
                    await progress(ev.get("status", ""), completed, ev.get("total"))

    async def pull(self, model: str, progress) -> None:
        """Descarga un modelo informando del progreso: progress(status, completed, total).

        Si el registro oficial de Ollama no avanza (algunas redes bloquean su CDN), se usa la
        copia GGUF de Hugging Face y se le da el nombre corto del catálogo.
        """
        await self.ensure_running()
        entry = next((m for m in CATALOG if m["id"] == model), None)
        sources = [model] + ([entry["hf"]] if entry and entry.get("hf") else [])
        last: Exception | None = None
        for i, src in enumerate(sources):
            has_fallback = i < len(sources) - 1
            try:
                if i > 0:
                    await progress("Registro oficial lento: descargando desde Hugging Face…", 0, 0)
                await self._pull_one(src, progress, stall_s=75 if has_fallback else None)
                if src != model:
                    await self._post("/api/copy", {"source": src, "destination": model})
                    async with httpx.AsyncClient(timeout=30) as c:
                        await c.request("DELETE", self.url + "/api/delete", json={"model": src})
                self._caps.pop(model, None)
                return
            except (TimeoutError, RuntimeError, httpx.HTTPError) as e:
                last = e
                log.warning("Descarga de %s desde %s falló: %s", model, src, e)
        raise RuntimeError(f"No se pudo descargar {model}: {last}")

    async def benchmark(self, model: str) -> dict[str, Any]:
        """Prueba rápida: velocidad y capacidad de usar herramientas en español."""
        await self.ensure_running()
        tool = {"type": "function", "function": {"name": "get_weather", "description": "Tiempo actual en una ciudad",
                                                 "parameters": {"type": "object", "properties": {"city": {"type": "string"}},
                                                                "required": ["city"]}}}
        t0 = time.time()
        body = {"model": model, "stream": False, "keep_alive": get_config().llm.local_keep_alive,
                "options": {"num_ctx": 4096, "num_predict": 300},
                "messages": [{"role": "user", "content": "¿Qué tiempo hace ahora en Sevilla?"}], "tools": [tool]}
        body["think"] = False
        if model.startswith("qwen3"):
            body["messages"] = [{"role": "system", "content": "/no_think"}] + body["messages"]
        r1 = await self._post("/api/chat", body, timeout=600)
        calls = (r1.get("message") or {}).get("tool_calls") or []
        tool_ok = bool(calls) and calls[0].get("function", {}).get("name") == "get_weather"
        body2 = {**body, "tools": [], "messages": body["messages"][:-1] + [{"role": "user", "content":
                 "Preséntate en dos frases como JARVIS, el asistente personal del usuario. Tutéale."}]}
        r2 = await self._post("/api/chat", body2, timeout=600)
        ev_s = (r2.get("eval_duration") or 0) / 1e9
        sample, _ = ThinkFilter(implicit_open=model.startswith("qwen3")).feed(
            (r2.get("message") or {}).get("content", ""), final=True)
        return {"model": model, "tool_calling": tool_ok, "load_s": round((r1.get("load_duration") or 0) / 1e9, 1),
                "tokens_per_s": round(r2.get("eval_count", 0) / ev_s, 1) if ev_s else None,
                "sample": sample.strip()[:400],
                "total_s": round(time.time() - t0, 1)}
