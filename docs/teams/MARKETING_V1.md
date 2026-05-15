# Marketing Team — V1 Plan (decision-grounded)

> **Document type:** execution-ready plan
> **Status:** V1 — supersedes `MARKETING_PLAN_V0.md` where the 5 founder decisions now constrain it
> **Owner:** Marketing Team
> **Branch:** `claude/review-system-audit-FBZ2h`
> **Binding decisions:** DEC-20260515-001 .. DEC-20260515-005 (see `docs/DECISIONS.md`)
> **Working principle (`CLAUDE.md` / `AGENTS.md`):** honesty over hype. No "AI" claim for rule-based + statistical behaviour. No investment advice. No fabricated numbers.

---

## 0. What changed from V0 (decision deltas)

| V0 assumption | Now constrained by | V1 reality |
|---|---|---|
| Hero could say "Trade like Minervini" (Phase 3, Q1) | **DEC-001** | Minervini name is acknowledgment / fair-use ONLY. Never a hero line, brand, endorsement, or logo. |
| 4 methodology profiles / tunable strategy implied as a sellable feature | **DEC-002** | One profile only: `minervini_strict`. Market simplicity ("one validated method"), not configurability. |
| "Israel-only vs global" was an open founder question (V0 Q3) | **DEC-003** | Decided: Israel-only, Hebrew-first. English deferred ~Q3. No translation work in plan body. |
| Anonymized founder track record / NAV curve as a marketing asset (V0 Q7, Q1.3) | **DEC-004** | Forbidden. Process/demo only. No %, no PnL, no synthetic backtest. Consented beta metrics only from Sprint 12. |
| Q2 "convert 5 of Tomer's friends to **paying** users"; pricing experiment ($39/$79/$149) | **DEC-005** | No paid acquisition, no pricing test, no billing in Q1. Closed FREE beta. Beta testers get 1 year free Pro at launch. |

V0 Phase 1 (asset inventory), Phase 2 (personas A/D primary, B deferred, C/E rejected) remain valid and are not repeated here.

---

## 1. Positioning V1

### One-sentence positioning (Minervini name NOT used as brand)

> **"Sentinel is the Hebrew-native discipline and risk-control bot for momentum traders who keep breaking their own rules under pressure."**

Hebrew (user-facing, RTL):

> **"סנטינל — בוט ההגנה והמשמעת בעברית לסוחרי מומנטום שמפרים לעצמם את הכללים בלחץ."**

This sentence stands fully on its own without any third-party name (DEC-001 compliant).

### Permitted acknowledgment line (fair-use, secondary, never the hero)

Allowed, only in a body/"how it works" section, never in the hero or as endorsement:

> "Built on publicly documented momentum-trading principles, including the trend-template approach popularised in *Trade Like a Stock Market Wizard* by Mark Minervini."

Hebrew:

> "מבוסס על עקרונות מסחר מומנטום מתועדים בפומבי, בהם גישת תבנית-המגמה שהוצגה בספר *Trade Like a Stock Market Wizard* מאת מארק מינרוויני."

Rules (DEC-001): no "your Minervini co-pilot", no "Minervini-approved", no photo/likeness/logo, no implied partnership. Book title in italics as a citation, author credited factually. Revisit licensing only with real traction.

### Honest category

Sentinel is a **rule-based, statistics-driven risk and discipline monitor**. It is NOT marketed as "AI". The adaptive ladder, state machine, and heat score are deterministic rules over the user's own recent campaign statistics. Approved category phrase: **"מנוע כללים + סטטיסטיקה"** ("rules + statistics engine"). The word "AI" must not appear in any public copy (`AGENTS.md` honesty line; V0 had a leftover "AI-driven" tagline — retired here).

### 5 anti-positioning lines (we are NOT)

1. **Not a signal service.** Sentinel never tells you what to buy or sell.
2. **Not an auto-trader / broker.** It never places an order and never holds funds; it reads IBKR Flex data only.
3. **Not investment advice.** Every message is risk telemetry about your own positions, not a recommendation.
4. **Not a backtester or a performance claim.** We show *how the system behaves*, never a track record or returns.
5. **Not for buy-and-hold investors.** No entry stop and no campaign means nothing for Sentinel to monitor.

