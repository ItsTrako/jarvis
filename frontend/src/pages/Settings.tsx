import {
  CheckCircle2, CircleAlert, FolderPlus, KeyRound, Loader2, MapPin, Mic, RefreshCw, Send, Shield, Sparkles, Stethoscope, Trash2, UserRound, X,
} from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { del, get, patch, post, put } from "../lib/api";
import { useJarvis } from "../lib/store";
import { AIEngine } from "../components/AIEngine";
import { MicPicker } from "../components/MicPicker";
import { VoiceGallery } from "../components/VoiceGallery";
import { AlwaysOn } from "../components/AlwaysOn";
import { Badge, Button, Input, PageHeader, Panel, Select, Toggle, cx } from "../components/ui";

type Tab = "credentials" | "model" | "voice" | "telegram" | "security" | "system";
const TABS: { id: Tab; label: string; icon: ReactNode }[] = [
  { id: "model", label: "Inteligencia", icon: <Sparkles size={15} /> },
  { id: "credentials", label: "Credenciales", icon: <KeyRound size={15} /> },
  { id: "voice", label: "Voz", icon: <Mic size={15} /> },
  { id: "telegram", label: "Telegram", icon: <Send size={15} /> },
  { id: "security", label: "Seguridad", icon: <Shield size={15} /> },
  { id: "system", label: "Sistema", icon: <Stethoscope size={15} /> },
];

function AboutYou({ cfg, save }: { cfg: any; save: (p: any) => Promise<void> | void }) {
  const [info, setInfo] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { get("/api/userinfo").then(setInfo).catch(() => undefined); }, [cfg.user.city]);
  const det = info?.perfil?.ubicacion;
  const detected = det ? [det.ciudad, det.region, det.pais].filter(Boolean).join(", ") : "";
  return (
    <Panel title="Sobre ti" icon={<UserRound size={14} />}>
      <Row label="Tu nombre" hint="Cómo te llama JARVIS.">
        <Input defaultValue={cfg.user.name} onBlur={(e) => save({ user: { name: e.target.value } })} placeholder="Tu nombre" />
      </Row>
      <Row label="Tu ciudad" hint={detected ? <>Vacío = automática. Detectada ahora: <b className="text-ink/90">{detected}</b> (aproximada, por la conexión).</> : "Vacío = se detecta sola por la conexión."}>
        <div className="flex gap-2">
          <Input defaultValue={cfg.user.city} onBlur={(e) => save({ user: { city: e.target.value.trim() } })} placeholder={detected || "Automática"} />
          <Button variant="ghost" title="Volver a detectar" disabled={busy}
            onClick={async () => { setBusy(true); try { setInfo(await post("/api/userinfo/refresh")); } finally { setBusy(false); } }}>
            {busy ? <Loader2 size={15} className="animate-spin" /> : <MapPin size={15} />}
          </Button>
        </div>
      </Row>
      <Row label="Ubicación automática" hint="Usa tu ubicación aproximada para el tiempo y lo cercano, sin preguntarte.">
        <Toggle checked={cfg.user.auto_location} onChange={(v) => save({ user: { auto_location: v } })} />
      </Row>
      <Row label="Aprender sobre ti" hint="Guarda en memoria lo que vaya sabiendo de ti (gustos, trabajo, gente, proyectos) para no volver a preguntarte. Lo puedes revisar y borrar en Memoria.">
        <Toggle checked={cfg.user.auto_learn} onChange={(v) => save({ user: { auto_learn: v } })} />
      </Row>
    </Panel>
  );
}

function Row({ label, hint, children }: { label: string; hint?: ReactNode; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-2 border-b border-line px-4 py-3.5 last:border-0 sm:flex-row sm:items-center sm:gap-6">
      <div className="sm:w-64 sm:shrink-0">
        <div className="text-[13.5px] text-ink">{label}</div>
        {hint && <div className="mt-0.5 text-xs leading-snug text-muted">{hint}</div>}
      </div>
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  );
}

