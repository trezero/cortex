-- 038_rename_extension_metadata.sql
-- 036 renamed extension name/content/content_hash but not the auxiliary
-- columns that drive bundle filenames and display: plugin_manifest
-- (filename/command_group feed the commands.tar.gz entry names),
-- display_name, description, and tags.

BEGIN;

UPDATE cortex_extensions
SET plugin_manifest = replace(replace(replace(plugin_manifest::text,
        'ARCHON', 'CORTEX'), 'Archon', 'Cortex'), 'archon', 'cortex')::jsonb
WHERE plugin_manifest::text ILIKE '%archon%';

UPDATE cortex_extensions
SET display_name = replace(replace(replace(display_name,
        'ARCHON', 'CORTEX'), 'Archon', 'Cortex'), 'archon', 'cortex')
WHERE display_name ILIKE '%archon%';

UPDATE cortex_extensions
SET description = replace(replace(replace(description,
        'ARCHON', 'CORTEX'), 'Archon', 'Cortex'), 'archon', 'cortex')
WHERE description ILIKE '%archon%';

UPDATE cortex_extensions
SET tags = replace(replace(replace(tags::text,
        'ARCHON', 'CORTEX'), 'Archon', 'Cortex'), 'archon', 'cortex')::text[]
WHERE tags::text ILIKE '%archon%';

INSERT INTO cortex_migrations (version, migration_name)
VALUES ('0.1.0', '038_rename_extension_metadata')
ON CONFLICT DO NOTHING;

COMMIT;
