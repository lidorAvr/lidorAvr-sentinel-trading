# MARK — Sprint-22 Rulings (BINDING — gates Wave-2)

**Author:** Mark (methodology owner & team lead) · **Date:** 2026-05-16
**Branch:** `claude/review-system-audit-FBZ2h` · **Authority:** DEC-20260516-019 / SPRINT22_PLAN.md
**Scope:** `analytics_engine.compute_period_analytics` (CLAUDE.md MOST-protected — campaign aggregation) + `period_data_probe.py` mirror. Doc-only; no code; no git commit/push.

Proven root cause (DEC-20260516-019; do NOT relitigate): same `tests/test_real_data_april_regression.py::_april_df()`, REAL `compute_period_analytics` — tz-**naive** bounds → 8 campaigns/+$180.49; tz-**aware** bounds (production via `report_on_demand.py:97`/`report_scheduler.py:553` `datetime.now(sched.ISRAEL_TZ)` → `_weekly/_monthly_period`, `.replace()` preserves tzinfo) → **0/$0.00, silent all-False, no raise**. `analytics_engine.py:30` `pd.to_datetime(df["trade_date"], errors="coerce")` yields a tz-**naive** Series; the comparisons at `analytics_engine.py:54-55` (WS-B unlinked) and `:334` (`_get_closed_campaigns`) compare tz-naive Series vs tz-aware scalar → all-False (probe pre-filter RAISED — same defect, different surface).

---

## §1 — BINDING tz-normalization policy

**§1.1 Direction (DECIDED): normalize BOTH sides to tz-NAIVE.** `trade_date` from Supabase is wall-clock with no offset; `period_start/period_end` derive from Israel-local calendar arithmetic (Sun 00:00 → Sat 23:59:59 / month bounds). The window boundaries are already Israel wall-clock; the tzinfo on them is incidental, not a real UTC offset to honor. Stripping tz (NOT tz-converting) is therefore the only direction that is a provable algebraic no-op for the already-naive suite. tz-AWARE-on-both (localizing `trade_date`) is REJECTED: it would require choosing a tz for naive `trade_date`, mutating comparison semantics on the LOCKED path → forbidden by AGENTS.md #1 / "do not change campaign math without tests" / CLAUDE.md accuracy>confidence.

