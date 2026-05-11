# Architecture Decision Log

This file records significant architecture or design decisions made during development.

Each entry explains what was decided, why, and what alternatives were considered.

---

## DEC-20260509-001 — Parallel symbol pre-fetch via ThreadPoolExecutor

Date: 2026-05-09
Status: implemented

### Decision

Use `concurrent.futures.ThreadPoolExecutor` to pre-fetch live prices, 6-month histories, and sector data for all open positions simultaneously before the serial analysis loop in `compute_live_portfolio_data`.

### Rationale

The dashboard was making N sequential network calls (each with 0.5–1.5s smart_delay) for N open positions. Pre-fetching in parallel reduces wall time from N×1s to ~1.5s regardless of position count.

### Alternatives considered

- **yf.download() batch**: faster for price data but returns last close, not live price. Accuracy tradeoff not acceptable.
- **Async/await**: would require restructuring the entire Streamlit app. Overkill for this use case.
- **Increase cache TTL only**: does not help on first load or after cache expiry.

### Constraints

- engine_core.YF_CACHE is a module-level dict. Python's GIL makes simple dict reads/writes safe across threads.
- smart_delay() still fires per thread — this is intentional to avoid Yahoo Finance rate limiting. Total wait is max(delays) not sum(delays).
- @st.cache_data on compute_live_portfolio_data means the pre-fetch only runs on cache miss (every 180s).

---

## DEC-20260509-002 — Minervini Trend Template: new function, not modifying existing

Date: 2026-05-09
Status: implemented

### Decision

Create `compute_trend_template_full()` with all 8 Minervini criteria. Keep existing `get_minervini_analysis()` (5 criteria) unchanged.

### Rationale

`get_minervini_analysis()` is consumed by `telegram_bot.py` and returns a formatted Hebrew string with a score out of 10. Changing its score formula would break Telegram display without a migration plan.

### Consequence

Two coexisting Trend Template functions:
- `get_minervini_analysis()`: Telegram-facing, 5 criteria, stable.
- `compute_trend_template_full()`: dashboard-facing, 8 criteria, structured dict.

A future refactor should unify these once the Telegram display is updated.

---

## DEC-20260509-003 — IBKR sync state in local JSON, not Supabase

Date: 2026-05-09
Status: implemented

### Decision

Track IBKR sync state in `/app/ibkr_sync_state.json` on the local filesystem.

### Rationale

Writing sync state to Supabase would introduce a network dependency in the sync loop itself. If Supabase is down, the sync loop would also fail to record state. A local JSON file is self-contained, survives Supabase outages, and is easily inspectable for debugging.

### Alternatives considered

- **Supabase table**: more visible but creates circular dependency.
- **Extend sentinel_config.json**: mixes account settings with sync state.
- **Plain text file (old approach)**: insufficient for multi-field state.

### Constraint

If the /app volume is not persistent across Docker rebuilds, state resets. Acceptable — worst case is one extra sync attempt on restart.

---

## DEC-20260510-001 — Docker timezone: TZ env var + explicit ZoneInfo in code

Date: 2026-05-10
Status: implemented

### Decision

Set `TZ=Asia/Jerusalem` in docker-compose.yml for affected services AND use `ZoneInfo("Asia/Jerusalem")` explicitly in main.py code.

### Rationale

Docker containers default to UTC regardless of host OS timezone. `datetime.now()` returned UTC, causing the IBKR sync window (intended 07:00–11:00 Israel) to run at 10:00–14:00 Israel instead — 3 hours late.

Two-layer fix provides defense in depth:
- `TZ` env var: makes `datetime.now()` return Israel time — fixes the symptom for all datetime calls.
- `ZoneInfo` in code: makes the code self-documenting and correct even if TZ var is missing.

### Alternatives considered

- **pytz**: not already in requirements.txt; ZoneInfo is stdlib (Python 3.9+).
- **Fixed UTC offset (timedelta(hours=3))**: doesn't handle DST correctly.
- **TZ env var only**: works but leaves code intention unclear if var is ever forgotten.

