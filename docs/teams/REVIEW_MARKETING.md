# Review — Marketing / Go-To-Market State

> **Document type:** system-review section (Marketing team lead)
> **Status:** review — founder-readable GTM snapshot
> **Owner:** Marketing Team
> **Branch:** `claude/review-system-audit-FBZ2h`
> **Sources:** `MARKETING_V1.md`, `MARKETING_SPRINT10_WEEK1` / `SPRINT12_WEEK2` / `SPRINT13_WEEK3` / `SPRINT14_WEEK4`, `docs/DECISIONS.md` DEC-20260515-001..010
> **Scope:** documentation only. No code, no commit. Marketing owns no engineering fix; cross-team items are flagged, not owned.

---

## 1. Binding GTM decisions (the rails — all of Q1 sits inside these)

| DEC | One-liner |
|---|---|
| **001** | Minervini = acknowledgment / fair-use only. Never a hero line, brand, endorsement, or logo. |
| **002** | One method only: `minervini_strict`. Sold as "one validated method", not configurability. |
| **003** | Israel-only, Hebrew-first. English/i18n deferred ~Q3. No translation work now. |
| **004** | Process/demo only. **No %, no PnL, no $, no synthetic backtest.** Real numbers only from a Sprint-12 consented dataset, only after legal clears. |
| **005** | Closed **free** beta (founder-selected). No billing, no pricing, no paid acquisition in Q1. Testers get 1 year Pro free at launch. |
| **006** | ALGO in Open Tasks = one consolidated, explicitly non-binding "observed" read-out. Never a task/stat. |
| **007** | RUNNER task suppressed when the stop already meets the engine suggestion (no no-op noise). |
| **008** | Audit trail exposed to the **user** as a read-only retrospective self-review surface. |
| **009** | Telegram rate-limit unchanged (8 msgs / 60s) — the guardrail stays. |
| **010** | Deploy = manual operator-run `deploy.sh`. No auto-watcher; Telegram deploy button is a no-op. |

DEC-006/007/008 are the DEC-004-safe **process/discipline demo hooks** (see §3).

## 2. Where the closed beta actually is

Six-week plan; four weeks documented. Status is per the execution sheets — **week-completion claims are plan-asserted, not independently verified by Marketing** (Marketing owns no code/deploy).

| Week | State | Outcome (as documented) |
|---|---|---|
| **W1 (Sprint 10)** | Prep / list-building | Positioning + disclaimer frozen; consent draft built (pending legal); invite + screening locked; Rings 1–3 candidate list screened, private; friction log open. No sends. |
| **W2 (Sprint 12)** | First outbound | Ring-1 invites sent 1:1 to screened candidates; private feedback channel + ≤5-Q pulse template stood up; consent-state ledger live (zero numbers). |
| **W3 (Sprint 13)** | First inbound | First Ring-1 acceptees onboarded; Ring-2 invites sent; Pulse #1 run and synthesized (qualitative only); first allowed process/demo asset drafts started. |
| **W4 (Sprint 14)** | Hold / consolidate | Pulse #2 + friction triage + redacted-PDF draft proceed with the **already-onboarded** cohort only. **Ring widening BLOCKED.** |
| W5–W6 | Not yet documented | Planned: reach 10–15 testers, ≥5 consented, retro + Sprint-12 handoff. Unverifiable at review time. |

**Currently BLOCKED:**
- **Ring-3 and any further onboarding (hard gate, W4.1):** blocked until the Sprint-14 **alert-spam fix is deployed via `deploy.sh` AND verified live** (anti-spam memory survives cycles + deploys; healthy positions stop push-spamming; P0 cases like `CAT 22:33` critical-exit **still fire**). Onboarding a new tester into a known alert-spam bug would destroy the beta. Holding is the correct, logged action — not a failure.
- **DEC-004 dataset reliance:** gated on **Legal sign-off of the plain-Hebrew consent form** (V1 §6 item 4) staying valid. If retracted, testing continues but no consented data counts.
- **Deploy stability:** an ongoing cross-team dependency for safe onboarding timing (manual `deploy.sh`, DEC-010; no `--build` mid-onboard).

## 3. The honest "we cannot say" list

Until a **Sprint-12 consented dataset exists AND legal clears it**, GTM may NOT publish or claim, anywhere:
- Any percentage — win rate, return, drawdown, expectancy.
- Any monetary figure — NAV, PnL, R in $, account size.
- Any synthetic/backtest output or simulated equity curve.
- The founder's personal trading results, anonymized or not, pre-counsel.
- The word "AI" (it is a rules + statistics engine), or Minervini as a brand/endorsement.
- Testimonials that quote numbers (strip or reject).

**Allowed to demo now (process/discipline only, mechanic-never-outcome):** state-machine transition screenshots with the Hebrew alert per transition; a qualitative "how it cuts drawdown" explainer (no curve/%/$); sample/illustrative alert messages; a redacted sample-PDF layout (figures → "—"/"XX"); engineering-ethos content (no silent failures, explicit stale/fallback labelling); and the DEC-006/007/008 discipline hooks (Open Tasks, batch stop promotion, ratchet-up stop guard, RUNNER no-op suppression, `🧾 הפעולות שלי` self-review) — as **1:1 recruiting talking points**, not yet published assets.

## 4. The single most important open item / founder decision pending

**Legal counsel sign-off — the consent form (near-term) and the future-numbers / ISA posture (downstream).** It is the one item gating everything that gives Sentinel credibility with evidence: without a valid signed consent the entire DEC-004 Sprint-12 dataset is unusable, and no number ever ships until an Israeli securities lawyer (a) approves anonymized aggregate beta metrics and (b) gives the ISA classification for the eventual *paid* sizing-alert tool. The free no-billing beta defers urgency but does not remove this. **Owner: Legal + Founder.** Secondary, non-blocking: brand/domain (`.co.il`) and founder-as-public-face.

---

*End of Marketing review section. Derived from `MARKETING_V1.md`, the four weekly execution sheets, and DEC-20260515-001..010. Week-completion states are plan-asserted (Marketing owns no code/deploy) and flagged where unverifiable. Documentation only — no code, no commit.*
