"""Tests for project_id filtering in KnowledgeSummaryService."""
import pytest
from unittest.mock import MagicMock


@pytest.fixture
def mock_supabase():
    """Create a mock Supabase client with chainable query builder."""
    client = MagicMock()
    return client


@pytest.fixture
def service(mock_supabase):
    """Create a KnowledgeSummaryService with mocked client."""
    from src.server.services.knowledge.knowledge_summary_service import KnowledgeSummaryService
    svc = KnowledgeSummaryService(mock_supabase)
    return svc


@pytest.mark.asyncio
async def test_get_summaries_with_project_id_filters_by_metadata(service, mock_supabase):
    """When project_id is provided, query should filter cortex_sources by metadata->>'project_id'."""
    # Setup mock chain for main query
    query_mock = MagicMock()
    query_mock.eq.return_value = query_mock
    query_mock.range.return_value = query_mock
    query_mock.order.return_value = query_mock
    query_mock.execute.return_value = MagicMock(data=[])

    # Setup mock chain for count query
    count_mock = MagicMock()
    count_mock.eq.return_value = count_mock
    count_mock.execute.return_value = MagicMock(count=0)

    mock_supabase.from_.return_value.select.side_effect = [query_mock, count_mock]

    project_id = "2d747998-7c66-46bb-82a9-74a6dcffd6c2"
    result = await service.get_summaries(project_id=project_id)

    # Verify the metadata filter was applied to both queries
    query_mock.eq.assert_called_with("metadata->>project_id", project_id)
    count_mock.eq.assert_called_with("metadata->>project_id", project_id)
    assert result["items"] == []
    assert result["total"] == 0


@pytest.mark.asyncio
async def test_get_summaries_without_project_id_returns_all(service, mock_supabase):
    """When project_id is None, no project filter should be applied."""
    query_mock = MagicMock()
    query_mock.range.return_value = query_mock
    query_mock.order.return_value = query_mock
    query_mock.execute.return_value = MagicMock(data=[])

    count_mock = MagicMock()
    count_mock.execute.return_value = MagicMock(count=0)

    mock_supabase.from_.return_value.select.side_effect = [query_mock, count_mock]

    result = await service.get_summaries()

    # eq should NOT have been called (no project filter)
    query_mock.eq.assert_not_called()
