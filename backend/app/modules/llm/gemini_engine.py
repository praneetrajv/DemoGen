"""
Gemini API integration for generating smart Playwright automation steps.
Uses Gemini's thinking capability to analyze website DOM and generate realistic demo steps.
"""

import logging
import json
import os
from typing import Dict, List, Optional
import google.generativeai as genai

logger = logging.getLogger(__name__)


class GeminiEngine:
    """Generate smart automation steps using Gemini's thinking capability"""
    
    def __init__(self, api_key: Optional[str] = None):
        """Initialize Gemini engine.

        Resolution order: explicit argument, GEMINI_API_KEY env var, then
        config. Placeholder values (`your_api_key_here` and friends) are
        treated as unset -- otherwise they are truthy, genai gets configured
        with a bogus credential, and every call fails with a provider 401
        instead of the app reporting that no key is present.
        """
        import sys
        from pathlib import Path

        sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))
        try:
            from config import real_secret, settings
        except ImportError:  # pragma: no cover - config should always import
            logger.warning("Could not import config; relying on env vars only")
            real_secret, settings = (lambda v: (v or "").strip()), None

        resolved_key = real_secret(api_key) or real_secret(os.getenv("GEMINI_API_KEY"))
        if not resolved_key and settings is not None:
            resolved_key = real_secret(settings.gemini_api_key)

        self.api_key = resolved_key
        if self.api_key:
            genai.configure(api_key=self.api_key)
        # One model name for the whole class. The file used to hardcode
        # "gemini-2.0-flash-thinking-exp-01-21" here and plain
        # "gemini-2.0-flash" in two other methods, so settings.gemini_model
        # was never honoured anywhere.
        self.model = (
            getattr(settings, "gemini_model", None) or "gemini-2.0-flash"
        ) if settings is not None else "gemini-2.0-flash"
    
    def generate_demo_steps(self, prompt: str, website_dom: str) -> List[Dict]:
        """
        Use Gemini thinking to analyze website DOM and generate realistic demo steps.
        
        Args:
            prompt: User's demo description (e.g., "Show how to create a project")
            website_dom: HTML structure of the website
        
        Returns:
            List of Playwright automation steps
        """
        if not self.api_key:
            logger.warning("Gemini API key not configured, using fallback steps")
            return self._generate_fallback_steps(prompt)
        
        try:
            logger.info("🤖 Using Gemini thinking to generate demo steps...")
            
            system_prompt = """You are an expert web automation specialist. Analyze the website DOM and generate detailed Playwright automation steps for the given demo task.

IMPORTANT RULES:
1. Generate realistic, actionable steps that someone would actually perform
2. Focus on demonstrating the main feature/workflow
3. Each step must be executable with Playwright (navigate, click, fill, wait, scroll)
4. Include proper selectors based on the DOM structure
5. Add reasonable waits between actions
6. Make it look like a real user is using the website
7. Return JSON array of actions

Example format:
[
  {"action_type": "navigate", "url": "website_url", "description": "Navigate to project management page"},
  {"action_type": "click", "selector": "button.create-btn", "description": "Click 'Create New' button"},
  {"action_type": "fill", "selector": "input#project-name", "value": "Demo Project", "description": "Enter project name"},
  {"action_type": "click", "selector": "button[type=submit]", "description": "Click Save button"},
  {"action_type": "wait", "time": 2000, "description": "Wait for project to be created"}
]

Guidelines:
- Use realistic selectors (button.xxx, #id, [data-testid=xxx], etc.)
- Include descriptive text for each action
- Limit to 15-20 steps for a 30-second demo
- Add strategic waits after "loading" actions
- Demonstrate the complete workflow, not just individual clicks"""
            
            user_message = f"""Generate Playwright automation steps for this demo:

USER TASK: {prompt}

WEBSITE HTML STRUCTURE:
{website_dom[:5000]}  # Limit DOM size to avoid token overload

Generate realistic steps that would create a compelling demo video on this website. Think about what a user would actually do to demonstrate this feature."""
            
            # Use Gemini with thinking for deep analysis
            response = genai.GenerativeModel(self.model).generate_content(
                [
                    {
                        "role": "user",
                        "parts": [
                            {
                                "text": system_prompt + "\n\n" + user_message
                            }
                        ]
                    }
                ],
                generation_config=genai.types.GenerationConfig(
                    temperature=1,  # Required for thinking mode
                    max_output_tokens=8000,
                )
            )
            
            response_text = response.text
            logger.info(f"Gemini response length: {len(response_text)} chars")
            
            # Extract JSON from response
            steps = self._extract_json_from_response(response_text)
            
            if steps:
                logger.info(f"✓ Generated {len(steps)} automation steps")
                return steps
            else:
                logger.warning("Could not extract steps from Gemini response")
                return self._generate_fallback_steps(prompt)
                
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            import traceback
            traceback.print_exc()
            return self._generate_fallback_steps(prompt)
    
    def review_website_state(self, screenshot_base64: str, current_step: int, total_steps: int) -> Dict:
        """
        Use Gemini to review website state from screenshot and validate the demo progress.
        
        Args:
            screenshot_base64: Base64 encoded screenshot
            current_step: Current step number
            total_steps: Total steps in demo
        
        Returns:
            Analysis of what's shown in the screenshot
        """
        if not self.api_key:
            return {"description": f"Step {current_step}/{total_steps}", "success": True}
        
        try:
            logger.info(f"📸 Reviewing screenshot for step {current_step}/{total_steps}")
            
            # Was "gemini-2-0-flash" (hyphens, not dots) -- a nonexistent model
            # id, so every screenshot review returned a 404 from the provider.
            response = genai.GenerativeModel(self.model).generate_content(
                [
                    {
                        "text": f"Analyze this website screenshot for step {current_step}/{total_steps} of a demo. Describe what you see in 1-2 sentences. Is this step successful? Respond with: {{\"visible\": \"what's on screen\", \"success\": true/false}}"
                    },
                    {
                        "mime_type": "image/png",
                        "data": screenshot_base64
                    }
                ]
            )
            
            review_text = response.text
            review_data = self._extract_json_from_response(review_text)
            
            if review_data:
                logger.info(f"  → {review_data.get('visible', 'Cannot analyze')}")
                return review_data
            else:
                return {"description": f"Step {current_step}", "success": True}
                
        except Exception as e:
            logger.warning(f"Screenshot review error: {e}")
            return {"description": f"Step {current_step}", "success": True}
    
    def generate_narration(self, actions: list, language: str = "en") -> str:
        """
        Generate narration script for demo steps using Gemini.
        
        Args:
            actions: List of automation action dicts
            language: Language code for narration (e.g. 'en', 'es', 'fr')
        
        Returns:
            Narration script text
        """
        if not self.api_key:
            logger.warning("Gemini API key not configured, cannot generate narration")
            return ""
        
        try:
            logger.info("🤖 Using Gemini to generate narration...")
            
            action_descriptions = "\n".join([
                f"Step {i+1}: [{a.get('action_type', 'action')}] {a.get('description', '')}"
                for i, a in enumerate(actions[:20])
            ])
            
            language_names = {
                "en": "English", "es": "Spanish", "fr": "French",
                "de": "German", "ja": "Japanese", "zh": "Chinese",
                "hi": "Hindi", "pt": "Portuguese", "ko": "Korean"
            }
            lang_name = language_names.get(language, "English")
            
            prompt = f"""You are a professional demo narrator. Create engaging, clear narration for a demo video.

DEMO STEPS:
{action_descriptions}

LANGUAGE: {lang_name}

RULES:
- Write the narration in {lang_name}
- Keep each step's narration to 1-2 clear sentences
- Start with a brief welcome/introduction
- End with a closing summary
- Use simple, professional language
- Direct the viewer's attention to important elements
- The narration should feel natural when read aloud by TTS

Return ONLY the narration script text, no JSON, no formatting marks."""

            response = genai.GenerativeModel(self.model).generate_content(prompt)
            narration = response.text.strip()
            
            logger.info(f"✓ Gemini narration generated: {len(narration)} chars")
            return narration
            
        except Exception as e:
            logger.error(f"Gemini narration error: {e}")
            return ""
    
    def validate_video_content(self, video_path: str, original_prompt: str) -> Dict:
        """
        Validate that the video's visual content matches the user's requested demo.
        Extracts key frames from the video, sends them to Gemini vision,
        and checks if the content matches what the user asked for.
        
        Args:
            video_path: Path to the generated video file
            original_prompt: The user's original demo request
        
        Returns:
            Validation result with match_score, is_valid, and reasoning
        """
        if not self.api_key:
            logger.warning("Gemini API key not configured, skipping visual validation")
            return {"is_valid": True, "match_score": 0, "reasoning": "Skipped - no API key"}
        
        try:
            import imageio.v3 as iio
            import base64
            from io import BytesIO
            from PIL import Image
            
            logger.info("🤖 Using Gemini to validate video content...")
            
            # Extract key frames from the video
            frames_data = iio.imread(video_path, plugin="pyav")
            total_frames = len(frames_data)
            
            if total_frames == 0:
                return {"is_valid": False, "match_score": 0, "reasoning": "Video has no frames"}
            
            # Sample up to 5 evenly-spaced frames
            num_samples = min(5, total_frames)
            indices = [int(i * (total_frames - 1) / max(num_samples - 1, 1)) for i in range(num_samples)]
            
            # Encode sampled frames as base64 images
            frame_parts = []
            for idx in indices:
                frame_array = frames_data[idx]
                img = Image.fromarray(frame_array)
                # Resize to save tokens
                img.thumbnail((800, 450))
                buffer = BytesIO()
                img.save(buffer, format="PNG")
                b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
                frame_parts.append({
                    "inline_data": {
                        "mime_type": "image/png",
                        "data": b64
                    }
                })
            
            # Build the validation prompt
            text_prompt = f"""You are a video quality reviewer. The user requested a demo video with this description:

USER REQUEST: "{original_prompt}"

I am showing you {num_samples} key frames extracted from the generated demo video.

Analyze the frames and answer:
1. Do the frames show content related to the user's request?
2. Does the video appear to demonstrate the requested feature/workflow?
3. Are there any obvious visual issues (blank screens, error pages, unrelated content)?

Respond in this exact JSON format:
{{"match_score": <0-100>, "is_valid": <true/false>, "reasoning": "<2-3 sentence explanation>"}}

A score of 70+ means the video is acceptable. Below 70 means it likely doesn't match the request."""

            # Send frames + prompt to Gemini vision
            content_parts = [{"text": text_prompt}] + frame_parts
            
            response = genai.GenerativeModel(self.model).generate_content(content_parts)
            response_text = response.text.strip()
            
            # Parse the JSON response
            import re
            json_match = re.search(r'\{[\s\S]*\}', response_text)
            if json_match:
                result = json.loads(json_match.group())
                logger.info(f"✓ Gemini validation: score={result.get('match_score')}, valid={result.get('is_valid')}")
                return result
            
            logger.warning("Could not parse Gemini validation response")
            return {"is_valid": True, "match_score": 50, "reasoning": "Could not parse validation response"}
            
        except ImportError as e:
            logger.warning(f"Missing dependency for video validation: {e}")
            return {"is_valid": True, "match_score": 0, "reasoning": f"Skipped - missing dependency: {e}"}
        except Exception as e:
            logger.error(f"Gemini visual validation error: {e}")
            return {"is_valid": True, "match_score": 0, "reasoning": f"Validation error: {e}"}
    
    def generate_action_plan(self, prompt: str, feature: Optional[str] = None) -> Dict:
        """
        Generate a full action plan from user prompt using Gemini thinking.
        This is the primary planner (without needing DOM).
        
        Args:
            prompt: User's description of what to demo
            feature: Optional feature/section to focus on
        
        Returns:
            Dictionary with success status and parsed plan
        """
        if not self.api_key:
            logger.warning("Gemini API key not configured, cannot generate action plan")
            return {"success": False, "error": "Gemini API key not configured"}
        
        try:
            logger.info("🤖 Using Gemini thinking to generate action plan...")
            
            user_message = f"""Generate a detailed Playwright automation plan for this demo:

USER REQUEST: {prompt}
{"FEATURE/SECTION: " + feature if feature else ""}

Create a step-by-step plan with specific browser actions. Each step should have:
- action_type: navigate, click, fill, scroll, wait, hover, screenshot
- selector: CSS selector if applicable
- value: input value if applicable  
- description: clear description of the step

Return a JSON array of action objects. Limit to 15-20 steps."""

            system_prompt = """You are an expert web automation planner. Break down user requests into specific, executable Playwright browser actions. Return a JSON array."""

            response = genai.GenerativeModel(self.model).generate_content(
                [{"role": "user", "parts": [{"text": system_prompt + "\n\n" + user_message}]}],
                generation_config=genai.types.GenerationConfig(
                    temperature=1,
                    max_output_tokens=8000,
                )
            )
            
            response_text = response.text
            steps = self._extract_json_from_response(response_text)
            
            if steps:
                logger.info(f"✓ Gemini generated action plan with {len(steps)} steps")
                return {"success": True, "plan": steps}
            else:
                return {"success": False, "error": "Could not parse action plan from response"}
                
        except Exception as e:
            logger.error(f"Gemini action plan error: {e}")
            return {"success": False, "error": str(e)}
    
    def _extract_json_from_response(self, response_text: str) -> Optional[List[Dict]]:
        """Extract JSON array from Gemini response"""
        try:
            # Look for JSON array in response
            import re
            json_match = re.search(r'\[[\s\S]*\]', response_text)
            if json_match:
                json_str = json_match.group()
                steps = json.loads(json_str)
                if isinstance(steps, list):
                    return steps
            
            # Try parsing entire response as JSON
            steps = json.loads(response_text)
            if isinstance(steps, list):
                return steps
        except:
            pass
        
        return None
    
    def _generate_fallback_steps(self, prompt: str) -> List[Dict]:
        """Generate generic fallback steps when Gemini is unavailable"""
        logger.info("Generating fallback demo steps...")
        
        return [
            {
                "action_type": "wait",
                "time": 2000,
                "description": f"Demo: {prompt}"
            },
            {
                "action_type": "wait",
                "time": 2000,
                "description": "Wait for page to load"
            },
            {
                "action_type": "scroll",
                "amount": 500,
                "description": "Scroll down to view content"
            },
            {
                "action_type": "wait",
                "time": 1500,
                "description": "Wait for scroll animation"
            },
            {
                "action_type": "scroll",
                "amount": 500,
                "description": "Scroll down more"
            },
            {
                "action_type": "wait",
                "time": 1000,
                "description": "Demonstration complete"
            }
        ]
