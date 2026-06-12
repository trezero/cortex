# Skills Management System Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a centralized skill registry in Cortex that tracks Claude Code skills across machines and projects, with a pull-based sync model and an Cortex UI for remote management.

**Architecture:** Five new DB tables store skills, systems, and install state. Four backend services handle CRUD, validation, sync, and system registration. Two MCP tools (`find_skills`, `manage_skills`) expose the backend to Claude Code. A new "Skills" tab in the project view shows registered systems and lets users queue installs. A sync skill auto-runs on startup to detect drift and reconcile state.

**Tech Stack:** PostgreSQL (Supabase), Python/FastAPI, httpx, React/TypeScript, TanStack Query v5, Radix UI

**Design doc:** `docs/plans/2026-03-04-skills-management-design.md`

---

### Task 1: Database migration — Create skills management tables

**Files:**
- Create: `migration/0.1.0/014_add_skills_management_tables.sql`
- Modify: `migration/complete_setup.sql`

**Step 1: Write the migration file**

Create `migration/0.1.0/014_add_skills_management_tables.sql`:

```sql
-- Skills Management System tables
-- Adds: cortex_systems, cortex_skills, cortex_skill_versions,
--        cortex_project_skills, cortex_system_skills

-- Registered machines/clients
CREATE TABLE IF NOT EXISTS cortex_systems (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  fingerprint TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  hostname TEXT,
  os TEXT,
  last_seen_at TIMESTAMPTZ DEFAULT NOW(),
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Central skill registry
CREATE TABLE IF NOT EXISTS cortex_skills (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL UNIQUE,
  display_name TEXT NOT NULL,
  description TEXT DEFAULT '',
  content TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  version INTEGER DEFAULT 1,
  is_required BOOLEAN DEFAULT false,
  is_validated BOOLEAN DEFAULT false,
  tags TEXT[] DEFAULT '{}',
  created_by_system_id UUID REFERENCES cortex_systems(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Skill version history
CREATE TABLE IF NOT EXISTS cortex_skill_versions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  skill_id UUID NOT NULL REFERENCES cortex_skills(id) ON DELETE CASCADE,
  version INTEGER NOT NULL,
  content TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  change_summary TEXT,
  created_by_system_id UUID REFERENCES cortex_systems(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(skill_id, version)
);

-- Project-specific skill overrides
CREATE TABLE IF NOT EXISTS cortex_project_skills (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL REFERENCES cortex_projects(id) ON DELETE CASCADE,
  skill_id UUID NOT NULL REFERENCES cortex_skills(id) ON DELETE CASCADE,
  content_override TEXT,
  content_hash TEXT,
  override_version INTEGER DEFAULT 1,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(project_id, skill_id)
);

-- System-skill install state (scoped to projects)
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

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_cortex_skills_name ON cortex_skills(name);
CREATE INDEX IF NOT EXISTS idx_cortex_systems_fingerprint ON cortex_systems(fingerprint);
CREATE INDEX IF NOT EXISTS idx_cortex_system_skills_system ON cortex_system_skills(system_id);
CREATE INDEX IF NOT EXISTS idx_cortex_system_skills_project ON cortex_system_skills(project_id);
CREATE INDEX IF NOT EXISTS idx_cortex_system_skills_status ON cortex_system_skills(status);
CREATE INDEX IF NOT EXISTS idx_cortex_skill_versions_skill ON cortex_skill_versions(skill_id);
CREATE INDEX IF NOT EXISTS idx_cortex_project_skills_project ON cortex_project_skills(project_id);
```

**Step 2: Add tables to complete_setup.sql**

Append the same SQL above into `migration/complete_setup.sql` before the `-- SETUP COMPLETE` block (before line ~1399).

**Step 3: Verify migration syntax**

Run: `cat migration/0.1.0/014_add_skills_management_tables.sql | head -5`
Expected: First lines of the migration visible without syntax errors.

**Step 4: Commit**

```bash
git add migration/0.1.0/014_add_skills_management_tables.sql migration/complete_setup.sql
git commit -m "feat: add skills management database tables"
```

---

### Task 2: Backend service — SkillValidationService

The validation service has no DB dependencies, making it a clean first service to build.

**Files:**
- Create: `python/src/server/services/skills/__init__.py`
- Create: `python/src/server/services/skills/skill_validation_service.py`
- Create: `python/tests/server/services/skills/test_skill_validation_service.py`

**Step 1: Write the failing tests**

Create `python/tests/server/services/skills/__init__.py` (empty).

Create `python/tests/server/services/skills/test_skill_validation_service.py`:

```python
"""Tests for skill validation service."""
import pytest

from src.server.services.skills.skill_validation_service import SkillValidationService


@pytest.fixture
def validator():
    return SkillValidationService()


VALID_SKILL = """---
name: test-skill
description: A test skill for validating things when the user asks to validate
---

## Phase 1: Do the thing

Instructions here.
"""

MISSING_FRONTMATTER = """# No Frontmatter Skill

Just content, no YAML block.
"""

MISSING_NAME = """---
description: Has description but no name
---

## Phase 1: Something
"""

BAD_NAME_FORMAT = """---
name: Test Skill With Spaces
description: A test skill for validating things when asked
---

## Phase 1: Something
"""

HAS_SECRETS = """---
name: secret-skill
description: A skill that accidentally includes API keys for testing
---

## Phase 1: Setup

Set your key: sk-proj-abc123def456ghi789jkl012mno345pqr678stu901vwx234
"""

TOO_LARGE = "---\nname: big-skill\ndescription: A very large skill that exceeds the size limit check\n---\n\n" + "x" * 51_000

SHORT_DESCRIPTION = """---
name: short-desc
description: Too short
---

## Phase 1: Something
"""


class TestFrontmatterParsing:
    def test_valid_skill_passes(self, validator):
        result = validator.validate(VALID_SKILL)
        assert result["valid"] is True
        assert len(result["errors"]) == 0
        assert result["parsed"]["name"] == "test-skill"

    def test_missing_frontmatter_errors(self, validator):
        result = validator.validate(MISSING_FRONTMATTER)
        assert result["valid"] is False
        assert any(e["check"] == "frontmatter_present" for e in result["errors"])

    def test_missing_name_errors(self, validator):
        result = validator.validate(MISSING_NAME)
        assert result["valid"] is False
        assert any(e["check"] == "frontmatter_present" for e in result["errors"])


class TestNameValidation:
    def test_bad_name_format_errors(self, validator):
        result = validator.validate(BAD_NAME_FORMAT)
        assert result["valid"] is False
        assert any(e["check"] == "name_format" for e in result["errors"])

    def test_kebab_case_passes(self, validator):
        result = validator.validate(VALID_SKILL)
        assert not any(e["check"] == "name_format" for e in result["errors"])


class TestSecurityChecks:
    def test_secrets_detected(self, validator):
        result = validator.validate(HAS_SECRETS)
        assert result["valid"] is False
        assert any(e["check"] == "no_secrets" for e in result["errors"])

    def test_size_limit(self, validator):
        result = validator.validate(TOO_LARGE)
        assert result["valid"] is False
        assert any(e["check"] == "size_limit" for e in result["errors"])


class TestWarnings:
    def test_short_description_warns(self, validator):
        result = validator.validate(SHORT_DESCRIPTION)
        assert any(w["check"] == "description_quality" for w in result["warnings"])

    def test_no_headings_warns(self, validator):
        content = "---\nname: no-headings\ndescription: A skill without any markdown headings at all\n---\n\nJust plain text."
        result = validator.validate(content)
        assert any(w["check"] == "content_structure" for w in result["warnings"])
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/server/services/skills/test_skill_validation_service.py -v`
Expected: FAIL — module not found

**Step 3: Create the service directory**

Create `python/src/server/services/skills/__init__.py`:

```python
"""Skills management services."""
from .skill_validation_service import SkillValidationService

__all__ = ["SkillValidationService"]
```

**Step 4: Write the validation service**

Create `python/src/server/services/skills/skill_validation_service.py`:

