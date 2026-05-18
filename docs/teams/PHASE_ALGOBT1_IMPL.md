# Phase ALGO-BT-1 — IMPL / יישום (ALGO backtest baseline: ingest + statistics + read-only surface)

**Status:** LANDED — parent-verified, full CI-equivalent post-commit on the
CLEAN tree 0-failed, byte-locked + LOCKED April + report KPIs byte-identical,
real strategy data git-ignored (verified post-commit). Scope:
`docs/teams/PHASE_ALGOBT1_SCOPE.md` (governs). Code HEAD `22d459b` on
`claude/review-system-audit-FBZ2h` (scope `c8bbbed`, baseline `0672b0c`
post-REPORT-1). No live financial values / no proprietary strategy data in any
committed file.

## What landed
- **`algo_backtest_store.py`** (new, root, not byte-locked) — pure read-only,
  no `engine_core`/`analytics_engine`/Supabase/network import:
  - `load_algo_backtests(base_dir="data/algo_backtests")` — deterministic
    UTF-8 walk, exact 22-col TrendSpider Strategy-Tester schema,
    `Closed?==yes` filter, numeric coercion, stable strategy id; malformed /
    wrong-schema rows/files skipped with an honest collected note, NEVER
    raises; missing/empty dir ⇒ honest empty marker. Idempotent: pure
    function of the files present (no DB, no accumulation, no state).
  - `compute_algo_backtest_stats` — per strategy: n, win-rate %, avg/median/
    sum Return %, profit-factor (+`∞`/0.0 label), expectancy %, max
    single-trade drawdown %, avg/max length (candles), exit-reason mix
    (take_profit / stop_loss / time-stop / signal), date span, longest
    win/loss streak. Every block BACKTEST + ALGO observe-only labelled. No
    R/NAV/account math.
  - `format_algo_backtest_summary` — pure Hebrew RTL text, labelled, honest
    empty-state.
- **`dashboard.py`** — ADDITIVE only: one import + one marker-delimited
  read-only panel "📊 ALGO — בסיס בקטסט (פיקוח בלבד)" appended at the end of
  the Strategy-Forensics tab. Alters/reorders/recomputes NO existing section
  or number; reads NO Supabase / NO live-ALGO; degrades to the honest
  empty-state; never raises. Observe-only: zero alerts, zero directives —
  display-only BACKTEST data explicitly marked "לא P&L חשבון, לא נתון חי, לא
  הבטחה קדימה".
- **Strategy-IP protection (W2 doctrine).** `.gitignore` blocks
  `data/algo_backtests/*` with `!.gitkeep`/`!README.md` negations. Verified
  POST-COMMIT: a real CSV dropped into `data/algo_backtests/<SYM>/` is
  git-ignored (`git status` clean, `git check-ignore` matched) — the
  founder's strategy IP can never be committed to the pushed repo. Only the
  scaffold + a SYNTHETIC test fixture are tracked.
- **`tests/test_phase_algobt1.py`** (24) + synthetic fixture
  `tests/_fixtures/algo_backtests/` (Hebrew-named parent + ASCII; IST/IDT;
  Closed?=no; malformed; wrong-schema).

## Proof obligations — verified (parent, independent)
- Full suite (CI env, parent's own run): **2229 passed / 0 failed**
  (2205 baseline + 24 new ADD-only).
- Exact CI command POST-COMMIT on the **clean tree**: `2229 passed`,
  **coverage 73.04% ≥ 67%**, 0 failed.
- Protected-set git-diff EMPTY: `engine_core.py`, `analytics_engine.py`,
  `period_data_probe.py`, LOCKED `tests/test_real_data_april_regression.py`,
  all `tests/_byte_lock_baselines/*`, `docker-compose.yml`,
  `telegram_bot_secure_runner.py`, migrations, `templates/*` — confirmed.
- `git diff --name-only` ⇒ only `.gitignore` + `dashboard.py`; new files only
  the store, scaffold, synthetic fixture, test. No existing test
  deleted/weakened. No migration, no Supabase mutation, no new message TYPE,
  no ALGO directive/alert.
- IP-protection verified post-commit (real CSV git-ignored, scaffold tracked).
- `algo_backtest_store.py` imports no engine/analytics/Supabase/network ⇒
  observe-only, no live coupling.

## Deploy (one command) + the host one-time step
Additive read-only feature; production wiring unchanged (`docker-compose.yml`
byte-identical). After pull-and-recreate, perform the **one-time host step**:
place the real TrendSpider exports into the git-ignored
`data/algo_backtests/<SYMBOL>/<strategy>.csv` (they will NOT be committed; the
dashboard panel computes stats on load). Re-ingest is idempotent — replacing a
file replaces only that strategy's stats.

## Phase-2 hand-off (separate governed Phase)
Live-vs-backtest **divergence detection** + **observational** ALGO alerts
(observe-only, reuse existing surfaces, no new message TYPE). The pure
`format_algo_backtest_summary` is already provided for reuse on a Telegram/
digest surface without rework. Phase-1 introduces ZERO alerts by design.
