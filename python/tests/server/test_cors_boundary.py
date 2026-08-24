"""CORS tests for the loopback-only Cortex API."""

from fastapi.testclient import TestClient

from src.server.main import app


def test_untrusted_origin_is_not_authorized():
    response = TestClient(app).options(
        "/api/settings",
        headers={
            "Origin": "https://untrusted.example",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_local_ui_origin_is_authorized():
    response = TestClient(app).options(
        "/api/settings",
        headers={
            "Origin": "http://localhost:3737",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3737"
