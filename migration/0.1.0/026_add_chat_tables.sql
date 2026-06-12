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
