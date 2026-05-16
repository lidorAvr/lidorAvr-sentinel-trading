# Mark — Sprint 17 Rulings (ALGO Governance: fine-tune DEC-014 + unblock #4/#5)

**Owner:** Mark (methodology, gate). **Date:** 2026-05-16. **Branch:** `claude/review-system-audit-FBZ2h`.
**Scope:** numeric fine-tuning of the already-accepted, structurally-locked DEC-20260515-014 against the founder's real ALGO data (`ALGO_REFERENCE_2026_05_16.md §6`), plus the BLOCKED #4 / #5 unblock. **Zero** R/NAV/exposure/campaign math change (AGENTS.md Red Lines; invariants #1/#8). Advisory-only, observer-mode (DEC-20260511-001). No code this sprint — this doc gates Wave 2. **Does not contradict `MARK_SPRINT15_RULINGS.md §4`; it makes that REFINE concrete.**

**Provenance rule (binding):** every threshold below traces to a cited `ALGO_REFERENCE §x` datum **or** an existing engine constant (file:line). No number is invented. Where the founder's §6 wording overlaps an already-shipped engine signal, the Governor **reuses** that signal — it does not add parallel math.

---

## 1. Fine-tune DEC-20260515-014 against ALGO_REFERENCE §6

The Gate is **advisory-only**: it withholds the *founder's own* discretionary ALGO size-up / new-asset / exposure-up decision. It NEVER instructs the ALGO, never alters an ALGO trade, emits at most `Review Required` — never `Action Required` (DEC-20260511-001 display rule; `evaluate_position_engine` ALGO_OBSERVED path already returns the fixed `"מנוהל חיצונית — בקרה בלבד"` action and `suggested_stop=None`, `engine_core.py:457-467` — that contract is untouched). All triggers below are computed on the **ALGO-segregated cohort** (§2) and surface as a single advisory `Review Required` read-out; none changes any ALGO position or any R/NAV/campaign formula.

### 1a. Decay control (§6 "Decay control" table)

| # | Founder §6 trigger | EXACT ruled condition | Reuses existing engine signal? | Governor effect (advisory) |
|---|---|---|---|---|
| D1 | PF of last 10 trades < 1 | Cohort rolling **PF over last 10 closed ALGO trades < 1.0** (PF = Σ wins / |Σ losses|, §2 formula). `1.0` = the founder's literal §6 value AND the §3 regime boundary (2022 PF 0.67, 2026 PF 0.73 = sub-1 = bad regime). | **NEW metric** (rolling cohort PF) — no existing engine signal computes PF on a 10-trade ALGO window. Methodology-isolated per §2. | `do not increase exposure` → withhold size-up; `Review Required`. |
| D2 | last 5 trades negative > 7.5% | Cohort **sum of last 5 closed ALGO trade %-returns < −7.5%**. `−7.5%` = founder's literal §6 number (no rounding/derivation). | NEW (rolling 5-sum); no existing signal. | `cut size 50%` → advise the founder cut new sizing by half; `Review Required`. |
| D3 | last 10 trades negative > 10% | Cohort **sum of last 10 closed ALGO trade %-returns < −10%**. `−10%` = founder's literal §6 number. | NEW (rolling 10-sum). | `freeze full-size opening` → withhold any new full-size; `Review Required`. |
| D4 | 6-loss streak → Yellow | Cohort **consecutive-loss count ≥ 6** ⇒ Yellow. `6` = founder's literal §6 number. | **REUSE the loss-streak primitive** in `risk_monitor.py:881-893` (`algo_loss_streak`, +1 per losing run). NB: the existing alert counts ~5-min monitor *runs* in a single open position (orange≥5/yellow≥3 runs, `:888-892`); the §6 Governor streak is **closed-trade** count on the cohort — a *different* unit. Ruling: keep the existing per-position run-streak alert byte-identical; the Governor streak is a NEW cohort-level closed-trade counter (consistent with §2 max-loss-streak of 7 for QQQ/TSLA in §2). The two never share state. | `Yellow` → `no increase until improvement`; `Review Required`. |
| D5 | 8-loss streak → Red | Cohort consecutive-loss count **≥ 8** ⇒ Red. `8` = founder's literal §6 number. | Same NEW cohort counter as D4 (escalation tier). | `Red` → withhold all size-up / new ALGO assets; `Review Required` (NEVER `Action Required`, even at Red — DEC-20260511-001). |
| D6 | trading-year negative for the algo | Per-symbol **current-year (2026) cumulative %-return < 0** for that ALGO. Grounding: §3 (2026 = −16.65%, 18.5% win, PF 0.73) is "THE current-state signal"; condition is literal ("year negative"), no invented cutoff. | NEW (per-symbol YTD cohort sum); reuses the same cohort store, segmented by symbol+year. | `no increase until improvement` for that symbol; `Review Required`. |

