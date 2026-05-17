# Phase NAV-Unify (Arch-F1 Decision B) — PREDEFINED SCOPE

**Status:** SCOPE — awaiting founder go-ahead + the canonical-semantics decision before execution.
**Origin:** Arch-F1 Decision B (deferred, behavior-bearing). Founder chose to open it. Highest-stakes remaining item: NAV is money-affecting + a CLAUDE.md most-fragile area; `engine_core.py` is byte-locked; unifying genuinely changes bot/risk-monitor behavior on the divergent edges.
**Authority model:** predefined scope + separate acceptance tests + parity-test-FIRST; founder-gated, Mark-gated; governed engine_core SHA-baseline ritual.

---

## 1. The two readers — EXACT divergences (verified against source)

`account_state.load()` (report pipeline; "single source of truth" per MODULE_MAP) vs `engine_core.get_nav_with_freshness()` (consumed by `bot_helpers.py:94` `get_nav_and_risk` + `risk_monitor.py:586,606`):

| # | Edge | `account_state.load()` | `engine_core.get_nav_with_freshness()` | Money-affecting? |
|---|---|---|---|---|
| D1 | **`nav: 0` in config** | `data.get("nav", …)` → keeps explicit **0.0** | `cfg.get("nav") or cfg.get("total_deposited") or 7500` → **falls through** to total_deposited | **YES** — different acc_size/target_risk |
| D2 | stale boundary | `age < 24` fresh / `< 48` stale (strict `<`) | `age > STALE` / `> CRITICAL` (strict `>`) | edge: classification at exactly 24/48h |
| D3 | no `nav_updated_at` | `freshness="unknown"`, `is_stale=True`, **`is_critical=False`** | `is_stale=is_critical=True`, `source="manual"` | callers branching on is_critical |
| D4 | missing/corrupt config | nav=7500, `ok=False`, **`is_critical=False`** (unknown) | nav=7500, `ok=False`, **`is_critical=True`** | callers branching on is_critical |
| D5 | dict shape / labels | shape A (`nav_source`, `freshness`, generic Hebrew labels, `total_deposited`, `risk_pct_input`) | shape B (`source`, `updated_at`, `$`-amount Hebrew labels, no total_deposited) | caller presentation only |
| — | success `ok` / normal broker-fresh | `ok=True` | `ok=True` | **identical today** (the normal path) |

**Risk-de-mitigant (verified):** the LOCKED `test_real_data_april_regression.py` + Sprint-22 pass a **fixture dict `_ACCT`** straight into `compute_period_analytics` — they never call `account_state.load()` nor the file reader. So an `account_state.load()` refactor is byte-identical w.r.t. the LOCKED regression. `bot_helpers.get_nav_and_risk` uses `nav_info["ok"]`; `risk_monitor` reads `["nav"]`/the dict.

## 2. Proposed design (Option β — recommended)

Extract ONE shared pure core `account_state._resolve_nav_core()` → canonical `(nav, nav_updated_at, age_hours, freshness, is_stale, is_critical, ok, source_kind)`. `account_state.load()` and `engine_core.get_nav_with_freshness()` both become **thin shape/label adapters** over that core (each keeps its OWN dict shape + its OWN label strings — D5 preserved per caller). The shared core guarantees the NAV **value + freshness classification can never desync** (closes the actual money-risk). Canonical semantics = **`account_state`'s** (the documented single source; honest explicit-`0` (D1), `unknown`-not-critical (D3/D4), strict-`<` boundary (D2); aligns with CLAUDE.md #1 and the Arch-F1 Decision-A "Honest" precedent).

Alternatives (for the decision): **α** = engine side calls `account_state.load()` and re-shapes (bigger engine_core change, same net effect); **γ** = one function/one shape, all callers migrated (largest blast radius — NOT recommended).

## 3. Behavior change (authorized point) vs byte-identical (must prove)

- **Byte-identical (must prove):** the **normal broker-fresh path** for BOTH callers (bot/risk-monitor sizing + every report-pipeline consumer) and ALL existing tests; the LOCKED April 8/+$180.49/WR.375/PF2.6262/excl2 + Sprint-22 (fixture-dict path, untouched).
- **Authorized behavior change (the closure point), ONLY on D1–D4 edges where the two currently disagree:** bot/risk-monitor adopt the canonical (account_state) semantics on `nav:0`, the exact 24/48h boundary, no-timestamp, and missing/corrupt `is_critical`. Each such delta enumerated by the **parity test FIRST** and pinned to the chosen canonical.

## 4. Governed rituals / hard constraints

- `engine_core.py` is byte-locked → C2/Engine-P2/P3-style: land the `get_nav_with_freshness` rewrite + regenerate ONLY `tests/_byte_lock_baselines/engine_core.py.baseline` (cmp exit 0 / identical SHA); redteam + the analytics allowlist + Sprint-24 proof stay GREEN. `account_state.py` is NOT byte-locked but its NAV path is treated with a byte-identical-on-normal-path proof. NO other baseline regenerated; `period_data_probe.py`/`analytics_engine.py`/`docker-compose.yml`/migrations/`telegram_*` 0-diff.
- No import cycle (account_state is a clean leaf — `os/json/datetime` only; engine_core importing it is acyclic). No new feature/flag/command/metric/schema. C1/C2/B3/Arch-F1/Sprint-22/23/24/Wave-2A invariants intact. WS-C/`-1`-sentinel untouched.
- Full suite `python -m pytest -q -p no:cacheprovider` ≥ **2008**, 0 failed (new tests only ADD). CI-equivalent (`--cov-fail-under=67`, CI env) GREEN **post-commit on the clean tree** (the Sprint-24 lesson).

## 5. Separate acceptance tests (`tests/test_phase_navunify.py`)

Parity test authored FIRST (freeze today's two outputs as the oracle): for present-broker-fresh / stale / critical / no-timestamp / `nav:0` / missing / corrupt configs, capture BOTH readers pre-refactor. Post-refactor: (a) normal broker-fresh → BOTH callers byte-identical to their pre-refactor output (incl. `bot_helpers.get_nav_and_risk` `(acc_size,target_risk)` and risk_monitor:606); (b) the D1–D4 edges resolve to the chosen canonical (the enumerated, founder-approved deltas); (c) shape/labels per caller unchanged on the normal path (D5); (d) LOCKED April + Sprint-22 byte-identical. No existing test weakened (Mark 6.1).

## 6. The decision for the founder (before execution)

**Canonical semantics + design:** (β-recommended) Option β with **canonical = `account_state` semantics** (honest explicit-0 / unknown-not-critical / strict-`<`); OR (α) engine side consumes `account_state.load()` wholesale; OR (γ) full one-shape unification (not recommended); OR specify a different per-edge ruling for D1–D4.

**Nothing executed until the founder approves this scope + the §6 decision.**
