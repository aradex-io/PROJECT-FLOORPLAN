"""FastAPI application — serves the FLOORPLAN web dashboard and API."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from floorplan.web.routes import create_router
from floorplan.web.ws import ConnectionManager

logger = logging.getLogger(__name__)


def create_app(
    static_dir: Optional[str] = None,
    cors_origins: list[str] | None = None,
) -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="FLOORPLAN",
        description="Wi-Fi FTM/RTT Indoor Positioning Dashboard",
        version="0.1.0",
    )

    # CORS for development
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins or ["http://localhost:5173", "http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # WebSocket connection manager
    ws_manager = ConnectionManager()
    app.state.ws_manager = ws_manager

    # API routes
    router = create_router(ws_manager)
    app.include_router(router, prefix="/api")

    # Serve frontend static files
    if static_dir:
        static_path = Path(static_dir)
        if static_path.is_dir():
            app.mount("/", StaticFiles(directory=str(static_path), html=True), name="static")

    @app.on_event("startup")
    async def startup() -> None:
        logger.info("FLOORPLAN dashboard started")

    @app.on_event("shutdown")
    async def shutdown() -> None:
        await ws_manager.broadcast({"type": "shutdown"})
        logger.info("FLOORPLAN dashboard shutdown")

    return app
