"""Sprint-24 Wave-2 + Wave-2b byte-identical proofs (DEC-20260516-021).

Scope SHIPPED (see docs/teams/SPRINT24_WAVE2_IMPL.md):
  * A1/A3 — analytics_engine.py: ADDITIVE comment-only clarity.
  * B2 — report_scheduler.py: lazy module-singleton Supabase client;
    `_fetch_trades_df` issues the SAME table/select/filter/order chain
    and keeps the missing-creds → None and failure → None contracts.
  * Wave-2b (founder-authorized post-Wave-2): B1 (the twice-applied
    `bucket.apply(ec.is_stat_countable)` mask hoisted ONCE into `_cnt`)
    and B3 (`_coerce_numeric` extraction) are now SHIPPED as PROVABLE
    byte-identical no-ops, admitted via the governed Sprint-19 byte-lock
    allowlist expansion and proven by
    tests/test_sprint24_b1b3_byte_identical.py.
  * B4 — SKIPPED (see impl doc). period_data_probe.py keeps its OWN
    inlined coerce copy (NOT rewired to the analytics helper).

These tests are NAMED Ruling-3 identity proofs. No behavior/math change
is asserted — only that the shipped path is provably equivalent.
"""
import os
import subprocess
import sys
from datetime import datetime
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import report_scheduler as rs

_REPO = os.path.dirname(os.path.dirname(__file__))


# ── A1/A3 + B1/B3 — analytics_engine.py stayed STRICTLY append-only ──

