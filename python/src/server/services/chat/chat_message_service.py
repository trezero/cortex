"""
Chat Message Service for Cortex

Handles persistence and retrieval of chat messages, including full-text search
via the search_chat_messages RPC function.
"""

from datetime import datetime
from typing import Any

from ...config.logfire_config import get_logger
from ...services.client_manager import get_supabase_client

logger = get_logger(__name__)


class ChatMessageService:
    """Service for managing chat messages."""

    def __init__(self, supabase_client=None):
        """Initialize with optional supabase client."""
        self.supabase_client = supabase_client or get_supabase_client()

    def save_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        tool_calls: list | None = None,
        tool_results: list | None = None,
        model_used: str | None = None,
        token_count: int | None = None,
    ) -> tuple[bool, dict[str, Any]]:
        """
        Insert a message into chat_messages and update the parent conversation's
        updated_at timestamp.

        Returns:
            Tuple of (success, result_dict)
        """
        try:
            message_data: dict[str, Any] = {
                "conversation_id": conversation_id,
                "role": role,
                "content": content,
                "created_at": datetime.now().isoformat(),
            }
            if tool_calls is not None:
                message_data["tool_calls"] = tool_calls
            if tool_results is not None:
                message_data["tool_results"] = tool_results
            if model_used is not None:
                message_data["model_used"] = model_used
            if token_count is not None:
                message_data["token_count"] = token_count

            response = self.supabase_client.table("chat_messages").insert(message_data).execute()

            if not response.data:
                logger.error("Supabase returned empty data for message insertion")
                return False, {"error": "Failed to save message - database returned no data"}

            message = response.data[0]

            # Update the conversation's updated_at to reflect recent activity
            try:
                self.supabase_client.table("chat_conversations").update(
                    {"updated_at": datetime.now().isoformat()}
                ).eq("id", conversation_id).execute()
            except Exception as e:
                logger.warning(f"Failed to update conversation updated_at for {conversation_id}: {e}")

            logger.info(f"Message saved for conversation {conversation_id}")
            return True, {"message": message}

        except Exception as e:
            logger.error(f"Error saving message: {e}")
            return False, {"error": f"Database error: {str(e)}"}

    def get_messages(
        self,
        conversation_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[bool, dict[str, Any]]:
        """
        Retrieve messages for a conversation, paginated and ordered by created_at ASC.

        Returns:
            Tuple of (success, result_dict)
        """
        try:
            response = (
                self.supabase_client.table("chat_messages")
                .select("*")
                .eq("conversation_id", conversation_id)
                .order("created_at", desc=False)
                .range(offset, offset + limit - 1)
                .execute()
            )

            messages = response.data or []
            return True, {"messages": messages, "total_count": len(messages)}

        except Exception as e:
            logger.error(f"Error getting messages for conversation {conversation_id}: {e}")
            return False, {"error": f"Error getting messages: {str(e)}"}

    def search_messages(self, query: str) -> tuple[bool, dict[str, Any]]:
        """
        Full-text search across chat messages using the search_chat_messages RPC function.

        Returns:
            Tuple of (success, result_dict)
        """
        try:
            response = self.supabase_client.rpc(
                "search_chat_messages", {"search_query": query}
            ).execute()

            results = response.data or []
            return True, {"results": results, "total_count": len(results)}

        except Exception as e:
            logger.error(f"Error searching messages with query '{query}': {e}")
            return False, {"error": f"Error searching messages: {str(e)}"}
