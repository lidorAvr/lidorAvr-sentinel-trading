# Marketing — Sprint 12, Week 2 Execution (Closed Beta — Ring-1 Sends)

> **Document type:** week-2 execution sheet (derived from `docs/teams/MARKETING_V1.md` §5 calendar, row **W2**)
> **Status:** active — Sprint 12, week 2 of the 6-week closed-beta plan
> **Owner:** Marketing Team
> **Branch:** `claude/review-system-audit-FBZ2h`
> **Continues from:** `docs/teams/MARKETING_SPRINT10_WEEK1.md` (W1 prep state — deltas only noted below)
> **Binding decisions:** DEC-20260515-001 (Minervini = acknowledgment only) · -002 (single `minervini_strict`) · -003 (Israel/Hebrew-only) · -004 (process/demo only, NO numbers) · -005 (closed free beta; testers get 1yr Pro) · -006/-007/-008 (process-hook features, Mark-ruled — see §3) · -009 (rate-limit unchanged)
> **Scope:** documentation only. No code, no Supabase, no git commit/push. Independent of Hyperscaler/UX/Backend execution — dependencies noted, not owned.
> **Working principle:** honesty over hype; no "AI"; no investment advice; no fabricated numbers (`AGENTS.md` / `CLAUDE.md`).

---

## 0. Continuity from Week 1 — what changed

