# Sprint-30 — SCOPE / איפיון (autonomous end-to-end treatment of the Sprint-29 findings)

**Mode:** founder authorized full autonomous end-to-end (scope→build→verify→CI post-commit clean-tree→deploy-ready); return only with a deploy command. Governed, Mark-gated, per-workstream parent-verified. DOC-anchored here; code follows. Live baseline HEAD `09dbec7`, suite **2101/0 cov 72.02%**. NO live financial values in any committed doc.

## EXPLICITLY DEFERRED (founder instruction / judgment — NOT this batch)
- **SECURITY L-1 + token rotation** — founder: "לא נטפל בסודות שנחשפו — משימה סופית להמשך." Untouched here; remains the documented urgent founder/ops task.
- **OPS-1/2 (scheduled IBKR sync failures + Orange-Pi host DNS)** — root cause is host/network/IBKR-side; not safely codeable autonomously. Code-side honest disclosure already works (B1). Deferred to a founder-gated infra Phase.
- **Research F5 (on-demand April monthly renders 0/$0)** — triage-first (may be live-data scoping, not a code bug); deferred to investigation, not a blind code change.

## Binding governance (unchanged)
NO byte-locked file modified: `analytics_engine.py`, `engine_core.py` (incl. the `:1613-1634` freshness-label source — G4 fixes in `bot_health.py`, NOT here), `period_data_probe.py`, LOCKED `tests/test_real_data_april_regression.py`, all `tests/_byte_lock_baselines/*`, `docker-compose.yml`, `telegram_bot_secure_runner.py`, migrations → git-diff EMPTY. LOCKED April (8/+$180.49/WR.375/PF2.6262/excl2) + Sprint-22/23/24 + C1/C2/B3/Arch-F1/NAV-Unify/Sprint-27 W1/W3 + ALGO-1 invariants intact. ALGO stays observe-only (DEC-20260511-001 #8). No brand-new alert/message TYPE (G3/G6 reuse/upgrade EXISTING surfaces). Each workstream: build → parent independent verify → exact CI command post-commit clean tree → push.

## IN — execute

### G1 — R-ALGO-2 finish: two-surface recon reconciliation (money-truth, the real remaining closure)
ALGO-1 W-A2 fixed the חדר-מצב silently-0 key bug, but the post-deploy export still shows the **master "סיכום תיק הפיקוד" surface and the חדר-מצב surface rendering DIFFERENT recon gaps + DIFFERENT bands ("פער מהותי" vs "פער נתונים קריטי")** above a risk-raise rec. **Investigate-first:** locate BOTH recon-gap/band computation+render paths; determine the exact divergence root (different inputs? closed-only vs all? a second wrong key? band-threshold derived from the divergent number?). Then EITHER make both surfaces show the **same correct value+band** (if they should be identical) OR make the distinction **explicitly, honestly labelled** (if they legitimately measure different things) — never force a wrong equality. Money-truth: named parity/identity proof; LOCKED April byte-identical; the dashboard oracle remains the correct reference. If the root is a byte-locked file, STOP and report (re-scope).

### G2 — Alert anti-spam: state-flap re-spam fix
`risk_monitor.py` anti-spam dedups on `(symbol, state)`; a sub-threshold status oscillation (e.g. 🟡↔🔥 on <1% price wiggle) is treated as a fresh transition and bypasses the cooldown → the same campaign alert re-fires many times (one campaign 5× in ~65 lines). Fix: the cooldown/dedup must hold across a status flip that is not a *material* escalation (preserve genuine escalations + the existing escalation semantics; only suppress noise-flap re-alerts within the cooldown window). Behavior-narrowing (fewer duplicate alerts), no new alert type, observe-only ALGO unaffected; named test on a flap fixture (flap ⇒ suppressed; real escalation ⇒ still fires).

### G3 — Route the "🧭 מה עכשיו?" companion voice into the LIVE stream
Sprint-27 W3's companion line appears 0× in the 995-msg live stream (only on-demand weekly/monthly). Surface the SAME existing computed companion/"what-now" line on the high-frequency live surface (the alert/חדר-מצב path the trader actually lives), reusing the existing W3 derivation — presentation-additive, zero math, never a false all-clear, never contradicts the body. No new message type.

### G4 — Doubled status glyph (`✅ ✅` / `🔴 🟠`) fix + correct the mis-codifying test
`bot_health.py:~25-54` `ok()/warn()/bad()` re-prefix an emoji onto `engine_core.get_nav_with_freshness()` labels that already start with their own emoji (and the two can disagree). Fix in `bot_health.py` ONLY (engine_core is byte-locked — call/consume, do not modify): do not double-prefix; render exactly one correct status glyph. Correct `tests/test_bot_health.py::test_nav_critical_shows_red` (and siblings) which currently codify the doubled form as correct — assert the SINGLE-glyph correct form (Mark 6.1: corrected expectation, not weakened).

### G5 — R-ALGO-3 finish: reconcile the misleading `L50(50)` literal
`telegram_formatters.py` still prints the hardcoded `S9(9) M21(21) L50(50)` literal directly above the honest "מדגם נוכחי: N/50" disclosure ALGO-1 added — an on-screen self-contradiction. Make the score-line window labels reflect the TRUE sample N (reuse the existing `get_sample_size_context`/true-N already available) so the literal no longer contradicts its own caveat. Presentation-only, zero math; ≥50 ⇒ byte-identical.

### G6 — silence ≠ all-clear: minimal honest closure (NOT a new message type)
The risk-monitor daily digest goes silent on no-rows (a dead monitor looks identical to a calm one; 0 positive-heartbeat in 1,425). Closure: when the digest path runs and has nothing actionable, it must emit an explicit "מערכת פעילה — אין פעולה נדרשת כרגע" line on the EXISTING digest (not a brand-new periodic message) so silence is never ambiguous. Honest, additive to an existing surface, zero math.

## Separate acceptance tests
New `tests/test_sprint30_report_fixes.py` (+ the corrected `test_bot_health.py`): G1 recon parity/labelled-distinction proof + LOCKED April byte-identical; G2 flap-suppressed vs real-escalation-fires; G3 companion line present on the live surface + never false-all-clear; G4 single-glyph (all freshness states) + the corrected bot_health test; G5 ≥50 byte-identical / <50 true-N no contradiction; G6 explicit alive line on empty digest. No existing test deleted/weakened (Mark 6.1).

## Hard constraints (auto-FAIL)
Byte-locked files + baselines + migrations + compose + secure_runner git-diff EMPTY. Only the authorized presentation/honesty/anti-spam/recon-correctness behavior changes; everything else incl. broker-fresh report numbers byte-identical; ≥50 L50 byte-identical. No addition of a new alert/message TYPE. ALGO observe-only intact. Full suite `python -m pytest -q` ≥ **2101**, 0 failed (new tests only ADD). Then the EXACT CI command (`pytest --tb=short -q --cov=engine_core --cov=adaptive_risk_engine --cov=analytics_engine --cov=addon_risk_engine --cov-report=term --cov-fail-under=67`, CI env) post-commit on the clean tree → 0 failed, cov ≥67.

## Done = deploy-ready
G1–G6 landed, parent-verified, full CI-equivalent post-commit clean-tree 0-failed, LOCKED/Sprint-22/23/24 byte-identical, no byte-locked file touched, `docs/teams/SPRINT30_IMPL.md` written. Then return to the founder with ONE deploy command (+ the deferred-items reminder: L-1/token-rotation, OPS-1/2, F5).
