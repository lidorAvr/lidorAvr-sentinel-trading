"""
Engagement-phase Wave-B shippable surfaces (21/05/2026).

Tier-B pinning tests — one per surface per Mark+Research binding. Each
test prevents a specific regression flagged in MEETING_ENGAGEMENT_*
docs:

  B2 — C2-S1 sizing voice (Mark binding: voice-only, dedup byte-
       identical, §X6 self-data only)

Future B-tier items land their tests here:
  B3 — C4-S1 Gate Receipt
  B4 — C1-S1 backfill prompt
  B5 — EOD process-verdict
  B1 — C5-S1 Monday R-distribution
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123456:test-token")
os.environ.setdefault("TELEGRAM_ADMIN_ID", "12345")
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-key")


# ════════════════════════════════════════════════════════════════════════════
# B2 — C2-S1 voice-only sizing alert refactor
# ════════════════════════════════════════════════════════════════════════════

class TestB2SizingAlertVoice:
    """C2-S1 voice change — Mark §3 anti-list + §X6 self-data fence +
    Sprint-25 §A.3 dedup-byte-identical binding. The MATH is byte-
    identical (sizing_ratio formula at call site unchanged); only the
    COPY changes."""

    def setup_method(self):
        from risk_monitor import _sizing_leak_alert
        self._alert = _sizing_leak_alert

    def test_alert_uses_atzlecha_personal_register(self):
        """E3 headline insight: the *אצלך* register is the cultural
        unlock. The voice change must use it."""
        out = self._alert("MRVL", "Breakout", 0.41, 47.0, 19.0)
        assert "אצלך" in out

    def test_alert_uses_brother_voice_escape_hatch(self):
        """E3-#3 voice: brother-voice direct but with an explicit
        escape hatch ('או אל תיכנס'). This is the differentiator."""
        out = self._alert("MRVL", "Breakout", 0.41, 47.0, 19.0)
        assert "או אל תיכנס" in out

    def test_alert_does_not_contain_old_foreign_header(self):
        """Mark binding: voice change must REMOVE the foreign-language
        'Sizing Leak' header (E3 register: native Hebrew only)."""
        out = self._alert("MRVL", "Breakout", 0.41, 47.0, 19.0)
        assert "Sizing Leak" not in out

    def test_alert_does_not_use_passive_directive(self):
        """Mark §3 anti-list (Sprint-12) — no directive verbs telling
        the user what to do. 'לרשום כלקח לטרייד הבא' was a directive."""
        out = self._alert("MRVL", "Breakout", 0.41, 47.0, 19.0)
        assert "לרשום כלקח" not in out

    def test_alert_renders_sizing_math_correctly(self):
        """The math (ratio + target + actual) MUST be visible byte-
        accurate. Voice change does not touch the formulas."""
        out = self._alert("MRVL", "Breakout", 0.41, 47.0, 19.0)
        assert "0.41x" in out
        assert "$47" in out
        assert "$19" in out

    def test_alert_preserves_symbol_and_setup(self):
        out = self._alert("MRVL", "Breakout", 0.41, 47.0, 19.0)
        assert "MRVL" in out
        assert "Breakout" in out

    def test_alert_rtl_marker_at_line_starts(self):
        """RTL invariant from previous waves — each Hebrew line starts
        with U+200F."""
        out = self._alert("MRVL", "Breakout", 0.41, 47.0, 19.0)
        # At least the first line must carry RTL.
        first_line = out.split("\n", 1)[0]
        assert "‏" in first_line

    def test_alert_function_signature_preserved(self):
        """ARCH binding: signature unchanged so dedup at risk_monitor.
        py:1173-1174 stays byte-identical."""
        import inspect
        sig = inspect.signature(self._alert)
        params = list(sig.parameters)
        assert params == [
            "sym", "setup", "sizing_ratio", "target_risk_usd",
            "original_campaign_risk",
        ]


# ════════════════════════════════════════════════════════════════════════════
# B2 — dedup-key byte-identical (Mark binding)
# ════════════════════════════════════════════════════════════════════════════

class TestB2DedupKeyByteIdentical:
    """Mark binding (MEETING_ENGAGEMENT_MARK_RESEARCH_RULINGS §C2):
    'voice-change refactor MUST preserve the dedup key at :1168-1174
    byte-identically; new test asserts the campaign-id cooldown is
    unchanged.' Pin by static-analysis on risk_monitor.py — the line
    pattern that anti-spams the alert must survive any future
    refactor."""

    def _read(self, relative_path):
        path = os.path.join(os.path.dirname(__file__), "..", relative_path)
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def test_sizing_leak_alerted_flag_pattern_preserved(self):
        src = self._read("risk_monitor.py")
        # The flag is set on the per-position entry; the read at the
        # gate (sizing_leak_alerted=False default) must remain a one-
        # time-per-campaign anti-spam.
        assert 'new_pos_entry.get("sizing_leak_alerted", False)' in src
        assert 'new_pos_entry["sizing_leak_alerted"] = True' in src

    def test_post_raise_settle_suppression_preserved(self):
        # The 48h settle suppression on a risk RAISE is a separate Mark
        # binding (Sprint-25); the voice change must NOT touch it.
        src = self._read("risk_monitor.py")
        assert "_in_post_raise_settle" in src
        assert 'settle_state.get("dir") == "up"' in src

    def test_sizing_leak_threshold_constant_referenced(self):
        # Sprint-25 G6 — SIZING_LEAK_THRESHOLD constant is the single
        # source. A future regression that hard-codes the threshold
        # would re-open the SST drift class.
        src = self._read("risk_monitor.py")
        assert "SIZING_LEAK_THRESHOLD" in src
        assert "_sizing_ratio < SIZING_LEAK_THRESHOLD" in src

    def test_alert_does_not_introduce_market_commentary(self):
        """§X6 fence — the voice change must NOT introduce market-
        commentary lead (SPY/QQQ/regime/etc.). Self-data only."""
        from risk_monitor import _sizing_leak_alert
        out = _sizing_leak_alert("MRVL", "Breakout", 0.41, 47.0, 19.0)
        for forbidden in ("SPY", "QQQ", "השוק", "המגזר", "מתחרים"):
            assert forbidden not in out, (
                f"§X6 violation: voice change introduced market "
                f"commentary substring {forbidden!r}"
            )
