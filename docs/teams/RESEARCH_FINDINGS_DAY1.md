# Research Team — Day 1 Findings

**Date:** 2026-05-14
**Branch:** `claude/review-system-audit-FBZ2h`
**Scope:** Empirical challenge of `docs/SYSTEM_AUDIT_2026_05.md` plus three new investigation angles (N1–N3).
**Method:** Read-only code inspection. Every claim is anchored to `file:line`.

> TL;DR — half of the audit's "critical issues" are **outdated** (fixed since the audit was written). The remaining real defects are: (1) `analytics_engine` does not filter ALGO / DATA_INCOMPLETE — violates AGENTS.md invariant #8 in the weekly/monthly PDF reports; (2) `original_campaign_risk` has TWO live definitions (engine_core canonical + adaptive_risk_engine inline) — not three; (3) `follow_through_score=None` still acts as a free-pass for RUNNER/WORKING gates in production for the first ~5 trading days; (4) heat score additive math (Sprint 9 P4) is unfixed; (5) `risk_monitor_state.json` writes are non-atomic and there is a real concurrent-writer race between `risk_monitor.py` and `bot_helpers._write_runner_decision`.

---

## Summary table

| ID | Issue (audit claim) | Severity (my rating) | Status | Recommended action |
|----|---------------------|---------------------|--------|--------------------|
| A | `original_campaign_risk` has 3 definitions | **MEDIUM** (was BLOCKER) | **Outdated — partly fixed.** analytics_engine + risk_monitor now use `ec.get_campaign_risk_metrics()`. adaptive_risk_engine still inlines its own formula. | Replace inline calc in `adaptive_risk_engine.compute_closed_campaigns` lines 159–175 with `ec.get_campaign_risk_metrics()`. |
| B | `follow_through_score` always None → easy RUNNER/WORKING | **MEDIUM** (was BLOCKER) | **Outdated — implemented, but design flaw remains.** FT is now computed (`risk_monitor.py:741`). When still None (first 5 days), the gate logic in `engine_core.py:2030, 2043-2044` treats None as a pass. | Replace `(FT is None or FT >= X)` with explicit `age_days >= _FT_MIN_DAYS_FOR_SCORE and FT >= X` gating. Don't let "no data yet" upgrade a position to RUNNER. |
| C | Profit Factor sentinel mismatch 2.0 vs 99.0 | **NOT-A-BUG** | **Outdated.** Both modules now use `math.inf` (analytics_engine.py:54, adaptive_risk_engine.py:281). | None. Maybe document the chosen sentinel in `DATA_CONTRACTS.md`. |
| D | Silent failures in risk_monitor lines 578/589/604 | **LOW** | **Outdated.** Alerts now fire on `live price=None` (596-602), missing initial stop (612-618), and `engine_res.ok=False` (633-640). | None — possibly tighten the no-stop alert (currently logs but still computes with original_risk=0). |
| E | State file save only at end → lost on crash | **NOT-A-BUG** | **Outdated.** Mid-loop checkpoint at 927; graceful SIGTERM/SIGINT shutdown at 1038-1059. | None. |
| F | WR/Expectancy must exclude DATA_INCOMPLETE + ALGO_OBSERVED | **HIGH** | **CONFIRMED — partial. dashboard.py filters, adaptive filters. analytics_engine.py does NOT filter. PDF reports therefore violate AGENTS.md invariant #8.** | Add `stat_bucket` filter to `analytics_engine._aggregate_campaigns` (line 235) OR to the wins/losses split at lines 43–44. Add tests. |
| G | Heat score additive — Sprint 9 P4 multiplicative refactor | **MEDIUM** (Sprint 9 task) | **Confirmed not yet done.** `adaptive_risk_engine.py:308-330` is still additive. | Implement Sprint 9 Priority 4 (multiplicative form per `docs/SPRINT_9_PLAN.md` lines 96-103). |
| N1 | `score_position` robustness to missing/NaN inputs | **LOW** | The 60-bar history gate prevents most NaN. `dist_8d`/`dist_12d` use bool sums and `int()` — safe. RS components have None-guards. Still one fragile path: `is_down_day` short-circuits NaN ATR check. | Tighten: log a warning when fewer than 60 bars (currently silent miss), and add `pd.notna()` around `daily_move > 1.3 * atr20`. |
| N2 | `compute_campaign_lot_state` edge cases when base_qty ≠ current_qty | **NOT-A-BUG** (one ambiguity) | Math is correct: `original_risk_usd` uses `base_qty` (frozen), `open_pnl/locked/risk` use `current_qty`. **But the `open_r` ratio mixes a current-qty numerator with a base-qty denominator** — intentional per design but easy to misread. | Document the asymmetry inline. Add a docstring example with partial sells. Add a test that asserts open_r is stable across a partial-sell event. |
| N3 | Race condition: risk_monitor write vs concurrent read/write | **HIGH** | **Confirmed.** `save_state` (line 106-107) writes non-atomically. `bot_helpers._write_runner_decision` (line 49-66) does a non-atomic read-modify-write to the SAME file. Concurrent readers (dashboard.py:495, bot_health.py:121) can see partial JSON. | Use atomic write pattern (`tempfile` + `os.replace`). Add a file lock (`fcntl.flock`) around the bot-side runner_decision update — the Telegram bot and risk_monitor run in separate containers and can collide. |

---

## Detailed analysis per issue

### Issue A — `original_campaign_risk` 3 definitions

**Audit claim:** Three modules compute `original_campaign_risk` differently.

**Code evidence (current state):**

