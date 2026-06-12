-- 017_add_session_tables.sql
-- Session memory tables for cortex-memory plugin

-- Session summaries (low volume, has embeddings)
CREATE TABLE IF NOT EXISTS cortex_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES cortex_projects(id) ON DELETE CASCADE,
    machine_id TEXT NOT NULL,
    session_id TEXT NOT NULL UNIQUE,
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ,
    summary TEXT,
    summary_embedding VECTOR(1536),
    observation_count INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Individual observations (high volume, full-text search)
CREATE TABLE IF NOT EXISTS cortex_session_observations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id TEXT NOT NULL REFERENCES cortex_sessions(session_id) ON DELETE CASCADE,
    project_id UUID REFERENCES cortex_projects(id) ON DELETE CASCADE,
    machine_id TEXT NOT NULL,
    type TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT,
    files TEXT[],
    search_vector TSVECTOR,
    observed_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for sessions
CREATE INDEX IF NOT EXISTS idx_sessions_project_time ON cortex_sessions(project_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_machine ON cortex_sessions(machine_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_embedding ON cortex_sessions
    USING hnsw(summary_embedding vector_cosine_ops);

-- Indexes for observations
CREATE INDEX IF NOT EXISTS idx_observations_session ON cortex_session_observations(session_id);
CREATE INDEX IF NOT EXISTS idx_observations_project_time
    ON cortex_session_observations(project_id, observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_observations_search
    ON cortex_session_observations USING gin(search_vector);
CREATE INDEX IF NOT EXISTS idx_observations_type
    ON cortex_session_observations(project_id, type, observed_at DESC);

-- Auto-populate search_vector on insert/update
CREATE OR REPLACE FUNCTION update_observation_search_vector()
RETURNS TRIGGER AS $$
BEGIN
    NEW.search_vector := to_tsvector('english',
        coalesce(NEW.title, '') || ' ' ||
        coalesce(NEW.content, '') || ' ' ||
        coalesce(array_to_string(NEW.files, ' '), '')
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_observation_search_vector
    BEFORE INSERT OR UPDATE ON cortex_session_observations
    FOR EACH ROW EXECUTE FUNCTION update_observation_search_vector();
