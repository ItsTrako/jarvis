import { createOrb } from "./assets/orb.js";

window.jarvisReady = true;
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

/* Textos por idioma: la página inglesa (en/) tiene <html lang="en"> */
const EN = document.documentElement.lang.startsWith("en");
const T = EN ? {
  states: { idle: "Idle", listening: "Listening", thinking: "Thinking", speaking: "Speaking" },
  script: [
    ["Hey JARVIS, what's on my list today?", "Three things. Most urgent: renew the domain."],
    ["Open Spotify and play something to focus.", "Done. Calm music playing on Spotify."],
    ["How's the GPU doing?", "21 % load and 58 °C. All good."],
    ["Write me a report on Notion alternatives.", "On it. I'll let you know when it's ready."],
  ],
  notes: { local: "gemma4:12b · qwen3:8b · $0 a month", claude: "claude-opus-5-5 · adaptive reasoning" },
  titles: { inicio: "Home", "motor-ia": "AI engine", voces: "Voices", sistema: "System", herramientas: "Tools" },
  copy: "Copy", copied: "Copied", kill: "Emergency stop", killed: "Everything stopped",
} : {
  states: { idle: "En espera", listening: "Escuchando", thinking: "Pensando", speaking: "Hablando" },
  script: [
    ["Hey JARVIS, ¿qué tengo pendiente hoy?", "Tres cosas. La más urgente: renovar el dominio."],
    ["Abre Spotify y pon algo para concentrarme.", "Hecho. Música tranquila sonando en Spotify."],
    ["¿Cómo va la GPU?", "Al 21 % y a 58 °C. Todo en orden."],
    ["Prepárame un informe de alternativas a Notion.", "Me pongo con ello. Te aviso al terminar."],
  ],
  notes: { local: "gemma4:12b · qwen3:8b · 0 € al mes", claude: "claude-opus-5-5 · razonamiento adaptativo" },
  titles: { inicio: "Inicio", "motor-ia": "Motor de IA", voces: "Voces", sistema: "Sistema", herramientas: "Herramientas" },
  copy: "Copiar", copied: "Copiado", kill: "Parada de emergencia", killed: "Todo detenido",
};

/* Aparición al hacer scroll */
const io = new IntersectionObserver((entries) => {
  for (const e of entries) if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); }
}, { rootMargin: "0px 0px -8% 0px", threshold: 0.12 });
$$(".reveal").forEach((el) => io.observe(el));

/* Barra de navegación */
const nav = $("#nav");
const onScroll = () => nav.classList.toggle("scrolled", scrollY > 24);
addEventListener("scroll", onScroll, { passive: true });
onScroll();

/* Núcleo + diálogo de demostración: escucha, piensa y habla en bucle */
const STATES = {
  idle: [T.states.idle, "#6ee7b7"],
  listening: [T.states.listening, "#a855f7"],
  thinking: [T.states.thinking, "#c4b5fd"],
  speaking: [T.states.speaking, "#a855f7"],
};
const SCRIPT = T.script;

let orb = null;
// El núcleo anima en su sitio (sin desplazamiento), así que se mantiene también con movimiento reducido
try { orb = createOrb($("#orb"), { reducedMotion: false }); } catch { orb = null; }
if (!orb) { $("#orb").hidden = true; $(".orb-fallback").hidden = false; }

let state = "idle", t0 = performance.now();
function setState(s) {
  state = s;
  orb?.setState(s);
  $("#stateLabel").textContent = STATES[s][0];
  $("#stateDot").style.background = STATES[s][1];
}
// Nivel de audio simulado: voz con sílabas al hablar, más suave al escuchar
(function level(now) {
  const t = (now - t0) / 1000;
  let v = 0;
  if (state === "speaking") v = Math.max(0, 0.35 + 0.35 * Math.sin(t * 13) * Math.sin(t * 3.1) + 0.2 * Math.sin(t * 29));
  else if (state === "listening") v = Math.max(0, 0.18 + 0.16 * Math.sin(t * 9) * Math.sin(t * 2.3));
  orb?.setLevel(v);
  requestAnimationFrame(level);
})(performance.now());

