# INCIDENT — Weekly report failed (2026-05-16 08:30 IL)

**Severity:** HIGH (core founder-facing feature down; weekly report did not send).
**Status:** Diagnosed; fix queued as **Sprint 16** (after Sprint-15 consolidation — no overlapping build agents on the shared tree).
**Detected:** founder pasted `docker compose logs --tail=30 reporting-service`.

## What happened

`2026-05-16 08:30:10 report_scheduler: ERROR in weekly report:` — the Saturday-08:30-IL scheduled run crashed.

```
report_scheduler.py:198  _run_weekly → from report_renderer import render_weekly
report_renderer.py:17    from weasyprint import HTML as WeasyHTML
weasyprint/text/ffi.py:476  gobject = _dlopen(...)
OSError: cannot load library 'libgobject-2.0-0': cannot open shared object file
```

## Root cause

WeasyPrint (PDF engine) requires native system libs — `libgobject-2.0-0`, Pango, Cairo, etc. The runtime image (`python:3.10-slim`, built by `Dockerfile`) does **not** install them. The import is at **module top of `report_renderer.py:17`**, so the failure aborts the **entire** weekly run (`_run_weekly`, report_scheduler.py:198) — not just the PDF. Net effect: **no weekly report sent at all** (text summary included). Very likely fails every Saturday until fixed; may have failed on prior Saturdays.

## Fix shape (two parts — Sprint 16, Mark-gated; Dockerfile is a CLAUDE.md most-fragile area)

1. **Graceful degradation (priority 1, methodology):** the weekly run must NEVER fail silently/entirely because PDF rendering is unavailable. Wrap the WeasyPrint import/use so a render failure still sends the **text summary** + an honest "PDF temporarily unavailable" note (AGENTS.md: never silently drop a founder-facing report; honest about degraded output).
2. **Dockerfile native deps (priority 2):** add the WeasyPrint OS dependencies (`apt-get install -y libpango-1.0-0 libpangoft2-1.0-0 libgdk-pixbuf2.0-0 libcairo2 libffi-dev shared-mime-info` etc.) so the PDF actually renders. Touches `Dockerfile` (production wiring) → Mark ruling + careful verification + the manual deploy/verify procedure.

## Immediate reality for the founder

The **next weekly report (next Saturday 08:30 IL) will also fail** until Sprint 16 ships. No safe in-place mitigation without a code/image change (the failure is at import time). No data is wrong — it crashes loudly, sends nothing.

## Not in scope here

This is independent of Sprint 15 (report R-integrity, different files). Recorded so it is not lost; actioned as Sprint 16 immediately after Sprint-15 consolidates.
