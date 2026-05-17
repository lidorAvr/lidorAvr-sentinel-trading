# Phase C2 — SELL/BUY Classifier Divergence (Engine F1+F2) — PREDEFINED SCOPE

**Status:** SCOPE — awaiting founder go-ahead before execution.
**Origin:** Sprint-25 Engine audit F1+F2 (top remaining latent money-affecting item; founder deferred to its own Phase).
**Authority model (founder):** separate, predefined scope + separate acceptance tests; fragile-area CLOSURE-FIX → founder-gated, Mark-gated.

---

## 1. The defect (verified against source)

Three sites classify SELL vs BUY **inconsistently**:

| Site | How it splits SELL/BUY | Correct? |
|---|---|---|
| `analytics_engine.py:399` | `df[df["side"].str.upper().eq("SELL")]` (and BUY) — **`side` string** | ✅ matches DATA_CONTRACTS |
| `adaptive_risk_engine.py:~140-149` | `buys = group[group["quantity"] > 0]`, `sells = group[group["quantity"] < 0]` — **sign of quantity** | ❌ |
| `engine_core.py` `get_open_positions_campaign` (~:483-490) | `net_qty = group["quantity"].sum()`, `buys = group[group["quantity"] > 0]` — **sign of quantity** | ❌ |

`DATA_CONTRACTS.md:48` documents the broker export can emit a **SELL with positive `quantity`**. On that input:
- **F1 (adaptive_risk_engine):** the closing SELL has `quantity > 0`, so it is misread as a BUY → the campaign's `buys_qty - sells_qty` close test never trips → the campaign **silently never closes** → absent from heat / streak / win-rate AND from the drawdown auto-cut. Worst case: drawdown auto-cut can **raise risk into a drawdown**.
- **F2 (engine_core open book):** the positive-qty SELL inflates `net_qty` so a *closed* campaign reads as a **phantom open position** → wrong NAV exposure / open-R / ALGO caps / `risk_monitor` alerts.

`analytics_engine.py` is already correct (`side`-string) and is the reference semantics.

## 2. The fix (proposed)

One shared, pure **side-first classifier** mirroring `analytics_engine`'s contract: a trade is a SELL iff `str(side).upper() == "SELL"`, a BUY iff `== "BUY"`; quantity is used only as magnitude (`.abs()`), never as the side oracle. Rewire `adaptive_risk_engine` (F1) and `engine_core.get_open_positions_campaign` (F2) to it. `analytics_engine.py` is **NOT touched** (already correct + byte-locked).

## 3. Hard constraints / byte-identity obligations

- **`engine_core.py` is byte-locked** (Wave-2A `tests/_byte_lock_baselines/engine_core.py.baseline` + lock family). C2 requires a **governed baseline regeneration** — the authorized ritual the Wave-2A mechanism documents: the legitimate Mark-gated edit lands together with a regenerated `engine_core.py.baseline`, accompanied by the named byte-identical proof. The lock family stays GREEN. No other baseline regenerated.
- **`adaptive_risk_engine.py`** is NOT baseline-locked (free to edit; covered by the `--cov=adaptive_risk_engine` gate).
- **`analytics_engine.py` / `period_data_probe.py` / `telegram_bot*` / `docker-compose.yml` / migrations / LOCKED `tests/test_real_data_april_regression.py`** — git-diff EMPTY.
- **Byte-identical on all currently-correct inputs:** negative-qty SELL and normal BUY must produce **identical** results to today. The LOCKED April regression fixture uses **negative-qty SELLs**, so the side-first classifier is a **provable no-op there** → `8 / +$180.49 / WR .375 / PF 2.626 / excl 2` byte-identical; Sprint-22 tz-aware==tz-naive unchanged; Sprint-23 probe loss-free; full suite ≥ 1961, 0 failed.
- Behavior change is **authorized and intended ONLY** on the currently-mishandled positive-qty-SELL input (that is the closure-fix point). No new feature/flag/metric (a classifier alignment is a closure-fix, not an addition). WS-C / `-1`-sentinel / ALGO string untouched.
- CI-equivalent (`--cov-fail-under=67`) verified GREEN **post-commit on the clean tree** (the Sprint-24 lesson, now standard).

## 4. Separate acceptance tests (must all pass)

New `tests/test_phase_c2_sell_classifier.py`:
1. **Positive-qty SELL now closes (F1):** an `adaptive_risk_engine` campaign whose closing SELL has `quantity > 0` and `side == "SELL"` is now correctly closed (enters heat/streak/WR; drawdown-cut sees it). Pre-fix oracle: it did NOT close.
2. **Positive-qty SELL not phantom-open (F2):** `engine_core.get_open_positions_campaign` no longer lists a fully-closed positive-qty-SELL campaign as open; `net_qty` excludes the SELL leg.
3. **Negative-qty SELL byte-identical (no regression):** identical adaptive + open-book output before/after for the negative-qty-SELL convention (oracle equality).
4. **LOCKED April byte-identical** post-C2 (`8/+$180.49/WR.375/PF2.626/excl 2`) reusing the LOCKED fixture verbatim.
5. **Mixed/edge:** blank/NaN `side`, `side` set but qty sign-conflicting, ALGO rows — defined deterministically, segregation preserved.
No existing test deleted/weakened (Mark Ruling 6.1); net suite count only grows.

## 5. Open governance question for the founder

The environment's binding dev-instruction is to develop on **`claude/review-system-audit-FBZ2h`** and not push to a different branch without explicit permission. The founder's Phase model says "separate branch". **Decision needed:** execute C2 on `claude/review-system-audit-FBZ2h`, OR explicitly authorize a named separate branch (e.g. `claude/phase-c2-sell-classifier`) to push to.

**Nothing in this Phase is executed until the founder approves this scope (and the branch question).**
