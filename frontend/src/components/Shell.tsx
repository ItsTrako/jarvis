import { AnimatePresence, motion } from "framer-motion";
import {
  Activity, Bot, Brain, Cpu, History, Home, Maximize2, Menu, MessagesSquare, Minimize2, Octagon, Play, Settings, Workflow,
  Wrench, X,
} from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { post } from "../lib/api";
import { useJarvis, type Page } from "../lib/store";
import { StatusDot, cx } from "./ui";

const NAV: { id: Page; label: string; icon: typeof Home }[] = [
  { id: "home", label: "Inicio", icon: Home },
  { id: "conversations", label: "Conversaciones", icon: MessagesSquare },
  { id: "memory", label: "Memoria", icon: Brain },
  { id: "automations", label: "Automatizaciones", icon: Workflow },
  { id: "tools", label: "Herramientas", icon: Wrench },
  { id: "system", label: "Sistema", icon: Cpu },
  { id: "history", label: "Historial", icon: History },
  { id: "settings", label: "Configuración", icon: Settings },
];

function Brand({ compact }: { compact?: boolean }) {
  return (
    <div className="flex items-center gap-3 px-2">
      <div className="relative grid size-9 place-items-center">
        <div className="absolute inset-0 rounded-full bg-electric/30 blur-md" />
        <div className="relative size-6 rounded-full bg-[radial-gradient(circle_at_35%_30%,#fff,#c4b5fd_35%,#8b5cf6_70%,#2e1065)] shadow-[0_0_18px_rgb(168_85_247/0.7)]" />
        <div className="absolute inset-0 animate-[spin_12s_linear_infinite] rounded-full border border-dashed border-lavender/30" />
      </div>
      {!compact && (
        <div className="leading-none">
          <div className="font-display text-[15px] font-semibold tracking-[0.22em] text-ink">J.A.R.V.I.S.</div>
          <div className="mt-1 text-[10px] tracking-[0.18em] text-faint uppercase">Asistente personal</div>
        </div>
      )}
    </div>
  );
}

function NavList({ onPick }: { onPick?: () => void }) {
  const page = useJarvis((s) => s.page);
  const setPage = useJarvis((s) => s.setPage);
  const approvals = useJarvis((s) => s.approvals.length);
  const activeJobs = useJarvis((s) => s.jobs.filter((j) => j.status === "running" || j.status === "queued").length);
  return (
    <nav className="flex flex-col gap-0.5">
      {NAV.map(({ id, label, icon: Icon }) => {
        const active = page === id;
        const badge = id === "automations" ? activeJobs : id === "home" ? approvals : 0;
        return (
          <button
            key={id}
            onClick={() => {
              setPage(id);
              onPick?.();
            }}
            className={cx(
              "group relative flex items-center gap-3 rounded-xl px-3 py-2.5 text-[13.5px] transition-colors duration-150",
              active ? "text-ink" : "text-muted hover:text-ink hover:bg-white/[0.03]",
            )}
          >
            {active && (
              <motion.span
                layoutId="nav-active"
                className="absolute inset-0 rounded-xl border border-electric/25 bg-gradient-to-r from-electric/[0.16] to-transparent"
                transition={{ type: "spring", stiffness: 420, damping: 36 }}
              />
            )}
            <Icon size={17} strokeWidth={1.7} className={cx("relative", active && "text-lavender")} />
            <span className="relative">{label}</span>
            {badge > 0 && (
              <span className="relative ml-auto rounded-full bg-electric/25 px-1.5 font-mono text-[10px] text-lavender">{badge}</span>
            )}
          </button>
        );
      })}
    </nav>
  );
}

function ConnectionPanel() {
  const conn = useJarvis((s) => s.conn);
  const status = useJarvis((s) => s.status);
  const tg = status?.telegram?.status;
  const model = status?.model;
  const rows = [
    { label: "Núcleo", ok: conn === "online", text: conn === "online" ? "En línea" : conn === "connecting" ? "Conectando" : "Sin conexión" },
    { label: "Cerebro", ok: !!model?.ok, warn: model?.local && !model?.ok,
      text: model?.ok ? (model.local ? model.display_name : "Claude · nube") : model?.detail ?? "No disponible" },
    { label: "Telegram", ok: tg === "conectado", text: tg === "conectado" ? `@${status?.telegram?.bot}` : tg === "sin_token" ? "Sin configurar" : tg ?? "—", warn: tg === "sin_token" || tg === "desactivado" },
    { label: "Voz", ok: !status?.voice?.stt?.error, text: status?.voice?.stt?.loaded ? `Whisper · ${status.voice.stt.device?.toUpperCase()}` : status?.voice?.stt?.error ? "Error" : "Whisper", warn: !!status?.voice?.stt?.error },
  ];
  return (
    <div className="glass-soft space-y-2 rounded-xl p-3">
      {rows.map((r) => (
        <div key={r.label} className="flex items-center gap-2 text-[11.5px]">
          <StatusDot tone={r.ok ? "ok" : r.warn ? "warn" : "danger"} pulse={r.ok && r.label === "Núcleo"} />
          <span className="text-faint">{r.label}</span>
          <span className="ml-auto truncate text-muted">{r.text}</span>
        </div>
      ))}
    </div>
  );
}

