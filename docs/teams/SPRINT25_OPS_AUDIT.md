# Sprint 25 — Hyperscaler Ops/Infra Audit (production-closure deep review)

**Scope:** DOC-ONLY. NO code, NO new pipelines/features. Flag-only. Branch `claude/review-system-audit-FBZ2h`, HEAD `1a9213a`, suite **1898 passed** (re-verified, exact CI command, 94.70s, coverage 72.23% ≥ 67%).

Format: `file:line · production risk · severity · value÷risk · tag · proof strategy`.

---

## P1 — CI is NOT production-trustworthy: the entire byte-lock family is commit-state-dependent

### F1 (P1) — every byte-lock test compares working-tree vs index, so all guards pass *vacuously* in CI

`tests/test_sprint19_headline_comparison.py:172`, `tests/test_sprint24_wave2_refactor.py:49,137,146`, `tests/test_sprint24_b1b3_byte_identical.py` (via the Sprint-19 cross-check), `tests/test_sprint23_probe_split.py:270,276`.

- **Re-verified:** every byte-lock subprocess is `git diff -- <file>` (working tree vs **index**) — there is **NO** `git diff HEAD`, `--cached`, or `--staged` variant anywhere in `tests/`. Confirmed by grep.
- On a clean CI checkout `index == working tree` → `git diff` output is **empty** → the `added`/`removed` line lists are empty → every "must be additive only / must be in the authorized B1/B3 set / must be byte-identical" assertion is **vacuously true**. Verified live: working tree clean, `git diff -- analytics_engine.py | wc -l` = `0`, and the four files pass with zero assertions exercised.
- **This is the SAME bug class as `1a9213a`**, only partially fixed. `1a9213a` made *one* assertion (`removed == _B1B3_REMOVED`) commit-state-agnostic by deleting the equality check; it left the whole `+`/`-`-line-scanning family still working-tree-only. The Sprint-19 lock that "kept Sprint-20/21/22 byte-identical-safe" and the Wave-2b `_SPRINT24_AUTHORIZED*` allowlist **provide zero protection in CI** — they only fire on a dirty local tree. Any future PR that *commits* a forbidden analytics_engine.py edit sails through CI green.
- **Production risk:** the money-affecting campaign/Expectancy math the founder personally reconciled against raw Supabase (Sprint-22) is guarded by a lock that is inert in the one place (CI on the committed PR head) that actually gates merges. A regression to that math would not be caught.
- **value÷risk:** very high (the lock's stated purpose is defeated; fix is conceptually `git diff HEAD --` and is itself byte-identical-provable). **tag: closure-fix.**
- **Proof strategy:** add a CI/regression assertion that runs each byte-lock against a synthetic *committed* forbidden edit in a throwaway temp clone and asserts it FAILS (red-on-violation), plus a meta-test asserting no byte-lock uses bare `git diff --` without `HEAD`. Until then the locks must be documented as **local-only, CI-inert**.

### F2 (P1) — `git diff` based tests are also CWD- and git-availability-fragile in CI

`tests/test_sprint19_headline_comparison.py:171`, `:332` (nested `subprocess … pytest --collect-only`), `tests/test_sprint24_wave2_refactor.py:48`, `tests/test_sprint23_probe_split.py:269,294`.

- All pass `cwd=_REPO` (= `os.path.dirname(os.path.dirname(__file__))`) so CWD is pinned — good. **But** they assume (a) `git` on PATH in the runner, (b) a real `.git` dir (true for `actions/checkout@v4` default, fetch-depth 1 still has a working `.git`), and (c) the nested `subprocess.run([sys.executable,"-m","pytest", … ])` self-recursion (Sprint-19 `:332`, Sprint-23 `:294`) re-enters the suite inside a test — a hidden second pytest process not counted in the 10-min budget and not coverage-instrumented.
- **value÷risk:** medium. **tag: polish** (works today; brittle if checkout strategy or runner image changes). **Proof:** assert `shutil.which("git")` and `.git` presence as explicit skips-with-reason rather than silent vacuous pass; bound/replace the self-recursive pytest with an in-process collect.

---

## P1 — CI / production environment parity

### F3 (P1) — CI runs Python **3.11**, production Docker runs Python **3.10-slim**

`.github/workflows/tests.yml:23` (`python-version: "3.11"`) vs `Dockerfile:1` (`FROM python:3.10-slim`).

- Tests are validated on an interpreter the system **never runs in production**. 3.10 vs 3.11 differ in stdlib (`zoneinfo`/`asyncio`/`typing`/match-statement edge cases, exception groups, dict/var-args semantics). A construct that passes CI on 3.11 can break the Orange Pi container on 3.10 — invisible until deploy. This is exactly the "passes CI, fatal in prod" failure mode the Sprint-7 socket incident and Sprint-24 `1a9213a` incident are about, one layer up.
- **Production risk:** silent prod-only breakage of `report_scheduler` / `risk_monitor` / bot; no test signal.
- **value÷risk:** high (one-line workflow alignment; high blast radius). **tag: closure-fix.** **Proof:** pin CI `python-version` to `"3.10"` (match Dockerfile) or matrix `[3.10, 3.11]`; re-run full suite on 3.10 and confirm 1898 pass.

### F4 (P2) — `_ssock` / unraisable asyncio teardown warning is a real latent flaky hazard, masked only because warnings are not promoted

Observed live in the exact CI run: `AttributeError: '_UnixSelectorEventLoop' object has no attribute '_ssock'` → `PytestUnraisableExceptionWarning`, plus `RuntimeWarning: coroutine 'calc_fig' was never awaited` (Streamlit/plotly internal, surfaced via `dashboard.py` import / chart tests).

- Root cause: a Streamlit/plotly internal coroutine + event loop is created during a dashboard/chart test and never closed; the selector loop is GC'd later, raising an unraisable that pytest **attributes nondeterministically to whatever test is running during that GC**. Proven: with `-W error::pytest.PytestUnraisableExceptionWarning` the suite goes **1 failed, 1897 passed**, and the *blamed* test is `test_sprint20_wave2_excluded_disclosure.py::test_on_demand_excluded_no_snap_save` — a test that has nothing to do with asyncio. The blame target is order/timing dependent.
- **Why not P1:** `grep` confirms NO `filterwarnings = error` / `-W error` / `PYTHONWARNINGS` in `pytest.ini`, `setup.cfg`, `pyproject.toml`, `tox.ini`, or the workflow → the warning never fails CI today. The hazard is latent: the day anyone adds `-W error` (a normal hardening step) the suite becomes flaky on a *random innocent test*.
- **value÷risk:** medium. **tag: polish / closure-fix** (hygiene; prevents a future self-inflicted flake). **Proof:** isolate the dashboard/chart import behind a fixture that closes the loop (`asyncio.get_event_loop().close()` / `nest_asyncio` / move chart tests to `slow` tier already excluded from CI default), then `-W error::PytestUnraisableExceptionWarning` must stay green.

### F5 (P2) — bare `pytest` in CI vs documented local `python -m pytest`; `tests/` is not a package yet two tests import `from tests.…`

`.github/workflows/tests.yml:39` runs bare `pytest …`; docs say `pytest -q`; the proof-recursion subprocesses use `python -m pytest`. `tests/__init__.py` does **not exist** (verified), yet `tests/test_sprint21_wave2.py:433` and `tests/test_sprint24_b1b3_byte_identical.py:48` do `from tests.test_real_data_april_regression import …`.

- This works **only** because pytest's rootdir-insertion (rootdir = repo root, the only place `pytest.ini` lives) puts repo root on `sys.path` so `tests` resolves as an implicit namespace package, *and* each file also does `sys.path.insert(0, repo_root)` (55 such inserts across the suite). Bare `pytest` and `python -m pytest` differ precisely in `sys.path[0]` (CWD-injection): the suite currently survives both **by luck of the redundant manual inserts + rootdir**. Remove an insert or change the working directory of the CI step and the cross-`tests`-package imports break — the canonical bare-vs-module hazard the Sprint-24 incident was about.
- **value÷risk:** medium (latent; the redundant inserts mask it now). **tag: polish.** **Proof:** add empty `tests/__init__.py` *or* `pythonpath = .` in `pytest.ini` `[pytest]` so import resolution no longer depends on per-file `sys.path` hacks; assert `python -m pytest` and bare `pytest` collect the identical 1898.

### F6 (P3) — `--cov-fail-under=67` ratchet vs current 72.23%; coverage on 4 modules only

`.github/workflows/tests.yml:45`.

- Live coverage: analytics 99%, adaptive_risk 90%, addon 86%, **engine_core 60%** (workflow comment says 57% — slightly stale). 5.23 pt headroom: a non-trivial untested engine_core change could land without tripping the gate. Telegram bot, secure runner, scheduler, risk_monitor, dashboard are **not coverage-measured at all** — the most production-fragile files (CLAUDE.md "most fragile areas") have no coverage floor.
- **value÷risk:** low–medium (intentional baseline per `docs/COVERAGE_BASELINE.md`; raising is a Sprint-7/8 roadmap item, not a closure blocker). **tag: polish (roadmap, not closure-fix).** **Proof:** none needed for closure; note the gate does not protect the runtime-critical modules.

### F7 (P3) — no `-p no:cacheprovider` in the CI invocation; nondeterministic-order risk is low but uncontrolled

`.github/workflows/tests.yml:39-45` runs `pytest …` with no `-p no:cacheprovider` and no `-p randomly`/fixed seed. The proof subprocesses *do* pass `-p no:cacheprovider` (good, internally), but the top-level CI run leaves `.pytest_cache` active.

- On the ephemeral `actions/checkout` runner there is no pre-existing `.pytest_cache`, so `--lf`/`--ff` ordering effects do not apply in CI — risk is low. The real ordering exposure is F4 (the unraisable's blame target is order-dependent). No plugin randomizes collection order, so ordering is deterministic-by-filename today.
- **value÷risk:** low. **tag: polish.** **Proof:** add `-p no:cacheprovider` to the CI command for parity with every nested invocation and to remove the only stateful pytest input.

---

## Runtime / deploy closure (compose, secure_runner, scheduler)

### F8 (P2) — `telegram_bot_secure_runner.py:48,173-174` `os.chdir` to a hard-coded **host** path inside the container

`WORKDIR = os.getenv('SENTINEL_WORKDIR', '/home/orangepi/sentinel_trading')`; `if os.path.isdir(WORKDIR): os.chdir(WORKDIR)`. Docker `WORKDIR` is `/app` (Dockerfile:2); compose sets no `working_dir`.

- Inside the container `/home/orangepi/sentinel_trading` does not exist, so `isdir` is False and chdir is skipped → process stays at `/app` (correct **by accident**). But: (a) the default is an Orange-Pi **host** path that has no meaning in the container — confusing and a latent footgun; (b) if `SENTINEL_WORKDIR` is ever set in `.env`, or that path is volume-mounted, the bot chdir's away from `/app` and every relative-path read (state, config, sector cache) silently resolves against the wrong dir. All other services depend on CWD=`/app`. The secure runner is the one production-mandated entrypoint (CLAUDE.md hard constraint) and should not contain a host-path chdir.
- **value÷risk:** medium. **tag: closure-fix.** **Proof:** default `SENTINEL_WORKDIR` to `/app` (or drop the chdir entirely — Dockerfile already sets WORKDIR); add a test asserting CWD is unchanged when the env var is unset; confirm secure-runner guard/rate-limit tests stay green (24/24 verified this audit).

### F9 (P3) — `sentinel_config.json` is git-tracked despite `.gitignore:3`; contains live account financials

`git ls-files` lists `sentinel_config.json`; content `{"total_deposited": 7500.0, "risk_pct_input": 0.5, "nav": 7922.18}`. `.gitignore:3` lists it, but gitignore does not untrack already-tracked files (`git check-ignore` returns non-match).

- Not a credential leak (no token/key), but real account NAV/deposit is committed. Worse for **correctness**: NAV/account config is a CLAUDE.md "most fragile area" — a stale committed `nav` overrides the IBKR-synced value on every `git pull` deploy (same class as the Sprint-14 `risk_monitor_state.json` revert incident already documented in `.gitignore:6-12`). This distorts R/exposure/risk math.
- **value÷risk:** medium (financial-accuracy + git-hygiene; the `.gitignore` line proves the intent was already to NOT track it). **tag: closure-fix.** **Proof:** `git rm --cached sentinel_config.json` (keep working copy), confirm `git check-ignore` now matches and a deploy `git pull` no longer reverts NAV; verify account_state.load() fallback path is exercised (test exists: `test_account_state.py`).

### F10 (P3) — scheduler partial-failure: `_mark_ran` is written *before* `_run_weekly/_run_monthly`

`report_scheduler.py:598,599` (`_mark_ran` then `_run_weekly`); same monthly `:606,607`.

- Idempotency itself is **correct**: `_already_ran(state,key,today)` + daily key + `minute >= MINUTE` + 60s loop → exactly once per calendar day, timezone correct (`datetime.now(ISRAEL_TZ)`, `ZoneInfo("Asia/Jerusalem")`, DEC-20260510-001 two-layer TZ). Verified by reading the loop.
- **But** the day is marked done *before* the report runs. If the container crashes / OOMs (`mem_limit: 1200m`) mid-`_run_weekly`, the state file already says `weekly=today` → on restart the report is **silently skipped for that week**. `restart: unless-stopped` brings the container back but the day is consumed. The inner `try/except` + `_notify_error` covers logic errors, not a hard crash between mark and completion. Rollback story (docs/TESTING_AND_DEPLOYMENT.md) is per-service and adequate; this is a missed-report, not a corruption.
- **value÷risk:** low (rare; weekly cadence; would need a crash inside the ~seconds-long render window). **tag: polish (would be an *addition* to fully fix — mark-after-success changes behavior; OUT of DOC-ONLY scope, flagged only).** **Proof (if ever done):** mark-after-success + a crash-injection test asserting the report re-fires next loop the same day.

---

## Things verified OK (closure-positive — no action)

- Compose: `telegram-bot.command: python3 telegram_bot_secure_runner.py` (compose:37) — secure runner correctly wired per CLAUDE.md hard constraint. `risk-monitor`/`reporting-service` `depends_on: telegram-bot`. `restart: always`/`unless-stopped`, `mem_limit: 1200m`, `json-file` logging with `max-size:10m max-file:5` (bounded), per-service healthchecks reading `/app/state/*_last_cycle` heartbeats, `autoheal` sidecar with `autoheal=true` labels. All present and consistent.
- Secrets: `.env` **not tracked** (verified `git ls-files`); `risk_monitor_state.json`/`risk_recommendations.json`/`risk_journal.json` not tracked; secrets via `env_file: .env` + CI `env:` block (placeholder values only). Secure runner `_log` never prints token/admin id (code-verified, lines 7-21,60-83). No PII/secret in log paths.
- Heartbeat path parity: secure_runner / report_scheduler / (risk_monitor) write `/app/state/{name}_last_cycle`; compose healthchecks read the same paths with sane staleness windows (telegram 180s, sentinel 1980s, risk 720s, report 150s). Consistent.
- Scheduler cadence/timezone/idempotency: correct (see F10 — only the mark-ordering is a soft gap, not a cadence bug).
- 10-min CI budget: full instrumented suite 94.70s — ~6× headroom. NOT a risk (F2's hidden nested-pytest recursions add a little, still far inside budget).

---

## P0 / P1 summary

- **P0:** none.
- **P1:** **F1** (byte-lock family is commit-state-dependent → all byte-locks pass vacuously in CI; the lock that protects reconciled money-math is inert exactly where merges are gated — same bug class as `1a9213a`, only partially fixed). **F2** (git-diff tests git/CWD-fragile + hidden self-recursive pytest). **F3** (CI Python 3.11 vs prod Docker 3.10 — validating an interpreter prod never runs).

## Single highest value÷risk ops closure

**F1 — make the byte-lock family commit-state-agnostic (CI parity, prioritized as instructed).** The Sprint-19/24 byte-locks are the stated guardrail over the founder-reconciled, money-affecting campaign/Expectancy math, yet `git diff -- <file>` (working tree vs index) is empty on every clean CI checkout, so the guards never assert anything in the one place that gates merges. `1a9213a` fixed a single symptom of this exact class but left the family intact. Closing it (compare against the committed head, e.g. `git diff HEAD --`, + a red-on-committed-violation regression proof) is conceptually small, itself byte-identical-provable, and is the difference between "the lock works locally" and "the lock works where it matters." Re-verified this sprint: clean tree, empty diff, four byte-lock files passing with zero assertions exercised.
