# Marketing — Sprint 10, Week 1 Execution (Closed Beta)

> **Document type:** week-1 execution sheet (derived from `docs/teams/MARKETING_V1.md` §5 calendar, row **W1**)
> **Status:** active — Sprint 10, week 1 of the 6-week closed-beta plan
> **Owner:** Marketing Team
> **Branch:** `claude/review-system-audit-FBZ2h`
> **Binding decisions:** DEC-20260515-001 (Minervini = acknowledgment only) · DEC-20260515-002 (single `minervini_strict`) · DEC-20260515-003 (Israel/Hebrew-only) · DEC-20260515-004 (process/demo only, NO numbers) · DEC-20260515-005 (closed free beta; testers get 1yr Pro)
> **Scope:** documentation only. No code, no Supabase, no git commit/push. Independent of Hyperscaler/UX/Backend execution — dependencies are noted, not owned.
> **Working principle:** honesty over hype; no "AI" claim; no investment advice; no fabricated numbers (`AGENTS.md` / `CLAUDE.md`).

---

## 0. Sprint-10 framing — what is new this week

V1 §5 row W1 is **prep + list-building** (lock copy, draft consent, finalize invite, founder builds Rings 1–3 candidate list). No invites are sent in W1 (Ring-1 sends are W2). Sprint 10 adds an **"Open Tasks" action-items engine** (per-position, Minervini-driven tasks — e.g. "hit stop → close now", "runner → protect profit", with done/skip/notes). This is a **process-demo hook**: it shows the system's discipline *without any performance numbers*, so it is DEC-004-compliant and is folded into the beta narrative below as a recruiting/demo asset — **not** published this week (asset production is V1 §5 W3–W4).

---

## 1. Week-1 execution checklist

All copy below is number-free (DEC-004), Minervini-name-clean (DEC-001), Hebrew-first (DEC-003), no-billing (DEC-005). `[OWNER]` = placeholder; Marketing writes no code.

| # | Task | Owner | Depends on | Done-when |
|---|---|---|---|---|
| W1.1 | Lock positioning §1 (one-sentence HE/EN), 5 anti-positioning lines, honest category ("מנוע כללים + סטטיסטיקה", **no "AI"**) as the frozen W1 copy block. | Mktg lead `[OWNER]` | — | Copy block frozen + linked from V1 §1 |
| W1.2 | Lock the **disclaimer** text (HE primary; EN deferred per DEC-003) verbatim from V1 §3 — to appear on every public surface and in-bot. | Mktg lead `[OWNER]` | — | Single canonical string agreed |
| W1.3 | Draft the **plain-Hebrew consent form** (free closed beta + revocable opt-in to anonymized aggregated metrics as future product evidence; never raw PnL, never identifiable) — DEC-004 dataset prerequisite. | Mktg `[OWNER]` | Legal `[OWNER]` pass scheduled (V1 §6 item 4, lands ≤ W2) | Draft ready for legal; states consent is revocable |
| W1.4 | **Finalize the invite message** (§2 below) — confirm against prior V1 wording, log deltas. | Mktg lead `[OWNER]` | — | Final text + delta note recorded |
| W1.5 | Finalize the **screening checklist** (§2 below) — founder's gate before any send. | Mktg `[OWNER]` + Founder `[OWNER]` | — | Checklist ready for founder use |
| W1.6 | Founder **builds the candidate list** (Rings 1–3 per V1 §2: ~6–8 / ~4–6 / ~3) against screening; private list, not published. | Founder `[OWNER]` | W1.5 | List exists, screened, private |
| W1.7 | Draft the **"Open Tasks" beta-demo talking points** (§3 below) for use in W2 invite conversations — internal script only this week, not a published asset. | Mktg `[OWNER]` | UX `[OWNER]`: Open Tasks / stop-promotion UX behaviour stable enough to describe verbally (informational dependency only — Marketing does not own or block it) | Talking points + DO-NOT-SAY list approved |
| W1.8 | Pre-stage the **W2 onboarding dependency**: confirm with Hyperscaler that the invited-user onboarding path (NO public signup, NO billing — DEC-005) is *scoped* (it goes live W3). | Mktg `[OWNER]` ↔ Hyperscaler `[OWNER]` | Hyperscaler scoping (V1 §5 W2 dependency) | Written confirmation onboarding is scoped, no-billing |
| W1.9 | DEC compliance self-check: run every W1 artifact past the V1 §3 DO-NOT-PUBLISH list (no %, no $, no backtest, no Minervini-as-brand, no "AI"). | Mktg lead `[OWNER]` | W1.1–W1.7 | Sign-off line recorded in friction log |

