"""
DemoGen Configuration Management
Handles environment variables and application settings
"""

from pydantic_settings import BaseSettings
from typing import Optional
import os


class Settings(BaseSettings):
    """Application configuration settings"""
    
    # LLM via OpenRouter (free models preferred)
    openrouter_api_key: str
    openrouter_model: str = "google/gemma-4-31b-it:free"
    openrouter_api_base: str = "https://openrouter.ai/api/v1/chat/completions"
    openrouter_reasoning_enabled: bool = True
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
    # local: system Chrome with free stealth patches
    # brave: optional free local Brave profile (if installed)
    browser_provider: str = "local"
    use_brave: bool = False
    brave_binary_path: Optional[str] = None
    brave_user_data_dir: Optional[str] = None
    brave_profile: str = "Default"
    selenium_headless: bool = False
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
    
    class Config:
        env_file = ".env"
        case_sensitive = False


# Create settings instance
settings = Settings()
