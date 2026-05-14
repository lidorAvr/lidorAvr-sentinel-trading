#!/usr/bin/env python3
"""Smoke test for prepare_pi_state_for_deploy.py — runs without pytest."""
import json
import os
import subprocess
import sys
import tempfile
import time


SCRIPT = os.path.join(os.path.dirname(__file__), "prepare_pi_state_for_deploy.py")


def run_script(state_dict):
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as fh:
        json.dump(state_dict, fh)
        path = fh.name
    try:
        result = subprocess.run(
            [sys.executable, SCRIPT, path],
            capture_output=True,
            text=True,
            check=True,
        )
        with open(path) as fh:
            new_state = json.load(fh)
        return new_state, result.stdout
    finally:
        os.unlink(path)
        for p in [f"{path}.pre-mitigation.{int(time.time())}",
                  f"{path}.pre-mitigation.{int(time.time())-1}",
                  f"{path}.pre-mitigation.{int(time.time())-2}"]:
            if os.path.exists(p):
                os.unlink(p)


def assert_eq(actual, expected, msg):
    if actual != expected:
        raise AssertionError(f"{msg}: expected {expected!r}, got {actual!r}")


def test_empty_state():
    new_state, _ = run_script({})
    assert "last_digest_date" in new_state
    assert "positions" not in new_state or new_state["positions"] in (None, {})


def test_position_missing_keys():
    src = {"positions": {"AAPL_123": {"qty": 100, "entry": 150.0}}}
    new_state, _ = run_script(src)
    pos = new_state["positions"]["AAPL_123"]
    assert "last_state_alert_ts" in pos and pos["last_state_alert_ts"] > 0
    assert pos["sizing_leak_alerted"] is False
    assert pos["breakeven_alerted"] is False
    assert pos["runner_decision"] == ""
    assert pos["runner_decision_ts"] == 0.0
    assert pos["qty"] == 100  # original keys preserved
    assert pos["entry"] == 150.0


def test_position_existing_keys_not_overwritten():
    src = {"positions": {"MSFT_99": {"last_state_alert_ts": 12345.0,
                                     "sizing_leak_alerted": True}}}
    new_state, _ = run_script(src)
    pos = new_state["positions"]["MSFT_99"]
    assert_eq(pos["last_state_alert_ts"], 12345.0, "must not overwrite existing ts")
    assert_eq(pos["sizing_leak_alerted"], True, "must not overwrite existing flag")


def test_root_last_digest_date_added_when_missing():
    new_state, _ = run_script({"foo": "bar"})
    assert "last_digest_date" in new_state
    assert_eq(new_state["foo"], "bar", "preserves unrelated root keys")


def test_root_last_digest_date_preserved_when_present():
    new_state, _ = run_script({"last_digest_date": "2026-01-01"})
    assert_eq(new_state["last_digest_date"], "2026-01-01", "must not overwrite existing date")


def test_non_dict_position_entries_skipped():
    src = {"positions": {"GARBAGE": "not_a_dict", "GOOD_1": {"qty": 50}}}
    new_state, _ = run_script(src)
    assert new_state["positions"]["GARBAGE"] == "not_a_dict"
    assert "last_state_alert_ts" in new_state["positions"]["GOOD_1"]


if __name__ == "__main__":
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    failed = []
    for fn in tests:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except Exception as e:
            failed.append((fn.__name__, e))
            print(f"FAIL  {fn.__name__}: {e}")
    if failed:
        sys.exit(1)
    print(f"\n{len(tests)} tests passed.")
