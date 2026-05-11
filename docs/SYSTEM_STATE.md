# Current System State

## Changes — 2026-05-11 (session 7: tracking cleanup + pytest.ini)

### Housekeeping (no production code changed)

**`pytest.ini`** (NEW)
- Added root-level `pytest.ini` with `testpaths = tests` so `pytest -q` works from repo root without collecting `scripts/archive/` files that depend on missing `dotenv`.
- Before: `pytest -q` from root crashed on `scripts/archive/test_xml_ibkr.py` and `test_infra.py`. After: 596 passed, 1 warning.

**`docs/AGENT_TASKS.md`**
- TASK-20260511-001 through TASK-20260511-007 all updated from `todo` → `implemented`.
- Code audit confirmed all tasks were fully implemented in prior sessions but tracking files were not updated.

**`docs/ROADMAP.md`**
- Phase 3 updated: `in progress` → `complete`.
- Phase 3B updated: `planned` → `complete`, all 9 deliverables listed with ✅.
- Phase 5 updated: `in progress` → `complete`, Portfolio Heat Map + Earnings Risk + Discretionary/ALGO/Combined stats added to done list.

### Test suite

- **596 tests, 0 failures** (unchanged — no production code touched)
- `pytest -q` now works from repo root (previously required `pytest tests/ -q`)

---

## Changes — 2026-05-11 (session 6: IBKR pipeline fixes + manual XML upload + NAV key fix)

### Production bugs fixed (all deployed ✅)

