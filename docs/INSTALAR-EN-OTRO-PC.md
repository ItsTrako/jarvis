# Instalar JARVIS igual en otro PC

## En este PC (el original)

1. Doble clic en **`Exportar-JARVIS.cmd`**.
2. Se crea `exportar\JARVIS-Setup-AAAAMMDD-HHMM.zip` (~1 MB) y se abre la carpeta.
3. Copia ese ZIP al portátil (USB, nube, etc.).

El paquete incluye: todo el programa, la interfaz ya compilada, **tu configuración** (voz, «Hey JARVIS», acceso
total, esfera del escritorio, motor de IA, tu nombre, Telegram autorizado, automatizaciones…), **tu memoria, tareas
y conversaciones**, tus scripts revisados y las **versiones exactas** de todas las librerías que funcionan aquí.

No incluye, a propósito:
- **Credenciales** (API keys, token de Telegram, PIN): están cifradas por Windows en este PC y no deben viajar en un
  ZIP. El instalador te las pide.
- **Modelos de IA y de voz** (~13 GB): se descargan solos en el portátil, elegidos según su gráfica.

> ¿Sin memoria ni conversaciones? `cd backend` y `..\.venv\Scripts\python -m jarvis export --sin-datos`.

## En el otro PC

1. Descomprime el ZIP, idealmente en **`C:\JARVIS`** (evita carpetas sincronizadas como OneDrive).
2. Doble clic en **`INSTALAR.cmd`**. No necesita administrador. El instalador hace todo:
   - instala lo que falte con winget: **Python 3.12**, **Ollama** (IA local gratuita) y **ffmpeg**;
   - crea el entorno con las versiones exactas y, si hay gráfica NVIDIA, la aceleración CUDA de la voz;
   - aplica tu configuración y restaura tu memoria;
   - elige y descarga los modelos según la gráfica, y deja la voz y «Hey JARVIS» precargados;
   - te pide las credenciales, crea el acceso directo del escritorio y ofrece el inicio automático;
   - pasa el diagnóstico y arranca JARVIS.
3. Al abrirlo, ve a *Configuración → Voz → Micrófono* y elige el micrófono del portátil.

Tarda unos 10-30 minutos, casi todo descargando los modelos. Si se corta, vuelve a ejecutar `INSTALAR.cmd`: retoma
lo que falte.

## Qué modelo usará según el portátil

| Gráfica del portátil | IA local (principal / ligero) | Reconocimiento de voz |
|---|---|---|
| NVIDIA con 10 GB o más | Gemma 4 12B / Qwen3 8B | Whisper large-v3-turbo en GPU |
| NVIDIA con 7-10 GB | Qwen3 8B / Qwen3 4B | Whisper large-v3-turbo en GPU |
| NVIDIA con 4-7 GB | Qwen3 4B | Whisper large-v3-turbo en GPU |
| Sin NVIDIA | Qwen3 4B (en CPU, más lento) | Whisper small en CPU |

Si pones la misma API key de Claude, en modo *Automático* usará Claude (igual de listo en cualquier portátil).

## Telegram en dos PCs

Un bot de Telegram solo puede estar conectado a **un** PC a la vez. Si quieres usarlo en los dos, crea **otro bot**
con @BotFather para el portátil y pega ese token durante la instalación. Tu usuario ya viene autorizado y el PIN se
vuelve a definir.

## Mantenerlos iguales

Cuando cambies cosas en un PC, vuelve a exportar e instala el ZIP nuevo **encima** en el otro: se actualiza el
programa, se aplica la configuración y se reemplaza la memoria por la del paquete.
