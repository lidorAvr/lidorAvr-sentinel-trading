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


# ════════════════════════════════════════════════════════════════════════════
# B3 — C4-S1 Gate Receipt (compute_gate_clamp_summary + fmt_gate_receipt)
# ════════════════════════════════════════════════════════════════════════════

class TestB3GateClampSummary:
    """Engine function: reads risk_recommendations.json, returns
    {n_days, total_clamps, by_gate, first_clamp_ts}. Mark §3 honesty:
    a missing log returns zero, never raises."""

    def setup_method(self):
        import json
        import tempfile
        import adaptive_risk_engine as are
        self._are = are
        self._json = json
        self._tmp_dir = tempfile.mkdtemp()
        import os as _os
        self._tmp_log = _os.path.join(self._tmp_dir, "test_rec.json")

    def teardown_method(self):
        import os as _os
        try:
            _os.unlink(self._tmp_log)
        except (FileNotFoundError, OSError):
            pass

    def _write_log(self, entries):
        with open(self._tmp_log, "w", encoding="utf-8") as f:
            self._json.dump(entries, f, ensure_ascii=False)

    def test_missing_log_returns_zero(self):
        import os as _os
        bogus = _os.path.join(self._tmp_dir, "does_not_exist.json")
        s = self._are.compute_gate_clamp_summary(n_days=90, log_path=bogus)
        assert s["total_clamps"] == 0
        assert s["by_gate"] == {}
        assert s["first_clamp_ts"] is None
        assert s["n_days"] == 90

    def test_corrupt_log_returns_zero(self):
        with open(self._tmp_log, "w", encoding="utf-8") as f:
            f.write("not valid json {{{")
        s = self._are.compute_gate_clamp_summary(n_days=90, log_path=self._tmp_log)
        assert s["total_clamps"] == 0

    def test_counts_only_clamps(self):
        from datetime import datetime, timedelta
        now = datetime.now()
        self._write_log([
            # Approved raise (allow_raise=True) → NOT a clamp.
            {"ts": (now - timedelta(days=1)).isoformat(),
             "gate_result": {"evaluated": True, "allow_raise": True,
                             "failed": [], "reason": ""}},
            # Clamp on G2.
            {"ts": (now - timedelta(days=2)).isoformat(),
             "gate_result": {"evaluated": True, "allow_raise": False,
                             "failed": ["G2_sample"], "reason": "מדגם קטן"}},
            # Clamp on G1.
            {"ts": (now - timedelta(days=3)).isoformat(),
             "gate_result": {"evaluated": True, "allow_raise": False,
                             "failed": ["G1_recon"], "reason": "נתונים"}},
            # No gate_result (pre-engagement entry) → ignored.
            {"ts": (now - timedelta(days=4)).isoformat()},
        ])
        s = self._are.compute_gate_clamp_summary(n_days=90, log_path=self._tmp_log)
        assert s["total_clamps"] == 2
        assert s["by_gate"] == {"G1_recon": 1, "G2_sample": 1}

    def test_filters_by_n_days_window(self):
        from datetime import datetime, timedelta
        now = datetime.now()
        self._write_log([
            # In-window.
            {"ts": (now - timedelta(days=10)).isoformat(),
             "gate_result": {"evaluated": True, "allow_raise": False,
                             "failed": ["G2_sample"]}},
            # Out-of-window (older than 90 days).
            {"ts": (now - timedelta(days=120)).isoformat(),
             "gate_result": {"evaluated": True, "allow_raise": False,
                             "failed": ["G1_recon"]}},
        ])
        s = self._are.compute_gate_clamp_summary(n_days=90, log_path=self._tmp_log)
        assert s["total_clamps"] == 1
        assert "G1_recon" not in s["by_gate"]

    def test_first_clamp_ts_is_oldest_in_window(self):
        from datetime import datetime, timedelta
        now = datetime.now()
        ts_old = (now - timedelta(days=5)).isoformat()
        ts_recent = (now - timedelta(days=1)).isoformat()
        self._write_log([
            {"ts": ts_recent,
             "gate_result": {"evaluated": True, "allow_raise": False,
                             "failed": ["G2_sample"]}},
            {"ts": ts_old,
             "gate_result": {"evaluated": True, "allow_raise": False,
                             "failed": ["G1_recon"]}},
        ])
        s = self._are.compute_gate_clamp_summary(n_days=90, log_path=self._tmp_log)
        assert s["first_clamp_ts"] is not None
        assert s["first_clamp_ts"].startswith(ts_old[:10])

    def test_zero_clamps_first_ts_is_none(self):
        self._write_log([])
        s = self._are.compute_gate_clamp_summary(n_days=90, log_path=self._tmp_log)
        assert s["first_clamp_ts"] is None

    def test_n_days_round_trips(self):
        self._write_log([])
        s = self._are.compute_gate_clamp_summary(n_days=30, log_path=self._tmp_log)
        assert s["n_days"] == 30


