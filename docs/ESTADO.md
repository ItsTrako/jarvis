# Registro de estado — J.A.R.V.I.S. 1.0

Fecha: 8 de noviembre de 2026. Leyenda: ✅ implementado y verificado · 🟡 implementado, pendiente de verificar
con tus credenciales o hardware · ⏳ pendiente / mejora futura.

## Fases

| Fase | Estado |
|---|---|
| 1. Inspección del entorno | ✅ Ver [ARQUITECTURA.md](ARQUITECTURA.md) §1 |
| 2. Arquitectura | ✅ |
| 3. Core (Claude, herramientas, memoria, planificador) | ✅ (con proveedor simulado) · 🟡 con Claude real |
| 4. Interfaz Twilight Purple | ✅ escritorio y móvil |
| 5. Voz | ✅ STT/TTS/palabra clave en backend · 🟡 micrófono real en la ventana |
| 6. Telegram | 🟡 requiere tu token |
| 7. Integración | ✅ |
| 8. Pruebas | ✅ 26 pruebas automatizadas + pruebas manuales listadas abajo |
| 9. Pulido | ✅ |
| 10. Entrega | ✅ instalador, lanzadores, documentación |

## Verificado en este PC

- **26/26 pruebas automatizadas** (`backend/tests`): confinamiento de rutas y bloqueo de rutas sensibles; lista
  de bloqueo de PowerShell (antivirus, firewall, registro HKLM, RunAs, `iwr|iex`, cuentas, arranque);
  validación de parámetros; herramientas seguras sin confirmación; peligrosas denegadas y aprobadas (y PIN
  exigido si vienen de Telegram); escalado de riesgo al sobrescribir; creación y relectura de Word/PDF/Markdown;
  memoria (búsqueda y contexto) y tareas; **bucle agéntico multipaso** (plan → documento → verificación →
  respuesta) con historial correcto; recuperación tras error de herramienta; cancelación a mitad de tarea
  dejando el historial válido; parada de emergencia; trabajo en segundo plano con notificación; cálculo de
  rutinas diarias/semanales/intervalo; formato y troceado de Telegram; API con token, `Host` y `Origin`;
  flujo de chat completo por HTTP + eventos WebSocket en vivo; validación de configuración; endpoint de
  emergencia; los secretos nunca se devuelven.
- **Petición real a la API de Claude** bien formada con el SDK (betas, pensamiento adaptativo con notas de
  progreso, fallbacks, 54 herramientas): con una clave falsa la API responde 401, como se espera.
- **Whisper large-v3-turbo en CUDA**: transcripción correcta en español; 0,38 s para 7,3 s de audio.
- **TTS Microsoft Neural** (`es-ES-AlvaroNeural`): síntesis correcta.
- **openWakeWord «hey_jarvis»**: modelo descargado y operativo (sin falsos positivos en silencio).
- **Playwright** controlando Google Chrome (Edge no está instalado en este PC; se detecta y usa Chrome).
- **Plugin del tiempo** (Open-Meteo) con datos reales de Madrid.
- **Descubrimiento de aplicaciones**: 504 apps del menú Inicio, búsqueda difusa (Chrome, Spotify, VS Code, Discord).
- **Servicio**: arranque en modo bandeja, diagnóstico (`/api/doctor`) y parada ordenada con `Detener-Jarvis`
  sin procesos huérfanos.
- **Interfaz** compilada sin errores de TypeScript y revisada visualmente a 1440×900 y en móvil (375×812).

Errores encontrados y corregidos durante las pruebas: bloqueo indebido de carpetas autorizadas bajo `AppData`;
cursor del generador PDF; incompatibilidad PyAV 19 ↔ faster-whisper (fijado `av<16`); codificación OEM de
PowerShell al listar apps; textarea con altura incorrecta; icono de bandeja que sobrevivía al servicio; el
registro de auditoría ya no puede interrumpir una acción.

## IA local gratuita (añadida el 8/11/2026) — ✅ verificada con modelos reales

- Proveedor Ollama con streaming, herramientas, visión, recorte de contexto, filtro de razonamiento y
  precalentamiento; selector Automático / Claude / Local; modo adaptativo por VRAM; búsqueda web gratuita.
