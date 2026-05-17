"""
report_delivery.py — HTTP delivery of reports to Telegram.
Uses requests directly (same pattern as main.py) — no dependency on telebot or
the secure runner, so the reporting service stays fully decoupled from the bot.
"""
import os, time, requests
from typing import Optional

_TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"
_MAX_RETRIES  = 3
_RETRY_WAIT   = [5, 15, 30]     # seconds between retries


def send_summary(text: str, chat_id: str, token: str) -> bool:
    """Send a plain-text summary message before the PDF."""
    return _post_json("sendMessage", token, {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
    })


def send_pdf(pdf_path: str, caption: str, chat_id: str, token: str) -> bool:
    """
    Send a PDF document via sendDocument.
    Returns True on success, False after all retries fail.
    """
    # Sprint 16: the degraded (text-only) path passes a falsy value ("") for
    # pdf_path. Guard against a falsy/None path BEFORE os.path.exists, which
    # would raise TypeError on os.path.exists(None). Falsy path → no PDF to send.
    if not pdf_path or not os.path.exists(pdf_path):
        return False
    url = _TELEGRAM_API.format(token=token, method="sendDocument")
    for attempt, wait in enumerate([0] + _RETRY_WAIT, start=1):
        if wait:
            time.sleep(wait)
        try:
            with open(pdf_path, "rb") as f:
                resp = requests.post(
                    url,
                    data={"chat_id": chat_id, "caption": caption[:1024]},
                    files={"document": (os.path.basename(pdf_path), f, "application/pdf")},
                    timeout=60,
                )
            if resp.ok and resp.json().get("ok"):
                return True
            _log(f"sendDocument attempt {attempt} failed: {resp.text[:200]}")
        except Exception as e:
            _log(f"sendDocument attempt {attempt} error: {e}")
    return False


def deliver_report(pdf_path: str, summary_text: str, caption: str,
                   chat_id: str, token: str) -> dict:
    """
    Full delivery: send summary message then PDF document.
    Returns {"summary_ok": bool, "pdf_ok": bool}.
    """
    summary_ok = send_summary(summary_text, chat_id, token)
    pdf_ok     = send_pdf(pdf_path, caption, chat_id, token)
    return {"summary_ok": summary_ok, "pdf_ok": pdf_ok}


# ── internals ──────────────────────────────────────────────────────────────────

def _post_json(method: str, token: str, payload: dict) -> bool:
    url = _TELEGRAM_API.format(token=token, method=method)
    for attempt, wait in enumerate([0] + _RETRY_WAIT, start=1):
        if wait:
            time.sleep(wait)
        try:
            resp = requests.post(url, json=payload, timeout=15)
            if resp.ok and resp.json().get("ok"):
                return True
            _log(f"{method} attempt {attempt} failed: {resp.text[:200]}")
        except Exception as e:
            _log(f"{method} attempt {attempt} error: {e}")
    return False


def _log(msg: str):
    from datetime import datetime
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] report_delivery: {msg}", flush=True)
    try:
        log_file = "/app/logs/sentinel_report.log"
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        with open(log_file, "a", encoding="utf-8") as f:
            from datetime import datetime as _dt
            f.write(f"[{_dt.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except Exception:
        pass
