# DemoGen — Audit, Fixes and Suggestions

Reviewed 2026-09-05 against `C:\projects\DemoGen`. Everything under "Fixed" is already
applied and compile-verified in your working tree. Everything under "Needs your call"
is flagged but untouched.

---

## The one thing that mattered most

`mock_site/` did not exist. `USE_MOCK_SITE_BY_DEFAULT` and `MOCK_SITE_HOME_PATH`
both pointed at it, `backend/app/mock_site_server.py` served it, the README
documented it, and the pipeline had a hand-written action plan
(`_build_mock_actions`) targeting `#create-project-btn` / `#project-name` /
`#tier` / `#submit-btn` inside it. The folder was simply absent, so the
documented default path could never produce a video. That is almost certainly
the root cause of most of the "it doesn't work" experience.

I built it: `mock_site/index.html` plus `mock_site/dashboard.html`, a GPU
fleet-allocation console carrying exactly the four ids the fallback plan drives,
with a deterministic layout so every recording is frame-identical.

---

## Errors fixed

### Would crash or silently do nothing

| Where | Problem |
|---|---|
| `config.py` | `openrouter_api_key` had no default, so a missing key was a `ValidationError` at import — the app refused to start rather than reporting a config problem |
| `config.py` | pydantic-settings defaults to `extra="forbid"`; one stray line in `.env` crashed the whole app at import. Now `extra="ignore"` |
| `config.py` | deprecated `class Config:` instead of `SettingsConfigDict` |
| `backend/app/main.py` | `allow_origins=["*"]` with `allow_credentials=True` — browsers reject that combination outright, so CORS silently failed |
| `backend/app/main.py` | `uvicorn.run(app, reload=True)` — `reload` is ignored when an app *object* is passed. Now passes the import string |
| `routes.py` | `validate_prompt`'s `except Exception` caught the `HTTPException` it had just raised and re-wrapped it, garbling its own error message |
| `routes.py` | `/generate` required 10 chars, `/validate-prompt` required 5 — the UI's pre-flight check rejected prompts the generator would have accepted. Unified as `MIN_PROMPT_LENGTH` |
| `routes.py` | `DemoResponse` didn't declare `duration` or `quality_score`, and FastAPI's `response_model` silently strips undeclared fields — so the UI's Duration and Quality Score always read `-` |
| `routes.py` | no `/api/health` route existed, but `api.js` polled `/api/health`. Every page load logged a 404 |
| `routes.py` | `_resolve_video_file` only looked for `.mp4` with predictable names; Playwright writes `.webm` with random-hash filenames, so finished recordings were reported as missing |
| `pipeline.py` | the mock action plan clicked an `<option>` element. Chromium renders dropdowns outside the page, so that click can only ever time out. Now uses `select_option()` |
| `gemini_engine.py` | `genai.GenerativeModel("gemini-2-0-flash")` — hyphens instead of dots. A nonexistent model id, so every screenshot review returned a provider 404 |
| `dom_monitor.py` | the moved-element comparison dereferenced `position` without a guard; a `None` raised `TypeError` mid-comparison |
| `dom_monitor.py` | drift score was a flat `0.1` per item, so a single high-severity structural change scored `0.9` — above the `0.85` threshold — and regeneration **never** fired. Now severity-weighted and clamped |
| `frontend/static/js/api.js` | every failure surfaced as `API Error: 500 Internal Server Error`; the server's actual `detail` was discarded. This is why debugging was painful |
| `frontend/static/js/api.js` | `generateDemo` hardcoded `use_mock_site: false`, so the mock site was unreachable from the UI even once it existed |

### "Browser launch failed" — the auto-reload trap

Found on the first real run, and caused by one of my own fixes. Full chain:

