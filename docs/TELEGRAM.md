# Telegram: JARVIS en tu móvil

`TELÉFONO → TELEGRAM → JARVIS (tu PC) → RESPUESTA`. Funciona desde cualquier lugar con Internet mientras el PC
esté encendido y JARVIS en ejecución (activa *Iniciar con Windows* para no depender de abrirlo a mano).

## Configuración (una vez)

1. En Telegram abre [@BotFather](https://t.me/BotFather) → `/newbot` → elige nombre y usuario (debe acabar
   en `bot`). Copia el **token**.
2. En JARVIS: *Configuración → Credenciales → Token del bot de Telegram* → pegar → *Guardar*.
   El estado pasará a **conectado**.
3. *Configuración → Telegram → PIN de seguridad*: define un PIN de 4–12 dígitos.
4. *Configuración → Telegram → Emparejar mi móvil → Generar código*. En el móvil abre tu bot y envía
   `/pair 123456` (el código mostrado). Queda autorizado solo tu usuario y tu chat.

Opcional en BotFather: `/setprivacy` → *Enable* y `/setjoingroups` → *Disable* (el bot es solo para ti).

## Uso

Escríbele con naturalidad o envía **notas de voz** (se transcriben en el PC con Whisper), **fotos** (las
analiza con visión) y **documentos** (se guardan en `workspace/telegram_recibidos` y puede leerlos).

Mientras trabaja verás un mensaje de estado que se actualiza con el plan y las herramientas usadas; al
terminar recibes la respuesta y los **archivos generados** como adjuntos.

| Comando | Función |
|---|---|
| `/status` | Estado de JARVIS, del modelo y del PC (CPU, RAM, GPU) |
| `/tasks` | Tareas pendientes |
| `/jobs` | Trabajos en segundo plano y su progreso |
| `/memory` | Lo que JARVIS recuerda de ti |
| `/new` | Nueva conversación (la memoria persistente se mantiene) |
| `/stop` | Detener la tarea en curso |
| `/brief` · `/detailed` | Respuestas resumidas o detalladas |
| `/voice` | Activar/desactivar respuestas también por nota de voz |
| `/emergency` | Parada de emergencia |
| `/resume` | Reanudar tras la parada (pide PIN) |
| `/id` | Muestra tu user_id y chat_id |

## Confirmaciones desde el móvil

Si una acción necesita permiso, llega un mensaje con **✅ Aprobar / ❌ Denegar** y la descripción exacta.
Para acciones peligrosas (borrar, terminar procesos, PowerShell) se pide el PIN; el mensaje con el PIN se
borra automáticamente. Las confirmaciones de trabajos en segundo plano y rutinas también llegan aquí.

## Notificaciones

Los trabajos en segundo plano («investiga… y avísame») y las rutinas programadas te envían el resultado y
los archivos por Telegram (y como notificación de Windows en el PC).

## Seguridad

Conexión saliente cifrada (no se abre ningún puerto), lista blanca de usuario y chat, límite de mensajes por
minuto, intentos no autorizados registrados y avisados en el PC. Para revocar el acceso de un dispositivo:
*Configuración → Telegram → Usuarios autorizados → ✕*. Detalles en [SEGURIDAD.md](SEGURIDAD.md).
