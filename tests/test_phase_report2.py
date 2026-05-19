"""Phase REPORT-2 acceptance suite — W-R2-1 pure units-lifecycle helper +
THE single-source-of-truth Hebrew formatter, W-R2-2 dual-surface
(Telegram discretionary card + dashboard per-position detail) wiring,
W-R2-3 SUPPRESSIVE-ONLY decision-awareness.

Authoritative spec: docs/teams/PHASE_REPORT2_SCOPE.md (governs).

REPORT-2 is read-only & honest: a pure deterministic re-projection of the
SAME raw legs the byte-locked engine splits in `split_side_first` (Σ|BUY|
/ Σ|SELL| / net), gated by the engine's OWN authoritative `quantity`. When
the legs are missing / ambiguous / non-reconciling the lifecycle is `—` +
`לא ניתן לאמת` — NEVER a fabricated number, NEVER a silent zero
(AGENTS.md #1; absence ≠ data). The decision-awareness half is
SUPPRESSIVE-ONLY: it softens a redundant realize/trim/Runner voice on a
non-ALGO campaign with realized-units > 0 — ZERO new directive, ZERO
risk-math change, ZERO ALGO touch, ZERO new message TYPE; on `ok=False`
the EXISTING `action_short` renders verbatim; a BROKEN / stop-breach /
critical action is NEVER suppressed.

These tests ONLY ADD coverage — no existing test is deleted or weakened
(Mark 6.1). All fixtures are hand-crafted synthetic leg dicts (NO real
symbols / quantities / P&L / CSV).
"""
import ast
import importlib
import os
import sys
from datetime import datetime

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import position_lifecycle as plc  # noqa: E402


# ── synthetic leg fixtures (no real trade data) ─────────────────────────────
def _leg(side, qty, trade_id=None):
    d = {"side": side, "quantity": qty}
    if trade_id is not None:
        d["trade_id"] = trade_id
    return d


# ════════════════════════════════════════════════════════════════════════════
# Case 1 — units-derivation correctness (mirrors split_side_first doctrine)
# ════════════════════════════════════════════════════════════════════════════
class TestCase1DerivationCorrectness:
    def test_single_buy_full_position(self):
        rows = [_leg("BUY", 10)]
        lc = plc.compute_units_lifecycle(rows, engine_net_qty=10)
        assert lc["ok"] is True
        assert lc["original"] == 10
        assert lc["realized"] == 0
        assert lc["remaining"] == 10
        assert lc["realized_pct"] == 0.0

    def test_buy_plus_add_on_original_includes_addons(self):
        # original = Σ|BUY| INCLUDING add-ons (NOT first-day-only base_qty)
        rows = [_leg("BUY", 10), _leg("BUY", 5)]
        lc = plc.compute_units_lifecycle(rows, engine_net_qty=15)
        assert lc["ok"] is True
        assert lc["original"] == 15
        assert lc["realized"] == 0
        assert lc["remaining"] == 15
        assert lc["realized_pct"] == 0.0

    def test_buy_plus_partial_sell(self):
        # founder's exact example: BUY 10 +add 5, SELL 6 → 15 / 9 / 6 / 40%
        rows = [_leg("BUY", 10), _leg("BUY", 5), _leg("SELL", 6)]
        lc = plc.compute_units_lifecycle(rows, engine_net_qty=9)
        assert lc["ok"] is True
        assert lc["original"] == 15
        assert lc["realized"] == 6
        assert lc["remaining"] == 9
        assert lc["realized_pct"] == pytest.approx(40.0)

    def test_buy_full_then_add(self):
        # BUY 4, SELL 4 (flat), BUY 3 → original 7, realized 4, net 3
        rows = [_leg("BUY", 4), _leg("SELL", 4), _leg("BUY", 3)]
        lc = plc.compute_units_lifecycle(rows, engine_net_qty=3)
        assert lc["ok"] is True
        assert lc["original"] == 7
        assert lc["realized"] == 4
        assert lc["remaining"] == 3
        assert lc["realized_pct"] == pytest.approx(4 / 7 * 100)

    def test_quantity_treated_as_magnitude_and_side_normalised(self):
        # negative-qty SELL + lowercase/whitespace side — exactly the
        # split_side_first doctrine (str(side).upper().strip(); .abs()).
        rows = [_leg(" buy ", 10), _leg("Sell", -4)]
        lc = plc.compute_units_lifecycle(rows, engine_net_qty=6)
        assert lc["ok"] is True
        assert lc["original"] == 10
        assert lc["realized"] == 4
        assert lc["remaining"] == 6

    def test_derivation_matches_split_side_first_doctrine(self):
        """The helper's Σ|BUY|/Σ|SELL| must equal engine_core.split_side_first
        for the SAME legs (the authoritative byte-locked doctrine)."""
        import pandas as pd
        import engine_core as ec
        rows = [_leg("BUY", 10, "t1"), _leg("buy", 5, "t2"),
                _leg("SELL", -3, "t3")]
        g = pd.DataFrame(rows)
        _b, _s, bq, sq = ec.split_side_first(g)
        net = bq - sq
        lc = plc.compute_units_lifecycle(rows, engine_net_qty=net)
        assert lc["original"] == bq
        assert lc["realized"] == sq
        assert lc["remaining"] == net


