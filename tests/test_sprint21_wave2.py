"""Sprint-21 Wave-2 — WS-A (read-only probe) + WS-B (NULL-campaign_id honest
disclosure) test suite.

Gates: docs/teams/MARK_SPRINT21_RULINGS.md 14-item checklist (items 1,3-9,11,
12), docs/teams/SPRINT21_DESIGN.md §4. WS-C is NO-OP (deferred) — covered by
the byte-identical guard here + the unmodified
tests/test_real_data_april_regression.py.
"""
import ast
import os
from datetime import datetime

import pandas as pd
import pytest

import analytics_engine as ae
import report_renderer as rr
import report_open_book as rob
import period_data_probe as probe

_ACCT = {"nav": 100000.0, "risk_pct_input": 1.0}
_PROBE_SRC = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                          "period_data_probe.py")


def _r(tid, sym, d, side, qty, px, pnl, istop, setup, cid):
    return dict(trade_id=tid, symbol=sym, trade_date=d, side=side,
                quantity=qty, price=px, pnl_usd=pnl, initial_stop=istop,
                stop_loss=istop, setup_type=setup, campaign_id=cid)


def _mixed_df():
    """countable + DATA_INCOMPLETE + ALGO + NULL/blank-cid, all in-window."""
    rows = [
        # countable VCP campaign (valid stop)
        _r('1', 'AAA', '2026-04-05', 'BUY', 10, 100.0, 0.0, 90.0, 'VCP', 'C1'),
        _r('2', 'AAA', '2026-04-20', 'SELL', -10, 110.0, 100.0, 0, 'VCP', 'C1'),
        # DATA_INCOMPLETE (invalid stop -1)
        _r('3', 'BBB', '2026-04-06', 'BUY', 5, 50.0, 0.0, -1, 'EP', 'C2'),
        _r('4', 'BBB', '2026-04-21', 'SELL', -5, 55.0, 25.0, 0, 'EP', 'C2'),
        # ALGO
        _r('5', 'CCC', '2026-04-07', 'BUY', 3, 200.0, 0.0, -1, 'ALGO', 'C3'),
        _r('6', 'CCC', '2026-04-22', 'SELL', -3, 190.0, -30.0, -1, 'ALGO', 'C3'),
        # NULL campaign_id SELL in-window (the silent drop)
        _r('7', 'DDD', '2026-04-15', 'SELL', -4, 25.0, 13.71, 0, 'EP', None),
        # blank campaign_id SELL in-window
        _r('8', 'EEE', '2026-04-16', 'SELL', -2, 30.0, -5.0, 0, 'EP', ''),
        # NULL campaign_id BUY in-window (open-book silent drop)
        _r('9', 'FFF', '2026-04-17', 'BUY', 6, 40.0, 0.0, 38.0, 'EP', None),
    ]
    return pd.DataFrame(rows)


def _clean_df():
    """No NULL/blank-cid rows — unlinked must be 0 (no disclosure)."""
    return pd.DataFrame([
        _r('1', 'AAA', '2026-04-05', 'BUY', 10, 100.0, 0.0, 90.0, 'VCP', 'C1'),
        _r('2', 'AAA', '2026-04-20', 'SELL', -10, 110.0, 100.0, 0, 'VCP', 'C1'),
    ])


_PS = datetime(2026, 4, 1)
_PE = datetime(2026, 4, 30, 23, 59, 59)


# ── WS-A: read-only AST proof (RULINGS item 3 / §A1) ────────────────────────

_FORBIDDEN_METHODS = {"save", "insert", "update", "upsert", "delete",
                      "snap_save", "_mark_ran", "_save_state"}
_SUPABASE_ALLOWED = {"table", "select", "gte", "lte", "eq", "order",
                     "execute", "limit"}


