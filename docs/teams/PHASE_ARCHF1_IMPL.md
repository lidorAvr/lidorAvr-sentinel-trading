# Phase Arch-F1 — Implementation record (NAV→target-risk reader de-dup)

**Date:** 2026-05-17 · **Branch:** `claude/review-system-audit-FBZ2h` (from `ecc6cce`)
**Scope authority:** `docs/teams/PHASE_ARCHF1_SCOPE.md` (founder-approved).
**Founder decisions:** Decision A = **Honest** · Decision B = **OUT (document-only)**.
**Status:** executed, tree left dirty for the parent's governed consolidation +
post-commit clean-tree CI-equivalent verification. **No git commit / no push.**

---

## 1. What was done (exactly the scope, parity-test-FIRST)

### Step 1 — parity test authored FIRST, before any deletion
`tests/test_phase_archf1_nav_single_source.py` (new, 11 tests). Authored and
run against the CURRENT (pre-de-dup) code to freeze today's behavior as the
oracle. Pre-de-dup result: **9 passed, 2 failed** — the 9 parity tests
(present / missing / **corrupt** / valid-no-`nav` reader parity +
`(acc_size, target_risk)` parity) passed on the untouched code; the 2
`TestSharedReaderDedup` tests failed *by design* (the de-dup had not happened
yet — the test-first proof that they actually assert the de-dup).

### Step 2 — de-duplicate the reader (the only production change)
`risk_monitor.py`: deleted its byte-identical local `get_account_settings`
copy **and the bare `except:`**; added `from bot_helpers import
get_account_settings` (+ a short explanatory comment). No other
`risk_monitor` logic touched.

### Decision B — document-only divergence note (no code)
Added to `docs/MODULE_MAP.md` (`account_state.py` section) and
`docs/DATA_CONTRACTS.md` (NAV/account-size contract) — a flagged,
DEFERRED, founder-gated note that the bot/risk-monitor NAV contract
(`engine_core.get_nav_with_freshness`) diverges in fallback/shape from the
report-pipeline contract (`account_state.load`), feeding the SAME risk
math, and that unifying them is OUT of this phase. NO `engine_core.py` /
`account_state.py` change.

---

## 2. file:line — before / after

### `risk_monitor.py` — local reader DELETED (the de-dup)

**Before** (`risk_monitor.py:150-153`, immediately after `get_ibkr_nav`):
```python
def get_account_settings():
    try:
        with open("sentinel_config.json", "r") as f: return json.load(f)
    except: return {"total_deposited": 7500.0, "risk_pct_input": 0.5}
```

**After** — that block is gone; instead, after the imports
(`risk_monitor.py:10-16`):
```python
import state_io
# Phase Arch-F1 (Sprint-25 F1): single shared sentinel_config.json reader.
# risk_monitor previously kept a byte-identical local get_account_settings
# copy with a bare `except:`. De-duplicated onto bot_helpers' reader
# (`except Exception:`); corrupt-config behavior is byte-identical (a
# JSONDecodeError is an Exception, caught by both) — pure parity-preserving
# polish per Decision A = Honest. See docs/teams/PHASE_ARCHF1_IMPL.md.
from bot_helpers import get_account_settings
```

The shared reader (UNCHANGED — `bot_helpers.py:80-85`):
```python
def get_account_settings() -> dict:
    try:
        with open("sentinel_config.json", "r") as f:
            return json.load(f)
    except Exception:
        return {"total_deposited": 7500.0, "risk_pct_input": 0.5}
```

### `risk_monitor.py` acc_size/target-risk math — UNTOUCHED
Was `:604-607`, now `:607-609` (shifted +3 only by the import/comment net
line delta). Byte-identical content; `git diff` shows only the import block
add + the local-reader delete — nothing else.

`risk_monitor.get_ibkr_nav`'s own trailing `except: return None` (a
DIFFERENT, non-config-reader function) was **NOT** touched — scope only
authorized deleting the *config-reader* copy's bare `except:`.

### Docs (Decision B = OUT, document-only)
- `docs/MODULE_MAP.md` — divergence note appended to the `account_state.py`
  "Rules:" block (after the "Never raise from `load()`" rule).
- `docs/DATA_CONTRACTS.md` — divergence flag appended to the NAV/account-size
  contract "Rules:" list (after rule 4).

