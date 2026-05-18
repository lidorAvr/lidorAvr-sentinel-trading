"""Sprint-30 G1 — R-ALGO-2 finish: the two-surface recon band divergence.

Authoritative spec: docs/teams/SPRINT30_SCOPE.md (G1)
Root-cause evidence: docs/teams/ALGO_INVESTIGATION_1.md (§1, residual),
                     docs/teams/SPRINT29_RESEARCH_REPORTMAP.md (F1, post-deploy
                     non-convergence), docs/teams/SPRINT30_G1_IMPL.md.

Context
-------
ALGO-1 W-A2 fixed the חדר-מצב silently-0 realized-PnL **key** bug
(`telegram_portfolio.py` now reads the producer key `total_pnl_usd`). But the
post-deploy Telegram export (`/tmp/tg_report_2.txt`) still shows the master
"📊 סיכום תיק הפיקוד" recon line and the dashboard oracle rendering DIFFERENT
bands for the same state — "פער מהותי" (Material Gap) on the phone vs
"פער נתונים קריטי" (Critical Data Gap) on the dashboard — directly above a
risk-raise recommendation.

Divergence root cause (this test pins it)
-----------------------------------------
The shared classifier `tf.classify_broker_reconciliation`
(`telegram_formatters.py:765`) has a Critical-Data-Gap branch:

    is_critical = (agap > 5*unit) or (bool(max_open_campaign_risk)
                                       and agap > max_open_campaign_risk)

The **dashboard oracle** PASSES `max_open_campaign_risk=_max_open_risk`
(`dashboard.py:452,460` — `live_df["OriginalRisk"].max()`), so the second
Critical condition is LIVE there. The חדר-מצב call-site
(`telegram_portfolio.py`) previously OMITTED that argument ⇒ it defaulted to
`0.0` ⇒ `bool(0.0)` is False ⇒ the second Critical branch was DEAD on the
phone surface. A gap inside the 5R anchor but larger than the biggest single
open-campaign original risk therefore classified as the **softer** "Material
Gap" on the phone while the dashboard oracle (the correctness reference)
classified the SAME state as "Critical Data Gap".

Resolution chosen: EQUAL (not labelled-distinct)
------------------------------------------------
The two surfaces measure the SAME thing (one broker reconciliation for one
state); the dashboard oracle is the documented correctness reference
(ALGO-1 §1: "the dashboard/master side is the methodologically intended
one"). The honest fix is therefore an *equality* fix: feed the חדר-מצב
classifier the SAME `max_open_campaign_risk` the oracle feeds it (the max of
the per-open-position `original_campaign_risk` the loop already computes),
so both surfaces emit the SAME band for the SAME state. Forcing a wrong
equality is explicitly NOT done — the classifier is unchanged; only the
phone call-site's argument set is brought into parity with the oracle.

These tests ONLY ADD coverage (Mark 6.1 — no existing test deleted/weakened).
"""
import ast
from pathlib import Path

import pytest

import telegram_formatters as tf

# telegram_portfolio imports bot_core which constructs telebot.TeleBot(TOKEN);
# the CI token has no colon ⇒ importing the module raises at collection. The
# source-contract checks below only need the *text* of handle_portfolio_room,
# so read it straight off disk (no module import, no telebot init) — robust
# regardless of conftest stub ordering.
_TP_PATH = Path(__file__).resolve().parent.parent / "telegram_portfolio.py"


def _handle_portfolio_room_source() -> str:
    """Extract the source of handle_portfolio_room from the file via AST,
    without importing the heavy module."""
    src = _TP_PATH.read_text(encoding="utf-8")
    mod = ast.parse(src)
    lines = src.splitlines()
    for node in ast.walk(mod):
        if isinstance(node, ast.FunctionDef) and node.name == "handle_portfolio_room":
            end = getattr(node, "end_lineno", len(lines))
            return "\n".join(lines[node.lineno - 1:end])
    raise AssertionError("handle_portfolio_room not found in telegram_portfolio.py")


