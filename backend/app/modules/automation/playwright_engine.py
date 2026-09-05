"""
Playwright Automation Engine

Drives a local Chromium instance and records the session using Playwright's
native context video recorder. Because recording is real-time and handled by
the browser itself, pacing a step is just "hold for N seconds" -- there is no
frame counting, no screenshot loop, and no imageio dependency.

Every action returns a log dict of the shape:
    {"action": str, "status": "completed" | "failed", "timestamp": float, ...}
so the pipeline can branch on ``status`` without inspecting exceptions.
"""

from __future__ import annotations

import asyncio
import logging
import sys
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

logger = logging.getLogger(__name__)


def _describe_exc(exc: BaseException) -> str:
    """Format an exception for a log line, tolerating an empty message.

    ``NotImplementedError()`` stringifies to ``""``, which used to produce
    "Could not start Playwright: " -- a log line that ended at the colon and
    named neither the cause nor the exception type.
    """
    text = str(exc).strip()
    return f"{type(exc).__name__}: {text}" if text else type(exc).__name__


# ----------------------------------------------------------------------
# Windows event-loop policy
# ----------------------------------------------------------------------
# Playwright's sync API launches its Node driver with
# asyncio.create_subprocess_exec, on a loop it builds itself with
# asyncio.new_event_loop() -- so it inherits the process-wide event loop
# *policy* whether we like it or not.
#
# On Windows only ProactorEventLoop implements subprocesses. SelectorEventLoop
# inherits BaseEventLoop._make_subprocess_transport, which raises a bare
# NotImplementedError with no message.
#
# uvicorn installs WindowsSelectorEventLoopPolicy process-wide whenever it
# needs a subprocess of its own -- that is, with reload enabled or
# workers > 1 (see uvicorn/loops/asyncio.py). So merely turning on auto-reload
# was enough to make every single browser launch fail, while the same code
# worked fine when run standalone. Re-assert Proactor immediately before we
# need it.
#
# Changing the policy does not disturb a loop that already exists, so
# uvicorn's running server loop is unaffected; only loops created afterwards
# (i.e. Playwright's) see the new policy.
_POLICY_LOCK = threading.Lock()


def _ensure_subprocess_capable_loop_policy() -> None:
    """On Windows, make ``asyncio.new_event_loop()`` able to spawn subprocesses."""
    if sys.platform != "win32":
        return

    proactor_policy = getattr(asyncio, "WindowsProactorEventLoopPolicy", None)
    if proactor_policy is None:  # pragma: no cover - not Windows
        return

    with _POLICY_LOCK:
        try:
            current = asyncio.get_event_loop_policy()
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("Could not read the event loop policy: %s", _describe_exc(exc))
            return

        if isinstance(current, proactor_policy):
            return

        asyncio.set_event_loop_policy(proactor_policy())
        logger.warning(
            "Swapped asyncio event loop policy %s -> WindowsProactorEventLoopPolicy; "
            "the previous policy cannot spawn the Playwright driver process.",
            type(current).__name__,
        )

# Only real web traffic. Blocks file://, chrome://, view-source:, data: and
# friends, which an LLM-authored plan can otherwise talk us into opening.
ALLOWED_URL_SCHEMES = {"http", "https"}

# Substrings that indicate an interstitial bot wall rather than real content.
# Matched against the page title only -- matching raw HTML produces constant
# false positives on any page that happens to mention verification.
BOT_CHALLENGE_TITLES = (
    "just a moment",
    "attention required",
    "verify you are human",
    "checking your browser",
    "access denied",
    "are you a robot",
)

VIEWPORT = {"width": 1920, "height": 1080}


def _is_navigable(url: str) -> bool:
    """True if ``url`` is an http(s) address we are willing to open."""
    try:
        return urlparse(url).scheme.lower() in ALLOWED_URL_SCHEMES
    except (ValueError, AttributeError):
        return False


