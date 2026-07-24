-- 039_add_extension_agent_targets.sql
-- Adds reviewed, agent-specific projections of agent-neutral Cortex skills.

BEGIN;

ALTER TABLE cortex_systems
  ADD COLUMN IF NOT EXISTS agent TEXT NOT NULL DEFAULT 'claude';

ALTER TABLE cortex_systems
  DROP CONSTRAINT IF EXISTS cortex_systems_fingerprint_key;

CREATE UNIQUE INDEX IF NOT EXISTS idx_cortex_systems_fingerprint_agent
  ON cortex_systems (fingerprint, agent);

CREATE TABLE IF NOT EXISTS cortex_extension_targets (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  extension_id UUID NOT NULL REFERENCES cortex_extensions(id) ON DELETE CASCADE,
  agent TEXT NOT NULL,
  mode TEXT NOT NULL CHECK (mode IN ('direct', 'adapted')),
  scope TEXT NOT NULL CHECK (scope IN ('repository', 'global')),
  reviewed_source_hash TEXT NOT NULL,
  payload_content TEXT NOT NULL,
  payload_hash TEXT NOT NULL,
  reviewed_by TEXT NOT NULL,
  reviewed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (extension_id, agent)
);

CREATE INDEX IF NOT EXISTS idx_cortex_extension_targets_agent
  ON cortex_extension_targets (agent);

INSERT INTO cortex_migrations (version, migration_name)
VALUES ('0.1.0', '039_add_extension_agent_targets')
ON CONFLICT DO NOTHING;

COMMIT;