const SECRETS = [
  { name: "anthropic_api_key", label: "API key de Anthropic", hint: <>Obligatoria. Créala en <a className="text-lavender underline" href="https://console.anthropic.com/settings/keys" target="_blank" rel="noreferrer">console.anthropic.com</a>.</> },
  { name: "telegram_bot_token", label: "Token del bot de Telegram", hint: <>Habla con <a className="text-lavender underline" href="https://t.me/BotFather" target="_blank" rel="noreferrer">@BotFather</a> → /newbot.</> },
  { name: "elevenlabs_api_key", label: "API key de ElevenLabs", hint: "Opcional: voz premium ultra realista." },
  { name: "azure_speech_key", label: "Clave de Azure Speech", hint: "Opcional: Azure Neural TTS oficial con estilos." },
];

function SecretRow({ s, configured, onChange }: { s: (typeof SECRETS)[number]; configured: boolean; onChange: () => void }) {
  const [v, setV] = useState("");
  const [busy, setBusy] = useState(false);
  const toast = useJarvis((x) => x.toast);
  return (
    <Row label={s.label} hint={s.hint}>
      <div className="flex flex-wrap items-center gap-2">
        {configured ? <Badge tone="ok"><CheckCircle2 size={11} /> Guardada</Badge> : <Badge tone="warn">Sin configurar</Badge>}
        <Input type="password" autoComplete="off" value={v} onChange={(e) => setV(e.target.value)} placeholder={configured ? "Reemplazar…" : "Pegar aquí"} className="!w-auto flex-1" />
        <Button variant="primary" disabled={!v.trim() || busy} onClick={async () => {
          setBusy(true);
          try { await put(`/api/secrets/${s.name}`, { value: v }); setV(""); toast({ title: "Credencial guardada", message: "Cifrada en el Administrador de credenciales de Windows.", tone: "ok" }); onChange(); }
          catch (e: any) { toast({ title: "Error", message: e.message, tone: "danger" }); }
          finally { setBusy(false); }
        }}>{busy ? <Loader2 size={15} className="animate-spin" /> : "Guardar"}</Button>
        {configured && <Button variant="subtle" onClick={async () => { if (confirm("¿Eliminar esta credencial?")) { await del(`/api/secrets/${s.name}`); onChange(); } }}><Trash2 size={14} /></Button>}
      </div>
    </Row>
  );
}

