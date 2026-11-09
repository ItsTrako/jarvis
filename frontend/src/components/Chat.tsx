import { AnimatePresence, motion } from "framer-motion";
import {
  AlertTriangle, ArrowUp, RotateCcw, Check, ChevronRight, FileText, FolderOpen, Globe, Loader2, Mic, MicOff, Paperclip, Square,
  Volume2, VolumeX, Wrench, X,
} from "lucide-react";
import { memo, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { fileUrl, post, uploadFile } from "../lib/api";
import { useJarvis, type ChatItem } from "../lib/store";
import { useVoice } from "../lib/voiceStore";
import { Badge, cx, riskTone } from "./ui";

const TOOL_LABELS: Record<string, string> = {
  web_search: "Búsqueda web", web_fetch: "Lectura web", system_info: "Estado del sistema", update_plan: "Plan",
  create_document: "Crear documento", read_document: "Leer documento", remember: "Memorizar", recall: "Consultar memoria",
  open_application: "Abrir aplicación", run_command: "Comando", take_screenshot: "Captura de pantalla",
  list_directory: "Listar carpeta", write_file: "Escribir archivo", search_files: "Buscar archivos",
  start_background_task: "Segundo plano", create_task: "Nueva tarea", list_tasks: "Tareas",
  file_info: "Verificar archivo", open_path: "Abrir archivo", list_applications: "Aplicaciones",
  desktop_actions: "Control del escritorio", get_weather: "El tiempo", update_task: "Actualizar tarea",
  check_background_tasks: "Trabajos", organize_folder: "Organizar carpeta", read_file: "Leer archivo",
  list_processes: "Procesos", list_windows: "Ventanas", send_notification: "Notificación",
};

const Markdown = memo(function Markdown({ text }: { text: string }) {
  return (
    <div className="prose-jarvis">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{ a: ({ node, ...p }) => <a {...p} target="_blank" rel="noreferrer" /> }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
});

function FileChip({ path }: { path: string }) {
  const name = path.split(/[\\/]/).pop();
  return (
    <div className="flex items-center gap-2 rounded-xl border border-line-strong bg-white/[0.03] py-1.5 pr-1.5 pl-3 text-xs">
      <FileText size={14} className="text-lavender" />
      <span className="max-w-[220px] truncate text-ink/90">{name}</span>
      <button
        className="rounded-lg px-2 py-1 text-muted hover:bg-white/[0.06] hover:text-ink"
        onClick={async () => window.open(await fileUrl(path), "_blank")}
      >
        Abrir
      </button>
      <button
        className="rounded-lg p-1 text-muted hover:bg-white/[0.06] hover:text-ink"
        title="Mostrar en la carpeta"
        onClick={() => post("/api/files/open", { path })}
      >
        <FolderOpen size={13} />
      </button>
    </div>
  );
}

function ToolRow({ item }: { item: ChatItem }) {
  const [open, setOpen] = useState(false);
  const label = TOOL_LABELS[item.name ?? ""] ?? item.name;
  const Icon = item.server ? Globe : Wrench;
  const summary = item.summary || (item.input ? JSON.stringify(item.input).slice(0, 140) : "");
  if (item.name === "update_plan") return null;
  return (
    <motion.div layout initial={{ opacity: 0, x: -10, filter: "blur(4px)" }} animate={{ opacity: 1, x: 0, filter: "blur(0px)" }} transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }} className="pl-11">
      <button
        onClick={() => setOpen(!open)}
        className="group flex w-full items-center gap-2.5 rounded-xl border border-line bg-white/[0.015] px-3 py-2 text-left text-[12.5px] transition-colors hover:border-line-strong"
      >
        <span className={cx("grid size-6 shrink-0 place-items-center rounded-lg",
          item.is_error ? (item.recovered ? "bg-white/[0.04] text-faint" : "bg-warn/10 text-warn") : item.running ? "bg-electric/15 text-lavender" : "bg-white/[0.04] text-lavender/80")}>
          {item.running ? <Loader2 size={13} className="animate-spin" /> : item.is_error ? (item.recovered ? <RotateCcw size={12} /> : <AlertTriangle size={13} />) : <Icon size={13} />}
        </span>
        <span className={cx("font-medium", item.is_error && item.recovered ? "text-faint" : "text-ink/85")}>{label}</span>
        <span className="min-w-0 flex-1 truncate text-faint">{item.is_error && item.recovered ? "intento fallido · resuelto por otra vía" : summary}</span>
        {item.risk && item.risk !== "seguro" && <Badge tone={riskTone(item.risk)}>{item.risk}</Badge>}
        {!item.running && !item.is_error && <Check size={13} className="text-ok/70" />}
        <ChevronRight size={14} className={cx("text-faint transition-transform", open && "rotate-90")} />
      </button>
      <AnimatePresence>
        {open && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden">
            <div className="mt-1.5 space-y-2 rounded-xl border border-line bg-black/25 p-3 font-mono text-[11px] text-muted">
              {item.input && <pre className="whitespace-pre-wrap break-all">{JSON.stringify(item.input, null, 2).slice(0, 2500)}</pre>}
              {item.result && <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-all border-t border-line pt-2 text-ink/70">{item.result}</pre>}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
      {item.files && item.files.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-2">{item.files.map((f) => <FileChip key={f} path={f} />)}</div>
      )}
    </motion.div>
  );
}

function Avatar() {
  return (
    <div className="relative mt-0.5 grid size-8 shrink-0 place-items-center">
      <div className="absolute inset-0 rounded-full bg-electric/25 blur-[6px]" />
      <div className="relative size-5 rounded-full bg-[radial-gradient(circle_at_35%_30%,#fff,#c4b5fd_35%,#8b5cf6_70%,#2e1065)]" />
    </div>
  );
}

function Message({ item, streaming }: { item: ChatItem; streaming?: boolean }) {
  if (item.kind === "user") {
    return (
      <motion.div initial={{ opacity: 0, y: 12, filter: "blur(8px)", scale: 0.98 }} animate={{ opacity: 1, y: 0, filter: "blur(0px)", scale: 1 }} transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }} className="flex justify-end">
        <div className="max-w-[85%] rounded-2xl rounded-br-md border border-electric/20 bg-gradient-to-br from-purple/25 to-electric/10 px-4 py-2.5 text-[14.5px] leading-relaxed text-ink shadow-[0_10px_30px_-18px_rgb(168_85_247/0.8)]">
          {item.source === "telegram" && <div className="mb-1 text-[10px] tracking-wider text-lavender/70 uppercase">vía Telegram</div>}
          {item.source === "voice" && <div className="mb-1 flex items-center gap-1 text-[10px] tracking-wider text-lavender/70 uppercase"><Mic size={10} /> voz</div>}
          <div className="whitespace-pre-wrap">{item.text}</div>
          {item.attachments && item.attachments.length > 0 && (
            <div className="mt-1.5 text-[11px] text-lavender/70">📎 {item.attachments.length} adjunto(s)</div>
          )}
        </div>
      </motion.div>
    );
  }
  if (item.kind === "assistant") {
    return (
      <motion.div initial={{ opacity: 0, y: 12, filter: "blur(8px)", scale: 0.98 }} animate={{ opacity: 1, y: 0, filter: "blur(0px)", scale: 1 }} transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }} className="flex gap-3">
        <Avatar />
        <div className={cx("min-w-0 flex-1 pt-1", streaming && "caret")}>
          <Markdown text={item.text ?? ""} />
        </div>
      </motion.div>
    );
  }
  if (item.kind === "progress") {
    return (
      <div className="flex items-start gap-2 pl-11 text-[12.5px] italic text-muted">
        <span className="mt-1.5 size-1 shrink-0 rounded-full bg-lavender/60" />
        <span>{item.text}</span>
      </div>
    );
  }
  if (item.kind === "note") {
    return <div className="text-center text-[11px] text-faint">— {item.text} —</div>;
  }
  return <ToolRow item={item} />;
}

