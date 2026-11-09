"""Ejecución controlada de comandos y scripts revisados.

* ``run_command``: PowerShell sin privilegios de administrador, SIEMPRE con confirmación
  explícita mostrando el comando exacto, con lista de bloqueo, límite de tiempo y salida acotada.
* ``run_script``: solo scripts guardados por el usuario en ``data/scripts`` (revisados).
"""

from __future__ import annotations

import json
import os
import subprocess

from ..config import DATA_DIR, get_config
from ..security import ExecContext, PermissionDenied, Risk, check_shell_command, resolve_path, untrusted
from .base import tool

_NO_WINDOW = 0x08000000


def _run(args: list[str], cwd: str, timeout: int) -> str:
    env = {k: v for k, v in os.environ.items() if not any(
        s in k.upper() for s in ("API_KEY", "TOKEN", "SECRET", "PASSWORD"))}
    try:
        r = subprocess.run(args, cwd=cwd, capture_output=True, timeout=timeout, creationflags=_NO_WINDOW,
                           env=env, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return f"Tiempo límite ({timeout}s) superado; proceso detenido."
    def dec(b: bytes) -> str:
        for enc in ("utf-8", "cp850", "cp1252"):
            try:
                return b.decode(enc)
            except UnicodeDecodeError:
                continue
        return b.decode("utf-8", "replace")
    out, err = dec(r.stdout), dec(r.stderr)
    body = f"Código de salida: {r.returncode}\n--- stdout ---\n{out[-20000:]}"
    if err.strip():
        body += f"\n--- stderr ---\n{err[-8000:]}"
    return untrusted("command_output", body, 30000)


@tool(
    name="run_command",
    description=(
        "Ejecuta un comando de PowerShell en el PC (sin privilegios de administrador). SIEMPRE requiere "
        "confirmación explícita del usuario con el comando exacto. Está bloqueado todo lo que afecte a antivirus, "
        "firewall, cuentas, privilegios, arranque o borrado masivo. Úsalo solo si ninguna herramienta específica "
        "sirve (p. ej. git, npm, pip, compilar o ejecutar tests de un proyecto). El directorio de trabajo debe "
        "estar en una carpeta autorizada."
    ),
    parameters={
        "command": {"type": "string"},
        "cwd": {"type": "string", "description": "Directorio de trabajo (carpeta autorizada)"},
        "timeout_s": {"type": "integer"},
        "reason": {"type": "string", "description": "Por qué es necesario (se muestra al usuario)"},
    },
    required=["command"], risk=Risk.DANGEROUS, category="sistema", blocking=True, timeout_s=900,
    enabled_fn=lambda: get_config().security.shell_enabled,
    summary_fn=lambda p: f"Ejecutar en PowerShell: {p.get('command')}" + (f"  — motivo: {p['reason']}" if p.get("reason") else ""),
)
def run_command(params: dict, ctx: ExecContext) -> str:
    cmd = params["command"]
    check_shell_command(cmd)
    cwd = str(resolve_path(params.get("cwd") or str(DATA_DIR / "workspace"), must_exist=True))
    timeout = min(int(params.get("timeout_s") or get_config().security.shell_timeout_s), 840)
    return _run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                 "-Command", cmd], cwd, timeout)


@tool(
    name="list_scripts",
    description="Lista los scripts revisados por el usuario disponibles en data/scripts (.ps1, .py, .bat).",
    category="automatizacion",
)
def list_scripts(params: dict, ctx: ExecContext) -> str:
    folder = DATA_DIR / "scripts"
    items = []
    for f in sorted(folder.glob("*")):
        if f.suffix.lower() in (".ps1", ".py", ".bat", ".cmd"):
            first = ""
            try:
                first = next((l.strip("#:/ ").strip() for l in f.read_text("utf-8", "ignore").splitlines() if l.strip()), "")
            except Exception:
                pass
            items.append({"name": f.name, "description": first[:150]})
    return json.dumps({"folder": str(folder), "scripts": items}, ensure_ascii=False)


@tool(
    name="run_script",
    description=(
        "Ejecuta uno de los scripts revisados de data/scripts por su nombre de archivo, con argumentos opcionales. "
        "Requiere confirmación."
    ),
    parameters={"name": {"type": "string"}, "args": {"type": "array", "items": {"type": "string"}}},
    required=["name"], risk=Risk.SENSITIVE, category="automatizacion", blocking=True, timeout_s=900,
    summary_fn=lambda p: f"Ejecutar script revisado {p.get('name')} {' '.join(p.get('args') or [])}",
)
def run_script(params: dict, ctx: ExecContext) -> str:
    folder = (DATA_DIR / "scripts").resolve()
    f = (folder / params["name"]).resolve()
    if not f.is_relative_to(folder) or not f.is_file():
        raise PermissionDenied("Solo se pueden ejecutar scripts que estén en data/scripts.")
    args = [str(a) for a in (params.get("args") or [])]
    ext = f.suffix.lower()
    if ext == ".ps1":
        cmd = ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(f), *args]
    elif ext == ".py":
        import sys
        cmd = [sys.executable, str(f), *args]
    elif ext in (".bat", ".cmd"):
        cmd = ["cmd.exe", "/c", str(f), *args]
    else:
        raise PermissionDenied("Tipo de script no soportado.")
    return _run(cmd, str(DATA_DIR / "workspace"), get_config().security.shell_timeout_s * 3)
