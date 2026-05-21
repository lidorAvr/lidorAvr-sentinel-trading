# Meeting (21/05/2026) — Team-Leads Consolidation: F-YTD + /portfolio UX Cleanup retroactive review

**Date:** 2026-05-21 · **Branch:** `claude/review-system-audit-FBZ2h` · **Mode:** DOC-ONLY review (no code touched, no tests added/changed).
**Scope:** the three just-landed commits responding to the founder's 21/05/2026 ~03:30 complaint ("מבלבל וארוך") + the prior F-YTD wave:

| Commit | Subject |
|---|---|
| `3ac93e8` | F-YTD data contract documented + `pre_db_realized_pnl_estimate` disclaimer flows through reconciliation classifier |
| `fdd4e84` | CLI helper to set/show/clear `pre_db_realized_pnl_estimate` |
| `e9872f8` | UX cleanup: recon line no longer contradicts itself; adaptive block compact when 4-gate clamped to hold |

**Per-discipline findings** (all DOC-ONLY, parent-verified, on branch HEAD `dd28168`):
- `MEETING_UX_ARCH_FINDINGS.md` — P1×2, P2×3, P3×3, P0=0
- `MEETING_UX_DATA_FINDINGS.md` — P1×1, P2×3, P3×3, P0=0
- `MEETING_UX_ENGINE_FINDINGS.md` — P1×1, P2×4, P3×4, P0=0
- `MEETING_UX_MARK_FINDINGS.md` — §A/§B/§C/§E PASS · §D REQUIRES_FOLLOWUP · 3 new §X rulings proposed
- `MEETING_UX_OPS_FINDINGS.md` — MEDIUM×2, LOW×4, P0/P1=0
- `MEETING_UX_SECURITY_FINDINGS.md` — P2×2, P3×3, P0/P1=0 — **APPROVE**
- `MEETING_UX_TELEGRAM_FINDINGS.md` — P1×2, P2×3, P3×1, 6 PRESERVED invariants
- `MEETING_UX_TESTING_FINDINGS.md` — P1×3, P2×4, 3 OOS flags

## The headline finding (4 teams converged)