class TestB3GateReceiptFormatter:
    """Mark §C4 binding: count-only Phase-1, no celebration vocabulary.
    Zero clamps → empty string (§X5 silence-as-surface). Non-zero →
    fact-stating Hebrew line + per-gate breakdown."""

    def setup_method(self):
        from telegram_formatters import fmt_gate_receipt
        self._fmt = fmt_gate_receipt

    def test_zero_clamps_returns_empty(self):
        # §X5: silence-as-surface. Tone-deaf "great work, no clamps"
        # banned at the formatter layer.
        out = self._fmt({"n_days": 90, "total_clamps": 0,
                          "by_gate": {}, "first_clamp_ts": None})
        assert out == ""

    def test_non_zero_clamps_render_with_count(self):
        out = self._fmt({"n_days": 90, "total_clamps": 7,
                          "by_gate": {"G2_sample": 4, "G1_recon": 3},
                          "first_clamp_ts": "2026-02-21T16:30:00"})
        assert "קבלה מהשער" in out
        assert "`7`" in out
        assert "`90`" in out

    def test_per_gate_breakdown_in_canonical_order(self):
        out = self._fmt({
            "n_days": 90, "total_clamps": 10,
            "by_gate": {"G4_drawdown": 1, "G2_sample": 5,
                        "G1_recon": 3, "G3_expectancy": 1},
            "first_clamp_ts": None,
        })
        # Stable G1 → G2 → G3 → G4 ordering.
        i1 = out.index("G1")
        i2 = out.index("G2")
        i3 = out.index("G3")
        i4 = out.index("G4")
        assert i1 < i2 < i3 < i4

    def test_no_celebration_vocabulary(self):
        # Mark §C4 R1: "saved you", "great", "excellent", "כל הכבוד"
        # all banned. The receipt is a record, not applause.
        out = self._fmt({"n_days": 90, "total_clamps": 7,
                          "by_gate": {"G2_sample": 7}, "first_clamp_ts": None})
        for forbidden in ("saved you", "great", "excellent",
                          "כל הכבוד", "כל הכבוד!", "מצוין"):
            assert forbidden.lower() not in out.lower(), (
                f"§C4 R1 violation: celebration substring {forbidden!r}"
            )

    def test_no_market_commentary(self):
        # §X6 fence.
        out = self._fmt({"n_days": 90, "total_clamps": 7,
                          "by_gate": {"G2_sample": 7}, "first_clamp_ts": None})
        for forbidden in ("SPY", "QQQ", "השוק", "המגזר"):
            assert forbidden not in out

    def test_unknown_gate_id_renders_with_id_as_label(self):
        # Defensive: a future gate G5 / typo gate name should not crash
        # — render the raw id and land at the end of the ordering.
        out = self._fmt({"n_days": 90, "total_clamps": 2,
                          "by_gate": {"G2_sample": 1, "G99_future": 1},
                          "first_clamp_ts": None})
        assert "G99_future" in out
        # Known gate label still resolves.
        assert "G2 גודל מדגם" in out


class TestB3HandlerEmptyState:
    """Honest empty-state on /gate_receipt: when there are no in-window
    clamps, emit an HONEST 'no clamps' line — NEVER a celebration."""

    def test_handler_module_imports(self):
        # Smoke: the engagement handler module is wired in.
        import telegram_engagement
        assert hasattr(telegram_engagement, "handle_gate_receipt")

    def test_telegram_bot_registers_gate_receipt_command(self):
        import os as _os
        path = _os.path.join(_os.path.dirname(__file__), "..", "telegram_bot.py")
        with open(path, "r", encoding="utf-8") as f:
            src = f.read()
        assert "/gate_receipt" in src
        assert "handle_gate_receipt(" in src


# ════════════════════════════════════════════════════════════════════════════
# B4 — C1-S1 backfill prompt (find_backfill_candidate + apply + skip)
# ════════════════════════════════════════════════════════════════════════════

