import { Ear, Headphones, Timer } from "lucide-react";
import { useEffect, useState } from "react";
import { get } from "../lib/api";
import { useVoice } from "../lib/voiceStore";
import { Select, Toggle, cx } from "./ui";

const STATE: Record<string, string> = {
  off: "Desactivada", standby: "Esperando «Hey JARVIS»", listening: "Escuchándote", transcribing: "Entendiendo",
  thinking: "Pensando", speaking: "Hablando", error: "Error: revisa el micrófono",
};

export function AlwaysOn({ cfg, save }: { cfg: any; save: (p: any) => Promise<void> }) {
  const v = useVoice();
  const [outs, setOuts] = useState<string[]>([]);
  useEffect(() => {
    get("/api/voice/devices").then((d) => setOuts(d.outputs ?? [])).catch(() => undefined);
  }, []);
  const on = v.assistant !== "off";
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3">
        <Toggle checked={on} onChange={(x) => void v.setWake(x)} disabled={!v.micEnabled} label="Escucha permanente" />
        <span className={cx("flex items-center gap-1.5 text-sm", on ? "text-lavender" : "text-muted")}>
          <Ear size={14} /> {STATE[v.assistant] ?? v.assistant}
        </span>
      </div>
      {on && v.assistantDevice && <div className="text-[11px] text-faint">Micrófono del servicio: {v.assistantDevice}</div>}
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="block">
          <span className="mb-1.5 flex items-center gap-1.5 text-xs text-muted"><Headphones size={13} /> Salida de voz</span>
          <Select value={cfg.voice.output_device} onChange={(d) => void save({ voice: { output_device: d } })}
            options={[{ value: "", label: "Predeterminada de Windows" }, ...outs.map((o) => ({ value: o, label: o }))]} />
        </label>
        <label className="block">
          <span className="mb-1.5 flex items-center gap-1.5 text-xs text-muted"><Timer size={13} /> Seguir escuchando tras responder</span>
          <Select value={String(cfg.voice.follow_up_s)} onChange={(s) => void save({ voice: { follow_up_s: parseFloat(s) } })}
            options={[{ value: "5", label: "5 segundos" }, { value: "8", label: "8 segundos" }, { value: "12", label: "12 segundos" },
                      { value: "20", label: "20 segundos" }]} />
        </label>
      </div>
    </div>
  );
}