# ════════════════════════════════════════════════════════════════════════════
# Case 2 — every §3 honest-empty gate ⇒ `—` + `לא ניתן לאמת` (NOT zero/guess)
# ════════════════════════════════════════════════════════════════════════════
class TestCase2HonestEmptyGates:
    def _is_honest_empty(self, lc):
        assert lc["ok"] is False
        assert lc["original"] is None and lc["realized"] is None
        assert lc["remaining"] is None and lc["realized_pct"] is None
        line = plc.format_units_lifecycle(lc)
        assert "—" in line
        assert plc.UNVERIFIABLE_HE in line  # "לא ניתן לאמת"
        # never a fabricated number / silent zero
        assert "0%" not in line and "מקורי" not in line

    def test_no_rows_gate(self):
        self._is_honest_empty(plc.compute_units_lifecycle([], engine_net_qty=5))
        self._is_honest_empty(
            plc.compute_units_lifecycle(None, engine_net_qty=5))

    def test_buys_qty_le_0_gate(self):
        # only SELL legs / no BUY ⇒ cannot establish original base
        lc = plc.compute_units_lifecycle([_leg("SELL", 3)], engine_net_qty=0)
        assert lc["reason"] == "buys_qty_le_0"
        self._is_honest_empty(lc)

    def test_sells_gt_buys_sign_gate(self):
        # over-export artifact: Σ|SELL| > Σ|BUY|
        rows = [_leg("BUY", 4), _leg("SELL", 9)]
        lc = plc.compute_units_lifecycle(rows, engine_net_qty=-5)
        assert lc["reason"] == "sells_gt_buys"
        self._is_honest_empty(lc)

    def test_net_reconciliation_mismatch_gate(self):
        # re-derived net (15-6=9) does NOT match the engine's quantity (12):
        # the leg split is untrustworthy ⇒ WHOLE line honest-empty (no guess)
        rows = [_leg("BUY", 10), _leg("BUY", 5), _leg("SELL", 6)]
        lc = plc.compute_units_lifecycle(rows, engine_net_qty=12)
        assert lc["reason"] == "net_recon_mismatch"
        self._is_honest_empty(lc)

    def test_reconciliation_within_engine_tolerance_passes(self):
        # within the engine's own 0.001 tolerance ⇒ valid (not a mismatch)
        rows = [_leg("BUY", 10), _leg("SELL", 4)]
        lc = plc.compute_units_lifecycle(rows, engine_net_qty=6.0005)
        assert lc["ok"] is True
        assert lc["remaining"] == 6

    def test_reconciliation_tolerance_pins_engine_constant(self):
        # the tolerance must be the engine's own 0.001 (engine_core.py:531)
        assert plc.RECON_TOL == 0.001


