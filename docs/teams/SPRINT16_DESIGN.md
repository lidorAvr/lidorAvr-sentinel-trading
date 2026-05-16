# Sprint 16 — Architecture + Infra Design (Weekly-Report Resilience)

**Date:** 2026-05-16
**Branch:** `claude/review-system-audit-FBZ2h`
**Severity:** HIGH — founder-facing weekly report aborts every Saturday 08:30 IL.
**Authors:** Architecture + Infra (folds the System/Infra image-size data point).
**Scope:** ONE design doc. No production code change in this deliverable. Wave-2 builds from this.
**Inputs read:** `docs/teams/SPRINT16_PLAN.md`, `docs/teams/INCIDENT_20260516_weekly_report.md`, `CLAUDE.md`, `AGENTS.md`, `report_renderer.py`, `report_scheduler.py`, `report_delivery.py`, `Dockerfile`, `docker-compose.yml` (read-only), `deploy.sh`.
**Mark gate:** `docs/teams/MARK_SPRINT16_RULINGS.md` is **absent** at authoring time (parallel Wave 1, as the plan predicted). All wording/policy decisions Mark must rule are left as verbatim `⟨MARK:…⟩` slots. Wave 2 MUST NOT build the degraded-message text or the "degraded = success" policy until Mark's ruling fills these slots. No wording is invented here.

---

## 1. Failure trace (file:line) — proof the whole run aborts, no text

Exact call chain on 2026-05-16 08:30:10 (matches the live traceback in the incident):

1. `report_scheduler.py:405 main()` loop → schedule match (Sat 08:30) → `report_scheduler.py:420` calls `_run_weekly(now)`.
2. `report_scheduler.py:189 _run_weekly` enters its `try:` at `:191`.
3. `report_scheduler.py:198` executes `from report_renderer import render_weekly, build_summary_text`.
4. Importing `report_renderer` runs the module body. **`report_renderer.py:17` `from weasyprint import HTML as WeasyHTML`** is at **module top**, NOT inside the `try/except ImportError` semantics that would survive a *native* load failure.
   - Note: the `try/except ImportError` at `report_renderer.py:16–20` only catches `ImportError`. The live failure is **`OSError: cannot load library 'libgobject-2.0-0'`** raised from `weasyprint/text/ffi.py` at import time. `OSError` is **not** an `ImportError`, so the `except ImportError` does **not** catch it. The exception propagates out of the `import` statement.
5. The `OSError` propagates out of line `:198`, out of the `_run_weekly` `try`, and is caught by the broad handler at **`report_scheduler.py:243–246`**: it logs `ERROR in weekly report:` and calls `_notify_error(...)`.

**Consequence:** Because the failing line is the `import` at `report_scheduler.py:198`, **every** statement after it in `_run_weekly` is skipped — including the analytics computation (`:207`), `build_summary_text(...)` (`:231`), and `deliver_report(...)` (`:240`). The trader receives **no text summary and no PDF** — only the `_notify_error` red alert (`report_scheduler.py:387 _notify_error`). This violates AGENTS.md invariant #1 ("never silently drop a founder-facing report" / no fabricated-or-absent founder report). The monthly path `_run_monthly` (`report_scheduler.py:257`) imports `report_renderer` the same way (`from report_renderer import render_monthly, build_summary_text`) and shares the identical module-top failure; the fix below is module-level so it covers monthly automatically.

### Send-text path that MUST remain reachable

The text summary is independent of WeasyPrint and only needs analytics + Jinja-free string building:

- `report_scheduler.py:207` `analytics = compute_period_analytics(...)` — no WeasyPrint.
- `report_scheduler.py:231` `summary_text = build_summary_text(analytics, period_label, "weekly", risk_rec=risk_rec)` → `report_renderer.py:99 build_summary_text` — pure Python/f-strings, **zero WeasyPrint reference**.
- `report_scheduler.py:240` `result = deliver_report(pdf_path, summary_text, caption, chat_id, token)` → `report_delivery.py:50 deliver_report` → `report_delivery.py:56 send_summary(...)` (text via `sendMessage`) is **already independent** of `send_pdf` (`report_delivery.py:57`); `send_pdf` already returns `False` gracefully if the path is missing (`report_delivery.py:28`).

So the only thing blocking the text path is the **module-top import** at `report_renderer.py:17`. Remove that single chokepoint and the existing delivery split already degrades correctly.

---

