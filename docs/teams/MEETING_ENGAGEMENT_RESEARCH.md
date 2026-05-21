# MEETING_ENGAGEMENT_RESEARCH — Sentinel's Unique Data-Asset Inventory

> RESEARCH-TEAM artifact. Engagement-phase meeting, 21/05/2026.
> Read-only. Pre-condition input for the 4 ideation agents (E1 Behavioral / E2 Psychology / E3 Hebrew Copy / E4 Narrative) and the UX/Mark synthesis.
> Methodology: code-walk + chat-log evidence + the seven `MEETING_UX_*_FINDINGS.md` reports from the 21/05/2026 review.

## Headline finding — the Sentinel wedge

**Sentinel's truly defensible surface is its longitudinal record of *this specific founder's relationship with this specific risk methodology*** — not market data, not strategy heuristics, not generic edge math. Three asset categories the rest of the world cannot reproduce:

1. **Decision provenance** — every adaptive-risk rec, every confirm/reject (with operator-typed reason), every 4-gate refusal of a raise, every position-state transition (incl. ALGO suppression), every locked at-entry price and every backfill. Captured in `risk_journal.json`, `risk_recommendations.json`, `audit_log` (Supabase), `risk_monitor_state.json`.
2. **Sizing-truth** — `target_risk_usd` vs `original_campaign_risk` per campaign, with the cent-rounded R denominator (engine_core.py:967) that defines every R he has ever booked. The MRVL 0.41x signature is one row in a 9-month rolling truth.
3. **Multi-window heat math** — S9/M21/L50 disc-only Win-Rate + Payoff + PF + streaks, weighted, with the 4-gate veto on raises and the drawdown auto-cut floor. Sentinel computes this hourly; the founder cannot retain it cognitively.

Everything UX/Mark builds in the engagement phase should draw from these three. Market data is Tier 2 — necessary scaffolding, not the wedge.

---

## Tier 1 — Sentinel-only data assets (15)

### T1.1 — Risk-Journal (every confirmed / rejected risk-pct recommendation)

- **Where it lives** — Engine: `adaptive_risk_engine.py:109-131` (`log_risk_journal`). Storage: `risk_journal.json` (500-row FIFO cap, `:126`). Schema: `{ts, direction, current_risk_pct, recommended_risk_pct, action, reason, actual_pct_set}`.
- **Freshness** — On-demand (writes the moment the founder taps confirm/reject in Telegram via `risk_confirm|YES/NO`).
- **Key derivable** — "You rejected 0.85% twice in two minutes on 19/05; the doc-only chat record shows no reason logged either time (`telegram_audit_review.py:41-46` does NOT surface risk_journal — UX-U4 in MEETING_UX_TEAM_MEETING.md)." A 30-day rejection-rate ratio is one `len()` away.
- **Engagement hooks** — (a) Weekly "Rejection Journal" (E2-S4) summarising rejected raises + the 5-day price action of underlying. (b) Reason-typology mirror: count of `"ללא הסבר"` / `"עדיין לא"` decisions (E2-S10 — fires Friday if ≥3). (c) Round-trip dignity: when the founder rejects a raise with a typed reason, surface that exact reason back to him 14 days later with the realized R alongside.

### T1.2 — Adherence Rate (system-rec follow-through)

