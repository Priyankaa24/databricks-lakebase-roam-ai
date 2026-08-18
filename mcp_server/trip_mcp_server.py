"""
RoamAI MCP server.

Exposes 7 tools that a Databricks Agent Bricks agent can call to plan
weather-aware outdoor trips:

  Reads:
    1. get_trip                - full trip context
    2. search_activities       - semantic search over activities

  Writes:
    3. build_itinerary         - generate day-by-day plan
    4. add_itinerary_item      - add one activity to a day
    5. remove_itinerary_item   - delete an itinerary entry
    6. reschedule_for_weather  - move outdoor activities off rainy days
    7. build_packing_list      - generate packing recommendations

Deployed as a Databricks App. Agent Bricks connects to this server as
an external MCP tool source.
"""

import json
import os
import time
import traceback
import uuid
from datetime import date, datetime, timedelta

from fastmcp import FastMCP

import lakebase
import trip_broker

# ---------------------------------------------------------------------------
# Server + user context
# ---------------------------------------------------------------------------

mcp = FastMCP("RoamAI Trip Planner")


def _get_end_user_email() -> str:
    """Read the caller's email from the X-Forwarded-User header set by
    Databricks Apps. Falls back to a generic name in local dev."""
    from fastmcp.server.dependencies import get_http_headers
    try:
        headers = get_http_headers()
        return headers.get("x-forwarded-email") or headers.get("x-forwarded-user") or "unknown@user"
    except Exception:
        return "local-dev@user"


# ---------------------------------------------------------------------------
# Tool call tracing — writes each invocation to mcp_tool_traces_roam
# ---------------------------------------------------------------------------

def _ensure_trace_table():
    """Create the trace table if it doesn't exist. Idempotent."""
    lakebase.run_write(
        """
        CREATE TABLE IF NOT EXISTS mcp_tool_traces_roam (
            id BIGSERIAL PRIMARY KEY,
            session_id TEXT,
            user_email TEXT,
            tool_name TEXT NOT NULL,
            params JSONB,
            result JSONB,
            duration_ms INT,
            success BOOLEAN,
            error_message TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
        """
    )


try:
    _ensure_trace_table()
except Exception:
    # Table might already exist under a different owner; ignore.
    pass