export function ChatList() {
  const items = useJarvis((s) => s.items);
  const streaming = useJarvis((s) => s.streaming);
  const progress = useJarvis((s) => s.progress);
  const busy = useJarvis((s) => s.busy);
  const files = useJarvis((s) => s.lastRunFiles);
  const endRef = useRef<HTMLDivElement>(null);
  const boxRef = useRef<HTMLDivElement>(null);
  const stick = useRef(true);

  useEffect(() => {
    if (stick.current) endRef.current?.scrollIntoView({ block: "end" });
  }, [items, streaming, progress, busy]);

  return (
    <div
      ref={boxRef}
      onScroll={(e) => {
        const el = e.currentTarget;
        stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 120;
      }}
      className="h-full space-y-4 overflow-y-auto px-4 py-5 sm:px-6"
    >
      {items.map((it, i) => <Message key={`${it.kind}-${it.id ?? i}-${i}`} item={it.kind === "tool" && it.is_error && i < items.length - 1 ? { ...it, recovered: true } : it} />)}
      {progress.trim() && <Message item={{ kind: "progress", text: progress }} />}
      {streaming && <Message item={{ kind: "assistant", text: streaming }} streaming />}
      {busy && !streaming && !progress && (
        <div className="flex items-center gap-3 pl-1">
          <Avatar />
          <span className="shimmer-text text-sm">Analizando…</span>
        </div>
      )}
      {!busy && files.length > 0 && (
        <div className="flex flex-wrap gap-2 pl-11">{files.map((f) => <FileChip key={f} path={f} />)}</div>
      )}
      <div ref={endRef} className="h-2" />
    </div>
  );
}

