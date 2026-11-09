import { create } from "zustand";
import { get, post } from "./api";

export type AgentState = "idle" | "listening" | "transcribing" | "thinking" | "speaking" | "offline";
export type Page = "home" | "conversations" | "memory" | "automations" | "tools" | "system" | "history" | "settings";

export interface ChatItem {
  kind: "user" | "assistant" | "tool" | "progress" | "note";
  id?: string | number;
  text?: string;
  name?: string;
  input?: any;
  result?: string | null;
  is_error?: boolean;
  recovered?: boolean;
  running?: boolean;
  server?: boolean;
  summary?: string;
  risk?: string;
  source?: string;
  ts?: number;
  attachments?: string[];
  files?: string[];
}

export interface PlanStep {
  title: string;
  status: "pending" | "in_progress" | "done" | "failed";
}

export interface Approval {
  id: string;
  tool: string;
  risk: string;
  risk_level: number;
  summary: string;
  details: Record<string, unknown>;
  source: string;
  created_at: number;
  expires_at: number;
  requires_pin: boolean;
}

export interface Toast {
  id: number;
  title: string;
  message: string;
  tone?: "info" | "ok" | "warn" | "danger";
  files?: string[];
}

interface State {
  page: Page;
  conn: "connecting" | "online" | "offline";
  status: any | null;
  stats: any | null;
  approvals: Approval[];
  emergency: boolean;
  conversationId: string | null;
  conversationTitle: string;
  items: ChatItem[];
  streaming: string;
  progress: string;
  busy: boolean;
  plan: { goal: string; steps: PlanStep[] } | null;
  jobs: any[];
  agentState: AgentState;
  lastRunFiles: string[];
  toasts: Toast[];
  versions: Record<string, number>;
  voiceTurn: boolean; // el turno actual se inició por voz
  setPage: (p: Page) => void;
  setAgentState: (s: AgentState) => void;
  refreshStatus: (force?: boolean) => Promise<void>;
  loadConversation: (id: string | null) => Promise<void>;
  newConversation: () => void;
  send: (text: string, opts?: { attachments?: string[]; voice?: boolean }) => Promise<void>;
  stop: () => Promise<void>;
  toast: (t: Omit<Toast, "id">) => void;
  dismissToast: (id: number) => void;
  handleEvent: (ev: any) => void;
  setVoiceTurn: (v: boolean) => void;
}

let toastId = 1;

