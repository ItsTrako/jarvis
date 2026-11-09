import { History as HistoryIcon, RefreshCw } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { get } from "../lib/api";
import { Badge, Button, Empty, PageHeader, Panel, cx } from "../components/ui";

const EVENT_LABEL: Record<string, string> = {
  tool_executed: "Herramienta ejecutada", tool_denied: "Acción denegada", tool_blocked: "Bloqueada por seguridad",
  tool_error: "Error de herramienta", approval_requested: "Confirmación solicitada", approval_decision: "Decisión",
  approval_timeout: "Confirmación caducada", emergency_stop: "Parada de emergencia", unauthorized: "Acceso no autorizado",
  rate_limited: "Límite de peticiones", pair_attempt: "Emparejamiento", pin_ok: "PIN correcto", pin_fail: "PIN incorrecto",
  config_changed: "Configuración cambiada", secret_set: "Credencial guardada", secret_deleted: "Credencial eliminada",
  memory_deleted: "Recuerdo eliminado", automation_created: "Rutina creada", autostart: "Inicio automático",
};

export function HistoryPage() {
  const [rows, setRows] = useState<any[]>([]);
  const [filter, setFilter] = useState("all");
  const load = () => get("/api/audit?limit=500").then(setRows).catch(() => undefined);
  useEffect(() => { void load(); }, []);

  const shown = useMemo(() => rows.filter((r) => filter === "all" ? true : filter === "security"
    ? ["tool_denied", "tool_blocked", "unauthorized", "pin_fail", "emergency_stop", "rate_limited", "approval_timeout"].includes(r.event)
    : r.source === filter), [rows, filter]);

  const tone = (r: any) => ["denied", "blocked", "error", "fail"].includes(r.decision) || r.event === "unauthorized" ? "danger"
    : r.decision === "approved" || r.decision === "ok" ? "ok" : r.decision === "pending" ? "warn" : "default";

  return (
    <div className="h-full overflow-y-auto p-4 sm:p-6">
      <div className="mx-auto max-w-5xl">
        <PageHeader title="Historial de actividad" subtitle="Registro de auditoría: cada acción, confirmación y evento de seguridad, desde cualquier interfaz."
          actions={<Button variant="ghost" onClick={load}><RefreshCw size={15} /> Actualizar</Button>} />
        <div className="mb-4 flex flex-wrap gap-1">
          {[["all", "Todo"], ["ui", "PC"], ["voice", "Voz"], ["telegram", "Telegram"], ["job", "Trabajos"], ["automation", "Rutinas"], ["security", "Seguridad"]].map(([k, l]) => (
            <button key={k} onClick={() => setFilter(k)}
              className={cx("rounded-lg px-3 py-1.5 text-xs transition-colors", filter === k ? "bg-electric/20 text-lavender" : "text-muted hover:text-ink")}>{l}</button>
          ))}
        </div>
        <Panel>
          {shown.length === 0 ? <Empty icon={<HistoryIcon size={20} />} title="Sin actividad registrada" /> : (
            <ul className="divide-y divide-line">
              {shown.map((r) => (
                <li key={r.id} className="flex items-start gap-3 px-4 py-2.5">
                  <span className="w-24 shrink-0 pt-0.5 font-mono text-[11px] text-faint">
                    {new Date(r.ts * 1000).toLocaleString("es-ES", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit" })}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-[13px] text-ink">{EVENT_LABEL[r.event] ?? r.event}</span>
                      {r.tool && <span className="font-mono text-[11px] text-lavender/80">{r.tool}</span>}
                      <Badge>{r.source}</Badge>
                      {r.risk && <Badge tone={r.risk === "peligroso" ? "danger" : r.risk === "sensible" ? "warn" : "default"}>{r.risk}</Badge>}
                      {r.decision && <Badge tone={tone(r) as any}>{r.decision}</Badge>}
                    </div>
                    {r.detail && <p className="mt-0.5 truncate text-xs text-muted" title={r.detail}>{r.detail}</p>}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>
    </div>
  );
}
