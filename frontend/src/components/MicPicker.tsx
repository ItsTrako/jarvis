import { AnimatePresence, motion } from "framer-motion";
import { Loader2, Mic, MicVocal, RefreshCw, Square } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { patch } from "../lib/api";
import { useJarvis } from "../lib/store";
import { listMics, micErrorMessage, monitorMic, Recorder, setPreferredMic, transcribe } from "../lib/voice";
import { Button, cx } from "./ui";

/** Nombre limpio del dispositivo: «Micrófono (DGM20 USB Microphone) (1234:abcd)» → «DGM20 USB Microphone». */
function deviceName(label: string) {
  const m = label.match(/\(([^()]+)\)/);
  return (m ? m[1] : label).trim();
}

export function MicPicker() {
  const status = useJarvis((s) => s.status);
  const refreshStatus = useJarvis((s) => s.refreshStatus);
  const toast = useJarvis((s) => s.toast);
  const [mics, setMics] = useState<MediaDeviceInfo[]>([]);
  const [err, setErr] = useState("");
  const [level, setLevel] = useState(0);
  const [peak, setPeak] = useState(0);
  const [testing, setTesting] = useState<"none" | "level" | "stt">("none");
  const [heard, setHeard] = useState<string | null>(null);
  const stopRef = useRef<(() => void) | null>(null);
  const current = status?.voice?.mic_label ?? "";

  const load = async () => {
    try {
      setErr("");
      setMics(await listMics());
    } catch (e) {
      setErr(micErrorMessage(e));
    }
  };
  useEffect(() => {
    void load();
    navigator.mediaDevices.addEventListener("devicechange", load);
    return () => {
      navigator.mediaDevices.removeEventListener("devicechange", load);
      stopRef.current?.();
    };
  }, []);

  const choose = async (label: string) => {
    stopRef.current?.();
    setTesting("none");
    setPreferredMic(label);
    await patch("/api/config", { voice: { mic_label: label } });
    await refreshStatus();
  };

  const testLevel = async () => {
    if (testing === "level") {
      stopRef.current?.();
      setTesting("none");
      return;
    }
    try {
      setPeak(0);
      setTesting("level");
      stopRef.current = await monitorMic((v) => {
        setLevel(v);
        setPeak((p) => Math.max(p * 0.995, v));
      });
      window.setTimeout(() => { stopRef.current?.(); setTesting((t) => (t === "level" ? "none" : t)); }, 10000);
    } catch (e) {
      setTesting("none");
      setErr(micErrorMessage(e));
    }
  };

  const testStt = async () => {
    stopRef.current?.();
    setHeard(null);
    setTesting("stt");
    try {
      const rec = new Recorder();
      const r = await rec.start({ maxMs: 8000, noSpeechMs: 6000 });
      if (!r.blob) {
        setHeard("");
        return;
      }
      const t = await transcribe(r.blob);
      setHeard(t.text);
    } catch (e) {
      setErr(micErrorMessage(e));
    } finally {
      setTesting("none");
    }
  };

  const selected = mics.find((m) => current && m.label.toLowerCase().includes(current.toLowerCase()));

  return (
    <div className="space-y-3">
      <div className="flex gap-2">
        <select
          value={selected ? deviceName(selected.label) : ""}
          onChange={(e) => void choose(e.target.value)}
          className="w-full rounded-xl border border-line-strong bg-abyss px-3 py-2 text-ink outline-none focus:border-electric/50"
        >
          <option value="">Predeterminado de Windows</option>
          {mics.map((m) => (
            <option key={m.deviceId} value={deviceName(m.label)}>{deviceName(m.label) || "Micrófono sin nombre"}</option>
          ))}
        </select>
        <button onClick={() => void load()} title="Volver a buscar micrófonos" aria-label="Actualizar lista"
          className="grid size-10 shrink-0 place-items-center rounded-xl border border-line-strong text-muted hover:text-ink">
          <RefreshCw size={15} />
        </button>
      </div>
      {current && !selected && mics.length > 0 && (
        <p className="text-xs text-warn">No encuentro «{current}» conectado ahora mismo; se usará el predeterminado.</p>
      )}

      <div className="rounded-xl border border-line bg-black/20 p-3">
        <div className="flex items-center gap-3">
          <Mic size={15} className={cx(testing === "level" ? "text-lavender" : "text-faint")} />
          <div className="relative h-2.5 flex-1 overflow-hidden rounded-full bg-white/[0.06]">
            <motion.div className="absolute inset-y-0 left-0 rounded-full bg-gradient-to-r from-lavender to-electric"
              animate={{ width: `${Math.round(level * 100)}%` }} transition={{ duration: 0.08 }} />
            {peak > 0.02 && <div className="absolute inset-y-0 w-0.5 bg-ink/70" style={{ left: `${Math.min(99, peak * 100)}%` }} />}
          </div>
          <span className="w-10 text-right font-mono text-[11px] text-muted">{Math.round(level * 100)}%</span>
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          <Button variant="ghost" onClick={() => void testLevel()} disabled={testing === "stt"}>
            {testing === "level" ? <><Square size={13} fill="currentColor" /> Parar</> : <><Mic size={14} /> Probar nivel</>}
          </Button>
          <Button variant="ghost" onClick={() => void testStt()} disabled={testing !== "none"}>
            {testing === "stt" ? <><Loader2 size={14} className="animate-spin" /> Escuchando… habla ahora</> : <><MicVocal size={14} /> Probar reconocimiento</>}
          </Button>
        </div>
        <AnimatePresence>
          {heard !== null && (
            <motion.p initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
              className={cx("mt-3 rounded-lg px-3 py-2 text-sm", heard ? "bg-ok/10 text-ok" : "bg-warn/10 text-warn")}>
              {heard ? <>He entendido: «{heard}»</> : "No he oído nada con este micrófono. Prueba otro o sube su volumen en Windows."}
            </motion.p>
          )}
        </AnimatePresence>
        {testing === "level" && level < 0.03 && peak < 0.03 && (
          <p className="mt-2 text-xs text-faint">Habla un poco: la barra debería moverse.</p>
        )}
      </div>
      {err && (
        <p className="text-xs text-danger">
          {err}{" "}
          <button className="underline" onClick={() => { setErr(""); toast({ title: "Micrófono", message: "Reintentando…", tone: "info" }); void load(); }}>Reintentar</button>
        </p>
      )}
    </div>
  );
}
