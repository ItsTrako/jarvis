import { AnimatePresence, motion } from "framer-motion";
import { Ear, EarOff, Mic, MicOff, Plus, Settings2, Square, VolumeX } from "lucide-react";
import { ChatList, Composer } from "../components/Chat";
import { OrbGL as Orb } from "../components/OrbGL";
import { ActivityPanel, SystemMini, TasksMini } from "../components/Panels";
import { Waveform } from "../components/Waveform";
import { cx } from "../components/ui";
import { useJarvis, type AgentState } from "../lib/store";
import { useVoice } from "../lib/voiceStore";

const STATE_TEXT: Record<AgentState, string> = {
  idle: "En espera",
  listening: "Escuchando",
  transcribing: "Procesando voz",
  thinking: "Pensando",
  speaking: "Respondiendo",
  offline: "Sin conexión",
};

function greeting(name?: string) {
  const h = new Date().getHours();
  const g = h < 6 ? "Buenas noches" : h < 14 ? "Buenos días" : h < 21 ? "Buenas tardes" : "Buenas noches";
  return name ? `${g}, ${name}.` : `${g}.`;
}

const SUGGESTIONS = [
  "¿Qué recursos está usando mi ordenador ahora mismo?",
  "Investiga tres alternativas a Notion, compáralas y prepara un documento con las conclusiones",
  "Organiza mi carpeta de Descargas por tipo de archivo",
  "¿Qué tareas tengo pendientes?",
];

function StatusLine({ state }: { state: AgentState }) {
  const conn = useJarvis((s) => s.conn);
  const status = useJarvis((s) => s.status);
  const counts = status?.counts;
  const s = conn !== "online" ? "offline" : state;
  return (
    <div className="flex flex-col items-center gap-1.5">
      <div className="flex items-center gap-2">
        <span className={cx("size-1.5 rounded-full", s === "offline" ? "bg-danger" : s === "idle" ? "bg-ok" : "animate-pulse bg-electric shadow-[0_0_10px_#a855f7]")} />
        <span className="font-display text-xs tracking-[0.28em] text-lavender uppercase">{STATE_TEXT[s]}</span>
      </div>
      {counts && (
        <p className="text-center text-xs text-faint">
          {status?.model?.ok || status?.model?.status === "ollama_detenido"
            ? `Todos los sistemas operativos · ${status.model.local ? `${status.model.display_name ?? "IA local"}` : "Claude"}`
            : "Cerebro sin configurar"} · {counts.open_tasks} tareas pendientes · {counts.active_jobs} en segundo plano
        </p>
      )}
    </div>
  );
}

const ASSISTANT_TEXT: Record<string, string> = {
  standby: "Di «Hey JARVIS»", listening: "Te escucho…", transcribing: "Entendiendo…", thinking: "Pensando…",
  speaking: "Hablando · di «Hey JARVIS» para interrumpir", error: "Error de micrófono",
};

function VoiceBar() {
  const v = useVoice();
  const state = useJarvis((s) => s.agentState);
  const active = state === "listening" || state === "speaking";
  const on = v.assistant !== "off";
  return (
    <div className="flex items-center gap-2">
      <button
        onClick={() => v.setMic(!v.micEnabled)}
        className={cx("grid size-9 place-items-center rounded-xl border transition-colors", v.micEnabled ? "border-line-strong text-muted hover:text-ink" : "border-danger/30 bg-danger/10 text-danger")}
        title={v.micEnabled ? "Desactivar micrófono" : "Activar micrófono"} aria-label="Micrófono"
      >
        {v.micEnabled ? <Mic size={16} /> : <MicOff size={16} />}
      </button>
      <div className="w-40 sm:w-56"><Waveform active={active} /></div>
      <button
        onClick={() => v.setWake(!on)}
        disabled={!v.micEnabled}
        className={cx("relative flex h-9 items-center gap-1.5 overflow-hidden rounded-xl border px-2.5 text-[11.5px] transition-colors disabled:opacity-40",
          on ? "border-electric/40 bg-electric/15 text-lavender" : "border-line-strong text-muted hover:text-ink")}
        title={on ? `Escucha permanente activa${v.assistantDevice ? ` · ${v.assistantDevice}` : ""}. Pulsa para desactivarla.`
                  : "Activar escucha permanente de «Hey JARVIS» (24/7, aunque la ventana esté cerrada; procesado local)"}
      >
        {on && v.assistant === "standby" && <span className="absolute inset-0 animate-pulse bg-electric/10" />}
        {on ? <Ear size={15} className="relative" /> : <EarOff size={15} />}
        <span className="relative hidden sm:inline">
          {v.wakeStatus === "starting" ? "Activando…" : on ? ASSISTANT_TEXT[v.assistant] ?? "Hey JARVIS" : "Hey JARVIS"}
        </span>
      </button>
      {(v.speaking || v.assistant === "speaking") && (
        <button onClick={v.stopSpeaking} className="grid size-9 place-items-center rounded-xl border border-line-strong text-lavender hover:text-ink" title="Detener la voz" aria-label="Detener voz">
          <VolumeX size={16} />
        </button>
      )}
    </div>
  );
}

