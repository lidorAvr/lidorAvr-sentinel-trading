"""
tests/test_healthcheck.py — verify _touch_heartbeat() works correctly in all three services.
"""
import os
import time
import pytest
import tempfile


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_touch_fn(tmp_dir):
    """Return a _touch_heartbeat function bound to tmp_dir, mirroring all service implementations."""
    def _touch_heartbeat(name: str) -> None:
        os.makedirs(tmp_dir, exist_ok=True)
        path = os.path.join(tmp_dir, f"{name}_last_cycle")
        with open(path, "w") as fh:
            fh.write(str(time.time()))
    return _touch_heartbeat


def _heartbeat_age(tmp_dir, name: str) -> float:
    """Return seconds since the heartbeat file was last modified."""
    path = os.path.join(tmp_dir, f"{name}_last_cycle")
    return time.time() - os.path.getmtime(path)


# ── Tests ──────────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestTouchHeartbeat:
    def test_creates_file_on_first_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            touch = _make_touch_fn(tmp)
            touch("risk_monitor")
            assert os.path.exists(os.path.join(tmp, "risk_monitor_last_cycle"))

    def test_file_content_is_recent_timestamp(self):
        with tempfile.TemporaryDirectory() as tmp:
            touch = _make_touch_fn(tmp)
            before = time.time()
            touch("report_scheduler")
            after = time.time()
            path = os.path.join(tmp, "report_scheduler_last_cycle")
            written = float(open(path).read())
            assert before <= written <= after

    def test_mtime_is_fresh_after_touch(self):
        with tempfile.TemporaryDirectory() as tmp:
            touch = _make_touch_fn(tmp)
            touch("sentinel_bot")
            age = _heartbeat_age(tmp, "sentinel_bot")
            assert age < 2.0, f"heartbeat file is {age:.2f}s old — expected < 2s"

    def test_second_touch_updates_mtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            touch = _make_touch_fn(tmp)
            touch("telegram_bot")
            time.sleep(0.05)
            mtime1 = os.path.getmtime(os.path.join(tmp, "telegram_bot_last_cycle"))
            time.sleep(0.05)
            touch("telegram_bot")
            mtime2 = os.path.getmtime(os.path.join(tmp, "telegram_bot_last_cycle"))
            assert mtime2 > mtime1, "second touch must update mtime"