### Constraint

`python:3.10-slim` has `zoneinfo` but no timezone data. Added `tzdata` pip package to requirements.txt to supply data on slim images.

---

## DEC-20260510-002 — Alert spam: market-hours gate for repeat cooldown alerts

Date: 2026-05-10
Status: implemented

### Decision

Repeat cooldown alerts in risk_monitor.py (same status, same alert key, 6h cooldown) only fire during US market hours: 11:00–21:00 UTC, Mon–Fri. First-time alerts and escalations (status worsened) are unaffected and fire at any hour.

### Rationale

PLTR "Broken" status fired repeat alerts at 00:13, 06:16, 12:19 Israel — all outside market hours when no action is possible. The 6-hour cooldown was correct in duration but not gated on market availability.

### Alternatives considered

- **Increase cooldown to 24h**: simpler, but too blunt — would delay an important escalation during market hours.
- **Market-hours check only (no cooldown)**: risk of flooding during volatile market sessions.

### Constraint

Uses UTC-based range (11:00–21:00 UTC) to avoid dependency on tzdata in Docker. Covers US pre-market to after-hours in all Israel DST/non-DST scenarios.

---

## DEC-20260510-003 — Market regime cached at Streamlit layer (TTL=600s)

Date: 2026-05-10
Status: implemented

### Decision

Wrap `compute_market_regime()` + its SPY/QQQ fetch in a `@st.cache_data(ttl=600)` Streamlit function, `get_cached_market_regime()`. This is separate from engine_core's own `YF_CACHE` (TTL=300s).

### Rationale

Streamlit re-runs the entire script on every user interaction (button click, filter change, etc.). On each re-run, `ec.get_cached_history("SPY", "1y", "1d")` was called synchronously in the sidebar before any tab content rendered. Even though engine_core has its own 5-min cache, the pandas market regime computation itself added overhead on every re-run.

Streamlit's `@st.cache_data` caches the return value across re-runs within the same process, not just within the same seconds. This means repeated user interactions (changing filters, viewing different tabs) get an instant regime result without any computation.

### Alternatives considered

- **engine_core cache only (TTL=300s)**: helps with network calls but not with Streamlit re-run overhead.
- **Store regime in st.session_state**: works but requires manual invalidation logic.

### Constraint

The returned DataFrame (`spy_hist`) is not returned from the cached function to avoid pickle overhead. After calling `get_cached_market_regime()`, `spy_hist` is retrieved separately via `ec.get_cached_history()` — which is a near-instant cache hit since the cached function just warmed it.

---

## DEC-20260510-004 — Hierarchical Telegram menus (4 categories → sub-menus)

Date: 2026-05-10
Status: implemented

### Decision

Replace the flat 5-button main menu with 4 category buttons (מצב תיק / ניתוח / יומן / עזרה) that each lead to a sub-menu. All original commands remain reachable.

### Rationale

The original menu had 5 buttons with no logical grouping. As features were added (market regime, drill-down, etc.), the menu grew cluttered. A hierarchical structure scales cleanly as features are added.

### Alternatives considered

- **Inline keyboard buttons**: can't be used for ReplyKeyboard (persistent menu) flows — requires callback queries.
- **Single command list only (no keyboard)**: less discoverable for mobile users.

### Constraint

All existing slash commands (/portfolio, /next, /trade, /analyze) remain functional and bypass the menu hierarchy. Backward compatibility preserved.

---

## DEC-20260510-005 — telegram_formatters.py as separate formatting module

Date: 2026-05-10
Status: implemented

### Decision

Create `telegram_formatters.py` as a pure formatting helper module (no Supabase, no bot, no engine_core imports). Import it into `telegram_bot.py` as `import telegram_formatters as tf`.

### Rationale

