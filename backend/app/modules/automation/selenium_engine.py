import os
import time
import logging
import threading
from typing import Dict, List, Optional
from pathlib import Path
from io import BytesIO

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException

from PIL import Image
import numpy as np
import imageio

logger = logging.getLogger(__name__)

# Realistic desktop Chrome UA — headless / automation defaults are often blocked.
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

# Strong signals of an interstitial bot wall (not just a captcha widget on a form).
_BOT_WALL_MARKERS = (
    "cf-browser-verification",
    "cf-challenge",
    "challenge-platform",
    "challenges.cloudflare.com",
    "cdn-cgi/challenge",
    "just a moment",
    "checking your browser",
    "attention required",
    "enable javascript and cookies to continue",
    "verify you are human",
    "verify that you are human",
    "human verification",
    "please complete the security check",
    "unusual traffic from your computer",
    "are you a robot",
    "px-captcha",
    "captcha-delivery.com",
    "geo.captcha-delivery.com",
)

# Title-only patterns for interstitial pages
_BOT_WALL_TITLES = (
    "just a moment",
    "attention required",
    "security check",
    "access denied",
    "please wait",
    "checking your browser",
    "verify you are human",
    "bot detection",
)

# Selectors that almost always mean an interstitial wall (not a form widget)
_BOT_WALL_SELECTORS = (
    "#challenge-form",
    "#challenge-running",
    "#cf-challenge-running",
    ".cf-browser-verification",
    "iframe[src*='challenges.cloudflare']",
    "#px-captcha",
)