class TestB4BackfillCandidate:
    """Engine: find_backfill_candidate — Mark §C1 binding (min 14
    days old + max 180 days + skip already-backfilled / skipped)."""

    def setup_method(self):
        import json
        import tempfile
        import adaptive_risk_engine as are
        self._are = are
        self._json = json
        self._tmp_dir = tempfile.mkdtemp()
        import os as _os
        self._tmp_journal = _os.path.join(self._tmp_dir, "test_journal.json")

    def teardown_method(self):
        import os as _os
        try:
            _os.unlink(self._tmp_journal)
        except (FileNotFoundError, OSError):
            pass

    def _write(self, entries):
        with open(self._tmp_journal, "w", encoding="utf-8") as f:
            self._json.dump(entries, f, ensure_ascii=False)

    def test_missing_journal_returns_empty(self):
        import os as _os
        bogus = _os.path.join(self._tmp_dir, "missing.json")
        c = self._are.find_backfill_candidate(journal_path=bogus)
        assert c == {}

    def test_corrupt_journal_returns_empty(self):
        with open(self._tmp_journal, "w", encoding="utf-8") as f:
            f.write("{ not json")
        c = self._are.find_backfill_candidate(journal_path=self._tmp_journal)
        assert c == {}

    def test_only_rejected_entries_are_candidates(self):
        from datetime import datetime, timedelta
        old = (datetime.now() - timedelta(days=20)).isoformat()
        self._write([
            # Confirmed entry — not a candidate.
            {"ts": old, "action": "confirmed", "reason": ""},
        ])
        c = self._are.find_backfill_candidate(journal_path=self._tmp_journal)
        assert c == {}

    def test_already_has_reason_not_a_candidate(self):
        from datetime import datetime, timedelta
        old = (datetime.now() - timedelta(days=20)).isoformat()
        self._write([
            {"ts": old, "action": "rejected",
             "reason": "מדגם קטן מדי", "recommended_risk_pct": 0.85},
        ])
        c = self._are.find_backfill_candidate(journal_path=self._tmp_journal)
        assert c == {}

    def test_too_fresh_not_a_candidate(self):
        from datetime import datetime, timedelta
        fresh = (datetime.now() - timedelta(days=7)).isoformat()
        self._write([
            {"ts": fresh, "action": "rejected", "reason": "",
             "recommended_risk_pct": 0.85},
        ])
        c = self._are.find_backfill_candidate(
            min_age_days=14, journal_path=self._tmp_journal,
        )
        assert c == {}

    def test_too_old_not_a_candidate(self):
        from datetime import datetime, timedelta
        ancient = (datetime.now() - timedelta(days=200)).isoformat()
        self._write([
            {"ts": ancient, "action": "rejected", "reason": "",
             "recommended_risk_pct": 0.85},
        ])
        c = self._are.find_backfill_candidate(
            max_age_days=180, journal_path=self._tmp_journal,
        )
        assert c == {}

    def test_oldest_in_window_wins(self):
        from datetime import datetime, timedelta
        # Both in window; oldest must be returned.
        a = (datetime.now() - timedelta(days=20)).isoformat()
        b = (datetime.now() - timedelta(days=40)).isoformat()
        self._write([
            {"ts": a, "action": "rejected", "reason": "",
             "recommended_risk_pct": 0.85},
            {"ts": b, "action": "rejected", "reason": "",
             "recommended_risk_pct": 0.85},
        ])
        c = self._are.find_backfill_candidate(
            min_age_days=14, max_age_days=180,
            journal_path=self._tmp_journal,
        )
        assert c["ts"] == b

    def test_already_skipped_not_a_candidate(self):
        from datetime import datetime, timedelta
        old = (datetime.now() - timedelta(days=20)).isoformat()
        self._write([
            {"ts": old, "action": "rejected", "reason": "",
             "backfill_skipped": True,
             "recommended_risk_pct": 0.85},
        ])
        c = self._are.find_backfill_candidate(
            min_age_days=14, journal_path=self._tmp_journal,
        )
        assert c == {}


