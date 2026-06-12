-- Migration 027: Workflow definitions
-- Stores canonical YAML workflow definitions with versioning

CREATE TABLE IF NOT EXISTS workflow_definitions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  description TEXT,
  project_id UUID REFERENCES cortex_projects(id) ON DELETE SET NULL,
  yaml_content TEXT NOT NULL,
  parsed_definition JSONB DEFAULT '{}',
  version INTEGER NOT NULL DEFAULT 1,
  is_latest BOOLEAN NOT NULL DEFAULT true,
  tags TEXT[] DEFAULT '{}',
  origin TEXT NOT NULL DEFAULT 'user',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  deleted_at TIMESTAMPTZ DEFAULT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_workflow_definitions_name_project_version
  ON workflow_definitions (name, COALESCE(project_id, '00000000-0000-0000-0000-000000000000'::uuid), version)
  WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_workflow_definitions_project
  ON workflow_definitions (project_id)
  WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_workflow_definitions_latest
  ON workflow_definitions (is_latest)
  WHERE is_latest = true AND deleted_at IS NULL;
