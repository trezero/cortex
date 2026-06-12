-- Migration 032: Execution backends
-- Routing table for remote-agent instances

CREATE TABLE IF NOT EXISTS execution_backends (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL UNIQUE,
  base_url TEXT NOT NULL,
  auth_token_hash TEXT NOT NULL,
  project_id UUID REFERENCES cortex_projects(id) ON DELETE SET NULL,
  status TEXT NOT NULL DEFAULT 'healthy',
  last_heartbeat_at TIMESTAMPTZ,
  registered_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_execution_backends_project
  ON execution_backends (project_id);
