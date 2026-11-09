import { AnimatePresence, motion } from "framer-motion";
import { CheckCircle2, Circle, CircleDot, Cpu, ListTodo, Loader2, Square, Target, XCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { get, patch, post } from "../lib/api";
import { useJarvis, type PlanStep } from "../lib/store";
import { Bar, Panel, Ring, cx, timeAgo } from "./ui";

function StepIcon({ s }: { s: PlanStep["status"] }) {
  if (s === "done") return <CheckCircle2 size={15} className="text-ok" />;
  if (s === "in_progress") return <Loader2 size={15} className="animate-spin text-lavender" />;
  if (s === "failed") return <XCircle size={15} className="text-danger" />;
  return <Circle size={15} className="text-faint" />;
}

export function PlanView({ steps, goal }: { steps: PlanStep[]; goal?: string }) {
  const done = steps.filter((s) => s.status === "done").length;
  return (
    <div className="space-y-2.5">
      {goal && <div className="text-[13px] text-ink/90">{goal}</div>}
      <Bar progress value={steps.length ? (done / steps.length) * 100 : 0} />
      <ol className="space-y-1.5">
        {steps.map((s, i) => (
          <motion.li key={i} layout className="flex items-start gap-2.5 text-[12.5px]">
            <span className="mt-0.5"><StepIcon s={s.status} /></span>
            <span className={cx(s.status === "done" ? "text-muted line-through decoration-faint" : s.status === "in_progress" ? "text-ink" : "text-muted")}>
              {s.title}
            </span>
          </motion.li>
        ))}
      </ol>
    </div>
  );
}

export function ActivityPanel() {
  const plan = useJarvis((s) => s.plan);
  const busy = useJarvis((s) => s.busy);
  const jobs = useJarvis((s) => s.jobs);
  const active = jobs.filter((j) => j.status === "running" || j.status === "queued");
  const recent = jobs.filter((j) => !(j.status === "running" || j.status === "queued")).slice(0, 3);
  const nothing = !plan && !active.length && !recent.length;
  return (
    <Panel title="Tareas activas" icon={<Target size={14} />}>
      <div className="space-y-4 px-4 pb-4">
        <AnimatePresence>
          {plan && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              className="rounded-xl border border-electric/20 bg-electric/[0.05] p-3">
              <div className="mb-2 flex items-center gap-2 text-[11px] tracking-wider text-lavender uppercase">
                {busy ? <CircleDot size={12} className="animate-pulse" /> : <CheckCircle2 size={12} />} Plan en curso
              </div>
              <PlanView steps={plan.steps} goal={plan.goal} />
            </motion.div>
          )}
        </AnimatePresence>
        {active.map((j) => (
          <div key={j.id} className="rounded-xl border border-line bg-white/[0.02] p-3">
            <div className="flex items-center gap-2">
              <Loader2 size={14} className="animate-spin text-lavender" />
              <span className="min-w-0 flex-1 truncate text-[13px] text-ink">{j.title}</span>
              <button className="text-faint hover:text-danger" title="Detener" onClick={() => post(`/api/jobs/${j.id}/cancel`)}>
                <Square size={12} fill="currentColor" />
              </button>
            </div>
            {j.plan?.length > 0 && <div className="mt-2.5"><PlanView steps={j.plan} /></div>}
          </div>
        ))}
        {recent.map((j) => (
          <div key={j.id} className="flex items-center gap-2 text-[12.5px]">
            {j.status === "done" ? <CheckCircle2 size={14} className="text-ok" /> : <XCircle size={14} className="text-danger" />}
            <span className="min-w-0 flex-1 truncate text-muted">{j.title}</span>
            <span className="text-[11px] text-faint">{timeAgo(j.finished_at)}</span>
          </div>
        ))}
        {nothing && <p className="py-2 text-center text-xs text-faint">Sin tareas en curso. Pide algo complejo y verás aquí el plan.</p>}
      </div>
    </Panel>
  );
}

export function SystemMini() {
  const stats = useJarvis((s) => s.stats);
  const gpu = stats?.gpu?.[0];
  return (
    <Panel title="Sistema" icon={<Cpu size={14} />}>
      <div className="grid grid-cols-3 gap-2 px-3 pb-4">
        <Ring value={stats?.cpu?.percent ?? 0} label="CPU" sub={stats?.cpu?.temp_c ? `${stats.cpu.temp_c}°C` : `${stats?.cpu?.freq_mhz ?? "—"} MHz`} />
        <Ring value={stats?.ram?.percent ?? 0} label="RAM" sub={stats ? `${stats.ram.used_gb}/${stats.ram.total_gb} GB` : ""} />
        <Ring value={gpu?.util ?? 0} label="GPU" sub={gpu ? `${gpu.temp_c ?? "—"}°C · ${gpu.mem_used_gb} GB` : "—"} />
      </div>
      {stats?.net && (
        <div className="flex justify-between border-t border-line px-4 py-2.5 font-mono text-[10.5px] text-faint">
          <span>↓ {stats.net.down_kbps} KB/s</span>
          <span>↑ {stats.net.up_kbps} KB/s</span>
          <span>{Math.floor(stats.uptime_s / 3600)} h encendido</span>
        </div>
      )}
    </Panel>
  );
}

export function TasksMini() {
  const [tasks, setTasks] = useState<any[]>([]);
  const v = useJarvis((s) => s.versions.tasks ?? 0);
  useEffect(() => {
    get("/api/tasks?status=open").then(setTasks).catch(() => undefined);
  }, [v]);
  const prio: Record<string, string> = { urgent: "bg-danger", high: "bg-warn", normal: "bg-electric", low: "bg-faint" };
  return (
    <Panel title={`Pendientes · ${tasks.length}`} icon={<ListTodo size={14} />}>
      <ul className="max-h-64 space-y-0.5 overflow-y-auto px-2 pb-3">
        {tasks.length === 0 && <li className="py-3 text-center text-xs text-faint">Nada pendiente. Dile a JARVIS «apunta…».</li>}
        {tasks.map((t) => (
          <li key={t.id} className="group flex items-center gap-2.5 rounded-lg px-2 py-1.5 hover:bg-white/[0.03]">
            <button
              aria-label="Completar"
              onClick={() => patch(`/api/tasks/${t.id}`, { status: "done" })}
              className="grid size-4 shrink-0 place-items-center rounded-full border border-line-strong transition-colors hover:border-ok hover:bg-ok/20"
            />
            <span className={cx("size-1.5 shrink-0 rounded-full", prio[t.priority] ?? "bg-faint")} />
            <span className="min-w-0 flex-1 truncate text-[13px] text-ink/90">{t.title}</span>
            {t.project && <span className="hidden truncate text-[10.5px] text-faint sm:inline">{t.project}</span>}
          </li>
        ))}
      </ul>
    </Panel>
  );
}
