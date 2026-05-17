# Sprint 17 — Architecture + Engine Design (ALGO Governance)

**Date:** 2026-05-16
**Branch:** `claude/review-system-audit-FBZ2h`
**Team:** Architecture + Engine (combined)
**Status:** DESIGN ONLY — no production code, no commit, no migration. Gated on `MARK_SPRINT17_RULINGS.md` (parallel; absent at authoring time → every threshold/label/wording is a verbatim `⟨MARK:…⟩` slot, none invented).
**Authoritative inputs read:** `ALGO_REFERENCE_2026_05_16.md` (§1 rules, §2 stats, §6 Governor), `SPRINT17_PLAN.md`, `DECISIONS.md` DEC-20260515-014 / -004, DEC-20260511-001, `CLAUDE.md`, `AGENTS.md` (#1, #8).

> **Backtest caveat carried into every surface (AGENTS.md #1, REFERENCE preamble).** All §2/§6 numbers are TrendSpider backtest, %-per-trade, **no commissions, no slippage, no real capital allocation**. No surface designed here presents them as live account truth; every ALGO-cohort readout carries an explicit `⟨MARK: backtest-caveat wording⟩` disclosure line.

---

## 0. Constraints honored (the "will NOT change" list)

This design changes **none** of:

- Engine R / NAV / campaign / exposure math (`compute_r_true:997`, `compute_r_target:1004`, `get_open_positions_campaign:473`, `compute_capital_at_risk_usd:1011`, freeze-risk:991) — read-only consumers only.
- Headline analytics (`analytics_engine.compute_period_analytics`) — **not touched**; #8 proven by construction (§2 below).
- `telegram_bot_secure_runner.py`, `docker-compose.yml` (`telegram-bot: python3 telegram_bot_secure_runner.py` stays), admin gating, anti-spam state machine.
- No Supabase schema / migration / `user_id` (single-user; Hyperscaler addendum confirms derived read-only, per-user cohort = deferred Phase-B touchpoint only).
- No new `_RULESET`, no §6 numeric constants invented in code — all thresholds are `⟨MARK⟩` slots traced to `ALGO_REFERENCE §6` or an existing constant.
- DEC-20260511-001 observer rule: ALGO never receives an instruction; max actionability `Review Required`; `evaluate_position_engine:457-467` and `compute_position_state:2008-2010` ALGO short-circuit (`suggested_stop=None`) is **preserved verbatim** — nothing here writes a stop or alters an ALGO trade.

**Risk classification:** #4 surfacing = **LOW** (static read-only lookup). ALGO-segregated metrics module = **MEDIUM** (new leaf, #8-critical → test-gated). Governor advisory surface = **MEDIUM** (reuses existing signals; new derived checks read-only). #5 dead-money = **LOW–MEDIUM** (reuses Open Tasks path, #8-safe). System/Infra note: **no infra/deploy change**; if any ALGO metric is persisted it reuses an existing local-JSON store (DEC-20260510-006 pattern) — no new volume/migration.

---

## 1. #4 — Replace "Unknown" stop/state with the §1 known per-symbol rule

### 1.1 Where ALGO emits "Unknown" today (pinpointed)

| Site | Behavior for ALGO | Why "Unknown" |
|---|---|---|
| `engine_core.evaluate_position_engine` **:457-467** | `action="מנוהל חיצונית — בקרה בלבד"`, `suggested_stop=None`, returns early before `build_management_action` | observer short-circuit — no stop surfaced at all |
| `engine_core.compute_position_state` **:2008-2010** | returns `POSITION_STATE_ALGO_OBSERVED` before DEAD_MONEY/PROVING/etc. | state collapses to one label; no per-symbol logic |
| `engine_core.classify_risk_basis` **:280-281** | `Target` if `target_risk_usd>0` else `Unknown` | binary; never reflects "QQQ/HOOD have no hard stop by design" |
| `engine_core.compute_risk_visibility_score` **:298-299** | `40` or `20` | by-design cap (DEC-014 notes `<70` is vacuous) |
| `telegram_tasks.py` **:208-222** `_algo_observed` | `external_stop = sl if sl>0 else None`; `risk_basis` from above | renders "Unknown" / no stop in the ALGO panel |
| `risk_monitor._algo_visibility_alert` **:394-402** | "score 40 = normal for ALGO (no known stop)" | already honest, but generic — not per-symbol |

**Root cause:** ALGO is correctly *not managed*, but the engine has **no per-symbol knowledge of the ALGO's own risk control** (QQQ/HOOD = no hard stop, time-exit controlled; TSLA −4.3%; JPM −3.3%; PLTR −25% emergency cushion). "Unknown" is technically wrong — the rule is *known*, it is just not Sentinel's.

### 1.2 Design — read-only per-symbol known-rule lookup

New **pure leaf**, no imports of bot/supabase/engine-state, observation-only (DEC-20260511-001 — never an instruction):

```
algo_rules.py   (NEW leaf module — static data + pure lookup, no I/O)

ALGO_KNOWN_RULES = {            # values are ⟨MARK⟩ slots, sourced from §1 ONLY
  "QQQ":  {"hard_stop": None, "stop_kind": ⟨MARK: QQQ stop label "אין סטופ קשיח — נשלט ביציאות-זמן"⟩,
           "time_exits": ⟨MARK: §1 QQQ "3c<−2% · 33c<0% · 46c<1.7% · 90c<11%"⟩,
           "tp": ⟨MARK: "+11%"⟩, "tech_exit": ⟨MARK: "SMA16↓SMA51"⟩},
  "TSLA": {"hard_stop_pct": ⟨MARK: −4.3⟩, "stop_kind": ⟨MARK: "סטופ קשיח"⟩, "time_exits": None, ...},
  "JPM":  {"hard_stop_pct": ⟨MARK: −3.3⟩, ...},
  "HOOD": {"hard_stop": None, "stop_kind": ⟨MARK: "אין סטופ קשיח — נשלט ביציאות-זמן"⟩,
           "time_exits": ⟨MARK: §1 HOOD "10c<4% · 65c<25% · 85c<40%"⟩, ...},
  "PLTR": {"emergency_cushion_pct": ⟨MARK: −25⟩, "stop_kind": ⟨MARK: "כרית חירום — לא סטופ ניהולי"⟩,
           "time_exits": ⟨MARK: §1 PLTR "230c if loss>14.8% · 295c if loss>12%"⟩, ...},
}

def get_algo_known_rule(symbol) -> dict | None      # exact-match only; unknown symbol → None
def describe_algo_risk_control(symbol) -> str        # one honest Hebrew line, ⟨MARK⟩ wording
```

**Surfacing (additive, observation-only):**

- **ALGO panel** (`telegram_tasks.handle_algo_panel:747`, `_algo_observed:212`): when `risk_basis`/`external_stop` would be "Unknown", instead render `describe_algo_risk_control(sym)` — e.g. QQQ → `⟨MARK: "QQQ: אין סטופ קשיח; נשלט ביציאות-זמן (3c<−2% …). מנוהל חיצונית — תיאור בלבד."⟩`. Stays under the existing mandatory non-binding header (`handle_algo_panel:786-791`); adds **no** task, no `suggested_stop`, no imperative verb.
- **Position view / AI context**: same lookup string in the ALGO block; never replaces a real broker stop if ALGO exposes one (`external_stop` precedence unchanged).
- **`risk_monitor._algo_visibility_alert:394`**: optionally append the per-symbol descriptor (`⟨MARK⟩` decides include/omit) — does not change the alert trigger.

**Invariants:** purely descriptive ("Sentinel sees the ALGO uses rule X"), never "do X"; symbol unknown → keep existing "Unknown" (never fabricate a rule); does not touch `classify_risk_basis`/`compute_risk_visibility_score` math (DEC-014 keeps the 40-cap by design).

---

## 2. ALGO-segregated metrics module — the #8 crux (proof by construction)

### 2.1 The construction-level isolation argument

Headline WR/Expectancy lives ONLY in `analytics_engine.compute_period_analytics`. Its edge stats already filter `countable = campaigns[bucket.apply(ec.is_stat_countable)]` (`analytics_engine.py:53`), and `is_stat_countable` returns **False for `STAT_BUCKET_ALGO`** (`engine_core.py:1263`). ALGO is therefore *already* excluded from the headline path.

**The #8 proof is by physical separation, not by a flag:**

1. The new module is a **separate file** (`algo_metrics.py`), a **separate function** (`compute_algo_cohort_metrics`), over a **separate cohort** built by an **inverse filter**.
2. The cohort filter is the *exact logical complement* of the headline filter, reusing the SAME predicate so they can never diverge:
   - Headline cohort: `is_stat_countable(bucket) == True` → ALGO impossible.
   - ALGO cohort: `bucket == ec.STAT_BUCKET_ALGO` (i.e. `is_algo_position` true) → manual impossible.
   - The two sets are **provably disjoint and exhaustive over the ALGO/non-ALGO partition** — reusing `engine_core.is_stat_countable` / `is_algo_position` / `classify_stat_bucket` (no new classification).
3. `analytics_engine.py` is **not edited**. It never imports `algo_metrics`. The headline path literally cannot see an ALGO trade because (a) it filters them out at :53 and (b) the new module is downstream and never feeds back.
4. `algo_metrics` returns its own dict; **no caller merges it into the headline analytics dict**. The Governor (§3) and panels read it as a *separate observer metric* — never summed with `win_rate`/`expectancy_r`.

### 2.2 Module shape (NEW leaf — read-only, pure)

```
algo_metrics.py   (NEW — imports only engine_core helpers + pandas; no bot/supabase/analytics)

def build_algo_cohort(df_trades) -> pd.DataFrame:
    # Reuse engine_core.get_open_positions_campaign / the same campaign
    # aggregation analytics uses, then keep ONLY:
    #   stat_bucket == ec.STAT_BUCKET_ALGO   (== is_algo_position true)
    # Closed campaigns only; chronological by close date.
    # Source = the SAME Supabase trades read the headline path uses (read-only),
    # so the cohort is the inverse slice of the same universe.

def compute_algo_cohort_metrics(df_trades, window=⟨MARK: 20–30, DEC-014 / §6 "last 10/20-30"⟩) -> dict:
    # Rolling over the last `window` closed ALGO campaigns:
    #   profit_factor       gross_win / gross_loss   (same formula shape as analytics:96-98, NOT shared code)
    #   expectancy_r        wr*avg_win_r + (1-wr)*avg_loss_r  (same shape, separate computation)
    #   loss_streak         max consecutive losing ALGO campaigns
    #   pf_last_10          PF over last ⟨MARK: 10⟩  (§6 "PF of last 10 < 1")
    #   sum_last_5_pct / sum_last_10_pct   (§6 "last 5 negative >7.5%", "last 10 negative >10%")
    #   trading_year_pnl    current-year ALGO P/L sign  (§6 "current trading-year negative")
    # Returns a SELF-CONTAINED dict, namespaced keys (algo_pf, algo_expectancy_r, …).
    # Caveat field always present: {"basis":"backtest","caveat": ⟨MARK: caveat line⟩}
```

**Cohort source:** the same `trades` table read the headline uses, sliced to `STAT_BUCKET_ALGO`. **Window:** `⟨MARK: 20–30⟩` (DEC-014 trigger #2/#3; §6 also names "last 10" and "last 5" — module exposes all; Mark picks the canonical rolling window and the secondary windows).

**Fixtures available now (§2 real backtest):** per-ALGO Trades/Win%/PF/avg-loss/max-loss-streak/last-5/last-10, aggregate (232 trades, PF 3.48, R/R 3.54, max streak 12), §3 regime-by-year (2026: 27 trades, 18.5%, PF 0.73). These become test fixtures (§5).

---

## 3. Governor as an advisory surface (`Review Required` only — never instructs ALGO)

The Governor is an **observer overlay** that withholds the *founder's own* discretionary size-up/new-asset/exposure-up (DEC-014 locked structure); it emits at most `Review Required`, never `Action Required`, never an ALGO instruction (DEC-20260511-001).

### 3.1 §6 trigger → existing signal reuse map (no duplication, no new math)

| §6 trigger (REFERENCE §6) | Reuse / source | New? |
|---|---|---|
| PF last 10 < ⟨MARK:1⟩ | `algo_metrics.pf_last_10` (§2) | derived read-only |
| last 5 negative > ⟨MARK:7.5%⟩ | `algo_metrics.sum_last_5_pct` | derived read-only |
| last 10 negative > ⟨MARK:10%⟩ | `algo_metrics.sum_last_10_pct` | derived read-only |
| 6-loss streak → Yellow / 8 → Red | **REUSE** `risk_monitor._algo_loss_streak_alert:377` + `algo_loss_streak` state (:881-897, currently 3/5 runs). ⟨MARK⟩ maps §6 *trade-count* streak (6/8) onto `algo_metrics.loss_streak` (campaign-based) vs the existing *run-based* monitor streak — keep distinct, do not redefine the existing one. | reuse + cite |
| current trading-year negative | `algo_metrics.trading_year_pnl` sign (§3 regime) | derived read-only |
| open > ⟨MARK:7/10/15/20%⟩ ladder | **REUSE** `risk_monitor` profit checkpoints (`PROFIT_CHECKPOINTS:56`), RUNNER state (`POSITION_STATE_RUNNER`), `_runner_state_alert:285` | reuse + cite |
| giveback > ⟨MARK:50%⟩ of peak | **REUSE** `engine_core.compute_giveback_from_peak:866` + `risk_monitor` Giveback monitor (:516-519, `GIVEBACK_RANK:55`) | reuse + cite |
| cluster > ⟨MARK:30%⟩ block new full-size | **REUSE** `risk_monitor` cluster machinery (:950-978, `ALGO_CLUSTER_WARNING_PCT=30`, `ALGO_CLUSTER_CRITICAL_PCT=35`) | reuse + cite |
| QQQ below key daily MAs → reduce aggressive | new derived check, read-only from existing history fetch (`ec.get_cached_history`) — observation only | new (read-only) |
| PLTR&HOOD / TSLA&PLTR open together | **Cluster-Risk** computed read-only from existing exposure data (see 3.2) | new (read-only) |

### 3.2 Cluster-Risk (read-only from existing exposure data)

Computed from the **already-collected** per-position exposure in `risk_monitor` (`total_algo_exposure`, per-symbol `pos_value` :621-647) and `get_open_positions_campaign` — **no new exposure math**, no new fetch. Derives: total ALGO cluster %, concurrent-pair flags (PLTR&HOOD, TSLA&PLTR), QQQ-below-MA flag. Output is a single advisory string `⟨MARK: "Review Required — אשכול ALGO …"⟩`; thresholds = `⟨MARK⟩` traced to §5 cluster cap (≤25 OK / 25–30 caution / >30 no new full-size / >35 Critical) and existing `ALGO_CLUSTER_*` constants.

**Output contract:** the Governor produces a `governor_state` dict consumed by the Telegram advisory surface (the ALGO panel and/or a `Review Required` line) — it **never** writes a stop, never emits an ALGO `Task`, never an `Action Required`, never feeds analytics. Reuses the existing anti-spam/cooldown state pattern (`risk_monitor` per-key cooldowns, DEC-20260510-002/-007) — no new recurring alert without per-key dedup (AGENTS.md #7).

---

## 4. #5 — Strategy-adaptive ALGO dead-money (from §1 time-exits)

**Problem:** `compute_position_state:2008-2010` returns `ALGO_OBSERVED` *before* the generic `DEAD_MONEY` branch (:2053-2061, `_DEAD_MONEY_MAX_R=0.75` etc., `engine_core.py:1696-1699`). ALGO therefore never gets a "not working" signal, and the *generic* discretionary dead-money rule would be **wrong** for ALGO (its non-working signal is its own §1 time-exit, not 8-days/0.75R).

**Design:** a read-only per-symbol "ALGO dead-money" derived from `algo_rules.get_algo_known_rule(sym).time_exits`:

- For symbols with §1 time-exits (QQQ, HOOD, PLTR): compute, read-only, whether the position's age/return has reached its **own** time-exit checkpoint (e.g. PLTR `⟨MARK: 230c if loss>14.8%⟩`). Inputs = existing features already computed (`days_held`, open R/%, `time_efficiency:192`) — **no new math**.
- For symbols with a hard stop and no time-exit (TSLA, JPM): the §1 hard stop is the control → **no ALGO dead-money signal** (avoid false "dead" labels; honest).
- **Surface:** the existing Open Tasks / alert path — folded into the **consolidated ALGO panel** (`handle_algo_panel`, DEC-20260515-006), as an additional observation-only line under the mandatory non-binding header. **Distinct** from generic `_DEAD_MONEY_MAX_R`: a separate `algo_dead_money` flag, `task_type` stays `ALGO_OBSERVE_ONLY` (never a real `Task`, never counted — `telegram_tasks.py:446-457` consolidation preserved).

**#8-safety:** observation-only; never creates a countable campaign; ALGO cohort stays in `algo_metrics`, never headline. Wording `⟨MARK: "Sentinel רואה: לפי חוקי ה-ALGO ל-PLTR, יציאת-זמן … — תיאור, לא הוראה"⟩`.

---

## 5. Wave-2 Test Plan

**Baseline: 1676 tests collected (verified), drift green required.** All new tests additive; no existing test modified.

### 5.1 #8-isolation guard (the critical test)

- `test_headline_byte_identical_with_without_algo`: build a manual-only trades DF; compute `analytics_engine.compute_period_analytics`. Inject ALGO campaigns (QQQ/TSLA/PLTR rows). Re-compute. Assert **every headline field byte-identical**: `win_rate`, `expectancy_r`, `profit_factor`, `avg_win_r`, `avg_loss_r`, `total_r_net`, `realized_pnl`, `best_trade`, `worst_trade`, `setup_breakdown`, `campaigns_closed`. (Exact equality, not approx.)
- `test_algo_cohort_is_complement`: assert `build_algo_cohort` ∩ headline `countable` = ∅, and union over the ALGO partition = all campaigns (reuse `is_stat_countable`/`is_algo_position` — disjoint & exhaustive).
- `test_analytics_engine_does_not_import_algo_metrics`: static import-graph assertion (the construction proof).

### 5.2 Founder real-number fixtures (§2 / §3 / §6)

- Per-ALGO fixtures from §2: QQQ (98 tr, WR 46.9%, PF 2.29, streak 7, last-5 +3.35%), TSLA (49, 38.8%, 2.45, last-10 +12.24%), JPM (33, 57.6%, 4.23, streak 3), HOOD (34, 52.9%, 7.13), PLTR (18, 72.2%, 4.01, streak 2, last-5 −29.86%); aggregate (232 / PF 3.48 / R/R 3.54 / max streak 12); §3 2026 regime (27 tr, 18.5%, PF 0.73). Assert `compute_algo_cohort_metrics` reproduces PF / loss-streak / last-5 / last-10 / trading-year-negative on these fixtures (tolerances `⟨MARK⟩`).
- §6 trigger fixtures: PF-last-10<1, last-5<−7.5%, last-10<−10%, 6/8 loss streak, year-negative → assert Governor sets the right `Review Required` flag (values `⟨MARK⟩`).

### 5.3 Advisory-not-instruction assertions

- `test_governor_never_action_required`: every Governor output ∈ {none, `Review Required`}; never `Action Required`; never a `suggested_stop`; never an ALGO `Task` (`task_type` stays `ALGO_OBSERVE_ONLY`, `info_only`).
- `test_algo_engine_shortcircuit_preserved`: `evaluate_position_engine` ALGO path still `suggested_stop=None`, `compute_position_state` still returns `ALGO_OBSERVED` first (regression guard on :457-467 / :2008-2010).
- `test_known_rule_no_imperative`: `describe_algo_risk_control` / #5 strings contain no imperative verb; unknown symbol → still "Unknown" (no fabricated rule).

### 5.4 Backtest-caveat presence

- `test_algo_metrics_carry_caveat`: every `compute_algo_cohort_metrics` / panel readout includes the `⟨MARK: backtest-caveat⟩` line; assert no surface presents a §2 number without it (AGENTS.md #1).

---

## 6. ⟨MARK⟩ slot index (Mark fills; engineering invents none)

| # | Slot | Source anchor |
|---|---|---|
| M1 | §1 per-symbol stop/time-exit labels & Hebrew wording (QQQ/TSLA/JPM/HOOD/PLTR) | REFERENCE §1 |
| M2 | "no hard stop → time-exit controlled" exact phrasing | §1 key note |
| M3 | Rolling window (20–30) + secondary windows (last 10 / last 5) | DEC-014 / §6 |
| M4 | §6 decay thresholds (PF<1, −7.5%, −10%, 6/8 streak, year-negative) | §6 decay table |
| M5 | §6 open-profit ladder (7/10/15/20%, giveback 50%) ↔ existing checkpoint/RUNNER/Giveback mapping | §6 open-profit |
| M6 | §6 cluster thresholds ↔ `ALGO_CLUSTER_*` + §5 cap bands | §6 cluster / §5 |
| M7 | Loss-streak reconciliation: §6 trade-count (6/8) vs existing run-based monitor (3/5 runs) | §6 + `risk_monitor:881-897` |
| M8 | Backtest-caveat disclosure wording (#1) | REFERENCE preamble |
| M9 | #5 ALGO dead-money Hebrew readout wording | §1 / DEC-006 |
| M10 | Test tolerances for §2 fixtures | §2 |

---

## 7. Deployment / rollback (no production behavior change in this design)

Design only — nothing ships this sprint (DEC-014: NOT built until Mark-gated tuning + founder re-confirmation). When Wave-2 builds: additive new leaves (`algo_rules.py`, `algo_metrics.py`) + read-only consumers; rollback = revert the two new files + their wiring; no migration, no docker-compose/secure_runner change, headline analytics provably untouched. System/Infra: no infra/deploy change; any optional persistence reuses an existing local-JSON store (DEC-20260510-006), no new volume.
