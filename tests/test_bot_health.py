"""
Tests for bot_health.py — build_health_report().

14-check system health report — uses patch.object on the module's bound
names (supabase, ec, get_account_settings) to verify outcomes.
"""
import sys, os, json, types as py_types
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ── Stub heavy deps if not yet loaded ─────────────────────────────────────────
for mod in ["telebot", "supabase", "dotenv", "engine_core"]:
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()

if "bot_core" not in sys.modules:
    _bc = py_types.ModuleType("bot_core")
    _bc.bot        = MagicMock()
    _bc.supabase   = MagicMock()
    _bc.user_state = {}
    _bc.RTL        = "‏"
    _bc.TOKEN      = ""
    _bc.ADMIN_ID   = ""
    sys.modules["bot_core"] = _bc

import bot_health as bh


def _make_supabase(trades=None, raise_on_table=False):
    """Build a mock supabase client with chainable methods."""
    sb = MagicMock()
    if raise_on_table:
        sb.table.side_effect = Exception("connection fail")
        return sb

    trades = trades if trades is not None else []

    def _table(name):
        chain = MagicMock()
        chain.select.return_value = chain
        chain.order.return_value = chain
        chain.limit.return_value = chain
        chain.execute.return_value = MagicMock(data=trades)
        return chain
    sb.table.side_effect = _table
    return sb


def _run_report(*, supabase_mock=None, ec_fresh=None, cfg=None, env=None):
    """Run build_health_report with patched deps."""
    if supabase_mock is None:
        supabase_mock = _make_supabase([{"trade_date": "2025-05-12"}])

    ec_mock = MagicMock()
    ec_mock.get_nav_with_freshness.return_value = ec_fresh or {
        "ok": True, "is_critical": False, "is_stale": False,
        "freshness_label": "NAV fresh", "nav": 10000.0,
    }

    cfg = cfg or {"total_deposited": 10000.0, "risk_pct_input": 0.5}
    env_overrides = env or {}

    with patch.object(bh, 'supabase', supabase_mock), \
         patch.object(bh, 'ec', ec_mock), \
         patch.object(bh, 'get_account_settings', lambda: cfg), \
         patch.dict(os.environ, env_overrides, clear=False):
        return bh.build_health_report()


# ── Report shape ──────────────────────────────────────────────────────────────

class TestReportShape:
    def test_returns_string(self):
        result = _run_report()
        assert isinstance(result, str)

    def test_contains_header(self):
        result = _run_report()
        assert "Sentinel System Health" in result

    def test_contains_separator(self):
        result = _run_report()
        assert "─" in result

    def test_contains_check_counts(self):
        result = _run_report()
        assert "תקין" in result and "אזהרה" in result and "שגיאה" in result

    def test_has_check_lines(self):
        result = _run_report()
        # Each check produces 1 line; 4 header lines + 14 checks = 18 lines
        # (allow some flex since ALGO Positions may be skipped if df is empty)
        line_count = result.count("\n")
        assert line_count >= 14  # at least the 4 header + ~10 checks


# ── NAV freshness routing ─────────────────────────────────────────────────────

