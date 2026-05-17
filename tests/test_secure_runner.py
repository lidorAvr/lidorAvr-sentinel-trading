from pathlib import Path

# Sprint-25 A1 (Testing P1-1 / Ops F5): anchor the protected-file reads
# to the repo root via THIS file, NOT a CWD-relative bare
# `Path('telegram_bot_secure_runner.py')`. Proven before the fix: running
# `pytest tests/test_secure_runner.py` from /tmp → 3 FAILED with
# `FileNotFoundError`; from repo root → 3 passed (the exact Sprint-24
# commit/env-dependent class). This is the SOLE production-protection test
# for telegram_bot_secure_runner.py (a CLAUDE.md hard-constrained file:
# admin protection, no-bypass), so it must be CWD-independent.
_SECURE_RUNNER = (Path(__file__).resolve().parents[1]
                  / "telegram_bot_secure_runner.py")


def test_secure_runner_exists_and_wraps_handlers():
    assert _SECURE_RUNNER.is_file(), (
        f"secure runner not found at {_SECURE_RUNNER} — path must be "
        "repo-root anchored, never CWD-relative (Sprint-25 A1 P1-1)")
    source = _SECURE_RUNNER.read_text(encoding='utf-8')
    assert 'install_telegram_hardening' in source
    assert 'message_handler' in source
    assert 'callback_query_handler' in source
    assert 'guard_decision' in source


def test_secure_runner_marks_user_reports_with_data_source():
    assert _SECURE_RUNNER.is_file()
    source = _SECURE_RUNNER.read_text(encoding='utf-8')
    assert 'truth_suffix' in source
    assert 'מקור נתונים' in source
    assert 'הערכה' in source


def test_secure_runner_uses_server_workdir_for_shared_config():
    assert _SECURE_RUNNER.is_file()
    source = _SECURE_RUNNER.read_text(encoding='utf-8')
    assert 'SENTINEL_WORKDIR' in source
    assert '/home/orangepi/sentinel_trading' in source
