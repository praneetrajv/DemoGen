"""End-to-end test: generate a demo video and download it.

/generate is synchronous -- it returns only after the pipeline has finished --
so there is nothing to poll for. Requires a running server (see conftest.py).
"""

import requests

PROMPT = (
    "Demonstrate how to create a new project on the GPU console. Show the steps: "
    "open the new project panel, fill in the project name, choose a workspace "
    "tier, and submit the form."
)


def test_end_to_end_video_generation(live_api: str, tmp_path) -> None:
    response = requests.post(
        f"{live_api}/generate",
        json={"prompt": PROMPT, "language": "en", "allow_partial": True},
        # The whole pipeline (browser + narration + compose) runs inline.
        timeout=600,
    )
    assert response.status_code == 200, response.text

    result = response.json()
    session_id = result.get("session_id")
    assert session_id, f"No session_id in response: {result}"
    # "partial" is expected when no LLM key is configured: the recording still
    # exists, only some planned actions were skipped.
    assert result["status"] in {"completed", "partial"}, result

    meta = requests.get(f"{live_api}/videos/{session_id}", timeout=30)
    assert meta.status_code == 200, meta.text
    video_info = meta.json()

    if not video_info.get("has_video"):
        raise AssertionError(
            f"Pipeline reported {result['status']} but produced no playable file. "
            f"metadata={video_info}"
        )

    download = requests.get(f"{live_api}/download/{session_id}", timeout=120)
    assert download.status_code == 200, download.text

    path = tmp_path / f"demo_{session_id}.mp4"
    path.write_bytes(download.content)
    assert path.stat().st_size > 0, "Downloaded video file is empty"
    print(
        f"\nsession={session_id} status={result['status']} "
        f"duration={video_info.get('duration')}s "
        f"size={path.stat().st_size} bytes -> {path}"
    )
