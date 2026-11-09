# Cómo extender JARVIS

## Añadir una herramienta (plugin)

Crea un archivo en `plugins/` (por ejemplo `plugins/spotify.py`) y reinicia JARVIS. No hay que tocar nada más.

```python
from jarvis.security import ExecContext, Risk, untrusted
from jarvis.tools.base import ToolResult, tool


@tool(
    name="mi_herramienta",
    description="Qué hace y cuándo debe usarla el modelo (sé concreto).",
    parameters={
        "consulta": {"type": "string", "description": "Texto a buscar"},
        "limite": {"type": "integer"},
        "modo": {"type": "string", "enum": ["rapido", "completo"]},
    },
    required=["consulta"],
    risk=Risk.SAFE,              # SAFE | MODERATE | SENSITIVE | DANGEROUS
    category="integraciones",
    timeout_s=60,
    # risk_fn=lambda p: Risk.SENSITIVE if p.get("modo") == "completo" else Risk.SAFE,
    # summary_fn=lambda p: f"Buscar {p['consulta']}",   # texto mostrado en confirmaciones
    # blocking=True,                                      # si la función es síncrona/bloqueante
)
async def mi_herramienta(params: dict, ctx: ExecContext) -> str | ToolResult:
    datos = "..."  # llama a tu API, lee un archivo, etc.
    # Envuelve SIEMPRE el contenido externo como no confiable:
    return untrusted("mi_servicio", datos)
```

Reglas:
- Para rutas usa `jarvis.security.resolve_path(ruta)` (aplica las carpetas autorizadas).
- Para archivos generados devuelve `ToolResult(texto, files=[ruta])` y se entregarán en la UI y en Telegram.
- Lanza `PermissionDenied` para rechazar con un mensaje claro.
- La herramienta aparece automáticamente en *Herramientas* de la interfaz con su nivel de riesgo.

Plugin de ejemplo funcional: [`plugins/weather.py`](../plugins/weather.py).

## Scripts revisados

Coloca scripts `.ps1`, `.py` o `.bat` en `data/scripts/` (la primera línea de comentario es su descripción).
JARVIS los lista con `list_scripts` y los ejecuta con `run_script` (con confirmación).

## Otro proveedor de IA

1. Implementa `LLMProvider` (`backend/jarvis/llm/base.py`): `stream_turn` debe devolver bloques en formato
   canónico (`text`, `thinking`, `tool_use`) y aceptar `tool_result` en el historial.
2. Regístralo en `llm/get_provider()` y añade el nombre a `LLMConfig.provider` en `config.py`.

## Otro motor de voz

Añade una función `async def _mi_motor(text) -> bytes` (MP3) en `voice/tts.py`, regístrala en `synthesize()` y
añade la opción en `VoiceConfig.tts_engine` y en la pantalla de Configuración.

## PostgreSQL

Instala `asyncpg` en el entorno y en `data/config.yaml` pon
`database_url: postgresql+asyncpg://usuario:clave@host/jarvis`. Las tablas se crean al arrancar.

## Desarrollo de la interfaz

```bash
cd frontend
npm run dev          # http://localhost:5173 con recarga en caliente (necesita el backend en marcha)
npm run build        # compila a frontend/dist, que sirve el backend
```

## Pruebas

```bash
cd backend
..\.venv\Scripts\python -m pytest tests
```
Las pruebas usan una carpeta temporal y un proveedor de IA simulado: no consumen API ni tocan tus datos.
