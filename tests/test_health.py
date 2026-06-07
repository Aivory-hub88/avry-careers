"""Tests for the /health endpoint of avry-careers service."""

import pytest
from unittest.mock import patch, AsyncMock

from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create a test client with mocked database pool creation."""
    with patch("app.main.create_pool", new_callable=AsyncMock):
        with patch("app.main.close_pool", new_callable=AsyncMock):
            with patch("app.main.run_migrations", new_callable=AsyncMock):
                from app.main import app
                with TestClient(app) as c:
                    yield c


def test_health_returns_200_when_db_connected(client):
    """Health endpoint returns 200 with healthy status when DB is reachable."""
    with patch("app.main.health_check", new_callable=AsyncMock, return_value=True):
        response = client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "avry-careers"
    assert data["database"] == "connected"


def test_health_returns_503_when_db_disconnected(client):
    """Health endpoint returns 503 with unhealthy status when DB is unreachable."""
    with patch("app.main.health_check", new_callable=AsyncMock, return_value=False):
        response = client.get("/health")

    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "unhealthy"
    assert data["service"] == "avry-careers"
    assert data["database"] == "disconnected"
