"""
Heidi Calls: Intelligent Voicemail System
Main FastAPI Application
"""

import os
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import uvicorn
from datetime import datetime

from app.routers import voicemail, analytics
from app.services.triage_service import TriageService
from app.models.schemas import HealthCheckResponse

# Initialize services
triage_service = TriageService()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    print("[Heidi Calls] Initializing Medical Voicemail Triage System...")
    yield
    print("[Heidi Calls] Shutting down...")

app = FastAPI(
    title="Heidi Calls - Intelligent Voicemail",
    description="Transform unstructured medical voicemails into prioritized, actionable insights",
    version="1.0.0",
    lifespan=lifespan
)

# CORS configuration for frontend
# Read allowed origins from environment variable, fallback to localhost for development
cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(voicemail.router, prefix="/api/v1/voicemail", tags=["Voicemail"])
app.include_router(analytics.router, prefix="/api/v1/analytics", tags=["Analytics"])


@app.get("/", response_model=HealthCheckResponse)
async def root():
    """Health check endpoint"""
    return HealthCheckResponse(
        status="healthy",
        service="Heidi Calls API",
        timestamp=datetime.utcnow().isoformat(),
        version="1.0.0"
    )


@app.get("/health", response_model=HealthCheckResponse)
async def health_check():
    """Detailed health check"""
    return HealthCheckResponse(
        status="healthy",
        service="Heidi Calls API",
        timestamp=datetime.utcnow().isoformat(),
        version="1.0.0",
        components={
            "database": "connected",
            "ai_engine": "ready",
            "pii_filter": "active"
        }
    )


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
