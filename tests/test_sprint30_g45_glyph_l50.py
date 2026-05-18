"""
Sprint-30 — G4 + G5 acceptance tests.

G4 — bot_health.py doubled status-glyph fix (R10 / Sprint-29 F7 / D1):
  `engine_core.get_nav_with_freshness()['freshness_label']` ALREADY begins
  with its own status emoji; `ok()/warn()/bad()` re-prefix a second one ⇒
  `✅ ✅`, `🔴 🟠`, `⚠️ 🟠`, `🔴 🚨` (the two glyphs can DISAGREE because the
  wrapper severity is the is_stale/is_critical ROUTING, not the label glyph).
  Acceptance: for EVERY freshness state the engine can emit, the NAV check
  line carries exactly ONE correct status glyph and the two glyphs never
  disagree (no doubling, the label TEXT preserved). engine_core is
  BYTE-LOCKED — its real label strings are consumed/reconstructed, never
  modified. The fix is asserted through the REAL build_health_report().

G5 — telegram_formatters.py R-ALGO-3 finish (Sprint-29 F2 / D2):
  the score line printed the hardcoded literal "S9(9) … L50(50)" directly
  above the honest "מדגם נוכחי: N/50" caveat W-A3 added — an on-screen
  self-contradiction. Acceptance: <50 true sample ⇒ the score line shows
  the TRUE per-window N (no contradiction with the N/50 caveat); ≥50 ⇒ the
  line is BYTE-IDENTICAL to the pre-fix literal; the legacy/synthetic
  risk_rec that omits a window stat keeps today's literal (no pin weakened).
"""
import sys, os, types as py_types
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ── Stub heavy deps if not yet loaded ─────────────────────────────────────────
for _mod in ["telebot", "supabase", "dotenv"]:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

if "bot_core" not in sys.modules:
    _bc = py_types.ModuleType("bot_core")
    _bc.bot        = MagicMock()
    _bc.supabase   = MagicMock()
    _bc.user_state = {}
    _bc.RTL        = "‏"
    _bc.TOKEN      = ""
    _bc.ADMIN_ID   = ""
    sys.modules["bot_core"] = _bc

import bot_health as bh           # noqa: E402
import telegram_formatters as tf  # noqa: E402

_STATUS_GLYPHS = ("✅", "⚠️", "🔴", "🟠", "🟡", "🚨")


# ════════════════════════════════════════════════════════════════════════════
# G4 — single correct status glyph for ALL freshness states
# ════════════════════════════════════════════════════════════════════════════
def _make_supabase():
    sb = MagicMock()

    def _table(name):
        chain = MagicMock()
        chain.select.return_value = chain
        chain.order.return_value = chain
        chain.limit.return_value = chain
        chain.execute.return_value = MagicMock(data=[{"trade_date": "2025-05-12"}])
        return chain
    sb.table.side_effect = _table
    return sb


def _health_with_nav(nav_info: dict) -> str:
    ec_mock = MagicMock()
    ec_mock.get_nav_with_freshness.return_value = nav_info
    cfg = {"total_deposited": 10000.0, "risk_pct_input": 0.5}
    with patch.object(bh, "supabase", _make_supabase()), \
         patch.object(bh, "ec", ec_mock), \
         patch.object(bh, "get_account_settings", lambda: cfg), \
         patch.dict(os.environ, {"TELEGRAM_ADMIN_ID": "1"}, clear=False):
        return bh.build_health_report()


def _nav_line(report: str, needle: str) -> str:
    return next(ln for ln in report.split("\n") if needle in ln)


def _leading_glyphs(line: str) -> list:
    """All status glyphs that appear at the front of the line, in order
    (after stripping the leading RTL marker the report prefixes)."""
    s = line.lstrip("‏").lstrip()
    found = []
    while True:
        for g in _STATUS_GLYPHS:
            if s.startswith(g):
                found.append(g)
                s = s[len(g):].lstrip()
                break
        else:
            break
    return found


