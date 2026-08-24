"""
Settings API endpoints for Cortex

Handles:
- OpenAI API key management
- Other credentials and configuration
- Settings storage and retrieval
"""

import re
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# Import logging
from ..config.logfire_config import logfire
from ..services.credential_service import credential_service, initialize_credentials
from ..utils import get_supabase_client

router = APIRouter(prefix="/api", tags=["settings"])


class CredentialRequest(BaseModel):
    key: str
    value: str
    is_encrypted: bool = False
    category: str | None = None
    description: str | None = None


class CredentialUpdateRequest(BaseModel):
    value: str
    is_encrypted: bool | None = None
    category: str | None = None
    description: str | None = None


class CredentialResponse(BaseModel):
    success: bool
    message: str


# Credential Management Endpoints
@router.get("/credentials")
async def list_credentials(category: str | None = None):
    """List all credentials and their categories."""
    try:
        logfire.info(f"Listing credentials | category={category}")
        credentials = await credential_service.list_all_credentials()

        if category:
            # Filter by category
            credentials = [cred for cred in credentials if cred.category == category]

        result_count = len(credentials)
        logfire.info(
            f"Credentials listed successfully | count={result_count} | category={category}"
        )

        return [
            {
                "key": cred.key,
                "value": cred.value,
                "encrypted_value": cred.encrypted_value,
                "is_encrypted": cred.is_encrypted,
                "category": cred.category,
                "description": cred.description,
            }
            for cred in credentials
        ]
    except Exception as e:
        logfire.error(f"Error listing credentials | category={category} | error={str(e)}")
        raise HTTPException(status_code=500, detail={"error": str(e)})


@router.get("/credentials/categories/{category}")
async def get_credentials_by_category(category: str):
    """Get all credentials for a specific category."""
    try:
        logfire.info(f"Getting credentials by category | category={category}")
        credentials = await credential_service.get_credentials_by_category(category)

        logfire.info(
            f"Credentials retrieved by category | category={category} | count={len(credentials)}"
        )

        return {"credentials": credentials}
    except Exception as e:
        logfire.error(
            f"Error getting credentials by category | category={category} | error={str(e)}"
        )
        raise HTTPException(status_code=500, detail={"error": str(e)})


@router.post("/credentials")
async def create_credential(request: CredentialRequest):
    """Create or update a credential."""
    try:
        logfire.info(
            f"Creating/updating credential | key={request.key} | is_encrypted={request.is_encrypted} | category={request.category}"
        )

        success = await credential_service.set_credential(
            key=request.key,
            value=request.value,
            is_encrypted=request.is_encrypted,
            category=request.category,
            description=request.description,
        )

        if success:
            logfire.info(
                f"Credential saved successfully | key={request.key} | is_encrypted={request.is_encrypted}"
            )

            return {
                "success": True,
                "message": f"Credential {request.key} {'encrypted and ' if request.is_encrypted else ''}saved successfully",
            }
        else:
            logfire.error(f"Failed to save credential | key={request.key}")
            raise HTTPException(status_code=500, detail={"error": "Failed to save credential"})

    except Exception as e:
        logfire.error(f"Error creating credential | key={request.key} | error={str(e)}")
        raise HTTPException(status_code=500, detail={"error": str(e)})


# Define optional settings with their default values
# These are user preferences that should return defaults instead of 404
# This prevents console errors in the frontend when settings haven't been explicitly set
# The frontend can check the 'is_default' flag to know if it's a default or user-set value
OPTIONAL_SETTINGS_WITH_DEFAULTS = {
    "DISCONNECT_SCREEN_ENABLED": "true",  # Show disconnect screen when server is unavailable
    "PROJECTS_ENABLED": "false",  # Enable project management features
    "LOGFIRE_ENABLED": "false",  # Enable Pydantic Logfire integration
    "POSTMAN_SYNC_MODE": "disabled",  # Postman integration mode: api, git, or disabled
}

