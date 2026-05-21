# MEETING — Status Taxonomy: ENGINE Discipline Plan

Binding engine-side plan for the position "סטטוס שוק" classifier regression. READ-ONLY output.

## Root-cause confirmed

The bug fires in `engine_core.py:369` inside `map_score_to_status(score, hard_rule=None, features=None)` (def at `engine_core.py:366`):

```
status = "🔴 Broken"          # engine_core.py:369  ← DEFAULT
if score >= 85: status = "🔥 Power"     # :370
elif score >= 70: status = "🟢 Healthy" # :371
elif score >= 55: status = "🟡 Yellow Flag"  # :372
elif score >= 40: status = "🟠 Weak"    # :373
```

`score_position()` (`engine_core.py:335-364`) collapses many independent signals (MA breaks, distribution, RS, time_efficiency, dist_from_high_20, atr down-moves, stage penalties) into a single 0–95 integer. Any cumulative low score — whether from a brand-new position that has not yet developed MA structure, from a stalled position with `time_efficiency=="dead_money"` (−12 at `:350`), or from genuine structural break — lands in the SAME default bucket at `:369`. The function has no `age_days`, no `open_r`, and no `violation_score` input, so it cannot distinguish "no time to develop" / "no movement" / "actively broken".

JPM case (age=1, open_R=−0.01): score is depressed by RS terms (`:345-346`) and one bad close, scoring ~30s, → falls through to `:369` → "🔴 Broken". Wrong. PLTR case (age=20, open_R=−0.25): score is depressed by `time_efficiency=="dead_money"` (`:350`, −12) and `dist_from_high_20 <= -8` (`:348`, −8), → also `:369` → "🔴 Broken". Wrong (it is stalled, not structurally broken).

Note: `compute_position_state` (`engine_core.py:2047-2158`) already has a richer 10-state taxonomy (DEAD_MONEY at `:2140-2145`, NEW at `:2153-2154`, PROVING at `:2148-2150`, BROKEN gated by `violation_score >= _VIOLATION_BROKEN=6` at `:2104-2106`). That is a parallel classifier surfaced as "position state". The Telegram card "סטטוס שוק" comes from `map_score_to_status` (the score-bucket classifier) — `evaluate_position_engine` returns `status` via `engine_core.py:460` and `:479`. Both classifiers must agree on the BROKEN claim; today they don't.

## Signal axes available

From `compute_score_from_features` features dict (built in `engine_core.py` indicators chain, consumed at `:336-364`):

- `age_days` — calendar days since first trade (already known to `evaluate_position_engine` at `engine_core.py:429`, just not passed to `map_score_to_status`).
- `open_r` / `total_r` — passed to `evaluate_position_engine` (`:423`), available at call site `:460`, not currently forwarded.
- `violation_score` — cumulative violation points (already used by `compute_position_state` at `:2104`).
- `has_new_high_since_entry` — boolean (already a `compute_position_state` input, `:2059`).
- `features["dist_from_high_20"]` (`:347-348`), `features["bad_closes_10"]` / `"good_closes_10"` (`:340-341`, `:376`), `features["dist_8d"]` / `"dist_12d"` (`:324-325`, `:343-344`), `features["time_efficiency"]` (`:349-351`).
- `hard_rule` already short-circuits at `:367` (stop_breach / 3-of-12 dist / runner_ma20_break → real Broken).

Any new logic must consume these axes WITHOUT changing `score_position` math (byte-lock).

## Proposed new tags + predicates

Four new tags. Each predicate is a CLAMP on the existing default branch (`:369`). They only fire when score < 40 AND no `hard_rule` matched. Order is top-to-bottom; first match wins.

### Tag 1 — "🆕 New / Watching"

Precondition: `score < 40` AND `hard_rule is None`.

Predicate (ALL must hold):
- `age_days is not None AND age_days <= 3`
- `abs(open_r) <= 0.5`  (no real move yet, either way)
- `features.get("dist_12d", 0) < 3` (else `hard_rule` would already have fired at `:325`)
- `features.get("violation_score", 0) < 3` (no significant structural events accrued)

Rationale: too fresh to call. Mirrors `_NEW_MAX_DAYS=2` (`engine_core.py:1788`) but extended by 1 day to account for noise on day-3. Below `_PROVING_MIN_DAYS=3` lower bound? Use `<= 3` (inclusive) — see mutual-exclusivity proof below.

### Tag 2 — "⏳ Stalled / Dead Money"

Precondition: `score < 40` AND Tag 1 did NOT fire AND `hard_rule is None`.

Predicate (ALL must hold):
- `age_days is not None AND age_days >= 8`
- `-0.5 <= open_r <= 0.75`  (flat — mirrors `_DEAD_MONEY_MIN_R / MAX_R` at `engine_core.py:1781-1782`)
- `features.get("has_new_high_since_entry", True) is False`  (never made a new high after entry)
- `features.get("violation_score", 0) < 4`  (structural events below Broken cutoff `_VIOLATION_BROKEN=6` at `:1792`, with a margin)