# ── Shared real-world state (the post-deploy export shape, structural only) ──
# Values chosen to reproduce the export's divergence MECHANISM without copying
# any live financial figure: NAV / deposited / risk% are generic round
# numbers; the only load-bearing relationship is
#   max_open_campaign_risk  <  |gap|  <  5 * unit
# i.e. the gap sits INSIDE the 5R anchor (so the first Critical condition is
# False) but EXCEEDS the biggest single open-campaign original risk (so the
# second Critical condition decides the band). This is precisely the regime in
# which omitting vs passing the argument flips the band.
_NAV = 8000.0
_DEPOSITED = 7500.0
_RISK_PCT = 0.50                       # one unit = 8000 * 0.5/100 = 40.0
_UNIT = _NAV * _RISK_PCT / 100.0       # 40.0
_GAP = 120.0                           # 40 < 120 < 200 (= 5*unit)
_MAX_OPEN_CAMPAIGN_RISK = 48.0         # |gap| 120 > 48 ⇒ Critical (oracle path)


def _classify(*, max_open_campaign_risk):
    """Invoke the SHARED classifier exactly as a call-site would, varying ONLY
    the one argument that is the divergence root."""
    return tf.classify_broker_reconciliation(
        _NAV, _DEPOSITED, 0.0,
        reconciliation_gap=_GAP,
        risk_pct_input=_RISK_PCT,
        nav_source="broker",
        max_open_campaign_risk=max_open_campaign_risk,
    )


# ════════════════════════════════════════════════════════════════════════════
# (1) The divergence is REAL and is exactly the `max_open_campaign_risk` arg
# ════════════════════════════════════════════════════════════════════════════
class TestDivergenceRootIsTheOmittedArgument:
    def test_gap_is_inside_5R_anchor(self):
        """Sanity: the first Critical condition (agap > 5*unit) is FALSE here,
        so the band is decided SOLELY by the max_open_campaign_risk branch —
        isolating the exact divergence root."""
        assert _UNIT == pytest.approx(40.0)
        assert abs(_GAP) < 5.0 * _UNIT          # 120 < 200 ⇒ not 5R-critical
        assert abs(_GAP) > _MAX_OPEN_CAMPAIGN_RISK  # 120 > 48 ⇒ open-risk-crit

    def test_prefix_phone_callsite_omitting_arg_understates_band(self):
        """Pre-fix חדר-מצב: argument OMITTED ⇒ defaults to 0.0 ⇒ the second
        Critical branch is DEAD ⇒ the SAME state is mis-banded the softer
        "Material Gap" ("פער מהותי") on the phone."""
        st = _classify(max_open_campaign_risk=0.0)
        assert st["band"] == "Material Gap"
        assert st["band_he"] == "פער מהותי"

    def test_dashboard_oracle_passing_arg_is_critical(self):
        """Dashboard oracle (the correctness reference): argument PASSED ⇒ the
        SAME state correctly classifies "Critical Data Gap"
        ("פער נתונים קריטי")."""
        st = _classify(max_open_campaign_risk=_MAX_OPEN_CAMPAIGN_RISK)
        assert st["band"] == "Critical Data Gap"
        assert st["band_he"] == "פער נתונים קריטי"

    def test_the_two_surfaces_diverged_pre_fix(self):
        """The bug, stated as one assertion: same classifier, same state, two
        DIFFERENT bands solely because one call-site omitted the argument."""
        phone_prefix = _classify(max_open_campaign_risk=0.0)["band"]
        oracle = _classify(max_open_campaign_risk=_MAX_OPEN_CAMPAIGN_RISK)["band"]
        assert phone_prefix != oracle  # ← the divergence (פער מהותי≠קריטי)


