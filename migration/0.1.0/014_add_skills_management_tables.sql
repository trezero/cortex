-- Skills Management System Tables
-- Adds tables for centralized skill registry, version history,
-- project-specific overrides, and per-system install state tracking.

-- cortex_systems: Registered machines
CREATE TABLE IF NOT EXISTS cortex_systems (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  fingerprint TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  hostname TEXT,
  os TEXT,
  last_seen_at TIMESTAMPTZ DEFAULT NOW(),
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- cortex_skills: Central skill registry
CREATE TABLE IF NOT EXISTS cortex_skills (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL UNIQUE,
  display_name TEXT DEFAULT '',
  description TEXT DEFAULT '',
  content TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  current_version INTEGER DEFAULT 1,
  is_required BOOLEAN DEFAULT false,
  is_validated BOOLEAN DEFAULT false,
  tags TEXT[] DEFAULT '{}',
  created_by TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- cortex_skill_versions: Version history
CREATE TABLE IF NOT EXISTS cortex_skill_versions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  skill_id UUID NOT NULL REFERENCES cortex_skills(id) ON DELETE CASCADE,
  version_number INTEGER NOT NULL,
  content TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  change_summary TEXT,
  created_by TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(skill_id, version_number)
);

-- cortex_project_skills: Project-specific overrides
CREATE TABLE IF NOT EXISTS cortex_project_skills (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL REFERENCES cortex_projects(id) ON DELETE CASCADE,
  skill_id UUID NOT NULL REFERENCES cortex_skills(id) ON DELETE CASCADE,
  custom_content TEXT,
  content_hash TEXT,
  is_enabled BOOLEAN DEFAULT true,
  override_version INTEGER DEFAULT 1,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(project_id, skill_id)
);

-- cortex_system_skills: Install state junction
CREATE TABLE IF NOT EXISTS cortex_system_skills (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  system_id UUID NOT NULL REFERENCES cortex_systems(id) ON DELETE CASCADE,
  skill_id UUID NOT NULL REFERENCES cortex_skills(id) ON DELETE CASCADE,
  project_id UUID NOT NULL REFERENCES cortex_projects(id) ON DELETE CASCADE,
  status TEXT NOT NULL DEFAULT 'pending_install',
  installed_content_hash TEXT,
  installed_version INTEGER,
  has_local_changes BOOLEAN DEFAULT false,
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(system_id, skill_id, project_id)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_cortex_skills_name ON cortex_skills(name);
CREATE INDEX IF NOT EXISTS idx_cortex_systems_fingerprint ON cortex_systems(fingerprint);
CREATE INDEX IF NOT EXISTS idx_cortex_system_skills_system ON cortex_system_skills(system_id);
CREATE INDEX IF NOT EXISTS idx_cortex_system_skills_project ON cortex_system_skills(project_id);
CREATE INDEX IF NOT EXISTS idx_cortex_system_skills_status ON cortex_system_skills(status);
CREATE INDEX IF NOT EXISTS idx_cortex_skill_versions_skill ON cortex_skill_versions(skill_id);
CREATE INDEX IF NOT EXISTS idx_cortex_project_skills_project ON cortex_project_skills(project_id);
