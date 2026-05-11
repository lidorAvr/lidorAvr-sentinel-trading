"""
ibkr_sync_runner.py — shared IBKR Flex Query sync logic.
Imported by main.py (scheduled loop) and telegram_bot.py (developer menu manual trigger).
Keeps all IBKR API interaction in one place so both callers stay in sync.
"""
import os, json, time, glob as _glob, requests
import xml.etree.ElementTree as ET
from datetime import datetime

MANUAL_RESULT_FILE = "/app/ibkr_last_sync_result.json"
_REPORTS_DIR       = "/app/ibkr_reports"
_REPORTS_TO_KEEP   = 3
_CONFIG_PATH       = "/app/sentinel_config.json"

IBKR_ERROR_CLASSES = {
    1001: ("temporary",  "הדוח לא נוצר כרגע — ניסיון מאוחר יותר"),
    1004: ("temporary",  "הדוח לא שלם עדיין"),
    1005: ("temporary",  "נתוני Settlement עדיין לא מוכנים"),
    1006: ("temporary",  "נתוני FIFO P/L עדיין לא מוכנים"),
    1007: ("temporary",  "נתוני MTM P/L עדיין לא מוכנים"),
    1008: ("temporary",  "נתוני MTM ו-FIFO עדיין לא מוכנים"),
    1009: ("temporary",  "עומס בשרתי IBKR"),
    1018: ("rate_limit", "יותר מדי בקשות — Rate Limit"),
    1019: ("temporary",  "הדוח עדיין בתהליך יצירה"),
    1021: ("temporary",  "לא ניתן למשוך את הדוח כרגע"),
    1012: ("fatal",      "Token פג תוקף"),
    1013: ("fatal",      "הגבלת IP — Token לא מורשה מכתובת זו"),
    1014: ("fatal",      "Query ID לא תקין"),
    1015: ("fatal",      "Token לא תקין"),
    1016: ("fatal",      "Account לא תקין"),
    1017: ("fatal",      "Reference Code לא תקין"),
    1020: ("fatal",      "בקשה לא תקינה או לא ניתנת לאימות"),
}


def parse_flex_error(xml_text: str):
    """Return error dict or None if the XML looks like a successful response."""
    try:
        root = ET.fromstring(xml_text)
        error_elem = root.find(".//ErrorCode")
        if error_elem is not None:
            try:
                code = int(error_elem.text.strip())
            except (ValueError, AttributeError):
                code = -1
            error_class, description = IBKR_ERROR_CLASSES.get(
                code, ("temporary", f"קוד שגיאה לא מוכר: {code}")
            )
            return {"code": code, "class": error_class, "description": description}
        return None
    except ET.ParseError as e:
        return {"code": -1, "class": "temporary", "description": f"XML parse error: {e}"}
    except Exception as e:
        return {"code": -1, "class": "temporary", "description": str(e)}


def get_statement_with_retry(ref_code: str, token: str, max_retries: int = 3,
                              wait_sec: int = 60, log_fn=print):
    """
    Fetch statement using ref_code, retrying on temporary errors.
    Returns (xml_text, None) on success, or (None, error_dict) on failure.
    Only one SendRequest is issued per sync — this reuses the same ref_code.
    """
    fetch_url = (
        "https://www.interactivebrokers.com/Universal/servlet/"
        "FlexStatementService.GetStatement"
    )
    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            res = requests.get(f"{fetch_url}?q={ref_code}&t={token}&v=3", timeout=60)
            error = parse_flex_error(res.text)
            if error is None:
                return res.text, None
            last_error = error
            log_fn(
                f"GetStatement {attempt}/{max_retries}: "
                f"code={error['code']} ({error['class']}) — {error['description']}"
            )
            if error["class"] == "fatal":
                return None, error
            if attempt < max_retries:
                log_fn(f"Waiting {wait_sec}s before retry…")
                time.sleep(wait_sec)
        except Exception as e:
            last_error = {"code": -1, "class": "temporary", "description": str(e)}
            log_fn(f"GetStatement network error (attempt {attempt}): {e}")
            if attempt < max_retries:
                time.sleep(wait_sec)
    return None, last_error


