"""Tests for MaterializationService.materialize() orchestration pipeline."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.server.models.materialization import MaterializationRecord
from src.server.services.knowledge.materialization_service import MaterializationService


def _make_supabase_mock():
    """Create a mock Supabase client with chainable table builder."""
    client = MagicMock()

    def _table(name):
        builder = MagicMock(name=f"table({name})")
        for method in ("select", "insert", "update", "delete"):
            getattr(builder, method).return_value = builder
        builder.eq.return_value = builder
        builder.in_.return_value = builder
        builder.order.return_value = builder
        builder.execute.return_value = MagicMock(data=[])
        return builder

    client.table.side_effect = _table
    return client


@pytest.fixture
def mock_supabase():
    return _make_supabase_mock()


@pytest.fixture
def service(mock_supabase):
    return MaterializationService(supabase_client=mock_supabase)


NOW = datetime.now(UTC).isoformat()

EXISTING_RECORD = MaterializationRecord(
    id="mat-existing",
    project_id="proj-1",
    project_path="/home/user/project",
    topic="React hooks",
    filename="react-hooks.md",
    file_path=".cortex/knowledge/react-hooks.md",
    source_ids=["src-1"],
    original_urls=["https://react.dev/hooks"],
    synthesis_model="openai:gpt-4.1-nano",
    word_count=1500,
    status="active",
    access_count=3,
    last_accessed_at=NOW,
    materialized_at=NOW,
    updated_at=NOW,
    metadata={},
)


# ── test: skip when already exists ─────────────────────────────


@pytest.mark.asyncio
async def test_materialize_skips_when_already_exists(service):
    """When check_existing returns a record, return it directly after marking accessed."""
    service.check_existing = AsyncMock(return_value=EXISTING_RECORD)
    service.mark_accessed = AsyncMock()

    result = await service.materialize(
        topic="React hooks",
        project_id="proj-1",
        project_path="/home/user/project",
    )

    assert result.success is True
    assert result.file_path == EXISTING_RECORD.file_path
    assert result.filename == EXISTING_RECORD.filename
    assert result.word_count == EXISTING_RECORD.word_count
    assert result.materialization_id == EXISTING_RECORD.id

    service.check_existing.assert_awaited_once_with("react hooks", "proj-1")
    service.mark_accessed.assert_awaited_once_with("mat-existing")


# ── test: no content when RAG returns empty ────────────────────


@pytest.mark.asyncio
async def test_materialize_returns_no_content_when_search_empty(service):
    """When RAG search returns no results, return failure and clean up pending record."""
    service.check_existing = AsyncMock(return_value=None)
    service.create_record = AsyncMock(return_value="pending-id")
    service.update_status = AsyncMock()
    service.delete_record = AsyncMock()

    mock_rag = MagicMock()
    mock_rag.search_documents = AsyncMock(return_value=[])

    with patch(
        "src.server.services.knowledge.materialization_service.RAGService",
        return_value=mock_rag,
    ):
        result = await service.materialize(
            topic="Nonexistent topic",
            project_id="proj-1",
            project_path="/home/user/project",
        )

    assert result.success is False
    assert result.reason == "no_relevant_content"

    service.create_record.assert_awaited_once()
    service.update_status.assert_awaited_once_with("pending-id", "pending")
    service.delete_record.assert_awaited_once_with("pending-id")


# ── test: filters short chunks ─────────────────────────────────


@pytest.mark.asyncio
async def test_materialize_filters_short_chunks(service):
    """When all RAG results have content under 50 chars, return no_relevant_content."""
    service.check_existing = AsyncMock(return_value=None)
    service.create_record = AsyncMock(return_value="pending-id")
    service.update_status = AsyncMock()
    service.delete_record = AsyncMock()

    short_results = [
        {"content": "Too short", "source_id": "s1", "url": "https://example.com", "title": "Ex"},
        {"content": "Also tiny", "source_id": "s2", "url": "https://example.com/2", "title": "Ex2"},
        {"content": "  ab  ", "source_id": "s3"},
    ]

    mock_rag = MagicMock()
    mock_rag.search_documents = AsyncMock(return_value=short_results)

    with patch(
        "src.server.services.knowledge.materialization_service.RAGService",
        return_value=mock_rag,
    ):
        result = await service.materialize(
            topic="Short content topic",
            project_id="proj-1",
            project_path="/home/user/project",
        )

    assert result.success is False
    assert result.reason == "no_relevant_content"
    service.delete_record.assert_awaited_once_with("pending-id")


# ── test: successful full pipeline ─────────────────────────────


@pytest.mark.asyncio
async def test_materialize_full_pipeline_success(service, mock_supabase):
    """Full pipeline: RAG search -> synthesis -> write -> finalize DB record."""
    service.check_existing = AsyncMock(return_value=None)
    service.create_record = AsyncMock(return_value="pending-id")
    service.update_status = AsyncMock()

    rag_results = [
        {
            "content": "A" * 100,
            "source_id": "src-1",
            "url": "https://example.com/doc1",
            "title": "Doc 1",
        },
        {
            "content": "B" * 80,
            "source_id": "src-2",
            "url": "https://example.com/doc2",
            "title": "Doc 2",
        },
    ]

    mock_rag = MagicMock()
    mock_rag.search_documents = AsyncMock(return_value=rag_results)

    mock_synthesized = MagicMock()
    mock_synthesized.source_urls = ["https://example.com/doc1", "https://example.com/doc2"]
    mock_synthesized.content = "# Synthesized Document\n\nContent here."
    mock_synthesized.summary = "A summary of the topic."
    mock_synthesized.word_count = 250

    mock_synthesizer = MagicMock()
    mock_synthesizer.model = "openai:gpt-4.1-nano"
    mock_synthesizer.synthesize = AsyncMock(return_value=mock_synthesized)

    mock_indexer = MagicMock()
    mock_indexer.generate_unique_filename.return_value = "test-topic.md"
    mock_indexer.write_materialized_file = AsyncMock()
    mock_indexer.update_index = AsyncMock()
    service.indexer = mock_indexer

    # Re-create table mock to capture the finalize update call
    table_builder = MagicMock()
    table_builder.update.return_value = table_builder
    table_builder.eq.return_value = table_builder
    table_builder.execute.return_value = MagicMock(data=[])
    mock_supabase.table.side_effect = None
    mock_supabase.table.return_value = table_builder

    with (
        patch(
            "src.server.services.knowledge.materialization_service.RAGService",
            return_value=mock_rag,
        ),
        patch(
            "src.agents.synthesizer_agent.SynthesizerAgent",
            return_value=mock_synthesizer,
        ),
    ):
        result = await service.materialize(
            topic="Test topic",
            project_id="proj-1",
            project_path="/home/user/project",
        )

    assert result.success is True
    assert result.file_path == ".cortex/knowledge/test-topic.md"
    assert result.filename == "test-topic.md"
    assert result.word_count == 250
    assert result.summary == "A summary of the topic."
    assert result.materialization_id == "pending-id"

    mock_indexer.generate_unique_filename.assert_called_once_with("/home/user/project", "test topic")
    mock_indexer.write_materialized_file.assert_awaited_once()
    mock_indexer.update_index.assert_awaited_once_with("/home/user/project")

    # Verify the finalize update was called on the table
    mock_supabase.table.assert_called_with("cortex_materialization_history")
    table_builder.update.assert_called_once()
    update_payload = table_builder.update.call_args[0][0]
    assert update_payload["status"] == "active"
    assert update_payload["filename"] == "test-topic.md"
    assert update_payload["word_count"] == 250


# ── test: synthesis error cleans up ────────────────────────────


@pytest.mark.asyncio
async def test_materialize_error_cleans_up_pending(service):
    """When synthesis raises an exception, pending record is deleted and failure returned."""
    service.check_existing = AsyncMock(return_value=None)
    service.create_record = AsyncMock(return_value="pending-id")
    service.update_status = AsyncMock()
    service.delete_record = AsyncMock()

    rag_results = [
        {"content": "X" * 100, "source_id": "src-1", "url": "https://example.com", "title": "T"},
    ]

    mock_rag = MagicMock()
    mock_rag.search_documents = AsyncMock(return_value=rag_results)

    mock_synthesizer = MagicMock()
    mock_synthesizer.model = "openai:gpt-4.1-nano"
    mock_synthesizer.synthesize = AsyncMock(side_effect=RuntimeError("LLM API timeout"))

    with (
        patch(
            "src.server.services.knowledge.materialization_service.RAGService",
            return_value=mock_rag,
        ),
        patch(
            "src.agents.synthesizer_agent.SynthesizerAgent",
            return_value=mock_synthesizer,
        ),
    ):
        result = await service.materialize(
            topic="Failing topic",
            project_id="proj-1",
            project_path="/home/user/project",
        )

    assert result.success is False
    assert "LLM API timeout" in result.reason
    service.delete_record.assert_awaited_once_with("pending-id")


# ── test: progress tracker updates ─────────────────────────────


@pytest.mark.asyncio
async def test_materialize_updates_progress_tracker(service, mock_supabase):
    """When progress_id is provided, ProgressTracker.state is updated at each step."""
    service.check_existing = AsyncMock(return_value=None)
    service.create_record = AsyncMock(return_value="pending-id")
    service.update_status = AsyncMock()

    rag_results = [
        {"content": "C" * 100, "source_id": "src-1", "url": "https://example.com", "title": "T"},
    ]

    mock_rag = MagicMock()
    mock_rag.search_documents = AsyncMock(return_value=rag_results)

    mock_synthesized = MagicMock()
    mock_synthesized.source_urls = ["https://example.com"]
    mock_synthesized.content = "# Doc\n\nContent."
    mock_synthesized.summary = "Summary."
    mock_synthesized.word_count = 100

    mock_synthesizer = MagicMock()
    mock_synthesizer.model = "openai:gpt-4.1-nano"
    mock_synthesizer.synthesize = AsyncMock(return_value=mock_synthesized)

    mock_indexer = MagicMock()
    mock_indexer.generate_unique_filename.return_value = "topic.md"
    mock_indexer.write_materialized_file = AsyncMock()
    mock_indexer.update_index = AsyncMock()
    service.indexer = mock_indexer

    table_builder = MagicMock()
    table_builder.update.return_value = table_builder
    table_builder.eq.return_value = table_builder
    table_builder.execute.return_value = MagicMock(data=[])
    mock_supabase.table.side_effect = None
    mock_supabase.table.return_value = table_builder

    mock_tracker = MagicMock()
    mock_tracker.state = {}

    with (
        patch(
            "src.server.services.knowledge.materialization_service.RAGService",
            return_value=mock_rag,
        ),
        patch(
            "src.agents.synthesizer_agent.SynthesizerAgent",
            return_value=mock_synthesizer,
        ),
        patch(
            "src.server.services.knowledge.materialization_service.ProgressTracker",
            return_value=mock_tracker,
        ) as mock_tracker_cls,
    ):
        result = await service.materialize(
            topic="Tracked topic",
            project_id="proj-1",
            project_path="/home/user/project",
            progress_id="prog-123",
        )

    assert result.success is True
    mock_tracker_cls.assert_called_once_with("prog-123", "materialization")
    # Final state should be completed
    assert mock_tracker.state.get("status") == "completed"
    assert mock_tracker.state.get("progress") == 100