class TestB4ApplyBackfillReason:
    """apply_backfill_reason: writes the §X4 verbatim reason back to
    the matching journal entry. Returns False on miss / I/O error;
    never raises."""

    def setup_method(self):
        import json
        import tempfile
        import adaptive_risk_engine as are
        self._are = are
        self._json = json
        self._tmp_dir = tempfile.mkdtemp()
        import os as _os
        self._tmp_journal = _os.path.join(self._tmp_dir, "test_journal.json")

    def teardown_method(self):
        import os as _os
        try:
            _os.unlink(self._tmp_journal)
        except (FileNotFoundError, OSError):
            pass

    def _write(self, entries):
        with open(self._tmp_journal, "w", encoding="utf-8") as f:
            self._json.dump(entries, f, ensure_ascii=False)

    def _read(self):
        with open(self._tmp_journal, "r", encoding="utf-8") as f:
            return self._json.load(f)

    def test_apply_writes_verbatim_reason(self):
        # §X4 binding: bytes-on-disk identity is the foundation of the
        # day-60 Callback's mirror function.
        verbatim = "*חזק* `chop` [bear] _hesitation_"
        self._write([{"ts": "2026-05-01T10:00:00",
                      "action": "rejected", "reason": ""}])
        ok = self._are.apply_backfill_reason(
            "2026-05-01T10:00:00", verbatim,
            journal_path=self._tmp_journal,
        )
        assert ok is True
        log = self._read()
        assert log[0]["reason"] == verbatim
        assert "backfill_filled_ts" in log[0]

    def test_apply_misses_unknown_ts(self):
        self._write([{"ts": "2026-05-01T10:00:00",
                      "action": "rejected", "reason": ""}])
        ok = self._are.apply_backfill_reason(
            "1999-01-01T00:00:00", "any reason",
            journal_path=self._tmp_journal,
        )
        assert ok is False

    def test_apply_rejects_empty_reason(self):
        self._write([{"ts": "2026-05-01T10:00:00",
                      "action": "rejected", "reason": ""}])
        ok = self._are.apply_backfill_reason(
            "2026-05-01T10:00:00", "   ",
            journal_path=self._tmp_journal,
        )
        assert ok is False

    def test_apply_missing_journal_returns_false(self):
        import os as _os
        bogus = _os.path.join(self._tmp_dir, "missing.json")
        ok = self._are.apply_backfill_reason(
            "any-ts", "reason", journal_path=bogus,
        )
        assert ok is False


class TestB4MarkBackfillSkipped:
    """mark_backfill_skipped sets backfill_skipped=True; no reason
    fabricated. Honest §3 semantics."""

    def setup_method(self):
        import json
        import tempfile
        import adaptive_risk_engine as are
        self._are = are
        self._json = json
        self._tmp_dir = tempfile.mkdtemp()
        import os as _os
        self._tmp_journal = _os.path.join(self._tmp_dir, "test_journal.json")

    def teardown_method(self):
        import os as _os
        try:
            _os.unlink(self._tmp_journal)
        except (FileNotFoundError, OSError):
            pass

    def test_mark_sets_skipped_flag(self):
        with open(self._tmp_journal, "w", encoding="utf-8") as f:
            import json as _j
            _j.dump([{"ts": "2026-05-01T10:00:00",
                      "action": "rejected", "reason": ""}], f)
        ok = self._are.mark_backfill_skipped(
            "2026-05-01T10:00:00", journal_path=self._tmp_journal,
        )
        assert ok is True
        with open(self._tmp_journal, "r", encoding="utf-8") as f:
            import json as _j
            log = _j.load(f)
        assert log[0]["backfill_skipped"] is True
        assert log[0]["reason"] == ""  # NOT fabricated

    def test_mark_misses_unknown_ts(self):
        with open(self._tmp_journal, "w", encoding="utf-8") as f:
            import json as _j
            _j.dump([{"ts": "2026-05-01T10:00:00",
                      "action": "rejected", "reason": ""}], f)
        ok = self._are.mark_backfill_skipped(
            "1999-01-01T00:00:00", journal_path=self._tmp_journal,
        )
        assert ok is False


