# Cortex Chat Interface Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an interactive AI chat interface within Cortex that understands the user's identity, projects, and priorities to serve as a strategic advisor and project management assistant.

**Architecture:** Frontend → Agent Service (SSE streaming via Vite proxy) + Frontend → Main Server (CRUD persistence). The ChatAgent (PydanticAI) uses MCPClient for data reads and calls Main Server REST API to persist messages. Two database migrations add project enrichment columns and chat tables.

**Tech Stack:** React 18, TypeScript, TanStack Query v5, Tailwind CSS, react-markdown + rehype-highlight + remark-gfm, FastAPI, PydanticAI, Supabase (PostgreSQL + pgvector), SSE streaming

**Spec:** `docs/superpowers/specs/2026-03-23-cortex-chat-interface-design.md`

---

## File Structure

### Database Migrations
- Create: `migration/0.1.0/025_add_project_enrichment_columns.sql`
- Create: `migration/0.1.0/026_add_chat_tables.sql`

### Backend — Main Server (python/src/server/)
- Create: `services/chat/chat_service.py` — Conversation CRUD
- Create: `services/chat/chat_message_service.py` — Message CRUD + search
- Create: `services/chat/user_profile_service.py` — Singleton profile CRUD
- Create: `services/chat/__init__.py` — Barrel exports
- Create: `api_routes/chat_api.py` — All chat REST endpoints
- Modify: `main.py` — Register chat router
- Delete: `api_routes/agent_chat_api.py` — Legacy stub

### Backend — Agent Service (python/src/agents/)
- Create: `chat_agent.py` — ChatAgent with advisor + action tools
- Create: `chat_tools.py` — Tool implementations (prioritization, synergy, etc.)
- Modify: `server.py` — Register chat streaming + action approval endpoints

### Frontend — Chat Feature (cortex-ui/src/features/chat/)
- Create: `types/index.ts` — Chat TypeScript types
- Create: `services/chatService.ts` — REST + SSE API client
- Create: `hooks/useChatQueries.ts` — TanStack Query hooks + keys
- Create: `hooks/useSSEStream.ts` — SSE streaming hook
- Create: `components/MessageBubble.tsx` — Message rendering with Markdown
- Create: `components/ToolUseCard.tsx` — Collapsible tool invocation display
- Create: `components/ActionRequestCard.tsx` — Approve/deny action UI
- Create: `components/ChatInput.tsx` — Message input with model selector
- Create: `components/ModelSelector.tsx` — Model picker dropdown
- Create: `components/MessageStream.tsx` — Scrollable message list
- Create: `components/ConversationList.tsx` — Sidebar conversation list
- Create: `components/ChatSidebar.tsx` — Floating sidebar panel
- Create: `components/ChatPage.tsx` — Full /chat page layout
- Create: `components/ConversationContext.tsx` — Right panel (project scope, action mode)
- Create: `components/OnboardingFlow.tsx` — First-time profile interview
- Create: `views/ChatView.tsx` — View orchestrator

### Frontend — Modifications
- Modify: `cortex-ui/vite.config.ts` — Add /agents proxy
- Modify: `cortex-ui/src/components/layout/MainLayout.tsx` — Activate floating chat button
- Modify: `cortex-ui/src/App.tsx` — Add /chat route
- Modify: `cortex-ui/src/pages/SettingsPage.tsx` — Add Profile section
- Create: `cortex-ui/src/components/settings/ProfileSettings.tsx` — Profile editor
- Create: `cortex-ui/src/components/settings/ChatModelSettings.tsx` — Model config
- Delete: `cortex-ui/src/services/agentChatService.ts` — Legacy service
- Delete: `cortex-ui/src/components/agent-chat/CortexChatPanel.tsx` — Legacy panel

### Frontend — Project Enrichment
- Modify: `cortex-ui/src/features/projects/types/project.ts` — Add enrichment fields
- Modify: `cortex-ui/src/features/projects/services/projectService.ts` — Add enrichment methods
- Create: `cortex-ui/src/features/projects/components/ProjectAboutSection.tsx` — Goals/relevance/category editor

### Tests
- Create: `python/tests/server/services/test_chat_service.py`
- Create: `python/tests/server/services/test_chat_message_service.py`
- Create: `python/tests/server/services/test_user_profile_service.py`
- Create: `python/tests/server/api_routes/test_chat_api.py`
- Create: `cortex-ui/src/features/chat/hooks/tests/useChatQueries.test.ts`

---

## Phase 1: Database Foundation

### Task 1: Migration 025 — Project Enrichment Columns

**Files:**
- Create: `migration/0.1.0/025_add_project_enrichment_columns.sql`

- [ ] **Step 1: Write the migration SQL**

```sql
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
```

- [ ] **Step 2: Run migration against Supabase**

Run the SQL in the Supabase SQL editor or via `psql`. Verify columns exist:
```sql
SELECT column_name, data_type FROM information_schema.columns
WHERE table_name = 'cortex_projects' AND column_name IN ('project_goals', 'project_relevance', 'project_category');
```
Expected: 3 rows returned.

- [ ] **Step 3: Commit**

```bash
git add migration/0.1.0/025_add_project_enrichment_columns.sql
git commit -m "feat: add project enrichment columns (goals, relevance, category)"
```

---

### Task 2: Migration 026 — Chat Tables

**Files:**
- Create: `migration/0.1.0/026_add_chat_tables.sql`

- [ ] **Step 1: Write the migration SQL**

```sql
-- Migration 026: Chat interface tables
-- Creates chat_conversations, chat_messages, and user_profile tables

-- Chat conversations
CREATE TABLE IF NOT EXISTS chat_conversations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  title TEXT,
  project_id UUID REFERENCES cortex_projects(id) ON DELETE SET NULL,
  conversation_type TEXT NOT NULL DEFAULT 'global',
  model_config JSONB DEFAULT '{}',
  action_mode BOOLEAN NOT NULL DEFAULT false,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  deleted_at TIMESTAMPTZ DEFAULT NULL,
  metadata JSONB DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_chat_conversations_project
  ON chat_conversations (project_id)
  WHERE project_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_chat_conversations_updated
  ON chat_conversations (updated_at DESC)
  WHERE deleted_at IS NULL;

-- Chat messages
CREATE TABLE IF NOT EXISTS chat_messages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id UUID NOT NULL REFERENCES chat_conversations(id) ON DELETE CASCADE,
  role TEXT NOT NULL,
  content TEXT NOT NULL DEFAULT '',
  tool_calls JSONB DEFAULT NULL,
  tool_results JSONB DEFAULT NULL,
  model_used TEXT DEFAULT NULL,
  token_count INTEGER DEFAULT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  search_vector TSVECTOR
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_conversation
  ON chat_messages (conversation_id, created_at);

CREATE INDEX IF NOT EXISTS idx_chat_messages_search
  ON chat_messages USING GIN (search_vector);

-- Auto-populate search_vector on insert/update
CREATE OR REPLACE FUNCTION chat_messages_search_vector_update() RETURNS trigger AS $$
BEGIN
  NEW.search_vector := to_tsvector('english', COALESCE(NEW.content, ''));
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS chat_messages_search_vector_trigger ON chat_messages;
CREATE TRIGGER chat_messages_search_vector_trigger
  BEFORE INSERT OR UPDATE ON chat_messages
  FOR EACH ROW EXECUTE FUNCTION chat_messages_search_vector_update();

-- User profile (singleton)
CREATE TABLE IF NOT EXISTS user_profile (
  id INTEGER PRIMARY KEY DEFAULT 1,
  display_name TEXT DEFAULT '',
  bio TEXT DEFAULT '',
  long_term_goals JSONB DEFAULT '[]',
  current_priorities JSONB DEFAULT '[]',
  preferences JSONB DEFAULT '{}',
  onboarding_completed BOOLEAN NOT NULL DEFAULT false,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT user_profile_singleton CHECK (id = 1)
);

-- Seed the singleton row
INSERT INTO user_profile (id) VALUES (1) ON CONFLICT (id) DO NOTHING;

-- Full-text search function for chat messages
CREATE OR REPLACE FUNCTION search_chat_messages(search_query TEXT)
RETURNS TABLE (
  id UUID, conversation_id UUID, role TEXT, content TEXT,
  created_at TIMESTAMPTZ, conversation_title TEXT
) AS $$
BEGIN
  RETURN QUERY
  SELECT m.id, m.conversation_id, m.role, m.content, m.created_at, c.title as conversation_title
  FROM chat_messages m
  JOIN chat_conversations c ON c.id = m.conversation_id
  WHERE m.search_vector @@ plainto_tsquery('english', search_query)
    AND c.deleted_at IS NULL
  ORDER BY ts_rank(m.search_vector, plainto_tsquery('english', search_query)) DESC
  LIMIT 50;
END;
$$ LANGUAGE plpgsql;
```

- [ ] **Step 2: Run migration against Supabase**

Verify tables exist:
```sql
SELECT table_name FROM information_schema.tables
WHERE table_name IN ('chat_conversations', 'chat_messages', 'user_profile');
```
Expected: 3 rows.

Verify singleton constraint:
```sql
INSERT INTO user_profile (id) VALUES (2);
```
Expected: ERROR — violates check constraint "user_profile_singleton".

- [ ] **Step 3: Commit**

```bash
git add migration/0.1.0/026_add_chat_tables.sql
git commit -m "feat: add chat tables (conversations, messages, user_profile)"
```