- **Conversaciones reales verificadas** a través de JARVIS (HTTP + WebSocket) con Gemma 4 12B y Qwen3 8B:
  estado del PC con `system_info`, memoria (`recall` → `remember`, sin duplicar) y búsqueda web con
  `web_search` + resumen correcto en español.
- 31/31 pruebas automatizadas (5 nuevas del proveedor local).
- Descargas: el CDN del registro de Ollama no responde en esta red; se añadió la descarga alternativa
  automática desde Hugging Face (verificada con ambos modelos).
- Medido con Roblox abierto (GPU al 97 %): ver [IA_LOCAL.md](IA_LOCAL.md). Sin juegos abiertos no se ha medido.

## Voz manos libres 24/7 (añadida el 8/11/2026)

- ✅ Servicio de voz en el backend (micrófono DGM20 por WASAPI, openWakeWord, Silero VAD, Whisper, reproducción
  por los cascos). Verificado de extremo a extremo con audio sintético: «Hey Jarvis» detectado en 2,2 s →
  «¿Qué hora es?» transcrito → respuesta de la IA local hablada → vuelve a escuchar para continuar.
- ✅ Micrófono real abierto desde el servicio y recibiendo audio; escucha permanente activa en reposo.
- ✅ Pantalla completa, galería de 12 voces con previsualización, voz por defecto Andrew Multilingüe,
  reintentos automáticos de la síntesis.
- 🟡 Pendiente de que lo pruebes con tu propia voz (sensibilidad ajustable en Configuración → Voz).

## Ronda del 9/11/2026

- ✅ **Voz en streaming**: el audio empieza a sonar con los primeros fragmentos (ventana: `GET /api/voice/tts/stream`;
  «Hey JARVIS»: decodificación progresiva con salida de audio abierta toda la respuesta). La voz se adelanta si el
  texto llega lento y, si la IA tarda en empezar, dice una frase corta precargada («Un segundo.»). «Leer respuestas»
  activado por defecto. Verificado con el circuito de voz simulado.
- ✅ Errores que se resuelven solos se muestran discretos («intento fallido · resuelto por otra vía»).
- ✅ Núcleo WebGL (plasma 3D con ruido simplex, iluminación, borde eléctrico, anillos, chispas), aurora animada de
  fondo, entrada de mensajes con desenfoque. Verificado en captura.
- ✅ **JARVIS en el escritorio** (`python -m jarvis overlay`): ventana transparente por píxel sobre el fondo y bajo
  las ventanas, sin clics, 2 % de CPU, 54 MB. Verificada en vivo (posición, capa, conexión).

## Pendiente de verificar (necesita tus credenciales o interacción física)

- 🟡 Conversación real con Claude, búsqueda web del servidor y fallbacks → al guardar tu API key.
  Si tu cuenta no admite alguna beta, el proveedor la desactiva sola y lo indica en el registro.
- 🟡 Bot de Telegram de extremo a extremo (emparejamiento, aprobaciones con PIN, notas de voz) → al guardar el token.
- 🟡 Captura de micrófono y «Hey JARVIS» con tu voz en la ventana de la app (el navegador pedirá permiso).
- 🟡 ElevenLabs y Azure TTS → requieren sus claves (si fallan, cae a Microsoft Neural).
- 🟡 Automatización de escritorio (`take_screenshot`, `desktop_actions`) y cierre de apps: implementadas,
  no ejercitadas en vivo para no interferir con tu sesión.
- 🟡 Inicio automático: implementado (acceso directo en la carpeta Inicio), no activado sin tu permiso.

## Mejoras futuras

- ⏳ Integraciones con correo y calendario (Google / Microsoft 365) como plugins con OAuth.
- ⏳ Conector MCP para servidores MCP remotos cuando aporten valor concreto.
- ⏳ OCR de PDFs escaneados.
- ⏳ TTS por WebSocket de ElevenLabs (audio en streaming dentro de cada frase) para latencia aún menor.
- ⏳ Empaquetado como ejecutable firmado.
