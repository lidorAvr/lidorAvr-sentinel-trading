# Module Map

This file explains the purpose of the main files and how they depend on each other.

## Production modules (root level)

### `engine_core.py`

Core analytical engine.

Responsibilities:
- market data retrieval and caching through yfinance
- ATR and moving-average calculations
- sector / relative strength mapping
- distribution and accumulation day detection
- trade-stage classification
- position scoring
- hard-rule risk evaluation
- management action suggestions
- open campaign aggregation
- market regime calculation
- Minervini-style analysis helpers (Trend Template, R/day, MAE/MFE, add-on quality)
- ALGO Observer Mode gating: `is_algo_position()`, `classify_management_mode()`
- Stat bucket classification: `classify_stat_bucket()`, `is_stat_countable()`, `is_discretionary_bucket()`
- Position state machine: `compute_position_state()` → RUNNER / BROKEN / DEAD_MONEY / WORKING / etc.
- Risk analytics: `compute_giveback_from_peak()`, `compute_risk_deviation()`, `compute_algo_oversight_summary()`

Stat bucket constants:
- `STAT_BUCKET_ALGO = "ALGO_OBSERVED"`
- `STAT_BUCKET_DATA_INCOMPLETE = "DATA_INCOMPLETE"`
- `classify_stat_bucket(setup_type, original_campaign_risk)` → EP_MANUAL / VCP_MANUAL / ALGO_OBSERVED / DATA_INCOMPLETE
- `is_stat_countable(bucket)` → False for ALGO_OBSERVED and DATA_INCOMPLETE
- `is_discretionary_bucket(bucket)` → True if bucket ends with `_MANUAL`

Position state constants:
- `POSITION_STATE_RUNNER`, `POSITION_STATE_BROKEN`, `POSITION_STATE_DEAD_MONEY`
- `POSITION_STATE_WORKING`, `POSITION_STATE_PROVING`, `POSITION_STATE_PROFIT_PROTECTION`
- `POSITION_STATE_YELLOW_FLAG`, `POSITION_STATE_ALGO_OBSERVED`, `POSITION_STATE_DATA_INCOMPLETE`

High-risk areas:
- `get_open_positions_campaign`
- `evaluate_position_engine`
- `calculate_atr_series`
- `evaluate_hard_rules`
- `score_position`

Rules:
- Do not change risk math without tests.
- Do not change campaign aggregation without sample trade rows.
- Do not change ALGO caps without documenting the reason.
- Do not remove cache behavior without considering provider rate limits.

---

### `account_state.py`

Single source of truth for NAV and account settings.

Responsibilities:
- `load()` → always returns a safe dict, never raises.
- Freshness labels: fresh (<24h) / stale (24–48h) / critical (>48h) / unknown.
- `target_risk_usd(account)` convenience helper.
- Fallback to $7,500 when config is missing or corrupted.

Rules:
- All services that need NAV must use `account_state.load()`, not read sentinel_config.json directly.
- Never raise from `load()` — callers must not need try/except.

> **Known NAV-contract divergence (Phase Arch-F1 / Sprint-25 F1 — DEFERRED, founder-gated).**
> The report pipeline resolves NAV via `account_state.load()` (shape A:
> `nav_source` ∈ broker/deposited/fallback, `is_critical = freshness=="critical"`,
> honest fallback dict, `ok=False` only on fallback). The bot
> (`bot_helpers.get_nav_and_risk`) and risk-monitor (`risk_monitor.py:607-609`
> acc_size/target-risk block, math byte-unchanged) resolve NAV via
> `engine_core.get_nav_with_freshness()` — a DIFFERENT contract: different
> shape (`source`/`updated_at` vs `nav_source`/`nav_updated_at`), a different
> fallback (`is_critical=True`, different Hebrew label, `ok=False` on
> fallback). Both feed the SAME risk math. Unifying the two NAV contracts is
> behavior-bearing (it changes which fallback/freshness a path sees — money
> affecting) and is **OUT of Arch-F1 — a deferred, founder-gated decision**,
> not done here. Arch-F1 only de-duplicated the `sentinel_config.json`
> *reader* (`risk_monitor` now imports `bot_helpers.get_account_settings`).
> `engine_core.py` / `account_state.py` are byte-unchanged.

---

### `analytics_engine.py`

Period analytics computation.

