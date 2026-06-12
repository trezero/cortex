"""
Unit tests for UserProfileService.
"""

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from src.server.services.chat.user_profile_service import SINGLETON_ID, UserProfileService


@pytest.fixture
def mock_supabase():
    """Mock Supabase client."""
    return MagicMock()


@pytest.fixture
def service(mock_supabase):
    """UserProfileService with mocked Supabase client."""
    return UserProfileService(supabase_client=mock_supabase)


def _make_profile(**kwargs):
    """Helper to build a profile dict."""
    return {
        "id": SINGLETON_ID,
        "display_name": kwargs.get("display_name", ""),
        "bio": kwargs.get("bio", ""),
        "long_term_goals": kwargs.get("long_term_goals", []),
        "current_priorities": kwargs.get("current_priorities", []),
        "preferences": kwargs.get("preferences", {}),
        "onboarding_completed": kwargs.get("onboarding_completed", False),
        "updated_at": datetime.now().isoformat(),
    }


class TestGetProfile:
    def test_returns_existing_profile(self, service, mock_supabase):
        profile = _make_profile(display_name="Alice")
        (
            mock_supabase.table.return_value
            .select.return_value
            .eq.return_value
            .execute.return_value.data
        ) = [profile]

        success, result = service.get_profile()

        assert success is True
        assert result["profile"]["display_name"] == "Alice"
        assert result["profile"]["id"] == SINGLETON_ID

    def test_creates_default_profile_when_missing(self, service, mock_supabase):
        """When no profile exists, should create and return a default one."""
        default_profile = _make_profile()

        table_mock = MagicMock()
        # select("*").eq("id", ...).execute().data = [] (profile not found)
        table_mock.select.return_value.eq.return_value.execute.return_value.data = []
        # upsert(...).execute().data = [default_profile]
        table_mock.upsert.return_value.execute.return_value.data = [default_profile]
        mock_supabase.table.return_value = table_mock

        success, result = service.get_profile()

        assert success is True
        assert result["profile"]["id"] == SINGLETON_ID
        # Verify upsert was called to create the default row
        table_mock.upsert.assert_called_once()

    def test_returns_error_on_exception(self, service, mock_supabase):
        mock_supabase.table.side_effect = Exception("DB error")

        success, result = service.get_profile()

        assert success is False
        assert "error" in result


class TestUpdateProfile:
    def test_upserts_with_singleton_id_and_refreshes_updated_at(self, service, mock_supabase):
        updated_profile = _make_profile(display_name="Bob", bio="Developer")
        mock_supabase.table.return_value.upsert.return_value.execute.return_value.data = [
            updated_profile
        ]

        success, result = service.update_profile(display_name="Bob", bio="Developer")

        assert success is True
        assert result["profile"]["display_name"] == "Bob"

        upsert_data = mock_supabase.table.return_value.upsert.call_args[0][0]
        assert upsert_data["id"] == SINGLETON_ID
        assert "updated_at" in upsert_data
        assert upsert_data["display_name"] == "Bob"
        assert upsert_data["bio"] == "Developer"

    def test_updates_onboarding_completed(self, service, mock_supabase):
        profile = _make_profile(onboarding_completed=True)
        mock_supabase.table.return_value.upsert.return_value.execute.return_value.data = [profile]

        success, result = service.update_profile(onboarding_completed=True)

        assert success is True
        upsert_data = mock_supabase.table.return_value.upsert.call_args[0][0]
        assert upsert_data["onboarding_completed"] is True

    def test_updates_structured_fields(self, service, mock_supabase):
        goals = ["Learn Rust", "Ship Cortex v2"]
        priorities = ["Fix bug #123"]
        profile = _make_profile(long_term_goals=goals, current_priorities=priorities)
        mock_supabase.table.return_value.upsert.return_value.execute.return_value.data = [profile]

        success, result = service.update_profile(
            long_term_goals=goals, current_priorities=priorities
        )

        assert success is True
        upsert_data = mock_supabase.table.return_value.upsert.call_args[0][0]
        assert upsert_data["long_term_goals"] == goals
        assert upsert_data["current_priorities"] == priorities

    def test_returns_error_when_database_returns_no_data(self, service, mock_supabase):
        mock_supabase.table.return_value.upsert.return_value.execute.return_value.data = []

        success, result = service.update_profile(display_name="X")

        assert success is False
        assert "error" in result

    def test_returns_error_on_exception(self, service, mock_supabase):
        mock_supabase.table.side_effect = Exception("DB connection lost")

        success, result = service.update_profile(display_name="X")

        assert success is False
        assert "error" in result


class TestEnsureDefaultProfile:
    def test_creates_default_profile_with_all_required_fields(self, service, mock_supabase):
        default_profile = _make_profile()
        mock_supabase.table.return_value.upsert.return_value.execute.return_value.data = [
            default_profile
        ]

        success, result = service._ensure_default_profile()

        assert success is True
        upsert_data = mock_supabase.table.return_value.upsert.call_args[0][0]
        assert upsert_data["id"] == SINGLETON_ID
        assert upsert_data["display_name"] == ""
        assert upsert_data["bio"] == ""
        assert upsert_data["long_term_goals"] == []
        assert upsert_data["current_priorities"] == []
        assert upsert_data["preferences"] == {}
        assert upsert_data["onboarding_completed"] is False
        assert "updated_at" in upsert_data

    def test_returns_error_when_upsert_returns_no_data(self, service, mock_supabase):
        mock_supabase.table.return_value.upsert.return_value.execute.return_value.data = []

        success, result = service._ensure_default_profile()

        assert success is False
        assert "error" in result

    def test_returns_error_on_exception(self, service, mock_supabase):
        mock_supabase.table.side_effect = Exception("DB error")

        success, result = service._ensure_default_profile()

        assert success is False
        assert "error" in result
