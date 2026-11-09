"""Integración con Windows: inicio automático (visible y configurable) y diagnóstico."""

from __future__ import annotations

import importlib
import os
import shutil
import sys
from pathlib import Path
from typing import Any

from .config import DATA_DIR, FRONTEND_DIST, PROJECT_ROOT, get_config
from .secrets import has_secret

STARTUP_DIR = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
SHORTCUT = STARTUP_DIR / "JARVIS.lnk"


def find_chromium() -> str | None:
    """Ruta de Microsoft Edge o Google Chrome (para la ventana de app y el navegador del agente)."""
    candidates: list[str] = []
    try:
        import winreg

        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            for exe in ("msedge.exe", "chrome.exe"):
                try:
                    k = winreg.OpenKey(hive, rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{exe}")
                    candidates.append(winreg.QueryValueEx(k, "")[0])
                except OSError:
                    pass
    except ImportError:
        pass
    for base in (os.environ.get("ProgramFiles(x86)", ""), os.environ.get("ProgramFiles", ""), os.environ.get("LOCALAPPDATA", "")):
        candidates += [str(Path(base) / "Microsoft" / "Edge" / "Application" / "msedge.exe"),
                       str(Path(base) / "Google" / "Chrome" / "Application" / "chrome.exe")]
    candidates += [shutil.which("msedge") or "", shutil.which("chrome") or ""]
    return next((c for c in candidates if c and Path(c).exists()), None)


def _pythonw() -> str:
    exe = Path(sys.executable)
    w = exe.with_name("pythonw.exe")
    return str(w if w.exists() else exe)


def create_shortcut(path: Path, args: str, description: str) -> None:
    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()  # necesario cuando se llama desde un hilo de trabajo (API)
    shell = win32com.client.Dispatch("WScript.Shell")
    sc = shell.CreateShortCut(str(path))
    sc.TargetPath = _pythonw()
    sc.Arguments = args
    sc.WorkingDirectory = str(PROJECT_ROOT / "backend")
    sc.Description = description
    icon = PROJECT_ROOT / "frontend" / "public" / "jarvis.ico"
    if icon.exists():
        sc.IconLocation = str(icon)
    sc.save()


def autostart_enabled() -> bool:
    return SHORTCUT.exists()


def set_autostart(enabled: bool) -> bool:
    if enabled:
        STARTUP_DIR.mkdir(parents=True, exist_ok=True)
        create_shortcut(SHORTCUT, "-m jarvis run --tray --no-browser",
                        "Inicia J.A.R.V.I.S. en segundo plano al iniciar sesión")
    else:
        SHORTCUT.unlink(missing_ok=True)
    return autostart_enabled()


def create_desktop_shortcut() -> Path:
    desktop = Path(os.environ.get("USERPROFILE", "")) / "Desktop"
    onedrive = os.environ.get("OneDrive")
    if onedrive and (Path(onedrive) / "Desktop").exists():
        desktop = Path(onedrive) / "Desktop"
    if onedrive and (Path(onedrive) / "Escritorio").exists():
        desktop = Path(onedrive) / "Escritorio"
    path = desktop / "J.A.R.V.I.S..lnk"
    create_shortcut(path, "-m jarvis run --tray", "Abrir J.A.R.V.I.S.")
    return path


def doctor() -> list[dict[str, Any]]:
    """Comprobación de dependencias y configuración. Devuelve una lista de checks."""
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str = "", level: str = "error") -> None:
        checks.append({"name": name, "ok": ok, "detail": detail, "level": "ok" if ok else level})

    add("Python ≥ 3.11", sys.version_info >= (3, 11), sys.version.split()[0])
    for mod, label, lvl in [("anthropic", "SDK de Anthropic", "error"), ("fastapi", "FastAPI", "error"),
                            ("telegram", "python-telegram-bot", "error"), ("faster_whisper", "faster-whisper (voz)", "warn"),
                            ("edge_tts", "edge-tts (voz)", "warn"), ("playwright", "Playwright (navegador)", "warn"),
                            ("openwakeword", "openWakeWord (palabra de activación)", "warn"),
                            ("win32api", "pywin32", "error"), ("pyautogui", "pyautogui (escritorio)", "warn")]:
        try:
            m = importlib.import_module(mod)
            add(label, True, getattr(m, "__version__", "instalado"))
        except Exception as e:
            add(label, False, str(e)[:120], lvl)
    add("ffmpeg", bool(shutil.which("ffmpeg")), shutil.which("ffmpeg") or "No encontrado (necesario para notas de voz de Telegram)", "warn")
    add("Interfaz compilada", (FRONTEND_DIST / "index.html").exists(), str(FRONTEND_DIST), "error")
    add("API key de Anthropic", has_secret("anthropic_api_key"),
        "Opcional si usas la IA local gratuita (Configuración → Inteligencia)", "warn")
    from .llm.ollama_provider import ollama_exe

    add("Ollama (IA local gratuita)", bool(ollama_exe()), ollama_exe() or "No instalado: https://ollama.com/download", "warn")
    add("Token de Telegram", has_secret("telegram_bot_token"), "Opcional: necesario para usar JARVIS desde el móvil", "warn")
    add("Usuarios de Telegram autorizados", bool(get_config().telegram.allowed_user_ids), "Empareja tu móvil desde Configuración → Telegram", "warn")
    add("PIN de Telegram", has_secret("telegram_pin_hash"), "Necesario para aprobar acciones peligrosas desde el móvil", "warn")
    try:
        import pynvml

        pynvml.nvmlInit()
        add("GPU NVIDIA (aceleración de voz)", True, f"{pynvml.nvmlDeviceGetCount()} GPU")
    except Exception:
        add("GPU NVIDIA (aceleración de voz)", False, "Se usará la CPU para el reconocimiento de voz", "warn")
    browser = find_chromium()
    add("Navegador Edge/Chrome (ventana de app y navegador del agente)", bool(browser),
        browser or "No encontrado: se usará el navegador predeterminado", "warn")
    add("Carpeta de datos escribible", os.access(DATA_DIR, os.W_OK), str(DATA_DIR))
    add("Inicio automático", autostart_enabled(), "Opcional", "info")
    return checks


# ------------------------------------------------------------------ JARVIS en el escritorio

_overlay_proc = None


def overlay_sync(restart: bool = False) -> bool:
    """Arranca/detiene la esfera del escritorio según la configuración. Devuelve si está activa."""
    import subprocess

    global _overlay_proc
    running = _overlay_proc is not None and _overlay_proc.poll() is None
    if restart and running:
        _overlay_proc.terminate()
        try:
            _overlay_proc.wait(5)
        except Exception:
            _overlay_proc.kill()
        running = False
    want = get_config().desktop.overlay
    if want and not running:
        _overlay_proc = subprocess.Popen([_pythonw(), "-m", "jarvis", "overlay"], cwd=str(PROJECT_ROOT / "backend"),
                                         creationflags=0x08000000, close_fds=True)
        return True
    if not want and running:
        _overlay_proc.terminate()
        _overlay_proc = None
        return False
    return running
