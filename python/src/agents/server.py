"""
Agents Service - Lightweight FastAPI server for PydanticAI agents

This service ONLY hosts PydanticAI agents. It does NOT contain:
- ML models or embeddings (those are in Server)
- Direct database access (use MCP tools)
- Business logic (that's in Server)

The agents use MCP tools for all data operations.
"""

import asyncio
import json
import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, TextPart, UserPromptPart

# Import our PydanticAI agents
from .chat_agent import ChatDependencies, create_chat_agent
from .document_agent import DocumentAgent
from .rag_agent import RagAgent

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Request/Response models
class AgentRequest(BaseModel):
    """Request model for agent interactions"""

    agent_type: str  # "document", "rag", etc.
    prompt: str
    context: dict[str, Any] | None = None
    options: dict[str, Any] | None = None


class AgentResponse(BaseModel):
    """Response model for agent interactions"""

    success: bool
    result: Any | None = None
    error: str | None = None
    metadata: dict[str, Any] | None = None


# Agent registry
AVAILABLE_AGENTS = {
    "document": DocumentAgent,
    "rag": RagAgent,
}

# Global credentials storage
AGENT_CREDENTIALS = {}


async def fetch_credentials_from_server():
    """Fetch credentials from the server's internal API."""
    max_retries = 30  # Try for up to 5 minutes (30 * 10 seconds)
    retry_delay = 10  # seconds

    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient() as client:
                # Call the server's internal credentials endpoint
                server_port = os.getenv("CORTEX_SERVER_PORT")
                if not server_port:
                    raise ValueError(
                        "CORTEX_SERVER_PORT environment variable is required. "
                        "Please set it in your .env file or environment."
                    )
                response = await client.get(
                    f"http://cortex-server:{server_port}/internal/credentials/agents", timeout=10.0
                )
                response.raise_for_status()
                credentials = response.json()

                # Set credentials as environment variables
                for key, value in credentials.items():
                    if value is not None:
                        os.environ[key] = str(value)
                        logger.info(f"Set credential: {key}")

                # Store credentials globally for agent initialization
                global AGENT_CREDENTIALS
                AGENT_CREDENTIALS = credentials

                logger.info(f"Successfully fetched {len(credentials)} credentials from server")
                return credentials

        except (httpx.HTTPError, httpx.RequestError) as e:
            if attempt < max_retries - 1:
                logger.warning(
                    f"Failed to fetch credentials (attempt {attempt + 1}/{max_retries}): {e}"
                )
                logger.info(f"Retrying in {retry_delay} seconds...")
                await asyncio.sleep(retry_delay)
            else:
                logger.error(f"Failed to fetch credentials after {max_retries} attempts")
                raise Exception("Could not fetch credentials from server")


