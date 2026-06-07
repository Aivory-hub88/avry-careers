"""
WebSocket Connection Manager for careers real-time updates.

Manages active WebSocket connections, broadcasts messages to all connected
clients, and runs a periodic heartbeat to detect and clean up dead connections.

Message types broadcast:
- vacancy_published: When a new vacancy is published (status set to open)
- vacancy_closed: When a vacancy is closed
- vacancy_edited: When a vacancy is edited
"""

import asyncio
import json
import logging
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

# Heartbeat configuration
HEARTBEAT_INTERVAL = 30  # seconds between pings
HEARTBEAT_TIMEOUT = 10   # seconds to wait for pong response


class ConnectionManager:
    """
    Manages WebSocket connections for careers real-time updates.

    Provides methods to connect/disconnect clients, broadcast messages
    to all connected clients, and run a heartbeat loop to detect dead connections.
    """

    def __init__(self) -> None:
        self._active_connections: list[WebSocket] = []
        self._heartbeat_task: asyncio.Task | None = None

    @property
    def active_connections(self) -> list[WebSocket]:
        """Return a copy of the active connections list."""
        return list(self._active_connections)

    @property
    def connection_count(self) -> int:
        """Return the number of active connections."""
        return len(self._active_connections)

    async def connect(self, websocket: WebSocket) -> None:
        """
        Accept and register a new WebSocket connection.

        Starts the heartbeat loop if this is the first connection.
        """
        await websocket.accept()
        self._active_connections.append(websocket)
        logger.info(
            f"WebSocket client connected. Total connections: {self.connection_count}"
        )

        # Start heartbeat if first connection
        if self._heartbeat_task is None or self._heartbeat_task.done():
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    def disconnect(self, websocket: WebSocket) -> None:
        """
        Remove a WebSocket connection from the active list.

        Stops the heartbeat loop if no connections remain.
        """
        if websocket in self._active_connections:
            self._active_connections.remove(websocket)
            logger.info(
                f"WebSocket client disconnected. Total connections: {self.connection_count}"
            )

        # Stop heartbeat if no connections remain
        if self.connection_count == 0 and self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
            self._heartbeat_task = None

    async def broadcast(self, message: dict[str, Any]) -> None:
        """
        Send a JSON message to all connected WebSocket clients.

        Failed sends to individual clients are logged and the dead connection
        is removed, but do not block delivery to other clients.
        """
        if not self._active_connections:
            return

        payload = json.dumps(message)
        dead_connections: list[WebSocket] = []

        for connection in self._active_connections[:]:  # iterate over a copy
            try:
                await connection.send_text(payload)
            except Exception as e:
                logger.warning(f"Failed to send to client: {e}")
                dead_connections.append(connection)

        # Clean up dead connections
        for conn in dead_connections:
            self.disconnect(conn)

    async def _heartbeat_loop(self) -> None:
        """
        Periodic heartbeat to detect dead connections.

        Sends a ping every HEARTBEAT_INTERVAL seconds. If a client does not
        respond within HEARTBEAT_TIMEOUT seconds, the connection is considered
        dead and removed.
        """
        try:
            while self._active_connections:
                await asyncio.sleep(HEARTBEAT_INTERVAL)

                dead_connections: list[WebSocket] = []

                for connection in self._active_connections[:]:
                    try:
                        # Send a ping message and wait for response
                        await asyncio.wait_for(
                            connection.send_json({"type": "ping"}),
                            timeout=HEARTBEAT_TIMEOUT,
                        )
                    except (asyncio.TimeoutError, Exception) as e:
                        logger.warning(f"Heartbeat failed for client: {e}")
                        dead_connections.append(connection)

                # Remove dead connections
                for conn in dead_connections:
                    self.disconnect(conn)
                    try:
                        await conn.close()
                    except Exception:
                        pass  # Already dead, ignore

        except asyncio.CancelledError:
            logger.info("Heartbeat loop cancelled")
        except Exception as e:
            logger.error(f"Heartbeat loop error: {e}")

    async def shutdown(self) -> None:
        """
        Gracefully shut down the manager.

        Cancels the heartbeat loop and closes all active connections.
        """
        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
            self._heartbeat_task = None

        for connection in self._active_connections[:]:
            try:
                await connection.close()
            except Exception:
                pass

        self._active_connections.clear()
        logger.info("WebSocket manager shut down")


# Global careers manager instance used by route handlers
careers_manager = ConnectionManager()
