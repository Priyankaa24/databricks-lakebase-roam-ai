"""
Trip broker: business logic for the MCP server tools.

Handles external APIs (Open-Meteo geocoding + weather + air quality,
Wikipedia) and semantic search over Lakebase pgvector.

The MCP server tools (in trip_mcp_server.py) call functions here.
Keeps the tool definitions thin and testable.
"""

import json
import os
from datetime import date, datetime, timedelta
from functools import lru_cache
from typing import Any

import requests

import lakebase

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

EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

DEFAULT_TIMEOUT = 15


# ---------------------------------------------------------------------------
# Embedding model — loaded once on first use
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _get_embedding_model():
    """Load sentence-transformers model. Cached after first call."""
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(EMBEDDING_MODEL_NAME)


def encode_query(text: str) -> str:
    """Encode text into a 384-dim pgvector-compatible string."""
    model = _get_embedding_model()
    vector = model.encode(text).tolist()
    return "[" + ",".join(f"{x:.6f}" for x in vector) + "]"


# ---------------------------------------------------------------------------
# External APIs
# ---------------------------------------------------------------------------

def geocode(location: str) -> dict[str, Any]:
    """Resolve a location name to lat/lon + timezone via Open-Meteo."""
    resp = requests.get(
        f"{OPEN_METEO_GEOCODE_BASE}/search",
        params={"name": location, "count": 1, "language": "en", "format": "json"},
        timeout=DEFAULT_TIMEOUT,
    )
    resp.raise_for_status()
    results = resp.json().get("results") or []
    if not results:
        raise ValueError(f"No location found for: {location!r}")
    top = results[0]
    return {
        "name": top.get("name"),
        "country": top.get("country"),
        "admin1": top.get("admin1"),
        "latitude": top.get("latitude"),
        "longitude": top.get("longitude"),
        "timezone": top.get("timezone"),
    }


def get_wikipedia_summary(title: str) -> dict[str, Any]:
    """Fetch Wikipedia REST summary for a page title."""
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
    }


