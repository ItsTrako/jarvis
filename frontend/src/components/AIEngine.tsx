import { AnimatePresence, motion } from "framer-motion";
import {
  Check, Cloud, Cpu, Download, Eye, Gauge, HardDrive, Loader2, Lock, Sparkles, Wand2, Wrench, Zap, BrainCircuit,
} from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { events, get, patch, post } from "../lib/api";
import { useJarvis } from "../lib/store";
import { Badge, Button, Select, Toggle, cx } from "./ui";

type Overview = any;

const CAP_ICON: Record<string, ReactNode> = {
  herramientas: <Wrench size={11} />, "visión": <Eye size={11} />, razonamiento: <BrainCircuit size={11} />,
};

function EngineCard({ active, onClick, icon, title, tag, desc, status, statusOk }: {
  active: boolean; onClick: () => void; icon: ReactNode; title: string; tag: string; desc: string;
  status: string; statusOk: boolean;
}) {
  return (
    <button
      onClick={onClick}
      className={cx(
        "group relative overflow-hidden rounded-2xl border p-4 text-left transition-colors duration-300",
        active ? "border-electric/50" : "border-line-strong hover:border-lavender/30",
      )}
    >
      {active && (
        <motion.div layoutId="engine-active" transition={{ type: "spring", stiffness: 380, damping: 34 }}
          className="absolute inset-0 bg-[radial-gradient(120%_90%_at_0%_0%,rgb(168_85_247/0.28),transparent_60%)]" />
      )}
      <div className="relative">
        <div className="flex items-center justify-between">
          <span className={cx("grid size-10 place-items-center rounded-xl border transition-colors",
            active ? "border-electric/40 bg-electric/20 text-white shadow-[0_0_24px_rgb(168_85_247/0.45)]" : "border-line bg-white/[0.03] text-lavender")}>
            {icon}
          </span>
          <span className={cx("grid size-5 place-items-center rounded-full border transition-all",
            active ? "border-electric bg-electric text-white" : "border-line-strong")}>
            {active && <Check size={12} strokeWidth={3} />}
          </span>
        </div>
        <div className="mt-3 font-display text-[15px] font-semibold text-ink">{title}</div>
        <div className="mt-0.5 text-[11px] font-medium tracking-wide text-lavender/90 uppercase">{tag}</div>
        <p className="mt-2 text-xs leading-relaxed text-muted">{desc}</p>
        <div className="mt-3 flex items-center gap-1.5 text-[11px]">
          <span className={cx("size-1.5 rounded-full", statusOk ? "bg-ok" : "bg-warn")} />
          <span className={statusOk ? "text-ok/90" : "text-warn/90"}>{status}</span>
        </div>
      </div>
    </button>
  );
}

function VramMeter({ gpu, modelsGb }: { gpu: any; modelsGb: number }) {
  if (!gpu) return null;
  const total = gpu.mem_total_gb;
  const used = gpu.mem_used_gb;
  const others = Math.max(0, used - modelsGb);
  const free = Math.max(0, total - used);
  const pct = (v: number) => `${Math.min(100, (v / total) * 100)}%`;
  return (
    <div className="rounded-xl border border-line bg-black/20 p-3.5">
      <div className="flex items-center justify-between text-xs">
        <span className="flex items-center gap-1.5 text-muted"><HardDrive size={13} /> Memoria de la GPU · {gpu.name}</span>
        <span className="font-mono text-ink/80">{used.toFixed(1)} / {total.toFixed(0)} GB</span>
      </div>
      <div className="relative mt-2.5 flex h-2.5 overflow-hidden rounded-full bg-white/[0.06]">
        <motion.div className="h-full bg-faint/70" animate={{ width: pct(others) }} transition={{ duration: 0.8 }} />
        <motion.div className="h-full bg-gradient-to-r from-lavender to-electric shadow-[0_0_12px_rgb(168_85_247/0.7)]"
          animate={{ width: pct(modelsGb) }} transition={{ duration: 0.8, ease: [0.22, 1, 0.36, 1] }} />
      </div>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-faint">
        <span className="flex items-center gap-1.5"><span className="size-2 rounded-sm bg-faint/70" /> Otras apps, voz y escritorio: {others.toFixed(1)} GB</span>
        <span className="flex items-center gap-1.5"><span className="size-2 rounded-sm bg-electric" /> IA local: {modelsGb.toFixed(1)} GB</span>
        <span className="flex items-center gap-1.5"><span className="size-2 rounded-sm bg-white/10" /> Libre: {free.toFixed(1)} GB</span>
      </div>
    </div>
  );
}

