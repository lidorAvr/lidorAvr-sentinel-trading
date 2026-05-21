# MEETING_ENGAGEMENT_TESTING_FEASIBILITY — TESTING discipline, Wave 4

> Engagement-phase feasibility review. 21/05/2026. Read-only.
> Inputs: `MEETING_ENGAGEMENT_UX_SYNTHESIS.md` (C1/C4/C5/C2 approved; C3 deferred);
> `MEETING_ENGAGEMENT_MARK_RESEARCH_RULINGS.md` (§X4/§X5/§X6 + Q1/Q2/Q3);
> `docs/TESTING_AND_DEPLOYMENT.md`, `docs/TESTING_GUIDELINES.md`;
> `MEETING_UX_TESTING_FINDINGS.md` (Sprint-25 byte-lock-vacuous lesson);
> `tests/test_meeting_ux_wave2.py` (yesterday's 22-pin anchor).
> Suite post-collect: **2587** (+22 vs the 2565 UX-cleanup baseline).

## Headline verdict

Engagement phase is testable on existing fixture plumbing (`tests/conftest.py`
mocks, `tmp_path`, `freeze_time`, AST static inspection per
`test_meeting_ux_wave2.py:259-262`). It is the first surface where **honesty
pins precede behavior pins**: §X4 verbatim, §X5 absence-as-output, §X6
self-data-only. Mark binds all three §X test files to land BEFORE any C1-C5
code merges (`MARK_RESEARCH_RULINGS.md:253-254`). Coverage ratchet: **70%
project, 80% per new engagement module**. Sprint-25 byte-lock-vacuous defect
recurs hard in C2 (`MARK_RESEARCH_RULINGS.md:143-144` "dedup key
byte-identically") — must be framed semantically, not via `git diff`.

## §X4 Callback Honesty — pinning tests required

**File:** `tests/test_engagement_callback.py` (new). Required classes:

- `TestCallbackQuoteVerbatim` — synthetic `risk_journal.json` row with Markdown
  chars (`*`, `_`, `` ` ``), RTL marker `‏`, emoji (`📉`), Hebrew quotes, literal
  `\n`. Assert `out_quoted_bytes == journal_row["reason"].encode("utf-8")`
  byte-for-byte. No `.strip()`, no `re.sub`, no unicode-normalisation on the
  read path (binding shape `MARK_RESEARCH_RULINGS.md:172-174`).
- `TestCallbackCarriesDate` — assert surface contains `"מתוך היומן שלך מ-{date}"`
  where `{date}` is `journal_row["timestamp"]` in Israel time
  (`ZoneInfo("Asia/Jerusalem")` per `main.py:10`). Run twice with `freeze_time`
  on either side of the 27/03/2026 DST clocks-forward boundary on a UTC
  timestamp in the day-cusp window — assert attributed date differs by one day.
  Relative phrasing `"פעם כתבת…"` BAN-listed.
- `TestCallbackFiredAuditRowWritten` — mock `audit_logger`, fire once, assert
  exactly one `log_action(ACTION_CALLBACK_FIRED, ...)` call; payload contains
  all 8 keys from `MARK_RESEARCH_RULINGS.md:49-52` (`anchor_rejection_id`,
  `anchor_ts`, `anchor_reason_text`, `surface_id`, `current_setup_bucket`,
  `similarity_score`, `current_heat_window`, `ts_fired`). Fire twice → call
  count == 2 (dedup at surface-cooldown, not at audit).
- `TestCallbackSpecialCharsRoundTrip` — re-read the audit row's
  `anchor_reason_text`; assert equals original journal bytes (catches
  paraphrase-by-JSON-serialisation on `‏` and emoji).

Plumbing exists: `audit_logger.py:28-62` `ACTION_*` constants pattern;
`ACTION_CALLBACK_FIRED` slots there.

## §X5 Silence-As-Beat — pinning tests required

**File:** `tests/test_engagement_silence_as_beat.py` (new).

- `TestMissedDayNoCheckinFired` — `last_founder_interaction_ts = now-49h`; call
  every C1/C2/C4/C5 push through `should_suppress_for_silence_or_2r_or_settle()`.
  String-search BAN-list: `"שמתי לב"`, `"אתה בסדר"`, `"לא פתחת"`, `"לא דיברנו"`
  — none in any output. Welcome-back string MUST carry `"נכון ל-"` (Q1 binding,
  `MARK_RESEARCH_RULINGS.md:36-39`).
- `TestMinus2RNoCallbackFired` — fixture: today's realized `R = -2.1`. Callback
  matcher returns `None`. C2-S1 sizing nudge suppressed. C5-S1 Monday anchor
  carve-out (E4 §6, `UX_SYNTHESIS.md:232-233`) pinned separately.
- `TestSettleSuppression` — monkeypatch `get_risk_settle_info`
  (`adaptive_risk_engine.py:87`) → `{"hours_remaining": 5}`. All PUSH surfaces
  suppressed; PULL surface (C4-S3 settle pull) still emits — pin the
  push-vs-pull distinction.
- `TestHelperReturnsTrueExactlyWhenAnyConditionFires` — table-driven 8-row test
  on the helper itself; catches AND-vs-OR defects.

## §X6 Process-Mirror — pinning tests required

**File:** `tests/test_engagement_process_mirror.py` (new).

- `TestNoMarketCommentaryAsLeadLine` — first non-empty line MUST contain a
  Tier-1 token (one of `"אצלך"`, `"שלך"`, `"היומן"`, `"הגייט"`, `"הסטאפ"`,
  `"לפני {n} ימים"`). Back-translation rule (`UX_SYNTHESIS.md:275-276`) made
  executable.
- `TestNoPeerComparisonStrings` — BAN-list across every surface:
  `"traders like you"`, `"average trader"`, `"השוואה"`, `"כמו טריידרים"`,
  `"המשתמש הממוצע"`, `"השוק עלה"`, `"השוק ירד"`, `"the market is telling"`.
- `TestNoYfinanceImportInEngagementModules` — AST scan on `engagement/`
  modules; assert no `import yfinance` / no `from yfinance`. Pattern model:
  `test_meeting_ux_wave2.py:259-262`.
- `TestNoPeerStatsFieldsConsumed` — AST scan: no references to `peer_*`,
  `cohort_*`, `community_*` field names.

## C1 — Callback engine concrete test cases

**File:** `tests/test_engagement_callback_engine.py` (sibling of §X4 honesty).

- **Positive match:** seed anchor day -65 `{symbol:MRVL, bucket:VCP_MANUAL,
  heat_window:S9+M21+, reason:"מדגם קטן מדי"}`; current setup identical → matcher
  returns the row.
- **Negative — different symbol:** current `symbol:NVDA` → `None`.
- **Negative — different regime:** same symbol, `heat_window:S9-M21-` → `None`.
- **Day-60 cooldown boundary:** anchor at day -30 → `None`; re-seed at day -60
  → fires. Boundary: day -59 `None`, day -60 fires (gate ≥60,
  `UX_SYNTHESIS.md:59`). Freeze_time on both ends.
- **Fortnight re-fire cooldown:** after first fire, advance 13d → `None`; +1d
  → fires (`UX_SYNTHESIS.md:71`).
- Verbatim integrity + single audit row: cross-link §X4 tests (do not
  duplicate).

## C4 — Gate Receipt count + $ saved concrete test cases

**File:** `tests/test_engagement_gate_receipts.py` (new).

- **Count = clamped-AND-would-have-been-raise only:** `rec_log` with 3 rows
  `allow_raise=False AND direction=raise_intent`; 1 row `allow_raise=False AND
  direction=hold` (natural hold); 1 row `gate_result=None`. Assert
  `count_clamps_saved(90d) == 3`. Natural-hold MUST NOT inflate
  (`MARK_RESEARCH_RULINGS.md:101`).
- **Anti-double-count:** same `recommendation_id` twice (initial + re-eval).
  Assert count == 1 (dedup key = recommendation_id).
- **Symmetric framing:** 7 clamps + counterfactual showing 1 would-have-been
  +1.5R if allowed → output contains saved-count AND "refused once incorrectly"
  token; net < 0 → sign-flip prefix `"אומדן: היה עדיף שלא"`. Pin Phase-1
  count-only AND Phase-2 with §X1 `"אומדן"`.
- **`gate_result` field presence (static):** assert `_log_recommendation`
  (`adaptive_risk_engine.py:849-874`) writes a `gate_result` key — CLOSURE-FIX
  per `MARK_RESEARCH_RULINGS.md:103-105`, prerequisite to C4-S1.

## C5 — Monday R-dist concrete test cases

**File:** `tests/test_engagement_monday_anchor.py` (new).

- **Week-bucket Sunday-vs-Monday:** campaign closes 2026-05-17 22:55 IL (Sun);
  render Monday `freeze_time("2026-05-18 13:08 IL")`. Counted in week N. Reuse
  the same Israel calendar helper as `analytics_engine.py:372-376` — do NOT
  invent local datetime arithmetic.
- **DST boundary:** campaign close 2026-10-30 23:30 (one minute before fall-
  back). Stays in week N, not N+1.
- **D10 SKIP-AND-NULL propagation (Q3):** 3 campaigns with regime, 1 with
  `regime=None`. Breakdown does NOT crash, NULL row surfaces as
  `"regime-unclassified"` — not silently dropped, not imputed
  (`MARK_RESEARCH_RULINGS.md:58-71`).
- **4-template rotation:** 4 consecutive Mondays, identical fixture → leading
  dimension covers ≥3 of {mean, σ, tail, hit-rate} (`UX_SYNTHESIS.md:247-248`).
- **Specificity gate (Phase-3, scoped now):** generator returning generic
  `"שבוע טוב!"` → mute (no emission); returning a number-or-named-pattern →
  emit.

## C2 — Sizing pattern (voice change) concrete test cases

**File:** extend `tests/test_risk_monitor.py` or new
`tests/test_engagement_sizing_voice.py`.

- **Dedup-key semantic byte-identity (Mark binding,
  `MARK_RESEARCH_RULINGS.md:143-144`):** snapshot `build_position_alert_key`
  output for 4 representative inputs against literal expected strings in the
  test source. **DO NOT** use `git diff` (Sprint-25 vacuity).
- **Voice-change-only numbers preserved:** fire `_sizing_leak_alert` with the
  existing test fixture; assert `"0.41"` ratio + all 3 numeric values appear;
  NEW voice tokens present (`"או אל תיכנס"`, `"היית ב-"`); OLD push-up tokens
  absent (BAN-list: `"תגדיל"`, `"הגדל סייז"`).
- **Module-imports unchanged:** AST diff `_sizing_leak_alert`'s module before/
  after — no new yfinance, no new peer-comparison.

## Coverage target for engagement phase

Current: 2587 tests / 73.20% / gate 67% (`TESTING_GUIDELINES.md:64-73`).
Engagement adds ~6 modules (Callback engine, similarity matcher, silence guard,
gate-receipt aggregator, Monday anchor formatter, sizing-voice formatter).
**Recommended: 70% project, 80% per new engagement module** (file-scoped
`--cov-fail-under` thresholds). Rationale: pure text rendering + audit
side-effects, 100%-coverable on hermetic fixtures. Phase-1 pin budget
(rough): C5-S1 ~6, C4-S1 ~5, C2-S1 ~4, C1-S1 ~5, §X4 ~4, §X5 ~4, §X6 ~4 →
**~32 new tests** concurrent with Phase-1 code → suite ≈ 2619.

## Byte-lock scrutiny

Sprint-25 lesson (`MEETING_UX_TESTING_FINDINGS.md:86-91`): `git diff -- <file>`
on a clean CI checkout returns empty — the assertion is vacuous either way.
Three new byte-lock candidates in the engagement phase:

1. **C2 "dedup-key byte-identical"** (`MARK_RESEARCH_RULINGS.md:143-144`).
   WRONG: `subprocess.run(["git", "diff", "--", "risk_monitor.py"])`. RIGHT:
   `assert build_position_alert_key("MRVL","VCP","C-123") == "MRVL|VCP|C-123"`
   — literal expected value frozen in the test source.
2. **§X4 verbatim quote.** Correctly framed already (`out_bytes == journal_row[
   "reason"].encode()`) — literal-bytes compare, not VCS diff. No change.
3. **C5-S1 4-template rotation strings.** Pin templates via literal-string
   assertion in test source; do NOT `open(__file__)` on the module (Sprint-25
   P0-2 anti-pattern).

## Sign-off

Engagement phase is testable; §X4/§X5/§X6 pinning files MUST land in the same
PR (or before) the C1-C5 code, per Mark's binding at
`MARK_RESEARCH_RULINGS.md:253-254`. Coverage ratchet to 70% project + 80% per
new engagement module. Sprint-25 byte-lock-vacuous defect class is prevented
preventively by literal-bytes / literal-strings comparisons (never VCS diff).

**Top-3 testing gaps if any concept ships without coverage:** (1) Callback
paraphrase-creep on RTL/emoji/Markdown round-trip — §X4 missing makes the
mirror function silently broken; (2) Silence-as-beat helper drift into passive-
aggressive "we noticed" wording — §X5 missing means engagement-mining ships
undetected; (3) C2 dedup-key regression from a voice-only refactor accidentally
re-keying the campaign cooldown — Mark's binding fails without the semantic
byte-identity snapshot.

— TESTING discipline, engagement-phase feasibility, Wave-4, 21/05/2026.
Read-only. Binds Phase-1 via §X4/§X5/§X6 pinning prerequisite.
