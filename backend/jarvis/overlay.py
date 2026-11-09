"""JARVIS en el escritorio: esfera animada transparente sobre tu fondo de pantalla.

Ventana «layered» de Windows con transparencia por píxel (UpdateLayeredWindow): se dibuja
encima del fondo (también de Wallpaper Engine) y por detrás de tus ventanas, no recibe clics,
no aparece en la barra de tareas y reacciona en directo al estado de JARVIS (escuchando,
pensando, hablando) a través del WebSocket local.

    python -m jarvis overlay
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import json
import logging
import math
import threading
import time

import numpy as np

from .config import DATA_DIR, get_config, load_config

log = logging.getLogger("jarvis.overlay")

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
kernel32 = ctypes.windll.kernel32

WS_EX_LAYERED, WS_EX_TRANSPARENT, WS_EX_TOOLWINDOW, WS_EX_NOACTIVATE = 0x80000, 0x20, 0x80, 0x08000000
WS_POPUP = 0x80000000
ULW_ALPHA = 2
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE, SWP_SHOWWINDOW = 0x1, 0x2, 0x10, 0x40
HWND_TOPMOST = -1
GW_HWNDPREV = 3
PM_REMOVE = 1
SPI_GETWORKAREA = 0x30
LRESULT = ctypes.c_ssize_t


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [("BlendOp", ctypes.c_ubyte), ("BlendFlags", ctypes.c_ubyte),
                ("SourceConstantAlpha", ctypes.c_ubyte), ("AlphaFormat", ctypes.c_ubyte)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG), ("biPlanes", wt.WORD),
                ("biBitCount", wt.WORD), ("biCompression", wt.DWORD), ("biSizeImage", wt.DWORD),
                ("biXPelsPerMeter", wt.LONG), ("biYPelsPerMeter", wt.LONG), ("biClrUsed", wt.DWORD),
                ("biClrImportant", wt.DWORD)]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wt.DWORD * 3)]


WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)


class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", wt.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", wt.HINSTANCE), ("hIcon", wt.HICON),
                ("hCursor", wt.HANDLE), ("hbrBackground", wt.HBRUSH), ("lpszMenuName", wt.LPCWSTR),
                ("lpszClassName", wt.LPCWSTR)]


user32.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.DefWindowProcW.restype = LRESULT
user32.SetWindowPos.argtypes = [wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.UINT]
user32.GetWindow.argtypes = [wt.HWND, wt.UINT]
user32.GetWindow.restype = wt.HWND
user32.FindWindowW.restype = wt.HWND
user32.FindWindowExW.argtypes = [wt.HWND, wt.HWND, wt.LPCWSTR, wt.LPCWSTR]
user32.FindWindowExW.restype = wt.HWND
user32.CreateWindowExW.restype = wt.HWND
user32.CreateWindowExW.argtypes = [wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_int, ctypes.c_int, wt.HWND, wt.HMENU, wt.HINSTANCE, wt.LPVOID]
user32.UpdateLayeredWindow.argtypes = [wt.HWND, wt.HDC, ctypes.POINTER(wt.POINT), ctypes.POINTER(wt.SIZE), wt.HDC,
                                       ctypes.POINTER(wt.POINT), wt.DWORD, ctypes.POINTER(BLENDFUNCTION), wt.DWORD]
gdi32.CreateDIBSection.restype = wt.HBITMAP
gdi32.CreateDIBSection.argtypes = [wt.HDC, ctypes.POINTER(BITMAPINFO), wt.UINT, ctypes.POINTER(ctypes.c_void_p),
                                   wt.HANDLE, wt.DWORD]
gdi32.SelectObject.argtypes = [wt.HDC, wt.HGDIOBJ]
gdi32.SelectObject.restype = wt.HGDIOBJ
gdi32.CreateCompatibleDC.argtypes = [wt.HDC]
gdi32.CreateCompatibleDC.restype = wt.HDC


# ------------------------------------------------------------------ estado (vía WebSocket)

STATE = {"state": "idle", "level": 0.0, "level_ts": 0.0, "assistant": "off", "online": False, "quit": False}

STATUS_TEXT = {"idle": "Di «Hey JARVIS»", "listening": "Te escucho…", "transcribing": "Entendiendo…",
               "thinking": "Pensando…", "speaking": "", "offline": "Sin conexión"}


def _ws_thread() -> None:
    from websockets.sync.client import connect

    port = get_config().server.port
    last_ok = time.time()
    busy_runs: set[str] = set()
    while not STATE["quit"]:
        try:
            token = (DATA_DIR / ".session_token").read_text(encoding="utf-8").strip()
            with connect(f"ws://127.0.0.1:{port}/ws?token={token}", open_timeout=5, max_size=None) as ws:
                STATE["online"] = True
                while not STATE["quit"]:
                    ev = json.loads(ws.recv(timeout=30))
                    last_ok = time.time()
                    t = ev.get("type")
                    if t == "voice_level":
                        STATE["level"], STATE["level_ts"] = float(ev.get("level", 0)), time.time()
                    elif t == "voice_state":
                        st = ev.get("state", "off")
                        STATE["assistant"] = st
                        if st in ("listening", "transcribing", "thinking", "speaking"):
                            STATE["state"] = st
                        elif not busy_runs:
                            STATE["state"] = "idle"
                    elif t == "run_start":
                        busy_runs.add(ev.get("conversation_id", ""))
                        if STATE["state"] == "idle":
                            STATE["state"] = "thinking"
                    elif t == "run_end":
                        busy_runs.discard(ev.get("conversation_id", ""))
                        if STATE["state"] == "thinking" and STATE["assistant"] in ("standby", "off", "listening"):
                            STATE["state"] = "idle" if STATE["assistant"] != "listening" else "listening"
                    elif t == "hello":
                        STATE["state"] = "idle"
        except Exception:
            STATE["online"] = False
            if time.time() - last_ok > 120:  # JARVIS ya no está en marcha: se cierra solo
                STATE["quit"] = True
                return
            time.sleep(3)


# ------------------------------------------------------------------ render (numpy)

PAL = {
    "idle": ((0.97, 0.95, 1.0), (0.77, 0.71, 0.99), (0.55, 0.36, 0.96), 0.12, 0.0),
    "listening": ((1.0, 0.97, 1.0), (0.85, 0.71, 1.0), (0.66, 0.33, 0.97), 0.45, 0.6),
    "transcribing": ((0.97, 0.95, 1.0), (0.77, 0.71, 0.99), (0.66, 0.33, 0.97), 0.6, 1.2),
    "thinking": ((0.98, 0.95, 1.0), (0.75, 0.66, 1.0), (0.48, 0.30, 0.95), 0.75, 2.2),
    "speaking": ((1.0, 1.0, 1.0), (0.87, 0.84, 1.0), (0.66, 0.33, 0.97), 0.5, 0.8),
    "offline": ((0.64, 0.6, 0.69), (0.44, 0.4, 0.5), (0.27, 0.23, 0.35), 0.0, 0.0),
}


def _smooth_noise(shape: tuple[int, int], cutoff: float, seed: int) -> np.ndarray:
    """Ruido suave y periódico (filtrado en frecuencia) para el plasma en coordenadas polares."""
    rng = np.random.default_rng(seed)
    f = np.fft.fft2(rng.standard_normal(shape))
    ky = np.fft.fftfreq(shape[0])[:, None]
    kx = np.fft.fftfreq(shape[1])[None, :]
    f *= np.exp(-(kx ** 2 + ky ** 2) / (2 * cutoff ** 2))
    n = np.real(np.fft.ifft2(f))
    return ((n - n.mean()) / (n.std() + 1e-9)).astype(np.float32)


class OrbRenderer:
    def __init__(self, size: int, text_h: int) -> None:
        self.S, self.TH = size, text_h
        n = self.N = max(96, size // 2)  # se calcula a media resolución y se escala (4x menos trabajo)
        y, x = np.mgrid[0:n, 0:n].astype(np.float32)
        self.x = (x - n / 2) / n
        self.y = (n / 2 - y) / n
        self.d = np.sqrt(self.x ** 2 + self.y ** 2)
        self.ang = np.arctan2(self.y, self.x)
        A, RB = 512, 160
        self.A, self.RB = A, RB
        self.ai = ((self.ang + math.pi) / (2 * math.pi) * A).astype(np.int32) % A
        self.n1 = _smooth_noise((A, RB), 0.022, 1)
        self.n2 = _smooth_noise((A, RB), 0.05, 2)
        self.cur = [np.array(c, np.float32) for c in PAL["idle"][:3]] + [PAL["idle"][3], PAL["idle"][4]]
        self.text_cache: tuple[str, np.ndarray] | None = None
        self.out = np.zeros((size + text_h, size, 4), np.uint8)
        self.t = 0.0
        self.lvl = 0.0

    def _text(self, text: str) -> np.ndarray:
        if self.text_cache and self.text_cache[0] == text:
            return self.text_cache[1]
        from PIL import Image, ImageDraw, ImageFont

        img = Image.new("RGBA", (self.S, self.TH), (0, 0, 0, 0))
        if text:
            try:
                font = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", max(12, self.S // 18))
            except OSError:
                font = ImageFont.load_default()
            dr = ImageDraw.Draw(img)
            w = dr.textlength(text, font=font)
            # sombra suave + texto lavanda
            dr.text(((self.S - w) / 2 + 1, 7), text, font=font, fill=(0, 0, 0, 140))
            dr.text(((self.S - w) / 2, 6), text, font=font, fill=(214, 204, 255, 235))
        a = np.asarray(img).astype(np.float32) / 255.0
        bgra = np.zeros((self.TH, self.S, 4), np.uint8)
        bgra[..., 0] = (a[..., 2] * a[..., 3] * 255).astype(np.uint8)
        bgra[..., 1] = (a[..., 1] * a[..., 3] * 255).astype(np.uint8)
        bgra[..., 2] = (a[..., 0] * a[..., 3] * 255).astype(np.uint8)
        bgra[..., 3] = (a[..., 3] * 255).astype(np.uint8)
        self.text_cache = (text, bgra)
        return bgra

    def frame(self, dt: float, state: str, level: float, text: str) -> np.ndarray:
        core_t, mid_t, rim_t, en_t, spin_t = PAL.get(state, PAL["idle"])
        k = 1 - 0.02 ** dt
        for i, tgt in enumerate((core_t, mid_t, rim_t)):
            self.cur[i] += (np.array(tgt, np.float32) - self.cur[i]) * k
        self.cur[3] += (en_t - self.cur[3]) * k
        self.cur[4] += (spin_t - self.cur[4]) * k
        core, mid, rim, E, spin = self.cur
        self.lvl += (level - self.lvl) * min(1.0, dt * 12)
        L = self.lvl
        self.t += dt * (1 + spin * 0.25)
        t = self.t
        d, ang = self.d, self.ang

        R = 0.205 + 0.007 * math.sin(t * 1.1) + 0.03 * L
        amp = 0.006 + 0.03 * E + 0.06 * L
        r = R + amp * (np.sin(3 * ang + 1.3 * t) + 0.6 * np.sin(5 * ang - 0.9 * t)
                       + 0.25 * np.sin(9 * ang + 2.1 * t)) / 1.85
        outside = np.maximum(d - r, 0)
        g = np.exp(-outside * 7.0) * (0.38 + 0.55 * E + 0.6 * L)
        g2 = np.exp(-outside * 24.0) * (0.6 + L)
        col = rim[None, None, :] * (g * 0.6)[..., None] + ((rim + mid) * 0.5)[None, None, :] * (g2 * 0.45)[..., None]
        alpha = g * 0.5 + g2 * 0.4

        inside = np.clip((r - d) / 0.005 + 0.5, 0, 1)
        z = np.sqrt(np.clip(1 - (d / r) ** 2, 0, 1))
        ri = np.clip((d / np.maximum(r, 1e-3)) * (self.RB - 1), 0, self.RB - 1).astype(np.int32)
        s1 = int(t * 14 * (1 + E * 2)) % self.A
        s2 = int(-t * 22) % self.A
        plasma = self.n1[(self.ai + s1) % self.A, ri] * 0.65 + self.n2[(self.ai + s2) % self.A, ri] * 0.45
        plasma = np.clip((plasma + 0.8) / 2.0, 0, 1)
        # El ruido polar converge en el centro: ahí se funde con un núcleo liso y luminoso
        rel = d / np.maximum(r, 1e-3)
        cmix = np.clip((rel - 0.12) / 0.33, 0, 1)
        plasma = 0.62 + (plasma - 0.62) * cmix
        deep = np.array([0.13, 0.03, 0.33], np.float32)
        base = deep + (rim * 1.05 - deep)[None, None, :] * plasma[..., None]
        base = base + (mid[None, None, :] - base) * (plasma ** 2 * 0.55)[..., None]
        nx, ny = self.x / np.maximum(r, 1e-3), self.y / np.maximum(r, 1e-3)
        diff = np.clip((-0.45 * nx + 0.55 * ny + 0.75 * z) / 1.03, 0, 1)
        fres = (1 - z) ** 2.2
        spec = np.exp(-((nx + 0.38) ** 2 + (ny - 0.45) ** 2) / 0.018) * 0.55
        c = base * (0.55 + 0.5 * diff)[..., None]
        c += core[None, None, :] * (z ** 6 * (0.42 + 0.45 * L))[..., None]
        c += spec[..., None]
        c += ((rim + mid) * 0.5)[None, None, :] * (fres * (1.1 + 1.4 * L))[..., None]
        col = col * (1 - inside)[..., None] + c * inside[..., None]
        alpha = alpha * (1 - inside) + inside

        for kk in range(3):
            rr = 0.33 + kk * 0.045 + 0.003 * math.sin(t * 0.8 + kk)
            w = 0.0035 + kk * 0.0008
            ring = np.exp(-((d - rr) / w) ** 2)
            rot = t * (0.22 + 0.12 * kk) * (1 if kk % 2 == 0 else -1) * (1 + spin)
            seg = np.clip((np.sin((3 + kk * 2) * (ang + rot)) + 0.3) / 0.6, 0, 1)
            a = ring * seg * (0.42 - kk * 0.1 + 0.45 * E)
            col += mid[None, None, :] * a[..., None]
            alpha += a

        alpha = np.clip(alpha, 0, 1)
        col = np.minimum(col, alpha[..., None] * 1.2)
        col = np.clip(col, 0, 1)
        from PIL import Image

        S = self.S
        small = np.empty((self.N, self.N, 4), np.uint8)
        small[..., 0] = (col[..., 2] * 255).astype(np.uint8)
        small[..., 1] = (col[..., 1] * 255).astype(np.uint8)
        small[..., 2] = (col[..., 0] * 255).astype(np.uint8)
        small[..., 3] = (alpha * 255).astype(np.uint8)
        o = self.out
        o[:S] = np.asarray(Image.fromarray(small, "RGBA").resize((S, S), Image.BILINEAR))
        if self.TH:
            o[S:] = self._text(text)
        return o


# ------------------------------------------------------------------ ventana

def _desktop_hwnd() -> int:
    """Ventana del escritorio (la que contiene los iconos: Progman o un WorkerW)."""
    progman = user32.FindWindowW("Progman", None)
    if user32.FindWindowExW(progman, None, "SHELLDLL_DefView", None):
        return progman
    w = None
    while True:
        w = user32.FindWindowExW(None, w, "WorkerW", None)
        if not w:
            break
        if user32.FindWindowExW(w, None, "SHELLDLL_DefView", None):
            return w
    return progman


def _place(hwnd, layer: str) -> None:
    flags = SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE
    if layer == "top":
        user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, flags)
        return
    desk = _desktop_hwnd()
    prev = user32.GetWindow(desk, GW_HWNDPREV)
    if prev and prev != hwnd:
        user32.SetWindowPos(hwnd, prev, 0, 0, 0, 0, flags)  # justo encima del escritorio, bajo tus ventanas


def main() -> None:
    load_config()
    logging.basicConfig(level=logging.INFO)
    mutex = kernel32.CreateMutexW(None, False, "JARVIS_Desktop_Overlay")
    if kernel32.GetLastError() == 183:  # ya hay una en marcha
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass
    cfg = get_config().desktop
    size = int(cfg.size)
    text_h = int(size * 0.16) if cfg.show_text else 0
    W, H = size, size + text_h

    rect = wt.RECT()
    user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(rect), 0)
    m = 24
    pos = {
        "bottom-right": (rect.right - W - m, rect.bottom - H - m),
        "top-right": (rect.right - W - m, rect.top + m),
        "bottom-left": (rect.left + m, rect.bottom - H - m),
        "top-left": (rect.left + m, rect.top + m),
        "center": ((rect.left + rect.right - W) // 2, (rect.top + rect.bottom - H) // 2),
    }.get(cfg.position, (rect.right - W - m, rect.bottom - H - m))

    hinst = kernel32.GetModuleHandleW(None)
    proc = WNDPROC(lambda h, msg, wp, lp: user32.DefWindowProcW(h, msg, wp, lp))
    wc = WNDCLASSW()
    wc.lpfnWndProc = proc
    wc.hInstance = hinst
    wc.lpszClassName = "JarvisDesktopOrb"
    user32.RegisterClassW(ctypes.byref(wc))
    hwnd = user32.CreateWindowExW(WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE,
                                  "JarvisDesktopOrb", "JARVIS", WS_POPUP, pos[0], pos[1], W, H, None, None, hinst, None)

    screen_dc = user32.GetDC(None)
    mem_dc = gdi32.CreateCompatibleDC(screen_dc)
    bmi = BITMAPINFO()
    bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmi.bmiHeader.biWidth, bmi.bmiHeader.biHeight = W, -H  # de arriba abajo
    bmi.bmiHeader.biPlanes, bmi.bmiHeader.biBitCount = 1, 32
    bits = ctypes.c_void_p()
    hbmp = gdi32.CreateDIBSection(mem_dc, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
    gdi32.SelectObject(mem_dc, hbmp)
    blend = BLENDFUNCTION(0, 0, int(255 * max(0.2, min(1.0, cfg.opacity))), 1)
    pt_dst, pt_src, sz = wt.POINT(*pos), wt.POINT(0, 0), wt.SIZE(W, H)

    renderer = OrbRenderer(size, text_h)
    threading.Thread(target=_ws_thread, daemon=True).start()
    user32.ShowWindow(hwnd, 4)  # SW_SHOWNOACTIVATE
    _place(hwnd, cfg.layer)

    msg = wt.MSG()
    last = time.perf_counter()
    last_place = 0.0
    while not STATE["quit"]:
        while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        now = time.perf_counter()
        dt = min(0.1, now - last)
        last = now
        state = STATE["state"] if STATE["online"] else "offline"
        level = STATE["level"] if time.time() - STATE["level_ts"] < 0.5 else 0.0
        text = STATUS_TEXT.get(state, "") if cfg.show_text else ""
        if state == "idle" and STATE["assistant"] == "off":
            text = "J.A.R.V.I.S." if cfg.show_text else ""
        frame = renderer.frame(dt, state, level, text)
        ctypes.memmove(bits, frame.ctypes.data, frame.nbytes)
        user32.UpdateLayeredWindow(hwnd, screen_dc, ctypes.byref(pt_dst), ctypes.byref(sz), mem_dc,
                                   ctypes.byref(pt_src), 0, ctypes.byref(blend), ULW_ALPHA)
        if now - last_place > 1.0:
            _place(hwnd, cfg.layer)
            last_place = now
        active = state not in ("idle", "offline") or level > 0.02
        time.sleep(max(0.0, (1 / 30 if active else 1 / 15) - (time.perf_counter() - now)))
    user32.DestroyWindow(hwnd)
    kernel32.CloseHandle(mutex)


if __name__ == "__main__":
    main()