class TestAnalyticsEngineAppendOnly:
    """Wave-2b (DEC-20260516-021): the founder, after Wave-2's honest
    report, explicitly authorized landing B1 + B3 as PROVABLE byte-
    identical no-ops via a governed Sprint-19 byte-lock allowlist
    expansion. So analytics_engine.py is NO LONGER strictly append-only:
    its diff is EXACTLY the A1/A3 additive `#` comments PLUS the B1
    mask-once hoist + B3 `_coerce_numeric` extraction — and NOTHING else.
    Byte-identity of B1/B3 is proven (strictly stronger than a token
    proxy) by tests/test_sprint24_b1b3_byte_identical.py."""

    def _diff(self):
        return subprocess.run(
            ["git", "diff", "--", "analytics_engine.py"],
            cwd=_REPO, capture_output=True, text=True).stdout

    # The EXACT `.strip()`-ed B1/B3 diff lines (verbatim from `git diff`).
    _B1B3_REMOVED = frozenset({
        'for col in ("price", "quantity", "stop_loss", '
        '"initial_stop", "pnl_usd"):',
        'if col in df.columns:',
        'df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)',
        'countable = campaigns[bucket.apply(ec.is_stat_countable)]',
        'excluded  = campaigns[~bucket.apply(ec.is_stat_countable)]',
    })
    _B1B3_ADDED = frozenset({
        'df = _coerce_numeric(df, ("price", "quantity", "stop_loss", '
        '"initial_stop", "pnl_usd"))',
        '_cnt = bucket.apply(ec.is_stat_countable)',
        'countable = campaigns[_cnt]',
        'excluded  = campaigns[~_cnt]',
        'def _coerce_numeric(df, cols):',
        'for col in cols:',
        'if col in df.columns:',
        'df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)',
        'return df',
    })

    def test_only_authorized_existing_lines_removed_or_modified(self):
        """Post-Wave-2b: any removed/modified analytics_engine.py line is in
        the founder-authorized B1+B3 set (A1/A3 stayed purely additive).
        Commit-state-AGNOSTIC: once the change is committed (CI checks out
        the committed state) `git diff` is empty → vacuously satisfied; on a
        dirty tree any removal must still be authorized. That B1/B3 ARE
        present is proven commit-agnostically by
        test_b1_b3_helpers_introduced_and_provable (source inspection)."""
        removed = {ln[1:].strip() for ln in self._diff().splitlines()
                   if ln.startswith("-") and not ln.startswith("---")
                   and ln[1:].strip()}
        unexpected = removed - self._B1B3_REMOVED
        assert unexpected == set(), (
            "analytics_engine.py removed a line outside the founder-"
            f"authorized B1/B3 set: {sorted(unexpected)}")

    def test_every_added_line_is_comment_or_authorized_b1b3(self):
        """Post-Wave-2b: every added line is either an A1/A3 `#` comment
        or a member of the founder-authorized B1+B3 added set."""
        added = [ln[1:] for ln in self._diff().splitlines()
                 if ln.startswith("+") and not ln.startswith("+++")
                 and ln[1:].strip()]
        bad = [a for a in added
               if not a.strip().startswith("#")
               and a.strip() not in self._B1B3_ADDED]
        assert bad == [], (
            "analytics_engine.py added a line that is neither an A1/A3 "
            f"comment nor an authorized B1/B3 line: {bad}")

    def test_b1_b3_helpers_introduced_and_provable(self):
        """Post-Wave-2b (premise reversed by the founder): the B1 mask is
        hoisted ONCE via a single `_cnt`, the B3 `_coerce_numeric` helper
        exists, the OLD twice-applied/inlined forms are GONE, and the
        named byte-identical proof file is present & collectible."""
        src = open(os.path.join(_REPO, "analytics_engine.py")).read()
        # B3 helper exists; B1 single-mask local exists.
        assert "def _coerce_numeric(df, cols):" in src
        assert "_cnt = bucket.apply(ec.is_stat_countable)" in src
        assert "countable = campaigns[_cnt]" in src
        assert "excluded  = campaigns[~_cnt]" in src
        assert ('df = _coerce_numeric(df, ("price", "quantity", '
                '"stop_loss", "initial_stop", "pnl_usd"))') in src
        # The OLD twice-applied mask + inlined loop are GONE.
        assert ("countable = campaigns[bucket.apply("
                "ec.is_stat_countable)]") not in src
        assert ("excluded  = campaigns[~bucket.apply("
                "ec.is_stat_countable)]") not in src
        assert ('for col in ("price", "quantity", "stop_loss", '
                '"initial_stop", "pnl_usd"):') not in src
        # The line :30 to_datetime stays INLINED (Sprint-22 load-bearing,
        # explicitly OUT of B3 scope — not folded into the helper).
        assert ('df["trade_date"] = pd.to_datetime(df["trade_date"], '
                'errors="coerce")') in src
        # Mask hoisted ONCE: exactly one bucket.apply(is_stat_countable).
        assert src.count("bucket.apply(ec.is_stat_countable)") == 1
        # NAMED Ruling-3 proof present & collectible.
        proof = os.path.join(
            _REPO, "tests", "test_sprint24_b1b3_byte_identical.py")
        assert os.path.isfile(proof)
        assert "class TestSprint24B1B3ByteIdentical" in open(proof).read()

    def test_period_data_probe_byte_locked_untouched(self):
        out = subprocess.run(
            ["git", "diff", "--", "period_data_probe.py"],
            cwd=_REPO, capture_output=True, text=True).stdout
        assert out == "", "period_data_probe.py must be byte-identical"
        # probe keeps its OWN inlined coerce (B3 SKIPPED, not rewired)
        psrc = open(os.path.join(_REPO, "period_data_probe.py")).read()
        assert "_coerce_numeric" not in psrc

    def test_engine_core_untouched(self):
        out = subprocess.run(
            ["git", "diff", "--", "engine_core.py"],
            cwd=_REPO, capture_output=True, text=True).stdout
        assert out == "", "engine_core.py must be untouched"


# ── B2 — lazy Supabase client singleton + unchanged-fetch contract ──

class _FakeResp:
    def __init__(self, data):
        self.data = data


class _FakeTable:
    """Records the exact query chain so we can assert it is unchanged."""

    def __init__(self, log):
        self._log = log

    def select(self, *a):
        self._log.append(("select", a))
        return self

    def gte(self, *a):
        self._log.append(("gte", a))
        return self

    def lte(self, *a):
        self._log.append(("lte", a))
        return self

    def order(self, *a, **kw):
        self._log.append(("order", a, kw))
        return self

    def execute(self):
        self._log.append(("execute",))
        return _FakeResp([{"trade_id": "t1", "trade_date": "2026-04-10",
                           "side": "SELL", "pnl_usd": 1.0}])