let skip = null;
const pause = (ms) => new Promise((r) => { const id = setTimeout(r, ms); skip = () => { clearTimeout(id); r(); }; });
async function type(el, text, cps) {
  el.textContent = "";
  for (const ch of text) { el.textContent += ch; await wait(1000 / cps); }
}
async function demo() {
  const you = $("#bYou"), jar = $("#bJarvis");
  for (let i = 0; ; i = (i + 1) % SCRIPT.length) {
    const [q, a] = SCRIPT[i];
    setState("idle"); await pause(1400);
    setState("listening"); you.classList.add("show"); await type($("#tYou"), q, 26); await pause(500);
    setState("thinking"); await pause(1100);
    setState("speaking"); jar.classList.add("show"); await type($("#tJarvis"), a, 22); await pause(1600);
    you.classList.remove("show"); jar.classList.remove("show"); await pause(500);
    $("#tYou").textContent = ""; $("#tJarvis").textContent = "";
  }
}
demo();
$("#orbWrap").addEventListener("click", () => skip?.());

/* Selector de motor de IA */
const engines = $(".engines");
const NOTES = T.notes;
$$(".engine", engines).forEach((b) => b.addEventListener("click", () => {
  engines.dataset.on = b.dataset.engine;
  $$(".engine", engines).forEach((x) => x.classList.toggle("on", x === b));
  $("#engineNote").textContent = NOTES[b.dataset.engine];
}));

/* Plan que se va completando cuando está a la vista */
const plan = $("#plan");
let planRunning = false;
async function runPlan() {
  if (planRunning) return; planRunning = true;
  const items = $$("li", plan);
  for (;;) {
    items.forEach((li) => (li.className = ""));
    await wait(700);
    for (const li of items) { li.className = "doing"; await wait(1100); li.className = "done"; await wait(150); }
    await wait(3200);
  }
}
new IntersectionObserver(([e], o) => { if (e.isIntersecting) { runPlan(); o.disconnect(); } }, { threshold: 0.5 }).observe(plan);

/* Onda de voz con alturas variadas */
const wave = $(".wave");
wave.replaceChildren(...Array.from({ length: 56 }, (_, i) => {
  const s = document.createElement("span");
  // Envolvente de frase: más energía en el centro, variación por barra
  const env = 0.45 + 0.55 * Math.sin((i / 55) * Math.PI);
  s.style.setProperty("--h", (env * (0.45 + Math.abs(Math.sin(i * 1.7)) * 0.55)).toFixed(2));
  s.style.animationDelay = `${(-((i * 0.37) % 1.6)).toFixed(2)}s`;
  s.style.animationDuration = `${(1.1 + (i % 5) * 0.18).toFixed(2)}s`;
  return s;
}));

/* Foco de luz que sigue al puntero en las tarjetas */
$$(".tile").forEach((t) => t.addEventListener("pointermove", (e) => {
  const r = t.getBoundingClientRect();
  t.style.setProperty("--mx", `${e.clientX - r.left}px`);
  t.style.setProperty("--my", `${e.clientY - r.top}px`);
}));

/* Galería de pantallas */
const TITLES = T.titles;
const tabs = $$(".tabs [role=tab]");
function show(name) {
  tabs.forEach((b) => b.setAttribute("aria-selected", String(b.dataset.shot === name)));
  $$(".shots img").forEach((img) => img.classList.toggle("on", img.dataset.shot === name));
  $("#shotTitle").textContent = TITLES[name];
}
tabs.forEach((b, i) => {
  b.addEventListener("click", () => show(b.dataset.shot));
  b.addEventListener("keydown", (e) => {
    const d = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
    if (!d) return;
    const n = tabs[(i + d + tabs.length) % tabs.length]; n.focus(); show(n.dataset.shot);
  });
});

/* Copiar comandos */
$$(".copy").forEach((b) => b.addEventListener("click", async () => {
  const text = $("#" + b.dataset.copy).innerText.split("\n").filter((l) => l && !l.startsWith("#")).join("\n");
  try { await navigator.clipboard.writeText(text); } catch { return; }
  b.classList.add("ok"); $("span", b).textContent = T.copied; $("i", b).className = "ph ph-check";
  setTimeout(() => { b.classList.remove("ok"); $("span", b).textContent = T.copy; $("i", b).className = "ph ph-copy"; }, 1800);
}));

/* Parada de emergencia (demostración) */
const kill = $("#kill");
kill.addEventListener("click", () => {
  kill.classList.add("fired"); $("span", kill).textContent = T.killed;
  setTimeout(() => { kill.classList.remove("fired"); $("span", kill).textContent = T.kill; }, 1800);
});
