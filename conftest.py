"""Shared pytest fixtures for DemoGen's integration tests.

The three ``test_*.py`` scripts at the repo root each hardcoded a different
API port (8000, 8000, 8001) while ``.env`` set ``API_PORT=8081``, so every one
of them silently skipped instead of testing anything. Ports now come from
``config.settings`` -- one source of truth -- with an env override for
one-off runs against another host.
"""

import os
import socket
import sys
from pathlib import Path
from urllib.parse import urlparse

import pytest

# Repo root on sys.path so `from config import settings` works no matter which
# directory pytest was invoked from.
sys.path.insert(0, str(Path(__file__).parent))

from config import settings


def api_base_url() -> str:
    """Return the ``/api`` base URL of the running DemoGen server."""
    override = os.environ.get("DEMOGEN_API_BASE")
    if override:
        return override.rstrip("/")

    host = settings.api_host
    # 0.0.0.0 / :: are bind addresses, not dialable ones.
    if host in ("0.0.0.0", "::", ""):
        host = "127.0.0.1"
    return f"http://{host}:{settings.api_port}/api"


def mock_site_url() -> str:
    """Return the bundled mock site's home URL."""
    path = settings.mock_site_home_path
    if not path.startswith("/"):
        path = f"/{path}"
    return f"http://127.0.0.1:{settings.mock_site_port}{path}"


def _is_listening(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except OSError:
        return False


@pytest.fixture(scope="session")
def base_url() -> str:
    """The API base URL, whether or not anything is listening on it."""
    return api_base_url()


@pytest.fixture
def live_api(base_url: str) -> str:
    """Skip the test unless the DemoGen API is accepting connections."""
    if not _is_listening(base_url):
        pytest.skip(
            f"DemoGen API not reachable at {base_url} - "
            f"start it with `python -m backend.app.main` first"
        )
    return base_url


@pytest.fixture
def live_mock_site() -> str:
    """Skip the test unless the mock site server is up."""
    url = mock_site_url()
    if not _is_listening(url):
        pytest.skip(
            f"Mock site not reachable at {url} - start it with "
            f"`python -m uvicorn backend.app.mock_site_server:app "
            f"--port {settings.mock_site_port}`"
        )
    return url
