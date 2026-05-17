# Phase NAV-Unify (Arch-F1 Decision B) — IMPLEMENTATION RECORD

**Status:** EXECUTED (tree left dirty; parent does the governed
consolidation/commit + the post-commit clean-tree CI-equivalent check —
the Sprint-24 lesson). **No git commit / no push.**
**Branch:** `claude/review-system-audit-FBZ2h` (clean at `40499cc` pre-edit).
**Authority:** founder-approved scope `docs/teams/PHASE_NAVUNIFY_SCOPE.md`
**Option β**, **canonical semantics = `account_state`'s** (honest
explicit-0 D1; strict-`<` boundary D2; unknown-not-critical D3;
missing/corrupt-not-critical D4). Governed engine_core SHA-baseline ritual
(C2 / Engine-P2/P3 precedent). Mark Sprint-25 rulings.
**Classification:** CLOSURE-FIX (founder-decision-required) — unifies the
NAV value + freshness classification so the report pipeline and the
bot/risk-monitor reader can never desync (the real money-risk). No new
feature/flag/command/metric/schema (Mark Ruling 2).

---

## 1. What was done (Option β, parity-test-FIRST)

### Step 1 — parity oracle authored FIRST (before any refactor)
`tests/test_phase_navunify.py` (NEW, 31 tests) authored & run against the
**CURRENT (pre-refactor) code** to freeze today's two outputs as the
oracle. Pre-refactor run: **21 passed, 10 failed** — the 21 byte-identical
parity assertions (account_state.load() on all 8 config states; engine
reader on broker-fresh/stale/critical normal paths; bot_helpers/
risk_monitor normal-path sizing; report-pipeline consumer; LOCKED April
fixture-path isolation) PASSED on untouched code; the 10
`D1–D4`/structural tests failed *by design* — the test-first proof that
they actually assert the authorized deltas + the Option-β core extraction.