# Browser clients may manage non-secret application preferences, but they never
# receive or mutate provider keys, tokens, passwords, or encrypted records.
SAFE_PREFERENCE_CATEGORIES = {
    "features",
    "monitoring",
    "rag_strategy",
    "code_extraction",
    "ollama_instances",
}
SAFE_PREFERENCE_KEYS = {
    # Browser feature toggles
    "DISCONNECT_SCREEN_ENABLED": "features",
    "PROJECTS_ENABLED": "features",
    "STYLE_GUIDE_ENABLED": "features",
    "AGENT_WORK_ORDERS_ENABLED": "features",
    "POSTMAN_SYNC_MODE": "features",
    "LOGFIRE_ENABLED": "monitoring",
    # RAG/provider preferences (never provider credentials)
    "USE_CONTEXTUAL_EMBEDDINGS": "rag_strategy",
    "CONTEXTUAL_EMBEDDINGS_MAX_WORKERS": "rag_strategy",
    "USE_HYBRID_SEARCH": "rag_strategy",
    "USE_AGENTIC_RAG": "rag_strategy",
    "USE_RERANKING": "rag_strategy",
    "MODEL_CHOICE": "rag_strategy",
    "LLM_PROVIDER": "rag_strategy",
    "LLM_BASE_URL": "rag_strategy",
    "LLM_INSTANCE_NAME": "rag_strategy",
    "OLLAMA_EMBEDDING_URL": "rag_strategy",
    "OLLAMA_EMBEDDING_INSTANCE_NAME": "rag_strategy",
    "EMBEDDING_MODEL": "rag_strategy",
    "EMBEDDING_PROVIDER": "rag_strategy",
    "CRAWL_BATCH_SIZE": "rag_strategy",
    "CRAWL_MAX_CONCURRENT": "rag_strategy",
    "CRAWL_WAIT_STRATEGY": "rag_strategy",
    "CRAWL_PAGE_TIMEOUT": "rag_strategy",
    "CRAWL_DELAY_BEFORE_HTML": "rag_strategy",
    "DOCUMENT_STORAGE_BATCH_SIZE": "rag_strategy",
    "EMBEDDING_BATCH_SIZE": "rag_strategy",
    "DELETE_BATCH_SIZE": "rag_strategy",
    "ENABLE_PARALLEL_BATCHES": "rag_strategy",
    "MEMORY_THRESHOLD_PERCENT": "rag_strategy",
    "DISPATCHER_CHECK_INTERVAL": "rag_strategy",
    "CODE_EXTRACTION_BATCH_SIZE": "rag_strategy",
    "CODE_SUMMARY_MAX_WORKERS": "rag_strategy",
    # Code extraction preferences
    "MIN_CODE_BLOCK_LENGTH": "code_extraction",
    "MAX_CODE_BLOCK_LENGTH": "code_extraction",
    "ENABLE_COMPLETE_BLOCK_DETECTION": "code_extraction",
    "ENABLE_LANGUAGE_SPECIFIC_PATTERNS": "code_extraction",
    "ENABLE_PROSE_FILTERING": "code_extraction",
    "MAX_PROSE_RATIO": "code_extraction",
    "MIN_CODE_INDICATORS": "code_extraction",
    "ENABLE_DIAGRAM_FILTERING": "code_extraction",
    "ENABLE_CONTEXTUAL_LENGTH": "code_extraction",
    "CODE_EXTRACTION_MAX_WORKERS": "code_extraction",
    "CONTEXT_WINDOW_SIZE": "code_extraction",
    "ENABLE_CODE_SUMMARIES": "code_extraction",
}
OLLAMA_PREFERENCE_KEY = re.compile(
    r"^ollama_instance_[A-Za-z0-9_-]+_"
    r"(name|baseUrl|isEnabled|isPrimary|instanceType|loadBalancingWeight|"
    r"isHealthy|responseTimeMs|modelsAvailable|lastHealthCheck)$"
)
PROVIDER_CREDENTIAL_STATUS_KEYS = {
    "ANTHROPIC_API_KEY",
    "GOOGLE_API_KEY",
    "GROK_API_KEY",
    "OPENAI_API_KEY",
    "OPENROUTER_API_KEY",
}


def _serialize_preference(credential) -> dict[str, Any]:
    return {
        "key": credential.key,
        "value": credential.value,
        "is_encrypted": False,
        "category": credential.category,
        "description": credential.description,
    }


