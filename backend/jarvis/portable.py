"""Llevar JARVIS a otro PC exactamente igual.

    python -m jarvis export [--sin-datos]   Crea JARVIS-Setup-AAAAMMDD.zip (código, interfaz compilada,
                                            configuración y, por defecto, tu memoria y conversaciones)
    python -m jarvis import-config RUTA     Aplica una configuración exportada adaptándola a este equipo
    python -m jarvis models [--plan]        Elige los modelos de IA local según la GPU y los descarga
                                            (y deja precargados Whisper y «Hey JARVIS»)

Lo que NO viaja en el paquete (por seguridad o por tamaño): las credenciales (API keys, token de
Telegram, PIN — están cifradas por Windows y se vuelven a introducir), los modelos (se descargan
solos) y los datos propios de este equipo (micrófono, carpetas, registros).
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
import platform
import sqlite3
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import yaml

from . import __version__
from .config import DATA_DIR, PROJECT_ROOT, AppConfig, SecurityConfig, get_config, load_config, save_config

# Carpetas y archivos que nunca se copian
EXCLUDE_DIRS = {".venv", "node_modules", "__pycache__", ".pytest_cache", "exportar", ".git"}
EXCLUDE_DATA = {"logs", "models", "audio", "uploads", "app-window", "browser-profile", "workspace"}
EXCLUDE_FILES = {".session_token", "jarvis.db", "jarvis.db-wal", "jarvis.db-shm", "pip-install.log",
                 "pip-voice.log", "voice-test.log"}

# Ajustes que dependen del equipo y no se copian tal cual
MACHINE_KEYS = {
    ("security", "allowed_roots"), ("voice", "mic_label"), ("voice", "output_device"),
    ("voice", "stt_device"), ("voice", "stt_model"), ("llm", "local_model"), ("llm", "local_light_model"),
    ("database_url",),
}


def _hardware() -> dict[str, Any]:
    info: dict[str, Any] = {"os": platform.platform(), "python": platform.python_version(), "gpu": None, "vram_gb": 0.0}
    try:
        import pynvml

        pynvml.nvmlInit()
        h = pynvml.nvmlDeviceGetHandleByIndex(0)
        name = pynvml.nvmlDeviceGetName(h)
        info["gpu"] = name.decode() if isinstance(name, bytes) else name
        info["vram_gb"] = round(pynvml.nvmlDeviceGetMemoryInfo(h).total / 1024**3, 1)
    except Exception:
        pass
    try:
        import psutil

        info["ram_gb"] = round(psutil.virtual_memory().total / 1024**3, 1)
    except Exception:
        pass
    return info


# ------------------------------------------------------------------ exportar

def _backup_db(dest: Path) -> bool:
    """Copia coherente de la base de datos aunque JARVIS esté en marcha (API de backup de SQLite)."""
    src = DATA_DIR / "jarvis.db"
    if not src.exists():
        return False
    a, b = sqlite3.connect(src), sqlite3.connect(dest)
    try:
        a.backup(b)
    finally:  # en Windows hay que cerrar explícitamente o el archivo queda bloqueado
        b.close()
        a.close()
    return True


def export_package(include_data: bool = True, out_dir: Path | None = None) -> Path:
    load_config()
    out_dir = out_dir or PROJECT_ROOT / "exportar"
    out_dir.mkdir(exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M")
    zpath = out_dir / f"JARVIS-Setup-{stamp}.zip"
    manifest = {
        "app": "J.A.R.V.I.S.", "version": __version__, "created": dt.datetime.now().isoformat(timespec="seconds"),
        "source_hardware": _hardware(), "includes_data": include_data,
        "llm": {"provider": get_config().llm.provider, "local_model": get_config().llm.local_model,
                "light_model": get_config().llm.local_light_model},
    }
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for root, dirs, files in os.walk(PROJECT_ROOT):
            rel_root = Path(root).relative_to(PROJECT_ROOT)
            parts = rel_root.parts
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS
                       and not (parts[:1] == ("data",) and len(parts) == 1 and d in EXCLUDE_DATA)
                       and not (rel_root == Path(".") and d == "data")]
            for f in files:
                if f in EXCLUDE_FILES or f.endswith((".pyc", ".log")):
                    continue
                z.write(Path(root) / f, "JARVIS" / rel_root / f)
        # data/: configuración portable, scripts revisados y (opcional) memoria y conversaciones
        cfg_yaml = yaml.safe_dump(get_config().model_dump(mode="json"), allow_unicode=True, sort_keys=False)
        z.writestr("JARVIS/data/config.portable.yaml", cfg_yaml)
        scripts = DATA_DIR / "scripts"
        if scripts.exists():
            for f in scripts.glob("*"):
                if f.is_file():
                    z.write(f, f"JARVIS/data/scripts/{f.name}")
        if include_data:
            with tempfile.TemporaryDirectory() as td:
                tmp = Path(td) / "jarvis.db"
                if _backup_db(tmp):
                    z.write(tmp, "JARVIS/data/jarvis.db")
        z.writestr("JARVIS/data/MANIFEST.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    return zpath


# ------------------------------------------------------------------ importar configuración

def recommend_models(hw: dict[str, Any] | None = None) -> dict[str, Any]:
    """Modelos locales y reconocimiento de voz adecuados a la GPU de este equipo."""
    hw = hw or _hardware()
    vram = hw.get("vram_gb") or 0
    if vram >= 10:
        main, light, why = "gemma4:12b", "qwen3:8b", "GPU de 10 GB o más: el modelo más capaz"
    elif vram >= 7:
        main, light, why = "qwen3:8b", "qwen3:4b", "GPU de 7-10 GB"
    elif vram >= 4:
        main, light, why = "qwen3:4b", "qwen3:4b", "GPU modesta"
    else:
        main, light, why = "qwen3:4b", "qwen3:4b", "sin GPU NVIDIA: funcionará en la CPU (más lento)"
    stt = {"stt_device": "auto", "stt_model": "large-v3-turbo"} if vram >= 4 else {"stt_device": "cpu", "stt_model": "small"}
    return {"main": main, "light": light, "reason": why, "vram_gb": vram, "gpu": hw.get("gpu"), **stt}


def import_config(src: Path) -> dict[str, Any]:
    """Aplica una configuración exportada, conservando lo que depende de este equipo."""
    load_config()
    incoming = yaml.safe_load(Path(src).read_text(encoding="utf-8")) or {}
    for path in MACHINE_KEYS:
        node = incoming
        for k in path[:-1]:
            node = node.get(k, {}) if isinstance(node, dict) else {}
        if isinstance(node, dict):
            node.pop(path[-1], None)
    current = get_config().model_dump(mode="json")

    def merge(a: dict, b: dict) -> dict:
        for k, v in b.items():
            if isinstance(v, dict) and isinstance(a.get(k), dict):
                merge(a[k], v)
            else:
                a[k] = v
        return a

    merged = merge(current, incoming)
    rec = recommend_models()
    merged.setdefault("llm", {}).update(local_model=rec["main"], local_light_model=rec["light"])
    merged.setdefault("voice", {}).update(stt_device=rec["stt_device"], stt_model=rec["stt_model"],
                                          mic_label="", output_device="")
    merged.setdefault("security", {})["allowed_roots"] = SecurityConfig().allowed_roots  # rutas de ESTE usuario
    cfg = AppConfig.model_validate(merged)
    save_config(cfg)
    return {"models": rec, "telegram_users": cfg.telegram.allowed_user_ids}


# ------------------------------------------------------------------ modelos

async def _pull_all(models: list[str]) -> None:
    from .llm.ollama_provider import OllamaProvider

    prov = OllamaProvider.instance()
    await prov.ensure_running()
    have = {m["name"] for m in await prov.installed()}
    for m in dict.fromkeys(models):
        if m in have or f"{m}:latest" in have:
            print(f"  ✓ {m} ya está descargado")
            continue
        print(f"  ↓ Descargando {m} (puede tardar varios minutos)…")
        last = {"pct": -10}

        async def progress(status, completed, total):
            if total:
                pct = int(completed * 100 / total)
                if pct >= last["pct"] + 10:
                    last["pct"] = pct
                    print(f"    {pct:3d} %  ({completed / 1e9:.1f} / {total / 1e9:.1f} GB)")
            elif status and "Hugging Face" in status:
                print(f"    {status}")

        await prov.pull(m, progress)
        print(f"  ✓ {m} listo")


def setup_models(plan_only: bool = False) -> dict[str, Any]:
    load_config()
    rec = recommend_models()
    print(f"  GPU: {rec['gpu'] or 'ninguna NVIDIA'} ({rec['vram_gb']} GB) → {rec['reason']}")
    print(f"  IA local: principal {rec['main']} · ligero {rec['light']} · voz: Whisper {rec['stt_model']} ({rec['stt_device']})")
    if plan_only:
        return rec
    from .config import update_config

    update_config({"llm": {"local_model": rec["main"], "local_light_model": rec["light"],
                           "local_adaptive": rec["main"] != rec["light"]},
                   "voice": {"stt_device": rec["stt_device"], "stt_model": rec["stt_model"]}})
    try:
        asyncio.run(_pull_all([rec["main"], rec["light"]]))
    except Exception as e:
        print(f"  ! No se pudieron descargar los modelos ahora ({e}). Podrás hacerlo desde Configuración → Inteligencia.")
    # Precarga de la voz para que el primer uso sea instantáneo
    try:
        print("  ↓ Preparando reconocimiento de voz (Whisper)…")
        from .voice import stt

        stt.load_model()
        print(f"  ✓ Whisper listo ({stt.info().get('device')})")
    except Exception as e:
        print(f"  ! Whisper se descargará en el primer uso ({e})")
    try:
        from .voice.wakeword import ensure_models

        ensure_models(get_config().voice.wake_word_model)
        print("  ✓ «Hey JARVIS» listo")
    except Exception as e:
        print(f"  ! Palabra de activación pendiente ({e})")
    return rec