---

## Phase 2: Backend Services (Main Server)

### Task 3: Chat Conversation Service

**Files:**
- Create: `python/src/server/services/chat/__init__.py`
- Create: `python/src/server/services/chat/chat_service.py`
- Create: `python/tests/server/services/test_chat_service.py`

- [ ] **Step 1: Create empty service package**

```python
# python/src/server/services/chat/__init__.py
# Barrel exports added after all services are created (Task 5)
```

- [ ] **Step 2: Write the failing test**

```python
# python/tests/server/services/test_chat_service.py
import pytest
from unittest.mock import MagicMock, patch

from src.server.services.chat.chat_service import ChatService


@pytest.fixture
def mock_supabase():
    return MagicMock()


@pytest.fixture
def service(mock_supabase):
    return ChatService(supabase_client=mock_supabase)


def test_create_conversation_global(service, mock_supabase):
    mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [
        {"id": "conv-1", "title": "New Chat", "conversation_type": "global", "project_id": None}
    ]
    success, result = service.create_conversation(title="New Chat")
    assert success is True
    assert result["conversation"]["id"] == "conv-1"
    assert result["conversation"]["conversation_type"] == "global"


def test_create_conversation_project_scoped(service, mock_supabase):
    mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [
        {"id": "conv-2", "title": "Project Chat", "conversation_type": "project", "project_id": "proj-1"}
    ]
    success, result = service.create_conversation(title="Project Chat", project_id="proj-1")
    assert success is True
    assert result["conversation"]["project_id"] == "proj-1"


def test_list_conversations_excludes_deleted(service, mock_supabase):
    mock_supabase.table.return_value.select.return_value.is_.return_value.order.return_value.execute.return_value.data = [
        {"id": "conv-1", "title": "Active Chat", "deleted_at": None}
    ]
    success, result = service.list_conversations()
    assert success is True
    assert len(result["conversations"]) == 1


def test_soft_delete_conversation(service, mock_supabase):
    mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value.data = [
        {"id": "conv-1", "deleted_at": "2026-03-23T00:00:00Z"}
    ]
    success, result = service.delete_conversation("conv-1")
    assert success is True
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd python && uv run pytest tests/server/services/test_chat_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.server.services.chat.chat_service'`

- [ ] **Step 4: Write the ChatService implementation**

```python
# python/src/server/services/chat/chat_service.py
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from ...config.database import get_supabase_client

logger = logging.getLogger(__name__)


class ChatService:
    def __init__(self, supabase_client=None):
        self.supabase_client = supabase_client or get_supabase_client()

    def create_conversation(
        self,
        title: str = "New Chat",
        project_id: str | None = None,
        model_config: dict | None = None,
    ) -> tuple[bool, dict[str, Any]]:
        try:
            conversation_type = "project" if project_id else "global"
            data = {
                "title": title,
                "project_id": project_id,
                "conversation_type": conversation_type,
                "model_config": model_config or {},
            }
            response = self.supabase_client.table("chat_conversations").insert(data).execute()
            return True, {"conversation": response.data[0]}
        except Exception as e:
            logger.error(f"Failed to create conversation: {e}", exc_info=True)
            return False, {"error": str(e)}

    def list_conversations(
        self,
        project_id: str | None = None,
        conversation_type: str | None = None,
    ) -> tuple[bool, dict[str, Any]]:
        try:
            query = (
                self.supabase_client.table("chat_conversations")
                .select("*")
                .is_("deleted_at", "null")
                .order("updated_at", desc=True)
            )
            if project_id:
                query = query.eq("project_id", project_id)
            if conversation_type:
                query = query.eq("conversation_type", conversation_type)
            response = query.execute()
            return True, {"conversations": response.data}
        except Exception as e:
            logger.error(f"Failed to list conversations: {e}", exc_info=True)
            return False, {"error": str(e)}

    def get_conversation(self, conversation_id: str) -> tuple[bool, dict[str, Any]]:
        try:
            response = (
                self.supabase_client.table("chat_conversations")
                .select("*")
                .eq("id", conversation_id)
                .is_("deleted_at", "null")
                .single()
                .execute()
            )
            return True, {"conversation": response.data}
        except Exception as e:
            logger.error(f"Failed to get conversation {conversation_id}: {e}", exc_info=True)
            return False, {"error": str(e)}

    def update_conversation(
        self, conversation_id: str, **updates: Any
    ) -> tuple[bool, dict[str, Any]]:
        try:
            updates["updated_at"] = datetime.now(timezone.utc).isoformat()
            response = (
                self.supabase_client.table("chat_conversations")
                .update(updates)
                .eq("id", conversation_id)
                .execute()
            )
            return True, {"conversation": response.data[0]}
        except Exception as e:
            logger.error(f"Failed to update conversation {conversation_id}: {e}", exc_info=True)
            return False, {"error": str(e)}

    def list_categories(self) -> tuple[bool, dict[str, Any]]:
        try:
            response = (
                self.supabase_client.table("cortex_projects")
                .select("project_category")
                .not_.is_("project_category", "null")
                .execute()
            )
            categories = sorted(set(
                row["project_category"] for row in response.data if row.get("project_category")
            ))
            return True, {"categories": categories}
        except Exception as e:
            logger.error(f"Failed to list categories: {e}", exc_info=True)
            return False, {"error": str(e)}

    def delete_conversation(self, conversation_id: str) -> tuple[bool, dict[str, Any]]:
        try:
            response = (
                self.supabase_client.table("chat_conversations")
                .update({"deleted_at": datetime.now(timezone.utc).isoformat()})
                .eq("id", conversation_id)
                .execute()
            )
            return True, {"conversation": response.data[0]}
        except Exception as e:
            logger.error(f"Failed to delete conversation {conversation_id}: {e}", exc_info=True)
            return False, {"error": str(e)}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd python && uv run pytest tests/server/services/test_chat_service.py -v`
Expected: All 4 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add python/src/server/services/chat/ python/tests/server/services/test_chat_service.py
git commit -m "feat: add ChatService for conversation CRUD"
```

---

### Task 4: Chat Message Service

**Files:**
- Create: `python/src/server/services/chat/chat_message_service.py`
- Create: `python/tests/server/services/test_chat_message_service.py`

- [ ] **Step 1: Write the failing test**

```python
# python/tests/server/services/test_chat_message_service.py
import pytest
from unittest.mock import MagicMock

from src.server.services.chat.chat_message_service import ChatMessageService


@pytest.fixture
def mock_supabase():
    return MagicMock()


@pytest.fixture
def service(mock_supabase):
    return ChatMessageService(supabase_client=mock_supabase)


def test_save_user_message(service, mock_supabase):
    mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [
        {"id": "msg-1", "role": "user", "content": "Hello", "conversation_id": "conv-1"}
    ]
    # Also mock the conversation update
    mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value.data = [{}]

    success, result = service.save_message(
        conversation_id="conv-1", role="user", content="Hello"
    )
    assert success is True
    assert result["message"]["role"] == "user"


def test_save_assistant_message_with_tool_calls(service, mock_supabase):
    mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [
        {
            "id": "msg-2",
            "role": "assistant",
            "content": "I found 5 projects",
            "tool_calls": [{"name": "list_projects"}],
            "model_used": "anthropic:claude-sonnet-4-6",
            "token_count": 150,
        }
    ]
    mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value.data = [{}]

    success, result = service.save_message(
        conversation_id="conv-1",
        role="assistant",
        content="I found 5 projects",
        tool_calls=[{"name": "list_projects"}],
        model_used="anthropic:claude-sonnet-4-6",
        token_count=150,
    )
    assert success is True
    assert result["message"]["model_used"] == "anthropic:claude-sonnet-4-6"


def test_get_messages_paginated(service, mock_supabase):
    mock_supabase.table.return_value.select.return_value.eq.return_value.order.return_value.range.return_value.execute.return_value.data = [
        {"id": "msg-1", "content": "Hello"},
        {"id": "msg-2", "content": "Hi there"},
    ]
    success, result = service.get_messages("conv-1", limit=20, offset=0)
    assert success is True
    assert len(result["messages"]) == 2


def test_search_messages(service, mock_supabase):
    mock_supabase.rpc.return_value.execute.return_value.data = [
        {"id": "msg-1", "content": "synergy between projects", "conversation_id": "conv-1"}
    ]
    success, result = service.search_messages("synergy")
    assert success is True
    assert len(result["messages"]) >= 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd python && uv run pytest tests/server/services/test_chat_message_service.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write the ChatMessageService implementation**

