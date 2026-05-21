# MEETING_UX — Mark Rulings on Recon Line + Adaptive Block Cleanup

**Reviewer:** Mark (rulings/precedent referee). **Date:** 2026-05-21.
**Branch:** `claude/review-system-audit-FBZ2h`. **Scope:** commits `3ac93e8`
(F-YTD contract+classifier), `fdd4e84` (CLI helper), `e9872f8` (recon line +
adaptive block cleanup) — UX variant-branching vs the Mark §3 verbatim
invariant (`MARK_SPRINT15_RULINGS.md §3`, lines 62–67). **Bar:** Sprint-25
Ruling 2 polish↔CLOSURE-FIX boundary; "when unsure whether a change is
cleanup or behavior, it is behavior" (`MARK_SPRINT24_RULINGS.md` Ruling 1,
lines 21–58 / CLAUDE.md).

---

## §A. Mark §3 verbatim invariant — preserved where Critical persists — PASS

The exact Sprint-15 §3 Hebrew string (`MARK_SPRINT15_RULINGS.md:64`) —
*"מצב התאמה מול ברוקר: <Band>. פער $<gap>. הסיבה לא אומתה — ייתכן …
דורש אימות ידני."* — is emitted verbatim at `telegram_formatters.py:1103-1107`
on every `band == "Critical Data Gap"` path, including residual-after-
disclaimer (the `band_softened` predicate at `:1079-1080` explicitly excludes
Critical). AI-copy English §3 at `:1086-1094` mirrors verbatim. Default
no-adjustment byte-identity pinned by
`tests/test_meeting_ux_cleanup.py::TestReconLineNoAdjustmentByteIdentical:97-111`;
Critical-residual preservation by `TestReconLineCriticalResidualKeepsMarkWording:77-94`.
The §3 "asserted cause is forbidden" half (`MARK_SPRINT15_RULINGS.md:67`) is
intact — the softened variant lists the *operator-declared* cause, not a
system-asserted cause.

## §B. Softened-band variant — sound interpretation — PASS (+ §X1)

§3 forbids "stating … as fact" what is *unverified* (`MARK_SPRINT15_RULINGS.md:67`).
Once the operator sets `pre_db_realized_pnl_estimate` (commit `3ac93e8`:
classifier `telegram_formatters.py:1004-1005`; defensive `min()` pinned by
`tests/test_meeting_fytd_pre_db_history.py::TestDefensiveInvariant`), the
cause is no longer unverified — it has been declared. Re-asserting "cause
unverified / manual verification required" after the operator has declared
the cause would itself violate §3 in the opposite direction (asserting
uncertainty as fact when certainty has been declared). Numeric truth is
**not hidden** — `:1099-1102` emits גולמי + מותאם side-by-side (pinned
`test_softened_line_omits_unverified_preamble:52-66`), satisfying CLAUDE.md
"do not silently present fallback data as exact truth". Same shape as Mark
§3 price-fallback labelling (`MARK_SPRINT12_RULINGS.md §3 "Price-fallback
labelling, invariant #1"`): disclose-don't-hide. Breakdown-surface duty
codified as §X1 below.

## §C. Compact-on-gate-clamp precedent — admissible; codify as §X2 — PASS