# The SIX real freshness-label shapes engine_core.get_nav_with_freshness can
# emit (engine_core.py:1600, 1613-1634) — consumed VERBATIM, never modified.
# (label, nav_info routing flags, expected SINGLE wrapper glyph, a needle.)
_FRESHNESS_CASES = [
    # fresh broker NAV  (engine_core.py:1617 ✅)            → ok() ✅
    ("✅ NAV $7,934 — עודכן לפני 0.1ש׳",
     dict(ok=True, is_critical=False, is_stale=False), "✅", "עודכן לפני 0.1"),
    # stale, parseable ts (engine_core.py:1615 🟡)          → warn() ⚠️
    ("🟡 NAV $7,934 — עודכן לפני 30ש׳",
     dict(ok=True, is_critical=False, is_stale=True), "⚠️", "עודכן לפני 30"),
    # critical, parseable ts (engine_core.py:1613 🔴)       → bad() 🔴
    ("🔴 NAV $7,934 — ישן 60ש׳ (לא עודכן!)",
     dict(ok=True, is_critical=True, is_stale=True), "🔴", "לא עודכן!"),
    # unparseable ts → manual (engine_core.py:1626 ⚠️)      → warn() ⚠️
    ("⚠️ NAV $7,934 — תאריך עדכון לא תקין",
     dict(ok=True, is_critical=False, is_stale=True), "⚠️", "תאריך עדכון לא תקין"),
    # no timestamp → manual (engine_core.py:1634 🟠)        → warn() ⚠️
    ("🟠 NAV $7,922 — אין timestamp (הוגדר ידנית)",
     dict(ok=True, is_critical=False, is_stale=True), "⚠️", "הוגדר ידנית"),
    # synthetic disagreeing label (the historic test's 🚨)  → bad() 🔴
    ("🚨 NAV קריטי",
     dict(ok=True, is_critical=True, is_stale=True), "🔴", "NAV קריטי"),
]


class TestG4SingleGlyphAllFreshnessStates:
    def test_every_freshness_state_single_correct_non_disagreeing_glyph(self):
        for label, flags, expected_glyph, needle in _FRESHNESS_CASES:
            info = {"freshness_label": label, "nav": 7934.0, **flags}
            report = _health_with_nav(info)
            line = _nav_line(report, needle)
            glyphs = _leading_glyphs(line)
            # exactly ONE leading status glyph (no doubling) …
            assert len(glyphs) == 1, (
                f"{needle!r}: expected ONE glyph, got {glyphs} in {line!r}")
            # … and it is the CORRECT freshness-routed wrapper glyph …
            assert glyphs[0] == expected_glyph, (
                f"{needle!r}: expected {expected_glyph}, got {glyphs[0]}")
            # … strip the label's own leading glyph to get its pure TEXT …
            text_only = label
            for g in _STATUS_GLYPHS:
                if text_only.startswith(g):
                    text_only = text_only[len(g):].lstrip(" ")
                    break
            # … the label's own (possibly DISAGREEING) glyph is gone unless
            #     it happens to equal the authoritative wrapper glyph …
            label_glyph = label[:len(_leading_glyphs(label)[0])] \
                if _leading_glyphs(label) else ""
            if label_glyph and label_glyph != expected_glyph:
                assert label_glyph not in line, (
                    f"{needle!r}: disagreeing label glyph {label_glyph} "
                    f"survived in {line!r}")
            # … the label TEXT is preserved verbatim …
            assert text_only in line
            # … and no doubled / disagreeing pair survives anywhere on it.
            for a in _STATUS_GLYPHS:
                for b in _STATUS_GLYPHS:
                    assert f"{a} {b}" not in line, (
                        f"{needle!r}: doubled/disagreeing {a} {b} in {line!r}")

    def test_fresh_case_is_the_classic_doubled_green_now_single(self):
        report = _health_with_nav({
            "ok": True, "is_critical": False, "is_stale": False,
            "freshness_label": "✅ NAV $7,934 — עודכן לפני 0.1ש׳",
            "nav": 7934.0,
        })
        line = _nav_line(report, "עודכן לפני 0.1")
        assert "✅ ✅" not in line
        assert line.count("✅") == 1
        assert "✅ NAV $7,934 — עודכן לפני 0.1ש׳" in line

    def test_disagreeing_pair_never_renders(self):
        # The historically worst cases: 🔴+🟠, ⚠️+🟠, 🔴+🚨.
        for label, flags, _glyph, needle in _FRESHNESS_CASES:
            report = _health_with_nav(
                {"freshness_label": label, "nav": 7934.0, **flags})
            line = _nav_line(report, needle)
            for bad_pair in ("🔴 🟠", "⚠️ 🟠", "🔴 🚨", "🟡 ⚠️", "⚠️ 🟡"):
                assert bad_pair not in line

    def test_strip_helper_idempotent_and_safe_on_plain_text(self):
        # plain message (no leading glyph) is returned unchanged …
        assert bh._strip_leading_status_glyph("NAV plain") == "NAV plain"
        # … a leading glyph (+ space) is removed exactly once …
        assert bh._strip_leading_status_glyph("✅ NAV x") == "NAV x"
        assert bh._strip_leading_status_glyph("🟠 NAV y") == "NAV y"
        # … idempotent: stripping an already-stripped string is a no-op.
        once = bh._strip_leading_status_glyph("🚨 NAV z")
        assert bh._strip_leading_status_glyph(once) == once == "NAV z"

    def test_summary_counts_unaffected_by_g4(self):
        # The footer tally counts checks by their (wrapper) leading glyph;
        # G4 changes the message body only, never the wrapper glyph, so the
        # "X תקין | Y אזהרה | Z שגיאה" tally still parses correctly.
        report = _health_with_nav({
            "ok": True, "is_critical": True, "is_stale": True,
            "freshness_label": "🔴 NAV $1 — ישן 99ש׳ (לא עודכן!)",
            "nav": 1.0,
        })
        assert "תקין" in report and "אזהרה" in report and "שגיאה" in report
        # the critical NAV contributes to the 🔴 count, not a stray glyph
        assert "🔴 1 שגיאה" in report or "🔴 2 שגיאה" in report \
            or "🔴 3 שגיאה" in report  # supabase/audit may also be 🔴


