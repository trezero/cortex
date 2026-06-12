-- Migration 025: Add project enrichment columns for chat prioritization
-- Adds optional goals, relevance, and category fields to cortex_projects

ALTER TABLE cortex_projects
  ADD COLUMN IF NOT EXISTS project_goals jsonb DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS project_relevance text DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS project_category text DEFAULT NULL;

-- Index for category-based filtering and grouping
CREATE INDEX IF NOT EXISTS idx_cortex_projects_category
  ON cortex_projects (project_category)
  WHERE project_category IS NOT NULL;
