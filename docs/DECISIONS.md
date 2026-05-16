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

---

## DEC-20260512-001 — `bot_core.py` as the single source of bot/supabase/user_state singletons

Date: 2026-05-12
Status: implemented

### Decision

Create a tiny `bot_core.py` whose only job is to instantiate `bot = TeleBot(TOKEN)`, the Supabase client, and the shared `user_state: dict`, plus expose `RTL`, `ADMIN_ID`, `TOKEN`. Every other module imports from there.

### Rationale

Before the refactor, `telegram_bot.py` created these objects at import time, and many modules wanting to reuse them faced a circular dependency. Putting them in a leaf module (no internal imports) breaks the cycle and makes the singletons unambiguously identifiable.

### Alternatives considered

- **Dependency injection through function arguments**: too invasive — would touch every call site.
- **Factory function** (`get_bot()`): adds indirection but doesn't change the underlying coupling.
- **`__init__.py` package conversion**: bigger structural change for the same outcome.

### Constraint

`bot_core.py` runs `load_dotenv()` and creates the Supabase client at import time. Tests stub `supabase` / `telebot` / `dotenv` in `sys.modules` *before* importing any application module to avoid real network or filesystem use.

---

## DEC-20260512-002 — Lazy import of `telegram_bot` inside `telegram_callbacks.handle_queries`

Date: 2026-05-12
Status: implemented

### Decision

`telegram_callbacks.py` does not import `telegram_bot` at the top level. Instead, inside `handle_queries(call)`, it does `import telegram_bot as _tb` and then calls `_tb.handle_drilldown` / `_tb.get_next_missing`.

### Rationale

The callback registration `@bot.callback_query_handler` needs to run when `telegram_bot.py` is imported — but `telegram_callbacks` also needs functions defined later in `telegram_bot`. A top-level `import telegram_bot` in `telegram_callbacks` creates a cycle. Lazy import deferred to call time resolves it: by the time any callback fires, both modules are fully initialized in `sys.modules`.

### Alternatives considered

- **Move callback registration to `telegram_bot.py`**: defeats the purpose of the split.
- **Pass `telegram_bot` module as a parameter**: telebot's decorator API doesn't support this.
- **Use late-binding attribute lookup** (`getattr(sys.modules['telegram_bot'], 'handle_drilldown')`): identical behavior but uglier.

### Constraint

The lazy import in callbacks only works because callback bodies execute after both modules are loaded. If we ever invoke a callback synchronously during import (we don't), this would break.

---

## DEC-20260512-003 — `quantity` in `trades` table is signed (BUY positive, SELL negative)

Date: 2026-05-12
Status: implemented

### Decision

The `quantity` column in Supabase `trades` stores signed values: BUY trades positive, SELL trades negative. `ibkr_trade_importer.parse_trades_from_xml` enforces this regardless of what IBKR sends.

### Rationale

`engine_core.get_open_positions_campaign` already computed `net_qty = group["quantity"].sum()` and used `if net_qty <= 0.001: continue` to detect closed campaigns. The entire existing dataset already used signed quantities (production query confirmed: BUY 4, SELL -4 for HOOD). Changing the engine would invalidate historic data and risk math. Aligning the importer is the safer choice.

### Constraint

Any tooling that displays `quantity` to a human should `abs()` before showing the magnitude — or rely on `side` for direction and `abs(quantity)` for size. The dashboard, `/portfolio`, and `fmt_position_card` already handle this correctly.

---

## DEC-20260512-004 — `campaign_id` format: `{SYMBOL}_{tradeID of first BUY}`

Date: 2026-05-12
Status: implemented

### Decision

When inserting a new trade into Supabase from an IBKR XML, assign `campaign_id = f"{symbol}_{trade_id}"` where `trade_id` is the IBKR `tradeID` of the BUY that opens the campaign. Add-on BUYs and SELLs join the open campaign; the next BUY after `net_qty` returns to 0 starts a fresh campaign.

### Rationale

This format was already in production (e.g. `HOOD_9449697599`, `JPM_9391377860`). UUIDs would have been technically simpler but would diverge from the existing convention and make manual SQL inspection harder. Reusing the format keeps the dataset homogeneous.

### Alternatives considered

- **UUID v4**: independent of trade IDs, but loses the human-readable symbol prefix and the natural link to the opening trade.
- **Auto-increment from a sequence**: requires DB-side coordination; symbol prefix is more debuggable.
- **Timestamp-based** (`HOOD_20260511_143300`): too coarse if two BUYs of the same symbol arrive in the same minute.

### Constraint

If two BUYs of the same symbol have the same `tradeID` (impossible — IBKR `tradeID` is globally unique), they'd collide. Not a real risk.

`engine_core.get_open_positions_campaign` filters out rows with NULL `campaign_id`. Any importer that fails to assign one will silently make positions disappear from `/portfolio` and the dashboard — discovered the hard way in this session.

---

## DEC-20260512-005 — Explicit DNS servers in `docker-compose.yml` for every service

Date: 2026-05-12
Status: implemented

### Decision

Each service in `docker-compose.yml` declares `dns: [8.8.8.8, 1.1.1.1]` so containers resolve external hostnames via Google + Cloudflare public DNS instead of the host's default (Docker's `127.0.0.11` resolver forwarding to the home router at `192.168.50.1`).

