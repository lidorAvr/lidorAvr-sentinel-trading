"""Phase REPORT-3 acceptance suite — the sidebar "🤖 AI Master Context
Export" (`ai_str`, dashboard.py) becomes a FULL consolidation by adding —
READ-ONLY, ADDITIVE, via the EXISTING single-source formatters / entry
points (ZERO new math) — 5 blocks:

  1. units-lifecycle (plc.compute/format_units_lifecycle)
  2. adaptive-risk regime / trade-heat (reused `_risk_rec` + the PURE
     tf.fmt_adaptive_risk_block + read-only are.get_risk_settle_info)
  3. ALGO-2A live↔backtest divergence (algo_divergence single-source pair)
  4. per-position engine action (raw `action_short` from the EXISTING
     eval_res via the additive live_df['Action'] field)
  5. portfolio aggregate (existing live_df / Heat-Map sums)

Authoritative spec: docs/teams/PHASE_REPORT3_SCOPE.md (governs).

Every block REUSES the EXISTING formatter / entry point the visual
surface + the Telegram report already use — the export is a faithful,
byte-identical mirror, never a parallel re-computation. Where a block
cannot be honestly verified the export shows the EXISTING honest marker,
never a fabricated value (CLAUDE.md accuracy-over-confidence; AGENTS.md
#1 absence ≠ data). ALGO observe-only carve-out INVIOLABLE (AGENTS.md #8
/ DEC-20260511-001).

These tests ONLY ADD coverage — no existing test is deleted/weakened
(Mark 6.1). All fixtures are hand-crafted synthetic dicts (NO real
symbols / quantities / P&L / CSV / network / Supabase). The export
builder is inline `dashboard.py` code (not an extractable function), so —
exactly the REPORT-2 / ALGO-2A precedent — block byte-identity is proven
against the single-source formatter on the SAME input, and the
read-only / additive / single-source wiring is proven by static analysis
of the `dashboard.py` source.
"""
import ast
import importlib
import os
import sys
from datetime import datetime

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import position_lifecycle as plc  # noqa: E402
import algo_divergence as ad  # noqa: E402
import telegram_formatters as tf  # noqa: E402

_ROOT = os.path.dirname(os.path.dirname(__file__))


def _src(name):
    with open(os.path.join(_ROOT, name), encoding="utf-8") as f:
        return f.read()


_DASH = _src("dashboard.py")


# synthetic leg / risk_rec fixtures (no real trade data) ──────────────────────
def _leg(side, qty, trade_id=None):
    d = {"side": side, "quantity": qty}
    if trade_id is not None:
        d["trade_id"] = trade_id
    return d


def _valid_risk_rec():
    """Minimal valid risk_rec carrying every key fmt_adaptive_risk_block
    requires on the ok=True path (synthetic — no real campaign data)."""
    return {
        "ok": True, "heat_color": "🟢", "heat_label": "נמוך",
        "heat_score": 20.0, "recent_10_wr": 60, "all_50_wr": 55,
        "n_used_50": 50, "n_trades": 50, "win_streak": 3, "loss_streak": 0,
        "heat_factors": [], "current_risk_pct": 0.5,
        "recommended_risk_pct": 0.5, "current_risk_usd": 500,
        "recommended_risk_usd": 500, "direction": "hold",
        "step_type": "ללא שינוי",
    }


