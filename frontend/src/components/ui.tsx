import { motion } from "framer-motion";
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, TextareaHTMLAttributes } from "react";

export function cx(...c: (string | false | null | undefined)[]) {
  return c.filter(Boolean).join(" ");
}

export function Panel({ children, className, title, icon, actions }: {
  children: ReactNode; className?: string; title?: ReactNode; icon?: ReactNode; actions?: ReactNode;
}) {
  return (
    <section className={cx("glass hairline-top rounded-2xl", className)}>
      {title && (
        <header className="flex items-center justify-between gap-3 px-4 pt-3.5 pb-2">
          <h3 className="flex items-center gap-2 font-display text-[13px] font-medium tracking-wide text-lavender/90 uppercase">
            {icon}
            {title}
          </h3>
          {actions}
        </header>
      )}
      {children}
    </section>
  );
}

const btnBase =
  "inline-flex items-center justify-center gap-2 rounded-xl text-sm font-medium transition-[background,border-color,color,transform,box-shadow] duration-200 active:scale-[0.97] disabled:opacity-40 disabled:active:scale-100";

export function Button({ variant = "ghost", className, ...p }: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "ghost" | "danger" | "subtle";
}) {
  const v = {
    primary: "bg-gradient-to-b from-electric to-purple text-white px-4 py-2 shadow-[0_8px_30px_-10px_rgb(168_85_247/0.8)] hover:brightness-110",
    ghost: "border border-line-strong bg-white/[0.02] px-3.5 py-2 text-ink/90 hover:bg-white/[0.06] hover:border-lavender/30",
    subtle: "px-3 py-2 text-muted hover:text-ink hover:bg-white/[0.05]",
    danger: "border border-danger/30 bg-danger/10 px-3.5 py-2 text-danger hover:bg-danger/20",
  }[variant];
  return <button {...p} className={cx(btnBase, v, className)} />;
}

export function IconButton({ className, label, ...p }: ButtonHTMLAttributes<HTMLButtonElement> & { label: string }) {
  return (
    <button
      {...p}
      aria-label={label}
      title={label}
      className={cx(
        "grid size-9 place-items-center rounded-xl text-muted transition-colors duration-150 hover:bg-white/[0.06] hover:text-ink active:scale-95",
        className,
      )}
    />
  );
}

export function Badge({ children, tone = "default", className }: {
  children: ReactNode; tone?: "default" | "ok" | "warn" | "danger" | "purple"; className?: string;
}) {
  const t = {
    default: "border-line-strong text-muted",
    ok: "border-ok/25 text-ok bg-ok/[0.06]",
    warn: "border-warn/25 text-warn bg-warn/[0.06]",
    danger: "border-danger/30 text-danger bg-danger/[0.08]",
    purple: "border-electric/30 text-lavender bg-electric/[0.08]",
  }[tone];
  return (
    <span className={cx("inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium", t, className)}>
      {children}
    </span>
  );
}

export function riskTone(risk?: string): "ok" | "warn" | "danger" | "purple" | "default" {
  return risk === "peligroso" ? "danger" : risk === "sensible" ? "warn" : risk === "moderado" ? "purple" : "ok";
}

export function StatusDot({ tone, pulse }: { tone: "ok" | "warn" | "danger" | "idle"; pulse?: boolean }) {
  const c = { ok: "bg-ok", warn: "bg-warn", danger: "bg-danger", idle: "bg-faint" }[tone];
  return (
    <span className="relative inline-flex size-2">
      {pulse && <span className={cx("absolute inset-0 animate-ping rounded-full opacity-60", c)} />}
      <span className={cx("relative inline-flex size-2 rounded-full", c)} />
    </span>
  );
}

