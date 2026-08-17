# RoamAI

**AI outdoor trip planner that adapts to the weather.**

RoamAI is a trip-planning app where an AI agent builds day-by-day
itineraries from live weather forecasts, air quality data, and semantic
search over destination attractions — then reschedules outdoor
activities automatically when the forecast changes.

Built on Databricks for the "Rise of the AI Data Engineer" bootcamp
capstone. Extends the RAG + MCP patterns from Day 2 and Day 3 into a
full agentic application.

---

## What makes it weather-aware

Most trip planners are calendars with attractions. RoamAI treats the
outdoors as the star and weather as the constraint that makes planning
interesting:

- **Weather-aware scheduling** — outdoor activities avoid forecasted rain
- **Air-quality-aware** — outdoor runs avoid high-AQI windows
- **Semantic activity matching** — "peaceful morning outside" finds a
  quiet-cove snorkel, not a hotel spa
- **Full-trip context** — agent knows all your other days when
  suggesting each one
- **Auto-adaptive** — forecast changes → itinerary changes, with a
  clear explanation

---

## Tech stack

- **Frontend** — Streamlit (deployed as a Databricks App)
- **AI agent** — Databricks Agent Bricks with external MCP tool source
- **MCP server** — FastMCP over HTTP (deployed as a Databricks App)
- **Database** — Databricks Lakebase (managed PostgreSQL + pgvector)
- **Embeddings** — `sentence-transformers/all-MiniLM-L6-v2` (384-dim)
- **APIs** — Open-Meteo (geocoding, weather, air quality) + Wikimedia
- **Compute** — Databricks serverless notebook compute

---

## Architecture

```
User
  │
  ├──► Streamlit Dashboard (Databricks App #1)
  │       Trip management UI — create trips, view itineraries, packing
  │       │
  │       │ SQL queries + inserts
  │       ▼
  │    Lakebase Postgres (7 tables + pgvector for semantic search)
  │       ▲
  │       │
  └──► Agent Bricks chat interface
          │
          │ Tool calls over HTTP
          ▼
       MCP Server (Databricks App #2)
          │
          │ Reads + writes
          ▼
       Lakebase Postgres  ← same database, shared state
```

Two Databricks Apps + one AI Agent + one shared Lakebase database.

---

## Repo structure

```
roam-ai/
├── README.md                           # this file
├── app.py                              # Streamlit dashboard
├── app.yaml                            # Databricks App config for dashboard
├── lakebase.py                         # Postgres connection helper
├── trip_client.py                      # Open-Meteo + Wikipedia HTTP client
├── requirements.txt
├── setup_secrets.py                    # One-time Lakebase URL setup
├── .env.example
├── .gitignore
│
├── sql/                                # 7 Lakebase table DDL files
│   ├── 01_setup_users_table.sql
│   ├── 02_setup_trips_table.sql
│   ├── 03_setup_destinations_table.sql
│   ├── 04_setup_activities_table.sql
│   ├── 05_setup_itinerary_items_table.sql
│   ├── 06_setup_weather_snapshots_table.sql
│   ├── 07_setup_packing_items_table.sql
│   └── README.md
│
├── notebooks/                          # Ingestion + embedding
│   ├── ingest_destinations_pipeline.py # Wikipedia + geocode → Lakebase
│   └── embed_pipeline.py               # Chunk + embed → pgvector
│
├── mcp_server/                         # FastMCP server (Databricks App #2)
│   ├── trip_mcp_server.py              # 7 tools (5 write + 2 read)
│   ├── trip_broker.py                  # Business logic + API helpers
│   ├── lakebase.py                     # Copy of root lakebase.py
│   ├── app.yaml
│   ├── requirements.txt
│   └── README.md
│
├── agent/                              # Agent Bricks configuration
│   ├── README.md                       # Wiring instructions
│   ├── system_prompt.md                # Verbatim configured prompt
│   └── screenshots/                    # Config + behavior evidence
│
└── docs/
    └── DEPLOYMENT_ISSUES.md            # Lessons learned during deployment
```

---

## What the agent can do

1. **Generate a day-by-day itinerary** — given destination + interests + dates
2. **Reschedule outdoor activities** when rain or poor air quality is forecast
3. **Build a packing list** based on trip length, weather, and activities
4. **Add, remove, or move itinerary items** — modify trip plans conversationally
5. **Explain weather-based changes** — tell you WHY each rescheduling happened

Backed by 7 MCP tools (5 write + 2 read) that call semantic search over
embedded destinations and activities.

---

## Getting started

### Prerequisites

- A Databricks workspace with Apps enabled
- A Lakebase (Databricks-managed Postgres) instance with `pgvector` enabled
- Lakebase URL stored in Databricks secret `database/lakebase-url`
  (already set up from Day 2 — no action needed)

### Setup

Create the 7 Lakebase tables by running each `sql/*.sql` file in the
Databricks SQL editor, in order. See `sql/README.md` for details.

### Run the Day 1 notebook

Open `notebooks/ingest_destinations_pipeline.py` in Databricks. Attach
to serverless compute. Run all cells. Confirms:
---



---

## Known limitations & future work

- **Single-user model.** No auth/groups. User identified by
  `X-Forwarded-User` header (from Databricks App runtime).
- **One destination per trip.** Multi-city trips would need a
  `trip_legs` table; out of scope for this capstone.
- **No caching.** Every agent tool call hits the upstream API (fine for
  personal use; wouldn't scale to production traffic).
- **Static activity library.** Activities extracted from Wikipedia +
  seed data. No user-feedback loop for recommendation improvement.
