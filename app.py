"""
RoamAI Streamlit dashboard.

Traditional web UI over the Lakebase data. Complements the Agent Bricks
chat interface — this is for browsing trips visually, while the agent
handles conversational planning.

Pages:
  - Home: list your trips + create a new one
  - Trip detail: itinerary, weather forecast, packing list
  - Discover: semantic search demo over activities

Deployed as a Databricks App. Uses the root lakebase.py to talk to
Lakebase Postgres directly (no MCP calls — that's the agent's job).
"""

from datetime import date, datetime, timedelta

import streamlit as st

import lakebase
import trip_client

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="RoamAI",
    page_icon="🌤️",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

def _init_state():
    if "user_id" not in st.session_state:
        # Look up the seeded user
        rows = lakebase.run_query(
            "SELECT id FROM users WHERE email = %s",
            ("rajendrannpriyankaa24@gmail.com",),
        )
        st.session_state.user_id = rows[0]["id"] if rows else 1
    if "page" not in st.session_state:
        st.session_state.page = "home"
    if "selected_trip_id" not in st.session_state:
        st.session_state.selected_trip_id = None


_init_state()


# ---------------------------------------------------------------------------
# Sidebar nav
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("🌤️ RoamAI")
    st.caption("Weather-aware AI trip planner")
    st.divider()

    if st.button("🏠 My Trips", use_container_width=True):
        st.session_state.page = "home"
        st.session_state.selected_trip_id = None
        st.rerun()

    if st.button("✨ New Trip", use_container_width=True):
        st.session_state.page = "new_trip"
        st.rerun()

    if st.button("🔍 Discover Activities", use_container_width=True):
        st.session_state.page = "discover"
        st.rerun()

    st.divider()
    st.caption("Ask the AI agent for help planning your trip in the Agent Bricks playground.")


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def load_trips(user_id: int) -> list[dict]:
    return lakebase.run_query(
        """
        SELECT t.id, t.name, t.start_date, t.end_date, t.notes,
               d.name AS destination_name, d.country, d.admin1
        FROM trips t
        LEFT JOIN destinations d ON d.trip_id = t.id
        WHERE t.user_id = %s
        ORDER BY t.start_date DESC
        """,
        (user_id,),
    )


def load_trip(trip_id: int) -> dict | None:
    rows = lakebase.run_query(
        """
        SELECT t.id, t.name, t.start_date, t.end_date, t.notes,
               d.id AS destination_id, d.name AS destination_name,
               d.country, d.admin1, d.latitude, d.longitude,
               d.description, d.wikipedia_url
        FROM trips t
        LEFT JOIN destinations d ON d.trip_id = t.id
        WHERE t.id = %s
        """,
        (trip_id,),
    )
    return rows[0] if rows else None


def load_itinerary(trip_id: int) -> list[dict]:
    return lakebase.run_query(
        """
        SELECT ii.id, ii.day_number, ii.scheduled_date, ii.time_slot,
               ii.notes, ii.weather_adjusted, ii.adjustment_reason,
               a.name AS activity_name, a.category, a.description,
               a.weather_sensitive, a.duration_hours
        FROM itinerary_items ii
        LEFT JOIN activities a ON a.id = ii.activity_id
        WHERE ii.trip_id = %s
        ORDER BY ii.scheduled_date, ii.time_slot NULLS LAST
        """,
        (trip_id,),
    )


def load_packing_list(trip_id: int) -> list[dict]:
    return lakebase.run_query(
        """
        SELECT id, item, category, is_packed, generated_by, reasoning
        FROM packing_items
        WHERE trip_id = %s
        ORDER BY category, item
        """,
        (trip_id,),
    )


def load_weather(destination_id: int) -> list[dict]:
    return lakebase.run_query(
        """
        SELECT forecast_date, temp_high_f, temp_low_f, precip_chance_pct,
               precip_amount_in, wind_mph, conditions, aqi, uv_max
        FROM weather_snapshots
        WHERE destination_id = %s
        ORDER BY forecast_date
        """,
        (destination_id,),
    )


def semantic_search_activities(query: str, limit: int = 5) -> list[dict]:
    """Search activities across ALL destinations via cosine similarity."""
    from sentence_transformers import SentenceTransformer
    # Cached across calls in the same session
    if "embedding_model" not in st.session_state:
        with st.spinner("Loading embedding model (first search only, ~30 sec)..."):
            st.session_state.embedding_model = SentenceTransformer(
                "sentence-transformers/all-MiniLM-L6-v2"
            )
    model = st.session_state.embedding_model

    vector = model.encode(query).tolist()
    vector_str = "[" + ",".join(f"{x:.6f}" for x in vector) + "]"

    return lakebase.run_query(
        """
        SELECT a.name, a.category, a.description, a.weather_sensitive,
               a.duration_hours, d.name AS destination,
               1 - (a.description_embedding <=> %s::vector) AS similarity
        FROM activities a
        JOIN destinations d ON d.id = a.destination_id
        WHERE a.description_embedding IS NOT NULL
        ORDER BY a.description_embedding <=> %s::vector
        LIMIT %s
        """,
        (vector_str, vector_str, limit),
    )


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

