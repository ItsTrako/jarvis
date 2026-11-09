import { Search, ShieldCheck, Wrench } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { get } from "../lib/api";
import { Badge, Input, PageHeader, Panel, riskTone } from "../components/ui";

const RISK_HELP: Record<string, string> = {
  seguro: "Solo lectura, se ejecuta sin preguntar",
  moderado: "Efectos reversibles, queda registrado",
  sensible: "Pide confirmación (privacidad o cambios relevantes)",
  peligroso: "Siempre pide confirmación explícita (y PIN en Telegram)",
};

export function Tools() {
  const [tools, setTools] = useState<any[]>([]);
  const [q, setQ] = useState("");
  useEffect(() => {
    get("/api/tools").then(setTools).catch(() => undefined);
  }, []);
  const groups = useMemo(() => {
    const f = tools.filter((t) => (t.name + t.description + t.category).toLowerCase().includes(q.toLowerCase()));
    const g: Record<string, any[]> = {};
    f.forEach((t) => (g[t.category] ??= []).push(t));
    return Object.entries(g).sort();
  }, [tools, q]);

  return (
    <div className="h-full overflow-y-auto p-4 sm:p-6">
      <div className="mx-auto max-w-6xl">
        <PageHeader title="Herramientas" subtitle={`${tools.length} capacidades disponibles. Cada una tiene parámetros definidos, nivel de riesgo y registro de uso. Además: búsqueda y lectura web en tiempo real.`} />
        <Panel className="mb-5 p-4">
          <div className="flex items-center gap-2 text-sm font-medium text-ink"><ShieldCheck size={16} className="text-lavender" /> Niveles de permiso</div>
          <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
            {Object.entries(RISK_HELP).map(([r, h]) => (
              <div key={r} className="flex items-start gap-2 text-xs text-muted"><Badge tone={riskTone(r)}>{r}</Badge><span>{h}</span></div>
            ))}
          </div>
        </Panel>
        <div className="relative mb-5">
          <Search size={15} className="absolute top-1/2 left-3 -translate-y-1/2 text-faint" />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Buscar herramienta…" className="pl-9" />
        </div>
        <div className="space-y-6">
          {groups.map(([cat, list]) => (
            <section key={cat}>
              <h2 className="mb-2.5 font-display text-xs tracking-[0.2em] text-lavender/80 uppercase">{cat}</h2>
              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                {list.map((t) => (
                  <Panel key={t.name} className="p-4">
                    <div className="flex items-center gap-2">
                      <Wrench size={14} className="text-lavender" />
                      <span className="font-mono text-[13px] text-ink">{t.name}</span>
                      <span className="ml-auto"><Badge tone={riskTone(t.risk)}>{t.risk}</Badge></span>
                    </div>
                    <p className="mt-2 line-clamp-4 text-xs leading-relaxed text-muted">{t.description}</p>
                    {Object.keys(t.parameters).length > 0 && (
                      <div className="mt-3 flex flex-wrap gap-1">
                        {Object.keys(t.parameters).map((p) => (
                          <span key={p} className="rounded-md bg-white/[0.04] px-1.5 py-0.5 font-mono text-[10px] text-faint">
                            {p}{t.required.includes(p) ? "*" : ""}
                          </span>
                        ))}
                      </div>
                    )}
                    {!t.enabled && <div className="mt-2 text-[11px] text-warn">Desactivada en la configuración</div>}
                  </Panel>
                ))}
              </div>
            </section>
          ))}
        </div>
      </div>
    </div>
  );
}
