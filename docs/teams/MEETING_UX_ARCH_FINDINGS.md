# ARCH — meeting-ux / meeting-fytd findings

**Date:** 2026-05-21 · **Branch:** `claude/review-system-audit-FBZ2h` · **Scope:** 3 commits
`3ac93e8 → fdd4e84 → e9872f8` (F-YTD disclaimer, CLI helper, /portfolio cleanup). DOC-ONLY.

## Headline

The F-YTD disclaimer is correctly additive at the math layer and the UX cleanup is surgically scoped, but `pre_db_realized_pnl_estimate` has been added as a **6th independently-read config field** (5 callers × ad-hoc `account_settings.get(..., 0) or 0`) without a single-source helper — a known F1-class divergence pattern (SPRINT25_ARCH_AUDIT F1) replicated on a brand-new field.

## F1 · 5-way ad-hoc read of `pre_db_realized_pnl_estimate` (no shared resolver)

**Severity:** P1 (latent SSOT violation — exactly the F1/F4 pattern S25 ARCH flagged).

**Evidence (all re-read):** `telegram_portfolio.py:262`, `:680`, `:732` · `dashboard.py:595`, `:626` · `risk_monitor.py:1236` · `report_scheduler.py:321` · `adaptive_risk_engine.py:556,590`. Each site re-inlines `float(<settings>.get("pre_db_realized_pnl_estimate", 0) or 0)` with no helper. Two surfaces (`telegram_portfolio.py:262` vs `:732`) re-read the SAME field twice within ~470 lines of the same module — guaranteed to drift the day someone tweaks coercion (`None`/`""`/string `"0"` semantics).

**Why it matters:** This is the exact triple-divergent-NAV failure mode SPRINT25_ARCH_AUDIT F1 documented for `acc_size = nav_info["nav"] if ... else float(account_settings.get("total_deposited", 7500.0))` — now reproduced for a NEW field BEFORE the original NAV divergence is even closed. The defensive invariant `min(|raw|, |adjusted|)` lives ONLY inside the classifier, but if one call-site silently coerces a non-numeric to `0` and another raises, the user sees inconsistent bands across surfaces with no audit trail.

**Suggested fix (NOT this wave):** add `bot_helpers.get_pre_db_pnl_estimate(account_settings) -> float` (single coercion contract: None / "" / non-numeric ⇒ 0.0 with a structured warning). Route the 5 call-sites + `adaptive_risk_engine.build_risk_raise_gate_ctx` through it. Founder-gateable, parity-test before deletion (the S25 F1 closure recipe).

## F2 · `report_scheduler._compute_risk_rec` duplicates `build_risk_raise_gate_ctx` body

**Severity:** P1 (hidden-coupling / single-source-of-truth violation).

**Evidence:** `report_scheduler.py:312-329` inlines a `gate_ctx = {...}` builder that recomputes `db_net = sum(...)`, `recon_gap = nav - (deposited + db_net)`, calls `_tf.classify_broker_reconciliation(...)`, sets `ctx["recon_band"]` — **byte-identical to `adaptive_risk_engine.build_risk_raise_gate_ctx`** (`adaptive_risk_engine.py:577-596`), which exists explicitly because (per its docstring at `:558-564`) the live callers should "share ONE source of truth for G1 (Clean Data — broker-reconciliation band). Extracted from report_scheduler.py:312-326."  The extraction was meant to delete the duplicate; the duplicate survived.

**Why it matters:** The F-YTD commit (3ac93e8) dutifully added `pre_db_realized_pnl_estimate=` to BOTH the helper AND the duplicate at `report_scheduler.py:321` — proving the team is already paying the duplication cost twice in PRs. Next field added to the G1 gate (e.g. open-PnL inclusion, drawdown bool, an L50-sample term) lands in one site but not the other, and the PDF/weekly report's gate semantics diverge from Telegram's silently — there is no test that compares the two output bands for the same inputs.

**Suggested fix:** `report_scheduler._compute_risk_rec` should call `are.build_risk_raise_gate_ctx(...)` and delete its local body. The `drawdown_active` ctx field is the only argument the report path currently sets independently; verify the helper preserves it (`adaptive_risk_engine.py:555,577`) before deletion.

## F3 · Module-boundary leak: `adaptive_risk_engine` now reaches into `telegram_formatters`

