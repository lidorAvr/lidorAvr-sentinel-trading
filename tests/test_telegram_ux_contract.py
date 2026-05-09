from pathlib import Path


def test_long_telegram_messages_are_split_safely_below_limit():
    source = Path("telegram_bot.py").read_text(encoding="utf-8")
    assert "def send_long_message" in source
    assert "max_len = 3900" in source, "Telegram messages should stay safely below the 4096-char API limit."


def test_portfolio_uses_long_message_helper_for_user_reports():
    source = Path("telegram_bot.py").read_text(encoding="utf-8")
    portfolio_section = source[source.find('if text in ["📊 חדר מצב (פוזיציות)"'):]
    assert "send_long_message" in portfolio_section, (
        "Portfolio/status reports should use send_long_message so Hebrew RTL reports do not fail "
        "or get cut when many positions are open."
    )


def test_hebrew_rtl_marker_is_available_for_reports():
    source = Path("telegram_bot.py").read_text(encoding="utf-8")
    assert 'RTL = "\\u200F"' in source


def test_reports_do_not_use_arrow_glyphs_that_break_rtl_readability():
    source = Path("telegram_bot.py").read_text(encoding="utf-8")
    assert "->" not in source
    assert "=>" not in source