class TestNavFreshness:
    def test_nav_critical_shows_red(self):
        # Sprint-30 G4 (CORRECTED expectation — Mark 6.1, NOT weakened).
        # PRE-G4 this test asserted BOTH "🚨 NAV קריטי" AND "🔴" in result
        # — i.e. it codified the DOUBLED + DISAGREEING glyph line
        # "🔴 🚨 NAV קריטי" as correct (the label's own 🚨 plus the bad()
        # wrapper's 🔴, two different glyphs). The correct render is a
        # SINGLE authoritative status glyph. Now asserted strictly: exactly
        # one 🔴 on the NAV check line, the doubled/disagreeing forms gone,
        # the label TEXT preserved. Coverage strengthened, not weakened.
        result = _run_report(ec_fresh={
            "ok": True, "is_critical": True, "is_stale": True,
            "freshness_label": "🚨 NAV קריטי",
            "nav": 5000.0,
        })
        nav_line = next(ln for ln in result.split("\n") if "NAV קריטי" in ln)
        # SINGLE correct glyph (bad() → 🔴), label text preserved …
        assert "🔴 NAV קריטי" in nav_line
        # … and the doubled / disagreeing forms are GONE.
        assert "🔴 🚨" not in nav_line
        assert "🚨 NAV קריטי" not in nav_line   # label's own glyph stripped
        assert "🔴 🔴" not in nav_line
        assert nav_line.count("🔴") == 1
        assert "🚨" not in nav_line

    def test_nav_stale_shows_yellow(self):
        # Sprint-30 G4: stale ⇒ warn() ⇒ exactly ONE ⚠️ on the NAV line,
        # NEVER the doubled "⚠️ ⚠️". Strengthened from a bare substring
        # check to a single-glyph assertion (Mark 6.1 — not weakened).
        result = _run_report(ec_fresh={
            "ok": True, "is_critical": False, "is_stale": True,
            "freshness_label": "⚠️ NAV ישן",
            "nav": 5000.0,
        })
        nav_line = next(ln for ln in result.split("\n") if "NAV ישן" in ln)
        assert "⚠️ NAV ישן" in nav_line
        assert "⚠️ ⚠️" not in nav_line
        assert nav_line.count("⚠️") == 1

    def test_nav_stale_label_glyph_disagrees_single_correct(self):
        # Sprint-30 G4 (ADD): the engine's stale label carries 🟡
        # (engine_core.py:1615) while the bot_health stale route is warn()
        # → ⚠️. The two glyphs DISAGREE; pre-G4 this rendered "⚠️ 🟡 NAV …".
        # Post-G4 the label's 🟡 is stripped and exactly the wrapper's ⚠️
        # (the authoritative freshness-routed glyph) remains.
        result = _run_report(ec_fresh={
            "ok": True, "is_critical": False, "is_stale": True,
            "freshness_label": "🟡 NAV $5,000 — עודכן לפני 30ש׳",
            "nav": 5000.0,
        })
        nav_line = next(ln for ln in result.split("\n")
                        if "עודכן לפני 30" in ln)
        assert "⚠️ NAV $5,000 — עודכן לפני 30ש׳" in nav_line
        assert "⚠️ 🟡" not in nav_line
        assert "🟡" not in nav_line
        assert nav_line.count("⚠️") == 1

    def test_nav_fresh_no_doubled_green(self):
        # Sprint-30 G4 (ADD): the most common case — fresh broker NAV. The
        # engine label starts with ✅ (engine_core.py:1617) and ok() also
        # prefixes ✅; pre-G4 this rendered "✅ ✅ NAV …" on EVERY healthy
        # render. Post-G4: exactly one ✅, text preserved.
        result = _run_report(ec_fresh={
            "ok": True, "is_critical": False, "is_stale": False,
            "freshness_label": "✅ NAV $5,000 — עודכן לפני 0.1ש׳",
            "nav": 5000.0,
        })
        nav_line = next(ln for ln in result.split("\n")
                        if "עודכן לפני 0.1" in ln)
        assert "✅ NAV $5,000 — עודכן לפני 0.1ש׳" in nav_line
        assert "✅ ✅" not in nav_line
        assert nav_line.count("✅") == 1

    def test_nav_manual_no_timestamp_single_glyph(self):
        # Sprint-30 G4 (ADD): manual / no-timestamp NAV. Engine label
        # starts with 🟠 (engine_core.py:1634); core sets is_stale=True,
        # is_critical=False ⇒ bot_health route is warn() → ⚠️. Pre-G4:
        # the honesty-critical line rendered "⚠️ 🟠 NAV …" (disagreeing
        # double). Post-G4: single ⚠️, the honest "(הוגדר ידנית)" text
        # intact (the most honesty-sensitive line must NOT look glitched).
        result = _run_report(ec_fresh={
            "ok": True, "is_critical": False, "is_stale": True,
            "freshness_label": "🟠 NAV $5,000 — אין timestamp (הוגדר ידנית)",
            "nav": 5000.0,
        })
        nav_line = next(ln for ln in result.split("\n")
                        if "הוגדר ידנית" in ln)
        assert "⚠️ NAV $5,000 — אין timestamp (הוגדר ידנית)" in nav_line
        assert "⚠️ 🟠" not in nav_line
        assert "🟠" not in nav_line
        assert nav_line.count("⚠️") == 1

    def test_nav_fallback_config_missing_single_red(self):
        # Sprint-30 G4 (ADD): config missing ⇒ ok=False ⇒ bot_health
        # emits its OWN bad() message ("sentinel_config.json לא נמצא"),
        # not the engine label — verify that path still renders a single
        # 🔴 and never a doubled glyph regardless of label content.
        result = _run_report(ec_fresh={
            "ok": False, "is_critical": True, "is_stale": True,
            "freshness_label": "🔴 NAV: fallback — sentinel_config.json לא נמצא",
            "nav": 7500.0,
        })
        nav_line = next(ln for ln in result.split("\n")
                        if "sentinel_config.json" in ln)
        assert "🔴 NAV Config — sentinel_config.json לא נמצא" in nav_line
        assert "🔴 🔴" not in nav_line
        assert nav_line.count("🔴") == 1

    def test_nav_missing_shows_red(self):
        result = _run_report(ec_fresh={
            "ok": False, "is_critical": False, "is_stale": False,
            "freshness_label": "", "nav": 0,
        })
        assert "sentinel_config.json" in result


