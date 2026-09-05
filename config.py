"""
DemoGen Configuration Management
Handles environment variables and application settings
"""

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    """Application configuration settings"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        # Tolerate unknown keys in .env. Under pydantic-settings' default
        # (extra="forbid") adding one stray line to .env crashes the whole app
        # at import time, which is a terrible failure mode for a config file.
        extra="ignore",
    )

    # LLM via an OpenAI-compatible chat-completions endpoint.
    # NOTE: despite the OPENROUTER_* names, api_base may point at any
    # OpenAI-compatible provider (Groq, Together, a local vLLM, ...).
    # Empty by default so the app still boots without a key; the LLM layer
    # raises a clear error at call time instead of a ValidationError at import.
    openrouter_api_key: str = ""
    openrouter_model: str = "meta-llama/llama-3.3-70b-instruct:free"
    openrouter_api_base: str = "https://openrouter.ai/api/v1/chat/completions"
    openrouter_reasoning_enabled: bool = False
    # Optional OpenRouter headers (app attribution; free)
    openrouter_http_referer: Optional[str] = "https://github.com/demogen"
    openrouter_app_title: str = "DemoGen"

    # Backward-compat aliases (optional; prefer OPENROUTER_*)
    groq_api_key: Optional[str] = None
    groq_model: Optional[str] = None
    groq_api_base: Optional[str] = None
    
    # Gemini API
    gemini_api_key: Optional[str] = None
    gemini_model: str = "gemini-2.0-flash-thinking-exp-01-21"
    
    # Database (Optional - for future use)
    database_url: Optional[str] = None
    database_host: str = "localhost"
    database_port: int = 5432
    database_name: str = "demogen"
    database_user: str = "postgres"
    database_password: str = "password"
    
    # Storage
    storage_type: str = "local"
    output_dir: str = "./outputs"
    video_output_dir: str = "./outputs/videos"
    narration_output_dir: str = "./outputs/narration"
    dom_snapshot_dir: str = "./outputs/dom_snapshots"
    
    # Cloud Storage (Optional - for future use)
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    aws_s3_bucket: str = "demogen-videos"
    gcs_bucket: str = "demogen-videos"
    gcs_project_id: Optional[str] = None
    
    # NeevCloud
    neevcloud_url: str = "https://en.wikipedia.org"
    neevcloud_test_email: Optional[str] = None
    neevcloud_test_password: Optional[str] = None
    neevcloud_auto_login: bool = False

    # Browser automation — free/local only (no paid cloud browsers or proxies)
    # local: Playwright's bundled Chromium
    # brave / chrome / msedge: an installed local browser
    browser_provider: str = "local"
    use_brave: bool = False
    brave_binary_path: Optional[str] = None
    brave_user_data_dir: Optional[str] = None
    brave_profile: str = "Default"
    # Renamed from SELENIUM_HEADLESS during the Playwright migration.
    # The old env var name is still accepted so existing .env files keep working.
    browser_headless: bool = Field(
        default=False,
        validation_alias=AliasChoices("browser_headless", "selenium_headless"),
    )
    brave_debugger_address: Optional[str] = None
    bot_challenge_timeout_s: int = 90

    # Local mock site demo defaults
    use_mock_site_by_default: bool = True
    mock_site_port: int = 8001
    mock_site_home_path: str = "/dashboard.html"
    auto_generate_for_dom_changes: bool = False
    
    # TTS
    tts_provider: str = "gtts"
    elevenlabs_api_key: Optional[str] = None
    
    # Application
    app_env: str = "development"
    app_debug: bool = True
    api_port: int = 8000
    api_host: str = "0.0.0.0"
    
    # Video
    video_quality: str = "1080p"
    video_fps: int = 30
    video_codec: str = "libx264"
    audio_bitrate: str = "128k"
    
    # Sentinel
    sentinel_check_interval: int = 86400  # 24 hours
    drift_detection_threshold: float = 0.85

    # Logging
    log_level: str = "INFO"
    log_file: str = "logs/demogen.log"

    @property
    def selenium_headless(self) -> bool:
        """Deprecated alias for :attr:`browser_headless`."""
        return self.browser_headless

    @property
    def llm_api_key(self) -> str:
        """The LLM key, or "" if none is really configured."""
        return real_secret(self.openrouter_api_key) or real_secret(self.groq_api_key)

    @property
    def llm_configured(self) -> bool:
        """True when an LLM call has any chance of succeeding.

        Guard on this rather than on the raw key: a copied-from-.env.example
        placeholder is a *truthy* string, so `if settings.openrouter_api_key:`
        passes and the provider answers 401 instead of the app reporting the
        real problem.
        """
        return bool(self.llm_api_key)


# Values that mean "not filled in yet". .env.example ships
# `your_api_key_here`, and copying it across leaves a truthy string behind.
_PLACEHOLDER_EXACT = {"changeme", "change_me", "none", "null", "todo", "tbd"}
_PLACEHOLDER_PREFIX = ("your_", "your-", "<", "xxx", "sk-xxx", "placeholder")


def real_secret(value: Optional[str]) -> str:
    """Return ``value`` stripped, or ``""`` if it is empty or a placeholder."""
    if not value:
        return ""
    text = str(value).strip()
    lowered = text.lower()
    if lowered in _PLACEHOLDER_EXACT or lowered.startswith(_PLACEHOLDER_PREFIX):
        return ""
    return text


# Create settings instance
settings = Settings()
