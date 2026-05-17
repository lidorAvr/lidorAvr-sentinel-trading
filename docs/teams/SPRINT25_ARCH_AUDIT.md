# Sprint 25 — Architecture Production-Closure Deep Review (DOC-ONLY)

**Date:** 2026-05-17 · **Branch:** `claude/review-system-audit-FBZ2h` · **Team:** 🏗️ Architecture
**Scope:** Structural/maintainability gaps that keep the CURRENT code from being 100% production-closed.
NO code, NO commit, NO additions/features, NO rewrites. Every line below is a verified `file:line`
(re-read against source). Baseline suite: **1898 collected** (`pytest --co`). Working tree clean.

## Constraints honored
No `telegram_bot.py` wholesale-rewrite proposal (AGENTS.md red line). Every proposed closure is
small + additive-or-byte-preserving + test-backable. Fragile-area items (engine_core / telegram_bot /
NAV config / docker-compose / analytics byte-lock) are flagged HIGH and remain founder-gated. The
Sprint-19 `test_analytics_engine_git_diff_empty` append-only byte-lock on `analytics_engine.py`
(SPRINT24_TEAM_MEETING) is treated as permanent: no executable-line edit there is proposed.

## Carry-forward status from Sprint-24
- S24 #6 (raw Supabase read in `telegram_bot.py`) — **STILL OPEN**, re-verified at
  `telegram_bot.py:769` (the only direct `.table(` in the file). Re-filed below as **P2 / F4**.
- S24 #2 (duplicate config reader) — **WORSENED**: now a 3-way divergence (see **P1 / F1**).
- S24 #1/#5/#3/#4 — unchanged status; not re-litigated here (Engine-owned / OUT lock items).

---

## Prioritized findings

### P1 — F1 · Triple-divergent NAV → target-risk resolution (latent money-risk)
**Evidence (all re-read):**
- `account_state.load()` + `account_state.target_risk_usd()` (`account_state.py:16-61`) —
  documented "Single source of truth for NAV" (MODULE_MAP). Reads `sentinel_config.json`
  `nav`→`total_deposited`→`7500.0`; fallback dict shape A; never raises.
- `engine_core.get_nav_with_freshness()` (`engine_core.py:1492-1525`) — reads the SAME
  `sentinel_config.json`, **different** fallback (`is_critical=True`, different Hebrew label),
  **different** dict shape (`source`/`updated_at` vs `nav_source`/`nav_updated_at`).
- `bot_helpers.get_nav_and_risk()` (`bot_helpers.py:94-97`) and
  `risk_monitor.py:604-607` — **byte-identical** logic
  `acc_size = nav_info["nav"] if nav_info["ok"] else float(account_settings.get("total_deposited",7500.0))`
  then `acc_size * (risk_pct/100)`, written twice. `report_open_book.py:211` is a third
  near-copy of the multiply step.
- Config-file *reader* itself duplicated 3×: `bot_helpers.py:80-85`,
  `risk_monitor.py:150-153` (bare `except:`), plus `account_state` / `engine_core` path-search
  variants. The S24 #2 two-way drift is now three-way.

**Production risk:** NAV and target-risk are a CLAUDE.md "most fragile area." The bot
(`get_nav_and_risk`) and risk-monitor (`:604`) resolve NAV via
`ec.get_nav_with_freshness()` while the report pipeline resolves it via `account_state.load()`
— **two different fallback/freshness contracts feeding the same risk math.** A future edit to
one fallback (e.g. `7500.0`, or the `ok` semantics) silently desyncs Telegram risk sizing,
risk-monitor Sizing-Leak threshold, and the weekly/monthly report target-risk — the exact
"same value computed two divergent ways" hazard. `risk_monitor.py:153` bare `except:` also
swallows a corrupt-config signal that `account_state` surfaces honestly.