class TestB4BackfillPromptFormatter:
    """fmt_backfill_prompt — Mark §3 anti-list (invitation not
    directive); §X4 prep (anchor verbatim); §X5 silence on empty."""

    def setup_method(self):
        from telegram_formatters import fmt_backfill_prompt
        self._fmt = fmt_backfill_prompt

    def test_empty_candidate_returns_empty(self):
        # §X5 silence: no candidate → no surface.
        assert self._fmt({}) == ""

    def test_renders_recommended_pct(self):
        out = self._fmt({
            "ts": "2026-04-15T14:00:00",
            "action": "rejected",
            "recommended_risk_pct": 0.85,
            "direction": "up",
        })
        assert "0.85" in out

    def test_renders_date_not_just_iso(self):
        # Founder-readable date (D/M/YYYY), never raw ISO.
        out = self._fmt({
            "ts": "2026-04-15T14:00:00",
            "action": "rejected",
            "recommended_risk_pct": 0.85,
            "direction": "up",
        })
        assert "15/04/2026" in out
        assert "2026-04-15T14:00:00" not in out

    def test_no_directive_verbs(self):
        # Mark §3 anti-list — invitation, not command.
        out = self._fmt({
            "ts": "2026-04-15T14:00:00",
            "action": "rejected",
            "recommended_risk_pct": 0.85,
            "direction": "up",
        })
        for forbidden in ("חובה", "אסור", "תכתוב!", "מה אתה חושב!",
                          "אתה חייב"):
            assert forbidden not in out, (
                f"§3 anti-list violation: directive substring {forbidden!r}"
            )

    def test_no_market_commentary(self):
        # §X6 fence.
        out = self._fmt({
            "ts": "2026-04-15T14:00:00",
            "action": "rejected",
            "recommended_risk_pct": 0.85,
            "direction": "up",
        })
        for forbidden in ("SPY", "QQQ", "השוק", "המגזר"):
            assert forbidden not in out


class TestB4HandlerWiring:
    """Static-analysis pins for the bot wiring of B4."""

    def _read(self, relative_path):
        import os as _os
        path = _os.path.join(_os.path.dirname(__file__), "..", relative_path)
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def test_telegram_engagement_exposes_b4_handlers(self):
        import telegram_engagement
        assert hasattr(telegram_engagement, "handle_backfill_prompt")
        assert hasattr(telegram_engagement, "handle_backfill_add")
        assert hasattr(telegram_engagement, "handle_backfill_skip")
        assert hasattr(telegram_engagement, "handle_backfill_collect_reason")

    def test_telegram_bot_registers_backfill_command(self):
        src = self._read("telegram_bot.py")
        assert "/backfill_prompt" in src
        assert "handle_backfill_prompt(" in src

    def test_telegram_bot_dispatches_collect_reason_state(self):
        src = self._read("telegram_bot.py")
        assert '"backfill_collect_reason"' in src
        assert "handle_backfill_collect_reason(" in src

    def test_telegram_callbacks_dispatches_add_and_skip(self):
        src = self._read("telegram_callbacks.py")
        assert "backfill_add|" in src
        assert "backfill_skip|" in src


# ════════════════════════════════════════════════════════════════════════════
# B5 — EOD verdict (compute_todays_R_summary + fmt_eod_verdict + handler)
# ════════════════════════════════════════════════════════════════════════════

class TestB5TodaysRSummary:
    """compute_todays_R_summary — IL-calendar-day boundary; only
    today's trades counted; no fabricated R for zero-risk campaigns."""

    def setup_method(self):
        from datetime import datetime
        try:
            from zoneinfo import ZoneInfo
            self._tz = ZoneInfo("Asia/Jerusalem")
        except Exception:
            self._tz = None
        import adaptive_risk_engine as are
        self._are = are
        # Anchor "now" deterministically for tests.
        if self._tz:
            self._now = datetime(2026, 5, 21, 22, 30, 0, tzinfo=self._tz)
        else:
            self._now = datetime(2026, 5, 21, 22, 30, 0)

    def _campaign(self, close_dt, pnl, risk):
        # close_date in the engine is usually pandas.Timestamp but the
        # function tolerates plain datetime.
        return {
            "campaign_id": "test",
            "symbol": "TEST",
            "total_pnl_usd": pnl,
            "original_campaign_risk": risk,
            "close_date": close_dt,
        }

    def test_no_campaigns_zero(self):
        s = self._are.compute_todays_R_summary([], now=self._now)
        assert s["n_trades"] == 0
        assert s["total_R"] == 0.0

    def test_only_todays_count(self):
        from datetime import timedelta
        today_morning = self._now.replace(hour=10, minute=0)
        yesterday = self._now - timedelta(days=1)
        s = self._are.compute_todays_R_summary([
            self._campaign(today_morning, pnl=100.0, risk=50.0),
            self._campaign(yesterday,     pnl=200.0, risk=50.0),
        ], now=self._now)
        assert s["n_trades"] == 1
        assert s["total_R"] == 2.0

    def test_zero_risk_does_not_fabricate_R(self):
        # Mark §3 binding: a campaign with risk=0 cannot produce an R.
        # It counts in n_trades (it was a closed trade today) but
        # contributes 0 to total_R — NEVER invent an R via div-by-eps.
        s = self._are.compute_todays_R_summary([
            self._campaign(self._now, pnl=100.0, risk=0.0),
        ], now=self._now)
        assert s["n_trades"] == 1
        assert s["total_R"] == 0.0

    def test_negative_R_is_negative(self):
        s = self._are.compute_todays_R_summary([
            self._campaign(self._now, pnl=-150.0, risk=50.0),
        ], now=self._now)
        assert s["total_R"] == -3.0

    def test_mixed_day_sums_correctly(self):
        s = self._are.compute_todays_R_summary([
            self._campaign(self._now, pnl=+100.0, risk=50.0),  # +2R
            self._campaign(self._now, pnl=-50.0,  risk=50.0),  # -1R
            self._campaign(self._now, pnl=+25.0,  risk=50.0),  # +0.5R
        ], now=self._now)
        assert s["n_trades"] == 3
        assert s["total_R"] == 1.5

    def test_returned_today_start_is_il_midnight(self):
        s = self._are.compute_todays_R_summary([], now=self._now)
        assert "2026-05-21T00:00:00" in s["today_start_iso"]


