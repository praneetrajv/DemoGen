"""
LLM Orchestrator
Handles all LLM interactions via OpenRouter chat completions
"""

import sys
from pathlib import Path
from typing import Optional

import requests

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))
from config import settings


class LLMOrchestrator:
    """Manages LLM interactions for demo generation (OpenRouter)."""

    def __init__(self):
        # llm_api_key filters out placeholders like `your_api_key_here`, which
        # are truthy and previously produced a provider 401 instead of a clear
        # "no key configured" message.
        self.api_key = settings.llm_api_key
        self.api_base = (
            settings.openrouter_api_base
            or settings.groq_api_base
            or "https://openrouter.ai/api/v1/chat/completions"
        )
        self.model = (
            settings.openrouter_model
            or settings.groq_model
            # Matches config.py's default. Do not invent a model name here:
            # a nonexistent id surfaces as an opaque 400 from the provider.
            or "meta-llama/llama-3.3-70b-instruct:free"
        )
        self.reasoning_enabled = bool(settings.openrouter_reasoning_enabled)
        self.conversation_history = []

    def _call_chat_completions(self, messages: list, max_tokens: int) -> dict:
        if not self.api_key:
            raise ValueError(
                "No LLM API key configured. Set OPENROUTER_API_KEY in .env "
                "(the shipped `your_api_key_here` placeholder counts as unset). "
                "Without it the pipeline uses its built-in mock action plan."
            )

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        # Optional free attribution headers recommended by OpenRouter
        referer = getattr(settings, "openrouter_http_referer", None)
        title = getattr(settings, "openrouter_app_title", None)
        if referer:
            headers["HTTP-Referer"] = referer
        if title:
            headers["X-Title"] = title

        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
        }
        if self.reasoning_enabled:
            payload["reasoning"] = {"enabled": True}

        response = requests.post(
            self.api_base,
            headers=headers,
            json=payload,
            timeout=120,
        )
        if not response.ok:
            detail = response.text[:500]
            raise RuntimeError(
                f"OpenRouter error {response.status_code}: {detail}"
            )
        return response.json()

    @staticmethod
    def _extract_content(api_response: dict) -> str:
        """Pull assistant text from an OpenRouter/OpenAI-style response."""
        try:
            message = api_response["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as e:
            raise RuntimeError(f"Unexpected LLM response shape: {api_response}") from e

        content = message.get("content")
        if isinstance(content, list):
            # Some models return content as a list of parts
            parts = []
            for part in content:
                if isinstance(part, dict) and part.get("text"):
                    parts.append(part["text"])
                elif isinstance(part, str):
                    parts.append(part)
            content = "\n".join(parts)

        if content is None or (isinstance(content, str) and not content.strip()):
            # Reasoning-only replies: fall back to any reasoning text if present
            reasoning = message.get("reasoning") or message.get("reasoning_details")
            if isinstance(reasoning, str) and reasoning.strip():
                return reasoning
            if isinstance(reasoning, list):
                texts = []
                for item in reasoning:
                    if isinstance(item, dict):
                        texts.append(str(item.get("text") or item.get("content") or ""))
                    else:
                        texts.append(str(item))
                joined = "\n".join(t for t in texts if t).strip()
                if joined:
                    return joined
            raise RuntimeError("LLM returned empty content")

        return content if isinstance(content, str) else str(content)

    def generate_action_plan(
        self,
        prompt: str,
        feature: Optional[str] = None,
        target_url: Optional[str] = None,
        dom_summary: Optional[str] = None,
    ) -> dict:
        """
        Generate action plan from user prompt using the configured OpenRouter model.

        When a snapshot of the target page's interactable elements (``dom_summary``)
        is provided, the planner is instructed to build selectors from those real
        elements rather than guessing — this is what lets the same code drive a
        demo on any site and any task.
        """
        system_prompt = """You are an expert web-demo automation planner. Turn the
user's request into a precise, ordered list of browser actions that accomplish
the WHOLE task (e.g. if they want to reach a specific page, plan the search/click
steps needed to get there — do not just open the home page).

Return ONLY a JSON array. Each element must be an object with:
- "action_type": one of navigate, click, fill, press, scroll, hover, wait, screenshot
- "selector": a CSS selector for the target element (omit for navigate/wait)
- "value": text to type (for fill) or key to press (for press, e.g. "ENTER")
- "url": the URL (for navigate only)
- "description": a short human-readable explanation of the step
- "wait_ms": milliseconds to pause after the action (use 800-2500)

Rules:
- Output valid JSON only. No prose, no markdown fences.
- Prefer stable selectors: ids (#id), [name="..."], [data-testid="..."], then link/button text or href.
- ONLY use selectors that plausibly match the provided page elements. Do not invent ids.
- To search, fill the search input with ONLY the search term (never the whole user sentence), then press ENTER or click the search button.
- Include the steps needed to click through to the final target (e.g. the matching search result link).
- Keep the plan focused: typically 3-8 steps."""

        user_message = f"User Request: {prompt}"
        if feature:
            user_message += f"\nFeature/Section: {feature}"
        if target_url:
            user_message += f"\nTarget URL (start here): {target_url}"
        if dom_summary:
            user_message += (
                "\n\nInteractable elements on the landing page "
                "(text -> selector):\n"
                f"{dom_summary[:4000]}"
            )
        user_message += (
            "\n\nReturn the JSON array of actions that completes the task."
        )

        try:
            message = self._call_chat_completions(
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                max_tokens=2048,
            )

            return {
                "success": True,
                "plan": self._extract_content(message),
                "usage": message.get("usage", {}),
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "plan": None,
            }

    def generate_next_actions(
        self,
        prompt: str,
        website_dom: str,
        completed_actions: list,
        remaining_actions: list,
        max_steps: int = 8,
    ) -> dict:
        """Generate next actions based on current DOM and progress."""
        system_prompt = """You are a web automation planner coordinating with a live browser.
        Return a JSON array of the NEXT actions to complete the user task based on the current DOM.

        Rules:
        - Only include actions that are visible/likely from the DOM provided
        - Prefer short, reliable selectors (ids, data-testid, button text)
        - If the task appears complete, return an empty JSON array: []
        - Return at most the requested number of steps
        """

        def _summarize(actions: list, limit: int = 6) -> str:
            parts = []
            for action in actions[-limit:]:
                parts.append(
                    f"{action.get('action_type','')} - {action.get('description','')}: {action.get('status','')}"
                )
            return "\n".join(parts)

        user_message = (
            f"User task: {prompt}\n\n"
            f"Completed actions (recent):\n{_summarize(completed_actions)}\n\n"
            f"Remaining plan (prior):\n{_summarize(remaining_actions)}\n\n"
            f"Current DOM:\n{website_dom[:6000]}\n\n"
            f"Return up to {max_steps} next actions as JSON array."
        )

        try:
            message = self._call_chat_completions(
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                max_tokens=2048,
            )

            return {
                "success": True,
                "plan": self._extract_content(message),
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "plan": None,
            }

    def generate_narration(self, actions: list, language: str = "en") -> str:
        """Generate narration script for the demo."""
        system_prompt = """You are a professional demo narrator. Create engaging, clear narration for demo videos.
        The narration should be:
        - Concise and professional
        - Use simple language
        - Direct the viewer's attention to important elements
        - Be approximately 30-60 seconds of narration per step

        Provide the narration as a simple text script that can be converted to speech."""

        action_descriptions = "\n".join(
            [f"Step {i+1}: {action.get('description', '')}" for i, action in enumerate(actions)]
        )

        user_message = f"""Create narration for these demo steps:
        {action_descriptions}

        Language: {language}
        Keep each step's narration to 1-2 sentences."""

        try:
            message = self._call_chat_completions(
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                max_tokens=1024,
            )

            return self._extract_content(message)
        except Exception as e:
            return f"Error generating narration: {str(e)}"

    def validate_video_quality(self, video_info: dict) -> dict:
        """Validate video quality and content via the configured LLM."""
        validation_prompt = f"""Analyze this demo video quality:
        - Duration: {video_info.get('duration', 'N/A')} seconds
        - Resolution: {video_info.get('resolution', 'N/A')}
        - Audio: {video_info.get('audio_present', 'N/A')}
        - Actions captured: {video_info.get('action_count', 'N/A')}
        - Errors: {video_info.get('errors', 'None')}

        Provide:
        1. Overall quality score (0-100)
        2. Whether video is acceptable for publishing (yes/no)
        3. Any issues or recommendations"""

        try:
            message = self._call_chat_completions(
                [{"role": "user", "content": validation_prompt}],
                max_tokens=512,
            )

            return {
                "success": True,
                "validation": self._extract_content(message),
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }

    def chat(self, user_message: str, system_prompt: Optional[str] = None) -> str:
        """General-purpose chat with the LLM."""
        self.conversation_history.append({
            "role": "user",
            "content": user_message,
        })

        try:
            message = self._call_chat_completions(
                [
                    {
                        "role": "system",
                        "content": system_prompt
                        or "You are a helpful AI assistant for demo generation.",
                    },
                ]
                + self.conversation_history,
                max_tokens=2048,
            )

            response = self._extract_content(message)
            self.conversation_history.append({
                "role": "assistant",
                "content": response,
            })

            return response
        except Exception as e:
            return f"Error: {str(e)}"

    def reset_conversation(self):
        """Reset conversation history"""
        self.conversation_history = []