**Severity:** P1 · **value÷risk:** high value / HIGH risk (NAV fragile area; founder-gated; cross-service).
**Tag:** closure-fix (debt+risk flag only — do NOT redesign).
**Proposed closure (small, gradual — CLAUDE.md "risk/NAV config helper"):** flag the debt; the
safe first step is the S24-#2 move — `risk_monitor` imports `bot_helpers.get_account_settings`
(delete its byte-identical local copy + bare `except`). Do NOT yet unify the `account_state`
vs `get_nav_with_freshness` NAV source — that is a behavior-bearing decision (different
fallback) requiring founder sign-off; only document the divergence at both call boundaries.
**Proof strategy:** new `test_nav_resolution_single_source.py` — present/missing/corrupt
config parity across `bot_helpers.get_account_settings` and the deleted `risk_monitor` copy;
assert `get_nav_and_risk` vs `risk_monitor:604-607` produce identical `(acc_size,target_risk)`
for the same inputs; full suite 1898 unchanged. Author the parity test BEFORE any deletion.

### P1 — F2 · `analytics_engine.compute_period_analytics` "never raises" contract leak
**Evidence:** `analytics_engine.py:24` —
`t_risk = account_state["nav"] * account_state["risk_pct_input"] / 100` executes **before**
the `try:` at `:25`. The function docstring (`:23`) and MODULE_MAP both promise "Never raises
— returns error dict on failure." Subscript access (`["nav"]`, `["risk_pct_input"]`) outside
the guard raises `KeyError`/`TypeError` if a caller passes a non-`account_state.load()` dict
(e.g. the `bot_helpers.get_account_settings()` shape, which has NO `nav` key — see F1).

**Production risk:** Today scheduler (`report_scheduler.py:285`) and on-demand
(`report_on_demand.py:109`) both pass `acc_mod.load()` (correct shape) → not triggered in
prod *now*. But the contract is a latent landmine: any future caller passing the OTHER
(equally-blessed) config dict shape crashes the report pipeline with an unhandled exception
instead of the documented honest `{ok:False,...}` error dict — and F1's shape divergence makes
that mis-pairing plausible. The byte-lock forbids fixing `:24` in place, which is itself the
closure constraint to record.

**Severity:** P1 (contract integrity on the report money-path) · **value÷risk:** high / HIGH
(byte-locked file — cannot edit `:24`; founder + Mark-gated like B1/B3).
**Tag:** closure-fix (flag only; the in-file fix is lock-blocked → must be a governed
allowlist expansion exactly like Wave-2b, NOT done ad hoc).
**Proposed closure:** DOC-ONLY now — record that the "never raises" guarantee is violated for
the first two statements and is structurally unfixable without a Mark-gated lock expansion.
Safe additive alternative (no `analytics_engine` edit): callers already normalize via
`acc_mod.load()`; add a `test_compute_period_analytics_contract.py` that PINS the current
behavior (raises on bad shape) so the gap is visible and a future governed fix has an oracle.
No behavior change this sprint.

### P2 — F3 · `addon_confirm|YES` rebinds campaign_id → wrong-campaign Supabase write
**Evidence:** `/addon` plans against `sym_rows.iloc[0]` (the open position resolved at
`telegram_bot.py:778-786`) but the pending state stored at `telegram_bot.py:860-867`
contains only `symbol` — **no campaign_id**. At confirm,
`telegram_callbacks.py:306` does `cid = repo.get_open_campaign_for_symbol(supabase, sym)`
— a fresh re-resolution. `repo.update_management_notes(...)` (`:308`) +
`repo.update_addon_record(...)` (`:315`) then write to whatever campaign that returns.

**Production risk:** If the campaign the user saw in the plan card closes (or a new campaign
for `sym` opens) between plan and tap, the Add-On note + `is_addon`/`base_campaign_lot_id`
write lands on a **different campaign** than the one the user reviewed — a silent
Supabase-record corruption. AGENTS.md #4 ("Supabase trade records must not be mutated unless
the user action explicitly requires it") and SAFE_CHANGE_PROTOCOL "Supabase writes must be
intentional & traceable" are at risk. Admin gate is NOT bypassed (callback is guarded by the
secure runner's patched `callback_query_handler`), so this is a correctness, not auth, defect.

