"""
DOM Sentinel
Monitors DOM changes to detect UI drift
"""

import sys
from pathlib import Path
from typing import Dict, List, Optional
import hashlib
import json
import logging
import time

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

from backend.app.modules.automation.selenium_engine import SeleniumEngine

logger = logging.getLogger(__name__)


class DOMSentinel:
    """Monitors and detects DOM changes"""
    
    def __init__(self):
        """Initialize DOM sentinel"""
        self.snapshots = {}
        self.storage_dir = Path("outputs/dom_snapshots")
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def _latest_snapshot_file(self, feature_name: str) -> Path:
        safe_name = feature_name.replace("/", "_").replace(" ", "_")
        return self.storage_dir / f"{safe_name}_latest.json"

    def load_latest_snapshot(self, feature_name: str) -> Optional[dict]:
        """Load the latest snapshot for a feature if it exists."""
        latest_file = self._latest_snapshot_file(feature_name)
        if not latest_file.exists():
            return None
        try:
            with open(latest_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Could not load latest snapshot for {feature_name}: {e}")
            return None

    def save_latest_snapshot(self, feature_name: str, snapshot: dict) -> None:
        """Persist the latest snapshot pointer for a feature."""
        latest_file = self._latest_snapshot_file(feature_name)
        with open(latest_file, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, indent=2)

    def capture_snapshot_from_url(self, portal_url: str, feature_name: str = "mock_site") -> dict:
        """Open a page with Selenium and capture a DOM snapshot."""
        engine = SeleniumEngine(headless=True)
        try:
            if not engine.launch_browser():
                return {"success": False, "error": "Failed to launch browser for DOM capture"}
            if not engine.create_context():
                engine.close()
                return {"success": False, "error": "Failed to create browser context for DOM capture"}

            nav = engine.navigate(portal_url, wait_time=1500)
            if nav.get("status") != "completed":
                return {"success": False, "error": nav.get("error", "Navigation failed")}

            snapshot = self.capture_dom_snapshot(engine.page, feature_name, portal_url)
            snapshot["success"] = "dom_hash" in snapshot
            return snapshot
        except Exception as e:
            logger.error(f"Failed to capture snapshot from URL: {e}")
            return {"success": False, "error": str(e)}
        finally:
            engine.close()
    
    def capture_dom_snapshot(self, page, feature_name: str, portal_url: str) -> dict:
        """
        Capture current DOM state
        
        Args:
            page: Playwright page object
            feature_name: Feature being monitored
            portal_url: Portal URL
            
        Returns:
            Snapshot dictionary
        """
        try:
            # Get DOM structure
            dom_html = page.content()
            dom_hash = hashlib.sha256(dom_html.encode()).hexdigest()
            
            # Count elements
            element_count = page.evaluate("document.querySelectorAll('*').length")
            
            # Extract key elements
            key_elements = page.evaluate("""
            () => {
                const elements = [];
                                document.querySelectorAll('button, input, select, a[href], [role="button"]').forEach(el => {
                    elements.push({
                        tag: el.tagName.toLowerCase(),
                        text: el.textContent?.substring(0, 50) || '',
                                                selector: el.getAttribute('id')
                                                    ? `#${el.getAttribute('id')}`
                                                    : (el.getAttribute('class')
                                                        ? `.${el.getAttribute('class').split(' ').filter(Boolean).slice(0, 2).join('.')}`
                                                        : el.tagName.toLowerCase()),
                        position: {
                            x: el.getBoundingClientRect().x,
                            y: el.getBoundingClientRect().y,
                            width: el.getBoundingClientRect().width,
                            height: el.getBoundingClientRect().height
                        }
                    });
                });
                return elements;
            }
            """)
            
            snapshot = {
                "feature_name": feature_name,
                "portal_url": portal_url,
                "dom_hash": dom_hash,
                "element_count": element_count,
                "key_elements": key_elements,
                "timestamp": int(time.time()),
                "saved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            }
            
            # Save snapshot
            snapshot_file = self.storage_dir / f"{feature_name}_{dom_hash[:8]}.json"
            with open(snapshot_file, "w") as f:
                json.dump(snapshot, f, indent=2)
            
            logger.info(f"DOM snapshot captured: {snapshot_file}")
            
            return snapshot
        except Exception as e:
            logger.error(f"Failed to capture DOM snapshot: {e}")
            return {"success": False, "error": str(e)}

    def detect_new_features(self, old_snapshot: dict, new_snapshot: dict) -> List[Dict]:
        """Detect newly introduced interactive elements as potential new features."""
        old_items = {
            (e.get("tag", ""), (e.get("text", "") or "").strip().lower(), e.get("selector", ""))
            for e in old_snapshot.get("key_elements", [])
        }

        discovered = []
        seen = set()
        for elem in new_snapshot.get("key_elements", []):
            item_key = (elem.get("tag", ""), (elem.get("text", "") or "").strip().lower(), elem.get("selector", ""))
            label = (elem.get("text", "") or "").strip()
            if item_key in old_items:
                continue
            if not label or len(label) < 3:
                continue
            if label.lower() in seen:
                continue

            seen.add(label.lower())
            discovered.append(
                {
                    "name": label,
                    "selector": elem.get("selector", ""),
                    "tag": elem.get("tag", ""),
                }
            )

        return discovered
    
    def compare_snapshots(self, old_snapshot: dict, new_snapshot: dict) -> dict:
        """
        Compare two DOM snapshots for drift
        
        Args:
            old_snapshot: Previous snapshot
            new_snapshot: Current snapshot
            
        Returns:
            Drift analysis dictionary
        """
        drift_detected = []
        
        # Check if DOM structure changed
        if old_snapshot["dom_hash"] != new_snapshot["dom_hash"]:
            drift_detected.append({
                "type": "structure_changed",
                "severity": "high",
                "description": "DOM structure has changed"
            })
        
        # Check element count
        old_count = old_snapshot.get("element_count", 0)
        new_count = new_snapshot.get("element_count", 0)
        if abs(old_count - new_count) > 5:  # Threshold
            drift_detected.append({
                "type": "element_count_changed",
                "severity": "medium",
                "old_count": old_count,
                "new_count": new_count,
                "description": f"Element count changed from {old_count} to {new_count}"
            })
        
        # Check for moved elements
        old_elements = {f"{e['selector']}_{e['text'][:10]}": e for e in old_snapshot.get("key_elements", [])}
        new_elements = {f"{e['selector']}_{e['text'][:10]}": e for e in new_snapshot.get("key_elements", [])}
        
        for key, new_elem in new_elements.items():
            if key in old_elements:
                old_elem = old_elements[key]
                pos_diff_x = abs(new_elem["position"]["x"] - old_elem["position"]["x"])
                pos_diff_y = abs(new_elem["position"]["y"] - old_elem["position"]["y"])
                
                if pos_diff_x > 20 or pos_diff_y > 20:  # Pixel threshold
                    drift_detected.append({
                        "type": "element_moved",
                        "severity": "medium",
                        "element": key,
                        "old_position": old_elem["position"],
                        "new_position": new_elem["position"]
                    })
        
        return {
            "feature_name": new_snapshot.get("feature_name"),
            "drift_detected": len(drift_detected) > 0,
            "drift_count": len(drift_detected),
            "drift_items": drift_detected,
            "similarity_score": 1.0 - (len(drift_detected) * 0.1)  # Simple scoring
        }
