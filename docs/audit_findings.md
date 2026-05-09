# Sentinel Trading - Audit Findings

## Scope

This audit branch focuses on five risk areas:

1. Portfolio and risk math correctness.
2. NAV freshness and automatic update contract.
3. Truthfulness of user-facing Telegram reports.
4. Hebrew RTL readability and message length safety.
5. Anti-spam and admin-only bot access.

## Findings

### 1. NAV read/write mismatch

`main.py` writes NAV into `/app/sentinel_config.json`, while `telegram_bot.py` reads `sentinel_config.json` from the current working directory.

Impact: the bot may present stale NAV, stale target risk, wrong exposure percentages, and wrong dollar-risk calculations.

Required fix: use one shared config path helper across the whole project, preferably controlled by `SENTINEL_CONFIG_PATH` with `/app/sentinel_config.json` as production default.

### 2. Fallback values are not clearly marked as estimates

Observed fallback patterns include:

- live price unavailable, then current price falls back to entry price;
- IBKR NAV unavailable, then account size falls back to deposited capital;
- portfolio exposure calculations continue after fallback.

Impact: the user may read estimated or stale data as exact truth.

Required fix: every user-facing report must expose data freshness labels, for example `Live`, `Cached`, `Estimated`, `Fallback`, or `Unavailable`.

### 3. Telegram handlers need explicit admin guard

The bot defines `ADMIN_ID`, but message and callback handlers should reject non-admin chat IDs before any Supabase read/write or portfolio analysis.

Impact: if a third party reaches the bot, they may trigger sensitive reads/writes or spam provider APIs.

Required fix: enforce admin-only access at the first line of each handler.

### 4. Anti-spam / rate-limit guard is missing from handlers

The audit branch adds `telegram_guard.py` and unit tests for burst protection and cooldown behavior.

Required integration: instantiate `TelegramGuard(ADMIN_ID)` in `telegram_bot.py` and call it at the beginning of message and callback handlers.

### 5. CI tests were not present

The branch adds pytest-based regression tests and a GitHub Actions workflow. Some tests are expected to fail until the production code is hardened. That is intentional: these tests define the minimum truth and safety contract.

## Added test coverage

- Engine math thresholds.
- ATR known-value calculation.
- Open campaign quantity and initial risk behavior.
- NAV read/write path consistency.
- Admin-only Telegram handling.
- User-facing fallback disclosure.
- Telegram message length safety.
- Hebrew RTL readability contract.
- Anti-spam guard behavior.

## Recommended implementation order

1. Fix NAV path consistency.
2. Add admin/rate-limit guard to Telegram handlers.
3. Add explicit data freshness labels to Telegram portfolio and drill-down reports.
4. Replace silent fallback behavior with visible warning lines.
5. Run CI and fix any failing math regression tests.
