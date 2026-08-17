-- One row per trip a user is planning. Each trip has a single destination
-- (see destinations table) and spans a date range.

CREATE TABLE IF NOT EXISTS trips (
    id         BIGSERIAL PRIMARY KEY,
    user_id    BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name       VARCHAR(255) NOT NULL,
    start_date DATE NOT NULL,
    end_date   DATE NOT NULL,
    notes      TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT trips_dates_valid CHECK (end_date >= start_date)
);

CREATE INDEX IF NOT EXISTS idx_trips_user ON trips(user_id);