(Single-method note, DEC-002: "One validated method, hardened — not 50 knobs to misconfigure" is an allowed positive talking point.)

---

## 2. Closed-beta recruitment plan — this IS the Q1 go-to-market (NOT paid acquisition)

Per DEC-005 this replaces the entire V0 "first paid users" track. No ads, no pricing page, no billing.

### Who to invite (founder-selected only)

Three concentric rings, all chosen personally by the founder:

1. **Ring 1 — trusted Hebrew-speaking momentum traders** (highest signal): people the founder already knows who actively swing/momentum-trade US equities on IBKR and follow trend-template / momentum content. Target ~6–8.
2. **Ring 2 — friends who trade** (medium signal): friends with real but lighter trading activity. Target ~4–6.
3. **Ring 3 — family / close circle** (lowest trading signal, highest goodwill / honesty of feedback): up to ~3.

**Target N for the closed beta: 10–15 active testers**, with **5+ who reach DEC-004's consented-data bar** (the gate Sprint 12 needs). Quality and consent over volume.

### Reward framing (DEC-005, exact)

> **"בטא סגורה וחינמית. אין תשלום, אין כרטיס אשראי, אין מנוי. מי שמשתתף ונותן פידבק — מקבל שנה שלמה של מסלול Pro בחינם כשמשיקים."**
>
> ("Closed free beta. No payment, no credit card, no subscription. Participants who give feedback receive a full year of the Pro tier free at launch.")

Framed as a **loyalty thank-you for early shaping**, never as a discount or a sales close. No price is ever stated (no pricing model exists pre-Phase D, DEC-005).

### Invite message (Hebrew, short, RTL-friendly, copy-ready)

> שלום [שם],
>
> בניתי בוט טלגרם בעברית ששומר על משמעת וניהול סיכון בטרייד מומנטום — מתריע כשחורגים מהתוכנית, לא נותן טיפים ולא סוחר בשבילך.
>
> אני פותח **בטא סגורה וחינמית** לקבוצה קטנה של סוחרים שאני סומך עליהם. אין תשלום ואין מנוי. בתמורה לפידבק כן — תקבל **שנה Pro בחינם** כשמשיקים.
>
> מתאים אם: אתה סוחר מומנטום פעיל ב-US, עובד מול IBKR, ומוכן לתת פידבק כן פעם בשבוע למשך כחודש.
>
> רוצה להיכנס? תגיד לי ואשלח הסבר קצר ואיך מתחילים. אין לחץ.

(Plain, no emojis, RTL-clean, no numbers, no advice, no Minervini name — DEC-001/003/004/005 all satisfied.)

### Screening criteria (founder applies before sending)

Invite only if **all** are true:
- Trades US equities on a real IBKR account (Flex available) — the product needs real positions to monitor.
- Active momentum/swing style with defined entry stops (not buy-and-hold; DEC-002 single method fits them).
- Hebrew-comfortable for the UX.
- Trusted to give honest, non-promotional feedback and to keep the beta private.
- Willing to a ~4-week feedback commitment (≈1 short check-in/week).
- **Understands and can consent** to anonymized usage-metric capture for future product proof (DEC-004 prerequisite).

### Feedback-capture loop → feeds Sprint 12 consented dataset (DEC-004)

1. **Onboarding consent:** at invite acceptance, tester signs a short plain-Hebrew consent: (a) joining a free closed beta, (b) explicit, revocable opt-in to *anonymized, aggregated* usage metrics being usable as future product evidence — never raw PnL, never identifiable. Consent state is recorded; non-consented testers still test but their data is excluded from the DEC-004 dataset.
2. **Weekly structured pulse** (Telegram or short form, ≤5 questions): biggest friction, one moment the bot helped, one moment it was wrong/confusing, RTL/clarity issues, would-you-keep-using.
3. **Friction log:** Marketing maintains an internal log (one row per reported issue → owning team: UX / Hyperscaler / Backend). Not published.
4. **Sprint 12 handoff:** at Sprint 12, the *consented* cohort's anonymized aggregate behaviour metrics become the **only** source eligible for any future "trust with numbers" material — and even then only after the open legal item (§6) clears. Until Sprint 12: zero numbers anywhere.

