"""Contract test: the built-in mock action plan must match the mock site's DOM.

The pipeline's fallback plan (used whenever no LLM key is configured, i.e. the
default) drives the bundled mock site by hardcoded id. If someone renames an
id in mock_site/dashboard.html, every generated demo silently degrades to
"partial" with no obvious cause. This test fails loudly instead.

No server, browser or network needed -- it reads the plan and the HTML.
"""

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

DASHBOARD = ROOT / "mock_site" / "dashboard.html"


def _mock_actions() -> list:
    """Grab the fallback plan without constructing a full pipeline.

    _build_mock_actions never touches self, so calling it unbound keeps this
    test free of the pipeline's constructor side effects.
    """
    from pipeline import DemoGenerationPipeline

    return DemoGenerationPipeline._build_mock_actions(
        None, "http://127.0.0.1:8001/dashboard.html"
    )


@pytest.fixture(scope="module")
def html() -> str:
    if not DASHBOARD.exists():
        pytest.fail(f"Mock site missing: {DASHBOARD}")
    return DASHBOARD.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def ids(html: str) -> set:
    return set(re.findall(r'\bid=["\']([^"\']+)["\']', html))


def test_no_duplicate_ids(html: str) -> None:
    found = re.findall(r'\bid=["\']([^"\']+)["\']', html)
    dupes = {i for i in found if found.count(i) > 1}
    assert not dupes, f"Duplicate ids would make selectors ambiguous: {sorted(dupes)}"


def test_every_planned_selector_exists(ids: set) -> None:
    missing = []
    for action in _mock_actions():
        selector = action.get("selector")
        if not selector or not selector.startswith("#"):
            continue
        if selector[1:] not in ids:
            missing.append(f"{selector} (step: {action.get('description')})")
    assert not missing, "Action plan targets ids absent from dashboard.html: " + "; ".join(missing)


def test_select_values_exist_as_options(html: str) -> None:
    """A select_option() call fails outright if the value isn't in the list."""
    options = set(re.findall(r'<option[^>]*\bvalue=["\']([^"\']*)["\']', html))
    for action in _mock_actions():
        if action.get("action_type") == "select":
            assert action["value"] in options, (
                f"select action wants value={action['value']!r} on "
                f"{action.get('selector')}, but dashboard.html only offers "
                f"{sorted(options)}"
            )


def test_no_click_on_option_elements() -> None:
    """Regression guard: clicking an <option> cannot work in Chromium.

    The dropdown is rendered by the OS outside the page, so Playwright's click
    times out. Selecting a tier must use the `select` action.
    """
    for action in _mock_actions():
        if action.get("action_type") == "click":
            assert "option" not in (action.get("selector") or "").lower(), (
                f"Step {action.get('description')!r} clicks an option element; "
                f"use action_type='select' instead"
            )


def test_plan_starts_by_navigating() -> None:
    actions = _mock_actions()
    assert actions, "Fallback plan is empty"
    assert actions[0]["action_type"] == "navigate", (
        "The recording's first frame should be a deliberate navigation, "
        f"not {actions[0]['action_type']!r}"
    )
    assert actions[0]["url"].startswith("http")