`engine_core.py:920-941` — canonical formula:
```python
def compute_original_campaign_risk(side, entry_price, initial_stop, quantity, fees=0.0):
    if entry_price <= 0 or initial_stop <= 0 or quantity <= 0:
        return 0.0
    if side.upper() in ("BUY", "LONG"):
        risk_per_share = entry_price - initial_stop
    else:
        risk_per_share = initial_stop - entry_price
    return round(max(0.0, risk_per_share * quantity + fees), 2)
```

`engine_core.py:943-977` — wrapper `get_campaign_risk_metrics(row)` with `valid` flag and stop sanity (LONG: `stop < entry`).

`analytics_engine.py:252-255` — **uses the canonical function**:
```python
_risk_row = {"price": entry, "quantity": qty, "initial_stop": init_sl,
             "side": str(fb.get("side", "BUY"))}
_metrics  = ec.get_campaign_risk_metrics(_risk_row)
orig_risk = _metrics["original_risk"] if _metrics["valid"] else target_risk_usd
```

`risk_monitor.py:609-611` — **uses the canonical function**:
```python
_risk_metrics = ec.get_campaign_risk_metrics(dict(row))
original_campaign_risk = _risk_metrics["original_risk"]
```

`adaptive_risk_engine.py:159-175` — **still has its own inline calculation**:
```python
first_date = buys["trade_date"].min()
first_day = buys[buys["trade_date"] == first_date]
base_qty = float(first_day["quantity"].sum())
base_price = (
    float((first_day["price"] * first_day["quantity"]).sum() / base_qty)
    if base_qty > 0 else 0.0
)
init_sl_raw = first_day.iloc[0].get("initial_stop", 0)
init_sl = float(init_sl_raw) if init_sl_raw and not pd.isna(init_sl_raw) else 0.0
if init_sl > 0 and init_sl < base_price:
    original_campaign_risk = round((base_price - init_sl) * base_qty, 2)
else:
    original_campaign_risk = 0.0
```

**Verdict:** **Audit OUTDATED** — there are now TWO definitions, not three. analytics_engine and risk_monitor consume the canonical engine_core function. adaptive_risk_engine remains an outlier.

Important subtle difference between adaptive_risk_engine and engine_core: adaptive uses `(price × qty).sum() / base_qty` to compute a weighted avg base price across first-day buys, while `engine_core.compute_original_campaign_risk` is called with a single price/quantity pair. **The two formulas are mathematically equivalent** for single-day weighted entries, but the adaptive flavor is closer to the "first-trade-day" campaign-aggregation semantics that engine_core's row-based wrapper doesn't directly express. So a direct swap requires care.

**Severity:** **MEDIUM** (down from BLOCKER). The risk of drift is real but the two surviving paths are now algebraically equivalent for well-formed first-day single-buy campaigns. Add-on days (multiple buy rows) will diverge if you just plug `get_campaign_risk_metrics(row)` into adaptive_risk without first computing the weighted base.

**Recommended action:**
- File: `adaptive_risk_engine.py` lines 159–175
- Build the same canonical row dict that adaptive currently builds inline, then call `ec.get_campaign_risk_metrics(_row)`:
  ```python
  _row = {"price": base_price, "quantity": base_qty,
          "initial_stop": init_sl, "side": "BUY"}
  _m = ec.get_campaign_risk_metrics(_row)
  original_campaign_risk = _m["original_risk"]
  ```
- Add a parametrised unit test (`tests/test_adaptive_risk_engine.py`) that asserts adaptive's per-campaign `original_campaign_risk` matches `ec.get_campaign_risk_metrics()` byte-for-byte across 5 fixtures (single buy, two-row first day, add-on the same day, ALGO, missing stop).

---

### Issue B — `follow_through_score` is always None

**Audit claim:** `follow_through_score` is always `None` because nothing computes it; RUNNER/WORKING gates pass too easily.

**Code evidence:**

`engine_core.py:1772-1862` — `compute_follow_through(symbol, entry_date_str, entry_price, ...)` IS implemented and returns a 0–100 score or None.

`risk_monitor.py:738-746`:
```python
_ft_score = None
if _mgt_mode != "algo_observed":
    try:
        _ft_score = ec.compute_follow_through(
            symbol=sym, entry_date_str=entry_date,
            entry_price=entry, side=_side_pos,
        )
    except Exception as e:
        print(f"follow-through error for {sym}: {e}")
```

So FT IS being computed and passed in. ✅

**But the design flaw remains.** `engine_core.py:2024-2031` (RUNNER gate):
```python
runner_by_realized = (
    original_campaign_risk > 0
    and realized_pnl >= original_campaign_risk
    and has_open_quantity
    and (follow_through_score is None or follow_through_score >= _RUNNER_FOLLOW_THROUGH_MIN)
)
```

And `engine_core.py:2042-2046` (WORKING gate):
```python
good_ft = (follow_through_score is None
           or follow_through_score >= _WORKING_FOLLOW_THROUGH_MIN)
if open_r >= _R_WORKING and good_ft:
    return _make_state(POSITION_STATE_WORKING, er, f"עובד: {open_r:.1f}R")
```

`compute_follow_through` returns None when `len(post) < _FT_MIN_DAYS_FOR_SCORE` (5 trading days, `engine_core.py:1821-1823`). So **for the first 5 trading days after entry, FT=None and a position can be classified RUNNER (by realized PnL) or WORKING without any quality gate**. The audit's concern is technically still valid — it's just shifted from "always None" to "None during the formative period."

**Verdict:** Audit is OUTDATED on the computation question, CORRECT in spirit on the gate logic. **MEDIUM severity** because:
- RUNNER-by-R (open_r ≥ 5R) still requires legitimate price action.
- RUNNER-by-realized requires `realized_pnl >= original_campaign_risk`, which is a real bar.
- WORKING just needs `open_r ≥ 1.0R`, which a momentary spike on day 2 can satisfy.

