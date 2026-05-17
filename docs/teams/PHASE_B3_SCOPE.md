# Phase B3 — Add-On `campaign_id` write-race — PREDEFINED SCOPE

**Status:** SCOPE — awaiting founder go-ahead before execution.
**Origin:** Sprint-25 Arch audit F3 ("single safest highest-value structural closure"). Founder selected B3 as the next governed Phase.
**Authority model:** predefined scope + separate acceptance tests; `telegram_bot.py` is a CLAUDE.md most-fragile area + this is an explicit Supabase write path (AGENTS.md #4) → founder-gated, Mark-gated.

---

## 1. The defect (verified against source)

`/addon SYMBOL …` plans the add-on against a specific open position resolved at `telegram_bot.py:778-786` (`sym_rows.iloc[0]` from `ec.get_open_positions_campaign(df)`). The pending state stored at `telegram_bot.py:~860-867` contains only `symbol` (+ entry/stop/qty/type) — **no `campaign_id`**.

At confirm, `telegram_callbacks.py:306` does a **fresh re-resolution**: `cid = repo.get_open_campaign_for_symbol(supabase, sym)`, then `repo.update_management_notes(...)` (`:308`) and `repo.update_addon_record(...)` (`:315`) write to **whatever campaign that returns**.

**Race / corruption:** if between plan and confirm the open campaign for `sym` changed (the planned campaign closed, a new same-symbol campaign opened, or a concurrent fill re-resolved it), the add-on management-notes + addon record are silently written to the **wrong campaign's Supabase rows**. User-invisible data-record corruption on an explicit write path.

## 2. The fix (Arch-recommended; minimal, additive, byte-identical in the normal case)

1. **`telegram_bot.py`** — when the Add-On pending state is set (~:860-867), ALSO store the **planned `campaign_id`**: the `campaign_id` of the exact open-position row the `/addon` was planned against (the same row used for entry/stop/qty, available from the `get_open_positions_campaign` result / `sym_rows`). Strictly additive (one extra key in the existing pending dict).
2. **`telegram_callbacks.py:~299-306`** — at `addon_confirm|YES`, **prefer the pending state's stored `campaign_id`**; only fall back to `repo.get_open_campaign_for_symbol(supabase, sym)` when the pending state has none (legacy/older pending → backward-compatible). Guarded fallback — **byte-identical when the stored cid is absent OR equals the re-resolved cid (the normal case)**; corrected only when they diverge (the race), where the write now targets the **planned** campaign the user actually saw/confirmed.
   - The stored↔re-resolved **mismatch** is exactly the race signal. Minimal scope = use the planned cid. *Optional hardening (founder/Mark decision, NOT baked in by default):* on mismatch, refuse the write with an explicit Hebrew message instead of silently writing — flag for the go-ahead decision.

`repo.*` write functions, the migration/schema, and the rest of the confirm flow are unchanged.

## 3. Hard constraints / byte-identity obligations

- **No byte-locked file changes:** `analytics_engine.py`, `engine_core.py`, `period_data_probe.py`, `telegram_bot_secure_runner.py`, `docker-compose.yml`, migrations, LOCKED `tests/test_real_data_april_regression.py`, and **all** `tests/_byte_lock_baselines/*` git-diff EMPTY. No baseline regenerated. No `engine_core`/`analytics` math change.
- **`telegram_bot.py`** (fragile, NOT baseline-locked; C1 already edits it): minimal additive change only — NO wholesale rewrite; the admin gate, the C1 `_require_active_dev_session` guard, and secure_runner wrapping/import order **untouched & byte-identical**.
- **Byte-identical normal case:** when the stored cid is absent or equals the re-resolved cid, the confirm path produces the identical Supabase calls + identical messages as today (the only behavior change is on the divergent-cid race).
- No new feature/flag/command/metric (persisting an already-known id + a guarded fallback is a closure-fix, not an addition). Sprint-22/23/24 + C1 + C2 + Wave-2A invariants intact; WS-C/`-1`-sentinel/ALGO string untouched.
- Full suite `python -m pytest -q -p no:cacheprovider` ≥ **1976**, 0 failed (new tests only ADD; none weakened — Mark 6.1). CI-equivalent (`--cov-fail-under=67`, CI env) verified GREEN **post-commit on the clean tree** (the Sprint-24 lesson).

## 4. Separate acceptance tests (new `tests/test_phase_b3_addon_cid.py`)

Deterministic mock-Supabase / mock-`repo`:
1. **Race corrected:** pending state has planned `campaign_id = X`; `get_open_campaign_for_symbol` would now return `Y≠X`; assert `update_management_notes`/`update_addon_record` are called with **X** (the planned campaign), never Y.
2. **Normal case byte-identical:** stored cid `== X` and re-resolution `== X` → identical calls/messages as the pre-B3 path (oracle equality).
3. **Legacy fallback:** pending state with **no** `campaign_id` (older state) → falls back to `get_open_campaign_for_symbol` exactly as today (byte-identical).
4. **Pending-state set:** `/addon` stores the planned `campaign_id` of the resolved position row (the same row used for entry/stop/qty).
5. (If the optional mismatch-refusal is approved) mismatch → explicit refusal, **no** Supabase write.
No existing test deleted/weakened; net suite count only grows.

## 5. Open decision for the founder (before execution)

**Mismatch policy:** (a) **minimal** — silently use the planned (stored) cid (corrects the race; byte-identical normal case); or (b) **hardened** — on stored↔re-resolved mismatch, refuse the write with an explicit Hebrew message (safer, but a small new user-visible behavior on the rare race). Recommended: **(b) hardened** — for a real-money write path, surfacing "the position changed since you planned — re-run /addon" is the honest, safe default (CLAUDE.md #1). Founder decides.

**Nothing in this Phase is executed until the founder approves this scope + the mismatch policy.**