# ── Risk config bounds ────────────────────────────────────────────────────────

class TestRiskConfigBounds:
    def test_valid_risk_pct(self):
        result = _run_report(cfg={"total_deposited": 10000.0, "risk_pct_input": 0.5})
        assert "Risk Config" in result
        assert "0.50%" in result

    def test_out_of_range_risk_pct_warns(self):
        result = _run_report(cfg={"total_deposited": 10000.0, "risk_pct_input": 5.0})
        # 5.0 is outside 0.2–3.0 range → should show warning
        assert "מחוץ לטווח" in result


# ── Supabase error handling ───────────────────────────────────────────────────

class TestSupabaseError:
    def test_supabase_connection_error_logged(self):
        sb_err = _make_supabase(raise_on_table=True)
        result = _run_report(supabase_mock=sb_err)
        assert "Supabase" in result
        assert "🔴" in result or "שגיאת" in result

    def test_empty_trades_warns(self):
        sb_empty = _make_supabase(trades=[])
        result = _run_report(supabase_mock=sb_empty)
        assert "Supabase" in result


# ── Env variable checks ───────────────────────────────────────────────────────

class TestEnvChecks:
    def test_missing_admin_id_shows_red(self):
        # Save current env, then ensure TELEGRAM_ADMIN_ID is absent
        saved = os.environ.pop("TELEGRAM_ADMIN_ID", None)
        try:
            result = _run_report()
            assert "TELEGRAM_ADMIN_ID" in result or "Telegram Admin — חסר" in result
        finally:
            if saved is not None:
                os.environ["TELEGRAM_ADMIN_ID"] = saved

    def test_admin_id_present_shows_ok(self):
        result = _run_report(env={"TELEGRAM_ADMIN_ID": "12345"})
        assert "Telegram Admin" in result


# ── Audit log accessibility (Sprint 7 check #14) ──────────────────────────────