export function Ring({ value, label, sub, size = 76 }: { value: number; label: string; sub?: string; size?: number }) {
  const r = (size - 10) / 2;
  const circ = 2 * Math.PI * r;
  const v = Math.max(0, Math.min(100, value || 0));
  const color = v > 90 ? "#fb7185" : v > 75 ? "#fcd34d" : "url(#ringGrad)";
  return (
    <div className="flex flex-col items-center gap-1.5">
      <div className="relative" style={{ width: size, height: size }}>
        <svg width={size} height={size} className="-rotate-90">
          <defs>
            <linearGradient id="ringGrad" x1="0" x2="1">
              <stop offset="0" stopColor="#c4b5fd" />
              <stop offset="1" stopColor="#a855f7" />
            </linearGradient>
          </defs>
          <circle cx={size / 2} cy={size / 2} r={r} stroke="rgb(196 181 253 / 0.08)" strokeWidth="5" fill="none" />
          <motion.circle
            cx={size / 2} cy={size / 2} r={r} stroke={color} strokeWidth="5" fill="none" strokeLinecap="round"
            strokeDasharray={circ}
            animate={{ strokeDashoffset: circ * (1 - v / 100) }}
            transition={{ duration: 0.8, ease: [0.22, 1, 0.36, 1] }}
          />
        </svg>
        <div className="absolute inset-0 grid place-items-center">
          <span className="font-mono text-[15px] font-medium tabular-nums text-ink">{Math.round(v)}<span className="text-[10px] text-muted">%</span></span>
        </div>
      </div>
      <div className="text-center leading-tight">
        <div className="text-[11px] font-medium uppercase tracking-wider text-lavender/80">{label}</div>
        {sub && <div className="font-mono text-[10px] text-faint">{sub}</div>}
      </div>
    </div>
  );
}

export function Bar({ value, className, progress }: { value: number; className?: string; progress?: boolean }) {
  // progress: barra de avance (más es mejor); sin él, de ocupación (rojo/ámbar al llenarse)
  const v = Math.max(0, Math.min(100, value || 0));
  return (
    <div className={cx("h-1.5 overflow-hidden rounded-full bg-white/[0.06]", className)}>
      <motion.div
        className={cx("h-full rounded-full", !progress && v > 90 ? "bg-danger" : !progress && v > 75 ? "bg-warn" : "bg-gradient-to-r from-lavender to-electric")}
        animate={{ width: `${v}%` }}
        transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
      />
    </div>
  );
}

export function Toggle({ checked, onChange, label, disabled }: {
  checked: boolean; onChange: (v: boolean) => void; label?: string; disabled?: boolean;
}) {
  return (
    <button
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={cx(
        "relative h-6 w-11 shrink-0 rounded-full border transition-colors duration-200",
        checked ? "border-electric/50 bg-electric/40" : "border-line-strong bg-white/[0.04]",
      )}
    >
      <motion.span
        layout
        transition={{ type: "spring", stiffness: 500, damping: 34 }}
        className={cx("absolute top-0.5 size-[18px] rounded-full shadow", checked ? "right-0.5 bg-white" : "left-0.5 bg-muted")}
      />
    </button>
  );
}

export function Input(p: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...p}
      className={cx(
        "w-full rounded-xl border border-line-strong bg-black/20 px-3 py-2 text-ink placeholder:text-faint outline-none transition-colors focus:border-electric/50 focus:bg-black/30",
        p.className,
      )}
    />
  );
}

export function TextArea(p: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      {...p}
      className={cx(
        "w-full resize-none rounded-xl border border-line-strong bg-black/20 px-3 py-2 text-ink placeholder:text-faint outline-none transition-colors focus:border-electric/50",
        p.className,
      )}
    />
  );
}

export function Select({ value, onChange, options, className }: {
  value: string; onChange: (v: string) => void; options: { value: string; label: string }[]; className?: string;
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className={cx("w-full rounded-xl border border-line-strong bg-abyss px-3 py-2 text-ink outline-none focus:border-electric/50", className)}
    >
      {options.map((o) => (
        <option key={o.value} value={o.value}>{o.label}</option>
      ))}
    </select>
  );
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: ReactNode }) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="font-display text-2xl font-semibold tracking-tight text-ink">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-muted">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

export function Empty({ icon, title, text }: { icon: ReactNode; title: string; text?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-12 text-center">
      <div className="grid size-12 place-items-center rounded-2xl border border-line bg-white/[0.02] text-lavender/70">{icon}</div>
      <div className="font-display text-sm font-medium text-ink/90">{title}</div>
      {text && <div className="max-w-sm text-xs text-muted">{text}</div>}
    </div>
  );
}

export function timeAgo(ts?: number | null) {
  if (!ts) return "—";
  const s = Date.now() / 1000 - ts;
  if (s < 60) return "ahora";
  if (s < 3600) return `hace ${Math.floor(s / 60)} min`;
  if (s < 86400) return `hace ${Math.floor(s / 3600)} h`;
  return new Date(ts * 1000).toLocaleDateString("es-ES", { day: "numeric", month: "short" });
}

export function fmtTime(ts?: number | null) {
  if (!ts) return "—";
  return new Date(ts * 1000).toLocaleString("es-ES", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
}