class SeleniumEngine:
    """Browser automation engine using Selenium with continuous video recording"""

    def __init__(
        self,
        headless: bool = True,
        binary_path: Optional[str] = None,
        user_data_dir: Optional[str] = None,
        profile_dir: Optional[str] = None,
        debugger_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ):
        self.headless = headless
        self.binary_path = binary_path
        self.user_data_dir = user_data_dir
        self.profile_dir = profile_dir
        self.debugger_address = debugger_address
        self.user_agent = user_agent or DEFAULT_USER_AGENT
        self.driver = None
        self.logs = []
        self._recorded_video_path = None
        self._recording = False
        self._record_thread = None
        self._video_writer = None
        self._latest_frame = None
        self._attached_to_debugger = False
        self._frame_lock = threading.Lock()
        self._total_frames = 0
        self._record_fps = 5

    def launch_browser(self) -> bool:
        """Initialize browser instance with anti-detection defaults."""
        # Prefer attaching to a real browser (best for bot-protected sites).
        if self.debugger_address:
            if self._try_attach_debugger():
                return True
            logger.warning(
                "Could not attach to debugger at %s; launching a new browser instead.",
                self.debugger_address,
            )

        try:
            options = self._build_chrome_options()
            logger.info(
                "Initializing Selenium Chrome driver (headless=%s, binary=%s)...",
                self.headless,
                self.binary_path or "system Chrome",
            )
            self.driver = webdriver.Chrome(options=options)
            self.driver.set_window_size(1920, 1080)
            self._apply_stealth_patches()
            return True
        except Exception as e:
            logger.error(f"Failed to launch Selenium browser: {e}")
            return False

    def _try_attach_debugger(self) -> bool:
        """Attach to an already-running Chrome/Brave with remote debugging."""
        try:
            options = Options()
            options.add_experimental_option("debuggerAddress", self.debugger_address)
            if self.binary_path:
                options.binary_location = self.binary_path
            logger.info("Attaching Selenium to browser at %s...", self.debugger_address)
            self.driver = webdriver.Chrome(options=options)
            self._attached_to_debugger = True
            # Attached sessions already look like a normal browser; light stealth only.
            self._apply_stealth_patches(light=True)
            return True
        except Exception as e:
            logger.warning(f"Debugger attach failed: {e}")
            self.driver = None
            self._attached_to_debugger = False
            return False

    def _build_chrome_options(self) -> Options:
        options = Options()

        # Headless is heavily fingerprinted by Cloudflare / bot walls.
        if self.headless:
            options.add_argument("--headless=new")
            options.add_argument("--disable-gpu")
            options.add_argument("--hide-scrollbars")
            options.add_argument("--force-device-scale-factor=1")

        if self.binary_path:
            options.binary_location = self.binary_path

        if self.user_data_dir:
            options.add_argument(f"--user-data-dir={self.user_data_dir}")
        if self.profile_dir:
            options.add_argument(f"--profile-directory={self.profile_dir}")

        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--start-maximized")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-infobars")
        options.add_argument("--lang=en-US,en")
        options.add_argument(f"--user-agent={self.user_agent}")

        # Reduce automation fingerprints
        options.add_experimental_option(
            "excludeSwitches", ["enable-automation", "enable-logging"]
        )
        options.add_experimental_option("useAutomationExtension", False)
        options.add_experimental_option(
            "prefs",
            {
                "credentials_enable_service": False,
                "profile.password_manager_enabled": False,
                "profile.default_content_setting_values.notifications": 2,
            },
        )

        return options

    def _apply_stealth_patches(self, light: bool = False) -> None:
        """Hide common automation signals that trigger bot verification."""
        if not self.driver:
            return
        try:
            stealth_js = """
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                window.chrome = window.chrome || { runtime: {} };
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['en-US', 'en']
                });
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5]
                });
                const originalQuery = window.navigator.permissions && window.navigator.permissions.query;
                if (originalQuery) {
                    window.navigator.permissions.query = (parameters) => (
                        parameters && parameters.name === 'notifications'
                            ? Promise.resolve({ state: Notification.permission })
                            : originalQuery(parameters)
                    );
                }
            """
            self.driver.execute_cdp_cmd(
                "Page.addScriptToEvaluateOnNewDocument",
                {"source": stealth_js},
            )
            if not light:
                self.driver.execute_cdp_cmd(
                    "Network.setUserAgentOverride",
                    {
                        "userAgent": self.user_agent,
                        "platform": "Windows",
                        "acceptLanguage": "en-US,en",
                    },
                )
            logger.info("Applied browser stealth patches")
        except Exception as e:
            logger.warning(f"Could not apply full stealth patches: {e}")
            try:
                self.driver.execute_script(
                    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
                )
            except Exception:
                pass

    def is_bot_challenge_present(self) -> bool:
        """
        Return True if the current page looks like a bot / human verification *wall*.

        Intentionally ignores ordinary reCAPTCHA/hCaptcha widgets on login forms so
        recording does not hang for 90s on normal pages.
        """
        if not self.driver:
            return False
        try:
            title = (self.driver.title or "").lower().strip()
            url = (self.driver.current_url or "").lower()

            for t in _BOT_WALL_TITLES:
                if t in title:
                    return True

            # Cloudflare challenge URLs
            if "/cdn-cgi/challenge" in url or "challenges.cloudflare.com" in url:
                return True

            try:
                source = (self.driver.page_source or "")[:80000].lower()
            except Exception:
                source = ""

            haystack = f"{title}\n{url}\n{source}"
            for marker in _BOT_WALL_MARKERS:
                if marker in haystack:
                    return True

            for sel in _BOT_WALL_SELECTORS:
                try:
                    if self.driver.find_elements(By.CSS_SELECTOR, sel):
                        return True
                except Exception:
                    continue

            # Sparse interstitial: almost no interactive content + captcha iframe
            try:
                body_text_len = self.driver.execute_script(
                    "return (document.body && document.body.innerText || '').trim().length"
                ) or 0
                interactive = self.driver.execute_script(
                    "return document.querySelectorAll('input, textarea, button, a[href]').length"
                ) or 0
                captcha_iframe = self.driver.find_elements(
                    By.CSS_SELECTOR,
                    "iframe[src*='recaptcha'], iframe[src*='hcaptcha'], iframe[src*='captcha']",
                )
                if captcha_iframe and body_text_len < 400 and interactive < 4:
                    return True
            except Exception:
                pass
        except Exception as e:
            logger.debug(f"Bot-challenge probe failed: {e}")
        return False

    def wait_for_bot_challenge(
        self,
        timeout: int = 90,
        poll_interval: float = 1.5,
    ) -> Dict:
        """
        If a bot / human verification page is showing, wait for it to clear.

        In headed mode this gives the user time to complete a captcha manually.
        Cloudflare-style challenges often auto-pass once the browser looks real.
        """
        if not self.driver:
            return {"status": "skipped", "reason": "no driver"}

        if not self.is_bot_challenge_present():
            return {"status": "clear", "waited_s": 0}

        mode = "headed" if not self.headless or self._attached_to_debugger else "headless"
        logger.warning(
            "Bot verification challenge detected (%s mode). Waiting up to %ss for it to clear...",
            mode,
            timeout,
        )
        if mode == "headed":
            logger.warning(
                "If a captcha/checkbox is shown, complete it in the browser window."
            )

        start = time.time()
        while time.time() - start < timeout:
            time.sleep(poll_interval)
            try:
                self._wait_for_dom_ready(timeout=5)
            except Exception:
                pass
            if not self.is_bot_challenge_present():
                waited = round(time.time() - start, 1)
                logger.info(f"Bot verification cleared after {waited}s")
                # Brief settle so the real page finishes loading
                time.sleep(1.0)
                self._wait_for_dom_ready(timeout=10)
                return {"status": "cleared", "waited_s": waited}

        waited = round(time.time() - start, 1)
        logger.error(
            "Still on a bot verification page after %ss. "
            "Use headed mode (SELENIUM_HEADLESS=false), a real browser profile "
            "(USE_BRAVE=true), or attach via remote debugging.",
            waited,
        )
        return {
            "status": "blocked",
            "waited_s": waited,
            "error": (
                "Site bot verification did not clear. "
                "Set SELENIUM_HEADLESS=false and/or USE_BRAVE=true with a logged-in profile."
            ),
        }

    def _grab_frame(self):
        """Capture one RGB frame from the browser (or reuse last frame)."""
        try:
            if not self.driver:
                return self._latest_frame
            png_bytes = self.driver.get_screenshot_as_png()
            if not png_bytes:
                return self._latest_frame
            image = Image.open(BytesIO(png_bytes)).convert("RGB")
            if image.size != (1920, 1080):
                image = image.resize((1920, 1080), Image.Resampling.LANCZOS)
            frame = np.array(image)
            self._latest_frame = frame
            return frame
        except Exception as e:
            logger.debug(f"Frame grab failed: {e}")
            return self._latest_frame

    def _append_frame(self, frame) -> None:
        if frame is None or self._video_writer is None:
            return
        with self._frame_lock:
            self._video_writer.append_data(frame)
            self._total_frames += 1

    def record_hold(self, seconds: float) -> int:
        """
        Write approximately `seconds` of video at the recording FPS.

        Captures live screenshots on the main thread so each narration step
        occupies the correct amount of timeline (true A/V pacing).
        """
        try:
            seconds = max(0.05, float(seconds))
        except Exception:
            seconds = 1.0
        fps = max(1, int(self._record_fps or 5))
        n_frames = max(1, int(round(seconds * fps)))
        frame_dt = 1.0 / fps
        written = 0
        for _ in range(n_frames):
            t0 = time.time()
            frame = self._grab_frame()
            if frame is not None:
                self._append_frame(frame)
                written += 1
            elapsed = time.time() - t0
            time.sleep(max(0.0, frame_dt - elapsed))
        return written

    def snapshot_frame(self) -> bool:
        """Capture and append a single frame (e.g. right after an action)."""
        frame = self._grab_frame()
        if frame is None:
            return False
        self._append_frame(frame)
        return True

    def create_context(self, video_dir: str = "outputs/videos") -> bool:
        """Set up video recording (main-thread frame capture for A/V sync)."""
        if not self.driver:
            return False

        try:
            Path(video_dir).mkdir(parents=True, exist_ok=True)
            self._recorded_video_path = str(Path(video_dir) / f"selenium_{int(time.time())}.mp4")
            self._total_frames = 0
            self._record_fps = 5

            logger.info(
                "Setting up Selenium recording at %s FPS to %s "
                "(main-thread paced frames for A/V sync)",
                self._record_fps,
                self._recorded_video_path,
            )
            # macro_block_size=1 avoids forced resize from 1080 -> 1088
            self._video_writer = imageio.get_writer(
                self._recorded_video_path,
                fps=self._record_fps,
                codec="libx264",
                macro_block_size=1,
                quality=7,
            )

            # No background capture thread: concurrent Selenium access drops
            # frames and desyncs wall-clock holds from encoded duration.
            self._recording = True
            self._record_thread = None
            # Seed one frame so the file is never empty
            self.snapshot_frame()

            return True
        except Exception as e:
            logger.error(f"Failed to setup Selenium recording: {e}")
            return False

    def _build_selector(self, selector: str):
        """Build a Selenium selector tuple (By, value) from a CSS-like selector."""
        if ':has-text(' in selector:
            text = selector.split(':has-text("')[1].split('")')[0]
            tag = selector.split(':')[0]
            if not tag:
                tag = "*"
            return (By.XPATH, f"//{tag}[contains(text(), '{text}')]")
        return (By.CSS_SELECTOR, selector)

    def _find_element(self, selector: str, timeout: int = 10, clickable: bool = False, visible: bool = False):
        """Wait for an element to be present/visible/clickable and return it."""
        by, value = self._build_selector(selector)
        wait = WebDriverWait(self.driver, timeout)
        if clickable:
            return wait.until(EC.element_to_be_clickable((by, value)))
        if visible:
            return wait.until(EC.visibility_of_element_located((by, value)))
        return wait.until(EC.presence_of_element_located((by, value)))

    def login(self, url: str, email: str, password: str, wait_time: int = 5000) -> Dict:
        """Log into portal"""
        try:
            logger.info(f"Logging into {url}...")
            nav = self.navigate(url, wait_time=3000)
            if nav.get("status") == "failed":
                return {"status": "failed", "error": nav.get("error", "Navigation failed")}

            email_selectors = [
                'input[type="email"]', 'input[name="email"]', '#email'
            ]
            password_selectors = [
                'input[type="password"]', 'input[name="password"]', '#password'
            ]

            email_filled = False
            for sel in email_selectors:
                try:
                    el = self._find_element(sel, timeout=6, visible=True)
                    el.clear()
                    el.send_keys(email)
                    email_filled = True
                    break
                except Exception:
                    pass

            pass_filled = False
            if email_filled:
                time.sleep(1)
                for sel in password_selectors:
                    try:
                        el = self._find_element(sel, timeout=6, visible=True)
                        el.clear()
                        el.send_keys(password)
                        pass_filled = True
                        break
                    except Exception:
                        pass

            if email_filled and pass_filled:
                time.sleep(1)
                submit_selectors = [
                    'button[type="submit"]', 'input[type="submit"]',
                    'button:has-text("Sign in")', 'button:has-text("Login")'
                ]
                for sel in submit_selectors:
                    try:
                        el = self._find_element(sel, timeout=6, clickable=True)
                        self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
                        try:
                            el.click()
                        except Exception:
                            self.driver.execute_script("arguments[0].click();", el)
                        break
                    except Exception:
                        pass

            time.sleep(wait_time / 1000.0)
            # Login can trigger a second challenge
            challenge = self.wait_for_bot_challenge(timeout=90)
            if challenge.get("status") == "blocked":
                return {"status": "failed", "error": challenge.get("error")}
            return {"status": "completed"}
        except Exception as e:
            logger.error(f"Login failed: {e}")
            return {"status": "failed", "error": str(e)}

    def navigate(self, url: str, wait_time: int = 2000) -> Dict:
        try:
            self.driver.get(url)
            self._wait_for_dom_ready(timeout=15)
            # Wait out Cloudflare / captcha walls before recording continues
            challenge = self.wait_for_bot_challenge(timeout=90)
            if challenge.get("status") == "blocked":
                log_entry = {
                    "action": "navigate",
                    "url": url,
                    "status": "failed",
                    "error": challenge.get("error"),
                }
                self.logs.append(log_entry)
                return log_entry
            time.sleep(wait_time / 1000.0)
            log_entry = {"action": "navigate", "url": url, "status": "completed"}
            self.logs.append(log_entry)
            return log_entry
        except Exception as e:
            logger.error(f"Navigation failed: {e}")
            return {"action": "navigate", "status": "failed", "error": str(e)}

    def _wait_for_dom_ready(self, timeout: int = 10):
        """Wait for the document readyState to be complete."""
        try:
            WebDriverWait(self.driver, timeout).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
        except Exception:
            pass

    def click(self, selector: str) -> Dict:
        try:
            # Re-check after SPA navigations that may hit a wall mid-flow
            if self.is_bot_challenge_present():
                challenge = self.wait_for_bot_challenge(timeout=60)
                if challenge.get("status") == "blocked":
                    return {
                        "action": "click",
                        "status": "failed",
                        "error": challenge.get("error"),
                    }

            el = self._find_element(selector, timeout=10, clickable=True)
            self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
            try:
                el.click()
            except Exception:
                self.driver.execute_script("arguments[0].click();", el)
            time.sleep(0.5)
            log_entry = {"action": "click", "selector": selector, "status": "completed"}
            self.logs.append(log_entry)
            return log_entry
        except Exception as e:
            logger.error(f"Click failed for {selector}: {e}")
            return {"action": "click", "status": "failed", "error": str(e)}

    def fill(self, selector: str, text: str) -> Dict:
        try:
            if self.is_bot_challenge_present():
                challenge = self.wait_for_bot_challenge(timeout=60)
                if challenge.get("status") == "blocked":
                    return {
                        "action": "fill",
                        "status": "failed",
                        "error": challenge.get("error"),
                    }

            el = self._find_element(selector, timeout=10, visible=True)
            self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
            el.clear()
            el.send_keys(text)
            time.sleep(0.5)
            log_entry = {"action": "fill", "selector": selector, "status": "completed"}
            self.logs.append(log_entry)
            return log_entry
        except Exception as e:
            return {"action": "fill", "status": "failed", "error": str(e)}

    def press(self, selector: Optional[str], key: str = "ENTER") -> Dict:
        """Press a key on a selector, with fallbacks to active/search inputs."""
        key_upper = (key or "ENTER").upper()
        key_map = {
            "ENTER": Keys.ENTER,
            "RETURN": Keys.RETURN,
            "TAB": Keys.TAB,
            "ESC": Keys.ESCAPE,
            "ESCAPE": Keys.ESCAPE,
        }
        send_key = key_map.get(key_upper, key)

        # Try explicit selector first, then common search fields, then active element.
        candidates = []
        if selector and str(selector).strip():
            candidates.append(str(selector).strip())
        candidates.extend(
            [
                "#searchInput",
                "input[name='search']",
                "input[type='search']",
                "input[name='q']",
                "textarea[name='search']",
            ]
        )

        last_error = None
        try:
            for sel in candidates:
                try:
                    target = self._find_element(sel, timeout=3, visible=True)
                    self.driver.execute_script(
                        "arguments[0].scrollIntoView({block:'center'});", target
                    )
                    target.click()
                    target.send_keys(send_key)
                    time.sleep(0.8)
                    log_entry = {
                        "action": "press",
                        "key": key_upper,
                        "selector": sel,
                        "status": "completed",
                    }
                    self.logs.append(log_entry)
                    return log_entry
                except Exception as e:
                    last_error = e
                    continue

            # Final fallback: whatever currently has focus
            try:
                self.driver.switch_to.active_element.send_keys(send_key)
                time.sleep(0.8)
                log_entry = {
                    "action": "press",
                    "key": key_upper,
                    "selector": "active_element",
                    "status": "completed",
                }
                self.logs.append(log_entry)
                return log_entry
            except Exception as e:
                last_error = e

            return {
                "action": "press",
                "key": key_upper,
                "status": "failed",
                "error": str(last_error) if last_error else "Press failed",
            }
        except Exception as e:
            return {"action": "press", "status": "failed", "error": str(e)}

    def execute_script(self, script: str):
        try:
            return self.driver.execute_script(script)
        except Exception:
            return None

    def get_dom_summary(self, max_elements: int = 60) -> str:
        """Return a compact, token-efficient summary of the *visible*
        interactable elements on the current page.

        Produces the same "text -> selector" format used for the initial plan,
        so the LLM sees consistent input whether planning up front or re-planning
        mid-demo against the live DOM.
        """
        script = r"""
        const out = [];
        const cssEscape = (s) => (window.CSS && CSS.escape) ? CSS.escape(s) : s;
        const selectorFor = (el) => {
            if (el.id) return '#' + cssEscape(el.id);
            if (el.getAttribute('data-testid'))
                return '[data-testid="' + el.getAttribute('data-testid') + '"]';
            if (el.getAttribute('name'))
                return el.tagName.toLowerCase() + '[name="' + el.getAttribute('name') + '"]';
            if (el.tagName === 'A' && el.getAttribute('href'))
                return 'a[href="' + el.getAttribute('href') + '"]';
            if (el.getAttribute('aria-label'))
                return el.tagName.toLowerCase() + '[aria-label="' + el.getAttribute('aria-label') + '"]';
            return el.tagName.toLowerCase();
        };
        const isVisible = (el) => {
            const r = el.getBoundingClientRect();
            return r.width > 0 && r.height > 0;
        };
        const nodes = document.querySelectorAll('a, button, input, textarea, select, h1, h2, h3');
        for (const el of nodes) {
            if (out.length >= arguments[0]) break;
            if (!isVisible(el)) continue;
            const tag = el.tagName.toLowerCase();
            let label = '';
            if (['input','textarea','select'].includes(tag)) {
                label = el.getAttribute('name') || el.getAttribute('placeholder')
                        || el.getAttribute('aria-label') || el.getAttribute('type') || tag;
            } else {
                label = (el.innerText || el.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 80);
                if (!label) continue;
            }
            out.push(tag + ' "' + label + '" -> ' + selectorFor(el));
        }
        return out.join('\n');
        """
        try:
            result = self.driver.execute_script(script, max_elements)
            return result or ""
        except Exception as e:
            logger.warning(f"get_dom_summary failed: {e}")
            return ""

    def capture_screenshot(self, path: str) -> bool:
        try:
            png_bytes = self.driver.get_screenshot_as_png()
            if not png_bytes:
                return False
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            with open(path, "wb") as f:
                f.write(png_bytes)
            return True
        except Exception:
            return False

    def get_video_path(self) -> Optional[str]:
        return self._recorded_video_path

    @property
    def recorded_video_path(self) -> Optional[str]:
        return self._recorded_video_path

    @property
    def page(self):
        """Mock page object to support page.content() and page.evaluate() calls in pipeline.py"""
        class MockPage:
            def content(inner_self):
                return self.driver.page_source

            def evaluate(inner_self, script):
                return self.driver.execute_script(script)

        return MockPage()

    def close(self):
        """Stop video recording and close browser (safe to call more than once)."""
        try:
            if self._recording or self._video_writer or self._record_thread:
                logger.info(
                    "Stopping video recording (%s frames)...",
                    self._total_frames,
                )
            self._recording = False
            if self._record_thread:
                self._record_thread.join(timeout=3.0)
                logger.info("Recording thread joined")
                self._record_thread = None

            if self._video_writer:
                logger.info(f"Closing video writer for {self._recorded_video_path}")
                try:
                    self._video_writer.close()
                except Exception as writer_err:
                    logger.warning(f"Video writer close: {writer_err}")
                self._video_writer = None
                logger.info(
                    "Video saved to %s (%s frames @ %sfps ≈ %.2fs)",
                    self._recorded_video_path,
                    self._total_frames,
                    self._record_fps,
                    (self._total_frames / self._record_fps) if self._record_fps else 0,
                )

                if self._recorded_video_path and os.path.exists(self._recorded_video_path):
                    file_size = os.path.getsize(self._recorded_video_path)
                    logger.info(f"Video file size: {file_size} bytes")

            if self.driver:
                # Don't quit an attached browser the user may still be using
                if self._attached_to_debugger:
                    logger.info("Detaching from debugger session (leaving browser open)")
                else:
                    try:
                        self.driver.quit()
                    except Exception as quit_err:
                        logger.warning(f"Driver quit: {quit_err}")
                self.driver = None
                logger.info("Selenium browser closed")
        except Exception as e:
            logger.error(f"Error closing Selenium: {e}")
