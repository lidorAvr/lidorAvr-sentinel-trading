"""
Engagement-phase Wave-A foundation tests (21/05/2026).

Pins for the additive infrastructure landed in Wave-3A:
  - A4 audit constants — ACTION_RISK_REJECT + ACTION_CALLBACK_FIRED
  - A6 render_journal_text — Markdown-escape helper (S-ENGAGE-1 closure)
  - A2 U4 closure — telegram_audit_review surfaces both new constants
       with §X4 verbatim semantics
  - A3 _log_recommendation extension — gate_result + nav_at_eval
       captured for C4 Gate Receipt + Phase-2 D11

Each pin maps to a binding Mark/§X clause from MEETING_ENGAGEMENT_
MARK_RESEARCH_RULINGS.md; a future drift that touches one of these
surfaces will fail loudly here before the founder sees the regression.
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# bot_core requires these env vars on import. Same pattern as
# tests/test_audit_review.py.
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123456:test-token")
os.environ.setdefault("TELEGRAM_ADMIN_ID", "12345")
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-key")

import audit_logger  # noqa: E402
import telegram_audit_review  # noqa: E402
from telegram_formatters import render_journal_text  # noqa: E402


# ════════════════════════════════════════════════════════════════════════════
# A4 — Audit constants
# ════════════════════════════════════════════════════════════════════════════

class TestAuditConstantsRegistered:
    def test_action_risk_reject_constant(self):
        assert hasattr(audit_logger, "ACTION_RISK_REJECT")
        assert audit_logger.ACTION_RISK_REJECT == "risk_reject"

    def test_action_callback_fired_constant(self):
        assert hasattr(audit_logger, "ACTION_CALLBACK_FIRED")
        assert audit_logger.ACTION_CALLBACK_FIRED == "callback_fired"

    def test_constants_are_distinct_from_risk_pct_change(self):
        # ACTION_RISK_REJECT must be a DISTINCT value, not aliased to
        # ACTION_RISK_PCT_CHANGE. The whole point of U4 closure is that
        # /myactions renders the dismissal with the reason rather than
        # the misleading same-pct line.
        assert audit_logger.ACTION_RISK_REJECT != audit_logger.ACTION_RISK_PCT_CHANGE
        assert audit_logger.ACTION_CALLBACK_FIRED != audit_logger.ACTION_RISK_PCT_CHANGE
        assert audit_logger.ACTION_RISK_REJECT != audit_logger.ACTION_CALLBACK_FIRED


# ════════════════════════════════════════════════════════════════════════════
# A6 — render_journal_text (S-ENGAGE-1 / §X4 render-boundary)
# ════════════════════════════════════════════════════════════════════════════

class TestRenderJournalTextEscape:
    """The helper escapes 5 Telegram-Markdown legacy specials: _ * ` [ ].
    §X4 honors STORAGE-verbatim; this helper lives at the RENDER boundary
    only. Bytes on disk stay the same; the escape is applied right before
    `bot.send_message(..., parse_mode="Markdown")`."""

    def test_empty_and_none_roundtrip(self):
        assert render_journal_text("") == ""
        assert render_journal_text(None) == ""

    def test_no_specials_passes_through(self):
        plain = "מדגם קטן מדי בסביבת chop"
        assert render_journal_text(plain) == plain

    def test_underscore_escaped(self):
        assert render_journal_text("a_b") == r"a\_b"

    def test_asterisk_escaped(self):
        assert render_journal_text("3*4") == r"3\*4"

    def test_backtick_escaped(self):
        assert render_journal_text("var = `x`") == r"var = \`x\`"

    def test_brackets_escaped(self):
        assert render_journal_text("see [link]") == r"see \[link\]"

    def test_multiple_specials_in_one_string(self):
        src = "_a_ *b* `c` [d]"
        out = render_journal_text(src)
        # Each special preceded by exactly one backslash.
        for ch in ("_", "*", "`", "[", "]"):
            # The raw special must not appear without a preceding backslash.
            unescaped_positions = [
                i for i, c in enumerate(out)
                if c == ch and (i == 0 or out[i - 1] != "\\")
            ]
            assert unescaped_positions == [], (
                f"unescaped {ch!r} at positions {unescaped_positions} in {out!r}"
            )

    def test_idempotency(self):
        # Applying the escape twice yields the same output as once. This
        # is the safety net for a future caller that accidentally double-
        # invokes the helper.
        src = "a_b *c* `d` [e]"
        once = render_journal_text(src)
        twice = render_journal_text(once)
        assert once == twice

    def test_hebrew_with_specials(self):
        src = "סיבה: *לא* מתאים — `chop`"
        out = render_journal_text(src)
        assert r"\*לא\*" in out
        assert r"\`chop\`" in out

    def test_rtl_marker_preserved(self):
        # Hebrew RTL marker (U+200F) MUST round-trip unchanged — it is not
        # a Markdown special.
        src = "‏סיבה לא ידועה"
        assert render_journal_text(src) == src

    def test_emoji_preserved(self):
        src = "✅ מאוזן — אבל ‎_זהירות_"
        out = render_journal_text(src)
        # ✅ untouched; underscores escaped.
        assert "✅" in out
        assert r"\_זהירות\_" in out

    def test_backslash_then_special_preserved(self):
        # If the source ALREADY contains a backslash-escaped special, the
        # helper must leave it alone (idempotency on a pre-escaped input).
        src = r"a\_b"
        assert render_journal_text(src) == r"a\_b"


