# Sprint 23 — Team-Leads Meeting (Consolidation): probe "message too long" fix

**Date:** 2026-05-16 · **Branch:** `claude/review-system-audit-FBZ2h`
**Suite:** 1864 → **1879 passed, 0 failed** (+15 split tests).

## Proven defect (closed)
`telegram_bot.py:318-320` sent `period_data_probe.build_probe_report()`'s FULL string (`_RTL + weekly + "\n\n" + _RTL + monthly`; a per-campaign line for EVERY closed campaign + the WS-C block — ~20 campaigns × 2 windows) in ONE plain-text `bot.send_message` → > Telegram 4096 → `Bad Request: message is too long` (founder hit it twice 20:22). Failed on LENGTH, not `Invalid comparison` ⇒ the Sprint-22 tz-mirror held. Pure formatting/delivery defect.

## Wave-1 commits
`b7587c5` Mark (BINDING split policy, 10-item gate) · `b981984` Arch+Engine (parse_mode-free splitter design) · `e9bdaad` Hyperscaler (no schema/infra impact).

## Parent independent verification (not agent self-report)

| Red line | Verified |
|---|---|
| **Loss-free (chunk ≠ truncate, #1)** | ✅ Read the actual `_send_probe_chunks`: split at `"\n\n"+_RTL` (the ONLY dropped byte between windows = the cosmetic `\n\n`, which becomes the natural gap between two Telegram bubbles — NO campaign row), then within a segment only at `\n` with `split_idx = nl+1` (the `\n` is kept at the END of the preceding part → byte loss-free), never mid-line/mid-campaign; an oversized single line is emitted WHOLE in its own part (loss-free dominates the size target — never truncated). Concatenating parts (minus injected per-part `_RTL`, re-inserting the cosmetic inter-window `\n\n`) reproduces the original exactly. The agent-reported boundary-`\n` fix is genuinely present and correct in the code. |
| Probe byte-identical | ✅ `git diff --quiet period_data_probe.py` clean — Sprint-22 tz-mirror + §A1 READ-ONLY + §A3 no-secrets AST contract untouched. |
| Scope | ✅ `git diff --stat` = `telegram_bot.py` ONLY (95 ins / 2 del = one additive module-level helper + the single `:319-320` send replaced). engine/analytics/scheduler 0-diff. No migration/compose/schema. New: the test + impl doc (untracked). |
| Plain-text invariant | ✅ NO `parse_mode` on ANY probe part (short-circuit single send, intermediate parts, last part) — `campaign_id` `_` cannot Markdown-break. `_send_long_message` NOT reused verbatim (only its shape mirrored). |
| RTL per part | ✅ Every part re-prefixed with `_RTL` (U+200F == `bot_core.RTL` == `period_data_probe._RTL`, parity proven at checkpoint) — each bubble renders RTL on its own. |
| markup last-only / short→single | ✅ `reply_markup=get_developer_menu()` on the LAST part ONLY; `len(text) <= 3900` → exactly ONE send, byte-identical to the pre-Sprint-23 behaviour (no regression for the common short case). |
| Admin gate / no rewrite | ✅ One additive helper + one line; the Probe handler stays inside the dev-PIN-gated region (`:147-153` untouched, not bypassed); the `except` Markdown error-path UNCHANGED; no secure_runner bypass; no new auth path; no `telegram_bot.py` wholesale rewrite. |
| Heritage | ✅ WS-C DEFERRED (not reopened); #8 ALGO, Sprint-22 tz fix, 920be95/bcf32f5/Sprint-16..22, WS-B `unlinked_*` intact. |
| Full suite | ✅ 1864 → 1879 passed, 0 failed (+15 split tests); §A1/§A3 AST contract green. |

## What Sprint-23 delivers
- **`telegram_bot.py`** — one additive module-level `_send_probe_chunks(chat_id, text)` (loss-free, plain-text, RTL-per-part, markup-last-only, per-part try/except, ≤3900, short→single send) inside the dev-PIN handler region; the single Probe-success send replaced by `return _send_probe_chunks(chat_id, txt)`. The `except` path unchanged.
- **`period_data_probe.py`** — 0-diff (the probe still NEVER sends/persists; delivery stays the caller's job per its binding contract).
- **`tests/test_sprint23_probe_split.py`** — 15 tests: loss-free/order, ≤limit, no `parse_mode`, markup last-only, short→single send, RTL-per-part, probe byte-identical, `tests/test_sprint21_wave2.py` AST READ-ONLY/no-secrets still green.

## Deployment
`cd ~/sentinel_trading && ./deploy.sh`. Then open the dev-PIN menu → **🔬 בדיקת נתוני תקופה (Probe)**: the output now arrives as multiple plain-text RTL messages (dev menu on the last), no more `message is too long`. Rollback: `git revert <range> && ./deploy.sh`.

## Carried
🟢 Live smoke-test (Sprint 11–22) CLOSED (DEC-019 reconciliation — exact vs raw Supabase). 🔴 NEW carried: founder runs the dev-PIN Probe post-deploy and confirms multi-part delivery without the 400. WS-C reconsideration (ratified `initial_risk_price` contract). NULL-`campaign_id` founder repair runbook (Sprint-21). Per-user (Phase-B). ALGO Oversight Gate (DEC-20260515-014).
