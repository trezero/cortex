"""
Projects API endpoints for Cortex

Handles:
- Project management (CRUD operations)
- Task management with hierarchical structure
- Streaming project creation with DocumentAgent integration
- HTTP polling for progress updates
"""

import json
from datetime import UTC, datetime
from email.utils import format_datetime
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request, Response
from fastapi import status as http_status
from pydantic import BaseModel, ConfigDict, Field

# Removed direct logging import - using unified config
# Set up standard logger for background tasks
from ..config.logfire_config import get_logger, logfire
from ..utils import get_supabase_client
from ..utils.etag_utils import check_etag, generate_etag

logger = get_logger(__name__)

# Service imports
from ..services.knowledge import KnowledgeSummaryService
from ..services.projects import (
    ProjectCreationService,
    ProjectService,
    SourceLinkingService,
    TaskService,
)
from ..services.projects.document_service import DocumentService
from ..services.projects.versioning_service import VersioningService

# Using HTTP polling for real-time updates

router = APIRouter(prefix="/api", tags=["projects"])


class CreateProjectRequest(BaseModel):
    title: str = Field(..., description="The project title")
    description: str | None = Field(None, description="Optional project description")
    github_repo: str | None = Field(None, description="Associated GitHub repository URL")
    docs: list[Any] | None = Field(None, description="Project documentation content")
    features: list[Any] | None = Field(None, description="Project features list")
    data: list[Any] | None = Field(None, description="Project data content")
    technical_sources: list[str] | None = Field(None, description="List of knowledge source IDs for technical sources")
    business_sources: list[str] | None = Field(None, description="List of knowledge source IDs for business sources")
    pinned: bool | None = Field(None, description="Whether this project should be pinned to top")
    parent_project_id: str | None = Field(None, description="Parent project ID for hierarchy")
    metadata: dict[str, Any] | None = Field(None, description="Key-value metadata")
    tags: list[str] | None = Field(None, description="Filterable tags")
    project_goals: list[str] | None = Field(None, description="Project goals for AI prioritization")
    project_relevance: str | None = Field(None, description="How this project relates to the user's overall objectives")
    project_category: str | None = Field(None, description="Project category for grouping and analysis")


class UpdateProjectRequest(BaseModel):
    title: str | None = Field(None, description="Updated project title")
    description: str | None = Field(None, description="Updated project description")
    github_repo: str | None = Field(None, description="Updated GitHub repository URL")
    docs: list[Any] | None = Field(None, description="Updated documentation content")
    features: list[Any] | None = Field(None, description="Updated features list")
    data: list[Any] | None = Field(None, description="Updated data content")
    technical_sources: list[str] | None = Field(None, description="List of knowledge source IDs for technical sources")
    business_sources: list[str] | None = Field(None, description="List of knowledge source IDs for business sources")
    pinned: bool | None = Field(None, description="Whether this project is pinned to top")
    parent_project_id: str | None = Field(None, description="Parent project ID for hierarchy")
    metadata: dict[str, Any] | None = Field(None, description="Key-value metadata")
    tags: list[str] | None = Field(None, description="Filterable tags")
    project_goals: list[str] | None = Field(None, description="Project goals for AI prioritization")
    project_relevance: str | None = Field(None, description="How this project relates to the user's overall objectives")
    project_category: str | None = Field(None, description="Project category for grouping and analysis")


class CreateTaskRequest(BaseModel):
    project_id: str = Field(..., description="ID of the project this task belongs to")
    title: str = Field(..., description="Task title")
    description: str | None = Field(None, description="Optional task description")
    status: str | None = Field("todo", description="Initial task status (todo, doing, review, done)")
    assignee: str | None = Field("User", description="Task assignee (User, Cortex, AI IDE Agent)")
    task_order: int | None = Field(0, description="Sort order within the task list")
    priority: str | None = Field("medium", description="Task priority (low, medium, high)")
    feature: str | None = Field(None, description="Feature tag for grouping tasks")


# ==================== RESPONSE MODELS ====================


class ProjectSummary(BaseModel):
    """Lightweight project representation."""

    id: str = Field(..., description="Unique project identifier")
    title: str = Field(..., description="Project title")
    description: str | None = Field(None, description="Project description")
    github_repo: str | None = Field(None, description="Associated GitHub repository URL")
    pinned: bool = Field(False, description="Whether this project is pinned")
    created_at: str | None = Field(None, description="ISO 8601 creation timestamp")
    model_config = ConfigDict(extra="allow")


class ProjectListResponse(BaseModel):
    projects: list[dict[str, Any]] = Field(..., description="List of project objects")
    timestamp: str = Field(..., description="ISO 8601 response timestamp")
    count: int = Field(..., description="Total number of projects")
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "projects": [{"id": "proj_abc", "title": "My Project"}],
                "timestamp": "2026-01-15T10:30:00Z",
                "count": 1,
            }
        }
    )


class ProjectCreateResponse(BaseModel):
    project_id: str = Field(..., description="ID of the created project")
    project: dict[str, Any] | None = Field(None, description="Full project object")
    status: str = Field(..., description="Creation status")
    message: str = Field(..., description="Human-readable status message")
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "project_id": "proj_abc123",
                "project": {"id": "proj_abc123", "title": "My Project"},
                "status": "completed",
                "message": "Project 'My Project' created successfully",
            }
        }
    )


class SchemaHealth(BaseModel):
    projects_table: bool = Field(..., description="Whether the projects table exists")
    tasks_table: bool = Field(..., description="Whether the tasks table exists")
    valid: bool = Field(..., description="Whether the schema is fully valid")


class ProjectHealthResponse(BaseModel):
    status: str = Field(..., description="Health status: 'healthy', 'schema_missing', or 'error'")
    service: str = Field(..., description="Service name")
    schema_info: SchemaHealth = Field(..., alias="schema", description="Schema validation details")
    error: str | None = Field(None, description="Error message if status is 'error'")
    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "status": "healthy",
                "service": "projects",
                "schema": {"projects_table": True, "tasks_table": True, "valid": True},
            }
        },
    )


class ProjectChildrenResponse(BaseModel):
    children: list[dict[str, Any]] = Field(..., description="List of child project objects")
    model_config = ConfigDict(
        json_schema_extra={
            "example": {"children": [{"id": "proj_child1", "title": "Child Project"}]}
        }
    )


class ProjectDeleteResponse(BaseModel):
    message: str = Field(..., description="Deletion confirmation message")
    deleted_tasks: int = Field(0, description="Number of tasks deleted with the project")
    model_config = ConfigDict(
        json_schema_extra={"example": {"message": "Project deleted successfully", "deleted_tasks": 5}}
    )


class TaskCreateResponse(BaseModel):
    message: str = Field(..., description="Creation confirmation message")
    task: dict[str, Any] = Field(..., description="The created task object")
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "message": "Task created successfully",
                "task": {"id": "task_abc", "title": "Fix bug", "status": "todo"},
            }
        }
    )


class PaginationInfo(BaseModel):
    total: int = Field(..., description="Total number of items")
    page: int = Field(..., description="Current page number")
    per_page: int = Field(..., description="Items per page")
    pages: int = Field(..., description="Total number of pages")