class PlaywrightEngine:
    """Browser automation with native video recording."""

    def __init__(
        self,
        headless: bool = False,
        channel: Optional[str] = None,
        executable_path: Optional[str] = None,
        slow_mo_ms: int = 0,
    ):
        self.headless = headless
        self.channel = channel or None
        self.executable_path = executable_path or None
        self.slow_mo_ms = slow_mo_ms
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.logs: List[Dict] = []
        self._video_dir: Optional[Path] = None
        self._recorded_video_path: Optional[str] = None
        # Set whenever launch_browser() returns False, so callers can report
        # *why* instead of a bare "Browser launch failed".
        self.launch_error: Optional[str] = None

    # ------------------------------------------------------------------
    # logging helper
    # ------------------------------------------------------------------
    def _log(self, action: str, status: str, **fields) -> Dict:
        entry = {"action": action, "status": status, "timestamp": time.time()}
        entry.update(fields)
        self.logs.append(entry)
        return entry

    def get_logs(self) -> List[Dict]:
        return list(self.logs)

    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------
    def launch_browser(self) -> bool:
        """Start Playwright and launch Chromium. Returns False on failure."""
        self.launch_error = None
        _ensure_subprocess_capable_loop_policy()

        try:
            self.playwright = sync_playwright().start()
        except NotImplementedError as exc:
            # Only reachable if the policy repair above could not be applied.
            self.launch_error = (
                "This asyncio event loop cannot spawn subprocesses, so the "
                "Playwright driver could not be started "
                f"({_describe_exc(exc)}). On Windows that means a "
                "SelectorEventLoop: start the server without reload "
                "(API_RELOAD=false) or install WindowsProactorEventLoopPolicy."
            )
            logger.error("Could not start Playwright: %s", self.launch_error)
            return False
        except Exception as exc:
            self.launch_error = f"Could not start Playwright ({_describe_exc(exc)})"
            logger.error("%s", self.launch_error)
            return False

        launch_kwargs = {
            "headless": self.headless,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--start-maximized",
            ],
        }
        if self.slow_mo_ms:
            launch_kwargs["slow_mo"] = self.slow_mo_ms
        if self.executable_path:
            # Any Chromium build (e.g. a local Brave install).
            launch_kwargs["executable_path"] = self.executable_path
        elif self.channel:
            launch_kwargs["channel"] = self.channel

        try:
            self.browser = self.playwright.chromium.launch(**launch_kwargs)
            logger.info(
                "Chromium launched (headless=%s, binary=%s)",
                self.headless,
                self.executable_path or self.channel or "bundled",
            )
            return True
        except Exception as exc:
            self.launch_error = f"Chromium failed to launch ({_describe_exc(exc)})"
            logger.error("%s", self.launch_error)
            # Do not leak the driver process if launch failed.
            self._stop_playwright()
            return False

    def create_context(self, video_dir: str = "outputs/videos") -> bool:
        """Open a recording context and a page. Returns False on failure."""
        if not self.browser:
            logger.error("create_context called before launch_browser")
            return False

        self._video_dir = Path(video_dir)
        try:
            self._video_dir.mkdir(parents=True, exist_ok=True)
            self.context = self.browser.new_context(
                record_video_dir=str(self._video_dir),
                record_video_size=VIEWPORT,
                viewport=VIEWPORT,
                locale="en-US",
                timezone_id="America/New_York",
            )
            self.context.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', "
                "{ get: () => undefined });"
            )
            self.page = self.context.new_page()
            self.page.set_default_timeout(15000)
            logger.info("Recording context created (video -> %s)", self._video_dir)
            return True
        except Exception as exc:
            logger.error("Failed to create browser context: %s", exc)
            return False

    def _stop_playwright(self) -> None:
        if self.playwright:
            try:
                self.playwright.stop()
            except Exception as exc:
                logger.warning("Playwright stop failed: %s", exc)
            finally:
                self.playwright = None

    def close(self) -> Optional[str]:
        """Tear down browser + driver and finalize the recording.

        Each stage runs in its own try/finally so a failure in one does not
        orphan a Chromium or driver process. Returns the recorded video path.
        """
        video = None
        try:
            if self.page and not self.page.is_closed():
                video = self.page.video
                # Let the encoder flush the last frame.
                time.sleep(1.0)
        except Exception as exc:
            logger.warning("Could not access page video handle: %s", exc)

        try:
            if self.context:
                # Closing the context is what flushes the .webm to disk.
                self.context.close()
        except Exception as exc:
            logger.warning("Context close failed: %s", exc)
        finally:
            self.context = None
            try:
                if self.browser:
                    self.browser.close()
            except Exception as exc:
                logger.warning("Browser close failed: %s", exc)
            finally:
                self.browser = None
                self._stop_playwright()

        if video is not None:
            try:
                self._recorded_video_path = str(video.path())
            except Exception as exc:
                logger.warning("Video path unavailable after close: %s", exc)

        if not self._recorded_video_path:
            self._recorded_video_path = self._find_recorded_video()

        self.page = None
        logger.info("Browser closed (video=%s)", self._recorded_video_path)
        return self._recorded_video_path

    def _find_recorded_video(self) -> Optional[str]:
        """Fallback: newest non-empty video Playwright wrote to the video dir."""
        if not self._video_dir or not self._video_dir.is_dir():
            return None
        clips = [
            p
            for pattern in ("*.webm", "*.mp4")
            for p in self._video_dir.glob(pattern)
            if p.is_file() and p.stat().st_size > 0
        ]
        if not clips:
            return None
        return str(max(clips, key=lambda p: p.stat().st_mtime))

    @property
    def recorded_video_path(self) -> Optional[str]:
        """Recorded video path. Only populated after :meth:`close`."""
        return self._recorded_video_path

    def __enter__(self) -> "PlaywrightEngine":
        if not self.launch_browser():
            raise RuntimeError("Chromium failed to launch")
        if not self.create_context():
            self.close()
            raise RuntimeError("Browser context failed to open")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    # ------------------------------------------------------------------
    # pacing
    # ------------------------------------------------------------------
    def record_hold(self, seconds: float) -> float:
        """Hold the current view on screen for ``seconds``.

        Playwright records in real time, so holding is a plain sleep -- the
        browser encodes those frames for us. Returns the seconds held so the
        caller can build a wall-clock timeline.
        """
        duration = max(0.0, float(seconds or 0.0))
        if duration:
            time.sleep(duration)
        return duration

    def snapshot_frame(self) -> None:
        """No-op. Kept so callers written against the old screenshot-loop
        recorder keep working; native recording needs no manual frames."""
        return None

    # ------------------------------------------------------------------
    # navigation
    # ------------------------------------------------------------------
    def navigate(self, url: str, wait_time: int = 2000) -> Dict:
        """Navigate to ``url``. Rejects non-http(s) schemes."""
        if not _is_navigable(url):
            logger.error("Refusing to navigate to unsupported URL: %r", url)
            return self._log(
                "navigate", "failed", url=url,
                error=f"Blocked URL scheme (only http/https allowed): {url}",
            )
        try:
            self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
            try:
                self.page.wait_for_load_state("networkidle", timeout=10000)
            except PlaywrightTimeoutError:
                # Long-polling / analytics pages never go idle. Not an error.
                logger.debug("networkidle not reached for %s; continuing", url)
            time.sleep(max(0, wait_time) / 1000)
            logger.info("Navigated to %s", url)
            return self._log("navigate", "completed", url=url)
        except Exception as exc:
            logger.error("Navigation to %s failed: %s", url, exc)
            return self._log("navigate", "failed", url=url, error=str(exc))

    def login(self, url: str, email: str, password: str, wait_time: int = 5000) -> Dict:
        """Fill and submit a login form.

        Reports ``failed`` unless the email field, the password field, AND a
        submit path all actually succeeded -- a login that quietly did nothing
        must not read as success, or the pipeline records a demo of the
        logged-out page and calls it a pass.
        """
        nav = self.navigate(url, wait_time=1500)
        if nav.get("status") != "completed":
            return self._log("login", "failed", error=nav.get("error", "Navigation failed"))

        email_selectors = [
            'input[type="email"]', 'input[name="email"]', "#email",
            'input[placeholder*="email" i]', 'input[name="username"]',
        ]
        password_selectors = [
            'input[type="password"]', 'input[name="password"]', "#password",
            'input[placeholder*="password" i]',
        ]
        submit_selectors = [
            'button[type="submit"]', 'input[type="submit"]',
            'button:has-text("Sign in")', 'button:has-text("Log in")',
            'button:has-text("Login")', 'button:has-text("Submit")',
        ]

        filled_email = self._fill_first(email_selectors, email, "email")
        if not filled_email:
            return self._log("login", "failed", error="Email field not found")

        filled_password = self._fill_first(password_selectors, password, "password")
        if not filled_password:
            return self._log("login", "failed", error="Password field not found")

        if not self._submit_login(submit_selectors, filled_password):
            return self._log("login", "failed", error="Could not submit the login form")

        try:
            self.page.wait_for_load_state("networkidle", timeout=15000)
        except PlaywrightTimeoutError:
            logger.debug("No networkidle after login submit; continuing")
        time.sleep(max(0, wait_time) / 1000)
        logger.info("Login submitted for %s", url)
        return self._log("login", "completed", url=url)

    def _fill_first(self, selectors: List[str], value: str, label: str) -> Optional[str]:
        """Fill the first selector that resolves to a visible field.

        Returns the selector that worked, or None. Never logs ``value``.
        """
        for selector in selectors:
            try:
                field = self.page.locator(selector).first
                if field.count() == 0:
                    continue
                field.fill(value, timeout=5000)
                logger.info("Filled %s field via %s", label, selector)
                return selector
            except (PlaywrightError, PlaywrightTimeoutError) as exc:
                logger.debug("%s selector %s did not work: %s", label, selector, exc)
        return None

    def _submit_login(self, submit_selectors: List[str], password_selector: str) -> bool:
        """Click a submit control, falling back to Enter in the password field."""
        for selector in submit_selectors:
            try:
                button = self.page.locator(selector).first
                if button.count() == 0:
                    continue
                button.click(timeout=5000)
                logger.info("Submitted login via %s", selector)
                return True
            except (PlaywrightError, PlaywrightTimeoutError) as exc:
                logger.debug("Submit selector %s did not work: %s", selector, exc)

        try:
            self.page.press(password_selector, "Enter")
            logger.info("Submitted login by pressing Enter in %s", password_selector)
            return True
        except (PlaywrightError, PlaywrightTimeoutError) as exc:
            logger.warning("Enter-to-submit fallback failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # interactions
    # ------------------------------------------------------------------
    def click(self, selector: str, alt_selectors: Optional[List[str]] = None) -> Dict:
        """Click the first selector that resolves. Scrolls into view first."""
        attempted = [selector] + list(alt_selectors or [])
        errors = []
        for sel in attempted:
            if not sel:
                continue
            try:
                target = self.page.locator(sel).first
                target.scroll_into_view_if_needed(timeout=5000)
                target.click(timeout=8000)
                logger.info("Clicked %s", sel)
                return self._log("click", "completed", selector=sel)
            except (PlaywrightError, PlaywrightTimeoutError) as exc:
                errors.append(f"{sel}: {type(exc).__name__}")
                logger.debug("Click on %s failed: %s", sel, exc)
        logger.error("Click failed for all selectors: %s", attempted)
        return self._log(
            "click", "failed", selector=selector,
            error="No clickable element for " + "; ".join(errors),
        )

    def fill(self, selector: str, text: str) -> Dict:
        """Type ``text`` into ``selector``."""
        try:
            field = self.page.locator(selector).first
            field.scroll_into_view_if_needed(timeout=5000)
            field.fill(text, timeout=8000)
            logger.info("Filled %s", selector)
            return self._log("fill", "completed", selector=selector)
        except (PlaywrightError, PlaywrightTimeoutError) as exc:
            logger.error("Fill on %s failed: %s", selector, exc)
            return self._log("fill", "failed", selector=selector, error=str(exc))

    # Playwright key names; the LLM tends to emit shouty variants.
    _KEY_ALIASES = {
        "ENTER": "Enter", "RETURN": "Enter", "TAB": "Tab", "ESC": "Escape",
        "ESCAPE": "Escape", "SPACE": " ", "BACKSPACE": "Backspace",
        "DELETE": "Delete", "ARROWDOWN": "ArrowDown", "ARROWUP": "ArrowUp",
        "PAGEDOWN": "PageDown", "PAGEUP": "PageUp", "HOME": "Home", "END": "End",
    }

    def press(self, selector: Optional[str], key: str) -> Dict:
        """Press ``key``, scoped to ``selector`` when one is given.

        Unlike the old engine this never silently types the literal word
        "PAGEDOWN" when a key name is unrecognised -- unmapped names go to
        Playwright as-is and a genuine failure is reported as failed.
        """
        resolved = self._KEY_ALIASES.get(str(key).strip().upper(), str(key).strip())
        try:
            if selector:
                self.page.locator(selector).first.press(resolved, timeout=8000)
            else:
                self.page.keyboard.press(resolved)
            logger.info("Pressed %s%s", resolved, f" on {selector}" if selector else "")
            return self._log("press", "completed", selector=selector, key=resolved)
        except (PlaywrightError, PlaywrightTimeoutError) as exc:
            logger.error("Press %s failed: %s", resolved, exc)
            return self._log(
                "press", "failed", selector=selector, key=resolved, error=str(exc)
            )

    def select_option(
        self,
        selector: str,
        value: Optional[str] = None,
        index: Optional[int] = None,
        label: Optional[str] = None,
    ) -> Dict:
        """Choose an option in a <select>.

        Clicking an <option> node does not work in Chromium, which is why the
        old code path for dropdowns silently did nothing.
        """
        try:
            dropdown = self.page.locator(selector).first
            dropdown.scroll_into_view_if_needed(timeout=5000)
            if index is not None:
                dropdown.select_option(index=int(index), timeout=8000)
            elif label is not None:
                dropdown.select_option(label=str(label), timeout=8000)
            else:
                dropdown.select_option(str(value), timeout=8000)
            logger.info("Selected option in %s", selector)
            return self._log("select", "completed", selector=selector, value=value)
        except (PlaywrightError, PlaywrightTimeoutError) as exc:
            logger.error("Select on %s failed: %s", selector, exc)
            return self._log("select", "failed", selector=selector, error=str(exc))

    def hover(self, selector: str) -> Dict:
        """Hover over an element (reveals menus, tooltips)."""
        try:
            target = self.page.locator(selector).first
            target.scroll_into_view_if_needed(timeout=5000)
            target.hover(timeout=8000)
            logger.info("Hovered %s", selector)
            return self._log("hover", "completed", selector=selector)
        except (PlaywrightError, PlaywrightTimeoutError) as exc:
            logger.error("Hover on %s failed: %s", selector, exc)
            return self._log("hover", "failed", selector=selector, error=str(exc))

    def scroll(self, direction: str = "down", amount: int = 500) -> Dict:
        """Smooth-scroll the window by ``amount`` pixels."""
        try:
            pixels = int(amount)
        except (TypeError, ValueError):
            pixels = 500
        if str(direction).lower() == "up":
            pixels = -abs(pixels)
        try:
            self.page.evaluate(
                "px => window.scrollBy({ top: px, behavior: 'smooth' })", pixels
            )
            time.sleep(0.6)
            return self._log("scroll", "completed", direction=direction, amount=pixels)
        except Exception as exc:
            logger.error("Scroll failed: %s", exc)
            return self._log("scroll", "failed", error=str(exc))

    def wait(self, milliseconds: int) -> Dict:
        time.sleep(max(0, int(milliseconds)) / 1000)
        return self._log("wait", "completed", duration_ms=milliseconds)

    def execute_script(self, script: str, arg=None):
        """Evaluate JS in the page. Returns None and logs on failure."""
        try:
            return self.page.evaluate(script, arg) if arg is not None \
                else self.page.evaluate(script)
        except Exception as exc:
            logger.warning("Script evaluation failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # diagnostics
    # ------------------------------------------------------------------
    def capture_screenshot(self, path: str) -> Dict:
        """Save a screenshot to an explicit path (callers pass the session dir)."""
        try:
            destination = Path(path)
            destination.parent.mkdir(parents=True, exist_ok=True)
            self.page.screenshot(path=str(destination))
            return self._log("screenshot", "completed", path=str(destination))
        except Exception as exc:
            logger.warning("Screenshot to %s failed: %s", path, exc)
            return self._log("screenshot", "failed", path=str(path), error=str(exc))

    # Backwards-compatible alias.
    def screenshot(self, path: str) -> Dict:
        return self.capture_screenshot(path)

    def wait_for_bot_challenge(self, timeout: int = 90) -> Dict:
        """Wait out an interstitial bot wall, if one is showing.

        Detection is title-only and returns immediately when the title looks
        normal, so ordinary pages cost nothing. The old implementation
        substring-matched 80KB of raw HTML and stalled for 90s on any page
        whose markup merely contained the word "verification".
        """
        deadline = time.time() + max(0, timeout)
        seen = False
        while True:
            try:
                title = (self.page.title() or "").lower()
            except Exception:
                return self._log("bot_challenge", "completed", detected=False)

            if not any(marker in title for marker in BOT_CHALLENGE_TITLES):
                return self._log("bot_challenge", "completed", detected=seen)

            seen = True
            if time.time() >= deadline:
                logger.error("Bot challenge still present after %ss: %r", timeout, title)
                return self._log(
                    "bot_challenge", "blocked",
                    error=f"Bot challenge did not clear within {timeout}s (title: {title!r})",
                )
            logger.info("Bot challenge detected (%r); waiting...", title)
            time.sleep(2.0)

    _DOM_SUMMARY_JS = """
    () => {
      const visible = (el) => {
        const r = el.getBoundingClientRect();
        if (r.width < 2 || r.height < 2) return false;
        const s = getComputedStyle(el);
        return s.visibility !== 'hidden' && s.display !== 'none' && s.opacity !== '0';
      };
      const ref = (el) => {
        if (el.id) return '#' + CSS.escape(el.id);
        if (el.name) return el.tagName.toLowerCase() + '[name="' + el.name + '"]';
        const c = (el.getAttribute('class') || '').trim().split(/\\s+/)[0];
        return c ? el.tagName.toLowerCase() + '.' + CSS.escape(c)
                 : el.tagName.toLowerCase();
      };
      const out = [];
      const nodes = document.querySelectorAll(
        'a[href], button, input, select, textarea, [role="button"], h1, h2, h3'
      );
      for (const el of nodes) {
        if (out.length >= 60) break;
        if (!visible(el)) continue;
        const tag = el.tagName.toLowerCase();
        const text = (el.innerText || el.value || el.placeholder || '')
          .trim().replace(/\\s+/g, ' ').slice(0, 60);
        out.push({ tag, text, selector: ref(el),
                   type: el.getAttribute('type') || '' });
      }
      return out;
    }
    """

    def get_dom_summary(self) -> str:
        """Compact, token-efficient listing of visible interactive elements.

        Feeds the LLM re-planner selectors that actually exist on the live page.
        """
        elements = self.execute_script(self._DOM_SUMMARY_JS)
        if not elements:
            return ""
        lines = []
        for el in elements:
            label = f' "{el["text"]}"' if el.get("text") else ""
            kind = f' type={el["type"]}' if el.get("type") else ""
            lines.append(f'{el["tag"]}{label}{kind} -> {el["selector"]}')
        return "\n".join(lines)
