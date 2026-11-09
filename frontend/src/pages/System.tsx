import { AppWindow, Bot, Cpu, HardDrive, MemoryStick, Mic, MonitorCog, Network, RefreshCw, Send, Thermometer } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { get } from "../lib/api";
import { useJarvis } from "../lib/store";
import { Badge, Bar, Button, PageHeader, Panel, Ring, StatusDot } from "../components/ui";

function Spark({ data, max = 100 }: { data: number[]; max?: number }) {
  const w = 220;
  const h = 44;
  const pts = data.map((v, i) => `${(i / Math.max(1, data.length - 1)) * w},${h - (Math.min(v, max) / max) * (h - 4) - 2}`).join(" ");
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="h-11 w-full" preserveAspectRatio="none">
      <defs>
        <linearGradient id="sparkFill" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0" stopColor="#a855f7" stopOpacity="0.35" />
          <stop offset="1" stopColor="#a855f7" stopOpacity="0" />
        </linearGradient>
      </defs>
      {data.length > 1 && <polygon points={`0,${h} ${pts} ${w},${h}`} fill="url(#sparkFill)" />}
      {data.length > 1 && <polyline points={pts} fill="none" stroke="#c4b5fd" strokeWidth="1.5" vectorEffect="non-scaling-stroke" />}
    </svg>
  );
}

function fmtUptime(s: number) {
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  return `${d ? `${d} d ` : ""}${h} h ${m} min`;
}

