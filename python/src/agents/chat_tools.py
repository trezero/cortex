"""ChatAgent tool implementations using MCPClient for data operations."""
from __future__ import annotations

import json
import logging
from typing import Any

from .mcp_client import get_mcp_client

logger = logging.getLogger(__name__)


def _to_json(result: Any) -> str:
    """Normalize an MCP result to a JSON string."""
    if isinstance(result, str):
        return result
    return json.dumps(result, default=str)


async def tool_search_knowledge_base(query: str, source_id: str | None = None, match_count: int = 5) -> str:
    """Search the knowledge base via RAG query."""
    client = await get_mcp_client()
    result = await client.perform_rag_query(query, source=source_id, match_count=match_count)
    return result  # perform_rag_query already returns a JSON string


async def tool_list_projects() -> str:
    """List all projects with their status, categories, and goals."""
    client = await get_mcp_client()
    result = await client.call_tool("find_projects")
    return _to_json(result)


async def tool_get_project_detail(project_id: str) -> str:
    """Get detailed information about a specific project."""
    client = await get_mcp_client()
    result = await client.call_tool("find_projects", project_id=project_id)
    return _to_json(result)


async def tool_list_tasks(project_id: str | None = None, status: str | None = None) -> str:
    """List tasks, optionally filtered by project or status."""
    client = await get_mcp_client()
    kwargs: dict[str, Any] = {}
    if project_id:
        kwargs["filter_by"] = "project"
        kwargs["filter_value"] = project_id
    elif status:
        kwargs["filter_by"] = "status"
        kwargs["filter_value"] = status
    result = await client.call_tool("find_tasks", **kwargs)
    return _to_json(result)


async def tool_get_task_detail(task_id: str) -> str:
    """Get detailed information about a specific task."""
    client = await get_mcp_client()
    result = await client.call_tool("find_tasks", task_id=task_id)
    return _to_json(result)


async def tool_list_documents(project_id: str) -> str:
    """List documents for a specific project."""
    client = await get_mcp_client()
    result = await client.call_tool("find_documents", project_id=project_id)
    return _to_json(result)


async def tool_get_session_history(query: str | None = None) -> str:
    """Search recent session history across machines."""
    client = await get_mcp_client()
    if query:
        result = await client.call_tool("cortex_search_sessions", query=query)
    else:
        result = await client.call_tool("cortex_search_sessions")
    return _to_json(result)


async def tool_search_code_examples(query: str) -> str:
    """Search for code examples in the knowledge base."""
    client = await get_mcp_client()
    result = await client.search_code_examples(query)
    return result  # search_code_examples already returns a JSON string


async def tool_suggest_project_category(
    project_name: str, description: str, existing_categories: list[str]
) -> str:
    """Returns context for the AI to suggest a category for the project."""
    return json.dumps({
        "project_name": project_name,
        "description": description,
        "existing_categories": existing_categories,
        "instruction": "Based on the project name, description, and existing categories, suggest the most appropriate category.",
    })


async def tool_get_prioritization_context() -> str:
    """Fetch all projects and recent sessions to build prioritization context.

    Returns structured JSON with project summaries, activity data, and current
    time so the AI can reason about what to work on next.
    """
    from datetime import datetime, timezone

    client = await get_mcp_client()

    projects_result = await client.call_tool("find_projects")
    sessions_result = await client.call_tool("cortex_search_sessions")

    # Fetch in-progress and todo tasks for urgency context
    doing_tasks = await client.call_tool("find_tasks", filter_by="status", filter_value="doing")
    todo_tasks = await client.call_tool("find_tasks", filter_by="status", filter_value="todo")

    return json.dumps({
        "projects": projects_result if isinstance(projects_result, (list, dict)) else json.loads(projects_result),
        "recent_sessions": (
            sessions_result if isinstance(sessions_result, (list, dict)) else json.loads(sessions_result)
        ),
        "tasks_in_progress": doing_tasks if isinstance(doing_tasks, (list, dict)) else json.loads(doing_tasks),
        "tasks_todo": todo_tasks if isinstance(todo_tasks, (list, dict)) else json.loads(todo_tasks),
        "current_time": datetime.now(timezone.utc).isoformat(),
        "instruction": (
            "Analyze the projects, their goals/categories/relevance, recent session activity, "
            "and current task status to recommend what the user should focus on next. "
            "Consider deadlines, momentum, and strategic alignment."
        ),
    }, default=str)


async def tool_analyze_project_synergies() -> str:
    """Fetch all projects with descriptions, goals, and categories for synergy analysis.

    Returns the data so the AI can reason about connections, shared dependencies,
    overlapping goals, and potential consolidation opportunities.
    """
    client = await get_mcp_client()
    projects_result = await client.call_tool("find_projects")

    return json.dumps({
        "projects": projects_result if isinstance(projects_result, (list, dict)) else json.loads(projects_result),
        "instruction": (
            "Analyze the projects to identify synergies: shared technologies, overlapping goals, "
            "potential code reuse, dependency relationships, and consolidation opportunities. "
            "Highlight connections the user might not have noticed."
        ),
    }, default=str)


async def tool_create_task(project_id: str, title: str, description: str = "") -> str:
    """Create a new task in a project via MCPClient."""
    client = await get_mcp_client()
    kwargs: dict[str, Any] = {
        "action": "create",
        "project_id": project_id,
        "title": title,
    }
    if description:
        kwargs["description"] = description
    result = await client.call_tool("manage_task", **kwargs)
    return _to_json(result)


async def tool_update_task(
    task_id: str, status: str | None = None, title: str | None = None
) -> str:
    """Update an existing task via MCPClient."""
    client = await get_mcp_client()
    kwargs: dict[str, Any] = {
        "action": "update",
        "task_id": task_id,
    }
    if status:
        kwargs["status"] = status
    if title:
        kwargs["title"] = title
    result = await client.call_tool("manage_task", **kwargs)
    return _to_json(result)


async def tool_create_document(project_id: str, title: str, content: str) -> str:
    """Create a new document in a project via MCPClient."""
    client = await get_mcp_client()
    result = await client.call_tool(
        "manage_document",
        action="create",
        project_id=project_id,
        title=title,
        content=content,
    )
    return _to_json(result)
