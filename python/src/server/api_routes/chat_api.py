"""
Chat API routes for Cortex

Handles:
- Conversation management (CRUD)
- Message persistence and retrieval
- Full-text message search
- User profile management
- Category listing
"""

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from ..config.logfire_config import get_logger
from ..services.chat import ChatMessageService, ChatService, UserProfileService

logger = get_logger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])


# ==================== REQUEST MODELS ====================


class CreateConversationRequest(BaseModel):
    title: str | None = Field(None, description="Optional conversation title")
    project_id: str | None = Field(None, description="Associated project ID")
    # model_config collides with Pydantic v2's reserved attribute; use alias
    model_config_data: dict[str, Any] | None = Field(
        None,
        alias="model_config",
        description="Model configuration (model name, temperature, etc.)",
    )

    model_config = ConfigDict(populate_by_name=True)


class UpdateConversationRequest(BaseModel):
    title: str | None = Field(None, description="Updated conversation title")
    model_config_data: dict[str, Any] | None = Field(
        None,
        alias="model_config",
        description="Updated model configuration",
    )
    action_mode: bool | None = Field(None, description="Whether action mode is enabled")

    model_config = ConfigDict(populate_by_name=True)


class SaveMessageRequest(BaseModel):
    role: str = Field(..., description="Message role: user, assistant, or tool")
    content: str = Field(..., description="Message content")
    tool_calls: list[Any] | None = Field(None, description="Tool calls made by the assistant")
    tool_results: list[Any] | None = Field(None, description="Results returned by tools")
    model_used: str | None = Field(None, description="Model identifier used for this message")
    token_count: int | None = Field(None, description="Token count for this message")


class UpdateProfileRequest(BaseModel):
    display_name: str | None = Field(None, description="User display name")
    bio: str | None = Field(None, description="Short bio")
    long_term_goals: list[Any] | None = Field(None, description="Long-term goals list")
    current_priorities: list[Any] | None = Field(None, description="Current priorities list")
    preferences: dict[str, Any] | None = Field(None, description="User preferences")
    onboarding_completed: bool | None = Field(None, description="Whether onboarding is complete")


# ==================== CONVERSATION ENDPOINTS ====================


@router.post("/conversations")
async def create_conversation(request: CreateConversationRequest):
    """Create a new chat conversation."""
    service = ChatService()

    kwargs: dict[str, Any] = {}
    if request.title is not None:
        kwargs["title"] = request.title
    if request.project_id is not None:
        kwargs["project_id"] = request.project_id
    if request.model_config_data is not None:
        kwargs["model_config"] = request.model_config_data

    success, result = service.create_conversation(**kwargs)
    if not success:
        raise HTTPException(status_code=500, detail=result.get("error", "Failed to create conversation"))
    return result


@router.get("/conversations")
async def list_conversations(
    project_id: str | None = Query(None, description="Filter by project ID"),
    conversation_type: str | None = Query(None, description="Filter by conversation type"),
):
    """List all non-deleted conversations, ordered by updated_at DESC."""
    service = ChatService()
    success, result = service.list_conversations(
        project_id=project_id,
        conversation_type=conversation_type,
    )
    if not success:
        raise HTTPException(status_code=500, detail=result.get("error", "Failed to list conversations"))
    return result


@router.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str):
    """Get a single conversation by ID."""
    service = ChatService()
    success, result = service.get_conversation(conversation_id)
    if not success:
        error = result.get("error", "")
        status_code = 404 if "not found" in error.lower() else 500
        raise HTTPException(status_code=status_code, detail=error)
    return result


@router.patch("/conversations/{conversation_id}")
async def update_conversation(conversation_id: str, request: UpdateConversationRequest):
    """Update a conversation's title, model config, or action mode."""
    service = ChatService()

    updates = request.model_dump(by_alias=True, exclude_none=True)
    # Rename model_config alias back to the actual DB field name
    if "model_config" in updates:
        updates["model_config"] = updates.pop("model_config")

    success, result = service.update_conversation(conversation_id, **updates)
    if not success:
        error = result.get("error", "")
        status_code = 404 if "not found" in error.lower() else 500
        raise HTTPException(status_code=status_code, detail=error)
    return result


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str):
    """Soft-delete a conversation."""
    service = ChatService()
    success, result = service.delete_conversation(conversation_id)
    if not success:
        error = result.get("error", "")
        status_code = 404 if "not found" in error.lower() else 500
        raise HTTPException(status_code=status_code, detail=error)
    return result


# ==================== MESSAGE ENDPOINTS ====================


@router.post("/conversations/{conversation_id}/messages")
async def save_message(conversation_id: str, request: SaveMessageRequest):
    """Persist a message to a conversation."""
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
        raise HTTPException(status_code=500, detail=result.get("error", "Failed to save message"))
    return result


@router.get("/conversations/{conversation_id}/messages")
async def get_messages(
    conversation_id: str,
    limit: int = Query(50, ge=1, le=200, description="Number of messages to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
):
    """Retrieve messages for a conversation, paginated and ordered ASC."""
    service = ChatMessageService()
    success, result = service.get_messages(
        conversation_id=conversation_id,
        limit=limit,
        offset=offset,
    )
    if not success:
        raise HTTPException(status_code=500, detail=result.get("error", "Failed to get messages"))
    return result


@router.get("/messages/search")
async def search_messages(
    q: str = Query(..., description="Search query"),
):
    """Full-text search across all chat messages."""
    service = ChatMessageService()
    success, result = service.search_messages(q)
    if not success:
        raise HTTPException(status_code=500, detail=result.get("error", "Search failed"))
    return result


# ==================== CATEGORIES ENDPOINT ====================


@router.get("/categories")
async def list_categories():
    """List distinct project categories for conversation filtering."""
    service = ChatService()
    success, result = service.list_categories()
    if not success:
        raise HTTPException(status_code=500, detail=result.get("error", "Failed to list categories"))
    return result


# ==================== USER PROFILE ENDPOINTS ====================


@router.get("/profile")
async def get_profile():
    """Get the singleton user profile, creating a default if missing."""
    service = UserProfileService()
    success, result = service.get_profile()
    if not success:
        raise HTTPException(status_code=500, detail=result.get("error", "Failed to get profile"))
    return result


@router.patch("/profile")
async def update_profile(request: UpdateProfileRequest):
    """Update the singleton user profile."""
    service = UserProfileService()
    updates = request.model_dump(exclude_none=True)
    success, result = service.update_profile(**updates)
    if not success:
        raise HTTPException(status_code=500, detail=result.get("error", "Failed to update profile"))
    return result
