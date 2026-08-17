-- Users of the RoamAI app. Identified by email (from X-Forwarded-User header).
-- Seed row inserted so the app has a user to attach trips to on first run.

CREATE TABLE IF NOT EXISTS users (
    id           BIGSERIAL PRIMARY KEY,
    email        VARCHAR(255) NOT NULL UNIQUE,
    display_name VARCHAR(255),
    created_at   TIMESTAMP DEFAULT NOW()
);

INSERT INTO users (email, display_name)
VALUES ('rajendrannpriyankaa24@gmail.com', 'Priyankaa')
ON CONFLICT (email) DO NOTHING;
