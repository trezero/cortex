# Knowledge Materialization Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enable Cortex agents to autonomously detect knowledge gaps, query the Vector DB, synthesize results via LLM, and write permanent Markdown documentation into project repos.

**Architecture:** Service Pipeline — MCP tool calls REST API, which orchestrates MaterializationService (search + synthesis + file write + DB tracking). Frontend shows progress, history, and toast notifications.

**Tech Stack:** Python 3.12, FastAPI, PydanticAI, Supabase, TanStack Query v5, React 18, TypeScript 5

**Design Doc:** `docs/plans/2026-03-08-knowledge-materialization-design.md`

---

## Phase 1: Database Schema

### Task 1: Create migration file

**Files:**
- Create: `migration/0.1.0/018_add_materialization_history.sql`

**Step 1: Write the migration**

```sql
-- 018_add_materialization_history.sql
-- Tracks knowledge materialization events across projects

CREATE TABLE IF NOT EXISTS cortex_materialization_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id TEXT NOT NULL,
    project_path TEXT NOT NULL,
    topic TEXT NOT NULL,
    filename TEXT NOT NULL,
    file_path TEXT NOT NULL,
    source_ids TEXT[] DEFAULT '{}',
    original_urls TEXT[] DEFAULT '{}',
    synthesis_model TEXT,
    word_count INTEGER DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active',
    access_count INTEGER DEFAULT 0,
    last_accessed_at TIMESTAMPTZ,
    materialized_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_mat_history_project ON cortex_materialization_history(project_id);
CREATE INDEX IF NOT EXISTS idx_mat_history_status ON cortex_materialization_history(status);
CREATE INDEX IF NOT EXISTS idx_mat_history_topic ON cortex_materialization_history(topic);
CREATE INDEX IF NOT EXISTS idx_mat_history_project_topic ON cortex_materialization_history(project_id, topic);
```

**Step 2: Apply migration to local database**

Run: `psql` or Supabase SQL editor to execute the migration.
Expected: Table `cortex_materialization_history` created with 4 indexes.

**Step 3: Commit**

```bash
git add migration/0.1.0/018_add_materialization_history.sql
git commit -m "feat: add materialization_history table (migration 018)"
```

---

## Phase 2: Backend Services

### Task 2: MaterializationService — models and DB operations

**Files:**
- Create: `python/src/server/services/knowledge/materialization_service.py`
- Create: `python/src/server/models/materialization.py`
- Test: `python/tests/server/services/test_materialization_service.py`

**Step 1: Write the Pydantic models**

Create `python/src/server/models/materialization.py`:

```python
"""Models for knowledge materialization."""

from datetime import datetime

from pydantic import BaseModel, Field


class MaterializationRequest(BaseModel):
    topic: str = Field(description="Topic to materialize")
    project_id: str = Field(description="Cortex project ID")
    project_path: str = Field(description="Filesystem path to project repo")
    agent_context: str | None = Field(default=None, description="Additional context from the requesting agent")


class MaterializationResult(BaseModel):
    success: bool
    file_path: str | None = None
    filename: str | None = None
    word_count: int = 0
    summary: str | None = None
    materialization_id: str | None = None
    reason: str | None = None


class MaterializationRecord(BaseModel):
    id: str
    project_id: str
    project_path: str
    topic: str
    filename: str
    file_path: str
    source_ids: list[str] = []
    original_urls: list[str] = []
    synthesis_model: str | None = None
    word_count: int = 0
    status: str = "active"
    access_count: int = 0
    last_accessed_at: datetime | None = None
    materialized_at: datetime
    updated_at: datetime
    metadata: dict = {}
```

**Step 2: Write failing tests for MaterializationService**

Create `python/tests/server/services/test_materialization_service.py`:

```python
"""Tests for MaterializationService."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.server.services.knowledge.materialization_service import MaterializationService


@pytest.fixture
def mock_supabase():
    client = MagicMock()
    client.table = MagicMock(return_value=client)
    client.select = MagicMock(return_value=client)
    client.insert = MagicMock(return_value=client)
    client.update = MagicMock(return_value=client)
    client.delete = MagicMock(return_value=client)
    client.eq = MagicMock(return_value=client)
    client.execute = MagicMock(return_value=MagicMock(data=[]))
    return client


@pytest.fixture
def service(mock_supabase):
    return MaterializationService(supabase_client=mock_supabase)


@pytest.mark.asyncio
async def test_check_existing_returns_none_when_not_found(service, mock_supabase):
    mock_supabase.execute.return_value.data = []
    result = await service.check_existing("auth middleware", "proj_123")
    assert result is None


@pytest.mark.asyncio
async def test_check_existing_returns_record_when_found(service, mock_supabase):
    mock_supabase.execute.return_value.data = [{
        "id": "abc-123",
        "project_id": "proj_123",
        "project_path": "/home/user/project",
        "topic": "auth middleware",
        "filename": "auth-middleware.md",
        "file_path": ".cortex/knowledge/auth-middleware.md",
        "source_ids": [],
        "original_urls": [],
        "synthesis_model": "gpt-4.1-nano",
        "word_count": 500,
        "status": "active",
        "access_count": 3,
        "last_accessed_at": "2026-03-08T10:00:00Z",
        "materialized_at": "2026-03-08T10:00:00Z",
        "updated_at": "2026-03-08T10:00:00Z",
        "metadata": {},
    }]
    result = await service.check_existing("auth middleware", "proj_123")
    assert result is not None
    assert result.topic == "auth middleware"


@pytest.mark.asyncio
async def test_list_materializations(service, mock_supabase):
    mock_supabase.execute.return_value.data = []
    result = await service.list_materializations(project_id="proj_123")
    assert result == []


@pytest.mark.asyncio
async def test_mark_accessed(service, mock_supabase):
    mock_supabase.execute.return_value.data = [{"access_count": 4}]
    await service.mark_accessed("abc-123")
    mock_supabase.table.assert_called_with("cortex_materialization_history")


@pytest.mark.asyncio
async def test_create_record(service, mock_supabase):
    mock_supabase.execute.return_value.data = [{"id": "new-id"}]
    record_id = await service.create_record(
        project_id="proj_123",
        project_path="/home/user/project",
        topic="auth middleware",
        filename="auth-middleware.md",
        file_path=".cortex/knowledge/auth-middleware.md",
        source_ids=["src_1"],
        original_urls=["https://docs.example.com"],
        synthesis_model="gpt-4.1-nano",
        word_count=500,
    )
    assert record_id == "new-id"
```

**Step 3: Run tests to verify they fail**

Run: `cd /home/winadmin/projects/Trinity/cortex && uv run pytest python/tests/server/services/test_materialization_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.server.services.knowledge.materialization_service'`

**Step 4: Implement MaterializationService (DB operations only)**

Create `python/src/server/services/knowledge/materialization_service.py`:

```python
"""
MaterializationService — orchestrates knowledge materialization.

Coordinates RAG search, LLM synthesis, file writing, and DB tracking
to materialize Vector DB knowledge into local project repos.
"""

from datetime import datetime, timezone
from typing import Any

from ...config.logfire_config import get_logger
from ...models.materialization import MaterializationRecord, MaterializationResult
from ...utils import get_supabase_client

logger = get_logger(__name__)

TABLE = "cortex_materialization_history"


class MaterializationService:
    def __init__(self, supabase_client=None):
        self.supabase = supabase_client or get_supabase_client()

    async def check_existing(self, topic: str, project_id: str) -> MaterializationRecord | None:
        """Check if topic is already materialized (active or pending) for this project."""
        result = (
            self.supabase.table(TABLE)
            .select("*")
            .eq("project_id", project_id)
            .eq("topic", topic)
            .in_("status", ["active", "pending"])
            .execute()
        )
        if result.data:
            return MaterializationRecord(**result.data[0])
        return None

    async def list_materializations(
        self, project_id: str | None = None, status: str | None = None
    ) -> list[MaterializationRecord]:
        """List materialization records with optional filters."""
        query = self.supabase.table(TABLE).select("*")
        if project_id:
            query = query.eq("project_id", project_id)
        if status:
            query = query.eq("status", status)
        query = query.order("materialized_at", desc=True)
        result = query.execute()
        return [MaterializationRecord(**row) for row in result.data]

    async def create_record(
        self,
        project_id: str,
        project_path: str,
        topic: str,
        filename: str,
        file_path: str,
        source_ids: list[str],
        original_urls: list[str],
        synthesis_model: str,
        word_count: int,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Create a materialization history record. Returns the record ID."""
        result = (
            self.supabase.table(TABLE)
            .insert({
                "project_id": project_id,
                "project_path": project_path,
                "topic": topic,
                "filename": filename,
                "file_path": file_path,
                "source_ids": source_ids,
                "original_urls": original_urls,
                "synthesis_model": synthesis_model,
                "word_count": word_count,
                "metadata": metadata or {},
            })
            .execute()
        )
        return result.data[0]["id"]

    async def mark_accessed(self, materialization_id: str) -> None:
        """Increment access_count and update last_accessed_at."""
        now = datetime.now(timezone.utc).isoformat()
        self.supabase.table(TABLE).update({
            "access_count": self.supabase.rpc("", {}).data,  # handled below
            "last_accessed_at": now,
            "updated_at": now,
        }).eq("id", materialization_id).execute()
        # Use raw SQL for atomic increment
        self.supabase.rpc("increment_access_count", {"record_id": materialization_id}).execute()

    async def update_status(self, materialization_id: str, status: str) -> None:
        """Update the status of a materialization record."""
        now = datetime.now(timezone.utc).isoformat()
        self.supabase.table(TABLE).update({
            "status": status,
            "updated_at": now,
        }).eq("id", materialization_id).execute()

    async def delete_record(self, materialization_id: str) -> None:
        """Delete a materialization record."""
        self.supabase.table(TABLE).delete().eq("id", materialization_id).execute()

    async def get_record(self, materialization_id: str) -> MaterializationRecord | None:
        """Get a single materialization record by ID."""
        result = (
            self.supabase.table(TABLE)
            .select("*")
            .eq("id", materialization_id)
            .execute()
        )
        if result.data:
            return MaterializationRecord(**result.data[0])
        return None
```

Note: The `mark_accessed` method uses an RPC for atomic increment. We'll need a simple Postgres function:

```sql
-- Add to migration 018:
CREATE OR REPLACE FUNCTION increment_access_count(record_id UUID)
RETURNS VOID AS $$
BEGIN
    UPDATE cortex_materialization_history
    SET access_count = access_count + 1,
        last_accessed_at = NOW(),
        updated_at = NOW()
    WHERE id = record_id;
END;
$$ LANGUAGE plpgsql;
```

**Step 5: Run tests to verify they pass**

Run: `cd /home/winadmin/projects/Trinity/cortex && uv run pytest python/tests/server/services/test_materialization_service.py -v`
Expected: All 5 tests PASS

**Step 6: Commit**

```bash
git add python/src/server/models/materialization.py python/src/server/services/knowledge/materialization_service.py python/tests/server/services/test_materialization_service.py
git commit -m "feat: add MaterializationService with DB operations and models"
```

---

### Task 3: SynthesizerAgent

**Files:**
- Create: `python/src/agents/synthesizer_agent.py`
- Test: `python/tests/agents/test_synthesizer_agent.py`

**Step 1: Write failing tests**

Create `python/tests/agents/test_synthesizer_agent.py`:

```python
"""Tests for SynthesizerAgent."""

import pytest

from src.agents.synthesizer_agent import (
    ChunkData,
    SourceInfo,
    SynthesizerAgent,
    SynthesizerDeps,
    SynthesizedDocument,
)


def test_synthesizer_deps_creation():
    deps = SynthesizerDeps(
        topic="auth middleware",
        chunks=[ChunkData(content="Auth uses JWT tokens", source_id="s1", url="https://docs.example.com/auth")],
        source_metadata=[SourceInfo(source_id="s1", title="Auth Docs", url="https://docs.example.com/auth")],
    )
    assert deps.topic == "auth middleware"
    assert len(deps.chunks) == 1
    assert len(deps.source_metadata) == 1


def test_synthesized_document_model():
    doc = SynthesizedDocument(
        title="Auth Middleware Logic",
        content="# Auth Middleware\n\nContent here.",
        summary="Overview of auth middleware patterns.",
        source_urls=["https://docs.example.com/auth"],
        word_count=42,
    )
    assert doc.title == "Auth Middleware Logic"
    assert doc.word_count == 42


def test_synthesizer_agent_instantiation():
    agent = SynthesizerAgent()
    assert agent.name == "SynthesizerAgent"


def test_synthesizer_agent_custom_model():
    agent = SynthesizerAgent(model="openai:gpt-4o")
    assert "gpt-4o" in agent.model
```

**Step 2: Run tests to verify they fail**

Run: `cd /home/winadmin/projects/Trinity/cortex && uv run pytest python/tests/agents/test_synthesizer_agent.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Implement SynthesizerAgent**

Create `python/src/agents/synthesizer_agent.py`:

```python
"""
Synthesizer Agent — transforms raw RAG chunks into cohesive Markdown documents.

Uses PydanticAI to produce clean, well-organized documentation from
fragmented vector search results, suitable for persisting in project repos.
"""

import logging
import os
from dataclasses import dataclass, field

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from .base_agent import CortexDependencies, BaseAgent

logger = logging.getLogger(__name__)


@dataclass
class ChunkData:
    """A single chunk from the RAG search results."""
    content: str
    source_id: str
    url: str | None = None
    title: str | None = None
    chunk_number: int | None = None


@dataclass
class SourceInfo:
    """Metadata about a knowledge source."""
    source_id: str
    title: str
    url: str | None = None


