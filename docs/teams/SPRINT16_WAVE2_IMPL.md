# Sprint 16 Wave-2 — Implementation Record (Weekly/Monthly Report Resilience)

**Date:** 2026-05-16
**Branch:** `claude/review-system-audit-FBZ2h`
**Engineer:** Sprint-16 Wave-2 build engineer
**Severity:** HIGH — founder-facing weekly (and monthly) report aborts every Saturday 08:30 IL.
**Authoritative inputs:** `docs/teams/SPRINT16_DESIGN.md`, `docs/teams/MARK_SPRINT16_RULINGS.md`,
`docs/teams/SPRINT16_PLAN.md`, `docs/teams/INCIDENT_20260516_weekly_report.md`, `CLAUDE.md`, `AGENTS.md`.

This doc is written incrementally as the change lands. Baseline before change: **1661 passed / 0 failed**.

---

## 0. Defect recap (cited)

- `report_renderer.py:17` `from weasyprint import HTML as WeasyHTML` is **module-top**, guarded only by
  `except ImportError:` (`report_renderer.py:16–20`).
- The live failure is `OSError: cannot load library 'libgobject-2.0-0'` raised at import time from
  `weasyprint/text/ffi.py`. `OSError` is **not** an `ImportError`, so the existing guard does not catch it.
- `_run_weekly` (`report_scheduler.py:189`) imports `report_renderer` at `:198` *before*
  `build_summary_text` at `:231` and `deliver_report` at `:240`. The `OSError` propagates out of `:198`,
  out of the big `try` (`:191–246`), into the broad handler `:243–246` which logs
  `ERROR in weekly report` and calls `_notify_error`. The founder gets **nothing** — not even text.
- `_run_monthly` (`report_scheduler.py:249`) has the identical chokepoint at `:257`.

This violates AGENTS.md invariant #1 (never silently drop a founder-facing report).

---

## 1. ⟨MARK⟩ slots — resolved from `docs/teams/MARK_SPRINT16_RULINGS.md` (verbatim, nothing invented)

| Slot (SPRINT16_DESIGN §2b / §5) | Resolved value (MARK_SPRINT16_RULINGS §1 / §4) |
|---|---|
| Exact Hebrew degraded-mode line appended to the text summary | `⚠️ ה-PDF לא נוצר בריצה זו. סיכום הטקסט למעלה הוא הנתון הקובע והמלא.` (Mark §1, "Honest degraded-mode note (mandatory exact Hebrew)") |
| Whether degraded send also emits a separate `_notify_error` ops alert | **NO.** Inline `⚠️` trailer only. "No separate alert, no `_notify_error` call (that channel is for true failures only; a delivered report is not a failure)." (Mark §1 Self-flagging) |
| Ruling that `summary_ok=True, pdf_ok=False` = degraded-**success** | **SUCCESS, not failure.** "A weekly run that delivers the text summary with NO PDF is a SUCCESS … must not route to `_notify_error` … must not emit `ERROR in weekly report`." (Mark §1) |
| Log level for the degraded path | **WARNING, not ERROR.** "the degraded path MUST log at a non-ERROR level a distinct, greppable line, e.g. `WARNING weekly: PDF render failed (<exc type>: <msg[:200]>) — text summary delivered`." (Mark §1 Logging) |
| True-failure boundary (kept as a real failure → existing `_notify_error`) | summary unbuildable (analytics/account unavailable) / Telegram creds missing / summary send fails. "PDF-only failure ≠ run failure; everything-else failure = run failure." (Mark §1 True-failure boundary) |

The honest-wording constraints (Mark §1): no "temporarily" / "soon" / "will arrive later" — we do **not**
promise a future PDF. The text **is** the authoritative full report; only PDF rendering is unavailable.
The resolved Hebrew line obeys this exactly (states PDF not created; text is authoritative; nothing more).

---

## 2. Changes (file:line)

### 2a. `report_renderer.py` (P1 step 1) — lazy + broad-guarded WeasyPrint

- **`report_renderer.py:1–14`** — removed the module-top
  `try: from weasyprint import HTML … except ImportError: _WEASYPRINT_OK=False`
  block (was `:16–20`). Added `import logging` + module logger `_log`. Docstring
  updated to state the OSError rationale. `_JINJA2_OK` block kept unchanged.
