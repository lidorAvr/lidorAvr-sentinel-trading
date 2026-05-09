import ast
from pathlib import Path


def test_main_and_telegram_bot_use_the_same_nav_config_path():
    main_source = Path("main.py").read_text(encoding="utf-8")
    bot_source = Path("telegram_bot.py").read_text(encoding="utf-8")

    assert "/app/sentinel_config.json" in main_source
    assert "sentinel_config.json" in bot_source
    assert "/app/sentinel_config.json" in bot_source, (
        "telegram_bot.py must read the same NAV config file that main.py writes. "
        "Otherwise NAV may be stale and user-facing risk math may be wrong."
    )


def test_telegram_bot_restricts_message_handling_to_admin_id():
    source = Path("telegram_bot.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    handlers = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name in {"handle_all_messages", "handle_queries"}
    ]
    assert handlers, "Expected Telegram message/callback handlers to exist."

    for handler in handlers:
        body = ast.get_source_segment(source, handler) or ""
        assert "ADMIN_ID" in body and "chat_id" in body, (
            f"{handler.name} should verify chat_id against ADMIN_ID before doing any work. "
            "Without this, any user who reaches the bot may trigger portfolio reads/writes."
        )


def test_user_facing_messages_mark_fallback_data_as_estimated_or_stale():
    source = Path("telegram_bot.py").read_text(encoding="utf-8")
    fallback_patterns = [
        "curr is None: curr = entry",
        "ec.get_live_price(sym) or float(row",
        "ibkr_nav if ibkr_nav else",
    ]
    uses_fallbacks = any(pattern in source for pattern in fallback_patterns)
    assert uses_fallbacks, "This test is meaningful only while fallbacks exist."

    truth_words = ["משוער", "הערכה", "לא זמין", "stale", "estimated", "fallback"]
    assert any(word in source for word in truth_words), (
        "When prices or NAV fall back to entry/deposited values, Telegram output must explicitly say so. "
        "Otherwise the system presents estimates as truth."
    )
