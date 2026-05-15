# Marketing — Sprint 13, Week 3 Execution (Closed Beta — First Onboard + Ring-2 + Pulse #1)

> **Document type:** week-3 execution sheet (derived from `docs/teams/MARKETING_V1.md` §5 calendar, row **W3**)
> **Status:** active — Sprint 13, week 3 of the 6-week closed-beta plan
> **Owner:** Marketing Team
> **Branch:** `claude/review-system-audit-FBZ2h`
> **Continues from:** `docs/teams/MARKETING_SPRINT12_WEEK2.md` (W2 = first Ring-1 sends — deltas only noted below)
> **Binding decisions:** DEC-20260515-001 (Minervini = acknowledgment only) · -002 (single `minervini_strict`) · -003 (Israel/Hebrew-only) · -004 (process/demo only, NO numbers) · -005 (closed free beta; testers get 1yr Pro) · -006/-007/-008 (process-hook features, Mark-ruled) · -009 (rate-limit unchanged)
> **Scope:** documentation only. No code, no Supabase, no git commit/push. Independent of Hyperscaler/UX/Backend/Mark execution — dependencies noted, not owned.
> **Working principle:** honesty over hype; no "AI"; no investment advice; no fabricated numbers (`AGENTS.md` / `CLAUDE.md`).

---

## 0. Continuity from Week 2 — what changed

W2 (first outbound) closed: consent blurb gated on legal, Hyperscaler onboarding dependency confirmed scoped/no-billing, Ring-1 invites sent 1:1 to screened candidates, private feedback channel + ≤5-Q pulse template stood up, consent-state ledger structure live (zero numbers), §3 demo-hook script re-passed the DO-NOT-PUBLISH self-check.

**W3 is the first *inbound* week.** Per V1 §5 row W3 the deliverables are: first testers onboarded → send Ring-2 invites → run **Pulse #1** → begin the **ALLOWED published process/demo asset set** (state-machine annotated screenshots + the "how it cuts drawdown" qualitative explainer). New since W2: Sprint-13 theme is **operational hardening / data hygiene** — the `deploy_watcher.sh` stale-network finding (`SPRINT13_PLAN.md` input #1, HIGH/infra) makes **deploy stability a hard cross-team dependency** for W3 onboarding (a tester staring at a dead bot during deploy is the worst possible first impression). The five process-demo hooks stay 1:1 talking points only; W3 is the first week any of them is captured as a *publishable* asset, and only the DEC-004-allowed forms (mechanic, never outcome).

---

## 1. Week-3 execution checklist (V1 §5 row W3)

All copy is number-free (DEC-004), Minervini-name-clean (DEC-001), Hebrew-first (DEC-003), no-billing (DEC-005). `[OWNER]` = placeholder; Marketing writes no code.

