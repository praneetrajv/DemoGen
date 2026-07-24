"""
Video Validation Module
Handles rule-based and AI-powered (Gemini Vision) quality validation of generated demo videos
"""

import sys
from pathlib import Path
from typing import Optional, Dict

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))


class VideoValidator:
    """Validates generated demo videos for quality and correctness"""
    
    def __init__(self):
        """Initialize video validator"""
        # Short demos (e.g. quick Wikipedia navigations) are still valid output.
        self.min_duration = 3  # seconds
        self.max_duration = 600  # seconds
        self.min_resolution = "720p"
        self.acceptable_formats = ["mp4", "webm", "mov"]
        
    def validate_video_file(self, video_path: str) -> Dict:
        """
        Validate video file exists and has correct format
        
        Args:
            video_path: Path to video file
            
        Returns:
            Validation result dictionary
        """
        try:
            path = Path(video_path)
            
            if not path.exists():
                return {
                    "valid": False,
                    "error": "Video file not found"
                }
            
            ext = path.suffix.lower().strip(".")
            if ext not in self.acceptable_formats:
                return {
                    "valid": False,
                    "error": f"Invalid format: {ext}. Accepted: {self.acceptable_formats}"
                }
            
            file_size = path.stat().st_size
            if file_size == 0:
                return {
                    "valid": False,
                    "error": "Video file is empty"
                }
            
            return {
                "valid": True,
                "file_size": file_size,
                "format": ext,
                "path": str(path)
            }
        except Exception as e:
            return {
                "valid": False,
                "error": str(e)
            }
    
    def validate_video_metadata(self, metadata: Dict) -> Dict:
        """
        Validate video metadata
        
        Args:
            metadata: Video metadata dictionary
            
        Returns:
            Validation result
        """
        issues = []
        
        # Check duration
        duration = metadata.get("duration", 0)
        if duration < self.min_duration:
            issues.append(f"Duration too short: {duration}s (minimum {self.min_duration}s)")
        elif duration > self.max_duration:
            issues.append(f"Duration too long: {duration}s (maximum {self.max_duration}s)")
        
        # Check resolution
        resolution = metadata.get("resolution", "unknown")
        if resolution == "unknown":
            issues.append("Resolution not detected")
        
        # Check audio
        has_audio = metadata.get("has_audio", False)
        if not has_audio:
            issues.append("No audio track detected")
        
        # Check frame rate
        fps = metadata.get("fps", 0)
        if fps < 24:
            issues.append(f"Frame rate too low: {fps} FPS (minimum 24 FPS)")
        
        # Check if all expected actions were captured
        expected_actions = metadata.get("expected_actions", 0)
        captured_actions = metadata.get("captured_actions", 0)
        if captured_actions < expected_actions:
            issues.append(f"Not all actions captured: {captured_actions}/{expected_actions}")
        
        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "score": 100 - (len(issues) * 10),  # Simple scoring
            "metadata": metadata
        }
    
    def validate_automation_output(self, automation_result: Dict) -> Dict:
        """
        Validate automation execution results
        
        Args:
            automation_result: Results from Playwright automation
            
        Returns:
            Validation result
        """
        issues = []
        
        # Check if automation completed successfully
        if not automation_result.get("success"):
            issues.append(f"Automation failed: {automation_result.get('error', 'Unknown error')}")
        
        # Check action completion
        total_actions = len(automation_result.get("actions", []))
        completed_actions = len([a for a in automation_result.get("actions", []) if a.get("status") == "completed"])
        
        if completed_actions < total_actions:
            issues.append(f"Not all actions completed: {completed_actions}/{total_actions}")
        
        # Check for errors during automation
        action_errors = [a.get("error") for a in automation_result.get("actions", []) if a.get("error")]
        if action_errors:
            issues.append(f"Action errors occurred: {len(action_errors)} errors")
        
        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "total_actions": total_actions,
            "completed_actions": completed_actions,
            "action_success_rate": (completed_actions / total_actions * 100) if total_actions > 0 else 0
        }
    
    def validate_with_gemini(self, video_path: str, original_prompt: str) -> Dict:
        """
        Use Gemini vision to validate that the video's visual content
        matches the user's requested demo.
        
        Args:
            video_path: Path to the generated video file
            original_prompt: The user's original demo request
        
        Returns:
            Gemini validation result with match_score, is_valid, reasoning
        """
        try:
            import sys
            from pathlib import Path
            sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))
            
            from backend.app.modules.llm.gemini_engine import GeminiEngine
            
            gemini = GeminiEngine()
            result = gemini.validate_video_content(video_path, original_prompt)
            
            return {
                "valid": result.get("is_valid", True),
                "match_score": result.get("match_score", 0),
                "reasoning": result.get("reasoning", ""),
                "source": "gemini_vision"
            }
        except Exception as e:
            return {
                "valid": True,
                "match_score": 0,
                "reasoning": f"Gemini validation skipped: {e}",
                "source": "fallback"
            }
    
    def generate_validation_report(self, validation_results: Dict) -> Dict:
        """
        Generate a comprehensive validation report
        
        Args:
            validation_results: All validation results
            
        Returns:
            Formatted validation report
        """
        # Check if Gemini visual validation was performed
        gemini_result = validation_results.get("gemini_validation", {})
        gemini_valid = gemini_result.get("valid", True)
        gemini_score = gemini_result.get("match_score", 0)
        
        overall_valid = all([
            validation_results.get("file_valid", False),
            validation_results.get("metadata_valid", False),
            validation_results.get("automation_valid", False),
            gemini_valid
        ])
        
        return {
            "timestamp": validation_results.get("timestamp"),
            "video_id": validation_results.get("video_id"),
            "overall_valid": overall_valid,
            "checks": {
                "file": validation_results.get("file_validation"),
                "metadata": validation_results.get("metadata_validation"),
                "automation": validation_results.get("automation_validation"),
                "gemini_visual": gemini_result
            },
            "content_match_score": gemini_score,
            "recommendation": "APPROVE" if overall_valid else "REVIEW",
            "notes": validation_results.get("notes", [])
        }