def _is_safe_preference_key(key: str, category: str | None) -> bool:
    expected_category = SAFE_PREFERENCE_KEYS.get(key)
    if expected_category is not None:
        return category == expected_category
    return category == "ollama_instances" and OLLAMA_PREFERENCE_KEY.fullmatch(key) is not None


def _require_safe_preference_key(key: str, category: str | None) -> None:
    if not _is_safe_preference_key(key, category):
        raise HTTPException(status_code=400, detail={"error": "Unsupported preference key"})


async def _find_safe_preference(key: str):
    credentials = await credential_service.list_all_credentials()
    credential = next((item for item in credentials if item.key == key), None)
    if credential is None:
        return None
    if credential.is_encrypted or not _is_safe_preference_key(
        credential.key, credential.category
    ):
        raise HTTPException(status_code=404, detail={"error": f"Preference {key} not found"})
    return credential


@router.get("/preferences")
async def list_preferences(category: str | None = None):
    """List browser-safe, non-secret preferences only."""
    if category is not None and category not in SAFE_PREFERENCE_CATEGORIES:
        raise HTTPException(status_code=400, detail={"error": "Unsupported preference category"})
    credentials = await credential_service.list_all_credentials()
    return [
        _serialize_preference(credential)
        for credential in credentials
        if not credential.is_encrypted
        and _is_safe_preference_key(credential.key, credential.category)
        and (category is None or credential.category == category)
    ]


@router.get("/preferences/categories/{category}")
async def get_preferences_by_category(category: str):
    """Return one allowlisted category without exposing encrypted records."""
    if category not in SAFE_PREFERENCE_CATEGORIES:
        raise HTTPException(status_code=400, detail={"error": "Unsupported preference category"})
    return {"preferences": await list_preferences(category)}


@router.post("/preferences/secret-status")
async def browser_secret_status(request: dict[str, list[str]]):
    """Return presence booleans for the fixed provider-key set, never values."""
    requested = request.get("keys", [])
    if any(key not in PROVIDER_CREDENTIAL_STATUS_KEYS for key in requested):
        raise HTTPException(status_code=400, detail={"error": "Unsupported credential status key"})
    result = {}
    for key in requested:
        value = await credential_service.get_credential(key, decrypt=True)
        result[key] = {"key": key, "has_value": bool(str(value).strip()) if value else False}
    return result


@router.get("/preferences/{key}")
async def get_preference(key: str):
    """Return one non-secret preference or its documented default."""
    credential = await _find_safe_preference(key)
    if credential is not None:
        return _serialize_preference(credential)
    if key in OPTIONAL_SETTINGS_WITH_DEFAULTS:
        return {
            "key": key,
            "value": OPTIONAL_SETTINGS_WITH_DEFAULTS[key],
            "is_default": True,
            "is_encrypted": False,
            "category": "features",
            "description": f"Default value for {key}",
        }
    raise HTTPException(status_code=404, detail={"error": f"Preference {key} not found"})


@router.post("/preferences")
async def create_preference(request: CredentialRequest):
    """Create a non-secret preference in an allowlisted category."""
    if request.is_encrypted:
        raise HTTPException(status_code=400, detail={"error": "Secrets are managed in 1Password"})
    _require_safe_preference_key(request.key, request.category)
    success = await credential_service.set_credential(
        key=request.key,
        value=request.value,
        is_encrypted=False,
        category=request.category,
        description=request.description,
    )
    if not success:
        raise HTTPException(status_code=500, detail={"error": "Failed to save preference"})
    return {"success": True, "message": f"Preference {request.key} saved successfully"}


@router.put("/preferences/{key}")
async def update_preference(key: str, request: dict[str, Any]):
    """Update or create a non-secret preference without opening credential routes."""
    if request.get("is_encrypted"):
        raise HTTPException(status_code=400, detail={"error": "Secrets are managed in 1Password"})
    category = request.get("category")
    if category is not None:
        _require_safe_preference_key(key, category)
    existing = await _find_safe_preference(key)
    if existing is not None and category is None:
        category = existing.category
    _require_safe_preference_key(key, category)
    success = await credential_service.set_credential(
        key=key,
        value=str(request.get("value", "")),
        is_encrypted=False,
        category=category,
        description=request.get("description"),
    )
    if not success:
        raise HTTPException(status_code=500, detail={"error": "Failed to save preference"})
    return {"success": True, "message": f"Preference {key} saved successfully"}


