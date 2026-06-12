"""Tests for _resolve_project_source_filter with junction table, caching, and cascading search."""
import pytest
from unittest.mock import MagicMock, patch, call


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear source cache before each test."""
    from src.server.utils.source_cache import invalidate_source_cache
    invalidate_source_cache()
    yield
    invalidate_source_cache()


@patch("src.server.api_routes.knowledge_api.get_supabase_client")
def test_returns_existing_source_unchanged(mock_get_client):
    """When existing_source is provided, return it without querying."""
    from src.server.api_routes.knowledge_api import _resolve_project_source_filter

    result = _resolve_project_source_filter(
        project_id="some-project-id",
        existing_source="src_abc,src_def",
    )
    assert result == "src_abc,src_def"
    mock_get_client.assert_not_called()


@patch("src.server.api_routes.knowledge_api.get_supabase_client")
def test_returns_none_when_no_project_id(mock_get_client):
    """When project_id is None, return None."""
    from src.server.api_routes.knowledge_api import _resolve_project_source_filter

    result = _resolve_project_source_filter(project_id=None, existing_source=None)
    assert result is None
    mock_get_client.assert_not_called()


def _make_mock_client(junction_data, project_data=None, parent_junction_data=None):
    """Helper to build a mock supabase client with configurable responses.

    Args:
        junction_data: data returned for the project's junction table query
        project_data: data returned for the project's parent_project_id lookup
        parent_junction_data: data returned for the parent's junction table query
    """
    mock_client = MagicMock()

    # Track call order to return different results for sequential table() calls
    call_count = {"n": 0}
    responses = []

    # First call: junction table for project
    responses.append(("cortex_project_sources", junction_data))
    # If include_parent, second call: cortex_projects for parent lookup
    if project_data is not None:
        responses.append(("cortex_projects", project_data))
    # If parent has sources, third call: junction table for parent
    if parent_junction_data is not None:
        responses.append(("cortex_project_sources", parent_junction_data))

    def table_side_effect(table_name):
        idx = call_count["n"]
        call_count["n"] += 1

        mock_table = MagicMock()
        mock_select = MagicMock()
        mock_eq = MagicMock()

        mock_table.select.return_value = mock_select
        mock_select.eq.return_value = mock_eq

        if idx < len(responses):
            _, data = responses[idx]
            if table_name == "cortex_projects":
                # maybe_single() chain
                mock_maybe = MagicMock()
                mock_eq.maybe_single.return_value = mock_maybe
                mock_maybe.execute.return_value = MagicMock(data=data)
            else:
                mock_eq.execute.return_value = MagicMock(data=data)
        else:
            mock_eq.execute.return_value = MagicMock(data=[])

        return mock_table

    mock_client.table.side_effect = table_side_effect
    return mock_client


@patch("src.server.api_routes.knowledge_api.get_supabase_client")
def test_queries_junction_table(mock_get_client):
    """Should query cortex_project_sources for project sources."""
    from src.server.api_routes.knowledge_api import _resolve_project_source_filter

    mock_client = _make_mock_client(
        junction_data=[{"source_id": "src_001"}, {"source_id": "src_002"}],
        project_data={"parent_project_id": None},
    )
    mock_get_client.return_value = mock_client

    project_id = "2d747998-7c66-46bb-82a9-74a6dcffd6c2"
    result = _resolve_project_source_filter(project_id=project_id, existing_source=None)

    assert result == "src_001,src_002"


@patch("src.server.api_routes.knowledge_api.get_supabase_client")
def test_returns_sentinel_when_no_junction_entries(mock_get_client):
    """When project has no junction table entries, return sentinel to prevent unfiltered search."""
    from src.server.api_routes.knowledge_api import _resolve_project_source_filter

    mock_client = _make_mock_client(
        junction_data=[],
        project_data={"parent_project_id": None},
    )
    mock_get_client.return_value = mock_client

    result = _resolve_project_source_filter(project_id="some-id", existing_source=None)
    # Should NOT return None (which would cause unfiltered search across all sources)
    assert result is not None
    assert result == "__no_linked_sources__"


@patch("src.server.api_routes.knowledge_api.get_supabase_client")
def test_cache_hit_with_empty_sources_returns_sentinel(mock_get_client):
    """When cache holds empty list for a project, return sentinel (not None)."""
    from src.server.api_routes.knowledge_api import _resolve_project_source_filter
    from src.server.utils.source_cache import set_cached_project_sources

    project_id = "empty-cached-project"
    # Simulate a cached empty result
    set_cached_project_sources(project_id, True, [])

    result = _resolve_project_source_filter(project_id=project_id, existing_source=None)
    assert result is not None
    assert result == "__no_linked_sources__"
    mock_get_client.assert_not_called()


@patch("src.server.api_routes.knowledge_api.get_supabase_client")
def test_handles_db_error_gracefully(mock_get_client):
    """On database error, log warning and return existing_source."""
    from src.server.api_routes.knowledge_api import _resolve_project_source_filter

    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_client.table.side_effect = Exception("DB connection failed")

    result = _resolve_project_source_filter(project_id="some-id", existing_source=None)
    assert result is None


@patch("src.server.api_routes.knowledge_api.get_supabase_client")
def test_cascading_search_includes_parent_sources(mock_get_client):
    """When include_parent=True and project has a parent, include parent's sources."""
    from src.server.api_routes.knowledge_api import _resolve_project_source_filter

    parent_id = "parent-uuid"
    mock_client = _make_mock_client(
        junction_data=[{"source_id": "child_src"}],
        project_data={"parent_project_id": parent_id},
        parent_junction_data=[{"source_id": "parent_src"}],
    )
    mock_get_client.return_value = mock_client

    result = _resolve_project_source_filter(
        project_id="child-uuid", existing_source=None, include_parent=True
    )

    assert "child_src" in result
    assert "parent_src" in result