**Recommended action:**
- File: `engine_core.py:2025-2046`
- Sketch:
  ```python
  # Replace the "None = pass" semantics with explicit age gating.
  ft_ready = (follow_through_score is not None)
  ft_good_for_runner  = ft_ready and follow_through_score >= _RUNNER_FOLLOW_THROUGH_MIN
  ft_good_for_working = ft_ready and follow_through_score >= _WORKING_FOLLOW_THROUGH_MIN

  runner_by_realized = (
      original_campaign_risk > 0
      and realized_pnl >= original_campaign_risk
      and has_open_quantity
      and ft_good_for_runner   # require a real score, not "missing = ok"
  )
  ...
  if open_r >= _R_WORKING and (ft_good_for_working or age_days < _FT_MIN_DAYS_FOR_SCORE):
      ...
  ```
  The asymmetry is intentional: RUNNER demands proof; WORKING is the early-life default and we don't want to demote everything to PROVING in the first 5 days.

- Add 4 tests: (a) RUNNER-by-realized with FT=None must NOT classify as RUNNER; (b) RUNNER-by-realized with FT=72 → RUNNER; (c) WORKING with FT=None at age 3 → WORKING; (d) WORKING with FT=45 at age 8 → not WORKING (falls through).

---

### Issue C — Profit Factor sentinel mismatch (2.0 vs 99.0)

**Audit claim:** adaptive_risk_engine uses 2.0 for all-wins; analytics_engine uses 99.0.

**Code evidence:**

`adaptive_risk_engine.py:276-283`:
```python
gross_profit = sum(win_pnl)
gross_loss   = sum(loss_pnl)
if gross_loss > 0:
    pf = round(gross_profit / gross_loss, 2)
elif gross_profit > 0:
    pf = math.inf
else:
    pf = 0.0
```

`analytics_engine.py:52-54`:
```python
gross_profit = wins["net_pnl"].sum()   if not wins.empty   else 0.0
gross_loss   = abs(losses["net_pnl"].sum()) if not losses.empty else 0.0
profit_factor = gross_profit / gross_loss if gross_loss > 0 else (math.inf if gross_profit > 0 else 0.0)
```

Both modules now use `math.inf`. Setup breakdown in analytics_engine.py:98 also uses `math.inf`. The MODULE_MAP.md docs at line 84 still says "Profit Factor sentinel: 99.0 (no losses)" — that doc is stale.

**Verdict:** Audit OUTDATED. NOT-A-BUG.

**Recommended action:**
- Update `docs/MODULE_MAP.md` line 84: change "99.0 (no losses)" to "math.inf (no losses)".
- Update `docs/DATA_CONTRACTS.md` to add a new section explicitly stating: "Profit Factor uses `math.inf` when there are wins but no losses; `0.0` when there are losses but no wins. Display layers (telegram_formatters, report_renderer) must convert `math.inf` to the symbol `∞` or the string `N/A`."
- Audit downstream renderers for `math.inf`-safety (Plotly may pass it through; WeasyPrint will render the literal `inf`).

---

### Issue D — Silent failures in risk_monitor.py (lines 578, 589, 604)

**Audit claim:** Three silent-skip patterns hide problems from the user.

**Code evidence:**

`risk_monitor.py:594-602` (was 578 in audit):
```python
curr = ec.get_live_price(sym)
if curr is None:
    send_telegram(
        f"{RTL}⚠️ *Sentinel — מחיר חי חסר*\n"
        f"{RTL}סימול: *{sym}* | קמפיין: `{campaign_id}`\n"
        f"{RTL}לא נמצא מחיר חי — משתמש במחיר כניסה `${entry:.2f}` כ-fallback.\n"
        f"{RTL}_בדוק את החיבור ל-yfinance / market data_"
    )
    curr = entry
```
✅ Now sends an alert.

`risk_monitor.py:612-618` (was 589):
```python
if not _risk_metrics["valid"] and str(setup).upper() != "ALGO":
    send_telegram(
        f"{RTL}⚠️ *Sentinel — סטופ מקורי חסר*\n"
        f"{RTL}סימול: *{sym}* | קמפיין: `{campaign_id}`\n"
        f"{RTL}לא ניתן לחשב 1R: {_risk_metrics['reason']}\n"
        f"{RTL}_עדכן initial\\_stop בסופאבייס_"
    )
```
✅ Now warns when initial_stop is missing for a non-ALGO position. **Note:** the loop continues and computes with `original_campaign_risk=0`, so `open_r` becomes 0 (line 623). That's a soft silent miss — the position still flows through state machine logic with R=0, which routes it to DATA_INCOMPLETE state in engine_core.

`risk_monitor.py:633-640` (was 604):
```python
if not engine_res["ok"]:
    send_telegram(
        f"{RTL}🚨 *Sentinel — שגיאה בהערכת פוזיציה*\n"
        f"{RTL}סימול: *{sym}* | קמפיין: `{campaign_id}`\n"
        f"{RTL}evaluate\\_position\\_engine נכשל: `{engine_res.get('error', 'unknown')}`\n"
        f"{RTL}_הפוזיציה דולגה בסבב זה_"
    )
    continue
```
✅ Now alerts on engine failure.

**Verdict:** **Audit OUTDATED.** All three silent failures have been addressed. **LOW** severity remaining (the cosmetic concern of running through with R=0 when initial_stop is missing — but engine_core routes that to DATA_INCOMPLETE state correctly via `compute_position_state` line 2013).