class TestWSAReadOnlyAST:
    def _tree(self):
        with open(_PROBE_SRC, "r", encoding="utf-8") as fh:
            return ast.parse(fh.read(), filename=_PROBE_SRC)

    def test_no_forbidden_write_method_calls(self):
        tree = self._tree()
        bad = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func,
                                                         ast.Attribute):
                if node.func.attr in _FORBIDDEN_METHODS:
                    bad.append(node.func.attr)
        assert not bad, f"WS-A probe must not write: {bad}"

    def test_no_env_assignment_no_file_open_write(self):
        tree = self._tree()
        for node in ast.walk(tree):
            # os.environ[...] = ...
            if isinstance(node, ast.Assign):
                for tgt in node.targets:
                    if isinstance(tgt, ast.Subscript):
                        src = ast.unparse(tgt)
                        assert "environ" not in src, "no os.environ[..] ="
            # open(..., 'w'/'a'/'x') write
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                    and node.func.id == "open":
                for a in node.args[1:]:
                    if isinstance(a, ast.Constant) and isinstance(a.value,
                                                                  str):
                        assert not any(c in a.value for c in ("w", "a", "x")), \
                            "WS-A probe must not open files for write"

    def test_no_runondemand_or_render_path(self):
        tree = self._tree()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func,
                                                         ast.Attribute):
                assert node.func.attr not in (
                    "run_on_demand", "deliver_report", "render_weekly",
                    "render_monthly"), f"WS-A must not call {node.func.attr}"

    def test_supabase_builder_method_allowlist(self):
        """No write-verb builder methods anywhere in the probe's own code."""
        tree = self._tree()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func,
                                                         ast.Attribute):
                attr = node.func.attr
                if attr in ("insert", "update", "upsert", "delete"):
                    pytest.fail(f"forbidden Supabase write verb: {attr}")


# ── WS-A: spy proof — no snapshot/state mutation (RULINGS item 3) ───────────

class TestWSASpyNoMutation:
    def test_probe_invokes_no_snapshot_or_state_writer(self, monkeypatch):
        import report_snapshot_store as rss
        import report_scheduler as sched

        called = []
        monkeypatch.setattr(rss, "save",
                             lambda *a, **k: called.append("rss.save"))
        if hasattr(sched, "_save_state"):
            monkeypatch.setattr(sched, "_save_state",
                                lambda *a, **k: called.append("_save_state"))
        if hasattr(sched, "_mark_ran"):
            monkeypatch.setattr(sched, "_mark_ran",
                                lambda *a, **k: called.append("_mark_ran"))

        # _fetch_trades_df is the ONLY read; stub it to a fixture (no network).
        monkeypatch.setattr(sched, "_fetch_trades_df",
                            lambda s, e: _mixed_df())
        out = probe.build_probe_report(now=datetime(2026, 5, 16, 12))
        assert isinstance(out, str) and out
        assert called == [], f"probe mutated state: {called}"


# ── WS-A: no-secret (RULINGS item 4 / §A3) ──────────────────────────────────

class TestWSANoSecret:
    def test_output_contains_no_secret_values(self, monkeypatch):
        import report_scheduler as sched
        fake_url = "https://supersecret-project.supabase.co"
        fake_key = ("eyJhbGciOiJIUzI1NiJ9."
                    "eyJyb2xlIjoic2VydmljZV9yb2xlIn0."
                    "ZmFrZXNpZ25hdHVyZQ")
        fake_tok = "1234567890:ABCDEF_secret_telegram_token_value"
        monkeypatch.setenv("SUPABASE_URL", fake_url)
        monkeypatch.setenv("SUPABASE_KEY", fake_key)
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", fake_tok)
        monkeypatch.setattr(sched, "_fetch_trades_df",
                            lambda s, e: _mixed_df())
        out = probe.build_probe_report(now=datetime(2026, 5, 16, 12))
        assert fake_url not in out
        assert fake_key not in out
        assert fake_tok not in out
        assert "eyJ" not in out          # no JWT substring leaked
        assert "supabase.co" not in out
        # The ONLY auth disclosure permitted = the role word.
        assert "service_role" in out     # parsed from the fake JWT locally

    def test_unknown_role_renders_honest_token(self, monkeypatch):
        import report_scheduler as sched
        monkeypatch.setenv("SUPABASE_KEY", "not-a-jwt")
        monkeypatch.setattr(sched, "_fetch_trades_df",
                            lambda s, e: _mixed_df())
        out = probe.build_probe_report(now=datetime(2026, 5, 16, 12))
        assert "לא ודאית" in out
        assert "not-a-jwt" not in out


# ── WS-A: honest empty/fail branch (RULINGS item 6 / §A1/§A2) ───────────────