### Rationale

The Orange Pi's home router DNS was intermittently failing, causing both `api.telegram.org` and `www.interactivebrokers.com` to fail with `NameResolutionError`. The host itself recovered quickly (local cache), but containers using the router-forwarding resolver did not. Pinning public DNS at the service level removes the dependency on the unreliable hop.

### Alternatives considered

- **Edit `/etc/docker/daemon.json` with `"dns"`**: applies globally to all containers including unrelated ones; not least-surprise.
- **Run a local DNS cache** (`dnsmasq`, `unbound`) on the host: heavier maintenance.
- **Switch the router**: not in scope; we don't control the user's network.

### Constraint

If both Google and Cloudflare are unreachable (extremely rare), containers lose DNS regardless of the router. Acceptable — this is the standard graceful-degradation tradeoff for public DNS.

---

## DEC-20260515-001 — Minervini name used as acknowledgment only, not branding

Date: 2026-05-15
Status: decided (product/GTM)

### Decision

Public marketing may reference *Trade Like a Stock Market Wizard* as an acknowledgment ("built on principles from …") under fair use. Mark Minervini's name is **not** used as a brand, endorsement, or hero line. Revisit a licensing/partnership approach only once there is real traction.

### Rationale

Bold name-use is the strongest positioning but requires a licensing agreement or explicit approval and carries DMCA/litigation risk if refused. Acknowledgment-only is legally neutral, costs nothing, and keeps the partnership option open for later from a position of strength.

### Alternatives considered

- **Name bold in branding** ("your Minervini co-pilot"): strongest, but needs legal clearance; rejected for launch.
- **No reference at all**: safest legally but neuters the competitive edge and weakens positioning.

### Unblocks

Marketing team — landing-page hero and Phase 3 positioning (see `docs/teams/MARKETING_PLAN_V0.md`). Mark review conflict #4 resolved.

---

## DEC-20260515-002 — Minervini-strict is the only methodology profile for now

Date: 2026-05-15
Status: decided (product/GTM)

### Decision

Ship a single, hardened, validated `minervini_strict` profile for all users. The 4-profile model (minervini_strict / minervini_relaxed / oneill_classic / swing_low_risk) is deferred to Sprint 13. A full user-tunable "custom profile" is permanently rejected.

### Rationale

One profile is the safest and most consistent with the AGENTS.md Red Lines. Multiple profiles widen the test surface and complicate Hyperscaler Phase B before the single-tenant base is even productized. Regardless of future profiles, the Red Lines (`mix_algo_into_wr=false`, admin-only, no DATA_INCOMPLETE in stats, secure_runner required) stay hard-coded constants, never profile fields.

### Alternatives considered

- **4 profiles now**: more flexible, but premature; deferred to Sprint 13.
- **Full custom profile**: breaks Mark's methodology and risks the Red Lines; rejected permanently.

### Unblocks

