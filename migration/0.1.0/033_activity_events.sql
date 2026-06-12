-- Migration 033: Activity events
-- Captures git commits, agent conversations, and workflow runs for pattern discovery

CREATE TABLE IF NOT EXISTS activity_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  event_type TEXT NOT NULL,
  project_id UUID REFERENCES cortex_projects(id) ON DELETE SET NULL,
  repo_url TEXT,
  raw_content TEXT,
  action_verb TEXT,
  target_object TEXT,
  trigger_context TEXT,
  intent_embedding vector,
  metadata JSONB DEFAULT '{}',
  normalized_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_activity_events_type_created
  ON activity_events (event_type, created_at);

CREATE INDEX IF NOT EXISTS idx_activity_events_pending_normalization
  ON activity_events (created_at)
  WHERE normalized_at IS NULL;
