-- Rename skills tables to extensions and add plugin support columns.
-- The "extensions" model encompasses skills and future plugin types
-- (e.g. MCP tools, agents) under a single registry.

-- Rename tables
ALTER TABLE IF EXISTS cortex_skills RENAME TO cortex_extensions;
ALTER TABLE IF EXISTS cortex_skill_versions RENAME TO cortex_extension_versions;
ALTER TABLE IF EXISTS cortex_project_skills RENAME TO cortex_project_extensions;
ALTER TABLE IF EXISTS cortex_system_skills RENAME TO cortex_system_extensions;

-- Add new columns for plugin support
ALTER TABLE cortex_extensions ADD COLUMN IF NOT EXISTS type TEXT NOT NULL DEFAULT 'skill';
ALTER TABLE cortex_extensions ADD COLUMN IF NOT EXISTS plugin_manifest JSONB;

-- Rename foreign key columns in dependent tables
ALTER TABLE cortex_extension_versions RENAME COLUMN skill_id TO extension_id;
ALTER TABLE cortex_project_extensions RENAME COLUMN skill_id TO extension_id;
ALTER TABLE cortex_system_extensions RENAME COLUMN skill_id TO extension_id;

-- Rename indexes to match new table names
ALTER INDEX IF EXISTS idx_cortex_skills_name RENAME TO idx_cortex_extensions_name;
ALTER INDEX IF EXISTS idx_cortex_skill_versions_skill RENAME TO idx_cortex_extension_versions_extension;
ALTER INDEX IF EXISTS idx_cortex_project_skills_project RENAME TO idx_cortex_project_extensions_project;
ALTER INDEX IF EXISTS idx_cortex_system_skills_system RENAME TO idx_cortex_system_extensions_system;
ALTER INDEX IF EXISTS idx_cortex_system_skills_project RENAME TO idx_cortex_system_extensions_project;
ALTER INDEX IF EXISTS idx_cortex_system_skills_status RENAME TO idx_cortex_system_extensions_status;

-- Add index for type filtering
CREATE INDEX IF NOT EXISTS idx_extensions_type ON cortex_extensions(type);
