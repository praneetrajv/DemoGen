"""
DemoGen FastAPI Application
Main entry point for the backend server
"""

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config import settings
from .api import routes

try:
    from __version__ import __version__ as APP_VERSION
except ImportError:  # pragma: no cover - defensive
    APP_VERSION = "0.0.0"

# Initialize FastAPI app
app = FastAPI(
    title="DemoGen API",
    description="AI-Powered Demo Video Generator for NeevCloud",
    version=APP_VERSION,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json"
)

# CORS. allow_credentials=True is incompatible with the "*" wildcard -- browsers
# reject the combination -- so credentials stay off for the wildcard case and
# an explicit origin list turns them back on.
_cors_origins = ["*"] if settings.app_env == "development" else [
    f"http://localhost:{settings.api_port}",
    f"http://127.0.0.1:{settings.api_port}",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_cors_origins != ["*"],
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
    """Health check endpoint (also exposed at /api/health for the web UI)."""
    return routes.build_health_payload()


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
        content={"error": exc.detail, "detail": exc.detail},
    )


if __name__ == "__main__":
    import uvicorn
    # reload=True is ignored when an app *object* is passed rather than an import
    # string, so pass the string and let uvicorn own the import.
    uvicorn.run(
        "backend.app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.app_debug,
        log_level=settings.log_level.lower()
    )
