# Sprint 22 — Design: single-point tz-normalization in `compute_period_analytics`

**Team:** Architecture + Engine · **Date:** 2026-05-16 · **Branch:** `claude/review-system-audit-FBZ2h`
**Authority:** DEC-20260516-019 (root cause proven); SPRINT22_PLAN.md.
**Doc-only.** No production code, no git commit/push, no file mutation in this deliverable.
**Mark gate:** `docs/teams/MARK_SPRINT22_RULINGS.md` is **ABSENT** at authoring time (parallel Wave-1).
Every threshold / wording / policy / normalization-direction choice is a verbatim
`⟨MARK:…⟩` placeholder. The **documented default-pending-Mark** is *normalize to
tz-naive* (strip tz from the bounds; keep `trade_date` tz-naive) — chosen because it
is provably byte-identical on the 100%-tz-naive suite (§2). Mark may override the
direction; the design is parameterised so only the helper body changes.

---

## 0. Proven root cause (do NOT relitigate)

Same `tests/test_real_data_april_regression.py::_april_df()` fixture, REAL
`analytics_engine.compute_period_analytics`:

| Bounds | Result |
|---|---|
| tz-**naive** (100% of suite) | **8 campaigns / +$180.49** ✅ |
| tz-**aware** Asia/Jerusalem (PRODUCTION) | **0 / $0.00** ❌ silent all-False |

Mechanism (cite file:line):
- `report_scheduler.py:553` `now = datetime.now(ISRAEL_TZ)` → `_run_weekly(now)`/`_run_monthly(now)`
  (`:562`/`:570`) → `_weekly_period`/`_monthly_period` (`:153-167`, pure
  `.replace()` + `timedelta` — **preserve `tzinfo`**) → tz-**aware**
  `period_start/period_end` into `compute_period_analytics` at
  `report_scheduler.py:251` and `:363`.
- `report_on_demand.py:96-97` `now = datetime.now(sched.ISRAEL_TZ)` →
  `last_complete_*_ref` (`:37-63`, `.replace`/`timedelta`, preserves tz) →
  `sched._weekly_period`/`_monthly_period` → tz-aware bounds into
  `compute_period_analytics` at `report_on_demand.py:112`.
- `analytics_engine.py:30` `pd.to_datetime(df["trade_date"], errors="coerce")`
  → tz-**naive** `datetime64[ns]` Series (fixture dates are naive strings).
- Comparisons: WS-B unlinked block `analytics_engine.py:54-55`
  (`_unlinked["trade_date"] >= period_start` / `< period_end`) and
  `_get_closed_campaigns` `analytics_engine.py:334`
  (`sells["trade_date"] >= start` / `< end`) compare a tz-naive Series vs a
  tz-aware scalar → in this pandas, **silently all-False** (in
  `period_data_probe.py`'s own pre-filter it instead **RAISED**
  `Invalid comparison between dtype=datetime64[ns] and datetime` — same defect,
  different surface). Production weekly/monthly therefore render "0 קמפיינים".

---

## 1. The single-point patch

### 1.1 Helper (pure, internal, no math)

Add ONE private helper to `analytics_engine.py` (Internals section, near
`_get_closed_campaigns:331`). Pure datetime handling — **no R / NAV / campaign
/ Expectancy / PnL arithmetic**:

```
def _to_naive(ts):
    """⟨MARK: normalization direction⟩ — default-pending-Mark = strip tz.
    Return `ts` as a tz-NAIVE datetime/Timestamp. If `ts` is tz-aware,
    drop the tzinfo WITHOUT shifting the wall-clock value
    (ts.replace(tzinfo=None)); if already naive, return unchanged
    (identity). No clock conversion — period bounds are wall-clock
    day boundaries, and trade_date is stored wall-clock-naive, so the
    naive-vs-naive comparison must match on the SAME wall clock."""
```

`⟨MARK: confirm strip-tz (replace(tzinfo=None), NO astimezone shift) — NOT
convert-to-UTC. Wall-clock preservation is mandatory: the locked April bounds
are 2026-04-01 00:00 .. 2026-04-30 23:59:59 wall time; an astimezone(UTC) shift
would move a boundary by the Asia/Jerusalem offset (+2/+3h DST) and could
re-bucket a midnight-adjacent trade — that WOULD be a campaign-aggregation
behaviour change and is forbidden.⟩`

