# MEETING_ENGAGEMENT_MARK_RESEARCH_RULINGS — Wave-3 Joint Ruling

> Mark (rulings/precedent) + Research (data-feasibility), jointly. 21/05/2026.
> Read-only. Binds Phase-1/2/3 engagement-phase build.
> Inputs: `MEETING_ENGAGEMENT_UX_SYNTHESIS.md`, `MEETING_ENGAGEMENT_RESEARCH.md`,
> `MARK_MEETING_UX_RULINGS §X1/§X2/§X3`, `MARK_SPRINT25_RULINGS §3`, `CLAUDE.md`.

## Joint posture

The engagement phase is the first Sentinel surface that is not a math/risk
correction — it is a behavioural mirror. That makes the §3-class honesty rules
*more* load-bearing, not less: a mirror that paraphrases the founder, smooths a
cached number, or celebrates a clamp without showing its cost is
fallback-as-truth in engagement-clothes. Mark's lens: every surface inherits
existing red lines (no fallback-as-truth, no R/NAV math drift, no secure_runner
bypass, no `telegram_bot.py` wholesale rewrite). Research's lens: four of five
concepts ship on existing Tier-1 data; C3 alone is gated on D2, C5-S2 alone on
D10 — the rest is **logging discipline**, not new derivation. We
APPROVE_WITH_CONDITIONS on four concepts, DEFER C3, codify three new §X clauses
(Callback Honesty, Silence-As-Beat, Process-Mirror), and extend §X1 to cover
welcome-back + audit_logger event types.

---

## Deliverable 1 — Open question rulings

### Q1 — §X1 source-disclosure on missed-day welcome-back

**Ruling: YES — §X1 binds.** Welcome-back numbers computed during a 2+ day
absence MUST carry a freshness label (`נכון ל-{ts}` minimum; `אומדן` /
`מבוסס על` when underlying input was cached/fallback). §X1's binding shape
was always a *class*, not a single case (`MARK_MEETING_UX §X1:46`:
"applies to any future disclaimer-style softening"). A welcome-back surface
is by definition a transformation the founder did not witness — in-class.
UX recommendation at `UX_SYNTHESIS.md:308-311` is correct; this makes it
binding precedent. Pinning:
`tests/test_engagement_welcome_back.py::TestWelcomeBackCarriesFreshnessLabel`
asserts `נכון ל-` appears whenever NAV/exposure was read from
`nav_source!="live"`. **MARK §X1 EXTENSION — binding.**

### Q2 — The Callback audit rule

**Ruling: YES — APPROVE `ACTION_CALLBACK_FIRED`.** Verbatim journal text is
not founder-asserted-data-class (that class transforms a *number*). But the
*act* of selecting which past quote to surface at which present setup IS a
Sentinel decision, and every Sentinel decision rendered to the founder must
be audit-reconstructable (pattern: `audit_logger.py:53`
`ACTION_POSITION_STATE_TRANSITION`). Required binding shape: new constant
`ACTION_CALLBACK_FIRED`; payload `{anchor_rejection_id, anchor_ts,
anchor_reason_text, surface_id, current_setup_bucket, similarity_score,
current_heat_window, ts_fired}`; founder's typed text NEVER modified —
referenced by id (see §X4). Without this, a future operator reading
`🧾 הפעולות שלי` cannot reconstruct *why* Sentinel quoted what when.
**APPROVE with the payload above as binding shape.**

### Q3 — D10 regime-at-close write-discipline

**Ruling: SKIP-AND-NULL.** When `compute_market_regime`
(`engine_core.py:570-620`) returns confidence below 0.70 (same as C5-S2's
UX gate), Sentinel MUST NOT write the label with a side-flag; it MUST omit
the column (NULL). **Research scope:** D10 is not currently stored at all
(`RESEARCH.md:168`); greenfield Tier-3, Phase-2. Choice (a) write label +
confidence with UX-side gate vs (b) write only when conf ≥ 0.70. Mark
rules (b): option (a) presents a label-shaped value any future aggregator
treats as truth unless it explicitly joins on the confidence flag — the
silent-zero / fallback-as-truth defect class (Sprint-25 §1.8). Option (b)
makes "I don't know" a first-class state. C5-S2's UX already handles
missing-regime ("משטר לא ברור", `UX_SYNTHESIS.md:234`). **Founder gate:**
D10 is behavior-bearing; per Sprint-25 Rulings 2/6, founder per-item
go-ahead required before Phase-2. **Research COMPLETE; Mark rules
SKIP-AND-NULL; founder-gated for build.**

