from pathlib import Path


def test_secure_runner_exists_and_wraps_handlers():
    source = Path('telegram_bot_secure_runner.py').read_text(encoding='utf-8')
    assert 'install_telegram_hardening' in source
    assert 'message_handler' in source
    assert 'callback_query_handler' in source
    assert 'guard_decision' in source


def test_secure_runner_marks_user_reports_with_data_source():
    source = Path('telegram_bot_secure_runner.py').read_text(encoding='utf-8')
    assert 'truth_suffix' in source
    assert 'מקור נתונים' in source
    assert 'הערכה' in source


def test_secure_runner_uses_server_workdir_for_shared_config():
    source = Path('telegram_bot_secure_runner.py').read_text(encoding='utf-8')
    assert 'SENTINEL_WORKDIR' in source
    assert '/home/orangepi/sentinel_trading' in source
