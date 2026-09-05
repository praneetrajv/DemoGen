"""Unit tests for PlaywrightEngine's launch preconditions.

These are pure-logic tests: no browser, no server, no network. They exist
because of a real failure -- with uvicorn's auto-reload enabled on Windows,
every demo generation died with "Browser launch failed" and the log line
"Could not start Playwright: " with nothing after the colon.

Root cause: uvicorn installs WindowsSelectorEventLoopPolicy process-wide when
it needs a subprocess (reload, or workers > 1). Playwright's sync API builds
its own loop with asyncio.new_event_loop(), inherits that policy, and a
Windows SelectorEventLoop cannot spawn subprocesses -- it raises a bare
NotImplementedError, whose message is the empty string.
"""

import asyncio
import sys

import pytest

from backend.app.modules.automation.playwright_engine import (
    _describe_exc,
    _ensure_subprocess_capable_loop_policy,
)


class _FakePolicy:
    """Stands in for WindowsProactorEventLoopPolicy on non-Windows CI."""


class _OtherPolicy:
    """Stands in for WindowsSelectorEventLoopPolicy."""


# ----------------------------------------------------------------------
# _describe_exc
# ----------------------------------------------------------------------
def test_describe_exc_names_the_type_when_the_message_is_empty():
    """The bug that made this hard to diagnose: an unnamed, messageless error."""
    assert str(NotImplementedError()) == ""
    assert _describe_exc(NotImplementedError()) == "NotImplementedError"


def test_describe_exc_keeps_a_real_message():
    assert _describe_exc(ValueError("no such file")) == "ValueError: no such file"


def test_describe_exc_strips_whitespace_only_messages():
    assert _describe_exc(RuntimeError("   \n ")) == "RuntimeError"


# ----------------------------------------------------------------------
# _ensure_subprocess_capable_loop_policy
# ----------------------------------------------------------------------
def test_policy_is_repaired_when_it_cannot_spawn_subprocesses(monkeypatch):
    monkeypatch.setattr(
        "backend.app.modules.automation.playwright_engine.sys.platform", "win32"
    )
    monkeypatch.setattr(asyncio, "WindowsProactorEventLoopPolicy", _FakePolicy, raising=False)
    monkeypatch.setattr(asyncio, "get_event_loop_policy", lambda: _OtherPolicy())

    installed = []
    monkeypatch.setattr(asyncio, "set_event_loop_policy", installed.append)

    _ensure_subprocess_capable_loop_policy()

    assert len(installed) == 1, "the unusable policy should have been replaced"
    assert isinstance(installed[0], _FakePolicy)


def test_policy_is_left_alone_when_already_correct(monkeypatch):
    monkeypatch.setattr(
        "backend.app.modules.automation.playwright_engine.sys.platform", "win32"
    )
    monkeypatch.setattr(asyncio, "WindowsProactorEventLoopPolicy", _FakePolicy, raising=False)
    monkeypatch.setattr(asyncio, "get_event_loop_policy", lambda: _FakePolicy())

    installed = []
    monkeypatch.setattr(asyncio, "set_event_loop_policy", installed.append)

    _ensure_subprocess_capable_loop_policy()

    assert installed == [], "must be idempotent - do not churn a working policy"


def test_policy_untouched_off_windows(monkeypatch):
    """Only Windows has the SelectorEventLoop subprocess gap."""
    monkeypatch.setattr(
        "backend.app.modules.automation.playwright_engine.sys.platform", "linux"
    )
    installed = []
    monkeypatch.setattr(asyncio, "set_event_loop_policy", installed.append)

    _ensure_subprocess_capable_loop_policy()

    assert installed == []


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only invariant")
def test_real_policy_can_spawn_subprocesses_after_repair():
    """End-to-end on Windows: after the repair, a fresh loop supports subprocesses."""
    _ensure_subprocess_capable_loop_policy()
    loop = asyncio.new_event_loop()
    try:
        assert isinstance(loop, asyncio.ProactorEventLoop), (
            f"asyncio.new_event_loop() returned {type(loop).__name__}, which "
            "cannot start the Playwright driver"
        )
    finally:
        loop.close()