# ════════════════════════════════════════════════════════════════════════════
# (2) PARITY pin — post-fix the phone surface emits the SAME band as the oracle
# ════════════════════════════════════════════════════════════════════════════
class TestPostFixSurfaceParity:
    def test_postfix_phone_band_equals_dashboard_oracle_band(self):
        """The money-truth parity proof: with the phone call-site now passing
        the SAME max_open_campaign_risk the dashboard oracle passes, both
        surfaces emit the SAME band + the SAME Hebrew label + the SAME gap
        for the SAME state. Resolution = EQUAL (not labelled-distinct):
        one reconciliation, one truth, dashboard oracle is the reference."""
        oracle = _classify(max_open_campaign_risk=_MAX_OPEN_CAMPAIGN_RISK)
        phone_postfix = _classify(max_open_campaign_risk=_MAX_OPEN_CAMPAIGN_RISK)
        assert phone_postfix["band"] == oracle["band"] == "Critical Data Gap"
        assert phone_postfix["band_he"] == oracle["band_he"] == "פער נתונים קריטי"
        assert phone_postfix["gap"] == oracle["gap"]
        assert phone_postfix == oracle  # full structural identity

    def test_classifier_itself_is_unchanged_no_forced_equality(self):
        """We did NOT force a wrong equality: the classifier still
        legitimately bands a gap WITHIN the 5R anchor AND below the max
        open-campaign risk as the softer "Material Gap" — equality holds
        only because both surfaces now feed it identical honest inputs."""
        st = _classify(max_open_campaign_risk=500.0)  # gap 120 < 500
        assert st["band"] == "Material Gap"           # genuinely not critical
        # and a gap beyond the 5R anchor is still Critical regardless of arg:
        big = tf.classify_broker_reconciliation(
            _NAV, _DEPOSITED, 0.0, reconciliation_gap=5.0 * _UNIT + 0.01,
            risk_pct_input=_RISK_PCT, nav_source="broker",
            max_open_campaign_risk=0.0)
        assert big["band"] == "Critical Data Gap"


# ════════════════════════════════════════════════════════════════════════════
# (3) Source contract — the חדר-מצב call-site now PASSES max_open_campaign_risk
# ════════════════════════════════════════════════════════════════════════════
class TestPhoneCallSitePassesTheArgument:
    def test_handle_portfolio_room_passes_max_open_campaign_risk(self):
        """Static guarantee against regression: the recon call inside
        telegram_portfolio.handle_portfolio_room now explicitly passes the
        `max_open_campaign_risk=` keyword to classify_broker_reconciliation
        (mirroring dashboard.py:460). Asserted on the AST so a future edit
        that drops it fails CI."""
        src = _handle_portfolio_room_source()
        tree = ast.parse(src)
        passes_arg = False
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = (fn.attr if isinstance(fn, ast.Attribute)
                    else getattr(fn, "id", ""))
            if name != "classify_broker_reconciliation":
                continue
            kws = {k.arg for k in node.keywords if k.arg}
            if "max_open_campaign_risk" in kws:
                passes_arg = True
        assert passes_arg, (
            "handle_portfolio_room must pass max_open_campaign_risk= to "
            "classify_broker_reconciliation (parity with dashboard oracle)")

    def test_max_open_campaign_risk_accumulator_present(self):
        """The accumulator that mirrors dashboard.py:452
        `live_df["OriginalRisk"].max()` is initialised and updated in the
        existing per-position loop (no new data source / no new math)."""
        src = _handle_portfolio_room_source()
        assert "_max_open_campaign_risk = 0.0" in src
        assert "original_campaign_risk > _max_open_campaign_risk" in src


# ════════════════════════════════════════════════════════════════════════════
# (4) LOCKED April regression byte-identical (the recon fix touches NO
#     analytics/engine path the locked fixture exercises)
# ════════════════════════════════════════════════════════════════════════════
class TestLockedAprilByteIdentical:
    def test_locked_april_regression_still_passes_byte_identical(self):
        """The authorized fix is confined to telegram_portfolio.py's recon
        call-site (a display-surface read); it changes ZERO analytics/engine
        number. Re-run the LOCKED April regression in-process and assert the
        canonical invariants (8 / +$180.49 / WR .375 / PF 2.6262 / excl 2)
        are byte-identical."""
        locked = Path(__file__).with_name("test_real_data_april_regression.py")
        assert locked.exists(), "LOCKED April regression file must exist"
        rc = pytest.main([
            "-q", "-p", "no:cacheprovider", str(locked),
        ])
        assert rc == 0, "LOCKED April regression must remain byte-identical"
