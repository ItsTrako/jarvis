import { motion } from "framer-motion";
import { useEffect } from "react";
import { Approvals, Toasts } from "./components/Overlays";
import { Shell } from "./components/Shell";
import { events, get } from "./lib/api";
import { useJarvis } from "./lib/store";
import { setPreferredMic, setRemoteLevel, speaker } from "./lib/voice";
import { streamer, useVoice } from "./lib/voiceStore";
import { Automations } from "./pages/Automations";
import { Conversations } from "./pages/Conversations";
import { HistoryPage } from "./pages/History";
import { Home } from "./pages/Home";
import { Memory } from "./pages/Memory";
import { Settings } from "./pages/Settings";
import { SystemPage } from "./pages/System";
import { Tools } from "./pages/Tools";

// Las respuestas a «Hey JARVIS» las habla el servicio por los altavoces: la ventana no las repite.
let remoteRun = false;

function shouldSpeak() {
  const j = useJarvis.getState();
  const v = useVoice.getState();
  if (remoteRun) return false;
  return v.readAloud || (j.voiceTurn && (j.status?.voice?.auto_speak ?? true));
}

export default function App() {
  const page = useJarvis((s) => s.page);

  useEffect(() => {
    const st = useJarvis.getState();
    void st.refreshStatus(true);
    void st.loadConversation(st.conversationId);
    get("/api/jobs").then((jobs) => useJarvis.setState({ jobs })).catch(() => undefined);

    // Micrófono preferido (guardado en la configuración del servidor)
    const unsubMic = useJarvis.subscribe((s, prev) => {
      if (s.status?.voice?.mic_label !== prev.status?.voice?.mic_label) setPreferredMic(s.status?.voice?.mic_label ?? "");
      const a = s.status?.voice?.assistant;
      if (a && a !== prev.status?.voice?.assistant) useVoice.getState().setAssistant(a.enabled ? (a.state === "off" ? "standby" : a.state) : "off", a.device);
    });
    const offStatus = events.onStatus((conn) => {
      useJarvis.setState({ conn });
      if (conn === "online") void useJarvis.getState().refreshStatus();
      if (conn === "offline") useJarvis.getState().setAgentState("offline");
      else if (useJarvis.getState().agentState === "offline") useJarvis.getState().setAgentState("idle");
    });
    const off = events.on((ev) => {
      const s = useJarvis.getState();
      // Servicio de voz permanente
      if (ev.type === "voice_level") setRemoteLevel(ev.level);
      if (ev.type === "voice_state") {
        useVoice.getState().setAssistant(ev.state, ev.device);
        // Al hablarle con «Hey JARVIS», la pantalla de Inicio muestra esa conversación
        if (ev.conversation_id && ev.state === "listening" && s.page === "home" && s.conversationId !== ev.conversation_id)
          void s.loadConversation(ev.conversation_id);
      }
      if (ev.type === "voice_transcript" && ev.conversation_id === s.conversationId)
        useJarvis.setState({ items: [...s.items, { kind: "user", text: ev.text, source: "voice", ts: Date.now() / 1000 }] });
      const mine = ev.conversation_id && ev.conversation_id === s.conversationId;
      if (mine && ev.type === "run_start") remoteRun = ev.source === "wake";
      // Voz en streaming: se habla frase a frase mientras llega la respuesta
      if (mine && ev.type === "run_start") streamer.reset();
      if (mine && ev.type === "assistant_delta" && shouldSpeak()) streamer.feed(ev.text);
      if (mine && ev.type === "run_end") {
        if (shouldSpeak() && !ev.stopped) streamer.flush();
        else streamer.reset();
      }
      s.handleEvent(ev);
      if (["approval_request", "job_update", "tasks_changed", "memory_changed", "emergency"].includes(ev.type)) {
        window.clearTimeout((App as any)._t);
        (App as any)._t = window.setTimeout(() => void useJarvis.getState().refreshStatus(), 800);
      }
    });
    void events.connect();
    const poll = window.setInterval(() => void useJarvis.getState().refreshStatus(), 30000);

    const onKey = (e: KeyboardEvent) => {
      if (e.ctrlKey && e.shiftKey && e.code === "Space") {
        e.preventDefault();
        void useVoice.getState().listen();
      }
      if (e.key === "Escape" && speaker.speaking) useVoice.getState().stopSpeaking();
    };
    window.addEventListener("keydown", onKey);
    return () => {
      off();
      offStatus();
      unsubMic();
      events.close();
      window.clearInterval(poll);
      window.removeEventListener("keydown", onKey);
    };
  }, []);

  const pages = {
    home: <Home />, conversations: <Conversations />, memory: <Memory />, automations: <Automations />,
    tools: <Tools />, system: <SystemPage />, history: <HistoryPage />, settings: <Settings />,
  };

  return (
    <Shell>
      {/* Sin fase de salida: la página nueva entra al instante con un fundido. Con mode="wait" una
          animación de salida que no termina (p. ej. dentro de Ajustes > Voz) dejaba la app en blanco. */}
      <motion.div
        key={page}
        className="h-full"
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
      >
        {pages[page]}
      </motion.div>
      <Approvals />
      <Toasts />
    </Shell>
  );
}