def get_daily_forecast(latitude: float, longitude: float, days: int = 7) -> list[dict]:
    """Daily weather forecast for a location (1-7 days)."""
    days = max(1, min(7, int(days)))
    resp = requests.get(
        f"{OPEN_METEO_BASE}/forecast",
        params={
            "latitude": latitude,
            "longitude": longitude,
            "daily": ",".join([
                "temperature_2m_max", "temperature_2m_min",
                "precipitation_sum", "precipitation_probability_max",
                "weather_code", "wind_speed_10m_max",
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
    return [
        {
            "date": dates[i],
            "high_f": daily.get("temperature_2m_max", [None])[i],
            "low_f": daily.get("temperature_2m_min", [None])[i],
            "precip_in": daily.get("precipitation_sum", [None])[i],
            "precip_chance_pct": daily.get("precipitation_probability_max", [None])[i],
            "wind_mph": daily.get("wind_speed_10m_max", [None])[i],
            "conditions": _weather_code_to_text(daily.get("weather_code", [None])[i]),
        }
        for i in range(len(dates))
    ]


def get_air_quality(latitude: float, longitude: float, days: int = 5) -> list[dict]:
    """Daily air quality forecast (US EPA AQI + UV).

    Note: Open-Meteo's air quality API only supports up to 5 forecast days.
    We cap at 5 even when the caller requests more; for trips longer than
    5 days we just don't have AQI data for the tail end.
    """
    days = max(1, min(5, int(days)))
    resp = requests.get(
        f"{OPEN_METEO_AIR_QUALITY_BASE}/air-quality",
        params={
            "latitude": latitude,
            "longitude": longitude,
            "daily": "us_aqi,uv_index_max",
            "forecast_days": days,
            "timezone": "auto",
        },
        timeout=DEFAULT_TIMEOUT,
    )
    resp.raise_for_status()
    daily = resp.json().get("daily", {})
    dates = daily.get("time", [])
    return [
        {
            "date": dates[i],
            "us_aqi": daily.get("us_aqi", [None])[i],
            "uv_max": daily.get("uv_index_max", [None])[i],
        }
        for i in range(len(dates))
    ]


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


def is_bad_weather_for_outdoors(day_forecast: dict, aqi: int | None = None) -> tuple[bool, str]:
    """Rule of thumb: is this day bad for outdoor activities?

    Returns (is_bad, reason). The agent uses this in reschedule_for_weather.
    """
    precip_chance = day_forecast.get("precip_chance_pct") or 0
    precip_amount = day_forecast.get("precip_in") or 0
    conditions = (day_forecast.get("conditions") or "").lower()

    if precip_chance >= 60:
        return True, f"{precip_chance}% chance of rain"
    if precip_amount >= 0.3:
        return True, f"{precip_amount} inches of rain expected"
    if "thunderstorm" in conditions:
        return True, f"thunderstorms forecast"
    if aqi is not None and aqi >= 100:
        return True, f"poor air quality (AQI {aqi})"
    return False, "OK for outdoors"


# ---------------------------------------------------------------------------
# Lakebase — trips, destinations, activities, itinerary
# ---------------------------------------------------------------------------

def get_trip(trip_id: int) -> dict | None:
    """Full trip context: trip + destination + itinerary items."""
    trip_rows = lakebase.run_query(
        """
        SELECT t.id, t.name, t.start_date, t.end_date, t.notes,
               d.id AS destination_id, d.name AS destination_name,
               d.country, d.admin1, d.latitude, d.longitude, d.timezone,
               d.description AS destination_description
        FROM trips t
        LEFT JOIN destinations d ON d.trip_id = t.id
        WHERE t.id = %s
        """,
        (trip_id,),
    )
    if not trip_rows:
        return None
    trip = trip_rows[0]

    itinerary = lakebase.run_query(
        """
        SELECT ii.id, ii.day_number, ii.scheduled_date, ii.time_slot,
               ii.notes, ii.weather_adjusted, ii.adjustment_reason,
               a.id AS activity_id, a.name AS activity_name,
               a.category, a.weather_sensitive, a.duration_hours
        FROM itinerary_items ii
        LEFT JOIN activities a ON a.id = ii.activity_id
        WHERE ii.trip_id = %s
        ORDER BY ii.scheduled_date, ii.time_slot NULLS LAST
        """,
        (trip_id,),
    )
    trip["itinerary"] = itinerary

    packing = lakebase.run_query(
        "SELECT id, item, category, is_packed, generated_by, reasoning "
        "FROM packing_items WHERE trip_id = %s ORDER BY category, item",
        (trip_id,),
    )
    trip["packing_list"] = packing

    return trip


def search_activities(query: str, destination_id: int, limit: int = 5) -> list[dict]:
    """Semantic search over activities for a destination."""
    query_vec_str = encode_query(query)
    return lakebase.run_query(
        """
        SELECT id, name, category, description, weather_sensitive, duration_hours,
               1 - (description_embedding <=> %s::vector) AS similarity
        FROM activities
        WHERE destination_id = %s
          AND description_embedding IS NOT NULL
        ORDER BY description_embedding <=> %s::vector
        LIMIT %s
        """,
        (query_vec_str, destination_id, query_vec_str, limit),
    )


def add_itinerary_item(
    trip_id: int,
    activity_id: int,
    day_number: int,
    scheduled_date: str,
    time_slot: str | None = None,
    notes: str | None = None,
) -> int:
    """Insert an itinerary item, return its id."""
    rows = lakebase.run_query(
        """
        INSERT INTO itinerary_items
            (trip_id, activity_id, day_number, scheduled_date, time_slot, notes)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (trip_id, activity_id, day_number, scheduled_date, time_slot, notes),
    )
    return rows[0]["id"]


def remove_itinerary_item(item_id: int) -> int:
    """Delete an itinerary item, return rows affected."""
    return lakebase.run_write(
        "DELETE FROM itinerary_items WHERE id = %s", (item_id,)
    )


def move_itinerary_item(
    item_id: int,
    new_day_number: int,
    new_scheduled_date: str,
    reason: str | None = None,
) -> int:
    """Move an itinerary item to a different day."""
    return lakebase.run_write(
        """
        UPDATE itinerary_items
        SET day_number = %s,
            scheduled_date = %s,
            weather_adjusted = TRUE,
            adjustment_reason = %s,
            updated_at = NOW()
        WHERE id = %s
        """,
        (new_day_number, new_scheduled_date, reason, item_id),
    )


# ---------------------------------------------------------------------------
# Weather snapshot cache — writes to weather_snapshots for later reads
# ---------------------------------------------------------------------------

def cache_weather_for_trip(trip_id: int) -> int:
    """Fetch forecast for the trip's destination + dates, upsert into
    weather_snapshots. Returns number of days cached."""
    trip = get_trip(trip_id)
    if not trip or not trip.get("destination_id"):
        return 0

    days_needed = (trip["end_date"] - trip["start_date"]).days + 1
    forecast = get_daily_forecast(trip["latitude"], trip["longitude"], days=days_needed)
    aqi = get_air_quality(trip["latitude"], trip["longitude"], days=days_needed)
    aqi_by_date = {a["date"]: a for a in aqi}

    cached = 0
    for day in forecast:
        aqi_data = aqi_by_date.get(day["date"], {})
        lakebase.run_write(
            """
            INSERT INTO weather_snapshots
                (destination_id, forecast_date, temp_high_f, temp_low_f,
                 precip_chance_pct, precip_amount_in, wind_mph, conditions,
                 aqi, uv_max, raw_payload)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (destination_id, forecast_date) DO UPDATE
            SET temp_high_f = EXCLUDED.temp_high_f,
                temp_low_f = EXCLUDED.temp_low_f,
                precip_chance_pct = EXCLUDED.precip_chance_pct,
                precip_amount_in = EXCLUDED.precip_amount_in,
                wind_mph = EXCLUDED.wind_mph,
                conditions = EXCLUDED.conditions,
                aqi = EXCLUDED.aqi,
                uv_max = EXCLUDED.uv_max,
                raw_payload = EXCLUDED.raw_payload,
                fetched_at = NOW()
            """,
            (
                trip["destination_id"],
                day["date"],
                day["high_f"],
                day["low_f"],
                day["precip_chance_pct"],
                day["precip_in"],
                day["wind_mph"],
                day["conditions"],
                aqi_data.get("us_aqi"),
                aqi_data.get("uv_max"),
                json.dumps({"forecast": day, "aqi": aqi_data}),
            ),
        )
        cached += 1
    return cached


def get_cached_weather(destination_id: int, target_date: str) -> dict | None:
    """Read a single day's cached forecast."""
    rows = lakebase.run_query(
        """
        SELECT forecast_date, temp_high_f, temp_low_f,
               precip_chance_pct, precip_amount_in, wind_mph, conditions,
               aqi, uv_max
        FROM weather_snapshots
        WHERE destination_id = %s AND forecast_date = %s
        """,
        (destination_id, target_date),
    )
    return rows[0] if rows else None


# ---------------------------------------------------------------------------
# Packing list generation — rule-based on activities + weather
# ---------------------------------------------------------------------------

def generate_packing_list(trip_id: int) -> list[dict]:
    """Generate a packing list based on trip length, activities, and weather.

    Returns a list of dicts with item, category, reasoning.
    Does not write to DB — caller (build_packing_list tool) handles writes.
    """
    trip = get_trip(trip_id)
    if not trip:
        return []

    days = (trip["end_date"] - trip["start_date"]).days + 1
    items = []

    # Baseline packing
    items.append({"item": "Passport / ID", "category": "documents",
                  "reasoning": "always needed for travel"})
    items.append({"item": f"{days + 1} shirts", "category": "clothing",
                  "reasoning": f"{days}-day trip"})
    items.append({"item": f"{days} pairs of underwear/socks", "category": "clothing",
                  "reasoning": f"{days}-day trip"})
    items.append({"item": "Toothbrush and toothpaste", "category": "toiletries",
                  "reasoning": "daily use"})
    items.append({"item": "Phone charger", "category": "electronics",
                  "reasoning": "daily use"})

    # Activity-driven items
    itinerary = trip.get("itinerary", [])
    activity_categories = {i["category"] for i in itinerary if i.get("category")}

    if "hiking" in activity_categories:
        items.append({"item": "Hiking shoes", "category": "activity_gear",
                      "reasoning": "hiking activity planned"})
        items.append({"item": "Daypack", "category": "activity_gear",
                      "reasoning": "hiking activity planned"})
        items.append({"item": "Reusable water bottle", "category": "activity_gear",
                      "reasoning": "hiking activity planned"})

    if any(c in activity_categories for c in ("beach", "water_sports")):
        items.append({"item": "Swimsuit", "category": "clothing",
                      "reasoning": "beach or water activity planned"})
        items.append({"item": "Reef-safe sunscreen", "category": "toiletries",
                      "reasoning": "outdoor water activity"})
        items.append({"item": "Beach towel", "category": "activity_gear",
                      "reasoning": "beach activity planned"})

    if "water_sports" in activity_categories:
        items.append({"item": "Rash guard or quick-dry shirt", "category": "activity_gear",
                      "reasoning": "water sports planned"})

    # Weather-driven items
    dest_id = trip.get("destination_id")
    if dest_id:
        forecasts = lakebase.run_query(
            """
            SELECT forecast_date, precip_chance_pct, temp_high_f, temp_low_f
            FROM weather_snapshots
            WHERE destination_id = %s
              AND forecast_date BETWEEN %s AND %s
            """,
            (dest_id, trip["start_date"], trip["end_date"]),
        )
        rainy_days = [f for f in forecasts if (f["precip_chance_pct"] or 0) >= 40]
        if rainy_days:
            items.append({
                "item": "Waterproof jacket or poncho",
                "category": "weather_gear",
                "reasoning": f"{len(rainy_days)} day(s) with rain in forecast",
            })
        cool_days = [f for f in forecasts if (f["temp_low_f"] or 100) < 65]
        if cool_days:
            items.append({
                "item": "Light jacket or sweater",
                "category": "clothing",
                "reasoning": f"{len(cool_days)} evening(s) with lows under 65°F",
            })

    return items