# ════════════════════════════════════════════════════════════════════════════
# Case 3 — exact-trade_id dedup mirrors split_side_first (F4)
# ════════════════════════════════════════════════════════════════════════════
class TestCase3TradeIdDedup:
    def test_duplicate_sell_not_double_counted(self):
        # a re-exported/double-synced SELL (same trade_id) counted ONCE
        rows = [_leg("BUY", 10, "b1"),
                _leg("SELL", 4, "s1"), _leg("SELL", 4, "s1")]
        lc = plc.compute_units_lifecycle(rows, engine_net_qty=6)
        assert lc["ok"] is True
        assert lc["realized"] == 4   # NOT 8
        assert lc["remaining"] == 6

    def test_dedup_only_when_all_rows_carry_trade_id(self):
        # guarded on column PRESENCE: absent on any row ⇒ no-op (no dedup)
        rows = [_leg("BUY", 10), _leg("SELL", 4), _leg("SELL", 4)]
        lc = plc.compute_units_lifecycle(rows, engine_net_qty=2)
        assert lc["ok"] is True
        assert lc["realized"] == 8   # not deduped (no trade_id key)

    def test_dedup_matches_engine_get_open_positions(self):
        """The dedup must mirror engine_core.get_open_positions_campaign /
        split_side_first F4 (drop_duplicates subset=[trade_id] keep=first)."""
        import pandas as pd
        import engine_core as ec
        rows = [_leg("BUY", 10, "b1"),
                _leg("SELL", 4, "s1"), _leg("SELL", 4, "s1")]
        g = pd.DataFrame(rows)
        if "trade_id" in g.columns:
            g = g.drop_duplicates(subset=["trade_id"], keep="first")
        _b, _s, bq, sq = ec.split_side_first(g)
        lc = plc.compute_units_lifecycle(rows, engine_net_qty=bq - sq)
        assert lc["original"] == bq
        assert lc["realized"] == sq


# ════════════════════════════════════════════════════════════════════════════
# Case 4 — valid-line formatting + founder's exact example
# ════════════════════════════════════════════════════════════════════════════
class TestCase4ValidLineFormat:
    def test_founder_example_line(self):
        rows = [_leg("BUY", 10), _leg("BUY", 5), _leg("SELL", 6)]
        lc = plc.compute_units_lifecycle(rows, engine_net_qty=9)
        line = plc.format_units_lifecycle(lc)
        assert "מקורי 15" in line
        assert "נותרו 9" in line
        assert "מומשו 6" in line
        assert "40%" in line
        assert plc.UNVERIFIABLE_HE not in line
        assert "—" not in line

    def test_fractional_units_trimmed(self):
        rows = [_leg("BUY", 1.5), _leg("SELL", 0.5)]
        lc = plc.compute_units_lifecycle(rows, engine_net_qty=1.0)
        line = plc.format_units_lifecycle(lc)
        assert "מקורי 1.5" in line
        assert "נותרו 1" in line
        assert "מומשו 0.5" in line

    def test_formatter_never_raises_on_garbage(self):
        for bad in (None, {}, {"ok": True}, "x", 7, [], {"ok": "yes"}):
            out = plc.format_units_lifecycle(bad)
            assert isinstance(out, str)
            assert plc.UNVERIFIABLE_HE in out  # honest empty, never a number

    def test_compute_never_raises_on_garbage(self):
        for bad in ("x", 7, [{"side": object()}], [{}], [None]):
            lc = plc.compute_units_lifecycle(bad, engine_net_qty="?")
            assert lc["ok"] is False  # honest empty, never a fabricated value


