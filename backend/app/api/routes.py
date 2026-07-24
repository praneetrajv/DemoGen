"""
API Routes for DemoGen
Handles all API endpoints
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import sys
from pathlib import Path
import json
import logging

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from pipeline import DemoGenerationPipeline
from config import settings
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool
from backend.app.modules.sentinel.dom_monitor import DOMSentinel
from backend.app.modules.sentinel.drift_detector import DriftDetector

router = APIRouter(prefix="/api", tags=["demo"])
logger = logging.getLogger(__name__)


def _resolve_video_file(video_id: str) -> Optional[Path]:
    """Resolve the generated video file location for a session.

    Checks final composed demos first, then any selenium recording left in the
    session folder so partial runs still return playable output.
    """
    candidates = [
        Path(settings.output_dir) / f"demo_{video_id}.mp4",
        Path(settings.output_dir) / f"session_{video_id}" / "output.mp4",
        Path(settings.output_dir) / "videos" / f"demo_{video_id}.mp4",
    ]
    for path in candidates:
        if path.exists() and path.is_file() and path.stat().st_size > 0:
            return path

    session_dir = Path(settings.output_dir) / f"session_{video_id}"
    if session_dir.is_dir():
        selenium_videos = sorted(
            [
                p for p in session_dir.glob("selenium_*.mp4")
                if p.is_file() and p.stat().st_size > 0
            ],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if selenium_videos:
            return selenium_videos[0]
        other = sorted(
            [
                p for p in session_dir.glob("*.mp4")
                if p.is_file() and p.stat().st_size > 0
            ],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if other:
            return other[0]
    return None


class DemoRequest(BaseModel):
    """Request model for demo generation"""
    prompt: str
    language: str = "en"
    feature: Optional[str] = None
    user_id: Optional[str] = None
    use_mock_site: Optional[bool] = None
    target_url: Optional[str] = None
    allow_partial: bool = False


class DemoResponse(BaseModel):
    """Response model for demo generation"""
    session_id: str
    status: str
    message: str
    video_url: Optional[str] = None


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    service: str
    version: str


class DOMRefreshRequest(BaseModel):
    """Request model for DOM drift check and auto regeneration."""
    target_url: Optional[str] = None
    feature_name: str = "mock_site"
    auto_generate: bool = True


def _build_local_mock_url(path: str) -> str:
    normalized = path if path.startswith("/") else f"/{path}"
    return f"http://localhost:{settings.mock_site_port}{normalized}"


def _resolve_target_url(request: DemoRequest) -> str:
    if request.target_url:
        return request.target_url
    use_mock = settings.use_mock_site_by_default if request.use_mock_site is None else request.use_mock_site
    if use_mock:
        return _build_local_mock_url(settings.mock_site_home_path)
    return settings.neevcloud_url


def _auto_generate_for_dom_changes(
    target_url: str,
    language: str = "en",
    feature_name: str = "mock_site",
) -> Dict[str, Any]:
    """Detect mock-site DOM changes and generate demos for newly discovered features."""
    sentinel = DOMSentinel()
    detector = DriftDetector(similarity_threshold=settings.drift_detection_threshold)

    latest_snapshot = sentinel.load_latest_snapshot(feature_name)
    current_snapshot = sentinel.capture_snapshot_from_url(target_url, feature_name=feature_name)
    if not current_snapshot.get("success"):
        return {
            "checked": True,
            "drift_detected": False,
            "new_features": [],
            "generated_sessions": [],
            "error": current_snapshot.get("error", "DOM capture failed"),
        }

    # First capture: establish baseline and return.
    if not latest_snapshot:
        sentinel.save_latest_snapshot(feature_name, current_snapshot)
        return {
            "checked": True,
            "drift_detected": False,
            "new_features": [],
            "generated_sessions": [],
            "message": "Baseline DOM snapshot created",
        }

    drift_analysis = sentinel.compare_snapshots(latest_snapshot, current_snapshot)
    recommendation = detector.analyze_drift(drift_analysis)
    new_features = sentinel.detect_new_features(latest_snapshot, current_snapshot)

    generated_sessions = []
    if recommendation.get("action") == "regenerate_video" and new_features:
        for feature in new_features[:5]:
            auto_prompt = (
                f"From the home page, navigate to and demonstrate this newly added mock-site feature: "
                f"{feature.get('name')}"
            )
            pipeline = DemoGenerationPipeline()
            auto_result = pipeline.generate(
                prompt=auto_prompt,
                language=language,
                feature=feature.get("name"),
                url=target_url,
            )
            if auto_result.get("success"):
                generated_sessions.append(
                    {
                        "feature": feature.get("name"),
                        "session_id": auto_result.get("session_id"),
                        "video_url": f"/api/download/{auto_result.get('session_id')}",
                    }
                )

    # Update baseline after drift processing so future checks compare against latest DOM.
    sentinel.save_latest_snapshot(feature_name, current_snapshot)

    return {
        "checked": True,
        "drift_detected": drift_analysis.get("drift_detected", False),
        "recommendation": recommendation,
        "new_features": new_features,
        "generated_sessions": generated_sessions,
        "current_dom_hash": current_snapshot.get("dom_hash"),
    }


@router.post("/generate", response_model=DemoResponse)
async def generate_demo(request: DemoRequest):
    """
    Generate a demo video based on user prompt
    
    Args:
        request: DemoRequest with prompt and configuration
        background_tasks: FastAPI background tasks
        
    Returns:
        DemoResponse with session info
    """
    try:
        # Validate prompt
        if not request.prompt or len(request.prompt) < 5:
            raise HTTPException(
                status_code=400,
                detail="Prompt must be at least 5 characters long"
            )
        
        target_url = _resolve_target_url(request)
        use_mock = settings.use_mock_site_by_default if request.use_mock_site is None else request.use_mock_site

        dom_change_result: Dict[str, Any] = {"checked": False}
        # Disabled DOM auto-generation for now - was causing issues
        # if settings.auto_generate_for_dom_changes and use_mock:
        #     dom_change_result = await run_in_threadpool(...)

        # Create pipeline and generate demo
        pipeline = DemoGenerationPipeline()
        
        try:
            # Run generation 
            result = await run_in_threadpool(
                pipeline.generate,
                request.prompt,
                request.language,
                request.feature,
                target_url,
            )
            logger.info(f"Pipeline result: {list(result.keys())}")
            session_id = result.get("session_id")
            has_video = bool(session_id and _resolve_video_file(session_id))

            # Prefer returning a playable recording over a hard 500 whenever possible.
            if result.get("success"):
                duration = result.get("duration", 0)
                status = "partial" if result.get("partial") else "completed"
                if status == "partial":
                    message = (
                        f"Demo generated with incomplete steps in {duration:.2f}s "
                        f"(recording still available)"
                    )
                else:
                    message = f"Demo generated successfully in {duration:.2f}s"
                return DemoResponse(
                    session_id=session_id,
                    status=status,
                    message=message,
                    video_url=f"/api/download/{session_id}" if has_video else None,
                )

            if (request.allow_partial or has_video) and session_id and has_video:
                return DemoResponse(
                    session_id=session_id,
                    status="partial",
                    message=(
                        f"Demo generated with incomplete steps: "
                        f"{result.get('error', 'Unknown error')}"
                    ),
                    video_url=f"/api/download/{session_id}",
                )

            raise HTTPException(
                status_code=500,
                detail=f"Generation failed: {result.get('error', 'Unknown error')}"
            )
                
        except HTTPException:
            raise
        except Exception as pipeline_error:
            logger.exception(f"Pipeline execution error: {pipeline_error}")
            raise HTTPException(
                status_code=500,
                detail=f"Pipeline error: {str(pipeline_error)}"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Unexpected error in generate endpoint: {e}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.get("/demos")
async def list_demos():
    """List available demo templates"""
    demos = [
        {"id": "gpu_deployment", "name": "Deploy GPU", "description": "Guide to GPU deployment on NeevCloud"},
        {"id": "ai_inference", "name": "AI Inference", "description": "Setting up AI Inference platform"},
        {"id": "storage_setup", "name": "Storage Setup", "description": "Configuring cloud storage"},
    ]
    return {"demos": demos, "count": len(demos)}


@router.get("/languages")
async def list_languages():
    """List supported languages for TTS"""
    languages = [
        {"code": "en", "name": "English"},
        {"code": "es", "name": "Spanish"},
        {"code": "fr", "name": "French"},
        {"code": "de", "name": "German"},
        {"code": "ja", "name": "Japanese"},
        {"code": "zh", "name": "Chinese"},
    ]
    return {"languages": languages, "count": len(languages)}


@router.get("/videos/{video_id}")
async def get_video(video_id: str):
    """Get video metadata and status"""
    try:
        # Look for session metadata
        session_dir = Path(settings.output_dir) / f"session_{video_id}"
        metadata_file = session_dir / "metadata.json"
        
        if metadata_file.exists():
            with open(metadata_file, "r") as f:
                metadata = json.load(f)
            
            video_file = _resolve_video_file(video_id)
            has_video = video_file is not None
            video_url = f"/api/download/{video_id}" if has_video else None
            
            video_data = {
                "video_id": video_id,
                "status": metadata.get("status", "unknown"),
                "created_at": metadata.get("started_at"),
                "completed_at": metadata.get("completed_at"),
                "duration": metadata.get("duration_seconds", 0),
                "prompt": metadata.get("prompt"),
                "language": metadata.get("language"),
                "has_video": has_video,
                "video_path": video_url,
                "file_size": video_file.stat().st_size if has_video else 0
            }
            return video_data
        else:
            raise HTTPException(
                status_code=404,
                detail=f"Video session {video_id} not found"
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving video: {str(e)}"
        )


@router.get("/download/{video_id}")
async def download_video(video_id: str):
    """Download video file"""
    try:
        video_file = _resolve_video_file(video_id)

        if video_file is None:
            raise HTTPException(
                status_code=404,
                detail=f"Video file not found for session: {video_id}"
            )
        
        # Return file as downloadable
        return FileResponse(
            path=video_file,
            filename=f"demo_{video_id}.mp4",
            media_type="video/mp4"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error downloading video: {str(e)}"
        )


@router.post("/validate-prompt")
async def validate_prompt(request: DemoRequest):
    """Validate user prompt before generation"""
    try:
        if not request.prompt or len(request.prompt) < 10:
            raise HTTPException(
                status_code=400,
                detail="Prompt must be at least 10 characters long"
            )
        
        return {
            "valid": True,
            "message": "Prompt is valid",
            "estimated_duration": 120
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/dom/check-and-regenerate")
async def check_dom_and_regenerate(request: DOMRefreshRequest):
    """Capture mock-site DOM, detect changes, auto-generate demos for newly found features, and update baseline."""
    try:
        target_url = request.target_url or _build_local_mock_url(settings.mock_site_home_path)
        if not request.auto_generate:
            sentinel = DOMSentinel()
            old_snapshot = sentinel.load_latest_snapshot(request.feature_name)
            current_snapshot = await run_in_threadpool(
                sentinel.capture_snapshot_from_url,
                target_url,
                request.feature_name,
            )
            if not current_snapshot.get("success"):
                raise HTTPException(status_code=500, detail=current_snapshot.get("error", "DOM capture failed"))

            if not old_snapshot:
                sentinel.save_latest_snapshot(request.feature_name, current_snapshot)
                return {
                    "checked": True,
                    "drift_detected": False,
                    "new_features": [],
                    "generated_sessions": [],
                    "message": "Baseline DOM snapshot created",
                }

            drift_analysis = sentinel.compare_snapshots(old_snapshot, current_snapshot)
            new_features = sentinel.detect_new_features(old_snapshot, current_snapshot)
            sentinel.save_latest_snapshot(request.feature_name, current_snapshot)
            return {
                "checked": True,
                "drift_detected": drift_analysis.get("drift_detected", False),
                "new_features": new_features,
                "generated_sessions": [],
                "current_dom_hash": current_snapshot.get("dom_hash"),
            }

        result = await run_in_threadpool(
            _auto_generate_for_dom_changes,
            target_url,
            "en",
            request.feature_name,
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DOM monitor error: {str(e)}")