function ModelCard({ m, selected, pull, onUse, onPull, bench, onBench, benching, freeGb, light, active }: {
  m: any; selected: boolean; pull?: any; onUse: () => void; onPull: () => void; bench?: any;
  onBench: () => void; benching: boolean; freeGb: number; light?: boolean; active?: boolean;
}) {
  const pulling = pull?.active;
  const pct = pull?.total ? Math.round((pull.completed / pull.total) * 100) : 0;
  const fit = m.size_gb + 1.5 <= freeGb ? "ok" : m.size_gb + 0.5 <= freeGb + 1.5 ? "tight" : "no";
  return (
    <motion.div
      layout
      className={cx("relative overflow-hidden rounded-2xl border p-4 transition-colors duration-300",
        selected ? "border-electric/50 bg-electric/[0.06] shadow-[0_0_40px_-12px_rgb(168_85_247/0.6)]" : "border-line-strong bg-white/[0.015]")}
    >
      {selected && <div className="pointer-events-none absolute -top-16 -right-16 size-40 rounded-full bg-electric/25 blur-3xl" />}
      <div className="relative flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <span className="font-display text-[15px] font-semibold text-ink">{m.name}</span>
            {m.tier === "Máxima calidad" && <Badge tone="purple"><Sparkles size={10} /> Recomendado</Badge>}
            {light && <Badge>Ligero</Badge>}
            {active && <Badge tone="ok">● Activo</Badge>}
          </div>
          <div className="mt-0.5 text-[11px] text-faint">{m.vendor} · {m.tier} · contexto {m.context}</div>
        </div>
        <div className="text-right">
          <div className="font-mono text-sm text-ink">{m.size_gb} GB</div>
          <div className={cx("text-[10.5px]", fit === "ok" ? "text-ok" : fit === "tight" ? "text-warn" : "text-danger")}>
            {fit === "ok" ? "Cabe en tu GPU" : fit === "tight" ? "Justo con la GPU ocupada" : "No cabe ahora"}
          </div>
        </div>
      </div>
      <p className="relative mt-2.5 text-xs leading-relaxed text-muted">{m.blurb}</p>
      <div className="relative mt-3 flex flex-wrap gap-1.5">
        {m.caps.map((c: string) => (
          <span key={c} className="flex items-center gap-1 rounded-md border border-line bg-white/[0.03] px-1.5 py-0.5 text-[10.5px] text-lavender/90">
            {CAP_ICON[c]} {c}
          </span>
        ))}
      </div>

      <AnimatePresence>
        {pulling && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}
            className="relative mt-3.5">
            <div className="mb-1.5 flex justify-between text-[11px]">
              <span className="truncate text-muted">{pull.status}</span>
              <span className="font-mono text-lavender">{pull.total ? `${pct}%` : ""}</span>
            </div>
            <div className="h-1.5 overflow-hidden rounded-full bg-white/[0.06]">
              <motion.div className="h-full rounded-full bg-[linear-gradient(90deg,#c4b5fd,#a855f7,#c4b5fd)] bg-[length:200%_100%] animate-[shimmer_1.6s_linear_infinite]"
                animate={{ width: `${pull.total ? pct : 8}%` }} transition={{ duration: 0.5 }} />
            </div>
            {pull.total > 0 && (
              <div className="mt-1 font-mono text-[10.5px] text-faint">
                {(pull.completed / 1e9).toFixed(2)} / {(pull.total / 1e9).toFixed(2)} GB
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
      {pull?.error && <p className="relative mt-2 text-[11px] text-danger">{pull.error}</p>}

      <AnimatePresence>
        {bench && (
          <motion.div initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }}
            className="relative mt-3.5 rounded-xl border border-line bg-black/25 p-3">
            <div className="grid grid-cols-3 gap-2 text-center">
              <div><div className="font-mono text-base text-ink">{bench.tokens_per_s ?? "—"}</div><div className="text-[10px] text-faint">tokens/s</div></div>
              <div><div className={cx("text-base", bench.tool_calling ? "text-ok" : "text-danger")}>{bench.tool_calling ? "✓" : "✗"}</div><div className="text-[10px] text-faint">herramientas</div></div>
              <div><div className="font-mono text-base text-ink">{bench.total_s}s</div><div className="text-[10px] text-faint">prueba</div></div>
            </div>
            {bench.sample && <p className="mt-2.5 border-t border-line pt-2.5 text-[11.5px] leading-relaxed text-muted italic">«{bench.sample}»</p>}
          </motion.div>
        )}
      </AnimatePresence>

      <div className="relative mt-4 flex gap-2">
        {m.installed ? (
          <>
            <Button variant={selected ? "subtle" : "primary"} disabled={selected} onClick={onUse} className="flex-1">
              {selected ? <><Check size={14} /> Principal</> : "Usar como principal"}
            </Button>
            <Button variant="ghost" onClick={onBench} disabled={benching} title="Medir velocidad y uso de herramientas">
              {benching ? <Loader2 size={14} className="animate-spin" /> : <Gauge size={14} />} Probar
            </Button>
          </>
        ) : (
          <Button variant="ghost" onClick={onPull} disabled={pulling} className="flex-1">
            {pulling ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />}
            {pulling ? "Descargando…" : `Descargar · ${m.size_gb} GB`}
          </Button>
        )}
      </div>
    </motion.div>
  );
}

