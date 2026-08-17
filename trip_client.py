"""
Trip client: thin HTTP wrapper around the third-party APIs used by RoamAI.

Provides a clean interface for pulling data from external APIs
and returning clean dicts. The ingestion notebook and the MCP server
both call functions from this module.

APIs (all free, no key required):
  - Open-Meteo Geocoding — location name → lat/lon + timezone
  - Open-Meteo Weather   — hourly + daily forecasts
  - Open-Meteo Air Quality — AQI, PM2.5, UV
  - Wikipedia (Wikimedia REST) — destination summaries + nearby articles

"""

import os
from typing import Any

import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

OPEN_METEO_BASE = "https://api.open-meteo.com/v1"
OPEN_METEO_GEOCODE_BASE = "https://geocoding-api.open-meteo.com/v1"
OPEN_METEO_AIR_QUALITY_BASE = "https://air-quality-api.open-meteo.com/v1"
WIKIPEDIA_BASE = "https://en.wikipedia.org/api/rest_v1"

WIKIPEDIA_USER_AGENT = os.environ.get(
    "WIKIPEDIA_USER_AGENT",
    "RoamAI/1.0 (rajendrannpriyankaa24@gmail.com)",
)

DEFAULT_TIMEOUT = 15

# ---------------------------------------------------------------------------
# Geocoding: place name -> lat/lon
# ---------------------------------------------------------------------------

def geocode(location: str) -> dict[str, Any]:
    """Resolve a location name to lat/lon + timezone via Open-Meteo geocoding.

    Raises ValueError if no result is found.
    """
    resp = requests.get(
        f"{OPEN_METEO_GEOCODE_BASE}/search",
        params={"name": location, "count": 1, "language": "en", "format": "json"},
        timeout=DEFAULT_TIMEOUT,
    )
    resp.raise_for_status()
    results = resp.json().get("results") or []
    if not results:
        raise ValueError(f"No location found for query: {location!r}")
    top = results[0]
    return {
        "query": location,
        "name": top.get("name"),
        "country": top.get("country"),
        "admin1": top.get("admin1"),
        "latitude": top.get("latitude"),
        "longitude": top.get("longitude"),
        "timezone": top.get("timezone"),
    }


# ---------------------------------------------------------------------------
# Wikipedia: summary of a destination
# ---------------------------------------------------------------------------

def get_wikipedia_summary(title: str) -> dict[str, Any]:
    """Fetch the Wikipedia REST summary for a page title.

    Returns extract (plain-text summary), URL, and thumbnail if available.
    Raises requests.HTTPError on 404 (page not found).
    """
    resp = requests.get(
        f"{WIKIPEDIA_BASE}/page/summary/{title}",
        headers={"User-Agent": WIKIPEDIA_USER_AGENT},
        timeout=DEFAULT_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    return {
        "title": data.get("title"),
        "extract": data.get("extract"),
        "url": data.get("content_urls", {}).get("desktop", {}).get("page"),
        "thumbnail": (data.get("thumbnail") or {}).get("source"),
        "description": data.get("description"),
    }


# ---------------------------------------------------------------------------
# Air Quality (Open-Meteo)
# ---------------------------------------------------------------------------

def get_air_quality(latitude: float, longitude: float, days: int = 5) -> dict[str, Any]:
    """Daily air quality forecast for a location (US EPA AQI + UV)."""
    days = max(1, min(7, int(days)))
    resp = requests.get(
        f"{OPEN_METEO_AIR_QUALITY_BASE}/air-quality",
        params={
            "latitude": latitude,
            "longitude": longitude,
            "daily": ",".join(["us_aqi", "uv_index_max"]),
            "forecast_days": days,
            "timezone": "auto",
        },
        timeout=DEFAULT_TIMEOUT,
    )
    resp.raise_for_status()
    daily = resp.json().get("daily", {})
    dates = daily.get("time", [])
    return {
        "latitude": latitude,
        "longitude": longitude,
        "days": [
            {
                "date": dates[i],
                "us_aqi": daily.get("us_aqi", [None])[i],
                "uv_index_max": daily.get("uv_index_max", [None])[i],
            }
            for i in range(len(dates))
        ],
    }


# ---------------------------------------------------------------------------
# Weather Forecast (Open-Meteo)
# ---------------------------------------------------------------------------

def get_daily_forecast(latitude: float, longitude: float, days: int = 7) -> dict[str, Any]:
    """Daily weather forecast for a location (1-7 days)."""
    days = max(1, min(7, int(days)))
    resp = requests.get(
        f"{OPEN_METEO_BASE}/forecast",
        params={
            "latitude": latitude,
            "longitude": longitude,
            "daily": ",".join([
                "temperature_2m_max",
                "temperature_2m_min",
                "precipitation_sum",
                "precipitation_probability_max",
                "weather_code",
                "wind_speed_10m_max",
                "sunrise",
                "sunset",
            ]),
            "forecast_days": days,
            "timezone": "auto",
            "temperature_unit": "fahrenheit",
            "wind_speed_unit": "mph",
            "precipitation_unit": "inch",
        },
        timeout=DEFAULT_TIMEOUT,
    )
    resp.raise_for_status()
    daily = resp.json().get("daily", {})
    dates = daily.get("time", [])
    return {
        "latitude": latitude,
        "longitude": longitude,
        "days": [
            {
                "date": dates[i],
                "high_f": daily.get("temperature_2m_max", [None])[i],
                "low_f": daily.get("temperature_2m_min", [None])[i],
                "precipitation_in": daily.get("precipitation_sum", [None])[i],
                "precipitation_chance_pct": daily.get("precipitation_probability_max", [None])[i],
                "max_wind_mph": daily.get("wind_speed_10m_max", [None])[i],
                "weather_code": daily.get("weather_code", [None])[i],
                "conditions": _weather_code_to_text(daily.get("weather_code", [None])[i]),
                "sunrise": daily.get("sunrise", [None])[i],
                "sunset": daily.get("sunset", [None])[i],
            }
            for i in range(len(dates))
        ],
    }


# ---------------------------------------------------------------------------
# WMO weather code -> text
# ---------------------------------------------------------------------------

_WEATHER_CODES = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Depositing rime fog",
    51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
    61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
    71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow",
    80: "Slight rain showers", 81: "Moderate rain showers", 82: "Violent rain showers",
    95: "Thunderstorm", 96: "Thunderstorm with slight hail", 99: "Thunderstorm with heavy hail",
}


def _weather_code_to_text(code: int | None) -> str | None:
    if code is None:
        return None
    return _WEATHER_CODES.get(int(code), f"Unknown ({code})")