W1 (prep) closed: positioning/disclaimer frozen, consent draft built (pending legal), invite + screening locked, Rings 1–3 candidate list screened and private, friction log open, W2 onboarding dependency pre-staged with Hyperscaler. **W2 is the first outbound week: Ring-1 invites are sent.** New since W1: four additional process-demo hooks shipped (Open Tasks was W1's hook; now also tap-only batch stop promotion, Minervini ratchet-up stop guard, RUNNER no-op suppression, and `🧾 הפעולות שלי` user audit-review). All are DEC-004-compliant (discipline/process, zero performance numbers) and Mark-ruled authoritative in `MARK_SPRINT11_RULINGS.md` (operationalizes DEC-20260515-006/-007/-008). They are folded into the §3 demo script as **1:1 recruiting talking points only — not published assets** (publishable asset capture remains V1 §5 W3–W4).

---

## 1. Week-2 execution checklist (V1 §5 row W2)

All copy is number-free (DEC-004), Minervini-name-clean (DEC-001), Hebrew-first (DEC-003), no-billing (DEC-005). `[OWNER]` = placeholder; Marketing writes no code.

| # | Task | Owner | Depends on | Done-when |
|---|---|---|---|---|
| W2.1 | **Confirm legal sign-off on the consent blurb** (§2.3 / W1.3 carryover) before any send. If not cleared, hold sends until it is — non-negotiable for the DEC-004 dataset. | Mktg `[OWNER]` ↔ Legal `[OWNER]` (V1 §6 item 4) | W1.3 draft; Legal pass | Written legal OK logged in friction log, or sends explicitly held |
| W2.2 | **Confirm Hyperscaler onboarding dependency**: invited-user onboarding path is *scoped*, NO public signup, NO billing (DEC-005); goes live W3. | Mktg `[OWNER]` ↔ Hyperscaler `[OWNER]` | W1.8 pre-stage; Hyperscaler scoping | Written confirmation onboarding scoped + no-billing |
| W2.3 | **Confirm Sprint-11/12 deploy state** of the process-hook features (Open Tasks, batch stop promotion, ratchet-up guard, RUNNER suppression, audit-review) is stable enough to *describe verbally* in 1:1s. Informational dependency only — Marketing does not own/block it. | Mktg `[OWNER]` ↔ UX/Backend `[OWNER]` | Sprint-11/12 deploy; `MARK_SPRINT11_RULINGS.md` | Verbal-describe readiness confirmed; gaps logged |
| W2.4 | **Founder sends Ring-1 invites** (target ~6–8) using §2.1 verbatim, only to candidates passing the §2.2 screening. 1:1 direct only — no group blast (V1 §4 anti-spam). | Founder `[OWNER]` | W2.1, W2.2, W1.6 screened list | Ring-1 invites sent 1:1; recipients logged privately |
| W2.5 | **Set up the private feedback channel** (closed Telegram group/DM thread) for accepted testers. Invited-only, private, no public link. | Mktg `[OWNER]` + Founder `[OWNER]` | W2.4 acceptances begin | Private channel exists, invite-only |
| W2.6 | **Build the weekly-pulse template** (≤5 questions per V1 §2 loop: biggest friction / one moment it helped / one moment wrong-confusing / RTL-clarity / would-keep-using). Hebrew, RTL, no numbers asked. | Mktg `[OWNER]` | — | Pulse template frozen, ≤5 Qs, number-free |
| W2.7 | **Capture consent at acceptance**: each accepting tester receives §2.3 blurb; consent state recorded (consented vs not). Non-consented testers still test, excluded from DEC-004 dataset. | Mktg `[OWNER]` + Founder `[OWNER]` | W2.1 legal OK; W2.4 acceptances | Consent state recorded per accepting tester (ledger structure only, zero numbers) |
| W2.8 | **Stand up / extend the internal friction log** for W2 (one row per issue → owning team UX/Hyperscaler/Backend; not published). Seed with W2 invite-delta notes + §3 DO-NOT-SAY check. | Mktg `[OWNER]` | W1 friction log | Log live, W2 items seeded |
| W2.9 | **Refresh the demo-hook script** (§3) with the new features and re-run the DO-NOT-PUBLISH self-check (no %, no $, no backtest, no Minervini-as-brand, no "AI"). | Mktg lead `[OWNER]` | W2.3 | Script + DO-NOT-SAY list approved; sign-off in friction log |

**Cross-team dependency summary (Marketing owns none):** Legal — consent-form sign-off **gates** W2 sends (V1 §6 item 4). Hyperscaler — invited-user onboarding scoped this week, live W3, no signup/no billing (DEC-005). UX/Backend — Sprint-11/12 deploy of the process-hook features stable enough to *describe* (publishable capture is W3–W4, not now). Mark — rulings already authoritative in `MARK_SPRINT11_RULINGS.md`; no Marketing action.

---

## 2. Beta-recruitment artifacts (copy-ready, Hebrew RTL)

> All four carried **verbatim from `MARKETING_V1.md` §2** (and W1 where W1 added an artifact). Deltas vs Week 1 explicitly flagged. No new numbers, no price, no Minervini name, no emojis, RTL-clean.

### 2.1 Invite message (short) — sent in W2.4

> שלום [שם],
>
> בניתי בוט טלגרם בעברית ששומר על משמעת וניהול סיכון בטרייד מומנטום — מתריע כשחורגים מהתוכנית, לא נותן טיפים ולא סוחר בשבילך.
>
> אני פותח **בטא סגורה וחינמית** לקבוצה קטנה של סוחרים שאני סומך עליהם. אין תשלום ואין מנוי. בתמורה לפידבק כן — תקבל **שנה Pro בחינם** כשמשיקים.
>
> מתאים אם: אתה סוחר מומנטום פעיל ב-US, עובד מול IBKR, ומוכן לתת פידבק כן פעם בשבוע למשך כחודש.
>
> רוצה להיכנס? תגיד לי ואשלח הסבר קצר ואיך מתחילים. אין לחץ.

**Delta vs Week 1:** none — identical text, frozen since W1.4. W2 only *uses* it (first send). Any future edit needs a logged reason.

### 2.2 Screening checklist (founder applies before each send — invite only if **all** true)

- [ ] Trades US equities on a real IBKR account (Flex available) — needs real positions to monitor.
- [ ] Active momentum/swing style with defined entry stops (not buy-and-hold) — fits the single `minervini_strict` method (DEC-002).
- [ ] Hebrew-comfortable for the UX (DEC-003).
- [ ] Trusted to give honest, non-promotional feedback and keep the beta private.
- [ ] Willing to a ~4-week feedback commitment (≈1 short check-in/week).
- [ ] Understands and can consent to anonymized usage-metric capture for future product proof (DEC-004 prerequisite).

**Delta vs Week 1:** none — same six criteria. Now applied operationally per Ring-1 recipient before W2.4 send.

### 2.3 Consent blurb — Sprint-12 dataset (DEC-004), plain Hebrew

> **הסכמה — בטא סגורה וחינמית של סנטינל**
>
> אני מצטרף/ת מרצוני לבטא סגורה וחינמית. אין תשלום, אין כרטיס אשראי, אין מנוי.
>
> אני נותן/ת הסכמה — **שניתנת לביטול בכל עת** — שמדדי שימוש **אנונימיים ומצרפיים בלבד** (לא נתוני רווח/הפסד, לא מידע שמזהה אותי אישית) ישמשו בעתיד כראיה לאיכות המוצר.
>
> אם לא אסכים — אוכל עדיין להשתתף ולבדוק; פשוט הנתונים שלי לא ייכללו במאגר ההסכמה.

**Delta vs Week 1:** none in text — same blurb W1 introduced. Status change: W1 = *draft for legal*; **W2 = must be legally signed off before W2.4 sends (W2.1).** No new commitment (free beta; anonymized + aggregated only; explicit revocability; non-consent does not block testing).

### 2.4 "1 year free Pro at launch" framing (DEC-005, exact)

> **"בטא סגורה וחינמית. אין תשלום, אין כרטיס אשראי, אין מנוי. מי שמשתתף ונותן פידבק — מקבל שנה שלמה של מסלול Pro בחינם כשמשיקים."**

Framed as a **loyalty thank-you for early shaping**, never a discount or sales close. **No price is ever stated** (no pricing model pre-Phase D, DEC-005).

**Delta vs Week 1:** none — exact V1/W1 reward string, unchanged.

---

## 3. Refreshed demo-hook script (Hebrew — process/discipline ONLY, DEC-004)

Use only in 1:1 recruiting conversations / live walkthroughs (W2+). **Not a published asset.** Frames the *discipline mechanic*, never an outcome. Single `minervini_strict` method (DEC-002), Hebrew (DEC-003), no Minervini-as-brand (DEC-001). All five new hooks are Mark-ruled authoritative (`MARK_SPRINT11_RULINGS.md`; DEC-006/-007/-008).

### Talking points (Hebrew)

1. **"הבוט הופך כל פוזיציה לרשימת פעולות ברורה — מה לעשות עכשיו, לא מה לקנות."** (Open Tasks: per-position action items, not signals — reinforces anti-positioning §1.1/§1.3.)
2. **"חצה סטופ? המשימה היא 'לסגור עכשיו' — בלי שיקול דעת רגעי בלחץ."** (Stop-discipline as a task; system enforces *your own* plan.)
3. **"כמה פוזיציות שצריכות הידוק סטופ? בלחיצה אחת מעלים את כולן יחד — בלי הקלדה, בלי טעות ידנית."** (Tap-only batch stop promotion: discipline at scale, one tap, no manual error — described as behaviour.)
4. **"רוצה לרופף סטופ? המערכת לא נותנת — בלי אישור מפורש ומתועד. סטופ עולה, לא יורד."** (Minervini ratchet-up stop guard: it blocks loosening a stop without explicit audited confirmation — pure discipline protection, no number.)
5. **"כשהסטופ שלך כבר עומד בהמלצה — אין משימה. הרשימה מציגה רק פעולה אמיתית, לא רעש."** (RUNNER no-op suppression: a task appears only when there's a *material* action — trust in the list, no figures.)
6. **"‏🧾 הפעולות שלי — אתה עובר אחורה על ההחלטות שתיעדת: מה בוצע, מה דולג, שינויי סטופ. סקירה עצמית, לא ציון."** (User audit-review: retrospective self-accountability over your own recorded decisions — review, never a score/number.)
7. **"שיטה אחת מוקשחת, לא חמישים כפתורים להתבלבל בהם — הכללים קבועים, אתה רק מבצע."** (Single hardened method, DEC-002 allowed talking point.)
8. **"בלי כשלים שקטים — נתון ישן/משוער/חלופי מסומן במפורש. מדויק לפני בטוח."** (Engineering ethos: no silent failures, explicit fallback/stale labelling — process credibility, number-free.)

### DO-NOT-SAY list (hard — DEC-004 / -001 / -002 / -005)

- Do **not** say or show any **percentage** (win rate, return, drawdown, expectancy).
- Do **not** say or show any **monetary figure** (NAV, PnL, R in $, account size, stop $ values as proof).
- Do **not** reference any **backtest / synthetic / simulated** result or equity curve.
- Do **not** cite the **founder's personal trading results**, anonymized or not, pre-counsel.
- Do **not** claim the tool **makes money / improves returns / "beats the market"** — behaviour only.
- Do **not** use **"AI"** / "smart/predictive AI" — it is a rules + statistics engine.
- Do **not** use **Minervini as a brand/endorsement** ("Minervini-approved", "your Minervini co-pilot"); acknowledgment line only, in body, never the pitch hook (DEC-001).
- Do **not** present any hook (Open Tasks, batch promotion, ratchet guard, audit-review) as **financial advice or a recommendation** — it is discipline telemetry on the user's own positions.
- Do **not** describe the **audit-review or RUNNER suppression as a performance/quality score** — it is process review, not a metric.
- Do **not** mention **price, tiers, or billing** (DEC-005) beyond the exact §2.4 reward framing.
- Do **not** demo **ALGO observed-actions as instructions** — they are non-binding, externally-managed read-outs (DEC-006 / DEC-20260511-001).

---

## 4. Week-2 success metric & feedback-capture into Sprint 12

**Success metric (qualitative, no public numbers — DEC-004):** W2 is the first outbound week. Success = **legal sign-off on the consent blurb confirmed (or sends deliberately held); Hyperscaler onboarding dependency confirmed scoped/no-billing; Ring-1 invites sent 1:1 only to screened candidates; the private feedback channel and ≤5-question weekly-pulse template stood up; consent state recorded for every accepting tester (consented vs not); and the refreshed §3 script + DO-NOT-SAY list re-passed the DO-NOT-PUBLISH self-check.** No tester counts, conversion rates, or any public figure — by design. "Done" is process completeness and DEC-compliance, not volume.

**Feedback-capture step feeding Sprint 12:** extend the internal **friction log** (V1 §2 step 3: one row per issue → owning team UX/Hyperscaler/Backend; not published) with W2 items — invite-delta notes (none this week), consent legal-sign-off outcome, any verbal-describe gaps for the five process hooks surfaced with UX/Backend, and the §3 DO-NOT-SAY sign-off line. This log plus the **consent-ledger structure** (definitions and consented/not state only — **zero numbers until Sprint 12**) is the clean, number-free handoff that V1 §5 W6 packages for the Sprint-12 consented dataset (DEC-004), and even then only after the Legal open item (V1 §6 item 1) clears.

---

*End of Sprint-12 Week-2 sheet. Continues `MARKETING_SPRINT10_WEEK1.md`; derived from `MARKETING_V1.md` §5 row W2; constrained by DEC-20260515-001..009 and `MARK_SPRINT11_RULINGS.md`. Any reintroduction of numbers, pricing, English, "AI", or Minervini-as-brand requires a new entry in `docs/DECISIONS.md`. Documentation only — no code, no commit.*
