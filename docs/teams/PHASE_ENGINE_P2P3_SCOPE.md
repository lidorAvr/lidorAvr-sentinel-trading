# Phase Engine-P2/P3 — remaining backlog — PREDEFINED SCOPE

**Status:** SCOPE — awaiting founder go-ahead + scope/decision choice before execution.
**Origin:** Sprint-25 Engine audit P2/P3 (F4,F5,F6,F7,F8,F9). **All P0/P1 already closed** (Tier-A/C1/B1/C2/B3/Arch-F1). Nothing here blocks production today (DEC-019 reconciled exact).
**Authority model:** predefined scope + separate acceptance tests; founder-gated, Mark-gated; byte-locked-file changes use the governed Wave-2A/Sprint-24/C2 ritual.

---

## Honest per-item value vs governance cost

| Item | What | Value | Cost / locked? | Class |
|---|---|---|---|---|
| **F4** | `_aggregate_campaigns` (`analytics_engine.py:417`) + `adaptive_risk_engine.py:155` + `engine_core.get_open_positions_campaign` sum `sells["pnl_usd"]` with **no `trade_id` dedup** → a re-exported/double-synced SELL **doubles realized PnL/R** (200→400) | **HIGH (latent)** — real defensive integrity for a money system; NOT observed in current prod (DEC-019) | **HIGHEST** — touches `analytics_engine.py` (Sprint-24 allowlist + Wave-2A SHA) **and** `engine_core.py` (C2-style SHA baseline regen). 3 files, 2 byte-locked | closure-fix (founder) |
| **F5** | `adaptive_risk_engine.py:150` `(buys_qty-sells_qty)/buys_qty > 0.01` — at **exactly** 1% residual (99/100) the campaign is falsely treated CLOSED while 1 share is still open | MED — real but razor-narrow boundary edge | **LOW** — `adaptive_risk_engine.py` NOT byte-locked; one-operator fix | closure-fix (founder) |
| **F6** | PF `math.inf` (`analytics_engine.py:189,214`) vs the documented 99.0 sentinel (dashboard only) — convention divergence / reconciliation trap | LOW — clamped everywhere checked; risk is future serialization/delta math | **~0** — **DOC-ONLY** (DEC-021 lists the `math.inf` branch as intentional DO-NOT-TOUCH) | polish (doc) |
| **F7** | `engine_core.py:973` `round(...,2)` of the 1R denominator → every `net_r` carries a sub-cent basis distortion | ~0 — **already pinned**; changing it BREAKS the LOCKED April PF 2.6262 | **~0** — **DOC-ONLY** (DEC-021: the round is intentional, do NOT "clean up") | polish (doc) |
| **F9** | out-of-order rows floor `days_held=1` → `avg_r_per_day`/dev-score inflated (display/score only, R itself correct) | LOW — not money-affecting | **~0** — **DOC-ONLY** | polish (doc) |
| **F8** | `-1` sentinel / WS-C recoverable-candidate counter | n/a — DEFERRED | **OUT** — Sprint-23 byte-locked; do NOT touch | addition (OUT) |

## Proposed scope options (founder picks one)

- **(a) FULL** — F4 (governed: analytics_engine Sprint-24-style allowlist+baseline expansion + C2-style engine_core baseline regen + named byte-identical proof) **+** F5 (boundary fix) **+** F6/F7/F9 (DATA_CONTRACTS doc) **+** F8 restated OUT. Closes the entire reviewed backlog.
- **(b) LEAN (recommended-if-not-full)** — F5 + F6/F7/F9 doc only; **defer F4** (latent, not-observed, the single most expensive governed change). Cheap, low-risk.
- **(c) DOC-ONLY** — only F6/F7/F9 in DATA_CONTRACTS (close the documented-vs-actual honesty gap; defer all code).
- **(d) STOP** — production-closure mission is substantively complete (all P0/P1 closed); log P2/P3 as documented backlog, no further code.

Parent recommendation: **(a) FULL** if you want the codebase fully closed — F4 is genuine silent-money-corruption defense (exactly the hardening this program targets) and the governed machinery + verification discipline are warm; but it is latent and the costliest governed change. **(b)/(d)** are entirely legitimate given all P0/P1 are already closed.

## F4 fix (if in scope)
Add a single `trade_id` dedup before per-campaign aggregation, applied identically in all three sites (`_aggregate_campaigns`, `adaptive_risk_engine.compute_closed_campaigns`, `engine_core.get_open_positions_campaign`): drop exact-duplicate `trade_id` rows (keep first) prior to the `sells["pnl_usd"].sum()`. **Byte-identical when there are no duplicate `trade_id`s** (the LOCKED April fixture + current prod per DEC-019) → April 8/+$180.49/WR.375/PF2.626/excl 2 unchanged; Sprint-22 full-dict unchanged. Behavior changes ONLY on the duplicated-row input (the authorized closure-fix point). Governed: analytics_engine via the Sprint-24 allowlist+baseline mechanism; engine_core via the C2 SHA-baseline-regeneration ritual; `period_data_probe.py` untouched.

## F5 fix + decision (if in scope)
`> 0.01` → **`>= 0.01`** so exactly-1%-residual stays OPEN (not falsely closed). **Decision F5:** (i) relative `>= 0.01` (minimal, recommended) vs (ii) an absolute residual-share floor (bigger design change). Byte-identical on full-close / residual-0 (LOCKED April) and any residual ≠ exactly 1%.

## Hard constraints (all options)
No `period_data_probe.py`/`docker-compose.yml`/migration/`telegram_*`/`account_state.py` change. C1/C2/B3/Arch-F1/Wave-2A invariants intact. `analytics_engine.py`/`engine_core.py` changes ONLY via their governed ritual + named byte-identical proof; ALL other `tests/_byte_lock_baselines/*` 0-diff. LOCKED April byte-identical; Sprint-22/23/24 intact. No addition. Suite ≥ **1992**, 0 failed (new tests only ADD). CI-equivalent (`--cov-fail-under=67`, CI env) GREEN **post-commit on the clean tree**.

**Nothing executed until the founder picks (a)/(b)/(c)/(d) and (if F5 in scope) Decision F5.**
