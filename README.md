# DemoGen v0.1.0

**AI-Powered Demo Video Generator**

DemoGen automatically generates professional demo videos by combining LLM-driven browser automation, screen recording, and text-to-speech narration. Describe what you want to demo in plain text, and DemoGen does the rest.

---

## Features

- **LLM-Powered Planning** — Uses OpenRouter (Groq/GPT) or Google Gemini to convert text prompts into structured browser automation steps
- **Browser Automation** — Executes planned actions via Selenium or Playwright on Chrome/Brave
- **Screen Recording** — Captures the browser screen during automation at 1080p/30fps
- **Text-to-Speech Narration** — Generates voiceover for each step using gTTS (free) or ElevenLabs (premium)
- **Video Composition** — Merges screen recording with narration into a final MP4 using FFmpeg
- **DOM Drift Detection** — Monitors UI changes and recommends video regeneration when the target site updates
- **Feedback Loops** — Replans failed steps by sending the current DOM state back to the LLM
- **Web UI** — Clean browser-based interface for submitting prompts and downloading generated videos

---

## Architecture

```
Text Prompt
    │
    ▼
┌─────────────┐
│  DOM Fetch   │  Fetch target page, extract interactable elements
└─────┬───────┘
      │
      ▼
┌─────────────┐
│ LLM Planner  │  OpenRouter / Gemini generates browser action steps
└─────┬───────┘
      │
      ▼
┌─────────────┐
│  TTS Engine   │  Generate narration audio for each step (gTTS / ElevenLabs)
└─────┬───────┘
      │
      ▼
┌─────────────┐
│  Automation   │  Selenium/Playwright executes actions while recording screen
└─────┬───────┘
      │
      ▼
┌─────────────┐
│  Composer     │  FFmpeg merges recording + narration into final MP4
└─────┬───────┘
      │
      ▼
┌─────────────┐
│  Validator    │  Rule-based + Gemini Vision quality checks
└─────┬───────┘
      │
      ▼
  Output Video
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.12 |
| Backend | FastAPI + Uvicorn |
| LLM | OpenRouter (Groq), Google Gemini |
| Browser Automation | Selenium, Playwright |
| TTS | gTTS, ElevenLabs, pyttsx3 |
| Video | FFmpeg, MoviePy, imageio |
| Database (optional) | PostgreSQL + SQLAlchemy + Alembic |
| Frontend | Vanilla HTML/CSS/JS |
| Containerization | Docker |

---

## Prerequisites

- **Python 3.12+**
- **FFmpeg** — installed and available in PATH (or use bundled `imageio-ffmpeg`)
- **Chrome** or **Brave** browser installed locally
- **API Keys** — at least one of:
  - [OpenRouter](https://openrouter.ai/) or [Groq](https://groq.com/) API key
  - [Google Gemini](https://ai.google.dev/) API key

---

## Installation

### 1. Clone the repository

```bash
git clone <repository-url>
cd PROJECT
```

### 2. Create and activate a virtual environment

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux/Mac
source .venv/bin/activate
```

### 3. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 4. Install Playwright browsers

```bash
python -m playwright install chromium --with-deps
```

### 5. Configure environment variables

Copy or edit the `.env` file in the project root:

```env
# LLM Configuration (choose one)
OPENROUTER_API_KEY=your_openrouter_or_groq_api_key
OPENROUTER_MODEL=openai/gpt-oss-20b
OPENROUTER_API_BASE=https://api.groq.com/openai/v1/chat/completions

GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-2.0-flash-thinking-exp-01-21

# Target Website
NEEVCLOUD_URL=https://en.wikipedia.org

# TTS Provider (gtts or elevenlabs)
TTS_PROVIDER=gtts

# Server
API_PORT=8081
API_HOST=0.0.0.0

# Browser Settings
BROWSER_PROVIDER=local
USE_BRAVE=false
SELENIUM_HEADLESS=false

# Video Output
VIDEO_QUALITY=1080p
VIDEO_FPS=30
VIDEO_CODEC=libx264
```

> **Warning:** Never commit real API keys to version control. The `.env` file is listed in `.gitignore`.

### 6. Run setup script (optional)

Creates required directories and verifies dependencies:

```bash
python setup.py
```

---

## Running the Project

### Start the server

```bash
python backend/app/main.py
```

The server starts on `http://localhost:8081` (configurable via `API_PORT`).

- **Web UI:** `http://localhost:8081`
- **API Docs:** `http://localhost:8081/api/docs`

### Start the mock site (for development)

```bash
python -m uvicorn backend.app.mock_site_server:app --port 8001
```

Serves mock HTML pages for testing automation without a real website.

### Run with Docker

```bash
docker build -t demogen .
docker run -p 8000:8000 demogen
```

### Run tests

```bash
pytest test_api.py
pytest test_improved_video.py
pytest test_playwright_video.py
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/generate` | Generate a demo video from a text prompt |
| `GET` | `/api/videos/{session_id}` | Get video metadata and status |
| `GET` | `/api/download/{session_id}` | Download the generated video |
| `GET` | `/api/demos` | List available demo templates |
| `POST` | `/api/validate-prompt` | Validate a prompt before generation |
| `POST` | `/api/dom/check-and-regenerate` | Check for DOM drift and regenerate if needed |

---

## Project Structure

```
PROJECT/
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI entry point
│   │   ├── mock_site_server.py     # Mock site server for dev
│   │   ├── api/
│   │   │   └── routes.py           # API route definitions
│   │   └── modules/
│   │       ├── automation/         # Selenium & Playwright engines
│   │       ├── database/           # SQLAlchemy models & connection
│   │       ├── llm/                # OpenRouter & Gemini integration
│   │       ├── tts/                # Text-to-speech generation
│   │       ├── video/              # FFmpeg video composition
│   │       ├── validation/         # Video quality checks
│   │       └── sentinel/           # DOM drift detection
│   └── mock_site/                  # Mock HTML pages
├── frontend/
│   ├── index.html                  # Web UI
│   └── static/
│       ├── css/styles.css
│       └── js/
│           ├── api.js              # API client
│           └── app.js              # Frontend logic
├── outputs/                        # Generated videos & session data
├── logs/                           # Application logs
├── config.py                       # Pydantic settings (.env loader)
├── pipeline.py                     # Main demo generation pipeline
├── setup.py                        # Setup & dependency checks
├── requirements.txt                # Python dependencies
├── Dockerfile                      # Docker configuration
└── .env                            # Environment variables
```

---

## How It Works

1. **User submits** a prompt (e.g., "Show how to search for Python on Wikipedia") and a target URL
2. **DOM Fetch** retrieves the page and extracts links, buttons, and input fields
3. **LLM Planning** converts the prompt into a sequence of browser actions (navigate, click, fill, scroll, wait)
4. **Narration Generation** creates per-step voiceover audio via gTTS or ElevenLabs
5. **Automation Execution** launches a real browser, executes each action, and records the screen
6. **Video Composition** merges the screen recording with concatenated narration into a 1080p MP4
7. **Validation** checks duration, resolution, audio presence, and action completion
8. **Output** is saved and served via the API for download

The pipeline includes automatic replanning — if actions fail, the current DOM is sent back to the LLM for up to 3 replanning attempts.

---

## License

[Add your license here]
