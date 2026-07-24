#!/usr/bin/env python3
"""Integration tests for video generation API endpoints."""

import socket
from urllib.parse import urlparse

import pytest
import requests


BASE_URL = "http://localhost:8001/api"


def _require_service(base_url: str) -> None:
    parsed = urlparse(base_url)
    host = parsed.hostname or "localhost"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        with socket.create_connection((host, port), timeout=2):
            return
    except OSError:
        pytest.skip(f"Integration service unavailable at {host}:{port}")


def test_generate_and_fetch_video_metadata() -> None:
    _require_service(BASE_URL)

    response = requests.post(
        f"{BASE_URL}/generate",
        json={"prompt": "Create a demo project"},
        timeout=120,
    )
    assert response.status_code == 200, response.text

    gen_data = response.json()
    session_id = gen_data.get("session_id")
    assert session_id, "Missing session_id in generation response"

    vid_response = requests.get(f"{BASE_URL}/videos/{session_id}", timeout=30)
    assert vid_response.status_code == 200, vid_response.text

    vid_data = vid_response.json()
    assert vid_data.get("status") in {"pending", "processing", "completed", "failed"}