**Severity:** P2 (real but narrow race; both states must change in a short window) ·
**value÷risk:** med / HIGH (`telegram_bot.py` fragile + Supabase write path; founder-gated).
**Tag:** closure-fix (small, additive: persist+verify the planned cid; NO rewrite).
**Proposed closure:** add `"cid"` to the pending-state dict at `telegram_bot.py:866` (the
campaign already resolvable from `row`/`pos_res` at plan time) and, at
`telegram_callbacks.py:306`, prefer the persisted cid and **only** fall back to
`get_open_campaign_for_symbol` if absent — emitting the existing
"לא נמצא קמפיין פתוח" honest warning if they disagree. Narrow, additive, preserves every
existing path.
**Proof strategy:** `test_addon_cid_binding.py` with a mock Supabase: plan→close-campaign→
confirm asserts the write targets the PLANNED cid (or surfaces the honest mismatch warning);
existing addon-flow tests + suite 1898 green.

### P2 — F4 · Residual raw Supabase read bypasses the repository layer (S24 #6, still open)
**Evidence:** `telegram_bot.py:769` `res = supabase.table("trades").select("*").execute()`
— the only direct `.table(` in the file; `supabase_repository.get_all_trades(sb)`
(`supabase_repository.py:22-23`) already issues the byte-identical
`select("*").execute().data`. Every other read in the file is routed through `repo.*`.

