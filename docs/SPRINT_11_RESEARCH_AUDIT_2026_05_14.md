# Research Department Audit
Authors: Sarah Chen (lead), Daria (quant)
Date: 2026-05-14
Branch reviewed: claude/integration-pi-and-main-2026-05-14
Commits in scope: 8bab814..67d0507 (Pi integration through Task Review)

## TL;DR

1. **Minervini Trend Template is in good shape.** All 8 criteria are encoded in `compute_trend_template_full` (engine_core.py:730). Market regime via SPY/QQQ MAs is computed but **never gates new entries** — it only labels.
2. **VCP entry mechanics (pivot, contraction, breakout volume) are NOT encoded.** The system knows a position *is* VCP only via a free-text `setup_type` label imported manually. There is no pivot detector, no contraction quality, no breakout-volume confirmation.
3. **The initial-stop policy (5–8% max) is unenforced.** No code anywhere checks that the recorded `initial_stop` is within 5–8% of entry. Risk math accepts any stop including 30%+ "stops" that defeat R.
4. **EP is a label, not a methodology.** Every R-management decision (BE@2R, trail@3R, dead-money>21d, runner@5R, follow-through window=10d) is *identical* for VCP and EP. EP's signature time-decay (exit by week 2-3) and lower-R targets are not encoded. `task_engine._task_dead_money` fires for EP *exactly when EP should already have been exited* — the 21-day threshold is past the EP shelf life.
5. **Power vs Weak labelling exists but is generic.** `score_position` (engine_core.py:326) labels positions Power/Healthy/Yellow/Weak/Broken but uses the same composite for both setups. There is no "after 2-3 weeks classify" timing gate — labels apply from day 1.

Net verdict: the system is a competent **R-bookkeeping + portfolio-heat engine** with strong Minervini decoration. It is *not yet* a methodology enforcer, and it does not differentiate the two setups beyond stat bucketing.

---

## Q1 — Minervini fidelity

