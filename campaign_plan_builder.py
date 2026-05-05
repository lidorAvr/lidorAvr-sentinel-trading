import os
import json
import argparse
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timezone

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

from supabase import create_client

BASE_DIR = Path(__file__).resolve().parent

if load_dotenv:
    load_dotenv(BASE_DIR / ".env")
    load_dotenv("/app/.env")

def _env(*names):
    for name in names:
        val = os.getenv(name)
        if val:
            return val
    return None

SUPABASE_URL = _env("SUPABASE_URL")
SUPABASE_KEY = _env("SUPABASE_SERVICE_KEY", "SUPABASE_KEY", "SUPABASE_ANON_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise SystemExit("Missing SUPABASE_URL / SUPABASE_KEY in .env")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def _s(v):
    if v is None:
        return None
    x = str(v).strip()
    return x if x else None

def _f(v, default=None):
    try:
        if v is None or v == "":
            return default
        return float(v)
    except Exception:
        return default

def _now():
    return datetime.now(timezone.utc).isoformat()

def _fetch_all(table, select="*"):
    rows = []
    start = 0
    page = 1000
    while True:
        res = supabase.table(table).select(select).range(start, start + page - 1).execute()
        chunk = res.data or []
        rows.extend(chunk)
        if len(chunk) < page:
            break
        start += page
    return rows

def _audit(event_type, severity, message, payload=None, symbol=None, campaign_id=None, account_id=None):
    try:
        supabase.table("campaign_audit_events").insert({
            "event_type": event_type,
            "severity": severity,
            "message": message,
            "symbol": symbol,
            "campaign_id": campaign_id,
            "account_id": account_id,
            "payload": payload or {},
        }).execute()
    except Exception as e:
        print(f"audit write skipped: {e}")

def _latest_risk_by_campaign():
    rows = _fetch_all("campaign_risk_snapshots")
    rows.sort(key=lambda r: _s(r.get("snapshot_at")) or "")
    out = {}
    for r in rows:
        cid = _s(r.get("campaign_id"))
        if cid:
            out[cid] = r
    return out

def _plans_by_campaign():
    try:
        rows = _fetch_all("campaign_plans")
    except Exception:
        return {}
    return {_s(r.get("campaign_id")): r for r in rows if _s(r.get("campaign_id"))}

def _strategy_stats():
    campaigns = _fetch_all("campaigns")
    risks = _latest_risk_by_campaign()

    vals = []
    wins = []
    losses = []

    for c in campaigns:
        if not c.get("strategy_eligible"):
            continue
        if c.get("has_open_position"):
            continue

        cid = _s(c.get("campaign_id"))
        r = risks.get(cid)
        if not r:
            continue

        val = _f(r.get("closed_target_r"))
        if val is None:
            continue

        vals.append(val)
        if val > 0:
            wins.append(val)
        elif val < 0:
            losses.append(val)

    avg_win = sum(wins) / len(wins) if wins else None
    avg_loss = sum(losses) / len(losses) if losses else None
    expectancy = sum(vals) / len(vals) if vals else None
    win_rate = len(wins) / len(vals) if vals else None

    if len(vals) < 10:
        confidence = "low"
    elif len(vals) < 30:
        confidence = "medium_low"
    elif len(vals) < 50:
        confidence = "medium"
    else:
        confidence = "higher"

    return {
        "sample_size": len(vals),
        "avg_win_r": avg_win,
        "avg_loss_r": avg_loss,
        "expectancy_r": expectancy,
        "win_rate": win_rate,
        "metric_scope": "YTD_VERIFIED_CAMPAIGNS_ONLY",
        "confidence": confidence,
    }

def _risk_alignment(target, actual):
    if target is None or target <= 0 or actual is None or actual <= 0:
        return "unknown", None

    ratio = actual / target

    if ratio < 0.5:
        return "undersized", ratio
    if ratio > 1.25:
        return "oversized", ratio
    return "aligned", ratio

def _confidence_score(stats, required_missing, red_flags, risk_quality):
    score = 50

    sample = stats.get("sample_size") or 0
    if sample >= 50:
        score += 20
    elif sample >= 30:
        score += 15
    elif sample >= 20:
        score += 8
    elif sample >= 10:
        score += 3
    else:
        score -= 10

    if risk_quality == "verified":
        score += 15
    elif risk_quality == "estimated":
        score += 3
    else:
        score -= 15

    score -= len(required_missing) * 18
    score -= len(red_flags) * 8

    return max(0, min(100, int(score)))

def _strength_plan(stats):
    sample = stats.get("sample_size") or 0
    avg_win = stats.get("avg_win_r")

    triggers = [
        {
            "trigger": "around_2r",
            "rule_he": "סביב 2R: להתחיל להגן. לא לתת לעסקה טובה להפוך להפסד גדול.",
            "preferred_action": "קדם סטופ לכניסה / סיכון אפס; אין מימוש חלקי בלי סימן חולשה.",
        },
        {
            "trigger": "around_3r",
            "rule_he": "סביב 3R ומעלה: נועלים חלק מהרווח ומפסיקים להשאיר החלטה פתוחה.",
            "preferred_action": "מימוש 25% כברירת מחדל; אם המהלך מתוח או הטרייד ותיק, מימוש 50%. סטופ יתרה ל-SMA10/סיכון אפס.",
        },
        {
            "trigger": "climactic_move",
            "rule_he": "מהלך מואץ, גאפים מאוחרים או ווליום חריג אחרי עלייה גדולה.",
            "preferred_action": "מכירה לתוך עוצמה או הידוק אגרסיבי של סטופ.",
        },
    ]

    if sample >= 10 and avg_win is not None:
        triggers.append({
            "trigger": "above_avg_win",
            "rule_he": f"מעל Avg Win מאומת ({avg_win:.2f}R): לבדוק הגנת רווח.",
            "preferred_action": "להגן על חלק משמעותי מהרווח; לא להחזיר טרייד איכותי לבינוניות.",
        })

    if sample >= 30 and avg_win is not None:
        triggers.append({
            "trigger": "twice_avg_win",
            "rule_he": f"פי 2 מהרווח הממוצע המאומת ({avg_win * 2:.2f}R): מכירת חצי הופכת רלוונטית.",
            "preferred_action": "מכור חצי אם אין סימני Leader חריגים; יתרה Runner.",
        })

    return {
        "action_type": "sell_strength_or_protect",
        "stat_basis": stats,
        "confidence_note_he": "היסטוריית YTD מאומתת מוגבלת; התוכנית משלבת סטטיסטיקה עם כללי ניהול בסיסיים.",
        "triggers": triggers,
    }

def _weakness_plan():
    return {
        "action_type": "sell_weakness",
        "rules": [
            {
                "trigger": "stop_hit",
                "rule_he": "סטופ נחצה.",
                "preferred_action": "יציאה מלאה. לא מוכרים חצי בצד ההפסד.",
                "deadline": "מיידי",
            },
            {
                "trigger": "no_follow_through",
                "rule_he": "אין Follow Through אחרי הכניסה או הפריצה.",
                "preferred_action": "להפחית או לצאת אם ההתנהגות לא משתפרת בזמן קצר.",
                "deadline": "1-3 ימי מסחר ב-EP, 5-10 ימים ב-VCP.",
            },
            {
                "trigger": "weak_closes_or_lower_lows",
                "rule_he": "יותר סגירות חלשות מחזקות או רצף שפלים יורדים.",
                "preferred_action": "להקטין חשיפה או לצאת אם נשברת תמיכה.",
                "deadline": "עד סוף היום / עם שבירת רמה.",
            },
            {
                "trigger": "profit_giveback",
                "rule_he": "רווח יפה נמחק בצורה חריגה.",
                "preferred_action": "לא לתת לרווח משמעותי להפוך להפסד.",
                "deadline": "באותו יום מסחר.",
            },
        ],
    }

def _emergency_plan(has_stop):
    if has_stop:
        return {
            "action_type": "emergency_exit",
            "rule_he": "אם הסטופ נחצה, סוגרים בברוקר ללא ויכוח.",
            "deadline": "מיידי",
            "partial_loss_sell_allowed": False,
        }

    return {
        "action_type": "missing_stop_emergency",
        "rule_he": "אין סטופ מאומת. זה סיכון לא מנוהל.",
        "deadline": "להזין סטופ תוך 5 דקות או לסמן חריגה.",
        "partial_loss_sell_allowed": False,
    }

def _plan_summary(symbol, setup, current_stop, target, actual, alignment, strength_plan, weakness_plan):
    stop_text = f"${current_stop:.2f}" if current_stop is not None else "חסר"
    target_text = f"${target:.0f}" if target is not None else "לא ידוע"
    actual_text = f"${actual:.0f}" if actual is not None else "לא ידוע"

    return (
        f"תוכנית ניהול ראשונית - {symbol}\n"
        f"Setup: {setup or 'לא סווג'}\n"
        f"סטופ: {stop_text}\n"
        f"סיכון בפועל: {actual_text} מול יעד {target_text}\n"
        f"יישור סיכון: {alignment}\n"
        f"מכירה לעוצמה: סביב 2R/3R, מעל Avg Win אם יש מספיק מדגם, או סימני Climax.\n"
        f"מכירה לחולשה: סטופ, חוסר Follow Through, סגירות חלשות, 3 שפלים יורדים או מחיקת רווח.\n"
        f"חירום: סטופ נחצה = יציאה מלאה."
    )

def _build_one(campaign, risk, stats):
    cid = _s(campaign.get("campaign_id"))
    symbol = _s(campaign.get("symbol"))
    setup = _s(campaign.get("setup_type"))
    account_id = _s(campaign.get("account_id"))
    decision_source = _s(campaign.get("decision_source")) or "manual"

    target = _f(risk.get("target_risk_usd")) if risk else _f(campaign.get("target_risk_usd"))
    actual = _f(risk.get("actual_initial_risk_usd")) if risk else _f(campaign.get("actual_initial_risk_usd"))
    current_stop = _f(risk.get("current_stop")) if risk else None
    entry_price = _f(risk.get("avg_entry_price")) if risk else _f(campaign.get("avg_entry_price"))
    risk_quality = _s(risk.get("data_quality_status")) if risk else _s(campaign.get("risk_data_quality_status"))

    required_missing = []
    optional_missing = []
    red_flags = []

    if current_stop is None:
        required_missing.append("initial_or_current_stop")
        red_flags.append("missing_stop")

    if not setup:
        required_missing.append("setup_type")
        red_flags.append("missing_setup")

    # Catalyst is intentionally optional.
    optional_missing.append("catalyst")

    alignment, ratio = _risk_alignment(target, actual)

    if alignment == "oversized":
        red_flags.append("actual_risk_above_target")
    elif alignment == "undersized":
        red_flags.append("actual_risk_below_target")

    strength = _strength_plan(stats)
    weakness = _weakness_plan()
    emergency = _emergency_plan(current_stop is not None)

    confidence = _confidence_score(stats, required_missing, red_flags, risk_quality)
    quality = "verified" if not required_missing and risk_quality == "verified" else (
        "estimated" if current_stop is not None else "uncertain"
    )

    summary = _plan_summary(symbol, setup, current_stop, target, actual, alignment, strength, weakness)

    return {
        "campaign_id": cid,
        "account_id": account_id,
        "symbol": symbol,
        "plan_status": "pending_review",
        "plan_source": "auto_builder_v1",
        "plan_version": "campaign_plan_builder_v1",
        "setup_type": setup,
        "setup_source": _s(campaign.get("setup_source")),
        "decision_source": decision_source,
        "entry_price": entry_price,
        "initial_stop": current_stop,
        "current_stop": current_stop,
        "target_risk_usd": target,
        "actual_initial_risk_usd": actual,
        "risk_alignment": alignment,
        "risk_ratio": ratio,
        "sell_strength_plan": strength,
        "sell_weakness_plan": weakness,
        "emergency_plan": emergency,
        "plan_summary": summary,
        "confidence_score": confidence,
        "stat_basis": stats,
        "missing_required_fields": required_missing,
        "optional_missing_fields": optional_missing,
        "red_flags": red_flags,
        "data_quality_status": quality,
        "updated_at": _now(),
    }

def _task_for_plan(plan):
    required = plan.get("missing_required_fields") or []
    optional = plan.get("optional_missing_fields") or []
    red = plan.get("red_flags") or []

    if "initial_or_current_stop" in required:
        step = "enter_stop"
        prompt = (
            f"זוהה קמפיין פתוח ב-{plan['symbol']} ללא סטופ מאומת.\n"
            f"זה סיכון לא מנוהל. הזן סטופ או סמן דילוג כחריגה."
        )
    elif "setup_type" in required:
        step = "choose_setup"
        prompt = (
            f"זוהה קמפיין פתוח ב-{plan['symbol']} עם סטופ, אבל ללא Setup.\n"
            f"בחר אסטרטגיה כדי שנוכל למדוד את הקמפיין נכון."
        )
    else:
        step = "review_plan"
        prompt = (
            f"נבנתה תוכנית ניהול ראשונית ל-{plan['symbol']}.\n"
            f"ברירת המחדל מאושרת אם לא עורכים, אבל מומלץ לבדוק סטופ/Setup/קטליסט."
        )

    return {
        "campaign_id": plan["campaign_id"],
        "account_id": plan.get("account_id"),
        "symbol": plan["symbol"],
        "task_status": "pending",
        "current_step": step,
        "required_fields": required,
        "optional_fields": optional,
        "red_flags": red,
        "next_prompt_he": prompt,
        "updated_at": _now(),
    }

def build(dry_run=False, force=False):
    campaigns = _fetch_all("campaigns")
    risks = _latest_risk_by_campaign()
    existing_plans = _plans_by_campaign()
    stats = _strategy_stats()

    open_campaigns = [
        c for c in campaigns
        if c.get("has_open_position") or c.get("campaign_status") in ["active_managed", "runner", "partially_realized"]
    ]

    plans = []
    tasks = []

    for c in open_campaigns:
        cid = _s(c.get("campaign_id"))
        existing = existing_plans.get(cid)

        if existing and existing.get("plan_status") == "approved" and not force:
            continue

        plan = _build_one(c, risks.get(cid), stats)

        if existing and existing.get("plan_status") in ["skipped", "approved"] and not force:
            continue

        plans.append(plan)
        tasks.append(_task_for_plan(plan))

    if dry_run:
        print("open_campaigns_seen=", len(open_campaigns))
        print("plans_to_upsert=", len(plans))
        print("strategy_stats=", json.dumps(stats, ensure_ascii=False))
        for p in plans:
            print(json.dumps({
                "campaign_id": p["campaign_id"],
                "symbol": p["symbol"],
                "status": p["plan_status"],
                "setup": p["setup_type"],
                "stop": p["current_stop"],
                "target": p["target_risk_usd"],
                "actual": p["actual_initial_risk_usd"],
                "alignment": p["risk_alignment"],
                "confidence": p["confidence_score"],
                "quality": p["data_quality_status"],
                "required_missing": p["missing_required_fields"],
                "red_flags": p["red_flags"],
            }, ensure_ascii=False))
        return

    for p in plans:
        supabase.table("campaign_plans").upsert(p, on_conflict="campaign_id").execute()

    for t in tasks:
        supabase.table("campaign_intake_tasks").upsert(t, on_conflict="campaign_id").execute()

    for p in plans:
        if p.get("red_flags"):
            _audit(
                "campaign_plan_red_flags",
                "warning",
                "Auto-built campaign plan has red flags",
                {
                    "red_flags": p["red_flags"],
                    "missing_required_fields": p["missing_required_fields"],
                    "confidence_score": p["confidence_score"],
                    "data_quality_status": p["data_quality_status"],
                },
                symbol=p["symbol"],
                campaign_id=p["campaign_id"],
                account_id=p.get("account_id"),
            )

    print("plans_upserted=", len(plans))
    print("intake_tasks_upserted=", len(tasks))
    print("strategy_sample_size=", stats.get("sample_size"))
    print("strategy_confidence=", stats.get("confidence"))

def status():
    plans = _fetch_all("campaign_plans")
    tasks = _fetch_all("campaign_intake_tasks")

    print("campaign_plans=", len(plans))
    print("campaign_intake_tasks=", len(tasks))

    by_status = defaultdict(int)
    by_quality = defaultdict(int)
    by_step = defaultdict(int)

    for p in plans:
        by_status[p.get("plan_status")] += 1
        by_quality[p.get("data_quality_status")] += 1

    for t in tasks:
        by_step[t.get("current_step")] += 1

    print("plans_by_status=")
    for k, v in sorted(by_status.items(), key=lambda x: str(x[0])):
        print(f"  {k}: {v}")

    print("plans_by_quality=")
    for k, v in sorted(by_quality.items(), key=lambda x: str(x[0])):
        print(f"  {k}: {v}")

    print("tasks_by_step=")
    for k, v in sorted(by_step.items(), key=lambda x: str(x[0])):
        print(f"  {k}: {v}")

    print("pending_tasks=")
    for t in sorted([x for x in tasks if x.get("task_status") == "pending"], key=lambda x: x.get("symbol") or ""):
        print(
            f"  {t.get('symbol')} | {t.get('campaign_id')} | "
            f"step={t.get('current_step')} | required={t.get('required_fields')} | red={t.get('red_flags')}"
        )

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["dry-run", "build", "status"])
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if args.command == "dry-run":
        build(dry_run=True, force=args.force)
    elif args.command == "build":
        build(dry_run=False, force=args.force)
    elif args.command == "status":
        status()

if __name__ == "__main__":
    main()