class TestB5EodVerdictFormatter:
    """fmt_eod_verdict — Mark §3 honest empty, §X5 respectful framing
    for -2R / settle, no celebration, §X6 fence."""

    def setup_method(self):
        from telegram_formatters import fmt_eod_verdict
        self._fmt = fmt_eod_verdict

    def test_empty_day_honest(self):
        out = self._fmt({"n_trades": 0, "total_R": 0.0,
                          "today_start_iso": "2026-05-21T00:00:00"})
        assert "לא נסגרו עסקאות" in out
        # No fabrication / spin.
        for forbidden in ("יום מנוחה", "סבלנות", "שקט יקר"):
            assert forbidden not in out

    def test_normal_day_includes_R_and_count(self):
        sup = {"suppress": False, "rule_id": "NONE", "reason": ""}
        out = self._fmt({"n_trades": 3, "total_R": 1.5,
                          "today_start_iso": "..."}, sup)
        assert "+1.50R" in out
        assert "3" in out
        assert "מחר" in out

    def test_two_r_down_day_respectful_no_coaching(self):
        # §X5 + E4: -2R day gets "הספר רושם, שקט עד מחר ב-16:00"
        # NEVER "tomorrow is new" / "you can make it back".
        sup = {"suppress": True, "rule_id": "TWO_R_DOWN",
               "reason": "-2R day floor"}
        out = self._fmt({"n_trades": 2, "total_R": -2.5,
                          "today_start_iso": "..."}, sup)
        assert "-2.50R" in out
        assert "הספר רושם" in out
        assert "שקט" in out
        # No coaching verbs.
        for forbidden in ("מחר זה יום חדש", "אתה יכול להחזיר",
                          "תחשוב", "השב את ההפסד"):
            assert forbidden not in out

    def test_settle_period_framing(self):
        sup = {"suppress": True, "rule_id": "SETTLE",
               "reason": "Settle-period active"}
        out = self._fmt({"n_trades": 1, "total_R": 0.5,
                          "today_start_iso": "..."}, sup)
        assert "בתקופת התבססות" in out
        assert "+0.50R" in out

    def test_no_celebration_on_positive_day(self):
        # Even on a green day, no celebration vocabulary (§C4 R1
        # precedent applies — we report fact, not applaud).
        sup = {"suppress": False, "rule_id": "NONE", "reason": ""}
        out = self._fmt({"n_trades": 5, "total_R": 4.2,
                          "today_start_iso": "..."}, sup)
        for forbidden in ("יום מצוין", "כל הכבוד", "מהמם",
                          "great day", "let's go"):
            assert forbidden.lower() not in out.lower()

    def test_no_market_commentary(self):
        sup = {"suppress": False, "rule_id": "NONE", "reason": ""}
        out = self._fmt({"n_trades": 3, "total_R": 1.5,
                          "today_start_iso": "..."}, sup)
        # §X6 fence.
        for forbidden in ("SPY", "QQQ", "השוק היה", "המגזר"):
            assert forbidden not in out

    def test_singular_vs_plural_trade_word(self):
        sup = {"suppress": False, "rule_id": "NONE", "reason": ""}
        # 1 trade.
        out_one = self._fmt({"n_trades": 1, "total_R": 1.0,
                              "today_start_iso": "..."}, sup)
        assert "1 עסקה" in out_one
        # 3 trades.
        out_many = self._fmt({"n_trades": 3, "total_R": 1.5,
                               "today_start_iso": "..."}, sup)
        assert "3 עסקאות" in out_many


