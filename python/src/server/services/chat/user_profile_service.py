"""
User Profile Service for Cortex

Manages the singleton user profile row used to personalize chat and AI interactions.
The profile is always at id=1; it is created on first access if missing.
"""

from datetime import datetime
from typing import Any

from ...config.logfire_config import get_logger
from ...services.client_manager import get_supabase_client

logger = get_logger(__name__)

SINGLETON_ID = 1


class UserProfileService:
    """Service for managing the singleton user profile."""

    def __init__(self, supabase_client=None):
        """Initialize with optional supabase client."""
        self.supabase_client = supabase_client or get_supabase_client()

    def get_profile(self) -> tuple[bool, dict[str, Any]]:
        """
        Retrieve the singleton user profile, creating a default row if one does
        not yet exist.

        Returns:
            Tuple of (success, result_dict)
        """
        try:
            response = (
                self.supabase_client.table("user_profile")
                .select("*")
                .eq("id", SINGLETON_ID)
                .execute()
            )

            if response.data:
                return True, {"profile": response.data[0]}

            # Profile missing — create the default row
            return self._ensure_default_profile()

        except Exception as e:
            logger.error(f"Error getting user profile: {e}")
            return False, {"error": f"Error getting user profile: {str(e)}"}

    def update_profile(self, **fields: Any) -> tuple[bool, dict[str, Any]]:
        """
        Update (upsert) the singleton profile with the provided fields.
        Always refreshes updated_at.

        Returns:
            Tuple of (success, result_dict)
        """
        try:
            upsert_data: dict[str, Any] = {
                "id": SINGLETON_ID,
                "updated_at": datetime.now().isoformat(),
            }
            upsert_data.update(fields)

            response = (
                self.supabase_client.table("user_profile")
                .upsert(upsert_data)
                .execute()
            )

            if not response.data:
                return False, {"error": "Failed to update profile - database returned no data"}

            return True, {"profile": response.data[0]}

        except Exception as e:
            logger.error(f"Error updating user profile: {e}")
            return False, {"error": f"Error updating user profile: {str(e)}"}

    def _ensure_default_profile(self) -> tuple[bool, dict[str, Any]]:
        """
        Create the default singleton profile row via upsert so concurrent calls
        are idempotent.

        Returns:
            Tuple of (success, result_dict)
        """
        try:
            default_data: dict[str, Any] = {
                "id": SINGLETON_ID,
                "display_name": "",
                "bio": "",
                "long_term_goals": [],
                "current_priorities": [],
                "preferences": {},
                "onboarding_completed": False,
                "updated_at": datetime.now().isoformat(),
            }

            response = (
                self.supabase_client.table("user_profile")
                .upsert(default_data)
                .execute()
            )

            if not response.data:
                return False, {"error": "Failed to create default profile"}

            logger.info("Default user profile created")
            return True, {"profile": response.data[0]}

        except Exception as e:
            logger.error(f"Error creating default user profile: {e}")
            return False, {"error": f"Error creating default profile: {str(e)}"}
