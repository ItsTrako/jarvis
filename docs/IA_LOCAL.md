# IA local y gratuita

JARVIS puede funcionar **sin API de Claude y sin coste**, con un modelo abierto ejecutado en tu propia GPU (probado en una RTX 3060)
mediante [Ollama](https://ollama.com). Memoria, herramientas, voz, Telegram, permisos y confirmaciones son
exactamente los mismos; solo cambia quién razona.

## Cómo se elige el motor

*Configuración → Inteligencia → Motor de IA*:

| Opción | Comportamiento |
|---|---|
| **Automático** (por defecto) | Claude si hay API key guardada; si no, el modelo local |
| **Claude · Nube** | Siempre Claude (máxima inteligencia, búsqueda web del servidor, pago por uso) |
| **Local · Gratis** | Siempre el modelo local (gratis, privado, funciona sin Internet salvo búsquedas) |

## Modelos instalados y probados en este PC

| Modelo | Tamaño | Capacidades | Papel |
|---|---|---|---|
| **Gemma 4 12B** (Google, abril 2026) | 7,1 GB | herramientas, visión, audio | **Principal**: la mejor calidad que cabe en 12 GB; español excelente |
| **Qwen3 8B** (Alibaba) | 5,0 GB | herramientas, razonamiento | **Ligero**: rápido y fiable con herramientas |

Se descartaron Qwen 3.6 27B (17 GB) y gpt-oss 20B (14 GB) porque no caben en la GPU junto al
reconocimiento de voz.

## Modo adaptativo

Con un juego u otras apps pesadas abiertas, la GPU se queda sin memoria y Windows empieza a mover datos de
la VRAM a la RAM, lo que vuelve el modelo grande decenas de veces más lento. JARVIS mide la VRAM libre y:

- usa **Gemma 4 12B** cuando hay sitio holgado (pesos + ~1,5 GB para el contexto);
- cambia **solo** a **Qwen3 8B** cuando escasea, y vuelve al principal cuando se libera;
- mantiene cada elección 5 minutos para no cambiar de modelo a mitad de una tarea.

Medido en este PC **con Roblox abierto** (GPU al 97 %): «¿Cuánta RAM tengo libre?» → Gemma 4 210 s,
Qwen3 8B 20 s. Búsqueda web + resumen → Gemma 4 79 s (mejor redacción), Qwen3 8B 48 s.
Con la GPU libre ambos son bastante más rápidos.

## Detalles técnicos

- **Precalentamiento**: al arrancar (o al cambiar de modelo) JARVIS carga el modelo y precalcula las
  instrucciones y las ~54 herramientas (~7.000 tokens) en la caché de Ollama; las preguntas reales solo
  procesan los tokens nuevos.
- **Búsqueda web gratuita**: `web_search` (DuckDuckGo) y `web_fetch` (extracción del texto principal con
  trafilatura), solo activas en modo local; bloquean direcciones locales y privadas.
- **Razonamiento**: *Automático* lo activa en tareas en segundo plano; en conversación se desactiva para
  responder rápido (Gemma 4 razona por defecto si no se le indica; Qwen3 usa `/no_think`).
- **Contexto**: 16K tokens por defecto; el historial antiguo se recorta automáticamente.
- **Descargas**: botón *Descargar* en cada tarjeta. Si el registro oficial de Ollama no avanza (en tu red su
  CDN de descargas no responde), JARVIS descarga la misma versión desde Hugging Face y le pone el nombre corto.
- **Prueba**: botón *Probar* en cada modelo: mide tokens/s, comprueba que llama bien a herramientas en español y
  muestra una frase de ejemplo.

## Limitaciones honestas

- Un modelo de 8–12B razona claramente peor que Claude en tareas largas de varios pasos y se equivoca más
  usando herramientas. Para investigaciones complejas, Claude (incluso Haiku 5.5, muy barato) es mejor.
- La velocidad depende mucho de lo que esté usando la GPU en ese momento.