1. `main.py` used to call `uvicorn.run(app, reload=True)` with an app *object*, so `reload` was silently ignored. I changed it to pass the import string, which finally made reload take effect.
2. uvicorn sets `use_subprocess = bool(reload or workers > 1)`, and `uvicorn/loops/asyncio.py` then does `asyncio.set_event_loop_policy(WindowsSelectorEventLoopPolicy())` on Windows. That is a **process-wide** change.
3. Playwright's sync API builds its own loop with `asyncio.new_event_loop()`, so it inherits that policy.
4. On Windows only `ProactorEventLoop` implements subprocesses. `SelectorEventLoop` inherits `BaseEventLoop._make_subprocess_transport`, which is `raise NotImplementedError`.
5. So `asyncio.create_subprocess_exec(node.exe, cli.js, "run-driver")` failed, and because `str(NotImplementedError())` is `""`, the log line read `Could not start Playwright: ` and stopped there.

`python setup.py` passed throughout because no uvicorn ran in that process, so the
default Proactor policy was intact — and because the check only read
`p.chromium.executable_path`, a string lookup that proves nothing about launching.

Fixed in four places:

- `playwright_engine.py` re-asserts `WindowsProactorEventLoopPolicy` immediately before starting Playwright. Safe: changing the policy does not disturb uvicorn's already-running loop, only loops created afterwards.
- `_describe_exc()` now prints the exception *type* when the message is empty, so a messageless error can never again produce a log line that ends at the colon.
- `main.py` no longer ties reload to `APP_DEBUG`. It is off unless `API_RELOAD=true`, and when on it excludes `outputs/`, `logs/` and `temp/` — the watcher was also liable to restart the server mid-generation, because the pipeline writes its video underneath the directory being watched.
- `setup.py`'s Playwright check now launches and closes a real browser, and `pipeline.py` returns `engine.launch_error` instead of the bare string `"Browser launch failed"`, so the cause reaches the UI.

Regression test: `test_playwright_launch.py` (6 assertions, no browser needed).

### The placeholder-key trap

`.env` contains `OPENROUTER_API_KEY=your_api_key_here` and
`GEMINI_API_KEY=your_api_key_here` — copied from `.env.example` and never
filled in. That string is *truthy*, so `if self.api_key:` passed, the app
configured itself with a bogus credential, and calls failed with a provider 401
instead of "no key configured."

Added `config.real_secret()` / `settings.llm_configured`, which treat
`your_*`, `changeme`, `xxx`, `<...>` and friends as unset. `orchestrator.py`,
`gemini_engine.py` and `setup.py` now use it and produce an actionable message.

**This is still the single biggest functional gap: with no real key, every run
uses the built-in rule-based plan, which only works against the bundled mock
site.** Arbitrary URLs need a real key.

### Model-name inconsistency

`gemini_engine.py` used three different model strings in one class:
`self.model` was `gemini-2.0-flash-thinking-exp-01-21` (a retired preview), two
methods hardcoded `gemini-2.0-flash`, one had the typo above — and
`settings.gemini_model` was never read anywhere. All five call sites now use
`self.model`, resolved from config.

Separately, `google/gemma-4-31b-it:free` appeared as a fallback in three places.
There is no Gemma 4. Replaced with the real config default.

---

## Redundancy and v1 leftovers

**Removed:**

- `backend/app/modules/automation/selenium_engine.py` and `selenium>=4.15.0` — nothing imported it after the Playwright migration. Three intentional textual references remain: a `.env` back-compat alias (`SELENIUM_HEADLESS` → `BROWSER_HEADLESS`), its comment, and a deprecated property.
- `test_playwright_video.py` — functionally identical to `test_improved_video.py` (same prompt shape, same POST, same poll, same download). Recoverable via `git show HEAD:test_playwright_video.py`.
- `__version__.py`'s `MODELS` dict — dead *and* wrong (the fake Gemma id, twice).
- Three dead client methods in `api.js`: `getSessions`, `getSession`, `getSessionScript`. No matching routes existed.
- `import os` from `main.py` and `config.py`; unused `HealthResponse` is now actually wired up.

**Still-live leftovers, in `config.py`:**

