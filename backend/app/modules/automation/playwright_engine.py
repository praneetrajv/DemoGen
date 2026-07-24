"""
Playwright Automation Engine
Handles browser automation with Playwright sync API
"""

import sys
from pathlib import Path
from typing import List, Dict, Optional
from playwright.sync_api import sync_playwright, Page
import time
import logging

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

logger = logging.getLogger(__name__)


class PlaywrightEngine:
    """Browser automation using Playwright sync API"""
    
    def __init__(self, headless: bool = False):
        """Initialize Playwright engine"""
        self.headless = headless
        self.browser = None
        self.context = None
        self.page = None
        self.logs = []
    
    def launch_browser(self):
        """Launch Chromium browser with reduced automation fingerprints"""
        try:
            self.playwright = sync_playwright().start()
            self.browser = self.playwright.chromium.launch(
                headless=self.headless,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-infobars",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                ],
            )
            logger.info("Chromium browser launched successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to launch browser: {e}")
            return False
    
    def create_context(self, video_dir: str = "outputs/videos"):
        """Create browser context with video recording and stealth init scripts"""
        if not self.browser:
            return False
        
        try:
            from pathlib import Path
            Path(video_dir).mkdir(parents=True, exist_ok=True)
            
            self.context = self.browser.new_context(
                record_video_dir=video_dir,
                record_video_size={"width": 1920, "height": 1080},
                viewport={"width": 1920, "height": 1080},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                ),
                locale="en-US",
                timezone_id="America/New_York",
            )
            # Hide navigator.webdriver and related automation signals
            self.context.add_init_script(
                """
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                window.chrome = window.chrome || { runtime: {} };
                Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                """
            )
            self.page = self.context.new_page()
            logger.info(f"Browser context created with video recording to {video_dir}")
            return True
        except Exception as e:
            logger.error(f"Failed to create context: {e}")
            return False
    
    def login(self, url: str, email: str, password: str, wait_time: int = 5000) -> Dict:
        """
        Log into NeevCloud portal
        
        Args:
            url: Login page URL
            email: Login email
            password: Login password
            wait_time: Wait time after login in ms
        """
        try:
            logger.info(f"Logging into {url}...")
            self.navigate(url, wait_time=3000)
            
            # Try common login form selectors
            email_selectors = [
                'input[type="email"]', 'input[name="email"]',
                '#email', 'input[placeholder*="email" i]',
                'input[type="text"]', 'input[name="username"]'
            ]
            password_selectors = [
                'input[type="password"]', 'input[name="password"]',
                '#password', 'input[placeholder*="password" i]'
            ]
            submit_selectors = [
                'button[type="submit"]', 'input[type="submit"]',
                'button:has-text("Sign in")', 'button:has-text("Log in")',
                'button:has-text("Login")', 'button:has-text("Submit")',
                'button:has-text("sign in")', 'button:has-text("log in")',
            ]
            
            # Fill email
            email_filled = False
            for sel in email_selectors:
                try:
                    if self.page.locator(sel).count() > 0:
                        self.page.fill(sel, email)
                        email_filled = True
                        logger.info(f"Filled email using: {sel}")
                        break
                except:
                    continue
            
            if not email_filled:
                logger.warning("Could not find email field")
                return {"action": "login", "status": "failed", "error": "Email field not found"}
            
            time.sleep(0.5)
            
            # Fill password
            password_filled = False
            for sel in password_selectors:
                try:
                    if self.page.locator(sel).count() > 0:
                        self.page.fill(sel, password)
                        password_filled = True
                        logger.info(f"Filled password using: {sel}")
                        break
                except:
                    continue
            
            if not password_filled:
                logger.warning("Could not find password field")
                return {"action": "login", "status": "failed", "error": "Password field not found"}
            
            time.sleep(0.5)
            
            # Click submit
            submitted = False
            for sel in submit_selectors:
                try:
                    if self.page.locator(sel).count() > 0:
                        self.page.click(sel)
                        submitted = True
                        logger.info(f"Clicked submit using: {sel}")
                        break
                except:
                    continue
            
            if not submitted:
                # Try pressing Enter as fallback
                self.page.press('input[type="password"]', 'Enter')
                logger.info("Pressed Enter to submit")
            
            # Wait for navigation after login
            try:
                self.page.wait_for_load_state("networkidle", timeout=15000)
            except:
                pass
            time.sleep(wait_time / 1000)
            
            logger.info("✓ Login completed")
            log_entry = {
                "action": "login",
                "status": "completed",
                "timestamp": time.time()
            }
            self.logs.append(log_entry)
            return log_entry
            
        except Exception as e:
            logger.error(f"Login failed: {e}")
            log_entry = {
                "action": "login",
                "status": "failed",
                "error": str(e),
                "timestamp": time.time()
            }
            self.logs.append(log_entry)
            return log_entry
    
    def get_video_path(self) -> Optional[str]:
        """
        Get the path to Playwright's recorded video.
        Must be called AFTER closing the context.
        """
        try:
            if self.page:
                video = self.page.video
                if video:
                    path = video.path()
                    logger.info(f"Playwright video recorded at: {path}")
                    return str(path)
        except Exception as e:
            logger.warning(f"Could not get video path: {e}")
        return None
    
    def navigate(self, url: str, wait_time: int = 5000) -> Dict:
        """Navigate to URL"""
        try:
            self.page.goto(url, wait_until="networkidle", timeout=30000)
            self.page.wait_for_load_state("networkidle")
            time.sleep(wait_time / 1000)
            
            log_entry = {
                "action": "navigate",
                "url": url,
                "status": "completed",
                "timestamp": time.time()
            }
            self.logs.append(log_entry)
            logger.info(f"Navigated to {url}")
            return log_entry
        except Exception as e:
            log_entry = {
                "action": "navigate",
                "url": url,
                "status": "failed",
                "error": str(e),
                "timestamp": time.time()
            }
            self.logs.append(log_entry)
            logger.error(f"Navigation failed: {e}")
            return log_entry
    
    def click(self, selector: str, alt_selectors: Optional[List[str]] = None) -> Dict:
        """Click element with fallback selectors"""
        selectors_to_try = [selector] + (alt_selectors or [])
        
        for sel in selectors_to_try:
            try:
                self.page.click(sel)
                time.sleep(500 / 1000)
                
                log_entry = {
                    "action": "click",
                    "selector": sel,
                    "status": "completed",
                    "timestamp": time.time()
                }
                self.logs.append(log_entry)
                logger.info(f"Clicked: {sel}")
                return log_entry
            except:
                continue
        
        log_entry = {
            "action": "click",
            "selector": selector,
            "status": "failed",
            "error": f"Element not found with selectors: {selectors_to_try}",
            "timestamp": time.time()
        }
        self.logs.append(log_entry)
        logger.error(f"Click failed: {selector}")
        return log_entry
    
    def fill(self, selector: str, text: str) -> Dict:
        """Fill input field"""
        try:
            self.page.fill(selector, text)
            time.sleep(300 / 1000)
            
            log_entry = {
                "action": "fill",
                "selector": selector,
                "status": "completed",
                "timestamp": time.time()
            }
            self.logs.append(log_entry)
            logger.info(f"Filled: {selector} with text")
            return log_entry
        except Exception as e:
            log_entry = {
                "action": "fill",
                "selector": selector,
                "status": "failed",
                "error": str(e),
                "timestamp": time.time()
            }
            self.logs.append(log_entry)
            logger.error(f"Fill failed: {e}")
            return log_entry
    
    def press(self, key: str) -> Dict:
        """Press keyboard key"""
        try:
            self.page.press("body", key)
            time.sleep(1000 / 1000)
            
            log_entry = {
                "action": "press",
                "key": key,
                "status": "completed",
                "timestamp": time.time()
            }
            self.logs.append(log_entry)
            logger.info(f"Pressed: {key}")
            return log_entry
        except Exception as e:
            log_entry = {
                "action": "press",
                "key": key,
                "status": "failed",
                "error": str(e),
                "timestamp": time.time()
            }
            self.logs.append(log_entry)
            logger.error(f"Press failed: {e}")
            return log_entry
    
    def scroll(self, direction: str = "down", amount: int = 3) -> Dict:
        """Scroll page"""
        try:
            if direction == "down":
                self.page.evaluate(f"window.scrollBy(0, {amount * 100})")
            else:
                self.page.evaluate(f"window.scrollBy(0, {-amount * 100})")
            
            time.sleep(1000 / 1000)
            
            log_entry = {
                "action": "scroll",
                "direction": direction,
                "amount": amount,
                "status": "completed",
                "timestamp": time.time()
            }
            self.logs.append(log_entry)
            return log_entry
        except Exception as e:
            log_entry = {
                "action": "scroll",
                "status": "failed",
                "error": str(e),
                "timestamp": time.time()
            }
            self.logs.append(log_entry)
            return log_entry
    
    def wait(self, milliseconds: int) -> Dict:
        """Wait for specified time"""
        time.sleep(milliseconds / 1000)
        log_entry = {
            "action": "wait",
            "duration_ms": milliseconds,
            "status": "completed",
            "timestamp": time.time()
        }
        self.logs.append(log_entry)
        return log_entry
    
    def screenshot(self, filename: str) -> Dict:
        """Take screenshot"""
        try:
            output_path = Path("outputs") / filename
            output_path.parent.mkdir(parents=True, exist_ok=True)
            self.page.screenshot(path=str(output_path))
            
            log_entry = {
                "action": "screenshot",
                "filename": filename,
                "status": "completed",
                "path": str(output_path),
                "timestamp": time.time()
            }
            self.logs.append(log_entry)
            return log_entry
        except Exception as e:
            log_entry = {
                "action": "screenshot",
                "status": "failed",
                "error": str(e),
                "timestamp": time.time()
            }
            self.logs.append(log_entry)
            return log_entry
    
    def execute_script(self, script: str):
        """Execute JavaScript"""
        try:
            return self.page.evaluate(script)
        except Exception as e:
            logger.error(f"Script execution failed: {e}")
            return None
    
    def get_video_path(self) -> Optional[str]:
        """Get the path to the recorded video for the current page"""
        if self.page:
            try:
                if self.page.video:
                    return self.page.video.path()
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"Failed to get video path: {e}")
        return None
        
    def close(self):
        """Close browser and finalize video recording"""
        try:
            # Brief wait to ensure the final frame is recorded
            import time
            time.sleep(1.0)
            
            video = self.page.video if hasattr(self, 'page') and self.page else None
            
            if hasattr(self, 'context') and self.context:
                self.context.close()
            if hasattr(self, 'browser') and self.browser:
                self.browser.close()
            if hasattr(self, 'playwright') and self.playwright:
                self.playwright.stop()
                
            if video:
                try:
                    self._recorded_video_path = video.path()
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).warning(f"Failed to get video path after close: {e}")
                    
            import logging
            logging.getLogger(__name__).info("Browser closed")
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Error closing browser: {e}")
    @property
    def recorded_video_path(self) -> Optional[str]:
        """Get the recorded video path (available after close)"""
        return getattr(self, '_recorded_video_path', None)
    
    def get_logs(self) -> List[Dict]:
        """Get all execution logs"""
        return self.logs
    
    def __enter__(self):
        """Context manager entry"""
        self.launch_browser()
        self.create_context()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()
