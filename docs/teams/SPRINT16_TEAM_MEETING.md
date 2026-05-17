# Sprint 16 — Team-Leads Meeting (Consolidation): Weekly-Report Resilience

**Date:** 2026-05-16
**Branch:** `claude/review-system-audit-FBZ2h`
**Severity:** HIGH incident (`INCIDENT_20260516`) — weekly + monthly report crashed entirely every run.
**Suite:** 1661 → **1676 passed, 0 failed** (+15; 1 pre-existing unrelated warning). Drift-safe by construction (engine_core/§6 untouched).

## Wave 1 commits
`298fde2` Mark · `419d208` Arch+Infra · `e1eb592` Hyperscaler. Mark + Arch independently proved the precise root cause.

## Root cause (verified at checkpoint)
`report_renderer.py:17` `from weasyprint import HTML` is module-top with a try/except that catches **only `ImportError`** (`:19`). The live failure is `OSError: cannot load library 'libgobject-2.0-0'` (native lib absent from `python:3.10-slim`) — NOT an `ImportError` — so it propagated, killing `_run_weekly` (`report_scheduler.py:215` `render_weekly` runs *before* `build_summary_text:231`) and the identical `_run_monthly` chokepoint. No PDF, no text — only `_notify_error`.

## Wave 2 — parent independent verification (this consolidation)

| Item | Verified |
|---|---|
| Broad-Exception guard | ✅ `report_renderer._load_weasyprint()` lazy, `except Exception` (incl. OSError) → `None` → `.html` fallback; module-top import removed |
| Text always sends | ✅ `report_scheduler` wraps `render_weekly`/`render_monthly` in `try/except Exception`; on failure `pdf_path=""`, summary+deliver still run |
| Degraded = SUCCESS | ✅ logs **WARNING** (not ERROR); `_notify_error` NOT called on the degraded path; Mark's exact honest trailer appended: *"⚠️ ה-PDF לא נוצר בריצה זו. סיכום הטקסט למעלה הוא הנתון הקובע והמלא."* (#1 — text authoritative, no optimistic wording) |
| Zero content change | ✅ `build_summary_text` not in the diff (body untouched); agent SHA-256 weekly+monthly identical; trailer appended by scheduler only when degraded |
| `os.path.exists(None)` safety | ✅ degraded passes `""` **and** `report_delivery.send_pdf` guards `if not pdf_path or not os.path.exists(...)` |
| Dockerfile additive-only | ✅ one `RUN apt-get … --no-install-recommends … && rm -rf /var/lib/apt/lists/*` layer **before** the pip step; `FROM python:3.10-slim` unchanged; bookworm pkg names (libgobject via libglib2.0-0 transitively); ~<0.12 GB, no SYS-BL-01 regression |
| Protected untouched | ✅ `docker-compose.yml`, `telegram_bot_secure_runner.py`, `engine_core.py`, `account_state.py`, `analytics_engine.py` empty diff; no migration/`_RULESET`/§6 |
| Weekly + monthly | ✅ both runners fixed (same chokepoint) |

## Deployment ("הטמעה")

**One `./deploy.sh` delivers both P1 and P2:**
```bash
cd ~/sentinel_trading && ./deploy.sh
```
- **P1 (code, pure Python)** takes effect immediately on the new code — next Saturday 08:30 IL the report sends the **text summary + ⚠️ trailer** even if PDF libs are still absent (no crash, no silent miss).
- **P2 (Dockerfile apt layer)** takes effect because `./deploy.sh` runs `up -d --build --force-recreate` → the image rebuilds with the WeasyPrint native libs → the **PDF renders** again. (The apt layer needs network during build; `./deploy.sh`'s connectivity self-check covers post-deploy.)

**Verify after deploy:** `docker compose logs --tail=20 reporting-service` (no libgobject OSError on import); next Saturday the report arrives — ideally with PDF; if libs still missing for any reason, it still arrives as text+⚠️ (graceful). **Rollback:** `git revert <consolidation commit> && ./deploy.sh`.

## Carried / open (pending founder)
🔴 Live Sprint 11–16 founder smoke-test still outstanding · **ALGO rules** (unblocks ALGO data-quality / dead-money) · **ALGO Oversight Gate** decision (Mark: REFINE) · deploy Sprint 15+16 · SYS-BL-01 disk hygiene · Hyperscaler PR-A3+.
