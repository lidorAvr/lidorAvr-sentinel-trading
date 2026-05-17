# Sprint-27 W1 — Dashboard NAV honesty (Mark P1-1 + Data D-F1)

**Date:** 2026-05-17 · **Branch:** `claude/review-system-audit-FBZ2h` ·
**Scope:** W1 ONLY (per `docs/teams/SPRINT27_SCOPE.md`). Tree left DIRTY
(parent consolidates + independently verifies + runs the post-commit
CI-equivalent on the clean tree — the Sprint-24 lesson). NOT committed/pushed.

W1 is a **presentation-only, additive** honesty closure mirroring Sprint-25
B1: ZERO KPI / R / NAV / exposure / Expectancy / PF / WR / campaign math
change. It changes dashboard sidebar bytes ONLY when the NAV is NOT
broker+fresh; **byte-identical on the broker+fresh happy path**.

---

## Root closed

`dashboard.py` rendered `🏦 Live IBKR NAV` in a GREEN `st.sidebar.success`
box **unconditionally** — even when NAV was the stale / no-timestamp / silent
$7,500 fallback (its own `load_settings`, `dashboard.py:46-50`, had a bare
`except: pass`). This is the exact "fallback-as-truth" class CLAUDE.md /
AGENTS #1 forbids; Sprint-25 B1 closed it for Telegram
(`report_renderer._nav_disclosure_lines`) but it was never applied to the
dashboard surface (Mark P1-1 + Data D-F1, same root).

---

## Files changed (1 source edit + 1 new pure helper + 1 named test)

| file | change |
|------|--------|
| `dashboard_nav.py` | **NEW** pure, import-light helper `nav_sidebar_render(acc)` (stdlib-only, no streamlit/engine import) — the B1-style gate, unit-testable in isolation exactly like `report_renderer._nav_disclosure_lines` |
| `dashboard.py` | sidebar NAV now reads the CANONICAL `account_state.load()` (single source) + renders via `nav_sidebar_render` — replaces the bare-`except` divergent reader for the prominent green box |
| `tests/test_sprint27_w1_dashboard_nav_honesty.py` | **NEW** named proof (24 tests) |

Nothing else W1-related changed. No byte-locked file touched (verified below).

---

## The change — file:line before/after

### `dashboard.py` (sidebar NAV render site)

**Before** (`dashboard.py:104-107`, pre-W1):
```python
# קריאת הנתונים מקובץ ההגדרות העדכני
saved_nav = float(settings.get("nav", settings.get("total_deposited", 7500.0)))

st.sidebar.success(f"🏦 Live IBKR NAV: **${saved_nav:,.2f}**")
```
`settings` came from `load_settings()` (`dashboard.py:46-50`) — its OWN
bare-`except` reader, the divergent path Data D-F1 flagged. The green
"Live" box was UNCONDITIONAL.

**After** (`dashboard.py:106-118`):
```python
# Sprint-27 W1 — read NAV via the CANONICAL single source
# (`account_state.load()`) … only the *render* now tells the truth.
_acc = acc_state.load()
saved_nav = float(_acc["nav"])

_nav_kind, _nav_text = _nav_sidebar_render(_acc)
if _nav_kind == "success":
    st.sidebar.success(_nav_text)        # broker+fresh — unchanged green box
else:
    st.sidebar.warning(_nav_text)        # stale / fallback / unknown — honest
```
Plus two imports (`dashboard.py:13-14`): `import account_state as acc_state`
and `from dashboard_nav import nav_sidebar_render as _nav_sidebar_render`.