---

## 3. Trust rail without numbers (DEC-004)

The trust story is **behaviour, not performance**.

### ALLOWED public process/demo material

- **Annotated screenshots / short GIF of the state machine reacting:** a position moving NEW → PROVING → WORKING → PROFIT_PROTECTION / YELLOW_FLAG / BROKEN, with the Hebrew alert that fires on each *transition*. Show the mechanic, not the outcome.
- **"How it cuts drawdown" explainer (qualitative):** narrative + diagram of the settle period and the adaptive ladder reducing size after a losing cluster and gating revenge re-sizing — described as *behaviour rules*, with **no equity curve, no %, no $**.
- **"What an alert looks like"** sample messages (synthetic, clearly labelled illustrative).
- **Anonymized, redacted sample PDF report layout** with all figures replaced by neutral placeholders (e.g. "—" / "XX") — sells the *format and rigor*, not results. (Note: V0's "anonymized real weekly report" lead magnet is **withdrawn**; replaced by this redacted layout-only artifact.)
- **Engineering-ethos content:** "no silent failures", explicit fallback/stale-data labelling, single hardened method (DEC-002) — process credibility, fully number-free.

### DO NOT PUBLISH list (hard, DEC-004)

- ❌ Any percentage: win rate, return %, drawdown %, expectancy.
- ❌ Any monetary figure: NAV, PnL, R in dollars, account size.
- ❌ Any synthetic/backtest output or simulated equity curve.
- ❌ Founder's personal trading results, anonymized or not, in any form, pre-counsel.
- ❌ Any chart with a populated y-axis of performance.
- ❌ Testimonials that quote numbers ("it made me X%") — strip or reject.
- ✅ Real numbers become possible **only** from consented beta metrics, **only** from Sprint 12, **only** after the legal open item (§6) is resolved.

### Compliance / disclaimer stance

- Every public surface and the bot itself carries: **"סנטינל הוא כלי בקרת סיכון ומשמעת בלבד. אינו מהווה ייעוץ השקעות, שיווק השקעות או המלצה. ההחלטות והאחריות שלך."** ("Sentinel is a risk-control and discipline tool only. Not investment advice, investment marketing, or a recommendation. Decisions and responsibility are yours.")
- Position strictly as *telemetry on the user's own positions*, never as advice or signals (anti-positioning §1.4 reinforces this).
- ISA (Israel Securities Authority) classification of a paid sizing-alert tool remains a **legal open item (§6)** — but the closed FREE beta with no billing and no recommendations (DEC-005) materially lowers near-term exposure. Counsel must still confirm before any paid/numbers stage.

---

## 4. Israel / Hebrew channel plan

Target: ~5k active Hebrew-speaking Israeli momentum traders (DEC-003). Q1 channel use is **recruitment-only and non-promotional** (closed beta, DEC-005) — these channels are where the founder *knows people*, not where we advertise.

| Channel | Use in V1 | Notes |
|---|---|---|
| Founder's personal trader network | **Primary** beta-recruitment source | Direct 1:1 invites only. No public post. |
| Israeli active-trading Telegram/WhatsApp groups (e.g. "סוחרים אקטיביים"-type) | Identify candidates the founder already trusts; DM only | No broadcast/spam (anti-spam ethos, `AGENTS.md`). Group blasts forbidden in beta. |
| Hebrew finance YouTube / educator circles (Persona D) | Relationship-building only in Q1; partner pilots are post-beta | Educators are a *future* channel, not a beta-recruitment blast. |
| IB-Israel / local trader meetups | Warm intros to Ring-1 candidates | In-person trust fits founder-selected model. |

**Deferred to Q3 English (DEC-003), no work now:** English landing page, i18n strings, English content, Stocktwits/X/Reddit, any non-Hebrew channel, Minervini-ecosystem outreach (also gated by DEC-001). These ride on Hyperscaler Phase C and are explicitly out of the V1 plan body.

---

## 5. Six-week execution calendar

Owners are placeholders. Marketing does no code. Hard dependencies: **Hyperscaler** (invited-user onboarding, **no public signup, no billing** — DEC-005) and **UX team** (Telegram clarity improvements). All copy is number-free (DEC-004) and Minervini-name-clean (DEC-001).

| Week | Marketing deliverables | Owner | Depends on |
|---|---|---|---|
| **W1** | Lock positioning §1 + anti-positioning + disclaimer text (HE/EN). Draft consent form (plain Hebrew). Finalize invite message. Founder builds the candidate list (Rings 1–3) against §2 screening. | Mktg lead `[OWNER]` + Founder `[OWNER]` | — |
| **W2** | Founder sends Ring-1 invites (target ~6–8). Set up private feedback channel + weekly-pulse template. Build internal friction log. | Founder `[OWNER]` + Mktg `[OWNER]` | Hyperscaler: invited-user onboarding path scoped (no signup/billing) |
| **W3** | First testers onboarded. Send Ring-2 invites. Run pulse #1. Start ALLOWED process/demo asset set: state-machine annotated screenshots + "how it cuts drawdown" qualitative explainer. | Mktg `[OWNER]` | **Hyperscaler:** invited-user onboarding live for first testers. **UX:** any RTL/clarity fixes from early friction |
| **W4** | Ring-3 invites if capacity. Pulse #2. Triage friction log → route to UX/Hyperscaler/Backend. Build redacted sample-PDF layout artifact. Verify every asset against the DO-NOT-PUBLISH list. | Mktg `[OWNER]` + UX `[OWNER]` | UX: Telegram clarity improvements landing; Hyperscaler: onboarding stable for ~10 users |
| **W5** | Reach 10–15 active testers. Pulse #3. Confirm ≥5 testers have signed consent (DEC-004 gate). Compliance review of all public-facing copy (disclaimer everywhere, no numbers, no Minervini-as-brand). | Mktg `[OWNER]` + Founder `[OWNER]` | Legal `[OWNER]` review of disclaimer/positioning |
| **W6** | Pulse #4 + closed-beta retro. Package consented-cohort *structure* (definitions, consent ledger — **still zero numbers**) as the clean handoff for Sprint 12. Decide which W3–W4 assets are publish-ready (process-only). Write Marketing V2 trigger list. | Mktg `[OWNER]` | Sprint 12 planning intake |

**Exit criteria (end W6):** 10–15 active consented-aware testers; ≥5 consented for DEC-004; friction log routed; a published-ready, number-free, name-clean process/demo asset set; consent ledger handed to Sprint 12. **No** pricing, **no** billing, **no** public numbers, **no** paid acquisition — by design.

---

## 6. Open items for the founder (only genuinely undecided post-DEC)

The 5 decisions closed positioning (DEC-001/002), geography (DEC-003), proof policy (DEC-004), and GTM model/pricing-timing (DEC-005). Remaining genuinely-open items:

1. **Legal counsel for future numbers + ISA posture.** Before *any* Sprint-12 consented metric is ever published, an Israeli securities lawyer must (a) confirm anonymized aggregate beta metrics are publishable, (b) give the ISA classification for the eventual *paid* sizing-alert tool. The free no-billing beta defers urgency but does not remove this. **Owner: Legal + Founder.**
2. **Domain & brand name.** Is "Sentinel Trading" final? Is a domain (`.co.il` preferred for DEC-003 Israel-first) reserved? Trademark search advisable since the Minervini name cannot carry the brand (DEC-001) — Sentinel's *own* mark must be strong. **Owner: Founder.**
3. **Founder as public face vs anonymous.** Affects future (post-beta, Q3+) content. Not blocking the closed beta. **Owner: Founder.**
4. **Beta-cohort consent form legal sign-off.** Plain-Hebrew consent (§2) should get a quick legal pass before W2 sends — low cost, de-risks the entire DEC-004 dataset. **Owner: Legal + Founder.**

All other former V0 questions are now answered by DEC-001..005 and are closed.

---

*End of V1. Supersedes V0 where the 5 decisions constrain it. Any reintroduction of numbers, pricing, English, or Minervini-as-brand requires a new decision in `docs/DECISIONS.md`.*