export const useJarvis = create<State>((set, getState) => ({
  page: "home",
  conn: "connecting",
  status: null,
  stats: null,
  approvals: [],
  emergency: false,
  conversationId: localStorage.getItem("jarvis.conversation") || null,
  conversationTitle: "",
  items: [],
  streaming: "",
  progress: "",
  busy: false,
  plan: null,
  jobs: [],
  agentState: "idle",
  lastRunFiles: [],
  toasts: [],
  versions: {},
  voiceTurn: false,

  setPage: (page) => set({ page }),
  setAgentState: (agentState) => set({ agentState }),
  setVoiceTurn: (voiceTurn) => set({ voiceTurn }),

  refreshStatus: async (force = false) => {
    try {
      const status = await get(`/api/status${force ? "?refresh=true" : ""}`);
      set({ status, emergency: status.emergency.engaged, approvals: status.approvals });
    } catch {
      /* el socket informará del estado */
    }
  },

  loadConversation: async (id) => {
    if (!id) {
      set({ conversationId: null, items: [], conversationTitle: "", plan: null, busy: false });
      localStorage.removeItem("jarvis.conversation");
      return;
    }
    try {
      const c = await get(`/api/conversations/${id}`);
      localStorage.setItem("jarvis.conversation", id);
      // El último plan publicado en la conversación se recupera también al recargar
      const lastPlan = [...c.items].reverse().find((i: ChatItem) => i.kind === "tool" && i.name === "update_plan");
      const plan = lastPlan?.input?.steps ? { goal: lastPlan.input.goal ?? "", steps: lastPlan.input.steps } : getState().plan;
      set({ conversationId: id, items: c.items, conversationTitle: c.title, busy: c.busy, plan,
            streaming: c.busy ? getState().streaming : "" });
    } catch {
      localStorage.removeItem("jarvis.conversation");
      set({ conversationId: null, items: [] });
    }
  },

  newConversation: () => {
    localStorage.removeItem("jarvis.conversation");
    set({ conversationId: null, items: [], conversationTitle: "", plan: null, streaming: "", progress: "", lastRunFiles: [] });
  },

  send: async (text, opts = {}) => {
    const s = getState();
    const optimistic: ChatItem = { kind: "user", text, ts: Date.now() / 1000, source: opts.voice ? "voice" : "ui",
                                   attachments: opts.attachments?.map(() => "archivo") };
    set({ items: [...s.items, optimistic], busy: true, streaming: "", progress: "", plan: null, lastRunFiles: [],
          agentState: "thinking", voiceTurn: !!opts.voice });
    try {
      const r = await post("/api/chat", { text, conversation_id: s.conversationId, attachments: opts.attachments ?? [],
                                          interface: opts.voice ? "voz" : "pc" });
      if (r.conversation_id !== s.conversationId) {
        localStorage.setItem("jarvis.conversation", r.conversation_id);
        set({ conversationId: r.conversation_id });
      }
    } catch (e: any) {
      set({ busy: false, agentState: "idle" });
      getState().toast({ title: "No se pudo enviar", message: e.message, tone: "danger" });
    }
  },

  stop: async () => {
    await post("/api/chat/stop", { conversation_id: getState().conversationId });
  },

  toast: (t) => {
    const id = toastId++;
    set({ toasts: [...getState().toasts, { ...t, id }] });
    window.setTimeout(() => getState().dismissToast(id), t.tone === "danger" ? 9000 : 6000);
  },
  dismissToast: (id) => set({ toasts: getState().toasts.filter((t) => t.id !== id) }),

  handleEvent: (ev) => {
    const s = getState();
    const mine = ev.conversation_id && ev.conversation_id === s.conversationId;
    const bump = (k: string) => set({ versions: { ...getState().versions, [k]: (getState().versions[k] ?? 0) + 1 } });

    const commitLive = (items: ChatItem[]) => {
      const st = getState();
      const out = [...items];
      if (st.progress.trim()) out.push({ kind: "progress", text: st.progress.trim() });
      if (st.streaming.trim()) out.push({ kind: "assistant", text: st.streaming });
      return out;
    };
    const finishServerTools = (items: ChatItem[]) =>
      items.map((i) => (i.kind === "tool" && i.server && i.running ? { ...i, running: false } : i));

    switch (ev.type) {
      case "hello":
        set({ approvals: ev.approvals, emergency: ev.emergency });
        break;
      case "system_stats":
        set({ stats: ev.stats });
        break;
      case "run_start":
        if (mine) set({ busy: true, agentState: "thinking", streaming: "", progress: "" });
        break;
      case "assistant_delta":
        if (mine) {
          const items = s.progress.trim() ? [...s.items, { kind: "progress", text: s.progress.trim() } as ChatItem] : s.items;
          set({ streaming: s.streaming + ev.text, progress: "", items: finishServerTools(items) });
        }
        break;
      case "progress":
        if (mine) set({ progress: s.progress + ev.text });
        break;
      case "tool_requested":
        if (mine && (ev.tool === "web_search" || ev.tool === "web_fetch")) {
          set({ items: [...commitLive(s.items), { kind: "tool", name: ev.tool, server: true, running: true,
                                                  summary: ev.tool === "web_search" ? "Buscando en Internet" : "Leyendo página web" }],
                streaming: "", progress: "" });
        }
        break;
      case "tool_start":
        if (mine) {
          set({ items: [...finishServerTools(commitLive(s.items)), { kind: "tool", id: ev.call_id, name: ev.tool,
                summary: ev.summary, risk: ev.risk, running: true }], streaming: "", progress: "" });
        }
        break;
      case "tool_end":
        if (mine) {
          set({ items: s.items.map((i) => (i.kind === "tool" && i.id === ev.call_id
            ? { ...i, running: false, result: ev.preview, is_error: !ev.ok, files: ev.files } : i)) });
        }
        break;
      case "plan":
        if (mine) set({ plan: { goal: ev.goal, steps: ev.steps } });
        if (ev.job_id) set({ jobs: s.jobs.map((j) => (j.id === ev.job_id ? { ...j, plan: ev.steps } : j)) });
        break;
      case "run_end":
        if (mine) {
          set({ busy: false, lastRunFiles: ev.files ?? [], agentState: getState().agentState === "speaking" ? "speaking" : "idle" });
          getState().loadConversation(ev.conversation_id).then(() => set({ streaming: "", progress: "" }));
          if (ev.error) getState().toast({ title: "JARVIS", message: ev.error, tone: "danger" });
        }
        bump("conversations");
        break;
      case "approval_request":
        set({ approvals: [...s.approvals.filter((a) => a.id !== ev.approval.id), ev.approval] });
        break;
      case "approval_resolved":
        set({ approvals: s.approvals.filter((a) => a.id !== ev.id) });
        break;
      case "emergency":
        set({ emergency: ev.engaged });
        if (ev.engaged) set({ busy: false, agentState: "idle" });
        getState().toast({ title: ev.engaged ? "Parada de emergencia" : "Sistemas reanudados",
          message: ev.engaged ? `${ev.cancelled} tareas canceladas. No se ejecutarán acciones.` : "JARVIS vuelve a estar operativo.",
          tone: ev.engaged ? "danger" : "ok" });
        break;
      case "job_update": {
        const others = s.jobs.filter((j) => j.id !== ev.job.id);
        set({ jobs: [ev.job, ...others].sort((a, b) => b.created_at - a.created_at).slice(0, 50) });
        break;
      }
      case "notification":
        getState().toast({ title: ev.title, message: ev.message, tone: "info", files: ev.files });
        break;
      case "conversation_compacted":
        if (mine) getState().loadConversation(ev.conversation_id);
        break;
      case "memory_changed":
        bump("memory");
        break;
      case "memory_learned":
        getState().toast({ title: "Lo tendré en cuenta", message: (ev.facts ?? []).join(" · "), tone: "info" });
        break;
      case "tasks_changed":
        bump("tasks");
        break;
      case "automations_changed":
        bump("automations");
        break;
      case "telegram_paired":
        getState().toast({ title: "Telegram emparejado", message: `@${ev.username || ev.user_id} ya puede hablar con JARVIS.`, tone: "ok" });
        getState().refreshStatus();
        break;
      case "telegram_unauthorized":
        getState().toast({ title: "Telegram: acceso no autorizado", message: `Intento de @${ev.username || "?"} (id ${ev.user_id}) bloqueado.`, tone: "warn" });
        break;
    }
  },
}));
