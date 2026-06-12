-- Migration: 012_backfill_project_sources_junction.sql
-- Description: Backfill cortex_project_sources junction table from cortex_sources metadata.
--              Sources ingested via MCP set metadata->>project_id but do NOT create junction
--              table entries. This migration ensures all existing project-source links exist
--              in the canonical junction table before search is migrated to use it.
-- Version: 0.1.0
-- Date: 2026-03

-- Backfill junction table from metadata project_id values
INSERT INTO cortex_project_sources (project_id, source_id, notes, created_by)
SELECT
  (metadata->>'project_id')::uuid,
  source_id,
  'technical',
  'migration_012'
FROM cortex_sources
WHERE metadata->>'project_id' IS NOT NULL
  AND NOT EXISTS (
    SELECT 1 FROM cortex_project_sources ps
    WHERE ps.source_id = cortex_sources.source_id
      AND ps.project_id = (cortex_sources.metadata->>'project_id')::uuid
  );
