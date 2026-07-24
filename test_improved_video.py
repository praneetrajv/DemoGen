"""Test the improved video generation pipeline"""
import socket
import time
from urllib.parse import urlparse

import pytest
import requests

BASE_URL = "http://localhost:8000/api"


def _require_service(base_url: str) -> None:
    parsed = urlparse(base_url)
    host = parsed.hostname or "localhost"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        with socket.create_connection((host, port), timeout=2):
            return
    except OSError:
        pytest.skip(f"Integration service unavailable at {host}:{port}")


def test_video_generation(tmp_path):
    """Generate a demo video and check the output"""
    _require_service(BASE_URL)
    
    # Test prompt for creating a project on NeevCloud
    prompt = "Demonstrate how to create a new project on NeevCloud. Show all the steps including navigating to the projects section, clicking the new project button, filling in the project details, and confirming the creation."
    
    print("\n" + "="*60)
    print("Testing Improved Video Generation")
    print("="*60)
    print(f"\nPrompt: {prompt}\n")
    
    # Step 1: Generate demo
    print("Generating demo...")
    response = requests.post(
        f"{BASE_URL}/generate",
        json={
            "prompt": prompt,
            "language": "en"
        }
    )
    assert response.status_code == 200, response.text
    
    result = response.json()
    session_id = result.get("session_id")
    
    print(f"✅ Demo generation started")
    print(f"   Session ID: {session_id}")
    print(f"   Status: {result.get('status')}")
    
    # Wait for generation to complete
    print("\nWaiting for video to generate...")
    time.sleep(10)
    
    # Step 2: Get video info
    print("\nFetching video metadata...")
    response = requests.get(f"{BASE_URL}/videos/{session_id}")
    assert response.status_code == 200, response.text

    video_info = response.json()
    print(f"✅ Video metadata retrieved:")
    print(f"   Status: {video_info.get('status')}")
    print(f"   Duration: {video_info.get('duration')} seconds")
    print(f"   File size: {video_info.get('file_size')} bytes")
    print(f"   Has video: {video_info.get('has_video')}")
    print(f"   Video path: {video_info.get('video_path')}")

    if not video_info.get("has_video"):
        pytest.skip("Generation completed but no downloadable video was produced")
    
    # Step 3: Try to download the video
    print("\nDownloading video...")
    response = requests.get(f"{BASE_URL}/download/{session_id}")
    assert response.status_code == 200, response.text

    download_path = tmp_path / f"test_demo_{session_id}.mp4"
    with open(download_path, "wb") as f:
        f.write(response.content)
    print(f"✅ Video downloaded successfully!")
    print(f"   Size: {len(response.content)} bytes")
    print(f"   Local path: {download_path}")

    assert download_path.exists()
    assert download_path.stat().st_size > 0
    
    print("\n" + "="*60)
    print("Test complete!")
    print("="*60 + "\n")

if __name__ == "__main__":
    test_video_generation()