def run_ibkr_sync(log_fn=print) -> dict:
    """
    Run one full IBKR Flex Query sync cycle:
      SendRequest → wait 15s → GetStatement (with retry) → save XML → update NAV.

    Returns:
        {"status": "success"|"temporary"|"fatal"|"rate_limit",
         "code": int|None, "message": str, "nav": float|None}
    """
    log_fn("IBKR Sync — started")
    token    = os.getenv("IBKR_TOKEN")
    query_id = os.getenv("IBKR_QUERY_ID", "1501352")
    send_url = (
        "https://www.interactivebrokers.com/Universal/servlet/"
        "FlexStatementService.SendRequest"
    )

    try:
        res = requests.get(f"{send_url}?t={token}&q={query_id}&v=3", timeout=30)
        send_error = parse_flex_error(res.text)
        if send_error:
            log_fn(
                f"SendRequest error: {send_error['code']} "
                f"({send_error['class']}) — {send_error['description']}"
            )
            log_fn(f"SendRequest raw response: {res.text[:500]}")
            return {
                "status": send_error["class"],
                "code": send_error["code"],
                "message": send_error["description"],
                "nav": None,
            }

        root = ET.fromstring(res.text)
        code_elem = root.find(".//ReferenceCode")
        if code_elem is None:
            code_elem = root.find(".//code")
        if code_elem is None:
            log_fn(f"SendRequest: no reference code in response: {res.text[:300]}")
            return {
                "status": "temporary", "code": 0,
                "message": "חסר Reference Code בתגובה מ-IBKR", "nav": None,
            }

        ref_code = code_elem.text
        log_fn(f"SendRequest OK — ref: {ref_code}. Waiting 15s…")
        time.sleep(15)

        xml_text, error = get_statement_with_retry(ref_code, token, log_fn=log_fn)
        if error:
            log_fn(
                f"GetStatement failed after retries: "
                f"code={error['code']} ({error['class']}) — {error['description']}"
            )
            return {
                "status": error["class"], "code": error["code"],
                "message": error["description"], "nav": None,
            }

        # Persist report XML (keep only _REPORTS_TO_KEEP most recent)
        os.makedirs(_REPORTS_DIR, exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M")
        report_path = os.path.join(_REPORTS_DIR, f"ibkr_{ts}.xml")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(xml_text)
        log_fn(f"Report saved: {report_path}")
        all_reports = sorted(_glob.glob(os.path.join(_REPORTS_DIR, "ibkr_*.xml")))
        while len(all_reports) > _REPORTS_TO_KEEP:
            old = all_reports.pop(0)
            os.remove(old)
            log_fn(f"Old report removed: {os.path.basename(old)}")

        # Parse NAV and update sentinel_config.json
        report_root = ET.fromstring(xml_text)
        nav_updated = None
        nav_node = report_root.find(".//ChangeInNAV")
        if nav_node is not None:
            v = nav_node.get("endingValue")
            if v:
                nav_updated = float(v)
                try:
                    cfg = {"total_deposited": 7500.0, "risk_pct_input": 0.5}
                    if os.path.exists(_CONFIG_PATH):
                        with open(_CONFIG_PATH) as f:
                            cfg = json.load(f)
                    cfg["nav"] = nav_updated
                    cfg["nav_updated_at"] = datetime.now().isoformat()
                    with open(_CONFIG_PATH, "w") as f:
                        json.dump(cfg, f)
                    log_fn(f"NAV updated: ${nav_updated:,.2f}")
                except Exception as e:
                    log_fn(f"NAV update error: {e}")

        trades = report_root.findall(".//Trade")
        nav_str = f" | NAV: ${nav_updated:,.0f}" if nav_updated else ""
        log_fn(f"Sync OK — {len(trades)} trades.{nav_str}")
        return {
            "status": "success", "code": None,
            "message": f"{len(trades)} עסקאות סונכרנו{nav_str}",
            "nav": nav_updated,
        }

    except Exception as e:
        log_fn(f"Sync error: {e}")
        return {"status": "temporary", "code": -1, "message": str(e), "nav": None}
