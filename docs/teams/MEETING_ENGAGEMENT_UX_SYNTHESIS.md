# MEETING_ENGAGEMENT_UX_SYNTHESIS — UX Lead Synthesis (Engagement Phase)

> UX-TEAM-LEAD artifact. 21/05/2026. Read-only.
> Inputs: E1 Behavioral, E2 Psychology, E3 Hebrew Copy, E4 Narrative, RESEARCH inventory.
> Constraints: CLAUDE.md, `MARK_MEETING_UX_RULINGS §X1/§X2/§X3`,
> `MEETING_UX_TELEGRAM_FINDINGS U1/U2/U4` (open coverage gaps that gate this work).

## The frame

Five inputs converge on one rule: **Sentinel earns the right to speak by showing the
founder something only Sentinel knows about HIM, at the moment of consequence, in a
Hebrew voice no other tool could write about anyone else.** Each concept below is a
SURFACE SYSTEM — not a single message — sharing an E4 character, a T1 data spine, an
E1 mechanic, an E2 mirror posture, and an E3 register.

## Headline concept (ship-first)

### **C1 — הספר מדבר חזרה** *(Sefer Speaks Back)*

**Pitch.** Every silent rejection the founder ever made (the literal friction that
triggered this engagement — `"ללא הסבר"` × 2 at 14:22 on 19/05) becomes raw material
for the system's eventual *Callback*: ~60 days in, when a near-identical setup
recurs, Sentinel quotes the founder's own past words back to him *before* he acts.
The only concept whose payoff IS the engagement diagnosis.

---

## C1 — הספר מדבר חזרה (HEADLINE — full spec)

1. **E4 anchor:** **הספר** (The Chronicler). הספר ≠ המנטור. The Chronicler does not
   advise, it *quotes*. Separation is what makes The Callback feel earned, not smug.
2. **T1 data:** T1.1 risk-journal (incl. 19/05 null-reason rows), T1.2 adherence
   (30d trend, emoji-strip `:919-927`), T1.4 per-bucket WR (similarity match), T1.5
   heat snapshot (similarity axis).
3. **E1 mechanics:** **E1-#9 Rejected-Raise Echo** (Cialdini cognitive consistency —
   past self speaks to present self) + **E1-#10 EOD Verdict** (process-grading,
   decoupled from P&L) as the daily drip growing the corpus. Hooked-loop: variable
   reward (which rejection surfaces is unpredictable) + investment (each typed
   reason sharpens the next Callback).
4. **E2 posture:** **S4 (Rejection Journal)** + **S10 (Reason-Free Counter)**.
   Annie Duke: decision quality ≠ outcome quality. Callback reports prior reasoning
   *with* realized outcome, never one as a verdict on the other.
