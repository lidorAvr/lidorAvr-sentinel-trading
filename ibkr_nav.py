import json, os
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime, timezone

BASE_DIR = Path("/home/orangepi/sentinel_trading")
CONFIG_PATH = BASE_DIR / "sentinel_config.json"
RAW_REPORT_PATH = BASE_DIR / "ibkr_raw_report.xml"

def _now_iso():
    return datetime.now(timezone.utc).isoformat()

def _safe_float(v):
    try:
        if v is None:
            return None
        return float(str(v).replace(",", "").replace("$", "").strip())
    except Exception:
        return None

def _load_config():
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"total_deposited": 7500.0, "risk_pct_input": 0.5}

def _save_config(cfg):
    tmp = str(CONFIG_PATH) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    os.replace(tmp, CONFIG_PATH)

def _tag_name(elem):
    return str(elem.tag).split("}", 1)[-1]

def _report_generated_at(root):
    stmt = root.find(".//FlexStatement")
    raw = stmt.attrib.get("whenGenerated") if stmt is not None else None
    if not raw:
        return None
    try:
        d, t = raw.split(";", 1)
        dt = datetime.strptime(d + t[:6], "%Y%m%d%H%M%S")
        return dt.replace(tzinfo=timezone.utc).isoformat()
    except Exception:
        return raw

def extract_nav_from_xml_text(xml_text):
    try:
        root = ET.fromstring(xml_text)
    except Exception as e:
        return {"ok": False, "error": f"xml_parse_error: {e}", "nav": None}

    generated_at = _report_generated_at(root)

    for elem in root.iter():
        tag = _tag_name(elem).lower()
        attrs = elem.attrib or {}

        if tag.endswith("changeinnav"):
            nav = _safe_float(attrs.get("endingValue") or attrs.get("endingvalue"))
            if nav and nav > 0:
                return {
                    "ok": True,
                    "error": None,
                    "nav": nav,
                    "source_tag": _tag_name(elem),
                    "source_field": "endingValue",
                    "report_generated_at": generated_at,
                }

    return {
        "ok": True,
        "error": None,
        "nav": None,
        "source_tag": None,
        "source_field": None,
        "report_generated_at": generated_at,
    }

def update_nav_from_xml(xml_text, source="ibkr_flex"):
    try:
        RAW_REPORT_PATH.write_text(xml_text, encoding="utf-8")
    except Exception:
        pass

    result = extract_nav_from_xml_text(xml_text)
    cfg = _load_config()
    cfg["current_nav_checked_at"] = _now_iso()
    cfg["current_nav_source"] = source

    if result.get("nav"):
        cfg["current_nav"] = float(result["nav"])
        cfg["current_nav_status"] = "ok"
        cfg["current_nav_error"] = None
        cfg["current_nav_updated_at"] = _now_iso()
        cfg["current_nav_report_generated_at"] = result.get("report_generated_at")
        cfg["current_nav_source_tag"] = result.get("source_tag")
        cfg["current_nav_source_field"] = result.get("source_field")
    else:
        cfg["current_nav_status"] = "missing_in_report"
        cfg["current_nav_error"] = "NAV not found in Flex report. Verify IBKR_QUERY_ID includes ChangeInNAV."

    _save_config(cfg)
    return result

def load_current_nav():
    cfg = _load_config()
    nav = _safe_float(cfg.get("current_nav"))
    return nav if nav and nav > 0 else None

def nav_status():
    cfg = _load_config()
    return {
        "current_nav": _safe_float(cfg.get("current_nav")),
        "status": cfg.get("current_nav_status"),
        "updated_at": cfg.get("current_nav_updated_at"),
        "checked_at": cfg.get("current_nav_checked_at"),
        "source": cfg.get("current_nav_source"),
        "source_tag": cfg.get("current_nav_source_tag"),
        "source_field": cfg.get("current_nav_source_field"),
        "report_generated_at": cfg.get("current_nav_report_generated_at"),
        "error": cfg.get("current_nav_error"),
    }
