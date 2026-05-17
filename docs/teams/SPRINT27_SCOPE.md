# Sprint-27 — SCOPE / איפיון (derived from the Sprint-26 findings)

**Mode:** founder granted autonomous execution ("start the work; consult only the team; return only with deploy-ready code"). Governed, Mark-gated, per-workstream independent verification + CI-equivalent post-commit on the clean tree (the Sprint-24 lesson). DOC-anchored here; code follows.

Production is LIVE on the branch (deployed code) / `main` `c761967`. Baseline suite: **2039 passed, 0 failed, cov 72.02%**.

## Binding governance (unchanged)
- No byte-locked file changed outside its governed ritual: `analytics_engine.py` (Sprint-24 closed-allowlist + Wave-2A SHA), `engine_core.py` (SHA baseline regen), `period_data_probe.py`, LOCKED `tests/test_real_data_april_regression.py`, all `tests/_byte_lock_baselines/*`. **None of W1–W4 needs to touch any byte-locked file** — if a workstream would, it stops and is re-scoped.
- LOCKED April 8/+$180.49/WR.375/PF2.6262/excl2 + Sprint-22/23 byte-identical. C1/C2/B3/Arch-F1/Engine-P2P3/NAV-Unify invariants intact.
- Behavior changes ONLY in the honest/closure direction; numbers byte-identical on the normal path. No new feature/flag/command (the dashboard *password* is an ADDITION — OUT, see SKIP).
- Each workstream: predefined sub-scope → build → parent independent verify → CI-equivalent post-commit clean tree → push.

## IN — execute

### W1 — Dashboard NAV honesty (Mark P1-1 + Data D-F1, same root) — P1, highest value / lowest risk
Dashboard renders `🏦 Live IBKR NAV` in a green success box even when NAV is stale / no-timestamp / the silent $7,500 fallback. Extend the **already-existing** B1 freshness/source/fallback disclosure (the `account_state.load()` fields: `nav_source`/`freshness`/`freshness_label`/`is_stale`/`is_critical`/`ok`) to the dashboard sidebar. `dashboard.py` is NOT byte-locked. **Byte-identical when broker+fresh** (the disclosure appears ONLY when NOT broker-fresh). Zero math/KPI change. Replace the dashboard's own `load_settings` bare-`except` with `account_state.load()` (single source — closes the divergence Data flagged). Test-pinned: fresh→unchanged; stale/fallback→banner present.

### W2 — Repo-hygiene: untrack the live NAV config (Ops O1 HIGH) — P1 safety
`sentinel_config.json` holds the live IBKR NAV but is git-tracked (`.gitignore:3` can't bite a tracked file) → any rollback `git checkout/reset` silently overwrites the live NAV. Repo fix: `git rm --cached sentinel_config.json` (working copy kept) so `.gitignore` finally bites; commit a tracked **`sentinel_config.example.json`** template so fresh clones still have a shape. **Host-safety step is the founder's** (cannot be done by the parent and a botched untrack-pull is the very data-loss we prevent): documented in `DEPLOYMENT_RUNBOOK.md` — on the host, BEFORE the pull that lands the untrack: `cp sentinel_config.json /tmp/nav.bak && git rm --cached sentinel_config.json` (local), pull, verify NAV intact, restore from backup if needed; and forbid `git reset --hard`/`git checkout .` on the prod host.

### W3 — Companion voice (UX P0 — the founder's core emotional goal) — P2, presentation-only
Add ONE concise "מה עכשיו?" verdict+next-step line at the TOP of: the weekly/monthly Telegram summary, the live חדר-מצב/open-book surface, and the risk-monitor daily digest — derived ONLY from already-computed signals (existing verdict/headline/open-book/drawdown/NAV-freshness state); **no new computation, zero math, numbers byte-identical**. Humanize the C1 PIN-expiry and B3 race-refusal wording (warmer, still honest). Disambiguate "silence ≠ all-clear" where a surface can render empty. Strictly additive presentation; broker-fresh report numbers byte-identical.

### W4 — Safe housekeeping
- **W4a** RISK_LADDER doc↔code divergence (Research): correct `docs/MODULE_MAP.md` to match the DEPLOYED code ladder `[0.25,0.40,0.60,0.85,1.15,1.50,2.00]` (code is authoritative for behavior; changing the ladder itself is a money-methodology decision → OUT/founder-only). DOC-only.
- **W4b** C1 test self-containment (Testing): the 5 `TestC1ValidSessionUnchanged` + the sprint17 order-dependency — add a 1-line `monkeypatch.setenv("DEV_PIN", …)` so "green" can't become a CI-lie via an unrelated env change. Test-only; net count unchanged.
- **W4c** `telegram_bot.py:872` raw `supabase.table("trades").select("*")` → `supabase_repository.get_all_trades(...)` (Arch S26-R1) + a parity test. Read-only, byte-identical result; `telegram_bot.py` is fragile but NOT byte-locked — minimal additive swap, no wholesale rewrite, C1 guard/admin gate untouched.

## SKIP — out of scope (with reason)
- **Dashboard password/auth** — a NEW feature (ADDITION) + a founder security/topology decision (Tailscale/LAN acceptance). NOT built. Founder operational item only.
- **Dashboard :8501 network-boundary confirmation** — founder operational/acceptance decision; not codeable here.
- **F3 NaN-`pnl_usd`→$0 disclosed-exclusion** — an engine behavior change on a byte-locked path; founder-gated, explicitly deferred by Engine. Re-scope only on explicit founder authorization.
- **Code-side RISK_LADDER change** / **migration stray `</content>` tag** — money-methodology / migration edits ruled OUT in prior sprints.

## Done = deploy-ready
All of W1–W4 landed, parent-verified, full CI-equivalent **post-commit on the clean tree** 0-failed (≥2039 + new tests), LOCKED regression + Sprint-22/23 byte-identical, no byte-locked file touched, `DEPLOYMENT_RUNBOOK.md` updated with the W2 host-safe procedure. Then — and only then — return to the founder with the deployable result + the founder-only operational items.
