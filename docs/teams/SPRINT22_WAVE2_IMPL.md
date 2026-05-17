# Sprint-22 Wave-2 — Implementation (single-point tz-normalization)

**Date:** 2026-05-16 · **Branch:** `claude/review-system-audit-FBZ2h`
**Authority:** DEC-20260516-019 · gate: `MARK_SPRINT22_RULINGS.md` §6 (12/12)
**Build engineer:** Sprint-22 Wave-2. NO git commit/push (parent consolidates).

PROVEN root cause (re-reproduced before edit, `_april_df()` through the REAL
`compute_period_analytics`): tz-**naive** bounds → **8 / +$180.49**; tz-**aware**
bounds → **0 / $0.00** silent all-False, no raise. The prior "engine PROVEN on
real data" claim held ONLY on the tz-naive path — **production never exercised
the proven path until this fix** (Mark §3 #1, stated plainly).

---

## 1. File:line per change (all additive — `git diff` shows ZERO removed lines)

### `analytics_engine.py`
- **`:357-378` — NEW pure helper `_to_naive(ts)`** (Internals section, directly
  above `_get_closed_campaigns:380`). Strips tzinfo via `ts.replace(tzinfo=None)`
  when `getattr(ts, "tzinfo", None) is not None`; otherwise returns `ts`
  **unchanged (identity)**. NO clock conversion, NO R/NAV/campaign/Expectancy/PnL.
- **`:55-59` — the ONE normalization site** inside `compute_period_analytics`,
  placed STRICTLY AFTER the `:31-33` numeric-coerce loop (which itself is after
  the `:30` `pd.to_datetime` coerce) and BEFORE the `:62` WS-B block:
  - `:56` `period_start = _to_naive(period_start)`
  - `:57` `period_end = _to_naive(period_end)`
  - `:58-59` `if getattr(df["trade_date"].dt, "tz", None) is not None: df["trade_date"] = df["trade_date"].dt.tz_localize(None)`
  The `:26` `df is None or df.empty` honest-empty guard is UNTOUCHED and precedes
  this site (the block sits at ≥`:55`).

### `period_data_probe.py`
- **`:170-188` — mirrored normalization** in `_window_block`, placed AFTER the
  `:164` `pd.to_datetime` coerce + `:165-168` numeric loop, and BEFORE the first
  comparison (`td = work["trade_date"]` at `:190`, `sells_in :199-200`,
  `ae._get_closed_campaigns :206`, `in_win :216-217`):
  - `:185` `period_start = ae._to_naive(period_start)`
  - `:186` `period_end = ae._to_naive(period_end)`
  - `:187-188` `if getattr(work["trade_date"].dt, "tz", None) is not None: work["trade_date"] = work["trade_date"].dt.tz_localize(None)`
  Reuses `ae._to_naive` (single source of truth — Mark §4). Sits AFTER the
  `:151-157` honest "input ריק/כשל" empty/fail branch.

### `tests/test_sprint22_tz_regression.py` — NEW (18 net-new tests)
Reuses LOCKED `_april_df`/`_weekly_df`/`_ACCT` by import; no copy/modify.
Classes: `TestSprint22TzAwareEqualsNaive` (§2 — param naive/aware locked numbers
+ full-dict equality + scheduler `ISRAEL_TZ` constant), `TestSprint22NoOpProof`
(§1.5 — `_to_naive` identity `is`, wall-clock-preserve, byte-identical sentinel),
`TestSprint22AntiMaskingHonestEmpty` (§3 #1 — empty/None df under tz-aware bounds
still honest `_empty()`; real non-empty zero stays honest with disclosure),
`TestSprint22ProbeMirrored` (§4 — no raise under tz-aware `now`; shared helper).

### `tests/test_sprint19_headline_comparison.py` — guard allowlist EXTENDED
`test_analytics_engine_git_diff_empty` is the per-sprint diff-allowlist meta-test
(already carries Sprint-20 + Sprint-21 extensions). Extended to admit the
Mark-authorized Sprint-22 region by deriving the AUTHORIZED added-line set from
the live `analytics_engine.py` between documented anchors (the `_to_naive`
helper span + the `Sprint-22 (DEC-20260516-019` block span). NOT the LOCKED
test — `tests/test_real_data_april_regression.py` is byte-identical/untouched.
This mirrors the established precedent (Sprint-20/21 each extended `_ALLOWED`).

---

## 2. ⟨MARK⟩ slots filled (from `MARK_SPRINT22_RULINGS.md` — invented nothing)

| Design ⟨MARK⟩ | Mark ruling | Applied |
|---|---|---|
| §6.1 direction | §1.1: normalize BOTH to tz-NAIVE | `_to_naive` strips tzinfo |
| §6.1 wall-clock | §1.1: strip (`replace(tzinfo=None)`), NEVER `astimezone` | no clock shift |
| §6.2 Series path | §1.2.2: `dt.tz_localize(None)` defensive guard | `:58-59` / probe `:187-188` |
| §6.3 `_get_closed_campaigns` guard | §1.4: NOT required, NOT added | helper body byte-identical |
| §6.4 probe helper | §4: reuse `ae._to_naive` | probe `:185-186` |
| §6.5 test ids/tz | §2/§5: `ZoneInfo("Asia/Jerusalem")` + `sched.ISRAEL_TZ`; full-dict equality (PF finite 2.6262) | new test file |
| §6.6 WS-C / #8 | §5: WS-C DEFERRED, #8 untouched | no campaign-math touched |

---

## 3. No-op proof for already-naive inputs (Mark §1.5 — byte-identical)

1. **Bounds.** `_to_naive(ts)` with `ts.tzinfo is None`: the
   `getattr(ts,"tzinfo",None) is not None` condition is **False** → `return ts`
   → the SAME object flows downstream (proven by
   `test_to_naive_identity_on_naive`: `ae._to_naive(d) is d`).
2. **Series.** Entire suite + LOCKED regression build `trade_date` from naive
   strings → `pd.to_datetime` yields tz-naive `datetime64[ns]` →
   `df["trade_date"].dt.tz` is `None` → the `tz_localize(None)` branch **never
   executes** → identical Series object.
3. ⇒ zero reassignment → every boolean mask, `closed_trades`, `campaigns`,
   `countable`/`excluded`/`manual` partition, WR/PF/Expectancy/R/`unlinked_*`
   is bit-for-bit unchanged. **Full suite 1846 + LOCKED regression
   byte-identical** (verified: `1864 passed, 0 failed`; the Sprint-19
   byte-identical guard + `test_naive_path_byte_identical_to_locked_numbers`
   pass; LOCKED `test_real_data_april_regression.py` assertions UNCHANGED).

---

## 4. tz-aware == tz-naive evidence

Verified pre-doc and via the new suite:
- April: tz-aware bounds → `campaigns_closed==8`, `round(realized_pnl,2)==180.49`,
  `win_rate≈0.375`, `profit_factor≈2.6262`, `excluded_count==2`
  (`_manual 1`/`_algo 1`), AND `aware == naive` over the FULL metrics dict.
- Weekly: tz-aware → `campaigns_closed==0`, `excluded_count==3`,
  `excluded_count_algo==3`, AND full-dict `aware == naive`.
- Real prod tz object: `sched.ISRAEL_TZ` bounds → 8 / equal-to-naive.

---

## 5. #1 anti-masking proof (empty guard precedes normalization — Mark §3)

`analytics_engine.py:26` `if df_trades is None or df_trades.empty: return
{**_empty(), ...}` executes BEFORE the `:55` normalization block. An empty/None
fetch short-circuits to the honest `_empty()` path and NEVER reaches `_to_naive`
— the two concerns never interact. Verified under tz-AWARE bounds:
`test_empty_df_under_tz_aware_bounds_is_honest_empty` /
`test_none_df_under_tz_aware_bounds_is_honest_empty` →
`campaigns_closed==0, ok True, unlinked_count==0`. A genuine non-empty "0
campaigns" (all-ALGO weekly) stays a legitimate honest zero WITH
`excluded_count==3` disclosure (`test_real_nonempty_zero_stays_honest_zero...`)
— NEVER conflated with the empty/failed-fetch branch. Probe `:151-157` honest
"input ריק/כשל" branch precedes the `:185` mirror identically.

---

## 6. Caller-coverage confirmation (one engine site fixes all)

`compute_period_analytics` callers (repo-wide, non-test): `report_on_demand.py:112`,
`report_scheduler.py:251`, `:363` — all tz-aware in prod via
`datetime.now(ISRAEL_TZ)` → `_weekly/_monthly_period`. All three share the ONE
engine path → the single `:55` site rebinds the local `period_start`/`period_end`
consumed by the WS-B unlinked filter (`:65-66` post-renumber) AND passed at
`:83` to `_get_closed_campaigns(df, period_start, period_end)` (transitive — no
helper edit). `period_data_probe.py:206` calls `_get_closed_campaigns` directly
(not via `compute_period_analytics`) → covered by the mirrored `:185` probe
block. `_aggregate_campaigns` does Timestamp−Timestamp on normalized `df` only
(naive−naive) — untouched. Two surgical edits total; `_get_closed_campaigns`
body byte-identical (Mark §1.4 / gate item 1).

Probe no-raise verified: `build_probe_report("weekly"/"monthly",
now=datetime.now(sched.ISRAEL_TZ))` returns non-empty `str`, NO `Invalid
comparison` raise (the original probe defect surface).

---

## 7. Test delta

Baseline `1846 passed`. Post-fix `1864 passed, 0 failed` (= 1846 + 18 net-new
Sprint-22 tz tests; Sprint-19 guard allowlist extended, still passing). Drift +
migration tests green; `verify_migrations` stays 005. LOCKED
`test_real_data_april_regression.py` + `test_sprint21_wave2.py` byte-identical
and green.

---

## 8. Untouched (Mark §5 — confirmed)

NO R/NAV/Expectancy/`_aggregate_campaigns`/`get_campaign_risk_metrics`/
`classify_stat_bucket`/WR/PF/Net-R change — only datetime operands normalized.
#8 ALGO segregation + WS-B `unlinked_*` namespace byte-identical (weekly still
`excluded_count_algo==3`). WS-C DEFERRED, NOT reopened (no `initial_risk_price`
fallback; April `excluded_count==2`). 920be95 / bcf32f5 / Sprint-16..21 / admin
gate / `telegram_bot_secure_runner.py` intact. NO migration / `docker-compose.yml`
/ `telegram_bot.py` wholesale change. Single-user, host-agnostic, zero-billing.
