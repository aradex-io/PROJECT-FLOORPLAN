"""WebSocket connection manager for real-time position updates."""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections for the real-time dashboard.

    Broadcasts position updates, zone events, and system status to all
    connected dashboard clients.
    """

    def __init__(self) -> None:
        self._connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        """Accept a new WebSocket connection."""
        await websocket.accept()
        self._connections.append(websocket)
        logger.info("WebSocket client connected (%d total)", len(self._connections))

    def disconnect(self, websocket: WebSocket) -> None:
        """Remove a disconnected WebSocket."""
        if websocket in self._connections:
            self._connections.remove(websocket)
        logger.info("WebSocket client disconnected (%d remaining)", len(self._connections))

    async def broadcast(self, data: dict[str, Any]) -> None:
        """Send a JSON message to all connected clients."""
        if not self._connections:
            return

        message = json.dumps(data)
        disconnected: list[WebSocket] = []

        for ws in self._connections:
            try:
                await ws.send_text(message)
            except Exception:
                disconnected.append(ws)

        for ws in disconnected:
            self.disconnect(ws)

    async def send_position_update(
        self,
        device_id: str,
        mac: str,
        x: float,
        y: float,
        z: float = 0.0,
        uncertainty: float = 0.0,
        confidence: float = 0.0,
        state: str = "active",
        speed: float = 0.0,
        zones: list[str] | None = None,
    ) -> None:
        """Broadcast a device position update."""
        await self.broadcast(
            {
                "type": "position_update",
                "device_id": device_id,
                "mac": mac,
                "position": {"x": x, "y": y, "z": z},
                "uncertainty_m": uncertainty,
                "confidence": confidence,
                "state": state,
                "speed_mps": speed,
                "zones": zones or [],
            }
        )

    async def send_zone_event(
        self,
        device_id: str,
        zone_name: str,
        event_type: str,
        x: float,
        y: float,
        dwell_time_s: float | None = None,
    ) -> None:
        """Broadcast a zone event."""
        await self.broadcast(
            {
                "type": "zone_event",
                "device_id": device_id,
                "zone_name": zone_name,
                "event_type": event_type,
                "position": {"x": x, "y": y},
                "dwell_time_s": dwell_time_s,
            }
        )

    async def send_device_list(self, devices: list[dict[str, Any]]) -> None:
        """Broadcast the full device list."""
        await self.broadcast(
            {
                "type": "device_list",
                "devices": devices,
            }
        )

    @property
    def client_count(self) -> int:
        return len(self._connections)
