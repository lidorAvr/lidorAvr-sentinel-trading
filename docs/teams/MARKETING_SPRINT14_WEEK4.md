# Marketing — Sprint 14, Week 4 Execution (Closed Beta — Ring-3 / Pulse #2 / Friction Triage / Redacted-PDF Asset)

> **Document type:** week-4 execution sheet (derived from `docs/teams/MARKETING_V1.md` §5 calendar, row **W4**)
> **Status:** active — Sprint 14, week 4 of the 6-week closed-beta plan
> **Owner:** Marketing Team
> **Branch:** `claude/review-system-audit-FBZ2h`
> **Continues from:** `docs/teams/MARKETING_SPRINT13_WEEK3.md` (W3 = first onboard + Ring-2 + Pulse #1 — deltas only noted below)
> **Binding decisions:** DEC-20260515-001 (Minervini = acknowledgment only) · -002 (single `minervini_strict`) · -003 (Israel/Hebrew-only) · -004 (process/demo only, NO numbers / PnL / backtest) · -005 (closed free beta; testers get 1yr Pro) · -006/-007/-008 (process-hook features, Mark-ruled) · -009 (rate-limit unchanged) · -010 (manual `deploy.sh`; no auto-watcher)
> **Scope:** documentation only. No code, no Supabase, no git commit/push. Independent of Mark/Architecture/Infra/Hyperscaler Sprint-14 execution — dependencies noted, not owned.
> **Working principle:** honesty over hype; no "AI"; no investment advice; no fabricated numbers (`AGENTS.md` / `CLAUDE.md`).

---

## 0. Continuity from Week 3 — what changed

W3 (first inbound) closed: deploy stability confirmed for the onboarding window, Hyperscaler invited-user onboarding confirmed LIVE/no-billing, first Ring-1 acceptees onboarded via the invited path with consent state recorded, Ring-2 invites sent 1:1 to screened candidates, Pulse #1 run and synthesized into the §3 number-free template, the first ALLOWED process/demo asset drafts (state-machine screenshots + drawdown explainer) started and re-passed the DO-NOT-PUBLISH self-check, early friction logged and routed.

**New since W3 — the dominant W4 fact:** Sprint 14 is a **HIGH-severity alert-spam remediation sprint** (`SPRINT14_PLAN.md`): the founder's live Telegram showed ~7 near-identical PWR pushes in ~2.5h on an unchanged healthy position, ALGO observer-only push-spam (HOOD), and a giveback dedup failing despite a 6h cooldown — while a genuine P0 (`CAT 22:33` critical exit, price < stop) had to stay buried under noise. Root-cause suspect: anti-spam memory (`risk_monitor_state.json`) not surviving monitor cycles / deploys. This is being fixed in Wave 2, Mark-gated (`MARK_SPRINT14_RULINGS.md`).

**Marketing consequence (the W4 spine):** V1 §5 row W4 is **Ring-3 invites if capacity + Pulse #2 + friction triage + redacted sample-PDF artifact**. The "if capacity" clause is now hard-gated: **a tester being alert-spammed is the single worst possible beta experience and would destroy trust irreversibly.** Therefore *widening the Ring* (Ring-3, and any further Ring-2 onboarding) is **BLOCKED until the Sprint-14 alert-spam fix is deployed AND verified**. Marketing does **not** own, design, or block the fix — but the go/no-go gate is non-negotiable and stated explicitly in §1 and §4. Pulse #2, friction triage, and the redacted-PDF artifact proceed with the *already-onboarded* cohort regardless (they do not widen exposure).

---

## 1. Week-4 execution checklist (V1 §5 row W4)

All copy is number-free (DEC-004), Minervini-name-clean (DEC-001), Hebrew-first (DEC-003), no-billing (DEC-005). `[OWNER]` = placeholder; Marketing writes no code.

| # | Task | Owner | Depends on | Done-when |
|---|---|---|---|---|
| W4.1 | **HARD GO/NO-GO GATE — alert-spam fix deployed & verified before any Ring widening.** Obtain written confirmation that the Sprint-14 alert-spam remediation (`SPRINT14_PLAN.md`, Mark-gated by `MARK_SPRINT14_RULINGS.md`) is (a) merged, (b) deployed via the manual `deploy.sh` path (DEC-010), and (c) verified: anti-spam memory survives a monitor cycle AND a deploy, healthy held positions no longer push-spam, ALGO observer-only push policy applied, giveback dedup effective — AND the "must STILL fire" P0 cases (price<stop / →Broken / critical-exit, e.g. `CAT 22:33`) are confirmed preserved. Marketing does **not** own/block the fix; this is an informational hard gate for *whether* to widen. | Mktg `[OWNER]` ↔ Mark / Architecture-Infra `[OWNER]` | Sprint-14 Wave 2 build + consolidation; `MARK_SPRINT14_RULINGS.md`; `SPRINT14_DESIGN.md` | Written "alert-spam fix deployed + verified, P0 still fires" confirmation logged in friction log — OR explicitly recorded as NOT yet green (→ W4.2 holds) |
| W4.2 | **Ring-3 invites — HELD until W4.1 is green** (V1 §5 W4 "if capacity"; V1 §2 target up to ~3). When W4.1 is green AND onboarding stable for ~10 users: send §2.1 verbatim, 1:1 only, to §2.2-screened Ring-3 candidates. While W4.1 is red: **HOLD** — do not send; holding is the correct DEC-aligned action (quality/consent over volume, V1 §2), logged, not a failure. | Founder `[OWNER]` | **W4.1 GREEN (hard gate)**; Hyperscaler onboarding stable ~10 users; §2.2-screened Ring-3 list | Ring-3 invites sent 1:1 *only after* W4.1 green — OR documented HOLD with reason (alert-spam fix not yet verified) |
| W4.3 | **Pulse #2** with the *already-onboarded* cohort (W3.6 ≤5-Q template, Hebrew/RTL, number-free). Proceeds regardless of W4.1 — does not widen exposure. **Add the alert-volume/signal-quality probe** (see §3) so testers' lived experience of the spam is captured qualitatively while the fix lands. | Mktg `[OWNER]` | W3.6 template; W3.3 onboarded testers | Pulse #2 sent to all onboarded testers; responses synthesized into §3 (incl. the alert-volume theme) |
| W4.4 | **Triage friction log → route to owning team.** Consolidate W3 + W4 friction one-row-per-issue → UX / Hyperscaler / Backend. Explicitly cross-reference any tester-reported alert-noise to the Sprint-14 remediation (route → Backend/Mark track) so Marketing's qualitative signal corroborates the engineering finding — without Marketing owning the fix. | Mktg `[OWNER]` + UX `[OWNER]` | W3.8 log; W4.3 Pulse #2; `SPRINT14_PLAN.md` | Log triaged; every item routed; alert-noise items cross-linked to the Sprint-14 track |
| W4.5 | **Build the redacted sample-PDF layout artifact** (V1 §3 / §5 W4): anonymized weekly-report *layout only*, every figure replaced by neutral placeholders ("—" / "XX"). Sells format/rigor, never results. Draft only; not published this week. | Mktg lead `[OWNER]` | W3.7 asset set; report layout reference | Redacted-PDF layout draft exists, zero %/$/curve/PnL, all figures neutral placeholders |
| W4.6 | **Verify every asset against the DO-NOT-PUBLISH list** (V1 §3 / §5 W4): W3.7 state-machine screenshots + drawdown explainer AND the new W4.5 redacted-PDF layout. No %, no $, no backtest, no founder PnL, no "AI", no Minervini-as-brand, no price/tiers. | Mktg lead `[OWNER]` | W3.7, W4.5 | Self-check passed on all assets; sign-off line in friction log |
| W4.7 | **Re-confirm consent + legal status still valid** for the DEC-004 dataset (V1 §6 item 4; W3.4 carryover). Any Legal retraction *holds dataset reliance*, not testing. Record consent state for any tester onboarded since W3 (none expected while W4.2 holds). | Mktg `[OWNER]` + Founder `[OWNER]` | W3.4; Legal status | Legal/consent status re-confirmed and logged (ledger structure only, zero numbers) |

**Cross-team dependency summary (Marketing owns none):**
- **Mark / Architecture / Infra — Sprint-14 alert-spam remediation (NEW, HARD-gates W4.1 → W4.2 Ring widening).** `SPRINT14_PLAN.md` HIGH-severity; Mark-gated by `MARK_SPRINT14_RULINGS.md`; designed in `SPRINT14_DESIGN.md`. Marketing only needs the written "deployed + verified + P0 still fires" confirmation. Marketing does not own, design, or block the fix.
- **Infra/Deploy — `deploy.sh` manual path (DEC-010).** The fix must reach the Pi via the supported manual `deploy.sh` (no auto-watcher); Marketing confirms *deployed*, not *how*.
- **Hyperscaler — invited-user onboarding stable for ~10 users** (V1 §5 W4 "Depends on"); no signup / no billing (DEC-005). Required before W4.2 even if W4.1 is green.
- **UX — Telegram clarity improvements landing** (V1 §5 W4 "Depends on"); feeds W4.4 routing and W3.7/W4.5 asset accuracy.
- **Legal — consent-form sign-off must remain valid** (W3.4 / V1 §6 item 4); retraction holds W4.7 dataset reliance, not testing.

---

## 2. Beta-recruitment artifacts (copy-ready, Hebrew RTL) — deltas only

> All four carried **verbatim from `MARKETING_SPRINT13_WEEK3.md` §2 / `MARKETING_SPRINT12_WEEK2.md` §2 / `MARKETING_V1.md` §2**. No new numbers, no price, no Minervini name, no emojis, RTL-clean. Deltas vs Week 3 explicitly flagged; "NONE" = byte-identical, frozen.

### 2.1 Invite message (short) — reused verbatim for Ring-3 in W4.2 (when unblocked)
> **Delta vs Week 3: NONE.** Identical text, frozen since W1.4. W4 reuses the *same* verbatim message for Ring-3 (V1 §2: one invite message for all rings). No edit — any future change needs a logged reason. (Text: `MARKETING_SPRINT12_WEEK2.md` §2.1.)

### 2.2 Screening checklist
> **Delta vs Week 3: NONE.** Same six criteria (`MARKETING_SPRINT12_WEEK2.md` §2.2). Applied operationally per **Ring-3** recipient before each W4.2 send (same bar as Ring-1/2; quality/consent over volume, V1 §2). Note: the §2.2 bar is *necessary but not sufficient* in W4 — the W4.1 hard gate sits above it.

### 2.3 Consent blurb — Sprint-12 dataset (DEC-004)
> **Delta vs Week 3: NONE in text.** Same legally-gated blurb (`MARKETING_SPRINT12_WEEK2.md` §2.3). **Status note:** unchanged from W3 — legal OK must remain valid for the dataset to count (W4.7 re-confirms; if Legal retracts, testing continues but DEC-004 dataset reliance is held — V1 §6 item 4). No new commitment.

### 2.4 "1 year free Pro at launch" framing (DEC-005, exact)
> **Delta vs Week 3: NONE.** Exact V1/W2/W3 reward string, unchanged. Loyalty thank-you for early shaping, never a discount or sales close; **no price ever stated** (no pricing model pre-Phase D, DEC-005).

*(No new recruitment artifact in W4. The W4.5 redacted sample-PDF layout is NOT a recruitment artifact — it is DEC-004 trust-rail material, drafted not published this week, same handling as the W3.7 assets.)*

---

## 3. Feedback-synthesis update (Hebrew, qualitative — feeds the Sprint-12 dataset)

> Same internal synthesis sheet as W3 §3 (`MARKETING_SPRINT13_WEEK3.md` §3). **Delta vs Week 3:** the per-pulse synthesis block is **carried verbatim** with **one added qualitative theme** for Pulse #2 (W4.3), reflecting the live alert-spam reality. Still **strictly qualitative — NO numbers** of any kind: no counts, no scores, no %, no $, no "X of Y said" (DEC-004). Quotes paraphrased/anonymized; never attach raw PnL or identifiable detail (DEC-004 / consent blurb §2.3).

**Per-pulse synthesis (verbatim from W3 §3 — themes in words, prose only, no metric tables):**

- **‏מה גרם הכי הרבה חיכוך?** (Biggest friction) — themes in words; route each to an owning team (UX / Hyperscaler / Backend) in the friction log — *that routing is the only "tally", and it stays internal*.
- **‏רגע אחד שבו הבוט עזר למשמעת.** (One moment it helped) — describe the *process* moment, never an outcome ("עזר לי להרוויח" → strip/reject per §4 DO-NOT-SAY).
- **‏רגע אחד שבו טעה / בלבל.** (One moment wrong/confusing) — the discipline mechanic that misfired or read unclearly.
- **‏בעיות RTL / בהירות בעברית.** (RTL / Hebrew clarity) — exact phrasing/layout issues, verbatim Hebrew snippets. Direct UX input.
- **‏האם תמשיך להשתמש? — ולמה (במילים).** (Would-keep-using — *qualitative reason only*, never a yes/no count or %).
- **‏ציטוט נבחר (פראפרזה, אנונימי, ללא מספרים).** (Selected paraphrased quote about discipline/process — number-free, identity-stripped.)

**ADDED THEME (W4 delta — Pulse #2, qualitative, NO numbers — DEC-004):**

- **‏עומס התראות / איכות האות.** (**Alert volume / signal quality** — explicit theme to probe with the current onboarded cohort.) In words only: did the bot ever feel *noisy* — repeated pushes on a position that did not change? Did real, important alerts feel *hard to find* under that noise? Could the tester *trust* that a push meant "something genuinely needs you"? Capture sentiment in prose (e.g. "הרגיש שהבוט חוזר על עצמו על פוזיציה שלא זזה", "פחדתי לפספס את ההתראה החשובה כי היו יותר מדי"). **Hard rule (DEC-004):** if a tester volunteers a number ("7 times", "every 5 min", "made me X%"), record the *qualitative* sentiment ("felt repetitive / buried the important one") and **drop the number** — never transcribed, aggregated, or carried to the Sprint-12 handoff. This theme is *also* internal corroboration for the Sprint-14 engineering finding (`SPRINT14_PLAN.md`) and is cross-linked in the friction log (W4.4) → routed to the Backend/Mark track; Marketing does not own the fix.

**Why this theme now:** the alert-spam issue is live and HIGH-severity *this sprint*. Probing it qualitatively (a) gives the founder honest tester-side evidence of impact and of fix effectiveness once deployed, (b) keeps Marketing's signal aligned with the engineering remediation, and (c) stays fully DEC-004-compliant — sentiment, never counts. Until Sprint 12: zero numbers anywhere. Consent-ledger + this synthesis travel together as **structure + qualitative themes only**.

---

## 4. Week-4 success metric & go/no-go for Ring-2/3 expansion

**Success metric (qualitative, no public numbers — DEC-004):** W4 success = **the alert-spam-fix go/no-go gate (W4.1) is explicitly evaluated and its state logged; Ring-3 sent ONLY if that gate is green (else a documented HOLD); Pulse #2 run with the already-onboarded cohort and synthesized into the §3 template including the new alert-volume/signal-quality theme; the friction log triaged and routed with alert-noise items cross-linked to the Sprint-14 track; the redacted sample-PDF layout drafted and, with the W3.7 assets, re-passed the DO-NOT-PUBLISH self-check; consent/legal status re-confirmed valid.** No tester counts, conversion rates, NPS, or any public figure — by design. "Done" is process completeness, DEC-compliance, and *correctly holding the Ring when the gate is red* — not volume.

**Hard go / no-go for Ring-2/3 expansion (the controlling gate this week):**
- **GO** to send Ring-3 / onboard any further testers **iff ALL of:**
  - (a) **Alert-spam fix DEPLOYED & VERIFIED** (W4.1): merged, deployed via `deploy.sh` (DEC-010), and confirmed — anti-spam memory survives cycles + deploys, healthy held positions no longer push-spam, ALGO observer push policy applied, giveback dedup effective, **and every "must STILL fire" P0 case (price<stop / →Broken / critical-exit, e.g. `CAT 22:33`) preserved** (`SPRINT14_PLAN.md` / `MARK_SPRINT14_RULINGS.md`); **AND**
  - (b) **Deploy stable** for the onboarding window — Hyperscaler invited-user onboarding stable for ~10 users, no `--build` deploy mid-onboard dead-botting a tester (V1 §5 W4; DEC-010 manual path); **AND**
  - (c) **Valid consent** — legal sign-off still valid and consent capture working (W4.7 / V1 §6 item 4); **AND**
  - (d) Pulse #2 surfaces no *blocking* onboarding/RTL defect that would give a new tester a broken first impression.
- **NO-GO / HOLD** Ring-3 and any further onboarding if the alert-spam fix is **not yet deployed-and-verified**, OR a deploy can dead-bot a tester mid-onboard, OR consent/legal is invalid, OR a blocking clarity/RTL defect is open. **Onboarding a new tester into a known alert-spam bug would destroy the closed beta** — this is a hard, non-negotiable stop. Holding is the *correct* DEC-aligned action (quality/consent over volume, V1 §2); it is logged, not treated as failure. Pulse #2, friction triage, and the redacted-PDF artifact (the non-widening W4 work) proceed regardless.

---

*End of Sprint-14 Week-4 sheet. Continues `MARKETING_SPRINT13_WEEK3.md`; derived from `MARKETING_V1.md` §5 row W4; constrained by DEC-20260515-001..010, `MARK_SPRINT14_RULINGS.md`, and the `SPRINT14_PLAN.md` HIGH-severity alert-spam remediation. Widening the Ring is hard-gated on the alert-spam fix being deployed AND verified — testers must not be spammed. Any reintroduction of numbers, pricing, English, "AI", or Minervini-as-brand requires a new entry in `docs/DECISIONS.md`. Documentation only — no code, no commit.*