@patch("src.server.api_routes.knowledge_api.get_supabase_client")
def test_include_parent_false_skips_parent(mock_get_client):
    """When include_parent=False, only project's own sources are returned."""
    from src.server.api_routes.knowledge_api import _resolve_project_source_filter

    mock_client = _make_mock_client(
        junction_data=[{"source_id": "child_src"}],
        # No project_data or parent_junction_data needed since include_parent=False
    )
    mock_get_client.return_value = mock_client

    result = _resolve_project_source_filter(
        project_id="child-uuid", existing_source=None, include_parent=False
    )

    assert result == "child_src"


@patch("src.server.api_routes.knowledge_api.get_supabase_client")
def test_cache_hit_avoids_db_query(mock_get_client):
    """Second call with same args should use cache and not query DB again."""
    from src.server.api_routes.knowledge_api import _resolve_project_source_filter

    mock_client = _make_mock_client(
        junction_data=[{"source_id": "src_001"}],
        project_data={"parent_project_id": None},
    )
    mock_get_client.return_value = mock_client

    project_id = "cached-project-id"

    # First call — populates cache
    result1 = _resolve_project_source_filter(project_id=project_id, existing_source=None)
    assert result1 == "src_001"
    first_call_count = mock_client.table.call_count

    # Second call — should hit cache
    result2 = _resolve_project_source_filter(project_id=project_id, existing_source=None)
    assert result2 == "src_001"
    assert mock_client.table.call_count == first_call_count  # No additional DB calls


@patch("src.server.api_routes.knowledge_api.get_supabase_client")
def test_cache_invalidation_forces_fresh_query(mock_get_client):
    """After invalidating cache, next call should query DB again."""
    from src.server.api_routes.knowledge_api import _resolve_project_source_filter
    from src.server.utils.source_cache import invalidate_source_cache

    mock_client = _make_mock_client(
        junction_data=[{"source_id": "src_001"}],
        project_data={"parent_project_id": None},
    )
    mock_get_client.return_value = mock_client

    project_id = "invalidated-project-id"

    # First call
    _resolve_project_source_filter(project_id=project_id, existing_source=None)
    first_call_count = mock_client.table.call_count

    # Invalidate
    invalidate_source_cache(project_id)

    # Need a fresh mock since the call_count tracker is exhausted
    mock_client2 = _make_mock_client(
        junction_data=[{"source_id": "src_002"}],
        project_data={"parent_project_id": None},
    )
    mock_get_client.return_value = mock_client2

    # Second call — should query DB again
    result = _resolve_project_source_filter(project_id=project_id, existing_source=None)
    assert result == "src_002"
    assert mock_client2.table.call_count > 0