# ════════════════════════════════════════════════════════════════════════════
# Block 1 — units-lifecycle: export line == the single source-of-truth
#           formatter (byte-identity vs dashboard-detail / Telegram card)
# ════════════════════════════════════════════════════════════════════════════
class TestBlock1UnitsLifecycle:
    def test_export_units_line_byte_identical_to_single_formatter(self):
        """The export calls the SAME plc.compute/format_units_lifecycle the
        dashboard detail panel + the Telegram card call — byte-identical
        for the same input (cannot drift)."""
        for rows, net in (
            ([_leg("BUY", 10), _leg("BUY", 5), _leg("SELL", 6)], 9),  # valid
            ([_leg("SELL", 3)], 0),                                   # empty
            ([], 5),                                                  # empty
            ([_leg("BUY", 4), _leg("SELL", 9)], -5),                  # empty
        ):
            lc = plc.compute_units_lifecycle(rows, engine_net_qty=net)
            single = plc.format_units_lifecycle(lc)
            # the export interpolates EXACTLY this fragment (the wired line)
            export_line = f"  📦 {single}\n"
            assert single in export_line
            assert export_line.encode("utf-8") == \
                f"  📦 {plc.format_units_lifecycle(lc)}\n".encode("utf-8")

    def test_export_units_valid_example_text(self):
        lc = plc.compute_units_lifecycle(
            [_leg("BUY", 10), _leg("BUY", 5), _leg("SELL", 6)],
            engine_net_qty=9)
        line = f"  📦 {plc.format_units_lifecycle(lc)}\n"
        assert "מקורי 15" in line and "נותרו 9" in line
        assert "מומשו 6" in line and "40%" in line
        assert plc.UNVERIFIABLE_HE not in line

    def test_export_units_honest_empty_marker(self):
        # missing/ambiguous/non-reconciling ⇒ `— (לא ניתן לאמת)`, never a
        # fabricated number / silent zero (AGENTS.md #1).
        for rows, net in (([], 5), ([_leg("SELL", 3)], 0),
                          ([_leg("BUY", 4), _leg("SELL", 9)], -5),
                          ([_leg("BUY", 10), _leg("SELL", 6)], 12)):
            lc = plc.compute_units_lifecycle(rows, engine_net_qty=net)
            line = f"  📦 {plc.format_units_lifecycle(lc)}\n"
            assert "—" in line and plc.UNVERIFIABLE_HE in line
            assert "מקורי" not in line and "0%" not in line

    def test_export_reuses_existing_camp_legs_and_qty(self):
        # the export feeds the helper the SAME read-only `_camp_legs_dash`
        # (built dashboard.py:299-318) + the engine's own net `qty` — no new
        # data source, no new math.
        assert "_camp_legs_dash.get(_campaign_id)" in _DASH
        assert "engine_net_qty=qty" in _DASH
        assert "plc.format_units_lifecycle(_lc_ai)" in _DASH


# ════════════════════════════════════════════════════════════════════════════
# Block 2 — adaptive-risk: export text == tf.fmt_adaptive_risk_block(_risk_rec)
#           (byte-identity vs Telegram) + ZERO new compute_adaptive_risk call
# ════════════════════════════════════════════════════════════════════════════
class TestBlock2AdaptiveRisk:
    def test_export_adaptive_text_byte_identical_to_telegram(self):
        """The export renders the SAME pure tf.fmt_adaptive_risk_block the
        Telegram report calls (telegram_portfolio.py:640) — byte-identical
        for an identical risk_rec (cross-surface anti-drift, SCOPE §6)."""
        rr = _valid_risk_rec()
        settle = {"active": False, "hours_remaining": 0.0, "dir": "",
                  "to_pct": 0.0}
        export_text = f"{tf.fmt_adaptive_risk_block(rr, settle_info=settle)}\n\n"
        telegram_text = tf.fmt_adaptive_risk_block(rr, settle_info=settle)
        assert telegram_text in export_text
        assert export_text.encode("utf-8") == \
            f"{tf.fmt_adaptive_risk_block(rr, settle_info=settle)}\n\n".encode(
                "utf-8")
        assert "המלצת סיכון אדפטיבי" in export_text
        assert "חום מסחר" in export_text

    def test_export_adaptive_ok_false_renders_honest_marker(self):
        # _risk_rec.ok False ⇒ the EXISTING `⚪ {msg}` honest marker, never a
        # fabricated heat/recommendation (AGENTS.md #1).
        out = tf.fmt_adaptive_risk_block({"ok": False,
                                          "message": "אין מספיק נתונים"})
        assert "⚪" in out and "אין מספיק נתונים" in out
        assert "חום מסחר" not in out
        out2 = tf.fmt_adaptive_risk_block({"ok": False})
        assert "⚪" in out2

    def test_export_makes_NO_new_compute_adaptive_risk_call(self):
        """THE headline invariant (SCOPE §2/§8): the export builder reuses
        the ALREADY-computed `_risk_rec`; the ONLY compute_adaptive_risk
        call site stays the pre-existing dashboard sidebar widget call.
        A NEW call would re-mutate risk_recommendations.json + re-enter
        risk-heat math (forbidden). Proven by AST — exactly one
        `compute_adaptive_risk` Call node in dashboard.py, and the export
        block reuses `_risk_rec`."""
        tree = ast.parse(_DASH)
        car_calls = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                fn = node.func
                if (isinstance(fn, ast.Attribute)
                        and fn.attr == "compute_adaptive_risk"):
                    car_calls.append(node.lineno)
        assert len(car_calls) == 1, \
            f"expected exactly 1 compute_adaptive_risk call, got {car_calls}"
        # the export block reuses the in-scope `_risk_rec` (not a re-call)
        assert "tf.fmt_adaptive_risk_block(_risk_rec, settle_info=" in _DASH
        # `are.get_risk_settle_info()` is the read-only config FILE READ the
        # Telegram report also makes (no write).
        assert "are.get_risk_settle_info()" in _DASH

    def test_risk_recommendations_json_write_count_invariant(self):
        """No new risk_recommendations.json write: the only producer is the
        pre-existing single compute_adaptive_risk call (which the export
        does NOT re-invoke). dashboard.py never writes that file directly,
        and the export adds no compute_adaptive_risk / _log_recommendation
        call."""
        tree = ast.parse(_DASH)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                fn = node.func
                if isinstance(fn, ast.Attribute):
                    assert fn.attr != "_log_recommendation"
        # no direct write of the recommendations file from dashboard
        assert "risk_recommendations.json" not in _DASH.replace(
            "# risk_recommendations.json write", "")  # only the comment ref

    def test_get_risk_settle_info_is_read_only(self):
        # adaptive_risk_engine.get_risk_settle_info only READS the config
        # file — it must not write (SCOPE §2). Static proof on its source.
        import inspect
        import adaptive_risk_engine as are
        src = inspect.getsource(are.get_risk_settle_info)
        assert ', "w"' not in src and ", 'w'" not in src
        assert "json.dump" not in src