class TestWSAHonestEmpty:
    def test_none_fetch_says_input_empty_not_zero_closes(self, monkeypatch):
        import report_scheduler as sched
        monkeypatch.setattr(sched, "_fetch_trades_df", lambda s, e: None)
        out = probe.build_probe_report(now=datetime(2026, 5, 16, 12))
        assert 'input ריק/כשל' in out
        assert "זהו פער האספקה" in out
        assert 'לא מוצג כ-"0 סגירות"' in out
        # never a fabricated breakdown
        assert "— פירוט קמפיין —" not in out

    def test_empty_df_same_honest_branch(self, monkeypatch):
        import report_scheduler as sched
        monkeypatch.setattr(sched, "_fetch_trades_df",
                            lambda s, e: pd.DataFrame())
        out = probe.build_probe_report(now=datetime(2026, 5, 16, 12))
        assert out.count('input ריק/כשל') == 2   # both windows

    def test_nonempty_fetch_shows_real_breakdown(self, monkeypatch):
        import report_scheduler as sched
        monkeypatch.setattr(sched, "_fetch_trades_df",
                            lambda s, e: _mixed_df())
        out = probe.build_probe_report("weekly",
                                       now=datetime(2026, 5, 16, 12))
        assert 'input ריק/כשל' not in out
        assert "🔬 בדיקת אספקת נתונים (קריאה בלבד)" in out
        assert "ללא campaign_id בחלון:" in out


# ── WS-A: probe-vs-engine parity + WS-C founder guidance string ─────────────

class TestWSAParityAndWSCGuidance:
    def test_probe_closed_count_matches_engine(self, monkeypatch):
        import report_scheduler as sched
        df = _mixed_df()
        monkeypatch.setattr(sched, "_fetch_trades_df", lambda s, e: df)
        # engine: window is the on-demand monthly window; compute it the
        # same way the probe does, then compare closed campaign count.
        import report_on_demand as rod
        now = datetime(2026, 5, 16, 12)   # monthly window → April 1–30
        ref = rod.last_complete_monthly_ref(now)
        ps, pe = sched._monthly_period(ref)
        # The probe reports the FULL pipeline closed count (RULINGS §A2:
        # "exactly what _get_closed_campaigns + _aggregate_campaigns
        # produce" — countable + excluded), NOT the countable-only KPI.
        closed = ae._get_closed_campaigns(df.copy().assign(
            trade_date=pd.to_datetime(df["trade_date"])), ps, pe)
        agg = ae._aggregate_campaigns(closed, 0.0)
        n_pipeline = len(agg)              # C1 + C2 + C3 = 3
        eng = ae.compute_period_analytics(df, ps, pe, _ACCT)
        assert eng["campaigns_closed"] == 1            # countable-only KPI
        assert n_pipeline == 3                          # pipeline closed total
        out = probe.build_probe_report("monthly", now=now)
        assert (f"קמפיינים שנסגרו (לפי הצינור האמיתי): "
                f"{n_pipeline}") in out
        # per-campaign נספר flags reconcile to the countable KPI
        assert out.count("נספר=כן") == eng["campaigns_closed"]

    def test_wsc_guidance_string_on_invalid_stop(self, monkeypatch):
        import report_scheduler as sched
        # C2 (BBB) has initial_stop=-1 → invalid → DATA_INCOMPLETE excluded.
        monkeypatch.setattr(sched, "_fetch_trades_df",
                            lambda s, e: _mixed_df())
        out = probe.build_probe_report("monthly",
                                       now=datetime(2026, 5, 16, 12))
        assert "⚠️ stop לא תקין (initial_stop" in out
        assert "תקן entry/stop כדי להיכלל בסטטיסטיקה" in out


# ── WS-A: admin-gate enforced (RULINGS item 5 / §A4) ────────────────────────