## 2. P1 — Guarded lazy import + degraded path (minimal diff, no content/number change)

**Goal:** `report_renderer` must always import successfully even when WeasyPrint's native libs are missing; PDF failure (import OR render) must NOT prevent `build_summary_text` → `deliver_report` → text send; a text-only delivery counts as success.

### 2a. `report_renderer.py` — make the WeasyPrint import lazy and broaden the guard

**Change 1 — replace module-top import (lines 16–20).** Do NOT import `weasyprint` at module top at all. Replace the current block with a lazy loader so import-time native failures cannot abort any importer:

- Delete the module-top `from weasyprint import HTML as WeasyHTML` / `_WEASYPRINT_OK` block (`report_renderer.py:16–20`).
- Add a private helper (placed near the other internals, e.g. after `_render` ~`:259`):
  - `def _load_weasyprint():` — `try: from weasyprint import HTML as WeasyHTML; return WeasyHTML` `except Exception as e:` (broad `Exception`, **not** just `ImportError`, because the real failure is `OSError`) `return None`. It MUST catch `OSError`/`Exception`, log a one-line reason, and return `None`. No global side effects.

**Change 2 — guard the only use site (`_render`, `report_renderer.py:254–258`).** Currently:
```
if _WEASYPRINT_OK:
    WeasyHTML(string=html_str, base_url=_TEMPLATES_DIR).write_pdf(pdf_path)
    return pdf_path
else:
    return html_path
```
Replace `_WEASYPRINT_OK` with a call to `_load_weasyprint()`; wrap the `.write_pdf()` in `try/except Exception`. On import-None **or** render exception: log the reason and `return html_path` (existing dev-fallback behaviour — `_render` already returns `html_path` when PDF is unavailable). **No template, context, KPI, R, NAV, or number is touched** — only which file path is returned. This is the entire renderer-side diff: ~1 block replaced + 1 helper added + 1 `if` condition changed. `build_summary_text` (`:99`) is **not modified**.

Net effect: `render_weekly` (`:60` → `_render`) and `render_monthly` (`:96` → `_render`) now **return an `.html` path instead of raising** when PDF is unavailable. `report_delivery.send_pdf` (`report_delivery.py:28`) already returns `False` for a non-`.pdf`/non-existent doc, so no crash downstream. (Optionally `send_pdf` could skip non-`.pdf` files explicitly — flagged as a Wave-2 nicety, not required for correctness.)

### 2b. `report_scheduler.py` — isolate PDF failure from the text send + degraded note

Today `_run_weekly` is one big `try` (`:191–246`); the `import` at `:198` and `render_weekly` at `:215` sit in the same scope as the text send (`:231`/`:240`). With 2a, the import no longer raises, so the run already proceeds. To make the contract explicit and to attach Mark's honest note, wrap **only the renderer call** in its own guard:

- Around `report_scheduler.py:215–225` (`pdf_path = render_weekly(...)`): wrap in `try/except Exception`. On success: `pdf_path` as today. On exception: log `WARN: PDF render failed, sending text-only weekly: <e>`; set `pdf_path = None`; set a degraded flag.
- Mirror the same wrapper around `report_scheduler.py:275–286` (`render_monthly`) in `_run_monthly`.
- Degraded-mode note: when degraded, **append Mark's honest line to `summary_text`** (after `:231` builds it). The exact Hebrew wording and whether to also fire a separate ops alert are Mark's call:
  - `⟨MARK: exact Hebrew degraded-mode line appended to the weekly/monthly text summary stating the PDF is temporarily unavailable, honest, no optimistic/fabricated claim — AGENTS.md #1 / CLAUDE.md "clear about fallback/cached data". Short, direct, RTL-friendly.⟩`
  - `⟨MARK: whether a degraded (text-only) delivery should ALSO emit a separate ops/error alert via _notify_error, or only the inline note (avoid double-pinging the founder).⟩`
- Success accounting: `deliver_report` returns `{"summary_ok", "pdf_ok"}` (`report_delivery.py:58`). The run logs delivery at `report_scheduler.py:241`. Per plan, a degraded send is a **success of the run**:
  - `⟨MARK: ruling that the weekly/monthly RUN is considered SUCCESSFUL when summary_ok is True even if pdf_ok is False (text-only = degraded-success, NOT a failure / NOT a _notify_error). Defines the pass condition for the test in §4.⟩`