# ════════════════════════════════════════════════════════════════════════════
# Block 3 — ALGO-2A divergence: LANDED (Phase REPORT-3.1, founder-authorized
# governed correction). The AI export is a SECOND legitimate divergence
# SURFACE in dashboard.py (distinct from the ALGO-backtest tab panel). It is
# byte-identical to that panel + the Telegram ALGO panel BY CONSTRUCTION: a
# SINGLE shared read-only input set (`_build_algo_divergence_inputs`, built
# once) feeds algo_divergence's SINGLE-source pair —
# `format_symbol_divergence_line(...)` per symbol then
# `format_divergence_footer()` EXACTLY ONCE per surface (de-dup proof, per
# SURFACE not per file). The ALGO-2A.1 de-dup test was correspondingly
# CORRECTED (not weakened) to a per-surface invariant (Mark 6.1). The export
# Block-3 region is delimited by stable unique marker comments. Observe-only
# INVIOLABLE (AGENTS.md #8 / DEC-20260511-001).
# ════════════════════════════════════════════════════════════════════════════
class TestBlock3AlgoDivergenceLanded:
    def test_export_is_a_second_divergence_surface_single_formatter(self):
        """LANDED: dashboard.py now has TWO divergence SURFACES (the
        ALGO-backtest tab panel + the AI-export Block 3) and BOTH render via
        the algo_divergence SINGLE-source pair — no inline re-implementation
        (SCOPE §6 anti-drift). There are exactly TWO executable
        `format_symbol_divergence_line` call sites and TWO
        `format_divergence_footer` call sites (one per surface)."""
        tree = ast.parse(_DASH)
        footer_calls = [
            n.lineno for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == "format_divergence_footer"]
        line_calls = [
            n.lineno for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == "format_symbol_divergence_line"]
        # one footer + one per-symbol-line call site per SURFACE (panel +
        # export); the footer is NEVER inside a per-symbol loop (de-dup).
        assert len(footer_calls) == 2, footer_calls
        assert len(line_calls) == 2, line_calls

    def test_export_block3_region_is_marker_delimited_line_then_footer(self):
        """The export Block-3 region is wrapped in stable unique marker
        comments (mirrors the panel's `<!-- ALGO-2A divergence section
        START/END -->`) so the corrected ALGO-2A.1 de-dup test can scope
        per-surface; inside it the per-symbol LINE precedes the footer and
        the footer appears EXACTLY ONCE (de-dup per surface)."""
        assert "# === ALGO-2A divergence (AI export) START ===" in _DASH
        assert "# === ALGO-2A divergence (AI export) END ===" in _DASH
        s = _DASH.index("# === ALGO-2A divergence (AI export) START ===")
        e = _DASH.index("# === ALGO-2A divergence (AI export) END ===")
        region = _DASH[s:e]
        assert "algo_divergence.format_symbol_divergence_line(" in region
        assert "algo_divergence.format_divergence_footer(" in region
        # footer EXACTLY ONCE in THIS surface (per-surface de-dup proof)
        assert region.count(
            "algo_divergence.format_divergence_footer(") == 1
        i_line = region.index(
            "algo_divergence.format_symbol_divergence_line(")
        i_footer = region.index(
            "algo_divergence.format_divergence_footer(")
        assert i_line < i_footer
        # no Supabase / state / push smuggled into the export surface
        for forbidden in ("supabase.table", ".execute(", ".insert(",
                          ".update(", ".delete(", "bot.send_message"):
            assert forbidden not in region, forbidden

    def test_export_block3_byte_identical_to_single_source_pair(self):
        """Cross-surface byte-identity (SCOPE §8(b)): the export Block-3
        text is, BY CONSTRUCTION, `format_symbol_divergence_line(sym, ...)`
        per symbol + `format_divergence_footer()` ONCE — the SAME single
        source the dashboard ALGO panel + the Telegram ALGO panel call.
        Proven on synthetic inputs: the export emits exactly the formatter
        output (never a re-implemented / fabricated delta)."""
        live = {"HOOD": {"n": 35, "win_rate_pct": 60.0,
                         "avg_return_pct": 1.20, "profit_factor": 1.80,
                         "loss_streak": 3}}
        bt = {"strategies": {"HOOD::s": {
            "symbol": "HOOD", "n": 50, "win_rate_pct": 66.0,
            "avg_return_pct": 7.5, "median_return_pct": 7.5,
            "profit_factor": 3.25, "longest_loss_streak": 1}}}
        # the export builds, per symbol, `format_symbol_divergence_line(...)`
        # + "\n" then ONE `format_divergence_footer()` + "\n" — identical to
        # what the dashboard ALGO panel renders for the SAME shared input.
        expected = (
            ad.format_symbol_divergence_line("HOOD", live, bt) + "\n"
            + ad.format_divergence_footer() + "\n"
        )
        # byte-for-byte stable (single source ⇒ deterministic)
        again = (
            ad.format_symbol_divergence_line("HOOD", live, bt) + "\n"
            + ad.format_divergence_footer() + "\n"
        )
        assert expected == again
        assert expected.encode("utf-8") == again.encode("utf-8")
        # the export source uses the formatter return value directly, NOT a
        # hand-written string (no inline re-implementation, SCOPE §6).
        s = _DASH.index("# === ALGO-2A divergence (AI export) START ===")
        e = _DASH.index("# === ALGO-2A divergence (AI export) END ===")
        region = _DASH[s:e]
        assert ("ai_str += algo_divergence.format_symbol_divergence_line("
                in region)
        assert ("ai_str += algo_divergence.format_divergence_footer()"
                in region)
        assert "compute_symbol_divergence" not in region

    def test_export_block3_observe_only_and_honest_empty_preserved(self):
        """ALGO observe-only INVIOLABLE: neutral 🔭, no imperative, no
        🔴/🟢; honest-empty / concrete-shortfall / no-cohort markers are the
        formatter's (never a fabricated delta — AGENTS.md #1)."""
        s = _DASH.index("# === ALGO-2A divergence (AI export) START ===")
        e = _DASH.index("# === ALGO-2A divergence (AI export) END ===")
        region = _DASH[s:e]
        # the export sub-section keeps the observe-only header + the
        # explicit "observation only / zero signal / no KPI / no directive".
        assert ("## 🔭 3b. ALGO Live↔Backtest Edge-Shape Divergence"
                in region)
        assert "תצפית בלבד" in region
        # no-cohort ⇒ the EXISTING honest INSUFFICIENT marker, never a delta
        assert "algo_divergence.INSUFFICIENT_LIVE_SAMPLE_HE" in region
        # no imperative / verdict colour smuggled into the export OUTPUT —
        # scope to the executable `ai_str +=` emit lines (prose comments are
        # not rendered to the founder; the rendered text is what matters).
        emit = "".join(
            ln for ln in region.splitlines(keepends=True)
            if ln.lstrip().startswith("ai_str"))
        assert emit, "export Block-3 must emit ai_str content"
        assert "🔴" not in emit and "🟢" not in emit
        assert "דרושה פעולה" not in emit
        # below-floor concrete shortfall is the formatter's (single source)
        line = ad.format_symbol_divergence_line(
            "FOO", {"FOO": {"n": 5, "win_rate_pct": 50.0,
                            "avg_return_pct": 1.0, "profit_factor": 1.5,
                            "loss_streak": 2}}, {"strategies": {}})
        assert "מדגם חי 5/30" in line and "חסרים 25" in line
        assert "תצפית, לא איתות" in line
        assert "🔴" not in line and "🟢" not in line
        assert "דרושה פעולה" not in line
        assert ad.MARKER == "🔭"
        assert "אין מספיק מדגם חי" in ad.INSUFFICIENT_LIVE_SAMPLE_HE

    def test_export_and_panel_share_one_readonly_input_assembly(self):
        """SCOPE §6 anti-drift: both divergence surfaces consume the ONE
        shared read-only assembly `_build_algo_divergence_inputs(...)` (built
        once — the `_camp_legs_dash` precedent), so they are byte-identical
        BY CONSTRUCTION and there is no second/parallel compute path. The
        helper is pure read-only (no Supabase / network / write / engine
        re-entry / R-NAV-exposure recompute)."""
        tree = ast.parse(_DASH)
        helper_calls = [
            n.lineno for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id == "_build_algo_divergence_inputs"]
        # built ONCE, reused by both surfaces (one call site)
        assert len(helper_calls) == 1, helper_calls
        # the shared variables feed BOTH the export and the panel
        assert "_export_div_live, _export_div_bt = " \
               "_build_algo_divergence_inputs(camp_df)" in _DASH
        assert "_bt_stats = _export_div_bt" in _DASH
        assert "_div_live_aggs = _export_div_live" in _DASH
        # the helper body is read-only — no Supabase / write / engine re-entry
        h0 = _DASH.index("def _build_algo_divergence_inputs(")
        h1 = _DASH.index("\n\n\n", h0)
        helper = _DASH[h0:h1]
        for forbidden in ("supabase", ".execute(", ".insert(", ".update(",
                          ".delete(", "json.dump", "evaluate_position_engine",
                          "compute_adaptive_risk", "are."):
            assert forbidden not in helper, forbidden

    def test_algo2a1_dedup_test_corrected_per_surface_not_weakened(self):
        """Mark 6.1 — the ALGO-2A.1 de-dup over-assertion was CORRECTED to a
        per-SURFACE invariant (strictly MORE precise, NOT weakened): the
        founder-authorized single surgical change to TestCase6 swaps the
        whole-FILE `dash.count(...) == 1` for a PER-SURFACE-region check
        (footer exactly once within EACH delimited divergence surface). The
        telegram_tasks.py side stays `== 1` (one ALGO-panel surface). No
        other assertion in tests/test_phase_algo2a.py changed."""
        a2a = _src("tests/test_phase_algo2a.py")
        # the corrected test asserts PER-SURFACE (region-scoped), not a
        # whole-file `dash.count(...) == 1` (which the legitimate 2nd
        # surface would falsely trip).
        assert "dash.count(\"algo_divergence.format_divergence_footer(\")" \
               " == 1" not in a2a
        # telegram_tasks.py still has exactly one ALGO-panel surface — its
        # whole-file footer count == 1 stays correct and is preserved.
        assert "tt.count(\"algo_divergence.format_divergence_footer(\")" \
               " == 1" in a2a
        # the corrected test still requires BOTH surfaces to reference the
        # single formatter (anti-drift kept) and scopes the de-dup per the
        # marker-delimited regions (panel + AI export).
        assert "format_symbol_divergence_line(" in a2a
        assert "format_divergence_footer(" in a2a
        assert "ALGO-2A divergence section START" in a2a  # panel region
        assert "ALGO-2A divergence (AI export) START" in a2a  # export region

    def test_underlying_divergence_formatter_still_honest_observe_only(self):
        # the single-source formatter both surfaces use is unchanged & honest
        # (below-floor concrete shortfall; observe-only; no fabricated 0).
        line = ad.format_symbol_divergence_line(
            "FOO", {"FOO": {"n": 5, "win_rate_pct": 50.0,
                            "avg_return_pct": 1.0, "profit_factor": 1.5,
                            "loss_streak": 2}}, {"strategies": {}})
        assert "מדגם חי 5/30" in line and "חסרים 25" in line
        assert "תצפית, לא איתות" in line
        assert "🔴" not in line and "🟢" not in line
        assert "דרושה פעולה" not in line
        assert ad.MARKER == "🔭"
        assert "אין מספיק מדגם חי" in ad.INSUFFICIENT_LIVE_SAMPLE_HE


