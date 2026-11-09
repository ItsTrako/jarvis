// Voz en el navegador: grabación con detección de silencio, reproducción TTS por frases
// (baja latencia), nivel de audio para el núcleo visual y palabra de activación.

import { ensureToken, uploadFile, wsUrl } from "./api";

// ------------------------------------------------------------ nivel de audio compartido
let level = 0;
// Nivel que envía el servicio de voz permanente (micrófono / voz de JARVIS en el PC)
let remoteLevel = 0;
let remoteAt = 0;
export function setRemoteLevel(v: number) {
  remoteLevel = v;
  remoteAt = performance.now();
}
export const audioLevel = () => {
  const age = (performance.now() - remoteAt) / 1000;
  const r = age < 0.4 ? remoteLevel : remoteLevel * Math.max(0, 1 - (age - 0.4) * 3);
  return Math.max(level, r);
};

let ctx: AudioContext | null = null;
function audioCtx(): AudioContext {
  if (!ctx) ctx = new AudioContext();
  if (ctx.state === "suspended") void ctx.resume();
  return ctx;
}

function rms(analyser: AnalyserNode, buf: Float32Array) {
  analyser.getFloatTimeDomainData(buf);
  let s = 0;
  for (let i = 0; i < buf.length; i++) s += buf[i] * buf[i];
  return Math.sqrt(s / buf.length);
}

// ------------------------------------------------------------ selección de micrófono
// El navegador usa por defecto el micrófono predeterminado de Windows; con varios micrófonos
// (webcam, cascos, Steam…) eso suele fallar. Se elige por nombre (p. ej. "DGM20").
let preferredMic = "";

export function setPreferredMic(label: string) {
  preferredMic = (label || "").trim();
}

export async function listMics(): Promise<MediaDeviceInfo[]> {
  let devs = (await navigator.mediaDevices.enumerateDevices()).filter((d) => d.kind === "audioinput");
  if (devs.length && devs.every((d) => !d.label)) {
    // Sin permiso concedido aún, los nombres vienen vacíos: se pide una vez y se vuelve a listar
    const s = await navigator.mediaDevices.getUserMedia({ audio: true });
    s.getTracks().forEach((t) => t.stop());
    devs = (await navigator.mediaDevices.enumerateDevices()).filter((d) => d.kind === "audioinput");
  }
  return devs.filter((d) => d.deviceId !== "default" && d.deviceId !== "communications");
}

export async function findMic(): Promise<MediaDeviceInfo | undefined> {
  if (!preferredMic) return undefined;
  const q = preferredMic.toLowerCase();
  return (await listMics()).find((d) => d.label.toLowerCase().includes(q));
}

export async function micConstraints(): Promise<MediaTrackConstraints> {
  // Sin supresión de ruido del navegador: deforma la voz y empeora la transcripción de Whisper
  const base: MediaTrackConstraints = { echoCancellation: true, noiseSuppression: false, autoGainControl: true, channelCount: 1 };
  const mic = await findMic();
  return mic ? { ...base, deviceId: { exact: mic.deviceId } } : base;
}

export function micErrorMessage(e: any): string {
  const n = e?.name;
  if (n === "NotAllowedError" || n === "SecurityError")
    return "Permiso de micrófono denegado. Pulsa el candado junto a la dirección de la ventana y permite el micrófono.";
  if (n === "NotFoundError" || n === "OverconstrainedError")
    return `No encuentro el micrófono${preferredMic ? ` «${preferredMic}»` : ""}. ¿Está conectado? Elige otro en Configuración → Voz.`;
  if (n === "NotReadableError")
    return "El micrófono está bloqueado por otra aplicación o por Windows. Ciérrala o revisa Configuración de Windows → Privacidad → Micrófono.";
  return e?.message || "No se pudo usar el micrófono.";
}