class TaskListResponse(BaseModel):
    tasks: list[dict[str, Any]] = Field(..., description="List of task objects")
    pagination: PaginationInfo = Field(..., description="Pagination metadata")
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "tasks": [{"id": "task_abc", "title": "Fix bug", "status": "todo"}],
                "pagination": {"total": 1, "page": 1, "per_page": 10, "pages": 1},
            }
        }
    )


class TaskUpdateResponse(BaseModel):
    message: str = Field(..., description="Update confirmation message")
    task: dict[str, Any] = Field(..., description="The updated task object")
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "message": "Task updated successfully",
                "task": {"id": "task_abc", "title": "Fix bug", "status": "doing"},
            }
        }
    )


class TaskDeleteResponse(BaseModel):
    message: str = Field(..., description="Archive confirmation message")
    model_config = ConfigDict(
        json_schema_extra={"example": {"message": "Task archived successfully"}}
    )


class DocumentCreateResponse(BaseModel):
    message: str = Field(..., description="Creation confirmation message")
    document: dict[str, Any] = Field(..., description="The created document object")
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "message": "Document created successfully",
                "document": {"id": "doc_abc", "title": "Design Doc", "document_type": "spec"},
            }
        }
    )


class DocumentUpdateResponse(BaseModel):
    message: str = Field(..., description="Update confirmation message")
    document: dict[str, Any] = Field(..., description="The updated document object")
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "message": "Document updated successfully",
                "document": {"id": "doc_abc", "title": "Updated Doc"},
            }
        }
    )


class DocumentDeleteResponse(BaseModel):
    message: str = Field(..., description="Deletion confirmation message")
    model_config = ConfigDict(
        json_schema_extra={"example": {"message": "Document deleted successfully"}}
    )


class VersionCreateResponse(BaseModel):
    message: str = Field(..., description="Creation confirmation message")
    version: dict[str, Any] = Field(..., description="The created version object")
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "message": "Version created successfully",
                "version": {"id": "ver_abc", "version_number": 1, "field_name": "docs"},
            }
        }
    )


class VersionRestoreResponse(BaseModel):
    message: str = Field(..., description="Restore confirmation message")
    model_config = ConfigDict(
        extra="allow",
        json_schema_extra={"example": {"message": "Successfully restored docs to version 3"}},
    )


@router.get(
    "/projects",
    response_model=ProjectListResponse,
    status_code=http_status.HTTP_200_OK,
    responses={500: {"description": "Internal server error"}},
)
async def list_projects(
    response: Response,
    include_content: bool = True,
    q: str | None = None,
    if_none_match: str | None = Header(None),
) -> ProjectListResponse | None:
    """
    List all projects.
    
    Args:
        include_content: If True (default), returns full project content.
                        If False, returns lightweight metadata with statistics.
    """
    try:
        logfire.debug(f"Listing all projects | include_content={include_content}")

        # Use ProjectService to get projects with include_content parameter
        project_service = ProjectService()
        success, result = project_service.list_projects(include_content=include_content)

        if not success:
            raise HTTPException(status_code=500, detail=result)

        # Only format with sources if we have full content
        if include_content:
            # Use SourceLinkingService to format projects with sources
            source_service = SourceLinkingService()
            formatted_projects = source_service.format_projects_with_sources(result["projects"])
        else:
            # Lightweight response doesn't need source formatting
            formatted_projects = result["projects"]

        # Apply title search filter before enrichment to avoid unnecessary work
        if q:
            q_lower = q.lower()
            formatted_projects = [
                p for p in formatted_projects
                if q_lower in (p.get("title") or "").lower()
            ]

        # Enrich projects with system registration data
        project_ids = [p["id"] for p in formatted_projects]
        system_regs = project_service.get_system_registrations_for_projects(project_ids)
        for project in formatted_projects:
            regs = system_regs.get(project["id"], [])
            project["system_registrations"] = regs
            project["has_uncommitted_changes"] = any(r.get("git_dirty") for r in regs)

        # Monitor response size for optimization validation
        response_json = json.dumps(formatted_projects)
        response_size = len(response_json)

        # Log response metrics
        logfire.debug(
            f"Projects listed successfully | count={len(formatted_projects)} | "
            f"size_bytes={response_size} | include_content={include_content}"
        )

        # Log large responses at debug level (>100KB is worth noting, but normal for project data)
        if response_size > 100000:
            logfire.debug(
                f"Large response size | size_bytes={response_size} | "
                f"include_content={include_content} | project_count={len(formatted_projects)}"
            )

        # Generate ETag from stable data (excluding timestamp)
        etag_data = {
            "projects": formatted_projects,
            "count": len(formatted_projects)
        }
        current_etag = generate_etag(etag_data)

        # Generate response with timestamp for polling
        response_data = {
            "projects": formatted_projects,
            "timestamp": datetime.utcnow().isoformat(),
            "count": len(formatted_projects)
        }

        # Check if client's ETag matches
        if check_etag(if_none_match, current_etag):
            response.status_code = http_status.HTTP_304_NOT_MODIFIED
            response.headers["ETag"] = current_etag
            response.headers["Cache-Control"] = "no-cache, must-revalidate"
            return None

        # Set headers
        response.headers["ETag"] = current_etag
        response.headers["Last-Modified"] = datetime.utcnow().isoformat()
        response.headers["Cache-Control"] = "no-cache, must-revalidate"

        return response_data

    except HTTPException:
        raise
    except Exception as e:
        logfire.error(f"Failed to list projects | error={str(e)}")
        raise HTTPException(status_code=500, detail={"error": str(e)})


@router.post(
    "/projects",
    response_model=ProjectCreateResponse,
    status_code=http_status.HTTP_201_CREATED,
    responses={
        422: {"description": "Validation error"},
        500: {"description": "Internal server error"},
    },
)
async def create_project(request: CreateProjectRequest) -> ProjectCreateResponse:
    """Create a new project with streaming progress."""
    # Validate title
    if not request.title:
        raise HTTPException(status_code=422, detail="Title is required")

    if not request.title.strip():
        raise HTTPException(status_code=422, detail="Title cannot be empty")

    try:
        logfire.info(
            f"Creating new project | title={request.title} | github_repo={request.github_repo}"
        )

        # Prepare kwargs for additional project fields
        kwargs = {}
        if request.pinned is not None:
            kwargs["pinned"] = request.pinned
        if request.features:
            kwargs["features"] = request.features
        if request.data:
            kwargs["data"] = request.data
        if request.parent_project_id is not None:
            kwargs["parent_project_id"] = request.parent_project_id
        if request.metadata is not None:
            kwargs["metadata"] = request.metadata
        if request.tags is not None:
            kwargs["tags"] = request.tags
        if request.project_goals is not None:
            kwargs["project_goals"] = request.project_goals
        if request.project_relevance is not None:
            kwargs["project_relevance"] = request.project_relevance
        if request.project_category is not None:
            kwargs["project_category"] = request.project_category

        # Create project directly with AI assistance
        project_service = ProjectCreationService()
        success, result = await project_service.create_project_with_ai(
            progress_id="direct",  # No progress tracking needed
            title=request.title,
            description=request.description,
            github_repo=request.github_repo,
            **kwargs,
        )

        if success:
            logfire.info(f"Project created successfully | project_id={result['project_id']}")
            return {
                "project_id": result["project_id"],
                "project": result.get("project"),
                "status": "completed",
                "message": f"Project '{request.title}' created successfully",
            }
        else:
            raise HTTPException(status_code=500, detail=result)

    except Exception as e:
        logfire.error(f"Failed to start project creation | error={str(e)} | title={request.title}")
        raise HTTPException(status_code=500, detail={"error": str(e)})