Rationale: matches the existing DEAD_MONEY definition in `compute_position_state` (`:2140-2145`) — same thresholds, same axis interpretation. Keeps the two classifiers in lock-step.

### Tag 3 — "🟠 Weak (active deterioration)"

NO CHANGE. The existing `score >= 40` branch at `engine_core.py:373` stays as today. Documented here for completeness — this is the legitimate "actively deteriorating but not broken" bucket. Score 40-55, MA breaks accumulating, no hard rule. Predicate: `40 <= score < 55 AND hard_rule is None`. Mutually exclusive by score band.

### Tag 4 — "🔴 Broken" (narrowed)

Precondition: `score < 40` AND Tag 1 did NOT fire AND Tag 2 did NOT fire.

Predicate (ANY one suffices — disjunction):
- `hard_rule is not None` (already handled at `:367`, listed for completeness)
- `features.get("violation_score", 0) >= 6`  (matches `_VIOLATION_BROKEN` at `:1792`)
- `features.get("dist_12d", 0) >= 3`  (also caught by `hard_rule` at `:325`; defence-in-depth)
- DEFAULT FALLBACK: `score < 40 AND Tag 1 false AND Tag 2 false` → still "🔴 Broken".

Critical: the DEFAULT FALLBACK preserves byte-lock. When age/open_r/violation_score are unknown OR positions look neither fresh nor stalled, "🔴 Broken" remains the answer. Today's behavior is the WORST case of the new logic, not the AVERAGE.

## Mutual exclusivity proof

Tags 1, 2 partition the `score < 40 AND hard_rule is None` space via `age_days`:
- Tag 1 fires only if `age_days <= 3`.
- Tag 2 fires only if `age_days >= 8`.
- The gap `4 <= age_days <= 7` falls through to Tag 4 (Broken default) — this matches `_PROVING_MIN_DAYS=3, _PROVING_MAX_DAYS=7` (`engine_core.py:1786-1787`). A score < 40 position in proving window with no fresh/stall signal is legitimately concerning.
- Tag 4 (Broken disjuncts) and Tag 2 are exclusive via `violation_score`: Tag 2 requires `violation_score < 4`; Tag 4-via-violation requires `>= 6`. Gap `4-5` falls through to Broken (consistent with `_VIOLATION_YELLOW_FLAG=2` at `:1791` — a position with violations in the 4-5 range is past Yellow but not yet hard-Broken; treating it as Broken is the conservative call).
- Tag 1 cannot overlap Tag 2: `age_days <= 3` vs `age_days >= 8` are disjoint.
- Existing score-band tags (Power ≥85, Healthy 70-84, Yellow Flag 55-69, Weak 40-54) are untouched.

Ordering is deterministic: hard_rule → Power → Healthy → Yellow Flag (incl. `bad_closes` override at `:375-377`) → Weak → Tag 1 (New) → Tag 2 (Stalled) → Tag 4 (Broken default).

## New `map_score_to_status` signature + back-compat

Current (`engine_core.py:366`):
```
def map_score_to_status(score, hard_rule=None, features=None):
```

Proposed:
```
def map_score_to_status(score, hard_rule=None, features=None,
                        age_days=None, open_r=None,
                        violation_score=None, has_new_high_since_entry=None):
```

Back-compat rules:
- All new params default to `None`. When ANY of `age_days`, `open_r` is `None`, Tag 1 and Tag 2 logic is SKIPPED — behavior collapses to today's mapping exactly (byte-identical).
- `violation_score` defaults to `features.get("violation_score", 0)` if `features` is provided, else `None` (no effect).
- `has_new_high_since_entry` defaults to `features.get("has_new_high_since_entry", True)` if provided, else `True` (benefit of the doubt — same as `compute_position_state` at `:2059`).
- The ONLY in-tree caller is `engine_core.py:460`. That call site must be updated to forward `age_days=days_held` (already computed at `:429`), `open_r=total_r` (parameter at `:423`), and `violation_score` if available in `features`.
- Tests or external callers that pass only `(score, hard_rule, features)` see ZERO behavior change.

## Required tests

New file `tests/test_status_taxonomy.py`. Per-predicate, ≥2 cases each (positive + negative boundary).

### Tag 1 (New / Watching) — 3 cases
1. POSITIVE: `score=30, age_days=1, open_r=-0.01, features={dist_12d:0, violation_score:0}` → expect "🆕 New / Watching".
2. NEGATIVE (boundary): `score=30, age_days=4, open_r=-0.01, features={dist_12d:0, violation_score:0}` → expect "🔴 Broken" (just past fresh window).
3. NEGATIVE (R out of band): `score=30, age_days=1, open_r=-0.8, features={dist_12d:0, violation_score:0}` → expect "🔴 Broken" (real move, not just-fresh).