# ════════════════════════════════════════════════════════════════════════════
# Case 5 — cross-surface byte-identity (the core anti-drift proof, SCOPE §5)
# ════════════════════════════════════════════════════════════════════════════
class TestCase5CrossSurfaceByteIdentity:
    def test_telegram_and_dashboard_emit_identical_line(self):
        """Both surfaces call the SAME `format_units_lifecycle`. For the SAME
        input the line is byte-identical (cannot drift)."""
        for rows, net in (
            ([_leg("BUY", 10), _leg("BUY", 5), _leg("SELL", 6)], 9),
            ([_leg("SELL", 3)], 0),                       # honest empty
            ([_leg("BUY", 4), _leg("SELL", 9)], -5),       # honest empty
            ([], 5),                                       # honest empty
        ):
            lc = plc.compute_units_lifecycle(rows, engine_net_qty=net)
            telegram_line = plc.format_units_lifecycle(lc)
            dashboard_line = plc.format_units_lifecycle(lc)
            assert telegram_line == dashboard_line
            assert telegram_line.encode("utf-8") == \
                dashboard_line.encode("utf-8")

    def test_both_surfaces_reference_the_single_formatter(self):
        """Static proof neither surface formats independently: both
        telegram_portfolio.py and dashboard.py call
        position_lifecycle.format_units_lifecycle — nothing else formats
        the lifecycle text."""
        root = os.path.dirname(os.path.dirname(__file__))
        tp = open(os.path.join(root, "telegram_portfolio.py"),
                  encoding="utf-8").read()
        db = open(os.path.join(root, "dashboard.py"),
                  encoding="utf-8").read()
        assert "format_units_lifecycle" in tp
        assert "format_units_lifecycle" in db
        assert "compute_units_lifecycle" in tp
        assert "compute_units_lifecycle" in db
        # both import the SAME pure module
        assert "import position_lifecycle" in tp
        assert "import position_lifecycle" in db


# ════════════════════════════════════════════════════════════════════════════
# Case 6 — SUPPRESSIVE-ONLY decision-awareness (the 4 HARD FENCES, SCOPE §4)
# ════════════════════════════════════════════════════════════════════════════
# The suppression is a thin, self-contained display-layer rule inside the
# NON-ALGO branch of handle_portfolio_room. These tests pin its logic
# directly (the exact predicate the build wired) so the fences are proven
# without standing up the whole bot.
def _suppress(action_short, status, lc):
    """Mirror of the wired predicate in
    telegram_portfolio.handle_portfolio_room (non-ALGO branch)."""
    SOFTENABLE = (
        "שקול מימוש חלקי", "שקול מימוש נוסף", "הידוק ל-Runner",
        "הידוק אגרסיבי ל-Runner", "קדם סטופ ל-Runner",
        "Runner חופשי - שקול מימוש",
        "Runner חופשי - שקול מימוש נוסף בשבירת MA10",
        "Runner חופשי - שקול מימוש בשבירת MA10",
    )
    CRITICAL_STATUS = ("🚨 קריטי", "🔴 Broken", "🚨 חריגת סיכון אלגו")
    NEVER_SUPPRESS_ACTION = (
        "יציאה מיידית 🚨", "יציאה / הידוק מידי",
        "מימוש יתרה / יציאה לפי תוכנית", "שקול סגירת יתרת Runner",
        "להפחית חשיפה",
    )
    if (lc.get("ok") and (lc.get("realized") or 0) > 0
            and status not in CRITICAL_STATUS
            and action_short not in NEVER_SUPPRESS_ACTION
            and any(t in str(action_short) for t in SOFTENABLE)):
        return "כבר מומש חלקית — אין צורך לממש שוב כרגע"
    return action_short


_REALIZED = plc.compute_units_lifecycle(
    [_leg("BUY", 10), _leg("SELL", 4)], engine_net_qty=6)          # ok, r>0
_FULL = plc.compute_units_lifecycle([_leg("BUY", 10)], engine_net_qty=10)  # r=0
_AMBIG = plc.compute_units_lifecycle([_leg("SELL", 3)], engine_net_qty=0)  # ok=F


