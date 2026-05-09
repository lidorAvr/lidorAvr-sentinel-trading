from pathlib import Path


def test_runtime_layer_redirects_legacy_config_reads():
    source = Path('sitecustomize.py').read_text(encoding='utf-8')
    assert 'SENTINEL_CONFIG_PATH' in source
    assert '/app/sentinel_config.json' in source
    assert 'sentinel_config.json' in source


def test_runtime_layer_wraps_telegram_handlers():
    source = Path('sitecustomize.py').read_text(encoding='utf-8')
    for term in ['ADMIN_ID', '_guard_decision', 'message_handler', 'callback_query_handler']:
        assert term in source


def test_runtime_layer_adds_report_data_source_note():
    source = Path('sitecustomize.py').read_text(encoding='utf-8')
    assert '_truth_suffix' in source
    assert 'Live/Cached' in source
    assert 'fallback' in source