- **`report_renderer.py:251–270`** — new `def _load_weasyprint()`: lazy
  `from weasyprint import HTML as WeasyHTML` inside `try`, `except Exception as e:`
  (**broad — includes `OSError`**, the live failure; NOT just `ImportError`),
  logs one `WARNING` line, returns `None`. No global side effects.
- **`report_renderer.py:303–314`** (`_render`, was `:254–258`) — replaced
  `if _WEASYPRINT_OK: …write_pdf… else: return html_path` with:
  `WeasyHTML = _load_weasyprint(); if WeasyHTML is None: return html_path;`
  then `try: …write_pdf(); return pdf_path except Exception as e: log WARNING;
  return html_path`. So ANY PDF failure (import-None / OSError / render
  exception) returns the existing `.html` dev-fallback path instead of raising.
  Jinja `_JINJA2_OK` RuntimeError boundary, template, context, KPIs, R, NAV,
  numbers — **untouched**. `build_summary_text` (`:99`) **not modified**.

### 2b. `report_scheduler.py` (P1 step 2) — local PDF guard + honest trailer

- **`report_scheduler.py:35–52`** — added module constant `_DEGRADED_PDF_NOTE`
  = Mark's exact binding Hebrew (§1 table above) and helper `_is_pdf_path(path)`
  (truthy `str` ending `.pdf`).
- **`report_scheduler.py:~230–260`** (`_run_weekly`) — wrapped ONLY the
  `render_weekly(...)` call in `try/except Exception`. On exception OR a
  non-`.pdf` return → `pdf_degraded=True`, log a **WARNING** greppable line
  (`WARNING weekly: PDF render failed (...) — text summary delivered`),
  `pdf_path=""`. `build_summary_text` (unchanged call) then runs; when degraded
  the `_DEGRADED_PDF_NOTE` trailer is appended to `summary_text` AFTER it is
  built (KPI lines untouched). `deliver_report` still runs. No `_notify_error`.
- **`report_scheduler.py:~300–335`** (`_run_monthly`) — identical wrapper around
  `render_monthly(...)` with `WARNING monthly:` log + same trailer logic.
- True-failure boundary preserved: the outer `try/except` + `_notify_error`
  (`:243–246` weekly / `:306–309` monthly equivalents) and the creds-missing
  early `return` are **unchanged** — analytics/account failure, creds missing,
  or summary-send failure still route to the existing error path.

### 2c. `report_delivery.py` (P1 step 3) — falsy/None send_pdf guard

- **`report_delivery.py:28–31`** — `if not os.path.exists(pdf_path)` →
  `if not pdf_path or not os.path.exists(pdf_path)`. The degraded path passes
  `""` (safe falsy); this guard additionally prevents
  `os.path.exists(None) → TypeError` for defence-in-depth. Falsy path ⇒ no PDF
  to send ⇒ returns `False` (existing graceful contract).

### 2d. `Dockerfile` (P2) — additive WeasyPrint native-deps layer

- **`Dockerfile:3–19`** — inserted ONE `RUN apt-get … --no-install-recommends`
  layer **between `WORKDIR /app` (`:2`) and `COPY requirements.txt .`** (now
  `:20`), installing the exact SPRINT16_DESIGN §3 set: `libpango-1.0-0
  libpangoft2-1.0-0 libharfbuzz0b libgdk-pixbuf-2.0-0 libcairo2 libffi-dev
  shared-mime-info fonts-dejavu`, ending `&& rm -rf /var/lib/apt/lists/*` in
  the **same RUN**. Base stays `python:3.10-slim` (`:1`). It is its own
  cacheable layer above pip, unaffected by app-code changes. `docker-compose.yml`
  service `command:`, `telegram_bot_secure_runner.py` — **NOT touched**.

---

## 3. Proofs / confirmations

### 3.1 "Text always sends even with WeasyPrint dead"

- `_load_weasyprint()` catches broad `Exception` incl. `OSError` → importing
  `report_renderer` can never raise (test
  `TestLoadWeasyprintGuard::test_import_report_renderer_survives_oserror`,
  `test_oserror_at_import_returns_none_no_raise`,
  `test_importerror_at_import_returns_none_no_raise`).
