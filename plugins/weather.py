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
    description="Tiempo actual y previsión de 3 días para una ciudad (Open-Meteo).",
    parameters={"city": {"type": "string"}},
    required=["city"], category="integraciones", timeout_s=30,
)
async def get_weather(params: dict, ctx: ExecContext) -> str:
    async with httpx.AsyncClient(timeout=15) as c:
        g = (await c.get("https://geocoding-api.open-meteo.com/v1/search",
                         params={"name": params["city"], "count": 1, "language": "es"})).json()
        if not g.get("results"):
            return f"No encuentro la ciudad '{params['city']}'."
        loc = g["results"][0]
        w = (await c.get("https://api.open-meteo.com/v1/forecast", params={
            "latitude": loc["latitude"], "longitude": loc["longitude"], "timezone": "auto", "forecast_days": 3,
            "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max"})).json()
    cur = w["current"]
    out = {
        "lugar": f"{loc['name']}, {loc.get('admin1', '')}, {loc.get('country', '')}",
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
