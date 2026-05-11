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

Adaptive risk recommendation engine.

Responsibilities:
- `compute_closed_campaigns(df)` → closed campaigns list.
- `compute_adaptive_risk(campaigns, current_risk_pct, nav)` → recommendation dict.
- `update_risk_pct(new_pct)` → writes to sentinel_config.json.
- `log_risk_journal(entry)` → appends to risk_journal.json (500 cap).
- `mark_adherence(rec_pct, actual_pct, followed, reason)` → updates risk_recommendations.json.
- `compute_adherence_stats()` → adherence statistics.

RISK_LADDER: `[0.35, 0.50, 0.75, 1.00, 1.25, 1.50, 2.00, 2.50]`

Direction logic:
- heat ≥ 60% and loss_streak < 3 → `up` (+1 step)
- heat < 40% or loss_streak ≥ 3 → `down_fast` (−2 steps)
- otherwise → `hold`

Rules:
- `is_win` must be accessed via `.get("is_win")` — never `["is_win"]`.

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
- developer menu (🛠️ — admin-only, rate-limited)

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
- Visual inspection of trades and portfolio state.
- Command Center: Trend Template 8 criteria + Add-on quality per position.
- Minervini Mentor tab: coaching insights and streak analysis.
- Visual Journal: closed campaign metrics including R/day.

Rules:
- Dashboard can be more verbose than Telegram.
- Must identify fallback/estimated values clearly.
- Reuse engine functions rather than re-implementing calculations.

---

### `risk_monitor.py`

Automated risk monitoring service (runs every 300s).

Responsibilities:
- periodic position risk monitoring
- proactive adaptive risk alerts (once/24h per direction)
- market-hours gate for repeat cooldown alerts

Rules:
- Must not spam Telegram.
- Must not auto-mutate trade management state.
- Repeat cooldown alerts only during US market hours (11:00–21:00 UTC Mon–Fri).

---

## Infrastructure

### `docker-compose.yml`

Production wiring.

Active services:
```yaml
sentinel-bot:    python3 main.py                       # IBKR sync
telegram-bot:    python3 telegram_bot_secure_runner.py # Telegram UI
dashboard:       streamlit run dashboard.py            # Web dashboard
risk-monitor:    python risk_monitor.py                # Monitoring
report-scheduler: python3 report_scheduler.py         # PDF reports
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

Test suite (587 tests).

Structure:
```
tests/
  test_account_state.py        # NAV loading, freshness, fallback
  test_adaptive_risk_engine.py # RISK_LADDER, directions, streaks, adherence
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
  test_risk_deviation.py       # Risk deviation classification (placeholder)
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

---

### `scripts/archive/`

Archived one-shot fix and debug scripts (not active production code).

These were created during iterative debugging sessions and are no longer needed for normal operation. Kept for historical reference.