| Principle | Where it lives | Verdict | Gap |
|---|---|---|---|
| **Trend Template (8 criteria)** | `engine_core.py:730` `compute_trend_template_full` | ✅ Fully encoded; returns 8 criteria + score. A legacy 5-criterion `get_minervini_analysis` (line 579) is still used for Telegram reports. | Telegram still uses the 5-criterion version (engine_core.py:606 "ציון תבנית מגמה"). UX shows /10 from 5 criteria, dashboard shows /10 from 8 — inconsistent. |
| **VCP entry (contraction + pivot + breakout vol)** | — | 🔴 Not encoded. Search for "pivot", "contraction", "VCP" returns only the legacy 5-criteria Hebrew comment at engine_core.py:606 and the setup-type literal. | No detector for tight bases, no pivot price, no volume-on-breakout filter. The system cannot evaluate VCP entry quality. |
| **Initial stop 5–8% from entry** | — | 🔴 Not enforced. The risk math (`compute_campaign_lot_state`, addon_risk_engine.py:90) accepts *any* `initial_stop < base_price`. | No validation rule. A 30% stop produces a comfortable "1R loss" that obscures the methodology breach. |
| **Position sizing 0.25%–2%** | `adaptive_risk_engine.py:20` `RISK_LADDER = [0.25, 0.40, 0.60, 0.85, 1.15, 1.50, 2.00]` | ✅ Encoded as ladder with closed-campaigns gate on UP steps (line 40). Drawdown auto-cut to 0.40% at -8% NAV (line 27). | Top of ladder is 2.00 not 2.50 — fine (Mark's preferred ceiling). |
| **BE @ 2R** | `task_engine.py:105` `_task_break_even_2r` | ✅ Encoded. | Fires from day 1. EP rarely sees 2R early; VCP can get there in days. Uniform rule is acceptable but coarse. |
| **Trail @ 3R+** | `task_engine.py:123` `_task_trail_up_3r` (locks +1R); `engine_core.py:1922` `compute_suggested_trail_stop` (MA50 at 5R, MA21 at 8R) | ✅ Encoded twice. Task engine moves to entry+1R. RUNNER suggestion uses MA21/MA50 with ATR buffer. | Two parallel systems with different thresholds (3R vs 5R/8R). User will see conflicting suggestions. |
| **Power vs Weak (after 2-3 weeks)** | `engine_core.py:357` `map_score_to_status` returns 🔥 Power / 🟢 Healthy / 🟡 Yellow / 🟠 Weak / 🔴 Broken | 🟡 Labels exist but applied from day 1 — no "after 2-3 weeks" gate. | Need an age guard: don't label Weak before day 10-15; don't label Power before day ~10. Otherwise a 3-day position can be tagged "Weak" on a single ATR shake. |
| **Time efficiency / Dead Money** | `engine_core.py:192` `map_time_efficiency` (>=8d, R<0.5 → dead_money); `engine_core.py:2064` PROFIT classifier; `task_engine.py:89` `_task_dead_money` (>21d, R<0.3) | 🟡 Three thresholds in three places: 8d/0.5R (score penalty), 8d with weak FT (state machine), 21d/0.3R (task review). | Inconsistent. Decide one canonical "dead money" definition; differentiate by setup (EP shelf life ≠ VCP). |
| **Distribution days** | `engine_core.py:174` `detect_distribution_days` | 🟡 Detector exists; uses 1.5× vol + range>1.2×ATR + close in bottom 35%. Counts in 8d/12d windows (line 235). | Mark's canonical is a 20-25 session rolling count vs a fixed cluster threshold (4-5 within 20 days = distribution cluster). The 8d/12d windows are too short and don't expose the "cluster" concept. |
| **Follow-Through Day (after market correction)** | — | 🔴 Not implemented. `compute_follow_through` (engine_core.py:1783) is per-position breakout follow-through, NOT the IBD/Minervini FTD market-level signal. | The market-correction-then-FTD switch is one of Mark's primary timing tools. Currently absent. |
| **Market regime gate** | `engine_core.py:535` `compute_market_regime` returns Hot/Warm/Neutral/Cold | 🟡 Computed and shown, but **does not gate new entries or sizing**. The coaching string at line 815 says "הקטן חשיפה" — text only, no code action. | Add a gate: when regime=Cold, block UP-ladder steps and warn on new positions. |
| **Pyramid Power, exit Weak** | `engine_core.py:701` `analyze_addon_quality` (no averaging down); `addon_risk_engine.py` (multi-gate add-on approval) | ✅ The add-on engine enforces "never below base" and a cushion ratio. | Doesn't actually require Power status before approving an add-on. `addon_risk_engine.check_addon_eligibility` does not query position state. |

---

## Q2 — EP coverage

| Principle | Where it lives | Verdict | Gap |
|---|---|---|---|
| **EP/VCP differentiation at the methodology layer** | `engine_core.py:1249` `classify_stat_bucket` separates `EP_MANUAL` vs `VCP_MANUAL`; dashboard.py:377-378 reports separate stats | 🟡 Stats are bucketed; behaviour is not. Same hard rules, same state machine, same task rules. | The only setup-aware code is `is_algo_position`. No `if setup == "EP"` branch in `task_engine.py`, `risk_monitor.py`, `evaluate_hard_rules`, `compute_position_state`, or `compute_suggested_trail_stop`. |
| **EP entry: D2/D3 after gap+volume** | — | 🔴 No detection. The system doesn't know what triggered an EP campaign — there's no `event_date`, no `gap_pct`, no `event_volume_ratio` field anywhere. | Without a catalyst date, the engine cannot evaluate whether the entry actually was an EP. |
| **EP stop at D1 low** | — | 🔴 Not encoded. `initial_stop` is whatever the importer or user wrote down. | Need a `pivot_bar_low` field that is enforced as the floor for EP stops. |
| **EP profit target (lower R, ~2-3R)** | — | 🔴 Not encoded. RUNNER threshold (`_R_RUNNER = 5.0`, engine_core.py:1696) applies to EP. | An EP at +3R should already be in late-stage profit-protection, not still "WORKING". |
| **EP time decay (exit by week 2-3 even if not stopped)** | — | 🔴 Not encoded — and **inverted in practice**. `task_engine._task_dead_money` (line 93) fires only at *days_held > 21* AND open_r < 0.3. For EP, 21 days is already past the typical hold window. The rule misses the EP-fades-fast scenario entirely. | Need EP-specific time gates: D5 = "should be working", D10 = "trim if not at 2R", D15 = "exit". |
| **`classify_stat_bucket` counts EP differently** | engine_core.py:1249 | ✅ Bucketed `EP_MANUAL` vs `VCP_MANUAL`. Stats segregate. | Sufficient for analytics, insufficient for management. |
| **Adaptive risk engine learns EP-specific edge** | `adaptive_risk_engine.py:486` `compute_adaptive_risk` runs on `disc_camps` (EP+VCP combined) | 🔴 EP and VCP are merged into a single "discretionary" pool for heat scoring. A great VCP run can mask a bleeding EP edge (and vice versa). | Split heat into per-bucket sub-scores. Mark's playbook says "edge dies setup-by-setup, not in aggregate." |
| **EP-specific follow-through score** | `engine_core.py:1783` `compute_follow_through` uses fixed 7% / 5% / 10-day window | 🟡 The 10-day window is roughly right for EP. The 7% peak threshold is high for many EP names that pop and fade. | Make `_FT_PEAK_FULL_PCT` setup-aware (EP: 4-5%, VCP: 7-8%). |
| **EP `evaluate_hard_rules`** | engine_core.py:307 | 🔴 Generic. The 3-distribution-days-in-12 rule (line 315) is fine for VCP but unhelpful for a 7-day-old EP that's already at +2R. | Add an EP path that triggers on D1-low loss and on 5-day failure to break the entry-day high. |

---

## Q3 — Gaps ranked

### 🔴 BLOCKER

1. **EP/VCP are statistically separate but operationally identical.** All management rules in `task_engine.py`, `risk_monitor.py`, `engine_core.evaluate_hard_rules`, and `engine_core.compute_position_state` ignore `setup_type` except for `ALGO`. The user trusts that "EP win rate", "EP expectancy" reflects EP discipline — but every guard-rail that enforces discipline is generic. *Recommendation:* introduce a `SetupProfile` dataclass keyed on setup, with fields `(max_hold_days, runner_r, profit_protect_r, dead_money_days, ft_peak_full_pct, distribution_window_days)` and thread it through the engine functions.

2. **Initial-stop 5–8% rule is not enforced anywhere.** A campaign can be imported with `initial_stop = entry × 0.70` and the engine will happily compute R relative to that 30% stop, making the dollar loss look like "1R" when it's actually 4× a real Minervini stop. *Recommendation:* add `validate_initial_stop(entry, initial_stop, setup_type) -> dict` returning quality grade (in-spec ≤ 8%, marginal 8-10%, out-of-spec > 10%) and surface it on the position card. Block stat-countable bucketing for out-of-spec stops, OR flag them as `STAT_BUCKET_LOOSE_STOP`.

3. **Dead-Money rule is wrong-direction for EP.** `task_engine.py:93` fires at *days_held > 21* — for EP that's a week *past* the methodology exit. The system effectively *tolerates* EP stagnation for three weeks and then suggests action. *Recommendation:* setup-specific thresholds: EP → trigger at D10 if open_r < 1.5; VCP → keep current.

### 🟠 HIGH

4. **No VCP entry detector.** The system trusts the user-supplied `setup_type`. There is no code that verifies a VCP-tagged position actually showed contraction, a pivot, and breakout volume. *Recommendation:* add `evaluate_vcp_entry_quality(symbol, entry_date, entry_price) -> {contraction_count, pivot_price, breakout_vol_ratio, grade}`.

5. **Market regime is decorative, not gating.** `compute_market_regime` (engine_core.py:535) returns Cold/Neutral/Warm/Hot, but no module reads the result to gate new entries or block UP-ladder steps. *Recommendation:* in `compute_adaptive_risk`, when regime=Cold, force `direction=hold` regardless of heat; raise drawdown floor.

6. **Follow-Through Day (market signal) is missing.** The function `compute_follow_through` is name-clashing — it does *per-position* breakout follow-through, not Minervini's *market-level* FTD after a correction. *Recommendation:* add `compute_market_ftd(spy_hist)` returning `{is_correction, days_since_low, ftd_today, ftd_recent}` and surface in the daily briefing.

7. **Heat scoring merges EP+VCP.** `adaptive_risk_engine.compute_adaptive_risk` pools `disc_camps`. A bleeding EP cohort can be masked by a winning VCP cohort. *Recommendation:* compute `s9_score` per bucket; require both to be ≥60 before stepping UP.

8. **Two parallel trailing systems with mismatched thresholds.** `task_engine._task_trail_up_3r` (lock +1R at 3R) and `compute_suggested_trail_stop` (MA50 at 5R, MA21 at 8R) will both fire on the same position. Telegram users will see contradictory suggestions. *Recommendation:* let one own R<5 territory, the other own R≥5; document the handoff.

9. **Power/Weak labels apply from day 1.** `score_position` labels a 2-day-old position 🟠 Weak on a single distribution day. *Recommendation:* gate labels by `days_held >= 10` for Power/Weak; before that, only NEW / PROVING / BROKEN.

### 🟡 MEDIUM

10. **Three inconsistent dead-money definitions.** `map_time_efficiency` (8d/0.5R), `compute_position_state` (8d, weak FT, no new high), `task_engine._task_dead_money` (21d/0.3R). Pick one canonical and have the others delegate.

11. **Distribution-day counting is short-window.** 8d/12d windows (line 235) don't expose Mark's "4-5 within 20 sessions = distribution cluster" concept. *Recommendation:* add `dist_25` and a `distribution_cluster: bool` flag.

12. **Legacy 5-criterion Trend Template still used by Telegram.** `get_minervini_analysis` (engine_core.py:579) computes /10 from 5 criteria. The full 8-criteria version was added but not adopted by the bot. *Recommendation:* migrate Telegram callers to `compute_trend_template_full` and retire the legacy formula, or label it explicitly as a "quick view".

13. **`compute_follow_through` thresholds are VCP-flavored.** 7% peak, 5% new high — fine for VCP, high for EP. Parameterize on setup.

14. **Add-on approval doesn't read position state.** `addon_risk_engine.check_addon_eligibility` doesn't gate on Power vs Weak. Methodology says "pyramid Power only." *Recommendation:* thread `position_state` into the eligibility check; require state ∈ {WORKING, PROFIT_PROTECTION, RUNNER} for any add-on.

15. **`classify_intent` is heuristic and shallow.** engine_core.py:1584 uses string match on `management_state` ("probe", "runner") — a free-text field. Brittle. *Recommendation:* derive intent from numeric state machine output, not text.

16. **No event-date / catalyst field.** EP positions don't carry `catalyst_date`, `catalyst_type` (earnings / FDA / M&A), or `gap_pct`. Without these, the engine can't reason about D1/D2/D3 entries or week-2 fade. *Recommendation:* add optional columns to the trades table; populate via IBKR importer + manual override.

17. **`mistake_classification` relies on management_notes text matching.** engine_core.py:1639 does Hebrew + English substring matches ("gap", "גאפ", "halt"...) on a free-text field. Fragile and untestable. *Recommendation:* structured mistake_code enum at close time.

### 🟢 LOW

18. **`_RUNNER_FOLLOW_THROUGH_MIN = 70.0` and `_WORKING_FOLLOW_THROUGH_MIN = 60.0` (engine_core.py:1701-1704) are magic numbers** with no test fixtures verifying they're not too strict for short-history positions.

19. **`compute_market_regime` weights SPY twice and QQQ once** — no documentation of why.

20. **Hebrew status labels mix emoji and text in non-standard ways** (e.g. "🟡 תקין אך במעקב" at line 368 collides with "🟡 Yellow Flag"). Two labels rendered as the same emoji = ambiguous on mobile.

---

## Recommendations for Sprint 11

1. **Introduce `SetupProfile` and thread it through the engine.** One dataclass per setup with (max_hold_days, runner_r, profit_protect_r, dead_money_threshold_days, dead_money_threshold_r, ft_peak_full_pct, dist_window). Update `task_engine`, `evaluate_hard_rules`, `compute_position_state`, `compute_follow_through` to consume it. Tests: parameterized per profile.

2. **Enforce 5–8% initial-stop rule.** Add `validate_initial_stop()` and surface a per-campaign stop-quality grade. Block UP-ladder steps when last 9 disc closes contain ≥3 out-of-spec stops. Tests: in-spec / marginal / out-of-spec.

3. **Build market-regime gating.** Modify `adaptive_risk_engine.compute_adaptive_risk` to force `direction=hold` when regime=Cold; force drawdown floor lower (0.25%) on Cold regime. Add `compute_market_ftd(spy_hist)` and surface in daily digest. Tests: cold-regime override; FTD detection on a known historical low.

4. **Split heat scoring per bucket.** Compute `ep_heat_score`, `vcp_heat_score`, `combined_heat_score`. Require both EP and VCP s9 ≥ 60 before any UP step. Tests: VCP-strong / EP-weak should hold; both-strong should step up.

5. **Reconcile dead-money definitions.** Pick the state-machine version (`compute_position_state`) as canonical; have `task_engine._task_dead_money` and `map_time_efficiency` delegate. Add setup-specific thresholds (EP→10d/1.5R, VCP→21d/0.3R). Tests: per-setup boundary cases.

6. **Reconcile trailing-stop systems.** Document one canonical rule: BE@2R, +1R@3R, MA21@5R+, MA50@8R+. Update both `task_engine` and `compute_suggested_trail_stop` to a shared helper. Tests: open_r = 1.5/2/3/5/8 transitions.

7. **Add catalyst metadata for EP.** New optional fields `catalyst_date`, `catalyst_type`, `gap_pct` on trades. Importer learns to populate; bot exposes "set catalyst" command. Foundational for any future EP-specific automation. Tests: import roundtrip + EP without catalyst still grades as `EP_MANUAL` but with `data_complete=partial`.

— Sarah & Daria