@dataclass
class SynthesizerDeps(CortexDependencies):
    """Dependencies for the synthesizer agent."""
    topic: str = ""
    chunks: list[ChunkData] = field(default_factory=list)
    source_metadata: list[SourceInfo] = field(default_factory=list)


class SynthesizedDocument(BaseModel):
    """Output of the synthesizer agent."""
    title: str = Field(description="Human-readable title for the document")
    content: str = Field(description="Full Markdown content (without frontmatter)")
    summary: str = Field(description="One-sentence summary of the document")
    source_urls: list[str] = Field(description="URLs of sources used")
    word_count: int = Field(description="Word count of the content")


SYSTEM_PROMPT = """You are a technical documentation synthesizer. Your job is to take
fragmented text chunks from a knowledge base and produce a single, cohesive Markdown document.

Rules:
- Produce clean Markdown with logical headers (##, ###)
- Deduplicate overlapping content from different chunks
- Organize information logically, not in chunk order
- Include code blocks with language tags where relevant
- Be concise — synthesize, don't pad
- End with a ## Sources section listing all source URLs
- Do NOT include YAML frontmatter — that will be added separately
- Write the title as an H1 at the top of the document

Topic to synthesize: {topic}

Source chunks:
{chunks}
"""


class SynthesizerAgent(BaseAgent[SynthesizerDeps, str]):
    """Agent that synthesizes RAG chunks into cohesive Markdown."""

    def __init__(self, model: str | None = None, **kwargs):
        if model is None:
            model = os.getenv("SYNTHESIZER_MODEL", "openai:gpt-4.1-nano")
        super().__init__(
            model=model,
            name="SynthesizerAgent",
            retries=3,
            enable_rate_limiting=True,
            **kwargs,
        )

    def _create_agent(self, **kwargs) -> Agent:
        return Agent(
            model=self.model,
            deps_type=SynthesizerDeps,
            output_type=SynthesizedDocument,
            system_prompt=SYSTEM_PROMPT,
        )

    async def synthesize(self, deps: SynthesizerDeps) -> SynthesizedDocument:
        """Run synthesis on the provided chunks."""
        chunks_text = "\n\n---\n\n".join(
            f"[Source: {c.url or c.source_id}]\n{c.content}" for c in deps.chunks
        )
        prompt = f"Synthesize the following chunks about '{deps.topic}' into a cohesive document."

        agent = self._create_agent()
        # Format system prompt with topic and chunks
        formatted_prompt = SYSTEM_PROMPT.format(topic=deps.topic, chunks=chunks_text)

        result = await self.run_with_rate_limit(
            agent, prompt, deps=deps, system_prompt_override=formatted_prompt
        )
        return result.data
```

**Step 4: Run tests to verify they pass**

Run: `cd /home/winadmin/projects/Trinity/cortex && uv run pytest python/tests/agents/test_synthesizer_agent.py -v`
Expected: All 4 tests PASS

**Step 5: Commit**

```bash
git add python/src/agents/synthesizer_agent.py python/tests/agents/test_synthesizer_agent.py
git commit -m "feat: add SynthesizerAgent for RAG chunk synthesis"
```

---

### Task 4: IndexerService

**Files:**
- Create: `python/src/server/services/knowledge/indexer_service.py`
- Test: `python/tests/server/services/test_indexer_service.py`

**Step 1: Write failing tests**

Create `python/tests/server/services/test_indexer_service.py`:

```python
"""Tests for IndexerService."""

import os
import tempfile

import pytest

from src.server.services.knowledge.indexer_service import IndexerService


@pytest.fixture
def temp_project():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def service():
    return IndexerService()


def test_slugify_topic(service):
    assert service.slugify_topic("Auth Middleware Logic") == "auth-middleware-logic"
    assert service.slugify_topic("rate-limiting") == "rate-limiting"
    assert service.slugify_topic("  Spaces  &  Symbols!! ") == "spaces-symbols"


@pytest.mark.asyncio
async def test_write_materialized_file(service, temp_project):
    content = "# Test\n\nSome content."
    path = await service.write_materialized_file(temp_project, "test-topic.md", content)
    assert os.path.exists(os.path.join(temp_project, ".cortex", "knowledge", "test-topic.md"))
    with open(path) as f:
        assert f.read() == content


@pytest.mark.asyncio
async def test_write_creates_directories(service, temp_project):
    content = "# Test"
    await service.write_materialized_file(temp_project, "new-file.md", content)
    assert os.path.isdir(os.path.join(temp_project, ".cortex", "knowledge"))


@pytest.mark.asyncio
async def test_update_index(service, temp_project):
    # Write two files first
    await service.write_materialized_file(temp_project, "topic-a.md", "---\ntopic: Topic A\nmaterialized_at: 2026-03-08\noriginal_urls:\n  - https://a.com\n---\n# Topic A\nContent.")
    await service.write_materialized_file(temp_project, "topic-b.md", "---\ntopic: Topic B\nmaterialized_at: 2026-03-08\noriginal_urls:\n  - https://b.com\n---\n# Topic B\nContent.")
    await service.update_index(temp_project)
    index_path = os.path.join(temp_project, ".cortex", "index.md")
    assert os.path.exists(index_path)
    with open(index_path) as f:
        content = f.read()
    assert "topic-a.md" in content
    assert "topic-b.md" in content


@pytest.mark.asyncio
async def test_remove_file(service, temp_project):
    await service.write_materialized_file(temp_project, "to-remove.md", "# Remove me")
    assert os.path.exists(os.path.join(temp_project, ".cortex", "knowledge", "to-remove.md"))
    await service.remove_file(temp_project, "to-remove.md")
    assert not os.path.exists(os.path.join(temp_project, ".cortex", "knowledge", "to-remove.md"))


@pytest.mark.asyncio
async def test_generate_unique_filename(service, temp_project):
    await service.write_materialized_file(temp_project, "topic.md", "# First")
    unique = service.generate_unique_filename(temp_project, "topic")
    assert unique == "topic-2.md"
```

**Step 2: Run tests to verify they fail**

Run: `cd /home/winadmin/projects/Trinity/cortex && uv run pytest python/tests/server/services/test_indexer_service.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Implement IndexerService**

Create `python/src/server/services/knowledge/indexer_service.py`:

```python
"""
IndexerService — writes materialized files and maintains the .cortex/index.md.

Handles filesystem operations for knowledge materialization:
- Writing synthesized Markdown to .cortex/knowledge/
- Generating and updating .cortex/index.md TOC
- Removing materialized files
- Filename generation and collision handling
"""

import os
import re

import yaml

from ...config.logfire_config import get_logger

logger = get_logger(__name__)

KNOWLEDGE_DIR = ".cortex/knowledge"
INDEX_FILE = ".cortex/index.md"


class IndexerService:
    def slugify_topic(self, topic: str) -> str:
        """Convert a topic string to a safe filename slug."""
        slug = topic.lower().strip()
        slug = re.sub(r"[^a-z0-9\s-]", "", slug)
        slug = re.sub(r"[\s]+", "-", slug)
        slug = re.sub(r"-+", "-", slug)
        return slug.strip("-")

    def generate_unique_filename(self, project_path: str, topic: str) -> str:
        """Generate a unique filename, appending -2, -3, etc. on collision."""
        slug = self.slugify_topic(topic)
        knowledge_dir = os.path.join(project_path, KNOWLEDGE_DIR)
        filename = f"{slug}.md"
        counter = 2
        while os.path.exists(os.path.join(knowledge_dir, filename)):
            filename = f"{slug}-{counter}.md"
            counter += 1
        return filename

    async def write_materialized_file(
        self, project_path: str, filename: str, content: str
    ) -> str:
        """Write content to .cortex/knowledge/{filename}. Creates dirs if needed."""
        knowledge_dir = os.path.join(project_path, KNOWLEDGE_DIR)
        os.makedirs(knowledge_dir, exist_ok=True)
        file_path = os.path.join(knowledge_dir, filename)
        with open(file_path, "w") as f:
            f.write(content)
        logger.info(f"Wrote materialized file | path={file_path}")
        return file_path

    async def remove_file(self, project_path: str, filename: str) -> None:
        """Remove a materialized file."""
        file_path = os.path.join(project_path, KNOWLEDGE_DIR, filename)
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"Removed materialized file | path={file_path}")

    async def update_index(self, project_path: str) -> None:
        """Regenerate .cortex/index.md from all files in .cortex/knowledge/."""
        knowledge_dir = os.path.join(project_path, KNOWLEDGE_DIR)
        cortex_dir = os.path.join(project_path, ".cortex")
        os.makedirs(cortex_dir, exist_ok=True)

        entries = []
        if os.path.isdir(knowledge_dir):
            for filename in sorted(os.listdir(knowledge_dir)):
                if not filename.endswith(".md"):
                    continue
                file_path = os.path.join(knowledge_dir, filename)
                meta = self._extract_frontmatter(file_path)
                topic = meta.get("topic", filename.replace(".md", "").replace("-", " ").title())
                date = meta.get("materialized_at", "unknown")
                urls = meta.get("original_urls", [])
                source_str = ", ".join(urls) if urls else "local"
                if isinstance(date, str) and "T" in date:
                    date = date.split("T")[0]
                entries.append(f"- [{topic}](knowledge/{filename}) — {date} — from {source_str}")

        lines = [
            "# .cortex Knowledge Index",
            "",
            "Auto-generated by Cortex. Do not edit manually.",
            "",
        ]
        if entries:
            lines.append("## Materialized Knowledge")
            lines.append("")
            lines.extend(entries)
        else:
            lines.append("No materialized knowledge files yet.")
        lines.append("")

        index_path = os.path.join(cortex_dir, "index.md")
        with open(index_path, "w") as f:
            f.write("\n".join(lines))
        logger.info(f"Updated index | path={index_path} | entries={len(entries)}")

    def _extract_frontmatter(self, file_path: str) -> dict:
        """Extract YAML frontmatter from a Markdown file."""
        try:
            with open(file_path) as f:
                content = f.read()
            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    return yaml.safe_load(parts[1]) or {}
        except Exception:
            pass
        return {}
```

**Step 4: Run tests to verify they pass**

Run: `cd /home/winadmin/projects/Trinity/cortex && uv run pytest python/tests/server/services/test_indexer_service.py -v`
Expected: All 7 tests PASS

**Step 5: Commit**

```bash
git add python/src/server/services/knowledge/indexer_service.py python/tests/server/services/test_indexer_service.py
git commit -m "feat: add IndexerService for file writing and index management"
```

---

### Task 5: MaterializationService — full orchestration pipeline

**Files:**
- Modify: `python/src/server/services/knowledge/materialization_service.py`
- Test: `python/tests/server/services/test_materialization_pipeline.py`

**Step 1: Write failing tests for the orchestration**

Create `python/tests/server/services/test_materialization_pipeline.py`:

```python
"""Tests for MaterializationService full pipeline."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.server.services.knowledge.materialization_service import MaterializationService


@pytest.fixture
def mock_supabase():
    client = MagicMock()
    client.table = MagicMock(return_value=client)
    client.select = MagicMock(return_value=client)
    client.insert = MagicMock(return_value=client)
    client.update = MagicMock(return_value=client)
    client.delete = MagicMock(return_value=client)
    client.eq = MagicMock(return_value=client)
    client.order = MagicMock(return_value=client)
    client.rpc = MagicMock(return_value=MagicMock(data=None))
    client.execute = MagicMock(return_value=MagicMock(data=[]))
    return client


@pytest.fixture
def service(mock_supabase):
    return MaterializationService(supabase_client=mock_supabase)


@pytest.mark.asyncio
async def test_materialize_skips_when_already_exists(service, mock_supabase):
    """Already-materialized topics return existing record."""
    mock_supabase.execute.return_value.data = [{
        "id": "existing-id",
        "project_id": "proj_123",
        "project_path": "/tmp/project",
        "topic": "auth",
        "filename": "auth.md",
        "file_path": ".cortex/knowledge/auth.md",
        "source_ids": [],
        "original_urls": [],
        "synthesis_model": None,
        "word_count": 100,
        "status": "active",
        "access_count": 1,
        "last_accessed_at": None,
        "materialized_at": "2026-03-08T10:00:00Z",
        "updated_at": "2026-03-08T10:00:00Z",
        "metadata": {},
    }]
    result = await service.materialize("auth", "proj_123", "/tmp/project")
    assert result.success is True
    assert result.file_path == ".cortex/knowledge/auth.md"


@pytest.mark.asyncio
@patch("src.server.services.knowledge.materialization_service.RAGService")
@patch("src.server.services.knowledge.materialization_service.SynthesizerAgent")
@patch("src.server.services.knowledge.materialization_service.IndexerService")
async def test_materialize_returns_no_content_when_search_empty(
    MockIndexer, MockSynthesizer, MockRAG, service, mock_supabase
):
    """No search results means no materialization."""
    # check_existing returns nothing
    mock_supabase.execute.return_value.data = []

    mock_rag = AsyncMock()
    mock_rag.search_documents = AsyncMock(return_value=[])
    MockRAG.return_value = mock_rag

    result = await service.materialize("nonexistent topic", "proj_123", "/tmp/project")
    assert result.success is False
    assert result.reason == "no_relevant_content"
```

**Step 2: Run tests to verify they fail**

Run: `cd /home/winadmin/projects/Trinity/cortex && uv run pytest python/tests/server/services/test_materialization_pipeline.py -v`
Expected: FAIL — `materialize` method not found or import errors

**Step 3: Add the `materialize()` orchestration method**

Add to `python/src/server/services/knowledge/materialization_service.py` — import and add the `materialize` method:

```python
# Add imports at top:
import uuid
from datetime import datetime, timezone

from ...utils.progress.progress_tracker import ProgressTracker
from ..search.rag_service import RAGService
from .indexer_service import IndexerService

# Add to __init__:
    self.indexer = IndexerService()

# Add method:
    async def materialize(
        self,
        topic: str,
        project_id: str,
        project_path: str,
        progress_id: str | None = None,
        agent_context: str | None = None,
    ) -> MaterializationResult:
        """Full materialization pipeline: search -> synthesize -> write -> track."""
        from src.agents.synthesizer_agent import (
            ChunkData,
            SourceInfo,
            SynthesizerAgent,
            SynthesizerDeps,
        )

        # Step 1: Check if already materialized
        existing = await self.check_existing(topic, project_id)
        if existing:
            await self.mark_accessed(existing.id)
            return MaterializationResult(
                success=True,
                file_path=existing.file_path,
                filename=existing.filename,
                word_count=existing.word_count,
                materialization_id=existing.id,
            )

        # Step 2: Claim with pending record (concurrency safety)
        pending_id = await self.create_record(
            project_id=project_id,
            project_path=project_path,
            topic=topic,
            filename="",  # placeholder until synthesis completes
            file_path="",
            source_ids=[],
            original_urls=[],
            synthesis_model="",
            word_count=0,
            metadata={"agent_context": agent_context, "status_override": "pending"} if agent_context else {"status_override": "pending"},
        )
        # Override status to pending (create_record defaults to active)
        await self.update_status(pending_id, "pending")

        # Step 3: Progress tracking
        tracker = None
        if progress_id:
            tracker = ProgressTracker(progress_id, operation_type="materialization")

        try:
            # Step 4: RAG search
            if tracker:
                tracker.state.update({"status": "searching", "progress": 10})
            rag = RAGService(supabase_client=self.supabase)
            search_results = await rag.search_documents(
                query=topic, match_count=10, use_hybrid_search=True
            )
            if not search_results:
                await self.delete_record(pending_id)
                if tracker:
                    tracker.state.update({"status": "completed", "progress": 100})
                return MaterializationResult(success=False, reason="no_relevant_content")

            # Step 5: Filter and synthesize
            if tracker:
                tracker.state.update({"status": "synthesizing", "progress": 40})

            # Filter out trivially short chunks (navigation fragments, headers)
            MIN_CHUNK_LENGTH = 50
            chunks = [
                ChunkData(
                    content=r.get("content", ""),
                    source_id=r.get("source_id", ""),
                    url=r.get("url"),
                    title=r.get("title"),
                )
                for r in search_results
                if len(r.get("content", "").strip()) >= MIN_CHUNK_LENGTH
            ]
            if not chunks:
                await self.delete_record(pending_id)
                if tracker:
                    tracker.state.update({"status": "completed", "progress": 100})
                return MaterializationResult(success=False, reason="no_relevant_content")

            source_map = {}
            for r in search_results:
                sid = r.get("source_id", "")
                if sid and sid not in source_map:
                    source_map[sid] = SourceInfo(
                        source_id=sid, title=r.get("title", ""), url=r.get("url")
                    )

            deps = SynthesizerDeps(
                topic=topic, chunks=chunks, source_metadata=list(source_map.values())
            )
            synthesizer = SynthesizerAgent()
            synthesized = await synthesizer.synthesize(deps)

            # Step 6: Build frontmatter and full content
            if tracker:
                tracker.state.update({"status": "writing", "progress": 70})

            source_urls = synthesized.source_urls or [s.url for s in source_map.values() if s.url]
            source_ids = list(source_map.keys())
            frontmatter = {
                "cortex_source": "vector_archive",
                "materialized_at": datetime.now(timezone.utc).isoformat(),
                "topic": topic,
                "source_urls": source_urls,
                "source_ids": source_ids,
                "synthesis_model": synthesizer.model,
            }
            import yaml
            full_content = f"---\n{yaml.dump(frontmatter, default_flow_style=False)}---\n\n{synthesized.content}"

            # Step 7: Write file
            filename = self.indexer.generate_unique_filename(project_path, topic)
            await self.indexer.write_materialized_file(project_path, filename, full_content)
            await self.indexer.update_index(project_path)

            # Step 8: Finalize DB record (pending -> active with real data)
            file_path = f".cortex/knowledge/{filename}"
            now = datetime.now(timezone.utc).isoformat()
            self.supabase.table(TABLE).update({
                "filename": filename,
                "file_path": file_path,
                "source_ids": source_ids,
                "original_urls": source_urls,
                "synthesis_model": synthesizer.model,
                "word_count": synthesized.word_count,
                "status": "active",
                "metadata": {"agent_context": agent_context} if agent_context else {},
                "updated_at": now,
            }).eq("id", pending_id).execute()

            if tracker:
                tracker.state.update({
                    "status": "completed",
                    "progress": 100,
                    "file_path": file_path,
                    "filename": filename,
                })

            return MaterializationResult(
                success=True,
                file_path=file_path,
                filename=filename,
                word_count=synthesized.word_count,
                summary=synthesized.summary,
                materialization_id=pending_id,
            )

        except Exception as e:
            logger.error(f"Materialization failed | topic={topic} | error={e}", exc_info=True)
            await self.delete_record(pending_id)
            if tracker:
                tracker.state.update({"status": "failed", "progress": 0, "error": str(e)})
            return MaterializationResult(success=False, reason=str(e))
```

**Step 4: Run tests to verify they pass**

Run: `cd /home/winadmin/projects/Trinity/cortex && uv run pytest python/tests/server/services/test_materialization_pipeline.py -v`
Expected: All 2 tests PASS

**Step 5: Commit**

```bash
git add python/src/server/services/knowledge/materialization_service.py python/tests/server/services/test_materialization_pipeline.py
git commit -m "feat: add full materialization orchestration pipeline"
```

---

## Phase 3: API Endpoints

### Task 6: Materialization REST API

**Files:**
- Create: `python/src/server/api_routes/materialization_api.py`
- Modify: `python/src/server/main.py:20-40` (add import)
- Modify: `python/src/server/main.py:203-220` (add include_router)
- Test: `python/tests/server/api_routes/test_materialization_api.py`

**Step 1: Write failing tests**

Create `python/tests/server/api_routes/test_materialization_api.py`:

```python
"""Tests for materialization API endpoints."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from src.server.main import app
    return TestClient(app)


def test_list_materializations_endpoint(client):
    with patch("src.server.api_routes.materialization_api.MaterializationService") as MockService:
        mock_svc = MagicMock()
        mock_svc.list_materializations = AsyncMock(return_value=[])
        MockService.return_value = mock_svc
        response = client.get("/api/materialization/history")
        assert response.status_code == 200
        assert response.json() == {"items": [], "total": 0}


def test_execute_materialization_endpoint(client):
    with patch("src.server.api_routes.materialization_api.MaterializationService") as MockService:
        mock_svc = MagicMock()
        mock_svc.materialize = AsyncMock(return_value=MagicMock(
            success=True, file_path=".cortex/knowledge/test.md",
            filename="test.md", word_count=100, summary="test",
            materialization_id="abc-123", reason=None,
        ))
        MockService.return_value = mock_svc
        response = client.post("/api/materialization/execute", json={
            "topic": "test topic",
            "project_id": "proj_123",
            "project_path": "/tmp/project",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
```