function AdaptiveCard({ local, onChange }: { local: any; onChange: (p: Record<string, unknown>) => void }) {
  const name = (id: string) => local.catalog.find((c: any) => c.id === id)?.name ?? id;
  const installed = [...local.catalog.filter((c: any) => c.installed).map((c: any) => c.id),
    ...local.models.map((m: any) => m.name).filter((n: string) => !n.startsWith("hf.co/") && !local.catalog.some((c: any) => c.id === n))];
  const lightActive = local.adaptive && local.active_model === local.light && local.light !== local.selected;
  const Slot = ({ label, id, active, onPick }: { label: string; id: string; active: boolean; onPick?: (v: string) => void }) => (
    <div className={cx("relative flex-1 rounded-xl border p-3 transition-all duration-500",
      active ? "border-electric/50 bg-electric/[0.10] shadow-[0_0_30px_-10px_rgb(168_85_247/0.8)]" : "border-line bg-black/20")}>
      <div className="flex items-center justify-between text-[10.5px] tracking-wider text-faint uppercase">
        {label}
        {active && (
          <span className="flex items-center gap-1 text-lavender normal-case tracking-normal">
            <span className="relative flex size-1.5"><span className="absolute inset-0 animate-ping rounded-full bg-electric" /><span className="relative size-1.5 rounded-full bg-electric" /></span>
            pensando ahora
          </span>
        )}
      </div>
      {onPick ? (
        <select value={id} onChange={(e) => onPick(e.target.value)}
          className="mt-1 w-full cursor-pointer bg-transparent font-display text-[14px] font-semibold text-ink outline-none">
          {installed.map((n: string) => <option key={n} value={n} className="bg-abyss">{name(n)}</option>)}
        </select>
      ) : <div className="mt-1 font-display text-[14px] font-semibold text-ink">{name(id)}</div>}
    </div>
  );
  return (
    <div className="mt-4 rounded-2xl border border-line-strong bg-gradient-to-br from-white/[0.03] to-transparent p-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 font-display text-[14px] font-semibold text-ink"><Gauge size={15} className="text-lavender" /> Modo adaptativo</div>
          <p className="mt-1 max-w-xl text-xs leading-relaxed text-muted">
            Usa el modelo principal cuando la GPU está libre y cambia solo al ligero cuando escasea la memoria
            (por ejemplo, mientras juegas). Nunca cambia a mitad de una tarea.
          </p>
        </div>
        <Toggle checked={local.adaptive} onChange={(v) => onChange({ local_adaptive: v })} label="Modo adaptativo" />
      </div>
      <div className="mt-3.5 flex flex-col gap-2 sm:flex-row sm:items-stretch">
        <Slot label="Principal" id={local.selected} active={!lightActive} onPick={(v) => onChange({ local_model: v })} />
        {local.adaptive && (
          <>
            <div className="hidden items-center text-faint sm:flex">⇄</div>
            <Slot label="Ligero" id={local.light} active={lightActive} onPick={(v) => onChange({ local_light_model: v })} />
          </>
        )}
      </div>
      <AnimatePresence>
        {lightActive && local.route_reason && (
          <motion.p initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}
            className="mt-2.5 flex items-center gap-1.5 text-[11.5px] text-warn/90">
            <Zap size={12} /> {local.route_reason}. Volverá al principal cuando haya memoria libre.
          </motion.p>
        )}
      </AnimatePresence>
    </div>
  );
}