@router.delete("/preferences/{key}")
async def delete_preference(key: str):
    """Delete a record only after proving it is a browser-safe preference."""
    credential = await _find_safe_preference(key)
    if credential is None:
        raise HTTPException(status_code=404, detail={"error": f"Preference {key} not found"})
    if not await credential_service.delete_credential(key):
        raise HTTPException(status_code=500, detail={"error": "Failed to delete preference"})
    return {"success": True, "message": f"Preference {key} deleted successfully"}


@router.get("/credentials/{key}")
async def get_credential(key: str):
    """Get a specific credential by key."""
    try:
        logfire.info(f"Getting credential | key={key}")
        # Never decrypt - always get metadata only for encrypted credentials
        value = await credential_service.get_credential(key, decrypt=False)

        if value is None:
            # Check if this is an optional setting with a default value
            if key in OPTIONAL_SETTINGS_WITH_DEFAULTS:
                logfire.info(f"Returning default value for optional setting | key={key}")
                return {
                    "key": key,
                    "value": OPTIONAL_SETTINGS_WITH_DEFAULTS[key],
                    "is_default": True,
                    "category": "features",
                    "description": f"Default value for {key}",
                }

            logfire.warning(f"Credential not found | key={key}")
            raise HTTPException(status_code=404, detail={"error": f"Credential {key} not found"})

        logfire.info(f"Credential retrieved successfully | key={key}")

        if isinstance(value, dict) and value.get("is_encrypted"):
            return {
                "key": key,
                "value": "[ENCRYPTED]",
                "is_encrypted": True,
                "category": value.get("category"),
                "description": value.get("description"),
                "has_value": bool(value.get("encrypted_value")),
            }

        # For non-encrypted credentials, return the actual value
        return {"key": key, "value": value, "is_encrypted": False}

    except HTTPException:
        raise
    except Exception as e:
        logfire.error(f"Error getting credential | key={key} | error={str(e)}")
        raise HTTPException(status_code=500, detail={"error": str(e)})


@router.put("/credentials/{key}")
async def update_credential(key: str, request: dict[str, Any]):
    """Update an existing credential."""
    try:
        logfire.info(f"Updating credential | key={key}")

        # Handle both CredentialUpdateRequest and full Credential object formats
        if isinstance(request, dict):
            # If the request contains a 'value' field directly, use it
            value = request.get("value", "")
            is_encrypted = request.get("is_encrypted")
            category = request.get("category")
            description = request.get("description")
        else:
            value = request.value
            is_encrypted = request.is_encrypted
            category = request.category
            description = request.description

        # Get existing credential to preserve metadata if not provided
        existing_creds = await credential_service.list_all_credentials()
        existing = next((c for c in existing_creds if c.key == key), None)

        if existing is None:
            # If credential doesn't exist, create it
            is_encrypted = is_encrypted if is_encrypted is not None else False
            logfire.info(f"Creating new credential via PUT | key={key}")
        else:
            # Preserve existing values if not provided
            if is_encrypted is None:
                is_encrypted = existing.is_encrypted
            if category is None:
                category = existing.category
            if description is None:
                description = existing.description
            logfire.info(f"Updating existing credential | key={key} | category={category}")

        success = await credential_service.set_credential(
            key=key,
            value=value,
            is_encrypted=is_encrypted,
            category=category,
            description=description,
        )

        if success:
            logfire.info(
                f"Credential updated successfully | key={key} | is_encrypted={is_encrypted}"
            )

            return {"success": True, "message": f"Credential {key} updated successfully"}
        else:
            logfire.error(f"Failed to update credential | key={key}")
            raise HTTPException(status_code=500, detail={"error": "Failed to update credential"})

    except Exception as e:
        logfire.error(f"Error updating credential | key={key} | error={str(e)}")
        raise HTTPException(status_code=500, detail={"error": str(e)})