@router.get(
    "/projects/health",
    response_model=ProjectHealthResponse,
    status_code=http_status.HTTP_200_OK,
    responses={500: {"description": "Internal server error"}},
)
async def projects_health() -> dict[str, Any]:
    """Health check for projects API and database schema validation."""
    try:
        logfire.info("Projects health check requested")
        supabase_client = get_supabase_client()

        # Check if projects table exists by testing ProjectService
        try:
            project_service = ProjectService(supabase_client)
            # Try to list projects with limit 1 to test table access
            success, _ = project_service.list_projects()
            projects_table_exists = success
            if success:
                logfire.info("Projects table detected successfully")
            else:
                logfire.warning("Projects table access failed")
        except Exception as e:
            projects_table_exists = False
            logfire.warning(f"Projects table not found | error={str(e)}")

        # Check if tasks table exists by testing TaskService
        try:
            task_service = TaskService(supabase_client)
            # Try to list tasks with limit 1 to test table access
            success, _ = task_service.list_tasks(include_closed=True)
            tasks_table_exists = success
            if success:
                logfire.info("Tasks table detected successfully")
            else:
                logfire.warning("Tasks table access failed")
        except Exception as e:
            tasks_table_exists = False
            logfire.warning(f"Tasks table not found | error={str(e)}")

        schema_valid = projects_table_exists and tasks_table_exists

        result = {
            "status": "healthy" if schema_valid else "schema_missing",
            "service": "projects",
            "schema": {
                "projects_table": projects_table_exists,
                "tasks_table": tasks_table_exists,
                "valid": schema_valid,
            },
        }

        logfire.info(
            f"Projects health check completed | status={result['status']} | schema_valid={schema_valid}"
        )

        return result

    except Exception as e:
        logfire.error(f"Projects health check failed | error={str(e)}")
        return {
            "status": "error",
            "service": "projects",
            "error": str(e),
            "schema": {"projects_table": False, "tasks_table": False, "valid": False},
        }


@router.get(
    "/projects/task-counts",
    status_code=http_status.HTTP_200_OK,
    responses={500: {"description": "Internal server error"}},
)
async def get_all_task_counts(
    request: Request,
    response: Response,
) -> dict[str, Any] | None:
    """
    Get task counts for all projects in a single batch query.
    Optimized endpoint to avoid N+1 query problem.
    
    Returns counts grouped by project_id with todo, doing, and done counts.
    Review status is included in doing count to match frontend logic.
    """
    try:
        # Get If-None-Match header for ETag comparison
        if_none_match = request.headers.get("If-None-Match")

        logfire.debug(f"Getting task counts for all projects | etag={if_none_match}")

        # Use TaskService to get batch task counts
        # Get client explicitly to ensure mocking works in tests
        supabase_client = get_supabase_client()
        task_service = TaskService(supabase_client)
        success, result = task_service.get_all_project_task_counts()

        if not success:
            logfire.error(f"Failed to get task counts | error={result.get('error')}")
            raise HTTPException(status_code=500, detail=result)

        # Generate ETag from counts data
        etag_data = {
            "counts": result,
            "count": len(result)
        }
        current_etag = generate_etag(etag_data)

        # Check if client's ETag matches (304 Not Modified)
        if check_etag(if_none_match, current_etag):
            response.status_code = 304
            response.headers["ETag"] = current_etag
            response.headers["Cache-Control"] = "no-cache, must-revalidate"
            logfire.debug(f"Task counts unchanged, returning 304 | etag={current_etag}")
            return None

        # Set ETag headers for successful response
        response.headers["ETag"] = current_etag
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
        response.headers["Last-Modified"] = datetime.utcnow().isoformat()

        logfire.debug(
            f"Task counts retrieved | project_count={len(result)} | etag={current_etag}"
        )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logfire.error(f"Failed to get task counts | error={str(e)}")
        raise HTTPException(status_code=500, detail={"error": str(e)})


@router.get(
    "/projects/{project_id}",
    status_code=http_status.HTTP_200_OK,
    responses={
        404: {"description": "Project not found"},
        500: {"description": "Internal server error"},
    },
)
async def get_project(project_id: str) -> dict[str, Any]:
    """Get a specific project."""
    try:
        logfire.info(f"Getting project | project_id={project_id}")

        # Use ProjectService to get the project
        project_service = ProjectService()
        success, result = project_service.get_project(project_id)

        if not success:
            if "not found" in result.get("error", "").lower():
                logfire.warning(f"Project not found | project_id={project_id}")
                raise HTTPException(status_code=404, detail=result)
            else:
                raise HTTPException(status_code=500, detail=result)

        project = result["project"]

        logfire.info(
            f"Project retrieved successfully | project_id={project_id} | title={project['title']}"
        )

        # The ProjectService already includes sources, so just add any missing fields
        return {
            **project,
            "description": project.get("description", ""),
            "docs": project.get("docs", []),
            "features": project.get("features", []),
            "data": project.get("data", []),
            "pinned": project.get("pinned", False),
        }

    except HTTPException:
        raise
    except Exception as e:
        logfire.error(f"Failed to get project | error={str(e)} | project_id={project_id}")
        raise HTTPException(status_code=500, detail={"error": str(e)})