**Dependencies summary (Marketing does not own these):** Hyperscaler — invited-user onboarding path scoped this week, live W3, no signup/no billing (DEC-005). UX — "Open Tasks" action items + stop-promotion improvements stable enough to *describe* (publishable asset capture is W3–W4, not W1). Legal — consent-form pass before W2 sends (V1 §6 item 4).

---

## 2. Beta-recruitment artifacts (copy-ready, Hebrew RTL)

> All four artifacts below are **carried verbatim from `MARKETING_V1.md` §2** to preserve consistency. Deltas vs V1 are explicitly flagged. No new numbers, no price, no Minervini name, no emojis, RTL-clean.

### 2.1 Invite message (short)

> שלום [שם],
>
> בניתי בוט טלגרם בעברית ששומר על משמעת וניהול סיכון בטרייד מומנטום — מתריע כשחורגים מהתוכנית, לא נותן טיפים ולא סוחר בשבילך.
>
> אני פותח **בטא סגורה וחינמית** לקבוצה קטנה של סוחרים שאני סומך עליהם. אין תשלום ואין מנוי. בתמורה לפידבק כן — תקבל **שנה Pro בחינם** כשמשיקים.
>
> מתאים אם: אתה סוחר מומנטום פעיל ב-US, עובד מול IBKR, ומוכן לתת פידבק כן פעם בשבוע למשך כחודש.
>
> רוצה להיכנס? תגיד לי ואשלח הסבר קצר ואיך מתחילים. אין לחץ.

**Delta vs V1 §2:** none — identical text, frozen for W1. (W1.4 only confirms it; any future edit needs a logged reason.)

### 2.2 Screening checklist (founder applies before sending — invite only if **all** true)

- [ ] Trades US equities on a real IBKR account (Flex available) — the product needs real positions to monitor.
- [ ] Active momentum/swing style with defined entry stops (not buy-and-hold) — fits the single `minervini_strict` method (DEC-002).
- [ ] Hebrew-comfortable for the UX (DEC-003).
- [ ] Trusted to give honest, non-promotional feedback and keep the beta private.
- [ ] Willing to a ~4-week feedback commitment (≈1 short check-in/week).
- [ ] Understands and can consent to anonymized usage-metric capture for future product proof (DEC-004 prerequisite).

**Delta vs V1 §2:** none — same six criteria, reformatted as a tick-list for founder operational use.

### 2.3 Consent blurb — Sprint-12 dataset (DEC-004), plain Hebrew

> **הסכמה — בטא סגורה וחינמית של סנטינל**
>
> אני מצטרף/ת מרצוני לבטא סגורה וחינמית. אין תשלום, אין כרטיס אשראי, אין מנוי.
>
> אני נותן/ת הסכמה — **שניתנת לביטול בכל עת** — שמדדי שימוש **אנונימיים ומצרפיים בלבד** (לא נתוני רווח/הפסד, לא מידע שמזהה אותי אישית) ישמשו בעתיד כראיה לאיכות המוצר.
>
> אם לא אסכים — אוכל עדיין להשתתף ולבדוק; פשוט הנתונים שלי לא ייכללו במאגר ההסכמה.

(Internal note: consent state is recorded per V1 §2 loop; non-consented testers still test but are excluded from the DEC-004 dataset. Legal pass required before W2 — V1 §6 item 4.)

**Delta vs V1 §2:** V1 described the consent mechanics in prose but gave **no copy-ready Hebrew blurb**. This is a *new artifact* that operationalizes V1 §2 step 1 verbatim in intent — it adds **no new commitment** (free beta; anonymized + aggregated only; explicit revocability; non-consent does not block testing). Flag for legal sign-off.

### 2.4 "1 year free Pro at launch" framing (DEC-005, exact)

> **"בטא סגורה וחינמית. אין תשלום, אין כרטיס אשראי, אין מנוי. מי שמשתתף ונותן פידבק — מקבל שנה שלמה של מסלול Pro בחינם כשמשיקים."**

