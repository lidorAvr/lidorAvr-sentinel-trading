# Sprint-25 — Data-Contracts / Supabase Production-Closure Deep Audit (DOC-ONLY)

**Date:** 2026-05-17 · **Branch:** working tree · **Mode:** DOC-ONLY (no code, no schema, no migrations, no additions).
**Mandate:** verify the CURRENT data layer is 100% production-closed and honest. Flag existing only.
**Baseline (carried, DEC-021 Wave-2b):** full suite 1898 passed. LOCKED `tests/test_real_data_april_regression.py` (8 / +$180.49 / WR .375 / PF 2.626 / excl 2) must stay byte-identical for every proof named below. WS-C + `-1`-sentinel stay DEFERRED (out of scope).

Re-verified against source + `docs/DATA_CONTRACTS.md` + DEC-019/-020/-021. Each finding: `file:line` (+ contract §), production data-integrity scenario, severity, value÷risk, tag, named proof.

---

## P0 — none

No P0. The Sprint-22 tz fix + Sprint-23 split + DEC-019/-020 raw-Supabase reconciliation hold; migrations are clean and idempotent; the WS-B unlinked + Sprint-20 excluded disclosures are present and honest. The data layer is materially production-closed. The single most important remaining gap is **F1 (P1)**.

---

## P1

### F1 — Telegram summary has NO NAV source/freshness/fallback disclosure; PDF-degraded mode presents fallback-NAV KPIs as "authoritative & complete"
- **Where:** `report_renderer.py:309 build_summary_text` (entire function — NO `nav_source`/`freshness_label`/`is_stale` line anywhere) vs `report_renderer.py:585-590` (PDF context DOES carry them) + `templates/weekly_report.html.j2:20,85` / `monthly_report.html.j2:19,79` (`.freshness-banner`, `nav_source`, `is_stale ⚠️`). Degraded path: `report_scheduler.py:362-363,473-474` appends `_DEGRADED_PDF_NOTE` (`report_scheduler.py:40` = "ה-PDF לא נוצר… סיכום הטקסט למעלה הוא הנתון הקובע והמלא"). Same gap on the on-demand path: `report_on_demand.py:220 build_summary_text`.
- **Contract:** `DATA_CONTRACTS.md` §"NAV / account-size contract" rule 2 ("If IBKR NAV is unavailable and the system falls back to deposited capital/default value, the report must say so"); §"Telegram report contract" ("source/fallback disclosure for risk-sensitive reports"); CLAUDE.md hard constraint "Do not silently present fallback data as exact truth"; AGENTS.md prime-directive #1.
- **Production scenario:** `sentinel_config.json` missing/corrupt or no `nav_updated_at` → `account_state.load()` returns `nav_source:"fallback"`, `nav:7500.0`, `ok:False`, `is_stale:True` (`account_state.py:89-102`). `compute_period_analytics` computes `t_risk = nav*risk_pct/100` off the **fallback $7,500** (`analytics_engine.py:24`); every R / Net-R / Expectancy / Sizing / oversized figure is then derived from a guessed NAV. The PDF would show the orange `freshness-fallback` banner — but when WeasyPrint degrades (the real, documented Sprint-16 `libgobject` OSError, `report_renderer.py:945`), `pdf_path=""` and the user gets ONLY the Telegram text, which carries **zero** NAV-source signal and a trailer explicitly calling it "the authoritative and complete figure." A stale/fallback-NAV risk picture is presented as exact truth — the precise CLAUDE.md red line.
- **Severity:** P1. **Value÷risk:** **HIGH value ÷ LOW risk** — the single highest value÷risk closure (see below).
- **Tag:** **closure-fix (founder decision)** — it changes user-facing Telegram output (adds a disclosure line), so it is a behavior change, not pure polish; needs founder go-ahead per the fragile-area / Telegram-output rules.
- **Named proof strategy:** new `tests/test_sprint25_nav_disclosure.py`: (a) `build_summary_text` with an account dict where `nav_source=="fallback"`/`is_stale==True` MUST contain a fallback/freshness token; with `nav_source=="broker"` & fresh it MUST be byte-identical to today (regression guard — fresh path unchanged); (b) assert the degraded-mode concatenation still carries the token. LOCKED April regression untouched (it asserts analytics, not summary text). No `analytics_engine.py` line touched ⇒ Sprint-19 byte-lock + Sprint-22 numbers unaffected.

