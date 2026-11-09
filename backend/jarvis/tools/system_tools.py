"""Consultas del sistema y gestión de procesos."""

from __future__ import annotations

import json

import psutil

from .. import sysmon
from ..config import get_config
from ..security import ExecContext, PermissionDenied, Risk
from .base import tool


@tool(
    name="system_info",
    description=(
        "Obtiene el estado actual del ordenador: sistema operativo, CPU (uso, frecuencia, "
        "temperatura si está disponible), RAM, GPU (uso, VRAM, temperatura, consumo), discos, "
        "red, tiempo encendido, batería, procesos que más consumen y ventanas/aplicaciones abiertas."
    ),
    parameters={"include_processes": {"type": "boolean", "description": "Incluir procesos y ventanas (por defecto true)"}},
    category="sistema", blocking=True,
)
def system_info(params: dict, ctx: ExecContext) -> str:
    snap = sysmon.snapshot(include_processes=params.get("include_processes", True))
    return json.dumps(snap, ensure_ascii=False, default=str)


@tool(
    name="list_processes",
    description="Lista procesos en ejecución ordenados por memoria o CPU. Permite filtrar por nombre.",
    parameters={
        "sort": {"type": "string", "enum": ["memory", "cpu"]},
        "name_filter": {"type": "string", "description": "Texto que debe contener el nombre del proceso"},
        "limit": {"type": "integer"},
    },
    category="sistema", blocking=True,
)
def list_processes(params: dict, ctx: ExecContext) -> str:
    sort = params.get("sort", "memory")
    if sort == "cpu":
        for p in psutil.process_iter():
            try:
                p.cpu_percent(None)
            except Exception:
                pass
        import time
        time.sleep(0.6)
    procs = sysmon.top_processes(2000, sort=sort)
    flt = (params.get("name_filter") or "").lower()
    if flt:
        procs = [p for p in procs if flt in (p["name"] or "").lower()]
    return json.dumps(procs[: int(params.get("limit") or 25)], ensure_ascii=False)


def _kill_summary(p: dict) -> str:
    target = p.get("pid") or p.get("name")
    try:
        if p.get("pid"):
            target = f"{psutil.Process(int(p['pid'])).name()} (PID {p['pid']})"
    except Exception:
        pass
    return f"Cerrar forzosamente el proceso {target}" + (" y todas sus instancias" if p.get("name") else "")


@tool(
    name="kill_process",
    description=(
        "Termina un proceso por PID o por nombre exacto (p. ej. 'chrome.exe'). Acción peligrosa: "
        "requiere confirmación del usuario. Los procesos críticos del sistema y de seguridad están protegidos."
    ),
    parameters={"pid": {"type": "integer"}, "name": {"type": "string"}, "force": {"type": "boolean"}},
    risk=Risk.DANGEROUS, category="sistema", summary_fn=_kill_summary, blocking=True,
)
def kill_process(params: dict, ctx: ExecContext) -> str:
    protected = {n.lower() for n in get_config().security.protected_processes}
    targets: list[psutil.Process] = []
    if params.get("pid"):
        targets.append(psutil.Process(int(params["pid"])))
    elif params.get("name"):
        name = params["name"].lower()
        targets = [p for p in psutil.process_iter(["name"]) if (p.info["name"] or "").lower() == name]
    else:
        return "Indica 'pid' o 'name'."
    if not targets:
        return "No se encontró ningún proceso que coincida."
    done = []
    for p in targets:
        pname = p.name().lower()
        if pname in protected or p.pid in (0, 4):
            raise PermissionDenied(f"{pname} es un proceso protegido")
        if params.get("force"):
            p.kill()
        else:
            p.terminate()
        done.append(f"{pname} (PID {p.pid})")
    gone, alive = psutil.wait_procs(targets, timeout=4)
    msg = f"Terminados: {', '.join(done)}."
    if alive:
        msg += f" Siguen vivos: {[a.pid for a in alive]} (puedes reintentar con force=true)."
    return msg


@tool(
    name="list_windows",
    description="Lista las aplicaciones con ventanas visibles abiertas ahora mismo y sus títulos.",
    category="sistema", blocking=True,
)
def list_windows(params: dict, ctx: ExecContext) -> str:
    return json.dumps(sysmon.active_windows(), ensure_ascii=False)
