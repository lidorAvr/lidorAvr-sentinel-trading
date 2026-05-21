# Meeting (UX cleanup wave) — TESTING discipline findings

**Branch:** `claude/review-system-audit-FBZ2h` ·
**Commits:** `3ac93e8` (meeting-fytd), `fdd4e84` (fytd-tooling), `e9872f8` (meeting-ux).
**Method:** read-only diagnose; no test code added; live probes against `telegram_formatters.py`.

## Headline

Wave is GREEN (46/46 in scope; 2564 passed + 1 skipped, 92.4s; coverage 73.20% > gate 67%).
Suite quality is the best in two sprints: `tmp_path`-scoped fixtures, `__file__`-anchored
source reads, sane subprocess env injection, **no `git diff` byte-locks** (so no Sprint-25
P0-1/P0-2 vacuity regression). But six coverage gaps remain — three are claims the test
files themselves make ("blocking reason MUST survive", "byte-identical", "AI-copy mirror
also drops the preamble") that fail on inputs the suite never exercises.

---

## T1 — Disclaimer over-shoot (positive gross → negative residual) untested · P1 · closure-fix

`tests/test_meeting_fytd_pre_db_history.py:95-130` covers `estimate==gap` and partial
disclaimer, never `estimate>gap`. Probed: `gap=+495.67, estimate=600` → `adjusted=-104.33` →
classifier returns `band="Material Gap"` and softened branch renders ✅ next to "פער מהותי"
with a NEGATIVE residual. The most likely founder real-world miscalibration. Fix: classifier
assertion + formatter assertion on the negative-residual line.

## T2 — Gate-clamp compact path with empty `heat_factors` silently drops the ⛔ reason · P1 · closure-fix

`tests/test_meeting_ux_cleanup.py:163` claims "⛔ gate reason MUST survive". Probed: with
`heat_factors=[]` and gate clamped, `fmt_adaptive_risk_block` (`telegram_formatters.py:414-417`)
emits 3 lines (title + headline only) — the WHY is gone. Any upstream `adaptive_risk_engine`
change that clamps without populating `heat_factors` hides the blocking reason from the founder.
Fix: pin compact-path fallback to `risk_raise_gate.reason` when `heat_factors` is empty.

## T3 — Critical-residual AI-copy variant untested · P2 · addition

`test_meeting_ux_cleanup.py:78-94` covers Critical-residual only in Hebrew; AI-copy is tested
only on the softened branch (`:68-74`). The AI Master Context Export consumes
`fmt_broker_reconciliation(..., ai_copy=True)` on every report (`telegram_formatters.py:1086-1094`).
Fix: mirror `test_huge_residual_still_critical_keeps_full_preamble` with `ai_copy=True` and pin
`"Cause unverified"` + `"Manual verification"` + `"Pre-DB history disclaimer applied"`.

## T4 — Non-numeric `pre_db_realized_pnl_estimate` crashes the portfolio chain · P1 · closure-fix

Probed: classifier with `pre_db_realized_pnl_estimate="abc"` raises `ValueError`. All four
production callsites (`telegram_portfolio.py:262/680/732`, `risk_monitor.py:1236`,
`dashboard.py:595/626`, `report_scheduler.py:321/327`) coerce via `float(... or 0)` which
ALSO raises on a non-numeric string. No failsafe — a fat-finger edit to `sentinel_config.json`
crashes /portfolio, the scheduler, and the dashboard. Fix: `TestCorruptConfig` class pinning
either classifier-graceful-fallback OR caller-side try/except-with-warning.

## T5 — Concurrent CLI writes — atomic-rename claim never exercised · P2 · polish

`tests/test_scripts_set_pre_db_pnl_estimate.py:145-151` proves no leftover temp files after
ONE write. `scripts/set_pre_db_pnl_estimate.py:88-106` documents POSIX-atomic rename but no
test fires two concurrent invocations. Fix: `ThreadPoolExecutor` spawning two `_run` calls;
assert both rc==0, final value ∈ {A, B}, no `.sentinel_config_*.tmp` lingers.

## T6 — "Byte-identical" claims are name-only · P2 · polish (Sprint-25 P1-3 echo)

`test_default_zero_keeps_legacy_keys_byte_identical` (`:72-88`) asserts five legacy fields,
but the returned dict is now a STRICT SUPERSET — three new keys always present even on the
default path. A downstream caller doing `set(status.keys()) == EXPECTED` breaks. Same applies
to `TestReconLineNoAdjustmentByteIdentical` (`test_meeting_ux_cleanup.py:97-111`) — substring
presence, not snapshot equality. Fix: rename to `…LegacyFieldsPreserved` OR add explicit
`assert status["pre_db_pnl_estimate"] == 0.0` to make the additive contract binding.

## T7 — CLI default path is bare-CWD-relative — Sprint-25 P1-1 class still latent in PROD code · P2 · addition

`scripts/set_pre_db_pnl_estimate.py:69` falls back to `Path("sentinel_config.json")` when
`SENTINEL_CONFIG_PATH` is unset. Every test sets the env var → CWD-trap invisible. Operator
running `python3 scripts/set_pre_db_pnl_estimate.py 495.67` from `/tmp` on Orange-Pi gets an
"file not found" exit-1 (loud, but only if the CWD has no `sentinel_config.json` — silently
edits the wrong file if it does). Fix: anchor default to `Path(__file__).resolve().parent.parent /
"sentinel_config.json"` and add a `cwd=tmp_path, env without override` test.

---

## Cross-cut convergence

- **MARK** — Mark §3 wording preserved on Critical-residual (T3 = AI-copy parity only).
- **TELEGRAM** — T2 (empty heat_factors) is the most likely founder-facing UX regression.
- **DATA / OPS** — T4 is jointly an OPS deploy-validation gap; T7 crosses with OPS runbook.
- **ENGINE** — `build_risk_raise_gate_ctx` signature pin (`:269-273`) is solid; no engine gap.

## Suite health

- **Collected:** 2565 (full); 46 in scope. **Result:** 2564 passed, 1 skipped, 1 warning, 92.39s.
- **Coverage:** 73.20% (gate 67%) — adaptive 91%, addon 86%, analytics 99%, engine_core 60%.
- **No `git diff` byte-locks added** ⇒ Sprint-25 P0-1/P0-2 vacuity class NOT reintroduced.
- **Isolation:** all three files use `tmp_path` (CLI) or `__file__`-anchored ROOT (source reads);
  CLI subprocess uses `os.environ.copy()` + per-call `SENTINEL_CONFIG_PATH` override → xdist-safe.

## Out-of-scope but flagged

- **F1** — Sprint-25 P2-1 still open: new caller wiring at `telegram_portfolio.py:262/680/732`,
  `report_scheduler.py:321/327`, `risk_monitor.py:1236`, `dashboard.py:595/626` is NOT covered
  by the 4-module `--cov-fail-under=67` gate.
- **F2** — Surface-wiring tests (`test_meeting_fytd_pre_db_history.py:253-267`) are bare-substring
  greps. A future caller reading the field for the WRONG purpose still passes the test.
- **F3** — `requirements-dev.txt` unpinned (Sprint-25 P3-2 still open).

## Sign-off

GREEN to merge. T1 / T2 / T4 are P1 — recommend a one-page follow-up wave this sprint
before the founder hits the over-disclaim, empty-factors, or corrupt-config path. T3 / T5 /
T6 / T7 ride the next housekeeping wave. No findings block production.

— TESTING discipline, meeting (UX cleanup wave), `claude/review-system-audit-FBZ2h`.