Per the Phase 4 refactor plan in ROADMAP.md, `telegram_bot.py` should be split into smaller modules. Starting with a `telegram_formatters.py` that only contains string-building functions is the lowest-risk first step — it has no logic, no state, and no network calls. It can grow independently of the main bot file.

### Alternatives considered

- **Inline formatting in telegram_bot.py (status quo)**: makes the file harder to maintain.
- **Full Phase 4 refactor now**: too large for one session — risk of breaking existing flows.

### Constraint

telegram_formatters.py must not import telebot, supabase, or engine_core to remain a pure utility. If a formatter needs computed data, the caller computes it and passes it in as a parameter.

---

## DEC-20260510-006 — Adaptive risk state stored in local JSON, not Supabase

Date: 2026-05-10
Status: implemented

### Decision

Store risk recommendations log (`risk_recommendations.json`) and risk decision journal (`risk_journal.json`) as local JSON files. Do not write to Supabase.

### Rationale

These are operational/meta files about the system's own behavior, not trading data. Writing them to Supabase would require schema changes (new tables), Supabase connectivity for every recommendation cycle, and would mix financial truth data with system telemetry.

Two separate files serve different purposes:
- `risk_recommendations.json` (200 entries): lightweight adherence tracker, updated live by callbacks.
- `risk_journal.json` (500 entries): full decision audit log with reasons, read for analysis.

### Alternatives considered

- **Single file**: would mix recommendation metadata with decision notes, making each file harder to reason about.
- **Supabase table**: high risk, requires migration, couples the risk monitor to DB availability.
- **sentinel_config.json extension**: mixes account settings with operational history.

### Constraint

Both files are runtime-only. They must be added to `.gitignore` to avoid committing ephemeral state to the repository. If the Docker volume is ephemeral, history is lost on rebuild — acceptable (data is operational, not financial truth).

---

## DEC-20260510-007 — Proactive risk alerts throttled to once per 24h per direction

Date: 2026-05-10
Status: implemented

### Decision

Send a proactive risk change alert at most once per 24 hours, and only when the direction (`up` / `down_fast`) changes from the last alert sent. Direction `hold` never triggers an alert.

### Rationale

The risk monitor runs every 300 seconds. Without throttling, the same "step up risk" recommendation would fire every 5 minutes during a winning streak. The 24h window matches the practical update cadence (risk is adjusted at most once per trading day). Direction-change gating ensures a new alert fires immediately if the situation deteriorates from "up" to "down_fast", regardless of the 24h window.

### Alternatives considered

- **Once per trading session**: harder to define for weekend/holiday edges.
- **Manual trigger only**: defeats the "proactive" goal.
- **Always fire on direction change, no time throttle**: could flood if data fluctuates around a threshold boundary.

### Constraint

State is stored in `risk_monitor_state.json["risk_alert"]`. If this file is deleted, the next cycle will fire regardless of recency — acceptable as a safe default.

---

## DEC-20260510-008 — Risk confirmation flow: inline keyboard callbacks, not slash commands

Date: 2026-05-10
Status: implemented

### Decision

Use Telegram InlineKeyboardMarkup with `callback_data` for the YES/NO risk confirmation flow. Rejection reason is collected via a follow-up free-text message using `user_state`.

### Rationale

Inline buttons are the standard Telegram UX for binary decisions. They stay attached to the original alert message, making the flow self-contained. The rejection reason must be free text (cannot be a button) — collecting it via `user_state["action"] = "risk_reject_reason"` reuses the established multi-step flow pattern already in `telegram_bot.py`.

### Alternatives considered

- **Slash commands (`/confirm`, `/reject`)**: not discoverable, user must type them.
- **Reply keyboard buttons**: would replace the persistent menu, breaking navigation state.

### Constraint

The `risk_confirm` callback handler must be added before the generic `v|` handler in `handle_queries` to avoid routing conflicts. Callback data format: `risk_confirm|{YES|NO}|{rec_pct}|{curr_pct}` — all fields needed because callback context is stateless in telebot.