@router.put(
    "/projects/{project_id}",
    status_code=http_status.HTTP_200_OK,
    responses={
        404: {"description": "Project not found"},
        500: {"description": "Internal server error"},
    },
)
async def update_project(project_id: str, request: UpdateProjectRequest) -> dict[str, Any]:
    """Update a project with comprehensive Logfire monitoring."""
    try:
        supabase_client = get_supabase_client()

        # Build update fields from request
        update_fields = {}
        if request.title is not None:
            update_fields["title"] = request.title
        if request.description is not None:
            update_fields["description"] = request.description
        if request.github_repo is not None:
            update_fields["github_repo"] = request.github_repo
        if request.docs is not None:
            update_fields["docs"] = request.docs
        if request.features is not None:
            update_fields["features"] = request.features
        if request.data is not None:
            update_fields["data"] = request.data
        if request.pinned is not None:
            update_fields["pinned"] = request.pinned
        if "parent_project_id" in request.model_fields_set:
            update_fields["parent_project_id"] = request.parent_project_id
        if request.metadata is not None:
            update_fields["metadata"] = request.metadata
        if request.tags is not None:
            update_fields["tags"] = request.tags
        if request.project_goals is not None:
            update_fields["project_goals"] = request.project_goals
        if request.project_relevance is not None:
            update_fields["project_relevance"] = request.project_relevance
        if request.project_category is not None:
            update_fields["project_category"] = request.project_category

        # Create version snapshots for JSONB fields before updating
        if update_fields:
            try:
                from ..services.projects.versioning_service import VersioningService

                versioning_service = VersioningService(supabase_client)

                # Get current project for comparison
                project_service = ProjectService(supabase_client)
                success, current_result = project_service.get_project(project_id)

                if success and current_result.get("project"):
                    current_project = current_result["project"]
                    version_count = 0

                    # Create versions for updated JSONB fields
                    for field_name in ["docs", "features", "data"]:
                        if field_name in update_fields:
                            current_content = current_project.get(field_name, {})
                            new_content = update_fields[field_name]

                            # Only create version if content actually changed
                            if current_content != new_content:
                                v_success, _ = versioning_service.create_version(
                                    project_id=project_id,
                                    field_name=field_name,
                                    content=current_content,
                                    change_summary=f"Updated {field_name} via API",
                                    change_type="update",
                                    created_by="api_user",
                                )
                                if v_success:
                                    version_count += 1

                    logfire.info(f"Created {version_count} version snapshots before update")
            except ImportError:
                logfire.warning("VersioningService not available - skipping version snapshots")
            except Exception as e:
                logfire.warning(f"Failed to create version snapshots: {e}")
                # Don't fail the update, just log the warning

        # Use ProjectService to update the project
        project_service = ProjectService(supabase_client)
        success, result = project_service.update_project(project_id, update_fields)

        if not success:
            if "not found" in result.get("error", "").lower():
                raise HTTPException(
                    status_code=404, detail={"error": f"Project with ID {project_id} not found"}
                )
            else:
                raise HTTPException(status_code=500, detail=result)

        project = result["project"]

        # Invalidate search cache when parent_project_id changes
        if "parent_project_id" in update_fields:
            from ..utils.source_cache import invalidate_source_cache
            invalidate_source_cache(project_id)

        # Handle source updates using SourceLinkingService
        source_service = SourceLinkingService(supabase_client)

        if request.technical_sources is not None or request.business_sources is not None:
            source_success, source_result = source_service.update_project_sources(
                project_id=project_id,
                technical_sources=request.technical_sources,
                business_sources=request.business_sources,
            )

            if source_success:
                logfire.info(
                    f"Project sources updated | project_id={project_id} | technical_success={source_result.get('technical_success', 0)} | technical_failed={source_result.get('technical_failed', 0)} | business_success={source_result.get('business_success', 0)} | business_failed={source_result.get('business_failed', 0)}"
                )
            else:
                logfire.warning(f"Failed to update some sources: {source_result}")

        # Format project response with sources using SourceLinkingService
        formatted_project = source_service.format_project_with_sources(project)

        logfire.info(
            f"Project updated successfully | project_id={project_id} | title={project.get('title')} | technical_sources={len(formatted_project.get('technical_sources', []))} | business_sources={len(formatted_project.get('business_sources', []))}"
        )

        return formatted_project

    except HTTPException:
        raise
    except Exception as e:
        logfire.error(f"Project update failed | project_id={project_id} | error={str(e)}")
        raise HTTPException(status_code=500, detail={"error": str(e)})


@router.get(
    "/projects/{project_id}/children",
    response_model=ProjectChildrenResponse,
    status_code=http_status.HTTP_200_OK,
    responses={500: {"description": "Internal server error"}},
)
async def get_project_children(project_id: str) -> ProjectChildrenResponse:
    """Get lightweight child projects for a parent project."""
    try:
        supabase_client = get_supabase_client()
        project_service = ProjectService(supabase_client)

        success, result = project_service.get_project_children(project_id)

        if not success:
            raise HTTPException(status_code=500, detail=result.get("error", "Failed to fetch children"))

        # Enrich children with system_registrations
        # get_system_registrations_for_projects returns dict[str, list[dict]]
        # mapping project_id -> list of registration dicts directly
        children = result.get("children", [])
        if children:
            child_ids = [c["id"] for c in children]
            reg_map = project_service.get_system_registrations_for_projects(child_ids)
            for child in children:
                child["system_registrations"] = reg_map.get(child["id"], [])

        return {"children": children}

    except HTTPException:
        raise
    except Exception as e:
        logfire.error(f"Failed to get project children | error={str(e)} | project_id={project_id}")
        raise HTTPException(status_code=500, detail={"error": str(e)}) from e


@router.delete(
    "/projects/{project_id}",
    response_model=ProjectDeleteResponse,
    status_code=http_status.HTTP_200_OK,
    responses={
        404: {"description": "Project not found"},
        500: {"description": "Internal server error"},
    },
)
async def delete_project(project_id: str) -> ProjectDeleteResponse:
    """Delete a project and all its tasks."""
    try:
        logfire.info(f"Deleting project | project_id={project_id}")

        # Use ProjectService to delete the project
        project_service = ProjectService()
        success, result = project_service.delete_project(project_id)

        if not success:
            if "not found" in result.get("error", "").lower():
                raise HTTPException(status_code=404, detail=result)
            else:
                raise HTTPException(status_code=500, detail=result)

        logfire.info(
            f"Project deleted successfully | project_id={project_id} | deleted_tasks={result.get('deleted_tasks', 0)}"
        )

        return {
            "message": "Project deleted successfully",
            "deleted_tasks": result.get("deleted_tasks", 0),
        }

    except HTTPException:
        raise
    except Exception as e:
        logfire.error(f"Failed to delete project | error={str(e)} | project_id={project_id}")
        raise HTTPException(status_code=500, detail={"error": str(e)})


@router.get(
    "/projects/{project_id}/features",
    status_code=http_status.HTTP_200_OK,
    responses={
        404: {"description": "Project not found"},
        500: {"description": "Internal server error"},
    },
)
async def get_project_features(project_id: str) -> dict[str, Any]:
    """Get features from a project's features JSONB field."""
    try:
        logfire.info(f"Getting project features | project_id={project_id}")

        # Use ProjectService to get features
        project_service = ProjectService()
        success, result = project_service.get_project_features(project_id)

        if not success:
            if "not found" in result.get("error", "").lower():
                logfire.warning(f"Project not found for features | project_id={project_id}")
                raise HTTPException(status_code=404, detail=result)
            else:
                raise HTTPException(status_code=500, detail=result)

        logfire.info(
            f"Project features retrieved | project_id={project_id} | feature_count={result.get('count', 0)}"
        )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logfire.error(f"Failed to get project features | error={str(e)} | project_id={project_id}")
        raise HTTPException(status_code=500, detail={"error": str(e)})


class ProjectStatsResponse(BaseModel):
    """Task count statistics for a project."""

    project_id: str = Field(..., description="Project identifier")
    todo: int = Field(0, description="Number of tasks in 'todo' status")
    doing: int = Field(0, description="Number of tasks in 'doing' status")
    review: int = Field(0, description="Number of tasks in 'review' status")
    done: int = Field(0, description="Number of tasks in 'done' status")
    total: int = Field(0, description="Total number of tasks across all statuses")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "project_id": "proj_abc123",
                "todo": 5,
                "doing": 2,
                "review": 1,
                "done": 12,
                "total": 20,
            }
        }
    )


