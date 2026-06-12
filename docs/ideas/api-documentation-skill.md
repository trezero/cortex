# Idea: API Documentation Enforcement Skill

## Problem

As Cortex grows, API endpoints are created with varying levels of documentation. FastAPI auto-generates OpenAPI docs at `/docs` and `/redoc`, but the quality depends on how thoroughly each endpoint is annotated. There's no enforcement or consistency check.

## Concept

A Claude Code skill that ensures every API endpoint is fully documented as it's created, and catches gaps in existing endpoints.

## Two Modes

### Template-driven creation (primary)
When creating new endpoints, the skill provides the full boilerplate with documentation baked in:
- Route decorator with `response_model`, `description`, `tags`, `status_code`
- Pydantic request/response models with field descriptions and examples
- Service call pattern following existing conventions
- Error handling with proper HTTP status codes

### Post-coding review (safety net)
After implementation work, scans `python/src/server/api_routes/` for new/modified endpoints and checks each has:
- `response_model` defined
- `description` or docstring
- `tags` for grouping in Swagger UI
- Explicit `status_code`
- Pydantic models with field-level descriptions
- Response examples where helpful

Flags gaps or auto-fills them.

## Integration Points

- **Postman skill** — could consume the OpenAPI spec to keep Postman collections in sync automatically
- **MCP tools** — MCP tool definitions in `python/src/mcp_server/features/` should mirror the REST API docs
- **Frontend services** — TypeScript types in `features/*/types/` should stay aligned with backend response models

## Brainstorming Prompt

```
I want to create a Claude Code skill that enforces API documentation for FastAPI endpoints in the Cortex project. Read the idea at docs/ideas/api-documentation-skill.md, then use /brainstorm to design it. Key considerations:

1. The skill should work in two modes: template-driven creation (when building new endpoints) and post-coding review (scanning for documentation gaps)
2. It should leverage FastAPI's built-in OpenAPI generation — the goal is to ensure the auto-generated docs are high quality, not to create a parallel documentation system
3. Look at existing endpoints in python/src/server/api_routes/ to understand current documentation levels and patterns
4. Consider integration with the existing Postman skill
5. Keep it simple — this is a developer workflow tool, not a documentation platform
```

## Status

Idea only — not yet brainstormed or specced.