export function Composer({ autoFocus }: { autoFocus?: boolean }) {
  const [text, setText] = useState("");
  const [attachments, setAttachments] = useState<{ path: string; name: string }[]>([]);
  const [uploading, setUploading] = useState(false);
  const send = useJarvis((s) => s.send);
  const stop = useJarvis((s) => s.stop);
  const busy = useJarvis((s) => s.busy);
  const emergency = useJarvis((s) => s.emergency);
  const toast = useJarvis((s) => s.toast);
  const v = useVoice();
  const ta = useRef<HTMLTextAreaElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const el = ta.current;
    if (!el) return;
    const fit = () => {
      if (!el.clientWidth) return;
      el.style.height = "auto";
      el.style.height = Math.min(el.scrollHeight, 200) + "px";
    };
    fit();
    const ro = new ResizeObserver(fit);
    ro.observe(el);
    return () => ro.disconnect();
  }, [text]);

  const submit = async () => {
    const t = text.trim();
    if ((!t && !attachments.length) || busy) return;
    setText("");
    const att = attachments.map((a) => a.path);
    setAttachments([]);
    await send(t || "Analiza los archivos adjuntos.", { attachments: att });
  };

  const onFiles = async (files: FileList | null) => {
    if (!files) return;
    setUploading(true);
    try {
      for (const f of Array.from(files).slice(0, 8)) {
        const r = await uploadFile(f, f.name);
        setAttachments((a) => [...a, { path: r.path, name: r.name }]);
      }
    } catch (e: any) {
      toast({ title: "Error al subir", message: e.message, tone: "danger" });
    } finally {
      setUploading(false);
    }
  };

  const micState = v.listening ? "listening" : v.transcribing ? "transcribing" : "idle";

  return (
    <div
      className="glass rounded-2xl p-2"
      onDragOver={(e) => e.preventDefault()}
      onDrop={(e) => {
        e.preventDefault();
        void onFiles(e.dataTransfer.files);
      }}
    >
      {attachments.length > 0 && (
        <div className="flex flex-wrap gap-1.5 px-2 pt-1 pb-2">
          {attachments.map((a) => (
            <span key={a.path} className="flex items-center gap-1.5 rounded-lg border border-line-strong bg-white/[0.03] py-1 pr-1 pl-2 text-xs">
              <FileText size={12} className="text-lavender" /> <span className="max-w-[160px] truncate">{a.name}</span>
              <button aria-label="Quitar" onClick={() => setAttachments((x) => x.filter((y) => y.path !== a.path))}
                className="rounded p-0.5 text-muted hover:text-ink"><X size={12} /></button>
            </span>
          ))}
        </div>
      )}
      <div className="flex items-end gap-1.5">
        <input ref={fileInput} type="file" multiple hidden onChange={(e) => void onFiles(e.target.files)} />
        <button
          onClick={() => fileInput.current?.click()}
          className="grid size-10 shrink-0 place-items-center rounded-xl text-muted transition-colors hover:bg-white/[0.06] hover:text-ink"
          aria-label="Adjuntar archivos" title="Adjuntar archivos (o arrástralos aquí)"
        >
          {uploading ? <Loader2 size={18} className="animate-spin" /> : <Paperclip size={18} />}
        </button>
        <textarea
          ref={ta}
          autoFocus={autoFocus}
          rows={1}
          value={text}
          disabled={emergency}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              void submit();
            }
          }}
          placeholder={emergency ? "Parada de emergencia activa" : v.listening ? "Te escucho…" : "Escribe a JARVIS o pulsa el micrófono…"}
          className="max-h-[200px] min-h-10 flex-1 resize-none bg-transparent px-2 py-2.5 text-[15px] leading-relaxed text-ink outline-none placeholder:text-faint"
        />
        {v.speaking && (
          <button onClick={v.stopSpeaking} title="Detener la voz" aria-label="Detener la voz"
            className="grid size-10 shrink-0 place-items-center rounded-xl text-lavender transition-colors hover:bg-white/[0.06]">
            <VolumeX size={18} />
          </button>
        )}
        <button
          onClick={() => void v.listen()}
          disabled={!v.micEnabled || emergency || (busy && !v.listening)}
          aria-label={v.listening ? "Terminar de hablar" : "Hablar"}
          title={!v.micEnabled ? "Micrófono desactivado" : v.listening ? "Terminar (o deja de hablar)" : "Hablar con JARVIS"}
          className={cx(
            "relative grid size-10 shrink-0 place-items-center rounded-xl transition-all duration-200",
            micState === "listening" ? "bg-electric text-white shadow-[0_0_24px_rgb(168_85_247/0.7)]"
              : micState === "transcribing" ? "bg-electric/30 text-lavender" : "text-muted hover:bg-white/[0.06] hover:text-ink",
          )}
        >
          {micState === "listening" && <span className="absolute inset-0 animate-ping rounded-xl bg-electric/40" />}
          {micState === "transcribing" ? <Loader2 size={18} className="animate-spin" /> : v.micEnabled ? <Mic size={18} className="relative" /> : <MicOff size={18} />}
        </button>
        {busy ? (
          <button onClick={() => void stop()} aria-label="Detener"
            className="grid size-10 shrink-0 place-items-center rounded-xl border border-line-strong bg-white/[0.04] text-ink transition-colors hover:bg-white/[0.08]">
            <Square size={14} fill="currentColor" />
          </button>
        ) : (
          <button onClick={() => void submit()} disabled={(!text.trim() && !attachments.length) || emergency} aria-label="Enviar"
            className="grid size-10 shrink-0 place-items-center rounded-xl bg-gradient-to-b from-electric to-purple text-white shadow-[0_6px_20px_-6px_rgb(168_85_247/0.9)] transition-all hover:brightness-110 active:scale-95 disabled:opacity-30 disabled:shadow-none">
            <ArrowUp size={18} />
          </button>
        )}
      </div>
      <div className="flex items-center gap-3 px-2 pt-1.5 pb-0.5 text-[11px] text-faint">
        <span className="hidden sm:inline">Enter para enviar · Shift+Enter nueva línea</span>
        <button onClick={() => v.setReadAloud(!v.readAloud)}
          className={cx("ml-auto flex items-center gap-1 transition-colors hover:text-ink", v.readAloud && "text-lavender")}>
          {v.readAloud ? <Volume2 size={12} /> : <VolumeX size={12} />} Leer respuestas
        </button>
      </div>
    </div>
  );
}
