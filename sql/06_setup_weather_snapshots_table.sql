-- Cached weather + air quality forecasts per destination per date.
-- The Spark ingestion job populates this daily; the agent reads from it
-- instead of hitting Open-Meteo on every tool call.

CREATE TABLE IF NOT EXISTS weather_snapshots (
    id                BIGSERIAL PRIMARY KEY,
    destination_id    BIGINT NOT NULL REFERENCES destinations(id) ON DELETE CASCADE,
    forecast_date     DATE NOT NULL,
    temp_high_f       NUMERIC(5,1),
    temp_low_f        NUMERIC(5,1),
    precip_chance_pct INT,
    precip_amount_in  NUMERIC(5,2),
    wind_mph          NUMERIC(5,1),
    conditions        TEXT,                             -- WMO code translated to text
    aqi               INT,                              -- US EPA air quality index
    uv_max            NUMERIC(4,1),
    raw_payload       JSONB,                            -- full API response for debugging
    fetched_at        TIMESTAMP DEFAULT NOW(),
    UNIQUE (destination_id, forecast_date)
);

CREATE INDEX IF NOT EXISTS idx_weather_dest_date
    ON weather_snapshots(destination_id, forecast_date);