---

## Deliverable 2 — Concept rulings

### C1 — הספר מדבר חזרה (HEADLINE)

**Ruling: APPROVE_WITH_CONDITIONS.** C1 metabolizes the literal
engagement-diagnosis (14:22 19/05 "ללא הסבר" — `UX_SYNTHESIS.md:21-25`).
הספר ≠ המנטור — a quote cannot be a verdict, which prevents §3-class
violation. **Conditions:** MARK §X4 (Callback Honesty, D3) verbatim +
date-attributed; MARK §X1 EXTENSION (Q1) on the 14d backfill ("לפני 14
יום…" date is anchor, no rounding); Q2 binding `ACTION_CALLBACK_FIRED`
shape; U4 closure non-negotiable before C1 Phase-1 ships
(`UX_SYNTHESIS.md:74` §10-R3, Mark ratifies). **Data feasibility:** T1.1
(`adaptive_risk_engine.py:109-131`, 500-row FIFO at `:126`) + T1.2
(`:877-937`) live. Callback similarity-match uses T1.4 + T1.5 (per-render,
no new derivation). **Phase-1 unblocked.** **Risk Mark catches:** "מבלבל
וארוך" recency pain means S1 backfill prompt MUST stay ≤2 sentences +
chips; free-text input is its own screen, not appended — otherwise risks
the forest-pattern §X2 was written against.

### C4 — קבלות מהמנטור

**Ruling: APPROVE_WITH_CONDITIONS.** C4 *justifies* the engagement
(`UX_SYNTHESIS.md:199-200`). Phase-1 count-only (no $) is correct: D11 is
L-complexity counterfactual; founder-pain on confidence-without-evidence is
exactly what §X1 prevents. **Conditions:** MARK §3 (Sprint-12) symmetric
clamp framing — when net clamp-cost > clamp-saved on 90d window, sign-flip
honestly (`UX_SYNTHESIS.md:194` §10-R1, Mark ratifies binding); MARK §X1
when D11 ships Phase-2 — every $ value carries "אומדן" + methodology
pointer; B-tier logging change — `gate_result` field on `_log_recommendation`
(`adaptive_risk_engine.py:849-874`); confirmed gap at `RESEARCH.md:37`;
CLOSURE-FIX class per Sprint-25 Ruling 2; founder-per-item go-ahead.
**Data feasibility — ruling on UX claim "T1.3 has a gap — blocks Phase-1?"**
*Gap does NOT block Phase-1 IF the logging change ships concurrently.*
S-complexity (one field, one fixture). Ship logging first, C4-S1 second,
same sprint — **Phase-1 unblocked**. **Risk:** R1 (one-sided celebration)
is §X1-class fallback-as-truth — Mark elevates from "risk" to binding
(§X4/§X6). R2 honestly bounded by count-only Phase-1.

### C5 — השוק הוא מזג אוויר

**Ruling: APPROVE_WITH_CONDITIONS** for S1+S3; **DEFER S2** until Q3 (D10
founder gate) executes. S1 (Monday R-distribution) is the highest-leverage
lowest-build engagement surface: T1.6 live (`engine_core.py:966-1066`), no
new derivation. S3 (Friday signature line) is the Callback-payoff at
week-cadence with the HARD specificity-gate. **Conditions:** MARK §3
verbatim (Sprint-15) — specificity gate binding; if generator can't produce
a number-or-named-pattern line, MUTE — NEVER emit "שבוע טוב!"
(`UX_SYNTHESIS.md:239`); MARK §X6 (D3) — C5 is the highest-temptation
concept for drifting into market-narration, §X6 fence non-negotiable; R3
4-template rotation binding — if removed in any future refactor, the
Monday anchor MUST be muted entirely. **Data feasibility:** T1.6 + T1.4
live. S1+S3 ship on existing data; S2 is the only D10-blocked surface.
**Risk Mark catches:** any future temptation to name SPY/QQQ levels in
S1/S3 is a §X6 violation (only *founder's R in that weather*).

### C2 — הדפוס מדבר

**Ruling: APPROVE_WITH_CONDITIONS.** C2-S1 is voice-only change on existing
path (`risk_monitor.py:497-540, 1168-1174`); Tier-A polish in Sprint-25
vocabulary. S2/S3 Phase-2/3. **Conditions:** MARK §3 anti-list (Sprint-12)
— existing push-up-size verb BANNED; voice preserves *"או אל תיכנס"*
escape-hatch; MARK §X6 — zero market-context; MARK §3 F7 binding — T1.7
ratio uses cent-rounded denominator (`engine_core.py:1006`), no shortcut
averaging; R2 bounded by T1.12 settle-period suppression. **Data
feasibility:** T1.7 + T1.5 + T1.15 live on-render. No new derivations.
**Risk vectors UX missed:** "Voice-only change" on `_sizing_leak_alert` is
still a behavior change on a `risk_monitor`-fired push (Sprint-25 §A.3:
every recurring push needs cooldown/dedup proof). **Mark binds: voice-
change refactor MUST preserve the dedup key at `:1168-1174` byte-identically;
new test asserts the campaign-id cooldown is unchanged.**

### C3 — השעה הטובה

**Ruling: DEFER.** C3 is gated on D2 which Research flags as M-complexity
with a real intraday-timestamp question (`RESEARCH.md:160`: *"`trade_date`
precision unclear; may need IBKR-Flex enrichment"*). Until verified, S1+S2
risk `n=42`-style numbers that are noise-on-cached-data — exactly the
§X1/Sprint-12 §3 failure mode. **Conditions to lift DEFER (any one):**
(a) Research verifies `trade_date` carries hour-precision on ≥90% of
post-deploy BUYs; (b) IBKR-Flex enrichment scoped + founder-approved as
separate Tier-3 prerequisite; (c) C3 re-scoped to weak-day (D1,
S-complexity). **Risk:** UX flagged R3 (collides with U1 — `risk_monitor`
bypasses `fmt_adaptive_risk_block`); Mark ratifies U1 closure as binding
precondition to lifting C3's DEFER.

---

## Deliverable 3 — Proposed new §X clauses (binding precedent)

### §X4 — The Callback Honesty Clause

**Statement.** When Sentinel quotes the founder's own past journal text
(any C1 Callback, any cross-Callback in C2/C3/C4/C5), the quote MUST be:
(1) **verbatim** — character-for-character; no normalisation, spell-fix,
paraphrase, or truncation without `[…]` marker; (2) **date-attributed
inline** — "מתוך היומן שלך מ-{date}"; relative phrasing alone ("פעם
כתבת…") banned because it strips the audit anchor; (3) **source-id
auditable** — every fire logs `ACTION_CALLBACK_FIRED` (Q2). **Pinning:**
`tests/test_engagement_callback.py::TestCallbackQuoteVerbatim` (quoted
bytes == journal-row bytes), `::TestCallbackCarriesDate`,
`::TestCallbackFiredAuditRowWritten`. **Scope:** C1-S2, all
cross-Callbacks (`UX_SYNTHESIS.md:112-113`), any future formatter reading
`risk_journal.json` text. **Failure mode prevented:** paraphrase-creep —
the Callback's emotional weight depends on the founder recognising *his
own past words*; any normalisation destroys the mirror function. §3-class
verbatim-honesty applied to founder-asserted *text*.

### §X5 — The Silence-As-Beat Clause

**Statement.** When E4 missed-day applies (silent ≥48h), -2R rule applies
(today ≤ -2R), or T1.12 settle-period applies (`hours_remaining > 0`), the
**absence** of a Sentinel message IS the surface. BANNED: "שמתי לב שלא
פתחת" / equivalent; "אתה בסדר?" / engagement-checkin; re-engagement
prompts; any meta-message *about* the silence. The next emission is the
welcome-back surface — substantive state-snapshot, freshness-labeled per
Q1, never a comment on the gap. **Pinning:**
`tests/test_engagement_silence_as_beat.py::TestMissedDayNoCheckinFired`,
`::TestMinus2RNoCallbackFired`, `::TestSettleSuppression`. **Scope:**
every push surface across C1-C5; required pre-check helper
`should_suppress_for_silence_or_2r_or_settle(state) -> bool`. **Failure
mode prevented:** passive-aggressive engagement-mining. A "we noticed"
message converts silence into a metric Sentinel mines — the trap
CLAUDE.md's accuracy-over-confidence posture rejects.

### §X6 — The Process-Mirror Clause

**Statement.** Every engagement-phase surface (C1-C5, all phases) uses
**only self-data** (Tier-1 per RESEARCH). Banned: market commentary as
primary content ("השוק עלה +1.2%"); peer comparison ("traders like you",
"average trader", "השוואה"); generic market narration without a self-data
join axis (Tier-2 appears ONLY as JOIN axis on Tier-1, per
`UX_SYNTHESIS.md:257-258`); "the market is telling you X" /
market-as-character. Weather, not actor. **Pinning:**
`tests/test_engagement_process_mirror.py::TestNoMarketCommentaryAsLeadLine`
(first sentence contains a Tier-1 reference); `::TestNoPeerComparisonStrings`
(string-search ban-list). **Scope:** every engagement-phase formatter;
new formatters MUST declare which Tier-1 asset they consume. **Failure
mode prevented:** drift from "Sentinel about him" to "Sentinel about the
market" — the concept-collapse that makes engagement indistinguishable
from generic market commentary.

---

## Mandatory Phase-1 build order (Mark + Research consensus)

UX synthesis Phase-1 plan at `UX_SYNTHESIS.md:280-289` is correct but
unordered. Dependency chain is non-negotiable:

1. **U1 closure** — route `risk_monitor.py:1242,1270-1305` through
   `fmt_adaptive_risk_block` (`MARK_MEETING_UX §X2:99-104`).
2. **U4 closure** — `ACTION_RISK_REJECT` + surfacing in
   `telegram_audit_review.py:41-46`. Non-negotiable before C1.
3. **`gate_result` field on `_log_recommendation`**
   (`adaptive_risk_engine.py:849-874`). CLOSURE-FIX; founder per-item.
4. **`ACTION_CALLBACK_FIRED` constant + payload** (Q2). Tier-A.
5. **`should_suppress_for_silence_or_2r_or_settle()` helper** (§X5).
6. **C5-S1** Monday R-distribution — no new derivation.
7. **C2-S1** voice change — Tier-A; dedup key byte-identical.
8. **C4-S1** count-only — depends on (3).
9. **C1-S1** backfill prompt — depends on (2).

Steps 1+2+3 are prerequisites; 4+5 infrastructure; 6-9 shipped surfaces.
The Callback itself (C1-S2) is Phase-3 day-~60, gated on backfill producing
≥1 typed-reason row in matching bucket.

---

## Open work flagged to Wave 4 (the 6 internal disciplines)

- **Formatters.** Does `fmt_adaptive_risk_block` need a welcome-back branch
  (Q1)? Scope freshness-label argument signature.
- **Repository.** Clean read API for `risk_journal.json` typed-reason rows,
  or direct file reads in C1's matcher? §X4 verbatim binds the read path —
  paraphrase-by-reformatting is a defect.
- **Risk-config.** D10 (Q3) schema — `trades` column vs new
  `campaign_close_snapshot` table; founder-gated.
- **Audit-logger.** Add `ACTION_CALLBACK_FIRED` + `ACTION_RISK_REJECT`;
  update `telegram_audit_review.py:41-46` to surface them on "הפעולות שלי".
- **Testing.** Author §X4/§X5/§X6 pinning tests BEFORE any C1-C5 code lands
  (Sprint-25 §A.3 binding).
- **Deployment.** D10 migration is the only Phase-2 schema change; scope
  rollback per `docs/SAFE_CHANGE_PROTOCOL.md`.

---

## Sign-off

— **Mark** (rulings/precedent referee): five concept rulings
(C1/C2/C4/C5 APPROVE_WITH_CONDITIONS; C3 DEFER); three §X clauses (§X4
Callback Honesty, §X5 Silence-As-Beat, §X6 Process-Mirror); §X1 extended to
welcome-back (Q1); `ACTION_CALLBACK_FIRED` audit-shape ratified (Q2); D10
skip-and-NULL (Q3, founder-gated).

— **Research** (data-feasibility): Tier-1 inventory supports C1/C2/C4/C5
Phase-1 on existing data; C3 deferred pending D2 intraday-timestamp
verification; T1.3 logging gap (`adaptive_risk_engine.py:849-874`)
confirmed as concurrent-blocker not Phase-1 blocker; D10 confirmed
not-currently-stored (`engine_core.py:570-620` per-render only).

— Joint, Wave-3 engagement-phase ruling, 21/05/2026. Read-only.
Binds Wave-4 (6 internal disciplines) and Phase-1/2/3 build.