@router.get(
    "/projects/{project_id}/stats",
    response_model=ProjectStatsResponse,
    status_code=http_status.HTTP_200_OK,
    tags=["projects"],
    responses={
        404: {"description": "Project not found"},
        500: {"description": "Internal server error"},
    },
)
async def get_project_stats(project_id: str) -> ProjectStatsResponse:
    """Get task count statistics for a project, grouped by status."""
    try:
        logfire.info(f"Getting project stats | project_id={project_id}")

        # Verify project exists
        project_service = ProjectService()
        success, result = project_service.get_project(project_id)
        if not success:
            if "not found" in result.get("error", "").lower():
                raise HTTPException(status_code=404, detail=result)
            else:
                raise HTTPException(status_code=500, detail=result)

        # Get task counts for this project
        task_service = TaskService()
        success, counts = task_service.get_all_project_task_counts()
        if not success:
            raise HTTPException(status_code=500, detail=counts)

        project_counts = counts.get(project_id, {"todo": 0, "doing": 0, "review": 0, "done": 0})

        stats = ProjectStatsResponse(
            project_id=project_id,
            todo=project_counts.get("todo", 0),
            doing=project_counts.get("doing", 0),
            review=project_counts.get("review", 0),
            done=project_counts.get("done", 0),
            total=sum(project_counts.values()),
        )

        logfire.info(f"Project stats retrieved | project_id={project_id} | total={stats.total}")
        return stats

    except HTTPException:
        raise
    except Exception as e:
        logfire.error(f"Failed to get project stats | error={str(e)} | project_id={project_id}")
        raise HTTPException(status_code=500, detail={"error": str(e)})


@router.get(
    "/projects/{project_id}/tasks",
    status_code=http_status.HTTP_200_OK,
    responses={500: {"description": "Internal server error"}},
)
async def list_project_tasks(
    project_id: str,
    request: Request,
    response: Response,
    include_archived: bool = False,
    exclude_large_fields: bool = False,
) -> list[dict[str, Any]] | None:
    """List all tasks for a specific project with ETag support for efficient polling."""
    try:
        # Get If-None-Match header for ETag comparison
        if_none_match = request.headers.get("If-None-Match")

        logfire.debug(
            f"Listing project tasks | project_id={project_id} | include_archived={include_archived} | exclude_large_fields={exclude_large_fields} | etag={if_none_match}"
        )

        # Use TaskService to list tasks
        task_service = TaskService()
        success, result = task_service.list_tasks(
            project_id=project_id,
            include_closed=True,  # Get all tasks, including done
            exclude_large_fields=exclude_large_fields,
            include_archived=include_archived,  # Pass the flag down to service
        )

        if not success:
            raise HTTPException(status_code=500, detail=result)

        tasks = result.get("tasks", [])

        # Generate ETag from task data (includes description and updated_at to drive polling invalidation)
        etag_tasks: list[dict[str, object]] = []
        last_modified_dt: datetime | None = None

        for task in tasks:
            raw_updated = task.get("updated_at")
            parsed_updated: datetime | None = None
            if isinstance(raw_updated, datetime):
                parsed_updated = raw_updated
            elif isinstance(raw_updated, str):
                try:
                    parsed_updated = datetime.fromisoformat(raw_updated.replace("Z", "+00:00"))
                except ValueError:
                    parsed_updated = None

            if parsed_updated is not None:
                parsed_updated = parsed_updated.astimezone(UTC)
                if last_modified_dt is None or parsed_updated > last_modified_dt:
                    last_modified_dt = parsed_updated

            etag_tasks.append(
                {
                    "id": task.get("id") or "",
                    "title": task.get("title") or "",
                    "status": task.get("status") or "",
                    "task_order": task.get("task_order") or 0,
                    "assignee": task.get("assignee") or "",
                    "priority": task.get("priority") or "",
                    "feature": task.get("feature") or "",
                    "description": task.get("description") or "",
                    "updated_at": (
                        parsed_updated.isoformat()
                        if parsed_updated is not None
                        else (str(raw_updated) if raw_updated else "")
                    ),
                }
            )

        etag_data = {"tasks": etag_tasks, "project_id": project_id, "count": len(tasks)}
        current_etag = generate_etag(etag_data)

        # Check if client's ETag matches (304 Not Modified)
        if check_etag(if_none_match, current_etag):
            response.status_code = 304
            response.headers["ETag"] = current_etag
            response.headers["Cache-Control"] = "no-cache, must-revalidate"
            response.headers["Last-Modified"] = format_datetime(
                last_modified_dt or datetime.now(UTC)
            )
            logfire.debug(f"Tasks unchanged, returning 304 | project_id={project_id} | etag={current_etag}")
            return None

        # Set ETag headers for successful response
        response.headers["ETag"] = current_etag
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
        response.headers["Last-Modified"] = format_datetime(
            last_modified_dt or datetime.now(UTC)
        )

        logfire.debug(
            f"Project tasks retrieved | project_id={project_id} | task_count={len(tasks)} | etag={current_etag}"
        )

        return tasks

    except HTTPException:
        raise
    except Exception as e:
        logfire.error(f"Failed to list project tasks | project_id={project_id}", exc_info=True)
        raise HTTPException(status_code=500, detail={"error": str(e)})


# Remove the complex /tasks endpoint - it's not needed and breaks things


@router.post(
    "/tasks",
    response_model=TaskCreateResponse,
    status_code=http_status.HTTP_201_CREATED,
    tags=["tasks"],
    responses={
        400: {"description": "Invalid task data"},
        500: {"description": "Internal server error"},
    },
)
async def create_task(request: CreateTaskRequest) -> TaskCreateResponse:
    """Create a new task with automatic reordering."""
    try:
        # Use TaskService to create the task
        task_service = TaskService()
        success, result = await task_service.create_task(
            project_id=request.project_id,
            title=request.title,
            description=request.description or "",
            assignee=request.assignee or "User",
            task_order=request.task_order or 0,
            priority=request.priority or "medium",
            feature=request.feature,
        )

        if not success:
            raise HTTPException(status_code=400, detail=result)

        created_task = result["task"]

        logfire.info(
            f"Task created successfully | task_id={created_task['id']} | project_id={request.project_id}"
        )

        return {"message": "Task created successfully", "task": created_task}

    except HTTPException:
        raise
    except Exception as e:
        logfire.error(f"Failed to create task | error={str(e)} | project_id={request.project_id}")
        raise HTTPException(status_code=500, detail={"error": str(e)})