Hyperscaler Phase B architecture (`docs/teams/HYPERSCALER_DESIGN_V0.md`). Mark directive #1 (`mix_algo_into_wr` hard constant) stands. Adaptive-UX `methodology_profile` field has a single enum value for V1.

---

## DEC-20260515-003 — Launch geography: Israel only (Hebrew-first)

Date: 2026-05-15
Status: decided (product/GTM)

### Decision

First launch targets the Hebrew-speaking Israeli momentum-trader market only. English/i18n is deferred to ~Q3, aligned with Hyperscaler Phase C readiness. No translation work in the near term.

### Rationale

The bot is already Hebrew-native with minimal friction and local networking; this is the fastest path to validating the product. A smaller market (~5k active momentum traders) is an acceptable trade for speed-to-feedback. English expansion rides on the multi-tenant infrastructure that Phase C delivers anyway.

### Alternatives considered

- **Global English only**: larger market but mandatory full translation, heavy competition, and a launch delay.
- **Bilingual from day one**: best long-term growth but doubles work and delays first launch.

### Unblocks

Marketing channel strategy and the i18n investment line (deferred). Adaptive-UX Layer-1 `language` field defaults to `he` for V1.

---

## DEC-20260515-004 — Public track record: process/demo only, no numbers

Date: 2026-05-15
Status: decided (product/GTM)

### Decision

Public materials show *how the system behaves* (e.g., how it cuts drawdown, how the state machine reacts) — not performance numbers. No synthetic backtest figures, no founder PnL. Real (anonymized, consented) beta-user metrics may be introduced from Sprint 12.

### Rationale

Process demos are the safest path regulatorily and avoid FINRA-style disclaimer exposure entirely. Synthetic backtests are weak (anyone can backtest); founder PnL needs legal review before any publication. Consented beta data later gives credible numbers without the personal-exposure risk.

### Alternatives considered

- **Synthetic backtest**: weak and not credible.
- **Founder's anonymized real data**: strong but exposure + legal review required; not before counsel.
- **Beta-user data now**: needs 5+ consented beta users first — months away.

### Unblocks

Marketing trust rail (`docs/teams/MARKETING_PLAN_V0.md`). Ties to DEC-20260515-005 (closed beta supplies the future consented dataset).

---

## DEC-20260515-005 — Closed free beta; testers get 1 year free Pro at launch

Date: 2026-05-15
Status: decided (product/GTM)

### Decision

First stage is a **free closed beta** for a founder-selected community (friends, family, trusted traders) for testing, feedback, and improvement. Beta participants receive a **full year of the Pro tier free at launch** as a loyalty reward. The full pricing model and subscription tiers are designed later, after beta feedback.

### Rationale

A closed free beta removes any need for a billing system in the near term (Hyperscaler Phase D), de-risks pricing by deferring it until product value is understood, and produces the consented real dataset that DEC-20260515-004 needs. The 1-year-Pro reward aligns early-tester incentives with long-term retention.

### Alternatives considered

- **Retail $29 + Pro $99 from launch**: premature; requires billing and a pricing model before product validation.
- **Single flat tier / free public trial**: free public trial needs synthetic demo-mode product work; closed beta is leaner and higher-signal.

### Constraint / unblocks

No billing/payments work needed before Phase D. Marketing Q1 should plan for closed-beta recruitment, not paid acquisition. Pricing model is an explicit open item for a future decision (post-beta). Adaptive-UX onboarding can assume invited users (no public signup) for V1.

---

## DEC-20260515-006 — ALGO in Open Tasks: one consolidated button + non-binding recommendations

Date: 2026-05-15
Status: decided (product) — **conditional on Mark's observer-safe ruling (Sprint 11 Wave 1)**

### Decision

Replace the per-ALGO `task_algo_noop` popup with a SINGLE consolidated ALGO entry in the Open Tasks list. Tapping it shows: (1) an explicit disclaimer "המלצה בלבד, לא חובת ביצוע — מנוהל חיצונית", then (2) for each ALGO-managed position, the engine's *observed* recommended action. These are **info-only**: never a `Task` with a status, never counted, never enter Win-Rate/Expectancy, never instruct an ALGO stop write.