### 1b. Open-profit control (§6 "Open-profit control" table) — REUSE existing live signals, do not duplicate

| # | Founder §6 state | EXACT ruled condition | Reuses existing engine signal | Governor effect (advisory) |
|---|---|---|---|---|
| O1 | open > 7% | Open ALGO position **open % ≥ 7%** → "tight monitor". Surfaced as an informational `Review Required` flag. | **REUSE** the per-position monitor loop; this is a label on existing `open_r`/open-% data — no new alert object. Lowest open-profit checkpoint = informational only. | "tight monitor" note in the ALGO read-out. |
| O2 | open > 10% | open % **≥ 10%** → "do not let it return to a full loss". | **REUSE** `risk_monitor.PROFIT_CHECKPOINTS = [2.0, 3.0]` + `compute_giveback_from_peak` (`engine_core.py:866-895`). The "don't give it all back" intent **is already** the Giveback monitor (`risk_monitor.py:516-533`). The Governor adds a §6-labelled read-out only; it fires NO new alert and NEVER tells the ALGO to do anything. | Giveback-watch note (reuses existing classification). |
| O3 | open > 15% | open % **≥ 15%** → "lock part of the profit". | **REUSE** the Giveback `tighten` zone (`giveback_pct_of_peak` > 35%, `engine_core.py:887-888`) + checkpoint surface. Advisory text to the *founder* ("consider locking part"); it is NOT a stop-raise/exit instruction to the ALGO (DEC-20260511-001). | Advisory "consider partial lock" — founder-facing only. |
| O4 | open > 20% | open % **≥ 20%** → "Runner Mode". | **REUSE** `POSITION_STATE_RUNNER` / `_R_RUNNER = 5.0` (`engine_core.py:1664,1685`) and the existing `_runner_state_alert` (`risk_monitor.py:285`). The Governor surfaces "this ALGO is in a runner-grade profit zone" using the existing RUNNER state; it does NOT manage the runner for the ALGO. The `20%` is the founder's literal §6 number; `5R` stays the engine's existing manual RUNNER constant — they are independent, not reconciled into one. | "Runner-grade profit" note; reuses RUNNER state. |
| O5 | giveback > 50% of peak profit | **REUSE verbatim** `compute_giveback_from_peak` → `classification == "protection_failure"` (`giveback_pct > 50`, `engine_core.py:889-890`). The founder's "giveback > 50%" **is exactly** the existing `protection_failure` bucket — same `50` constant, no new math. | **REUSE** the existing Giveback alert (`risk_monitor.py:518-533`, `_giveback_alert_text`). Genuinely-new = nothing; this is a pure reuse. | "strong alert" = the existing Giveback `protection_failure` alert, ALGO-labelled. |

### 1c. Cluster control (§6 "Cluster control" table)

| # | Founder §6 state | EXACT ruled condition | Reuses existing engine signal | Governor effect (advisory) |
|---|---|---|---|---|
| C1 | several algos open on growth names together → compute Cluster Risk | ≥ 2 ALGO positions concurrently open among the growth set {TSLA, PLTR, HOOD, QQQ} → compute Cluster Risk = total ALGO exposure % of NAV. | **REUSE** `algo_cluster_pct` already computed in `risk_monitor.py:950` (`total_algo_exposure / acc_size * 100`). "Cluster Risk" = this existing number, surfaced — NOT a new exposure formula (no new R/NAV/exposure math, AGENTS.md Red Line). | Surface Cluster Risk %; advisory only. |
| C2 | QQQ below key daily MAs → reduce size on aggressive algos | QQQ ALGO position open AND QQQ price below its daily MAs (read-only price check, no new indicator math beyond what the engine already pulls). Grounding: §1 QQQ rule + §3 (QQQ Yellow in 2026). | Partial reuse: price/MA data the engine already fetches; the *combination flag* is NEW (read-only) but adds no math. | "consider reducing size on TSLA/HOOD/PLTR"; founder-facing advisory only. |
| C3 | PLTR & HOOD open together → no additional speculative risk | PLTR AND HOOD both open simultaneously. Literal §6 pairing; PLTR & HOOD are §2's two most concentrated/explosive (PF 4.01 / 7.13, worst DD −24.26% / −11.14%). | NEW co-occurrence flag (read-only on existing open-position set). | Withhold *new speculative* size-up; `Review Required`. |
| C4 | TSLA & PLTR open together → check volatile-momentum exposure | TSLA AND PLTR both open simultaneously. Literal §6 pairing (§1: both highest-volatility books). | NEW co-occurrence flag (read-only). | "check volatile-momentum exposure" advisory note. |
| C5 | whole cluster > 30% → block new full-size | `algo_cluster_pct > 30%` → withhold new full-size ALGO opens. | **REUSE** `ec.ALGO_CLUSTER_WARNING_PCT = 30.0` (`engine_core.py:15`; risk_monitor `:957`). `30%` is **already the engine's existing yellow constant** AND the founder's §5/§6 literal cap — exact match, nothing invented. Critical stays the existing `ALGO_CLUSTER_CRITICAL_PCT = 35.0` (`engine_core.py:16`; §5 ">35% Critical"). | Withhold new full-size; reuses existing cluster-yellow alert text (`risk_monitor.py:974`). |

