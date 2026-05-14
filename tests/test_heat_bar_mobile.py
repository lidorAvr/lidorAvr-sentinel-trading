"""
Sprint 8 #10 — Mobile UX: heat-bar uses emoji squares, not block chars.

Why this matters: block characters █░ are bidirectional in Hebrew RTL
contexts and visually flip on iOS Telegram. A 70%-filled bar can
read as 30%-filled to a trader on the iPhone — a serious UX bug
because heat score drives risk-sizing decisions.

Coloured emoji circles 🟢⚪ render left-to-right inside RTL lines on
every Telegram client (verified by Sarah on iPhone 14 + Pixel 7).

Sarah's Meeting 6 backlog #28 listed this as a Mobile UX hard rule.
Sprint 8 ships it.
"""
import pytest
import telegram_formatters as tf


@pytest.mark.unit
class TestHeatBarMobileSafe:
    """The bar must NEVER use bidirectional block characters again."""

    def test_filled_char_is_emoji_not_block(self):
        """Block chars (█) flip in RTL on iOS — banned."""
        assert tf._HEAT_FILLED == "🟢"
        assert "█" not in tf._HEAT_FILLED
        assert "▓" not in tf._HEAT_FILLED
        assert "▒" not in tf._HEAT_FILLED

    def test_empty_char_is_emoji_not_block(self):
        assert tf._HEAT_EMPTY == "⚪"
        assert "░" not in tf._HEAT_EMPTY

    def test_full_bar_all_green(self):
        bar = tf._score_to_bar(100)
        # 10 green circles, 0 white
        assert bar == "🟢" * 10
        assert "⚪" not in bar

    def test_empty_bar_all_white(self):
        bar = tf._score_to_bar(0)
        assert bar == "⚪" * 10
        assert "🟢" not in bar

    def test_half_bar_split(self):
        bar = tf._score_to_bar(50)
        # 5 green + 5 white = 10 emoji squares
        assert bar.count("🟢") == 5
        assert bar.count("⚪") == 5

    def test_low_score_mostly_white(self):
        bar = tf._score_to_bar(15)
        # round(15/100 * 10) = round(1.5) = 2 → 2 green, 8 white
        assert bar.count("🟢") == 2
        assert bar.count("⚪") == 8

    def test_score_above_100_clamped(self):
        bar = tf._score_to_bar(150)
        # Caller bug, but bar must stay 10 wide and not crash
        assert bar.count("🟢") == 10
        assert bar.count("⚪") == 0

    def test_score_below_0_clamped(self):
        bar = tf._score_to_bar(-20)
        assert bar.count("🟢") == 0
        assert bar.count("⚪") == 10

    def test_custom_blocks_param_respected(self):
        """fmt_heat_thermometer uses blocks=5 for window breakdowns."""
        bar = tf._score_to_bar(60, blocks=5)
        # 60/100 * 5 = 3 green
        assert bar.count("🟢") == 3
        assert bar.count("⚪") == 2
        assert len([c for c in bar if c in ("🟢", "⚪")]) == 5

    def test_no_block_chars_in_thermometer_output(self):
        """End-to-end: full thermometer output must contain zero block chars."""
        risk_rec = {
            "ok": True, "heat_score": 72,
            "s9_score": 78, "m21_score": 65, "l50_score": 60,
            "recent_10_wr": 70, "all_50_wr": 58,
            "s9_stats": {"n": 9}, "l50_stats": {"n": 27},
            "current_risk_pct": 0.6, "recommended_risk_pct": 0.85,
            "direction": "up",
        }
        out = tf.fmt_heat_thermometer(risk_rec)
        assert "█" not in out
        assert "░" not in out
        assert "▓" not in out
        assert "🟢" in out  # at least one filled emoji
        assert "⚪" in out  # at least one empty emoji