### Step 2 — the shared pure core (`account_state._resolve_nav_core`)
`account_state.py` — added `_classify_age(age_hours)` (pure canonical
age→freshness, strict-`<`) and `_resolve_nav_core(_paths=None) -> dict`
returning the CANONICAL classification ONLY (no labels/shape):
`nav, total_deposited, risk_pct_input, nav_updated_at, age_hours,
freshness, is_stale, is_critical, ok, source_kind`. Implements
account_state's exact semantics: **D1** `data.get("nav",
data.get("total_deposited", 7500.0))` (explicit `0` kept — NOT an
`or`-chain); **D2** strict `_classify_age` (`<24` fresh / `<48` stale);
**D3** no/bad timestamp → `freshness="unknown"`, `is_stale=True`,
`is_critical=False`; **D4** missing/corrupt/non-dict → `ok=False`,
`nav=7500`, `is_critical=False`. account_state stays a clean stdlib-only
leaf (`os/json/datetime/typing`).

### Step 3 — `account_state.load()` = thin shape-A adapter
Control flow mirrors the ORIGINAL `load()` EXACTLY (same `_find_config`
→ open/json/non-dict guards → `_fallback(reason)` wording; the same
single `_freshness()` call producing `(age_hours, freshness,
freshness_label)` so the dict's `age_hours` and the label's embedded
`{age_h}` share ONE `datetime.now()` — no double-now drift). `_freshness`
now delegates only the CLASSIFICATION to the shared `_classify_age`
(byte-identical thresholds); all label strings unchanged. account_state's
observable output does **not change at all** (it IS the canonical).

### Step 4 — `engine_core.get_nav_with_freshness()` = thin shape-B adapter
`engine_core.py` — added `import account_state` (acyclic: account_state
is a stdlib-only leaf, does NOT import engine_core). The function now
calls `account_state._resolve_nav_core(_paths=_CONFIG_PATHS)` and builds
shape B from the canonical core, keeping its OWN caller-presentation (D5,
verbatim): the `$`-amount Hebrew label strings, the
`ibkr_sync`/`manual`/`fallback` `source` mapping, and `updated_at` as a
parsed `datetime`. The `_CONFIG_PATHS` is passed THROUGH (the engine's
own constant — the knob existing callers/tests patch; byte-identical
list in production) so the value is still single-sourced via the core.

---

## 2. file:line — before / after

### `account_state.py`
- **Before:** `load()` (`:16-56`) read config inline; `_freshness`
  (`:73-86`) had its own `if age_h < _STALE_HOURS … elif … < _CRITICAL`.
- **After:** `_classify_age` + `_resolve_nav_core` ADDED (the shared
  canonical core); `load()` is a thin shape-A adapter (control flow
  byte-identical to the original); `_freshness` delegates classification
  to `_classify_age` (thresholds identical), label strings verbatim;
  `_fallback`/`_find_config`/`target_risk_usd` byte-unchanged.

### `engine_core.py`
- **Before** (`:1529-1593`): `get_nav_with_freshness` read config inline;
  `nav = float(cfg.get("nav") or cfg.get("total_deposited") or 7500.0)`;
  `is_stale = age > NAV_STALE_HOURS`; no-ts/bad-ts → `is_critical=True`;
  fallback → `is_critical=True`.
- **After**: top-of-file `import account_state` (acyclic) ADDED;
  `get_nav_with_freshness` is a thin shape-B adapter over
  `account_state._resolve_nav_core(_paths=_CONFIG_PATHS)`. Shape-B keys,
  `$`-labels, `source` mapping (`ibkr_sync` if a parseable timestamp;
  `manual` if no/bad timestamp; `fallback` if `not ok`), and
  `updated_at = datetime.fromisoformat(...)` PRESERVED. `nav`/
  `age_hours`/`is_stale`/`is_critical`/`ok` now come from the canonical
  core.

### `tests/_byte_lock_baselines/engine_core.py.baseline`
Regenerated as a verbatim copy (governed ritual — §4).

---

## 3. The ENUMERATED D1–D4 authorized deltas (PRE → POST)

Direct old-vs-new comparison (HEAD `get_nav_with_freshness` vs the new
shape-B adapter), confirmed programmatically:

| Edge | Field | PRE (engine) | POST (canonical = account_state) |
|---|---|---|---|
| D1 `nav: 0` | `nav` | **8000.0** (`or`-chain fell through to total_deposited) | **0.0** (explicit-0 kept) |
| D2 exactly **24.0h** | freshness/`is_stale` | fresh (`age>24` False) | **stale** (strict-`<`) |
| D2 exactly **48.0h** | freshness/`is_critical` | stale (`age>48` False) | **critical** (strict-`<`) |
| D3 no `nav_updated_at` | `is_critical` | **True** | **False** (`is_stale` stays True, `source` stays `manual`) |
| D3 bad/unparseable ts | `is_critical` | **True** | **False** (D3-class; `is_stale` True, `source` `manual`) |
| D4 missing/corrupt | `is_critical` | **True** | **False** (`nav=7500`, `ok=False`, `source=fallback` — all unchanged) |

**No other field changes anywhere.** D1 propagates to
`bot_helpers.get_nav_and_risk` & `risk_monitor:606-609`: with `nav:0`
`acc_size` is now the canonical `0.0` (was `8000.0`) — pinned by
`TestBotHelpersAndRiskMonitorSizing::test_D1_*`.

## 4. Byte-identity proofs

- **`account_state.load()` byte-identical on ALL paths:** programmatic
  full-dict comparison of HEAD `account_state.load` vs the new adapter
  over broker_fresh / stale / critical / no_timestamp / nav_zero /
  valid_no_nav / bad_timestamp / missing / corrupt → **all
  BYTE-IDENTICAL** (incl. exact `age_hours` — the single-`_freshness()`
  structure was preserved). It is the canonical; zero observable change.
  Pinned: `TestAccountStateByteIdenticalAllPaths` (+ the UNMODIFIED,
  still-GREEN `tests/test_account_state.py`).
- **Engine reader byte-identical on the normal path:** programmatic
  comparison of HEAD vs new adapter on broker_fresh/stale/critical/
  valid_no_nav → **all BYTE-IDENTICAL** (shape B + `$`-labels +
  `source=ibkr_sync` + `updated_at` datetime + nav/age/flags). Pinned:
  `TestEngineReaderNormalPathByteIdentical`,
  `TestBotHelpersAndRiskMonitorSizing::test_*_normal_path_byte_identical`,
  and the UNMODIFIED existing `tests/test_nav_and_intent.py`
  (`ec._CONFIG_PATHS` honored — pass-through — so those tests pass
  UNCHANGED).
- **D1–D4 deltas:** `TestEngineReaderD1toD4CanonicalDeltas` +
  `TestBotHelpersAndRiskMonitorSizing::test_D1_*` assert each delta to
  the founder-approved canonical value (D2 razor-edge via
  `_classify_age(24.0)=="stale"` / `_classify_age(48.0)=="critical"`).
- **LOCKED April + Sprint-22 byte-identical:** they pass a fixture
  `_ACCT` dict straight into the analytics engine — never call
  `account_state.load()` nor `get_nav_with_freshness`. Byte-identical by
  construction; pinned by `TestLockedAprilAndSprint22FixturePathUntouched`
  and the still-GREEN `tests/test_real_data_april_regression.py`
  (0-diff) + 22 Sprint-22 tests.

## 5. Governed engine_core byte-lock ritual (evidence)

`engine_core.py` is guarded by the hard SHA256
`bl.assert_byte_identical("engine_core.py")`. The legitimate Mark-gated
edit lands together with a regenerated baseline that is a verbatim copy:

```
$ cp engine_core.py tests/_byte_lock_baselines/engine_core.py.baseline
$ cmp engine_core.py tests/_byte_lock_baselines/engine_core.py.baseline   # exit 0
$ sha256sum engine_core.py tests/_byte_lock_baselines/engine_core.py.baseline
d9547622f254d3f31793f14440028bc144a8d8440dec44a749b3f7f9f0b2b1d6  engine_core.py
d9547622f254d3f31793f14440028bc144a8d8440dec44a749b3f7f9f0b2b1d6  tests/_byte_lock_baselines/engine_core.py.baseline
```

Identical SHA256 ⇒ `assert_byte_identical("engine_core.py")` GREEN. **No
other baseline regenerated/touched** — `analytics_engine.py.baseline`,
`period_data_probe.py.baseline`,
`test_real_data_april_regression.py.baseline` git-diff EMPTY. The
Sprint-25 redteam (RED-on-unauthorized-edit, sandboxed), the
`analytics_engine` allowlist (`baseline_line_delta` EMPTY → GREEN,
UNMODIFIED), the Sprint-24 Wave-2 paired proof + the F4 self-reference
hardening — all GREEN, UNMODIFIED. `account_state.py` is NOT byte-locked.
No import cycle (account_state stdlib-only leaf).

## 6. ⟨MARK⟩ gate slots

- ⟨MARK Ruling 1.1 — money-math correct vs contract⟩: NAV value +
  freshness now single-sourced (canonical = account_state); D1 stops the
  bot/risk-monitor silently substituting total_deposited for an explicit
  `nav:0`. LOCKED April + DEC-019 unchanged (fixture path). _____
- ⟨MARK Ruling 3.3 — LOCKED April byte-identical⟩: 8/+$180.49/WR.375/
  PF2.6262/excl2; `test_real_data_april_regression.py` + baseline 0-diff,
  GREEN. _____
- ⟨MARK Ruling 3.4 — Sprint-19/24 lock + paired proof intact⟩: analytics
  0-diff; redteam + Sprint-24 Wave-2 + F4 hardening GREEN, UNMODIFIED;
  only `engine_core.py.baseline` regenerated. _____
- ⟨MARK Ruling 3.5 — no R/NAV/exposure/campaign math change without
  proof⟩: NAV change confined to the enumerated D1–D4 edges; normal path
  byte-identical; named proof `tests/test_phase_navunify.py`. _____
- ⟨MARK Ruling 4 — byte-identical / authorized-edge split⟩: account_state
  byte-identical on ALL paths; engine/bot/risk-monitor byte-identical on
  the normal path; behavior change ONLY on D1–D4, each pinned to the
  founder-approved canonical. _____
- ⟨MARK Ruling 5.A — suite ≥ floor, 0 failed, no test weakened⟩:
  CI-equivalent + CI env → **2039 passed, 0 failed** (≥ 2008 floor; only
  ADDs — the 31-test parity suite; no existing test modified/weakened). _____
- ⟨MARK Ruling 5.B — CI-equivalent green⟩: exact CI command + CI env →
  **2039 passed, 0 failed**, coverage **72.02% ≥ 67%**. _____
- ⟨MARK Ruling 5.D.8/9 — no addition; behavior change only by gate⟩:
  CLOSURE-FIX, founder-approved Option β + canonical=account_state; no
  new feature/flag/command/metric/schema. _____
- ⟨MARK governed engine_core baseline regeneration⟩: ONLY
  `engine_core.py.baseline` regenerated as a verbatim copy (SHA
  `d9547622…`); all other baselines 0-diff. _____

## 7. Explicit confirmations

- Modified (exactly): `account_state.py`, `engine_core.py`,
  `tests/_byte_lock_baselines/engine_core.py.baseline`; NEW:
  `tests/test_phase_navunify.py`, `docs/teams/PHASE_NAVUNIFY_IMPL.md`.
- 0-diff (git): `analytics_engine.py`, `period_data_probe.py`,
  `adaptive_risk_engine.py`, `risk_monitor.py`, `bot_helpers.py`,
  `report_open_book.py`, `docker-compose.yml`, `telegram_bot.py`,
  `telegram_callbacks.py`, `telegram_bot_secure_runner.py`, `migrations/`,
  `tests/test_real_data_april_regression.py`,
  `analytics_engine.py.baseline`, `period_data_probe.py.baseline`,
  `test_real_data_april_regression.py.baseline`.
- account_state.load() byte-identical on ALL config states (it IS the
  canonical — zero observable change). Engine/bot/risk-monitor reader
  byte-identical on the normal broker-fresh/stale/critical path. Behavior
  change confined to the enumerated D1–D4 edges, each = the
  founder-approved canonical (account_state) value.
- LOCKED April **8/+$180.49/WR.375/PF2.6262/excl2** + Sprint-22
  byte-identical (fixture `_ACCT` path — never calls a NAV reader).
- C1 dev-PIN / C2 `split_side_first` / B3 `_coerce_numeric` / Arch-F1
  reader / Sprint-22/23/24 / Wave-2A mechanism / WS-C / `-1`-sentinel
  intact & untouched. No import cycle (account_state stdlib leaf;
  engine_core→account_state is the acyclic direction).
- No existing test deleted or weakened (Mark 6.1) — only the 31 new
  parity tests ADDed; existing `test_nav_and_intent.py` /
  `test_account_state.py` pass UNMODIFIED.
- Full suite `python -m pytest -q -p no:cacheprovider`: **2034 passed,
  5 failed** — the 5 are the env-dependent
  `test_sprint25_c1_devpin_enforcement.py::TestC1ValidSessionUnchanged`
  isolation tests, 100% PRE-EXISTING on the clean baseline (documented in
  PHASE_ARCHF1_IMPL §7 / PHASE_ENGINE_P2P3 / PHASE_C2), unrelated to
  NAV-Unify; GREEN under the binding CI-equivalent command + CI env.
- CI-equivalent (`--tb=short -q --cov=engine_core
  --cov=adaptive_risk_engine --cov=analytics_engine
  --cov=addon_risk_engine --cov-report=term --cov-fail-under=67`, CI env
  `TELEGRAM_BOT_TOKEN=ci-test-token TELEGRAM_ADMIN_ID=12345
  SUPABASE_URL=https://ci-test.supabase.co SUPABASE_KEY=ci-test-key
  DEV_PIN=0000`): **2039 passed, 0 failed**, coverage **72.02% ≥ 67%**.
- NOT committed/pushed; tree left dirty for the parent's governed
  consolidation + the post-commit clean-tree CI-equivalent re-verification
  (the Sprint-24 lesson).