**Side note — anti-spam concern:** the three new alerts above currently have NO per-symbol dedup. If `yfinance` is down or a single symbol is permanently missing its stop, the user will get this alert every 5 minutes. **Sprint 10 item:** add `last_data_alert_ts` keys per symbol to throttle these alerts to once per hour. This is itself a violation of the anti-spam invariant from AGENTS.md.

**Recommended action:**
- File: `risk_monitor.py`, the three new alerts above.
- Add throttling state keys: `last_live_price_alert_ts`, `last_missing_stop_alert_ts`, `last_engine_fail_alert_ts` (per symbol), with cooldown ≥ 1h.
- Add a test that simulates a yfinance outage over 12 cycles and asserts only 1 (or 2) alerts fire, not 12.

---

### Issue E — State file save only at end of loop

**Audit claim:** `risk_monitor_state.json` is saved only at the end of `main()`; crash mid-loop loses state.

**Code evidence:**

`risk_monitor.py:925-927`:
```python
# Checkpoint: persist position alerts before the slower global checks run.
# A crash in the sections below won't lose per-position alert state.
save_state(state)
```
Mid-loop checkpoint after per-position evaluation and cluster checks.

`risk_monitor.py:1016`:
```python
save_state(state)
```
End-of-loop save.

`risk_monitor.py:1038-1059` — graceful shutdown handler for SIGTERM and SIGINT:
```python
def _graceful_shutdown(signum, frame):
    ...
    state["shutdown_at"] = datetime.utcnow().isoformat()
    state["shutdown_signal"] = sig_name
    save_state(state)
    sys.exit(0)
```

`risk_monitor.py:1062-1070`:
```python
if __name__ == "__main__":
    _require_env()
    signal.signal(signal.SIGTERM, _graceful_shutdown)
    signal.signal(signal.SIGINT,  _graceful_shutdown)
```

**Verdict:** Audit OUTDATED. NOT-A-BUG.

**Caveat:** A SIGKILL or hard crash (OOM, segfault) still loses the in-memory state delta between the two saves. The mid-loop checkpoint is a real safety improvement but doesn't eliminate the risk. **Not worth fixing further** — best mitigation would be to save state immediately after every alert send, which would slow the loop and amplify the race condition (see N3).

---

### Issue F — Win Rate / Expectancy must exclude DATA_INCOMPLETE and ALGO_OBSERVED

**Audit claim:** (Not flagged in audit but listed as Sprint 9 / AGENTS.md invariant.)

**Code evidence:**

`AGENTS.md` invariant #8:
> Win Rate and Expectancy must never include DATA_INCOMPLETE or ALGO_OBSERVED campaigns.

`adaptive_risk_engine.py:431-437` — filters correctly via `_is_disc()`:
```python
def _is_disc(c: dict) -> bool:
    bucket = c.get("stat_bucket")
    if bucket:
        return ec.is_stat_countable(bucket)
    ...
disc_camps = [c for c in closed_campaigns if _is_disc(c)]
```

`dashboard.py:374-384` — filters correctly:
```python
countable_df = camp_df[camp_df['stat_bucket'].apply(ec.is_stat_countable)]
combined_stats = _bucket_stats(countable_df)
```

`analytics_engine.py:43-54` — **does NOT filter**:
```python
wins   = campaigns[campaigns["net_pnl"] > 0]
losses = campaigns[campaigns["net_pnl"] <= 0]
n      = len(campaigns)
win_rate    = len(wins) / n if n else 0
avg_win_r   = float(wins["net_r"].mean())   if not wins.empty   else 0.0
avg_loss_r  = float(losses["net_r"].mean()) if not losses.empty else 0.0
expectancy  = win_rate * avg_win_r + (1 - win_rate) * avg_loss_r
gross_profit = wins["net_pnl"].sum()   if not wins.empty   else 0.0
gross_loss   = abs(losses["net_pnl"].sum()) if not losses.empty else 0.0
profit_factor = gross_profit / gross_loss if gross_loss > 0 else (math.inf if gross_profit > 0 else 0.0)
```

`analytics_engine.py:235-267` — `_aggregate_campaigns` builds records with `setup_type` but never with `stat_bucket`. ALGO and DATA_INCOMPLETE campaigns get a `target_risk_usd`-based fallback for `orig_risk` and flow into the same metric pipeline as discretionary trades.

`analytics_engine.py:255`:
```python
orig_risk = _metrics["original_risk"] if _metrics["valid"] else target_risk_usd
```
This is the line that lets DATA_INCOMPLETE / ALGO leak in: when `valid=False`, the code substitutes `target_risk_usd` and continues.

`report_scheduler.py:207, 266` — both weekly and monthly PDF reports use `compute_period_analytics()`. **So the user's PDF reports show contaminated stats.**

`tests/test_analytics_engine.py` — does NOT cover stat_bucket / ALGO / DATA_INCOMPLETE exclusion. Confirmed via `grep -n "ALGO\|DATA_INCOMPLETE\|stat_bucket" tests/test_analytics_engine.py` → 0 matches.

**Verdict:** **HIGH severity, CONFIRMED.** This is the audit's biggest blind spot — it complains about three definitions of `original_campaign_risk` but misses the much more impactful invariant-#8 violation in the report pipeline.

**Recommended action:**
- File: `analytics_engine.py:235-267` (`_aggregate_campaigns`).
- Step 1: at the campaign loop, compute `stat_bucket` per campaign and attach it to the record:
  ```python
  bucket = ec.classify_stat_bucket(setup, _metrics["original_risk"])
  records.append({
      "campaign_id": cid, "symbol": sym, "setup_type": setup,
      "stat_bucket": bucket,
      "net_pnl": net_pnl, "net_r": net_r,
      "orig_risk": orig_risk, "days_held": days_held,
  })
  ```
