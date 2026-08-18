# RoamAI MCP Server

FastMCP server exposing 7 trip-planning tools to a Databricks Agent
Bricks agent. Deployed as a Databricks App; wired to the agent as an
external MCP tool source.

---

## The 7 tools

### Reads

| Tool | Purpose |
|---|---|
| `get_trip(trip_id)` | Full trip state: destination, itinerary, packing list |
| `search_activities(query, destination_id, limit=5)` | Semantic search over activity descriptions |

### Writes

| Tool | Purpose |
|---|---|
| `build_itinerary(trip_id, interests, activities_per_day=2)` | Generate a full day-by-day plan, weather-aware |
| `add_itinerary_item(trip_id, activity_id, day, date, time_slot, notes)` | Add a single itinerary entry |
| `remove_itinerary_item(item_id)` | Delete an itinerary entry |
| `reschedule_for_weather(trip_id)` | Move outdoor activities off rainy days, explain why |
| `build_packing_list(trip_id)` | Generate packing recommendations based on trip + weather + activities |

---

## What each tool does

**`get_trip`** — Returns everything the agent needs to reason about a
trip: name, dates, destination (with lat/lon), itinerary items grouped
by date, and current packing list. Should be the agent's first call
whenever the user references a trip.

**`search_activities`** — Encodes the natural-language `query` into a
384-dim vector via sentence-transformers, then finds the closest
activities in Lakebase pgvector using cosine similarity. Powers all
suggestion logic.

**`build_itinerary`** — The big one. Fetches the trip's forecast into
`weather_snapshots`, gets a list of activities matching `interests`,
splits them into outdoor vs indoor, and assigns items to days —
avoiding scheduling outdoor activities on rainy or high-AQI days.
Writes to `itinerary_items`.

**`add_itinerary_item`** — Manual single-item add. Used when the user
wants to add one specific activity.

**`remove_itinerary_item`** — Delete by id. Used when the user drops
something from the plan.

**`reschedule_for_weather`** — The impressive demo. Reads the current
itinerary, refreshes the forecast, and moves outdoor activities off
bad-weather days by swapping with items on good-weather days. Sets
`weather_adjusted = TRUE` and stores the reason. The agent can then
tell the user why each change was made.

**`build_packing_list`** — Rule-based generation. Trip length →
clothes count. Hiking activities → hiking gear. Beach activities →
swim gear + sunscreen. Rainy forecast → waterproof jacket. Each item
stored with a `reasoning` string for the agent to explain.

---

## Observability

Every tool call is logged to `mcp_tool_traces_roam` in Lakebase:

```sql
SELECT tool_name, COUNT(*) AS calls, AVG(duration_ms)::int AS avg_ms
FROM mcp_tool_traces_roam
WHERE created_at > NOW() - INTERVAL '1 day'
GROUP BY tool_name
ORDER BY calls DESC;
```

Fields captured: session id, user email (from `X-Forwarded-User`),
parameters, result, duration, success/failure, error.

---

## Deploying as a Databricks App

Prerequisites:
- Lakebase URL stored at Databricks secret `database/lakebase-url`
- 7 tables created (see `../sql/`)
- Kauai destination + 15 activities embedded (see `../sql/08_seed_kauai_activities.sql` + `../colab/embed_activities.ipynb`)

Steps:

1. **Push this folder to your GitHub repo** (should already be there
   via a git folder sync).

2. **In Databricks:** Compute → Apps → **Create app**.

3. **Choose "Custom App"** (Bring your own code).

4. **Point at this folder:**
   `/Workspace/Users/rajendrannpriyankaa24@gmail.com/roam-ai/mcp_server`

   The folder MUST contain `app.yaml` at its root.

5. **App name:** `roam-ai-mcp` (or your preference).

6. **Deploy.** First deploy takes 2-3 minutes (pip install).

7. **Copy the deployed URL** — you'll paste it into Agent Bricks next.

---

## Wiring up Agent Bricks

1. Left sidebar → **Agent Bricks** (or "AI/BI → Agents").
2. **Create new agent** named "RoamAI Trip Planner".
3. **Add MCP tools:** paste the deployed URL from above.
4. **Configure system prompt:** see `../agent/system_prompt.md`.
5. **Test in the playground** with prompts like:
   - "Build me an itinerary for my Kauai trip"
   - "It's supposed to rain on the 24th — can you reschedule outdoor stuff?"
   - "Generate a packing list for my Kauai trip"

---

## Known operational notes

- **First tool call is slow.** The sentence-transformers model
  downloads on first request (~30 sec, ~90 MB). Subsequent calls are
  fast.
- **`build_itinerary` is destructive.** It appends to
  `itinerary_items`; if you re-run it on the same trip you'll get
  duplicates. In production you'd add an "existing items" check.
- **`reschedule_for_weather` is limited to the same trip.** It swaps
  days within a trip but never creates net-new items.
- **Trace table is auto-created** on first successful call
  (`mcp_tool_traces_roam`). If you get "must be owner" errors on
  startup, ignore — the try/except handles it.
