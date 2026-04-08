-- 035_add_is_default_to_extensions.sql
-- Adds is_default flag to archon_extensions for the default template feature.
-- Extensions where is_default = true are installed on every new Archon-connected application.

ALTER TABLE archon_extensions
  ADD COLUMN IF NOT EXISTS is_default BOOLEAN NOT NULL DEFAULT false;
