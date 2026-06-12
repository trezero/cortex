"""ChatAgent — the AI brain for the Cortex chat interface."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from pydantic_ai import Agent, RunContext

from .base_agent import CortexDependencies
from .mcp_client import get_mcp_client

logger = logging.getLogger(__name__)


@dataclass
class ChatDependencies(CortexDependencies):
    """Dependencies injected per chat request."""

    conversation_id: str = ""
    project_id: str | None = None
    user_profile: dict[str, Any] = field(default_factory=dict)
    action_mode: bool = False
    model_override: str | None = None
    conversation_history: list[dict[str, Any]] = field(default_factory=list)


def create_chat_agent(model: str = "openai:gpt-4o") -> Agent[ChatDependencies, str]:
    """Create and configure a PydanticAI ChatAgent with advisor tools.

    Args:
        model: PydanticAI model identifier (e.g. "openai:gpt-4o", "anthropic:claude-sonnet-4-6")

    Returns:
        Configured PydanticAI Agent instance
    """
    agent = Agent(
        model=model,
        deps_type=ChatDependencies,
        output_type=str,
        retries=2,
    )

    # Dynamic system prompt assembled per conversation turn
    @agent.system_prompt
    async def build_system_prompt(ctx: RunContext[ChatDependencies]) -> str:
        deps = ctx.deps
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        parts = [
            "You are Cortex, an AI assistant that helps manage and prioritize projects.",
            "You have access to the user's projects, tasks, knowledge base, and session history.",
            "Be concise, actionable, and helpful. When recommending priorities, explain your reasoning.",
            f"\nCurrent date/time: {now}",
        ]

        # User context from profile
        profile = deps.user_profile
        if profile.get("bio"):
            parts.append(f"\nAbout the user: {profile['bio']}")
        if profile.get("long_term_goals"):
            goals = ", ".join(str(g) for g in profile["long_term_goals"])
            parts.append(f"Long-term goals: {goals}")
        if profile.get("current_priorities"):
            priorities = ", ".join(str(p) for p in profile["current_priorities"])
            parts.append(f"Current priorities: {priorities}")
        if profile.get("preferences"):
            parts.append(f"Communication preferences: {profile['preferences']}")

        # Project scope
        if deps.project_id:
            parts.append(f"\nThis conversation is scoped to project ID: {deps.project_id}")
            parts.append("Focus your responses on this project's context.")

        # Action mode status
        if deps.action_mode:
            parts.append(
                "\nAction mode is ENABLED. You can create tasks, update projects, and take other actions."
            )
            parts.append("Always explain what you're about to do and confirm before taking destructive actions.")
        else:
            parts.append("\nYou are in advisor mode. You can search and analyze but cannot modify data.")
            parts.append("If the user asks you to take an action, suggest they enable action mode.")

        # Onboarding prompt for new users
        if not profile.get("onboarding_completed", False):
            parts.append("\nThe user has not completed onboarding. Start by asking them about themselves.")
            parts.append("Ask one question at a time to build their profile.")

        return "\n".join(parts)

    # Register advisor tools (always available)
    from . import chat_tools

    @agent.tool
    async def search_knowledge_base(ctx: RunContext[ChatDependencies], query: str) -> str:
        """Search the knowledge base for relevant documents and information."""
        return await chat_tools.tool_search_knowledge_base(query)

    @agent.tool
    async def list_projects(ctx: RunContext[ChatDependencies]) -> str:
        """List all projects with their status, categories, and goals."""
        return await chat_tools.tool_list_projects()

    @agent.tool
    async def get_project_detail(ctx: RunContext[ChatDependencies], project_id: str) -> str:
        """Get detailed information about a specific project."""
        return await chat_tools.tool_get_project_detail(project_id)

    @agent.tool
    async def list_tasks(ctx: RunContext[ChatDependencies], project_id: str = "", status: str = "") -> str:
        """List tasks, optionally filtered by project or status."""
        return await chat_tools.tool_list_tasks(
            project_id=project_id or None,
            status=status or None,
        )

    @agent.tool
    async def get_task_detail(ctx: RunContext[ChatDependencies], task_id: str) -> str:
        """Get detailed information about a specific task."""
        return await chat_tools.tool_get_task_detail(task_id)

    @agent.tool
    async def list_documents(ctx: RunContext[ChatDependencies], project_id: str) -> str:
        """List documents for a specific project."""
        return await chat_tools.tool_list_documents(project_id)

    @agent.tool
    async def get_session_history(ctx: RunContext[ChatDependencies], query: str = "") -> str:
        """Search recent session history across machines to understand activity patterns."""
        return await chat_tools.tool_get_session_history(query=query or None)

    @agent.tool
    async def search_code_examples(ctx: RunContext[ChatDependencies], query: str) -> str:
        """Search for code examples in the knowledge base."""
        return await chat_tools.tool_search_code_examples(query)

    @agent.tool
    async def suggest_project_category(
        ctx: RunContext[ChatDependencies], project_name: str, description: str
    ) -> str:
        """Suggest a category for a project based on its name, description, and existing categories."""
        # Fetch existing categories via MCP to provide context
        client = await get_mcp_client()
        projects_data = await client.call_tool("find_projects")
        if isinstance(projects_data, str):
            projects = json.loads(projects_data)
        else:
            projects = projects_data
        # Extract unique existing categories
        project_list = projects if isinstance(projects, list) else projects.get("projects", [])
        existing = list({
            p.get("project_category", "")
            for p in project_list
            if p.get("project_category")
        })
        return await chat_tools.tool_suggest_project_category(project_name, description, existing)

    # Prioritization and synergy analysis tools
    @agent.tool
    async def get_prioritization_context(ctx: RunContext[ChatDependencies]) -> str:
        """Gather all projects, recent sessions, and active tasks to recommend what to work on next."""
        return await chat_tools.tool_get_prioritization_context()

    @agent.tool
    async def analyze_project_synergies(ctx: RunContext[ChatDependencies]) -> str:
        """Analyze all projects for shared technologies, overlapping goals, and consolidation opportunities."""
        return await chat_tools.tool_analyze_project_synergies()

    # Action mode tools — guarded by ctx.deps.action_mode
    @agent.tool
    async def create_task(
        ctx: RunContext[ChatDependencies], project_id: str, title: str, description: str = ""
    ) -> str:
        """Create a new task in a project. Requires action mode to be enabled."""
        if not ctx.deps.action_mode:
            return "Action mode is not enabled. Ask the user to enable action mode to create tasks."
        return await chat_tools.tool_create_task(project_id, title, description)

    @agent.tool
    async def update_task(
        ctx: RunContext[ChatDependencies], task_id: str, status: str = "", title: str = ""
    ) -> str:
        """Update an existing task's status or title. Requires action mode to be enabled."""
        if not ctx.deps.action_mode:
            return "Action mode is not enabled. Ask the user to enable action mode to update tasks."
        return await chat_tools.tool_update_task(task_id, status=status or None, title=title or None)

    @agent.tool
    async def create_document(
        ctx: RunContext[ChatDependencies], project_id: str, title: str, content: str
    ) -> str:
        """Create a new document in a project. Requires action mode to be enabled."""
        if not ctx.deps.action_mode:
            return "Action mode is not enabled. Ask the user to enable action mode to create documents."
        return await chat_tools.tool_create_document(project_id, title, content)

    return agent