export function Home() {
  const items = useJarvis((s) => s.items);
  const busy = useJarvis((s) => s.busy);
  const agentState = useJarvis((s) => s.agentState);
  const status = useJarvis((s) => s.status);
  const send = useJarvis((s) => s.send);
  const newConversation = useJarvis((s) => s.newConversation);
  const title = useJarvis((s) => s.conversationTitle);
  const setPage = useJarvis((s) => s.setPage);
  const v = useVoice();
  const empty = items.length === 0 && !busy;
  const needsKey = status && !status.model?.ok && status.model?.status !== "ollama_detenido";

  return (
    <div className="flex h-full">
      <div className="flex min-w-0 flex-1 flex-col">
        <AnimatePresence mode="popLayout" initial={false}>
          {empty ? (
            <motion.div
              key="hero"
              className="flex min-h-0 flex-1 flex-col items-center justify-center-safe overflow-y-auto px-4 py-4"
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0, scale: 0.98 }}
            >
              <div className="relative">
                <button onClick={() => void v.listen()} aria-label="Hablar con JARVIS" className="block w-[min(300px,40vh,80vw)] rounded-full">
                  <Orb state={agentState} size={300} />
                </button>
              </div>
              <h1 className="mt-1 text-center font-display text-3xl font-semibold tracking-tight sm:text-4xl">
                <span className="text-gradient">{greeting(status?.user?.name)}</span>
              </h1>
              <div className="mt-3"><StatusLine state={agentState} /></div>
              <div className="mt-5"><VoiceBar /></div>
              {needsKey ? (
                <button onClick={() => setPage("settings")}
                  className="mt-6 flex items-center gap-2 rounded-xl border border-warn/30 bg-warn/[0.07] px-4 py-2.5 text-sm text-warn hover:bg-warn/15">
                  <Settings2 size={16} /> Activa el cerebro de JARVIS: modelo local gratuito o Claude
                </button>
              ) : (
                <div className="mt-7 grid w-full max-w-2xl grid-cols-1 gap-2 sm:grid-cols-2">
                  {SUGGESTIONS.map((s) => (
                    <button key={s} onClick={() => void send(s)}
                      className="glass-soft rounded-xl px-3.5 py-2.5 text-left text-[12.5px] leading-snug text-muted transition-colors hover:border-lavender/25 hover:text-ink">
                      {s}
                    </button>
                  ))}
                </div>
              )}
            </motion.div>
          ) : (
            <motion.div key="chat" className="flex min-h-0 flex-1 flex-col" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
              <div className="flex shrink-0 items-center gap-3 border-b border-line px-4 py-2 sm:px-6">
                <button onClick={() => void v.listen()} aria-label="Hablar" className="-my-3 -ml-3 shrink-0">
                  <Orb state={agentState} size={92} />
                </button>
                <div className="min-w-0 flex-1">
                  <div className="truncate font-display text-[15px] font-medium text-ink">{title || "Conversación"}</div>
                  <div className="flex items-center gap-2 text-[11px] tracking-[0.2em] text-lavender/80 uppercase">
                    {STATE_TEXT[agentState]}
                    {busy && <span className="shimmer-text normal-case tracking-normal">· trabajando</span>}
                  </div>
                </div>
                <div className="hidden md:block"><VoiceBar /></div>
                {busy && (
                  <button onClick={() => void useJarvis.getState().stop()} className="hidden items-center gap-1.5 rounded-xl border border-line-strong px-3 py-1.5 text-xs text-muted hover:text-ink sm:flex">
                    <Square size={11} fill="currentColor" /> Detener
                  </button>
                )}
                <button onClick={newConversation} title="Nueva conversación" aria-label="Nueva conversación"
                  className="grid size-9 place-items-center rounded-xl border border-line-strong text-muted hover:text-ink">
                  <Plus size={16} />
                </button>
              </div>
              <div className="min-h-0 flex-1"><ChatList /></div>
            </motion.div>
          )}
        </AnimatePresence>
        <div className="mx-auto w-full max-w-3xl shrink-0 px-3 pb-3 sm:px-6 sm:pb-5">
          <Composer autoFocus />
        </div>
      </div>
      <aside className="hidden w-[340px] shrink-0 flex-col gap-4 overflow-y-auto border-l border-line p-4 xl:flex">
        <ActivityPanel />
        <SystemMini />
        <TasksMini />
      </aside>
    </div>
  );
}