### Rationale

Founder wants visibility into what the system *observes* for ALGO positions instead of a dead-end popup. Surfacing the engine's existing observation as a clearly non-binding read-out preserves the value while keeping Sentinel out of ALGO management.

### Constraint (hard — gates implementation)

This shifts ALGO from "pure observation, no text" toward "advisory read-out", which is adjacent to the AGENTS.md ALGO-observer Red Line (DEC-20260511-001 / invariants #5, #8). **Implementation is blocked until Mark rules** (Sprint 11 Wave 1) on the exact observer-safe form: the wording must be descriptive of the engine's observation only, explicitly non-binding, produce no actionable `Task`, and never feed stats. If Mark cannot define a safe form, fall back to DEC option "consolidated button, no recommendations".

### Alternatives considered

- **Consolidated button, no recommendations** (red-line-safe fallback): one button "מנוהל חיצונית — אין פעולת Sentinel".
- **Remove ALGO from tasks entirely**: cleanest, but loses the signal that ALGO positions exist.

---

## DEC-20260515-007 — Suppress the RUNNER task when the stop already meets the engine suggestion

Date: 2026-05-15
Status: decided (methodology) — Mark defines the epsilon (Sprint 11 Wave 1)

### Decision

`PROTECT_RUNNER_PROFIT` is **not** emitted when the campaign's current stop already satisfies the engine's own `compute_suggested_trail_stop()` — i.e. `current_stop >= suggested_stop - epsilon`. A RUNNER task appears only when there is a *material* tighten to perform.

### Rationale

Observed live (MRVL): current stop $157.70 vs engine suggestion $158.11 — a $0.41 (0.26%) "task" that is pure noise. A task list must contain *actionable* items; surfacing a no-op tighten erodes trust in the whole list.

### Constraint

`epsilon` is a methodology threshold, defined by Mark in Sprint 11 Wave 1 (not invented by engineering). The check is read-only over the engine's own suggested-stop output — zero new R/NAV/campaign math. Tightening that *is* material still surfaces unchanged.

---

## DEC-20260515-008 — Audit trail exposed to the USER as a retrospective review surface

Date: 2026-05-15
Status: decided (product)

### Decision

The recorded action trail (`audit_log`: stop changes incl. loosen-overrides, task done/skip, risk-pct changes, etc.) is exposed to the **user** — not buried in the developer menu — as a read-only "review my actions / performance" surface in the normal menu, in friendly Hebrew, most-recent-first.

### Rationale

The founder's goal is self-review ("שיכול לעבור אחרונה על הביצועים") — retrospective accountability over their own decisions. That is a first-class user need, not a dev/forensic one.

### Constraint

`audit_logger.py` is currently write-only **by design**. This adds a *deliberate, additive read path* (a new read function) — read-only, never mutates, honest data-source labels, still admin-only at the bot boundary (secure_runner unchanged). Mark (Sprint 11 Wave 1) confirms the read surface cannot present any fallback/derived number as authoritative (AGENTS.md #1).

---

## DEC-20260515-009 — Telegram rate-limit stays 8 msgs / 60s (secure_runner unchanged)

Date: 2026-05-15
Status: decided (security)

### Decision

The `telegram_bot_secure_runner.py` rate-limit (8 messages / 60s, 90s cooldown) is **kept as-is**. It tripped during intensive smoke-testing; that is the guardrail working. Work at a reasonable pace rather than weaken a security Red Line.

### Rationale

`telegram_bot_secure_runner.py` is a CLAUDE.md hard constraint. A single-user-admin convenience is not worth loosening anti-spam. Recorded so it is not re-litigated.

---

## DEC-20260515-010 — Manual operator-run `deploy.sh`; `deploy-watcher` not installed

Date: 2026-05-15
Status: decided (ops)

### Decision

The host `deploy-watcher` systemd service is **not** installed on the Pi (`systemctl restart deploy-watcher` → "Unit not found"), so the Telegram "🔄 Git Pull + Deploy" button has always been a no-op and the real deploy path is a manual SSH command. Going forward the supported deploy path is a new operator-run `deploy.sh` at the repo root. The auto-deploy `deploy-watcher` is **not** installed (founder chose explicit control over auto-deploy). `deploy_watcher.sh` (Sprint 13) stays in the repo for a possible future watcher install but is dormant.

### Rationale

The founder wants deploys under explicit control, not auto-fired by a Telegram tap. `deploy.sh` applies the exact Sprint-13 resilience Mark ruled (MARK_SPRINT13_RULINGS.md §1) — `up -d --build --force-recreate` (no `down`), a forced-IPv4 in-container connectivity self-check, retry-once, and on persistent failure it prints the exact `down && up -d` recovery and exits non-zero (never a fabricated success on a dead bot; never an unattended `down`).

### Constraint

`deploy.sh` is a new standalone file. It does NOT modify `docker-compose.yml` service commands, `deploy_watcher.sh`, `deploy-watcher.service`, `telegram_bot_secure_runner.py`, or any app/risk/NAV/campaign math (CLAUDE.md most-fragile area). Host bash → not unit-testable; `bash -n` clean; manual verification only.

### Alternatives considered

- **Install the `deploy-watcher` systemd service**: makes the Telegram button a live auto-deploy; rejected — founder wants explicit control.
- **Both watcher + manual script**: deferred; revisit only if unattended auto-deploy is wanted later.
- **Keep raw `docker compose up -d --build`**: rejected — it is exactly what caused the [Errno 101] stale-bridge outage this session.

---

## DEC-20260515-011 — Dual R: Structure R + Account R (never one conflated number)

Date: 2026-05-15
Status: decided (methodology) — Mark defines exact formulas/labels (Sprint 15 Wave 1)

### Decision

Every surface that shows an open-R (Telegram report, dashboard, AI-copy textbox) MUST show **two distinct, labelled metrics**, never a single number labelled with the wrong basis:
- **Structure R** — net/open PnL ÷ the trade's **own original campaign risk** (existing `engine_core.compute_r_true`, :997).
- **Account R** — net/open PnL ÷ the **frozen target risk** (existing `engine_core.compute_r_target`, :1004).

### Rationale

Founder-found defect: the report prints `RiskBasis: Target` but the OpenR is computed off original campaign risk. Live: MRVL shows 9.22R (Structure, ~$19 base) while Account R vs $47.53 target is ~3.73R; PWR 1.34R vs 0.89R; WCC 0.26R vs 0.11R. Both are true but they are different truths — collapsing them into one mislabelled number misrepresents real account impact (a "9R monster" is ~3.7R to the account).

### Constraint

This is a *surfacing + labelling* fix using the TWO formulas that already exist — it must introduce **no new R/NAV/campaign math** (AGENTS.md / CLAUDE.md red line). Mark (Sprint 15 Wave 1) rules the exact label strings, which existing function feeds which, and ALGO handling (ALGO has no real stop → Structure R may be N/A, Account R only). Test-gated.

---

## DEC-20260515-012 — Risk Capital Basis must be declared (NAV vs Base Capital)

Date: 2026-05-15
Status: decided (methodology)

### Decision

Wherever a target-risk $ figure is shown, the report MUST state the capital basis it was derived from: `Risk Capital Basis: NAV` or `Risk Capital Basis: Base Capital`. No silent basis.

### Rationale

Founder-found: $47.53 target risk is from NAV ($7,921); from Base Capital ($7,500) it would be $45.00. Not dramatic, but the reader must know which figure the system pulled from (data-source honesty — AGENTS.md #1).

### Constraint

Declaration/labelling only — does not change which basis the engine uses (that stays as implemented unless a separate decision changes it). Mark confirms the wording and that no number changes.

---

## DEC-20260515-013 — Broker Reconciliation Status (never silent on NAV vs DB gap)

Date: 2026-05-15
Status: decided (methodology)

### Decision

The report MUST surface a `Broker Reconciliation Status`: `Balanced` / `Minor Difference` / `Material Gap` / `Critical Data Gap`, computed from Broker NAV vs DB-derived net PnL (accounting for base capital). The system must never pass over a material discrepancy silently.

### Rationale

Founder-found: Broker NAV $7,921.08 (+$421.08 over $7,500 base, +5.61%) vs DB Net PnL all −$320.23 → ~$741.31 gap. Likely deposits/withdrawals/open positions/fees/revaluation or — founder's hypothesis — trades absent because the IBKR report pulls YTD only. Whatever the cause, silence is unacceptable.

### Constraint

Mark (Sprint 15 Wave 1) defines the band thresholds (grounded, no invented numbers) and the honest "cause unknown — verify" wording (#1, never present a guessed cause as truth). System/Infra verifies the YTD-window hypothesis. No change to NAV/PnL math — this is a derived status indicator + disclosure.

### Open (NOT decided — for the Sprint 15 team meeting / pending founder input)

- **ALGO Oversight Gate** — **RESOLVED → see DEC-20260515-014 below** (founder accepted Mark's REFINE; structure locked, numeric thresholds pending founder's real-ALGO-data fine-tuning).
- **BLOCKED pending founder's ALGO rules** (founder will provide): ALGO open-position data quality (`State/InitStop/CurrStop unknown`, `Visibility 40/100` not good enough); strategy-adaptive "dead money" alert when no smart follow-through. Team designs the *framework to absorb* the rules; no ALGO logic invented.

---

## DEC-20260515-014 — ALGO Oversight Gate (Mark's refined structure, accepted)

Date: 2026-05-16
Status: **structure accepted (founder); real ALGO data RECEIVED 2026-05-16** (`docs/teams/ALGO_REFERENCE_2026_05_16.md` — authoritative) → Sprint 17 fine-tunes numbers + unblocks #4/#5. **NOT built** until Sprint-17 Mark-gated tuning + re-confirmation.

### Decision

The founder accepted Mark's `REFINE` (`MARK_SPRINT15_RULINGS.md §4`). The Gate's **structure is locked**; the founder will supply a full review with real ALGO data to fine-tune the exact numbers.

**Locked structure:**
- **Advisory only.** The Gate withholds the *founder's own* discretionary ALGO size-up / new-asset / exposure-up decision. It NEVER instructs the ALGO, never alters an ALGO trade, emits at most `Review Required` (DEC-20260511-001 display rule) — never `Action Required`. This is the methodological clearance: advisory oversight ≠ management, so it is admissible under DEC-20260511-001.
- **Triggers (any → Gate engages):**
  1. ALGO Net PnL `< −5R` on an explicit **Account-R** basis (ALGO has no real stop; per DEC-20260515-011) — must be stated.
  2. Rolling expectancy negative over the last 20–30 ALGO trades, computed on an **ALGO-segregated cohort that is EXCLUDED from headline Win-Rate/Expectancy** (invariant #8) — a separate observer metric, never leaking into main stats.
  3. ALGO Profit Factor `< 1`, same ALGO-segregated cohort, same #8 isolation.
  4. Stop / max-loss unknown → gates **new ALGO assets ONLY** (not size-up on existing, not a blanket exposure freeze).
- **DROPPED:** the original `Visibility < 70` condition — vacuous (ALGO visibility is capped at 40 by design, `compute_risk_visibility_score:298-299`, so `<70` is always true). The existing visibility score already encodes the intent; if a visibility trigger is wanted it must be reframed (e.g. `Visibility == 20` / no target risk), to be decided with the real data.

### Rationale

Founder's risk-discipline intent is sound; Mark cleared the observer-mode compatibility (advisory, `Review Required` only). The exact thresholds (−5R basis, 20–30 window, PF<1, any reframed visibility trigger) interlock with the founder's real ALGO performance data and forthcoming ALGO rules — locking the structure now while fine-tuning numbers against real data avoids both rework and an invented-number red-line breach.

### Constraint / next

NOT built this sprint or until: (a) the founder's full real-ALGO-data review arrives, (b) Mark + team fine-tune the numeric thresholds against it, (c) it is re-confirmed. The ALGO-segregated expectancy/PF cohort must never contaminate headline stats (#8). Build also stays gated on the still-pending founder ALGO rules (the same data feeds the BLOCKED #4/#5 framework above).
