"""
Chat Conversation Service for Cortex

Provides CRUD operations for chat conversations including creation, listing,
retrieval, updating, and soft deletion.
"""

from datetime import datetime
from typing import Any

from ...config.logfire_config import get_logger
from ...services.client_manager import get_supabase_client

logger = get_logger(__name__)


class ChatService:
    """Service for managing chat conversations."""

    def __init__(self, supabase_client=None):
        """Initialize with optional supabase client."""
        self.supabase_client = supabase_client or get_supabase_client()

    def create_conversation(
        self,
        title: str | None = None,
        project_id: str | None = None,
        model_config: dict | None = None,
    ) -> tuple[bool, dict[str, Any]]:
        """
        Create a new conversation. Sets conversation_type to 'project' when
        project_id is provided, otherwise 'global'.

        Returns:
            Tuple of (success, result_dict)
        """
        try:
            conversation_type = "project" if project_id else "global"
            data: dict[str, Any] = {
                "conversation_type": conversation_type,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
            }
            if title is not None:
                data["title"] = title
            if project_id is not None:
                data["project_id"] = project_id
            if model_config is not None:
                data["model_config"] = model_config

            response = self.supabase_client.table("chat_conversations").insert(data).execute()

            if not response.data:
                logger.error("Supabase returned empty data for conversation creation")
                return False, {"error": "Failed to create conversation - database returned no data"}

            conversation = response.data[0]
            logger.info(f"Conversation created with ID: {conversation['id']}")
            return True, {"conversation": conversation}

        except Exception as e:
            logger.error(f"Error creating conversation: {e}")
            return False, {"error": f"Database error: {str(e)}"}

    def list_conversations(
        self,
        project_id: str | None = None,
        conversation_type: str | None = None,
    ) -> tuple[bool, dict[str, Any]]:
        """
        List conversations where deleted_at IS NULL, ordered by updated_at DESC.
        Optionally filter by project_id or conversation_type.

        Returns:
            Tuple of (success, result_dict)
        """
        try:
            query = (
                self.supabase_client.table("chat_conversations")
                .select("*")
                .is_("deleted_at", "null")
                .order("updated_at", desc=True)
            )

            if project_id is not None:
                query = query.eq("project_id", project_id)
            if conversation_type is not None:
                query = query.eq("conversation_type", conversation_type)

            response = query.execute()
            conversations = response.data or []
            return True, {"conversations": conversations, "total_count": len(conversations)}

        except Exception as e:
            logger.error(f"Error listing conversations: {e}")
            return False, {"error": f"Error listing conversations: {str(e)}"}

    def get_conversation(self, conversation_id: str) -> tuple[bool, dict[str, Any]]:
        """
        Get a single conversation by ID where deleted_at IS NULL.

        Returns:
            Tuple of (success, result_dict)
        """
        try:
            response = (
                self.supabase_client.table("chat_conversations")
                .select("*")
                .eq("id", conversation_id)
                .is_("deleted_at", "null")
                .execute()
            )

            if not response.data:
                return False, {"error": f"Conversation {conversation_id} not found"}

            return True, {"conversation": response.data[0]}

        except Exception as e:
            logger.error(f"Error getting conversation {conversation_id}: {e}")
            return False, {"error": f"Error getting conversation: {str(e)}"}

    def update_conversation(
        self, conversation_id: str, **updates: Any
    ) -> tuple[bool, dict[str, Any]]:
        """
        Update a conversation with the provided fields, always refreshing updated_at.

        Returns:
            Tuple of (success, result_dict)
        """
        try:
            update_data: dict[str, Any] = {"updated_at": datetime.now().isoformat()}
            update_data.update(updates)

            response = (
                self.supabase_client.table("chat_conversations")
                .update(update_data)
                .eq("id", conversation_id)
                .execute()
            )

            if not response.data:
                return False, {"error": f"Conversation {conversation_id} not found"}

            return True, {"conversation": response.data[0]}

        except Exception as e:
            logger.error(f"Error updating conversation {conversation_id}: {e}")
            return False, {"error": f"Error updating conversation: {str(e)}"}

    def list_categories(self) -> tuple[bool, dict[str, Any]]:
        """
        List distinct project categories from cortex_projects (non-null values only).

        Returns:
            Tuple of (success, result_dict)
        """
        try:
            response = (
                self.supabase_client.table("cortex_projects")
                .select("project_category")
                .not_.is_("project_category", "null")
                .execute()
            )

            seen: set[str] = set()
            categories: list[str] = []
            for row in response.data or []:
                cat = row.get("project_category")
                if cat and cat not in seen:
                    seen.add(cat)
                    categories.append(cat)

            return True, {"categories": categories}

        except Exception as e:
            logger.error(f"Error listing categories: {e}")
            return False, {"error": f"Error listing categories: {str(e)}"}

    def delete_conversation(self, conversation_id: str) -> tuple[bool, dict[str, Any]]:
        """
        Soft delete a conversation by setting deleted_at to the current timestamp.

        Returns:
            Tuple of (success, result_dict)
        """
        try:
            response = (
                self.supabase_client.table("chat_conversations")
                .update({"deleted_at": datetime.now().isoformat()})
                .eq("id", conversation_id)
                .execute()
            )

            if not response.data:
                return False, {"error": f"Conversation {conversation_id} not found"}

            return True, {"message": "Conversation deleted", "conversation_id": conversation_id}

        except Exception as e:
            logger.error(f"Error deleting conversation {conversation_id}: {e}")
            return False, {"error": f"Error deleting conversation: {str(e)}"}
