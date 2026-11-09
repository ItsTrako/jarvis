"""Configuración de JARVIS.

La configuración NO secreta vive en ``data/config.yaml`` (editable a mano o desde la UI).
Los secretos (API keys, token de Telegram, PIN) viven en el Administrador de
credenciales de Windows a través de ``jarvis.secrets`` — nunca en este fichero.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("JARVIS_DATA_DIR", PROJECT_ROOT / "data")).resolve()
CONFIG_PATH = DATA_DIR / "config.yaml"
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"

HOME = Path.home()


def _default_roots() -> list[str]:
    roots = [DATA_DIR / "workspace"]
    for name in ("Documents", "Desktop", "Downloads"):
        p = HOME / name
        if p.exists():
            roots.append(p)
    # OneDrive redirige a menudo Documentos/Escritorio
    onedrive = os.environ.get("OneDrive")
    if onedrive:
        for name in ("Documents", "Documentos", "Desktop", "Escritorio"):
            p = Path(onedrive) / name
            if p.exists():
                roots.append(p)
    return [str(p) for p in roots]


class ServerConfig(BaseModel):
    host: str = "127.0.0.1"  # Solo localhost. No se expone a la red.
    port: int = 8765
    open_browser_on_start: bool = True
    app_window: bool = True  # Abrir como ventana de aplicación (Edge --app)


class LLMConfig(BaseModel):
    # auto: Claude si hay API key; si no, el modelo local gratuito (Ollama)
    provider: Literal["auto", "anthropic", "ollama"] = "auto"
    model: str = "claude-opus-5-5"
    # --- IA local (Ollama) ---
    ollama_url: str = "http://127.0.0.1:11434"
    local_model: str = "gemma4:12b"
    # Modo adaptativo: si la GPU está ocupada (juegos, etc.) usa el modelo ligero automáticamente
    local_adaptive: bool = True
    local_light_model: str = "qwen3:8b"
    local_context: int = 16384
    local_thinking: Literal["auto", "on", "off"] = "auto"  # auto: razona en tareas complejas/segundo plano
    local_keep_alive: str = "30m"
    effort: Literal["low", "medium", "high", "xhigh", "max"] = "medium"
    background_effort: Literal["low", "medium", "high", "xhigh", "max"] = "high"
    max_tokens: int = 32000
    max_tool_iterations: int = 40
    web_search: bool = True
    web_fetch: bool = True
    server_fallbacks: bool = True  # fallbacks:"default" ante rechazos de clasificadores
    progress_updates: bool = True  # thinking.display="updates"
    compact_after_tokens: int = 180_000  # compactación simple de conversaciones largas


class SecurityConfig(BaseModel):
    # Acceso total: todos los discos, cualquier programa y sin confirmaciones para órdenes dadas en el PC
    # (texto o voz). Siguen bloqueados: desactivar protecciones del sistema / elevar privilegios, y las
    # acciones peligrosas que lleguen por Telegram o trabajos automáticos siguen pidiendo confirmación.
    full_access: bool = False
    allowed_roots: list[str] = Field(default_factory=_default_roots)
    # Riesgo a partir del cual se pide confirmación explícita.
    # "sensitive" (recomendado): confirma lo sensible y lo peligroso. "dangerous" nunca
    # puede saltarse: las acciones peligrosas SIEMPRE requieren confirmación.
    confirm_level: Literal["moderate", "sensitive", "dangerous"] = "sensitive"
    confirmation_timeout_s: int = 300
    shell_enabled: bool = True
    shell_timeout_s: int = 120
    app_mode: Literal["start_menu", "allowlist"] = "start_menu"
    app_allowlist: dict[str, str] = Field(default_factory=lambda: {
        "bloc de notas": "notepad.exe",
        "calculadora": "calc.exe",
        "explorador": "explorer.exe",
        "terminal": "wt.exe",
        "paint": "mspaint.exe",
    })
    protected_processes: list[str] = Field(default_factory=lambda: [
        "system", "smss.exe", "csrss.exe", "wininit.exe", "winlogon.exe", "services.exe",
        "lsass.exe", "svchost.exe", "dwm.exe", "explorer.exe", "msmpeng.exe",
        "securityhealthservice.exe", "mpdefendercoreservice.exe", "nissrv.exe",
        "python.exe", "pythonw.exe",
    ])


class TelegramConfig(BaseModel):
    enabled: bool = True
    allowed_user_ids: list[int] = Field(default_factory=list)
    allowed_chat_ids: list[int] = Field(default_factory=list)
    rate_limit_per_minute: int = 12
    require_pin_for_sensitive: bool = True
    voice_replies: bool = False  # responder también con nota de voz
    pin_max_attempts: int = 3


class VoiceConfig(BaseModel):
    stt_engine: Literal["faster-whisper"] = "faster-whisper"
    stt_model: str = "large-v3-turbo"
    stt_device: Literal["auto", "cuda", "cpu"] = "auto"
    stt_language: str = "es"
    tts_engine: Literal["edge", "elevenlabs", "azure"] = "edge"
    # Voz multilingüe de última generación (entonación más humana); habla español nativo
    edge_voice: str = "en-US-AndrewMultilingualNeural"
    edge_rate: str = "+0%"
    edge_pitch: str = "+0Hz"
    elevenlabs_voice_id: str = ""
    elevenlabs_model: str = "eleven_flash_v2_5"
    azure_region: str = "westeurope"
    azure_voice: str = "es-ES-AlvaroNeural"
    azure_style: str = ""
    auto_speak: bool = True
    mic_label: str = ""  # parte del nombre del micrófono preferido (p. ej. "DGM20"); vacío = predeterminado
    wake_word_enabled: bool = True  # escucha permanente de «Hey JARVIS» (desactivable en la interfaz)
    wake_word_model: str = "hey_jarvis"
    wake_word_threshold: float = 0.5
    follow_up_s: float = 8.0       # tras responder, sigue escuchando este tiempo sin necesidad de «Hey JARVIS»
    end_silence_s: float = 1.0     # silencio que marca el final de tu frase
    output_device: str = ""        # altavoces/cascos (vacío = predeterminado de Windows)


class DesktopConfig(BaseModel):
    """JARVIS en el escritorio: esfera animada transparente sobre el fondo de pantalla."""
    overlay: bool = False
    position: Literal["bottom-right", "top-right", "bottom-left", "top-left", "center"] = "bottom-right"
    size: int = 300
    layer: Literal["desktop", "top"] = "desktop"  # desktop: detrás de tus ventanas · top: siempre encima
    show_text: bool = True
    opacity: float = 1.0


class UserConfig(BaseModel):
    name: str = ""
    language: str = "es"
    timezone: str = "Europe/Madrid"
    city: str = ""              # vacío: se detecta sola por la conexión (auto_location)
    auto_location: bool = True  # ubicación aproximada por IP para el tiempo y lo cercano
    auto_learn: bool = True     # aprende datos sobre ti de las conversaciones y los guarda en memoria


class AppConfig(BaseModel):
    server: ServerConfig = Field(default_factory=ServerConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)
    voice: VoiceConfig = Field(default_factory=VoiceConfig)
    user: UserConfig = Field(default_factory=UserConfig)
    desktop: DesktopConfig = Field(default_factory=DesktopConfig)
    database_url: str = ""  # vacío = SQLite en data/jarvis.db. Admite postgresql+asyncpg://


_lock = threading.RLock()
_config: AppConfig | None = None


def ensure_dirs() -> None:
    for sub in ("", "workspace", "logs", "scripts", "uploads", "audio", "models"):
        (DATA_DIR / sub).mkdir(parents=True, exist_ok=True)


def load_config() -> AppConfig:
    global _config
    with _lock:
        ensure_dirs()
        if CONFIG_PATH.exists():
            raw = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
            _config = AppConfig.model_validate(raw)
        else:
            _config = AppConfig()
        save_config(_config)  # normaliza y añade claves nuevas
        return _config


def get_config() -> AppConfig:
    return _config or load_config()


def save_config(cfg: AppConfig) -> None:
    global _config
    with _lock:
        ensure_dirs()
        header = (
            "# Configuración de J.A.R.V.I.S. (no contiene secretos).\n"
            "# Los secretos se guardan en el Administrador de credenciales de Windows.\n"
            "# Edita con cuidado o usa la pantalla Configuración de la interfaz.\n"
        )
        CONFIG_PATH.write_text(
            header + yaml.safe_dump(cfg.model_dump(mode="json"), allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        _config = cfg


def update_config(patch: dict[str, Any]) -> AppConfig:
    """Fusión profunda de un parche sobre la configuración actual (validada)."""
    current = get_config().model_dump(mode="json")

    def merge(a: dict, b: dict) -> dict:
        for k, v in b.items():
            if isinstance(v, dict) and isinstance(a.get(k), dict):
                merge(a[k], v)
            else:
                a[k] = v
        return a

    new_cfg = AppConfig.model_validate(merge(current, patch))
    save_config(new_cfg)
    return new_cfg