```python
# python/src/server/services/chat/chat_message_service.py
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from ...config.database import get_supabase_client

logger = logging.getLogger(__name__)


class ChatMessageService:
    def __init__(self, supabase_client=None):
        self.supabase_client = supabase_client or get_supabase_client()

    def save_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        tool_calls: list[dict] | None = None,
        tool_results: list[dict] | None = None,
        model_used: str | None = None,
        token_count: int | None = None,
    ) -> tuple[bool, dict[str, Any]]:
        try:
            data: dict[str, Any] = {
                "conversation_id": conversation_id,
                "role": role,
                "content": content,
            }
            if tool_calls is not None:
                data["tool_calls"] = tool_calls
            if tool_results is not None:
                data["tool_results"] = tool_results
            if model_used is not None:
                data["model_used"] = model_used
            if token_count is not None:
                data["token_count"] = token_count

            response = self.supabase_client.table("chat_messages").insert(data).execute()

            # Update conversation's updated_at timestamp
            self.supabase_client.table("chat_conversations").update(
                {"updated_at": datetime.now(timezone.utc).isoformat()}
            ).eq("id", conversation_id).execute()

            return True, {"message": response.data[0]}
        except Exception as e:
            logger.error(f"Failed to save message: {e}", exc_info=True)
            return False, {"error": str(e)}

    def get_messages(
        self,
        conversation_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[bool, dict[str, Any]]:
        try:
            response = (
                self.supabase_client.table("chat_messages")
                .select("*")
                .eq("conversation_id", conversation_id)
                .order("created_at", desc=False)
                .range(offset, offset + limit - 1)
                .execute()
            )
            return True, {"messages": response.data}
        except Exception as e:
            logger.error(f"Failed to get messages for {conversation_id}: {e}", exc_info=True)
            return False, {"error": str(e)}

    def search_messages(self, query: str) -> tuple[bool, dict[str, Any]]:
        try:
            response = self.supabase_client.rpc(
                "search_chat_messages",
                {"search_query": query},
            ).execute()
            return True, {"messages": response.data}
        except Exception as e:
            logger.error(f"Failed to search messages: {e}", exc_info=True)
            return False, {"error": str(e)}
```

Note: The `search_chat_messages` RPC function needs to be added to migration 026. Add this to the end of the migration file:

```sql
-- Full-text search function for chat messages
CREATE OR REPLACE FUNCTION search_chat_messages(search_query TEXT)
RETURNS TABLE (
  id UUID, conversation_id UUID, role TEXT, content TEXT,
  created_at TIMESTAMPTZ, conversation_title TEXT
) AS $$
BEGIN
  RETURN QUERY
  SELECT m.id, m.conversation_id, m.role, m.content, m.created_at, c.title as conversation_title
  FROM chat_messages m
  JOIN chat_conversations c ON c.id = m.conversation_id
  WHERE m.search_vector @@ plainto_tsquery('english', search_query)
    AND c.deleted_at IS NULL
  ORDER BY ts_rank(m.search_vector, plainto_tsquery('english', search_query)) DESC
  LIMIT 50;
END;
$$ LANGUAGE plpgsql;
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd python && uv run pytest tests/server/services/test_chat_message_service.py -v`
Expected: All 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add python/src/server/services/chat/chat_message_service.py python/tests/server/services/test_chat_message_service.py
git commit -m "feat: add ChatMessageService for message CRUD and search"
```

---

### Task 5: User Profile Service

**Files:**
- Create: `python/src/server/services/chat/user_profile_service.py`
- Create: `python/tests/server/services/test_user_profile_service.py`

- [ ] **Step 1: Write the failing test**

```python
# python/tests/server/services/test_user_profile_service.py
import pytest
from unittest.mock import MagicMock

from src.server.services.chat.user_profile_service import UserProfileService


@pytest.fixture
def mock_supabase():
    return MagicMock()


@pytest.fixture
def service(mock_supabase):
    return UserProfileService(supabase_client=mock_supabase)


def test_get_profile_returns_singleton(service, mock_supabase):
    mock_supabase.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "id": 1, "display_name": "Test User", "bio": "CTO", "onboarding_completed": True
    }
    success, result = service.get_profile()
    assert success is True
    assert result["profile"]["display_name"] == "Test User"


def test_update_profile_upserts(service, mock_supabase):
    mock_supabase.table.return_value.upsert.return_value.execute.return_value.data = [
        {"id": 1, "display_name": "Updated", "bio": "Engineer"}
    ]
    success, result = service.update_profile(display_name="Updated", bio="Engineer")
    assert success is True
    assert result["profile"]["display_name"] == "Updated"


