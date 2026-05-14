# Safe Change Protocol

This protocol is mandatory for humans and AI agents working on this repo.

## Goal

Improve the system without breaking unrelated parts.

The system has multiple coupled areas:

- broker/account sync
- Supabase trade records
- Telegram workflows
- risk engine
- dashboard
- risk monitor
- Docker deployment

A change in one area can break another area. Always reason about downstream impact.

## Change categories

### Low-risk changes

Examples:

- documentation updates
- wording improvements that do not affect commands or parsing
- adding tests
- adding non-used helper functions

Process:

1. Make the change.
2. Run tests.
3. Verify no production command changed unexpectedly.

### Medium-risk changes

Examples:

- Telegram message formatting
- dashboard layout
- adding a new read-only report
- adding a new non-mutating metric

Process:

1. Identify user-facing behavior.
2. Keep the old path working.
3. Add a fallback if data is missing.
4. Add tests where possible.
5. Manually test Telegram/dashboard behavior.

### High-risk changes

Examples:

- R-multiple math
- NAV/account size handling
- open campaign aggregation
- Supabase writes
- Docker Compose commands
- Telegram authorization / anti-spam
- any auto-management or auto-update behavior
- risk_monitor alert logic and state machine

Process:

1. Stop and document the intended behavior.
2. Add or update tests first.
3. Use sample rows and edge cases.
4. Make a small change.
5. Run tests.
6. Verify Docker command if service behavior changed.
7. Document rollback.

## Mandatory impact checklist

Before changing code, answer these questions in the PR/commit notes or working notes:

1. Which service is affected?
2. Does it read or write Supabase?
3. Does it affect NAV, R, exposure, PnL, or stop logic?
4. Does it affect Telegram output?
5. Does it affect Docker deployment?
6. Does it introduce live API dependency?
7. What is the rollback path?

## Rules for `engine_core.py`

`engine_core.py` is the math engine. Treat it like a library.

Do:

- add deterministic unit tests
- use small pure helper functions
- document new risk formulas
- keep old behavior unless intentionally changed

Do not:

- change formulas silently
- add network calls to functions that should be pure
- mix user-facing Hebrew strings deeply into core formulas unless already existing
- make campaign logic depend on UI assumptions

## Rules for `risk_monitor.py`

`risk_monitor.py` is the automated alert and anti-spam state machine. Treat changes here as high-risk.

### Alert deduplication invariants

Every new alert type introduced in `risk_monitor.py` must:

1. Have a **per-position boolean flag** in `risk_monitor_state.json` (e.g., `sizing_leak_alerted`, `breakeven_alerted`).
2. Add that flag key to the **carry-over key list** at the top of the position loop.
3. Check the flag before sending: `if not new_pos_entry.get("flag_name", False):`.
4. Set the flag to `True` immediately after sending.
5. Never re-fire the alert based on a timer/cooldown alone within the same state.

Violating these invariants causes alert spam, which degrades the user's trust in the system.

### Giveback zone rules

- Giveback alerts must fire only when the **zone classification changes** (`gb["classification"] != prev_gb_class`).
- Firing must also require that the current or previous zone is in `alert_classes` (`{"watch", "tighten", "protection_failure"}`).
- Do NOT add a cooldown-based re-fire within the same zone. Zone-change detection already throttles it correctly.
- `last_giveback_class` must always be updated after every cycle, even when no alert fires.

### BROKEN state gate

When a position reaches `POSITION_STATE_BROKEN`, the following alerts are suppressed:

- Giveback alerts
- Any alert that assumes the position is still developing

The guard pattern is:
```python
if peak_open_r >= 1.5 and open_r < peak_open_r and _pos_state != ec.POSITION_STATE_BROKEN:
    # Giveback logic here
```

Do not remove this guard.

### Alert key rules

- `build_position_alert_key()` must NOT include `trigger` in the key.
- Including trigger causes Live Alert to fire on every minor price movement, which is spam.
- Non-escalating key changes fire at most once per `LIVE_ALERT_REPEAT_COOLDOWN` (45 min).
- Status escalations (higher `STATUS_RANK`) bypass the cooldown and always fire.

### Daily Digest rules

- Daily Digest fires **once per calendar day** only, tracked by `last_digest_date`.
- Window: 21:00–22:00 UTC, Monday–Friday only.
- It is not a Live Alert — do not add it to the position-level alert key or cooldown logic.

## Rules for `telegram_bot.py`

`telegram_bot.py` is long and high-risk.

Do:

- keep changes narrow
- extract helpers to new modules
- preserve existing commands
- keep `send_long_message` for long reports
- keep Hebrew output readable

Do not:

