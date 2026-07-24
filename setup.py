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
    dependencies = [
        ("fastapi", "FastAPI"),
        ("playwright", "Playwright"),
        ("requests", "Requests"),
        ("gtts", "Google TTS"),
        ("imageio_ffmpeg", "ImageIO FFmpeg"),
        ("sqlalchemy", "SQLAlchemy"),
        ("psycopg2", "psycopg2"),
    ]
    
    print("\n📦 Checking dependencies...")
    all_installed = True
    
    for module, name in dependencies:
        try:
            __import__(module)
            print(f"✓ {name}")
        except ImportError:
            print(f"✗ {name} - NOT INSTALLED")
            all_installed = False
    
    return all_installed


def check_playwright():
    """Check Playwright browser installation"""
    print("\n🎬 Checking Playwright browsers...")
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            # Try to check browser availability
            try:
                p.chromium.executable_path
                print("✓ Chromium browser available")
            except:
                print("✗ Chromium browser NOT found")
                print("  Run: python -m playwright install chromium --with-deps")
                return False
    except Exception as e:
        print(f"✗ Error checking browsers: {e}")
        return False
    
    return True


def check_api_keys():
    """Check if required API keys are configured"""
    print("\n🔑 Checking API keys...")
    
    key = getattr(settings, "openrouter_api_key", None) or getattr(settings, "groq_api_key", None)
    if not key or str(key).startswith("your_"):
        print("⚠ OPENROUTER_API_KEY not configured")
        print("  Add your key to .env file")
        return False
    else:
        model = getattr(settings, "openrouter_model", None) or "google/gemma-4-31b-it:free"
        print(f"✓ OpenRouter API key configured (model: {model})")
    
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
    
    # Check database (optional)
    check_database_connection()
    
    # Print startup info
    print_startup_info()
    
    return True


if __name__ == "__main__":
    success = setup()
    sys.exit(0 if success else 1)