# ════════════════════════════════════════════════════════════════════════════
# A2 — U4 closure: telegram_audit_review surfaces the new constants
# ════════════════════════════════════════════════════════════════════════════

class TestAuditReviewSurfaceCoversNewConstants:
    def test_action_risk_reject_in_surface_list(self):
        assert audit_logger.ACTION_RISK_REJECT in telegram_audit_review._SURFACE_ACTIONS

    def test_action_callback_fired_in_surface_list(self):
        assert audit_logger.ACTION_CALLBACK_FIRED in telegram_audit_review._SURFACE_ACTIONS

    def test_friendly_line_for_rejection_with_reason(self):
        row = {
            "action": audit_logger.ACTION_RISK_REJECT,
            "metadata": {
                "recommended_pct": 0.85,
                "direction": "up",
                "reason": "מדגם קטן מדי בסביבת chop",
                "nav": 7857.0,
            },
            "before_state": {"risk_pct": 0.60},
            "after_state":  {"risk_pct": 0.60},
        }
        line = telegram_audit_review._friendly_line(row)
        # Hebrew label + recommended pct + verbatim reason (§X4 at render).
        assert "דחיית המלצת סיכון" in line
        assert "0.85" in line
        assert "מדגם קטן מדי בסביבת chop" in line

    def test_friendly_line_for_null_reason_uses_literal_marker(self):
        """Mark §X1 + §3 honesty: a missing reason is NEVER fabricated.
        It surfaces with the literal absence-marker — the 19/05 friction
        signal that triggered the engagement phase."""
        row = {
            "action": audit_logger.ACTION_RISK_REJECT,
            "metadata": {
                "recommended_pct": 0.85,
                "direction": "up",
                "reason": "",
                "nav": 7857.0,
            },
            "before_state": {"risk_pct": 0.60},
            "after_state":  {"risk_pct": 0.60},
        }
        line = telegram_audit_review._friendly_line(row)
        assert "(ללא הסבר)" in line
        # No invented reason text.
        assert "אינטואיציה" not in line

    def test_friendly_line_for_callback_fired_quotes_verbatim(self):
        """§X4 binding: the Callback surface quotes the verbatim text."""
        verbatim = "מדגם קטן מדי בסביבת chop"
        row = {
            "action": audit_logger.ACTION_CALLBACK_FIRED,
            "metadata": {
                "anchor_date": "04/04",
                "anchor_journal_id": "abc-123",
                "surface_id": "C1-S2",
                "quoted_text": verbatim,
            },
        }
        line = telegram_audit_review._friendly_line(row)
        assert "הספר הזכיר" in line
        assert "04/04" in line
        assert verbatim in line

    def test_friendly_line_callback_truncates_long_quote(self):
        long_quote = "א" * 200
        row = {
            "action": audit_logger.ACTION_CALLBACK_FIRED,
            "metadata": {
                "anchor_date": "04/04",
                "quoted_text": long_quote,
            },
        }
        line = telegram_audit_review._friendly_line(row)
        # Truncated, with the "…" marker. Never silently drop the marker
        # (that would be fallback-as-truth — claiming the quote is short
        # when it is not).
        assert "…" in line
        # First 50 chars survive.
        assert "א" * 50 in line


