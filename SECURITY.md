# Política de seguridad

JARVIS puede actuar sobre el ordenador en el que se ejecuta, así que los fallos de seguridad se toman muy en serio.

## Cómo informar de una vulnerabilidad

**No abras una *issue* pública.** Usa el formulario privado de GitHub:
pestaña **Security → Report a vulnerability** de este repositorio.

Incluye, si puedes:

- Qué componente se ve afectado (núcleo, herramientas, Telegram, interfaz web, voz, instalador).
- Pasos para reproducirlo y el impacto que tiene.
- Versión o *commit* en el que lo has probado.

Recibirás respuesta lo antes posible. Cuando haya una corrección publicada, se reconocerá tu aportación si lo deseas.

## Qué se considera vulnerabilidad

- Saltarse una confirmación, el PIN de Telegram o el nivel de riesgo de una herramienta.
- Que contenido externo (una web, un documento, un mensaje) consiga que JARVIS ejecute acciones no pedidas.
- Acceso a la interfaz o a la API desde fuera de `127.0.0.1`, o sin el token de sesión.
- Exposición de credenciales guardadas en el Administrador de credenciales de Windows.
- Lectura o escritura fuera de las carpetas autorizadas sin el modo de acceso total activado.

## Diseño de seguridad

El modelo completo (niveles de riesgo, aprobaciones, parada de emergencia y defensa frente a inyección de
instrucciones) está en [docs/SEGURIDAD.md](docs/SEGURIDAD.md).
