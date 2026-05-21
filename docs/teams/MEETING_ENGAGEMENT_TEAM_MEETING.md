# MEETING_ENGAGEMENT_TEAM_MEETING — Engagement Phase Team Meeting

> Parent consolidator artifact. 21/05/2026.
> Inputs: 13 wave-1..wave-4 docs in `docs/teams/MEETING_ENGAGEMENT_*`.
> Branch: `claude/review-system-audit-FBZ2h`, HEAD at consolidation: `83bd83d`.
> Suite at consolidation: 2586 passed · 1 skipped · 0 failed · coverage 73.20% (gate 67%).
> No code changes during this review (DOC-ONLY by construction).

## The frame

Founder brief (21/05/2026): make Sentinel's market-open + close messages **אישי, בעל משמעות, שייתן את האקסטרה — לצאת מהקופסה, המשתמש פשוט חייב**. UX team in focus, external team brainstorms, Mark + Research approve, other disciplines rotate.

**5 waves executed:**

| Wave | Discipline(s) | Output | Status |
|---|---|---|---|
| 1 | E1 Behavioral · E2 Psychology · E3 Hebrew Copy · E4 Narrative · Research | 5 docs (raw ideation + data-asset inventory) | ✅ |
| 2 | UX-Lead | 5 cohesive concepts with headline pick | ✅ |
| 3 | Mark + Research (joint) | Rulings per concept + 3 new §X clauses + Q1/Q2/Q3 binding answers | ✅ |
| 4 | ARCH · DATA · ENGINE · OPS · SECURITY · TESTING | 6 feasibility docs | ✅ |
| 5 | Parent (this doc) | Consolidation + tiered menu + founder decision | ← here |

## Headline (the convergence)

**Sentinel doesn't need new information. It needs to start showing the founder things only Sentinel knows about HIM, at the moment of consequence, in a Hebrew voice no other tool could write about anyone else.**

The diagnosis from E3 is the sharpest: ה-bot לא **"מבלבל וארוך"** — הוא **"זר"**. ה-fix אינו הודעות קצרות יותר; הוא הודעות שמוכיחות שה-bot צופה בו ספציפית. המילה הקסם: **`אצלך`**.

The 4 external personas + Research converged independently on the same six rules:

1. **Self-data only** — no market hype, no peer comparisons (E1, E2, Research wedge, §X6).
2. **Process mirror, not market commentary** (E2 headline, E4 הדפוס character).
3. **The Callback** — system quotes founder's own past words back at the decision moment (E4 payoff, E2 S4, E3 #3).
4. **The `אצלך` Hebrew register** (E3 headline).
5. **Silence as a beat** — missed-day welcome without guilt, -2R day without coaching (E4, §X5).
6. **Variable reward from the founder's own archive** (E1 headline).

Mark's posture (Wave 3): *"The engagement phase is the first Sentinel surface that isn't math/risk correction — it's a behavioural mirror, which makes existing §3-class honesty rules MORE load-bearing, not less. A mirror that paraphrases the founder, smooths a cached number, or one-sidedly celebrates a clamp is fallback-as-truth in engagement-clothes."*

## The 4 approved concepts (ranked)

| # | Concept | Anchor | Ruling | First-fire | MUST-have |
|---|---|---|---|---|---|
| C1 | **הספר מדבר חזרה** *(Sefer Speaks Back)* | הספר (Chronicler) | APPROVE_WITH_CONDITIONS | Phase-1 backfill, **The Callback at day ~60** | 10/10 |
| C4 | **קבלות מהמנטור** | המנטור | APPROVE_WITH_CONDITIONS | Phase-1 count-only | 9/10 |
| C5 | **השוק הוא מזג אוויר** (S1+S3) | השוק | APPROVE_WITH_CONDITIONS | Monday 16:00 IL | 8/10 |
| C2 | **הדפוס מדבר** (S1 only Phase-1) | הדפוס | APPROVE_WITH_CONDITIONS | Pre-open MRVL-class sizing nudge | 9/10 |
| C3 | השעה הטובה | (deferred) | DEFER (D2 gated) | — | — |

