# Phase Arch-F1 — NAV→target-risk triple-divergent resolution — PREDEFINED SCOPE

**Status:** SCOPE — awaiting founder go-ahead + 2 decisions before execution.
**Origin:** Sprint-25 Arch audit F1 (P1, high value / HIGH risk — NAV is a CLAUDE.md most-fragile area; cross-service). Founder selected as the next governed Phase.
**Authority model:** predefined scope + separate acceptance tests + parity-test-BEFORE-deletion; founder-gated, Mark-gated.

---

## 1. The defect (verified against source)

NAV → target-risk is resolved **three divergent ways**:
- `account_state.load()`/`target_risk_usd()` (`account_state.py:16-61`) — the documented single-source. Reads `sentinel_config.json` `nav`→`total_deposited`→`7500.0`; shape A (`nav_source` broker/deposited, `is_critical = freshness=="critical"`, honest fallback dict); never raises.
- `engine_core.get_nav_with_freshness()` (`engine_core.py:1527+`) — reads the SAME file, **different** fallback (`is_critical=True`, different Hebrew label), **different** shape (`source`/`updated_at` vs `nav_source`/`nav_updated_at`), `ok=False` on fallback.
- `bot_helpers.get_nav_and_risk()` (`bot_helpers.py:94-97`) and `risk_monitor.py:604-607` — **byte-identical** `acc_size = nav_info["nav"] if nav_info["ok"] else float(account_settings.get("total_deposited",7500.0))` then `acc_size*risk_pct/100`, written twice; `report_open_book.py:211` a third near-copy of the multiply.
- The config-file **reader** is duplicated 3× incl. `risk_monitor.py:150-153` with a bare `except:` that **swallows a corrupt-config signal** `account_state` surfaces honestly.

**Production risk:** the bot + risk-monitor resolve NAV via `ec.get_nav_with_freshness()` while the report pipeline uses `account_state.load()` — two fallback/freshness contracts feeding the SAME risk math. A future edit to one fallback silently desyncs Telegram risk sizing, the risk-monitor Sizing-Leak threshold, and the weekly/monthly report target-risk.

## 2. Scope of THIS phase (deliberately narrow — Arch's own recommendation)

**IN (the safe, gradual S24-#2 step):**
1. **Parity test FIRST** (author BEFORE any deletion): `tests/test_phase_archf1_nav_single_source.py` — for present / missing / corrupt / valid-no-`nav` `sentinel_config.json`, assert `bot_helpers.get_account_settings` and the *current* `risk_monitor` local copy resolve **identically**, and that `bot_helpers.get_nav_and_risk()` vs the `risk_monitor.py:604-607` block produce **identical `(acc_size, target_risk)`** for the same inputs. This freezes today's behavior as the oracle.
2. **De-duplicate the reader:** `risk_monitor.py` imports and uses `bot_helpers.get_account_settings` (the shared reader); DELETE its byte-identical local copy **and the bare `except:`**. No other risk_monitor logic changed; `:604-607` math untouched.

**EXPLICITLY OUT (behavior-bearing — documentation only, no code):**
3. Do NOT unify `account_state.load()` vs `engine_core.get_nav_with_freshness()` — genuinely different fallbacks/shape → unifying changes which contract a path sees (money-affecting). Only **document the divergence** at both call boundaries — in `docs/MODULE_MAP.md` / `docs/DATA_CONTRACTS.md` / this teams doc, **NOT** in `engine_core.py`/`account_state.py` (engine_core is byte-locked; account_state edits avoided to keep risk math untouched). `bot_helpers.py`/`risk_monitor.py` are NOT byte-locked.
4. Do NOT touch `engine_core.get_nav_with_freshness`, `account_state.load`, `report_open_book.py:211`, or the `:604-607` risk math.

## 3. The 2 decisions for the founder (before execution)

**Decision A — corrupt-config edge (the crux).** Today `risk_monitor.py:153` bare `except:` swallows a corrupt `sentinel_config.json`; `bot_helpers.get_account_settings` may handle it differently. The parity test (step 1) will reveal whether the resolved `(acc_size, target_risk)` on a corrupt config is **byte-identical** between the two:
- if **identical** → the de-dup is pure byte-preserving polish (no behavior change) — proceed.
- if **divergent** → it is a CLOSURE-FIX: (a) **honest (recommended)** — adopt `bot_helpers`' behavior (stop swallowing; surface the corrupt-config signal, consistent with `account_state`/CLAUDE.md #1); or (b) **strict** — replicate the old swallow exactly so it stays byte-identical (preserves a known-dishonest edge). Founder chooses A-a or A-b; default recommend **A-a (honest)**.

**Decision B — NAV-source unification.** Confirm it stays **OUT** of this phase (document-only), OR explicitly authorize the larger, riskier unification of the two NAV contracts (NOT recommended now). Default: **OUT (document-only)**.

## 4. Hard constraints / proof obligations

- No byte-locked file change: `analytics_engine.py`, `engine_core.py`, `period_data_probe.py`, `telegram_bot_secure_runner.py`, `docker-compose.yml`, migrations, LOCKED `tests/test_real_data_april_regression.py`, ALL `tests/_byte_lock_baselines/*` git-diff EMPTY; no baseline regenerated. No `account_state.py` change (keep the report-pipeline NAV path byte-identical). C1 dev-PIN guard / C2 `split_side_first` / B3 Add-On guard untouched.
- `bot_helpers.py`/`risk_monitor.py` not baseline-locked: minimal, no rewrite. The `:604-607` math + every other risk_monitor path byte-identical.
- Byte-identical for present/valid/missing config (the normal cases); the ONLY possible behavior change is the corrupt-config edge per Decision A.
- No new feature/flag/command/metric/schema. Sprint-22/23/24 + C1 + C2 + B3 + Wave-2A invariants intact.
- Full suite `python -m pytest -q -p no:cacheprovider` ≥ **1981**, 0 failed (new tests only ADD; none weakened). CI-equivalent (`--cov-fail-under=67`, CI env) GREEN **post-commit on the clean tree** (the Sprint-24 lesson).

## 5. Separate acceptance tests (`tests/test_phase_archf1_nav_single_source.py`)

Authored BEFORE deletion: (1) reader parity present/missing/corrupt/valid-no-`nav`; (2) `get_nav_and_risk` vs `risk_monitor:604-607` identical `(acc_size, target_risk)`; (3) post-de-dup: risk_monitor uses the shared reader, no local copy / no bare `except`; (4) corrupt-config behaves per the chosen Decision-A policy; (5) full suite unchanged elsewhere. No existing test weakened.

**Nothing executed until the founder approves this scope + Decision A + Decision B.**
