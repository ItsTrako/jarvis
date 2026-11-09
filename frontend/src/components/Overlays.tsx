import { AnimatePresence, motion } from "framer-motion";
import { AlertOctagon, Bell, CheckCircle2, Info, ShieldAlert, TriangleAlert, X } from "lucide-react";
import { useEffect, useState } from "react";
import { post } from "../lib/api";
import { useJarvis, type Approval } from "../lib/store";
import { Badge, Button, cx, riskTone } from "./ui";

function Countdown({ until }: { until: number }) {
  const [now, setNow] = useState(Date.now() / 1000);
  useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now() / 1000), 1000);
    return () => window.clearInterval(t);
  }, []);
  const left = Math.max(0, Math.round(until - now));
  return <span className="font-mono tabular-nums">{Math.floor(left / 60)}:{String(left % 60).padStart(2, "0")}</span>;
}

function ApprovalCard({ a }: { a: Approval }) {
  const [busy, setBusy] = useState(false);
  const decide = async (approved: boolean) => {
    setBusy(true);
    try {
      await post(`/api/approvals/${a.id}`, { approved });
    } finally {
      setBusy(false);
    }
  };
  const danger = a.risk_level >= 3;
  const src = { ui: "PC", voice: "voz", telegram: "Telegram", job: "trabajo en segundo plano", automation: "automatización" }[a.source] ?? a.source;
  return (
    <motion.div
      initial={{ opacity: 0, y: 24, scale: 0.97 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: 12, scale: 0.98 }}
      transition={{ type: "spring", stiffness: 360, damping: 30 }}
      className={cx("glass w-full max-w-lg overflow-hidden rounded-2xl", danger && "border-danger/30")}
      role="alertdialog"
      aria-labelledby={`ap-${a.id}`}
    >
      <div className={cx("h-0.5 w-full", danger ? "bg-gradient-to-r from-danger/0 via-danger to-danger/0" : "bg-gradient-to-r from-warn/0 via-warn to-warn/0")} />
      <div className="p-5">
        <div className="flex items-start gap-3">
          <div className={cx("grid size-10 shrink-0 place-items-center rounded-xl", danger ? "bg-danger/15 text-danger" : "bg-warn/10 text-warn")}>
            {danger ? <AlertOctagon size={20} /> : <ShieldAlert size={20} />}
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h2 id={`ap-${a.id}`} className="font-display text-base font-semibold text-ink">Confirmación requerida</h2>
              <Badge tone={riskTone(a.risk)}>{a.risk}</Badge>
            </div>
            <p className="mt-0.5 text-xs text-muted">
              Solicitado desde {src} · herramienta <span className="font-mono text-lavender/80">{a.tool}</span> · caduca en <Countdown until={a.expires_at} />
            </p>
          </div>
        </div>
        <p className="mt-4 rounded-xl border border-line bg-black/25 px-3.5 py-3 text-[14px] leading-relaxed text-ink">{a.summary}</p>
        {Object.keys(a.details || {}).length > 0 && (
          <details className="mt-2 text-xs text-muted">
            <summary className="cursor-pointer select-none hover:text-ink">Ver parámetros exactos</summary>
            <pre className="mt-2 max-h-48 overflow-auto rounded-lg bg-black/30 p-2.5 font-mono text-[11px] whitespace-pre-wrap break-all">
              {JSON.stringify(a.details, null, 2)}
            </pre>
          </details>
        )}
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" disabled={busy} onClick={() => decide(false)}>Denegar</Button>
          <Button variant={danger ? "danger" : "primary"} disabled={busy} onClick={() => decide(true)}
            className={danger ? "!bg-danger/80 !text-white hover:!bg-danger" : ""}>
            Autorizar
          </Button>
        </div>
      </div>
    </motion.div>
  );
}

export function Approvals() {
  const approvals = useJarvis((s) => s.approvals);
  const first = approvals[0];
  return (
    <AnimatePresence>
      {first && (
        <motion.div
          key="ap-backdrop"
          className="fixed inset-0 z-[60] flex items-end justify-center bg-black/55 p-4 backdrop-blur-[3px] sm:items-center"
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
        >
          <ApprovalCard key={first.id} a={first} />
          {approvals.length > 1 && (
            <div className="absolute top-4 rounded-full border border-line-strong bg-abyss px-3 py-1 text-xs text-muted">
              {approvals.length - 1} confirmación(es) más en cola
            </div>
          )}
        </motion.div>
      )}
    </AnimatePresence>
  );
}

export function Toasts() {
  const toasts = useJarvis((s) => s.toasts);
  const dismiss = useJarvis((s) => s.dismissToast);
  const icon = { info: Bell, ok: CheckCircle2, warn: TriangleAlert, danger: AlertOctagon };
  return (
    <div className="pointer-events-none fixed right-4 bottom-4 z-[70] flex w-[min(380px,calc(100vw-2rem))] flex-col gap-2">
      <AnimatePresence initial={false}>
        {toasts.map((t) => {
          const Icon = icon[t.tone ?? "info"] ?? Info;
          return (
            <motion.div
              key={t.id}
              layout
              initial={{ opacity: 0, x: 40, scale: 0.96 }}
              animate={{ opacity: 1, x: 0, scale: 1 }}
              exit={{ opacity: 0, x: 40, transition: { duration: 0.18 } }}
              transition={{ type: "spring", stiffness: 420, damping: 34 }}
              className="glass pointer-events-auto flex gap-3 rounded-xl p-3.5"
            >
              <Icon size={18} className={cx("mt-0.5 shrink-0", {
                info: "text-lavender", ok: "text-ok", warn: "text-warn", danger: "text-danger" }[t.tone ?? "info"])} />
              <div className="min-w-0 flex-1">
                <div className="text-[13px] font-medium text-ink">{t.title}</div>
                <div className="mt-0.5 line-clamp-4 text-xs whitespace-pre-line text-muted">{t.message}</div>
              </div>
              <button onClick={() => dismiss(t.id)} className="self-start text-faint hover:text-ink" aria-label="Cerrar"><X size={14} /></button>
            </motion.div>
          );
        })}
      </AnimatePresence>
    </div>
  );
}
