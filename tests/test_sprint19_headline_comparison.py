"""
Sprint-19 Wave-2 — period-honest headline + period-over-period/vs-average
context + System-Health #1 fix + `_period_label` off-by-one.

Proves (MARK_SPRINT19_RULINGS.md §1–§3 + SPRINT19_DESIGN.md §1–§3):

  • §1 Realized byte-identical guard: analytics_engine.py git-diff EMPTY;
    _base_ctx realized keys + verdict/verdict_class identical WITH vs WITHOUT
    every new code path (headline + period_average + open_book_history).
  • §1 Headline switch: campaigns_closed==0 + live book ⇒ NO dominant
    "ללא עסקאות" on page 1; period-honest badge + promoted banner present;
    realized cards still truthfully "0"/"$0"/"0.0%", reframed + demoted; ALGO
    NOT in the headline badge / disc figures (#8).
  • §1d truly-empty (0 closed AND 0 open) ⇒ legacy verdict path byte-identical
    (no headline_open_book_mode, no suppression).
  • §2 compute_period_average: < N ⇒ baseline-pending (no mean); ≥ N ⇒ exact
    arithmetic mean of stored floats; profit_factor None skipped.
  • §2 compute_open_book_history: prev leg == compute_mark_delta; ALGO
    segregated; < N open_marks ⇒ baseline-pending token, never a number.
  • §2f on-demand renders comparison/average READ-ONLY yet NEVER snap_save /
    _mark_ran / _save_state.
  • §3a _build_system_health: never ✅ on temporary/rate_limit/fatal/unknown;
    raw IBKR-flex "הדוח לא נוצר" NEVER in sync_status; success → ✅ ok line.
  • §3b _period_label: monthly April "1–30 באפריל" (not 1–29); weekly
    Sun–Sat "3–9 במאי"; existing TestPeriodLabels still green.
  • Sprint-18 period-scoping + 920be95 + bcf32f5 + Sprint-16 intact.

`python -m pytest -q -p no:cacheprovider`.
"""
import json
import os
import subprocess
import sys
from datetime import datetime
from unittest.mock import patch, MagicMock

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Sprint-25 A1 — commit-state-AGNOSTIC byte-lock baseline (replaces the
# old `git diff -- analytics_engine.py` working-tree-vs-index source that
# was vacuously empty in CI). See tests/_byte_lock_baseline.py.
from tests._byte_lock_baseline import baseline_line_delta

for _mod in ("telebot", "telebot.types", "supabase", "dotenv"):
    sys.modules.setdefault(_mod, MagicMock())
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("TELEGRAM_ADMIN_ID", "12345")
os.environ.setdefault("SUPABASE_URL", "http://test")
os.environ.setdefault("SUPABASE_KEY", "test-key")

import report_renderer as rr
import report_open_book as rob
import report_scheduler as sched
from analytics_engine import compute_verdict

_REPO = os.path.dirname(os.path.dirname(__file__))

START = datetime(2025, 5, 4)
END = datetime(2025, 5, 10, 23, 59, 59)
_ACCOUNT_STATE = {"nav": 7921.0, "nav_source": "broker",
                  "freshness": "fresh", "risk_pct_input": 0.5}

_ANALYTICS_REALIZED = {
    "ok": True, "campaigns_closed": 5, "win_rate": 0.6,
    "expectancy_r": 0.42, "profit_factor": 2.1, "avg_win_r": 1.5,
    "avg_loss_r": -0.8, "total_r_net": 2.4, "realized_pnl": 480.0,
    "missing_stop_rate": 0.05, "oversized_rate": 0.10,
    "avg_r_per_day": 0.06, "setup_breakdown": {},
}
_ANALYTICS_EMPTY = {
    "ok": True, "campaigns_closed": 0, "win_rate": 0,
    "expectancy_r": 0, "profit_factor": 0, "total_r_net": 0,
    "realized_pnl": 0, "missing_stop_rate": 0, "oversized_rate": 0,
}

_REALIZED_CTX_KEYS = [
    "verdict", "verdict_class", "campaigns_closed", "win_rate",
    "expectancy_r", "profit_factor", "avg_win_r", "avg_loss_r",
    "total_r_net", "realized_pnl", "best_trade", "worst_trade",
    "setup_breakdown", "missing_stop_rate", "oversized_rate",
    "avg_r_per_day",
]


def _present_open_book(n_opened_total=2):
    return {
        "open_book_present": True,
        "open_book_disc": [
            {"symbol": "MRVL", "entry": 60.0, "current": 65.0, "qty": 30,
             "floating_pnl": 150.0, "realized_pnl": 0.0,
             "structure_r": 0.83, "account_r": 3.79,
             "structure_valid": True, "account_valid": True,
             "exposure_pct": 24.6, "price_is_fallback": False,
             "is_algo": False, "period_status": "opened_in_period",
             "period_label_he": "נפתחה בתקופה", "unrealized_label": "לא ממומש"},
        ],
        "open_book_algo": [
            {"symbol": "HOOD", "entry": 20.0, "current": 23.0, "qty": 50,
             "floating_pnl": 150.0, "realized_pnl": 0.0,
             "structure_r": 0.0, "account_r": 3.79,
             "structure_valid": False, "account_valid": True,
             "exposure_pct": 14.5, "price_is_fallback": False,
             "is_algo": True, "period_status": "opened_in_period",
             "period_label_he": "נפתחה בתקופה", "unrealized_label": "לא ממומש",
             "observation_label": "פיקוח בלבד · לא הוראה",
             "external_caveat": "מנוהל חיצונית — פיקוח, ללא הוראת Sentinel",
             "structure_r_token": "—"},
        ],
        "open_book_totals": {
            "floating_pnl_disc": 150.0, "floating_pnl_algo": 150.0,
            "exposure_pct_total": 39.1, "exposure_pct_disc": 24.6,
            "exposure_pct_algo": 14.5, "n_disc": 1, "n_algo": 1,
            "n_opened_disc": 1, "n_opened_algo": 1,
            "n_opened_total": n_opened_total,
        },
        "open_book_data_source": "Live",
        "open_book_price_fallback_syms": [],
        "open_book_error": None,
    }


def _capture_ctx(render_fn, **kw):
    """Render and return the Jinja2 ctx dict that the template received."""
    captured = {}

    def _fake_render(template_name, ctx, output_dir, filename):
        captured.update(ctx)
        return os.path.join(output_dir, filename.replace(".pdf", ".html"))

    with patch.object(rr, "_render", _fake_render), \
         patch.object(rr, "_generate_weekly_charts",
                      lambda *a, **k: rr._no_charts()), \
         patch.object(rr, "_generate_monthly_charts",
                      lambda *a, **k: rr._no_charts()):
        render_fn(**kw)
    return captured


# ════════════════════════════════════════════════════════════════════════════
# §1 — Realized byte-identical guard
# ════════════════════════════════════════════════════════════════════════════

class TestRealizedByteIdentical:
    def test_analytics_engine_git_diff_empty(self):
        """Sprint-19 made ZERO analytics edits. Sprint-20 Step-2 (Mark §5 gate
        item 3 / SPRINT20_DESIGN §2, APPROVED presentation/additive-only)
        makes the MINIMAL purely-additive `excluded_*_manual`/`_algo`
        partition of the SAME already-aggregated `excluded["net_pnl"]` — NO
        new R/NAV/campaign/Expectancy math and the countable/edge path stays
        byte-identical. The Sprint-19 byte-identical intent (realized number
        path untouched) is preserved by asserting every ADDED line is confined
        to the additive Sprint-20 split (no countable/edge/verdict line
        touched). The dedicated countable-byte-identical proof lives in
        tests/test_sprint20_wave2_excluded_disclosure.py.

        Sprint-24 Wave-2b (DEC-20260516-021): the founder, after Wave-2's
        honest report, explicitly authorized landing B1 (the twice-applied
        `bucket.apply(ec.is_stat_countable)` mask hoisted ONCE into a local
        `_cnt`, reused by `countable`/`excluded`) and B3 (the inlined
        numeric-coerce loop extracted into the pure top-level `_coerce_numeric`
        helper, called with the EXACT same tuple in the EXACT same order) as
        PROVABLE byte-identical no-op refactors — NOT math changes. The
        Sprint-19 "ZERO analytics edits" narrative is thereby SUPERSEDED for
        these TWO founder-authorized no-ops ONLY: they are admitted via the
        closed-literal `_SPRINT24_AUTHORIZED_REMOVED` / `_SPRINT24_AUTHORIZED`
        sets below and PROVEN byte-identical by
        tests/test_sprint24_b1b3_byte_identical.py (LOCKED April regression
        byte-identical + Sprint-22 tz-aware==tz-naive + the dedicated B1/B3
        partition/frame `.equals()` identity proofs). The lock can NEVER admit
        a Sprint-24 line without that paired byte-identical proof file
        existing AND collectible (asserted below). All Sprint-20/21/22 clauses
        are UNCHANGED — Wave-2b only ADDS the two closed Sprint-24 sets.

        Sprint-25 A1 (Ops F1 / Testing P0-1): the diff SOURCE is now the
        committed in-repo baseline (`tests/_byte_lock_baselines/
        analytics_engine.py.baseline`) vs the current ON-DISK file, NOT
        `git diff` (working-tree vs index, which was EMPTY on every clean
        CI checkout → this whole allowlist was vacuously satisfied where
        merges gate). The verdict is now IDENTICAL dirty / committed-clean
        / fresh CI checkout and FAILS on an unauthorized change to the
        *committed* analytics_engine.py. The authorized-allowlist semantics
        below are byte-for-byte unchanged — only the diff source moved to a
        commit-agnostic baseline (no widening)."""
        added, removed = baseline_line_delta("analytics_engine.py")
        # Tolerated "modified" lines — ALL are byte-identical-content brace
        # reflows where ONLY a trailing `}` moved so an authorized additive
        # block could be appended; nothing edge/countable is removed/modified:
        #   • Sprint-20: `"excluded_pnl": excluded_pnl}` → `,` + separate `}`
        #     for the additive `excluded_*_manual/_algo` split.
        #   • Sprint-21 WS-B (MARK_SPRINT21_RULINGS §B2 — additive-only,
        #     countable/excluded byte-identical): the two `_empty()` early
        #     returns `return {**_empty(), "target_risk_usd": t_risk}` got
        #     `, **_unlinked_keys` appended (content identical, brace moved),
        #     and `"excluded_pnl_algo": excluded_pnl_algo}` got its brace
        #     reflowed so the four `unlinked_*` keys append after it. The
        #     disjoint `unlinked_*` namespace NEVER touches a countable/edge
        #     value (proven byte-identical by tests/test_sprint21_wave2.py
        #     TestWSBByteIdentical).
        _TOL_REFLOW = (
            'return {**_empty(), "target_risk_usd": t_risk}',
            '"excluded_pnl_algo":     excluded_pnl_algo}',
        )
        # Sprint-24 Wave-2b (DEC-20260516-021) — founder-authorized PROVABLE
        # byte-identical no-ops. CLOSED literal set of the EXACT `.strip()`-ed
        # pre-edit lines B1 (mask hoisted once) + B3 (`_coerce_numeric`
        # extraction) remove/modify, derived VERBATIM from the real
        # `git diff -- analytics_engine.py` output (not guessed). These are
        # the ONLY non-additive removals admitted; their byte-identity is
        # PROVEN (strictly stronger than this token guard) by
        # tests/test_sprint24_b1b3_byte_identical.py.
        _SPRINT24_AUTHORIZED_REMOVED = frozenset({
            'for col in ("price", "quantity", "stop_loss", '
            '"initial_stop", "pnl_usd"):',
            'if col in df.columns:',
            'df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)',
            'countable = campaigns[bucket.apply(ec.is_stat_countable)]',
            'excluded  = campaigns[~bucket.apply(ec.is_stat_countable)]',
        })
        for ln in removed:
            s = ln.strip()
            if not s:
                continue
            if s in _TOL_REFLOW:
                continue
            if s in _SPRINT24_AUTHORIZED_REMOVED:
                continue
            assert ("excluded_pnl" in s and "excluded_pnl_" not in s), (
                "analytics_engine.py REMOVED/MODIFIED a non-additive line — "
                f"Sprint-20/21 must be additive-only:\n{ln!r}")
        # Every added line is either a comment or confined to the additive
        # Sprint-20 `excluded_*_manual`/`_algo` split OR the additive Sprint-21
        # WS-B `unlinked_*` NULL-campaign_id disclosure namespace
        # (MARK_SPRINT21_RULINGS §B2: "implement via a new unlinked_count/
        # unlinked_pnl pair ... additive ... countable/excluded byte-identical"
        # — exactly the precedent that admitted the Sprint-20 split tokens
        # below) OR the Sprint-22 single-point tz-normalization
        # (DEC-20260516-019 / MARK_SPRINT22_RULINGS §1.2/§6 gate item 1-2:
        # the `_to_naive` helper + ONE boundary-normalization block strip
        # tzinfo from `period_start`/`period_end` and guarantee `trade_date`
        # tz-naive — PURE datetime-operand normalization, PROVABLE no-op for
        # already-naive inputs per Mark §1.5, NO R/NAV/campaign/Expectancy
        # math; the LOCKED tests/test_real_data_april_regression.py stays
        # byte-identical and the tz-aware==tz-naive contract is proven by
        # tests/test_sprint22_tz_regression.py). Never a countable/edge/
        # verdict (win_rate/expectancy/profit_factor/total_r/real_pnl/
        # campaigns_closed) edit.
        _ALLOWED = ("#", "excl_algo", "excl_manual", "excluded_count_algo",
                    "excluded_pnl_algo", "excluded_count_manual",
                    "excluded_pnl_manual", '"excluded_count_manual"',
                    '"excluded_pnl_manual"', '"excluded_count_algo"',
                    '"excluded_pnl_algo"',
                    # Sprint-21 WS-B additive `unlinked_*` namespace (disjoint
                    # from countable/excluded; surfaced ONLY by _unlinked_ctx).
                    "_null_mask", "_unlinked", "_ul_cid", "_ul_inwin",
                    "_ul_side", "_ul_sell", "_ul_buy", "_unlinked_keys",
                    "unlinked_count", "unlinked_pnl", "unlinked_count_buy",
                    "unlinked_pnl_buy", '"unlinked_count"', '"unlinked_pnl"',
                    '"unlinked_count_buy"', '"unlinked_pnl_buy"',
                    )
        # Sprint-22 single-point tz-normalization (DEC-20260516-019 /
        # MARK_SPRINT22_RULINGS §1.2/§6 gate items 1-2): the authorized
        # change is exactly (a) the pure `_to_naive` helper and (b) the ONE
        # boundary-normalization block. Rather than enumerate every
        # free-text docstring line as a brittle token, derive the AUTHORIZED
        # added-line set from the live source between the documented
        # anchors. Any added line whose stripped content is a member of
        # this authorized region is admitted (pure datetime-operand
        # normalization — no R/NAV/campaign/Expectancy math; LOCKED
        # real-data regression byte-identical; tz-aware==tz-naive proven by
        # tests/test_sprint22_tz_regression.py).
        with open(os.path.join(_REPO, "analytics_engine.py")) as _f:
            _ae_src = _f.read().splitlines()

        # Sprint-25 A1 (Testing P0-2) — anchor-order hardening. The
        # Sprint-22 authorized region is DERIVED between four source
        # anchors. The OLD `next(...)` form (a) raised a bare,
        # message-less `StopIteration` (ERRORing the lock instead of
        # failing it with a clear message) if a legitimate helper reorder
        # moved `_to_naive` AFTER `_get_closed_campaigns` or moved the
        # Sprint-22 block comment, and (b) the `_to_naive` docstring at
        # L366 ALSO contains "Sprint-22 (DEC-20260516-019" — only source
        # ORDER kept the first match correct. Harden FAIL-CLOSED: locate
        # every anchor explicitly, ASSERT each exists and that the
        # documented ordering (`_to_naive` def < `_get_closed_campaigns`
        # def; the Sprint-22 *block* sentinel sits AFTER the `_to_naive`
        # def so its docstring mention can never be picked) actually
        # holds. A reorder now produces an explicit, actionable failure —
        # never a silent StopIteration and never a silently-widened span.
        def _first_idx(pred, lo=0, what=""):
            for _k in range(lo, len(_ae_src)):
                if pred(_ae_src[_k]):
                    return _k
            raise AssertionError(
                "Sprint-22 byte-lock anchor not found (fail-closed, "
                f"Sprint-25 A1 P0-2): {what}. analytics_engine.py was "
                "restructured — the governed Mark-gated baseline ritual "
                "must re-derive the authorized region; the lock refuses "
                "to silently widen or StopIteration-error.")

        _i_help = _first_idx(lambda l: l.startswith("def _to_naive("),
                             what="`def _to_naive(`")
        _j_help = _first_idx(
            lambda l: l.startswith("def _get_closed_campaigns("),
            lo=_i_help + 1, what="`def _get_closed_campaigns(` after _to_naive")
        # The Sprint-22 block sentinel ("Sprint-22 (DEC-20260516-019") and
        # its tz_localize boundary BOTH live inside `compute_period_
        # analytics`, which precedes the `_to_naive` def. A SECOND
        # occurrence of the sentinel is inside the `_to_naive` *docstring*
        # (~L366, AFTER `_i_help`). `_first_idx` (from index 0) finds the
        # FIRST hit = the in-function block — but ONLY if the documented
        # ordering holds. Assert it FAIL-CLOSED: the helper defs are
        # ordered, AND the first sentinel + its tz_localize boundary fully
        # precede the `_to_naive` def, so the docstring mention can NEVER
        # be mis-anchored and the span can never silently widen into the
        # helper defs.
        _i_blk = _first_idx(lambda l: "Sprint-22 (DEC-20260516-019" in l,
                            what="Sprint-22 block sentinel")
        _j_blk = _first_idx(
            lambda l: 'df["trade_date"] = df["trade_date"].dt.tz_localize'
            in l, lo=_i_blk + 1,
            what="tz_localize boundary line after the Sprint-22 sentinel")
        assert _i_help < _j_help, (
            "Sprint-25 A1 P0-2 fail-closed: `_to_naive` must be defined "
            "before `_get_closed_campaigns` for the derived authorized "
            "helper span to be valid; a reorder requires the governed "
            "baseline-regeneration ritual, not a silent re-derivation")
        assert _i_blk < _j_blk < _i_help, (
            "Sprint-25 A1 P0-2 fail-closed: the Sprint-22 in-function "
            "block sentinel + its tz_localize boundary must BOTH precede "
            "the `_to_naive` def (so the helper's docstring sentinel "
            "mention at ~L366 can never be the first match / the span can "
            "never widen into the helper defs); source restructured — "
            "governed baseline-regeneration ritual required")
        _SPRINT22_AUTHORIZED = {
            ln.strip() for ln in
            _ae_src[_i_help:_j_help] + _ae_src[_i_blk:_j_blk + 1]
            if ln.strip()}
        # Sprint-22 self-reference hardening (Mark consolidation ruling,
        # DEC-20260516-019): _SPRINT22_AUTHORIZED is DERIVED from live
        # source, so assert the authorized region ITSELF assigns no KPI/
        # countable value — even a self-derived allowlist can then never
        # admit a math/verdict edit smuggled inside the anchored spans
        # (prose mentioning "Expectancy"/"PnL" is fine: no `kpi =`/`["kpi"]`).
        import re as _re
        _FORBIDDEN_KPI = _re.compile(
            r'(\b(win_rate|expectancy|expectancy_r|profit_factor|total_r'
            r'|total_r_net|real_pnl|realized_pnl|campaigns_closed|net_pnl'
            r'|countable)\b\s*=(?!=)'
            r'|\["(win_rate|expectancy|expectancy_r|profit_factor|total_r'
            r'|total_r_net|real_pnl|realized_pnl|campaigns_closed|net_pnl'
            r'|countable)"\])')
        _viol = sorted(a for a in _SPRINT22_AUTHORIZED
                       if _FORBIDDEN_KPI.search(a))
        assert not _viol, (
            "Sprint-22 authorized region must not assign any KPI/countable "
            f"value (self-reference hardening): {_viol}")
        # Sprint-24 Wave-2b (DEC-20260516-021) — founder-authorized PROVABLE
        # byte-identical no-ops. CLOSED literal set of the EXACT `.strip()`-ed
        # lines B1 + B3 ADD, derived VERBATIM from the real `git diff` output
        # (NOT derived/open like Sprint-22 — a fixed, auditable allowlist).
        # B1 re-binds `countable`/`excluded` to the SAME value via the hoisted
        # `_cnt`; we deliberately do NOT run `_FORBIDDEN_KPI` over this set
        # because the dedicated full-frame/partition `.equals()` identity proof
        # in tests/test_sprint24_b1b3_byte_identical.py is STRICTLY STRONGER
        # than the token proxy and is the real guarantee.
        _SPRINT24_AUTHORIZED = frozenset({
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
        # Sprint-24 self-reference hardening: the closed `_SPRINT24_*` sets can
        # NEVER exist without their paired NAMED Ruling-3 byte-identical proof.
        # Assert the proof file exists AND is collectible AND defines the named
        # proof class (so a future edit cannot keep the allowlist while
        # deleting/gutting the proof to "go green").
        _proof_path = os.path.join(
            _REPO, "tests", "test_sprint24_b1b3_byte_identical.py")
        assert os.path.isfile(_proof_path), (
            "Sprint-24 B1/B3 allowlist requires its paired byte-identical "
            "proof tests/test_sprint24_b1b3_byte_identical.py to exist")
        _proof_src = open(_proof_path).read()
        assert "class TestSprint24B1B3ByteIdentical" in _proof_src, (
            "Sprint-24 proof file must define the named byte-identical proof")
        # Sprint-25 A1 (Testing P1-3) — bind the proof BODY, not just the
        # class NAME. The OLD check was a substring match on the class
        # name + collectibility, so the `.equals()`/regression oracle
        # bodies could be gutted to `assert True` while the lock stayed
        # green ("strictly stronger than the token proxy" claim hollow).
        # Parse the proof AST and assert the load-bearing oracle methods
        # exist AND that their bodies still contain the binding
        # `.equals()` / locked-headline assertions — an oracle hollowed
        # to `assert True` (or with its `.equals()` removed) now FAILS
        # this lock.
        import ast as _ast
        _ptree = _ast.parse(_proof_src)
        _pcls = next((n for n in _ast.walk(_ptree)
                      if isinstance(n, _ast.ClassDef)
                      and n.name == "TestSprint24B1B3ByteIdentical"), None)
        assert _pcls is not None, (
            "Sprint-24 proof class must be AST-parseable")
        _pmethods = {m.name: m for m in _pcls.body
                     if isinstance(m, _ast.FunctionDef)}
        # The four load-bearing oracles + the substring each MUST still
        # contain in its source (the actual byte-identity / locked-number
        # assertion — not a gutted `assert True`).
        _REQUIRED_ORACLE_BODY = {
            "test_b1_mask_once_partition_equals_twice_applied":
                ("new_countable.equals(old_countable)",
                 "new_excluded.equals(old_excluded)"),
            "test_b3_coerce_numeric_full_frame_equals_inlined":
                ("helper_out.equals(oracle_out)",),
            "test_locked_april_regression_byte_identical_post_b1b3":
                ('a["campaigns_closed"] == 8', "180.49"),
            "test_sprint22_tz_aware_equals_tz_naive_post_b1b3":
                ("aware[k] == naive[k]",),
        }
        for _mname, _needles in _REQUIRED_ORACLE_BODY.items():
            assert _mname in _pmethods, (
                f"Sprint-24 proof must define oracle {_mname!r} "
                "(Sprint-25 A1 P1-3 — proof-body binding)")
            _mbody = _ast.get_source_segment(_proof_src, _pmethods[_mname])
            assert _mbody is not None
            for _needle in _needles:
                assert _needle in _mbody, (
                    f"Sprint-24 oracle {_mname!r} no longer contains its "
                    f"binding assertion {_needle!r} — proof body gutted "
                    "(Sprint-25 A1 P1-3 fail-closed). A hollowed "
                    "`assert True` oracle can NOT keep this lock green.")
        _proof_collect = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
             "--collect-only",
             "tests/test_sprint24_b1b3_byte_identical.py"],
            cwd=_REPO, capture_output=True, text=True)
        assert _proof_collect.returncode == 0, (
            "Sprint-24 byte-identical proof must be collectible:\n"
            f"{_proof_collect.stdout}\n{_proof_collect.stderr}")
        for ln in added:
            s = ln.strip()
            if not s or s == "}":
                # bare `}` = the reflowed closing brace of the early-return
                # dict (its content keys are added separately, all in _ALLOWED)
                continue
            # The reflowed `"excluded_pnl": excluded_pnl,` counterpart of the
            # tolerated removed `...excluded_pnl}` line — key/value identical,
            # only the trailing brace moved (still additive in effect).
            if "excluded_pnl" in s and "excluded_pnl_" not in s:
                continue
            if s in _SPRINT22_AUTHORIZED:
                continue
            if s in _SPRINT24_AUTHORIZED:
                continue
            assert any(tok in s for tok in _ALLOWED), (
                f"analytics_engine.py added a NON-additive line outside the "
                f"Sprint-20 excluded_* / Sprint-21 unlinked_* / Sprint-22 "
                f"tz-normalization / Sprint-24 B1+B3 authorized regions: "
                f"{ln!r}")

    def test_realized_ctx_identical_with_and_without_new_paths(self):
        """_base_ctx realized keys + verdict/verdict_class byte-identical
        WITH vs WITHOUT open_book/period_average/open_book_history."""
        base = _capture_ctx(
            rr.render_weekly, analytics=_ANALYTICS_REALIZED,
            account_state=_ACCOUNT_STATE, period_start=START, period_end=END)
        ob = _present_open_book()
        avg = rr.compute_period_average(
            [{"win_rate": 0.5, "expectancy_r": 0.3, "profit_factor": 1.5,
              "total_r_net": 1.0, "realized_pnl": 100.0,
              "missing_stop_rate": 0.0, "oversized_rate": 0.0,
              "avg_r_per_day": 0.02}] * 4)
        obh = rob.compute_open_book_history(ob, [], None)
        full = _capture_ctx(
            rr.render_weekly, analytics=_ANALYTICS_REALIZED,
            account_state=_ACCOUNT_STATE, period_start=START, period_end=END,
            open_book=ob, mark_delta=rob.compute_mark_delta(ob, None),
            period_average=avg, open_book_history=obh)
        for k in _REALIZED_CTX_KEYS:
            assert base[k] == full[k], f"realized ctx key {k} drifted"
        # The new seams emit their namespaced keys ALWAYS (additive by
        # construction — present even in the no-open_book base path), and
        # those keys never collide with a realized _base_ctx key.
        ns = {k for k in full
              if k.startswith(("headline_", "cmp_", "obcmp_"))}
        assert ns, "expected additive headline_/cmp_/obcmp_ keys present"
        assert not (ns & set(_REALIZED_CTX_KEYS)), \
            "namespaced ctx collided with a realized key"
        # Realized data present (campaigns_closed=5) ⇒ headline mode False in
        # BOTH paths; the realized keys above are byte-identical regardless —
        # proof the additive seam never mutates the realized ctx.
        assert base["headline_open_book_mode"] is False
        assert full["headline_open_book_mode"] is False

    def test_verdict_value_unchanged_under_trigger(self):
        """compute_verdict still returns the 920be95 string; the headline
        seam never mutates it."""
        v, vc = compute_verdict(_ANALYTICS_EMPTY)
        assert v == "שבוע ללא עסקאות" and vc == "neutral"
        vm, vcm = compute_verdict(_ANALYTICS_EMPTY, period_word="חודש")
        assert vm == "חודש ללא עסקאות" and vcm == "neutral"


# ════════════════════════════════════════════════════════════════════════════
# §1 — Period-honest headline switch
# ════════════════════════════════════════════════════════════════════════════

class TestHeadlineSwitch:
    def test_zero_closed_plus_live_book_triggers_honest_headline(self):
        ob = _present_open_book(n_opened_total=2)
        ctx = _capture_ctx(
            rr.render_weekly, analytics=_ANALYTICS_EMPTY,
            account_state=_ACCOUNT_STATE, period_start=START, period_end=END,
            open_book=ob, mark_delta=rob.compute_mark_delta(ob, None))
        assert ctx["headline_open_book_mode"] is True
        assert ctx["headline_badge_text"] == (
            "📌 שבוע ללא סגירות — ספר פתוח פעיל")
        assert ctx["headline_badge_class"] == "neutral"
        # Realized cards still truthful 0 — never hidden / spun.
        assert ctx["campaigns_closed"] == 0
        assert ctx["realized_pnl"] == 0
        assert ctx["win_rate"] == 0
        assert ctx["headline_realized_pnl_label"] == "רווח ממומש (0 בתקופה)"
        assert ctx["headline_realized_subheading"] == (
            "📉 ביצועים ממומשים (0 קמפיינים נסגרו בתקופה)")

    def test_monthly_headline_uses_chodesh(self):
        ob = _present_open_book()
        ctx = _capture_ctx(
            rr.render_monthly, analytics=_ANALYTICS_EMPTY,
            account_state=_ACCOUNT_STATE,
            period_start=datetime(2026, 4, 1),
            period_end=datetime(2026, 4, 30, 23, 59, 59),
            open_book=ob, mark_delta=rob.compute_mark_delta(ob, None))
        assert ctx["headline_badge_text"] == (
            "📌 חודש ללא סגירות — ספר פתוח פעיל")

    def test_rendered_html_has_no_lo_iskaot_on_page1_when_book_present(self):
        """The literal 'ללא עסקאות' must NOT appear in the rendered page-1
        badge when a live book spanned the period."""
        ob = _present_open_book()
        with patch.object(rr, "_generate_weekly_charts",
                          lambda *a, **k: rr._no_charts()), \
             patch.object(rr, "_load_weasyprint", lambda: None), \
             patch.object(rr, "_REPORTS_DIR", "/tmp/s19_reports"):
            html_path = rr.render_weekly(
                analytics=_ANALYTICS_EMPTY, account_state=_ACCOUNT_STATE,
                period_start=START, period_end=END, open_book=ob,
                mark_delta=rob.compute_mark_delta(ob, None))
        html = open(html_path, encoding="utf-8").read()
        page1 = html.split("PAGE 2")[0]
        assert "ללא עסקאות" not in page1
        assert "📌 שבוע ללא סגירות — ספר פתוח פעיל" in page1
        # Honest banner present; realized still truthful 0.
        assert 'אין ביצועים' in page1
        assert "רווח ממומש (0 בתקופה)" in page1
        assert "📉 ביצועים ממומשים (0 קמפיינים נסגרו בתקופה)" in page1

    def test_algo_not_in_headline_badge_or_disc_figures(self):
        ob = _present_open_book()
        ctx = _capture_ctx(
            rr.render_weekly, analytics=_ANALYTICS_EMPTY,
            account_state=_ACCOUNT_STATE, period_start=START, period_end=END,
            open_book=ob, mark_delta=rob.compute_mark_delta(ob, None))
        badge = ctx["headline_badge_text"]
        assert "ALGO" not in badge and "HOOD" not in badge
        # The disc banner line carries only the disc floating ($+150 — Mark's
        # verbatim "${:+,.0f}" format), never the disc+algo sum ($+300).
        lines = ctx["headline_banner_lines"]
        disc_line = [ln for ln in lines if "דיסקרציוני" in ln][0]
        assert "$+150" in disc_line and "$+300" not in disc_line
        # ALGO is on its OWN segregated observation-only line.
        algo_line = [ln for ln in lines if "ALGO" in ln]
        assert algo_line and "פיקוח בלבד · לא הוראה" in algo_line[0]
        assert "$+150" in algo_line[0]

    def test_truly_empty_keeps_legacy_verdict_path(self):
        """0 closed AND 0 open ⇒ headline_open_book_mode False, legacy
        verdict badge byte-identical (no suppression, §1d)."""
        empty_ob = rob.build_open_book(pd.DataFrame(), _ACCOUNT_STATE)
        assert empty_ob["open_book_present"] is False
        ctx = _capture_ctx(
            rr.render_weekly, analytics=_ANALYTICS_EMPTY,
            account_state=_ACCOUNT_STATE, period_start=START, period_end=END,
            open_book=empty_ob)
        assert ctx["headline_open_book_mode"] is False
        assert ctx["verdict"] == "שבוע ללא עסקאות"
        assert ctx["verdict_class"] == "neutral"

    def test_legacy_open_book_none_caller_no_headline_mode(self):
        ctx = _capture_ctx(
            rr.render_weekly, analytics=_ANALYTICS_EMPTY,
            account_state=_ACCOUNT_STATE, period_start=START, period_end=END)
        assert ctx["headline_open_book_mode"] is False
        assert ctx["verdict"] == "שבוע ללא עסקאות"

    def test_nonzero_campaigns_never_triggers_headline(self):
        ob = _present_open_book()
        ctx = _capture_ctx(
            rr.render_weekly, analytics=_ANALYTICS_REALIZED,
            account_state=_ACCOUNT_STATE, period_start=START, period_end=END,
            open_book=ob)
        assert ctx["headline_open_book_mode"] is False


# ════════════════════════════════════════════════════════════════════════════
# §2 — compute_period_average (realized vs-average, baseline-pending)
# ════════════════════════════════════════════════════════════════════════════

class TestComputePeriodAverage:
    def _snap(self, **kw):
        base = {"win_rate": 0.5, "expectancy_r": 0.3, "profit_factor": 1.5,
                "total_r_net": 1.0, "realized_pnl": 100.0,
                "missing_stop_rate": 0.1, "oversized_rate": 0.2,
                "avg_r_per_day": 0.02}
        base.update(kw)
        return base

    def test_below_N_is_baseline_pending_never_a_mean(self):
        for k in (0, 1, 2):
            r = rr.compute_period_average([self._snap()] * k)
            assert r["available"] is False
            assert r["metrics"] == {}
            assert r["n_have"] == k
            assert r["baseline_pending_text"] == (
                f"📊 מול ממוצע: — · ממתין ל-3 תקופות בסיס (קיימות {k} מתוך 3)")

    def test_at_N_exact_arithmetic_mean(self):
        snaps = [self._snap(total_r_net=1.0, win_rate=0.4),
                 self._snap(total_r_net=2.0, win_rate=0.6),
                 self._snap(total_r_net=3.0, win_rate=0.5)]
        r = rr.compute_period_average(snaps, n=3)
        assert r["available"] is True
        assert r["metrics"]["total_r_net"] == pytest.approx(2.0)
        assert r["metrics"]["win_rate"] == pytest.approx(0.5)

    def test_profit_factor_none_skipped_per_metric(self):
        snaps = [self._snap(profit_factor=None),
                 self._snap(profit_factor=2.0),
                 self._snap(profit_factor=4.0)]
        r = rr.compute_period_average(snaps, n=3)
        # None skipped → mean of the two finite values only.
        assert r["metrics"]["profit_factor"] == pytest.approx(3.0)

    def test_uses_only_first_n_newest(self):
        snaps = [self._snap(total_r_net=10.0)] * 3 + \
                [self._snap(total_r_net=0.0)] * 5
        r = rr.compute_period_average(snaps, n=3)
        assert r["metrics"]["total_r_net"] == pytest.approx(10.0)


# ════════════════════════════════════════════════════════════════════════════
# §2 — compute_open_book_history (open-book period-over-period + vs-average)
# ════════════════════════════════════════════════════════════════════════════

class TestComputeOpenBookHistory:
    def _mark(self, disc, algo, expo=30.0):
        return {"open_marks": {"floating_pnl_disc": disc,
                               "floating_pnl_algo": algo,
                               "open_exposure_pct": expo}}

    def test_prev_leg_equals_compute_mark_delta(self):
        ob = _present_open_book()
        prev = self._mark(100.0, 50.0)
        obh = rob.compute_open_book_history(ob, [], prev)
        md = rob.compute_mark_delta(ob, prev)
        assert obh["prev_delta"]["text"] == md["text"]

    def test_below_N_open_marks_baseline_pending_never_number(self):
        ob = _present_open_book()
        for k in (0, 1, 2):
            snaps = [self._mark(10.0, 5.0)] * k
            obh = rob.compute_open_book_history(ob, snaps, None, n=3)
            assert obh["available"] is False
            assert obh["avg_floating_disc"] is None
            assert obh["baseline_pending_text"] == (
                f"📊 מול ממוצע (לא ממומש): — · "
                f"ממתין ל-3 תקופות בסיס (קיימות {k} מתוך 3)")

    def test_at_N_segregates_algo_from_disc(self):
        ob = _present_open_book()
        snaps = [self._mark(100.0, 50.0), self._mark(200.0, 60.0),
                 self._mark(300.0, 70.0)]
        obh = rob.compute_open_book_history(ob, snaps, None, n=3)
        assert obh["available"] is True
        assert obh["avg_floating_disc"] == pytest.approx(200.0)
        assert obh["avg_floating_algo"] == pytest.approx(60.0)
        # ALGO never folded into the disc figure / disc text.
        assert "200" in obh["avg_text"] and "ALGO" not in obh["avg_text"]
        assert "ALGO" in obh["avg_algo_text"]
        assert "פיקוח בלבד · לא הוראה" in obh["avg_algo_text"]

    def test_old_snapshots_without_open_marks_skipped(self):
        ob = _present_open_book()
        snaps = [{"campaigns_closed": 3}, {"campaigns_closed": 1},
                 self._mark(100.0, 0.0)]
        obh = rob.compute_open_book_history(ob, snaps, None, n=3)
        # Only 1 open_marks-bearing → still baseline-pending.
        assert obh["available"] is False
        assert obh["n_have"] == 1


# ════════════════════════════════════════════════════════════════════════════
# §2f — on-demand renders comparison/average READ-ONLY, never snap_save
# ════════════════════════════════════════════════════════════════════════════

class TestOnDemandNoSnapSave:
    def test_on_demand_reads_history_but_never_writes(self, tmp_path):
        import report_on_demand as rod
        import report_snapshot_store as rss

        def _boom_save(*a, **k):
            raise AssertionError("on-demand MUST NOT call snap_save")

        def _boom_mark(*a, **k):
            raise AssertionError("on-demand MUST NOT _mark_ran")

        def _boom_state(*a, **k):
            raise AssertionError("on-demand MUST NOT _save_state")

        # Prior snapshot exists in an isolated store → comparison populated.
        with patch.object(rss, "_BASE_DIR", str(tmp_path)):
            from datetime import datetime as _dt
            rss.save("weekly", _dt(2025, 4, 26), _dt(2025, 5, 2),
                     _ANALYTICS_REALIZED, _ACCOUNT_STATE, "/x.pdf",
                     open_book=_present_open_book())
            with patch.object(rss, "save", _boom_save), \
                 patch.object(sched, "_mark_ran", _boom_mark), \
                 patch.object(sched, "_save_state", _boom_state), \
                 patch.object(sched, "_fetch_trades_df",
                              lambda *a, **k: pd.DataFrame()), \
                 patch("account_state.load", lambda: _ACCOUNT_STATE), \
                 patch("report_delivery.deliver_report",
                       lambda *a, **k: {"summary_ok": True, "pdf_ok": False}):
                res = rod.run_on_demand(
                    "weekly", now=datetime(2025, 5, 14),
                    token="t", chat_id="c")
        assert res["ok"] is True


# ════════════════════════════════════════════════════════════════════════════
# §3a — System-Health honest mapping (no ✅ on non-ok; no raw flex string)
# ════════════════════════════════════════════════════════════════════════════

class TestSystemHealthHonesty:
    def _health_with(self, payload, tmp_path):
        from unittest.mock import mock_open
        m = mock_open(read_data=json.dumps(payload))
        with patch("builtins.open", m):
            return sched._build_system_health()

    def test_temporary_never_emoji_ok_nor_raw_flex_string(self, tmp_path):
        h = self._health_with(
            {"status": "temporary",
             "message": "הדוח לא נוצר כרגע — ניסיון מאוחר יותר",
             "code": 1001}, tmp_path)
        s = h["sync_status"]
        assert not s.startswith("✅")
        assert "✅" not in s
        assert "הדוח לא נוצר" not in s
        assert s == ("⏳ סנכרון IBKR — עיכוב זמני בצד IBKR "
                     "(לא משפיע על דוח זה)")

    def test_rate_limit_no_check_mark(self, tmp_path):
        h = self._health_with({"status": "rate_limit",
                               "message": "יותר מדי בקשות"}, tmp_path)
        assert "✅" not in h["sync_status"]

    def test_fatal_no_check_mark(self, tmp_path):
        h = self._health_with({"status": "fatal",
                               "message": "Token פג תוקף"}, tmp_path)
        s = h["sync_status"]
        assert "✅" not in s and s.startswith("🔴")

    def test_success_uses_ok_line(self, tmp_path):
        h = self._health_with({"status": "success", "message": "ok"},
                              tmp_path)
        assert h["sync_status"] == "✅ סנכרון IBKR תקין"

    def test_unknown_and_missing_file_no_check_mark(self, tmp_path):
        h = self._health_with({"status": "weird"}, tmp_path)
        assert "✅" not in h["sync_status"]
        assert h["sync_status"] == "⚠️ סנכרון IBKR — מצב לא ידוע"
        # Missing file path → unknown, never ✅.
        with patch("builtins.open", side_effect=FileNotFoundError()):
            h2 = sched._build_system_health()
        assert "✅" not in h2["sync_status"]
        assert h2["sync_status"] == "⚠️ סנכרון IBKR — מצב לא ידוע"


# ════════════════════════════════════════════════════════════════════════════
# §3b — _period_label inclusive end (drop the off-by-one in BOTH branches)
# ════════════════════════════════════════════════════════════════════════════

class TestPeriodLabelInclusiveEnd:
    def test_monthly_april_reads_1_to_30(self):
        ps, pe = sched._monthly_period(datetime(2026, 5, 1))
        # period_end is inclusive last instant: 2026-04-30 23:59:59.
        assert (pe.month, pe.day) == (4, 30)
        label = rr._period_label(ps, pe)
        assert label == "1–30 באפריל 2026"
        assert "1–29" not in label

    def test_monthly_31_day_month(self):
        ps, pe = sched._monthly_period(datetime(2026, 4, 1))  # → March
        assert rr._period_label(ps, pe) == "1–31 במרץ 2026"

    def test_monthly_february_non_leap_and_leap(self):
        ps, pe = sched._monthly_period(datetime(2026, 3, 1))  # Feb 2026 (28)
        assert rr._period_label(ps, pe) == "1–28 בפברואר 2026"
        ps2, pe2 = sched._monthly_period(datetime(2024, 3, 1))  # Feb 2024 (29)
        assert rr._period_label(ps2, pe2) == "1–29 בפברואר 2024"

    def test_weekly_sun_to_sat_reads_3_to_9_be_mai(self):
        # Saturday 2025-05-10 → week Sun 04 .. Sat 10. Founder's report
        # window "3–9 במאי" corresponds to Sat 2025-05-09's week.
        ps, pe = sched._weekly_period(datetime(2025, 5, 9, 8, 30))
        assert (ps.day, pe.day) == (3, 9)
        assert rr._period_label(ps, pe) == "3–9 במאי 2025"

    def test_existing_period_label_tests_still_green(self):
        # The legacy non-empty / month-name / year invariants must hold.
        for m in range(1, 13):
            lbl = rr._period_label(datetime(2025, m, 1),
                                   datetime(2025, m, 28))
            assert isinstance(lbl, str) and len(lbl) > 0
        cross = rr._period_label(datetime(2025, 1, 27),
                                 datetime(2025, 2, 3))
        assert "ינואר" in cross and "פברואר" in cross


# ════════════════════════════════════════════════════════════════════════════
# §2 — template surfacing (vs-average column / baseline-pending; open-book)
# ════════════════════════════════════════════════════════════════════════════

class TestComparisonTemplateWiring:
    def test_weekly_ctx_carries_namespaced_cmp_keys(self):
        avg = rr.compute_period_average(
            [{"win_rate": 0.5, "expectancy_r": 0.3, "profit_factor": 1.5,
              "total_r_net": 1.0, "realized_pnl": 100.0,
              "missing_stop_rate": 0.0, "oversized_rate": 0.0,
              "avg_r_per_day": 0.02}] * 4)
        ctx = _capture_ctx(
            rr.render_weekly, analytics=_ANALYTICS_REALIZED,
            account_state=_ACCOUNT_STATE, period_start=START, period_end=END,
            period_average=avg)
        assert ctx["cmp_vs_avg_available"] is True
        assert "מול תקופה קודמת (ממומש בלבד)" == ctx["cmp_vs_prev_label"]
        assert "שבועות" in ctx["cmp_vs_avg_label"]
        assert "total_r_net" in ctx["cmp_vs_avg"]

    def test_baseline_pending_when_below_N(self):
        avg = rr.compute_period_average([])  # 0 priors
        ctx = _capture_ctx(
            rr.render_weekly, analytics=_ANALYTICS_REALIZED,
            account_state=_ACCOUNT_STATE, period_start=START, period_end=END,
            period_average=avg)
        assert ctx["cmp_vs_avg_available"] is False
        assert ctx["cmp_vs_avg_baseline_pending"] == (
            "📊 מול ממוצע: — · ממתין ל-3 תקופות בסיס (קיימות 0 מתוך 3)")

    def test_summary_text_appends_average_without_touching_realized(self):
        avg = rr.compute_period_average(
            [{"win_rate": 0.5, "expectancy_r": 0.3, "profit_factor": 1.5,
              "total_r_net": 1.0, "realized_pnl": 100.0,
              "missing_stop_rate": 0.0, "oversized_rate": 0.0,
              "avg_r_per_day": 0.02}] * 3)
        base = rr.build_summary_text(_ANALYTICS_REALIZED, "lbl", "weekly")
        with_avg = rr.build_summary_text(
            _ANALYTICS_REALIZED, "lbl", "weekly", period_average=avg)
        # Realized KPI lines unchanged (the base lines are a prefix subset).
        for line in base.split("\n"):
            if line.startswith(("📊 קמפיינים", "💰 Realized", "🎯 Expectancy",
                                "⚙️ Missing")):
                assert line in with_avg
        assert "מול ממוצע" in with_avg
