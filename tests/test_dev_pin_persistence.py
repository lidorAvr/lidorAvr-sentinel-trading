"""
Sprint 6 — persistent PIN failed-attempt tracking.

Verifies that dev_pin_record_failure() survives a process restart, closing the
post-restart brute-force window that existed in Sprint 5 (rate-limit state was
in-memory only).
"""
import sys, os, json, time
import pytest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Heavy deps that telegram_devops pulls in transitively must be stubbed
# before import — same pattern as test_developer_menu.py.
for _mod in ("telebot", "telebot.types", "supabase", "dotenv",
             "adaptive_risk_engine", "engine_core", "telegram_formatters"):
    sys.modules.setdefault(_mod, MagicMock())

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("TELEGRAM_ADMIN_ID", "12345")
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-key")

import telegram_devops as devops


@pytest.fixture
def tmp_failed_file(tmp_path, monkeypatch):
    """Redirect PIN failure persistence to a tmp file and reset in-memory state."""
    path = tmp_path / "dev_pin_failed.json"
    monkeypatch.setattr(devops, "_PIN_FAILED_FILE", str(path))
    monkeypatch.setattr(devops, "_PIN_FAILED_ATTEMPTS", {})
    return path


@pytest.mark.unit
class TestPinFailurePersistence:

    def test_record_failure_writes_file(self, tmp_failed_file):
        devops.dev_pin_record_failure(42)
        assert tmp_failed_file.exists()
        data = json.loads(tmp_failed_file.read_text())
        assert "42" in data
        assert len(data["42"]) == 1

    def test_record_failure_appends_multiple(self, tmp_failed_file):
        devops.dev_pin_record_failure(42)
        devops.dev_pin_record_failure(42)
        devops.dev_pin_record_failure(42)
        data = json.loads(tmp_failed_file.read_text())
        assert len(data["42"]) == 3

    def test_load_survives_restart(self, tmp_failed_file):
        """Simulate: record failures, then restart container (re-load module state)."""
        devops.dev_pin_record_failure(42)
        devops.dev_pin_record_failure(42)
        devops.dev_pin_record_failure(42)
        # Restart: clear in-memory state, reload from disk
        devops._PIN_FAILED_ATTEMPTS.clear()
        devops._PIN_FAILED_ATTEMPTS.update(devops._load_pin_failures())
        assert devops.dev_pin_rate_limited(42) is True

    def test_load_drops_expired_entries(self, tmp_failed_file, monkeypatch):
        """Entries older than _PIN_RATE_LIMIT_WINDOW (300s) must not be loaded."""
        old_ts = time.time() - 400  # outside 5-min window
        tmp_failed_file.write_text(json.dumps({"42": [old_ts, old_ts]}))
        loaded = devops._load_pin_failures()
        assert loaded == {}

    def test_load_keeps_fresh_entries(self, tmp_failed_file):
        fresh_ts = time.time() - 60  # 1 minute ago
        tmp_failed_file.write_text(json.dumps({"42": [fresh_ts]}))
        loaded = devops._load_pin_failures()
        assert 42 in loaded
        assert len(loaded[42]) == 1

    def test_load_handles_corrupt_file(self, tmp_failed_file):
        tmp_failed_file.write_text("not valid json {")
        assert devops._load_pin_failures() == {}

    def test_load_handles_missing_file(self, tmp_failed_file):
        # tmp_failed_file fixture sets path but doesn't create the file
        assert not tmp_failed_file.exists()
        assert devops._load_pin_failures() == {}

    def test_rate_limit_triggers_at_three_failures(self, tmp_failed_file):
        devops.dev_pin_record_failure(99)
        assert devops.dev_pin_rate_limited(99) is False
        devops.dev_pin_record_failure(99)
        assert devops.dev_pin_rate_limited(99) is False
        devops.dev_pin_record_failure(99)
        assert devops.dev_pin_rate_limited(99) is True

    def test_rate_limit_per_chat_isolated(self, tmp_failed_file):
        """Locking out chat A must not affect chat B."""
        for _ in range(3):
            devops.dev_pin_record_failure(100)
        assert devops.dev_pin_rate_limited(100) is True
        assert devops.dev_pin_rate_limited(200) is False