Mirror for the Series (post-`pd.to_datetime`):

```
# guarantee trade_date tz-naive; identity if already naive
if getattr(df["trade_date"].dt, "tz", None) is not None:
    df["trade_date"] = df["trade_date"].dt.tz_localize(None)  # ⟨MARK⟩ wall-clock, no convert
```

`⟨MARK: Series path — tz_localize(None) (wall-clock drop) vs tz_convert(None).
Default-pending-Mark = tz_localize(None) to match the scalar strip-tz rule.
In the locked suite trade_date is ALWAYS naive so this branch never executes
(provable no-op, §2) — Mark only needs to ratify behaviour for a future
tz-aware Supabase column.⟩`

### 1.2 EXACT placement

Inside `compute_period_analytics`, immediately AFTER the numeric coerce loop
ends (`analytics_engine.py:33`) and BEFORE the WS-B unlinked block begins
(`:35`/`:50-55`):

```
        df = df_trades.copy()
        df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce")
        for col in (...):
            ...
        # ── Sprint-22 (DEC-20260516-019 / ⟨MARK:SPRINT22 §tz⟩) — single-point
        # tz-normalization. Boundary-only: BOTH period bounds and the coerced
        # trade_date Series become tz-naive (wall-clock preserved). NO R/NAV/
        # campaign/Expectancy/PnL math touched. Provable no-op for tz-naive
        # inputs (§2). Fixes the WS-B unlinked filter (:54-55),
        # _get_closed_campaigns (:334), and EVERY caller at this one site.
        period_start = _to_naive(period_start)
        period_end   = _to_naive(period_end)
        if getattr(df["trade_date"].dt, "tz", None) is not None:
            df["trade_date"] = df["trade_date"].dt.tz_localize(None)  # ⟨MARK⟩
        # ── Sprint-21 WS-B ... (unchanged from here)
        _ul_cid = df["campaign_id"].astype(str).str.strip()
```

**One site covers all three consumers — proof:**
1. **WS-B unlinked filter (`:54-55`)** reads the now-rebound local
   `period_start`/`period_end` and the in-scope `df["trade_date"]` — both
   normalized two lines above. Covered.
2. **`_get_closed_campaigns` (`:334`)** is called at `:72` as
   `_get_closed_campaigns(df, period_start, period_end)` — it receives the
   SAME normalized `df` and the SAME rebound bounds (Python passes the local
   names; the helper compares `df["trade_date"]` vs `start`/`end`, all naive).
   Covered transitively — no edit inside `_get_closed_campaigns`.
3. **Every external caller** invokes ONLY `compute_period_analytics`
   (§4 audit) — never `_get_closed_campaigns` directly except the probe
   (§3, mirrored separately). So normalization at this one site fixes
   on-demand + scheduled weekly + scheduled monthly.

`_aggregate_campaigns` (`:341`) operates on already-filtered rows and does
`pd.Timestamp(...) - pd.Timestamp(...)` for `days_held` — both operands derive
from the normalized `df`, so naive−naive; no change. Untouched.

### 1.3 Does `_get_closed_campaigns` need an INDEPENDENT guard?

Enumerate every `_get_closed_campaigns` caller (repo-wide):
- `analytics_engine.py:72` — inside `compute_period_analytics`, AFTER §1.2
  normalization. Covered.
- `period_data_probe.py:184` — `ae._get_closed_campaigns(work, period_start,
  period_end)`. The probe builds `work` itself and does **not** pass through
  `compute_period_analytics`, so the §1.2 site does NOT cover it. Handled by
  the mirrored probe patch in §3 (normalize the probe's own bounds + `work`
  before its pre-filter AND before this delegation).

Conclusion: **NO independent guard inside `_get_closed_campaigns`** is needed.
`⟨MARK: ratify "no internal guard in _get_closed_campaigns; both its only two
callers normalize upstream (compute_period_analytics §1.2 / probe §3)".
Rationale: keeping the MOST-protected internal helper untouched minimizes
campaign-aggregation surface area; an internal guard would be dead-defensive
duplication. Mark may instead require a defensive internal idempotent
re-normalization — if so it MUST be identity on naive input (§2 still holds).⟩`