**Severity:** P2 (architectural-boundary inversion already pre-existing, made deeper) — `adaptive_risk_engine.py:579` does `import telegram_formatters as _tf` and calls `_tf.classify_broker_reconciliation(...)`. MODULE_MAP.md:240-250 declares `telegram_formatters.py` as "Pure formatting helpers (no Supabase, no bot, no engine_core)" — and pinned the direction "Callers compute data and pass it in as parameters." This wave's F-YTD-2 extended that lazy-import inside the engine's gate-ctx builder. **Why it matters:** `adaptive_risk_engine` is in the MODULE_MAP's "Core analytical engine" tier; pulling a display module into it makes the dependency graph cyclic in the runtime sense (engine→formatters→...→engine via `compute_adaptive_risk` callers). The classifier is genuinely band-math (5R anchor, units), not formatting — it lives in the wrong module. **Suggested fix:** extract `classify_broker_reconciliation` into a new `recon_classifier.py` (pure, no I/O, no Telegram). Both `telegram_formatters.fmt_broker_reconciliation*` and `adaptive_risk_engine.build_risk_raise_gate_ctx` import from there. Out-of-scope for this wave; flag for the next refactor batch.

## F4 · Anchor instability: `pre_db_pnl_estimate` result key vs `pre_db_realized_pnl_estimate` config key

**Severity:** P2 (convention divergence, mis-grep / mis-read hazard) — config key is `pre_db_realized_pnl_estimate` (used by 5 callers + script + DATA_CONTRACTS.md). Classifier result dict key (`telegram_formatters.py:1042`) is `pre_db_pnl_estimate` — **silently shortened**, dropping `realized_`. Three downstream consumers (`telegram_formatters.py:1067`, `:1159`, the breakdown formatter) read `status.get("pre_db_pnl_estimate", ...)`. **Why it matters:** A future test/consumer that greps `pre_db_realized_pnl_estimate` finds 23 hits; a search for the result key finds 4 — operators investigating "where does this value land?" follow two name trails. Also: the script's `_FIELD_NAME = "pre_db_realized_pnl_estimate"` constant (`scripts/set_pre_db_pnl_estimate.py:60`) is correct for the config but wouldn't help anyone tracing the display surface. **Suggested fix:** rename the result dict key to `pre_db_realized_pnl_estimate` to match the config field everywhere (or add a constant `PRE_DB_PNL_KEY` re-exported by both `telegram_formatters` and the script). Either is mechanical; pick the former for grep-uniformity.

## F5 · `account_state` schema does not know about the new field

**Severity:** P2 (`account_state.py` is SSOT for NAV/account config per MODULE_MAP:55-65 — "single source of truth … all services that need NAV must use `account_state.load()`"). The F-YTD field went straight into `sentinel_config.json` via 5 ad-hoc readers — `account_state.load()` does NOT surface it. Result: the documented SSOT is now lying — there is config state that `load()` callers can't see. The 3 live callers using `account_state.load()` (report_renderer / report_on_demand / `compute_period_analytics`) get NO view of the disclaimer. **Why it matters:** Today nothing breaks because none of those callers use the recon band. Tomorrow, when the weekly-PDF Adaptive-Risk block tries to reflect the same band as Telegram, it'll skip the disclaimer silently. **Suggested fix:** add `pre_db_realized_pnl_estimate` to `account_state.load()`'s returned dict (defaults 0.0); migrate the 5 ad-hoc readers to consume it from there. Pairs naturally with F1.

## F6 · Test surface inconsistency: F-YTD pins ONLY the source-text presence, not propagation

**Severity:** P3 (testing convention diverging from MODULE_MAP) — `tests/test_meeting_fytd_pre_db_history.py:253-267` "Surface wiring" tests do `assert 'pre_db_realized_pnl_estimate' in src` against raw file text for `telegram_portfolio.py`, `dashboard.py`, `risk_monitor.py`, `report_scheduler.py`. That's a grep test, not a propagation test — it can't catch a caller that reads the field and then discards it before the classifier call. The pattern works for "is this wired?" smoke but cannot detect F1/F2 regressions. **Why it matters:** the 5-way drift in F1 will not be caught by any of the new 34 tests. **Suggested fix (not this wave):** add a mock-based test on `build_risk_raise_gate_ctx` that asserts the kwarg actually reaches `classify_broker_reconciliation` — same recipe as S26 F2 / SPRINT28_ARCH parity tests.

## F7 · `fmt_adaptive_risk_block` compact-path anchor relies on emoji-substring detection

**Severity:** P3 (anchor instability) — `telegram_formatters.py:414-417` decides which heat_factors entries to surface in the compact block by `if "⛔" in str(f_line)`. The blocking ⛔ glyph is produced inside `adaptive_risk_engine.compute_adaptive_risk` (heat_factors construction, not in this diff). A future glyph swap (e.g. "🚫" or i18n change) silently empties the compact block to title+headline only. **Why it matters:** This is the founder's exact bug-fix surface — a silent regression here looks identical to "everything is fine, no gates blocking" when actually the block has gone blind. **Suggested fix:** export an `_AR_GATE_BLOCK_PREFIX` constant from `adaptive_risk_engine` and import it in the formatter (or have the gate emit a structured `blocked: bool` flag per factor). Both ends share the constant.

## F8 · Convention divergence: script writes config but `account_state.load()` reads it on a different path

