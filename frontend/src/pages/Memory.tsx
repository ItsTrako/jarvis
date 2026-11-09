import { AnimatePresence, motion } from "framer-motion";
import { Brain, Check, Pencil, Plus, Search, Star, Trash2, X } from "lucide-react";
import { useEffect, useState } from "react";
import { del, get, patch, post } from "../lib/api";
import { useJarvis } from "../lib/store";
import { Badge, Button, Empty, Input, PageHeader, Panel, Select, TextArea, cx, timeAgo } from "../components/ui";

const KINDS: Record<string, string> = {
  preference: "Preferencia", personal: "Personal", project: "Proyecto", fact: "Dato", note: "Nota", config: "Configuración",
};

function Stars({ value, onChange }: { value: number; onChange?: (v: number) => void }) {
  return (
    <div className="flex gap-0.5">
      {[1, 2, 3, 4, 5].map((n) => (
        <button key={n} disabled={!onChange} onClick={() => onChange?.(n)} aria-label={`Importancia ${n}`}>
          <Star size={12} className={n <= value ? "fill-lavender text-lavender" : "text-faint"} />
        </button>
      ))}
    </div>
  );
}

export function Memory() {
  const [rows, setRows] = useState<any[]>([]);
  const [q, setQ] = useState("");
  const [kind, setKind] = useState("all");
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState({ content: "", kind: "fact", importance: 3, tags: "" });
  const [adding, setAdding] = useState(false);
  const v = useJarvis((s) => s.versions.memory ?? 0);

  const refresh = () => get(`/api/memories${q ? `?q=${encodeURIComponent(q)}` : ""}`).then(setRows).catch(() => undefined);
  useEffect(() => {
    const t = window.setTimeout(refresh, 200);
    return () => window.clearTimeout(t);
  }, [q, v]);

  const shown = rows.filter((r) => kind === "all" || r.kind === kind);

  const save = async () => {
    if (!draft.content.trim()) return;
    if (editing) await patch(`/api/memories/${editing}`, draft);
    else await post("/api/memories", draft);
    setEditing(null);
    setAdding(false);
    setDraft({ content: "", kind: "fact", importance: 3, tags: "" });
    void refresh();
  };

  return (
    <div className="h-full overflow-y-auto p-4 sm:p-6">
      <div className="mx-auto max-w-4xl">
        <PageHeader
          title="Memoria"
          subtitle="Lo que JARVIS recuerda de ti de forma persistente. Puedes consultarlo, corregirlo o borrarlo."
          actions={<Button variant="primary" onClick={() => { setAdding(true); setEditing(null); }}><Plus size={16} /> Añadir recuerdo</Button>}
        />
        <div className="mb-4 flex flex-wrap gap-2">
          <div className="relative min-w-[220px] flex-1">
            <Search size={15} className="absolute top-1/2 left-3 -translate-y-1/2 text-faint" />
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Buscar en la memoria…" className="pl-9" />
          </div>
          <div className="flex flex-wrap gap-1">
            {["all", ...Object.keys(KINDS)].map((k) => (
              <button key={k} onClick={() => setKind(k)}
                className={cx("rounded-lg px-2.5 py-1.5 text-xs transition-colors", kind === k ? "bg-electric/20 text-lavender" : "text-muted hover:text-ink")}>
                {k === "all" ? "Todo" : KINDS[k]}
              </button>
            ))}
          </div>
        </div>

        <AnimatePresence>
          {(adding || editing) && (
            <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }} className="mb-4">
              <Panel className="p-4">
                <TextArea rows={3} value={draft.content} autoFocus placeholder="Ej.: Prefiero los informes en PDF y con conclusiones al principio."
                  onChange={(e) => setDraft({ ...draft, content: e.target.value })} />
                <div className="mt-3 flex flex-wrap items-center gap-3">
                  <div className="w-40"><Select value={draft.kind} onChange={(k) => setDraft({ ...draft, kind: k })}
                    options={Object.entries(KINDS).map(([value, label]) => ({ value, label }))} /></div>
                  <Input className="!w-48" value={draft.tags} placeholder="etiquetas" onChange={(e) => setDraft({ ...draft, tags: e.target.value })} />
                  <Stars value={draft.importance} onChange={(i) => setDraft({ ...draft, importance: i })} />
                  <div className="ml-auto flex gap-2">
                    <Button variant="subtle" onClick={() => { setAdding(false); setEditing(null); }}><X size={15} /> Cancelar</Button>
                    <Button variant="primary" onClick={save}><Check size={15} /> Guardar</Button>
                  </div>
                </div>
              </Panel>
            </motion.div>
          )}
        </AnimatePresence>

        <Panel>
          {shown.length === 0 ? (
            <Empty icon={<Brain size={20} />} title="Memoria vacía" text="Dile a JARVIS «recuerda que…» o añade recuerdos manualmente." />
          ) : (
            <ul className="divide-y divide-line">
              {shown.map((m) => (
                <motion.li layout key={m.id} className="group flex items-start gap-3 px-4 py-3.5">
                  <div className="min-w-0 flex-1">
                    <p className="text-[14px] leading-relaxed text-ink/95">{m.content}</p>
                    <div className="mt-1.5 flex flex-wrap items-center gap-2 text-[11px] text-faint">
                      <Badge tone="purple">{KINDS[m.kind] ?? m.kind}</Badge>
                      <Stars value={m.importance} />
                      {m.tags && <span>#{m.tags.split(",").map((t: string) => t.trim()).filter(Boolean).join(" #")}</span>}
                      <span>· {timeAgo(m.updated_at)}</span>
                      <span>· origen: {m.source}</span>
                    </div>
                  </div>
                  <div className="flex gap-1 sm:opacity-0 sm:group-hover:opacity-100">
                    <button className="rounded-lg p-2 text-faint hover:bg-white/[0.05] hover:text-ink" title="Editar"
                      onClick={() => { setEditing(m.id); setAdding(false); setDraft({ content: m.content, kind: m.kind, importance: m.importance, tags: m.tags }); }}>
                      <Pencil size={14} />
                    </button>
                    <button className="rounded-lg p-2 text-faint hover:bg-danger/10 hover:text-danger" title="Olvidar"
                      onClick={async () => { if (confirm("¿Olvidar este recuerdo?")) { await del(`/api/memories/${m.id}`); void refresh(); } }}>
                      <Trash2 size={14} />
                    </button>
                  </div>
                </motion.li>
              ))}
            </ul>
          )}
        </Panel>
      </div>
    </div>
  );
}
