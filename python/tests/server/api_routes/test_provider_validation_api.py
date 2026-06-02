from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from src.server.api_routes.knowledge_api import _validate_provider_api_key
from src.server.services.embeddings.embedding_exceptions import (
    EmbeddingAPIError,
    EmbeddingQuotaExhaustedError,
)


@pytest.mark.asyncio
async def test_validate_provider_api_key_surfaces_authentication_failures():
    with patch(
        "src.server.services.embeddings.embedding_service.create_embedding",
        new_callable=AsyncMock,
    ) as mock_create_embedding:
        mock_create_embedding.side_effect = EmbeddingAPIError(
            "Error code: 401 - Incorrect API key provided"
        )

        with pytest.raises(HTTPException) as exc_info:
            await _validate_provider_api_key("openai")

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail["error_type"] == "authentication_failed"
    assert exc_info.value.detail["provider"] == "openai"


@pytest.mark.asyncio
async def test_validate_provider_api_key_surfaces_quota_failures():
    with patch(
        "src.server.services.embeddings.embedding_service.create_embedding",
        new_callable=AsyncMock,
    ) as mock_create_embedding:
        mock_create_embedding.side_effect = EmbeddingQuotaExhaustedError("OpenAI quota exhausted")

        with pytest.raises(HTTPException) as exc_info:
            await _validate_provider_api_key("openai")

    assert exc_info.value.status_code == 429
    assert exc_info.value.detail["error_type"] == "quota_exhausted"
    assert "billing" in exc_info.value.detail["message"].lower()


@pytest.mark.asyncio
async def test_validate_provider_api_key_surfaces_embedding_configuration_failures():
    with patch(
        "src.server.services.embeddings.embedding_service.create_embedding",
        new_callable=AsyncMock,
    ) as mock_create_embedding:
        mock_create_embedding.side_effect = EmbeddingAPIError(
            "This model does not support embeddings"
        )

        with pytest.raises(HTTPException) as exc_info:
            await _validate_provider_api_key("openai")

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["error_type"] == "configuration_error"
    assert "does not support embeddings" in exc_info.value.detail["message"].lower()
