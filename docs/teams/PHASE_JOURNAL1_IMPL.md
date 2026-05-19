# Phase JOURNAL-1 — IMPL / יישום (T-J1: SELL leg inherits campaign Setup/Quality)

**Status:** LANDED — parent-verified, full CI-equivalent post-commit on the CLEAN tree 0-failed, BUY add-on inheritance + LOCKED April + report KPIs byte-identical, no byte-locked file touched. Scope: `docs/teams/PHASE_JOURNAL1_SCOPE.md`. Code HEAD `97dbaca` on `claude/review-system-audit-FBZ2h` (scope `6e88c57`, baseline `4093ecc` post-ALGO-BT-1). No live financial values in this doc.

## What landed (the single production change)
`telegram_backlog.py` `get_next_missing` — added an `elif row.get('side','').upper() == 'SELL':` branch parallel to the existing BUY add-on inheritance. When a SELL (close) row has a `campaign_id` and its `setup_type`/`quality` is missing while the campaign's first BUY has it, the missing-on-SELL/present-on-BUY `{setup_type, quality}` are inherited from `repo.get_earlier_buys_for_campaign(...)[0]` via `repo.update_trade`, then `continue` — the SAME helper/pattern the BUY path already uses. Never writes `None`, never overwrites a value already set on the SELL; if there is no `campaign_id`, no earlier BUY, or nothing to inherit, it falls through to the existing prompt (zero regression). The genuinely close-specific fields (exit `score`, `image_url`, `management_notes`) are still asked at close. The BUY block, the `'Legacy'` skip, and the ALGO `-1` observe-only sentinel path are byte-unchanged.

## Why it was needed (founder-reported)
On PWR SELL `9521074847` the close journal re-asked "אנא סווג את האסטרטגיה (Setup)" though Setup is an entry-time, campaign-level decision the founder had already classified on the BUY. Setup/Quality are stored per-row; the BUY add-on path inherited them but the SELL path had no symmetric inheritance. The founder's intuition was correct — this was a real data-flow gap, now closed.

## Proof obligations — verified (parent, independent)
- Full suite (CI env, parent's own run): **2242 passed / 0 failed** (2229 baseline + 13 new ADD-only).
- Exact CI command POST-COMMIT on the **clean tree**: `2242 passed`, **coverage 73.04% ≥ 67%**, 0 failed.
- `git diff --name-only` ⇒ only `telegram_backlog.py` (+ new `tests/test_phase_journal1.py`). Protected set + `supabase_repository.py` (used, not modified) + `templates/*` git-diff EMPTY.
- Existing `tests/test_telegram_backlog.py` (13) passed unchanged; LOCKED April + byte-lock redteam green. No existing test deleted/weakened (Mark 6.1).
- Named proofs held: SELL+classified-BUY ⇒ both inherited, Setup+Quality prompts skipped, flow proceeds to exit-score; partial (setup only) ⇒ quality still asked; no campaign_id / unclassified BUY ⇒ existing ask, no regression; set SELL field never overwritten; BUY add-on path byte-unchanged. No schema/migration, no new message TYPE, ALGO observe-only intact.

## Deploy
Behavior-narrowing UX/data-flow fix (removes a redundant prompt by inheriting an already-founder-entered campaign property); production wiring unchanged (`docker-compose.yml` byte-identical). Standard pull-and-recreate-all-services per `docs/DEPLOYMENT_RUNBOOK.md` (host tracks the branch; full `--force-recreate` because `volumes: .:/app` + long-running Python). Effect is visible the next time the journal-completion flow runs on a SELL whose campaign BUY is already classified.
