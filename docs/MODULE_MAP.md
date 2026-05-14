# Module Map

This file explains the purpose of the main files and how they depend on each other.
**Last major update**: 2026-05-14 (end of Sprint 11 P4).

## Production modules (root level)

### `engine_core.py`

Core analytical engine.

Responsibilities:
- market data retrieval and caching through yfinance
- ATR and moving-average calculations
- sector / relative strength mapping
- distribution and accumulation day detection (incl. **`dist_25d` + `distribution_cluster`** — Mark's 20-25 session cluster, Sprint 11 MEDIUM 11)
- trade-stage classification
- position scoring + **age-gated label mapping** (`map_score_to_status(score, days_held=...)` — no Power before day 10, no Weak before day 15, Sprint 11 HIGH 9)
- hard-rule risk evaluation
- management action suggestions
- open campaign aggregation (incl. **`risk_pct_at_entry` + `nav_at_entry` surface** from first BUY trade, migration 003)
- market regime calculation
- **Minervini Follow-Through Day** (`compute_market_ftd(spy_hist)` — Sprint 11 HIGH 6)
- Minervini Trend Template — **8 criteria** (`compute_trend_template_full`). Legacy 5-criterion `get_minervini_analysis` is DEPRECATED (Sprint 11 P4).
- R/day, MAE/MFE, add-on quality
- ALGO Observer Mode gating: `is_algo_position()`, `classify_management_mode()`
- Stat bucket classification: `classify_stat_bucket()`, `is_stat_countable()`, `is_discretionary_bucket()`
- Position state machine: `compute_position_state()` → RUNNER / BROKEN / DEAD_MONEY / WORKING / etc.
- Risk analytics: `compute_giveback_from_peak()`, `compute_risk_deviation()`, `compute_algo_oversight_summary()`
- **Time efficiency** (`map_time_efficiency(days_held, total_r, setup_type=None)` — setup-aware, Sprint 11 MEDIUM 10)
- Suggested trail stop (`compute_suggested_trail_stop`) owns R≥5 zone; task_engine owns 3R..5R

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

RISK_LADDER (Sprint 8 refinement): `[0.25, 0.40, 0.60, 0.85, 1.15, 1.50, 2.00]`
— 7 rungs, no 2.50% outlier, finer steps at the low end.

Direction logic:
- heat ≥ 60% and loss_streak < 3 → `up` (+1 step)
- heat < 40% or loss_streak ≥ 3 → `down_fast` (−2 steps)
- otherwise → `hold`

Four UP-step gates (must ALL pass to ladder up):
1. **Closed-campaigns gate** (B3): `RISK_STEP_UP_MIN_CLOSED_CAMPAIGNS = 5`
   stat-countable closed campaigns since the last `risk_changed_ts`.
2. **Cold-regime gate** (Sprint 11 HIGH 5): `ec.compute_market_regime` Cold
   → force `direction = "hold"`. Down stays fast.
3. **Per-bucket heat gate** (Sprint 11 HIGH 7): when both EP and VCP have
   ≥3 stat-countable campaigns, the WEAKEST bucket's s9 score must be ≥60.
4. **Drawdown auto-cut**: `compute_drawdown_recommendation` — 30d cumPnL
   ≤ -8% NAV → force risk to 0.40%.

Other Sprint 11 additions:
- `_last_risk_change_ts()` — anchor for the closed-campaigns gate.
- `_count_stat_countable_closed_since(camps, ts)` — counter helper.
- Per-bucket short-window heat (`bucket_scores = {"EP": ..., "VCP": ...}`).

Rules:
- `is_win` must be accessed via `.get("is_win")` — never `["is_win"]`.
- DATA_INCOMPLETE campaigns must never enter Win Rate or Expectancy.
- `compute_closed_campaigns()` is the single source of truth for closed campaign stats — do not reimplement inline.
- New gates are FAIL-OPEN (e.g., `compute_market_regime` raises → skip gate, not block user).

---

### `setup_profile.py` (Sprint 11 P2)

Per-setup methodology parameters. Source of truth for thresholds that
DIFFER by setup type.

Profiles (frozen dataclasses):

| Setup | dead_money_days | dead_money_r | profit_protect_r | runner_r | max_initial_stop_pct |
|---|---|---|---|---|---|
| VCP   | 21 | 0.3  | 2.0 | 5.0 | 8.0% |
| EP    | 10 | 1.5  | 1.5 | 3.0 | 8.0% |
| SWING | 14 | 0.5  | 2.0 | 4.0 | 10.0% |
| ALGO  | (neutralized) | | | | |

API:
- `get_profile(setup_type)` — case-insensitive, VCP_MANUAL→VCP, EP_MANUAL→EP, unknown→VCP fallback.
- `validate_initial_stop(entry, init_stop, setup_type) -> dict` —
  returns grade `in_spec` / `marginal` / `out_of_spec` / `missing` + Hebrew label.

Rules:
- Frozen dataclass — must not mutate at runtime.
- All thresholds must be cited in the research audit doc before changing.
- Tests in `tests/test_setup_profile.py` pin specific values.

---

### `task_engine.py` (Sprint 10 → 11)

Pure-functions task computation per open campaign. Stops-only MVP.

Five rules (urgency-sorted):

| # | Kind | Urgency | Condition | Action |
|---|---|---|---|---|
| 1 | `stop_breach` | 100 | open_r ≤ -1 OR price ≤ stop | exit |
| 2 | `dead_money` (setup-aware) | 80 | days > profile.dead_money_days AND open_r < profile.dead_money_r | exit |
| 3 | `break_even_2r` (setup-aware) | 60 | open_r ≥ profile.profit_protect_r AND stop ≤ entry | update_stop to entry |
| 4 | `trail_up_3r` (setup-aware) | 55 | open_r ≥ profile.profit_protect_r+1 AND open_r < profile.runner_r | update_stop to entry + 1R |
| 5 | `loose_stop` | 50 | initial_stop grade == out_of_spec | review |

API:
- `Task` dataclass: campaign_id, symbol, kind, urgency, title, detail, suggested_level, suggested_action
- `compute_open_tasks(positions, snoozed, now_ts)` — returns sorted task list
- `group_by_symbol(tasks)` — convenience for UI menu
- `render_task_line(task)` / `render_task_detail(task)` — Hebrew renderers

Rules:
- ALGO setups skipped entirely.
- `trail_up_3r` DEFERS when open_r ≥ profile.runner_r — engine_core's MA-based trail owns RUNNER zone.
- All thresholds are setup-aware via `setup_profile.get_profile()`.

---

### `task_state.py` (Sprint 10)

JSON-persisted task acks + snoozes. State file: `/app/task_state.json`.

Schema:
```
{
  "snoozed": {"<campaign_id>|<kind>": <expiry_unix>},
  "last_action": {
    "<campaign_id>|<kind>": {
      "action": "approve"|"snooze"|"dismiss",
      "ts": <unix>,
      "before": <value_or_null>, "after": <value_or_null>
    }
  }
}
```

API (all functions take optional `path` parameter — resolves at call time
to make `TASK_STATE_FILE` monkeypatchable):
- `load_state(path=None) -> dict`
- `save_state(state, path=None) -> bool` — atomic (tmp + os.replace)
- `get_snoozes(path=None, now_ts=None)` — auto-purges expired
- `snooze_task(dedup_key, duration_sec, path=None, now_ts=None)`
- `dismiss_task(dedup_key, path=None, now_ts=None)` — 30d snooze
- `approve_task(dedup_key, before, after, path=None, now_ts=None)` — + 1h grace
- `last_action(dedup_key, path=None) -> dict | None`

Rules:
- Atomic writes only (tmp + os.replace).
- Never raises — returns False / empty on any failure.
- `_resolve_path()` reads `TASK_STATE_FILE` at call time, NOT as default argument (Sprint 11 P2 CI fix — default-arg-binding bug).

---

### `telegram_tasks.py` (Sprint 10)

UI handlers for the 📋 סקירת משימות feature.

Five screens / one text-input mode:
1. `handle_tasks_review(chat_id)` — list of symbols with task counts
2. `show_symbol_tasks(chat_id, sym)` — tasks for one symbol
3. `show_task_detail(chat_id, cid, kind)` — detail + 4 buttons
4. `show_approve_confirm(...)` — 2-step confirm dialog
5. `apply_confirmed_value(...)` — execute Supabase write + audit_log
+ `start_manual_edit` / `apply_manual_edit_value` — text input mode
+ `snooze_short` / `dismiss_long` — snooze actions

Callback data scheme: `task|<verb>|<campaign_id>|<kind>[|<value>]`

Rules:
- `_find_task` re-evaluates the rule before applying — if state changed
  (stop already moved, position closed), shows "המשימה כבר לא רלוונטית".
- Supabase write failure ABORTS audit + state record (no silent inconsistency).
- audit_logger entry on every approve.

---

### `setup_performance.py` (Sprint 11 P1)

Per-setup_type breakdown of closed campaigns for the `/setup_stats` Telegram view.

API:
- `compute_setup_breakdown(closed_campaigns) -> dict` — keys: VCP / EP / SWING / ALGO / (other)
  - Each value: n / wins / losses / win_rate / total_pnl_usd / avg_pnl_usd / payoff / total_r / avg_r / stat_countable / label
- `best_and_worst(breakdown)` — surfaces the comparison insight; requires n≥2 per bucket and stat_countable
- `render_breakdown(breakdown) -> str` — Telegram-friendly RTL Hebrew

Rules:
- VCP_MANUAL collapses into VCP for display.
- ALGO marked `stat_countable=False`, excluded from best/worst comparison.

---

### `audit_logger.py` (Sprint 6)

Append-only audit trail (migration 002 `audit_log` table). Fail-open.

API:
- `log_action(sb, action, *, chat_id, before, after, metadata)` — returns True/False, never raises

Action codes:
- `risk_pct_change` — adaptive risk approved
- `addon_confirm` — add-on confirmed
- `dev_pin_record_failure` / `dev_pin_activate_session` — dev menu access
- `stop_update_via_task` — Sprint 10 — every approve action via Task Review
- `task_acknowledged` — Sprint 10 — exit-type tasks (no Supabase write)

Rules:
- NEVER raise — caller's logic must not block on audit failure.
- Caller is responsible for the actual data mutation (audit only records it).

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

Test suite (**1,622 tests** as of Sprint 11 P4, 2026-05-14 — branch
`claude/integration-pi-and-main-2026-05-14`).

Coverage on core modules:
- `engine_core` 59%, `adaptive_risk_engine` 89%, `analytics_engine` 99%, `addon_risk_engine` 86%
- Combined: **71.4%** (CI gate: 67%)

Notable test files added in Sprint 10/11:
- `test_task_engine.py` (37 tests) — 5 task-rule classes + grouping/sort
- `test_task_state.py` (20 tests) — atomic writes + snooze semantics
- `test_telegram_tasks.py` (18 tests) — UI wiring + edit-mode validation
- `test_morning_briefing.py` (19 tests) — TZ gate + briefing text
- `test_setup_performance.py` (24 tests) — breakdown + best/worst
- `test_setup_profile.py` (24 tests) — profile values + validate_initial_stop
- `test_b1_campaign_target_locked.py` (13 tests) — migration 003 surface
- `test_b3_closed_campaigns_gate.py` (14 tests) — ladder gate logic
- `test_sprint11_p3a.py` (14 tests) — age gate + regime gate
- `test_sprint11_p3b.py` (12 tests) — trail reconciliation + dead-money
- `test_sprint11_p3c.py` (8 tests) — per-bucket heat + distribution 25d
- `test_market_ftd.py` (8 tests) — FTD market signal
- `test_ibkr_1001_fixes.py` (27 tests) — IBKR cooldown + period detection
- `test_ibkr_config_visibility.py` (13 tests) — bot_health + startup log
- `test_session_2026_05_14_feedback.py` (14 tests) — display/UX fixes
- `test_c1_ux_shortcuts.py` (17 tests) — slash shortcuts
- `test_risk_monitor_log_tee.py` (11 tests) — sentinel_risk.log fix (#33)

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