class TestWSAAdminGate:
    def test_menu_button_present_only_in_developer_menu(self):
        """Source-based (robust to other tests MagicMock-ing telebot): the
        probe button is added EXACTLY ONCE, inside get_developer_menu(), and
        never in get_main_menu()."""
        src = open(os.path.join(os.path.dirname(_PROBE_SRC),
                                "telegram_menus.py"), encoding="utf-8").read()
        assert src.count("🔬 בדיקת נתוני תקופה (Probe)") == 1
        dev_i = src.index("def get_developer_menu")
        main_i = src.index("def get_main_menu")
        # next def after get_developer_menu bounds its body
        after = src.index("\ndef ", dev_i + 1)
        dev_body = src[dev_i:after]
        main_after = src.index("\ndef ", main_i + 1)
        main_body = src[main_i:main_after]
        assert "🔬 בדיקת נתוני תקופה (Probe)" in dev_body
        assert "🔬 בדיקת נתוני תקופה (Probe)" not in main_body

    def test_handler_branch_after_health_and_uses_existing_gate(self):
        src = open(os.path.join(os.path.dirname(_PROBE_SRC),
                                "telegram_bot.py"), encoding="utf-8").read()
        # exactly one additive handler branch
        assert src.count('if text == "🔬 בדיקת נתוני תקופה (Probe)":') == 1
        # placed AFTER the health handler (same dev-menu region).
        i_health = src.index('if text == "🏥 בריאות מערכת":')
        i_probe = src.index('if text == "🔬 בדיקת נתוני תקופה (Probe)":')
        # Sprint-25 C1 (Security S-1/S-2/S-3) UPDATED the dev-PIN gate from
        # the OLD single fail-OPEN expression
        # `dev_pin_is_configured() and not dev_pin_session_active(chat_id)`
        # (which this test previously asserted verbatim) to a fail-CLOSED
        # form: an unconfigured DEV_PIN now DENIES the menu, and EVERY
        # privileged dev handler re-asserts the session via the shared
        # `_require_active_dev_session` guard. The old insecure substring is
        # intentionally gone; assert the corrected, stronger contract.
        i_gate = src.index("dev_pin_is_configured")
        assert i_gate < i_health < i_probe
        # The menu-open gate is now fail-CLOSED on an unconfigured PIN.
        assert "if not dev_pin_is_configured():" in src
        # The shared privileged-action guard exists and is invoked for the
        # probe handler (no `text ==`-only dispatch without a session).
        assert src.count("def _require_active_dev_session") == 1
        guard_uses = src.count("_require_active_dev_session(chat_id)")
        assert guard_uses >= 9, (
            f"expected the C1 guard at every privileged dev handler, "
            f"found {guard_uses} call sites")
        probe_block = src[i_probe:i_probe + 200]
        assert "_require_active_dev_session(chat_id)" in probe_block, (
            "the Probe handler must re-assert an active dev-PIN session")
        # the gate helpers are still imported, never redefined/weakened here
        assert src.count("def dev_pin_is_configured") == 0  # imported, not redef
        assert src.count("def dev_pin_session_active") == 0  # imported, not redef


# ── WS-B: disclosure iff unlinked>0 + verbatim wording (items 7,12) ─────────

_VERBATIM = ("⚠️ {n} עסקאות לא-מקושרות (חסר campaign_id) — לא נכללו · "
             "${x:+,.2f} · דורש קישור")


class TestWSBDisclosure:
    def test_unlinked_keys_present_and_correct(self):
        a = ae.compute_period_analytics(_mixed_df(), _PS, _PE, _ACCT)
        # SELL rows 7 (+13.71) and 8 (-5.00) are NULL/blank-cid in-window.
        assert a["unlinked_count"] == 2
        assert a["unlinked_pnl"] == pytest.approx(8.71, abs=1e-6)
        # BUY row 9 is NULL-cid in-window (open-book silent drop).
        assert a["unlinked_count_buy"] == 1
        assert a["unlinked_pnl_buy"] == pytest.approx(0.0, abs=1e-6)

    def test_disclosure_present_when_unlinked_gt_zero(self):
        a = ae.compute_period_analytics(_mixed_df(), _PS, _PE, _ACCT)
        lines = rr._summary_unlinked_lines(a)
        expect = _VERBATIM.format(n=2, x=8.71)
        assert expect in lines
        ob = rob.unlinked_open_line(a)
        assert ob == [_VERBATIM.format(n=1, x=0.0)]

    def test_no_disclosure_when_unlinked_zero(self):
        a = ae.compute_period_analytics(_clean_df(), _PS, _PE, _ACCT)
        assert a["unlinked_count"] == 0
        assert rr._summary_unlinked_lines(a) == []
        assert rr._unlinked_ctx(a)["unlinked_present"] is False
        assert rob.unlinked_open_line(a) == []

    def test_never_silent_zero_real_founder_scenario(self):
        """8 in-window SELLs, ALL NULL-cid → campaigns_closed==0 but the
        unlinked activity is honestly disclosed (#1)."""
        rows = [_r(str(900 + i), f'S{i}', f'2026-04-{10 + i:02d}', 'SELL',
                   -1, 50.0, 1.0 + i, 0, 'EP', None) for i in range(8)]
        df = pd.DataFrame(rows)
        a = ae.compute_period_analytics(df, _PS, _PE, _ACCT)
        assert a["campaigns_closed"] == 0
        assert a["unlinked_count"] == 8
        lines = rr._summary_unlinked_lines(a)
        assert any("עסקאות לא-מקושרות" in ln for ln in lines)

    def test_verbatim_wording_exact(self):
        ctx = rr._unlinked_ctx({"unlinked_count": 3, "unlinked_pnl": -12.5,
                                "unlinked_count_buy": 0,
                                "unlinked_pnl_buy": 0.0})
        assert ctx["unlinked_line"] == _VERBATIM.format(n=3, x=-12.5)