| # | Task | Owner | Depends on | Done-when |
|---|---|---|---|---|
| W3.1 | **Confirm Sprint-13 deploy stability before first onboard.** Get written confirmation from Infra that the `deploy_watcher.sh` stale-network risk (`SPRINT13_PLAN.md` input #1) is either fixed/mitigated OR that no `--build` deploy will run during a tester's onboarding window. Marketing does **not** own/block the fix — this is an informational go/no-go gate for *when* to onboard. | Mktg `[OWNER]` ↔ Infra/Backend `[OWNER]` | Sprint-13 Wave-2 deploy; `SPRINT13_DESIGN.md` | Written "deploy stable for onboarding window" (or onboarding deliberately timed around deploys); logged in friction log |
| W3.2 | **Confirm Hyperscaler invited-user onboarding is LIVE** (W2.2 was *scoped*; W3 needs it *live* for the first testers — V1 §5 W3 "Depends on"). NO public signup, NO billing (DEC-005). | Mktg `[OWNER]` ↔ Hyperscaler `[OWNER]` | W2.2 scoping; Hyperscaler onboarding live | Written confirmation onboarding live + no-billing; first-tester path walkthrough done |
| W3.3 | **Onboard the first accepted Ring-1 testers** (founder-led 1:1): walk each through invited entry, confirm bot reachable, point to the private feedback channel and `🧾 הפעולות שלי` self-review surface. Hold onboarding for anyone if W3.1 is not green. | Founder `[OWNER]` + Mktg `[OWNER]` | W3.1, W3.2; W2.4 acceptances | Each first tester live in the bot via invited path; logged privately (state only, zero numbers) |
| W3.4 | **Capture consent at/after onboarding** for each tester not already recorded in W2.7 (legal-signed §2.3 blurb; consented vs not). Non-consented testers still test, excluded from the DEC-004 dataset. Re-confirm the W2.1 legal status is still **OK** (V1 §6 item 4) before relying on any consent for the dataset. | Mktg `[OWNER]` + Founder `[OWNER]` | W2.1 legal OK; W3.3 | Consent state recorded per onboarded tester (ledger structure only, zero numbers) |
| W3.5 | **Send Ring-2 invites** (target ~4–6, V1 §2) using §2.1 verbatim, only to candidates passing the §2.2 screening. 1:1 direct only — no group blast (V1 §4 anti-spam). | Founder `[OWNER]` | W2.4 Ring-1 sent; §2.2 screened Ring-2 list | Ring-2 invites sent 1:1; recipients logged privately |
| W3.6 | **Run Pulse #1** with onboarded testers (the W2.6 ≤5-Q template, Hebrew/RTL, number-free). Distribute via the private channel; collect qualitative replies only. | Mktg `[OWNER]` | W2.6 template; W3.3 onboarded testers | Pulse #1 sent to all onboarded testers; responses collected into the feedback-synthesis template (§3) |
| W3.7 | **Begin the ALLOWED published process/demo asset set** (V1 §3 / §5 W3): (a) state-machine annotated screenshots (NEW→PROVING→WORKING→PROFIT_PROTECTION / YELLOW_FLAG / BROKEN) showing the Hebrew alert per *transition*; (b) the "how it cuts drawdown" qualitative explainer (settle period + adaptive ladder as *behaviour rules*). Draft only this week; verified against DO-NOT-PUBLISH at W4. | Mktg lead `[OWNER]` | W3.1 (assets must reflect a *stable* deployed UI); UX RTL/clarity inputs | Asset drafts exist, mechanic-only, zero %/$/curve/AI/Minervini-as-brand; self-check noted in friction log |
| W3.8 | **Triage early friction → route.** First real-tester friction (onboarding, RTL, clarity) logged one-row-per-issue → owning team UX/Hyperscaler/Backend; not published. Seed with Ring-2 invite-delta notes (none — see §2) + any deploy-window gaps from W3.1. | Mktg `[OWNER]` | W2.8 friction log; W3.3, W3.6 | Log extended with W3 items; each routed to an owning team |
| W3.9 | **Re-run the DO-NOT-PUBLISH self-check** on the new W3.7 asset drafts and the §3 demo-hook script (no %, no $, no backtest, no founder PnL, no "AI", no Minervini-as-brand, no price/tiers). | Mktg lead `[OWNER]` | W3.7 | Self-check passed; sign-off line in friction log |

**Cross-team dependency summary (Marketing owns none):**
- **Infra/Backend — Sprint-13 deploy stability (NEW, gates *timing* of W3.3 onboarding).** The `deploy_watcher.sh` stale-network finding (`SPRINT13_PLAN.md` #1) is HIGH/infra and Mark-ruled in Wave 1; Marketing only needs the written "stable enough to onboard a first tester" confirmation. Marketing does not own, design, or block the fix.
- **Hyperscaler — invited-user onboarding must be LIVE this week** (was scoped in W2), no signup / no billing (DEC-005).
- **UX — RTL/clarity fixes from early friction** feed both W3.3 onboarding quality and the W3.7 asset accuracy.
- **Legal — consent-form sign-off must remain valid** (W2.1 / V1 §6 item 4); any retraction *holds* W3.4 dataset reliance, not testing itself.
- **Mark — `MARK_SPRINT13_RULINGS.md`** is the deploy/data-hygiene authority; **no Marketing action** (informational only).

---

## 2. Beta-recruitment artifacts (copy-ready, Hebrew RTL) — deltas only

> All four carried **verbatim from `MARKETING_SPRINT12_WEEK2.md` §2 / `MARKETING_V1.md` §2**. No new numbers, no price, no Minervini name, no emojis, RTL-clean. Deltas vs Week 2 explicitly flagged; "none" = byte-identical, frozen.

### 2.1 Invite message (short) — reused for Ring-2 in W3.5
> **Delta vs Week 2: NONE.** Identical text, frozen since W1.4. W3 reuses the *same* verbatim message for Ring-2 (V1 §2 says one invite message for all rings). No edit — any future change needs a logged reason. (Text: `MARKETING_SPRINT12_WEEK2.md` §2.1.)

### 2.2 Screening checklist
> **Delta vs Week 2: NONE.** Same six criteria (`MARKETING_SPRINT12_WEEK2.md` §2.2). Now applied operationally per **Ring-2** recipient before each W3.5 send (same bar as Ring-1; quality/consent over volume, V1 §2).

### 2.3 Consent blurb — Sprint-12 dataset (DEC-004)
> **Delta vs Week 2: NONE in text.** Same legally-gated blurb (`MARKETING_SPRINT12_WEEK2.md` §2.3). **Status note:** W2 = "must be legally signed off before sends"; **W3 = legal OK must remain valid for the dataset to count** (W3.4 re-confirms; if Legal retracts, testing continues but DEC-004 dataset reliance is held — V1 §6 item 4). No new commitment.

### 2.4 "1 year free Pro at launch" framing (DEC-005, exact)
> **Delta vs Week 2: NONE.** Exact V1/W2 reward string, unchanged. Loyalty thank-you for early shaping, never a discount or sales close; **no price ever stated** (no pricing model pre-Phase D, DEC-005).

*(No new artifact is introduced in W3. The W3.7 published process/demo assets are NOT recruitment artifacts — they are DEC-004 trust-rail material, drafted not published this week.)*

---

## 3. Feedback-synthesis template (Hebrew, qualitative — feeds the Sprint-12 dataset)

> Internal synthesis sheet for **Pulse #1** (and later pulses). Captures **what testers say about discipline/process** — qualitative only. **Explicitly NO numbers** of any kind: no counts, no scores, no %, no $, no "X of Y said". This is the structured, number-free input that V1 §5 W6 packages for the Sprint-12 consented dataset (DEC-004), and even then only after the Legal open item (V1 §6 item 1) clears. Quotes are paraphrased/anonymized; never attach raw PnL or identifiable detail (DEC-004 / consent blurb §2.3).

**Per-pulse synthesis (one block per pulse, prose only — no tables of metrics):**

- **‏מה גרם הכי הרבה חיכוך?** (Biggest friction) — themes in words: where the discipline flow felt heavy, confusing, or got in the way. Route each to an owning team (UX / Hyperscaler / Backend) in the friction log — *that routing is the only "tally", and it stays internal*.
- **‏רגע אחד שבו הבוט עזר למשמעת.** (One moment it helped) — describe the *process* moment (e.g. "החזיק אותי בתוכנית כשרציתי לרופף סטופ"), never an outcome ("עזר לי להרוויח" → strip/reject per §4 DO-NOT-SAY).
- **‏רגע אחד שבו טעה / בלבל.** (One moment wrong/confusing) — the discipline mechanic that misfired or read unclearly. Feeds W3.8 routing + W3.7 asset accuracy.
- **‏בעיות RTL / בהירות בעברית.** (RTL / Hebrew clarity) — exact phrasing/layout issues, verbatim Hebrew snippets. Direct UX input.
- **‏האם תמשיך להשתמש? — ולמה (במילים).** (Would-keep-using — *qualitative reason only*, never a yes/no count or %).
- **‏ציטוט נבחר (פראפרזה, אנונימי, ללא מספרים).** (Selected paraphrased quote about discipline/process — number-free, identity-stripped.)

**Hard rule (DEC-004):** if a tester volunteers a number (%, $, "made me X", win rate), the synthesis records the *qualitative* sentiment and **drops the number** — it is never transcribed, aggregated, or carried into the Sprint-12 handoff. Until Sprint 12: zero numbers anywhere. The consent-ledger and this synthesis travel together as **structure + qualitative themes only**.

---

## 4. Week-3 success metric & go/no-go for Ring-2 expansion

**Success metric (qualitative, no public numbers — DEC-004):** W3 is the first *inbound* week. Success = **Sprint-13 deploy stability confirmed for the onboarding window (or onboarding deliberately timed around deploys); Hyperscaler invited-user onboarding confirmed LIVE/no-billing; the first Ring-1 acceptees onboarded via the invited path with consent state recorded; Ring-2 invites sent 1:1 only to screened candidates; Pulse #1 run and synthesized into the §3 number-free template; the first ALLOWED process/demo asset drafts (state-machine screenshots + drawdown explainer) started and re-passed the DO-NOT-PUBLISH self-check; early friction logged and routed.** No tester counts, conversion rates, NPS, or any public figure — by design. "Done" is process completeness and DEC-compliance, not volume.

**Go / no-go signal for Ring-2 expansion (qualitative gate):**
- **GO** to send/continue Ring-2 (W3.5) **iff**: (a) the invited-user onboarding path works end-to-end for the first real Ring-1 tester (W3.2/W3.3 green), AND (b) Sprint-13 deploy stability is confirmed for the onboarding window (W3.1 green), AND (c) Pulse #1 surfaces no *blocking* onboarding/RTL defect that would give Ring-2 a broken first impression, AND (d) consent capture works and legal sign-off is still valid (W3.4 / V1 §6 item 4).
- **NO-GO / HOLD** Ring-2 if onboarding is not live, a deploy can dead-bot a tester mid-onboard, or a blocking clarity/RTL defect is open — fix-and-route first (W3.8), expand after. Holding Ring-2 is the *correct* DEC-aligned action (quality/consent over volume, V1 §2); it is logged, not treated as failure.

---

*End of Sprint-13 Week-3 sheet. Continues `MARKETING_SPRINT12_WEEK2.md`; derived from `MARKETING_V1.md` §5 row W3; constrained by DEC-20260515-001..009, `MARK_SPRINT12_RULINGS.md`, and the `SPRINT13_PLAN.md` deploy-stability finding. Any reintroduction of numbers, pricing, English, "AI", or Minervini-as-brand requires a new entry in `docs/DECISIONS.md`. Documentation only — no code, no commit.*