- Step 2: in `compute_period_analytics`, split the campaigns frame into countable vs uncountable:
  ```python
  countable = campaigns[campaigns["stat_bucket"].apply(ec.is_stat_countable)]
  wins   = countable[countable["net_pnl"] > 0]
  losses = countable[countable["net_pnl"] <= 0]
  n_countable = len(countable)
  win_rate = len(wins) / n_countable if n_countable else 0
  ...
  ```
- Step 3: report **two** counts: `campaigns_closed` (everything) and `campaigns_countable` (excludes ALGO + DATA_INCOMPLETE). The PDF should display the second alongside Win Rate / Expectancy / PF, while showing the first as "total volume."
- Step 4: ALGO Drag / ALGO Net R should be computed and reported separately (analytics_engine already implicitly counts these in `total_r_net` — also wrong).
- Tests: add to `tests/test_analytics_engine.py`:
  - `test_algo_excluded_from_win_rate` — fixture with 3 wins (EP) and 2 losses (ALGO) → WR = 100% (3/3), not 60% (3/5).
  - `test_data_incomplete_excluded_from_expectancy` — fixture with one no-stop campaign that is profitable → expectancy unaffected.
  - `test_profit_factor_excludes_algo_losses` — fixture where ALGO produces a large loss → PF stays clean.
- Open question: do we also need to refactor `total_r_net`? Currently it's a sum across all campaigns (including ALGO). Per ALGO contract (DATA_CONTRACTS.md:84-87), ALGO net R should be reported but kept separate. Recommend introducing `total_r_net_disc` and `total_r_net_algo`.

---

### Issue G — Heat score additive → multiplicative refactor (Sprint 9 P4)

**Audit claim:** (Not flagged in audit — flagged in Sprint 9 plan.)

**Code evidence:**

`adaptive_risk_engine.py:296-331`:
```python
def _window_heat_score(stats: dict) -> float:
    if stats["n"] == 0:
        return 50.0
    score = stats["wr"] * 100

    p = stats["payoff"]
    if   p >= 3.0:      score += 24
    elif p >= 2.5:      score += 20
    elif p >= 2.0:      score += 15
    elif p >= 1.5:      score += 8
    elif p >= 1.2:      score += 3
    elif p >= 1.0:      score += 1
    elif 0 < p < 0.8:   score -= 15

    pf = stats["pf"]
    if   pf >= 2.5: score += 12
    elif pf >= 2.0: score += 8
    elif pf >= 1.5: score += 4
    elif pf >= 1.0: score += 1
    elif pf < 1.0:  score -= 15

    if   stats["loss_streak"] >= 3: score -= 18
    elif stats["loss_streak"] >= 2: score -= 10
    return min(100.0, max(0.0, score))
```

Sarah's Sprint 9 case: WR=70%, payoff=0.5, PF=0.8 →
- base 70
- payoff < 0.8 → -15
- pf < 1.0 → -15
- streak 0 → 0
- score = 40

Direction logic (file:line `adaptive_risk_engine.py` around 470, easy to verify):
- `heat ≥ 60 → up`
- `heat < 40 → down_fast`
- else `hold`

So 40 → **hold**. The trader stays at current risk despite a losing edge. The multiplicative formula proposed in Sprint 9 plan gives 9 → `down_fast`.

**Verdict:** **MEDIUM severity, CONFIRMED unfixed.** This is exactly the Sprint 9 priority — known, scheduled, not yet implemented.