class TestB5HandlerWiring:
    def _read(self, relative_path):
        import os as _os
        path = _os.path.join(_os.path.dirname(__file__), "..", relative_path)
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def test_telegram_engagement_exposes_handler(self):
        import telegram_engagement
        assert hasattr(telegram_engagement, "handle_eod_check")

    def test_telegram_bot_registers_eod_check_command(self):
        src = self._read("telegram_bot.py")
        assert "/eod_check" in src
        assert "handle_eod_check(" in src


# ════════════════════════════════════════════════════════════════════════════
# B1 — C5-S1 Monday R-distribution opener
# ════════════════════════════════════════════════════════════════════════════

class TestB1WeeklyRSummary:
    """compute_weekly_R_summary — window-filtered + sample-honesty +
    zero-risk preservation."""

    def setup_method(self):
        from datetime import datetime
        try:
            from zoneinfo import ZoneInfo
            self._tz = ZoneInfo("Asia/Jerusalem")
        except Exception:
            self._tz = None
        import adaptive_risk_engine as are
        self._are = are
        if self._tz:
            self._now = datetime(2026, 5, 25, 14, 0, 0, tzinfo=self._tz)
        else:
            self._now = datetime(2026, 5, 25, 14, 0, 0)

    def _c(self, close_dt, pnl, risk):
        return {
            "campaign_id": "test",
            "symbol": "TEST",
            "total_pnl_usd": pnl,
            "original_campaign_risk": risk,
            "close_date": close_dt,
        }

    def test_empty_window_returns_zero(self):
        s = self._are.compute_weekly_R_summary([], window_days=7,
                                                now=self._now)
        assert s["n_trades"] == 0
        assert s["total_R"] == 0.0
        assert s["best_R"] is None
        assert s["worst_R"] is None
        assert s["sample_too_small"] is True

    def test_in_window_aggregates(self):
        from datetime import timedelta
        days_back = [1, 3, 5]
        camps = [self._c(self._now - timedelta(days=d), pnl=100.0, risk=50.0)
                 for d in days_back]
        s = self._are.compute_weekly_R_summary(camps, window_days=7,
                                                now=self._now)
        assert s["n_trades"] == 3
        assert s["total_R"] == 6.0  # 3 * 2R
        assert s["best_R"] == 2.0
        assert s["worst_R"] == 2.0

    def test_excludes_out_of_window(self):
        from datetime import timedelta
        camps = [
            self._c(self._now - timedelta(days=2),  pnl=100.0, risk=50.0),
            self._c(self._now - timedelta(days=10), pnl=200.0, risk=50.0),  # out
        ]
        s = self._are.compute_weekly_R_summary(camps, window_days=7,
                                                now=self._now)
        assert s["n_trades"] == 1
        assert s["total_R"] == 2.0

    def test_sample_too_small_below_5(self):
        # Mark §3 sample-honesty: n<5 must surface as too-small.
        from datetime import timedelta
        camps = [self._c(self._now - timedelta(days=d), pnl=100.0, risk=50.0)
                 for d in (1, 2, 3)]
        s = self._are.compute_weekly_R_summary(camps, window_days=7,
                                                now=self._now)
        assert s["sample_too_small"] is True
        assert s["min_sample_for_wr"] == 5

    def test_sample_ok_at_5(self):
        from datetime import timedelta
        camps = [self._c(self._now - timedelta(days=d), pnl=100.0, risk=50.0)
                 for d in (1, 2, 3, 4, 5)]
        s = self._are.compute_weekly_R_summary(camps, window_days=7,
                                                now=self._now)
        assert s["sample_too_small"] is False
        assert s["n_trades"] == 5

    def test_zero_risk_counts_in_n_not_R(self):
        # Mark §3: a zero-risk campaign counts as a trade but contributes
        # 0 to R — never fabricate via div-by-eps.
        camps = [self._c(self._now, pnl=100.0, risk=0.0)]
        s = self._are.compute_weekly_R_summary(camps, window_days=7,
                                                now=self._now)
        assert s["n_trades"] == 1
        assert s["total_R"] == 0.0
        assert s["best_R"] is None  # no R was computable
        assert s["worst_R"] is None

    def test_wins_count_uses_pnl_not_R(self):
        # is_win is positive pnl even if risk is 0 (it WAS a winning
        # campaign).
        from datetime import timedelta
        camps = [
            self._c(self._now,                       pnl=+50.0, risk=0.0),
            self._c(self._now - timedelta(days=1),   pnl=-30.0, risk=15.0),
        ]
        s = self._are.compute_weekly_R_summary(camps, window_days=7,
                                                now=self._now)
        assert s["wins"] == 1


