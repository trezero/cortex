-- Project-System Registration Table
-- Tracks which systems have synced with which projects.
-- Decouples system registration from skill install state so a system
-- is visible in a project's Skills tab as soon as it first syncs,
-- even before any skills are installed.

CREATE TABLE IF NOT EXISTS cortex_project_system_registrations (
  project_id UUID NOT NULL REFERENCES cortex_projects(id) ON DELETE CASCADE,
  system_id  UUID NOT NULL REFERENCES cortex_systems(id)  ON DELETE CASCADE,
  last_sync_at TIMESTAMPTZ DEFAULT NOW(),
  PRIMARY KEY (project_id, system_id)
);

CREATE INDEX IF NOT EXISTS idx_project_system_reg_project
  ON cortex_project_system_registrations(project_id);

CREATE INDEX IF NOT EXISTS idx_project_system_reg_system
  ON cortex_project_system_registrations(system_id);
