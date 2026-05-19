# Phase JOURNAL-1 — SCOPE / איפיון (T-J1: SELL leg inherits campaign Setup/Quality — stop the redundant close-time re-ask)

**Status:** SCOPE — founder-approved (founder reported the live redundancy on PWR SELL `9521074847`; chose "ירושת setup+quality ב-SELL"). Governed, Mark-gated, parent-verified, exact-CI post-commit on the clean tree. Live baseline HEAD `4093ecc` (post-ALGO-BT-1), suite **2229/0 cov 73.04%**. No live financial values in any committed doc.

## The defect (confirmed, narrow — founder-correct)
`Setup` (and `Quality`) are **entry-time, campaign-level** properties, decided at open. They are stored **per trade row**, not per campaign. The journal-backlog scanner `telegram_backlog.py` `get_next_missing` already encodes this for **add-on BUYs**: `:21-34` — a BUY row in a campaign with earlier BUYs **inherits** `setup_type`/`quality`/`initial_stop`/`stop_loss` from the first BUY (`repo.get_earlier_buys_for_campaign`) via `repo.update_trade` and `continue`s (never re-asks). **But there is NO symmetric inheritance for the SELL (close) leg.** A SELL row is a distinct DB row with the same `campaign_id` and its own `setup_type = NULL`; with no SELL→campaign-BUY inheritance it falls straight to `:70 if t.get('setup_type') is None:` ⇒ "אנא סווג את האסטרטגיה (Setup)" — re-asking, at close, a question the founder already answered with certainty at open. This is a real data-flow gap, not intended behavior.

## T-J1 — fix (additive, symmetric to the existing BUY inheritance)
In `get_next_missing`'s incomplete-row loop, add a **SELL branch parallel to the existing BUY branch** (`telegram_backlog.py:~21-39`): when a SELL row has `campaign_id` and its `setup_type` and/or `quality` is missing, look up the campaign's earlier BUYs with the SAME helper the BUY path uses — `repo.get_earlier_buys_for_campaign(supabase, cid, row["trade_date"])` — and **inherit ONLY the missing-on-SELL / present-on-BUY fields** of `{setup_type, quality}` from the first BUY via `repo.update_trade`, then `continue` (mirroring `:33-34` exactly). Constraints:
- Inherit ONLY `setup_type` and `quality` (the entry/campaign properties). **Never** touch the genuinely close-specific fields — exit `score`, `image_url`, `management_notes` (`:109-133`) are still asked at close (correct).
- Never write `None`/empty and never overwrite a value already set on the SELL — inherit a field ONLY if it is missing on the SELL AND present on the campaign's first BUY.
- No `campaign_id`, OR no earlier BUY, OR the BUY itself has no `setup_type`/`quality` (founder never classified at open) ⇒ **fall through to the existing ask** — unchanged fallback, zero regression (the Setup must still be captured somewhere).
- The `'Legacy'` skip (`:19`) and the ALGO BUY `-1` stop sentinel path (`:35-39`) are UNCHANGED. The Supabase write is the SAME authorized `repo.update_trade` the BUY path already performs (`:33`) — symmetric, idempotent, inherits only a founder-entered value (no fabrication); this is the journal-completion write flow, not a read-only flow (CLAUDE.md respected).

## Byte-identity / proof obligations (named)
- **BUY add-on inheritance byte-identical** — `:21-34` logic untouched; add-on BUYs behave exactly as today.
- **SELL with a classified campaign BUY** — `setup_type`+`quality` inherited onto the SELL, the Setup/Quality prompts are SKIPPED, and the close journal asks ONLY the legitimate close-time items (exit score / image / notes).
- **No false inheritance / no regression** — SELL without `campaign_id`, or campaign whose BUY lacks setup/quality ⇒ the existing ask still fires (unchanged path); a SELL that already has setup/quality is never overwritten; `None` is never written.
- No engine/R/NAV/PF/campaign-math change; no Supabase schema/migration; no new message TYPE; ALGO observe-only intact (the ALGO `-1` path unchanged). LOCKED April + Sprint-22..30/ALGO-1..3/REPORT-1/ALGO-BT-1 invariants intact (this flow is not on any of those compute paths).

## Separate acceptance tests (`tests/test_phase_journal1.py`, mirror `tests/test_telegram_backlog.py` harness)
- SELL row, campaign's first BUY has setup_type+quality ⇒ both inherited via `update_trade`, the Setup AND Quality prompts NOT sent; the next prompt is the close-specific one (exit score).
- SELL row, BUY has setup_type but NOT quality ⇒ only setup_type inherited; quality still asked (partial, correct).
- SELL row, no `campaign_id` ⇒ no inheritance, the existing Setup ask still fires (no regression).
- SELL row, campaign BUY itself has no setup_type ⇒ no inheritance, existing ask fires (no false recovery).
- SELL row already has setup_type ⇒ never overwritten; no spurious `update_trade`.
- BUY add-on path regression: a BUY with earlier campaign BUYs still inherits exactly as before (byte-identical behavior).
No existing test deleted/weakened (Mark 6.1); existing `tests/test_telegram_backlog.py` cases stay green.

## Hard constraints (auto-FAIL)
`engine_core.py`/`analytics_engine.py`/`period_data_probe.py`/LOCKED April/`tests/_byte_lock_baselines/*`/`docker-compose.yml`/`telegram_bot_secure_runner.py`/migrations git-diff EMPTY. Only `telegram_backlog.py` (small, additive SELL branch) + the new `tests/test_phase_journal1.py` change. No schema/migration, no Supabase read-only-flow mutation (this is the journal-write flow, symmetric to the existing `:33` write), no new message TYPE, ALGO observe-only intact. Full suite `python -m pytest -q` ≥ **2229**, 0 failed (new tests only ADD). Exact CI command (CI env) post-commit on the clean tree → 0 failed, cov ≥67.

## Done = deploy-ready
T-J1 landed, parent-verified, full CI-equivalent post-commit clean-tree 0-failed, BUY-inheritance + LOCKED April + report KPIs byte-identical, no byte-locked file touched, `docs/teams/PHASE_JOURNAL1_IMPL.md` written. Then return to the founder with ONE deploy command + the standing deferred reminder (L-1/token rotation, OPS-1/2) + the open Phase-2 (ALGO live-vs-backtest divergence) note.
