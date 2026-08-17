-- One row per destination attached to a trip. Includes the Wikipedia
-- description and an embedding of it for semantic activity retrieval.
-- Uses the pgvector extension.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS destinations (
    id                    BIGSERIAL PRIMARY KEY,
    trip_id               BIGINT NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
    name                  VARCHAR(255) NOT NULL,
    country               VARCHAR(100),
    admin1                VARCHAR(100),                  -- state / province / island
    latitude              DOUBLE PRECISION NOT NULL,
    longitude             DOUBLE PRECISION NOT NULL,
    timezone              VARCHAR(64),
    description           TEXT,
    description_embedding VECTOR(384),                   -- sentence-transformers/all-MiniLM-L6-v2
    wikipedia_url         TEXT,
    created_at            TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_destinations_trip ON destinations(trip_id);

-- HNSW index for fast cosine-similarity semantic search.
CREATE INDEX IF NOT EXISTS idx_destinations_embedding_hnsw
    ON destinations USING hnsw (description_embedding vector_cosine_ops);