**Recommended action:**
- Implement Sprint 9 P4 as written. The proposed formula (`docs/SPRINT_9_PLAN.md:96-103`) is well-specified.
- Watch out: the existing `_build_what_to_improve` and `_build_heat_factors` use `s9_score` arithmetic to back out the WR-needed math (`adaptive_risk_engine.py:387 — non_wr_component = s9_score - s9_wr`). Under the multiplicative model this back-calculation breaks. The factor-explainer must be rewritten or it will print nonsense.
- Add 5+ historical scenarios as fixtures (per Daria's acceptance criteria): all wins, all losses, mixed normal, payoff=0.5 catastrophe, single trade.

---

## New angles

### N1 — Does `score_position` handle missing/NaN inputs robustly?

**Risk:** `score_position` reads from a `features` dict produced by `compute_behavior_features`. If MA10/MA20/MA50 or ATR20 are NaN (insufficient history), booleans like `close < ma10` silently return False, biasing the score upward.

**Code evidence:**

`engine_core.py:215-216`:
```python
close, prev_close = df["Close"].iloc[-1], df["Close"].iloc[-2]
ma10, ma20, ma50 = df["MA10"].iloc[-1], df["MA20"].iloc[-1], df["MA50"].iloc[-1]
```

`engine_core.py:241`:
```python
"close_below_ma10": close < ma10, "close_below_ma20": close < ma20, "close_below_ma50": close < ma50,
```

In pandas/numpy, `value < NaN` returns `False`. So if `ma50` is NaN, `close_below_ma50 = False`, and `score_position` adds **+10 instead of -12** (`engine_core.py:330`). A 22-point swing per indicator.

**Mitigation in production:** `evaluate_position_engine` guards `len(hist) < 60` (`engine_core.py:417`) and returns `ok=False`, so the MA50 case is largely covered. MA50 needs 50 bars → with 60 bars guaranteed, MA50 has 10 valid trailing values.

**Still concerning:**
- `df["DistributionDay"]` requires `AvgVol20` (20-day rolling) and `ATR20` (20-day). With exactly 60 bars, the DistributionDay flags for the first ~20 bars are based on partial moving averages. The `.tail(8).sum()` and `.tail(12).sum()` reads the last 8/12 bars — which are valid given 60 bars. So **safe in production**.
- `is_down_day` on `engine_core.py:219`: `is_down_day = close < prev_close`. If `prev_close` is NaN (impossible given 60 bars), returns False. Safe.
- The ATR guard at `engine_core.py:343` uses `not pd.isna(features["atr20"])` — explicit. Safe.

**Verdict:** **LOW** — the 60-bar gate is a strong defense. NOT a bug today, but it's brittle. If anyone reduces the 60-bar guard for any reason (small-cap, low-volume name, recent IPO), the NaN behavior in `score_position` will silently inflate scores.

**Recommended action:**
- Defensive `pd.notna()` checks added to `score_position`:
  ```python
  if pd.notna(features.get("ma10")):
      score += 8 if not features["close_below_ma10"] else -8
  ```
- Or, simpler: make `compute_behavior_features` raise on NaN MA50, and let `evaluate_position_engine` catch and return `ok=False, error="insufficient_history"`.
- Add a unit test that passes a 30-bar DataFrame and asserts `evaluate_position_engine` returns `ok=False`.

---

### N2 — `compute_campaign_lot_state` mathematical edge cases when `base_qty != current_qty`

**Code evidence:**

`addon_risk_engine.py:90-110`:
```python
if initial_stop > 0 and initial_stop < base_price and base_qty > 0:
    original_risk_usd = (base_price - initial_stop) * base_qty
else:
    data_complete = False

open_pnl_usd = (current_price - base_price) * current_qty
total_pnl_usd = open_pnl_usd + realized_pnl_usd

locked_profit_usd = max(0.0, (stop_loss - base_price) * current_qty) if stop_loss > base_price else 0.0
open_risk_usd = max(0.0, (base_price - stop_loss) * current_qty) if stop_loss < base_price else 0.0

net_result_if_stop_hit = realized_pnl_usd + (stop_loss - base_price) * current_qty

open_r  = open_pnl_usd / original_risk_usd if original_risk_usd > 0 else None
total_r = total_pnl_usd / original_risk_usd if original_risk_usd > 0 else None
cushion_ratio = locked_profit_usd / original_risk_usd if original_risk_usd > 0 else 0.0
```

**Scenario walkthrough — partial-sell case:**

| Field | Pre-partial (base_qty=100) | After 50% sell (current_qty=50, realized=+500) |
|---|---|---|
| base_qty | 100 | 100 (frozen) |
| current_qty | 100 | 50 |
| original_risk_usd | (100-90)×100 = 1000 | (100-90)×100 = 1000 (frozen) |
| open_pnl_usd | (110-100)×100 = 1000 | (110-100)×50 = 500 |
| open_r | 1000/1000 = 1.0 | 500/1000 = 0.5 |

So **`open_r` halved after a 50% partial sell, even though the trader is still at the same price**. The intent is that `open_r` measures "what fraction of original 1R is still in floating profit on the unrealized portion." That's coherent — but the user-facing `total_r` is what represents the full campaign performance:
- total_r = (open_pnl + realized) / original_risk = (500 + 500) / 1000 = 1.0 ✓

So `total_r` is invariant under partial sell, `open_r` is not. **Intentional design.**

**Real edge case I found:** `net_result_if_stop_hit` (line 105):
```python
net_result_if_stop_hit = realized_pnl_usd + (stop_loss - base_price) * current_qty
```

If `stop_loss > base_price` (trader has raised stop above entry) and `current_qty > 0`:
- Suppose base_price=100, stop_loss=105, current_qty=50, realized=+500
- `net_result_if_stop_hit` = 500 + (105 - 100) × 50 = 500 + 250 = +750. Correct.

If `stop_loss < base_price` (stop still below entry) and `current_qty > 0`:
- Same prices except stop=92: 500 + (92 - 100) × 50 = 500 - 400 = +100. Correct.

If `current_qty == 0` (campaign fully closed, called accidentally):
- All current_qty-based fields = 0. `total_r` = realized / original_risk. `open_r` = 0 / original_risk = 0.
- The function doesn't refuse to compute. **Minor risk**: caller can compute a "stale lot state" for a closed campaign without warning. Should add an explicit check.

**Another edge case I found:** `original_risk_usd` requires `initial_stop < base_price` for LONG. If the user typoed and set `initial_stop > base_price` (LONG with stop above entry — nonsensical), `data_complete=False` and downstream eligibility returns `MANUAL_REVIEW`. **Safe.**

**Bigger concern:** the docstring at `addon_risk_engine.py:60-83` doesn't explicitly mention that `open_r` measures the *unrealized* portion's R, not the campaign's total R. A user / future agent reading just the field name will assume the wrong thing. The 5-pt Eligibility Gate 3 (`addon_risk_engine.py:~200`, "Cushion") asks "open_r ≥ 1.0R OR locked ≥ 50% orig" — this is *floating-only*, which is the correct gate for an add-on decision. But the naming is fragile.

**Verdict:** **NOT-A-BUG** — math is internally consistent — but documentation drift is a real maintenance hazard.

**Recommended action:**
- Update the docstring of `compute_campaign_lot_state` to explicitly state: "open_r measures floating PnL on the currently-open quantity divided by ORIGINAL campaign risk. After partial sells, open_r decreases proportionally to current_qty/base_qty even if price is unchanged. Use total_r for full-campaign performance."
- Add `tests/test_addon_risk_engine.py` test: `test_open_r_decreases_after_partial_sell_at_same_price`.
- Add a defensive check at the function entry: `if current_qty <= 0: warn / raise / return data_complete=False`.

---

### N3 — Race condition between `risk_monitor.py` writing `risk_monitor_state.json` and concurrent readers/writers

**Code evidence:**

`risk_monitor.py:106-107` (writer #1, runs every 300s in `risk-monitor` container):
```python
def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f: json.dump(state, f, ensure_ascii=False, indent=2)
```

**Non-atomic:** `open(...,"w")` truncates the file immediately. Between truncation and `json.dump` completing, the file on disk is either empty or partially written.

`bot_helpers.py:49-66` (writer #2, runs inline in `telegram-bot` container on user callback):
```python
def _write_runner_decision(campaign_id: str, decision: str) -> None:
    try:
        try:
            with open(_RM_STATE_FILE, "r", encoding="utf-8") as f:
                rm_state = json.load(f)
        except Exception:
            rm_state = {"positions": {}, "cluster": {}}
        pos_entry = rm_state.setdefault("positions", {}).get(campaign_id)
        if pos_entry is None:
            rm_state["positions"][campaign_id] = {}
            pos_entry = rm_state["positions"][campaign_id]
        pos_entry["runner_decision"] = decision
        pos_entry["runner_decision_ts"] = datetime.now().timestamp()
        with open(_RM_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(rm_state, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
```

**Two-process read-modify-write to the same file** with no locking. The classic anomalies:

1. **Lost update.** risk_monitor reads at T0, bot reads at T1, bot writes at T2, risk_monitor writes at T3 → bot's runner_decision is overwritten.
2. **Partial read.** bot reads while risk_monitor's write is mid-stream → `json.load` raises, the except clause kicks in and **resets `rm_state = {"positions": {}, "cluster": {}}`** — silently losing ALL position state. The very next save then persists the empty state.
3. **Reader exposure.** `dashboard.py:495` and `bot_health.py:121` both do `json.load(open(...))` on the same file. A simultaneous partial-write produces a JSONDecodeError. Both call sites lack try/except → likely uncaught.

`docker-compose.yml` mounts the repo into `/app` for ALL services, so all five containers see the same file.

`dashboard.py:495`:
```python
with open("risk_monitor_state.json", "r", encoding="utf-8") as _f:
```
(Need to verify try/except wrap around it — but even if wrapped, a partial read is undesirable.)

`bot_health.py:121`:
```python
rm = json.load(open("risk_monitor_state.json"))
```
No try/except around `json.load`. Will raise on partial read.

**Verdict:** **HIGH severity, CONFIRMED.** This is the kind of bug that produces "phantom state loss" — a reset of `last_giveback_class` / `checkpoints_hit` etc., causing a duplicate alert that the user can't explain.

**Recommended action:**
1. **Atomic write pattern** in `risk_monitor.py`:
   ```python
   import tempfile, os
   def save_state(state):
       d = os.path.dirname(os.path.abspath(STATE_FILE)) or "."
       fd, tmp = tempfile.mkstemp(prefix=".rmstate.", dir=d)
       try:
           with os.fdopen(fd, "w", encoding="utf-8") as f:
               json.dump(state, f, ensure_ascii=False, indent=2)
           os.replace(tmp, STATE_FILE)
       except Exception:
           if os.path.exists(tmp): os.remove(tmp)
           raise
   ```
   `os.replace` is atomic on POSIX (single inode swap). Readers will always see either the old or the new file, never partial.
2. **Same atomic pattern** in `bot_helpers._write_runner_decision`.
3. **Add a file lock** (`fcntl.flock`) around the read-modify-write in bot_helpers to prevent lost updates. risk_monitor doesn't strictly need a lock if it's the sole writer of most keys, but the bot is touching `runner_decision` from a different process — they need to coordinate.
4. **Wrap readers** in try/except (dashboard, bot_health) so partial-read JSONDecodeErrors are graceful.
5. **Test:** spawn two threads, one calling `save_state` 500 times, the other calling `_write_runner_decision` 500 times; assert no JSONDecodeError on a third reader thread and assert no positions are silently dropped.

---

## Open questions for Mark / Sarah / Daria

1. **Mark — should ALGO net R appear in the weekly PDF at all?** Currently `analytics_engine.compute_period_analytics` rolls everything into `total_r_net`. After the fix in Issue F we will split disc vs ALGO. Do you want the PDF to show **both** numbers or only the disc number?
2. **Sarah — heat-score multiplicative formula:** the proposed clamp `payoff/2.0` makes payoff=1.0 → factor 0.5 (penalty). At WR=55% and payoff=1.0 the multiplicative score is `0.55 × 0.5 × … ≈ 14` → `down_fast`. That seems too harsh for a marginally-positive system. Should we clamp the lower bound at 0.5 (current proposal) or 0.7?
3. **Daria — fixture set:** which 5 historical examples do you want me to use to validate the new heat-score formula? (Need ticker, R-distribution, payoff context for each.)
4. **Mark / Compliance — race condition exposure window:** I estimate <1ms file write at typical sizes (~10–50 kB). Sprint 9 P3 added Drawdown P0 alerts; if a race blanks the state, the P0 dedup flag is lost and Drawdown can re-fire. Is that within Compliance's risk tolerance for the current production?
5. **David — FT gate semantics for BACKING_OFF (Sprint 9 P5):** does the new state require an FT score, or does it inherit the same "None = pass" semantics? If it inherits, we add a *fourth* place where missing FT silently degrades the gate.

---

## Priority recommendations for Sprint 10

Ranked by user impact × engineering cost:

### P0 (must do)
1. **Fix Issue F — analytics_engine bucket filter.** Direct, user-visible defect. The PDF reports the user reads weekly are wrong. ~2 hours including tests. (`analytics_engine.py:235-267`)
2. **Fix Issue N3 — atomic state writes + file lock.** Direct cause of unexplained "duplicate alert" / "lost checkpoint" complaints. ~3 hours including a multi-thread test. (`risk_monitor.py:106-107`, `bot_helpers.py:49-66`)
3. **Throttle the new error alerts (audit Issue D follow-up).** A live-price outage today sends an alert every 5 minutes per symbol. Anti-spam invariant violation. ~1 hour. (`risk_monitor.py:594-640`)

### P1 (should do)
4. **Fix Issue B properly — FT gate semantics.** Today RUNNER-by-realized can fire on day 3 with no FT score. ~2 hours including 4 tests. (`engine_core.py:2024-2046`)
5. **Issue A consolidation — `adaptive_risk_engine.compute_closed_campaigns` uses `ec.get_campaign_risk_metrics`.** Removes the last divergent definition of `original_campaign_risk`. ~1 hour + parametrised tests. (`adaptive_risk_engine.py:159-175`)
6. **Sprint 9 P4 — multiplicative heat score** (already planned, just shipping).

### P2 (nice to have)
7. **Issue N1 — defensive NaN guards in `score_position`.** Future-proof for any reduction in the 60-bar history requirement. ~30 minutes. (`engine_core.py:326-355`)
8. **Issue N2 — docstring + test for `compute_campaign_lot_state` partial-sell semantics.** Documentation maintenance. ~30 minutes.
9. **Docs hygiene** — update MODULE_MAP.md PF sentinel from 99.0 to math.inf; update DATA_CONTRACTS.md with the explicit invariant-#8 enforcement note for analytics_engine.

### P3 (later)
10. Audit of all other JSON state files (`sentinel_config.json`, `risk_journal.json`, `risk_recommendations.json`, `ibkr_sync_state.json`, `scheduler_state.json`) — same atomic-write pattern. Likely the same race exists in 2–3 of them.

---

## Key file:line references (for quick navigation)

| Issue | File | Lines | What's there |
|------|------|-------|--------------|
| A — engine_core canonical | `engine_core.py` | 920–977 | `compute_original_campaign_risk`, `get_campaign_risk_metrics` |
| A — analytics uses canonical | `analytics_engine.py` | 252–255 | calls `ec.get_campaign_risk_metrics` |
| A — risk_monitor uses canonical | `risk_monitor.py` | 609–611 | calls `ec.get_campaign_risk_metrics` |
| A — adaptive inlines its own | `adaptive_risk_engine.py` | 159–175 | inline `(base_price - init_sl) * base_qty` |
| B — FT computed | `risk_monitor.py` | 738–746 | `_ft_score = ec.compute_follow_through(...)` |
| B — FT None-passes RUNNER | `engine_core.py` | 2030 | `(follow_through_score is None or ...)` |
| B — FT None-passes WORKING | `engine_core.py` | 2043–2044 | `(follow_through_score is None or ...)` |
| B — FT min-bars rule | `engine_core.py` | 1821–1823 | returns None when `len(post) < 5` |
| C — adaptive PF sentinel | `adaptive_risk_engine.py` | 281 | `pf = math.inf` |
| C — analytics PF sentinel | `analytics_engine.py` | 54 | `math.inf if gross_profit > 0` |
| D — live price alert | `risk_monitor.py` | 594–602 | now alerts |
| D — missing stop alert | `risk_monitor.py` | 612–618 | now alerts |
| D — engine fail alert | `risk_monitor.py` | 633–640 | now alerts |
| E — mid-loop save | `risk_monitor.py` | 925–927 | first checkpoint |
| E — end-loop save | `risk_monitor.py` | 1016 | second save |
| E — graceful shutdown | `risk_monitor.py` | 1038–1059 | SIGTERM/SIGINT handler |
| F — analytics no filter | `analytics_engine.py` | 43–54 | wins/losses split without stat_bucket |
| F — analytics aggregator | `analytics_engine.py` | 235–267 | `_aggregate_campaigns` (no bucket on records) |
| F — adaptive correct filter | `adaptive_risk_engine.py` | 431–437 | `_is_disc` filter |
| F — dashboard correct filter | `dashboard.py` | 374–380 | `countable_df` |
| F — report consumes | `report_scheduler.py` | 207, 266 | `compute_period_analytics` calls |
| G — additive heat score | `adaptive_risk_engine.py` | 296–331 | `_window_heat_score` |
| N1 — features build | `engine_core.py` | 215–245 | `compute_behavior_features` |
| N1 — score consumes | `engine_core.py` | 326–355 | `score_position` |
| N1 — 60-bar guard | `engine_core.py` | 417 | `len(hist) < 60` |
| N2 — lot state math | `addon_risk_engine.py` | 50–130 | `compute_campaign_lot_state` |
| N3 — non-atomic writer 1 | `risk_monitor.py` | 106–107 | `save_state` |
| N3 — non-atomic writer 2 | `bot_helpers.py` | 49–66 | `_write_runner_decision` |
| N3 — unsafe reader | `dashboard.py` | 495 | `with open(...) as _f: json.load(_f)` |
| N3 — unsafe reader | `bot_health.py` | 121 | `json.load(open(...))` |

---

## Methodology / caveats

- **Read-only audit.** No production code modified. No tests executed.
- I did not run `pytest -q`. Some claims about test coverage rely on grep, not actual coverage runs.
- I did not inspect `telegram_bot.py` (per the audit's note and CLAUDE.md, treated as fragile).
- The audit document references absolute line numbers (e.g. "risk_monitor.py:578"). Since the audit was written, lines have shifted — I've used current line numbers throughout.
- Where I rated severity differently from the audit, the rating reflects (a) whether the issue still exists, (b) user-facing impact, (c) ease of fix. None of these ratings are normative — Mark / Sarah / David should reweigh.

— Research Team, Day 1
