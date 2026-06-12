-- Migration: 013_add_project_hierarchy_and_metadata.sql
-- Description: Add parent_project_id for project hierarchy, metadata JSONB, and tags array
--              to cortex_projects. Includes single-level hierarchy enforcement via trigger.
-- Version: 0.1.0
-- Date: 2026-03

-- Add parent_project_id column with self-referencing FK
ALTER TABLE cortex_projects
  ADD COLUMN IF NOT EXISTS parent_project_id UUID REFERENCES cortex_projects(id) ON DELETE SET NULL;

-- Add metadata (key-value object) and tags (filterable array) columns
ALTER TABLE cortex_projects
  ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS tags TEXT[] DEFAULT '{}';

-- Indexes
CREATE INDEX IF NOT EXISTS idx_cortex_projects_parent ON cortex_projects(parent_project_id);
CREATE INDEX IF NOT EXISTS idx_cortex_projects_metadata ON cortex_projects USING GIN(metadata);
CREATE INDEX IF NOT EXISTS idx_cortex_projects_tags ON cortex_projects USING GIN(tags);

-- Single-level hierarchy constraint via trigger
-- A parent cannot itself have a parent, and a project with children cannot become a child.
CREATE OR REPLACE FUNCTION enforce_single_level_hierarchy()
RETURNS TRIGGER AS $$
BEGIN
  IF NEW.parent_project_id IS NOT NULL THEN
    -- Check that the parent is not itself a child
    IF EXISTS (
      SELECT 1 FROM cortex_projects
      WHERE id = NEW.parent_project_id AND parent_project_id IS NOT NULL
    ) THEN
      RAISE EXCEPTION 'Cannot nest projects more than one level deep. Parent project % is already a child project.', NEW.parent_project_id;
    END IF;
    -- Check that this project doesn't already have children
    IF EXISTS (
      SELECT 1 FROM cortex_projects
      WHERE parent_project_id = NEW.id
    ) THEN
      RAISE EXCEPTION 'Cannot make project % a child — it already has child projects.', NEW.id;
    END IF;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Drop trigger if it exists (idempotent)
DROP TRIGGER IF EXISTS trg_enforce_single_level_hierarchy ON cortex_projects;

CREATE TRIGGER trg_enforce_single_level_hierarchy
  BEFORE INSERT OR UPDATE OF parent_project_id ON cortex_projects
  FOR EACH ROW EXECUTE FUNCTION enforce_single_level_hierarchy();

-- Column comments
COMMENT ON COLUMN cortex_projects.parent_project_id IS 'Optional parent project for hierarchy. Single level only (enforced by trigger).';
COMMENT ON COLUMN cortex_projects.metadata IS 'Key-value metadata (domain, directory, deployment_url, etc.)';
COMMENT ON COLUMN cortex_projects.tags IS 'Filterable tags for categorization';