export function AIEngine() {
  const [ov, setOv] = useState<Overview | null>(null);
  const [pulls, setPulls] = useState<Record<string, any>>({});
  const [bench, setBench] = useState<Record<string, any>>({});
  const [benching, setBenching] = useState<string | null>(null);
  const refreshStatus = useJarvis((s) => s.refreshStatus);
  const toast = useJarvis((s) => s.toast);

  const load = async () => {
    const o = await get("/api/llm");
    setOv(o);
    setPulls((p) => ({ ...o.pulls, ...Object.fromEntries(Object.entries(p).filter(([, v]: any) => v.active)) }));
  };
  useEffect(() => {
    void load();
    const off = events.on((ev) => {
      if (ev.type === "model_pull") {
        setPulls((p) => ({ ...p, [ev.model]: ev }));
        if (!ev.active) {
          void load();
          if (ev.status === "completado") toast({ title: "Modelo descargado", message: `${ev.model} listo para usar.`, tone: "ok" });
        }
      }
    });
    return () => { off(); };
  }, []);

  if (!ov) return <div className="grid place-items-center py-10"><Loader2 className="animate-spin text-lavender" /></div>;

  const setEngine = async (provider: string) => {
    await patch("/api/config", { llm: { provider } });
    await load();
    await refreshStatus(true);
  };
  const useModel = async (id: string) => {
    await patch("/api/config", { llm: { local_model: id } });
    await load();
    await refreshStatus(true);
  };
  const local = ov.local;
  const selectedCat = local.catalog.find((c: any) => c.id === local.selected);
  const modelsGb = Object.values(local.loaded_vram ?? {}).reduce((a: number, b: any) => a + Number(b), 0);
  // Memoria disponible para modelos = total - lo que usan otras apps (los modelos se intercambian)
  const freeGb = ov.gpu ? ov.gpu.mem_total_gb - Math.max(0, ov.gpu.mem_used_gb - modelsGb) : 8;
  const localReady = local.running && local.catalog.concat(local.models.map((m: any) => ({ id: m.name, installed: true })))
    .some((c: any) => c.id === local.selected && c.installed);
  const others = local.models.filter((m: any) => !local.catalog.some((c: any) => c.id === m.name) && !m.name.startsWith("hf.co/"));

  return (
    <div className="space-y-6">
      <section>
        <div className="mb-3 flex items-end justify-between">
          <div>
            <h2 className="font-display text-lg font-semibold text-ink">Motor de IA</h2>
            <p className="text-xs text-muted">Elige quién piensa por JARVIS. Memoria, herramientas, voz, Telegram y permisos son los mismos con cualquier motor.</p>
          </div>
          <Badge tone="purple">Activo: {ov.active === "anthropic" ? "Claude" : "Local"}</Badge>
        </div>
        <div className="grid gap-3 md:grid-cols-3">
          <EngineCard active={ov.setting === "auto"} onClick={() => setEngine("auto")} icon={<Wand2 size={19} />}
            title="Automático" tag="Recomendado" desc="Usa Claude si tienes API key; si no, el modelo local gratuito. Sin pensar en nada."
            status={ov.active === "anthropic" ? "Ahora mismo: Claude" : "Ahora mismo: local"} statusOk />
          <EngineCard active={ov.setting === "anthropic"} onClick={() => setEngine("anthropic")} icon={<Cloud size={19} />}
            title="Claude · Nube" tag="Máxima inteligencia" desc="El razonamiento más potente, búsqueda web integrada y planificación compleja. Pago por uso."
            status={ov.cloud.configured ? `API key lista · ${ov.cloud.model}` : "Falta la API key"} statusOk={ov.cloud.configured} />
          <EngineCard active={ov.setting === "ollama"} onClick={() => setEngine("ollama")} icon={<Cpu size={19} />}
            title="Local · Gratis" tag="100 % privado" desc="Un modelo abierto en tu propia GPU. Sin coste, sin claves, funciona sin Internet."
            status={!local.installed_app ? "Ollama no instalado" : localReady ? `${selectedCat?.name ?? local.selected} listo` : "Descarga un modelo"}
            statusOk={localReady} />
        </div>
      </section>

      <section className="glass hairline-top rounded-2xl p-5">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <span className="grid size-9 place-items-center rounded-xl bg-electric/15 text-lavender"><Cpu size={17} /></span>
            <div>
              <div className="font-display text-[15px] font-semibold text-ink">Modelos locales</div>
              <div className="text-[11px] text-faint">
                {local.running ? `Ollama ${local.version} en marcha` : local.installed_app ? "Ollama se arrancará automáticamente" : "Instala Ollama desde ollama.com"}
                {local.loaded?.length ? ` · cargado: ${local.loaded.join(", ")}` : ""}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-1.5 text-[11px] text-muted"><Lock size={12} /> Tus conversaciones no salen del PC</div>
        </div>

        <VramMeter gpu={ov.gpu} modelsGb={modelsGb} />

        <AdaptiveCard local={local} onChange={async (p) => { await patch("/api/config", { llm: p }); await load(); await refreshStatus(true); }} />

        <div className="mt-4 grid gap-3 lg:grid-cols-2">
          {local.catalog.map((m: any) => (
            <ModelCard key={m.id} m={m} selected={local.selected === m.id} pull={pulls[m.id]} freeGb={freeGb}
              light={local.adaptive && local.light === m.id && local.selected !== m.id}
              active={ov.active === "ollama" && local.active_model === m.id}
              onUse={() => useModel(m.id)}
              onPull={async () => { setPulls((p) => ({ ...p, [m.id]: { active: true, status: "Conectando…" } })); await post("/api/llm/pull", { model: m.id }); }}
              bench={bench[m.id]} benching={benching === m.id}
              onBench={async () => {
                setBenching(m.id);
                try { const r = await post("/api/llm/benchmark", { model: m.id }); setBench((b) => ({ ...b, [m.id]: r })); }
                catch (e: any) { toast({ title: "Prueba fallida", message: e.message, tone: "danger" }); }
                finally { setBenching(null); void load(); }
              }} />
          ))}
        </div>

        {others.length > 0 && (
          <div className="mt-5">
            <div className="mb-2 text-[11px] tracking-wider text-faint uppercase">Otros modelos instalados</div>
            <div className="flex flex-wrap gap-2">
              {others.map((m: any) => (
                <button key={m.name} onClick={() => useModel(m.name)}
                  className={cx("flex items-center gap-2 rounded-xl border px-3 py-1.5 text-xs transition-colors",
                    local.selected === m.name ? "border-electric/50 bg-electric/15 text-ink" : "border-line-strong text-muted hover:text-ink")}>
                  {local.selected === m.name && <Check size={12} />} {m.name}
                  <span className="font-mono text-faint">{m.params} · {m.size_gb} GB</span>
                </button>
              ))}
            </div>
          </div>
        )}

        <div className="mt-5 grid gap-3 border-t border-line pt-4 sm:grid-cols-2">
          <label className="block">
            <span className="mb-1.5 flex items-center gap-1.5 text-xs text-muted"><BrainCircuit size={13} /> Razonamiento del modelo local</span>
            <Select value={local.thinking} onChange={async (v) => { await patch("/api/config", { llm: { local_thinking: v } }); void load(); }}
              options={[{ value: "auto", label: "Automático (en tareas complejas)" }, { value: "on", label: "Siempre (más preciso, más lento)" },
                        { value: "off", label: "Nunca (respuestas más rápidas)" }]} />
          </label>
          <label className="block">
            <span className="mb-1.5 flex items-center gap-1.5 text-xs text-muted"><Zap size={13} /> Memoria de conversación (contexto)</span>
            <Select value={String(local.context)} onChange={async (v) => { await patch("/api/config", { llm: { local_context: parseInt(v) } }); void load(); }}
              options={[{ value: "8192", label: "8K tokens (más rápido, menos memoria)" }, { value: "16384", label: "16K tokens (recomendado)" },
                        { value: "32768", label: "32K tokens (documentos largos, más VRAM)" }]} />
          </label>
        </div>
      </section>
    </div>
  );
}
