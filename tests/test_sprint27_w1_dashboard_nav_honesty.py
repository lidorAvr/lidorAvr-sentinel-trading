"""Sprint-27 W1 — NAMED proof: Dashboard NAV honesty (Mark P1-1 + Data D-F1).

Root: the dashboard sidebar rendered `🏦 Live IBKR NAV` in a GREEN success box
*unconditionally* — even when the NAV was the stale / no-timestamp / silent
$7,500 fallback (its own `load_settings` had a bare `except`). That is the
exact "fallback-as-truth" class CLAUDE.md / AGENTS #1 forbids and Sprint-25 B1
closed for Telegram but never applied to the dashboard.

W1 (presentation-only, ZERO KPI/math change, additive) does two things:

  1. The dashboard reads NAV via the CANONICAL `account_state.load()` single
     source — NOT its own independent bare-`except` reader (closes the
     divergence Data D-F1 flagged).
  2. The sidebar NAV render mirrors B1's gate EXACTLY
     (`report_renderer._nav_disclosure_lines`): broker+fresh ⇒ the
     BYTE-IDENTICAL green "🏦 Live IBKR NAV: **$X**" success box; any
     non-broker-fresh state (deposited / fallback / stale / critical /
     unknown / `ok=False`) ⇒ a clear NON-green warning that reuses the
     already-honest `freshness_label` verbatim + the NAV source.

This file is the Mark-Ruling named proof and pins:
  * broker+fresh ⇒ NO disclosure; the success-box text is byte-identical to
    the pre-W1 string ⇒ the normal screen is unchanged.
  * stale / no-timestamp / missing-config / corrupt-config (fallback,
    `ok=False`) ⇒ the honest disclosure is present and the render is NOT a
    green "Live" success box.
  * the dashboard helper consumes the SAME canonical dict
    `account_state.load()` returns for those config states (D3 no-timestamp /
    D4 missing+corrupt) — i.e. there is no independent bare-`except` reader
    feeding the prominent sidebar figure.

`python -m pytest -q -p no:cacheprovider tests/test_sprint27_w1_dashboard_nav_honesty.py`
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "ci-test-token")
os.environ.setdefault("TELEGRAM_ADMIN_ID", "12345")
os.environ.setdefault("SUPABASE_URL", "https://ci-test.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "ci-test-key")

import account_state as acc_state  # noqa: E402  (real canonical module)

# W1 extracted the sidebar-NAV decision into the pure, stdlib-only helper
# `dashboard_nav.nav_sidebar_render` (no streamlit/engine import) — exactly
# like B1's `report_renderer._nav_disclosure_lines`. `dashboard.py` imports
# THIS helper for the sidebar; testing it directly is the single-source proof
# (the dashboard owns no independent bare-`except` reader for that figure).
from dashboard_nav import nav_sidebar_render as _nav_sidebar_render  # noqa: E402


def test_dashboard_imports_the_pure_helper_for_the_sidebar():
    """Pin the wiring: `dashboard.py` binds the sidebar NAV render to the
    pure `dashboard_nav.nav_sidebar_render` (NOT its own bare-`except`
    reader) AND reads NAV via `account_state.load()`."""
    src = open(
        os.path.join(os.path.dirname(__file__), "..", "dashboard.py"),
        encoding="utf-8").read()
    assert "from dashboard_nav import nav_sidebar_render" in src
    # the prominent sidebar figure comes from the canonical single source
    assert "acc_state.load()" in src
    assert "_nav_sidebar_render(_acc)" in src
    # the OLD bare-except sidebar reader for the green box is gone
    assert 'st.sidebar.success(f"🏦 Live IBKR NAV' not in src


# Stable token of the honest non-green disclosure (never the volatile
# freshness_label which carries a live age).
_HONEST_TOKEN = "לא Live"
_SOURCE_TOKEN = "מקור NAV:"


# ── fixtures: the exact account_state.load() output shapes ──────────────────
_ACC_BROKER_FRESH = {
    "nav": 7921.0, "total_deposited": 7500.0, "risk_pct_input": 0.5,
    "nav_source": "broker", "freshness": "fresh",
    "freshness_label": "✅ NAV עדכני (6.2h)", "is_stale": False,
    "is_critical": False, "ok": True,
}
_ACC_FALLBACK = {  # exact account_state._fallback() shape
    "nav": 7500.0, "total_deposited": 7500.0, "risk_pct_input": 0.5,
    "nav_source": "fallback", "nav_updated_at": None, "age_hours": None,
    "freshness": "unknown",
    "freshness_label": "🟠 Fallback NAV — sentinel_config.json לא נמצא",
    "is_stale": True, "is_critical": False, "ok": False,
}
_ACC_STALE = {
    "nav": 7921.0, "total_deposited": 7500.0, "risk_pct_input": 0.5,
    "nav_source": "broker", "freshness": "stale",
    "freshness_label": "🟡 NAV ישן (30h)", "is_stale": True,
    "is_critical": False, "ok": True,
}
_ACC_CRITICAL = {
    "nav": 7921.0, "total_deposited": 7500.0, "risk_pct_input": 0.5,
    "nav_source": "broker", "freshness": "critical",
    "freshness_label": "🔴 NAV קריטי (60h)", "is_stale": True,
    "is_critical": True, "ok": True,
}
_ACC_DEPOSITED = {
    "nav": 7500.0, "total_deposited": 7500.0, "risk_pct_input": 0.5,
    "nav_source": "deposited", "freshness": "fresh",
    "freshness_label": "✅ NAV עדכני (1.0h)", "is_stale": False,
    "is_critical": False, "ok": True,
}
_ACC_NO_TS = {  # account_state D3 — no nav_updated_at
    "nav": 8100.0, "total_deposited": 7500.0, "risk_pct_input": 0.5,
    "nav_source": "broker", "nav_updated_at": None, "age_hours": None,
    "freshness": "unknown", "freshness_label": "🟠 NAV ללא חותמת זמן",
    "is_stale": True, "is_critical": False, "ok": True,
}


# ── 1. broker+fresh ⇒ unchanged green success box (byte-identical) ──────────
class TestBrokerFreshUnchanged:
    def test_broker_fresh_is_success_kind(self):
        kind, _ = _nav_sidebar_render(_ACC_BROKER_FRESH)
        assert kind == "success"

    def test_broker_fresh_text_byte_identical_to_pre_w1(self):
        # The pre-W1 sidebar string was EXACTLY this f-string. The W1 helper
        # MUST reproduce it byte-for-byte on the happy path so the normal
        # screen is unchanged (Mark-gate: broker+fresh byte-identical).
        nav = _ACC_BROKER_FRESH["nav"]
        pre_w1 = f"🏦 Live IBKR NAV: **${nav:,.2f}**"
        kind, text = _nav_sidebar_render(_ACC_BROKER_FRESH)
        assert kind == "success"
        assert text == pre_w1

    def test_broker_fresh_has_no_disclosure(self):
        _, text = _nav_sidebar_render(_ACC_BROKER_FRESH)
        assert _HONEST_TOKEN not in text
        assert _SOURCE_TOKEN not in text
        assert "Live IBKR NAV" in text  # the unchanged green wording

    def test_broker_fresh_value_formatted_like_before(self):
        # A different fresh broker NAV still renders the identical format.
        acc = dict(_ACC_BROKER_FRESH, nav=12345.6)
        kind, text = _nav_sidebar_render(acc)
        assert kind == "success"
        assert text == "🏦 Live IBKR NAV: **$12,345.60**"


# ── 2. every non-broker-fresh state ⇒ honest NON-green disclosure ───────────
class TestNonBrokerFreshDiscloses:
    @pytest.mark.parametrize("acc", [
        _ACC_FALLBACK, _ACC_STALE, _ACC_CRITICAL, _ACC_DEPOSITED, _ACC_NO_TS,
    ])
    def test_not_green_success(self, acc):
        kind, text = _nav_sidebar_render(acc)
        # NOT a green "Live" success box.
        assert kind == "warning"
        assert "Live IBKR NAV" not in text
        assert _HONEST_TOKEN in text

    @pytest.mark.parametrize("acc", [
        _ACC_FALLBACK, _ACC_STALE, _ACC_CRITICAL, _ACC_DEPOSITED, _ACC_NO_TS,
    ])
    def test_reuses_verbatim_freshness_label_and_source(self, acc):
        # B1 voice: reuse the ALREADY-honest freshness_label verbatim + the
        # source — invent no new wording.
        _, text = _nav_sidebar_render(acc)
        assert acc["freshness_label"] in text
        assert _SOURCE_TOKEN in text
        assert acc["nav_source"] in text

    def test_fallback_is_explicit_about_source(self):
        _, text = _nav_sidebar_render(_ACC_FALLBACK)
        assert "fallback" in text
        assert "לא נתון מדויק" in text

    def test_stale_broker_is_disclosed_too(self):
        # Data D-F1's specific gap: a stale BUT broker NAV must still warn
        # (the old fmt_risk_capital_basis caption missed this).
        kind, text = _nav_sidebar_render(_ACC_STALE)
        assert kind == "warning"
        assert "🟡 NAV ישן (30h)" in text

    def test_empty_or_non_dict_acc_is_disclosed_not_green(self):
        for bad in ({}, None, "x", 123):
            kind, text = _nav_sidebar_render(bad)
            assert kind == "warning"
            assert "Live IBKR NAV" not in text


# ── 3. the dashboard reads NAV via account_state.load() (single source) ─────
#
# Drive REAL config files through the REAL account_state.load() and feed the
# result to the dashboard helper — proving the dashboard consumes the
# canonical resolver's dict (no independent bare-`except` reader for the
# prominent sidebar figure).
class TestCanonicalSingleSource:
    def _load_via_canonical(self, monkeypatch, tmp_path, payload):
        cfg = tmp_path / "sentinel_config.json"
        if payload is not None:
            cfg.write_text(payload, encoding="utf-8")
            monkeypatch.setattr(acc_state, "_CONFIG_PATHS", [str(cfg)])
        else:
            # missing config: point at a path that does not exist
            monkeypatch.setattr(
                acc_state, "_CONFIG_PATHS", [str(tmp_path / "nope.json")])
        return acc_state.load()

    def test_missing_config_canonical_then_helper_is_honest(
            self, monkeypatch, tmp_path):
        acc = self._load_via_canonical(monkeypatch, tmp_path, None)
        # account_state D4: ok=False, fallback.
        assert acc["ok"] is False and acc["nav_source"] == "fallback"
        kind, text = _nav_sidebar_render(acc)
        assert kind == "warning"
        assert "Live IBKR NAV" not in text
        assert acc["freshness_label"] in text  # verbatim canonical label

    def test_corrupt_config_canonical_then_helper_is_honest(
            self, monkeypatch, tmp_path):
        acc = self._load_via_canonical(
            monkeypatch, tmp_path, "{ this is not valid json ")
        assert acc["ok"] is False and acc["nav_source"] == "fallback"
        kind, text = _nav_sidebar_render(acc)
        assert kind == "warning"
        assert "Live IBKR NAV" not in text

    def test_no_timestamp_config_canonical_then_helper_is_honest(
            self, monkeypatch, tmp_path):
        # D3 — a real broker `nav` but NO nav_updated_at ⇒ unknown/stale.
        acc = self._load_via_canonical(
            monkeypatch, tmp_path, json.dumps({"nav": 8100.0}))
        assert acc["freshness"] == "unknown" and acc["is_stale"] is True
        kind, text = _nav_sidebar_render(acc)
        assert kind == "warning"
        assert "Live IBKR NAV" not in text
        assert acc["freshness_label"] in text

    def test_stale_config_canonical_then_helper_is_honest(
            self, monkeypatch, tmp_path):
        acc = self._load_via_canonical(
            monkeypatch, tmp_path,
            json.dumps({"nav": 8100.0,
                        "nav_updated_at": "2000-01-01T00:00:00"}))
        # very old timestamp ⇒ critical (>=48h).
        assert acc["is_stale"] is True
        kind, text = _nav_sidebar_render(acc)
        assert kind == "warning"
        assert "Live IBKR NAV" not in text

    def test_fresh_broker_config_canonical_then_helper_unchanged_green(
            self, monkeypatch, tmp_path):
        # A genuine fresh broker NAV ⇒ the canonical loader says broker+fresh
        # ⇒ the helper renders the BYTE-IDENTICAL green box (no disclosure).
        from datetime import datetime
        acc = self._load_via_canonical(
            monkeypatch, tmp_path,
            json.dumps({"nav": 8100.0,
                        "nav_updated_at": datetime.now().isoformat()}))
        assert acc["nav_source"] == "broker" and acc["freshness"] == "fresh"
        kind, text = _nav_sidebar_render(acc)
        assert kind == "success"
        assert text == f"🏦 Live IBKR NAV: **${acc['nav']:,.2f}**"

    def test_dashboard_module_exposes_the_helper_not_a_bare_reader(self):
        # The helper exists and is the surface the sidebar uses; the canonical
        # single-source wiring is asserted by the config-driven tests above.
        assert callable(_nav_sidebar_render)
