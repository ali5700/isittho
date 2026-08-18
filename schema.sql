-- isittho database schema
-- Run this once against a Postgres database with the pgvector extension available.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS submissions (
    id              BIGSERIAL PRIMARY KEY,
    text            TEXT NOT NULL,
    category        TEXT NOT NULL,
    relationship_stage TEXT,
    severity_band   TEXT,
    outcome_label   TEXT NOT NULL CHECK (outcome_label IN ('normal', 'yellow_flag', 'red_flag')),
    source          TEXT NOT NULL DEFAULT 'user' CHECK (source IN ('user', 'synthetic')),
    embedding       vector(1024),  -- voyage-3 outputs 1024-dim vectors
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Approximate nearest-neighbor index for fast similarity search.
-- IVFFlat needs data present before it's built well; fine to create now
-- and REINDEX later once you have thousands of real rows.
CREATE INDEX IF NOT EXISTS submissions_embedding_idx
    ON submissions USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

CREATE INDEX IF NOT EXISTS submissions_category_idx ON submissions (category);
CREATE INDEX IF NOT EXISTS submissions_source_idx ON submissions (source);

-- Optional: track community votes on ambiguous submissions, useful once
-- you have real users weighing in on "normal vs red flag" for open cases.
CREATE TABLE IF NOT EXISTS votes (
    id              BIGSERIAL PRIMARY KEY,
    submission_id   BIGINT NOT NULL REFERENCES submissions(id) ON DELETE CASCADE,
    vote            TEXT NOT NULL CHECK (vote IN ('normal', 'yellow_flag', 'red_flag')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS votes_submission_idx ON votes (submission_id);
