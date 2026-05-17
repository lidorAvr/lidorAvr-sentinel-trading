# System Review — Architecture + Adaptive UX

**Team lead:** 🏗️ Architecture + 🤝 Adaptive UX
**Branch:** `claude/review-system-audit-FBZ2h`
**Date:** 2026-05-15
**Status:** Review only. No code changes. Not committed.

This section reports the architecture and Telegram-UX state after the
Sprint 11–14 programme. Every claim below was verified against the live
modules, not just the design docs; unverifiable items are flagged.

---

## 1. Module map — what this programme added

The programme grew the system **outward into leaf modules**, never by
rewriting the core. Seven new modules were added around the old
`telegram_bot.py` and `engine_core.py`:

| Module | Lines | Role | Tier |
|---|---:|---|---|
| `open_tasks.py` | 944 | Open-Tasks engine: turns the engine's existing 10-state `compute_position_state()` into prioritized done/skip/note action items. Pure projection — caller passes engine output in. | leaf |
| `telegram_tasks.py` | 1003 | `📋 משימות פתוחות` UX: builds/caches the task list, in-place lifecycle re-render. | telegram |
| `telegram_stop_promote.py` | 435 | `🎯 קידום סטופ`: tap-only stop promotion, the ratchet-up loosen guard, batch `temp_positions` cache. | telegram |
| `telegram_clean_gate.py` | 243 | `/clean` defaulted-NO confirm gate wrapping the legacy bulk UPDATE byte-identically. | telegram |
| `telegram_audit_review.py` | 170 | `🧾 הפעולות שלי`: SELECT-only retrospective of the user's own recorded actions. | telegram |
| `state_io.py` | 101 | Atomic + `fcntl`-locked JSON state I/O; owns the shared `/app/state/risk_monitor_state.json` path constant. | leaf |
| `user_context.py` | 387 | Phase-A single-user resolver; module-level Red-Line invariants that no profile can override. | leaf |

**How they relate.** `telegram_tasks` consumes `open_tasks` which consumes
`engine_core` (constants only) + `user_context`. `telegram_clean_gate`,
`telegram_audit_review`, `telegram_stop_promote` are thin UX layers
re-exported into `telegram_bot.py` and routed from `telegram_callbacks.py`.
`state_io` is shared by `risk_monitor.py` and `bot_helpers.py` (Sprint-14
persistence fix). `audit_logger` (write path + the new SELECT-only
`read_recent_actions`) is dependency-injected, never imported as a writer
into a read flow.

**Import / leaf discipline (verified).** The pure leaves
(`open_tasks`, `state_io`, `user_context`, `audit_logger`) import only
stdlib + `engine_core` constants + each other — **no `telebot`, no
`supabase`, no `bot_core`, no `risk_monitor`, no `telegram_*`**. Supabase
(`sb`) and the audit logger are always injected, never module-level. The
telegram UX modules (`telegram_tasks`, `telegram_clean_gate`,
`telegram_audit_review`, `telegram_stop_promote`) sit one tier up and may
touch `bot_core`/`supabase`. This layering is what keeps a one-line UX
change from being able to break risk math: the math-adjacent code
physically cannot reach the bot, and the bot code physically cannot
re-derive a trading number — it can only render what the engine handed it.

**The `_RULESET` ↔ §6 drift test.** `open_tasks._RULESET` is a typed
constant transcribed verbatim from Mark's `OPEN_TASKS_METHODOLOGY_SPEC.md`
§6 machine-readable block. `tests/test_open_tasks.py::
test_ruleset_matches_methodology_spec` (verified at line 763) parses §6 and
asserts `set(spec.keys()) == set(code.keys())` plus per-entry equality of
`task_type / urgency / info_only / action_he / suppress_when`. This makes
Mark the methodology owner and fails CI loudly if the doc and the runtime
drift apart. Critically, the Sprint-12 portfolio-drawdown task (T7) and
Sprint-13 missing-stops surface were both deliberately built as **sibling
derivations outside `_RULESET`** precisely so they cannot perturb this
test — a test asserts `PORTFOLIO_DRAWDOWN` is not a `_RULESET` key
(verified, line 618-619). This is the single most important safety
invariant the programme protects.

---

## 2. Telegram UX surface (as it stands)

**Menu tree (verified in `telegram_menus.py`).**

- **Main** (`get_main_menu`, 5 categories): `📊 מצב תיק` · `🔬 ניתוח` ·
  `📚 יומן` · `❓ עזרה` · `🛠️ מפתח`.
- **Portfolio** (`get_portfolio_menu`): `📊 חדר מצב` · `📋 משימות פתוחות` ·
  `🎯 קידום סטופ` · `🌡️ משטר שוק וסיכונים` · **`🧾 הפעולות שלי`** ·
  back. The audit-review button sits in the *normal* menu (DEC-008
  intentional — a first-class self-review need), explicitly **not** in the
  developer menu.
- **Analysis** (`get_analysis_menu`): stock review · full Minervini ·
  back.
- **Journal** (`get_journal_menu`): `🔍 השלמת יומן — הפריט הבא`
  (sequential next-missing walker; label deliberately honest that it is
  *not* a browsable grouped backlog) · `🧹 ארכיון עסקאות (Legacy)` · back.
