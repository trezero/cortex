-- 023_add_git_dirty_to_registrations.sql
-- Adds git dirty tracking to project-system registrations for the Projects view
-- uncommitted changes indicator.

ALTER TABLE cortex_project_system_registrations
  ADD COLUMN IF NOT EXISTS git_dirty boolean DEFAULT false,
  ADD COLUMN IF NOT EXISTS git_dirty_checked_at timestamptz;
