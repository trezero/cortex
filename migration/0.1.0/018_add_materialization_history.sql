-- 018_add_materialization_history.sql
-- Tracks knowledge materialization events across projects

CREATE TABLE IF NOT EXISTS cortex_materialization_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id TEXT NOT NULL,
    project_path TEXT NOT NULL,
    topic TEXT NOT NULL,
    filename TEXT NOT NULL,
    file_path TEXT NOT NULL,
    source_ids TEXT[] DEFAULT '{}',
    original_urls TEXT[] DEFAULT '{}',
    synthesis_model TEXT,
    word_count INTEGER DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active',
    access_count INTEGER DEFAULT 0,
    last_accessed_at TIMESTAMPTZ,
    materialized_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'
);

-- Indexes for materialization history
CREATE INDEX IF NOT EXISTS idx_mat_history_project ON cortex_materialization_history(project_id);
CREATE INDEX IF NOT EXISTS idx_mat_history_status ON cortex_materialization_history(status);
CREATE INDEX IF NOT EXISTS idx_mat_history_topic ON cortex_materialization_history(topic);
CREATE INDEX IF NOT EXISTS idx_mat_history_project_topic ON cortex_materialization_history(project_id, topic);

-- Increment access count and update timestamps atomically
CREATE OR REPLACE FUNCTION increment_access_count(record_id UUID)
RETURNS VOID AS $$
BEGIN
    UPDATE cortex_materialization_history
    SET access_count = access_count + 1,
        last_accessed_at = NOW(),
        updated_at = NOW()
    WHERE id = record_id;
END;
$$ LANGUAGE plpgsql;
