"""
Mock site static server
Serves the mock_site folder on a dedicated port.
"""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pathlib import Path

app = FastAPI(title="Mock Site", docs_url=None, redoc_url=None, openapi_url=None)

mock_path = Path(__file__).parent.parent.parent / "mock_site"
mock_path.mkdir(parents=True, exist_ok=True)
app.mount("/", StaticFiles(directory=str(mock_path), html=True), name="mock_site")
