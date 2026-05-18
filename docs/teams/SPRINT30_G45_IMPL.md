# Sprint-30 — G4 + G5 IMPL

**Status:** BUILT, parent-pending. Tree left DIRTY (no commit/push per scope).
Spec: `docs/teams/SPRINT30_SCOPE.md` (G4 §24-25, G5 §27-28).
Evidence: `SPRINT29_RESEARCH_REPORTMAP.md` (F7/F2), `SPRINT29_TESTING_REPORT_REVIEW.md`
(D1/D2), `SPRINT29_DATA_REPORT_REVIEW.md` (H3/H8). Live HEAD at build: `2db811c`.
Baseline suite 2101/0 cov 72.02%.

Strict file ownership honored: only `bot_health.py`, `telegram_formatters.py`,
`tests/test_bot_health.py` (corrected) + new `tests/test_sprint30_g45_glyph_l50.py`
touched. `engine_core.py` BYTE-LOCKED — consumed/reconstructed only, 0-diff.

---

## G4 — doubled status glyph fix (`✅ ✅` / `🔴 🟠` / `⚠️ 🟠` / `🔴 🚨`)

### Root (verified in source)

`engine_core.get_nav_with_freshness()` returns a `freshness_label` that
ALREADY begins with its own status emoji:
`✅` fresh (`engine_core.py:1617`), `🟡` stale (`:1615`), `🔴` critical
(`:1613`), `⚠️` unparseable-ts/manual (`:1626`), `🟠` no-timestamp/manual
(`:1634`), `🔴` fallback (`:1600`). `bot_health.py:25-27` `ok()/warn()/bad()`
then PREPEND a second emoji (`✅`/`⚠️`/`🔴`). Result: `✅ ✅ NAV …`, and the
two glyphs can DISAGREE — the wrapper severity is the `is_stale`/`is_critical`
ROUTING (`bot_health.py:49-54`), not the label's own leading glyph (e.g. stale
label `🟡` routed via `warn()` ⇒ `⚠️ 🟡 …`; manual `🟠` ⇒ `⚠️ 🟠 …`; the
historic test's synthetic `🚨` ⇒ `🔴 🚨 …`).

### Change — `bot_health.py` ONLY

Added module-level `_STATUS_GLYPHS` + `_strip_leading_status_glyph(msg)`
(idempotent, safe no-op on the common no-glyph message). `ok()/warn()/bad()`
now strip any leading status glyph from the message BEFORE prefixing their
single authoritative glyph. The freshness ROUTING is unchanged — it remains
the single source of the displayed severity, so for every state
(fresh/stale/critical/unknown→manual/manual-no-ts/fallback) exactly ONE
correct glyph renders and the disagreeing pair can no longer occur. The
footer tally (`bot_health.py:206-208`, counts by wrapper leading glyph) is
unaffected — the wrapper glyph is unchanged; only the message body is
stripped. The verbatim Sprint-12 missing-stops notices (which bypass the
wrapper and start `‏⚠️`) were already excluded from the tally and stay
untouched.

### Corrected mis-codifying tests — `tests/test_bot_health.py` (Mark 6.1)

`test_nav_critical_shows_red` PRE-G4 asserted BOTH `"🚨 NAV קריטי"` AND
`"🔴"` in result — i.e. it codified the DOUBLED + DISAGREEING line
`🔴 🚨 NAV קריטי` as correct. CORRECTED (not weakened): now isolates the NAV
check line and asserts the SINGLE authoritative `🔴 NAV קריטי`, label TEXT
preserved, `"🔴 🚨"`/`"🔴 🔴"` absent, `nav_line.count("🔴") == 1`, `🚨`
gone. `test_nav_stale_shows_yellow` strengthened from a bare substring to a
single-`⚠️` assertion. ADDED siblings (net +7, none deleted/weakened —
18→25 tests): stale-disagrees (`🟡`→single `⚠️`), fresh no-doubled-green,
manual-no-timestamp single-glyph (the honesty-critical line), fallback
single-`🔴`.

---

## G5 — R-ALGO-3 finish: reconcile the misleading `L50(50)` literal

### Root (verified in source)

`telegram_formatters.py:299` (was :250) printed the HARDCODED literal
`S9(9)=… | M21(21)=… | L50(50)=…` directly above the honest
`מדגם נוכחי: N/50` caveat ALGO-1 W-A3 added (`:300-304`) — an on-screen
self-contradiction (literal claims 50 while its own caveat one line down
says e.g. 9/50). The parentheticals are the window's NOMINAL size, not the
TRUE sample. `adaptive_risk_engine` builds the windows as
`disc_camps[:9]/[:21]/[:50]` and `_window_stats(...)['n'] == len(window) ==
min(window_size, len(disc_camps))` (`adaptive_risk_engine.py:283-314`,
`:463-465`, `:561-563`).

### Change — `telegram_formatters.py` (presentation-only, ZERO math)

New private helper `_score_line_window_labels(risk_rec)` returns the TRUE
per-window sample `(s9_stats['n'], m21_stats['n'], l50_stats['n'])` — the
SAME stats the Win-Rate sub-line already consumes (engine CALLED/consumed
only, `engine_core.py` 0-diff) — but ONLY when ALL THREE window-stat dicts
carry an int `n`; otherwise it returns the unchanged nominal `(9, 21, 50)`.
Wired at the single contradicting site (the `fmt_adaptive_risk_block` score
line). The heat thermometer `S9/M21/L50 [bar] score` block has no
parenthetical literal (no contradiction there) — left untouched.

