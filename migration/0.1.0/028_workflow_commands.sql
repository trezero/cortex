-- Migration 028: Workflow commands
-- Stores prompt templates referenced by workflow nodes

CREATE TABLE IF NOT EXISTS workflow_commands (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  description TEXT,
  prompt_template TEXT NOT NULL,
  variables JSONB DEFAULT '{}',
  version INTEGER NOT NULL DEFAULT 1,
  is_latest BOOLEAN NOT NULL DEFAULT true,
  project_id UUID REFERENCES cortex_projects(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  is_builtin BOOLEAN NOT NULL DEFAULT false,
  deleted_at TIMESTAMPTZ DEFAULT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_workflow_commands_name_project_version
  ON workflow_commands (name, COALESCE(project_id, '00000000-0000-0000-0000-000000000000'::uuid), version)
  WHERE deleted_at IS NULL;