**Step 2: Run tests to verify they fail**

Run: `cd /home/winadmin/projects/Trinity/cortex && uv run pytest python/tests/server/api_routes/test_materialization_api.py -v`
Expected: FAIL — import error or 404

**Step 3: Implement the API routes**

Create `python/src/server/api_routes/materialization_api.py`:

```python
"""
Materialization API — endpoints for knowledge materialization.

Handles materialization execution, history queries, status updates, and deletion.
"""

import asyncio
import uuid

from fastapi import APIRouter, HTTPException

from ..config.logfire_config import get_logger
from ..models.materialization import MaterializationRequest, MaterializationResult
from ..services.knowledge.materialization_service import MaterializationService
from ..utils import get_supabase_client

logger = get_logger(__name__)

router = APIRouter(prefix="/api/materialization", tags=["materialization"])


@router.post("/execute")
async def execute_materialization(request: MaterializationRequest) -> dict:
    """Kick off a materialization pipeline."""
    progress_id = str(uuid.uuid4())
    service = MaterializationService(supabase_client=get_supabase_client())

    # Run async — for now synchronous for simplicity, can be backgrounded later
    result = await service.materialize(
        topic=request.topic,
        project_id=request.project_id,
        project_path=request.project_path,
        progress_id=progress_id,
        agent_context=request.agent_context,
    )
    return {
        "success": result.success,
        "progress_id": progress_id,
        "materialization_id": result.materialization_id,
        "file_path": result.file_path,
        "filename": result.filename,
        "word_count": result.word_count,
        "summary": result.summary,
        "reason": result.reason,
    }


@router.get("/history")
async def list_materializations(
    project_id: str | None = None,
    status: str | None = None,
) -> dict:
    """List materialization records with optional filters."""
    service = MaterializationService(supabase_client=get_supabase_client())
    records = await service.list_materializations(project_id=project_id, status=status)
    return {"items": [r.model_dump() for r in records], "total": len(records)}


@router.get("/{materialization_id}")
async def get_materialization(materialization_id: str) -> dict:
    """Get a single materialization record."""
    service = MaterializationService(supabase_client=get_supabase_client())
    record = await service.get_record(materialization_id)
    if not record:
        raise HTTPException(status_code=404, detail="Materialization not found")
    return record.model_dump()


@router.put("/{materialization_id}/access")
async def mark_accessed(materialization_id: str) -> dict:
    """Bump access_count and last_accessed_at."""
    service = MaterializationService(supabase_client=get_supabase_client())
    await service.mark_accessed(materialization_id)
    return {"success": True}


@router.put("/{materialization_id}/status")
async def update_status(materialization_id: str, status: str) -> dict:
    """Update materialization status."""
    if status not in ("active", "stale", "archived"):
        raise HTTPException(status_code=400, detail="Invalid status")
    service = MaterializationService(supabase_client=get_supabase_client())
    await service.update_status(materialization_id, status)
    return {"success": True}


@router.delete("/{materialization_id}")
async def delete_materialization(materialization_id: str) -> dict:
    """Delete materialization record and associated file."""
    service = MaterializationService(supabase_client=get_supabase_client())
    record = await service.get_record(materialization_id)
    if not record:
        raise HTTPException(status_code=404, detail="Materialization not found")

    from ..services.knowledge.indexer_service import IndexerService
    indexer = IndexerService()
    await indexer.remove_file(record.project_path, record.filename)
    await indexer.update_index(record.project_path)
    await service.delete_record(materialization_id)
    return {"success": True}
```

**Step 4: Register the router in main.py**

Add to `python/src/server/main.py`:
- Import: `from .api_routes.materialization_api import router as materialization_router` (after line 35)
- Include: `app.include_router(materialization_router)` (after line 220)

**Step 5: Run tests to verify they pass**

Run: `cd /home/winadmin/projects/Trinity/cortex && uv run pytest python/tests/server/api_routes/test_materialization_api.py -v`
Expected: All 2 tests PASS

**Step 6: Commit**

```bash
git add python/src/server/api_routes/materialization_api.py python/src/server/main.py python/tests/server/api_routes/test_materialization_api.py
git commit -m "feat: add materialization REST API endpoints"
```

---

## Phase 4: MCP Tools

### Task 7: Materialization MCP tools

**Files:**
- Create: `python/src/mcp_server/features/materialization/__init__.py`
- Create: `python/src/mcp_server/features/materialization/materialization_tools.py`
- Modify: `python/src/mcp_server/mcp_server.py:593-595` (add registration)

**Step 1: Create the MCP tools module**

Create `python/src/mcp_server/features/materialization/__init__.py`:

```python
"""
Knowledge Materialization tools for Cortex MCP Server.

Tools for materializing vector knowledge into local project repos.
"""

from .materialization_tools import register_materialization_tools

__all__ = ["register_materialization_tools"]
```

Create `python/src/mcp_server/features/materialization/materialization_tools.py`:

```python
"""
MCP tools for knowledge materialization.

Provides:
- materialize_knowledge: Autonomous knowledge gap filling
- find_materializations: Query materialization history
- manage_materialization: Status changes and deletion
"""

import json
from urllib.parse import urljoin

import httpx
from mcp.server.fastmcp import Context, FastMCP

from src.server.config.service_discovery import get_api_url


def register_materialization_tools(mcp: FastMCP):
    """Register all materialization tools with the MCP server."""

    @mcp.tool()
    async def materialize_knowledge(
        ctx: Context,
        topic: str,
        project_id: str,
        project_path: str,
    ) -> str:
        """Materialize knowledge from the Vector DB into a local project repo.

        Searches the RAG knowledge base for the given topic, synthesizes
        the results into a cohesive Markdown document, and writes it to
        the project's .cortex/knowledge/ directory.

        Args:
            topic: The knowledge topic to materialize (e.g., "auth middleware patterns")
            project_id: The Cortex project ID
            project_path: Filesystem path to the project repo
        """
        try:
            api_url = get_api_url()
            timeout = httpx.Timeout(120.0, connect=5.0)

            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    urljoin(api_url, "/api/materialization/execute"),
                    json={
                        "topic": topic,
                        "project_id": project_id,
                        "project_path": project_path,
                    },
                )
                if response.status_code == 200:
                    return json.dumps(response.json(), indent=2)
                else:
                    return json.dumps({
                        "success": False,
                        "error": f"HTTP {response.status_code}: {response.text}",
                    }, indent=2)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)}, indent=2)

    @mcp.tool()
    async def find_materializations(
        ctx: Context,
        project_id: str | None = None,
        status: str | None = None,
        materialization_id: str | None = None,
    ) -> str:
        """Find materialization history records.

        Args:
            project_id: Filter by project ID
            status: Filter by status (active, stale, archived)
            materialization_id: Get a specific record by ID
        """
        try:
            api_url = get_api_url()
            timeout = httpx.Timeout(30.0, connect=5.0)

            async with httpx.AsyncClient(timeout=timeout) as client:
                if materialization_id:
                    response = await client.get(
                        urljoin(api_url, f"/api/materialization/{materialization_id}")
                    )
                else:
                    params = {}
                    if project_id:
                        params["project_id"] = project_id
                    if status:
                        params["status"] = status
                    response = await client.get(
                        urljoin(api_url, "/api/materialization/history"),
                        params=params,
                    )
                if response.status_code == 200:
                    return json.dumps(response.json(), indent=2)
                else:
                    return json.dumps({
                        "success": False,
                        "error": f"HTTP {response.status_code}: {response.text}",
                    }, indent=2)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)}, indent=2)

    @mcp.tool()
    async def manage_materialization(
        ctx: Context,
        action: str,
        materialization_id: str,
    ) -> str:
        """Manage materialization records.

        Args:
            action: One of "mark_accessed", "mark_stale", "archive", "delete"
            materialization_id: The materialization record ID
        """
        try:
            api_url = get_api_url()
            timeout = httpx.Timeout(30.0, connect=5.0)

            async with httpx.AsyncClient(timeout=timeout) as client:
                if action == "mark_accessed":
                    response = await client.put(
                        urljoin(api_url, f"/api/materialization/{materialization_id}/access")
                    )
                elif action in ("mark_stale", "archive"):
                    status = "stale" if action == "mark_stale" else "archived"
                    response = await client.put(
                        urljoin(api_url, f"/api/materialization/{materialization_id}/status"),
                        params={"status": status},
                    )
                elif action == "delete":
                    response = await client.delete(
                        urljoin(api_url, f"/api/materialization/{materialization_id}")
                    )
                else:
                    return json.dumps({
                        "success": False,
                        "error": f"Invalid action: {action}. Use mark_accessed, mark_stale, archive, or delete.",
                    }, indent=2)

                if response.status_code == 200:
                    return json.dumps(response.json(), indent=2)
                else:
                    return json.dumps({
                        "success": False,
                        "error": f"HTTP {response.status_code}: {response.text}",
                    }, indent=2)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)}, indent=2)
```

**Step 2: Register in MCP server**

Add to `python/src/mcp_server/mcp_server.py` after the session tools registration block (~line 595):

```python
    # Import and register Materialization module
    try:
        from src.mcp_server.features.materialization import register_materialization_tools
        register_materialization_tools(mcp)
        modules_registered += 1
        logger.info("✓ Materialization module registered (HTTP-based)")
    except ImportError as e:
        logger.warning(f"⚠ Materialization module not available: {e}")
```

**Step 3: Commit**

```bash
git add python/src/mcp_server/features/materialization/ python/src/mcp_server/mcp_server.py
git commit -m "feat: add materialization MCP tools"
```

---

## Phase 5: Agent Prompt Update

### Task 8: Update codebase-analyst with Context Escalation Protocol

**Files:**
- Modify: `.claude/agents/codebase-analyst.md`

**Step 1: Read the current file and add the protocol**

Append the following section to `.claude/agents/codebase-analyst.md`:

```markdown
## Context Escalation Protocol

When analyzing a topic or pattern in a project:

1. **Check local context first:**
   - Read `.cortex/index.md` if it exists — this lists all materialized knowledge
   - Search project source files and documentation for the topic
   - Check CLAUDE.md and any docs/ directory

2. **Escalate to Vector DB if local context is insufficient:**
   - If the topic is not covered locally, or local docs are incomplete/outdated
   - Call `materialize_knowledge` with the topic, project_id, and project_path
   - This will search the global knowledge base, synthesize results, and write a Markdown file to `.cortex/knowledge/`

3. **Continue with enriched context:**
   - Read the newly materialized file
   - Incorporate the knowledge into your analysis
   - The file persists for future sessions — no repeated searches needed

Use your judgment on when to escalate. Good signals:
- The topic involves external libraries, APIs, or patterns not in the source code
- You're asked about best practices or conventions that aren't documented locally
- The project references technologies you need deeper context on
```

**Step 2: Commit**

```bash
git add .claude/agents/codebase-analyst.md
git commit -m "feat: add Context Escalation Protocol to codebase-analyst"
```

---

## Phase 6: Frontend Integration

### Task 9: Materialization types and service

**Files:**
- Create: `cortex-ui/src/features/knowledge/materialization/types/index.ts`
- Create: `cortex-ui/src/features/knowledge/materialization/services/materializationService.ts`

**Step 1: Create types**

Create `cortex-ui/src/features/knowledge/materialization/types/index.ts`:

```typescript
export interface MaterializationRecord {
  id: string;
  project_id: string;
  project_path: string;
  topic: string;
  filename: string;
  file_path: string;
  source_ids: string[];
  original_urls: string[];
  synthesis_model: string | null;
  word_count: number;
  status: "active" | "stale" | "archived";
  access_count: number;
  last_accessed_at: string | null;
  materialized_at: string;
  updated_at: string;
  metadata: Record<string, unknown>;
}

export interface MaterializationHistoryResponse {
  items: MaterializationRecord[];
  total: number;
}

export interface MaterializationExecuteResponse {
  success: boolean;
  progress_id: string;
  materialization_id: string | null;
  file_path: string | null;
  filename: string | null;
  word_count: number;
  summary: string | null;
  reason: string | null;
}
```

**Step 2: Create service**

Create `cortex-ui/src/features/knowledge/materialization/services/materializationService.ts`:

```typescript
import { callAPIWithETag } from "../../../shared/api/apiClient";
import type { MaterializationHistoryResponse, MaterializationRecord } from "../types";

export const materializationService = {
  async getHistory(
    projectId?: string,
    status?: string,
  ): Promise<MaterializationHistoryResponse> {
    const params = new URLSearchParams();
    if (projectId) params.append("project_id", projectId);
    if (status) params.append("status", status);
    const query = params.toString();
    return callAPIWithETag<MaterializationHistoryResponse>(
      `/api/materialization/history${query ? `?${query}` : ""}`,
    );
  },

  async getRecord(id: string): Promise<MaterializationRecord> {
    return callAPIWithETag<MaterializationRecord>(`/api/materialization/${id}`);
  },

  async updateStatus(id: string, status: string): Promise<{ success: boolean }> {
    return callAPIWithETag<{ success: boolean }>(
      `/api/materialization/${id}/status?status=${status}`,
      { method: "PUT" },
    );
  },

  async deleteRecord(id: string): Promise<{ success: boolean }> {
    return callAPIWithETag<{ success: boolean }>(
      `/api/materialization/${id}`,
      { method: "DELETE" },
    );
  },
};
```

**Step 3: Commit**

```bash
git add cortex-ui/src/features/knowledge/materialization/
git commit -m "feat: add materialization types and service"
```

---

### Task 10: Materialization query hooks

**Files:**
- Create: `cortex-ui/src/features/knowledge/materialization/hooks/useMaterializationQueries.ts`