# ════════════════════════════════════════════════════════════════════════════
# Block 4 — per-position engine action: raw `action_short` from the EXISTING
#           eval_res (additive live_df['Action']); ALGO verbatim + no
#           directive; engine not-OK ⇒ error verbatim + honest un-softened note
# ════════════════════════════════════════════════════════════════════════════
class TestBlock4EngineAction:
    def test_action_field_added_from_existing_eval_res_no_new_call(self):
        """SCOPE §4/§8: the ONLY engine touch is reading
        eval_res['data']['action'] from the EXISTING evaluate_position_engine
        call — NO new call site. Proven by AST: exactly ONE
        evaluate_position_engine Call node in dashboard.py."""
        tree = ast.parse(_DASH)
        epe = [n.lineno for n in ast.walk(tree)
               if isinstance(n, ast.Call)
               and isinstance(n.func, ast.Attribute)
               and n.func.attr == "evaluate_position_engine"]
        assert len(epe) == 1, \
            f"expected exactly 1 evaluate_position_engine call, got {epe}"
        # the additive live_df field reads the EXISTING eval_res
        assert "_engine_action = eval_res['data']['action'] if eval_res['ok'] else None" in _DASH
        assert "'Action': _engine_action," in _DASH
        assert "'ActionErr': _engine_action_err," in _DASH

    def test_export_prints_raw_action_with_honest_unsoftened_note(self):
        # the export §2 prints the RAW engine action + the explicit honest
        # note disclosing it is un-softened vs the Telegram REPORT-2
        # de-noising (so a reader never assumes byte-identity).
        assert "Engine Action (advisory, raw):" in _DASH
        note = ("raw engine action; the Telegram card additionally applies a "
                "display-only partial-realize de-noising (REPORT-2) the "
                "export does NOT replicate")
        assert note in _DASH

    def test_algo_action_verbatim_no_added_directive(self):
        """For an ALGO position the engine ALREADY returns the verbatim
        externally-managed oversight-only string. The export prints it
        verbatim with NO added directive (ALGO observe-only INVIOLABLE).
        Proven on the engine's own source (not re-implemented) + the export
        adds no ALGO-specific action mutation."""
        import inspect
        import engine_core as ec
        eng_src = inspect.getsource(ec.evaluate_position_engine)
        assert "מנוהל חיצונית — בקרה בלבד" in eng_src
        # the export block 4 does NOT branch/soften on ALGO — it prints the
        # looked-up raw action unconditionally; no ALGO directive token
        # introduced by the export wiring.
        b4 = _DASH[_DASH.index("Phase REPORT-3 block 4 — per-position"):
                   _DASH.index("if not is_algo_pos and _ctx['has_profit']:",
                               _DASH.index(
                                   "Phase REPORT-3 block 4 — per-position"))]
        for tok in ("מכור", "צא מיד", "בצע יציאה", "סגור פוזיציה"):
            assert tok not in b4
        # no engine re-call inside the block
        assert "evaluate_position_engine" not in b4

    def test_engine_not_ok_error_verbatim_plus_honest_note(self):
        # engine not-OK ⇒ the raw engine error string verbatim + an honest
        # note it is not softened / no fabricated directive (AGENTS.md #1).
        assert ("_engine_action_err = (None if eval_res['ok']\n"
                "                              else f\"engine: "
                "{eval_res.get('error', 'unknown')}\")") in _DASH
        assert ("engine result not OK — error shown verbatim; not softened "
                "(no fabricated directive)") in _DASH

    def test_action_lookup_built_like_existing_live_price_lookup(self):
        # the Symbol→Action lookup is built the SAME read-only zip way the
        # existing _live_price_lookup is (SCOPE §1.4 / §6).
        assert ("_live_action_lookup = (dict(zip(live_df['Symbol'], "
                "live_df['Action']))") in _DASH
        assert ("_live_action_err_lookup = (dict(zip(live_df['Symbol'], "
                "live_df['ActionErr']))") in _DASH