**Production risk:** Module-boundary inconsistency on the CLAUDE.md "extract Supabase
repository layer" direction. Read-only (no mutation), so the risk is maintainability +
predictability (one query that won't pick up a future repo-level filter/RLS change), not
data safety. Lowest-risk of the closure items.
**Severity:** P2 · **value÷risk:** med / med-HIGH (`telegram_bot.py` fragile but read-only).
**Tag:** closure-fix (one-line, mirrors the proven prior repo extraction).
**Proposed closure:** replace the inline read with
`repo.get_all_trades(supabase)` → `pd.DataFrame(...)`. Read-only flow → AGENTS.md #4 intact.
**Proof strategy:** mock-Supabase parity test asserting identical query + identical DataFrame;
`test_supabase_repository.py` + addon-flow tests + suite 1898.

### P3 — F5 · Unreachable duplicate `/help` handler (dead code)
**Evidence:** `telegram_bot.py:473` `if text in ["❓ עזרה", "❓ פקודות מערכת", "/help"]: …
return …` already matches BOTH `"❓ פקודות מערכת"` and `"/help"` and returns. The later
block `telegram_bot.py:562` `if text in ["❓ פקודות מערכת", "/help"]:` is therefore
**provably unreachable** (and renders an older, inconsistent help string that can never ship).
**Production risk:** None functionally; pure dead code + maintainer confusion (two help texts,
only one live). Closure = remove the unreachable 2-line block.
**Severity:** P3 · **value÷risk:** low / low (1 dead branch in a fragile file — keep additive-safe).
**Tag:** polish (delete-dead; behavior-preserving — the branch is proven unreachable).
**Proof strategy:** `test_help_handler_single.py` asserting `"/help"` / `"❓ פקודות מערכת"`
route through the `:473` branch only; AST/coverage shows `:562` unhit; suite 1898 green.

### P3 — F6 · Dead local import + drift among 3 numeric-coerce variants
**Evidence:**
- `telegram_bot.py:859` `import json as _json` — `_json` never referenced (dead import; the
  module already imports `json` at `:1`).
- Numeric-coerce written 3 divergent ways: `analytics_engine._coerce_numeric`
  (`analytics_engine.py:356-362`, 5 cols, `if col in df.columns` guard) ·
  `period_data_probe.py:165-168` (inline, **6** cols incl. `initial_risk_price`, guarded) ·
  `engine_core.py:478` (inline, 5 cols, **NO `if col in` guard** → raises `KeyError` where the
  other two silently skip). `period_data_probe` ALREADY imports `analytics_engine as ae` and
  reuses `ae._to_naive` (`:185-186`) but NOT `ae._coerce_numeric` — the partial reuse is the
  drift tell.
**Production risk:** F6a is cosmetic dead code. F6b: the `engine_core.py:478` no-guard variant
has a *different failure contract* than the other two on a math-bearing path — a real
copy-paste-drift hazard if column sets ever diverge (already do: probe carries
`initial_risk_price`). Unifying is OUT (Engine-owned byte-identical proof per S24 #3 / Tier-C;
`engine_core` is the top fragile area) — flag the **debt only**.
**Severity:** P3 · **value÷risk:** low / (F6a low, F6b HIGH-if-touched).
**Tag:** F6a polish (remove dead import — trivially byte-safe) · F6b **addition/refactor
(OUT — flag only)**, defer to Engine team's locked April-regression proof; Architecture does
NOT duplicate Engine's analysis.

---

## Module-boundary & runtime-ordering observations (debt, no edit proposed)
- **Admin-gate ordering dependency (record, do NOT change):** the secure runner installs the
  admin/rate gate by monkey-patching `telebot.TeleBot.message_handler` /
  `callback_query_handler` in `telegram_bot_secure_runner.install_telegram_hardening()`
  **before** `import telegram_bot` (`:176-177`). The gate is correct ONLY because that import
  order holds and `bot_core.bot` is instantiated *after* the patch. This is a latent
  ordering invariant: anything that imports `telegram_bot`/`bot_core` before the patch (e.g. a
  future test harness or a new entrypoint) yields an UNPATCHED bot with NO admin gate.
  Not a current production bug (compose runs the runner — verified MODULE_MAP/AGENTS) and is a
  HARD red line to "fix" by restructuring. **Flag as a documented fragility only**; the
  existing `test_secure_runner.py` should be noted as the guardrail. No change proposed.
- **Import-time `SystemExit` side effects:** `bot_core.py:14-28` raises `SystemExit` at import
  for missing `TELEGRAM_BOT_TOKEN`/`ADMIN_ID`/Supabase creds, and instantiates the global
  `bot`/`supabase` singletons + `DEFAULT_USER_ID` at import. Intentional fail-fast; flagged
  only as an ordering/global-mutable-state fact for the F-items above. No change.
- **B2 Supabase module-singleton** (`report_scheduler.py:123-143`): re-verified
  behavior-preserving (load_dotenv + env reads + None-on-missing stay per-call). No issue;
  noted because it is shared mutable module state under the real loop — correctly scoped.

## Explicitly OUT-OF-SCOPE (tempting but a behavior change / not closure)
- Unifying `account_state.load()` vs `engine_core.get_nav_with_freshness()` NAV source
  (different fallback semantics = behavior change; founder decision).
- Any `analytics_engine.py` executable-line edit (Sprint-19 permanent byte-lock).
- Any `engine_core` coerce/math unification (Tier-C, Engine-owned proof).
- Sender transport/parse_mode/retry unification, probe edits, ALGO wording (S24 OUT, unchanged).
- `telegram_bot.py` wholesale rewrite; admin/dev-PIN gate; secure_runner; compose/migration.

## Recommendation
Tier-A safe-now (DOC-trivial / byte-safe): **F5, F6a**. Tier-B (test-backed small additive
closure, founder-gated): **F3, F4, F1-step-1**. Tier-C / record-only (lock/Engine-owned):
**F2, F6b**, admin-gate-ordering note. Founder default = Tier-A only, then reassess.

### Single safest highest-value structural closure
**F3 — persist the planned `campaign_id` in the Add-On pending state.** It is the only
finding that is simultaneously (a) a real, user-invisible **Supabase-record-corruption** risk
on an explicit write path (AGENTS.md #4), (b) closable with a strictly **additive** 1-key
change in `telegram_bot.py` + a guarded fallback in `telegram_callbacks.py` (no rewrite, no
existing path removed, byte-identical when the cid agrees — which is the normal case), and
(c) fully test-pinnable with a deterministic mock-Supabase race fixture. Highest value
(data integrity) at the lowest structural blast radius.
