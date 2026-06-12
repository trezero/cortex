-- Migration 029: Workflow runs
-- Tracks individual executions of workflow definitions

CREATE TABLE IF NOT EXISTS workflow_runs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  definition_id UUID NOT NULL REFERENCES workflow_definitions(id) ON DELETE CASCADE,
  project_id UUID REFERENCES cortex_projects(id) ON DELETE SET NULL,
  backend_id UUID,
  status TEXT NOT NULL DEFAULT 'pending',
  triggered_by TEXT,
  trigger_context JSONB DEFAULT '{}',
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_workflow_runs_status
  ON workflow_runs (status);

CREATE INDEX IF NOT EXISTS idx_workflow_runs_project_status
  ON workflow_runs (project_id, status)
  WHERE project_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_workflow_runs_definition
  ON workflow_runs (definition_id);
