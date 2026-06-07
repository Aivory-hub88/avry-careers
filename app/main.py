"""
AVRY-Careers Service
Vacancy Management and Applicant Processing
Port: 8090
"""

import os
import sys
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.config import settings
from app.database.connection import create_pool, close_pool, health_check
from app.database.migrations import run_migrations
from app.routes.vacancies import router as vacancies_router
from app.routes.applications import router as applications_router
from app.routes.admin import router as admin_router
from app.websocket.manager import careers_manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"[{datetime.now().isoformat()}] [STARTUP] AVRY-Careers service starting on port {settings.port}...")
    try:
        await create_pool()
        print(f"[{datetime.now().isoformat()}] [STARTUP] Database pool created")
        await run_migrations()
        print(f"[{datetime.now().isoformat()}] [STARTUP] Database migrations applied")
    except Exception as e:
        print(f"[{datetime.now().isoformat()}] [STARTUP] WARNING: Database initialization failed: {e}")
    yield
    # Cleanup WebSocket connections and database pool
    await careers_manager.shutdown()
    await close_pool()
    print(f"[{datetime.now().isoformat()}] [SHUTDOWN] AVRY-Careers service shutting down...")


app = FastAPI(
    title="AVRY Careers Service",
    version="1.0.0",
    description="Vacancy Management and Applicant Processing",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(vacancies_router, prefix="/api")
app.include_router(applications_router, prefix="/api")
app.include_router(admin_router, prefix="/api")


@app.get("/health")
async def health():
    """Service health check — returns 200 when database is reachable, 503 otherwise."""
    db_healthy = await health_check()

    if db_healthy:
        return JSONResponse(
            status_code=200,
            content={
                "status": "healthy",
                "service": "avry-careers",
                "database": "connected",
            },
        )
    else:
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "service": "avry-careers",
                "database": "disconnected",
            },
        )


@app.get("/")
async def root():
    """Service info"""
    return {
        "service": "AVRY Careers Service",
        "version": "1.0.0"
    }


@app.websocket("/ws/careers")
async def websocket_careers(websocket: WebSocket):
    """
    WebSocket endpoint for careers real-time updates.

    Clients connect here to receive live notifications about:
    - Vacancy published (new vacancy made open)
    - Vacancy closed
    - Vacancy edited
    """
    await careers_manager.connect(websocket)
    try:
        while True:
            # Keep the connection alive by waiting for client messages
            # Clients can send "pong" in response to heartbeat pings
            data = await websocket.receive_text()
            # Client messages are acknowledged but not processed further
    except WebSocketDisconnect:
        careers_manager.disconnect(websocket)
    except Exception:
        careers_manager.disconnect(websocket)


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", settings.port))
    print(f"\n[*] Starting AVRY-Careers on port {port}...")
    uvicorn.run(app, host="0.0.0.0", port=port, reload=False, log_level="info")
