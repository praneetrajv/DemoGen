"""Setup and initialization script for DemoGen"""

import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from config import settings


def setup_directories():
    """Create necessary directories"""
    directories = [
        settings.output_dir,
        settings.video_output_dir,
        settings.narration_output_dir,
        settings.dom_snapshot_dir,
        "logs",
        "temp"
    ]
    
    for directory in directories:
        Path(directory).mkdir(parents=True, exist_ok=True)
        print(f"✓ Created directory: {directory}")


def setup_database():
    """Initialize database"""
    try:
        from backend.app.modules.database.connection import db
        print("⏳ Initializing database...")
        db.create_tables()
        print("✓ Database initialized")
    except Exception as e:
        print(f"✗ Database initialization failed: {e}")
        return False
    return True


def check_dependencies():
    """Check if all dependencies are installed"""
    required = [
        ("fastapi", "FastAPI"),
        ("uvicorn", "Uvicorn"),
        ("playwright", "Playwright"),
        ("requests", "Requests"),
        ("gtts", "Google TTS"),
        ("imageio_ffmpeg", "ImageIO FFmpeg"),
        ("pydantic_settings", "Pydantic Settings"),
    ]
    # Only needed for the optional Postgres session store and the optional
    # Gemini visual validation. A missing one used to fail the whole preflight.
    optional = [
        ("sqlalchemy", "SQLAlchemy", "database session history"),
        ("psycopg2", "psycopg2", "Postgres driver"),
        ("google.generativeai", "Gemini SDK", "visual video validation"),
        ("imageio", "ImageIO", "frame extraction for visual validation"),
    ]

    print("\n📦 Checking dependencies...")
    all_installed = True

    for module, name in required:
        try:
            __import__(module)
            print(f"✓ {name}")
        except ImportError:
            print(f"✗ {name} - NOT INSTALLED (required)")
            all_installed = False

    for module, name, why in optional:
        try:
            __import__(module)
            print(f"✓ {name}")
        except ImportError:
            print(f"⏭ {name} - not installed (optional: {why})")

    return all_installed


def check_mock_site():
    """The default demo target is the bundled mock site, so it must exist."""
    print("\n🧪 Checking bundled mock site...")
    home = settings.mock_site_home_path.lstrip("/")
    page = project_root / "mock_site" / home
    if not page.exists():
        print(f"✗ Missing {page}")
        print(f"  MOCK_SITE_HOME_PATH={settings.mock_site_home_path} points at nothing.")
        return False
    print(f"✓ mock_site/{home} present")
    print(f"  Serve it with: python -m uvicorn backend.app.mock_site_server:app "
          f"--port {settings.mock_site_port}")
    return True


def check_playwright():
    """Check that Playwright can actually launch and close a browser.

    This used to only read ``p.chromium.executable_path``, which is a string
    lookup that succeeds even when launching is impossible -- so the preflight
    reported "Chromium browser available" while every real run failed with
    "Browser launch failed". Launch a browser for real instead.
    """
    print("\n🎬 Checking Playwright browsers...")
    try:
        from backend.app.modules.automation.playwright_engine import PlaywrightEngine
    except Exception as e:
        print(f"✗ Could not import the Playwright engine: {type(e).__name__}: {e}")
        return False

    engine = PlaywrightEngine(headless=True)
    if not engine.launch_browser():
        print("✗ Chromium could not be launched")
        print(f"  {engine.launch_error}")
        print("  If the binary is missing: python -m playwright install chromium")
        return False

    try:
        print("✓ Chromium launches and closes cleanly")
    finally:
        engine.close()
    return True


def check_api_keys():
    """Check if required API keys are configured"""
    print("\n🔑 Checking API keys...")

    # settings.llm_configured filters placeholders such as `your_api_key_here`,
    # which are truthy strings and used to read as "configured".
    if not settings.llm_configured:
        print("⚠ OPENROUTER_API_KEY not configured")
        print("  Add your key to .env (the `your_api_key_here` placeholder counts as unset)")
        print("  Without it the pipeline falls back to its built-in mock action plan,")
        print("  which only works against the bundled mock site.")
        return False

    print(f"✓ LLM API key configured (model: {settings.openrouter_model})")
    return True


def check_database_connection():
    """Check database connection"""
    print("\n💾 Checking database connection...")
    
    if not settings.database_url:
        print("⏭ Database skipped (not configured - using local storage only)")
        return True
    
    try:
        from backend.app.modules.database.connection import db
        if db.engine is None:
            print("✗ Database connection failed - check DATABASE_URL in .env")
            return False
        
        with db.get_session() as session:
            session.execute("SELECT 1")
        print("✓ Database connection OK")
        return True
    except Exception as e:
        print(f"⚠ Database unavailable: {e} (continuing with local storage)")
        return True


def print_startup_info():
    """Print startup information"""
    print("\n" + "="*60)
    print("DemoGen - AI-Powered Demo Video Generator")
    print("="*60)
    print(f"\n📖 Documentation: See README.md")
    print(f"🌐 API Docs: http://localhost:{settings.api_port}/api/docs")
    print(f"🎨 Web UI: http://localhost:{settings.api_port}")
    print(f"🧪 Mock Site: http://localhost:{settings.mock_site_port}")
    print(f"📝 Logs: {settings.log_file}")
    print(f"\n✨ Ready to generate demos!")
    print("="*60 + "\n")


def setup():
    """Run complete setup"""
    print("\n🚀 DemoGen Setup Starting...\n")
    
    # Setup directories
    setup_directories()
    
    # Check dependencies
    if not check_dependencies():
        print("\n⚠ Some dependencies are missing. Run:")
        print("  pip install -r requirements.txt")
        return False
    
    # Check Playwright
    if not check_playwright():
        print("\n⚠ Playwright browsers not installed. Run:")
        print("  python -m playwright install chromium --with-deps")
        return False
    
    # Check API keys
    if not check_api_keys():
        print("\n⚠ Warning: OpenRouter API key not configured")
        print("  Add OPENROUTER_API_KEY to .env file")

    # The bundled mock site is the default demo target
    if not check_mock_site():
        return False

    # Check database (optional)
    check_database_connection()
    
    # Print startup info
    print_startup_info()
    
    return True


if __name__ == "__main__":
    success = setup()
    sys.exit(0 if success else 1)
