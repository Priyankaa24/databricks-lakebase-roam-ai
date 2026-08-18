# RoamAI

**AI trip planner that adapts to the weather.**

RoamAI is an end-to-end trip planning application where an AI agent
builds day-by-day itineraries from live weather forecasts, air quality
data, and semantic search over destination attractions — then
reschedules outdoor activities automatically when the forecast changes.

Built on Databricks — combines a Lakebase Postgres data layer,
pgvector semantic search, a PySpark analytics pipeline, a Streamlit
dashboard, and an Agent Bricks agent backed by 8 MCP tools.

---

## Project requirements — how each is met

| Requirement | Implementation |
|---|---|
| **Data pipeline in Spark** | `notebooks/analyze_activities_spark.ipynb` — PySpark JDBC read → aggregations by category and destination → JDBC write of an `activity_analytics` table back to Lakebase |
| **Third-party API integration** | Four APIs: Open-Meteo Geocoding, Open-Meteo Weather Forecast, Open-Meteo Air Quality, Wikipedia REST. All wired in `trip_client.py` and `mcp_server/trip_broker.py` |
| **Unstructured data processing** | Wikipedia destination summaries + activity descriptions (raw prose) → embedded via `sentence-transformers/all-MiniLM-L6-v2` into 384-dim vectors → stored in Lakebase pgvector columns with HNSW cosine indexes for semantic retrieval |
| **Databricks App with frontend** | Streamlit dashboard (`app.py`) deployed as a Databricks App — trip list, new trip form, trip detail with itinerary/weather/packing tabs, semantic activity search |
| **AI agent with tools** | Databricks Agent Bricks agent connected to a FastMCP server (deployed as a second Databricks App) exposing 8 tools — 2 reads (`get_trip`, `search_activities`) and 6 writes (`add_destination`, `build_itinerary`, `add_itinerary_item`, `remove_itinerary_item`, `reschedule_for_weather`, `build_packing_list`) |

---

## What makes it weather-aware

Most trip planners are calendars with attractions. RoamAI treats the
outdoors as the star and weather as the constraint that makes planning
interesting:

- **Weather-aware scheduling** — outdoor activities avoid forecasted rain
- **Air-quality-aware** — outdoor activities avoid high-AQI windows
- **Semantic activity matching** — "peaceful morning outside" finds a
  quiet-cove snorkel, not a hotel spa
- **Full-trip context** — agent knows all your other days when
  suggesting each one
- **Auto-adaptive** — forecast changes → itinerary changes, with a
  clear per-day explanation

---

## Architecture

```
User
  │
  ├──► Streamlit Dashboard (Databricks App)
  │       Trip management UI — browse trips, view itinerary,
  │       check weather + packing list, semantic activity search
  │       │
  │       │ SQL queries + inserts
  │       ▼
  │    Lakebase Postgres (7 tables + pgvector for semantic search)
  │       ▲
  │       │
  └──► Agent Bricks chat interface
          │
          │ Tool calls over HTTP (MCP protocol)
          ▼
       MCP Server (Databricks App)
          │  Calls Open-Meteo (geocode, weather, AQI) + Wikipedia
          │  Encodes queries into 384-dim vectors on the fly
          │  Reads + writes across all 7 tables
          ▼
       Lakebase Postgres  ← same database, shared state
          │
          │ Batch analytics (scheduled or ad-hoc)
          ▼
       PySpark notebook — reads via JDBC, aggregates, writes
       activity_analytics table
```

Two Databricks Apps + one AI Agent + one PySpark notebook + one shared
Lakebase database.

---

## Tech stack

- **Frontend** — Streamlit deployed as a Databricks App
- **AI agent** — Databricks Agent Bricks (Meta Llama 3.3 70B Instruct) with external MCP tool source
- **MCP server** — FastMCP over HTTP, deployed as a Databricks App
- **Database** — Databricks Lakebase (managed Postgres) with `pgvector`
- **Embeddings** — `sentence-transformers/all-MiniLM-L6-v2` (384-dim)
- **Vector index** — HNSW with cosine similarity
- **Analytics** — PySpark via JDBC (native Databricks compute)
- **External APIs** — Open-Meteo (geocoding, weather, air quality) + Wikipedia REST
- **Observability** — every MCP tool call logged to `mcp_tool_traces_roam` (session id, user, tool, params, result, duration, success/error)