### 1d. The −5R trigger basis (DEC-20260515-014 trigger #1)

The DEC-014 `ALGO Net PnL < −5R` trigger stays. **R basis = Account R** = `compute_r_target(net_pnl, frozen_target_risk_usd)` (`engine_core.py:1004-1008`), denominator the frozen target risk (NAV-based; `MARK_SPRINT15_RULINGS.md §1-§2`). Rationale (binding, restates DEC-011 / MARK_S15 §1/§4): **ALGO has no real stop** (`classify_risk_basis` returns `"Target"` for ALGO; §1 confirms QQQ/HOOD have no hard stop, PLTR's −25% is an emergency cushion not a management stop). Therefore `compute_r_true` is invalid for ALGO (returns 0.0 on invalid risk → must never display as `0.00R`, invariant #1). The `−5R` magnitude is **not invented**: it is the system's existing materiality anchor reused by `MARK_SPRINT15_RULINGS.md §3` (Critical Data Gap = 5× the 0.5% risk unit) and the founder's own gate scale. State explicitly in the read-out: *"−5R on Account-R basis (ALGO has no real stop)."*

**Advisory-only confirmation (all of §1):** every trigger above produces at most a founder-facing `Review Required` read-out that withholds the founder's discretionary size-up / new-asset / exposure-up. None emits `Action Required`; none is sent to or about managing the ALGO; the `evaluate_position_engine` ALGO_OBSERVED return contract (`engine_core.py:457-467`) is byte-identical (DEC-20260511-001).

---

## 2. The ALGO-segregated cohort (the #8 crux)

**Cohort membership (exact):** a closed campaign is in the **ALGO cohort** iff `classify_stat_bucket(...) == STAT_BUCKET_ALGO` (`engine_core.py:1232,1238-1258`), i.e. `is_algo_position(setup_type, symbol)` is true (`setup_type == "ALGO"` primary, the 5 `ALGO_SYMBOLS` {QQQ,TSLA,JPM,HOOD,PLTR} secondary, `engine_core.py:247-261`). This is the **same predicate** that already excludes ALGO from headline stats — the cohort is the *complement of the headline set by construction*, not a new classification.

**Rolling window:** **last 30 closed ALGO trades** (cohort, most-recent first), with sub-windows of **last 10** (D1/D3/D6) and **last 5** (D2) per §6. `20–30` is DEC-20260515-014's locked range; choose **30** (upper bound) as the cohort store size so the 5/10 sub-windows are always satisfiable; the founder's §6 windows are literally 5 and 10. (Cross-check: §2 per-ALGO trade counts — JPM 33, HOOD 34, PLTR 18 — a 30-deep *cross-ALGO* cohort is viable; per-symbol D6 uses whatever 2026 trades exist, ≥1.)

**Formulas (no new math primitives; standard definitions, computed ONLY on the cohort):**
- **PF (D1):** `Σ(positive trade returns) / |Σ(negative trade returns)|` over the window; undefined-if-no-losses → treat as ≥1 (not a decay trigger). Cross-check vs §2 (QQQ PF 2.29, aggregate 3.48) — formula reproduces the founder's stated PFs.
- **Rolling sum (D2/D3/D6):** arithmetic sum of the window's per-trade %-returns. (%-per-trade is the founder's §1/§2 unit; honor §5 backtest caveat — see §5 below.)
- **Loss streak (D4/D5):** max trailing run of consecutive negative-return closed trades in the cohort (cross-check §2 "Max loss streak": QQQ/TSLA 7, aggregate 12 — formula reproduces).
- **Expectancy (DEC-014 trigger #2):** `mean(per-trade return)` over the window; negative ⇒ trigger. Computed cohort-only.

**#8 physical isolation (binding proof obligation for Wave 2):** the cohort and every metric above are computed in a **separate function over a separately-filtered list**; the headline Win-Rate/Expectancy path keeps calling `is_stat_countable(stat_bucket)` (`engine_core.py:1261-1263`) which **already returns False for `STAT_BUCKET_ALGO`** (and `DATA_INCOMPLETE`). The ALGO cohort metrics must be **read-only consumers** of the same closed-campaign rows AFTER the headline filter has excluded them — they are NEVER merged back. Founder's binding intent: *"separating manual vs ALGO stats is mandatory"* (§7; AGENTS.md invariant #8: "Win Rate and Expectancy must never include … ALGO_OBSERVED campaigns"). The Governor reads ALGO PF/expectancy/streak; the headline report reads `is_stat_countable`-true campaigns; the two sets are disjoint by the existing predicate. **No new exclusion logic is written — the existing `is_stat_countable` path is the single source of the #8 boundary, reused as-is.**

---

## 3. #4 ruling — ALGO known stop/exit (UNBLOCKED)

DEC-20260515-014 / DEC-20260515-005-class blocker on "State/InitStop/CurrStop Unknown, Visibility 40/100" is now unblocked by `ALGO_REFERENCE §1`. The engine (ALGO_OBSERVED path, `engine_core.py:457-467`) currently emits `suggested_stop=None` and the display layer shows `External / Unknown` (DEC-20260511-001). Ruling: replace the bare "Unknown" with the **§1 known per-symbol rule, observation-only**, as a derived read-only field (no DB write, invariant on read-only flows). Display contract per symbol:

| Symbol | Display instead of "Unknown" (Hebrew, RTL, short) | Source |
|---|---|---|
| **QQQ** | `ALGO ללא סטופ קשיח — נשלט ביציאות-זמן (3c<−2% · 33c<0% · 46c<1.7% · 90c<11%)` | §1 |
| **HOOD** | `ALGO ללא סטופ קשיח — נשלט ביציאות-זמן (10c<4% · 65c<25% · 85c<40%)` | §1 |
| **TSLA** | `סטופ ALGO ידוע: −4.3%` | §1 |
| **JPM** | `סטופ ALGO ידוע: −3.3%` | §1 |
| **PLTR** | `אין סטופ ניהולי — כרית חירום בלבד −25% (יציאות-זמן: 230c אם הפסד>14.8% · 295c אם >12%)` | §1 |

**Honesty mandate (invariant #1):** the field is labelled as the **ALGO's own rule, observed not enforced by Sentinel** — wording must say "ALGO known rule (observed)", never imply Sentinel set or guarantees it. `risk_visibility_score` stays 40 (`compute_risk_visibility_score:298-299`) — that score is unchanged; #4 adds *content*, not a higher visibility number (the DEC-014 dropped-`Visibility<70` ruling stands; do not resurrect it). "No hard stop → time-exit-controlled" is stated as a *fact about the ALGO's design*, not a defect.

---

## 4. #5 ruling — strategy-adaptive ALGO dead-money (UNBLOCKED)

Generic discretionary dead-money = `_DEAD_MONEY_MAX_R = 0.75` / `_DEAD_MONEY_MIN_DAYS = 8` (`engine_core.py:1696-1698`) — **stays byte-identical for the manual path** (MARK_S15 §5: route by strategy key; `manual` unchanged). For an **ALGO** position, "dead money" = **the ALGO's own §1 time-exit threshold for that symbol**, observation-only:

| Symbol | ALGO "not-working / dead-money" signal (from §1 time-exits) |
|---|---|
| QQQ | candle-age vs %: 3c<−2% / 33c<0% / 46c<1.7% / 90c<11% not met |
| HOOD | 10c<4% / 65c<25% / 85c<40% not met |
| PLTR | 230c & loss>14.8%, or 295c & loss>12% |
| TSLA / JPM | no ALGO time-exit (MA-cross / TP / hard-stop controlled) → **no ALGO dead-money signal**; do NOT apply the generic 0.75R |

**Surfacing:** emit as an **Open-Tasks / `Review Required` advisory note** ("ALGO X near its own time-exit window — verify the ALGO is connected and acting"), mirroring the existing observer wording in `_algo_loss_streak_alert` (`risk_monitor.py:389-390`: "Sentinel does not intervene in ALGO management; verify the ALGO is connected"). **It must NOT** instruct the ALGO, raise/move a stop, or trigger an exit (DEC-20260511-001). **#8 guard:** this is a live open-position observer note only; it never touches the closed-campaign cohort or any stat — zero contamination path. Distinct from `_DEAD_MONEY_MAX_R`: different key, different threshold source (§1 per-symbol, not 0.75R), different surface (advisory note, not the `DEAD_MONEY` position state).

---

## 5. Backtest-caveat disclosure (invariant #1)

Wherever ANY ALGO stat derived from this dataset is shown (cohort PF/expectancy/streak, §2/§3 figures, the −5R read-out), the surface MUST carry, honestly and non-suppressibly:

- Hebrew (short, RTL): `‏נתוני ALGO = בק-טסט (ללא עמלות/החלקה/הון אמיתי) — לא טראק-רקורד חי.`
- English / AI-copy: `ALGO stats = backtest (no fees/slippage/real capital) — not a live track record.`

This restates `ALGO_REFERENCE` header caveat + §5 + AGENTS.md invariant #1 ("must not present fallback or stale data as exact truth"). DEC-20260515-004 still forbids ANY public ALGO numbers — these surfaces are **internal/founder-facing only**; no public/marketing exposure.

---

## 6. Gate — 12-item pass/fail checklist + #8 byte-identical guard

1. Every §1a–§1c threshold traces to a cited `ALGO_REFERENCE §x` datum or an existing engine constant (file:line); zero invented numbers. ☐
2. O2/O3/O4/O5 **reuse** existing Giveback (`engine_core.py:866-895` / `risk_monitor.py:516-533`), `PROFIT_CHECKPOINTS`, RUNNER (`_R_RUNNER=5.0`) — no parallel profit-protection math added. ☐
3. C5 reuses `ALGO_CLUSTER_WARNING_PCT=30.0` / `CRITICAL_PCT=35.0` (`engine_core.py:15-16`); C1 reuses `algo_cluster_pct` (`risk_monitor.py:950`) — no new exposure formula. ☐
4. D4/D5 cohort closed-trade streak is a NEW counter that does **not** share state with the existing per-position run-streak (`risk_monitor.py:881-893`), which stays byte-identical. ☐
5. −5R trigger explicitly stated as **Account R** (`compute_r_target`, `engine_core.py:1004`); `compute_r_true`/0.00R never shown for ALGO (invariant #1). ☐
6. ALGO cohort = `classify_stat_bucket==STAT_BUCKET_ALGO`; metrics computed in a separate function, never merged into headline. ☐
7. Headline Win-Rate/Expectancy path still gated solely by existing `is_stat_countable` (`engine_core.py:1261-1263`); no new exclusion logic. ☐
8. Rolling window = 30-deep cohort with 5/10 sub-windows (DEC-014's 20–30; §6 literal 5/10). ☐
9. #4: per-symbol §1 known stop/exit displayed instead of "Unknown"; `risk_visibility_score` (40) unchanged; honest "observed, not enforced" wording. ☐
10. #5: ALGO dead-money = §1 per-symbol time-exit; manual `_DEAD_MONEY_MAX_R=0.75` byte-identical; TSLA/JPM get NO ALGO dead-money signal; surfaces as `Review Required` note only. ☐
11. Every Governor output ≤ `Review Required`; no `Action Required`; ALGO_OBSERVED return contract (`engine_core.py:457-467`) and DEC-20260511-001 untouched; backtest caveat (§5) present on every ALGO-stat surface; no public ALGO numbers (DEC-004). ☐
12. `pytest -q` green, baseline ≥1676, drift green; includes the #8 isolation guard test below. ☐

**Explicit #8 byte-identical guard (gate-failing if violated):** a Wave-2 regression test MUST assert headline **Win-Rate and Expectancy are byte-identical with vs without ALGO trades present in the input** — run the analytics over (a) the real fixture and (b) the fixture with the founder's §2 ALGO trades injected; the two headline WR/Expectancy outputs MUST be identical to the last decimal. Any divergence = ALGO leaked into headline stats = **FAIL the gate** (AGENTS.md invariant #8; founder §7 "mandatory"). The cohort PF/expectancy/streak fixtures use the founder's real §2/§3 numbers (QQQ PF 2.29, aggregate PF 3.48, 2026 PF 0.73, max streak 12) as expected values — proving the cohort math is correct *and* segregated.

---

**Gate status:** Wave 2 may build against this doc. Build remains advisory-only, observer-mode, no R/NAV/campaign/exposure math, #8 proven by construction + guard test. Any FAIL on items 1–12 or the #8 guard blocks consolidation.