Responsibilities:
- `compute_period_analytics(df, start, end, account)` → full analytics dict.
- `compute_trader_development_score(analytics)` → 0–100 score with breakdown.
- `compute_verdict(analytics)` → (Hebrew text, class).
- `compute_period_comparison(current, previous)` → per-metric delta.

Rules:
- Profit Factor sentinel: 99.0 (no losses), 0.0 (no wins).
- Oversized threshold: actual risk > 125% of target risk USD.
- Do not change math without updating `tests/test_calculations_comprehensive.py`.

---

### `adaptive_risk_engine.py`

Adaptive risk recommendation engine and stat-bucket-aware campaign processor.

Responsibilities:
- `compute_closed_campaigns(df)` → closed campaigns list. Each dict includes:
  - `campaign_id`, `symbol`, `setup_type`, `total_pnl_usd`, `close_date`, `is_win`
  - `original_campaign_risk` (computed from first BUY day price/qty/initial_stop)
  - `stat_bucket` (via `ec.classify_stat_bucket()`)
- `compute_adaptive_risk(campaigns, current_risk_pct, nav)` → recommendation dict.
  - Uses `_is_disc()` helper: `ec.is_stat_countable(bucket)` to exclude ALGO/DATA_INCOMPLETE from WR/streak.
  - Weighted Win Rate: last-10 weight=2, rest=1, ALGO positions at 0.25× (observer only).
- `update_risk_pct(new_pct)` → writes to sentinel_config.json.
- `log_risk_journal(entry)` → appends to risk_journal.json (500 cap).
- `mark_adherence(rec_pct, actual_pct, followed, reason)` → updates risk_recommendations.json.
- `compute_adherence_stats()` → adherence statistics.

RISK_LADDER: `[0.25, 0.40, 0.60, 0.85, 1.15, 1.50, 2.00]`
<!-- Sprint-27 W4a: corrected to the DEPLOYED, authoritative ladder
     adaptive_risk_engine.py:20 RISK_LADDER (mirrored user_context.py:218,
     pinned by tests/test_user_context.py). The prior [0.35…2.50] 8-step
     value was stale doc-drift — the code deliberately removes the
     non-monotonic 2.50 outlier (uniform step cadence). Code is
     authoritative for behaviour; changing the ladder itself is a
     money-methodology decision (founder-gated), out of this DOC-only fix. -->


Direction logic:
- heat ≥ 60% and loss_streak < 3 → `up` (+1 step)
- heat < 40% or loss_streak ≥ 3 → `down_fast` (−2 steps)
- otherwise → `hold`

Rules:
- `is_win` must be accessed via `.get("is_win")` — never `["is_win"]`.
- DATA_INCOMPLETE campaigns must never enter Win Rate or Expectancy.
- `compute_closed_campaigns()` is the single source of truth for closed campaign stats — do not reimplement inline.

---

### `ibkr_sync_runner.py`

IBKR Flex Query sync pipeline.

Responsibilities:
- `IBKR_ERROR_CLASSES` — 17 known error codes with class and Hebrew description.
- `parse_flex_error(xml)` → classified error dict or None.
- `get_statement_with_retry(ref, token, max_retries, wait_sec)` → (xml, err).
- `run_ibkr_sync(log_fn)` → `{"status", "code", "message", "nav"}`.
- NAV extraction from `ChangeInNAV endingValue`.
- Auto-cleanup of old XML reports (keeps last 3).

Rules:
- Fatal errors (1012–1017, 1020) must NEVER retry — account lockout risk.
- Token must never appear in returned result dict or log messages.

---

### `telegram_bot.py`

Main Telegram interaction layer.

Responsibilities:
- menu handling (hierarchical: 4 categories → sub-menus)
- `/portfolio`, `/next`, `/trade SYMBOL`, `/analyze`, `/mentor`, `/stats`, `/health`
- backlog/journal completion flows
- user prompts for setup, quality, stops, images, management notes
- Supabase reads and writes
- adaptive risk confirmation callbacks (`risk_confirm|YES/NO`)
- runner decision callbacks (`runner_decision|hold/tighten/partial|SYM|CID`)
- developer menu (🛠️ — admin-only, rate-limited)

Win Rate in `/portfolio` uses `are.compute_closed_campaigns(df)` + `ec.is_stat_countable()` to exclude DATA_INCOMPLETE. Never recompute inline.

Risks:
- very long file
- many implicit flows
- direct Supabase mutation paths