- `_render` returns the `.html` path on import-None or `.write_pdf` exception
  (`TestRenderDegrades`, all 3 cases).
- `_run_weekly` / `_run_monthly`: with `render_*` forced to raise `OSError`
  (and with it returning a non-`.pdf` path), `deliver_report` is STILL called
  with the full `summary_text`; `_notify_error` is NOT called
  (`TestSchedulerDegradedSuccess::test_weekly_render_raises_text_still_sent_no_notify`,
  `test_weekly_render_returns_html_path_degrades`,
  `test_monthly_render_raises_text_still_sent_no_notify`).
- **Degraded == SUCCESS** (Mark §1): no `_notify_error`, log level is
  `WARNING` (not `ERROR`), existing delivery log still fires showing
  `pdf=False`.

### 3.2 `os.path.exists(None)` handling

The degraded path sets `pdf_path = ""` (a safe falsy **string**, never `None`).
Independently, `report_delivery.send_pdf` now short-circuits on any falsy path
before `os.path.exists`, so even `None` cannot raise `TypeError`. Both proven:
`TestSendPdfFalsySafety` (`""`, `None`, and `deliver_report` text-only).

### 3.3 Zero content/number change (cryptographic proof)

`build_summary_text` output SHA-256, computed pre-change (`git stash`) vs
post-change, identical for BOTH periods:

- weekly: `c291b3a0d33ae52782911d5c44a7695ce4bf6f73a00fe3873e31c64537d2bbaa`
- monthly: `2883d9ffc1716a42eaad3ae44b478f1608ef741a382d1ea4de1bd42f369eddd5`

`build_summary_text`, `analytics_engine`, `engine_core`, `account_state`,
Sprint-15 dual-R / recon strings — untouched. The trailer is appended by the
scheduler *only when degraded*, never inside `build_summary_text`
(`TestSummaryTextByteIdentical`).

### 3.4 P1 effective with NO image rebuild (Mark §4)

P1 is pure Python (renderer lazy import + scheduler guard + delivery guard).
On the **currently-running libs-absent image**, next Saturday 08:30 IL:
`import report_renderer` succeeds → `render_weekly` returns the `.html` path →
scheduler detects non-`.pdf` → `pdf_path=""`, trailer appended → `deliver_report`
sends the founder the full text summary + `⚠️` note, no crash, no
`_notify_error`. **No Docker rebuild required.** P2 (image) only restores the
actual PDF; P1 correctness never depends on P2.

---

## 4. P2 manual rebuild / verify / rollback (image-only, not unit-testable)

Operator on the Pi, from `~/sentinel_trading`:

1. `./deploy.sh` — pulls branch + `docker compose up -d --build --force-recreate`
   (rebuilds the shared image incl. the new apt layer).
2. Verify a PDF actually renders:
   `docker compose exec -T reporting-service python3 -c "from weasyprint import HTML as H; H(string='<h1>ok</h1>').write_pdf('/tmp/_p.pdf'); import os; print('PDF_OK', os.path.getsize('/tmp/_p.pdf'))"`
   → expect `PDF_OK <bytes>`, no `OSError`.
3. (Optional) trigger / await one weekly run → founder receives BOTH text
   summary and the PDF document, no `⚠️` trailer.

**Rollback:** `git revert` the Sprint-16 hunks on
`claude/review-system-audit-FBZ2h`, then `./deploy.sh` to rebuild the prior
image. Additive only — no schema/state/migration to undo. Reverting just the
`Dockerfile` hunk + `./deploy.sh` restores the libs-absent image while P1 keeps
the report degrading safely to text-only.

---

## 5. Test delta

- New file `tests/test_report_renderer_degraded.py` — **15 tests** covering the
  design's 8 P1 cases plus the falsy/None `send_pdf` safety and the
  true-failure (creds-missing) boundary.
- Full suite: **baseline 1661 → 1676 passed / 0 failed** (`+15`).
  Drift-safe by construction (no `engine_core`/§6/math/`_RULESET` touched);
  full-suite green run covers any golden/drift assertions.
- Locked files byte-identical: `docker-compose.yml`,
  `telegram_bot_secure_runner.py`, `engine_core.py`.

— End of SPRINT16_WAVE2_IMPL.md —