def page_home():
    st.title("My Trips")
    st.caption("Weather-aware itineraries powered by an AI agent")

    trips = load_trips(st.session_state.user_id)

    if not trips:
        st.info("No trips yet. Click **New Trip** in the sidebar to get started.")
        return

    for trip in trips:
        with st.container(border=True):
            col1, col2, col3 = st.columns([4, 2, 1])

            with col1:
                st.subheader(trip["name"])
                if trip["destination_name"]:
                    place = trip["destination_name"]
                    if trip["admin1"]:
                        place += f", {trip['admin1']}"
                    if trip["country"]:
                        place += f", {trip['country']}"
                    st.caption(f"📍 {place}")
                else:
                    st.caption("_No destination set_")

            with col2:
                days = (trip["end_date"] - trip["start_date"]).days + 1
                st.metric("Dates", f"{trip['start_date']} → {trip['end_date']}",
                          f"{days} days")

            with col3:
                if st.button("Open", key=f"open_{trip['id']}", use_container_width=True):
                    st.session_state.selected_trip_id = trip["id"]
                    st.session_state.page = "trip_detail"
                    st.rerun()


def page_new_trip():
    st.title("Plan a New Trip")
    st.caption("Create a trip, then use the AI agent to build a weather-aware itinerary")

    with st.form("new_trip_form"):
        name = st.text_input("Trip name", value="My Kauai adventure")
        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input("Start date", value=date(2026, 12, 22))
        with col2:
            end_date = st.date_input("End date", value=date(2026, 12, 28))

        destination_name = st.text_input(
            "Destination",
            value="Kauai",
            help="City, region, or landmark. Will be geocoded via Open-Meteo.",
        )
        notes = st.text_area("Notes (optional)", height=100)

        submitted = st.form_submit_button("Create Trip", use_container_width=True)

        if submitted:
            if end_date < start_date:
                st.error("End date must be on or after start date.")
                return

            # Insert trip
            trip_rows = lakebase.run_query(
                """
                INSERT INTO trips (user_id, name, start_date, end_date, notes)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
                """,
                (st.session_state.user_id, name, str(start_date), str(end_date),
                 notes or None),
            )
            trip_id = trip_rows[0]["id"]

            # Geocode + insert destination
            try:
                with st.spinner(f"Looking up {destination_name}..."):
                    geo = trip_client.geocode(destination_name)
                    try:
                        wiki = trip_client.get_wikipedia_summary(destination_name)
                        description = wiki.get("extract")
                        wiki_url = wiki.get("url")
                    except Exception:
                        description = f"{geo['name']}, {geo['country']}"
                        wiki_url = None

                lakebase.run_write(
                    """
                    INSERT INTO destinations
                        (trip_id, name, country, admin1, latitude, longitude,
                         timezone, description, wikipedia_url)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (trip_id, geo["name"], geo["country"], geo.get("admin1"),
                     geo["latitude"], geo["longitude"], geo["timezone"],
                     description, wiki_url),
                )
                st.success(f"Trip created! {geo['name']} added as destination.")
            except Exception as e:
                st.warning(f"Trip created (id={trip_id}), but destination lookup "
                           f"failed: {e}. You can retry via the agent.")

            st.session_state.selected_trip_id = trip_id
            st.session_state.page = "trip_detail"
            st.rerun()


def page_trip_detail():
    trip = load_trip(st.session_state.selected_trip_id)
    if not trip:
        st.error("Trip not found.")
        return

    # Header
    st.title(trip["name"])
    if trip["destination_name"]:
        place = trip["destination_name"]
        if trip["admin1"]:
            place += f", {trip['admin1']}"
        if trip["country"]:
            place += f", {trip['country']}"
        st.caption(f"📍 {place}  •  {trip['start_date']} → {trip['end_date']}")

    tabs = st.tabs(["🗓️ Itinerary", "🌤️ Weather", "🎒 Packing", "ℹ️ About"])

    # ---- Itinerary tab
    with tabs[0]:
        itinerary = load_itinerary(trip["id"])
        if not itinerary:
            st.info("No itinerary yet. Ask the AI agent to build one for you.")
        else:
            # Group by day
            days = {}
            for item in itinerary:
                key = str(item["scheduled_date"])
                days.setdefault(key, []).append(item)

            for day_date, items in sorted(days.items()):
                with st.expander(f"📅 {day_date} — Day {items[0]['day_number']}", expanded=True):
                    for item in items:
                        col1, col2 = st.columns([4, 1])
                        with col1:
                            slot = item["time_slot"] or "any time"
                            st.markdown(f"**{slot.title()}** — {item['activity_name']}")
                            if item["category"]:
                                st.caption(f"Category: {item['category']}  •  "
                                           f"Duration: {item['duration_hours'] or '—'} hrs")
                            if item["weather_adjusted"] and item["adjustment_reason"]:
                                st.info(f"🔄 Rescheduled: {item['adjustment_reason']}")
                        with col2:
                            if item["weather_sensitive"]:
                                st.caption("☀️ Outdoor")
                            else:
                                st.caption("🏠 Indoor")

    # ---- Weather tab
    with tabs[1]:
        if not trip["destination_id"]:
            st.info("No destination set for this trip.")
        else:
            weather = load_weather(trip["destination_id"])
            if not weather:
                st.info("Weather forecast not cached yet. Ask the AI agent to "
                        "build an itinerary — it will fetch the forecast.")
            else:
                for day in weather:
                    with st.container(border=True):
                        col1, col2, col3, col4 = st.columns(4)
                        col1.metric("Date", str(day["forecast_date"]))
                        col2.metric("High / Low",
                                    f"{day['temp_high_f']}° / {day['temp_low_f']}°F")
                        col3.metric("Precip", f"{day['precip_chance_pct'] or 0}%",
                                    f"{day['precip_amount_in'] or 0}\"")
                        col4.metric("Wind", f"{day['wind_mph'] or 0} mph")
                        cond = day["conditions"] or "—"
                        aqi = day["aqi"] or "—"
                        st.caption(f"Conditions: {cond}  •  AQI: {aqi}")

    # ---- Packing tab
    with tabs[2]:
        packing = load_packing_list(trip["id"])
        if not packing:
            st.info("Packing list not generated yet. Ask the AI agent to "
                    "build one based on your itinerary and weather.")
        else:
            by_category = {}
            for item in packing:
                by_category.setdefault(item["category"] or "other", []).append(item)

            for cat, items in sorted(by_category.items()):
                st.subheader(cat.replace("_", " ").title())
                for item in items:
                    col1, col2 = st.columns([4, 1])
                    with col1:
                        checkbox_label = item["item"]
                        st.checkbox(checkbox_label, value=item["is_packed"],
                                    key=f"pack_{item['id']}", disabled=True)
                        if item["reasoning"]:
                            st.caption(f"💡 {item['reasoning']}")
                    with col2:
                        st.caption(f"_{item['generated_by'] or 'user'}_")

    # ---- About tab
    with tabs[3]:
        st.subheader("Destination Info")
        if trip["description"]:
            st.write(trip["description"])
        if trip["wikipedia_url"]:
            st.link_button("📖 Read more on Wikipedia", trip["wikipedia_url"])

        st.divider()
        st.subheader("Trip metadata")
        st.write(f"**Trip ID:** {trip['id']}")
        if trip["destination_id"]:
            st.write(f"**Destination ID:** {trip['destination_id']}")
            st.write(f"**Coordinates:** {trip['latitude']}, {trip['longitude']}")


def page_discover():
    st.title("Discover Activities")
    st.caption("Semantic search over all destinations. Try natural-language queries.")

    query = st.text_input(
        "What kind of activity are you looking for?",
        value="peaceful morning near the water",
        placeholder="e.g. adventurous hike with great views, rainy-day indoor thing, "
                    "family-friendly beach",
    )

    limit = st.slider("Number of results", 3, 15, 5)

    if st.button("Search", type="primary", use_container_width=True):
        with st.spinner("Searching..."):
            results = semantic_search_activities(query, limit=limit)

        if not results:
            st.info("No results — try a different query or seed more activities.")
        else:
            st.success(f"Top {len(results)} results for {query!r}")
            for i, r in enumerate(results, 1):
                with st.container(border=True):
                    col1, col2 = st.columns([4, 1])
                    with col1:
                        st.subheader(f"{i}. {r['name']}")
                        st.caption(f"📍 {r['destination']}  •  "
                                   f"Category: {r['category']}  •  "
                                   f"Duration: {r['duration_hours'] or '—'} hrs")
                        st.write(r["description"])
                    with col2:
                        st.metric("Similarity", f"{r['similarity']:.2f}")
                        if r["weather_sensitive"]:
                            st.caption("☀️ Outdoor")
                        else:
                            st.caption("🏠 Indoor")


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

if st.session_state.page == "home":
    page_home()
elif st.session_state.page == "new_trip":
    page_new_trip()
elif st.session_state.page == "trip_detail":
    page_trip_detail()
elif st.session_state.page == "discover":
    page_discover()
else:
    st.session_state.page = "home"
    st.rerun()