/** Abre el micrófono elegido y llama a onLevel con el nivel (0-1) hasta que se llame a stop(). */
export async function monitorMic(onLevel: (v: number) => void): Promise<() => void> {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: await micConstraints() });
  const ac = audioCtx();
  const analyser = ac.createAnalyser();
  analyser.fftSize = 1024;
  ac.createMediaStreamSource(stream).connect(analyser);
  const buf = new Float32Array(analyser.fftSize);
  let raf = 0;
  const tick = () => {
    onLevel(Math.min(1, rms(analyser, buf) * 9));
    raf = requestAnimationFrame(tick);
  };
  tick();
  return () => {
    cancelAnimationFrame(raf);
    stream.getTracks().forEach((t) => t.stop());
    onLevel(0);
  };
}

// ------------------------------------------------------------ sonidos de interfaz
export function chime(kind: "start" | "stop" | "wake" = "start") {
  const ac = audioCtx();
  const now = ac.currentTime;
  const notes = kind === "stop" ? [784, 523] : kind === "wake" ? [523, 784, 1046] : [523, 784];
  notes.forEach((f, i) => {
    const o = ac.createOscillator();
    const g = ac.createGain();
    o.type = "sine";
    o.frequency.value = f;
    g.gain.setValueAtTime(0, now + i * 0.07);
    g.gain.linearRampToValueAtTime(0.06, now + i * 0.07 + 0.015);
    g.gain.exponentialRampToValueAtTime(0.0001, now + i * 0.07 + 0.32);
    o.connect(g).connect(ac.destination);
    o.start(now + i * 0.07);
    o.stop(now + i * 0.07 + 0.35);
  });
}

// ------------------------------------------------------------ grabación
export interface RecordResult {
  blob: Blob | null;
  reason: "silence" | "manual" | "timeout" | "no-speech" | "cancel";
}

export class Recorder {
  private stream: MediaStream | null = null;
  private rec: MediaRecorder | null = null;
  private raf = 0;
  private resolve: ((r: RecordResult) => void) | null = null;
  private reason: RecordResult["reason"] = "manual";
  active = false;

  async start(opts: { maxMs?: number; silenceMs?: number; noSpeechMs?: number } = {}): Promise<RecordResult> {
    const { maxMs = 30000, silenceMs = 1300, noSpeechMs = 7000 } = opts;
    this.stream = await navigator.mediaDevices.getUserMedia({ audio: await micConstraints() });
    const ac = audioCtx();
    const src = ac.createMediaStreamSource(this.stream);
    const analyser = ac.createAnalyser();
    analyser.fftSize = 1024;
    src.connect(analyser);
    const buf = new Float32Array(analyser.fftSize);
    const mime = MediaRecorder.isTypeSupported("audio/webm;codecs=opus") ? "audio/webm;codecs=opus" : "audio/webm";
    this.rec = new MediaRecorder(this.stream, { mimeType: mime, audioBitsPerSecond: 64000 });
    const chunks: Blob[] = [];
    this.rec.ondataavailable = (e) => e.data.size && chunks.push(e.data);
    this.active = true;
    const started = performance.now();
    let speechAt = 0;
    let lastVoice = 0;
    let noise = 0.01;

    const loop = () => {
      if (!this.active) return;
      const v = rms(analyser, buf);
      level = Math.min(1, v * 9);
      const t = performance.now();
      if (t - started < 400) noise = Math.max(noise * 0.9 + v * 0.1, 0.006);
      const thr = Math.max(0.018, noise * 2.6);
      if (v > thr) {
        lastVoice = t;
        if (!speechAt) speechAt = t;
      }
      if (speechAt && t - lastVoice > silenceMs) return this.finish("silence");
      if (!speechAt && t - started > noSpeechMs) return this.finish("no-speech");
      if (t - started > maxMs) return this.finish("timeout");
      this.raf = requestAnimationFrame(loop);
    };

    return new Promise<RecordResult>((resolve) => {
      this.resolve = resolve;
      this.rec!.onstop = () => {
        level = 0;
        this.stream?.getTracks().forEach((tr) => tr.stop());
        const blob = chunks.length && this.reason !== "no-speech" && this.reason !== "cancel"
          ? new Blob(chunks, { type: mime }) : null;
        this.resolve?.({ blob, reason: this.reason });
        this.resolve = null;
      };
      this.rec!.start(250);
      this.raf = requestAnimationFrame(loop);
    });
  }

