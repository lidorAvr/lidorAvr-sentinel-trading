# Sprint-20 RCA — Why "0 Realized" for 03–09/05/2026 + April 2026

**Date:** 2026-05-16 · Branch `claude/review-system-audit-FBZ2h` · READ-ONLY audit.
Gates DEC-20260516-017. No analytics/campaign-math changed; nothing committed.

## 1. Exhaustive failure enumeration (real trade → shows `0`)

| # | Condition | Exact site | Realized path | Open book | Class |
|---|-----------|-----------|---------------|-----------|-------|
| a | In-window SELL, **NULL/blank `campaign_id`** | `analytics_engine.py:261` `.dropna().unique()` | DROPPED — not counted, NOT in `excluded` | `engine_core.py:479` `notnull()` also drops it | **data-integrity** (vanishes from BOTH) |
| b | BUY/SELL of one logical trade linked to **different `campaign_id`s** | `:262` groups by id; `_aggregate_campaigns:268-272` skips a group with `buys.empty` | close-only group: `continue` (uncounted); open-only group: net_qty>0 → perpetually open | `engine_core.py:481-484` perpetual open | **data-integrity** |
| c | **Partial exit** (campaign still net-open, realized pnl on partial SELL) | `_get_closed_campaigns:258-262` keys off *any* in-window SELL → campaign IS pulled; `_aggregate_campaigns:274` `net_pnl=sells.pnl_usd.sum()` counts it; **but** also still appears net-open in `engine_core.py:483` | counted as realized (full campaign net_pnl, may be partial) | also shows as open | **formula/semantic** (double-surface; not "0", but mis-scoped) |
| d | SELL `pnl_usd` NULL/0 | `analytics_engine.py:33` `to_numeric…fillna(0)`; `:274` sum=0 | campaign counted, **realized contribution $0** | n/a | **data-integrity** (shows 0) |
| e | `side` casing/whitespace (`" sell"`, `Sell`) | `:257/:269/:270` `.str.upper().eq("SELL")` — no `.strip()` | leading/trailing space ⇒ SELL not matched ⇒ no in-window SELL ⇒ campaign never pulled | BUY mis-match similar | **data-integrity** |
| f | In-window round-trip but campaign classified **DATA_INCOMPLETE/ALGO** | `:55` `excluded`; `:80-85` early-return; ALGO via `engine_core.py:1251`, DATA_INCOMPLETE via `:1258` | excluded from WR/Exp/PF/Net-R (correct #8) BUT `excluded_count`/`excluded_pnl` **NOT rendered** (absent in `report_renderer.py` + both `.j2`) | n/a | **formula/honesty gap (#1)** |
| g | Close executed in IBKR but **never synced to Supabase** | out of `report_scheduler._fetch_trades_df:136-141` reach (`select("*")` only returns rows that exist) | invisible — report honest about data it has (#1) | invisible | **out-of-reach / upstream sync** |
| h | Close `trade_date` outside `[start, end)` | `:258` `>= start` & `< end` | excluded if truly outside | n/a | **out-of-window** |

**Window-boundary note (h):** `trade_date` is coerced date-only (`analytics_engine.py:30`, time 00:00:00). `_weekly_period`/`_monthly_period` set `period_end` = last day **23:59:59** (inclusive instant); `_period_label` renders that inclusive day ("3–9 במאי"/"1–30 באפריל", `report_renderer.py:731-736`). So `trade_date < end` with date-only timestamps **correctly includes** SELLs on the labelled last day. No off-by-one here. Real out-of-window risk: a close on the boundary **date** stored *with* a non-midnight time, or one calendar day past the window.

**Leading hypothesis (must be data-confirmed by the probe):** (a) null-`campaign_id` in-window SELLs and/or (g) unsynced closes — both consistent with `bot_health.py:146` already flagging null-`campaign_id` rows and the open broker-recon $190.29 gap. (f) is a secondary #1 honesty gap regardless.

## 2. Root-cause decision tree (run probe, then classify)

```
Probe Σ for the window:
├─ SELL rows with NULL campaign_id  > 0 ?
│    └─ YES → ROOT = data-integrity: UNLINKED closes (a). Fix = link campaign_id
│             upstream (importer DEC-20260512-004). Union view alone won't fix.
├─ total SELL rows in window == 0 ?
│    ├─ founder is sure a close happened → ROOT = (g) UNSYNCED to Supabase
│    │     (IBKR/broker truth not in DB). #1: report cannot show what is absent.
│    └─ side casing/whitespace suspected → inspect raw `side` values (e).
├─ #campaigns with in-window SELL > 0 BUT campaigns_closed == 0 ?
│    └─ excluded_count > 0 → ROOT = (f) linked-but-excluded (DATA_INCOMPLETE/ALGO),
│         silently 0 because templates omit excluded_*. Honest-surface fix.
├─ closes exist & linked & countable but dates land 1 day off window → (h) out-of-window.
└─ else → escalate: round-trip present but mis-aggregated (b/c) — inspect by campaign_id.
```

## 3. Read-only diagnostic probe spec — "תקינות נתוני תקופה"

- **New module:** `period_data_probe.py` (self-contained, NOT wired to production). Function `run_period_probe(period_type, now=None) -> dict` + `format_probe_he(result) -> str`.
- **Data source (read-only):** reuse `report_scheduler._fetch_trades_df(period_start, period_end)` (8-week lookback, pure SELECT, `report_scheduler.py:113-145`) and `report_on_demand.last_complete_weekly_ref` / `_weekly_period` / `_monthly_period` for the SAME windows. NO `report_snapshot_store.save`, NO `_mark_ran/_save_state`, NO Supabase write, NO call into `compute_period_analytics` number path beyond reading `excluded_count/excluded_pnl`.
- **Dev-menu wiring point:** add one `KeyboardButton("🩺 תקינות נתוני תקופה")` row in `telegram_menus.get_developer_menu()` (next to the on-demand buttons, `telegram_menus.py:30`); add an `if text == "🩺 תקינות נתוני תקופה":` branch in `telegram_bot.py` beside the on-demand handler (`telegram_bot.py:312`), run in a daemon thread like `_run_on_demand_report_thread`.
- **Existing admin gate to reuse (no new gate):** the dev-menu PIN session — `dev_pin_is_configured()` / `dev_pin_session_active()` / `awaiting_dev_pin` state (`telegram_bot.py:83-94, 147-153`); the button only renders inside `get_developer_menu()` which is reached only after PIN. Same boundary as the on-demand report.
- **Output per window (weekly + monthly), read-only:** total trades; BUY count; SELL count; **BUY with NULL `campaign_id` (count)**; **SELL with NULL `campaign_id` (count + list: symbol · trade_date · pnl_usd only — no IDs/secrets)**; #distinct `campaign_id` with an in-window SELL; #campaigns opened-AND-closed within the window (first BUY ≥ start AND last SELL < end, same id); Σ `pnl_usd` for in-window rows; `excluded_count` / `excluded_pnl` (read from `compute_period_analytics` result dict — already computed, just surfaced); raw distinct `side` values seen (detects casing/whitespace, failure e). Hebrew, RTL, explicit "קריאה בלבד — לא משנה נתונים".

This probe is genuinely read-only and self-contained → it MAY be implemented now as a new unwired file; leave it uncommitted for parent review. Do NOT wire the menu/handler until parent/Mark approves (that touches production menus).

## 4. Mark-ruling questions for the gated Step-2 union build

1. **Partial-exit (c):** a campaign net-open with realized partial-SELL pnl — does realized WR/Exp/PF/Net-R count the *realized slice only*, and is the residual strictly in the open book, with a hard guard that the same campaign_id is never double-counted (realized vs unrealized)? Exact split formula.
2. **#8 treatment of unlinked/incomplete (a/f):** unlinked & DATA_INCOMPLETE round-trips must NOT enter headline WR/Exp/PF (#8) — confirm they surface only as an honest separate disclosure line, never in the countable subset (which stays byte-identical — guard test).
3. **Honest Hebrew wording** for the disclosure: e.g. `⚠️ {n} עסקאות לא מקושרות/חסרות נתון — לא נספרו ב-WR/Expectancy, דורש קישור (campaign_id)` and, when closes are absent from the DB, `סגירות שלא סונכרנו — מחוץ לתחום הדוח` (never fabricate a close not in the data — #1).
4. **Union semantics:** does "opened-in-period" require the *first* BUY in-window, and does an open-spanning position contribute realized $0 + unrealized only (no realized leakage)? Confirm the union changes scoping only, introduces zero new R/NAV/campaign math, and the linked-closed countable KPIs remain byte-identical (guard).
