# Hyperscaler Team — V0 Design

**Date:** 2026-05-14
**Branch:** `claude/review-system-audit-FBZ2h`
**Mission:** Take a system that was built for ONE trader (Mark), ONE portfolio,
ONE Telegram chat, ONE IBKR account — and design a path to multi-tenant SaaS
**without breaking the current production deployment.**

This is a **V0** (read-only investigation + paper design). No production code
was modified. Every claim is backed by a `file:line` reference in the appendix.

---

## Executive summary

- The system is **single-tenant by design**, not by accident. Tenancy is
  baked into ~12 distinct surfaces (env vars, JSON files on a shared volume,
  the Telegram admin guard, the Supabase `trades` schema, the IBKR Flex token,
  and even hardcoded ALGO symbol caps in `engine_core.py:13`). There is **no**
  `user_id` / `account_id` / `tenant_id` anywhere in the codebase or DB schema
  (grep confirmed zero hits).
- Single-tenancy lives in three layers that must be peeled in the right order:
  (1) **state files** on the shared Docker volume (sentinel_config.json,
  risk_monitor_state.json, risk_journal.json, sector_cache.json — all
  global), (2) **identity** (one env-var-bound Telegram admin chat, one
  IBKR Flex token), (3) **methodology** (Minervini SEPA constants hardcoded
  across engine_core, adaptive_risk_engine, risk_monitor).
- **Recommended target architecture:** shared Supabase DB with Row-Level
  Security (RLS) on a mandatory `user_id` column, identity via Supabase Auth
  with a Telegram-link table, methodology as a per-user "profile" record that
  parameterises today's hardcoded constants. **One bot token shared by all
  users** (router by chat_id ↔ user_id), with optional BYO-bot for power users.
- **Migration is 4 phases.** Phase A (additive `user_id` everywhere, default
  to a single `DEFAULT_USER_ID` env var) is the only phase that touches prod
  today, and it is designed to be a **zero-behavior-change** rollout — Mark
  becomes user `00000000-0000-0000-0000-000000000001` and nothing else moves.
  Phase B onwards is purely additive new tables / new routes / new bot
  instances.
- **Hard blockers for SaaS that cannot be solved in code alone:** IBKR Flex
  Query is per-account and requires the customer to generate a token on
  Interactive Brokers' web UI; we cannot programmatically onboard a user.
  This forces a "BYO-broker-token" UX from day one of Phase C.

---

## Phase 1 — Single-user assumption inventory

Severity legend:
- **BLOCKER** — must be fixed before phase B can ship.
- **HIGH** — fix during phase B / phase C; visible bugs if missed.
- **MEDIUM** — quality / scale issue; fix in phase C / D.
- **LOW** — cosmetic / tunable later.

### Identity & authentication

| # | File:line | What is hardcoded / single-tenant | Severity |
|---|---|---|---|
| 1 | `bot_core.py:17-23` | `TELEGRAM_ADMIN_ID` read from env at module import. One integer chat_id. `SystemExit` if missing or non-positive. Every module that imports `bot_core` inherits this single admin. | **BLOCKER** |
| 2 | `telegram_bot_secure_runner.py:30, 42-44` | Hard equality check `chat_id != str(ADMIN_ID)` in `guard_decision()`. Anyone who is not that exact chat_id gets `"⛔ אין הרשאה"`. The rate-limit and cooldown maps are keyed by chat_id but the allow-list is exactly one entry. | **BLOCKER** |
| 3 | `risk_monitor.py:24, 501-502, 506-507` | `ADMIN_ID = os.getenv("TELEGRAM_ADMIN_ID")`. `send_telegram()` and `send_telegram_with_keyboard()` both broadcast to that single ID. Every alert in the system uses one of these two helpers. | **BLOCKER** |
| 4 | `main.py:162-166` | Startup notification sent to the single env `TELEGRAM_ADMIN_ID`. | HIGH |
| 5 | `report_scheduler.py:235, 298, 391` | Weekly + monthly PDF + Telegram delivery all read `TELEGRAM_CHAT_ID` (note: **different env var name** than the rest of the codebase — see SYSTEM_AUDIT_2026_05.md §5). | HIGH |
| 6 | `dashboard.py` (whole file) | **No authentication at all.** Anyone with network access to `:8501` sees the portfolio, edits trades, changes settings (`dashboard.py:1313-1318` mutates Supabase). | **BLOCKER** |
| 7 | `bot_core.py:13-15`, `risk_monitor.py:23, 27` | A single `TELEGRAM_BOT_TOKEN` env var. One bot, one token, one polling loop (`telegram_bot.py:658`). | HIGH |
| 8 | `telegram_bot.py:648-657` | "ONLINE" message at startup hard-coded to `ADMIN_ID`. | LOW |

### Database / data model

| # | File:line | What is hardcoded / single-tenant | Severity |
|---|---|---|---|
| 9 | Supabase `trades` table (schema implicit; see `migrations/001_addon_phase2.sql`, `supabase_repository.py:22-201`) | **No `user_id` / `account_id` column anywhere.** Grep `user_id|account_id|tenant` across the entire `.py` set returns zero matches. Every query is `sb.table("trades").select("*")` with at most a `symbol` or `campaign_id` filter. | **BLOCKER** |
| 10 | `migrations/002_audit_log.sql:4-12` | `audit_log` table has `chat_id BIGINT` but no `user_id`. `chat_id` is the only proxy for "who did this". OK for a single-user system, useless once chat_id is no longer unique-per-tenant. | HIGH |
| 11 | `supabase_repository.py:22-201` (every function) | Every read is unfiltered: `get_all_trades`, `get_trades_by_symbol`, `get_incomplete_trades`, `get_old_trades`, `get_campaigns_pnl`, `get_existing_trade_ids` — all assume one user owns all rows. | **BLOCKER** |
| 12 | `risk_monitor.py:572`, `dashboard.py:61`, `telegram_bot.py:520`, `report_scheduler.py:118` | All four top-level services fetch the entire `trades` table with no tenant filter. | **BLOCKER** |
| 13 | `audit_logger.py:36-69` | `log_action()` writes audit rows with no user_id. Compliance trail becomes ambiguous in multi-tenant. | HIGH |

