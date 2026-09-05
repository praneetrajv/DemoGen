# DemoGen v0.1.0

## AI-Powered Demo Video Generator

**DemoGen** automatically generates professional demo videos from natural-language instructions.

Describe what you want to demonstrate, provide a target website, and DemoGen uses an LLM to plan browser interactions, executes them with Playwright, records the browser, generates narration, and composes everything into a final MP4 video.

DemoGen also includes a **bundled deterministic mock website**, rule-based fallback planning, DOM drift detection, automatic replanning, and video-quality validation.

---

## ✨ Features

* **LLM-Powered Planning**

  * Converts natural-language prompts into structured browser automation actions.
  * Supports OpenAI-compatible APIs such as OpenRouter/Groq.
  * Supports Google Gemini.

* **Browser Automation**

  * Uses Playwright with local Chromium.
  * Supports navigation, clicking, filling forms, scrolling, waiting, and dropdown selection.
  * Includes fallback action planning for the bundled mock website.

* **Screen Recording**

  * Records browser automation at configurable resolution and frame rate.
  * Default configuration: 1080p / 30 FPS.

* **Text-to-Speech Narration**

  * Generates narration for individual automation steps.
  * Supports gTTS.
  * ElevenLabs support is available as an optional provider.

* **Video Composition**

  * Uses FFmpeg to combine screen recordings and narration.
  * Produces MP4 output.

* **DOM Drift Detection**

  * Detects changes to the target website's DOM.
  * Uses severity-weighted drift scoring.
  * Can recommend/regenerate demos when significant UI changes are detected.

* **Automatic Replanning**

  * If an automation action fails, the current DOM state can be sent back to the LLM.
  * Supports multiple replanning attempts.

* **Video Validation**

  * Performs rule-based checks such as duration, resolution, audio presence, and action completion.
  * Supports Gemini-based visual review when configured.

* **Bundled Mock Website**

  * Provides a deterministic GPU fleet-management demo target.
  * Allows the complete automation flow to be exercised without depending on an external website or LLM API.
  * Useful for development and testing.

* **Web UI**

  * Browser-based interface for submitting demo prompts.
  * Displays generation status and generated-video metadata.
  * Provides video download functionality.

---

# 🏗️ Architecture

```text
                         Natural Language Prompt
                                  │
                                  ▼
                         ┌──────────────────┐
                         │    DOM Fetch     │
                         │                  │
                         │ Extract links,   │
                         │ buttons, inputs  │
                         └────────┬─────────┘
                                  │
                                  ▼
                         ┌──────────────────┐
                         │   LLM Planner    │
                         │                  │
                         │ OpenRouter/Groq  │
                         │ or Gemini        │
                         └────────┬─────────┘
                                  │
                                  ▼
                         ┌──────────────────┐
                         │  TTS Generation  │
                         │                  │
                         │ gTTS / ElevenLabs│
                         └────────┬─────────┘
                                  │
                                  ▼
                         ┌──────────────────┐
                         │    Automation    │
                         │                  │
                         │ Playwright +     │
                         │ Chromium         │
                         └────────┬─────────┘
                                  │
                                  ▼
                         ┌──────────────────┐
                         │ Video Recording  │
                         │                  │
                         │ Browser capture  │
                         └────────┬─────────┘
                                  │
                                  ▼
                         ┌──────────────────┐
                         │    Composer      │
                         │                  │
                         │ FFmpeg + audio   │
                         └────────┬─────────┘
                                  │
                                  ▼
                         ┌──────────────────┐
                         │    Validator     │
                         │                  │
                         │ Rules + optional  │
                         │ Gemini Vision    │
                         └────────┬─────────┘
                                  │
                                  ▼
                           Final Demo Video
```

---

# 🔄 How It Works

A typical DemoGen run follows these stages:

### 1. Prompt Submission

The user provides a natural-language instruction such as:

```text
Show how to create a new GPU project
```

along with a target URL.

---

### 2. DOM Fetch

DemoGen loads the target page and extracts relevant interactive elements such as:

* Links
* Buttons
* Input fields
* Select/dropdown elements
* Other actionable DOM elements

This DOM information gives the planner the current state of the website.

---

### 3. LLM Planning