def _trace(tool_name: str, params: dict, result, duration_ms: int, success: bool, error: str | None = None):
    """Best-effort trace write. Never raises to the caller."""
    try:
        lakebase.run_write(
            """
            INSERT INTO mcp_tool_traces_roam
                (session_id, user_email, tool_name, params, result,
                 duration_ms, success, error_message)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                os.environ.get("MCP_SESSION_ID", "unknown"),
                _get_end_user_email(),
                tool_name,
                json.dumps(params, default=str),
                json.dumps(result, default=str) if success else None,
                duration_ms,
                success,
                error,
            ),
        )
    except Exception:
        pass  # never let tracing break a tool call


def traced(fn):
    """Decorator: time the call, capture params + result, log to Lakebase."""
    def wrapper(**kwargs):
        start = time.time()
        try:
            result = fn(**kwargs)
            duration_ms = int((time.time() - start) * 1000)
            _trace(fn.__name__, kwargs, result, duration_ms, True)
            return result
        except Exception as e:
            duration_ms = int((time.time() - start) * 1000)
            _trace(fn.__name__, kwargs, None, duration_ms, False, str(e))
            raise
    wrapper.__name__ = fn.__name__
    wrapper.__doc__ = fn.__doc__
    return wrapper


# ---------------------------------------------------------------------------
# READ TOOLS
# ---------------------------------------------------------------------------

@mcp.tool
@traced
def get_trip(trip_id: int) -> dict:
    """Return full context for a trip: dates, destination, itinerary, and
    packing list. Call this first when the user references a trip so the
    agent has full state before making changes."""
    trip = trip_broker.get_trip(trip_id)
    if not trip:
        return {"error": f"Trip {trip_id} not found"}
    # Convert dates to strings for JSON
    trip["start_date"] = str(trip["start_date"])
    trip["end_date"] = str(trip["end_date"])
    for item in trip.get("itinerary", []):
        if item.get("scheduled_date"):
            item["scheduled_date"] = str(item["scheduled_date"])
    return trip


@mcp.tool
@traced
def search_activities(
    query: str,
    destination_id: int,
    limit: int = 5,
) -> list[dict]:
    """Semantic search over activities at a destination. `query` is a
    natural-language description of what the user wants
    (e.g. 'peaceful morning near water', 'adventurous hike',
    'family-friendly beach'). Returns top matches ranked by cosine
    similarity of their descriptions."""
    return trip_broker.search_activities(query, destination_id, limit)


# ---------------------------------------------------------------------------
# WRITE TOOLS
# ---------------------------------------------------------------------------

@mcp.tool
@traced
def build_itinerary(
    trip_id: int,
    interests: str,
    activities_per_day: int = 2,
) -> dict:
    """Generate a full day-by-day itinerary for a trip.

    Fetches the trip's destination + dates, caches the weather forecast,
    semantically searches for activities matching the user's interests,
    and inserts them into the itinerary_items table, avoiding outdoor
    activities on days with bad weather.

    `interests` is a natural-language description
    (e.g. 'hiking, snorkeling, and quiet mornings').
    """
    trip = trip_broker.get_trip(trip_id)
    if not trip:
        return {"error": f"Trip {trip_id} not found"}
    if not trip.get("destination_id"):
        return {"error": "Trip has no destination"}

    # Cache weather for the trip dates
    trip_broker.cache_weather_for_trip(trip_id)

    # Get activities matching the user's interests
    candidates = trip_broker.search_activities(
        interests, trip["destination_id"], limit=20
    )
    if not candidates:
        return {"error": "No activities found matching interests"}

    # Split into outdoor (weather-sensitive) and indoor (backup)
    outdoor = [a for a in candidates if a["weather_sensitive"]]
    indoor = [a for a in candidates if not a["weather_sensitive"]]

    # Read forecast per day to decide scheduling
    days = (trip["end_date"] - trip["start_date"]).days + 1
    inserted = []
    outdoor_idx = 0
    indoor_idx = 0

    for day_offset in range(days):
        scheduled_date = trip["start_date"] + timedelta(days=day_offset)
        day_number = day_offset + 1

        forecast = trip_broker.get_cached_weather(
            trip["destination_id"], str(scheduled_date)
        )

        is_bad = False
        if forecast:
            fc_dict = {
                "precip_chance_pct": forecast["precip_chance_pct"],
                "precip_in": forecast["precip_amount_in"],
                "conditions": forecast["conditions"],
            }
            is_bad, _ = trip_broker.is_bad_weather_for_outdoors(
                fc_dict, forecast.get("aqi")
            )

        for slot_idx in range(activities_per_day):
            time_slot = ["morning", "afternoon", "evening"][slot_idx % 3]

            if is_bad and indoor_idx < len(indoor):
                activity = indoor[indoor_idx]
                indoor_idx += 1
            elif outdoor_idx < len(outdoor):
                activity = outdoor[outdoor_idx]
                outdoor_idx += 1
            elif indoor_idx < len(indoor):
                activity = indoor[indoor_idx]
                indoor_idx += 1
            else:
                break

            item_id = trip_broker.add_itinerary_item(
                trip_id=trip_id,
                activity_id=activity["id"],
                day_number=day_number,
                scheduled_date=str(scheduled_date),
                time_slot=time_slot,
                notes=None,
            )
            inserted.append({
                "id": item_id,
                "day": day_number,
                "date": str(scheduled_date),
                "time_slot": time_slot,
                "activity": activity["name"],
                "category": activity["category"],
            })

    return {
        "trip_id": trip_id,
        "days_scheduled": days,
        "activities_added": len(inserted),
        "itinerary": inserted,
    }


@mcp.tool
@traced
def add_itinerary_item(
    trip_id: int,
    activity_id: int,
    day_number: int,
    scheduled_date: str,
    time_slot: str = "morning",
    notes: str = "",
) -> dict:
    """Add a single activity to a trip's itinerary. Use this when the
    user wants to add one specific activity rather than build a full
    itinerary. `scheduled_date` in YYYY-MM-DD format; `time_slot` is
    one of morning/afternoon/evening or a clock time like '14:00'."""
    item_id = trip_broker.add_itinerary_item(
        trip_id=trip_id,
        activity_id=activity_id,
        day_number=day_number,
        scheduled_date=scheduled_date,
        time_slot=time_slot,
        notes=notes or None,
    )
    return {"item_id": item_id, "message": "Itinerary item added"}


@mcp.tool
@traced
def remove_itinerary_item(item_id: int) -> dict:
    """Remove an itinerary item by id."""
    rows = trip_broker.remove_itinerary_item(item_id)
    return {"removed": rows, "message": f"Removed itinerary item {item_id}" if rows else "Item not found"}


@mcp.tool
@traced
def reschedule_for_weather(trip_id: int) -> dict:
    """Scan the trip's itinerary against the current forecast and move
    outdoor (weather_sensitive) activities off any day with bad weather
    or poor air quality. Swaps them with indoor items on other days
    when possible. Returns a list of adjustments with reasons."""
    trip = trip_broker.get_trip(trip_id)
    if not trip or not trip.get("destination_id"):
        return {"error": "Trip or destination not found"}

    trip_broker.cache_weather_for_trip(trip_id)

    itinerary = trip["itinerary"]
    if not itinerary:
        return {"message": "No itinerary to reschedule", "adjustments": []}

    # Map day -> list of items
    days_needed = (trip["end_date"] - trip["start_date"]).days + 1
    adjustments = []
    good_days = []
    bad_day_items = []

    for day_offset in range(days_needed):
        scheduled_date = trip["start_date"] + timedelta(days=day_offset)
        forecast = trip_broker.get_cached_weather(
            trip["destination_id"], str(scheduled_date)
        )
        if not forecast:
            continue
        fc_dict = {
            "precip_chance_pct": forecast["precip_chance_pct"],
            "precip_in": forecast["precip_amount_in"],
            "conditions": forecast["conditions"],
        }
        is_bad, reason = trip_broker.is_bad_weather_for_outdoors(
            fc_dict, forecast.get("aqi")
        )

        day_items = [i for i in itinerary if str(i["scheduled_date"]) == str(scheduled_date)]

        if is_bad:
            outdoor_items = [i for i in day_items if i.get("weather_sensitive")]
            for it in outdoor_items:
                bad_day_items.append((it, str(scheduled_date), day_offset + 1, reason))
        else:
            good_days.append((str(scheduled_date), day_offset + 1))

    # Move outdoor items to good days (round-robin)
    for it, orig_date, orig_day, reason in bad_day_items:
        if not good_days:
            break
        new_date, new_day = good_days[0]
        good_days.append(good_days.pop(0))  # rotate

        trip_broker.move_itinerary_item(
            item_id=it["id"],
            new_day_number=new_day,
            new_scheduled_date=new_date,
            reason=f"Moved from day {orig_day} ({orig_date}): {reason}",
        )
        adjustments.append({
            "item_id": it["id"],
            "activity": it["activity_name"],
            "moved_from": orig_date,
            "moved_to": new_date,
            "reason": reason,
        })

    return {
        "trip_id": trip_id,
        "adjustments_made": len(adjustments),
        "adjustments": adjustments,
    }


@mcp.tool
@traced
def build_packing_list(trip_id: int) -> dict:
    """Generate a packing list based on trip length, planned activities,
    and weather forecast. Writes items to the packing_items table with
    reasoning attached to each. Overwrites any existing agent-generated
    items for the trip (user-added items are preserved)."""
    trip = trip_broker.get_trip(trip_id)
    if not trip:
        return {"error": f"Trip {trip_id} not found"}

    # Ensure weather is cached for accurate weather-driven items
    if trip.get("destination_id"):
        trip_broker.cache_weather_for_trip(trip_id)

    items = trip_broker.generate_packing_list(trip_id)

    # Clear previous agent-generated items, keep user-added ones
    lakebase.run_write(
        "DELETE FROM packing_items WHERE trip_id = %s AND generated_by = 'agent'",
        (trip_id,),
    )

    for item in items:
        lakebase.run_write(
            """
            INSERT INTO packing_items (trip_id, item, category, generated_by, reasoning)
            VALUES (%s, %s, %s, 'agent', %s)
            """,
            (trip_id, item["item"], item["category"], item["reasoning"]),
        )

    return {
        "trip_id": trip_id,
        "items_generated": len(items),
        "items": items,
    }


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run(
        transport="http",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8000)),
    )
