-- 020_add_postman_collection_uid.sql
-- Add postman_collection_uid to cortex_projects for API-mode collection tracking.

ALTER TABLE cortex_projects
  ADD COLUMN IF NOT EXISTS postman_collection_uid VARCHAR(255);

COMMENT ON COLUMN cortex_projects.postman_collection_uid IS 'Postman collection UID for API-mode sync. Set by manage_postman init_collection action.';