---

## 3. The parity-test oracle

| Oracle | Definition |
|---|---|
| Reader parity | For present / missing / corrupt-JSON / valid-no-`nav` `sentinel_config.json`, `bot_helpers.get_account_settings()` and `risk_monitor.get_account_settings` resolve to the **identical dict**. |
| Corrupt-config evidence (Decision A) | Both readers' result on a corrupt config is captured and asserted identical (`== {"total_deposited": 7500.0, "risk_pct_input": 0.5}`). |
| (acc_size, target_risk) parity | `bot_helpers.get_nav_and_risk(settings)` (with `bh.ec.get_nav_with_freshness` patched) vs the `risk_monitor.py:607-609` block replicated verbatim, over 5 nav_info/settings cases incl. `ok`/`!ok`/missing-keys → identical `(acc_size, target_risk)`. The math is NOT modified by this phase. |
| Post-de-dup structure | `rm.get_account_settings is bh.get_account_settings`; the reader's `__module__ == "bot_helpers"`; its source uses `except Exception:`, contains no bare `except:`. |

---

## 4. Decision A — corrupt-config edge: byte-identical polish (NOT a closure-fix)

**Result: the corrupt-config edge is BYTE-IDENTICAL. The de-dup is pure
byte-preserving polish on this edge — it is NOT a Decision-A-Honest
closure-fix (no behavior delta exists to fix).**

Parity evidence: the pre-de-dup parity run showed
`test_corrupt_json_identical_fallback_DECISION_A_EVIDENCE` **PASSED on the
CURRENT code** — i.e. the old `risk_monitor` local bare-`except:` copy and
`bot_helpers`' `except Exception:` reader BOTH return the SAME fallback
dict `{"total_deposited": 7500.0, "risk_pct_input": 0.5}` on a corrupt
`sentinel_config.json`. Reason: a corrupt JSON file makes `json.load`
raise `json.JSONDecodeError` (a `ValueError`, hence an `Exception`), which
**both** `except:` and `except Exception:` catch. The ONLY behavioral
difference between bare-`except:` and `except Exception:` is for
non-`Exception` `BaseException` (e.g. `KeyboardInterrupt` / `SystemExit`),
which a corrupt JSON file never raises. So the resolved
`(acc_size, target_risk)` on a corrupt config is unchanged → Decision A =
Honest here = byte-preserving polish (we still remove the dishonest-pattern
bare `except:`, consistent with `account_state` / CLAUDE.md #1, but with NO
observable behavior change).

**Which test pins it:**
`tests/test_phase_archf1_nav_single_source.py::TestReaderParity::test_corrupt_json_identical_fallback_DECISION_A_EVIDENCE`
asserts both readers' corrupt-config result are identical AND equal the
exact fallback literal — pinning the corrupt-config behavior for any future
change.

Present / valid / missing / valid-without-`nav` configs: **byte-identical**
(the other `TestReaderParity` tests pin each).

---

## 5. Decision B — divergence note location (document-only, no code)

- `docs/MODULE_MAP.md` — `account_state.py` section, blockquote after the
  "Never raise from `load()`" rule.
- `docs/DATA_CONTRACTS.md` — "NAV / account-size contract" Rules list,
  blockquote after rule 4.
- This impl doc, §1 + §6.

No `engine_core.py` (byte-locked) / `account_state.py` change — confirmed
git-diff EMPTY.

---

## 6. ⟨MARK⟩ slots