The planner converts the user's request and available DOM information into structured browser actions.

Conceptually:

```text
User Prompt
     │
     ▼
Current DOM
     │
     ▼
LLM
     │
     ▼
Structured Action Plan
```

An action plan can contain operations such as:

```text
navigate
click
fill
select_option
scroll
wait
```

The planner is designed to work with OpenAI-compatible chat APIs as well as Gemini.

---

### 4. Narration Generation

Each planned step can have an associated narration script.

For example:

```text
Step 1:
"Open the GPU project dashboard."

Step 2:
"Enter a name for the new project."

Step 3:
"Select the required GPU tier."

Step 4:
"Create the project."
```

The narration is converted into audio using the configured TTS provider.

---

### 5. Browser Automation

Playwright launches Chromium and executes the action plan against the target website.

For the bundled mock site, DemoGen also contains a deterministic fallback plan.

The mock site's action flow uses elements such as:

```text
#create-project-btn
#project-name
#tier
#submit-btn
```

Dropdowns are handled using Playwright's `select_option()` mechanism rather than attempting to click an `<option>` element directly.

---

### 6. Screen Recording

The browser session is recorded while the automation executes.

Default configuration:

```text
Resolution: 1080p
Frame rate: 30 FPS
Codec: libx264
```

---

### 7. Video Composition

The screen recording and generated narration are combined using FFmpeg.

The final output is an MP4 video containing:

```text
Browser Recording
       +
Narration Audio
       ↓
    Final MP4
```

---

### 8. Validation

The generated video is checked for basic quality and correctness.

Validation can include:

* Video existence
* Duration
* Resolution
* Audio presence
* Action completion
* Optional Gemini visual review

A generation can return:

```text
status: "success"
```

or:

```text
status: "partial"
```

A `partial` result indicates that a usable result was produced but one or more quality/completeness checks were not fully satisfied.

---

# 🧠 Automatic Replanning

DemoGen supports feedback-driven recovery when browser actions fail.

The basic loop is:

```text
Execute Action
      │
      ├── Success ──────────────► Continue
      │
      ▼
   Failure
      │
      ▼
Capture Current DOM
      │
      ▼
Send DOM + Context to LLM
      │
      ▼
Generate Replacement Plan
      │
      ▼
Retry
```

The pipeline supports up to three replanning attempts.

This makes the automation less dependent on a completely static UI.

---

# 🛡️ DOM Drift Detection

Websites change over time.

A selector that works today may stop working after a frontend update.

DemoGen includes a DOM monitoring component that compares the current page structure against the expected state.

The detector considers changes such as:

* Added elements
* Removed elements
* Changed elements
* Moved elements
* Structural changes

Drift is scored using severity-weighted changes rather than treating every difference equally.

This allows DemoGen to distinguish between:

```text
Minor UI change
       ↓
Probably safe
```

and:

```text
Major structural/interactive change
       ↓
Recommend regeneration
```

The system can expose this through the DOM check/regeneration API.

---

# 🧪 Bundled Mock Website

DemoGen includes a deterministic mock target under:

```text
mock_site/
```

The mock application represents a GPU fleet-allocation console.

It contains:

```text
mock_site/
├── index.html
└── dashboard.html
```

The dashboard contains the controls required by the built-in fallback automation plan.

The mock site is useful because it provides a stable environment for testing:

* DOM extraction
* Action planning
* Playwright automation
* Screen recording
* Video composition
* Validation
* API integration

It also means DemoGen can demonstrate its core workflow without requiring a third-party website.

---

# 🔑 LLM Configuration

DemoGen supports two primary LLM configuration paths:

### OpenAI-Compatible API

The application can communicate with OpenAI-compatible chat-completion endpoints.

For example:

```env
OPENROUTER_API_KEY=your_api_key
OPENROUTER_MODEL=openai/gpt-oss-20b
OPENROUTER_API_BASE=https://api.groq.com/openai/v1/chat/completions
```

The configuration names currently retain the historical `OPENROUTER_*` naming even when the configured endpoint is a compatible provider such as Groq.

### Google Gemini

```env
GEMINI_API_KEY=your_api_key
GEMINI_MODEL=gemini-2.0-flash
```