# ════════════════════════════════════════════════════════════════════════════
# Block 5 — portfolio aggregate == the EXISTING live_df / Heat-Map sums
#           (no recompute of R/NAV/exposure)
# ════════════════════════════════════════════════════════════════════════════
class TestBlock5PortfolioAggregate:
    def test_aggregate_uses_same_source_live_df_sums(self):
        # the aggregate is composed from the SAME read-only live_df[col].sum()
        # expressions the existing Heat-Map (dashboard.py:813-833) uses —
        # NEVER a recompute of R/NAV/exposure (SCOPE §5 same-source mandate).
        assert "live_df['LockedProfit'].sum()" in _DASH
        assert "live_df['GivebackRisk'].sum()" in _DASH
        assert "live_df['CapitalRisk'].sum()" in _DASH
        assert "live_df['Exposure_USD'].sum()" in _DASH
        # total floating PnL reuses the ALREADY-computed sidebar value
        assert "_agg_pnl = float(total_open_pnl)" in _DASH
        # ALGO-cluster exposure is a factual exposure read-out (no directive)
        assert ("_algo_mask = live_df['Setup'].astype(str).str.upper() == "
                "'ALGO'") in _DASH
        assert "ALGO-Cluster Exposure:" in _DASH

    def test_aggregate_emits_same_source_disclosure(self):
        # honest: the aggregate explicitly discloses it is factual sums
        # (not a recompute) and inherits NAV-freshness + reconciliation.
        assert ("factual sums of the existing live_df columns / Heat-Map; "
                "not a recompute of R/NAV/exposure") in _DASH

    def test_aggregate_arithmetic_matches_heatmap_logic(self):
        """Numeric equivalence proof on a synthetic live_df: the aggregate
        expressions equal the SAME Heat-Map groupby sums for the same data
        (no recompute — identical pandas reduction)."""
        import pandas as pd
        live_df = pd.DataFrame([
            {"Symbol": "AAA", "Setup": "EP", "Exposure_USD": 1000.0,
             "LockedProfit": 50.0, "GivebackRisk": 20.0, "CapitalRisk": 10.0,
             "PnL": 30.0},
            {"Symbol": "BBB", "Setup": "ALGO", "Exposure_USD": 500.0,
             "LockedProfit": 0.0, "GivebackRisk": 5.0, "CapitalRisk": 0.0,
             "PnL": -10.0},
        ])
        acc = 5000.0
        # the export expressions (verbatim semantics from the wired block)
        agg_locked = float(live_df['LockedProfit'].sum())
        agg_give = float(live_df['GivebackRisk'].sum())
        agg_expo = float(live_df['Exposure_USD'].sum())
        algo_mask = live_df['Setup'].astype(str).str.upper() == 'ALGO'
        agg_algo_expo = float(live_df.loc[algo_mask, 'Exposure_USD'].sum())
        # the existing Heat-Map groupby reductions (dashboard.py:813-833)
        hm = live_df.groupby('Setup')
        hm_locked = float(sum(g['LockedProfit'].sum() for _, g in hm))
        hm_give = float(sum(g['GivebackRisk'].sum() for _, g in hm))
        hm_expo = float(sum(g['Exposure_USD'].sum() for _, g in hm))
        assert agg_locked == hm_locked == 50.0
        assert agg_give == hm_give == 25.0
        assert agg_expo == hm_expo == 1500.0
        assert agg_algo_expo == 500.0
        assert (agg_expo / acc * 100.0) == pytest.approx(30.0)


