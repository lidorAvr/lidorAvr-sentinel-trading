"""
tests/test_healthcheck.py — tests for the real _touch_heartbeat() in risk_monitor.py.

Imports the actual production implementation (not a re-defined helper) so any
regression in the real code will be caught here.

Uses the same stub pattern as test_phase5_anti_spam.py to silence heavy
module-level imports (telebot, supabase, dotenv) that aren't relevant to
the heartbeat logic.
"""
import os
import sys
import time
import types
import tempfile
import pytest

# ── Stub heavy dependencies so risk_monitor can be imported in tests ─────────
for _mod in ["telebot", "supabase", "dotenv"]:
    if _mod not in sys.modules:
        sys.modules[_mod] = types.ModuleType(_mod)

sys.modules["supabase"].create_client = lambda *a, **k: None   # type: ignore
sys.modules["dotenv"].load_dotenv     = lambda *a, **k: None   # type: ignore

class _FakeBot:
    def __init__(self, *a, **k): pass

sys.modules["telebot"].TeleBot = _FakeBot  # type: ignore

import risk_monitor as rm   # ← real production module


# ── Helpers ───────────────────────────────────────────────────────────────────

def _heartbeat_path(tmp_dir: str, name: str) -> str:
    return os.path.join(tmp_dir, f"{name}_last_cycle")


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestRealTouchHeartbeat:
    """Tests call the actual rm._touch_heartbeat() implementation."""

    def test_creates_file_on_first_call(self, monkeypatch, tmp_path):
        monkeypatch.setattr(rm, "_HEARTBEAT_DIR", str(tmp_path))
        rm._touch_heartbeat("risk_monitor")
        assert os.path.exists(_heartbeat_path(str(tmp_path), "risk_monitor"))

    def test_file_content_is_recent_timestamp(self, monkeypatch, tmp_path):
        monkeypatch.setattr(rm, "_HEARTBEAT_DIR", str(tmp_path))
        before = time.time()
        rm._touch_heartbeat("report_scheduler")
        after = time.time()
        content = open(_heartbeat_path(str(tmp_path), "report_scheduler")).read()
        written = float(content)
        assert before <= written <= after

    def test_mtime_is_fresh_after_touch(self, monkeypatch, tmp_path):
        monkeypatch.setattr(rm, "_HEARTBEAT_DIR", str(tmp_path))
        rm._touch_heartbeat("sentinel_bot")
        age = time.time() - os.path.getmtime(_heartbeat_path(str(tmp_path), "sentinel_bot"))
        assert age < 2.0, f"heartbeat file is {age:.2f}s old — expected < 2s"

    def test_second_touch_updates_mtime(self, monkeypatch, tmp_path):
        monkeypatch.setattr(rm, "_HEARTBEAT_DIR", str(tmp_path))
        rm._touch_heartbeat("telegram_bot")
        mtime1 = os.path.getmtime(_heartbeat_path(str(tmp_path), "telegram_bot"))
        time.sleep(0.05)
        rm._touch_heartbeat("telegram_bot")
        mtime2 = os.path.getmtime(_heartbeat_path(str(tmp_path), "telegram_bot"))
        assert mtime2 > mtime1, "second touch must update mtime"

    def test_creates_dir_if_missing(self, monkeypatch, tmp_path):
        nested = str(tmp_path / "deep" / "nested")
        monkeypatch.setattr(rm, "_HEARTBEAT_DIR", nested)
        rm._touch_heartbeat("risk_monitor")
        assert os.path.exists(os.path.join(nested, "risk_monitor_last_cycle"))

    def test_silent_on_permission_error(self, monkeypatch):
        """_touch_heartbeat must never raise — it silently swallows errors."""
        monkeypatch.setattr(rm, "_HEARTBEAT_DIR", "/proc/nonexistent_sentinel_test")
        rm._touch_heartbeat("risk_monitor")   # must not raise