- `pdf_path = None` flows safely into `snap_save(...)` (`report_scheduler.py:227`) and `deliver_report(...)` (`:240`) — `send_pdf` already handles a missing/None path by returning `False` (`report_delivery.py:28`); confirm `snap_save` tolerates `pdf_path=None` (Wave-2 verify; if it does not, pass `pdf_path or ""`).

**Diff size:** renderer ≈ 1 block + 1 helper + 1 condition; scheduler ≈ 2 small `try/except` wrappers + 1 conditional append. No math, no template, no number, no schedule, no `command:` touched.

---

## 3. P2 — Dockerfile native deps for WeasyPrint

Base image is `python:3.10-slim` (`Dockerfile:1`). It ships none of WeasyPrint's GObject/Pango/Cairo/gdk-pixbuf stack — root cause of the `OSError`.

**Exact apt step (insert BEFORE the pip step, i.e. between `Dockerfile:2 WORKDIR /app` and `Dockerfile:3 COPY requirements.txt .` — so it is its own cacheable layer above pip and unaffected by app-code changes):**

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpango-1.0-0 \
        libpangoft2-1.0-0 \
        libharfbuzz0b \
        libgdk-pixbuf-2.0-0 \
        libcairo2 \
        libffi-dev \
        shared-mime-info \
        fonts-dejavu \
    && rm -rf /var/lib/apt/lists/*
```

**Package-name note (base-image correctness):** `python:3.10-slim` is Debian **bookworm**. On bookworm the gdk-pixbuf runtime package is **`libgdk-pixbuf-2.0-0`** (the older `libgdk-pixbuf2.0-0` is the buster/bullseye name). Use `libgdk-pixbuf-2.0-0`. If a future base bump regresses to bullseye, fall back to `libgdk-pixbuf2.0-0`. `libgobject-2.0-0` (the exact lib named in the traceback) is pulled in transitively by libpango/libgdk-pixbuf via `libglib2.0-0` — no separate line needed; the post-deploy verify in §4 confirms the actual `import weasyprint` works rather than trusting the dependency graph.

**Image-size impact vs SYS-BL-01 (root fs 80% / ~7 GB backlog):** this package set + their transitive deps (libglib2.0-0, libcairo, libpng, libfreetype, fontconfig, the DejaVu fonts) adds roughly **~60–110 MB** to the image (one-time, shared across all five services since they share one image). `--no-install-recommends` suppresses doc/dev recommend bloat; `rm -rf /var/lib/apt/lists/*` in the **same `RUN`** layer keeps the apt index (~tens of MB) out of the committed layer. Net: a single bounded ~<0.12 GB increment, well under the 7 GB backlog and **does not worsen SYS-BL-01**; recommendation: keep the `--no-install-recommends` + same-layer list cleanup exactly as written, and (separate, out-of-scope) prune dangling images post-deploy (`docker image prune -f`) to offset the new layer on the constrained Pi disk.

**Do NOT** add system deps via `docker-compose.yml`; **do NOT** change any `command:` or the `reporting-service` block (read-only here).

---

## 4. Verification & rollback

**Baseline:** suite 1661 passed / 0 failed (per `SPRINT15_TEAM_MEETING.md`). Drift test green (no `engine_core`/`§6`/math touched → drift-safe by construction). Wave 2 target: **1661 + new tests, 0 failed**.

### P1 — unit/integration testable (force the import/render to raise → text still sent)

Add to `tests/test_report_scheduler.py` / a new `tests/test_report_renderer_degraded.py` (follow the existing stub-heavy convention in `tests/test_heat_in_weekly_report.py`: pre-stub `telebot/supabase/dotenv`, set env). Cases:

1. **Renderer import guard:** monkeypatch so `from weasyprint import HTML` raises `OSError("cannot load library 'libgobject-2.0-0'")`; assert `import report_renderer` still succeeds and `_load_weasyprint()` returns `None` (no raise).
2. **`_render` degrades to HTML on import-None:** with WeasyPrint unavailable, `_render(...)` returns the `.html` path (not raising) — existing dev-fallback contract preserved.
3. **`_render` degrades on render exception:** `_load_weasyprint()` returns a stub whose `.write_pdf` raises; assert `_render` catches it and returns the `.html` path.
4. **`build_summary_text` unaffected:** byte-identical output with/without WeasyPrint present (guards "no content/number change").
5. **`_run_weekly` text-still-sent (core requirement):** patch `render_weekly` to raise; patch `deliver_report` to a spy; assert `send_summary`/`deliver_report` is still called with the full `summary_text`, `pdf_path` is `None`, and the run does NOT call `_notify_error` as a failure — i.e. degraded-success per the `⟨MARK⟩` ruling in §2b.
6. **Degraded note present:** when degraded, assert the appended honest line (the resolved `⟨MARK⟩` Hebrew text) is in the sent `summary_text`.
7. **`_run_monthly` parity:** same as (5) for the monthly path.
8. **Non-degraded regression:** WeasyPrint present + working → `pdf_path` ends `.pdf`, `pdf_ok` True, no degraded note (no behaviour change on the happy path).

(Cases 5–7 are the explicit "weekly text summary still sends even with PDF totally broken" requirement from `SPRINT16_PLAN.md` / Mark's checklist.)

### P2 — image-only (NOT unit-testable) → manual rebuild + verify

Operator on the Pi, from `~/sentinel_trading`:

1. `./deploy.sh` — pulls branch + `docker compose up -d --build --force-recreate` (rebuilds the shared image incl. the new apt layer; existing connectivity self-check unchanged).
2. **Confirm a PDF actually renders post-deploy:**
   `docker compose exec -T reporting-service python3 -c "from weasyprint import HTML as H; H(string='<h1>ok</h1>').write_pdf('/tmp/_p.pdf'); import os; print('PDF_OK', os.path.getsize('/tmp/_p.pdf'))"` → expect `PDF_OK <bytes>` with no `OSError`.
3. **Confirm graceful text-only if libs still missing** (proves P1 independent of P2): temporarily on a libs-missing image, run the §4 case-5 test or trigger a manual weekly invocation and confirm Telegram receives the text summary + the `⟨MARK⟩` degraded note and **no crash**.
4. Optionally trigger one off-schedule weekly run (or wait for Sat 08:30 IL) and confirm the founder receives **both** text summary and the PDF document.

**Rollback (P1 and/or P2):** `git revert` the Sprint-16 commit(s) on `claude/review-system-audit-FBZ2h`, then `./deploy.sh` to rebuild/redeploy the prior image. P2 is purely additive Dockerfile layers + P1 is additive guards → revert is clean, no data/state migration to undo, no schema change. If only the image is suspect, reverting just the Dockerfile hunk and re-running `./deploy.sh` restores the prior (libs-absent) image while P1 keeps the report degrading safely to text-only.

---

## 5. Risk classification + explicit "will NOT change"

**Risk:** P1 = **MEDIUM** (touches `report_renderer.py` import + `report_scheduler.py` weekly/monthly flow — delivery-resilience only, fully unit-tested, no math). P2 = **MEDIUM/HIGH** (Dockerfile is a CLAUDE.md most-fragile / production-wiring area — additive apt layer only, Mark-gated, manual verify + clean rollback). Combined exposure bounded: no app logic, no numbers, no schedule, no service wiring.

**This change will NOT:**

- change `docker-compose.yml` — no service `command:`, no `reporting-service` block, no volumes/healthcheck (read-only).
- bypass or modify `telegram_bot_secure_runner.py` or any Telegram admin/anti-spam protection (reporting service is already fully decoupled — `report_delivery.py` uses raw `requests`).
- touch app/risk/NAV/exposure/campaign math, `analytics_engine`, `adaptive_risk_engine`, `engine_core`, or Sprint-15 dual-R/recon logic.
- change report **content or numbers** — `build_summary_text` (`report_renderer.py:99`) and every Jinja context value are byte-identical; only the returned file path / delivery resilience changes.
- touch `_RULESET` / methodology §6, ALGO rules, the Oversight Gate, or the live smoke-test (remain founder-pending, separate).
- introduce any DB schema change, migration, `user_id`, or multi-user surface (single-user, byte-identical — consistent with the Hyperscaler addendum).
- alter the weekly/monthly **schedule** (Sat 08:30 / 1st 08:40) or the scheduler loop/state.

**Open `⟨MARK⟩` slots (Wave 2 blocked on these — none invented here):**
1. Exact Hebrew degraded-mode line appended to the text summary.
2. Whether a degraded (text-only) delivery also emits a separate `_notify_error` ops alert, or inline note only.
3. Ruling that `summary_ok=True, pdf_ok=False` = degraded-**success** (not a failure / not `_notify_error`) — defines §4 test pass condition.

— End of SPRINT16_DESIGN.md —