# ════════════════════════════════════════════════════════════════════════════
# A3 — _log_recommendation extension: gate_result + nav_at_eval
# ════════════════════════════════════════════════════════════════════════════

class TestRecommendationLoggingExtended:
    """ENGINE F2 closure: _log_recommendation now captures the full
    risk_raise_gate dict + nav_at_eval so C4 "Gate Receipt" can later
    count refusals + Phase-2 D11 can compute the dollar-value saved."""

    def setup_method(self):
        import adaptive_risk_engine as are
        self._are = are
        self._tmp_dir = tempfile.mkdtemp()
        self._tmp_log = os.path.join(self._tmp_dir, "risk_recommendations.json")
        self._orig_log_file = are.RECOMMENDATIONS_LOG_FILE
        are.RECOMMENDATIONS_LOG_FILE = self._tmp_log

    def teardown_method(self):
        self._are.RECOMMENDATIONS_LOG_FILE = self._orig_log_file
        try:
            os.unlink(self._tmp_log)
        except (FileNotFoundError, OSError):
            pass

    def _read_log(self):
        with open(self._tmp_log, "r", encoding="utf-8") as f:
            return json.load(f)

    def test_gate_result_persisted_when_present(self):
        rec = {
            "generated_at": "2026-05-21T16:30:00",
            "heat_score": 99,
            "direction": "hold",
            "current_risk_pct": 0.60,
            "recommended_risk_pct": 0.60,
            "recommended_risk_usd": 47,
            "risk_raise_gate": {
                "evaluated": True,
                "allow_raise": False,
                "failed": ["G2_sample"],
                "reason": "שער 2 — מדגם לא מספיק",
            },
        }
        self._are._log_recommendation(rec)
        entry = self._read_log()[0]
        assert "gate_result" in entry
        assert entry["gate_result"]["evaluated"] is True
        assert entry["gate_result"]["allow_raise"] is False
        assert entry["gate_result"]["failed"] == ["G2_sample"]
        assert "שער 2" in entry["gate_result"]["reason"]

    def test_gate_result_omitted_when_no_gate(self):
        # Backwards-compat: pre-engagement recs (no gate eval) must not
        # carry a stub gate_result key.
        rec = {
            "generated_at": "2026-05-21T16:30:00",
            "heat_score": 50,
            "direction": "hold",
            "current_risk_pct": 0.60,
            "recommended_risk_pct": 0.60,
            "recommended_risk_usd": 47,
        }
        self._are._log_recommendation(rec)
        entry = self._read_log()[0]
        assert "gate_result" not in entry

    def test_nav_at_eval_computed_from_pct_and_usd(self):
        # ENGINE F2: nav back-computed as recommended_risk_usd / (pct/100)
        # so Phase-2 D11 can compute dollar-value-saved without storing
        # NAV redundantly.
        rec = {
            "generated_at": "2026-05-21T16:30:00",
            "heat_score": 100,
            "direction": "hold",
            "current_risk_pct": 0.60,
            "recommended_risk_pct": 0.85,
            "recommended_risk_usd": 66,
        }
        self._are._log_recommendation(rec)
        entry = self._read_log()[0]
        # 66 / (0.85 / 100) = 7764.71
        assert entry["nav_at_eval"] is not None
        assert abs(entry["nav_at_eval"] - 7764.71) < 0.05

    def test_nav_at_eval_zero_pct_safe(self):
        # Division-by-zero safety: a 0% pct must NOT raise.
        rec = {
            "generated_at": "2026-05-21T16:30:00",
            "heat_score": 0,
            "direction": "hold",
            "current_risk_pct": 0.00,
            "recommended_risk_pct": 0.00,
            "recommended_risk_usd": 0,
        }
        # Must not raise.
        self._are._log_recommendation(rec)
        entry = self._read_log()[0]
        assert "nav_at_eval" not in entry or entry["nav_at_eval"] is None

    def test_existing_fields_unchanged(self):
        # Byte-compat: the 7 pre-engagement keys still surface identically.
        rec = {
            "generated_at": "2026-05-21T16:30:00",
            "heat_score": 100,
            "direction": "hold",
            "current_risk_pct": 0.60,
            "recommended_risk_pct": 0.60,
            "recommended_risk_usd": 47,
        }
        self._are._log_recommendation(rec)
        entry = self._read_log()[0]
        for key in ("ts", "heat_score", "direction", "current_risk_pct",
                    "recommended_risk_pct", "followed", "reason"):
            assert key in entry, f"missing key {key!r}"
        assert entry["followed"] is None
        assert entry["reason"] is None