### Tag 2 (Stalled / Dead Money) — 3 cases
1. POSITIVE: `score=30, age_days=20, open_r=-0.25, has_new_high_since_entry=False, features={violation_score:1}` → expect "⏳ Stalled / Dead Money" (PLTR case).
2. NEGATIVE (age boundary): `score=30, age_days=7, open_r=-0.25, has_new_high_since_entry=False` → expect "🔴 Broken" (one day below threshold).
3. NEGATIVE (made new high): `score=30, age_days=20, open_r=-0.25, has_new_high_since_entry=True` → expect "🔴 Broken" (had momentum, lost it → not stalled, actually broken).

### Tag 4 (Broken — narrowed) — 3 cases
1. POSITIVE via `violation_score`: `score=30, age_days=15, open_r=0.0, features={violation_score:7}` → "🔴 Broken".
2. POSITIVE via DEFAULT FALLBACK: `score=30, age_days=5, open_r=-0.3` (proving-window gap) → "🔴 Broken".
3. NEGATIVE: `score=42, age_days=5, open_r=-0.3` → "🟠 Weak" (score band wins, taxonomy untouched).

### JPM regression test
`score=35, age_days=1, open_r=-0.01, features={dist_12d:0, bad_closes_10:1, good_closes_10:0, violation_score:0}` → expect "🆕 New / Watching", NOT "🔴 Broken".

### PLTR regression test
`score=32, age_days=20, open_r=-0.25, has_new_high_since_entry=False, features={time_efficiency:"dead_money", dist_from_high_20:-10, violation_score:1}` → expect "⏳ Stalled / Dead Money", NOT "🔴 Broken".

### Back-compat byte-lock
- `map_score_to_status(score=30)` → "🔴 Broken" (no new args).
- `map_score_to_status(score=30, features={...})` (no age/r) → "🔴 Broken".
- `map_score_to_status(score=75, features={bad_closes_10:5, good_closes_10:2})` → "🟡 תקין אך במעקב" (existing override at `:375-377` preserved).
- All existing Power/Healthy/Yellow/Weak score-band tests pass byte-identical.

## Byte-lock implications

- `score_position` (`engine_core.py:335-364`): NOT TOUCHED. All score-band tests pass identically.
- `evaluate_hard_rules` (`:316-333`): NOT TOUCHED. Stop-breach, 3-of-12 distribution, runner-MA20-break, climactic all keep firing the same "🔴 Broken" / "⚠️ Climactic" / "🚨" statuses.
- `build_management_action` (`:381-421`): currently switches on the status string. New tags "🆕 New / Watching" and "⏳ Stalled / Dead Money" will not match any existing branch and fall through to the implicit default (`action="מעקב", trigger=""` from `:384`). This is the SAFE default — no aggressive stop change, no premature exit signal. A follow-up sprint can add explicit branches; not required for this fix.
- `tests/test_sprint30_g236_riskmonitor.py:86` (`_BROKEN = "🔴 Broken"`) and `tests/test_sprint14_alert_dedup.py:209,219` (alert dedup on "🔴 Broken"): all use the LITERAL string. The new tags are additional values, not replacements. Byte-identical.
- LOCKED April fixture (`tests/test_sprint24_b1b3_byte_identical.py:74-77`, `tests/test_phase_algo2.py:378-398`): April positions either have hard_rules firing OR were not score<40-with-age-≤3 OR were not stalled-with-no-new-high — verify by running `pytest -q tests/test_sprint24_b1b3_byte_identical.py` post-implementation. If any April row newly classifies as Tag 1 or Tag 2, the implementation has a bug (must roll back).
- Byte-lock baseline at `tests/_byte_lock_baselines/engine_core.py.baseline` will need re-pinning AFTER implementation by the testing discipline — not by engine.

## Sign-off

Engine plan is binding on the implementer. Thresholds (`age_days <= 3`, `abs(open_r) <= 0.5`, `age_days >= 8`, `-0.5 <= open_r <= 0.75`, `violation_score < 4` for Tag 2, `violation_score >= 6` for Tag 4-disjunct, `has_new_high_since_entry == False` for Tag 2) are EXACT and must not drift during implementation. Any threshold change requires a new meeting. The default fallback to "🔴 Broken" is REQUIRED for byte-lock and must not be removed.

Top engineering risk: the call-site at `engine_core.py:460` must successfully forward `age_days` and `open_r` — these are computed at `:429` (`days_held`) and passed in as `total_r` at `:423`. If either is missing, Tag 1 / Tag 2 silently never fire and we ship the bug fix as a no-op. Implementer MUST add a test that the call-site forwards these (assert via mock or via end-to-end on `evaluate_position_engine`).
