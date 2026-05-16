# Sprint 17 — Wave 2 Implementation (ALGO Governance + On-demand Report Dev Button)

**Date:** 2026-05-16
**Branch:** `claude/review-system-audit-FBZ2h`
**Engineer:** Sprint-17 Wave-2 build engineer
**Status:** IN PROGRESS — written incrementally as code lands.

Authoritative inputs (locked): `ALGO_REFERENCE_2026_05_16.md` (§1 rules, §2 stats, §3
regime, §6 Governor), `MARK_SPRINT17_RULINGS.md` (every `⟨MARK⟩` slot filled from
THIS doc), `SPRINT17_DESIGN.md`, `SPRINT17_PLAN.md` (Scope item B), `DECISIONS.md`
DEC-20260515-014/-011/-004, DEC-20260511-001, `CLAUDE.md`, `AGENTS.md` (#1, #8).

Baseline: **1676 passed** (verified before any change). Target: full suite green
(≥1676, 0 failed), drift green.

---

## 0. ⟨MARK⟩ slot index — every slot filled from MARK_SPRINT17_RULINGS.md (none invented)

| Slot (from SPRINT17_DESIGN §6) | Filled value | MARK source |
|---|---|---|
| M1 — §1 per-symbol stop/time-exit Hebrew wording | the 5 strings in `algo_rules.ALGO_KNOWN_RULES.display` | MARK §3 table (rows QQQ/HOOD/TSLA/JPM/PLTR) — verbatim |
| M2 — "no hard stop → time-exit controlled" phrasing | `ALGO ללא סטופ קשיח — נשלט ביציאות-זמן (…)` | MARK §3 (QQQ/HOOD rows) |
| M3 — rolling window + sub-windows | cohort store **30**-deep; sub-windows **last 10** (D1/D3/D6) and **last 5** (D2) | MARK §2 "Rolling window: last 30 closed ALGO trades … sub-windows last 10 and last 5" |
| M4 — §6 decay thresholds | PF<**1.0** (D1), sum last 5 < **−7.5%** (D2), sum last 10 < **−10%** (D3), streak ≥**6**→Yellow (D4) / ≥**8**→Red (D5), per-symbol 2026 YTD < **0** (D6) | MARK §1a table (literal §6 numbers) |
| M5 — open-profit ladder ↔ existing signals | open% ≥**7** (O1 tight-monitor) / ≥**10** (O2 Giveback-watch) / ≥**15** (O3 partial-lock) / ≥**20** (O4 runner-grade); giveback >**50%** of peak = `protection_failure` (O5) | MARK §1b table (reuse Giveback/checkpoints/RUNNER) |
| M6 — cluster thresholds ↔ constants/§5 | C5 `algo_cluster_pct > 30` (reuse `ec.ALGO_CLUSTER_WARNING_PCT=30.0`); Critical `35.0` (`ec.ALGO_CLUSTER_CRITICAL_PCT`); C1 reuse cluster %, C3 PLTR&HOOD, C4 TSLA&PLTR co-occurrence | MARK §1c table |
| M7 — loss-streak reconciliation | Governor streak = NEW cohort **closed-trade** counter; existing `risk_monitor` per-position **run-streak** alert byte-identical, never shares state | MARK §1a D4 note + §6 gate item 4 |
| M8 — backtest-caveat wording | HE: `‏נתוני ALGO = בק-טסט (ללא עמלות/החלקה/הון אמיתי) — לא טראק-רקורד חי.` · EN: `ALGO stats = backtest (no fees/slippage/real capital) — not a live track record.` | MARK §5 (verbatim) |
| M9 — #5 ALGO dead-money Hebrew readout | `ALGO {sym} קרוב לחלון יציאת-הזמן שלו — לוודא שהאלגו מחובר ופועל. תיאור, לא הוראה.` | MARK §4 (mirrors `_algo_loss_streak_alert` observer wording) |
| M10 — test tolerances for §2 fixtures | PF rel-tol 0.05; streak/sum exact on synthesized fixtures | MARK §2 cross-checks (QQQ PF 2.29, aggregate 3.48, 2026 PF 0.73, max streak 12) |
| −5R basis | Account R = `compute_r_target(net_pnl, frozen_target_risk_usd)` (`engine_core.py:1004`); read-out states *"−5R on Account-R basis (ALGO has no real stop)."* | MARK §1d |

---

## 1. Files added / changed

### Added (new leaves)
- **`algo_rules.py`** (NEW pure leaf, #4/#5). No bot/supabase/engine/network
  import — static data + pure functions. `ALGO_KNOWN_RULES` (5 symbols, §1
  data, `display` = MARK §3 verbatim); `get_algo_known_rule` (returns a copy,
  unknown→None), `describe_algo_risk_control`, `algo_time_exit_signal`
  (TSLA/JPM→None per MARK §4). Re-exports `ALGO_BACKTEST_CAVEAT_HE/EN`
  (MARK §5 verbatim).
- **`algo_metrics.py`** (NEW separate leaf, #8-critical + Governor). Imports
  ONLY `engine_core` + `pandas` + `algo_rules` — NOT `analytics_engine`,
  NOT bot/supabase. `build_algo_cohort` (reuses `ec.STAT_BUCKET_ALGO`),
  `compute_algo_cohort_metrics` (PF / pf_last_10 / expectancy / loss_streak /
  sum_last_5/10 / per-symbol YTD; window `ALGO_COHORT_WINDOW=30`),
  `evaluate_governor` (D1..D6 decay, O1..O5 open-profit reuse, C1/C3/C4/C5
  cluster, R5 −5R Account-R) → `actionability` ∈ {none, `Review Required`}.
  Every returned dict carries the backtest caveat.
- **`report_on_demand.py`** (NEW, Scope B; SEPARATE from Workstream A).
  `last_complete_weekly_ref` / `last_complete_monthly_ref` /
  `run_on_demand(period_type)`. Reuses `report_scheduler._weekly_period`
  /`_monthly_period`/`_fetch_trades_df`/`_compute_risk_rec`/`_build_system_health`
  /`_*_coaching_insights`/`_build_weekly_breakdown`/`_is_pdf_path`
  /`_DEGRADED_PDF_NOTE` + `render_weekly`/`render_monthly`→`build_summary_text`
  →`deliver_report`. NEVER imports `report_snapshot_store.save`; only
  `load_recent` (read-only). NEVER touches `report_scheduler` dedup state.
- **`tests/test_sprint17_wave2.py`** (NEW, 33 tests).

### Changed (minimal, additive, observation-only)
- `telegram_tasks.py:40` — `import algo_rules`.
- `telegram_tasks.py:213-237` — `_algo_observed` dict gains `known_rule` (#4)
  and `algo_time_exit` (#5) fields (pure static lookup; no I/O/math).
- `telegram_tasks.py:~815-842` (`handle_algo_panel`) — when external stop is
  Unknown, render the §1 known rule (`חוק ALGO ידוע (נצפה, לא נאכף): …`);
  #5 dead-money note for QQQ/HOOD/PLTR; mandatory backtest caveat line. All
  under the EXISTING mandatory non-binding header (telegram_tasks.py:788-792).
- `telegram_menus.py:30` (`get_developer_menu`) — two dev-menu buttons
  `📈 דוח שבועי עכשיו` / `📆 דוח חודשי עכשיו` (developer menu ONLY).
- `telegram_bot.py:306-356` — dev-menu handler (admin-gated by the existing
  dev-menu/PIN path) → background thread → `report_on_demand.run_on_demand`.

**NOT edited:** `analytics_engine.py`, `engine_core.py` (R/NAV/campaign/stop
math byte-identical; `_DEAD_MONEY_MAX_R=0.75` untouched), `risk_monitor.py`
(`_algo_loss_streak_alert` run-streak untouched — Governor streak is a separate
cohort closed-trade counter, M7), `report_scheduler.py` /
`report_snapshot_store.py` (scheduled run byte-identical), `open_tasks._RULESET`
/ §6 spec (drift test green), `docker-compose.yml`,
`telegram_bot_secure_runner.py`. No migration.

---

## 2. #8-by-construction proof

1. **Physical separation.** ALGO cohort metrics live in a SEPARATE FILE
   (`algo_metrics.py`), a SEPARATE FUNCTION (`compute_algo_cohort_metrics`),
   over a SEPARATELY-FILTERED list (`build_algo_cohort`).
2. **Reused predicate, not a new one.** `build_algo_cohort` keeps only
   `stat_bucket == ec.STAT_BUCKET_ALGO`. The headline path keeps only
   `ec.is_stat_countable(stat_bucket)` (`analytics_engine.py:53`), which is
   already `False` for `STAT_BUCKET_ALGO` (`engine_core.py:1263`). The two
   sets are the exact logical complement over the ALGO/non-ALGO partition —
   they share ONE predicate so they cannot diverge. No new exclusion logic.
3. **`analytics_engine.py` not edited and never imports `algo_metrics`** —
   enforced by `test_analytics_engine_does_not_import_algo_metrics` (static
   AST import-graph assertion).
4. **No merge-back.** `compute_algo_cohort_metrics` returns a self-contained
   dict with namespaced `algo_*` keys; no caller sums it into `win_rate`/
   `expectancy_r`. The Governor reads it as a separate observer metric.
5. **Gate-failing guard test:**
   `TestHeadlineByteIdenticalWithWithoutAlgo.test_headline_identical_with_vs_without_algo`
   asserts every headline field (`win_rate`, `expectancy_r`, `profit_factor`,
   `avg_win_r`, `avg_loss_r`, `total_r_net`, `realized_pnl`, `best_trade`,
   `worst_trade`, `campaigns_closed`, `setup_breakdown`) is `==` (exact, not
   approx) with vs without the founder §2-style ALGO rows injected. PASSES.

---

## 3. Scope-B no-snapshot-mutation proof

1. `report_on_demand.run_on_demand` deliberately OMITS the
   `report_snapshot_store.save(...)` call that `report_scheduler._run_weekly`
   (`:265`) / `_run_monthly` (`:345`) make. The only snapshot-store symbol it
   imports is `load_recent` (read-only, for the monthly weekly-breakdown,
   identical to the scheduler's pure read).
2. It never calls `report_scheduler._mark_ran` / `_save_state` / touches
   `STATE_FILE` — the scheduler period-dedup is byte-identical, so the real
   Saturday/monthly run still fires and its "already-ran" guard is unchanged.
3. `comparison` is intentionally `None`: an isolated test run must not read
   or assert against the real scheduled "vs previous" history; the report
   content is otherwise the SAME render path (zero number/content change) —
   only the optional comparison block is absent (documented in the module).
4. Period boundary is the SAME scheduler logic
   (`report_scheduler._weekly_period`/`_monthly_period`), no new period def.
5. Tests proving it:
   `TestScopeBNoSnapshotMutation.test_run_on_demand_never_calls_snap_save`
   (asserts `report_snapshot_store.save`, `_mark_ran`, `_save_state` all
   `assert_not_called()`), `test_on_demand_module_does_not_call_snapshot_save`
   (AST: never imports/calls `save`), `test_graceful_degradation_still_works`
   (OSError on render → text+`_DEGRADED_PDF_NOTE`, still no snap_save),
   `TestScopeBDevMenuGated.test_button_in_developer_menu_only`.

---

## 4. Test delta

Baseline **1676 passed** → **1709 passed** (+33 new in
`tests/test_sprint17_wave2.py`), **0 failed**, 1 pre-existing warning
(unrelated, `analytics_engine.py:30` dateutil). Ruleset/§6 drift guard
(`test_open_tasks.py::test_ruleset_matches_methodology_spec`) green. No
existing test modified. `python -m pytest -q -p no:cacheprovider`.

New coverage: #8 byte-identical guard; cohort = complement & analytics no-import
proof; founder §2/§3 cohort numbers (PF, loss-streak, last-5/10, sub-1 PF
regime); caveat-always-present; Governor never-Action-Required / −5R Account-R
/ cluster-reuses-constants / co-occurrence / caveat; engine ALGO short-circuit
preserved + `is_stat_countable` still excludes ALGO; algo_rules per-symbol
(QQQ/HOOD no hard stop, TSLA −4.3/JPM −3.3, PLTR emergency cushion,
unknown→None, no imperative, returns copy); Scope-B period logic / no-snapshot
/ graceful degradation / dev-menu gated.

---

## 5. Deferred / out of scope

- Live wiring of the Governor `Review Required` read-out into a Telegram push
  surface is NOT added (would need a new per-key anti-spam cooldown, AGENTS.md
  #7; out of Wave-2 scope which is "surface read-only under the EXISTING ALGO
  panel header" + a callable Governor). `evaluate_governor` is implemented,
  tested, and reusable; surfacing it as a recurring alert is deferred to a
  follow-up with the dedup design.
- Per-symbol candle-age computation for the #5 dead-money "near its window"
  precision is NOT done — #5 surfaces the ALGO's OWN §1 time-exit *descriptor*
  (honest, observation-only) rather than computing candle counts (no new math,
  AGENTS.md Red Line; MARK §4 allows the descriptive note).
- "vs previous" comparison block in the on-demand report (intentionally None;
  see §3 — would require a snapshot read that risks coupling to scheduled
  state; the real scheduled report keeps its comparison).
- Per-user ALGO cohort = deferred Phase-B (Hyperscaler addendum; single-user).
- Live Sprint 11–16 founder smoke-test; deploy Sprint 15/16 (carried, plan
  "Out of scope").