---

## DEC-20260511-002 — ibkr_sync_runner.py extracted from main.py

Date: 2026-05-11
Status: implemented

### Decision

Extract all IBKR sync logic from `main.py` into `ibkr_sync_runner.py` as a standalone, testable module.

### Rationale

`main.py` had no unit tests because its sync logic was embedded in a `while True` loop with `os.environ` reads and file writes interspersed throughout. Extracting to `ibkr_sync_runner.py` allows:
- Full unit test coverage of all 17 IBKR error codes.
- Reuse by the developer menu in `telegram_bot.py` without importing `main.py`.
- Isolation of the fatal-error security boundary (no retry on auth failures).

### Consequence

`main.py` now delegates to `ibkr_sync_runner.run_ibkr_sync()`. The module boundary allows patching in tests without running the full loop.

### Alternatives considered

- **Test main.py directly**: circular — main loop runs indefinitely and is tightly coupled to env vars.
- **Inline the sync code in telegram_bot.py**: duplication; two places to maintain.

---

## DEC-20260511-003 — account_state.py as single NAV source of truth

Date: 2026-05-11
Status: implemented

### Decision

Create `account_state.py` as the authoritative module for reading NAV and account settings from `sentinel_config.json`. All services must use `account_state.load()`.

### Rationale

Multiple services (telegram_bot.py, risk_monitor.py, adaptive_risk_engine.py, report_scheduler.py) were reading `sentinel_config.json` independently with slightly different fallback logic and key names. This led to inconsistent behavior when the file was missing, corrupted, or had wrong types.

`account_state.load()` guarantees:
- Never raises — always returns a safe dict with known keys.
- Consistent fallback value ($7,500) and `nav_source="fallback"` when file is missing.
- Explicit freshness classification with labeled status.
- Non-dict JSON guard: if file contains `[...]` instead of `{...}`, returns fallback.

### Constraint

`sentinel_config.json` remains the storage format. `account_state.py` is a read layer only — it does not write. Writes go through `adaptive_risk_engine.update_risk_pct()` (for risk_pct) and `ibkr_sync_runner.run_ibkr_sync()` (for nav).

---

## DEC-20260511-004 — PDF reports via WeasyPrint + Jinja2 (not a Streamlit export)

Date: 2026-05-11
Status: implemented

### Decision

Generate PDF reports using WeasyPrint (HTML→PDF) + Jinja2 (template rendering), delivered as Telegram file attachments. Not exported from the Streamlit dashboard.

### Rationale

Streamlit does not offer a reliable headless PDF export path. WeasyPrint renders pixel-accurate Hebrew RTL PDFs from HTML+CSS, including page headers/footers via CSS `position: running()`. Jinja2 templates allow clean separation of content from formatting logic.

### PDF structure

- `templates/report_base.css`: shared styles, RTL base (`lang="he" dir="rtl"`), LTR number spans.
- `templates/weekly_report.html.j2` / `templates/monthly_report.html.j2`: Jinja2 report templates.
- `chart_generator.py`: Plotly → Kaleido → PNG files, embedded as `<img>` in HTML.
- `report_renderer.py`: Jinja2 render → WeasyPrint → PDF bytes.

### Alternatives considered

- **Streamlit PDF export (pdfkit/wkhtmltopdf)**: poor Hebrew RTL support, no running headers.
- **ReportLab**: programmatic PDF without HTML — verbose, no CSS RTL.
- **LaTeX**: correct RTL with babel/Hebrew package, but requires TeX environment, overkill.

### Constraint

Kaleido (for Plotly PNG export) is an optional dependency. All chart functions return `None` gracefully when unavailable. Report renderer handles `None` charts without error — the PDF is generated without charts in that case.

---

## DEC-20260511-005 — report-scheduler as a standalone Docker service

Date: 2026-05-11
Status: implemented

### Decision

