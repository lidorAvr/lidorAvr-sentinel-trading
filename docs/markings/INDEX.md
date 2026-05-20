# MARK Rulings — Index

**Purpose.** Mark is the internal architect/reviewer who issues design
rulings cited verbatim from production code (`# Sprint-12 / Mark §3 ...`,
`# MARK_SPRINT15_RULINGS.md §1`, etc.). Before F12 (Meeting 21/05/2026)
these rulings existed only as scattered files under `docs/teams/` mixed
with marketing/team-meeting notes — discovery required guessing the
sprint number. The external advisory team (Yoav) flagged this as
opaque: "Mark becomes an internal regulator with no decisions board."

This file is the **discoverable index**. It does NOT move any ruling
file (that would break the verbatim path-references in code comments).
It catalogs them with one-line topic summaries so a future agent can
answer "what did Mark already rule on?" in 30 seconds.

> **Where the files live.** All ruling files remain at
> `docs/teams/MARK_SPRINT<N>_RULINGS.md`. References from code
> (`telegram_formatters.py`, `analytics_engine.py`, etc.) point there
> verbatim and are NOT updated by F12.

---

## Rulings catalog

| Sprint | File | Topic (one line) | Cited from |
|---|---|---|---|
| 11 | [`docs/teams/MARK_SPRINT11_RULINGS.md`](../teams/MARK_SPRINT11_RULINGS.md) | Open-tasks lifecycle + COMPLETE_RISK_DATA exclusion from WR/Expectancy | `telegram_formatters.py` §13/2 |
| 12 | [`docs/teams/MARK_SPRINT12_RULINGS.md`](../teams/MARK_SPRINT12_RULINGS.md) | Single canonical `PRICE_FALLBACK_LABEL` for live-price→entry fallback | `telegram_formatters.py:10-15`, `telegram_portfolio.py` |
| 13 | [`docs/teams/MARK_SPRINT13_RULINGS.md`](../teams/MARK_SPRINT13_RULINGS.md) | Missing-stop split: OPEN (urgent backlog) vs CLOSED (hygiene /clean only) | `telegram_formatters.py:579-693` |
| 14 | [`docs/teams/MARK_SPRINT14_RULINGS.md`](../teams/MARK_SPRINT14_RULINGS.md) | (see file for §-by-§ topics) | — |
| 15 | [`docs/teams/MARK_SPRINT15_RULINGS.md`](../teams/MARK_SPRINT15_RULINGS.md) | Dual-R (Structure / Account) + Risk Capital Basis + Broker Reconciliation bands | `telegram_formatters.py:697-909`, `dashboard.py`, `report_renderer.py` |
| 16 | [`docs/teams/MARK_SPRINT16_RULINGS.md`](../teams/MARK_SPRINT16_RULINGS.md) | (see file) | — |
| 17 | [`docs/teams/MARK_SPRINT17_RULINGS.md`](../teams/MARK_SPRINT17_RULINGS.md) | On-demand last-period report (dev/testing — never snap_save) | `telegram_menus.py` "📈 דוח שבועי עכשיו" |
| 18 | [`docs/teams/MARK_SPRINT18_RULINGS.md`](../teams/MARK_SPRINT18_RULINGS.md) | (see file) | — |
| 19 | [`docs/teams/MARK_SPRINT19_RULINGS.md`](../teams/MARK_SPRINT19_RULINGS.md) | (see file) | — |
| 20 | [`docs/teams/MARK_SPRINT20_RULINGS.md`](../teams/MARK_SPRINT20_RULINGS.md) | (see file) | — |
| 21 | [`docs/teams/MARK_SPRINT21_RULINGS.md`](../teams/MARK_SPRINT21_RULINGS.md) | WS-A pure-read-only period-data probe (no write / no snap_save / no secrets) | `telegram_menus.py` "🔬 בדיקת נתוני תקופה" |
| 22 | [`docs/teams/MARK_SPRINT22_RULINGS.md`](../teams/MARK_SPRINT22_RULINGS.md) | (see file) | — |
| 23 | [`docs/teams/MARK_SPRINT23_RULINGS.md`](../teams/MARK_SPRINT23_RULINGS.md) | (see file) | — |
| 24 | [`docs/teams/MARK_SPRINT24_RULINGS.md`](../teams/MARK_SPRINT24_RULINGS.md) | analytics_engine append-only constraint; period-window any-SELL-in-window doctrine | `analytics_engine.py`, `docs/DATA_CONTRACTS.md` (closed-campaign window invariant) |
| 25 | [`docs/teams/MARK_SPRINT25_RULINGS.md`](../teams/MARK_SPRINT25_RULINGS.md) | DEV_PIN fail-CLOSED gate; byte-lock baseline framework (`tests/_byte_lock_baselines/`) | `telegram_bot.py:307-326`, `tests/test_sprint25_byte_lock_redteam.py` |

## Sub-rulings (non-sprint)

| File | Topic |
|---|---|
| [`docs/teams/MARK_DAY3_GUARDRAILS.md`](../teams/MARK_DAY3_GUARDRAILS.md) | Day-3 UX audit guardrails (stop-promote / fallback labels) |
| [`docs/teams/MARK_ALIGNMENT_REVIEW.md`](../teams/MARK_ALIGNMENT_REVIEW.md) | Cross-sprint alignment review (decisions index) |
| [`docs/teams/REVIEW_MARK_FUNCTIONS.md`](../teams/REVIEW_MARK_FUNCTIONS.md) | Mark's functional review process |

---

## How to use this index

**Looking for the decision behind a code comment?**
Code comments reference Mark by sprint+section: `# Sprint-12 / Mark §3`.
Find sprint 12 above, click through, read §3.

**Adding a new Mark ruling?**
1. Add the ruling file at `docs/teams/MARK_SPRINT<N>_RULINGS.md`.
2. Add a row to the catalog above with the one-line topic.
3. The row should name the production file(s) that cite the ruling.

**Promoting a ruling to production rule?**
A Mark ruling lives in `docs/teams/`; once it stabilizes into an
invariant (LOCKED-April-style), it migrates to
`docs/DATA_CONTRACTS.md` or `docs/SAFE_CHANGE_PROTOCOL.md` and the
ruling file becomes the historical record.