The configured Gemini model is used consistently by the Gemini integration rather than relying on multiple hardcoded model names.

> Model availability changes over time. Use a currently supported model ID for your provider.

---

# ⚠️ API Keys and Fallback Behaviour

API keys are optional for running the bundled mock-site workflow.

DemoGen detects common placeholder values such as:

```text
your_api_key_here
changeme
xxx
<...>
```

as unconfigured credentials.

If no valid LLM credential is available:

```text
No valid API key
       │
       ▼
Rule-based fallback plan
       │
       ▼
Bundled mock site
```

This fallback is intended for the deterministic mock environment.

**Arbitrary external websites generally require a valid LLM API key.**

Never commit real API keys to Git.

The `.env` file should remain ignored by version control.

---

# 🛠️ Tech Stack

| Layer              | Technology                                   |
| ------------------ | -------------------------------------------- |
| Language           | Python 3.12                                  |
| Backend            | FastAPI + Uvicorn                            |
| LLM                | OpenAI-compatible Chat API / Google Gemini   |
| Browser Automation | Playwright + Chromium                        |
| TTS                | gTTS / ElevenLabs                            |
| Video              | FFmpeg                                       |
| FFmpeg Packaging   | imageio-ffmpeg                               |
| Database           | PostgreSQL + SQLAlchemy + Alembic (optional) |
| Frontend           | Vanilla HTML / CSS / JavaScript              |
| Containerization   | Docker                                       |
| Testing            | pytest                                       |

---

# 📋 Prerequisites

Install the following before running DemoGen:

* Python 3.12+
* Chromium through Playwright
* FFmpeg
* At least one supported LLM API key for arbitrary external targets

Playwright browser installation:

```bash
python -m playwright install chromium --with-deps
```

On Windows, if `--with-deps` is not appropriate for your environment, install Chromium with:

```bash
python -m playwright install chromium
```

---

# 🚀 Installation

## 1. Clone the repository

```bash
git clone <repository-url>
cd DemoGen
```

---

## 2. Create a virtual environment

### Windows

```powershell
python -m venv .venv
.venv\Scripts\activate
```

### Linux / macOS

```bash
python -m venv .venv
source .venv/bin/activate
```

---

## 3. Install dependencies

```bash
pip install -r requirements.txt
```

---

## 4. Install Chromium

```bash
python -m playwright install chromium
```

---

## 5. Configure environment variables

Create `.env` from `.env.example`.

Example:

```env
# LLM
OPENROUTER_API_KEY=your_api_key_here
OPENROUTER_MODEL=openai/gpt-oss-20b
OPENROUTER_API_BASE=https://api.groq.com/openai/v1/chat/completions

GEMINI_API_KEY=your_api_key_here
GEMINI_MODEL=gemini-2.0-flash

# Target Website
NEEVCLOUD_URL=http://localhost:8001/dashboard.html

# TTS
TTS_PROVIDER=gtts

# Server
API_PORT=8081
API_HOST=0.0.0.0

# Browser
BROWSER_PROVIDER=local
USE_BRAVE=false
BROWSER_HEADLESS=false

# Video
VIDEO_QUALITY=1080p
VIDEO_FPS=30
VIDEO_CODEC=libx264
```

For a local mock-site workflow, configure:

```env
USE_MOCK_SITE_BY_DEFAULT=true
```

For arbitrary external targets, use:

```env
USE_MOCK_SITE_BY_DEFAULT=false
```

and provide a valid LLM API key.

---

# ▶️ Running DemoGen

DemoGen consists of two useful development processes:

1. The mock target website
2. The DemoGen API server

## Terminal 1 — Start the mock site

```powershell
python -m uvicorn backend.app.mock_site_server:app --port 8001
```

The mock site will be available at:

```text
http://localhost:8001
```

The dashboard is:

```text
http://localhost:8001/dashboard.html
```

---

## Terminal 2 — Start DemoGen

```powershell
python -m backend.app.main
```

The default server configuration is:

```text
http://localhost:8081
```

---

## Web UI

Open:

```text
http://localhost:8081
```

The UI can be used to:

1. Enter a natural-language demo request.
2. Select or provide a target URL.
3. Generate the demo.
4. Monitor the generation result.
5. Download the generated video.