**Headline concept — C1 הספר מדבר חזרה.** Every silent rejection (incl. the literal `"ללא הסבר"` × 2 at 14:22 19/05 that triggered this meeting) becomes raw material for the Callback. Phase-1 builds the corpus; the Callback fires when it earns itself (day ~60+). This is the only concept whose payoff IS the engagement diagnosis it was designed to solve.

Sample C1 surfaces (E3 voice register):

- **Backfill** (14d after null-reason): `‏לפני 14 יום דחית העלאה ל-0.85% עם "ללא הסבר". מאז: שני ירוקים, אחד אדום. השאלה לא אם צדקת — אם תזכור למה. [הוסף סיבה במשפט אחד] [דלג — זה היה אינטואיציה]`
- **The Callback** (day ~60+): `‏לפני 47 יום כתבת: "מדגם קטן מדי בסביבת chop". הסטאפ עכשיו דומה — heat S9 ‎+18, M21 ‎+12. אותו פער. לא המלצה. הספר רק זוכר במקומך.`
- **EOD process-positive on losing day**: `‏סגירה: ‎-0.7R. הספר רושם: לא חרגת מסיכון, לא נכנסת ב-20:40, סגרת בתזה. תהליך נקי. P&L לא תמיד שווה לציון.`

## 3 binding §X clauses (Mark, codified Wave 3)

| § | Clause | Failure mode prevented |
|---|---|---|
| **§X4** | **Callback Honesty** — verbatim quote (char-for-char, no normalization) + date-attributed inline ("מתוך היומן שלך מ-{date}") + `ACTION_CALLBACK_FIRED` audit row | Paraphrase-creep — destroys the mirror function |
| **§X5** | **Silence-As-Beat** — absence IS the surface during missed-day / -2R / settle-period; "we noticed you've been quiet" passive-aggressive messages **BANNED** | Engagement-mining via silence-commentary |
| **§X6** | **Process-Mirror** — every engagement surface uses ONLY self-data; market commentary as primary content / peer comparison **BANNED** | Drift into market-narration; §3 fallback-as-truth in engagement clothes |

Plus: **§X1 EXTENSION** — welcome-back inherits source-disclosure for cached-data numbers (Q1 ratified). **`ACTION_CALLBACK_FIRED` audit shape** ratified (Q2). **D10 SKIP-AND-NULL** for regime-at-close low-confidence (Q3, founder-gated).

## Phase-1 mandatory build order (Mark + Research consensus)

