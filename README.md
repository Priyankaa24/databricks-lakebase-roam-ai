# RoamAI

**AI outdoor trip planner that adapts to the weather.**

RoamAI is a trip-planning app where an AI agent builds day-by-day
itineraries from live weather forecasts, air quality data, and semantic
search over destination attractions — then reschedules outdoor
activities automatically when the forecast changes.
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

- **Backend** — Python, Flask, FastMCP
- **Database** — PostgreSQL (Databricks Lakebase) with pgvector
- **Warehouse** — Delta tables in Unity Catalog (bronze / silver / gold)
- **Embeddings** — `sentence-transformers/all-MiniLM-L6-v2` (384-dim)
- **Live data** — Open-Meteo (geocoding + weather + air quality) + Wikimedia
- **Compute** — Databricks serverless notebook compute + Databricks Workflows
- **Frontend** — Databricks Genie over Gold Delta tables
- **AI** — Databricks Agent Bricks with external MCP tool
- **Change data feed** — Lakebase → Delta CDF for analytics

---

## Capstone requirements coverage

| # | Requirement | Where |
|---|---|---|
| 1 | Spark data pipeline | `notebooks/*.py` scheduled via `resources/*.yml` |
| 2 | Third-party API integration | `trip_client.py` (Open-Meteo + Wikipedia) |
| 3 | Unstructured data processing | `notebooks/embed_destinations.py` chunks + embeds Wikipedia text |
| 4 | Databricks App frontend | Genie dashboard configured over Gold Delta tables (`genie/`) |
| 5 | AI agent with read + write tools | `mcp_server/` (10+ tools, deployed as Databricks App) |
| 6 | All prod data in Unity Catalog | Delta tables in `roam_ai.bronze/silver/gold`; Lakebase Postgres for live app state; CDF sync from Lakebase → Delta |

---

## Repo structure

```
roam-ai/
├── README.md                           # this file
├── app.py                              # Flask app (trip management UI)
├── app.yaml                            # Databricks App config for Flask
├── lakebase.py                         # Postgres helper (shared)
├── trip_client.py                      # HTTP client for Open-Meteo + Wikipedia
├── requirements.txt
├── setup_secrets.py
├── databricks.yml
├── .env.example
├── .gitignore
│
├── sql/                                # DDL for all tables
│   ├── 01_setup_users_table.sql
│   ├── 02_setup_trips_table.sql
│   ├── 03_setup_destinations_table.sql
│   ├── 04_setup_activities_table.sql
│   ├── 05_setup_itinerary_items_table.sql
│   ├── 06_setup_weather_snapshots_table.sql
│   ├── 07_setup_packing_items_table.sql
│   ├── 08_setup_analytics_delta.sql    # Delta tables + CDF
│   └── README.md
│
├── notebooks/                          # Spark ingestion + embedding
│   ├── ingest_destinations_pipeline.py # Wikipedia + geocoding → Lakebase
│   └── embed_destinations.py           # Chunk + embed → Lakebase pgvector
│
├── resources/                          # Databricks Workflow YAMLs
│   └── (job schedules)
│
├── templates/                          # Flask templates
│   ├── index.html
│   └── trip_detail.html
│
├── mcp_server/                         # Databricks App: MCP server
│   ├── trip_mcp_server.py
│   ├── trip_broker.py
│   ├── lakebase.py
│   ├── app.yaml
│   ├── requirements.txt
│   └── README.md
│
├── agent/                              # Agent Bricks configuration
│   ├── README.md
│   ├── system_prompt.md
│   └── screenshots/
│
├── genie/                              # Genie frontend config
│   ├── README.md
│   └── sample_questions.md
│
└── docs/
    ├── architecture.md
    └── DEPLOYMENT_ISSUES.md
```

---

## Getting started

### Prerequisites

- A Databricks workspace with Apps enabled
- A Lakebase (Databricks-managed Postgres) instance with `pgvector` enabled
- The Lakebase connection URL stored at Databricks secret `database/lakebase-url`
  (already set up from Day 2 — no action needed)

### One-time setup

If `database/lakebase-url` doesn't already exist:

```bash
python setup_secrets.py
```

Then create the 7 Lakebase tables by running each `sql/*.sql` file in
the Databricks SQL editor, in order. See `sql/README.md` for details.

### Run the Day 1 notebook

Open `notebooks/ingest_destinations_pipeline.py` in Databricks. Attach
to serverless compute. Run all cells. Confirms:

- All 7 tables exist
- Open-Meteo geocoding works
- Wikipedia API works
- First trip + destination lands in Lakebase

---

## Roadmap

- [x] Day 1 — Lakebase schema + API integration
- [ ] Day 2 — Spark pipeline: Wikipedia → Delta (bronze/silver/gold)
- [ ] Day 3 — Embedding pipeline (destinations + activities → pgvector)
- [ ] Day 4 — MCP server with read + write tools
- [ ] Day 5 — Databricks App frontend + CDF setup
- [ ] Day 6 — Agent Bricks setup + end-to-end test
- [ ] Day 7 — README polish + submission

---

## Known limitations & future work

- **Single-user model.** No auth/groups. User identified by `X-Forwarded-User` header.
- **One destination per trip.** Multi-city trips would need a `trip_legs` table.
- **NWS alerts are US-only.** International severe-weather alerts unsupported.
- **No caching.** Every agent tool call hits the upstream API (fine for personal use, wouldn't scale to production).
- **Static recommendation rules.** Activity suggestions come from Wikipedia + LLM inference, not user feedback loops.