**`telegram_bot.py` — Telegram Markdown crash** (PR #5)
- `_build_health_report()` sent with `parse_mode="Markdown"` — IBKR filenames like `ibkr_2026-05-11.xml` contain underscores that Telegram v1 Markdown treats as unclosed italic, crashing the polling thread.
- Fix: removed `parse_mode="Markdown"` from both send calls in `_build_health_report()`, removed `*...*` from title.

**`dashboard.py` — matplotlib ImportError** (PR #6)
- `.background_gradient(subset=["חשיפה %"], cmap="YlOrRd")` requires matplotlib which is not in requirements.txt.
- Fix: removed the cosmetic call; table still renders with all formatted values.

**`ibkr_sync_runner.py` — IBKR sync diagnostic logging** (PR #7)
- Added `log_fn(f"SendRequest raw response: {res.text[:500]}")` on error to expose what IBKR actually returns.

**`telegram_bot.py` — manual sync logs silent** (PR #8)
- `_run_manual_sync_thread` called `run_ibkr_sync()` with default `print()` — unbuffered, invisible in Docker logs.
- Fix: `run_ibkr_sync(log_fn=_bot_log)` — all sync output now in `sentinel_bot.log` and `docker compose logs`.

**`ibkr_sync_runner.py` — ReferenceCode parsing (root cause of all IBKR failures)** (PR #9)
- Code searched `root.find(".//code")` but IBKR returns `<ReferenceCode>` (PascalCase). Every successful SendRequest was treated as "no reference code". Root cause of all IBKR sync failures.
- Fix: `root.find(".//ReferenceCode")` with explicit `is None` check (not `or` — XML Elements with no children are falsy even when they contain text).

**`ibkr_sync_runner.py` — GetStatement wrong URL** (PR #10)
- Hardcoded `www.interactivebrokers.com` for GetStatement. IBKR's SendRequest response includes `<Url>` pointing to `gdcdyn.interactivebrokers.com`.
- Fix: extract `<Url>` from SendRequest response and pass as `fetch_url` param to `get_statement_with_retry`. Added `fetch_url` param with `gdcdyn` default.

**`dashboard.py` — NAV key mismatch** (PR #12)
- Dashboard read `settings.get("current_nav", ...)` — wrong key. `ibkr_sync_runner` writes `"nav"`. Always fell back to `total_deposited: $7,500` even after successful IBKR sync.
- Second bug: `save_settings()` overwrote the entire config file, silently deleting `nav` on any settings change.
- Fix: read `"nav"` key; `save_settings` merges into existing config dict instead of replacing it.

### New feature: manual IBKR XML upload (PR #11)

**`telegram_bot.py`**
- `📤 העלה דוח XML` button in developer menu (fallback when IBKR API is throttled/unavailable).
- Flow: button → bot requests file → user sends XML downloaded from IBKR Flex Query → bot processes identically to auto-sync.
- `_process_uploaded_ibkr_xml(chat_id, message)`: downloads file, validates `.xml`, parses `ChangeInNAV endingValue` + Trades, saves to `_REPORTS_DIR`, updates `sentinel_config.json`, writes `MANUAL_RESULT_FILE`.
- `handle_document_upload()`: telebot `content_types=['document']` handler, active only when `user_state['action'] == 'awaiting_ibkr_xml'`.
- Confirmed working 2026-05-11 21:07: 27 trades + NAV $7,934.27 loaded successfully.

### Test suite

- **596 tests, 0 failures** (up from 588 after session 5 hotfixes)
- 8 new tests in `test_developer_menu.py` covering `_process_uploaded_ibkr_xml`.

---

## Changes — 2026-05-11 (session 5: PDF reports + comprehensive test suite)

### New services and modules

**`ibkr_sync_runner.py`** (NEW — extracted from main.py)
- `IBKR_ERROR_CLASSES`: 17 known error codes mapped to `(class, description)`.
  - Classes: `temporary` (retry), `fatal` (stop immediately), `rate_limit` (log and stop).
- `parse_flex_error(xml_text)` → `dict | None`: classifies IBKR Flex error responses.
- `get_statement_with_retry(ref, token, max_retries, wait_sec)` → `(xml, err)`: retries only on `temporary` errors; aborts on `fatal` to prevent account lockout.
- `run_ibkr_sync(log_fn=print)` → `{"status", "code", "message", "nav"}`: full sync pipeline with NAV extraction and config write.
- Auto-cleans old XML reports, keeps only `_REPORTS_TO_KEEP=3`.

**`account_state.py`** (NEW — single NAV source of truth)
- `load()` → always returns a safe dict, never raises.
- Keys: `nav`, `total_deposited`, `risk_pct_input`, `nav_source` (`broker`/`deposited`/`fallback`), `nav_updated_at`, `age_hours`, `freshness` (`fresh`/`stale`/`critical`/`unknown`), `freshness_label`, `is_stale`, `is_critical`, `ok`.
- Freshness thresholds: `fresh` < 24h, `stale` 24–48h, `critical` > 48h.
- `target_risk_usd(account)` convenience helper.

**`analytics_engine.py`** (NEW — period analytics)
- `compute_period_analytics(df, start, end, account)` → full analytics dict (win_rate, expectancy_r, profit_factor, avg_win_r, avg_loss_r, total_r_net, realized_pnl, missing_stop_rate, oversized_rate, avg_r_per_day, risk_adherence_rate, campaigns_closed).
- `compute_trader_development_score(analytics)` → score 0–100 with breakdown (process/edge/risk/execution), label.
- `compute_verdict(analytics)` → `(text, class)` in Hebrew (strong/mixed/defensive/neutral).
- `compute_period_comparison(current, previous)` → per-metric delta/direction/improving.
- Profit Factor: 99.0 sentinel when no losses; 0.0 when no wins.
- Oversized threshold: actual risk > 125% of target risk USD.

**`report_snapshot_store.py`** (NEW — WoW/MoM comparison)
- `save_snapshot(analytics, label)`: stores analytics dict to `/app/report_state/snapshots/`.
- `load_snapshots()` → list sorted newest-first.
- `load_previous_snapshot(current_label)` → snapshot before given label, or None.

**`chart_generator.py`** (NEW — Plotly static charts for PDF)
- `campaign_r_bars(closed_campaigns, out_dir)` → PNG path or None.
- `setup_performance_bars(analytics, out_dir)` → PNG path or None.
- `weekly_equity_curve(snapshots, out_dir)` → PNG path or None.
- `win_loss_donut(analytics, out_dir)` → PNG path or None.
- All return None gracefully when Plotly/Kaleido unavailable.
- Export standard: 520×260px, brand palette (#2563eb / #059669 / #dc2626).

**`report_renderer.py`** (NEW — HTML+CSS → PDF via WeasyPrint)
- `build_weekly_report(analytics, period_label, coaching, charts, comparison)` → PDF bytes.
- `build_monthly_report(analytics, period_label, coaching, charts, comparison, breakdown_table)` → PDF bytes.
- `build_summary_text(analytics, period_label, report_type)` → Telegram Markdown summary.
- `_period_label(start, end)` → Hebrew month names label.
- Uses Jinja2 templates: `templates/weekly_report.html.j2`, `templates/monthly_report.html.j2`, `templates/report_base.css`.
- RTL Hebrew (`lang="he" dir="rtl"`), LTR spans for numbers/tickers.

**`report_scheduler.py`** (NEW — scheduled PDF delivery service)
- `main()` loop: 60s tick, checks weekday+hour+minute (Israel TZ), dedup via `scheduler_state.json`.
- Weekly: Saturday 08:30, covers Sunday 00:00 → Saturday 23:59:59.
- Monthly: 1st of month 08:40, covers previous full month.
- `_weekly_coaching_insights(analytics)` / `_monthly_coaching_insights(analytics)` → non-empty list always.
- `_weekly_period(ref)` / `_monthly_period(ref)` → (start, end) datetimes.
- `_build_weekly_breakdown(snaps, period_start, period_end)` → filtered snapshot list.

**`report_delivery.py`** (NEW — Telegram PDF sender)
- `send_pdf(path, caption, chat_id, token)` → bool.
- `send_message(text, chat_id, token)` → bool.
- Caption auto-truncated to Telegram's 1024-char limit.
- `_log(msg)`: prints to stdout and appends to `/app/logs/sentinel_report.log`.

### Telegram bot additions (developer menu)

**`telegram_bot.py`** (additive)
- `🛠️ פיתוח` button added to help sub-menu.
- Developer menu (admin-only, rate-limited 2/day + 3h cooldown):
  - Manual IBKR sync → calls `ibkr_sync_runner.run_ibkr_sync()`
  - View last sync result → reads result JSON
  - System health check → NAV freshness + file checks
  - Show config (tokens masked) → `sentinel_config.json` display
  - View last 10 log lines → tail of app log
  - Git pull → runs `git pull origin main`
- `_dev_sync_check()` / `_dev_sync_record()` → rate-limit enforcement via `_DEV_STATE_FILE`.

### docker-compose.yml

- `report-scheduler` service added:
  ```yaml
  report-scheduler:
    command: python3 report_scheduler.py
    environment:
      TZ: Asia/Jerusalem
  ```

### Production bug fixes

**`adaptive_risk_engine.py`** — Defensive `is_win` access:
- 3 occurrences of `c["is_win"]` changed to `c.get("is_win")` (in weighted WR loop, recent_10_wr, all_50_wr, and streak detection).
- Prevents `KeyError` when campaign dict has no `is_win` key (malformed input from Supabase).

**`account_state.py`** — Non-dict JSON guard:
- Added `if not isinstance(data, dict): return _fallback(...)` immediately after `json.load()`.
- Prevents `AttributeError` when `sentinel_config.json` contains a JSON array instead of an object.

### Test suite

**6 new test files, 587 total tests (0 failures):**

| File | Count | Coverage |
|------|-------|---------|
| `tests/test_security.py` | 30 | Token masking, rate limiting, input sanitization, secrets in logs, retry security boundary |
| `tests/test_calculations_comprehensive.py` | 45 | R-multiples, profit factor, expectancy, dev score bounds, oversized boundary, adaptive risk math, NAV freshness precision, period deltas |
| `tests/test_data_validation.py` | 50 | Malformed analytics input, account state edge cases, snapshot store, adaptive risk malformed input, IBKR XML parsing, delivery boundary |
| `tests/test_ux_formatting_comprehensive.py` | 40 | Hebrew month labels, Telegram Markdown validity, verdict system, dev score labels, freshness labels, coaching insights |
| `tests/test_adaptive_risk_engine.py` | 55 | RISK_LADDER invariants, all direction scenarios, heat score math, streak detection, adherence, journal, ladder bounds |
| `tests/test_ibkr_sync_full.py` | 35 | All 17 IBKR error codes, retry logic, full sync pipeline, NAV extraction, report cleanup, required keys |

### Script cleanup

Moved 26 orphaned one-shot fix/debug scripts to `scripts/archive/`. Production code files at root are now only active production modules.

---

## Changes — 2026-05-10 (session 3: adaptive risk engine + proactive alerts)

### adaptive_risk_engine.py (NEW FILE)
- RISK_LADDER: `[0.35, 0.50, 0.75, 1.00, 1.25, 1.50, 2.00, 2.50]` (min 0.35%, max 2.50%)
- `compute_closed_campaigns(df)`: extracts closed campaigns (net_qty ≈ 0) from trades DataFrame, sorted newest→oldest.
- `compute_adaptive_risk(closed_camps, current_risk_pct, nav)`: weighted win rate algorithm, streak detection, step-up/step-down logic, returns full recommendation dict.
- `update_risk_pct(new_pct)`: reads/writes `sentinel_config.json` atomically.
- `log_risk_journal(entry)`: appends decisions to `risk_journal.json` (500 entries).
- `mark_adherence(rec_pct, actual_pct, followed, reason="")`: updates latest entry in `risk_recommendations.json`.
- `compute_adherence_stats()`: returns total/evaluated/followed/not_followed/adherence_pct + last 10 icons.
- `_log_recommendation(rec)`: auto-called by `compute_adaptive_risk`, logs to `risk_recommendations.json` (200 entries).

### engine_core.py
- `compute_market_regime`: now returns raw `signals` dict inside `data` key.

### telegram_formatters.py
- `fmt_regime_report`: renders raw SPY/QQQ signals with ✅/❌.
- `fmt_adaptive_risk_block` (new): adaptive risk recommendation block.

### risk_monitor.py
- Proactive adaptive risk alert at end of `main()`: throttled to once per 24h per direction.
- `send_telegram_with_keyboard` helper.

### telegram_bot.py
- `risk_confirm|YES` / `risk_confirm|NO` callbacks.
- `risk_reject_reason` state handler.
- `/stats` command.

### Runtime files (auto-created, gitignored)
- `risk_recommendations.json` — recommendation log, last 200 entries.
- `risk_journal.json` — full decision journal, last 500 entries.

---

## Changes — 2026-05-10 (session 2: dashboard + telegram upgrade)

### dashboard.py
- `get_cached_market_regime()` — wraps SPY/QQQ fetch + compute_market_regime in `@st.cache_data(ttl=600)`.
- `_warm_symbol_cache`: period changed from "6mo" to "1y".
- Campaign buy records lookup for Add-on quality analysis.
- Command Center: 4-column expander with Trend Template 8 criteria + Add-on quality.
- New "🧠 Minervini Mentor" tab (tabs[4]).
- Visual Journal: days held + R-per-day + actual vs planned risk metrics.
- DB Manager moved to tabs[5].

### engine_core.py (additive)
- `generate_minervini_coaching(...)` — dynamic Hebrew coaching insights.

### telegram_bot.py
- Hierarchical menus (4 categories → sub-menus).
- `/mentor SYMBOL` command.
- `mentor_symbol` user_state action.
- Regime report via `tf.fmt_regime_report()`.
- Coaching insights in `/portfolio`.

### telegram_formatters.py (NEW FILE)
- `fmt_position_card()`, `fmt_summary_footer()`, `fmt_regime_report()`, `fmt_minervini_trend_template()`.

---

## Current date context

Last updated: 2026-05-11 (session 6)

## Production wiring

Docker Compose services:

| Service | Command |
|---------|---------|
| `sentinel-bot` | `python3 main.py` |
| `telegram-bot` | `python3 telegram_bot_secure_runner.py` |
| `dashboard` | `streamlit run dashboard.py` |
| `risk-monitor` | `python risk_monitor.py` |
| `report-scheduler` | `python3 report_scheduler.py` |

## Code state vs deployed state

| Session | Changes | Deployed |
|---------|---------|---------|
| Session 1 (2026-05-09/10) | main.py v16.0, base infra | ✅ Orange Pi |
| Session 2 (2026-05-10) | Dashboard + Telegram upgrade | ✅ Orange Pi |
| Session 3 (2026-05-10) | Adaptive risk engine | ✅ Orange Pi |
| Session 4 (2026-05-10) | Timezone fix + spam fix | ✅ Orange Pi |
| Session 5 (2026-05-11) | PDF reports + test suite + dev menu | ✅ Orange Pi |
| Session 6 (2026-05-11) | 6 bug fixes + XML upload + NAV key fix | ✅ Orange Pi |
| Session 7 (2026-05-11) | pytest.ini + tracking docs cleanup | ✅ docs only |

## IBKR sync status

- Auto-sync (07:00 Israel): configured, Flex Query 1446152 (Last Business Week, XML) — pending first successful morning run
- Manual XML upload: ✅ confirmed working — 27 trades, NAV $7,934.27 loaded 2026-05-11
- Pipeline: SendRequest → `<ReferenceCode>` → wait 15s → GetStatement on `gdcdyn.interactivebrokers.com`

Smoke tests:
- `🛠️ פיתוח` in Telegram developer menu (admin only)
- `/stats` → adherence report
- `pytest -q` on server → must show 587 passed

## Known high-risk areas (unchanged)

1. `telegram_bot.py` is long and should not be rewritten wholesale.
2. NAV/config path consistency must be validated on the server after deployment.
3. Campaign/R calculations are protected by tests — do not change without test coverage.
4. Supabase write flows must remain explicit and traceable.
5. Telegram output must remain Hebrew-friendly and not too verbose.

## Rollback paths

| Service | Rollback command |
|---------|-----------------|
| sentinel-bot | `git revert <commit>` + `docker compose up -d --build sentinel-bot` |
| telegram-bot | `git revert <commit>` + `docker compose restart telegram-bot` |
| report-scheduler | `docker compose stop report-scheduler` — safe, no state |
| engine_core | Revert is safe — no existing functions changed |
| Supabase | No schema changes made in session 5 |
