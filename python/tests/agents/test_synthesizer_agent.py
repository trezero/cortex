"""Tests for the SynthesizerAgent — construction and model validation only.

These tests do NOT call the LLM; they verify that the dataclasses,
Pydantic models, and agent class can be instantiated correctly.
"""

import os

import pytest
from pydantic import ValidationError

from src.agents.synthesizer_agent import (
    ChunkData,
    SourceInfo,
    SynthesizedDocument,
    SynthesizerAgent,
    SynthesizerDeps,
)


@pytest.fixture(autouse=True)
def _set_dummy_api_key(monkeypatch):
    """Provide a dummy OpenAI API key so the Agent constructor doesn't raise."""
    if not os.getenv("OPENAI_API_KEY"):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-dummy-key-for-unit-tests")


# ---------------------------------------------------------------------------
# Dataclass / Pydantic model construction
# ---------------------------------------------------------------------------


class TestChunkData:
    def test_minimal(self):
        chunk = ChunkData(content="hello", source_id="src-1")
        assert chunk.content == "hello"
        assert chunk.source_id == "src-1"
        assert chunk.url is None
        assert chunk.title is None
        assert chunk.chunk_number is None

    def test_full(self):
        chunk = ChunkData(
            content="body", source_id="src-2", url="https://example.com", title="Doc", chunk_number=3
        )
        assert chunk.url == "https://example.com"
        assert chunk.title == "Doc"
        assert chunk.chunk_number == 3


class TestSourceInfo:
    def test_minimal(self):
        info = SourceInfo(source_id="s1", title="Title")
        assert info.source_id == "s1"
        assert info.url is None

    def test_with_url(self):
        info = SourceInfo(source_id="s2", title="T", url="https://x.com")
        assert info.url == "https://x.com"


class TestSynthesizerDeps:
    def test_defaults(self):
        deps = SynthesizerDeps()
        assert deps.topic == ""
        assert deps.chunks == []
        assert deps.source_metadata == []
        # Inherited from CortexDependencies
        assert deps.request_id is None

    def test_with_chunks_and_metadata(self):
        chunks = [ChunkData(content="c1", source_id="s1")]
        sources = [SourceInfo(source_id="s1", title="Source 1")]
        deps = SynthesizerDeps(topic="FastAPI auth", chunks=chunks, source_metadata=sources)
        assert deps.topic == "FastAPI auth"
        assert len(deps.chunks) == 1
        assert len(deps.source_metadata) == 1

    def test_independent_default_lists(self):
        """Ensure each instance gets its own list (no shared mutable default)."""
        a = SynthesizerDeps()
        b = SynthesizerDeps()
        a.chunks.append(ChunkData(content="x", source_id="y"))
        assert len(b.chunks) == 0


class TestSynthesizedDocument:
    def test_valid(self):
        doc = SynthesizedDocument(
            title="Auth Guide",
            content="# Auth Guide\n\nSome content.",
            summary="A guide to authentication.",
            source_urls=["https://docs.example.com/auth"],
            word_count=42,
        )
        assert doc.title == "Auth Guide"
        assert doc.word_count == 42
        assert len(doc.source_urls) == 1

    def test_empty_sources(self):
        doc = SynthesizedDocument(
            title="T", content="C", summary="S", source_urls=[], word_count=1
        )
        assert doc.source_urls == []

    def test_missing_required_field(self):
        with pytest.raises(ValidationError):
            SynthesizedDocument(title="T")  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# Agent construction (no LLM calls)
# ---------------------------------------------------------------------------


class TestSynthesizerAgentConstruction:
    def test_default_instantiation(self):
        agent = SynthesizerAgent()
        assert agent.name == "SynthesizerAgent"
        assert agent.model == "openai:gpt-4.1-nano"
        assert agent.retries == 3
        assert agent.enable_rate_limiting is True

    def test_custom_model(self):
        agent = SynthesizerAgent(model="openai:gpt-4o")
        assert agent.model == "openai:gpt-4o"
        assert agent.name == "SynthesizerAgent"

    def test_env_model_override(self, monkeypatch):
        monkeypatch.setenv("SYNTHESIZER_MODEL", "openai:gpt-4o-mini")
        agent = SynthesizerAgent()
        assert agent.model == "openai:gpt-4o-mini"

    def test_get_system_prompt(self):
        agent = SynthesizerAgent()
        prompt = agent.get_system_prompt()
        assert "technical documentation synthesizer" in prompt.lower()

    def test_underlying_pydantic_agent_exists(self):
        agent = SynthesizerAgent()
        assert agent.agent is not None