export function Settings() {
  const [tab, setTab] = useState<Tab>(() => (sessionStorage.getItem("jarvis.settingsTab") as Tab) || "model");
  useEffect(() => {
    try { sessionStorage.setItem("jarvis.settingsTab", tab); } catch { /* noop */ }
  }, [tab]);
  const [cfg, setCfg] = useState<any>(null);
  const [secrets, setSecrets] = useState<Record<string, boolean>>({});
  const [voices, setVoices] = useState<any>({ edge: [], elevenlabs: [] });
  const [pairing, setPairing] = useState<{ code: string; bot: string } | null>(null);
  const [pin, setPin] = useState("");
  const [checks, setChecks] = useState<any[] | null>(null);
  const [newRoot, setNewRoot] = useState("");
  const [autostart, setAutostart] = useState(false);
  const status = useJarvis((s) => s.status);
  const refreshStatus = useJarvis((s) => s.refreshStatus);
  const toast = useJarvis((s) => s.toast);

  const load = async () => {
    setCfg(await get("/api/config"));
    setSecrets(await get("/api/secrets"));
    setAutostart((await get("/api/autostart")).enabled);
  };
  useEffect(() => { void load(); }, []);
  useEffect(() => {
    if (tab === "voice" && !voices.edge.length) get("/api/voice/voices").then(setVoices).catch(() => undefined);
    if (tab === "system" && !checks) get("/api/doctor").then(setChecks).catch(() => undefined);
  }, [tab]);

  const save = async (p: any) => {
    try {
      const c = await patch("/api/config", p);
      setCfg({ ...cfg, ...c });
      void refreshStatus();
    } catch (e: any) {
      toast({ title: "No se pudo guardar", message: e.message, tone: "danger" });
    }
  };

  if (!cfg) return <div className="grid h-full place-items-center"><Loader2 className="animate-spin text-lavender" /></div>;
  const tg = status?.telegram;

  return (
    <div className="h-full overflow-y-auto p-4 sm:p-6">
      <div className="mx-auto max-w-4xl">
        <PageHeader title="Configuración" subtitle="Los secretos se guardan cifrados en Windows; el resto en data/config.yaml." />
        <div className="mb-5 flex gap-1 overflow-x-auto pb-1">
          {TABS.map((t) => (
            <button key={t.id} onClick={() => setTab(t.id)}
              className={cx("flex shrink-0 items-center gap-2 rounded-xl px-3.5 py-2 text-sm transition-colors",
                tab === t.id ? "bg-electric/[0.16] text-ink ring-1 ring-electric/25" : "text-muted hover:text-ink")}>
              {t.icon} {t.label}
            </button>
          ))}
        </div>

        {tab === "credentials" && (
          <Panel>
            {SECRETS.map((s) => <SecretRow key={s.name} s={s} configured={!!secrets[s.name]} onChange={async () => { await load(); await refreshStatus(true); }} />)}
          </Panel>
        )}

        {tab === "model" && (
          <div className="space-y-6">
          <AboutYou cfg={cfg} save={save} />
          <AIEngine />
          <Panel title="Claude · nube" icon={<Sparkles size={14} />}>
            <Row label="Modelo de Claude" hint="Opus 5.5: el más capaz. Haiku 5.5: casi gratis (~40 veces más barato).">
              <Select value={cfg.llm.model} onChange={(m) => save({ llm: { model: m } })} options={[
                { value: "claude-opus-5-5", label: "Claude Opus 5.5 (recomendado)" },
                { value: "claude-fable-5-1", label: "Claude Fable 5.1 (máxima capacidad, más caro)" },
                { value: "claude-sonnet-5-5", label: "Claude Sonnet 5.5 (rápido y económico)" },
                { value: "claude-haiku-5-5", label: "Claude Haiku 5.5 (muy rápido, tareas simples)" },
              ]} />
            </Row>
            <Row label="Esfuerzo en conversación" hint="Más esfuerzo = razonamiento más profundo, más latencia y coste.">
              <Select value={cfg.llm.effort} onChange={(e) => save({ llm: { effort: e } })}
                options={["low", "medium", "high", "xhigh", "max"].map((v) => ({ value: v, label: { low: "Bajo (rápido)", medium: "Medio (equilibrado)", high: "Alto", xhigh: "Muy alto", max: "Máximo" }[v]! }))} />
            </Row>
            <Row label="Esfuerzo en segundo plano" hint="Para investigaciones e informes autónomos.">
              <Select value={cfg.llm.background_effort} onChange={(e) => save({ llm: { background_effort: e } })}
                options={["low", "medium", "high", "xhigh", "max"].map((v) => ({ value: v, label: v }))} />
            </Row>
            <Row label="Búsqueda web en tiempo real"><Toggle checked={cfg.llm.web_search} onChange={(v) => save({ llm: { web_search: v } })} /></Row>
            <Row label="Lectura de páginas web"><Toggle checked={cfg.llm.web_fetch} onChange={(v) => save({ llm: { web_fetch: v } })} /></Row>
            <Row label="Respaldo ante rechazos" hint="Si un filtro de seguridad rechaza por error una petición legítima, se reintenta en el modelo recomendado.">
              <Toggle checked={cfg.llm.server_fallbacks} onChange={(v) => save({ llm: { server_fallbacks: v } })} />
            </Row>
            <Row label="Notas de progreso" hint="Muestra qué está haciendo JARVIS entre herramientas.">
              <Toggle checked={cfg.llm.progress_updates} onChange={(v) => save({ llm: { progress_updates: v } })} />
            </Row>
          </Panel>
          </div>
        )}

        {tab === "voice" && (
          <Panel>
            <Row label="Micrófono" hint="El que JARVIS usará para escucharte (voz y «Hey JARVIS»). Se recuerda aunque cambies el predeterminado de Windows.">
              <MicPicker />
            </Row>
            <Row label="Escucha permanente" hint="«Hey JARVIS» 24/7 desde el servicio: funciona con la ventana minimizada o cerrada. Tras cada respuesta sigue escuchándote; di «gracias, eso es todo» para terminar.">
              <AlwaysOn cfg={cfg} save={save} />
            </Row>
            <div className="border-b border-line px-4 py-4">
              <div className="mb-3">
                <div className="text-[13.5px] text-ink">Voz de JARVIS</div>
                <div className="mt-0.5 text-xs text-muted">Elige la voz que más te guste. Se aplica al PC, a «Hey JARVIS» y a las notas de voz de Telegram.</div>
              </div>
              <VoiceGallery cfg={cfg} secrets={secrets} onSaved={() => void load()} />
            </div>
            {cfg.voice.tts_engine === "elevenlabs" && (
              <Row label="Modelo de ElevenLabs" hint="Flash v2.5: mínima latencia. Multilingual v2: máxima calidad. v3: la más expresiva.">
                <Select value={cfg.voice.elevenlabs_model} onChange={(v) => save({ voice: { elevenlabs_model: v } })} options={[
                  { value: "eleven_flash_v2_5", label: "Flash v2.5 (baja latencia)" },
                  { value: "eleven_multilingual_v2", label: "Multilingual v2 (máxima calidad)" },
                  { value: "eleven_v3", label: "Eleven v3 (más expresiva)" },
                ]} />
              </Row>
            )}
            {cfg.voice.tts_engine === "azure" && (
              <>
                <Row label="Región de Azure"><Input defaultValue={cfg.voice.azure_region} onBlur={(e) => save({ voice: { azure_region: e.target.value } })} /></Row>
                <Row label="Voz de Azure"><Input defaultValue={cfg.voice.azure_voice} onBlur={(e) => save({ voice: { azure_voice: e.target.value } })} /></Row>
              </>
            )}
            <Row label="Hablar respuestas a preguntas por voz"><Toggle checked={cfg.voice.auto_speak} onChange={(v) => save({ voice: { auto_speak: v } })} /></Row>
            <Row label="Reconocimiento de voz" hint="Whisper local: el audio no sale de tu PC.">
              <div className="flex gap-2">
                <Select value={cfg.voice.stt_model} onChange={(v) => save({ voice: { stt_model: v } })} options={[
                  { value: "large-v3-turbo", label: "large-v3-turbo (recomendado con GPU)" },
                  { value: "large-v3", label: "large-v3 (máxima precisión)" },
                  { value: "medium", label: "medium" }, { value: "small", label: "small (CPU)" },
                ]} />
                <Select value={cfg.voice.stt_device} onChange={(v) => save({ voice: { stt_device: v } })}
                  options={[{ value: "auto", label: "Auto" }, { value: "cuda", label: "GPU" }, { value: "cpu", label: "CPU" }]} className="!w-28" />
              </div>
            </Row>
            <Row label="Sensibilidad de «Hey JARVIS»" hint="Umbral de detección (0.3 más sensible – 0.8 más estricto).">
              <Input type="number" step="0.05" min="0.2" max="0.95" defaultValue={cfg.voice.wake_word_threshold}
                onBlur={(e) => save({ voice: { wake_word_threshold: parseFloat(e.target.value) } })} className="!w-28" />
            </Row>
          </Panel>
        )}

        {tab === "telegram" && (
          <div className="space-y-4">
            <Panel>
              <Row label="Estado del bot" hint="Conexión saliente segura (long polling): no se abre ningún puerto en tu PC.">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone={tg?.status === "conectado" ? "ok" : "warn"}>{tg?.status ?? "—"}</Badge>
                  {tg?.bot && <a href={`https://t.me/${tg.bot}`} target="_blank" rel="noreferrer" className="text-sm text-lavender underline">@{tg.bot}</a>}
                  {tg?.error && <span className="text-xs text-danger">{tg.error}</span>}
                  <Button variant="subtle" onClick={async () => { await post("/api/telegram/restart"); await refreshStatus(); }}><RefreshCw size={14} /> Reiniciar</Button>
                </div>
              </Row>
              <Row label="Emparejar mi móvil" hint="Genera un código de un solo uso (10 min). Solo quien lo envíe quedará autorizado.">
                {pairing ? (
                  <div className="rounded-xl border border-electric/30 bg-electric/[0.08] p-3 text-sm">
                    <div>Abre <a className="text-lavender underline" href={`https://t.me/${pairing.bot}`} target="_blank" rel="noreferrer">@{pairing.bot}</a> en Telegram y envía:</div>
                    <div className="mt-2 font-mono text-xl tracking-widest text-ink">/pair {pairing.code}</div>
                  </div>
                ) : (
                  <Button variant="primary" disabled={tg?.status !== "conectado"} onClick={async () => {
                    try { setPairing(await post("/api/telegram/pairing")); } catch (e: any) { toast({ title: "Telegram", message: e.message, tone: "danger" }); }
                  }}>Generar código</Button>
                )}
              </Row>
              <Row label="Usuarios autorizados">
                <div className="flex flex-wrap gap-2">
                  {(tg?.authorized_users ?? []).length === 0 && <span className="text-xs text-faint">Ninguno todavía.</span>}
                  {(tg?.authorized_users ?? []).map((u: number) => (
                    <span key={u} className="flex items-center gap-1.5 rounded-lg border border-line-strong py-1 pr-1 pl-2.5 font-mono text-xs">
                      {u}
                      <button aria-label="Revocar" className="rounded p-0.5 text-faint hover:text-danger"
                        onClick={async () => { if (confirm(`¿Revocar el acceso de ${u}?`)) { await del(`/api/telegram/users/${u}`); await refreshStatus(); } }}><X size={12} /></button>
                    </span>
                  ))}
                </div>
              </Row>
              <Row label="PIN de seguridad" hint="Se pide en Telegram para aprobar acciones peligrosas y para reanudar tras una parada de emergencia.">
                <div className="flex items-center gap-2">
                  {tg?.has_pin ? <Badge tone="ok">Configurado</Badge> : <Badge tone="warn">Sin PIN</Badge>}
                  <Input type="password" inputMode="numeric" value={pin} onChange={(e) => setPin(e.target.value.replace(/\D/g, ""))} placeholder="4-12 dígitos" className="!w-40" />
                  <Button variant="ghost" disabled={pin.length < 4} onClick={async () => {
                    try { await post("/api/telegram/pin", { pin }); setPin(""); toast({ title: "PIN guardado", message: "Guardado como hash seguro.", tone: "ok" }); await refreshStatus(); }
                    catch (e: any) { toast({ title: "PIN", message: e.message, tone: "danger" }); }
                  }}>Guardar</Button>
                </div>
              </Row>
              <Row label="Exigir PIN para acciones peligrosas"><Toggle checked={cfg.telegram.require_pin_for_sensitive} onChange={(v) => save({ telegram: { require_pin_for_sensitive: v } })} /></Row>
              <Row label="Respuestas por voz en Telegram" hint="Además del texto, envía una nota de voz."><Toggle checked={cfg.telegram.voice_replies} onChange={(v) => save({ telegram: { voice_replies: v } })} /></Row>
              <Row label="Límite de mensajes por minuto">
                <Input type="number" min={1} max={60} defaultValue={cfg.telegram.rate_limit_per_minute} className="!w-28"
                  onBlur={(e) => save({ telegram: { rate_limit_per_minute: parseInt(e.target.value) || 12 } })} />
              </Row>
              <Row label="Bot activado"><Toggle checked={cfg.telegram.enabled} onChange={async (v) => { await save({ telegram: { enabled: v } }); await post("/api/telegram/restart"); await refreshStatus(); }} /></Row>
            </Panel>
            {!secrets.telegram_bot_token && (
              <p className="flex items-center gap-2 text-sm text-warn"><CircleAlert size={15} /> Primero guarda el token del bot en Credenciales.</p>
            )}
          </div>
        )}

        {tab === "security" && (
          <Panel>
            <Row label="Acceso total al PC" hint="Todos los discos y programas, y sin confirmaciones para lo que pidas en el PC o por voz. Siempre bloqueado: desactivar antivirus/firewall o hacerse administrador. Por Telegram, lo peligroso sigue pidiendo PIN.">
              <div className="flex items-center gap-3">
                <Toggle checked={!!cfg.security.full_access} onChange={(v) => save({ security: { full_access: v } })} label="Acceso total" />
                <span className={cfg.security.full_access ? "text-sm text-warn" : "text-sm text-muted"}>
                  {cfg.security.full_access ? "Activado: JARVIS ejecuta sin preguntar" : "Desactivado"}
                </span>
              </div>
            </Row>
            <Row label="Pedir confirmación desde" hint="Las acciones peligrosas siempre piden confirmación, sea cual sea este ajuste.">
              <Select value={cfg.security.confirm_level} onChange={(v) => save({ security: { confirm_level: v } })} options={[
                { value: "moderate", label: "Moderado (máxima precaución)" },
                { value: "sensitive", label: "Sensible (recomendado)" },
                { value: "dangerous", label: "Solo peligroso" },
              ]} />
            </Row>
            <Row label="Carpetas autorizadas" hint="JARVIS solo puede leer y escribir dentro de estas carpetas.">
              <div className="space-y-1.5">
                {cfg.security.allowed_roots.map((r: string) => (
                  <div key={r} className="flex items-center gap-2 rounded-lg border border-line bg-black/20 px-2.5 py-1.5 font-mono text-xs">
                    <span className="min-w-0 flex-1 truncate">{r}</span>
                    <button aria-label="Quitar" className="text-faint hover:text-danger"
                      onClick={() => save({ security: { allowed_roots: cfg.security.allowed_roots.filter((x: string) => x !== r) } })}><X size={13} /></button>
                  </div>
                ))}
                <div className="flex gap-2">
                  <Input value={newRoot} onChange={(e) => setNewRoot(e.target.value)} placeholder="C:\Users\…\Proyectos" />
                  <Button variant="ghost" disabled={!newRoot.trim()} onClick={() => { void save({ security: { allowed_roots: [...cfg.security.allowed_roots, newRoot.trim()] } }); setNewRoot(""); }}>
                    <FolderPlus size={15} />
                  </Button>
                </div>
              </div>
            </Row>
            <Row label="Comandos de PowerShell" hint="Siempre con confirmación, sin privilegios de administrador y con lista de bloqueo.">
              <Toggle checked={cfg.security.shell_enabled} onChange={(v) => save({ security: { shell_enabled: v } })} />
            </Row>
            <Row label="Aplicaciones que puede abrir">
              <Select value={cfg.security.app_mode} onChange={(v) => save({ security: { app_mode: v } })} options={[
                { value: "start_menu", label: "Las del menú Inicio + lista blanca" }, { value: "allowlist", label: "Solo la lista blanca" },
              ]} />
            </Row>
            <Row label="Tiempo para confirmar" hint="Segundos antes de denegar automáticamente.">
              <Input type="number" defaultValue={cfg.security.confirmation_timeout_s} className="!w-28"
                onBlur={(e) => save({ security: { confirmation_timeout_s: parseInt(e.target.value) || 300 } })} />
            </Row>
          </Panel>
        )}

        {tab === "system" && (
          <div className="space-y-4">
            <Panel title="JARVIS en el escritorio" icon={<Sparkles size={14} />}>
              <Row label="Esfera sobre tu fondo de pantalla" hint="Una esfera animada transparente encima de tu fondo (también de Wallpaper Engine) y detrás de tus ventanas. No bloquea clics y reacciona cuando escucha, piensa o habla.">
                <div className="flex items-center gap-3">
                  <Toggle checked={!!cfg.desktop?.overlay} onChange={(v) => save({ desktop: { overlay: v } })} label="Esfera en el escritorio" />
                  <span className={cfg.desktop?.overlay ? "text-sm text-lavender" : "text-sm text-muted"}>{cfg.desktop?.overlay ? "Visible en tu escritorio" : "Desactivada"}</span>
                </div>
              </Row>
              <Row label="Posición">
                <Select value={cfg.desktop?.position ?? "bottom-right"} onChange={(v) => save({ desktop: { position: v } })} options={[
                  { value: "bottom-right", label: "Abajo a la derecha" }, { value: "top-right", label: "Arriba a la derecha" },
                  { value: "center", label: "En el centro" }, { value: "bottom-left", label: "Abajo a la izquierda" },
                  { value: "top-left", label: "Arriba a la izquierda" },
                ]} />
              </Row>
              <Row label="Tamaño">
                <Select value={String(cfg.desktop?.size ?? 300)} onChange={(v) => save({ desktop: { size: parseInt(v) } })} options={[
                  { value: "200", label: "Pequeña" }, { value: "300", label: "Mediana" }, { value: "420", label: "Grande" }, { value: "600", label: "Enorme" },
                ]} />
              </Row>
              <Row label="Capa" hint="«Fondo» la deja detrás de tus ventanas, como parte del escritorio; «Siempre visible» la pone por encima de todo.">
                <Select value={cfg.desktop?.layer ?? "desktop"} onChange={(v) => save({ desktop: { layer: v } })} options={[
                  { value: "desktop", label: "Fondo (detrás de las ventanas)" }, { value: "top", label: "Siempre visible (encima de todo)" },
                ]} />
              </Row>
              <Row label="Mostrar estado bajo la esfera"><Toggle checked={cfg.desktop?.show_text ?? true} onChange={(v) => save({ desktop: { show_text: v } })} /></Row>
            </Panel>
            <Panel>
              <Row label="Iniciar con Windows" hint="Crea un acceso directo visible en la carpeta Inicio de tu usuario. Puedes quitarlo cuando quieras.">
                <Toggle checked={autostart} onChange={async (v) => setAutostart((await post("/api/autostart", { enabled: v })).enabled)} />
              </Row>
              <Row label="Abrir la interfaz al arrancar"><Toggle checked={cfg.server.open_browser_on_start} onChange={(v) => save({ server: { open_browser_on_start: v } })} /></Row>
              <Row label="Ventana de aplicación" hint="Abre JARVIS en una ventana propia (Edge en modo app) en lugar de una pestaña."><Toggle checked={cfg.server.app_window} onChange={(v) => save({ server: { app_window: v } })} /></Row>
            </Panel>
            <Panel title="Diagnóstico" icon={<Stethoscope size={14} />}
              actions={<Button variant="subtle" onClick={async () => { setChecks(null); setChecks(await get("/api/doctor")); }}><RefreshCw size={14} /> Repetir</Button>}>
              {!checks ? <div className="grid place-items-center py-8"><Loader2 className="animate-spin text-lavender" /></div> : (
                <ul className="divide-y divide-line">
                  {checks.map((c) => (
                    <li key={c.name} className="flex items-start gap-3 px-4 py-2.5 text-sm">
                      <span className={cx("mt-1.5 size-2 shrink-0 rounded-full", { ok: "bg-ok", warn: "bg-warn", error: "bg-danger", info: "bg-faint" }[c.level as string])} />
                      <span className="text-ink">{c.name}</span>
                      <span className="ml-auto max-w-[55%] truncate text-right text-xs text-muted" title={c.detail}>{c.detail}</span>
                    </li>
                  ))}
                </ul>
              )}
            </Panel>
          </div>
        )}
      </div>
    </div>
  );
}