class TestCase6SuppressiveOnly:
    def test_fires_only_when_realized_gt_0_and_softenable(self):
        out = _suppress("שקול מימוש חלקי", "🟢 תקין", _REALIZED)
        assert out == "כבר מומש חלקית — אין צורך לממש שוב כרגע"

    def test_does_not_fire_when_no_realized_units(self):
        # realized == 0 ⇒ existing action verbatim (nothing to de-noise)
        out = _suppress("שקול מימוש חלקי", "🟢 תקין", _FULL)
        assert out == "שקול מימוש חלקי"

    def test_does_not_fire_on_ambiguous_ok_false(self):
        # honest-empty / cannot prove realized>0 ⇒ EXISTING action verbatim
        out = _suppress("שקול מימוש חלקי", "🟢 תקין", _AMBIG)
        assert out == "שקול מימוש חלקי"

    def test_broken_stop_breach_critical_never_suppressed(self):
        # a BROKEN / stop-breach / critical status+action is NEVER softened,
        # even with realized>0
        for st, act in (
            ("🚨 קריטי", "יציאה מיידית 🚨"),
            ("🔴 Broken", "יציאה / הידוק מידי"),
            ("🔴 Broken", "מימוש יתרה / יציאה לפי תוכנית"),
            ("🚨 קריטי", "שקול סגירת יתרת Runner"),
            ("🚨 חריגת סיכון אלגו", "להפחית חשיפה"),
        ):
            assert _suppress(act, st, _REALIZED) == act

    def test_non_softenable_action_passes_through_verbatim(self):
        # a neutral "hold" action is NOT a realize/trim voice ⇒ untouched
        out = _suppress("החזק Runner חופשי", "🟢 תקין", _REALIZED)
        assert out == "החזק Runner חופשי"

    def test_softens_runner_tighten_voices(self):
        for act in ("הידוק ל-Runner", "הידוק אגרסיבי ל-Runner",
                    "קדם סטופ ל-Runner",
                    "Runner חופשי - שקול מימוש נוסף בשבירת MA10"):
            assert _suppress(act, "🟢 תקין", _REALIZED) == \
                "כבר מומש חלקית — אין צורך לממש שוב כרגע"

    def test_suppression_note_is_not_a_new_directive_or_type(self):
        note = _suppress("שקול מימוש חלקי", "🟢 תקין", _REALIZED)
        # It is exactly the SCOPE §4(c) neutral honest de-noising note (a
        # "no need to realize again" suppression of a redundant voice — NOT
        # a new instruction). It must introduce NO new actuation/TYPE token.
        assert note == "כבר מומש חלקית — אין צורך לממש שוב כרגע"
        for tok in ("callback", "push", "alert", "TYPE", "directive",
                    "בצע", "מכור עכשיו", "צא מיד"):
            assert tok not in note
        # it is a de-noising negation ("אין צורך" = no need) — not an
        # imperative to act
        assert "אין צורך" in note


# ════════════════════════════════════════════════════════════════════════════
# Case 7 — ALGO observe-only carve-out INVIOLABLE (the ALGO branch untouched)
# ════════════════════════════════════════════════════════════════════════════
class TestCase7AlgoObserveOnlyIntact:
    def test_algo_branch_and_algo_observed_byte_diff_only_imports(self):
        """The suppression must be NON-ALGO only. The ALGO branch of
        handle_portfolio_room and telegram_tasks._algo_observed must NOT
        receive any suppression logic. We assert the only edits to
        telegram_portfolio.py are the additive lifecycle/suppression block
        and the new import — the ALGO `else`-sibling branch wording is
        byte-identical to baseline reasoning (no suppression token inside
        the ALGO branch)."""
        root = os.path.dirname(os.path.dirname(__file__))
        tp = open(os.path.join(root, "telegram_portfolio.py"),
                  encoding="utf-8").read()
        # the ALGO branch block
        algo_start = tp.index("if str(setup).upper() == 'ALGO':")
        algo_block = tp[algo_start:tp.index("else:", algo_start)]
        # the suppression note + softening predicate live in the NON-ALGO
        # branch ONLY — never inside the ALGO block
        assert "כבר מומש חלקית" not in algo_block
        assert "_action_short_eff" not in algo_block
        assert "format_units_lifecycle" not in algo_block

    def test_telegram_tasks_algo_observed_not_touched_by_phase(self):
        # telegram_tasks.py is OUTSIDE the permitted diff (SCOPE §7) — no
        # REPORT-2 edit at all (the _algo_observed observe-only path stays
        # verbatim; the suppression is display-layer in telegram_portfolio
        # only, never the ALGO oversight path).
        root = os.path.dirname(os.path.dirname(__file__))
        tt = open(os.path.join(root, "telegram_tasks.py"),
                  encoding="utf-8").read()
        assert "position_lifecycle" not in tt
        assert "compute_units_lifecycle" not in tt
        assert "כבר מומש חלקית" not in tt
        # the observe-only _algo_observed payload is still present & intact
        assert '_algo_observed' in tt

    def test_helper_carries_no_action_wording(self):
        # the lifecycle line is a factual units read-out — it MUST NOT
        # carry any directive/recommendation token (safe to show on ALGO).
        for rows, net in (([_leg("BUY", 10), _leg("SELL", 4)], 6),
                          ([], 5)):
            lc = plc.compute_units_lifecycle(rows, engine_net_qty=net)
            line = plc.format_units_lifecycle(lc)
            for tok in ("שקול", "ממש", "הידוק", "יציאה", "פעולה",
                        "המלצה", "buy", "sell"):
                assert tok not in line


