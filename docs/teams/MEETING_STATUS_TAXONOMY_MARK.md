# Mark Ruling — Position-Status Taxonomy (21/05/2026)

**Reviewer:** Mark (precedent referee). **Date:** 2026-05-21.
**Scope:** "🔴 שבור" default-on-low-chart-score (JPM 1d flat, PLTR 20d
stalled in `/portfolio`). **Anchors:** Sprint-12 §3 (fallback-as-truth),
MARK_MEETING_UX §X1/§X2/§X3, MARK §X4/§X5/§X6. Code sites:
`engine_core.map_score_to_status` (`:366-379`) and
`engine_core.compute_position_state` (`:2047-2155`).

## Ruling on existing "🔴 Broken" default

**VIOLATES Mark §3 (Sprint-12).** `map_score_to_status` (`:369`) sets
`status = "🔴 Broken"` as *initialised default*, upgrading only on positive
band-hits. Any score < 40 with no other signal gets a fabricated "broken"
verdict — no stop-breach, no violation score, no structural predicate.
Textbook §3 defect: ambiguous cause → "cause unverified — manual
verification required", never a fabricated verdict.

Sibling `compute_position_state` (`:2101-2106`) shows the honest shape:
BROKEN fires iff `_price_through_stop(...)` OR `violation_score >=
_VIOLATION_BROKEN` (=6, `:1792`). `map_score_to_status` has no predicate
— it leaks absence-of-positive-signal as a negative verdict. "Users
understand it as a heuristic" fails: the founder did not, on JPM and
PLTR. §3 binds on the surface, not intent. **Status:** VIOLATES.

## Boundary rulings (broken / fresh / stalled — strict predicate per §3)

UX picks tokens; the predicates are non-negotiable.

1. **"🔴 שבור" — REQUIRED iff** `_price_through_stop(...) == True` (`:2102`)
   **or** `violation_score >= _VIOLATION_BROKEN` (=6, `:1792, 2104`). Score
   < 40 alone does **not** qualify.
2. **"🌱 טרי / במעקב" — REQUIRED iff** `age_days <= _PROVING_MAX_DAYS`
   (`:1786`) AND no BROKEN predicate AND chart score < 40. §3 forbids
   "Broken" — position has not had time to prove or break.
3. **"⏳ דריכה / הון מת" — REQUIRED iff** the existing DEAD_MONEY predicate
   holds (`:2137-2145`): `age_days >= _DEAD_MONEY_MIN_DAYS` (=8), R within
   `[_DEAD_MONEY_MIN_R, _DEAD_MONEY_MAX_R]`, `has_new_high_since_entry ==
   False`, no BROKEN. §3 forbids "Broken" — no structural break, only lack
   of movement.
4. **Residual — REQUIRED when no predicate fires.** Sprint-12 §3 verbatim:
   `‏❓ סיבה לא מאומתת — נדרשת בדיקה ידנית`. No fabricated verdict.

## Action-line wording boundary

`build_management_action` (`engine_core.py:381-421`) emits directive
Hebrew verbs per status. Sprint-12 §3 anti-list forbids "directive verbs"
and fabricated "you should X" when the predicate is not satisfied.

- **🔴 שבור** (strict predicate): directive verbs permitted. Current
  `יציאה / הידוק מידי` (`:410`) stays.
- **🌱 טרי / במעקב**: directive verbs **forbidden**. Acceptable shape:
  `מעקב — טרם הוכיחה את עצמה ({age_days} ימים)`. No "צא"/"הדק"/"הוסף"/
  "צמצם". Mirrors Sprint-12 §1.2 T7 "zero imperative trading verb".
- **⏳ דריכה / הון מת**: directive verbs **forbidden** except
  `אין מהלך מאז כניסה ({age_days} ימים) — שקול בחינה`. "שקול בחינה" is
  the maximum strength permitted.
- **❓ סיבה לא מאומתת**: action MUST be exactly `נדרשת בדיקה ידנית`.

## §X7 — Verdict-Honesty Clause (proposed text)

> **§X7 — Verdict-Honesty Clause.** A label asserting a position state
> (broken, stalled, fresh, healthy, dead-money, runner, etc.) MUST have an
> **explicit positive predicate** satisfied on the position's actual data.
> A label MUST NOT be assigned as the *default branch* of a classifier
> (the `else`, the initialised value, the "no other rule matched") when
> the predicate is not independently true. When no predicate satisfies,
> the classifier MUST emit the Sprint-12 §3 "cause unverified — manual
> verification required" shape instead of a fabricated verdict.
>
> Binding for all future classifier additions: every label constant MUST
> be paired with a documented predicate function. A drift test MUST
> assert `set(labels) == set(predicates)`. Adding a label without a
> predicate, or a predicate that resolves to "default fallthrough," is a
> §X7 violation and a release-blocker.
>
> Cross-refs: AGENTS #1, Sprint-12 §3, §X1 (source disclosure),
> §X2 (precise predicate for compact form). §X1/§X2 govern the breakdown
> surface; §X7 governs the **label surface** — the general case.

## §X3 reaffirmation on AI-copy mirror

§X3 binds unmodified. Today's "🔴 שבור" → "🔴 Broken" mirror is honest only
because both are equally wrong. Once Hebrew adopts the predicate-anchored
tags, AI-copy MUST mirror **semantically, not literally**: "🌱 טרי / במעקב"
→ "🌱 Fresh — watching" (NOT "Broken"); "⏳ דריכה / הון מת" → "⏳ Stalled /
Dead Money"; "❓ סיבה לא מאומתת — נדרשת בדיקה ידנית" → "❓ Cause unverified
— manual verification required" (§3 English mirror). A divergence where
Hebrew refused "broken" but AI-copy still emits "Broken" is the §3 defect
§X3 prevents. Pin to a new mirror test in `tests/test_meeting_ux_cleanup.py`
when the taxonomy ships.

## Cross-classifier consistency ruling

Two classifiers exist and CAN emit contradictory tags today:
`map_score_to_status` (`:366-379`, /portfolio chart card, score-band
heuristic) and `compute_position_state` (`:2047-2155`, `_RULESET`,
position lifecycle). Example: JPM score=35, stop intact, violations=0 →
chart card says "🔴 Broken", lifecycle says "PROVING/WORKING". Founder
sees both, no precedence.

**Ruling — `compute_position_state` takes priority on user-facing
status.** It is predicate-anchored (§X7-compliant by construction), it is
what `_RULESET` and Open Tasks consume (`MARK_SPRINT12_RULINGS.md` §1.7
drift-test-guarded), and it already carries the BROKEN/DEAD_MONEY/PROVING
distinctions the new taxonomy needs.

`map_score_to_status` MAY survive as a *descriptive score line* (e.g.
`ציון תרשים: {score}/100`) — but MUST lose its verdict nouns
("🔴 Broken"/"🟢 Healthy") and MUST NEVER override
`compute_position_state.label`. Any future code emitting a status token
to Telegram, Dashboard, or AI-copy consults `compute_position_state`
first. Score band stays as a numeric/colour cue only.

## Sign-off

Codified. Cite as **MARK_TAXONOMY §X7** (this file is the canonical
anchor). §X7 supersedes any future "default-bucket" label proposal
lacking a positive predicate. — Mark, 2026-05-21.