**The cleanup landed surgically on `/portfolio` only — ~3 sibling surfaces still emit the pre-cleanup verbose shape, and a corruption-free disclaimer can softly drift into the same "fallback-as-truth" failure mode Sprint-25 just closed.** The math/honesty layer is sound (defensive `min(|raw|,|adjusted|)` clamp prevents escalation; Mark §3 verbatim preserved on Critical-residual; CLAUDE.md #1 intact). What was *not* held to the same bar is the *propagation*: `pre_db_realized_pnl_estimate` is read ad-hoc in 5 places without a single-source helper, the disclaimer reaches `G1` gate through a band-string indirection that has no end-to-end pin, the inline `risk_monitor.py:1242` alert bypasses `fmt_adaptive_risk_block` (so the 14-line shape will recur on any future direction-change rec), and `docs/DATA_CONTRACTS.md` carries a sign-convention example that, *taken literally*, would worsen the gap (the founder happened to use the opposite sign and got the right result).

## Cross-team convergence

### Theme A — sibling-surface coverage gap (ARCH F1+F2 · DATA F1 · ENGINE F1 · UX U1) → 5×P1
The F-YTD disclaimer + the cleanup were scoped to `/portfolio` only:
- **ARCH F1 (P1)** — `pre_db_realized_pnl_estimate` read in 5 places via ad-hoc `account_settings.get(..., 0) or 0`; no single-source helper. This is the **exact** divergence pattern Sprint-25 ARCH F1 flagged on a brand-new field.
- **ARCH F2 (P1)** — `report_scheduler._compute_risk_rec` duplicates `build_risk_raise_gate_ctx` logic; the disclaimer-aware G1 is in only one of them.
- **DATA F1 (P1)** — `docs/DATA_CONTRACTS.md` sign-convention example contradicts the code path the founder actually used. Doc is wrong, not the code — but the next operator will be misled.
- **ENGINE F1 (P1)** — disclaimer → G1 (Clean Data) gate chain is *not* pinned end-to-end. The classifier emits an updated band string; G1 reads that band string. No integration test asserts the chain.
- **UX U1 (P1)** — `risk_monitor.py:1242,1270-1305` builds the adaptive-risk alert text *inline*, bypassing the cleaned-up `fmt_adaptive_risk_block`. The 14-line verbose shape **will recur** on the next direction-change recommendation.

### Theme B — tests pin shape, not invariants (TESTING T1+T2+T3) → 3×P1
Three claims the test files *imply* but never verify:
- **T1 (P1)** — over-shoot disclaimer (`gap=+495.67, estimate=600`) → `band="Material Gap"`, `adjusted_gap=-104.33`. Softened-branch renders ✅ next to "פער מהותי" with a *negative* residual. Untested.
- **T2 (P1)** — empty `heat_factors=[]` + gate-clamped → 3-line block with **no ⛔ reason** (`telegram_formatters.py:414-417` iterates an empty list silently). Directly contradicts `test_meeting_ux_cleanup.py:163`'s pinned invariant.
- **T3 (P1)** — non-numeric `pre_db_realized_pnl_estimate="abc"` in `sentinel_config.json` raises `ValueError` at every of the 4 caller `float(... or 0)` sites. No failsafe.

### Theme C — user-visible label lie (UX U4) → 1×P1
**U4 (P1)** — `telegram_audit_review.py:41-46` lists only `ACTION_RISK_PCT_CHANGE`; risk-raise rejections are logged to `risk_journal.json` (via `log_risk_journal`), never to `audit_log`. Result: after the user dismissed 0.85% twice (msgs 18837, 18896), the next `הפעולות שלי` view (msg 18964) said "אין פעולות מתועדות עדיין" — *the surface contradicts its own label.*

### Theme D — Sprint-25 closure echoes (OPS F2 · SECURITY S-1) → ops/security
Latent items not introduced by this wave but visible in the chat log:
- **OPS F2 (MEDIUM)** — `sentinel-bot` restart-loop: `LOOP_INTERVAL_SEC=900` vs `docker-compose.yml:27` 1980s healthcheck staleness ratio yields a tight loop. The 6+ "Sentinel Bot מחובר" reconnects between 18-21/05 are a symptom of autoheal masking the loop.
- **SECURITY S-1 (P2)** — dev-PIN anti-bruteforce window is too narrow (5 min in-memory). Chat-log shows the PIN value rotated between the 19/05 23:27 session (PIN "1945" worked) and 21/05 01:30 (PIN "1945" failed, "4915" worked) — rotation is intentional ops hygiene, but the anti-bruteforce lockout doesn't span sessions.

### Theme E — chat-log incidentals (engine surface + UX friction)
- **ENGINE F5 (P2)** — MRVL `evaluate_position_engine` `missing_data` (msg 18819 at 2026-05-19 13:12) traces to a bare `except` at `engine_core.py:88` that swallows yfinance errors. One-cycle skip, not deep fragility — but ops visibility is poor.
- **ENGINE F6 (P2)** — Win Rate jumped 56% → 67% between 19/05 23:30 and 21/05 01:40, caused by one trade re-bucketed by a stat_bucket sweep after backlog completion. Behavior matches AGENTS #8 but is knife-edge at small N.
- **UX U3 (P2)** — risk-raise dismissal validator is just `text.strip()`; "ללא הסבר" and "עדיין לא" accepted verbatim. Quick-pick chips would reduce the friction the founder is signaling.

## MARK rulings on the cleanup itself
| § | Subject | Ruling |
|---|---|---|
| §A | Mark §3 verbatim wording preserved on Critical-residual | **PASS** (Hebrew + AI-copy mirrored; tests pinned) |
| §B | Softened-band suppresses §3 preamble | **PASS** — sound interpretation: cause is now operator-declared, so re-asserting "unverified — manual verification required" would itself violate §3 in the opposite direction |
| §C | Compact-on-gate-clamp 5-line block | **PASS** — precise 3-part predicate; ⛔ reason + current/recommended survive |
| §D | Natural-hold dual-path (verbose preserved) | **REQUIRES_FOLLOWUP** — acceptable, but codify §X2 to prevent later weaponization ("hide stats when system decides against the up-leg") |
| §E | AI-copy mirrors Hebrew variant on §3-class wording | **PASS** — codified as §X3 going forward |

**3 new rulings proposed** (would land in `MARK_SPRINT26_RULINGS.md` or `MARK_MEETING_UX_RULINGS.md`):
- §X1 — Breakdown lines must disclose their own source (raw vs adjusted), not silently absorb the disclaimer.
- §X2 — When the system's own decision contradicts a verbose breakdown, the breakdown may collapse to a compact reason-only form (precedent for future cleanups). Three-part predicate: (i) direction is the conservative one, (ii) gate explicitly evaluated, (iii) gate refused.
- §X3 — AI-copy variants MUST mirror the Hebrew variant for any §3-class (honesty/verification) wording.

## Tiered menu (per `MARK_SPRINT25_RULINGS.md` precedent)

### Tier-A — pure DOC/TEST polish (no behavior change, byte-preserving, agent-safe)
- **A1** (DATA F1) — Fix `docs/DATA_CONTRACTS.md` sign-convention example so it matches the code path the founder actually used. *Doc-only.*
- **A2** (OPS F1) — Add the CLI to `docs/DEPLOYMENT_RUNBOOK.md` (incl. `SENTINEL_CONFIG_PATH` env-var, docker-exec invocation). *Doc-only.*
- **A3** (TESTING T1+T2+T3) — Add 3 missing edge-case tests: over-shoot disclaimer, empty `heat_factors`, corrupt config value. *Test-only, byte-preserving.*
- **A4** (ENGINE F1) — Add end-to-end integration test pinning the `disclaimer → band string → G1 gate` chain. *Test-only.*
- **A5** (MARK §X1/§X2/§X3) — Codify the 3 new rulings.
- **A6** (DATA F4–F6) — Minor doc clarifications (key naming `total_pnl_usd` vs `net_pnl`; breakdown source; `adjustment_applied=True` semantics when band didn't actually soften).

### Tier-B — CLOSURE-FIX (wrong-vs-contract; additive; founder decision; low risk)
- **B1** (ARCH F1) — Extract a single-source helper for `pre_db_realized_pnl_estimate` (reduces 5 ad-hoc reads → 1; aligns with Sprint-25 ARCH F1 closure on the legacy fields). **Highest value of Tier-B — prevents F-YTD from drifting into Sprint-25 "fallback-as-truth" on sibling surfaces.**
- **B2** (ARCH F2) — Collapse `report_scheduler._compute_risk_rec` duplicate of `build_risk_raise_gate_ctx`.
- **B3** (UX U4) — Route risk-raise rejection through `audit_log` (or extend `audit_log` to read `risk_journal`) so `הפעולות שלי` reflects them. **Directly visible to the founder — the surface contradicts its label *right now.***
- **B4** (SECURITY S-2) — Path-traversal validation on `SENTINEL_CONFIG_PATH` (reject `..` / absolute paths outside the repo).

### Tier-C — CLOSURE-FIX in fragile/safety areas (explicit founder per-item, byte-locks regenerated)
- **C1** (UX U1) — Extract `risk_monitor.py:1242,1270-1305` adaptive-alert builder so the cleanup applies. Touches `risk_monitor.py` — Sprint-25 fragile zone with anti-spam invariants. Per AGENTS prime directive #7 ("preserve anti-spam"), requires per-position-dedup pin.
- **C2** (OPS F2) — Tune `LOOP_INTERVAL_SEC` vs healthcheck staleness ratio. Touches `main.py` + `docker-compose.yml` — production wiring.
- **C3** (SECURITY S-1) — Escalate dev-PIN anti-bruteforce beyond 5-min in-memory window. Touches `telegram_devops.py` PIN module.

### OUT — ADDITION (flagged, not built; founder follow-up)
- UX U3 — quick-pick chips for risk-raise dismissal reasons (UX addition).
- UX U5 — surface "אזהרות: הון מת" on portfolio-room card (UX addition; currently drill-down only).
- ENGINE F5 — structured logging at the bare-`except` `missing_data` site in `engine_core.py:88` (additive observability).
- ENGINE F6 — knife-edge WR/PF stability across stat_bucket sweeps (deferred per Sprint-25 C2 pattern).
- OPS LOW items + DATA P3 keys cleanups — collect into a future "Sprint-26 doc-drift" pass.

## Parent recommendation

**Take Tier-A in full** (6 items, ~all DOC/TEST, zero production-code-byte-change risk, A3+A4 close the lowest-hanging coverage holes the founder's session already revealed — the sign-convention contradiction alone would mislead the next operator).

Of the CLOSURE-FIX tier, **B1 + B3 are the highest priority**:
- **B1** (ARCH F1) — single-source helper is the cleanest path to prevent the F-YTD disclaimer from drifting into Sprint-25's "fallback-as-truth" failure mode on the sibling surfaces (`report_scheduler`, `risk_monitor`, `telegram_bot`).
- **B3** (UX U4) — the "אין פעולות מתועדות עדיין" lie is *visible to the founder right now* and the surface contradicts its own label. The fix is additive (re-route or extend the audit_log read path, no behavior change to risk math).

**B2 + B4** are sound but second-order; recommend bundling with B1 if Tier-B is accepted.

**Tier-C should be deferred** to a separate scoped phase per Sprint-25 C2 precedent — these touch fragile areas (`risk_monitor` anti-spam, `docker-compose` wiring, dev-PIN module) that warrant individual founder go-ahead with byte-locks regenerated and the AGENTS prime-directive invariants (#3 admin-only, #7 anti-spam) re-pinned.

## Founder decision (pending)

Reply with chosen scope:
- `A` — Tier-A only (recommended floor)
- `A+B1+B3` — recommended set
- `A+B` — Tier-A + Tier-B full
- `A+B+C` — full menu (each Tier-C item gets a per-item confirm before code)
- Custom — name the items

## Suite state at meeting time
- Pre-meeting: `2564 passed · 1 skipped · 0 failed` · coverage `73.20%` (gate `67%`).
- No code changes during this review (DOC-ONLY by construction). Suite intact.

## Sign-off
ARCH · DATA · ENGINE · MARK · OPS · SECURITY · UX/Telegram · TESTING — **all 8 approve closure of the 3 meeting-ux/fytd commits as scoped.** Follow-up work is founder choice per the tiered menu above. No item in this consolidation touches the CLAUDE.md red lines.

— Parent (consolidator), 2026-05-21.

---

## LANDED (2026-05-21, post-deploy verified)

**Founder chose `A+B1+B3` (recommended set).** Implemented as 3 sequential
Mark-gated waves, then deployed to production on the Orange-Pi host via
the runbook in `docs/DEPLOYMENT_RUNBOOK.md` §2.

### Commits (branch `claude/review-system-audit-FBZ2h`)

| Wave | SHA | Scope | Δ files | Δ lines |
|---|---|---|---|---|
| 2A | `d6299d6` | DOC polish (A1+A2+A5+A6) | 3 | +246 |
| 2B | `1324b3a` | B1 single-source helper + T2 fallback + A3/A4 tests (17 new) | 7 | +294 |
| 2C | `d16a70b` | B3 audit_log routing + 5 new tests | 4 | +108 |

### Suite state at landing
- **Pre-meeting:** 2564 passed · 1 skipped · 0 failed · coverage 73.20% (gate 67%).
- **Post-Wave-2C:** 2586 passed · 1 skipped · 0 failed (+22 tests). Coverage gate intact.
- CI-equivalent re-verified POST-COMMIT on the clean tree (Sprint-25 pattern).

### Production deployment outcome (host `orangepi3-lts`, 2026-05-21 ~07:08 UTC)
- Pre-deploy ref snapshotted: `e9872f8` (rollback anchor in `/tmp/sentinel_prev_ref.txt`).
- Pull: `e9872f8..d16a70b` fast-forward, 21 files / 1566 insertions.
- `sentinel_config.json` host-managed file NOT clobbered (live NAV `$7,878.92` preserved).
- 5 images rebuilt (cached layers, ~6s). 5 containers force-recreated.
- All 5 services flipped from `health: starting` to `(healthy)` within 8 minutes (faster than the 33-minute worst-case healthcheck window).

### Post-deploy smoke verified
- **B1 helper failsafe** (`{'pre_db_realized_pnl_estimate':'abc'}` → `0.0`): ✅
- **B1 helper numeric** (`495.67` → `495.67`): ✅
- **CLI `--show`** displays the live founder declaration `pre_db_realized_pnl_estimate: $+495.67` (the 21/05 declaration survived the deploy): ✅
- **`telegram_bot_secure_runner`** starting line in logs (CLAUDE.md hard constraint #2 satisfied — admin guard configured, rate limit 8 msgs / 60s, cooldown 90s): ✅
- **`report_scheduler`** start line in logs (reporting service operational): ✅

### Open follow-up (founder-deferred, NOT landed)
- **Tier-C C1** — `risk_monitor.py:1242,1270-1305` inline adaptive-alert builder (bypasses `fmt_adaptive_risk_block`; UX U1 P1 — recurs on direction-change alerts).
- **Tier-C C2** — `LOOP_INTERVAL_SEC=900` vs healthcheck `1980s` autoheal-mask (OPS F2; 6+ "Sentinel Bot מחובר" reconnects in 3 days).
- **Tier-C C3** — Dev-PIN anti-bruteforce window broadening (SECURITY S1).
- **OUT items** — UX U3 quick-pick rejection chips, UX U5 הון מת on portfolio-card, ENGINE F5 structured-log bare-except, ENGINE F6 WR/PF stat-bucket stability.

Tier-C reserved for a future founder-confirmed scoped phase per Sprint-25 C2 precedent — each item gets a per-item confirm + byte-locks regenerated.

### Mark §X1/§X2/§X3 status
Codified in `docs/teams/MARK_MEETING_UX_RULINGS.md`; now binding precedent for every future cleanup of the same shape. The 22 wave-2 tests are the pinning set.

— Parent (consolidator), 2026-05-21 post-deploy. Branch HEAD: `d16a70b`.
