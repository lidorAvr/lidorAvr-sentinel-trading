"""
Comprehensive tests for telegram_formatters.py.
Covers UX requirements:
  - RTL marker present
  - Hebrew text present
  - Markdown bold/code correct
  - Actionability label present where required
  - No exit/sell instructions in ALGO messages
  - Stale data labelled clearly
  - Telegram 4096 char limit not exceeded for typical inputs
  - All required data fields rendered
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import telegram_formatters as tf

RTL = "‏"
MAX_TELEGRAM_MSG = 4096


# ── fmt_position_card ──────────────────────────────────────────────────────────

class TestFmtPositionCard:
    def _card(self, **kwargs):
        defaults = dict(
            i=1, sym="AAPL", setup="VCP", days_held=10,
            curr=155.0, entry=150.0, open_pnl=50.0,
            pos_value=1550.0, weight_pct=5.0,
            total_pos_profit=50.0, total_campaign_r=0.5,
            open_r_val=0.5, status="🟢 Healthy", action_short="Hold",
        )
        defaults.update(kwargs)
        return tf.fmt_position_card(**defaults)

    def test_contains_symbol(self):
        assert "AAPL" in self._card()

    def test_contains_setup(self):
        assert "VCP" in self._card()

    def test_contains_days_held(self):
        assert "10d" in self._card()

    def test_contains_entry_price(self):
        assert "150.00" in self._card()

    def test_contains_current_price(self):
        assert "155.00" in self._card()

    def test_positive_pnl_green_icon(self):
        assert "🟢" in self._card(open_pnl=100.0)

    def test_negative_pnl_red_icon(self):
        assert "🔴" in self._card(open_pnl=-50.0)

    def test_contains_weight_pct(self):
        assert "5.0%" in self._card()

    def test_contains_status(self):
        assert "Healthy" in self._card()

    def test_contains_action(self):
        assert "Hold" in self._card()

    def test_rtl_marker_present(self):
        assert RTL in self._card()

    def test_locked_profit_shown_when_positive(self):
        result = self._card(locked_profit=500.0)
        assert "500" in result
        assert "🔒" in result

    def test_locked_profit_hidden_when_zero(self):
        result = self._card(locked_profit=0)
        assert "🔒" not in result

    def test_giveback_shown_when_positive(self):
        result = self._card(giveback_risk=300.0)
        assert "300" in result
        assert "⚡" in result

    def test_capital_risk_shown_when_positive(self):
        result = self._card(capital_risk=200.0)
        assert "200" in result
        assert "⚠️" in result

    def test_addon_tag_shown(self):
        result = self._card(add_on_count=2, base_price=148.0)
        assert "+2" in result or "(+2)" in result
        assert "148.00" in result

    def test_no_stop_data_shows_warning(self):
        result = self._card(
            total_campaign_r=0, open_r_val=0,
            capital_risk=0, locked_profit=0,
        )
        assert "חסר סטופ" in result or "N/A" in result

    def test_returns_string(self):
        assert isinstance(self._card(), str)

    def test_under_telegram_limit(self):
        result = self._card(locked_profit=1000, giveback_risk=500, capital_risk=300)
        assert len(result) < MAX_TELEGRAM_MSG


# ── fmt_summary_footer ─────────────────────────────────────────────────────────

class TestFmtSummaryFooter:
    def _footer(self, **kwargs):
        defaults = dict(
            total_open_pnl=1000.0, total_disc_pnl=600.0, total_algo_pnl=400.0,
            total_exposure=15000.0, acc_size=20000.0, total_locked_profit=500.0,
            total_giveback_risk=200.0, total_risk=0.0, total_realized_camp=300.0,
            disc_count=2, algo_count=1,
        )
        defaults.update(kwargs)
        return tf.fmt_summary_footer(**defaults)

    def test_contains_exposure_pct(self):
        result = self._footer()
        assert "75.0%" in result  # 15000/20000*100

    def test_contains_total_pnl(self):
        assert "1,000" in self._footer() or "1000" in self._footer()

    def test_disc_section_shown(self):
        assert "דיסקרשן" in self._footer()
        assert "(2)" in self._footer()

    def test_algo_section_shown(self):
        assert "אלגו" in self._footer()
        assert "(1)" in self._footer()

    def test_disc_hidden_when_zero(self):
        result = self._footer(disc_count=0, total_disc_pnl=0)
        assert "דיסקרשן" not in result

    def test_algo_hidden_when_zero(self):
        result = self._footer(algo_count=0, total_algo_pnl=0)
        assert "אלגו" not in result

    def test_warning_when_both_zero(self):
        result = self._footer(disc_count=0, algo_count=0)
        assert "setup_type" in result or "אין פוזיציות" in result

    def test_locked_profit_shown(self):
        assert "🔒" in self._footer()

    def test_giveback_shown(self):
        assert "⚡" in self._footer()

    def test_realized_camp_shown(self):
        assert "ממומש" in self._footer()

    def test_rtl_present(self):
        assert RTL in self._footer()

    def test_returns_string(self):
        assert isinstance(self._footer(), str)


# ── fmt_regime_report ──────────────────────────────────────────────────────────

class TestFmtRegimeReport:
    def _regime_ok(self):
        return {
            "ok": True,
            "data": {
                "color": "🟢", "status": "Healthy", "text": "סביבה חיובית",
                "signals": {
                    "score": 4, "max_score": 4,
                    "spy_above_ma20": True, "spy_close": 500.0, "spy_ma20": 490.0,
                    "spy_above_ma50": True, "spy_ma50": 480.0,
                    "spy_ma20_above_ma50": True,
                    "qqq_above_ma20": True, "qqq_close": 430.0, "qqq_ma20": 420.0,
                }
            }
        }

    def test_contains_market_status(self):
        result = tf.fmt_regime_report(self._regime_ok(), 30.0, 5000, 3000, 2000, 20000)
        assert "Healthy" in result

    def test_contains_exposure(self):
        result = tf.fmt_regime_report(self._regime_ok(), 30.0, 5000, 3000, 2000, 20000)
        assert "30.0%" in result

    def test_score_shown(self):
        result = tf.fmt_regime_report(self._regime_ok(), 30.0, 0, 0, 0, 20000)
        assert "4/4" in result

    def test_checkmarks_for_passing_signals(self):
        result = tf.fmt_regime_report(self._regime_ok(), 30.0, 0, 0, 0, 20000)
        assert "✅" in result

    def test_algo_exposure_shown(self):
        result = tf.fmt_regime_report(self._regime_ok(), 30.0, 5000, 0, 0, 20000)
        assert "אלגו" in result

    def test_unknown_regime(self):
        result = tf.fmt_regime_report({"ok": False}, 10.0, 0, 0, 0, 20000)
        assert "לא ידוע" in result

    def test_actionability_label_present(self):
        result = tf.fmt_regime_report(self._regime_ok(), 30.0, 0, 0, 0, 20000)
        assert "מידע בלבד" in result or "observation" in result.lower()

    def test_rtl_present(self):
        result = tf.fmt_regime_report(self._regime_ok(), 30.0, 0, 0, 0, 20000)
        assert RTL in result

    def test_returns_string(self):
        assert isinstance(tf.fmt_regime_report({"ok": False}, 0, 0, 0, 0, 0), str)


# ── fmt_adaptive_risk_block ────────────────────────────────────────────────────

class TestFmtAdaptiveRiskBlock:
    def _rec(self, **kwargs):
        defaults = dict(
            ok=True, heat_color="🟢", heat_label="חם", heat_score=75.0,
            win_streak=3, loss_streak=0, recent_10_wr=70.0, all_50_wr=65.0,
            current_risk_pct=0.5, recommended_risk_pct=0.75,
            current_risk_usd=100.0, recommended_risk_usd=150.0,
            direction="up", step_type="שלב מעלה",
        )
        defaults.update(kwargs)
        return defaults

    def test_not_ok_returns_graceful_message(self):
        result = tf.fmt_adaptive_risk_block({"ok": False, "message": "אין נתונים"})
        assert "אין נתונים" in result

    def test_contains_heat_label(self):
        assert "חם" in tf.fmt_adaptive_risk_block(self._rec())

    def test_contains_win_streak(self):
        result = tf.fmt_adaptive_risk_block(self._rec(win_streak=3))
        assert "3" in result

    def test_loss_streak_shown_with_warning(self):
        result = tf.fmt_adaptive_risk_block(self._rec(win_streak=0, loss_streak=4))
        assert "4" in result
        assert "⚠️" in result

    def test_direction_up_arrow(self):
        result = tf.fmt_adaptive_risk_block(self._rec(direction="up"))
        assert "⬆️" in result

    def test_direction_down_fast_double_arrow(self):
        result = tf.fmt_adaptive_risk_block(self._rec(direction="down_fast"))
        assert "⬇️" in result

    def test_same_pct_shows_maintain(self):
        result = tf.fmt_adaptive_risk_block(
            self._rec(current_risk_pct=0.5, recommended_risk_pct=0.5,
                      current_risk_usd=100, recommended_risk_usd=100)
        )
        assert "ללא שינוי" in result

    def test_actionability_review_required(self):
        result = tf.fmt_adaptive_risk_block(self._rec())
        assert "לבדוק" in result or "review" in result.lower()

    def test_win_rate_shown(self):
        result = tf.fmt_adaptive_risk_block(self._rec())
        assert "70%" in result or "70" in result

    def test_returns_string(self):
        assert isinstance(tf.fmt_adaptive_risk_block(self._rec()), str)


# ── fmt_minervini_trend_template ───────────────────────────────────────────────

class TestFmtMinerviniTrendTemplate:
    def _tt_ok(self, passed=7):
        criteria = {k: True for k in range(passed)}
        criteria.update({k: False for k in range(passed, 8)})
        return {"ok": True, "data": {"passed": passed, "criteria": criteria}}

    def test_no_data_returns_error_msg(self):
        result = tf.fmt_minervini_trend_template("AAPL", {"ok": False})
        assert "אין מספיק נתונים" in result

    def test_contains_symbol(self):
        assert "AAPL" in tf.fmt_minervini_trend_template("AAPL", self._tt_ok())

    def test_score_shown(self):
        result = tf.fmt_minervini_trend_template("AAPL", self._tt_ok(7))
        assert "7/8" in result

    def test_full_trend_green(self):
        result = tf.fmt_minervini_trend_template("AAPL", self._tt_ok(7))
        assert "🟢" in result

    def test_partial_yellow(self):
        result = tf.fmt_minervini_trend_template("AAPL", self._tt_ok(5))
        assert "🟡" in result

    def test_failed_red(self):
        result = tf.fmt_minervini_trend_template("AAPL", self._tt_ok(3))
        assert "🔴" in result

    def test_checkmarks_and_crosses_present(self):
        result = tf.fmt_minervini_trend_template("AAPL", self._tt_ok(5))
        assert "✅" in result
        assert "❌" in result

    def test_rtl_present(self):
        assert RTL in tf.fmt_minervini_trend_template("AAPL", self._tt_ok())

    def test_returns_string(self):
        assert isinstance(tf.fmt_minervini_trend_template("TSLA", {"ok": False}), str)

    def test_under_telegram_limit(self):
        result = tf.fmt_minervini_trend_template("AAPL", self._tt_ok(8))
        assert len(result) < MAX_TELEGRAM_MSG


# ── ALGO safety — cross-formatter ─────────────────────────────────────────────

class TestAlgoSafetyAcrossFormatters:
    """No formatter should ever issue exit/sell/stop instructions for ALGO."""

    FORBIDDEN_WORDS = ["exit", "sell", "close position", "סגור פוזיציה", "צא מהפוזיציה"]

    def _check(self, text):
        lower = text.lower()
        for word in self.FORBIDDEN_WORDS:
            assert word not in lower, f"Forbidden word '{word}' found in message"

    def test_algo_risk_note_no_exit(self):
        self._check(tf.fmt_algo_risk_note("QQQ", -2.0, 15.0, "ירידה חדה"))

    def test_position_card_holds_are_ok(self):
        card = tf.fmt_position_card(
            1, "QQQ", "ALGO", 5, 430.0, 420.0, 50.0,
            4300.0, 10.0, 50.0, 0.5, 0.5, "🟠 מנוהל חיצונית", "Hold & Monitor"
        )
        # "Hold" is fine, exit verbs are forbidden
        self._check(card)


# ── Markdown validity ──────────────────────────────────────────────────────────

class TestMarkdownValidity:
    """Check that backticks and bold markers are balanced (basic check)."""

    def _count_backticks(self, text):
        # Inline code blocks use single backtick — count must be even
        return text.count('`')

    def _count_bold(self, text):
        return text.count('*')

    def test_position_card_balanced_backticks(self):
        card = tf.fmt_position_card(
            1, "AAPL", "VCP", 10, 155.0, 150.0, 50.0,
            1550.0, 5.0, 50.0, 0.5, 0.5, "🟢", "Hold",
        )
        assert self._count_backticks(card) % 2 == 0

    def test_position_card_balanced_bold(self):
        card = tf.fmt_position_card(
            1, "AAPL", "VCP", 10, 155.0, 150.0, 50.0,
            1550.0, 5.0, 50.0, 0.5, 0.5, "🟢", "Hold",
        )
        assert self._count_bold(card) % 2 == 0

    def test_algo_risk_note_balanced_backticks(self):
        note = tf.fmt_algo_risk_note("QQQ", 1.5, 10.0, "בדיקה")
        assert self._count_backticks(note) % 2 == 0

    def test_trend_template_balanced_bold(self):
        tt = {"ok": True, "data": {"passed": 7, "criteria": {i: True for i in range(8)}}}
        result = tf.fmt_minervini_trend_template("AAPL", tt)
        assert self._count_bold(result) % 2 == 0


# ── Sprint-13 / Mark §2 — missing-stops split-label helper ──────────────────

class TestClassifyMissingStops:
    """Mark §2: split detected missing-stop rows by lifecycle. Pure /
    read-only — never fabricates a stop, never a stat, total preserved."""

    def _rows_55_like(self):
        # Mirrors the live finding shape: MSGE/SNEX/TSLA open, JPM/HP closed.
        return [
            {"symbol": "MSGE", "campaign_id": "MSGE_1"},
            {"symbol": "MSGE", "campaign_id": "MSGE_1"},
            {"symbol": "SNEX", "campaign_id": "SNEX_2"},
            {"symbol": "TSLA", "campaign_id": "TSLA_3"},
            {"symbol": "JPM", "campaign_id": "JPM_OLD"},
            {"symbol": "HP", "campaign_id": "HP_OLD"},
            {"symbol": "HP", "campaign_id": None},  # no campaign → hygiene
        ]

    def test_split_routes_open_vs_closed(self):
        rows = self._rows_55_like()
        open_ids = {"MSGE_1", "SNEX_2", "TSLA_3"}
        s = tf.classify_missing_stops(rows, open_ids)
        assert s["open_count"] == 4          # 2x MSGE + SNEX + TSLA
        assert s["legacy_count"] == 3        # 2x HP-ish + JPM
        assert s["open_symbols"] == ["MSGE", "SNEX", "TSLA"]
        assert s["legacy_symbols"] == ["HP", "JPM"]

    def test_total_invariant_no_row_lost_or_duplicated(self):
        rows = self._rows_55_like()
        s = tf.classify_missing_stops(rows, {"MSGE_1"})
        assert s["total"] == len(rows)
        assert s["open_count"] + s["legacy_count"] == s["total"]

    def test_referentially_transparent(self):
        rows = self._rows_55_like()
        open_ids = {"MSGE_1", "TSLA_3"}
        a = tf.classify_missing_stops(rows, open_ids)
        b = tf.classify_missing_stops(rows, open_ids)
        assert a == b
        # input not mutated
        assert rows == self._rows_55_like()
        assert open_ids == {"MSGE_1", "TSLA_3"}

    def test_no_open_campaigns_all_hygiene(self):
        rows = self._rows_55_like()
        s = tf.classify_missing_stops(rows, set())
        assert s["open_count"] == 0
        assert s["legacy_count"] == len(rows)

    def test_empty_inputs(self):
        s = tf.classify_missing_stops([], set())
        assert s == {
            "open_count": 0, "open_symbols": [],
            "legacy_count": 0, "legacy_symbols": [], "total": 0,
        }
        assert tf.classify_missing_stops(None, None)["total"] == 0

    def test_missing_symbol_becomes_placeholder_not_a_price(self):
        s = tf.classify_missing_stops([{"campaign_id": "X"}], {"X"})
        assert s["open_symbols"] == ["?"]
        # never emits a numeric stop / price
        for sym in s["open_symbols"] + s["legacy_symbols"]:
            assert not sym.replace(".", "").isdigit()

    def test_never_emits_stop_price_or_stat_key(self):
        rows = [{"symbol": "MSGE", "campaign_id": "MSGE_1"}]
        s = tf.classify_missing_stops(rows, {"MSGE_1"})
        keys = set(s.keys())
        # only count/symbols/total — no stop, no $, no R/WR/PF/expectancy
        assert keys == {
            "open_count", "open_symbols",
            "legacy_count", "legacy_symbols", "total",
        }
        for forbidden in ("stop", "price", "wr", "expectancy", "pf", "r_", "usd"):
            assert not any(forbidden in k.lower() for k in keys)


class TestMissingStopsSplitLabel:
    """The /health split-label string: non-numeric, Mark §2 routing,
    no fabricated stop, empty when nothing missing."""

    def test_empty_when_nothing_missing(self):
        assert tf.fmt_missing_stops_split_label(
            {"total": 0, "open_count": 0, "legacy_count": 0}
        ) == ""
        assert tf.fmt_missing_stops_split_label(None) == ""

    def test_open_subset_routes_to_journal_backlog_language(self):
        split = tf.classify_missing_stops(
            [{"symbol": "MSGE", "campaign_id": "M1"}], {"M1"}
        )
        line = tf.fmt_missing_stops_split_label(split)
        assert "פוזיציות פתוחות ללא סטופ: 1" in line
        assert "MSGE" in line
        assert "לא יומצא" in line          # no fabrication promise
        assert "לא נכלל בסטטיסטיקה" in line  # not counted
        # non-numeric: no stop price / $ / R-tier
        assert "$" not in line
        assert "P0" not in line and "P1" not in line

    def test_legacy_subset_routes_to_clean_language(self):
        split = tf.classify_missing_stops(
            [{"symbol": "JPM", "campaign_id": "OLD"}], set()
        )
        line = tf.fmt_missing_stops_split_label(split)
        assert "סגורות/ארכיון" in line
        assert "/clean" in line
        assert "אינו משימה" in line

    def test_mark_verbatim_backlog_constant_only_symbol_substituted(self):
        # MISSING_STOP_BACKLOG_HE is VERBATIM Mark §2 :76-80; the ONLY
        # substitution is {SYMBOL} — never a price.
        rendered = tf.MISSING_STOP_BACKLOG_HE.format(SYMBOL="MSGE")
        assert "פוזיציה פתוחה ללא סטופ — MSGE" in rendered
        assert "לא יומצא ערך" in rendered
        assert "לא נכלל בסטטיסטיקה" in rendered
        assert "{SYMBOL}" not in rendered
        assert "150.50" in rendered  # Mark's literal example, not a real stop
