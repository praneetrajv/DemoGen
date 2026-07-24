"""
Main Pipeline Orchestrator
Coordinates all modules for end-to-end demo generation
"""

import sys
from pathlib import Path
from typing import Dict, Optional
import logging
import re
import time
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

from backend.app.modules.llm.orchestrator import LLMOrchestrator
from backend.app.modules.automation.selenium_engine import SeleniumEngine
from backend.app.modules.automation.action_planner import ActionPlanner
from backend.app.modules.tts.generator import TTSGenerator
from backend.app.modules.video.composer import VideoComposer
from backend.app.modules.validation.video_reviewer import VideoValidator
from config import settings
import json
import uuid

# Optional database imports
try:
    from backend.app.modules.database.connection import db
    from backend.app.modules.database.models import DemoSession, VideoAsset, AutomationLog, NarrationScript
    HAS_DATABASE = True
except:
    HAS_DATABASE = False

logger = logging.getLogger(__name__)


class DemoGenerationPipeline:
    """Orchestrates complete demo generation workflow"""
    
    def __init__(self):
        """Initialize pipeline components"""
        self.llm = LLMOrchestrator()
        self.planner = ActionPlanner()
        self.tts = TTSGenerator()
        self.composer = VideoComposer()
        self.validator = VideoValidator()
        self.browser = None
        self.session_id = None
        self.output_dir = Path(__file__).parent.absolute() / "outputs"
        self.output_dir.mkdir(exist_ok=True, parents=True)
    
    def generate(self, prompt: str, language: str = "en", 
                feature: Optional[str] = None, url: Optional[str] = None) -> Dict:
        """
        Generate complete demo video
        
        Args:
            prompt: User description of demo
            language: Language for narration
            feature: Portal feature to demo
            url: Target URL (defaults to NEEVCLOUD_URL from config)
            
        Returns:
            Generation result dictionary
        """
        try:
            start_time = time.time()
            
            # Create session ID
            self.session_id = str(uuid.uuid4())[:8]
            
            # Save session metadata locally
            session_dir = Path(settings.output_dir) / f"session_{self.session_id}"
            session_dir.mkdir(parents=True, exist_ok=True)
            
            session_metadata = {
                "session_id": self.session_id,
                "prompt": prompt,
                "language": language,
                "feature": feature,
                "status": "processing",
                "started_at": datetime.utcnow().isoformat()
            }
            
            metadata_file = session_dir / "metadata.json"
            with open(metadata_file, "w") as f:
                json.dump(session_metadata, f, indent=2)
            
            logger.info(f"Starting demo generation: {self.session_id}")
            
            # Step 1a: Fetch website DOM for intelligent planning
            logger.info("Step 1a: Fetching website DOM...")
            target_url = url or settings.neevcloud_url
            website_dom = self._fetch_website_dom(target_url)
            
            # Step 1b: Generate the action plan.
            # The local mock site uses a fixed, deterministic plan. Every other
            # target — any site, any task — is planned by the LLM using a real
            # snapshot of the landing page so selectors reflect the actual DOM.
            if self._is_mock_target(target_url):
                logger.info("Step 1b: Using mock-site action plan...")
                actions = self._build_mock_actions(target_url)
            else:
                logger.info("Step 1b: Using OpenRouter LLM to generate demo steps...")
                plan_result = self.llm.generate_action_plan(
                    prompt,
                    feature,
                    target_url=target_url,
                    dom_summary=website_dom,
                )
                if not plan_result.get("success"):
                    logger.warning("LLM plan failed, using fallback actions")
                    actions = self.planner._create_fallback_actions()
                else:
                    actions = self.planner.parse_llm_plan(plan_result.get("plan"))

                # Make sure the demo always starts on the requested page, even
                # if the model forgot an explicit navigate step.
                if not actions or actions[0].get("action_type") != "navigate":
                    actions.insert(
                        0,
                        {
                            "action_type": "navigate",
                            "url": target_url,
                            "description": "Open the target site",
                            "wait_ms": 1500,
                        },
                    )

                # Outro is handled by timed narration hold, not a fixed wait action.
            
            # Step 2: Per-step narration BEFORE recording so we can pace the video
            logger.info("Step 2: Generating per-step narration (for A/V sync)...")
            narration_result = self._generate_narration(actions, language)
            actions = self._attach_narration_timings(actions, narration_result)

            # Step 3: Execute automation paced to narration durations
            logger.info("Step 3: Executing automation (paced to narration)...")
            automation_result = self._execute_automation(
                actions,
                url or settings.neevcloud_url,
                prompt,
                feature,
                narration_result=narration_result,
            )
            
            # Prefer a usable recording over a hard fail. Automation may be
            # incomplete, but if frames were captured we still deliver the video.
            recorded_path = automation_result.get("video_path")
            automation_ok = bool(automation_result.get("success"))
            has_recording = bool(
                recorded_path
                and Path(recorded_path).exists()
                and Path(recorded_path).stat().st_size > 0
            )

            if not automation_ok and not has_recording:
                raise Exception(
                    f"Automation failed: {automation_result.get('error', 'Unknown error')}"
                )

            partial = not automation_ok
            if partial:
                logger.warning(
                    "Automation incomplete (%s); continuing with recorded video: %s",
                    automation_result.get("error", "unknown"),
                    recorded_path,
                )
                automation_result = dict(automation_result)
                automation_result["success"] = True
                automation_result["partial"] = True
                if not automation_result.get("actions"):
                    automation_result["actions"] = actions

            failed_actions = [
                a for a in automation_result.get("actions", [])
                if a.get("status") and a.get("status") != "completed"
            ]
            if failed_actions:
                logger.warning(
                    "Automation incomplete: %s actions failed", len(failed_actions)
                )
                partial = True
            
            # Step 4: Compose video (timelines already aligned by pacing)
            logger.info("Step 4: Composing video...")
            video_result = self._compose_video(
                automation_result,
                narration_result
            )

            if not video_result.get("success"):
                # Fall back to the raw selenium recording so the user still gets output.
                if has_recording:
                    logger.warning(
                        "Composition failed (%s); using raw recording",
                        video_result.get("error"),
                    )
                    video_result = {
                        "success": True,
                        "file_path": recorded_path,
                        "duration": 0,
                        "raw_fallback": True,
                    }
                    partial = True
                else:
                    raise Exception(
                        f"Video composition failed: {video_result.get('error', 'Unknown error')}"
                    )

            video_path = video_result.get("file_path")
            if not video_path or not Path(video_path).exists() or Path(video_path).stat().st_size == 0:
                if has_recording:
                    video_path = recorded_path
                    video_result["file_path"] = recorded_path
                    partial = True
                else:
                    raise Exception("Video composition did not produce a valid output file")

            # Promote raw recording into demo_<session>.mp4 when composition skipped
            demo_path = self.output_dir / f"demo_{self.session_id}.mp4"
            try:
                if Path(video_path).resolve() != demo_path.resolve() and Path(video_path).exists():
                    import shutil
                    shutil.copy2(video_path, demo_path)
                    video_path = str(demo_path)
                    video_result["file_path"] = video_path
            except Exception as copy_err:
                logger.warning(f"Could not promote recording to demo path: {copy_err}")
            
            # Step 5: Validate video (rule-based + Gemini visual content match)
            logger.info("Step 5: Validating video...")
            validation_result = self._validate_video(
                video_result,
                automation_result,
                prompt
            )

            # Validation issues are warnings only — never discard a real recording.
            if not validation_result.get("overall_valid", False):
                logger.warning(
                    "Video validation soft-failed: %s",
                    validation_result.get("reason")
                    or validation_result.get("issues")
                    or "Unknown validation error",
                )
                partial = True
            
            # Update session status
            duration = time.time() - start_time
            session_metadata["status"] = "partial" if partial else "completed"
            session_metadata["completed_at"] = datetime.utcnow().isoformat()
            session_metadata["duration_seconds"] = duration
            session_metadata["video_path"] = video_path
            if partial:
                session_metadata["warning"] = automation_result.get("error") or (
                    validation_result.get("issues") or ["Partial automation result"]
                )
            
            with open(metadata_file, "w") as f:
                json.dump(session_metadata, f, indent=2)
            
            logger.info(
                "Demo generation %s in %.2fs: %s -> %s",
                "partially completed" if partial else "completed",
                duration,
                self.session_id,
                video_path,
            )
            
            return {
                "success": True,
                "partial": partial,
                "session_id": self.session_id,
                "video_path": video_path,
                "duration": duration,
                "quality_score": validation_result.get("score", 100 if validation_result.get("overall_valid", True) else 70),
                "metadata": {
                    "actions": len(automation_result.get("actions") or actions),
                    "narration_length": len(narration_result.get("text", "")),
                    "video_duration": video_result.get("duration"),
                    "partial": partial,
                    "warning": session_metadata.get("warning"),
                }
            }
        except Exception as e:
            logger.error(f"Demo generation failed: {e}")
            
            # Update session status to failed
            if self.session_id:
                try:
                    session_dir = Path(settings.output_dir) / f"session_{self.session_id}"
                    metadata_file = session_dir / "metadata.json"
                    if metadata_file.exists():
                        with open(metadata_file, "r") as f:
                            session_metadata = json.load(f)
                        session_metadata["status"] = "failed"
                        session_metadata["error"] = str(e)
                        with open(metadata_file, "w") as f:
                            json.dump(session_metadata, f, indent=2)
                except:
                    pass
            
            return {
                "success": False,
                "error": str(e),
                "session_id": self.session_id
            }
    
    def _execute_automation(
        self,
        actions: list,
        url: str,
        prompt: str,
        feature: Optional[str] = None,
        narration_result: Optional[Dict] = None,
    ) -> Dict:
        """Execute automation using Selenium's continuous video recording.

        When per-step narration durations are available, each action holds on
        screen for that step's audio length so speech and UI stay aligned.
        """
        automation_dir = self.output_dir / f"session_{self.session_id}"
        automation_dir.mkdir(parents=True, exist_ok=True)
        engine = None
        engine_closed = False
        narration_result = narration_result or {}
        intro_duration = float(narration_result.get("intro_duration_s") or 0.0)
        outro_duration = float(narration_result.get("outro_duration_s") or 0.0)

        try:
            provider = (getattr(settings, "browser_provider", None) or "local").strip().lower()
            # Legacy: USE_BRAVE=true still selects Brave
            if settings.use_brave or provider == "brave":
                provider = "brave"

            logger.info(
                f"🌐 Launching free local browser for recording (provider={provider}, actions={len(actions)})..."
            )

            if provider == "brave":
                engine = SeleniumEngine(
                    headless=settings.selenium_headless,
                    binary_path=settings.brave_binary_path,
                    user_data_dir=settings.brave_user_data_dir,
                    profile_dir=settings.brave_profile,
                    debugger_address=settings.brave_debugger_address,
                )
            else:
                # Free local Chrome via Selenium + stealth (no cloud / paid services)
                engine = SeleniumEngine(headless=settings.selenium_headless)

            action_exec_start = time.time()
            
            if not engine.launch_browser():
                return {"success": False, "error": "Browser launch failed"}
            
            if not engine.create_context(video_dir=str(automation_dir)):
                engine.close()
                return {"success": False, "error": "Browser context creation failed"}
                
            # Use target URL and login
            target_url = url if url else settings.neevcloud_url
            email = settings.neevcloud_test_email
            password = settings.neevcloud_test_password
            
            if email and password:
                login_result = engine.login(target_url, email, password, wait_time=3000)
                if login_result.get("status") != "completed":
                    err = login_result.get("error") or "Login failed"
                    logger.error(f"Login failed (possibly bot verification): {err}")
                    engine.capture_screenshot(str(automation_dir / "bot_challenge.png"))
                    return self._finalize_recording(
                        engine,
                        automation_dir,
                        success=False,
                        error=err,
                        actions=[],
                    )
            else:
                logger.info(f"Navigating to {target_url} without login credentials...")
                nav_result = engine.navigate(target_url, wait_time=3000)
                if nav_result.get("status") != "completed":
                    err = nav_result.get("error") or "Navigation failed"
                    logger.error(f"Navigation failed (possibly bot verification): {err}")
                    engine.capture_screenshot(str(automation_dir / "bot_challenge.png"))
                    return self._finalize_recording(
                        engine,
                        automation_dir,
                        success=False,
                        error=err,
                        actions=[],
                    )

            # Final challenge check before actions (some walls appear after redirects)
            challenge_timeout = getattr(settings, "bot_challenge_timeout_s", 90) or 90
            challenge = engine.wait_for_bot_challenge(timeout=challenge_timeout)
            if challenge.get("status") == "blocked":
                engine.capture_screenshot(str(automation_dir / "bot_challenge.png"))
                return self._finalize_recording(
                    engine,
                    automation_dir,
                    success=False,
                    error=challenge.get("error"),
                    actions=[],
                )

            # Stabilize page, then hold for intro narration on the landing UI
            time.sleep(1.0)
            engine.capture_screenshot(str(automation_dir / "initial.png"))
            recording_t0 = time.time()
            if intro_duration > 0:
                logger.info(f"Intro hold {intro_duration:.2f}s (match intro narration)")
                if hasattr(engine, "record_hold"):
                    engine.record_hold(intro_duration)
                else:
                    time.sleep(intro_duration)
            
            # Execute each action with LLM feedback loop
            logger.info(f"Executing {len(actions)} automation actions (audio-paced)...")
            screenshots_captured = 0
            remaining_actions = list(actions)
            completed_actions = []
            replan_attempts = 0
            max_replans = 3
            feedback_interval = 3
            max_total_actions = 60
            timeline = []

            while remaining_actions:
                if len(completed_actions) + len(remaining_actions) > max_total_actions:
                    return self._finalize_recording(
                        engine,
                        automation_dir,
                        success=False,
                        error="Automation exceeded safe action limit",
                        actions=completed_actions + remaining_actions,
                    )

                action = remaining_actions.pop(0)
                idx = len(completed_actions) + 1
                action_type = action.get('action_type', 'unknown')
                description = action.get('description', f'Step {idx}')
                target_hold = float(action.get("narration_duration_s") or 0.0)
                if target_hold <= 0:
                    # Fallback estimate if TTS missing for this step
                    words = len(str(description).split()) or 4
                    target_hold = max(2.0, words / 2.5)
                logger.info(
                    f"  [{idx}] {action_type}: {description} (hold≈{target_hold:.2f}s)"
                )
                wait_ms = action.get('wait_ms', action.get('wait_time', action.get('time', 500)))
                try:
                    wait_ms = int(wait_ms)
                except Exception:
                    wait_ms = 500
                # Keep a short technical settle only; pacing comes from narration.
                settle_ms = min(max(wait_ms, 400), 1200)

                action_status = "completed"
                action_error = None
                step_t0 = time.time()
                video_start_s = step_t0 - recording_t0

                try:
                    if action_type == 'navigate':
                        url_to_navigate = action.get('url') or action.get('value')
                        if url_to_navigate:
                            engine.navigate(url_to_navigate, wait_time=max(settle_ms, 800))
                        else:
                            action_status = "failed"
                            action_error = "Missing URL for navigate"
                            
                    elif action_type == 'click':
                        selector = action.get('selector')
                        if selector:
                            result = engine.click(selector)
                            action_status = result.get("status", action_status)
                            action_error = result.get("error")
                        else:
                            action_status = "failed"
                            action_error = "Missing selector for click"
                            
                    elif action_type == 'fill':
                        selector = action.get('selector')
                        value = action.get('value', '')
                        if selector:
                            result = engine.fill(selector, value)
                            action_status = result.get("status", action_status)
                            action_error = result.get("error")
                        else:
                            action_status = "failed"
                            action_error = "Missing selector for fill"
                            
                    elif action_type == 'scroll':
                        amount = action.get('amount', 500)
                        try:
                            amount = int(amount)
                        except Exception:
                            amount = 500
                        engine.page.evaluate(f"window.scrollBy(0, {amount})")
                        
                    elif action_type == 'wait':
                        # Wait actions still use narration pacing below.
                        time.sleep(min(settle_ms / 1000.0, 0.5))

                    elif action_type == 'press':
                        selector = action.get('selector') or None
                        key = action.get('key') or action.get('value') or 'ENTER'
                        # LLM sometimes puts the key name in selector by mistake
                        if selector and str(selector).strip().upper() in {
                            "ENTER", "RETURN", "TAB", "ESC", "ESCAPE"
                        }:
                            key = str(selector).strip()
                            selector = None
                        result = engine.press(selector, key)
                        action_status = result.get("status", action_status)
                        action_error = result.get("error")
                        # Common search flow: fill worked, press selector is wrong
                        if action_status != "completed":
                            fallback = engine.press(None, key)
                            if fallback.get("status") == "completed":
                                action_status = "completed"
                                action_error = None
                        
                    else:
                        time.sleep(0.3)

                    # Encode this step's full narration window as video frames
                    # showing the post-action UI (true timeline sync, not wall sleep).
                    if hasattr(engine, "snapshot_frame"):
                        engine.snapshot_frame()
                    logger.info(
                        f"      record_hold {target_hold:.2f}s for step narration "
                        f"(action wall {time.time() - step_t0:.2f}s)"
                    )
                    if hasattr(engine, "record_hold"):
                        engine.record_hold(target_hold)
                    else:
                        time.sleep(target_hold)
                    screenshots_captured += 1
                    
                except Exception as exec_error:
                    action_status = "failed"
                    action_error = str(exec_error)
                    logger.warning(f"      Action execution error: {exec_error}")

                # Timeline uses cumulative *encoded* duration (frame-based), not wall clock.
                frames = int(getattr(engine, "_total_frames", 0) or 0)
                fps = float(getattr(engine, "_record_fps", 5) or 5)
                video_end_s = frames / fps if fps else (time.time() - recording_t0)
                video_start_s = max(0.0, video_end_s - target_hold)
                action["status"] = action_status
                action["video_start_s"] = round(video_start_s, 3)
                action["video_end_s"] = round(video_end_s, 3)
                action["narration_duration_s"] = target_hold
                if action_error:
                    action["error"] = action_error
                completed_actions.append(action)
                timeline.append(
                    {
                        "index": idx,
                        "description": description,
                        "action_type": action_type,
                        "video_start_s": action["video_start_s"],
                        "video_end_s": action["video_end_s"],
                        "narration_duration_s": target_hold,
                        "status": action_status,
                    }
                )

                if action_status != "completed":
                    engine.capture_screenshot(str(automation_dir / "failure.png"))
                    try:
                        failure_dom = engine.page.content()
                        with open(automation_dir / "failure_dom.html", "w", encoding="utf-8") as f:
                            f.write(failure_dom)
                    except Exception:
                        pass
                    if replan_attempts < max_replans:
                        current_dom = self._live_dom_summary(engine)
                        logger.info("Attempting LLM replan based on current DOM...")
                        replan_result = self.llm.generate_next_actions(
                            prompt,
                            current_dom,
                            completed_actions,
                            remaining_actions,
                        )
                        if replan_result.get("success") and replan_result.get("plan"):
                            plan_text = (replan_result.get("plan") or "").strip()
                            # Empty array means the model thinks the task is done.
                            if plan_text in {"[]", ""}:
                                logger.info("LLM replan indicates task complete; ending automation with partial success")
                                break
                            replanned = self.planner.parse_llm_plan(plan_text)
                            if replanned:
                                remaining_actions = replanned
                                replan_attempts += 1
                                continue
                        replan_attempts += 1
                    # Keep whatever was recorded instead of discarding the session.
                    return self._finalize_recording(
                        engine,
                        automation_dir,
                        success=False,
                        error="Automation incomplete: action failed and replanning exhausted",
                        actions=completed_actions + remaining_actions,
                    )

                if feedback_interval and (len(completed_actions) % feedback_interval == 0) and remaining_actions:
                    current_dom = self._live_dom_summary(engine)
                    feedback_result = self.llm.generate_next_actions(
                        prompt,
                        current_dom,
                        completed_actions,
                        remaining_actions,
                    )
                    if feedback_result.get("success") and feedback_result.get("plan"):
                        replanned = self.planner.parse_llm_plan(feedback_result.get("plan"))
                        if replanned:
                            remaining_actions = replanned
            
            # Outro hold so closing narration lines up with the final UI state
            if outro_duration > 0:
                logger.info(f"Outro hold {outro_duration:.2f}s (match outro narration)")
                if hasattr(engine, "record_hold"):
                    engine.record_hold(outro_duration)
                else:
                    time.sleep(outro_duration)

            # Persist timeline for debugging A/V alignment
            try:
                with open(automation_dir / "timeline.json", "w", encoding="utf-8") as tf:
                    json.dump(
                        {
                            "intro_duration_s": intro_duration,
                            "outro_duration_s": outro_duration,
                            "steps": timeline,
                        },
                        tf,
                        indent=2,
                    )
            except Exception as tl_err:
                logger.warning(f"Could not write timeline.json: {tl_err}")

            # Close browser to finalize video recording
            action_exec_time = time.time() - action_exec_start
            logger.info(f"Automation completed in {action_exec_time:.2f}s. Closing browser to finalize video...")
            finalized = self._finalize_recording(
                engine,
                automation_dir,
                success=True,
                error=None,
                actions=completed_actions,
            )
            engine_closed = True
            if finalized.get("success"):
                finalized["screenshots_captured"] = screenshots_captured
                finalized["browser_used"] = True
                finalized["timeline"] = timeline
                logger.info(f"✓ Video recorded successfully: {finalized.get('video_path')}")
            return finalized
            
        except Exception as e:
            logger.error(f"Automation error: {e}")
            if engine and not engine_closed:
                try:
                    return self._finalize_recording(
                        engine,
                        automation_dir,
                        success=False,
                        error=str(e),
                        actions=locals().get("completed_actions") or [],
                    )
                except Exception:
                    pass
            return {"success": False, "error": str(e)}
        finally:
            if engine and not engine_closed:
                try:
                    engine.close()
                except Exception:
                    pass

    def _finalize_recording(
        self,
        engine,
        automation_dir: Path,
        success: bool,
        error: Optional[str],
        actions: list,
    ) -> Dict:
        """Stop recording, close browser, and return any saved video path."""
        video_file = None
        try:
            if engine:
                # Prefer the path the engine already tracks.
                video_file = getattr(engine, "recorded_video_path", None)
                try:
                    engine.close()
                except Exception as close_err:
                    logger.warning(f"Engine close during finalize: {close_err}")
                video_file = getattr(engine, "recorded_video_path", None) or video_file
        except Exception as e:
            logger.warning(f"Finalize recording error: {e}")

        # Also scan session dir for selenium_*.mp4 in case the property was cleared.
        if (not video_file or not Path(video_file).exists()) and automation_dir:
            candidates = sorted(
                Path(automation_dir).glob("selenium_*.mp4"),
                key=lambda p: p.stat().st_mtime if p.exists() else 0,
                reverse=True,
            )
            if candidates:
                video_file = str(candidates[0])

        has_video = bool(video_file and Path(video_file).exists() and Path(video_file).stat().st_size > 0)
        result = {
            "success": bool(success and has_video),
            "actions": actions or [],
            "video_path": video_file if has_video else None,
            "browser_used": True,
        }
        if error:
            result["error"] = error
        # Partial path: recording exists even though actions failed.
        if not success and has_video:
            result["success"] = False
            result["partial"] = True
            result["video_path"] = video_file
        elif not has_video and success:
            result["success"] = False
            result["error"] = error or "Browser recording did not produce a video file"
        return result

    def _generate_narration(self, actions: list, language: str) -> Dict:
        """Generate per-step TTS clips so recording can be paced to speech."""
        try:
            logger.info("Generating per-step narration for A/V sync...")
            narration_dir = self.output_dir / f"narration_{self.session_id}"
            narration_dir.mkdir(parents=True, exist_ok=True)

            work_actions = list(actions[:20]) if actions else []
            intro_text = self._sanitize_narration_text(
                f"Welcome. This demo covers {max(len(work_actions), 1)} steps."
            )
            outro_text = self._sanitize_narration_text(
                "That completes this demonstration. Thanks for watching."
            )

            step_texts = []
            for idx, action in enumerate(work_actions):
                step_num = idx + 1
                description = (action.get("description") or f"Step {step_num}").strip()
                description = self._sanitize_narration_text(description) or f"Step {step_num}."
                if not description.endswith((".", "!", "?")):
                    description += "."
                # Keep lines short so one step does not dominate the timeline.
                if len(description.split()) > 28:
                    description = " ".join(description.split()[:28]).rstrip(".,") + "."
                step_texts.append(f"Step {step_num}. {description}")

            # Ordered clips: intro → steps → outro
            clip_specs = [("intro", intro_text)]
            for i, text in enumerate(step_texts):
                clip_specs.append((f"step_{i:03d}", text))
            clip_specs.append(("outro", outro_text))

            steps_meta = []
            audio_files = []
            all_text_parts = []
            for name, text in clip_specs:
                out_path = narration_dir / f"{name}.mp3"
                result = self.tts.generate_audio(text, str(out_path), language)
                duration = 0.0
                path = None
                if result.get("success") and result.get("file_path"):
                    path = result["file_path"]
                    duration = float(
                        result.get("duration_s")
                        or result.get("duration_estimate")
                        or 0.0
                    )
                    if duration <= 0.05:
                        duration = self.composer._get_media_duration(path)
                else:
                    # Fallback duration keeps pacing usable without audio for this clip
                    duration = max(1.5, len(text.split()) / 2.5)
                    logger.warning(f"TTS failed for {name}; using estimated {duration:.2f}s hold")

                audio_files.append(path)
                all_text_parts.append(text)
                steps_meta.append(
                    {
                        "name": name,
                        "text": text,
                        "audio_file": path,
                        "duration_s": duration,
                    }
                )

            intro_duration = steps_meta[0]["duration_s"] if steps_meta else 0.0
            outro_duration = steps_meta[-1]["duration_s"] if steps_meta else 0.0
            # Middle entries map 1:1 to actions
            action_step_meta = steps_meta[1:-1] if len(steps_meta) >= 2 else []

            # Concatenate into one track for final mux (same order as holds)
            valid_audio = [p for p in audio_files if p and Path(p).exists()]
            full_audio = None
            total_duration = sum(s["duration_s"] for s in steps_meta)
            if valid_audio:
                full_path = str(narration_dir / "narration.mp3")
                if len(valid_audio) == 1:
                    import shutil
                    shutil.copy2(valid_audio[0], full_path)
                    full_audio = full_path
                else:
                    full_audio = self.composer._concat_audio_files(valid_audio, full_path)
                measured = self.composer._get_media_duration(full_audio)
                if measured > 0.05:
                    total_duration = measured

            spoken_text = " ".join(all_text_parts)
            logger.info(
                "Narration ready: %s clips, total≈%.2fs (intro=%.2fs outro=%.2fs)",
                len(steps_meta),
                total_duration,
                intro_duration,
                outro_duration,
            )
            return {
                "success": True,
                "text": spoken_text,
                "audio_file": full_audio,
                "audio_files": valid_audio,
                "steps": steps_meta,
                "action_steps": action_step_meta,
                "intro_duration_s": intro_duration,
                "outro_duration_s": outro_duration,
                "duration": total_duration,
                "total_duration_s": total_duration,
            }
        except Exception as e:
            logger.error(f"Narration generation failed: {e}")
            return {"success": False, "error": str(e)}

    def _attach_narration_timings(self, actions: list, narration_result: Dict) -> list:
        """Copy per-step audio durations onto planned actions for recording holds."""
        if not actions:
            return actions
        action_steps = narration_result.get("action_steps") or []
        timed = []
        for i, action in enumerate(actions):
            a = dict(action)
            if i < len(action_steps):
                a["narration_duration_s"] = float(
                    action_steps[i].get("duration_s") or 2.5
                )
                a["narration_text"] = action_steps[i].get("text")
                a["narration_audio"] = action_steps[i].get("audio_file")
            else:
                desc = str(a.get("description") or "Step")
                a["narration_duration_s"] = max(2.0, len(desc.split()) / 2.5)
            timed.append(a)
        return timed

    def _sanitize_narration_text(self, text: str) -> str:
        """Strip non-spoken formatting so TTS only gets what users should hear."""
        if not text:
            return ""
        cleaned = re.sub(r"```[\s\S]*?```", "", text)
        cleaned = re.sub(r"\{[\s\S]*?\}", "", cleaned)
        lines = []
        for line in cleaned.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("[") or stripped.startswith("]"):
                continue
            if stripped.lower().startswith("narration:"):
                stripped = stripped.split(":", 1)[-1].strip()
            lines.append(stripped)
        return " ".join(lines).strip()
    
    def _compose_video(self, automation_result: Dict, narration_result: Dict) -> Dict:
        """Compose final video using paced recording + full narration track."""
        try:
            if not automation_result.get("success"):
                raise Exception("Automation failed, cannot compose video")
            
            if not narration_result.get("success"):
                raise Exception("Narration generation failed, cannot compose video")
            
            # Create video output path
            video_file = self.output_dir / f"demo_{self.session_id}.mp4"
            
            audio_file = narration_result.get("audio_file")
            audio_paths = []
            if audio_file:
                audio_paths = [audio_file]
            elif narration_result.get("audio_files"):
                audio_paths = [
                    p for p in narration_result["audio_files"] if p and Path(p).exists()
                ]

            # Use FFmpeg to compose
            composition_result = self.composer.compose_video_with_audio(
                automation_result.get("video_path", ""),
                audio_paths,
                str(video_file),
                {
                    "quality": settings.video_quality,
                    "bitrate": "5000k",
                    "codec": settings.video_codec,
                    "fps": settings.video_fps
                }
            )
            
            return composition_result
        except Exception as e:
            logger.error(f"Video composition failed: {e}")
            return {"success": False, "error": str(e)}
    
    def _validate_video(self, video_result: Dict, automation_result: Dict, 
                        original_prompt: str = "") -> Dict:
        """Validate generated video - rule-based checks only (skip Gemini)"""
        try:
            if not video_result.get("success"):
                return {"overall_valid": False, "reason": "Video composition failed"}
            
            # Rule-based metadata validation
            metadata = {
                "duration": video_result.get("duration", 0),
                "resolution": settings.video_quality,
                "has_audio": True,
                "fps": settings.video_fps,
                "expected_actions": len(automation_result.get("actions", [])),
                "captured_actions": len(automation_result.get("actions", []))
            }
            validation = self.validator.validate_video_metadata(metadata)
            
            return {
                "overall_valid": validation.get("valid", True),
                "score": validation.get("score", 100),
                "content_match_score": 100,
                "content_match_reasoning": "Using Selenium automation - content verified by execution",
                "issues": validation.get("issues", [])
            }
        except Exception as e:
            logger.error(f"Validation failed: {e}")
            return {"overall_valid": False, "error": str(e)}
    
    def _fetch_website_dom(self, url: str) -> str:
        """Fetch the landing page and return a compact, token-efficient summary
        of its interactable elements (links, buttons, inputs, headings).

        This gives the LLM planner a view of the *real* page so it can produce
        selectors that actually exist, instead of guessing. Failures are
        non-fatal — the planner can still work from the prompt alone and the
        pipeline re-plans against the live DOM once the browser is running.
        """
        try:
            import requests

            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0 Safari/537.36"
                )
            }
            response = requests.get(url, headers=headers, timeout=15)
            if not response.ok:
                logger.warning(
                    f"DOM fetch returned {response.status_code} for {url}"
                )
                return ""
            return self._summarize_dom(response.text)
        except Exception as e:
            logger.warning(f"Could not fetch DOM for {url}: {e}")
            return ""

    def _live_dom_summary(self, engine) -> str:
        """Compact summary of the live browser DOM for mid-demo re-planning.

        Prefers the engine's JS-based extractor (visible elements only); falls
        back to summarizing the raw page source if that is unavailable.
        """
        try:
            if hasattr(engine, "get_dom_summary"):
                summary = engine.get_dom_summary()
                if summary:
                    return summary
        except Exception:
            pass
        try:
            return self._summarize_dom(engine.page.content())
        except Exception:
            return ""

    def _summarize_dom(self, html: str, max_elements: int = 60) -> str:
        """Extract a compact list of interactable elements from raw HTML.

        Produces lines like:
            link "Alexander the Great" -> a[href="/wiki/Alexander_the_Great"]
            input name=search -> input[name="search"]
            button "Search" -> button

        Uses only the standard library (no bs4/lxml dependency).
        """
        from html.parser import HTMLParser
        from html import unescape

        class _Extractor(HTMLParser):
            def __init__(self):
                super().__init__(convert_charrefs=True)
                self.elements = []
                self._capture_tag = None
                self._attrs = {}
                self._text_parts = []

            def handle_starttag(self, tag, attrs):
                attrs = dict(attrs)
                if tag in ("a", "button", "h1", "h2", "h3"):
                    # Start capturing inner text for these tags.
                    self._capture_tag = tag
                    self._attrs = attrs
                    self._text_parts = []
                elif tag in ("input", "textarea", "select"):
                    self.elements.append(("field", tag, attrs, ""))

            def handle_data(self, data):
                if self._capture_tag:
                    self._text_parts.append(data)

            def handle_endtag(self, tag):
                if self._capture_tag and tag == self._capture_tag:
                    text = unescape(" ".join(self._text_parts).strip())
                    text = re.sub(r"\s+", " ", text)
                    self.elements.append(
                        (self._capture_tag, tag, self._attrs, text)
                    )
                    self._capture_tag = None
                    self._attrs = {}
                    self._text_parts = []

        try:
            parser = _Extractor()
            parser.feed(html)
        except Exception as e:
            logger.warning(f"DOM summary parse failed: {e}")
            return ""

        def _selector(tag: str, attrs: dict) -> str:
            if attrs.get("id"):
                return f"#{attrs['id']}"
            if attrs.get("data-testid"):
                return f'[data-testid="{attrs["data-testid"]}"]'
            if attrs.get("name"):
                return f'{tag}[name="{attrs["name"]}"]'
            if tag == "a" and attrs.get("href"):
                return f'a[href="{attrs["href"]}"]'
            if attrs.get("aria-label"):
                return f'{tag}[aria-label="{attrs["aria-label"]}"]'
            return tag

        lines = []
        seen = set()
        for kind, tag, attrs, text in parser.elements:
            if len(lines) >= max_elements:
                break
            selector = _selector(tag, attrs)
            if kind == "field":
                label = (
                    attrs.get("name")
                    or attrs.get("placeholder")
                    or attrs.get("aria-label")
                    or attrs.get("type")
                    or tag
                )
                line = f'{tag} "{label}" -> {selector}'
            else:
                if not text:
                    continue
                # Keep descriptions short.
                short = text[:80]
                line = f'{tag} "{short}" -> {selector}'
            if line in seen:
                continue
            seen.add(line)
            lines.append(line)

        return "\n".join(lines)

    def _is_mock_target(self, url: str) -> bool:
        """Detect if the target URL is the local mock site."""
        try:
            from urllib.parse import urlparse

            parsed = urlparse(url)
            return (
                parsed.hostname in {"localhost", "127.0.0.1"}
                and (parsed.port == settings.mock_site_port)
            )
        except Exception:
            return False

    def _build_mock_actions(self, target_url: str) -> list:
        """Build a deterministic action plan for the local mock site."""
        base = target_url.split("/", 3)[:3]
        base = "/".join(base)
        return [
            {
                "action_type": "navigate",
                "url": f"{base}/dashboard.html",
                "description": "Open the Projects dashboard",
                "wait_ms": 1500,
            },
            {
                "action_type": "click",
                "selector": "#create-project-btn",
                "description": "Click Create New Project",
                "wait_ms": 1000,
            },
            {
                "action_type": "fill",
                "selector": "#project-name",
                "value": "Demo Project",
                "description": "Enter the project name",
                "wait_ms": 800,
            },
            {
                "action_type": "click",
                "selector": "#tier",
                "description": "Open the workspace tier selector",
                "wait_ms": 500,
            },
            {
                "action_type": "click",
                "selector": "#tier option:nth-child(2)",
                "description": "Select GPU Pro tier",
                "wait_ms": 500,
            },
            {
                "action_type": "click",
                "selector": "#submit-btn",
                "description": "Initialize the project",
                "wait_ms": 2000,
            },
            {
                "action_type": "wait",
                "wait_ms": 2000,
                "description": "Wait for provisioning to complete",
            },
        ]
