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

---

## English

JARVIS can act on the computer it runs on, so security issues are taken very seriously.

**Please don't open a public issue.** Use GitHub's private form instead: **Security → Report a vulnerability** in
this repository. Include the affected component (core, tools, Telegram, web interface, voice, installer), steps to
reproduce, the impact, and the version or commit you tested.

In scope: bypassing a confirmation, the Telegram PIN or a tool's risk level; external content (a web page, a
document, a message) making JARVIS run actions nobody asked for; reaching the interface or API from outside
`127.0.0.1` or without the session token; exposing credentials stored in Windows Credential Manager; reading or
writing outside the allowed folders without full access mode enabled.