### F2 — `compute_period_analytics` ignores `account["ok"] is False`; fallback NAV silently flows into all R-math with no honest gate
- **Where:** `analytics_engine.py:24` `t_risk = account_state["nav"] * account_state["risk_pct_input"] / 100` — direct subscript, no read of `account_state.get("ok")` / `nav_source` / `is_stale`. Callers `report_scheduler.py:288,400` and `report_on_demand.py:112` pass `acc_mod.load()` straight through; none branch on `account["ok"] is False`.
- **Contract:** `DATA_CONTRACTS.md` §"NAV / account-size contract" rule 2; §"Core principle" ("computed from … default config … the output must say so"); `MODULE_MAP.md` `account_state.py` ("Fallback to $7,500 when config is missing or corrupted").
- **Production scenario:** identical trigger to F1 (config missing/corrupt). `account_state.load()` deliberately never raises and returns a *usable* dict with `ok:False`; analytics happily computes a full KPI set off the $7,500 fallback. Because `ok`/`nav_source` are never inspected anywhere in the analytics→summary path, the only honest signal is the PDF banner — which F1 shows is absent in degraded/Telegram mode. F1 and F2 are the same root data-integrity hole seen from two layers (presentation vs computation); fixing F1's disclosure closes the user-visible risk even if F2's compute path is left as-is, which is why F1 is the priority.
- **Severity:** P1 (collapses into F1 operationally). **Value÷risk:** HIGH ÷ LOW (subsumed by F1).
- **Tag:** **closure-fix (founder decision)** (same disclosure surface as F1).
- **Named proof:** covered by the F1 test (assert the fallback token appears whenever `account["ok"] is False`); no math change, R/NAV/Expectancy values byte-identical on the `ok:True` path (LOCKED April fixture uses a valid test account → unchanged).

---

## P2

### F3 — `verify_migrations.py` reaches `==005` correctly, but its header docstring is stale ("only two migrations today" / "MIGRATIONS below… hard-code")
- **Where:** `migrations/verify_migrations.py:16-22` docstring says "with only two migrations today, that's over-engineering" while `MIGRATIONS` (`:30-56`) correctly lists **all 5** (001…005) with the right post-conditions. The runtime check is correct and idempotent (read-only `select().limit(1)`).
- **Contract:** `DATA_CONTRACTS.md` §"Schema change protocol"; honesty principle (a future operator reading "two migrations" could under-trust the check).
- **Scenario:** purely a doc/operator-confidence drift; `verify_migrations` itself enforces 005 exactly and the migrations are all `IF NOT EXISTS`/`ADD COLUMN IF NOT EXISTS` (idempotent, additive, reversible via the matching `rollback_00X.sql`). 003/004/005 use a fixed sentinel UUID default + `WHERE user_id IS NULL` backfill — safe to re-run, no destructive DDL anywhere.
- **Severity:** P2. **Value÷risk:** LOW ÷ negligible.
- **Tag:** **polish** (doc-only; comment fix, no behavior).
- **Named proof:** none needed (comment-only); `python migrations/verify_migrations.py` still exits 0 against a fully-migrated DB.

### F4 — `005_create_open_tasks.sql` has a stray closing `</content>` tag on the last line
- **Where:** `migrations/005_create_open_tasks.sql:59` ends with a literal `</content>` (same artifact in `rollback_005.sql:18`). It sits *after* the final `--` comment block, so PostgreSQL parses it as trailing garbage on an otherwise-comment region — but it is NOT valid SQL and would error if the file were run verbatim past the comment.
- **Contract:** `DATA_CONTRACTS.md` §"Schema change protocol" step 4 (backward-safe, runnable migration). DEC-021 / SPRINT24 explicitly forbid schema/migration changes — flag only.
- **Scenario:** the founder applies migrations by copy-pasting into the Supabase SQL Editor. `005`/`rollback_005` are marked APPLIED 2026-05-15 (header) so production is unaffected, but a re-run or a fresh environment that pastes the whole file including line 59 hits a syntax error after the verify block. Low likelihood (file already applied; the DDL precedes the tag), real correctness defect.
- **Severity:** P2. **Value÷risk:** LOW ÷ LOW (forbidden to fix this sprint — migration change is OUT).
- **Tag:** **closure-fix (founder decision)** — touching a migration file is explicitly out-of-scope for Sprint-24/25 guardrails; needs an explicit founder ruling to remove the stray tag.
- **Named proof:** if ever authorized — `git diff` shows ONLY the deleted `</content>` line; `verify_migrations` still 0; no schema semantic change.