@router.get(
    "/tasks",
    response_model=TaskListResponse,
    status_code=http_status.HTTP_200_OK,
    tags=["tasks"],
    responses={500: {"description": "Internal server error"}},
)
async def list_tasks(
    status: str | None = None,
    project_id: str | None = None,
    include_closed: bool = True,
    page: int = 1,
    per_page: int = 10,
    exclude_large_fields: bool = False,
    q: str | None = None,
) -> TaskListResponse:
    """List tasks with optional filters including status, project, and keyword search."""
    try:
        logfire.info(
            f"Listing tasks | status={status} | project_id={project_id} | include_closed={include_closed} | page={page} | per_page={per_page} | q={q}"
        )

        # Use TaskService to list tasks
        task_service = TaskService()
        success, result = task_service.list_tasks(
            project_id=project_id,
            status=status,
            include_closed=include_closed,
            exclude_large_fields=exclude_large_fields,
            search_query=q,  # Pass search query to service
        )

        if not success:
            raise HTTPException(status_code=500, detail=result)

        tasks = result.get("tasks", [])

        # If exclude_large_fields is True, remove large fields from tasks
        if exclude_large_fields:
            for task in tasks:
                # Remove potentially large fields
                task.pop("sources", None)
                task.pop("code_examples", None)
                task.pop("messages", None)

        # Apply pagination
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        paginated_tasks = tasks[start_idx:end_idx]

        # Prepare response
        response = {
            "tasks": paginated_tasks,
            "pagination": {
                "total": len(tasks),
                "page": page,
                "per_page": per_page,
                "pages": (len(tasks) + per_page - 1) // per_page,
            },
        }

        # Monitor response size for optimization validation
        response_json = json.dumps(response)
        response_size = len(response_json)

        # Log response metrics
        logfire.info(
            f"Tasks listed successfully | count={len(paginated_tasks)} | "
            f"size_bytes={response_size} | exclude_large_fields={exclude_large_fields}"
        )

        # Warning for large responses (>10KB)
        if response_size > 10000:
            logfire.warning(
                f"Large task response size | size_bytes={response_size} | "
                f"exclude_large_fields={exclude_large_fields} | task_count={len(paginated_tasks)}"
            )

        return response

    except HTTPException:
        raise
    except Exception as e:
        logfire.error(f"Failed to list tasks | error={str(e)}")
        raise HTTPException(status_code=500, detail={"error": str(e)})


@router.get(
    "/tasks/{task_id}",
    status_code=http_status.HTTP_200_OK,
    tags=["tasks"],
    responses={
        404: {"description": "Task not found"},
        500: {"description": "Internal server error"},
    },
)
async def get_task(task_id: str) -> dict[str, Any]:
    """Get a specific task by ID."""
    try:
        # Use TaskService to get the task
        task_service = TaskService()
        success, result = task_service.get_task(task_id)

        if not success:
            if "not found" in result.get("error", "").lower():
                raise HTTPException(status_code=404, detail=result.get("error"))
            else:
                raise HTTPException(status_code=500, detail=result)

        task = result["task"]

        logfire.info(
            f"Task retrieved successfully | task_id={task_id} | project_id={task.get('project_id')}"
        )

        return task

    except HTTPException:
        raise
    except Exception as e:
        logfire.error(f"Failed to get task | error={str(e)} | task_id={task_id}")
        raise HTTPException(status_code=500, detail={"error": str(e)})


class UpdateTaskRequest(BaseModel):
    title: str | None = Field(None, description="Updated task title")
    description: str | None = Field(None, description="Updated task description")
    status: str | None = Field(None, description="Updated task status (todo, doing, review, done)")
    assignee: str | None = Field(None, description="Updated task assignee")
    task_order: int | None = Field(None, description="Updated sort order")
    priority: str | None = Field(None, description="Updated task priority (low, medium, high)")
    feature: str | None = Field(None, description="Updated feature tag")


class CreateDocumentRequest(BaseModel):
    document_type: str = Field(..., description="Document type (e.g., spec, design, notes)")
    title: str = Field(..., description="Document title")
    content: dict[str, Any] | None = Field(None, description="Document content as JSON")
    tags: list[str] | None = Field(None, description="Document tags for categorization")
    author: str | None = Field(None, description="Document author")


class UpdateDocumentRequest(BaseModel):
    title: str | None = Field(None, description="Updated document title")
    content: dict[str, Any] | None = Field(None, description="Updated document content as JSON")
    tags: list[str] | None = Field(None, description="Updated document tags")
    author: str | None = Field(None, description="Updated document author")


class CreateVersionRequest(BaseModel):
    field_name: str = Field(..., description="JSONB field name to version (docs, features, data)")
    content: dict[str, Any] = Field(..., description="Content snapshot to store as the version")
    change_summary: str | None = Field(None, description="Human-readable summary of what changed")
    change_type: str | None = Field("update", description="Type of change (create, update, delete)")
    document_id: str | None = Field(None, description="Associated document ID if versioning a specific document")
    created_by: str | None = Field("system", description="Who created this version")


class RestoreVersionRequest(BaseModel):
    restored_by: str | None = Field("system", description="Who initiated the restore")


@router.put(
    "/tasks/{task_id}",
    response_model=TaskUpdateResponse,
    status_code=http_status.HTTP_200_OK,
    tags=["tasks"],
    responses={
        404: {"description": "Task not found"},
        500: {"description": "Internal server error"},
    },
)
async def update_task(task_id: str, request: UpdateTaskRequest) -> TaskUpdateResponse:
    """Update a task."""
    try:
        # Build update fields dictionary
        update_fields = {}
        if request.title is not None:
            update_fields["title"] = request.title
        if request.description is not None:
            update_fields["description"] = request.description
        if request.status is not None:
            update_fields["status"] = request.status
        if request.assignee is not None:
            update_fields["assignee"] = request.assignee
        if request.task_order is not None:
            update_fields["task_order"] = request.task_order
        if request.priority is not None:
            update_fields["priority"] = request.priority
        if request.feature is not None:
            update_fields["feature"] = request.feature

        # Use TaskService to update the task
        task_service = TaskService()
        success, result = await task_service.update_task(task_id, update_fields)

        if not success:
            if "not found" in result.get("error", "").lower():
                raise HTTPException(status_code=404, detail=result.get("error"))
            else:
                raise HTTPException(status_code=500, detail=result)

        updated_task = result["task"]

        logfire.info(
            f"Task updated successfully | task_id={task_id} | project_id={updated_task.get('project_id')} | updated_fields={list(update_fields.keys())}"
        )

        return {"message": "Task updated successfully", "task": updated_task}

    except HTTPException:
        raise
    except Exception as e:
        logfire.error(f"Failed to update task | error={str(e)} | task_id={task_id}")
        raise HTTPException(status_code=500, detail={"error": str(e)})


@router.delete(
    "/tasks/{task_id}",
    response_model=TaskDeleteResponse,
    status_code=http_status.HTTP_200_OK,
    tags=["tasks"],
    responses={
        404: {"description": "Task not found"},
        409: {"description": "Task already archived"},
        500: {"description": "Internal server error"},
    },
)
async def delete_task(task_id: str) -> TaskDeleteResponse:
    """Archive a task (soft delete)."""
    try:
        # Use TaskService to archive the task
        task_service = TaskService()
        success, result = await task_service.archive_task(task_id, archived_by="api")

        if not success:
            if "not found" in result.get("error", "").lower():
                raise HTTPException(status_code=404, detail=result.get("error"))
            elif "already archived" in result.get("error", "").lower():
                raise HTTPException(status_code=409, detail=result.get("error"))
            else:
                raise HTTPException(status_code=500, detail=result)

        logfire.info(f"Task archived successfully | task_id={task_id}")

        return {"message": result.get("message", "Task archived successfully")}

    except HTTPException:
        raise
    except Exception as e:
        logfire.error(f"Failed to archive task | error={str(e)} | task_id={task_id}")
        raise HTTPException(status_code=500, detail={"error": str(e)})


# MCP endpoints for task operations