- **Where it lives** — Engine: `adaptive_risk_engine.py:877-897` (`mark_adherence`), `:900-937` (`compute_adherence_stats`). Storage: `risk_recommendations.json` (200-row cap, `:869`). Each row: `{ts, heat_score, direction, current_risk_pct, recommended_risk_pct, followed, actual_risk_pct, reason}`.
- **Freshness** — Real-time on user response; daily decay via FIFO. Returns `adherence_pct` over evaluated rows.
- **Key derivable** — "Your 30-day adherence is N% — your last 10 actions are `['✅','✅','❌','⏳','❌','✅','✅','✅','❌','✅']` (`compute_adherence_stats` already builds the emoji list at `:919-927`)."
- **Engagement hooks** — (a) Trend-line: adherence improving vs declining month-over-month. (b) Disagreement-type: clusters of consecutive `❌` followed by drawdown — was the founder right? (c) Friction surface: every `❌` with an empty `reason` is a candidate for the meta-cognition prompt (E1-#10 "ללא נימוק" counter).

### T1.3 — 4-Gate Clamp History (the system "saving" the founder)

- **Where it lives** — Engine: `adaptive_risk_engine.py:490-549` (`evaluate_risk_raise_gate`), result keys `{allow_raise, failed:[G1_recon|G2_sample|G3_expectancy|G4_drawdown], reason}`. Emitted into the recommendation dict at `:813-822` (`result["risk_raise_gate"]`). The clamp is then logged into `risk_recommendations.json` via `_log_recommendation` (`:849-874`) with `direction="hold"` even though heat would have said "up". **Important gap:** the rec-log does NOT currently store the 4-gate result distinctly — only the clamped direction. The dollar value of the "save" is not yet stored.
- **Freshness** — Per adaptive-risk evaluation cycle (every Telegram /portfolio + dashboard render + `risk_monitor` proactive alert).
- **Key derivable** — Realized R that would have come from the un-clamped step had the founder taken it (requires retrospective lookup over closed campaigns in the gate window). The data exists; the join is not yet computed.
- **Engagement hooks** — (a) E1-#2 / E2-S6 "Gate Receipt" — show the founder, on a clamp day, what the un-clamped sizing would have lost. (b) "Sentinel saved you 14 days ago" beat — count days since last clamp + the realized outcome. (c) Honest balance: also surface clamp-cost days (when the gate left R on the table) so the mirror is symmetric.

### T1.4 — Per-Campaign `stat_bucket` Distribution + per-bucket WR

- **Where it lives** — Engine: `engine_core.py:1284` (`classify_stat_bucket`), `:1295-1330` (returns `EP_MANUAL / VCP_MANUAL / ALGO_OBSERVED / DATA_INCOMPLETE`). Attached to every closed campaign by `adaptive_risk_engine.py:227-238` (`compute_closed_campaigns`). Stat-countable filter: `engine_core.is_stat_countable()`.
- **Freshness** — Per-cycle (re-derived on every dashboard/Telegram load from raw Supabase rows; no persistent cache).
- **Key derivable** — Win Rate, Expectancy, Profit Factor, Avg Win R, Avg Loss R *per bucket per scope*. Already surfaced in `dashboard.py` Trader Edge Panel (11 metrics × 4 scopes).
- **Engagement hooks** — (a) E1-#5 "Bucket Mirror" — MANUAL-you vs ALGO-you vs DATA_INCOMPLETE-you scoreboard, fires on close. (b) Reclassification correction: tap "this MANUAL was actually a system signal" → reroute to ALGO (UI exists in `telegram_bot.py` backlog flow). (c) Coaching framing: never compare across users, only across founder's own buckets.

### T1.5 — Multi-Window Heat (S9 / M21 / L50)

- **Where it lives** — Engine: `adaptive_risk_engine.py:675-683` (S9/M21/L50 stats + window heat scores), `:683` (weighted base_heat = S9·0.50 + M21·0.30 + L50·0.20), `:711` heat_score with open_r_bonus. `_window_heat_score` at `:345-387` defines the payoff/PF/streak components.
- **Freshness** — On every `compute_adaptive_risk` call (every dashboard render, every `/portfolio`, every `risk_monitor` cycle).
- **Key derivable** — Heat-curve over time (the score itself is logged into `risk_recommendations.json:861` as `heat_score`). The full S9/M21 *divergence* is the most under-used signal — `_build_heat_factors:414` already detects ≥15 pt divergence.
- **Engagement hooks** — (a) Sparkline of `heat_score` over last 90 days. (b) "Your S9 is N pts above M21 — you're heating up" (or below — cooling). (c) E1-#1 "Edge Mirror" — when S9 is positive 4 days in a row, surface what he did the last time that happened.

### T1.6 — Per-Trader R-Distribution (with the cent-rounded denominator)

- **Where it lives** — Engine: `engine_core.py:966-1066` (`compute_original_campaign_risk` — the `round(max(0, risk*qty+fees), 2)` denominator at `:1006` is **deliberately load-bearing** per DATA_CONTRACTS.md F7). Per-campaign R distribution computed via `analytics_engine._aggregate_campaigns` (net_r = net_pnl / orig_risk).
- **Freshness** — Per closed campaign (one new R sample on each campaign closure).
- **Key derivable** — Mean, σ, skew, hit-rate, right-tail (top 5%), left-tail (bottom 5%). E2-S7 sample: "ממוצע +0.18R, σ=1.6R, hit-rate 47%, זנב ימני +3.4R, זנב שמאלי -2.1R."
- **Engagement hooks** — (a) Weekly Monday R-distribution surface (E2-S7) — anchors his identity as "tail trader" vs "hit-rate trader". (b) "Your last 10 trades skew right" — derivable from recent_10 in `_window_stats:311-342`. (c) Personal-best / personal-worst R headstones in `הספר` (E4 Chronicler).

### T1.7 — Sizing Accuracy: target_risk_usd vs original_campaign_risk

- **Where it lives** — Engine: `engine_core.py:966-1066` produces `original_campaign_risk`; `account_state.target_risk_usd()` at `:204-206` produces the target. Per-campaign ratio at `risk_monitor.py:497-540` (`_sizing_leak_alert`) and `risk_monitor.py:1168-1174` (Sizing Leak fire when ratio < 0.65, one-time per campaign).
- **Freshness** — Per `risk_monitor` cycle (300s) for open positions; per closed-campaign aggregation for the historical roll.
- **Key derivable** — Rolling-20 sizing ratio (E2-S2 sample: 0.58x mean). 90-day distribution of sizing-accuracy with σ. The MRVL 0.41x is one entry; the *pattern* is the signal.
- **Engagement hooks** — (a) E2-S2 "פער הסיזינג" — fires when rolling sizing < 0.7 or > 1.3, max once/week. (b) Tharp framing: "position-sizing is where psychology meets P&L." (c) Pair with conviction-text-richness (T1.15) — sizing × conviction = his hidden decision-quality dimension.

### T1.8 — Position-State Transition History (incl. ALGO suppressed)

- **Where it lives** — Engine: `engine_core.py:2047-2158` (`compute_position_state` — 10 states: ALGO_OBSERVED, DATA_INCOMPLETE, BROKEN, RUNNER, PROFIT_PROTECTION, WORKING, YELLOW_FLAG, DEAD_MONEY, PROVING, NEW). Audit trail: `audit_logger.ACTION_POSITION_STATE_TRANSITION` (`audit_logger.py:53`), wired in `risk_monitor.py:1054`. **F7 — every transition is recorded, even ALGO whose alerts are suppressed.**
- **Freshness** — Every `risk_monitor` cycle (300s), `audit_log` row per transition with `{symbol, prev_state, new_state, is_algo, alert_sent, suppression_reason}`.
- **Key derivable** — "PLTR went BROKEN at 14:22 on 19/05 — alert suppressed because ALGO." Mean time in each state. RUNNER → BROKEN survival curve.
- **Engagement hooks** — (a) "When did this position turn?" — answers the CEO's exact F7 question from the chat log. (b) E4 Beat-2 (inciting incident) inputs. (c) Heatmap of state-time across all positions over a quarter.

### T1.9 — Open-Task Lifecycle (committed vs skipped)

- **Where it lives** — Engine: `open_tasks.py:417` (`derive_tasks`), `:835` (`mark_done`), `:899` (`add_note`). Storage: Supabase `open_tasks` table (migration 005). Schema includes `task_type, status, urgency [P0–P3], trigger_state, trigger_open_r, trigger_age_days, notes (JSONB), created_ts, closed_ts` (`migrations/005_create_open_tasks.sql:16-31`). Idempotent unique index on `(user_id, campaign_id, task_type)` (`:36-37`).
- **Freshness** — Re-derived every render (engine is source of truth); only lifecycle deltas stored (G-rule #8 in `open_tasks.py:65`). `_SKIPPED_CRITICAL_EXIT` is the audited "skip P0 BROKEN exit" event (`:66`).
- **Key derivable** — Task-completion rate per urgency tier. Median time-to-done per task_type. The P0-BROKEN-skip count is itself a behavioural signal.
- **Engagement hooks** — (a) Weekly task-completion mirror ("8/12 P2 done this week, 1 P0 BROKEN skipped — that's `_SKIPPED_CRITICAL_EXIT` row 4 this quarter"). (b) Note-richness over time as a proxy for engagement depth. (c) "התחלת מה שלא סיימת" — tasks created >7d ago still open.

### T1.10 — Pre-DB Realized PnL Disclaimer (the founder-declared +$495.67)

- **Where it lives** — Engine: `account_state.py:209-232` (`pre_db_realized_pnl_estimate` — the single-source reader). Storage: `sentinel_config.json` key `pre_db_realized_pnl_estimate`. Consumed by `telegram_formatters.py:970-1062` (`classify_broker_reconciliation`). Documented at `docs/DATA_CONTRACTS.md:481-562`.
- **Freshness** — On-demand (founder writes via `scripts/set_pre_db_pnl_estimate.py`; per-call read; **no audit-log trail yet — DATA-F7 in MEETING_UX_DATA_FINDINGS.md**).
- **Key derivable** — Forensic visibility into the reconciliation arc: raw_gap_usd → pre_db_pnl_estimate → adjusted_gap_usd → band. The founder's own historical assertion stored as data.
- **Engagement hooks** — (a) "You declared +$495.67 of pre-DB gains on 21/05 — your DB-only realized PnL since then is $X; the residual is $Y." (b) Reconciliation streak (E1-#7) — days the gap stays balanced. (c) Honest-about-honesty: surface the date the disclaimer was last set + flag if file is missing.

### T1.11 — Locked At-Entry Price History (RISK-1 trail)

- **Where it lives** — Engine: `supabase_repository.py:223+` (`set_locked_entry`). Schema (migration 006): `locked_entry_price, locked_entry_at, lock_source, lock_method` on `trades` table. Resolver at `telegram_formatters.py:29-94` (`resolve_entry_display`). Backfill orchestrator: `risk1c_backfill.py:58+ (preview)`, `:111+ (run)`. Audit constants: `audit_logger.ACTION_AT_ENTRY_LOCK / _SKIP / _BACKFILL_RUN` (`audit_logger.py:39-46`).
- **Freshness** — On every BUY entry (RISK-1b wizard, forward-going) + admin backfill events (RISK-1c).
- **Key derivable** — Data-hygiene arc: NULL-locked rows over time → trending toward zero. Per-symbol lock-source distribution.
- **Engagement hooks** — (a) "21 of your last 21 entries are locked — your data hygiene is at 100%." (b) Banner suppression (`ENTRY_NOT_LOCKED_LABEL` at `:26`) becomes a milestone removal event. (c) The MRVL $87-vs-$170 regression is a story beat: "this fix exists because of one bad render in February — you caught it."

### T1.12 — Adaptive-Risk Settle Period (48h hold after a change)

- **Where it lives** — Engine: `adaptive_risk_engine.py:87-106` (`get_risk_settle_info`). Storage: `sentinel_config.json` keys `risk_changed_ts`, `risk_changed_dir`. Constant: `RISK_SETTLE_HOURS = 48.0` (`:47`).
- **Freshness** — Real-time; decays automatically (hours_remaining = max(0, 48 - elapsed)).
- **Key derivable** — "You changed to 0.85% at 14:22 on 19/05 — 31h remaining at this level before the next rec can fire."
- **Engagement hooks** — (a) Cooldown surface — explains why no rec is firing (transparency builds trust). (b) Settle-period kept-trades summary at settle-end (closure beat). (c) E4 Mentor's silence: "I'm watching, not pushing — settle period."

### T1.13 — Adaptive-Risk Heat Factors & "What to Improve"

- **Where it lives** — Engine: `adaptive_risk_engine.py:390-423` (`_build_heat_factors`, top-5 ranked drivers), `:426-461` (`_build_what_to_improve` — derives the WR-needed at current payoff). Surface in `telegram_formatters.fmt_adaptive_risk_block`.
- **Freshness** — Per adaptive-risk evaluation.
- **Key derivable** — Per-factor contribution. The factors today are: S9 WR, Payoff, PF, loss/win streak, S9-vs-M21 divergence, open R bonus.
- **Engagement hooks** — (a) Improvement-vector surface: "Win Rate S9: 33% — with Payoff 1.8x you need ~47% to lift the score." (`:448-450`). (b) Factor-rotation over time: which factor is currently the bottleneck. (c) "Your win-streak factor went from -10 to +5 in 9 days" — momentum on the meta-level.

### T1.14 — Drawdown-30d Auto-Cut Floor (forced-cut record)

- **Where it lives** — Engine: `adaptive_risk_engine.py:271-308` (`drawdown_auto_cut_recommendation`). Constants: `DRAWDOWN_TRIGGER_PCT = -8.0`, `DRAWDOWN_CUT_TO_PCT = 0.40`, `DRAWDOWN_WINDOW_DAYS = 30`. Applied at `:828-843` as a recommendation override (`result["override"] = "drawdown_auto_cut"`).
- **Freshness** — Per adaptive-risk evaluation cycle.
- **Key derivable** — Frequency of override firing, the 30d PnL when fired, recovery time from a force-cut back to ladder-organic recommendation.
- **Engagement hooks** — (a) "The system has never force-cut you" is itself a fact worth surfacing (process trust). (b) On a fire: surface the exact $ drawdown that triggered it — honest, no euphemism. (c) Recovery-arc: number of days from cut to first non-cut up-step.

### T1.15 — Risk-Visibility & Management-Mode (per-position decision provenance)

- **Where it lives** — Engine: `engine_core.py:256-296` (`is_algo_position`, `classify_management_mode` → `manual_managed | algo_observed | unknown`), `:298-340` (`compute_risk_visibility_score` 0/20/40/60/100). Per `docs/DATA_CONTRACTS.md:243-275`.
- **Freshness** — Runtime-derived per position render (never stored in Supabase).
- **Key derivable** — Per-position truth-of-management: did the founder delegate this to ALGO, did he own the stop, was the risk visible or `External / Unknown`?
- **Engagement hooks** — (a) E2-S8 ALGO outsourcing pattern — % delegated by time-of-day. (b) Risk-visibility trend: ratio of `score=100` (true risk known) trades over time. (c) "You delegated 64% to ALGO this week vs 51% rolling-90d — what happened at 15:00?"

---

## Data-freshness map (the four refresh tiers)

A surface can only be as fresh as its slowest input. For UX timing decisions:

- **Real-time / on-event** — risk_journal writes (T1.1), adherence marks (T1.2), open-task lifecycle deltas (T1.9), position-state transitions (T1.8), at-entry locks (T1.11), risk-pct change audit (T1.12), pre-DB disclaimer edits (T1.10).
- **Per `risk_monitor` cycle (300s)** — position-state classification (T1.8), peak_open_r and giveback zone (`risk_monitor.py:638-684`), sizing-leak detection (T1.7 / `:1168-1174`), Daily Digest dedup state (`last_digest_date`).
- **Per render (Telegram /portfolio, dashboard load)** — adaptive-risk recommendation (T1.5 / T1.13 / T1.14), per-bucket WR (T1.4), R-distribution snapshot (T1.6), 4-gate evaluation (T1.3), reconciliation classifier output, management-mode + risk-visibility (T1.15).
- **Cached (≥ minutes)** — yfinance price/MA series (~15-min provider cadence, ATR series), earnings dates (`engine_core.py:1456` — 6h TTL), sector cache (`sector_cache.json`), report-snapshot store (`report_snapshot_store.py` — WoW/MoM comparisons).

A surface that *implies* freshness it doesn't have ("מחיר חי...") on a cached input violates CLAUDE.md #1. Every Tier-1 derivable above is computable with strictly the freshness tier listed; no surface in this inventory requires faster data than Sentinel already collects.

---

## Tier 2 — Sentinel-has-but-not-unique (brief, deprioritized)

| Asset | Where | Note |
|---|---|---|
| NAV + freshness | `account_state.py:1-202` shape-A (`load()`) + `engine_core.py:1544-1641` shape-B (`get_nav_with_freshness`) — known divergence (Arch-F1 deferred) | Every brokerage shows NAV; Sentinel's value is the freshness label + the fallback-honesty disclosure |
| Market regime | `engine_core.py:570-620` (`compute_market_regime` — SPY/QQQ MA20/MA50 score) | Generic regime classifier; the wedge is per-trader WR conditioned on regime (T1.4 join) |
| Earnings dates | `engine_core.py:1456+` (6h cached yfinance) | Public data; cached. Useful only as input to event-risk shaping |
| ALGO exposure caps | `engine_core.py` constants (QQQ 10%, TSLA 7%, JPM 7%, PLTR 6%, HOOD 6%) | Static rules; not derived from founder behaviour |
| Live prices / ATR / MA bands | `engine_core.py` market-data layer | Standard tech-analysis; Sentinel's wedge is the cached/fallback honesty, not the value itself |
| IBKR sync errors (17 classes) | `ibkr_sync_runner.py` `IBKR_ERROR_CLASSES` | Ops surface; useful for "data integrity" beats but not founder-specific |
| Audit-log generic actions | `audit_logger.py:28-62` (8 constants) | Useful as denominator; not unique signal |

---

## Tier 3 — High-value derivations not yet computed (12)

| # | Derivation (1-line logic) | Why high-value | Complexity |
|---|---|---|---|
| D1 | **Best/worst day-of-week** — group closed campaigns by `close_date.dayofweek`, compute mean R | Anchors his weekly arc; pairs with E4 daily beats | **S** (one groupby) |
| D2 | **Best/worst hour-of-day** — group `trade_date` BUYs by hour, conditional expectancy R | E2-S1 "מראת התזמון" depends on this | **M** (need intraday timestamps — `trade_date` precision unclear; may need IBKR-Flex enrichment) |
| D3 | **Streak-length distribution** vs current — histogram of consecutive-win and consecutive-loss runs from `_window_stats:333-340` | Tilt antecedent surface (E1-#4, E2-S5) — current streak vs typical | **S** (one pass over closed campaigns) |
| D4 | **Recovery time from -2R day** — days from a -2R close to the next +1R day | Personal psychological recovery signature | **S** |
| D5 | **Conviction-trade detector** — text length of `management_notes` per campaign as proxy for rationale richness; flag top-quartile | The founder's "I had a reason vs I winged it" axis (E2-S10 inverse) | **S** |
| D6 | **Risk-raise adherence rate over time** — rolling-30d slice of `compute_adherence_stats` | Improving or declining trust in the system | **S** |
| D7 | **ALGO-vs-Manual hit-rate delta** — WR(ALGO_OBSERVED) − WR(EP_MANUAL+VCP_MANUAL) over rolling 60d | E2-S8 framing alternative ("ALGO באמת טוב יותר ממך?") | **S** |
| D8 | **Time-since-last-gate-clamp save** — days since `result["risk_raise_gate"]["allow_raise"]=False` last fired in rec-log | E1-#2 "Gate Receipt" anniversary beat | **M** (requires logging the gate result distinctly — see T1.3 gap) |
| D9 | **Disposition-effect signature** — for each closed campaign, partial-sell-R vs final-sell-R; positive = "let winners run", negative = "cut winners early" | E2-S3 core mirror | **M** (needs per-leg R, not just final R) |
| D10 | **Personal regime-conditional Win Rate** — WR(closed campaigns IN regime X) for each `compute_market_regime` state at the time of campaign close | E2-S9 + E1-#6 Regime Memory + analog-matcher | **M** (requires regime snapshot at close — not currently captured) |
| D11 | **Sentinel-save dollar value cumulative** — Σ(would-have-loss − actual-loss) for clamps that proved correct | E2-S6 + dashboard hero-metric | **L** (needs counterfactual price modelling per clamp) |
| D12 | **Reason-vocabulary clustering** — k-means / simple bucketing of `reason` text from `risk_journal.json` + audit_log + open_task notes | "Your personal tilt vocabulary" (E1-#4) | **L** (NLP — out-of-scope unless founder approves) |

---

## Data NOT to use (anti-list — out-of-scope for this engagement)

- **Real-time news feeds** — Sentinel does not fetch. Any "news triggered" surface is fabrication.
- **Options chains / IV / skew** — not in Sentinel's data path.
- **Social-sentiment (X/Reddit/StockTwits)** — never collected.
- **Cross-trader / leaderboard data** — only one trader in this system (sentinel user_id `00000000-0000-0000-0000-000000000001` per migration 003). No social comparison possible; E2 anti-pattern explicitly rejects it.
- **Live Level-2 / order-book / tape** — not subscribed.
- **Pre-deploy trades (historical brokerage)** — explicitly absent from Supabase per DATA_CONTRACTS.md:481-499. Only the `pre_db_realized_pnl_estimate` disclaimer covers this gap. Surfaces must respect the YTD-bound history scope.
- **Sentiment / mood self-report** — never collected; would require a new input surface. Out-of-scope for engagement phase.
- **Live IV / earnings whisper numbers** — yfinance earnings calendar only (`engine_core.py:1456+`), and that is dates-only.

---

## Cross-reference index — which Tier-1 asset powers which ideation surface

For the UX/Mark cherry-pick. Cross-referencing the 4 ideation streams against the inventory:

| Stream / Surface | Primary Tier-1 | Secondary | Tier-3 derivation needed |
|---|---|---|---|
| E1-#1 Edge Mirror | T1.5 (S9 heat) | T1.4 (per-bucket WR) | D10 (regime-cond WR) |
| E1-#2 Gate Receipts / E2-S6 | T1.3 (4-gate history) | T1.2 (adherence) | D8 (time-since-clamp), D11 (clamp $ saved) |
| E1-#3 Sharp-Hour | — | — | D2 (best/worst hour) — gated on intraday timestamp availability |
| E1-#4 / E2-S5 Loss-Sequence | T1.5 (loss_streak) | T1.6 (R-distribution) | D3 (streak histogram), D4 (recovery time) |
| E1-#5 Bucket Mirror | T1.4 | T1.15 (mgmt-mode) | D7 (ALGO-vs-MANUAL hit-rate) |
| E1-#6 Regime Memory | T2 (market regime) | T1.4 + T1.6 | D10 (regime snapshot at close) — blocks the analog matcher |
| E1-#7 Reconciliation Streak | T1.10 (pre-DB disclaimer) | T1.11 (locked-entry) | — |
| E1-#10 / E2-S10 "ללא נימוק" | T1.1 (risk-journal) | T1.9 (open-task notes) | D12 (reason clustering — out-of-scope NLP) |
| E2-S1 Time-of-Day | — | — | D2 — blocks on data |
| E2-S2 Sizing Drift | T1.7 | T1.5 (heat factors) | — (S-complexity wrapper) |
| E2-S3 Disposition | — | T1.6 (R distribution) | D9 (partial-vs-final R per campaign) |
| E2-S4 Rejection Journal | T1.1 | T1.2 | — |
| E2-S7 R-Distribution | T1.6 | — | — |
| E2-S8 ALGO Outsourcing | T1.4 + T1.15 | T1.8 | D7 + D2 |
| E2-S9 Regime-Conditional WR | T2 + T1.4 | — | D10 — blocks |
| E4 Daily Beats (5) | T1.8 (transitions) + T1.5 (heat) | T1.9 (open-tasks) | D1 (day-of-week), D2 (hour) |
| E4 Chronicler (הספר) | T1.1 + T1.2 + audit_log | — | — (read existing assets) |

The bottleneck for ideation surfaces is **D2 (intraday hour) and D10 (regime-at-close snapshot)** — six of the eighteen surfaces above are gated on these two. Sentinel should resolve both before the engagement-phase build, or the UX team will be forced to design around their absence.

---

## Top 10 most-valuable assets (ranked for UX prioritization)

1. **T1.7 — Sizing accuracy vs target** — the cleanest behavioral telemetry; powers E2-S2 (MUST-have 10/10), most likely to make the founder screenshot a message.
2. **T1.3 — 4-Gate clamp history** — powers E1-#2 / E2-S6 ("the surface that justifies the whole engagement"). Closes Tier-3 gap D8 + D11.
3. **T1.1 — Risk-journal entries** — powers E2-S4 (Rejection Journal, MUST-have 10/10), directly addresses the silent-rejection behaviour that triggered this engagement.
4. **T1.5 — Multi-window heat (S9/M21/L50)** — already computed; under-used. S9-vs-M21 divergence is a buried signal.
5. **T1.6 — R-distribution** — powers E2-S7 (the identity-defining weekly anchor); cheap to surface, deep meaning.
6. **T1.8 — Position-state transitions** — powers E4 Beat-2 + answers the CEO's "when did PLTR go BROKEN?" question; F7 already logging.
7. **T1.4 — Per-bucket WR (incl. ALGO outsourcing)** — powers E2-S8 + E1-#5; already in dashboard, needs Telegram surface parity.
8. **T1.2 — Adherence rate** — meta-signal of system-trust; pairs with T1.3 for the trust arc.
9. **T1.9 — Open-task lifecycle** — engagement-depth proxy; the `_SKIPPED_CRITICAL_EXIT` count alone is a behaviour signal worth surfacing.
10. **T1.15 — Risk-visibility / management-mode** — defines what Sentinel can and cannot say about each position; surfaces the ALGO-delegation boundary cleanly.

T1.10–T1.14 are next-tier (forensic/operational) — important for honesty contracts, not engagement first-contact.

---

## Honesty constraints inherited from the codebase (must propagate to every surface)

Every engagement surface that consumes these assets inherits the existing honesty contracts:

- **AGENTS.md #1** — Fallback / cached / estimated values must be labelled as such. A surface that reads `account_state.load()` on a `nav_source="fallback"` shape must surface that.
- **AGENTS.md #8** — `DATA_INCOMPLETE` and `ALGO_OBSERVED` must never enter Win Rate / Expectancy / Profit Factor. Any surface in the engagement layer that quotes these stats must filter via `engine_core.is_stat_countable()`.
- **DATA_CONTRACTS F4** — Exact-`trade_id` dedup before per-campaign aggregation. Any new R-distribution surface (T1.6 / E2-S7) must respect this or risk double-counting a re-synced SELL.
- **DATA_CONTRACTS F6** — DB-net-PnL term reads `total_pnl_usd`, NOT `net_pnl`. A reader using the wrong key silently sums to zero (Sprint-25 ARCH F1 regression class).
- **DATA_CONTRACTS F7** — 1R denominator is deliberately cent-rounded. The LOCKED April fixture pins this. Engagement surfaces that recompute R must use the same `compute_original_campaign_risk` path.
- **YTD-bound history** — All-time stats only cover post-deploy. Any "lifetime" framing in a surface must either disclose this or use the pre-DB disclaimer (T1.10) to compensate.
- **Anti-spam invariant (AGENTS #3 / risk_monitor)** — Every new recurring surface must have a per-position dedup flag or cooldown. Open-Task lifecycle (T1.9) and risk-journal (T1.1) are pull surfaces and exempt; any new *push* surface must be authored under this constraint.

These are not the engagement team's invention — they are pre-existing red lines. Listing them here so the UX/Mark synthesis does not propose surfaces that violate them.

---

## Sign-off

The 15 Tier-1 assets above are the **inventory the four ideation streams (E1/E2/E3/E4) can cherry-pick from without inventing data Sentinel does not have**. Every cited file:line is on `main` HEAD as of 21/05/2026; every storage location is documented in `docs/DATA_CONTRACTS.md` or the per-module docstring.

Three structural notes for the UX/Mark synthesis:

- **T1.3 + Tier-3 D8/D11 have a data gap**: the 4-gate's veto event is not currently logged with sufficient detail to compute the "dollar-value saved" derivable. Either log distinctly (B-tier change in `_log_recommendation`) or accept that Gate-Receipt UX requires a small backfill pass.
- **T1.2 + UX-U4 (chat-log finding)**: `telegram_audit_review.py:41-46` shows only `ACTION_RISK_PCT_CHANGE` — the rejection journal (T1.1) is invisible to "הפעולות שלי". Any "Rejection Journal" surface (E2-S4) will collide with this label-truth gap until the audit table reads risk_journal or vice versa (B3 in MEETING_UX_TEAM_MEETING.md Tier-B).
- **The market-regime conditional join (D10) is the highest-leverage Tier-3** — it turns market-context (Tier-2) into per-founder truth (Tier-1) with one snapshot-at-close write. The wedge surface (E2-S9 / E1-#6 Regime Memory) cannot exist without it.

Research-team verdict: the inventory is sufficient for UX/Mark synthesis to proceed. Three Tier-3 derivations (D1, D3, D6) are "S"-complexity and could ship in the same sprint as the first surface.

— RESEARCH-team, single-meeting, read-only artifact.