# ── WS-B: byte-identical guards (RULINGS item 1 / §B / §C) ──────────────────

_COUNTABLE_KEYS = ["campaigns_closed", "win_rate", "expectancy_r",
                   "profit_factor", "avg_win_r", "avg_loss_r", "total_r_net",
                   "realized_pnl", "setup_breakdown", "missing_stop_rate",
                   "oversized_rate", "avg_r_per_day", "excluded_count",
                   "excluded_pnl", "excluded_count_manual",
                   "excluded_pnl_manual", "excluded_count_algo",
                   "excluded_pnl_algo", "best_trade", "worst_trade"]


class TestWSBByteIdentical:
    def test_countable_kpi_subset_byte_identical(self):
        """The additive unlinked_* keys must not move ANY countable KPI."""
        a = ae.compute_period_analytics(_mixed_df(), _PS, _PE, _ACCT)
        # Expected values computed from the linked subset ONLY (C1 countable,
        # C2 DATA_INCOMPLETE, C3 ALGO) — unaffected by the NULL-cid rows.
        assert a["campaigns_closed"] == 1            # only C1 countable
        assert a["realized_pnl"] == pytest.approx(100.0, abs=1e-6)
        assert a["excluded_count"] == 2              # C2 + C3
        assert a["excluded_count_manual"] == 1       # C2
        assert a["excluded_count_algo"] == 1         # C3
        # Removing the NULL/blank rows entirely yields the SAME countable KPIs.
        linked = _mixed_df()
        linked = linked[linked["campaign_id"].notna() &
                        (linked["campaign_id"].astype(str).str.strip() != "")]
        b = ae.compute_period_analytics(linked, _PS, _PE, _ACCT)
        for k in _COUNTABLE_KEYS:
            assert a[k] == b[k], f"countable KPI {k} drifted with NULL-cid"

    def test_open_book_byte_identical_with_vs_without_unlinked(self):
        """get_open_positions_campaign + build_open_book figures unchanged —
        disclosure only (the .notnull() filter is NOT modified)."""
        import engine_core as ec
        df = _mixed_df()
        r1 = ec.get_open_positions_campaign(df.copy())
        # build_open_book on the same df vs the linked-only df: the open-book
        # figures depend only on linked rows (NULL-cid already dropped at :479).
        ob_full = rob.build_open_book(df.copy(), _ACCT,
                                      period_start=_PS, period_end=_PE)
        linked = df[df["campaign_id"].notna() &
                    (df["campaign_id"].astype(str).str.strip() != "")]
        ob_linked = rob.build_open_book(linked.copy(), _ACCT,
                                        period_start=_PS, period_end=_PE)
        assert ob_full["open_book_totals"] == ob_linked["open_book_totals"]
        assert r1["ok"] is True

    def test_unlinked_ctx_keyset_disjoint(self):
        a = ae.compute_period_analytics(_mixed_df(), _PS, _PE, _ACCT)
        uc = rr._unlinked_ctx(a)
        ec_ctx = rr._excluded_ctx(a)
        assert set(uc).isdisjoint(set(ec_ctx)), \
            "unlinked_* must be disjoint from excl_*"
        assert all(k.startswith("unlinked_") for k in uc)

    def test_wsb_no_supabase_write_in_renderer_or_openbook(self):
        """RULINGS item 8 — no insert/update/upsert/delete on trades from the
        WS-B disclosure code paths."""
        for path in ("report_renderer.py", "report_open_book.py"):
            src = open(os.path.join(os.path.dirname(_PROBE_SRC), path),
                       encoding="utf-8").read()
            # The WS-B additions are pure ctx/line builders — assert the
            # specific new symbols carry no write verb nearby.
            assert "unlinked" in src
            for verb in (".insert(", ".upsert(", ".delete("):
                # these never appear adjacent to unlinked logic
                assert verb not in src or "unlinked" not in src.split(
                    verb)[0][-400:], f"{path}: write verb near unlinked"