`saved_nav`, `current_acc_size`, `target_risk_usd`, and every downstream KPI
are byte-identical: `account_state.load()["nav"]` is
`float(data.get("nav", data.get("total_deposited", 7500.0)))` — the SAME
canonical value the old `settings.get(...)` produced on the normal broker
config (the only delta is NAV-Unify D1: an explicit `nav:0` is now kept
rather than `or`-fallen-through — intended, money-positive, not a regression).
The Sprint-15 `fmt_risk_capital_basis` caption (`dashboard.py:181-185`) is
UNCHANGED (out of W1's tight scope; no behavior change there).

### The disclosure logic — `dashboard_nav.nav_sidebar_render(acc)`

GATE is **identical to B1** (`report_renderer._nav_disclosure_lines`):

```
broker_fresh = nav_source == "broker" AND freshness == "fresh"
               AND not is_stale AND ok
```

* `broker_fresh` ⇒ `("success", f"🏦 Live IBKR NAV: **${nav:,.2f}**")` —
  the **BYTE-IDENTICAL** pre-W1 green string, rendered via
  `st.sidebar.success` exactly as before.
* anything else (deposited / fallback / stale / critical / unknown /
  `ok=False` / non-dict arg) ⇒ `("warning", …)` — a NON-green
  `st.sidebar.warning` that **reuses the already-honest `freshness_label`
  verbatim** (e.g. `🟠 Fallback NAV — …`, `🟡 NAV ישן (…)`,
  `🔴 NAV קריטי (…)`) + the NAV source + a short Hebrew "לא Live …
  לא נתון מדויק" line. No new field invented, no math, B1 voice reused.

---

## Broker-fresh byte-identical proof

| scenario | render | result |
|----------|--------|--------|
| broker + fresh NAV (LOCKED-style normal config) | `st.sidebar.success("🏦 Live IBKR NAV: **$X**")` | **BYTE-IDENTICAL to pre-W1** |
| fallback / missing / corrupt config (`ok=False`) | `st.sidebar.warning(…)` | honest disclosure, NOT a green "Live" box |
| no `nav_updated_at` (D3) | `st.sidebar.warning(…)` | honest disclosure |
| stale / critical broker NAV (D2) | `st.sidebar.warning(…)` | honest disclosure (closes D-F1's stale-broker gap the old caption missed) |
| deposited NAV | `st.sidebar.warning(…)` | honest disclosure |

The success-box string is asserted byte-for-byte equal to the literal
pre-W1 f-string by
`TestBrokerFreshUnchanged::test_broker_fresh_text_byte_identical_to_pre_w1`
(and `test_broker_fresh_value_formatted_like_before`,
`TestCanonicalSingleSource::test_fresh_broker_config_canonical_then_helper_unchanged_green`).
The disclosure appears ONLY when NOT broker-fresh ⇒ the normal screen is
unchanged.

---

## Confirmations

- **No byte-locked file touched.** `git diff` is EMPTY for
  `analytics_engine.py`, `engine_core.py`, `period_data_probe.py`,
  `tests/_byte_lock_baselines/*`, `tests/test_real_data_april_regression.py`.
  W1 touched only `dashboard.py` + new `dashboard_nav.py` + new test.
- **C1 / C2 / B3 / Arch-F1 / NAV-Unify intact.** W1 imports the existing
  `account_state` canonical core unchanged (no edit to `account_state.py`);
  no engine/telegram/secure-runner path touched; ALGO/risk math untouched.
- **Presentation-only, additive, zero KPI/math.** `saved_nav` and all
  downstream values are the same canonical NAV; only the sidebar box style +
  an honest warning string change, and only when NOT broker-fresh.
- **Suite count:** baseline-without-W1 (default ordering) =
  **2039 passed, 0 failed** (matches the SCOPE baseline). With W1:
  **exact CI command ⇒ 2063 passed, 0 failed** (2039 + 24 new W1 tests).
- **CI-equivalent (exact command + CI env
  `TELEGRAM_BOT_TOKEN=ci-test-token TELEGRAM_ADMIN_ID=12345
  SUPABASE_URL=https://ci-test.supabase.co SUPABASE_KEY=ci-test-key
  DEV_PIN=0000`):** `pytest --tb=short -q --cov=engine_core
  --cov=adaptive_risk_engine --cov=analytics_engine --cov=addon_risk_engine
  --cov-report=term --cov-fail-under=67` ⇒ **2063 passed, 0 failed,
  coverage 72.02% ≥ 67%.**
- **Ordering note (NOT a W1 defect):** under the alternate
  `-p no:cacheprovider` ordering a single PRE-EXISTING B1 test
  (`test_sprint25_b1_fallback_disclosure.py::…test_frozen_literal_representative_fixture`)
  is order-sensitive in the shared dirty tree. Proven independent of W1:
  baseline WITHOUT any W1 file (default ordering) = 2039/0; that B1 test
  passes alone (17/17) and with the W1 file together (41/41); W1 modifies no
  `report_renderer.py` path. The authoritative CI command (default ordering)
  is 0-failed.
- **Named proof — `tests/test_sprint27_w1_dashboard_nav_honesty.py`
  (24 tests):** broker+fresh ⇒ `kind=="success"`, text byte-identical to
  pre-W1, no disclosure; fallback / stale / critical / deposited /
  no-timestamp / non-dict ⇒ `kind=="warning"`, NOT a green "Live" box,
  verbatim `freshness_label` + source present; REAL config files
  (missing / corrupt / no-timestamp / stale / fresh-broker) driven through
  the REAL `account_state.load()` then the helper ⇒ proves the dashboard
  consumes the CANONICAL single source (no independent bare-`except` reader
  for the prominent figure); a wiring test pins `dashboard.py` imports the
  pure helper + `acc_state.load()` and the old bare-except success box is
  gone. No existing test weakened.
- **NOT committed/pushed; tree left DIRTY.**