### F5 — NULL/blank `pnl_usd` on a real in-window SELL silently coerced to $0 (masking real realized PnL)
- **Where:** `analytics_engine.py:31` `_coerce_numeric(df, (... "pnl_usd"))` → `pd.to_numeric(...).fillna(0)` (`:356-362`). Consumed by `_aggregate_campaigns:422` `net_pnl = float(sells["pnl_usd"].sum())` and the WS-B `unlinked_pnl` sums (`:84,87`). A SELL row with NULL/blank/garbage `pnl_usd` contributes `$0.00` to the campaign's realized PnL and Net R with no flag.
- **Contract:** `DATA_CONTRACTS.md` §"Trade row contract" ("Do not assume every field is always populated"); §"Core principle" (incomplete records must be marked); CLAUDE.md "do not silently present fallback data as exact truth."
- **Scenario:** the DEC-019/-020 raw-SQL reconciliation proved the **April** production set has populated `pnl_usd` for all countable campaigns, so this is currently latent, not active. But the contract explicitly warns fields may be unpopulated; a future import gap (or a manually-inserted SELL) would understate realized PnL/Net R and silently re-classify a winner→breakeven with zero disclosure — a #1 risk if it ever materializes. No counter exists for "SELL with NULL pnl_usd" (contrast: NULL `campaign_id` IS disclosed via the WS-B `unlinked_*` path).
- **Severity:** P2 (latent; no production occurrence proven). **Value÷risk:** MEDIUM ÷ LOW.
- **Tag:** **addition (OUT — flag)** — adding a "NULL-pnl SELL" disclosure counter is a new feature/contract surface (mirrors WS-B but is net-new); explicitly out of a no-additions sprint. Flag for the WS-B/data-completion backlog.
- **Named proof (if ever taken up):** mirror the WS-B guard pattern — countable KPI subset byte-identical with/without the new counter; LOCKED April fixture (all `pnl_usd` populated) byte-identical ⇒ proves additive-only.

---

## P3

### F6 — `commission` is a documented trade field never read by the realized-PnL path
- **Where:** `DATA_CONTRACTS.md` §"Trade row contract" lists `commission`; `analytics_engine` net PnL uses ONLY `pnl_usd` (`:422`) — `commission` is never referenced anywhere in the data layer (`grep` clean across `analytics_engine.py`, `report_scheduler.py`, `period_data_probe.py`).
- **Assessment:** NOT a bug. The DEC-019/-020 raw-Supabase reconciliation (to the cent: $+336.14, +11.01R, PF 4.03) proves production `pnl_usd` is the **broker-side NET** figure (commission already deducted). The defect is a **contract-documentation gap**: the contract lists `commission` without stating it is informational-only and that `pnl_usd` is authoritative-net. A future agent could wrongly subtract `commission` again (double-count) — exactly the kind of mistake the contract exists to prevent.
- **Contract:** `DATA_CONTRACTS.md` §"Trade row contract" / §"Schema change protocol".
- **Severity:** P3. **Value÷risk:** LOW ÷ negligible.
- **Tag:** **polish** (one clarifying sentence in `DATA_CONTRACTS.md` — doc-only, no code).
- **Named proof:** none (doc-only); reconciliation already proves `pnl_usd` net-of-commission.

### F7 — `_get_closed_campaigns` docstring/contract drift ("last SELL" vs actual "ANY in-window SELL") — already noted, not yet contract-documented
- **Where:** `analytics_engine.py:389` docstring "whose last SELL falls in [start, end)"; real logic `:399-404` keys off **ANY** in-window SELL (`in_period = sells[(td>=start)&(td<end)]`). The A1 Sprint-24 additive `#` CORRECTNESS NOTE (`:390-398`) documents this *in code* but `DATA_CONTRACTS.md` does not state the closed-campaign window contract at all.
- **Scenario:** a campaign with a partial SELL inside the window and the FINAL SELL after `period_end` is counted as "closed" for the period (any-SELL semantics). DEC-019/-020 reconciled the April numbers exact under this exact behavior, so it is the *intended, validated* contract — but undocumented in the data contract, so a future "fix to match the docstring" would silently change the validated campaign set (a campaign-math change forbidden without tests).
- **Contract:** `DATA_CONTRACTS.md` §"Campaign contract" (no period-boundary clause exists) / §"Schema change protocol".
- **Severity:** P3. **Value÷risk:** MEDIUM ÷ negligible (doc-only hardens a validated invariant against future regression).
- **Tag:** **polish** (add the "ANY in-window SELL closes the campaign for the period" rule to `DATA_CONTRACTS.md` §Campaign — doc-only; the in-code A1 note already protects it).
- **Named proof:** none (doc-only); LOCKED April regression already pins the behavior numerically.

