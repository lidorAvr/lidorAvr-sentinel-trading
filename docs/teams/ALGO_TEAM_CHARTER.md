# ALGO Team — Charter, Roster, Doctrine & Requirements Backlog

**Formed:** 2026-05-18 (DEC-20260518-001, founder). **Status:** chartered; DOC-ONLY on formation — every requirement is investigate-first + founder-gated governed Phase. NO code executed by forming the team.

> Source of doctrine: the founder/Mark personal portfolio memo (2026-05-18) + `DEC-20260511-001` (#8 ALGO observer) + `AGENTS.md` + `CLAUDE.md`. The founder noted a formal "ALGO rules" file will be expanded with more data later — **DEPENDENCY: this charter is grounded in the memo + repo as-built; when the formal ALGO rules doc arrives it supersedes/extends §Doctrine and the team re-baselines.** (Accuracy over confidence: where doctrine here is inferred from the memo it is marked ⟨memo⟩.)

## 1. Mission & inviolable boundary
Own the ALGO domain end-to-end: trust, segregation, risk-gating, probation/kill-switch policy, data-honesty for ALGO. **Inviolable:** ALGO is **observe-only** — Sentinel NEVER issues manual ALGO entries/exits (DEC-20260511-001 #8; AGENTS.md). ALGO work = *gating, alerting, disclosure, segregation, trust scoring* — never automated order management. WS-C / `-1`-sentinel stay **DEFERRED** unless the founder explicitly reclassifies. Every ALGO change is a governed, Mark-gated Phase with a named byte-identical/behavior proof; byte-locked paths (engine_core/analytics/period_data_probe/LOCKED April + baselines) only via their governed ritual.

## 2. Roster (the members we were missing)
| Member | Responsibility | Authority / interface |
|---|---|---|
| **ALGO Lead** | Owns ALGO doctrine + this charter; final ALGO-domain sign-off before any ALGO Phase | Reports to founder via Mark; gates ALGO scope with Mark + parent |
| **ALGO Risk & Kill-Switch Officer** | The probation state machine: `No-Add` / `No-Re-entry-Boost` / `Algo-Probation` / `Kill-Switch @ 0.50R-` / `Algo Risk Breach Review` alert; per-symbol watch (HOOD/PLTR today) | Defines thresholds; observe-only (alerts/gates, never exits) |
| **ALGO Data-Integrity / Reconciliation Analyst** | Broker-reconciliation correctness + the gate "Critical Data Gap ⇒ NO risk-raise even if all green"; the $510.51-vs-$190.29 inconsistency | Owns the data-cleanliness gate; works with Data team |
| **ALGO Stats / Trust-Score Quant** | Per-engine Trust Score (WR, Expectancy, Payoff, PF, MaxDD, loss-streak, data-quality, target-risk adherence, broker-gap, sample-size); the 4-gate risk-raise model; L50 sample-honesty | Owns scoring math; works with Engine team |
| **ALGO Segregation & Reporting Engineer** | Strict manual/ALGO separation across dashboard+reports (EP-manual / VCP-manual / ALGO / Combined — decisions never mixed); decision-card-per-position surface | Works with UX + Data; presentation-first |
| **ALGO QA / Methodology Conformance** | Verifies every ALGO Phase vs Mark's doctrine + the governed/byte-lock model + Sprint-22/23/24 invariants; the named-proof discipline | Veto on any Phase lacking a Ruling-3 proof |

## 3. Doctrine (captured from the 2026-05-18 memo — ⟨memo⟩)
- ⟨memo⟩ ALGO decisions are **supervision** decisions, never "sell/hold": is the algo still trusted, may it add, is a Kill-Switch needed.
- ⟨memo⟩ Per-symbol probation: `No Add`, `No Re-entry Boost`, `Algo Under Watch`; **Kill-Switch trigger = 0.50R- accounting** OR a fresh same-symbol trade right after a losing exit without clear structural improvement ⇒ temporary freeze for review (HOOD); PLTR = stricter watch + `Algo Risk Breach Review` at 0.50R- (~$23.8 vs $47.53 risk target).
- ⟨memo⟩ **Risk-raise gate:** do NOT raise risk (0.60%→0.85% rejected) while ANY of: broker-reconciliation mismatch, historically-negative ALGO cluster, ≥1 ALGO position `Broken`, or report data inconsistency. "Clean truth before aggressiveness."
- ⟨memo⟩ ALGO must be a **separate cluster with its own stats** — never mixed into manual success (ALGO hist: 47 campaigns, −$612.16, ≈ −0.27R/trade ⇒ low-medium trust until proven).
- ⟨memo⟩ Sample honesty: never display "L50" with <50 trades — show "L50 unavailable — sample too small" / "Current sample: N/50".

## 4. Requirements backlog (derived from the memo — investigate-first, founder-gated, NONE executed)
| ID | Requirement | Class | Money? | Prior-art / risk |
|---|---|---|---|---|
| R-ALGO-1 | Broker-reconciliation gate: Critical Data Gap ⇒ block risk-raise | closure-fix (behavior) | YES | new risk-gate; HIGH; founder-gated |
| R-ALGO-2 | Fix broker-recon inconsistency ($510.51 master vs $190.29 חדר-מצב) | bug-fix | YES (truth) | reproduce-first; likely real |
| R-ALGO-3 | L50 sample-honesty (<50 ⇒ "unavailable / N/50") | honesty-fix (presentation) | no | CLAUDE.md #1 / B1 class; LOW-risk |
| R-ALGO-4 | Strict manual/ALGO separation in dashboard+reports (4 tables) | feature/restructure | no | founder-gated; UX+Data |
| R-ALGO-5 | Per-engine Trust Score | addition | no | founder-gated; design-heavy |
| R-ALGO-6 | 4-gate risk-raise (replace Heat-only) | behavior change | YES | HIGH; money-affecting; founder-gated |
| R-ALGO-7 | Decision-card per position (Runner+EventRisk / Probation / …) | feature | no | founder-gated; UX |
| R-ALGO-8 | ALGO probation/kill-switch state machine + Risk-Breach-Review alert | behavior (observe-only) | YES (gates/alerts) | HIGH; founder-gated; NO manual exits |

## 5. First mandate (DOC-ONLY investigation — already dispatched)
Verify against live source (no code): R-ALGO-2 (reproduce the two-number broker-recon inconsistency + locate root), R-ALGO-3 (confirm the L50-with-N<50 false-confidence display path), and the ALGO-segregation/-$612.16 trust reality — then produce a **tiered Mark-gated scope menu** for the founder to choose from (same governed model as Sprint-24/25/27). Output: `docs/teams/ALGO_INVESTIGATION_1.md` + a CEO-facing tiered menu. **No code until the founder picks scope.**