function EmergencyButton({ compact }: { compact?: boolean }) {
  const emergency = useJarvis((s) => s.emergency);
  const [confirm, setConfirm] = useState(false);
  const toggle = async () => {
    if (emergency) {
      await post("/api/emergency", { engaged: false });
      return;
    }
    if (!confirm) {
      setConfirm(true);
      window.setTimeout(() => setConfirm(false), 3000);
      return;
    }
    setConfirm(false);
    await post("/api/emergency", { engaged: true });
  };
  return (
    <button
      onClick={toggle}
      className={cx(
        "flex items-center justify-center gap-2 rounded-xl border px-3 py-2 text-[12.5px] font-medium transition-all duration-200 active:scale-[0.97]",
        emergency
          ? "border-ok/30 bg-ok/10 text-ok hover:bg-ok/15"
          : confirm
            ? "border-danger bg-danger/25 text-white shadow-[0_0_24px_rgb(251_113_133/0.4)]"
            : "border-danger/25 bg-danger/[0.07] text-danger hover:bg-danger/15",
      )}
      title="Parada de emergencia: cancela todas las tareas y bloquea nuevas acciones"
    >
      {emergency ? <Play size={15} /> : <Octagon size={15} />}
      {!compact && (emergency ? "Reanudar sistemas" : confirm ? "Pulsa otra vez para detener" : "Parada de emergencia")}
    </button>
  );
}

function FullscreenButton() {
  const [full, setFull] = useState(!!document.fullscreenElement);
  useEffect(() => {
    const on = () => setFull(!!document.fullscreenElement);
    document.addEventListener("fullscreenchange", on);
    return () => document.removeEventListener("fullscreenchange", on);
  }, []);
  const toggle = async () => {
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else await document.documentElement.requestFullscreen({ navigationUI: "hide" });
    } catch {
      /* el navegador puede rechazarlo si no viene de un clic */
    }
  };
  return (
    <button onClick={toggle} title={full ? "Salir de pantalla completa (Esc)" : "Pantalla completa (F11)"}
      aria-label="Pantalla completa"
      className="grid size-9 place-items-center rounded-xl border border-line-strong text-muted transition-colors hover:border-lavender/30 hover:text-ink">
      {full ? <Minimize2 size={16} /> : <Maximize2 size={16} />}
    </button>
  );
}

function Clock() {
  const [now, setNow] = useState(new Date());
  useEffect(() => {
    const t = window.setInterval(() => setNow(new Date()), 15000);
    return () => window.clearInterval(t);
  }, []);
  return (
    <div className="text-right leading-tight">
      <div className="font-mono text-sm tabular-nums text-ink">{now.toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" })}</div>
      <div className="text-[10.5px] capitalize text-faint">{now.toLocaleDateString("es-ES", { weekday: "long", day: "numeric", month: "long" })}</div>
    </div>
  );
}

export function Shell({ children }: { children: ReactNode }) {
  const [drawer, setDrawer] = useState(false);
  const emergency = useJarvis((s) => s.emergency);
  const page = useJarvis((s) => s.page);
  const busy = useJarvis((s) => s.busy);
  const label = NAV.find((n) => n.id === page)?.label;

  return (
    <div className="relative flex h-full">
      <div className="ambient" />
      <div className="aurora" aria-hidden><span /><span /><span /></div>
      {/* Barra lateral (escritorio) */}
      <aside className="relative z-10 hidden w-[236px] shrink-0 flex-col gap-5 border-r border-line bg-abyss/40 p-4 backdrop-blur-xl lg:flex">
        <Brand />
        <NavList />
        <div className="mt-auto space-y-3">
          <ConnectionPanel />
          <EmergencyButton />
        </div>
      </aside>

      {/* Cajón móvil */}
      <AnimatePresence>
        {drawer && (
          <>
            <motion.div className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm lg:hidden" initial={{ opacity: 0 }}
              animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => setDrawer(false)} />
            <motion.aside
              className="fixed inset-y-0 left-0 z-50 flex w-[272px] flex-col gap-5 border-r border-line bg-abyss p-4 lg:hidden"
              initial={{ x: -290 }} animate={{ x: 0 }} exit={{ x: -290 }} transition={{ type: "spring", stiffness: 380, damping: 38 }}
            >
              <div className="flex items-center justify-between">
                <Brand />
                <button onClick={() => setDrawer(false)} className="text-muted" aria-label="Cerrar menú"><X size={18} /></button>
              </div>
              <NavList onPick={() => setDrawer(false)} />
              <div className="mt-auto space-y-3">
                <ConnectionPanel />
                <EmergencyButton />
              </div>
            </motion.aside>
          </>
        )}
      </AnimatePresence>

      <div className="relative z-10 flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center gap-3 border-b border-line px-4 lg:px-6">
          <button className="text-muted lg:hidden" onClick={() => setDrawer(true)} aria-label="Abrir menú"><Menu size={20} /></button>
          <div className="lg:hidden"><Brand compact /></div>
          <div className="hidden items-center gap-2 text-sm text-muted lg:flex">
            <span className="text-faint">J.A.R.V.I.S.</span>
            <span className="text-faint">/</span>
            <span className="text-ink">{label}</span>
          </div>
          {busy && (
            <span className="ml-2 hidden items-center gap-1.5 text-xs text-lavender sm:flex">
              <Bot size={14} className="animate-pulse" /> <span className="shimmer-text">Trabajando…</span>
            </span>
          )}
          <div className="ml-auto flex items-center gap-4">
            {emergency && (
              <span className="flex items-center gap-1.5 rounded-full border border-danger/40 bg-danger/15 px-2.5 py-1 text-[11px] font-medium text-danger">
                <Activity size={12} /> PARADA ACTIVA
              </span>
            )}
            <div className="lg:hidden"><EmergencyButton compact /></div>
            <div className="hidden sm:block"><Clock /></div>
            <FullscreenButton />
          </div>
        </header>
        <main className="min-h-0 flex-1 overflow-hidden">{children}</main>
      </div>
    </div>
  );
}