  finish(reason: RecordResult["reason"] = "manual") {
    if (!this.active) return;
    this.active = false;
    this.reason = reason;
    cancelAnimationFrame(this.raf);
    if (this.rec && this.rec.state !== "inactive") this.rec.stop();
  }
}

export async function transcribe(blob: Blob): Promise<{ text: string; elapsed: number }> {
  return uploadFile(blob, "voz.webm", "/api/voice/transcribe");
}

// ------------------------------------------------------------ reproducción TTS (streaming)
// Cada frase se pide al servidor como MP3 en streaming: el navegador empieza a reproducir con los
// primeros fragmentos (~0,3 s) en vez de esperar al audio completo. Las siguientes frases se van
// descargando en paralelo mientras suena la actual.

let ttsToken: string | null = null;
async function ttsUrl(text: string): Promise<string> {
  ttsToken = ttsToken ?? (await ensureToken());
  return `/api/voice/tts/stream?text=${encodeURIComponent(text)}&token=${encodeURIComponent(ttsToken)}`;
}

type SpeakerListener = (speaking: boolean) => void;

export class Speaker {
  private queue: Promise<HTMLAudioElement>[] = [];
  private playing = false;
  private current: HTMLAudioElement | null = null;
  private listeners = new Set<SpeakerListener>();
  private raf = 0;
  private generation = 0;
  speaking = false;

  onChange(fn: SpeakerListener) {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }
  private set(s: boolean) {
    if (this.speaking === s) return;
    this.speaking = s;
    this.listeners.forEach((f) => f(s));
  }

  enqueue(text: string) {
    const t = text.trim();
    if (!t || !/\w/.test(t)) return;
    const gen = this.generation;
    // La descarga empieza ya (preload): cuando le toque sonar, el audio ya estará llegando
    const p = ttsUrl(t).then((url) => {
      const a = new Audio();
      a.preload = "auto";
      a.src = url;
      return a;
    });
    this.queue.push(p);
    if (!this.playing && gen === this.generation) void this.drain();
  }

  private async drain() {
    this.playing = true;
    const gen = this.generation;
    const ac = audioCtx();
    while (this.queue.length && gen === this.generation) {
      let a: HTMLAudioElement;
      try {
        a = await this.queue.shift()!;
      } catch {
        continue;
      }
      if (gen !== this.generation) break;
      this.current = a;
      this.set(true);
      try {
        const src = ac.createMediaElementSource(a);
        const analyser = ac.createAnalyser();
        analyser.fftSize = 1024;
        const buf = new Float32Array(analyser.fftSize);
        src.connect(analyser);
        analyser.connect(ac.destination);
        const tick = () => {
          level = Math.min(1, rms(analyser, buf) * 6);
          this.raf = requestAnimationFrame(tick);
        };
        tick();
      } catch {
        /* sin analizador: suena igual */
      }
      await new Promise<void>((resolve) => {
        const done = () => {
          cancelAnimationFrame(this.raf);
          level = 0;
          resolve();
        };
        a.onended = done;
        a.onerror = done;
        a.play().catch(done);
      });
      this.current = null;
    }
    this.playing = false;
    if (gen === this.generation) this.set(false);
  }

  stop() {
    this.generation++;
    this.queue = [];
    if (this.current) {
      this.current.pause();
      this.current.src = "";
    }
    this.current = null;
    cancelAnimationFrame(this.raf);
    level = 0;
    this.playing = false;
    this.set(false);
  }
}

export const speaker = new Speaker();

/** Trocea el texto que llega en streaming en frases y las va encolando para hablar. */
export class SentenceStreamer {
  private buf = "";
  private inCode = false;
  private started = false;
  private lastFeed = 0;
  private timer: number | undefined;

