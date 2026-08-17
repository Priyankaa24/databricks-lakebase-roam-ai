-- The actual day-by-day schedule. Links an activity to a specific day
-- of a trip. `weather_adjusted` + `adjustment_reason` track when the
-- agent moves an item due to weather so we can show that in the UI.

CREATE TABLE IF NOT EXISTS itinerary_items (
    id                BIGSERIAL PRIMARY KEY,
    trip_id           BIGINT NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
    activity_id       BIGINT REFERENCES activities(id) ON DELETE SET NULL,
    day_number        INT NOT NULL,                     -- 1 = first day of trip
    scheduled_date    DATE NOT NULL,
    time_slot         VARCHAR(32),                      -- morning, afternoon, evening, or HH:MM
    notes             TEXT,
    weather_adjusted  BOOLEAN DEFAULT FALSE,
    adjustment_reason TEXT,
    created_at        TIMESTAMP DEFAULT NOW(),
    updated_at        TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_itinerary_trip           ON itinerary_items(trip_id);
CREATE INDEX IF NOT EXISTS idx_itinerary_scheduled_date ON itinerary_items(scheduled_date);