# ── WS-C: NO-OP — real-data regression byte-identical (RULINGS items 2,10) ──

class TestWSCNoOp:
    def test_get_campaign_risk_metrics_unmodified_behaviour(self):
        import engine_core as ec
        # AEHR-class: initial_stop 68.4 ABOVE entry 60.3 → invalid (NO
        # fallback to initial_risk_price — WS-C deferred, binding).
        m = ec.get_campaign_risk_metrics(
            {"price": 60.3, "quantity": 5, "initial_stop": 68.4,
             "side": "BUY"})
        assert m["valid"] is False
        assert "initial_stop invalid" in m["reason"]
        # -1 sentinel still invalid (no fallback).
        m2 = ec.get_campaign_risk_metrics(
            {"price": 100.0, "quantity": 1, "initial_stop": -1,
             "side": "BUY"})
        assert m2["valid"] is False

    def test_real_data_regression_still_green(self):
        """WS-C NO-OP ⇒ the locked real-data numbers are byte-identical."""
        from tests.test_real_data_april_regression import (_april_df,
                                                           _weekly_df)
        a = ae.compute_period_analytics(
            _april_df(), datetime(2026, 4, 1),
            datetime(2026, 4, 30, 23, 59, 59), _ACCT)
        assert a["campaigns_closed"] == 8
        assert round(a["realized_pnl"], 2) == 180.49
        assert a["win_rate"] == pytest.approx(0.375, abs=1e-6)
        assert a["profit_factor"] == pytest.approx(2.6262, abs=1e-3)
        assert a["excluded_count"] == 2
        w = ae.compute_period_analytics(
            _weekly_df(), datetime(2026, 5, 3),
            datetime(2026, 5, 9, 23, 59, 59), _ACCT)
        assert w["campaigns_closed"] == 0
        assert w["excluded_count"] == 3


# ── Sprint-22: probe diagnostic columns + WS-C fork signal (read-only) ──────

class TestProbeForkDiagnostics:
    def test_per_campaign_line_shows_entry_irp_sl(self, monkeypatch):
        """entry/initial_risk_price/stop_loss are SURFACED per campaign so the
        recoverable-vs-lost-at-source fork is decidable from the probe."""
        import report_scheduler as sched
        monkeypatch.setattr(sched, "_fetch_trades_df",
                            lambda s, e: _mixed_df())
        out = probe.build_probe_report("monthly",
                                       now=datetime(2026, 5, 16, 12))
        assert "entry=" in out
        assert "irp=" in out
        assert "sl=" in out
        # countable reconciliation token is UNCHANGED (Sprint-21 parity).
        assert "נספר=כן" in out and "נספר=לא" in out

    def test_wsc_fork_signal_line_present(self, monkeypatch):
        """C2 (BBB) excluded for invalid initial_stop=-1; its fixture
        stop_loss=-1 (non-zero) ⇒ counted as a recoverable CANDIDATE, labelled
        as needing a Mark ruling (NO fallback applied)."""
        import report_scheduler as sched
        monkeypatch.setattr(sched, "_fetch_trades_df",
                            lambda s, e: _mixed_df())
        out = probe.build_probe_report("monthly",
                                       now=datetime(2026, 5, 16, 12))
        assert "— הכרעת WS-C (מועמדים בלבד) —" in out
        assert "הוחרגו על initial_stop לא תקין:" in out
        assert "דורש פסיקת Mark + חוזה-נתונים" in out

    def test_irp_never_feeds_risk_metrics_wsc_still_deferred(self):
        """The DISPLAY columns must NOT alter campaign-math: the probe's
        _risk_row carries ONLY initial_stop (no initial_risk_price key), so an
        AEHR-class invalid stop stays invalid (WS-C DEFERRED, binding)."""
        import ast
        src = open(_PROBE_SRC, encoding="utf-8").read()
        tree = ast.parse(src, filename=_PROBE_SRC)
        risk_row_keys = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                ks = [k.value for k in node.keys
                      if isinstance(k, ast.Constant)]
                if "initial_stop" in ks and "price" in ks:
                    risk_row_keys = ks
        assert risk_row_keys, "probe _risk_row dict not found"
        assert "initial_risk_price" not in risk_row_keys
        assert "stop_loss" not in risk_row_keys