@router.delete("/credentials/{key}")
async def delete_credential(key: str):
    """Delete a credential."""
    try:
        logfire.info(f"Deleting credential | key={key}")
        success = await credential_service.delete_credential(key)

        if success:
            logfire.info(f"Credential deleted successfully | key={key}")

            return {"success": True, "message": f"Credential {key} deleted successfully"}
        else:
            logfire.error(f"Failed to delete credential | key={key}")
            raise HTTPException(status_code=500, detail={"error": "Failed to delete credential"})

    except Exception as e:
        logfire.error(f"Error deleting credential | key={key} | error={str(e)}")
        raise HTTPException(status_code=500, detail={"error": str(e)})


@router.post("/credentials/initialize")
async def initialize_credentials_endpoint():
    """Reload credentials from database."""
    try:
        logfire.info("Reloading credentials from database")
        await initialize_credentials()

        logfire.info("Credentials reloaded successfully")

        return {"success": True, "message": "Credentials reloaded from database"}
    except Exception as e:
        logfire.error(f"Error reloading credentials | error={str(e)}")
        raise HTTPException(status_code=500, detail={"error": str(e)})


@router.get("/database/metrics")
async def database_metrics():
    """Get database metrics and statistics."""
    try:
        logfire.info("Getting database metrics")
        supabase_client = get_supabase_client()

        # Get various table counts
        tables_info = {}

        # Get projects count
        projects_response = (
            supabase_client.table("cortex_projects").select("id", count="exact").execute()
        )
        tables_info["projects"] = (
            projects_response.count if projects_response.count is not None else 0
        )

        # Get tasks count
        tasks_response = supabase_client.table("cortex_tasks").select("id", count="exact").execute()
        tables_info["tasks"] = tasks_response.count if tasks_response.count is not None else 0

        # Get crawled pages count
        pages_response = (
            supabase_client.table("cortex_crawled_pages").select("id", count="exact").execute()
        )
        tables_info["crawled_pages"] = (
            pages_response.count if pages_response.count is not None else 0
        )

        # Get settings count
        settings_response = (
            supabase_client.table("cortex_settings").select("id", count="exact").execute()
        )
        tables_info["settings"] = (
            settings_response.count if settings_response.count is not None else 0
        )

        total_records = sum(tables_info.values())
        logfire.info(
            f"Database metrics retrieved | total_records={total_records} | tables={tables_info}"
        )

        return {
            "status": "healthy",
            "database": "supabase",
            "tables": tables_info,
            "total_records": total_records,
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logfire.error(f"Error getting database metrics | error={str(e)}")
        raise HTTPException(status_code=500, detail={"error": str(e)})


@router.get("/settings/health")
async def settings_health():
    """Health check for settings API."""
    logfire.info("Settings health check requested")
    result = {"status": "healthy", "service": "settings"}

    return result


@router.post("/credentials/status-check")
async def check_credential_status(request: dict[str, list[str]]):
    """Report whether credentials are populated without returning their values."""
    try:
        credential_keys = request.get("keys", [])
        logfire.info(f"Checking status for credentials: {credential_keys}")
        
        result = {}
        
        for key in credential_keys:
            try:
                # Decrypt only to determine presence. Never return the value.
                decrypted_value = await credential_service.get_credential(key, decrypt=True)
                
                if decrypted_value and isinstance(decrypted_value, str) and decrypted_value.strip():
                    result[key] = {
                        "key": key,
                        "has_value": True
                    }
                else:
                    result[key] = {
                        "key": key,
                        "has_value": False
                    }
                    
            except Exception as e:
                logfire.warning(f"Failed to get credential for status check: {key} | error={str(e)}")
                result[key] = {
                    "key": key,
                    "has_value": False,
                    "error": str(e)
                }
        
        logfire.info(f"Credential status check completed | checked={len(credential_keys)} | found={len([k for k, v in result.items() if v.get('has_value')])}")
        return result
        
    except Exception as e:
        logfire.error(f"Error in credential status check | error={str(e)}")
        raise HTTPException(status_code=500, detail={"error": str(e)})