---

## Data model

```
users
  └── trips
        ├── destinations (with description + description_embedding VECTOR(384))
        │     └── activities (with description + description_embedding VECTOR(384))
        │           └── itinerary_items (with weather_adjusted flag + adjustment_reason)
        ├── weather_snapshots (cached per destination + date)
        └── packing_items (with generated_by + reasoning)
```

Plus two operational tables:
- `activity_analytics` — materialized by the PySpark pipeline
- `mcp_tool_traces_roam` — every agent tool call, auto-created by the MCP server

---

## Repo structure

```
databricks-lakebase-roam-ai/
├── README.md                           # this file
├── app.py                              # Streamlit dashboard
├── app.yaml                            # Databricks App config for dashboard
├── lakebase.py                         # Postgres connection helper (psycopg v3)
├── trip_client.py                      # Open-Meteo + Wikipedia HTTP client
├── requirements.txt
├── setup_secrets.py                    # One-time Lakebase URL secret setup
├── .env.example
├── .gitignore
│
├── sql/                                # Table DDL + seed data
│   ├── 01_setup_users_table.sql
│   ├── 02_setup_trips_table.sql
│   ├── 03_setup_destinations_table.sql
│   ├── 04_setup_activities_table.sql
│   ├── 05_setup_itinerary_items_table.sql
│   ├── 06_setup_weather_snapshots_table.sql
│   ├── 07_setup_packing_items_table.sql
│   ├── 08_seed_kauai_activities.sql    # 15 Kauai activities
│   └── README.md
│
├── notebooks/
│   ├── analyze_activities_spark.ipynb  # PySpark analytics pipeline
│   ├── ingest_destinations_pipeline.ipynb  # Reference implementation
│   ├── embed_pipeline.ipynb                # Reference implementation
│   └── embed_activities.ipynb          # Runs sentence-transformers in Google Colab
│
└── mcp_server/                         # FastMCP server (Databricks App)
    ├── trip_mcp_server.py              # 8 MCP tools + tracing
    ├── trip_broker.py                  # Business logic + API helpers
    ├── lakebase.py                     # Copy of root lakebase.py (self-contained)
    ├── app.yaml
    ├── requirements.txt
    └── README.md
```

---

## The 8 MCP tools

### Reads

| Tool | Purpose |
|---|---|
| `get_trip(trip_id)` | Full trip state — destination, itinerary, packing list |
| `search_activities(query, destination_id, limit)` | Semantic search over activity descriptions |

### Writes

| Tool | Purpose |
|---|---|
| `add_destination(destination_name, trip_id)` | Onboard a destination — geocode via Open-Meteo, fetch Wikipedia summary, embed the description |
| `build_itinerary(trip_id, interests, activities_per_day)` | Generate a day-by-day plan, weather-aware |
| `add_itinerary_item(...)` | Add a single itinerary entry |
| `remove_itinerary_item(item_id)` | Delete an itinerary entry |
| `reschedule_for_weather(trip_id)` | Move outdoor activities off rainy or high-AQI days, explain why |
| `build_packing_list(trip_id)` | Generate packing recommendations based on trip length, activities, and weather |

See `mcp_server/README.md` for full deployment and wiring instructions.

---

## Unstructured data processing

The RAG pipeline runs on Wikipedia destination summaries and detailed
activity descriptions — pure prose with no schema.

**Extraction:** `trip_client.get_wikipedia_summary(name)` calls the
Wikipedia REST API for each destination and pulls the intro paragraph
(~500-1500 characters).