# ════════════════════════════════════════════════════════════════════════════
# G5 — score-line window labels reflect the TRUE sample (no self-contradiction)
# ════════════════════════════════════════════════════════════════════════════
def _risk_rec(*, n9, n21, n50, with_m21=True):
    rr = {
        "ok": True,
        "heat_color": "🟠", "heat_label": "חם", "heat_score": 62.0,
        "s9_score": 70.0, "m21_score": 60.0, "l50_score": 55.0,
        "recent_10_wr": 60.0, "all_50_wr": 50.0,
        "s9_stats": {"n": n9}, "l50_stats": {"n": n50},
        "win_streak": 0, "loss_streak": 0, "heat_factors": [],
        "current_risk_pct": 0.60, "recommended_risk_pct": 0.60,
        "current_risk_usd": 45.0, "recommended_risk_usd": 45.0,
        "direction": "hold", "step_type": "ללא שינוי",
    }
    if with_m21:
        rr["m21_stats"] = {"n": n21}
    return rr


def _score_line(rr, s9w, m21w, l50w):
    """Reconstruct the exact score-line string with the given parentheticals."""
    return (f"{tf.RTL}  ▸ ציון (0-100) לפי טווח: "
            f"S9({s9w})=`{rr['s9_score']:.0f}` | "
            f"M21({m21w})=`{rr['m21_score']:.0f}` | "
            f"L50({l50w})=`{rr['l50_score']:.0f}`")