---

## tz / period-boundary / ordering re-verification (closed — no new finding)

- **tz interplay:** `report_scheduler.py:169` lookback = `period_start - timedelta(weeks=8)` (8-week, doc corrected A2); query `.gte/.lte("trade_date")` on date strings, `.order("trade_date", desc=False)`. Production passes tz-AWARE bounds (`datetime.now(ISRAEL_TZ)` → `_weekly/_monthly_period`); the Sprint-22 single-point `_to_naive` normalization (`analytics_engine.py:54-57`, mirrored `period_data_probe.py:185-188`) makes both sides tz-naive wall-clock. Verified: provable no-op for naive inputs; covers the WS-B unlinked filter (`:78-79`) and `_get_closed_campaigns` transitively. **No drift.**
- **Ordering:** query orders `trade_date` ascending; `_aggregate_campaigns:417` independently re-sorts `buys` by `trade_date` before `iloc[0]` (first-BUY basis) — the A3 in-code invariant note protects this. First-BUY entry/stop/qty basis is order-robust regardless of query order. **No drift.**
- **NULL `campaign_id` end-to-end:** `_get_closed_campaigns:403 .dropna()` + `engine_core.py:479 .notnull()` silently drop unlinked rows from realized + open book — but this is **honestly disclosed**: WS-B `unlinked_*` (SELL + BUY legs, `analytics_engine.py:74-94`) → `report_renderer._summary_unlinked_lines`/`_summary_unlinked_open_lines` (`:908-936`) → Telegram, AND the read-only probe (`period_data_probe.py:213-230`). Disjoint namespace, never summed into any KPI, gated `count>0`. Re-link is the founder-run manual runbook only; the read flow never mutates Supabase (verified: no `.insert/.update/.upsert/.delete` in any read path; AGENTS.md #4 / DATA_CONTRACTS §"Supabase write contract" intact). **Honest & complete.**
- **Migration integrity:** `verify_migrations==005` exact; 001–005 all `IF NOT EXISTS`/`ADD COLUMN IF NOT EXISTS`, additive, sentinel-UUID-defaulted, each with a matching `rollback_00X.sql`; no destructive DDL; safe to re-run. Only F3 (stale docstring) + F4 (stray `</content>` tag) flagged. **Integrity sound.**

---

## Summary

**P0:** none.
**P1:** F1 — Telegram/degraded-mode summary has NO NAV source/freshness/fallback disclosure; fallback $7,500 NAV drives all R/Expectancy KPIs presented as "authoritative & complete" (CLAUDE.md / DATA_CONTRACTS §NAV rule 2 / AGENTS #1 violation). F2 — `analytics_engine.py:24` never inspects `account["ok"]`/`nav_source` (same root hole, computation side; operationally subsumed by F1).
**P2:** F3 stale `verify_migrations` docstring (polish); F4 stray `</content>` in `005`/`rollback_005` (closure-fix, migration-OUT); F5 NULL `pnl_usd` SELL → silent $0 (latent; addition-OUT).
**P3:** F6 `commission` doc gap (polish); F7 `_get_closed_campaigns` window-contract undocumented (polish).

**Single highest value÷risk data-contract closure:** **F1** — add ONE NAV source/freshness/fallback disclosure line to `report_renderer.build_summary_text` (Telegram + PDF-degraded path), guarded by a dedicated `tests/test_sprint25_nav_disclosure.py` (fallback→token present; broker+fresh→byte-identical regression). HIGH value (closes the only live CLAUDE.md "fallback presented as truth" red-line gap in the data layer) ÷ LOW risk (additive presentation line; zero `analytics_engine.py` change ⇒ Sprint-19 byte-lock, Sprint-22 numbers, and the LOCKED April regression all stay byte-identical). Founder decision required (Telegram-output behavior change).