def test_get_profile_creates_default_if_missing(service, mock_supabase):
    # First call raises (no row), second returns default
    mock_supabase.table.return_value.select.return_value.eq.return_value.single.return_value.execute.side_effect = [
        Exception("No rows"),
    ]
    mock_supabase.table.return_value.upsert.return_value.execute.return_value.data = [
        {"id": 1, "display_name": "", "bio": "", "onboarding_completed": False}
    ]
    success, result = service.get_profile()
    assert success is True
    assert result["profile"]["onboarding_completed"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd python && uv run pytest tests/server/services/test_user_profile_service.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write the UserProfileService implementation**

```python
# python/src/server/services/chat/user_profile_service.py
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from ...config.database import get_supabase_client

logger = logging.getLogger(__name__)

SINGLETON_ID = 1


class UserProfileService:
    def __init__(self, supabase_client=None):
        self.supabase_client = supabase_client or get_supabase_client()

    def get_profile(self) -> tuple[bool, dict[str, Any]]:
        try:
            response = (
                self.supabase_client.table("user_profile")
                .select("*")
                .eq("id", SINGLETON_ID)
                .single()
                .execute()
            )
            return True, {"profile": response.data}
        except Exception:
            # Row doesn't exist — create default
            return self._ensure_default_profile()

    def update_profile(self, **fields: Any) -> tuple[bool, dict[str, Any]]:
        try:
            fields["id"] = SINGLETON_ID
            fields["updated_at"] = datetime.now(timezone.utc).isoformat()
            response = (
                self.supabase_client.table("user_profile")
                .upsert(fields)
                .execute()
            )
            return True, {"profile": response.data[0]}
        except Exception as e:
            logger.error(f"Failed to update profile: {e}", exc_info=True)
            return False, {"error": str(e)}

    def _ensure_default_profile(self) -> tuple[bool, dict[str, Any]]:
        try:
            default = {
                "id": SINGLETON_ID,
                "display_name": "",
                "bio": "",
                "long_term_goals": [],
                "current_priorities": [],
                "preferences": {},
                "onboarding_completed": False,
            }
            response = (
                self.supabase_client.table("user_profile")
                .upsert(default)
                .execute()
            )
            return True, {"profile": response.data[0]}
        except Exception as e:
            logger.error(f"Failed to create default profile: {e}", exc_info=True)
            return False, {"error": str(e)}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd python && uv run pytest tests/server/services/test_user_profile_service.py -v`
Expected: All 3 tests PASS.

- [ ] **Step 5: Update barrel exports in __init__.py**

Now that all three services exist, update `python/src/server/services/chat/__init__.py`:

```python
from .chat_service import ChatService
from .chat_message_service import ChatMessageService
from .user_profile_service import UserProfileService

__all__ = ["ChatService", "ChatMessageService", "UserProfileService"]
```

- [ ] **Step 6: Commit**

```bash
git add python/src/server/services/chat/ python/tests/server/services/test_user_profile_service.py
git commit -m "feat: add UserProfileService with singleton pattern, complete service barrel exports"
```

---

### Task 6: Chat API Routes

**Files:**
- Create: `python/src/server/api_routes/chat_api.py`
- Modify: `python/src/server/main.py`
- Delete: `python/src/server/api_routes/agent_chat_api.py`
- Create: `python/tests/server/api_routes/test_chat_api.py`

- [ ] **Step 1: Write the failing test**

```python
# python/tests/server/api_routes/test_chat_api.py
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from src.server.main import app

client = TestClient(app)


@patch("src.server.api_routes.chat_api.ChatService")
def test_create_conversation(mock_service_class):
    mock_service = MagicMock()
    mock_service_class.return_value = mock_service
    mock_service.create_conversation.return_value = (
        True, {"conversation": {"id": "conv-1", "title": "Test"}}
    )
    response = client.post("/api/chat/conversations", json={"title": "Test"})
    assert response.status_code == 200
    assert response.json()["conversation"]["id"] == "conv-1"


@patch("src.server.api_routes.chat_api.ChatService")
def test_list_conversations(mock_service_class):
    mock_service = MagicMock()
    mock_service_class.return_value = mock_service
    mock_service.list_conversations.return_value = (
        True, {"conversations": []}
    )
    response = client.get("/api/chat/conversations")
    assert response.status_code == 200


@patch("src.server.api_routes.chat_api.UserProfileService")
def test_get_profile(mock_service_class):
    mock_service = MagicMock()
    mock_service_class.return_value = mock_service
    mock_service.get_profile.return_value = (
        True, {"profile": {"id": 1, "display_name": "Test"}}
    )
    response = client.get("/api/chat/profile")
    assert response.status_code == 200
    assert response.json()["profile"]["display_name"] == "Test"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd python && uv run pytest tests/server/api_routes/test_chat_api.py -v`
Expected: FAIL — routes don't exist yet.

- [ ] **Step 3: Write the chat API routes**

```python
# python/src/server/api_routes/chat_api.py
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Any

from ..services.chat.chat_service import ChatService
from ..services.chat.chat_message_service import ChatMessageService
from ..services.chat.user_profile_service import UserProfileService
from ..config.logfire_config import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])


# --- Request Models ---

class CreateConversationRequest(BaseModel):
    title: str = Field(default="New Chat", description="Conversation title")
    project_id: str | None = Field(default=None, description="Project ID for scoped chat")
    model_config_data: dict | None = Field(default=None, alias="model_config", description="Model configuration")

class UpdateConversationRequest(BaseModel):
    title: str | None = None
    model_config_data: dict | None = Field(default=None, alias="model_config")
    action_mode: bool | None = None

class SaveMessageRequest(BaseModel):
    role: str = Field(..., description="Message role: user, assistant, system, tool")
    content: str = Field(..., description="Message content")
    tool_calls: list[dict] | None = None
    tool_results: list[dict] | None = None
    model_used: str | None = None
    token_count: int | None = None

class UpdateProfileRequest(BaseModel):
    display_name: str | None = None
    bio: str | None = None
    long_term_goals: list | None = None
    current_priorities: list | None = None
    preferences: dict | None = None
    onboarding_completed: bool | None = None


# --- Conversation Endpoints ---

@router.get("/conversations")
async def list_conversations(
    project_id: str | None = Query(None),
    conversation_type: str | None = Query(None),
):
    service = ChatService()
    success, result = service.list_conversations(project_id=project_id, conversation_type=conversation_type)
    if not success:
        raise HTTPException(status_code=500, detail=result.get("error", "Unknown error"))
    return result


@router.post("/conversations")
async def create_conversation(request: CreateConversationRequest):
    service = ChatService()
    success, result = service.create_conversation(
        title=request.title,
        project_id=request.project_id,
        model_config=request.model_config_data,
    )
    if not success:
        raise HTTPException(status_code=500, detail=result.get("error", "Unknown error"))
    return result


@router.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str):
    service = ChatService()
    success, result = service.get_conversation(conversation_id)
    if not success:
        raise HTTPException(status_code=404, detail=result.get("error", "Unknown error"))
    return result


@router.put("/conversations/{conversation_id}")
async def update_conversation(conversation_id: str, request: UpdateConversationRequest):
    service = ChatService()
    updates = {k: v for k, v in request.model_dump(by_alias=True, exclude_none=True).items()}
    success, result = service.update_conversation(conversation_id, **updates)
    if not success:
        raise HTTPException(status_code=500, detail=result.get("error", "Unknown error"))
    return result


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str):
    service = ChatService()
    success, result = service.delete_conversation(conversation_id)
    if not success:
        raise HTTPException(status_code=500, detail=result.get("error", "Unknown error"))
    return result


# --- Message Endpoints ---

@router.get("/conversations/{conversation_id}/messages")
async def get_messages(
    conversation_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    service = ChatMessageService()
    success, result = service.get_messages(conversation_id, limit=limit, offset=offset)
    if not success:
        raise HTTPException(status_code=500, detail=result.get("error", "Unknown error"))
    return result


@router.post("/conversations/{conversation_id}/messages")
async def save_message(conversation_id: str, request: SaveMessageRequest):
    service = ChatMessageService()
    success, result = service.save_message(
        conversation_id=conversation_id,
        role=request.role,
        content=request.content,
        tool_calls=request.tool_calls,
        tool_results=request.tool_results,
        model_used=request.model_used,
        token_count=request.token_count,
    )
    if not success:
        raise HTTPException(status_code=500, detail=result.get("error", "Unknown error"))
    return result


# --- Search ---

@router.get("/messages/search")
async def search_messages(q: str = Query(..., min_length=1)):
    service = ChatMessageService()
    success, result = service.search_messages(q)
    if not success:
        raise HTTPException(status_code=500, detail=result.get("error", "Unknown error"))
    return result


# --- Profile Endpoints ---

@router.get("/profile")
async def get_profile():
    service = UserProfileService()
    success, result = service.get_profile()
    if not success:
        raise HTTPException(status_code=500, detail=result.get("error", "Unknown error"))
    return result


@router.put("/profile")
async def update_profile(request: UpdateProfileRequest):
    service = UserProfileService()
    updates = {k: v for k, v in request.model_dump(exclude_none=True).items()}
    success, result = service.update_profile(**updates)
    if not success:
        raise HTTPException(status_code=500, detail=result.get("error", "Unknown error"))
    return result


# --- Categories ---

@router.get("/categories")
async def list_categories():
    service = ChatService()
    success, result = service.list_categories()
    if not success:
        raise HTTPException(status_code=500, detail=result.get("error", "Unknown error"))
    return result
```

- [ ] **Step 4: Delete old agent_chat_api.py and register new router in main.py**

Delete `python/src/server/api_routes/agent_chat_api.py`.

In `python/src/server/main.py`:
- Remove the import: `from .api_routes.agent_chat_api import router as agent_chat_router`
- Remove: `app.include_router(agent_chat_router)`
- Add import: `from .api_routes.chat_api import router as chat_router`
- Add: `app.include_router(chat_router)`

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd python && uv run pytest tests/server/api_routes/test_chat_api.py -v`
Expected: All 3 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add python/src/server/api_routes/chat_api.py python/src/server/main.py python/tests/server/api_routes/test_chat_api.py
git rm python/src/server/api_routes/agent_chat_api.py
git commit -m "feat: add chat API routes, delete legacy agent_chat_api stub"
```

---

## Phase 3: Agent Service — ChatAgent & Streaming

### Task 7: ChatAgent Implementation

**Files:**
- Create: `python/src/agents/chat_agent.py`
- Create: `python/src/agents/chat_tools.py`

- [ ] **Step 1: Create ChatAgent with advisor tools**

Create `python/src/agents/chat_tools.py` with tool implementations that use MCPClient:

```python
# python/src/agents/chat_tools.py
"""ChatAgent tool implementations using MCPClient for data operations."""
from __future__ import annotations

import json
import logging
from typing import Any

from .mcp_client import get_mcp_client

logger = logging.getLogger(__name__)


async def tool_search_knowledge_base(query: str, source_id: str | None = None, match_count: int = 5) -> str:
    client = await get_mcp_client()
    result = await client.perform_rag_query(query, source=source_id, match_count=match_count)
    return json.dumps(result, default=str)


async def tool_list_projects() -> str:
    client = await get_mcp_client()
    result = await client.call_tool("find_projects")
    return result


async def tool_get_project_detail(project_id: str) -> str:
    client = await get_mcp_client()
    result = await client.call_tool("find_projects", project_id=project_id)
    return result


async def tool_list_tasks(project_id: str | None = None, status: str | None = None) -> str:
    client = await get_mcp_client()
    kwargs: dict[str, Any] = {}
    if project_id:
        kwargs["filter_by"] = "project"
        kwargs["filter_value"] = project_id
    elif status:
        kwargs["filter_by"] = "status"
        kwargs["filter_value"] = status
    result = await client.call_tool("find_tasks", **kwargs)
    return result


async def tool_get_task_detail(task_id: str) -> str:
    client = await get_mcp_client()
    result = await client.call_tool("find_tasks", task_id=task_id)
    return result


async def tool_list_documents(project_id: str) -> str:
    client = await get_mcp_client()
    result = await client.call_tool("find_documents", project_id=project_id)
    return result


async def tool_get_session_history(query: str | None = None) -> str:
    client = await get_mcp_client()
    if query:
        result = await client.call_tool("cortex_search_sessions", query=query)
    else:
        result = await client.call_tool("cortex_search_sessions")
    return result


async def tool_search_code_examples(query: str) -> str:
    client = await get_mcp_client()
    result = await client.search_code_examples(query)
    return json.dumps(result, default=str)


async def tool_suggest_project_category(project_name: str, description: str, existing_categories: list[str]) -> str:
    """Returns a suggested category for the AI to present to the user."""
    return json.dumps({
        "project_name": project_name,
        "description": description,
        "existing_categories": existing_categories,
        "instruction": "Based on the project name, description, and existing categories, suggest the most appropriate category.",
    })
```

- [ ] **Step 2: Create the ChatAgent class**

```python
# python/src/agents/chat_agent.py
"""ChatAgent — the AI brain for the Cortex chat interface."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from pydantic_ai import Agent, RunContext

from .base_agent import CortexDependencies

logger = logging.getLogger(__name__)


@dataclass
class ChatDependencies(CortexDependencies):
    conversation_id: str = ""
    project_id: str | None = None
    user_profile: dict = field(default_factory=dict)
    action_mode: bool = False
    model_override: str | None = None
    conversation_history: list[dict] = field(default_factory=list)


def create_chat_agent(model: str = "openai:gpt-4o") -> Agent[ChatDependencies, str]:
    agent = Agent(
        model=model,
        deps_type=ChatDependencies,
        result_type=str,
        retries=2,
    )

    @agent.system_prompt
    async def build_system_prompt(ctx: RunContext[ChatDependencies]) -> str:
        deps = ctx.deps
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        parts = [
            "You are Cortex, an AI assistant that helps manage and prioritize projects.",
            "You have access to the user's projects, tasks, knowledge base, and session history.",
            "Be concise, actionable, and helpful. When recommending priorities, explain your reasoning.",
            f"\nCurrent date/time: {now}",
        ]

        # User context
        profile = deps.user_profile
        if profile.get("bio"):
            parts.append(f"\nAbout the user: {profile['bio']}")
        if profile.get("long_term_goals"):
            goals = ", ".join(str(g) for g in profile["long_term_goals"])
            parts.append(f"Long-term goals: {goals}")
        if profile.get("current_priorities"):
            priorities = ", ".join(str(p) for p in profile["current_priorities"])
            parts.append(f"Current priorities: {priorities}")
        if profile.get("preferences"):
            parts.append(f"Communication preferences: {profile['preferences']}")

        # Project context for project-scoped chats
        if deps.project_id:
            parts.append(f"\nThis conversation is scoped to project ID: {deps.project_id}")
            parts.append("Focus your responses on this project's context.")

        # Action mode
        if deps.action_mode:
            parts.append("\nAction mode is ENABLED. You can create tasks, update projects, and take other actions.")
            parts.append("Always explain what you're about to do and confirm before taking destructive actions.")
        else:
            parts.append("\nYou are in advisor mode. You can search and analyze but cannot modify data.")
            parts.append("If the user asks you to take an action, suggest they enable action mode.")

        # Onboarding
        if not profile.get("onboarding_completed", False):
            parts.append("\nThe user has not completed onboarding. Start by asking them about themselves.")
            parts.append("Ask one question at a time to build their profile.")

        return "\n".join(parts)

    # Register advisor tools (always available)
    from . import chat_tools

    @agent.tool
    async def search_knowledge_base(ctx: RunContext[ChatDependencies], query: str) -> str:
        """Search the knowledge base for relevant documents and information."""
        return await chat_tools.tool_search_knowledge_base(query)

    @agent.tool
    async def list_projects(ctx: RunContext[ChatDependencies]) -> str:
        """List all projects with their status, categories, and goals."""
        return await chat_tools.tool_list_projects()

    @agent.tool
    async def get_project_detail(ctx: RunContext[ChatDependencies], project_id: str) -> str:
        """Get detailed information about a specific project."""
        return await chat_tools.tool_get_project_detail(project_id)

    @agent.tool
    async def list_tasks(ctx: RunContext[ChatDependencies], project_id: str = "", status: str = "") -> str:
        """List tasks, optionally filtered by project or status."""
        return await chat_tools.tool_list_tasks(
            project_id=project_id or None,
            status=status or None,
        )

    @agent.tool
    async def get_session_history(ctx: RunContext[ChatDependencies], query: str = "") -> str:
        """Search recent session history across machines to understand activity patterns."""
        return await chat_tools.tool_get_session_history(query=query or None)

    @agent.tool
    async def get_task_detail(ctx: RunContext[ChatDependencies], task_id: str) -> str:
        """Get detailed information about a specific task."""
        return await chat_tools.tool_get_task_detail(task_id)

    @agent.tool
    async def list_documents(ctx: RunContext[ChatDependencies], project_id: str) -> str:
        """List documents for a specific project."""
        return await chat_tools.tool_list_documents(project_id)

    @agent.tool
    async def search_code_examples(ctx: RunContext[ChatDependencies], query: str) -> str:
        """Search for code examples in the knowledge base."""
        return await chat_tools.tool_search_code_examples(query)

    @agent.tool
    async def suggest_project_category(ctx: RunContext[ChatDependencies], project_name: str, description: str) -> str:
        """Suggest a category for a project based on its name, description, and existing categories."""
        from . import chat_tools as ct
        # Fetch existing categories via MCP
        client = await get_mcp_client()
        projects_data = await client.call_tool("find_projects")
        import json as j
        projects = j.loads(projects_data) if isinstance(projects_data, str) else projects_data
        existing = list(set(p.get("project_category", "") for p in projects if p.get("project_category")))
        return await ct.tool_suggest_project_category(project_name, description, existing)

    return agent
```

- [ ] **Step 3: Commit**

```bash
git add python/src/agents/chat_agent.py python/src/agents/chat_tools.py
git commit -m "feat: add ChatAgent with advisor tools via MCPClient"
```

---

### Task 8: SSE Streaming Endpoint in Agent Service

**Files:**
- Modify: `python/src/agents/server.py`

- [ ] **Step 1: Add chat streaming endpoint to agent server**

Add the following to `python/src/agents/server.py`. Place it after the existing `/agents/{agent_type}/stream` endpoint:

```python
# Add these imports at the top
import asyncio
import httpx
from .chat_agent import create_chat_agent, ChatDependencies

# Add this endpoint
@app.post("/agents/chat/stream")
async def stream_chat(request: Request):
    """SSE streaming endpoint for the chat interface."""
    body = await request.json()
    conversation_id = body["conversation_id"]
    message = body["message"]
    user_profile = body.get("user_profile", {})
    project_id = body.get("project_id")
    action_mode = body.get("action_mode", False)
    model = body.get("model", "openai:gpt-4o")
    conversation_history = body.get("conversation_history", [])

    # Persist user message via Main Server
    api_url = os.environ.get("CORTEX_API_URL", "http://localhost:8181")
    async with httpx.AsyncClient(timeout=30) as client:
        await client.post(
            f"{api_url}/api/chat/conversations/{conversation_id}/messages",
            json={"role": "user", "content": message},
        )

    deps = ChatDependencies(
        conversation_id=conversation_id,
        project_id=project_id,
        user_profile=user_profile,
        action_mode=action_mode,
        model_override=model,
        conversation_history=conversation_history,
    )

    agent = create_chat_agent(model=model)

    # Build message list from conversation history
    from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, TextPart, UserPromptPart
    messages: list[ModelMessage] = []
    for msg in conversation_history[-20:]:  # Last 20 messages for context window
        if msg["role"] == "user":
            messages.append(ModelRequest(parts=[UserPromptPart(content=msg["content"])]))
        elif msg["role"] == "assistant":
            messages.append(ModelResponse(parts=[TextPart(content=msg["content"])]))

    async def generate():
        try:
            yield f"data: {json.dumps({'type': 'message_start', 'conversation_id': conversation_id})}\n\n"

            full_content = ""
            last_heartbeat = asyncio.get_event_loop().time()
            async with agent.run_stream(message, deps=deps, message_history=messages) as stream:
                async for chunk in stream.stream_text(delta=True):
                    full_content += chunk
                    yield f"data: {json.dumps({'type': 'text_delta', 'delta': chunk})}\n\n"
                    # Heartbeat every 15 seconds during long tool calls
                    now = asyncio.get_event_loop().time()
                    if now - last_heartbeat > 15:
                        yield ": heartbeat\n\n"
                        last_heartbeat = now

            # Persist assistant message via Main Server
            async with httpx.AsyncClient(timeout=30) as client:
                save_response = await client.post(
                    f"{api_url}/api/chat/conversations/{conversation_id}/messages",
                    json={
                        "role": "assistant",
                        "content": full_content,
                        "model_used": model,
                    },
                )
                saved_msg = save_response.json().get("message", {})

            # Auto-generate conversation title from first assistant response
            if len(conversation_history) == 0:  # First message in conversation
                title_prompt = f"Generate a short title (max 6 words) for a conversation that starts with: {message[:200]}"
                # Use a quick non-streaming call to generate the title
                title_agent = create_chat_agent(model=model)
                title_result = await title_agent.run(title_prompt, deps=deps)
                title = title_result.data.strip('"').strip()[:100]
                async with httpx.AsyncClient(timeout=10) as client:
                    await client.put(
                        f"{api_url}/api/chat/conversations/{conversation_id}",
                        json={"title": title},
                    )

            yield f"data: {json.dumps({'type': 'message_complete', 'message_id': saved_msg.get('id', ''), 'model_used': model, 'persisted': True})}\n\n"

        except Exception as e:
            logger.error(f"Chat stream error: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'error': str(e), 'retryable': True})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
```

- [ ] **Step 2: Test manually**

Start the agent service and main server, then test with curl:
```bash
curl -X POST http://localhost:8052/agents/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"conversation_id": "test", "message": "Hello", "user_profile": {}, "model": "openai:gpt-4o"}' \
  --no-buffer
```
Expected: SSE events stream back with `message_start`, `text_delta`, and `message_complete`.

- [ ] **Step 3: Commit**

```bash
git add python/src/agents/server.py
git commit -m "feat: add SSE streaming endpoint for chat in agent service"
```

---

## Phase 4: Frontend Foundation

### Task 9: Vite Proxy Configuration

**Files:**
- Modify: `cortex-ui/vite.config.ts`

- [ ] **Step 1: Add /agents proxy rule**

In `cortex-ui/vite.config.ts`, add a new proxy entry BEFORE the `/api` catch-all (order matters — more specific routes first):

```typescript
// Add after the '/api/agent-work-orders' proxy and before '/api'
'/agents': {
  target: isDocker ? 'http://cortex-agents:8052' : 'http://localhost:8052',
  changeOrigin: true,
  configure: (proxy) => {
    proxy.on('error', (err, req, res) => {
      if (res && !res.headersSent) {
        res.writeHead(502, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: 'Agent service unavailable' }));
      }
    });
  },
},
```

- [ ] **Step 2: Verify proxy works**

Start the dev server and verify: `curl http://localhost:3737/agents/health`
Expected: Returns health response from agent service (or 502 if agent service not running — which is fine).

- [ ] **Step 3: Commit**

```bash
git add cortex-ui/vite.config.ts
git commit -m "feat: add /agents Vite proxy for agent service SSE"
```

---

### Task 10: Frontend Types

**Files:**
- Create: `cortex-ui/src/features/chat/types/index.ts`

- [ ] **Step 1: Define chat types**

```typescript
// cortex-ui/src/features/chat/types/index.ts

export interface ChatConversation {
  id: string;
  title: string;
  project_id: string | null;
  conversation_type: "global" | "project";
  model_config: Record<string, unknown>;
  action_mode: boolean;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
  metadata: Record<string, unknown>;
}

export interface ChatMessage {
  id: string;
  conversation_id: string;
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  tool_calls: ToolCall[] | null;
  tool_results: ToolResult[] | null;
  model_used: string | null;
  token_count: number | null;
  created_at: string;
}

export interface ToolCall {
  name: string;
  args: Record<string, unknown>;
}

export interface ToolResult {
  name: string;
  result_summary: string;
  duration_ms: number;
}

export interface UserProfile {
  id: number;
  display_name: string;
  bio: string;
  long_term_goals: string[];
  current_priorities: string[];
  preferences: Record<string, unknown>;
  onboarding_completed: boolean;
  updated_at: string;
}

// SSE Event types
export type SSEEventType =
  | "message_start"
  | "text_delta"
  | "tool_start"
  | "tool_result"
  | "action_request"
  | "message_complete"
  | "error"
  | "heartbeat";

export interface SSEEvent {
  type: SSEEventType;
  [key: string]: unknown;
}

export interface TextDeltaEvent extends SSEEvent {
  type: "text_delta";
  delta: string;
}

export interface ToolStartEvent extends SSEEvent {
  type: "tool_start";
  tool_name: string;
  tool_args: Record<string, unknown>;
}

export interface ToolResultEvent extends SSEEvent {
  type: "tool_result";
  tool_name: string;
  result_summary: string;
  duration_ms: number;
}

export interface MessageCompleteEvent extends SSEEvent {
  type: "message_complete";
  message_id: string;
  model_used: string;
  token_count: number;
  persisted: boolean;
}

export interface ActionRequestEvent extends SSEEvent {
  type: "action_request";
  action_id: string;
  action: string;
  details: Record<string, unknown>;
  requires_approval: boolean;
}

// Streaming state
export interface StreamingMessage {
  content: string;
  toolCalls: ToolStartEvent[];
  toolResults: ToolResultEvent[];
  pendingAction: ActionRequestEvent | null;
  isStreaming: boolean;
}

export interface CreateConversationRequest {
  title?: string;
  project_id?: string | null;
  model_config?: Record<string, unknown>;
}

export interface UpdateConversationRequest {
  title?: string;
  model_config?: Record<string, unknown>;
  action_mode?: boolean;
}

export interface SendMessageRequest {
  conversation_id: string;
  message: string;
  user_profile: UserProfile;
  project_id?: string | null;
  action_mode?: boolean;
  model?: string;
  conversation_history?: Array<{ role: string; content: string }>;
}
```

- [ ] **Step 2: Commit**

```bash
git add cortex-ui/src/features/chat/types/index.ts
git commit -m "feat: add chat TypeScript type definitions"
```

---

### Task 11: Frontend Chat Service

**Files:**
- Create: `cortex-ui/src/features/chat/services/chatService.ts`
- Delete: `cortex-ui/src/services/agentChatService.ts`

- [ ] **Step 1: Write the chat service**

```typescript
// cortex-ui/src/features/chat/services/chatService.ts
import { callAPIWithETag } from "@/features/shared/api/apiClient";
import type {
  ChatConversation,
  ChatMessage,
  CreateConversationRequest,
  UpdateConversationRequest,
  UserProfile,
  SendMessageRequest,
} from "../types";

export const chatService = {
  // --- Conversations (Main Server) ---

  async listConversations(params?: {
    project_id?: string;
    conversation_type?: string;
  }): Promise<ChatConversation[]> {
    const query = new URLSearchParams();
    if (params?.project_id) query.set("project_id", params.project_id);
    if (params?.conversation_type) query.set("conversation_type", params.conversation_type);
    const qs = query.toString();
    const response = await callAPIWithETag<{ conversations: ChatConversation[] }>(
      `/api/chat/conversations${qs ? `?${qs}` : ""}`
    );
    return response.conversations || [];
  },

  async createConversation(data: CreateConversationRequest): Promise<ChatConversation> {
    const response = await callAPIWithETag<{ conversation: ChatConversation }>(
      "/api/chat/conversations",
      { method: "POST", body: JSON.stringify(data) }
    );
    return response.conversation;
  },

  async getConversation(id: string): Promise<ChatConversation> {
    const response = await callAPIWithETag<{ conversation: ChatConversation }>(
      `/api/chat/conversations/${id}`
    );
    return response.conversation;
  },

  async updateConversation(id: string, data: UpdateConversationRequest): Promise<ChatConversation> {
    const response = await callAPIWithETag<{ conversation: ChatConversation }>(
      `/api/chat/conversations/${id}`,
      { method: "PUT", body: JSON.stringify(data) }
    );
    return response.conversation;
  },

  async deleteConversation(id: string): Promise<void> {
    await callAPIWithETag(`/api/chat/conversations/${id}`, { method: "DELETE" });
  },

  // --- Messages (Main Server) ---

  async getMessages(conversationId: string, limit = 50, offset = 0): Promise<ChatMessage[]> {
    const response = await callAPIWithETag<{ messages: ChatMessage[] }>(
      `/api/chat/conversations/${conversationId}/messages?limit=${limit}&offset=${offset}`
    );
    return response.messages || [];
  },

  async searchMessages(query: string): Promise<ChatMessage[]> {
    const response = await callAPIWithETag<{ messages: ChatMessage[] }>(
      `/api/chat/messages/search?q=${encodeURIComponent(query)}`
    );
    return response.messages || [];
  },

  // --- Profile (Main Server) ---

  async getProfile(): Promise<UserProfile> {
    const response = await callAPIWithETag<{ profile: UserProfile }>("/api/chat/profile");
    return response.profile;
  },

  async updateProfile(data: Partial<UserProfile>): Promise<UserProfile> {
    const response = await callAPIWithETag<{ profile: UserProfile }>(
      "/api/chat/profile",
      { method: "PUT", body: JSON.stringify(data) }
    );
    return response.profile;
  },

  // --- Categories (Main Server) ---

  async listCategories(): Promise<string[]> {
    const response = await callAPIWithETag<{ categories: string[] }>("/api/chat/categories");
    return response.categories || [];
  },

  // --- Streaming (Agent Service via Vite proxy) ---

  streamMessage(
    data: SendMessageRequest,
    onEvent: (event: Record<string, unknown>) => void,
    onError: (error: Error) => void,
  ): AbortController {
    const controller = new AbortController();

    fetch("/agents/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok) throw new Error(`Stream failed: ${response.status}`);
        const reader = response.body?.getReader();
        if (!reader) throw new Error("No response body");

        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() || "";

          for (const line of lines) {
            if (line.startsWith("data: ")) {
              try {
                const event = JSON.parse(line.slice(6));
                onEvent(event);
              } catch {
                // Skip malformed events
              }
            }
          }
        }
      })
      .catch((error) => {
        if (error.name !== "AbortError") {
          onError(error);
        }
      });

    return controller;
  },

  // --- Agent Health ---

  async checkAgentHealth(): Promise<boolean> {
    try {
      const response = await fetch("/agents/health", { signal: AbortSignal.timeout(5000) });
      return response.ok;
    } catch {
      return false;
    }
  },

  // --- Action Approval ---

  async confirmAction(actionId: string): Promise<void> {
    await fetch("/agents/chat/confirm-action", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action_id: actionId }),
    });
  },

  async denyAction(actionId: string): Promise<void> {
    await fetch("/agents/chat/deny-action", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action_id: actionId }),
    });
  },
};
```

- [ ] **Step 2: Delete legacy service**

Delete `cortex-ui/src/services/agentChatService.ts`.

- [ ] **Step 3: Commit**

```bash
git add cortex-ui/src/features/chat/services/chatService.ts
git rm cortex-ui/src/services/agentChatService.ts
git commit -m "feat: add chat service layer, delete legacy agentChatService"
```

---

### Task 12: TanStack Query Hooks

**Files:**
- Create: `cortex-ui/src/features/chat/hooks/useChatQueries.ts`

- [ ] **Step 1: Write query hooks with key factory**

```typescript
// cortex-ui/src/features/chat/hooks/useChatQueries.ts
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { DISABLED_QUERY_KEY, STALE_TIMES } from "@/features/shared/config/queryPatterns";
import { chatService } from "../services/chatService";
import type { CreateConversationRequest, UpdateConversationRequest, UserProfile } from "../types";

export const chatKeys = {
  all: ["chat"] as const,
  conversations: () => [...chatKeys.all, "conversations"] as const,
  conversationDetail: (id: string) => [...chatKeys.all, "conversations", id] as const,
  messages: (conversationId: string) => [...chatKeys.all, "messages", conversationId] as const,
  profile: () => [...chatKeys.all, "profile"] as const,
  categories: () => [...chatKeys.all, "categories"] as const,
  search: (query: string) => [...chatKeys.all, "search", query] as const,
  agentHealth: () => [...chatKeys.all, "agentHealth"] as const,
};

// --- Conversations ---

export function useConversations(params?: { project_id?: string; conversation_type?: string }) {
  return useQuery({
    queryKey: chatKeys.conversations(),
    queryFn: () => chatService.listConversations(params),
    staleTime: STALE_TIMES.normal,
  });
}

export function useConversationDetail(id: string | undefined) {
  return useQuery({
    queryKey: id ? chatKeys.conversationDetail(id) : DISABLED_QUERY_KEY,
    queryFn: () => (id ? chatService.getConversation(id) : Promise.reject("No ID")),
    enabled: !!id,
    staleTime: STALE_TIMES.normal,
  });
}

export function useCreateConversation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: CreateConversationRequest) => chatService.createConversation(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: chatKeys.conversations() });
    },
  });
}

export function useUpdateConversation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: UpdateConversationRequest }) =>
      chatService.updateConversation(id, data),
    onSuccess: (_, { id }) => {
      queryClient.invalidateQueries({ queryKey: chatKeys.conversations() });
      queryClient.invalidateQueries({ queryKey: chatKeys.conversationDetail(id) });
    },
  });
}

export function useDeleteConversation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => chatService.deleteConversation(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: chatKeys.conversations() });
    },
  });
}

// --- Messages ---

export function useMessages(conversationId: string | undefined) {
  return useQuery({
    queryKey: conversationId ? chatKeys.messages(conversationId) : DISABLED_QUERY_KEY,
    queryFn: () => (conversationId ? chatService.getMessages(conversationId) : Promise.reject("No ID")),
    enabled: !!conversationId,
    staleTime: STALE_TIMES.static, // Messages arrive via SSE, not polling
  });
}

export function useSearchMessages(query: string) {
  return useQuery({
    queryKey: query ? chatKeys.search(query) : DISABLED_QUERY_KEY,
    queryFn: () => chatService.searchMessages(query),
    enabled: query.length > 0,
    staleTime: STALE_TIMES.normal,
  });
}

// --- Profile ---

export function useProfile() {
  return useQuery({
    queryKey: chatKeys.profile(),
    queryFn: () => chatService.getProfile(),
    staleTime: STALE_TIMES.static,
  });
}

export function useUpdateProfile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: Partial<UserProfile>) => chatService.updateProfile(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: chatKeys.profile() });
    },
  });
}

// --- Categories ---

export function useCategories() {
  return useQuery({
    queryKey: chatKeys.categories(),
    queryFn: () => chatService.listCategories(),
    staleTime: STALE_TIMES.rare,
  });
}

// --- Agent Health ---

export function useAgentHealth() {
  return useQuery({
    queryKey: chatKeys.agentHealth(),
    queryFn: () => chatService.checkAgentHealth(),
    staleTime: STALE_TIMES.frequent,
    refetchInterval: 30_000, // Check every 30s
  });
}
```

- [ ] **Step 2: Commit**

```bash
git add cortex-ui/src/features/chat/hooks/useChatQueries.ts
git commit -m "feat: add TanStack Query hooks for chat feature"
```

---

## Phase 5: Frontend UI Components

### Task 13: MessageBubble Component

**Files:**
- Create: `cortex-ui/src/features/chat/components/MessageBubble.tsx`

- [ ] **Step 1: Install Markdown dependencies**

```bash
cd cortex-ui && npm install rehype-highlight remark-gfm
```

- [ ] **Step 2: Create MessageBubble component**

Create `cortex-ui/src/features/chat/components/MessageBubble.tsx` with:
- ReactMarkdown for assistant messages with rehype-highlight and remark-gfm
- Code block copy-to-clipboard button
- User messages right-aligned with accent color
- Assistant messages left-aligned with glassmorphic card
- Tool use cards rendered inline (using ToolUseCard component — created in next task)
- Timestamps displayed subtly

Reference `cortex-ui/src/features/ui/primitives/styles.ts` for glassmorphism classes.

- [ ] **Step 3: Commit**

```bash
git add cortex-ui/src/features/chat/components/MessageBubble.tsx cortex-ui/package.json cortex-ui/package-lock.json
git commit -m "feat: add MessageBubble with Markdown rendering"
```

---

### Task 14: ToolUseCard and ActionRequestCard

**Files:**
- Create: `cortex-ui/src/features/chat/components/ToolUseCard.tsx`
- Create: `cortex-ui/src/features/chat/components/ActionRequestCard.tsx`

- [ ] **Step 1: Create ToolUseCard**

Collapsible card showing tool name, args, result summary, and duration. Uses Radix Collapsible primitive. Cyan border glow.

- [ ] **Step 2: Create ActionRequestCard**

Highlighted card with approve/deny buttons. Amber/orange glow. Calls `chatService.confirmAction()` or `chatService.denyAction()`.

- [ ] **Step 3: Commit**

```bash
git add cortex-ui/src/features/chat/components/ToolUseCard.tsx cortex-ui/src/features/chat/components/ActionRequestCard.tsx
git commit -m "feat: add ToolUseCard and ActionRequestCard components"
```

---

### Task 15: ChatInput Component

**Files:**
- Create: `cortex-ui/src/features/chat/components/ChatInput.tsx`
- Create: `cortex-ui/src/features/chat/components/ModelSelector.tsx`

- [ ] **Step 1: Create ModelSelector**

Dropdown chip showing current model. Click to open dropdown with available models (based on configured API keys). Grayed out models without configured keys.

- [ ] **Step 2: Create ChatInput**

Text area with:
- Shift+Enter for newline, Enter to send
- ModelSelector chip
- Action mode toggle (lock icon)
- Disabled state when agent service unavailable
- Loading state during streaming

- [ ] **Step 3: Commit**

```bash
git add cortex-ui/src/features/chat/components/ChatInput.tsx cortex-ui/src/features/chat/components/ModelSelector.tsx
git commit -m "feat: add ChatInput with model selector and action mode toggle"
```

---

### Task 16: MessageStream and SSE Hook

**Files:**
- Create: `cortex-ui/src/features/chat/hooks/useSSEStream.ts`
- Create: `cortex-ui/src/features/chat/components/MessageStream.tsx`

- [ ] **Step 1: Create useSSEStream hook**

Custom hook that wraps `chatService.streamMessage()`:
- Manages streaming state (content accumulation, tool calls, completion)
- Appends completed messages to TanStack Query cache
- Returns: `{ streamingMessage, isStreaming, sendMessage, cancelStream }`

- [ ] **Step 2: Create MessageStream**

Scrollable container rendering:
- Persisted messages from `useMessages()` query
- Current streaming message from `useSSEStream()` state
- Auto-scroll to bottom on new messages
- Loading skeleton while messages load

- [ ] **Step 3: Commit**

```bash
git add cortex-ui/src/features/chat/hooks/useSSEStream.ts cortex-ui/src/features/chat/components/MessageStream.tsx
git commit -m "feat: add SSE streaming hook and MessageStream component"
```

---

### Task 17: ConversationList Component

**Files:**
- Create: `cortex-ui/src/features/chat/components/ConversationList.tsx`

- [ ] **Step 1: Create ConversationList**

Left sidebar component for the full /chat page:
- Lists conversations sorted by `updated_at`
- Search input for filtering
- Filter tabs: All / Global / Project
- "New Chat" button
- Active conversation highlighted
- Each item shows: title, last message preview, relative time
- Delete button (trash icon, calls `useDeleteConversation`)

- [ ] **Step 2: Commit**

```bash
git add cortex-ui/src/features/chat/components/ConversationList.tsx
git commit -m "feat: add ConversationList sidebar component"
```

---

### Task 18: ChatSidebar (Floating Panel)

**Files:**
- Create: `cortex-ui/src/features/chat/components/ChatSidebar.tsx`
- Modify: `cortex-ui/src/components/layout/MainLayout.tsx`

- [ ] **Step 1: Create ChatSidebar**

Slide-in panel (400px, right side):
- Uses ChatInput and MessageStream internally
- "Expand" button to navigate to /chat page
- "New Chat" button
- Conversation switcher dropdown
- Close button (X)
- Agent health indicator

- [ ] **Step 2: Activate the floating button in MainLayout**

In `MainLayout.tsx`, replace the disabled button with:
- Remove `disabled` attribute
- Add `onClick` handler to toggle ChatSidebar visibility
- Change styling from grayed out to active neon glow
- Conditionally render `<ChatSidebar />` when open
- Dim the button when agent service is unavailable (using `useAgentHealth()`)

- [ ] **Step 3: Delete legacy CortexChatPanel**

Delete `cortex-ui/src/components/agent-chat/CortexChatPanel.tsx`.

- [ ] **Step 4: Commit**

```bash
git add cortex-ui/src/features/chat/components/ChatSidebar.tsx cortex-ui/src/components/layout/MainLayout.tsx
git rm cortex-ui/src/components/agent-chat/CortexChatPanel.tsx
git commit -m "feat: add ChatSidebar, activate floating button, delete legacy panel"
```

---

### Task 19: Full Chat Page

**Files:**
- Create: `cortex-ui/src/features/chat/components/ChatPage.tsx`
- Create: `cortex-ui/src/features/chat/components/ConversationContext.tsx`
- Create: `cortex-ui/src/features/chat/views/ChatView.tsx`
- Modify: `cortex-ui/src/App.tsx`

- [ ] **Step 1: Create ConversationContext**

Right panel (collapsible):
- Shows current project scope (if project-scoped)
- Action mode toggle with explanation
- Model selector (full dropdown, not just chip)
- Conversation metadata (created at, message count)

- [ ] **Step 2: Create ChatPage**

Three-column layout:
- Left: `<ConversationList />`
- Center: `<MessageStream />` + `<ChatInput />`
- Right: `<ConversationContext />` (collapsible)

- [ ] **Step 3: Create ChatView**

View orchestrator that manages conversation state (selected conversation, create new, etc.).

- [ ] **Step 4: Add /chat route to App.tsx**

In `cortex-ui/src/App.tsx`:
- Import ChatView
- Add route: `<Route path="/chat" element={<ChatView />} />`

Add navigation item in `Navigation.tsx` for the chat page.

- [ ] **Step 5: Commit**

```bash
git add cortex-ui/src/features/chat/components/ChatPage.tsx cortex-ui/src/features/chat/components/ConversationContext.tsx cortex-ui/src/features/chat/views/ChatView.tsx cortex-ui/src/App.tsx cortex-ui/src/components/layout/Navigation.tsx
git commit -m "feat: add full /chat page with three-column layout and routing"
```

---

## Phase 6: User Profile & Settings

### Task 20: Profile Settings Section

**Files:**
- Create: `cortex-ui/src/components/settings/ProfileSettings.tsx`
- Modify: `cortex-ui/src/pages/SettingsPage.tsx`

- [ ] **Step 1: Create ProfileSettings component**

Settings section with:
- Display name text input
- Bio text area
- Long-term goals: editable list (add/remove/reorder)
- Current priorities: editable list
- Preferences: key-value editor or simple text area
- Save button that calls `useUpdateProfile()`
- Shows onboarding status

- [ ] **Step 2: Add to SettingsPage**

Import and add `<ProfileSettings />` section in `SettingsPage.tsx`.

- [ ] **Step 3: Commit**

```bash
git add cortex-ui/src/components/settings/ProfileSettings.tsx cortex-ui/src/pages/SettingsPage.tsx
git commit -m "feat: add user profile settings section"
```

---

### Task 21: Onboarding Flow

**Files:**
- Create: `cortex-ui/src/features/chat/components/OnboardingFlow.tsx`

- [ ] **Step 1: Create OnboardingFlow**

Renders when `user_profile.onboarding_completed` is false:
- The ChatAgent handles the onboarding conversationally (via system prompt)
- This component just renders the first-time welcome state
- After the AI finishes onboarding, the profile is marked as complete
- Re-onboarding: detect `/onboarding` in user input and trigger re-onboarding system prompt

- [ ] **Step 2: Commit**

```bash
git add cortex-ui/src/features/chat/components/OnboardingFlow.tsx
git commit -m "feat: add onboarding flow component for first-time chat"
```

---

## Phase 7: Project Enrichment

### Task 22: Backend — Project Enrichment API

**Files:**
- Modify: `python/src/server/services/projects/project_service.py`
- Modify: `python/src/server/api_routes/projects_api.py`

- [ ] **Step 1: Update project service to handle enrichment fields**

In `project_service.py`, ensure `create_project()` and `update_project()` accept and persist `project_goals`, `project_relevance`, and `project_category`.

- [ ] **Step 2: Update project API route**

In `projects_api.py`, add the new fields to the `CreateProjectRequest` and `UpdateProjectRequest` Pydantic models.

- [ ] **Step 3: Commit**

```bash
git add python/src/server/services/projects/project_service.py python/src/server/api_routes/projects_api.py
git commit -m "feat: add project enrichment fields to project API"
```

---

### Task 23: Frontend — Project Enrichment UI

**Files:**
- Modify: `cortex-ui/src/features/projects/types/project.ts`
- Modify: `cortex-ui/src/features/projects/services/projectService.ts`
- Create: `cortex-ui/src/features/projects/components/ProjectAboutSection.tsx`

- [ ] **Step 1: Add enrichment fields to Project type**

Add `project_goals`, `project_relevance`, `project_category` to the `Project` interface.

- [ ] **Step 2: Update projectService**

Add methods for updating enrichment fields.

- [ ] **Step 3: Create ProjectAboutSection**

An "About" section on the project detail page:
- Project goals: editable list
- Project relevance: text area
- Project category: text input with autocomplete dropdown (using `useCategories()` from chat hooks)
- AI-suggested category pre-fill (calls chat service in background)

- [ ] **Step 4: Commit**

```bash
git add cortex-ui/src/features/projects/types/project.ts cortex-ui/src/features/projects/services/projectService.ts cortex-ui/src/features/projects/components/ProjectAboutSection.tsx
git commit -m "feat: add project enrichment UI (goals, relevance, category)"
```

---

## Phase 8: Advanced ChatAgent Tools

### Task 24: Prioritization Engine Tool

**Files:**
- Modify: `python/src/agents/chat_tools.py`
- Modify: `python/src/agents/chat_agent.py`

- [ ] **Step 1: Implement get_prioritization_context tool**

In `chat_tools.py`, add a function that:
1. Fetches all projects with goals, categories, task counts
2. Fetches recent session history for momentum analysis
3. Gets current time for effort matching
4. Returns a structured JSON summary of all 5 prioritization signals

- [ ] **Step 2: Register tool in ChatAgent**

Add `@agent.tool` decorator for `get_prioritization_context` in `chat_agent.py`.

- [ ] **Step 3: Commit**

```bash
git add python/src/agents/chat_tools.py python/src/agents/chat_agent.py
git commit -m "feat: add prioritization engine tool to ChatAgent"
```

---

### Task 25: Synergy Analysis Tool

**Files:**
- Modify: `python/src/agents/chat_tools.py`
- Modify: `python/src/agents/chat_agent.py`

- [ ] **Step 1: Implement analyze_project_synergies tool**

In `chat_tools.py`, add a function that:
1. Fetches all projects with descriptions, goals, categories, knowledge sources
2. Returns the data as structured JSON for the AI to reason about
3. The AI does the actual synergy analysis in its response (not computed)

- [ ] **Step 2: Register tool in ChatAgent**

- [ ] **Step 3: Commit**

```bash
git add python/src/agents/chat_tools.py python/src/agents/chat_agent.py
git commit -m "feat: add cross-project synergy analysis tool"
```

---

### Task 26: Action Mode Tools

**Files:**
- Modify: `python/src/agents/chat_tools.py`
- Modify: `python/src/agents/chat_agent.py`

- [ ] **Step 1: Implement action tools**

Add tools for: `create_task`, `update_task`, `create_document`, `update_project`, `trigger_knowledge_crawl`. Each tool:
- Checks `deps.action_mode` before executing
- Returns a confirmation prompt describing the action
- Uses MCPClient for the actual operation

- [ ] **Step 2: Register tools conditionally in ChatAgent**

Register action tools only when `action_mode` is enabled in the dependencies.

- [ ] **Step 3: Add action approval endpoint to agent server**

In `server.py`, add `POST /agents/chat/confirm-action` and `POST /agents/chat/deny-action` endpoints with in-memory pending action storage and 5-minute TTL.

- [ ] **Step 4: Commit**

```bash
git add python/src/agents/chat_tools.py python/src/agents/chat_agent.py python/src/agents/server.py
git commit -m "feat: add action mode tools with approval flow"
```

---

## Phase 9: Polish & Integration

### Task 27: Chat History Search UI

**Files:**
- Modify: `cortex-ui/src/features/chat/components/ConversationList.tsx`

- [ ] **Step 1: Add search functionality**

Enhance ConversationList with:
- Search input that calls `useSearchMessages()`
- Results displayed as message snippets with conversation context
- Click to navigate to the conversation and scroll to the message

- [ ] **Step 2: Commit**

```bash
git add cortex-ui/src/features/chat/components/ConversationList.tsx
git commit -m "feat: add chat history search to conversation list"
```

---

### Task 28: Model Configuration Settings

**Files:**
- Create: `cortex-ui/src/components/settings/ChatModelSettings.tsx`
- Modify: `cortex-ui/src/pages/SettingsPage.tsx`

- [ ] **Step 1: Create ChatModelSettings**

Settings section for configuring chat models:
- Shows available providers based on configured API keys (from existing credential system)
- Default model selector dropdown
- Provider-specific model name input
- Test connection button (optional — can reuse providers_api.py pattern from POC branch)

- [ ] **Step 2: Add to SettingsPage**

- [ ] **Step 3: Commit**

```bash
git add cortex-ui/src/components/settings/ChatModelSettings.tsx cortex-ui/src/pages/SettingsPage.tsx
git commit -m "feat: add chat model configuration settings section"
```

---

### Task 29: Context Window Management

**Files:**
- Modify: `python/src/agents/chat_agent.py`

- [ ] **Step 1: Implement context window truncation**

In the ChatAgent streaming endpoint:
- If conversation history exceeds 20 messages, take last 20 for the message_history
- Optionally use SynthesizerAgent to create a summary of older messages (can be deferred to a follow-up)
- Add summary as a system message at the start of the history

- [ ] **Step 2: Commit**

```bash
git add python/src/agents/chat_agent.py
git commit -m "feat: add context window management with message truncation"
```

---

### Task 30: Integration Testing & Cleanup

**Files:**
- Various — final verification

- [ ] **Step 1: Run all backend tests**

```bash
cd python && uv run pytest -v
```
Expected: All tests pass.

- [ ] **Step 2: Run frontend linting**

```bash
cd cortex-ui && npm run biome && npx tsc --noEmit
```
Expected: No errors.

- [ ] **Step 3: Manual E2E test**

1. Start backend: `docker compose --profile agents up -d`
2. Start frontend: `cd cortex-ui && npm run dev`
3. Open browser → Click floating chat button → Sidebar should open
4. Type a message → Should stream response with tool use visibility
5. Navigate to /chat → Full page should work
6. Create project-scoped conversation
7. Test onboarding flow (reset profile onboarding_completed to false)
8. Test action mode toggle

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "feat: Cortex Chat Interface — complete implementation"
```

---

## Propagation Steps

After implementation, to see changes on a running system:

| What changed | How to propagate |
|---|---|
| Database migrations | Run SQL in Supabase SQL editor |
| Backend Python (services, routes) | `docker compose restart cortex-server` |
| Agent Service (ChatAgent, streaming) | `docker compose restart cortex-agents` (or `--profile agents up -d`) |
| Frontend | Auto-reloads if `npm run dev` is running |
| New npm dependencies | `cd cortex-ui && npm install` |
| Vite proxy config | Restart `npm run dev` |