5. **Hebrew samples (4 surfaces, RTL).**

   *S1 — Backfill prompt, 14d after null-reason rejection (E3-#3 wry-direct):*
   `‏לפני 14 יום דחית העלאה ל-0.85% עם "ללא הסבר". מאז: שני ירוקים, אחד אדום. השאלה לא אם צדקת — אם תזכור למה. [הוסף סיבה במשפט אחד] [דלג — זה היה אינטואיציה]`

   *S2 — The Callback (E4 Payoff A), ~60d in, on setup-similarity match:*
   `‏לפני 47 יום כתבת: "מדגם קטן מדי בסביבת chop". הסטאפ עכשיו דומה — heat S9 ‎+18, M21 ‎+12. אותו פער. לא המלצה. הספר רק זוכר במקומך.`

   *S3 — Friday null-reason counter (E2-S10 + E3 dry), only if count ≥3:*
   `‏השבוע: 4 החלטות בלי נימוק רשום. לפעמים אינטואיציה היא הנימוק. אם תכתוב מילה אחת ליד הבאה, הספר ילמד מהר יותר.`

   *S4 — EOD process-positive on a losing day (E1-#10, E3 wry-protective):*
   `‏סגירה: ‎-0.7R. הספר רושם: לא חרגת מסיכון, לא נכנסת ב-20:40, סגרת בתזה. תהליך נקי. P&L לא תמיד שווה לציון. [מסכים] [לא מסכים — סיבה?]`

6. **Fires.** Backfill: 14d after null-reason; max 1/week; suppressed if silent ≥48h
   (E4 missed-day). Callback: ≥60 trading days elapsed AND setup-bucket × heat-window
   match AND anchor has typed reason (no Callback on null-reason rows — Callback
   honors the backfill loop). Friday counter: Fri 22:30 IL, only if
   `null_reason_count_7d ≥ 3`. EOD verdict: every close EXCEPT -2R days (E4 §6).
7. **DOESN'T say.** No right/wrong verdict on past rejection (E2-S4). No "you would
   be up X" counterfactual (CLAUDE.md). No celebration on losing-day green-process
   (E4 anti). No directive ("רשום סיבה!"). Never Callback during a -2R drawdown beat.
8. **Earned moment.** S2 (Callback) is the long-arc payoff. **First-fire ETA: day
   ~60**, gated on backfill producing ≥1 typed-reason row in matching bucket.
   Phase-1 ships collection; Callback fires when it earns itself.
9. **MUST-have: 10/10.** Day-60 first-fire passes the *"איך לא השתמשתי בזה עד היום"*
   test — engagement was triggered by silent rejection; this surface metabolizes it.
10. **Risk.** *R1:* Callback feels stalker-ish if over-quoted. Detect: tap-through
    < 30% by day-90. Bound: max 1 Callback/fortnight/reason-bucket. *R2:* Backfill
    feels like nagging. Bound: 4 quick-pick chips + free text (U3 precedent).
    *R3:* **U4** (audit surface silent on rejections) makes Chronicler invisible on
    `🧾 הפעולות שלי`. **Land U4 BEFORE C1 Phase-1 — non-negotiable.**

**Phase-1 MVP (week 1).** S1 + U4 closure only. Backfill cron in `risk_monitor`-
companion (NOT inside the 300s loop); writes typed reason back to `risk_journal.json`;
appends new `ACTION_REASON_BACKFILL` audit row. Emotional shape proven: founder taps
backfill → types reason → sees it on `🧾 הפעולות שלי` next morning. S2/S3/S4 are Ph2/3.

---

## C2 — הדפוס מדבר *(The Pattern Has a Voice)*

1. **E4:** **הדפוס** (Internal Flaw). Named explicitly. Founder ≠ הדפוס; הדפוס is
   what he is working on.
2. **T1:** T1.7 (sizing accuracy — MRVL 0.41x), T1.6 (R-dist incl. winner-hold), T1.4
   (per-bucket WR), T1.15 (mgmt-mode). *T3:* D9 (disposition, M) gates the
   cut-winners surface; D5 (conviction-text, S) gates the under-sizing one.
3. **E1:** **#5 Bucket Mirror** (Bandura self-efficacy) + **#8 Hold-Or-Cut Dialectic**
   (pre-commitment, System-2 articulation per open position).
4. **E2:** **S2 Sizing Drift** + **S3 Disposition Signature**. Tharp's position-
   sizing-as-confession. Never push toward more size.
5. **Hebrew (3 surfaces, E3 coach-direct).**

   *S1 — Pre-open sizing nudge (E3-#3 verbatim):*
   `‏MRVL חוזר ל-watchlist. ב-9 הכניסות האחרונות עליו היית ב-0.41x מהיעד. אם תיכנס היום — תכניס את הסייז שאתה באמת מאמין בו, או אל תיכנס.`

   *S2 — Friday disposition mirror (E3-#6, ≥3-week persistence + n_winners ≥4):*
   `‏סיכום שבוע — תבנית שזיהיתי: החזקה ממוצעת במנצחות 42 דק׳. ההיסטורי שלך 78 דק׳. מוקדם מדי. הדפוס מדבר. [היה לי טריגר ספציפי] [תזכיר בעוד שבוע]`

   *S3 — Thesis-of-the-day (E1-#8, /portfolio open, ≥2 positions):*
   `‏3 פוזיציות פתוחות. ב-MSFT שינית עמדה ב-19/05 (cut→hold). שורה אחת — מה התזה שלך עליה היום? [___] [דלג]`

6. **Fires.** S1: 16:08 IL pre-open, watchlist sizing <0.7x over ≥5 trades, 7d
   per-symbol cooldown, symbol queried in last 24h (E3-#3 guard). S2: Fri 23:00, +
   max once/4w. S3: in-app /portfolio; free-text only; saved to lightweight
   `position_theses.json`.
7. **DOESN'T say.** No "תגדיל פוזיציה" (E2-S2). No "תן לרווחים לרוץ" (E2-S3). No
   "כל הכבוד!" on high-sizing weeks (E3 anti-list). Never name הדפוס on -2R day (E4).
8. **Earned moment.** First-fire **day ~30**. Screenshot moment is S1's
   *"או אל תיכנס"* (E3 forwarding-bait). Cross-Callback day-90: *"לפני 6 שבועות
   חתכת ב-MRVL ב-42 דק׳. הספר רושם: 'יצאתי כי פחדתי לאבד'."* — C2 × C1.
9. **MUST-have: 9/10.** E2 ranked S2 as the most screenshot-likely surface;
   −1 for D9 dependency on Friday surface.
10. **Risk.** *R1:* Misread as nag. Bound: weekly cap. *R2:* Pushes him to larger
    size on bad day. Bound: SUPPRESS S1 if `risk_settle_info` (T1.12) shows recent
    pct-change. *R3:* D9 partial-leg-R gap. Bound: `n_winners ≥ 4` AND
    `is_stat_countable()`; never DATA_INCOMPLETE.

**Phase-1 MVP.** S1 only. Existing `_sizing_leak_alert` (`risk_monitor.py:497-540,
1168-1174`) already fires one-time per campaign — Phase-1 is voice change + the
conviction-history pull, not a new path. No D9 dependency for week-1.

---

## C3 — השעה הטובה *(The Ally — Best-Hour Mirror)*

1. **E4:** **השעה הטובה** (Ally) — also a constraint: trading outside Ally without
   reason is noted.
2. **T1:** T1.5 (heat-by-window), T1.6 (R-dist conditioned on hour), T1.4 (WR per
   hour). *T3 BLOCKER:* **D2** (best/worst-hour) — gates on intraday timestamp
   precision; one of Research's two bottleneck derivations.
3. **E1:** **#3 Sharp-Hour Whisper** (Fogg Prompt at peak Ability; habit-stack on
   existing strong moment). Variable reward: rotating question bank, never recs.
4. **E2:** **S1 Time-of-Day Mirror**. Variance always with mean. NEVER label hours
   ירוק/אדום (E2-S1 anti).
5. **Hebrew (2 surfaces, E3-#1/#2).**

   *S1 — Weak-hour pre-open (E3-#1, `open_winrate < baseline-5pp`):*
   `‏פתיחה בעוד 22 דק׳. NAV: $12,400 · חשיפה: 38%. שעה חלשה היסטורית אצלך — win-rate בפתיחה 31% מול 47% בשאר היום (n=42). אין חובה להיכנס.`

   *S2 — Sharp-hour whisper (E1-#3, top-tercile hour, max 1/day):*
   `‏17:42 · החלון שלך — היסטורית 56% ב-31 עסקאות בשעה הזו. לא תירוץ להגדיל סייז. תירוץ להישאר ערני. שאלה להיום: יש פוזיציה אחת שאתה דוחה מלגעת בה? למה?`

6. **Fires.** S1: 16:08 IL on weak-hour days; `n_open_trades ≥ 25` (E3-#1);
   suppressed entire week after -2R close (E4 §6). S2: 17:00-21:00 IL strong-hour,
   max 1/day; suppressed if silent ≥2d (E4 missed-day). Both SUPPRESSED if
   `risk_settle_info.hours_remaining > 0` (T1.12 wins — Mentor's silence).
7. **DOESN'T say.** No "אל תיכנס עכשיו" (E2-S1 directive ban). No "חכה ל-17:00
   ואז תרוויח" (inverse-FOMO ban). Never quote good-hour without variance.
8. **Earned moment.** S1 day-1; S2 day ~14 (after sample). Cross-Callback ~month-1:
   *"לפני 3 שבועות בשעה הזו דחית כניסה ל-NVDA ורשמת 'תזה לא ברורה'."* — C3 × C1.
9. **MUST-have: 8/10** (−1 for D2 blocker; 9 if D2 ships same sprint).
10. **Risk.** *R1:* Gamifies good hours → over-trade. Bound: variance-with-mean.
    *R2:* Noisy on small N. Bound: `n ≥ 25` per hour-bucket. *R3:* Collides with
    proactive risk_monitor alert (**U1 open**). Bound: route through
    `fmt_adaptive_risk_block`; Sharp-Hour cooldown key in `risk_monitor_state.json`.
    **Land U1 BEFORE C3 Phase-1.**

**Phase-1 MVP.** S1 only, contingent on D2 verification week-1. If hour data absent,
C3 slips to Phase-2.

---

## C4 — קבלות מהמנטור *(The Mentor's Receipts — Gate-Clamp Trust Arc)*

1. **E4:** **המנטור** (Yoda-not-Jarvis). Receipts itself: shows clamp's cost-saved
   AND, symmetrically, when the clamp left R on the table.
2. **T1:** T1.3 (4-gate history), T1.2 (adherence), T1.12 (48h settle silence).
   *T3:* D8 (time-since-clamp, S); **D11 (clamp $ saved, L)** counterfactual-heavy.
   *Research-flagged gap:* 4-gate veto not logged distinctly in `_log_recommendation`
   (`adaptive_risk_engine.py:849-874`) — B-tier logging change is prerequisite.
3. **E1:** **#2 Gate Receipts** (loss-aversion inversion — clamp as proof-of-value,
   not restriction) + **#7 Reconciliation Streak** (Clear habit-stack; mastery).
4. **E2:** **S6 Gate-Clamp Save** — Douglas: belief in the system. Honest balance:
   also show clamp-COST days. One-sided = fallback-as-truth.
5. **Hebrew (3 surfaces, E3-#4/#5/#8).**

   *S1 — Weekly clamp receipt (E3-#4 verbatim):*
   `‏90 הימים האחרונים: 3 פעמים הגדלה נחסמה. עלות משוערת שנחסכה: ~$420. אומדן, לא חישוב מדויק — ההפסד הוויפותטי מבוסס על R ממוצע לעסקה.`

   *S2 — Flat-day-gate-worked (E3-#8, realized R ∈ ±0.2R AND clamp ≥1):*
   `‏סגירה: ‎+0.1R, אבל לא זה הסיפור. היום הגייט חסם אותך פעם אחת — בלי זה, ההערכה: כ-‎-0.8R. יום שקט הוא לפעמים יום שעבד.`

   *S3 — 48h settle silence pull (E3-#5 clinical-honest):*
   `‏אתה ב-0.85% כבר 31 שעות. נשארו 17 לפני שהמערכת תציע שינוי. זה לא קיפאון. זו תקופת התבססות.`

6. **Fires.** S1: weekly, Mon pre-open OR Sun close; `clamp_count ≥ 3` (E3-#4);
   silent if zero clamps for 14d (E4). S2: EOD only on flat-with-clamp; max
   once/week per "saved" framing (E3-#8). S3: PULL-only on /portfolio during settle —
   never push.
7. **DOESN'T say.** No "תודה לגייט" anthropomorphism (E2-S6). No $ without
   "אומדן" (E3-#4 — §X1). NEVER cherry-pick — 90d window MUST surface clamp-cost
   days; sign-flip honestly if net negative.
8. **Earned moment.** S1 first-fire day ~30 (needs ≥3 clamps). Long-arc payoff:
   **monthly anniversary beat** (E4 Payoff B) — *"לפני 30 יום הגייט עצר עסקה שהיתה
   נסגרת ב-‎-1.4R לפי הסימולציה."* Once on the anniversary, never repeated.
9. **MUST-have: 10/10.** E1 explicit: *"directly answers 'why am I paying attention
   to this thing.'"*
10. **Risk.** *R1:* One-sided celebration → fallback-as-truth. Bound: symmetric;
    sign-flip when net < 0. *R2:* D11 modeling distorts. Bound: Phase-1 COUNT-only;
    Phase-2 adds $ with §X1 "אומדן". *R3:* **U1**. Bound: same as C3 R3.

**Phase-1 MVP.** S1 count-only (no $). Prerequisite: add `gate_result` field to
`_log_recommendation`. Fires Mon 16:08 IL; reads 90d rec-log; gated count ≥ 3.

---

## C5 — השוק הוא מזג אוויר *(The Market is Weather — Monday Anchor & Regime)*

1. **E4:** **השוק** (Tape). NOT a villain. Weather. Sentinel reports the forecast
   in terms of HIS performance in that weather, never the weather standalone.
2. **T1:** T1.6 (R-dist — Monday anchor), T1.5 (heat curve 90d), T1.4 (WR per
   regime). *T2:* market regime (JOIN axis only). *T3 BLOCKER:* **D10
   (regime-at-close snapshot)** — Research's highest-leverage Tier-3.
3. **E1:** **#6 Regime Memory** (Hooked search — analog unpredictable) + **#1 Edge
   Mirror** (self-as-variable-reward; S9 streaks).
4. **E2:** **S7 R-Distribution** as identity-defining weekly anchor + **S9
   Regime-Conditional WR** daily calibration. Variance always with means.
5. **Hebrew (3 surfaces, E3-#7/#10/#12).**

   *S1 — Monday R-distribution (E2-S7):*
   `‏שבוע 21/2026 — פתיחה. ההתפלגות שלך: ממוצע ‎+0.18R, σ=1.6R, hit-rate 47%, זנב ימני ‎+3.4R, שמאלי ‎-2.1R. אתה לא טריידר של hit-rate. אתה טריידר של זנב. שמור על הזנב.`

   *S2 — Regime-conditional pre-open (E3-#10, regime changed + conf ≥70%):*
   `‏הרג׳ים היום: chop-low-vol. ההיסטוריה שלך בו: 38% ב-23 עסקאות, ‎+0.04R בממוצע. לא אומר לך לא לסחור. אומר לך לדעת איפה אתה עומד.`

   *S3 — Friday week-close (E3-#12, signature-line specificity-gated):*
   `‏שבוע 21/2026 — סגירה. ‎+1.7R · win-rate 52% · sizing accuracy 0.68x. השורה שאני שומר לך לשבוע הבא: הגדלות שנחסמו חסכו לך יותר ממה שעסקאות חדשות הוסיפו. שבת שקטה.`

6. **Fires.** S1: Mon 16:08 — the only always-fires daily surface (E4 Monday
   exposition). S2: pre-open ONLY when regime changed + conf ≥70% (degrade to
   "משטר לא ברור" otherwise) + `regime_winrate < baseline-8pp` + `regime_n ≥ 20`
   (E3-#10). S3: Fri 23:00 ONLY; signature-line MUST contain number or named
   pattern (E3-#12 specificity — drop if generic).
7. **DOESN'T say.** No "השוק עלה ‎+1.2%" (E2 #1; E4 anti-personifying). No "שב
   בצד" (E2-S9). No "כוון להעלות hit-rate" (E2-S7 wrong KPI). No "שבוע מעולה!" —
   *"שבת שקטה"* is the ONLY allowed sign-off (E3 anti-list).
8. **Earned moment.** S1 first-fire day-1 (existing T1.6 — no new derivation). S2
   needs D10. S3 signature line is the Callback moment (E4 Payoff B) — first Friday
   a founder-specific specificity-passing line emits.
9. **MUST-have: 9/10** (S1+S3 are 10; S2 drops to 7 without D10).
10. **Risk.** *R1:* S3 degrades to generic ("שבוע טוב!") → mute. Bound: HARD
    specificity-gate — drop rather than emit. *R2:* Regime noisy. Bound: conf ≥70%
    AND `regime_n ≥ 20`; degrade gracefully. *R3:* Monday predictable → variable
    reward dies. Bound: rotate which dimension leads (mean/σ/tail/hit-rate) from a
    4-template pool.

**Phase-1 MVP.** S1 only. Existing T1.6; no new derivation. Becomes the permanent
Monday anchor.

---

## Cross-cuts

1. **Self-data only.** Every concept's spine is Tier-1. Market data (Tier-2) is JOIN
   axis only (C5 regime × bucket). C1/C2/C4 use zero Tier-2.
2. **The Callback is concept-crossing.** C1's הספר returns the words; C2/C3/C4/C5
   are the surfaces *where* the Callback fires (sizing-decision moment, sharp-hour
   echo, monthly clamp anniversary, Friday signature line). One Callback engine,
   driven by C1's collection loop.
3. **Silence-as-beat is system-wide.** E4 missed-day rule + -2R rule + T1.12 settle
   suppress every push surface across C1-C5. Mentor earns the right to speak by
   sometimes choosing not to.
4. **§X1 source-disclosure propagates.** Every estimated/cached/modeled number
   carries "אומדן"/"מבוסס על"/"הערכה" prefix. C4 S1 is the exemplar; all $ values
   inherit it.
5. **U1/U2/U4 are Phase-1 PREREQUISITES.** C1 needs U4 (audit visibility on
   rejections). C3+C4-S2 need U1 (route risk_monitor through
   `fmt_adaptive_risk_block`). C5-S2 brushes U2. These three open
   `MEETING_UX_TELEGRAM_FINDINGS` gaps must close before/with Phase-1 ships.
6. **No directive verbs.** Mirror-verb framing (*"רשמת"*/*"חתכת"*/*"דחית"*) +
   escape hatches (*"או אל תיכנס"*, *"דלג"*). Zero imperatives.
7. **The אצלך register is enforced.** Stat sentences MUST use *"אצלך"*/*"שלך"*. If
   a sentence survives back-translation into generic English, kill it (E3 sign-off).

## Phase plan (3-month)

**Phase 1 — this week (headline ship).**
- **C1 Ph1:** Backfill prompt (S1) + **U4 closure** (`ACTION_RISK_REJECT`).
- **C4 Ph1:** Weekly clamp count receipt (S1, count-only, no $). Prerequisite: add
  `gate_result` field to `_log_recommendation` (B-tier).
- **C5 Ph1:** Monday R-distribution anchor (S1).
- **C2 Ph1:** S1 (MRVL-style sizing nudge) via existing `_sizing_leak_alert`,
  voice-only change.
- **U1 fix (prerequisite):** route risk_monitor proactive alert through
  `fmt_adaptive_risk_block` — unblocks C3 + C4 S2.
- *Not yet:* The Callback (C1 S2), all other S2/S3/S4 surfaces.

**Phase 2 — this month.**
- C1 S3 (Friday null-reason counter) + S4 (EOD process verdict).
- C2 S2 (Friday disposition) — needs D9. C4 S2 (flat-gate-worked) + S3 (settle pull).
- C5 S2 (regime-cond pre-open) — needs D10.
- Tier-3 derivations: **D2** (hour), **D9** (disposition), **D10** (regime-at-close),
  **D11** (clamp $).

**Phase 3 — this quarter.**
- **C1 The Callback (S2)** earns first-fire (~day 60).
- C3 Ph1 (Sharp-Hour) contingent on D2 from Ph2.
- C5 S3 (Friday signature line) — pending generator QA.
- C4 monthly anniversary beat (E4 Payoff B) earns first-fire.
- E4 quarterly chronicle (Payoff C) — explicit founder consent required.

## Open questions for Mark + Research

1. **§X1 on E4 missed-day welcome-back.** When the founder returns after 2+ days,
   the welcome-back beat shows "current state, not last state". Does *current state*
   inherit §X1 source-disclosure if numbers were computed during his absence on
   cached data? Recommendation: yes, with inline "(נכון ל-{ts})". **Mark to rule.**
2. **The Callback audit rule.** When הספר quotes the founder back, is it
   `pre_db_realized_pnl_estimate`-class founder-asserted data (§X1 audit-log
   required) or journal text (no audit)? Recommendation: log
   `ACTION_CALLBACK_FIRED` with anchor-rejection-id + surface-id — chain auditable
   without modifying his typed text. **Mark to rule.**
3. **D10 regime-at-close write-discipline.** One row per campaign close. When
   `compute_market_regime` returns low-confidence at close, write with flag or skip
   with NULL? **Research to scope; founder-gated if behavior-bearing.**

*(Additional research deps: D2 IBKR-Flex intraday timestamps; D11 counterfactual
methodology; D9 partial-leg-R schema gap.)*

## Ranking — `(must_have × emotional_payoff) / (build_complexity × risk)`

| # | Concept | MUST | EmoPayoff | Build | Risk | Score | Phase-1? |
|---|---|---|---|---|---|---|---|
| 1 | **C1 הספר מדבר חזרה** | 10 | 10 | 4 | 2 | **12.5** | ✅ headline |
| 2 | C4 קבלות מהמנטור | 10 | 9 | 3 | 2 | 15.0 | ✅ |
| 3 | C5 השוק הוא מזג אוויר | 9 | 8 | 3 | 2 | 12.0 | ✅ S1 only |
| 4 | C2 הדפוס מדבר | 9 | 9 | 4 | 3 | 6.75 | ✅ S1 only |
| 5 | C3 השעה הטובה | 8 | 8 | 5 | 3 | 4.27 | ⛔ blocks on D2 |

> *Note:* C4 outscores C1 numerically (lower build), but **C1 is the headline**
> because it metabolizes the literal engagement diagnosis (silent rejection). Score
> is tiebreaker, not verdict. C4 *justifies* the engagement; C1 *resolves* it. Both
> ship Phase-1.

## Sign-off

Five concepts share one DNA: **Sentinel is a mirror, not a coach.** The Callback is
the long-arc reason all five exist; C1 builds the corpus; C2/C3/C4/C5 are the
surfaces at which the Callback fires. Phase-1 ships the spine (C1 collection + C4
receipts + C5 Monday + C2 sizing voice); the Callback itself fires when it earns
itself — first ETA day-60.

The rule on the wall (borrowing E3 + E4 sign-offs): **every Hebrew sentence in this
system should be one a friend could have written about him last night — and Sentinel
earns the right to speak by sometimes choosing not to.** If a surface fails either
test, kill it.

— UX TEAM LEAD, engagement-phase synthesis, 21/05/2026. Read-only.
