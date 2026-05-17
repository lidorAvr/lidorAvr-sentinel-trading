# Phase C2 — SELL/BUY Side-First Classifier (Engine F1+F2) — IMPLEMENTATION RECORD

**Status:** EXECUTED (tree left dirty; parent does the governed consolidation/commit).
**Branch:** `claude/review-system-audit-FBZ2h` (founder-approved per `PHASE_C2_SCOPE.md` §5).
**Authority:** founder-approved predefined scope `docs/teams/PHASE_C2_SCOPE.md`;
Sprint-25 Engine audit F1+F2; Mark Sprint-25 rulings (CLOSURE-FIX founder-gated).
**Classification:** CLOSURE-FIX (founder-decision-required) — fixes a genuinely-wrong
production behavior vs the `analytics_engine`/DATA_CONTRACTS.md:48 contract on the
documented positive-qty-SELL broker export. No new feature/flag/metric (a classifier
single-sourcing is a closure-fix, not an ADDITION — Mark Ruling 2).

---

## 1. The shared classifier (NEW — `engine_core.split_side_first`)

Inserted into `engine_core.py` immediately before `get_open_positions_campaign`
(after the prior function's `except` line). Pure, no I/O, does not mutate `group`.

`engine_core.py:473-506` (post-edit line numbers):

```python
def split_side_first(group):
    """Phase-C2 shared side-first SELL/BUY classifier (pure). ..."""
    side_u = group["side"].astype(str).str.upper().str.strip()
    buys = group[side_u.eq("BUY")]
    sells = group[side_u.eq("SELL")]
    buys_qty = float(buys["quantity"].abs().sum())
    sells_qty = float(sells["quantity"].abs().sum())
    return buys, sells, buys_qty, sells_qty
```

**Contract (mirrors the CORRECT `analytics_engine.py:399/417`):** a row is a SELL
iff `str(side).upper().strip() == "SELL"`, a BUY iff `== "BUY"`. `quantity` is
treated ONLY as a magnitude (`.abs()`) and is NEVER the side oracle. Returns
`(buys, sells, buys_qty, sells_qty)` — row subsets + non-negative magnitude sums.
A blank/NaN/garbage `side` is NEITHER a BUY nor a SELL (excluded from both legs —
honest, never silently coerced into a side).

Placement rationale: both callers already `import engine_core as ec`
(`adaptive_risk_engine.py:18`, and F2 is in-file), so the helper lives where both
reach it without a new fragile coupling; it adds no other engine_core behavior.

---

## 2. F1 rewire — `adaptive_risk_engine.py` (`compute_closed_campaigns`)

NOT baseline-locked (covered by `--cov=adaptive_risk_engine`).

**Before** (`adaptive_risk_engine.py:140-144`, sign-of-quantity):
```python
buys = group[group["quantity"] > 0]
sells = group[group["quantity"] < 0]
buys_qty = buys["quantity"].sum()
sells_qty = sells["quantity"].abs().sum()
if buys_qty <= 0:
```

**After** (`adaptive_risk_engine.py:140-148`, side-first via shared helper +
explanatory comment):
```python
# Phase-C2 F1: side-first SELL/BUY split (shared classifier in
# engine_core), mirroring analytics_engine's `side`-string contract
# ... provable no-op on the negative-qty SELL convention ...
buys, sells, buys_qty, sells_qty = ec.split_side_first(group)
if buys_qty <= 0:
```

The close-test math (`(buys_qty - sells_qty)/buys_qty > 0.01`), dates
(`sells["trade_date"].max()`), `pnl_usd` aggregation (`sells["pnl_usd"].sum()`),
first-BUY basis, and ALGO/`stat_bucket` handling are byte-identical otherwise.

## 3. F2 rewire — `engine_core.get_open_positions_campaign`

**Before** (`engine_core.py` old `:518-523`):
```python
net_qty = group["quantity"].sum()
if net_qty <= 0.001: continue
sym = group.iloc[0]["symbol"]
realized_pnl = group[group["side"].str.upper() == "SELL"]["pnl_usd"].sum()
buys = group[group["quantity"] > 0]
if buys.empty: continue
```

**After** (`engine_core.py` new `:518-523`):
```python
buys, _c2_sells, _c2_buys_qty, _c2_sells_qty = split_side_first(group)
net_qty = _c2_buys_qty - _c2_sells_qty
if net_qty <= 0.001: continue
sym = group.iloc[0]["symbol"]
realized_pnl = group[group["side"].str.upper() == "SELL"]["pnl_usd"].sum()
if buys.empty: continue
```

`net_qty` is now `buys_qty − sells_qty` by **side string** (so a fully-closed
positive-qty-SELL campaign nets to 0, not a phantom 200); `buys` is the side-first
BUY subset. **Every other line of `get_open_positions_campaign` and the rest of
`engine_core.py` is byte-identical** (only these two derivations changed; `realized_pnl`,
`first_day_buys`, `base_qty`, `avg_price`, `sl`/`init_sl`, `has_sells`, the output
dict — all untouched).

## 4. `analytics_engine.py` — NOT TOUCHED

Already correct (`side`-string) + Sprint-19/24 byte-locked. `git diff` EMPTY;
`tests/_byte_lock_baselines/analytics_engine.py.baseline` 0-diff;
`test_analytics_engine_git_diff_empty` GREEN.

---

## 5. Governed `engine_core.py` byte-lock ritual (CRITICAL — evidence)

`engine_core.py` is guarded by the Sprint-25 commit-state-AGNOSTIC byte-lock:
`tests/test_sprint25_byte_lock_redteam.py::TestGreenOnAuthorizedState`
calls **`bl.assert_byte_identical("engine_core.py")`** — a hard **SHA256** guard
(NOT an allowlist-delta path; the allowlist `baseline_line_delta` form is used only
for `analytics_engine.py`). The authorized ritual (`tests/_byte_lock_baseline.py`
module docstring): the legitimate Mark-gated edit lands **together with** a
regenerated `<file>.baseline` that is a verbatim copy of the new authorized content.
The mechanism provides no regeneration helper, so the ritual is an exact file copy:

```
cp engine_core.py tests/_byte_lock_baselines/engine_core.py.baseline
```

**Named byte-identical proof** (`cmp` + SHA256, final post-doc-correction state):

```
$ cmp engine_core.py tests/_byte_lock_baselines/engine_core.py.baseline   # exit 0
$ sha256sum engine_core.py tests/_byte_lock_baselines/engine_core.py.baseline
7f90baba6f4114cbdd138b2a065e99e28b1fa1b7f14417ce03c8a3c14772f95d  engine_core.py
7f90baba6f4114cbdd138b2a065e99e28b1fa1b7f14417ce03c8a3c14772f95d  tests/_byte_lock_baselines/engine_core.py.baseline
```

Identical SHA256 ⇒ `assert_byte_identical("engine_core.py")` GREEN. **No other
baseline regenerated or touched**: `analytics_engine.py.baseline`,
`period_data_probe.py.baseline`, `test_real_data_april_regression.py.baseline` all
git-diff EMPTY (verified). The lock family + `test_sprint25_byte_lock_redteam.py`
stay GREEN (the RED-on-unauthorized-edit direction is unaffected: it sandboxes a
synthetic pair and is independent of the engine_core bytes).

Byte-lock guard verification (subset, deterministic):
`tests/test_sprint25_byte_lock_redteam.py` (13) +
`test_analytics_engine_git_diff_empty` (1) + `tests/test_sprint24_b1b3_byte_identical.py`
+ `tests/test_real_data_april_regression.py` + `tests/test_phase_c2_sell_classifier.py`
→ **40 passed, 0 failed**.

---

## 6. Byte-identity proof — the NO-OP argument (Mark Ruling 4)

On the **currently-correct conventions** the classifier is a provable no-op:

- **Negative-qty SELL** (the convention the LOCKED April fixture uses): for
  in-contract data SELL rows have `side=="SELL"` AND `quantity<0`, BUY rows have
  `side=="BUY"` AND `quantity>0`. The classifier's `side=="SELL"` mask selects
  EXACTLY the rows the old `quantity<0` mask did; `side=="BUY"` selects exactly the
  old `quantity>0` rows. `quantity.abs()` equals the old `sells["quantity"].abs()`
  magnitude, and for positive-qty BUYs `.abs()` is the identity ⇒ identical
  `buys`/`sells`/`buys_qty`/`sells_qty`. The `float()` wrap is value-preserving.
- **Normal positive-qty BUY:** same argument, BUY side.

Behavior differs **ONLY** on the previously-mishandled positive-qty SELL (the
authorized closure-fix point). No new feature/flag/metric; WS-C / `-1`-sentinel /
ALGO string untouched; no `telegram_bot.py` change; no Sprint-24 B1/B3, C1 dev-PIN,
or Wave-2A mechanism regression.

**Which tests pin the no-op:**
- `tests/test_phase_c2_sell_classifier.py::TestNegativeQtySellByteIdenticalNoOp`
  reconstructs the EXACT pre-C2 sign-of-quantity split inline and asserts the live
  `ec.split_side_first` returns identical row-sets (`trade_id` lists) and magnitude
  sums for both callers' shapes, plus adaptive + open-book oracle equality.
- `tests/test_phase_c2_sell_classifier.py::TestLockedAprilByteIdenticalPostC2`
  re-runs the LOCKED April fixture VERBATIM (imported from
  `tests.test_real_data_april_regression`) through analytics (8 / +$180.49 /
  WR .375 / PF 2.626 / excl 2) and through the C2-rewired adaptive engine.
- `tests/test_real_data_april_regression.py` itself: byte-identical, **0-diff**,
  not edited, not re-asserted — still GREEN in the full suite.

---

## 7. Acceptance tests (NEW — `tests/test_phase_c2_sell_classifier.py`)

The five mandated by scope §4 (15 assertions, all GREEN), no existing test
deleted/weakened (Mark 6.1 — net suite count only grows):

1. **F1 positive-qty SELL now closes** + a pinned pre-fix oracle (old sign split
   → `sells.empty`, never closed).
2. **F2 positive-qty SELL not phantom-open** + pre-fix oracle (`quantity.sum()`
   = 200 phantom) + a still-open partial-close control (residual net_qty 60).
3. **Negative-qty SELL byte-identical** (inline pre-C2 reconstruction equality
   for both callers + adaptive + open-book oracle).
4. **LOCKED April byte-identical** post-C2 reusing the LOCKED fixture verbatim
   (analytics 8/+$180.49/WR.375/PF2.626/excl2 + adaptive/weekly-ALGO no-op).
5. **Mixed/edge:** blank/`None` side excluded from both legs; side-set-but-qty-
   sign-conflicting resolves by side string; ALGO segregation preserved
   (`stat_bucket == ALGO_OBSERVED`), incl. an ALGO positive-qty-SELL closure.

---

## 8. ⟨MARK⟩ gate slots

- ⟨MARK Ruling 1.1 — money-math correct vs contract⟩: F1/F2 now match the
  `analytics_engine`/DATA_CONTRACTS.md:48 `side`-string contract on the documented
  positive-qty-SELL export; LOCKED April + DEC-019 reconciliation unchanged. _____
- ⟨MARK Ruling 3.3 — LOCKED April byte-identical⟩: 8/+$180.49/WR.375/PF2.626/excl2,
  `tests/test_real_data_april_regression.py` 0-diff, GREEN. _____
- ⟨MARK Ruling 3.4 — Sprint-19/24 lock + paired proof intact⟩: analytics 0-diff;
  `test_analytics_engine_git_diff_empty` + `TestSprint24B1B3ByteIdentical` GREEN. _____
- ⟨MARK Ruling 3.5 — no R/NAV/exposure/campaign math change without proof⟩: change
  is the side-classifier closure-fix; no-op on in-contract inputs, named proof §6. _____
- ⟨MARK Ruling 5.A — suite ≥ floor, 0 failed, no test weakened⟩: full suite
  **1976 passed, 0 failed** (1961 + 15 new). _____
- ⟨MARK Ruling 5.B — CI-equivalent green⟩: CI command + CI env →
  **1976 passed, 0 failed**, cov **71.84% ≥ 67%**. _____
- ⟨MARK Ruling 5.D.8/9 — no addition; behavior change only by gate⟩: CLOSURE-FIX,
  founder-approved scope; no new feature/flag/metric. _____
- ⟨MARK governed engine_core baseline regeneration⟩: only `engine_core.py.baseline`
  regenerated as a verbatim copy (SHA `7f90baba…`); all other baselines 0-diff. _____

---

## 9. Explicit confirmations

- Modified files (exactly): `adaptive_risk_engine.py`, `engine_core.py`,
  `tests/_byte_lock_baselines/engine_core.py.baseline`; NEW:
  `tests/test_phase_c2_sell_classifier.py`, `docs/teams/PHASE_C2_IMPL.md`.
- 0-diff (git): `analytics_engine.py`, `period_data_probe.py`, `telegram_bot*`,
  `docker-compose.yml`, `migrations/`, `tests/test_real_data_april_regression.py`,
  `analytics_engine.py.baseline`, `period_data_probe.py.baseline`,
  `test_real_data_april_regression.py.baseline`.
- LOCKED April **8 / +$180.49 / WR .375 / PF 2.626 / excl 2** byte-identical
  (negative-qty SELLs ⇒ classifier no-op); Sprint-22 tz / Sprint-23 probe / C1
  dev-PIN / Sprint-24 B1/B3 / Wave-2A mechanism intact.
- Behavior change confined to the positive-qty-SELL closure-fix point.
- NOT committed/pushed; tree left dirty for the parent's governed consolidation.