---

## 2. No-op proof for tz-naive inputs (byte-identical guarantee)

The normalization is **algebraic identity** when inputs are already tz-naive:

1. **Bounds:** `_to_naive(ts)` for a tz-naive `ts`: the `tzinfo is None`
   branch returns `ts` unchanged — same object/value. The downstream
   comparisons `Series >= period_start` / `< period_end` receive the
   identical scalars they receive today. ⇒ identical boolean masks ⇒
   identical `_ul_*`, `closed_trades`, `campaigns`, every KPI.
2. **Series:** in the entire suite + the LOCKED
   `test_real_data_april_regression.py`, `trade_date` is built from naive
   strings (`_r(... d ...)` → `'2026-03-13'` etc.); `pd.to_datetime` yields a
   tz-naive `datetime64[ns]` Series ⇒ `getattr(...dt, "tz", None) is None`
   ⇒ the `tz_localize(None)` branch **never executes** ⇒ the Series is the
   identical object it is today.
3. Therefore every value flowing into WS-B, `_get_closed_campaigns`,
   `_aggregate_campaigns`, the `countable`/`excluded`/`manual` partitions,
   WR / Expectancy / PF / R / setup-breakdown is **bit-for-bit unchanged**.
   ⇒ entire suite (baseline **1846**) + the LOCKED regression are
   **byte-identical**. A dedicated guard test (§5) asserts this explicitly.

The change is therefore *purely additive on the production tz-aware path* and
a *strict no-op on every existing test path*.

---

## 3. Mirrored probe patch (`period_data_probe.py`)

The probe filters BEFORE delegating, so it needs the SAME normalization
applied to its own bounds and its own `work` frame. Exact placement: in
`_window_block`, immediately AFTER the numeric coerce loop
(`period_data_probe.py:168`) and BEFORE the `td = work["trade_date"]` /
`sells_in` pre-filter (`:170-179`) AND before the
`ae._get_closed_campaigns(work, period_start, period_end)` delegation (`:184`):

```
        for col in (...):
            ...
        # ── Sprint-22 (DEC-20260516-019) — MIRROR analytics_engine §1.2.
        # Probe filters its OWN window (:178-179, :194-195) BEFORE delegating
        # to ae._get_closed_campaigns(:184); without this the tz-aware `now`
        # default (build_probe_report:301 = datetime.now(sched.ISRAEL_TZ))
        # makes the pre-filter RAISE (the original probe defect surface).
        # SAME rule, SAME helper semantics (import or shared) — ⟨MARK⟩ same
        # strip-tz direction as §1.1.
        period_start = ae._to_naive(period_start)
        period_end   = ae._to_naive(period_end)
        if getattr(work["trade_date"].dt, "tz", None) is not None:
            work["trade_date"] = work["trade_date"].dt.tz_localize(None)
```

`⟨MARK: reuse ae._to_naive (single source of truth, keeps the probe's
"reads ONLY via existing helpers" §A1 contract) vs a probe-local copy.
Default-pending-Mark = reuse ae._to_naive — it adds no new Supabase/math
surface and is already AST-clean for tests/test_sprint21_wave2.py.⟩`

Effects:
- `td.min()/td.max()` (`:171-174`), `sells_in` (`:178-179`), `in_win`
  (`:194-195`) all now compare naive-vs-naive ⇒ no raise under tz-aware `now`.
- The delegated `ae._get_closed_campaigns(work, period_start, period_end)`
  (`:184`) receives the already-normalized `work` + bounds ⇒ the probe
  still **faithfully delegates to the real pipeline** (no re-derivation;
  §A1 SAFETY CONTRACT intact). `_aggregate_campaigns(closed, 0.0)` (`:190`)
  unchanged. No new math, no Supabase, no mutation — purely the existing
  boundary fix mirrored.

Probe still delegates to the **fixed** `_get_closed_campaigns` (after §1.2 the
helper body is unchanged; both probe and engine feed it naive inputs).

---

## 4. Caller audit table

Every `compute_period_analytics` invocation (repo-wide, non-test):

