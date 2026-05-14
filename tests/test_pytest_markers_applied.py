"""
Sprint 8 #4 — meta-test: every collected test has exactly one tier marker.

Chris (QA) flagged in Meeting 8: pytest.ini declared markers since Sprint 3,
but they were never applied — `pytest -m unit` returned 0. This test is the
guardrail that prevents the gap from re-opening: if a future test file is
added without a marker AND it's not in the conftest auto-tag lists, this
fails loudly.

Without this guardrail, marker drift is invisible — you'd only notice
when CI accidentally skipped tests because `-m "not slow"` deselected them.
"""
import pytest
import subprocess
import sys
from pathlib import Path


@pytest.mark.unit
class TestPytestMarkersApplied:
    """Every collected test must have exactly one of: unit / integration / slow."""

    def _collect(self, marker: str) -> int:
        """Return the count of tests selected by `-m <marker>`. Uses --collect-only
        to avoid running the suite recursively."""
        repo_root = Path(__file__).parent.parent
        env = {
            "TELEGRAM_BOT_TOKEN": "test-token",
            "TELEGRAM_ADMIN_ID": "12345",
            "SUPABASE_URL": "https://test.supabase.co",
            "SUPABASE_KEY": "test-key",
            "DEV_PIN": "0000",
            "PATH": "/usr/bin:/bin:/usr/local/bin",
        }
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "--collect-only", "-q",
             "-m", marker, "--no-header"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            env=env,
        )
        # Last meaningful line: "N/M tests collected (X deselected)"
        for line in reversed(result.stdout.splitlines()):
            if "collected" in line:
                # e.g. "842/1248 tests collected (406 deselected)"
                first_token = line.strip().split()[0]
                if "/" in first_token:
                    return int(first_token.split("/")[0])
                # Or "842 tests collected" if no deselection
                try:
                    return int(first_token)
                except ValueError:
                    pass
        return -1  # parse failure

    def test_three_tiers_partition_the_suite(self):
        """unit + integration + slow = total. No test left untagged.
        No test in two tiers."""
        unit = self._collect("unit")
        integration = self._collect("integration")
        slow = self._collect("slow")
        # All three counts must be positive
        assert unit > 0, f"unit count was {unit} — auto-tagging broke?"
        assert integration > 0, f"integration count was {integration}"
        assert slow > 0, f"slow count was {slow}"
        # The three tiers must partition the total
        # (this test itself is a unit test, so it's counted in unit)
        total = self._collect("unit or integration or slow")
        assert unit + integration + slow == total, (
            f"Markers overlap or have gaps: "
            f"unit={unit} + integration={integration} + slow={slow} "
            f"= {unit + integration + slow}, but combined query returns {total}"
        )

    def test_no_test_lacks_a_tier_marker(self):
        """A test without any of unit/integration/slow markers should not exist."""
        all_collected = self._collect("unit or integration or slow")
        every_test = self._collect("")  # no marker filter — full suite
        # If they don't match, some tests have no tier marker
        assert all_collected == every_test, (
            f"{every_test - all_collected} tests have no tier marker "
            f"— add their file to _INTEGRATION_FILES, _SLOW_FILES, "
            f"or let conftest.py default them to unit."
        )

    def test_ci_default_excludes_slow(self):
        """`pytest -m 'not slow'` is the CI command — must include unit + integration."""
        not_slow = self._collect("not slow")
        unit = self._collect("unit")
        integration = self._collect("integration")
        assert not_slow == unit + integration, (
            f"`-m 'not slow'` should be unit + integration ({unit + integration}), "
            f"got {not_slow}"
        )
