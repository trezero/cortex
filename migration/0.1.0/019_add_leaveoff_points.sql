-- 019_add_leaveoff_points.sql
-- Per-project singleton capturing current development state for session continuity.
-- UNIQUE constraint on project_id enforces exactly one LeaveOff point per project.

CREATE TABLE IF NOT EXISTS cortex_leaveoff_points (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id      UUID NOT NULL UNIQUE REFERENCES cortex_projects(id) ON DELETE CASCADE,
    machine_id      TEXT,
    last_session_id UUID,
    content         TEXT NOT NULL,
    component       TEXT,
    next_steps      TEXT[] NOT NULL DEFAULT '{}',
    "references"    TEXT[] NOT NULL DEFAULT '{}',
    metadata        JSONB NOT NULL DEFAULT '{}',
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_leaveoff_project ON cortex_leaveoff_points(project_id);