- **⟨MARK: tag⟩** — `polish` (pure byte-preserving, provably-identical
  internal dedupe; Ruling 2 ADMISSIBLE "provably-identical internal
  dedupe"). NOT a CLOSURE-FIX (no observable behavior delta — §4 proof).
  NOT an ADDITION (no new feature/flag/command/metric/schema).
- **⟨MARK: severity / value÷risk⟩** — closes P1/F1's safe S24-#2 first step;
  high value (removes the 3-way reader drift + a dishonest bare-`except:`
  pattern) / risk neutralized to byte-preserving by the parity-first proof.
- **⟨MARK: named proof⟩** — `tests/test_phase_archf1_nav_single_source.py`
  (reader parity present/missing/**corrupt**/valid-no-`nav`;
  `get_nav_and_risk` vs `risk_monitor:607-609` `(acc_size,target_risk)`
  identity; post-de-dup shared-reader structure). "No test failed" is NOT
  the proof — this named parity oracle is.
- **⟨MARK: behavior-change gate⟩** — none. The only edge that *could* change
  (corrupt-config) is proven byte-identical (§4); no per-item founder
  go-ahead consumed because there is no behavior change. Decision B kept OUT.
- **⟨MARK: do-no-harm⟩** — see §7: clean-baseline (`ecc6cce`, all Arch-F1
  changes removed) full suite already has the SAME 5 pre-existing
  `test_sprint25_c1_devpin_enforcement.py` isolation failures; Arch-F1 adds
  ZERO new failures (+11 passing tests).

---

## 7. Confirmations / proof obligations

**Byte-locked files — git-diff EMPTY (verified):** `analytics_engine.py`,
`engine_core.py`, `period_data_probe.py`, `telegram_bot_secure_runner.py`,
`docker-compose.yml`, `tests/test_real_data_april_regression.py`, ALL
`tests/_byte_lock_baselines/*` + `tests/_byte_lock_baseline.py` (no baseline
regenerated), migrations (none changed). `account_state.py` UNCHANGED.
`telegram_bot.py` UNCHANGED. C1 dev-PIN guard / C2 `split_side_first` / B3
Add-On guard / Wave-2A mechanism: untouched & byte-identical (only
`risk_monitor.py` modified; the C1 anchor `telegram_bot.py:241-247` is in an
unchanged file).

**`git status` (dirty, intentional — not committed):**
- `M risk_monitor.py` (the de-dup: +7 / −5; `git diff` = import block add +
  local-reader delete only)
- `M docs/MODULE_MAP.md`, `M docs/DATA_CONTRACTS.md` (Decision-B note)
- `?? tests/test_phase_archf1_nav_single_source.py` (new parity test)
- `?? docs/teams/PHASE_ARCHF1_IMPL.md` (this doc)

**No addition:** no new feature / flag / command / alert / endpoint /
metric / schema / config key. Sprint-22/23/24 + C1 + C2 + B3 + Wave-2A
invariants intact; WS-C / `-1`-sentinel / ALGO "תקן entry/stop" string
untouched.

**Full suite (`python -m pytest -q -p no:cacheprovider`, CI env set):**
**1992 passed, 0 failed** (1981 baseline collected + 11 new Arch-F1 tests).

**CI-equivalent (`python -m pytest --tb=short -q --cov=engine_core
--cov=adaptive_risk_engine --cov=analytics_engine --cov=addon_risk_engine
--cov-report=term --cov-fail-under=67`, CI env
`TELEGRAM_BOT_TOKEN=ci-test-token TELEGRAM_ADMIN_ID=12345
SUPABASE_URL=https://ci-test.supabase.co SUPABASE_KEY=ci-test-key
DEV_PIN=0000`):** **1992 passed, 0 failed; coverage 71.84% ≥ 67%
(`Required test coverage of 67% reached`).**

**Do-no-harm / pre-existing-failure note (IMPORTANT for the parent's
adjudication):** without the CI env vars, `pytest -q` shows
**5 failed** in `tests/test_sprint25_c1_devpin_enforcement.py`
(`TestC1ValidSessionUnchanged`). Verified these are **100% PRE-EXISTING
on the clean baseline `ecc6cce`** with ALL Arch-F1 changes removed
(`risk_monitor.py` stashed + the new test file moved aside): clean baseline
full suite = **1976 passed / 5 failed**; with Arch-F1 = **1987 passed / 5
failed** (the SAME 5) → Arch-F1 introduces ZERO new failures and adds 11
passing tests (1976 → 1987 = +11). Those 5 require the CI env (`DEV_PIN`
etc.) to pass; under the binding CI-equivalent command + CI env the suite is
fully **GREEN (1992 / 0)**. The parent's post-commit clean-tree
CI-equivalent verification (with CI env, per Mark §5.B) is the authoritative
gate and should be GREEN. The spec's "≥1981, 0 failed (plain `-q`)" does not
hold on the bare baseline itself (pre-existing env-dependent C1 isolation
fragility) — flagged here, NOT introduced or weakened by Arch-F1.

**No test deleted or weakened** (Mark 6.1) — only the 11 new Arch-F1 tests
ADDed.
