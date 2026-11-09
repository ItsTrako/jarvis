"""Plugin de ejemplo: el tiempo con Open-Meteo (gratis, sin API key).

Sirve como plantilla para añadir integraciones: crea un .py en esta carpeta, decora una
función con ``@tool`` y reinicia JARVIS. No hace falta tocar nada más del proyecto.
"""

import json

import httpx

from jarvis.security import ExecContext, untrusted
from jarvis.tools.base import tool

CODES = {0: "despejado", 1: "mayormente despejado", 2: "parcialmente nuboso", 3: "cubierto", 45: "niebla",
         48: "niebla con escarcha", 51: "llovizna débil", 53: "llovizna", 55: "llovizna intensa", 61: "lluvia débil",
         63: "lluvia", 65: "lluvia fuerte", 71: "nieve débil", 73: "nieve", 75: "nieve fuerte", 80: "chubascos",
         81: "chubascos fuertes", 82: "chubascos violentos", 95: "tormenta", 96: "tormenta con granizo", 99: "tormenta fuerte"}


@tool(
    name="get_weather",
    description="Tiempo actual y previsión de 3 días (Open-Meteo). Si el usuario no nombra una ciudad, NO le "
                "preguntes: omite 'city' y se usa su ubicación actual.",
    parameters={"city": {"type": "string", "description": "Ciudad. Omítela para usar la ubicación del usuario."}},
    required=[], category="integraciones", timeout_s=30,
)
async def get_weather(params: dict, ctx: ExecContext) -> str:
    from jarvis import userinfo
    from jarvis.config import get_config

    city = (params.get("city") or "").strip()
    name = get_config().user.name.strip().lower()
    if city.lower() in ("", name, "mi ciudad", "aquí", "aqui", "my city"):
        city = ""  # sin ciudad (o el modelo confundió el nombre del usuario con un lugar): ubicación actual
    async with httpx.AsyncClient(timeout=15) as c:
        here = None if city else await userinfo.location()
        if here and here.get("lat") is not None:
            loc = {"name": here["ciudad"], "admin1": here.get("region", ""), "country": here.get("pais", ""),
                   "latitude": here["lat"], "longitude": here["lon"]}
        else:
            query = city or (here or {}).get("ciudad", "")
            if not query:
                return "No conozco la ubicación del usuario. Pregúntale la ciudad una vez y guárdala con remember."
            g = (await c.get("https://geocoding-api.open-meteo.com/v1/search",
                             params={"name": query, "count": 1, "language": "es"})).json()
            if not g.get("results"):
                return f"No encuentro la ciudad '{query}'."
            loc = g["results"][0]
        w = (await c.get("https://api.open-meteo.com/v1/forecast", params={
            "latitude": loc["latitude"], "longitude": loc["longitude"], "timezone": "auto", "forecast_days": 3,
            "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max"})).json()
    cur = w["current"]
    out = {
        "lugar": ", ".join(x for x in (loc["name"], loc.get("admin1", ""), loc.get("country", "")) if x),
        "ahora": {"temp_c": cur["temperature_2m"], "sensacion_c": cur["apparent_temperature"],
                  "humedad": cur["relative_humidity_2m"], "viento_kmh": cur["wind_speed_10m"],
                  "estado": CODES.get(cur["weather_code"], cur["weather_code"])},
        "prevision": [{"fecha": d, "max": mx, "min": mn, "prob_lluvia": pp, "estado": CODES.get(code, code)}
                      for d, mx, mn, pp, code in zip(w["daily"]["time"], w["daily"]["temperature_2m_max"],
                                                     w["daily"]["temperature_2m_min"],
                                                     w["daily"]["precipitation_probability_max"],
                                                     w["daily"]["weather_code"])],
    }
    return untrusted("open-meteo", json.dumps(out, ensure_ascii=False))
