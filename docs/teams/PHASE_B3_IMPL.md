# Phase B3 — Add-On `campaign_id` write-race — IMPLEMENTATION

**Status:** EXECUTED (founder-approved scope `PHASE_B3_SCOPE.md`, HARDENED mismatch
policy, branch `claude/review-system-audit-FBZ2h`). Tree left DIRTY for the parent's
governed verification + consolidation. NOT committed/pushed.

**Defect (Sprint-25 Arch F3, re-verified against source):** `/addon` plans the
add-on against the exact open-position row `sym_rows.iloc[0]`
(`telegram_bot.py` resolution from `ec.get_open_positions_campaign(df)`). The
pending state stored only `symbol` (+ entry/stop/qty/add_type) — no
`campaign_id`. At confirm, `telegram_callbacks.py` did an UNCONDITIONAL fresh
re-resolution `cid = repo.get_open_campaign_for_symbol(supabase, sym)` and wrote
`repo.update_management_notes` + `repo.update_addon_record` to *whatever* that
returned → if the open campaign for `sym` changed between plan and tap, the
Add-On record silently corrupted a **different** campaign's Supabase rows
(user-invisible, explicit-write-path data corruption — AGENTS.md #4).

---

## Edit 1 — `telegram_bot.py` (persist the planned `campaign_id`)

**Location:** `_handle_addon_command`, the `addon_pending` state set.
Pre-B3 the dict was at lines **962-969**; post-B3 it is **974-981** (the
preceding comment + `_planned_cid` resolution added 12 lines).

The `row` here is `sym_rows.iloc[0]` (line 889) — the exact open-position row
already used for `base_price`/`base_qty`/`quantity`/`stop_loss`/etc. Its
`campaign_id` key is the first field emitted by
`engine_core.get_open_positions_campaign` (`engine_core.py:549`
`"campaign_id": cid`), so it is the campaign the user reviewed in the plan card.

**Before (962-969):**
```python
        # Store plan for confirmation step
        user_state[chat_id] = {
            "action":   "addon_pending",
            "symbol":   symbol,
            "entry":    add_entry,
            "stop":     add_stop,
            "qty":      plan.get("proposed_qty", qty_arg),
            "add_type": type_arg,
        }
```

**After (961-981):** strictly additive — ONE new key `"campaign_id"`. No other
key, message, branch, or the inline keyboard / callback_data touched.
```python
        # Store plan for confirmation step.
        # Phase B3: persist the planned campaign_id … (comment)
        _planned_cid = row.get("campaign_id")
        if pd.isna(_planned_cid):
            _planned_cid = None
        user_state[chat_id] = {
            "action":      "addon_pending",
            "symbol":      symbol,
            "entry":       add_entry,
            "stop":        add_stop,
            "qty":         plan.get("proposed_qty", qty_arg),
            "add_type":    type_arg,
            "campaign_id": _planned_cid,
        }
```
If the planned row has no resolvable campaign_id (`NaN`/missing) → store `None`
so confirm falls back to legacy behavior (scope §1 / §2c). `pd` is already
imported (`telegram_bot.py:2`).

⟨MARK⟩ Additive 1-key change in a fragile-but-not-baseline-locked file. NO
wholesale rewrite. Admin gate, C1 `_require_active_dev_session`, secure_runner
wrapping/import order untouched & byte-identical (verified: `git diff
telegram_bot_secure_runner.py` EMPTY; `test_secure_runner.py` +
`test_sprint25_c1_devpin_enforcement.py` 76/76 green). No
`engine_core.split_side_first` / C2 change.

---

## Edit 2 — `telegram_callbacks.py` (`addon_confirm|YES` — 3-case guard)

**Location:** `handle_queries`, `data.startswith("addon_confirm|")` →
`action == "YES"`. Pre-B3 the single line was **306**:
`cid = repo.get_open_campaign_for_symbol(supabase, sym)`. Post-B3 that one
line is replaced by the guard block at **306-338**; everything from `if cid:`
onward (now line 339) is byte-for-byte unchanged.

**Exact confirm-branch logic (the 3 cases):**
```
planned_cid  = pending.get("campaign_id")
resolved_cid = repo.get_open_campaign_for_symbol(supabase, sym)   # always called
if planned_cid is not None:                       # (2a) stored cid present
    if resolved_cid != planned_cid:               # (2b) HARDENED race
        clear pending (if chat_id in user_state: del user_state[chat_id])
        bot.send_message(... explicit Hebrew refusal ..., get_main_menu(), Markdown)
        return                                    # ZERO Supabase write
    cid = planned_cid                             # resolved == planned → proceed
else:                                             # (2c) legacy / None
    cid = resolved_cid                            # fall back, proceed
# unchanged pre-B3 tail: if cid: update_management_notes / addon record /
#   migration-pending `except: pass`; else "no open campaign" warning;
#   pending-clear; success message; decline branch — ALL UNCHANGED.
```

- **(2a) normal:** `resolved_cid == planned_cid` → `cid = planned_cid`
  (== resolved). Identical `repo.*` calls + identical messages as pre-B3.
- **(2b) HARDENED race (the ONLY behavior change):** `resolved_cid !=
  planned_cid` → refuse: NO `update_management_notes`/`update_addon_record`/any
  Supabase write; explicit short RTL Hebrew message
  (`❌ ביטול: הפוזיציה השתנתה — {sym} … הרץ ‎/addon‎ מחדש`); pending cleared
  exactly like the existing cancel/decline path; `return` (no partial write,
  no success message).
- **(2c) legacy/None:** no stored cid (older in-flight pending) OR stored
  `None` → `cid = resolved_cid`; proceeds exactly as pre-B3 (byte-identical).

`repo.*` write functions, the migration-pending `except: pass`, the
"no open campaign" warning, the success message, and the decline branch are
UNCHANGED.

⟨MARK⟩ The single behavior delta is the divergent-cid race → explicit refusal
+ zero write — exactly the authorized closure-fix point (scope §2b, founder
HARDENED choice). Not a new feature/flag/command/metric: it persists an
already-known id + guards an existing write. No schema/migration change.

---

## Named byte-identity proof

`tests/test_phase_b3_addon_cid.py` (NEW, +5 tests, strictly additive):

1. `TestRaceRefusedHardened` — pending `campaign_id="CID-PLANNED-X"`,
   re-resolve `"CID-NEW-Y"` → asserts `update_management_notes` /
   `update_addon_record` **never called**, `get_latest_buy_trade_id` not
   called, explicit Hebrew refusal sent, pending cleared.
2. **`TestNormalByteIdentical`** — *pins normal-case byte-identity*. Runs the
   REAL B3 `handle_queries` AND a faithful pre-B3 ORACLE (the unconditional
   `get_open_campaign_for_symbol` + original write block + original messages,
   same `RTL`, same FROZEN timestamp) and asserts `_repo_call_shape` AND
   `_msg_shape` (exact ordered repo.* calls incl. the precise note string +
   exact outbound message strings/kwargs) are **equal**.
3. **`TestLegacyFallbackByteIdentical`** — *pins legacy byte-identity*. Two
   cases (no `campaign_id` key; explicit `campaign_id=None`) vs the same
   oracle: `_repo_call_shape` == oracle AND `_msg_shape` == oracle, no
   refusal, writes target the re-resolved cid.
4. `TestPendingStoresPlannedCid` — drives the REAL
   `telegram_bot._handle_addon_command` with a deterministic open-positions
   DataFrame; asserts the persisted `campaign_id` is the resolved row's
   campaign_id (`"CAMP-PLANNED"`, the same `sym_rows.iloc[0]` row used for
   entry/stop/qty).

The byte-identity of the **normal** path is pinned by test 2; of the
**legacy** path by test 3 (both via the explicit pre-B3 oracle equality on
ordered repo.* call shape + exact message shape). ONLY the divergent-cid race
(test 1) changes behavior — refuse + zero write.

---

## Confirmations (Mark Ruling 4/5 gate)

- **Byte-locked files git-diff EMPTY:** `analytics_engine.py`,
  `engine_core.py`, `period_data_probe.py`, `telegram_bot_secure_runner.py`,
  `docker-compose.yml`, `tests/test_real_data_april_regression.py`, ALL
  `tests/_byte_lock_baselines/*`, ALL `migrations/*` — verified
  (`git diff --stat` empty). No baseline regenerated. No engine/analytics
  math change.
- **Sprint-19 lock + Sprint-24 paired proof + secure_runner + C1 proof:**
  `test_sprint19_headline_comparison.py` +
  `test_sprint24_b1b3_byte_identical.py` + `test_secure_runner.py` +
  `test_sprint25_c1_devpin_enforcement.py` = **76/76 passed**. Admin gate, C1
  `_require_active_dev_session` guard, secure_runner wrapping/import order
  untouched & byte-identical. No C2 / `split_side_first` change.
- **Sprint-22/23/24 + C1 + C2 + Wave-2A invariants intact;** WS-C /
  `-1`-sentinel / ALGO "תקן entry/stop" string untouched. No
  feature/flag/command/metric/schema/migration added.
- **Suite count only grows:** baseline 1976 collected →
  **1981 passed** (+5 B3 acceptance tests; none deleted/weakened — Mark 6.1).
- **CI-equivalent (BINDING command, CI env incl. `DEV_PIN=0000`):**
  `python -m pytest --tb=short -q --cov=engine_core
  --cov=adaptive_risk_engine --cov=analytics_engine --cov=addon_risk_engine
  --cov-report=term --cov-fail-under=67` →
  **1981 passed, 0 failed, total coverage 71.84% ≥ 67%**. Plain
  `python -m pytest -q` parity (CI env) = **1981 passed, 0 failed**.
- **Pre-existing env-dependency note (NOT a B3 regression):** without
  `DEV_PIN` in env, 5 `TestC1ValidSessionUnchanged` tests fail-CLOSED — this
  is identical at the **clean baseline `782e3ed`** (verified via `git stash`:
  7 failed / 1974 passed there, flaky 5–7 by collection composition). It is a
  pre-existing C1 env/order dependency (Mark Ruling 1.9 class), orthogonal to
  B3 (B3 file run directly before C1 = 37/37 green; B3 saves/restores
  `sys.modules["telegram_bot"]`). The BINDING Mark CI-equivalent command +
  CI env (which sets `DEV_PIN=0000`) is fully GREEN. B3 introduces ZERO new
  failures and weakens no test.

**Post-commit clean-tree CI-equivalent verification + governed consolidation:
the parent's responsibility (not done here; tree left dirty).**