Example prompt:

```text
Show how to create a new GPU project
```

---

## API Documentation

FastAPI's interactive documentation is available at:

```text
http://localhost:8081/api/docs
```

---

# 🐳 Docker

Build the image:

```bash
docker build -t demogen .
```

Run the container:

```bash
docker run -p 8000:8000 demogen
```

If using a different application port, configure the container/environment accordingly.

---

# 🔌 API

| Method | Endpoint                        | Description                               |
| ------ | ------------------------------- | ----------------------------------------- |
| `GET`  | `/health`                       | Application health check                  |
| `GET`  | `/api/health`                   | API health check                          |
| `POST` | `/api/generate`                 | Generate a demo video                     |
| `GET`  | `/api/videos/{session_id}`      | Get video metadata/status                 |
| `GET`  | `/api/download/{session_id}`    | Download generated video                  |
| `GET`  | `/api/demos`                    | List available demo templates             |
| `GET`  | `/api/languages`                | List supported narration languages        |
| `POST` | `/api/validate-prompt`          | Validate a generation prompt              |
| `POST` | `/api/dom/check-and-regenerate` | Check DOM drift and optionally regenerate |

---

# 📁 Project Structure

```text
DemoGen/
│
├── backend/
│   └── app/
│       ├── main.py
│       ├── mock_site_server.py
│       │
│       ├── api/
│       │   └── routes.py
│       │
│       └── modules/
│           ├── automation/
│           │   └── ...
│           │
│           ├── database/
│           │   └── ...
│           │
│           ├── llm/
│           │   └── ...
│           │
│           ├── tts/
│           │   └── ...
│           │
│           ├── video/
│           │   └── ...
│           │
│           ├── validation/
│           │   └── ...
│           │
│           └── sentinel/
│               └── ...
│
├── mock_site/
│   ├── index.html
│   └── dashboard.html
│
├── frontend/
│   ├── index.html
│   └── static/
│       ├── css/
│       │   └── styles.css
│       └── js/
│           ├── api.js
│           └── app.js
│
├── outputs/
├── logs/
│
├── config.py
├── pipeline.py
├── setup.py
├── conftest.py
├── requirements.txt
├── Dockerfile
├── .env.example
└── .env
```

---

# 🧩 Core Components

## `pipeline.py`

The main generation pipeline coordinates:

```text
Planning
   ↓
Automation
   ↓
Narration
   ↓
Recording
   ↓
Composition
   ↓
Validation
```

It also contains the current recovery/replanning logic.

> The pipeline is currently centralized in a large orchestration module. Further separation into independent planning, execution, narration, composition, and validation stages is planned for a future version.

---

## `automation/`

Responsible for:

* DOM interaction
* Action planning
* Playwright browser execution
* Action dispatch
* Replanning

---

## `llm/`

Provides integrations for:

* OpenAI-compatible chat endpoints
* Google Gemini

---

## `tts/`

Responsible for generating narration audio.

Current providers include:

```text
gTTS
ElevenLabs
```

---

## `video/`

Responsible for:

* Recording-related processing
* FFmpeg composition
* Video metadata

---

## `validation/`

Performs post-generation checks.

Validation combines deterministic checks with optional model-assisted review.

---

## `sentinel/`

Contains DOM drift detection logic used to identify changes in target websites.

---

# 🧪 Testing

DemoGen includes both contract/integration testing and pure logic that can be tested independently.

## Mock Site Contract Test

This is the fastest test:

```bash
pytest test_mock_site_contract.py -v
```

It verifies that the built-in fallback action plan remains compatible with the mock site's DOM.

---

## API Integration Test

Start the application first, then:

```bash
pytest test_api.py -v
```

The test uses the configured API port.

---

## End-to-End Video Test

```bash
pytest test_improved_video.py -v
```

This exercises the full generation pipeline and can take several minutes because it involves browser automation and video processing.

---

# 🔍 Verification

The current codebase has been statically audited and compile-checked.

The audit verified:

* Python project files compile.
* JavaScript files parse successfully.
* Dashboard inline JavaScript parses.
* Project imports resolve against the development environment, apart from an optional `imageio` import that is guarded by `try/except ImportError`.
* API client routes correspond to declared backend routes.
* Mock-site pages are present.
* Mock-site contract assertions pass.
* The fallback GPU allocation flow completes without exceptions under the deterministic mock-site scenario.
* Removed Selenium and obsolete model references no longer have live code dependencies.

The following require a live environment and are therefore not claimed as statically verified:

* Actual Playwright recording
* Live gTTS generation
* FFmpeg composition in the runtime environment
* Real external LLM requests
* Full end-to-end generation against arbitrary external websites

These can be verified by running the application and integration tests locally.

---

# ⚠️ Current Limitations

DemoGen v0.1.0 is a working prototype rather than a production-ready video-generation platform.

### Synchronous generation

The current `/api/generate` flow performs the generation pipeline through a threadpool while the request remains active.

Long-running generations can therefore be affected by browser, server, or reverse-proxy timeouts.

A future version should return a session ID immediately and process generation as a background job.

---

### Simulated frontend progress

The current frontend includes progress behaviour that is not yet fully connected to real pipeline-stage events.

The intended future architecture is:

```text
Pipeline Stage
      │
      ▼
metadata.json
      │
      ▼
GET /api/videos/{session_id}
      │
      ▼
Real UI Progress
```

---

### Limited selector self-healing

Replanning exists when actions fail, but fully autonomous selector replacement is not yet a dedicated subsystem.

A future version can use the current DOM and failed selector to request a replacement selector from the LLM and retry the individual action.

---

### Narration languages

The application exposes multiple narration languages, but multilingual narration should be considered an area for further improvement.

Changing the TTS voice/language does not automatically guarantee that the generated narration script itself has been translated.

---

### Hardcoded demo templates

The current demo template API contains hardcoded template definitions.

A future version should move templates into a declarative configuration format such as YAML.

---

### Large pipeline module

The main pipeline is currently centralized in `pipeline.py`.

A future refactor should expose smaller interfaces:

```text
Planner
   ↓
Executor
   ↓
Narrator
   ↓
Composer
   ↓
Validator
```

This would improve maintainability and unit testing.

---

# 🗺️ Roadmap

## v0.2

* [ ] Background/async generation jobs
* [ ] Real-time pipeline stage reporting
* [ ] Replace simulated frontend progress with actual status
* [ ] Add unit tests for DOM drift scoring
* [ ] Add unit tests for action-plan parsing
* [ ] Add unit tests for video-file resolution
* [ ] Add dry-run mode for inspecting action plans
* [ ] Cache plans using `(prompt, target_url, dom_hash)`
* [ ] Generate WebVTT subtitles from narration scripts

## v0.3

* [ ] Self-healing selectors
* [ ] Per-step recording and retry
* [ ] Scene-aware video composition
* [ ] Proper multilingual narration generation
* [ ] YAML-based demo templates

## Future

* [ ] More robust browser/session management
* [ ] Persistent job queue
* [ ] Cloud video storage
* [ ] Authentication
* [ ] Production deployment configuration
* [ ] More advanced video editing
* [ ] Analytics and generation history

---

# 🧹 Repository Hygiene

Do not commit:

```text
.env
```

or generated credentials.

Large generated files, debugging output, local snapshots, and archives should also remain outside the repository unless they are intentionally versioned.

If Git reports many files as modified solely because of line-ending differences, normalize the repository before making the next substantive change:

```bash
git add --renormalize .
git status
git commit -m "Normalize repository line endings"
```

---

# 🔐 Security Notes

Never place real credentials in:

* `.env.example`
* README files
* source code
* Git history
* ZIP archives committed to the repository
* test output

Use:

```text
.env
```

for local secrets and keep it in `.gitignore`.

If a real credential has already been committed to Git history, rotate/revoke it rather than relying solely on deleting the file in a later commit.

---

# 📌 Development Notes

The bundled mock site is the recommended starting point when developing or debugging DemoGen.

It provides a controlled environment where failures can be isolated from:

* Third-party website changes
* CAPTCHA/bot protection
* Network instability
* External DOM changes
* LLM planning variability

Once the mock workflow is working, external target websites can be tested with a valid LLM provider configuration.

---

# 📄 License

License information has not yet been finalized.