| # | Call site (file:line) | `now` source / bounds | tz-aware in prod? | Covered by §1.2 single site? |
|---|---|---|---|---|
| 1 | `report_on_demand.py:112` | `datetime.now(sched.ISRAEL_TZ)` (`:97`) → `last_complete_*_ref` → `sched._weekly/_monthly_period` | **Yes** (tz-aware) | **Yes** — normalized at `analytics_engine.py:32-ish` (post-`:33`, pre-`:50`) |
| 2 | `report_scheduler.py:251` (`_run_weekly`) | `datetime.now(ISRAEL_TZ)` (`:553`) → `_run_weekly(now)` (`:562`) → `_weekly_period` (`:153`) | **Yes** (tz-aware) | **Yes** — same one site |
| 3 | `report_scheduler.py:363` (`_run_monthly`) | `datetime.now(ISRAEL_TZ)` (`:553`) → `_run_monthly(now)` (`:570`) → `_monthly_period` (`:162`) | **Yes** (tz-aware) | **Yes** — same one site |
| — | `report_open_book.py:12` | comment/docstring reference only — NOT a call | n/a | n/a |
| P | `period_data_probe.py:184` calls `_get_closed_campaigns` directly (NOT `compute_period_analytics`) | `datetime.now(sched.ISRAEL_TZ)` (`build_probe_report:301`) | **Yes** (tz-aware; original RAISE surface) | **No** — covered by the **mirrored §3 patch** |

Test callers (`tests/test_real_data_april_regression.py:77,93`;
`tests/test_sprint21_wave2.py`) pass tz-naive bounds today → §2 no-op; the
NEW tz-aware tests (§5) exercise the fix.

**Conclusion:** the three production `compute_period_analytics` callers are ALL
fixed by the ONE §1.2 site (they share the engine path); the probe's direct
`_get_closed_campaigns` use is the only additional site and is fixed by the
single mirrored §3 patch. Two surgical edits total.

---

## 5. Test design

New file `tests/test_sprint22_tz_regression.py` (`⟨MARK: filename / test
ids / Israel tz constant — ZoneInfo("Asia/Jerusalem") vs the scheduler's
sched.ISRAEL_TZ⟩`). Reuses the LOCKED fixtures by import (`_april_df`,
`_weekly_df`, `_ACCT`) — does **not** copy or modify them.

1. **tz-aware == tz-naive regression (the contract).** Parametrize the locked
   April + weekly bounds over `{tz-naive, tz-aware Asia/Jerusalem}` (apply
   `.replace(tzinfo=ZoneInfo("Asia/Jerusalem"))` to the existing
   `datetime(2026,4,1)` / `datetime(2026,4,30,23,59,59)` /
   `datetime(2026,5,3)` / `datetime(2026,5,9,23,59,59)`). Assert the
   tz-aware run returns **EXACTLY** the locked numbers:
   - April: `campaigns_closed == 8`, `round(realized_pnl,2) == 180.49`,
     `win_rate ≈ 0.375`, `profit_factor ≈ 2.6262`, `excluded_count == 2`,
     `excluded_count_manual == 1`, `excluded_pnl_manual ≈ 69.34`,
     `excluded_count_algo == 1`, `excluded_pnl_algo ≈ -48.905`.
   - Weekly: `campaigns_closed == 0`, `excluded_count == 3`,
     `excluded_count_algo == 3`, `excluded_pnl_algo ≈ -37.234`,
     `excluded_count_manual == 0`.
   - Plus equality cross-check: `tz_aware_result == tz_naive_result` for the
     full metrics dict (`⟨MARK: full-dict equality vs key subset; NaN/inf
     handling for profit_factor==math.inf — compare via repr or explicit
     key list⟩`).
2. **Probe no-raise under tz-aware `now`.** Call
   `probe.build_probe_report("monthly", now=datetime.now(ZoneInfo(
   "Asia/Jerusalem")))` and `("weekly", ...)`; assert it returns a non-empty
   `str` and does **not** raise (regression for the original
   `Invalid comparison` surface). Add a fixed-`now` tz-aware variant
   (`datetime(2026,5,16,12, tzinfo=ZoneInfo("Asia/Jerusalem"))`) asserting
   the block still produces the honest header/lines (faithful delegation).
   `⟨MARK: assert the probe's `n_closed`/`n_sell` under tz-aware now equals
   the tz-naive-now values for the same window (faithfulness), or just
   assert no-raise + non-empty.⟩`
