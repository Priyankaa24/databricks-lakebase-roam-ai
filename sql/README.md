# SQL Schema

Seven tables in Lakebase (Postgres + pgvector) supporting the RoamAI
trip planner data model.

## Run order

Run each file top-to-bottom in the Databricks SQL editor. Files 2-7
depend on foreign keys defined in earlier files, so ordering matters.

1. `01_setup_users_table.sql` — Users + seed row (Priyankaa)
2. `02_setup_trips_table.sql` — Trips owned by users
3. `03_setup_destinations_table.sql` — One destination per trip; enables pgvector
4. `04_setup_activities_table.sql` — Activities available at each destination
5. `05_setup_itinerary_items_table.sql` — Day-by-day schedule
6. `06_setup_weather_snapshots_table.sql` — Cached forecasts per destination + date
7. `07_setup_packing_items_table.sql` — Packing list per trip

## Design decisions

- **Single-user model.** `users` has no groups/team concept. Trip Planner
  spec doesn't require groups (unlike MovieNight Option 1). Simplifies
  the write tools significantly.
- **One destination per trip.** Simplifies day-by-day scheduling — the
  `itinerary_items.day_number` unambiguously maps to a date within one
  trip's date range. Multi-city trips would need a separate `trip_legs`
  table; out of scope for this iteration.
- **`weather_sensitive` flag on activities.** This is what powers the
  "reschedule when it rains" feature. Outdoor activities set this to
  TRUE; indoor backups (museums, dining) leave it FALSE.
- **Embeddings on destinations AND activities.** 384-dim vectors from
  `sentence-transformers/all-MiniLM-L6-v2` (matches the embedding model
  used elsewhere in the pipeline, so we
  can reuse the ingestion notebook pattern). HNSW cosine index on both.
- **`weather_snapshots` is a cache, not source of truth.** Populated by
  the ingestion notebook. The agent reads from here for speed. If a date
  isn't in the cache, the agent hits Open-Meteo directly.
- **`packing_items.reasoning`** exists so the agent can explain why it
  suggested each item ("rain expected Fri" → "waterproof jacket").

## Verifying setup

After running all 7 files, verify with:

```sql
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name IN (
      'users', 'trips', 'destinations', 'activities',
      'itinerary_items', 'weather_snapshots', 'packing_items'
  )
ORDER BY table_name;
```

You should see 7 rows. Then:

```sql
SELECT * FROM users;
```

Should return one row (the seeded user).