**Step 1: Create query hooks**

```typescript
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { DISABLED_QUERY_KEY, STALE_TIMES } from "../../../shared/config/queryPatterns";
import { useToast } from "../../../shared/hooks/useToast";
import { materializationService } from "../services/materializationService";
import type { MaterializationHistoryResponse } from "../types";

export const materializationKeys = {
  all: ["materialization"] as const,
  lists: () => [...materializationKeys.all, "list"] as const,
  history: (projectId?: string, status?: string) =>
    [...materializationKeys.all, "history", projectId, status] as const,
  detail: (id: string) => [...materializationKeys.all, "detail", id] as const,
};

export function useMaterializationHistory(projectId?: string, status?: string) {
  return useQuery<MaterializationHistoryResponse>({
    queryKey: materializationKeys.history(projectId, status),
    queryFn: () => materializationService.getHistory(projectId, status),
    staleTime: STALE_TIMES.normal,
  });
}

export function useDeleteMaterialization() {
  const queryClient = useQueryClient();
  const { showToast } = useToast();

  return useMutation({
    mutationFn: (id: string) => materializationService.deleteRecord(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: materializationKeys.lists() });
      showToast("Materialization deleted", "success");
    },
    onError: () => {
      showToast("Failed to delete materialization", "error");
    },
  });
}

export function useUpdateMaterializationStatus() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) =>
      materializationService.updateStatus(id, status),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: materializationKeys.lists() });
    },
  });
}
```

**Step 2: Commit**

```bash
git add cortex-ui/src/features/knowledge/materialization/hooks/
git commit -m "feat: add materialization query hooks"
```

---

### Task 11: MaterializationList component

**Files:**
- Create: `cortex-ui/src/features/knowledge/materialization/components/MaterializationList.tsx`

**Step 1: Create the component**

```typescript
import { useMaterializationHistory, useDeleteMaterialization } from "../hooks/useMaterializationQueries";
import type { MaterializationRecord } from "../types";

interface MaterializationListProps {
  projectId?: string;
  statusFilter?: string;
}

export const MaterializationList = ({ projectId, statusFilter }: MaterializationListProps) => {
  const { data, isLoading } = useMaterializationHistory(projectId, statusFilter);
  const deleteMutation = useDeleteMaterialization();

  if (isLoading) {
    return <div className="text-gray-400 p-4">Loading materialization history...</div>;
  }

  const items = data?.items ?? [];

  if (items.length === 0) {
    return (
      <div className="text-gray-500 p-4 text-center">
        No materialized knowledge files yet. Agents will automatically materialize
        knowledge when they detect gaps in local context.
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {items.map((item: MaterializationRecord) => (
        <div
          key={item.id}
          className="bg-gray-800/50 border border-gray-700 rounded-lg p-4 flex items-center justify-between"
        >
          <div className="flex-1">
            <div className="flex items-center gap-2">
              <span className="text-white font-medium">{item.topic}</span>
              <span className={`text-xs px-2 py-0.5 rounded ${
                item.status === "active" ? "bg-green-900/50 text-green-400" :
                item.status === "stale" ? "bg-yellow-900/50 text-yellow-400" :
                "bg-gray-700 text-gray-400"
              }`}>
                {item.status}
              </span>
            </div>
            <div className="text-sm text-gray-400 mt-1">
              {item.file_path} — {item.word_count} words — accessed {item.access_count} times
            </div>
            <div className="text-xs text-gray-500 mt-0.5">
              Materialized {new Date(item.materialized_at).toLocaleDateString()}
              {item.original_urls.length > 0 && ` from ${item.original_urls[0]}`}
            </div>
          </div>
          <button
            onClick={() => deleteMutation.mutate(item.id)}
            className="text-red-400 hover:text-red-300 text-sm px-3 py-1"
            disabled={deleteMutation.isPending}
          >
            Delete
          </button>
        </div>
      ))}
    </div>
  );
};
```

**Step 2: Commit**

```bash
git add cortex-ui/src/features/knowledge/materialization/components/
git commit -m "feat: add MaterializationList component"
```

---

### Task 12: Integrate into KnowledgeView

**Files:**
- Modify: `cortex-ui/src/features/knowledge/views/KnowledgeView.tsx`
- Modify: `cortex-ui/src/features/knowledge/components/KnowledgeHeader.tsx`

**Step 1: Add "Materialized" tab/filter to KnowledgeView**

Read the current KnowledgeView.tsx and KnowledgeHeader.tsx to understand their exact structure, then:

- Add a new state: `const [showMaterialized, setShowMaterialized] = useState(false);`
- Add a toggle button in KnowledgeHeader next to the existing type filters
- When `showMaterialized` is true, render `<MaterializationList />` instead of the normal knowledge grid/table
- Import `MaterializationList` from the materialization sub-feature

**Step 2: Add toast notification for materialization events**

In KnowledgeView or a parent component, use `useMaterializationHistory` with smart polling. When a new item appears in the list that wasn't there before, show a toast:

```typescript
const { showToast } = useToast();
// In an effect watching materialization data:
showToast(`Cortex materialized '${newItem.topic}' to ${newItem.file_path}`, "success");
```

**Step 3: Commit**

```bash
git add cortex-ui/src/features/knowledge/views/KnowledgeView.tsx cortex-ui/src/features/knowledge/components/KnowledgeHeader.tsx
git commit -m "feat: integrate MaterializationList into KnowledgeView"
```

---

## Phase 7: Verification

### Task 13: Run full test suite

**Step 1: Run backend tests**

Run: `cd /home/winadmin/projects/Trinity/cortex && uv run pytest python/tests/ -v --tb=short`
Expected: All tests PASS including new materialization tests

**Step 2: Run frontend type check**

Run: `cd /home/winadmin/projects/Trinity/cortex/cortex-ui && npx tsc --noEmit`
Expected: No TypeScript errors

**Step 3: Run linters**

Run: `cd /home/winadmin/projects/Trinity/cortex && make lint`
Expected: No linting errors

**Step 4: Commit any fixes**

```bash
git commit -m "fix: address linting and type errors"
```

---

### Task 14: End-to-end smoke test

**Step 1: Start services**

Run: `cd /home/winadmin/projects/Trinity/cortex && docker compose up --build -d`

**Step 2: Apply migration**

Run the migration SQL against the database.

**Step 3: Test API manually**

```bash
# List materializations (should be empty)
curl http://localhost:8181/api/materialization/history

# Execute materialization (requires a topic that exists in RAG)
curl -X POST http://localhost:8181/api/materialization/execute \
  -H "Content-Type: application/json" \
  -d '{"topic": "test topic", "project_id": "test", "project_path": "/tmp/test-project"}'
```

**Step 4: Verify MCP tool availability**

Check MCP health and verify `materialize_knowledge` tool is listed.

**Step 5: Verify frontend**

Open http://localhost:3737, navigate to Knowledge tab, verify "Materialized" filter appears.