Run `report_scheduler.py` as a separate Docker service (`report-scheduler`) with its own container, rather than embedding scheduling in an existing service.

### Rationale

- Scheduling logic (60s tick, Saturday/1st-of-month checks) runs indefinitely and should not block or complicate `telegram-bot` or `risk-monitor`.
- Separate container allows independent restart without affecting live Telegram responses.
- `TZ=Asia/Jerusalem` env is set on the container so `datetime.now()` returns Israel time, same pattern as `sentinel-bot`.

### Alternatives considered

- **APScheduler inside telegram-bot**: couples delivery to bot lifecycle; if bot restarts, scheduled report is missed.
- **Cron job on host**: requires host-level configuration, not portable across environments.
- **main.py combined service**: main.py is already responsible for IBKR sync; mixing reporting would blur responsibilities.

---

## DEC-20260509-004 — Planned R:R deferred: requires Supabase schema change

Date: 2026-05-09
Status: deferred / blocked

### Decision

Do not implement true planned R:R in this session. Defer until `target_price` field is added to the Supabase `trades` table.

### Rationale

True planned R:R = (target_price - entry) / (entry - initial_stop). No target price field exists in current schema. Using a fabricated proxy would violate the data contract: "The system must show truth only."

### What is implemented instead

- Planned risk $ (target_risk_usd from config) vs actual risk $ (original_campaign_risk).
- Planned risk % of NAV vs actual risk % of NAV.

### Prerequisites for full implementation

1. Add `target_price NUMERIC` to Supabase trades table.
2. Update docs/DATA_CONTRACTS.md.
3. Update DB Manager in dashboard for target price entry.
4. Update Telegram backlog flow to capture target price.
This is a HIGH risk schema change — requires a dedicated task.

---

## DEC-20260511-001 — ALGO Observer Mode: Sentinel does not manage external ALGO positions

Date: 2026-05-11
Status: implemented

### Decision

Sentinel must not issue stop-raise, exit, or management instructions to positions managed by an external ALGO system. Sentinel's role for ALGO positions is: oversight, measurement, deviation alerting, and data integrity — not trade management.

### Formal rule encoded in engine_core.py

`evaluate_position_engine()` now checks `classify_management_mode()` before calling `build_management_action()`. If `management_mode == "algo_observed"`, the function returns `action = "מנוהל חיצונית — בקרה בלבד"` and skips all discretionary management logic.

### Three new runtime fields (derived, not stored in Supabase)

- `management_mode`: `algo_observed` | `manual_managed`
- `risk_basis`: `True` | `Target` | `Unknown`
- `risk_visibility_score`: 0–100

### Display rules

- ALGO positions never show `Current Stop: $0.00` — display: `External / Unknown`.
- Telegram ALGO block shows risk basis and visibility score.
- AI context export shows `management_mode` and `risk_basis` per position.
- ALGO does not receive `Action Required` alerts — maximum actionability is `Review Required`.

### Alternatives considered

- **Show $0.00 as-is**: misleading — looks like a data error or missing stop.
- **Hide ALGO positions from analysis entirely**: loses oversight value.
- **Run full discretionary engine for ALGO**: produces wrong management instructions.

### Known ALGO symbols

Defined in `engine_core.ALGO_SYMBOLS` (derived from `ALGO_SYMBOL_LIMITS`): QQQ, TSLA, JPM, PLTR, HOOD.
Classification is primarily by `setup_type == "ALGO"`, with symbol as secondary fallback.

---

## DEC-20260511-006 — IBKR GetStatement URL: use `<Url>` from SendRequest response

Date: 2026-05-11
Status: implemented

### Decision

Extract the `<Url>` element from IBKR's SendRequest XML response and pass it as `fetch_url` to `get_statement_with_retry()`. Default to `gdcdyn.interactivebrokers.com` if absent.

### Rationale

