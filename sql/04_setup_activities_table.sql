-- Activities available at each destination. Populated by:
--  1. Pulling attractions from Wikipedia's nearby-articles endpoint
--  2. LLM-generated activities from the destination description
--  3. User-added items
--
-- The `weather_sensitive` flag is what powers weather-aware rescheduling:
-- when the agent sees rain in the forecast, it moves weather_sensitive
-- activities to a different day.

CREATE TABLE IF NOT EXISTS activities (
    id                    BIGSERIAL PRIMARY KEY,
    destination_id        BIGINT NOT NULL REFERENCES destinations(id) ON DELETE CASCADE,
    name                  VARCHAR(255) NOT NULL,
    category              VARCHAR(64),                   -- hiking, beach, water_sports, viewpoint, nature, dining, cultural, shopping
    description           TEXT,
    description_embedding VECTOR(384),
    weather_sensitive     BOOLEAN DEFAULT FALSE,
    duration_hours        NUMERIC(4,1),
    source                VARCHAR(64),                   -- wikipedia, llm_generated, user_added
    created_at            TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_activities_destination ON activities(destination_id);
CREATE INDEX IF NOT EXISTS idx_activities_category    ON activities(category);
CREATE INDEX IF NOT EXISTS idx_activities_embedding_hnsw
    ON activities USING hnsw (description_embedding vector_cosine_ops);