### Shared per-user state files on the Docker volume

The Docker compose mounts `. : /app`, so **all five containers share one
filesystem**. Every JSON file below is global state that today implicitly
belongs to "the user".

| # | File:line | What is hardcoded / single-tenant | Severity |
|---|---|---|---|
| 14 | `sentinel_config.json` (whole file) | `{"total_deposited": 7500.0, "risk_pct_input": 0.5, "nav": 7922.18}` — one NAV, one risk pct, one deposit base. Read by `account_state.py:11`, `engine_core.py:1489`, `adaptive_risk_engine.py:32, 41-70`, `dashboard.py:31, 42-55`, `ibkr_sync_runner.py:13, 180-189`, `risk_monitor.py:124`, `telegram_bot.py:236-256`, `bot_helpers.py:71`. | **BLOCKER** |
| 15 | `risk_monitor_state.json` (whole file) | Per-symbol anti-spam dedup state (`peak_open_r`, `checkpoints_hit`, `last_giveback_class`, `breakeven_alerted`, `sizing_leak_alerted`, etc.). Top-level keys `last_digest_date`, `last_known_risk_pct`, `risk_alert`. Read in `risk_monitor.py:30`, `bot_helpers.py:12, 50`, `dashboard.py:495`, `bot_health.py:121`. If two users share this file, alerts cross-fire. | **BLOCKER** |
| 16 | `risk_journal.json` (path in `adaptive_risk_engine.py:31, 95-150`) | One-user risk-decision journal (last 500 entries). | HIGH |
| 17 | `risk_recommendations.json` (path in `adaptive_risk_engine.py:30, 575-620`) | Per-user adherence tracking. | HIGH |
| 18 | `sector_cache.json` | Symbol → sector/ETF lookup. Globally safe to share (it's market data, not user data), but currently bundled into the same volume. Keep but make it global. | LOW |
| 19 | `scheduler_state.json` (referenced in `MODULE_MAP.md` §`report_scheduler.py`) | Weekly/monthly dedup. One-user only. | HIGH |
| 20 | `ibkr_sync_state.json` (`main.py:179`, `_handle_manual_trigger`) | One IBKR sync cursor. | HIGH |
| 21 | `/app/state/*_last_cycle` heartbeats | One per service container, not per user. Fine for service health, not for per-tenant SLO tracking. | MEDIUM |

### Broker integration (IBKR)

| # | File:line | What is hardcoded / single-tenant | Severity |
|---|---|---|---|
| 22 | `ibkr_sync_runner.py:106-114` | One `IBKR_TOKEN` env var, one `IBKR_QUERY_ID` (default `1501352` hardcoded). Single Flex Query → single account. | **BLOCKER** |
| 23 | `check_my_trades.py:8-13`, `fetch_live_ibkr.py:9-10` | Same single token & query id. | HIGH |
| 24 | `ibkr_trade_importer.py:23-90` | Parses Flex XML and writes to `trades` with no user_id tagging. The function signature has no tenant parameter. | **BLOCKER** |
| 25 | `ibkr_sync_runner.py:175-189`, `main.py` (manual trigger path) | NAV from `<ChangeInNAV endingValue>` is written into the shared `sentinel_config.json`. One NAV per system. | **BLOCKER** |

### Methodology / opinionated thresholds (Mark's Minervini SEPA)

Every constant below encodes Mark's specific trading methodology. For SaaS,
each must become either a **profile parameter** (varies per user) or a
**system constant** (genuinely universal, kept in code).

| # | File:line | What is hardcoded / single-tenant | Severity |
|---|---|---|---|
| 26 | `engine_core.py:13-16` | `ALGO_SYMBOL_LIMITS = {"QQQ": 10.0, "TSLA": 7.0, "JPM": 7.0, "PLTR": 6.0, "HOOD": 6.0}` + `ALGO_CLUSTER_WARNING_PCT = 30.0` + `ALGO_CLUSTER_CRITICAL_PCT = 35.0`. This is Mark's personal ALGO universe and his personal exposure tolerance. **For SaaS, a user's "ALGO universe" is whatever they trade algorithmically** — this map must become per-user. | **BLOCKER** |
| 27 | `engine_core.py:1685-1708` | Position state machine R-thresholds: `_R_RUNNER=5.0`, `_R_PROFIT_PROTECT=2.0`, `_R_WORKING=1.0`, `_DEAD_MONEY_MIN_DAYS=8`, `_DEAD_MONEY_MIN_R=-0.5`, `_DEAD_MONEY_MAX_R=0.75`, `_DEAD_MONEY_FOLLOW_MAX=50.0`, `_VIOLATION_YELLOW_FLAG=2`, `_VIOLATION_BROKEN=6`. These define what counts as a Runner vs. Dead Money. Different methodologies (e.g. O'Neill 25%, swing traders aiming for 2R) want different numbers. | HIGH |
| 28 | `adaptive_risk_engine.py:20` | `RISK_LADDER = [0.25, 0.40, 0.60, 0.85, 1.15, 1.50, 2.00]`. Seven steps tuned for $5k–$10k portfolios. A $500k account on this ladder would risk $5k–$10k per trade, which most methodologies would call reckless. | **BLOCKER** for portfolio-size tiers |
| 29 | `adaptive_risk_engine.py:27-29` | `DRAWDOWN_TRIGGER_PCT = -8.0`, `DRAWDOWN_CUT_TO_PCT = 0.40`, `DRAWDOWN_WINDOW_DAYS = 30`. Mark's specific drawdown discipline. | HIGH |
| 30 | `adaptive_risk_engine.py:33` | `RISK_SETTLE_HOURS = 48.0`. How long to hold at a new risk level. Methodology-specific. | MEDIUM |
| 31 | `risk_monitor.py:39-52` | `PROFIT_CHECKPOINTS = [2.0, 3.0]`, `DEVIATION_COOLDOWN_SEC = 3h`, `GIVEBACK_COOLDOWN_SEC = 6h`, `LIVE_ALERT_REPEAT_COOLDOWN = 45min`, `SIZING_LEAK_THRESHOLD = 0.65`, `STATE_ALERT_COOLDOWN` table. All Mark-specific tuning. | HIGH |
| 32 | `risk_monitor.py:43-44` | `DAILY_DIGEST_UTC_HOUR_START = 21`, `DAILY_DIGEST_UTC_HOUR_END = 22`. Mon-Fri only. Assumes US-market trader in a single timezone. Asian or European traders will want different windows. | HIGH |
| 33 | `engine_core.py:19-37` | `SECTOR_ETF_MAP` + bootstrap `SECTOR_CACHE` — hardcoded list of US sector ETFs. Fine for US-equity users; broken for crypto / non-US-equity users. | LOW (US-equity assumption is acceptable v1) |
| 34 | `risk_monitor.py:136-144`, `is_during_us_market_hours()` | `11 <= now_utc.hour < 21` Mon-Fri = US session. Globally assumed. | MEDIUM |
| 35 | `account_state.py:91, 39, 46`, `engine_core.py:1509`, `risk_monitor.py:125`, `ibkr_sync_runner.py:181` | NAV fallback of **$7,500** hardcoded everywhere. This is Mark's starting deposit baked into source code as a "safe default". For SaaS this default is wrong for every other user. | HIGH |
| 36 | `README.md:5-6` + `AGENTS.md` whole file | Documentation explicitly names "Mark Minervini's SEPA methodology" as the system's reason for existing. Not a code issue, but a product positioning one. | MEDIUM (for product) |

### Operational / infra

| # | File:line | What is hardcoded / single-tenant | Severity |
|---|---|---|---|
| 37 | `docker-compose.yml` (all 5 services) | All services share volume `.:/app` and read the same JSON state files. A second user cannot simply spin up a second compose stack against the same Supabase without colliding on `trades` rows. | **BLOCKER** |
| 38 | `telegram_bot_secure_runner.py:36-38` | In-memory rate-limit (`defaultdict + deque`) keyed by chat_id. Per-tenant rate isolation works only because there is one tenant. Resets on every container restart. | HIGH |
| 39 | `engine_core.py:17, 66-103` | `YF_CACHE = {}` — in-process yfinance cache. Safe for one process, but in a multi-worker SaaS you want shared (Redis) cache to avoid yfinance rate limits across N tenants. | MEDIUM |
| 40 | No request-context / no `user_id` plumbed through any function signature. | Every function in `engine_core`, `adaptive_risk_engine`, `analytics_engine`, `addon_risk_engine`, `risk_monitor`, `supabase_repository` would need a `user_id` (or `account` / `profile` object) argument. Today: zero do. | **BLOCKER** (volume of change) |

### Summary table

| Severity | Count |
|----------|------:|
| BLOCKER  | 14 |
| HIGH     | 18 |
| MEDIUM   | 6  |
| LOW      | 2  |

---

## Phase 2 — Target architecture

### Tenancy model

**Recommendation: shared Supabase DB + Row-Level Security (RLS), one `users` table, one `user_id` UUID column on every per-tenant table.**

Considered:

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **DB-per-tenant** | Maximal isolation; easy "delete my data" GDPR; can charge differently per DB size. | Operational nightmare at N>5 tenants; migrations × N; backup × N; Supabase doesn't price-favour this. | ❌ |
| **Schema-per-tenant** | Decent isolation; migrations are easier than DB-per-tenant. | Postgres schemas don't scale to thousands; cross-tenant analytics requires UNIONing every schema; Supabase RLS is the idiomatic path. | ❌ |
| **Shared DB + RLS** ✅ | Idiomatic Supabase; cheap; one migration runs for everyone; cross-tenant analytics trivial (admin role); per-row policies enforce isolation. | All-eggs-one-basket: a bad policy = data leak; Postgres performance must be watched as `trades` grows. | ✅ **Pick this.** |

Concrete tables (additive — none of today's tables are renamed):

```sql
-- New tables
CREATE TABLE users (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email           TEXT UNIQUE NOT NULL,
  display_name    TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  status          TEXT NOT NULL DEFAULT 'active',  -- active|suspended|deleted
  tier            TEXT NOT NULL DEFAULT 'small',   -- small|medium|large (size tier)
  methodology     TEXT NOT NULL DEFAULT 'minervini_strict',  -- profile key
  default_telegram_chat_id BIGINT  -- nullable until user links
);

CREATE TABLE telegram_links (
  chat_id    BIGINT PRIMARY KEY,
  user_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  linked_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  bot_token_id UUID  -- nullable; FK to bot_instances when BYO-bot
);

CREATE TABLE broker_links (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  broker     TEXT NOT NULL,        -- 'ibkr' (only v1)
  flex_token_encrypted TEXT NOT NULL,
  query_id   TEXT NOT NULL,
  added_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE account_profiles (
  user_id          UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  nav              NUMERIC NOT NULL DEFAULT 7500.0,
  nav_source       TEXT NOT NULL DEFAULT 'fallback',
  nav_updated_at   TIMESTAMPTZ,
  total_deposited  NUMERIC NOT NULL DEFAULT 7500.0,
  risk_pct_input   NUMERIC NOT NULL DEFAULT 0.5,
  risk_changed_ts  TIMESTAMPTZ,
  risk_changed_dir TEXT,
  -- replaces sentinel_config.json
  raw_config_json  JSONB
);

CREATE TABLE methodology_profiles (
  key              TEXT PRIMARY KEY,           -- 'minervini_strict', 'minervini_relaxed', 'oneill', 'swing_low_risk'
  display_name     TEXT NOT NULL,
  risk_ladder      JSONB NOT NULL,             -- replaces adaptive_risk_engine.RISK_LADDER
  drawdown_trigger_pct NUMERIC NOT NULL,
  drawdown_cut_to_pct  NUMERIC NOT NULL,
  drawdown_window_days INT NOT NULL,
  r_runner             NUMERIC NOT NULL,       -- replaces engine_core._R_RUNNER
  r_profit_protect     NUMERIC NOT NULL,
  r_working            NUMERIC NOT NULL,
  dead_money_min_days  INT NOT NULL,
  dead_money_min_r     NUMERIC NOT NULL,
  dead_money_max_r     NUMERIC NOT NULL,
  violation_yellow_flag INT NOT NULL,
  violation_broken     INT NOT NULL,
  profit_checkpoints   JSONB NOT NULL,         -- e.g. [2.0, 3.0]
  sizing_leak_threshold NUMERIC NOT NULL,
  digest_utc_hour_start INT NOT NULL,
  digest_utc_hour_end   INT NOT NULL,
  digest_days_of_week   JSONB NOT NULL,        -- e.g. [0,1,2,3,4] Mon-Fri
  algo_cluster_warning_pct  NUMERIC NOT NULL,
  algo_cluster_critical_pct NUMERIC NOT NULL,
  notes_md         TEXT
);

CREATE TABLE algo_universe (
  user_id   UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  symbol    TEXT NOT NULL,
  cap_pct   NUMERIC NOT NULL,
  PRIMARY KEY (user_id, symbol)
);

-- Migration to existing tables (additive, default-backed)
ALTER TABLE trades       ADD COLUMN user_id UUID REFERENCES users(id);
ALTER TABLE audit_log    ADD COLUMN user_id UUID REFERENCES users(id);
CREATE INDEX idx_trades_user_id    ON trades   (user_id);
CREATE INDEX idx_audit_log_user_id ON audit_log(user_id);

-- RLS (turned on AFTER phase A backfills every row)
ALTER TABLE trades            ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log         ENABLE ROW LEVEL SECURITY;
ALTER TABLE account_profiles  ENABLE ROW LEVEL SECURITY;
ALTER TABLE algo_universe     ENABLE ROW LEVEL SECURITY;
-- policy example:
CREATE POLICY trades_owner ON trades
  USING (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());
```

State files that today live on disk become rows:

- `sentinel_config.json` → `account_profiles` row.
- `risk_journal.json` → new `risk_journal` table with `user_id` + 500-row TTL per user.
- `risk_recommendations.json` → new `risk_recommendations` table.
- `risk_monitor_state.json` → new `risk_monitor_state` table keyed by `(user_id, position_key)` + a global keys table for `last_digest_date` per user.
- `scheduler_state.json` → `scheduler_state` table.
- `ibkr_sync_state.json` → `broker_sync_state` table.
- `sector_cache.json` → stays a global file (it's market data, not user data); can later move to a `global_sector_map` table.

### Identity & auth

**Recommendation: Supabase Auth (email + magic link) as the source of truth; Telegram and IBKR are linked artifacts.**

```
1. Sign up:   email + magic-link via Supabase Auth → row inserted in `users`.
2. Link Telegram:
   - User opens our marketing site → clicks "Connect Telegram".
   - We generate a one-time code (UUID, TTL 10min, stored in `telegram_link_codes`).
   - User DMs our shared bot with `/link <code>`.
   - Bot resolves code → inserts (chat_id, user_id) into `telegram_links`.
3. Link IBKR:
   - We point the user at IB's Flex Query setup docs.
   - User pastes their Flex Token + Query ID into our web form.
   - We encrypt with a per-row KEK (Supabase Vault) and store in `broker_links`.
4. Dashboard auth:
   - Streamlit replaced (or wrapped) with Supabase Auth — see Phase 3 / Phase C.
   - Until then: dashboard goes behind a reverse-proxy with basic auth + per-user URL slug.
```

Open security points:

- **Telegram chat_id is not authentication** — anyone can spoof a chat_id if the bot is BYO. Our shared bot is safe because Telegram authenticates the chat. The `/link <code>` flow is the binding moment.
- **IBKR Flex Token = read-only**, which is the right primitive for SaaS. It cannot place trades. We must still encrypt at rest (Supabase Vault, AES-256).

### Per-user config schema

What lives where:

| Lives in… | Examples | Rationale |
|---|---|---|
| **Code (system constants)** | Status names ("Power", "Healthy"), Hebrew label strings, alert priority tiers (`risk_monitor.py:55-71`), Markdown templates, sector ETF map | Truly universal; changing them means changing the product. |
| **`methodology_profiles` table (admin-curated, user-selectable)** | `RISK_LADDER`, `_R_RUNNER`, `_DEAD_MONEY_MIN_DAYS`, `PROFIT_CHECKPOINTS`, `SIZING_LEAK_THRESHOLD`, `DAILY_DIGEST_UTC_*`, `ALGO_CLUSTER_WARNING_PCT` | Methodology-specific; we curate 3-4 profiles; users pick one. Cannot be edited by users (would let them "tune" themselves into unsafe defaults). |
| **`account_profiles` table (per-user, user-editable)** | NAV, total_deposited, risk_pct_input, timezone, language preference, default chat_id | Per-account state that changes daily. |
| **`algo_universe` table (per-user, user-editable)** | Their ALGO symbols + caps. Mark's `{QQQ: 10, TSLA: 7, ...}` becomes his row set. | Personal universe; varies wildly per user. |
| **Local on-disk (no longer per-user)** | `sector_cache.json` only. Optional Redis cache for yfinance. | Market data, safe to share. |

Resolution order at runtime:

```
target = methodology_profiles[users[uid].methodology][param]    # baseline
       overlaid by account_profiles[uid].risk_pct_input         # account-specific
       overlaid by algo_universe[uid] for ALGO caps             # symbol-specific
```

### Methodology profiles

Three profiles to ship at Phase D launch:

| Key | Display | Risk ladder | RUNNER R | Dead-money min days | Sizing leak | Digest hours UTC | Notes |
|---|---|---|---|---|---|---|---|
| `minervini_strict` | "Minervini — קלאסי" | `[0.25, 0.40, 0.60, 0.85, 1.15, 1.50, 2.00]` | 5.0 | 8 | 0.65 | 21-22 Mon-Fri | Today's defaults — Mark's profile. |
| `minervini_relaxed` | "Minervini — גמיש" | `[0.35, 0.60, 0.85, 1.15, 1.50, 2.00, 2.50]` | 4.0 | 10 | 0.55 | 21-22 Mon-Fri | Slightly looser; for new users still learning the methodology. |
| `oneill_classic` | "O'Neill CAN SLIM" | `[0.30, 0.50, 0.75, 1.00, 1.50, 2.00]` | 4.0 (25% target) | 6 | 0.70 | 21-22 Mon-Fri | O'Neill's 7-8% stop, 20-25% gain rule. |
| `swing_low_risk` | "סווינג שמרני" | `[0.15, 0.25, 0.40, 0.60, 0.85]` | 3.0 | 5 | 0.50 | 19-20 UTC (EU close) | Short-hold swing trader; smaller R, tighter dead-money window. |

**Engineering rule:** every constant flagged in Phase 1 §"Methodology" must be read via a `MethodologyProfile` object passed into the function — never as a module-level import. Code review gate: any new constant in `engine_core.py` / `adaptive_risk_engine.py` / `risk_monitor.py` that influences trader behaviour must also have a column in `methodology_profiles`.

### Portfolio size tiers

| Tier | NAV range | Difference vs. baseline |
|---|---|---|
| **small** | < $25k | Today's defaults. Risk ladder caps at 2.0%. Position count cap 6. Pattern Day Trader rule (US) shown as warning in `/portfolio`. |
| **medium** | $25k–$200k | Same risk ladder but absolute USD caps kick in: `target_risk_usd_max = $2,000`. Position count cap 12. Margin call awareness in alerts. |
| **large** | > $200k | Risk ladder compressed: `[0.10, 0.15, 0.20, 0.30, 0.40, 0.50]` — the 2.00% top-step would be $4k+ per trade and is rarely correct at this size. Position count cap 20. Block-trade slippage warning (>1% of ADV) added to drill-down. Tax-lot tracking surfaced. |

Tier is **derived from NAV**, not user-chosen, with a 60-day moving NAV to prevent flapping. Profile choice is orthogonal to tier (a Minervini-strict user at $5k and a Minervini-strict user at $500k get the same methodology but different absolute caps).

### Resource isolation

The current `risk_monitor.py` runs one main loop, fetches every position, then iterates. With N users, the naive approach is `for user in users: run_cycle(user)` — but one slow yfinance call or one timing-out IBKR sync would block every other user.

**Recommendation: per-user task workers behind a job queue.**

```
[scheduler]   →  enqueues  →  [Redis/RQ or Supabase Edge Function queue]
                                     ↓
                              [N worker processes]   ←  scale N independently
                                     ↓
                              one user_id per job
                                     ↓
                            tenant-scoped DB session (RLS on)
                            tenant-scoped per-process yfinance cache
                            tenant-scoped Telegram send (resolved via telegram_links)
```

Concrete components:

- **Job queue:** Supabase has no native job queue but RQ on Redis is the simplest path. Alternatively, Postgres LISTEN/NOTIFY + a Python consumer (no new infra).
- **Yfinance cache:** move from in-process `YF_CACHE` (`engine_core.py:17`) to Redis with a 5-min TTL. Shared across tenants because the data is the same.
- **IBKR rate limiting:** IB Flex Query is per-token, not global, so per-user tokens isolate naturally. But "send-then-wait-15s-then-fetch" (`ibkr_sync_runner.py:144-148`) is a 15+ second blocking call — must happen in a worker, not in the request path.
- **Telegram outbound:** Telegram caps a bot at ~30 messages/sec globally. With one shared bot at scale we need a per-bot outbound queue with priority lanes (Tier 1 alerts > Tier 3 digests). Or, BYO-bot users bypass this entirely.
- **Bot polling:** today `bot.infinity_polling()` blocks one process for one bot. SaaS with a shared bot uses webhook mode behind a public HTTPS endpoint; routing by chat_id → user_id happens in the webhook handler. BYO-bot users still get a polling worker pinned to their token.

Latency / SLO target:
- P95 risk_monitor cycle per user: <2s.
- Worst-case yfinance call must time out at 5s (today: 30s on IBKR, no timeout on yfinance).

---

## Phase 3 — 4-phase migration plan

Guiding principle: **Mark's production must keep working at every step.** Each phase is independently deployable and independently rollback-able.

### Phase 0 — Today (no change)

Single user, monolithic, env-var-bound. Documented baseline. **This is what the migration must not break.**

### Phase A — Additive `user_id`, single-user default (≈ 2 weeks of work)

**Goal:** introduce the `user_id` concept everywhere with **zero behaviour change** for Mark.

What changes:

1. **DB migration 003**: add nullable `user_id UUID` columns to `trades` and `audit_log`. Add `users`, `account_profiles`, `telegram_links`, `broker_links`, `methodology_profiles`, `algo_universe` tables. Do **not** enable RLS yet. Seed one row in `users` for Mark (UUID `00000000-0000-0000-0000-000000000001`); seed his `minervini_strict` methodology profile; seed his `algo_universe` from `engine_core.py:13`.
2. **Env var `DEFAULT_USER_ID`** added everywhere `TELEGRAM_ADMIN_ID` is read today. Both env vars co-exist. New `user_context.py` module: `current_user_id() → DEFAULT_USER_ID if not in webhook context else lookup from telegram_links`.
3. **Backfill script** (migrations/003_*.py): every existing row in `trades` and `audit_log` gets `UPDATE … SET user_id = DEFAULT_USER_ID WHERE user_id IS NULL`.
4. **Repository layer** (`supabase_repository.py`): every function gains a `user_id` arg; all reads add `.eq("user_id", user_id)`. **Default arg** = `current_user_id()`. Phase A does **not** force callers to pass it — they still work without it.
5. **Tests**: add `test_user_isolation.py` proving (a) Mark's existing queries still return all his rows, (b) a second seeded user's rows are not visible to Mark's queries.

What does NOT change in Phase A:

- The Docker compose file.
- The Telegram bot architecture (still one bot, still polling).
- `sentinel_config.json` and all the JSON state files.
- The hardcoded methodology constants in code.
- Anything user-facing.

Risks: SQL migration runs against production data; backfill could be slow on large `trades` tables; null `user_id` columns until backfill completes.

Rollback: drop the new columns + new tables; restore from snapshot. The env var `DEFAULT_USER_ID` is harmless on its own.

Test plan: `pytest -q` passes; manual smoke = `/portfolio` returns same row count as before; one fresh second-user UUID seeded in staging and verified that their `/portfolio` returns empty.

Effort: ~10 dev-days. Mostly schema work and repository plumbing.

### Phase B — JSON state → DB; methodology profiles activated (≈ 4 weeks)

**Goal:** move all per-user state out of the shared `/app` volume into the DB; activate the methodology profile resolution path; still one user, but the architecture now permits a second.

What changes:

1. **`account_profiles` table** populated from `sentinel_config.json` for Mark. New `account_state.py` reads from DB; falls back to file only if env `LEGACY_CONFIG_FILE=1` (kill-switch).
2. **`risk_monitor_state.json` → DB**. New table `risk_monitor_state(user_id, position_key, blob jsonb)`. Backfill from the existing JSON file. The 45-min cooldown / digest dedup keys now persist properly across container restart (today they survive but only because the file is on a persistent volume).
3. **`risk_journal.json`, `risk_recommendations.json` → DB tables**. Migrated by a one-shot script.
4. **`methodology_profiles` rows seeded** (minervini_strict, minervini_relaxed, oneill_classic, swing_low_risk). Mark's `users.methodology` is set to `minervini_strict`. New `methodology.py` module: `get_profile(user_id) → MethodologyProfile`. Every previously-hardcoded constant in `engine_core.py:1685-1708`, `adaptive_risk_engine.py:20-33`, `risk_monitor.py:39-52` now reads from the profile object passed in.
5. **`algo_universe` rows seeded** from `engine_core.py:13`. Mark gets the same QQQ/TSLA/JPM/PLTR/HOOD caps. `compute_algo_oversight_summary()` and friends now query `algo_universe` for the calling user.
6. **`audit_log.user_id` populated** at every write site (`audit_logger.log_action()` gains a required `user_id` arg).
7. **Dashboard auth**: gate `dashboard.py` behind Supabase Auth (or, as a stop-gap, reverse-proxy basic auth + per-user URL slug). No multi-user UI yet — just preventing the open `:8501` from being world-readable.
8. **`telegram_bot_secure_runner.py`** updated: `guard_decision()` consults `telegram_links` table instead of single env var. For now the table has one row (Mark's chat_id → Mark's user_id) so behaviour is unchanged.

Risks: state migration is one-way; if `risk_monitor_state` table is wrong, anti-spam dedup breaks and Mark gets duplicate alerts. **Mitigation:** dual-write for 1 week (write to both file and DB, read from file), then flip read, then stop writing to file.

Rollback: feature-flag `STATE_BACKEND=file|db`. Re-run with `=file` and the JSON files (kept in the volume backup) take over again.

Test plan: full `pytest -q`; manual = a full risk_monitor cycle with one position triggers same alerts as before; dual-write verifies file and DB stay in sync for one cycle.

Effort: ~20 dev-days. Main risk is anti-spam state correctness.

### Phase C — Real multi-tenant routing + IBKR onboarding flow (≈ 6 weeks)

**Goal:** enable a **second real user** to sign up and use the system. Mark is unchanged; user #2 is the first stress test.

What changes:

1. **Marketing site + email/magic-link signup** (Supabase Auth). Onboarding wizard: choose methodology profile → paste IBKR Flex token → DM the bot a code.
2. **Webhook mode for the Telegram bot.** `bot.infinity_polling()` retired in favour of a Flask/FastAPI webhook endpoint behind HTTPS. Inbound message → resolve chat_id via `telegram_links` → set `user_context.user_id` for the duration of the handler → dispatch to existing handlers (now all `user_id`-aware after Phase A/B).
3. **Per-user IBKR sync workers.** The current `main.py` loop becomes a per-user job scheduled by cron + RQ. Each worker pulls one user's Flex token from `broker_links` and runs `run_ibkr_sync()` scoped to that user.
4. **Per-user `risk_monitor` cycles.** A scheduler enqueues one job per active user every 60 seconds. Worker concurrency tuned to keep P95 cycle <2s.
5. **Outbound Telegram rate limiter** (Redis token bucket) gates the shared-bot global 30/sec limit.
6. **RLS turned on** for `trades`, `audit_log`, `account_profiles`, `algo_universe`, `risk_monitor_state`, `risk_journal`, `risk_recommendations`. The Supabase service role used by workers bypasses RLS; the dashboard's user-scoped role uses RLS for defense-in-depth.
7. **Per-tenant resource caps:** max 25 open positions, max 1 broker per user (v1), max 1 Telegram chat per user (v1).
8. **Multi-tenant dashboard.** Streamlit page-per-user keyed by `st.session_state.user_id` after Supabase auth.
9. **Onboarding tests:** `test_e2e_signup.py` simulates signup → link Telegram → link IBKR → first sync → first alert.

Risks: RLS misconfiguration = data leak across tenants (highest-stakes risk in the entire migration). **Mitigation:** dedicated security-review PR with manual penetration test; every table's RLS policy reviewed by two engineers; integration test that runs as user B and tries to read user A's rows must return zero.

Rollback: feature-flag `MULTI_TENANT=on/off`. With it off, the webhook still resolves Mark's chat_id and the old single-user code path runs.

Test plan: full `pytest -q` + new RLS test suite + manual two-user smoke. Mark's behaviour must be bit-for-bit identical before and after the cutover (snapshot comparison of `/portfolio` and weekly PDF).

Effort: ~30 dev-days.

### Phase D — Full SaaS (≈ ongoing)

**Goal:** the product is sellable. Mark is one of many.

What changes:

- Billing (Stripe), pricing tiers tied to portfolio-size tiers.
- BYO-bot for paying customers (per-user `TELEGRAM_BOT_TOKEN` stored in `bot_instances` table; per-bot polling worker).
- More methodology profiles (community-contributed, admin-curated).
- Public-facing docs + onboarding videos.
- Status page + per-tenant SLO dashboard.
- Multi-broker support (Schwab, Robinhood) added behind the `broker_links` abstraction.
- Cross-tenant analytics (admin role, anonymised) for product insight.

This phase is open-ended product work, not a step-change in architecture.

---

## Phase 4 — Open questions for the founder

These must be answered before Phase B kicks off — they shape the data model.

1. **Methodology breadth.** Are we keeping Mark's Minervini SEPA as the only methodology, or are we offering 3-4 curated alternatives at Phase D launch? (Affects `methodology_profiles` schema scope and onboarding UX.)
2. **One bot or many?** All users share one Telegram bot token (cheaper, simpler routing, but Telegram's 30 msg/sec global cap is real), or every paying customer gets their own bot? (Affects polling vs webhook architecture and the `bot_instances` table.)
3. **Broker scope v1.** Is IBKR the only broker we target through Phase D, or do we need a `broker` abstraction from day one of Phase B? (Affects `broker_links` shape and the `ibkr_*` module renames.)
4. **NAV freshness SLA.** Today NAV updates once-per-morning via Flex Query (07:00-11:00 Asia/Jerusalem, `main.py`). For paying customers, do we promise intraday NAV updates? If so, IBKR Flex is the wrong tool — we'd need TWS gateway, which is dramatically more complex.
5. **Dashboard scope.** Does the multi-tenant dashboard (`dashboard.py`) stay Streamlit-and-Hebrew, or do we rebuild it as a proper web app (React/Next.js) with i18n? (Streamlit at scale is painful; but rewriting is 4+ weeks.)
6. **Pricing model.** Flat monthly per user, tiered by portfolio size, or commission-style (% of NAV)? (Affects what we need to track in `users` and `account_profiles`.)
7. **Data retention.** Is the trade history deleted on account close, or kept (anonymised) for system-wide research? (Affects RLS policies, GDPR posture, and DB sizing.)
8. **Audit / compliance.** Do we need SOC 2 / financial-services compliance from launch? (If yes, the `audit_log` table needs immutability constraints, encrypted at rest, time-bound retention. Adds 2-4 weeks.)
9. **Mark's own data.** Is Mark's production data treated as a real customer in the new system, or is it isolated in a "founder" DB? (We recommend treating Mark as user #1 in the same DB — but that means he's affected by RLS bugs. Tradeoff: realism vs safety.)
10. **Hebrew-first vs i18n.** Every Telegram template today is Hebrew-only (`telegram_formatters.py`, `risk_monitor.py` alert text). Are we i18n-ing at Phase C, or staying Hebrew-only for v1? (Affects the template layer scope.)
11. **Live price data source.** Today `yfinance` is the only source (engine_core.py:81-104) — it's free, rate-limited, and *not licensed for redistribution*. At any commercial scale we need a paid feed (Polygon, IEX, Alpaca). Who buys those licenses and when?
12. **ALGO observer mode applicability.** Mark's ALGO concept ("Sentinel observes only, doesn't manage") is specific to his setup of running a separate algo system. For SaaS users with no algo: do they even see the ALGO column / cluster alerts? Is it a feature flag per profile, or do we ship a "manual-only" profile that hides ALGO entirely?

---

## Appendix — Code references

All paths absolute. Line numbers from branch `claude/review-system-audit-FBZ2h` at this commit.

### Single-user identity surfaces

- `/home/user/lidorAvr-sentinel-trading/bot_core.py:13-23` — TELEGRAM_BOT_TOKEN + TELEGRAM_ADMIN_ID validated at import, `SystemExit` on missing.
- `/home/user/lidorAvr-sentinel-trading/telegram_bot_secure_runner.py:30, 42-44` — `guard_decision()` enforces single chat_id.
- `/home/user/lidorAvr-sentinel-trading/telegram_bot_secure_runner.py:36-38` — in-memory rate-limit maps.
- `/home/user/lidorAvr-sentinel-trading/telegram_bot.py:11, 648-657` — startup notification to ADMIN_ID.
- `/home/user/lidorAvr-sentinel-trading/risk_monitor.py:23-28, 501-508` — single-admin send helpers.
- `/home/user/lidorAvr-sentinel-trading/main.py:161-166` — startup Telegram via single admin id.
- `/home/user/lidorAvr-sentinel-trading/report_scheduler.py:234-240, 297-303, 390-396` — uses `TELEGRAM_CHAT_ID` (different env var name).
- `/home/user/lidorAvr-sentinel-trading/dashboard.py` — no authentication.

### Supabase / data layer

- `/home/user/lidorAvr-sentinel-trading/supabase_repository.py:22-201` — every read/write is global (no user_id filter).
- `/home/user/lidorAvr-sentinel-trading/migrations/001_addon_phase2.sql:1-13` — adds addon columns; no user_id.
- `/home/user/lidorAvr-sentinel-trading/migrations/002_audit_log.sql:1-23` — chat_id only, no user_id.
- `/home/user/lidorAvr-sentinel-trading/audit_logger.py:36-69` — `log_action()` has no user_id arg.
- `/home/user/lidorAvr-sentinel-trading/risk_monitor.py:572-578` — unfiltered fetch.
- `/home/user/lidorAvr-sentinel-trading/dashboard.py:59-73` — unfiltered fetch + Streamlit cache.
- `/home/user/lidorAvr-sentinel-trading/dashboard.py:1313-1318` — unfiltered Supabase update.
- `/home/user/lidorAvr-sentinel-trading/telegram_bot.py:520` — unfiltered fetch.
- `/home/user/lidorAvr-sentinel-trading/report_scheduler.py:118-127` — unfiltered fetch (only date filter).

### Shared state files

- `/home/user/lidorAvr-sentinel-trading/sentinel_config.json` — global NAV/risk pct.
- `/home/user/lidorAvr-sentinel-trading/account_state.py:11, 39-47` — reader.
- `/home/user/lidorAvr-sentinel-trading/engine_core.py:1489-1535` — second reader.
- `/home/user/lidorAvr-sentinel-trading/adaptive_risk_engine.py:32, 41-70` — writer.
- `/home/user/lidorAvr-sentinel-trading/dashboard.py:31, 42-55` — writer.
- `/home/user/lidorAvr-sentinel-trading/ibkr_sync_runner.py:13, 180-189` — writer (NAV).
- `/home/user/lidorAvr-sentinel-trading/risk_monitor.py:122-125` — reader.
- `/home/user/lidorAvr-sentinel-trading/telegram_bot.py:236-256` — reader (dev menu).
- `/home/user/lidorAvr-sentinel-trading/bot_helpers.py:12, 50, 71` — reader/writer.
- `/home/user/lidorAvr-sentinel-trading/risk_monitor_state.json` — global anti-spam state.
- `/home/user/lidorAvr-sentinel-trading/risk_monitor.py:30` — owner.
- `/home/user/lidorAvr-sentinel-trading/bot_helpers.py:12, 50` — concurrent writer.
- `/home/user/lidorAvr-sentinel-trading/dashboard.py:495` — reader.
- `/home/user/lidorAvr-sentinel-trading/risk_journal.json` (path-only) — `adaptive_risk_engine.py:31, 95-150`.
- `/home/user/lidorAvr-sentinel-trading/risk_recommendations.json` — `adaptive_risk_engine.py:30, 575-620`.
- `/home/user/lidorAvr-sentinel-trading/sector_cache.json` — safe-global; only writer is `scripts/archive/system_cleanup_and_backup.py:14`.

### Methodology constants (Mark's opinions)

- `/home/user/lidorAvr-sentinel-trading/engine_core.py:13-16` — ALGO symbol/cluster caps.
- `/home/user/lidorAvr-sentinel-trading/engine_core.py:1685-1708` — R thresholds + dead-money + violation.
- `/home/user/lidorAvr-sentinel-trading/engine_core.py:19-37` — sector ETF map.
- `/home/user/lidorAvr-sentinel-trading/adaptive_risk_engine.py:20` — RISK_LADDER.
- `/home/user/lidorAvr-sentinel-trading/adaptive_risk_engine.py:27-33` — drawdown + settle.
- `/home/user/lidorAvr-sentinel-trading/risk_monitor.py:39-52` — profit checkpoints + cooldowns + state-alert cooldowns + sizing leak.
- `/home/user/lidorAvr-sentinel-trading/risk_monitor.py:43-44, 136-144` — daily digest UTC hours + US market window.

### Broker integration

- `/home/user/lidorAvr-sentinel-trading/ibkr_sync_runner.py:106-114` — single IBKR_TOKEN + IBKR_QUERY_ID (default `1501352`).
- `/home/user/lidorAvr-sentinel-trading/check_my_trades.py:8-13` — same single token.
- `/home/user/lidorAvr-sentinel-trading/fetch_live_ibkr.py:9-10` — same single token.
- `/home/user/lidorAvr-sentinel-trading/ibkr_trade_importer.py:23-90` — no user_id tagging on insert.
- `/home/user/lidorAvr-sentinel-trading/ibkr_sync_runner.py:172-190` — writes NAV into shared `sentinel_config.json`.

### Infrastructure

- `/home/user/lidorAvr-sentinel-trading/docker-compose.yml:1-169` — five services, shared `.:/app` volume, shared `sentinel_state` named volume, single bot command.
- `/home/user/lidorAvr-sentinel-trading/engine_core.py:17, 66-104` — in-process YF_CACHE (would need Redis at scale).
- `/home/user/lidorAvr-sentinel-trading/telegram_bot.py:658` — `bot.infinity_polling()` (would need webhooks at scale).

### Fallback hardcoded values

Everywhere the literal `7500.0` appears (Mark's starting deposit, used as a "safe" fallback for everyone):

- `/home/user/lidorAvr-sentinel-trading/account_state.py:39, 46, 91`
- `/home/user/lidorAvr-sentinel-trading/engine_core.py:1509`
- `/home/user/lidorAvr-sentinel-trading/risk_monitor.py:125, 565`
- `/home/user/lidorAvr-sentinel-trading/ibkr_sync_runner.py:181`
- `/home/user/lidorAvr-sentinel-trading/dashboard.py:48, 103, 108`
- `/home/user/lidorAvr-sentinel-trading/bot_helpers.py` (via load helpers)

This value should become `methodology_profiles.default_fallback_nav` or be eliminated entirely in favour of refusing to compute when NAV is unknown.