- rewrite the whole file in one pass
- remove existing callback formats without migration
- add new Supabase writes without documenting them
- bypass `telegram_bot_secure_runner.py`

## Rules for `telegram_bot_secure_runner.py`

This file protects the bot until the Telegram layer is refactored.

Do:

- keep access control and rate limit active
- keep behavior deterministic
- keep messages short

Do not:

- remove admin checks
- remove cooldown behavior
- call Supabase from this wrapper
- add complex business logic here

## Rules for Supabase writes

Every write must be intentional.

Safe examples:

- user explicitly submitted a quality score
- user explicitly entered an initial stop
- deterministic backlog inheritance from same campaign

Unsafe examples:

- auto-changing stops from analysis output without user confirmation
- overwriting setup type from weak inference
- filling unknown values with defaults that look real

## Rules for fallback data

Fallbacks are allowed only if marked.

Examples of fallback:

- live price unavailable, using last close
- IBKR NAV unavailable, using deposited capital
- sector unavailable, using cached hardcoded sector map

User-facing reports must mark this as estimated/cached/fallback.

## Rollback protocol

If production breaks after a change:

1. Stop only the affected service if possible.
2. Check logs.
3. Revert the last commit or restore previous command.
4. Rebuild only the affected container.
5. Verify Telegram and dashboard manually.

Common rollback for Telegram runner:

```bash
docker compose stop telegram-bot
# temporarily revert command to python3 telegram_bot.py only if secure runner itself is the problem
docker compose up -d --build telegram-bot
```

Use direct `telegram_bot.py` only as an emergency rollback, because it bypasses the runner protections.

Common rollback for risk-monitor:

```bash
docker compose stop risk-monitor
git revert <commit_sha>
docker compose up -d --build risk-monitor
docker logs -f risk-monitor
```

## Refactor protocol

When splitting long files:

1. Extract one concern at a time.
2. Keep public function behavior identical.
3. Add tests around extracted behavior.
4. Do not mix refactor with feature changes.
5. Commit refactor separately from behavior changes.

Recommended future splits:

- `telegram_handlers.py`
- `telegram_formatters.py` ✅ done (Phase 4)
- `telegram_backlog.py` ✅ done (Phase 4)
- `portfolio_reports.py`
- `supabase_repository.py` ✅ done (Phase 4)
- `risk_formatters.py`
- `config.py`

---

## Lessons from Sprint 10 / 11 (2026-05-14)

### Default-arg binding to module constants — DON'T

When writing functions that need to read a module-level constant for a path,
**don't bind the constant as a default argument**. Python evaluates default
arguments at function-definition time, which freezes the value. Subsequent
`monkeypatch.setattr` on the module constant becomes a no-op. This caused
2 silent CI failures (Sprint 11 P1).

❌ Wrong:
```python
TASK_STATE_FILE = "/app/task_state.json"
def load_state(path: str = TASK_STATE_FILE) -> dict:
    ...
```

✅ Right:
```python
TASK_STATE_FILE = "/app/task_state.json"
def load_state(path: Optional[str] = None) -> dict:
    if path is None:
        path = TASK_STATE_FILE
    ...
```

The second form is `monkeypatch`-friendly AND supports runtime overrides.

### sys.modules stubbing leaks globally — DON'T (selectively)

`sys.modules.setdefault("real_module", MagicMock())` in a test file pollutes
the global module registry for the entire pytest session. Other tests that
need the real `real_module` will get the mock instead. Cost us 104 false
failures in Sprint 11 C1.

✅ Right: only stub truly-external deps (`telebot`, `supabase`, `dotenv`).
Real internal modules (`engine_core`, `telegram_formatters`, etc.) must
stay real.

### Setup-aware thresholds via `setup_profile.get_profile()`

Sprint 11 introduced `setup_profile.SetupProfile` as the source of truth for
thresholds that differ by setup type. When adding a new threshold:

1. Add it to the dataclass (`SetupProfile`).
2. Set per-setup values in the VCP / EP / SWING / ALGO instances.
3. Use `get_profile(setup_type)` in the consuming function.
4. Add tests that pin the VCP-vs-EP ordering (e.g., `EP.X < VCP.X`).

DO NOT hardcode `if setup == "EP": ... else: ...` in the engine — the
profile dataclass is the only acceptable place to encode setup differences.

### Gates must be fail-open

Adaptive risk gates (Cold-regime, per-bucket-heat, etc.) MUST catch data-
fetch failures and fall through to "no block". Trapping the user behind a
stale `yfinance` error or a broken Supabase query is worse than allowing a
potentially-questionable UP step.

```python
try:
    is_cold = check_external_signal()
except Exception:
    is_cold = False   # fail-open
if is_cold:
    block_with_explanation()
```