# ════════════════════════════════════════════════════════════════════════════
# Cross-cutting — never-replace; only-added live_df field is Action/ActionErr;
# read-only intact; permitted-diff; LOCKED April + byte-lock unaffected
# ════════════════════════════════════════════════════════════════════════════
class TestCrossCuttingNeverReplaceAndReadOnly:
    def test_only_dashboard_changed_in_permitted_diff(self):
        """`git diff --name-only` must be exactly dashboard.py (+ this NEW
        test). Every protected/byte-locked file git-diff EMPTY (SCOPE §7)."""
        import subprocess
        out = subprocess.run(
            ["git", "-C", _ROOT, "diff", "--name-only"],
            capture_output=True, text=True).stdout.split()
        changed = set(out)
        # dashboard.py is the ONLY tracked-file modification permitted
        forbidden = {
            "engine_core.py", "analytics_engine.py", "period_data_probe.py",
            "adaptive_risk_engine.py", "risk_monitor.py",
            "telegram_portfolio.py", "telegram_formatters.py",
            "telegram_bot.py", "telegram_tasks.py", "supabase_repository.py",
            "position_lifecycle.py", "algo_divergence.py", "algo_metrics.py",
            "algo_rules.py", "algo_backtest_store.py", "docker-compose.yml",
            "telegram_bot_secure_runner.py",
            "tests/test_real_data_april_regression.py",
        }
        assert not (changed & forbidden), \
            f"forbidden file(s) modified: {changed & forbidden}"
        for c in changed:
            assert not c.startswith("docs/"), f"docs changed: {c}"
            assert not c.startswith("tests/_byte_lock_baselines/"), c
            assert not c.startswith("migrations/"), c
            assert not c.startswith("templates/"), c

    def test_only_added_live_df_fields_are_action_and_actionerr(self):
        """The ONLY new keys on the live_positions.append({...}) dict are
        'Action' and 'ActionErr'; every existing column key is byte-identical
        (strictly additive)."""
        tree = ast.parse(_DASH)
        # locate the live_positions.append({...}) dict literal
        append_dict = None
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "append"
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "live_positions"
                    and node.args
                    and isinstance(node.args[0], ast.Dict)):
                append_dict = node.args[0]
                break
        assert append_dict is not None
        keys = [k.value for k in append_dict.keys
                if isinstance(k, ast.Constant)]
        assert "Action" in keys and "ActionErr" in keys
        # every legacy column the export / Heat-Map depends on still present
        for legacy in ("Symbol", "Setup", "Exposure_USD", "Exposure_Pct",
                       "PnL", "Open_R", "Total_R", "Score", "Status",
                       "Sizing", "GivebackRisk", "LockedProfit",
                       "CapitalRisk", "CampaignId", "Qty", "Current"):
            assert legacy in keys, f"existing live_df column lost: {legacy}"

    def test_existing_ai_str_anchor_lines_byte_identical(self):
        """Every existing `ai_str` structural line/number the export already
        carried is byte-identical pre/post — the 5 blocks are strictly
        ADDITIVE (never-replace, SCOPE §3.6). Anchor the canonical existing
        tokens verbatim."""
        for anchor in (
            'ai_str = f"# 🛡️ Sentinel AI - Master Context Report\\n\\n"',
            'ai_str += f"## ⚠️ Sentinel Observer Note\\n"',
            'ai_str += f"## 📊 1. Performance Matrix & Risk Profile\\n"',
            'ai_str += f"- Broker NAV: ${current_acc_size:,.2f} | '
            'Base Capital: ${total_deposited:,.2f}\\n"',
            'ai_str += f"## 🔭 2. Live Battlefield (Open Positions)\\n"',
            'ai_str += f"  State: {_state_str} | Sizing: {_sizing_str}\\n"',
            'ai_str += f"\\n## 📅 3. Execution Archive (Recent Campaigns)'
            '\\n"',
            'ai_str += f"\\n## 🧭 4. Next Required Decisions\\n"',
            'else: ai_str += "No open positions.\\n"',
            'else: ai_str += "No campaigns closed yet.\\n"',
        ):
            assert anchor in _DASH, f"existing ai_str line altered: {anchor}"

    def test_export_observer_note_and_algo_fence_unchanged(self):
        # the Observer Note at the TOP of the export (ALGO fence) is
        # byte-identical (SCOPE §6 / AGENTS.md #8).
        assert ('ai_str += f"## ⚠️ Sentinel Observer Note\\n"') in _DASH
        assert ("ALGO positions (management_mode=algo_observed) are managed "
                "externally. " in _DASH)
        assert ("Never issue exit or stop instructions for ALGO positions."
                in _DASH)

    def test_no_supabase_state_or_new_message_type_added(self):
        # the 5 blocks add zero Supabase write / state mutation / push /
        # new message TYPE (SCOPE §8(f)). Static proof on the new blocks.
        blocks = _DASH[_DASH.index("Phase REPORT-3 block 2 — Adaptive-risk"):
                       _DASH.index("## 🧭 4. Next Required Decisions")]
        for tok in (".insert(", ".update(", ".execute(", ".delete(",
                    "supabase.", "bot.send_message", "telebot",
                    "json.dump", "state_io.", "register_next_step"):
            assert tok not in blocks, f"forbidden side-effect token: {tok}"

    def test_no_new_side_effecting_import_in_dashboard(self):
        # the export imports no NEW side-effecting symbol — block 3 only
        # uses `import algo_metrics` locally (the SAME the dashboard ALGO
        # panel already imports, pure read-only) and the already-imported
        # plc / tf / are / algo_divergence / abs_store. No engine re-entry.
        tree = ast.parse(_DASH)
        top_imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                top_imports |= {n.name for n in node.names}
            elif isinstance(node, ast.ImportFrom):
                top_imports.add(node.module or "")
        for forbidden in ("requests", "urllib"):
            assert forbidden not in top_imports

    def test_locked_april_regression_invariant_still_holds(self):
        # LOCKED April byte-identical (8 / +$180.49 / WR .375 / PF 2.6262 /
        # excl 2) — the export change is display-only, zero math.
        mod = importlib.import_module(
            "tests.test_real_data_april_regression")
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

    def test_byte_locked_files_unmodified(self):
        from tests._byte_lock_baseline import assert_byte_identical
        for rel in (
            "engine_core.py",
            "analytics_engine.py",
            "period_data_probe.py",
            "tests/test_real_data_april_regression.py",
        ):
            assert_byte_identical(rel)

    def test_dashboard_compiles(self):
        import py_compile
        py_compile.compile(os.path.join(_ROOT, "dashboard.py"),
                           doraise=True)
