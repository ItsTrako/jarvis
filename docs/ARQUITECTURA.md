# Arquitectura de J.A.R.V.I.S.

## 1. Entorno detectado (fase 1)

| Componente | Valor |
|---|---|
| Sistema | Windows 11 Pro 23H2 (10.0.22631), 64 bits |
| CPU | AMD Ryzen 7 5700X3D — 8 núcleos / 16 hilos |
| RAM | 32 GB |
| GPU | NVIDIA GeForce RTX 3060 — 12 GB VRAM (driver 621.14, CUDA 12) |
| Disco | C: 1,86 TB (130 GB libres) |
| Audio | Realtek, Logitech PRO X Wireless (micrófono), dispositivos virtuales |
| Herramientas | Python 3.12.10, Node 24, Git, ffmpeg, winget, Google Chrome (Edge no instalado) |

La RTX 3060 permite ejecutar **Whisper large-v3-turbo en local** con aceleración CUDA (7 s de audio en 0,38 s).

## 2. Vista general

```
┌──────────────────────────── Interfaces ─────────────────────────────┐
│  Interfaz web (React)      Voz (navegador)       Telegram (móvil)   │
│  REST + WebSocket          Whisper / TTS / wake  long polling HTTPS │
└──────────────┬─────────────────────┬─────────────────────┬──────────┘
               │                     │                     │
        ┌──────▼─────────────────────▼─────────────────────▼──────┐
        │   server.py (FastAPI, 127.0.0.1)   ·   events.py (bus)   │
        └──────────────────────────┬───────────────────────────────┘
                                   │  ExecContext (origen, chat, trabajo)
        ┌──────────────────────────▼───────────────────────────────┐
        │  agent/core.py — bucle agéntico                           │
        │   contexto (hora, memoria relevante, tareas) → Claude →   │
        │   herramientas → resultados → … → respuesta verificada    │
        ├──────────────┬──────────────┬──────────────┬─────────────┤
        │ llm/         │ tools/       │ security.py  │ store.py/db │
        │ Claude (SDK) │ 52 + plugins │ permisos,    │ memoria,    │
        │ + web search │ registro,    │ aprobaciones,│ tareas,     │
        │ + web fetch  │ validación   │ kill switch  │ trabajos…   │
        └──────────────┴──────────────┴──────────────┴─────────────┘
        agent/jobs.py: trabajos en segundo plano + programador de rutinas
```

Un único proceso Python asíncrono aloja todo: API, bot de Telegram, programador y agente. Así las
interfaces comparten literalmente el mismo estado (no hay sincronización entre servicios).

## 3. Núcleo de IA

- **Modelo**: Claude Opus 5.5 (`claude-opus-5-5`) vía SDK oficial `anthropic` 2.6, con streaming.
  Configurable (Fable 5.1, Sonnet 5.5, Haiku 5.5) desde la interfaz.
- **Pensamiento adaptativo** siempre activo; el *esfuerzo* (`low`…`max`) controla profundidad, latencia y
  coste. Conversación: `medium`. Trabajos en segundo plano: `high`.
- **Notas de progreso** (`thinking.display: "updates"`): el modelo explica entre herramientas qué ha
  encontrado y qué hará; la interfaz y Telegram las muestran en directo.
- **Herramientas del servidor**: `web_search` y `web_fetch` (búsqueda y lectura web reales, con filtrado
  dinámico). No requieren claves adicionales.
- **Respaldo ante rechazos** (`fallbacks: "default"`): si un clasificador de seguridad declina por error
  una petición legítima, la API la reintenta en el modelo recomendado.
- **Historial solo-anexado**: el prompt de sistema es estable (sin fecha) y el contexto variable va en cada
  mensaje del usuario dentro de `<contexto>`. Esto maximiza la caché de prompts y mantiene válido el
  pensamiento preservado; además se envía `prefix_mismatch_behavior: drop_block` como red de seguridad.
- **Modo compatible automático**: si la cuenta no admite alguna función beta, el proveedor la desactiva y
  reintenta sin ella (sin intervención del usuario).
- **Compactación**: al superar ~180 k tokens de contexto, la conversación se resume y continúa en un
  segmento nuevo (compactación simple, compatible con el pensamiento preservado).
- **Recuperación ante errores**: los fallos de herramientas vuelven al modelo como `tool_result` con
  `is_error`, para que replantee; cancelaciones y errores cierran siempre los `tool_use` pendientes, de
  modo que el historial nunca queda corrupto.
- **Planificador**: herramienta `update_plan`. El modelo publica el plan y lo va actualizando; la interfaz
  muestra la barra de progreso y Telegram un mensaje que se edita en vivo. El prompt exige **verificar**
  (p. ej. `file_info`) antes de anunciar un resultado.
- **Extensible a otros proveedores**: `llm/base.py` define `LLMProvider`; basta implementar `stream_turn`.

## 4. Herramientas

Cada herramienta declara nombre, descripción, esquema JSON de parámetros, **nivel de riesgo**
(seguro · moderado · sensible · peligroso), categoría, tiempo límite y, opcionalmente, una función que
eleva el riesgo según los parámetros (p. ej. sobrescribir un archivo existente). El registro valida tipos,
obligatorios, enumerados y parámetros desconocidos antes de ejecutar nada.

