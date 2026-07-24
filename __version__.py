"""
DemoGen Version Info and Metadata
"""

__version__ = "0.1.0"
__title__ = "DemoGen"
__description__ = "AI-Powered Demo Video Generator for NeevCloud Portal"
__author__ = "DemoGen Team"
__license__ = "Proprietary"
__copyright__ = "Copyright 2025"
__release_date__ = "2025-03-25"

# Feature flags
FEATURES = {
    "automation": True,           # Playwright automation
    "llm_integration": True,      # OpenRouter LLM
    "video_composition": True,    # FFmpeg composition
    "tts_generation": True,       # Text-to-speech
    "dom_monitoring": True,       # DOM sentinel
    "drift_detection": True,      # UI drift detection
    "video_validation": True,     # Quality validation
    "cloud_storage": False,       # Not yet implemented
    "user_auth": False,           # Not yet implemented
    "websocket_updates": False,   # Not yet implemented
}

# Supported models
MODELS = {
    "primary": {
        "provider": "openrouter",
        "model": "google/gemma-4-31b-it:free",
        "description": "Primary LLM for action planning and narration (free)"
    },
    "validation": {
        "provider": "openrouter",
        "model": "google/gemma-4-31b-it:free",
        "description": "Video validation / quality checks (free)"
    }
}

# Database schema version
DB_VERSION = "1.0.0"

# API version
API_VERSION = "v1"