export function SystemPage() {
  const stats = useJarvis((s) => s.stats);
  const status = useJarvis((s) => s.status);
  const refreshStatus = useJarvis((s) => s.refreshStatus);
  const [detail, setDetail] = useState<any>(null);
  const hist = useRef<{ cpu: number[]; ram: number[]; gpu: number[] }>({ cpu: [], ram: [], gpu: [] });

  useEffect(() => {
    const load = () => get("/api/system").then(setDetail).catch(() => undefined);
    void load();
    const t = window.setInterval(load, 6000);
    return () => window.clearInterval(t);
  }, []);
  if (stats) {
    const h = hist.current;
    const push = (a: number[], v: number) => { a.push(v); if (a.length > 60) a.shift(); };
    if (h.cpu.length === 0 || stats.ts !== (h as any)._ts) {
      push(h.cpu, stats.cpu.percent);
      push(h.ram, stats.ram.percent);
      push(h.gpu, stats.gpu?.[0]?.util ?? 0);
      (h as any)._ts = stats.ts;
    }
  }
  const s = stats ?? detail;
  const gpu = s?.gpu?.[0];
  const st = s?.static;

  const services = [
    { icon: Bot, name: "Modelo de IA", ok: status?.model?.ok, text: status?.model?.ok ? `${status.model.display_name} · esfuerzo ${status.model.effort}` : status?.model?.detail ?? "—" },
    { icon: Send, name: "Telegram", ok: status?.telegram?.status === "conectado", text: status?.telegram?.status === "conectado" ? `@${status.telegram.bot} · ${status.telegram.authorized_users.length} usuario(s)` : status?.telegram?.status },
    { icon: Mic, name: "Reconocimiento de voz", ok: status?.voice?.stt?.loaded, text: status?.voice?.stt?.loaded ? `Whisper ${status.voice.stt.model} · ${status.voice.stt.device}` : status?.voice?.stt?.error || "Cargando modelo…" },
    { icon: Mic, name: "Síntesis de voz", ok: true, text: `${status?.voice?.tts_engine} · ${status?.voice?.voice}` },
  ];

  return (
    <div className="h-full overflow-y-auto p-4 sm:p-6">
      <div className="mx-auto max-w-6xl">
        <PageHeader title="Sistema" subtitle={st ? `${st.hostname} · ${st.os}` : "Estado del ordenador y de los servicios de JARVIS"}
          actions={<Button variant="ghost" onClick={() => refreshStatus(true)}><RefreshCw size={15} /> Comprobar servicios</Button>} />

        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <Panel title="CPU" icon={<Cpu size={14} />}>
            <div className="flex items-center gap-4 px-4 pb-2">
              <Ring value={s?.cpu?.percent ?? 0} label="Uso" size={70} />
              <div className="min-w-0 text-xs text-muted">
                <div className="truncate text-ink/90">{st?.cpu_name}</div>
                <div>{st?.cores} núcleos · {st?.threads} hilos</div>
                <div className="font-mono">{s?.cpu?.freq_mhz} MHz</div>
              </div>
            </div>
            <div className="px-3 pb-3"><Spark data={hist.current.cpu} /></div>
          </Panel>
          <Panel title="Memoria" icon={<MemoryStick size={14} />}>
            <div className="flex items-center gap-4 px-4 pb-2">
              <Ring value={s?.ram?.percent ?? 0} label="RAM" size={70} />
              <div className="text-xs text-muted">
                <div className="font-mono text-ink/90">{s?.ram?.used_gb} / {s?.ram?.total_gb} GB</div>
                <div>Swap {s?.swap?.percent}%</div>
              </div>
            </div>
            <div className="px-3 pb-3"><Spark data={hist.current.ram} /></div>
          </Panel>
          <Panel title="GPU" icon={<MonitorCog size={14} />}>
            {gpu ? (
              <>
                <div className="flex items-center gap-4 px-4 pb-2">
                  <Ring value={gpu.util} label="Uso" size={70} />
                  <div className="min-w-0 text-xs text-muted">
                    <div className="truncate text-ink/90">{gpu.name}</div>
                    <div className="font-mono">VRAM {gpu.mem_used_gb}/{gpu.mem_total_gb} GB</div>
                    <div className="font-mono">{gpu.power_w ?? "—"} W</div>
                  </div>
                </div>
                <div className="px-3 pb-3"><Spark data={hist.current.gpu} /></div>
              </>
            ) : <p className="px-4 pb-4 text-xs text-faint">No se detecta GPU NVIDIA.</p>}
          </Panel>
          <Panel title="Temperaturas" icon={<Thermometer size={14} />}>
            <div className="space-y-3 px-4 pb-4 text-sm">
              <div className="flex justify-between"><span className="text-muted">GPU</span><span className="font-mono">{gpu?.temp_c != null ? `${gpu.temp_c} °C` : "—"}</span></div>
              <div className="flex justify-between"><span className="text-muted">CPU</span><span className="font-mono">{s?.cpu?.temp_c != null ? `${s.cpu.temp_c} °C` : "No disponible"}</span></div>
              {s?.cpu?.temp_c == null && <p className="text-[11px] leading-snug text-faint">Tu placa no expone la temperatura de la CPU sin privilegios de administrador; JARVIS no los solicita por seguridad.</p>}
              <div className="flex justify-between border-t border-line pt-3"><span className="text-muted">Encendido</span><span className="font-mono text-xs">{s ? fmtUptime(s.uptime_s) : "—"}</span></div>
            </div>
          </Panel>
        </div>

        <div className="mt-4 grid gap-4 lg:grid-cols-3">
          <Panel title="Servicios de JARVIS" icon={<Bot size={14} />}>
            <ul className="space-y-3 px-4 pb-4">
              {services.map((sv) => (
                <li key={sv.name} className="flex items-start gap-3">
                  <span className="mt-1.5"><StatusDot tone={sv.ok ? "ok" : "warn"} /></span>
                  <div className="min-w-0">
                    <div className="text-[13px] text-ink">{sv.name}</div>
                    <div className="truncate text-xs text-muted">{sv.text}</div>
                  </div>
                </li>
              ))}
            </ul>
          </Panel>
          <Panel title="Almacenamiento" icon={<HardDrive size={14} />}>
            <ul className="space-y-3.5 px-4 pb-4">
              {s?.disks?.map((d: any) => (
                <li key={d.mount}>
                  <div className="mb-1.5 flex justify-between text-xs">
                    <span className="font-mono text-ink">{d.mount}</span>
                    <span className="font-mono text-muted">{d.used_gb} / {d.total_gb} GB</span>
                  </div>
                  <Bar value={d.percent} />
                </li>
              ))}
            </ul>
            {s?.net && (
              <div className="flex items-center gap-2 border-t border-line px-4 py-3 font-mono text-[11px] text-muted">
                <Network size={13} /> ↓ {s.net.down_kbps} KB/s · ↑ {s.net.up_kbps} KB/s
              </div>
            )}
          </Panel>
          <Panel title="Aplicaciones activas" icon={<AppWindow size={14} />}>
            <ul className="max-h-72 space-y-2 overflow-y-auto px-4 pb-4">
              {detail?.windows?.map((w: any) => (
                <li key={w.process} className="text-xs">
                  <div className="flex items-center gap-2"><span className="text-ink">{w.process}</span><Badge>PID {w.pid}</Badge></div>
                  <div className="truncate text-faint">{w.windows.join(" · ")}</div>
                </li>
              ))}
            </ul>
          </Panel>
        </div>

        <Panel title="Procesos con más memoria" icon={<Cpu size={14} />} className="mt-4">
          <div className="overflow-x-auto px-2 pb-3">
            <table className="w-full text-left text-xs">
              <thead className="text-faint"><tr><th className="px-2 py-1.5 font-medium">Proceso</th><th className="px-2 font-medium">PID</th><th className="px-2 text-right font-medium">Memoria</th></tr></thead>
              <tbody>
                {detail?.processes?.map((p: any) => (
                  <tr key={p.pid} className="border-t border-line">
                    <td className="px-2 py-1.5 text-ink/90">{p.name}</td>
                    <td className="px-2 font-mono text-faint">{p.pid}</td>
                    <td className="px-2 text-right font-mono text-muted">{p.mem_mb} MB</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      </div>
    </div>
  );
}