# ════════════════════════════════════════════════════════════════════════════
# §X4 storage-verbatim — the bytes on disk are NEVER mutated by the render
# ════════════════════════════════════════════════════════════════════════════

class TestX4StorageVerbatim:
    """§X4 verbatim is enforced at the STORAGE layer. The render-escape
    in render_journal_text changes ONLY what goes out to Telegram — the
    stored bytes in risk_journal.json / audit_log must round-trip
    character-for-character so the day-60 Callback can recover the
    EXACT original phrasing."""

    def test_round_trip_with_specials_in_json(self):
        # Operator-typed reason carrying every Markdown special.
        verbatim = "*חזק* `chop` [bear] _hesitation_"
        # Storage shape: emulate risk_journal.json round-trip.
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump([{"reason": verbatim}], f, ensure_ascii=False)
            path = f.name
        try:
            with open(path, "r", encoding="utf-8") as f:
                back = json.load(f)
            assert back[0]["reason"] == verbatim
        finally:
            os.unlink(path)

    def test_render_does_not_mutate_stored_bytes(self):
        """The escape MUST be applied to a COPY, never the source. Caller
        contract: render_journal_text returns a NEW string; the original
        is untouched."""
        original = "a_b *c*"
        rendered = render_journal_text(original)
        # Original unchanged.
        assert original == "a_b *c*"
        # Rendered escaped.
        assert rendered != original
        assert rendered == r"a\_b \*c\*"


# ════════════════════════════════════════════════════════════════════════════
# A1 — U1 closure: risk_monitor delegates to fmt_adaptive_risk_block
# ════════════════════════════════════════════════════════════════════════════

class TestRiskMonitorRoutesThroughFormatter:
    """UX U1 P1 closure: risk_monitor's push alert MUST delegate to the
    same fmt_adaptive_risk_block used by /portfolio (the pull surface).
    Pin by static-analysis so a future inline-rebuilder regression
    surfaces in CI before the founder sees the 14-line shape again."""

    def _read(self, relative_path):
        path = os.path.join(os.path.dirname(__file__), "..", relative_path)
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def test_risk_monitor_imports_formatter(self):
        src = self._read("risk_monitor.py")
        # Must import the formatter under the `tf` alias (same as other
        # call sites). A future drift back to inline-builder MUST first
        # remove this import — and the next pin will fail loudly.
        assert "import telegram_formatters as tf" in src

    def test_risk_monitor_calls_fmt_adaptive_risk_block(self):
        src = self._read("risk_monitor.py")
        # The exact callsite — `tf.fmt_adaptive_risk_block(`. Catches a
        # regression to `risk_monitor`-local re-implementation.
        assert "tf.fmt_adaptive_risk_block(" in src

    def test_risk_monitor_does_not_contain_inline_14_line_shape(self):
        """The yesterday's UX U1 finding said the 14-line inline shape
        would recur on any direction-change rec. After U1 closure, the
        signature inline phrases that ONLY existed in the inline builder
        must be GONE — they live now only inside the formatter."""
        src = self._read("risk_monitor.py")
        # Signature substrings that lived in the old inline builder only.
        forbidden_substrings = [
            "*התראת סיכון אדפטיבי*",     # alert-specific header
            "📊 גורמים מרכזיים:",        # inline factors heading
            "🔼 לשיפור:",                 # inline improve heading
        ]
        for needle in forbidden_substrings:
            assert needle not in src, (
                f"UX U1 regression: inline builder reintroduced phrase "
                f"{needle!r} — route through fmt_adaptive_risk_block instead."
            )

    def test_risk_monitor_keyboard_prompt_preserved(self):
        # The alert-specific prompt (the keyboard ask) MUST stay in
        # risk_monitor — the formatter does not emit it.
        src = self._read("risk_monitor.py")
        assert "האם לאשר שינוי סיכון?" in src
