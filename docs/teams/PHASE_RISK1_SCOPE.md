# Phase RISK-1 — SCOPE / איפיון — at-entry locked-immutable planned-risk baseline (forward-capture wizard + legacy-backfill + single-source formatter across 3 surfaces + ratio-verdict)

**Status.** SCOPE / איפיון (DOC-ONLY). Branch `claude/review-system-audit-FBZ2h`, HEAD `79b2ce8`, suite `2347/0` cov `73.04%`. Governs sub-phases RISK-1a … RISK-1f. No code change in this commit. Founder-locked contract re-stated below; open decisions §4 must be founder-resolved before RISK-1b starts.

## STOP-now items at the top (read these first)

- **(S1)** `engine_core.py` is under a HARD byte-lock guard (`tests/_byte_lock_baselines/engine_core.py.baseline` + `tests/test_sprint25_byte_lock_redteam.py:46`). RISK-1f (changing `compute_initial_risk_metrics` thresholds + `evaluate_position_engine`'s `sizing_status` block at `engine_core.py:435-440`) cannot proceed without a founder-authorized baseline re-bless commit. Precedent: NavUnify re-blessed it under explicit founder gating. RISK-1d is intentionally designed to land BEFORE RISK-1f so the dashboard/Telegram fix lands without touching the byte-lock.
- **(S2)** The LOCKED April regression (`tests/test_real_data_april_regression.py`, byte-locked at `tests/_byte_lock_baselines/test_real_data_april_regression.py.baseline`) goes through `analytics_engine.compute_period_analytics` — NOT through `compute_initial_risk_metrics` / `sizing_status` / `evaluate_position_engine`. Grep confirms: zero references to those names in that fixture's code path. Therefore the at-entry-risk fix is safe vs LOCKED April by construction — the verdict change in RISK-1f does not enter April PF / WR / +$180.49 / 8-countable. Still PINNED by an explicit RISK-1 test that re-runs April after each sub-phase.
- **(S3)** There is no separate Telegram "position-open wizard" today. Positions are imported from IBKR Flex by `main.py` → `ibkr_sync_runner.py`; the founder fills missing fields via `telegram_backlog.get_next_missing()` (the journal-completion flow). The contract's "NEW wizard step immediately AFTER the stop is entered" slots into `telegram_bot.py:752-762` (the `action == 'initial_stop'` text handler that writes `initial_stop`/`stop_loss` and calls `get_next_missing(chat_id)`). RISK-1b designs this as a SURGICAL insertion only — CLAUDE.md "no wholesale rewrite of telegram_bot.py" honored.
- **(S4 — same-defect-class finding outside RISK-1 scope)** `risk_monitor.py:1093-1099` has the EXACT same defect: `_sizing_ratio = original_campaign_risk / target_risk_usd; if _sizing_ratio < SIZING_LEAK_THRESHOLD`. A band-aid `_in_post_raise_settle` carve-out exists already with the comment "retroactively flagged because the user raised their risk level" — i.e., the system already recognises this bug class and patches one specific case. Proposed RISK-2 follow-up (separate high-risk module, separate phase) — see §4 #7.

## 1. Diagnosis recap

The dashboard risk card (`dashboard.py:1105-1114`) and AI Master Context Export (`dashboard.py:1548, 1573`) compute "תכנון" as `target_risk_usd = current_acc_size × risk_pct_input/100` (`dashboard.py:130`) — an account-global figure that retroactively moves with NAV/risk-% changes. The Minervini verdict at `engine_core.py:654-677` uses `risk_pct = risk_usd/nav*100` thresholds against today's NAV — same defect. "בפועל $" `(base_price-init_sl)*base_qty` is correct/immutable, but "בפועל %" divides by current NAV (`dashboard.py:226` passes `_acc_size`). Founder example MRVL: planned-at-entry ~$40/0.5% → today displays "תכנון $47 (0.6%) | בפועל $19 | -59.2% | 📉 קטן מדי" — nonsensical against the original plan. Fix: store immutable at-entry baselines; single-source formatter across 3 surfaces; ratio-verdict `actual/planned_at_entry`.

## 2. Phase decomposition — six small governed sub-phases

Each sub-phase is independently deployable, individually rollback-able, ≤ 1 day. STOP conditions are inviolable per CLAUDE.md.

### RISK-1a — schema additive migration + repository methods (ZERO behavior change)
- **Goal.** Add immutable at-entry columns to `trades`; add repo write helpers (not yet called from production paths).
- **Permitted-diff allowlist.** NEW `migrations/006_at_entry_risk_baseline.sql`, NEW `migrations/rollback_006.sql`, `supabase_repository.py` (append helpers only), `docs/DATA_CONTRACTS.md` (Trade row contract: list the four new fields + NULL semantics).
- **Byte-locked set (git-diff EMPTY).** `engine_core.py`, `analytics_engine.py`, `period_data_probe.py`, `adaptive_risk_engine.py`, `risk_monitor.py`, `telegram_bot.py`, `telegram_portfolio.py`, `telegram_formatters.py`, `dashboard.py`, `algo_*`, `telegram_bot_secure_runner.py`, `docker-compose.yml`, `templates/*`, `tests/test_real_data_april_regression.py`, all `tests/_byte_lock_baselines/*`.
- **STOP.** Any read/write of the new columns from non-migration code (must wait for RISK-1b). Any change to existing trade columns. Any Supabase mutation from a read-only path.
- **Success.** Migration applies + rolls back idempotently on sandbox Supabase; `verify_migrations.py` passes; suite green; column `is_nullable=YES`.
- **Tests delta.** +2 (migration apply/rollback + NULL semantics doc test). Suite: 2347 → 2349.
- **Risk class.** Low (additive schema only).

### RISK-1b — NEW wizard "after-stop" step in journal-completion flow (FORWARD CAPTURE)
- **Goal.** After `telegram_bot.py:752-762` writes `initial_stop`/`stop_loss`, compute a *suggested* planned-risk $/% from `(base_price-stop)*base_qty` and current NAV × risk-%, then send ONE confirm/edit message. On confirm/edit: WRITE `{nav_at_entry, planned_risk_usd_at_entry, planned_risk_pct_at_entry, risk_target_pct_at_entry}` to the trade row, locked-immutable. Existing `initial_stop`/`stop_loss` write is byte-identical — the wizard step is appended AFTER it. On skip/cancel: leave the four columns NULL (legacy / pre-fix marker; the position appears in the RISK-1c banner).
- **Permitted-diff allowlist.** `telegram_bot.py` (SURGICAL insertion of one new state branch `action='at_entry_confirm'`), `telegram_backlog.py` (one "is at_entry baseline missing?" check before completion-done), `supabase_repository.py` (call site for the helper added in RISK-1a; idempotent UPDATE — overwrites only when columns are NULL). NEW pure helper module `risk_lifecycle.py` (just `compute_at_entry_suggested(base_price, stop, qty, nav, risk_pct)` — no I/O; RISK-1d later adds the formatter to the same module).
- **Byte-locked set.** `engine_core.py`, `dashboard.py`, `telegram_portfolio.py`, `analytics_engine.py`, `adaptive_risk_engine.py`, `risk_monitor.py`, `telegram_formatters.py`, `algo_*`, baselines.
- **STOP.** Any change to existing message text byte-pattern for stop-entry / journal flow; any auto-write of the four columns from a non-confirm path; any per-position write to a row that already has the columns non-NULL (immutability inviolable except via §4 #4 founder-correction flow).
- **Success.** Founder confirms a new position → row in Supabase shows the four columns populated; founder skips → NULL; existing journal-completion path unaffected when no stop is typed; admin-protection unchanged (`telegram_bot_secure_runner.py` byte-identical).
- **Tests delta.** +8 (state-machine ask→confirm→write; ask→edit-pct→derive-nav→write; ask→edit-usd→write; ask→cancel→NULL; idempotent re-entry guard; ALGO positions skip the step (ALGO ⇒ `initial_stop=-1` sentinel); NO existing journal-completion text byte-modified; admin-protection regression). Suite: 2349 → 2357.
- **Risk class.** Medium (new Supabase write path; CLAUDE.md hard constraint "no wholesale rewrite of telegram_bot.py" honored by surgical insertion only).

### RISK-1c — legacy-backfill banner + handler (LEGACY CAPTURE — same wizard step per pre-fix open position)
- **Goal.** On every open position whose four at-entry columns are NULL: surface a banner ("⚠️ X פוזיציות-פתוחות דורשות אימות at-entry") across surfaces; tapping the banner per-position triggers the SAME RISK-1b confirm/edit wizard step. On save the columns are written locked-immutable. After backfill the banner disappears.
- **Permitted-diff allowlist.** `dashboard.py` (banner near top of Command Center tab + per-position card "אמת at-entry" link), `telegram_bot.py` (new menu entry "⚠️ אמת at-entry — X פוזיציות" that walks the founder through legacy backfill one position at a time via the RISK-1b flow), `risk_lifecycle.py` (count-of-null helper), `supabase_repository.py` (read-only query: open positions with NULL nav_at_entry).
- **Byte-locked set.** Same as RISK-1b plus `risk_monitor.py` (banner is display-only; no recurring alert — CLAUDE.md anti-spam invariant).
- **STOP.** Any recurring alert without per-position dedup flag. Any auto-fill of legacy columns from current NAV / current risk-% (this is exactly the bug). Banner suppression honest-empty: 0 open positions ⇒ banner hidden, NOT a wrong number.
- **Success.** MRVL example: clicking banner opens the SAME wizard, shows engine-suggested $40/0.5% from `(base_price-init_sl)*base_qty` plus current NAV (with clear "אומדן בהתבסס על נתוני היום — אמת מול הרישומים המקוריים שלך"); founder edits to originally-planned values; columns become non-NULL; banner count decrements; dashboard risk card shows the corrected verdict via the RISK-1d formatter.
- **Tests delta.** +6 (banner show/hide; per-position walk-through; immutable-once-set; no recurring alert; no fallback fabrication; dashboard banner element honest). Suite: 2357 → 2363.
- **Risk class.** Medium (Supabase writes + UX state machine across 2 surfaces; no math change).

### RISK-1d — single-source formatter + dashboard refactor (CONSUMES locked at-entry data; NULL = pre-fix marker)
- **Goal.** Add `risk_lifecycle.format_planned_vs_actual_block(...)` to `risk_lifecycle.py`. Both dashboard surfaces (risk card + AI Master Context Export HTML block) call this ONE formatter with the SAME inputs (anti-drift; cross-surface byte-identity — mirrors `algo_divergence.format_symbol_divergence_line` / `position_lifecycle.format_units_lifecycle`).
- **Permitted-diff allowlist.** `risk_lifecycle.py` (add `format_planned_vs_actual_block` — pure, no I/O, no engine, no Supabase, no telebot), `dashboard.py:1105-1114` (replace inline render with single formatter call), `dashboard.py:1573` (replace inline HTML block with single formatter call routed through the same helper, `ai_copy=True` mode).
- **Byte-locked set.** `engine_core.py`, `telegram_*.py`, `analytics_engine.py`, `risk_monitor.py`, baselines, LOCKED April.
- **NULL back-compat rule (load-bearing).** Any of the four at-entry columns NULL ⇒ formatter returns honest pre-fix marker: `‏⚠️ at-entry טרם אומת — לא ניתן להציג שיפוט (ראה באנר אימות)`. NEVER a fabricated number (AGENTS.md — absence ≠ data). "בפועל $" (`InitRisk_USD`) can still render (correct + immutable), but the planned/% and verdict are gated behind non-NULL `nav_at_entry`.
- **STOP.** Any change to "בפועל $" math (already correct/immutable per founder contract #4). Any read of current NAV in the formatter (the whole point is to NOT use current NAV).
- **Success.** MRVL with backfilled $40/0.5% nav_at_entry=$8,000: dashboard risk card shows "תכנון $40 (0.5%) | בפועל $19 (0.24%) | -52% | 📉 קטן מדי" — verdict from RISK-1f (or, if RISK-1f hasn't shipped yet, an interim RISK-1d ratio-aware label that the formatter renders directly; see §4 #1).
- **Tests delta.** +12 (cross-surface byte-identity 2 surfaces; NULL pre-fix marker; valid-data shape; ratio computation idempotent; ai_copy vs html modes byte-different but data-identical; no fabricated number on missing data; formatter never raises; import purity). Suite: 2363 → 2375.
- **Risk class.** Medium (display-layer only; ZERO engine math change).

### RISK-1e — NEW Telegram per-position risk block via the same single-source formatter
- **Goal.** Add ONE new block to `telegram_portfolio.py` non-ALGO discretionary card. Emitted by the SAME `risk_lifecycle.format_planned_vs_actual_block` ⇒ byte-identical content to the dashboard risk card (cross-surface anti-drift; 3 surfaces now).
- **Permitted-diff allowlist.** `telegram_portfolio.py` (insertion of ONE block per non-ALGO position), `risk_lifecycle.py` (no change — formatter shipped in RISK-1d).
- **Byte-locked set.** All others including `telegram_bot.py`, `engine_core.py`, baselines.
- **STOP.** Adding a per-position block to ALGO positions (observe-only — DEC-20260511-001). Adding the block to any push/alert flow (read-only on pull surfaces only — `/portfolio`). Display-only string change must not alter R/NAV/exposure math (REPORT-2 precedent).
- **Success.** `/portfolio` shows the new block on each non-ALGO position; identical text to the dashboard risk card (per-symbol byte-identity test); ALGO cards unchanged; admin-protection unchanged.
- **Tests delta.** +6 (telegram-card byte-identity vs dashboard; ALGO carve-out; never-fires-on-NULL; no fabricated number; never-replaces existing R numbers; 3-surface byte-identity test). Suite: 2375 → 2381.
- **Risk class.** Medium (Telegram UX surface; surgical addition only).

### RISK-1f — engine verdict ratio-thresholds (REPLACES absolute-%-of-NAV at `engine_core.py:654-677`; mirror `:435-440`)
- **Goal.** Founder contract #5: ratio = `actual_remaining_usd / planned_risk_usd_at_entry` → `<50%` ⇒ "📉 קטן מדי" / `50%–150%` ⇒ "✅ תקין" / `>150%` ⇒ "🔥 גדול מדי". Wrap behind a `mode` kwarg: `mode='live'` (new ratio-verdict; consumed by RISK-1d/1e formatter) and `mode='historical'` (existing absolute-% logic preserved verbatim; consumed by LOCKED-April / backtest paths). Default: `mode='historical'` (no behavior change for any existing caller unless it opts in).
- **Permitted-diff allowlist.** `engine_core.py` (SURGICAL: add `mode` kwarg, default historical; new ratio-verdict branch reads `planned_risk_usd_at_entry` from a NEW kwarg, never re-derives from current NAV), `tests/_byte_lock_baselines/engine_core.py.baseline` (founder-authorized re-bless, parent-verified, NavUnify precedent), `risk_lifecycle.py` formatter (now calls engine in `mode='live'` with locked planned), `risk_monitor.py:163, 858, 1099` (continues to receive `sizing_status` byte-identically — confirmed by test).
- **Byte-locked set.** All other files; LOCKED April byte-identical.
- **STOP.** Any thread that passes non-NULL `planned_risk_usd_at_entry` into `mode='historical'`. Any change to `sizing_status` string the `risk_monitor.py:1099` `SIZING_LEAK_THRESHOLD=0.65` check depends on (different semantics from this verdict; the two MUST stay independent).
- **Success.** LOCKED-April byte-identical (April never sets `mode='live'`); MRVL example resolves to "📉 קטן מדי" via ratio `$19/$40=0.475 < 0.50`; founder-corrected MRVL with planned $40 actual $25 ⇒ ratio 0.625 ⇒ "✅ תקין"; `risk_monitor.py` Sizing Leak alert unchanged.
- **Tests delta.** +10 (ratio thresholds at boundaries 0.499/0.500/0.501/1.499/1.500/1.501; mode='historical' byte-identical to today; mode='live' new behavior; LOCKED-April byte-identical; risk_monitor SIZING_LEAK_THRESHOLD path unchanged; baseline re-bless audited). Suite: 2381 → 2391.
- **Risk class.** High (engine math change + byte-lock re-bless; CLAUDE.md "do not change R/NAV/exposure/campaign math without tests" honored by the mode-flag carve-out + LOCKED April + ratio-threshold tests).

## 3. Cross-team responsibility map

- **DB-team.** Extend `trades` table (NOT a new table — data is 1-to-1 with the campaign's first BUY lot; separate table would force JOIN on every read in the risk card / Telegram block / AI export). Migration `migrations/006_at_entry_risk_baseline.sql`:

  ```sql
  ALTER TABLE trades ADD COLUMN nav_at_entry NUMERIC NULL;
  ALTER TABLE trades ADD COLUMN planned_risk_usd_at_entry NUMERIC NULL;
  ALTER TABLE trades ADD COLUMN planned_risk_pct_at_entry NUMERIC NULL;
  ALTER TABLE trades ADD COLUMN risk_target_pct_at_entry NUMERIC NULL;
  ```

  NULL ⇒ "pre-fix / awaiting backfill". Forward-compat: any prior reader doing `row.get('nav_at_entry')` gets None. Rollback drops the four columns (no other table references them, safe). Update `docs/DATA_CONTRACTS.md` "Trade row contract" + new "At-entry risk baseline contract" section.

- **Telegram-team.** RISK-1b insertion point: `telegram_bot.py:752-762` (`action == 'initial_stop'` branch). After `repo.update_trade(...)` and BEFORE `get_next_missing(chat_id)`, push the new `at_entry_confirm` state. Hebrew text (FOUNDER REVIEW — §4 #2):

  > 🛡️ *גיבוי תכנון סיכון (לכניסה זו)*
  > *סטופ:* `${stop}`  *|*  *כניסה:* `${entry}`  *|*  *כמות:* `{qty}`
  > תכנון מחושב: **${planned_usd:.0f}** (≈ {planned_pct:.2f}% × NAV ${nav:,.0f})
  > ✅ אמת — נעל כתכנון הקבוע לפוזיציה זו
  > ✏️ ערוך — הזן את הסכום שתכננת בפועל ($)
  > ❌ דלג — תופיע באנר אימות

  Three inline buttons: `at_entry|confirm|{trade_id}`, `at_entry|edit_usd|{trade_id}`, `at_entry|skip|{trade_id}`. Edit path reuses the numeric-input flow.

  New per-position Telegram risk block (RISK-1e — same Hebrew as RISK-1d dashboard formatter for byte-identity):

  > ⚖️ *סיכון:* תכנון `${planned}` ({planned_pct:.2f}%) · בפועל `${actual}` ({actual_pct:.2f}%) · {ratio_pct:+.0f}% · {verdict_emoji}

  Backlog banner UX in Telegram: dedicated menu entry under the developer/operator menu — NOT a push alert (anti-spam).

- **Dashboard-team.** Refactor `dashboard.py:1105-1114` and `dashboard.py:1573` to one shared call into `risk_lifecycle.format_planned_vs_actual_block(...)`. Add banner at top of `Command Center` tab when `count_open_with_null_at_entry > 0` (legacy-backfill prompt — same wizard step in a modal). Pre-fix marker for NULL nav_at_entry: render `‏⚠️ at-entry טרם אומת` instead of a wrong number.

- **Engine-team.** RISK-1f `compute_initial_risk_metrics(base_price, initial_stop, base_qty, nav, *, mode='historical', planned_at_entry_usd=None)`. `mode='live'` requires `planned_at_entry_usd` non-None; ratio = `(base_price-initial_stop)*base_qty / planned_at_entry_usd`; thresholds 0.5/1.5. `mode='historical'` (default) keeps absolute-%-of-NAV behavior verbatim. `evaluate_position_engine` `sizing_status` block at `:435-440` is parallel logic — wrap with the same mode flag.

  **Recommended LOCKED-April back-compat path:** Option A (mode-flag carve-out) — `mode='historical'` default + ALL existing callers untouched + ONLY `risk_lifecycle.format_planned_vs_actual_block` opts into `mode='live'`. April fixture goes through `compute_period_analytics`, which does NOT call `compute_initial_risk_metrics` (verified by grep); even if it did, default-historical keeps it byte-identical. Option B (re-bless April under new thresholds) — REJECTED: April has no `nav_at_entry` data → all positions would render pre-fix marker → byte-locked fixture changes shape. Founder confirm A.

- **Tests-team.** New test file `tests/test_phase_risk1.py` with ~11 classes. Cross-surface byte-identity 3-surface test (mirrors REPORT-3.1). Ratio-verdict thresholds: exhaustive boundaries. `mode='historical'` byte-identity vs current behavior. LOCKED-April byte-identical after each sub-phase. Schema migration apply+rollback. Wizard-step state machine: ask→confirm/edit/skip. Backfill banner state machine. Suite expectations cumulative: RISK-1a 2349, RISK-1b 2357, RISK-1c 2363, RISK-1d 2375, RISK-1e 2381, RISK-1f 2391. Coverage ≥ 67% throughout.

- **DevOps-team.** Deploy order per sub-phase: RISK-1a apply migration BEFORE deploying any code that reads new columns (migration-only phase). `bash scripts/apply_migration.sh migrations/006_at_entry_risk_baseline.sql`. Rollback: `rollback_006.sql`. RISK-1b: rebuild `telegram-bot` only. RISK-1c: rebuild `telegram-bot` + `dashboard`. RISK-1d: rebuild `dashboard` only. RISK-1e: rebuild `telegram-bot` only. RISK-1f: rebuild ALL of `dashboard`, `telegram-bot`, `risk-monitor`, `sentinel-bot` (engine_core.py touch ripples). Post-deploy verification: open a position via IBKR sync → walk wizard → confirm row in Supabase → check dashboard/Telegram show the new block consistently → re-verify legacy MRVL shows pre-fix marker/banner.

## 4. Open decisions still needing founder input (DO NOT decide unilaterally)

1. **LOCKED-April back-compat path** — Option A (mode-flag carve-out, recommended) vs Option B (re-bless April baseline — rejected).
2. **Hebrew text for the wizard step, the per-position Telegram block, and the backfill banner** — drafted in §3. Founder review for tone/brevity/RTL friendliness.
3. **Edit semantics in wizard** — founder edits planned $ → does system back-derive `planned_pct = planned_usd/nav*100` only, or also allow editing % directly (and back-derive implied at-entry NAV)? Recommendation: $-only edit (single-input; % is computed).
4. **Founder-correction of an already-locked at-entry value** — once non-NULL, can the founder re-edit? Recommendation: yes via a dedicated `/at_entry_correct {symbol}` admin command that ALSO writes an `audit_log` row (defense-in-depth — `audit_logger.py` exists). Without a correction path, a mistyped value is locked forever.
5. **Telegram per-position block: always show, or only on divergence?** Recommendation: always show on non-ALGO discretionary positions (matches REPORT-2 / dashboard parity). Alternative: show only when `|ratio-1.0| > 0.50`.
6. **Wizard skip vs block** — if founder cancels / times out, does the position open with NULL at-entry (pre-fix marker + banner)? Or is position-open BLOCKED until completed? Recommendation: allow skip → NULL → banner (consistent with `telegram_backlog.py:107-108` "⏭️ דילוג / ללא סטופ" precedent). Blocking risks losing the trade entirely on a transient Telegram outage.
7. **risk_monitor.py SIZING_LEAK_THRESHOLD interaction** — `risk_monitor.py:1099` uses `original_campaign_risk / target_risk_usd < 0.65` (current target_risk_usd; same defect class — band-aid `_in_post_raise_settle` already exists in `risk_monitor.py:1093` proving the founder previously hit this). Recommendation: carve out to RISK-2 follow-up (out of RISK-1 scope; touches separate fragile module). Founder confirm carve-out.

## 5. Test strategy

- **Cross-surface byte-identity (3 surfaces, anti-drift).** Per-symbol input → assert `format_planned_vs_actual_block(...)` output substring appears verbatim in dashboard risk-card render, AI Master Context Export HTML, Telegram per-position card. Pattern: REPORT-3.1 `test_phase_report3.py:684-691` + REPORT-2 dual-surface.
- **Anti-drift via AST grep.** ZERO inline re-implementation of `planned_at_entry` / `actual` / `ratio` / `verdict` outside `risk_lifecycle.format_planned_vs_actual_block`. `ast.walk` on `dashboard.py` + `telegram_portfolio.py` post-RISK-1d/1e asserts no occurrence of the bare arithmetic.
- **Ratio-verdict math + thresholds (RISK-1f).** Boundary table at 0.499/0.500/0.501/1.499/1.500/1.501. Determinism: same inputs → same output across 1000 calls.
- **Schema migration.** Apply on sandbox; assert columns exist & NULL; insert synthetic row with the four columns populated; rollback; assert columns vanish; no other table dropped.
- **Wizard-step flow.** State machine: stop-entry → confirm → row updated; stop-entry → edit-usd → numeric-input → row updated; stop-entry → skip → row NULL; ALGO position (`initial_stop=-1` sentinel) bypasses the wizard.
- **Backfill banner.** Count-show-hide; per-position walk-through writes only NULL columns; no recurring alert from `risk_monitor.py`.
- **LOCKED-April protection.** Re-run `tests/test_real_data_april_regression.py` byte-identically after each sub-phase. April 8-countable / +$180.49 / PF 2.6262 / WR .375 / excl 2 byte-unchanged.
- **CI suite count expectations.** Cumulative after RISK-1f: 2391/0 (current 2347 + 44 additive). Coverage ≥ 67% throughout (current 73.04% — additive tests raise floor).

## 6. Risk register (per sub-phase, against CLAUDE.md + AGENTS.md HARD constraints)

| Phase  | Worst case                                                                                          | Detection post-deploy                                                                                | HARD line honored                                                                  |
|--------|-----------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------|
| RISK-1a| Migration partially applied; columns exist in one env, not another                                  | `verify_migrations.py`; `SELECT column_name FROM information_schema.columns` smoke check             | Updates DATA_CONTRACTS.md                                                          |
| RISK-1b| Founder confirms wizard but Supabase write fails silently → row NULL at-entry → reads show pre-fix  | Telegram ack message includes the four written values verbatim; row recently written re-displayed    | No bypass of `telegram_bot_secure_runner.py`; no wholesale rewrite of telegram_bot.py |
| RISK-1c| Banner click loops or fails to walk through all legacy positions                                    | Banner count decrements per save; explicit completion message; backlog state machine modeled on `telegram_backlog.get_next_missing()` precedent | Anti-spam (no recurring alert); admin-only via secure runner                       |
| RISK-1d| Dashboard surfaces drift between risk card & AI export — exactly the bug class this phase prevents  | Cross-surface byte-identity test + AST anti-inlining test; visual check after deploy                 | "Do not silently present fallback data as truth" — pre-fix marker explicit         |
| RISK-1e| Telegram block shows a fabricated number when at-entry is NULL                                      | Pre-fix marker rendered honestly; test asserts NEVER renders numeric verdict on NULL data            | Hebrew RTL readability; no misleading precision                                    |
| RISK-1f| Byte-lock baseline re-bless reviewed under wrong commit → engine math drifts unnoticed              | Founder-authorized re-bless commit isolates diff to thresholds + mode-flag carve-out; LOCKED April re-runs byte-identically; risk_monitor SIZING_LEAK unaffected | "Do not change R/NAV/exposure/campaign math without tests" — mode-flag carve-out + new tests |

## 7. Deploy plan (per sub-phase)

| Phase  | Rebuilds                                                | Single deploy command                                       | Rollback                                                                  | Observable verification                                                  |
|--------|---------------------------------------------------------|-------------------------------------------------------------|---------------------------------------------------------------------------|--------------------------------------------------------------------------|
| RISK-1a| none (DB only)                                          | `bash scripts/apply_migration.sh migrations/006_at_entry_risk_baseline.sql` | `bash scripts/apply_migration.sh migrations/rollback_006.sql`             | columns exist; existing reads unaffected                                 |
| RISK-1b| `telegram-bot`                                          | `docker compose up -d --build telegram-bot`                 | `git revert {sha}; docker compose up -d --build telegram-bot`             | open a sync'd position, walk wizard, verify row in Supabase              |
| RISK-1c| `telegram-bot` + `dashboard`                            | `docker compose up -d --build telegram-bot dashboard`       | `git revert {sha}; docker compose up -d --build telegram-bot dashboard`   | banner shows for MRVL; click walks to wizard; counter decrements         |
| RISK-1d| `dashboard`                                             | `docker compose up -d --build dashboard`                    | `git revert {sha}; docker compose up -d --build dashboard`                | risk card + AI export show byte-identical block; pre-fix marker on NULL  |
| RISK-1e| `telegram-bot`                                          | `docker compose up -d --build telegram-bot`                 | `git revert {sha}; docker compose up -d --build telegram-bot`             | `/portfolio` block byte-identical to dashboard risk-card                 |
| RISK-1f| `dashboard`+`telegram-bot`+`risk-monitor`+`sentinel-bot`| `docker compose up -d --build`                              | `git revert {sha}; restore engine_core.py.baseline; docker compose up -d --build` | LOCKED April still byte-identical; MRVL verdict resolves correctly       |

## 8. Recommendation to founder

Start with **RISK-1a** — pure additive schema migration, zero behavior change, zero code path touched, unlocks every downstream sub-phase. Estimated total scope: 6 sub-phases × ≤1 day each ≈ 1 working week with parent-verified gates between each sub-phase. The ordering (1a → 1b → 1c → 1d → 1e → 1f) lets each sub-phase ship independently — even RISK-1f, the only high-risk one (touching byte-locked `engine_core.py`), can be deferred indefinitely behind the mode-flag without blocking the founder's daily UX fix (RISK-1d delivers the corrected dashboard immediately once 1a/1b/1c are in place). Before RISK-1b starts, please resolve the §4 open-decisions table — especially #1 (LOCKED-April A/B), #4 (re-edit + audit-log), #6 (skip vs block), #7 (`risk_monitor.py` SIZING_LEAK carve-out → RISK-2).
