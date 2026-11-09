# Modelo de seguridad

JARVIS actúa sobre tu ordenador, así que la seguridad está en el núcleo y no en cada interfaz:
**Telegram, la voz, la interfaz web, los trabajos en segundo plano y las rutinas pasan por exactamente las
mismas comprobaciones** (`tools/base.py` → `security.py`).

## Principio de mínimo privilegio

- El servicio corre con tu usuario normal, **nunca como administrador**, y no solicita elevación.
- Los comandos que tocan antivirus, firewall, UAC, cuentas, privilegios, arranque, servicios o borrado del
  registro de eventos están **bloqueados** aunque el usuario los apruebe (`security.check_shell_command`).
- Solo se accede a **carpetas autorizadas** (por defecto: workspace de JARVIS, Documentos, Escritorio y
  Descargas). Las rutas se resuelven (enlaces y `..`) antes de comprobarlas; dentro de ellas se bloquean
  subcarpetas sensibles (`.ssh`, credenciales, `.aws`…).
- Las aplicaciones abribles son las del menú Inicio más una lista blanca (o solo la lista blanca).
- `open_path` no ejecuta programas ni scripts; los scripts solo se ejecutan desde `data/scripts` (revisados por ti).
- Los procesos críticos del sistema y de seguridad están protegidos frente a `kill_process`/`close_application`.
- Los subprocesos de PowerShell se lanzan **sin** las variables de entorno que contienen claves o tokens.
- El navegador del agente usa un **perfil aislado** (sin tus sesiones ni contraseñas), no accede a direcciones
  locales/privadas y se niega a escribir en campos de contraseña.

## Modo «Acceso total» (activado a petición del usuario el 8/11/2026)

*Configuración → Seguridad → Acceso total al PC.* Con él activo: acceso a todos los discos (C:, D:, F:), puede
abrir cualquier programa o ejecutable y ejecutar cualquier comando, **sin confirmaciones** para lo que se pida
desde el PC (texto o voz). Se mantiene: la lista de bloqueo de protecciones del sistema (antivirus, firewall,
UAC, cuentas, administrador), las subcarpetas de credenciales (.ssh, .aws…), la confirmación con PIN de acciones
peligrosas que lleguen por Telegram o de trabajos automáticos, el registro de auditoría y la parada de emergencia.
Los borrados siguen yendo a la Papelera.

## Niveles de riesgo y confirmación

| Nivel | Ejemplos | Comportamiento |
|---|---|---|
| Seguro | leer, listar, buscar, estado del sistema | Se ejecuta y se registra |
| Moderado | crear archivo nuevo, abrir app, crear documento | Se ejecuta y se registra |
| Sensible | sobrescribir, mover, captura de pantalla, teclado/ratón, rutinas, olvidar | Confirmación explícita |
| Peligroso | Papelera, terminar procesos, PowerShell | **Siempre** confirmación (y PIN en Telegram) |

El umbral es configurable (*Configuración → Seguridad*), pero **lo peligroso siempre exige confirmación**.
La confirmación muestra la acción exacta (p. ej. el comando literal) y los parámetros; caduca a los 5 min
(denegada por defecto). Si el usuario deniega, el modelo recibe la instrucción de no buscar otra vía.

Las peticiones originadas en Telegram o en trabajos/rutinas se envían al móvil con botones
*Aprobar / Denegar*; las peligrosas requieren además el **PIN** (guardado como hash PBKDF2 con sal, 3 intentos;
el mensaje con el PIN se borra del chat). Las originadas en el PC se aprueban en el PC.

## Parada de emergencia

Botón rojo (doble pulsación) en la interfaz, menú del icono de bandeja o `/emergency` en Telegram:
cancela todas las ejecuciones y trabajos en curso, deniega las confirmaciones pendientes y bloquea nuevas
acciones y rutinas hasta reanudar (en Telegram, `/resume` exige PIN). Además, mover el ratón a una esquina
de la pantalla aborta cualquier secuencia de automatización de escritorio.

## Telegram

- Conexión **saliente** por long polling: ningún puerto abierto, nada expuesto a Internet.
- Token en el Administrador de credenciales de Windows.
- Lista blanca de `user_id` y `chat_id` (solo chats privados por defecto). Emparejamiento con código de
  6 dígitos de un solo uso, visible únicamente en la interfaz local y válido 10 minutos.
- Límite de mensajes por minuto por usuario; intentos no autorizados registrados y notificados en el PC.

## API local

- Escucha solo en `127.0.0.1`.
- Token de sesión aleatorio (256 bits) generado en cada arranque e inyectado en la interfaz servida.
- Comprobación de cabecera `Host` (anti DNS-rebinding) y de `Origin`/`Sec-Fetch-Site` (anti CSRF desde webs).
- Los secretos nunca se devuelven por la API (solo si están configurados o no).

## Protección frente a prompt injection

- Todo contenido externo (webs, búsquedas, documentos, archivos, portapapeles, capturas, salidas de comandos,
  mensajes reenviados) se envuelve en `<untrusted_content>` y el prompt de sistema ordena tratarlo como datos.
- Los permisos no dependen del modelo: aunque un documento malicioso convenciera al modelo, cualquier
  acción sensible requiere tu confirmación y lo bloqueado sigue bloqueado.
- Las únicas instrucciones válidas son las tuyas; el bloque `<contexto>` lo genera el sistema.

## Registro de actividad

Cada ejecución, bloqueo, confirmación, decisión, cambio de configuración o credencial, intento no autorizado y
uso del PIN queda en la tabla `audit_log` (*Historial* en la interfaz). Registros técnicos en `data/logs/`.

## Credenciales

API keys, token de Telegram y hash del PIN se guardan en el **Administrador de credenciales de Windows**
(servicio `JARVIS-Assistant`, cifrado DPAPI por usuario). `data/config.yaml` nunca contiene secretos.
Para revocar: *Configuración → Credenciales → eliminar*, o desde el Administrador de credenciales de Windows.