1. **U1 closure** — route `risk_monitor` adaptive alert through `fmt_adaptive_risk_block` (yesterday's UX-U4 P1 hanging closure; prereq for C2/C3).
2. **U4 closure** — `ACTION_RISK_REJECT` constant + surfacing in `telegram_audit_review.py:41-46`. **Non-negotiable before C1.** (Partially closed by yesterday's B3 commit `d16a70b`; needs full audit-review surface.)
3. **`gate_result` field on `_log_recommendation`** (`adaptive_risk_engine.py:849-874`) — closes T1.3 logging gap; one key on the entry dict, backwards-compat automatic. CLOSURE-FIX class.
4. **`ACTION_CALLBACK_FIRED` constant + payload** (Q2). Tier-A.
5. **`should_suppress_for_silence_or_2r_or_settle()` helper** in new leaf module `engagement_suppression.py` (§X5). Importable from `risk_monitor` + `report_scheduler`.
6. **§X4 + §X5 + §X6 pinning tests** (TESTING binding: must land in same PR as concept code, not after).
7. **C5-S1** Monday R-distribution — no new derivation.
8. **C2-S1** voice change — Tier-A; dedup key byte-identical (Mark binding).
9. **C4-S1** count-only — depends on (3).
10. **C1-S1** backfill prompt — depends on (2).

Steps 1+2+3 are prerequisites; 4+5+6 infrastructure; 7-10 shipped surfaces. **The Callback itself (C1-S2) is Phase-3 day-~60**, gated on backfill producing ≥1 typed-reason row in matching bucket.

## Risk map across 6 disciplines (Wave 4)

| Discipline | Headline | Top risk |
|---|---|---|
| ARCH | GO_WITH_CONDITIONS | SST regression on `risk_journal.json` — re-opens "5 ad-hoc reads" pattern B1 just closed (needs `risk_journal_repository` helper Phase-1.5) |
| DATA | GREEN | `compute_market_regime` (engine_core.py:570-612) has NO `confidence` field — prerequisite for D10 |
| ENGINE | 4/5 on existing math; one new function | C1 matcher must filter ALGO-driven journal entries (else §X6 violation in numeric clothes) |
| OPS | APPROVE_WITH_CONDITIONS | F2 reconnect-storm amplification — every new emitter = new heartbeat-stall site (`main.py:32` `LOOP_INTERVAL_SEC=900` vs compose `stale=1980s`) |
| SECURITY | APPROVE_WITH_CONDITIONS | **S-ENGAGE-1 Markdown injection** on journal-text render (`telegram_bot.py:302`) — must-fix before C1; the Callback intensifies an existing defect |
| TESTING | testable on existing fixtures | §X4/§X5/§X6 pinning tests must land **before** any C1-C5 code merges; ratchet to 70% project / 80% per new module |

**Cross-cut convergences across all 6 disciplines:**

- ARCH+DATA: T1.3 gate-logging gap is the same trivial-but-real fix (one key on `_log_recommendation`).
- ENGINE+SECURITY: the §X4 verbatim requirement is data-safe today (UTF-8 round-trip clean) **but** rendering-safe is NOT (Markdown injection at the Telegram boundary).
- OPS+ENGINE: MRVL-class `missing_data` events propagate into engagement surfaces as silent gaps — both flag the same `engine_core.py:88` bare-except as load-bearing.
- ARCH+OPS: C1 companion **must** be hosted inside the existing `risk_monitor.py` 300s loop (do NOT introduce a new compose service — red line per CLAUDE.md).
- TESTING+SECURITY: regression test for "Callback fires but send fails" is needed at both layers.

## Tiered menu — A/B/C

### Tier-A — Prerequisites only (build floor, ~1 sprint)
- **A1** U1 — route `risk_monitor` alert through `fmt_adaptive_risk_block` (`risk_monitor.py:1242,1270-1305`)
- **A2** U4 — `ACTION_RISK_REJECT` constant + surfacing in `telegram_audit_review.py:41-46`
- **A3** `gate_result` field on `_log_recommendation`
- **A4** `ACTION_CALLBACK_FIRED` + `ACTION_RISK_REJECT` audit constants
- **A5** `engagement_suppression.py` leaf module (§X5 primitive)
- **A6** S-ENGAGE-1 — `_render_journal_text` Markdown-escape helper
- **A7** §X4 + §X5 + §X6 pinning tests
- **A8** `compute_market_regime` adds float `confidence` field (additive, no migration)

### Tier-B — Headline concepts (Phase-1 surfaces, ~2 sprints after A)
- **B1** C5-S1 Monday R-distribution opener (Mon 16:00 IL)
- **B2** C2-S1 voice-change refactor of `_sizing_leak_alert` (dedup key byte-identical)
- **B3** C4-S1 Gate Receipt count-only (depends on A3)
- **B4** C1-S1 backfill prompt + write-back (depends on A2)
- **B5** EOD process-verdict on non-2R days (C1-S4)

### Tier-C — Earned moments (Phase-2/3, weeks to months)
- **C1** The Callback (C1-S2) — day ~60 first-fire, gated on backfill corpus
- **C2** C5-S3 Friday signature line (specificity-gated; mute-on-failure)
- **C3** C2-S2 Friday disposition mirror (≥3-week persistence)
- **C4** C4-S2 dollar-value-saved (Phase-2, D11 with §X4 audit)
- **C5** D10 regime-at-close storage (founder-gated; Q3 SKIP-AND-NULL)
- **C6** `risk_journal_repository` helper (ARCH F1 Phase-1.5)

### Tier-OUT — Deferred (NOT built, founder-flagged)
- **C3 השעה הטובה** — DEFER until D2 intraday-timestamp verified ≥90% on post-deploy BUYs.
- **C5-S2** mid-week intraday regime check — DEFER until D10 schema decision.

## Parent recommendation

**Recommended scope: `A + B1 + B2 + B3 + B4`.**

Reasoning:
- **A in full** is the build floor — without it, the concepts ship into known defects (S-ENGAGE-1 Markdown injection, T1.3 gate-log gap, §X5 helper missing, §X4 verbatim untested). All 6 disciplines agreed: A must precede any B.
- **B1+B2+B3+B4** is the minimum viable shape of the headline. B1 (Monday R-dist) is the lowest-build highest-leverage opener — no new derivation. B2 (sizing voice) is voice-only on existing path (Tier-A polish vocabulary). B3 (Gate Receipt) and B4 (backfill) build the corpus for the day-60 Callback — without them, C1-S2 (the day-60 magic moment) never earns itself.
- **B5 (EOD verdict)** is bundled with B4 — they share the journal-write path. Recommend bundling.
- **All of Tier-C is deferred** to a future founder-confirmed scoped phase per Sprint-25 C2 precedent. The Callback (C1) is the long-arc payoff — it earns itself only after Tier-A+B has run for ~60 days. Building it before the corpus exists is a fallback-as-truth disguise.

**Out of scope for any founder choice:** C3 (השעה הטובה) — DEFER stands until D2 timestamp verification.

**Suite + coverage targets for the engagement phase (TESTING binding):**
- Project coverage gate ratchets from 67% → 70%.
- Each new engagement module (`engagement_suppression.py`, `callback_engine.py` in Tier-C, etc.) targets ≥80% line coverage.
- §X4/§X5/§X6 pinning tests are **landing-blockers**, not "if time permits".

## Founder decision (pending)

Reply with chosen scope:
- `A` — Prerequisites floor only (~1 sprint; nothing visible to the founder yet, but the build is honest)
- `A+B1` — Floor + Monday R-distribution opener (lowest-leverage shipping unit)
- **`A+B1+B2+B3+B4` — recommended set** (headline shape; corpus accumulates toward day-60 Callback)
- `A+B+C` — full menu (each Tier-C item gets per-item confirm with byte-locks)
- Custom — name the items

## Sign-off

— **E1 Behavioral** (06f5e6d), **E2 Psychology** (b4d0f15), **E3 Hebrew Copy** (a714bfc / E3 register is binding voice across all surfaces), **E4 Narrative** (54adb6a / 5 characters + 5 daily beats + missed-day + -2R rules), **Research** (6b09dd7 / 15 Tier-1 assets), **UX-Lead** (07ddef9 / 5 concepts headed by C1), **Mark + Research joint rulings** (3630211 / 4 APPROVE + 1 DEFER + §X4/§X5/§X6 + 3 Q-answers), **ARCH** (79de0d0 / GO_WITH_CONDITIONS, 2 new modules), **DATA** (83bd83d / GREEN, 2 trivial fixes), **ENGINE** (47a9747 / 4/5 on existing math), **OPS** (47a9747 / coordinated full-stack deploy required), **SECURITY** (55a0bc0 / APPROVE_WITH_CONDITIONS, must-fix S-ENGAGE-1), **TESTING** (47a9747 / testable; ratchet to 70%/80%).

All 6 disciplines + Mark + Research + UX-Lead + 4 externals **APPROVE the engagement phase as scoped above**. Follow-up work is founder choice per the tiered menu. **No item in this consolidation touches the CLAUDE.md red lines.** The 3 new §X clauses are codified in `docs/teams/MARK_MEETING_UX_RULINGS.md` (extension PR forthcoming when Tier-A code lands).

— Parent (consolidator), 2026-05-21. Branch HEAD at consolidation: `83bd83d`.