3. **Byte-identical naive-path guard.** Assert the tz-naive April + weekly
   results equal a snapshot captured WITHOUT the patch semantics (i.e. the
   normalization helper is identity on naive input): compare the metrics
   dict produced by `compute_period_analytics` with the locked numbers AND
   assert `_to_naive(datetime(2026,4,1)) is datetime(2026,4,1)`-equivalent
   (returns an equal, tz-naive value; no shift). This is the explicit
   "entire suite stays 1846 & byte-identical" sentinel.
4. **#1 honest-empty still DISTINCT from the tz fix.** Assert
   `compute_period_analytics(pd.DataFrame(), aware_start, aware_end, _ACCT)`
   and `(None, ...)` still return the honest `_empty()` shape
   (`campaigns_closed == 0`, `ok True`, `unlinked_count == 0`) — i.e. a
   genuinely empty/None fetch is STILL an honest empty, NOT masked or
   fabricated by normalization, and NOT conflated with the tz bug (a real
   non-empty df under tz-aware bounds now yields the true non-zero numbers,
   per test 1; an empty df still yields honest empty). The WS-A
   honest-"input ריק/כשל" probe branch (`period_data_probe.py:151-157`) is
   unaffected — assert it still triggers on a `None`/empty fetch under
   tz-aware `now`.

**Regression coverage to keep green (no edits to these):**
- LOCKED `tests/test_real_data_april_regression.py` — byte-identical (§2).
- `tests/test_sprint21_wave2.py` (28 tests) — probe still passes; the §3
  mirror is identity on the existing tz-naive `now=datetime(2026,5,16,12)`
  inputs those tests use.
- Sprint-16..21 suites + WS-B `unlinked_*` keys + commits `920be95`,
  `bcf32f5` behaviour intact (no math/render/period change).
- Baseline full suite **1846** → expected **1846 + new tz tests** (all green).

### Explicit "will NOT change" list

- R / NAV / Expectancy / Win-Rate / Profit-Factor / net_r / campaign
  aggregation math — untouched (boundary-only normalization, §2 no-op).
- AGENTS.md invariant **#8** (ALGO_OBSERVED / DATA_INCOMPLETE never in
  WR/Expectancy) — untouched; partition predicates unchanged.
- AGENTS.md invariant **#1** honesty — strengthened, never weakened
  (honest-empty stays distinct, §5.4).
- **WS-C** (`initial_stop` vs `initial_risk_price`) — stays **DEFERRED**,
  not reopened (`⟨MARK: confirm WS-C remains deferred⟩`).
- Telegram admin gate, `telegram_bot_secure_runner.py`, `telegram_bot.py`
  (no wholesale rewrite), Supabase migrations (`verify_migrations` stays
  005), `docker-compose.yml` service commands — all untouched.
- Sprint-16..21 disclosure, WS-B `unlinked_*` namespace, `920be95`,
  `bcf32f5` — all preserved.
- No Supabase write / `snap_save` / scheduler-state mutation introduced.

---

## 6. Open `⟨MARK⟩` items (blocking Wave-2 build)

1. `⟨MARK⟩` Normalization **direction**: strip-tz / wall-clock-preserve
   (default-pending-Mark) vs convert-to-UTC. Design forbids any clock shift
   (would be a campaign-aggregation change).
2. `⟨MARK⟩` Series path: `tz_localize(None)` vs `tz_convert(None)` (no-op in
   suite either way; ratify for future tz-aware DB column).
3. `⟨MARK⟩` `_get_closed_campaigns` internal guard: none (default) vs
   defensive idempotent re-normalization.
4. `⟨MARK⟩` Probe: reuse `ae._to_naive` (default) vs probe-local copy.
5. `⟨MARK⟩` Test ids / filename / Israel-tz constant / equality-assertion
   granularity (full dict vs key subset; `math.inf` handling).
6. `⟨MARK⟩` Confirm WS-C DEFERRED + #8 untouched in the binding ruling.

No Wave-2 code until `MARK_SPRINT22_RULINGS.md` resolves §6.
