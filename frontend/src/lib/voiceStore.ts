import { create } from "zustand";
import { useJarvis } from "./store";
import { post } from "./api";
import { chime, findMic, micErrorMessage, Recorder, SentenceStreamer, speaker, transcribe } from "./voice";

// Controlador de voz global (funciona en todas las pantallas).
// «Hey JARVIS» lo gestiona el servicio de JARVIS (escucha 24/7 aunque la ventana no esté delante).

const recorder = new Recorder();
export const streamer = new SentenceStreamer();
export type AssistantState = "off" | "standby" | "listening" | "transcribing" | "thinking" | "speaking" | "error";

function pref(key: string, def: boolean) {
  try {
    const v = localStorage.getItem(key);
    return v === null ? def : v === "1";
  } catch {
    return def;
  }
}
function savePref(key: string, v: boolean) {
  try {
    localStorage.setItem(key, v ? "1" : "0");
  } catch {
    /* noop */
  }
}

interface VoiceState {
  micEnabled: boolean;
  wakeEnabled: boolean;
  wakeStatus: "off" | "starting" | "on" | "error";
  assistant: AssistantState;
  assistantDevice: string;
  setAssistant: (state: AssistantState, device?: string) => void;
  readAloud: boolean;
  listening: boolean;
  transcribing: boolean;
  speaking: boolean;
  lastTranscript: string;
  error: string;
  listen: () => Promise<void>;
  stopListening: () => void;
  stopSpeaking: () => void;
  setMic: (v: boolean) => void;
  setWake: (v: boolean) => Promise<void>;
  setReadAloud: (v: boolean) => void;
}

export const useVoice = create<VoiceState>((set, get) => ({
  micEnabled: pref("jarvis.mic", true),
  wakeEnabled: false,
  wakeStatus: "off",
  assistant: "off",
  assistantDevice: "",
  setAssistant: (assistant, device) => {
    set({ assistant, wakeEnabled: assistant !== "off", wakeStatus: assistant === "off" ? "off" : assistant === "error" ? "error" : "on",
          ...(device ? { assistantDevice: device } : {}) });
    const j = useJarvis.getState();
    const map: Record<string, any> = { listening: "listening", transcribing: "transcribing", thinking: "thinking", speaking: "speaking" };
    if (map[assistant]) j.setAgentState(map[assistant]);
    else if (["listening", "transcribing", "speaking"].includes(j.agentState) && !get().listening && !get().speaking)
      j.setAgentState(j.busy ? "thinking" : "idle");
  },
  readAloud: pref("jarvis.readAloud2", true),
  listening: false,
  transcribing: false,
  speaking: false,
  lastTranscript: "",
  error: "",

  listen: async () => {
    const j = useJarvis.getState();
    if (!get().micEnabled) {
      j.toast({ title: "Micrófono desactivado", message: "Actívalo para hablar con JARVIS.", tone: "warn" });
      return;
    }
    if (get().listening) {
      recorder.finish("manual");
      return;
    }
    speaker.stop();
    streamer.reset();
    set({ listening: true, error: "" });
    j.setAgentState("listening");
    chime("start");
    try {
      const r = await recorder.start();
      set({ listening: false });
      if (!r.blob) {
        j.setAgentState("idle");
        if (r.reason === "no-speech") {
          const mic = await findMic().catch(() => undefined);
          set({ error: "No he oído nada." });
          j.toast({ title: "No he oído nada", tone: "warn",
            message: `Micrófono en uso: ${mic?.label ?? "el predeterminado de Windows"}. Si no es el correcto, cámbialo en Configuración → Voz.` });
        }
        return;
      }
      chime("stop");
      set({ transcribing: true });
      j.setAgentState("transcribing");
      const t = await transcribe(r.blob);
      set({ transcribing: false, lastTranscript: t.text });
      if (!t.text.trim()) {
        j.setAgentState("idle");
        set({ error: "No he entendido nada." });
        return;
      }
      await j.send(t.text, { voice: true });
    } catch (e: any) {
      const msg = e?.name ? micErrorMessage(e) : e?.message || "Error de voz";
      set({ listening: false, transcribing: false, error: msg });
      j.setAgentState("idle");
      j.toast({ title: "Micrófono", message: msg, tone: "danger" });
    }
  },

  stopListening: () => recorder.finish("cancel"),

  stopSpeaking: () => {
    speaker.stop();
    streamer.reset();
    if (get().assistant === "speaking" || get().assistant === "thinking") void post("/api/voice/assistant/interrupt");
  },

  setMic: (v) => {
    savePref("jarvis.mic", v);
    set({ micEnabled: v });
    if (!v) {
      recorder.finish("cancel");
      if (get().wakeEnabled) void get().setWake(false); // privacidad: micrófono apagado = nada escucha
    }
  },

  setWake: async (v) => {
    if (v && !get().micEnabled) return;
    set({ wakeStatus: "starting" });
    try {
      const r = await post("/api/voice/assistant", { enabled: v });
      get().setAssistant(r.enabled ? (r.state === "off" ? "standby" : r.state) : "off", r.device);
      if (v) chime("wake");
    } catch (e: any) {
      set({ wakeStatus: "error" });
      useJarvis.getState().toast({ title: "Escucha permanente", message: e.message, tone: "danger" });
    }
  },

  setReadAloud: (v) => {
    savePref("jarvis.readAloud2", v);
    set({ readAloud: v });
    if (!v) speaker.stop();
  },
}));

speaker.onChange((speaking) => {
  useVoice.setState({ speaking });
  const j = useJarvis.getState();
  if (speaking) j.setAgentState("speaking");
  else if (j.agentState === "speaking" && useVoice.getState().assistant !== "speaking") j.setAgentState(j.busy ? "thinking" : "idle");
});