class _FakeClient:
    instances = 0

    def __init__(self):
        _FakeClient.instances += 1
        self.query_log = []

    def table(self, name):
        self.query_log.append(("table", name))
        return _FakeTable(self.query_log)


@pytest.fixture(autouse=True)
def _reset_singleton():
    rs._SB_CLIENT = None
    rs._SB_CLIENT_KEY = None
    yield
    rs._SB_CLIENT = None
    rs._SB_CLIENT_KEY = None


class TestB2ClientSingleton:
    def test_get_supabase_client_caches_per_key(self):
        with patch("supabase.create_client") as cc:
            cc.side_effect = lambda u, k: MagicMock(name=f"client::{u}::{k}")
            c1 = rs._get_supabase_client("u", "k")
            c2 = rs._get_supabase_client("u", "k")
            assert c1 is c2
            assert cc.call_count == 1  # built ONCE, reused

    def test_get_supabase_client_rebuilds_on_key_change(self):
        with patch("supabase.create_client") as cc:
            cc.side_effect = lambda u, k: MagicMock(name=f"{u}:{k}")
            c1 = rs._get_supabase_client("u1", "k1")
            c2 = rs._get_supabase_client("u2", "k2")
            assert c1 is not c2
            assert cc.call_count == 2

    def test_fetch_trades_df_query_chain_unchanged(self, monkeypatch):
        monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
        monkeypatch.setenv("SUPABASE_KEY", "anon-key")
        _FakeClient.instances = 0
        fake = _FakeClient()
        with patch("dotenv.load_dotenv", lambda *a, **k: None), \
             patch("supabase.create_client", return_value=fake):
            ps = datetime(2026, 4, 1)
            pe = datetime(2026, 4, 30)
            df1 = rs._fetch_trades_df(ps, pe)
            df2 = rs._fetch_trades_df(ps, pe)
        # client built ONCE despite two fetches (singleton reuse)
        assert _FakeClient.instances == 1
        assert rs._SB_CLIENT is fake
        assert isinstance(df1, pd.DataFrame) and isinstance(df2, pd.DataFrame)
        # exact query chain preserved: 8-week lookback, select *, gte/lte, asc
        lookback = (ps - pd.Timedelta(weeks=8)).strftime("%Y-%m-%d")
        end_str = pe.strftime("%Y-%m-%d")
        log = fake.query_log
        assert ("table", "trades") in log
        assert ("select", ("*",)) in log
        assert ("gte", ("trade_date", lookback)) in log
        assert ("lte", ("trade_date", end_str)) in log
        assert ("order", ("trade_date",), {"desc": False}) in log

    def test_fetch_trades_df_missing_creds_returns_none(self, monkeypatch):
        monkeypatch.delenv("SUPABASE_URL", raising=False)
        monkeypatch.delenv("SUPABASE_KEY", raising=False)
        with patch("dotenv.load_dotenv", lambda *a, **k: None):
            out = rs._fetch_trades_df(datetime(2026, 4, 1),
                                      datetime(2026, 4, 30))
        assert out is None  # unchanged missing-creds contract

    def test_fetch_trades_df_failure_returns_none(self, monkeypatch):
        monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
        monkeypatch.setenv("SUPABASE_KEY", "anon-key")
        with patch("dotenv.load_dotenv", lambda *a, **k: None), \
             patch("supabase.create_client", side_effect=RuntimeError("boom")):
            out = rs._fetch_trades_df(datetime(2026, 4, 1),
                                      datetime(2026, 4, 30))
        assert out is None  # unchanged failure → None contract

    def test_fetch_trades_df_empty_data_returns_empty_df(self, monkeypatch):
        monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
        monkeypatch.setenv("SUPABASE_KEY", "anon-key")

        class _EmptyTable(_FakeTable):
            def execute(self):
                return _FakeResp([])

        class _EmptyClient(_FakeClient):
            def table(self, name):
                self.query_log.append(("table", name))
                return _EmptyTable(self.query_log)

        with patch("dotenv.load_dotenv", lambda *a, **k: None), \
             patch("supabase.create_client", return_value=_EmptyClient()):
            out = rs._fetch_trades_df(datetime(2026, 4, 1),
                                      datetime(2026, 4, 30))
        assert isinstance(out, pd.DataFrame) and out.empty
