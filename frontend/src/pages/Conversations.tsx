import { Archive, MessageSquare, Pencil, Search, Send, Trash2, Workflow } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { del, get, patch } from "../lib/api";
import { useJarvis } from "../lib/store";
import { Badge, Empty, Input, PageHeader, Panel, cx, timeAgo } from "../components/ui";

export function Conversations() {
  const [list, setList] = useState<any[]>([]);
  const [q, setQ] = useState("");
  const [archived, setArchived] = useState(false);
  const v = useJarvis((s) => s.versions.conversations ?? 0);
  const current = useJarvis((s) => s.conversationId);
  const load = useJarvis((s) => s.loadConversation);
  const setPage = useJarvis((s) => s.setPage);

  const refresh = () => get(`/api/conversations?archived=${archived}`).then(setList).catch(() => undefined);
  useEffect(() => {
    void refresh();
  }, [v, archived]);

  const filtered = useMemo(() => list.filter((c) => c.title.toLowerCase().includes(q.toLowerCase())), [list, q]);
  const icon = (s: string) => (s === "telegram" ? <Send size={15} /> : s === "job" ? <Workflow size={15} /> : <MessageSquare size={15} />);

  return (
    <div className="h-full overflow-y-auto p-4 sm:p-6">
      <div className="mx-auto max-w-4xl">
        <PageHeader title="Conversaciones" subtitle="Historial compartido entre el PC, la voz, Telegram y los trabajos en segundo plano." />
        <div className="mb-4 flex flex-wrap gap-2">
          <div className="relative min-w-[220px] flex-1">
            <Search size={15} className="absolute top-1/2 left-3 -translate-y-1/2 text-faint" />
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Buscar conversaciones…" className="pl-9" />
          </div>
          <button onClick={() => setArchived(!archived)}
            className={cx("flex items-center gap-2 rounded-xl border px-3 text-sm", archived ? "border-electric/40 text-lavender" : "border-line-strong text-muted")}>
            <Archive size={15} /> {archived ? "Incluye archivadas" : "Activas"}
          </button>
        </div>
        <Panel>
          {filtered.length === 0 ? (
            <Empty icon={<MessageSquare size={20} />} title="Sin conversaciones" text="Empieza a hablar con JARVIS desde Inicio o Telegram." />
          ) : (
            <ul className="divide-y divide-line">
              {filtered.map((c) => (
                <li key={c.id} className={cx("group flex items-center gap-3 px-4 py-3 transition-colors hover:bg-white/[0.02]", c.id === current && "bg-electric/[0.06]")}>
                  <span className="grid size-8 shrink-0 place-items-center rounded-lg border border-line bg-white/[0.02] text-lavender/80">{icon(c.source)}</span>
                  <button className="min-w-0 flex-1 text-left" onClick={async () => { await load(c.id); setPage("home"); }}>
                    <div className="truncate text-[14px] text-ink">{c.title}</div>
                    <div className="mt-0.5 flex items-center gap-2 text-[11px] text-faint">
                      {timeAgo(c.updated_at)}
                      {c.source !== "ui" && <Badge>{c.source === "telegram" ? "Telegram" : c.source === "job" ? "Trabajo" : c.source}</Badge>}
                      {c.archived && <Badge>archivada</Badge>}
                    </div>
                  </button>
                  <div className="flex gap-1 opacity-100 sm:opacity-0 sm:group-hover:opacity-100">
                    <button title="Renombrar" className="rounded-lg p-2 text-faint hover:bg-white/[0.05] hover:text-ink"
                      onClick={async () => {
                        const t = prompt("Nuevo título", c.title);
                        if (t) { await patch(`/api/conversations/${c.id}`, { title: t }); void refresh(); }
                      }}><Pencil size={14} /></button>
                    <button title={c.archived ? "Desarchivar" : "Archivar"} className="rounded-lg p-2 text-faint hover:bg-white/[0.05] hover:text-ink"
                      onClick={async () => { await patch(`/api/conversations/${c.id}`, { archived: !c.archived }); void refresh(); }}><Archive size={14} /></button>
                    <button title="Eliminar" className="rounded-lg p-2 text-faint hover:bg-danger/10 hover:text-danger"
                      onClick={async () => {
                        if (confirm(`¿Eliminar definitivamente «${c.title}»? No se puede deshacer.`)) {
                          await del(`/api/conversations/${c.id}`);
                          if (c.id === current) await load(null);
                          void refresh();
                        }
                      }}><Trash2 size={14} /></button>
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
