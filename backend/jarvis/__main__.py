"""Punto de entrada de JARVIS.

    python -m jarvis run [--tray] [--no-browser]   Inicia el servicio (y la interfaz)
    python -m jarvis setup                         Asistente de credenciales y configuración
    python -m jarvis doctor                        Diagnóstico de dependencias
    python -m jarvis autostart on|off              Inicio automático con Windows
    python -m jarvis shortcut                      Crea el acceso directo del escritorio
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import logging
import logging.handlers
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

from .config import DATA_DIR, PROJECT_ROOT, get_config, load_config, update_config


def setup_logging(console: bool = True) -> None:
    (DATA_DIR / "logs").mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S")
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    fh = logging.handlers.RotatingFileHandler(DATA_DIR / "logs" / "jarvis.log", maxBytes=5_000_000, backupCount=5,
                                              encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)
    if console and sys.stdout:
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(fmt)
        root.addHandler(sh)
    for noisy in ("httpx", "httpcore", "httpx2", "httpcore2", "telegram.ext", "apscheduler", "faster_whisper"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def open_ui() -> None:
    cfg = get_config().server
    url = f"http://127.0.0.1:{cfg.port}/"
    if cfg.app_window:
        from .system_integration import find_chromium

        browser = find_chromium()
        if browser:
            profile = DATA_DIR / "app-window"
            subprocess.Popen([browser, f"--app={url}", f"--user-data-dir={profile}", "--window-size=1500,940",
                              "--no-first-run", "--no-default-browser-check", "--disable-features=Translate"],
                             close_fds=True)
            return
    webbrowser.open(url)


def run_server(tray: bool, browser: bool) -> None:
    import uvicorn

    cfg = load_config()
    setup_logging(console=not tray or bool(sys.stdout))
    log = logging.getLogger("jarvis")
    if port_in_use(cfg.server.host, cfg.server.port):
        log.info("JARVIS ya está en ejecución; abriendo la interfaz.")
        open_ui()
        return

    from .server import app

    config = uvicorn.Config(app, host=cfg.server.host, port=cfg.server.port, log_config=None, access_log=False,
                            ws_ping_interval=20, ws_ping_timeout=30)
    server = uvicorn.Server(config)
    app.state.server = server  # permite el apagado ordenado vía /api/shutdown

    def opener():
        for _ in range(120):
            if server.started:
                if browser:
                    open_ui()
                return
            time.sleep(0.25)

    threading.Thread(target=opener, daemon=True).start()

    if not tray:
        server.run()
        return

    t = threading.Thread(target=server.run, daemon=True, name="uvicorn")
    t.start()
    from .tray import run_tray

    run_tray(server, open_ui, t)
    server.should_exit = True
    t.join(timeout=10)


def setup_wizard() -> None:
    from . import secrets

    load_config()
    print("\n  J.A.R.V.I.S. — Asistente de configuración")
    print("  Las credenciales se guardan cifradas en el Administrador de credenciales de Windows.")
    print("  Pulsa Enter para mantener el valor actual / omitir.\n")

    def ask_secret(name: str, label: str, help_: str) -> None:
        state = "configurada" if secrets.has_secret(name) else "NO configurada"
        print(f"• {label} ({state})\n  {help_}")
        v = getpass.getpass("  Valor (no se muestra): ").strip()
        if v:
            secrets.set_secret(name, v)
            print("  ✓ Guardada.\n")
        else:
            print("  — Sin cambios.\n")

    ask_secret("anthropic_api_key", "API key de Anthropic (obligatoria)",
               "Créala en https://console.anthropic.com/settings/keys")
    ask_secret("telegram_bot_token", "Token del bot de Telegram (opcional)",
               "Habla con @BotFather en Telegram → /newbot y copia el token.")
    if secrets.has_secret("telegram_bot_token") and not secrets.has_secret("telegram_pin_hash"):
        pin = getpass.getpass("• PIN numérico (4-12 dígitos) para aprobar acciones peligrosas desde Telegram: ").strip()
        if pin:
            try:
                secrets.set_pin(pin)
                print("  ✓ PIN guardado.\n")
            except ValueError as e:
                print(f"  ✗ {e}\n")
    ask_secret("elevenlabs_api_key", "API key de ElevenLabs (opcional, voz premium)",
               "https://elevenlabs.io → Profile → API Keys. Si no la pones se usan voces neuronales de Microsoft gratis.")
    name = input(f"• ¿Cómo te llamo? [{get_config().user.name}]: ").strip()
    if name:
        update_config({"user": {"name": name}})
    print("\n  Listo. Inicia JARVIS con Jarvis.cmd o el acceso directo del escritorio.")
    print("  Para emparejar Telegram: Configuración → Telegram → 'Emparejar móvil'.\n")


def main() -> None:
    sys.path.insert(0, str(PROJECT_ROOT / "backend"))
    p = argparse.ArgumentParser(prog="jarvis")
    sub = p.add_subparsers(dest="cmd")
    r = sub.add_parser("run")
    r.add_argument("--tray", action="store_true", help="Icono en la bandeja del sistema")
    r.add_argument("--no-browser", action="store_true", help="No abrir la interfaz al arrancar")
    sub.add_parser("setup")
    sub.add_parser("doctor")
    a = sub.add_parser("autostart")
    a.add_argument("state", choices=["on", "off"])
    sub.add_parser("shortcut")
    sub.add_parser("overlay")
    e = sub.add_parser("export", help="Crea un paquete para instalar JARVIS igual en otro PC")
    e.add_argument("--sin-datos", action="store_true", help="No incluir memoria ni conversaciones")
    sub.add_parser("export-config", help="Guarda tu configuración (sin secretos) en perfil/ para subirla al repositorio")
    ic = sub.add_parser("import-config")
    ic.add_argument("path")
    mo = sub.add_parser("models", help="Elige y descarga los modelos de IA local según la GPU")
    mo.add_argument("--plan", action="store_true")
    args = p.parse_args()

    if args.cmd in (None, "run"):
        tray = getattr(args, "tray", False)
        browser = not getattr(args, "no_browser", False) and get_config().server.open_browser_on_start
        run_server(tray, browser)
    elif args.cmd == "setup":
        setup_wizard()
    elif args.cmd == "doctor":
        from .system_integration import doctor

        load_config()
        marks = {"ok": "✓", "warn": "!", "error": "✗", "info": "·"}
        for c in doctor():
            print(f"  {marks[c['level']]} {c['name']}: {c['detail']}")
    elif args.cmd == "autostart":
        from .system_integration import set_autostart

        print("Inicio automático:", "activado" if set_autostart(args.state == "on") else "desactivado")
    elif args.cmd == "export":
        from .portable import export_package

        z = export_package(include_data=not args.sin_datos)
        print(f"\n  Paquete creado: {z}  ({z.stat().st_size / 1e6:.1f} MB)")
        print("  Cópialo al otro PC, descomprímelo (mejor en C:\\JARVIS) y haz doble clic en INSTALAR.cmd\n")
    elif args.cmd == "export-config":
        import yaml

        load_config()
        out = PROJECT_ROOT / "perfil" / "config.portable.yaml"
        out.parent.mkdir(exist_ok=True)
        cfg = get_config().model_dump(mode="json")
        cfg.get("security", {}).pop("allowed_roots", None)  # rutas propias de este equipo
        out.write_text("# Configuración de JARVIS (sin secretos). La aplica INSTALAR.cmd en otro PC.\n"
                       + yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")
        print(f"  Configuración guardada en {out}")
    elif args.cmd == "import-config":
        from .portable import import_config

        r = import_config(Path(args.path))
        print("  Configuración importada y adaptada a este equipo.")
        print(f"  Modelos locales: {r['models']['main']} / {r['models']['light']} ({r['models']['reason']})")
    elif args.cmd == "models":
        from .portable import setup_models

        setup_models(plan_only=args.plan)
    elif args.cmd == "overlay":
        from .overlay import main as overlay_main

        overlay_main()
    elif args.cmd == "shortcut":
        from .system_integration import create_desktop_shortcut

        print("Acceso directo creado:", create_desktop_shortcut())


if __name__ == "__main__":
    main()