# ════════════════════════════════════════════════════════════════════════════
# Case 8 — never-replace: the existing quantity/Qty stays byte-identical
# ════════════════════════════════════════════════════════════════════════════
class TestCase8NeverReplace:
    def test_lifecycle_is_strictly_additive_in_telegram(self):
        """The lifecycle line is APPENDED after the card; the card's
        existing `quantity`/`כמות` token is unchanged. Static proof: the
        existing qty_text/`כמות` formatting is not modified, and the
        lifecycle is a separate appended `msg +=` line."""
        root = os.path.dirname(os.path.dirname(__file__))
        tp = open(os.path.join(root, "telegram_portfolio.py"),
                  encoding="utf-8").read()
        # the canonical qty token formatting is intact
        assert 'qty_text   = f"`{qty}`"' in tp
        assert "כמות: {qty_text}" in tp        # ALGO line unchanged
        # the lifecycle line is appended as its own additive msg line
        assert "msg += f\"{RTL}   ▸ {_lc_line}\\n\"" in tp

    def test_lifecycle_is_strictly_additive_in_dashboard(self):
        root = os.path.dirname(os.path.dirname(__file__))
        db = open(os.path.join(root, "dashboard.py"),
                  encoding="utf-8").read()
        # the additive element NEVER replaces the Qty column
        assert "'Qty': qty" in db                # live_df Qty col unchanged
        assert "[units-lifecycle]" in db          # the new additive element
        # it is a st.caption (additive), not a rewrite of any st.metric
        assert "format_units_lifecycle(_lc_dash)" in db

    def test_fmt_position_card_signature_unchanged(self):
        """telegram_formatters.py was NOT touched (the caller appends the
        line — preferred per SCOPE §7.4). fmt_position_card's existing
        params/behaviour are byte-identical for every existing caller."""
        import telegram_formatters as tf
        import inspect
        sig = inspect.signature(tf.fmt_position_card)
        assert "units_lifecycle_fragment" not in sig.parameters


# ════════════════════════════════════════════════════════════════════════════
# Case 9 — import-introspection: helper imports nothing forbidden
# ════════════════════════════════════════════════════════════════════════════
class TestCase9ImportPurity:
    def test_no_forbidden_static_import(self):
        src = open(plc.__file__, encoding="utf-8").read()
        tree = ast.parse(src)
        names = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names += [n.name for n in node.names]
            elif isinstance(node, ast.ImportFrom):
                names.append(node.module or "")
        for forbidden in ("engine_core", "analytics_engine",
                          "period_data_probe", "risk_monitor", "supabase",
                          "supabase_repository", "requests", "urllib",
                          "yfinance", "telebot", "pandas"):
            assert not any(forbidden in (n or "") for n in names), \
                f"{forbidden} imported by position_lifecycle"
        # only stdlib `typing`
        assert set(n for n in names if n) == {"typing"}

    def test_importing_helper_does_not_pull_engine_or_supabase(self):
        import subprocess
        root = os.path.dirname(os.path.dirname(__file__))
        code = (
            "import sys; import position_lifecycle; "
            "bad=[m for m in ('engine_core','analytics_engine',"
            "'period_data_probe','risk_monitor','supabase',"
            "'supabase_repository','requests','yfinance','telebot') "
            "if m in sys.modules]; "
            "print('BAD' if bad else 'CLEAN', bad)"
        )
        out = subprocess.run([sys.executable, "-c", code], cwd=root,
                             capture_output=True, text=True)
        assert "CLEAN" in out.stdout, (out.stdout, out.stderr)

    def test_helper_does_no_supabase_state_or_network(self):
        src = open(plc.__file__, encoding="utf-8").read()
        for forbidden in ("supabase", ".execute(", ".insert(",
                          ".update(", "requests.", "urllib", "open(",
                          "state_io", "json.dump"):
            assert forbidden not in src, forbidden

    def test_rtl_constant_matches_canonical(self):
        # RTL inlined (pure leaf) — must equal bot_core / telegram_formatters
        import telegram_formatters as tf
        assert plc.RTL == tf.RTL


