import { CalendarClock, CheckCircle2, Clock, ListTodo, Loader2, Play, Plus, Rocket, Square, Trash2, XCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { del, get, patch, post } from "../lib/api";
import { useJarvis } from "../lib/store";
import { PlanView } from "../components/Panels";
import { Badge, Button, Empty, Input, PageHeader, Panel, Select, TextArea, Toggle, cx, fmtTime, timeAgo } from "../components/ui";

function scheduleText(a: any) {
  if (a.schedule_type === "interval") return `Cada ${a.schedule_value} min`;
  if (a.schedule_type === "daily") return `Cada día · ${a.schedule_value}`;
  return `Semanal · ${a.schedule_value}`;
}

function NewAutomation({ onDone }: { onDone: () => void }) {
  const [f, setF] = useState({ name: "", prompt: "", schedule_type: "daily", schedule_value: "08:30", notify: "all" });
  const [err, setErr] = useState("");
  return (
    <Panel className="mb-4 p-4">
      <div className="grid gap-3 sm:grid-cols-2">
        <Input placeholder="Nombre (p. ej. Resumen de la mañana)" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />
        <div className="flex gap-2">
          <Select value={f.schedule_type} onChange={(v) => setF({ ...f, schedule_type: v, schedule_value: v === "interval" ? "60" : v === "weekly" ? "lun,mie,vie 09:00" : "08:30" })}
            options={[{ value: "daily", label: "Diaria" }, { value: "weekly", label: "Semanal" }, { value: "interval", label: "Intervalo" }]} />
          <Input value={f.schedule_value} onChange={(e) => setF({ ...f, schedule_value: e.target.value })}
            placeholder={f.schedule_type === "interval" ? "minutos" : f.schedule_type === "weekly" ? "lun,mie 09:00" : "HH:MM"} />
        </div>
        <TextArea rows={3} className="sm:col-span-2" placeholder="Qué debe hacer JARVIS en cada ejecución. Ej.: Revisa el estado del PC, mis tareas pendientes y el tiempo en Madrid y envíame un resumen breve."
          value={f.prompt} onChange={(e) => setF({ ...f, prompt: e.target.value })} />
        <Select value={f.notify} onChange={(v) => setF({ ...f, notify: v })}
          options={[{ value: "all", label: "Notificar en escritorio y Telegram" }, { value: "desktop", label: "Solo escritorio" },
                    { value: "telegram", label: "Solo Telegram" }, { value: "none", label: "Sin notificación" }]} />
        <div className="flex items-center justify-end gap-2">
          {err && <span className="text-xs text-danger">{err}</span>}
          <Button variant="subtle" onClick={onDone}>Cancelar</Button>
          <Button variant="primary" disabled={!f.name || !f.prompt} onClick={async () => {
            try { await post("/api/automations", f); onDone(); } catch (e: any) { setErr(e.message); }
          }}>Crear</Button>
        </div>
      </div>
    </Panel>
  );
}

export function Automations() {
  const [autos, setAutos] = useState<any[]>([]);
  const [tasks, setTasks] = useState<any[]>([]);
  const [showNew, setShowNew] = useState(false);
  const [newTask, setNewTask] = useState("");
  const [jobPrompt, setJobPrompt] = useState("");
  const jobs = useJarvis((s) => s.jobs);
  const va = useJarvis((s) => s.versions.automations ?? 0);
  const vt = useJarvis((s) => s.versions.tasks ?? 0);

  const loadAutos = () => get("/api/automations").then(setAutos).catch(() => undefined);
  const loadTasks = () => get("/api/tasks?status=all").then(setTasks).catch(() => undefined);
  useEffect(() => { void loadAutos(); }, [va]);
  useEffect(() => { void loadTasks(); }, [vt]);
  useEffect(() => {
    get("/api/jobs").then((j) => useJarvis.setState({ jobs: j })).catch(() => undefined);
  }, []);

  const jobIcon = (s: string) => s === "running" || s === "queued" ? <Loader2 size={15} className="animate-spin text-lavender" />
    : s === "done" ? <CheckCircle2 size={15} className="text-ok" /> : <XCircle size={15} className="text-danger" />;

  return (
    <div className="h-full overflow-y-auto p-4 sm:p-6">
      <div className="mx-auto max-w-6xl">
        <PageHeader title="Automatizaciones" subtitle="Rutinas programadas, trabajos en segundo plano y tus tareas pendientes."
          actions={<Button variant="primary" onClick={() => setShowNew(true)}><Plus size={16} /> Nueva rutina</Button>} />
        {showNew && <NewAutomation onDone={() => { setShowNew(false); void loadAutos(); }} />}

        <div className="grid gap-4 lg:grid-cols-2">
          <Panel title="Rutinas programadas" icon={<CalendarClock size={14} />}>
            {autos.length === 0 ? (
              <Empty icon={<CalendarClock size={20} />} title="Sin rutinas" text="Ej.: «JARVIS, cada día a las 8:30 envíame un resumen de mis tareas y del tiempo»." />
            ) : (
              <ul className="divide-y divide-line">
                {autos.map((a) => (
                  <li key={a.id} className="px-4 py-3">
                    <div className="flex items-center gap-3">
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-[14px] text-ink">{a.name}</div>
                        <div className="mt-0.5 flex flex-wrap items-center gap-2 text-[11px] text-faint">
                          <Badge tone="purple"><Clock size={10} /> {scheduleText(a)}</Badge>
                          <span>Próxima: {fmtTime(a.next_run)}</span>
                          {a.last_run && <span>· Última: {timeAgo(a.last_run)}</span>}
                        </div>
                      </div>
                      <button title="Ejecutar ahora" className="rounded-lg p-2 text-faint hover:bg-white/[0.05] hover:text-lavender"
                        onClick={() => post(`/api/automations/${a.id}/run`)}><Play size={14} /></button>
                      <Toggle checked={a.enabled} label="Activa" onChange={async (v) => { await patch(`/api/automations/${a.id}`, { enabled: v }); void loadAutos(); }} />
                      <button title="Eliminar" className="rounded-lg p-2 text-faint hover:bg-danger/10 hover:text-danger"
                        onClick={async () => { if (confirm(`¿Eliminar «${a.name}»?`)) { await del(`/api/automations/${a.id}`); void loadAutos(); } }}>
                        <Trash2 size={14} />
                      </button>
                    </div>
                    <p className="mt-2 line-clamp-2 text-xs text-muted">{a.prompt}</p>
                  </li>
                ))}
              </ul>
            )}
          </Panel>

          <Panel title="Trabajos en segundo plano" icon={<Rocket size={14} />}>
            <div className="flex gap-2 px-4 pb-3">
              <Input value={jobPrompt} onChange={(e) => setJobPrompt(e.target.value)} placeholder="Lanzar un trabajo: «Investiga… y prepara un informe»" />
              <Button variant="ghost" disabled={!jobPrompt.trim()} onClick={async () => {
                await post("/api/jobs", { title: jobPrompt.slice(0, 60), prompt: jobPrompt });
                setJobPrompt("");
              }}>Lanzar</Button>
            </div>
            {jobs.length === 0 ? (
              <Empty icon={<Rocket size={20} />} title="Sin trabajos" text="Los trabajos largos se ejecutan aquí y te avisan al terminar." />
            ) : (
              <ul className="max-h-[480px] divide-y divide-line overflow-y-auto">
                {jobs.map((j) => (
                  <li key={j.id} className="px-4 py-3">
                    <details>
                      <summary className="flex cursor-pointer list-none items-center gap-2.5">
                        {jobIcon(j.status)}
                        <span className="min-w-0 flex-1 truncate text-[13.5px] text-ink">{j.title}</span>
                        <span className="text-[11px] text-faint">{timeAgo(j.created_at)}</span>
                        {(j.status === "running" || j.status === "queued") && (
                          <button onClick={(e) => { e.preventDefault(); void post(`/api/jobs/${j.id}/cancel`); }} className="text-faint hover:text-danger" title="Detener">
                            <Square size={12} fill="currentColor" />
                          </button>
                        )}
                      </summary>
                      <div className="mt-3 space-y-3 pl-6">
                        {j.plan?.length > 0 && <PlanView steps={j.plan} />}
                        {j.result && <p className="max-h-48 overflow-y-auto text-xs whitespace-pre-wrap text-muted">{j.result}</p>}
                        {j.error && <p className="text-xs text-danger">{j.error}</p>}
                      </div>
                    </details>
                  </li>
                ))}
              </ul>
            )}
          </Panel>

          <Panel title="Tareas" icon={<ListTodo size={14} />} className="lg:col-span-2">
            <form className="flex gap-2 px-4 pb-3" onSubmit={async (e) => {
              e.preventDefault();
              if (!newTask.trim()) return;
              await post("/api/tasks", { title: newTask });
              setNewTask("");
            }}>
              <Input value={newTask} onChange={(e) => setNewTask(e.target.value)} placeholder="Añadir tarea…" />
              <Button variant="ghost" type="submit"><Plus size={15} /></Button>
            </form>
            <ul className="grid gap-x-6 px-2 pb-3 sm:grid-cols-2">
              {tasks.map((t) => (
                <li key={t.id} className="group flex items-center gap-2.5 rounded-lg px-2 py-2 hover:bg-white/[0.02]">
                  <button aria-label="Cambiar estado"
                    onClick={() => patch(`/api/tasks/${t.id}`, { status: t.status === "done" ? "pending" : "done" })}
                    className={cx("grid size-4 shrink-0 place-items-center rounded-full border transition-colors",
                      t.status === "done" ? "border-ok bg-ok/30" : "border-line-strong hover:border-ok")}>
                    {t.status === "done" && <CheckCircle2 size={10} className="text-ok" />}
                  </button>
                  <span className={cx("min-w-0 flex-1 truncate text-[13px]", t.status === "done" ? "text-faint line-through" : "text-ink/90")}>{t.title}</span>
                  {t.project && <Badge>{t.project}</Badge>}
                  {t.priority !== "normal" && <Badge tone={t.priority === "urgent" ? "danger" : t.priority === "high" ? "warn" : "default"}>{t.priority}</Badge>}
                  <button className="text-faint opacity-0 group-hover:opacity-100 hover:text-danger" aria-label="Eliminar"
                    onClick={() => del(`/api/tasks/${t.id}`)}><Trash2 size={13} /></button>
                </li>
              ))}
            </ul>
          </Panel>
        </div>
      </div>
    </div>
  );
}