class TestB1WeeklyOpenerFormatter:
    """fmt_weekly_R_opener — Mark §C5 specificity gate + §3 sample-
    honesty + §X6 fence."""

    def setup_method(self):
        from telegram_formatters import fmt_weekly_R_opener
        self._fmt = fmt_weekly_R_opener

    def test_empty_window_returns_empty_string(self):
        # Mark §C5 specificity gate: no trades → MUTE (no "שבוע טוב!"
        # filler).
        out = self._fmt({"window_days": 7, "n_trades": 0,
                          "total_R": 0.0, "best_R": None,
                          "worst_R": None, "wins": 0,
                          "sample_too_small": True,
                          "min_sample_for_wr": 5})
        assert out == ""

    def test_small_sample_says_so(self):
        # Mark §3: never compute a WR off 3 trades.
        out = self._fmt({"window_days": 7, "n_trades": 3,
                          "total_R": 2.5, "best_R": 1.5,
                          "worst_R": -0.5, "wins": 2,
                          "sample_too_small": True,
                          "min_sample_for_wr": 5})
        assert "מדגם קטן מדי" in out
        assert "Win-rate" not in out  # WR suppressed

    def test_full_sample_renders_wr(self):
        out = self._fmt({"window_days": 7, "n_trades": 10,
                          "total_R": 4.0, "best_R": 2.0,
                          "worst_R": -1.0, "wins": 7,
                          "sample_too_small": False,
                          "min_sample_for_wr": 5})
        assert "Win-rate" in out
        assert "7/10" in out
        assert "70.0%" in out

    def test_renders_best_and_worst_R(self):
        out = self._fmt({"window_days": 7, "n_trades": 10,
                          "total_R": 4.0, "best_R": 2.0,
                          "worst_R": -1.0, "wins": 7,
                          "sample_too_small": False,
                          "min_sample_for_wr": 5})
        assert "+2.00R" in out
        assert "-1.00R" in out

    def test_uses_atzlecha_register(self):
        # E3 binding: the opener uses the personal "אצלך" register.
        out = self._fmt({"window_days": 7, "n_trades": 10,
                          "total_R": 4.0, "best_R": 2.0,
                          "worst_R": -1.0, "wins": 7,
                          "sample_too_small": False,
                          "min_sample_for_wr": 5})
        assert "אצלך" in out

    def test_no_market_commentary(self):
        # §X6 fence — C5 has the HIGHEST temptation to drift here.
        out = self._fmt({"window_days": 7, "n_trades": 10,
                          "total_R": 4.0, "best_R": 2.0,
                          "worst_R": -1.0, "wins": 7,
                          "sample_too_small": False,
                          "min_sample_for_wr": 5})
        for forbidden in ("SPY", "QQQ", "השוק", "המגזר", "S&P", "Nasdaq"):
            assert forbidden not in out, (
                f"§X6 violation: opener leaked market commentary "
                f"substring {forbidden!r}"
            )

    def test_no_celebration_vocabulary(self):
        # §C4 R1 precedent: even a +4R week is fact-stated, not applauded.
        out = self._fmt({"window_days": 7, "n_trades": 10,
                          "total_R": 4.0, "best_R": 2.0,
                          "worst_R": -1.0, "wins": 7,
                          "sample_too_small": False,
                          "min_sample_for_wr": 5})
        for forbidden in ("מהמם", "כל הכבוד", "שבוע מצוין",
                          "let's go", "amazing"):
            assert forbidden.lower() not in out.lower()

    def test_singular_vs_plural_trade_word(self):
        out_one = self._fmt({"window_days": 7, "n_trades": 1,
                              "total_R": 1.0, "best_R": 1.0,
                              "worst_R": 1.0, "wins": 1,
                              "sample_too_small": True,
                              "min_sample_for_wr": 5})
        assert "1 עסקה" in out_one


class TestB1HandlerWiring:
    def _read(self, relative_path):
        import os as _os
        path = _os.path.join(_os.path.dirname(__file__), "..", relative_path)
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def test_telegram_engagement_exposes_handler(self):
        import telegram_engagement
        assert hasattr(telegram_engagement, "handle_weekly_opener")

    def test_telegram_bot_registers_weekly_opener_command(self):
        src = self._read("telegram_bot.py")
        assert "/weekly_opener" in src
        assert "handle_weekly_opener(" in src