```python
"""Skill validation and cleanup service.

Validates SKILL.md content before it can be uploaded to the Cortex registry.
Checks frontmatter format, naming conventions, security, and content structure.
"""
import logging
import re
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# Patterns that suggest secrets or credentials
SECRET_PATTERNS = [
    r"sk-[a-zA-Z0-9]{20,}",                          # OpenAI-style keys
    r"sk-proj-[a-zA-Z0-9]{20,}",                      # OpenAI project keys
    r"sk-ant-[a-zA-Z0-9]{20,}",                       # Anthropic keys
    r"ghp_[a-zA-Z0-9]{36}",                           # GitHub PATs
    r"gho_[a-zA-Z0-9]{36}",                           # GitHub OAuth
    r"glpat-[a-zA-Z0-9\-]{20,}",                      # GitLab PATs
    r"xox[bpors]-[a-zA-Z0-9\-]{10,}",                 # Slack tokens
    r"-----BEGIN\s+(RSA\s+)?PRIVATE\sKEY-----",       # Private keys
    r"AKIA[0-9A-Z]{16}",                              # AWS access keys
    r"eyJ[a-zA-Z0-9_-]{20,}\.[a-zA-Z0-9_-]{20,}\.",  # JWTs
]

KEBAB_CASE_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
HARDCODED_PATH_PATTERN = re.compile(r"(?:^|\s)(/home/|/Users/|C:\\Users\\)[^\s]+")
MAX_SKILL_SIZE = 50 * 1024  # 50KB
MIN_DESCRIPTION_LENGTH = 20


class SkillValidationService:
    """Validates SKILL.md content for the Cortex skill registry."""

    def validate(self, content: str, existing_name: str | None = None) -> dict[str, Any]:
        """Validate skill content and return a validation report.

        Args:
            content: Full SKILL.md content including frontmatter.
            existing_name: If updating an existing skill, its current name (skip uniqueness check).

        Returns:
            Validation report with valid, errors, warnings, and parsed fields.
        """
        errors: list[dict[str, str]] = []
        warnings: list[dict[str, str]] = []
        parsed: dict[str, Any] = {}

        # Size check first
        if len(content.encode("utf-8")) > MAX_SKILL_SIZE:
            errors.append({
                "check": "size_limit",
                "message": f"Skill content exceeds {MAX_SKILL_SIZE // 1024}KB limit ({len(content.encode('utf-8')) // 1024}KB).",
            })

        # Parse frontmatter
        name, description, frontmatter_error = self._parse_frontmatter(content)
        if frontmatter_error:
            errors.append({"check": "frontmatter_present", "message": frontmatter_error})
        else:
            parsed["name"] = name
            parsed["description"] = description

        # Name format check
        if name and not KEBAB_CASE_PATTERN.match(name):
            errors.append({
                "check": "name_format",
                "message": f"Name '{name}' must be kebab-case (lowercase alphanumeric with hyphens).",
            })

        # Secret detection
        for pattern in SECRET_PATTERNS:
            if re.search(pattern, content):
                errors.append({
                    "check": "no_secrets",
                    "message": "Content appears to contain secrets or API keys. Remove them before uploading.",
                })
                break

        # Description quality (warning)
        if description and len(description) < MIN_DESCRIPTION_LENGTH:
            warnings.append({
                "check": "description_quality",
                "message": f"Description is short ({len(description)} chars). Consider adding trigger phrases for discoverability.",
            })

        # Content structure (warning)
        body = self._get_body(content)
        headings = re.findall(r"^#{2,}\s+.+$", body, re.MULTILINE)
        parsed["heading_count"] = len(headings)
        parsed["estimated_phases"] = len([h for h in headings if re.match(r"^##\s+", h)])

        if len(headings) == 0:
            warnings.append({
                "check": "content_structure",
                "message": "No markdown headings found. Skills should have at least one ## section.",
            })

        # Hardcoded paths (warning)
        if HARDCODED_PATH_PATTERN.search(content):
            warnings.append({
                "check": "no_hardcoded_paths",
                "message": "Content contains absolute file paths. Consider using relative paths or placeholders.",
            })

        # Tool references (warning — catalog deferred to future phase)
        tool_refs = re.findall(r"\b([a-z_]+)\(", body)
        parsed["tool_references"] = list(set(tool_refs))

        valid = len(errors) == 0
        return {"valid": valid, "errors": errors, "warnings": warnings, "parsed": parsed}

    def _parse_frontmatter(self, content: str) -> tuple[str | None, str | None, str | None]:
        """Extract name and description from YAML frontmatter.

        Returns:
            (name, description, error_message)
        """
        if not content.startswith("---"):
            return None, None, "Missing YAML frontmatter (file must start with ---)."

        parts = content.split("---", 2)
        if len(parts) < 3:
            return None, None, "Malformed frontmatter (missing closing ---)."

        try:
            frontmatter = yaml.safe_load(parts[1])
        except yaml.YAMLError as e:
            return None, None, f"Invalid YAML in frontmatter: {e}"

        if not isinstance(frontmatter, dict):
            return None, None, "Frontmatter must be a YAML mapping with name and description fields."

        name = frontmatter.get("name")
        description = frontmatter.get("description")

        if not name:
            return None, None, "Frontmatter missing required 'name' field."

        return str(name), str(description) if description else None, None

    def _get_body(self, content: str) -> str:
        """Extract the body (everything after frontmatter)."""
        if not content.startswith("---"):
            return content
        parts = content.split("---", 2)
        return parts[2] if len(parts) >= 3 else ""
```

**Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/server/services/skills/test_skill_validation_service.py -v`
Expected: ALL PASS

**Step 6: Run linter**

Run: `uv run ruff check src/server/services/skills/`
Expected: No errors

**Step 7: Commit**

```bash
git add python/src/server/services/skills/ python/tests/server/services/skills/
git commit -m "feat: add SkillValidationService with frontmatter, naming, and security checks"
```

---

### Task 3: Backend service — SystemService

Handles machine fingerprint registration and lookup.

**Files:**
- Create: `python/src/server/services/skills/system_service.py`
- Create: `python/tests/server/services/skills/test_system_service.py`
- Modify: `python/src/server/services/skills/__init__.py`

**Step 1: Write the failing tests**

Create `python/tests/server/services/skills/test_system_service.py`:

```python
"""Tests for system registration service."""
import pytest
from unittest.mock import MagicMock, patch

from src.server.services.skills.system_service import SystemService


@pytest.fixture
def mock_supabase():
    return MagicMock()


@pytest.fixture
def service(mock_supabase):
    return SystemService(supabase_client=mock_supabase)


class TestFindByFingerprint:
    def test_returns_system_when_found(self, service, mock_supabase):
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            {"id": "sys-1", "fingerprint": "abc123", "name": "My Machine"}
        ]
        result = service.find_by_fingerprint("abc123")
        assert result is not None
        assert result["id"] == "sys-1"

    def test_returns_none_when_not_found(self, service, mock_supabase):
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []
        result = service.find_by_fingerprint("unknown")
        assert result is None


class TestRegisterSystem:
    def test_creates_system_record(self, service, mock_supabase):
        mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [
            {"id": "sys-new", "fingerprint": "abc123", "name": "Dev Laptop"}
        ]
        result = service.register_system(
            fingerprint="abc123", name="Dev Laptop", hostname="devbox", os="linux"
        )
        assert result["id"] == "sys-new"
        assert result["name"] == "Dev Laptop"
        mock_supabase.table.return_value.insert.assert_called_once()

    def test_insert_data_contains_all_fields(self, service, mock_supabase):
        mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [
            {"id": "sys-new", "fingerprint": "fp", "name": "N", "hostname": "h", "os": "linux"}
        ]
        service.register_system(fingerprint="fp", name="N", hostname="h", os="linux")
        call_args = mock_supabase.table.return_value.insert.call_args[0][0]
        assert call_args["fingerprint"] == "fp"
        assert call_args["name"] == "N"
        assert call_args["hostname"] == "h"
        assert call_args["os"] == "linux"


class TestUpdateLastSeen:
    def test_updates_timestamp(self, service, mock_supabase):
        mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value.data = [
            {"id": "sys-1"}
        ]
        service.update_last_seen("sys-1")
        mock_supabase.table.return_value.update.assert_called_once()
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/server/services/skills/test_system_service.py -v`
Expected: FAIL — module not found

**Step 3: Write the service**

Create `python/src/server/services/skills/system_service.py`:

```python
"""System registration and fingerprint matching service.

Manages the cortex_systems table — registering new machines,
looking up existing ones by fingerprint, and tracking last-seen times.
"""
import logging
from datetime import datetime, timezone
from typing import Any

from src.server.config.database import get_supabase_client

logger = logging.getLogger(__name__)

TABLE = "cortex_systems"


class SystemService:
    """Manages system registration and lookup."""

    def __init__(self, supabase_client=None):
        self.supabase = supabase_client or get_supabase_client()

    def find_by_fingerprint(self, fingerprint: str) -> dict[str, Any] | None:
        """Find a system by its machine fingerprint.

        Returns:
            System record or None if not found.
        """
        result = (
            self.supabase.table(TABLE)
            .select("*")
            .eq("fingerprint", fingerprint)
            .execute()
        )
        return result.data[0] if result.data else None

    def register_system(
        self,
        fingerprint: str,
        name: str,
        hostname: str | None = None,
        os: str | None = None,
    ) -> dict[str, Any]:
        """Register a new system.

        Args:
            fingerprint: SHA256(hostname|username|os) machine identifier.
            name: User-provided friendly name.
            hostname: Raw hostname for display.
            os: Operating system identifier.

        Returns:
            Created system record.

        Raises:
            Exception: If insert fails (e.g. duplicate fingerprint).
        """
        data = {
            "fingerprint": fingerprint,
            "name": name,
            "hostname": hostname,
            "os": os,
        }
        result = self.supabase.table(TABLE).insert(data).execute()
        if not result.data:
            raise RuntimeError(f"Failed to register system with fingerprint {fingerprint}")
        logger.info("Registered new system: %s (%s)", name, fingerprint[:12])
        return result.data[0]

    def update_last_seen(self, system_id: str) -> None:
        """Update last_seen_at timestamp for a system."""
        self.supabase.table(TABLE).update(
            {"last_seen_at": datetime.now(timezone.utc).isoformat()}
        ).eq("id", system_id).execute()

    def get_system(self, system_id: str) -> dict[str, Any] | None:
        """Get a system by ID."""
        result = (
            self.supabase.table(TABLE)
            .select("*")
            .eq("id", system_id)
            .execute()
        )
        return result.data[0] if result.data else None

    def list_systems(self) -> list[dict[str, Any]]:
        """List all registered systems."""
        result = self.supabase.table(TABLE).select("*").order("created_at").execute()
        return result.data or []

    def update_system(self, system_id: str, name: str) -> dict[str, Any]:
        """Update a system's name."""
        result = (
            self.supabase.table(TABLE)
            .update({"name": name})
            .eq("id", system_id)
            .execute()
        )
        if not result.data:
            raise RuntimeError(f"System {system_id} not found")
        return result.data[0]

    def delete_system(self, system_id: str) -> None:
        """Delete a system. Cascades to cortex_system_skills."""
        self.supabase.table(TABLE).delete().eq("id", system_id).execute()
```

**Step 4: Update `__init__.py`**

Add to `python/src/server/services/skills/__init__.py`:

```python
"""Skills management services."""
from .skill_validation_service import SkillValidationService
from .system_service import SystemService

__all__ = ["SkillValidationService", "SystemService"]
```

**Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/server/services/skills/test_system_service.py -v`
Expected: ALL PASS

**Step 6: Commit**

```bash
git add python/src/server/services/skills/system_service.py python/src/server/services/skills/__init__.py python/tests/server/services/skills/test_system_service.py
git commit -m "feat: add SystemService for machine fingerprint registration"
```

---

### Task 4: Backend service — SkillService

Core CRUD for the skill registry with version management and content hashing.

**Files:**
- Create: `python/src/server/services/skills/skill_service.py`
- Create: `python/tests/server/services/skills/test_skill_service.py`
- Modify: `python/src/server/services/skills/__init__.py`

**Step 1: Write the failing tests**

Create `python/tests/server/services/skills/test_skill_service.py`:

```python
"""Tests for skill CRUD service."""
import hashlib
import pytest
from unittest.mock import MagicMock

from src.server.services.skills.skill_service import SkillService


@pytest.fixture
def mock_supabase():
    return MagicMock()


@pytest.fixture
def service(mock_supabase):
    return SkillService(supabase_client=mock_supabase)


SKILL_CONTENT = """---
name: test-skill
description: A test skill for testing purposes when needed
---

## Phase 1: Test

Do the thing.
"""


class TestContentHash:
    def test_hash_is_sha256(self, service):
        h = service.compute_content_hash(SKILL_CONTENT)
        assert len(h) == 64  # SHA256 hex digest
        assert h == hashlib.sha256(SKILL_CONTENT.encode("utf-8")).hexdigest()

    def test_same_content_same_hash(self, service):
        assert service.compute_content_hash("abc") == service.compute_content_hash("abc")

    def test_different_content_different_hash(self, service):
        assert service.compute_content_hash("abc") != service.compute_content_hash("def")


class TestCreateSkill:
    def test_creates_skill_and_version(self, service, mock_supabase):
        skill_row = {
            "id": "skill-1", "name": "test-skill", "display_name": "Test Skill",
            "content": SKILL_CONTENT, "version": 1,
        }
        version_row = {"id": "ver-1", "skill_id": "skill-1", "version": 1}

        mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [skill_row]
        # Second call for version insert
        mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [version_row]

        result = service.create_skill(
            name="test-skill",
            display_name="Test Skill",
            description="A test skill",
            content=SKILL_CONTENT,
        )
        assert result["id"] == "skill-1"


class TestListSkills:
    def test_returns_skills_list(self, service, mock_supabase):
        mock_supabase.table.return_value.select.return_value.order.return_value.execute.return_value.data = [
            {"id": "s1", "name": "skill-a"},
            {"id": "s2", "name": "skill-b"},
        ]
        result = service.list_skills()
        assert len(result) == 2


class TestGetSkill:
    def test_returns_skill(self, service, mock_supabase):
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            {"id": "s1", "name": "skill-a", "content": "..."}
        ]
        result = service.get_skill("s1")
        assert result["name"] == "skill-a"

    def test_returns_none_when_missing(self, service, mock_supabase):
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []
        result = service.get_skill("missing")
        assert result is None


class TestFindByName:
    def test_finds_by_name(self, service, mock_supabase):
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            {"id": "s1", "name": "cortex-memory"}
        ]
        result = service.find_by_name("cortex-memory")
        assert result["id"] == "s1"
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/server/services/skills/test_skill_service.py -v`
Expected: FAIL — module not found

**Step 3: Write the service**

Create `python/src/server/services/skills/skill_service.py`:

```python
"""Skill CRUD and version management service.

Manages the cortex_skills and cortex_skill_versions tables —
creating, updating, versioning, and hashing skill content.
"""
import hashlib
import logging
from typing import Any

from src.server.config.database import get_supabase_client

logger = logging.getLogger(__name__)

SKILLS_TABLE = "cortex_skills"
VERSIONS_TABLE = "cortex_skill_versions"
PROJECT_SKILLS_TABLE = "cortex_project_skills"


class SkillService:
    """Manages the central skill registry."""

    def __init__(self, supabase_client=None):
        self.supabase = supabase_client or get_supabase_client()

    @staticmethod
    def compute_content_hash(content: str) -> str:
        """Compute SHA256 hash of skill content for drift detection."""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def list_skills(self) -> list[dict[str, Any]]:
        """List all skills in the registry (without full content)."""
        result = (
            self.supabase.table(SKILLS_TABLE)
            .select("id, name, display_name, description, version, is_required, is_validated, tags, content_hash, created_at, updated_at")
            .order("name")
            .execute()
        )
        return result.data or []

    def get_skill(self, skill_id: str) -> dict[str, Any] | None:
        """Get a skill by ID (includes full content)."""
        result = (
            self.supabase.table(SKILLS_TABLE)
            .select("*")
            .eq("id", skill_id)
            .execute()
        )
        return result.data[0] if result.data else None

    def find_by_name(self, name: str) -> dict[str, Any] | None:
        """Find a skill by its unique name."""
        result = (
            self.supabase.table(SKILLS_TABLE)
            .select("*")
            .eq("name", name)
            .execute()
        )
        return result.data[0] if result.data else None

    def create_skill(
        self,
        name: str,
        display_name: str,
        description: str,
        content: str,
        is_required: bool = False,
        is_validated: bool = False,
        tags: list[str] | None = None,
        created_by_system_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a new skill in the registry and save version 1.

        Returns:
            Created skill record.
        """
        content_hash = self.compute_content_hash(content)
        skill_data = {
            "name": name,
            "display_name": display_name,
            "description": description,
            "content": content,
            "content_hash": content_hash,
            "version": 1,
            "is_required": is_required,
            "is_validated": is_validated,
            "tags": tags or [],
            "created_by_system_id": created_by_system_id,
        }

        result = self.supabase.table(SKILLS_TABLE).insert(skill_data).execute()
        if not result.data:
            raise RuntimeError(f"Failed to create skill '{name}'")

        skill = result.data[0]

        # Save version 1
        self._save_version(
            skill_id=skill["id"],
            version=1,
            content=content,
            content_hash=content_hash,
            change_summary="Initial version",
            created_by_system_id=created_by_system_id,
        )

        logger.info("Created skill: %s (v1)", name)
        return skill

    def update_skill(
        self,
        skill_id: str,
        content: str,
        change_summary: str | None = None,
        created_by_system_id: str | None = None,
    ) -> dict[str, Any]:
        """Update a skill's content and bump version.

        Returns:
            Updated skill record.
        """
        existing = self.get_skill(skill_id)
        if not existing:
            raise RuntimeError(f"Skill {skill_id} not found")

        new_version = existing["version"] + 1
        content_hash = self.compute_content_hash(content)

        update_data = {
            "content": content,
            "content_hash": content_hash,
            "version": new_version,
        }

        result = (
            self.supabase.table(SKILLS_TABLE)
            .update(update_data)
            .eq("id", skill_id)
            .execute()
        )
        if not result.data:
            raise RuntimeError(f"Failed to update skill {skill_id}")

        self._save_version(
            skill_id=skill_id,
            version=new_version,
            content=content,
            content_hash=content_hash,
            change_summary=change_summary,
            created_by_system_id=created_by_system_id,
        )

        logger.info("Updated skill %s to v%d", existing["name"], new_version)
        return result.data[0]

    def delete_skill(self, skill_id: str) -> None:
        """Delete a skill. Cascades to versions, project overrides, and system installs."""
        self.supabase.table(SKILLS_TABLE).delete().eq("id", skill_id).execute()

    def get_versions(self, skill_id: str) -> list[dict[str, Any]]:
        """Get version history for a skill."""
        result = (
            self.supabase.table(VERSIONS_TABLE)
            .select("*")
            .eq("skill_id", skill_id)
            .order("version", desc=True)
            .execute()
        )
        return result.data or []

    def get_project_skills(self, project_id: str) -> list[dict[str, Any]]:
        """Get skills associated with a project (with override info)."""
        result = (
            self.supabase.table(PROJECT_SKILLS_TABLE)
            .select("*, cortex_skills(*)")
            .eq("project_id", project_id)
            .execute()
        )
        return result.data or []

    def save_project_override(
        self,
        project_id: str,
        skill_id: str,
        content_override: str,
    ) -> dict[str, Any]:
        """Save a project-specific skill override."""
        content_hash = self.compute_content_hash(content_override)
        data = {
            "project_id": project_id,
            "skill_id": skill_id,
            "content_override": content_override,
            "content_hash": content_hash,
        }
        result = (
            self.supabase.table(PROJECT_SKILLS_TABLE)
            .upsert(data, on_conflict="project_id,skill_id")
            .execute()
        )
        if not result.data:
            raise RuntimeError(f"Failed to save project override for skill {skill_id}")
        return result.data[0]

    def _save_version(
        self,
        skill_id: str,
        version: int,
        content: str,
        content_hash: str,
        change_summary: str | None = None,
        created_by_system_id: str | None = None,
    ) -> None:
        """Save a version history entry."""
        self.supabase.table(VERSIONS_TABLE).insert({
            "skill_id": skill_id,
            "version": version,
            "content": content,
            "content_hash": content_hash,
            "change_summary": change_summary,
            "created_by_system_id": created_by_system_id,
        }).execute()
```

**Step 4: Update `__init__.py`**

```python
"""Skills management services."""
from .skill_service import SkillService
from .skill_validation_service import SkillValidationService
from .system_service import SystemService

__all__ = ["SkillService", "SkillValidationService", "SystemService"]
```

**Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/server/services/skills/test_skill_service.py -v`
Expected: ALL PASS

**Step 6: Commit**

```bash
git add python/src/server/services/skills/skill_service.py python/src/server/services/skills/__init__.py python/tests/server/services/skills/test_skill_service.py
git commit -m "feat: add SkillService for skill CRUD and version management"
```

---

### Task 5: Backend service — SkillSyncService

The sync logic: compare local hashes against DB, resolve pending actions, detect drift.

**Files:**
- Create: `python/src/server/services/skills/skill_sync_service.py`
- Create: `python/tests/server/services/skills/test_skill_sync_service.py`
- Modify: `python/src/server/services/skills/__init__.py`

**Step 1: Write the failing tests**

Create `python/tests/server/services/skills/test_skill_sync_service.py`:

```python
"""Tests for skill sync service."""
import pytest
from unittest.mock import MagicMock

from src.server.services.skills.skill_sync_service import SkillSyncService


@pytest.fixture
def mock_supabase():
    return MagicMock()


@pytest.fixture
def service(mock_supabase):
    return SkillSyncService(supabase_client=mock_supabase)


class TestComputeSyncReport:
    def test_in_sync_when_hashes_match(self, service):
        local_skills = [{"name": "cortex-memory", "content_hash": "aaa"}]
        cortex_skills = [{"id": "s1", "name": "cortex-memory", "content_hash": "aaa", "content": "..."}]
        system_skills = [{"skill_id": "s1", "status": "installed", "installed_content_hash": "aaa"}]

        report = service.compute_sync_report(local_skills, cortex_skills, system_skills)
        assert "cortex-memory" in report["in_sync"]
        assert len(report["local_changes"]) == 0

    def test_detects_local_changes(self, service):
        local_skills = [{"name": "cortex-memory", "content_hash": "bbb"}]
        cortex_skills = [{"id": "s1", "name": "cortex-memory", "content_hash": "aaa", "content": "..."}]
        system_skills = [{"skill_id": "s1", "status": "installed", "installed_content_hash": "aaa"}]

        report = service.compute_sync_report(local_skills, cortex_skills, system_skills)
        assert len(report["local_changes"]) == 1
        assert report["local_changes"][0]["name"] == "cortex-memory"

    def test_detects_unknown_local(self, service):
        local_skills = [{"name": "new-skill", "content_hash": "xxx"}]
        cortex_skills = []
        system_skills = []

        report = service.compute_sync_report(local_skills, cortex_skills, system_skills)
        assert len(report["unknown_local"]) == 1
        assert report["unknown_local"][0]["name"] == "new-skill"

    def test_detects_pending_installs(self, service):
        local_skills = []
        cortex_skills = [{"id": "s1", "name": "code-reviewer", "content_hash": "ccc", "content": "...content..."}]
        system_skills = [{"skill_id": "s1", "status": "pending_install"}]

        report = service.compute_sync_report(local_skills, cortex_skills, system_skills)
        assert len(report["pending_install"]) == 1
        assert report["pending_install"][0]["name"] == "code-reviewer"

    def test_detects_pending_removals(self, service):
        local_skills = [{"name": "old-skill", "content_hash": "ddd"}]
        cortex_skills = [{"id": "s2", "name": "old-skill", "content_hash": "ddd", "content": "..."}]
        system_skills = [{"skill_id": "s2", "status": "pending_remove"}]

        report = service.compute_sync_report(local_skills, cortex_skills, system_skills)
        assert len(report["pending_remove"]) == 1
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/server/services/skills/test_skill_sync_service.py -v`
Expected: FAIL — module not found

**Step 3: Write the service**

Create `python/src/server/services/skills/skill_sync_service.py`:

```python
"""Skill sync service.

Compares local skill state against the Cortex registry,
resolves pending actions, and detects drift.
"""
import logging
from typing import Any