# Lifespan context manager
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and cleanup resources"""
    logger.info("Starting Agents service...")

    # Fetch credentials from server first
    try:
        await fetch_credentials_from_server()
    except Exception as e:
        logger.error(f"Failed to fetch credentials: {e}")
        # Continue with defaults if we can't get credentials

    # Initialize agents with fetched credentials
    app.state.agents = {}
    for name, agent_class in AVAILABLE_AGENTS.items():
        try:
            # Pass model configuration from credentials
            model_key = f"{name.upper()}_AGENT_MODEL"
            model = AGENT_CREDENTIALS.get(model_key, "openai:gpt-4o-mini")

            app.state.agents[name] = agent_class(model=model)
            logger.info(f"Initialized {name} agent with model: {model}")
        except Exception as e:
            logger.error(f"Failed to initialize {name} agent: {e}")

    yield

    # Cleanup
    logger.info("Shutting down Agents service...")


# Create FastAPI app
app = FastAPI(
    title="Cortex Agents Service",
    description="Lightweight service hosting PydanticAI agents",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "agents",
        "agents_available": list(AVAILABLE_AGENTS.keys()),
        "note": "This service only hosts PydanticAI agents",
    }


@app.post("/agents/run", response_model=AgentResponse)
async def run_agent(request: AgentRequest):
    """
    Run a specific agent with the given prompt.

    The agent will use MCP tools for any data operations.
    """
    try:
        # Get the requested agent
        if request.agent_type not in app.state.agents:
            raise HTTPException(status_code=400, detail=f"Unknown agent type: {request.agent_type}")

        agent = app.state.agents[request.agent_type]

        # Prepare dependencies for the agent
        deps = {
            "context": request.context or {},
            "options": request.options or {},
            "mcp_endpoint": os.getenv("MCP_SERVICE_URL", "http://cortex-mcp:8051"),
        }

        # Run the agent
        result = await agent.run(request.prompt, deps)

        return AgentResponse(
            success=True,
            result=result,
            metadata={"agent_type": request.agent_type, "model": agent.model},
        )

    except Exception as e:
        logger.error(f"Error running {request.agent_type} agent: {e}")
        return AgentResponse(success=False, error=str(e))


@app.get("/agents/list")
async def list_agents():
    """List all available agents and their capabilities"""
    agents_info = {}

    for name, agent in app.state.agents.items():
        agents_info[name] = {
            "name": agent.name,
            "model": agent.model,
            "description": agent.__class__.__doc__ or "No description available",
            "available": True,
        }

    return {"agents": agents_info, "total": len(agents_info)}


# IMPORTANT: Chat stream must be declared BEFORE the generic /agents/{agent_type}/stream
# route, otherwise FastAPI matches {agent_type}="chat" and validates against AgentRequest.
@app.post("/agents/chat/stream")
async def stream_chat(request: Request):
    """SSE streaming endpoint for the chat interface.

    Receives the user message, persists it via Main Server, runs the ChatAgent
    with streaming, and emits SSE events (message_start, text_delta,
    message_complete, error, heartbeat).
    """
    body = await request.json()
    conversation_id = body.get("conversation_id", "")
    message = body.get("message") or body.get("content", "")
    user_profile = body.get("user_profile", {})
    project_id = body.get("project_id")
    action_mode = body.get("action_mode", False)
    model = body.get("model", "openai:gpt-4o")
    conversation_history = body.get("conversation_history", [])

    # In Docker compose, use the service name; locally, use CORTEX_HOST.
    is_docker = os.path.exists("/.dockerenv")
    cortex_host = os.environ.get("CORTEX_HOST", "localhost")
    server_port = os.environ.get("CORTEX_SERVER_PORT", "8181")
    default_api_url = f"http://cortex-server:{server_port}" if is_docker else f"http://{cortex_host}:{server_port}"
    api_url = os.environ.get("CORTEX_API_URL", default_api_url)

    # Persist the user message via Main Server REST API (skip if no conversation)
    if conversation_id:
        async with httpx.AsyncClient(timeout=30) as http_client:
            await http_client.post(
                f"{api_url}/api/chat/conversations/{conversation_id}/messages",
                json={"role": "user", "content": message},
            )

    # Build ChatDependencies for this request
    deps = ChatDependencies(
        conversation_id=conversation_id,
        project_id=project_id,
        user_profile=user_profile,
        action_mode=action_mode,
        model_override=model,
        conversation_history=conversation_history,
    )

    agent = create_chat_agent(model=model)

    # Convert conversation history into PydanticAI message objects (last 20 messages).
    # TODO: Replace fixed-window truncation with SynthesizerAgent that summarizes older
    # messages into a compressed context block, preserving key decisions and facts while
    # staying within the model's context window budget.
    pydantic_messages: list[ModelMessage] = []
    for msg in conversation_history[-20:]:
        if msg.get("role") == "user":
            pydantic_messages.append(ModelRequest(parts=[UserPromptPart(content=msg["content"])]))
        elif msg.get("role") == "assistant":
            pydantic_messages.append(ModelResponse(parts=[TextPart(content=msg["content"])]))

    async def generate() -> AsyncGenerator[str, None]:
        try:
            yield f"data: {json.dumps({'type': 'message_start', 'conversation_id': conversation_id})}\n\n"

            full_content = ""
            last_heartbeat = asyncio.get_event_loop().time()

            async with agent.run_stream(
                message, deps=deps, message_history=pydantic_messages
            ) as stream:
                async for chunk in stream.stream_text(delta=True):
                    full_content += chunk
                    yield f"data: {json.dumps({'type': 'text_delta', 'delta': chunk})}\n\n"

                    # Emit heartbeat comment every 15 seconds during long-running streams
                    now = asyncio.get_event_loop().time()
                    if now - last_heartbeat > 15:
                        yield ": heartbeat\n\n"
                        last_heartbeat = now

            # Persist the assistant message via Main Server
            saved_msg: dict = {}
            if conversation_id:
                async with httpx.AsyncClient(timeout=30) as http_client:
                    save_response = await http_client.post(
                        f"{api_url}/api/chat/conversations/{conversation_id}/messages",
                        json={
                            "role": "assistant",
                            "content": full_content,
                            "model_used": model,
                        },
                    )
                    save_data = save_response.json()
                    saved_msg = save_data.get("message", {})

            # Auto-generate conversation title from the first exchange
            if conversation_id and len(conversation_history) == 0:
                try:
                    title_prompt = (
                        f"Generate a short title (max 6 words) for a conversation that starts with: "
                        f"{message[:200]}"
                    )
                    title_agent = create_chat_agent(model=model)
                    title_result = await title_agent.run(title_prompt, deps=deps)
                    title = title_result.data.strip('"').strip()[:100]
                    async with httpx.AsyncClient(timeout=10) as http_client:
                        await http_client.patch(
                            f"{api_url}/api/chat/conversations/{conversation_id}",
                            json={"title": title},
                        )
                except Exception as title_err:
                    logger.warning(f"Failed to auto-generate conversation title: {title_err}")

            yield f"data: {json.dumps({'type': 'message_complete', 'message_id': saved_msg.get('id', ''), 'model_used': model, 'persisted': True})}\n\n"

        except Exception as e:
            logger.error(f"Chat stream error: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'error': str(e), 'retryable': True})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/agents/{agent_type}/stream")
async def stream_agent(agent_type: str, request: AgentRequest):
    """
    Stream responses from an agent using Server-Sent Events (SSE).

    This endpoint streams the agent's response in real-time, allowing
    for a more interactive experience.
    """
    # Get the requested agent
    if agent_type not in app.state.agents:
        raise HTTPException(status_code=400, detail=f"Unknown agent type: {agent_type}")

    agent = app.state.agents[agent_type]

    async def generate() -> AsyncGenerator[str, None]:
        try:
            # Prepare dependencies based on agent type
            # Import dependency classes
            if agent_type == "rag":
                from .rag_agent import RagDependencies

                deps = RagDependencies(
                    source_filter=request.context.get("source_filter") if request.context else None,
                    match_count=request.context.get("match_count", 5) if request.context else 5,
                    project_id=request.context.get("project_id") if request.context else None,
                )
            elif agent_type == "document":
                from .document_agent import DocumentDependencies

                deps = DocumentDependencies(
                    project_id=request.context.get("project_id") if request.context else None,
                    user_id=request.context.get("user_id") if request.context else None,
                )
            else:
                # Default dependencies
                from .base_agent import CortexDependencies

                deps = CortexDependencies()

            # Use PydanticAI's run_stream method
            # run_stream returns an async context manager directly
            async with agent.run_stream(request.prompt, deps) as stream:
                # Stream text chunks as they arrive
                async for chunk in stream.stream_text():
                    event_data = json.dumps({"type": "stream_chunk", "content": chunk})
                    yield f"data: {event_data}\n\n"

                # Get the final structured result
                try:
                    final_result = await stream.get_data()
                    event_data = json.dumps({"type": "stream_complete", "content": final_result})
                    yield f"data: {event_data}\n\n"
                except Exception:
                    # If we can't get structured data, just send completion
                    event_data = json.dumps({"type": "stream_complete", "content": ""})
                    yield f"data: {event_data}\n\n"

        except Exception as e:
            logger.error(f"Error streaming {agent_type} agent: {e}")
            event_data = json.dumps({"type": "error", "error": str(e)})
            yield f"data: {event_data}\n\n"

    # Return SSE response
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable Nginx buffering
        },
    )


# Main entry point
if __name__ == "__main__":
    agents_port = os.getenv("CORTEX_AGENTS_PORT")
    if not agents_port:
        raise ValueError(
            "CORTEX_AGENTS_PORT environment variable is required. "
            "Please set it in your .env file or environment. "
            "Default value: 8052"
        )
    port = int(agents_port)

    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=port,
        log_level="info",
        reload=False,  # Disable reload in production
    )
