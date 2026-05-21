# MEETING_ENGAGEMENT_TESTING_FEASIBILITY — TESTING discipline, Wave 4

> Engagement-phase feasibility review. 21/05/2026. Read-only.
> Inputs: `MEETING_ENGAGEMENT_UX_SYNTHESIS.md` (C1/C4/C5/C2 approved; C3 deferred),
> `MEETING_ENGAGEMENT_MARK_RESEARCH_RULINGS.md` (§X4/§X5/§X6 binding + Q1/Q2/Q3
> rulings), `docs/TESTING_AND_DEPLOYMENT.md`, `docs/TESTING_GUIDELINES.md`,
> `MEETING_UX_TESTING_FINDINGS.md` (Sprint-25 byte-lock-vacuous lesson),
> `tests/test_meeting_ux_wave2.py` (yesterday's 22 pin anchor).
> Suite post-collect: **2587** (+22 vs the 2565 baseline in the UX-cleanup wave;
> Wave-2 landed `test_meeting_ux_wave2.py`).

## Headline verdict

Engagement-phase is testable on existing fixture plumbing, but it is the first
Sentinel surface where **honesty pins precede behavior pins** (§X4 verbatim,
§X5 absence-as-output, §X6 self-data-only). All three §X clauses MUST land as
explicitly-named test classes BEFORE any C1-C5 code merges — Mark binds this at
`MEETING_ENGAGEMENT_MARK_RESEARCH_RULINGS.md:253-254`. Coverage gate ratchet:
**70%** on the new engagement-phase modules (not 67%) — six new modules, all
behavior-bearing on text accuracy and audit chains. The Sprint-25 byte-lock-
vacuous lesson recurs HARD in C2 ("dedup key byte-identical" at
`MARK_RESEARCH_RULINGS.md:143-144`) — see §Byte-lock scrutiny below.

---

## §X4 Callback Honesty — pinning tests required

**Target file:** `tests/test_engagement_callback.py` (new). Required classes:

- `TestCallbackQuoteVerbatim` — write a synthetic `risk_journal.json` row with a
  reason field containing Markdown chars (`*`, `_`, `` ` ``), RTL marker
  `‏`, emoji (`📉`), Hebrew quotes (`"`), and a literal `"\n"`. Render the
  C1-S2 Callback. Assert `out_quoted_bytes == journal_row["reason"].encode("utf-8")`
  byte-for-byte. **No** `.strip()`, **no** `re.sub`, **no** unicode normalisation
  on the read path (the binding shape at `:172-174`).
- `TestCallbackCarriesDate` — assert the rendered surface contains
  `"מתוך היומן שלך מ-{date}"` where `{date}` is computed from
  `journal_row["timestamp"]` converted to Israel time (`ZoneInfo("Asia/Jerusalem")`,
  per `main.py:10`). Run TWICE with `freeze_time("2026-03-26 22:30 UTC")` (pre-DST)
  and `freeze_time("2026-03-27 22:30 UTC")` (post-DST IL clocks-forward) on a
  journal row whose UTC timestamp falls in the day-boundary window — assert the
  attributed date differs by exactly one day. Relative phrasing alone (`"פעם
  כתבת…"`) string-search BAN-listed.
- `TestCallbackFiredAuditRowWritten` — fire the Callback once; assert exactly one
  `audit_logger.log_action(ACTION_CALLBACK_FIRED, ...)` call (mock `audit_logger`
  per `tests/conftest.py` style), payload contains all 8 keys from
  `MARK_RESEARCH_RULINGS.md:49-52` (`anchor_rejection_id`, `anchor_ts`,
  `anchor_reason_text`, `surface_id`, `current_setup_bucket`, `similarity_score`,
  `current_heat_window`, `ts_fired`). **Audit row written EXACTLY ONCE per fire**
  — fire twice in one session, assert call count == 2 (one per fire, not one
  per session — dedup is at the surface level via cooldown, not at audit).
- `TestCallbackRoundTripsSpecialChars` — sibling of Verbatim above, this one
  re-reads the audit row's `anchor_reason_text` and asserts it equals the
  original journal bytes (catches a paraphrase-by-serialisation defect — UTF-8
  JSON round-trip on `‏` is non-obvious).

**Where this lives in plumbing.** `audit_logger.py:28-62` already defines the
`ACTION_*` constants pattern; `ACTION_CALLBACK_FIRED` slots there. The audit
mock pattern is established in `test_meeting_ux_wave2.py:264-303` (static-source
inspection); the new tests must use **runtime mock** (`mock_audit_logger`
fixture) because the assertion is on payload shape, not import presence.

## §X5 Silence-As-Beat — pinning tests required

**Target file:** `tests/test_engagement_silence_as_beat.py` (new). Required
classes:

- `TestMissedDayNoCheckinFired` — set `last_founder_interaction_ts = now - 49h`.
  Call every push surface (C1-S1 backfill, C2-S1 sizing nudge, C4-S1 weekly
  receipt, C5-S1 Monday R-dist) through the `should_suppress_for_silence_or_2r_or_settle()`
  helper. Assert: surface emits the welcome-back substantive snapshot OR nothing.
  String-search BAN-list: `"שמתי לב"`, `"אתה בסדר"`, `"לא פתחת"`, `"לא דיברנו"`
  — none of these may appear in any rendered output. Welcome-back string MUST
  carry `"נכון ל-"` per Q1 (`MARK_RESEARCH_RULINGS.md:36-39`).
- `TestMinus2RNoCallbackFired` — fixture: today's realized `R = -2.1`. Fire the
  Callback similarity-matcher; assert it returns `None` (no surface). Also fire
  C2-S1 sizing nudge on a watchlist symbol — assert suppression. C5-S1 Monday
  anchor is the only allowed surface on a -2R Monday (E4 §6 carve-out per
  `UX_SYNTHESIS.md:232-233`); pin separately if the carve-out applies.
- `TestSettleSuppression` — monkeypatch `get_risk_settle_info()`
  (`adaptive_risk_engine.py:87`) to return `{"hours_remaining": 5}`. Assert every
  push surface returns no emission; PULL-only surfaces (C4-S3 settle pull) DO
  emit (PULL is the inverse of suppression — verify the helper correctly
  distinguishes by surface_kind="push"/"pull").
- `TestHelperReturnsTrueExactlyWhenAnyConditionFires` — table-driven test on
  the helper itself: 8 input combinations × expected bool. Catches the AND-vs-OR
  defect that would silently let one branch dominate.

**Where this lives in plumbing.** New helper at
`engagement/silence_guard.py::should_suppress_for_silence_or_2r_or_settle(state)`
(scaffolding implied at `MARK_RESEARCH_RULINGS.md:230`); the helper is the
single chokepoint and is the test surface. `get_risk_settle_info` is the only
prod dep; freeze_time is used for missed-day.

## §X6 Process-Mirror — pinning tests required

**Target file:** `tests/test_engagement_process_mirror.py` (new). Required
classes:

- `TestNoMarketCommentaryAsLeadLine` — for each rendered C1-C5 surface, parse
  the first non-empty line; assert it contains a Tier-1 reference token (one of
  `"אצלך"`, `"שלך"`, `"היומן"`, `"הגייט"`, `"הסטאפ"`, `"לפני {n} ימים"`). The
  E3 register at `UX_SYNTHESIS.md:275-276` mandates `"אצלך"`/`"שלך"` — this is
  the back-translation test made executable.
- `TestNoPeerComparisonStrings` — string-search BAN-list across every formatter
  output: `"traders like you"`, `"average trader"`, `"השוואה"`, `"כמו טריידרים"`,
  `"המשתמש הממוצע"`, `"השוק עלה"`, `"השוק ירד"`, `"the market is telling"`.
- `TestNoYfinanceImportInEngagementModules` — static AST scan: for each new
  module in `engagement/` (Callback, sizing pattern, gate receipts, Monday
  anchor, silence guard), assert `import yfinance` and `from yfinance` do NOT
  appear. Tier-2 market data is JOIN-axis only (C5 regime × bucket); a direct
  yfinance import indicates surface code drifted into market narration. Static
  inspection pattern at `test_meeting_ux_wave2.py:259-262` is the model.
- `TestNoPeerStatsFieldsConsumed` — sibling AST scan: assert no engagement-phase
  module references `peer_*`, `cohort_*`, `community_*` field names.

---

## C1 — Callback engine, concrete test cases

**Target file:** `tests/test_engagement_callback_engine.py` (new; sibling of
honesty pins).

- **Near-identical setup matcher (positive):** seed journal with one
  null-reason-backfilled row at day -65: `{symbol: "MRVL", bucket: "VCP_MANUAL",
  heat_window: "S9+M21+", reason: "מדגם קטן מדי"}`. Fire the matcher with
  current setup `{symbol: "MRVL", bucket: "VCP_MANUAL", heat_window: "S9+M21+"}`.
  Assert the matcher returns the row (similarity_score ≥ threshold).
- **Negative match (different symbol):** same fixture, current setup `symbol:
  "NVDA"` — assert returns `None`. **Negative match (different regime):** same
  symbol, `heat_window: "S9-M21-"` — assert returns `None`. Both required;
  symbol-only matching would over-fire.
- **Day-60 cooldown — fires at 60, NOT at 30:** seed anchor at day -30, fire
  matcher → assert `None`. Re-seed at day -60, fire → assert returns the anchor.
  Boundary case: day -59 → `None`; day -60 → fires (gate is ≥60 per
  `UX_SYNTHESIS.md:59`). Freeze_time on both ends.
- **Cooldown re-fire:** after first fire, advance 13 days → fire again → assert
  `None` (max 1 Callback / fortnight / reason-bucket per `UX_SYNTHESIS.md:71`).
  Advance 1 more day (total 14d) → fires.
- **Verbatim integrity:** see §X4 above — this concept's quote-bytes test IS
  the §X4 test. Cross-link, do not duplicate.
- **Audit-log row written exactly once per fire:** see §X4
  `TestCallbackFiredAuditRowWritten` — same test, two concept anchors.

## C4 — Gate Receipt count + dollar-value saved, concrete test cases

**Target file:** `tests/test_engagement_gate_receipts.py` (new).

- **Count = clamped-AND-would-have-been-raise:** seed `rec_log` with 5 rows:
  3 with `gate_result.allow_raise=False` AND `direction="raise_intent"`;
  1 with `gate_result.allow_raise=False` AND `direction="hold"` (natural hold,
  not clamp); 1 with `gate_result=None` (no gate evaluated). Assert
  `count_clamps_saved(90d) == 3`. The natural-hold row MUST NOT inflate the
  count — `MARK_RESEARCH_RULINGS.md:101` binds this as §X1-class.
- **Anti-double-count:** same recommendation_id appears twice in `rec_log` (one
  initial fire, one re-evaluation 5min later — Sprint-25 §A.3 dedup class).
  Assert count == 1 (dedup key = `recommendation_id`, not row count).
- **Symmetric framing (sign-flip):** seed `rec_log` 90d window with 7 clamps
  AND a counterfactual backtest column showing 1 of those 7 would-have-been
  +1.5R if allowed. Assert C4-S1 rendered text contains the saved-count AND a
  "refused once incorrectly" framing token. If net counterfactual saved < 0,
  the entire surface MUST sign-flip and prefix with `"אומדן: היה עדיף שלא"` —
  pin both the count-only Phase-1 path (no $ framing) and the Phase-2 path
  with §X1 `"אומדן"` prefix.
- **`gate_result` field presence pin:** sibling to `test_meeting_ux_wave2.py`-
  style static inspection, assert `_log_recommendation` writes a `gate_result`
  key. Without this CLOSURE-FIX (`MARK_RESEARCH_RULINGS.md:103-105`,
  prerequisite step 3 of the build order), C4-S1 has no data to read.

## C5 — Monday R-dist, concrete test cases

**Target file:** `tests/test_engagement_monday_anchor.py` (new).

- **Week-bucket boundary stability:** seed a campaign closing 2026-05-17 22:55
  Israel-local (Sunday night, week N close). Run C5-S1 Monday-morning render
  with `freeze_time("2026-05-18 13:08 Israel")`. Assert the campaign IS counted
  in week N. Off-by-one Sunday-vs-Monday is the canonical
  `analytics_engine.py:372-376` reuse — the test must read the same Israel
  calendar helper, not its own datetime arithmetic.
- **DST boundary stability:** repeat with a campaign closing on
  2026-10-30 23:30 (one minute before IL clocks-back from IDT to IST). Assert
  it stays in week N, not week N+1. The bug class: UTC-only bucketing flips on
  fall-back nights.
- **D10 SKIP-AND-NULL propagation:** seed 4 closed campaigns — 3 with
  `regime="trend_up"`, 1 with `regime=None` (D10's skip-and-NULL ruling per
  Q3). Run the breakdown. Assert no crash, NO `KeyError` on the NULL row, AND
  the NULL row surfaces as `"regime-unclassified"` — NOT silently dropped, NOT
  imputed (per `MARK_RESEARCH_RULINGS.md:58-71`).
- **4-template rotation:** fire the Monday anchor on 4 consecutive Mondays with
  identical fixture. Assert the 4 leading-dimension tokens (mean/σ/tail/hit-rate)
  cover at least 3 of the 4 — pin the rotation, prevent the predictable-Monday
  failure mode (`UX_SYNTHESIS.md:247-248`).
- **Specificity gate on S3 (Phase-3, scope-flag now):** Friday signature line
  with generator returning a generic `"שבוע טוב!"` → assert MUTED (returns
  None / no emission). Generator returning `"הגדלות שנחסכו חסכו לך יותר"`
  (number-or-named-pattern) → assert emits.

## C2 — Sizing pattern (voice change), concrete test cases

**Target file:** extend `tests/test_risk_monitor.py` or new
`tests/test_engagement_sizing_voice.py`.

- **Byte-identity on dedup key (Mark's binding condition):** the existing
  campaign-id cooldown at `risk_monitor.py:1168-1174` (`sizing_leak_alerted`
  one-time flag) MUST be unchanged. **DO NOT** byte-lock via `git diff`
  (Sprint-25 vacuity class — see §Byte-lock below). Instead: import the keying
  function, snapshot its output dict for 4 representative inputs, assert
  identity vs a frozen literal in the test source. This is the Sprint-25
  P0-1/P0-2 lesson applied — semantic byte-identity, not VCS byte-identity.
- **Voice-change-only / numbers unchanged:** fire `_sizing_leak_alert` with a
  fixture from the existing `test_risk_monitor.py::test_sizing_leak_alert`. The
  rendered numbers (sizing_ratio, target_risk_usd, original_campaign_risk) MUST
  appear in the new voice unchanged. Pin: assert `"0.41"` (the ratio) appears
  in the output; assert all three numeric values appear; assert NEW voice
  tokens appear (`"או אל תיכנס"`, `"היית ב-"`); assert OLD push-up tokens
  absent (BAN-list: `"תגדיל"`, `"הגדל סייז"`).
- **§X6 cross-check:** static AST — `_sizing_leak_alert`'s module imports list
  unchanged before/after voice change; in particular, no new yfinance / no new
  peer-comparison imports.

---

## Coverage target for engagement phase

Current suite: 2587 tests / 73.20% / **gate 67%** (per
`TESTING_GUIDELINES.md:64-73`). Engagement phase adds ~6 new modules (Callback
engine, similarity matcher, silence guard, gate-receipt aggregator, Monday
anchor formatter, sizing-voice formatter).

**Recommended gate: 70% project-wide** (modest ratchet from 67%) **AND 80% per
new engagement module** (file-scoped `--cov` thresholds for the new files).
Rationale: the engagement-phase code is text-rendering with audit-log
side-effects — both are deterministic and 100%-coverable on hermetic fixtures
(no yfinance, no Supabase, no time). 80% per-file gives breathing room for
the unhappy paths that legitimately go uncovered (e.g. corrupt-config
fallback branches), but blocks any new module landing with no tests at all.

The Phase-1 per-surface pin count (rough budget): C5-S1 ~6 tests, C4-S1 ~5,
C2-S1 ~4, C1-S1 ~5, plus §X4 ~4, §X5 ~4, §X6 ~4 → **~32 new tests** to land
concurrently with Phase-1 code. This puts the suite at ~2619 after Phase-1.

## Byte-lock scrutiny

The Sprint-25 byte-lock-vacuous lesson (`MEETING_UX_TESTING_FINDINGS.md:86-91`):
`git diff -- <file>` on a clean CI checkout returns empty whether the code
matches or not — the assertion is vacuous. **Mark's C2 binding at
`MARK_RESEARCH_RULINGS.md:143-144` explicitly says "dedup key
byte-identically; new test asserts the campaign-id cooldown is unchanged."**
This is a new byte-lock candidate and it MUST NOT use the vacuous form.

The correct pattern (apply in `tests/test_engagement_sizing_voice.py`):

```python
# WRONG (Sprint-25 vacuous):
# diff = subprocess.run(["git", "diff", "--", "risk_monitor.py"], ...)
# assert "sizing_leak_alerted" not in diff.stdout  # vacuous on clean checkout

# RIGHT (semantic byte-identity):
import risk_monitor
key_before = {"key_format": "...", "fields": ("sym", "setup", "campaign_id")}
actual = risk_monitor.build_position_alert_key("MRVL", "VCP", "C-123")
assert actual == "MRVL|VCP|C-123"  # literal expected value frozen in test
```

A second byte-lock candidate is §X4 `TestCallbackQuoteVerbatim` — but that one
is correctly framed (compare `out_quoted_bytes == journal_row["reason"].encode()`,
not a git-diff). Use literal-bytes assertion only; never VCS-diff.

Third candidate to flag: the C5-S1 4-template rotation — the templates ARE
text byte-strings that users will see verbatim. Pin them with literal-string
assertions in the test source, not by reading the module's source file via
`open(__file__)` (the Sprint-25 P0-2 anti-pattern).

## Sign-off

Engagement phase is testable. The discipline ask is concrete: **§X4/§X5/§X6
pinning tests MUST land in the same PR (or BEFORE) the C1-C5 code**, per Mark's
binding at `MARK_RESEARCH_RULINGS.md:253-254`. Coverage gate: ratchet to 70%
project, 80% per new engagement module. The Sprint-25 byte-lock-vacuous
defect class recurs in C2 — fix it preventively with semantic byte-identity,
not VCS diff. Top-3 testing gaps if any concept ships without the above:
(1) Callback paraphrase-creep on RTL/emoji round-trip; (2) silence-as-beat
helper drift into passive-aggressive "we noticed" wording; (3) C2 dedup-key
regression from a voice-only refactor that accidentally re-keyed the cooldown.

— TESTING discipline, engagement-phase feasibility, Wave-4, 21/05/2026.
Read-only. Binds Phase-1 build via §X4/§X5/§X6 pinning prerequisite.