**§1.2 The single normalization site.** ONE normalization block at the TOP of `compute_period_analytics`, immediately AFTER `analytics_engine.py:30` (the `pd.to_datetime(df["trade_date"], errors="coerce")` line) and BEFORE the WS-B block at `:50` — i.e. between current `:30` and `:50`. It MUST:
  1. **Strip tz from `period_start`/`period_end`** when (and only when) tz-aware: if `getattr(period_start, "tzinfo", None) is not None` → `period_start = period_start.replace(tzinfo=None)`; same for `period_end`. These rebound locals are then used by EVERY downstream comparison.
  2. **Guarantee `trade_date` tz-naive post-coerce:** if `df["trade_date"].dt.tz is not None` → `df["trade_date"] = df["trade_date"].dt.tz_localize(None)`. (Defensive: today's coerce yields naive, but a future tz-aware input on either side must not silently re-introduce the defect.)

**§1.3 One site suffices for all internal comparisons — RULED.** The WS-B unlinked filter (`:54-55`) and `_get_closed_campaigns` (`:334`, called at `:72`) both consume the SAME rebound `period_start`/`period_end` locals and the SAME `df`. `_aggregate_campaigns` does Timestamp-vs-Timestamp diffs on `df` columns only (no bound comparison). Therefore the single block at §1.2 covers `:54-55`, `:72→:334`, the execution-quality `df` slice at `:120-123`, and every other in-function comparison. **No second site inside `compute_period_analytics` is permitted** (single-point fix per DEC-20260516-019).

**§1.4 `_get_closed_campaigns` own guard — RULED: NOT required, and NOT to be added.** Its only non-`compute_period_analytics` caller is `period_data_probe.py:184`, which is governed by §4 (the probe normalizes its own bounds BEFORE delegating). Adding an internal guard to `_get_closed_campaigns` would (a) duplicate logic, (b) risk a non-no-op on some naive call path, (c) widen the protected-area diff beyond the single ruled site. Keep `_get_closed_campaigns` byte-identical.

**§1.5 The NO-OP invariant (BINDING).** For any input where `period_start`/`period_end` are already tz-naive AND `trade_date` coerces to a tz-naive Series, the §1.2 block MUST be a provable algebraic identity: every branch condition is False (`tzinfo is None`, `.dt.tz is None`) → zero reassignment → byte-identical objects flow downstream. Consequence: the ENTIRE existing suite and the LOCKED `test_real_data_april_regression.py` MUST produce byte-identical results (baseline full suite **1846**, unchanged except the additive new tz test in §2).

---

## §2 — tz-aware == tz-naive regression contract (BINDING)

A NEW additive test (do NOT edit the locked `tests/test_real_data_april_regression.py` assertions; add a parametrized/sibling test reusing `_april_df()`/`_weekly_df()`/`_ACCT`) MUST assert: feeding tz-AWARE bounds (constructed via `datetime(...).replace(tzinfo=ZoneInfo("Asia/Jerusalem"))` or `sched.ISRAEL_TZ`) into the REAL `compute_period_analytics` yields EXACTLY the locked tz-naive numbers, key-for-key:

**April (`_april_df`, bounds 2026-04-01 → 2026-04-30 23:59:59):**
- `campaigns_closed == 8`
- `round(realized_pnl, 2) == 180.49`
- `win_rate == pytest.approx(0.375, abs=1e-6)`
- `profit_factor == pytest.approx(2.6262, abs=1e-3)`
- `excluded_count == 2` · `excluded_count_manual == 1` · `excluded_pnl_manual ≈ 69.34` · `excluded_count_algo == 1` · `excluded_pnl_algo ≈ -48.905`

**Weekly (`_weekly_df`, bounds 2026-05-03 → 2026-05-09 23:59:59):**
- `campaigns_closed == 0` · `excluded_count == 3` · `excluded_count_algo == 3` · `excluded_pnl_algo ≈ -37.234` · `excluded_count_manual == 0`

The test MUST assert tz-aware result `==` tz-naive result for the FULL countable KPI subset (not just spot keys) so any future drift on either path fails. The locked tz-naive test stays byte-identical and untouched.

---

## §3 — #1 anti-masking ruling (BINDING)

The fix is a **comparison-boundary** correction ONLY. It MUST NOT make a genuinely empty or failed fetch resemble "0 closes":

- **Invariant:** the honest empty-state paths remain reachable and SEMANTICALLY DISTINCT from the tz fix. Specifically: `compute_period_analytics`'s `df is None or df.empty` → `_empty()` branch (`analytics_engine.py:26-27`) and the probe's WS-A honest-empty branch (`period_data_probe.py:151-157`, `'⚠️ לא נמשכו שורות (input ריק/כשל) — … לא מוצג כ-"0 סגירות".'`) are triggered by EMPTINESS/FETCH-FAILURE, never by tz-normalization. The §1.2 block runs only AFTER the `df.empty` guard at `:26` (it sits at ≥`:31`), so an empty/None fetch still short-circuits to the honest branch BEFORE any normalization — the two concerns never interact.
- **Distinctness rule:** post-fix, a true "0 campaigns" on a NON-empty df (e.g. all-ALGO weekly — locked at `excluded_count==3`, `campaigns_closed==0`) remains a legitimate honest zero WITH its excluded disclosure; an empty/failed fetch remains "input ריק/כשל". The fix must NEVER convert the latter into the former. AGENTS.md #1 (never mask/fabricate) holds: the prior "engine PROVEN on real data" claim was a false-confidence gap that held ONLY on the tz-naive path — Wave-2 docs MUST state plainly that production NEVER exercised the proven path until this fix.

---

## §4 — Probe-mirroring requirement (BINDING)

`period_data_probe.py` filters on its OWN copy BEFORE delegating, so it must mirror §1.1/§1.2 to (a) stop raising under tz-aware `now` and (b) stay a faithful witness of the real pipeline:

- Apply the SAME tz-strip to `period_start`/`period_end` AND the same `work["trade_date"]` tz-naive guard, placed immediately AFTER the local coerce at `period_data_probe.py:164` (and the numeric coerce `:165-168`), BEFORE the first comparison at `:178`.
- This single mirrored block covers ALL three probe comparison sites: the SELL-in-window filter (`:178-179`), the delegation to `ae._get_closed_campaigns` (`:184` — now receiving normalized bounds + naive `work`), and the NULL-`campaign_id` in-window filter (`:194-195`). The probe MUST NOT raise `Invalid comparison between dtype=datetime64[ns] and datetime` under tz-aware `now`, and MUST report the same `n_sell`/`n_closed`/`n_null` the fixed engine computes.
- Probe normalization carries the SAME no-op invariant (§1.5): tz-naive `now` path of the probe stays byte-identical.

---

## §5 — Confirm UNTOUCHED (BINDING)

- **WS-C stays DEFERRED — NOT reopened** (DEC-20260516-018 UPDATE-2 / SPRINT22_PLAN "Carried"). NO `initial_stop`↔`initial_risk_price` fallback. AEHR stays DATA_INCOMPLETE/excluded; RVMD classifications unchanged. The locked `excluded_count==2` (April) proves WS-C is untouched.
- **#8 ALGO segregation untouched:** the `countable`/`manual`/`excluded` partition (`analytics_engine.py:94-117`), `ec.is_stat_countable`, `STAT_BUCKET_ALGO`, observation-only ALGO (DEC-20260511-001), and the `excluded_*_algo`/`excluded_*_manual` split — all byte-identical (no math touches them; tz-strip is pre-aggregation).
- **NO R / NAV / Expectancy / campaign-math change:** `t_risk`, `net_r`, `_aggregate_campaigns`, `get_campaign_risk_metrics`, `classify_stat_bucket`, win-rate/PF/expectancy formulas — all untouched. Only datetime comparison operands are normalized.
- **Preserved intact:** 920be95, bcf32f5, Sprint-16..21, the WS-B `unlinked_*` keys + disjoint namespace (`analytics_engine.py:50-70,221`, `_empty():403-404`), Telegram admin gate, `telegram_bot_secure_runner.py`, no `telegram_bot.py` wholesale rewrite, no migration/compose change (`verify_migrations` stays 005), single-user byte-identical.

---

## §6 — Wave-2 PASS/FAIL checklist (12 items — ALL must pass to clear the gate)

1. **One site only:** exactly one normalization block in `compute_period_analytics`, between `:30` and the WS-B block (`:50`); `_get_closed_campaigns` body byte-identical (no own guard — §1.4).
2. **Direction = tz-naive strip** (`.replace(tzinfo=None)` on bounds; `.dt.tz_localize(None)` guard on `trade_date`) — NOT tz-convert, NOT localize-to-aware (§1.1).
3. **No-op proof:** documented algebraic proof that both branch conditions are False for already-naive inputs → zero reassignment → byte-identical downstream (§1.5).
4. **tz-naive suite byte-identical:** full suite green at **≥1846**; LOCKED `test_real_data_april_regression.py` assertions UNCHANGED and passing.
5. **NEW tz-aware regression added** (additive, reuses `_april_df`/`_weekly_df`/`_ACCT`): tz-aware bounds → April 8/+$180.49/WR .375/PF 2.6262/excl 2(1 man+1 algo); weekly 0/excl 3 algo — and asserts tz-aware result `==` tz-naive result over the full countable KPI subset (§2).
6. **All callers covered by the one site:** `report_on_demand.py:112-113`, `report_scheduler.py:251`, `:363`, and `period_data_probe.py:184`-delegation — verified one engine site fixes every `compute_period_analytics` consumer.
7. **Probe mirrored:** `period_data_probe.py` block after `:164`/`:168` before `:178`; no `Invalid comparison` raise under tz-aware `now`; covers `:178-179`, `:184`, `:194-195`; probe tz-naive path byte-identical (§4).
8. **#1 honest-empty distinct:** `analytics_engine.py:26-27` `_empty()` and probe `:151-157` honest-empty branch still trigger ONLY on empty/None/failed fetch, BEFORE normalization; a genuine non-empty "0 campaigns" stays an honest zero with disclosure — never conflated (§3).
9. **No R/NAV/Expectancy/campaign-math diff:** diff confined to datetime-operand normalization + the new test + Wave-2 docs; `_aggregate_campaigns`/`ec.*`/KPI formulas untouched (§5).
10. **#8 ALGO segregation + WS-B `unlinked_*` intact:** partition and `unlinked_*`/`excluded_*` namespaces byte-identical; weekly all-ALGO case still `excluded_count_algo==3` (§5).
11. **WS-C DEFERRED, not reopened:** no `initial_risk_price` fallback; AEHR/RVMD classifications unchanged; April `excluded_count==2` (§5).
12. **No infra/protection change:** 920be95/bcf32f5/Sprint-16..21 preserved; admin gate + `secure_runner` intact; no migration/compose/`telegram_bot.py` wholesale change; host-agnostic, zero-billing, single-user byte-identical.

**GATE:** Wave-2 is cleared ONLY when all 12 pass. Any item failing → Wave-2 blocked, return to Mark. Citations: DEC-20260516-019, -018(UPDATE-2), -017, DEC-20260511-001; `analytics_engine.py:26-30,50-55,72,94-117,334,403-405`; `report_on_demand.py:96-113`; `report_scheduler.py:153-167,251,363,553`; `period_data_probe.py:151-157,163-168,178-179,184,194-195`; `tests/test_real_data_april_regression.py`.
