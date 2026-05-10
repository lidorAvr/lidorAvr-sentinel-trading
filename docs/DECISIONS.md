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
