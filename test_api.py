#!/usr/bin/env python3
"""Integration tests for the video generation API endpoints.

Requires a running server. Start it with `python -m backend.app.main`;
otherwise these tests skip. The base URL comes from conftest.api_base_url(),
which follows API_PORT in .env.
"""

import requests


def test_generate_and_fetch_video_metadata(live_api: str) -> None:
    response = requests.post(
        f"{live_api}/generate",
        json={"prompt": "Create a demo project", "allow_partial": True},
        timeout=300,
    )
    assert response.status_code == 200, response.text

    gen_data = response.json()
    session_id = gen_data.get("session_id")
    assert session_id, "Missing session_id in generation response"

    vid_response = requests.get(f"{live_api}/videos/{session_id}", timeout=30)
    assert vid_response.status_code == 200, vid_response.text

    vid_data = vid_response.json()
    # "partial" is what the pipeline writes when the recording succeeded but
    # some planned actions did not -- the common case without an LLM key.
    assert vid_data.get("status") in {
        "pending", "processing", "partial", "completed", "failed",
    }


def test_health(live_api: str) -> None:
    """/api/health is what the web UI polls on load."""
    response = requests.get(f"{live_api}/health", timeout=10)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "ok"
    # The UI prefills the target URL field from this, so it must be present.
    assert body["mock_site_url"].startswith("http")


def test_validate_prompt_rejects_short_input(live_api: str) -> None:
    """Short prompts come back as 200 + valid=False, not an HTTP error."""
    response = requests.post(f"{live_api}/validate-prompt", json={"prompt": "hi"}, timeout=10)
    assert response.status_code == 200, response.text
    assert response.json()["valid"] is False


def test_validate_prompt_accepts_real_input(live_api: str) -> None:
    response = requests.post(
        f"{live_api}/validate-prompt",
        json={"prompt": "Show how to create a new GPU project"},
        timeout=10,
    )
    assert response.status_code == 200, response.text
    assert response.json()["valid"] is True