  feed(delta: string) {
    this.buf += delta;
    this.lastFeed = performance.now();
    if (this.timer === undefined) this.timer = window.setInterval(() => this.tick(), 350);
    for (;;) {
      // Primera frase en cuanto hay una coma (voz casi instantánea); después, frase a frase
      const m = (!this.started && this.buf.match(/^([\s\S]{12,}?[.!?…:;,])(\s)/)) ||
        this.buf.match(/^([\s\S]{20,}?[.!?…:;])(\s|\n)/) || this.buf.match(/^([\s\S]+?)\n\n/) ||
        this.buf.match(/^([\s\S]{160,}?[,;])(\s)/);
      if (!m) break;
      this.emit(m[1]);
      this.buf = this.buf.slice(m[0].length);
    }
  }

  private emit(sentence: string) {
    this.started = true;
    if ((sentence.match(/```/g) || []).length % 2 === 1) {
      this.inCode = !this.inCode;
      return;
    }
    if (!this.inCode) speaker.enqueue(sentence);
  }

  /** Si el texto llega lento (IA local ocupada), adelanta la voz cortando en el último espacio. */
  private tick() {
    if (this.inCode || this.buf.length < 28 || performance.now() - this.lastFeed < 700) return;
    const cut = this.buf.lastIndexOf(" ");
    if (cut < 14) return;
    this.emit(this.buf.slice(0, cut));
    this.buf = this.buf.slice(cut + 1);
  }

  private stopTimer() {
    window.clearInterval(this.timer);
    this.timer = undefined;
  }

  flush() {
    this.stopTimer();
    if (this.buf.trim() && !this.inCode) speaker.enqueue(this.buf);
    this.buf = "";
    this.inCode = false;
    this.started = false;
  }

  reset() {
    this.stopTimer();
    this.buf = "";
    this.inCode = false;
    this.started = false;
  }
}

// ------------------------------------------------------------ palabra de activación
const WORKLET = `
class Down extends AudioWorkletProcessor {
  constructor() { super(); this.ratio = sampleRate / 16000; this.acc = []; this.pos = 0; }
  process(inputs) {
    const ch = inputs[0][0];
    if (!ch) return true;
    for (let i = 0; i < ch.length; i++) {
      this.pos += 1;
      if (this.pos >= this.ratio) { this.pos -= this.ratio; this.acc.push(ch[i]); }
    }
    if (this.acc.length >= 1280) {
      const out = new Int16Array(this.acc.length);
      for (let i = 0; i < this.acc.length; i++) out[i] = Math.max(-1, Math.min(1, this.acc[i])) * 32767;
      this.port.postMessage(out.buffer, [out.buffer]);
      this.acc = [];
    }
    return true;
  }
}
registerProcessor('jarvis-down', Down);
`;

export class WakeWordListener {
  private ws: WebSocket | null = null;
  private stream: MediaStream | null = null;
  private node: AudioWorkletNode | null = null;
  private paused = false;
  active = false;

  async start(onWake: () => void, onError: (msg: string) => void) {
    if (this.active) return;
    this.active = true;
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({ audio: await micConstraints() });
      const ac = audioCtx();
      const url = URL.createObjectURL(new Blob([WORKLET], { type: "application/javascript" }));
      await ac.audioWorklet.addModule(url);
      this.node = new AudioWorkletNode(ac, "jarvis-down");
      ac.createMediaStreamSource(this.stream).connect(this.node);
      this.ws = new WebSocket(await wsUrl("/ws/wake"));
      this.ws.binaryType = "arraybuffer";
      this.ws.onmessage = (m) => {
        const ev = JSON.parse(m.data);
        if (ev.type === "wake" && !this.paused) onWake();
        if (ev.type === "error") onError(ev.detail);
      };
      this.ws.onclose = () => {
        if (this.active) onError("Conexión de palabra de activación cerrada");
      };
      this.node.port.onmessage = (e) => {
        if (!this.paused && this.ws?.readyState === 1) this.ws.send(e.data);
      };
    } catch (e: any) {
      this.stop();
      onError(micErrorMessage(e));
    }
  }

  pause(p: boolean) {
    this.paused = p;
  }

  stop() {
    this.active = false;
    this.ws?.close();
    this.ws = null;
    this.node?.disconnect();
    this.node = null;
    this.stream?.getTracks().forEach((t) => t.stop());
    this.stream = null;
  }
}
