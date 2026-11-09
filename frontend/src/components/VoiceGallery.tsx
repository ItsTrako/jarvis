import { motion } from "framer-motion";
import { AudioLines, Check, Crown, Loader2, Pause, Play, Sparkles } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api, get, patch } from "../lib/api";
import { useJarvis } from "../lib/store";
import { Badge, Select, cx } from "./ui";

interface VoiceOpt {
  engine: "edge" | "elevenlabs";
  id: string;
  name: string;
  desc: string;
  accent: string;
  gender: "m" | "f";
  tag?: string;
}

// Voces neuronales gratuitas seleccionadas. Las «Multilingual» son la generación más reciente de
// Microsoft: entonación más natural y conversacional (hablan español aunque su código sea en-US).
const EDGE: VoiceOpt[] = [
  { engine: "edge", id: "en-US-AndrewMultilingualNeural", name: "Andrew", desc: "Cálida, segura y muy natural", accent: "Multilingüe", gender: "m", tag: "Más natural" },
  { engine: "edge", id: "en-US-BrianMultilingualNeural", name: "Brian", desc: "Cercana y conversacional", accent: "Multilingüe", gender: "m" },
  { engine: "edge", id: "es-ES-AlvaroNeural", name: "Álvaro", desc: "Clara, acento de España", accent: "España", gender: "m", tag: "Castellano" },
  { engine: "edge", id: "fr-FR-RemyMultilingualNeural", name: "Rémy", desc: "Grave y elegante", accent: "Multilingüe", gender: "m" },
  { engine: "edge", id: "de-DE-FlorianMultilingualNeural", name: "Florian", desc: "Serena y profunda", accent: "Multilingüe", gender: "m" },
  { engine: "edge", id: "es-MX-JorgeNeural", name: "Jorge", desc: "Natural, acento mexicano", accent: "México", gender: "m" },
  { engine: "edge", id: "en-US-AvaMultilingualNeural", name: "Ava", desc: "Expresiva y amable", accent: "Multilingüe", gender: "f", tag: "Más natural" },
  { engine: "edge", id: "en-US-EmmaMultilingualNeural", name: "Emma", desc: "Alegre y clara", accent: "Multilingüe", gender: "f" },
  { engine: "edge", id: "es-ES-ElviraNeural", name: "Elvira", desc: "Clara, acento de España", accent: "España", gender: "f", tag: "Castellano" },
  { engine: "edge", id: "es-ES-XimenaNeural", name: "Ximena", desc: "Joven y cercana", accent: "España", gender: "f" },
  { engine: "edge", id: "de-DE-SeraphinaMultilingualNeural", name: "Seraphina", desc: "Suave y sofisticada", accent: "Multilingüe", gender: "f" },
  { engine: "edge", id: "es-MX-DaliaNeural", name: "Dalia", desc: "Natural, acento mexicano", accent: "México", gender: "f" },
];

const SAMPLE = (name: string) =>
  `Buenas noches${name ? `, ${name}` : ""}. Todos los sistemas están operativos. He revisado tu agenda: tienes dos tareas pendientes y la investigación que me pediste ya está lista. ¿Por dónde quieres empezar?`;

