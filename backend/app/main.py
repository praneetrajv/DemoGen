"""
DemoGen FastAPI Application
Main entry point for the backend server
"""

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
import sys
import os
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config import settings
from .api import routes

# Initialize FastAPI app
app = FastAPI(
    title="DemoGen API",
    description="AI-Powered Demo Video Generator for NeevCloud",
    version="0.1.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
static_path = Path(__file__).parent.parent.parent / "frontend" / "static"
if static_path.exists():
    app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

# Mount mock site
mock_path = Path(__file__).parent.parent.parent / "mock_site"
mock_path.mkdir(parents=True, exist_ok=True)
app.mount("/mock", StaticFiles(directory=str(mock_path), html=True), name="mock")

# Mount outputs folder for video/media access
outputs_path = Path(__file__).parent.parent.parent / "outputs"
outputs_path.mkdir(parents=True, exist_ok=True)
app.mount("/outputs", StaticFiles(directory=str(outputs_path)), name="outputs")

# Include API routes
app.include_router(routes.router)


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "ok",
        "service": "DemoGen API",
        "version": "0.1.0",
        "environment": settings.app_env
    }


@app.get("/")
async def root():
    """Root endpoint - serve frontend"""
    frontend_path = Path(__file__).parent.parent.parent / "frontend" / "index.html"
    if frontend_path.exists():
        return FileResponse(frontend_path)
    return {
        "message": "Welcome to DemoGen",
        "docs": "/api/docs",
        "health": "/health"
    }


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Custom HTTP exception handler"""
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail},
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.app_debug,
        log_level=settings.log_level.lower()
    )
