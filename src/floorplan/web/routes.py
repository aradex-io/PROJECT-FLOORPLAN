"""FastAPI REST API routes and WebSocket endpoint."""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, UploadFile, File
from pydantic import BaseModel

from floorplan.web.ws import ConnectionManager

logger = logging.getLogger(__name__)


# --- Request/Response models ---

class ReferencePointModel(BaseModel):
    mac: str
    channel: int
    x: float
    y: float
    z: float = 0.0
    label: Optional[str] = None


class ZoneModel(BaseModel):
    name: str
    zone_type: str = "authorized"
    vertices: list[list[float]]
    floor: int = 0
    alert_on_enter: bool = False
    alert_on_exit: bool = False


class RangeRequestModel(BaseModel):
    target_mac: str
    channel: int = 0


class StatusResponse(BaseModel):
    status: str
    active_devices: int
    ws_clients: int
    session_active: bool
    session_id: Optional[int] = None


def create_router(ws_manager: ConnectionManager) -> APIRouter:
    """Create the API router with all endpoints."""
    router = APIRouter()

    # In-memory state (in production, these would be shared with the main engine)
    _state: dict[str, Any] = {
        "devices": {},
        "reference_points": [],
        "zones": [],
        "session_id": None,
    }

    # --- System ---

    @router.get("/status", response_model=StatusResponse)
    async def get_status() -> StatusResponse:
        """Get system status."""
        return StatusResponse(
            status="running",
            active_devices=len(_state["devices"]),
            ws_clients=ws_manager.client_count,
            session_active=_state["session_id"] is not None,
            session_id=_state["session_id"],
        )

    # --- Devices ---

    @router.get("/devices")
    async def list_devices() -> list[dict]:
        """List all tracked devices."""
        return list(_state["devices"].values())

    @router.get("/devices/{device_id}")
    async def get_device(device_id: str) -> dict:
        """Get a specific tracked device."""
        device = _state["devices"].get(device_id)
        if not device:
            return {"error": "Device not found"}
        return device

    @router.get("/devices/{device_id}/track")
    async def get_device_track(
        device_id: str,
        limit: int = 100,
    ) -> list[dict]:
        """Get position track history for a device."""
        device = _state["devices"].get(device_id)
        if not device:
            return []
        track = device.get("track_history", [])
        return track[-limit:]

    # --- Reference Points ---

    @router.get("/reference-points")
    async def list_reference_points() -> list[dict]:
        """List configured reference points."""
        return _state["reference_points"]

    @router.post("/reference-points")
    async def add_reference_point(rp: ReferencePointModel) -> dict:
        """Add a reference point."""
        rp_dict = rp.model_dump()
        _state["reference_points"].append(rp_dict)
        return {"status": "added", "reference_point": rp_dict}

    # --- Zones ---

    @router.get("/zones")
    async def list_zones() -> list[dict]:
        """List configured zones."""
        return _state["zones"]

    @router.post("/zones")
    async def add_zone(zone: ZoneModel) -> dict:
        """Add a geofence zone."""
        zone_dict = zone.model_dump()
        _state["zones"].append(zone_dict)
        return {"status": "added", "zone": zone_dict}

    # --- Floor Plan ---

    @router.post("/floor-plan/upload")
    async def upload_floor_plan(file: UploadFile = File(...)) -> dict:
        """Upload a floor plan image."""
        if not file.filename:
            return {"error": "No filename"}
        content = await file.read()
        # In production, save to disk and compute calibration
        logger.info("Floor plan uploaded: %s (%d bytes)", file.filename, len(content))
        return {
            "status": "uploaded",
            "filename": file.filename,
            "size_bytes": len(content),
        }

    @router.post("/floor-plan/calibrate")
    async def calibrate_floor_plan(
        points: list[dict],
    ) -> dict:
        """Calibrate floor plan with pixel-to-world coordinate mappings."""
        if len(points) < 3:
            return {"error": "Need at least 3 calibration points"}
        logger.info("Floor plan calibration with %d points", len(points))
        return {"status": "calibrated", "num_points": len(points)}

    # --- Ranging ---

    @router.post("/range")
    async def range_to_device(req: RangeRequestModel) -> dict:
        """Perform a single ranging measurement."""
        logger.info("Range request to %s on channel %d", req.target_mac, req.channel)
        return {
            "status": "pending",
            "target_mac": req.target_mac,
            "message": "Ranging request queued",
        }

    # --- Sessions ---

    @router.get("/sessions")
    async def list_sessions() -> list[dict]:
        """List recorded sessions."""
        return []

    @router.post("/sessions/start")
    async def start_session(name: str = "default") -> dict:
        """Start a recording session."""
        _state["session_id"] = 1  # placeholder
        return {"status": "started", "session_id": 1, "name": name}

    @router.post("/sessions/stop")
    async def stop_session() -> dict:
        """Stop the current recording session."""
        sid = _state["session_id"]
        _state["session_id"] = None
        return {"status": "stopped", "session_id": sid}

    # --- WebSocket ---

    @router.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        """WebSocket endpoint for real-time position updates."""
        await ws_manager.connect(websocket)
        try:
            while True:
                # Keep connection alive, receive any client commands
                data = await websocket.receive_text()
                logger.debug("WS received: %s", data[:200])
        except WebSocketDisconnect:
            ws_manager.disconnect(websocket)

    return router