### ≥50 byte-identical proof

When there ARE ≥50 closed campaigns the three windows are full ⇒
`s9_stats['n']=9`, `m21_stats['n']=21`, `l50_stats['n']=50` BY CONSTRUCTION
(`_window_stats` caps at the window size) ⇒ the helper returns exactly
`(9, 21, 50)` ⇒ the score line is **BYTE-IDENTICAL** to the pre-fix literal
and W-A3 appends NO caveat (`_l50_sample_honesty_line` returns `None` at
≥50). Proven by `test_ge_50_byte_identical_to_pre_fix_literal` /
`test_ge_50_with_larger_book_still_caps_at_nominals` (reconstructed pre-fix
literal `in out`, no caveat). When <50, every window collapses toward the
true small N ⇒ `S9(8) M21(8) L50(8)` consistent with `מדגם נוכחי: 8/50`
(no self-contradiction).

### No existing pin weakened (Mark 6.1)

The all-three-present gate is what keeps ALGO-1 green: the W-A3 fixture
`tests/test_phase_algo1_recon_and_sample.py::_risk_rec(9)` OMITS
`m21_stats` ⇒ the helper returns the nominal `(9, 21, 50)` ⇒ that test's
`_expected_l50_score_line` (literal `S9(9)…L50(50)`) still matches
byte-identically. Same for the heat fixtures
(`test_heat_in_weekly_report.py`, `test_heat_bar_mobile.py` — `s9_stats`
+ `l50_stats`, no `m21_stats`) and `test_telegram_formatters._rec`
(no `s9_score`, score-line block never entered). ALGO-1 13/13 green
post-change; LOCKED April 2/2 byte-identical.

---

## Tests delivered

- `tests/test_sprint30_g45_glyph_l50.py` (NEW, 12 tests, ADD-only):
  G4 — all SIX real freshness shapes through the REAL
  `build_health_report()`: exactly one correct freshness-routed glyph,
  no doubling, disagreeing pairs (`🔴 🟠`/`⚠️ 🟠`/`🔴 🚨`/`🟡 ⚠️`) never
  render, label text preserved, strip-helper idempotent, footer tally
  unaffected. G5 — ≥50 byte-identical to reconstructed pre-fix literal;
  <50 true per-window N with no contradiction vs the `N/50` caveat;
  per-window independence (25 ⇒ S9(9) M21(21) L50(25)); legacy
  no-`m21_stats` keeps the literal; helper unit contract; no math/KPI
  change (heat score + risk % byte-identical small vs big).
- `tests/test_bot_health.py` CORRECTED (Mark 6.1): mis-codifying
  `test_nav_critical_shows_red` fixed to assert the single-glyph correct
  form; `test_nav_stale_shows_yellow` strengthened; +5 ADD siblings.
  18 → 25 tests, none deleted/weakened.

---

## Confirmations

- **Byte-locked 0-diff:** `git diff --stat HEAD` EMPTY for `engine_core.py`,
  `analytics_engine.py`, `period_data_probe.py`, `docker-compose.yml`,
  `telegram_bot_secure_runner.py`, LOCKED
  `tests/test_real_data_april_regression.py`,
  `tests/_byte_lock_baselines/*`, `migrations/`. `engine_core.py` 0-diff
  (helper/labels CONSUMED only).
- **Only the 3 owned files touched** (+ the new test file). The other
  parallel workstreams' files present in the tree
  (`risk_monitor.py`/`telegram_portfolio.py` + their G1/G236 test files)
  were NOT modified by this workstream and were left intact (HEAD-relative
  diff verified unchanged through the isolation runs).
- **LOCKED / Sprint invariants intact:** LOCKED April 2/2 byte-identical
  (8 / +$180.49 / WR .375 / PF 2.6262 / excl 2); Sprint-22/23/24 + C1/C2/
  B3/Arch-F1/NAV-Unify/W1/W3/ALGO-1 (W-A2 recon parity + W-A3 honesty)
  green; ALGO observe-only unchanged (display/glyph-only); no new
  message/alert type; broker-fresh numbers + the ≥50 L50 line
  byte-identical.
- **Suite (G4/G5 isolated, other workstreams stashed/aside):**
  `python -m pytest -q -p no:cacheprovider` → **2117 passed, 0 failed**
  (2101 baseline + 12 new ADD + net +7 corrected bot_health, minus the
  other-workstream G1/G236 ADD files set aside for the isolation proof;
  none weakened — Mark 6.1).
- **Exact CI command (G4/G5 isolated, CI env):** `python -m pytest
  --tb=short -q --cov=engine_core --cov=adaptive_risk_engine
  --cov=analytics_engine --cov=addon_risk_engine --cov-report=term
  --cov-fail-under=67` → **2117 passed, 0 failed, cov 72.02%** (≥67).

> **Note (cross-workstream, not this scope):** the full dirty tree shows
> 9 failures in `tests/test_sprint14_alert_dedup.py` (+8 in
> `tests/test_sprint30_g236_riskmonitor.py` when its own
> `risk_monitor.py` is absent). Isolation proof: stashing ONLY the other
> workstreams' `risk_monitor.py`/`telegram_portfolio.py` (leaving the 3
> G4/G5 owned files active) ⇒ `test_sprint14_alert_dedup.py` 18/18 green
> and full suite 2117/0. The failures are attributable to the G2/G3/G6
> `risk_monitor.py` changes (a DIFFERENT, parent-verified workstream),
> NOT to G4/G5. Reported, not actioned (out of strict file ownership).