The compact branch (`telegram_formatters.py:393-425`) fires **only** when all
three hold: `risk_raise_gate.evaluated is True` AND `allow_raise is False`
AND `direction == 'hold'` (`:401-405`). Precise, machine-checkable; **not** a
generic "hide info on hold". On this exact path the engine has explicitly
decided against the raise — the score/win-rate/heat-factor breakdown
justifies *change*, but no change is happening, so the breakdown actively
misleads (`score=100` + "hold" reads as a contradiction). Safety: ⛔ blocking
reason survives `:413-417` (pinned `test_compact_path_keeps_blocking_reason:163-167`);
current/recommended pct+USD survive `:410-411` (pinned
`test_compact_path_keeps_current_recommendation:169-173`). Severity (Sprint-25
Ruling 4): **P3 polish**; no R/NAV/exposure/campaign math touched (Sprint-25
Ruling 3 / AGENTS.md #2/#8 intact). Sprint-25 Ruling 2 ADMISSIBLE — every
non-clamp shape is byte-identical. Codify as §X2 so future
"collapse-on-system-decided-no" cleanups cite the two-part predicate.

## §D. Natural-hold dual-path — REQUIRES_FOLLOWUP (codify §X2)

The dual-path itself is acceptable: natural hold (no `evaluated` flag) keeps
the verbose breakdown — pinned `TestAdaptiveBlockVerboseOnNaturalHold:189-223`.
The compact-vs-verbose split tracks exactly the existence of an explicit
system decision against the raise; that is the correct boundary.
**Followup:** without a written rule, a future team could replicate the
*shape* ("hide breakdown on context X") without the *condition* ("…only when
the system has itself decided against the action the breakdown justifies") —
the weaponization risk. With §X2 written the dual-path is bounded; without
it the precedent leaks. Prior precedent: Sprint-22 §3 anti-masking
(`MARK_SPRINT22_RULINGS.md §3`, lines 45–82, "#1 honest-empty distinct" at
`:82`) — don't collapse states the operator needs to distinguish; reused
here for "system-decided-no" vs "no-decision-made".

## §E. AI-copy mirror — must match Hebrew on §3-class wording — PASS (+ §X3)

AI-copy branch (`telegram_formatters.py:1081-1096`) mirrors Hebrew exactly:
softened-band → English clean (`:1083-1085`); residual-Critical → verbatim
English §3 (`:1087-1090`). Pinned `test_softened_line_ai_copy_also_clean:68-74`.
**Binding:** AI-copy MUST mirror Hebrew whenever the Hebrew variant is a §3-
derived honesty surface — divergence would split §3 into two contradictory
surfaces (the "R changes depending on which screen" defect flagged in
`MARK_ALIGNMENT_REVIEW.md §2b`, Sprint-10 Directive #5). Codified as §X3.

---

## New rulings (proposed)

- **§X1 (followup, P2).** When a softened-band recon variant is emitted, the
  AI export breakdown (`fmt_broker_reconciliation_breakdown`,
  `telegram_formatters.py:1127+`) MUST continue to carry both the raw and
  adjusted gap and the disclaimer source. Already true (`:1160-1179`); pin
  as binding so a future "simplify breakdown" cleanup cannot delete it.
- **§X2 (precedent, P3).** "Compact-on-system-decision-against." A presenter
  may collapse decision-justifying breakdown lines to a compact variant
  **iff** the system has emitted an explicit, machine-checkable decision
  against the action the breakdown would justify (e.g. gate
  `evaluated=True` AND `allow_raise=False`). The decision-against MUST
  itself survive in the compact output. Natural-no-decision states KEEP the
  verbose path. Future cleanups citing §X2 MUST point to the specific
  decision predicate.
- **§X3 (binding, P1).** Honesty-wording variants (§3-derived) MUST be
  mirrored byte-for-byte in shape between the Hebrew Telegram surface and
  the English/AI-copy surface. A regression test pinning *both* surfaces is
  required for any new §3-class variant. Current
  `TestReconLineSoftenedVariant` (`:52-74`) is the binding pattern.

## Sign-off (Mark)

§A PASS · §B PASS · §C PASS · §D REQUIRES_FOLLOWUP (codify §X2) · §E PASS.
3 new rulings proposed (§X1, §X2, §X3). Mark §3 verbatim invariant intact on
Critical-residual and default paths; softened-band is a sound *interpretation*
of §3 (cause operator-declared → "cause unverified" itself becomes a false
assertion of uncertainty). Compact-on-gate-clamp is a clean precedent for
collapsing decision-context noise when the system has decided against the
action — admissible Sprint-25-Ruling-2 polish, requires §X2 codification
(two-part predicate: evaluated AND decided-against). §X3 binds AI-copy to
Hebrew on honesty-wording variants. — Mark, 2026-05-21