class TestAuditLogCheck:
    """
    Sprint 7 #4: check #14 surfaces missing migration 002 to the trader.
    audit_logger is fail-open by design, so without this check a missing
    audit_log table is silent — exactly the compliance gap Meeting 7 flagged.
    """

    def _make_sb_with_audit(self, audit_behaviour):
        """Build a supabase mock where the audit_log table behaves per kwarg.

        audit_behaviour:
          "ok"      → select.execute returns empty data
          "missing" → table().select() raises with 'does not exist'
          "other"   → table().select() raises with a generic message
        """
        sb = MagicMock()

        def _table(name):
            chain = MagicMock()
            chain.select.return_value = chain
            chain.order.return_value = chain
            chain.limit.return_value = chain
            if name == "audit_log":
                if audit_behaviour == "ok":
                    chain.execute.return_value = MagicMock(data=[])
                elif audit_behaviour == "missing":
                    chain.execute.side_effect = Exception(
                        'relation "audit_log" does not exist'
                    )
                else:  # other
                    chain.execute.side_effect = Exception("network down")
            else:
                chain.execute.return_value = MagicMock(
                    data=[{"trade_date": "2025-05-12"}]
                )
            return chain
        sb.table.side_effect = _table
        return sb

    def test_audit_log_accessible_shows_ok(self):
        result = _run_report(supabase_mock=self._make_sb_with_audit("ok"))
        assert "Audit Log — טבלה נגישה" in result
        # No bad/warning for audit log
        assert "Audit Log — טבלה חסרה" not in result

    def test_missing_table_shows_bad_with_migration_hint(self):
        result = _run_report(supabase_mock=self._make_sb_with_audit("missing"))
        assert "Audit Log — טבלה חסרה" in result
        # Operator must see how to fix it
        assert "002_audit_log.sql" in result

    def test_other_error_shows_warn_not_bad(self):
        """Non-schema errors (network blip, auth) get a softer warning,
        not the migration-missing red."""
        result = _run_report(supabase_mock=self._make_sb_with_audit("other"))
        assert "Audit Log — שגיאת גישה" in result
        # Hint must NOT appear for non-schema errors
        assert "002_audit_log.sql" not in result.split("Audit Log")[-1].split("\n")[0]


# ── RTL markers ───────────────────────────────────────────────────────────────

class TestRTLMarkers:
    def test_each_line_has_rtl_marker(self):
        result = _run_report()
        rtl = "‏"  # U+200F
        # At least most lines should have RTL marker
        non_empty = [ln for ln in result.split("\n") if ln.strip()]
        rtl_lines = [ln for ln in non_empty if rtl in ln]
        assert len(rtl_lines) >= len(non_empty) * 0.8


# ── Sprint-12 / Mark §4 — missing-stops data-hygiene NOTICE ────────────────────

class TestMissingStopsNotice:
    """Mark §4: surface missing stops ONLY as a non-numeric data-hygiene
    notice — never an action-item, never counted, no fabricated stop. The
    count+symbols are a factual hygiene readout Mark explicitly permits."""

    def _sb_with_missing(self):
        return _make_supabase([
            {"trade_date": "2025-01-01", "symbol": "MSGE",
             "side": "BUY", "stop_loss": 0, "quantity": 10,
             "campaign_id": "MSGE_1", "setup_type": "VCP"},
            {"trade_date": "2025-01-02", "symbol": "TSLA",
             "side": "BUY", "stop_loss": 0, "quantity": 5,
             "campaign_id": "TSLA_2", "setup_type": "VCP"},
        ])

    def test_notice_present_with_mark_verbatim_clause(self):
        result = _run_report(supabase_mock=self._sb_with_missing())
        # the legacy numeric warn still there
        assert "Missing Stops — 2 שורות" in result
        # Mark §4 VERBATIM non-task / non-counted clause appended
        assert "נתוני סיכון חסרים: 2 רשומות" in result
        assert "(אינו משימה, אינו נספר בסטטיסטיקה.)" in result
        assert "השלם entry/stop כדי שייכללו." in result

    def test_no_notice_when_no_missing_stops(self):
        sb = _make_supabase([
            {"trade_date": "2025-01-01", "symbol": "AAPL",
             "side": "BUY", "stop_loss": 95.0, "quantity": 10,
             "campaign_id": "AAPL_1", "setup_type": "VCP"},
        ])
        result = _run_report(supabase_mock=sb)
        assert "Missing Stops — אין" in result
        assert "אינו משימה, אינו נספר בסטטיסטיקה" not in result

    def test_notice_is_non_numeric_and_not_a_task(self):
        # No fabricated stop value, no R/$/urgency tier, no "task" word —
        # it is a notice, not an action-item (Mark §4).
        result = _run_report(supabase_mock=self._sb_with_missing())
        line = next(ln for ln in result.split("\n")
                    if "אינו משימה" in ln)
        assert "$" not in line
        assert "R" not in line.replace("RTL", "")
        assert "P0" not in line and "P1" not in line
