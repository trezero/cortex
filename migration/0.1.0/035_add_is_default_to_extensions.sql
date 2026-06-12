-- 035_add_is_default_to_extensions.sql
-- Adds is_default flag to cortex_extensions for the default template feature.
-- Extensions where is_default = true are installed on every new Cortex-connected application.

ALTER TABLE cortex_extensions
  ADD COLUMN IF NOT EXISTS is_default BOOLEAN NOT NULL DEFAULT false;