Rules:
- Avoid broad rewrites.
- Prefer extracting small helpers into new files.
- Keep Hebrew output readable.
- Any Supabase update must be intentional and traceable.

---

### `telegram_bot_secure_runner.py`

Runtime safety wrapper for Telegram.

Responsibilities:
- enforce `TELEGRAM_ADMIN_ID`
- rate-limit burst usage
- add cooldown after spam-like behavior
- append data-source note to user-facing reports

Rules:
- Do not bypass this runner in production unless protections are moved into `telegram_bot.py`.
- If Docker Compose changes the Telegram command, verify the runner is still active.

---

### `telegram_formatters.py`

Pure formatting helpers (no Supabase, no bot, no engine_core).

Responsibilities:
- `fmt_position_card()` — unified position card
- `fmt_summary_footer()` — portfolio summary block
- `fmt_regime_report()` — market regime report
- `fmt_minervini_trend_template()` — 8-criteria output
- `fmt_adaptive_risk_block()` — adaptive risk recommendation block

Rules:
- Must not import telebot, supabase, or engine_core.
- Callers compute data and pass it in as parameters.

---

### `report_scheduler.py`

Scheduled PDF report delivery service (Docker standalone).

Responsibilities:
- 60s polling loop with Israel-TZ scheduling.
- Weekly: Saturday 08:30 → full week coverage.
- Monthly: 1st of month 08:40 → previous full month.
- Deduplication via `scheduler_state.json`.
- Orchestrates analytics → charts → PDF → delivery pipeline.
- `_weekly_coaching_insights(analytics)` / `_monthly_coaching_insights(analytics)` — always returns non-empty list.

Rules:
- Must not send duplicate reports (dedup key = date string).
- Coaching insights must always produce at least one item.

---

### `report_renderer.py`

HTML + CSS → PDF renderer.

Responsibilities:
- `build_weekly_report(...)` / `build_monthly_report(...)` → PDF bytes.
- `build_summary_text(...)` → Telegram Markdown string.
- `_period_label(start, end)` → Hebrew month names.
- Jinja2 templates + WeasyPrint rendering.

Rules:
- All Hebrew numbers/tickers must be wrapped in `.ltr` CSS class for RTL display.
- Markdown: balanced backticks (even count), balanced asterisks.

---

### `report_delivery.py`

Telegram PDF and message delivery.

Responsibilities:
- `send_pdf(path, caption, chat_id, token)` → bool.
- `send_message(text, chat_id, token)` → bool.
- Caption auto-truncated to 1024 chars (Telegram limit).
- `_log(msg)` → stdout + `/app/logs/sentinel_report.log`.

---

### `report_snapshot_store.py`

WoW/MoM comparison snapshot storage.

Responsibilities:
- `save_snapshot(analytics, label)` → writes to `/app/report_state/snapshots/`.
- `load_snapshots()` → sorted newest-first.
- `load_previous_snapshot(label)` → snapshot before given label.

Rules:
- Snapshot files are local runtime state. Not committed to git.
- Corrupt snapshot files are skipped silently.

---

### `chart_generator.py`

Plotly + Kaleido static chart generation for PDF embedding.

Responsibilities:
- `campaign_r_bars(campaigns, out_dir)` → PNG or None.
- `setup_performance_bars(analytics, out_dir)` → PNG or None.
- `weekly_equity_curve(snapshots, out_dir)` → PNG or None.
- `win_loss_donut(analytics, out_dir)` → PNG or None.

Rules:
- All functions return None gracefully if Plotly/Kaleido unavailable.
- Export: 520×260px PNG, brand palette.

---

### `main.py`

IBKR sync / account update loop (v16.0).

Responsibilities:
- Sync window: 07:00–11:00 Asia/Jerusalem only.
- One attempt per clock-hour.
- State in `/app/ibkr_sync_state.json`.
- Delegates sync logic to `ibkr_sync_runner.run_ibkr_sync()`.
- Telegram alerts on failure and success.

Rules:
- Any NAV/account-size write must be documented.
- Ensure Telegram and dashboard read the same account assumptions.

---

### `dashboard.py`

Streamlit dashboard.