**Preprocessing:** each description is passed to
`sentence-transformers/all-MiniLM-L6-v2` which tokenizes the text and
produces a fixed-size 384-dimensional dense embedding capturing the
semantic meaning of the text.

**Storage:** embeddings are written to `description_embedding VECTOR(384)`
columns in Lakebase. Both `destinations` and `activities` tables have
this column, indexed with HNSW for cosine similarity search.

**Retrieval:** the `search_activities` MCP tool and the Streamlit
"Discover Activities" page both encode natural-language queries into
the same 384-dim space and use `<=>` (pgvector cosine distance) to
find the nearest neighbours.

Example: a query for *"peaceful morning near the water"* ranks
`Anini Beach` and `Wailua River Kayak` at the top even though neither
description uses the words "peaceful" or "morning" — semantic retrieval,
not keyword matching.

**Total embeddings:** 16 (1 destination + 15 activities). All generated
via the workflow in `notebooks/embed_activities.ipynb` (Colab notebook).

---

## PySpark data pipeline

`notebooks/analyze_activities_spark.ipynb` implements a real extract →
transform → load pipeline:

**Extract** — reads the `activities` table from Lakebase via Spark JDBC
(`spark.read.format("jdbc")`).

**Transform** — two aggregations using PySpark DataFrame operations:

1. **By category** — `count(*)`, `avg(duration_hours)`, sum of outdoor
   vs indoor activities per category
2. **By destination** — total activities, percentage that are
   weather-sensitive, average duration, and `collect_set(category)`
   for the category array

The two aggregations are unioned into a wide-form analytics DataFrame
with a `dimension` column indicating whether each row is a per-category
or per-destination summary.

**Load** — writes the analytics DataFrame back to Lakebase as a new
`activity_analytics` table via Spark JDBC in overwrite mode.

**Verify** — reads the analytics table back to confirm the round trip.

The pipeline is idempotent and would scale to millions of rows if the
activities dataset grew. In production it would run on a scheduled
Databricks Workflow.

---

## Setup

### Prerequisites

- A Databricks workspace with Apps enabled
- A Lakebase (Databricks-managed Postgres) instance with `pgvector` extension
- Lakebase URL stored in Databricks secret `database/lakebase-url`

### Step 1 — Create the tables

Run each `sql/01` through `sql/07` file in the Databricks SQL Editor,
in order. See `sql/README.md` for details.

### Step 2 — Seed activities

Run `sql/08_seed_kauai_activities.sql` in the SQL Editor. Inserts 15
Kauai activities (12 outdoor + 3 indoor) with `description_embedding = NULL`.

### Step 3 — Embed destinations + activities

Open `notebooks/embed_activities.ipynb` in Google Colab. Run all cells.
Copy the generated UPDATE SQL statements into the Databricks SQL
Editor and run them to populate all 16 embeddings.

(In an environment with proper Python compute, `notebooks/embed_pipeline.ipynb`
would do this directly against Lakebase. See "Environment notes" below
for why Colab is used on Databricks Free Edition.)

### Step 4 — Deploy the MCP server

1. Databricks → Compute → Apps → Create app → Custom app
2. Source path: `/Workspace/Users/<you>/databricks-lakebase-roam-ai/mcp_server`
3. Deploy — takes ~2 min for first-time pip install
4. Copy the app URL — needed for Agent Bricks

### Step 5 — Deploy the Streamlit dashboard

1. Databricks → Compute → Apps → Create app → Custom app
2. Source path: `/Workspace/Users/<you>/databricks-lakebase-roam-ai`
   (repo root — `app.yaml` for Streamlit lives at root)
3. Deploy

### Step 6 — Configure the Agent Bricks agent

1. Databricks → Agent Bricks → Create agent
2. Add MCP tools → paste the MCP server URL from Step 4
3. System prompt — a version is included that tells the agent about
   the 8 tools, the current user's trip context, and usage rules
4. Test with the prompts in "Agent test prompts" below

### Step 7 — Run the PySpark analytics pipeline

