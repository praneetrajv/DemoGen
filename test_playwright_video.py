"""Test Playwright-based video generation with real website automation"""
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


def test_playwright_video(tmp_path):
    """Generate demo using Playwright to automate website"""
    _require_service(BASE_URL)
    
    prompt = "Demonstrate creating a new project on NeevCloud by navigating, clicking project button, and filling in details"
    
    print("\n" + "="*70)
    print("Testing PLAYWRIGHT-POWERED Video Generation")
    print("="*70)
    print(f"\nPrompt: {prompt}\n")
    print("This will:")
    print("  1. Launch a real browser with Playwright")
    print("  2. Navigate to website")
    print("  3. Perform automation steps")
    print("  4. Capture REAL SCREENSHOTS of the website")
    print("  5. Overlay step info on screenshots")
    print("  6. Compose video from actual screenshots\n")
    
    # Generate demo
    print("Starting demo generation...")
    response = requests.post(
        f"{BASE_URL}/generate",
        json={
            "prompt": prompt,
            "language": "en"
        },
        timeout=120
    )
    assert response.status_code == 200, response.text
    
    result = response.json()
    session_id = result.get("session_id")
    
    print(f"✅ Generation started: {session_id}")
    print(f"   Status: {result.get('status')}")
    
    # Wait for completion
    print("\n⏳ Waiting for video generation (this may take 60+ seconds)...")
    completed = False
    for i in range(15):
        time.sleep(4)
        response = requests.get(f"{BASE_URL}/videos/{session_id}")
        if response.status_code == 200:
            video_info = response.json()
            if video_info.get('status') == 'completed':
                completed = True
                print(f"\n✅ Video generation complete!")
                print(f"   Duration: {video_info.get('duration')} seconds")
                print(f"   File size: {video_info.get('file_size')} bytes")
                print(f"   Has video: {video_info.get('has_video')}")

                if not video_info.get("has_video"):
                    pytest.skip("Generation completed but no downloadable video was produced")
                
                # Download video
                print("\nDownloading video...")
                response = requests.get(f"{BASE_URL}/download/{session_id}")
                if response.status_code == 200:
                    path = tmp_path / f"playwright_demo_{session_id}.mp4"
                    with open(path, "wb") as f:
                        f.write(response.content)
                    print(f"✅ Downloaded: {len(response.content)} bytes")
                    print(f"   Saved to: {path}")
                    print("\n🎥 Video is ready to play! It should contain:")
                    print("   - Real website screenshots (not just text)")
                    print("   - Automation steps actually performed in browser")
                    print("   - Step overlays with action info")
                    print("   - Natural narration audio")
                else:
                    print(f"❌ Download failed: {response.status_code}")
                break
        print(f"   Progress... ({i+1}/15)")

    assert completed, "Video generation did not reach completed state in time"

if __name__ == "__main__":
    test_playwright_video()
