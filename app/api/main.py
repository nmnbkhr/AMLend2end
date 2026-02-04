"""
AML Pipeline Runner - FastAPI Application

Main entry point for the API server. Provides REST endpoints for:
- Starting and managing pipeline runs
- Checking run status and progress
- Accessing artifacts and reports

Run with: uvicorn app.api.main:app --reload
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ..db import init_db
from .routes import runs_router, status_router, artifacts_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    # Startup
    logger.info("Starting AML Pipeline Runner API...")
    init_db()
    logger.info("Database initialized")
    yield
    # Shutdown
    logger.info("Shutting down AML Pipeline Runner API...")


# Create FastAPI application
app = FastAPI(
    title="AML Pipeline Runner",
    description="API for running and monitoring the AML end-to-end detection pipeline",
    version="1.0.0",
    lifespan=lifespan,
)

# Configure CORS for Streamlit UI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict to specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(runs_router)
app.include_router(status_router)
app.include_router(artifacts_router)


@app.get("/")
async def root():
    """Root endpoint - API information"""
    return {
        "name": "AML Pipeline Runner API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/status/health",
        "endpoints": {
            "runs": "/runs",
            "status": "/status",
            "artifacts": "/artifacts",
        },
    }


@app.get("/ping")
async def ping():
    """Simple health check endpoint"""
    return {"status": "ok", "message": "pong"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