from src.server.config.database import get_supabase_client

logger = logging.getLogger(__name__)

SYSTEM_SKILLS_TABLE = "cortex_system_skills"


class SkillSyncService:
    """Handles sync logic between local systems and the Cortex skill registry."""

    def __init__(self, supabase_client=None):
        self.supabase = supabase_client or get_supabase_client()

    def compute_sync_report(
        self,
        local_skills: list[dict[str, Any]],
        cortex_skills: list[dict[str, Any]],
        system_skills: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Compare local skills against Cortex state and return a sync report.

        Args:
            local_skills: [{name, content_hash}] from the client's disk.
            cortex_skills: Full skill records from cortex_skills table.
            system_skills: Records from cortex_system_skills for this system+project.

        Returns:
            Sync report with in_sync, local_changes, pending_install, pending_remove, unknown_local.
        """
        cortex_by_name = {s["name"]: s for s in cortex_skills}
        system_by_skill_id = {s["skill_id"]: s for s in system_skills}
        local_by_name = {s["name"]: s for s in local_skills}

        in_sync: list[str] = []
        local_changes: list[dict[str, Any]] = []
        pending_install: list[dict[str, Any]] = []
        pending_remove: list[dict[str, Any]] = []
        unknown_local: list[dict[str, Any]] = []

        # Check each local skill against Cortex
        for local in local_skills:
            name = local["name"]
            cortex_skill = cortex_by_name.get(name)

            if not cortex_skill:
                unknown_local.append({"name": name, "content_hash": local["content_hash"]})
                continue

            sys_skill = system_by_skill_id.get(cortex_skill["id"])

            if sys_skill and sys_skill["status"] == "pending_remove":
                pending_remove.append({
                    "skill_id": cortex_skill["id"],
                    "name": name,
                })
            elif local["content_hash"] == cortex_skill["content_hash"]:
                in_sync.append(name)
            else:
                local_changes.append({
                    "name": name,
                    "skill_id": cortex_skill["id"],
                    "local_hash": local["content_hash"],
                    "cortex_hash": cortex_skill["content_hash"],
                })

        # Check for pending installs (in Cortex but not local, with pending_install status)
        for sys_skill in system_skills:
            if sys_skill["status"] != "pending_install":
                continue
            skill_id = sys_skill["skill_id"]
            cortex_skill = next((s for s in cortex_skills if s["id"] == skill_id), None)
            if cortex_skill and cortex_skill["name"] not in local_by_name:
                pending_install.append({
                    "skill_id": skill_id,
                    "name": cortex_skill["name"],
                    "content": cortex_skill.get("content", ""),
                })

        return {
            "in_sync": in_sync,
            "local_changes": local_changes,
            "pending_install": pending_install,
            "pending_remove": pending_remove,
            "unknown_local": unknown_local,
        }

    def get_system_skills(self, system_id: str, project_id: str) -> list[dict[str, Any]]:
        """Get all skill install records for a system+project."""
        result = (
            self.supabase.table(SYSTEM_SKILLS_TABLE)
            .select("*")
            .eq("system_id", system_id)
            .eq("project_id", project_id)
            .execute()
        )
        return result.data or []

    def set_install_status(
        self,
        system_id: str,
        skill_id: str,
        project_id: str,
        status: str,
        installed_content_hash: str | None = None,
        installed_version: int | None = None,
        has_local_changes: bool = False,
    ) -> dict[str, Any]:
        """Create or update a system-skill install record."""
        data = {
            "system_id": system_id,
            "skill_id": skill_id,
            "project_id": project_id,
            "status": status,
            "installed_content_hash": installed_content_hash,
            "installed_version": installed_version,
            "has_local_changes": has_local_changes,
        }
        result = (
            self.supabase.table(SYSTEM_SKILLS_TABLE)
            .upsert(data, on_conflict="system_id,skill_id,project_id")
            .execute()
        )
        if not result.data:
            raise RuntimeError(f"Failed to set install status for skill {skill_id} on system {system_id}")
        return result.data[0]

    def queue_install(self, system_ids: list[str], skill_id: str, project_id: str) -> int:
        """Queue a skill for installation on multiple systems.

        Returns:
            Number of systems queued.
        """
        count = 0
        for system_id in system_ids:
            self.set_install_status(system_id, skill_id, project_id, status="pending_install")
            count += 1
        return count

    def queue_remove(self, system_ids: list[str], skill_id: str, project_id: str) -> int:
        """Queue a skill for removal on multiple systems."""
        count = 0
        for system_id in system_ids:
            self.set_install_status(system_id, skill_id, project_id, status="pending_remove")
            count += 1
        return count

    def get_project_systems(self, project_id: str) -> list[dict[str, Any]]:
        """Get all systems that have skills installed for a project."""
        result = (
            self.supabase.table(SYSTEM_SKILLS_TABLE)
            .select("system_id, cortex_systems(*)")
            .eq("project_id", project_id)
            .execute()
        )
        if not result.data:
            return []
        # Deduplicate by system_id
        seen = set()
        systems = []
        for row in result.data:
            sys_id = row["system_id"]
            if sys_id not in seen:
                seen.add(sys_id)
                if row.get("cortex_systems"):
                    systems.append(row["cortex_systems"])
        return systems

    def get_system_project_skills(self, system_id: str, project_id: str) -> list[dict[str, Any]]:
        """Get detailed skill state for a system within a project (with skill info)."""
        result = (
            self.supabase.table(SYSTEM_SKILLS_TABLE)
            .select("*, cortex_skills(id, name, display_name, description, version, content_hash, is_required, is_validated, tags)")
            .eq("system_id", system_id)
            .eq("project_id", project_id)
            .execute()
        )
        return result.data or []
```

**Step 4: Update `__init__.py`**

```python
"""Skills management services."""
from .skill_service import SkillService
from .skill_sync_service import SkillSyncService
from .skill_validation_service import SkillValidationService
from .system_service import SystemService

__all__ = ["SkillService", "SkillSyncService", "SkillValidationService", "SystemService"]
```

**Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/server/services/skills/test_skill_sync_service.py -v`
Expected: ALL PASS

**Step 6: Run all skills tests together**

Run: `uv run pytest tests/server/services/skills/ -v`
Expected: ALL PASS

**Step 7: Commit**

```bash
git add python/src/server/services/skills/ python/tests/server/services/skills/
git commit -m "feat: add SkillSyncService for hash comparison and install state management"
```

---

### Task 6: Backend API — skills_api.py

REST endpoints for skills CRUD, systems, and project-scoped operations.

**Files:**
- Create: `python/src/server/api_routes/skills_api.py`
- Modify: `python/src/server/main.py` (line ~200, add router include)

**Step 1: Write the API route file**

Create `python/src/server/api_routes/skills_api.py`:

```python
"""Skills management API routes.

Provides REST endpoints for skill CRUD, system management,
and project-scoped skill installation.
"""
import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.server.services.skills import (
    SkillService,
    SkillSyncService,
    SkillValidationService,
    SystemService,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["skills"])

# --- Request models ---


class CreateSkillRequest(BaseModel):
    name: str
    display_name: str
    description: str = ""
    content: str
    is_required: bool = False
    tags: list[str] = []


class UpdateSkillRequest(BaseModel):
    content: str
    change_summary: str | None = None


class ValidateSkillRequest(BaseModel):
    content: str


class UpdateSystemRequest(BaseModel):
    name: str


class InstallRemoveRequest(BaseModel):
    system_ids: list[str]


class ProjectSkillOverrideRequest(BaseModel):
    content_override: str


# --- Skills CRUD ---


@router.get("/skills")
async def list_skills() -> dict[str, Any]:
    service = SkillService()
    skills = service.list_skills()
    return {"skills": skills, "count": len(skills)}


@router.get("/skills/{skill_id}")
async def get_skill(skill_id: str) -> dict[str, Any]:
    service = SkillService()
    skill = service.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")
    return skill


@router.post("/skills", status_code=201)
async def create_skill(request: CreateSkillRequest) -> dict[str, Any]:
    validator = SkillValidationService()
    report = validator.validate(request.content)
    if not report["valid"]:
        raise HTTPException(status_code=422, detail={"validation": report})

    service = SkillService()
    existing = service.find_by_name(request.name)
    if existing:
        raise HTTPException(status_code=409, detail=f"Skill '{request.name}' already exists")

    skill = service.create_skill(
        name=request.name,
        display_name=request.display_name,
        description=request.description,
        content=request.content,
        is_required=request.is_required,
        is_validated=report["valid"],
        tags=request.tags,
    )
    return skill


@router.put("/skills/{skill_id}")
async def update_skill(skill_id: str, request: UpdateSkillRequest) -> dict[str, Any]:
    validator = SkillValidationService()
    report = validator.validate(request.content)
    if not report["valid"]:
        raise HTTPException(status_code=422, detail={"validation": report})

    service = SkillService()
    skill = service.update_skill(
        skill_id=skill_id,
        content=request.content,
        change_summary=request.change_summary,
    )
    return skill


@router.delete("/skills/{skill_id}", status_code=204)
async def delete_skill(skill_id: str) -> None:
    service = SkillService()
    existing = service.get_skill(skill_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")
    service.delete_skill(skill_id)


@router.post("/skills/{skill_id}/validate")
async def validate_skill(skill_id: str, request: ValidateSkillRequest) -> dict[str, Any]:
    validator = SkillValidationService()
    return validator.validate(request.content)


@router.get("/skills/{skill_id}/versions")
async def get_skill_versions(skill_id: str) -> dict[str, Any]:
    service = SkillService()
    versions = service.get_versions(skill_id)
    return {"versions": versions, "count": len(versions)}


# --- Systems ---


@router.get("/systems")
async def list_systems() -> dict[str, Any]:
    service = SystemService()
    systems = service.list_systems()
    return {"systems": systems, "count": len(systems)}


@router.get("/systems/{system_id}")
async def get_system(system_id: str) -> dict[str, Any]:
    service = SystemService()
    system = service.get_system(system_id)
    if not system:
        raise HTTPException(status_code=404, detail=f"System {system_id} not found")
    return system


@router.put("/systems/{system_id}")
async def update_system(system_id: str, request: UpdateSystemRequest) -> dict[str, Any]:
    service = SystemService()
    return service.update_system(system_id, request.name)


@router.delete("/systems/{system_id}", status_code=204)
async def delete_system(system_id: str) -> None:
    service = SystemService()
    existing = service.get_system(system_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"System {system_id} not found")
    service.delete_system(system_id)


# --- Project-scoped skills ---


@router.get("/projects/{project_id}/skills")
async def get_project_skills(project_id: str) -> dict[str, Any]:
    skill_service = SkillService()
    sync_service = SkillSyncService()

    # Get all skills in the registry
    all_skills = skill_service.list_skills()

    # Get systems registered to this project
    systems = sync_service.get_project_systems(project_id)

    # For each system, get their skill install state
    systems_with_skills = []
    for system in systems:
        system_skills = sync_service.get_system_project_skills(system["id"], project_id)
        systems_with_skills.append({
            **system,
            "skills": system_skills,
        })

    return {
        "all_skills": all_skills,
        "systems": systems_with_skills,
    }


@router.get("/projects/{project_id}/systems")
async def get_project_systems(project_id: str) -> dict[str, Any]:
    sync_service = SkillSyncService()
    systems = sync_service.get_project_systems(project_id)
    return {"systems": systems, "count": len(systems)}


@router.post("/projects/{project_id}/skills/{skill_id}/install")
async def install_skill_on_systems(
    project_id: str, skill_id: str, request: InstallRemoveRequest
) -> dict[str, Any]:
    sync_service = SkillSyncService()
    count = sync_service.queue_install(request.system_ids, skill_id, project_id)
    return {"queued": count, "status": "pending_install"}


@router.post("/projects/{project_id}/skills/{skill_id}/remove")
async def remove_skill_from_systems(
    project_id: str, skill_id: str, request: InstallRemoveRequest
) -> dict[str, Any]:
    sync_service = SkillSyncService()
    count = sync_service.queue_remove(request.system_ids, skill_id, project_id)
    return {"queued": count, "status": "pending_remove"}


@router.put("/projects/{project_id}/skills/{skill_id}")
async def save_project_skill_override(
    project_id: str, skill_id: str, request: ProjectSkillOverrideRequest
) -> dict[str, Any]:
    service = SkillService()
    return service.save_project_override(project_id, skill_id, request.content_override)
```

**Step 2: Register router in main.py**

In `python/src/server/main.py`, after line 200 (`app.include_router(migration_router)`), add:

```python
from src.server.api_routes.skills_api import router as skills_router
# ... (with other imports at top of file)

app.include_router(skills_router)
```

**Step 3: Run linter**

Run: `uv run ruff check src/server/api_routes/skills_api.py`
Expected: No errors

**Step 4: Commit**

```bash
git add python/src/server/api_routes/skills_api.py python/src/server/main.py
git commit -m "feat: add skills management REST API endpoints"
```

---

### Task 7: MCP tools — find_skills and manage_skills

Two new consolidated MCP tools following the existing pattern.

**Files:**
- Create: `python/src/mcp_server/features/skills/__init__.py`
- Create: `python/src/mcp_server/features/skills/skill_tools.py`
- Modify: `python/src/mcp_server/mcp_server.py` (add registration in `register_modules()`)
- Create: `python/tests/mcp_server/features/skills/test_skill_tools.py`

**Step 1: Write the failing test**

Create `python/tests/mcp_server/features/skills/__init__.py` (empty).

Create `python/tests/mcp_server/features/skills/test_skill_tools.py`:

```python
"""Tests for skills MCP tools."""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from mcp.server.fastmcp import FastMCP

from src.mcp_server.features.skills import register_skill_tools


@pytest.fixture
def mcp():
    server = FastMCP("test")
    register_skill_tools(server)
    return server


@pytest.fixture
def mock_response_200():
    resp = MagicMock()
    resp.status_code = 200
    return resp


@patch("src.mcp_server.features.skills.skill_tools.get_api_url", return_value="http://localhost:8181")
@pytest.mark.asyncio
async def test_find_skills_list(mock_api_url, mcp):
    """find_skills with no params returns all skills."""
    fn = mcp._tools["find_skills"].fn
    ctx = MagicMock()

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"skills": [{"name": "s1"}], "count": 1}

    with patch("httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_resp)

        result = await fn(ctx)
        data = json.loads(result)
        assert data["success"] is True
        assert data["count"] == 1


@patch("src.mcp_server.features.skills.skill_tools.get_api_url", return_value="http://localhost:8181")
@pytest.mark.asyncio
async def test_manage_skills_validate(mock_api_url, mcp):
    """manage_skills with action=validate calls validation endpoint."""
    fn = mcp._tools["manage_skills"].fn
    ctx = MagicMock()

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"valid": True, "errors": [], "warnings": []}

    with patch("httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_resp)

        result = await fn(ctx, action="validate", skill_content="---\nname: test\n---\n")
        data = json.loads(result)
        assert data["success"] is True
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/mcp_server/features/skills/test_skill_tools.py -v`
Expected: FAIL — module not found

**Step 3: Create the MCP skill tools module**

Create `python/src/mcp_server/features/skills/__init__.py`:

```python
from .skill_tools import register_skill_tools

__all__ = ["register_skill_tools"]
```

Create `python/src/mcp_server/features/skills/skill_tools.py`:

```python
"""Skills management MCP tools.

Provides find_skills and manage_skills tools for querying and managing
the Cortex skill registry from Claude Code.
"""
import json
import logging
from urllib.parse import urljoin

import httpx

from mcp.server.fastmcp import Context, FastMCP
from src.mcp_server.utils.error_handling import MCPErrorFormatter
from src.mcp_server.utils.timeout_config import get_default_timeout
from src.server.config.service_discovery import get_api_url

logger = logging.getLogger(__name__)


def register_skill_tools(mcp: FastMCP):
    """Register skills management tools with the MCP server."""

    @mcp.tool()
    async def find_skills(
        ctx: Context,
        skill_id: str | None = None,
        query: str | None = None,
        project_id: str | None = None,
        system_id: str | None = None,
        include_content: bool = False,
    ) -> str:
        """Find skills in the Cortex registry.

        Args:
            skill_id: Get a specific skill by ID (returns full content)
            query: Search skills by name or description
            project_id: List skills assigned to a project (with system install state)
            system_id: List skills installed on a specific system
            include_content: Include full SKILL.md content in list results (default: false)

        Returns:
            JSON with skills list or single skill details.

        Examples:
            find_skills()  # All skills
            find_skills(skill_id="uuid")  # Specific skill
            find_skills(project_id="uuid")  # Project skills with system state
        """
        try:
            api_url = get_api_url()
            timeout = get_default_timeout()

            async with httpx.AsyncClient(timeout=timeout) as client:
                # Single skill by ID
                if skill_id:
                    resp = await client.get(urljoin(api_url, f"/api/skills/{skill_id}"))
                    if resp.status_code == 200:
                        return json.dumps({"success": True, "skill": resp.json()})
                    elif resp.status_code == 404:
                        return MCPErrorFormatter.format_error("not_found", f"Skill {skill_id} not found")
                    return MCPErrorFormatter.from_http_error(resp, "get skill")

                # Project-scoped skills
                if project_id:
                    resp = await client.get(urljoin(api_url, f"/api/projects/{project_id}/skills"))
                    if resp.status_code == 200:
                        data = resp.json()
                        return json.dumps({"success": True, **data})
                    return MCPErrorFormatter.from_http_error(resp, "get project skills")

                # List all skills
                resp = await client.get(urljoin(api_url, "/api/skills"))
                if resp.status_code == 200:
                    data = resp.json()
                    skills = data.get("skills", [])

                    # Client-side search filter
                    if query:
                        q = query.lower()
                        skills = [
                            s for s in skills
                            if q in s.get("name", "").lower()
                            or q in s.get("description", "").lower()
                            or q in s.get("display_name", "").lower()
                        ]

                    return json.dumps({
                        "success": True,
                        "skills": skills,
                        "count": len(skills),
                    })

                return MCPErrorFormatter.from_http_error(resp, "list skills")

        except Exception as e:
            return MCPErrorFormatter.from_exception(e, "find skills")

    @mcp.tool()
    async def manage_skills(
        ctx: Context,
        action: str,
        # For sync
        local_skills: list[dict] | None = None,
        system_fingerprint: str | None = None,
        system_name: str | None = None,
        project_id: str | None = None,
        # For upload/validate
        skill_content: str | None = None,
        skill_name: str | None = None,
        # For install/remove
        skill_id: str | None = None,
        system_id: str | None = None,
    ) -> str:
        """Manage skills: sync, upload, validate, install, or remove.

        Args:
            action: Operation to perform — "sync", "upload", "validate", "install", "remove"

            For sync (called by auto-sync skill on startup):
                local_skills: List of {name, content_hash} from local disk
                system_fingerprint: SHA256 machine fingerprint
                system_name: Friendly name (required for first-time registration)
                project_id: Current project ID

            For upload (push local skill to Cortex registry):
                skill_content: Full SKILL.md content
                skill_name: Override name (for creating new skill from modified content)

            For validate (check skill without saving):
                skill_content: Full SKILL.md content to validate

            For install/remove (queue action from Cortex UI):
                skill_id: Skill to install or remove
                system_id: Target system
                project_id: Project scope

        Returns:
            JSON response. For sync: full sync report. For others: operation result.
        """
        try:
            api_url = get_api_url()
            timeout = get_default_timeout()

            async with httpx.AsyncClient(timeout=timeout) as client:

                if action == "validate":
                    if not skill_content:
                        return MCPErrorFormatter.format_error("validation", "skill_content is required for validate")
                    # Use a dummy skill_id for the validate endpoint
                    resp = await client.post(
                        urljoin(api_url, "/api/skills/_/validate"),
                        json={"content": skill_content},
                    )
                    if resp.status_code == 200:
                        return json.dumps({"success": True, "validation": resp.json()})
                    return MCPErrorFormatter.from_http_error(resp, "validate skill")

                elif action == "upload":
                    if not skill_content:
                        return MCPErrorFormatter.format_error("validation", "skill_content is required for upload")
                    # Parse frontmatter to extract name/description
                    import yaml
                    parts = skill_content.split("---", 2)
                    if len(parts) >= 3:
                        frontmatter = yaml.safe_load(parts[1]) or {}
                    else:
                        frontmatter = {}

                    name = skill_name or frontmatter.get("name", "unnamed-skill")
                    display_name = name.replace("-", " ").title()
                    description = frontmatter.get("description", "")

                    resp = await client.post(
                        urljoin(api_url, "/api/skills"),
                        json={
                            "name": name,
                            "display_name": display_name,
                            "description": description,
                            "content": skill_content,
                            "tags": [],
                        },
                    )
                    if resp.status_code == 201:
                        return json.dumps({"success": True, "skill": resp.json()})
                    elif resp.status_code == 409:
                        # Skill exists — try update
                        # Find by name first
                        find_resp = await client.get(urljoin(api_url, "/api/skills"))
                        if find_resp.status_code == 200:
                            skills = find_resp.json().get("skills", [])
                            existing = next((s for s in skills if s["name"] == name), None)
                            if existing:
                                update_resp = await client.put(
                                    urljoin(api_url, f"/api/skills/{existing['id']}"),
                                    json={"content": skill_content},
                                )
                                if update_resp.status_code == 200:
                                    return json.dumps({"success": True, "skill": update_resp.json(), "updated": True})
                    return MCPErrorFormatter.from_http_error(resp, "upload skill")

                elif action == "sync":
                    # Step 1: Register or identify system
                    system_data = None
                    is_new = False

                    if system_fingerprint:
                        # Check if system exists
                        systems_resp = await client.get(urljoin(api_url, "/api/systems"))
                        if systems_resp.status_code == 200:
                            systems = systems_resp.json().get("systems", [])
                            system_data = next(
                                (s for s in systems if s["fingerprint"] == system_fingerprint),
                                None,
                            )

                        if not system_data and system_name:
                            # Register new system — call the API directly via DB service
                            # For now, return is_new flag so the skill can prompt
                            is_new = True

                    # Step 2: Get all Cortex skills
                    skills_resp = await client.get(urljoin(api_url, "/api/skills"))
                    cortex_skills = skills_resp.json().get("skills", []) if skills_resp.status_code == 200 else []

                    # Step 3: Build sync report
                    # Since we need full content for pending installs, fetch individually for those
                    report = {
                        "system": {
                            "id": system_data["id"] if system_data else None,
                            "name": system_data["name"] if system_data else system_name,
                            "is_new": is_new,
                        },
                        "in_sync": [],
                        "local_changes": [],
                        "pending_install": [],
                        "pending_remove": [],
                        "unknown_local": [],
                    }

                    if local_skills:
                        local_by_name = {s["name"]: s for s in local_skills}
                        cortex_by_name = {s["name"]: s for s in cortex_skills}

                        for local in local_skills:
                            cortex = cortex_by_name.get(local["name"])
                            if not cortex:
                                report["unknown_local"].append({
                                    "name": local["name"],
                                    "content_hash": local["content_hash"],
                                })
                            elif local["content_hash"] == cortex.get("content_hash"):
                                report["in_sync"].append(local["name"])
                            else:
                                report["local_changes"].append({
                                    "name": local["name"],
                                    "skill_id": cortex["id"],
                                    "local_hash": local["content_hash"],
                                    "cortex_hash": cortex.get("content_hash"),
                                })

                    return json.dumps({"success": True, **report})

                elif action == "install":
                    if not all([skill_id, system_id, project_id]):
                        return MCPErrorFormatter.format_error("validation", "skill_id, system_id, and project_id required")
                    resp = await client.post(
                        urljoin(api_url, f"/api/projects/{project_id}/skills/{skill_id}/install"),
                        json={"system_ids": [system_id]},
                    )
                    if resp.status_code == 200:
                        return json.dumps({"success": True, **resp.json()})
                    return MCPErrorFormatter.from_http_error(resp, "install skill")

                elif action == "remove":
                    if not all([skill_id, system_id, project_id]):
                        return MCPErrorFormatter.format_error("validation", "skill_id, system_id, and project_id required")
                    resp = await client.post(
                        urljoin(api_url, f"/api/projects/{project_id}/skills/{skill_id}/remove"),
                        json={"system_ids": [system_id]},
                    )
                    if resp.status_code == 200:
                        return json.dumps({"success": True, **resp.json()})
                    return MCPErrorFormatter.from_http_error(resp, "remove skill")

                else:
                    return MCPErrorFormatter.format_error(
                        "validation",
                        f"Unknown action '{action}'. Use: sync, upload, validate, install, remove",
                    )

        except Exception as e:
            return MCPErrorFormatter.from_exception(e, f"manage_skills({action})")
```

**Step 4: Register in mcp_server.py**

In `python/src/mcp_server/mcp_server.py`, add a new try/except block after the feature tools registration (after line ~572):

```python
    try:
        from src.mcp_server.features.skills import register_skill_tools
        register_skill_tools(mcp)
        modules_registered += 1
        logger.info("✓ Skill tools registered")
    except ImportError as e:
        logger.warning(f"⚠ Skill tools module not available (optional): {e}")
    except Exception as e:
        logger.error(f"✗ Failed to register skill tools: {e}", exc_info=True)
```

**Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/mcp_server/features/skills/test_skill_tools.py -v`
Expected: ALL PASS

**Step 6: Commit**

```bash
git add python/src/mcp_server/features/skills/ python/tests/mcp_server/features/skills/ python/src/mcp_server/mcp_server.py
git commit -m "feat: add find_skills and manage_skills MCP tools"
```

---

### Task 8: Frontend — Types and service layer

**Files:**
- Create: `cortex-ui/src/features/projects/skills/types/index.ts`
- Create: `cortex-ui/src/features/projects/skills/services/skillService.ts`

**Step 1: Create types**

Create `cortex-ui/src/features/projects/skills/types/index.ts`:

```typescript
export interface Skill {
  id: string;
  name: string;
  display_name: string;
  description: string;
  content?: string;
  content_hash: string;
  version: number;
  is_required: boolean;
  is_validated: boolean;
  tags: string[];
  created_at: string;
  updated_at: string;
}

export interface System {
  id: string;
  fingerprint: string;
  name: string;
  hostname: string | null;
  os: string | null;
  last_seen_at: string;
  created_at: string;
}

export interface SystemSkill {
  id: string;
  system_id: string;
  skill_id: string;
  project_id: string;
  status: "pending_install" | "installed" | "pending_remove" | "removed";
  installed_content_hash: string | null;
  installed_version: number | null;
  has_local_changes: boolean;
  updated_at: string;
  cortex_skills?: Skill;
}

export interface SystemWithSkills extends System {
  skills: SystemSkill[];
}

export interface ProjectSkillsResponse {
  all_skills: Skill[];
  systems: SystemWithSkills[];
}

export interface ProjectSystemsResponse {
  systems: System[];
  count: number;
}

export interface SkillsListResponse {
  skills: Skill[];
  count: number;
}
```

**Step 2: Create service**

Create `cortex-ui/src/features/projects/skills/services/skillService.ts`:

```typescript
import { callAPIWithETag } from "@/features/shared/api/apiClient";
import type { ProjectSkillsResponse, ProjectSystemsResponse, SkillsListResponse } from "../types";

export const skillService = {
  async getProjectSkills(projectId: string): Promise<ProjectSkillsResponse> {
    return callAPIWithETag<ProjectSkillsResponse>(`/api/projects/${projectId}/skills`);
  },

  async getProjectSystems(projectId: string): Promise<ProjectSystemsResponse> {
    return callAPIWithETag<ProjectSystemsResponse>(`/api/projects/${projectId}/systems`);
  },

  async getAllSkills(): Promise<SkillsListResponse> {
    return callAPIWithETag<SkillsListResponse>("/api/skills");
  },

  async installSkill(projectId: string, skillId: string, systemIds: string[]): Promise<void> {
    const response = await fetch(`/api/projects/${projectId}/skills/${skillId}/install`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ system_ids: systemIds }),
    });
    if (!response.ok) throw new Error(`Failed to install skill: ${response.statusText}`);
  },

  async removeSkill(projectId: string, skillId: string, systemIds: string[]): Promise<void> {
    const response = await fetch(`/api/projects/${projectId}/skills/${skillId}/remove`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ system_ids: systemIds }),
    });
    if (!response.ok) throw new Error(`Failed to remove skill: ${response.statusText}`);
  },
};
```

**Step 3: Commit**

```bash
git add cortex-ui/src/features/projects/skills/
git commit -m "feat: add skills types and service layer"
```

---

### Task 9: Frontend — TanStack Query hooks

**Files:**
- Create: `cortex-ui/src/features/projects/skills/hooks/useSkillQueries.ts`

**Step 1: Create query hooks**

Create `cortex-ui/src/features/projects/skills/hooks/useSkillQueries.ts`:

```typescript
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { DISABLED_QUERY_KEY, STALE_TIMES } from "@/features/shared/config/queryPatterns";
import { skillService } from "../services/skillService";

export const skillKeys = {
  all: ["skills"] as const,
  lists: () => [...skillKeys.all, "list"] as const,
  byProject: (projectId: string) => ["projects", projectId, "skills"] as const,
  projectSystems: (projectId: string) => ["projects", projectId, "systems"] as const,
};

export function useProjectSkills(projectId: string | undefined) {
  return useQuery({
    queryKey: projectId ? skillKeys.byProject(projectId) : DISABLED_QUERY_KEY,
    queryFn: () =>
      projectId ? skillService.getProjectSkills(projectId) : Promise.reject("No project ID"),
    enabled: !!projectId,
    staleTime: STALE_TIMES.normal,
  });
}

export function useProjectSystems(projectId: string | undefined) {
  return useQuery({
    queryKey: projectId ? skillKeys.projectSystems(projectId) : DISABLED_QUERY_KEY,
    queryFn: () =>
      projectId ? skillService.getProjectSystems(projectId) : Promise.reject("No project ID"),
    enabled: !!projectId,
    staleTime: STALE_TIMES.normal,
  });
}

export function useAllSkills() {
  return useQuery({
    queryKey: skillKeys.lists(),
    queryFn: () => skillService.getAllSkills(),
    staleTime: STALE_TIMES.normal,
  });
}

export function useInstallSkill() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      projectId,
      skillId,
      systemIds,
    }: {
      projectId: string;
      skillId: string;
      systemIds: string[];
    }) => skillService.installSkill(projectId, skillId, systemIds),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: skillKeys.byProject(variables.projectId) });
    },
  });
}

export function useRemoveSkill() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      projectId,
      skillId,
      systemIds,
    }: {
      projectId: string;
      skillId: string;
      systemIds: string[];
    }) => skillService.removeSkill(projectId, skillId, systemIds),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: skillKeys.byProject(variables.projectId) });
    },
  });
}
```

**Step 2: Commit**

```bash
git add cortex-ui/src/features/projects/skills/hooks/
git commit -m "feat: add TanStack Query hooks for skills management"
```

---

### Task 10: Frontend — SkillStatusBadge and SystemCard components

**Files:**
- Create: `cortex-ui/src/features/projects/skills/components/SkillStatusBadge.tsx`
- Create: `cortex-ui/src/features/projects/skills/components/SystemCard.tsx`

**Step 1: Create SkillStatusBadge**

Create `cortex-ui/src/features/projects/skills/components/SkillStatusBadge.tsx`:

```tsx
interface SkillStatusBadgeProps {
  status: "pending_install" | "installed" | "pending_remove" | "removed";
  hasLocalChanges?: boolean;
}

const STATUS_CONFIG = {
  installed: { label: "Installed", className: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30" },
  pending_install: { label: "Pending Install", className: "bg-yellow-500/20 text-yellow-400 border-yellow-500/30" },
  pending_remove: { label: "Pending Remove", className: "bg-red-500/20 text-red-400 border-red-500/30" },
  removed: { label: "Removed", className: "bg-zinc-500/20 text-zinc-400 border-zinc-500/30" },
  local_changes: { label: "Local Changes", className: "bg-orange-500/20 text-orange-400 border-orange-500/30" },
};

export function SkillStatusBadge({ status, hasLocalChanges }: SkillStatusBadgeProps) {
  const effectiveStatus = hasLocalChanges && status === "installed" ? "local_changes" : status;
  const config = STATUS_CONFIG[effectiveStatus];

  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border ${config.className}`}>
      {config.label}
    </span>
  );
}
```

**Step 2: Create SystemCard**

Create `cortex-ui/src/features/projects/skills/components/SystemCard.tsx`:

```tsx
import type { SystemWithSkills } from "../types";

interface SystemCardProps {
  system: SystemWithSkills;
  isSelected: boolean;
  onClick: () => void;
}

export function SystemCard({ system, isSelected, onClick }: SystemCardProps) {
  const isOnline = isRecentlyActive(system.last_seen_at);
  const skillCount = system.skills?.length ?? 0;

  return (
    <button
      type="button"
      onClick={onClick}
      className={`w-full text-left p-3 rounded-lg border transition-colors ${
        isSelected
          ? "border-cyan-500/50 bg-cyan-500/10"
          : "border-white/10 bg-white/5 hover:border-white/20 hover:bg-white/[0.07]"
      }`}
    >
      <div className="flex items-center gap-2">
        <span className={`w-2 h-2 rounded-full ${isOnline ? "bg-emerald-400" : "bg-zinc-500"}`} />
        <span className="font-medium text-sm text-white truncate">{system.name}</span>
      </div>
      <div className="mt-1 text-xs text-zinc-400">
        {skillCount} skill{skillCount !== 1 ? "s" : ""}
        {system.hostname && ` · ${system.hostname}`}
      </div>
    </button>
  );
}

function isRecentlyActive(lastSeen: string): boolean {
  const fiveMinutes = 5 * 60 * 1000;
  return Date.now() - new Date(lastSeen).getTime() < fiveMinutes;
}
```

**Step 3: Commit**

```bash
git add cortex-ui/src/features/projects/skills/components/
git commit -m "feat: add SkillStatusBadge and SystemCard components"
```

---

### Task 11: Frontend — SystemSkillList and SkillsTab

**Files:**
- Create: `cortex-ui/src/features/projects/skills/components/SystemSkillList.tsx`
- Create: `cortex-ui/src/features/projects/skills/SkillsTab.tsx`

**Step 1: Create SystemSkillList**

Create `cortex-ui/src/features/projects/skills/components/SystemSkillList.tsx`:

```tsx
import { SkillStatusBadge } from "./SkillStatusBadge";
import type { Skill, SystemSkill } from "../types";

interface SystemSkillListProps {
  systemSkills: SystemSkill[];
  allSkills: Skill[];
  onInstall: (skillId: string) => void;
}

export function SystemSkillList({ systemSkills, allSkills, onInstall }: SystemSkillListProps) {
  const installedSkillIds = new Set(systemSkills.map((ss) => ss.skill_id));
  const availableSkills = allSkills.filter((s) => !installedSkillIds.has(s.id));

  return (
    <div className="space-y-4">
      {systemSkills.length > 0 && (
        <div>
          <h4 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">
            Installed Skills
          </h4>
          <div className="space-y-1">
            {systemSkills.map((ss) => (
              <div
                key={ss.id}
                className="flex items-center justify-between p-2 rounded-md bg-white/5"
              >
                <span className="text-sm text-white">
                  {ss.cortex_skills?.display_name ?? ss.skill_id}
                </span>
                <SkillStatusBadge status={ss.status} hasLocalChanges={ss.has_local_changes} />
              </div>
            ))}
          </div>
        </div>
      )}

      {availableSkills.length > 0 && (
        <div>
          <h4 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">
            Available
          </h4>
          <div className="space-y-1">
            {availableSkills.map((skill) => (
              <div
                key={skill.id}
                className="flex items-center justify-between p-2 rounded-md bg-white/5"
              >
                <div>
                  <span className="text-sm text-white">{skill.display_name}</span>
                  {skill.is_required && (
                    <span className="ml-2 text-xs text-cyan-400">Required</span>
                  )}
                </div>
                <button
                  type="button"
                  onClick={() => onInstall(skill.id)}
                  className="px-3 py-1 text-xs rounded-md bg-cyan-500/20 text-cyan-400 border border-cyan-500/30 hover:bg-cyan-500/30 transition-colors"
                >
                  Install
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {systemSkills.length === 0 && availableSkills.length === 0 && (
        <div className="text-center py-8 text-zinc-500 text-sm">
          No skills in the registry yet. Skills are added when systems sync.
        </div>
      )}
    </div>
  );
}
```

**Step 2: Create SkillsTab**

Create `cortex-ui/src/features/projects/skills/SkillsTab.tsx`:

```tsx
import { useState } from "react";
import { useProjectSkills, useInstallSkill } from "./hooks/useSkillQueries";
import { SystemCard } from "./components/SystemCard";
import { SystemSkillList } from "./components/SystemSkillList";

interface SkillsTabProps {
  projectId: string;
}

export function SkillsTab({ projectId }: SkillsTabProps) {
  const { data, isLoading, error } = useProjectSkills(projectId);
  const installSkill = useInstallSkill();
  const [selectedSystemId, setSelectedSystemId] = useState<string | null>(null);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12 text-zinc-400">
        Loading skills...
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center py-12 text-red-400">
        Failed to load skills: {error.message}
      </div>
    );
  }

  const systems = data?.systems ?? [];
  const allSkills = data?.all_skills ?? [];
  const selectedSystem = systems.find((s) => s.id === selectedSystemId) ?? systems[0];

  const handleInstall = (skillId: string) => {
    if (!selectedSystem) return;
    installSkill.mutate({
      projectId,
      skillId,
      systemIds: [selectedSystem.id],
    });
  };

  if (systems.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-zinc-400 space-y-2">
        <p className="text-sm">No systems registered to this project yet.</p>
        <p className="text-xs text-zinc-500">
          Systems are registered when they connect via the Cortex MCP server and run a skill sync.
        </p>
      </div>
    );
  }

  return (
    <div className="flex gap-4 h-full">
      {/* Systems list */}
      <div className="w-64 flex-shrink-0 space-y-2">
        <h3 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">
          Systems
        </h3>
        {systems.map((system) => (
          <SystemCard
            key={system.id}
            system={system}
            isSelected={system.id === (selectedSystem?.id ?? null)}
            onClick={() => setSelectedSystemId(system.id)}
          />
        ))}
      </div>

      {/* Detail panel */}
      <div className="flex-1 min-w-0">
        {selectedSystem && (
          <div className="space-y-4">
            <div className="border-b border-white/10 pb-3">
              <h3 className="text-lg font-medium text-white">{selectedSystem.name}</h3>
              <div className="flex gap-4 mt-1 text-xs text-zinc-400">
                {selectedSystem.hostname && <span>Host: {selectedSystem.hostname}</span>}
                {selectedSystem.os && <span>OS: {selectedSystem.os}</span>}
                <span>Last seen: {new Date(selectedSystem.last_seen_at).toLocaleString()}</span>
              </div>
            </div>

            <SystemSkillList
              systemSkills={selectedSystem.skills}
              allSkills={allSkills}
              onInstall={handleInstall}
            />
          </div>
        )}
      </div>
    </div>
  );
}
```

**Step 3: Commit**

```bash
git add cortex-ui/src/features/projects/skills/
git commit -m "feat: add SkillsTab with system list and skill management"
```

---

### Task 12: Frontend — Integrate Skills tab into ProjectsView

**Files:**
- Modify: `cortex-ui/src/features/projects/views/ProjectsView.tsx`

**Step 1: Add import**

At the top of `ProjectsView.tsx` (near line 17, with other tab imports), add:

```typescript
import { SkillsTab } from "../skills/SkillsTab";
import { Puzzle } from "lucide-react";
```

**Step 2: Add to horizontal PillNavigation items**

At line ~215-219, add the Skills item between Knowledge and Tasks:

```typescript
items={[
  { id: "docs", label: "Docs", icon: <FileText className="w-4 h-4" /> },
  { id: "knowledge", label: "Knowledge", icon: <Library className="w-4 h-4" /> },
  { id: "skills", label: "Skills", icon: <Puzzle className="w-4 h-4" /> },
  { id: "tasks", label: "Tasks", icon: <ListTodo className="w-4 h-4" /> },
]}
```

**Step 3: Add to sidebar PillNavigation items**

At line ~296-299, add Skills:

```typescript
items={[
  { id: "docs", label: "Docs", icon: <FileText className="w-4 h-4" /> },
  { id: "skills", label: "Skills", icon: <Puzzle className="w-4 h-4" /> },
  { id: "tasks", label: "Tasks", icon: <ListTodo className="w-4 h-4" /> },
]}
```

**Step 4: Add conditional rendering (horizontal layout)**

At line ~233-235, add after the knowledge tab:

```typescript
{activeTab === "docs" && <DocsTab project={selectedProject} />}
{activeTab === "knowledge" && <KnowledgeTab projectId={selectedProject.id} />}
{activeTab === "skills" && <SkillsTab projectId={selectedProject.id} />}
{activeTab === "tasks" && <TasksTab projectId={selectedProject.id} />}
```

**Step 5: Add conditional rendering (sidebar layout)**

At line ~314-316, add the same:

```typescript
{activeTab === "docs" && <DocsTab project={selectedProject} />}
{activeTab === "knowledge" && <KnowledgeTab projectId={selectedProject.id} />}
{activeTab === "skills" && <SkillsTab projectId={selectedProject.id} />}
{activeTab === "tasks" && <TasksTab projectId={selectedProject.id} />}
```

**Step 6: Run TypeScript check**

Run: `cd cortex-ui && npx tsc --noEmit 2>&1 | grep "src/features/projects/skills"`
Expected: No errors

**Step 7: Commit**

```bash
git add cortex-ui/src/features/projects/views/ProjectsView.tsx
git commit -m "feat: integrate Skills tab into project view"
```

---

### Task 13: Create the cortex-skill-sync SKILL.md

The auto-sync skill that runs on startup and reconciles local vs Cortex state.

**Files:**
- Create: `integrations/claude-code/skills/cortex-skill-sync/SKILL.md`

**Step 1: Write the skill**

Create `integrations/claude-code/skills/cortex-skill-sync/SKILL.md`:

```markdown
---
name: cortex-skill-sync
description: Sync local Claude Code skills with the Cortex skill registry. Detects new skills, local modifications, and pending installs. Use when "sync skills", "check skills", "update skills", or at startup when sync is stale.
---

# Cortex Skill Sync

Synchronizes local Claude Code skills with the Cortex skill registry. Detects drift, handles conflict resolution, installs pending skills, and uploads new local skills.

**Invocation:** `/cortex-skill-sync`
**Auto-trigger:** Runs automatically when any Cortex skill detects last_skill_sync > 24h in `.claude/cortex-state.json`

---

## Phase 0: Compute Machine Fingerprint

### 0a. Gather system info

```bash
hostname
```

```bash
whoami
```

```bash
uname -s
```

### 0b. Compute fingerprint

Concatenate: `<hostname>|<username>|<os>` and compute SHA256:

```bash
echo -n "$(hostname)|$(whoami)|$(uname -s)" | sha256sum | cut -d' ' -f1
```

Store as `system_fingerprint`.

---

## Phase 1: Scan Local Skills

### 1a. Find all SKILL.md files

Scan these directories for SKILL.md files:
- `.claude/skills/` (user-installed skills)
- `integrations/claude-code/skills/` (repo skills, if in Cortex repo)
- Any directory listed in `.claude/cortex-state.json` under `skill_directories`

```
Glob: .claude/skills/**/SKILL.md
Glob: integrations/claude-code/skills/**/SKILL.md
```

### 1b. Parse each skill

For each SKILL.md found:
1. Read the file content
2. Parse YAML frontmatter to extract `name`
3. Compute SHA256 hash of the full content:
   ```bash
   sha256sum <filepath> | cut -d' ' -f1
   ```

Build `local_skills` list: `[{name, content_hash}]`

---

## Phase 2: Sync with Cortex

### 2a. Read project state

Read `.claude/cortex-state.json` for `cortex_project_id`.

If no project ID:
> "No Cortex project linked. Run `/link-to-project` first to associate this repo with an Cortex project."

Stop here.

### 2b. Call sync

```
manage_skills(
    action="sync",
    local_skills=<local_skills list>,
    system_fingerprint="<fingerprint>",
    project_id="<cortex_project_id>"
)
```

### 2c. Handle first-time registration

If response has `system.is_new == true`:

Ask the user:
> "This is the first time this machine is connecting to Cortex. What name should we use for this system?"
>
> Suggestion: `<hostname>`

Store the user's choice, then re-call:
```
manage_skills(
    action="sync",
    local_skills=<local_skills list>,
    system_fingerprint="<fingerprint>",
    system_name="<user-provided-name>",
    project_id="<cortex_project_id>"
)
```

---

## Phase 3: Process Sync Results

### 3a. Install pending skills

For each item in `pending_install`:
1. Write the `content` to `.claude/skills/<name>/SKILL.md`
2. Report: "Installed skill: <name>"

### 3b. Remove pending skills

For each item in `pending_remove`:
1. Delete `.claude/skills/<name>/SKILL.md`
2. Report: "Removed skill: <name>"

### 3c. Resolve local changes

For each item in `local_changes`, ask the user:

> "Skill **<name>** has local modifications (local hash: `<local_hash>`, Cortex hash: `<cortex_hash>`). What would you like to do?"

Options:
- **Update Source** — Push local content to Cortex as a new version
- **Save as Project Version** — Store as a project-specific override
- **Create New Skill** — Upload as a new skill with a different name
- **Discard Changes** — Overwrite local with Cortex version

**If Update Source:**
Read the local file content, then:
```
manage_skills(action="upload", skill_content="<local content>")
```

**If Save as Project Version:**
Read the local file content. The backend stores it as a project override (future API call).

**If Create New Skill:**
Ask for a new name, then:
```
manage_skills(action="validate", skill_content="<local content>")
```
If validation passes:
```
manage_skills(action="upload", skill_content="<local content>", skill_name="<new-name>")
```

**If Discard Changes:**
Fetch the Cortex version via `find_skills(skill_id="<skill_id>")` and overwrite the local file.

### 3d. Handle unknown local skills

For each item in `unknown_local`, ask the user:

> "Found local skill **<name>** not in Cortex. Would you like to upload it to the registry?"

Options:
- **Upload** — Validate and upload
- **Skip** — Leave as local-only

**If Upload:**
Read the local file, then:
```
manage_skills(action="validate", skill_content="<content>")
```
If validation passes (or user accepts warnings):
```
manage_skills(action="upload", skill_content="<content>")
```
If validation has errors, show them and ask user to fix.

---

## Phase 4: Update State

### 4a. Write sync timestamp

Update `.claude/cortex-state.json`:
```json
{
  "last_skill_sync": "<ISO timestamp>",
  "system_fingerprint": "<fingerprint>",
  "system_name": "<name>"
}
```

Merge with existing state — do not overwrite other fields.

### 4b. Summary

> "**Skill sync complete:**
> - In sync: <N> skills
> - Installed: <list or 'none'>
> - Removed: <list or 'none'>
> - Updated: <list or 'none'>
> - Uploaded: <list or 'none'>
> - Skipped: <list or 'none'>"

---

## Important Notes

### Sync Freshness

Other Cortex skills check sync freshness in their Phase 0:
```
Read .claude/cortex-state.json
If last_skill_sync is missing or older than 24h:
  → Run /cortex-skill-sync before continuing
```

### Skill File Locations

- **Installed skills:** `.claude/skills/<name>/SKILL.md`
- **Repo skills:** `integrations/claude-code/skills/<name>/SKILL.md`
- Skills are identified by their frontmatter `name` field, not directory name

### Error Recovery

- If Cortex is unreachable, skip sync and continue with stale state
- If a single skill install/upload fails, continue with remaining operations
- Always save the sync timestamp even if some operations failed (prevents retry loops)
```

**Step 2: Commit**

```bash
git add integrations/claude-code/skills/cortex-skill-sync/
git commit -m "feat: add cortex-skill-sync skill for startup skill synchronization"
```

---

### Task 14: Update existing skills with sync freshness check

**Files:**
- Modify: `integrations/claude-code/skills/cortex-memory/SKILL.md`
- Modify: `integrations/claude-code/skills/cortex-link-project/SKILL.md`

**Step 1: Add sync check to cortex-memory Phase 0**

In `integrations/claude-code/skills/cortex-memory/SKILL.md`, add after the health check in Phase 0 (after the `health_check()` call and before the state file loading):

```markdown
### 0b. Check skill sync freshness

Read `.claude/cortex-state.json`. If `last_skill_sync` is missing or older than 24 hours:
> "Skills are out of sync. Running skill sync first..."

Run `/cortex-skill-sync` before continuing.
```

Renumber subsequent steps (0b becomes 0c, etc.).

**Step 2: Add sync check to cortex-link-project Phase 0**

In `integrations/claude-code/skills/cortex-link-project/SKILL.md`, add the same block after the health check in Phase 0 (after step 0a, before 0b):

```markdown
### 0b. Check skill sync freshness

Read `.claude/cortex-state.json`. If `last_skill_sync` is missing or older than 24 hours:
> "Skills are out of sync. Running skill sync first..."

Run `/cortex-skill-sync` before continuing.
```

Renumber subsequent steps.

**Step 3: Commit**

```bash
git add integrations/claude-code/skills/cortex-memory/SKILL.md integrations/claude-code/skills/cortex-link-project/SKILL.md
git commit -m "feat: add sync freshness check to existing Cortex skills"
```

---

### Task 15: Run full test suite and verify

**Step 1: Run all backend skills tests**

Run: `uv run pytest tests/server/services/skills/ -v`
Expected: ALL PASS

**Step 2: Run all MCP skills tests**

Run: `uv run pytest tests/mcp_server/features/skills/ -v`
Expected: ALL PASS

**Step 3: Run full backend test suite**

Run: `uv run pytest tests/ -v --tb=short`
Expected: ALL PASS (no regressions)

**Step 4: Run backend linter**

Run: `uv run ruff check src/server/services/skills/ src/server/api_routes/skills_api.py src/mcp_server/features/skills/`
Expected: No errors

**Step 5: Run frontend TypeScript check**

Run: `cd cortex-ui && npx tsc --noEmit 2>&1 | grep -E "(error|skills)"`
Expected: No errors in skills files

**Step 6: If any tests or checks fail, fix them before proceeding**

---

### Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | Database migration (5 tables) | `014_add_skills_management_tables.sql` |
| 2 | SkillValidationService | `skill_validation_service.py` + tests |
| 3 | SystemService | `system_service.py` + tests |
| 4 | SkillService | `skill_service.py` + tests |
| 5 | SkillSyncService | `skill_sync_service.py` + tests |
| 6 | REST API endpoints | `skills_api.py` + main.py registration |
| 7 | MCP tools (find_skills, manage_skills) | `skill_tools.py` + mcp_server.py registration |
| 8 | Frontend types + service | `types/index.ts`, `skillService.ts` |
| 9 | TanStack Query hooks | `useSkillQueries.ts` |
| 10 | SkillStatusBadge + SystemCard | React components |
| 11 | SystemSkillList + SkillsTab | Main tab component |
| 12 | ProjectsView integration | Add Skills tab to both layouts |
| 13 | cortex-skill-sync SKILL.md | New sync skill |
| 14 | Update existing skills | Add sync freshness check to Phase 0 |
| 15 | Full test suite verification | All tests pass, no regressions |