- **Developer** (`get_developer_menu`, admin-only, rate-limited): IBKR
  sync, XML upload, Git Pull+Deploy, Config, last sync, system health,
  logs, back.

**Key surfaces.**

- **`📋 משימות פתוחות` / `/tasks`** — prioritized action list from
  `open_tasks`; lifecycle (✅/⏭️/note) is tap-only and re-renders **in
  place from a cache**, with no engine re-derive (Sprint-11 §1, verified
  routing in `telegram_callbacks.py`).
- **Tap-only stop promotion** (`🎯 קידום סטופ` / `/promote`) — inline
  buttons only, no free-text stop entry; ALGO rows are filtered out of
  this flow (discretionary-only); the ratchet-up loosen requires the
  defaulted-NO `loosen_confirm` gate with an audit row written first.
- **`🧾 הפעולות שלי` / `/myactions`** — SELECT-only retrospective of the
  user's own recorded actions, friendly Hebrew, most-recent-first,
  explicit "source: audit log · no performance figures" header. No PnL /
  win-rate / R is ever computed here; no engine import in the path.
- **`/clean`** — no longer a one-tap bulk write. It now runs a read-only
  preview, sends a defaulted-NO confirm, writes an audit row first, then
  runs the **byte-identical** legacy UPDATE behind the gate; open-campaign
  rows are protected from sweep.
- **`/health`** — system-health readout including the non-numeric,
  never-counted missing-stops notice (DATA_INCOMPLETE shape; never a
  fabricated stop).
- **Cache/efficiency pattern** — the Day-3 "re-run the heavy room per
  action" anti-pattern is gone. `telegram_stop_promote`'s `temp_positions`
  batch cache and `telegram_tasks`' `tasks_cache` (bounded TTL, explicit
  🔄 refresh always re-derives, cache-miss safely falls back) mean a
  single ✅/⏭️/promote no longer pays the full
  trades-fetch + campaign-aggregation + N×network pipeline.

---

## 3. Strengths and honest debts

**Architectural strengths (verified).**

- **Additive-only growth.** Every programme feature is a new leaf/UX
  module re-exported into `telegram_bot.py` via existing import +
  routing seams. `telegram_bot.py` was **not** rewritten — it gained
  re-export lines, routing lines and one help line (verified).
- **Byte-identical write paths.** `/clean`'s bulk UPDATE and the
  stop-promote write are relocated verbatim behind gates; the field
  construction is unchanged. New guards only ever protect *more* data.
- **Engine stays the single source of truth.** No new R/NAV/exposure/
  campaign/drawdown math anywhere; the leaves re-derive nothing — they
  project the engine's own output. The `_RULESET`↔§6 drift test enforces
  Mark's methodology ownership at CI.
- **State durability fixed (Sprint-14).** The anti-spam state file was
  git-tracked and reverted by every `git pull` deploy (root cause of the
  observed alert-spam). It now lives on the persistent `sentinel_state`
  named volume via a single shared `state_io` constant, gitignored and
  `git rm --cached`-ed. The fix is a path constant + gitignore, no math
  change.

**Honest debts / risks.**

- **`telegram_bot.py` size (~740 lines).** Still the largest, most
  implicit-flow file with direct Supabase paths. Smaller than peak only
  because new logic went into leaves; it remains the fragile center and
  has not itself been decomposed.
- **Worktree-isolation-didn't-take (process, documented).** On Day 3 and
  Sprint 10 the Wave-2 build agents wrote to the shared main tree instead
  of an isolated worktree. Mitigated each time: parent verified
  independently, ran the full suite, committed by explicit file name
  (never `git add -A`), `.claude/` gitignored — no partial/foreign work
  captured. This is a recurring process fragility, not a code defect.
- **Mark-gated slots are doc-time placeholders.** Sprint 13/14 designs
  carry many `⟨MARK:…⟩` slots; Sprint 13/14 Wave-2 shipped only where
  Mark's rulings had landed. Any unverified slot is a *deferred*, not
  done, item — flagged here as not independently verifiable from code.
- **Cross-container state RMW residual.** `state_io` removes the
  catastrophic torn-read/empty-reset modes, but a `runner_decision` the
  bot writes mid-cycle can still be overshadowed by risk-monitor's
  end-of-cycle save (documented; full fix is Hyperscaler Phase B,
  state→DB).
- **Test baseline.** 1638 tests collected (verified via `pytest --co`);
  full green run not re-executed in this review (collection only).

---

## 4. Top-3 architecture follow-ups (list only — no work now)

1. **Decompose `telegram_bot.py`.** Continue the proven leaf-extraction
   direction — pull the remaining message-routing dispatch and direct
   Supabase write paths into small, testable modules; the file is still
   the single biggest fragility.
2. **Move runtime state to the DB (Hyperscaler Phase B).** Close the
   `state_io` RMW residual and remove the last dependence on the host
   working tree for anti-spam/runner-decision durability.
3. **Generalize the `_RULESET`↔spec drift test.** Extend the same
   doc↔runtime lockstep guard to the other Mark-owned constant surfaces
   (cooldown tiers, ALGO/DATA_INCOMPLETE exclusion sets) so methodology
   ownership is CI-enforced everywhere, not only Open Tasks.

— Architecture + Adaptive UX
