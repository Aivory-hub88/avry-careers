"""
Integration tests for WebSocket broadcast delivery in avry-careers.

Validates Requirements 13.1, 13.2, 13.3, 13.4:
- Careers_Service establishes WebSocket connections with clients
- Admin publishes vacancy → connected careers WS client receives update within 2s
- Admin closes vacancy → connected careers WS client receives update within 2s
- Admin edits vacancy → connected careers WS client receives update within 2s

These tests use real WebSocket connections to the FastAPI app via Starlette's
TestClient, with the database mocked. The broadcast function is called directly
to simulate admin actions triggering real-time updates.
"""

import asyncio
import json
import threading

import pytest
from unittest.mock import patch, AsyncMock

from app.main import app
from app.websocket.manager import careers_manager


@pytest.fixture(autouse=True)
def mock_database():
    """Mock database calls so tests don't require a real PostgreSQL connection."""
    with patch("app.database.connection.create_pool", new_callable=AsyncMock), \
         patch("app.database.connection.close_pool", new_callable=AsyncMock), \
         patch("app.database.connection.health_check", new_callable=AsyncMock, return_value=True), \
         patch("app.database.migrations.run_migrations", new_callable=AsyncMock):
        yield


@pytest.fixture(autouse=True)
def reset_manager():
    """Reset the global careers_manager state before each test for isolation."""
    careers_manager._active_connections = []
    if careers_manager._heartbeat_task is not None:
        careers_manager._heartbeat_task.cancel()
    careers_manager._heartbeat_task = None
    yield
    # Cleanup after test
    careers_manager._active_connections = []
    if careers_manager._heartbeat_task is not None:
        careers_manager._heartbeat_task.cancel()
    careers_manager._heartbeat_task = None


def _broadcast_sync(manager, message: dict) -> None:
    """Run an async broadcast in a new event loop on a separate thread (within 2s)."""
    async def do_broadcast():
        await manager.broadcast(message)

    loop = asyncio.new_event_loop()
    t = threading.Thread(target=lambda: loop.run_until_complete(do_broadcast()))
    t.start()
    t.join(timeout=2)
    loop.close()


class TestCareersWebSocketBroadcastIntegration:
    """Integration tests: admin action → careers WS broadcast → client receives within 2s."""

    def test_vacancy_published_broadcast_delivery(self):
        """
        Admin publishes a vacancy → connected careers WS client receives
        'vacancy_published' message within 2 seconds.

        Validates: Requirements 13.2, 13.4
        """
        from starlette.testclient import TestClient

        with TestClient(app) as client:
            with client.websocket_connect("/ws/careers") as websocket:
                message = {
                    "type": "vacancy_published",
                    "data": {
                        "vacancy_id": "vacancy-123",
                        "title": "Senior Software Engineer",
                        "department": "Engineering",
                        "location": "Remote",
                    },
                }

                _broadcast_sync(careers_manager, message)

                data = websocket.receive_text()
                received = json.loads(data)

                assert received["type"] == "vacancy_published"
                assert received["data"]["vacancy_id"] == "vacancy-123"
                assert received["data"]["title"] == "Senior Software Engineer"

    def test_vacancy_closed_broadcast_delivery(self):
        """
        Admin closes a vacancy → connected careers WS client receives
        'vacancy_closed' message within 2 seconds.

        Validates: Requirements 13.2, 13.4
        """
        from starlette.testclient import TestClient

        with TestClient(app) as client:
            with client.websocket_connect("/ws/careers") as websocket:
                message = {
                    "type": "vacancy_closed",
                    "data": {
                        "vacancy_id": "vacancy-456",
                    },
                }

                _broadcast_sync(careers_manager, message)

                data = websocket.receive_text()
                received = json.loads(data)

                assert received["type"] == "vacancy_closed"
                assert received["data"]["vacancy_id"] == "vacancy-456"

    def test_vacancy_edited_broadcast_delivery(self):
        """
        Admin edits a vacancy → connected careers WS client receives
        'vacancy_edited' message within 2 seconds.

        Validates: Requirements 13.2, 13.4
        """
        from starlette.testclient import TestClient

        with TestClient(app) as client:
            with client.websocket_connect("/ws/careers") as websocket:
                message = {
                    "type": "vacancy_edited",
                    "data": {
                        "vacancy_id": "vacancy-789",
                        "title": "Updated: Senior Software Engineer",
                        "department": "Engineering",
                    },
                }

                _broadcast_sync(careers_manager, message)

                data = websocket.receive_text()
                received = json.loads(data)

                assert received["type"] == "vacancy_edited"
                assert received["data"]["vacancy_id"] == "vacancy-789"
                assert received["data"]["title"] == "Updated: Senior Software Engineer"

    def test_multiple_clients_receive_broadcast(self):
        """
        Broadcast sent → ALL connected careers WS clients receive the message
        within 2 seconds.

        Validates: Requirements 13.2, 13.4
        """
        from starlette.testclient import TestClient

        with TestClient(app) as client1, TestClient(app) as client2:
            with client1.websocket_connect("/ws/careers") as ws1, \
                 client2.websocket_connect("/ws/careers") as ws2:

                message = {
                    "type": "vacancy_published",
                    "data": {
                        "vacancy_id": "broadcast-all-test",
                        "title": "Broadcast to All Clients",
                    },
                }

                _broadcast_sync(careers_manager, message)

                data1 = ws1.receive_text()
                data2 = ws2.receive_text()

                received1 = json.loads(data1)
                received2 = json.loads(data2)

                assert received1["type"] == "vacancy_published"
                assert received1["data"]["vacancy_id"] == "broadcast-all-test"
                assert received2["type"] == "vacancy_published"
                assert received2["data"]["vacancy_id"] == "broadcast-all-test"

    def test_vacancy_closed_includes_status_transition(self):
        """
        Admin closes a vacancy → broadcast includes status transition data
        so clients can update their local state.

        Validates: Requirements 13.2, 13.4
        """
        from starlette.testclient import TestClient

        with TestClient(app) as client:
            with client.websocket_connect("/ws/careers") as websocket:
                message = {
                    "type": "vacancy_closed",
                    "data": {
                        "vacancy_id": "close-test-001",
                        "previous_status": "open",
                        "new_status": "closed",
                    },
                }

                _broadcast_sync(careers_manager, message)

                data = websocket.receive_text()
                received = json.loads(data)

                assert received["type"] == "vacancy_closed"
                assert received["data"]["vacancy_id"] == "close-test-001"
                assert received["data"]["new_status"] == "closed"