Production logs showed SendRequest returning `<Url>https://gdcdyn.interactivebrokers.com/...</Url>` but the code hardcoded `www.interactivebrokers.com`. IBKR documents that GetStatement must be called on the URL provided in the SendRequest response — a different subdomain. Using the wrong host caused all GetStatement calls to fail silently or return errors.

### Alternatives considered

- **Hardcode `gdcdyn`**: works today but brittle — IBKR could change the subdomain.
- **Try both hosts**: wasteful, unclear fallback semantics.

### Constraint

`fetch_url` param added to `get_statement_with_retry()` with a sensible default. Tests mock the URL so they are not affected by host changes.

---

## DEC-20260511-007 — sentinel_config.json: `"nav"` is the authoritative NAV key

Date: 2026-05-11
Status: implemented

### Decision

All readers and writers of `sentinel_config.json` must use the key `"nav"` for the IBKR-synced account value. `"current_nav"` is deprecated and must never be introduced.

### Rationale

`ibkr_sync_runner.py` and `account_state.py` always used `"nav"`. The dashboard used `"current_nav"` — a typo/inconsistency that meant the dashboard always showed the `total_deposited` fallback ($7,500) even after successful IBKR sync. Additionally, `save_settings()` in `dashboard.py` overwrote the entire config dict, silently deleting `"nav"` whenever the user changed any setting.

### Fix applied

- `dashboard.py` line 99: `settings.get("nav", ...)` (was `"current_nav"`).
- `save_settings()`: merges updates into existing config dict instead of replacing it.

### Contract (as of session 6)

| Key | Writer | Reader |
|-----|--------|--------|
| `nav` | `ibkr_sync_runner.run_ibkr_sync()`, `_process_uploaded_ibkr_xml()` | all modules via `ec.get_nav_with_freshness()` or `account_state.load()` |
| `nav_updated_at` | `ibkr_sync_runner`, `_process_uploaded_ibkr_xml()` | `engine_core.get_nav_with_freshness()` (freshness calc) |
| `total_deposited` | `dashboard.save_settings()` | all modules (base capital / fallback) |
| `risk_pct_input` | `dashboard.save_settings()`, `adaptive_risk_engine.update_risk_pct()` | all modules |

### Constraint

Any future writer of `sentinel_config.json` must read the existing file first and merge, never replace. Pattern: `cfg = json.load(f); cfg["key"] = val; json.dump(cfg, f)`.

---

## DEC-20260511-008 — Manual IBKR XML upload as API-throttle fallback

Date: 2026-05-11
Status: implemented

### Decision

Add `📤 העלה דוח XML` to the developer menu. When the IBKR API returns error 1001 (throttled/unavailable), the user can download the Flex Query XML from the IBKR website and upload it directly in Telegram.

### Rationale

IBKR imposes per-token throttling after many rapid API requests (as occurred during debug sessions). The cooldown period can be hours. Without a manual fallback, the NAV would remain stale and risk calculations would use $7,500. Uploading the XML achieves the same outcome as a successful auto-sync without any IBKR API call.

### Processing contract

`_process_uploaded_ibkr_xml()` processes the file identically to `run_ibkr_sync()`:
- Validate `.xml` extension.
- Parse `ChangeInNAV endingValue` for NAV.
- Count `<Trade>` elements.
- Save to `_REPORTS_DIR` with cleanup to `_REPORTS_TO_KEEP`.
- Merge `nav` + `nav_updated_at` into `sentinel_config.json`.
- Write result to `MANUAL_RESULT_FILE` (so `📊 תוצאת Sync אחרון` shows it).

### Alternatives considered

- **Re-run sync on demand**: blocked by throttle — same result.
- **Store the XML somewhere and process on next boot**: too manual, too delayed.
- **Direct input of NAV value via Telegram message**: bypasses data validation and audit trail.

### Constraint

The handler only activates when `user_state['action'] == 'awaiting_ibkr_xml'`, set by the button press. An unsolicited document sent to the bot is ignored.
