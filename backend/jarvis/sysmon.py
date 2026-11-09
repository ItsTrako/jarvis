"""Monitorización del sistema (CPU, RAM, GPU, discos, red, temperaturas, ventanas)."""

from __future__ import annotations

import logging
import platform
import subprocess
import time
from typing import Any

import psutil

log = logging.getLogger("jarvis.sysmon")

try:
    import pynvml  # nvidia-ml-py

    pynvml.nvmlInit()
    _NVML = True
except Exception:  # sin GPU NVIDIA o sin driver
    _NVML = False

_last_net = (time.time(), psutil.net_io_counters())
_cpu_temp_supported: bool | None = None
_cpu_temp_cache: tuple[float, float | None] = (0.0, None)
_static: dict[str, Any] | None = None


def static_info() -> dict[str, Any]:
    global _static
    if _static is None:
        cpu_name = platform.processor()
        try:
            import winreg

            k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
            cpu_name = winreg.QueryValueEx(k, "ProcessorNameString")[0].strip()
        except Exception:
            pass
        _static = {
            "os": f"{platform.system()} {platform.release()} ({platform.version()})",
            "hostname": platform.node(),
            "cpu_name": cpu_name,
            "cores": psutil.cpu_count(logical=False),
            "threads": psutil.cpu_count(logical=True),
            "ram_total_gb": round(psutil.virtual_memory().total / 1024**3, 1),
            "python": platform.python_version(),
        }
    return _static


def _gpu() -> list[dict[str, Any]]:
    if not _NVML:
        return []
    out = []
    try:
        for i in range(pynvml.nvmlDeviceGetCount()):
            h = pynvml.nvmlDeviceGetHandleByIndex(i)
            name = pynvml.nvmlDeviceGetName(h)
            name = name.decode() if isinstance(name, bytes) else name
            util = pynvml.nvmlDeviceGetUtilizationRates(h)
            mem = pynvml.nvmlDeviceGetMemoryInfo(h)
            try:
                temp = pynvml.nvmlDeviceGetTemperature(h, pynvml.NVML_TEMPERATURE_GPU)
            except Exception:
                temp = None
            try:
                power = round(pynvml.nvmlDeviceGetPowerUsage(h) / 1000, 1)
            except Exception:
                power = None
            out.append({
                "name": name, "util": util.gpu, "mem_used_gb": round(mem.used / 1024**3, 2),
                "mem_total_gb": round(mem.total / 1024**3, 2), "temp_c": temp, "power_w": power,
            })
    except Exception as e:
        log.debug("NVML: %s", e)
    return out


def _cpu_temp() -> float | None:
    """Temperatura CPU vía ACPI (WMI). Muchas placas no la exponen sin privilegios."""
    global _cpu_temp_supported, _cpu_temp_cache
    if _cpu_temp_supported is False:
        return None
    t, val = _cpu_temp_cache
    if time.time() - t < 15:
        return val
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "(Get-CimInstance -Namespace root/wmi -ClassName MSAcpi_ThermalZoneTemperature "
             "-ErrorAction Stop | Select-Object -First 1).CurrentTemperature"],
            capture_output=True, text=True, timeout=6, creationflags=0x08000000)
        raw = r.stdout.strip()
        if r.returncode != 0 or not raw:
            _cpu_temp_supported = False
            return None
        val = round(int(raw) / 10 - 273.15, 1)
        _cpu_temp_supported = True
        _cpu_temp_cache = (time.time(), val)
        return val
    except Exception:
        _cpu_temp_supported = False
        return None


def active_windows() -> list[dict[str, Any]]:
    try:
        import win32gui
        import win32process
    except ImportError:
        return []
    seen: dict[str, dict[str, Any]] = {}

    def cb(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        title = win32gui.GetWindowText(hwnd)
        if not title or title in ("Program Manager", "Settings", "Configuración"):
            return
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            proc = psutil.Process(pid)
            name = proc.name()
        except Exception:
            return
        if name.lower() in ("textinputhost.exe", "applicationframehost.exe", "shellexperiencehost.exe"):
            return
        entry = seen.setdefault(name, {"process": name, "pid": pid, "windows": []})
        if len(entry["windows"]) < 4:
            entry["windows"].append(title[:120])

    try:
        win32gui.EnumWindows(cb, None)
    except Exception:
        pass
    return list(seen.values())


def snapshot(include_processes: bool = False) -> dict[str, Any]:
    global _last_net
    vm = psutil.virtual_memory()
    sw = psutil.swap_memory()
    now = time.time()
    net = psutil.net_io_counters()
    dt = max(now - _last_net[0], 0.001)
    up = (net.bytes_sent - _last_net[1].bytes_sent) / dt
    down = (net.bytes_recv - _last_net[1].bytes_recv) / dt
    _last_net = (now, net)

    disks = []
    for p in psutil.disk_partitions(all=False):
        if "cdrom" in p.opts or not p.fstype:
            continue
        try:
            u = psutil.disk_usage(p.mountpoint)
        except Exception:
            continue
        if u.total == 0:
            continue
        disks.append({"mount": p.mountpoint, "total_gb": round(u.total / 1024**3, 1),
                      "used_gb": round(u.used / 1024**3, 1), "percent": u.percent})
    freq = psutil.cpu_freq()
    battery = None
    try:
        b = psutil.sensors_battery()
        if b:
            battery = {"percent": b.percent, "plugged": b.power_plugged}
    except Exception:
        pass

    data: dict[str, Any] = {
        "ts": now,
        "static": static_info(),
        "cpu": {
            "percent": psutil.cpu_percent(interval=None),
            "per_core": psutil.cpu_percent(interval=None, percpu=True),
            "freq_mhz": round(freq.current) if freq else None,
            "temp_c": _cpu_temp(),
        },
        "ram": {"percent": vm.percent, "used_gb": round(vm.used / 1024**3, 1),
                "total_gb": round(vm.total / 1024**3, 1)},
        "swap": {"percent": sw.percent},
        "gpu": _gpu(),
        "disks": disks,
        "net": {"up_kbps": round(up / 1024, 1), "down_kbps": round(down / 1024, 1)},
        "uptime_s": int(now - psutil.boot_time()),
        "battery": battery,
    }
    if include_processes:
        data["processes"] = top_processes(12)
        data["windows"] = active_windows()
    return data


def top_processes(n: int = 15, sort: str = "memory") -> list[dict[str, Any]]:
    procs = []
    for p in psutil.process_iter(["pid", "name", "memory_info", "cpu_percent", "username"]):
        try:
            info = p.info
            procs.append({
                "pid": info["pid"], "name": info["name"],
                "mem_mb": round((info["memory_info"].rss if info["memory_info"] else 0) / 1024**2, 1),
                "cpu": info["cpu_percent"] or 0.0,
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    key = "cpu" if sort == "cpu" else "mem_mb"
    procs.sort(key=lambda x: x[key], reverse=True)
    return procs[:n]


psutil.cpu_percent(interval=None)  # inicializa el contador