| Categoría | Herramientas |
|---|---|
| Archivos | listar, leer, escribir, crear carpeta, mover, copiar, Papelera, buscar, info, organizar |
| Documentos | leer PDF/Word/Excel/PowerPoint/CSV; crear Word, PDF, Markdown, Excel |
| Aplicaciones | listar (504 del menú Inicio), abrir, abrir archivo/URL, cerrar |
| Sistema | estado completo, procesos, terminar proceso, ventanas |
| Escritorio | captura de pantalla (visión), secuencias teclado/ratón, portapapeles |
| Web | búsqueda y lectura (servidor), navegador controlado con Playwright (Chrome/Edge, perfil aislado) |
| Automatización | PowerShell controlado, scripts revisados, rutinas programadas |
| Planificación | plan, trabajos en segundo plano (lanzar, consultar, cancelar) |
| Memoria / tareas | recordar, buscar, corregir, olvidar; crear, listar, actualizar, borrar tareas |
| Notificaciones | escritorio (toast) y Telegram, envío de archivos |
| Integraciones | plugins en `plugins/` (ejemplo: tiempo con Open-Meteo) |

Se priorizan APIs nativas (Win32, `os.startfile`, `Get-StartApps`, psutil, NVML) frente a la
automatización por ratón/teclado, que queda como último recurso.

## 5. Memoria

- **Temporal**: el historial de la conversación (persistido; se compacta cuando crece).
- **Persistente**: tabla `memories` con tipo (preferencia, personal, proyecto, dato, nota, configuración),
  etiquetas e importancia 1–5. En cada turno se inyectan los recuerdos esenciales y los relevantes al
  mensaje (búsqueda por palabras clave sin acentos). Consultable, editable y borrable desde la interfaz.
- **Tareas, trabajos y rutinas**: tablas propias, compartidas por todas las interfaces.

## 6. Decisiones técnicas

| Necesidad | Elección | Alternativas consideradas | Motivo |
|---|---|---|---|
| Backend | Python 3.12 + FastAPI asíncrono | Node/Express, .NET | Mejor ecosistema para voz (Whisper), automatización Windows (pywin32, pyautogui), documentos y Telegram |
| Servidor | Uvicorn en 127.0.0.1 | Exponer puerto, túnel | Nunca se expone el PC; Telegram usa conexión saliente |
| IA | SDK oficial `anthropic`, bucle propio | Tool Runner del SDK, Agent SDK, Managed Agents | Bucle propio = aprobaciones bloqueantes, auditoría, cancelación y eventos en vivo por herramienta; ejecución local en tu PC |
| BD | SQLAlchemy 2 async + SQLite (WAL) | SQLite directo, PostgreSQL | Cero instalación; cambiar `database_url` a `postgresql+asyncpg://` basta para migrar |
| Credenciales | `keyring` → Administrador de credenciales de Windows (DPAPI) | `.env`, YAML | Cifrado por usuario de Windows; nada sensible en disco del proyecto |
| Telegram | python-telegram-bot 22.8, long polling | Webhooks | Webhooks exigirían abrir un puerto o un túnel público |
| STT | faster-whisper large-v3-turbo (CUDA) | Whisper API, Deepgram, Azure STT | Local (privacidad), gratis, muy preciso en español, ~0,4 s con la RTX 3060 |
| TTS | edge (Microsoft Neural) por defecto; ElevenLabs y Azure opcionales | Google Cloud TTS, Piper | Ver [VOZ.md](VOZ.md) |
| Palabra de activación | openWakeWord «hey_jarvis» (ONNX, CPU) | Porcupine (requiere clave), Whisper continuo | Local, gratuito, modelo preentrenado con el propio nombre |
| Navegador | Playwright con Chrome/Edge instalado | Selenium, Chromium descargado | Sin descargas extra, perfil aislado, API moderna |
| Frontend | React 18 + TS + Vite 6 + Tailwind 4 + Framer Motion + zustand | Next.js, Svelte | SPA local sin SSR; ecosistema y animaciones de primer nivel |
| Núcleo visual | Canvas 2D propio | Three.js/WebGL | Ligero, sin dependencias, reacciona al audio a 60 fps |
| Ventana | Chrome/Edge en modo `--app` | Electron, Tauri | Experiencia de app nativa sin empaquetar un runtime de 150 MB |
| MCP | No incluido en esta versión | Conector MCP de la API | Solo admite servidores MCP remotos; los plugins locales cubren las integraciones con menos superficie de ataque. Ver ESTADO.md |

## 7. Flujo de una petición

1. La interfaz envía el texto (o el audio transcrito) a `/api/chat`; Telegram llama directamente al agente.
2. El agente añade el bloque `<contexto>` (hora, interfaz, recuerdos, tareas, trabajos) y guarda el mensaje.
3. Claude responde en streaming; el texto y las notas de progreso se emiten por el bus de eventos.
4. Para cada `tool_use`: validación → cálculo de riesgo → confirmación si procede (UI y/o Telegram, con
   PIN si es peligroso) → ejecución con tiempo límite → auditoría → `tool_result`.
5. Se repite hasta la respuesta final; los archivos generados se adjuntan (UI y Telegram).
6. Con voz, la respuesta se sintetiza frase a frase mientras se genera.