Responsibilities:
- Sidebar: Market Regime, Account Settings, Adaptive Risk recommendation + deviation indicators, Data Reconciliation, AI Master Context Export.
- Command Center tab: live portfolio treemap, heat map, Minervini analysis per position (Trend Template + Add-on quality + MAE/MFE).
- **Performance Matrix tab**:
  - **Trader Edge Panel** (top of tab): table of 11 metrics × 4 scopes (ידני/EP/VCP/ALGO):
    - N, Win Rate, Avg Win R, Avg Loss R, W/L Ratio, Expectancy, Profit Factor, Payoff Consistency, Max Loss R, Sizing Efficiency, Net PnL
  - Decision Matrix: color-coded callouts for Manual scope — Expectancy, W/L Ratio, Profit Factor, Max Loss, Payoff Consistency, Sizing Efficiency
  - ALGO Drag shown separately
  - Legacy bucket stats (disc/ALGO/combined) + equity curve, drawdown, R-distribution
- Strategy Forensics tab, Visual Journal tab, Minervini Mentor tab, DB Manager tab.

`_bucket_stats(df)` returns:
- `win_rate`, `adj_rr`, `expectancy_r`, `total_pnl`, `total_r`, `count`
- `avg_win_r`, `avg_loss_r`, `profit_factor`, `payoff_consistency`, `max_loss_r`

Scope DataFrames computed from `camp_df`:
- `disc_df` = `stat_bucket.apply(is_discretionary_bucket)` — EP+VCP+other MANUAL
- `ep_df` = `stat_bucket == 'EP_MANUAL'`
- `vcp_df` = `stat_bucket == 'VCP_MANUAL'`
- `algo_df` = `stat_bucket == STAT_BUCKET_ALGO`
- `countable_df` = `stat_bucket.apply(is_stat_countable)`

Adaptive Risk sidebar deviation indicators:
1. Direction + recommended risk pct/usd
2. Configured vs recommended (green/warning/info)
3. Open positions avg sizing ratio vs ideal (0.85–1.15x)
4. Win Rate vs 50% target

Rules:
- Dashboard can be more verbose than Telegram.
- Must identify fallback/estimated values clearly.
- Reuse engine functions rather than re-implementing calculations.
- All stat calculations must go through `_bucket_stats()` — no inline Win Rate loops.

---

### `risk_monitor.py`

Automated risk monitoring service (runs every 300 seconds).

Responsibilities:
- Periodic position risk evaluation via `ec.evaluate_position_engine()`
- Position state machine: RUNNER / BROKEN / DEAD_MONEY / YELLOW_FLAG / WORKING
- **Live Alert** anti-spam:
  - `trigger` field excluded from `alert_key` (oscillates intra-day)
  - Non-escalating key changes throttled by `LIVE_ALERT_REPEAT_COOLDOWN = 45 min`
  - Status escalation always fires immediately
  - Critical/Broken re-alert: once per 6h during market hours only
- **Giveback alerts**: zone-change-only firing. Fires when zone transitions (natural→watch, watch→tighten, tighten→watch, etc). Never re-fires in same zone.
- Giveback suppressed entirely when `position_state == POSITION_STATE_BROKEN`
- **Sizing Leak alert**: one-time per campaign when `original_campaign_risk / target_risk_usd < SIZING_LEAK_THRESHOLD (0.65)`. Stored as `sizing_leak_alerted` in state.
- **Daily Digest**: once per day at 21:00–22:00 UTC (Mon–Fri). Lists all positions with state emoji, Open R, action. Tracked by `last_digest_date`.
- Risk deviation alerts: escalation or 3h cooldown
- Profit Protection Checkpoints: one-time at 2R and 3R
- Breakeven Protocol: one-time when open_r ≥ 3R but capital still at risk
- ALGO Oversight: streak alerts, deep loss alerts, cluster alerts, visibility alerts
- Proactive Adaptive Risk alert (once/24h per direction)
- Manual risk override detection

Key state keys per position in `risk_monitor_state.json`:
- `position_state`, `state_label` — current state machine output
- `last_state_alert_type`, `last_state_alert_ts` — oscillation prevention
- `peak_open_r`, `checkpoints_hit` — profit protection tracking
- `last_giveback_class`, `last_giveback_ts` — giveback zone tracking
- `last_deviation_class`, `last_deviation_ts` — risk deviation tracking
- `breakeven_alerted` — one-time breakeven protocol flag
- `sizing_leak_alerted` — one-time sizing leak alert flag
- `runner_decision`, `runner_decision_ts` — user runner decision tracking
- `algo_loss_streak`, `algo_streak_alerted_yellow`, `algo_streak_alerted_orange` — ALGO streak tracking
- `algo_deep_loss_alerted` — single deep-loss alert flag