Framed as a **loyalty thank-you for early shaping**, never as a discount or a sales close. **No price is ever stated** (no pricing model exists pre-Phase D, DEC-005).

**Delta vs V1 §2:** none — exact V1 reward string, unchanged.

---

## 3. "Open Tasks" as a beta demo hook (process only — DEC-004)

Use only in 1:1 recruiting conversations / live walkthroughs (W2+). **Not a published asset in W1.** Frames the *discipline mechanic*, never an outcome. Aligned to the single `minervini_strict` method (DEC-002), Hebrew (DEC-003), no Minervini-as-brand (DEC-001).

### Talking points (Hebrew, process/discipline only)

1. **"הבוט הופך כל פוזיציה לרשימת פעולות ברורה — מה לעשות עכשיו, לא מה לקנות."** (Per-position action items, not signals — reinforces anti-positioning §1.1/§1.3.)
2. **"חצה סטופ? המשימה היא 'לסגור עכשיו' — בלי שיקול דעת רגעי בלחץ."** (Stop-discipline as a task; shows the system enforcing the user's own plan.)
3. **"פוזיציה רצה? המשימה היא 'להגן על הרווח / להעלות סטופ' — תהליך, לא תחושה."** (Stop-promotion / profit-protection as a process step — the UX stop-promotion improvement, described as behaviour.)
4. **"כל משימה נסגרת ב'בוצע / דילגתי / הערה' — כך נבנה תיעוד משמעת שלך, לעצמך."** (Closed-loop accountability; ties to the consented feedback story without any metric.)
5. **"שיטה אחת מוקשחת, לא חמישים כפתורים להתבלבל בהם — הכללים קבועים, אתה רק מבצע."** (Single hardened method, DEC-002 allowed talking point.)

### DO-NOT-SAY list (hard — DEC-004 / DEC-001 / DEC-002)

- Do **not** say or show any **percentage** (win rate, return, drawdown, expectancy).
- Do **not** say or show any **monetary figure** (NAV, PnL, R in $, account size).
- Do **not** reference any **backtest / synthetic / simulated** result or equity curve.
- Do **not** cite the **founder's personal trading results**, anonymized or not.
- Do **not** claim the tool **makes money / improves returns / "beats the market"** — describe behaviour only.
- Do **not** use **"AI"** or "smart/predictive AI" — it is a rules + statistics engine.
- Do **not** use **Minervini as a brand/endorsement** ("Minervini-approved", "your Minervini co-pilot"); acknowledgment line only, in body, never in pitch hook (DEC-001).
- Do **not** present **Open Tasks** as financial advice or a recommendation — it is discipline telemetry on the user's own positions.
- Do **not** mention **price, tiers, or billing** (DEC-005) beyond the exact §2.4 reward framing.

---

## 4. Week-1 success metric & feedback-capture into Sprint 12

**Success metric (qualitative, no public numbers — DEC-004):** W1 is *prep, not outreach*. Success = **all W1.1–W1.9 artifacts frozen and DEC-compliant, a screened private Ring 1–3 candidate list exists, the consent draft is ready for legal, and the W2 onboarding dependency is confirmed scoped with Hyperscaler (no billing).** No tester counts, no conversion rates, nothing public — by design.

**Feedback-capture step feeding Sprint 12:** open the internal **friction log** now (V1 §2 step 3: one row per issue → owning team UX/Hyperscaler/Backend; not published) and seed it with W1 items — invite-copy delta notes, consent-form legal questions, the new §3 DO-NOT-SAY list, and any "Open Tasks" description gaps surfaced with UX. This log plus the **consent ledger structure** (definitions only, **zero numbers** until Sprint 12) is the clean, number-free handoff that V1 §5 W6 packages for the Sprint-12 consented dataset (DEC-004) — and even then only after the Legal open item (V1 §6 item 1) clears.

---

*End of Sprint-10 Week-1 sheet. Derived from `MARKETING_V1.md` (§1–§6) and constrained by DEC-20260515-001..005. Any reintroduction of numbers, pricing, English, "AI", or Minervini-as-brand requires a new entry in `docs/DECISIONS.md`. Documentation only — no code, no commit.*