@router.put(
    "/mcp/tasks/{task_id}/status",
    response_model=TaskUpdateResponse,
    status_code=http_status.HTTP_200_OK,
    tags=["tasks"],
    responses={
        404: {"description": "Task not found"},
        500: {"description": "Internal server error"},
    },
)
async def mcp_update_task_status(task_id: str, status: str) -> TaskUpdateResponse:
    """Update task status via MCP tools."""
    try:
        logfire.info(f"MCP task status update | task_id={task_id} | status={status}")

        # Use TaskService to update the task
        task_service = TaskService()
        success, result = await task_service.update_task(
            task_id=task_id, update_fields={"status": status}
        )

        if not success:
            if "not found" in result.get("error", "").lower():
                raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
            else:
                raise HTTPException(status_code=500, detail=result)

        updated_task = result["task"]
        project_id = updated_task["project_id"]

        logfire.info(
            f"Task status updated | task_id={task_id} | project_id={project_id} | status={status}"
        )

        return {"message": "Task status updated successfully", "task": updated_task}

    except HTTPException:
        raise
    except Exception as e:
        logfire.error(
            f"Failed to update task status | error={str(e)} | task_id={task_id}"
        )
        raise HTTPException(status_code=500, detail=str(e))


# Progress tracking via HTTP polling - see /api/progress endpoints

# ==================== DOCUMENT MANAGEMENT ENDPOINTS ====================


@router.get(
    "/projects/{project_id}/docs",
    status_code=http_status.HTTP_200_OK,
    responses={
        404: {"description": "Project not found"},
        500: {"description": "Internal server error"},
    },
)
async def list_project_documents(project_id: str, include_content: bool = False) -> dict[str, Any]:
    """
    List all documents for a specific project.
    
    Args:
        project_id: Project UUID
        include_content: If True, includes full document content.
                        If False (default), returns metadata only.
    """
    try:
        logfire.info(
            f"Listing documents for project | project_id={project_id} | include_content={include_content}"
        )

        # Use DocumentService to list documents
        document_service = DocumentService()
        success, result = document_service.list_documents(project_id, include_content=include_content)

        if not success:
            if "not found" in result.get("error", "").lower():
                raise HTTPException(status_code=404, detail=result.get("error"))
            else:
                raise HTTPException(status_code=500, detail=result)

        logfire.info(
            f"Documents listed successfully | project_id={project_id} | count={result.get('total_count', 0)} | lightweight={not include_content}"
        )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logfire.error(f"Failed to list documents | error={str(e)} | project_id={project_id}")
        raise HTTPException(status_code=500, detail={"error": str(e)})


@router.post(
    "/projects/{project_id}/docs",
    response_model=DocumentCreateResponse,
    status_code=http_status.HTTP_201_CREATED,
    responses={
        404: {"description": "Project not found"},
        400: {"description": "Invalid document data"},
        500: {"description": "Internal server error"},
    },
)
async def create_project_document(project_id: str, request: CreateDocumentRequest) -> DocumentCreateResponse:
    """Create a new document for a project."""
    try:
        logfire.info(
            f"Creating document for project | project_id={project_id} | title={request.title}"
        )

        # Use DocumentService to create document
        document_service = DocumentService()
        success, result = document_service.add_document(
            project_id=project_id,
            document_type=request.document_type,
            title=request.title,
            content=request.content,
            tags=request.tags,
            author=request.author,
        )

        if not success:
            if "not found" in result.get("error", "").lower():
                raise HTTPException(status_code=404, detail=result.get("error"))
            else:
                raise HTTPException(status_code=400, detail=result)

        logfire.info(
            f"Document created successfully | project_id={project_id} | doc_id={result['document']['id']}"
        )

        return {"message": "Document created successfully", "document": result["document"]}

    except HTTPException:
        raise
    except Exception as e:
        logfire.error(f"Failed to create document | error={str(e)} | project_id={project_id}")
        raise HTTPException(status_code=500, detail={"error": str(e)})


@router.get(
    "/projects/{project_id}/docs/{doc_id}",
    status_code=http_status.HTTP_200_OK,
    responses={
        404: {"description": "Document not found"},
        500: {"description": "Internal server error"},
    },
)
async def get_project_document(project_id: str, doc_id: str) -> dict[str, Any]:
    """Get a specific document from a project."""
    try:
        logfire.info(f"Getting document | project_id={project_id} | doc_id={doc_id}")

        # Use DocumentService to get document
        document_service = DocumentService()
        success, result = document_service.get_document(project_id, doc_id)

        if not success:
            if "not found" in result.get("error", "").lower():
                raise HTTPException(status_code=404, detail=result.get("error"))
            else:
                raise HTTPException(status_code=500, detail=result)

        logfire.info(f"Document retrieved successfully | project_id={project_id} | doc_id={doc_id}")

        return result["document"]

    except HTTPException:
        raise
    except Exception as e:
        logfire.error(
            f"Failed to get document | error={str(e)} | project_id={project_id} | doc_id={doc_id}"
        )
        raise HTTPException(status_code=500, detail={"error": str(e)})


@router.put(
    "/projects/{project_id}/docs/{doc_id}",
    response_model=DocumentUpdateResponse,
    status_code=http_status.HTTP_200_OK,
    responses={
        404: {"description": "Document not found"},
        500: {"description": "Internal server error"},
    },
)
async def update_project_document(project_id: str, doc_id: str, request: UpdateDocumentRequest) -> DocumentUpdateResponse:
    """Update a document in a project."""
    try:
        logfire.info(f"Updating document | project_id={project_id} | doc_id={doc_id}")

        # Build update fields
        update_fields = {}
        if request.title is not None:
            update_fields["title"] = request.title
        if request.content is not None:
            update_fields["content"] = request.content
        if request.tags is not None:
            update_fields["tags"] = request.tags
        if request.author is not None:
            update_fields["author"] = request.author

        # Use DocumentService to update document
        document_service = DocumentService()
        success, result = document_service.update_document(project_id, doc_id, update_fields)

        if not success:
            if "not found" in result.get("error", "").lower():
                raise HTTPException(status_code=404, detail=result.get("error"))
            else:
                raise HTTPException(status_code=500, detail=result)

        logfire.info(f"Document updated successfully | project_id={project_id} | doc_id={doc_id}")

        return {"message": "Document updated successfully", "document": result["document"]}

    except HTTPException:
        raise
    except Exception as e:
        logfire.error(
            f"Failed to update document | error={str(e)} | project_id={project_id} | doc_id={doc_id}"
        )
        raise HTTPException(status_code=500, detail={"error": str(e)})


@router.delete(
    "/projects/{project_id}/docs/{doc_id}",
    response_model=DocumentDeleteResponse,
    status_code=http_status.HTTP_200_OK,
    responses={
        404: {"description": "Document not found"},
        500: {"description": "Internal server error"},
    },
)
async def delete_project_document(project_id: str, doc_id: str) -> DocumentDeleteResponse:
    """Delete a document from a project."""
    try:
        logfire.info(f"Deleting document | project_id={project_id} | doc_id={doc_id}")

        # Use DocumentService to delete document
        document_service = DocumentService()
        success, result = document_service.delete_document(project_id, doc_id)

        if not success:
            if "not found" in result.get("error", "").lower():
                raise HTTPException(status_code=404, detail=result.get("error"))
            else:
                raise HTTPException(status_code=500, detail=result)

        logfire.info(f"Document deleted successfully | project_id={project_id} | doc_id={doc_id}")

        return {"message": "Document deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logfire.error(
            f"Failed to delete document | error={str(e)} | project_id={project_id} | doc_id={doc_id}"
        )
        raise HTTPException(status_code=500, detail={"error": str(e)})


