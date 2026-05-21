# Mark Rulings — Meeting (21/05/2026) UX / F-YTD wave

**Reviewer:** Mark (rulings/precedent referee).
**Date:** 2026-05-21.
**Branch at issuance:** `claude/review-system-audit-FBZ2h`, HEAD `cd004aa`.
**Promotes from:** `MEETING_UX_MARK_FINDINGS.md` (8-discipline meeting deliverable).
**Status:** Codified — these become binding precedent for the next
follow-up phase and every later cleanup of the same shape.

This rulings doc codifies the three new §X clauses proposed by the
team-meeting consolidation. Pre-existing rulings (Sprint-12 §3
fallback-labelling, Sprint-15 §3 verbatim wording, Sprint-22 §3
anti-masking, Sprint-24 Ruling 1, Sprint-25 Rulings 2/3/4) remain
authoritative and are not amended here.

---

## §X1 — Breakdown lines MUST disclose their own source

When a number on the founder-facing surface has been *transformed* by
an operator-asserted disclaimer (e.g. `pre_db_realized_pnl_estimate`
softening the broker-reconciliation gap), every line that surfaces
the number MUST disclose whether it is showing:
- the **raw** value (untransformed), or
- the **adjusted** value (after the disclaimer was applied).

The breakdown must NEVER silently absorb the disclaimer into a single
"residual" number without naming it. Both raw and adjusted MUST surface
side-by-side (per the 21/05/2026 founder session: "$+495.67 גולמי →
$+0.00 מותאם" is the binding shape).

**Why.** Otherwise a future operator reading only the surfaced number
cannot reconstruct what actually happened. This is a §3-class
preservation: the line that hides its own transformation is a
fallback-as-truth disguise. Cross-references: AGENTS prime directive #1,
Sprint-12 §3, Sprint-22 §3.

**Pinned by:**
- `tests/test_meeting_ux_cleanup.py::TestReconLineSoftenedVariant`
  (asserts `גולמי` and `מותאם` both appear).
- `tests/test_meeting_fytd_pre_db_history.py::*` (raw+adjusted surface
  invariant on default and adjusted paths).

**Scope.** Applies to any future disclaimer-style softening (broker
recon today; potentially per-campaign disclaimers, per-position notes,
or NAV-side declarations in the future). Does NOT apply to read-only
display rounding (e.g. `${:,.2f}`) — only to lines where a
transformation changes the number.

---

## §X2 — Compact-on-system-decision-against precedent

When the system has already DECIDED against a particular up-leg (e.g.
the 4-gate clamped a `direction='up'` recommendation to `'hold'`), the
verbose decision-context breakdown that explains the up-case (S9/M21/L50
scores, win-rate breakdown, "🔼 לשיפור" gap line, full multi-line stat
contribution list) MAY collapse to a *compact* reason-only form
(direction + heat label + current/recommended + ⛔ blocking reason).

**Three-part predicate (binding):**
1. The system's surfaced `direction` is the conservative one
   (e.g. `'hold'` clamped down from `'up'`).
2. The gate was **explicitly evaluated** (`risk_raise_gate.evaluated
   == True`).
3. The gate **refused** (`risk_raise_gate.allow_raise == False`).

When all three hold, the verbose breakdown becomes contradictory
context-noise (the founder sees a forest of "why you could raise"
stats explaining why they CAN'T raise). The compact form is permitted
ONLY under this exact predicate.

**When the predicate does NOT hold:**
- Natural hold (no gate eval, `direction='hold'` because heat is
  neutral) → verbose path stays. The breakdown explains *why* heat
  was neutral, which is non-contradictory information.
- Gate refused but `direction='up'` survived another path (e.g. a
  drawdown override) → verbose stays.
- Up-leg approved (`allow_raise=True`) → verbose stays (the breakdown
  justifies the raise).

**Why.** Without the three-part predicate this clause could be
weaponized to hide stats whenever the system "decides against" anything
— a fallback-as-truth pattern. The strictness keeps the cleanup
surgical: compact form fires *only* on the founder's explicit
"forest-of-stats explaining 'no change'" pain point from 21/05/2026
~03:30.

**Pinned by:**
- `tests/test_meeting_ux_cleanup.py::TestAdaptiveBlockCompactOnGateClamp`
- `tests/test_meeting_ux_cleanup.py::TestAdaptiveBlockVerboseOnNaturalHold`
- `tests/test_meeting_ux_cleanup.py::TestAdaptiveBlockUpDirectionStaysVerbose`

**Scope.** `fmt_adaptive_risk_block` in `telegram_formatters.py`. Other
discipline-specific blocks (broker recon, campaign cards) follow §X1
not §X2 — they don't have a "system decided against" decision to
suppress.

**Open work flagged.** `risk_monitor.py:1242,1270-1305` builds the
adaptive-risk alert text *inline*, bypassing `fmt_adaptive_risk_block`.
Until that path is refactored to use the formatter, §X2 applies to
`/portfolio` only and the 14-line verbose shape will recur on any
direction-change alert from the monitor. Tracked as Tier-C C1 in the
meeting consolidation.

---

## §X3 — AI-copy variants MUST mirror Hebrew on §3-class wording

For every line that falls under a §3-class invariant (Mark §3 verbatim
honesty wording, §X1 source-disclosure, §X2 compact-on-clamp), the
AI-copy English variant MUST mirror the Hebrew variant's *semantic
shape*. Specifically:
- If the Hebrew variant drops the "cause unverified — manual
  verification required" preamble in the softened-band case, the
  AI-copy MUST also drop the English equivalent ("Cause unverified" /
  "Manual verification required").
- If the Hebrew variant keeps Mark §3 verbatim on Critical-residual,
  the AI-copy MUST keep the English equivalent.
- New §X1 source-disclosure ("גולמי" → "raw", "מותאם" → "adjusted")
  must mirror.

The AI-copy is NOT a translation toggle — it is the *machine-readable
honesty surface*. A divergence between Hebrew and English on §3-class
wording is a fallback-as-truth defect (the user reading the AI-copy
sees one story; the user reading the Hebrew sees another).

**Pinned by:**
- `tests/test_meeting_ux_cleanup.py::TestReconLineSoftenedVariant::test_softened_line_ai_copy_also_clean`
- `tests/test_meeting_fytd_pre_db_history.py::TestAiCopyMirrorsHebrew` (or
  equivalent — the AI-copy critical-residual variant test is the
  TESTING T-class gap flagged in `MEETING_UX_TESTING_FINDINGS.md`).

**Scope.** Applies to every formatter that emits an `ai_copy=True`
branch. New formatters must add `ai_copy=True` mirror tests when they
emit §3-class wording.

---

## Sign-off

— Mark, 2026-05-21. Codified into binding precedent. The next sprint
referee should cite these as `MARK_MEETING_UX §X1/§X2/§X3` (this file
is the canonical anchor).