class TestG5ScoreLineTrueSampleReconciliation:
    def test_ge_50_byte_identical_to_pre_fix_literal(self):
        # ≥50 closed campaigns ⇒ true window Ns are EXACTLY the nominals
        # (9, 21, 50) ⇒ the score line is BYTE-IDENTICAL to today's literal
        # and W-A3 appends NO disclosure (zero math/KPI change).
        rr = _risk_rec(n9=9, n21=21, n50=50)
        out = tf.fmt_adaptive_risk_block(rr)
        pre_fix_literal = _score_line(rr, 9, 21, 50)
        assert pre_fix_literal in out                     # byte-identical
        assert "מדגם נוכחי:" not in out                   # no <50 caveat
        assert "מבוסס מדגם חלקי" not in out

    def test_ge_50_with_larger_book_still_caps_at_nominals(self):
        # A real book bigger than 50 still yields s9=9, m21=21, l50=50
        # (windows are disc_camps[:9]/[:21]/[:50]) ⇒ byte-identical.
        rr = _risk_rec(n9=9, n21=21, n50=50)  # _window_stats caps at window
        out = tf.fmt_adaptive_risk_block(rr)
        assert _score_line(rr, 9, 21, 50) in out
        assert "S9(50)" not in out and "L50(9)" not in out

    def test_lt_50_score_line_shows_true_n_no_self_contradiction(self):
        # Small book: 8 closed campaigns ⇒ ALL THREE windows hold 8. The
        # score line must read S9(8) M21(8) L50(8) — consistent with the
        # honest "מדגם נוכחי: 8/50" caveat W-A3 prints right below it. The
        # misleading "(50)"/"(21)"/"(9)" literal must be GONE.
        rr = _risk_rec(n9=8, n21=8, n50=8)
        out = tf.fmt_adaptive_risk_block(rr)
        assert _score_line(rr, 8, 8, 8) in out
        assert "מדגם נוכחי: 8/50" in out
        # No self-contradiction: the lying "(50)" / "(21)" no longer appears
        # in the score line while the caveat says 8/50.
        score_ln = next(ln for ln in out.split("\n")
                        if "ציון (0-100) לפי טווח" in ln)
        assert "L50(50)" not in score_ln
        assert "M21(21)" not in score_ln
        assert "S9(9)" not in score_ln
        assert "L50(8)" in score_ln

    def test_lt_50_partial_book_each_window_independent(self):
        # 25 closed campaigns ⇒ S9 holds 9, M21 holds 21, L50 holds 25
        # (each window independently min(window_size, book)). The line must
        # reflect each TRUE per-window N, and the L50 caveat reads 25/50.
        rr = _risk_rec(n9=9, n21=21, n50=25)
        out = tf.fmt_adaptive_risk_block(rr)
        assert _score_line(rr, 9, 21, 25) in out
        assert "מדגם נוכחי: 25/50" in out
        assert "L50(50)" not in out

    def test_legacy_riskrec_without_m21_stats_keeps_literal(self):
        # The W-A3 fixture (and other legacy/synthetic risk_recs) omit
        # m21_stats. With the true M21 N unknown the helper must NOT invent
        # one — it keeps today's nominal literal so no existing pin is
        # weakened (Mark 6.1). This is exactly what keeps
        # tests/test_phase_algo1_recon_and_sample.py green.
        rr = _risk_rec(n9=9, n21=0, n50=9, with_m21=False)
        out = tf.fmt_adaptive_risk_block(rr)
        # Unchanged nominal literal preserved (S9(9) M21(21) L50(50)).
        assert _score_line(rr, 9, 21, 50) in out
        # W-A3 still appends its honest caveat for the <50 true L50 sample.
        assert "מדגם נוכחי: 9/50" in out

    def test_helper_returns_nominals_when_a_window_stat_missing(self):
        # Unit-level: _score_line_window_labels falls back to (9,21,50)
        # unless ALL THREE window stats carry an int n.
        assert tf._score_line_window_labels({}) == (9, 21, 50)
        assert tf._score_line_window_labels(
            {"s9_stats": {"n": 3}, "l50_stats": {"n": 3}}) == (9, 21, 50)
        assert tf._score_line_window_labels({
            "s9_stats": {"n": 3}, "m21_stats": {"n": 3},
            "l50_stats": {"n": 3}}) == (3, 3, 3)
        assert tf._score_line_window_labels({
            "s9_stats": {"n": 9}, "m21_stats": {"n": 21},
            "l50_stats": {"n": 50}}) == (9, 21, 50)  # ≥50 ⇒ byte-identical

    def test_no_math_or_kpi_change(self):
        # G5 is presentation-only: the heat score and recommended risk %
        # are byte-identical between the <50 and ≥50 renders (only the
        # parenthetical sample labels + the honest caveat differ).
        small = tf.fmt_adaptive_risk_block(_risk_rec(n9=8, n21=8, n50=8))
        big   = tf.fmt_adaptive_risk_block(_risk_rec(n9=9, n21=21, n50=50))
        for kpi in ("ציון: `62/100`", "סיכון נוכחי: `0.60%`",
                    "סיכון מוצע: `0.60%`"):
            assert kpi in small and kpi in big
