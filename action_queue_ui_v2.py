
import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone, timedelta

from telebot import types

STATE_FILE = Path(__file__).resolve().parent / "action_queue_state.json"
RTL = "\u200f"
SEP = "━━━━━━━━━━━━"

def _now():
    return datetime.now(timezone.utc)

def _load_state():
    if not STATE_FILE.exists():
        return {"items": {}}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"items": {}}

def _save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

def _s(v, default=""):
    if v is None:
        return default
    return str(v).strip()

def _f(v, default=0.0):
    try:
        return float(v)
    except Exception:
        return default

def _identifiers(row):
    ids = []
    for k in ("campaign_id", "symbol"):
        v = _s(row.get(k))
        if v and v not in ids:
            ids.append(v)
    return ids

def _decision_key(row):
    data = {
        "campaign_id": _s(row.get("campaign_id")),
        "symbol": _s(row.get("symbol")),
        "status": _s(row.get("status")),
        "position_state": _s(row.get("position_state")),
        "decision_bias": _s(row.get("decision_bias")),
        "primary_action": _s(row.get("primary_action") or row.get("suggested_action")),
        "violation_count": _s(row.get("violation_count")),
    }
    raw = json.dumps(data, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()

def _priority_score(row):
    txt = " ".join([
        _s(row.get("priority")),
        _s(row.get("urgency")),
        _s(row.get("status")),
        _s(row.get("position_state")),
    ]).lower()

    if "critical" in txt or "קריטי" in txt or "🚨" in txt:
        return 0
    if "high" in txt or "גבוה" in txt:
        return 1
    if "medium" in txt or "בינוני" in txt:
        return 2
    return 3

def _priority_label(row):
    score = _priority_score(row)
    return ["קריטי", "גבוה", "בינוני", "נמוך"][min(score, 3)]

def _is_hidden(row):
    state = _load_state()
    key = _decision_key(row)
    now = _now()

    for ident in _identifiers(row):
        item = state.get("items", {}).get(ident)
        if not item:
            continue

        if item.get("decision_key") != key:
            continue

        status = item.get("status")
        if status in ("done", "hidden"):
            return True

        if status == "snoozed":
            until = item.get("snooze_until")
            try:
                if until and datetime.fromisoformat(until) > now:
                    return True
            except Exception:
                pass

    return False

def _mark(row, status, note=None, snooze_hours=6):
    state = _load_state()
    state.setdefault("items", {})
    key = _decision_key(row)
    now = _now()

    item = {
        "status": status,
        "decision_key": key,
        "symbol": _s(row.get("symbol")),
        "campaign_id": _s(row.get("campaign_id")),
        "decision_bias": _s(row.get("decision_bias")),
        "primary_action": _s(row.get("primary_action") or row.get("suggested_action")),
        "updated_at": now.isoformat(),
        "note": note or "",
    }

    if status == "snoozed":
        item["snooze_until"] = (now + timedelta(hours=snooze_hours)).isoformat()

    for ident in _identifiers(row):
        state["items"][ident] = dict(item)

    _save_state(state)

def _latest_rows(supabase):
    rows = []

    for table, order_col in [
        ("decision_journal", "decision_at"),
        ("position_snapshots", "snapshot_at"),
    ]:
        try:
            res = supabase.table(table).select("*").order(order_col, desc=True).limit(120).execute()
            rows.extend(res.data or [])
        except Exception:
            pass

    latest = {}
    for row in rows:
        symbol = _s(row.get("symbol"))
        if not symbol:
            continue

        cid = _s(row.get("campaign_id")) or symbol
        if cid not in latest:
            latest[cid] = row

    return list(latest.values())

def _find_row(supabase, token):
    token = _s(token)
    if not token:
        return {}

    rows = _latest_rows(supabase)
    token_up = token.upper()

    for row in rows:
        if _s(row.get("campaign_id")) == token:
            return row

    for row in rows:
        if _s(row.get("symbol")).upper() == token_up:
            return row

    return {"campaign_id": token, "symbol": token}

def _action_text(row):
    return _s(row.get("primary_action") or row.get("suggested_action") or row.get("action"), "אין פעולה מוגדרת")

def _decision_text(row):
    return _s(row.get("decision_bias") or row.get("decision") or row.get("position_state"), "מעקב")

def _is_actionable(row):
    decision = _decision_text(row)
    action = _action_text(row)
    action_clean = action.strip().lower()
    blob = f"{decision} {action} {_s(row.get('status'))}".lower()

    if "closed" in blob or "סגור" in blob:
        return False

    if action_clean in ["בוצע", "done", "completed", "complete"]:
        return False

    return bool(_s(row.get("symbol")) and (decision != "מעקב" or action != "אין פעולה מוגדרת"))

def _log_event(supabase, category, row, note=None):
    try:
        supabase.table("ai_logs").insert({
            "category": category,
            "raw_response": {
                "symbol": _s(row.get("symbol")),
                "campaign_id": _s(row.get("campaign_id")),
                "decision_key": _decision_key(row),
                "decision": _decision_text(row),
                "action": _action_text(row),
                "note": note or "",
                "timestamp": _now().isoformat(),
            }
        }).execute()
    except Exception:
        pass

def _queue_message(rows):
    visible = [r for r in rows if _is_actionable(r) and not _is_hidden(r)]
    visible.sort(key=_priority_score)
    visible = visible[:8]

    if not visible:
        return (
            f"{RTL}🎯 תור פעולות - Sentinel\n"
            f"{RTL}{SEP}\n\n"
            f"{RTL}אין כרגע פעולות פתוחות.\n"
            f"{RTL}פעולות שסומנו כבוצע יופיעו שוב רק אם המצב או ההחלטה ישתנו."
        ), None, []

    lines = [
        f"{RTL}🎯 תור פעולות - Sentinel",
        f"{RTL}{SEP}",
        f"{RTL}מציג החלטות פתוחות בלבד. פעולה שסומנה כבוצע מוסתרת עד שינוי מהותי.",
        "",
    ]

    for i, row in enumerate(visible, 1):
        symbol = _s(row.get("symbol"), "?")
        setup = _s(row.get("setup_type"), "")
        lines += [
            f"{RTL}{i}. {symbol} {setup}",
            f"{RTL}• עדיפות: {_priority_label(row)} | מצב: {_s(row.get('status'), '-')}",
            f"{RTL}• החלטה: {_decision_text(row)}",
            f"{RTL}• פעולה: {_action_text(row)}",
        ]

        open_r = row.get("open_r")
        total_r = row.get("total_r")
        if open_r is not None or total_r is not None:
            lines.append(f"{RTL}• R: פתוח {_f(open_r):.1f}R | כולל {_f(total_r):.1f}R")

        vc = row.get("violation_count")
        if vc is not None:
            lines.append(f"{RTL}• הפרות: {_s(vc)}")

        lines.append("")

    markup = types.InlineKeyboardMarkup(row_width=1)
    for row in visible:
        token = _s(row.get("campaign_id")) or _s(row.get("symbol"))
        symbol = _s(row.get("symbol"), token)
        markup.add(types.InlineKeyboardButton(f"⚙️ ניהול {symbol}", callback_data=f"aq_menu|{token}"))

    return "\n".join(lines).strip(), markup, visible

def _management_message(row):
    symbol = _s(row.get("symbol"), "?")
    lines = [
        f"{RTL}⚙️ ניהול פעולה - {symbol}",
        f"{RTL}{SEP}",
        f"{RTL}• עדיפות: {_priority_label(row)}",
        f"{RTL}• מצב: {_s(row.get('status'), '-')}",
        f"{RTL}• החלטה: {_decision_text(row)}",
        f"{RTL}• פעולה: {_action_text(row)}",
    ]

    reason = _s(row.get("reason") or row.get("decision_reason") or row.get("management_summary"))
    if reason:
        lines.append(f"{RTL}• סיבה: {reason}")

    lines += [
        "",
        f"{RTL}אם הפעולה כבר בוצעה או לא רלוונטית יותר, סמני בוצע. היא לא תחזור עד שינוי מהותי."
    ]
    return "\n".join(lines)


def _parse_callback_data(data):
    data = _s(data)

    if "|" in data:
        op, token = data.split("|", 1)
        return op.strip(), token.strip()

    if ":" in data:
        op, token = data.split(":", 1)
        return op.strip(), token.strip()

    # Support older button formats if they still exist in Telegram.
    for prefix in ["aq_done_", "aq_not_done_", "aq_snooze_", "aq_menu_", "done_", "not_done_"]:
        if data.startswith(prefix):
            return prefix.rstrip("_"), data[len(prefix):].strip()

    return data, ""

def register(bot, get_supabase, get_user_state):
    def _supabase():
        return get_supabase()

    @bot.message_handler(func=lambda m: _s(getattr(m, "text", "")) in ["🎯 תור פעולות", "/actions"])
    def _handle_actions(message):
        supabase = _supabase()
        if supabase is None:
            bot.send_message(message.chat.id, f"{RTL}❌ אין חיבור למסד הנתונים כרגע.")
            return

        rows = _latest_rows(supabase)
        text, markup, _ = _queue_message(rows)
        bot.send_message(message.chat.id, text, reply_markup=markup)

    @bot.callback_query_handler(func=lambda call: _s(getattr(call, "data", "")).startswith(("aq_", "action_", "done", "not_done")))
    def _handle_action_callback(call):
        data = _s(call.data)
        op, token = _parse_callback_data(data)

        try:
            print(f"ActionQueue callback received: data={data} op={op} token={token}", flush=True)
        except Exception:
            pass

        try:
            bot.answer_callback_query(call.id, "נקלט. מעדכן...")
        except Exception:
            pass

        try:
            supabase = _supabase()
            row = _find_row(supabase, token) if supabase is not None else {"campaign_id": token, "symbol": token}
            symbol = _s(row.get("symbol"), token or "הפעולה")

            if op in ("aq_menu", "action_menu"):
                markup = types.InlineKeyboardMarkup(row_width=1)
                real_token = _s(row.get("campaign_id")) or symbol

                markup.add(types.InlineKeyboardButton("✅ בוצע / השתק עד שינוי", callback_data=f"aq_done|{real_token}"))
                markup.add(types.InlineKeyboardButton("📝 לא בוצע - להוסיף הערה", callback_data=f"aq_not_done|{real_token}"))
                markup.add(types.InlineKeyboardButton("🙈 השתק ל-6 שעות", callback_data=f"aq_snooze|{real_token}"))

                bot.send_message(call.message.chat.id, _management_message(row), reply_markup=markup)
                return

            if op in ("aq_done", "action_done", "done"):
                _mark(row, "done")

                if supabase is not None:
                    _log_event(supabase, "action_queue_done", row)

                bot.send_message(
                    call.message.chat.id,
                    f"{RTL}✅ {symbol} סומן כבוצע.\n"
                    f"{RTL}הפעולה הושתקה עד שינוי מהותי בהחלטת המערכת."
                )

                try:
                    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
                except Exception as e:
                    print(f"ActionQueue edit markup skipped: {e}", flush=True)

                return

            if op in ("aq_snooze", "action_snooze"):
                _mark(row, "snoozed", snooze_hours=6)

                bot.send_message(
                    call.message.chat.id,
                    f"{RTL}🙈 {symbol} הושתק ל-6 שעות.\n"
                    f"{RTL}אם המצב ישתנה מהותית, הפעולה תחזור לתור."
                )

                try:
                    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
                except Exception as e:
                    print(f"ActionQueue edit markup skipped: {e}", flush=True)

                return

            if op in ("aq_not_done", "action_not_done", "not_done"):
                state = get_user_state()
                state[call.message.chat.id] = {
                    "action": "aq_v2_note",
                    "aq_token": token,
                }

                bot.send_message(
                    call.message.chat.id,
                    f"{RTL}📝 למה הפעולה לא בוצעה?\n"
                    f"{RTL}כתבי הערה קצרה, והיא תישמר ביומן."
                )
                return

            bot.send_message(
                call.message.chat.id,
                f"{RTL}⚠️ הכפתור נקלט, אבל לא זוהתה פעולה מתאימה.\n"
                f"{RTL}נתון טכני: {data}"
            )

        except Exception as e:
            try:
                print(f"ActionQueue callback error: {e}", flush=True)
            except Exception:
                pass

            try:
                bot.send_message(
                    call.message.chat.id,
                    f"{RTL}❌ הכפתור נקלט אבל העדכון נכשל.\n"
                    f"{RTL}שגיאה: {e}"
                )
            except Exception:
                pass

    @bot.message_handler(func=lambda m: get_user_state().get(m.chat.id, {}).get("action") == "aq_v2_note")
    def _handle_not_done_note(message):
        state = get_user_state()
        st = state.get(message.chat.id, {})
        token = st.get("aq_token", "")
        note = _s(getattr(message, "text", ""))

        supabase = _supabase()
        row = _find_row(supabase, token) if supabase is not None else {"campaign_id": token, "symbol": token}

        _mark(row, "snoozed", note=note, snooze_hours=6)

        if supabase is not None:
            _log_event(supabase, "action_queue_not_done", row, note=note)

        state.pop(message.chat.id, None)

        symbol = _s(row.get("symbol"), token)
        bot.send_message(
            message.chat.id,
            f"{RTL}✅ ההערה נשמרה עבור {symbol}.\n"
            f"{RTL}הפעולה תופיע שוב בעוד כמה שעות אם היא עדיין רלוונטית."
        )

