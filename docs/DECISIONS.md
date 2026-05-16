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

---

## DEC-20260516-015 — Weekly/Monthly report: open-book + honest empty-state

Date: 2026-05-16
Status: **decided (founder); Sprint 18, Mark-led** — not built until Mark rulings + checkpoint.

### Problem (founder smoke-test, Sprint-17 on-demand button)

The weekly/monthly report is **realized-only by design** (`compute_period_analytics`: "campaigns that closed within [period_start, period_end)"). With a live 6-position book (HOOD/MRVL/PLTR/PWR/TSLA/WCC, +$230 floating, 31.3% exposure) and **0 campaigns closed** in the on-demand window (03–09/05), the report rendered "🔴 שבוע ללא עסקאות" — technically true for *closed* campaigns but **misleading** (a #1 concern: presents an empty realized set as "no trading activity") and a real product gap: the open book's state + how it performed is entirely absent.

### Decision (founder chose "מלא + snapshot קדימה")

Sprint 18 adds to the weekly/monthly report:
1. **Open-book section** — current state per open position (entry / current / floating PnL / Open-R / exposure), reusing the existing live source `ec.get_open_positions_campaign` (engine_core.py:473; same as the command room). **Realized vs unrealized strictly separated**; the open book NEVER enters realized Win-Rate/Expectancy/PF/Net-R. **ALGO open positions segregated** (#8 / DEC-20260515-014) — observation-only, never an instruction (DEC-20260511-001).
2. **Honest empty-state** — replace the misleading "שבוע/חודש ללא עסקאות" when there IS a live book: state plainly "0 קמפיינים נסגרו בתקופה" + the open-book summary; #1-honest about the data window and source (Live/Cached/Sync-temporary).
3. **Begin snapshotting open-position marks** with each scheduled run (new `report_snapshot_store` field) so a **true weekly mark-to-market delta** appears from the NEXT week onward. Honest constraint surfaced: the delta is "—" until a baseline week accumulates (no retroactive week-ago open-mark exists — accuracy over confidence, #1).

### Hard constraints

- No change to realized R/NAV/campaign/Expectancy math (CLAUDE.md fragile area; Safe-Change: tests required). Realized KPIs byte-identical.
- Strict realized/unrealized separation + ALGO #8 segregation provable by construction + test (open book never contaminates realized stats; ALGO never in headline).
- Advisory/observation only for ALGO (DEC-20260511-001). Backtest/Live/Cached honesty (#1).
- New snapshot field is additive (Hyperscaler: no migration; per-host derived state).
- No wholesale rewrite; reuse `get_open_positions_campaign` (battle-tested in the command room) — invent no new position math.

---

## DEC-20260516-016 — Period-honest headline + period-over-period context + System-Health #1 bug

Date: 2026-05-16
Status: **decided (founder); Sprint 19, Mark-led** — not built until Mark rulings + checkpoint.

### Trigger (founder smoke-test of deployed Sprint-18 f43a94c)

Sprint-18 shipped & verified live: the open book now renders in weekly/monthly, period-scoped (opened-in-period / held-from-before / opened-after-window excluded), ALGO-segregated, honest empty-state line. Real progress on the founder's prior asks. Re-test surfaced THREE remaining issues:

1. **Headline still reads "0 / ללא עסקאות".** Despite the new honest empty-state LINE, the dominant visuals — the big `verdict-badge` ("שבוע/חודש ללא עסקאות") and the all-zero KPI cards (WR/Exp/PF/Realized $0) — still scream "no trading / zero" while a live book (+$72 weekly, +$224 monthly, 33–34% exposure, 4 opened-in-period) spanned the period. Founder: "עדיין הנתונים אפסיים, אין התייחסות לנתונים ביחס לשבוע/חודש ביחס לתיק."
2. **No period-over-period / vs-average context.** Founder: "אין התייחסות לגבי השבוע/החודש שנבדקו ביחס לשבועות/חודשים קודמים ולעומת שבוע/חודש ממוצעים." `compute_period_comparison` ("vs previous") is omitted in on-demand by design and only fires for scheduled runs once a prior snapshot exists; there is NO "vs average" metric anywhere; the open book has no period-over-period view.
3. **System-Health #1 bug (RCA done).** `ibkr_sync_runner.py:16` `IBKR_ERROR_CLASSES[1001]=("temporary","הדוח לא נוצר כרגע — ניסיון מאוחר יותר")` is the IBKR **flex-query** status; `report_scheduler._build_system_health` blindly renders it as `✅ Sync temporary — הדוח לא נוצר כרגע …` INSIDE a successfully delivered Sentinel report. Two faults: (a) "הדוח" reads as the Sentinel report → actively misleading (#1); (b) `✅` prefix on a non-ok/temporary state. Minor sibling: monthly PDF header shows "1–29 באפריל" (April=30) — suspected `_period_label` off-by-one.

### Decision (Sprint 19, Mark-led)

1. **Period-honest headline (presentation only — NO realized-math / `compute_verdict` / 920be95 / #8 change):** when 0 closed but an active book spanned the period, the verdict badge + KPI framing must NOT visually read "no trading / zero". Surface the period's OPEN-BOOK performance prominently (floating PnL, exposure, # opened-in-period, mark-to-market Δ once a baseline exists) clearly separated from realized; realized KPI cards stay byte-identical but are framed as "0 ממומש" not the dominant verdict.
2. **Period-over-period + vs-average context:** add "מול תקופה קודמת" and "מול ממוצע" for BOTH realized (existing snapshot history via `load_recent`) and the open book (new `open_marks` history). Honest baseline-pending until ≥N prior snapshots accumulate (#1 — never a fabricated average). On-demand may show it READ-ONLY from existing history (no snap_save — Scope-B invariant holds).
3. **Fix System-Health #1 bug:** `_build_system_health` must map sync status to an honest, non-self-contradictory line — no `✅` on `temporary`; never surface the IBKR-flex "הדוח לא נוצר" string verbatim where it reads as the Sentinel report. Mark rules exact Hebrew. Check & fix the monthly `_period_label` "1–29" off-by-one.

### Hard constraints

- No realized R/NAV/campaign/Expectancy math change; `analytics_engine.py` realized path byte-identical (guard). `compute_verdict` 920be95 signature + bcf32f5 + Sprint-16 graceful + Sprint-18 period-scoping all preserved.
- Realized vs unrealized strictly separated; ALGO #8-segregated & observation-only (DEC-20260511-001) in every new comparison too — ALGO never in headline/realized comparison.
- #1: never fabricate an average/comparison without enough history — explicit baseline-pending; never present sync-temporary as ✅ or as "report not created".
- On-demand stays NO snap_save; comparison/average read-only from existing history. Hyperscaler: comparison uses existing per-host snapshot files; no migration.
- No wholesale renderer rewrite; presentation-layer + additive ctx; reuse `compute_period_comparison` + `load_recent` + the Sprint-18 `open_marks`.

---

## DEC-20260516-017 — Period view = union(opened ∪ closed ∪ open); RCA-gated on the "0 realized" data-integrity question

Date: 2026-05-16
Status: **decided (founder direction); Sprint 20, Mark-led, RCA-GATED** — no analytics/campaign-math build until the read-only RCA confirms root cause.

### Trigger (founder smoke-test of deployed Sprint-19 2075756)

Sprint-19 verified live: period-honest headline (no dominant "ללא עסקאות" with a live book), realized cards truthfully demoted "0 בתקופה", vs-average baseline-pending honest, System-Health honest, `_period_label` "3–9 במאי"/"1–30 באפריל". Founder's sharpened core objection: **"רוב הנתונים 0 ולא תואם לאמת — גם נפתחו וגם נסגרו פוזיציות במהלך השבוע/החודש."** Proposed direction: the period basis must be the **union (OR)** — *opened-in-period* OR *closed-in-period* OR *open-spanning* — then compute on that union (incl. positions that BOTH open AND close within the same period).

### RCA finding (code-level, this session — leading hypothesis, NOT yet data-confirmed)

`analytics_engine._get_closed_campaigns:255-262` ALREADY counts any campaign with an in-window SELL, **including same-period open→close round-trips** — so this is NOT a formula bug that drops round-trips. BUT:
- `:258` `closed_ids = in_period["campaign_id"].dropna().unique()` → an in-window SELL with **NULL campaign_id is silently dropped** (never counted, never `excluded`).
- `engine_core.get_open_positions_campaign:479` `valid_df = work[work["campaign_id"].notnull()]` → null-campaign trades are invisible to the OPEN book too. ⇒ a trade without `campaign_id` vanishes from BOTH views.
- `bot_health.py:146` already tracks `df_c["campaign_id"].isnull()` → null-campaign trades are a **known real condition** in this system (consistent with the open broker-recon $190.29 "requires manual verification" gap).
- `excluded_pnl`/`excluded_count` are **not surfaced** in the weekly/monthly templates → linked-but-DATA_INCOMPLETE round-trips are silently 0 (a second #1 honesty gap).

Leading hypothesis: the founder's missing closes are NOT in the data the report reads *with a campaign_id* (null-linkage and/or unsynced), OR are linked-but-excluded and not surfaced. Per #1 the report is honest about the data it has; the gap is data-integrity upstream — building the union view on the assumption "the closes are in the data" would not fix "0" and would itself violate #1.

### Decision (Sprint 20, Mark-led, RCA-GATED)

1. **RCA FIRST (no campaign-math change until done):** a read-only, admin-gated dev-menu probe ("תקינות נתוני תקופה") that, for the last weekly+monthly windows, reports the decisive numbers — total trades in window; BUY/SELL counts; **BUY/SELL with NULL campaign_id**; # campaigns with an in-window SELL; # opened-AND-closed-in-window round-trips; Σ `pnl_usd` in window; `excluded_count`/`excluded_pnl`. This classifies the root cause (null-linkage vs unsynced vs out-of-window vs linked-but-excluded) without guessing or mutating anything.
2. **Gated on the RCA:** implement the founder's union-based period view — period basis = opened-in-period ∪ closed-in-period ∪ open-spanning; same-period round-trips explicitly counted in realized; **surface excluded/unlinked realized PnL honestly** so nothing real is silently 0 (#1). Realized stats for the existing linked-closed countable subset stay **byte-identical** (guard test). ALGO #8-segregated throughout; observation-only.

### Hard constraints

- No campaign/R/NAV/Expectancy math change until RCA confirms root cause; the existing linked-closed countable realized KPIs must remain byte-identical (guard). #8 ALGO segregation + #1 honesty (never present unlinked/incomplete data as exact truth; never fabricate closes that aren't in the data — say so explicitly).
- RCA probe is strictly read-only (no Supabase mutation, no snap_save, admin-gated via existing dev-menu/PIN path).
- Preserve 920be95 / bcf32f5 / Sprint-16 graceful / Sprint-18 period-scoping / Sprint-19 headline+comparison+System-Health. No migration / compose / secure_runner change.

---

## DEC-20260516-017 — UPDATE: RCA GATE PASSED, root cause CONFIRMED (data-confirmed via 🏥 בריאות מערכת)

Date: 2026-05-16
Status: **RCA gate PASSED; Step-2 UNGATED with precise confirmed scope; Sprint-20 Step-2 Mark-led.**

### Founder ran the existing `🏥 בריאות מערכת` (no build) — decisive result

- `✅ Campaign IDs — כולם מלאים` → **null-campaign_id hypothesis RULED OUT** (all trades linked).
- `✅ Supabase — טרייד אחרון: 2026-05-15` → **not a sync gap** (data current).
- `🧹 רשומות סגורות/ארכיון ללא סטופ: 52 (HOOD, HP, JPM, MSGE, PLTR) — אינו נספר` → **the smoking gun.**

### Confirmed root cause (RCA path f, data-confirmed + code-traced)

The founder's period closes ARE real, ARE campaign-linked, ARE in the data — but lack `initial_stop`. Trace: `_get_closed_campaigns` picks them up (campaign_id present, in-window SELL) → `_aggregate_campaigns` → `classify_stat_bucket(setup, true_orig_risk=0)` → `STAT_BUCKET_DATA_INCOMPLETE` (engine_core.py:1257-1258) → `is_stat_countable` False (1263) → NOT in `countable` → `campaigns_closed = len(countable) = 0` (analytics_engine.py:89,129). They DO land in `excluded_count`/`excluded_pnl` (analytics_engine.py:57-58,144-145) — **which are computed but rendered NOWHERE** (confirmed absent from report_renderer.py + both templates). So the report shows "0 קמפיינים נסגרו / Realized $0" while N campaigns truly closed with $X realized PnL.

**This is a #1 disclosure/honesty defect — NOT a campaign-math bug.** Excluding no-stop campaigns from edge stats (WR/Expectancy/PF/Net-R) is methodologically CORRECT (#8 — no R without a stop). The defect is the SILENT omission: the report must honestly disclose "N קמפיינים נסגרו בתקופה אך הוחרגו מסטטיסטיקת edge (חסר stop) — רווח/הפסד ממומש לא-מאומת: $X · השלם entry/stop כדי להיכלל." Partly also a founder-side data-completion task (52 closed records lack stop; the system already says "השלם entry/stop").

### Step-2 scope (UNGATED, Mark-led, Wave-1/2 rigor)

1. **Surface the excluded/closed-but-incomplete leg honestly** in weekly/monthly + the Telegram summary, using the ALREADY-COMPUTED `excluded_count`/`excluded_pnl` — ZERO campaign/R/NAV/Expectancy math change. Strictly separated from countable edge stats (which stay byte-identical & #8-clean). Labeled "לא-מאומת / חסר stop", never as exact edge truth (#1).
2. **ALGO stays segregated** (DEC-20260515-014 / DEC-20260511-001): the excluded bucket mixes DATA_INCOMPLETE (manual, missing stop) AND ALGO — disclose them on SEPARATE lines, ALGO observation-only, never merged, never in headline edge stats.
3. Satisfies the founder's union framing: closed-but-excluded now visible (closed leg) alongside Sprint-18/19 opened-in-period + open-book legs.

### Hard constraints
No campaign/R/NAV/Expectancy math change (excluded_pnl already computed); countable realized KPIs byte-identical (guard). #8 ALGO/DATA_INCOMPLETE never in countable; #1 honest ("לא-מאומת", explicit incomplete-data disclosure, never fabricated). Preserve 920be95/bcf32f5/Sprint-16/Sprint-18 period-scoping/Sprint-19. No migration/compose/secure_runner change. No wholesale renderer rewrite — additive presentation.

---

## DEC-20260516-018 — Full-DB read-only diagnostic ("where are my closes")

Date: 2026-05-16
Status: **decided (founder); Sprint 21, Mark-led — read-only diagnostic, no analytics/campaign-math change.**

### Trigger (founder smoke-test of deployed Sprint-20 8e6834b)

Sprint-20 verified live: NO excluded-disclosure block appears for the 03–09/05 weekly or April monthly windows → `excluded_count==0` AND `campaigns_closed==0` for those windows. The report is now HONEST and correct across all three legs (countable / excluded-closed / open-book + opened-in-period). The 52 missing-stop CLOSED records from `🏥 בריאות מערכת` are GLOBAL/all-time (that check is unwindowed) — they are NOT dated within the tested windows (else Sprint-20's `excluded_count>0` block would render). Conclusion: this is no longer a report-logic defect — it is a **data-location / visibility** question: *where in time are the founder's closes, and why are they not in the tested windows?* Founder direction: **look at the FULL database**, not a single window.

### Decision (Sprint 21, Mark-led)

Build a strictly **read-only, admin-gated** diagnostic surfacing the FULL trades history so the founder can SEE the real distribution:
- Total trades; `trade_date` min/max; per-month breakdown (recent N months): #BUY, #SELL, #closed campaigns split countable vs excluded(no-stop)/ALGO, Σ realized `pnl_usd`, #round-trips (opened&closed same month).
- The missing-stop CLOSED records listed WITH their actual close dates + symbol + pnl (so the founder sees which periods the 52 fall in).
- Windowed null/blank `campaign_id` reconfirm (bot_health is global-clean; confirm per-window).
- #1-honest labels (Live/Cached, "לא-מאומת" for no-stop, explicit "אין סגירות בחלון" vs "סגירות קיימות בחודש X"); #8 ALGO segregated in the breakdown (observation-only, never merged into edge).

### Hard constraints

- **Strictly read-only:** no Supabase write, no `snap_save`, no scheduler state mutation; reuse the existing read path (`_fetch_trades_df`-style select) — NO new campaign/R/NAV/Expectancy math (counts + already-stored `pnl_usd` sums only).
- **Admin protection preserved (AGENTS.md / CLAUDE.md):** wire ONLY via the EXISTING dev-menu admin/PIN gate; do NOT remove admin protection, do NOT bypass `telegram_bot_secure_runner.py`, do NOT rewrite `telegram_bot.py` wholesale — minimal additive handler + one menu entry.
- No secrets in output (no account numbers / tokens / NAV-source internals beyond what existing reports already show).
- Preserve 920be95 / bcf32f5 / Sprint-16 / Sprint-18 period-scoping / Sprint-19 / Sprint-20 disclosure. No migration / compose / secure_runner change.

---

## DEC-20260516-018 — UPDATE: engine PROVEN CORRECT on real data → production "0" is a DATA-DELIVERY gap

Date: 2026-05-16
Status: **RCA decisive. Report logic exonerated by real-data reproduction. Sprint-21 probe re-targeted to the LIVE fetch path.**

### Decisive reproduction (founder dumped full `trades` table; ran the REAL code)

`tests/test_real_data_april_regression.py` runs the REAL `compute_period_analytics` on the founder's verbatim rows:

- **April 2026 → `campaigns_closed=8`, `realized_pnl=+$180.49`, win_rate 37.5%, expectancy +1.07R, PF 2.63, net_r +8.59** (CVX/DAR/RVMD×2/MTZ/NEE/INTC/AXGN — manual EP/VCP, valid stops, correctly countable). Excluded split correct: AEHR +69.34 (stop 68.4 ABOVE entry 60.3 → DATA_INCOMPLETE, founder data-entry error — real stop is in `initial_risk_price` 54.85), TSLA -48.905 (ALGO).
- **Weekly 03–09/05 → `campaigns_closed=0` (correct, all 3 closes are ALGO #8), `excluded_count_algo=3`, `excluded_pnl_algo=-$37.23`.**

### Conclusion (evidence-based, ends the speculation)

The analytics/classification/Sprint-20-split logic is **CORRECT**. Given the founder's data it returns 8 closed / +$180 for April. Therefore the production report's "0 קמפיינים" is **NOT** a logic/display defect — the live report run is **not receiving these rows** (`report_scheduler._fetch_trades_df` → Supabase returns empty/partial/None at report time, OR the on-demand path's data input differs from the DB state). Sprint 17–20 display fixes were all correct and necessary; they could never resolve "0" because the *input* is empty in production, not the math.

Corroborating real data issues (independent of the delivery gap):
- Trades from 2026-05-11+ (`9476246095`…, incl. CAT SELL 05-15 +13.71) have **`campaign_id=null`** → silently dropped both views (still a real fix: surface/repair null-linkage).
- AEHR-class campaigns: `initial_stop` holds a value ABOVE entry (real stop sits in `initial_risk_price`) → correctly DATA_INCOMPLETE; founder-side data correction OR a future ruling on `initial_risk_price` fallback (campaign-math → Mark-gated, separate).

### Sprint-21 re-target (no logic change)

The read-only admin-gated probe must run **inside the live environment** and report, for the on-demand weekly/monthly windows: `_fetch_trades_df` row count, `trade_date` min/max, #SELL in-window, #closed campaigns the real pipeline computes, per-campaign classification (campaign_id/setup/initial_stop/original_risk+valid+reason/bucket/countable/net_pnl), and in-window NULL-`campaign_id` count. This catches the production data-delivery gap definitively. Still strictly read-only, existing admin/PIN gate, no campaign-math, no Supabase write.

---

## DEC-20260516-018 — UPDATE 2: comprehensive 3-workstream fix (founder: "תיקון מלא וזהיר")

Date: 2026-05-16
Status: **decided (founder); Sprint 21 COMPREHENSIVE, Mark-led, full Wave-1/2 rigor.**

Engine PROVEN correct on real data (April→8 closed/+$180.49; weekly→3 ALGO-excluded; `tests/test_real_data_april_regression.py`). Production "0" = data-delivery. Founder chose a full, careful, team-divided treatment. Sprint-21 = 3 bounded workstreams:

### WS-A — Live read-only diagnostic probe (LOW risk)
Admin-gated, strictly read-only module that runs the REAL `_fetch_trades_df` in the live env for the on-demand weekly/monthly windows and reports: rows fetched, `trade_date` min/max, #SELL in-window, #closed campaigns the real pipeline computes, per-campaign classification (campaign_id/setup/initial_stop/original_risk+valid+reason/bucket/countable/net_pnl), #in-window NULL-`campaign_id`, and the effective Supabase key/RLS context (no secret values — only "service-role vs anon", row visibility). Localizes WHY production input is empty (RLS/key vs runtime-failure vs data). Reuse existing dev-menu admin/PIN gate; minimal additive handler; no telegram_bot.py wholesale rewrite.

### WS-B — NULL-`campaign_id` honest surfacing + repair runbook (MED risk)
Code: trades with NULL/blank `campaign_id` currently vanish silently from BOTH realized (`analytics_engine.py:258 .dropna()`) and open-book (`engine_core.py:479 notnull()`). #1 violation. Add an HONEST disclosure (count + Σpnl of in-window unlinked trades) — never silently zero; NEVER auto-mutate Supabase from a read flow. Plus a documented manual repair query/runbook the founder runs to re-link the 8 rows from 2026-05-11+ (parent_trade_id/symbol-based). Realized/open-book countable values stay byte-identical (guard).

### WS-C — `initial_stop` vs `initial_risk_price` fallback (HIGH risk — Mark-GATED, may DEFER)
Real data shows manual EP/VCP campaigns where `initial_stop` is the `-1` sentinel or set ABOVE entry (data-entry error) while the genuine stop sits in `initial_risk_price` (e.g. AEHR 54.85, RVMD 127.8). These become DATA_INCOMPLETE → excluded though a real stop exists. **Campaign-math = CLAUDE.md most-protected.** Mark must rule the EXACT policy: (a) is `initial_risk_price`/`stop_loss` a valid fallback for `get_campaign_risk_metrics` when `initial_stop` is sentinel/invalid? (b) or is this strictly a founder data-correction task (no code change)? If a code change is ruled: everything currently countable must stay byte-identical; extensive new tests; the real-data regression (`test_real_data_april_regression.py`) updated only with Mark sign-off. DEFER if any ambiguity (#1: accuracy over confidence).

### Hard constraints
Strictly read-only WS-A (no Supabase write/snap_save/scheduler-state); admin protection preserved (no secure_runner bypass, no telegram_bot.py wholesale rewrite); #8 ALGO segregation; #1 honesty (never silent-zero, never fabricated); no campaign/R/NAV math change outside an explicit Mark WS-C ruling + guards; preserve 920be95/bcf32f5/Sprint-16/18/19/20; no migration/compose change.

---

## DEC-20260516-019 — Sprint 22: production "0" ROOT CAUSE = tz-aware bounds vs tz-naive trade_date (Mark-gated full sprint)

Date: 2026-05-16
Status: **decided (founder: "ספרינט Mark-gated מלא"); Sprint 22, full Wave-1/2 rigor, analytics-engine MOST-protected.**

### The proven root cause (supersedes the WS-A "data-delivery" hypothesis as the PRIMARY production defect)
Same `tests/test_real_data_april_regression.py::_april_df()` fixture through the REAL `analytics_engine.compute_period_analytics`:
- tz-**naive** bounds (what 100% of the test suite passes): **8 campaigns / +$180.49** ✅
- tz-**aware** bounds (what PRODUCTION actually passes): **0 campaigns / $0.00** ❌ (silent all-False, no raise)

`report_on_demand.py:96-113` (and `report_scheduler.py:251,363`) build `now = datetime.now(sched.ISRAEL_TZ)` → `last_complete_*_ref` → `_weekly/_monthly_period` ⇒ **tz-aware** `period_start/period_end`. `analytics_engine.py:30` `pd.to_datetime(df["trade_date"])` ⇒ **tz-naive** Series. `_get_closed_campaigns:334` `sells["trade_date"] >= start` and the Sprint-21 WS-B unlinked block `:54-55` compare tz-naive Series vs tz-aware scalar → in this pandas this **silently yields all-False** (in the probe's own pre-filter it RAISED `Invalid comparison between dtype=datetime64[ns] and datetime` — same defect, different surface). Production weekly/monthly reports therefore show "0 קמפיינים" while the engine math is correct. Every "engine PROVEN on real data" claim held ONLY on the tz-naive path — never the production tz-aware path (#1 false-confidence gap; stated plainly).

### Sprint-22 scope (Mark-gated, analytics-engine MOST-protected per CLAUDE.md)
Single-point tz-normalization at the comparison boundary INSIDE `compute_period_analytics` (normalize BOTH sides to tz-naive: strip tz from `period_start`/`period_end` if present; ensure `trade_date` tz-naive post-coerce) so ALL callers (on-demand + scheduled + probe-via-`_get_closed_campaigns`) are fixed at one site. Mirror the SAME normalization in `period_data_probe.py`'s own pre-pipeline window filter (it filters before delegating). NO R/NAV/campaign/Expectancy math change — pure boundary tz-normalization.

### Hard constraints
tz-**naive** path (entire suite + the LOCKED `test_real_data_april_regression.py`) byte-identical — normalization is a no-op for naive inputs. NEW regression: tz-**aware** bounds MUST return EXACTLY the tz-naive numbers (April 8/+$180.49/WR .375/PF 2.626/excl 2; weekly 0/excl 3). #1 honesty (fix must not mask/fabricate). #8 ALGO segregation untouched. WS-C stays DEFERRED (not reopened). Preserve 920be95/bcf32f5/Sprint-16..21 + WS-B `unlinked_*` + admin gate + secure_runner; no migration/compose/telegram_bot.py wholesale change. Baseline full suite **1846**.

---

## DEC-20260516-019 UPDATE — PRODUCTION CONFIRMS the tz fix; honest number reconciliation; NEW probe length defect

Date: 2026-05-16 (post-deploy, founder ran the real on-demand reports + probe)

### PRIMARY DEFECT FIXED — confirmed end-to-end in production ✅
Founder ran the REAL on-demand reports after `./deploy.sh`:
- **Monthly April-2026:** was "0 קמפיינים" → now **10 campaigns / Win 50.0% / Realized $+336 / Net R +11.01R / Expectancy +1.10R / PF 4.03 / Missing-Stop 0.0%**, plus **10 ALGO closed (observe-only, $+218 unverified, NOT in edge)** — #8 ALGO segregation intact live.
- **Weekly 03–09/05:** **0 discretionary closed** (HONEST zero — 5 open positions carried through, **3 ALGO closed/excluded −$37 unverified**) — exactly the LOCKED weekly shape (0 countable / 3 ALGO-excluded). This is the system correctly distinguishing an honest "0 discretionary this week" from the OLD silent tz-bug "0".

The silent tz "0 קמפיינים" production blocker is **eliminated**. The live accumulated smoke-test (Sprint 11–22) **closes for the PRIMARY defect**.

### Honest number reconciliation (#1 — NOT hand-waved)
Production April = **10 / +$336**; the LOCKED `tests/test_real_data_april_regression.py::_april_df()` = **8 / +$180.49**. These intentionally differ — reconciled with evidence, not asserted:
1. **The locked fixture is a CURATED RCA byte-stability anchor, demonstrably a SUBSET of live April** — concrete evidence: the fixture contains **exactly ONE** ALGO campaign (TSLA), production April closed **TEN** ALGO campaigns. The docstring's "full DB dump" means *sourced from* the dump, not *the entirety of* April.
2. **The fixture uses a TEST account `{"nav": 7922.19, "risk_pct_input": 0.5}`**, not the production account config. R / Net-R / Expectancy / countability (`is_stat_countable` / `classify_stat_bucket`) are R-threshold-sensitive → a different NAV legitimately yields a different countable set & R-metrics **with zero math change**.
3. The Sprint-22 fix is **independently proven math-neutral** (tz-aware == tz-naive == the locked 8/+$180.49, byte-identical, on the SAME fixture). So the production delta is **dataset scope + account NAV**, NOT a tz-fix regression or an over-count.
Exact line-item reconciliation of the live 10/+$336 against raw Supabase rows still requires the read-only probe — see the new defect below.

### NEW defect (separate, now blocking the reconciliation tool) — probe "message too long"
At 20:22 the founder's `🔬 בדיקת נתוני תקופה (Probe)` failed **twice**: `Telegram API ... Error code: 400 ... message is too long`. The Sprint-21/22 probe builds one Telegram string exceeding the 4096-char limit. Note: it failed on LENGTH, not on `Invalid comparison` → the Sprint-22 tz-mirror in the probe plausibly held, but the probe is **unusable** and is exactly the tool needed for the line-item reconciliation above. Candidate fix (Sprint-23): chunk/trim the probe output to Telegram limits (≤~3900 chars/message, split per window) — pure formatting, READ-ONLY contract unchanged, no math. Scope/priority = founder decision.

### Founder decision (post-reconciliation question): **"עצור — אבדוק ידנית קודם"**
Founder will MANUALLY reconcile the live April **10 / +$336** against the raw Supabase rows and report back. Therefore:
- The probe "message too long" fix is **HELD / not started** (no Sprint-23 yet) — pending the founder's manual finding (which may confirm 10/$336 as correct full-dataset, or surface a real over-count to investigate).
- **No code change** from this turn beyond the already-shipped Sprint-22 fix (`638d845`) + this doc trail. Worktree stays clean; nothing touched on the probe or analytics.
- Awaiting: founder's manual line-item reconciliation of 10/+$336 (+ the 10 ALGO / $+218 observe-only and weekly 0/3-ALGO). The Sprint 11–22 smoke-test remains **closed for the PRIMARY tz defect**; full sign-off pends the founder's manual number check.

### DEC-20260516-019 RECONCILIATION COMPLETE — production EXACT vs raw Supabase ✅ (smoke-test fully CLOSED)
Date: 2026-05-16 (founder ran the independent SQL Q1 against raw `trades`; parent reconciled line-by-line)

Founder's raw-row SQL (all campaigns with an April SELL, bucketed) reconciles the production monthly report to the cent — independent of the engine code:
- **COUNTABLE = 10** campaigns; Σ net_pnl = **+$336.14** (report `$+336`); Σ net_r = **+11.01R** (report `+11.01R`); Expectancy **+1.10R**; PF 447.13/110.99 = **4.03**; Win 5/10 = **50.0%**; Missing-Stop **0%** — every headline value EXACT.
- **ALGO_OBSERVED = 10** (HOOD×3, JPM×3, PLTR, QQQ, TSLA×2); Σ net_pnl = **+$217.66** (report `$+218`), correctly excluded from edge — #8 segregation verified on real data.
- **NO over-count, NO regression, NO masking.** The Sprint-22 tz fix is validated end-to-end against raw production data.

**8→10 fully explained (honest):** the LOCKED fixture's 8 + (a) **AEHR_9283303702** — fixture `initial_stop`=68.4 (ABOVE entry 60.3 → invalid → DATA_INCOMPLETE); the LIVE DB now stores `initial_stop`=54.85 (valid) → legitimately countable. The AEHR data was REPAIRED in the DB since the Sprint-21 RCA snapshot — confirmed by the raw SQL value, NOT a fix artifact. (b) **MRVL_9118118916** — a real EP campaign (+$86.31) simply absent from the curated RCA subset. The locked `test_real_data_april_regression.py` stays a valid frozen byte-stability anchor (intentionally NOT live) — still byte-identical.

**Status:** the live accumulated smoke-test (Sprint 11–22) is **fully CLOSED** — primary tz defect fixed AND production numbers independently reconciled exact against raw rows. Remaining OPEN (separate, founder-decided HELD): probe "message too long" (Telegram 400) — formatting-only Sprint-23 candidate; the reconciliation it would have served is now complete via raw SQL, so it is non-blocking.