**Severity:** P3 (convention diverging from MODULE_MAP) — `scripts/set_pre_db_pnl_estimate.py:62-66` resolves config path via `SENTINEL_CONFIG_PATH` env-var with fallback `./sentinel_config.json`. `account_state._CONFIG_PATHS` is `["/app/sentinel_config.json", "sentinel_config.json"]` (`account_state.py:26`). `bot_helpers.get_account_settings()` opens hardcoded `"sentinel_config.json"`. `ibkr_sync_runner._CONFIG_PATH = "/app/sentinel_config.json"`. **Why it matters:** Founder runs `python3 scripts/set_pre_db_pnl_estimate.py 495.67` from the host CWD; the bot in the container reads `/app/sentinel_config.json`. Without remembering to set `SENTINEL_CONFIG_PATH=/app/...` or to `docker exec`, the write lands on a stale host file with NO error — operator sees "✅ Updated" and the next `/portfolio` shows zero change. The commit's OPERATOR USAGE note covers it but a misuse fails silently. **Suggested fix:** the script should consult the SAME `_CONFIG_PATHS` list `account_state` uses (import it, or factor a tiny shared resolver). Closes the "two truths about where the file lives" trap.

## Cross-cut convergence

- **UX team** will surface (F7) — the compact block's reliance on glyph anchors is a UX-stability concern too.
- **DATA team** will surface (F4) — the schema field-name divergence between config and result-dict is the kind of contract leak DATA_CONTRACTS.md exists to enforce; the new doc section does not pin the result-dict key name.
- **TESTING team** will surface (F6) — the "src.contains(field_name)" tests pass while real propagation can silently break.
- **OPS team** will surface (F8) and the chat-log "Sentinel Bot מחובר ×6 reconnects 18-21/05" — independent of this wave but worth recording: the path-resolution divergence makes operator config edits a recurring foot-gun. Also the MRVL `missing_data` evaluation (2026-05-19 13:12) is a separate ENGINE concern; no overlap with this wave.

## Architecture invariants preserved

- engine_core / analytics_engine math: UNTOUCHED (verified via `git show --stat`).
- adaptive_risk_engine.py: added ONE kwarg + propagation in `build_risk_raise_gate_ctx`; the math/ladder path (RISK_LADDER, direction logic, `compute_adaptive_risk`) is byte-identical.
- Mark §3 honest disclosure: the cleanup correctly preserved verbose-Mark-§3 wording for the Critical-residual path (`telegram_formatters.py:1098-1110`) and for default/no-adjustment path. AGENTS.md #1 ("must not present fallback/stale data as exact truth") respected: raw gap stays visible in both the compact and the verbose surfaces.
- Default-0 byte-identity: classifier signature additive; `adjustment_applied=False` ⇒ all legacy keys identical (pinned by `TestClassifierSignature.test_default_zero_keeps_legacy_keys_byte_identical`).
- LOCKED-April analytics fixture: untouched (classifier is display-layer).
- Admin gate / secure_runner / docker-compose service wiring: untouched.

## Out-of-scope but flagged

- **NAV-resolution divergence (S25 F1) still open** — this wave added a 6th config field on the SAME ad-hoc-read pattern; the original 3-way `acc_size = ...` drift remains. Strongly recommend founder approves the S25 F1 step-1 closure before another field is grafted on.
- **`engine_core` byte-lock vs the F-YTD gap field** — the raw recon gap is still computed inline at 4+ sites (`telegram_portfolio.py:660`, `dashboard.py:404-405`, `report_scheduler.py:317`, `build_risk_raise_gate_ctx:584`). None of these is the disclaimer's fault, but the disclaimer can never be applied earlier than the gap, and the gap-computation duplication is now load-bearing for the disclaimer too.
- **Adaptive-block VERBOSE path on natural hold** is still 14 lines (`telegram_formatters.py:430-498`) — the founder feedback "מבלבל וארוך" was scoped to the gate-clamped case; natural-hold remains verbose by design (tests TestAdaptiveBlockVerboseOnNaturalHold pin it). Future UX wave may want to revisit but is correctly out-of-scope here.
- **`fmt_broker_reconciliation_breakdown` has only ONE live caller** (`dashboard.py:742`, AI Master Context Export). The Wave-2 refinement (cc656d8 / 4cdedb1) removed it from /portfolio. The breakdown is not dead code (AI export is live), but `telegram_portfolio.py:690-694` carries a stale-feeling comment referencing it — note for next cleanup, not flagged P-level.

## Sign-off

**ARCH lead** · 2026-05-21 · branch `claude/review-system-audit-FBZ2h` HEAD `e9872f8`.
**Suite count (collection):** `pytest --collect-only` failed locally with `ModuleNotFoundError: No module named 'pandas'` (this audit env lacks runtime deps; per commit footers the post-e9872f8 suite is **2564 passed / 1 skipped / 0 failed**, baseline 2552 + 12 new UX-cleanup tests). 109 test files on disk; 2447 `def test_` definitions counted statically.