- `GROQ_API_KEY` / `GROQ_MODEL` / `GROQ_API_BASE` sit alongside the `OPENROUTER_*` trio and mean the same thing. Your provider history is Gemini → Groq → OpenRouter, and the names never caught up: the settings say OpenRouter while `.env`'s `OPENROUTER_API_BASE` points at `api.groq.com`. Confusing but harmless.
- `NEEVCLOUD_URL=https://en.wikipedia.org`. Wikipedia was a stand-in target and is now the *default* when `USE_MOCK_SITE_BY_DEFAULT=false` — which is what your `.env` currently says.
- `AWS_*`, `GCS_*`, `DATABASE_*`, `ELEVENLABS_API_KEY`, `BRAVE_*`, `BOT_CHALLENGE_TIMEOUT_S` — 20-odd settings for features that are off or unimplemented. `FEATURES` in `__version__.py` honestly marks `cloud_storage` and `user_auth` as `False`, but nothing reads that dict either.
- `gemini_engine.py` is reachable only through a lazy import at `video_reviewer.py:169`.

---

## Criticism

**The pipeline is one 1185-line file with one class.** `pipeline.py` does
orchestration, browser driving, action dispatch, narration, composition,
validation, metadata and error recovery. `_execute_automation` alone runs
several hundred lines with nested try/except and inline replanning. This is the
main thing standing between you and being able to change one stage
confidently. Splitting it into `plan / execute / narrate / compose / validate`
stages behind a small interface would let you test each one without a browser.

**`setup.py` is not a packaging script.** It is a preflight doctor, but that
filename is reserved by convention — `pip install .` will try to run it as a
distutils script and fail confusingly. Rename it to `preflight.py` or
`scripts/doctor.py`.

**Generation is synchronous and blocking.** `POST /api/generate` runs the entire
pipeline inline (via `run_in_threadpool`) and can take minutes. The frontend
compensates with `simulateProgress()` — a fake 5-step animation on a 1-second
timer that reports "Composing video..." regardless of what is actually
happening. Every status field in the UI (`automationStatus`, `narrationStatus`,
`videoStatus`, `validationStatus`) is decorative; nothing ever writes to them.
It also means a browser or proxy timeout kills a finished video.

**Error handling swallows too much.** There were bare `except:` clauses, and
several `except Exception` blocks return success-shaped dicts. Combined with
the placeholder-key issue, the app's default behaviour was to look like it
worked while quietly doing something else. Prefer failing loudly at the boundary
and degrading deliberately, with the degradation in the response — the
`status: "partial"` path is the right pattern; extend it.

**No unit tests.** The three root scripts were all slow integration tests that
skipped by default, and all three pointed at the wrong port
(`8000`/`8000`/`8001` while `.env` says `API_PORT=8081`), so they had been
skipping silently. Nothing tested `DriftDetector`'s scoring, the action
planner's parsing, or `_resolve_video_file` — all pure functions, all easy to
test, all previously broken.

**Every file shows as modified in git.** The initial commit stored LF; Windows
editors rewrote everything as CRLF with `core.autocrlf` unset. `git status`
reports ~40 modified files whose diffs are pure line endings, which makes real
review impossible. Added `.gitattributes`; see the cleanup command below.

**Also:** a single "Initial Commit" with no history; `test_output.txt` is 8.5 MB
of UTF-16 PowerShell stderr *tracked in git*, referencing a `test_generate.py`
that no longer exists; `DemoGen-zip.zip` (3.1 MB, untracked) is a full August
snapshot of the project **including `.env`** — don't keep credential files
inside zips in the repo folder.

---

## Suggestions

**High value, small effort**

1. Make generation async. Return a `session_id` immediately, write real stage progress into `metadata.json`, and poll `GET /api/videos/{id}`. This removes the fake progress bar, wires up the four dead status fields, and fixes the timeout risk. The metadata file already exists — it just needs stage granularity.
2. Cache action plans by `(prompt, target_url, dom_hash)`. Re-running the same demo currently re-pays the LLM call. Pairs naturally with the DOM sentinel, which already computes the hash.
3. Add a `--dry-run` that prints the resolved plan without launching a browser. Most failures are planning failures, and today you can only see them by watching a video.
4. Unit-test the pure logic: `DriftDetector.analyze_drift`, `_resolve_video_file`, the action-plan JSON parser. The drift-scoring bug would have been caught by a three-line test.
5. Burn a subtitle track from the narration script. You already have per-step text and timings; a `.vtt` alongside the MP4 is nearly free and makes the videos accessible and skimmable.