# ==================== VERSION MANAGEMENT ENDPOINTS ====================


@router.get(
    "/projects/{project_id}/versions",
    status_code=http_status.HTTP_200_OK,
    responses={
        404: {"description": "Project not found"},
        500: {"description": "Internal server error"},
    },
)
async def list_project_versions(project_id: str, field_name: str = None) -> dict[str, Any]:
    """List version history for a project's JSONB fields."""
    try:
        logfire.info(
            f"Listing versions for project | project_id={project_id} | field_name={field_name}"
        )

        # Use VersioningService to list versions
        versioning_service = VersioningService()
        success, result = versioning_service.list_versions(project_id, field_name)

        if not success:
            if "not found" in result.get("error", "").lower():
                raise HTTPException(status_code=404, detail=result.get("error"))
            else:
                raise HTTPException(status_code=500, detail=result)

        logfire.info(
            f"Versions listed successfully | project_id={project_id} | count={result.get('total_count', 0)}"
        )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logfire.error(f"Failed to list versions | error={str(e)} | project_id={project_id}")
        raise HTTPException(status_code=500, detail={"error": str(e)})


@router.post(
    "/projects/{project_id}/versions",
    response_model=VersionCreateResponse,
    status_code=http_status.HTTP_201_CREATED,
    responses={
        404: {"description": "Project not found"},
        400: {"description": "Invalid version data"},
        500: {"description": "Internal server error"},
    },
)
async def create_project_version(project_id: str, request: CreateVersionRequest) -> VersionCreateResponse:
    """Create a version snapshot for a project's JSONB field."""
    try:
        logfire.info(
            f"Creating version for project | project_id={project_id} | field_name={request.field_name}"
        )

        # Use VersioningService to create version
        versioning_service = VersioningService()
        success, result = versioning_service.create_version(
            project_id=project_id,
            field_name=request.field_name,
            content=request.content,
            change_summary=request.change_summary,
            change_type=request.change_type,
            document_id=request.document_id,
            created_by=request.created_by,
        )

        if not success:
            if "not found" in result.get("error", "").lower():
                raise HTTPException(status_code=404, detail=result.get("error"))
            else:
                raise HTTPException(status_code=400, detail=result)

        logfire.info(
            f"Version created successfully | project_id={project_id} | version_number={result['version_number']}"
        )

        return {"message": "Version created successfully", "version": result["version"]}

    except HTTPException:
        raise
    except Exception as e:
        logfire.error(f"Failed to create version | error={str(e)} | project_id={project_id}")
        raise HTTPException(status_code=500, detail={"error": str(e)})


@router.get(
    "/projects/{project_id}/versions/{field_name}/{version_number}",
    status_code=http_status.HTTP_200_OK,
    responses={
        404: {"description": "Version not found"},
        500: {"description": "Internal server error"},
    },
)
async def get_project_version(project_id: str, field_name: str, version_number: int) -> dict[str, Any]:
    """Get a specific version's content."""
    try:
        logfire.info(
            f"Getting version | project_id={project_id} | field_name={field_name} | version_number={version_number}"
        )

        # Use VersioningService to get version content
        versioning_service = VersioningService()
        success, result = versioning_service.get_version_content(
            project_id, field_name, version_number
        )

        if not success:
            if "not found" in result.get("error", "").lower():
                raise HTTPException(status_code=404, detail=result.get("error"))
            else:
                raise HTTPException(status_code=500, detail=result)

        logfire.info(
            f"Version retrieved successfully | project_id={project_id} | field_name={field_name} | version_number={version_number}"
        )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logfire.error(
            f"Failed to get version | error={str(e)} | project_id={project_id} | field_name={field_name} | version_number={version_number}"
        )
        raise HTTPException(status_code=500, detail={"error": str(e)})


@router.post(
    "/projects/{project_id}/versions/{field_name}/{version_number}/restore",
    response_model=VersionRestoreResponse,
    status_code=http_status.HTTP_200_OK,
    responses={
        404: {"description": "Version not found"},
        500: {"description": "Internal server error"},
    },
)
async def restore_project_version(
    project_id: str, field_name: str, version_number: int, request: RestoreVersionRequest
) -> VersionRestoreResponse:
    """Restore a project's JSONB field to a specific version."""
    try:
        logfire.info(
            f"Restoring version | project_id={project_id} | field_name={field_name} | version_number={version_number}"
        )

        # Use VersioningService to restore version
        versioning_service = VersioningService()
        success, result = versioning_service.restore_version(
            project_id=project_id,
            field_name=field_name,
            version_number=version_number,
            restored_by=request.restored_by,
        )

        if not success:
            if "not found" in result.get("error", "").lower():
                raise HTTPException(status_code=404, detail=result.get("error"))
            else:
                raise HTTPException(status_code=500, detail=result)

        logfire.info(
            f"Version restored successfully | project_id={project_id} | field_name={field_name} | version_number={version_number}"
        )

        return {
            "message": f"Successfully restored {field_name} to version {version_number}",
            **result,
        }

    except HTTPException:
        raise
    except Exception as e:
        logfire.error(
            f"Failed to restore version | error={str(e)} | project_id={project_id} | field_name={field_name} | version_number={version_number}"
        )
        raise HTTPException(status_code=500, detail={"error": str(e)})


# ==================== PROJECT KNOWLEDGE SOURCES ENDPOINT ====================


@router.get("/projects/{project_id}/knowledge-sources")
async def get_project_knowledge_sources(
    project_id: str,
    page: int = 1,
    per_page: int = 20,
    knowledge_type: str | None = None,
    search: str | None = None,
):
    """Get knowledge sources associated with a project via metadata.project_id."""
    try:
        page = max(1, page)
        per_page = min(100, max(1, per_page))

        service = KnowledgeSummaryService(get_supabase_client())
        return await service.get_summaries(
            page=page,
            per_page=per_page,
            knowledge_type=knowledge_type,
            search=search,
            project_id=project_id,
        )

    except HTTPException:
        raise
    except Exception as e:
        logfire.error(
            f"Failed to get project knowledge sources | error={str(e)} | project_id={project_id}"
        )
        raise HTTPException(status_code=500, detail={"error": str(e)})


# ==================== GIT STATUS ENDPOINT ====================


@router.put("/projects/{project_id}/systems/{system_id}/git-status")
async def update_git_status(project_id: str, system_id: str, request: Request):
    """Update git dirty status for a project-system registration."""
    body = await request.json()
    git_dirty = body.get("git_dirty", False)

    project_service = ProjectService(get_supabase_client())
    success, result = project_service.update_git_status(project_id, system_id, git_dirty)

    if not success:
        raise HTTPException(status_code=404, detail=result.get("error"))

    return {"success": True, "git_dirty": git_dirty}
