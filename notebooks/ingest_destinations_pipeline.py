# Databricks notebook source
# MAGIC %md
# MAGIC # Day 1 — RoamAI proof of life
# MAGIC
# MAGIC Goal: prove the API layer works end-to-end and land your first
# MAGIC trip + destination in Lakebase.
# MAGIC
# MAGIC Steps:
# MAGIC 1. Confirm the SQL tables exist (should already be done via `sql/*.sql`)
# MAGIC 2. Geocode Kauai via Open-Meteo
# MAGIC 3. Fetch Kauai's Wikipedia summary
# MAGIC 4. Insert a Kauai trip + destination into Lakebase
# MAGIC 5. Verify with a SELECT query

# COMMAND ----------
# MAGIC %pip install -r /Workspace/Users/rajendrannpriyankaa24@gmail.com/roam-ai/requirements.txt --quiet
# MAGIC dbutils.library.restartPython()

# COMMAND ----------
# MAGIC %md
# MAGIC ## Step 1 — Verify all 7 Lakebase tables exist

# COMMAND ----------
import sys
sys.path.insert(0, "/Workspace/Users/rajendrannpriyankaa24@gmail.com/roam-ai")

import lakebase

rows = lakebase.run_query("""
    SELECT table_name
    FROM information_schema.tables
    WHERE table_schema = 'public'
      AND table_name IN (
          'users', 'trips', 'destinations', 'activities',
          'itinerary_items', 'weather_snapshots', 'packing_items'
      )
    ORDER BY table_name
""")
print(f"Found {len(rows)} tables:")
for r in rows:
    print(f"  - {r['table_name']}")

assert len(rows) == 7, "Expected 7 tables. Run all files in sql/ first."
print("\nAll 7 tables present.")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Step 2 — Geocode Kauai via Open-Meteo

# COMMAND ----------
import trip_client

geo = trip_client.geocode("Kauai")
print(f"Location: {geo['name']}, {geo.get('admin1')}, {geo['country']}")
print(f"Latitude:  {geo['latitude']}")
print(f"Longitude: {geo['longitude']}")
print(f"Timezone:  {geo['timezone']}")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Step 3 — Fetch Kauai's Wikipedia summary

# COMMAND ----------
wiki = trip_client.get_wikipedia_summary("Kauai")
print(f"Title: {wiki['title']}")
print(f"URL:   {wiki['url']}")
print(f"\nExtract (first 500 chars):")
print(wiki['extract'][:500])
print("...")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Step 4 — Insert Kauai trip + destination into Lakebase

# COMMAND ----------
# Get the seeded user's ID
user_rows = lakebase.run_query(
    "SELECT id FROM users WHERE email = %s",
    ('rajendrannpriyankaa24@gmail.com',),
)
user_id = user_rows[0]['id']
print(f"User ID: {user_id}")

# COMMAND ----------
# Create the Kauai trip (Dec 22-28, 2026)
trip_rows = lakebase.run_query(
    """
    INSERT INTO trips (user_id, name, start_date, end_date, notes)
    VALUES (%s, %s, %s, %s, %s)
    RETURNING id
    """,
    (user_id, 'Kauai Dec 2026', '2026-12-22', '2026-12-28',
     'First RoamAI test trip - real vacation'),
)
trip_id = trip_rows[0]['id']
print(f"Trip ID: {trip_id}")

# COMMAND ----------
# Insert Kauai as the trip's destination
# NOTE: description_embedding is left NULL for now.
# The Day 2 embedding pipeline will populate it.
dest_rows = lakebase.run_query(
    """
    INSERT INTO destinations (
        trip_id, name, country, admin1,
        latitude, longitude, timezone,
        description, wikipedia_url
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    RETURNING id
    """,
    (
        trip_id,
        geo['name'],
        geo['country'],
        geo.get('admin1'),
        geo['latitude'],
        geo['longitude'],
        geo['timezone'],
        wiki['extract'],
        wiki['url'],
    ),
)
dest_id = dest_rows[0]['id']
print(f"Destination ID: {dest_id}")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Step 5 — Verify with a JOIN query

# COMMAND ----------
verify = lakebase.run_query("""
    SELECT
        u.email        AS user_email,
        t.name         AS trip_name,
        t.start_date,
        t.end_date,
        d.name         AS destination,
        d.country,
        d.latitude,
        d.longitude,
        LEFT(d.description, 200) AS description_preview,
        d.wikipedia_url
    FROM users u
    JOIN trips t        ON t.user_id = u.id
    JOIN destinations d ON d.trip_id = t.id
    WHERE t.id = %s
""", (trip_id,))

if verify:
    row = verify[0]
    print(f"User:         {row['user_email']}")
    print(f"Trip:         {row['trip_name']}")
    print(f"Dates:        {row['start_date']} to {row['end_date']}")
    print(f"Destination:  {row['destination']}, {row['country']}")
    print(f"Coordinates:  ({row['latitude']}, {row['longitude']})")
    print(f"Wikipedia:    {row['wikipedia_url']}")
    print(f"\nDescription preview:")
    print(row['description_preview'] + "...")
    print("\nDay 1 complete. Ready for Day 2.")
else:
    print("Verification failed - no rows returned.")