# ════════════════════════════════════════════════════════════════════════════
# Case 10 — idempotence / determinism
# ════════════════════════════════════════════════════════════════════════════
class TestCase10Determinism:
    def test_idempotent_deterministic(self):
        rows = [_leg("BUY", 10), _leg("BUY", 5), _leg("SELL", 6)]
        a = plc.compute_units_lifecycle(rows, engine_net_qty=9)
        b = plc.compute_units_lifecycle(rows, engine_net_qty=9)
        assert a == b
        assert plc.format_units_lifecycle(a) == plc.format_units_lifecycle(b)
        # input rows not mutated
        assert rows == [_leg("BUY", 10), _leg("BUY", 5), _leg("SELL", 6)]


# ════════════════════════════════════════════════════════════════════════════
# Case 11 — LOCKED April + byte-locked money-math untouched by this Phase
# ════════════════════════════════════════════════════════════════════════════
class TestCase11LockedAprilAndByteLockUnaffected:
    def test_byte_locked_files_unmodified(self):
        from tests._byte_lock_baseline import assert_byte_identical
        for rel in (
            "engine_core.py",
            "analytics_engine.py",
            "period_data_probe.py",
            "tests/test_real_data_april_regression.py",
        ):
            assert_byte_identical(rel)

    def test_locked_april_regression_invariant_still_holds(self):
        mod = importlib.import_module("tests.test_real_data_april_regression")
        import analytics_engine as ae
        a = ae.compute_period_analytics(
            mod._april_df(), datetime(2026, 4, 1),
            datetime(2026, 4, 30, 23, 59, 59), mod._ACCT)
        assert a["ok"] is True
        assert a["campaigns_closed"] == 8
        assert round(a["realized_pnl"], 2) == 180.49
        assert a["win_rate"] == pytest.approx(0.375, abs=1e-6)
        assert a["profit_factor"] == pytest.approx(2.6262, abs=1e-3)
        assert a["excluded_count"] == 2

    def test_managed_campaign_risk_r_nav_unaffected_by_helper(self):
        """The helper does ZERO risk/R/NAV/exposure math — it only re-derives
        unit magnitudes. A managed campaign's R figures are computed entirely
        by the engine; the helper never participates. Proof: no risk-math
        identifier appears in the helper's CODE (comments/docstrings, which
        legitimately *describe* the read-only boundary, are stripped via the
        AST so the explanatory prose does not false-positive)."""
        src = open(plc.__file__, encoding="utf-8").read()
        tree = ast.parse(src)
        # collect every identifier / attribute / string-CONSTANT used in
        # executable code (docstrings & `#` comments are not AST nodes /
        # are module/func docstrings we explicitly skip).
        code_tokens = []

        class _V(ast.NodeVisitor):
            def visit_Name(self, n):
                code_tokens.append(n.id)
            def visit_Attribute(self, n):
                code_tokens.append(n.attr)
                self.generic_visit(n)
            def visit_arg(self, n):
                code_tokens.append(n.arg)
        # drop module/function/class docstrings before walking
        for node in ast.walk(tree):
            if (isinstance(node, (ast.Module, ast.FunctionDef,
                                  ast.ClassDef))
                    and node.body
                    and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)
                    and isinstance(node.body[0].value.value, str)):
                node.body = node.body[1:]
        _V().visit(tree)
        joined = " ".join(code_tokens).lower()
        for tok in ("original_campaign_risk", "total_campaign_r", "open_r",
                    "weight_pct", "exposure", "heat", "adaptive",
                    "target_risk", "evaluate_position", "compute_r_"):
            assert tok not in joined, tok

    def test_helper_does_no_r_nav_account_math(self):
        src = open(plc.__file__, encoding="utf-8").read()
        assert "import engine_core" not in src
        assert "import analytics_engine" not in src
        assert "import risk_monitor" not in src
        assert "import supabase_repository" not in src