Top-level state keys:
- `last_digest_date` — daily digest dedup (YYYY-MM-DD)
- `last_known_risk_pct` — manual override detection
- `algo_visibility_alerted_ts` — ALGO visibility alert cooldown
- `risk_alert` — last adaptive risk alert direction + ts

Constants:
- `LIVE_ALERT_REPEAT_COOLDOWN = 45 * 60`
- `DAILY_DIGEST_UTC_HOUR_START = 21`, `DAILY_DIGEST_UTC_HOUR_END = 22`
- `SIZING_LEAK_THRESHOLD = 0.65`
- `DEVIATION_COOLDOWN_SEC = 3 * 3600`
- `GIVEBACK_COOLDOWN_SEC = 6 * 3600` (kept but no longer used for same-zone re-fire)
- `STATE_ALERT_COOLDOWN`: RUNNER=4h, BROKEN=4h, DEAD_MONEY=12h

Rules:
- Must not spam Telegram.
- Must not auto-mutate trade management state.
- Every recurring check must have a state-tracked dedup flag or cooldown.
- Giveback must use zone-change detection, not timer-based re-fire.
- BROKEN positions must not receive Giveback alerts.

---

## Infrastructure

### `docker-compose.yml`

Production wiring.

Active services:
```yaml
sentinel-bot:      python3 main.py                       # IBKR sync
telegram-bot:      python3 telegram_bot_secure_runner.py # Telegram UI
dashboard:         streamlit run dashboard.py            # Web dashboard
risk-monitor:      python risk_monitor.py                # Monitoring
reporting-service: python report_scheduler.py            # PDF reports
```

Rules:
- Do not change Telegram service back to `telegram_bot.py` without replacing the runner protections.
- Rebuild only affected services when possible.
- Validate logs after deployment.

---

### `requirements.txt` / `requirements-dev.txt`

Runtime and dev dependencies.

Rules:
- Keep additions minimal.
- PDF stack (weasyprint, jinja2, plotly, kaleido) are production dependencies.
- Test stack (pytest, pytest-cov) in requirements-dev.txt only.

---

### `tests/`

Test suite (1107 tests as of branch `claude/review-dev-roadmap-6K19V`).

Structure:
```
tests/
  test_account_state.py        # NAV loading, freshness, fallback
  test_adaptive_risk_engine.py # RISK_LADDER, directions, streaks, adherence,
                               # stat_bucket classification in closed campaigns,
                               # DATA_INCOMPLETE exclusion from adaptive risk
  test_algo_observer.py        # ALGO mode, management_mode, risk_basis
  test_analytics_engine.py     # Period analytics, verdict, comparison
  test_calculations_comprehensive.py  # Math precision tests
  test_chart_generator.py      # Chart generation, graceful None fallback
  test_data_quality_badges.py  # Data quality badge computation
  test_data_validation.py      # Malformed input, edge cases, corrupt files
  test_developer_menu.py       # Dev menu rate limiting, admin gating
  test_earnings_module.py      # Earnings risk, next date fetching
  test_ibkr_error_handling.py  # Error classification, retry logic
  test_ibkr_sync_full.py       # Full sync pipeline, all 17 error codes
  test_nav_and_intent.py       # NAV updates, intent classification
  test_report_scheduler.py     # Scheduling, dedup, period calculation
  test_risk_deviation.py       # Risk deviation classification
  test_secure_runner.py        # Secure runner admin/rate protection
  test_security.py             # Token masking, input sanitization
  test_stat_bucket.py          # Stat bucket classification
  test_telegram_formatters.py  # Formatting contracts
  test_trade_metrics.py        # Minervini metrics, R calculations
  test_ux_formatting_comprehensive.py  # Hebrew UX, Markdown validity
```

Rules:
- No external network calls in tests.
- Prefer deterministic unit tests with fixtures.
- Tests must protect behavior, not implementation details.
- Add fixtures for trade rows when changing campaign logic.
- `test_adaptive_risk_engine.py` covers: VCP_MANUAL/EP_MANUAL/DATA_INCOMPLETE classification, _is_disc() filter, win rate exclusion of DATA_INCOMPLETE, streak filter on disc-only.

---

### `scripts/archive/`

Archived one-shot fix and debug scripts (not active production code).

These were created during iterative debugging sessions and are no longer needed for normal operation. Kept for historical reference.
