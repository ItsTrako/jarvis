// Cliente de la API local de JARVIS (REST + WebSocket con reconexión).

declare global {
  interface Window {
    __JARVIS_TOKEN__?: string;
  }
}

let token: string | null = window.__JARVIS_TOKEN__ ?? null;

export async function ensureToken(): Promise<string> {
  if (token) return token;
  const r = await fetch("/api/session");
  if (!r.ok) throw new Error("No se pudo obtener la sesión");
  token = (await r.json()).token as string;
  return token;
}

/** El servicio se reinició y el token de esta página ya no vale: recargar para obtener uno nuevo. */
function reloadForNewSession() {
  try {
    const last = Number(sessionStorage.getItem("jarvis.reloadAt") || 0);
    if (Date.now() - last < 15000) return; // evita bucles
    sessionStorage.setItem("jarvis.reloadAt", String(Date.now()));
  } catch {
    /* noop */
  }
  location.reload();
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export async function api<T = any>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const t = await ensureToken();
  const headers: Record<string, string> = { "X-Jarvis-Token": t, ...(init.headers as Record<string, string>) };
  let body = init.body;
  if (init.json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(init.json);
  }
  const r = await fetch(path, { ...init, headers, body });
  if (r.status === 401) reloadForNewSession();
  if (!r.ok) {
    let msg = r.statusText;
    try {
      const j = await r.json();
      msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
    } catch {
      /* noop */
    }
    throw new ApiError(r.status, msg);
  }
  const ct = r.headers.get("content-type") || "";
  return (ct.includes("application/json") ? r.json() : (r as unknown)) as T;
}

export const get = <T = any>(p: string) => api<T>(p);
export const post = <T = any>(p: string, json?: unknown) => api<T>(p, { method: "POST", json: json ?? {} });
export const patch = <T = any>(p: string, json: unknown) => api<T>(p, { method: "PATCH", json });
export const put = <T = any>(p: string, json: unknown) => api<T>(p, { method: "PUT", json });
export const del = <T = any>(p: string) => api<T>(p, { method: "DELETE" });

export async function uploadFile(file: Blob, name: string, path = "/api/upload"): Promise<any> {
  const t = await ensureToken();
  const fd = new FormData();
  fd.append("file", file, name);
  const r = await fetch(path, { method: "POST", headers: { "X-Jarvis-Token": t }, body: fd });
  if (!r.ok) throw new ApiError(r.status, (await r.json().catch(() => ({}))).detail || r.statusText);
  return r.json();
}

export async function fileUrl(path: string): Promise<string> {
  const t = await ensureToken();
  return `/api/files?path=${encodeURIComponent(path)}&token=${encodeURIComponent(t)}`;
}

export async function wsUrl(path: string): Promise<string> {
  const t = await ensureToken();
  const proto = location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${location.host}${path}?token=${encodeURIComponent(t)}`;
}

type Listener = (ev: any) => void;

export class EventSocket {
  private ws: WebSocket | null = null;
  private listeners = new Set<Listener>();
  private statusListeners = new Set<(s: "connecting" | "online" | "offline") => void>();
  private retry = 0;
  private pingTimer: number | undefined;
  private closed = false;

  on(fn: Listener) {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }
  onStatus(fn: (s: "connecting" | "online" | "offline") => void) {
    this.statusListeners.add(fn);
    return () => this.statusListeners.delete(fn);
  }
  private setStatus(s: "connecting" | "online" | "offline") {
    this.statusListeners.forEach((f) => f(s));
  }

  async connect() {
    this.closed = false;
    this.setStatus("connecting");
    let ws: WebSocket;
    try {
      // Si el servicio se reinició, el token de esta página caducó: se comprueba antes de conectar.
      const probe = await fetch("/api/status", { headers: { "X-Jarvis-Token": await ensureToken() } });
      if (probe.status === 401) return reloadForNewSession();
      ws = new WebSocket(await wsUrl("/ws"));
    } catch {
      return this.schedule();
    }
    if (this.closed) {
      ws.close();
      return;
    }
    this.ws?.close();
    this.ws = ws;
    ws.onopen = () => {
      this.retry = 0;
      this.setStatus("online");
      window.clearInterval(this.pingTimer);
      this.pingTimer = window.setInterval(() => this.ws?.readyState === 1 && this.ws.send("ping"), 20000);
    };
    ws.onmessage = (m) => {
      if (this.ws !== ws) return;
      try {
        const ev = JSON.parse(m.data);
        this.listeners.forEach((f) => f(ev));
      } catch {
        /* noop */
      }
    };
    ws.onclose = () => {
      if (this.ws !== ws) return; // conexión antigua reemplazada
      window.clearInterval(this.pingTimer);
      this.setStatus("offline");
      if (!this.closed) this.schedule();
    };
    ws.onerror = () => ws.close();
  }

  private schedule() {
    const delay = Math.min(1000 * 2 ** this.retry, 10000);
    this.retry++;
    window.setTimeout(() => this.connect(), delay);
  }

  close() {
    this.closed = true;
    this.ws?.close();
  }
}

export const events = new EventSocket();