**Bigger bets**

6. Self-healing selectors. When a selector misses, you already have the DOM and an LLM — ask for a replacement and retry once, then record the substitution. This is the natural payoff for the sentinel work you've already built and would make demos survive UI changes.
7. Multi-language properly. The dropdown offers six languages, but the *narration script* is generated in English and only the TTS voice changes. Translate the script before synthesis, or generate it in the target language directly.
8. Scene-aware editing. Rather than one continuous recording, capture per-step clips and concatenate with the narration. You get per-step retries, accurate durations, and the ability to re-record one broken step instead of the whole demo.
9. A real template system. `/api/demos` returns three hardcoded dicts. Move them to YAML with prompt, target URL and expected selectors, and let the contract test validate all of them.

---

## Needs your call

- `DemoGen-zip.zip` (3.1 MB, contains `.env`) — delete, or move outside the repo?
- `test_output.txt` (8.5 MB, tracked) — untrack with `git rm --cached test_output.txt` then delete? Both are now in `.gitignore`, but ignoring does not untrack.
- `.env` says `USE_MOCK_SITE_BY_DEFAULT=false`, so direct API calls target Wikipedia. The web UI is unaffected (it prefills the mock URL from `/api/health`), but flip it to `true` if you want API calls to default to the mock site too.
- `setup.py` → `preflight.py` rename.
- Line-ending cleanup: `git add --renormalize .` then commit. Do this **before** your next real change or the two will be indistinguishable.
- Collapsing the `GROQ_*` / `OPENROUTER_*` duplication into provider-neutral `LLM_*` names.

---

## Running it

From `C:\projects\DemoGen` in PowerShell. Your venv already has all 67 required
packages — `imageio` was the only gap, and the Playwright migration made it
unnecessary.

```powershell
.\venv\Scripts\Activate.ps1

# Once: install the browser binary and confirm the environment.
python -m playwright install chromium
python setup.py

# Terminal 1 - the demo target.
python -m uvicorn backend.app.mock_site_server:app --port 8001

# Terminal 2 - the app.
python -m backend.app.main
```

Open `http://localhost:8081` (your `.env` sets `API_PORT=8081`). The target URL
field prefills with `http://localhost:8001/dashboard.html`. Enter a prompt of at
least 10 characters — "Show how to create a new GPU project" works — and
generate. Expect `status: "partial"` and a playable recording: partial is
correct here, because with a placeholder API key the run uses the fallback plan.

Then:

```powershell
pytest test_mock_site_contract.py -v   # fast, no server needed
pytest test_playwright_launch.py -v    # fast, no browser needed
pytest test_api.py -v                  # needs the app running
```

Do not set `API_RELOAD=true` while generating a video. It breaks Playwright's
driver on Windows (see "the auto-reload trap" above) and the file watcher can
restart the server mid-run.

To get non-mock targets working, put a real key in `.env` under
`OPENROUTER_API_KEY` — Groq and OpenRouter both have free tiers, and
`OPENROUTER_API_BASE` already points at Groq.

---

## Verification performed

No network access in my sandbox, so I could not boot the server myself. Verified
statically instead:

- every project `.py` compiles; both JS files pass `node --check`; the dashboard's inline JS parses
- every import in the project resolves against your venv's 67 installed packages — the sole exception is `imageio` at `gemini_engine.py:247`, which is inside a `try/except ImportError` that degrades to "skipped"
- all 7 endpoints `api.js` calls exist as declared routes (scripted comparison)
- the mock site serves HTTP 200 on `/`, `/index.html`, `/dashboard.html`
- all 5 plan-vs-DOM contract assertions pass against the real files; a scripted walk through the flow allocated exactly 16 GPUs (36→52) and settled the row to Running with no exceptions
- no dangling references to `selenium_engine`, `SeleniumEngine`, `test_playwright_video`, `gemma-4`, or `gemini-2-0-flash` outside explanatory comments

**Unverified:** anything requiring a live browser or network — actual Playwright
recording, gTTS, FFmpeg composition, and the real end-to-end run. Those are what
the commands above will exercise.