Open `notebooks/analyze_activities_spark.ipynb` in Databricks. Attach
to Serverless compute. Run all cells. Populates the `activity_analytics`
table.

---

## Agent test prompts

Prompts used to verify each tool works end-to-end:

1. **`get_trip`** — *"I have a trip to Kauai in December. Show me what's planned."*
2. **`build_itinerary`** — *"Build me a day-by-day itinerary for my Kauai trip. I love hiking, snorkeling, quiet beaches, and peaceful outdoor time. About 2 activities per day."*
3. **`reschedule_for_weather`** — *"Some of my Kauai days might have bad weather. Please look at the forecast and reschedule outdoor activities off rainy or high-AQI days. Explain what you moved and why."*
4. **`build_packing_list`** — *"Generate a packing list for my Kauai trip based on the itinerary and weather forecast."*
5. **`add_destination`** — *"Add Kyoto as an additional destination for my trip (trip_id=1). Geocode it, fetch the Wikipedia summary, and embed it."*
6. **`search_activities` (bonus)** — *"What activities on Kauai are best for peaceful outdoor time near the water?"*

---

## Environment notes

This project targets Databricks as the primary runtime. Some steps
have workarounds specific to the **Databricks Free Edition** tier
(Serverless-only compute):

- **`psycopg2-binary` crashes on Serverless** (SIGABRT 134) due to
  missing PostgreSQL client system libraries. Switched to `psycopg` v3
  (`psycopg[binary]`) which is more permissive.
- **`sentence-transformers` cannot load reliably on Serverless
  notebooks** — the ~800MB torch install + 90MB model download exceeds
  the runtime's tolerances. Embedding generation was moved to Google
  Colab (see `colab/embed_activities.ipynb`), with results pasted back
  into Databricks SQL Editor as UPDATE statements. On a Classic
  cluster or paid Serverless tier, `notebooks/embed_pipeline.ipynb`
  would run directly against Lakebase.
- **FastMCP tools cannot use `**kwargs` in their signature** — the
  first version of the `traced` decorator used `def wrapper(**kwargs)`,
  which FastMCP rejects because it can't determine the tool's schema.
  Fixed by using `functools.wraps` so FastMCP inspects the wrapped
  function's real signature.
- **Open-Meteo Air Quality API only supports hourly variables**, not
  daily. The first version of `get_air_quality` sent `daily=us_aqi`,
  which returned 400. Fixed by fetching hourly data and aggregating
  to daily max in the client.

Databricks Apps (both the MCP server and the dashboard) have a
proper Python runtime and don't hit the Serverless notebook restrictions
— once deployed, everything runs cleanly.

---

## Known limitations & future work

- **Single-user model.** No auth or groups; user identified by
  `X-Forwarded-User` header (from Databricks App runtime).
- **No `create_trip` MCP tool.** `add_destination` requires an existing
  `trip_id`. Users create trips via the Streamlit dashboard's "New
  Trip" page or via SQL. Adding a `create_trip` tool would let the
  agent handle *"plan me a trip to Kyoto"* end-to-end.
- **Activities pre-seeded for Kauai only.** `add_destination` onboards
  new destinations dynamically, but activities are still curated per
  destination. Auto-generating activities via LLM extraction from
  Wikipedia would close this gap.
- **Weather cache never expires.** `cache_weather_for_trip` upserts on
  `(destination_id, forecast_date)` but doesn't track freshness. A
  scheduled job would refresh caches near trip dates.
- **No user feedback loop.** Which suggested activities were accepted
  or rejected isn't captured, so recommendations don't improve over
  time.
- **`reschedule_for_weather` swaps within a trip only.** Never creates
  net-new items or reaches for activities from other destinations.

---

## Credits

- **Weather + air quality data:** [Open-Meteo](https://open-meteo.com/) (CC BY 4.0)
- **Destination summaries:** [Wikipedia](https://www.wikipedia.org/) (CC BY-SA)
- **Embedding model:** [`sentence-transformers/all-MiniLM-L6-v2`](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2)