export function VoiceGallery({ cfg, secrets, onSaved }: { cfg: any; secrets: Record<string, boolean>; onSaved: () => void }) {
  const [playing, setPlaying] = useState<string | null>(null);
  const [loading, setLoading] = useState<string | null>(null);
  const [eleven, setEleven] = useState<VoiceOpt[]>([]);
  const audio = useRef<HTMLAudioElement | null>(null);
  const toast = useJarvis((s) => s.toast);
  const userName = useJarvis((s) => s.status?.user?.name ?? "");

  useEffect(() => {
    if (!secrets.elevenlabs_api_key) return;
    get("/api/voice/voices").then((v) => setEleven((v.elevenlabs ?? []).slice(0, 12).map((x: any) => ({
      engine: "elevenlabs", id: x.id, name: x.name, desc: [x.labels?.accent, x.labels?.description, x.labels?.age].filter(Boolean).join(" · ") || "Voz ultra realista",
      accent: "ElevenLabs", gender: x.labels?.gender === "female" ? "f" : "m",
    })))).catch(() => undefined);
  }, [secrets.elevenlabs_api_key]);

  useEffect(() => () => audio.current?.pause(), []);

  const isCurrent = (v: VoiceOpt) =>
    cfg.voice.tts_engine === v.engine &&
    (v.engine === "edge" ? cfg.voice.edge_voice === v.id : (cfg.voice.elevenlabs_voice_id || "JBFqnCBsd6RMkjVDRZzb") === v.id);

  const preview = async (v: VoiceOpt) => {
    const key = `${v.engine}:${v.id}`;
    audio.current?.pause();
    if (playing === key) {
      setPlaying(null);
      return;
    }
    setLoading(key);
    try {
      const r: Response = await api("/api/voice/tts", { method: "POST", json: { text: SAMPLE(userName), engine: v.engine, voice: v.id } });
      const url = URL.createObjectURL(await r.blob());
      const a = new Audio(url);
      audio.current = a;
      a.onended = () => setPlaying(null);
      await a.play();
      setPlaying(key);
    } catch (e: any) {
      toast({ title: "Voz", message: e.message, tone: "danger" });
    } finally {
      setLoading(null);
    }
  };

  const choose = async (v: VoiceOpt) => {
    await patch("/api/config", { voice: v.engine === "edge" ? { tts_engine: "edge", edge_voice: v.id } : { tts_engine: "elevenlabs", elevenlabs_voice_id: v.id } });
    onSaved();
    toast({ title: "Voz cambiada", message: `JARVIS hablará con la voz de ${v.name}.`, tone: "ok" });
  };

  const Card = ({ v }: { v: VoiceOpt }) => {
    const key = `${v.engine}:${v.id}`;
    const cur = isCurrent(v);
    return (
      <motion.div layout className={cx("group relative flex items-center gap-3 rounded-xl border p-3 transition-colors",
        cur ? "border-electric/50 bg-electric/[0.08] shadow-[0_0_30px_-14px_rgb(168_85_247/0.9)]" : "border-line bg-white/[0.015] hover:border-line-strong")}>
        <button onClick={() => void preview(v)} aria-label={`Escuchar ${v.name}`}
          className={cx("relative grid size-10 shrink-0 place-items-center rounded-full transition-all",
            playing === key ? "bg-electric text-white shadow-[0_0_20px_rgb(168_85_247/0.7)]" : "bg-white/[0.05] text-lavender hover:bg-electric/25")}>
          {loading === key ? <Loader2 size={16} className="animate-spin" /> : playing === key ? <Pause size={15} fill="currentColor" /> : <Play size={15} fill="currentColor" className="ml-0.5" />}
          {playing === key && <span className="absolute inset-0 animate-ping rounded-full bg-electric/30" />}
        </button>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5">
            <span className="font-display text-[14px] font-semibold text-ink">{v.name}</span>
            {v.tag && <Badge tone="purple">{v.tag}</Badge>}
          </div>
          <div className="truncate text-[11.5px] text-muted">{v.desc}</div>
          <div className="text-[10.5px] text-faint">{v.accent} · {v.gender === "m" ? "masculina" : "femenina"}</div>
        </div>
        <button onClick={() => void choose(v)} disabled={cur}
          className={cx("shrink-0 rounded-lg px-2.5 py-1.5 text-xs transition-colors",
            cur ? "text-ok" : "border border-line-strong text-muted hover:border-electric/40 hover:text-ink")}>
          {cur ? <span className="flex items-center gap-1"><Check size={13} /> En uso</span> : "Usar"}
        </button>
      </motion.div>
    );
  };

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-line bg-black/20 p-3 text-xs leading-relaxed text-muted">
        <span className="flex items-center gap-1.5 font-medium text-ink"><AudioLines size={14} className="text-lavender" /> Escúchalas y elige</span>
        Pulsa ▶ para oír cada voz diciendo una frase típica de JARVIS. Las <b className="text-lavender">Multilingües</b> son la
        generación más reciente y suenan mucho más humanas; las de <b className="text-lavender">España</b> tienen acento castellano nativo.
      </div>

      <div className="grid gap-2 sm:grid-cols-2">{EDGE.map((v) => <Card key={v.id} v={v} />)}</div>

      <div className="rounded-2xl border border-electric/25 bg-[radial-gradient(120%_120%_at_0%_0%,rgb(168_85_247/0.14),transparent_60%)] p-4">
        <div className="flex items-center gap-2 font-display text-[14px] font-semibold text-ink"><Crown size={15} className="text-lavender" /> ElevenLabs · realismo máximo</div>
        <p className="mt-1 text-xs leading-relaxed text-muted">
          Las voces más humanas que existen: respiración, emoción y matices. Tiene plan gratuito mensual.
          {!secrets.elevenlabs_api_key && <> Crea una cuenta en <a className="text-lavender underline" href="https://elevenlabs.io" target="_blank" rel="noreferrer">elevenlabs.io</a>, copia tu API key y pégala en <b>Credenciales</b>: aparecerán aquí sus voces.</>}
        </p>
        {secrets.elevenlabs_api_key && (
          <div className="mt-3 grid gap-2 sm:grid-cols-2">
            {(eleven.length ? eleven : [{ engine: "elevenlabs", id: "JBFqnCBsd6RMkjVDRZzb", name: "George", desc: "Cálida y británica, estilo JARVIS", accent: "ElevenLabs", gender: "m", tag: "Recomendada" } as VoiceOpt])
              .map((v) => <Card key={v.id} v={v} />)}
          </div>
        )}
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <label className="block">
          <span className="mb-1.5 flex items-center gap-1.5 text-xs text-muted"><Sparkles size={13} /> Velocidad al hablar</span>
          <Select value={cfg.voice.edge_rate} onChange={async (r) => { await patch("/api/config", { voice: { edge_rate: r } }); onSaved(); }}
            options={[{ value: "-10%", label: "Pausada" }, { value: "-5%", label: "Tranquila" }, { value: "+0%", label: "Natural" },
                      { value: "+5%", label: "Ágil" }, { value: "+10%", label: "Rápida" }]} />
        </label>
      </div>
    </div>
  );
}
